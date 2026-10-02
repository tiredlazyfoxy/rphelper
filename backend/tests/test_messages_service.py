"""Tests for `app/services/messages.py` — feature 012, step 002.

Every expected value comes from `docs/plans/012.messages-and-settle/002.messages-service.md`
(its Interface intent and Definition of done), from `002.context.md` (the statement table,
"Classifying the edit target", "Instants", "Test seeding") and from the feature
`context.md` (the four states, **D1**, **D2**, **D3**, **D7**, **D11**, **D14**, **D16**,
R5, R6, R11, R12 and its "Test conventions"). Each test name ends `__S012_002_DoD<n>`
with the DoD item it covers.

Seeding follows 011's service tests: a file-local `engine` fixture applies the registry
with `schema.metadata.create_all`, then raw-inserts users, characters and sessions (the FK
chain). Stream state is built through the service where 012 has a writer, and raw-inserted
into `messages` where it has none (an assistant zone row, a buried row, a settled turn) or
where a precise state is needed. One connection per service call. **No fixture is added to
`conftest.py`.**

Timestamps are asserted by their fixed-width shape and by equality / non-decrease, never
by exact value; ordering is asserted by integer id, never by `created_at`.
"""

import ast
import inspect
import re
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, func, select

from app.db import schema
from app.errors import MessageNotEditableError, MessageNotFoundError, SessionNotFoundError
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services import messages as messages_module
from app.services.messages import (
    StreamMessage,
    append_message,
    edit_message_text,
    file_partner_entry,
    list_entries,
    list_zone,
)

#: The seeded instant — older than any instant an operation stamps today, so a bump or an
#: edit is visible as a change (002.context.md "Instants").
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
ARCHIVED_AT = "2026-02-01T00:00:00.000000+00:00"

USER_A = 101
USER_B = 202

CHAR_A1 = 1_001
CHAR_B1 = 2_001

SESSION_A = 5_001
SESSION_A2 = 5_002
SESSION_B = 6_001

#: Ids that belong to no row of any user.
UNKNOWN_SESSION_ID = 7_777_777_777
UNKNOWN_MESSAGE_ID = 8_888_888_888

#: Raw-seeded `messages` ids. Small, so every service-minted snowflake sorts after them.
RAW_SETTLED_HEAD = 11
RAW_BURIED = 12
RAW_ZONE = 13
RAW_ASSISTANT_ZONE = 14
RAW_SETTLED_TURN = 15
RAW_B_ZONE = 21
RAW_B_SETTLED = 22

#: `YYYY-MM-DDTHH:MM:SS.ffffff+00:00` — the fixed-width form.
FIXED_WIDTH_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00$")

PARTNER_WITH_FRAGMENT = "She smiles. ((ooc: brb)) Then leaves."
PARTNER_WHOLLY_PARENS = "((whole thing))"


class _FixedIdGenerator:
    """A generator stand-in whose ``next_id()`` always answers one known value."""

    def __init__(self, value: int) -> None:
        self.value = value
        self.calls = 0

    def next_id(self) -> int:
        self.calls += 1
        return self.value


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


def _insert_session(
    engine: Engine,
    *,
    session_id: int,
    user_id: int,
    character_id: int,
    archived_at: str | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.insert().values(
                id=session_id,
                user_id=user_id,
                character_id=character_id,
                setup_id=None,
                last_used_at=TIMESTAMP,
                archived_at=archived_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_message(
    engine: Engine,
    *,
    message_id: int,
    user_id: int,
    session_id: int,
    text: str,
    role: str = "user",
    kind: str | None = None,
    related_to: int | None = None,
    settled_at: str | None = None,
) -> None:
    """Raw-insert one `messages` row in a chosen state (002.context.md "Test seeding")."""
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


def _seed_buried_settled_zone(engine: Engine) -> None:
    """Session A: one settled head, one row buried under it, one zone row (DoD-6)."""
    _insert_message(
        engine,
        message_id=RAW_SETTLED_HEAD,
        user_id=USER_A,
        session_id=SESSION_A,
        text="The settled head.",
        kind="turn",
        settled_at=TIMESTAMP,
    )
    _insert_message(
        engine,
        message_id=RAW_BURIED,
        user_id=USER_A,
        session_id=SESSION_A,
        text="A buried draft.",
        related_to=RAW_SETTLED_HEAD,
    )
    _insert_message(
        engine,
        message_id=RAW_ZONE,
        user_id=USER_A,
        session_id=SESSION_A,
        text="A zone draft.",
    )


def _seed_user_b_stream(engine: Engine) -> None:
    """Session B (another user's): one settled row, one zone row (DoD-7)."""
    _insert_message(
        engine,
        message_id=RAW_B_SETTLED,
        user_id=USER_B,
        session_id=SESSION_B,
        text="Bob's settled entry.",
        kind="partner",
        settled_at=TIMESTAMP,
    )
    _insert_message(
        engine,
        message_id=RAW_B_ZONE,
        user_id=USER_B,
        session_id=SESSION_B,
        text="Bob's zone draft.",
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


@pytest.fixture
def generator() -> SnowflakeGenerator:
    """One real generator per test, so ids minted within a test never collide."""
    return SnowflakeGenerator(node_id=1)


# --- service call wrappers (one connection per call) -------------------------------------


def _entries(engine: Engine, user_id: int, session_id: int) -> list[StreamMessage]:
    with engine.connect() as connection:
        return list_entries(connection, user_id, session_id)


def _zone(engine: Engine, user_id: int, session_id: int) -> list[StreamMessage]:
    with engine.connect() as connection:
        return list_zone(connection, user_id, session_id)


def _append(
    engine: Engine, generator: Any, user_id: int, session_id: int, text: str
) -> StreamMessage:
    with engine.connect() as connection:
        return append_message(connection, generator, user_id, session_id, text)


def _file(
    engine: Engine, generator: Any, user_id: int, session_id: int, text: str
) -> StreamMessage:
    with engine.connect() as connection:
        return file_partner_entry(connection, generator, user_id, session_id, text)


def _edit(engine: Engine, user_id: int, message_id: int, text: str) -> StreamMessage:
    with engine.connect() as connection:
        return edit_message_text(connection, user_id, message_id, text)


def _ids(values: list[StreamMessage]) -> list[int]:
    return [value.id for value in values]


# --- direct reads of stored state (tests may read the raw table) -------------------------


def _stored_message(engine: Engine, message_id: int) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(
            select(schema.messages).where(schema.messages.c.id == message_id)
        ).one()
    return dict(row._mapping)


def _all_messages(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(select(schema.messages).order_by(schema.messages.c.id)).all()
    return [dict(row._mapping) for row in rows]


def _count_messages(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(select(func.count()).select_from(schema.messages)).scalar_one()
        )


def _session_row(engine: Engine, session_id: int) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(
            select(schema.sessions).where(schema.sessions.c.id == session_id)
        ).one()
    return dict(row._mapping)


def _archive_session_row(engine: Engine, session_id: int) -> None:
    """Archive a session with a raw update (002.context.md "Test seeding", DoD-11)."""
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.update()
            .where(schema.sessions.c.id == session_id)
            .values(archived_at=ARCHIVED_AT)
        )


def _begin_and_roll_back(connection: Connection) -> None:
    """A following `begin()` must succeed — it raises if a transaction is still open."""
    assert not connection.in_transaction()
    transaction = connection.begin()
    transaction.rollback()


# --- DoD-1: append a zone message ---------------------------------------------------------


def test_append_returns_the_minted_id_and_a_zone_value__S012_002_DoD1(engine: Engine) -> None:
    """DoD-1 — the value carries the generator's id, the session, role 'user', null kind and
    settled_at, the text as given, and one fixed-width instant (UC-083 step 2, R11)."""
    fixed = _FixedIdGenerator(424_242)
    text = "  Aria leans in, whispering.\n"

    created = _append(engine, fixed, USER_A, SESSION_A, text)

    assert isinstance(created, StreamMessage)
    assert fixed.calls == 1
    assert created.id == 424_242
    assert created.session_id == SESSION_A
    assert created.role == "user"
    assert created.kind is None
    assert created.settled_at is None
    assert created.text == text
    assert created.created_at == created.updated_at
    assert FIXED_WIDTH_TIMESTAMP.match(created.created_at)
    assert FIXED_WIDTH_TIMESTAMP.match(created.updated_at)


def test_an_appended_message_is_in_the_zone_and_not_in_the_entries__S012_002_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-1 — `list_zone` contains it, `list_entries` does not."""
    created = _append(engine, generator, USER_A, SESSION_A, "First draft.")

    zone = _zone(engine, USER_A, SESSION_A)
    entries = _entries(engine, USER_A, SESSION_A)

    assert created in zone
    assert _ids(zone) == [created.id]
    assert created.id not in _ids(entries)


def test_the_stored_appended_row_has_null_related_to__S012_002_DoD1(engine: Engine) -> None:
    """DoD-1 — the stored row: `related_to`, `kind`, `settled_at` NULL, text verbatim,
    owned by the caller."""
    fixed = _FixedIdGenerator(424_243)
    text = "Draft with ((a fragment)) inside."

    created = _append(engine, fixed, USER_A, SESSION_A, text)
    stored = _stored_message(engine, created.id)

    assert stored["related_to"] is None
    assert stored["kind"] is None
    assert stored["settled_at"] is None
    assert stored["role"] == "user"
    assert stored["text"] == text
    assert stored["user_id"] == USER_A
    assert stored["session_id"] == SESSION_A
    assert stored["created_at"] == created.created_at
    assert stored["updated_at"] == created.updated_at


# --- DoD-2: the zone is a set -------------------------------------------------------------


def test_three_appends_all_stay_in_the_zone_in_call_order__S012_002_DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-2 — nothing refuses a second or third zone message; ascending id order equals
    the order of the calls (US-125.AC-1)."""
    first = _append(engine, generator, USER_A, SESSION_A, "one")
    second = _append(engine, generator, USER_A, SESSION_A, "two")
    third = _append(engine, generator, USER_A, SESSION_A, "three")

    zone = _zone(engine, USER_A, SESSION_A)

    assert _ids(zone) == [first.id, second.id, third.id]
    assert _ids(zone) == sorted(_ids(zone))
    assert [message.text for message in zone] == ["one", "two", "three"]


# --- DoD-3: file a born-settled partner block ---------------------------------------------


def test_filing_a_partner_block_returns_a_born_settled_value__S012_002_DoD3(
    engine: Engine,
) -> None:
    """DoD-3 — role 'user', kind 'partner', settled_at set and equal to both timestamps,
    the text as given, the minted id (US-121.AC-1)."""
    fixed = _FixedIdGenerator(535_353)
    text = "The partner's reply, pasted whole.\n\nSecond paragraph."

    filed = _file(engine, fixed, USER_A, SESSION_A, text)

    assert isinstance(filed, StreamMessage)
    assert filed.id == 535_353
    assert filed.session_id == SESSION_A
    assert filed.role == "user"
    assert filed.kind == "partner"
    assert filed.settled_at is not None
    assert filed.settled_at == filed.created_at == filed.updated_at
    assert FIXED_WIDTH_TIMESTAMP.match(filed.settled_at)
    assert filed.text == text


def test_a_filed_partner_block_is_in_the_entries_and_not_the_zone__S012_002_DoD3(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-3 — `list_entries` contains it, `list_zone` does not; stored `related_to` NULL
    (R11's single exception)."""
    filed = _file(engine, generator, USER_A, SESSION_A, "Pasted block.")

    entries = _entries(engine, USER_A, SESSION_A)
    zone = _zone(engine, USER_A, SESSION_A)
    stored = _stored_message(engine, filed.id)

    assert filed in entries
    assert _ids(entries) == [filed.id]
    assert filed.id not in _ids(zone)
    assert stored["related_to"] is None
    assert stored["kind"] == "partner"
    assert stored["settled_at"] == filed.settled_at
    assert stored["user_id"] == USER_A


# --- DoD-4: no parens handling on a partner block -----------------------------------------


@pytest.mark.parametrize("text", [PARTNER_WITH_FRAGMENT, PARTNER_WHOLLY_PARENS])
def test_a_partner_block_keeps_its_parens_byte_for_byte__S012_002_DoD4(
    engine: Engine, generator: SnowflakeGenerator, text: str
) -> None:
    """DoD-4 — stored and returned unchanged, kind 'partner', never 'decision'
    (US-121.AC-2, R12)."""
    filed = _file(engine, generator, USER_A, SESSION_A, text)
    stored = _stored_message(engine, filed.id)
    (listed,) = _entries(engine, USER_A, SESSION_A)

    assert filed.text == text
    assert stored["text"] == text
    assert listed.text == text
    assert filed.kind == "partner"
    assert stored["kind"] == "partner"
    assert listed.kind == "partner"


# --- DoD-5: several partner blocks; no zone precondition ----------------------------------


def test_several_partner_blocks_in_a_row_all_settle_in_order__S012_002_DoD5(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-5 — UC-031's several partner blocks in sequence all succeed; ascending id."""
    first = _file(engine, generator, USER_A, SESSION_A, "block one")
    second = _file(engine, generator, USER_A, SESSION_A, "block two")
    third = _file(engine, generator, USER_A, SESSION_A, "block three")

    entries = _entries(engine, USER_A, SESSION_A)

    assert _ids(entries) == [first.id, second.id, third.id]
    assert _ids(entries) == sorted(_ids(entries))


def test_filing_while_the_zone_holds_a_message_succeeds_and_leaves_it__S012_002_DoD5(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-5 — D14: no zone precondition; the zone row is untouched."""
    draft = _append(engine, generator, USER_A, SESSION_A, "A draft in progress.")
    draft_stored_before = _stored_message(engine, draft.id)

    first = _file(engine, generator, USER_A, SESSION_A, "partner one")
    second = _file(engine, generator, USER_A, SESSION_A, "partner two")

    assert _ids(_entries(engine, USER_A, SESSION_A)) == [first.id, second.id]
    assert _zone(engine, USER_A, SESSION_A) == [draft]
    assert _stored_message(engine, draft.id) == draft_stored_before


# --- DoD-6: each read returns exactly its own state ---------------------------------------


def test_each_read_returns_exactly_its_own_state_and_no_buried_row__S012_002_DoD6(
    engine: Engine,
) -> None:
    """DoD-6 — zone row only in `list_zone`, settled row only in `list_entries`, the buried
    row in neither (R11, R7)."""
    _seed_buried_settled_zone(engine)

    entries = _entries(engine, USER_A, SESSION_A)
    zone = _zone(engine, USER_A, SESSION_A)

    assert _ids(entries) == [RAW_SETTLED_HEAD]
    assert _ids(zone) == [RAW_ZONE]
    assert RAW_BURIED not in _ids(entries)
    assert RAW_BURIED not in _ids(zone)


def test_the_reads_carry_the_stored_fields_of_each_row__S012_002_DoD6(engine: Engine) -> None:
    """DoD-6 — each value is the row's own: session, role, kind, text, timestamps."""
    _seed_buried_settled_zone(engine)

    (entry,) = _entries(engine, USER_A, SESSION_A)
    (zoned,) = _zone(engine, USER_A, SESSION_A)

    assert entry == StreamMessage(
        id=RAW_SETTLED_HEAD,
        session_id=SESSION_A,
        role="user",
        kind="turn",
        text="The settled head.",
        settled_at=TIMESTAMP,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )
    assert zoned == StreamMessage(
        id=RAW_ZONE,
        session_id=SESSION_A,
        role="user",
        kind=None,
        text="A zone draft.",
        settled_at=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def test_the_reads_are_scoped_to_the_addressed_session__S012_002_DoD6(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-6 — another session of the same owner contributes nothing to either read."""
    _seed_buried_settled_zone(engine)
    _append(engine, generator, USER_A, SESSION_A2, "other session draft")
    _file(engine, generator, USER_A, SESSION_A2, "other session partner")

    assert _ids(_entries(engine, USER_A, SESSION_A)) == [RAW_SETTLED_HEAD]
    assert _ids(_zone(engine, USER_A, SESSION_A)) == [RAW_ZONE]


def test_reads_of_an_empty_session_are_empty__S012_002_DoD6(engine: Engine) -> None:
    """DoD-6 — a session with no rows reads as two empty lists."""
    assert _entries(engine, USER_A, SESSION_A) == []
    assert _zone(engine, USER_A, SESSION_A) == []


# --- DoD-7: owner scope (R5) --------------------------------------------------------------


_SESSION_OPERATIONS: dict[str, Callable[[Engine, Any, int, int], object]] = {
    "list_entries": lambda engine, gen, user_id, session_id: _entries(engine, user_id, session_id),
    "list_zone": lambda engine, gen, user_id, session_id: _zone(engine, user_id, session_id),
    "append_message": lambda engine, gen, user_id, session_id: _append(
        engine, gen, user_id, session_id, "an intruding draft"
    ),
    "file_partner_entry": lambda engine, gen, user_id, session_id: _file(
        engine, gen, user_id, session_id, "an intruding partner block"
    ),
}


@pytest.mark.parametrize("operation", sorted(_SESSION_OPERATIONS))
def test_a_session_operation_on_another_users_session_is_not_found__S012_002_DoD7(
    engine: Engine, generator: SnowflakeGenerator, operation: str
) -> None:
    """DoD-7 — user A addressing user B's session raises `SessionNotFoundError`; B's rows
    and session are unchanged and no row is inserted."""
    _seed_user_b_stream(engine)
    messages_before = _all_messages(engine)
    session_b_before = _session_row(engine, SESSION_B)
    session_a_before = _session_row(engine, SESSION_A)

    with pytest.raises(SessionNotFoundError):
        _SESSION_OPERATIONS[operation](engine, generator, USER_A, SESSION_B)

    assert _all_messages(engine) == messages_before
    assert _session_row(engine, SESSION_B) == session_b_before
    assert _session_row(engine, SESSION_A) == session_a_before


@pytest.mark.parametrize("operation", sorted(_SESSION_OPERATIONS))
def test_a_session_operation_on_an_unknown_session_is_not_found__S012_002_DoD7(
    engine: Engine, generator: SnowflakeGenerator, operation: str
) -> None:
    """DoD-7 — the same error as for an id that exists for nobody; nothing inserted."""
    count_before = _count_messages(engine)

    with pytest.raises(SessionNotFoundError):
        _SESSION_OPERATIONS[operation](engine, generator, USER_A, UNKNOWN_SESSION_ID)

    assert _count_messages(engine) == count_before


@pytest.mark.parametrize("message_id", [RAW_B_ZONE, RAW_B_SETTLED])
def test_editing_another_users_message_is_not_found__S012_002_DoD7(
    engine: Engine, message_id: int
) -> None:
    """DoD-7 — a message of another user's session raises `MessageNotFoundError`; B's rows
    and session are unchanged and no row is inserted (R5)."""
    _seed_user_b_stream(engine)
    messages_before = _all_messages(engine)
    session_b_before = _session_row(engine, SESSION_B)
    session_a_before = _session_row(engine, SESSION_A)

    with pytest.raises(MessageNotFoundError):
        _edit(engine, USER_A, message_id, "hijacked text")

    assert _all_messages(engine) == messages_before
    assert _session_row(engine, SESSION_B) == session_b_before
    assert _session_row(engine, SESSION_A) == session_a_before


def test_editing_an_unknown_message_is_not_found__S012_002_DoD7(engine: Engine) -> None:
    """DoD-7 — an id that exists for nobody raises the same `MessageNotFoundError`."""
    messages_before = _all_messages(engine)

    with pytest.raises(MessageNotFoundError):
        _edit(engine, USER_A, UNKNOWN_MESSAGE_ID, "text for nobody")

    assert _all_messages(engine) == messages_before


def test_the_owner_still_reads_their_own_rows_after_an_intrusion__S012_002_DoD7(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-7 — after A's refused attempts, B reads exactly B's own rows."""
    _seed_user_b_stream(engine)
    for operation in _SESSION_OPERATIONS.values():
        with pytest.raises(SessionNotFoundError):
            operation(engine, generator, USER_A, SESSION_B)

    assert _ids(_entries(engine, USER_B, SESSION_B)) == [RAW_B_SETTLED]
    assert _ids(_zone(engine, USER_B, SESSION_B)) == [RAW_B_ZONE]


# --- DoD-8: edit a current-zone row --------------------------------------------------------


def test_editing_a_zone_row_stores_the_text_verbatim__S012_002_DoD8(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-8 — the new text, `((fragment))` included, is stored and returned unchanged;
    `created_at` is unchanged and `updated_at` does not move backward (US-115.AC-1, R12)."""
    draft = _append(engine, generator, USER_A, SESSION_A, "Original draft.")
    new_text = "Edited draft ((fragment)) with a note.  "

    edited = _edit(engine, USER_A, draft.id, new_text)
    stored = _stored_message(engine, draft.id)

    assert isinstance(edited, StreamMessage)
    assert edited.id == draft.id
    assert edited.session_id == SESSION_A
    assert edited.role == "user"
    assert edited.text == new_text
    assert stored["text"] == new_text
    assert edited.created_at == draft.created_at
    assert stored["created_at"] == draft.created_at
    assert edited.updated_at >= draft.updated_at
    assert FIXED_WIDTH_TIMESTAMP.match(edited.updated_at)
    assert stored["updated_at"] == edited.updated_at


def test_an_edit_leaves_the_state_columns_null__S012_002_DoD8(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-8 — `kind`, `settled_at`, `related_to` stay NULL (D16)."""
    draft = _append(engine, generator, USER_A, SESSION_A, "Draft.")

    edited = _edit(engine, USER_A, draft.id, "((wholly an instruction))")
    stored = _stored_message(engine, draft.id)

    assert edited.kind is None
    assert edited.settled_at is None
    assert stored["kind"] is None
    assert stored["settled_at"] is None
    assert stored["related_to"] is None


def test_an_edit_moves_updated_at_strictly_forward_from_an_older_row__S012_002_DoD8(
    engine: Engine,
) -> None:
    """DoD-8 — against an explicitly older seeded `updated_at`, the edit moves it forward
    and leaves `created_at` unchanged (002.context.md "Instants")."""
    _insert_message(
        engine, message_id=RAW_ZONE, user_id=USER_A, session_id=SESSION_A, text="Old draft."
    )

    edited = _edit(engine, USER_A, RAW_ZONE, "Fresh draft.")

    assert edited.updated_at > TIMESTAMP
    assert edited.created_at == TIMESTAMP
    assert _stored_message(engine, RAW_ZONE)["created_at"] == TIMESTAMP


def test_an_edited_row_stays_in_the_zone_at_the_same_position__S012_002_DoD8(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-8 — the edited value is in `list_zone` at the same index; the others untouched."""
    first = _append(engine, generator, USER_A, SESSION_A, "one")
    second = _append(engine, generator, USER_A, SESSION_A, "two")
    third = _append(engine, generator, USER_A, SESSION_A, "three")

    edited = _edit(engine, USER_A, second.id, "two, revised")
    zone = _zone(engine, USER_A, SESSION_A)

    assert _ids(zone) == [first.id, second.id, third.id]
    assert zone[1] == edited
    assert zone[1].text == "two, revised"
    assert zone[0] == first
    assert zone[2] == third
    assert edited.id not in _ids(_entries(engine, USER_A, SESSION_A))


def test_an_assistant_zone_row_is_editable_the_same_way__S012_002_DoD8(engine: Engine) -> None:
    """DoD-8 — a raw-inserted `role='assistant'` zone row edits like a roleplayer's."""
    _insert_message(
        engine,
        message_id=RAW_ASSISTANT_ZONE,
        user_id=USER_A,
        session_id=SESSION_A,
        text="The assistant's suggestion.",
        role="assistant",
    )
    new_text = "The assistant's suggestion, ((tweaked)) by hand."

    edited = _edit(engine, USER_A, RAW_ASSISTANT_ZONE, new_text)
    stored = _stored_message(engine, RAW_ASSISTANT_ZONE)

    assert edited.id == RAW_ASSISTANT_ZONE
    assert edited.role == "assistant"
    assert edited.text == new_text
    assert edited.kind is None
    assert edited.settled_at is None
    assert edited.created_at == TIMESTAMP
    assert edited.updated_at >= TIMESTAMP
    assert stored["text"] == new_text
    assert stored["role"] == "assistant"
    assert stored["kind"] is None
    assert stored["settled_at"] is None
    assert stored["related_to"] is None
    assert _zone(engine, USER_A, SESSION_A) == [edited]


# --- DoD-9: buried and settled rows are not editable --------------------------------------


def _assert_edit_refused_and_nothing_moved(engine: Engine, message_id: int) -> None:
    stored_before = _stored_message(engine, message_id)
    session_before = _session_row(engine, SESSION_A)

    with pytest.raises(MessageNotEditableError):
        _edit(engine, USER_A, message_id, "an attempted edit")

    stored_after = _stored_message(engine, message_id)
    session_after = _session_row(engine, SESSION_A)
    assert stored_after["text"] == stored_before["text"]
    assert stored_after["updated_at"] == stored_before["updated_at"]
    assert stored_after == stored_before
    assert session_after["last_used_at"] == session_before["last_used_at"]
    assert session_after["updated_at"] == session_before["updated_at"]


def test_editing_a_buried_row_is_not_editable__S012_002_DoD9(engine: Engine) -> None:
    """DoD-9 — a raw-seeded buried row raises `MessageNotEditableError`; text, `updated_at`
    and the session are unchanged (US-116.AC-1, D2)."""
    _seed_buried_settled_zone(engine)

    _assert_edit_refused_and_nothing_moved(engine, RAW_BURIED)


def test_editing_a_filed_partner_block_is_not_editable__S012_002_DoD9(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-9 — a settled partner block (filed through the service) is refused until 014."""
    filed = _file(engine, generator, USER_A, SESSION_A, "A pasted partner block.")

    _assert_edit_refused_and_nothing_moved(engine, filed.id)


def test_editing_a_raw_settled_turn_is_not_editable__S012_002_DoD9(engine: Engine) -> None:
    """DoD-9 — a raw-seeded settled turn is refused the same way."""
    _insert_message(
        engine,
        message_id=RAW_SETTLED_TURN,
        user_id=USER_A,
        session_id=SESSION_A,
        text="A settled turn.",
        kind="turn",
        settled_at=TIMESTAMP,
    )

    _assert_edit_refused_and_nothing_moved(engine, RAW_SETTLED_TURN)


def test_a_refused_edit_leaves_the_reads_unchanged__S012_002_DoD9(engine: Engine) -> None:
    """DoD-9 — after refusals, the record and the zone read as before."""
    _seed_buried_settled_zone(engine)

    for message_id in (RAW_BURIED, RAW_SETTLED_HEAD):
        with pytest.raises(MessageNotEditableError):
            _edit(engine, USER_A, message_id, "nope")

    assert _ids(_entries(engine, USER_A, SESSION_A)) == [RAW_SETTLED_HEAD]
    assert _ids(_zone(engine, USER_A, SESSION_A)) == [RAW_ZONE]
    assert _stored_message(engine, RAW_SETTLED_HEAD)["text"] == "The settled head."
    assert _stored_message(engine, RAW_BURIED)["text"] == "A buried draft."


# --- DoD-10: every content write bumps the session; reads and refusals do not -------------


def test_append_bumps_the_session_to_the_rows_instant__S012_002_DoD10(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-10 — `last_used_at` and `updated_at` both equal the written row's `updated_at`."""
    created = _append(engine, generator, USER_A, SESSION_A, "draft")
    session = _session_row(engine, SESSION_A)

    assert session["last_used_at"] == created.updated_at
    assert session["updated_at"] == created.updated_at
    assert _stored_message(engine, created.id)["updated_at"] == created.updated_at


def test_filing_a_partner_block_bumps_the_session__S012_002_DoD10(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-10 — the same for `file_partner_entry`."""
    filed = _file(engine, generator, USER_A, SESSION_A, "partner block")
    session = _session_row(engine, SESSION_A)

    assert session["last_used_at"] == filed.updated_at
    assert session["updated_at"] == filed.updated_at


def test_an_edit_bumps_the_rows_session__S012_002_DoD10(engine: Engine) -> None:
    """DoD-10 — the edit bumps the edited row's session to the row's new `updated_at`."""
    _insert_message(
        engine, message_id=RAW_ZONE, user_id=USER_A, session_id=SESSION_A, text="Old draft."
    )

    edited = _edit(engine, USER_A, RAW_ZONE, "New draft.")
    session = _session_row(engine, SESSION_A)

    assert session["last_used_at"] == edited.updated_at
    assert session["updated_at"] == edited.updated_at
    assert _stored_message(engine, RAW_ZONE)["updated_at"] == edited.updated_at


def test_a_write_bumps_only_its_own_session__S012_002_DoD10(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-10 — the owner's other session and the other user's session are untouched."""
    other_before = _session_row(engine, SESSION_A2)
    b_before = _session_row(engine, SESSION_B)

    _append(engine, generator, USER_A, SESSION_A, "draft")
    _file(engine, generator, USER_A, SESSION_A, "partner")

    assert _session_row(engine, SESSION_A2) == other_before
    assert _session_row(engine, SESSION_B) == b_before


def test_the_reads_do_not_bump_the_session__S012_002_DoD10(engine: Engine) -> None:
    """DoD-10 — after `list_entries` and `list_zone` the session row is unchanged."""
    _seed_buried_settled_zone(engine)
    before = _session_row(engine, SESSION_A)

    _entries(engine, USER_A, SESSION_A)
    _zone(engine, USER_A, SESSION_A)

    after = _session_row(engine, SESSION_A)
    assert after["last_used_at"] == before["last_used_at"] == TIMESTAMP
    assert after["updated_at"] == before["updated_at"] == TIMESTAMP


def test_refused_operations_do_not_bump_any_session__S012_002_DoD10(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-10 — the DoD-7 and DoD-9 refusals leave every session's timestamps unchanged."""
    _seed_buried_settled_zone(engine)
    _seed_user_b_stream(engine)
    before = {sid: _session_row(engine, sid) for sid in (SESSION_A, SESSION_A2, SESSION_B)}

    for operation in _SESSION_OPERATIONS.values():
        with pytest.raises(SessionNotFoundError):
            operation(engine, generator, USER_A, SESSION_B)
        with pytest.raises(SessionNotFoundError):
            operation(engine, generator, USER_A, UNKNOWN_SESSION_ID)
    with pytest.raises(MessageNotFoundError):
        _edit(engine, USER_A, RAW_B_ZONE, "x")
    with pytest.raises(MessageNotFoundError):
        _edit(engine, USER_A, UNKNOWN_MESSAGE_ID, "x")
    for message_id in (RAW_BURIED, RAW_SETTLED_HEAD):
        with pytest.raises(MessageNotEditableError):
            _edit(engine, USER_A, message_id, "x")

    for sid, row in before.items():
        after = _session_row(engine, sid)
        assert after["last_used_at"] == row["last_used_at"]
        assert after["updated_at"] == row["updated_at"]


# --- DoD-11: archive is not a lock (R6) ---------------------------------------------------


def test_every_operation_works_on_an_archived_session__S012_002_DoD11(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-11 — all five operations succeed as on a working session; it stays archived."""
    _seed_buried_settled_zone(engine)
    _archive_session_row(engine, SESSION_A)

    appended = _append(engine, generator, USER_A, SESSION_A, "draft on an archived session")
    filed = _file(engine, generator, USER_A, SESSION_A, "partner on an archived session")
    edited = _edit(engine, USER_A, appended.id, "draft, edited while archived")
    entries = _entries(engine, USER_A, SESSION_A)
    zone = _zone(engine, USER_A, SESSION_A)

    assert appended.kind is None
    assert appended.settled_at is None
    assert filed.kind == "partner"
    assert filed.settled_at is not None
    assert edited.text == "draft, edited while archived"
    assert _ids(entries) == [RAW_SETTLED_HEAD, filed.id]
    assert _ids(zone) == [RAW_ZONE, appended.id]
    assert zone[1] == edited

    session = _session_row(engine, SESSION_A)
    assert session["archived_at"] == ARCHIVED_AT
    assert session["last_used_at"] == edited.updated_at
    assert session["updated_at"] == edited.updated_at


def test_the_raw_zone_row_of_an_archived_session_is_editable__S012_002_DoD11(
    engine: Engine,
) -> None:
    """DoD-11 — the edit reads no `archived_at` either."""
    _seed_buried_settled_zone(engine)
    _archive_session_row(engine, SESSION_A)

    edited = _edit(engine, USER_A, RAW_ZONE, "revised while archived")

    assert edited.text == "revised while archived"
    assert _session_row(engine, SESSION_A)["archived_at"] == ARCHIVED_AT


# --- DoD-12: the reads leave no transaction open ------------------------------------------


@pytest.mark.parametrize("read", [list_entries, list_zone])
def test_a_read_leaves_no_transaction_open__S012_002_DoD12(
    engine: Engine, read: Callable[[Connection, int, int], list[StreamMessage]]
) -> None:
    """DoD-12 — after a successful read, a following `connection.begin()` succeeds."""
    _seed_buried_settled_zone(engine)

    with engine.connect() as connection:
        read(connection, USER_A, SESSION_A)
        _begin_and_roll_back(connection)


@pytest.mark.parametrize("read", [list_entries, list_zone])
@pytest.mark.parametrize("session_id", [SESSION_B, UNKNOWN_SESSION_ID])
def test_a_refused_read_leaves_no_transaction_open__S012_002_DoD12(
    engine: Engine,
    read: Callable[[Connection, int, int], list[StreamMessage]],
    session_id: int,
) -> None:
    """DoD-12 — and on the raising exit, after `SessionNotFoundError`."""
    with engine.connect() as connection:
        with pytest.raises(SessionNotFoundError):
            read(connection, USER_A, session_id)
        _begin_and_roll_back(connection)


@pytest.mark.parametrize("read", [list_entries, list_zone])
def test_a_write_can_follow_a_read_on_one_connection__S012_002_DoD12(
    engine: Engine,
    generator: SnowflakeGenerator,
    read: Callable[[Connection, int, int], list[StreamMessage]],
) -> None:
    """DoD-12 — a read then a service write (which opens its own `begin()`) on the same
    connection both succeed."""
    with engine.connect() as connection:
        read(connection, USER_A, SESSION_A)
        created = append_message(connection, generator, USER_A, SESSION_A, "after a read")

    assert _ids(_zone(engine, USER_A, SESSION_A)) == [created.id]


# --- DoD-13: source check -----------------------------------------------------------------

_DELETE_CALL = re.compile(r"\bdelete\s*\(", re.IGNORECASE)
_DELETE_SQL_KEYWORD = re.compile(r"\bDELETE\b")
_FORBIDDEN_IMPORT_ROOT = "app.services"


def _module_tree() -> ast.Module:
    return ast.parse(inspect.getsource(messages_module))


def _names_the_messages_table(node: ast.AST) -> bool:
    """True if the expression mentions the `messages` Table (bare or `schema.messages`),
    including any of its columns (`messages.c.<col>`)."""
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name) and inner.id == "messages":
            return True
        if isinstance(inner, ast.Attribute) and inner.attr == "messages":
            return True
    return False


def _is_select_call(node: ast.Call) -> bool:
    func_node = node.func
    if isinstance(func_node, ast.Name):
        return func_node.id == "select"
    if isinstance(func_node, ast.Attribute):
        return func_node.attr == "select"
    return False


def test_no_select_call_takes_the_messages_table_or_its_columns__S012_002_DoD13() -> None:
    """DoD-13 — D1 / D7: reads go only through `settled_entries`, `current_zone` and
    `message_states`; no `select(...)` over `messages` or its columns, and no
    `messages.select()`."""
    offenders: list[str] = []
    for node in ast.walk(_module_tree()):
        if not isinstance(node, ast.Call) or not _is_select_call(node):
            continue
        arguments: list[ast.AST] = [*node.args, *(kw.value for kw in node.keywords)]
        if any(_names_the_messages_table(argument) for argument in arguments):
            offenders.append(ast.unparse(node))
        if isinstance(node.func, ast.Attribute) and _names_the_messages_table(node.func.value):
            offenders.append(ast.unparse(node))

    assert offenders == []


def test_the_module_has_no_delete_path__S012_002_DoD13() -> None:
    """DoD-13 — D16: no `delete(` call and no `DELETE` SQL keyword."""
    source = inspect.getsource(messages_module)

    assert _DELETE_CALL.search(source) is None
    assert _DELETE_SQL_KEYWORD.search(source) is None


def test_the_module_imports_no_fastapi_no_service_and_no_parens__S012_002_DoD13() -> None:
    """DoD-13 — D11 / R12: nothing from `fastapi`, nothing from any `app.services.` module
    (nor relatively), and nothing named `parens`."""
    offenders: list[str] = []
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported = [alias.name for alias in node.names]
            if node.level > 0:
                offenders.append(f"relative import, level {node.level}")
            if module == "fastapi" or module.startswith("fastapi."):
                offenders.append(f"from {module} import ...")
            if module == _FORBIDDEN_IMPORT_ROOT or module.startswith(
                _FORBIDDEN_IMPORT_ROOT + "."
            ):
                offenders.append(f"from {module} import ...")
            if "parens" in module or any("parens" in name for name in imported):
                offenders.append(f"from {module} import {imported}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name == "fastapi" or name.startswith("fastapi."):
                    offenders.append(f"import {name}")
                if name == _FORBIDDEN_IMPORT_ROOT or name.startswith(_FORBIDDEN_IMPORT_ROOT + "."):
                    offenders.append(f"import {name}")
                if "parens" in name:
                    offenders.append(f"import {name}")

    assert offenders == []


def test_the_module_never_assigns_related_to__S012_002_DoD13() -> None:
    """DoD-13 — D16: `related_to` is never set in an insert or update — no `related_to=`
    keyword and no `related_to` key in a values mapping."""
    offenders: list[str] = []
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.keyword) and node.arg == "related_to":
            offenders.append("related_to= keyword")
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if key is None:
                    continue
                if isinstance(key, ast.Constant) and key.value == "related_to":
                    offenders.append("'related_to' dict key")
                if isinstance(key, ast.Attribute) and key.attr == "related_to":
                    offenders.append(f"{ast.unparse(key)} dict key")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"values", "ordered_values"}
        ):
            for argument in node.args:
                if isinstance(argument, (ast.Tuple, ast.List)):
                    for element in ast.walk(argument):
                        if isinstance(element, ast.Attribute) and element.attr == "related_to":
                            offenders.append(f"{ast.unparse(argument)} in .values()")

    assert offenders == []
