"""The tool seam — scope, outcome, protocol, registry, offered tools, dispatch.

Feature `021`, step `004` (D5, D6, D7). `026` / `027` / `028` bind to this: a tool receives a
`ToolScope` it cannot forge (built only here, from an owner-scoped session read) and an open
connection it must leave with no transaction open; it returns a `ToolOutcome` or raises. Any
`Exception` from `run` is a failure; a cancellation propagates untouched and writes no row.
"""

import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Protocol

from loguru import logger
from sqlalchemy import Connection, Engine

from app.errors import ToolFailedError
from app.ids import SnowflakeGenerator
from app.services.configuration import SessionConfiguration
from app.services.llm.chat import ChatMessage, ToolCall
from app.services.llm.frames import ToolFailFrame, ToolResultFrame, ToolStartFrame
from app.services.messages import append_tool_message
from app.services.sessions import get_session
from app.services.tools.definitions import (
    MEMO_SEARCH_NAME,
    SESSION_SEARCH_NAME,
    TOOL_DECLARATIONS,
    WEB_SEARCH_NAME,
    ToolDeclaration,
)
from app.services.tools.memo_search import MemoSearchTool
from app.services.tools.session_search import SessionSearchTool

TOOL_FAILED_CONTENT: Final = "The tool failed. Continue without its result."
"""The tool message content sent to the model for a failed call."""

TOOL_FAILED_ROW_TEXT: Final = "The tool failed."
"""The persisted tool row's `text` for a failed call."""


@dataclass(frozen=True)
class ToolScope:
    """Who and where a tool call runs for — built only by `build_tool_scope`, never from the model."""

    user_id: int
    session_id: int
    character_id: int
    setup_id: int | None


@dataclass(frozen=True)
class ToolOutcome:
    """A tool's result: `content` goes to the model; `summary` goes to the frame and the row."""

    content: str
    summary: str


class Tool(Protocol):
    """One tool implementation, registered under its declared name."""

    @property
    def name(self) -> str: ...

    async def run(
        self, scope: ToolScope, connection: Connection, arguments: Mapping[str, object]
    ) -> ToolOutcome: ...


ToolRegistry = Mapping[str, Tool]
"""Name → `Tool`. Injectable; the production mapping is `PRODUCTION_TOOL_REGISTRY` below."""

PRODUCTION_TOOL_REGISTRY: Final[ToolRegistry] = MappingProxyType(
    {MEMO_SEARCH_NAME: MemoSearchTool(), SESSION_SEARCH_NAME: SessionSearchTool()}
)
"""The production registry: read-only; holds `memo_search` (`026`) and `session_search` (`027`)."""


@dataclass(frozen=True)
class DispatchResult:
    """What one dispatched call yields: the frame to emit and the tool message to append."""

    frame: ToolResultFrame | ToolFailFrame
    message: ChatMessage


def build_tool_scope(connection: Connection, user_id: int, session_id: int) -> ToolScope:
    """The caller's scope for `session_id`, via `sessions.get_session` (`SessionNotFoundError`)."""
    session = get_session(connection, user_id, session_id)
    return ToolScope(
        user_id=user_id,
        session_id=session.id,
        character_id=session.character_id,
        setup_id=session.setup_id,
    )


def _switches(configuration: SessionConfiguration) -> dict[str, bool | None]:
    """Each declared tool's resolved `tool_*` switch, by tool name."""
    return {
        MEMO_SEARCH_NAME: configuration.tool_memo_search.value,
        SESSION_SEARCH_NAME: configuration.tool_session_search.value,
        WEB_SEARCH_NAME: configuration.tool_web_search.value,
    }


_NAMED_DECLARATIONS: Final = tuple(
    zip((MEMO_SEARCH_NAME, SESSION_SEARCH_NAME, WEB_SEARCH_NAME), TOOL_DECLARATIONS, strict=True)
)
"""Each declaration paired with its name, in offered order (D5)."""


def offered_tools(configuration: SessionConfiguration, registry: ToolRegistry) -> list[ToolDeclaration]:
    """Declarations whose `tool_*` switch resolves true and whose name is registered, in order."""
    switches = _switches(configuration)
    return [
        declaration
        for name, declaration in _NAMED_DECLARATIONS
        if switches[name] is True and name in registry
    ]


def _parse_object(raw: str) -> dict[str, Any] | None:
    """`raw` parsed as a JSON object, or `None` when it does not parse or is not an object."""
    try:
        parsed = json.loads(raw)
    except (ValueError, RecursionError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def tool_start_frame(call: ToolCall) -> ToolStartFrame:
    """The `tool_start` frame for `call`; args = parsed JSON object, or `{}` otherwise."""
    parsed = _parse_object(call.arguments)
    return ToolStartFrame(tool=call.name, call_id=call.call_id, args={} if parsed is None else parsed)


def _compact(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _write_row(
    engine: Engine, generator: SnowflakeGenerator, scope: ToolScope, call: ToolCall, text: str, payload: str
) -> None:
    """Persist the tool row on a short-lived connection of its own; log-and-swallow a failure (D7)."""
    try:
        with engine.connect() as connection:
            append_tool_message(
                connection, generator, scope.user_id, scope.session_id, text, call.name, payload
            )
    except Exception as error:
        logger.warning(
            "tool row not kept session={} tool={} exception={}",
            str(scope.session_id),
            call.name,
            type(error).__name__,
        )


async def dispatch(
    call: ToolCall,
    scope: ToolScope,
    offered: Collection[str],
    registry: ToolRegistry,
    engine: Engine,
    generator: SnowflakeGenerator,
) -> DispatchResult:
    """Run one provider tool call into a frame, a tool message and a persisted tool row (D6, D7)."""
    arguments = _parse_object(call.arguments)
    tool = registry.get(call.name) if call.name in offered else None
    outcome: ToolOutcome | None = None
    failure = ToolFailedError.__name__
    if tool is not None and arguments is not None:
        # The connection closes whatever happens, a cancellation included; only an `Exception`
        # is a failure — `CancelledError` / `GeneratorExit` propagate and no row is written.
        try:
            with engine.connect() as connection:
                outcome = await tool.run(scope, connection, arguments)
        except Exception as error:
            failure = type(error).__name__
    if outcome is None:
        logger.warning("tool failed tool={} call={} exception={}", call.name, call.call_id, failure)
        frame: ToolResultFrame | ToolFailFrame = ToolFailFrame(
            tool=call.name, call_id=call.call_id, code=ToolFailedError.code
        )
        content = TOOL_FAILED_CONTENT
        row_text = TOOL_FAILED_ROW_TEXT
        payload = _compact(
            {
                "call_id": call.call_id,
                "arguments": call.arguments,
                "status": "failed",
                "code": ToolFailedError.code,
            }
        )
    else:
        frame = ToolResultFrame(tool=call.name, call_id=call.call_id, summary=outcome.summary)
        content = outcome.content
        row_text = outcome.summary
        payload = _compact(
            {"call_id": call.call_id, "arguments": call.arguments, "status": "ok", "content": outcome.content}
        )
    _write_row(engine, generator, scope, call, row_text, payload)
    return DispatchResult(
        frame=frame, message=ChatMessage(role="tool", content=content, tool_call_id=call.call_id)
    )
