"""A user's memos — create at a level, list one level, update, delete.

Feature `015`, step `002` (FEAT-008). Plain arguments in, a frozen `Memo` out or a typed
`DomainError` raised. This module imports nothing HTTP-shaped and no other service module.
Every operation takes a Core `Connection` first and the owner's `user_id` as a required
positional argument after it (after the id generator, for the create).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection, Row, Update, func, select

from app.db.schema import characters, memos, sessions, setups
from app.errors import CharacterNotFoundError, MemoNotFoundError, SessionNotFoundError, SetupNotFoundError
from app.ids import SnowflakeGenerator
from app.models.memos import MemoScope


@dataclass(frozen=True)
class Memo:
    """One memo as every operation here returns it — the row minus `user_id`.

    `scope_id` is `None` exactly when `scope` is `"user"`. Field order is `MemoResponse`'s,
    so the router validates one of these through `from_attributes=True`.
    """

    id: int
    scope: MemoScope
    scope_id: int | None
    body: str
    is_enabled: bool
    is_forced: bool
    sort_key: int
    created_at: str
    updated_at: str


def to_memo(row: Row[Any]) -> Memo:
    """A full `memos` row (all ten columns) as its `Memo`; pure, no connection use."""
    # A user-level row stores the owner's id as its `scope_id`; the value hands back `None`.
    return Memo(
        id=row.id,
        scope=row.scope,
        scope_id=None if row.scope == "user" else row.scope_id,
        body=row.body,
        is_enabled=bool(row.is_enabled),
        is_forced=bool(row.is_forced),
        sort_key=row.sort_key,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def create_memo(
    connection: Connection,
    generator: SnowflakeGenerator,
    user_id: int,
    scope: MemoScope,
    scope_id: int | None,
    body: str,
) -> Memo:
    """Insert one enabled, not-forced memo at the caller's addressed level and return it."""
    with connection.begin():
        # D12's order: target check, allocation, id minting, insert. A refusal raises before
        # `next_id()`, so it inserts nothing and mints nothing.
        stored_scope_id = _require_target(connection, user_id, scope, scope_id)
        sort_key: int = connection.execute(
            select(func.coalesce(func.max(memos.c.sort_key), -1) + 1).where(
                memos.c.user_id == user_id,
                memos.c.scope == scope,
                memos.c.scope_id == stored_scope_id,
            )
        ).scalar_one()
        new_id = generator.next_id()
        now = _now_text()
        connection.execute(
            memos.insert().values(
                id=new_id,
                user_id=user_id,
                scope=scope,
                scope_id=stored_scope_id,
                body=body,
                is_enabled=True,
                is_forced=False,
                sort_key=sort_key,
                created_at=now,
                updated_at=now,
            )
        )
        memo = _fetch_existing(connection, user_id, new_id)
    return memo


def list_memos(
    connection: Connection,
    user_id: int,
    scope: MemoScope,
    scope_id: int | None,
) -> list[Memo]:
    """The caller's memos at one level, by `sort_key` then `id`; leaves no transaction open."""
    # Both reads sit in the one guard, so the autobegun transaction ends on the normal
    # return and on the target check's raise alike.
    with _reading(connection):
        stored_scope_id = _require_target(connection, user_id, scope, scope_id)
        rows = connection.execute(
            select(memos)
            .where(
                memos.c.user_id == user_id,
                memos.c.scope == scope,
                memos.c.scope_id == stored_scope_id,
            )
            .order_by(memos.c.sort_key, memos.c.id)
        ).all()
    return [to_memo(row) for row in rows]


def update_memo(
    connection: Connection,
    user_id: int,
    memo_id: int,
    body: str | None = None,
    is_enabled: bool | None = None,
    is_forced: bool | None = None,
) -> Memo:
    """Write only the supplied columns (plus `updated_at` if any) and return the row after."""
    # Only supplied columns reach the SET clause: `is_enabled` alone never writes
    # `is_forced` (R3, US-101), and nothing supplied writes nothing (D6).
    supplied: dict[str, Any] = {}
    if body is not None:
        supplied["body"] = body
    if is_enabled is not None:
        supplied["is_enabled"] = is_enabled
    if is_forced is not None:
        supplied["is_forced"] = is_forced
    with connection.begin():
        memo = _require_memo(connection, user_id, memo_id)
        if supplied:
            supplied["updated_at"] = _now_text()
            connection.execute(_owned_update(user_id, memo_id).values(supplied))
            memo = _fetch_existing(connection, user_id, memo_id)
    return memo


def delete_memo(connection: Connection, user_id: int, memo_id: int) -> None:
    """Delete the caller's memo; `MemoNotFoundError` when it is missing or foreign."""
    with connection.begin():
        result = connection.execute(memos.delete().where(memos.c.id == memo_id, memos.c.user_id == user_id))
        if result.rowcount == 0:
            raise MemoNotFoundError()


def _require_target(connection: Connection, user_id: int, scope: MemoScope, scope_id: int | None) -> int:
    """Check the addressed level is the caller's and return the stored `scope_id`.

    For `"user"` the target is the caller and the argument is ignored. Otherwise the row must
    be the caller's character / setup / session, with no lifecycle predicate (D8), each
    checked by its own scoped select against its own table, else that level's not-found error.
    """
    if scope == "user":
        return user_id
    if scope == "character":
        if scope_id is None or not _owned(connection, characters.c.id, characters.c.user_id, scope_id, user_id):
            raise CharacterNotFoundError()
    elif scope == "setup":
        if scope_id is None or not _owned(connection, setups.c.id, setups.c.user_id, scope_id, user_id):
            raise SetupNotFoundError()
    elif scope_id is None or not _owned(connection, sessions.c.id, sessions.c.user_id, scope_id, user_id):
        raise SessionNotFoundError()
    return scope_id


def _owned(connection: Connection, id_column: Any, owner_column: Any, row_id: int, user_id: int) -> bool:
    """Whether the parent row with this id belongs to this user."""
    statement = select(id_column).where(id_column == row_id, owner_column == user_id)
    return connection.execute(statement).first() is not None


def _owned_update(user_id: int, memo_id: int) -> Update:
    """An UPDATE carrying the owner in its own `WHERE`, not only in the locating read."""
    return memos.update().where(memos.c.id == memo_id, memos.c.user_id == user_id)


def _require_memo(connection: Connection, user_id: int, memo_id: int) -> Memo:
    """The caller's memo by id, or `MemoNotFoundError` (missing and foreign alike, R5)."""
    row = connection.execute(select(memos).where(memos.c.id == memo_id, memos.c.user_id == user_id)).first()
    if row is None:
        raise MemoNotFoundError()
    return to_memo(row)


def _fetch_existing(connection: Connection, user_id: int, memo_id: int) -> Memo:
    """Read back one memo known to exist, inside the caller's transaction."""
    row = connection.execute(select(memos).where(memos.c.id == memo_id, memos.c.user_id == user_id)).one()
    return to_memo(row)


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
