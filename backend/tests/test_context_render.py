"""Feature 020 step 001 — chat value type, system-prompt renderer, message mapper.

Expected values come from `docs/plans/020.context-assembly/context.md` ("The prompt
format", "Kind tags on settled messages", D1-D12) and the step's Definition of done.
Headings and lead-ins are asserted as whole lines / line starts by exact text (D10); the
prose after a lead-in's colon is never asserted, except for the language names (D4).
No database is needed: every input is a plain value.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence
from pathlib import Path

import pytest

from app.services import context as context_module
from app.services.context import ForcedNoteLevel, render_system_prompt, to_chat_messages
from app.services.llm import chat as chat_module
from app.services.llm.chat import ChatMessage
from app.services.messages import StreamMessage

# --- literals from context.md "The prompt format" ----------------------------------------

H_SYSTEM = "=== System prompt ==="
H_SHEET = "=== Character sheet ==="
H_FORCED = "=== Forced notes ==="
H_TAGS = "=== Message tags ==="
H_LANG = "=== Languages ==="
H_PARENS = "=== Double parentheses ==="
ALL_HEADINGS = [H_SYSTEM, H_SHEET, H_FORCED, H_TAGS, H_LANG, H_PARENS]
INSTRUCTION_HEADINGS = [H_TAGS, H_LANG, H_PARENS]

L_USER = "--- User notes ---"
L_CHARACTER = "--- Character notes ---"
L_SETUP = "--- Setup notes ---"
L_SESSION = "--- Session notes ---"
ALL_LEVEL_HEADINGS = [L_USER, L_CHARACTER, L_SETUP, L_SESSION]

NOTE_LINE = "[note]"

LEAD_PARTNER = "- [partner]:"
LEAD_MY_TURN = "- [my turn]:"
LEAD_DECISION = "- [decision]:"
LEAD_UNTAGGED = "- Untagged:"
LEAD_CANDIDATES = "- Candidates:"
LEAD_MIRRORING = "- Mirroring:"
LEAD_OOC = "- Out of character:"
LEAD_WHOLLY = "- Wholly parenthesised:"
LEAD_FRAGMENT = "- Fragment:"

TAG_PARTNER = "[partner]"
TAG_TURN = "[my turn]"
TAG_DECISION = "[decision]"

FALLBACK = "English"

# User-supplied texts: markdown, inner newlines, leading / trailing whitespace; all distinct.
SYSTEM_PROMPT_TEXT = "  \n# Persona rules\n\nWrite **vividly**, in *third person*.\n- keep it short\n  \n"
SHEET_TEXT = "\n\n## Mira Valen\n\nA _retired_ cartographer.\n\n> Quiet, precise.\n   "


# --- helpers ------------------------------------------------------------------------------


def _line_offsets(prompt: str) -> list[tuple[int, str]]:
    """(character offset, line text) for every line of the prompt, split on line feed."""
    result: list[tuple[int, str]] = []
    offset = 0
    for line in prompt.split("\n"):
        result.append((offset, line))
        offset += len(line) + 1
    return result


def _whole_line_offsets(prompt: str, line_text: str) -> list[int]:
    return [offset for offset, line in _line_offsets(prompt) if line == line_text]


def _whole_line_offset(prompt: str, line_text: str) -> int:
    """Offset of the single whole line equal to `line_text`; fails if absent or repeated."""
    offsets = _whole_line_offsets(prompt, line_text)
    assert len(offsets) == 1, f"expected exactly one line {line_text!r}, found {len(offsets)}"
    return offsets[0]


def _has_line(prompt: str, line_text: str) -> bool:
    return bool(_whole_line_offsets(prompt, line_text))


def _lines_starting_after(prompt: str, prefix: str, after: int) -> list[str]:
    """Lines that start with `prefix` and begin after character offset `after`."""
    return [line for offset, line in _line_offsets(prompt) if offset > after and line.startswith(prefix)]


def _levels() -> list[ForcedNoteLevel]:
    return [
        ForcedNoteLevel(scope="user", bodies=["user-body-alpha", "user-body-beta"]),
        ForcedNoteLevel(scope="character", bodies=["character-body-gamma"]),
        ForcedNoteLevel(scope="setup", bodies=["setup-body-delta"]),
        ForcedNoteLevel(scope="session", bodies=["session-body-epsilon", "session-body-zeta"]),
    ]


def _full_prompt(
    *,
    system_prompt: str | None = SYSTEM_PROMPT_TEXT,
    sheet: str = SHEET_TEXT,
    levels: Sequence[ForcedNoteLevel] | None = None,
    rp_language: str | None = "Japanese",
    preferred_language: str | None = "Russian",
) -> str:
    return render_system_prompt(
        system_prompt,
        sheet,
        _levels() if levels is None else levels,
        rp_language,
        preferred_language,
    )


_TS = "2026-10-04T00:00:00.000Z"


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


def _zone(row_id: int, text: str, role: str = "user") -> StreamMessage:
    return StreamMessage(
        id=row_id,
        session_id=1,
        role=role,
        kind=None,
        text=text,
        settled_at=None,
        created_at=_TS,
        updated_at=_TS,
    )


def _contents(messages: Sequence[ChatMessage]) -> list[str]:
    return [message.content for message in messages]


# --- DoD-1: ChatMessage ------------------------------------------------------------------


def test_chat_message_holds_role_and_content__S020_001_DoD1() -> None:
    """DoD-1 — both roles construct; the fields hold what was given."""
    user_message = ChatMessage(role="user", content="hello there")
    assistant_message = ChatMessage(role="assistant", content="general kenobi")
    assert user_message.role == "user"
    assert user_message.content == "hello there"
    assert assistant_message.role == "assistant"
    assert assistant_message.content == "general kenobi"


@pytest.mark.parametrize("field_name", ["role", "content"])
def test_chat_message_is_immutable__S020_001_DoD1(field_name: str) -> None:
    """DoD-1 — assigning a field raises."""
    message = ChatMessage(role="user", content="fixed")
    with pytest.raises(AttributeError):
        setattr(message, field_name, "assistant")


# --- DoD-2: six headings, order, verbatim system prompt and sheet -------------------------


def test_full_prompt_has_six_headings_in_order__S020_001_DoD2() -> None:
    """DoD-2 — every input present: the six heading lines as whole lines, in fixed order."""
    prompt = _full_prompt()
    offsets = [_whole_line_offset(prompt, heading) for heading in ALL_HEADINGS]
    assert offsets == sorted(offsets)


def test_system_prompt_and_sheet_verbatim_in_their_sections__S020_001_DoD2() -> None:
    """DoD-2 — the system prompt and the sheet appear verbatim between their heading and the next."""
    prompt = _full_prompt()
    system_heading = _whole_line_offset(prompt, H_SYSTEM)
    sheet_heading = _whole_line_offset(prompt, H_SHEET)
    forced_heading = _whole_line_offset(prompt, H_FORCED)

    system_at = prompt.find(SYSTEM_PROMPT_TEXT)
    assert system_at != -1, "system prompt not verbatim in the prompt"
    assert system_heading < system_at
    assert system_at + len(SYSTEM_PROMPT_TEXT) <= sheet_heading

    sheet_at = prompt.find(SHEET_TEXT)
    assert sheet_at != -1, "sheet not verbatim in the prompt"
    assert sheet_heading < sheet_at
    assert sheet_at + len(SHEET_TEXT) <= forced_heading


# --- DoD-3: omitted system prompt / sheet --------------------------------------------------


def test_null_system_prompt_omits_only_its_heading__S020_001_DoD3() -> None:
    """DoD-3 — a null system prompt omits `=== System prompt ===` and nothing else."""
    prompt = _full_prompt(system_prompt=None)
    assert not _has_line(prompt, H_SYSTEM)
    remaining = [heading for heading in ALL_HEADINGS if heading != H_SYSTEM]
    offsets = [_whole_line_offset(prompt, heading) for heading in remaining]
    assert offsets == sorted(offsets)
    assert SHEET_TEXT in prompt


@pytest.mark.parametrize("sheet", ["", "   \n\t  \n "], ids=["empty", "whitespace-only"])
def test_empty_or_blank_sheet_omits_only_its_heading__S020_001_DoD3(sheet: str) -> None:
    """DoD-3 — a sheet of `""` or only whitespace omits `=== Character sheet ===` and nothing else."""
    prompt = _full_prompt(sheet=sheet)
    assert not _has_line(prompt, H_SHEET)
    remaining = [heading for heading in ALL_HEADINGS if heading != H_SHEET]
    offsets = [_whole_line_offset(prompt, heading) for heading in remaining]
    assert offsets == sorted(offsets)
    assert SYSTEM_PROMPT_TEXT in prompt


# --- DoD-4: forced-note level blocks --------------------------------------------------------


def test_forced_note_levels_render_in_given_order_with_note_markers__S020_001_DoD4() -> None:
    """DoD-4 — level headings in order; each followed by its own bodies, in order, after `[note]`."""
    prompt = _full_prompt()
    forced_heading = _whole_line_offset(prompt, H_FORCED)
    tags_heading = _whole_line_offset(prompt, H_TAGS)

    level_offsets = [_whole_line_offset(prompt, heading) for heading in ALL_LEVEL_HEADINGS]
    assert level_offsets == sorted(level_offsets)
    assert forced_heading < level_offsets[0]
    assert level_offsets[-1] < tags_heading

    bounds = [*level_offsets, tags_heading]
    for index, level in enumerate(_levels()):
        start, end = bounds[index], bounds[index + 1]
        body_offsets: list[int] = []
        for body in level.bodies:
            at = prompt.find(body)
            assert at != -1, f"body {body!r} not verbatim in the prompt"
            assert start < at < end, f"body {body!r} not inside its own level block"
            assert prompt[:at].endswith(NOTE_LINE + "\n"), f"body {body!r} not preceded by a [note] line"
            body_offsets.append(at)
        assert body_offsets == sorted(body_offsets)

    total_bodies = sum(len(level.bodies) for level in _levels())
    assert len(_whole_line_offsets(prompt, NOTE_LINE)) == total_bodies


def test_forced_note_bodies_are_verbatim__S020_001_DoD4() -> None:
    """DoD-4 — a body with markdown, inner newlines and edge whitespace enters verbatim."""
    body = "  **Never** break character.\n\n- unless asked\n  "
    levels = [ForcedNoteLevel(scope="user", bodies=[body])]
    prompt = _full_prompt(levels=levels)
    at = prompt.find(body)
    assert at != -1
    assert prompt[:at].endswith(NOTE_LINE + "\n")
    assert _whole_line_offset(prompt, L_USER) < at < _whole_line_offset(prompt, H_TAGS)


# --- DoD-5: empty levels, missing setup, no forced notes -------------------------------------


def test_level_with_no_bodies_has_no_heading__S020_001_DoD5() -> None:
    """DoD-5 — a level given with no bodies has no heading line."""
    levels = [
        ForcedNoteLevel(scope="user", bodies=["only-user-body"]),
        ForcedNoteLevel(scope="character", bodies=[]),
        ForcedNoteLevel(scope="setup", bodies=["only-setup-body"]),
        ForcedNoteLevel(scope="session", bodies=[]),
    ]
    prompt = _full_prompt(levels=levels)
    assert _has_line(prompt, L_USER)
    assert _has_line(prompt, L_SETUP)
    assert not _has_line(prompt, L_CHARACTER)
    assert not _has_line(prompt, L_SESSION)
    assert _has_line(prompt, H_FORCED)


def test_no_setup_level_session_follows_character_directly__S020_001_DoD5() -> None:
    """DoD-5 / R2 — without a setup level there is no setup heading and no gap."""
    character_body = "character-body-without-setup"
    session_body = "session-body-without-setup"
    levels = [
        ForcedNoteLevel(scope="user", bodies=["user-body-without-setup"]),
        ForcedNoteLevel(scope="character", bodies=[character_body]),
        ForcedNoteLevel(scope="session", bodies=[session_body]),
    ]
    prompt = _full_prompt(levels=levels)
    assert not _has_line(prompt, L_SETUP)
    character_heading = _whole_line_offset(prompt, L_CHARACTER)
    session_heading = _whole_line_offset(prompt, L_SESSION)
    assert character_heading < session_heading
    character_at = prompt.find(character_body)
    assert character_heading < character_at < session_heading
    between = prompt[character_at + len(character_body) : session_heading]
    assert between.strip() == "", f"something sits between the character and session blocks: {between!r}"
    assert session_heading < prompt.find(session_body)


@pytest.mark.parametrize(
    "levels",
    [
        [],
        [
            ForcedNoteLevel(scope="user", bodies=[]),
            ForcedNoteLevel(scope="character", bodies=[]),
            ForcedNoteLevel(scope="setup", bodies=[]),
            ForcedNoteLevel(scope="session", bodies=[]),
        ],
    ],
    ids=["empty-sequence", "all-levels-empty"],
)
def test_no_forced_notes_omits_forced_section__S020_001_DoD5(levels: list[ForcedNoteLevel]) -> None:
    """DoD-5 — no forced note anywhere omits `=== Forced notes ===` (and every level heading)."""
    prompt = _full_prompt(levels=levels)
    assert not _has_line(prompt, H_FORCED)
    for heading in ALL_LEVEL_HEADINGS:
        assert not _has_line(prompt, heading)
    assert not _has_line(prompt, NOTE_LINE)
    for heading in (H_SYSTEM, H_SHEET, H_TAGS, H_LANG, H_PARENS):
        assert _has_line(prompt, heading)


# --- DoD-6: language instructions --------------------------------------------------------------


def test_language_lines_name_rp_and_preferred_languages__S020_001_DoD6() -> None:
    """DoD-6 — Candidates names the RP language, Out of character the preferred one; Mirroring present."""
    prompt = _full_prompt(rp_language="Japanese", preferred_language="Russian")
    languages_heading = _whole_line_offset(prompt, H_LANG)

    candidates = _lines_starting_after(prompt, LEAD_CANDIDATES, languages_heading)
    assert candidates, "no `- Candidates:` line after `=== Languages ===`"
    assert any("Japanese" in line for line in candidates)

    ooc = _lines_starting_after(prompt, LEAD_OOC, languages_heading)
    assert ooc, "no `- Out of character:` line after `=== Languages ===`"
    assert any("Russian" in line for line in ooc)

    assert _lines_starting_after(prompt, LEAD_MIRRORING, languages_heading), (
        "no `- Mirroring:` line after `=== Languages ===`"
    )


# --- DoD-7: English fallback -------------------------------------------------------------------


def _language_lines(prompt: str) -> tuple[list[str], list[str]]:
    languages_heading = _whole_line_offset(prompt, H_LANG)
    candidates = _lines_starting_after(prompt, LEAD_CANDIDATES, languages_heading)
    ooc = _lines_starting_after(prompt, LEAD_OOC, languages_heading)
    assert candidates and ooc
    return candidates, ooc


def test_null_rp_language_names_english_on_candidates__S020_001_DoD7() -> None:
    """DoD-7 — null RP language: `English` on Candidates; the set preferred language stays on OOC."""
    prompt = _full_prompt(rp_language=None, preferred_language="Russian")
    candidates, ooc = _language_lines(prompt)
    assert any(FALLBACK in line for line in candidates)
    assert any("Russian" in line for line in ooc)


def test_null_preferred_language_names_english_on_ooc__S020_001_DoD7() -> None:
    """DoD-7 — null preferred language: `English` on OOC; the set RP language stays on Candidates."""
    prompt = _full_prompt(rp_language="Japanese", preferred_language=None)
    candidates, ooc = _language_lines(prompt)
    assert any("Japanese" in line for line in candidates)
    assert any(FALLBACK in line for line in ooc)


def test_both_languages_null_render_english_without_raising__S020_001_DoD7() -> None:
    """DoD-7 — both null: renders without raising; both lines name `English`."""
    prompt = _full_prompt(rp_language=None, preferred_language=None)
    candidates, ooc = _language_lines(prompt)
    assert any(FALLBACK in line for line in candidates)
    assert any(FALLBACK in line for line in ooc)


# --- DoD-8: message-tag instructions ----------------------------------------------------------


def test_message_tags_section_holds_four_lead_ins__S020_001_DoD8() -> None:
    """DoD-8 — after `=== Message tags ===`: `[partner]`, `[my turn]`, `[decision]`, `Untagged` lead-ins."""
    prompt = _full_prompt()
    tags_heading = _whole_line_offset(prompt, H_TAGS)
    for lead_in in (LEAD_PARTNER, LEAD_MY_TURN, LEAD_DECISION, LEAD_UNTAGGED):
        assert _lines_starting_after(prompt, lead_in, tags_heading), f"no {lead_in!r} line after {H_TAGS!r}"


# --- DoD-9: double-parentheses instructions ---------------------------------------------------


def test_double_parentheses_section_holds_two_lead_ins__S020_001_DoD9() -> None:
    """DoD-9 — after `=== Double parentheses ===`: `Wholly parenthesised` and `Fragment` lead-ins."""
    prompt = _full_prompt()
    parens_heading = _whole_line_offset(prompt, H_PARENS)
    for lead_in in (LEAD_WHOLLY, LEAD_FRAGMENT):
        assert _lines_starting_after(prompt, lead_in, parens_heading), f"no {lead_in!r} line after {H_PARENS!r}"


# --- DoD-10: minimal prompt --------------------------------------------------------------------


def test_minimal_prompt_starts_with_message_tags__S020_001_DoD10() -> None:
    """DoD-10 — null prompt, empty sheet, no forced notes: non-empty, starts with Message tags, three headings."""
    prompt = render_system_prompt(None, "", [], "Japanese", "Russian")
    assert prompt != ""
    assert prompt.split("\n")[0] == H_TAGS
    present = [line for _, line in _line_offsets(prompt) if line in ALL_HEADINGS]
    assert present == INSTRUCTION_HEADINGS


def test_minimal_prompt_with_null_languages_still_has_three_headings__S020_001_DoD10() -> None:
    """DoD-10 — the same minimal prompt with null languages keeps the same shape."""
    prompt = render_system_prompt(None, "   ", [], None, None)
    assert prompt != ""
    assert prompt.split("\n")[0] == H_TAGS
    present = [line for _, line in _line_offsets(prompt) if line in ALL_HEADINGS]
    assert present == INSTRUCTION_HEADINGS


# --- DoD-11: no tool names ---------------------------------------------------------------------

_TOOL_NAMES = ("memo_search", "session_search", "web_search")


@pytest.mark.parametrize(
    ("system_prompt", "sheet", "with_levels", "rp_language", "preferred_language"),
    [
        (SYSTEM_PROMPT_TEXT, SHEET_TEXT, True, "Japanese", "Russian"),
        (None, "", False, None, None),
        (None, SHEET_TEXT, True, None, "Russian"),
        (SYSTEM_PROMPT_TEXT, "  ", False, "Japanese", None),
    ],
    ids=["all-present", "all-absent", "mixed-a", "mixed-b"],
)
def test_prompt_never_names_a_tool__S020_001_DoD11(
    system_prompt: str | None,
    sheet: str,
    with_levels: bool,
    rp_language: str | None,
    preferred_language: str | None,
) -> None:
    """DoD-11 / D2 — the prompt names no tool, with any inputs."""
    prompt = render_system_prompt(
        system_prompt,
        sheet,
        _levels() if with_levels else [],
        rp_language,
        preferred_language,
    )
    for tool_name in _TOOL_NAMES:
        assert tool_name not in prompt


# --- DoD-12: role and kind tags ----------------------------------------------------------------


def test_zone_rows_map_untagged_with_their_role__S020_001_DoD12() -> None:
    """DoD-12 — zone rows (kind null) keep their role; content is the text exactly."""
    user_text = "What if Mira refuses the map?"
    assistant_text = "She could hesitate first, then hand it over."
    messages = to_chat_messages([], [_zone(10, user_text, "user"), _zone(11, assistant_text, "assistant")])
    assert [(m.role, m.content) for m in messages] == [("user", user_text), ("assistant", assistant_text)]


def test_settled_rows_carry_kind_tags_and_stored_role__S020_001_DoD12() -> None:
    """DoD-12 / D1 — partner, turn, decision get `[tag]\\n` + text; the stored role is kept."""
    partner_text = "The stranger leans across the table."
    turn_user_text = "Mira folds the map and says nothing."
    turn_assistant_text = "Mira finally speaks: 'No.'"
    decision_text = "We agreed Mira never sells the map."
    entries = [
        _settled(1, "partner", partner_text, "user"),
        _settled(2, "turn", turn_user_text, "user"),
        _settled(3, "turn", turn_assistant_text, "assistant"),
        _settled(4, "decision", decision_text, "user"),
    ]
    messages = to_chat_messages(entries, [])
    assert [(m.role, m.content) for m in messages] == [
        ("user", TAG_PARTNER + "\n" + partner_text),
        ("user", TAG_TURN + "\n" + turn_user_text),
        ("assistant", TAG_TURN + "\n" + turn_assistant_text),
        ("user", TAG_DECISION + "\n" + decision_text),
    ]


def test_mapper_returns_chat_messages__S020_001_DoD12() -> None:
    """DoD-12 — the output items are `ChatMessage` values."""
    messages = to_chat_messages([_settled(1, "partner", "p-text")], [_zone(2, "z-text")])
    assert all(isinstance(message, ChatMessage) for message in messages)


# --- DoD-13: merge by id ---------------------------------------------------------------------


def test_rows_merge_by_id_across_lists__S020_001_DoD13() -> None:
    """DoD-13 / D7 — out-of-order, interleaved settled and zone ids come back ascending by id."""
    entries = [
        _settled(500, "turn", "settled-500"),
        _settled(200, "partner", "settled-200"),
    ]
    zone = [
        _zone(700, "zone-700"),
        _zone(100, "zone-100"),
        _zone(300, "zone-300", "assistant"),
    ]
    messages = to_chat_messages(entries, zone)
    assert _contents(messages) == [
        "zone-100",
        TAG_PARTNER + "\nsettled-200",
        "zone-300",
        TAG_TURN + "\nsettled-500",
        "zone-700",
    ]


def test_only_entries_sorted__S020_001_DoD13() -> None:
    """DoD-13 — the zone may be empty."""
    entries = [_settled(9, "decision", "e-9"), _settled(3, "partner", "e-3")]
    assert _contents(to_chat_messages(entries, [])) == [TAG_PARTNER + "\ne-3", TAG_DECISION + "\ne-9"]


def test_only_zone_sorted__S020_001_DoD13() -> None:
    """DoD-13 — the settled list may be empty."""
    zone = [_zone(8, "z-8"), _zone(4, "z-4", "assistant"), _zone(6, "z-6")]
    assert _contents(to_chat_messages([], zone)) == ["z-4", "z-6", "z-8"]


def test_both_empty_gives_empty_list__S020_001_DoD13() -> None:
    """DoD-13 — both empty gives an empty list."""
    assert to_chat_messages([], []) == []


# --- DoD-14: tool rows skipped -----------------------------------------------------------------


def test_tool_rows_are_skipped_in_either_list__S020_001_DoD14() -> None:
    """DoD-14 / D3 — a `tool` row in either list is absent; the rest keep id order."""
    entries = [
        _settled(40, "turn", "settled-40"),
        _settled(20, "turn", "settled-tool-20", "tool"),
        _settled(10, "partner", "settled-10"),
    ]
    zone = [
        _zone(50, "zone-50", "assistant"),
        _zone(30, "zone-tool-30", "tool"),
        _zone(60, "zone-60"),
    ]
    messages = to_chat_messages(entries, zone)
    assert _contents(messages) == [
        TAG_PARTNER + "\nsettled-10",
        TAG_TURN + "\nsettled-40",
        "zone-50",
        "zone-60",
    ]
    for message in messages:
        assert "tool-20" not in message.content
        assert "tool-30" not in message.content
        assert message.role in ("user", "assistant")


# --- DoD-15: verbatim texts --------------------------------------------------------------------


def test_texts_pass_through_unchanged__S020_001_DoD15() -> None:
    """DoD-15 / R12 — `(( ))`, edge whitespace and blank lines survive; only the tag is added."""
    wholly_ooc = "((can we slow the pacing down a little?))"
    draft_with_fragment = "Mira steps inside. ((make this moodier)) She sits by the fire."
    decision_with_parens = "((Agreed: no time skip until the storm ends.))"
    whitespace_zone = "  \n\nFirst paragraph.\n\n\n  Second paragraph.  \n\n"
    whitespace_partner = "\n   The rain fell harder.\n\n\nThunder.   \n"
    entries = [
        _settled(1, "decision", decision_with_parens, "user"),
        _settled(2, "partner", whitespace_partner, "user"),
    ]
    zone = [
        _zone(3, wholly_ooc, "user"),
        _zone(4, draft_with_fragment, "user"),
        _zone(5, whitespace_zone, "assistant"),
    ]
    messages = to_chat_messages(entries, zone)
    assert _contents(messages) == [
        TAG_DECISION + "\n" + decision_with_parens,
        TAG_PARTNER + "\n" + whitespace_partner,
        wholly_ooc,
        draft_with_fragment,
        whitespace_zone,
    ]


# --- DoD-16: no truncation ---------------------------------------------------------------------


def test_large_record_arrives_whole__S020_001_DoD16() -> None:
    """DoD-16 / D12 — 2,000 rows, one 200,000 characters long, all arrive un-truncated."""
    big_text = ("Long paragraph of roleplay text. " * 7000)[:199_990] + "END-MARKER"
    assert len(big_text) == 200_000
    big_id = 1_337
    entries: list[StreamMessage] = []
    zone: list[StreamMessage] = []
    for row_id in range(1, 2_001):
        if row_id == big_id:
            zone.append(_zone(row_id, big_text))
        elif row_id % 2 == 0:
            entries.append(_settled(row_id, "turn", f"settled-{row_id}"))
        else:
            zone.append(_zone(row_id, f"zone-{row_id}"))
    messages = to_chat_messages(entries, zone)
    assert len(messages) == 2_000
    big_message = messages[big_id - 1]
    assert big_message.content == big_text
    assert len(big_message.content) == 200_000


# --- DoD-17: source checks ---------------------------------------------------------------------


def _module_source(module_file: str | None) -> str:
    assert module_file is not None
    return Path(module_file).read_text(encoding="utf-8")


def _imported_modules(source: str, package: str) -> list[str]:
    """Absolute dotted names of every import in `source`; relative ones resolved against `package`."""
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                parts = package.split(".")
                base_parts = parts[: len(parts) - (node.level - 1)]
                base = ".".join(base_parts)
            else:
                base = ""
            module = node.module or ""
            prefix = ".".join(part for part in (base, module) if part)
            names.append(prefix)
            names.extend(f"{prefix}.{alias.name}" if prefix else alias.name for alias in node.names)
    return names


def test_chat_module_imports_nothing_from_services__S020_001_DoD17() -> None:
    """DoD-17 / D9 — `llm/chat.py` imports nothing from `app.services`."""
    imported = _imported_modules(_module_source(chat_module.__file__), "app.services.llm")
    offenders = [name for name in imported if name == "app.services" or name.startswith("app.services.")]
    assert offenders == []
    assert "app.services.context" not in imported
    assert "app.services.llm.client" not in imported


def test_context_module_avoids_parens_fastapi_and_translation__S020_001_DoD17() -> None:
    """DoD-17 / R8 / R12 — `context.py` imports no `parens`, no `fastapi`; no `translation` substring."""
    source = _module_source(context_module.__file__)
    imported = _imported_modules(source, "app.services")
    parens_offenders = [
        name for name in imported if name == "app.services.parens" or name.startswith("app.services.parens.")
    ]
    assert parens_offenders == []
    fastapi_offenders = [name for name in imported if name == "fastapi" or name.startswith("fastapi.")]
    assert fastapi_offenders == []
    assert "translation" not in source
