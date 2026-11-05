"""`services/search/my_search.py` — feature 029, step 002 (DoD-1..12).

Every expected value comes from the **spec**, never from the implementation:
`docs/plans/029.my-search/002.my-search-orchestrator.md` (Interface intent and Definition of
done), `002.context.md` (the hydration statements, the port-call notes and the seeding notes)
and the feature `context.md` — **U1** (an embedding failure fails the whole search), **U2** (no
flag predicate on memos), **U3** (archived rows are included and flagged), **D1** (five fixed
groups; a blank query opens no model), **D2** (the per-kind cap is `20`; sessions, entries and
memos keep the port's order), **D4** (hydration, and a port hit missing from its hydration read
is dropped), **D5** (fail-whole), **D6** (read posture), **R5**, **R11** and the wire contract
(`scope_id` is **null for `"user"`**; `character_id` is the character page the note routes to).

Bindings come from `## Skeleton` → "Step 002 — frozen interface (2026-10-05)" in `status.md`
(and "Step 001" for the cap):

    MY_SEARCH_PER_KIND_LIMIT: Final[int] = 20
    SessionHit(id, character_name, setup_name: str | None, name: str | None, created_at: str, archived)
    EntryHit(id, session_id, snippet, character_name, session_name: str | None, session_created_at: str)
    MemoHit(id, scope: MemoScope, scope_id: int | None, character_id: int | None, snippet, is_enabled)
    MySearchResults(characters, setups, sessions, entries, memos)
    run_my_search(connection, user_id, query_text, *, client_factory=LlmClient,
                  timeout_seconds=DEFAULT_EMBED_TIMEOUT_SECONDS) -> MySearchResults

Timestamps are `str`, the fixed-width UTC text form the rows are seeded with — no `datetime`
and no parsing. The three hydration helpers are **private** and nothing here binds to them.

How the expectations are derived
--------------------------------
Nothing here asks the code under test what the answer is.

* **The port is never mocked and nothing is monkeypatched.** The search tables are the real
  ones, created only through 024's `ensure_fts_tables` / `ensure_vector_tables` at dimension 8;
  vectors are written only through 024's `write_vector` from `tests/llm_fakes.py`'s pure
  `embedding_vector(text, dim)`; a designated model is a raw `llm_servers` + `models` pair with
  `api_key_ref=None`; the provider arrives through the frozen `client_factory=` seam.
* **A row meant to match carries the token in its text *and* the fake's vector of the query
  text**, so both of the port's arms reach it and a distance of zero is the best any row can
  score. An absence is therefore the owner predicate's or the corpus boundary's work, never a
  needle or a vector that missed.
* **Owner isolation is proved with twins** (`context.md` cross-cutting constraints): B's rows
  carry the same names, the same texts, the same bodies and the **same** vectors as A's.
* **Order is asserted only where the spec defines it.** The five groups' order is
  `MySearchResults`' field order (the freeze, US-075.AC-1). Within the memo group, D2 says the
  port's order is kept, and DoD-8 is written both ways the step file allows: once as a
  vector-derived prefix that no distance metric can disagree about (the sole zero-distance row
  comes first, the lexical arm contributing nothing at all), and once as the port's own answer
  to exactly the call step 002's Interface intent specifies — 025 is delivered code and is not
  the code under test. Nothing asserts a fused score or a tie order.
* **DoD-12's two halves need two mechanisms** (`## Ultra phase`, "Notes carried from the
  skeletons"): `fastapi` is checked through the **AST**, because the module's frozen docstring
  legitimately contains the word; `is_forced` is checked as **source text**, because the token
  may appear nowhere at all — not in code, not in a comment, not in a docstring.

Each test name ends `__S029_002_DoD<n>` with the DoD item it covers.

Feature 034, step 003 (session names in my-search)
--------------------------------------------------
The later block of this module covers `docs/plans/034.session-names/003.my-search-names.md`
DoD-1..DoD-9 (DEC-034-8, DEC-arch-session-names-5), each test ending `__S034_003_DoD<n>`.
The two shapes above carry `SessionHit.name` and `EntryHit.session_name` (step 003's frozen
record), and the step adds two bindings:

    search_session_names(connection, user_id, query_text, limit=MY_SEARCH_PER_KIND_LIMIT) -> list[int]
    merge_session_hits(name_ids, vector_hits: Sequence[SearchHit], limit) -> list[int]

A session reachable **only** through the name arm is seeded with no `session_vec` row: the
session corpus is vector-only, so such a session in the sessions group can only have come from
the name match. Where the vector arm's order matters, the expectation is the port's own answer
to the session-scope call (as DoD-8 above does for memos) — 025 is delivered code, not the code
under test.

Mechanics (`context.md` "Test conventions"): a real SQLite file per test through the shared
`db_engine` fixture (`tests/conftest.py` and `tests/llm_fakes.py` are untouched), raw inserts
only, ids above 2^60, two users A and B, and every other helper file-local.
"""

import ast
import dataclasses
import inspect
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, Table, event, select

from app.db import schema
from app.db.search_tables import MEMO_VEC_TABLE, SESSION_VEC_TABLE, ensure_fts_tables, ensure_vector_tables
from app.errors import LlmUnreachableError, NoEmbeddingModelError
from app.roles import Role
from app.services.embedding import write_vector
from app.services.search import my_search as my_search_module
from app.services.search.hybrid import search as port_search
from app.services.search.my_search import (
    MY_SEARCH_PER_KIND_LIMIT,
    EntryHit,
    MemoHit,
    MySearchResults,
    SessionHit,
    merge_session_hits,
    run_my_search,
    search_session_names,
)
from app.services.search.ports import MemoSearchScope, SearchHit, SessionSearchScope
from tests.llm_fakes import FakeClientFactory, embedding_vector, fake_factory, unreachable_factory

#: The seeded instant, in the project's fixed-width UTC text form.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

#: The instant rows seeded already settled carry.
SEEDED_SETTLED_AT = "2025-12-31T00:00:00.000000+00:00"

#: Every id below is above 2^60 = 1152921504606846976 (snowflake-sized).
SNOWFLAKE_FLOOR = 2**60

#: The designated embedding width throughout; 8 is what 024 and 025 use.
DIMENSION = 8

#: DoD-10's mismatch: the vector tables stay at `DIMENSION`, the designated model declares this.
MISMATCHED_DIMENSION = 16

#: D2's per-kind cap, written out as the **spec's** literal (the literals table).
EXPECTED_PER_KIND_CAP = 20

#: The searched term. Lower case, so FTS5's verbatim snippet text contains it as typed.
TOKEN = "kaelith"

USER_A = 1_291_000_000_000_000_001
USER_B = 1_291_000_000_000_000_002

CHAR_A1 = 1_291_000_000_000_000_101
CHAR_A2 = 1_291_000_000_000_000_102
CHAR_B1 = 1_291_000_000_000_000_103

SETUP_A1 = 1_291_000_000_000_000_151
SETUP_A2 = 1_291_000_000_000_000_152
SETUP_B1 = 1_291_000_000_000_000_153

SESSION_WITH_SETUP = 1_291_000_000_000_000_201
SESSION_NO_SETUP = 1_291_000_000_000_000_202
SESSION_ARCHIVED = 1_291_000_000_000_000_203
SESSION_B = 1_291_000_000_000_000_204

ENTRY_SETTLED = 1_291_000_000_000_000_301
ENTRY_ZONE = 1_291_000_000_000_000_302
ENTRY_BURIED = 1_291_000_000_000_000_303
ENTRY_B = 1_291_000_000_000_000_304

MEMO_USER = 1_291_000_000_000_000_401
MEMO_CHARACTER = 1_291_000_000_000_000_402
MEMO_SETUP = 1_291_000_000_000_000_403
MEMO_SESSION = 1_291_000_000_000_000_404
MEMO_B = 1_291_000_000_000_000_405

FLAG_ENABLED_FORCED = 1_291_000_000_000_000_501
FLAG_ENABLED_PLAIN = 1_291_000_000_000_000_502
FLAG_DISABLED_FORCED = 1_291_000_000_000_000_503
FLAG_DISABLED_PLAIN = 1_291_000_000_000_000_504

SERVER_ID = 1_291_000_000_000_000_901
MODEL_ID = 1_291_000_000_000_000_902

BASE_URL = "http://embedding.test:8080/v1"
MODEL_NAME = "the-designated-embedding-model"

#: DoD-8's twenty-five notes, and the twenty-five characters of its companion clause.
CAP_MEMO_BASE = 1_291_000_000_000_000_601
CAP_MEMO_COUNT = 25
CAP_MEMO_EXACT_OFFSET = 7
CAP_MEMO_IDS = tuple(CAP_MEMO_BASE + offset for offset in range(CAP_MEMO_COUNT))

CAP_CHARACTER_BASE = 1_291_000_000_000_000_701
CAP_CHARACTER_COUNT = 25
CAP_CHARACTER_IDS = tuple(CAP_CHARACTER_BASE + offset for offset in range(CAP_CHARACTER_COUNT))

# --- the seeded texts ------------------------------------------------------------------------

CHARACTER_NAME = "Kaelith"
UNDERSTUDY_NAME = "the understudy"
PERSONA = "The lamplighter who keeps the tide-beacons of the drowned coast."
SETUP_NAME = f"{CHARACTER_NAME}'s observatory"
SPARE_SETUP_NAME = "the spare stage"
SETUP_DESCRIPTION = "The drowned observatory, three nights after the spring tide."

SETTLED_TEXT = f"the {TOKEN} beacon stayed lit until the tide turned"

#: The two rows outside the record, each carrying the token **and** its own marker word, so
#: their absence from the entry group is the corpus boundary's work (R11).
ZONE_MARKER = "zonemarker"
BURIED_MARKER = "buriedmarker"
ZONE_TEXT = f"a draft about {TOKEN} and the {ZONE_MARKER}"
BURIED_TEXT = f"an aside about {TOKEN} and the {BURIED_MARKER}"

#: Each session carries its own `created_at`, so hydration cannot pass the wrong one unnoticed.
CREATED_WITH_SETUP = "2026-02-01T00:00:00.000000+00:00"
CREATED_NO_SETUP = "2026-02-02T00:00:00.000000+00:00"
CREATED_ARCHIVED = "2026-02-03T00:00:00.000000+00:00"
CREATED_OTHER_OWNER = "2026-02-04T00:00:00.000000+00:00"

A_SESSION_IDS = (SESSION_WITH_SETUP, SESSION_NO_SETUP, SESSION_ARCHIVED)
A_MEMO_IDS = (MEMO_USER, MEMO_CHARACTER, MEMO_SETUP, MEMO_SESSION)


def _memo_body(marker: str) -> str:
    """A note body holding the token, so the lexical arm reaches it too."""
    return f"{TOKEN} remembers the {marker}"


# --- raw-insert helpers (file-local; no service is used to seed) -----------------------------


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


def _insert_character(
    engine: Engine,
    *,
    character_id: int,
    user_id: int = USER_A,
    name: str,
    sheet: str = "",
    archived_at: str | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.characters.insert().values(
                id=character_id,
                user_id=user_id,
                name=name,
                sheet=sheet,
                archived_at=archived_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_setup(
    engine: Engine,
    *,
    setup_id: int,
    character_id: int,
    user_id: int = USER_A,
    name: str,
    description: str = "",
    archived_at: str | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.setups.insert().values(
                id=setup_id,
                user_id=user_id,
                character_id=character_id,
                name=name,
                description=description,
                archived_at=archived_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_session(
    engine: Engine,
    *,
    session_id: int,
    user_id: int = USER_A,
    character_id: int = CHAR_A1,
    setup_id: int | None = None,
    archived_at: str | None = None,
    created_at: str = TIMESTAMP,
    name: str | None = None,
) -> None:
    """Raw-insert one `sessions` row; `name` stays NULL ("never renamed") unless given (034)."""
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.insert().values(
                id=session_id,
                user_id=user_id,
                character_id=character_id,
                setup_id=setup_id,
                last_used_at=TIMESTAMP,
                archived_at=archived_at,
                created_at=created_at,
                updated_at=TIMESTAMP,
                name=name,
            )
        )


def _insert_message(
    engine: Engine,
    *,
    message_id: int,
    session_id: int,
    body: str,
    user_id: int = USER_A,
    related_to: int | None = None,
    settled_at: str | None = SEEDED_SETTLED_AT,
) -> None:
    """Raw-insert one `messages` row.

    `settled_at` set with `related_to` null is a **record** row; `settled_at` null with
    `related_to` null is a current-zone row; `related_to` set is a buried row (and must leave
    `settled_at` null — the two are mutually exclusive in the schema).
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


def _insert_memo(
    engine: Engine,
    *,
    memo_id: int,
    scope: str,
    scope_id: int,
    body: str,
    user_id: int = USER_A,
    is_enabled: bool = True,
    forced: bool = False,
    sort_key: int = 0,
) -> None:
    """Raw-insert one `memos` row; `scope_id` is the **stored** id (the user id at user level).

    The flag 029 must never read is named `forced` on this helper's own keyword, so that the
    test file says what it seeds while the module under test stays free of the column name.
    """
    with engine.begin() as connection:
        connection.execute(
            schema.memos.insert().values(
                id=memo_id,
                user_id=user_id,
                scope=scope,
                scope_id=scope_id,
                body=body,
                is_enabled=is_enabled,
                is_forced=forced,
                sort_key=sort_key,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _seed_designation(engine: Engine, *, dimension: int = DIMENSION) -> None:
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
                embedding_dim=dimension,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _build_search_tables(engine: Engine, *, dimension: int = DIMENSION) -> None:
    """024's two helpers, after the rows: the FTS back-fill indexes what is already there."""
    with engine.begin() as connection:
        ensure_fts_tables(connection)
        ensure_vector_tables(connection, dimension)


def _write_vectors(
    engine: Engine,
    *,
    memos: Sequence[tuple[int, str]] = (),
    sessions: Sequence[tuple[int, str]] = (),
) -> None:
    """One vector row per pair, each `embedding_vector(<source text>, 8)`, via 024's writer."""
    with engine.begin() as connection:
        for row_id, source in memos:
            write_vector(connection, MEMO_VEC_TABLE, row_id, embedding_vector(source, DIMENSION))
        for row_id, source in sessions:
            write_vector(connection, SESSION_VEC_TABLE, row_id, embedding_vector(source, DIMENSION))


# --- seeds ----------------------------------------------------------------------------------


def _seed_characters_and_setups(engine: Engine) -> None:
    """One matching character and one matching setup, plus a non-matching pair.

    The setup-level note of DoD-4 lives on `SETUP_A2`, which hangs off `CHAR_A2` — so the
    setup level's `scope_id` and `character_id` are two different ids and cannot be confused.
    """
    _insert_character(engine, character_id=CHAR_A1, name=CHARACTER_NAME, sheet=PERSONA)
    _insert_character(engine, character_id=CHAR_A2, name=UNDERSTUDY_NAME, sheet="")
    _insert_setup(engine, setup_id=SETUP_A1, character_id=CHAR_A1, name=SETUP_NAME, description=SETUP_DESCRIPTION)
    _insert_setup(engine, setup_id=SETUP_A2, character_id=CHAR_A2, name=SPARE_SETUP_NAME, description="")


def _seed_sessions(engine: Engine) -> None:
    """Three of A's sessions: one with a setup, one without, one archived."""
    _insert_session(
        engine,
        session_id=SESSION_WITH_SETUP,
        setup_id=SETUP_A1,
        created_at=CREATED_WITH_SETUP,
    )
    _insert_session(engine, session_id=SESSION_NO_SETUP, setup_id=None, created_at=CREATED_NO_SETUP)
    _insert_session(
        engine,
        session_id=SESSION_ARCHIVED,
        setup_id=SETUP_A1,
        archived_at=TIMESTAMP,
        created_at=CREATED_ARCHIVED,
    )


def _seed_messages(engine: Engine) -> None:
    """One record row, one current-zone row and one buried row — all three holding the token."""
    _insert_message(engine, message_id=ENTRY_SETTLED, session_id=SESSION_WITH_SETUP, body=SETTLED_TEXT)
    _insert_message(
        engine,
        message_id=ENTRY_ZONE,
        session_id=SESSION_WITH_SETUP,
        body=ZONE_TEXT,
        settled_at=None,
    )
    _insert_message(
        engine,
        message_id=ENTRY_BURIED,
        session_id=SESSION_WITH_SETUP,
        body=BURIED_TEXT,
        related_to=ENTRY_SETTLED,
        settled_at=None,
    )


def _seed_level_memos(engine: Engine) -> None:
    """One of A's notes at each of the four levels."""
    _insert_memo(engine, memo_id=MEMO_USER, scope="user", scope_id=USER_A, body=_memo_body("aurelian"))
    _insert_memo(
        engine, memo_id=MEMO_CHARACTER, scope="character", scope_id=CHAR_A1, body=_memo_body("bellringer")
    )
    _insert_memo(engine, memo_id=MEMO_SETUP, scope="setup", scope_id=SETUP_A2, body=_memo_body("cindermoor"))
    _insert_memo(
        engine, memo_id=MEMO_SESSION, scope="session", scope_id=SESSION_WITH_SETUP, body=_memo_body("dawnwarden")
    )


def _seed_other_owner(engine: Engine) -> None:
    """B's five rows: the same names, texts, bodies and vectors as A's matching ones."""
    _insert_character(engine, character_id=CHAR_B1, user_id=USER_B, name=CHARACTER_NAME, sheet=PERSONA)
    _insert_setup(
        engine,
        setup_id=SETUP_B1,
        user_id=USER_B,
        character_id=CHAR_B1,
        name=SETUP_NAME,
        description=SETUP_DESCRIPTION,
    )
    _insert_session(
        engine,
        session_id=SESSION_B,
        user_id=USER_B,
        character_id=CHAR_B1,
        setup_id=SETUP_B1,
        created_at=CREATED_OTHER_OWNER,
    )
    _insert_message(engine, message_id=ENTRY_B, session_id=SESSION_B, body=SETTLED_TEXT, user_id=USER_B)
    _insert_memo(
        engine, memo_id=MEMO_B, scope="user", scope_id=USER_B, body=_memo_body("aurelian"), user_id=USER_B
    )


def _seed_everything(engine: Engine, *, other_owner: bool = False) -> None:
    """A's character, setup, three sessions, three message rows and four notes — then the index.

    Every row meant to match on the vector arm is given `embedding_vector(TOKEN, 8)`, the
    fake's vector of the query text, so it sits at distance zero. B's twins get the **same**
    vector, which is what makes DoD-7's absences the owner predicate's work.
    """
    _seed_characters_and_setups(engine)
    _seed_sessions(engine)
    _seed_messages(engine)
    _seed_level_memos(engine)
    if other_owner:
        _seed_other_owner(engine)
    _seed_designation(engine)
    _build_search_tables(engine)

    memo_vectors = [(memo_id, TOKEN) for memo_id in A_MEMO_IDS]
    session_vectors = [(session_id, TOKEN) for session_id in A_SESSION_IDS]
    if other_owner:
        memo_vectors.append((MEMO_B, TOKEN))
        session_vectors.append((SESSION_B, TOKEN))
    _write_vectors(engine, memos=memo_vectors, sessions=session_vectors)


# --- running the search ---------------------------------------------------------------------


def _run(
    engine: Engine,
    *,
    query_text: str = TOKEN,
    user_id: int = USER_A,
    factory: FakeClientFactory | None = None,
) -> MySearchResults:
    with engine.connect() as connection:
        return run_my_search(
            connection,
            user_id,
            query_text,
            client_factory=factory if factory is not None else fake_factory(DIMENSION),
        )


def _ids(hits: Sequence[Any]) -> list[int]:
    """Every hit's id, in the order given — the five hit values all carry an `id` field."""
    return [hit.id for hit in hits]


def _all_ids(results: MySearchResults) -> set[int]:
    groups = (results.characters, results.setups, results.sessions, results.entries, results.memos)
    return {hit.id for group in groups for hit in group}


def _assert_no_open_transaction(connection: Connection) -> None:
    assert not connection.in_transaction()
    transaction = connection.begin()
    transaction.rollback()


# --- fixtures -------------------------------------------------------------------------------


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """The schema and the two users A and B; every other row is seeded by the test itself.

    `create_all` leaves the search tables absent and designates nothing, so each test opts
    into exactly the index and the designation it needs.
    """
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="aster")
    _insert_user(db_engine, user_id=USER_B, username="briar")
    return db_engine


# --- DoD-1: every kind reachable from one query (US-074.AC-1, UC-058) -----------------------


def test_one_query_returns_a_hit_in_each_of_the_five_groups__S029_002_DoD1(engine: Engine) -> None:
    """A owns a character, a setup, sessions with a settled entry and notes at all four levels,
    each holding the token (and, for the vector-armed kinds, the fake's vector of it). One call
    reaches all five, each group naming the seeded id."""
    _seed_everything(engine)

    results = _run(engine)

    assert _ids(results.characters) == [CHAR_A1]
    assert _ids(results.setups) == [SETUP_A1]
    assert set(_ids(results.sessions)) == set(A_SESSION_IDS)
    assert _ids(results.entries) == [ENTRY_SETTLED]
    assert set(_ids(results.memos)) == set(A_MEMO_IDS)


# --- DoD-2: the five groups, in order (US-075.AC-1, UC-059) ---------------------------------


def test_the_result_exposes_the_five_groups_in_uc059_order__S029_002_DoD2() -> None:
    """US-075.AC-1: characters, setups, sessions, entries, memos — the value's field order."""
    assert [field.name for field in dataclasses.fields(MySearchResults)] == [
        "characters",
        "setups",
        "sessions",
        "entries",
        "memos",
    ]


def test_each_group_holds_only_its_own_kinds_ids__S029_002_DoD2(engine: Engine) -> None:
    """No kind's id leaks into another group, although the one query reaches all five kinds."""
    _seed_everything(engine)

    results = _run(engine)

    assert set(_ids(results.characters)) <= {CHAR_A1, CHAR_A2}
    assert set(_ids(results.setups)) <= {SETUP_A1, SETUP_A2}
    assert set(_ids(results.sessions)) <= set(A_SESSION_IDS)
    assert set(_ids(results.entries)) <= {ENTRY_SETTLED, ENTRY_ZONE, ENTRY_BURIED}
    assert set(_ids(results.memos)) <= set(A_MEMO_IDS)


# --- DoD-3: a note's state never filters it out (US-137.AC-1, US-137.AC-2 data, R3) ---------


FLAG_CASES = (
    (FLAG_ENABLED_FORCED, True, True, "ironquill"),
    (FLAG_ENABLED_PLAIN, True, False, "jessamine"),
    (FLAG_DISABLED_FORCED, False, True, "kestrelbane"),
    (FLAG_DISABLED_PLAIN, False, False, "lanternmere"),
)


def test_all_four_flag_combinations_are_returned_with_their_stored_state__S029_002_DoD3(engine: Engine) -> None:
    """US-137.AC-1: my-search applies the owner predicate only, so a disabled note and a forced
    note both come back; `is_enabled` reports what is stored and never filters."""
    _seed_characters_and_setups(engine)
    _seed_sessions(engine)
    for memo_id, is_enabled, forced, marker in FLAG_CASES:
        _insert_memo(
            engine,
            memo_id=memo_id,
            scope="session",
            scope_id=SESSION_WITH_SETUP,
            body=_memo_body(marker),
            is_enabled=is_enabled,
            forced=forced,
        )
    _seed_designation(engine)
    _build_search_tables(engine)
    _write_vectors(engine, memos=[(memo_id, TOKEN) for memo_id, _, _, _ in FLAG_CASES])

    results = _run(engine)

    assert {hit.id: hit.is_enabled for hit in results.memos} == {
        FLAG_ENABLED_FORCED: True,
        FLAG_ENABLED_PLAIN: True,
        FLAG_DISABLED_FORCED: False,
        FLAG_DISABLED_PLAIN: False,
    }


# --- DoD-4: the four levels and their routing ids (U4, D4, US-119) --------------------------


def test_a_memo_hit_names_its_level_and_the_page_it_routes_to__S029_002_DoD4(engine: Engine) -> None:
    """The wire contract: `scope_id` is **none** at the user level, the character's id at the
    character level, the setup's id at the setup level and the session's id at the session
    level; `character_id` is the character page the note routes to, or none."""
    _seed_everything(engine)

    results = _run(engine)

    by_id = {hit.id: (hit.scope, hit.scope_id, hit.character_id) for hit in results.memos}
    assert by_id[MEMO_USER] == ("user", None, None)
    assert by_id[MEMO_CHARACTER] == ("character", CHAR_A1, CHAR_A1)
    assert by_id[MEMO_SETUP] == ("setup", SETUP_A2, CHAR_A2)
    assert by_id[MEMO_SESSION] == ("session", SESSION_WITH_SETUP, None)


def test_the_user_levels_none_scope_id_is_not_a_missing_row__S029_002_DoD4(engine: Engine) -> None:
    """The stored `memos.scope_id` of a user-level note **is** the owner's own id, and the hit
    still carries none: the hit's `None` is the level, never a read that found nothing."""
    _seed_everything(engine)

    with engine.connect() as connection:
        stored = connection.execute(
            select(schema.memos.c.scope_id).where(schema.memos.c.id == MEMO_USER)
        ).scalar_one()
    assert stored == USER_A

    results = _run(engine)

    user_level = [hit for hit in results.memos if hit.id == MEMO_USER]
    assert [(hit.scope, hit.scope_id, hit.character_id) for hit in user_level] == [("user", None, None)]


def test_a_memo_hit_carries_no_title__S029_002_DoD4() -> None:
    """US-119: a note has no title anywhere, so the hit value declares none — the six frozen
    fields and nothing else."""
    assert [field.name for field in dataclasses.fields(MemoHit)] == [
        "id",
        "scope",
        "scope_id",
        "character_id",
        "snippet",
        "is_enabled",
    ]


# --- DoD-5: session hydration (D4, U3, US-068 shape) ----------------------------------------


def test_a_session_hit_carries_its_character_setup_start_and_archive_state__S029_002_DoD5(
    engine: Engine,
) -> None:
    """D4: the character name through an owner-scoped inner join, the setup name through an
    owner-scoped LEFT OUTER join (none when there is no setup), the session's own `created_at`
    as text, and `archived` from the **session's** own `archived_at` (U3)."""
    _seed_everything(engine)

    results = _run(engine)

    by_id = {hit.id: hit for hit in results.sessions}
    # 034/003 DoD-8: none of these three was ever renamed, so each carries `name` None.
    assert by_id[SESSION_WITH_SETUP] == SessionHit(
        id=SESSION_WITH_SETUP,
        character_name=CHARACTER_NAME,
        setup_name=SETUP_NAME,
        name=None,
        created_at=CREATED_WITH_SETUP,
        archived=False,
    )
    assert by_id[SESSION_NO_SETUP] == SessionHit(
        id=SESSION_NO_SETUP,
        character_name=CHARACTER_NAME,
        setup_name=None,
        name=None,
        created_at=CREATED_NO_SETUP,
        archived=False,
    )
    assert by_id[SESSION_ARCHIVED] == SessionHit(
        id=SESSION_ARCHIVED,
        character_name=CHARACTER_NAME,
        setup_name=SETUP_NAME,
        name=None,
        created_at=CREATED_ARCHIVED,
        archived=True,
    )


# --- DoD-6: entry hydration and the corpus boundary (D4, R11, UC-038, US-115) ---------------


def test_a_settled_entry_is_returned_with_its_session_and_character__S029_002_DoD6(engine: Engine) -> None:
    """D4: the message id, its session id, a snippet holding the token, the session's character
    name and the **session's** `created_at` — not the message's own timestamp."""
    _seed_everything(engine)

    results = _run(engine)

    by_id = {hit.id: hit for hit in results.entries}
    assert set(by_id) == {ENTRY_SETTLED}
    hit = by_id[ENTRY_SETTLED]
    assert hit.session_id == SESSION_WITH_SETUP
    assert TOKEN in hit.snippet.lower()
    assert hit.character_name == CHARACTER_NAME
    assert hit.session_created_at == CREATED_WITH_SETUP
    assert hit.session_name is None  # 034/003 DoD-8: the session was never renamed


def test_a_zone_row_and_a_buried_row_are_outside_the_entry_corpus__S029_002_DoD6(engine: Engine) -> None:
    """R11: entries come from the settled record only. Both excluded rows carry the token, so
    their absence is the corpus boundary's work and not a needle that missed."""
    _seed_everything(engine)

    results = _run(engine)

    returned = set(_ids(results.entries))
    assert ENTRY_ZONE not in returned
    assert ENTRY_BURIED not in returned
    snippets = "\n".join(hit.snippet for hit in results.entries).lower()
    assert ZONE_MARKER not in snippets
    assert BURIED_MARKER not in snippets


def test_an_entry_hit_carries_the_frozen_six_fields__S029_002_DoD6__S034_003_DoD8() -> None:
    """The hydrated entry value is exactly the wire contract's keys, in that order; 034/003
    (DEC-034-8) adds `session_name` next to `session_created_at`."""
    assert [field.name for field in dataclasses.fields(EntryHit)] == [
        "id",
        "session_id",
        "snippet",
        "character_name",
        "session_name",
        "session_created_at",
    ]


# --- DoD-7: owner isolation, every kind, as an absence (US-076.AC-1, UC-065, R5) ------------


def test_no_row_of_another_user_appears_in_any_group__S029_002_DoD7(engine: Engine) -> None:
    """R5: B's character, setup, session, settled entry and note all match A's query on every
    arm their kind runs — B's session carries the **same** vector as A's and B's note the same
    body and the same vector — and none of B's ids reaches any of A's five groups."""
    _seed_everything(engine, other_owner=True)

    results = _run(engine)

    assert _all_ids(results) & {CHAR_B1, SETUP_B1, SESSION_B, ENTRY_B, MEMO_B} == set()
    assert CHAR_A1 in _ids(results.characters)
    assert SETUP_A1 in _ids(results.setups)
    assert SESSION_WITH_SETUP in _ids(results.sessions)
    assert ENTRY_SETTLED in _ids(results.entries)
    assert MEMO_USER in _ids(results.memos)


def test_the_other_user_finds_only_their_own_rows__S029_002_DoD7(engine: Engine) -> None:
    """The twins are reachable — by their owner — so the absence above is not missing data."""
    _seed_everything(engine, other_owner=True)

    results = _run(engine, user_id=USER_B)

    assert _ids(results.characters) == [CHAR_B1]
    assert _ids(results.setups) == [SETUP_B1]
    assert _ids(results.sessions) == [SESSION_B]
    assert _ids(results.entries) == [ENTRY_B]
    assert _ids(results.memos) == [MEMO_B]


# --- DoD-8: the port's order is kept, and the cap (D2) --------------------------------------


def _cap_memo_body(offset: int) -> str:
    """Deliberately **without** the token, so the lexical arm contributes no ranking at all."""
    return f"a plain note number {offset:02d}"


def _cap_vector_source(offset: int) -> str:
    """The one note at `CAP_MEMO_EXACT_OFFSET` is given the fake's vector of the query text."""
    return TOKEN if offset == CAP_MEMO_EXACT_OFFSET else f"unrelated source {offset:02d}"


def _seed_cap_memos(engine: Engine) -> None:
    for offset in range(CAP_MEMO_COUNT):
        _insert_memo(
            engine,
            memo_id=CAP_MEMO_IDS[offset],
            scope="user",
            scope_id=USER_A,
            body=_cap_memo_body(offset),
        )
    _seed_designation(engine)
    _build_search_tables(engine)
    _write_vectors(
        engine,
        memos=[(CAP_MEMO_IDS[offset], _cap_vector_source(offset)) for offset in range(CAP_MEMO_COUNT)],
    )


def test_the_memo_group_is_capped_and_led_by_the_zero_distance_note__S029_002_DoD8(engine: Engine) -> None:
    """D2: twenty-five notes carry a vector, exactly `MY_SEARCH_PER_KIND_LIMIT` come back, and
    the leader is the vector-derived one.

    No body holds the token, so the lexical arm ranks nothing and the fused order is the vector
    ranking alone. Exactly one note's stored vector **is** `embedding_vector(TOKEN, 8)`, the
    vector of the query text itself, so it sits at distance zero — the minimum under any
    distance metric — and leads. No further position is claimed.
    """
    assert CAP_MEMO_COUNT > EXPECTED_PER_KIND_CAP
    _seed_cap_memos(engine)

    returned = _ids(_run(engine).memos)

    assert len(returned) == EXPECTED_PER_KIND_CAP
    assert len(set(returned)) == len(returned)
    assert set(returned) <= set(CAP_MEMO_IDS)
    assert returned[0] == CAP_MEMO_IDS[CAP_MEMO_EXACT_OFFSET]


def test_the_memo_group_is_in_the_ports_own_order__S029_002_DoD8(engine: Engine) -> None:
    """D2: "sessions, entries and memos keep the port's order".

    The expected order is 025's answer to exactly the call step 002's Interface intent
    specifies — a memo scope built from the user id alone with **no** extra predicate, the
    query text, and the cap as `limit`. 025 is delivered code, not the code under test, so this
    is the spec's sentence written out rather than a value read off 029's implementation.
    """
    _seed_cap_memos(engine)

    with engine.connect() as connection:
        expected = port_search(
            connection,
            MemoSearchScope(user_id=USER_A),
            TOKEN,
            MY_SEARCH_PER_KIND_LIMIT,
            client_factory=fake_factory(DIMENSION),
        )

    returned = _ids(_run(engine).memos)

    assert returned == [hit.id for hit in expected]


def test_the_character_group_is_capped_too__S029_002_DoD8(engine: Engine) -> None:
    """D2: the cap is per kind, and the LIKE corpora are capped by the same constant."""
    for offset in range(CAP_CHARACTER_COUNT):
        _insert_character(
            engine,
            character_id=CAP_CHARACTER_IDS[offset],
            name=f"{CHARACTER_NAME} understudy {offset:02d}",
        )
    _seed_designation(engine)
    _build_search_tables(engine)

    returned = _ids(_run(engine).characters)

    assert len(returned) == EXPECTED_PER_KIND_CAP
    assert set(returned) <= set(CAP_CHARACTER_IDS)


# --- DoD-9: a blank query opens no model (D1) ----------------------------------------------


@pytest.mark.parametrize("query_text", ["", "   "])
def test_a_blank_query_returns_five_empty_groups_and_opens_no_model__S029_002_DoD9(
    engine: Engine, query_text: str
) -> None:
    """D1: a blank or whitespace-only query answers five empty lists, and the fake factory
    records **zero** constructions and zero embed calls — no model was opened at all."""
    _seed_everything(engine)
    factory = fake_factory(DIMENSION)

    results = _run(engine, query_text=query_text, factory=factory)

    assert results.characters == []
    assert results.setups == []
    assert results.sessions == []
    assert results.entries == []
    assert results.memos == []
    assert factory.call_count == 0
    assert factory.embed_calls == []


# --- DoD-10: an embedding failure fails the whole search (U1, D5) ---------------------------


def _seed_matching_character_and_tables(engine: Engine, *, dimension: int | None = None) -> None:
    """A matching character, then the vector tables — created **first**, so the expected raise
    never depends on 025's internal ordering of "open the model" versus "table absent".

    `dimension` is the **designated model's** `embedding_dim`; `None` designates nothing. The
    vector tables are always built at `DIMENSION`.
    """
    _insert_character(engine, character_id=CHAR_A1, name=CHARACTER_NAME, sheet=PERSONA)
    if dimension is not None:
        _seed_designation(engine, dimension=dimension)
    _build_search_tables(engine)


def test_no_designated_model_fails_the_whole_search__S029_002_DoD10(engine: Engine) -> None:
    """U1: with no usable embedding model my-search answers nothing — not even the character
    name match that is sitting right there."""
    _seed_matching_character_and_tables(engine, dimension=None)

    with engine.connect() as connection:
        with pytest.raises(NoEmbeddingModelError) as raised:
            run_my_search(connection, USER_A, TOKEN, client_factory=fake_factory(DIMENSION))

    assert raised.value.code == "no_embedding_model"


def test_a_dimension_mismatch_fails_the_whole_search__S029_002_DoD10(engine: Engine) -> None:
    """U1: the vector tables are at dimension 8 and the designated model declares 16, so the
    error carries `detail` exactly `{"reason": "dimension_mismatch"}`, unchanged."""
    _seed_matching_character_and_tables(engine, dimension=MISMATCHED_DIMENSION)

    with engine.connect() as connection:
        with pytest.raises(NoEmbeddingModelError) as raised:
            run_my_search(connection, USER_A, TOKEN, client_factory=fake_factory(DIMENSION))

    assert raised.value.code == "no_embedding_model"
    assert raised.value.detail == {"reason": "dimension_mismatch"}


def test_an_unreachable_provider_fails_the_whole_search__S029_002_DoD10(engine: Engine) -> None:
    """U1: the scripted fake's `LlmUnreachableError` reaches the caller unchanged."""
    _seed_matching_character_and_tables(engine, dimension=DIMENSION)

    with engine.connect() as connection:
        with pytest.raises(LlmUnreachableError):
            run_my_search(connection, USER_A, TOKEN, client_factory=unreachable_factory(DIMENSION))


# --- DoD-11: no transaction left open (D6) --------------------------------------------------


def test_a_successful_search_leaves_no_transaction_in_progress__S029_002_DoD11(engine: Engine) -> None:
    """D6: the autobegun read is ended again on the ordinary exit."""
    _seed_everything(engine)

    with engine.connect() as connection:
        results = run_my_search(connection, USER_A, TOKEN, client_factory=fake_factory(DIMENSION))

        assert _ids(results.characters) == [CHAR_A1]
        _assert_no_open_transaction(connection)


def test_a_blank_search_leaves_no_transaction_in_progress__S029_002_DoD11(engine: Engine) -> None:
    """D6 and D1 together: the blank early exit issues no SQL, so there is nothing to end."""
    _seed_everything(engine)

    with engine.connect() as connection:
        results = run_my_search(connection, USER_A, "   ", client_factory=fake_factory(DIMENSION))

        assert results.memos == []
        _assert_no_open_transaction(connection)


@pytest.mark.parametrize(
    ("model_dimension", "unreachable", "expected_error"),
    [
        (None, False, NoEmbeddingModelError),
        (MISMATCHED_DIMENSION, False, NoEmbeddingModelError),
        (DIMENSION, True, LlmUnreachableError),
    ],
)
def test_a_failing_search_leaves_no_transaction_in_progress__S029_002_DoD11(
    engine: Engine,
    model_dimension: int | None,
    unreachable: bool,
    expected_error: type[Exception],
) -> None:
    """D6: the guarantee holds on a raise too — for each of DoD-10's three failures."""
    _seed_matching_character_and_tables(engine, dimension=model_dimension)
    factory = unreachable_factory(DIMENSION) if unreachable else fake_factory(DIMENSION)

    with engine.connect() as connection:
        with pytest.raises(expected_error):
            run_my_search(connection, USER_A, TOKEN, client_factory=factory)

        _assert_no_open_transaction(connection)


# --- DoD-12: the module's imports and the flag it never reads --------------------------------


def _module_source() -> str:
    return inspect.getsource(my_search_module)


def _imported_names() -> set[str]:
    """Every module named by an import in `my_search.py`, read from its **AST**.

    Deliberately not a text scan: the module's frozen docstring legitimately contains the word
    `fastapi` (it records that the module imports none), so only import statements count.
    """
    module_file = my_search_module.__file__
    assert module_file is not None
    names: set[str] = set()
    for node in ast.walk(ast.parse(Path(module_file).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_the_my_search_module_still_imports_no_web_framework__S029_002_DoD12() -> None:
    """`context.md` cross-cutting constraints: a service imports no web framework."""
    offenders = {name for name in _imported_names() if name.split(".")[0] in {"fastapi", "starlette"}}

    assert offenders == set()


def test_the_my_search_module_never_names_the_forced_flag__S029_002_DoD12() -> None:
    """R3 constrains the assistant, not the owner: nothing in 029 reads the forced flag, so its
    column name appears nowhere in this module — not in code, not in a comment, not in a
    docstring. A source-text guard, the house form at `tests/test_memos_service.py`."""
    assert "is_forced" not in _module_source()


# =============================================================================================
# Feature 034, step 003 — the session name arm (DoD-1..DoD-9; DEC-034-8,
# DEC-arch-session-names-5). Expected values come from the step file's Interface intent and
# Definition of done; nothing below is read off the implementation.
# =============================================================================================

#: Ids of this block's sessions, in a range of their own (above 2^60, clear of the 029 ids).
NAMED_BASE = 1_291_000_000_000_001_000
NAMED_ONE = NAMED_BASE + 1
NAMED_TWO = NAMED_BASE + 2
NAMED_OTHER = NAMED_BASE + 3
NAMED_B = NAMED_BASE + 4
NAMED_ARCHIVED = NAMED_BASE + 5
UNNAMED_DATED = NAMED_BASE + 6
DATE_NAMED = NAMED_BASE + 7

#: DoD-6's name-order sessions. Ids are deliberately out of step with the name order, so an
#: id sort cannot pass for a name sort: c < b(low) < a < b(high) by id.
ORDER_C = NAMED_BASE + 11
ORDER_B_LOW = NAMED_BASE + 12
ORDER_A = NAMED_BASE + 13
ORDER_B_HIGH = NAMED_BASE + 14

#: DoD-4's wildcard sessions.
WILD_PERCENT = NAMED_BASE + 21
WILD_PLAIN = NAMED_BASE + 22
WILD_UNDERSCORE = NAMED_BASE + 23
WILD_LETTER = NAMED_BASE + 24

#: DoD-6's merge sessions: two name-only, one matched by both arms, three vector-only.
MERGE_NAMED_EARLY = NAMED_BASE + 32
MERGE_NAMED_LATE = NAMED_BASE + 31
MERGE_BOTH = NAMED_BASE + 33
MERGE_VECTOR_IDS = (NAMED_BASE + 34, NAMED_BASE + 35, NAMED_BASE + 36)

#: DoD-6's cap sessions: many named (offset 100..) and many vector-only (offset 200..).
CAP_NAMED_BASE = NAMED_BASE + 100
CAP_VECTOR_BASE = NAMED_BASE + 200

LATIN_NAME = "Lantern Quay"
CYRILLIC_NAME = "Ночной Порт"
UNRELATED_NAME = "Something else entirely"

#: The query the merge tests type, and the stem every merge / cap name shares.
MERGE_QUERY = "lantern quay"

#: A start instant for the named sessions whose hit value is compared field for field.
CREATED_NAMED = "2026-03-05T00:00:00.000000+00:00"

#: DoD-2: the never-renamed session's start instant, and the date a roleplayer would type.
UNNAMED_CREATED = "2026-03-14T09:30:00.000000+00:00"


def _rename(engine: Engine, session_id: int, name: str | None) -> None:
    """Write `sessions.name` directly (a stored rename; the route is step 002's concern)."""
    with engine.begin() as connection:
        connection.execute(schema.sessions.update().where(schema.sessions.c.id == session_id).values(name=name))


def _name_arm(engine: Engine, query_text: str, *, user_id: int = USER_A, limit: int | None = None) -> list[int]:
    """One call of the name arm on a fresh connection; `limit=None` uses its default."""
    with engine.connect() as connection:
        if limit is None:
            return search_session_names(connection, user_id, query_text)
        return search_session_names(connection, user_id, query_text, limit)


def _session_hit(session_id: int) -> SearchHit:
    """A vector-arm session hit as the port shapes it: only `id` and the order matter to the merge."""
    return SearchHit(
        kind="session",
        id=session_id,
        score=0.5,
        snippet="",
        memo_scope=None,
        memo_scope_id=None,
        session_id=None,
    )


def _port_session_order(engine: Engine, query_text: str) -> list[int]:
    """The vector arm's own order: the port's answer to my-search's session-scope call.

    025 is delivered code, not the code under test, so this is "the vector hits in port
    order" (DoD-6) written out, not a value read off 034's implementation.
    """
    with engine.connect() as connection:
        hits = port_search(
            connection,
            SessionSearchScope(user_id=USER_A),
            query_text,
            MY_SEARCH_PER_KIND_LIMIT,
            client_factory=fake_factory(DIMENSION),
        )
    return [hit.id for hit in hits]


def _ready_for_search(engine: Engine) -> None:
    """The designation and the (empty-until-written) search tables, after the rows."""
    _seed_designation(engine)
    _build_search_tables(engine)


@contextmanager
def _statements_on(engine: Engine) -> Iterator[list[str]]:
    """Collect every SQL statement sent through `engine` while the block runs.

    Attached only after the test's connection is open, so connection set-up never counts:
    what is recorded is exactly what the call under test issued.
    """
    seen: list[str] = []

    def record(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", record)


# --- DoD-1: a stored name is found by any substring, in any case (US-152.AC-1, US-147) ------


@pytest.mark.parametrize(
    ("stored", "query_text"),
    [
        (LATIN_NAME, "lantern"),
        (LATIN_NAME, "QUAY"),
        (LATIN_NAME, "tern qu"),
        (LATIN_NAME, "lantern quay"),
        (CYRILLIC_NAME, "ночной"),
        (CYRILLIC_NAME, "ПОРТ"),
        (CYRILLIC_NAME, "ной по"),
    ],
    ids=[
        "latin-lower",
        "latin-upper",
        "latin-inner",
        "latin-whole",
        "cyrillic-lower",
        "cyrillic-upper",
        "cyrillic-inner",
    ],
)
def test_the_name_arm_finds_a_session_by_a_substring_in_any_case__S034_003_DoD1(
    engine: Engine, stored: str, query_text: str
) -> None:
    """DoD-1: a query that is a substring of the stored name — in a different case, Latin and
    Cyrillic alike — finds that session; a session with an unrelated name is not found."""
    _seed_characters_and_setups(engine)
    _insert_session(engine, session_id=NAMED_ONE, name=stored)
    _insert_session(engine, session_id=NAMED_OTHER, name=UNRELATED_NAME)

    assert _name_arm(engine, query_text) == [NAMED_ONE]


def test_my_search_returns_a_session_found_only_by_its_name__S034_003_DoD1(engine: Engine) -> None:
    """DoD-1: neither session has a vector, so only the name arm can put them in the sessions
    group — a Latin query in another case finds the Latin name, a Cyrillic one the Cyrillic."""
    _seed_characters_and_setups(engine)
    _insert_session(engine, session_id=NAMED_ONE, setup_id=SETUP_A1, name=LATIN_NAME, created_at=CREATED_NAMED)
    _insert_session(engine, session_id=NAMED_TWO, name=CYRILLIC_NAME, created_at=CREATED_NAMED)
    _ready_for_search(engine)

    latin = _run(engine, query_text="LANTERN quay")
    cyrillic = _run(engine, query_text="порт")

    assert _ids(latin.sessions) == [NAMED_ONE]
    assert latin.sessions[0].name == LATIN_NAME
    assert _ids(cyrillic.sessions) == [NAMED_TWO]
    assert cyrillic.sessions[0].name == CYRILLIC_NAME


# --- DoD-2: a NULL name is never matched; the start date is not a name ----------------------


@pytest.mark.parametrize("query_text", ["2026-03-14", "2026", "03-14"])
def test_a_never_renamed_session_is_not_found_by_its_start_date__S034_003_DoD2(
    engine: Engine, query_text: str
) -> None:
    """DoD-2 (accepted limitation): the never-renamed session's label is its start date, which
    is computed by the client and never stored, so typing it does not reach that session. A
    session whose **stored** name holds the same text is the positive control."""
    _seed_characters_and_setups(engine)
    _insert_session(engine, session_id=UNNAMED_DATED, created_at=UNNAMED_CREATED)
    _insert_session(engine, session_id=DATE_NAMED, name="2026-03-14 rematch")

    assert _name_arm(engine, query_text) == [DATE_NAMED]


def test_my_search_does_not_return_a_null_named_session_by_its_date__S034_003_DoD2(engine: Engine) -> None:
    """DoD-2 through `run_my_search`: neither session has a vector, so the sessions group is
    exactly what the name arm matched — the stored name, never the NULL one."""
    _seed_characters_and_setups(engine)
    _insert_session(engine, session_id=UNNAMED_DATED, created_at=UNNAMED_CREATED)
    _insert_session(engine, session_id=DATE_NAMED, name="2026-03-14 rematch")
    _ready_for_search(engine)

    assert _ids(_run(engine, query_text="2026-03-14").sessions) == [DATE_NAMED]


# --- DoD-3: another user's matching name is never returned (US-076.AC-1) --------------------


def test_another_users_session_with_the_same_name_is_never_matched__S034_003_DoD3(engine: Engine) -> None:
    """DoD-3: B's session carries A's session's exact name; each owner's name arm finds only
    their own, so the absence is the owner predicate's work and not a name that missed."""
    _seed_characters_and_setups(engine)
    _insert_character(engine, character_id=CHAR_B1, user_id=USER_B, name=CHARACTER_NAME)
    _insert_session(engine, session_id=NAMED_ONE, name=LATIN_NAME)
    _insert_session(engine, session_id=NAMED_B, user_id=USER_B, character_id=CHAR_B1, name=LATIN_NAME)

    assert _name_arm(engine, "lantern") == [NAMED_ONE]
    assert _name_arm(engine, "lantern", user_id=USER_B) == [NAMED_B]


def test_my_search_never_returns_another_users_named_session__S034_003_DoD3(engine: Engine) -> None:
    """DoD-3 through `run_my_search`: A sees A's named session only, B sees B's only."""
    _seed_characters_and_setups(engine)
    _insert_character(engine, character_id=CHAR_B1, user_id=USER_B, name=CHARACTER_NAME)
    _insert_session(engine, session_id=NAMED_ONE, name=LATIN_NAME)
    _insert_session(engine, session_id=NAMED_B, user_id=USER_B, character_id=CHAR_B1, name=LATIN_NAME)
    _ready_for_search(engine)

    assert _ids(_run(engine, query_text="lantern").sessions) == [NAMED_ONE]
    assert _ids(_run(engine, query_text="lantern", user_id=USER_B).sessions) == [NAMED_B]


# --- DoD-4: `%` and `_` match literally ----------------------------------------------------


def _seed_wildcard_names(engine: Engine) -> None:
    """Four names built so that a query read as a LIKE pattern would match more than one."""
    _seed_characters_and_setups(engine)
    _insert_session(engine, session_id=WILD_PERCENT, name="100% harbour")
    _insert_session(engine, session_id=WILD_PLAIN, name="100 harbour")
    _insert_session(engine, session_id=WILD_UNDERSCORE, name="night_watch")
    _insert_session(engine, session_id=WILD_LETTER, name="nightXwatch")


@pytest.mark.parametrize(
    ("query_text", "expected"),
    [
        ("%", [WILD_PERCENT]),
        ("100%", [WILD_PERCENT]),
        ("0% h", [WILD_PERCENT]),
        ("_", [WILD_UNDERSCORE]),
        ("t_w", [WILD_UNDERSCORE]),
        ("%harbour", []),
    ],
    ids=["percent", "percent-suffix", "percent-inner", "underscore", "underscore-inner", "percent-prefix"],
)
def test_percent_and_underscore_in_the_query_match_literally__S034_003_DoD4(
    engine: Engine, query_text: str, expected: list[int]
) -> None:
    """DoD-4: user input never acts as a wildcard — `%` and `_` match only names that contain
    those characters at that place."""
    _seed_wildcard_names(engine)

    assert _name_arm(engine, query_text) == expected


# --- DoD-5: a blank query returns five empty groups and runs no name query -----------------


@pytest.mark.parametrize("query_text", ["", "   ", "\t\n "])
def test_a_blank_query_returns_nothing_from_the_name_arm_and_issues_no_sql__S034_003_DoD5(
    engine: Engine, query_text: str
) -> None:
    """DoD-5: the name arm answers `[]` for a blank query without sending a statement."""
    _seed_characters_and_setups(engine)
    _insert_session(engine, session_id=NAMED_ONE, name=LATIN_NAME)

    with engine.connect() as connection:
        with _statements_on(engine) as seen:
            found = search_session_names(connection, USER_A, query_text)

    assert found == []
    assert seen == []


@pytest.mark.parametrize("query_text", ["", "   "])
def test_a_blank_query_still_returns_five_empty_groups_with_named_sessions_present__S034_003_DoD5(
    engine: Engine, query_text: str
) -> None:
    """DoD-5 through `run_my_search`: with a named session present, a blank query still answers
    five empty groups, opens no model and sends no statement at all — so no name query ran."""
    _seed_everything(engine)
    _rename(engine, SESSION_NO_SETUP, f"{CHARACTER_NAME} {LATIN_NAME}")
    factory = fake_factory(DIMENSION)

    with engine.connect() as connection:
        with _statements_on(engine) as seen:
            results = run_my_search(connection, USER_A, query_text, client_factory=factory)

    assert results == MySearchResults(characters=[], setups=[], sessions=[], entries=[], memos=[])
    assert seen == []
    assert factory.call_count == 0


# --- DoD-6: merge order and the cap (DEC-arch-session-names-5, DEC-034-8) ------------------


def test_the_name_arm_orders_by_name_then_id__S034_003_DoD6(engine: Engine) -> None:
    """DoD-6: name hits are ordered by name, then id — never by id or insertion order."""
    _seed_characters_and_setups(engine)
    _insert_session(engine, session_id=ORDER_B_HIGH, name="harbour night b")
    _insert_session(engine, session_id=ORDER_C, name="harbour night c")
    _insert_session(engine, session_id=ORDER_A, name="harbour night a")
    _insert_session(engine, session_id=ORDER_B_LOW, name="harbour night b")

    assert _name_arm(engine, "harbour night") == [ORDER_A, ORDER_B_LOW, ORDER_B_HIGH, ORDER_C]


def _seed_cap_named_sessions(engine: Engine, count: int) -> list[int]:
    """`count` named sessions, ids inserted in **reverse** name order; returns ids in name order."""
    by_name: list[int] = []
    for offset in range(count):
        by_name.append(CAP_NAMED_BASE + (count - 1 - offset))
    for offset in reversed(range(count)):
        _insert_session(engine, session_id=by_name[offset], name=f"{MERGE_QUERY} {offset:02d}")
    return by_name


def test_the_name_arm_is_capped_at_its_limit__S034_003_DoD6(engine: Engine) -> None:
    """DoD-6: the name arm takes the per-kind limit (20 by default), keeping the name order."""
    _seed_characters_and_setups(engine)
    by_name = _seed_cap_named_sessions(engine, 25)

    assert _name_arm(engine, MERGE_QUERY) == by_name[:EXPECTED_PER_KIND_CAP]
    assert _name_arm(engine, MERGE_QUERY, limit=3) == by_name[:3]


def test_merge_puts_name_hits_first_then_unmatched_vector_hits_in_port_order__S034_003_DoD6() -> None:
    """DoD-6: name ids keep their order, then the vector hits in the order given."""
    name_ids = [NAMED_BASE + 3, NAMED_BASE + 1]
    vector = [_session_hit(NAMED_BASE + 9), _session_hit(NAMED_BASE + 5), _session_hit(NAMED_BASE + 7)]

    merged = merge_session_hits(name_ids, vector, EXPECTED_PER_KIND_CAP)

    assert merged == [NAMED_BASE + 3, NAMED_BASE + 1, NAMED_BASE + 9, NAMED_BASE + 5, NAMED_BASE + 7]


def test_merge_keeps_a_session_matched_by_both_once_in_its_name_position__S034_003_DoD6() -> None:
    """DoD-6: a session the vector arm also found appears once, where the name arm put it."""
    name_ids = [NAMED_BASE + 1, NAMED_BASE + 2]
    vector = [_session_hit(NAMED_BASE + 7), _session_hit(NAMED_BASE + 2), _session_hit(NAMED_BASE + 8)]

    merged = merge_session_hits(name_ids, vector, EXPECTED_PER_KIND_CAP)

    assert merged == [NAMED_BASE + 1, NAMED_BASE + 2, NAMED_BASE + 7, NAMED_BASE + 8]


def test_merge_with_an_empty_arm_is_the_other_arm__S034_003_DoD6() -> None:
    """DoD-6: no name hits leaves the vector order; no vector hits leaves the name order."""
    vector_ids = [NAMED_BASE + 9, NAMED_BASE + 4, NAMED_BASE + 6]

    assert merge_session_hits([], [_session_hit(one) for one in vector_ids], EXPECTED_PER_KIND_CAP) == vector_ids
    assert merge_session_hits([NAMED_BASE + 2, NAMED_BASE + 1], [], EXPECTED_PER_KIND_CAP) == [
        NAMED_BASE + 2,
        NAMED_BASE + 1,
    ]
    assert merge_session_hits([], [], EXPECTED_PER_KIND_CAP) == []


def test_merge_never_exceeds_the_limit__S034_003_DoD6() -> None:
    """DoD-6: the group never exceeds 20 — name hits fill first, vector hits take what is left,
    and an overlap does not use up a place twice."""
    names = [CAP_NAMED_BASE + offset for offset in range(15)]
    vectors = [CAP_VECTOR_BASE + offset for offset in range(10)]

    merged = merge_session_hits(names, [_session_hit(one) for one in vectors], EXPECTED_PER_KIND_CAP)
    assert merged == names + vectors[:5]

    overlapping = [names[3], names[0]] + vectors
    merged = merge_session_hits(names, [_session_hit(one) for one in overlapping], EXPECTED_PER_KIND_CAP)
    assert merged == names + vectors[:5]

    many_names = [CAP_NAMED_BASE + offset for offset in range(25)]
    merged = merge_session_hits(many_names, [_session_hit(one) for one in vectors], EXPECTED_PER_KIND_CAP)
    assert merged == many_names[:EXPECTED_PER_KIND_CAP]

    many_vectors = [CAP_VECTOR_BASE + offset for offset in range(25)]
    merged = merge_session_hits([], [_session_hit(one) for one in many_vectors], EXPECTED_PER_KIND_CAP)
    assert merged == many_vectors[:EXPECTED_PER_KIND_CAP]


def test_merge_honours_a_smaller_limit__S034_003_DoD6() -> None:
    """DoD-6: the cap is the `limit` argument, not a constant baked into the merge."""
    names = [NAMED_BASE + 1, NAMED_BASE + 2]
    vectors = [_session_hit(NAMED_BASE + 7), _session_hit(NAMED_BASE + 8)]

    assert merge_session_hits(names, vectors, 3) == [NAMED_BASE + 1, NAMED_BASE + 2, NAMED_BASE + 7]
    assert merge_session_hits(names, vectors, 1) == [NAMED_BASE + 1]


def test_my_search_puts_name_hits_first_then_the_ports_vector_hits__S034_003_DoD6(engine: Engine) -> None:
    """DoD-6 through `run_my_search`: the two name-only sessions and the one matched by both
    arms come first, in name order; then the vector arm's other hits in the port's order. The
    session matched by both appears once."""
    _seed_characters_and_setups(engine)
    _insert_session(engine, session_id=MERGE_NAMED_LATE, name=f"{MERGE_QUERY} b")
    _insert_session(engine, session_id=MERGE_NAMED_EARLY, name=f"{MERGE_QUERY} a")
    _insert_session(engine, session_id=MERGE_BOTH, name=f"{MERGE_QUERY} c")
    for session_id in MERGE_VECTOR_IDS:
        _insert_session(engine, session_id=session_id)
    _ready_for_search(engine)
    _write_vectors(engine, sessions=[(one, MERGE_QUERY) for one in (MERGE_BOTH, *MERGE_VECTOR_IDS)])

    port_order = _port_session_order(engine, MERGE_QUERY)
    assert set(port_order) == {MERGE_BOTH, *MERGE_VECTOR_IDS}, "the vector arm must reach the seeded rows"
    name_order = [MERGE_NAMED_EARLY, MERGE_NAMED_LATE, MERGE_BOTH]

    returned = _ids(_run(engine, query_text=MERGE_QUERY).sessions)

    assert returned == name_order + [one for one in port_order if one not in name_order]
    assert returned.count(MERGE_BOTH) == 1


def test_my_search_caps_the_merged_session_group_at_twenty__S034_003_DoD6(engine: Engine) -> None:
    """DoD-6 through `run_my_search`: 15 name hits and 10 vector-only hits give exactly 20 —
    all 15 name hits in name order, then the port's first 5 vector hits."""
    _seed_characters_and_setups(engine)
    by_name = _seed_cap_named_sessions(engine, 15)
    vector_ids = [CAP_VECTOR_BASE + offset for offset in range(10)]
    for session_id in vector_ids:
        _insert_session(engine, session_id=session_id)
    _ready_for_search(engine)
    _write_vectors(engine, sessions=[(one, MERGE_QUERY) for one in vector_ids])

    port_order = _port_session_order(engine, MERGE_QUERY)
    returned = _ids(_run(engine, query_text=MERGE_QUERY).sessions)

    assert len(returned) == EXPECTED_PER_KIND_CAP
    assert returned == by_name + port_order[:5]


def test_my_search_with_more_name_hits_than_the_cap_returns_only_name_hits__S034_003_DoD6(
    engine: Engine,
) -> None:
    """DoD-6: 25 name hits fill the group by themselves; no vector hit gets a place."""
    _seed_characters_and_setups(engine)
    by_name = _seed_cap_named_sessions(engine, 25)
    vector_ids = [CAP_VECTOR_BASE + offset for offset in range(3)]
    for session_id in vector_ids:
        _insert_session(engine, session_id=session_id)
    _ready_for_search(engine)
    _write_vectors(engine, sessions=[(one, MERGE_QUERY) for one in vector_ids])

    returned = _ids(_run(engine, query_text=MERGE_QUERY).sessions)

    assert returned == by_name[:EXPECTED_PER_KIND_CAP]


# --- DoD-7: a vector-arm failure still fails the whole search (029 U1) ---------------------


@pytest.mark.parametrize(
    ("model_dimension", "unreachable", "expected_error"),
    [
        (None, False, NoEmbeddingModelError),
        (MISMATCHED_DIMENSION, False, NoEmbeddingModelError),
        (DIMENSION, True, LlmUnreachableError),
    ],
    ids=["no-model", "dimension-mismatch", "unreachable"],
)
def test_a_vector_arm_failure_fails_the_search_even_when_a_name_matched__S034_003_DoD7(
    engine: Engine,
    model_dimension: int | None,
    unreachable: bool,
    expected_error: type[Exception],
) -> None:
    """DoD-7: the name arm alone does find the session (the control), yet `run_my_search`
    raises the vector arm's error and returns no partial answer."""
    _seed_characters_and_setups(engine)
    _insert_session(engine, session_id=NAMED_ONE, name=LATIN_NAME)
    if model_dimension is not None:
        _seed_designation(engine, dimension=model_dimension)
    _build_search_tables(engine)
    factory = unreachable_factory(DIMENSION) if unreachable else fake_factory(DIMENSION)

    assert _name_arm(engine, "lantern") == [NAMED_ONE]
    with engine.connect() as connection:
        with pytest.raises(expected_error):
            run_my_search(connection, USER_A, "lantern", client_factory=factory)


# --- DoD-8: session hits carry `name`, entry hits `session_name` (US-152.AC-2) ---------------


def test_a_session_hit_declares_name_after_setup_name__S034_003_DoD8() -> None:
    """DoD-8: the hydrated session value carries `name` beside `created_at` (frozen order)."""
    assert [field.name for field in dataclasses.fields(SessionHit)] == [
        "id",
        "character_name",
        "setup_name",
        "name",
        "created_at",
        "archived",
    ]


def test_session_and_entry_hits_carry_the_stored_name_or_none__S034_003_DoD8(engine: Engine) -> None:
    """DoD-8: a renamed session's hit carries its name — whether the name arm or the vector arm
    found it — and a never-renamed one carries None; the entry hit carries its session's name
    next to the session's `created_at`."""
    _seed_everything(engine)
    name_hit_name = f"The {CHARACTER_NAME} rematch"  # holds the token, so the name arm finds it
    vector_hit_name = "Harbour Vigil"  # no token: this session is reached by its vector only
    _rename(engine, SESSION_NO_SETUP, name_hit_name)
    _rename(engine, SESSION_WITH_SETUP, vector_hit_name)

    results = _run(engine)

    by_id = {hit.id: hit for hit in results.sessions}
    assert by_id[SESSION_NO_SETUP] == SessionHit(
        id=SESSION_NO_SETUP,
        character_name=CHARACTER_NAME,
        setup_name=None,
        name=name_hit_name,
        created_at=CREATED_NO_SETUP,
        archived=False,
    )
    assert by_id[SESSION_WITH_SETUP] == SessionHit(
        id=SESSION_WITH_SETUP,
        character_name=CHARACTER_NAME,
        setup_name=SETUP_NAME,
        name=vector_hit_name,
        created_at=CREATED_WITH_SETUP,
        archived=False,
    )
    assert by_id[SESSION_ARCHIVED].name is None
    assert by_id[SESSION_ARCHIVED].created_at == CREATED_ARCHIVED
    assert _ids(results.sessions)[0] == SESSION_NO_SETUP  # DoD-6: the name hit leads

    entries = {hit.id: hit for hit in results.entries}
    assert entries[ENTRY_SETTLED].session_id == SESSION_WITH_SETUP
    assert entries[ENTRY_SETTLED].session_name == vector_hit_name
    assert entries[ENTRY_SETTLED].session_created_at == CREATED_WITH_SETUP


# --- DoD-9: an archived session found by name is returned and marked (029 U3) ---------------


def test_an_archived_session_found_by_name_is_returned_and_marked_archived__S034_003_DoD9(
    engine: Engine,
) -> None:
    """DoD-9: the name arm includes archived sessions, and the hit says so."""
    _seed_characters_and_setups(engine)
    _insert_session(
        engine,
        session_id=NAMED_ARCHIVED,
        setup_id=SETUP_A1,
        archived_at=TIMESTAMP,
        created_at=CREATED_NAMED,
        name=LATIN_NAME,
    )
    _ready_for_search(engine)

    assert _name_arm(engine, "quay") == [NAMED_ARCHIVED]
    assert _run(engine, query_text="quay").sessions == [
        SessionHit(
            id=NAMED_ARCHIVED,
            character_name=CHARACTER_NAME,
            setup_name=SETUP_NAME,
            name=LATIN_NAME,
            created_at=CREATED_NAMED,
            archived=True,
        )
    ]
