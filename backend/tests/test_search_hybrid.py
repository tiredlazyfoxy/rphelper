"""End-to-end tests for the `search` entry point — feature 025, step 004 (DoD-1..15).

Every expected value comes from the **spec**, never from the implementation:
`docs/plans/025.hybrid-search-port/004.search-entry-point.md` (Interface intent and Definition
of done), `004.context.md` (the hydration reads, the arm order, the "Test shape" note) and the
feature `context.md` — **U1** (the variant → arms table and the caller's extra predicate),
**U2** (the model's errors propagate; an absent vec/FTS table is empty, not an error; the model
is opened only when the vector arm runs), **U3** / **D3** (the hit shape — a memo hit has **no
title, ever**, US-119), **D1** (RRF with `k = 60`, ties by ascending id, `limit` is the final
count), **D2** (early exits), **D4** (a memo snippet's two shapes), **D6** (owner scope, tested
as an absence) and the Test conventions.

How the expectations are derived (`004.context.md` "Test shape")
---------------------------------------------------------------
Nothing here asks the code under test what the answer is.

* **The vector arm's ranking** is recomputed by the test: every stored vector is
  `llm_fakes.embedding_vector(<source text>, 8)`, a **pure** function of `(text, dim)`, so the
  test brute-forces the order with a plain-Python L2 (`math.dist`), ties by ascending id, and
  cuts at `ARM_DEPTH`. The comparison needs no tolerance: components are multiples of `2 ** -8`
  inside `(-1, 1)`, so every squared difference is a multiple of `2 ** -16` and the 8-term sum
  is an exact float32 value (`llm_fakes.py`'s documented contract). A row whose source text *is*
  the query text therefore stores the query vector exactly — distance 0, the device the
  owner-isolation and extra-predicate tests use.
* **The lexical arm's membership** is "which bodies contain the token". Where BM25's exact order
  would be ambiguous the test seeds exactly one match, or uses the one ordering BM25's
  *definition* fixes (a term twice in a three-token body beats once in a 49-token body, as step
  002's tests do). **BM25 magnitudes are never asserted, only order.**
* **The fused score** is D1's formula, implemented locally in `_rrf_fuse` below from the plan's
  words (`Σ 1 / (k + rank)`, `rank` 1-based, `k = 60`, ties by ascending id) rather than imported
  from `ports`, so the expectation stands on the spec alone.
* **The leading extract** is D4's rule, implemented locally in `_leading_extract`.
* `RRF_K` (60), `ARM_DEPTH` (50) and `SNIPPET_CHARS` (160) are written out here as the spec's
  numbers (D1); step 001's DoD-9 is what pins the module constants to them.

Bindings come from `## Skeleton` → "Step 004 — frozen interface" in `status.md`:
`search(connection, scope, query_text, limit, *, client_factory=LlmClient,
timeout_seconds=DEFAULT_EMBED_TIMEOUT_SECONDS) -> list[SearchHit]` — `limit` is
**positional-or-keyword and defaultless**; `client_factory` is keyword-only. `SearchHit`'s seven
fields and the three scope variants come from step 001's record.

Each test name ends `__S025_004_DoD<n>` with the DoD item it covers.

Mechanics (`context.md` "Test conventions"):
- a real SQLite file per test via the shared `db_engine` fixture, with
  `schema.metadata.create_all`; **`tests/conftest.py` and `tests/llm_fakes.py` are untouched**
  and every other fixture and helper here is file-local;
- every row is a **raw insert** with an id **above 2^60**, and **two users** are always present
  so owner isolation is observable as an absence;
- the four virtual tables are created only through 024's `ensure_fts_tables` /
  `ensure_vector_tables`, written only through 024's `write_vector`, and named only through
  024's constants;
- a designated model is a raw `llm_servers` + `models` pair with `is_enabled`,
  `is_embedding_designated` and `embedding_dim` (8), and `api_key_ref=None`, so no environment
  variable is involved;
- the provider arrives through the frozen `client_factory=` seam. **No monkeypatching**, no
  network.
"""

import ast
import dataclasses
import math
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from sqlalchemy import ColumnElement, Engine, FromClause, Table, text

import app.services.search as search_package
from app.db import schema
from app.db.search_tables import (
    MEMO_FTS_TABLE,
    MEMO_VEC_TABLE,
    MESSAGE_FTS_TABLE,
    SESSION_VEC_TABLE,
    ensure_fts_tables,
    ensure_vector_tables,
)
from app.errors import LlmUnreachableError, NoEmbeddingModelError
from app.roles import Role
from app.services.embedding import write_vector
from app.services.search.hybrid import search
from app.services.search.ports import (
    EntrySearchScope,
    ExtraPredicateBuilder,
    MemoSearchScope,
    SearchHit,
    SearchScope,
    SessionSearchScope,
)
from tests.llm_fakes import FakeClientFactory, embedding_vector, fake_factory, unreachable_factory

#: The seeded instant, in the project's fixed-width UTC text form.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

#: The instant a record row carries in `settled_at` (non-null ⇒ it is in `settled_entries`).
SETTLED_AT = "2026-01-01T00:10:00.000000+00:00"

#: Every id below is above 2^60 = 1152921504606846976 (snowflake-sized, 024 D3).
SNOWFLAKE_FLOOR = 2**60

#: The designated embedding width throughout; 8 keeps the tests fast (`context.md`).
DIMENSION = 8

#: D1's three numbers, written out as the **spec's** values (step 001 DoD-9 pins the constants).
RRF_K = 60
ARM_DEPTH = 50
SNIPPET_CHARS = 160

USER_A = 1_500_000_000_000_000_001
USER_B = 1_500_000_000_000_000_002

CHARACTER_A1 = 1_500_000_000_000_000_101
CHARACTER_A2 = 1_500_000_000_000_000_102
CHARACTER_B1 = 1_500_000_000_000_000_103

SESSION_A1 = 1_500_000_000_000_000_201
SESSION_A2 = 1_500_000_000_000_000_202
SESSION_B1 = 1_500_000_000_000_000_203
#: A second `USER_A` session under **`CHARACTER_A1`**, so DoD-8's `character_id = :c AND
#: id != :current` predicate has something left to find once the "current" session is excluded.
SESSION_A3 = 1_500_000_000_000_000_204

SERVER_ID = 1_500_000_000_000_000_901
MODEL_ID = 1_500_000_000_000_000_902

BASE_URL = "http://embedding.test:8080/v1"
MODEL_NAME = "the-designated-embedding-model"

#: The searched term. Lower case, so FTS5's verbatim snippet text contains it as-is.
TOKEN = "kaelith"

#: DoD-2's rare term — present in exactly one body in the whole 60-memo corpus.
RARE_TOKEN = "zephyrine"

#: DoD-12: a query of punctuation only. Rule 2 of `001.context.md` strips every `"` from the one
#: token, rule 3 drops it as empty and rule 6 returns **none** — so the lexical arm contributes
#: nothing, and `MATCH ''` (which raises) is never issued.
PUNCTUATION_QUERY = '"""'

#: DoD-1 / DoD-14: four of one user's memos, all vectored, exactly **one** body holding the token
#: so the lexical ranking is unambiguously `[MEMO_TWO]` (rank 1).
MEMO_ONE = 1_500_000_000_000_000_301
MEMO_TWO = 1_500_000_000_000_000_302
MEMO_THREE = 1_500_000_000_000_000_303
MEMO_FOUR = 1_500_000_000_000_000_304

HYBRID_BODIES: Mapping[int, str] = {
    MEMO_ONE: "the lantern over the harbour at dusk",
    MEMO_TWO: f"a ledger naming {TOKEN} among the debtors",
    MEMO_THREE: "rain against the shutters all night",
    MEMO_FOUR: "the long road inland past the mill",
}

#: The source texts the stored vectors are derived from — all distinct, so all distances differ.
HYBRID_SOURCES: Mapping[int, str] = {
    MEMO_ONE: "stored vector source for the harbour memo",
    MEMO_TWO: "stored vector source for the ledger memo",
    MEMO_THREE: "stored vector source for the shutters memo",
    MEMO_FOUR: "stored vector source for the inland memo",
}

#: DoD-3: one lexically found memo and one the vector arm alone can reach.
MEMO_LEXICAL = 1_500_000_000_000_000_311
MEMO_VECTOR_ONLY = 1_500_000_000_000_000_312

#: DoD-4: the two memo levels (U3 — `scope` + `scope_id`, never a name).
MEMO_USER_LEVEL = 1_500_000_000_000_000_321
MEMO_SESSION_LEVEL = 1_500_000_000_000_000_322

#: DoD-7: the other owner's memo, matching on **both** arms.
MEMO_B_MATCHING = 1_500_000_000_000_000_331

#: DoD-8: the extra predicate's three memos — one kept, one disabled, one forced.
MEMO_PLAIN = 1_500_000_000_000_000_341
MEMO_DISABLED = 1_500_000_000_000_000_342
MEMO_FORCED = 1_500_000_000_000_000_343

#: DoD-13: the long-body match has the **lower** id and the short-body match the higher one, so
#: an ordering produced by id instead of BM25 would come out reversed (step 002's device).
MEMO_LONG = 1_500_000_000_000_000_351
MEMO_SHORT = 1_500_000_000_000_000_352

MESSAGE_A1 = 1_500_000_000_000_000_401
MESSAGE_A2 = 1_500_000_000_000_000_402
MESSAGE_B1 = 1_500_000_000_000_000_403
MESSAGE_A_ZONE = 1_500_000_000_000_000_404
MESSAGE_A_BURIED = 1_500_000_000_000_000_405

#: The token twice in a three-token body: the stronger BM25 match **by BM25's definition**.
SHORT_TOKEN_BODY = f"{TOKEN} greets {TOKEN}"

#: The token once in a 49-token body: the weaker match, and long enough that FTS5 truncates its
#: snippet with the ellipsis (harvest D13).
LONG_TOKEN_BODY = f"{TOKEN} " + " ".join(["filler"] * 48)

#: A body the token cannot match.
BODY_WITHOUT_TOKEN = "the quiet river at dusk"

#: DoD-3: messy whitespace **and** longer than `SNIPPET_CHARS` once collapsed, so the leading
#: extract must both collapse and truncate (D4).
VECTOR_ONLY_BODY = "  the   wandering\tlight\n\nover the salt flats " + "and the long slow dusk beyond the ridge " * 5

#: The ellipsis both D4's leading extract and FTS5's `snippet()` append (U+2026, one character).
ELLIPSIS = "…"

#: DoD-2. **60 memos > `ARM_DEPTH` (50).** The 59 filler vectors are chosen (inside the test) as
#: the pool texts **nearest** the query vector and the target's as the **farthest**, so the
#: target's vector rank is 60 — outside the arm — **by construction**, not by luck.
RESCUE_BASE = 1_500_000_000_000_000_601
RESCUE_FILLER_COUNT = 59
RESCUE_MEMO_COUNT = RESCUE_FILLER_COUNT + 1
RESCUE_FILLER_IDS = tuple(RESCUE_BASE + offset for offset in range(RESCUE_FILLER_COUNT))
#: Deliberately the **largest** id in the corpus, so even an exact distance tie leaves it last.
RESCUE_TARGET = RESCUE_BASE + 500
RESCUE_POOL = tuple(f"rescue pool vector source text number {index}" for index in range(300))
RESCUE_LIMIT = 10

#: The six modules `context.md` "Files this feature touches" lists (DoD-15).
SEARCH_PACKAGE_MODULES = ("__init__.py", "ports.py", "candidates.py", "lexical.py", "vector.py", "hybrid.py")

#: D3's hit shape, exactly — step 001's frozen field list. No title, ever (US-119).
EXPECTED_HIT_FIELDS = frozenset(
    {"kind", "id", "score", "snippet", "memo_scope", "memo_scope_id", "session_id"}
)


# --- the expectations, computed from the spec and from the fake's pure function -------------


def _rrf_fuse(rankings: Sequence[Sequence[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """D1's reciprocal-rank fusion, implemented from the plan's words.

    `Σ 1 / (k + rank)` over the arms that ran, `rank` 1-based, best first, **ties broken by
    ascending id**. Deliberately local: the expectation must not come from `ports.rrf_fuse`.
    """
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, row_id in enumerate(ranking, start=1):
            scores[row_id] = scores.get(row_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


def _leading_extract(body: str) -> str:
    """D4's rule, implemented locally: collapse every whitespace run, strip, truncate at 160."""
    collapsed = " ".join(body.split())
    if len(collapsed) > SNIPPET_CHARS:
        return collapsed[:SNIPPET_CHARS] + ELLIPSIS
    return collapsed


def _l2(left: Sequence[float], right: Sequence[float]) -> float:
    """Plain-Python L2 distance — the metric the exact scan is specified to use."""
    return math.dist(left, right)


def _vector_ranking(query_text: str, sources: Mapping[int, str], depth: int = ARM_DEPTH) -> list[int]:
    """Brute-force expected vector ranking: ascending L2 to the query vector, ties by id."""
    query = embedding_vector(query_text, DIMENSION)
    ordered = sorted(
        sources,
        key=lambda row_id: (_l2(embedding_vector(sources[row_id], DIMENSION), query), row_id),
    )
    return ordered[:depth]


def _ids(hits: Sequence[SearchHit]) -> list[int]:
    return [hit.id for hit in hits]


def _scores(hits: Sequence[SearchHit]) -> list[float]:
    return [hit.score for hit in hits]


def _expected_ids(fused: Sequence[tuple[int, float]]) -> list[int]:
    return [row_id for row_id, _ in fused]


def _expected_scores(fused: Sequence[tuple[int, float]]) -> list[float]:
    return [score for _, score in fused]


# --- seeding (file-local raw inserts; no service is used) ---------------------------------


def _servers() -> Table:
    return schema.metadata.tables["llm_servers"]


def _models() -> Table:
    return schema.metadata.tables["models"]


def _insert_user(engine: Engine, *, user_id: int, username: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.users.insert().values(
                id=user_id,
                username=username,
                password_hash="not-a-real-hash",
                role=Role.ROLEPLAYER,
                is_enabled=True,
                rp_language=None,
                preferred_language=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_character(engine: Engine, *, character_id: int, user_id: int, name: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.characters.insert().values(
                id=character_id,
                user_id=user_id,
                name=name,
                sheet="",
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_session(engine: Engine, *, session_id: int, user_id: int, character_id: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.insert().values(
                id=session_id,
                user_id=user_id,
                character_id=character_id,
                setup_id=None,
                last_used_at=TIMESTAMP,
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_memo(
    engine: Engine,
    *,
    memo_id: int,
    user_id: int,
    body: str,
    scope: str = "user",
    scope_id: int | None = None,
    is_enabled: bool = True,
    is_forced: bool = False,
    sort_key: int = 0,
) -> None:
    """Raw-insert one `memos` row (user-level unless a scope is named)."""
    with engine.begin() as connection:
        connection.execute(
            schema.memos.insert().values(
                id=memo_id,
                user_id=user_id,
                scope=scope,
                scope_id=user_id if scope_id is None else scope_id,
                body=body,
                is_enabled=is_enabled,
                is_forced=is_forced,
                sort_key=sort_key,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_memos(engine: Engine, bodies: Mapping[int, str], *, user_id: int = USER_A) -> None:
    """Raw-insert many user-level `memos` rows in one transaction."""
    with engine.begin() as connection:
        connection.execute(
            schema.memos.insert(),
            [
                {
                    "id": memo_id,
                    "user_id": user_id,
                    "scope": "user",
                    "scope_id": user_id,
                    "body": body,
                    "is_enabled": True,
                    "is_forced": False,
                    "sort_key": index,
                    "created_at": TIMESTAMP,
                    "updated_at": TIMESTAMP,
                }
                for index, (memo_id, body) in enumerate(bodies.items())
            ],
        )


def _insert_message(
    engine: Engine,
    *,
    message_id: int,
    user_id: int,
    session_id: int,
    body: str,
    related_to: int | None = None,
    settled_at: str | None = None,
) -> None:
    """Raw-insert one `messages` row in a chosen state.

    **record** = `settled_at` set, `related_to` null; **zone** = both null; **buried** =
    `related_to` set and therefore `settled_at` null (`ck_messages_buried_or_settled`).
    """
    with engine.begin() as connection:
        connection.execute(
            schema.messages.insert().values(
                id=message_id,
                user_id=user_id,
                session_id=session_id,
                role="user",
                kind=None,
                text=body,
                related_to=related_to,
                settled_at=settled_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_record_row(engine: Engine, *, message_id: int, user_id: int, session_id: int, body: str) -> None:
    _insert_message(
        engine,
        message_id=message_id,
        user_id=user_id,
        session_id=session_id,
        body=body,
        settled_at=SETTLED_AT,
    )


def _seed_designation(engine: Engine, *, dim: int | None = DIMENSION) -> None:
    """Raw-insert one server and one enabled, designated embedding model — no service used."""
    with engine.begin() as connection:
        connection.execute(
            _servers().insert().values(
                id=SERVER_ID,
                name="the embedding server",
                kind="llamaswap",
                base_url=BASE_URL,
                api_key_ref=None,
                last_test_at=None,
                last_test_ok=None,
                last_test_error=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )
        connection.execute(
            _models().insert().values(
                id=MODEL_ID,
                server_id=SERVER_ID,
                model_name=MODEL_NAME,
                is_enabled=True,
                is_embedding_designated=True,
                embedding_dim=dim,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _ensure_fts(engine: Engine) -> None:
    """Create `memo_fts` / `message_fts` with 024's helper (test setup only), after the inserts."""
    with engine.begin() as connection:
        ensure_fts_tables(connection)


def _ensure_vec(engine: Engine, dimension: int = DIMENSION) -> None:
    """Create `memo_vec` / `session_vec` at `dimension` with 024's helper (test setup only)."""
    with engine.begin() as connection:
        ensure_vector_tables(connection, dimension)


def _write_vectors(engine: Engine, table_name: str, sources: Mapping[int, str]) -> None:
    """Write one vector per id, each `embedding_vector(<its source text>, 8)`, via 024's writer."""
    with engine.begin() as connection:
        for row_id, source in sources.items():
            write_vector(connection, table_name, row_id, embedding_vector(source, DIMENSION))


def _table_exists(engine: Engine, table_name: str) -> bool:
    """A file-local `sqlite_master` probe, so absence is asserted without the code under test."""
    with engine.connect() as connection:
        found = connection.execute(
            text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name"),
            {"name": table_name},
        ).first()
    return found is not None


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """Two users, three characters and three sessions — and **no** virtual table, **no** model.

    `create_all` alone leaves all four search tables absent (they live outside
    `schema.metadata`), and nothing is designated; each test opts in to exactly what it needs,
    because "no table" and "no designated model" are both halves of this step's contract.
    """
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="aster")
    _insert_user(db_engine, user_id=USER_B, username="briar")
    _insert_character(db_engine, character_id=CHARACTER_A1, user_id=USER_A, name="first")
    _insert_character(db_engine, character_id=CHARACTER_A2, user_id=USER_A, name="second")
    _insert_character(db_engine, character_id=CHARACTER_B1, user_id=USER_B, name="other owner")
    _insert_session(db_engine, session_id=SESSION_A1, user_id=USER_A, character_id=CHARACTER_A1)
    _insert_session(db_engine, session_id=SESSION_A2, user_id=USER_A, character_id=CHARACTER_A2)
    _insert_session(db_engine, session_id=SESSION_B1, user_id=USER_B, character_id=CHARACTER_B1)
    return db_engine


# --- extra-predicate builders (U1: a clause over the FROM object handed to them) ----------


def _memo_enabled_and_not_forced(relation: FromClause) -> ColumnElement[bool]:
    """`026`'s shape: enabled, not forced."""
    return relation.c["is_enabled"].is_(True) & relation.c["is_forced"].is_(False)


def _session_of_character_except(character_id: int, current_id: int) -> ExtraPredicateBuilder:
    """`027`'s shape: one character's sessions, excluding the current one."""

    def builder(relation: FromClause) -> ColumnElement[bool]:
        return (relation.c["character_id"] == character_id) & (relation.c["id"] != current_id)

    return builder


# --- calling the frozen interface --------------------------------------------------------


def _search(
    engine: Engine,
    scope: SearchScope,
    query_text: str,
    limit: int,
    factory: FakeClientFactory,
) -> list[SearchHit]:
    """`limit` is the fourth **positional** parameter; `client_factory` is keyword-only."""
    with engine.connect() as connection:
        return search(connection, scope, query_text, limit, client_factory=factory)


# --- shared seeding for the four-memo hybrid corpus ---------------------------------------


def _seed_memo_hybrid(engine: Engine) -> None:
    """Four vectored, FTS-indexed memos of `USER_A`, exactly one holding the token."""
    _insert_memos(engine, HYBRID_BODIES)
    _seed_designation(engine)
    _ensure_fts(engine)
    _ensure_vec(engine)
    _write_vectors(engine, MEMO_VEC_TABLE, HYBRID_SOURCES)


def _expected_memo_hybrid(limit: int) -> list[tuple[int, float]]:
    """D1's fusion of the test-derived vector ranking with the single lexical match, cut to `limit`."""
    return _rrf_fuse([_vector_ranking(TOKEN, HYBRID_SOURCES), [MEMO_TWO]])[:limit]


# --- DoD-1: the memo hybrid, end to end (D1, D3) ------------------------------------------


def test_memo_hybrid_ids_order_and_scores_are_the_fused_arms__S025_004_DoD1(engine: Engine) -> None:
    """Both arms run and the result **is** D1's fusion of them, cut to `limit`.

    The vector ranking is the test's own brute force over the fake's vectors; the lexical ranking
    is `[MEMO_TWO]`, the one body containing the token, so its rank is unambiguously 1.
    """
    _seed_memo_hybrid(engine)
    limit = 3
    expected = _expected_memo_hybrid(limit)
    factory = fake_factory(DIMENSION)

    hits = _search(engine, MemoSearchScope(user_id=USER_A), TOKEN, limit, factory)

    # The expectation is only meaningful if both arms really contribute.
    assert len(_vector_ranking(TOKEN, HYBRID_SOURCES)) == len(HYBRID_SOURCES)
    assert len(expected) == limit
    assert _ids(hits) == _expected_ids(expected)
    assert _scores(hits) == pytest.approx(_expected_scores(expected))


def test_every_memo_hit_carries_its_level_no_session_and_a_snippet__S025_004_DoD1(engine: Engine) -> None:
    """D3's memo row of the hit table: kind, level, `session_id` none, snippet never empty."""
    _seed_memo_hybrid(engine)
    factory = fake_factory(DIMENSION)

    hits = _search(engine, MemoSearchScope(user_id=USER_A), TOKEN, 4, factory)

    assert len(hits) == len(HYBRID_BODIES)
    for hit in hits:
        assert hit.kind == "memo"
        assert hit.memo_scope == "user"
        assert hit.memo_scope_id == USER_A
        assert hit.session_id is None
        assert isinstance(hit.snippet, str)
        assert hit.snippet != ""


# --- DoD-2: the lexical arm rescues the exact token ("Why hybrid") -------------------------


def test_lexical_rescues_a_memo_outside_the_vector_arm__S025_004_DoD2(engine: Engine) -> None:
    """The clause that justifies hybrid search existing.

    60 memos — more than `ARM_DEPTH` — all vectored. The 59 fillers take the pool texts
    **nearest** the query vector and the target the **farthest**, so the target's vector rank is
    60: outside the arm **by construction**, which the test then verifies from the fake's pure
    function. Only the target's body holds the rare token, so it is rank 1 of the lexical arm and
    absent from the vector arm — fused score exactly `1 / (60 + 1)`.
    """
    query = embedding_vector(RARE_TOKEN, DIMENSION)
    by_distance = sorted(RESCUE_POOL, key=lambda source: (_l2(embedding_vector(source, DIMENSION), query), source))
    filler_sources = dict(zip(RESCUE_FILLER_IDS, by_distance[:RESCUE_FILLER_COUNT], strict=True))
    sources = {**filler_sources, RESCUE_TARGET: by_distance[-1]}
    bodies = {memo_id: f"a filler memo body number {memo_id}" for memo_id in RESCUE_FILLER_IDS}
    bodies[RESCUE_TARGET] = f"the {RARE_TOKEN} charm lies under the floorboards"

    _insert_memos(engine, bodies)
    _seed_designation(engine)
    _ensure_fts(engine)
    _ensure_vec(engine)
    _write_vectors(engine, MEMO_VEC_TABLE, sources)

    full_order = _vector_ranking(RARE_TOKEN, sources, depth=RESCUE_MEMO_COUNT)
    vector_arm = _vector_ranking(RARE_TOKEN, sources)
    expected = _rrf_fuse([vector_arm, [RESCUE_TARGET]])[:RESCUE_LIMIT]
    factory = fake_factory(DIMENSION)

    # The fixture must really put the target outside the vector arm, or the test proves nothing.
    assert len(bodies) == RESCUE_MEMO_COUNT > ARM_DEPTH
    assert full_order.index(RESCUE_TARGET) + 1 == RESCUE_MEMO_COUNT
    assert full_order.index(RESCUE_TARGET) + 1 > ARM_DEPTH
    assert RESCUE_TARGET not in vector_arm
    assert len(vector_arm) == ARM_DEPTH

    hits = _search(engine, MemoSearchScope(user_id=USER_A), RARE_TOKEN, RESCUE_LIMIT, factory)
    rescued = [hit for hit in hits if hit.id == RESCUE_TARGET]

    assert len(rescued) == 1
    assert rescued[0].score == pytest.approx(1.0 / (RRF_K + 1))
    assert _ids(hits) == _expected_ids(expected)
    assert _scores(hits) == pytest.approx(_expected_scores(expected))


# --- DoD-3: the two memo snippet shapes, and no field beyond D3's (D4, US-119) -------------


def test_memo_snippet_shapes_per_arm__S025_004_DoD3(engine: Engine) -> None:
    """A lexical hit's snippet contains the token; a vector-only hit's **is** the leading extract."""
    _insert_memo(engine, memo_id=MEMO_LEXICAL, user_id=USER_A, body=SHORT_TOKEN_BODY)
    _insert_memo(engine, memo_id=MEMO_VECTOR_ONLY, user_id=USER_A, body=VECTOR_ONLY_BODY)
    _seed_designation(engine)
    _ensure_fts(engine)
    _ensure_vec(engine)
    _write_vectors(
        engine,
        MEMO_VEC_TABLE,
        {MEMO_LEXICAL: HYBRID_SOURCES[MEMO_ONE], MEMO_VECTOR_ONLY: HYBRID_SOURCES[MEMO_TWO]},
    )
    factory = fake_factory(DIMENSION)

    hits = _search(engine, MemoSearchScope(user_id=USER_A), TOKEN, 2, factory)
    snippets = {hit.id: hit.snippet for hit in hits}

    assert set(snippets) == {MEMO_LEXICAL, MEMO_VECTOR_ONLY}
    assert snippets[MEMO_LEXICAL] is not None
    assert TOKEN in snippets[MEMO_LEXICAL]
    # D4: found by the vector arm only ⇒ exactly the leading extract, computed here from D4's rule.
    assert snippets[MEMO_VECTOR_ONLY] == _leading_extract(VECTOR_ONLY_BODY)
    assert snippets[MEMO_VECTOR_ONLY] != VECTOR_ONLY_BODY
    assert len(_leading_extract(VECTOR_ONLY_BODY)) == SNIPPET_CHARS + 1


def test_no_hit_carries_a_title_or_any_field_beyond_the_hit_shape__S025_004_DoD3(engine: Engine) -> None:
    """US-119: a memo hit has no title, ever — and the hit shape is exactly D3's seven fields."""
    _seed_memo_hybrid(engine)
    factory = fake_factory(DIMENSION)

    hits = _search(engine, MemoSearchScope(user_id=USER_A), TOKEN, 4, factory)

    assert frozenset(field.name for field in dataclasses.fields(SearchHit)) == EXPECTED_HIT_FIELDS
    assert hits != []
    for hit in hits:
        assert not hasattr(hit, "title")
        assert not hasattr(hit, "name")


# --- DoD-4: a memo hit's level is `scope` + `scope_id` only (U3) ---------------------------


def test_memo_hits_carry_the_stored_scope_and_scope_id__S025_004_DoD4(engine: Engine) -> None:
    """A user-level and a session-level memo, each reporting its own stored level — no name."""
    _insert_memo(engine, memo_id=MEMO_USER_LEVEL, user_id=USER_A, body=SHORT_TOKEN_BODY)
    _insert_memo(
        engine,
        memo_id=MEMO_SESSION_LEVEL,
        user_id=USER_A,
        body=SHORT_TOKEN_BODY,
        scope="session",
        scope_id=SESSION_A1,
    )
    _seed_designation(engine)
    _ensure_fts(engine)
    _ensure_vec(engine)
    _write_vectors(
        engine,
        MEMO_VEC_TABLE,
        {MEMO_USER_LEVEL: HYBRID_SOURCES[MEMO_ONE], MEMO_SESSION_LEVEL: HYBRID_SOURCES[MEMO_TWO]},
    )
    factory = fake_factory(DIMENSION)

    hits = _search(engine, MemoSearchScope(user_id=USER_A), TOKEN, 2, factory)
    levels = {hit.id: (hit.memo_scope, hit.memo_scope_id) for hit in hits}

    assert levels == {
        MEMO_USER_LEVEL: ("user", USER_A),
        MEMO_SESSION_LEVEL: ("session", SESSION_A1),
    }
    assert not any("name" in field.name for field in dataclasses.fields(SearchHit))


# --- DoD-5: the session variant is vector-only (U1, D3) -----------------------------------


def test_session_search_is_the_vector_ranking_with_no_fts_table_present__S025_004_DoD5(engine: Engine) -> None:
    """Session hits in the test-derived vector order, scores `1/(60+rank)`, snippet none.

    **Neither FTS table is created.** The search can only succeed if no FTS table is queried for
    this variant (U1: there is no `session_fts`, and `message_fts` would yield message hits).
    """
    sources = {SESSION_A1: HYBRID_SOURCES[MEMO_ONE], SESSION_A2: HYBRID_SOURCES[MEMO_TWO]}
    _seed_designation(engine)
    _ensure_vec(engine)
    _write_vectors(engine, SESSION_VEC_TABLE, sources)
    factory = fake_factory(DIMENSION)

    assert _table_exists(engine, MEMO_FTS_TABLE) is False
    assert _table_exists(engine, MESSAGE_FTS_TABLE) is False

    hits = _search(engine, SessionSearchScope(user_id=USER_A), TOKEN, 5, factory)

    assert _ids(hits) == _vector_ranking(TOKEN, sources)
    assert _scores(hits) == pytest.approx([1.0 / (RRF_K + 1), 1.0 / (RRF_K + 2)])
    for hit in hits:
        assert hit.kind == "session"
        assert hit.snippet is None
        assert hit.memo_scope is None
        assert hit.memo_scope_id is None
        assert hit.session_id is None


# --- DoD-6: the entry variant is lexical-only and never opens the model (U1, U2) -----------


def test_entry_search_is_lexical_only_and_opens_no_model__S025_004_DoD6(engine: Engine) -> None:
    """Entry hits for the record rows holding the token — with **no designated model at all**.

    The fake factory is never called, which is the direct statement that the entry scope does not
    touch the embedding model. The order is BM25's definition: the token twice in a three-token
    body outranks the token once in a 49-token body.
    """
    _insert_record_row(engine, message_id=MESSAGE_A1, user_id=USER_A, session_id=SESSION_A1, body=SHORT_TOKEN_BODY)
    _insert_record_row(engine, message_id=MESSAGE_A2, user_id=USER_A, session_id=SESSION_A2, body=LONG_TOKEN_BODY)
    _insert_record_row(engine, message_id=MESSAGE_B1, user_id=USER_B, session_id=SESSION_B1, body=SHORT_TOKEN_BODY)
    _ensure_fts(engine)
    factory = fake_factory(DIMENSION)

    hits = _search(engine, EntrySearchScope(user_id=USER_A), TOKEN, 5, factory)

    assert factory.call_count == 0
    assert factory.embed_calls == []
    assert _ids(hits) == [MESSAGE_A1, MESSAGE_A2]
    assert _scores(hits) == pytest.approx([1.0 / (RRF_K + 1), 1.0 / (RRF_K + 2)])
    assert {hit.id: hit.session_id for hit in hits} == {MESSAGE_A1: SESSION_A1, MESSAGE_A2: SESSION_A2}
    for hit in hits:
        assert hit.kind == "entry"
        assert hit.snippet is not None
        assert TOKEN in hit.snippet
        assert hit.memo_scope is None
        assert hit.memo_scope_id is None


# --- DoD-7: owner isolation, as an absence, for each variant (D6, UC-065, US-085) ----------


def test_another_owners_memo_matching_both_arms_is_absent__S025_004_DoD7(engine: Engine) -> None:
    """`USER_B`'s memo holds the token **and** stores the query vector exactly (distance 0)."""
    _insert_memos(engine, HYBRID_BODIES)
    _insert_memo(engine, memo_id=MEMO_B_MATCHING, user_id=USER_B, body=SHORT_TOKEN_BODY)
    _seed_designation(engine)
    _ensure_fts(engine)
    _ensure_vec(engine)
    _write_vectors(engine, MEMO_VEC_TABLE, {**HYBRID_SOURCES, MEMO_B_MATCHING: TOKEN})
    expected = _expected_memo_hybrid(10)
    factory = fake_factory(DIMENSION)

    hits = _search(engine, MemoSearchScope(user_id=USER_A), TOKEN, 10, factory)

    assert MEMO_B_MATCHING not in _ids(hits)
    assert _ids(hits) == _expected_ids(expected)
    assert _scores(hits) == pytest.approx(_expected_scores(expected))


def test_another_owners_session_matching_the_vector_arm_is_absent__S025_004_DoD7(engine: Engine) -> None:
    """The session variant runs one arm, and `USER_B`'s session is at distance 0 on it."""
    sources = {SESSION_A1: HYBRID_SOURCES[MEMO_ONE], SESSION_A2: HYBRID_SOURCES[MEMO_TWO]}
    _seed_designation(engine)
    _ensure_vec(engine)
    _write_vectors(engine, SESSION_VEC_TABLE, {**sources, SESSION_B1: TOKEN})
    factory = fake_factory(DIMENSION)

    hits = _search(engine, SessionSearchScope(user_id=USER_A), TOKEN, 10, factory)

    assert SESSION_B1 not in _ids(hits)
    assert _ids(hits) == _vector_ranking(TOKEN, sources)


def test_another_owners_entry_matching_the_lexical_arm_is_absent__S025_004_DoD7(engine: Engine) -> None:
    """The entry variant runs one arm, and `USER_B`'s record row matches it."""
    _insert_record_row(engine, message_id=MESSAGE_A1, user_id=USER_A, session_id=SESSION_A1, body=SHORT_TOKEN_BODY)
    _insert_record_row(engine, message_id=MESSAGE_B1, user_id=USER_B, session_id=SESSION_B1, body=SHORT_TOKEN_BODY)
    _ensure_fts(engine)
    factory = fake_factory(DIMENSION)

    hits = _search(engine, EntrySearchScope(user_id=USER_A), TOKEN, 10, factory)

    assert MESSAGE_B1 not in _ids(hits)
    assert _ids(hits) == [MESSAGE_A1]


# --- DoD-8: the caller's extra predicate is honoured (U1) ---------------------------------


def test_memo_extra_predicate_excludes_the_disabled_and_the_forced__S025_004_DoD8(engine: Engine) -> None:
    """Both excluded memos match on **both** arms (token in the body, query vector stored)."""
    _insert_memo(engine, memo_id=MEMO_PLAIN, user_id=USER_A, body=SHORT_TOKEN_BODY)
    _insert_memo(engine, memo_id=MEMO_DISABLED, user_id=USER_A, body=SHORT_TOKEN_BODY, is_enabled=False)
    _insert_memo(engine, memo_id=MEMO_FORCED, user_id=USER_A, body=SHORT_TOKEN_BODY, is_forced=True)
    _seed_designation(engine)
    _ensure_fts(engine)
    _ensure_vec(engine)
    _write_vectors(
        engine,
        MEMO_VEC_TABLE,
        {MEMO_PLAIN: HYBRID_SOURCES[MEMO_ONE], MEMO_DISABLED: TOKEN, MEMO_FORCED: TOKEN},
    )
    scope = MemoSearchScope(user_id=USER_A, extra_predicate=_memo_enabled_and_not_forced)
    factory = fake_factory(DIMENSION)

    hits = _search(engine, scope, TOKEN, 10, factory)

    assert _ids(hits) == [MEMO_PLAIN]
    assert MEMO_DISABLED not in _ids(hits)
    assert MEMO_FORCED not in _ids(hits)
    # One id, rank 1 in the single arm that found it (memo runs two arms, lexical and vector).
    assert hits[0].score == pytest.approx(2.0 / (RRF_K + 1))


def test_session_extra_predicate_excludes_the_other_character_and_the_current__S025_004_DoD8(
    engine: Engine,
) -> None:
    """`character_id = :c AND id != :current` — both excluded sessions are at distance 0."""
    _insert_session(engine, session_id=SESSION_A3, user_id=USER_A, character_id=CHARACTER_A1)
    _seed_designation(engine)
    _ensure_vec(engine)
    _write_vectors(
        engine,
        SESSION_VEC_TABLE,
        {SESSION_A3: HYBRID_SOURCES[MEMO_ONE], SESSION_A1: TOKEN, SESSION_A2: TOKEN},
    )
    scope = SessionSearchScope(
        user_id=USER_A,
        extra_predicate=_session_of_character_except(CHARACTER_A1, SESSION_A1),
    )
    factory = fake_factory(DIMENSION)

    hits = _search(engine, scope, TOKEN, 10, factory)

    assert _ids(hits) == [SESSION_A3]
    assert SESSION_A1 not in _ids(hits)
    assert SESSION_A2 not in _ids(hits)
    assert hits[0].score == pytest.approx(1.0 / (RRF_K + 1))


# --- DoD-9: the entry corpus boundary, as an absence (R11, US-115, UC-038) -----------------


def test_zone_and_buried_rows_are_never_entry_hits__S025_004_DoD9(engine: Engine) -> None:
    """All three rows hold the token, in the same session, for the same owner."""
    _insert_record_row(engine, message_id=MESSAGE_A1, user_id=USER_A, session_id=SESSION_A1, body=SHORT_TOKEN_BODY)
    _insert_message(
        engine,
        message_id=MESSAGE_A_ZONE,
        user_id=USER_A,
        session_id=SESSION_A1,
        body=f"a zone draft naming {TOKEN}",
    )
    _insert_message(
        engine,
        message_id=MESSAGE_A_BURIED,
        user_id=USER_A,
        session_id=SESSION_A1,
        body=f"a buried alternative naming {TOKEN}",
        related_to=MESSAGE_A1,
    )
    _ensure_fts(engine)
    factory = fake_factory(DIMENSION)

    hits = _search(engine, EntrySearchScope(user_id=USER_A), TOKEN, 10, factory)

    assert _ids(hits) == [MESSAGE_A1]
    assert MESSAGE_A_ZONE not in _ids(hits)
    assert MESSAGE_A_BURIED not in _ids(hits)


# --- DoD-10: no model means an error, never a degrade to lexical (U2, R4) ------------------


def test_memo_search_without_a_model_raises_even_though_fts_matches__S025_004_DoD10(engine: Engine) -> None:
    """The clause proving lexical results are not silently returned instead.

    `memo_fts` exists and holds a match, so a degrading implementation would return a hit; the
    port must raise instead, and must not even build a client.
    """
    _insert_memo(engine, memo_id=MEMO_LEXICAL, user_id=USER_A, body=SHORT_TOKEN_BODY)
    _ensure_fts(engine)
    _ensure_vec(engine)
    _write_vectors(engine, MEMO_VEC_TABLE, {MEMO_LEXICAL: HYBRID_SOURCES[MEMO_ONE]})
    factory = fake_factory(DIMENSION)

    assert _table_exists(engine, MEMO_FTS_TABLE) is True

    with pytest.raises(NoEmbeddingModelError):
        _search(engine, MemoSearchScope(user_id=USER_A), TOKEN, 5, factory)

    assert factory.call_count == 0
    assert factory.embed_calls == []


def test_session_search_without_a_model_raises__S025_004_DoD10(engine: Engine) -> None:
    _ensure_vec(engine)
    _write_vectors(engine, SESSION_VEC_TABLE, {SESSION_A1: HYBRID_SOURCES[MEMO_ONE]})
    factory = fake_factory(DIMENSION)

    with pytest.raises(NoEmbeddingModelError):
        _search(engine, SessionSearchScope(user_id=USER_A), TOKEN, 5, factory)

    assert factory.call_count == 0


def test_an_unreachable_provider_propagates_from_a_memo_search__S025_004_DoD10(engine: Engine) -> None:
    """The provider's own error reaches the caller unchanged (U2) — no lexical fallback."""
    _seed_memo_hybrid(engine)
    factory = unreachable_factory(DIMENSION)

    with pytest.raises(LlmUnreachableError):
        _search(engine, MemoSearchScope(user_id=USER_A), TOKEN, 5, factory)


# --- DoD-11: the early exits, for every variant (D2) --------------------------------------


def _seed_all_corpora(engine: Engine) -> None:
    """Enough of all three corpora, with both tables and a designation, that only D2 can empty."""
    _insert_memos(engine, HYBRID_BODIES)
    _insert_record_row(engine, message_id=MESSAGE_A1, user_id=USER_A, session_id=SESSION_A1, body=SHORT_TOKEN_BODY)
    _seed_designation(engine)
    _ensure_fts(engine)
    _ensure_vec(engine)
    _write_vectors(engine, MEMO_VEC_TABLE, HYBRID_SOURCES)
    _write_vectors(
        engine,
        SESSION_VEC_TABLE,
        {SESSION_A1: HYBRID_SOURCES[MEMO_ONE], SESSION_A2: HYBRID_SOURCES[MEMO_TWO]},
    )


@pytest.mark.parametrize(
    "scope",
    [
        MemoSearchScope(user_id=USER_A),
        SessionSearchScope(user_id=USER_A),
        EntrySearchScope(user_id=USER_A),
    ],
    ids=["memo", "session", "entry"],
)
@pytest.mark.parametrize(
    ("query_text", "limit"),
    [
        (TOKEN, 0),
        (TOKEN, -3),
        ("", 5),
        ("   \t\n  ", 5),
    ],
    ids=["limit-zero", "negative-limit", "empty-query", "whitespace-query"],
)
def test_early_exits_return_nothing_and_open_nothing__S025_004_DoD11(
    engine: Engine,
    scope: SearchScope,
    query_text: str,
    limit: int,
) -> None:
    """`limit <= 0` or a blank query: `[]`, and no embedding model opened (D2)."""
    _seed_all_corpora(engine)
    factory = fake_factory(DIMENSION)

    assert _search(engine, scope, query_text, limit, factory) == []
    assert factory.call_count == 0
    assert factory.embed_calls == []


# --- DoD-12: a query with no usable lexical text (`001.context.md` rule 6, D1) -------------


def test_a_punctuation_only_query_returns_the_vector_arm_alone__S025_004_DoD12(engine: Engine) -> None:
    """`'\"\"\"'` sanitises to **none**, so only the vector arm contributes — and nothing raises.

    This is also the guard against ever issuing `MATCH ''`, which raises an FTS5 syntax error.
    `memo_fts` is present and the memos are indexed, so an empty lexical contribution can only
    come from the sanitiser's none.
    """
    _seed_memo_hybrid(engine)
    expected = _vector_ranking(PUNCTUATION_QUERY, HYBRID_SOURCES)
    factory = fake_factory(DIMENSION)

    assert _table_exists(engine, MEMO_FTS_TABLE) is True

    hits = _search(engine, MemoSearchScope(user_id=USER_A), PUNCTUATION_QUERY, 4, factory)

    assert _ids(hits) == expected
    assert _scores(hits) == pytest.approx([1.0 / (RRF_K + rank) for rank in range(1, len(expected) + 1)])
    # Every hit is vector-only, so every snippet is D4's leading extract of its body.
    for hit in hits:
        assert hit.snippet == _leading_extract(HYBRID_BODIES[hit.id])


# --- DoD-13: absent tables are empty, not errors (U2) -------------------------------------


def test_memo_search_with_neither_memo_table_present_returns_nothing__S025_004_DoD13(engine: Engine) -> None:
    """A designated model exists; `memo_fts` and `memo_vec` do not. No error, no hits."""
    _insert_memos(engine, HYBRID_BODIES)
    _seed_designation(engine)
    factory = fake_factory(DIMENSION)

    assert _table_exists(engine, MEMO_FTS_TABLE) is False
    assert _table_exists(engine, MEMO_VEC_TABLE) is False

    assert _search(engine, MemoSearchScope(user_id=USER_A), TOKEN, 10, factory) == []


def test_memo_search_with_only_memo_fts_returns_the_lexical_matches__S025_004_DoD13(engine: Engine) -> None:
    """`memo_vec` absent: the lexical arm alone, scores `1/(60+rank)`, snippets from FTS5.

    The order is BM25's definition — twice in a three-token body beats once in a 49-token body —
    and the long-body memo has the **lower** id, so an id-ordered result would be reversed.
    """
    _insert_memo(engine, memo_id=MEMO_LONG, user_id=USER_A, body=LONG_TOKEN_BODY)
    _insert_memo(engine, memo_id=MEMO_SHORT, user_id=USER_A, body=SHORT_TOKEN_BODY)
    _insert_memo(engine, memo_id=MEMO_ONE, user_id=USER_A, body=BODY_WITHOUT_TOKEN)
    _seed_designation(engine)
    _ensure_fts(engine)
    factory = fake_factory(DIMENSION)

    assert _table_exists(engine, MEMO_VEC_TABLE) is False

    hits = _search(engine, MemoSearchScope(user_id=USER_A), TOKEN, 10, factory)
    snippets = {hit.id: hit.snippet for hit in hits}

    assert _ids(hits) == [MEMO_SHORT, MEMO_LONG]
    assert _scores(hits) == pytest.approx([1.0 / (RRF_K + 1), 1.0 / (RRF_K + 2)])
    assert MEMO_ONE not in _ids(hits)
    assert snippets[MEMO_SHORT] == SHORT_TOKEN_BODY
    assert snippets[MEMO_LONG] is not None
    assert TOKEN in snippets[MEMO_LONG]
    assert ELLIPSIS in snippets[MEMO_LONG]


def test_entry_search_with_message_fts_absent_returns_nothing__S025_004_DoD13(engine: Engine) -> None:
    """Record rows holding the token exist; the index does not. No error, no hits."""
    _insert_record_row(engine, message_id=MESSAGE_A1, user_id=USER_A, session_id=SESSION_A1, body=SHORT_TOKEN_BODY)
    factory = fake_factory(DIMENSION)

    assert _table_exists(engine, MESSAGE_FTS_TABLE) is False

    assert _search(engine, EntrySearchScope(user_id=USER_A), TOKEN, 10, factory) == []


# --- DoD-14: `limit` is the final count (D1) ----------------------------------------------


def test_a_limit_larger_than_the_fused_set_returns_all_of_it__S025_004_DoD14(engine: Engine) -> None:
    _seed_memo_hybrid(engine)
    expected = _expected_memo_hybrid(100)
    factory = fake_factory(DIMENSION)

    with engine.connect() as connection:
        # `limit` is positional-or-keyword, so the keyword form is also legal.
        hits = search(connection, MemoSearchScope(user_id=USER_A), TOKEN, limit=100, client_factory=factory)

    assert len(expected) == len(HYBRID_BODIES)
    assert _ids(hits) == _expected_ids(expected)
    assert _scores(hits) == pytest.approx(_expected_scores(expected))


def test_a_smaller_limit_returns_the_prefix_of_the_fused_set__S025_004_DoD14(engine: Engine) -> None:
    _seed_memo_hybrid(engine)
    whole = _expected_memo_hybrid(100)
    factory = fake_factory(DIMENSION)

    hits = _search(engine, MemoSearchScope(user_id=USER_A), TOKEN, 2, factory)

    assert len(hits) == 2
    assert _ids(hits) == _expected_ids(whole)[:2]
    assert _scores(hits) == pytest.approx(_expected_scores(whole)[:2])


# --- DoD-15: the package's imports (`context.md` cross-cutting constraints) ----------------


def _package_directory() -> Path:
    package_file = search_package.__file__
    assert package_file is not None
    return Path(package_file).parent


def _imported_roots(module_path: Path) -> set[str]:
    """The first dotted component of every name the module imports."""
    roots: set[str] = set()
    for node in ast.walk(ast.parse(module_path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.add(node.module.split(".")[0])
    return roots


def test_the_six_search_modules_are_all_present_to_scan__S025_004_DoD15() -> None:
    """The scan would be vacuous if a module were missing, so pin the file list first."""
    directory = _package_directory()

    assert {path.name for path in directory.glob("*.py")} == set(SEARCH_PACKAGE_MODULES)


def test_no_search_module_imports_fastapi__S025_004_DoD15() -> None:
    """`backend-structure.md`: services import no web framework."""
    directory = _package_directory()
    offenders = {
        name
        for name in SEARCH_PACKAGE_MODULES
        if _imported_roots(directory / name) & {"fastapi", "starlette"}
    }

    assert offenders == set()


def test_only_the_vector_module_imports_sqlite_vec__S025_004_DoD15() -> None:
    """The vector extension is the vector arm's business and nobody else's."""
    directory = _package_directory()
    offenders = {
        name
        for name in SEARCH_PACKAGE_MODULES
        if name != "vector.py" and "sqlite_vec" in _imported_roots(directory / name)
    }

    assert offenders == set()
