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

Amended by feature 014, step 001 (`docs/plans/014.entry-editing-and-copy-out/
001.settled-edit-backend.md`, D1 / D2): a settled row of any kind is now editable through
`edit_message_text`; only a buried row stays `MessageNotEditableError`. 012 DoD-9's two
settled-refusal cases are removed and every refusal loop is narrowed to the buried row. The
014 cases carry the suffix `__S014_001_DoD<n>`.
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
    created_at: str = TIMESTAMP,
    updated_at: str = TIMESTAMP,
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
                created_at=created_at,
                updated_at=updated_at,
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


# --- DoD-9: buried rows are not editable (settled rows: see 014 step 001 below) -----------


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


def test_editing_a_buried_row_is_not_editable__S012_002_DoD9__S014_001_DoD5(
    engine: Engine,
) -> None:
    """DoD-9 (amended by 014 001 DoD-5) — a raw-seeded buried row raises
    `MessageNotEditableError`; text, `updated_at` and the session are unchanged (US-116.AC-1).
    The former settled-row refusal cases are gone: settled rows are editable (014 D1)."""
    _seed_buried_settled_zone(engine)

    _assert_edit_refused_and_nothing_moved(engine, RAW_BURIED)


def test_a_refused_edit_leaves_the_reads_unchanged__S012_002_DoD9(engine: Engine) -> None:
    """DoD-9 — after a refusal (the buried row), the record and the zone read as before."""
    _seed_buried_settled_zone(engine)

    with pytest.raises(MessageNotEditableError):
        _edit(engine, USER_A, RAW_BURIED, "nope")

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
    """DoD-10 — the DoD-7 and DoD-9 refusals (DoD-9 narrowed to the buried row by 014 D1)
    leave every session's timestamps unchanged."""
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
    with pytest.raises(MessageNotEditableError):
        _edit(engine, USER_A, RAW_BURIED, "x")

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

_DELETE_SQL_KEYWORD = re.compile(r"\bDELETE\b")
_FORBIDDEN_IMPORT_ROOT = "app.services"

#: Feature 023, step 001 (D11, US-111.AC-1) narrowed 012's "no delete path" guard, by the
#: user's decision of 2026-10-04 recorded under step 001's `## Tests` in
#: `docs/plans/023.partner-translation/status.md`: `edit_message_text` discards the edited
#: message's cached translations inside its own transaction, so exactly one table may be
#: deleted from, and `messages` is still not it.
_PERMITTED_DELETE_TABLE = "translations"


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


def _names_table(node: ast.AST, table: str) -> bool:
    """True if the expression mentions the named Table (bare or `schema.<table>`), including
    any of its columns (`<table>.c.<col>`)."""
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name) and inner.id == table:
            return True
        if isinstance(inner, ast.Attribute) and inner.attr == table:
            return True
    return False


def _is_delete_call(node: ast.Call) -> bool:
    """True for `delete(...)` and for `<something>.delete(...)`, however the name was bound."""
    func_node = node.func
    if isinstance(func_node, ast.Name):
        return func_node.id == "delete"
    if isinstance(func_node, ast.Attribute):
        return func_node.attr == "delete"
    return False


def _delete_operands(node: ast.Call) -> list[ast.AST]:
    """Everything a delete call could name as its target: its arguments, plus the receiver of
    a `<table>.delete()` form."""
    operands: list[ast.AST] = [*node.args, *(kw.value for kw in node.keywords)]
    if isinstance(node.func, ast.Attribute):
        operands.append(node.func.value)
    return operands


def _delete_aliases(tree: ast.Module) -> list[str]:
    """Imports that rebind `delete` under another name — the one way a name-based check could
    be evaded, so it is refused outright."""
    aliases: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name.rsplit(".", 1)[-1] == "delete" and alias.asname is not None:
                    aliases.append(f"{alias.name} as {alias.asname}")
    return aliases


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
    """DoD-13 — D16: no delete path, **narrowed** by feature 023, step 001 (D11,
    US-111.AC-1) on the user's decision of 2026-10-04: the *only* permitted delete in this
    module targets the `translations` table — the edited message's cached translations,
    discarded inside `edit_message_text`'s own transaction. 012's half of the guard keeps
    biting: no delete reaches `messages`, and no raw `DELETE` SQL keyword appears.

    The target check is AST-based rather than a regex, so neither an alias
    (`from sqlalchemy import delete as _drop`) nor a `<table>.delete()` receiver can slip a
    `messages` delete past it.
    """
    tree = _module_tree()
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_delete_call(node):
            continue
        operands = _delete_operands(node)
        if not any(_names_table(operand, _PERMITTED_DELETE_TABLE) for operand in operands):
            offenders.append(f"delete not targeting {_PERMITTED_DELETE_TABLE}: {ast.unparse(node)}")
        if any(_names_the_messages_table(operand) for operand in operands):
            offenders.append(f"delete naming the messages table: {ast.unparse(node)}")

    assert offenders == []
    assert _delete_aliases(tree) == []
    assert _DELETE_SQL_KEYWORD.search(inspect.getsource(messages_module)) is None


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


# =========================================================================================
# Feature 014, step 001 — settled rows become editable (D1, D2)
#
# Expected values come from `docs/plans/014.entry-editing-and-copy-out/
# 001.settled-edit-backend.md` (Interface intent + DoD), `001.context.md` ("The
# classification, after this step", "Test seeding") and the feature `context.md` (D1, D2,
# R5, R6, R12). Binding: `edit_message_text(connection, user_id, message_id, text) ->
# StreamMessage`, unchanged (status.md `## Skeleton`, Step 001).
# =========================================================================================

#: "Weeks old" (001.context.md "Test seeding") — far before any instant an edit stamps.
WEEKS_OLD = "2026-08-01T10:00:00.000000+00:00"

#: Raw-seeded settled rows for the 014 cases; ascending so list position is decidable.
RAW_WEEKS_OLD_BEFORE = 31
RAW_WEEKS_OLD_TURN = 32
RAW_WEEKS_OLD_AFTER = 33
RAW_SETTLED_DECISION = 34


def _seed_weeks_old_turn(engine: Engine) -> None:
    """Session A: three weeks-old settled entries; the middle one is the turn to edit."""
    for message_id, text, kind in (
        (RAW_WEEKS_OLD_BEFORE, "The partner opened the scene.", "partner"),
        (RAW_WEEKS_OLD_TURN, "Fixed the typpo.", "turn"),
        (RAW_WEEKS_OLD_AFTER, "The partner answered.", "partner"),
    ):
        _insert_message(
            engine,
            message_id=message_id,
            user_id=USER_A,
            session_id=SESSION_A,
            text=text,
            kind=kind,
            settled_at=WEEKS_OLD,
            created_at=WEEKS_OLD,
            updated_at=WEEKS_OLD,
        )


# --- 014 DoD-1: a weeks-old settled turn is edited ----------------------------------------


def test_a_weeks_old_settled_turn_is_edited_and_keeps_its_kind_and_instants__S014_001_DoD1(
    engine: Engine,
) -> None:
    """014 DoD-1 — the returned value has the new text, kind 'turn', `settled_at` and
    `created_at` as seeded, `updated_at` strictly later (US-032.AC-1, US-110.AC-1, D1)."""
    _seed_weeks_old_turn(engine)

    edited = _edit(engine, USER_A, RAW_WEEKS_OLD_TURN, "Fixed the typo.")

    assert isinstance(edited, StreamMessage)
    assert edited.id == RAW_WEEKS_OLD_TURN
    assert edited.session_id == SESSION_A
    assert edited.role == "user"
    assert edited.text == "Fixed the typo."
    assert edited.kind == "turn"
    assert edited.settled_at == WEEKS_OLD
    assert edited.created_at == WEEKS_OLD
    assert edited.updated_at > WEEKS_OLD
    assert FIXED_WIDTH_TIMESTAMP.match(edited.updated_at)


def test_the_stored_settled_row_keeps_its_state_columns__S014_001_DoD1(engine: Engine) -> None:
    """014 DoD-1 — the stored row: new text, kind/settled_at/created_at as seeded,
    `related_to` NULL, `updated_at` equal to the returned one."""
    _seed_weeks_old_turn(engine)

    edited = _edit(engine, USER_A, RAW_WEEKS_OLD_TURN, "Fixed the typo.")
    stored = _stored_message(engine, RAW_WEEKS_OLD_TURN)

    assert stored["text"] == "Fixed the typo."
    assert stored["kind"] == "turn"
    assert stored["settled_at"] == WEEKS_OLD
    assert stored["created_at"] == WEEKS_OLD
    assert stored["related_to"] is None
    assert stored["updated_at"] == edited.updated_at


def test_the_edited_turn_stays_at_its_position_in_the_entries_not_the_zone__S014_001_DoD1(
    engine: Engine,
) -> None:
    """014 DoD-1 — `list_entries` holds the new text at the same position, the neighbours
    untouched; `list_zone` does not contain the row."""
    _seed_weeks_old_turn(engine)
    before = _entries(engine, USER_A, SESSION_A)

    edited = _edit(engine, USER_A, RAW_WEEKS_OLD_TURN, "Fixed the typo.")
    entries = _entries(engine, USER_A, SESSION_A)

    assert _ids(entries) == [RAW_WEEKS_OLD_BEFORE, RAW_WEEKS_OLD_TURN, RAW_WEEKS_OLD_AFTER]
    assert entries[1] == edited
    assert entries[1].text == "Fixed the typo."
    assert entries[0] == before[0]
    assert entries[2] == before[2]
    assert RAW_WEEKS_OLD_TURN not in _ids(_zone(engine, USER_A, SESSION_A))


# --- 014 DoD-2: a filed partner block is edited verbatim ----------------------------------


def test_a_filed_partner_block_is_edited_byte_for_byte__S014_001_DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """014 DoD-2 — `"She waves. ((ooc: brb))"` stored and returned verbatim; kind 'partner'
    and `settled_at` unchanged (US-109.AC-1, US-121.AC-2, R12)."""
    filed = _file(engine, generator, USER_A, SESSION_A, "A pasted partner block.")
    new_text = "She waves. ((ooc: brb))"

    edited = _edit(engine, USER_A, filed.id, new_text)
    stored = _stored_message(engine, filed.id)
    (listed,) = _entries(engine, USER_A, SESSION_A)

    assert edited.id == filed.id
    assert edited.text == new_text
    assert stored["text"] == new_text
    assert listed.text == new_text
    assert edited.kind == "partner"
    assert stored["kind"] == "partner"
    assert listed.kind == "partner"
    assert edited.settled_at == filed.settled_at
    assert stored["settled_at"] == filed.settled_at
    assert stored["related_to"] is None
    assert _zone(engine, USER_A, SESSION_A) == []


# --- 014 DoD-3: literal edits keep the kind -----------------------------------------------


def test_a_settled_decision_edited_into_prose_stays_a_decision__S014_001_DoD3(
    engine: Engine,
) -> None:
    """014 DoD-3 — raw-seeded `((x))` decision edited to `plain words` stays 'decision';
    `settled_at` unchanged (R12, D1)."""
    _insert_message(
        engine,
        message_id=RAW_SETTLED_DECISION,
        user_id=USER_A,
        session_id=SESSION_A,
        text="((x))",
        kind="decision",
        settled_at=WEEKS_OLD,
        created_at=WEEKS_OLD,
        updated_at=WEEKS_OLD,
    )

    edited = _edit(engine, USER_A, RAW_SETTLED_DECISION, "plain words")
    stored = _stored_message(engine, RAW_SETTLED_DECISION)

    assert edited.text == "plain words"
    assert edited.kind == "decision"
    assert edited.settled_at == WEEKS_OLD
    assert stored["text"] == "plain words"
    assert stored["kind"] == "decision"
    assert stored["settled_at"] == WEEKS_OLD
    assert stored["related_to"] is None
    assert _ids(_entries(engine, USER_A, SESSION_A)) == [RAW_SETTLED_DECISION]


def test_a_settled_turn_edited_into_parens_stays_a_turn_verbatim__S014_001_DoD3(
    engine: Engine,
) -> None:
    """014 DoD-3 — a settled turn edited to `((whole thing))` stays 'turn' with that text
    verbatim; `settled_at` unchanged (R12, D1)."""
    _insert_message(
        engine,
        message_id=RAW_SETTLED_TURN,
        user_id=USER_A,
        session_id=SESSION_A,
        text="A settled turn.",
        kind="turn",
        settled_at=WEEKS_OLD,
        created_at=WEEKS_OLD,
        updated_at=WEEKS_OLD,
    )

    edited = _edit(engine, USER_A, RAW_SETTLED_TURN, "((whole thing))")
    stored = _stored_message(engine, RAW_SETTLED_TURN)
    (listed,) = _entries(engine, USER_A, SESSION_A)

    assert edited.text == "((whole thing))"
    assert edited.kind == "turn"
    assert edited.settled_at == WEEKS_OLD
    assert stored["text"] == "((whole thing))"
    assert stored["kind"] == "turn"
    assert stored["settled_at"] == WEEKS_OLD
    assert listed.kind == "turn"
    assert listed.text == "((whole thing))"


# --- 014 DoD-4: a settled edit bumps the session ------------------------------------------


def test_a_settled_edit_bumps_the_session_to_the_rows_instant__S014_001_DoD4(
    engine: Engine,
) -> None:
    """014 DoD-4 — `last_used_at` and `updated_at` both equal the edited row's returned
    `updated_at` (D2, 012 D3); the owner's other session is untouched."""
    _seed_weeks_old_turn(engine)
    other_before = _session_row(engine, SESSION_A2)

    edited = _edit(engine, USER_A, RAW_WEEKS_OLD_TURN, "Fixed the typo.")
    session = _session_row(engine, SESSION_A)

    assert session["last_used_at"] == edited.updated_at
    assert session["updated_at"] == edited.updated_at
    assert _session_row(engine, SESSION_A2) == other_before


# --- 014 DoD-6: another user's settled row is not found (R5) -------------------------------


def test_editing_another_users_settled_row_is_not_found__S014_001_DoD6(engine: Engine) -> None:
    """014 DoD-6 — A editing B's settled row raises `MessageNotFoundError`, the same as an id
    that exists for nobody; the row and B's session are unchanged (R5)."""
    _seed_user_b_stream(engine)
    row_before = _stored_message(engine, RAW_B_SETTLED)
    session_b_before = _session_row(engine, SESSION_B)

    with pytest.raises(MessageNotFoundError):
        _edit(engine, USER_A, RAW_B_SETTLED, "hijacked settled text")
    with pytest.raises(MessageNotFoundError):
        _edit(engine, USER_A, UNKNOWN_MESSAGE_ID, "hijacked settled text")

    assert _stored_message(engine, RAW_B_SETTLED) == row_before
    assert _session_row(engine, SESSION_B) == session_b_before
    assert _ids(_entries(engine, USER_B, SESSION_B)) == [RAW_B_SETTLED]
    assert _entries(engine, USER_B, SESSION_B)[0].text == "Bob's settled entry."


# --- 014 DoD-7: archive is not a lock (R6) ------------------------------------------------


def test_a_settled_edit_succeeds_on_an_archived_session__S014_001_DoD7(engine: Engine) -> None:
    """014 DoD-7 — on a raw-archived session a settled edit succeeds; it stays archived."""
    _seed_weeks_old_turn(engine)
    _archive_session_row(engine, SESSION_A)

    edited = _edit(engine, USER_A, RAW_WEEKS_OLD_TURN, "Edited while archived.")

    assert edited.text == "Edited while archived."
    assert edited.kind == "turn"
    assert edited.settled_at == WEEKS_OLD
    assert _stored_message(engine, RAW_WEEKS_OLD_TURN)["text"] == "Edited while archived."
    assert _session_row(engine, SESSION_A)["archived_at"] == ARCHIVED_AT


# --- 014 DoD-8: source check — no update assigns a state column ---------------------------

_STATE_COLUMNS = {"kind", "settled_at", "related_to"}


def _is_update_call(node: ast.AST) -> bool:
    """`update(...)` / `sa.update(...)` / `<table>.update(...)`."""
    if not isinstance(node, ast.Call):
        return False
    func_node = node.func
    if isinstance(func_node, ast.Name):
        return func_node.id == "update"
    if isinstance(func_node, ast.Attribute):
        return func_node.attr == "update"
    return False


def _chain_contains_update(expression: ast.AST) -> bool:
    """Walk a method chain (`update(t).where(...).values(...)`) down to its root."""
    current: ast.AST | None = expression
    while current is not None:
        if _is_update_call(current):
            return True
        if isinstance(current, ast.Call):
            current = current.func
        elif isinstance(current, ast.Attribute):
            current = current.value
        elif isinstance(current, ast.Subscript):
            current = current.value
        else:
            current = None
    return False


def _assigned_state_columns(call: ast.Call) -> list[str]:
    """State columns named as a keyword, a dict key or a column in a `.values(...)` call."""
    found: list[str] = []
    for keyword in call.keywords:
        if keyword.arg in _STATE_COLUMNS:
            found.append(f"{keyword.arg}= keyword")
    arguments: list[ast.AST] = [*call.args, *(kw.value for kw in call.keywords if kw.arg is None)]
    for argument in arguments:
        for inner in ast.walk(argument):
            if isinstance(inner, ast.Dict):
                for key in inner.keys:
                    if isinstance(key, ast.Constant) and key.value in _STATE_COLUMNS:
                        found.append(f"'{key.value}' dict key")
                    if isinstance(key, ast.Attribute) and key.attr in _STATE_COLUMNS:
                        found.append(f"{ast.unparse(key)} dict key")
            if isinstance(argument, (ast.Tuple, ast.List)) and isinstance(inner, ast.Attribute):
                if inner.attr in _STATE_COLUMNS:
                    found.append(f"{ast.unparse(inner)} in .values()")
    return found


def test_the_module_issues_update_statements__S014_001_DoD8() -> None:
    """014 DoD-8 — guard against a vacuous check: the edit and the bump are UPDATEs, so the
    module contains at least one `update(...)` call."""
    assert any(_is_update_call(node) for node in ast.walk(_module_tree()))


def test_no_update_statement_assigns_kind_settled_at_or_related_to__S014_001_DoD8() -> None:
    """014 DoD-8 — D1, 012 D16: no `update(...)` statement's `.values(...)` assigns `kind`,
    `settled_at` or `related_to` (the edit writes `text` and `updated_at` only)."""
    offenders: list[str] = []
    for node in ast.walk(_module_tree()):
        if not isinstance(node, ast.Call):
            continue
        if _is_update_call(node):
            offenders.extend(_assigned_state_columns(node))
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in {"values", "ordered_values"}
            and _chain_contains_update(node.func.value)
        ):
            offenders.extend(_assigned_state_columns(node))

    assert offenders == []
