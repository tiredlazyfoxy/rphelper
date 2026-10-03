"""Tests for `app/services/memos.py` — feature 015, step 002 (the memos service).

Every expected value comes from the step's Definition of done and the feature context
(D2, D4, D6, D8, D11, D12, D15, R3, R5, R6). The module is called only through the frozen
interface recorded under `## Skeleton` in `docs/plans/015.memos/status.md`:

- `Memo` (frozen dataclass, no `user_id`)
- `create_memo(connection, generator, user_id, scope, scope_id, body) -> Memo`
- `list_memos(connection, user_id, scope, scope_id) -> list[Memo]`
- `update_memo(connection, user_id, memo_id, body=None, is_enabled=None, is_forced=None)`
- `delete_memo(connection, user_id, memo_id) -> None`

Targets (users, characters, setups, sessions) are raw-inserted with their committed
columns; memos are created through the service except where a DoD needs a precise state
(another user's row, chosen `sort_key` values, a disabled or forced row).
"""

from __future__ import annotations

import ast
import inspect
import re
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, func, select

from app.db import schema
from app.errors import (
    CharacterNotFoundError,
    MemoNotFoundError,
    SessionNotFoundError,
    SetupNotFoundError,
)
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services import memos as memos_module
from app.services.memos import Memo, create_memo, delete_memo, list_memos, update_memo

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

USER_A = 101
USER_B = 202

CHAR_A1 = 1_001
CHAR_A2 = 1_002
CHAR_B1 = 1_101

SETUP_A1 = 2_001
SETUP_B1 = 2_101

SESSION_A1 = 3_001
SESSION_B1 = 3_101

UNKNOWN_CHARACTER_ID = 8_888_888_888
UNKNOWN_SETUP_ID = 9_999_999_999
UNKNOWN_SESSION_ID = 7_777_777_777
UNKNOWN_MEMO_ID = 6_666_666_666

#: `YYYY-MM-DDTHH:MM:SS.ffffff+00:00` — the fixed-width form.
FIXED_WIDTH_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00$")

#: The caller's own target at each of the four levels (`None` for the user level).
OWN_TARGETS: list[tuple[str, int | None]] = [
    ("user", None),
    ("character", CHAR_A1),
    ("setup", SETUP_A1),
    ("session", SESSION_A1),
]


class _RecordingIdGenerator:
    """A generator stand-in that issues distinct, known ids and records every call."""

    def __init__(self, start: int) -> None:
        self.next_value = start
        self.issued: list[int] = []

    @property
    def calls(self) -> int:
        return len(self.issued)

    def next_id(self) -> int:
        value = self.next_value
        self.next_value += 1
        self.issued.append(value)
        return value


# --- seeding ------------------------------------------------------------------------------


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
    engine: Engine, *, session_id: int, user_id: int, character_id: int, setup_id: int | None
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.insert().values(
                id=session_id,
                user_id=user_id,
                character_id=character_id,
                setup_id=setup_id,
                last_used_at=TIMESTAMP,
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_memo(
    engine: Engine,
    *,
    memo_id: int,
    user_id: int,
    scope: str,
    scope_id: int,
    sort_key: int,
    body: str = "a raw note",
    is_enabled: bool = True,
    is_forced: bool = False,
) -> None:
    """Raw-insert one `memos` row in a precise state, with fixed-width timestamps."""
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


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """Two owners, each with characters, a setup and a session."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="alice")
    _insert_user(db_engine, user_id=USER_B, username="bob")
    _insert_character(db_engine, character_id=CHAR_A1, user_id=USER_A, name="Aria")
    _insert_character(db_engine, character_id=CHAR_A2, user_id=USER_A, name="Brynn")
    _insert_character(db_engine, character_id=CHAR_B1, user_id=USER_B, name="Bob's own")
    _insert_setup(db_engine, setup_id=SETUP_A1, user_id=USER_A, character_id=CHAR_A1, name="Tavern")
    _insert_setup(db_engine, setup_id=SETUP_B1, user_id=USER_B, character_id=CHAR_B1, name="Dock")
    _insert_session(
        db_engine, session_id=SESSION_A1, user_id=USER_A, character_id=CHAR_A1, setup_id=SETUP_A1
    )
    _insert_session(
        db_engine, session_id=SESSION_B1, user_id=USER_B, character_id=CHAR_B1, setup_id=SETUP_B1
    )
    return db_engine


@pytest.fixture
def generator() -> SnowflakeGenerator:
    return SnowflakeGenerator(node_id=1)


# --- one connection per service call ------------------------------------------------------


def _create(
    engine: Engine,
    generator: Any,
    user_id: int,
    scope: str,
    scope_id: int | None,
    body: str = "a note",
) -> Memo:
    with engine.connect() as connection:
        return create_memo(connection, generator, user_id, scope, scope_id, body)  # type: ignore[arg-type]


def _list(engine: Engine, user_id: int, scope: str, scope_id: int | None) -> list[Memo]:
    with engine.connect() as connection:
        return list_memos(connection, user_id, scope, scope_id)  # type: ignore[arg-type]


def _update(engine: Engine, user_id: int, memo_id: int, **changes: Any) -> Memo:
    with engine.connect() as connection:
        return update_memo(connection, user_id, memo_id, **changes)


def _delete(engine: Engine, user_id: int, memo_id: int) -> object:
    with engine.connect() as connection:
        return delete_memo(connection, user_id, memo_id)  # type: ignore[func-returns-value]


def _stored(engine: Engine, memo_id: int) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = (
            connection.execute(select(schema.memos).where(schema.memos.c.id == memo_id))
            .mappings()
            .first()
        )
    return dict(row) if row is not None else None


def _count_memos(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(schema.memos)).scalar_one())


def _ids(values: list[Memo]) -> list[int]:
    return [value.id for value in values]


def _begin_and_roll_back(connection: Connection) -> None:
    transaction = connection.begin()
    transaction.rollback()


# --- DoD-1: create at each of the four levels -------------------------------------------


@pytest.mark.parametrize(("scope", "scope_id"), OWN_TARGETS)
def test_create_at_each_level_returns_the_new_note__S015_002_DoD1(
    engine: Engine, scope: str, scope_id: int | None
) -> None:
    recording = _RecordingIdGenerator(start=5_000_000_001)

    memo = _create(engine, recording, USER_A, scope, scope_id, "Keep it short.")

    assert isinstance(memo, Memo)
    assert recording.issued == [5_000_000_001]
    assert memo.id == 5_000_000_001
    assert memo.scope == scope
    assert memo.scope_id == scope_id
    assert memo.body == "Keep it short."
    assert memo.is_enabled is True
    assert memo.is_forced is False
    assert memo.sort_key == 0
    assert FIXED_WIDTH_TIMESTAMP.match(memo.created_at)
    assert memo.created_at == memo.updated_at


@pytest.mark.parametrize(("scope", "scope_id"), OWN_TARGETS)
def test_created_row_stores_the_caller_as_owner__S015_002_DoD1(
    engine: Engine, generator: SnowflakeGenerator, scope: str, scope_id: int | None
) -> None:
    memo = _create(engine, generator, USER_A, scope, scope_id)

    stored = _stored(engine, memo.id)
    assert stored is not None
    assert stored["user_id"] == USER_A
    assert stored["scope"] == scope
    expected_stored_scope_id = USER_A if scope == "user" else scope_id
    assert stored["scope_id"] == expected_stored_scope_id


def test_the_value_carries_no_user_id__S015_002_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    memo = _create(engine, generator, USER_A, "character", CHAR_A1)

    assert not hasattr(memo, "user_id")


# --- DoD-2: a user-level create ignores the supplied scope_id ---------------------------


@pytest.mark.parametrize("other_number", [USER_B, CHAR_A1, 424_242])
def test_user_level_create_ignores_the_supplied_scope_id__S015_002_DoD2(
    engine: Engine, generator: SnowflakeGenerator, other_number: int
) -> None:
    memo = _create(engine, generator, USER_A, "user", other_number, "mine only")

    assert memo.scope == "user"
    assert memo.scope_id is None
    stored = _stored(engine, memo.id)
    assert stored is not None
    assert stored["scope_id"] == USER_A
    assert stored["user_id"] == USER_A

    assert memo.id not in _ids(_list(engine, USER_B, "user", None))
    assert memo.id not in _ids(_list(engine, USER_B, "user", USER_B))
    assert memo.id in _ids(_list(engine, USER_A, "user", None))


# --- DoD-3: the body is verbatim ---------------------------------------------------------


def test_body_is_returned_stored_and_listed_verbatim__S015_002_DoD3(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    body = "  # Heading\n\ntext  "

    memo = _create(engine, generator, USER_A, "character", CHAR_A1, body)

    assert memo.body == body
    stored = _stored(engine, memo.id)
    assert stored is not None
    assert stored["body"] == body
    listed = _list(engine, USER_A, "character", CHAR_A1)
    assert [value.body for value in listed if value.id == memo.id] == [body]


# --- DoD-4: sort_key allocation ----------------------------------------------------------


def test_three_creates_at_one_level_get_0_1_2__S015_002_DoD4(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    keys = [_create(engine, generator, USER_A, "setup", SETUP_A1).sort_key for _ in range(3)]

    assert keys == [0, 1, 2]


def test_a_create_at_a_different_level_starts_at_0__S015_002_DoD4(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    for _ in range(3):
        _create(engine, generator, USER_A, "character", CHAR_A1)

    assert _create(engine, generator, USER_A, "character", CHAR_A2).sort_key == 0
    assert _create(engine, generator, USER_A, "user", None).sort_key == 0
    assert _create(engine, generator, USER_A, "session", SESSION_A1).sort_key == 0


def test_allocation_is_one_more_than_the_largest_existing_key__S015_002_DoD4(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    _insert_memo(engine, memo_id=90_001, user_id=USER_A, scope="character", scope_id=CHAR_A1, sort_key=2)
    _insert_memo(engine, memo_id=90_002, user_id=USER_A, scope="character", scope_id=CHAR_A1, sort_key=5)

    assert _create(engine, generator, USER_A, "character", CHAR_A1).sort_key == 6


@pytest.mark.parametrize(
    ("scope", "scope_id", "stored_scope_id"),
    [("character", CHAR_A1, CHAR_A1), ("user", None, USER_A)],
)
def test_another_users_row_at_the_same_level_does_not_affect_allocation__S015_002_DoD4(
    engine: Engine,
    generator: SnowflakeGenerator,
    scope: str,
    scope_id: int | None,
    stored_scope_id: int,
) -> None:
    _insert_memo(
        engine, memo_id=90_010, user_id=USER_B, scope=scope, scope_id=stored_scope_id, sort_key=40
    )

    assert _create(engine, generator, USER_A, scope, scope_id).sort_key == 0
    assert _create(engine, generator, USER_A, scope, scope_id).sort_key == 1


def test_after_deleting_the_highest_the_next_is_one_more_than_the_remaining_max__S015_002_DoD4(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    first = _create(engine, generator, USER_A, "session", SESSION_A1)
    middle = _create(engine, generator, USER_A, "session", SESSION_A1)
    last = _create(engine, generator, USER_A, "session", SESSION_A1)
    assert [first.sort_key, middle.sort_key, last.sort_key] == [0, 1, 2]

    _delete(engine, USER_A, last.id)
    assert _create(engine, generator, USER_A, "session", SESSION_A1).sort_key == 2


def test_gaps_are_left_as_they_are__S015_002_DoD4(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    first = _create(engine, generator, USER_A, "session", SESSION_A1)
    middle = _create(engine, generator, USER_A, "session", SESSION_A1)
    last = _create(engine, generator, USER_A, "session", SESSION_A1)

    _delete(engine, USER_A, middle.id)
    after_gap = _create(engine, generator, USER_A, "session", SESSION_A1)
    assert after_gap.sort_key == 3

    _delete(engine, USER_A, after_gap.id)
    _delete(engine, USER_A, last.id)
    assert _create(engine, generator, USER_A, "session", SESSION_A1).sort_key == 1

    stored_first = _stored(engine, first.id)
    assert stored_first is not None
    assert stored_first["sort_key"] == 0


# --- DoD-5: refused targets --------------------------------------------------------------

REFUSED_TARGETS: list[tuple[str, int, type[Exception]]] = [
    ("character", CHAR_B1, CharacterNotFoundError),
    ("character", UNKNOWN_CHARACTER_ID, CharacterNotFoundError),
    ("setup", SETUP_B1, SetupNotFoundError),
    ("setup", UNKNOWN_SETUP_ID, SetupNotFoundError),
    ("session", SESSION_B1, SessionNotFoundError),
    ("session", UNKNOWN_SESSION_ID, SessionNotFoundError),
]


@pytest.mark.parametrize(("scope", "scope_id", "error"), REFUSED_TARGETS)
def test_create_at_a_foreign_or_unknown_target_is_refused__S015_002_DoD5(
    engine: Engine, scope: str, scope_id: int, error: type[Exception]
) -> None:
    recording = _RecordingIdGenerator(start=5_000_000_100)
    before = _count_memos(engine)

    with pytest.raises(error):
        _create(engine, recording, USER_A, scope, scope_id)

    assert _count_memos(engine) == before
    assert recording.calls == 0


@pytest.mark.parametrize(("scope", "scope_id", "error"), REFUSED_TARGETS)
def test_list_at_a_foreign_or_unknown_target_is_refused__S015_002_DoD5(
    engine: Engine, scope: str, scope_id: int, error: type[Exception]
) -> None:
    with pytest.raises(error):
        _list(engine, USER_A, scope, scope_id)


# --- DoD-6: archived targets are accepted ------------------------------------------------


def _archive_targets(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.characters.update()
            .where(schema.characters.c.id == CHAR_A1)
            .values(archived_at=TIMESTAMP)
        )
        connection.execute(
            schema.setups.update().where(schema.setups.c.id == SETUP_A1).values(archived_at=TIMESTAMP)
        )
        connection.execute(
            schema.sessions.update()
            .where(schema.sessions.c.id == SESSION_A1)
            .values(archived_at=TIMESTAMP)
        )


@pytest.mark.parametrize(
    ("scope", "scope_id"),
    [("character", CHAR_A1), ("setup", SETUP_A1), ("session", SESSION_A1)],
)
def test_create_and_list_succeed_at_archived_targets__S015_002_DoD6(
    engine: Engine, generator: SnowflakeGenerator, scope: str, scope_id: int
) -> None:
    _archive_targets(engine)

    memo = _create(engine, generator, USER_A, scope, scope_id, "still allowed")

    assert memo.scope == scope
    assert memo.scope_id == scope_id
    assert _ids(_list(engine, USER_A, scope, scope_id)) == [memo.id]


# --- DoD-7: list returns exactly the addressed level, ordered ----------------------------


def test_list_returns_only_the_callers_notes_at_the_level__S015_002_DoD7(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    wanted = _create(engine, generator, USER_A, "character", CHAR_A1, "wanted")
    _create(engine, generator, USER_A, "user", None, "user level")
    _create(engine, generator, USER_A, "character", CHAR_A2, "other character")
    _create(engine, generator, USER_A, "setup", SETUP_A1, "setup level")
    _create(engine, generator, USER_A, "session", SESSION_A1, "session level")
    _create(engine, generator, USER_B, "character", CHAR_B1, "bob's character")
    _create(engine, generator, USER_B, "user", None, "bob's user level")
    _insert_memo(
        engine, memo_id=90_020, user_id=USER_B, scope="character", scope_id=CHAR_A1, sort_key=0
    )

    assert _ids(_list(engine, USER_A, "character", CHAR_A1)) == [wanted.id]


def test_user_level_list_omits_another_users_user_level_notes__S015_002_DoD7(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    mine = _create(engine, generator, USER_A, "user", None, "mine")
    _create(engine, generator, USER_B, "user", None, "bob's")
    _insert_memo(engine, memo_id=90_030, user_id=USER_B, scope="user", scope_id=USER_A, sort_key=0)
    _create(engine, generator, USER_A, "character", CHAR_A1, "character level")

    assert _ids(_list(engine, USER_A, "user", None)) == [mine.id]


def test_list_orders_by_sort_key_then_id_and_includes_disabled__S015_002_DoD7(
    engine: Engine,
) -> None:
    # Inserted out of order; 90_104 and 90_102 share sort_key 1.
    _insert_memo(engine, memo_id=90_105, user_id=USER_A, scope="setup", scope_id=SETUP_A1, sort_key=3)
    _insert_memo(engine, memo_id=90_104, user_id=USER_A, scope="setup", scope_id=SETUP_A1, sort_key=1)
    _insert_memo(
        engine,
        memo_id=90_103,
        user_id=USER_A,
        scope="setup",
        scope_id=SETUP_A1,
        sort_key=0,
        is_enabled=False,
    )
    _insert_memo(engine, memo_id=90_102, user_id=USER_A, scope="setup", scope_id=SETUP_A1, sort_key=1)
    _insert_memo(engine, memo_id=90_101, user_id=USER_A, scope="setup", scope_id=SETUP_A1, sort_key=7)

    listed = _list(engine, USER_A, "setup", SETUP_A1)

    assert _ids(listed) == [90_103, 90_102, 90_104, 90_105, 90_101]
    assert [value.sort_key for value in listed] == [0, 1, 1, 3, 7]
    disabled = next(value for value in listed if value.id == 90_103)
    assert disabled.is_enabled is False


def test_listed_user_level_notes_carry_a_null_scope_id__S015_002_DoD7(
    engine: Engine,
) -> None:
    _insert_memo(engine, memo_id=90_201, user_id=USER_A, scope="user", scope_id=USER_A, sort_key=0)

    listed = _list(engine, USER_A, "user", None)

    assert _ids(listed) == [90_201]
    assert listed[0].scope == "user"
    assert listed[0].scope_id is None


# --- DoD-8: update the body alone --------------------------------------------------------


def test_update_with_only_body_changes_only_the_body__S015_002_DoD8(engine: Engine) -> None:
    _insert_memo(
        engine,
        memo_id=90_301,
        user_id=USER_A,
        scope="character",
        scope_id=CHAR_A1,
        sort_key=7,
        body="old",
        is_enabled=False,
        is_forced=True,
    )
    before = _list(engine, USER_A, "character", CHAR_A1)[0]

    after = _update(engine, USER_A, 90_301, body="new body")

    assert after.id == 90_301
    assert after.body == "new body"
    assert after.is_enabled is False
    assert after.is_forced is True
    assert after.sort_key == 7
    assert after.scope == "character"
    assert after.scope_id == CHAR_A1
    assert after.created_at == before.created_at == TIMESTAMP
    assert FIXED_WIDTH_TIMESTAMP.match(after.updated_at)
    assert after.updated_at >= before.updated_at

    assert _list(engine, USER_A, "character", CHAR_A1) == [after]


# --- DoD-9: is_enabled alone never writes is_forced --------------------------------------


def test_disabling_and_re_enabling_a_forced_note_keeps_it_forced__S015_002_DoD9(
    engine: Engine,
) -> None:
    _insert_memo(
        engine,
        memo_id=90_401,
        user_id=USER_A,
        scope="session",
        scope_id=SESSION_A1,
        sort_key=0,
        is_enabled=True,
        is_forced=True,
    )

    disabled = _update(engine, USER_A, 90_401, is_enabled=False)
    assert (disabled.is_enabled, disabled.is_forced) == (False, True)
    stored = _stored(engine, 90_401)
    assert stored is not None
    assert (bool(stored["is_enabled"]), bool(stored["is_forced"])) == (False, True)

    enabled = _update(engine, USER_A, 90_401, is_enabled=True)
    assert (enabled.is_enabled, enabled.is_forced) == (True, True)
    listed = _list(engine, USER_A, "session", SESSION_A1)
    assert [(value.is_enabled, value.is_forced) for value in listed] == [(True, True)]


def test_disabling_and_re_enabling_a_not_forced_note_keeps_it_not_forced__S015_002_DoD9(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    memo = _create(engine, generator, USER_A, "session", SESSION_A1)

    disabled = _update(engine, USER_A, memo.id, is_enabled=False)
    assert (disabled.is_enabled, disabled.is_forced) == (False, False)

    enabled = _update(engine, USER_A, memo.id, is_enabled=True)
    assert (enabled.is_enabled, enabled.is_forced) == (True, False)
    listed = _list(engine, USER_A, "session", SESSION_A1)
    assert [(value.is_enabled, value.is_forced) for value in listed] == [(True, False)]


# --- DoD-10: is_forced alone never writes is_enabled -------------------------------------


def test_forcing_a_disabled_note_leaves_it_disabled__S015_002_DoD10(engine: Engine) -> None:
    _insert_memo(
        engine,
        memo_id=90_501,
        user_id=USER_A,
        scope="setup",
        scope_id=SETUP_A1,
        sort_key=0,
        is_enabled=False,
        is_forced=False,
    )

    forced = _update(engine, USER_A, 90_501, is_forced=True)

    assert (forced.is_enabled, forced.is_forced) == (False, True)
    stored = _stored(engine, 90_501)
    assert stored is not None
    assert (bool(stored["is_enabled"]), bool(stored["is_forced"])) == (False, True)

    unforced = _update(engine, USER_A, 90_501, is_forced=False)
    assert (unforced.is_enabled, unforced.is_forced) == (False, False)


def test_forcing_an_enabled_note_leaves_it_enabled__S015_002_DoD10(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    memo = _create(engine, generator, USER_A, "setup", SETUP_A1)

    forced = _update(engine, USER_A, memo.id, is_forced=True)
    assert (forced.is_enabled, forced.is_forced) == (True, True)

    unforced = _update(engine, USER_A, memo.id, is_forced=False)
    assert (unforced.is_enabled, unforced.is_forced) == (True, False)


# --- DoD-11: nothing supplied writes nothing ---------------------------------------------


def test_update_with_nothing_supplied_returns_the_row_unchanged__S015_002_DoD11(
    engine: Engine,
) -> None:
    _insert_memo(
        engine,
        memo_id=90_601,
        user_id=USER_A,
        scope="character",
        scope_id=CHAR_A1,
        sort_key=4,
        body="as is",
        is_enabled=False,
        is_forced=True,
    )
    before = _list(engine, USER_A, "character", CHAR_A1)[0]
    stored_before = _stored(engine, 90_601)

    after = _update(engine, USER_A, 90_601)

    assert after == before
    assert after.updated_at == TIMESTAMP
    assert _stored(engine, 90_601) == stored_before


# --- DoD-12: another user's or an unknown memo -------------------------------------------


@pytest.mark.parametrize("memo_id", [90_701, UNKNOWN_MEMO_ID])
def test_update_of_a_foreign_or_unknown_memo_is_refused__S015_002_DoD12(
    engine: Engine, memo_id: int
) -> None:
    _insert_memo(
        engine, memo_id=90_701, user_id=USER_B, scope="character", scope_id=CHAR_B1, sort_key=0
    )
    stored_before = _stored(engine, 90_701)

    with pytest.raises(MemoNotFoundError):
        _update(engine, USER_A, memo_id, body="hijacked", is_enabled=False, is_forced=True)

    assert _stored(engine, 90_701) == stored_before


@pytest.mark.parametrize("memo_id", [90_702, UNKNOWN_MEMO_ID])
def test_delete_of_a_foreign_or_unknown_memo_is_refused__S015_002_DoD12(
    engine: Engine, memo_id: int
) -> None:
    _insert_memo(
        engine, memo_id=90_702, user_id=USER_B, scope="character", scope_id=CHAR_B1, sort_key=0
    )
    stored_before = _stored(engine, 90_702)
    before = _count_memos(engine)

    with pytest.raises(MemoNotFoundError):
        _delete(engine, USER_A, memo_id)

    assert _stored(engine, 90_702) == stored_before
    assert _count_memos(engine) == before
    assert _ids(_list(engine, USER_B, "character", CHAR_B1)) == [90_702]


# --- DoD-13: delete removes the row ------------------------------------------------------


def test_delete_removes_the_row_and_only_that_row__S015_002_DoD13(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    keep_first = _create(engine, generator, USER_A, "character", CHAR_A1, "keep one")
    doomed = _create(engine, generator, USER_A, "character", CHAR_A1, "doomed")
    keep_last = _create(engine, generator, USER_A, "character", CHAR_A1, "keep two")

    result = _delete(engine, USER_A, doomed.id)

    assert result is None
    assert _stored(engine, doomed.id) is None
    assert _list(engine, USER_A, "character", CHAR_A1) == [keep_first, keep_last]

    with pytest.raises(MemoNotFoundError):
        _update(engine, USER_A, doomed.id, body="revived")
    with pytest.raises(MemoNotFoundError):
        _delete(engine, USER_A, doomed.id)

    assert _list(engine, USER_A, "character", CHAR_A1) == [keep_first, keep_last]


# --- DoD-14: list leaves no transaction open ---------------------------------------------


@pytest.mark.parametrize(("scope", "scope_id"), OWN_TARGETS)
def test_list_leaves_no_transaction_open__S015_002_DoD14(
    engine: Engine, generator: SnowflakeGenerator, scope: str, scope_id: int | None
) -> None:
    _create(engine, generator, USER_A, scope, scope_id)

    with engine.connect() as connection:
        list_memos(connection, USER_A, scope, scope_id)  # type: ignore[arg-type]
        _begin_and_roll_back(connection)


@pytest.mark.parametrize(("scope", "scope_id", "error"), REFUSED_TARGETS)
def test_a_refused_list_leaves_no_transaction_open__S015_002_DoD14(
    engine: Engine, scope: str, scope_id: int, error: type[Exception]
) -> None:
    with engine.connect() as connection:
        with pytest.raises(error):
            list_memos(connection, USER_A, scope, scope_id)  # type: ignore[arg-type]
        _begin_and_roll_back(connection)


# --- DoD-15: source text checks ----------------------------------------------------------

_FASTAPI_IMPORT = re.compile(r"^\s*(?:from|import)\s+fastapi\b", re.MULTILINE)
_FORBIDDEN_IMPORT_ROOT = "app.services"


def test_the_service_module_has_no_fastapi_import__S015_002_DoD15() -> None:
    source = inspect.getsource(memos_module)

    assert _FASTAPI_IMPORT.search(source) is None
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert node.module != "fastapi" and not node.module.startswith("fastapi.")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "fastapi" and not alias.name.startswith("fastapi.")


def test_the_service_module_imports_no_other_service__S015_002_DoD15() -> None:
    tree = ast.parse(inspect.getsource(memos_module))

    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level > 0:
                offenders.append(f"relative import, level {node.level}")
            elif node.module is not None and (
                node.module == _FORBIDDEN_IMPORT_ROOT
                or node.module.startswith(_FORBIDDEN_IMPORT_ROOT + ".")
            ):
                offenders.append(f"from {node.module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == _FORBIDDEN_IMPORT_ROOT or alias.name.startswith(
                    _FORBIDDEN_IMPORT_ROOT + "."
                ):
                    offenders.append(f"import {alias.name}")

    assert offenders == []


def test_the_service_module_never_mentions_archived_at_or_title__S015_002_DoD15() -> None:
    source = inspect.getsource(memos_module)

    assert "archived_at" not in source
    assert "title" not in source
