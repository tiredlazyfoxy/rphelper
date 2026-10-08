"""RP sessions — start under a character, list, get, archive, restore.

Feature `011`, step `002` (FEAT-008). Plain arguments in, a frozen `RpSession` out or a typed
`DomainError` raised. This module imports nothing HTTP-shaped, never sees a request and never
names a status code. Every operation takes a Core `Connection` first and the owner's `user_id`
as a required positional argument after it (after the generator, for the create); every
statement carries the owner in its own `WHERE` or `VALUES`, so another user's id and nobody's
id follow one path and raise the same error (`context.md` R5, D11). A session id that is not
the caller's raises `SessionNotFoundError`; a parent character that is not the caller's raises
`CharacterNotFoundError`; a chosen setup that is not the caller's under that same character
raises `SetupNotFoundError`, and one of the caller's that is archived raises
`SetupArchivedError` — all four from `app.errors`.

"Session" here is always the RP session (the `sessions` Table), never the login session:
`services/auth.py` owns `OpenedSession`, `open_session`, `resolve_session` and friends, and
nothing in this module shadows them (D11).

The seven operations below are the whole surface. Nothing here ever removes a row (R6), nothing
here writes a row in any table but `sessions` (R2 — no setup is ever created, and there is no
sentinel "no setup" row) except the one opening zone message `start_seeded_session` inserts
through `services/messages.py`'s transaction-neutral `insert_zone_message` (018 D3 — that helper
and `StreamMessage` are the only names imported from that module), and there is no "touch" operation:
`last_used_at` is stamped once at creation and bumped only by the content writes `012` brings (D3), so a read
— `get_session` included — never writes.

Creation captures the session's model in its one transaction, after the character and setup
checks (`017` D1): the character's own configured pair, taken as-is and never checked against
the registry (R4); otherwise the first enabled model (`017` D7, through `llm_registry`'s
transaction-neutral `first_enabled_chat_model` — the one service import, `017` D12); otherwise
NULL. Nothing else is copied from the character — prompt and tools resolve live. Every
configuration write after creation lives in `services/configuration.py` (`017` step `004`), not
here. A session leaves the working lists by `archive_session` and comes back by
`restore_session`, and the row survives both unchanged (D13).

Statements run against the `sessions` Table from `app.db.schema`, the parent check against the
`characters` Table and the setup check plus the `setup_name` label against `setups`, all from
that same module — this service never calls the characters or setups service (D11), and calls
the registry only for the capture above. `setup_name`
is joined at read time by an owner-scoped LEFT OUTER JOIN with no `archived_at` predicate on the
setup, so an archived setup still labels its sessions (D10). Reads end the transaction they
autobegan, on the normal return **and** on the raise, so a later `connection.begin()` on the
same request-scoped connection still works; writes run inside `with connection.begin():` with
the parent check, the setup check and the owner-scoped locating read in the same block;
timestamps come from this module's own private `_now_text()`, not from another service's helper.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Connection, Row, Select, Update, select

from app.db.schema import characters, sessions, setups
from app.errors import CharacterNotFoundError, SessionNotFoundError, SetupArchivedError, SetupNotFoundError
from app.ids import SnowflakeGenerator
from app.services.llm_registry import first_enabled_chat_model
from app.services.messages import StreamMessage, insert_zone_message


@dataclass(frozen=True)
class RpSession:
    """One RP session as every operation here returns it — and nothing more.

    No `user_id`: the owner is the caller's, never part of what is handed back. The field
    order is `SessionResponse`'s (`app.models.sessions`, step `001`), so the router validates
    one of these straight through `from_attributes=True`. Timestamps are the stored fixed-width
    UTC text, passed through unparsed; `archived_at` is `None` for a working session. `setup_id`
    is `None` when the session was started with no setup (R2), and `setup_name` is the
    referenced setup's current name joined at read time — `None` exactly when `setup_id` is,
    and present even when that setup is archived (D10).
    """

    id: int
    character_id: int
    setup_id: int | None
    setup_name: str | None
    archived_at: str | None
    last_used_at: str
    created_at: str
    updated_at: str


def start_session(
    connection: Connection,
    generator: SnowflakeGenerator,
    user_id: int,
    character_id: int,
    setup_id: int | None = None,
) -> RpSession:
    """Insert one working session under the owner's character and return it.

    In one write transaction, in this order (D12): the parent check, raising
    `CharacterNotFoundError` and inserting nothing when the character is missing or foreign —
    an archived character of the caller's is fine (D2); then, when `setup_id` is given, the
    setup check, raising `SetupNotFoundError` when it is not the caller's setup under that same
    character and `SetupArchivedError` when it is the caller's but archived; then the id minted
    from `generator`, with `created_at`, `updated_at` and `last_used_at` all stamped with the
    one instant (D3), `archived_at` left NULL and `user_id` written from the argument. The
    returned value carries `setup_name` from the setup the check already read, or `None`. Any
    refusal inserts nothing.
    """
    with connection.begin():
        session = _insert_session(connection, generator, user_id, character_id, setup_id)
    return session


@dataclass(frozen=True)
class StartedSession:
    """A just-created session and the opening message seeded into its zone, or `None` (018 D3)."""

    session: RpSession
    opening_message: StreamMessage | None


def start_seeded_session(
    connection: Connection,
    generator: SnowflakeGenerator,
    user_id: int,
    character_id: int,
    opening_text: str,
    setup_id: int | None = None,
) -> StartedSession:
    """Create a session exactly as `start_session` does and seed its zone in the same transaction.

    One `with connection.begin():` — the parent check, the optional setup check, the session id,
    `now`, 017's model capture and the session insert (shared with `start_session`), then
    `insert_zone_message` with the new session id and the **same** `now` (018 D3). No `(( ))`
    parsing, no settle, no model call, no second bump. Any failure inserts nothing.
    """
    # The session id is minted before the message id, both inside the one transaction, so a
    # failure of the message insert rolls the session insert back with it.
    with connection.begin():
        session = _insert_session(connection, generator, user_id, character_id, setup_id)
        # The session's own creation instant is the message's: creation and the first content
        # write are one instant, so `last_used_at` needs no second bump (018 D3, 011 D3).
        message = insert_zone_message(connection, generator, user_id, session.id, opening_text, session.created_at)
    return StartedSession(session=session, opening_message=message)


def _insert_session(
    connection: Connection,
    generator: SnowflakeGenerator,
    user_id: int,
    character_id: int,
    setup_id: int | None,
) -> RpSession:
    """The shared create body: checks, 017's model capture, id, `now`, insert — inside the caller's transaction.

    Opens no transaction itself; `start_session` and `start_seeded_session` each wrap it in
    their own `with connection.begin():`.
    """
    # D12's order, all inside the caller's one write transaction, so any refusal inserts
    # nothing: the parent character first, then the setup's existence under that same parent,
    # then its archive state.
    character_model = _require_parent_character(connection, user_id, character_id)
    setup_name: str | None = None
    if setup_id is not None:
        setup_name = _require_choosable_setup(connection, user_id, character_id, setup_id)
    # 017 D1, after every check so a refusal costs no registry read: the character's own
    # pair as-is (never validated, R4); else the first enabled model (D7); else NULL.
    model_server_id: int | None = None
    model_name: str | None = None
    if character_model is not None:
        model_server_id, model_name = character_model
    else:
        first_enabled = first_enabled_chat_model(connection)
        if first_enabled is not None:
            model_server_id = first_enabled.server.id
            model_name = first_enabled.model_name
    new_id = generator.next_id()
    now = _now_text()
    connection.execute(
        sessions.insert().values(
            id=new_id,
            user_id=user_id,
            character_id=character_id,
            setup_id=setup_id,
            model_server_id=model_server_id,
            model_name=model_name,
            last_used_at=now,
            archived_at=None,
            created_at=now,
            updated_at=now,
        )
    )
    # One instant for all three stamps (D3), and `setup_name` is the name the setup check
    # just read — so the created value needs no second read.
    return RpSession(
        id=new_id,
        character_id=character_id,
        setup_id=setup_id,
        setup_name=setup_name,
        archived_at=None,
        last_used_at=now,
        created_at=now,
        updated_at=now,
    )


def list_sessions(connection: Connection, user_id: int, include_archived: bool = False) -> list[RpSession]:
    """The owner's sessions across all of their characters, working only unless the flag is set.

    Ordered `last_used_at` descending, then `id` descending (D14), each with its `setup_name`
    (D10). A read: leaves no transaction open, and writes nothing (D3).
    """
    # Owner and the working filter both live in the statement — nothing is fetched and then
    # filtered in Python (R5). The order is D14's; the snowflake breaks a same-microsecond tie.
    statement = _session_select(user_id).where(sessions.c.user_id == user_id)
    if not include_archived:
        statement = statement.where(sessions.c.archived_at.is_(None))
    statement = statement.order_by(sessions.c.last_used_at.desc(), sessions.c.id.desc())
    with _reading(connection):
        rows = connection.execute(statement).all()
    return [_to_session(row) for row in rows]


def list_character_sessions(
    connection: Connection,
    user_id: int,
    character_id: int,
    include_archived: bool = False,
) -> list[RpSession]:
    """One of the owner's characters' sessions, working only unless `include_archived`.

    Raises `CharacterNotFoundError` when the character does not exist for that user; an
    archived character of the user's is fine (D2). Otherwise the same shape and order as
    `list_sessions` (D14). A read: leaves no transaction open, including on the raise.
    """
    statement = _session_select(user_id).where(
        sessions.c.user_id == user_id,
        sessions.c.character_id == character_id,
    )
    if not include_archived:
        statement = statement.where(sessions.c.archived_at.is_(None))
    statement = statement.order_by(sessions.c.last_used_at.desc(), sessions.c.id.desc())
    # Both reads sit in the one guard, so the autobegun transaction ends on the normal return
    # and on the parent check's raise alike.
    with _reading(connection):
        _require_parent_character(connection, user_id, character_id)
        rows = connection.execute(statement).all()
    return [_to_session(row) for row in rows]


def get_session(connection: Connection, user_id: int, session_id: int) -> RpSession:
    """One of the owner's sessions by id, archived or not; otherwise `SessionNotFoundError`.

    Whatever its character's archive state. Writes nothing at all — opening a session is not
    a use (D3). A read: leaves no transaction open, including on the raise.
    """
    # No `archived_at` predicate anywhere below: an archived session stays reachable by its id.
    with _reading(connection):
        session = _require_session(connection, user_id, session_id)
    return session


def archive_session(connection: Connection, user_id: int, session_id: int) -> RpSession:
    """Set `archived_at` and bump `updated_at` when the session is working.

    On an already archived one nothing is written and it comes back with its original
    `archived_at` and `updated_at` (D13). `last_used_at` is never touched (D3). Reads and
    writes no table but `sessions`, apart from the `setup_name` join of the locating read.
    Raises `SessionNotFoundError`.
    """
    # D13: re-archiving keeps the first `archived_at` and bumps no `updated_at` either — a
    # no-op writes nothing at all. `last_used_at` is never among the written values (D3).
    with connection.begin():
        session = _require_session(connection, user_id, session_id)
        if session.archived_at is None:
            now = _now_text()
            connection.execute(_owned_update(user_id, session_id).values(archived_at=now, updated_at=now))
            session = _fetch_existing(connection, user_id, session_id)
    return session


def restore_session(connection: Connection, user_id: int, session_id: int) -> RpSession:
    """Clear `archived_at` and bump `updated_at` when the session is archived.

    On a working one nothing is written (D13). `last_used_at` is never touched (D3). Every
    other field comes back exactly as it was before the archive (US-027.AC-3, the row half).
    Raises `SessionNotFoundError`.
    """
    with connection.begin():
        session = _require_session(connection, user_id, session_id)
        if session.archived_at is not None:
            connection.execute(_owned_update(user_id, session_id).values(archived_at=None, updated_at=_now_text()))
            session = _fetch_existing(connection, user_id, session_id)
    return session


def _session_select(user_id: int) -> Select[tuple[int, int, int | None, str | None, str | None, str, str, str]]:
    """The one `sessions` projection every result is built from, with the setup label joined.

    The owner stays out of the projection. The LEFT OUTER JOIN onto `setups` carries
    `setups.user_id == user_id` in the join condition itself and no `archived_at` predicate, so
    an archived setup still labels its sessions and another user's setup can never label one
    (D10, R5). Callers add their own `sessions.user_id` predicate, the working filter and the
    order.
    """
    label_join = (setups.c.id == sessions.c.setup_id) & (setups.c.user_id == user_id)
    return select(
        sessions.c.id,
        sessions.c.character_id,
        sessions.c.setup_id,
        setups.c.name,
        sessions.c.archived_at,
        sessions.c.last_used_at,
        sessions.c.created_at,
        sessions.c.updated_at,
    ).select_from(sessions.outerjoin(setups, label_join))


def _to_session(row: Row[tuple[int, int, int | None, str | None, str | None, str, str, str]]) -> RpSession:
    """Map a projected row to the plain result; the stored timestamp text passes through."""
    return RpSession(
        id=row.id,
        character_id=row.character_id,
        setup_id=row.setup_id,
        setup_name=row.name,
        archived_at=row.archived_at,
        last_used_at=row.last_used_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _owned_update(user_id: int, session_id: int) -> Update:
    """An UPDATE carrying the owner in its own `WHERE`, not only in the locating read."""
    return sessions.update().where(sessions.c.id == session_id, sessions.c.user_id == user_id)


def _require_session(connection: Connection, user_id: int, session_id: int) -> RpSession:
    """The owner's session by id, or `SessionNotFoundError` — every write locates with this.

    Another user's id and an id that exists for nobody both miss this one `WHERE` and raise the
    same error: there is no "exists but not yours" branch (R5, D12). No `archived_at` predicate:
    an archived session stays reachable by its own id.
    """
    row = connection.execute(
        _session_select(user_id).where(sessions.c.id == session_id, sessions.c.user_id == user_id)
    ).first()
    if row is None:
        raise SessionNotFoundError()
    return _to_session(row)


def _fetch_existing(connection: Connection, user_id: int, session_id: int) -> RpSession:
    """Read back one session known to exist, inside the caller's transaction."""
    row = connection.execute(
        _session_select(user_id).where(sessions.c.id == session_id, sessions.c.user_id == user_id)
    ).one()
    return _to_session(row)


def _require_parent_character(connection: Connection, user_id: int, character_id: int) -> tuple[int, str] | None:
    """This module's own scoped parent check, or `CharacterNotFoundError` (D11).

    Its own `SELECT` against the `characters` Table — never a call into the characters service,
    and never a join with `sessions`, which could not tell "no sessions yet" from "not your
    character". No `archived_at` predicate (D2). Answers the character's own configured model
    pair as stored, or `None` when it has none (017 D1); the pair is never checked against the
    registry here.
    """
    row = connection.execute(
        select(characters.c.id, characters.c.model_server_id, characters.c.model_name).where(
            characters.c.id == character_id, characters.c.user_id == user_id
        )
    ).first()
    if row is None:
        raise CharacterNotFoundError()
    if row.model_server_id is None or row.model_name is None:
        return None
    return (row.model_server_id, row.model_name)


def _require_choosable_setup(connection: Connection, user_id: int, character_id: int, setup_id: int) -> str:
    """The chosen setup's current name, or the refusal the request earned (D12).

    This module's own scoped `SELECT` against the `setups` Table — never a call into the setups
    service. No row for that id, user **and** character (nobody's, another user's, or one of the
    caller's other characters') raises `SetupNotFoundError`; a row of the caller's with
    `archived_at` set raises `SetupArchivedError`, because an archived setup is never offered,
    so naming one is stale or hand-made. Only ever called inside the create transaction.
    """
    row = connection.execute(
        select(setups.c.id, setups.c.name, setups.c.archived_at).where(
            setups.c.id == setup_id,
            setups.c.user_id == user_id,
            setups.c.character_id == character_id,
        )
    ).first()
    if row is None:
        raise SetupNotFoundError()
    if row.archived_at is not None:
        raise SetupArchivedError()
    name: str = row.name
    return name


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
