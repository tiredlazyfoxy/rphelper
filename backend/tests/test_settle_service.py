"""Tests for `app/services/settle.py` — feature 012, step 003 (DoD-7..23).

Every expected value comes from `docs/plans/012.messages-and-settle/003.parser-and-settle.md`
(its Interface intent and Definition of done), from `003.context.md` ("The parser, as
spec", the settle / re-open statement sequences, "Test seeding") and from the feature
`context.md` (the four states, **D3**, **D8**, **D10**, **D11**, **D16**, R5, R6, R11,
R12, "Test conventions"). Each test name ends `__S012_003_DoD<n>` with the DoD item it
covers.

Seeding: a file-local `engine` fixture applies the registry with
`schema.metadata.create_all` and raw-inserts two users, a character and sessions each.
**Every `messages` row is a raw insert** with an explicitly chosen ascending id, so this
file does not depend on step 002's service. One connection per service call. Stream
state is read back through the named selectables `current_zone` / `settled_entries`
narrowed by session and owner, and individual rows through the raw table (test-side only).

Timestamps are asserted by their fixed-width shape and by equality / non-decrease, never
by exact value; ordering is asserted by integer id.

Amended by feature 024, step 005 (`docs/plans/024.embedding-lifecycle/005.record-keeping-paths.md`,
DoD-9): DoD-23's import guard below is **narrowed** to permit `app.services.session_index`,
the module settle and re-open now reach their degraded `session_vec` refresh through. That is
an approved deviation, cited at the guard. No behavioural assertion in this file changed: the
two results' new `search_coverage_incomplete` field is read nowhere here, no result is compared
as a whole object, and with no model designated every settle and re-open still succeeds (the
record-keeping posture degrades, it does not fail — `context.md` D8).
"""

import ast
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, select, update

from app.db import schema
from app.errors import (
    NothingToReopenError,
    SessionNotFoundError,
    ZoneEmptyError,
    ZoneNotEmptyError,
)
from app.roles import Role
from app.services import settle as settle_module
from app.services.settle import ReopenResult, SettleResult, reopen, settle

#: The seeded instant — older than any instant an operation stamps today.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
#: An earlier instant for settled / partner rows seeded raw.
SEEDED_SETTLED_AT = "2025-12-31T00:00:00.000000+00:00"
ARCHIVED_AT = "2026-02-01T00:00:00.000000+00:00"

USER_A = 101
USER_B = 202

CHAR_A1 = 1_001
CHAR_B1 = 2_001

SESSION_A = 5_001
SESSION_A2 = 5_002
SESSION_B = 6_001

#: A session id that belongs to nobody.
UNKNOWN_SESSION_ID = 7_777_777_777

#: `YYYY-MM-DDTHH:MM:SS.ffffff+00:00` — the fixed-width form.
FIXED_WIDTH_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00$")


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
    user_id: int = USER_A,
    session_id: int = SESSION_A,
    role: str = "user",
    kind: str | None = None,
    related_to: int | None = None,
    settled_at: str | None = None,
) -> None:
    """Raw-insert one `messages` row in a chosen state (003.context.md "Test seeding")."""
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
            )
        )


def _insert_zone(engine: Engine, message_id: int, text: str, **overrides: Any) -> None:
    """A current-zone row: `related_to`, `settled_at`, `kind` all NULL."""
    _insert_message(engine, message_id=message_id, text=text, **overrides)


def _insert_partner(engine: Engine, message_id: int, text: str, **overrides: Any) -> None:
    """A born-settled partner row: `kind='partner'`, `settled_at` set (US-121)."""
    _insert_message(
        engine,
        message_id=message_id,
        text=text,
        kind="partner",
        settled_at=SEEDED_SETTLED_AT,
        **overrides,
    )


def _archive(engine: Engine, session_id: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            update(schema.sessions)
            .where(schema.sessions.c.id == session_id)
            .values(archived_at=ARCHIVED_AT)
        )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database: the registry, two owners, a character and sessions each."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="alice")
    _insert_user(db_engine, user_id=USER_B, username="bob")
    _insert_character(db_engine, character_id=CHAR_A1, user_id=USER_A, name="Aria")
    _insert_character(db_engine, character_id=CHAR_B1, user_id=USER_B, name="Bob's own")
    _insert_session(db_engine, session_id=SESSION_A, user_id=USER_A, character_id=CHAR_A1)
    _insert_session(db_engine, session_id=SESSION_A2, user_id=USER_A, character_id=CHAR_A1)
    _insert_session(db_engine, session_id=SESSION_B, user_id=USER_B, character_id=CHAR_B1)
    return db_engine


# --- service call wrappers (one connection per call) -------------------------------------


def _settle(engine: Engine, user_id: int = USER_A, session_id: int = SESSION_A) -> SettleResult:
    with engine.connect() as connection:
        return settle(connection, user_id, session_id)


def _reopen(engine: Engine, user_id: int = USER_A, session_id: int = SESSION_A) -> ReopenResult:
    with engine.connect() as connection:
        return reopen(connection, user_id, session_id)


# --- read-back helpers (test side) --------------------------------------------------------


def _zone_ids(engine: Engine, user_id: int = USER_A, session_id: int = SESSION_A) -> list[int]:
    """The session's current zone through the `current_zone` selectable, id ascending."""
    statement = schema.current_zone.where(
        schema.messages.c.session_id == session_id,
        schema.messages.c.user_id == user_id,
    ).order_by(schema.messages.c.id)
    with engine.connect() as connection:
        return [int(row.id) for row in connection.execute(statement)]


def _record(
    engine: Engine, user_id: int = USER_A, session_id: int = SESSION_A
) -> list[tuple[int, str | None]]:
    """The session's record through `settled_entries`: (id, kind), id ascending."""
    statement = schema.settled_entries.where(
        schema.messages.c.session_id == session_id,
        schema.messages.c.user_id == user_id,
    ).order_by(schema.messages.c.id)
    with engine.connect() as connection:
        return [(int(row.id), row.kind) for row in connection.execute(statement)]


def _record_ids(engine: Engine, user_id: int = USER_A, session_id: int = SESSION_A) -> list[int]:
    return [message_id for message_id, _ in _record(engine, user_id, session_id)]


def _row(engine: Engine, message_id: int) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(
            select(schema.messages).where(schema.messages.c.id == message_id)
        ).one()
    return dict(row._mapping)


def _messages_snapshot(engine: Engine) -> list[dict[str, Any]]:
    """Every `messages` row, every column, id ascending."""
    with engine.connect() as connection:
        rows = connection.execute(select(schema.messages).order_by(schema.messages.c.id)).all()
    return [dict(row._mapping) for row in rows]


def _ids_and_created(engine: Engine) -> dict[int, str]:
    return {int(row["id"]): row["created_at"] for row in _messages_snapshot(engine)}


def _session(engine: Engine, session_id: int = SESSION_A) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(
            select(schema.sessions).where(schema.sessions.c.id == session_id)
        ).one()
    return dict(row._mapping)


def _sessions_snapshot(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(select(schema.sessions).order_by(schema.sessions.c.id)).all()
    return [dict(row._mapping) for row in rows]


def _settle_group(engine: Engine, ids_and_texts: list[tuple[int, str]]) -> SettleResult:
    """Raw-insert a zone of the given rows in session A and settle it."""
    for message_id, text in ids_and_texts:
        _insert_zone(engine, message_id, text)
    return _settle(engine)


# =========================================================================================
# Settle
# =========================================================================================

# --- DoD-7: empty zone --------------------------------------------------------------------


def test_settle_on_a_new_session_raises_zone_empty__S012_003_DoD7(engine: Engine) -> None:
    """DoD-7 — a session with no rows: `ZoneEmptyError`, nothing written."""
    messages_before = _messages_snapshot(engine)
    sessions_before = _sessions_snapshot(engine)

    with pytest.raises(ZoneEmptyError):
        _settle(engine)

    assert _messages_snapshot(engine) == messages_before
    assert _sessions_snapshot(engine) == sessions_before


def test_settle_on_a_session_whose_rows_are_all_settled_raises_zone_empty__S012_003_DoD7(
    engine: Engine,
) -> None:
    """DoD-7 — a session whose only rows are settled (a partner row and a settled turn):
    `ZoneEmptyError`; no `messages` row and no session column changes."""
    _insert_partner(engine, 11, "The partner's block.")
    _insert_message(engine, message_id=12, text="My turn.", kind="turn", settled_at=TIMESTAMP)
    messages_before = _messages_snapshot(engine)
    sessions_before = _sessions_snapshot(engine)

    with pytest.raises(ZoneEmptyError):
        _settle(engine)

    assert _messages_snapshot(engine) == messages_before
    assert _sessions_snapshot(engine) == sessions_before


# --- DoD-8: one roleplayer row -----------------------------------------------------------

LONE_TURN_TEXT = "  She  walks.\n\n\n\nShe sits.  "


def test_settle_a_lone_roleplayer_row_files_it_as_a_turn__S012_003_DoD8(engine: Engine) -> None:
    """DoD-8 — US-031.AC-1 / US-034.AC-1 / US-135.AC-1 / US-127: the one zone row becomes
    the settled turn, text byte-for-byte unchanged, id and created_at kept; the zone is
    empty and the record holds exactly that row."""
    _insert_zone(engine, 21, LONE_TURN_TEXT, role="user")
    before = _row(engine, 21)

    result = _settle(engine)

    assert result.entry_id == 21
    assert result.kind == "turn"
    assert result.buried_ids == []

    after = _row(engine, 21)
    assert after["settled_at"] is not None
    assert after["kind"] == "turn"
    assert after["related_to"] is None
    assert after["text"] == LONE_TURN_TEXT
    assert after["id"] == before["id"] == 21
    assert after["created_at"] == before["created_at"]
    assert after["role"] == "user"

    assert _zone_ids(engine) == []
    assert _record(engine) == [(21, "turn")]


# --- DoD-9: roleplayer then assistant -----------------------------------------------------


def test_settle_takes_the_last_row_even_when_it_is_the_assistants__S012_003_DoD9(
    engine: Engine,
) -> None:
    """DoD-9 — US-126.AC-1 / R11: zone = roleplayer row, assistant row; the assistant row
    is the head and its text is the settled text; the roleplayer row is buried under it."""
    _insert_zone(engine, 31, "My draft.", role="user")
    _insert_zone(engine, 32, "The assistant's version.", role="assistant")

    result = _settle(engine)

    assert result.entry_id == 32
    assert result.buried_ids == [31]

    head = _row(engine, 32)
    assert head["text"] == "The assistant's version."
    assert head["settled_at"] is not None
    assert head["related_to"] is None

    buried = _row(engine, 31)
    assert buried["related_to"] == 32
    assert buried["settled_at"] is None
    assert buried["text"] == "My draft."

    assert 31 not in _zone_ids(engine)
    assert 31 not in _record_ids(engine)
    assert _zone_ids(engine) == []
    assert _record_ids(engine) == [32]


# --- DoD-10: assistant then roleplayer; four rows -----------------------------------------


def test_settle_takes_the_roleplayer_row_when_it_is_last__S012_003_DoD10(engine: Engine) -> None:
    """DoD-10 — US-126.AC-2: zone = assistant row, roleplayer row; the roleplayer row is
    the head and the assistant row is buried."""
    _insert_zone(engine, 41, "The assistant's suggestion.", role="assistant")
    _insert_zone(engine, 42, "What I actually wrote.", role="user")

    result = _settle(engine)

    assert result.entry_id == 42
    assert result.buried_ids == [41]
    assert _row(engine, 42)["text"] == "What I actually wrote."
    assert _row(engine, 41)["related_to"] == 42
    assert _row(engine, 41)["settled_at"] is None
    assert _record_ids(engine) == [42]
    assert _zone_ids(engine) == []


def test_settle_four_rows_buries_the_three_earlier_ones__S012_003_DoD10(engine: Engine) -> None:
    """DoD-10 — four zone rows: `buried_ids` is the three earlier ids ascending, each
    pointing at the head."""
    _insert_zone(engine, 51, "first", role="user")
    _insert_zone(engine, 52, "second", role="assistant")
    _insert_zone(engine, 53, "third", role="user")
    _insert_zone(engine, 54, "fourth", role="assistant")

    result = _settle(engine)

    assert result.entry_id == 54
    assert result.buried_ids == [51, 52, 53]
    for buried_id in (51, 52, 53):
        row = _row(engine, buried_id)
        assert row["related_to"] == 54
        assert row["settled_at"] is None
    assert _record_ids(engine) == [54]
    assert _zone_ids(engine) == []


# --- DoD-11: decisions --------------------------------------------------------------------


def test_settle_a_wholly_parenthesised_head_files_a_decision__S012_003_DoD11(
    engine: Engine,
) -> None:
    """DoD-11 — US-129.AC-1 / US-122 precondition: kind `decision`, text unchanged, and
    `settled_entries` returns it with kind `decision`."""
    decision_text = "((Let's skip to the next morning))"
    _insert_zone(engine, 61, decision_text)

    result = _settle(engine)

    assert result.entry_id == 61
    assert result.kind == "decision"
    head = _row(engine, 61)
    assert head["kind"] == "decision"
    assert head["text"] == decision_text
    assert _record(engine) == [(61, "decision")]


def test_settle_a_decision_keeps_its_text_verbatim__S012_003_DoD11(engine: Engine) -> None:
    """DoD-11 — D8: `"  ((a)) prose ((b))\\n"` is a decision stored verbatim, outer
    whitespace and both fragments kept."""
    decision_text = "  ((a)) prose ((b))\n"
    _insert_zone(engine, 62, decision_text)

    result = _settle(engine)

    assert result.kind == "decision"
    head = _row(engine, 62)
    assert head["kind"] == "decision"
    assert head["text"] == decision_text


# --- DoD-12: turns are stripped, buried rows are not --------------------------------------


def test_settle_strips_fragments_from_a_turn_head_only__S012_003_DoD12(engine: Engine) -> None:
    """DoD-12 — US-130.AC-1 / R12: the turn head's fragment is stripped; a buried row
    containing `((x))` keeps its text unchanged."""
    buried_text = "An earlier draft ((x)) with a note."
    _insert_zone(engine, 71, buried_text)
    _insert_zone(engine, 72, "She walks. ((be dramatic)) Then sits.")

    result = _settle(engine)

    assert result.entry_id == 72
    assert result.kind == "turn"
    head = _row(engine, 72)
    assert head["kind"] == "turn"
    assert head["text"] == "She walks. Then sits."
    assert _row(engine, 71)["text"] == buried_text


# --- DoD-13: two turns running ------------------------------------------------------------


def test_two_turns_running_land_in_the_record_in_order__S012_003_DoD13(engine: Engine) -> None:
    """DoD-13 — UC-031: settle, raw-insert a new zone row, settle again; two `turn` rows
    in ascending id order, no partner entry between them, the zone empty."""
    _insert_zone(engine, 81, "My first turn.")
    first = _settle(engine)
    _insert_zone(engine, 82, "My second turn.")
    second = _settle(engine)

    assert first.entry_id == 81
    assert second.entry_id == 82
    assert second.buried_ids == []
    assert _record(engine) == [(81, "turn"), (82, "turn")]
    assert _zone_ids(engine) == []


# --- DoD-14: one instant ------------------------------------------------------------------


def test_settle_stamps_one_instant_everywhere__S012_003_DoD14(engine: Engine) -> None:
    """DoD-14 — D3: head `settled_at` / `updated_at`, every buried row's `updated_at`, and
    the session's `last_used_at` / `updated_at` are one instant."""
    _insert_zone(engine, 91, "one")
    _insert_zone(engine, 92, "two")
    _insert_zone(engine, 93, "three")

    _settle(engine)

    head = _row(engine, 93)
    instant = head["settled_at"]
    assert isinstance(instant, str)
    assert FIXED_WIDTH_TIMESTAMP.match(instant)
    assert instant > TIMESTAMP
    assert head["updated_at"] == instant
    assert _row(engine, 91)["updated_at"] == instant
    assert _row(engine, 92)["updated_at"] == instant
    session = _session(engine)
    assert session["last_used_at"] == instant
    assert session["updated_at"] == instant


def test_settle_bumps_only_the_addressed_session__S012_003_DoD14(engine: Engine) -> None:
    """DoD-14 — the bump lands on the settled session alone."""
    _insert_zone(engine, 95, "one")
    other_before = _session(engine, SESSION_A2)

    _settle(engine)

    assert _session(engine, SESSION_A2) == other_before


# =========================================================================================
# Re-open
# =========================================================================================

# --- DoD-15: re-open restores the group ---------------------------------------------------


def test_reopen_restores_the_group_to_the_zone__S012_003_DoD15(engine: Engine) -> None:
    """DoD-15 — US-041.AC-1 / US-128.AC-1 / D10 / R12: after settling a three-row zone,
    re-open with the zone empty brings all three back in id order; the record no longer
    holds the head; the head keeps the stripped text."""
    _insert_zone(engine, 101, "first draft")
    _insert_zone(engine, 102, "second draft", role="assistant")
    _insert_zone(engine, 103, "She walks. ((x)) Then sits.")
    settled = _settle(engine)
    assert settled.entry_id == 103

    result = _reopen(engine)

    assert result.reopened_id == 103
    assert result.restored_ids == [101, 102]
    assert _zone_ids(engine) == [101, 102, 103]
    for message_id in (101, 102, 103):
        row = _row(engine, message_id)
        assert row["related_to"] is None
        assert row["settled_at"] is None
        assert row["kind"] is None
    assert 103 not in _record_ids(engine)
    assert _record_ids(engine) == []
    assert _row(engine, 103)["text"] == "She walks. Then sits."


def test_reopen_leaves_earlier_record_entries_in_place__S012_003_DoD15(engine: Engine) -> None:
    """DoD-15 — only the last group returns; an earlier partner entry stays recorded."""
    _insert_partner(engine, 104, "Partner block.")
    _insert_zone(engine, 105, "draft")
    _insert_zone(engine, 106, "final")
    _settle(engine)

    result = _reopen(engine)

    assert result.reopened_id == 106
    assert result.restored_ids == [105]
    assert _record(engine) == [(104, "partner")]
    assert _zone_ids(engine) == [105, 106]


# --- DoD-16: round trip -------------------------------------------------------------------


def test_settle_reopen_settle_round_trip_is_stable__S012_003_DoD16(engine: Engine) -> None:
    """DoD-16 — R11 "ids never move": settle → reopen → settle gives the same result as
    the first settle, and no row's id or created_at changes at any point."""
    _insert_zone(engine, 111, "one", role="user")
    _insert_zone(engine, 112, "two", role="assistant")
    _insert_zone(engine, 113, "three", role="user")
    identity = _ids_and_created(engine)

    first = _settle(engine)
    assert _ids_and_created(engine) == identity
    _reopen(engine)
    assert _ids_and_created(engine) == identity
    second = _settle(engine)
    assert _ids_and_created(engine) == identity

    assert second.entry_id == first.entry_id == 113
    assert second.kind == first.kind
    assert second.buried_ids == first.buried_ids == [111, 112]


# --- DoD-17: zone not empty ---------------------------------------------------------------


def test_reopen_with_a_zone_row_raises_zone_not_empty__S012_003_DoD17(engine: Engine) -> None:
    """DoD-17 — US-042.AC-1 / US-128.AC-2: a settled group then one new zone row; re-open
    is refused and nothing moves."""
    _settle_group(engine, [(121, "draft"), (122, "final")])
    _insert_zone(engine, 123, "A new zone message.")
    messages_before = _messages_snapshot(engine)
    sessions_before = _sessions_snapshot(engine)

    with pytest.raises(ZoneNotEmptyError):
        _reopen(engine)

    assert _messages_snapshot(engine) == messages_before
    assert _sessions_snapshot(engine) == sessions_before
    head = _row(engine, 122)
    assert head["settled_at"] is not None
    assert _row(engine, 121)["related_to"] == 122
    assert _zone_ids(engine) == [123]


# --- DoD-18: nothing to re-open -----------------------------------------------------------


def _state_no_rows(engine: Engine) -> None:
    del engine


def _state_lone_settled_turn(engine: Engine) -> None:
    _insert_zone(engine, 131, "A lone turn.")
    _settle(engine)


def _state_lone_decision(engine: Engine) -> None:
    _insert_zone(engine, 132, "((Let's skip ahead))")
    _settle(engine)


def _state_last_is_born_settled_partner(engine: Engine) -> None:
    _insert_partner(engine, 133, "The partner's block.")


def _state_group_then_partner(engine: Engine) -> None:
    _settle_group(engine, [(134, "draft"), (135, "final")])
    _insert_partner(engine, 136, "The partner's reply.")


NOTHING_TO_REOPEN_STATES: list[tuple[str, Callable[[Engine], None]]] = [
    ("no_rows", _state_no_rows),
    ("lone_settled_turn", _state_lone_settled_turn),
    ("lone_decision", _state_lone_decision),
    ("last_is_born_settled_partner", _state_last_is_born_settled_partner),
    ("group_then_partner", _state_group_then_partner),
]


@pytest.mark.parametrize(
    "build",
    [build for _, build in NOTHING_TO_REOPEN_STATES],
    ids=[name for name, _ in NOTHING_TO_REOPEN_STATES],
)
def test_reopen_raises_nothing_to_reopen_and_changes_nothing__S012_003_DoD18(
    engine: Engine, build: Callable[[Engine], None]
) -> None:
    """DoD-18 — D10 / R11 / UC-037: with no settled row, or a last settled row that has no
    group under it, re-open is refused and nothing changes."""
    build(engine)
    messages_before = _messages_snapshot(engine)
    sessions_before = _sessions_snapshot(engine)

    with pytest.raises(NothingToReopenError):
        _reopen(engine)

    assert _messages_snapshot(engine) == messages_before
    assert _sessions_snapshot(engine) == sessions_before


def test_an_earlier_group_behind_a_partner_row_stays_buried__S012_003_DoD18(
    engine: Engine,
) -> None:
    """DoD-18 — UC-037: a settled group followed by a born-settled partner row is
    unreachable; after the refusal the group is still buried under its head."""
    _state_group_then_partner(engine)

    with pytest.raises(NothingToReopenError):
        _reopen(engine)

    assert _row(engine, 134)["related_to"] == 135
    assert _row(engine, 134)["settled_at"] is None
    assert _record(engine) == [(135, "turn"), (136, "partner")]
    assert _zone_ids(engine) == []


# --- DoD-19: check order ------------------------------------------------------------------


def test_reopen_checks_the_zone_before_the_last_settled_row__S012_003_DoD19(
    engine: Engine,
) -> None:
    """DoD-19 — D10 check order: a zone row and no settled row → `ZoneNotEmptyError`."""
    _insert_zone(engine, 141, "A zone draft.")
    messages_before = _messages_snapshot(engine)

    with pytest.raises(ZoneNotEmptyError):
        _reopen(engine)

    assert _messages_snapshot(engine) == messages_before


# --- DoD-20: one instant on re-open; refusals write nothing -------------------------------


def test_reopen_stamps_one_instant_everywhere__S012_003_DoD20(engine: Engine) -> None:
    """DoD-20 — D3: after re-open the head's and group's `updated_at` and the session's
    `last_used_at` / `updated_at` are one instant, no earlier than the settle's."""
    _settle_group(engine, [(151, "one"), (152, "two"), (153, "three")])
    settle_instant = _row(engine, 153)["settled_at"]
    assert isinstance(settle_instant, str)

    _reopen(engine)

    instant = _row(engine, 153)["updated_at"]
    assert isinstance(instant, str)
    assert FIXED_WIDTH_TIMESTAMP.match(instant)
    assert instant >= settle_instant
    assert _row(engine, 151)["updated_at"] == instant
    assert _row(engine, 152)["updated_at"] == instant
    session = _session(engine)
    assert session["last_used_at"] == instant
    assert session["updated_at"] == instant


def _refuse_settle_empty_zone(engine: Engine) -> None:
    with pytest.raises(ZoneEmptyError):
        _settle(engine)


def _refuse_reopen_zone_not_empty(engine: Engine) -> None:
    _insert_zone(engine, 161, "A zone draft.")
    with pytest.raises(ZoneNotEmptyError):
        _reopen(engine)


def _refuse_reopen_nothing_to_reopen(engine: Engine) -> None:
    _insert_partner(engine, 162, "Partner block.")
    with pytest.raises(NothingToReopenError):
        _reopen(engine)


def _refuse_settle_foreign_session(engine: Engine) -> None:
    _insert_zone(engine, 163, "Alice's draft.")
    with pytest.raises(SessionNotFoundError):
        _settle(engine, USER_B, SESSION_A)


def _refuse_reopen_foreign_session(engine: Engine) -> None:
    with pytest.raises(SessionNotFoundError):
        _reopen(engine, USER_B, SESSION_A)


REFUSALS: list[tuple[str, Callable[[Engine], None]]] = [
    ("settle_zone_empty", _refuse_settle_empty_zone),
    ("reopen_zone_not_empty", _refuse_reopen_zone_not_empty),
    ("reopen_nothing_to_reopen", _refuse_reopen_nothing_to_reopen),
    ("settle_foreign_session", _refuse_settle_foreign_session),
    ("reopen_foreign_session", _refuse_reopen_foreign_session),
]


@pytest.mark.parametrize(
    "refuse",
    [refuse for _, refuse in REFUSALS],
    ids=[name for name, _ in REFUSALS],
)
def test_a_refused_operation_does_not_bump_the_session__S012_003_DoD20(
    engine: Engine, refuse: Callable[[Engine], None]
) -> None:
    """DoD-20 — D3: after any refused settle or re-open the session's `last_used_at` and
    `updated_at` are unchanged."""
    before = _session(engine)

    refuse(engine)

    after = _session(engine)
    assert after["last_used_at"] == before["last_used_at"]
    assert after["updated_at"] == before["updated_at"]


# =========================================================================================
# Both
# =========================================================================================

# --- DoD-21: owner scope ------------------------------------------------------------------


def test_settle_on_another_users_session_is_session_not_found__S012_003_DoD21(
    engine: Engine,
) -> None:
    """DoD-21 — R5: user B settling user A's session raises `SessionNotFoundError`; A's
    rows and session are unchanged."""
    _insert_zone(engine, 171, "Alice's draft.")
    _insert_zone(engine, 172, "Alice's final.")
    messages_before = _messages_snapshot(engine)
    sessions_before = _sessions_snapshot(engine)

    with pytest.raises(SessionNotFoundError):
        _settle(engine, USER_B, SESSION_A)

    assert _messages_snapshot(engine) == messages_before
    assert _sessions_snapshot(engine) == sessions_before


def test_reopen_on_another_users_session_is_session_not_found__S012_003_DoD21(
    engine: Engine,
) -> None:
    """DoD-21 — R5: user B re-opening user A's re-openable session raises
    `SessionNotFoundError`; A's rows and session are unchanged."""
    # The head first: `related_to` is a foreign key to it.
    _insert_message(engine, message_id=174, text="Settled head.", kind="turn", settled_at=TIMESTAMP)
    _insert_message(engine, message_id=173, text="Buried draft.", related_to=174)
    messages_before = _messages_snapshot(engine)
    sessions_before = _sessions_snapshot(engine)

    with pytest.raises(SessionNotFoundError):
        _reopen(engine, USER_B, SESSION_A)

    assert _messages_snapshot(engine) == messages_before
    assert _sessions_snapshot(engine) == sessions_before


@pytest.mark.parametrize("user_id", [USER_A, USER_B])
def test_settle_on_an_unknown_session_is_session_not_found__S012_003_DoD21(
    engine: Engine, user_id: int
) -> None:
    """DoD-21 — an id that exists for nobody answers the same `SessionNotFoundError`."""
    messages_before = _messages_snapshot(engine)
    sessions_before = _sessions_snapshot(engine)

    with pytest.raises(SessionNotFoundError):
        _settle(engine, user_id, UNKNOWN_SESSION_ID)

    assert _messages_snapshot(engine) == messages_before
    assert _sessions_snapshot(engine) == sessions_before


@pytest.mark.parametrize("user_id", [USER_A, USER_B])
def test_reopen_on_an_unknown_session_is_session_not_found__S012_003_DoD21(
    engine: Engine, user_id: int
) -> None:
    """DoD-21 — an id that exists for nobody answers the same `SessionNotFoundError`."""
    messages_before = _messages_snapshot(engine)
    sessions_before = _sessions_snapshot(engine)

    with pytest.raises(SessionNotFoundError):
        _reopen(engine, user_id, UNKNOWN_SESSION_ID)

    assert _messages_snapshot(engine) == messages_before
    assert _sessions_snapshot(engine) == sessions_before


def test_owner_operates_on_their_own_session_after_a_foreign_refusal__S012_003_DoD21(
    engine: Engine,
) -> None:
    """DoD-21 — the refusal is owner scope, not state: B's own session settles fine."""
    _insert_zone(engine, 175, "Bob's draft.", user_id=USER_B, session_id=SESSION_B)

    with pytest.raises(SessionNotFoundError):
        _settle(engine, USER_A, SESSION_B)
    result = _settle(engine, USER_B, SESSION_B)

    assert result.entry_id == 175
    assert _record_ids(engine, USER_B, SESSION_B) == [175]


# --- DoD-22: archive is not a lock --------------------------------------------------------


def test_settle_and_reopen_work_on_an_archived_session__S012_003_DoD22(engine: Engine) -> None:
    """DoD-22 — R6: on an archived session settle and re-open behave as on a working one,
    and the session stays archived."""
    _archive(engine, SESSION_A)
    _insert_zone(engine, 181, "draft")
    _insert_zone(engine, 182, "She walks. ((x)) Then sits.")

    settled = _settle(engine)

    assert settled.entry_id == 182
    assert settled.kind == "turn"
    assert settled.buried_ids == [181]
    assert _row(engine, 182)["text"] == "She walks. Then sits."
    assert _record(engine) == [(182, "turn")]
    assert _zone_ids(engine) == []
    assert _session(engine)["archived_at"] == ARCHIVED_AT

    reopened = _reopen(engine)

    assert reopened.reopened_id == 182
    assert reopened.restored_ids == [181]
    assert _zone_ids(engine) == [181, 182]
    assert _record_ids(engine) == []
    assert _session(engine)["archived_at"] == ARCHIVED_AT


# --- DoD-23: source check -----------------------------------------------------------------

_APP_SERVICES = "app.services"


def _settle_tree() -> ast.Module:
    module_file = settle_module.__file__
    assert module_file is not None
    return ast.parse(Path(module_file).read_text(encoding="utf-8"))


def _docstring_nodes(tree: ast.Module) -> set[int]:
    """`id()`s of the string-constant nodes that are docstrings (not SQL)."""
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))
    return docstrings


def _called_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


#: Feature 021 step 001 (D4): settle think-strips an assistant head with `strip_think`,
#: imported from `app.services.llm.chat` — the one other allowed `app.services` import.
_ALLOWED_CHAT_MODULE = f"{_APP_SERVICES}.llm.chat"
_ALLOWED_CHAT_NAMES = {"strip_think"}

#: Feature 024 step 005 (`context.md` D5 / D9, `005.context.md` "Built state"): settle and
#: re-open refresh the session's `session_vec` through `app.services.session_index`, which
#: also re-exports `LlmClient`, `LlmClientFactory` and `DEFAULT_EMBED_TIMEOUT_SECONDS`. That
#: makes it the one further permitted `app.services` module here — an **approved deviation**
#: (the user's decision of 2026-10-04, recorded under `## Ultra phase` conflict (1) and under
#: step 005's `## Tests` in `docs/plans/024.embedding-lifecycle/status.md`). The guard is
#: narrowed, not weakened: exactly this one named module is permitted, and every other
#: `app.services` module — and every relative import — stays an offender.
_ALLOWED_INDEX_MODULE = f"{_APP_SERVICES}.session_index"


def test_settle_imports_parens_and_no_other_service__S012_003_DoD23__S021_001_DoD10() -> None:
    """DoD-23 — D11: `parens` is imported; nothing else from `app.services.`, except (021
    001, D4) `strip_think` from `app.services.llm.chat` and (024 005) the whole of
    `app.services.session_index`."""
    imports_parens = False
    offenders: list[str] = []
    for node in ast.walk(_settle_tree()):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = [alias.name for alias in node.names]
            if node.level == 0 and module == _ALLOWED_CHAT_MODULE:
                offenders.extend(
                    f"from {module} import {name}" for name in names if name not in _ALLOWED_CHAT_NAMES
                )
            elif node.level == 0 and module == _ALLOWED_INDEX_MODULE:
                pass  # 024 005: permitted outright — the degraded refresh and the D9 defaults.
            elif node.level > 0:
                if module == "" and names == ["parens"]:
                    imports_parens = True
                elif module == "parens":
                    imports_parens = True
                else:
                    offenders.append(ast.unparse(node))
            elif module == _APP_SERVICES:
                if "parens" in names:
                    imports_parens = True
                offenders.extend(f"from {module} import {name}" for name in names if name != "parens")
            elif module.startswith(f"{_APP_SERVICES}."):
                if module == f"{_APP_SERVICES}.parens":
                    imports_parens = True
                else:
                    offenders.append(ast.unparse(node))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == f"{_APP_SERVICES}.parens":
                    imports_parens = True
                elif alias.name == _APP_SERVICES or alias.name.startswith(f"{_APP_SERVICES}."):
                    offenders.append(ast.unparse(node))

    assert imports_parens
    assert offenders == []


def test_settle_does_not_import_fastapi__S012_003_DoD23() -> None:
    """DoD-23 — services import nothing HTTP-shaped."""
    offenders: list[str] = []
    for node in ast.walk(_settle_tree()):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "fastapi" or module.startswith("fastapi."):
                offenders.append(ast.unparse(node))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "fastapi" or alias.name.startswith("fastapi."):
                    offenders.append(ast.unparse(node))

    assert offenders == []


def test_settle_has_no_delete_and_no_insert__S012_003_DoD23() -> None:
    """DoD-23 — D16 / R11 / `data-model.md`: no `delete(` call, no `insert(` call, and no
    `DELETE` SQL keyword in any non-docstring string (settle is two UPDATEs, no INSERT)."""
    tree = _settle_tree()
    docstrings = _docstring_nodes(tree)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _called_name(node) in {"delete", "insert"}:
            offenders.append(ast.unparse(node))
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
            and re.search(r"\bDELETE\b", node.value, re.IGNORECASE)
        ):
            offenders.append(repr(node.value))

    assert offenders == []
