"""A session's memo chain — every level's notes in one read — and a note's reach.

Feature `015`, step `003` (FEAT-008). `resolve_chain` does one owner-scoped session read and
one memo select whose OR-terms are built from the levels that exist (R2); `memo_reach` is
the backend twin of R3's three-way derivation, `is_enabled` checked first (D7). From
`app.services.memos` this module imports only `Memo` and its row mapper (D11).
"""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import ColumnElement, Connection, and_, or_, select

from app.db.schema import memos, sessions
from app.errors import SessionNotFoundError
from app.models.memos import MemoScope
from app.services.memos import Memo, to_memo

MemoReach = Literal["forced", "searchable", "disabled"]


@dataclass(frozen=True)
class MemoChainLevel:
    """One level of a chain; `scope_id` is `None` for the user level.

    Field names are `MemoChainLevelResponse`'s, so it validates with `from_attributes=True`.
    """

    scope: MemoScope
    scope_id: int | None
    memos: list[Memo]


def resolve_chain(connection: Connection, user_id: int, session_id: int) -> list[MemoChainLevel]:
    """The caller's session's levels (user, character, setup if any, session) with their notes.

    `SessionNotFoundError` for a missing or foreign session; leaves no transaction open.
    """
    opened_here = not connection.in_transaction()
    try:
        # No `archived_at` predicate: an archived session still has its chain (D8).
        session_row = connection.execute(
            select(sessions.c.character_id, sessions.c.setup_id).where(
                sessions.c.id == session_id, sessions.c.user_id == user_id
            )
        ).first()
        if session_row is None:
            raise SessionNotFoundError()
        levels: list[tuple[MemoScope, int | None, int]] = [("user", None, user_id)]
        levels.append(("character", session_row.character_id, session_row.character_id))
        if session_row.setup_id is not None:
            levels.append(("setup", session_row.setup_id, session_row.setup_id))
        levels.append(("session", session_id, session_id))
        # One select: one OR-term per existing level; the owner predicate stays in SQL (R5).
        terms: list[ColumnElement[bool]] = [
            and_(memos.c.scope == scope, memos.c.scope_id == stored_id) for scope, _, stored_id in levels
        ]
        rows = connection.execute(
            select(memos).where(memos.c.user_id == user_id, or_(*terms)).order_by(memos.c.sort_key, memos.c.id)
        ).all()
    finally:
        if opened_here and connection.in_transaction():
            connection.rollback()
    buckets: dict[str, list[Memo]] = {scope: [] for scope, _, _ in levels}
    for row in rows:
        buckets[row.scope].append(to_memo(row))
    return [MemoChainLevel(scope=scope, scope_id=scope_id, memos=buckets[scope]) for scope, scope_id, _ in levels]


def memo_reach(is_enabled: bool, is_forced: bool) -> MemoReach:
    """`"disabled"` unless enabled; then `"forced"` or `"searchable"` by `is_forced`."""
    if not is_enabled:
        return "disabled"
    return "forced" if is_forced else "searchable"
