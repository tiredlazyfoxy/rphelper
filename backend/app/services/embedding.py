"""The embedding seam — the designated model as a ready client, the sync bridge, vector rows.

Feature 024, step `002`. Four things live here and nothing else:

- **`open_embedding_model`** turns a connection into an `EmbeddingModelHandle`: it asks
  `app.services.llm_registry.validate_embedding_model` for the designation (no
  substitution, R4 — an unusable designation is `NoEmbeddingModelError` and no other model
  is ever tried), re-selects that server's `api_key_ref` from `llm_servers` (the pointer is
  deliberately not a field on `LlmServer`), resolves it through `app.secrets.resolve_secret`
  and builds the client **once**. It makes no network call, so a write that turns out to
  need no embedding pays nothing.
- **`embed_texts`** is the sync bridge (D1). `LlmClient.embed` is a coroutine; every 024
  caller is a sync `def` service running inside `with connection.begin():` on a threadpool
  thread with no running loop, so one `asyncio.run` per call is both legal and sufficient.
  **One client and one `embed` call per write operation**: `asyncio.run` closes the loop it
  made, and an httpx pool bound to a closed loop is the failure that rule avoids. A fan-out
  over N sessions therefore sends one request carrying N texts, not N requests.
- **`write_vector` / `delete_vector`** are the only vector-row writers in the backend
  (D4). The forms are not stylistic: on sqlite-vec 0.1.9 `INSERT OR REPLACE` — and
  `INSERT OR IGNORE` — raise `UNIQUE constraint failed on <table> primary key`, because
  vec0 ignores the conflict clause. The upsert is delete-then-insert by id, and vectors are
  serialised with `sqlite_vec.serialize_float32`.
- **`DEFAULT_EMBED_TIMEOUT_SECONDS`**, the timeout every downstream service defaults to.

This module imports **nothing from the web framework** — no application object, no
`Request`, no `Depends` (`context.md`: services take the client factory and the timeout as
plain arguments, and the routers supply them). It opens no transaction of its own — the
caller's `begin()` block is already open — and it issues no KNN query and no FTS `MATCH`,
which belong to `025`.

Error posture (D8): both failures leave this module unchanged and untranslated.
`NoEmbeddingModelError` (409) comes out of `open_embedding_model` for a missing or disabled
designation and out of `embed_texts` for a returned vector of the wrong length, with
`detail` exactly `{"reason": "dimension_mismatch"}`. `LlmUnreachableError` (502) propagates
from `embed` as raised. Deciding which to swallow is the caller's: an authoring write lets
both through (strict), a record-keeping write catches both and flags incomplete coverage.
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import sqlite_vec  # type: ignore[import-untyped]
from sqlalchemy import Connection, select, text

from app.config import Settings
from app.db.schema import llm_servers
from app.errors import NoEmbeddingModelError
from app.secrets import resolve_secret
from app.services.llm.client import LlmClient
from app.services.llm_registry import LlmClientFactory, LlmClientLike, validate_embedding_model

DEFAULT_EMBED_TIMEOUT_SECONDS: Final[float] = Settings.model_fields[
    "llm_request_timeout_seconds"
].default
"""The services' default outbound timeout, **read from the field declaration** (D9).

Taken from `Settings`' own default for `llm_request_timeout_seconds` rather than re-typed
here, so the number lives in exactly one place (`config.py`). A route that depends on
`get_settings` passes `settings.llm_request_timeout_seconds` and never sees this value.
"""


@dataclass(frozen=True)
class EmbeddingModelHandle:
    """A designated embedding model resolved into something callable, for one write.

    Frozen, and deliberately short-lived: `client` is bound to the one `asyncio.run` that
    `embed_texts` will do for it (D1). Do not cache a handle across write operations.
    """

    client: LlmClientLike
    """The constructed client, typed as the registry's protocol so a fake satisfies it."""
    model_name: str
    """The designated model's name, passed to `client.embed` as-is."""
    embedding_dim: int
    """The designation's declared dimension; every returned vector must have this length."""


def open_embedding_model(
    connection: Connection,
    *,
    client_factory: LlmClientFactory = LlmClient,
    timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS,
) -> EmbeddingModelHandle:
    """Resolve the designated embedding model into a ready `EmbeddingModelHandle`.

    Calls `validate_embedding_model(connection)`, whose `NoEmbeddingModelError` propagates
    unchanged (no designation, the designated model disabled, or no `embedding_dim`). Then
    re-selects that server's `api_key_ref` from `llm_servers` by `server.id` — `LlmServer`
    does not carry the pointer — resolves it through `resolve_secret`, whose
    `SecretRefError` propagates, and calls `client_factory(base_url, api_key,
    timeout_seconds)` **exactly once**.

    **No network call happens here**, and no vector table is created or read. `connection`
    may already be inside the caller's transaction; this opens none of its own.
    """
    designation = validate_embedding_model(connection)
    # The pointer text is not a field on `LlmServer` (only `has_api_key` is), so it is
    # re-read from the row by id — the re-select `designate_embedding_model` already does.
    # A read on a Core connection autobegins, so a transaction begun here is ended again;
    # inside the caller's `begin()` block both checks are false and nothing happens.
    opened_here = not connection.in_transaction()
    try:
        row = connection.execute(
            select(llm_servers.c.api_key_ref).where(llm_servers.c.id == designation.server.id)
        ).first()
    finally:
        if opened_here and connection.in_transaction():
            connection.rollback()
    # Resolved before any client exists, so an unset variable raises `SecretRefError`
    # instead of yielding a client that would only fail on the wire.
    api_key = resolve_secret(row.api_key_ref if row is not None else None)
    client = client_factory(designation.server.base_url, api_key, timeout_seconds)
    return EmbeddingModelHandle(client, designation.model_name, designation.embedding_dim)


def embed_texts(handle: EmbeddingModelHandle, texts: Sequence[str]) -> list[list[float]]:
    """Embed `texts` through `handle`'s client, synchronously: one vector per text, in order.

    Makes **one** `handle.client.embed(handle.model_name, texts)` call and runs it to
    completion with `asyncio.run` (D1). `texts` is non-empty; batching N texts into the one
    call is what the fan-out relies on.

    `LlmUnreachableError` propagates exactly as `embed` raised it, reason and all. A
    returned vector whose length is not `handle.embedding_dim` raises
    `NoEmbeddingModelError` with a fixed message and `detail` exactly
    `{"reason": "dimension_mismatch"}` (D8) — a wrong-width model counts as unavailable,
    not as a transport fault.

    Must not be called from inside a running event loop; no 024 caller does.
    """
    # One `embed`, one `asyncio.run`: the loop this makes is closed again on return, which is
    # why a handle's client is never reused across write operations (D1).
    vectors = asyncio.run(handle.client.embed(handle.model_name, texts))
    if any(len(vector) != handle.embedding_dim for vector in vectors):
        raise NoEmbeddingModelError(
            "The designated embedding model returned a vector of the wrong width.",
            {"reason": "dimension_mismatch"},
        )
    return vectors


def write_vector(
    connection: Connection, table_name: str, row_id: int, vector: Sequence[float]
) -> None:
    """Leave exactly one row of `table_name` for `row_id`, holding `vector`.

    `table_name` is `MEMO_VEC_TABLE` or `SESSION_VEC_TABLE` from `app.db.search_tables`,
    and **the table must already exist** — the caller ensured it at the designation's
    dimension. `row_id` is a snowflake (above 2^60; vec0 stores those fine) and `vector`
    has that table's declared width.

    The form is delete-then-insert by id, serialising with `sqlite_vec.serialize_float32`
    (D4). `INSERT OR REPLACE` is forbidden: on sqlite-vec 0.1.9 it raises
    `UNIQUE constraint failed on <table> primary key` for an id that is already present.
    A plain `UPDATE … SET embedding` is the permitted alternative only where the row is
    known to exist, which here it is not. Writes inside the caller's transaction.
    """
    key_column = _key_column(connection, table_name)
    # An unresolved key column means the table is absent, so the caller skipped the ensure:
    # the statement below then fails with SQLite's own `no such table`, which is the
    # truthful report. Nothing here ever creates a table.
    connection.execute(text(f"DELETE FROM {table_name} WHERE {key_column} = :row_id"), {"row_id": row_id})
    connection.execute(
        text(f"INSERT INTO {table_name}({key_column}, embedding) VALUES (:row_id, :embedding)"),
        {"row_id": row_id, "embedding": sqlite_vec.serialize_float32(list(vector))},
    )


def delete_vector(connection: Connection, table_name: str, row_id: int) -> None:
    """Remove `table_name`'s row for `row_id`, tolerating both kinds of absence.

    A **no-op** when no such row exists *and* when the table itself was never created —
    `DELETE FROM session_vec …` on a database without that table raises
    `no such table`, so existence is probed first. That second tolerance is load-bearing:
    an empty-text session (D6) and a blank-bodied memo (D7) resolve no model and so may
    reach this on a database that has no vector table at all.

    `table_name` is one of `app.db.search_tables`' two vector constants. Writes inside the
    caller's transaction.
    """
    opened_here = not connection.in_transaction()
    key_column = _key_column(connection, table_name)
    if key_column is None:
        # No such table: there is nothing to remove, and `DELETE` would raise
        # `no such table` rather than doing nothing. The key-column read autobegins, so a
        # transaction begun for it is ended again and this no-op really writes nothing.
        if opened_here and connection.in_transaction():
            connection.rollback()
        return
    # An absent row is `rowcount` 0 and no error, so no row-existence check is needed (D4).
    connection.execute(text(f"DELETE FROM {table_name} WHERE {key_column} = :row_id"), {"row_id": row_id})


# The table-valued pragma form accepts a **bound** parameter, which bare `PRAGMA` does not,
# and returns no row at all for a table that does not exist. One query therefore answers
# both "what is the key column called" and "does this table exist".
_KEY_COLUMN_SQL = text("SELECT name FROM pragma_table_info(:table_name) WHERE pk = 1")


def _key_column(connection: Connection, table_name: str) -> str | None:
    """The `vec0` table's declared key column, or `None` when the table does not exist.

    `rowid` is unusable on these tables: the DDL names the key column (`memo_id` /
    `session_id`), so every `rowid` spelling fails with `no such column`. The name is read
    back from the table rather than re-typed here, because `app.db.search_tables`' DDL owns
    both names.
    """
    row = connection.execute(_KEY_COLUMN_SQL, {"table_name": table_name}).first()
    return None if row is None else str(row[0])
