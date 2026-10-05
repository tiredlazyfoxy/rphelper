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
    SessionHit(id, character_name, setup_name: str | None, created_at: str, archived)
    EntryHit(id, session_id, snippet, character_name, session_created_at: str)
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

Mechanics (`context.md` "Test conventions"): a real SQLite file per test through the shared
`db_engine` fixture (`tests/conftest.py` and `tests/llm_fakes.py` are untouched), raw inserts
only, ids above 2^60, two users A and B, and every other helper file-local.
"""

import ast
import dataclasses
import inspect
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, Table, select

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
    run_my_search,
)
from app.services.search.ports import MemoSearchScope
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
) -> None:
    """Raw-insert one `sessions` row (`002.context.md`: no title, name or partner column)."""
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
    assert by_id[SESSION_WITH_SETUP] == SessionHit(
        id=SESSION_WITH_SETUP,
        character_name=CHARACTER_NAME,
        setup_name=SETUP_NAME,
        created_at=CREATED_WITH_SETUP,
        archived=False,
    )
    assert by_id[SESSION_NO_SETUP] == SessionHit(
        id=SESSION_NO_SETUP,
        character_name=CHARACTER_NAME,
        setup_name=None,
        created_at=CREATED_NO_SETUP,
        archived=False,
    )
    assert by_id[SESSION_ARCHIVED] == SessionHit(
        id=SESSION_ARCHIVED,
        character_name=CHARACTER_NAME,
        setup_name=SETUP_NAME,
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


def test_an_entry_hit_carries_the_frozen_five_fields__S029_002_DoD6() -> None:
    """The hydrated entry value is exactly the wire contract's five keys, in that order."""
    assert [field.name for field in dataclasses.fields(EntryHit)] == [
        "id",
        "session_id",
        "snippet",
        "character_name",
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
