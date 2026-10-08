"""The compose source — the tool-calling loop 019's harness drains — and `begin_compose`.

Feature `021`, step `005` (D3, D4, D11, D15). `compose_stream` optionally yields `accepted`,
then on its own short-lived connection (closed before any provider call) resolves the model at
use time, assembles context, reads the configuration and the tool scope and opens the chat
client; then runs rounds of `chat_stream` with no cap — content and `<think>`-wrapped reasoning
become `token` frames, tool calls are dispatched through the seam — until a round with no calls,
whose exchange text is written as one assistant row before `done`. It never catches an error to
write a row (019 D4: the harness owns the partial write) and never touches a caller's connection.

`begin_compose` (step `006`, D1/D2) is the handler-side half: it commits the roleplayer's text
on the handler's connection, or — textless — checks the zone holds something to retry.
"""

from collections.abc import AsyncGenerator, Mapping
from dataclasses import dataclass, field

from sqlalchemy import Connection, Engine

from app.errors import ZoneEmptyError
from app.ids import SnowflakeGenerator
from app.services.configuration import get_session_configuration, resolve_model_for_use
from app.services.context import assemble_context
from app.services.llm.chat import THINK_CLOSE, THINK_OPEN, ChatMessage, ToolCall
from app.services.llm.frames import AcceptedFrame, DoneFrame, Frame, TokenFrame
from app.services.llm_registry import ChatClientFactory, open_chat_client
from app.services.messages import append_assistant_message, append_message, list_zone
from app.services.tools import (
    ToolRegistry,
    build_tool_scope,
    dispatch,
    offered_tools,
    tool_start_frame,
)
from app.services.tools.definitions import ToolDeclaration


@dataclass
class _PendingCall:
    """One tool call being accumulated from its fragments, by index (D11)."""

    call_id: str | None = None
    name: str | None = None
    arguments: list[str] = field(default_factory=list)


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
    """The compose exchange as frame values: `accepted`? → tokens / tool frames → `done` (D11)."""
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
    calls_seen = 0

    # No round cap, no round counter (FEAT-010, D11).
    while True:
        round_content: list[str] = []
        pending: dict[int, _PendingCall] = {}
        in_think = False
        stream = client.chat_stream(enabled_model.model_name, list(conversation), list(tools))
        try:
            async for delta in stream:
                if delta.reasoning is not None:
                    if not in_think:
                        in_think = True
                        exchange_parts.append(THINK_OPEN)
                        yield TokenFrame(text=THINK_OPEN)
                    exchange_parts.append(delta.reasoning)
                    yield TokenFrame(text=delta.reasoning)
                if delta.content is not None:
                    if in_think:
                        in_think = False
                        exchange_parts.append(THINK_CLOSE)
                        yield TokenFrame(text=THINK_CLOSE)
                    round_content.append(delta.content)
                    exchange_parts.append(delta.content)
                    yield TokenFrame(text=delta.content)
                for fragment in delta.tool_calls:
                    partial = pending.setdefault(fragment.index, _PendingCall())
                    if partial.call_id is None and fragment.call_id is not None:
                        partial.call_id = fragment.call_id
                    if partial.name is None and fragment.name is not None:
                        partial.name = fragment.name
                    if fragment.arguments is not None:
                        partial.arguments.append(fragment.arguments)
        finally:
            # Closing guarantee: a stop (`aclose` of this source) closes the provider stream now.
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                await aclose()

        if in_think:
            exchange_parts.append(THINK_CLOSE)
            yield TokenFrame(text=THINK_CLOSE)

        if not pending:
            break

        calls: list[ToolCall] = []
        for index in sorted(pending):
            accumulated = pending[index]
            calls_seen += 1
            calls.append(
                ToolCall(
                    call_id=accumulated.call_id if accumulated.call_id is not None else f"call_{calls_seen}",
                    name=accumulated.name if accumulated.name is not None else "",
                    arguments="".join(accumulated.arguments),
                )
            )
        conversation.append(
            ChatMessage(role="assistant", content="".join(round_content), tool_calls=tuple(calls))
        )
        for call in calls:
            yield tool_start_frame(call)
            result = await dispatch(call, scope, offered_names, registry, engine, generator)
            yield result.frame
            conversation.append(result.message)

    # Success only: the one assistant row, on a fresh short-lived connection, before `done` (019 D4).
    with engine.connect() as connection:
        row = append_assistant_message(connection, generator, user_id, session_id, "".join(exchange_parts))
    yield DoneFrame(message_id=row.id)
