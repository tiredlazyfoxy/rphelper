"""Tests for the assembler in `app/services/context.py` — feature 020, step 002.

Every expected value comes from `docs/plans/020.context-assembly/002.assemble-context.md`
(Definition of done), the feature `context.md` ("The prompt format", the Kind tags table,
D1..D12) and `002.context.md`. No renderer or mapper of step 001 is called to compute an
expectation. Bindings come from `status.md` `## Skeleton` -> Step 002:

- `AssembledContext` (frozen: `system_prompt: str`, `messages: Sequence[ChatMessage]`)
- `assemble_context(connection, user_id, session_id) -> AssembledContext`

Users, characters, setups, sessions, `memos` and `messages` rows are raw-inserted with
file-local helpers; `conftest.py` is untouched and no shared fixture is added. Test names
follow `test_<behavior>__S020_002_DoD<n>`.
"""

from __future__ import annotations

import ast
import inspect
import json
from collections.abc import Sequence
from typing import Any

import pytest
from sqlalchemy import Engine, Table, select

from app.db import schema
from app.errors import SessionNotFoundError
from app.roles import Role
from app.services import context as context_module
from app.services.context import AssembledContext, assemble_context
from app.services.llm.chat import ChatMessage, ToolCall

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
ARCHIVED_AT = "2026-02-01T00:00:00.000000+00:00"

USER_A = 101
USER_B = 202

CHAR_A1 = 1_001  # the character of SESSION_MAIN
CHAR_A2 = 1_002  # another character of the caller
CHAR_B1 = 1_101

SETUP_A1 = 2_001  # under CHAR_A1; the setup of SESSION_MAIN
SETUP_A2 = 2_002  # under CHAR_A1; the setup of SESSION_SIBLING
SETUP_B1 = 2_101

SESSION_MAIN = 3_001  # USER_A, CHAR_A1, SETUP_A1
SESSION_NO_SETUP = 3_002  # USER_A, CHAR_A1, no setup
SESSION_SIBLING = 3_003  # USER_A, CHAR_A1, SETUP_A2 (another session of the same character)
SESSION_A2 = 3_004  # USER_A, CHAR_A2, no setup
SESSION_B1 = 3_101  # USER_B, CHAR_B1, SETUP_B1

UNKNOWN_SESSION_ID = 7_777_777_777

# The prompt format (context.md) — exact literals.
H_SYSTEM_PROMPT = "=== System prompt ==="
H_SHEET = "=== Character sheet ==="
H_FORCED = "=== Forced notes ==="
H_TAGS = "=== Message tags ==="
H_LANGUAGES = "=== Languages ==="
H_PARENS = "=== Double parentheses ==="
SIX_HEADINGS = [H_SYSTEM_PROMPT, H_SHEET, H_FORCED, H_TAGS, H_LANGUAGES, H_PARENS]

LEVEL_HEADING = {
    "user": "--- User notes ---",
    "character": "--- Character notes ---",
    "setup": "--- Setup notes ---",
    "session": "--- Session notes ---",
}
NOTE_MARKER = "[note]"

LEAD_INS = {
    H_TAGS: ["- [partner]:", "- [my turn]:", "- [decision]:", "- Untagged:"],
    H_LANGUAGES: ["- Candidates:", "- Mirroring:", "- Out of character:"],
    H_PARENS: ["- Wholly parenthesised:", "- Fragment:"],
}
CANDIDATES = "- Candidates:"
OUT_OF_CHARACTER = "- Out of character:"

KIND_TAG = {"partner": "[partner]", "turn": "[my turn]", "decision": "[decision]"}

FOUR_SCOPES = ["user", "character", "setup", "session"]


# --- seeding ------------------------------------------------------------------------------


def _insert_user(
    engine: Engine,
    *,
    user_id: int,
    username: str,
    rp_language: str | None = None,
    preferred_language: str | None = None,
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
                preferred_language=preferred_language,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_character(
    engine: Engine,
    *,
    character_id: int,
    user_id: int,
    name: str,
    sheet: str = "",
    system_prompt: str | None = None,
    archived_at: str | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.characters.insert().values(
                id=character_id,
                user_id=user_id,
                name=name,
                sheet=sheet,
                archived_at=archived_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
                model_server_id=None,
                model_name=None,
                system_prompt=system_prompt,
                tool_memo_search=None,
                tool_session_search=None,
                tool_web_search=None,
            )
        )


def _insert_setup(
    engine: Engine, *, setup_id: int, user_id: int, character_id: int, name: str
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.setups.insert().values(
                id=setup_id,
                user_id=user_id,
                character_id=character_id,
                name=name,
                description="",
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_session(
    engine: Engine,
    *,
    session_id: int,
    user_id: int,
    character_id: int,
    setup_id: int | None,
    system_prompt: str | None = None,
    rp_language: str | None = None,
    preferred_language: str | None = None,
    archived_at: str | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.insert().values(
                id=session_id,
                user_id=user_id,
                character_id=character_id,
                setup_id=setup_id,
                last_used_at=TIMESTAMP,
                archived_at=archived_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
                model_server_id=None,
                model_name=None,
                system_prompt=system_prompt,
                tool_memo_search=None,
                tool_session_search=None,
                tool_web_search=None,
                rp_language=rp_language,
                preferred_language=preferred_language,
            )
        )


def _insert_memo(
    engine: Engine,
    *,
    memo_id: int,
    user_id: int,
    scope: str,
    scope_id: int,
    body: str,
    sort_key: int = 0,
    is_enabled: bool = True,
    is_forced: bool = True,
) -> None:
    """Raw-insert one `memos` row (a user-level note's `scope_id` is the owner's id)."""
    with engine.begin() as connection:
        connection.execute(
            schema.memos.insert().values(
                id=memo_id,
                user_id=user_id,
                scope=scope,
                scope_id=scope_id,
                body=body,
                is_enabled=is_enabled,
                is_forced=is_forced,
                sort_key=sort_key,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_message(
    engine: Engine,
    *,
    message_id: int,
    session_id: int,
    text: str,
    user_id: int = USER_A,
    role: str = "user",
    kind: str | None = None,
    related_to: int | None = None,
    settled_at: str | None = None,
    tool_name: str | None = None,
    tool_payload: str | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.messages.insert().values(
                id=message_id,
                user_id=user_id,
                session_id=session_id,
                role=role,
                kind=kind,
                text=text,
                related_to=related_to,
                settled_at=settled_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
                tool_name=tool_name,
                tool_payload=tool_payload,
            )
        )


def _settled(
    engine: Engine,
    message_id: int,
    kind: str,
    text: str,
    *,
    session_id: int = SESSION_MAIN,
    role: str = "user",
) -> None:
    _insert_message(
        engine,
        message_id=message_id,
        session_id=session_id,
        text=text,
        role=role,
        kind=kind,
        settled_at=TIMESTAMP,
    )


def _zone(
    engine: Engine,
    message_id: int,
    text: str,
    *,
    session_id: int = SESSION_MAIN,
    role: str = "user",
) -> None:
    _insert_message(engine, message_id=message_id, session_id=session_id, text=text, role=role)


def _update(engine: Engine, table: Table, row_id: int, **values: Any) -> None:
    with engine.begin() as connection:
        connection.execute(table.update().where(table.c.id == row_id).values(**values))


def _scope_id(scope: str, session_id: int = SESSION_MAIN) -> int:
    """The MAIN session's scope id for a level (user level: the owner's id)."""
    return {
        "user": USER_A,
        "character": CHAR_A1,
        "setup": SETUP_A1,
        "session": session_id,
    }[scope]


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """Two owners; USER_A has two characters, two setups under one, and four sessions."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="alice")
    _insert_user(db_engine, user_id=USER_B, username="bob")
    _insert_character(db_engine, character_id=CHAR_A1, user_id=USER_A, name="Aria")
    _insert_character(db_engine, character_id=CHAR_A2, user_id=USER_A, name="Brynn")
    _insert_character(db_engine, character_id=CHAR_B1, user_id=USER_B, name="Bob's own")
    _insert_setup(db_engine, setup_id=SETUP_A1, user_id=USER_A, character_id=CHAR_A1, name="Tavern")
    _insert_setup(db_engine, setup_id=SETUP_A2, user_id=USER_A, character_id=CHAR_A1, name="Road")
    _insert_setup(db_engine, setup_id=SETUP_B1, user_id=USER_B, character_id=CHAR_B1, name="Dock")
    _insert_session(
        db_engine, session_id=SESSION_MAIN, user_id=USER_A, character_id=CHAR_A1, setup_id=SETUP_A1
    )
    _insert_session(
        db_engine, session_id=SESSION_NO_SETUP, user_id=USER_A, character_id=CHAR_A1, setup_id=None
    )
    _insert_session(
        db_engine,
        session_id=SESSION_SIBLING,
        user_id=USER_A,
        character_id=CHAR_A1,
        setup_id=SETUP_A2,
    )
    _insert_session(
        db_engine, session_id=SESSION_A2, user_id=USER_A, character_id=CHAR_A2, setup_id=None
    )
    _insert_session(
        db_engine, session_id=SESSION_B1, user_id=USER_B, character_id=CHAR_B1, setup_id=SETUP_B1
    )
    return db_engine


# --- call and inspection helpers ----------------------------------------------------------


def _assemble(
    engine: Engine, user_id: int = USER_A, session_id: int = SESSION_MAIN
) -> AssembledContext:
    with engine.connect() as connection:
        return assemble_context(connection, user_id, session_id)


def _lines(prompt: str) -> list[str]:
    return prompt.split("\n")


def _has_line(prompt: str, line_text: str) -> bool:
    return line_text in _lines(prompt)


def _line_index(prompt: str, line_text: str) -> int:
    """The index of the single line equal to `line_text`."""
    hits = [i for i, line in enumerate(_lines(prompt)) if line == line_text]
    assert len(hits) == 1, f"expected exactly one line {line_text!r}, found {len(hits)}"
    return hits[0]


def _line_after(prompt: str, heading: str) -> str:
    lines = _lines(prompt)
    return lines[_line_index(prompt, heading) + 1]


def _lead_line(prompt: str, lead: str) -> str:
    hits = [line for line in _lines(prompt) if line.startswith(lead)]
    assert len(hits) == 1, f"expected exactly one line starting {lead!r}, found {len(hits)}"
    return hits[0]


def _contents(context: AssembledContext) -> list[str]:
    return [message.content for message in context.messages]


def _all_text(context: AssembledContext) -> str:
    """The whole result: the system prompt and every message's content."""
    return "\n".join([context.system_prompt, *_contents(context)])


def _tagged(kind: str, text: str) -> str:
    return f"{KIND_TAG[kind]}\n{text}"


def _assert_in_level(prompt: str, scope: str, body: str, present_scopes: Sequence[str]) -> None:
    """`body` sits as a whole line after a `[note]` line, under `scope`'s level heading."""
    lines = _lines(prompt)
    body_index = _line_index(prompt, body)
    assert lines[body_index - 1] == NOTE_MARKER
    heading_index = _line_index(prompt, LEVEL_HEADING[scope])
    assert heading_index < body_index
    later = present_scopes[present_scopes.index(scope) + 1 :]
    if later:
        assert body_index < _line_index(prompt, LEVEL_HEADING[later[0]])
    else:
        assert body_index < _line_index(prompt, H_TAGS)


def _messages_snapshot(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(select(schema.messages).order_by(schema.messages.c.id))
        return [dict(row) for row in rows.mappings()]


def _memos_snapshot(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(select(schema.memos).order_by(schema.memos.c.id))
        return [dict(row) for row in rows.mappings()]


# --- DoD-1: happy path --------------------------------------------------------------------

HAPPY_BODIES = {
    "user": "happy user-level forced body",
    "character": "happy character-level forced body",
    "setup": "happy setup-level forced body",
    "session": "happy session-level forced body",
}


def _seed_happy(engine: Engine) -> None:
    _update(engine, schema.characters, CHAR_A1, system_prompt="P", sheet="S")
    for offset, scope in enumerate(FOUR_SCOPES):
        _insert_memo(
            engine,
            memo_id=5_001 + offset,
            user_id=USER_A,
            scope=scope,
            scope_id=_scope_id(scope),
            body=HAPPY_BODIES[scope],
        )
    _settled(engine, 4_001, "partner", "The partner's pasted block.")
    _settled(engine, 4_002, "turn", "My own settled turn.")
    _settled(engine, 4_003, "decision", "((The tavern burns down tonight.))")
    _zone(engine, 4_004, "A live zone draft from me.", role="user")
    _zone(engine, 4_005, "The assistant's live zone answer.", role="assistant")


def test_happy_path_returns_an_assembled_context__S020_002_DoD1(engine: Engine) -> None:
    _seed_happy(engine)

    result = _assemble(engine)

    assert isinstance(result, AssembledContext)
    assert isinstance(result.system_prompt, str)


def test_happy_path_system_prompt_and_sheet_sit_under_their_headings__S020_002_DoD1(
    engine: Engine,
) -> None:
    _seed_happy(engine)

    prompt = _assemble(engine).system_prompt

    assert _line_after(prompt, H_SYSTEM_PROMPT) == "P"
    assert _line_after(prompt, H_SHEET) == "S"


def test_happy_path_holds_all_six_sections_in_order__S020_002_DoD1(engine: Engine) -> None:
    _seed_happy(engine)

    prompt = _assemble(engine).system_prompt

    positions = [_line_index(prompt, heading) for heading in SIX_HEADINGS]
    assert positions == sorted(positions)
    for heading, leads in LEAD_INS.items():
        heading_index = _line_index(prompt, heading)
        for lead in leads:
            assert _lines(prompt).index(_lead_line(prompt, lead)) > heading_index


def test_happy_path_forced_bodies_sit_under_their_level_headings_in_level_order__S020_002_DoD1(
    engine: Engine,
) -> None:
    _seed_happy(engine)

    prompt = _assemble(engine).system_prompt

    level_positions = [_line_index(prompt, LEVEL_HEADING[scope]) for scope in FOUR_SCOPES]
    assert level_positions == sorted(level_positions)
    assert _line_index(prompt, H_FORCED) < level_positions[0]
    for scope in FOUR_SCOPES:
        _assert_in_level(prompt, scope, HAPPY_BODIES[scope], FOUR_SCOPES)


def test_happy_path_messages_are_exactly_the_tagged_record_then_the_zone__S020_002_DoD1(
    engine: Engine,
) -> None:
    _seed_happy(engine)

    result = _assemble(engine)

    assert list(result.messages) == [
        ChatMessage(role="user", content="[partner]\nThe partner's pasted block."),
        ChatMessage(role="user", content="[my turn]\nMy own settled turn."),
        ChatMessage(role="user", content="[decision]\n((The tavern burns down tonight.))"),
        ChatMessage(role="user", content="A live zone draft from me."),
        ChatMessage(role="assistant", content="The assistant's live zone answer."),
    ]


# --- DoD-2: disabled, disabled-and-forced and searchable notes are absent ------------------


def test_only_enabled_forced_notes_reach_the_result_at_every_level__S020_002_DoD2(
    engine: Engine,
) -> None:
    memo_id = 5_100
    for scope in FOUR_SCOPES:
        for body, enabled, forced in [
            (f"keep {scope} enabled forced", True, True),
            (f"drop {scope} disabled forced", False, True),
            (f"drop {scope} disabled plain", False, False),
            (f"drop {scope} enabled searchable", True, False),
        ]:
            memo_id += 1
            _insert_memo(
                engine,
                memo_id=memo_id,
                user_id=USER_A,
                scope=scope,
                scope_id=_scope_id(scope),
                body=body,
                sort_key=memo_id,
                is_enabled=enabled,
                is_forced=forced,
            )
    _settled(engine, 4_101, "turn", "A settled turn for DoD-2.")
    _zone(engine, 4_102, "A zone row for DoD-2.")

    result = _assemble(engine)
    everything = _all_text(result)

    for scope in FOUR_SCOPES:
        _assert_in_level(result.system_prompt, scope, f"keep {scope} enabled forced", FOUR_SCOPES)
        assert f"drop {scope} disabled forced" not in everything
        assert f"drop {scope} disabled plain" not in everything
        assert f"drop {scope} enabled searchable" not in everything


# --- DoD-3: level order, then sort_key, then id -------------------------------------------


def test_forced_notes_follow_level_order_then_sort_key_then_id__S020_002_DoD3(
    engine: Engine,
) -> None:
    # (id, scope, sort_key), raw-inserted out of order; the user level's sort_keys are
    # larger than the session level's, and 5_302 / 5_303 tie on sort_key 100.
    inserts = [
        (5_303, "user", 100),
        (5_301, "user", 101),
        (5_302, "user", 100),
        (5_311, "character", 9),
        (5_312, "character", 7),
        (5_321, "setup", 3),
        (5_332, "session", 1),
        (5_331, "session", 0),
    ]
    for memo_id, scope, sort_key in inserts:
        _insert_memo(
            engine,
            memo_id=memo_id,
            user_id=USER_A,
            scope=scope,
            scope_id=_scope_id(scope),
            body=f"<<ordered note {memo_id}>>",
            sort_key=sort_key,
        )

    prompt = _assemble(engine).system_prompt

    expected = [
        ("user", 5_302),
        ("user", 5_303),
        ("user", 5_301),
        ("character", 5_312),
        ("character", 5_311),
        ("setup", 5_321),
        ("session", 5_331),
        ("session", 5_332),
    ]
    positions = [_line_index(prompt, f"<<ordered note {memo_id}>>") for _, memo_id in expected]
    assert positions == sorted(positions)
    assert len(set(positions)) == len(positions)
    for scope, memo_id in expected:
        _assert_in_level(prompt, scope, f"<<ordered note {memo_id}>>", FOUR_SCOPES)


# --- DoD-4: a sort_key swap shows on the next call ----------------------------------------


def test_swapped_sort_keys_render_in_the_new_order_on_the_next_call__S020_002_DoD4(
    engine: Engine,
) -> None:
    first, second = "<<reorder note first>>", "<<reorder note second>>"
    _insert_memo(
        engine, memo_id=5_401, user_id=USER_A, scope="character", scope_id=CHAR_A1,
        body=first, sort_key=0,
    )
    _insert_memo(
        engine, memo_id=5_402, user_id=USER_A, scope="character", scope_id=CHAR_A1,
        body=second, sort_key=1,
    )

    before = _assemble(engine).system_prompt
    assert _line_index(before, first) < _line_index(before, second)

    _update(engine, schema.memos, 5_401, sort_key=1)
    _update(engine, schema.memos, 5_402, sort_key=0)

    after = _assemble(engine).system_prompt
    assert _line_index(after, second) < _line_index(after, first)


# --- DoD-5: a session without a setup -----------------------------------------------------


def test_a_session_without_setup_has_no_setup_level_and_keeps_the_others__S020_002_DoD5(
    engine: Engine,
) -> None:
    bodies = {
        "user": "no-setup user forced",
        "character": "no-setup character forced",
        "session": "no-setup session forced",
    }
    _insert_memo(engine, memo_id=5_501, user_id=USER_A, scope="user", scope_id=USER_A,
                 body=bodies["user"])
    _insert_memo(engine, memo_id=5_502, user_id=USER_A, scope="character", scope_id=CHAR_A1,
                 body=bodies["character"])
    _insert_memo(engine, memo_id=5_503, user_id=USER_A, scope="session",
                 scope_id=SESSION_NO_SETUP, body=bodies["session"])
    # A forced setup-level note of a setup under the same character.
    _insert_memo(engine, memo_id=5_504, user_id=USER_A, scope="setup", scope_id=SETUP_A1,
                 body="foreign setup forced body")

    result = _assemble(engine, USER_A, SESSION_NO_SETUP)
    prompt = result.system_prompt

    assert not _has_line(prompt, LEVEL_HEADING["setup"])
    three = ["user", "character", "session"]
    for scope in three:
        _assert_in_level(prompt, scope, bodies[scope], three)
    assert "foreign setup forced body" not in _all_text(result)


# --- DoD-6: buried rows are absent --------------------------------------------------------


@pytest.mark.parametrize("zone_has_newer_row", [False, True])
def test_buried_rows_never_reach_the_result__S020_002_DoD6(
    engine: Engine, zone_has_newer_row: bool
) -> None:
    _settled(engine, 4_201, "turn", "The settled head turn.")
    _insert_message(
        engine, message_id=4_202, session_id=SESSION_MAIN, text="BURIED first discussion",
        related_to=4_201,
    )
    _insert_message(
        engine, message_id=4_203, session_id=SESSION_MAIN, text="BURIED second discussion",
        role="assistant", related_to=4_201,
    )
    expected = [ChatMessage(role="user", content="[my turn]\nThe settled head turn.")]
    if zone_has_newer_row:
        _zone(engine, 4_204, "A newer zone row.")
        expected.append(ChatMessage(role="user", content="A newer zone row."))

    result = _assemble(engine)

    assert list(result.messages) == expected
    assert "BURIED" not in _all_text(result)


# --- DoD-7: isolation ---------------------------------------------------------------------


def test_other_users_sessions_and_characters_never_reach_the_result__S020_002_DoD7(
    engine: Engine,
) -> None:
    # The caller's own content, which must be present.
    for offset, scope in enumerate(FOUR_SCOPES):
        _insert_memo(
            engine, memo_id=5_701 + offset, user_id=USER_A, scope=scope,
            scope_id=_scope_id(scope), body=f"own {scope} forced note",
        )
    _settled(engine, 4_701, "partner", "Own settled partner block.")
    _zone(engine, 4_702, "Own zone row.")

    # Another user's memos at this session's exact scopes and scope ids.
    for offset, scope in enumerate(FOUR_SCOPES):
        _insert_memo(
            engine, memo_id=5_711 + offset, user_id=USER_B, scope=scope,
            scope_id=_scope_id(scope), body=f"LEAK other-user {scope} forced note",
        )
    # Another session of the same character: its record, zone and forced session notes.
    _settled(engine, 4_711, "turn", "LEAK sibling settled turn", session_id=SESSION_SIBLING)
    _zone(engine, 4_712, "LEAK sibling zone row", session_id=SESSION_SIBLING)
    _insert_memo(
        engine, memo_id=5_721, user_id=USER_A, scope="session", scope_id=SESSION_SIBLING,
        body="LEAK sibling session forced note",
    )
    # Another character of the caller: its forced character-level notes.
    _insert_memo(
        engine, memo_id=5_731, user_id=USER_A, scope="character", scope_id=CHAR_A2,
        body="LEAK other-character forced note",
    )

    result = _assemble(engine)
    everything = _all_text(result)

    assert "LEAK" not in everything
    for scope in FOUR_SCOPES:
        _assert_in_level(result.system_prompt, scope, f"own {scope} forced note", FOUR_SCOPES)
    assert list(result.messages) == [
        ChatMessage(role="user", content="[partner]\nOwn settled partner block."),
        ChatMessage(role="user", content="Own zone row."),
    ]


# --- DoD-8: foreign and unknown sessions ---------------------------------------------------


def test_another_users_session_raises_session_not_found__S020_002_DoD8(engine: Engine) -> None:
    with pytest.raises(SessionNotFoundError):
        _assemble(engine, USER_B, SESSION_MAIN)
    with pytest.raises(SessionNotFoundError):
        _assemble(engine, USER_A, SESSION_B1)


def test_an_unknown_session_raises_session_not_found__S020_002_DoD8(engine: Engine) -> None:
    with pytest.raises(SessionNotFoundError):
        _assemble(engine, USER_A, UNKNOWN_SESSION_ID)


# --- DoD-9: read live ---------------------------------------------------------------------


def test_edits_between_two_calls_show_in_the_second__S020_002_DoD9(engine: Engine) -> None:
    _update(engine, schema.characters, CHAR_A1, system_prompt="PROMPT BEFORE EDIT")
    _settled(engine, 4_901, "turn", "settled text before edit")
    _zone(engine, 4_902, "zone text before edit")
    _insert_memo(engine, memo_id=5_901, user_id=USER_A, scope="user", scope_id=USER_A,
                 body="toggled forced note body", sort_key=0)
    _insert_memo(engine, memo_id=5_902, user_id=USER_A, scope="user", scope_id=USER_A,
                 body="steady forced note body", sort_key=1)

    first = _assemble(engine)
    assert _line_after(first.system_prompt, H_SYSTEM_PROMPT) == "PROMPT BEFORE EDIT"
    assert "toggled forced note body" in first.system_prompt
    assert list(first.messages) == [
        ChatMessage(role="user", content="[my turn]\nsettled text before edit"),
        ChatMessage(role="user", content="zone text before edit"),
    ]

    _update(engine, schema.messages, 4_901, text="settled text after edit")
    _update(engine, schema.messages, 4_902, text="zone text after edit")
    _update(engine, schema.characters, CHAR_A1, system_prompt="PROMPT AFTER EDIT")
    _update(engine, schema.memos, 5_901, is_enabled=False)

    second = _assemble(engine)
    everything = _all_text(second)
    assert _line_after(second.system_prompt, H_SYSTEM_PROMPT) == "PROMPT AFTER EDIT"
    assert list(second.messages) == [
        ChatMessage(role="user", content="[my turn]\nsettled text after edit"),
        ChatMessage(role="user", content="zone text after edit"),
    ]
    assert "toggled forced note body" not in everything
    assert "steady forced note body" in second.system_prompt
    assert "settled text before edit" not in everything
    assert "zone text before edit" not in everything
    assert "PROMPT BEFORE EDIT" not in everything


# --- DoD-10: configuration ----------------------------------------------------------------


def test_a_session_system_prompt_beats_the_characters__S020_002_DoD10(engine: Engine) -> None:
    _update(engine, schema.characters, CHAR_A1, system_prompt="CHARACTER LEVEL PROMPT")
    _update(engine, schema.sessions, SESSION_MAIN, system_prompt="SESSION LEVEL PROMPT")

    prompt = _assemble(engine).system_prompt

    assert _line_after(prompt, H_SYSTEM_PROMPT) == "SESSION LEVEL PROMPT"
    assert "CHARACTER LEVEL PROMPT" not in prompt


def test_with_no_system_prompt_set_the_section_is_absent__S020_002_DoD10(engine: Engine) -> None:
    prompt = _assemble(engine).system_prompt

    assert not _has_line(prompt, H_SYSTEM_PROMPT)
    assert _has_line(prompt, H_TAGS)


def test_user_languages_appear_on_the_language_lines__S020_002_DoD10(engine: Engine) -> None:
    _update(engine, schema.users, USER_A, rp_language="Japanese", preferred_language="Russian")

    prompt = _assemble(engine).system_prompt

    assert "Japanese" in _lead_line(prompt, CANDIDATES)
    assert "Russian" in _lead_line(prompt, OUT_OF_CHARACTER)


def test_a_session_rp_language_override_replaces_the_users__S020_002_DoD10(
    engine: Engine,
) -> None:
    _update(engine, schema.users, USER_A, rp_language="Japanese", preferred_language="Russian")
    _update(engine, schema.sessions, SESSION_MAIN, rp_language="French")

    prompt = _assemble(engine).system_prompt

    candidates = _lead_line(prompt, CANDIDATES)
    assert "French" in candidates
    assert "Japanese" not in candidates
    assert "Russian" in _lead_line(prompt, OUT_OF_CHARACTER)


def test_with_no_language_set_both_lines_name_english__S020_002_DoD10(engine: Engine) -> None:
    prompt = _assemble(engine).system_prompt

    assert "English" in _lead_line(prompt, CANDIDATES)
    assert "English" in _lead_line(prompt, OUT_OF_CHARACTER)


# --- DoD-11: an empty sheet ---------------------------------------------------------------


def test_an_empty_sheet_gives_no_character_sheet_section__S020_002_DoD11(engine: Engine) -> None:
    _update(engine, schema.characters, CHAR_A1, sheet="", system_prompt="Some prompt here")

    prompt = _assemble(engine).system_prompt

    assert not _has_line(prompt, H_SHEET)
    assert _line_after(prompt, H_SYSTEM_PROMPT) == "Some prompt here"


# --- DoD-12: archived session and character -----------------------------------------------


def test_an_archived_session_under_an_archived_character_assembles__S020_002_DoD12(
    engine: Engine,
) -> None:
    _update(
        engine, schema.characters, CHAR_A1, archived_at=ARCHIVED_AT,
        system_prompt="ARCHIVED CHARACTER PROMPT", sheet="ARCHIVED CHARACTER SHEET",
    )
    _update(engine, schema.sessions, SESSION_MAIN, archived_at=ARCHIVED_AT)
    _insert_memo(engine, memo_id=5_121, user_id=USER_A, scope="session",
                 scope_id=SESSION_MAIN, body="archived session forced note")
    _settled(engine, 4_121, "partner", "Archived partner block.")
    _zone(engine, 4_122, "Archived zone row.")

    result = _assemble(engine)

    assert _line_after(result.system_prompt, H_SYSTEM_PROMPT) == "ARCHIVED CHARACTER PROMPT"
    assert _line_after(result.system_prompt, H_SHEET) == "ARCHIVED CHARACTER SHEET"
    _assert_in_level(result.system_prompt, "session", "archived session forced note", FOUR_SCOPES)
    assert list(result.messages) == [
        ChatMessage(role="user", content="[partner]\nArchived partner block."),
        ChatMessage(role="user", content="Archived zone row."),
    ]


# --- DoD-13: tool rows (amended by 021 `002` DoD-8 to 021 D9: zone tool rows are replayed) --


def _shapes(context: AssembledContext) -> list[tuple[str, str, tuple[ToolCall, ...], str | None]]:
    return [
        (m.role, m.content, tuple(m.tool_calls), m.tool_call_id) for m in context.messages
    ]


def test_a_tool_zone_row_is_replayed_at_its_id_position__S020_002_DoD13__S021_002_DoD8(
    engine: Engine,
) -> None:
    """021 `002` DoD-8 / D9 — a zone tool row becomes an assistant call + a tool result."""
    _zone(engine, 4_131, "Zone row before the tool row.")
    _settled(engine, 4_132, "partner", "Partner block filed between zone rows.")
    _insert_message(
        engine,
        message_id=4_133,
        session_id=SESSION_MAIN,
        text="TOOL ROW SUMMARY TEXT",
        role="tool",
        tool_name="memo_search",
        tool_payload=json.dumps(
            {
                "call_id": "c1",
                "arguments": '{"query": "inn"}',
                "status": "ok",
                "content": "Inn is the Gull",
            }
        ),
    )
    _zone(engine, 4_134, "Assistant row after the tool row.", role="assistant")

    result = _assemble(engine)

    assert _shapes(result) == [
        ("user", "Zone row before the tool row.", (), None),
        ("user", "[partner]\nPartner block filed between zone rows.", (), None),
        (
            "assistant",
            "",
            (ToolCall(call_id="c1", name="memo_search", arguments='{"query": "inn"}'),),
            None,
        ),
        ("tool", "Inn is the Gull", (), "c1"),
        ("assistant", "Assistant row after the tool row.", (), None),
    ]
    assert "TOOL ROW SUMMARY TEXT" not in _all_text(result)


def test_a_buried_tool_row_is_absent_from_every_message__S021_002_DoD8(engine: Engine) -> None:
    """021 `002` DoD-8 / D9 / R11 / UC-038 — a tool row buried under a settled head never
    reaches context: no call, no tool message, none of its content or arguments."""
    _settled(engine, 4_141, "turn", "The settled head turn.")
    _insert_message(
        engine,
        message_id=4_142,
        session_id=SESSION_MAIN,
        text="BURIED tool summary",
        role="tool",
        related_to=4_141,
        tool_name="memo_search",
        tool_payload=json.dumps(
            {
                "call_id": "c_buried",
                "arguments": '{"query": "BURIED-ARGS"}',
                "status": "ok",
                "content": "BURIED tool content",
            }
        ),
    )
    _zone(engine, 4_143, "A newer zone row.")

    result = _assemble(engine)

    assert _shapes(result) == [
        ("user", "[my turn]\nThe settled head turn.", (), None),
        ("user", "A newer zone row.", (), None),
    ]
    assert "BURIED" not in _all_text(result)
    for message in result.messages:
        assert message.tool_call_id is None
        assert list(message.tool_calls) == []


# --- DoD-14: no compaction ----------------------------------------------------------------


def test_a_large_record_arrives_whole_in_id_order__S020_002_DoD14(engine: Engine) -> None:
    kinds = ["partner", "turn", "decision"]
    long_text = ("LONG-" + "abcdefghij" * 10_000)[:100_000]
    assert len(long_text) == 100_000
    expected: list[ChatMessage] = []
    rows = []
    for index in range(300):
        message_id = 10_000 + index
        kind = kinds[index % 3]
        text = long_text if index == 150 else f"settled row number {index:03d}."
        rows.append(
            {
                "id": message_id, "user_id": USER_A, "session_id": SESSION_MAIN,
                "role": "user", "kind": kind, "text": text, "related_to": None,
                "settled_at": TIMESTAMP, "created_at": TIMESTAMP, "updated_at": TIMESTAMP,
            }
        )
        expected.append(ChatMessage(role="user", content=_tagged(kind, text)))
    with engine.begin() as connection:
        connection.execute(schema.messages.insert(), rows)
    _zone(engine, 10_300, "Zone user row after the record.")
    _zone(engine, 10_301, "Zone assistant row after the record.", role="assistant")
    expected.append(ChatMessage(role="user", content="Zone user row after the record."))
    expected.append(
        ChatMessage(role="assistant", content="Zone assistant row after the record.")
    )

    result = _assemble(engine)

    assert len(result.messages) == 302
    assert list(result.messages) == expected
    assert result.messages[150].content == _tagged("partner", long_text)


# --- DoD-15: no transaction left open, nothing written -------------------------------------


def test_no_transaction_is_left_open_and_nothing_is_written__S020_002_DoD15(
    engine: Engine,
) -> None:
    _insert_memo(engine, memo_id=5_151, user_id=USER_A, scope="user", scope_id=USER_A,
                 body="transaction check forced note")
    _insert_memo(engine, memo_id=5_152, user_id=USER_A, scope="session",
                 scope_id=SESSION_MAIN, body="transaction check searchable", is_forced=False)
    _settled(engine, 4_151, "turn", "Transaction check settled turn.")
    _zone(engine, 4_152, "Transaction check zone row.")
    messages_before = _messages_snapshot(engine)
    memos_before = _memos_snapshot(engine)

    with engine.connect() as connection:
        assemble_context(connection, USER_A, SESSION_MAIN)
        assert not connection.in_transaction()
        connection.begin().rollback()

        with pytest.raises(SessionNotFoundError):
            assemble_context(connection, USER_B, SESSION_MAIN)
        assert not connection.in_transaction()
        connection.begin().rollback()

        with pytest.raises(SessionNotFoundError):
            assemble_context(connection, USER_A, UNKNOWN_SESSION_ID)
        assert not connection.in_transaction()
        connection.begin().rollback()

    assert _messages_snapshot(engine) == messages_before
    assert _memos_snapshot(engine) == memos_before


# --- DoD-16: source convention ------------------------------------------------------------

ALLOWED_SERVICE_IMPORTS = {
    "messages",
    "sessions",
    "characters",
    "configuration",
    "memo_chain",
    "llm.chat",
}
QUERY_BUILDERS = {"select", "insert", "update", "delete", "text"}


def _context_source() -> str:
    return inspect.getsource(context_module)


def _context_tree() -> ast.Module:
    return ast.parse(_context_source())


def _absolute_module(node: ast.ImportFrom) -> str:
    """Resolve a (possibly relative) `from` import inside the `app.services` package."""
    if node.level == 0:
        return node.module or ""
    base = "app.services".split(".")
    if node.level > 1:
        base = base[: -(node.level - 1)]
    return ".".join([*base, *([node.module] if node.module else [])])


def _imported_names(tree: ast.Module) -> list[tuple[str, str | None]]:
    """(module, imported name or None for `import x`) for every import in the tree."""
    found: list[tuple[str, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = _absolute_module(node)
            for alias in node.names:
                found.append((module, alias.name))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, None))
    return found


def _is_under(module: str, package: str) -> bool:
    return module == package or module.startswith(package + ".")


def test_context_module_imports_nothing_from_app_db_and_no_fastapi__S020_002_DoD16() -> None:
    offenders: list[str] = []
    for module, name in _imported_names(_context_tree()):
        full = module if name is None else f"{module}.{name}"
        if _is_under(module, "app.db") or _is_under(full, "app.db"):
            offenders.append(full)
        if _is_under(module, "fastapi"):
            offenders.append(full)

    assert offenders == []


def test_context_module_imports_at_most_connection_from_sqlalchemy__S020_002_DoD16() -> None:
    offenders: list[str] = []
    for module, name in _imported_names(_context_tree()):
        if _is_under(module, "sqlalchemy") and name != "Connection":
            offenders.append(f"{module}:{name}")

    assert offenders == []


def test_context_module_calls_no_query_builder__S020_002_DoD16() -> None:
    called: list[str] = []
    for node in ast.walk(_context_tree()):
        if isinstance(node, ast.Call):
            func = node.func
            name = (
                func.id if isinstance(func, ast.Name)
                else func.attr if isinstance(func, ast.Attribute)
                else None
            )
            if name in QUERY_BUILDERS:
                called.append(name)

    assert called == []


def test_context_module_names_no_view_and_no_translation__S020_002_DoD16() -> None:
    source = _context_source()

    assert "settled_entries" not in source
    assert "current_zone" not in source
    assert "translation" not in source


def test_context_module_service_imports_are_exactly_the_six__S020_002_DoD16() -> None:
    services: set[str] = set()
    for module, name in _imported_names(_context_tree()):
        if name is None:
            if _is_under(module, "app.services"):
                services.add(module.removeprefix("app.services").lstrip("."))
            continue
        if module == "app.services":
            services.add(name)
        elif _is_under(module, "app.services"):
            services.add(module.removeprefix("app.services."))

    assert services == ALLOWED_SERVICE_IMPORTS


def test_every_flag_access_sits_inside_a_memo_reach_call__S020_002_DoD16() -> None:
    tree = _context_tree()

    inside_memo_reach: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_memo_reach = (isinstance(func, ast.Name) and func.id == "memo_reach") or (
            isinstance(func, ast.Attribute) and func.attr == "memo_reach"
        )
        if not is_memo_reach:
            continue
        for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
            for inner in ast.walk(argument):
                inside_memo_reach.add(id(inner))

    stray = [
        f"line {node.lineno}: .{node.attr}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr in {"is_enabled", "is_forced"}
        and id(node) not in inside_memo_reach
    ]
    assert stray == []
