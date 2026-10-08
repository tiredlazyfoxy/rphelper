"""The lexical arm: BM25 ranking plus a plain-text snippet over an FTS5 table (`025`, step `002`).

One ranking, produced by one statement per call, shaped by `002.context.md`:

```sql
SELECT rowid, snippet(T, 0, '', '', '…', 16)
FROM T
WHERE T MATCH :fts_expr AND rowid IN (<candidate ids>)
ORDER BY bm25(T), rowid
LIMIT :depth
```

`T` is `memo_fts` (memo scope) or `message_fts` (entry scope) — there is no `session_fts`. Both
are external-content indexes keyed on `id`, so the FTS `rowid` **is** the `memos.id` /
`messages.id` the hit carries. `bm25()` is lower-is-better, hence the ascending order, and the
`rowid` tiebreak makes the ranking deterministic. The candidate select is embedded as a subquery,
never applied afterwards (D5).

Two absences are empty results rather than errors (U2): a **none** FTS expression (an empty
`MATCH` is an FTS5 syntax error, so the short-circuit is load-bearing, not tidiness) and an
**absent** FTS table (a pre-024 database has none until a qualifying write or the rebuild). In
both cases the FTS table is not queried at all.

The table is always named through the **caller's** `table_name` argument — one of
`app.db.search_tables`'s constants — and never as a string literal in this module. The module
imports no `fastapi` and creates no table.
"""

from dataclasses import dataclass
from typing import Final

from sqlalchemy import (
    ColumnClause,
    Connection,
    Integer,
    Select,
    column,
    func,
    literal_column,
    select,
    table,
    text,
)

from app.services.search.ports import ARM_DEPTH

SNIPPET_TOKENS: Final[int] = 16
"""How many tokens FTS5's `snippet()` may return. Conventional and unmeasured, like D1's numbers."""


@dataclass(frozen=True)
class LexicalMatch:
    """One row of the lexical ranking: which row matched, and the snippet FTS5 cut from it."""

    id: int
    """The base relation's id — the FTS `rowid`, i.e. the memo id or the message id."""
    snippet: str
    """`snippet()`'s plain text: no highlight markup, `…` where it was cut (D4)."""


def fts_table_exists(connection: Connection, table_name: str) -> bool:
    """Answer whether an FTS5 table of that name exists (U2).

    `table_name` is one of `app.db.search_tables`'s FTS constants. Read from `sqlite_master`
    (`type = 'table'`, by name), because 024 exposes no public FTS existence helper — only
    `vector_table_dimension`, which covers the vec tables. Writes nothing and creates nothing.
    """
    present = connection.execute(
        text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name LIMIT 1"),
        {"name": table_name},
    ).first()
    return present is not None


def lexical_ranking(
    connection: Connection,
    table_name: str,
    candidate_select: Select[tuple[int]],
    fts_expression: str | None,
    *,
    depth: int = ARM_DEPTH,
) -> list[LexicalMatch]:
    """Rank the candidate set by BM25 over `table_name`, best first, at most `depth` long.

    `table_name` is `MEMO_FTS_TABLE` (memo scope) or `MESSAGE_FTS_TABLE` (entry scope);
    `candidate_select` is `candidate_ids(scope)`, embedded as an `IN (…)` subquery so only
    candidates can be ranked (D5, D6); `fts_expression` is `build_fts_query`'s sanitised output.

    Returns the matching rows ordered by ascending `bm25()` (lower is better) and then by ascending
    id, each with its `snippet()` text. Returns `[]` **without querying the FTS table** when
    `fts_expression` is `None` or the table does not exist (U2) — neither is an error.
    """
    # Both absences short-circuit before any statement reaches the FTS table: an empty `MATCH` is
    # an FTS5 syntax error, and a pre-024 database simply has no such table (U2).
    if fts_expression is None or not fts_table_exists(connection, table_name):
        return []

    # The FTS tables live outside `schema.metadata`, so the relation is a lightweight
    # `table()` / `column()` construct over the caller's name; `fts_name` is the bare table name,
    # which is what both `MATCH` and the auxiliary functions take on their left / first position.
    relation = table(table_name, column("rowid", Integer))
    fts_name: ColumnClause[str] = literal_column(table_name)
    row_id = relation.c["rowid"]
    statement = (
        # Column 0, empty start / end markers (plain text, no highlight markup), `…`, 16 tokens.
        select(row_id, func.snippet(fts_name, 0, "", "", "…", SNIPPET_TOKENS))
        # The candidate set restricts the ranking inside the statement, never afterwards (D5, D6).
        .where(fts_name.match(fts_expression), row_id.in_(candidate_select))
        # `bm25()` is lower-is-better, so ascending is best first; the id breaks ties.
        .order_by(func.bm25(fts_name), row_id)
        .limit(depth)
    )
    return [LexicalMatch(id=row[0], snippet=row[1]) for row in connection.execute(statement).all()]
