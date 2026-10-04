"""`services/search/memo_search.py` — feature 026, step 001 (DoD-4..13).

Every expected value comes from the **spec**, never from the implementation:
`docs/plans/026.memo-search-tool/001.chain-clause-and-memo-search.md` (Interface intent and
Definition of done), `001.context.md` (the port-binding and seeding notes) and the feature
`context.md` — **D1** (the result cap is `8`, no paging), **D2** (the extra predicate is
`is_enabled AND NOT is_forced AND <chain clause>`, `is_enabled` first), **D5** (port errors
propagate unchanged; no transaction is left open on either exit), **R2**, **R3**, **R5** and
the literals table (`result cap` = `8`).

Bindings come from `## Skeleton` → "Step 001 — frozen interface" in `status.md`:

    MEMO_SEARCH_LIMIT: Final[int] = 8
    searchable_chain_predicate(user_id, character_id, setup_id, session_id) -> ExtraPredicateBuilder
    search_memos(connection, user_id, character_id, setup_id, session_id, query_text, *,
                 client_factory=LlmClient, timeout_seconds=DEFAULT_EMBED_TIMEOUT_SECONDS) -> list[SearchHit]

A hit's memo fields are `memo_scope` / `memo_scope_id` (025 step 001's frozen record), and
`memo_scope_id` is the **raw stored** `memos.scope_id` — so a user-level hit carries the user's
own id (DoD-6). There is no bare `scope` field.

How the expectations are derived
--------------------------------
Nothing here asks the code under test what the answer is.

* **The port is never mocked and nothing is monkeypatched.** The search tables are the real
  ones, created only through 024's `ensure_fts_tables` / `ensure_vector_tables`; vectors are
  written only through 024's `write_vector` from `tests/llm_fakes.py`'s pure
  `embedding_vector(text, dim)`; a designated model is a raw `llm_servers` + `models` pair at
  dimension 8 with `api_key_ref=None`; the provider arrives through the frozen
  `client_factory=` seam.
* **Every seeded note carries the same token in its body *and* a `memo_vec` row**, so both
  arms would reach every one of them (`context.md` cross-cutting constraints). An absence is
  therefore proof that the predicate excluded the row, never that the arms missed it. Each
  note additionally carries its own unique marker word, so its text can be asserted absent.
* **Membership and levels are asserted, never the fused order or the scores** — those are
  025's contract, not 026's. The cap is asserted against `MEMO_SEARCH_LIMIT`, except in the
  one test that pins the constant to the spec's literal `8`.

Each test name ends `__S026_001_DoD<n>` with the DoD item it covers.

Mechanics (`context.md` "Test conventions"): a real SQLite file per test through the shared
`db_engine` fixture (`tests/conftest.py` and `tests/llm_fakes.py` are untouched), raw inserts
only, ids above 2^60, two users A and B, and every other helper file-local.
"""

import ast
import dataclasses
from collections.abc import Sequence
from pathlib import Path

import pytest
from sqlalchemy import ColumnElement, Connection, Engine, Table, select, text
from sqlalchemy.dialects import sqlite

from app.db import schema
from app.db.search_tables import MEMO_VEC_TABLE, ensure_fts_tables, ensure_vector_tables
from app.errors import LlmUnreachableError, NoEmbeddingModelError
from app.roles import Role
from app.services.embedding import write_vector
from app.services.search import memo_search as memo_search_module
from app.services.search.memo_search import MEMO_SEARCH_LIMIT, search_memos, searchable_chain_predicate
from app.services.search.ports import SearchHit
from tests.llm_fakes import FakeClientFactory, embedding_vector, fake_factory, unreachable_factory

#: The seeded instant, in the project's fixed-width UTC text form.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

#: Every id below is above 2^60 = 1152921504606846976 (snowflake-sized).
SNOWFLAKE_FLOOR = 2**60

#: The designated embedding width throughout; 8 is what 024 and 025 use.
DIMENSION = 8

#: D1's result cap, written out as the **spec's** literal (the literals table).
EXPECTED_RESULT_CAP = 8

#: The searched term. Lower case, so FTS5's verbatim snippet text contains it as-is.
TOKEN = "kaelith"

USER_A = 1_700_000_000_000_000_001
USER_B = 1_700_000_000_000_000_002

CHARACTER_A1 = 1_700_000_000_000_000_101
CHARACTER_A2 = 1_700_000_000_000_000_102
CHARACTER_B1 = 1_700_000_000_000_000_103

SETUP_A1 = 1_700_000_000_000_000_151
SETUP_A2 = 1_700_000_000_000_000_152

#: `SESSION_A1` carries a setup; `SESSION_A_PLAIN` is the same character with **no** setup.
SESSION_A1 = 1_700_000_000_000_000_201
SESSION_A2 = 1_700_000_000_000_000_202
SESSION_A_PLAIN = 1_700_000_000_000_000_203
SESSION_B1 = 1_700_000_000_000_000_204

SERVER_ID = 1_700_000_000_000_000_901
MODEL_ID = 1_700_000_000_000_000_902

BASE_URL = "http://embedding.test:8080/v1"
MODEL_NAME = "the-designated-embedding-model"


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


def _insert_setup(engine: Engine, *, setup_id: int, user_id: int, character_id: int, name: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.setups.insert().values(
                id=setup_id,
                user_id=user_id,
                character_id=character_id,
                name=name,
                description="",
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_session(
    engine: Engine, *, session_id: int, user_id: int, character_id: int, setup_id: int | None
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.insert().values(
                id=session_id,
                user_id=user_id,
                character_id=character_id,
                setup_id=setup_id,
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
    scope: str,
    scope_id: int,
    body: str,
    is_enabled: bool = True,
    is_forced: bool = False,
    sort_key: int = 0,
) -> None:
    """Raw-insert one `memos` row; `scope_id` is the **stored** id (the user id at user level)."""
    with engine.begin() as connection:
        connection.execute(
            schema.memos.insert().values(
                id=memo_id,
                user_id=user_id,
                scope=scope,
                scope_id=scope_id,
                body=body,
                is_enabled=is_enabled,
                is_forced=is_forced,
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


def _ensure_fts(engine: Engine) -> None:
    """Create `memo_fts` / `message_fts` with 024's helper (test setup only), after the inserts."""
    with engine.begin() as connection:
        ensure_fts_tables(connection)


def _ensure_vec(engine: Engine, dimension: int = DIMENSION) -> None:
    """Create `memo_vec` / `session_vec` at `dimension` with 024's helper (test setup only)."""
    with engine.begin() as connection:
        ensure_vector_tables(connection, dimension)


def _write_vectors(engine: Engine, sources: dict[int, str]) -> None:
    """One `memo_vec` row per memo, each `embedding_vector(<its body>, 8)`, via 024's writer."""
    with engine.begin() as connection:
        for row_id, source in sources.items():
            write_vector(connection, MEMO_VEC_TABLE, row_id, embedding_vector(source, DIMENSION))


def _fts_match_count(engine: Engine, token: str = TOKEN) -> int:
    """A file-local `memo_fts` probe, so "the index holds a match" is asserted without the code."""
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT rowid FROM memo_fts WHERE memo_fts MATCH :query"), {"query": token}
        ).all()
    return len(rows)


# --- the notes: one shared token, one unique marker each ------------------------------------


@dataclasses.dataclass(frozen=True)
class _Note:
    """One seeded note. Its body always holds `TOKEN`, so both arms would reach it."""

    memo_id: int
    scope: str
    scope_id: int
    marker: str
    user_id: int = USER_A
    is_enabled: bool = True
    is_forced: bool = False

    @property
    def body(self) -> str:
        return f"{TOKEN} remembers the {self.marker}"


def _seed(engine: Engine, notes: Sequence[_Note], *, designate: bool = True) -> None:
    """Rows, then the designation, then the FTS tables, then the vec tables, then the vectors."""
    for note in notes:
        _insert_memo(
            engine,
            memo_id=note.memo_id,
            user_id=note.user_id,
            scope=note.scope,
            scope_id=note.scope_id,
            body=note.body,
            is_enabled=note.is_enabled,
            is_forced=note.is_forced,
        )
    if designate:
        _seed_designation(engine)
    _ensure_fts(engine)
    _ensure_vec(engine)
    _write_vectors(engine, {note.memo_id: note.body for note in notes})


def _run_search(
    engine: Engine,
    *,
    character_id: int = CHARACTER_A1,
    setup_id: int | None = SETUP_A1,
    session_id: int = SESSION_A1,
    user_id: int = USER_A,
    query_text: str = TOKEN,
    factory: FakeClientFactory | None = None,
) -> list[SearchHit]:
    with engine.connect() as connection:
        return search_memos(
            connection,
            user_id=user_id,
            character_id=character_id,
            setup_id=setup_id,
            session_id=session_id,
            query_text=query_text,
            client_factory=factory if factory is not None else fake_factory(DIMENSION),
        )


def _snippets(hits: Sequence[SearchHit]) -> str:
    """Every hit's snippet, joined — an excluded note's marker can only be absent from this."""
    return "\n".join(hit.snippet or "" for hit in hits)


def _assert_no_open_transaction(connection: Connection) -> None:
    assert not connection.in_transaction()
    transaction = connection.begin()
    transaction.rollback()


# --- fixtures -------------------------------------------------------------------------------


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """Two users, three characters, two setups and four sessions — one of them setup-less.

    No virtual table and no designated model: `create_all` leaves the search tables absent and
    designates nothing, so each test opts into exactly what it needs.
    """
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="aster")
    _insert_user(db_engine, user_id=USER_B, username="briar")
    _insert_character(db_engine, character_id=CHARACTER_A1, user_id=USER_A, name="first")
    _insert_character(db_engine, character_id=CHARACTER_A2, user_id=USER_A, name="second")
    _insert_character(db_engine, character_id=CHARACTER_B1, user_id=USER_B, name="other owner")
    _insert_setup(db_engine, setup_id=SETUP_A1, user_id=USER_A, character_id=CHARACTER_A1, name="the inn")
    _insert_setup(db_engine, setup_id=SETUP_A2, user_id=USER_A, character_id=CHARACTER_A2, name="the road")
    _insert_session(
        db_engine, session_id=SESSION_A1, user_id=USER_A, character_id=CHARACTER_A1, setup_id=SETUP_A1
    )
    _insert_session(
        db_engine, session_id=SESSION_A2, user_id=USER_A, character_id=CHARACTER_A2, setup_id=SETUP_A2
    )
    _insert_session(
        db_engine, session_id=SESSION_A_PLAIN, user_id=USER_A, character_id=CHARACTER_A1, setup_id=None
    )
    _insert_session(
        db_engine, session_id=SESSION_B1, user_id=USER_B, character_id=CHARACTER_B1, setup_id=None
    )
    return db_engine


# --- DoD-4: the predicate's shape — R3 order, negation, conjunction (R3, D2) ----------------

FLAGS_SEARCHABLE = 1_700_000_000_000_000_301
FLAGS_FORCED = 1_700_000_000_000_000_302
FLAGS_DISABLED = 1_700_000_000_000_000_303
FLAGS_DISABLED_AND_FORCED = 1_700_000_000_000_000_304
FLAGS_OUTSIDE_THE_CHAIN = 1_700_000_000_000_000_305


def _predicate_clause() -> ColumnElement[bool]:
    """A's with-setup chain, built over the `memos` table itself (what the port passes)."""
    builder = searchable_chain_predicate(
        user_id=USER_A, character_id=CHARACTER_A1, setup_id=SETUP_A1, session_id=SESSION_A1
    )
    return builder(schema.memos)


def test_the_predicate_names_is_enabled_before_is_forced__S026_001_DoD4() -> None:
    """R3: `is_enabled` gates first, so it comes first in the compiled text as well."""
    compiled = str(
        _predicate_clause().compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "is_enabled" in compiled
    assert "is_forced" in compiled
    assert compiled.index("is_enabled") < compiled.index("is_forced")


def test_the_predicate_keeps_only_enabled_unforced_notes_of_the_chain__S026_001_DoD4(engine: Engine) -> None:
    """The `is_forced` term is negated, conjoined with `is_enabled`, and the chain is ANDed in."""
    for memo_id, is_enabled, is_forced in (
        (FLAGS_SEARCHABLE, True, False),
        (FLAGS_FORCED, True, True),
        (FLAGS_DISABLED, False, False),
        (FLAGS_DISABLED_AND_FORCED, False, True),
    ):
        _insert_memo(
            engine,
            memo_id=memo_id,
            user_id=USER_A,
            scope="session",
            scope_id=SESSION_A1,
            body=f"{TOKEN} flag case {memo_id}",
            is_enabled=is_enabled,
            is_forced=is_forced,
        )
    _insert_memo(
        engine,
        memo_id=FLAGS_OUTSIDE_THE_CHAIN,
        user_id=USER_A,
        scope="session",
        scope_id=SESSION_A2,
        body=f"{TOKEN} outside the chain",
    )

    with engine.connect() as connection:
        rows = connection.execute(select(schema.memos.c.id).where(_predicate_clause())).all()

    assert {row.id for row in rows} == {FLAGS_SEARCHABLE}


# --- DoD-5: the result cap (D1) -------------------------------------------------------------


def test_the_result_count_constant_is_eight__S026_001_DoD5() -> None:
    """D1 and the literals table: the cap is a fixed `8`, with no paging around it."""
    assert MEMO_SEARCH_LIMIT == EXPECTED_RESULT_CAP


# --- DoD-6: all four levels (US-063.AC-1, US-099.AC-2) --------------------------------------

LEVEL_USER = 1_700_000_000_000_000_311
LEVEL_CHARACTER = 1_700_000_000_000_000_312
LEVEL_SETUP = 1_700_000_000_000_000_313
LEVEL_SESSION = 1_700_000_000_000_000_314

FOUR_LEVEL_NOTES = (
    _Note(memo_id=LEVEL_USER, scope="user", scope_id=USER_A, marker="aurelian"),
    _Note(memo_id=LEVEL_CHARACTER, scope="character", scope_id=CHARACTER_A1, marker="bellringer"),
    _Note(memo_id=LEVEL_SETUP, scope="setup", scope_id=SETUP_A1, marker="cindermoor"),
    _Note(memo_id=LEVEL_SESSION, scope="session", scope_id=SESSION_A1, marker="dawnwarden"),
)


def test_a_with_setup_chain_returns_one_hit_at_each_of_the_four_levels__S026_001_DoD6(engine: Engine) -> None:
    """Each hit names its own level; the user-level hit's `memo_scope_id` is A's own id."""
    _seed(engine, FOUR_LEVEL_NOTES)

    hits = _run_search(engine)

    assert len(hits) == 4
    assert {(hit.id, hit.memo_scope, hit.memo_scope_id) for hit in hits} == {
        (LEVEL_USER, "user", USER_A),
        (LEVEL_CHARACTER, "character", CHARACTER_A1),
        (LEVEL_SETUP, "setup", SETUP_A1),
        (LEVEL_SESSION, "session", SESSION_A1),
    }


# --- DoD-7: no setup, no gap (US-065.AC-1, R2) ---------------------------------------------

PLAIN_USER = 1_700_000_000_000_000_321
PLAIN_CHARACTER = 1_700_000_000_000_000_322
PLAIN_SESSION = 1_700_000_000_000_000_323
PLAIN_UNREACHED_SETUP = 1_700_000_000_000_000_324

NO_SETUP_NOTES = (
    _Note(memo_id=PLAIN_USER, scope="user", scope_id=USER_A, marker="elmsong"),
    _Note(memo_id=PLAIN_CHARACTER, scope="character", scope_id=CHARACTER_A1, marker="fernwhistle"),
    _Note(memo_id=PLAIN_SESSION, scope="session", scope_id=SESSION_A_PLAIN, marker="galeharrow"),
    _Note(memo_id=PLAIN_UNREACHED_SETUP, scope="setup", scope_id=SETUP_A1, marker="hollowbrand"),
)


def test_a_no_setup_chain_returns_the_three_levels_and_raises_nothing__S026_001_DoD7(engine: Engine) -> None:
    """R2: with no setup level there is one fewer term, and no gap in the three that remain."""
    _seed(engine, NO_SETUP_NOTES)

    hits = _run_search(engine, setup_id=None, session_id=SESSION_A_PLAIN)

    assert len(hits) == 3
    assert {(hit.id, hit.memo_scope, hit.memo_scope_id) for hit in hits} == {
        (PLAIN_USER, "user", USER_A),
        (PLAIN_CHARACTER, "character", CHARACTER_A1),
        (PLAIN_SESSION, "session", SESSION_A_PLAIN),
    }


def test_a_no_setup_chain_reaches_no_setup_level_note__S026_001_DoD7(engine: Engine) -> None:
    """Stated as an absence: a setup-scoped note with the token is unreachable without a setup."""
    _seed(engine, NO_SETUP_NOTES)

    hits = _run_search(engine, setup_id=None, session_id=SESSION_A_PLAIN)

    assert PLAIN_UNREACHED_SETUP not in {hit.id for hit in hits}
    assert "hollowbrand" not in _snippets(hits)


# --- DoD-8: the flags, as absences (UC-052, US-100.AC-2, US-055.AC-2, R3) ------------------

FLAG_SEARCHABLE = 1_700_000_000_000_000_331
FLAG_FORCED = 1_700_000_000_000_000_332
FLAG_DISABLED = 1_700_000_000_000_000_333
FLAG_DISABLED_AND_FORCED = 1_700_000_000_000_000_334

FLAG_NOTES = (
    _Note(memo_id=FLAG_SEARCHABLE, scope="session", scope_id=SESSION_A1, marker="ironquill"),
    _Note(
        memo_id=FLAG_FORCED,
        scope="session",
        scope_id=SESSION_A1,
        marker="jessamine",
        is_enabled=True,
        is_forced=True,
    ),
    _Note(
        memo_id=FLAG_DISABLED,
        scope="session",
        scope_id=SESSION_A1,
        marker="kestrelbane",
        is_enabled=False,
        is_forced=False,
    ),
    _Note(
        memo_id=FLAG_DISABLED_AND_FORCED,
        scope="session",
        scope_id=SESSION_A1,
        marker="lanternmere",
        is_enabled=False,
        is_forced=True,
    ),
)


def test_only_the_enabled_unforced_note_of_the_level_is_returned__S026_001_DoD8(engine: Engine) -> None:
    """R3: forced, disabled and disabled-and-forced notes are all absent, the searchable one is not."""
    _seed(engine, FLAG_NOTES)

    hits = _run_search(engine)

    assert [hit.id for hit in hits] == [FLAG_SEARCHABLE]


def test_the_forced_and_disabled_notes_texts_never_appear__S026_001_DoD8(engine: Engine) -> None:
    """Each excluded note carries the token and a vector, so its absence is the predicate's work."""
    _seed(engine, FLAG_NOTES)

    hits = _run_search(engine)
    snippets = _snippets(hits)

    assert "jessamine" not in snippets
    assert "kestrelbane" not in snippets
    assert "lanternmere" not in snippets
    assert "ironquill" in snippets


# --- DoD-9: another user, as absences (US-064.AC-1, R5) ------------------------------------

OWN_USER = 1_700_000_000_000_000_341
OWN_CHARACTER = 1_700_000_000_000_000_342
OWN_SETUP = 1_700_000_000_000_000_343
OWN_SESSION = 1_700_000_000_000_000_344

B_OWN_USER = 1_700_000_000_000_000_351
B_AT_A_USER = 1_700_000_000_000_000_352
B_AT_A_CHARACTER = 1_700_000_000_000_000_353
B_AT_A_SETUP = 1_700_000_000_000_000_354
B_AT_A_SESSION = 1_700_000_000_000_000_355

#: `memos.scope_id` carries no foreign key, so B's rows can collide with A's chain levels.
COLLIDING_NOTES = (
    _Note(memo_id=OWN_USER, scope="user", scope_id=USER_A, marker="mirebloom"),
    _Note(memo_id=OWN_CHARACTER, scope="character", scope_id=CHARACTER_A1, marker="nightreed"),
    _Note(memo_id=OWN_SETUP, scope="setup", scope_id=SETUP_A1, marker="oakenshade"),
    _Note(memo_id=OWN_SESSION, scope="session", scope_id=SESSION_A1, marker="pinefall"),
    _Note(memo_id=B_OWN_USER, scope="user", scope_id=USER_B, marker="quillraven", user_id=USER_B),
    _Note(memo_id=B_AT_A_USER, scope="user", scope_id=USER_A, marker="riverhelm", user_id=USER_B),
    _Note(
        memo_id=B_AT_A_CHARACTER, scope="character", scope_id=CHARACTER_A1, marker="stonewren", user_id=USER_B
    ),
    _Note(memo_id=B_AT_A_SETUP, scope="setup", scope_id=SETUP_A1, marker="thornvale", user_id=USER_B),
    _Note(memo_id=B_AT_A_SESSION, scope="session", scope_id=SESSION_A1, marker="umbercoil", user_id=USER_B),
)

B_MARKERS = ("quillraven", "riverhelm", "stonewren", "thornvale", "umbercoil")


def test_another_users_notes_never_appear_in_the_callers_results__S026_001_DoD9(engine: Engine) -> None:
    """R5: B's own user-level note and B's four chain-colliding notes are all absent."""
    _seed(engine, COLLIDING_NOTES)

    hits = _run_search(engine)

    assert {hit.id for hit in hits} == {OWN_USER, OWN_CHARACTER, OWN_SETUP, OWN_SESSION}


def test_another_users_note_texts_never_appear_in_the_callers_results__S026_001_DoD9(engine: Engine) -> None:
    """Each of B's notes carries the token and a vector, so the owner predicate is what excludes it."""
    _seed(engine, COLLIDING_NOTES)

    snippets = _snippets(_run_search(engine))

    for marker in B_MARKERS:
        assert marker not in snippets


# --- DoD-10: outside the chain, as absences (R2) -------------------------------------------

INSIDE_THE_CHAIN = 1_700_000_000_000_000_361
OTHER_SESSION_NOTE = 1_700_000_000_000_000_362
OTHER_CHARACTER_NOTE = 1_700_000_000_000_000_363
OTHER_SETUP_NOTE = 1_700_000_000_000_000_364

OUTSIDE_NOTES = (
    _Note(memo_id=INSIDE_THE_CHAIN, scope="session", scope_id=SESSION_A1, marker="valebrook"),
    _Note(memo_id=OTHER_SESSION_NOTE, scope="session", scope_id=SESSION_A2, marker="wyrmgate"),
    _Note(memo_id=OTHER_CHARACTER_NOTE, scope="character", scope_id=CHARACTER_A2, marker="xanthemoor"),
    _Note(memo_id=OTHER_SETUP_NOTE, scope="setup", scope_id=SETUP_A2, marker="yarrowind"),
)


def test_notes_outside_the_chain_are_absent__S026_001_DoD10(engine: Engine) -> None:
    """R2: another session, character and setup of the **same** user are all out of the chain."""
    _seed(engine, OUTSIDE_NOTES)

    hits = _run_search(engine)

    assert {hit.id for hit in hits} == {INSIDE_THE_CHAIN}
    snippets = _snippets(hits)
    assert "wyrmgate" not in snippets
    assert "xanthemoor" not in snippets
    assert "yarrowind" not in snippets


# --- DoD-11: the cap (D1) -----------------------------------------------------------------

CAP_BASE = 1_700_000_000_000_000_371
CAP_NOTE_COUNT = 11

CAP_NOTES = tuple(
    _Note(
        memo_id=CAP_BASE + offset,
        scope=("user", "character", "session")[offset % 3],
        scope_id=(USER_A, CHARACTER_A1, SESSION_A1)[offset % 3],
        marker=f"capmarker{offset}",
    )
    for offset in range(CAP_NOTE_COUNT)
)


def test_more_than_the_cap_of_matching_notes_yields_exactly_the_cap__S026_001_DoD11(engine: Engine) -> None:
    """D1: eleven searchable matching notes in the chain, and exactly `MEMO_SEARCH_LIMIT` hits."""
    assert CAP_NOTE_COUNT > MEMO_SEARCH_LIMIT
    _seed(engine, CAP_NOTES)

    hits = _run_search(engine)

    assert len(hits) == MEMO_SEARCH_LIMIT
    returned = {hit.id for hit in hits}
    assert len(returned) == MEMO_SEARCH_LIMIT
    assert returned <= {note.memo_id for note in CAP_NOTES}


# --- DoD-12: errors propagate, no transaction left open (D5, R4) ---------------------------

ERROR_NOTE = (_Note(memo_id=1_700_000_000_000_000_391, scope="session", scope_id=SESSION_A1, marker="zephyrine"),)


def test_no_designated_model_raises_no_embedding_model__S026_001_DoD12(engine: Engine) -> None:
    """D5: the port's error propagates unchanged, even though `memo_fts` holds a match."""
    _seed(engine, ERROR_NOTE, designate=False)
    assert _fts_match_count(engine) == 1

    with engine.connect() as connection:
        with pytest.raises(NoEmbeddingModelError):
            search_memos(
                connection,
                user_id=USER_A,
                character_id=CHARACTER_A1,
                setup_id=SETUP_A1,
                session_id=SESSION_A1,
                query_text=TOKEN,
                client_factory=fake_factory(DIMENSION),
            )

        _assert_no_open_transaction(connection)


def test_an_unreachable_provider_raises_llm_unreachable__S026_001_DoD12(engine: Engine) -> None:
    """D5: the scripted fake's `LlmUnreachableError` reaches the caller unchanged."""
    _seed(engine, ERROR_NOTE)

    with engine.connect() as connection:
        with pytest.raises(LlmUnreachableError):
            search_memos(
                connection,
                user_id=USER_A,
                character_id=CHARACTER_A1,
                setup_id=SETUP_A1,
                session_id=SESSION_A1,
                query_text=TOKEN,
                client_factory=unreachable_factory(DIMENSION),
            )

        _assert_no_open_transaction(connection)


def test_a_successful_search_leaves_no_transaction_in_progress__S026_001_DoD12(engine: Engine) -> None:
    """The guarantee holds on the ordinary exit too, not only on a raise."""
    _seed(engine, ERROR_NOTE)

    with engine.connect() as connection:
        hits = search_memos(
            connection,
            user_id=USER_A,
            character_id=CHARACTER_A1,
            setup_id=SETUP_A1,
            session_id=SESSION_A1,
            query_text=TOKEN,
            client_factory=fake_factory(DIMENSION),
        )

        assert [hit.id for hit in hits] == [ERROR_NOTE[0].memo_id]
        _assert_no_open_transaction(connection)


# --- DoD-13: the module's imports (`context.md` cross-cutting constraints) -----------------


def _imported_names() -> set[str]:
    """Every module named by an import in `memo_search.py`'s source, read as text (001 `context.md`)."""
    module_file = memo_search_module.__file__
    assert module_file is not None
    names: set[str] = set()
    for node in ast.walk(ast.parse(Path(module_file).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_the_memo_search_module_imports_no_web_framework__S026_001_DoD13() -> None:
    """A service imports no web framework (`context.md` cross-cutting constraints)."""
    offenders = {
        name
        for name in _imported_names()
        if name.split(".")[0] in {"fastapi", "starlette"}
    }

    assert offenders == set()


def test_the_memo_search_module_imports_nothing_from_the_tools_package__S026_001_DoD13() -> None:
    """D3: this module knows nothing of tools; the dependency runs the other way."""
    offenders = {name for name in _imported_names() if name.startswith("app.services.tools")}

    assert offenders == set()
