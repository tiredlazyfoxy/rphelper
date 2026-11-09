"""The compose source — the exchange 019's harness drains — and `begin_compose`.

Feature `021`, step `005` (D3, D4, D11, D15); moved onto the LLM gateway by feature `035`,
step `004` (DEC-035-6, DEC-035-7). `compose_stream` optionally yields `accepted`, then on its
own short-lived connection (closed before any provider call) resolves the model at use time,
assembles context, reads the configuration and the tool scope and opens the chat client; then
drains the client's `compose` — each text piece becomes a `token` frame verbatim (`<think>`
included), each tool call runs through this module's private runner over the tool seam — and
writes the exchange text as one assistant row before `done`. Rounds, tool-call fragments and
`<think>` markers are the library's business, not this module's (DEC-arch-llm-client-library-8).
It never catches an error to write a row (019 D4: the harness owns the partial write) and never
touches a caller's connection.

`begin_compose` (step `006`, D1/D2) is the handler-side half: it commits the roleplayer's text
on the handler's connection, or — textless — checks the zone holds something to retry.
"""

from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import aclosing

from loguru import logger
from sqlalchemy import Connection, Engine

from app.errors import ToolFailedError, ZoneEmptyError
from app.ids import SnowflakeGenerator
from app.services.configuration import get_session_configuration, resolve_model_for_use
from app.services.context import assemble_context
from app.services.llm.chat import ChatMessage, ToolCall
from app.services.llm.frames import AcceptedFrame, DoneFrame, Frame, TokenFrame, ToolFailFrame
from app.services.llm.gateway import ComposeText, ComposeTools
from app.services.llm_registry import ChatClientFactory, open_chat_client
from app.services.messages import append_assistant_message, append_message, list_zone
from app.services.tools import (
    ToolRegistry,
    build_tool_scope,
    offered_tools,
)
from app.services.tools.definitions import ToolDeclaration
from app.services.tools.seam import TOOL_FAILED_CONTENT, dispatch, tool_start_frame


def _declared_name(declaration: ToolDeclaration) -> str | None:
    """The `function.name` of an OpenAI tool declaration, if present."""
    function = declaration.get("function")
    if isinstance(function, Mapping):
        name = function.get("name")
        if isinstance(name, str):
            return name
    return None


def begin_compose(
    connection: Connection,
    generator: SnowflakeGenerator,
    user_id: int,
    session_id: int,
    text: str | None,
) -> int | None:
    """The handler-side half of a compose (step `006`, D1/D2); never calls a model.

    With `text`: `append_message` (own committed transaction) and return the new row's id.
    Without: `list_zone`, raise `ZoneEmptyError` when no row's role is not `"tool"`; return
    `None`. Ownership failures raise `SessionNotFoundError` either way.
    """
    if text is not None:
        return append_message(connection, generator, user_id, session_id, text).id
    zone = list_zone(connection, user_id, session_id)
    if not any(message.role != "tool" for message in zone):
        raise ZoneEmptyError()
    return None


async def compose_stream(
    engine: Engine,
    generator: SnowflakeGenerator,
    user_id: int,
    session_id: int,
    accepted_id: int | None,
    timeout_seconds: float,
    client_factory: ChatClientFactory,
    registry: ToolRegistry,
) -> AsyncGenerator[Frame, None]:
    """The compose exchange as frame values: `accepted`? → tokens / tool frames → `done` (D11).

    Setup (model resolution, context, configuration, offered tools, tool scope, client) runs on
    one short-lived connection closed before any provider call (D3). The exchange then drains
    the client's `compose` (DEC-035-6) inside `contextlib.aclosing`, with the offered
    declarations in the fixed `memo_search`, `session_search`, `web_search` order and a private
    runner that owns every RPHelper rule about a tool call: each `ComposeText` becomes one
    `token` frame (verbatim, `<think>` included) and is accumulated; each runner-emitted frame
    (`tool_start`, `tool_result` / `tool_fail`) passes through. On success the joined token
    text is written as one assistant row on a fresh connection, then `done` carries its id.

    Raises:
        DomainError: model-resolution refusals and `secret_ref_missing` from setup; an
            `LlmUnreachableError` from the stream. The harness turns these into `error`
            frames and owns the partial write (019 D4); nothing here catches to write a row.
    """
    if accepted_id is not None:
        yield AcceptedFrame(message_id=accepted_id)

    # Setup on one short-lived connection, closed before any provider call (D3).
    with engine.connect() as connection:
        enabled_model = resolve_model_for_use(connection, user_id, session_id)
        assembled = assemble_context(connection, user_id, session_id)
        configuration = get_session_configuration(connection, user_id, session_id)
        tools = offered_tools(configuration, registry)
        scope = build_tool_scope(connection, user_id, session_id)
        client = open_chat_client(connection, enabled_model, timeout_seconds, client_factory)

    offered_names = {name for name in map(_declared_name, tools) if name is not None}
    conversation: list[ChatMessage] = [
        ChatMessage(role="system", content=assembled.system_prompt),
        *assembled.messages,
    ]
    exchange_parts: list[str] = []

    async def run_tool(call: ToolCall, emit: Callable[[Frame], None]) -> str:
        """Run one tool call for the gateway: the compose half of the tool wrapper (DEC-035-6).

        Emits `tool_start`, awaits the seam's `dispatch` (which persists the tool row and logs),
        emits its `tool_result` / `tool_fail` frame and returns the tool message's content —
        the text the library hands back to the model as the tool result.

        Any `Exception` — including one from `dispatch` itself — emits a `tool_fail`
        (`tool_failed`) frame for this call and returns the seam's fixed failed text, so the
        exchange always continues (DEC-arch-llm-client-library-7). A cancellation is a
        `BaseException` and propagates: closing the compose source mid-tool ends the exchange
        and writes no tool row (US-132.AC-1).
        """
        emit(tool_start_frame(call))
        try:
            result = await dispatch(call, scope, offered_names, registry, engine, generator)
        except Exception as error:
            # Only the exception type is logged — never its message, which may carry provider
            # or tool text (DEC-035-8); same shape as the seam's own failure line.
            logger.warning(
                "tool runner failed tool={} call={} exception={}", call.name, call.call_id, type(error).__name__
            )
            # The same frame and model-facing text `dispatch` produces for a failed call.
            emit(ToolFailFrame(tool=call.name, call_id=call.call_id, code=ToolFailedError.code))
            return TOOL_FAILED_CONTENT
        emit(result.frame)
        return result.message.content

    compose_tools: ComposeTools[Frame] = ComposeTools(declarations=tools, runner=run_tool)
    # `aclosing` is what stops model work in flight: the harness closes this generator with a
    # shielded `aclose()`, which only reaches the gateway's stream — and through it cancels the
    # library task and any running tool — when that stream is iterated inside `aclosing`
    # (DEC-035-7). Without it the inner stream would be left to the GC.
    async with aclosing(client.compose(enabled_model.model_name, conversation, compose_tools)) as stream:
        async for item in stream:
            if isinstance(item, ComposeText):
                exchange_parts.append(item.text)
                yield TokenFrame(text=item.text)
            else:
                yield item

    # Success only: the one assistant row, on a fresh short-lived connection, before `done` (019 D4).
    with engine.connect() as connection:
        row = append_assistant_message(connection, generator, user_id, session_id, "".join(exchange_parts))
    yield DoneFrame(message_id=row.id)
