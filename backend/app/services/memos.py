"""A user's memos — create at a level, list one level, update, delete.

Feature `015`, step `002` (FEAT-008). Plain arguments in, a frozen `Memo` out or a typed
`DomainError` raised. This module imports nothing HTTP-shaped. Every operation takes a Core
`Connection` first and the owner's `user_id` as a required positional argument after it
(after the id generator, for the create).

Feature `024`, step `004` added the search seam: a write that stores a new body, or removes
a memo, keeps that memo's search rows in step **inside the same transaction** (024 D5, D7).
That makes `app.services.embedding` the **one and only** other service module imported here;
everything else it needs (the vector table name, the two ensure functions) lives under
`app.db`. The client factory and the outbound timeout arrive as keyword-only arguments with
defaults (024 D9), so every existing positional caller still calls the same way.

The posture is **strict** (024 D8): if the designated embedding model is unusable or the
embed call fails, `NoEmbeddingModelError` / `LlmUnreachableError` propagates, the
transaction rolls back and nothing is stored. A flag-only update, a body equal to the
stored one and `reorder_memos` do no search work at all and never touch the factory.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection, Row, Update, func, select

from app.db.schema import characters, memos, sessions, setups
from app.db.search_tables import MEMO_VEC_TABLE, ensure_fts_tables, ensure_vector_tables
from app.errors import (
    CharacterNotFoundError,
    MemoNotFoundError,
    MemoOrderMismatchError,
    SessionNotFoundError,
    SetupNotFoundError,
)
from app.ids import SnowflakeGenerator
from app.models.memos import MemoScope
from app.services.embedding import (
    DEFAULT_EMBED_TIMEOUT_SECONDS,
    LlmClient,
    LlmClientFactory,
    delete_vector,
    embed_texts,
    open_embedding_model,
    write_vector,
)


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
    *,
    client_factory: LlmClientFactory = LlmClient,
    timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS,
) -> Memo:
    """Insert one enabled, not-forced memo at the caller's addressed level and return it.

    `client_factory` and `timeout_seconds` are keyword-only with defaults (024 D9): the
    route passes the shared factory and `settings.llm_request_timeout_seconds`, and a caller
    that passes neither gets the real client and `Settings`' own declared default. They are
    used only for the search seam below, and a blank body never reaches a model at all.
    """
    with connection.begin():
        # D12's order: target check, allocation, id minting, insert. A refusal raises before
        # `next_id()`, so it inserts nothing and mints nothing.
        stored_scope_id = _require_target(connection, user_id, scope, scope_id)
        # New-note-first (016 D5): one below the level's minimum, or 0 for an empty level.
        sort_key: int = connection.execute(
            select(func.coalesce(func.min(memos.c.sort_key), 1) - 1).where(
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
        # The search seam, inside this transaction and after the insert (024 D5). Every create
        # reaches it unguarded: the helper owns D7's blank-body decision, so a whitespace-only
        # body resolves no model and calls no factory, while a real one embeds strictly and a
        # failure rolls this insert back with it.
        _refresh_memo_search_rows(
            connection,
            new_id,
            body,
            client_factory=client_factory,
            timeout_seconds=timeout_seconds,
        )
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
    *,
    client_factory: LlmClientFactory = LlmClient,
    timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS,
) -> Memo:
    """Write only the supplied columns (plus `updated_at` if any) and return the row after.

    `client_factory` and `timeout_seconds` are keyword-only with defaults (024 D9), exactly
    as on `create_memo`; the three positional value parameters keep their own defaults, so
    every existing call shape still binds. They are consulted **only** when a supplied
    `body` differs from the stored one — a flag-only update, or a body equal to the stored
    one, must not construct a client whatever the registry holds (UC-044, UC-075).
    """
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
        # The owner-scoped read that authorises the update also answers "did the body change":
        # this is the value **as stored before** the update, captured inside the same
        # transaction (024 D5, `004.context.md`).
        stored_body = memo.body
        if supplied:
            supplied["updated_at"] = _now_text()
            connection.execute(_owned_update(user_id, memo_id).values(supplied))
            memo = _fetch_existing(connection, user_id, memo_id)
        # D5's guard, and the whole point of this step: search work happens only when a `body`
        # was supplied **and** differs from what was stored. A flag-only update, and a body
        # resent unchanged alongside a flag, therefore ensure no table, resolve no model and
        # never call the factory, whatever the registry holds (UC-044, UC-075).
        if body is not None and body != stored_body:
            _refresh_memo_search_rows(
                connection,
                memo_id,
                memo.body,
                client_factory=client_factory,
                timeout_seconds=timeout_seconds,
            )
    return memo


def delete_memo(connection: Connection, user_id: int, memo_id: int) -> None:
    """Delete the caller's memo and its search rows; `MemoNotFoundError` when missing or foreign.

    The signature is unchanged (024 D5): dropping a vector row needs no model, so this takes
    neither a factory nor a timeout and can never answer `no_embedding_model`.
    """
    with connection.begin():
        result = connection.execute(memos.delete().where(memos.c.id == memo_id, memos.c.user_id == user_id))
        if result.rowcount == 0:
            raise MemoNotFoundError()
        # Inside this transaction and after the row is gone. The ensure is all a pre-024
        # instance needs — once `memo_fts` exists its delete trigger has already removed the
        # text row with the memo. The vector row has no trigger, so it goes by hand;
        # `delete_vector` tolerates both an absent row and an absent table, and no model is
        # resolved, so a delete can never answer `no_embedding_model`.
        ensure_fts_tables(connection)
        delete_vector(connection, MEMO_VEC_TABLE, memo_id)


def reorder_memos(
    connection: Connection,
    user_id: int,
    scope: MemoScope,
    scope_id: int | None,
    memo_ids: list[int],
) -> list[Memo]:
    """Rewrite one level's whole order as 0..n-1 in one owner-scoped transaction (016 D6).

    `MemoOrderMismatchError` unless `memo_ids` is exactly the level's notes with no repeat;
    writes only `sort_key`. Returns the level's notes by `sort_key` then `id`.
    """
    with connection.begin():
        stored_scope_id = _require_target(connection, user_id, scope, scope_id)
        level = (
            memos.c.user_id == user_id,
            memos.c.scope == scope,
            memos.c.scope_id == stored_scope_id,
        )
        held_ids: set[int] = set(connection.execute(select(memos.c.id).where(*level)).scalars().all())
        # Both sets come from owner-scoped reads/arguments; a refusal raises before any write.
        if len(memo_ids) != len(set(memo_ids)) or set(memo_ids) != held_ids:
            raise MemoOrderMismatchError()
        for index, memo_id in enumerate(memo_ids):
            # `sort_key` only — `updated_at` is deliberately not touched (D6).
            connection.execute(memos.update().where(memos.c.id == memo_id, *level).values(sort_key=index))
        rows = connection.execute(select(memos).where(*level).order_by(memos.c.sort_key, memos.c.id)).all()
    return [to_memo(row) for row in rows]


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


def _refresh_memo_search_rows(
    connection: Connection,
    memo_id: int,
    body: str,
    *,
    client_factory: LlmClientFactory,
    timeout_seconds: float,
) -> None:
    """Leave this memo's search rows matching `body`, inside the caller's transaction (024 D5/D7).

    The one search seam of this module, and the only place a client is ever built here. `body`
    is the body **as now stored**; `memo_id` is a memo that exists. Both keyword arguments are
    required, so neither call site can drift onto a default.

    The work, in this order (`004.context.md`):

    1. ensure the full-text half — all a pre-024 instance needs; the `memo_fts` triggers keep
       the text half in step by themselves once the table exists.
    2. A non-blank `body` (024 D7): open the designated model, ensure the vector tables at its
       dimension, make **one** embed call carrying the body **alone** — US-119 means a memo is
       nothing but its body — and write the `memo_vec` row.
    3. A whitespace-only `body`: drop the `memo_vec` row and nothing else. No model is
       resolved and no embed call is made, because a blank memo has nothing to retrieve and an
       empty string is an invalid embed input for common providers.

    Strict (024 D8): nothing is caught. `NoEmbeddingModelError` (including the dimension
    mismatch) and `LlmUnreachableError` propagate, and the caller's transaction rolls back
    the relational write together with any DDL an ensure created.
    """
    # Step 1 runs on every call, blank body included, so a pre-024 instance ends up with its
    # back-filled full-text tables even when there is nothing to embed.
    ensure_fts_tables(connection)
    if not body.strip():
        # Step 3. Tolerant of an absent row and of a database with no vector table at all.
        delete_vector(connection, MEMO_VEC_TABLE, memo_id)
        return
    # Step 2. The model is opened **before** the vector ensure, so a missing or unusable
    # designation fails before any DDL; the ensure then precedes the write, so a dimension
    # mismatch fails before any vector row is touched.
    handle = open_embedding_model(connection, client_factory=client_factory, timeout_seconds=timeout_seconds)
    ensure_vector_tables(connection, handle.embedding_dim)
    # One call carrying one text. Unpacking a single vector makes a provider that answers the
    # wrong count a `ValueError` instead of a silent miss (step 003's posture).
    (vector,) = embed_texts(handle, [body])
    write_vector(connection, MEMO_VEC_TABLE, memo_id, vector)


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
