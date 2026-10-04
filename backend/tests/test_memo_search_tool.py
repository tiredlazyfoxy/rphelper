"""`services/tools/memo_search.py` — feature 026, step 002 (DoD-1..14).

Every expected value comes from the **spec**, never from the implementation:
`docs/plans/026.memo-search-tool/002.memo-search-tool-adapter.md` (Interface intent and
Definition of done), `002.context.md` (the seam details and the seeding notes) and the feature
`context.md` — **D3** (the adapter runs step 001's sync search off the event loop, and is
registered in the production registry), **D4** (the content line `[<level>] <snippet>` with
whitespace runs collapsed, lines joined by `\\n`; `No matching notes.` for no hits; the summary
`<N> memos`), **D5** (failure raises; no transaction is left open on either exit), **D6** (the
ids come only from the `ToolScope`), and the literals table.

Bindings come from `## Skeleton` → "Step 002 — frozen interface" in `status.md`:

    def format_hits(hits: Sequence[SearchHit]) -> tuple[str, str]      # (content, summary)

    @dataclass(frozen=True, kw_only=True)
    class MemoSearchTool:
        client_factory: LlmClientFactory | None = None
        timeout_seconds: float | None = None
        name: ClassVar[str] = MEMO_SEARCH_NAME
        async def run(self, scope, connection, arguments) -> ToolOutcome

Construction is keyword-only, and `MemoSearchTool()` — both injections left at `None` — is the
production instance. A test that wants 024's fake embedder writes
`MemoSearchTool(client_factory=fake_factory(8))`.

The seam names are 021's, as built: `ToolScope(user_id, session_id, character_id, setup_id)`,
`ToolOutcome(content, summary)`, `PRODUCTION_TOOL_REGISTRY`, `build_tool_scope`,
`offered_tools`, `dispatch(call, scope, offered, registry, engine, generator)`.

How the expectations are derived
--------------------------------
* **The port is never mocked and nothing is monkeypatched.** The search tables are the real
  ones, created only through 024's `ensure_fts_tables` / `ensure_vector_tables`; vectors are
  written only through 024's `write_vector` from `tests/llm_fakes.py`'s pure
  `embedding_vector(text, dim)`; a designated model is a raw `llm_servers` + `models` pair at
  dimension 8; the provider arrives through the frozen `client_factory=` seam.
* **The hit order is step 001's contract, not this step's** (`002.context.md`): the expected
  hits come from calling `search_memos` with the same inputs, and the expected *lines* are then
  **D4 applied here** (`[<level>] <snippet>`, whitespace collapsed, joined by `\\n`). Nothing is
  ever read back out of `format_hits` or `run` to build an expectation.
* **Every seeded note carries the same token in its body *and* a `memo_vec` row**, so both arms
  would reach every one of them. An absence is therefore the predicate's work, never a missed
  arm. Each note also carries its own unique marker word, so its text can be asserted absent.
* The literals (`No matching notes.`, `<N> memos`, `The tool failed. Continue without its
  result.`, `tool_failed`) are written out here from `context.md`'s literals table.

Each test name ends `__S026_002_DoD<n>` with the DoD item it covers. DoD-15 (the amendments to
021's three test files) is not a test of its own; DoD-16 is `[manual/live]`.

Mechanics (`context.md` "Test conventions"): a real SQLite file per test through the shared
`db_engine` fixture (`tests/conftest.py` and `tests/llm_fakes.py` are untouched), raw inserts
only, ids above 2^60, two users A and B, async driven by `asyncio.run` bounded by
`asyncio.wait_for`, and every other helper file-local.
"""

import ast
import asyncio
import dataclasses
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, Table, select

from app.db import schema
from app.db.search_tables import MEMO_VEC_TABLE, ensure_fts_tables, ensure_vector_tables
from app.errors import NoEmbeddingModelError, ToolFailedError
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services.configuration import ConfigLevel, ResolvedSetting, SessionConfiguration
from app.services.embedding import write_vector
from app.services.llm.chat import ToolCall
from app.services.llm.frames import ToolFailFrame, ToolResultFrame
from app.services.search.memo_search import search_memos
from app.services.search.ports import SearchHit
from app.services.tools import memo_search as adapter_module
from app.services.tools import seam as seam_module
from app.services.tools.definitions import MEMO_SEARCH, MEMO_SEARCH_NAME
from app.services.tools.memo_search import MemoSearchTool, format_hits
from app.services.tools.seam import (
    PRODUCTION_TOOL_REGISTRY,
    DispatchResult,
    ToolOutcome,
    ToolScope,
    build_tool_scope,
    dispatch,
    offered_tools,
)
from tests.llm_fakes import embedding_vector, fake_factory

#: The seeded instant, in the project's fixed-width UTC text form.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

#: Every id below is above 2^60 = 1152921504606846976 (snowflake-sized).
SNOWFLAKE_FLOOR = 2**60

#: The designated embedding width throughout; 8 is what 024 and 025 use.
DIMENSION = 8

#: The searched term, in every seeded body. Lower case, so FTS5's snippet holds it as-is.
TOKEN = "kaelith"

#: Literals from `context.md`'s literals table — the contract these tests bind to.
ZERO_HIT_CONTENT = "No matching notes."
FAILED_CONTENT = "The tool failed. Continue without its result."
FAILED_CODE = "tool_failed"
EXPECTED_TOOL_NAME = "memo_search"

#: Bound for every asyncio run and every subprocess.
TIMEOUT_SECONDS = 10.0
SUBPROCESS_TIMEOUT_SECONDS = 60.0

USER_A = 1_800_000_000_000_000_001
USER_B = 1_800_000_000_000_000_002

CHARACTER_A1 = 1_800_000_000_000_000_101
CHARACTER_A2 = 1_800_000_000_000_000_102
CHARACTER_B1 = 1_800_000_000_000_000_103

SETUP_A1 = 1_800_000_000_000_000_151
SETUP_A2 = 1_800_000_000_000_000_152

#: `SESSION_A1` carries a setup; `SESSION_A_PLAIN` is the same character with **no** setup.
SESSION_A1 = 1_800_000_000_000_000_201
SESSION_A2 = 1_800_000_000_000_000_202
SESSION_A_PLAIN = 1_800_000_000_000_000_203
SESSION_B1 = 1_800_000_000_000_000_204

SERVER_ID = 1_800_000_000_000_000_901
MODEL_ID = 1_800_000_000_000_000_902

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
    body_override: str | None = None

    @property
    def body(self) -> str:
        if self.body_override is not None:
            return self.body_override
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


# --- the spec's own expectations (D4 applied here, to step 001's hits) ----------------------


def _expected_hits(
    engine: Engine,
    *,
    user_id: int = USER_A,
    character_id: int = CHARACTER_A1,
    setup_id: int | None = SETUP_A1,
    session_id: int = SESSION_A1,
    query_text: str = TOKEN,
) -> list[SearchHit]:
    """Step 001's contracted answer for the same inputs (`002.context.md`): the hit order."""
    with engine.connect() as connection:
        return search_memos(
            connection,
            user_id=user_id,
            character_id=character_id,
            setup_id=setup_id,
            session_id=session_id,
            query_text=query_text,
            client_factory=fake_factory(DIMENSION),
        )


def _expected_line(hit: SearchHit) -> str:
    """D4: `[<level>] <snippet>`, the snippet's whitespace runs collapsed and its ends stripped."""
    return f"[{hit.memo_scope}] {' '.join((hit.snippet or '').split())}"


def _expected_content(hits: Sequence[SearchHit]) -> str:
    """D4: one line per hit in the given order, joined by a newline; `No matching notes.` for none."""
    if not hits:
        return ZERO_HIT_CONTENT
    return "\n".join(_expected_line(hit) for hit in hits)


def _expected_summary(hits: Sequence[SearchHit]) -> str:
    """D4: exactly `<N> memos`, never pluralised away from `memos`."""
    return f"{len(hits)} memos"


def _levels(content: str) -> list[str]:
    """The level literal of each content line, in line order (D4's `[<level>] ` prefix)."""
    return [line[1 : line.index("]")] for line in content.splitlines()]


# --- call wrappers ---------------------------------------------------------------------------

SCOPE_A = ToolScope(user_id=USER_A, session_id=SESSION_A1, character_id=CHARACTER_A1, setup_id=SETUP_A1)
SCOPE_A_PLAIN = ToolScope(
    user_id=USER_A, session_id=SESSION_A_PLAIN, character_id=CHARACTER_A1, setup_id=None
)
SCOPE_A_OTHER = ToolScope(
    user_id=USER_A, session_id=SESSION_A2, character_id=CHARACTER_A2, setup_id=SETUP_A2
)


def _tool() -> MemoSearchTool:
    """The adapter with 024's fake factory injected (construction is keyword-only)."""
    return MemoSearchTool(client_factory=fake_factory(DIMENSION))


def _run(
    engine: Engine,
    scope: ToolScope = SCOPE_A,
    arguments: Mapping[str, object] | None = None,
) -> ToolOutcome:
    """Await `run` on a connection of its own, from a sync test."""
    with engine.connect() as connection:
        return asyncio.run(
            asyncio.wait_for(
                _tool().run(scope, connection, {"query": TOKEN} if arguments is None else arguments),
                timeout=TIMEOUT_SECONDS,
            )
        )


def _build_scope(engine: Engine, user_id: int, session_id: int) -> ToolScope:
    """021's owner-scoped scope builder, which also proves the owner read."""
    with engine.connect() as connection:
        return build_tool_scope(connection, user_id, session_id)


def _dispatch(
    engine: Engine,
    generator: SnowflakeGenerator,
    scope: ToolScope,
    tool: MemoSearchTool,
    arguments: Mapping[str, object] | None = None,
) -> DispatchResult:
    """One call through 021's real `dispatch`, with the real adapter in the registry."""
    call = ToolCall(
        call_id="call-026-002",
        name=MEMO_SEARCH_NAME,
        arguments=json.dumps({"query": TOKEN} if arguments is None else arguments),
    )
    return asyncio.run(
        asyncio.wait_for(
            dispatch(call, scope, [MEMO_SEARCH_NAME], {MEMO_SEARCH_NAME: tool}, engine, generator),
            timeout=TIMEOUT_SECONDS,
        )
    )


def _tool_rows(engine: Engine, session_id: int) -> list[dict[str, object]]:
    with engine.connect() as connection:
        rows = connection.execute(
            select(schema.messages)
            .where(schema.messages.c.session_id == session_id)
            .where(schema.messages.c.role == "tool")
            .order_by(schema.messages.c.id)
        ).all()
    return [dict(row._mapping) for row in rows]


def _assert_no_open_transaction(connection: Connection) -> None:
    assert not connection.in_transaction()
    transaction = connection.begin()
    transaction.rollback()


# --- configuration values (021's shape, file-local) ----------------------------------------


def _bool_setting(value: bool) -> ResolvedSetting[bool]:
    return ResolvedSetting(
        session=value, inherited=None, inherited_level=None, value=value, level=ConfigLevel.SESSION
    )


def _text_setting() -> ResolvedSetting[str]:
    return ResolvedSetting(session=None, inherited=None, inherited_level=None, value=None, level=None)


def _configuration(*, memo: bool, session: bool, web: bool) -> SessionConfiguration:
    return SessionConfiguration(
        model=None,
        system_prompt=_text_setting(),
        tool_memo_search=_bool_setting(memo),
        tool_session_search=_bool_setting(session),
        tool_web_search=_bool_setting(web),
        rp_language=_text_setting(),
        preferred_language=_text_setting(),
    )


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


@pytest.fixture
def generator() -> SnowflakeGenerator:
    return SnowflakeGenerator(node_id=1)


# --- DoD-1: the content, its lines and their order (D4, UC-051, US-063.AC-1) ----------------

LEVEL_USER = 1_800_000_000_000_000_301
LEVEL_CHARACTER = 1_800_000_000_000_000_302
LEVEL_SETUP = 1_800_000_000_000_000_303
LEVEL_SESSION = 1_800_000_000_000_000_304

FOUR_LEVEL_NOTES = (
    _Note(memo_id=LEVEL_USER, scope="user", scope_id=USER_A, marker="aurelian"),
    _Note(memo_id=LEVEL_CHARACTER, scope="character", scope_id=CHARACTER_A1, marker="bellringer"),
    _Note(memo_id=LEVEL_SETUP, scope="setup", scope_id=SETUP_A1, marker="cindermoor"),
    _Note(memo_id=LEVEL_SESSION, scope="session", scope_id=SESSION_A1, marker="dawnwarden"),
)

FOUR_LEVELS = ("user", "character", "setup", "session")


def test_the_content_is_one_level_prefixed_line_per_hit__S026_002_DoD1(engine: Engine) -> None:
    """D4: one `[<level>] <snippet>` line per expected note, four notes → four lines."""
    _seed(engine, FOUR_LEVEL_NOTES)
    expected = _expected_hits(engine)
    assert len(expected) == 4

    outcome = _run(engine)

    lines = outcome.content.splitlines()
    assert len(lines) == 4
    assert lines == [_expected_line(hit) for hit in expected]


def test_each_content_line_names_its_own_level__S026_002_DoD1(engine: Engine) -> None:
    """D4: the level literal of a line is its note's level; all four levels are reached."""
    _seed(engine, FOUR_LEVEL_NOTES)
    expected = _expected_hits(engine)

    outcome = _run(engine)

    assert set(_levels(outcome.content)) == set(FOUR_LEVELS)
    assert _levels(outcome.content) == [str(hit.memo_scope) for hit in expected]


def test_the_line_order_is_the_search_hit_order__S026_002_DoD1(engine: Engine) -> None:
    """D4: the hit order is step 001's (`002.context.md`); the content keeps it."""
    _seed(engine, FOUR_LEVEL_NOTES)
    expected = _expected_hits(engine)

    outcome = _run(engine)

    assert outcome.content == _expected_content(expected)


def test_the_formatter_renders_the_given_hits_in_order__S026_002_DoD1() -> None:
    """D4 over hand-built hits: the formatter is pure and returns `(content, summary)`."""
    hits = (
        SearchHit(kind="memo", id=1, score=0.5, snippet="the first note", memo_scope="user", memo_scope_id=1),
        SearchHit(
            kind="memo", id=2, score=0.4, snippet="the second note", memo_scope="session", memo_scope_id=2
        ),
    )

    content, summary = format_hits(hits)

    assert content == "[user] the first note\n[session] the second note"
    assert summary == "2 memos"


# --- DoD-2: the summary (D4, 021 D6) -------------------------------------------------------

ONLY_NOTE = (_Note(memo_id=1_800_000_000_000_000_311, scope="session", scope_id=SESSION_A1, marker="emberlace"),)


def test_the_summary_counts_the_four_hits__S026_002_DoD2(engine: Engine) -> None:
    """D4: exactly `4 memos` for the four-level chain."""
    _seed(engine, FOUR_LEVEL_NOTES)

    outcome = _run(engine)

    assert outcome.summary == "4 memos"


def test_the_summary_of_one_hit_is_one_memos__S026_002_DoD2(engine: Engine) -> None:
    """D4 fixes the literal: `1 memos`, never pluralised to `1 memo`."""
    _seed(engine, ONLY_NOTE)

    outcome = _run(engine)

    assert outcome.summary == "1 memos"


def test_no_summary_carries_any_note_text__S026_002_DoD2(engine: Engine) -> None:
    """021 D6: the summary never contains content — not a marker, not the shared token."""
    _seed(engine, FOUR_LEVEL_NOTES)

    four = _run(engine).summary

    assert TOKEN not in four
    for note in FOUR_LEVEL_NOTES:
        assert note.marker not in four
        assert note.body not in four


def test_a_single_hit_summary_carries_no_note_text__S026_002_DoD2(engine: Engine) -> None:
    """The same for the one-note chain, whose summary is the shortest it can be."""
    _seed(engine, ONLY_NOTE)

    summary = _run(engine).summary

    assert TOKEN not in summary
    assert ONLY_NOTE[0].marker not in summary


# --- DoD-3: one line per hit, whatever the body's whitespace (D4) ---------------------------

RAGGED_NOTE = (
    _Note(
        memo_id=1_800_000_000_000_000_321,
        scope="session",
        scope_id=SESSION_A1,
        marker="fernholt",
        body_override=f"first line\n\t{TOKEN}\t\n\n   fernholt   \tlast line",
    ),
)


def test_a_body_with_newlines_and_tabs_gives_one_content_line__S026_002_DoD3(engine: Engine) -> None:
    """D4: whitespace runs collapse to one space, so each hit is exactly one line."""
    _seed(engine, RAGGED_NOTE)
    expected = _expected_hits(engine)
    assert len(expected) == 1

    outcome = _run(engine)

    assert "\n" not in outcome.content
    assert "\t" not in outcome.content
    assert len(outcome.content.splitlines()) == 1
    assert outcome.content == _expected_content(expected)
    assert outcome.content.startswith("[session] ")


def test_the_formatter_collapses_whitespace_runs_in_a_snippet__S026_002_DoD3() -> None:
    """D4 over a hand-built hit: runs collapse to one space and the ends are stripped."""
    hit = SearchHit(
        kind="memo",
        id=1,
        score=0.5,
        snippet="  a\n\tb   c \n",
        memo_scope="character",
        memo_scope_id=2,
    )

    content, _ = format_hits([hit])

    assert content == "[character] a b c"


# --- DoD-4: zero hits is a success (D4) ----------------------------------------------------

AWAY_CHARACTER = 1_800_000_000_000_000_331
AWAY_SETUP = 1_800_000_000_000_000_332
AWAY_SESSION = 1_800_000_000_000_000_333

#: Notes only on A1's chain, and none at the user level — so A2's chain matches nothing.
NOTES_OFF_THE_CHAIN = (
    _Note(memo_id=AWAY_CHARACTER, scope="character", scope_id=CHARACTER_A1, marker="gallowmere"),
    _Note(memo_id=AWAY_SETUP, scope="setup", scope_id=SETUP_A1, marker="hazelrook"),
    _Note(memo_id=AWAY_SESSION, scope="session", scope_id=SESSION_A1, marker="ivorysong"),
)


def test_a_chain_matching_nothing_returns_the_no_match_content__S026_002_DoD4(engine: Engine) -> None:
    """D4: zero hits is a success — the content is exactly `No matching notes.`"""
    _seed(engine, NOTES_OFF_THE_CHAIN)
    assert _expected_hits(engine, character_id=CHARACTER_A2, setup_id=SETUP_A2, session_id=SESSION_A2) == []

    outcome = _run(engine, SCOPE_A_OTHER)

    assert outcome.content == ZERO_HIT_CONTENT


def test_a_chain_matching_nothing_summarises_zero_memos__S026_002_DoD4(engine: Engine) -> None:
    """D4: the summary is exactly `0 memos`, and nothing is raised."""
    _seed(engine, NOTES_OFF_THE_CHAIN)

    outcome = _run(engine, SCOPE_A_OTHER)

    assert outcome.summary == "0 memos"


def test_the_formatter_with_no_hits_says_no_matching_notes__S026_002_DoD4() -> None:
    """D4 over an empty sequence: the two literals, with nothing raised."""
    content, summary = format_hits([])

    assert content == ZERO_HIT_CONTENT
    assert summary == "0 memos"


# --- DoD-5: the exclusions hold through the tool (UC-052, US-100.AC-2, US-064.AC-1) ---------

KEPT_NOTE = 1_800_000_000_000_000_341
FORCED_NOTE = 1_800_000_000_000_000_342
DISABLED_NOTE = 1_800_000_000_000_000_343
DISABLED_FORCED_NOTE = 1_800_000_000_000_000_344
B_COLLIDING_NOTE = 1_800_000_000_000_000_345
OTHER_SESSION_NOTE = 1_800_000_000_000_000_346

EXCLUSION_NOTES = (
    _Note(memo_id=KEPT_NOTE, scope="session", scope_id=SESSION_A1, marker="jessamine"),
    _Note(
        memo_id=FORCED_NOTE,
        scope="session",
        scope_id=SESSION_A1,
        marker="kestrelbane",
        is_forced=True,
    ),
    _Note(
        memo_id=DISABLED_NOTE,
        scope="session",
        scope_id=SESSION_A1,
        marker="lanternmere",
        is_enabled=False,
    ),
    _Note(
        memo_id=DISABLED_FORCED_NOTE,
        scope="session",
        scope_id=SESSION_A1,
        marker="mirebloom",
        is_enabled=False,
        is_forced=True,
    ),
    _Note(
        memo_id=B_COLLIDING_NOTE,
        scope="session",
        scope_id=SESSION_A1,
        marker="nightreed",
        user_id=USER_B,
    ),
    _Note(memo_id=OTHER_SESSION_NOTE, scope="session", scope_id=SESSION_A2, marker="oakenshade"),
)

EXCLUDED_MARKERS = ("kestrelbane", "lanternmere", "mirebloom", "nightreed", "oakenshade")


def test_no_excluded_notes_text_reaches_the_content__S026_002_DoD5(engine: Engine) -> None:
    """Each excluded note carries the token and a vector, so its absence is the predicate's work."""
    _seed(engine, EXCLUSION_NOTES)

    content = _run(engine).content

    for marker in EXCLUDED_MARKERS:
        assert marker not in content


def test_the_searchable_notes_line_is_the_content__S026_002_DoD5(engine: Engine) -> None:
    """US-099.AC-2: the enabled, unforced note of the chain is the one line that appears."""
    _seed(engine, EXCLUSION_NOTES)
    expected = _expected_hits(engine)
    assert [hit.id for hit in expected] == [KEPT_NOTE]

    outcome = _run(engine)

    assert "jessamine" in outcome.content
    assert outcome.content == _expected_content(expected)
    assert outcome.summary == "1 memos"


# --- DoD-6: no setup, no gap (US-065.AC-1) -------------------------------------------------

PLAIN_USER = 1_800_000_000_000_000_351
PLAIN_CHARACTER = 1_800_000_000_000_000_352
PLAIN_SESSION = 1_800_000_000_000_000_353
PLAIN_UNREACHED_SETUP = 1_800_000_000_000_000_354

NO_SETUP_NOTES = (
    _Note(memo_id=PLAIN_USER, scope="user", scope_id=USER_A, marker="pinefall"),
    _Note(memo_id=PLAIN_CHARACTER, scope="character", scope_id=CHARACTER_A1, marker="quillraven"),
    _Note(memo_id=PLAIN_SESSION, scope="session", scope_id=SESSION_A_PLAIN, marker="riverhelm"),
    _Note(memo_id=PLAIN_UNREACHED_SETUP, scope="setup", scope_id=SETUP_A1, marker="stonewren"),
)


def test_a_scope_without_a_setup_gives_the_three_levels_lines__S026_002_DoD6(engine: Engine) -> None:
    """US-065.AC-1: one line each for the user, character and session notes, and no gap."""
    _seed(engine, NO_SETUP_NOTES)
    expected = _expected_hits(engine, setup_id=None, session_id=SESSION_A_PLAIN)
    assert len(expected) == 3

    outcome = _run(engine, SCOPE_A_PLAIN)

    assert len(outcome.content.splitlines()) == 3
    assert set(_levels(outcome.content)) == {"user", "character", "session"}
    assert outcome.content == _expected_content(expected)
    assert outcome.summary == "3 memos"


def test_a_scope_without_a_setup_reaches_no_setup_note__S026_002_DoD6(engine: Engine) -> None:
    """Stated as an absence: the setup-level note carries the token and still never appears."""
    _seed(engine, NO_SETUP_NOTES)

    content = _run(engine, SCOPE_A_PLAIN).content

    assert "stonewren" not in content
    assert "setup" not in _levels(content)


# --- DoD-7: the ids come only from the scope (D6, R5, US-064.AC-1) --------------------------

MINE_SESSION_NOTE = 1_800_000_000_000_000_361
MINE_USER_NOTE = 1_800_000_000_000_000_362
B_USER_NOTE = 1_800_000_000_000_000_363
B_SESSION_NOTE = 1_800_000_000_000_000_364

SPOOFING_NOTES = (
    _Note(memo_id=MINE_USER_NOTE, scope="user", scope_id=USER_A, marker="thornvale"),
    _Note(memo_id=MINE_SESSION_NOTE, scope="session", scope_id=SESSION_A1, marker="umbercoil"),
    _Note(memo_id=B_USER_NOTE, scope="user", scope_id=USER_B, marker="valebrook", user_id=USER_B),
    _Note(
        memo_id=B_SESSION_NOTE, scope="session", scope_id=SESSION_B1, marker="wyrmgate", user_id=USER_B
    ),
)

#: Every key but `query` must be ignored (D6).
SPOOFING_ARGUMENTS = {
    "query": TOKEN,
    "user_id": USER_B,
    "session_id": SESSION_B1,
    "character_id": CHARACTER_B1,
    "setup_id": SETUP_A2,
    "scope": "user",
}


def test_arguments_naming_another_user_change_nothing__S026_002_DoD7(engine: Engine) -> None:
    """D6: only `query` is read, so the content is the same as with `{"query": …}` alone."""
    _seed(engine, SPOOFING_NOTES)

    plain = _run(engine)
    spoofed = _run(engine, SCOPE_A, SPOOFING_ARGUMENTS)

    assert spoofed.content == plain.content
    assert spoofed.summary == plain.summary


def test_nothing_of_another_user_appears_however_the_arguments_ask__S026_002_DoD7(engine: Engine) -> None:
    """R5 / US-064.AC-1: B's notes carry the token and a vector, and still never appear."""
    _seed(engine, SPOOFING_NOTES)

    content = _run(engine, SCOPE_A, SPOOFING_ARGUMENTS).content

    assert "valebrook" not in content
    assert "wyrmgate" not in content
    assert "thornvale" in content
    assert "umbercoil" in content


# --- DoD-8: bad arguments raise `ToolFailedError` (D5) --------------------------------------


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"query": 7},
        {"query": None},
        {"query": ["kaelith"]},
    ],
    ids=["missing", "integer", "none", "list"],
)
def test_arguments_without_a_string_query_raise_tool_failed__S026_002_DoD8(
    engine: Engine, arguments: Mapping[str, object]
) -> None:
    """D5: a missing or non-string `query` is the tool's own failure."""
    _seed(engine, FOUR_LEVEL_NOTES)

    with engine.connect() as connection:
        with pytest.raises(ToolFailedError) as raised:
            asyncio.run(
                asyncio.wait_for(
                    _tool().run(SCOPE_A, connection, arguments), timeout=TIMEOUT_SECONDS
                )
            )

    assert raised.value.detail["tool"] == EXPECTED_TOOL_NAME


# --- DoD-9: the search runs off the event loop (D3) -----------------------------------------


def test_run_awaited_inside_a_running_loop_returns_hits__S026_002_DoD9(engine: Engine) -> None:
    """D3: awaited from inside a running loop, the sync port still runs — off that loop."""
    _seed(engine, FOUR_LEVEL_NOTES)
    tool = _tool()

    async def scenario() -> ToolOutcome:
        with engine.connect() as connection:
            return await tool.run(SCOPE_A, connection, {"query": TOKEN})

    outcome = asyncio.run(asyncio.wait_for(scenario(), timeout=TIMEOUT_SECONDS))

    assert len(outcome.content.splitlines()) == 4
    assert outcome.summary == "4 memos"
    assert outcome.content != ZERO_HIT_CONTENT


# --- DoD-10: no transaction left open, on either exit (D5, 021 D6) --------------------------


def test_a_successful_run_leaves_no_transaction_in_progress__S026_002_DoD10(engine: Engine) -> None:
    """D5: the connection the seam handed in is left with no transaction in progress."""
    _seed(engine, FOUR_LEVEL_NOTES)

    with engine.connect() as connection:
        outcome = asyncio.run(
            asyncio.wait_for(
                _tool().run(SCOPE_A, connection, {"query": TOKEN}), timeout=TIMEOUT_SECONDS
            )
        )

        assert outcome.summary == "4 memos"
        _assert_no_open_transaction(connection)


def test_a_failed_run_leaves_no_transaction_in_progress__S026_002_DoD10(engine: Engine) -> None:
    """D5: the same guarantee after the port's `NoEmbeddingModelError` propagated."""
    _seed(engine, FOUR_LEVEL_NOTES, designate=False)

    with engine.connect() as connection:
        with pytest.raises(NoEmbeddingModelError):
            asyncio.run(
                asyncio.wait_for(
                    _tool().run(SCOPE_A, connection, {"query": TOKEN}), timeout=TIMEOUT_SECONDS
                )
            )

        _assert_no_open_transaction(connection)


# --- DoD-11: the registration (D3, 021 D5) --------------------------------------------------


def test_the_production_registry_holds_exactly_memo_search__S026_002_DoD11() -> None:
    """D3: one entry, keyed `memo_search`, whose value's `name` is `memo_search`."""
    assert len(PRODUCTION_TOOL_REGISTRY) == 1
    assert list(PRODUCTION_TOOL_REGISTRY) == [EXPECTED_TOOL_NAME]
    assert PRODUCTION_TOOL_REGISTRY[EXPECTED_TOOL_NAME].name == EXPECTED_TOOL_NAME


def test_the_adapters_name_is_the_declared_name__S026_002_DoD11() -> None:
    """The adapter answers the protocol's `name` with the declaration's own constant."""
    assert MemoSearchTool.name == EXPECTED_TOOL_NAME
    assert _tool().name == MEMO_SEARCH_NAME


def test_offered_tools_over_the_production_registry_is_the_declaration__S026_002_DoD11() -> None:
    """021 D5: all three switches on → exactly `definitions.py`'s `memo_search` declaration."""
    offered = offered_tools(_configuration(memo=True, session=True, web=True), PRODUCTION_TOOL_REGISTRY)

    assert list(offered) == [MEMO_SEARCH]
    function = offered[0]["function"]
    assert function["name"] == EXPECTED_TOOL_NAME
    assert list(function["parameters"]["properties"]) == ["query"]
    assert function["parameters"]["required"] == ["query"]


def test_offered_tools_with_the_memo_switch_off_offers_nothing__S026_002_DoD11() -> None:
    """021 D5: registered is not enough — the switch gates it."""
    offered = offered_tools(_configuration(memo=False, session=True, web=True), PRODUCTION_TOOL_REGISTRY)

    assert list(offered) == []


# --- DoD-12: failure through the real seam (US-066.AC-1, UC-051 exception flow, R9) ---------


def test_dispatch_with_no_designated_model_fails_the_tool_and_raises_nothing__S026_002_DoD12(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """R9: the failure is reported as a tool result and the exchange carries on."""
    _seed(engine, FOUR_LEVEL_NOTES, designate=False)
    scope = _build_scope(engine, USER_A, SESSION_A1)

    result = _dispatch(engine, generator, scope, _tool())

    assert isinstance(result.frame, ToolFailFrame)
    assert result.frame.tool == EXPECTED_TOOL_NAME
    assert result.frame.code == FAILED_CODE


def test_dispatch_with_no_designated_model_tells_the_model_the_tool_failed__S026_002_DoD12(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """US-066.AC-1: the tool message content is exactly 021's failure sentence."""
    _seed(engine, FOUR_LEVEL_NOTES, designate=False)
    scope = _build_scope(engine, USER_A, SESSION_A1)

    result = _dispatch(engine, generator, scope, _tool())

    assert result.message.content == FAILED_CONTENT


def test_dispatch_with_no_designated_model_writes_one_failed_tool_row__S026_002_DoD12(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """021 D7: exactly one tool row is kept, naming `memo_search`."""
    _seed(engine, FOUR_LEVEL_NOTES, designate=False)
    scope = _build_scope(engine, USER_A, SESSION_A1)

    _dispatch(engine, generator, scope, _tool())

    rows = _tool_rows(engine, SESSION_A1)
    assert len(rows) == 1
    assert rows[0]["tool_name"] == EXPECTED_TOOL_NAME


# --- DoD-13: success through the real seam (UC-051, 021 D6) ---------------------------------


def test_dispatch_returns_a_tool_result_frame_summarising_the_hits__S026_002_DoD13(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """UC-051: the frame's summary is `<N> memos` for the expected hit count."""
    _seed(engine, FOUR_LEVEL_NOTES)
    expected = _expected_hits(engine)
    scope = _build_scope(engine, USER_A, SESSION_A1)

    result = _dispatch(engine, generator, scope, _tool())

    assert isinstance(result.frame, ToolResultFrame)
    assert result.frame.tool == EXPECTED_TOOL_NAME
    assert result.frame.summary == _expected_summary(expected)


def test_dispatch_gives_the_model_the_formatted_hits__S026_002_DoD13(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """UC-051: the tool message carries D4's content for those hits, and no failure sentence."""
    _seed(engine, FOUR_LEVEL_NOTES)
    expected = _expected_hits(engine)
    scope = _build_scope(engine, USER_A, SESSION_A1)

    result = _dispatch(engine, generator, scope, _tool())

    assert result.message.content == _expected_content(expected)
    assert result.message.content != FAILED_CONTENT


# --- DoD-14: the import shape (D3) ---------------------------------------------------------

BACKEND_DIRECTORY = Path(__file__).resolve().parent.parent

ADAPTER_MODULE = "app.services.tools.memo_search"
SEAM_MODULE = "app.services.tools.seam"

IMPORT_CASES = (
    f"import {ADAPTER_MODULE}",
    f"import {SEAM_MODULE}",
    f"import {ADAPTER_MODULE}; import {SEAM_MODULE}",
    f"import {SEAM_MODULE}; import {ADAPTER_MODULE}",
)


def _module_source(module: object) -> str:
    module_file = getattr(module, "__file__", None)
    assert module_file is not None
    return Path(module_file).read_text(encoding="utf-8")


def _imported_roots(source: str) -> set[str]:
    """The top-level package of every import in the source, read as text (no `sys.modules`)."""
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("code", IMPORT_CASES, ids=["adapter", "seam", "adapter-first", "seam-first"])
def test_each_module_imports_cleanly_in_a_fresh_interpreter__S026_002_DoD14(code: str) -> None:
    """D3: no import cycle — either module imports alone, and either order works."""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIRECTORY,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("module_name", ["adapter", "seam"])
def test_neither_module_imports_a_web_framework__S026_002_DoD14(module_name: str) -> None:
    """`context.md` cross-cutting constraints: a service imports no web framework.

    Checked against the module **source**, not `sys.modules`: `app/errors.py` imports the web
    framework and the seam imports `app.errors`, so a `sys.modules` probe would answer a
    question this step does not own.
    """
    module = adapter_module if module_name == "adapter" else seam_module

    roots = _imported_roots(_module_source(module))

    assert roots & {"fastapi", "starlette"} == set()
