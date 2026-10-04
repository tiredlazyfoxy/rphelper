"""The vector arm: embed the query once, then rank the candidate set by L2 distance (`025`, step `003`).

One ranking, produced by one statement per call — the **exact scan**, the only form `003.context.md`
permits. For a vec table `V` whose declared key column is `C` (`memo_id` for the memo index,
`session_id` for the session index):

```sql
SELECT C
FROM V
WHERE C IN (<candidate ids>)
ORDER BY vec_distance_l2(embedding, :query_vector), C
LIMIT :depth
```

`:query_vector` is the embedded query serialised with `sqlite_vec.serialize_float32` (024 D4) and
bound as plain bytes; the extension itself is already loaded on every connection by
`app.db.engine`, so this module loads nothing. L2 rather than cosine follows 024's recorded form —
only the **rank** reaches fusion, so the metric's scale is irrelevant to RRF.

The scan is deliberate, not incidental. The vec0 nearest-neighbour form — the one that pushes a `k`
limit and an id restriction down into the virtual table — silently drops true candidates once ids
pass roughly 2^50, which every id in this product does (024 D3). This module therefore uses the
operator that triggers that path **nowhere**, not even in a comment, and a source scan asserts the
absence (DoD-11). Candidate sets here are hundreds of rows, the scan is exact, and it has no recall
parameter to tune. The candidate select is embedded as a subquery, so the relational filter runs
**before** ranking and never after it (D5, D6).

`rowid` is unusable on a vec0 table: the DDL names the key column, so every `rowid` spelling fails
with `no such column`. The key column is resolved from the table name instead.

Order of operations is fixed (U2, `003.context.md` "Ordering rationale"): the model is opened
**first**, so an instance with no designated model always raises even when its vec tables do not
exist yet — a search that quietly returned lexical-only results there would be the degrade R4 rules
out. The declared table dimension is read **second**: with a model but no table there is nothing to
compare against, so no provider call is spent. The table-versus-designation width check runs
**before** embedding, because `vec_distance_l2` on vectors of different widths raises a raw SQLite
error.

Errors propagate unchanged — no degrade to lexical-only, no substitution (U2, R4). An absent or
empty vec table is an empty result, not an error. The module creates no table, writes no row, and
imports nothing from the web framework (`embedding.py`'s phrasing, used so that DoD-11's source scan
cannot trip over this docstring).
"""

from collections.abc import Iterator
from contextlib import contextmanager

import sqlite_vec  # type: ignore[import-untyped]
from sqlalchemy import BigInteger, Connection, LargeBinary, Select, column, func, literal, select, table

from app.db.search_tables import MEMO_VEC_TABLE, SESSION_VEC_TABLE, vector_table_dimension
from app.errors import NoEmbeddingModelError
from app.services.embedding import DEFAULT_EMBED_TIMEOUT_SECONDS, embed_texts, open_embedding_model
from app.services.llm.client import LlmClient
from app.services.llm_registry import LlmClientFactory
from app.services.search.ports import ARM_DEPTH

_KEY_COLUMNS: dict[str, str] = {MEMO_VEC_TABLE: "memo_id", SESSION_VEC_TABLE: "session_id"}
"""Each `vec0` table's declared key column, keyed by 024's table constants.

Read from 024's DDL, which declares `memo_id` / `session_id` as the key: the name has to be
spelled in the statement because a `vec0` table has no `rowid` to fall back on.
"""

_DIMENSION_CONFLICT_MESSAGE = (
    "The embedding index was built for a different dimension; an administrator must rebuild it."
)
"""`NoEmbeddingModelError` declares no default message, so the raise site supplies one."""


@contextmanager
def _reading(connection: Connection) -> Iterator[None]:
    """A read on a Core connection autobegins; end it again when the caller had none open."""
    opened_here = not connection.in_transaction()
    try:
        yield
    finally:
        if opened_here and connection.in_transaction():
            connection.rollback()


def vector_ranking(
    connection: Connection,
    table_name: str,
    candidate_select: Select[tuple[int]],
    query_text: str,
    *,
    depth: int = ARM_DEPTH,
    client_factory: LlmClientFactory = LlmClient,
    timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS,
) -> list[int]:
    """Rank the candidate set by distance to the embedded query, nearest first, at most `depth` long.

    `table_name` is `MEMO_VEC_TABLE` (memo scope) or `SESSION_VEC_TABLE` (session scope), one of
    `app.db.search_tables`'s constants; `candidate_select` is `candidate_ids(scope)`, embedded as an
    `IN (…)` subquery so only candidates can be ranked (D5, D6); `query_text` is the raw query, which
    this arm embeds verbatim.

    Returns distinct ids ordered by ascending L2 distance with ties broken by ascending id — a
    ranking `rrf_fuse` consumes directly. A candidate with no vector row is simply not ranked, and
    that is not an error.

    In order:

    1. opens the designated model via `open_embedding_model(connection,
       client_factory=client_factory, timeout_seconds=timeout_seconds)`; its
       `NoEmbeddingModelError`, `SecretRefError` and `LlmUnreachableError` propagate unchanged (U2,
       R4);
    2. reads the table's declared dimension via `vector_table_dimension`; an **absent** table
       returns `[]` **without embedding** (U2);
    3. a declared dimension differing from the handle's `embedding_dim` raises
       `NoEmbeddingModelError` with a fixed message and `detail` exactly
       `{"reason": "dimension_mismatch"}`, **without embedding** (024 D8);
    4. embeds `query_text` with exactly **one** `embed_texts` call, carrying exactly that one text;
       its errors propagate;
    5. runs the exact scan above and returns the ids.

    Reads follow D7's posture: a read on a Core connection autobegins, so a transaction begun here
    is ended again when the caller had none open.
    """
    key_column = _KEY_COLUMNS[table_name]
    with _reading(connection):
        # (1) The model first, deliberately: an instance with no designated model raises here even
        # when its vec tables do not exist yet, so the arm can never quietly contribute nothing
        # where a model is missing. Every error comes out unchanged (U2, R4).
        handle = open_embedding_model(
            connection, client_factory=client_factory, timeout_seconds=timeout_seconds
        )
        # (2) The table second: with a model but no table there is nothing to rank, so the empty
        # ranking costs no provider call (U2). An empty-but-present table falls through to the
        # statement below, which simply returns no row.
        declared_dimension = vector_table_dimension(connection, table_name)
        if declared_dimension is None:
            return []
        # (3) The width guard runs **before** embedding: a distance over vectors of different
        # widths raises a raw SQLite error, and an index built at another width counts as an
        # unavailable model rather than a transport fault (024 D8).
        if declared_dimension != handle.embedding_dim:
            raise NoEmbeddingModelError(_DIMENSION_CONFLICT_MESSAGE, {"reason": "dimension_mismatch"})
        # (4) One call carrying exactly the one query text. Unpacking a single vector makes a
        # provider that answers the wrong count a `ValueError` rather than a silent miss (024 D1).
        (query_vector,) = embed_texts(handle, [query_text])
        # (5) The exact scan. The vec tables live outside `schema.metadata`, so the relation is a
        # lightweight `table()` / `column()` construct over the caller's name, and the key column
        # is named outright — a `vec0` table has no `rowid`.
        relation = table(table_name, column(key_column, BigInteger), column("embedding"))
        key = relation.c[key_column]
        # The serialised query vector is bound as raw bytes, which the distance function takes as
        # a parameter; the extension is already loaded on every connection by `app.db.engine`.
        query_blob = literal(sqlite_vec.serialize_float32(query_vector), LargeBinary)
        statement = (
            # The candidate set restricts the ranking inside the statement, never afterwards: the
            # relational filter runs first and nothing is dropped from the result later (D5, D6).
            select(key)
            .where(key.in_(candidate_select))
            # Nearest first; the key column breaks distance ties, so the ranking is deterministic.
            .order_by(func.vec_distance_l2(relation.c["embedding"], query_blob), key)
            .limit(depth)
        )
        return [int(row[0]) for row in connection.execute(statement).all()]
