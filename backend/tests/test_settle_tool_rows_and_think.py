"""Tests for `app/services/settle.py` under tool rows and `<think>` — feature 021, step 001.

Every expected value comes from `docs/plans/021.compose-loop-and-tools/001.tool-rows-and-settle.md`
(Interface intent + Definition of done), `001.context.md` and the feature `context.md`
(**D4** strip rule and worked examples, **D7** tool-row columns, **D8** settle head rule,
R11, R12, 012's settle behaviour as already pinned by `tests/test_settle_service.py`).
Bindings: `settle(connection, user_id, session_id) -> SettleResult` and `reopen(...)`
(signatures unchanged, `status.md` `## Skeleton` Step 001).

DoD-6, 7, 8, 10, 11, 12, 13 are covered here. Each test name ends `__S021_001_DoD<n>`.

Seeding: a file-local engine with `schema.metadata.create_all`, raw-inserted users,
characters and sessions, and **every `messages` row raw-inserted** (tool rows included, with
`role='tool'`, `tool_name` and `tool_payload` set) with explicit ascending ids, so nothing
here depends on `append_tool_message` (001.context.md).
"""

from typing import Any

import pytest
from sqlalchemy import Engine, select

from app.db import schema
from app.errors import ZoneEmptyError
from app.roles import Role
from app.services.settle import ReopenResult, SettleResult, reopen, settle

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
SEEDED_SETTLED_AT = "2025-12-31T00:00:00.000000+00:00"

USER_A = 101
USER_B = 202

CHAR_A1 = 1_001
CHAR_B1 = 2_001

SESSION_A = 5_001
SESSION_B = 6_001

TOOL_NAME = "memo_search"
#: A D7-shaped ok payload (compact JSON).
TOOL_PAYLOAD = (
    '{"call_id":"call_1","arguments":"{\\"query\\":\\"inn\\"}","status":"ok",'
    '"content":"The inn is called The Gilded Goose."}'
)
TOOL_SUMMARY = "1 memo found"


# --- seeding -----------------------------------------------------------------------------


def _insert_user(engine: Engine, *, user_id: int, username: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.users.insert().values(
                id=user_id,
                username=username,
                password_hash="not-a-real-hash",
                role=Role.ROLEPLAYER,
                is_enabled=True,
                rp_language=None,
                preferred_language=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_character(engine: Engine, *, character_id: int, user_id: int, name: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.characters.insert().values(
                id=character_id,
                user_id=user_id,
                name=name,
                sheet="",
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_session(engine: Engine, *, session_id: int, user_id: int, character_id: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.insert().values(
                id=session_id,
                user_id=user_id,
                character_id=character_id,
                setup_id=None,
                last_used_at=TIMESTAMP,
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_message(
    engine: Engine,
    *,
    message_id: int,
    text: str,
    role: str = "user",
    user_id: int = USER_A,
    session_id: int = SESSION_A,
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
                tool_name=tool_name,
                tool_payload=tool_payload,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_zone(engine: Engine, message_id: int, text: str, role: str = "user") -> None:
    """A current-zone user / assistant row."""
    _insert_message(engine, message_id=message_id, text=text, role=role)


def _insert_tool(engine: Engine, message_id: int, text: str = TOOL_SUMMARY) -> None:
    """A current-zone tool row (D7 columns)."""
    _insert_message(
        engine,
        message_id=message_id,
        text=text,
        role="tool",
        tool_name=TOOL_NAME,
        tool_payload=TOOL_PAYLOAD,
    )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="alice")
    _insert_user(db_engine, user_id=USER_B, username="bob")
    _insert_character(db_engine, character_id=CHAR_A1, user_id=USER_A, name="Aria")
    _insert_character(db_engine, character_id=CHAR_B1, user_id=USER_B, name="Bob's own")
    _insert_session(db_engine, session_id=SESSION_A, user_id=USER_A, character_id=CHAR_A1)
    _insert_session(db_engine, session_id=SESSION_B, user_id=USER_B, character_id=CHAR_B1)
    return db_engine


# --- wrappers and read-back ----------------------------------------------------------------


def _settle(engine: Engine, user_id: int = USER_A, session_id: int = SESSION_A) -> SettleResult:
    with engine.connect() as connection:
        return settle(connection, user_id, session_id)


def _reopen(engine: Engine, user_id: int = USER_A, session_id: int = SESSION_A) -> ReopenResult:
    with engine.connect() as connection:
        return reopen(connection, user_id, session_id)


def _row(engine: Engine, message_id: int) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(
            select(schema.messages).where(schema.messages.c.id == message_id)
        ).one()
    return dict(row._mapping)


def _messages_snapshot(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(select(schema.messages).order_by(schema.messages.c.id)).all()
    return [dict(row._mapping) for row in rows]


def _sessions_snapshot(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(select(schema.sessions).order_by(schema.sessions.c.id)).all()
    return [dict(row._mapping) for row in rows]


def _zone_ids(engine: Engine, user_id: int = USER_A, session_id: int = SESSION_A) -> list[int]:
    statement = schema.current_zone.where(
        schema.messages.c.session_id == session_id,
        schema.messages.c.user_id == user_id,
    ).order_by(schema.messages.c.id)
    with engine.connect() as connection:
        return [int(row.id) for row in connection.execute(statement)]


def _record(
    engine: Engine, user_id: int = USER_A, session_id: int = SESSION_A
) -> list[tuple[int, str | None]]:
    statement = schema.settled_entries.where(
        schema.messages.c.session_id == session_id,
        schema.messages.c.user_id == user_id,
    ).order_by(schema.messages.c.id)
    with engine.connect() as connection:
        return [(int(row.id), row.kind) for row in connection.execute(statement)]


# --- DoD-6: [user, assistant, tool] -------------------------------------------------------


def test_settle_skips_a_trailing_tool_row_and_heads_on_the_assistant__S021_001_DoD6(
    engine: Engine,
) -> None:
    """DoD-6 — D8 / US-126.AC-1: the assistant row is the settled head; the user row and the
    tool row both point at it."""
    _insert_zone(engine, 11, "My draft.", role="user")
    _insert_zone(engine, 12, "The assistant's version.", role="assistant")
    _insert_tool(engine, 13)

    result = _settle(engine)

    assert result.entry_id == 12
    assert sorted(result.buried_ids) == [11, 13]
    head = _row(engine, 12)
    assert head["settled_at"] is not None
    assert head["related_to"] is None
    assert head["text"] == "The assistant's version."
    for buried_id in (11, 13):
        buried = _row(engine, buried_id)
        assert buried["related_to"] == 12
        assert buried["settled_at"] is None
    assert _row(engine, 13)["role"] == "tool"
    assert _row(engine, 13)["text"] == TOOL_SUMMARY
    assert _zone_ids(engine) == []
    assert [entry_id for entry_id, _ in _record(engine)] == [12]


def test_settle_buries_a_tool_row_between_user_and_assistant__S021_001_DoD6(
    engine: Engine,
) -> None:
    """DoD-6 — D8: every zone row other than the head, tool rows included, is buried."""
    _insert_zone(engine, 21, "My draft.", role="user")
    _insert_tool(engine, 22)
    _insert_zone(engine, 23, "The reply after the tool.", role="assistant")

    result = _settle(engine)

    assert result.entry_id == 23
    assert sorted(result.buried_ids) == [21, 22]
    assert _row(engine, 22)["related_to"] == 23
    assert _row(engine, 21)["related_to"] == 23
    assert _zone_ids(engine) == []


# --- DoD-7: [user, tool, tool] ------------------------------------------------------------

USER_HEAD_TEXT = "  She  walks.\n\nShe sits.  "


def test_settle_heads_on_the_user_row_before_two_tool_rows__S021_001_DoD7(
    engine: Engine,
) -> None:
    """DoD-7 — D8 / US-135.AC-1: the user row is the head, settled as a turn with its text
    as-is; both tool rows are buried under it."""
    _insert_zone(engine, 31, USER_HEAD_TEXT, role="user")
    _insert_tool(engine, 32)
    _insert_tool(engine, 33)

    result = _settle(engine)

    assert result.entry_id == 31
    assert result.kind == "turn"
    assert sorted(result.buried_ids) == [32, 33]
    head = _row(engine, 31)
    assert head["kind"] == "turn"
    assert head["text"] == USER_HEAD_TEXT
    assert head["settled_at"] is not None
    for buried_id in (32, 33):
        buried = _row(engine, buried_id)
        assert buried["related_to"] == 31
        assert buried["settled_at"] is None
    assert _zone_ids(engine) == []
    assert _record(engine) == [(31, "turn")]


# --- DoD-8: only tool rows ----------------------------------------------------------------


def test_settle_over_only_tool_rows_raises_zone_empty__S021_001_DoD8(engine: Engine) -> None:
    """DoD-8 — D8 / R11: a zone of only tool rows counts as empty; nothing changes."""
    _insert_tool(engine, 41)
    _insert_tool(engine, 42)
    messages_before = _messages_snapshot(engine)
    sessions_before = _sessions_snapshot(engine)

    with pytest.raises(ZoneEmptyError):
        _settle(engine)

    assert _messages_snapshot(engine) == messages_before
    assert _sessions_snapshot(engine) == sessions_before
    assert _zone_ids(engine) == [41, 42]


def test_settle_over_one_tool_row_after_a_settled_entry_raises_zone_empty__S021_001_DoD8(
    engine: Engine,
) -> None:
    """DoD-8 — a settled record before a lone zone tool row: still `zone_empty`, no change."""
    _insert_message(
        engine, message_id=43, text="The partner's block.", kind="partner", settled_at=SEEDED_SETTLED_AT
    )
    _insert_tool(engine, 44)
    messages_before = _messages_snapshot(engine)
    sessions_before = _sessions_snapshot(engine)

    with pytest.raises(ZoneEmptyError):
        _settle(engine)

    assert _messages_snapshot(engine) == messages_before
    assert _sessions_snapshot(engine) == sessions_before


# --- DoD-10: assistant head is think-stripped before classification -----------------------


def test_settle_strips_think_then_files_a_decision__S021_001_DoD10(engine: Engine) -> None:
    """DoD-10 — D4 / R12 / US-129.AC-1: `<think>x\\ny</think>\\n((ooc))` → decision `((ooc))`."""
    _insert_zone(engine, 51, "Go on.", role="user")
    _insert_zone(engine, 52, "<think>x\ny</think>\n((ooc))", role="assistant")

    result = _settle(engine)

    assert result.entry_id == 52
    assert result.kind == "decision"
    head = _row(engine, 52)
    assert head["kind"] == "decision"
    assert head["text"] == "((ooc))"
    assert _record(engine) == [(52, "decision")]


def test_settle_strips_think_then_files_a_turn__S021_001_DoD10(engine: Engine) -> None:
    """DoD-10 — D4: `<think>plan</think>\\n\\nShe nods.` → turn `She nods.`."""
    _insert_zone(engine, 53, "<think>plan</think>\n\nShe nods.", role="assistant")

    result = _settle(engine)

    assert result.entry_id == 53
    assert result.kind == "turn"
    head = _row(engine, 53)
    assert head["kind"] == "turn"
    assert head["text"] == "She nods."


def test_settle_strips_think_from_an_assistant_head_followed_by_a_tool_row__S021_001_DoD10(
    engine: Engine,
) -> None:
    """DoD-10 with D8 — the assistant head found past a trailing tool row is still
    think-stripped."""
    _insert_zone(engine, 54, "<think>plan</think>\n\nShe nods.", role="assistant")
    _insert_tool(engine, 55)

    result = _settle(engine)

    assert result.entry_id == 54
    assert result.kind == "turn"
    assert _row(engine, 54)["text"] == "She nods."


# --- DoD-11: a user head is never think-stripped ------------------------------------------


def test_settle_keeps_think_in_a_user_head__S021_001_DoD11(engine: Engine) -> None:
    """DoD-11 — D4: user text is taken literally; `<think>a</think> b` settles as-is."""
    _insert_zone(engine, 61, "<think>a</think> b", role="user")

    result = _settle(engine)

    assert result.entry_id == 61
    assert result.kind == "turn"
    assert _row(engine, 61)["text"] == "<think>a</think> b"


# --- DoD-12: an assistant head without a think block is 012's behaviour ---------------------


@pytest.mark.parametrize(
    ("text", "expected_kind", "expected_text"),
    [
        ("  She  walks.\n\n\n\nShe sits.  ", "turn", "  She  walks.\n\n\n\nShe sits.  "),
        ("She walks. ((be dramatic)) Then sits.", "turn", "She walks. Then sits."),
        ("((Let's skip to the next morning))", "decision", "((Let's skip to the next morning))"),
        ("a </think> b", "turn", "a </think> b"),
    ],
    ids=["whitespace_kept", "fragment_stripped", "decision_verbatim", "stray_close_kept"],
)
def test_settle_of_an_assistant_head_without_think_is_unchanged__S021_001_DoD12(
    engine: Engine, text: str, expected_kind: str, expected_text: str
) -> None:
    """DoD-12 — D4 / R12: no think block → 012's settle exactly (whitespace untouched,
    fragments stripped from a turn, a decision verbatim)."""
    _insert_zone(engine, 71, text, role="assistant")

    result = _settle(engine)

    assert result.entry_id == 71
    assert result.kind == expected_kind
    head = _row(engine, 71)
    assert head["kind"] == expected_kind
    assert head["text"] == expected_text


# --- DoD-13: re-open brings tool rows back ------------------------------------------------


def test_reopen_returns_a_buried_tool_row_with_its_group__S021_001_DoD13(engine: Engine) -> None:
    """DoD-13 — R11 / D8: after settling [user, tool, assistant, tool], re-open returns the
    head and every buried row, both tool rows included, to the zone."""
    _insert_zone(engine, 81, "My draft.", role="user")
    _insert_tool(engine, 82)
    _insert_zone(engine, 83, "The reply.", role="assistant")
    _insert_tool(engine, 84)
    settled = _settle(engine)
    assert settled.entry_id == 83

    result = _reopen(engine)

    assert result.reopened_id == 83
    assert sorted(result.restored_ids) == [81, 82, 84]
    assert _zone_ids(engine) == [81, 82, 83, 84]
    for message_id in (81, 82, 83, 84):
        row = _row(engine, message_id)
        assert row["related_to"] is None
        assert row["settled_at"] is None
        assert row["kind"] is None
    tool_row = _row(engine, 82)
    assert tool_row["role"] == "tool"
    assert tool_row["tool_name"] == TOOL_NAME
    assert tool_row["tool_payload"] == TOOL_PAYLOAD
    assert _record(engine) == []
