"""Feature 018, step 001 — the shared, transaction-neutral zone insert in
`app/services/messages.py`, and `append_message` running through it.

Expected values come from `docs/plans/018.character-page/001.zone-insert-and-models.md`
(Interface intent, DoD-1..4) and the feature `context.md` (**D3** — one transaction, one
insert; the Wire contract's "current-zone row"; "Test conventions"). Tests are suffixed
`__S018_001_DoD<n>`.

Seeding follows 011 / 012's service tests: a file-local `engine` fixture applies the
registry with `schema.metadata.create_all`, then raw-inserts users, characters and sessions
(the FK chain). Two users for isolation. **No fixture is added to `conftest.py`.**
"""

import ast
import inspect
import re
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, func, select

from app.db import schema
from app.errors import SessionNotFoundError
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services.messages import (
    StreamMessage,
    append_message,
    insert_zone_message,
    list_zone,
)

#: The seeded instant — older than anything an operation stamps today.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

#: The instant the caller hands the helper to stamp (fixed-width form, distinct from the seed).
NOW = "2026-10-03T09:30:00.123456+00:00"

USER_A = 101
USER_B = 202

CHAR_A1 = 1_001
CHAR_B1 = 2_001

SESSION_A = 5_001
SESSION_A2 = 5_002
SESSION_B = 6_001


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
    return SnowflakeGenerator(node_id=1)


# --- direct reads of stored state --------------------------------------------------------


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


def _insert_in_committed_transaction(
    engine: Engine, generator: Any, user_id: int, session_id: int, text: str, now: str
) -> StreamMessage:
    """The caller owns the transaction (D3): open it, call the helper, commit."""
    with engine.connect() as connection:
        with connection.begin():
            return insert_zone_message(connection, generator, user_id, session_id, text, now)


# ====================================================================== DoD-1
# The helper inserts one current-zone user row (R11) and returns it.


def test_the_helper_inserts_exactly_one_row_for_the_given_session__S018_001_DoD1(
    engine: Engine,
) -> None:
    """DoD-1 — inside the caller's open transaction, exactly one row is added, and it is
    for the given session."""
    assert _count_messages(engine) == 0

    _insert_in_committed_transaction(
        engine, _FixedIdGenerator(424_242), USER_A, SESSION_A, "Opening line.", NOW
    )

    rows = _all_messages(engine)
    assert len(rows) == 1
    assert rows[0]["session_id"] == SESSION_A


def test_the_stored_row_is_a_current_zone_user_row__S018_001_DoD1(engine: Engine) -> None:
    """DoD-1 — read back: role "user"; kind, settled_at and related_to NULL; owned by the
    caller; both timestamps the given timestamp."""
    _insert_in_committed_transaction(
        engine, _FixedIdGenerator(424_243), USER_A, SESSION_A, "Opening line.", NOW
    )

    (stored,) = _all_messages(engine)
    assert stored["id"] == 424_243
    assert stored["role"] == "user"
    assert stored["kind"] is None
    assert stored["settled_at"] is None
    assert stored["related_to"] is None
    assert stored["user_id"] == USER_A
    assert stored["session_id"] == SESSION_A
    assert stored["created_at"] == NOW
    assert stored["updated_at"] == NOW


@pytest.mark.parametrize(
    "text",
    [
        "  Aria leans in, whispering.\n",
        "\n\nLeading newlines, trailing spaces   ",
        "Line one.\r\nLine two.\n\n\tIndented ((ooc)) line.\n",
        "Unicode — «кавычки» and emoji ✨  ",
    ],
    ids=["lead-trail", "newlines-spaces", "crlf-tabs", "unicode"],
)
def test_the_stored_text_is_verbatim__S018_001_DoD1(engine: Engine, text: str) -> None:
    """DoD-1 — text equals the given text byte for byte; leading / trailing whitespace and
    newlines are kept."""
    created = _insert_in_committed_transaction(
        engine, _FixedIdGenerator(424_244), USER_A, SESSION_A, text, NOW
    )

    (stored,) = _all_messages(engine)
    assert stored["text"] == text
    assert stored["text"].encode("utf-8") == text.encode("utf-8")
    assert created.text == text


def test_the_returned_value_carries_the_generators_next_id__S018_001_DoD1(
    engine: Engine,
) -> None:
    """DoD-1 — the returned message value's id equals the generator's next id; one id is
    minted; the value describes the inserted zone row."""
    fixed = _FixedIdGenerator(535_353)

    created = _insert_in_committed_transaction(
        engine, fixed, USER_A, SESSION_A, "Opening line.", NOW
    )

    assert isinstance(created, StreamMessage)
    assert fixed.calls == 1
    assert created.id == 535_353
    assert created.session_id == SESSION_A
    assert created.role == "user"
    assert created.kind is None
    assert created.settled_at is None
    assert created.created_at == NOW
    assert created.updated_at == NOW


def test_the_inserted_row_is_in_the_sessions_zone__S018_001_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-1 — R11: a zone row, so 012's zone read for that session lists it, and no other
    session's zone does."""
    created = _insert_in_committed_transaction(
        engine, generator, USER_A, SESSION_A, "Opening line.", NOW
    )

    with engine.connect() as connection:
        zone = list_zone(connection, USER_A, SESSION_A)
        other = list_zone(connection, USER_A, SESSION_A2)

    assert [message.id for message in zone] == [created.id]
    assert other == []


# ====================================================================== DoD-2
# The helper opens no transaction and does not bump the session (the caller owns both).


def test_the_helper_runs_inside_an_already_open_transaction__S018_001_DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-2 — calling it while the caller's transaction is open succeeds (a nested
    `begin()` on the same connection would raise), and the transaction is still the
    caller's afterwards."""
    with engine.connect() as connection:
        transaction = connection.begin()
        insert_zone_message(connection, generator, USER_A, SESSION_A, "Inside.", NOW)
        assert connection.in_transaction()
        assert transaction.is_active
        transaction.commit()

    assert _count_messages(engine) == 1


def test_a_caller_rollback_leaves_no_row__S018_001_DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-2 — the insert belongs to the caller's transaction: rolling it back leaves no
    row."""
    with engine.connect() as connection:
        transaction = connection.begin()
        insert_zone_message(connection, generator, USER_A, SESSION_A, "Rolled back.", NOW)
        transaction.rollback()

    assert _count_messages(engine) == 0
    assert _all_messages(engine) == []


def test_a_caller_rollback_after_an_exception_leaves_no_row__S018_001_DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-2 — the same through `with connection.begin():` exiting on an error."""

    class _Abort(Exception):
        pass

    with engine.connect() as connection:
        with pytest.raises(_Abort):
            with connection.begin():
                insert_zone_message(connection, generator, USER_A, SESSION_A, "Doomed.", NOW)
                raise _Abort

    assert _count_messages(engine) == 0


def test_the_helper_does_not_bump_the_session__S018_001_DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-2 — after a committed insert, the session's `last_used_at` and `updated_at` are
    still the seeded values, not the stamped timestamp."""
    before = _session_row(engine, SESSION_A)

    _insert_in_committed_transaction(engine, generator, USER_A, SESSION_A, "No bump.", NOW)

    after = _session_row(engine, SESSION_A)
    assert after["last_used_at"] == before["last_used_at"] == TIMESTAMP
    assert after["updated_at"] == before["updated_at"] == TIMESTAMP


def test_the_helper_leaves_the_connection_without_a_transaction_it_opened__S018_001_DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-2 — the caller's rollback ends the only transaction: a fresh `begin()` on the
    same connection afterwards succeeds."""
    with engine.connect() as connection:
        transaction = connection.begin()
        insert_zone_message(connection, generator, USER_A, SESSION_A, "x", NOW)
        transaction.rollback()
        _begin_and_roll_back(connection)


def _begin_and_roll_back(connection: Connection) -> None:
    assert not connection.in_transaction()
    connection.begin().rollback()


# ====================================================================== DoD-3
# `append_message` still behaves as 012 built it.


def _append(
    engine: Engine, generator: Any, user_id: int, session_id: int, text: str
) -> StreamMessage:
    with engine.connect() as connection:
        return append_message(connection, generator, user_id, session_id, text)


def test_append_still_appends_a_zone_row_for_the_callers_session__S018_001_DoD3(
    engine: Engine,
) -> None:
    """DoD-3 — the stored row is a current-zone user row for the caller's session, with the
    generator's id and the text verbatim, and it is in that session's zone."""
    fixed = _FixedIdGenerator(626_262)
    text = "  Aria leans in.\n"

    created = _append(engine, fixed, USER_A, SESSION_A, text)

    assert isinstance(created, StreamMessage)
    assert created.id == 626_262
    assert created.session_id == SESSION_A
    assert created.role == "user"
    assert created.kind is None
    assert created.settled_at is None
    assert created.text == text

    (stored,) = _all_messages(engine)
    assert stored["id"] == 626_262
    assert stored["user_id"] == USER_A
    assert stored["session_id"] == SESSION_A
    assert stored["role"] == "user"
    assert stored["kind"] is None
    assert stored["settled_at"] is None
    assert stored["related_to"] is None
    assert stored["text"] == text
    assert stored["created_at"] == created.created_at
    assert stored["updated_at"] == created.updated_at

    with engine.connect() as connection:
        zone = list_zone(connection, USER_A, SESSION_A)
    assert [message.id for message in zone] == [626_262]


def test_append_still_bumps_last_used_at__S018_001_DoD3(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-3 — the session's `last_used_at` moves off the seeded value to the appended
    row's instant."""
    created = _append(engine, generator, USER_A, SESSION_A, "Bump me.")

    session = _session_row(engine, SESSION_A)
    assert session["last_used_at"] != TIMESTAMP
    assert session["last_used_at"] == created.updated_at


def test_append_refuses_another_users_session_and_inserts_nothing__S018_001_DoD3(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-3 — user A addressing user B's session raises `session_not_found`; no row is
    inserted and B's session is not bumped."""
    before = _session_row(engine, SESSION_B)

    with pytest.raises(SessionNotFoundError) as raised:
        _append(engine, generator, USER_A, SESSION_B, "Not yours.")

    assert raised.value.code == "session_not_found"
    assert _count_messages(engine) == 0
    after = _session_row(engine, SESSION_B)
    assert after["last_used_at"] == before["last_used_at"]
    assert after["updated_at"] == before["updated_at"]


# ====================================================================== DoD-4
# D3 — one insert: the zone insert exists once, in the helper.

_RAW_INSERT_INTO_MESSAGES = re.compile(r"\bINSERT\s+INTO\s+[\"'`]?messages\b", re.IGNORECASE)


def _names_the_messages_table(node: ast.AST) -> bool:
    """True if the expression mentions the `messages` Table (bare or `schema.messages`)."""
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name) and inner.id == "messages":
            return True
        if isinstance(inner, ast.Attribute) and inner.attr == "messages":
            return True
    return False


def _messages_insert_count(function: Any) -> int:
    """Direct inserts into `messages` in a function's own source: `messages.insert()`,
    `insert(messages)` and raw `INSERT INTO messages`."""
    source = inspect.getsource(function)
    tree = ast.parse(source)
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_node = node.func
        if isinstance(func_node, ast.Attribute) and func_node.attr == "insert":
            if _names_the_messages_table(func_node.value):
                count += 1
                continue
        is_bare_insert = (isinstance(func_node, ast.Name) and func_node.id == "insert") or (
            isinstance(func_node, ast.Attribute) and func_node.attr == "insert"
        )
        if is_bare_insert and node.args and _names_the_messages_table(node.args[0]):
            count += 1
    count += len(_RAW_INSERT_INTO_MESSAGES.findall(source))
    return count


def test_append_message_has_no_direct_messages_insert__S018_001_DoD4() -> None:
    """DoD-4 — `append_message`'s own source contains no direct `messages` insert."""
    assert _messages_insert_count(append_message) == 0


def test_append_message_inserts_through_the_helper__S018_001_DoD4() -> None:
    """DoD-4 / Interface intent — its insert is replaced by a call to the helper."""
    tree = ast.parse(inspect.getsource(append_message))
    called = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    assert "insert_zone_message" in called


def test_the_helper_contains_exactly_one_messages_insert__S018_001_DoD4() -> None:
    """DoD-4 — the helper's source contains exactly one `messages` insert: the zone insert
    exists once."""
    assert _messages_insert_count(insert_zone_message) == 1
