"""SSE frame emission — the seven frame values and the one encoder that writes them.

Feature `019`, step `001` (D2). A source yields frame **values**; `encode_frame` is the one
site that turns a value into wire text `data: <json>\\n\\n`, with `event` first, compact
separators, non-ASCII left unescaped and every `message_id` rendered as a decimal string.
`error_frame` builds an `error` frame from a `DomainError`'s inner fields, never from
`to_wire()`'s wrapper.
"""

import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy import Engine

from app.errors import DomainError
from app.ids import SnowflakeGenerator
from app.services.messages import append_assistant_message

_FAILED_MESSAGE = "The reply could not be completed."
_EXHAUSTED_MESSAGE = "The reply ended before it was complete."


@dataclass(frozen=True)
class AcceptedFrame:
    """`accepted` — the roleplayer's committed message id."""

    message_id: int


@dataclass(frozen=True)
class TokenFrame:
    """`token` — one chunk of assistant text."""

    text: str


@dataclass(frozen=True)
class ToolStartFrame:
    """`tool_start` — a tool call began; `call_id` is opaque, `args` JSON-serialisable."""

    tool: str
    call_id: str
    args: Mapping[str, Any]


@dataclass(frozen=True)
class ToolResultFrame:
    """`tool_result` — a tool call finished; a summary string only, never raw content."""

    tool: str
    call_id: str
    summary: str


@dataclass(frozen=True)
class ToolFailFrame:
    """`tool_fail` — a tool call failed with `code`."""

    tool: str
    call_id: str
    code: str


@dataclass(frozen=True)
class ErrorFrame:
    """`error` — terminal; the error model's inner `code`, `message`, `detail`."""

    code: str
    message: str | None
    detail: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DoneFrame:
    """`done` — terminal; the assistant row's id."""

    message_id: int


Frame = AcceptedFrame | TokenFrame | ToolStartFrame | ToolResultFrame | ToolFailFrame | ErrorFrame | DoneFrame


def encode_frame(frame: Frame) -> str:
    """The frame's wire text: `data: ` + compact JSON (`event` first) + a blank line."""
    payload: dict[str, Any]
    if isinstance(frame, AcceptedFrame):
        payload = {"event": "accepted", "message_id": str(frame.message_id)}
    elif isinstance(frame, TokenFrame):
        payload = {"event": "token", "text": frame.text}
    elif isinstance(frame, ToolStartFrame):
        payload = {"event": "tool_start", "tool": frame.tool, "call_id": frame.call_id, "args": dict(frame.args)}
    elif isinstance(frame, ToolResultFrame):
        payload = {"event": "tool_result", "tool": frame.tool, "call_id": frame.call_id, "summary": frame.summary}
    elif isinstance(frame, ToolFailFrame):
        payload = {"event": "tool_fail", "tool": frame.tool, "call_id": frame.call_id, "code": frame.code}
    elif isinstance(frame, ErrorFrame):
        payload = {"event": "error", "code": frame.code, "message": frame.message, "detail": dict(frame.detail)}
    else:
        payload = {"event": "done", "message_id": str(frame.message_id)}
    return "data: " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n\n"


def error_frame(error: DomainError) -> ErrorFrame:
    """An `error` frame from `error`'s inner `code`, `message` and `detail` (missing → `{}`)."""
    detail = error.detail if error.detail is not None else {}
    return ErrorFrame(code=error.code, message=error.message, detail=detail)


class DisconnectProbe(Protocol):
    """The one request capability the harness uses (D3); a Starlette `Request` satisfies it."""

    async def is_disconnected(self) -> bool: ...


async def frame_stream(
    request: DisconnectProbe,
    source: AsyncIterator[Frame],
    on_partial: Callable[[str], None],
) -> AsyncGenerator[str, None]:
    """Drain `source` into wire strings: poll, encode, stop after a terminal frame (D3–D6).

    No `done` passed ⇒ `on_partial(text)` once, unless the streamed text is blank (D4);
    exception/exhaustion ⇒ a fallback `llm_unreachable` frame (D5); the `finally` closes the
    source under `asyncio.shield` and re-raises `CancelledError`/`GeneratorExit` (D6).
    """
    parts: list[str] = []
    done_passed = False
    persisted = False

    def persist() -> None:
        nonlocal persisted
        if persisted or done_passed:
            return
        persisted = True
        text = "".join(parts)
        if text.strip():
            on_partial(text)

    try:
        while True:
            fallback: ErrorFrame | None = None
            try:
                frame = await source.__anext__()
            except StopAsyncIteration:
                fallback = ErrorFrame(code="llm_unreachable", message=_EXHAUSTED_MESSAGE, detail={})
            except DomainError as error:
                fallback = error_frame(error)
            except Exception as error:
                logger.warning("frame stream source failed code=llm_unreachable exception={}", type(error).__name__)
                fallback = ErrorFrame(code="llm_unreachable", message=_FAILED_MESSAGE, detail={})
            if fallback is not None:
                persist()
                if await request.is_disconnected():
                    return
                yield encode_frame(fallback)
                return
            if await request.is_disconnected():
                return
            if isinstance(frame, TokenFrame):
                parts.append(frame.text)
            elif isinstance(frame, DoneFrame):
                done_passed = True
            yield encode_frame(frame)
            if isinstance(frame, ErrorFrame):
                persist()
                return
            if isinstance(frame, DoneFrame):
                return
    finally:
        persist()
        aclose = getattr(source, "aclose", None)
        if aclose is not None:
            with contextlib.suppress(Exception):
                await asyncio.shield(aclose())


def sse_response(
    request: DisconnectProbe,
    source: AsyncIterator[Frame],
    on_partial: Callable[[str], None],
) -> StreamingResponse:
    """A `text/event-stream` `StreamingResponse` over `frame_stream`, header `X-Accel-Buffering: no`."""
    return StreamingResponse(
        frame_stream(request, source, on_partial),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


def own_connection_persister(
    engine: Engine,
    generator: SnowflakeGenerator,
    user_id: int,
    session_id: int,
) -> Callable[[str], None]:
    """The synchronous `on_partial`: one own connection, `append_assistant_message`, log-and-swallow (D7)."""

    def persist(text: str) -> None:
        try:
            with engine.connect() as connection:
                append_assistant_message(connection, generator, user_id, session_id, text)
        except Exception as error:
            logger.warning(
                "partial reply not kept session={} exception={}", str(session_id), type(error).__name__
            )

    return persist
