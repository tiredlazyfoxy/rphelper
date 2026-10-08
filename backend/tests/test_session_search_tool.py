"""`services/tools/session_search.py` — feature 027, step 003 (DoD-1..14).

Every expected value comes from the **spec**, never from the implementation:
`docs/plans/027.session-search-tool/003.session-search-tool-adapter.md` (Interface intent and
Definition of done), `003.context.md` (the seam pointers, the one worker-thread call and the
seeding notes) and the feature `context.md` — **D3** (the block format: the header
`### Session <YYYY-MM-DD> · setup: <name>` or `### Session <YYYY-MM-DD> · no setup`, then `\\n`,
then the excerpt or `(no settled entries)`; blocks joined by `\\n\\n`; `No matching sessions.`
for no hits; the summary `<N> sessions`; no persona, no setup description, no ids), **D5**
(failure raises and leaves no transaction open), **D6** (one `asyncio.to_thread` call, and the
registration beside `memo_search`), **D7** (the ids come only from the `ToolScope`) and the
literals table.

Bindings come from `## Skeleton` → "Step 003 — frozen interface (2026-10-05)" in `status.md`:

    def format_excerpts(excerpts: Sequence[SessionExcerpt]) -> tuple[str, str]   # (content, summary)

    @dataclass(frozen=True, kw_only=True)
    class SessionSearchTool:
        client_factory: LlmClientFactory | None = None
        timeout_seconds: float | None = None
        name: ClassVar[str] = SESSION_SEARCH_NAME
        async def run(self, scope, connection, arguments) -> ToolOutcome

Construction is keyword-only, and `SessionSearchTool()` — both injections left at `None` — is
the production instance the registry holds. A test that wants 024's fake embedder writes
`SessionSearchTool(client_factory=fake_factory(8))`. **Nothing here binds to the name of the
worker-thread callable inside `run`**, which the skeleton record deliberately left unfrozen;
DoD-9 pins its behaviour instead.

The seam names are 021's, as built: `ToolScope(user_id, session_id, character_id, setup_id)`,
`ToolOutcome(content, summary)`, `PRODUCTION_TOOL_REGISTRY`, `build_tool_scope`,
`offered_tools`, `dispatch(call, scope, offered, registry, engine, generator)`.

How the expectations are derived
-------------------------------
* **The port is never mocked and nothing is monkeypatched.** `session_vec` is built only
  through 024's real path: a raw `llm_servers` + `models` designation at dimension 8 with
  `api_key_ref=None`, then `refresh_session_vectors` with `tests/llm_fakes.py`'s fake factory,
  so the persona, the setup description and the settled entries really are in the embedded
  text. The provider arrives through the frozen `client_factory=` keyword.
* **Two sanctioned reads of already-verified contracts** (`003.context.md` "Test seeding
  notes"): the expected **hit order** comes from calling step `001`'s `search_sessions` with
  the same inputs, and the expected **blocks** come from D3 applied **here** to the seeded rows
  (the stored `created_at`'s date, the seeded setup name, the seeded settled texts). Nothing is
  ever read back out of `format_excerpts` or `run` to build an expectation.
* **Absences are proved with data that would match** (`context.md` cross-cutting constraints):
  every excluded session shares the persona, the setup description and the settled entries of
  the included past session P, differing only by the unique marker word that makes its absence
  assertable — and the scenario holds exactly one in-scope past session, so the summary
  `1 sessions` independently shows that no twin came back.
* **The query is always a session's exact composed text**, read from 024's
  `compose_session_text`. The fake embedder is deterministic, **not** semantic, so nothing here
  claims a paraphrase finds a session — that is DoD-16, `[manual/live]` (`context.md` "What the
  fake embedder can prove — and what it cannot").

Each test name ends `__S027_003_DoD<n>` with the DoD item it covers. DoD-15 (the amendments to
021's and 026's four test files) is not a test of its own; DoD-16 and DoD-17 are `[manual/live]`.

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
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, Table, select

from app.db import schema
from app.errors import NoEmbeddingModelError, ToolFailedError
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services.configuration import ConfigLevel, ResolvedSetting, SessionConfiguration
from app.services.llm.chat import ToolCall
from app.services.llm.frames import ToolFailFrame, ToolResultFrame
from app.services.search.ports import SearchHit
from app.services.search.session_search import SessionExcerpt, search_sessions
from app.services.session_index import compose_session_text, refresh_session_vectors
from app.services.tools import seam as seam_module
from app.services.tools import session_search as adapter_module
from app.services.tools.definitions import MEMO_SEARCH, SESSION_SEARCH, SESSION_SEARCH_NAME
from app.services.tools.seam import (
    PRODUCTION_TOOL_REGISTRY,
    DispatchResult,
    ToolOutcome,
    ToolScope,
    build_tool_scope,
    dispatch,
    offered_tools,
)
from app.services.tools.session_search import SessionSearchTool, format_excerpts
from tests.llm_fakes import fake_factory

#: The seeded instant, in the project's fixed-width UTC text form.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

#: The instant rows seeded already settled carry.
SEEDED_SETTLED_AT = "2025-12-31T00:00:00.000000+00:00"

#: The instant an archived session carries.
ARCHIVED_AT = "2026-08-01T00:00:00.000000+00:00"

#: Every id below is above 2^60 = 1152921504606846976 (snowflake-sized).
SNOWFLAKE_FLOOR = 2**60

#: The designated embedding width throughout; 8 is what 024 and 025 use.
DIMENSION = 8

#: Bound for every asyncio run and every subprocess.
TIMEOUT_SECONDS = 10.0
SUBPROCESS_TIMEOUT_SECONDS = 60.0

# --- D3's literals, written out from `context.md`'s literals table ---------------------------

#: ` · ` — space, U+00B7 MIDDLE DOT, space.
MIDDLE_DOT = "·"

#: U+2026, prepended with no following space.
ELLIPSIS = "…"

EXCERPT_CHARS = 1500
NO_ENTRIES_BODY = "(no settled entries)"
ZERO_HIT_CONTENT = "No matching sessions."
EXPECTED_TOOL_NAME = "session_search"
MEMO_TOOL_NAME = "memo_search"

#: 021's literals, as the seam reports a failure.
FAILED_CONTENT = "The tool failed. Continue without its result."
FAILED_CODE = "tool_failed"

# --- the texts the composed session text is built from (024's three sources) -----------------

#: The one distinctive token every seeded entry carries.
TOKEN = "tidewatch"

#: The persona marker (DoD-4): it must never reach the content. Shared by all three characters.
PERSONA_MARKER = "lampwright"
PERSONA = f"Kaelith the {PERSONA_MARKER}, who keeps the beacons of the drowned coast."

#: The setup-description marker (DoD-4): it must never reach the content either.
DESCRIPTION_MARKER = "quaymarket"
SETUP_DESCRIPTION = f"The {DESCRIPTION_MARKER} at the harbour, three nights after the spring tide."

#: D3's `<setup name>` for the one named setup the plan asks for.
HARBOUR_NAME = "Harbour Night"
TWIN_SETUP_NAME = "Twin Harbour Night"
B_SETUP_NAME = "B's Harbour Night"

ENTRY_ONE = f"{TOKEN}: Kaelith climbed the stair and found the great lens cracked."
ENTRY_TWO = f"((Agreed: the beacon stays lit until the {TOKEN} turns.))"
ENTRY_THREE = f"{TOKEN}: the ferryman counted the lanterns twice and said nothing."
CURRENT_ENTRY = f"{TOKEN}: the page still being written tonight, unfinished."

#: DoD-2's long session: the joined text must exceed 1500 characters.
LONG_ENTRY_ONE = f"{TOKEN}: the first long entry. " + "Lanternlight lies flat on the water. " * 40
LONG_ENTRY_TWO = f"{TOKEN}: the second long entry. " + "The tide returns before dawn. " * 20

#: DoD-6's markers: one per excluded session, the only difference from P's entries.
MARKER_CURRENT = "fogbellow"
MARKER_ARCHIVED = "saltquill"
MARKER_OTHER_CHARACTER = "gullspire"
MARKER_OTHER_USER = "brinehollow"
EXCLUDED_MARKERS = (MARKER_CURRENT, MARKER_ARCHIVED, MARKER_OTHER_CHARACTER, MARKER_OTHER_USER)

USER_A = 1_271_000_000_000_000_001
USER_B = 1_271_000_000_000_000_002

CHAR_A1 = 1_271_000_000_000_000_101
CHAR_A2 = 1_271_000_000_000_000_102
CHAR_B1 = 1_271_000_000_000_000_103

SETUP_HARBOUR = 1_271_000_000_000_000_151
SETUP_TWIN = 1_271_000_000_000_000_152
SETUP_B = 1_271_000_000_000_000_153

SERVER_ID = 1_271_000_000_000_000_901
MODEL_ID = 1_271_000_000_000_000_902

#: Session ids are spaced by ten; a session's settled rows take `session_id + 1`, `+ 2`, …
S_WITH_SETUP = 1_271_000_000_000_002_001
S_NO_SETUP = 1_271_000_000_000_002_011
S_NO_ENTRIES = 1_271_000_000_000_002_021
S_MAIN_CURRENT = 1_271_000_000_000_002_031
S_LONG = 1_271_000_000_000_002_041
S_LONG_CURRENT = 1_271_000_000_000_002_051
S_ZERO_CURRENT = 1_271_000_000_000_002_061
S_ZERO_ARCHIVED = 1_271_000_000_000_002_071
S_ZERO_OTHER_CHARACTER = 1_271_000_000_000_002_081
S_ZERO_OF_B = 1_271_000_000_000_002_091
S_PAST = 1_271_000_000_000_002_101
S_TWIN_CURRENT = 1_271_000_000_000_002_111
S_TWIN_ARCHIVED = 1_271_000_000_000_002_121
S_TWIN_CHARACTER = 1_271_000_000_000_002_131
S_TWIN_USER = 1_271_000_000_000_002_141

#: Distinct stored `created_at` values, so each block's header date is its own (D3).
DATE_WITH_SETUP = "2026-03-14T12:00:00.000000+00:00"
DATE_NO_SETUP = "2026-04-02T12:00:00.000000+00:00"
DATE_NO_ENTRIES = "2026-05-20T12:00:00.000000+00:00"
DATE_MAIN_CURRENT = "2026-06-01T12:00:00.000000+00:00"
DATE_LONG = "2026-02-09T12:00:00.000000+00:00"
DATE_PAST = "2026-07-04T12:00:00.000000+00:00"

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


def _insert_character(engine: Engine, *, character_id: int, user_id: int, name: str, sheet: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.characters.insert().values(
                id=character_id,
                user_id=user_id,
                name=name,
                sheet=sheet,
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_setup(
    engine: Engine,
    *,
    setup_id: int,
    user_id: int,
    character_id: int,
    name: str,
    description: str,
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
    """Raw-insert one `sessions` row (`context.md` (A): no title, name or partner column)."""
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
    role: str = "user",
    kind: str | None = None,
    settled_at: str | None = SEEDED_SETTLED_AT,
) -> None:
    """Raw-insert one `messages` row; `settled_at` set and `related_to` null is a record row."""
    with engine.begin() as connection:
        connection.execute(
            schema.messages.insert().values(
                id=message_id,
                user_id=user_id,
                session_id=session_id,
                role=role,
                kind=kind,
                text=body,
                related_to=None,
                settled_at=settled_at,
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


def _remove_designation(engine: Engine) -> None:
    """Undesignate every model, leaving the vectors already written in place (DoD-10, DoD-12)."""
    with engine.begin() as connection:
        connection.execute(_models().update().values(is_embedding_designated=False))


# --- the seeded sessions, and D3 applied to them ---------------------------------------------


@dataclasses.dataclass(frozen=True)
class _Seeded:
    """One seeded session and everything D3 needs to predict its block from the seeded rows."""

    session_id: int
    created_at: str
    setup_name: str | None
    entries: tuple[str, ...] = ()
    user_id: int = USER_A
    character_id: int = CHAR_A1
    setup_id: int | None = None
    archived_at: str | None = None


def _seed(engine: Engine, sessions: Sequence[_Seeded]) -> None:
    """The rows, the designation, then `session_vec` through 024's real refresh path."""
    for seeded in sessions:
        _insert_session(
            engine,
            session_id=seeded.session_id,
            user_id=seeded.user_id,
            character_id=seeded.character_id,
            setup_id=seeded.setup_id,
            archived_at=seeded.archived_at,
            created_at=seeded.created_at,
        )
        for offset, body in enumerate(seeded.entries, start=1):
            _insert_message(
                engine,
                message_id=seeded.session_id + offset,
                session_id=seeded.session_id,
                body=body,
                user_id=seeded.user_id,
            )
    _seed_designation(engine)
    factory = fake_factory(DIMENSION)
    with engine.begin() as connection:
        for seeded in sessions:
            refresh_session_vectors(
                connection, seeded.user_id, [seeded.session_id], client_factory=factory
            )


def _expected_excerpt(entries: Sequence[str]) -> str:
    """D3: the settled texts in id order joined by `\\n\\n`, empties skipped, tail-bounded."""
    joined = "\n\n".join(entry for entry in entries if entry)
    if len(joined) > EXCERPT_CHARS:
        return ELLIPSIS + joined[-EXCERPT_CHARS:]
    return joined


def _expected_header(seeded: _Seeded) -> str:
    """D3: `### Session <YYYY-MM-DD> · setup: <name>`, or the `no setup` form."""
    calendar_date = seeded.created_at[:10]
    if seeded.setup_name is None:
        return f"### Session {calendar_date} {MIDDLE_DOT} no setup"
    return f"### Session {calendar_date} {MIDDLE_DOT} setup: {seeded.setup_name}"


def _expected_block(seeded: _Seeded) -> str:
    """D3: the header, `\\n`, then the excerpt or `(no settled entries)`."""
    excerpt = _expected_excerpt(seeded.entries)
    return f"{_expected_header(seeded)}\n{excerpt if excerpt else NO_ENTRIES_BODY}"


def _expected_content(hits: Sequence[SearchHit], sessions: Sequence[_Seeded]) -> str:
    """D3: one block per hit in hit order, joined by `\\n\\n`; the zero-hit sentence for none."""
    by_id = {seeded.session_id: seeded for seeded in sessions}
    if not hits:
        return ZERO_HIT_CONTENT
    return "\n\n".join(_expected_block(by_id[hit.id]) for hit in hits)


def _expected_summary(hits: Sequence[SearchHit]) -> str:
    """D3: exactly `<N> sessions`, never pluralised away from `sessions`."""
    return f"{len(hits)} sessions"


def _compose(engine: Engine, session_id: int, *, user_id: int = USER_A) -> str:
    """024's composed text for one session — the query that puts that session at distance zero."""
    with engine.connect() as connection:
        return compose_session_text(connection, user_id, session_id)


def _expected_hits(
    engine: Engine,
    *,
    query_text: str,
    current_session_id: int,
    character_id: int = CHAR_A1,
    user_id: int = USER_A,
) -> list[SearchHit]:
    """Step `001`'s contracted answer for the same inputs (`003.context.md`): the hit order."""
    with engine.connect() as connection:
        return search_sessions(
            connection,
            user_id=user_id,
            character_id=character_id,
            current_session_id=current_session_id,
            query_text=query_text,
            client_factory=fake_factory(DIMENSION),
        )


# --- call wrappers ---------------------------------------------------------------------------

MAIN_SCOPE = ToolScope(
    user_id=USER_A, session_id=S_MAIN_CURRENT, character_id=CHAR_A1, setup_id=SETUP_HARBOUR
)
LONG_SCOPE = ToolScope(user_id=USER_A, session_id=S_LONG_CURRENT, character_id=CHAR_A1, setup_id=None)
ZERO_SCOPE = ToolScope(
    user_id=USER_A, session_id=S_ZERO_CURRENT, character_id=CHAR_A1, setup_id=SETUP_HARBOUR
)
TWIN_SCOPE = ToolScope(
    user_id=USER_A, session_id=S_TWIN_CURRENT, character_id=CHAR_A1, setup_id=SETUP_HARBOUR
)


def _tool() -> SessionSearchTool:
    """The adapter with 024's fake factory injected (construction is keyword-only)."""
    return SessionSearchTool(client_factory=fake_factory(DIMENSION))


def _run(engine: Engine, scope: ToolScope, arguments: Mapping[str, object]) -> ToolOutcome:
    """Await `run` on a connection of its own, from a sync test."""
    with engine.connect() as connection:
        return asyncio.run(
            asyncio.wait_for(_tool().run(scope, connection, arguments), timeout=TIMEOUT_SECONDS)
        )


def _build_scope(engine: Engine, user_id: int, session_id: int) -> ToolScope:
    """021's owner-scoped scope builder, which also proves the owner read."""
    with engine.connect() as connection:
        return build_tool_scope(connection, user_id, session_id)


def _dispatch(
    engine: Engine,
    generator: SnowflakeGenerator,
    scope: ToolScope,
    tool: SessionSearchTool,
    arguments: Mapping[str, object],
) -> DispatchResult:
    """One call through 021's real `dispatch`, with the real adapter in the registry."""
    call = ToolCall(
        call_id="call-027-003", name=SESSION_SEARCH_NAME, arguments=json.dumps(arguments)
    )
    return asyncio.run(
        asyncio.wait_for(
            dispatch(call, scope, [SESSION_SEARCH_NAME], {SESSION_SEARCH_NAME: tool}, engine, generator),
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


# --- configuration values (021's shape, file-local) ------------------------------------------


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


# --- fixtures --------------------------------------------------------------------------------


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """Two users, three characters sharing one persona, three setups sharing one description.

    Sessions are seeded per test. No virtual table and no designated model: `create_all` leaves
    the search tables absent and designates nothing, so each test opts into what it needs.
    """
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="aster")
    _insert_user(db_engine, user_id=USER_B, username="briar")
    _insert_character(db_engine, character_id=CHAR_A1, user_id=USER_A, name="Kaelith", sheet=PERSONA)
    _insert_character(db_engine, character_id=CHAR_A2, user_id=USER_A, name="Kaelith again", sheet=PERSONA)
    _insert_character(db_engine, character_id=CHAR_B1, user_id=USER_B, name="Kaelith of B", sheet=PERSONA)
    _insert_setup(
        db_engine,
        setup_id=SETUP_HARBOUR,
        user_id=USER_A,
        character_id=CHAR_A1,
        name=HARBOUR_NAME,
        description=SETUP_DESCRIPTION,
    )
    _insert_setup(
        db_engine,
        setup_id=SETUP_TWIN,
        user_id=USER_A,
        character_id=CHAR_A2,
        name=TWIN_SETUP_NAME,
        description=SETUP_DESCRIPTION,
    )
    _insert_setup(
        db_engine,
        setup_id=SETUP_B,
        user_id=USER_B,
        character_id=CHAR_B1,
        name=B_SETUP_NAME,
        description=SETUP_DESCRIPTION,
    )
    return db_engine


@pytest.fixture
def generator() -> SnowflakeGenerator:
    return SnowflakeGenerator(node_id=1)


# --- the scenarios ---------------------------------------------------------------------------

#: DoD-1's three past sessions — one with the named setup, one without a setup, one with no
#: settled entries — plus the session being composed in, which is never a result.
MAIN_WITH_SETUP = _Seeded(
    session_id=S_WITH_SETUP,
    created_at=DATE_WITH_SETUP,
    setup_name=HARBOUR_NAME,
    setup_id=SETUP_HARBOUR,
    entries=(ENTRY_ONE, ENTRY_TWO),
)
MAIN_NO_SETUP = _Seeded(
    session_id=S_NO_SETUP,
    created_at=DATE_NO_SETUP,
    setup_name=None,
    setup_id=None,
    entries=(ENTRY_THREE,),
)
MAIN_NO_ENTRIES = _Seeded(
    session_id=S_NO_ENTRIES, created_at=DATE_NO_ENTRIES, setup_name=None, setup_id=None, entries=()
)
MAIN_CURRENT = _Seeded(
    session_id=S_MAIN_CURRENT,
    created_at=DATE_MAIN_CURRENT,
    setup_name=HARBOUR_NAME,
    setup_id=SETUP_HARBOUR,
    entries=(CURRENT_ENTRY,),
)
SCENARIO_MAIN = (MAIN_WITH_SETUP, MAIN_NO_SETUP, MAIN_NO_ENTRIES, MAIN_CURRENT)

MAIN_ENTRY_TEXTS = (ENTRY_ONE, ENTRY_TWO, ENTRY_THREE)

#: DoD-2's scenario: exactly one in-scope past session, whose settled text is over the bound.
LONG_PAST = _Seeded(
    session_id=S_LONG,
    created_at=DATE_LONG,
    setup_name=HARBOUR_NAME,
    setup_id=SETUP_HARBOUR,
    entries=(LONG_ENTRY_ONE, LONG_ENTRY_TWO),
)
LONG_CURRENT = _Seeded(
    session_id=S_LONG_CURRENT,
    created_at=DATE_MAIN_CURRENT,
    setup_name=None,
    setup_id=None,
    entries=(CURRENT_ENTRY,),
)
SCENARIO_LONG = (LONG_PAST, LONG_CURRENT)

#: DoD-5's scenario: the current session, plus only excluded sessions.
ZERO_CURRENT = _Seeded(
    session_id=S_ZERO_CURRENT,
    created_at=DATE_MAIN_CURRENT,
    setup_name=HARBOUR_NAME,
    setup_id=SETUP_HARBOUR,
    entries=(CURRENT_ENTRY,),
)
ZERO_ARCHIVED = _Seeded(
    session_id=S_ZERO_ARCHIVED,
    created_at=DATE_WITH_SETUP,
    setup_name=HARBOUR_NAME,
    setup_id=SETUP_HARBOUR,
    entries=(ENTRY_ONE, ENTRY_TWO),
    archived_at=ARCHIVED_AT,
)
ZERO_OTHER_CHARACTER = _Seeded(
    session_id=S_ZERO_OTHER_CHARACTER,
    created_at=DATE_WITH_SETUP,
    setup_name=TWIN_SETUP_NAME,
    character_id=CHAR_A2,
    setup_id=SETUP_TWIN,
    entries=(ENTRY_ONE, ENTRY_TWO),
)
ZERO_OF_B = _Seeded(
    session_id=S_ZERO_OF_B,
    created_at=DATE_WITH_SETUP,
    setup_name=B_SETUP_NAME,
    user_id=USER_B,
    character_id=CHAR_B1,
    setup_id=SETUP_B,
    entries=(ENTRY_ONE, ENTRY_TWO),
)
SCENARIO_ZERO = (ZERO_CURRENT, ZERO_ARCHIVED, ZERO_OTHER_CHARACTER, ZERO_OF_B)


def _twinned(marker: str) -> tuple[str, str]:
    """P's two entries, with one marker word added — the only difference from P's text."""
    return (ENTRY_ONE, f"{ENTRY_TWO} {marker}")


#: DoD-6/DoD-7's scenario: P, and four sessions that would match but are each excluded.
TWIN_PAST = _Seeded(
    session_id=S_PAST,
    created_at=DATE_PAST,
    setup_name=HARBOUR_NAME,
    setup_id=SETUP_HARBOUR,
    entries=(ENTRY_ONE, ENTRY_TWO),
)
TWIN_CURRENT = _Seeded(
    session_id=S_TWIN_CURRENT,
    created_at=DATE_MAIN_CURRENT,
    setup_name=HARBOUR_NAME,
    setup_id=SETUP_HARBOUR,
    entries=_twinned(MARKER_CURRENT),
)
TWIN_ARCHIVED = _Seeded(
    session_id=S_TWIN_ARCHIVED,
    created_at=DATE_WITH_SETUP,
    setup_name=HARBOUR_NAME,
    setup_id=SETUP_HARBOUR,
    entries=_twinned(MARKER_ARCHIVED),
    archived_at=ARCHIVED_AT,
)
TWIN_CHARACTER = _Seeded(
    session_id=S_TWIN_CHARACTER,
    created_at=DATE_WITH_SETUP,
    setup_name=TWIN_SETUP_NAME,
    character_id=CHAR_A2,
    setup_id=SETUP_TWIN,
    entries=_twinned(MARKER_OTHER_CHARACTER),
)
TWIN_USER = _Seeded(
    session_id=S_TWIN_USER,
    created_at=DATE_WITH_SETUP,
    setup_name=B_SETUP_NAME,
    user_id=USER_B,
    character_id=CHAR_B1,
    setup_id=SETUP_B,
    entries=_twinned(MARKER_OTHER_USER),
)
SCENARIO_TWIN = (TWIN_PAST, TWIN_CURRENT, TWIN_ARCHIVED, TWIN_CHARACTER, TWIN_USER)


# --- DoD-1: the content's blocks, their order and their parts (D3, UC-053 main flow) ---------


def test_the_content_is_one_block_per_hit_in_hit_order__S027_003_DoD1(engine: Engine) -> None:
    """D3: one block per hit, joined by `\\n\\n`, in `search_sessions`' own hit order.

    The order comes from step `001`'s contract for the same inputs; each block comes from D3
    applied to the seeded rows (the stored `created_at`'s date, the seeded setup name and the
    seeded settled texts).
    """
    _seed(engine, SCENARIO_MAIN)
    query = _compose(engine, S_WITH_SETUP)
    hits = _expected_hits(engine, query_text=query, current_session_id=S_MAIN_CURRENT)
    assert len(hits) == 3

    outcome = _run(engine, MAIN_SCOPE, {"query": query})

    assert outcome.content == _expected_content(hits, SCENARIO_MAIN)


def test_the_block_order_equals_the_search_hit_order__S027_003_DoD1(engine: Engine) -> None:
    """D3: the headers, read in content order, are the hit sessions' headers in hit order."""
    _seed(engine, SCENARIO_MAIN)
    query = _compose(engine, S_WITH_SETUP)
    hits = _expected_hits(engine, query_text=query, current_session_id=S_MAIN_CURRENT)
    by_id = {seeded.session_id: seeded for seeded in SCENARIO_MAIN}

    outcome = _run(engine, MAIN_SCOPE, {"query": query})

    headers = [line for line in outcome.content.splitlines() if line.startswith("### Session ")]
    assert headers == [_expected_header(by_id[hit.id]) for hit in hits]


def test_each_seeded_session_contributes_its_own_block__S027_003_DoD1(engine: Engine) -> None:
    """D3: the setup form, the `no setup` form and the `(no settled entries)` body all appear."""
    _seed(engine, SCENARIO_MAIN)
    query = _compose(engine, S_WITH_SETUP)

    outcome = _run(engine, MAIN_SCOPE, {"query": query})

    assert _expected_block(MAIN_WITH_SETUP) in outcome.content
    assert _expected_block(MAIN_NO_SETUP) in outcome.content
    assert _expected_block(MAIN_NO_ENTRIES) in outcome.content


def test_the_formatter_renders_the_given_records_in_order__S027_003_DoD1() -> None:
    """D3: handed records directly, the formatter joins their blocks with `\\n\\n` in order."""
    records = [
        SessionExcerpt(
            session_id=MAIN_WITH_SETUP.session_id,
            created_date=date(2026, 3, 14),
            setup_name=HARBOUR_NAME,
            excerpt=_expected_excerpt(MAIN_WITH_SETUP.entries),
        ),
        SessionExcerpt(
            session_id=MAIN_NO_SETUP.session_id,
            created_date=date(2026, 4, 2),
            setup_name=None,
            excerpt=_expected_excerpt(MAIN_NO_SETUP.entries),
        ),
        SessionExcerpt(
            session_id=MAIN_NO_ENTRIES.session_id,
            created_date=date(2026, 5, 20),
            setup_name=None,
            excerpt="",
        ),
    ]

    content, summary = format_excerpts(records)

    expected_blocks = [
        _expected_block(MAIN_WITH_SETUP),
        _expected_block(MAIN_NO_SETUP),
        _expected_block(MAIN_NO_ENTRIES),
    ]
    assert content == "\n\n".join(expected_blocks)
    assert summary == "3 sessions"


# --- DoD-2: the excerpt bound through the tool (D3) ------------------------------------------


def test_a_long_sessions_body_is_marked_and_exactly_1501_characters__S027_003_DoD2(
    engine: Engine,
) -> None:
    """D3: over 1500 characters, the body is `…` plus the last 1500 — 1501 characters in all.

    The scenario holds exactly one in-scope past session, so the content is that single block
    and its body is everything after the first newline.
    """
    _seed(engine, SCENARIO_LONG)
    query = _compose(engine, S_LONG)
    assert len("\n\n".join(LONG_PAST.entries)) > EXCERPT_CHARS

    outcome = _run(engine, LONG_SCOPE, {"query": query})

    header, body = outcome.content.split("\n", 1)
    assert header == _expected_header(LONG_PAST)
    assert body.startswith(ELLIPSIS)
    assert len(body) == EXCERPT_CHARS + 1
    assert body == _expected_excerpt(LONG_PAST.entries)


# --- DoD-3: the summary (D3, 021 D6) --------------------------------------------------------


def test_the_summary_counts_the_three_hits__S027_003_DoD3(engine: Engine) -> None:
    """D3: exactly `3 sessions` for the DoD-1 call — never pluralised away from `sessions`."""
    _seed(engine, SCENARIO_MAIN)
    query = _compose(engine, S_WITH_SETUP)

    outcome = _run(engine, MAIN_SCOPE, {"query": query})

    assert outcome.summary == "3 sessions"


def test_the_summary_of_one_hit_is_one_sessions__S027_003_DoD3(engine: Engine) -> None:
    """D3: a single hit summarises as `1 sessions`, not `1 session`."""
    _seed(engine, SCENARIO_LONG)
    query = _compose(engine, S_LONG)

    outcome = _run(engine, LONG_SCOPE, {"query": query})

    assert outcome.summary == "1 sessions"


def test_no_summary_carries_any_entry_text_or_the_token__S027_003_DoD3(engine: Engine) -> None:
    """D3 / 021 D6: the summary never contains content — not an entry text, not the token."""
    _seed(engine, SCENARIO_MAIN)
    query = _compose(engine, S_WITH_SETUP)

    outcome = _run(engine, MAIN_SCOPE, {"query": query})

    assert TOKEN not in outcome.summary
    for entry in MAIN_ENTRY_TEXTS:
        assert entry not in outcome.summary


def test_a_single_hit_summary_carries_no_entry_text_or_token__S027_003_DoD3(engine: Engine) -> None:
    """D3 / 021 D6: the same of the one-hit summary, whose excerpt is long."""
    _seed(engine, SCENARIO_LONG)
    query = _compose(engine, S_LONG)

    outcome = _run(engine, LONG_SCOPE, {"query": query})

    assert TOKEN not in outcome.summary
    assert LONG_ENTRY_ONE not in outcome.summary
    assert LONG_ENTRY_TWO not in outcome.summary


# --- DoD-4: no persona, no setup description, no ids (D3) ------------------------------------


def test_neither_the_persona_nor_the_setup_description_reaches_the_content__S027_003_DoD4(
    engine: Engine,
) -> None:
    """D3: both are in the embedded text, and neither marker word may reach the model."""
    _seed(engine, SCENARIO_MAIN)
    query = _compose(engine, S_WITH_SETUP)

    outcome = _run(engine, MAIN_SCOPE, {"query": query})

    assert PERSONA_MARKER not in outcome.content
    assert DESCRIPTION_MARKER not in outcome.content


def test_no_seeded_id_appears_in_the_content__S027_003_DoD4(engine: Engine) -> None:
    """D3: no ids in the content. Every seeded id is above 2^60, so its decimal string cannot
    occur by chance in seeded prose."""
    _seed(engine, SCENARIO_MAIN)
    query = _compose(engine, S_WITH_SETUP)
    identifiers = (USER_A, CHAR_A1, SETUP_HARBOUR, S_WITH_SETUP, S_NO_SETUP, S_NO_ENTRIES, S_MAIN_CURRENT)
    assert all(identifier > SNOWFLAKE_FLOOR for identifier in identifiers)

    outcome = _run(engine, MAIN_SCOPE, {"query": query})

    for identifier in identifiers:
        assert str(identifier) not in outcome.content


# --- DoD-5: zero hits is a success (D3) -----------------------------------------------------


def test_no_in_scope_session_gives_the_zero_hit_content__S027_003_DoD5(engine: Engine) -> None:
    """D3: the content is exactly `No matching sessions.`, and nothing is raised.

    Everything seeded here would match — the query is the archived session's own composed text —
    but every one of them is out of scope.
    """
    _seed(engine, SCENARIO_ZERO)
    query = _compose(engine, S_ZERO_ARCHIVED)

    outcome = _run(engine, ZERO_SCOPE, {"query": query})

    assert outcome.content == ZERO_HIT_CONTENT


def test_no_in_scope_session_summarises_zero_sessions__S027_003_DoD5(engine: Engine) -> None:
    """D3: the summary is exactly `0 sessions`."""
    _seed(engine, SCENARIO_ZERO)
    query = _compose(engine, S_ZERO_ARCHIVED)

    outcome = _run(engine, ZERO_SCOPE, {"query": query})

    assert outcome.summary == "0 sessions"


def test_the_formatter_with_no_records_says_no_matching_sessions__S027_003_DoD5() -> None:
    """D3: handed no records, the formatter answers the zero-hit sentence and `0 sessions`."""
    content, summary = format_excerpts([])

    assert content == ZERO_HIT_CONTENT
    assert summary == "0 sessions"


# --- DoD-6: the exclusions hold through the tool (US-069.AC-1/2, UC-054, D1) -----------------


def test_no_excluded_sessions_marker_reaches_the_content__S027_003_DoD6(engine: Engine) -> None:
    """D1: the current, the archived, the other character's and the other user's sessions all
    share P's persona, setup description and entries, and none of their markers appears."""
    _seed(engine, SCENARIO_TWIN)
    query = _compose(engine, S_PAST)

    outcome = _run(engine, TWIN_SCOPE, {"query": query})

    for marker in EXCLUDED_MARKERS:
        assert marker not in outcome.content


def test_only_the_in_scope_past_sessions_block_comes_back__S027_003_DoD6(engine: Engine) -> None:
    """D1: P's block is the whole content, and the summary counts one session — so no twin of
    P's text came back, markers aside."""
    _seed(engine, SCENARIO_TWIN)
    query = _compose(engine, S_PAST)

    outcome = _run(engine, TWIN_SCOPE, {"query": query})

    assert outcome.content == _expected_block(TWIN_PAST)
    assert outcome.summary == "1 sessions"


# --- DoD-7: the ids come only from the scope (D7, R5) ----------------------------------------

SPOOFING_ARGUMENTS: dict[str, object] = {
    "user_id": USER_B,
    "session_id": S_TWIN_USER,
    "character_id": CHAR_A2,
    "setup_id": SETUP_B,
    "current_session_id": S_PAST,
}


def test_arguments_naming_other_ids_change_nothing__S027_003_DoD7(engine: Engine) -> None:
    """D7: only `query` is read, so the extra keys leave the content byte-identical.

    The spoofed `current_session_id` is P's own id: were it honoured, P would be excluded.
    """
    _seed(engine, SCENARIO_TWIN)
    query = _compose(engine, S_PAST)

    plain = _run(engine, TWIN_SCOPE, {"query": query})
    spoofed = _run(engine, TWIN_SCOPE, {"query": query, **SPOOFING_ARGUMENTS})

    assert spoofed.content == plain.content
    assert spoofed.summary == plain.summary


def test_nothing_of_the_other_user_appears_however_the_arguments_ask__S027_003_DoD7(
    engine: Engine,
) -> None:
    """R5: B's marker stays absent, and the current session is still excluded."""
    _seed(engine, SCENARIO_TWIN)
    query = _compose(engine, S_PAST)

    outcome = _run(engine, TWIN_SCOPE, {"query": query, **SPOOFING_ARGUMENTS})

    assert MARKER_OTHER_USER not in outcome.content
    assert MARKER_CURRENT not in outcome.content
    assert outcome.content == _expected_block(TWIN_PAST)


# --- DoD-8: bad arguments raise `ToolFailedError` (D5) --------------------------------------


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"query": 7},
        {"query": None},
        {"query": ["tidewatch"]},
    ],
    ids=["missing", "integer", "none", "list"],
)
def test_arguments_without_a_string_query_raise_tool_failed__S027_003_DoD8(
    engine: Engine, arguments: Mapping[str, object]
) -> None:
    """D5: a missing or non-string `query` is the tool's own failure, naming the tool."""
    _seed(engine, SCENARIO_MAIN)

    with engine.connect() as connection:
        with pytest.raises(ToolFailedError) as raised:
            asyncio.run(
                asyncio.wait_for(
                    _tool().run(MAIN_SCOPE, connection, arguments), timeout=TIMEOUT_SECONDS
                )
            )

    assert raised.value.detail["tool"] == EXPECTED_TOOL_NAME


# --- DoD-9: the search runs off the event loop (D6) ------------------------------------------


def test_run_awaited_inside_a_running_loop_returns_blocks__S027_003_DoD9(engine: Engine) -> None:
    """D6: awaited from inside a running loop, the sync port still runs — off that loop.

    The coroutine is the test's own, so `run` is awaited while a loop is running, which is the
    condition under which an on-loop sync search would fail.
    """
    _seed(engine, SCENARIO_MAIN)
    query = _compose(engine, S_WITH_SETUP)
    tool = _tool()

    async def scenario() -> ToolOutcome:
        with engine.connect() as connection:
            return await tool.run(MAIN_SCOPE, connection, {"query": query})

    outcome = asyncio.run(asyncio.wait_for(scenario(), timeout=TIMEOUT_SECONDS))

    assert outcome.content.startswith("### Session ")
    assert outcome.summary == "3 sessions"
    assert outcome.content != ZERO_HIT_CONTENT


# --- DoD-10: no transaction left open, on either exit (D5) -----------------------------------


def test_a_successful_run_leaves_no_transaction_in_progress__S027_003_DoD10(engine: Engine) -> None:
    """D5: the connection the seam handed in is left with no transaction in progress."""
    _seed(engine, SCENARIO_MAIN)
    query = _compose(engine, S_WITH_SETUP)

    with engine.connect() as connection:
        outcome = asyncio.run(
            asyncio.wait_for(
                _tool().run(MAIN_SCOPE, connection, {"query": query}), timeout=TIMEOUT_SECONDS
            )
        )

        assert outcome.summary == "3 sessions"
        _assert_no_open_transaction(connection)


def test_a_failed_run_leaves_no_transaction_in_progress__S027_003_DoD10(engine: Engine) -> None:
    """D5: the same guarantee after the port's `NoEmbeddingModelError` propagated.

    The vectors are written while the model is designated, and the designation is then removed,
    so `session_vec` is present and non-empty and the query embedding is what fails.
    """
    _seed(engine, SCENARIO_MAIN)
    query = _compose(engine, S_WITH_SETUP)
    _remove_designation(engine)

    with engine.connect() as connection:
        with pytest.raises(NoEmbeddingModelError):
            asyncio.run(
                asyncio.wait_for(
                    _tool().run(MAIN_SCOPE, connection, {"query": query}), timeout=TIMEOUT_SECONDS
                )
            )

        _assert_no_open_transaction(connection)


# --- DoD-11: the registration (D6, 021 D5) --------------------------------------------------


def test_the_production_registry_holds_the_two_tools__S027_003_DoD11() -> None:
    """D6: exactly two entries, keyed `memo_search` and `session_search`."""
    assert len(PRODUCTION_TOOL_REGISTRY) == 2
    assert list(PRODUCTION_TOOL_REGISTRY) == [MEMO_TOOL_NAME, EXPECTED_TOOL_NAME]


def test_the_registered_session_search_value_names_itself__S027_003_DoD11() -> None:
    """D6: the `session_search` value answers the protocol's `name` with the declared name."""
    assert PRODUCTION_TOOL_REGISTRY[EXPECTED_TOOL_NAME].name == EXPECTED_TOOL_NAME
    assert SessionSearchTool.name == EXPECTED_TOOL_NAME
    assert SessionSearchTool().name == SESSION_SEARCH_NAME


def test_offered_tools_over_the_production_registry_is_both_declarations__S027_003_DoD11() -> None:
    """021 D5: all three switches on → both declarations, in `definitions.py`'s order."""
    offered = offered_tools(_configuration(memo=True, session=True, web=True), PRODUCTION_TOOL_REGISTRY)

    assert list(offered) == [MEMO_SEARCH, SESSION_SEARCH]


def test_offered_tools_with_the_session_switch_off_is_memo_search_alone__S027_003_DoD11() -> None:
    """021 D5: registered is not enough — with only `tool_session_search` off, `memo_search`
    alone is offered."""
    offered = offered_tools(_configuration(memo=True, session=False, web=True), PRODUCTION_TOOL_REGISTRY)

    assert list(offered) == [MEMO_SEARCH]


# --- DoD-12: failure through the real seam (UC-053 exception flow, R9) -----------------------


def test_dispatch_with_no_designated_model_fails_the_tool_and_raises_nothing__S027_003_DoD12(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """R9: the failure is reported as a tool result and the exchange carries on."""
    _seed(engine, SCENARIO_MAIN)
    _remove_designation(engine)
    scope = _build_scope(engine, USER_A, S_MAIN_CURRENT)

    result = _dispatch(engine, generator, scope, _tool(), {"query": TOKEN})

    assert isinstance(result.frame, ToolFailFrame)
    assert result.frame.tool == EXPECTED_TOOL_NAME
    assert result.frame.code == FAILED_CODE


def test_dispatch_with_no_designated_model_tells_the_model_the_tool_failed__S027_003_DoD12(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """UC-053 exception flow: the tool message content is exactly 021's failure sentence."""
    _seed(engine, SCENARIO_MAIN)
    _remove_designation(engine)
    scope = _build_scope(engine, USER_A, S_MAIN_CURRENT)

    result = _dispatch(engine, generator, scope, _tool(), {"query": TOKEN})

    assert result.message.content == FAILED_CONTENT


def test_dispatch_with_no_designated_model_writes_one_failed_tool_row__S027_003_DoD12(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """021 D7: exactly one tool row is kept, naming `session_search`."""
    _seed(engine, SCENARIO_MAIN)
    _remove_designation(engine)
    scope = _build_scope(engine, USER_A, S_MAIN_CURRENT)

    _dispatch(engine, generator, scope, _tool(), {"query": TOKEN})

    rows = _tool_rows(engine, S_MAIN_CURRENT)
    assert len(rows) == 1
    assert rows[0]["tool_name"] == EXPECTED_TOOL_NAME


# --- DoD-13: success through the real seam (UC-053 main flow, 021 D6) -----------------------


def test_dispatch_returns_a_tool_result_frame_summarising_the_hits__S027_003_DoD13(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """UC-053: the frame's summary is `<N> sessions` for the expected hit count."""
    _seed(engine, SCENARIO_MAIN)
    query = _compose(engine, S_WITH_SETUP)
    hits = _expected_hits(engine, query_text=query, current_session_id=S_MAIN_CURRENT)
    scope = _build_scope(engine, USER_A, S_MAIN_CURRENT)

    result = _dispatch(engine, generator, scope, _tool(), {"query": query})

    assert isinstance(result.frame, ToolResultFrame)
    assert result.frame.tool == EXPECTED_TOOL_NAME
    assert result.frame.summary == _expected_summary(hits)


def test_dispatch_gives_the_model_the_formatted_blocks__S027_003_DoD13(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """UC-053: the tool message carries D3's content for those hits, and no failure sentence."""
    _seed(engine, SCENARIO_MAIN)
    query = _compose(engine, S_WITH_SETUP)
    hits = _expected_hits(engine, query_text=query, current_session_id=S_MAIN_CURRENT)
    scope = _build_scope(engine, USER_A, S_MAIN_CURRENT)

    result = _dispatch(engine, generator, scope, _tool(), {"query": query})

    assert result.message.content == _expected_content(hits, SCENARIO_MAIN)
    assert result.message.content != FAILED_CONTENT


# --- DoD-14: the import shape (D6) ----------------------------------------------------------

BACKEND_DIRECTORY = Path(__file__).resolve().parent.parent

ADAPTER_MODULE = "app.services.tools.session_search"
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
def test_each_module_imports_cleanly_in_a_fresh_interpreter__S027_003_DoD14(code: str) -> None:
    """D6: no import cycle — either module imports alone, and either order works.

    A subprocess, so `sys.modules` is fresh. It imports modules and opens no database.
    """
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
def test_neither_module_imports_a_web_framework__S027_003_DoD14(module_name: str) -> None:
    """D6: neither module imports `fastapi`.

    Checked against the module **source**, not `sys.modules`: `app/errors.py` imports the web
    framework and the seam imports `app.errors`, so a `sys.modules` probe would answer a
    question this step does not own.
    """
    module = adapter_module if module_name == "adapter" else seam_module

    roots = _imported_roots(_module_source(module))

    assert roots & {"fastapi", "starlette"} == set()
