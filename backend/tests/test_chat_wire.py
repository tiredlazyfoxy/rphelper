"""Feature 021 step 002 — tool-capable chat values and their OpenAI wire form.

Expected values come from `docs/plans/021.compose-loop-and-tools/002.chat-messages-and-replay.md`
(Interface intent, DoD-1 / DoD-2) and the feature `context.md` (D9, D10). Bindings come from
`status.md` `## Skeleton` -> Step 002:

- `ChatRole = Literal["system", "user", "assistant", "tool"]`
- `ToolCall(call_id: str, name: str, arguments: str)` (frozen)
- `ChatMessage(role, content, tool_calls: tuple[ToolCall, ...] = (), tool_call_id: str | None = None)`
- `to_wire_message(message: ChatMessage) -> dict[str, object]`

No database is needed: every input is a plain value.
"""

from __future__ import annotations

import pytest

from app.services.llm.chat import ChatMessage, ChatRole, ToolCall, to_wire_message

# --- DoD-1: ChatMessage and ToolCall values -------------------------------------------------


@pytest.mark.parametrize("role", ["system", "user", "assistant", "tool"])
def test_chat_message_constructs_with_each_of_four_roles__S021_002_DoD1(role: ChatRole) -> None:
    """DoD-1 — each of the four roles constructs; role and content hold what was given."""
    message = ChatMessage(role=role, content=f"content for {role}")
    assert message.role == role
    assert message.content == f"content for {role}"


def test_two_field_chat_message_has_no_tool_calls_and_no_tool_call_id__S021_002_DoD1() -> None:
    """DoD-1 — built from role and content only: no tool calls, no `tool_call_id`."""
    message = ChatMessage(role="user", content="hello")
    assert list(message.tool_calls) == []
    assert message.tool_call_id is None


def test_two_field_chat_messages_still_compare_equal__S021_002_DoD1() -> None:
    """DoD-1 — existing two-field construction stays valid (equal values are equal)."""
    assert ChatMessage(role="assistant", content="x") == ChatMessage(role="assistant", content="x")
    assert ChatMessage(role="assistant", content="x") != ChatMessage(role="user", content="x")


@pytest.mark.parametrize("field_name", ["role", "content", "tool_calls", "tool_call_id"])
def test_chat_message_is_immutable__S021_002_DoD1(field_name: str) -> None:
    """DoD-1 — assigning any field raises."""
    message = ChatMessage(
        role="assistant",
        content="",
        tool_calls=(ToolCall(call_id="c1", name="memo_search", arguments="{}"),),
    )
    with pytest.raises(AttributeError):
        setattr(message, field_name, "changed")


def test_chat_message_holds_tool_calls_and_tool_call_id__S021_002_DoD1() -> None:
    """DoD-1 — the two new fields hold what was given."""
    call = ToolCall(call_id="c1", name="memo_search", arguments='{"query": "inn"}')
    assistant = ChatMessage(role="assistant", content="", tool_calls=(call,))
    tool = ChatMessage(role="tool", content="Inn is the Gull", tool_call_id="c1")
    assert list(assistant.tool_calls) == [call]
    assert assistant.tool_call_id is None
    assert list(tool.tool_calls) == []
    assert tool.tool_call_id == "c1"


def test_tool_call_keeps_its_fields_verbatim__S021_002_DoD1() -> None:
    """DoD-1 / D9 — `call_id`, `name`, `arguments` verbatim; arguments stay that exact string."""
    call = ToolCall(call_id="call_abc-123", name="memo_search", arguments='{"query": "inn"}')
    assert call.call_id == "call_abc-123"
    assert call.name == "memo_search"
    assert call.arguments == '{"query": "inn"}'
    assert isinstance(call.arguments, str)


@pytest.mark.parametrize("field_name", ["call_id", "name", "arguments"])
def test_tool_call_is_immutable__S021_002_DoD1(field_name: str) -> None:
    """DoD-1 — `ToolCall` is frozen."""
    call = ToolCall(call_id="c1", name="memo_search", arguments="{}")
    with pytest.raises(AttributeError):
        setattr(call, field_name, "changed")


# --- DoD-2: the wire form ------------------------------------------------------------------


def test_system_message_wire_form__S021_002_DoD2() -> None:
    """DoD-2 — system → exactly `{"role": "system", "content": "S"}`."""
    assert to_wire_message(ChatMessage(role="system", content="S")) == {"role": "system", "content": "S"}


def test_user_message_wire_form__S021_002_DoD2() -> None:
    """DoD-2 — user → exactly `{"role": "user", "content": "U"}`."""
    assert to_wire_message(ChatMessage(role="user", content="U")) == {"role": "user", "content": "U"}


def test_assistant_without_calls_has_no_tool_calls_key__S021_002_DoD2() -> None:
    """DoD-2 — an assistant with no calls → exactly `{"role": "assistant", "content": "A"}`."""
    wire = to_wire_message(ChatMessage(role="assistant", content="A"))
    assert wire == {"role": "assistant", "content": "A"}
    assert "tool_calls" not in wire


def test_assistant_with_calls_wire_form__S021_002_DoD2() -> None:
    """DoD-2 / D10 — calls in order, each `{"id", "type": "function", "function": {name, arguments}}`."""
    message = ChatMessage(
        role="assistant",
        content="",
        tool_calls=(
            ToolCall(call_id="c1", name="memo_search", arguments='{"query":"inn"}'),
            ToolCall(call_id="c2", name="web_search", arguments="{}"),
        ),
    )
    assert to_wire_message(message) == {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "memo_search", "arguments": '{"query":"inn"}'},
            },
            {
                "id": "c2",
                "type": "function",
                "function": {"name": "web_search", "arguments": "{}"},
            },
        ],
    }


def test_tool_message_wire_form__S021_002_DoD2() -> None:
    """DoD-2 — a tool message → exactly `{"role": "tool", "tool_call_id": "c1", "content": "T"}`."""
    message = ChatMessage(role="tool", content="T", tool_call_id="c1")
    assert to_wire_message(message) == {"role": "tool", "tool_call_id": "c1", "content": "T"}
