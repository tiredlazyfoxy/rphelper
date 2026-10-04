"""Feature 021 step 005 — the compose source (`app/services/compose.py`).

Expected values come from `docs/plans/021.compose-loop-and-tools/005.compose-source.md`
(Interface intent, DoD-1..DoD-14), `005.context.md` and the feature `context.md` (D2 accepted
only with text, D3 model resolution inside the source, D4 `<think>` wrapping, D5 offered tools,
D11 the loop and fallback ids, D15 the import rule, the Literals table) and 020's prompt-format
markers (`=== Languages ===`, `- Candidates:`). Bindings come from `status.md` `## Skeleton`:

- `compose_stream(engine, generator, user_id, session_id, accepted_id, timeout_seconds,
  client_factory, registry) -> AsyncGenerator[Frame, None]` (Step 005)
- `ChatDelta(content, reasoning, tool_calls)`, `ToolCallDelta(index, call_id, name, arguments)`
  (Step 003); `ChatClientFactory = Callable[[str, str | None, float], ChatClientLike]`
- `ChatMessage(role, content, tool_calls, tool_call_id)`, `ToolCall(call_id, name, arguments)`
  (Step 002)
- `ToolOutcome(content, summary)`, `PRODUCTION_TOOL_REGISTRY`, `MEMO_SEARCH` (Step 004)
- 019 `001` frames: `AcceptedFrame(message_id)`, `TokenFrame(text)`, `DoneFrame(message_id)`,
  `ToolStartFrame(tool, call_id, args)`, `ToolResultFrame(tool, call_id, summary)`,
  `ToolFailFrame(tool, call_id, code)`

The chat client is a file-local fake replaying scripted rounds of deltas and recording each
call's model, messages and tools and whether its iterator was closed. Tools are file-local
fakes. The engine, users, character, session, zone rows and registry rows are raw-inserted
(`conftest.py` untouched). Async code is driven with `asyncio.run`, every run bounded by
`asyncio.wait_for`. Each test name ends `__S021_005_DoD<n>`.
"""

from __future__ import annotations

import ast
import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, Table, select, update

from app.db import schema
from app.errors import (
    LlmUnreachableError,
    ModelNotChosenError,
    ModelNotEnabledError,
    NoModelEnabledError,
)
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services import compose as compose_module
from app.services.compose import compose_stream
from app.services.llm.chat import ChatMessage, ToolCall
from app.services.llm.client import ChatDelta, ToolCallDelta
from app.services.llm.frames import (
    AcceptedFrame,
    DoneFrame,
    TokenFrame,
    ToolFailFrame,
    ToolResultFrame,
    ToolStartFrame,
)
from app.services.tools import PRODUCTION_TOOL_REGISTRY, Tool, ToolOutcome, ToolScope
from app.services.tools.definitions import MEMO_SEARCH

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

USER_A = 9_551_001
USER_B = 9_551_002

CHAR_A = 1_501
CHAR_B = 2_501

SESSION_A = 5_501
SESSION_B = 6_501

SERVER_A = 8_501
MODEL_ROW_A = 8_601
MODEL_ROW_OFF = 8_602
MODEL_NAME = "story-model-7b"
MODEL_OFF_NAME = "retired-model-3b"
BASE_URL = "http://chat-compose.test:8080"

#: The zone's user row (the roleplayer's committed text).
ZONE_USER_ROW = 4_501
ZONE_USER_TEXT = "The partner asks where we spend the night."

#: The accepted id the route would hand the source.
ACCEPTED_ID = ZONE_USER_ROW

REQUEST_TIMEOUT = 30.0

#: 020's prompt-format markers.
H_LANGUAGES = "=== Languages ==="
CANDIDATES = "- Candidates:"

#: Literals (context.md).
THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"
FAILED_CONTENT = "The tool failed. Continue without its result."
FAILED_CODE = "tool_failed"

#: Bound for every asyncio run.
RUN_TIMEOUT_SECONDS = 10.0


# --- seeding -----------------------------------------------------------------------------


def _servers() -> Table:
    return schema.metadata.tables["llm_servers"]


def _models() -> Table:
    return schema.metadata.tables["models"]


def _insert_user(
    engine: Engine, *, user_id: int, username: str, rp_language: str | None = None
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.users.insert().values(
                id=user_id,
                username=username,
                password_hash="not-a-real-hash",
                role=Role.ROLEPLAYER,
                is_enabled=True,
                rp_language=rp_language,
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
                model_server_id=None,
                model_name=None,
                system_prompt=None,
                tool_memo_search=None,
                tool_session_search=None,
                tool_web_search=None,
            )
        )


def _insert_session(
    engine: Engine,
    *,
    session_id: int,
    user_id: int,
    character_id: int,
    model_server_id: int | None,
    model_name: str | None,
) -> None:
    """A session with all three tool switches explicitly on."""
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
                model_server_id=model_server_id,
                model_name=model_name,
                system_prompt=None,
                tool_memo_search=True,
                tool_session_search=True,
                tool_web_search=True,
                rp_language=None,
                preferred_language=None,
            )
        )


def _insert_server(engine: Engine, *, server_id: int, base_url: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            _servers()
            .insert()
            .values(
                id=server_id,
                name=f"server {server_id}",
                kind="llamaswap",
                base_url=base_url,
                api_key_ref=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_model(
    engine: Engine, *, model_id: int, server_id: int, name: str, enabled: bool
) -> None:
    with engine.begin() as connection:
        connection.execute(
            _models()
            .insert()
            .values(
                id=model_id,
                server_id=server_id,
                model_name=name,
                is_enabled=enabled,
                is_embedding_designated=False,
                embedding_dim=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_message(
    engine: Engine, *, message_id: int, session_id: int, user_id: int, role: str, text: str
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.messages.insert().values(
                id=message_id,
                user_id=user_id,
                session_id=session_id,
                role=role,
                kind=None,
                text=text,
                related_to=None,
                settled_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
                tool_name=None,
                tool_payload=None,
            )
        )


def _set_session_model(engine: Engine, server_id: int | None, name: str | None) -> None:
    with engine.begin() as connection:
        connection.execute(
            update(schema.sessions)
            .where(schema.sessions.c.id == SESSION_A)
            .values(model_server_id=server_id, model_name=name)
        )


def _set_model_enabled(engine: Engine, model_id: int, enabled: bool) -> None:
    with engine.begin() as connection:
        connection.execute(
            update(_models()).where(_models().c.id == model_id).values(is_enabled=enabled)
        )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """User A (RP language Japanese) with a character and a session whose captured model is an
    enabled model on one server, and one user row in its zone; user B with their own session."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="aster", rp_language="Japanese")
    _insert_user(db_engine, user_id=USER_B, username="briar", rp_language="German")
    _insert_character(db_engine, character_id=CHAR_A, user_id=USER_A, name="Aria")
    _insert_character(db_engine, character_id=CHAR_B, user_id=USER_B, name="Bram")
    _insert_server(db_engine, server_id=SERVER_A, base_url=BASE_URL)
    _insert_model(
        db_engine, model_id=MODEL_ROW_A, server_id=SERVER_A, name=MODEL_NAME, enabled=True
    )
    _insert_model(
        db_engine, model_id=MODEL_ROW_OFF, server_id=SERVER_A, name=MODEL_OFF_NAME, enabled=False
    )
    _insert_session(
        db_engine,
        session_id=SESSION_A,
        user_id=USER_A,
        character_id=CHAR_A,
        model_server_id=SERVER_A,
        model_name=MODEL_NAME,
    )
    _insert_session(
        db_engine,
        session_id=SESSION_B,
        user_id=USER_B,
        character_id=CHAR_B,
        model_server_id=SERVER_A,
        model_name=MODEL_NAME,
    )
    _insert_message(
        db_engine,
        message_id=ZONE_USER_ROW,
        session_id=SESSION_A,
        user_id=USER_A,
        role="user",
        text=ZONE_USER_TEXT,
    )
    return db_engine


@pytest.fixture
def generator() -> SnowflakeGenerator:
    return SnowflakeGenerator(node_id=1)


# --- the fake chat client and factory ------------------------------------------------------

#: One round: deltas in order, optionally ending in an exception to raise.
Round = Sequence[ChatDelta | BaseException]


class ChatCall:
    """What one `chat_stream` call received, and what became of its iterator."""

    def __init__(
        self, model: str, messages: list[ChatMessage], tools: list[Mapping[str, object]]
    ) -> None:
        self.model = model
        self.messages = messages
        self.tools = tools
        self.closed = False
        self.exhausted = False


class FakeChatClient:
    """Replays scripted rounds, one per `chat_stream` call; records every call."""

    def __init__(self, rounds: Sequence[Round]) -> None:
        self.rounds = list(rounds)
        self.calls: list[ChatCall] = []

    def chat_stream(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        tools: Sequence[Mapping[str, object]],
    ) -> AsyncIterator[ChatDelta]:
        call = ChatCall(model, list(messages), [dict(tool) for tool in tools])
        index = len(self.calls)
        self.calls.append(call)
        return self._stream(call, index)

    async def _stream(self, call: ChatCall, index: int) -> AsyncIterator[ChatDelta]:
        if index >= len(self.rounds):
            raise AssertionError(f"chat_stream called {index + 1} times; only {len(self.rounds)} scripted")
        try:
            for item in self.rounds[index]:
                if isinstance(item, BaseException):
                    raise item
                await asyncio.sleep(0)
                yield item
            call.exhausted = True
        except GeneratorExit:
            call.closed = True
            raise


class FakeFactory:
    """A `ChatClientFactory` returning one fake client and recording its arguments."""

    def __init__(self, client: FakeChatClient) -> None:
        self.client = client
        self.calls: list[tuple[str, str | None, float]] = []

    def __call__(self, base_url: str, api_key: str | None, timeout_seconds: float) -> Any:
        self.calls.append((base_url, api_key, timeout_seconds))
        return self.client


# --- fake tools ----------------------------------------------------------------------------


class RecordingTool:
    """A fake `Tool` returning a fixed outcome; records each call's arguments."""

    def __init__(self, name: str, outcome: ToolOutcome | None = None) -> None:
        self.name = name
        self.outcome = outcome or ToolOutcome(content=f"{name} content", summary=f"{name} summary")
        self.arguments: list[dict[str, object]] = []

    async def run(
        self, scope: ToolScope, connection: Connection, arguments: Mapping[str, object]
    ) -> ToolOutcome:
        self.arguments.append(dict(arguments))
        return self.outcome


class RaisingTool(RecordingTool):
    """A fake whose `run` raises."""

    async def run(
        self, scope: ToolScope, connection: Connection, arguments: Mapping[str, object]
    ) -> ToolOutcome:
        self.arguments.append(dict(arguments))
        raise RuntimeError("the memo index is down")


def _registry(*tools: RecordingTool) -> dict[str, Tool]:
    return {tool.name: tool for tool in tools}


# --- delta builders ------------------------------------------------------------------------


def _content(text: str) -> ChatDelta:
    return ChatDelta(content=text)


def _reasoning(text: str) -> ChatDelta:
    return ChatDelta(reasoning=text)


def _call_fragment(
    index: int,
    *,
    call_id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
) -> ChatDelta:
    return ChatDelta(
        tool_calls=(ToolCallDelta(index=index, call_id=call_id, name=name, arguments=arguments),)
    )


def _one_call_round(call_id: str | None, arguments: str, name: str = "memo_search") -> Round:
    return [_call_fragment(0, call_id=call_id, name=name, arguments=arguments)]


# --- drivers --------------------------------------------------------------------------------


def _source(
    engine: Engine,
    generator: SnowflakeGenerator,
    factory: FakeFactory,
    registry: Mapping[str, Tool],
    accepted_id: int | None = None,
) -> Any:
    return compose_stream(
        engine,
        generator,
        USER_A,
        SESSION_A,
        accepted_id,
        REQUEST_TIMEOUT,
        factory,
        registry,
    )


def _run(
    engine: Engine,
    generator: SnowflakeGenerator,
    factory: FakeFactory,
    registry: Mapping[str, Tool] | None = None,
    accepted_id: int | None = None,
) -> list[Any]:
    """Drain the source; return every frame."""

    async def collect() -> list[Any]:
        frames: list[Any] = []
        async for frame in _source(
            engine, generator, factory, registry or PRODUCTION_TOOL_REGISTRY, accepted_id
        ):
            frames.append(frame)
        return frames

    return asyncio.run(asyncio.wait_for(collect(), timeout=RUN_TIMEOUT_SECONDS))


def _run_until_error(
    engine: Engine,
    generator: SnowflakeGenerator,
    factory: FakeFactory,
    expected: type[BaseException],
    accepted_id: int | None = None,
) -> tuple[list[Any], BaseException]:
    """Drain the source expecting it to raise `expected`; return the frames before it."""

    async def collect() -> tuple[list[Any], BaseException]:
        frames: list[Any] = []
        try:
            async for frame in _source(
                engine, generator, factory, PRODUCTION_TOOL_REGISTRY, accepted_id
            ):
                frames.append(frame)
        except expected as error:
            return frames, error
        raise AssertionError(f"the source ended without raising {expected.__name__}: {frames!r}")

    return asyncio.run(asyncio.wait_for(collect(), timeout=RUN_TIMEOUT_SECONDS))


def _rows(engine: Engine, role: str) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            select(schema.messages)
            .where(schema.messages.c.role == role)
            .order_by(schema.messages.c.id)
        ).mappings()
        return [dict(row) for row in rows]


def _tokens(frames: Sequence[Any]) -> list[str]:
    return [frame.text for frame in frames if isinstance(frame, TokenFrame)]


def _assert_done_matches_the_one_assistant_row(engine: Engine, frames: Sequence[Any]) -> dict[str, Any]:
    assert isinstance(frames[-1], DoneFrame)
    rows = _rows(engine, "assistant")
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == frames[-1].message_id
    assert row["session_id"] == SESSION_A
    assert row["user_id"] == USER_A
    assert row["settled_at"] is None
    assert row["related_to"] is None
    return row


# =========================================================================================
# DoD-1: accepted only when an id is given
# =========================================================================================


def test_an_accepted_id_gives_accepted_as_the_first_frame__S021_005_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-1 / D2 — given an accepted id, the first frame is `accepted` with that id."""
    factory = FakeFactory(FakeChatClient([[_content("Hi")]]))

    frames = _run(engine, generator, factory, accepted_id=ACCEPTED_ID)

    assert frames[0] == AcceptedFrame(message_id=ACCEPTED_ID)
    assert [f for f in frames if isinstance(f, AcceptedFrame)] == [AcceptedFrame(message_id=ACCEPTED_ID)]
    assert isinstance(frames[-1], DoneFrame)


def test_no_accepted_id_yields_no_accepted_frame__S021_005_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-1 / D2 — a textless compose yields no `accepted` frame at all."""
    factory = FakeFactory(FakeChatClient([[_content("Hi")]]))

    frames = _run(engine, generator, factory, accepted_id=None)

    assert not any(isinstance(frame, AcceptedFrame) for frame in frames)
    assert isinstance(frames[0], TokenFrame)
    assert isinstance(frames[-1], DoneFrame)


# =========================================================================================
# DoD-2: the assembled system prompt and the zone are sent to the captured model
# =========================================================================================


def test_the_first_call_gets_the_system_prompt_then_the_zone_and_the_captured_model__S021_005_DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-2 / US-037.AC-1 / UC-034 / R4 — messages[0] is a system message holding the
    Languages section with Japanese on the Candidates line; messages[1] is the zone's user
    message; the model is the session's captured model name."""
    client = FakeChatClient([[_content("Hi")]])
    factory = FakeFactory(client)

    _run(engine, generator, factory)

    assert len(client.calls) >= 1
    first = client.calls[0]
    assert first.model == MODEL_NAME
    assert len(first.messages) >= 2
    system = first.messages[0]
    assert system.role == "system"
    lines = system.content.split("\n")
    assert H_LANGUAGES in lines
    candidates = [line for line in lines if line.startswith(CANDIDATES)]
    assert len(candidates) == 1
    assert "Japanese" in candidates[0]
    zone = first.messages[1]
    assert zone.role == "user"
    assert zone.content == ZONE_USER_TEXT
    assert len(first.messages) == 2


def test_the_factory_is_called_with_the_server_and_the_timeout__S021_005_DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-2 / R4 / D14 — the client is opened for the captured model's server (NULL key ref)
    with the given timeout."""
    factory = FakeFactory(FakeChatClient([[_content("Hi")]]))

    _run(engine, generator, factory)

    assert factory.calls == [(BASE_URL, None, REQUEST_TIMEOUT)]


# =========================================================================================
# DoD-3: content → tokens → done; one assistant row with the text
# =========================================================================================


def test_content_deltas_become_tokens_then_done_and_one_assistant_row__S021_005_DoD3(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-3 / UC-034 / 019 D4 — token `Once `, token `upon`, `done(id)`; the zone holds an
    assistant row `Once upon` whose id is the done id."""
    factory = FakeFactory(FakeChatClient([[_content("Once "), _content("upon")]]))

    frames = _run(engine, generator, factory)

    assert frames[:2] == [TokenFrame(text="Once "), TokenFrame(text="upon")]
    assert len(frames) == 3
    row = _assert_done_matches_the_one_assistant_row(engine, frames)
    assert row["text"] == "Once upon"


# =========================================================================================
# DoD-4: reasoning wrapped in <think> tokens
# =========================================================================================


@pytest.mark.parametrize(
    ("round_", "expected_tokens"),
    [
        (
            [_reasoning("r1"), _reasoning("r2"), _content("Hi")],
            [THINK_OPEN, "r1", "r2", THINK_CLOSE, "Hi"],
        ),
        ([_reasoning("r1")], [THINK_OPEN, "r1", THINK_CLOSE]),
        ([_content("<think>x</think>Hi")], ["<think>x</think>Hi"]),
    ],
    ids=["reasoning-then-content", "reasoning-only", "inline-think-content"],
)
def test_reasoning_is_streamed_as_think_wrapped_tokens__S021_005_DoD4(
    engine: Engine,
    generator: SnowflakeGenerator,
    round_: Round,
    expected_tokens: list[str],
) -> None:
    """DoD-4 / D4 — reasoning runs are wrapped in `<think>` / `</think>` tokens, closed when
    content begins or the round ends; inline tags in content pass untouched; the persisted row
    text is the concatenation of the tokens."""
    factory = FakeFactory(FakeChatClient([round_]))

    frames = _run(engine, generator, factory)

    assert _tokens(frames) == expected_tokens
    assert all(isinstance(frame, TokenFrame) for frame in frames[:-1])
    row = _assert_done_matches_the_one_assistant_row(engine, frames)
    assert row["text"] == "".join(expected_tokens)


# =========================================================================================
# DoD-5: one fragmented tool call, then an answer
# =========================================================================================

MEMO_OUTCOME = ToolOutcome(content="Memo: the inn is called The Gilded Goose.", summary="1 memo found")


def test_a_fragmented_tool_call_is_dispatched_and_the_loop_continues__S021_005_DoD5(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-5 / D11 — three fragments accumulate into one call; frames `tool_start` (args
    `{"query":"inn"}`), `tool_result`, then round 2's tokens and `done`."""
    fake = RecordingTool("memo_search", MEMO_OUTCOME)
    client = FakeChatClient(
        [
            [
                _call_fragment(0, call_id="call_a", name="memo_search"),
                _call_fragment(0, arguments='{"query":'),
                _call_fragment(0, arguments='"inn"}'),
            ],
            [_content("We stay at "), _content("the Goose.")],
        ]
    )

    frames = _run(engine, generator, FakeFactory(client), _registry(fake))

    assert len(frames) == 5
    start, result = frames[0], frames[1]
    assert isinstance(start, ToolStartFrame)
    assert start.tool == "memo_search"
    assert start.call_id == "call_a"
    assert dict(start.args) == {"query": "inn"}
    assert result == ToolResultFrame(tool="memo_search", call_id="call_a", summary="1 memo found")
    assert frames[2:4] == [TokenFrame(text="We stay at "), TokenFrame(text="the Goose.")]
    row = _assert_done_matches_the_one_assistant_row(engine, frames)
    assert row["text"] == "We stay at the Goose."
    assert fake.arguments == [{"query": "inn"}]


def test_the_second_call_gets_the_assistant_call_then_the_tool_message__S021_005_DoD5(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-5 / D11 — the second call's conversation is the first's plus an assistant message
    carrying the one call (arguments `{"query":"inn"}`) and the tool message (`call_a`, the
    fake's content)."""
    fake = RecordingTool("memo_search", MEMO_OUTCOME)
    client = FakeChatClient(
        [
            [
                _call_fragment(0, call_id="call_a", name="memo_search"),
                _call_fragment(0, arguments='{"query":'),
                _call_fragment(0, arguments='"inn"}'),
            ],
            [_content("We stay at the Goose.")],
        ]
    )

    _run(engine, generator, FakeFactory(client), _registry(fake))

    assert len(client.calls) == 2
    first, second = client.calls
    assert second.model == MODEL_NAME
    assert len(second.messages) == len(first.messages) + 2
    assert second.messages[: len(first.messages)] == first.messages
    assistant, tool = second.messages[-2], second.messages[-1]
    assert assistant.role == "assistant"
    assert assistant.content == ""
    assert tuple(assistant.tool_calls) == (
        ToolCall(call_id="call_a", name="memo_search", arguments='{"query":"inn"}'),
    )
    assert tool.role == "tool"
    assert tool.tool_call_id == "call_a"
    assert tool.content == MEMO_OUTCOME.content


def test_one_assistant_row_and_one_tool_row_are_written__S021_005_DoD5(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-5 — exactly one assistant row and one tool row after the exchange."""
    fake = RecordingTool("memo_search", MEMO_OUTCOME)
    client = FakeChatClient(
        [
            [
                _call_fragment(0, call_id="call_a", name="memo_search"),
                _call_fragment(0, arguments='{"query":'),
                _call_fragment(0, arguments='"inn"}'),
            ],
            [_content("We stay at the Goose.")],
        ]
    )

    _run(engine, generator, FakeFactory(client), _registry(fake))

    assert len(_rows(engine, "assistant")) == 1
    assert len(_rows(engine, "tool")) == 1


def test_the_first_calls_tools_list_is_exactly_the_memo_search_declaration__S021_005_DoD5(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-5 / D5 — `memo_search` registered and switched on → tools = [its declaration]."""
    fake = RecordingTool("memo_search", MEMO_OUTCOME)
    client = FakeChatClient(
        [
            _one_call_round("call_a", '{"query":"inn"}'),
            [_content("We stay at the Goose.")],
        ]
    )

    _run(engine, generator, FakeFactory(client), _registry(fake))

    assert client.calls[0].tools == [dict(MEMO_SEARCH)]


# =========================================================================================
# DoD-6: a raising tool is a failed result; the exchange continues
# =========================================================================================


def test_a_raising_tool_gives_tool_fail_and_the_exchange_carries_on__S021_005_DoD6(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-6 / R9 / UC-051 / UC-053 — `tool_start`, `tool_fail` (`tool_failed`), then round
    2's tokens and `done`; the second call's last message is the failed literal."""
    fake = RaisingTool("memo_search")
    client = FakeChatClient(
        [
            _one_call_round("call_f", '{"query":"inn"}'),
            [_content("Without notes: "), _content("the Goose.")],
        ]
    )

    frames = _run(engine, generator, FakeFactory(client), _registry(fake))

    assert isinstance(frames[0], ToolStartFrame)
    assert frames[0].call_id == "call_f"
    assert frames[1] == ToolFailFrame(tool="memo_search", call_id="call_f", code=FAILED_CODE)
    assert frames[2:4] == [TokenFrame(text="Without notes: "), TokenFrame(text="the Goose.")]
    assert len(frames) == 5
    row = _assert_done_matches_the_one_assistant_row(engine, frames)
    assert row["text"] == "Without notes: the Goose."

    assert len(client.calls) == 2
    last = client.calls[1].messages[-1]
    assert last.role == "tool"
    assert last.tool_call_id == "call_f"
    assert last.content == FAILED_CONTENT


# =========================================================================================
# DoD-7: no cap on rounds
# =========================================================================================


def test_thirty_tool_rounds_then_an_answer_has_no_cap__S021_005_DoD7(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-7 / FEAT-010 / D11 — 30 single-call rounds then a content round → 30 start/result
    pairs, then tokens and `done`; 31 client calls."""
    fake = RecordingTool("memo_search", MEMO_OUTCOME)
    rounds: list[Round] = [
        _one_call_round(f"call_r{n}", f'{{"query":"q{n}"}}') for n in range(1, 31)
    ]
    rounds.append([_content("Finally, "), _content("an answer.")])
    client = FakeChatClient(rounds)

    frames = _run(engine, generator, FakeFactory(client), _registry(fake))

    assert len(client.calls) == 31
    tool_frames = frames[:60]
    for n in range(1, 31):
        start, result = tool_frames[2 * (n - 1)], tool_frames[2 * (n - 1) + 1]
        assert isinstance(start, ToolStartFrame)
        assert start.call_id == f"call_r{n}"
        assert dict(start.args) == {"query": f"q{n}"}
        assert result == ToolResultFrame(
            tool="memo_search", call_id=f"call_r{n}", summary=MEMO_OUTCOME.summary
        )
    assert frames[60:62] == [TokenFrame(text="Finally, "), TokenFrame(text="an answer.")]
    assert len(frames) == 63
    row = _assert_done_matches_the_one_assistant_row(engine, frames)
    assert row["text"] == "Finally, an answer."


# =========================================================================================
# DoD-8: two calls in one round, dispatched in index order
# =========================================================================================


def test_two_calls_in_one_round_are_dispatched_in_index_order__S021_005_DoD8(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-8 / D11 — fragments of index 0 and 1 interleaved (index 1 arriving first) →
    `tool_start` 0, result 0, `tool_start` 1, result 1; the next call's assistant message
    carries both calls in index order, followed by their tool messages."""
    fake = RecordingTool("memo_search", MEMO_OUTCOME)
    client = FakeChatClient(
        [
            [
                _call_fragment(1, call_id="call_y", name="memo_search"),
                _call_fragment(0, call_id="call_x", name="memo_search"),
                _call_fragment(1, arguments='{"query":'),
                _call_fragment(0, arguments='{"query":'),
                _call_fragment(0, arguments='"a"}'),
                _call_fragment(1, arguments='"b"}'),
            ],
            [_content("Both read.")],
        ]
    )

    frames = _run(engine, generator, FakeFactory(client), _registry(fake))

    start0, result0, start1, result1 = frames[:4]
    assert isinstance(start0, ToolStartFrame)
    assert start0.call_id == "call_x"
    assert dict(start0.args) == {"query": "a"}
    assert result0 == ToolResultFrame(
        tool="memo_search", call_id="call_x", summary=MEMO_OUTCOME.summary
    )
    assert isinstance(start1, ToolStartFrame)
    assert start1.call_id == "call_y"
    assert dict(start1.args) == {"query": "b"}
    assert result1 == ToolResultFrame(
        tool="memo_search", call_id="call_y", summary=MEMO_OUTCOME.summary
    )
    assert frames[4] == TokenFrame(text="Both read.")
    assert isinstance(frames[5], DoneFrame)
    assert fake.arguments == [{"query": "a"}, {"query": "b"}]

    assert len(client.calls) == 2
    first, second = client.calls
    appended = second.messages[len(first.messages) :]
    assert len(appended) == 3
    assistant = appended[0]
    assert assistant.role == "assistant"
    assert tuple(assistant.tool_calls) == (
        ToolCall(call_id="call_x", name="memo_search", arguments='{"query":"a"}'),
        ToolCall(call_id="call_y", name="memo_search", arguments='{"query":"b"}'),
    )
    assert [(m.role, m.tool_call_id) for m in appended[1:]] == [
        ("tool", "call_x"),
        ("tool", "call_y"),
    ]


# =========================================================================================
# DoD-9: fallback call ids
# =========================================================================================


def test_id_less_calls_get_fallback_ids_counted_per_exchange__S021_005_DoD9(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-9 / D11 — a call with no provider id is dispatched as `call_1`; a second id-less
    call later in the same exchange is `call_2`; the conversation carries those ids."""
    fake = RecordingTool("memo_search", MEMO_OUTCOME)
    client = FakeChatClient(
        [
            _one_call_round(None, '{"query":"a"}'),
            _one_call_round(None, '{"query":"b"}'),
            [_content("Done reading.")],
        ]
    )

    frames = _run(engine, generator, FakeFactory(client), _registry(fake))

    starts = [frame for frame in frames if isinstance(frame, ToolStartFrame)]
    results = [frame for frame in frames if isinstance(frame, ToolResultFrame)]
    assert [frame.call_id for frame in starts] == ["call_1", "call_2"]
    assert [frame.call_id for frame in results] == ["call_1", "call_2"]

    assert len(client.calls) == 3
    second_round_messages = client.calls[1].messages
    assistant, tool = second_round_messages[-2], second_round_messages[-1]
    assert [call.call_id for call in assistant.tool_calls] == ["call_1"]
    assert tool.tool_call_id == "call_1"
    third_round_messages = client.calls[2].messages
    assistant2, tool2 = third_round_messages[-2], third_round_messages[-1]
    assert [call.call_id for call in assistant2.tool_calls] == ["call_2"]
    assert tool2.tool_call_id == "call_2"


# =========================================================================================
# DoD-10: use-time model check failures propagate after accepted
# =========================================================================================


def _no_model_enabled(engine: Engine) -> None:
    _set_model_enabled(engine, MODEL_ROW_A, False)


def _no_captured_model(engine: Engine) -> None:
    _set_session_model(engine, None, None)


def _captured_model_not_enabled(engine: Engine) -> None:
    _set_session_model(engine, SERVER_A, MODEL_OFF_NAME)


MODEL_FAILURES = [
    pytest.param(_no_model_enabled, NoModelEnabledError, id="no-model-enabled"),
    pytest.param(_no_captured_model, ModelNotChosenError, id="no-captured-model"),
    pytest.param(_captured_model_not_enabled, ModelNotEnabledError, id="captured-not-enabled"),
]


@pytest.mark.parametrize(("arrange", "expected"), MODEL_FAILURES)
@pytest.mark.parametrize("accepted_id", [ACCEPTED_ID, None], ids=["with-accepted", "textless"])
def test_a_failed_model_check_raises_after_accepted_and_calls_no_factory__S021_005_DoD10(
    engine: Engine,
    generator: SnowflakeGenerator,
    arrange: Any,
    expected: type[BaseException],
    accepted_id: int | None,
) -> None:
    """DoD-10 / R4 / D3 — `accepted` (when given), then the model-check error propagates; the
    factory is never called; no assistant row exists."""
    arrange(engine)
    client = FakeChatClient([[_content("never")]])
    factory = FakeFactory(client)

    frames, _ = _run_until_error(engine, generator, factory, expected, accepted_id)

    if accepted_id is None:
        assert frames == []
    else:
        assert frames == [AcceptedFrame(message_id=accepted_id)]
    assert factory.calls == []
    assert client.calls == []
    assert _rows(engine, "assistant") == []


# =========================================================================================
# DoD-11: a provider failure after a token propagates; no row by the source
# =========================================================================================


def test_a_provider_failure_after_a_token_propagates_and_writes_no_row__S021_005_DoD11(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-11 / 019 D4 / US-044.AC-1 — token `Par`, then `LlmUnreachableError` raised; no
    assistant row written by the source."""
    client = FakeChatClient(
        [[_content("Par"), LlmUnreachableError("Provider timed out", {"reason": "unreachable"})]]
    )

    frames, error = _run_until_error(
        engine, generator, FakeFactory(client), LlmUnreachableError
    )

    assert frames == [TokenFrame(text="Par")]
    assert isinstance(error, LlmUnreachableError)
    assert _rows(engine, "assistant") == []


# =========================================================================================
# DoD-12: closing the source closes the provider stream
# =========================================================================================


def test_closing_the_source_after_a_token_closes_the_provider_stream__S021_005_DoD12(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-12 / US-132.AC-2 / D11 — `aclose()` while suspended after a token: the fake
    client's iterator records it was closed (checked before the loop shuts down), and no
    assistant row is written."""
    client = FakeChatClient([[_content("Par"), _content("tial"), _content(" answer")]])
    factory = FakeFactory(client)

    async def scenario() -> tuple[Any, bool, bool]:
        source = _source(engine, generator, factory, PRODUCTION_TOOL_REGISTRY, None)
        first = await source.__anext__()
        await source.aclose()
        call = client.calls[0]
        return first, call.closed, call.exhausted

    first, closed, exhausted = asyncio.run(
        asyncio.wait_for(scenario(), timeout=RUN_TIMEOUT_SECONDS)
    )

    assert first == TokenFrame(text="Par")
    assert len(client.calls) == 1
    assert closed is True
    assert exhausted is False
    assert _rows(engine, "assistant") == []


# =========================================================================================
# DoD-13: production registry → empty tools list
# =========================================================================================


def test_the_production_registry_sends_an_empty_tools_list__S021_005_DoD13(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-13 / D5 / U3 — all switches on, empty registry → the client gets `tools == []`."""
    client = FakeChatClient([[_content("Hi")]])

    _run(engine, generator, FakeFactory(client), PRODUCTION_TOOL_REGISTRY)

    assert len(client.calls) == 1
    assert client.calls[0].tools == []


# =========================================================================================
# DoD-14: compose.py imports no fastapi
# =========================================================================================


def _compose_imports() -> list[str]:
    module_file = compose_module.__file__
    assert module_file is not None
    tree = ast.parse(Path(module_file).read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0:
                found.append(node.module or "")
        elif isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
    return found


def test_compose_imports_no_fastapi__S021_005_DoD14() -> None:
    """DoD-14 / D15 — `compose.py` imports no `fastapi`."""
    offenders = [
        module
        for module in _compose_imports()
        if module == "fastapi" or module.startswith("fastapi.")
    ]
    assert offenders == []
