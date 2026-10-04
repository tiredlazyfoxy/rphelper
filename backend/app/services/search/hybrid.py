"""The port's one entry point: arm selection, reciprocal-rank fusion, the limit, hydration (`025`, step `004`).

`search` is the single way anything in this product searches. It lives here and not in `ports.py`
on purpose: `ports.py` is the contract every other module of this package imports, so holding the
implementation there would make the contract import its own arms and close an import cycle. Callers
(`026`-`029`) import the scope variants and `SearchHit` from `ports.py` and `search` from this
module; swapping the backing store touches this module and the two arm modules, never a caller.

What a call does, in order (`context.md` U1-U3, D1-D7):

1. **Early exits** (D2) — a `limit` of zero or less, or a query that is empty or whitespace-only,
   returns `[]` with no model opened, no provider call and no statement issued against the search
   tables.
2. **Candidates once** (D5) — `candidate_ids(scope)` collapses the corpus to the owner's rows
   (D6) narrowed by the caller's optional extra predicate (U1), as a select both arms embed as a
   subquery. Filtering after ranking is forbidden.
3. **The variant's arms** (U1) — memo runs the vector arm over the memo vec index **and** the
   lexical arm over the memo FTS index; session runs the vector arm over the session vec index
   **only** (there is no session FTS index); entry runs the lexical arm over the message FTS index
   **only**, and therefore never opens the embedding model. Inside a memo search the **vector arm
   runs first**, so an instance with no designated model raises before any FTS work is spent
   (`004.context.md`). The vector arm's errors propagate unchanged - no degrade, no substitution
   (U2, R4). A `None` FTS expression or an absent table contributes an empty ranking, not an error.
4. **Fusion** (D1) — `rrf_fuse` over the rankings that ran, including the single ranking of a
   single-arm variant so `score` means one thing everywhere, then the first `limit` entries.
5. **Hydration** (D6, `004.context.md`) — one owner-scoped read per kind: a memo read for `scope`,
   `scope_id` and `body`; an entry read for `session_id` off the settled-entries relation (R11); no
   read at all for a session. A kept id absent from its hydration read is **dropped, not raised**.
6. **The hit** (D3, D4) — a memo snippet is the lexical arm's own `snippet()` text when the lexical
   arm found that id, kept by id from the arm's matches rather than re-queried, and otherwise the
   `leading_extract` of the memo's body. A session hit carries no snippet; an entry hit carries the
   FTS snippet and its session id.

**One `base_relation` call per statement, reused.** For the entry variant `base_relation` mints a
**fresh** subquery on every call, so a hydration statement that calls it twice - once for its
columns and once for its FROM - compiles an **extra FROM**, a silent cross join, rather than
raising. Every statement built here therefore binds one `base_relation` result to a local name and
uses that one object for its columns and its FROM alike.

Reads follow D7's posture: the autobegun read transaction is ended again when the caller had none
open, and the embed call happens inside that read window so no write lock is held. The module
creates no table and writes no row - it never calls 024's `ensure_*` functions - and it imports
nothing from the web framework and nothing from the vector extension (only the vector arm does).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Connection, Row, Select, select

from app.db.schema import memos
from app.db.search_tables import MEMO_FTS_TABLE, MEMO_VEC_TABLE, MESSAGE_FTS_TABLE, SESSION_VEC_TABLE
from app.services.embedding import DEFAULT_EMBED_TIMEOUT_SECONDS
from app.services.llm.client import LlmClient
from app.services.llm_registry import LlmClientFactory
from app.services.search.candidates import base_relation, candidate_ids
from app.services.search.lexical import lexical_ranking
from app.services.search.ports import (
    EntrySearchScope,
    MemoSearchScope,
    SearchHit,
    SearchScope,
    SessionSearchScope,
    build_fts_query,
    leading_extract,
    rrf_fuse,
)
from app.services.search.vector import vector_ranking


@contextmanager
def _reading(connection: Connection) -> Iterator[None]:
    """A read on a Core connection autobegins; end it again when the caller had none open."""
    opened_here = not connection.in_transaction()
    try:
        yield
    finally:
        if opened_here and connection.in_transaction():
            connection.rollback()


def search(
    connection: Connection,
    scope: SearchScope,
    query_text: str,
    limit: int,
    *,
    client_factory: LlmClientFactory = LlmClient,
    timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS,
) -> list[SearchHit]:
    """Search one corpus and return at most `limit` fused hits, best first (U1, D1-D7).

    `scope` is one of the three variants of `SearchScope` and fixes both the corpus and which arms
    run (U1); it always carries the owner, and the owner predicate is applied by this port rather
    than by the caller (D6, R5, UC-065, US-085). `query_text` is the raw user text: the vector arm
    embeds it verbatim and the lexical arm consumes `build_fts_query`'s sanitised form of it.
    `limit` is the **final** result count, not a per-arm depth - each arm contributes at most
    `ARM_DEPTH` ids regardless (D1). `client_factory` and `timeout_seconds` reach
    `open_embedding_model` unchanged and are only ever used by a variant whose vector arm runs
    (U2, 024 D9).

    Returns hits ordered by descending fused score with ties broken by **ascending id**, so the
    order is deterministic. Returns `[]` for a `limit` of zero or less and for an empty or
    whitespace-only query, without opening the model or issuing any search-table statement (D2),
    and `[]` when the variant's tables are absent or nothing matched (U2).

    Raises whatever the vector arm raises, unchanged: `NoEmbeddingModelError` when no model is
    designated or the index width differs, `SecretRefError`, and `LlmUnreachableError` (U2, R4). A
    variant with no vector arm raises none of them, because it never opens the model.
    """
    # (1) D2's early exits come before everything: no model is opened, no provider call is made
    # and no statement is issued against a search table — not even a candidate select is built.
    if limit <= 0 or not query_text.strip():
        return []
    # (2) The candidate set, built exactly **once** and embedded by both arms as a subquery, so the
    # relational filter runs before ranking and never after it (D5, D6).
    candidates = candidate_ids(scope)
    with _reading(connection):
        # (3) The arms this variant fixes (U1), vector first for a memo search (`004.context.md`).
        rankings, lexical_snippets = _run_arms(
            connection,
            scope,
            candidates,
            query_text,
            client_factory=client_factory,
            timeout_seconds=timeout_seconds,
        )
        # (4) One fusion over whatever ran — a single-arm variant included, so `score` means the
        # same thing everywhere — then the caller's limit, applied after fusion and never before.
        fused = rrf_fuse(rankings)[:limit]
        if not fused:
            # Nothing matched, so there is nothing to hydrate: no further statement is issued.
            return []
        # (5) and (6): one owner-scoped read per kind, then the D3 / D4 hit.
        if isinstance(scope, MemoSearchScope):
            return _memo_hits(connection, scope, fused, lexical_snippets)
        if isinstance(scope, SessionSearchScope):
            return _session_hits(fused)
        return _entry_hits(connection, scope, fused, lexical_snippets)


def _run_arms(
    connection: Connection,
    scope: SearchScope,
    candidates: Select[tuple[int]],
    query_text: str,
    *,
    client_factory: LlmClientFactory,
    timeout_seconds: float,
) -> tuple[list[list[int]], dict[int, str]]:
    """Run the arms `scope`'s variant fixes, as id rankings plus the lexical arm's snippets (U1).

    The second element maps an id to the `snippet()` text the lexical arm already produced for it,
    so hydration spends no second FTS query (`004.context.md`); it is empty for a variant with no
    lexical arm. An arm that found nothing — a `None` FTS expression, an absent table, an empty
    index — contributes an empty ranking rather than an error (U2), and fusion ignores it.
    """
    if isinstance(scope, MemoSearchScope):
        # The **vector arm first**: an instance with no designated model therefore raises before any
        # FTS work is spent, even when the memo FTS index holds a match (`004.context.md`, U2, R4).
        vector_ids = vector_ranking(
            connection,
            MEMO_VEC_TABLE,
            candidates,
            query_text,
            client_factory=client_factory,
            timeout_seconds=timeout_seconds,
        )
        matches = lexical_ranking(connection, MEMO_FTS_TABLE, candidates, build_fts_query(query_text))
        snippets = {match.id: match.snippet for match in matches}
        return [vector_ids, [match.id for match in matches]], snippets
    if isinstance(scope, SessionSearchScope):
        # Vector only: there is no session FTS index, so no FTS table is consulted at all (U1).
        vector_ids = vector_ranking(
            connection,
            SESSION_VEC_TABLE,
            candidates,
            query_text,
            client_factory=client_factory,
            timeout_seconds=timeout_seconds,
        )
        return [vector_ids], {}
    # The entry variant: lexical only, so the embedding model is never opened and the client factory
    # is never called, whatever the registry holds (U1, U2).
    matches = lexical_ranking(connection, MESSAGE_FTS_TABLE, candidates, build_fts_query(query_text))
    return [[match.id for match in matches]], {match.id: match.snippet for match in matches}


def _memo_hits(
    connection: Connection,
    scope: MemoSearchScope,
    fused: list[tuple[int, float]],
    lexical_snippets: dict[int, str],
) -> list[SearchHit]:
    """Hydrate the kept memo ids in **one** owner-scoped read and build their hits (D3, D4, D6).

    The one statement reads `scope`, `scope_id` and `body` for every kept id at once: `body` is
    needed only by the ids the lexical arm did not find, but reading it for all of them keeps the
    read count at one. A kept id the read does not return is **dropped, not raised**. The snippet is
    the lexical arm's own text when that arm found the id and the `leading_extract` of the body
    otherwise (D4), and the level is `scope` plus the stored `scope_id` with no name join (U3). A
    memo hit carries no title, ever (US-119).
    """
    kept = [memo_id for memo_id, _ in fused]
    rows: dict[int, Row[Any]] = {
        row.id: row
        for row in connection.execute(
            select(memos.c.id, memos.c.scope, memos.c.scope_id, memos.c.body).where(
                memos.c.user_id == scope.user_id, memos.c.id.in_(kept)
            )
        ).all()
    }
    hits: list[SearchHit] = []
    for memo_id, score in fused:
        row = rows.get(memo_id)
        if row is None:
            continue
        snippet = lexical_snippets.get(memo_id)
        hits.append(
            SearchHit(
                kind="memo",
                id=memo_id,
                score=score,
                snippet=snippet if snippet is not None else leading_extract(row.body),
                memo_scope=row.scope,
                memo_scope_id=row.scope_id,
            )
        )
    return hits


def _session_hits(fused: list[tuple[int, float]]) -> list[SearchHit]:
    """Build the session hits — id and score alone, with **no** read at all (D3, `004.context.md`).

    `sessions` has no text column, so a session hit carries no snippet, no memo level and no
    `session_id`; the ids come from a candidate select that was already owner-scoped (D6), so there
    is nothing left to hydrate and no second statement to issue.
    """
    return [SearchHit(kind="session", id=session_id, score=score) for session_id, score in fused]


def _entry_hits(
    connection: Connection,
    scope: EntrySearchScope,
    fused: list[tuple[int, float]],
    lexical_snippets: dict[int, str],
) -> list[SearchHit]:
    """Hydrate the kept entries' session ids in **one** owner-scoped read and build their hits (D3).

    The read goes through the settled-entries relation and never through raw `messages` (R11, D6).
    **One** `base_relation` call: its result is bound here and used for the projection, the owner
    predicate and the FROM alike, because a second call would mint a second subquery and splice a
    silent extra FROM into the statement instead of failing. A kept id the read does not return is
    dropped, not raised. The snippet is the lexical arm's text — the only arm an entry search runs.
    """
    kept = [entry_id for entry_id, _ in fused]
    # Called **once**, and this one object is the statement's columns *and* its FROM.
    relation = base_relation(scope)
    session_ids: dict[int, int] = {
        row.id: row.session_id
        for row in connection.execute(
            select(relation.c["id"], relation.c["session_id"]).where(
                relation.c["user_id"] == scope.user_id, relation.c["id"].in_(kept)
            )
        ).all()
    }
    hits: list[SearchHit] = []
    for entry_id, score in fused:
        session_id = session_ids.get(entry_id)
        if session_id is None:
            continue
        hits.append(
            SearchHit(
                kind="entry",
                id=entry_id,
                score=score,
                snippet=lexical_snippets.get(entry_id),
                session_id=session_id,
            )
        )
    return hits
