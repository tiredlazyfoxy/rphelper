"""The neutral chat-message value type — what the assembler returns and the client consumes.

Feature `020`, step `001`. A sibling of `client.py` so feature `021`'s client can import the
type without importing the assembler. Imports nothing from any `app.services.` module (D9).
"""

from dataclasses import dataclass
from typing import Final, Literal

THINK_OPEN: Final = "<think>"
"""The opening tag of a think block (feature `021`, `context.md` D4)."""

THINK_CLOSE: Final = "</think>"
"""The closing tag of a think block (feature `021`, `context.md` D4)."""

ChatRole = Literal["system", "user", "assistant", "tool"]
"""The four chat roles a message can carry (feature `021` step `002` widened it from two)."""


def strip_think(text: str) -> str:
    """`text` with every think block removed per D4's strip rule — pure.

    A block runs from `THINK_OPEN` through the nearest following `THINK_CLOSE` inclusive (an
    unterminated opener runs to the end); blocks are removed left to right; the result is
    trimmed only when at least one block was removed, otherwise returned unchanged.
    """
    pieces: list[str] = []
    removed = False
    position = 0
    while True:
        start = text.find(THINK_OPEN, position)
        if start == -1:
            pieces.append(text[position:])
            break
        pieces.append(text[position:start])
        removed = True
        end = text.find(THINK_CLOSE, start + len(THINK_OPEN))
        if end == -1:
            break
        position = end + len(THINK_CLOSE)
    if not removed:
        return text
    return "".join(pieces).strip()


@dataclass(frozen=True)
class ToolCall:
    """One tool call an assistant message carries (feature `021`, D9).

    `call_id` is opaque; `arguments` is the raw JSON arguments string, verbatim — never parsed
    and re-serialised.
    """

    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ChatMessage:
    """One chat message: its role and its content, verbatim.

    `tool_calls` is non-empty only on an assistant message that calls tools; `tool_call_id`
    is set only on a `tool` message (feature `021`, D9). Two-field construction stays valid.
    """

    role: ChatRole
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


def to_wire_message(message: ChatMessage) -> dict[str, object]:
    """`message` as the OpenAI chat-completions message object — pure (feature `021`, D10).

    system / user → `{"role", "content"}`; assistant → `{"role", "content"}` plus
    `"tool_calls"` only when non-empty, each `{"id", "type": "function", "function":
    {"name", "arguments"}}` in order; tool → `{"role", "tool_call_id", "content"}`.
    """
    if message.role == "tool":
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content,
        }
    wire: dict[str, object] = {"role": message.role, "content": message.content}
    if message.role == "assistant" and message.tool_calls:
        wire["tool_calls"] = [
            {
                "id": call.call_id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in message.tool_calls
        ]
    return wire
