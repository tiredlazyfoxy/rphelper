"""Tests for `app/services/llm/frames.py` — feature 019, step 001 (frame values + encoder).

Every expected value comes from `docs/plans/019.streaming-transport-and-stop/
001.frames-and-assistant-append.md` (Interface intent + Definition of done), from
`001.context.md` ("Wire field order per event": `event` first, compact separators,
`ensure_ascii=False`) and from the feature `context.md` (**D2**, "Test conventions"). The
expected bytes are the plan's worked examples, written out literally — never obtained by
calling the encoder. Bindings come from `status.md` `## Skeleton`, Step 001.

Each test name ends `__S019_001_DoD<n>`. DoD-1 .. DoD-4 are covered here; DoD-5 .. DoD-8 are
in `tests/test_assistant_append.py`.
"""

import json
from typing import Any

from app.errors import LlmUnreachableError
from app.services.llm.frames import (
    AcceptedFrame,
    DoneFrame,
    ErrorFrame,
    TokenFrame,
    ToolFailFrame,
    ToolResultFrame,
    ToolStartFrame,
    encode_frame,
    error_frame,
)

DATA_PREFIX = "data: "
FRAME_TERMINATOR = "\n\n"


def _payload(wire: str) -> Any:
    """The JSON between `data: ` and the terminating blank line, parsed (test side only)."""
    assert wire.startswith(DATA_PREFIX)
    assert wire.endswith(FRAME_TERMINATOR)
    return json.loads(wire[len(DATA_PREFIX) : -len(FRAME_TERMINATOR)])


# --- DoD-1: accepted / done carry the id as a decimal string -----------------------------


def test_an_accepted_frame_encodes_exactly_with_a_string_id__S019_001_DoD1() -> None:
    """DoD-1 — the worked example, byte for byte."""
    wire = encode_frame(AcceptedFrame(message_id=7250416938275332095))

    assert wire == 'data: {"event":"accepted","message_id":"7250416938275332095"}\n\n'


def test_a_done_frame_encodes_exactly_with_a_string_id__S019_001_DoD1() -> None:
    """DoD-1 — the worked example, byte for byte."""
    wire = encode_frame(DoneFrame(message_id=7250416938275332096))

    assert wire == 'data: {"event":"done","message_id":"7250416938275332096"}\n\n'


def test_the_message_id_is_a_json_string_not_a_number__S019_001_DoD1() -> None:
    """DoD-1 — parsed back, `message_id` is a `str` equal to the decimal form of the id."""
    accepted = _payload(encode_frame(AcceptedFrame(message_id=7250416938275332095)))
    done = _payload(encode_frame(DoneFrame(message_id=7250416938275332096)))

    assert isinstance(accepted["message_id"], str)
    assert accepted["message_id"] == "7250416938275332095"
    assert isinstance(done["message_id"], str)
    assert done["message_id"] == "7250416938275332096"


# --- DoD-2: token text — non-ASCII unescaped, newline never a blank line -----------------

TOKEN_TEXT = "Привет, «мир»\nnext"


def test_a_token_frame_parses_back_to_event_and_text__S019_001_DoD2() -> None:
    """DoD-2 — `data: ` + JSON whose parsed form is exactly the event and the text, with
    `event` the first key (001.context.md field order)."""
    parsed = _payload(encode_frame(TokenFrame(text=TOKEN_TEXT)))

    assert parsed == {"event": "token", "text": TOKEN_TEXT}
    assert list(parsed) == ["event", "text"]


def test_a_token_frame_keeps_the_cyrillic_unescaped__S019_001_DoD2() -> None:
    """DoD-2 — the raw wire text holds the characters themselves, not `\\uXXXX` escapes."""
    wire = encode_frame(TokenFrame(text=TOKEN_TEXT))

    assert "Привет" in wire
    assert "«мир»" in wire
    assert "\\u" not in wire


def test_a_token_frame_ends_with_exactly_one_blank_line__S019_001_DoD2() -> None:
    """DoD-2 — the frame ends with `\\n\\n` and not with a third newline."""
    wire = encode_frame(TokenFrame(text=TOKEN_TEXT))

    assert wire.startswith(DATA_PREFIX)
    assert wire.endswith(FRAME_TERMINATOR)
    assert not wire.endswith("\n" + FRAME_TERMINATOR)


def test_a_newline_in_the_text_never_makes_a_blank_line_inside_the_frame__S019_001_DoD2() -> None:
    """DoD-2 — only the terminator is a blank line: the frame body contains no `\\n\\n`,
    even for text made of newlines."""
    for text in (TOKEN_TEXT, "\n\n", "a\n\nb", "\n"):
        wire = encode_frame(TokenFrame(text=text))
        body = wire[: -len(FRAME_TERMINATOR)]

        assert FRAME_TERMINATOR not in body, text
        assert wire.count(FRAME_TERMINATOR) == 1, text
        assert _payload(wire) == {"event": "token", "text": text}


# --- DoD-3: the three tool frames --------------------------------------------------------


def test_a_tool_start_frame_encodes_exactly__S019_001_DoD3() -> None:
    """DoD-3 — the worked example, byte for byte."""
    wire = encode_frame(ToolStartFrame(tool="memo_search", call_id="call_9f2", args={"query": "x"}))

    assert wire == (
        'data: {"event":"tool_start","tool":"memo_search","call_id":"call_9f2",'
        '"args":{"query":"x"}}\n\n'
    )


def test_a_tool_result_frame_encodes_exactly__S019_001_DoD3() -> None:
    """DoD-3 — the worked example, byte for byte."""
    wire = encode_frame(ToolResultFrame(tool="memo_search", call_id="call_9f2", summary="3 memos"))

    assert wire == (
        'data: {"event":"tool_result","tool":"memo_search","call_id":"call_9f2",'
        '"summary":"3 memos"}\n\n'
    )


def test_a_tool_fail_frame_encodes_exactly__S019_001_DoD3() -> None:
    """DoD-3 — the worked example, byte for byte."""
    wire = encode_frame(ToolFailFrame(tool="web_search", call_id="c2", code="tool_failed"))

    assert wire == 'data: {"event":"tool_fail","tool":"web_search","call_id":"c2","code":"tool_failed"}\n\n'


# --- DoD-4: the error-frame constructor uses the inner fields ----------------------------


def test_an_error_frame_from_a_domain_error_encodes_exactly__S019_001_DoD4() -> None:
    """DoD-4 — the worked example, byte for byte."""
    frame = error_frame(LlmUnreachableError("Provider timed out", {"server_id": "7250000000000000007"}))

    assert isinstance(frame, ErrorFrame)
    assert encode_frame(frame) == (
        'data: {"event":"error","code":"llm_unreachable","message":"Provider timed out",'
        '"detail":{"server_id":"7250000000000000007"}}\n\n'
    )


def test_an_error_frame_has_no_error_wrapper_and_keeps_detail_ids_strings__S019_001_DoD4() -> None:
    """DoD-4 — no `"error"` wrapper key (not `to_wire()`); the id in `detail` stays a str."""
    parsed = _payload(
        encode_frame(error_frame(LlmUnreachableError("Provider timed out", {"server_id": "7250000000000000007"})))
    )

    assert "error" not in parsed
    assert list(parsed) == ["event", "code", "message", "detail"]
    assert isinstance(parsed["detail"]["server_id"], str)
    assert parsed["detail"]["server_id"] == "7250000000000000007"


def test_an_error_frame_from_a_bare_domain_error_has_null_message_and_empty_detail__S019_001_DoD4() -> None:
    """DoD-4 — `LlmUnreachableError()` encodes `"message":null` and `"detail":{}`."""
    frame = error_frame(LlmUnreachableError())
    wire = encode_frame(frame)
    parsed = _payload(wire)

    assert isinstance(frame, ErrorFrame)
    assert parsed == {"event": "error", "code": "llm_unreachable", "message": None, "detail": {}}
    assert list(parsed) == ["event", "code", "message", "detail"]
    assert '"message":null' in wire
    assert '"detail":{}' in wire
