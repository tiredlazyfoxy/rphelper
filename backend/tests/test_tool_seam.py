"""Feature 021 step 004 — the tool seam (`app/services/tools/seam.py`).

Expected values come from `docs/plans/021.compose-loop-and-tools/004.tool-seam.md`
(Interface intent + DoD-2..DoD-10), `004.context.md` and the feature `context.md` (D5 offered
rule, D6 the seam, D7 the tool row and its payload table, D13 `tool_failed`, D15 the import
exception, the Literals table). Bindings come from `status.md` `## Skeleton` -> Steps 001,
002, 004 and 019 `001` / 017 `003`:

- `ToolScope(user_id, session_id, character_id, setup_id)`; `ToolOutcome(content, summary)`
- `Tool` protocol: `name`; `async run(scope, connection, arguments) -> ToolOutcome`
- `PRODUCTION_TOOL_REGISTRY`; `DispatchResult(frame, message)`
- `build_tool_scope(connection, user_id, session_id) -> ToolScope`
- `offered_tools(configuration, registry) -> list[ToolDeclaration]`
- `tool_start_frame(call) -> ToolStartFrame`
- `async dispatch(call, scope, offered, registry, engine, generator) -> DispatchResult`
- `ToolStartFrame(tool, call_id, args)`, `ToolResultFrame(tool, call_id, summary)`,
  `ToolFailFrame(tool, call_id, code)` (019 `001`)
- `ToolCall(call_id, name, arguments)`, `ChatMessage(role, content, tool_calls, tool_call_id)`
- `SessionConfiguration(...)`, `ResolvedSetting(session, inherited, inherited_level, value,
  level)`, `ConfigLevel` (017 `003`)

Async code is driven with `asyncio.run(...)`, every run bounded by `asyncio.wait_for`. Tools are
file-local fakes recording scope, connection and arguments. Each test name ends
`__S021_004_DoD<n>`.
"""

from __future__ import annotations

import ast
import asyncio
import json
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, select

from app.db import schema
from app.errors import SessionNotFoundError
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services import configuration as configuration_module
from app.services.configuration import ConfigLevel, ResolvedSetting, SessionConfiguration
from app.services.llm.chat import ChatMessage, ToolCall
from app.services.llm.frames import ToolFailFrame, ToolResultFrame, ToolStartFrame
from app.services.passwords import hash_password
from app.services.tools import seam as seam_module
from app.services.tools.definitions import MEMO_SEARCH, SESSION_SEARCH, WEB_SEARCH
from app.services.tools.seam import (
    PRODUCTION_TOOL_REGISTRY,
    DispatchResult,
    Tool,
    ToolOutcome,
    ToolScope,
    build_tool_scope,
    dispatch,
    offered_tools,
    tool_start_frame,
)

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
ARCHIVED_AT = "2026-02-01T00:00:00.000000+00:00"

USER_A = 9_441_001
USER_B = 9_441_002

CHAR_A = 1_401
CHAR_B = 2_401

SETUP_A = 3_401

#: User A's session with a setup.
SESSION_A = 5_401
#: User A's session without a setup.
SESSION_A_NO_SETUP = 5_402
#: User A's archived session (with the setup).
SESSION_A_ARCHIVED = 5_403
#: User B's session.
SESSION_B = 6_401

#: An id that belongs to no session of any user.
UNKNOWN_SESSION_ID = 7_250_000_000_000_000_404

#: Literals (context.md) — the contract.
FAILED_CONTENT = "The tool failed. Continue without its result."
FAILED_ROW_TEXT = "The tool failed."
FAILED_CODE = "tool_failed"

#: Bound for every asyncio run.
TIMEOUT_SECONDS = 5.0


# --- seeding -----------------------------------------------------------------------------


def _insert_user(engine: Engine, *, user_id: int, username: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.users.insert().values(
                id=user_id,
                username=username,
                password_hash=hash_password("a quiet river at dusk"),
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


def _insert_setup(engine: Engine, *, setup_id: int, user_id: int, character_id: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.setups.insert().values(
                id=setup_id,
                user_id=user_id,
                character_id=character_id,
                name="The Gilded Goose",
                description="",
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_session(
    engine: Engine,
    *,
    session_id: int,
    user_id: int,
    character_id: int,
    setup_id: int | None,
    archived_at: str | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.insert().values(
                id=session_id,
                user_id=user_id,
                character_id=character_id,
                setup_id=setup_id,
                last_used_at=TIMESTAMP,
                archived_at=archived_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """Two owners; user A has a character, a setup and three sessions; user B one session."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="aster")
    _insert_user(db_engine, user_id=USER_B, username="briar")
    _insert_character(db_engine, character_id=CHAR_A, user_id=USER_A, name="Aria")
    _insert_character(db_engine, character_id=CHAR_B, user_id=USER_B, name="Bob's own")
    _insert_setup(db_engine, setup_id=SETUP_A, user_id=USER_A, character_id=CHAR_A)
    _insert_session(
        db_engine, session_id=SESSION_A, user_id=USER_A, character_id=CHAR_A, setup_id=SETUP_A
    )
    _insert_session(
        db_engine,
        session_id=SESSION_A_NO_SETUP,
        user_id=USER_A,
        character_id=CHAR_A,
        setup_id=None,
    )
    _insert_session(
        db_engine,
        session_id=SESSION_A_ARCHIVED,
        user_id=USER_A,
        character_id=CHAR_A,
        setup_id=SETUP_A,
        archived_at=ARCHIVED_AT,
    )
    _insert_session(
        db_engine, session_id=SESSION_B, user_id=USER_B, character_id=CHAR_B, setup_id=None
    )
    return db_engine


@pytest.fixture
def generator() -> SnowflakeGenerator:
    return SnowflakeGenerator(node_id=1)


#: The caller's scope for SESSION_A, as D6 defines it.
SCOPE_A = ToolScope(user_id=USER_A, session_id=SESSION_A, character_id=CHAR_A, setup_id=SETUP_A)


# --- fake tools ----------------------------------------------------------------------------


class RecordingTool:
    """A fake `Tool`: records every call's scope, connection and arguments."""

    def __init__(self, name: str, outcome: ToolOutcome | None = None) -> None:
        self.name = name
        self.outcome = outcome or ToolOutcome(content=f"{name} content", summary=f"{name} summary")
        self.scopes: list[ToolScope] = []
        self.connections: list[Connection] = []
        self.arguments: list[dict[str, object]] = []

    @property
    def calls(self) -> int:
        return len(self.scopes)

    def _record(self, scope: ToolScope, connection: Connection, arguments: Mapping[str, object]) -> None:
        self.scopes.append(scope)
        self.connections.append(connection)
        self.arguments.append(dict(arguments))

    async def run(
        self, scope: ToolScope, connection: Connection, arguments: Mapping[str, object]
    ) -> ToolOutcome:
        self._record(scope, connection, arguments)
        return self.outcome


class RaisingTool(RecordingTool):
    """A fake whose `run` raises `RuntimeError`."""

    async def run(
        self, scope: ToolScope, connection: Connection, arguments: Mapping[str, object]
    ) -> ToolOutcome:
        self._record(scope, connection, arguments)
        raise RuntimeError("the index is down")


class ForeverTool(RecordingTool):
    """A fake whose `run` signals it started, then awaits forever."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.started: asyncio.Event | None = None

    async def run(
        self, scope: ToolScope, connection: Connection, arguments: Mapping[str, object]
    ) -> ToolOutcome:
        self._record(scope, connection, arguments)
        assert self.started is not None
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


def _registry(*tools: RecordingTool) -> dict[str, Tool]:
    return {tool.name: tool for tool in tools}


# --- configuration values ------------------------------------------------------------------


def _bool_setting(value: bool) -> ResolvedSetting[bool]:
    return ResolvedSetting(
        session=value, inherited=None, inherited_level=None, value=value, level=ConfigLevel.SESSION
    )


def _text_setting() -> ResolvedSetting[str]:
    return ResolvedSetting(
        session=None, inherited=None, inherited_level=None, value=None, level=None
    )


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


def _names(declarations: list[Any]) -> list[str]:
    return [str(declaration["function"]["name"]) for declaration in declarations]


# --- call wrappers ---------------------------------------------------------------------------


def _build_scope(engine: Engine, user_id: int, session_id: int) -> ToolScope:
    with engine.connect() as connection:
        return build_tool_scope(connection, user_id, session_id)


def _dispatch(
    call: ToolCall,
    offered: Collection[str],
    registry: Mapping[str, Tool],
    engine: Engine,
    generator: SnowflakeGenerator,
    scope: ToolScope = SCOPE_A,
) -> DispatchResult:
    return asyncio.run(
        asyncio.wait_for(
            dispatch(call, scope, offered, registry, engine, generator),
            timeout=TIMEOUT_SECONDS,
        )
    )


def _tool_rows(engine: Engine, session_id: int = SESSION_A) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            select(schema.messages)
            .where(schema.messages.c.session_id == session_id)
            .where(schema.messages.c.role == "tool")
            .order_by(schema.messages.c.id)
        ).all()
    return [dict(row._mapping) for row in rows]


def _all_tool_rows(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            select(schema.messages).where(schema.messages.c.role == "tool")
        ).all()
    return [dict(row._mapping) for row in rows]


# =========================================================================================
# DoD-2: the production registry holds exactly the registered tools
# Amended by 026 step 002 (DoD-15): it registers `memo_search`, so "empty" is no longer true.
# The `__S021_004_DoD2` tag is kept; only the three emptiness assertions moved.
# =========================================================================================


# Amended by 026 step 002: the registry now holds exactly `memo_search`.
def test_the_production_registry_holds_exactly_memo_search__S021_004_DoD2() -> None:
    """DoD-2 / D5 — exactly the tools registered so far: `memo_search` (026), and no other."""
    assert len(PRODUCTION_TOOL_REGISTRY) == 1
    assert list(PRODUCTION_TOOL_REGISTRY) == ["memo_search"]


# Amended by 026 step 002: the trailing length is 1; the registry is still a `MappingProxyType`.
def test_the_production_registry_is_read_only__S021_004_DoD2() -> None:
    """DoD-2 / Interface intent — a read-only mapping: item assignment is refused."""
    fake = RecordingTool("memo_search")
    with pytest.raises(TypeError):
        PRODUCTION_TOOL_REGISTRY["memo_search"] = fake  # type: ignore[index]
    assert len(PRODUCTION_TOOL_REGISTRY) == 1


# Amended by 026 step 002: `memo_search` is registered, so the switch is now what decides.
def test_offered_tools_over_the_production_registry_is_memo_search__S021_004_DoD2() -> None:
    """DoD-2 / D5 / U3 — all three switches on → exactly the one registered declaration; with
    the memo-search switch off → nothing."""
    offered = offered_tools(
        _configuration(memo=True, session=True, web=True), PRODUCTION_TOOL_REGISTRY
    )
    assert list(offered) == [MEMO_SEARCH]

    switched_off = offered_tools(
        _configuration(memo=False, session=True, web=True), PRODUCTION_TOOL_REGISTRY
    )
    assert list(switched_off) == []


# =========================================================================================
# DoD-3: offered = switch on ∩ registered, declaration order, closed at three
# =========================================================================================


def test_offered_tools_is_switch_on_and_registered__S021_004_DoD3() -> None:
    """DoD-3 / D5 — memo + web registered; memo on, session on, web off → exactly the
    `memo_search` declaration (session is not registered, web is switched off)."""
    registry = _registry(RecordingTool("memo_search"), RecordingTool("web_search"))

    offered = offered_tools(_configuration(memo=True, session=True, web=False), registry)

    assert list(offered) == [MEMO_SEARCH]
    assert _names(list(offered)) == ["memo_search"]


def test_offered_tools_all_on_and_registered_is_declaration_order__S021_004_DoD3() -> None:
    """DoD-3 / D5 / US-062.AC-1 — all three on and registered (registry inserted in reverse)
    → all three in declaration order."""
    registry = _registry(
        RecordingTool("web_search"), RecordingTool("session_search"), RecordingTool("memo_search")
    )

    offered = offered_tools(_configuration(memo=True, session=True, web=True), registry)

    assert list(offered) == [MEMO_SEARCH, SESSION_SEARCH, WEB_SEARCH]
    assert _names(list(offered)) == ["memo_search", "session_search", "web_search"]


def test_offered_tools_never_returns_a_name_outside_the_three__S021_004_DoD3() -> None:
    """DoD-3 / R9 — a registered `lore_search` is never offered."""
    registry = _registry(
        RecordingTool("lore_search"),
        RecordingTool("memo_search"),
        RecordingTool("session_search"),
        RecordingTool("web_search"),
    )

    offered = offered_tools(_configuration(memo=True, session=True, web=True), registry)

    assert _names(list(offered)) == ["memo_search", "session_search", "web_search"]
    assert "lore_search" not in _names(list(offered))


def test_offered_tools_only_an_outside_name_registered_offers_nothing__S021_004_DoD3() -> None:
    """DoD-3 / R9 — the only registered name is outside the three → nothing offered."""
    registry = _registry(RecordingTool("lore_search"))

    offered = offered_tools(_configuration(memo=True, session=True, web=True), registry)

    assert list(offered) == []


# =========================================================================================
# DoD-4: build_tool_scope
# =========================================================================================


def test_build_tool_scope_on_an_owned_session_with_a_setup__S021_004_DoD4(engine: Engine) -> None:
    """DoD-4 / R5 — user id, session id, its character id and setup id."""
    scope = _build_scope(engine, USER_A, SESSION_A)

    assert scope == ToolScope(
        user_id=USER_A, session_id=SESSION_A, character_id=CHAR_A, setup_id=SETUP_A
    )


def test_build_tool_scope_without_a_setup_has_setup_id_none__S021_004_DoD4(
    engine: Engine,
) -> None:
    """DoD-4 — a session without a setup → `setup_id` is `None`."""
    scope = _build_scope(engine, USER_A, SESSION_A_NO_SETUP)

    assert scope.user_id == USER_A
    assert scope.session_id == SESSION_A_NO_SETUP
    assert scope.character_id == CHAR_A
    assert scope.setup_id is None


@pytest.mark.parametrize(
    "session_id", [SESSION_B, UNKNOWN_SESSION_ID], ids=["another-users", "unknown"]
)
def test_build_tool_scope_on_a_foreign_or_unknown_session_is_not_found__S021_004_DoD4(
    engine: Engine, session_id: int
) -> None:
    """DoD-4 / R5 / FEAT-019 — another user's session and an unknown id raise
    `SessionNotFoundError`."""
    with pytest.raises(SessionNotFoundError):
        _build_scope(engine, USER_A, session_id)


def test_build_tool_scope_on_an_archived_session_builds_normally__S021_004_DoD4(
    engine: Engine,
) -> None:
    """DoD-4 / R6 — an archived session is fine."""
    scope = _build_scope(engine, USER_A, SESSION_A_ARCHIVED)

    assert scope == ToolScope(
        user_id=USER_A, session_id=SESSION_A_ARCHIVED, character_id=CHAR_A, setup_id=SETUP_A
    )


def test_tool_scope_is_frozen__S021_004_DoD4() -> None:
    """DoD-4 / D6 — `ToolScope` is frozen: a tool cannot forge it."""
    with pytest.raises(AttributeError):
        SCOPE_A.user_id = USER_B  # type: ignore[misc]


# =========================================================================================
# DoD-5: tool_start_frame
# =========================================================================================


def test_tool_start_frame_carries_parsed_args_and_the_call_id_verbatim__S021_004_DoD5() -> None:
    """DoD-5 / D6 — tool = the call's name, call id verbatim, args = the parsed object."""
    frame = tool_start_frame(
        ToolCall(call_id="call_9f2", name="memo_search", arguments='{"query":"inn"}')
    )

    assert isinstance(frame, ToolStartFrame)
    assert frame.tool == "memo_search"
    assert frame.call_id == "call_9f2"
    assert dict(frame.args) == {"query": "inn"}


@pytest.mark.parametrize("arguments", ["not json", "[1,2]"], ids=["unparseable", "not-an-object"])
def test_tool_start_frame_args_are_empty_when_not_a_json_object__S021_004_DoD5(
    arguments: str,
) -> None:
    """DoD-5 / D6 — `'not json'` and `'[1,2]'` → args `{}`; call id still verbatim."""
    frame = tool_start_frame(ToolCall(call_id="call_9f2", name="memo_search", arguments=arguments))

    assert isinstance(frame, ToolStartFrame)
    assert frame.tool == "memo_search"
    assert frame.call_id == "call_9f2"
    assert dict(frame.args) == {}


# =========================================================================================
# DoD-6: success
# =========================================================================================

CONTENT_C = "Memo: the inn is called The Gilded Goose."
SUMMARY_S = "1 memo found"
SUCCESS_ARGUMENTS = '{"query":"inn"}'


def test_dispatch_success_frame_and_message__S021_004_DoD6(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-6 / D6 — tool-result (`memo_search`, the call id, `S`); a role-tool message with
    that `tool_call_id` and content `C`."""
    fake = RecordingTool("memo_search", ToolOutcome(content=CONTENT_C, summary=SUMMARY_S))
    call = ToolCall(call_id="call_ok1", name="memo_search", arguments=SUCCESS_ARGUMENTS)

    result = _dispatch(call, ["memo_search"], _registry(fake), engine, generator)

    assert isinstance(result, DispatchResult)
    assert isinstance(result.frame, ToolResultFrame)
    assert result.frame == ToolResultFrame(tool="memo_search", call_id="call_ok1", summary=SUMMARY_S)
    assert isinstance(result.message, ChatMessage)
    assert result.message.role == "tool"
    assert result.message.tool_call_id == "call_ok1"
    assert result.message.content == CONTENT_C


def test_dispatch_success_writes_one_ok_tool_row__S021_004_DoD6(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-6 / D7 — one zone row: role `tool`, text `S`, `tool_name` `memo_search`, payload
    `{"call_id", "arguments": <raw string>, "status": "ok", "content": "C"}`."""
    fake = RecordingTool("memo_search", ToolOutcome(content=CONTENT_C, summary=SUMMARY_S))
    call = ToolCall(call_id="call_ok1", name="memo_search", arguments=SUCCESS_ARGUMENTS)

    _dispatch(call, ["memo_search"], _registry(fake), engine, generator)

    rows = _tool_rows(engine)
    assert len(rows) == 1
    row = rows[0]
    assert row["role"] == "tool"
    assert row["user_id"] == USER_A
    assert row["settled_at"] is None
    assert row["kind"] is None
    assert row["text"] == SUMMARY_S
    assert row["tool_name"] == "memo_search"
    assert json.loads(row["tool_payload"]) == {
        "call_id": "call_ok1",
        "arguments": SUCCESS_ARGUMENTS,
        "status": "ok",
        "content": CONTENT_C,
    }


def test_dispatch_success_hands_the_fake_scope_and_parsed_arguments__S021_004_DoD6(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-6 / D6 — the fake is called once, with the given (built) `ToolScope` and the parsed
    arguments mapping; the connection it received is closed after dispatch."""
    scope = _build_scope(engine, USER_A, SESSION_A)
    fake = RecordingTool("memo_search", ToolOutcome(content=CONTENT_C, summary=SUMMARY_S))
    call = ToolCall(call_id="call_ok1", name="memo_search", arguments=SUCCESS_ARGUMENTS)

    _dispatch(call, ["memo_search"], _registry(fake), engine, generator, scope=scope)

    assert fake.calls == 1
    assert fake.scopes == [scope]
    assert fake.scopes[0] == SCOPE_A
    assert fake.arguments == [{"query": "inn"}]
    assert isinstance(fake.connections[0], Connection)
    assert fake.connections[0].closed


# =========================================================================================
# DoD-7: failures
# =========================================================================================

FAILURE_CASES = [
    # (case id, call name, raw arguments, offered names, which fakes are registered)
    ("registered-not-offered", "memo_search", '{"query":"inn"}', ["web_search"], "plain"),
    ("unknown-name", "lore_search", '{"query":"inn"}', ["memo_search"], "plain"),
    ("arguments-not-json", "memo_search", '{"query":', ["memo_search"], "plain"),
    ("run-raises", "memo_search", '{"query":"inn"}', ["memo_search"], "raising"),
]


def _failure_fake(kind: str) -> RecordingTool:
    if kind == "raising":
        return RaisingTool("memo_search")
    return RecordingTool("memo_search")


@pytest.mark.parametrize(
    ("name", "arguments", "offered", "kind"),
    [case[1:] for case in FAILURE_CASES],
    ids=[case[0] for case in FAILURE_CASES],
)
def test_dispatch_failure_gives_a_tool_fail_frame_and_the_failed_message__S021_004_DoD7(
    engine: Engine,
    generator: SnowflakeGenerator,
    name: str,
    arguments: str,
    offered: list[str],
    kind: str,
) -> None:
    """DoD-7 / D6 / R9 — tool-fail frame (name as given, call id, `tool_failed`); a role-tool
    message with that `tool_call_id` and the failed literal; `dispatch` raises nothing."""
    fake = _failure_fake(kind)
    call = ToolCall(call_id="call_bad1", name=name, arguments=arguments)

    result = _dispatch(call, offered, _registry(fake), engine, generator)

    assert isinstance(result.frame, ToolFailFrame)
    assert result.frame == ToolFailFrame(tool=name, call_id="call_bad1", code=FAILED_CODE)
    assert result.message.role == "tool"
    assert result.message.tool_call_id == "call_bad1"
    assert result.message.content == FAILED_CONTENT


@pytest.mark.parametrize(
    ("name", "arguments", "offered", "kind"),
    [case[1:] for case in FAILURE_CASES],
    ids=[case[0] for case in FAILURE_CASES],
)
def test_dispatch_failure_writes_one_failed_tool_row__S021_004_DoD7(
    engine: Engine,
    generator: SnowflakeGenerator,
    name: str,
    arguments: str,
    offered: list[str],
    kind: str,
) -> None:
    """DoD-7 / D7 — one tool row: text `The tool failed.`, `tool_name` as given, payload
    `{"call_id", "arguments": <raw string>, "status": "failed", "code": "tool_failed"}`."""
    fake = _failure_fake(kind)
    call = ToolCall(call_id="call_bad1", name=name, arguments=arguments)

    _dispatch(call, offered, _registry(fake), engine, generator)

    rows = _tool_rows(engine)
    assert len(rows) == 1
    row = rows[0]
    assert row["role"] == "tool"
    assert row["settled_at"] is None
    assert row["text"] == FAILED_ROW_TEXT
    assert row["tool_name"] == name
    assert json.loads(row["tool_payload"]) == {
        "call_id": "call_bad1",
        "arguments": arguments,
        "status": "failed",
        "code": FAILED_CODE,
    }


@pytest.mark.parametrize(
    ("name", "arguments", "offered"),
    [case[1:4] for case in FAILURE_CASES if case[4] == "plain"],
    ids=[case[0] for case in FAILURE_CASES if case[4] == "plain"],
)
def test_dispatch_failure_before_run_never_calls_the_fake__S021_004_DoD7(
    engine: Engine,
    generator: SnowflakeGenerator,
    name: str,
    arguments: str,
    offered: list[str],
) -> None:
    """DoD-7 (a)-(c) / D6 — not offered, unknown name, arguments not a JSON object: `run` is
    never called."""
    fake = RecordingTool("memo_search")
    call = ToolCall(call_id="call_bad1", name=name, arguments=arguments)

    _dispatch(call, offered, _registry(fake), engine, generator)

    assert fake.calls == 0


def test_dispatch_failure_when_run_raises_closes_its_connection__S021_004_DoD7(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-7 (d) / D6 — the raising fake was called once and its connection is closed
    whatever happened."""
    fake = RaisingTool("memo_search")
    call = ToolCall(call_id="call_bad1", name="memo_search", arguments='{"query":"inn"}')

    _dispatch(call, ["memo_search"], _registry(fake), engine, generator)

    assert fake.calls == 1
    assert fake.connections[0].closed


# =========================================================================================
# DoD-8: model-supplied ids stay inside the arguments mapping
# =========================================================================================


def test_model_supplied_ids_reach_the_tool_only_as_arguments__S021_004_DoD8(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-8 / R5 / D6 — `user_id` / `session_id` in the arguments reach the fake only inside
    its arguments mapping; the scope still names the caller's user and session."""
    raw = json.dumps(
        {"query": "x", "user_id": str(USER_B), "session_id": str(SESSION_B)},
        separators=(",", ":"),
    )
    fake = RecordingTool("memo_search")
    call = ToolCall(call_id="call_iso1", name="memo_search", arguments=raw)

    _dispatch(call, ["memo_search"], _registry(fake), engine, generator)

    assert fake.calls == 1
    assert fake.arguments == [
        {"query": "x", "user_id": str(USER_B), "session_id": str(SESSION_B)}
    ]
    received = fake.scopes[0]
    assert received == SCOPE_A
    assert received.user_id == USER_A
    assert received.session_id == SESSION_A
    # The row lands in the caller's session, never the one the model named.
    assert len(_tool_rows(engine, SESSION_A)) == 1
    assert _tool_rows(engine, SESSION_B) == []


# =========================================================================================
# DoD-9: a cancellation propagates, writes no row, closes the connection
# =========================================================================================


def test_a_cancelled_dispatch_propagates_and_writes_no_row__S021_004_DoD9(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-9 / llm-and-streaming.md consequence 4 — awaiting the cancelled task raises
    `CancelledError`; no tool row is written; the fake's connection is closed."""
    fake = ForeverTool("memo_search")
    call = ToolCall(call_id="call_stop1", name="memo_search", arguments='{"query":"inn"}')

    async def scenario() -> None:
        fake.started = asyncio.Event()
        task = asyncio.create_task(
            dispatch(call, SCOPE_A, ["memo_search"], _registry(fake), engine, generator)
        )
        started = asyncio.create_task(fake.started.wait())
        done, _ = await asyncio.wait(
            {task, started}, timeout=TIMEOUT_SECONDS, return_when=asyncio.FIRST_COMPLETED
        )
        if task in done:
            started.cancel()
            task.result()  # surfaces the reason dispatch ended before run started
            raise AssertionError("dispatch returned before the tool's run was cancelled")
        assert started in done, "the tool's run never started"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=TIMEOUT_SECONDS)

    asyncio.run(asyncio.wait_for(scenario(), timeout=TIMEOUT_SECONDS * 3))

    assert fake.calls == 1
    assert _all_tool_rows(engine) == []
    assert fake.connections[0].closed


# =========================================================================================
# DoD-10: seam.py import conventions
# =========================================================================================

ALLOWED_SERVICE_MODULES = {
    "app.services.sessions",
    "app.services.messages",
    "app.services.configuration",
    "app.services.llm.chat",
    "app.services.llm.frames",
    "app.services.tools.definitions",
    # Added by 026 step 002 (DoD-15): the seam imports the adapter to register it.
    "app.services.tools.memo_search",
}


def _seam_imports() -> list[tuple[str, str | None]]:
    module_file = seam_module.__file__
    assert module_file is not None
    tree = ast.parse(Path(module_file).read_text(encoding="utf-8"))
    package = "app.services.tools"
    found: list[tuple[str, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0:
                module = node.module or ""
            else:
                parts = package.split(".")
                base = parts[: len(parts) - (node.level - 1)]
                module = ".".join([*base, *([node.module] if node.module else [])])
            found.extend((module, alias.name) for alias in node.names)
        elif isinstance(node, ast.Import):
            found.extend((alias.name, None) for alias in node.names)
    return found


def _under(name: str, package: str) -> bool:
    return name == package or name.startswith(package + ".")


def test_seam_imports_no_fastapi__S021_004_DoD10() -> None:
    """DoD-10 — `seam.py` imports no `fastapi`."""
    offenders = [module for module, _ in _seam_imports() if _under(module, "fastapi")]
    assert offenders == []


def test_seam_service_imports_are_within_the_allowed_set__S021_004_DoD10() -> None:
    """DoD-10 / D15 — from `app.services`, only `sessions`, `messages`, `configuration`,
    `llm.chat`, `llm.frames` and `tools.definitions`."""
    offenders: list[str] = []
    for module, name in _seam_imports():
        if module == "app" and name == "services":
            offenders.append("app.services")
            continue
        if not _under(module, "app.services"):
            continue
        full = module if name is None else f"{module}.{name}"
        if module in ALLOWED_SERVICE_MODULES or full in ALLOWED_SERVICE_MODULES:
            continue
        offenders.append(full)
    assert offenders == []


def test_seam_imports_only_types_from_configuration__S021_004_DoD10() -> None:
    """DoD-10 — from `configuration`, types only: every name imported from it is a class."""
    offenders = [
        name
        for module, name in _seam_imports()
        if module == "app.services.configuration"
        and name is not None
        and not isinstance(getattr(configuration_module, name, None), type)
    ]
    assert offenders == []
