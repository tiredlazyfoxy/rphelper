"""The roleplayer's characters — list, create, get, update, archive, restore.

Feature `009`, step `002` (FEAT-006). Plain arguments in, a frozen `Character` out or a
typed `DomainError` raised. This module imports nothing HTTP-shaped, never sees a request
and never names a status code. Every operation takes a Core `Connection` first and the
owner's `user_id` as a required positional argument after it; every statement carries the
owner in its `WHERE` or `VALUES`, so another user's id and nobody's id follow one path and
raise the same `CharacterNotFoundError` from `app.errors` (`context.md` R5, D8).

The six operations below are the whole surface: nothing here ever removes a row (R6). A
character leaves the working list by `archive_character` and comes back by
`restore_character`, and the row survives both.

Feature `024`, step `006` adds one seam and nothing else: when `update_character` writes a
`sheet` that differs from the stored one, every session that persona feeds is re-indexed
inside the same transaction, strictly (024 D5, D8, U4). That work lives in
`app.services.session_index` — the single service this module imports — so the outbound
client factory and the one outbound timeout arrive here as keyword-only arguments with
defaults (024 D9) and no setting is ever looked up. `create_character`, `archive_character`
and `restore_character` do no search work at all.

Implementation notes for the coder (nothing below is frozen): the statements run against
the `characters` Table from `app.db.schema`; reads end the transaction they autobegan so a
later `connection.begin()` on the same request-scoped connection still works; writes run
inside `with connection.begin():` with the owner-scoped locating read in the same block;
timestamps come from this module's own private `_now_text()` returning
`datetime.now(UTC).isoformat(timespec="microseconds")`, not from another service's helper.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection, Row, Select, Update, select

from app.db.schema import characters
from app.errors import CharacterNotFoundError
from app.ids import SnowflakeGenerator
from app.services.session_index import (
    DEFAULT_EMBED_TIMEOUT_SECONDS,
    LlmClient,
    LlmClientFactory,
    refresh_session_vectors,
    session_ids_for_character,
)


@dataclass(frozen=True)
class Character:
    """One character as every operation here returns it — and nothing more.

    No `user_id`: the owner is the caller's, never part of what is handed back. Timestamps
    are the stored fixed-width UTC text, passed through unparsed; `archived_at` is `None`
    for a working character.
    """

    id: int
    name: str
    sheet: str
    archived_at: str | None
    created_at: str
    updated_at: str


def list_characters(connection: Connection, user_id: int, include_archived: bool = False) -> list[Character]:
    """The owner's characters, working only unless `include_archived`, newest created first.

    A read: leaves no transaction open.
    """
    # The owner predicate and the working filter both live in the statement — nothing is
    # fetched and then filtered in Python (R5). The order is D10's interim one; the
    # snowflake breaks a same-microsecond tie the same way the timestamp would.
    statement = _character_select().where(characters.c.user_id == user_id)
    if not include_archived:
        statement = statement.where(characters.c.archived_at.is_(None))
    statement = statement.order_by(characters.c.created_at.desc(), characters.c.id.desc())
    with _reading(connection):
        rows = connection.execute(statement).all()
    return [_to_character(row) for row in rows]


def create_character(
    connection: Connection,
    generator: SnowflakeGenerator,
    user_id: int,
    name: str,
    sheet: str,
) -> Character:
    """Insert one working character owned by `user_id` and return it.

    The id is minted from `generator` before the insert; `created_at` and `updated_at` are
    stamped with the same instant and `archived_at` stays NULL. `name` and `sheet` are
    stored as given — validation belongs to the request model.
    """
    with connection.begin():
        new_id = generator.next_id()
        now = _now_text()
        connection.execute(
            characters.insert().values(
                id=new_id,
                user_id=user_id,
                name=name,
                sheet=sheet,
                archived_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        character = _fetch_existing(connection, user_id, new_id)
    return character


def get_character(connection: Connection, user_id: int, character_id: int) -> Character:
    """One of the owner's characters by id, archived or not; otherwise `CharacterNotFoundError`.

    A read: leaves no transaction open.
    """
    # No `archived_at` predicate here: an archived character stays reachable by its own id.
    with _reading(connection):
        character = _require_character(connection, user_id, character_id)
    return character


def update_character(
    connection: Connection,
    user_id: int,
    character_id: int,
    name: str | None = None,
    sheet: str | None = None,
    *,
    client_factory: LlmClientFactory = LlmClient,
    timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS,
) -> Character:
    """Write the supplied fields of the owner's character and bump `updated_at`.

    `None` means "not supplied". With neither supplied nothing is written and the current
    row comes back. `archived_at` is never touched here, so an archived character can be
    edited.

    A `sheet` that differs from the stored one also re-indexes every session of this
    character, archived ones included, inside this one transaction and **strictly**: an
    unusable designation or a failed embed propagates, and the persona edit is not stored
    (024 D5, D6, D8, U4). A name-only edit, a resent unchanged sheet, and a character with
    no sessions do no search work and resolve no model, so they need neither keyword
    argument. `client_factory` and `timeout_seconds` are keyword-only with the usual
    defaults (024 D9), which is why every existing positional call still binds.
    """
    supplied: dict[str, Any] = {}
    if name is not None:
        supplied["name"] = name
    if sheet is not None:
        supplied["sheet"] = sheet
    with connection.begin():
        character = _require_character(connection, user_id, character_id)
        # The pre-update sheet, taken from the owner-scoped read the authorisation already
        # performs: this is the only moment the stored value is still the old one, and
        # "changed" is defined against it (024 D5).
        stored_sheet = character.sheet
        if supplied:
            supplied["updated_at"] = _now_text()
            connection.execute(_owned_update(user_id, character_id).values(supplied))
            character = _fetch_existing(connection, user_id, character_id)
        # The persona fan-out, last in this write transaction so every composed session text
        # reads the sheet the block above just wrote (024 D6). The dispatch is narrow on
        # purpose: a sheet that was not supplied, and a sheet resent identical to the stored
        # one, both fall through — a name-only edit does no search work and resolves no
        # model, whatever the registry holds (024 D5).
        if sheet is not None and sheet != stored_sheet:
            # Ascending id, archived sessions included, no archive predicate (U4): a restored
            # session must not come back silently stale.
            session_ids = session_ids_for_character(connection, user_id, character_id)
            # Only when N > 0 (U4). A character with no session has nothing to re-index, so
            # the strict refresh is never entered and no designation is resolved.
            if session_ids:
                # Strict (024 D8): nothing here is caught, so an unusable designation or a
                # failed embed propagates, this transaction rolls back, and the sheet stays
                # as it was — the persona edit is not stored.
                refresh_session_vectors(
                    connection,
                    user_id,
                    session_ids,
                    client_factory=client_factory,
                    timeout_seconds=timeout_seconds,
                )
    return character


def archive_character(connection: Connection, user_id: int, character_id: int) -> Character:
    """Set `archived_at` and bump `updated_at` when the character is working.

    On an already archived one nothing is written and it comes back with its original
    `archived_at`.
    """
    # D9: re-archiving keeps the first `archived_at`, so "when was this archived" stays
    # true, and it bumps no `updated_at` either — a no-op writes nothing at all.
    with connection.begin():
        character = _require_character(connection, user_id, character_id)
        if character.archived_at is None:
            now = _now_text()
            connection.execute(_owned_update(user_id, character_id).values(archived_at=now, updated_at=now))
            character = _fetch_existing(connection, user_id, character_id)
    return character


def restore_character(connection: Connection, user_id: int, character_id: int) -> Character:
    """Clear `archived_at` and bump `updated_at` when the character is archived.

    On a working one nothing is written.
    """
    with connection.begin():
        character = _require_character(connection, user_id, character_id)
        if character.archived_at is not None:
            connection.execute(
                _owned_update(user_id, character_id).values(archived_at=None, updated_at=_now_text())
            )
            character = _fetch_existing(connection, user_id, character_id)
    return character


def _character_select() -> Select[tuple[int, str, str, str | None, str, str]]:
    """The one `characters` projection every result is built from — the owner stays out of it."""
    return select(
        characters.c.id,
        characters.c.name,
        characters.c.sheet,
        characters.c.archived_at,
        characters.c.created_at,
        characters.c.updated_at,
    )


def _to_character(row: Row[tuple[int, str, str, str | None, str, str]]) -> Character:
    """Map a projected row to the plain result; the stored timestamp text passes through."""
    return Character(
        id=row.id,
        name=row.name,
        sheet=row.sheet,
        archived_at=row.archived_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _owned_update(user_id: int, character_id: int) -> Update:
    """An UPDATE carrying the owner in its own `WHERE`, not only in the locating read."""
    return characters.update().where(characters.c.id == character_id, characters.c.user_id == user_id)


def _require_character(connection: Connection, user_id: int, character_id: int) -> Character:
    """The owner's character by id, or `CharacterNotFoundError` — every write locates with this.

    Another user's id and an id that exists for nobody both miss this one `WHERE` and
    raise the same error: there is no "exists but not yours" branch (R5, D8).
    """
    row = connection.execute(
        _character_select().where(characters.c.id == character_id, characters.c.user_id == user_id)
    ).first()
    if row is None:
        raise CharacterNotFoundError()
    return _to_character(row)


def _fetch_existing(connection: Connection, user_id: int, character_id: int) -> Character:
    """Read back one character known to exist, inside the caller's transaction."""
    row = connection.execute(
        _character_select().where(characters.c.id == character_id, characters.c.user_id == user_id)
    ).one()
    return _to_character(row)


@contextmanager
def _reading(connection: Connection) -> Iterator[None]:
    """A read on a Core connection autobegins; end it again when the caller had none open."""
    opened_here = not connection.in_transaction()
    try:
        yield
    finally:
        if opened_here and connection.in_transaction():
            connection.rollback()


def _now_text() -> str:
    """Now as the fixed-width UTC ISO-8601 text the other services write."""
    return datetime.now(UTC).isoformat(timespec="microseconds")
