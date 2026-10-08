"""Tests for the vector arm — feature 025, step 003 (DoD-1..11).

Every expected value comes from the **spec**, never from the implementation:
`docs/plans/025.hybrid-search-port/003.vector-arm.md` (Interface intent — the five ordered
steps — and Definition of done), `003.context.md` (the one permitted query form, the
dimension handling, the ordering rationale and the "Test shape" note) and the feature
`context.md` — **U2** (the model's errors propagate; an absent or empty vec table yields no
hits and is *not* an error; the model is opened **only** when the vector arm runs), **D5**
(filters first: an arm ranks only inside the candidate set) and **D6** (the owner predicate
in every statement, tested as an *absence*).

How the expected order is derived (`003.context.md` "Test shape")
----------------------------------------------------------------
Each ranked row's stored vector is `llm_fakes.embedding_vector(<source text>, 8)` — a **pure**
function of `(text, dim)`. The query's vector is the same function of the query text. The test
therefore computes the expected ranking itself, with a plain-Python L2 distance and ties broken
by **ascending id**, and never asks the code under test what the answer is.

The comparison is exact, with no tolerance, and that is sound rather than lucky: every vector
component is a multiple of `2 ** -8` strictly inside `(-1, 1)` (`llm_fakes.py`'s documented
contract), so every component difference is a multiple of `2 ** -8`, every squared difference a
multiple of `2 ** -16`, and the 8-term sum is an integer multiple of `2 ** -16` below `8` —
exactly representable in float32. Two mathematically distinct distances therefore differ by far
more than float32 resolution, and two mathematically equal distances are *bit-identical* in
float32, so the tie falls through to the ascending-id tiebreak on both sides.

Bindings come from `## Skeleton` -> "Step 003 — frozen interface" in `status.md`:
`vector_ranking(connection, table_name, candidate_select, query_text, *, depth=ARM_DEPTH,
client_factory=LlmClient, timeout_seconds=DEFAULT_EMBED_TIMEOUT_SECONDS) -> list[int]`
(**`depth`, `client_factory` and `timeout_seconds` are keyword-only**; the return value is a
plain list of ids). The candidate select comes from step 002's `candidate_ids(scope)` and the
scope variants from step 001's record.

Each test name ends `__S025_003_DoD<n>` with the DoD item it covers.

Mechanics (`context.md` "Test conventions"):
- a real SQLite file per test via the shared `db_engine` fixture, with
  `schema.metadata.create_all`; **`tests/conftest.py` is untouched** and every other fixture
  and helper here is file-local;
- every row is a **raw insert** with an id **above 2^60**, and **two users** are always present
  so owner isolation is observable as an absence;
- the vec tables are created only through 024's `ensure_vector_tables` and written only through
  024's `write_vector`; the two virtual tables are named only through 024's constants, and
  `memo_vec` / `session_vec` are keyed by `memo_id` / `session_id` (never `rowid`);
- a designated model is a raw `llm_servers` + `models` pair with `is_enabled`,
  `is_embedding_designated` and `embedding_dim` (8), so no registry write path is used, and the
  server carries `api_key_ref=None` so no environment variable is involved;
- the provider is injected through the frozen `client_factory=` seam with the shared fake in
  `tests/llm_fakes.py` (**never edited**). **No monkeypatching**, no network.
"""

import ast
import inspect
import math
from collections.abc import Mapping, Sequence

import pytest
from sqlalchemy import ColumnElement, Engine, FromClause, Table

import app.services.search.vector as vector_module
from app.db import schema
from app.db.search_tables import (
    MEMO_VEC_TABLE,
    SESSION_VEC_TABLE,
    ensure_vector_tables,
    vector_table_dimension,
)
from app.errors import LlmUnreachableError, NoEmbeddingModelError
from app.roles import Role
from app.services.embedding import write_vector
from app.services.search.candidates import candidate_ids
from app.services.search.ports import (
    ARM_DEPTH,
    ExtraPredicateBuilder,
    MemoSearchScope,
    SearchScope,
    SessionSearchScope,
)
from app.services.search.vector import vector_ranking
from tests.llm_fakes import (
    FakeClientFactory,
    embedding_vector,
    fake_factory,
    unreachable_factory,
)

#: The seeded instant, in the project's fixed-width UTC text form.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

#: The designated dimension throughout; 8 keeps the tests fast (`context.md`).
DIMENSION = 8

#: A second, deliberately different designation width, for the DoD-9 mismatch.
OTHER_DIMENSION = 16

#: Every id below is above 2^60 = 1152921504606846976 (snowflake-sized, 024 D3).
SNOWFLAKE_FLOOR = 2**60

USER_A = 1_500_000_000_000_000_001
USER_B = 1_500_000_000_000_000_002

CHARACTER_A1 = 1_500_000_000_000_000_101
CHARACTER_A2 = 1_500_000_000_000_000_102
CHARACTER_B1 = 1_500_000_000_000_000_103

SESSION_A1 = 1_500_000_000_000_000_201
SESSION_A2 = 1_500_000_000_000_000_202
SESSION_B1 = 1_500_000_000_000_000_203
#: A `USER_B` session deliberately placed under **`USER_A`'s** character: the only way to show
#: that the owner predicate still applies *alongside* a satisfied extra predicate (DoD-4).
SESSION_B2 = 1_500_000_000_000_000_204

SERVER_ID = 1_500_000_000_000_000_901
MODEL_ID = 1_500_000_000_000_000_902

BASE_URL = "http://embedding.test:8080/v1"
MODEL_NAME = "the-designated-embedding-model"

#: DoD-1: four memos of one user, each with a vector of its own source text.
MEMO_A_ONE = 1_500_000_000_000_000_301
MEMO_A_TWO = 1_500_000_000_000_000_302
MEMO_A_THREE = 1_500_000_000_000_000_303
MEMO_A_FOUR = 1_500_000_000_000_000_304

#: DoD-3: rows whose vector is the **query vector exactly** (distance 0) yet must be absent.
MEMO_B_EXACT = 1_500_000_000_000_000_311
MEMO_A_DISABLED_EXACT = 1_500_000_000_000_000_312

#: DoD-5: a candidate with no vector row at all.
MEMO_A_WITHOUT_VECTOR = 1_500_000_000_000_000_313

#: DoD-5: more candidates with vectors than the depth the call asks for.
MEMO_CAP_IDS = tuple(1_500_000_000_000_000_321 + offset for offset in range(5))
CAP_DEPTH = 3

#: DoD-2 (the snowflake-correctness proof against 024 D3). The ids are **spread and
#: non-contiguous** — a prime stride — and candidates and non-candidates are **interleaved**, so
#: no id range separates the two sets. `BULK_DEPTH` is far smaller than `BULK_COUNT`.
BULK_BASE = 1_500_000_000_000_000_000
BULK_STRIDE = 104_729
BULK_COUNT = 200
BULK_DEPTH = 25
BULK_CANDIDATE_IDS = tuple(BULK_BASE + (2 * index) * BULK_STRIDE for index in range(BULK_COUNT))
BULK_OTHER_IDS = tuple(BULK_BASE + (2 * index + 1) * BULK_STRIDE for index in range(BULK_COUNT))

#: 024 measured the pushed-down-KNN defect in only 18-36 % of queries at realistic ids, so the
#: snowflake test sweeps several distinct query texts rather than one (`003.context.md`).
BULK_QUERY_TEXTS = tuple(f"the probe query number {index}" for index in range(8))

#: The query whose embedding every other test ranks against.
QUERY_TEXT = "a query the fake embeds deterministically"

#: Source texts for the stored vectors — all distinct, so all distances are distinct.
SOURCE_ONE = "the lantern over the harbour"
SOURCE_TWO = "a ledger of unpaid debts"
SOURCE_THREE = "rain against the shutters"
SOURCE_FOUR = "the long road inland"


def _source_text(index: int) -> str:
    """A distinct source text per row, for the bulk and cap fixtures."""
    return f"stored vector source text number {index}"


# --- the expected ranking, computed from the fake's pure function -------------------------


def _l2(left: Sequence[float], right: Sequence[float]) -> float:
    """Plain-Python L2 distance — the metric `003.context.md` fixes for the exact scan."""
    return math.dist(left, right)


def _expected_ranking(query_text: str, sources: Mapping[int, str], depth: int = ARM_DEPTH) -> list[int]:
    """Brute-force expected ranking: ascending L2 to the query vector, ties by ascending id.

    `sources` maps each **ranked** row's id to the text its stored vector was derived from.
    """
    query = embedding_vector(query_text, DIMENSION)
    ordered = sorted(
        sources,
        key=lambda row_id: (_l2(embedding_vector(sources[row_id], DIMENSION), query), row_id),
    )
    return ordered[:depth]


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


def _insert_memos(engine: Engine, rows: Sequence[tuple[int, int, bool]]) -> None:
    """Raw-insert user-level `memos` rows as `(memo_id, user_id, is_enabled)`, in one transaction.

    The body text is irrelevant to the vector arm (it indexes no text), so it is derived from the
    id purely to keep the rows distinguishable.
    """
    with engine.begin() as connection:
        connection.execute(
            schema.memos.insert(),
            [
                {
                    "id": memo_id,
                    "user_id": user_id,
                    "scope": "user",
                    "scope_id": user_id,
                    "body": f"the body of memo {memo_id}",
                    "is_enabled": is_enabled,
                    "is_forced": False,
                    "sort_key": index,
                    "created_at": TIMESTAMP,
                    "updated_at": TIMESTAMP,
                }
                for index, (memo_id, user_id, is_enabled) in enumerate(rows)
            ],
        )


def _seed_designation(
    engine: Engine,
    *,
    dim: int | None = DIMENSION,
    is_enabled: bool = True,
    is_designated: bool = True,
) -> None:
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
                is_enabled=is_enabled,
                is_embedding_designated=is_designated,
                embedding_dim=dim,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _ensure_vec_tables(engine: Engine, dimension: int = DIMENSION) -> None:
    """Create `memo_vec` / `session_vec` at `dimension` with 024's helper (test setup only)."""
    with engine.begin() as connection:
        ensure_vector_tables(connection, dimension)


def _write_vectors(engine: Engine, table_name: str, sources: Mapping[int, str]) -> None:
    """Write one vector per id, each `embedding_vector(<its source text>, 8)`, via 024's writer."""
    with engine.begin() as connection:
        for row_id, source in sources.items():
            write_vector(connection, table_name, row_id, embedding_vector(source, DIMENSION))


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """Two users, three characters and three sessions — and **no** vec table, **no** designation.

    `create_all` alone leaves `memo_vec` / `session_vec` absent (they live outside
    `schema.metadata`), which DoD-6 and DoD-8 need; every other test opts in by calling
    `_ensure_vec_tables`. No model is designated here either, because "no designated model" is
    half of this step's contract (DoD-6).
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


def _memo_is_enabled(relation: FromClause) -> ColumnElement[bool]:
    """`026`'s shape, reduced to its enabled half."""
    return relation.c["is_enabled"].is_(True)


def _session_of_character(character_id: int) -> ExtraPredicateBuilder:
    """`027`'s shape: one character's sessions."""

    def builder(relation: FromClause) -> ColumnElement[bool]:
        return relation.c["character_id"] == character_id

    return builder


# --- calling the frozen interface --------------------------------------------------------


def _ranking(
    engine: Engine,
    table_name: str,
    scope: SearchScope,
    factory: FakeClientFactory,
    query_text: str = QUERY_TEXT,
    *,
    depth: int | None = None,
) -> list[int]:
    """Run the vector arm over `scope`'s candidate set. `depth` is keyword-only when given."""
    with engine.connect() as connection:
        if depth is None:
            return vector_ranking(connection, table_name, candidate_ids(scope), query_text, client_factory=factory)
        return vector_ranking(
            connection,
            table_name,
            candidate_ids(scope),
            query_text,
            depth=depth,
            client_factory=factory,
        )


# --- DoD-1: the ranking is ascending L2 distance to the query vector (D5) -----------------


def test_the_ranking_is_ordered_by_ascending_l2_distance__S025_003_DoD1(engine: Engine) -> None:
    """Four of one user's memos, ordered by the distance the test computes for itself."""
    sources = {
        MEMO_A_ONE: SOURCE_ONE,
        MEMO_A_TWO: SOURCE_TWO,
        MEMO_A_THREE: SOURCE_THREE,
        MEMO_A_FOUR: SOURCE_FOUR,
    }
    _insert_memos(engine, [(memo_id, USER_A, True) for memo_id in sources])
    _seed_designation(engine)
    _ensure_vec_tables(engine)
    _write_vectors(engine, MEMO_VEC_TABLE, sources)

    expected = _expected_ranking(QUERY_TEXT, sources)
    ranking = _ranking(engine, MEMO_VEC_TABLE, MemoSearchScope(user_id=USER_A), fake_factory(DIMENSION))

    # The expectation is only meaningful if the fake's vectors really do order the four rows.
    assert sorted(expected) == sorted(sources)
    assert len(expected) == 4
    assert ranking == expected


def test_every_ranked_id_is_the_exact_snowflake_id_written__S025_003_DoD1(engine: Engine) -> None:
    """The ids round-trip through the vec0 key column with no loss (ids above 2^60)."""
    sources = {MEMO_A_ONE: SOURCE_ONE, MEMO_A_TWO: SOURCE_TWO}
    _insert_memos(engine, [(memo_id, USER_A, True) for memo_id in sources])
    _seed_designation(engine)
    _ensure_vec_tables(engine)
    _write_vectors(engine, MEMO_VEC_TABLE, sources)

    ranking = _ranking(engine, MEMO_VEC_TABLE, MemoSearchScope(user_id=USER_A), fake_factory(DIMENSION))

    assert all(memo_id > SNOWFLAKE_FLOOR for memo_id in sources)
    assert sorted(ranking) == sorted(sources)
    assert ranking == _expected_ranking(QUERY_TEXT, sources)


# --- DoD-2: snowflake correctness at scale (024 D3) ---------------------------------------


def test_no_true_candidate_is_missing_at_snowflake_ids__S025_003_DoD2(engine: Engine) -> None:
    """The single most load-bearing test in this step.

    200 candidates and 200 non-candidates, ids above 2^60, spread with a prime stride and
    **interleaved** so no range separates the sets; every one of the 400 rows has a vector; and
    `depth` (25) is far smaller than the candidate count. For each of several distinct query
    texts the ranking must equal the brute-force top-`depth` computed over the **candidates
    only** — the defect 024 D3 measured (a pushed-down KNN silently dropping true candidates at
    large ids) shows up here as a missing or mis-ordered candidate.
    """
    candidate_sources = {memo_id: _source_text(memo_id) for memo_id in BULK_CANDIDATE_IDS}
    other_sources = {memo_id: _source_text(memo_id) for memo_id in BULK_OTHER_IDS}
    _insert_memos(
        engine,
        [(memo_id, USER_A, True) for memo_id in BULK_CANDIDATE_IDS]
        + [(memo_id, USER_B, True) for memo_id in BULK_OTHER_IDS],
    )
    _seed_designation(engine)
    _ensure_vec_tables(engine)
    _write_vectors(engine, MEMO_VEC_TABLE, candidate_sources)
    _write_vectors(engine, MEMO_VEC_TABLE, other_sources)

    assert len(BULK_CANDIDATE_IDS) >= 200
    assert len(BULK_OTHER_IDS) >= 200
    assert BULK_DEPTH < len(BULK_CANDIDATE_IDS)
    assert min(BULK_CANDIDATE_IDS + BULK_OTHER_IDS) > SNOWFLAKE_FLOOR

    for query_text in BULK_QUERY_TEXTS:
        expected = _expected_ranking(query_text, candidate_sources, BULK_DEPTH)
        ranking = _ranking(
            engine,
            MEMO_VEC_TABLE,
            MemoSearchScope(user_id=USER_A),
            fake_factory(DIMENSION),
            query_text,
            depth=BULK_DEPTH,
        )

        assert len(expected) == BULK_DEPTH
        assert ranking == expected, f"the ranking diverged from brute force for {query_text!r}"
        assert set(ranking).isdisjoint(BULK_OTHER_IDS)


def test_a_nearer_non_candidate_does_not_displace_a_candidate__S025_003_DoD2(engine: Engine) -> None:
    """The same 400 rows, checked to be a *discriminating* fixture.

    At least one query must have a non-candidate strictly nearer than the furthest kept
    candidate — otherwise filtering-after-ranking would pass DoD-2 by accident. The kept set is
    still exactly the candidate-only top-`depth`.
    """
    candidate_sources = {memo_id: _source_text(memo_id) for memo_id in BULK_CANDIDATE_IDS}
    other_sources = {memo_id: _source_text(memo_id) for memo_id in BULK_OTHER_IDS}
    _insert_memos(
        engine,
        [(memo_id, USER_A, True) for memo_id in BULK_CANDIDATE_IDS]
        + [(memo_id, USER_B, True) for memo_id in BULK_OTHER_IDS],
    )
    _seed_designation(engine)
    _ensure_vec_tables(engine)
    _write_vectors(engine, MEMO_VEC_TABLE, candidate_sources)
    _write_vectors(engine, MEMO_VEC_TABLE, other_sources)

    discriminating = 0
    for query_text in BULK_QUERY_TEXTS:
        query = embedding_vector(query_text, DIMENSION)
        expected = _expected_ranking(query_text, candidate_sources, BULK_DEPTH)
        worst_kept = _l2(embedding_vector(candidate_sources[expected[-1]], DIMENSION), query)
        nearer_outsiders = [
            memo_id
            for memo_id, source in other_sources.items()
            if _l2(embedding_vector(source, DIMENSION), query) < worst_kept
        ]
        if nearer_outsiders:
            discriminating += 1
            ranking = _ranking(
                engine,
                MEMO_VEC_TABLE,
                MemoSearchScope(user_id=USER_A),
                fake_factory(DIMENSION),
                query_text,
                depth=BULK_DEPTH,
            )
            assert ranking == expected
            assert set(ranking).isdisjoint(nearer_outsiders)

    assert discriminating > 0


# --- DoD-3: ids outside the candidate set never appear, even at distance 0 (D5, D6) --------


def test_another_users_exact_match_is_absent_from_the_memo_ranking__S025_003_DoD3(engine: Engine) -> None:
    """The other owner's vector **equals the query vector exactly**, so its distance is 0.

    It can only be absent if the candidate restriction was applied *before* the ranking (D5).
    """
    candidate_sources = {MEMO_A_ONE: SOURCE_ONE, MEMO_A_TWO: SOURCE_TWO}
    _insert_memos(
        engine,
        [(MEMO_A_ONE, USER_A, True), (MEMO_A_TWO, USER_A, True), (MEMO_B_EXACT, USER_B, True)],
    )
    _seed_designation(engine)
    _ensure_vec_tables(engine)
    _write_vectors(engine, MEMO_VEC_TABLE, {**candidate_sources, MEMO_B_EXACT: QUERY_TEXT})

    ranking = _ranking(engine, MEMO_VEC_TABLE, MemoSearchScope(user_id=USER_A), fake_factory(DIMENSION))

    assert MEMO_B_EXACT not in ranking
    assert ranking == _expected_ranking(QUERY_TEXT, candidate_sources)


def test_a_memo_excluded_by_the_extra_predicate_is_absent_at_distance_zero__S025_003_DoD3(
    engine: Engine,
) -> None:
    """Same owner, disabled, vector **equal to the query vector** — still absent."""
    candidate_sources = {MEMO_A_ONE: SOURCE_ONE, MEMO_A_TWO: SOURCE_TWO}
    _insert_memos(
        engine,
        [
            (MEMO_A_ONE, USER_A, True),
            (MEMO_A_TWO, USER_A, True),
            (MEMO_A_DISABLED_EXACT, USER_A, False),
            (MEMO_B_EXACT, USER_B, True),
        ],
    )
    _seed_designation(engine)
    _ensure_vec_tables(engine)
    _write_vectors(
        engine,
        MEMO_VEC_TABLE,
        {**candidate_sources, MEMO_A_DISABLED_EXACT: QUERY_TEXT, MEMO_B_EXACT: QUERY_TEXT},
    )

    scope = MemoSearchScope(user_id=USER_A, extra_predicate=_memo_is_enabled)
    ranking = _ranking(engine, MEMO_VEC_TABLE, scope, fake_factory(DIMENSION))

    assert MEMO_A_DISABLED_EXACT not in ranking
    assert MEMO_B_EXACT not in ranking
    assert ranking == _expected_ranking(QUERY_TEXT, candidate_sources)


# --- DoD-4: the same holds for `session_vec` (U1, US-085) ---------------------------------


def test_the_session_ranking_is_only_the_scope_users_sessions__S025_003_DoD4(engine: Engine) -> None:
    """`session_vec` over the session variant: the other owner's exact match is absent."""
    candidate_sources = {SESSION_A1: SOURCE_ONE, SESSION_A2: SOURCE_TWO}
    _seed_designation(engine)
    _ensure_vec_tables(engine)
    _write_vectors(engine, SESSION_VEC_TABLE, {**candidate_sources, SESSION_B1: QUERY_TEXT})

    ranking = _ranking(engine, SESSION_VEC_TABLE, SessionSearchScope(user_id=USER_A), fake_factory(DIMENSION))

    assert SESSION_B1 not in ranking
    assert ranking == _expected_ranking(QUERY_TEXT, candidate_sources)


def test_the_session_ranking_honours_the_character_extra_predicate__S025_003_DoD4(engine: Engine) -> None:
    """One character's sessions only.

    `SESSION_A2` is the same owner's *other* character (dropped by the extra predicate) and
    `SESSION_B2` is the other owner's session under **`USER_A`'s** character, so it satisfies the
    extra predicate and only the owner predicate can drop it. Both carry the query vector
    exactly, so both would rank first if either filter were missing.
    """
    _insert_session(engine, session_id=SESSION_B2, user_id=USER_B, character_id=CHARACTER_A1)
    candidate_sources = {SESSION_A1: SOURCE_ONE}
    _seed_designation(engine)
    _ensure_vec_tables(engine)
    _write_vectors(
        engine,
        SESSION_VEC_TABLE,
        {
            **candidate_sources,
            SESSION_A2: QUERY_TEXT,
            SESSION_B1: QUERY_TEXT,
            SESSION_B2: QUERY_TEXT,
        },
    )

    scope = SessionSearchScope(user_id=USER_A, extra_predicate=_session_of_character(CHARACTER_A1))
    ranking = _ranking(engine, SESSION_VEC_TABLE, scope, fake_factory(DIMENSION))

    assert ranking == [SESSION_A1]
    assert SESSION_A2 not in ranking
    assert SESSION_B1 not in ranking
    assert SESSION_B2 not in ranking


# --- DoD-5: depth caps; a vectorless candidate is skipped; an empty table is empty (U2) ----


def test_depth_caps_the_ranking__S025_003_DoD5(engine: Engine) -> None:
    sources = {memo_id: _source_text(memo_id) for memo_id in MEMO_CAP_IDS}
    _insert_memos(engine, [(memo_id, USER_A, True) for memo_id in MEMO_CAP_IDS])
    _seed_designation(engine)
    _ensure_vec_tables(engine)
    _write_vectors(engine, MEMO_VEC_TABLE, sources)

    ranking = _ranking(
        engine,
        MEMO_VEC_TABLE,
        MemoSearchScope(user_id=USER_A),
        fake_factory(DIMENSION),
        depth=CAP_DEPTH,
    )

    assert len(MEMO_CAP_IDS) > CAP_DEPTH
    assert len(ranking) == CAP_DEPTH
    assert len(set(ranking)) == CAP_DEPTH
    assert ranking == _expected_ranking(QUERY_TEXT, sources, CAP_DEPTH)


def test_a_candidate_without_a_vector_row_is_simply_not_ranked__S025_003_DoD5(engine: Engine) -> None:
    """No error: the candidate with no vector row is just missing from the ranking."""
    sources = {MEMO_A_ONE: SOURCE_ONE, MEMO_A_TWO: SOURCE_TWO}
    _insert_memos(
        engine,
        [(MEMO_A_ONE, USER_A, True), (MEMO_A_TWO, USER_A, True), (MEMO_A_WITHOUT_VECTOR, USER_A, True)],
    )
    _seed_designation(engine)
    _ensure_vec_tables(engine)
    _write_vectors(engine, MEMO_VEC_TABLE, sources)

    ranking = _ranking(engine, MEMO_VEC_TABLE, MemoSearchScope(user_id=USER_A), fake_factory(DIMENSION))

    assert MEMO_A_WITHOUT_VECTOR not in ranking
    assert ranking == _expected_ranking(QUERY_TEXT, sources)


def test_an_empty_but_present_vec_table_returns_no_ranking__S025_003_DoD5(engine: Engine) -> None:
    """The table exists at the designated width and holds no row; candidates do exist."""
    _insert_memos(engine, [(MEMO_A_ONE, USER_A, True), (MEMO_A_TWO, USER_A, True)])
    _seed_designation(engine)
    _ensure_vec_tables(engine)

    with engine.connect() as connection:
        assert vector_table_dimension(connection, MEMO_VEC_TABLE) == DIMENSION

    assert _ranking(engine, MEMO_VEC_TABLE, MemoSearchScope(user_id=USER_A), fake_factory(DIMENSION)) == []
    assert _ranking(engine, SESSION_VEC_TABLE, SessionSearchScope(user_id=USER_A), fake_factory(DIMENSION)) == []


# --- DoD-6: no designated model always raises, and does no vector work (U2, R4) ------------


def test_no_designated_model_raises_and_builds_no_client__S025_003_DoD6(engine: Engine) -> None:
    """The vec table is present and populated, so only the missing designation can raise."""
    _insert_memos(engine, [(MEMO_A_ONE, USER_A, True)])
    _ensure_vec_tables(engine)
    _write_vectors(engine, MEMO_VEC_TABLE, {MEMO_A_ONE: SOURCE_ONE})
    factory = fake_factory(DIMENSION)

    with pytest.raises(NoEmbeddingModelError):
        _ranking(engine, MEMO_VEC_TABLE, MemoSearchScope(user_id=USER_A), factory)

    assert factory.call_count == 0
    assert factory.embed_calls == []


def test_no_designated_model_raises_even_with_the_vec_table_absent__S025_003_DoD6(engine: Engine) -> None:
    """Model first, table second: an instance without `memo_vec` still raises, never degrades."""
    _insert_memos(engine, [(MEMO_A_ONE, USER_A, True)])
    factory = fake_factory(DIMENSION)

    with engine.connect() as connection:
        assert vector_table_dimension(connection, MEMO_VEC_TABLE) is None

    with pytest.raises(NoEmbeddingModelError):
        _ranking(engine, MEMO_VEC_TABLE, MemoSearchScope(user_id=USER_A), factory)

    assert factory.call_count == 0
    assert factory.embed_calls == []


def test_an_undesignated_model_row_still_raises__S025_003_DoD6(engine: Engine) -> None:
    """A registry row that is enabled but **not** designated is not a substitute (R4)."""
    _insert_memos(engine, [(MEMO_A_ONE, USER_A, True)])
    _seed_designation(engine, is_designated=False)
    _ensure_vec_tables(engine)
    _write_vectors(engine, MEMO_VEC_TABLE, {MEMO_A_ONE: SOURCE_ONE})
    factory = fake_factory(DIMENSION)

    with pytest.raises(NoEmbeddingModelError):
        _ranking(engine, MEMO_VEC_TABLE, MemoSearchScope(user_id=USER_A), factory)

    assert factory.call_count == 0


# --- DoD-7: the provider's own failure propagates unchanged (U2) ---------------------------


def test_an_unreachable_provider_propagates_its_error__S025_003_DoD7(engine: Engine) -> None:
    _insert_memos(engine, [(MEMO_A_ONE, USER_A, True)])
    _seed_designation(engine)
    _ensure_vec_tables(engine)
    _write_vectors(engine, MEMO_VEC_TABLE, {MEMO_A_ONE: SOURCE_ONE})
    factory = unreachable_factory(DIMENSION)

    with pytest.raises(LlmUnreachableError):
        _ranking(engine, MEMO_VEC_TABLE, MemoSearchScope(user_id=USER_A), factory)

    # The fake records the call before raising, so the arm really did reach the embed step.
    assert len(factory.embed_calls) == 1


# --- DoD-8: an absent vec table is empty, and costs no provider call (U2) ------------------


def test_an_absent_vec_table_returns_no_ranking_and_embeds_nothing__S025_003_DoD8(engine: Engine) -> None:
    """A designated model exists but `memo_vec` / `session_vec` do not.

    The table check therefore sits **after** opening the model and **before** embedding.
    """
    _insert_memos(engine, [(MEMO_A_ONE, USER_A, True), (MEMO_A_TWO, USER_A, True)])
    _seed_designation(engine)
    factory = fake_factory(DIMENSION)

    with engine.connect() as connection:
        assert vector_table_dimension(connection, MEMO_VEC_TABLE) is None
        assert vector_table_dimension(connection, SESSION_VEC_TABLE) is None

    assert _ranking(engine, MEMO_VEC_TABLE, MemoSearchScope(user_id=USER_A), factory) == []
    assert _ranking(engine, SESSION_VEC_TABLE, SessionSearchScope(user_id=USER_A), factory) == []
    assert factory.embed_calls == []


# --- DoD-9: the pre-embed table-vs-designation width guard (024 D8) ------------------------


def test_a_table_narrower_than_the_designation_raises_dimension_mismatch__S025_003_DoD9(
    engine: Engine,
) -> None:
    """Table at 8, model designated at 16.

    The guard must raise `NoEmbeddingModelError` with exactly `{"reason": "dimension_mismatch"}`
    **before** embedding, so sqlite-vec never sees mismatched widths (it would raise its own raw
    `Vector dimension mistmatch` error instead).
    """
    _insert_memos(engine, [(MEMO_A_ONE, USER_A, True)])
    _seed_designation(engine, dim=OTHER_DIMENSION)
    _ensure_vec_tables(engine, DIMENSION)
    factory = fake_factory(OTHER_DIMENSION)

    with engine.connect() as connection:
        assert vector_table_dimension(connection, MEMO_VEC_TABLE) == DIMENSION

    with pytest.raises(NoEmbeddingModelError) as raised:
        _ranking(engine, MEMO_VEC_TABLE, MemoSearchScope(user_id=USER_A), factory)

    assert raised.value.code == "no_embedding_model"
    assert raised.value.detail == {"reason": "dimension_mismatch"}
    assert factory.embed_calls == []
    # The class has no default message (024 `001.context.md`), so the raise site passes a fixed one.
    assert isinstance(raised.value.message, str)
    assert raised.value.message != ""


# --- DoD-10: exactly one embed call, the designated model, the one query text (024 D1) ----


def test_exactly_one_embed_call_carries_the_model_and_the_query__S025_003_DoD10(engine: Engine) -> None:
    sources = {MEMO_A_ONE: SOURCE_ONE, MEMO_A_TWO: SOURCE_TWO}
    _insert_memos(engine, [(memo_id, USER_A, True) for memo_id in sources])
    _seed_designation(engine)
    _ensure_vec_tables(engine)
    _write_vectors(engine, MEMO_VEC_TABLE, sources)
    factory = fake_factory(DIMENSION)

    ranking = _ranking(engine, MEMO_VEC_TABLE, MemoSearchScope(user_id=USER_A), factory)

    assert ranking == _expected_ranking(QUERY_TEXT, sources)
    assert factory.embed_calls == [(MODEL_NAME, (QUERY_TEXT,))]


# --- DoD-11: the forbidden KNN operator and the web framework are absent (024 D3) ----------


def _module_source() -> str:
    return inspect.getsource(vector_module)


def test_the_vector_module_contains_no_match_operator__S025_003_DoD11() -> None:
    """A plain substring scan, exactly as the DoD clause words it.

    `MATCH` is the vec0 nearest-neighbour operator, and the pushed-down KNN form that silently
    drops true candidates above ~2^50 (024 D3) cannot be written without it. The exact scan
    `003.context.md` fixes uses no `MATCH` at all.
    """
    assert "MATCH" not in _module_source()


def test_the_vector_module_imports_no_fastapi__S025_003_DoD11() -> None:
    """An AST import walk: no `fastapi` (or its `starlette` base) import anywhere."""
    imported: list[str] = []
    for node in ast.walk(ast.parse(_module_source())):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)

    offenders = [name for name in imported if name.split(".")[0] in {"fastapi", "starlette"}]
    assert offenders == []


def test_the_vector_module_binds_no_fastapi_symbol__S025_003_DoD11() -> None:
    """No module-level name is a fastapi/starlette object."""
    offenders = []
    for name, value in vars(vector_module).items():
        origin = getattr(value, "__module__", None) or getattr(value, "__name__", "")
        if isinstance(origin, str) and origin.split(".")[0] in {"fastapi", "starlette"}:
            offenders.append(name)

    assert offenders == []
