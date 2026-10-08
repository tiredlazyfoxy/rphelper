"""The search port's contract — the scope variants, the hit value and the pure helpers.

Feature `025`, step `001`. This module is the shape of hybrid search and nothing else:

- **The three constants** (`RRF_K`, `ARM_DEPTH`, `SNIPPET_CHARS`) — the conventional,
  unmeasured numbers fusion and snippets are tuned by (`context.md` D1).
- **The three scope variants** and their `SearchScope` union — one per indexed corpus, each
  carrying the owner it is scoped to and an optional caller predicate over its base
  relation (U1).
- **`SearchHit`** — the one result shape, the same value whichever arm found the row (D3).
- **`rrf_fuse`**, **`build_fts_query`** and **`leading_extract`** — the three pure helpers
  the arms and the entry point share (D1, D4, `001.context.md`).

**Pure by contract.** No connection is taken, no SQL is executed, no row is read: SQLAlchemy
appears here only as the *types* the extra-predicate builder is expressed in. The module
imports no `fastapi`, no `sqlite_vec` and nothing from `app.db.engine`, so it can be
imported and exercised without a database or a web application.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final, Literal

from sqlalchemy import ColumnElement, FromClause

from app.models.memos import MemoScope

RRF_K: Final[int] = 60
"""Reciprocal-rank fusion's rank offset: a hit at 1-based `rank` scores `1 / (k + rank)` (D1)."""

ARM_DEPTH: Final[int] = 50
"""How many ids one arm contributes at most. The final result count is the caller's `limit` (D1)."""

SNIPPET_CHARS: Final[int] = 160
"""The snippet budget in characters, for the FTS5 snippet and for `leading_extract` alike (D1, D4)."""

#: The three corpora a hit can come from — one value per scope variant (D3).
SearchKind = Literal["memo", "session", "entry"]

#: A caller-supplied extra predicate, as a builder over the FROM object the port uses (U1).
#:
#: The port calls it with the base relation it selects candidates from and ANDs the returned
#: clause with its own owner predicate; the caller therefore never names a table itself.
ExtraPredicateBuilder = Callable[[FromClause], ColumnElement[bool]]


@dataclass(frozen=True)
class MemoSearchScope:
    """Search the owner's memos: the vector arm over `memo_vec`, the lexical arm over `memo_fts` (U1)."""

    user_id: int
    """The owner. Required and defaultless — the port applies `memos.user_id = :user_id` itself (D6)."""
    extra_predicate: ExtraPredicateBuilder | None = None
    """An optional further narrowing over `memos`, ANDed with the owner predicate (U1)."""


@dataclass(frozen=True)
class SessionSearchScope:
    """Search the owner's sessions: the vector arm over `session_vec` only — there is no `session_fts` (U1)."""

    user_id: int
    """The owner. Required and defaultless — the port applies `sessions.user_id = :user_id` itself (D6)."""
    extra_predicate: ExtraPredicateBuilder | None = None
    """An optional further narrowing over `sessions`, ANDed with the owner predicate (U1)."""


@dataclass(frozen=True)
class EntrySearchScope:
    """Search the owner's settled entries: the lexical arm over `message_fts` only (U1, R11)."""

    user_id: int
    """The owner. Required and defaultless — the port applies the view's `user_id = :user_id` itself (D6)."""
    extra_predicate: ExtraPredicateBuilder | None = None
    """An optional further narrowing over the `settled_entries` FROM object (U1)."""


#: The scope argument `search` accepts — exactly one corpus per call; fusion never crosses kinds (D1).
SearchScope = MemoSearchScope | SessionSearchScope | EntrySearchScope


@dataclass(frozen=True)
class SearchHit:
    """One fused result. Which optional fields are set follows from `kind` alone (D3).

    A memo hit carries a snippet and its level (`memo_scope`, `memo_scope_id`) and **never a
    title** (US-119). A session hit carries neither snippet nor level, because `sessions` has
    no text column. An entry hit carries a snippet and its `session_id`.
    """

    kind: SearchKind
    """Which corpus the row came from."""
    id: int
    """The row's own snowflake id: the memo id, the session id, or the message id."""
    score: float
    """The fused reciprocal-rank score (D1). Comparable only within one result list."""
    snippet: str | None = None
    """Plain text, no highlight markup; `None` for a session hit (D3, D4)."""
    memo_scope: MemoScope | None = None
    """A memo hit's level, as the scope literal alone — no name join (U3). `None` otherwise."""
    memo_scope_id: int | None = None
    """A memo hit's level target id, `None` for the `"user"` level and for non-memo hits (U3)."""
    session_id: int | None = None
    """An entry hit's owning session id. `None` for memo and session hits (D3)."""


def rrf_fuse(rankings: Sequence[Sequence[int]], *, k: int = RRF_K) -> list[tuple[int, float]]:
    """Fuse per-arm rankings into one ordered `(id, score)` list by reciprocal rank (D1).

    Each ranking is an ordered sequence of distinct ids, best first. An id's score is the sum
    of `1 / (k + rank)` over every ranking it appears in, with `rank` 1-based. The result
    covers every id appearing in any ranking, ordered by score descending and then by id
    ascending so ties are deterministic. No rankings, or only empty rankings, gives `[]`.
    """
    scores: dict[int, float] = {}
    for ranking in rankings:
        for index, row_id in enumerate(ranking):
            scores[row_id] = scores.get(row_id, 0.0) + 1.0 / (k + index + 1)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


def build_fts_query(query: str) -> str | None:
    """Turn raw user text into an FTS5 `MATCH` expression that cannot be a syntax error.

    Follows `001.context.md`'s numbered rules: split on whitespace runs, strip every `"` from
    each token, drop tokens left empty, quote each survivor as an FTS5 string and join with
    `" OR "`. Returns `None` when no usable token remains — the caller then skips the lexical
    arm rather than passing an empty expression to `MATCH`.
    """
    phrases: list[str] = []
    for token in query.split():
        bare = token.replace('"', "")
        if not bare:
            continue
        phrases.append(f'"{bare}"')
    if not phrases:
        return None
    return " OR ".join(phrases)


def leading_extract(body: str) -> str:
    """Return `body`'s leading extract: the memo snippet for a vector-only hit (D4).

    Collapses every whitespace run to one space and strips both ends. A result longer than
    `SNIPPET_CHARS` characters is cut to its first `SNIPPET_CHARS` characters with `…`
    (U+2026, one character) appended; a shorter result is returned as is.
    """
    collapsed = " ".join(body.split())
    if len(collapsed) > SNIPPET_CHARS:
        return f"{collapsed[:SNIPPET_CHARS]}…"
    return collapsed
