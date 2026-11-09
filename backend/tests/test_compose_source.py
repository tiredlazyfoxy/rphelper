"""The compose source (`app/services/compose.py`) — feature 021 step 005, moved onto the gateway by
feature 035 step 004.

Feature 035 step 004 (DoD-1..DoD-9
and DoD-14, its context, DEC-035-1/-6/-7 and `DEC-arch-llm-client-library-7`/-8): the
source drains the client's `compose(model, messages, tools)` inside `aclosing`; each text piece
becomes one token frame, verbatim and in order (`<think>` tags included); each frame the runner
emits passes through; on success the joined token text is written as the assistant row and `done`
carries its id. The runner — private to `compose.py` — emits `tool_start`, awaits the seam's
`dispatch`, emits its frame and returns the result message's content; on any `Exception` it emits
a `tool_fail` (`tool_failed`) for that call and returns the seam's fixed failed text; cancellation
propagates. The clauses of 021 step 005 that described the old round loop (fragment accumulation,
reasoning wrapping, per-round conversations, fallback ids) now belong to the gateway and are
covered by its own tests; the clauses that still hold here (accepted, the prompt sent, the
model-check refusals, the provider failure, the close, the offered declarations, the import rule)
keep their `__S021_005_DoD<n>` tags and gain the 035 id they also cover.

Bindings come from feature 035's status record, `## Skeleton`:

- `compose_stream(engine, generator, user_id, session_id, accepted_id, timeout_seconds,
  client_factory, registry) -> AsyncGenerator[Frame, None]` (035 step 004, unchanged)
- `ChatClientFactory = Callable[[str, str, str | None, float], ChatClientLike]` — `(kind,
  base_url, api_key, timeout_seconds)` (035 step 004)
- `ComposeText(text)`, `ComposeTools[E](declarations, runner)` with
  `runner(call: ToolCall, emit: Callable[[E], None]) -> Awaitable[str]` (035 step 003)
- `ToolCall(call_id, name, arguments)` (021 step 002); the frames of 019 step 001;
  `frame_stream(request, source, on_partial)` and `own_connection_persister(engine, generator,
  user_id, session_id)` (019 step 002, used for the stop-during-a-tool clause)

The chat client is a file-local fake in the gateway shape: a generic async-generator `compose` that
plays a script of text pieces, whole tool calls and exceptions; for a tool call it awaits
`tools.runner(ToolCall("call_<n>", ...), emitted.append)` exactly as the gateway would, then yields
each emitted event and continues. Tools are file-local fakes. Rows are raw-inserted (`conftest.py`
untouched). Async code is driven with `asyncio.run`, every run bounded by `asyncio.wait_for`.

Feature 035 step 006 (DoD-9..DoD-13, tagged `__S035_006_DoD<n>`;
DEC-035-17, DEC-035-18, `DEC-arch-llm-client-library-15`): the fake also plays `Reject` steps,
yielding `ComposeRejected(call=ToolCall("call_<n>", name, arguments), kind=...)` from the same
counter (frozen skeleton binding). The source turns each into `tool_start` then `tool_fail`
(`tool_failed`) without dispatching, writes one failed tool row, and logs the tool name and kind.
"""

from __future__ import annotations

import ast
import asyncio
import json
from collections.abc import AsyncGenerator, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from loguru import logger
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
from app.services.llm.frames import (
    AcceptedFrame,
    DoneFrame,
    TokenFrame,
    ToolFailFrame,
    ToolResultFrame,
    ToolStartFrame,
    frame_stream,
    own_connection_persister,
)
from app.services.llm.gateway import ComposeRejected, ComposeRejectionKind, ComposeText, ComposeTools
from app.services.messages import list_zone
from app.services.tools import PRODUCTION_TOOL_REGISTRY, Tool, ToolOutcome, ToolScope
from app.services.tools.definitions import MEMO_SEARCH, SESSION_SEARCH, WEB_SEARCH
from tests.privacy_audit_support import (
    FakeChatClientFactory,
    failure_round,
    text_round,
    tool_call_round,
)

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

USER_A = 9_551_001
USER_B = 9_551_002

CHAR_A = 1_501
CHAR_B = 2_501

SESSION_A = 5_501
SESSION_B = 6_501

SERVER_A = 8_501
SERVER_KIND = "llamaswap"
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

#: The seam's fixed model-facing failed text and the failed-tool code (021 literals table,
#: `backend-structure.md` error model).
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
                kind=SERVER_KIND,
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


def _set_switches(engine: Engine, *, memo: bool, session: bool, web: bool) -> None:
    with engine.begin() as connection:
        connection.execute(
            update(schema.sessions)
            .where(schema.sessions.c.id == SESSION_A)
            .values(tool_memo_search=memo, tool_session_search=session, tool_web_search=web)
        )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """User A (RP language Japanese) with a character and a session whose captured model is an
    enabled model on one `llamaswap` server, and one user row in its zone; user B with their own
    session."""
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


# --- the fake chat client and factory (gateway shape, DEC-035-6) ---------------------------


@dataclass(frozen=True)
class Text:
    """A scripted text piece: the fake yields it as one `ComposeText`."""

    text: str


@dataclass(frozen=True)
class Call:
    """A scripted whole tool call: the fake hands it to the runner as `ToolCall("call_<n>", ...)`."""

    name: str
    arguments: str


@dataclass(frozen=True)
class Reject:
    """A scripted model-side rejection (035 step 006, DEC-035-17): the fake yields one
    `ComposeRejected` whose call is `ToolCall("call_<n>", name, arguments)` — `<n>` taken from the
    same counter `Call` uses, as the gateway mints it — with the rejection `kind`."""

    name: str
    arguments: str
    kind: str


#: One exchange's script: text pieces, tool calls, rejections and exceptions (raised from inside
#: the stream).
Step = Text | Call | Reject | BaseException


class ComposeCall:
    """What one `compose` call received, and how its stream ended.

    `finalized` is set when the stream's body is left by any route (completion, an exception,
    a close or a cancellation); `exhausted` only when the whole script was played. A stream that
    is `finalized` but not `exhausted` was closed (or raised) early.
    """

    def __init__(self, model: str, messages: list[ChatMessage], declarations: list[dict[str, object]]) -> None:
        self.model = model
        self.messages = messages
        self.declarations = declarations
        self.finalized = False
        self.exhausted = False


class FakeChatClient:
    """A gateway-shaped chat client playing one script per `compose` call; records every call and
    every text the runner returned (the model-facing tool output)."""

    def __init__(self, script: Sequence[Step]) -> None:
        self.script = list(script)
        self.calls: list[ComposeCall] = []
        self.tool_outputs: list[str] = []

    async def complete(self, model: str, messages: Sequence[ChatMessage]) -> str:
        raise AssertionError("the compose source never calls `complete`")

    async def compose[E](
        self,
        model: str,
        messages: Sequence[ChatMessage],
        tools: ComposeTools[E],
    ) -> AsyncGenerator[ComposeText | ComposeRejected | E, None]:
        call = ComposeCall(model, list(messages), [dict(one) for one in tools.declarations])
        self.calls.append(call)
        minted = 0
        try:
            for step in self.script:
                await asyncio.sleep(0)
                if isinstance(step, BaseException):
                    raise step
                if isinstance(step, Text):
                    yield ComposeText(step.text)
                    continue
                if isinstance(step, Reject):
                    # 035 step 006: a model-side rejection is its own stream value; the runner is
                    # never involved, but the id comes from the same per-compose counter.
                    minted += 1
                    rejected = ToolCall(call_id=f"call_{minted}", name=step.name, arguments=step.arguments)
                    yield ComposeRejected(call=rejected, kind=ComposeRejectionKind(step.kind))
                    continue
                # The gateway's half of the wrapper (DEC-035-6): mint `call_<n>`, await the runner,
                # then hand on what it emitted, in order.
                minted += 1
                emitted: list[E] = []
                tool_call = ToolCall(call_id=f"call_{minted}", name=step.name, arguments=step.arguments)
                output = await tools.runner(tool_call, emitted.append)
                self.tool_outputs.append(output)
                for event in emitted:
                    yield event
            call.exhausted = True
        finally:
            call.finalized = True


class FakeFactory:
    """A `ChatClientFactory` returning one fake client and recording its four arguments."""

    def __init__(self, client: Any) -> None:
        self.client = client
        self.calls: list[tuple[str, str, str | None, float]] = []

    def __call__(self, kind: str, base_url: str, api_key: str | None, timeout_seconds: float) -> Any:
        self.calls.append((kind, base_url, api_key, timeout_seconds))
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


class BlockingTool(RecordingTool):
    """A fake whose `run` signals it has started and then never finishes — a tool still running
    when the roleplayer stops (DoD-8). `cancelled` records that the stop reached it."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.started = asyncio.Event()
        self.cancelled = False

    async def run(
        self, scope: ToolScope, connection: Connection, arguments: Mapping[str, object]
    ) -> ToolOutcome:
        self.arguments.append(dict(arguments))
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        raise AssertionError("unreachable: the blocking tool never finishes")


def _registry(*tools: RecordingTool) -> dict[str, Tool]:
    return {tool.name: tool for tool in tools}


# --- drivers --------------------------------------------------------------------------------


def _source(
    engine: Engine,
    generator: SnowflakeGenerator,
    factory: Any,
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
    factory: Any,
    registry: Mapping[str, Tool] | None = None,
    accepted_id: int | None = None,
) -> list[Any]:
    """Drain the source; return every frame."""

    async def collect() -> list[Any]:
        frames: list[Any] = []
        async for frame in _source(
            engine, generator, factory, PRODUCTION_TOOL_REGISTRY if registry is None else registry, accepted_id
        ):
            frames.append(frame)
        return frames

    return asyncio.run(asyncio.wait_for(collect(), timeout=RUN_TIMEOUT_SECONDS))


def _run_until_error(
    engine: Engine,
    generator: SnowflakeGenerator,
    factory: Any,
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


class NeverDisconnected:
    """The harness's request stand-in: only `is_disconnected()` exists, and it never reports a
    disconnect — the stop in DoD-8 arrives as a cancellation, as a server delivers it."""

    async def is_disconnected(self) -> bool:
        return False


# =========================================================================================
# 021 DoD-1: accepted only when an id is given
# =========================================================================================


def test_an_accepted_id_gives_accepted_as_the_first_frame__S021_005_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """021 DoD-1 / D2 — given an accepted id, the first frame is `accepted` with that id."""
    factory = FakeFactory(FakeChatClient([Text("Hi")]))

    frames = _run(engine, generator, factory, accepted_id=ACCEPTED_ID)

    assert frames[0] == AcceptedFrame(message_id=ACCEPTED_ID)
    assert [f for f in frames if isinstance(f, AcceptedFrame)] == [AcceptedFrame(message_id=ACCEPTED_ID)]
    assert isinstance(frames[-1], DoneFrame)


def test_no_accepted_id_yields_no_accepted_frame__S021_005_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """021 DoD-1 / D2 — a textless compose yields no `accepted` frame at all."""
    factory = FakeFactory(FakeChatClient([Text("Hi")]))

    frames = _run(engine, generator, factory, accepted_id=None)

    assert not any(isinstance(frame, AcceptedFrame) for frame in frames)
    assert isinstance(frames[0], TokenFrame)
    assert isinstance(frames[-1], DoneFrame)


# =========================================================================================
# 021 DoD-2 / 035 DoD-1: the prompt and the zone go to the captured model on its server
# =========================================================================================


def test_compose_gets_the_system_prompt_then_the_zone_and_the_captured_model__S021_005_DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """021 DoD-2 / US-037.AC-1 / UC-034 — one `compose` call: messages[0] is a system message
    holding the Languages section with Japanese on the Candidates line; messages[1] is the zone's
    user message; the model is the session's captured model name."""
    client = FakeChatClient([Text("Hi")])
    factory = FakeFactory(client)

    _run(engine, generator, factory)

    assert len(client.calls) == 1
    first = client.calls[0]
    assert first.model == MODEL_NAME
    assert len(first.messages) == 2
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


def test_the_factory_is_called_with_the_kind_the_server_and_the_timeout__S021_005_DoD2__S035_004_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """035 DoD-1 / 021 DoD-2 / D14 — the client is opened for the captured model's server: its
    `kind`, its base URL, the (NULL-ref) key and the given timeout, in that order."""
    factory = FakeFactory(FakeChatClient([Text("Hi")]))

    _run(engine, generator, factory)

    assert factory.calls == [(SERVER_KIND, BASE_URL, None, REQUEST_TIMEOUT)]


# =========================================================================================
# 035 DoD-2: one token per text piece, verbatim; the row is the joined token text
# =========================================================================================


def test_each_text_piece_is_one_token_frame_verbatim_then_done_with_the_row_id__S035_004_DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """035 DoD-2 / UC-034 / US-114 / US-146 — four pieces, two of them `<think>` markup: exactly
    four token frames carrying the pieces verbatim and in order, then `done`; the one assistant
    row holds the joined text and its id is the `done` id."""
    pieces = ["<think>plan the scene", "</think>", "Once ", "upon"]
    factory = FakeFactory(FakeChatClient([Text(piece) for piece in pieces]))

    frames = _run(engine, generator, factory)

    assert frames[:-1] == [TokenFrame(text=piece) for piece in pieces]
    assert len(frames) == len(pieces) + 1
    row = _assert_done_matches_the_one_assistant_row(engine, frames)
    assert row["text"] == "".join(pieces)
    assert row["text"] == "<think>plan the scene</think>Once upon"


def test_text_pieces_become_tokens_then_done_and_one_assistant_row__S021_005_DoD3__S035_004_DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """021 DoD-3 / 035 DoD-2 — token `Once `, token `upon`, `done(id)`; the zone holds an assistant
    row `Once upon` whose id is the done id."""
    factory = FakeFactory(FakeChatClient([Text("Once "), Text("upon")]))

    frames = _run(engine, generator, factory)

    assert frames[:2] == [TokenFrame(text="Once "), TokenFrame(text="upon")]
    assert len(frames) == 3
    row = _assert_done_matches_the_one_assistant_row(engine, frames)
    assert row["text"] == "Once upon"


def test_an_inline_think_block_inside_one_piece_passes_untouched__S035_004_DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """035 DoD-2 — a piece carrying a whole `<think>` block is one token, verbatim, and the row
    keeps it (the stored text is exactly what streamed)."""
    factory = FakeFactory(FakeChatClient([Text("<think>x</think>Hi")]))

    frames = _run(engine, generator, factory)

    assert _tokens(frames) == ["<think>x</think>Hi"]
    row = _assert_done_matches_the_one_assistant_row(engine, frames)
    assert row["text"] == "<think>x</think>Hi"


# =========================================================================================
# 035 DoD-3: an invoked tool → tool_start, tool_result, a tool row, then the final text
# =========================================================================================

MEMO_OUTCOME = ToolOutcome(content="Memo: the inn is called The Gilded Goose.", summary="1 memo found")


def test_an_invoked_tool_streams_start_then_result_then_the_final_text__S035_004_DoD3(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """035 DoD-3 / UC-051 / UC-053 — the client invokes `memo_search`: `tool_start` (call `call_1`,
    args `{"query":"inn"}`), `tool_result` (call `call_1`, the tool's summary), then the final
    text's tokens and `done`; the assistant row holds only the text."""
    fake = RecordingTool("memo_search", MEMO_OUTCOME)
    client = FakeChatClient([Call("memo_search", '{"query":"inn"}'), Text("We stay at "), Text("the Goose.")])

    frames = _run(engine, generator, FakeFactory(client), _registry(fake))

    assert len(frames) == 5
    start, result = frames[0], frames[1]
    assert isinstance(start, ToolStartFrame)
    assert start.tool == "memo_search"
    assert start.call_id == "call_1"
    assert dict(start.args) == {"query": "inn"}
    assert result == ToolResultFrame(tool="memo_search", call_id="call_1", summary="1 memo found")
    assert frames[2:4] == [TokenFrame(text="We stay at "), TokenFrame(text="the Goose.")]
    row = _assert_done_matches_the_one_assistant_row(engine, frames)
    assert row["text"] == "We stay at the Goose."
    assert fake.arguments == [{"query": "inn"}]


def test_an_invoked_tool_persists_one_tool_row_and_returns_its_content__S035_004_DoD3(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """035 DoD-3 — the seam persisted the call: exactly one tool row (`memo_search`, in the
    session, before the assistant row) and one assistant row; the text the runner returned to the
    model is the tool's content."""
    fake = RecordingTool("memo_search", MEMO_OUTCOME)
    client = FakeChatClient([Call("memo_search", '{"query":"inn"}'), Text("We stay at the Goose.")])

    _run(engine, generator, FakeFactory(client), _registry(fake))

    tool_rows = _rows(engine, "tool")
    assistant_rows = _rows(engine, "assistant")
    assert len(tool_rows) == 1
    assert len(assistant_rows) == 1
    assert tool_rows[0]["tool_name"] == "memo_search"
    assert tool_rows[0]["session_id"] == SESSION_A
    assert tool_rows[0]["user_id"] == USER_A
    assert tool_rows[0]["id"] < assistant_rows[0]["id"]
    assert client.tool_outputs == [MEMO_OUTCOME.content]


def test_thirty_tool_calls_in_one_exchange_each_carry_their_call_id__S021_005_DoD7__S035_004_DoD3(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """021 DoD-7 (no cap) / 035 DoD-3 — thirty calls in one exchange, then an answer: thirty
    `tool_start` / `tool_result` pairs, each pair carrying its own `call_<n>`, thirty tool rows,
    then the tokens and `done`."""
    fake = RecordingTool("memo_search", MEMO_OUTCOME)
    script: list[Step] = [Call("memo_search", f'{{"query":"q{n}"}}') for n in range(1, 31)]
    script += [Text("Finally, "), Text("an answer.")]
    client = FakeChatClient(script)

    frames = _run(engine, generator, FakeFactory(client), _registry(fake))

    tool_frames = frames[:60]
    for n in range(1, 31):
        start, result = tool_frames[2 * (n - 1)], tool_frames[2 * (n - 1) + 1]
        assert isinstance(start, ToolStartFrame)
        assert start.call_id == f"call_{n}"
        assert dict(start.args) == {"query": f"q{n}"}
        assert result == ToolResultFrame(tool="memo_search", call_id=f"call_{n}", summary=MEMO_OUTCOME.summary)
    assert frames[60:62] == [TokenFrame(text="Finally, "), TokenFrame(text="an answer.")]
    assert len(frames) == 63
    row = _assert_done_matches_the_one_assistant_row(engine, frames)
    assert row["text"] == "Finally, an answer."
    assert len(_rows(engine, "tool")) == 30


# =========================================================================================
# 035 DoD-4: a tool whose run fails is a failed result; the exchange continues
# =========================================================================================


def test_a_failing_tool_gives_tool_fail_the_fixed_text_and_still_done__S021_005_DoD6__S035_004_DoD4(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """035 DoD-4 / 021 DoD-6 / US-066.AC-1 / UC-051 / UC-053 — `tool_start`, then `tool_fail` with
    code `tool_failed` for `call_1`, then the final text and `done`; the model-facing output is
    the seam's fixed failed text."""
    fake = RaisingTool("memo_search")
    client = FakeChatClient(
        [Call("memo_search", '{"query":"inn"}'), Text("Without notes: "), Text("the Goose.")]
    )

    frames = _run(engine, generator, FakeFactory(client), _registry(fake))

    assert isinstance(frames[0], ToolStartFrame)
    assert frames[0].call_id == "call_1"
    assert frames[1] == ToolFailFrame(tool="memo_search", call_id="call_1", code=FAILED_CODE)
    assert frames[2:4] == [TokenFrame(text="Without notes: "), TokenFrame(text="the Goose.")]
    assert len(frames) == 5
    row = _assert_done_matches_the_one_assistant_row(engine, frames)
    assert row["text"] == "Without notes: the Goose."
    assert client.tool_outputs == [FAILED_CONTENT]


# =========================================================================================
# 035 DoD-5: dispatch itself raising is caught by the runner
# =========================================================================================


async def _broken_dispatch(*args: Any, **kwargs: Any) -> Any:
    """A seam `dispatch` that raises a plain exception before doing anything (DoD-5)."""
    raise RuntimeError("dispatch broke")


def test_a_raising_dispatch_gives_tool_fail_and_the_fixed_text_and_still_done__S035_004_DoD5(
    engine: Engine, generator: SnowflakeGenerator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """035 DoD-5 / `DEC-arch-llm-client-library-7` — the seam's `dispatch` raises a non-cancellation
    exception: the runner emits `tool_start` then a `tool_fail` (`tool_failed`) for `call_1`,
    returns the seam's fixed failed text, and the exchange still reaches `done`.

    `dispatch` is replaced at every name it is reachable by (the compose module, the tools package
    and the seam module), so the replacement holds whichever spelling the source uses.
    """
    monkeypatch.setattr("app.services.compose.dispatch", _broken_dispatch, raising=False)
    monkeypatch.setattr("app.services.tools.dispatch", _broken_dispatch)
    monkeypatch.setattr("app.services.tools.seam.dispatch", _broken_dispatch)
    fake = RecordingTool("memo_search", MEMO_OUTCOME)
    client = FakeChatClient([Call("memo_search", '{"query":"inn"}'), Text("Carrying on.")])

    frames = _run(engine, generator, FakeFactory(client), _registry(fake))

    assert len(frames) == 4
    assert isinstance(frames[0], ToolStartFrame)
    assert frames[0].tool == "memo_search"
    assert frames[0].call_id == "call_1"
    assert frames[1] == ToolFailFrame(tool="memo_search", call_id="call_1", code=FAILED_CODE)
    assert frames[2] == TokenFrame(text="Carrying on.")
    row = _assert_done_matches_the_one_assistant_row(engine, frames)
    assert row["text"] == "Carrying on."
    assert client.tool_outputs == [FAILED_CONTENT]


# =========================================================================================
# 035 DoD-6: compose receives the offered declarations, in the fixed order
# =========================================================================================


def test_all_three_offered_tools_reach_compose_in_the_fixed_order__S035_004_DoD6(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """035 DoD-6 / FEAT-014 / FEAT-015 / FEAT-016 — all three tools registered (in reverse order)
    and switched on: `compose` receives exactly the `memo_search`, `session_search`, `web_search`
    declarations, in that order."""
    registry = _registry(RecordingTool("web_search"), RecordingTool("session_search"), RecordingTool("memo_search"))
    client = FakeChatClient([Text("Hi")])

    _run(engine, generator, FakeFactory(client), registry)

    assert len(client.calls) == 1
    assert client.calls[0].declarations == [dict(MEMO_SEARCH), dict(SESSION_SEARCH), dict(WEB_SEARCH)]


def test_only_switched_on_registered_tools_are_offered__S035_004_DoD6(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """035 DoD-6 — with `session_search` switched off, `compose` receives only the other two
    declarations, still in the fixed order."""
    _set_switches(engine, memo=True, session=False, web=True)
    registry = _registry(RecordingTool("web_search"), RecordingTool("session_search"), RecordingTool("memo_search"))
    client = FakeChatClient([Text("Hi")])

    _run(engine, generator, FakeFactory(client), registry)

    assert client.calls[0].declarations == [dict(MEMO_SEARCH), dict(WEB_SEARCH)]


@pytest.mark.parametrize("case", ["empty-registry", "every-switch-off"])
def test_no_offered_tool_gives_compose_an_empty_declaration_list__S035_004_DoD6(
    engine: Engine, generator: SnowflakeGenerator, case: str
) -> None:
    """035 DoD-6 — with no tool offered (nothing registered, or everything switched off), `compose`
    is still called, with an empty declaration list, and the exchange reaches `done`."""
    if case == "empty-registry":
        registry: dict[str, Tool] = {}
    else:
        _set_switches(engine, memo=False, session=False, web=False)
        registry = _registry(
            RecordingTool("memo_search"), RecordingTool("session_search"), RecordingTool("web_search")
        )
    client = FakeChatClient([Text("Hi")])

    frames = _run(engine, generator, FakeFactory(client), registry)

    assert len(client.calls) == 1
    assert client.calls[0].declarations == []
    assert isinstance(frames[-1], DoneFrame)


# Amended by 026 step 002, then by 027 step 003: the production registry holds both tools.
def test_the_production_registry_sends_both_registered_declarations__S021_005_DoD13__S035_004_DoD6(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """021 DoD-13 / 035 DoD-6 — all switches on, the real registry → `compose` gets exactly the
    `memo_search` and `session_search` declarations, in the fixed order."""
    client = FakeChatClient([Text("Hi")])

    _run(engine, generator, FakeFactory(client), PRODUCTION_TOOL_REGISTRY)

    assert len(client.calls) == 1
    assert client.calls[0].declarations == [dict(MEMO_SEARCH), dict(SESSION_SEARCH)]


# =========================================================================================
# 035 DoD-7: the stream raising llm_unreachable after some text
# =========================================================================================


def test_a_provider_failure_after_a_token_propagates_and_writes_no_row__S021_005_DoD11__S035_004_DoD7(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """035 DoD-7 / 021 DoD-11 / US-044 — token `Par`, then the stream raises `llm_unreachable`: the
    source raises it on (the harness turns it into the `error` frame and keeps the partial), and
    the source itself writes no assistant row and yields no `done`."""
    client = FakeChatClient([Text("Par"), LlmUnreachableError("Provider timed out", {"reason": "unreachable"})])

    frames, error = _run_until_error(engine, generator, FakeFactory(client), LlmUnreachableError)

    assert frames == [TokenFrame(text="Par")]
    assert isinstance(error, LlmUnreachableError)
    assert error.code == "llm_unreachable"
    assert not any(isinstance(frame, DoneFrame) for frame in frames)
    assert _rows(engine, "assistant") == []


# =========================================================================================
# 035 DoD-8: closing the source closes the client's compose stream
# =========================================================================================


def test_closing_the_source_after_a_token_closes_the_compose_stream__S021_005_DoD12__S035_004_DoD8(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """035 DoD-8 / 021 DoD-12 / US-132.AC-1 — `aclose()` while suspended after a token: the client's
    compose stream was closed before `aclose()` returned (left early, not played out), and the
    source writes no assistant row."""
    client = FakeChatClient([Text("Par"), Text("tial"), Text(" answer")])
    factory = FakeFactory(client)

    async def scenario() -> tuple[Any, bool, bool]:
        source = _source(engine, generator, factory, PRODUCTION_TOOL_REGISTRY, None)
        first = await source.__anext__()
        await source.aclose()
        call = client.calls[0]
        return first, call.finalized, call.exhausted

    first, finalized, exhausted = asyncio.run(asyncio.wait_for(scenario(), timeout=RUN_TIMEOUT_SECONDS))

    assert first == TokenFrame(text="Par")
    assert len(client.calls) == 1
    assert finalized is True
    assert exhausted is False
    assert _rows(engine, "assistant") == []


def test_a_stop_while_a_tool_runs_closes_compose_writes_no_tool_row_and_keeps_the_text__S035_004_DoD8(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """035 DoD-8 / US-132.AC-1 / US-133.AC-1 — the source runs under the SSE harness with the
    own-connection persister, as the route wires it. Two tokens stream, then the client invokes a
    tool that never finishes; while it runs, the consumer is cancelled (the stop). The exchange
    ends: the client's compose stream was closed, the stop reached the tool, no tool row exists
    and no tool frame was streamed, and the text streamed before the stop is an ordinary zone row
    (assistant, unsettled, unrelated)."""
    tool = BlockingTool("memo_search")
    client = FakeChatClient([Text("Par"), Text("tial"), Call("memo_search", '{"query":"inn"}'), Text("never")])
    factory = FakeFactory(client)

    async def scenario() -> tuple[list[str], bool]:
        chunks: list[str] = []
        source = _source(engine, generator, factory, _registry(tool), None)
        persist = own_connection_persister(engine, generator, USER_A, SESSION_A)

        async def consume() -> None:
            async for chunk in frame_stream(NeverDisconnected(), source, persist):
                chunks.append(chunk)

        task = asyncio.create_task(consume())
        await asyncio.wait_for(tool.started.wait(), RUN_TIMEOUT_SECONDS)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=RUN_TIMEOUT_SECONDS)
        assert task in done, "the cancelled consumer did not finish"
        return chunks, task.cancelled()

    chunks, cancelled = asyncio.run(asyncio.wait_for(scenario(), timeout=RUN_TIMEOUT_SECONDS * 2))

    assert cancelled is True
    assert len(chunks) == 2
    assert all('"event":"token"' in chunk for chunk in chunks)
    assert len(client.calls) == 1
    assert client.calls[0].finalized is True
    assert client.calls[0].exhausted is False
    assert tool.cancelled is True
    assert client.tool_outputs == []
    assert _rows(engine, "tool") == []
    assistant_rows = _rows(engine, "assistant")
    assert len(assistant_rows) == 1
    assert assistant_rows[0]["text"] == "Partial"
    assert assistant_rows[0]["session_id"] == SESSION_A
    assert assistant_rows[0]["settled_at"] is None
    assert assistant_rows[0]["related_to"] is None


# =========================================================================================
# 035 DoD-9 / 021 DoD-10: model-resolution refusals propagate after accepted
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
def test_a_failed_model_check_raises_after_accepted_and_calls_no_factory__S021_005_DoD10__S035_004_DoD9(
    engine: Engine,
    generator: SnowflakeGenerator,
    arrange: Any,
    expected: type[BaseException],
    accepted_id: int | None,
) -> None:
    """035 DoD-9 / 021 DoD-10 / US-107 / US-144 — `accepted` (when given), then the model-check
    error propagates (the harness frames it); the factory is never called; no assistant row."""
    arrange(engine)
    client = FakeChatClient([Text("never")])
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
# 035 DoD-14: the shared privacy-audit chat fakes drive the source in the new shape
# =========================================================================================


def test_the_shared_chat_fake_drives_a_tool_exchange_through_the_source__S035_004_DoD14(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """035 DoD-14 / FEAT-019 / US-085 — the moved `FakeChatClientFactory` of
    `tests/privacy_audit_support.py`, scripted with `tool_call_round` (a caller-chosen call id) and
    `text_round`, drives one exchange: `tool_start` / `tool_result` with that id, the text token,
    `done`; it recorded the four factory arguments and the offered declaration."""
    fake = RecordingTool("memo_search", MEMO_OUTCOME)
    factory = FakeChatClientFactory()
    factory.script(
        tool_call_round(name="memo_search", arguments='{"query":"inn"}', call_id="audit-call"),
        text_round("Noted."),
    )

    frames = _run(engine, generator, factory, _registry(fake))

    assert isinstance(frames[0], ToolStartFrame)
    assert frames[0].call_id == "audit-call"
    assert frames[1] == ToolResultFrame(tool="memo_search", call_id="audit-call", summary=MEMO_OUTCOME.summary)
    assert frames[2] == TokenFrame(text="Noted.")
    row = _assert_done_matches_the_one_assistant_row(engine, frames)
    assert row["text"] == "Noted."
    assert factory.calls == [(SERVER_KIND, BASE_URL, None, REQUEST_TIMEOUT)]
    assert [call.tools for call in factory.chat_calls] == [(dict(MEMO_SEARCH),)]
    assert len(_rows(engine, "tool")) == 1


def test_the_shared_chat_fake_mints_call_1_when_no_id_is_scripted__S035_004_DoD14(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """035 DoD-14 — `script_tool_call` without a call id behaves as the gateway does: the call is
    `call_1`, and `then_text` follows it."""
    fake = RecordingTool("memo_search", MEMO_OUTCOME)
    factory = FakeChatClientFactory()
    factory.script_tool_call(name="memo_search", arguments='{"query":"inn"}', then_text="After.")

    frames = _run(engine, generator, factory, _registry(fake))

    assert [frame.call_id for frame in frames if isinstance(frame, (ToolStartFrame, ToolResultFrame))] == [
        "call_1",
        "call_1",
    ]
    assert _tokens(frames) == ["After."]


def test_the_shared_chat_fake_failure_script_raises_from_the_stream__S035_004_DoD14(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """035 DoD-14 — `failure_round` / `script_failure` raise the caller's error from inside the
    compose stream, after the text scripted before it."""
    scripted = LlmUnreachableError("audit failure")
    factory = FakeChatClientFactory()
    factory.script(text_round("Par"), failure_round(scripted))

    frames, error = _run_until_error(engine, generator, factory, LlmUnreachableError)

    assert frames == [TokenFrame(text="Par")]
    assert error is scripted


# =========================================================================================
# 035 step 006: model-side rejections (DoD-9..DoD-13)
# =========================================================================================

#: The seam's persisted failed-row text (021 literals table; data-model.md `messages`).
FAILED_ROW_TEXT = "The tool failed."

#: One rejection per gateway-owned kind (DEC-035-17): (kind, the model's name, its argument text).
#: Names and argument texts are what a model would send for that mistake; the source must carry
#: them verbatim, so the not-offered text has irregular spacing a re-serialisation would lose.
REJECTIONS = [
    pytest.param("not_offered", "ghost_tool", '{ "query" :  "inn" }', id="not-offered"),
    pytest.param("bad_arguments", "memo_search", '{"query": "inn"', id="bad-arguments"),
    pytest.param("unknown_argument", "memo_search", '{"query":"inn","undeclared":1}', id="unknown-argument"),
]


@pytest.fixture
def dispatch_calls(monkeypatch: pytest.MonkeyPatch) -> list[ToolCall]:
    """Every `ToolCall` handed to the seam's `dispatch`, which still runs as normal.

    It is wrapped at every name it is reachable by (as in the 035 step 004 DoD-5 test), so a
    rejection that reached `dispatch` by any spelling is seen (DoD-9 says it never does).
    """
    from app.services.tools import seam

    original = seam.dispatch
    seen: list[ToolCall] = []

    async def recording_dispatch(call: ToolCall, *args: Any, **kwargs: Any) -> Any:
        seen.append(call)
        return await original(call, *args, **kwargs)

    monkeypatch.setattr("app.services.compose.dispatch", recording_dispatch, raising=False)
    monkeypatch.setattr("app.services.tools.dispatch", recording_dispatch)
    monkeypatch.setattr("app.services.tools.seam.dispatch", recording_dispatch)
    return seen


@contextmanager
def captured_log_records() -> Iterator[list[str]]:
    """Every loguru record (all levels) logged while the block runs, one string per record:
    the message followed by any bound `extra` fields."""
    records: list[str] = []
    sink_id = logger.add(lambda message: records.append(str(message)), level=0, format="{message} {extra}")
    try:
        yield records
    finally:
        logger.remove(sink_id)


def _tool_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = json.loads(row["tool_payload"])
    assert isinstance(payload, dict)
    return payload


# --- DoD-9: tool_start then tool_fail, in stream order, no dispatch, then done --------------


@pytest.mark.parametrize(("kind", "name", "arguments"), REJECTIONS)
def test_a_rejection_streams_tool_start_then_tool_fail_in_place_and_reaches_done__S035_006_DoD9(
    engine: Engine, generator: SnowflakeGenerator, dispatch_calls: list[ToolCall], kind: str, name: str, arguments: str
) -> None:
    """S035 006 DoD-9 / US-066.AC-1 / UC-051 / UC-053 — text, a rejection, text: token, `tool_start`
    and `tool_fail` (`tool_failed`) both for `call_1` with the model's name, token, `done`; the
    assistant row is the joined text; `dispatch` is never called and the tool never runs."""
    tool = RecordingTool("memo_search", MEMO_OUTCOME)
    client = FakeChatClient([Text("Before "), Reject(name, arguments, kind), Text("after.")])

    frames = _run(engine, generator, FakeFactory(client), _registry(tool))

    assert len(frames) == 5
    assert frames[0] == TokenFrame(text="Before ")
    start = frames[1]
    assert isinstance(start, ToolStartFrame)
    assert (start.tool, start.call_id) == (name, "call_1")
    assert frames[2] == ToolFailFrame(tool=name, call_id="call_1", code=FAILED_CODE)
    assert frames[3] == TokenFrame(text="after.")
    row = _assert_done_matches_the_one_assistant_row(engine, frames)
    assert row["text"] == "Before after."
    assert dispatch_calls == []
    assert tool.arguments == []
    assert client.tool_outputs == []


def test_a_rejection_with_object_arguments_starts_with_those_arguments__S035_006_DoD9(
    engine: Engine, generator: SnowflakeGenerator, dispatch_calls: list[ToolCall]
) -> None:
    """S035 006 DoD-9 — an unoffered call whose argument text is a JSON object: its `tool_start`
    shows that object, as any `tool_start` for the same argument text does (035 step 004 DoD-3)."""
    client = FakeChatClient([Reject("ghost_tool", '{"query":"inn"}', "not_offered"), Text("On.")])

    frames = _run(engine, generator, FakeFactory(client), _registry(RecordingTool("memo_search")))

    start = frames[0]
    assert isinstance(start, ToolStartFrame)
    assert dict(start.args) == {"query": "inn"}
    assert frames[1] == ToolFailFrame(tool="ghost_tool", call_id="call_1", code=FAILED_CODE)


def test_a_rejection_with_an_empty_name_keeps_the_name_empty__S035_006_DoD9(
    engine: Engine, generator: SnowflakeGenerator, dispatch_calls: list[ToolCall]
) -> None:
    """S035 006 DoD-9 — a call with an empty tool name: `tool_start` and `tool_fail` carry `""`."""
    client = FakeChatClient([Reject("", '{"query":"inn"}', "not_offered"), Text("On.")])

    frames = _run(engine, generator, FakeFactory(client), _registry(RecordingTool("memo_search")))

    start = frames[0]
    assert isinstance(start, ToolStartFrame)
    assert (start.tool, start.call_id) == ("", "call_1")
    assert frames[1] == ToolFailFrame(tool="", call_id="call_1", code=FAILED_CODE)
    assert frames[2] == TokenFrame(text="On.")
    assert isinstance(frames[3], DoneFrame)
    assert dispatch_calls == []


def test_rejections_and_wrapper_calls_keep_their_ids_and_order__S035_006_DoD9(
    engine: Engine, generator: SnowflakeGenerator, dispatch_calls: list[ToolCall]
) -> None:
    """S035 006 DoD-9 — a wrapper call, a rejection, a wrapper call: `call_1` start/result,
    `call_2` start/fail, `call_3` start/result, the text, `done`; only `call_1` and `call_3` were
    dispatched."""
    tool = RecordingTool("memo_search", MEMO_OUTCOME)
    client = FakeChatClient(
        [
            Call("memo_search", '{"query":"a"}'),
            Reject("ghost_tool", '{"query":"b"}', "not_offered"),
            Call("memo_search", '{"query":"c"}'),
            Text("Done looking."),
        ]
    )

    frames = _run(engine, generator, FakeFactory(client), _registry(tool))

    assert [type(frame) for frame in frames] == [
        ToolStartFrame,
        ToolResultFrame,
        ToolStartFrame,
        ToolFailFrame,
        ToolStartFrame,
        ToolResultFrame,
        TokenFrame,
        DoneFrame,
    ]
    assert [(frames[i].tool, frames[i].call_id) for i in (0, 1, 2, 3, 4, 5)] == [
        ("memo_search", "call_1"),
        ("memo_search", "call_1"),
        ("ghost_tool", "call_2"),
        ("ghost_tool", "call_2"),
        ("memo_search", "call_3"),
        ("memo_search", "call_3"),
    ]
    assert frames[3] == ToolFailFrame(tool="ghost_tool", call_id="call_2", code=FAILED_CODE)
    assert [call.call_id for call in dispatch_calls] == ["call_1", "call_3"]
    assert tool.arguments == [{"query": "a"}, {"query": "c"}]
    row = _assert_done_matches_the_one_assistant_row(engine, frames)
    assert row["text"] == "Done looking."


# --- DoD-10: one failed tool row per rejection, before the assistant row --------------------


@pytest.mark.parametrize(("kind", "name", "arguments"), REJECTIONS)
def test_a_rejection_writes_one_failed_tool_row_before_the_assistant_row__S035_006_DoD10(
    engine: Engine, generator: SnowflakeGenerator, kind: str, name: str, arguments: str
) -> None:
    """S035 006 DoD-10 / data-model.md `messages` tool columns — one `role='tool'` current-zone row:
    text `The tool failed.`, the model's name, payload `call_id` `call_1`, `arguments` the model's
    text verbatim, status `failed`, code `tool_failed`; it precedes the assistant row, and the zone
    read shows it `failed`."""
    client = FakeChatClient([Text("Before "), Reject(name, arguments, kind), Text("after.")])

    _run(engine, generator, FakeFactory(client), _registry(RecordingTool("memo_search")))

    tool_rows = _rows(engine, "tool")
    assistant_rows = _rows(engine, "assistant")
    assert len(tool_rows) == 1
    assert len(assistant_rows) == 1
    row = tool_rows[0]
    assert row["text"] == FAILED_ROW_TEXT
    assert row["tool_name"] == name
    assert row["session_id"] == SESSION_A
    assert row["user_id"] == USER_A
    assert row["settled_at"] is None
    assert row["related_to"] is None
    assert row["id"] < assistant_rows[0]["id"]
    payload = _tool_payload(row)
    assert payload["call_id"] == "call_1"
    assert payload["arguments"] == arguments
    assert payload["status"] == "failed"
    assert payload["code"] == FAILED_CODE
    with engine.connect() as connection:
        zone = list_zone(connection, USER_A, SESSION_A)
    zone_tool_rows = [message for message in zone if message.role == "tool"]
    assert [message.id for message in zone_tool_rows] == [row["id"]]
    assert zone_tool_rows[0].tool_status == "failed"
    assert zone_tool_rows[0].tool_name == name


def test_a_rejection_with_an_empty_name_writes_an_empty_tool_name__S035_006_DoD10(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """S035 006 DoD-10 — the row's `tool_name` is the model's name verbatim, `""` kept."""
    client = FakeChatClient([Reject("", "", "not_offered"), Text("On.")])

    _run(engine, generator, FakeFactory(client), _registry(RecordingTool("memo_search")))

    (row,) = _rows(engine, "tool")
    assert row["tool_name"] == ""
    assert row["text"] == FAILED_ROW_TEXT
    payload = _tool_payload(row)
    assert payload["call_id"] == "call_1"
    assert payload["arguments"] == ""
    assert payload["status"] == "failed"
    assert payload["code"] == FAILED_CODE


def test_each_rejection_writes_its_own_row_with_its_own_id__S035_006_DoD10(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """S035 006 DoD-10 — two rejections write two failed rows, `call_1` then `call_2`, both before
    the assistant row."""
    client = FakeChatClient(
        [
            Reject("ghost_tool", '{"query":"a"}', "not_offered"),
            Reject("memo_search", "[1, 2]", "bad_arguments"),
            Text("On."),
        ]
    )

    _run(engine, generator, FakeFactory(client), _registry(RecordingTool("memo_search")))

    tool_rows = _rows(engine, "tool")
    (assistant_row,) = _rows(engine, "assistant")
    assert [_tool_payload(row)["call_id"] for row in tool_rows] == ["call_1", "call_2"]
    assert [row["tool_name"] for row in tool_rows] == ["ghost_tool", "memo_search"]
    assert [_tool_payload(row)["arguments"] for row in tool_rows] == ['{"query":"a"}', "[1, 2]"]
    assert all(row["id"] < assistant_row["id"] for row in tool_rows)


# --- DoD-11: a stop between tool_start and tool_fail writes no row --------------------------


def test_closing_the_source_at_a_rejections_tool_start_writes_no_tool_row__S035_006_DoD11(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """S035 006 DoD-11 / US-133.AC-1 — `aclose()` while the source is suspended at a rejection's
    `tool_start`: no `tool_fail` was produced and no tool row exists."""
    client = FakeChatClient([Text("Par"), Reject("ghost_tool", '{"query":"inn"}', "not_offered"), Text("never")])
    factory = FakeFactory(client)

    async def scenario() -> list[Any]:
        source = _source(engine, generator, factory, _registry(RecordingTool("memo_search")), None)
        seen = [await source.__anext__(), await source.__anext__()]
        await source.aclose()
        return seen

    seen = asyncio.run(asyncio.wait_for(scenario(), timeout=RUN_TIMEOUT_SECONDS))

    assert seen[0] == TokenFrame(text="Par")
    assert isinstance(seen[1], ToolStartFrame)
    assert seen[1].call_id == "call_1"
    assert _rows(engine, "tool") == []


def test_a_stop_at_a_rejections_tool_start_keeps_the_text_and_writes_no_tool_row__S035_006_DoD11(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """S035 006 DoD-11 / US-133.AC-1 / US-132.AC-1 — under the SSE harness with the own-connection
    persister, the stream is closed (the stop, as a server closes it on disconnect) once the
    rejection's `tool_start` chunk arrived and before its `tool_fail`: no tool row exists, and the
    text streamed before the stop is an ordinary unsettled zone assistant row."""
    client = FakeChatClient(
        [Text("Par"), Text("tial"), Reject("ghost_tool", '{"query":"inn"}', "not_offered"), Text("never")]
    )
    factory = FakeFactory(client)

    async def scenario() -> list[str]:
        chunks: list[str] = []
        source = _source(engine, generator, factory, _registry(RecordingTool("memo_search")), None)
        persist = own_connection_persister(engine, generator, USER_A, SESSION_A)
        stream = frame_stream(NeverDisconnected(), source, persist)
        # Pull chunk by chunk; nothing is pulled after tool_start, so the source stays suspended
        # at that frame until the stream is closed.
        while not chunks or '"event":"tool_start"' not in chunks[-1]:
            chunks.append(await stream.__anext__())
        await stream.aclose()
        return chunks

    chunks = asyncio.run(asyncio.wait_for(scenario(), timeout=RUN_TIMEOUT_SECONDS))

    assert len(chunks) == 3
    assert '"event":"tool_start"' in chunks[2]
    assert not any('"event":"tool_fail"' in chunk for chunk in chunks)
    assert _rows(engine, "tool") == []
    assistant_rows = _rows(engine, "assistant")
    assert len(assistant_rows) == 1
    assert assistant_rows[0]["text"] == "Partial"
    assert assistant_rows[0]["settled_at"] is None
    assert assistant_rows[0]["related_to"] is None


# --- DoD-12: one log record per rejection, name and kind only ------------------------------


#: Argument text whose distinctive value must never reach a log (DEC-035-18: roleplay text).
ARGUMENT_SENTINEL = "".join(("sntl", "rejectargs", "4b8e"))


@pytest.mark.parametrize("kind", ["not_offered", "bad_arguments", "unknown_argument"])
def test_a_rejection_is_logged_once_with_its_name_and_kind_and_no_arguments__S035_006_DoD12(
    engine: Engine, generator: SnowflakeGenerator, kind: str
) -> None:
    """S035 006 DoD-12 / DEC-035-18 — exactly one log record carries both the model's tool name and
    the rejection kind; no record carries the argument text."""
    name = "".join(("ghost", "_tool", "_q7"))
    arguments = f'{{"query":"{ARGUMENT_SENTINEL}"}}'
    client = FakeChatClient([Text("Before "), Reject(name, arguments, kind), Text("after.")])

    with captured_log_records() as records:
        _run(engine, generator, FakeFactory(client), _registry(RecordingTool("memo_search")))

    carrying = [record for record in records if name in record and kind in record]
    assert len(carrying) == 1, records
    assert not any(ARGUMENT_SENTINEL in record for record in records), records


def test_two_rejections_give_two_log_records__S035_006_DoD12(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """S035 006 DoD-12 — each drained rejection produces its own record (name + kind)."""
    first, second = "".join(("ghost", "_one")), "".join(("ghost", "_two"))
    client = FakeChatClient(
        [Reject(first, "{}", "not_offered"), Reject(second, "{oops", "bad_arguments"), Text("On.")]
    )

    with captured_log_records() as records:
        _run(engine, generator, FakeFactory(client), _registry(RecordingTool("memo_search")))

    assert len([r for r in records if first in r and "not_offered" in r]) == 1, records
    assert len([r for r in records if second in r and "bad_arguments" in r]) == 1, records


# --- DoD-13: the next exchange replays the rejected row under the existing rule -------------


def _next_exchange_messages(
    engine: Engine, generator: SnowflakeGenerator, first_script: Sequence[Step]
) -> list[ChatMessage]:
    """Run one exchange with `first_script`, then a plain next exchange over the same zone;
    return the conversation the next exchange's `compose` received (the assembled context)."""
    registry = _registry(RecordingTool("memo_search"))
    _run(engine, generator, FakeFactory(FakeChatClient(first_script)), registry)
    follow_up = FakeChatClient([Text("Next.")])
    _run(engine, generator, FakeFactory(follow_up), registry)
    assert len(follow_up.calls) == 1
    return follow_up.calls[0].messages


def _assert_no_orphan_tool_message(messages: Sequence[ChatMessage]) -> None:
    """Every `tool` message directly follows an assistant message holding the call it answers."""
    for index, message in enumerate(messages):
        if message.role != "tool":
            continue
        assert index > 0
        previous = messages[index - 1]
        assert previous.role == "assistant"
        assert message.tool_call_id in [call.call_id for call in previous.tool_calls]


def test_a_not_offered_rejection_with_object_arguments_replays_as_the_pair__S035_006_DoD13(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """S035 006 DoD-13 / llm-and-streaming.md § Tool rows are replayed — the next exchange gets,
    between the zone's user message and the first assistant answer, the recorded call (`call_1`,
    the model's name and argument text) and then a `tool` message carrying the failed literal."""
    arguments = '{"query":"inn"}'
    messages = _next_exchange_messages(
        engine, generator, [Reject("ghost_tool", arguments, "not_offered"), Text("First answer.")]
    )

    roles = [message.role for message in messages]
    assert roles[0] == "system"
    user_index = next(i for i, m in enumerate(messages) if m.role == "user" and m.content == ZONE_USER_TEXT)
    call_message, tool_message, answer = messages[user_index + 1 : user_index + 4]
    assert call_message.role == "assistant"
    assert list(call_message.tool_calls) == [ToolCall(call_id="call_1", name="ghost_tool", arguments=arguments)]
    assert tool_message.role == "tool"
    assert tool_message.tool_call_id == "call_1"
    assert tool_message.content == FAILED_CONTENT
    assert answer.role == "assistant"
    assert answer.content == "First answer."
    _assert_no_orphan_tool_message(messages)


@pytest.mark.parametrize(
    ("kind", "name", "arguments"),
    [
        pytest.param("bad_arguments", "memo_search", "{not json", id="unreadable-arguments"),
        pytest.param("bad_arguments", "memo_search", "[1, 2]", id="non-object-arguments"),
        pytest.param("bad_arguments", "memo_search", "", id="missing-arguments"),
        pytest.param("not_offered", "", '{"query":"inn"}', id="empty-name"),
        pytest.param("unknown_argument", "memo_search", '{"query":"inn","undeclared":1}', id="unknown-argument"),
    ],
)
def test_any_rejected_row_replays_as_the_pair_or_is_skipped_never_an_orphan__S035_006_DoD13(
    engine: Engine, generator: SnowflakeGenerator, kind: str, name: str, arguments: str
) -> None:
    """S035 006 DoD-13 — under the existing replay rule a rejected row is either the recorded call
    followed by a `tool` message with the failed literal, or skipped entirely; there is never a
    `tool` message without its matching call."""
    messages = _next_exchange_messages(engine, generator, [Reject(name, arguments, kind), Text("First answer.")])

    _assert_no_orphan_tool_message(messages)
    calls = [
        (index, call)
        for index, message in enumerate(messages)
        for call in message.tool_calls
        if call.call_id == "call_1"
    ]
    answers = [message for message in messages if message.role == "tool" and message.tool_call_id == "call_1"]
    if calls:
        ((index, call),) = calls
        assert call == ToolCall(call_id="call_1", name=name, arguments=arguments)
        assert answers == [messages[index + 1]]
        assert answers[0].content == FAILED_CONTENT
    else:
        assert answers == []
    assert [m.content for m in messages if m.role == "assistant" and not m.tool_calls] == ["First answer."]


# =========================================================================================
# 021 DoD-14 / 035: the compose module's imports
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
    """021 DoD-14 / D15 — `compose.py` imports no `fastapi`."""
    offenders = [
        module
        for module in _compose_imports()
        if module == "fastapi" or module.startswith("fastapi.")
    ]
    assert offenders == []


def test_compose_imports_neither_the_old_client_nor_the_library__S035_004_DoD2() -> None:
    """035 DoD-2 (the source drains the gateway's `compose`; feature 035's context: the gateway is the only
    module that imports the library) — `compose.py` imports neither `app.services.llm.client` nor
    the `llm` package."""
    offenders = [
        module
        for module in _compose_imports()
        if module in ("app.services.llm.client", "llm") or module.startswith("llm.")
    ]
    assert offenders == []
