"""A character's setups — list, create, get, update, archive, restore.

Feature `010`, step `002` (FEAT-007). Plain arguments in, a frozen `Setup` out or a typed
`DomainError` raised. This module imports nothing HTTP-shaped, never sees a request and
never names a status code. Every operation takes a Core `Connection` first and the owner's
`user_id` as a required positional argument after it; every statement carries the owner in
its `WHERE` or `VALUES`, so another user's id and nobody's id follow one path and raise the
same error (`context.md` R5, D8). A setup id that is not the caller's raises
`SetupNotFoundError`; a parent character that is not the caller's raises
`CharacterNotFoundError`, both from `app.errors`.

The six operations below are the whole surface: nothing here ever removes a row (R6), and
nothing here writes a `setups` row except `create_setup` (R2). A setup leaves the working
list by `archive_setup` and comes back by `restore_setup`, and the row survives both.

The statements run against the `setups` Table from `app.db.schema`, and the parent check
against the `characters` Table from the same module — this service never calls the
characters service (D6). Reads end the transaction they autobegan, on the normal return
**and** on the raise, so a later `connection.begin()` on the same request-scoped connection
still works; writes run inside `with connection.begin():` with the parent check and the
owner-scoped locating read in the same block; timestamps come from this module's own
private `_now_text()`, not from another service's helper.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection, Row, Select, Update, select

from app.db.schema import characters, setups
from app.errors import CharacterNotFoundError, SetupNotFoundError
from app.ids import SnowflakeGenerator


@dataclass(frozen=True)
class Setup:
    """One setup as every operation here returns it — and nothing more.

    No `user_id`: the owner is the caller's, never part of what is handed back. The field
    order is `SetupResponse`'s (`app.models.setups`, step `001`), so the router validates
    one of these straight through `from_attributes=True`. Timestamps are the stored
    fixed-width UTC text, passed through unparsed; `archived_at` is `None` for a working
    setup. `character_id` is the parent the setup was created under, fixed for life (D5).
    """

    id: int
    character_id: int
    name: str
    description: str
    archived_at: str | None
    created_at: str
    updated_at: str


def list_setups(
    connection: Connection,
    user_id: int,
    character_id: int,
    include_archived: bool = False,
) -> list[Setup]:
    """One of the owner's characters' setups, working only unless `include_archived`.

    Raises `CharacterNotFoundError` when the character does not exist for that user; an
    archived character of the user's is fine (D5). Newest created first (D10). A read:
    leaves no transaction open, including on the raise.
    """
    # Owner, parent and the working filter all live in the statement — nothing is fetched
    # and then filtered in Python (R5). The order is D10's; the snowflake breaks a
    # same-microsecond tie the same way the timestamp would.
    statement = _setup_select().where(setups.c.user_id == user_id, setups.c.character_id == character_id)
    if not include_archived:
        statement = statement.where(setups.c.archived_at.is_(None))
    statement = statement.order_by(setups.c.created_at.desc(), setups.c.id.desc())
    # Both reads sit in the one guard, so the autobegun transaction ends on the normal
    # return and on the parent check's raise alike.
    with _reading(connection):
        _require_parent_character(connection, user_id, character_id)
        rows = connection.execute(statement).all()
    return [_to_setup(row) for row in rows]


def create_setup(
    connection: Connection,
    generator: SnowflakeGenerator,
    user_id: int,
    character_id: int,
    name: str,
    description: str,
) -> Setup:
    """Insert one working setup under the owner's character and return it.

    In one write transaction: the parent check first, raising `CharacterNotFoundError` and
    inserting nothing when the character is missing or foreign; then the id minted from
    `generator`, `created_at` and `updated_at` stamped with the same instant, `archived_at`
    left NULL and `user_id` written from the argument. `name` and `description` are stored
    as given — validation belongs to the request model.
    """
    with connection.begin():
        # First, so a missing or foreign parent leaves the table untouched and mints no id.
        _require_parent_character(connection, user_id, character_id)
        new_id = generator.next_id()
        now = _now_text()
        connection.execute(
            setups.insert().values(
                id=new_id,
                user_id=user_id,
                character_id=character_id,
                name=name,
                description=description,
                archived_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        setup = _fetch_existing(connection, user_id, new_id)
    return setup


def get_setup(connection: Connection, user_id: int, setup_id: int) -> Setup:
    """One of the owner's setups by id, archived or not; otherwise `SetupNotFoundError`.

    A read: leaves no transaction open.
    """
    # No `archived_at` predicate here: an archived setup stays reachable by its own id.
    with _reading(connection):
        setup = _require_setup(connection, user_id, setup_id)
    return setup


def update_setup(
    connection: Connection,
    user_id: int,
    setup_id: int,
    name: str | None = None,
    description: str | None = None,
) -> Setup:
    """Write the supplied fields of the owner's setup and bump `updated_at`.

    `None` means "not supplied". With neither supplied nothing is written and the current
    row comes back. `character_id` and `archived_at` are never touched here, so an archived
    setup can be edited (D5, D9). Raises `SetupNotFoundError`.
    """
    supplied: dict[str, Any] = {}
    if name is not None:
        supplied["name"] = name
    if description is not None:
        supplied["description"] = description
    with connection.begin():
        setup = _require_setup(connection, user_id, setup_id)
        if supplied:
            supplied["updated_at"] = _now_text()
            connection.execute(_owned_update(user_id, setup_id).values(supplied))
            setup = _fetch_existing(connection, user_id, setup_id)
    return setup


def archive_setup(connection: Connection, user_id: int, setup_id: int) -> Setup:
    """Set `archived_at` and bump `updated_at` when the setup is working.

    On an already archived one nothing is written and it comes back with its original
    `archived_at` and `updated_at` (D9). Reads and writes no table but `setups` (D3).
    Raises `SetupNotFoundError`.
    """
    # D9: re-archiving keeps the first `archived_at`, so "when was this archived" stays
    # true, and it bumps no `updated_at` either — a no-op writes nothing at all. No other
    # table is touched: archiving does not cascade (D3).
    with connection.begin():
        setup = _require_setup(connection, user_id, setup_id)
        if setup.archived_at is None:
            now = _now_text()
            connection.execute(_owned_update(user_id, setup_id).values(archived_at=now, updated_at=now))
            setup = _fetch_existing(connection, user_id, setup_id)
    return setup


def restore_setup(connection: Connection, user_id: int, setup_id: int) -> Setup:
    """Clear `archived_at` and bump `updated_at` when the setup is archived.

    On a working one nothing is written (D9). Raises `SetupNotFoundError`.
    """
    with connection.begin():
        setup = _require_setup(connection, user_id, setup_id)
        if setup.archived_at is not None:
            connection.execute(_owned_update(user_id, setup_id).values(archived_at=None, updated_at=_now_text()))
            setup = _fetch_existing(connection, user_id, setup_id)
    return setup


def _setup_select() -> Select[tuple[int, int, str, str, str | None, str, str]]:
    """The one `setups` projection every result is built from — the owner stays out of it."""
    return select(
        setups.c.id,
        setups.c.character_id,
        setups.c.name,
        setups.c.description,
        setups.c.archived_at,
        setups.c.created_at,
        setups.c.updated_at,
    )


def _to_setup(row: Row[tuple[int, int, str, str, str | None, str, str]]) -> Setup:
    """Map a projected row to the plain result; the stored timestamp text passes through."""
    return Setup(
        id=row.id,
        character_id=row.character_id,
        name=row.name,
        description=row.description,
        archived_at=row.archived_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _owned_update(user_id: int, setup_id: int) -> Update:
    """An UPDATE carrying the owner in its own `WHERE`, not only in the locating read."""
    return setups.update().where(setups.c.id == setup_id, setups.c.user_id == user_id)


def _require_setup(connection: Connection, user_id: int, setup_id: int) -> Setup:
    """The owner's setup by id, or `SetupNotFoundError` — every write locates with this.

    Another user's id and an id that exists for nobody both miss this one `WHERE` and raise
    the same error: there is no "exists but not yours" branch (R5, D8).
    """
    row = connection.execute(_setup_select().where(setups.c.id == setup_id, setups.c.user_id == user_id)).first()
    if row is None:
        raise SetupNotFoundError()
    return _to_setup(row)


def _fetch_existing(connection: Connection, user_id: int, setup_id: int) -> Setup:
    """Read back one setup known to exist, inside the caller's transaction."""
    row = connection.execute(_setup_select().where(setups.c.id == setup_id, setups.c.user_id == user_id)).one()
    return _to_setup(row)


def _require_parent_character(connection: Connection, user_id: int, character_id: int) -> None:
    """This module's own scoped parent check, or `CharacterNotFoundError` (D6).

    Its own `SELECT` against the `characters` Table — never a call into the characters
    service, and never a join with `setups`, which could not tell "no setups yet" from "not
    your character". No `archived_at` predicate (D5).
    """
    row = connection.execute(
        select(characters.c.id).where(characters.c.id == character_id, characters.c.user_id == user_id)
    ).first()
    if row is None:
        raise CharacterNotFoundError()


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
