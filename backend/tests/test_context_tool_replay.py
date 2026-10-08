"""Feature 021 step 002 — tool-row replay and `<think>` stripping in `to_chat_messages`.

Expected values come from `docs/plans/021.compose-loop-and-tools/002.chat-messages-and-replay.md`
(DoD-3..DoD-7, DoD-10), the feature `context.md` (D4's worked examples, D7's payload shape,
D9's replay rule, the Literals table) and 020's kind-tag convention (`[my turn]` + line feed).
Bindings come from `status.md` `## Skeleton` -> Steps 001-002:

- `StreamMessage(..., tool_name: str | None = None, tool_payload: str | None = None)`
- `ToolCall(call_id, name, arguments)`; `ChatMessage(role, content, tool_calls=(), tool_call_id=None)`
- `to_chat_messages(entries, zone) -> list[ChatMessage]`

No database is needed: every input is a plain value.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from app.services import context as context_module
from app.services.context import to_chat_messages
from app.services.llm import chat as chat_module
from app.services.llm.chat import ChatMessage, ToolCall
from app.services.messages import StreamMessage

TOOL_FAILED_CONTENT = "The tool failed. Continue without its result."

_TS = "2026-10-04T00:00:00.000Z"

Shape = tuple[str, str, tuple[ToolCall, ...], str | None]


def _zone(
    row_id: int,
    text: str,
    role: str = "user",
    *,
    tool_name: str | None = None,
    tool_payload: str | None = None,
) -> StreamMessage:
    return StreamMessage(
        id=row_id,
        session_id=1,
        role=role,
        kind=None,
        text=text,
        settled_at=None,
        created_at=_TS,
        updated_at=_TS,
        tool_name=tool_name,
        tool_payload=tool_payload,
    )


def _settled(row_id: int, kind: str, text: str, role: str = "user") -> StreamMessage:
    return StreamMessage(
        id=row_id,
        session_id=1,
        role=role,
        kind=kind,
        text=text,
        settled_at=_TS,
        created_at=_TS,
        updated_at=_TS,
    )


def _ok_payload(call_id: str, arguments: str, content: str) -> str:
    return json.dumps({"call_id": call_id, "arguments": arguments, "status": "ok", "content": content})


def _failed_payload(call_id: str, arguments: str) -> str:
    return json.dumps(
        {"call_id": call_id, "arguments": arguments, "status": "failed", "code": "tool_failed"}
    )


def _tool_row(row_id: int, payload: str | None, tool_name: str | None = "memo_search") -> StreamMessage:
    return _zone(row_id, "a short tool summary", "tool", tool_name=tool_name, tool_payload=payload)


def _shape(message: ChatMessage) -> Shape:
    return (message.role, message.content, tuple(message.tool_calls), message.tool_call_id)


def _shapes(messages: Sequence[ChatMessage]) -> list[Shape]:
    return [_shape(message) for message in messages]


def _plain(role: str, content: str) -> Shape:
    return (role, content, (), None)


def _call_pair(call_id: str, name: str, arguments: str, content: str) -> list[Shape]:
    return [
        ("assistant", "", (ToolCall(call_id=call_id, name=name, arguments=arguments),), None),
        ("tool", content, (), call_id),
    ]


# --- DoD-3: an ok tool row replays as an assistant/tool pair at its id position --------------


def test_ok_tool_row_replays_as_assistant_call_then_tool_result__S021_002_DoD3() -> None:
    """DoD-3 / D9 — user; assistant "" + the one call; tool `c1` with the content; assistant."""
    arguments = '{"query": "inn"}'
    zone = [
        _zone(1, "Where do they sleep tonight?", "user"),
        _tool_row(2, _ok_payload("c1", arguments, "Inn is the Gull")),
        _zone(3, "They take a room at the Gull.", "assistant"),
    ]
    messages = to_chat_messages([], zone)
    assert _shapes(messages) == [
        _plain("user", "Where do they sleep tonight?"),
        *_call_pair("c1", "memo_search", '{"query": "inn"}', "Inn is the Gull"),
        _plain("assistant", "They take a room at the Gull."),
    ]


def test_ok_tool_row_replays_from_the_exact_spec_payload__S021_002_DoD3() -> None:
    """DoD-3 — the payload literal from the DoD, raw arguments string kept verbatim."""
    payload = '{"call_id":"c1","arguments":"{\\"query\\":\\"inn\\"}","status":"ok","content":"Inn is the Gull"}'
    zone = [_zone(1, "u", "user"), _tool_row(2, payload), _zone(3, "a", "assistant")]
    messages = to_chat_messages([], zone)
    assert _shapes(messages) == [
        _plain("user", "u"),
        *_call_pair("c1", "memo_search", '{"query":"inn"}', "Inn is the Gull"),
        _plain("assistant", "a"),
    ]
    assert isinstance(messages[1].tool_calls[0].arguments, str)


def test_replayed_call_uses_the_rows_tool_name__S021_002_DoD3() -> None:
    """DoD-3 / D9 — the call's name is the row's `tool_name`."""
    zone = [_tool_row(5, _ok_payload("call_7", "{}", "result"), tool_name="web_search")]
    assert _shapes(to_chat_messages([], zone)) == _call_pair("call_7", "web_search", "{}", "result")


# --- DoD-4: a failed tool row replays with the failed literal --------------------------------


def test_failed_tool_row_replays_with_the_failed_literal__S021_002_DoD4() -> None:
    """DoD-4 / D9 / R9 — status `failed` → tool content exactly the failed literal."""
    zone = [
        _zone(1, "Look it up.", "user"),
        _tool_row(2, _failed_payload("c9", '{"query": "storm"}')),
        _zone(3, "No luck; carrying on.", "assistant"),
    ]
    messages = to_chat_messages([], zone)
    assert _shapes(messages) == [
        _plain("user", "Look it up."),
        *_call_pair("c9", "memo_search", '{"query": "storm"}', TOOL_FAILED_CONTENT),
        _plain("assistant", "No luck; carrying on."),
    ]
    assert messages[2].content == "The tool failed. Continue without its result."


# --- DoD-5: two tool rows interleaved with settled rows --------------------------------------


def test_two_tool_rows_replay_as_separate_pairs_at_their_id_positions__S021_002_DoD5() -> None:
    """DoD-5 / D9 — one pair per tool row, each at its own id, between its neighbours."""
    entries = [
        _settled(40, "decision", "settled-40"),
        _settled(10, "partner", "settled-10"),
    ]
    zone = [
        _zone(60, "zone-60", "assistant"),
        _tool_row(50, _failed_payload("c2", "{}"), tool_name="web_search"),
        _zone(20, "zone-20", "user"),
        _tool_row(30, _ok_payload("c1", '{"query": "inn"}', "Inn is the Gull")),
    ]
    messages = to_chat_messages(entries, zone)
    assert _shapes(messages) == [
        _plain("user", "[partner]\nsettled-10"),
        _plain("user", "zone-20"),
        *_call_pair("c1", "memo_search", '{"query": "inn"}', "Inn is the Gull"),
        _plain("user", "[decision]\nsettled-40"),
        *_call_pair("c2", "web_search", "{}", TOOL_FAILED_CONTENT),
        _plain("assistant", "zone-60"),
    ]


def test_adjacent_tool_rows_are_not_grouped__S021_002_DoD5() -> None:
    """DoD-5 / D9 — two consecutive tool rows give two assistant/tool pairs, not one grouped call."""
    zone = [
        _zone(1, "u", "user"),
        _tool_row(2, _ok_payload("c1", "{}", "first")),
        _tool_row(3, _ok_payload("c2", "{}", "second"), tool_name="session_search"),
        _zone(4, "a", "assistant"),
    ]
    assert _shapes(to_chat_messages([], zone)) == [
        _plain("user", "u"),
        *_call_pair("c1", "memo_search", "{}", "first"),
        *_call_pair("c2", "session_search", "{}", "second"),
        _plain("assistant", "a"),
    ]


# --- DoD-6: unreplayable tool rows are skipped -----------------------------------------------


@pytest.mark.parametrize(
    ("payload", "tool_name"),
    [
        ("this is not json {", "memo_search"),
        (json.dumps({"arguments": "{}", "status": "ok", "content": "x"}), "memo_search"),
        (json.dumps({"call_id": "c1", "status": "ok", "content": "x"}), "memo_search"),
        (json.dumps({"call_id": "c1", "arguments": "{}", "content": "x"}), "memo_search"),
        (_ok_payload("c1", "{}", "x"), None),
    ],
    ids=["payload-not-json", "lacks-call_id", "lacks-arguments", "lacks-status", "tool_name-none"],
)
def test_unreplayable_tool_row_is_skipped__S021_002_DoD6(payload: str, tool_name: str | None) -> None:
    """DoD-6 / D9 — no message for the row; its neighbours keep their order."""
    zone = [
        _zone(1, "before", "user"),
        _tool_row(2, payload, tool_name=tool_name),
        _zone(3, "after", "assistant"),
    ]
    messages = to_chat_messages([], zone)
    assert _shapes(messages) == [_plain("user", "before"), _plain("assistant", "after")]


def test_skipped_tool_row_does_not_disturb_a_valid_one__S021_002_DoD6() -> None:
    """DoD-6 — an unreplayable row next to a valid one: only the valid one replays."""
    zone = [
        _zone(1, "before", "user"),
        _tool_row(2, "not json"),
        _tool_row(3, _ok_payload("c3", "{}", "kept")),
        _zone(4, "after", "assistant"),
    ]
    assert _shapes(to_chat_messages([], zone)) == [
        _plain("user", "before"),
        *_call_pair("c3", "memo_search", "{}", "kept"),
        _plain("assistant", "after"),
    ]


# --- DoD-7: think stripping, zone assistant rows only ------------------------------------------


def test_zone_assistant_row_is_think_stripped__S021_002_DoD7() -> None:
    """DoD-7 / D4 — `<think>plan</think>\\n\\nHello` → `Hello`."""
    messages = to_chat_messages([], [_zone(1, "<think>plan</think>\n\nHello", "assistant")])
    assert _shapes(messages) == [_plain("assistant", "Hello")]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hello", "Hello"),
        ("  Hello  ", "  Hello  "),
        ("<think>a</think>One<think>b</think> two", "One two"),
        ("Start<think>never closed", "Start"),
        ("a </think> b", "a </think> b"),
        ("<think>x\ny</think>\n((ooc))", "((ooc))"),
    ],
    ids=["no-block", "no-block-whitespace", "two-blocks", "unterminated", "stray-close", "before-ooc"],
)
def test_zone_assistant_row_follows_the_strip_rule__S021_002_DoD7(text: str, expected: str) -> None:
    """DoD-7 / D4 — the worked examples hold for a mapped zone assistant row."""
    messages = to_chat_messages([], [_zone(1, text, "assistant")])
    assert _shapes(messages) == [_plain("assistant", expected)]


def test_zone_user_row_with_think_maps_verbatim__S021_002_DoD7() -> None:
    """DoD-7 / D4 / R12 — a user row is never stripped."""
    messages = to_chat_messages([], [_zone(1, "<think>a</think> b", "user")])
    assert _shapes(messages) == [_plain("user", "<think>a</think> b")]


@pytest.mark.parametrize("role", ["user", "assistant"])
def test_settled_turn_row_with_think_maps_verbatim_after_its_tag__S021_002_DoD7(role: str) -> None:
    """DoD-7 / D4 — settled rows are never stripped: `[my turn]\\n` + the stored text verbatim."""
    stored = "Before <think>x</think> after"
    messages = to_chat_messages([_settled(1, "turn", stored, role)], [])
    assert _shapes(messages) == [_plain(role, "[my turn]\n" + stored)]


# --- DoD-10: import guards -----------------------------------------------------------------------


def _module_tree(module_file: str | None) -> ast.Module:
    assert module_file is not None
    return ast.parse(Path(module_file).read_text(encoding="utf-8"))


def _absolute(node: ast.ImportFrom, package: str) -> str:
    if node.level == 0:
        return node.module or ""
    parts = package.split(".")
    base = parts[: len(parts) - (node.level - 1)]
    return ".".join([*base, *([node.module] if node.module else [])])


def _imports(tree: ast.Module, package: str) -> list[tuple[str, str | None]]:
    """(module, imported name or None for `import x`) for every import in the tree."""
    found: list[tuple[str, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = _absolute(node, package)
            found.extend((module, alias.name) for alias in node.names)
        elif isinstance(node, ast.Import):
            found.extend((alias.name, None) for alias in node.names)
    return found


def _under(name: str, package: str) -> bool:
    return name == package or name.startswith(package + ".")


def test_chat_module_imports_nothing_from_services__S021_002_DoD10() -> None:
    """DoD-10 / 020 D9 — `llm/chat.py` imports nothing from `app.services`."""
    offenders = [
        f"{module}:{name}"
        for module, name in _imports(_module_tree(chat_module.__file__), "app.services.llm")
        if _under(module, "app.services")
        or (module == "app" and name == "services")
    ]
    assert offenders == []


def test_context_module_imports_no_parens_and_no_fastapi__S021_002_DoD10() -> None:
    """DoD-10 / R12 — `context.py` imports no `parens` and no `fastapi`."""
    offenders: list[str] = []
    for module, name in _imports(_module_tree(context_module.__file__), "app.services"):
        full = module if name is None else f"{module}.{name}"
        if _under(full, "app.services.parens") or _under(module, "app.services.parens"):
            offenders.append(full)
        if _under(module, "fastapi"):
            offenders.append(full)
    assert offenders == []


def test_context_module_service_imports_are_exactly_020s__S021_002_DoD10() -> None:
    """DoD-10 — the `app.services` imports are exactly 020's list (020 `002` DoD-16)."""
    services: set[str] = set()
    for module, name in _imports(_module_tree(context_module.__file__), "app.services"):
        if name is None:
            if _under(module, "app.services"):
                services.add(module.removeprefix("app.services").lstrip("."))
            continue
        if module == "app.services":
            services.add(name)
        elif _under(module, "app.services"):
            services.add(module.removeprefix("app.services."))
    assert services == {"messages", "sessions", "characters", "configuration", "memo_chain", "llm.chat"}
