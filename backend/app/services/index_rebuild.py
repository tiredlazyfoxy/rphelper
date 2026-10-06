"""The administrator's index rebuild — FEAT-005, UC-016, US-019.AC-1 (feature `fast/002`).

One all-or-nothing transaction: validate the embedding designation, drop and re-declare
both `vec0` tables at the designated dimension, re-embed every memo and every session of
every user, rebuild both FTS5 indexes, and report the fixed list of derived tables rebuilt.
The report never carries a count or any text derived from user content (UC-066, R5).
"""

from collections.abc import Sequence

from sqlalchemy import Connection, select

from app.db.schema import memos, sessions
from app.db.search_tables import (
    MEMO_VEC_TABLE,
    SESSION_VEC_TABLE,
    drop_vector_tables,
    ensure_vector_tables,
    rebuild_fts_indexes,
)
from app.models.admin_db import RebuildReportResponse
from app.services.embedding import embed_texts, open_embedding_model, write_vector
from app.services.llm_registry import LlmClientFactory
from app.services.session_index import compose_session_text

#: Maximum number of texts sent in one `embed_texts` call; each chunk uses a fresh handle.
#: Deliberately not `Final`: tests monkeypatch it, so it is read at call time.
REBUILD_EMBED_BATCH_SIZE: int = 32


def rebuild_index(
    connection: Connection,
    *,
    client_factory: LlmClientFactory,
    timeout_seconds: float,
) -> RebuildReportResponse:
    """Drop and re-derive `memo_vec`, `session_vec`, `memo_fts` and `message_fts` in one transaction.

    Opens its own `with connection.begin():` block. Raises `NoEmbeddingModelError` when no
    embedding model is designated; every raised error (unreachable server, dimension
    mismatch, secret-ref failure) propagates unchanged and rolls the whole transaction back.
    Returns the report naming the four derived tables, always the same four in that order.
    """
    with connection.begin():
        # Validates the designation and learns its dimension; no network call happens here.
        handle = open_embedding_model(connection, client_factory=client_factory, timeout_seconds=timeout_seconds)
        drop_vector_tables(connection)
        ensure_vector_tables(connection, handle.embedding_dim)

        # Mirrors the memo write path: a blank body has no vector.
        memo_rows = [
            (row.id, row.body)
            for row in connection.execute(select(memos.c.id, memos.c.body).order_by(memos.c.id))
            if row.body.strip()
        ]
        _embed_and_write(connection, MEMO_VEC_TABLE, memo_rows, client_factory, timeout_seconds)

        session_rows: list[tuple[int, str]] = []
        for row in connection.execute(select(sessions.c.id, sessions.c.user_id).order_by(sessions.c.id)).all():
            composed = compose_session_text(connection, row.user_id, row.id)
            if composed:
                session_rows.append((row.id, composed))
        _embed_and_write(connection, SESSION_VEC_TABLE, session_rows, client_factory, timeout_seconds)

        rebuild_fts_indexes(connection)
    return RebuildReportResponse(tables_rebuilt=["memo_vec", "session_vec", "memo_fts", "message_fts"])


def _embed_and_write(
    connection: Connection,
    table_name: str,
    rows: Sequence[tuple[int, str]],
    client_factory: LlmClientFactory,
    timeout_seconds: float,
) -> None:
    """Embed `rows`' texts in chunks of `REBUILD_EMBED_BATCH_SIZE` and write each vector by id."""
    batch_size = REBUILD_EMBED_BATCH_SIZE
    for start in range(0, len(rows), batch_size):
        chunk = rows[start : start + batch_size]
        # A handle is single-use across `embed_texts` calls, so each chunk opens a fresh one.
        handle = open_embedding_model(connection, client_factory=client_factory, timeout_seconds=timeout_seconds)
        vectors = embed_texts(handle, [body for _, body in chunk])
        # `strict` turns a provider answering the wrong count into a `ValueError`, not a silent miss.
        for (row_id, _), vector in zip(chunk, vectors, strict=True):
            write_vector(connection, table_name, row_id, vector)
