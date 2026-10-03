"""Tests for `app/services/sessions.py` — feature 011, step 002.

Every expected value comes from `docs/plans/011.rp-sessions/002.sessions-service.md` (its
Definition of done and Interface intent), from `002.context.md` (the scope-predicate table,
the test-seeding note, "Returning the value after a write") and from the feature
`context.md`'s **D2** (an archived character is allowed; the setup must be the caller's
under that character; an archived setup is refused), **D3** (reads never bump
`last_used_at`), **D10** (the setup-name join, present even for an archived setup),
**D12** (the codes and the check order), **D13** (archive / restore no-ops), **D14** (the
order `last_used_at DESC, id DESC`) plus the owner-scope (R5), no-delete (R6),
no-default-setup (R2) and no-model-capture (R4 deferred) constraints. Each test name ends
`__S011_002_DoD<n>` with the DoD item it covers.

The file follows `tests/test_setups_service.py`'s pattern: a file-local `engine` fixture
that applies the registry with `schema.metadata.create_all`, one connection per service
call (writes too — the service opens its own transaction), the real `SnowflakeGenerator`
for ordinary tests and a file-local fake where a known minted id matters. **No fixture is
added to `conftest.py`.**

`sessions.user_id`, `.character_id` and `.setup_id` are real foreign keys, so the FK chain
is seeded in order: users, then characters (a raw insert), then setups (a raw insert — this
module offers no setup operation), then sessions through `start_session`, except DoD-7's
deliberately out-of-creation-order rows, which are raw inserts.
"""

import ast
import inspect
import re
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, func, select

from app.db import schema
from app.errors import (
    CharacterNotFoundError,
    SessionNotFoundError,
    SetupArchivedError,
    SetupNotFoundError,
)
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services import sessions as sessions_module
from app.services.messages import StreamMessage
from app.services.sessions import (
    RpSession,
    StartedSession,
    archive_session,
    get_session,
    list_character_sessions,
    list_sessions,
    restore_session,
    start_seeded_session,
    start_session,
)

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

USER_A = 101
USER_B = 202

#: Characters seeded by the `engine` fixture. `CHAR_A_ARCHIVED` carries `archived_at`.
CHAR_A1 = 1_001
CHAR_A2 = 1_002
CHAR_A_ARCHIVED = 1_003
CHAR_B1 = 2_001

#: Setups seeded by the `engine` fixture, with their names.
SETUP_A1 = 3_001
SETUP_A1_NAME = "Tavern scene"
SETUP_A1_ARCHIVED = 3_002
SETUP_A1_ARCHIVED_NAME = "Retired scene"
SETUP_A2 = 3_003
SETUP_A2_NAME = "Another character's scene"
SETUP_B1 = 4_001
SETUP_B1_NAME = "Bob's scene"

#: Ids that belong to no row of any user.
UNKNOWN_CHARACTER_ID = 8_888_888_888
UNKNOWN_SETUP_ID = 9_999_999_999
UNKNOWN_SESSION_ID = 7_777_777_777

#: `YYYY-MM-DDTHH:MM:SS.ffffff+00:00` — the fixed-width form (DoD-1, DoD-10).
FIXED_WIDTH_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00$")


class _FixedIdGenerator:
    """A generator stand-in whose ``next_id()`` always answers one known value."""

    def __init__(self, value: int) -> None:
        self.value = value
        self.calls = 0

    def next_id(self) -> int:
        self.calls += 1
        return self.value


def _insert_user(engine: Engine, *, user_id: int, username: str) -> None:
    """Seed one owner row — the first link of the FK chain."""
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


def _insert_character(
    engine: Engine,
    *,
    character_id: int,
    user_id: int,
    name: str,
    sheet: str = "",
    archived_at: str | None = None,
) -> None:
    """Seed one parent character with a raw insert: this module has no create-character."""
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
            )
        )


def _insert_setup(
    engine: Engine,
    *,
    setup_id: int,
    user_id: int,
    character_id: int,
    name: str,
    description: str = "",
    archived_at: str | None = None,
) -> None:
    """Seed one setup with a raw insert: this module has no create-setup either."""
    with engine.begin() as connection:
        connection.execute(
            schema.setups.insert().values(
                id=setup_id,
                user_id=user_id,
                character_id=character_id,
                name=name,
                description=description,
                archived_at=archived_at,
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
    last_used_at: str,
    created_at: str,
    setup_id: int | None = None,
    archived_at: str | None = None,
) -> None:
    """Seed one session row directly, with a chosen `last_used_at` (DoD-7 only)."""
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.insert().values(
                id=session_id,
                user_id=user_id,
                character_id=character_id,
                setup_id=setup_id,
                last_used_at=last_used_at,
                archived_at=archived_at,
                created_at=created_at,
                updated_at=created_at,
            )
        )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database with the registry applied, two owners, four characters, four setups."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="alice")
    _insert_user(db_engine, user_id=USER_B, username="bob")
    _insert_character(db_engine, character_id=CHAR_A1, user_id=USER_A, name="Aria")
    _insert_character(db_engine, character_id=CHAR_A2, user_id=USER_A, name="Brynn")
    _insert_character(
        db_engine,
        character_id=CHAR_A_ARCHIVED,
        user_id=USER_A,
        name="Retired",
        archived_at=TIMESTAMP,
    )
    _insert_character(db_engine, character_id=CHAR_B1, user_id=USER_B, name="Bob's own")
    _insert_setup(
        db_engine,
        setup_id=SETUP_A1,
        user_id=USER_A,
        character_id=CHAR_A1,
        name=SETUP_A1_NAME,
    )
    _insert_setup(
        db_engine,
        setup_id=SETUP_A1_ARCHIVED,
        user_id=USER_A,
        character_id=CHAR_A1,
        name=SETUP_A1_ARCHIVED_NAME,
        archived_at=TIMESTAMP,
    )
    _insert_setup(
        db_engine,
        setup_id=SETUP_A2,
        user_id=USER_A,
        character_id=CHAR_A2,
        name=SETUP_A2_NAME,
    )
    _insert_setup(
        db_engine,
        setup_id=SETUP_B1,
        user_id=USER_B,
        character_id=CHAR_B1,
        name=SETUP_B1_NAME,
    )
    return db_engine


@pytest.fixture
def generator() -> SnowflakeGenerator:
    """One real generator per test, so ids minted within a test never collide."""
    return SnowflakeGenerator(node_id=1)


def _start(
    engine: Engine,
    generator: Any,
    user_id: int,
    character_id: int,
    setup_id: int | None = None,
) -> RpSession:
    with engine.connect() as connection:
        return start_session(connection, generator, user_id, character_id, setup_id)


def _start_without_the_setup_argument(
    engine: Engine, generator: Any, user_id: int, character_id: int
) -> RpSession:
    """`setup_id` left at its declared default — the omitted-setup call shape (R2)."""
    with engine.connect() as connection:
        return start_session(connection, generator, user_id, character_id)


def _list(engine: Engine, user_id: int) -> list[RpSession]:
    """The all-characters listing, flag left at its default."""
    with engine.connect() as connection:
        return list_sessions(connection, user_id)


def _list_all(engine: Engine, user_id: int) -> list[RpSession]:
    with engine.connect() as connection:
        return list_sessions(connection, user_id, include_archived=True)


def _list_character(engine: Engine, user_id: int, character_id: int) -> list[RpSession]:
    with engine.connect() as connection:
        return list_character_sessions(connection, user_id, character_id)


def _list_character_all(engine: Engine, user_id: int, character_id: int) -> list[RpSession]:
    with engine.connect() as connection:
        return list_character_sessions(connection, user_id, character_id, include_archived=True)


def _get(engine: Engine, user_id: int, session_id: int) -> RpSession:
    with engine.connect() as connection:
        return get_session(connection, user_id, session_id)


def _archive(engine: Engine, user_id: int, session_id: int) -> RpSession:
    with engine.connect() as connection:
        return archive_session(connection, user_id, session_id)


def _restore(engine: Engine, user_id: int, session_id: int) -> RpSession:
    with engine.connect() as connection:
        return restore_session(connection, user_id, session_id)


def _ids(values: list[RpSession]) -> list[int]:
    return [value.id for value in values]


def _count_sessions(engine: Engine) -> int:
    """Rows in the `sessions` table, counted directly (DoD-3, DoD-4, DoD-5)."""
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(schema.sessions)).scalar_one())


def _count_setups(engine: Engine) -> int:
    """Rows in the `setups` table, counted directly (DoD-15)."""
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(schema.setups)).scalar_one())


def _stored_state(engine: Engine, session_id: int) -> tuple[str | None, str, str]:
    """`(archived_at, last_used_at, updated_at)` read straight from the row (DoD-9, DoD-12)."""
    with engine.connect() as connection:
        row = connection.execute(
            select(
                schema.sessions.c.archived_at,
                schema.sessions.c.last_used_at,
                schema.sessions.c.updated_at,
            ).where(schema.sessions.c.id == session_id)
        ).one()
    return (row[0], row[1], row[2])


def _archive_setup_row(engine: Engine, setup_id: int) -> None:
    """Archive a setup with a raw update — this module never writes to `setups` (DoD-13)."""
    with engine.begin() as connection:
        connection.execute(
            schema.setups.update()
            .where(schema.setups.c.id == setup_id)
            .values(archived_at=TIMESTAMP)
        )


# --- DoD-1: start with no setup ----------------------------------------------------------


def test_start_with_no_setup_returns_the_minted_id_and_one_instant__S011_002_DoD1(
    engine: Engine,
) -> None:
    """DoD-1 — the returned value carries the generator's id, the addressed character, a
    null `setup_id` / `setup_name` / `archived_at`, and one instant stamped into all three
    timestamps in the fixed-width form (US-026.AC-1, US-024.AC-1, D3)."""
    fixed = _FixedIdGenerator(77_777)

    created = _start_without_the_setup_argument(engine, fixed, USER_A, CHAR_A1)

    assert created.id == 77_777
    assert created.character_id == CHAR_A1
    assert created.setup_id is None
    assert created.setup_name is None
    assert created.archived_at is None
    assert created.created_at == created.updated_at == created.last_used_at
    assert FIXED_WIDTH_TIMESTAMP.match(created.created_at)
    assert FIXED_WIDTH_TIMESTAMP.match(created.updated_at)
    assert FIXED_WIDTH_TIMESTAMP.match(created.last_used_at)


def test_an_explicit_none_setup_id_starts_a_session_with_no_setup__S011_002_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-1 — passing `None` explicitly is the same request as omitting it (R2)."""
    created = _start(engine, generator, USER_A, CHAR_A1, None)

    assert created.setup_id is None
    assert created.setup_name is None


def test_the_started_session_reads_back_and_lists_in_both_listings__S011_002_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-1 — `get_session` answers an equal value, and both listings contain it."""
    created = _start(engine, generator, USER_A, CHAR_A1)

    assert _get(engine, USER_A, created.id) == created
    assert created in _list(engine, USER_A)
    assert created in _list_character(engine, USER_A, CHAR_A1)


# --- DoD-2: start with the caller's setup under the same character -----------------------


def test_start_with_the_characters_own_setup_carries_its_name__S011_002_DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-2 — the chosen setup's id comes back with `setup_name` equal to the setup's
    current name, joined at read time (US-025.AC-1, D10)."""
    created = _start(engine, generator, USER_A, CHAR_A1, SETUP_A1)

    assert created.setup_id == SETUP_A1
    assert created.setup_name == SETUP_A1_NAME


def test_two_sessions_may_share_one_setup__S011_002_DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-2 — one setup backs several sessions, and both list with its id and name
    (UC-022, D10)."""
    first = _start(engine, generator, USER_A, CHAR_A1, SETUP_A1)
    second = _start(engine, generator, USER_A, CHAR_A1, SETUP_A1)

    assert first.id != second.id
    for listing in (_list(engine, USER_A), _list_character(engine, USER_A, CHAR_A1)):
        assert sorted(_ids(listing)) == sorted([first.id, second.id])
        assert [row.setup_id for row in listing] == [SETUP_A1, SETUP_A1]
        assert [row.setup_name for row in listing] == [SETUP_A1_NAME, SETUP_A1_NAME]


# --- DoD-3: a foreign or nonexistent parent character; the archived one is allowed -------


@pytest.mark.parametrize(
    "character_id",
    [CHAR_B1, UNKNOWN_CHARACTER_ID],
    ids=["another-users-character", "nobodys-character"],
)
def test_start_under_a_parent_that_is_not_the_callers_is_refused__S011_002_DoD3(
    engine: Engine, generator: SnowflakeGenerator, character_id: int
) -> None:
    """DoD-3 — another user's character id and an id that exists for nobody follow the same
    path: `CharacterNotFoundError`, and nothing is inserted (R5, D2, D12)."""
    before = _count_sessions(engine)

    with pytest.raises(CharacterNotFoundError):
        _start(engine, generator, USER_A, character_id)

    assert _count_sessions(engine) == before


@pytest.mark.parametrize(
    "character_id",
    [CHAR_B1, UNKNOWN_CHARACTER_ID],
    ids=["another-users-character", "nobodys-character"],
)
def test_the_per_character_listing_refuses_a_foreign_parent__S011_002_DoD3(
    engine: Engine, character_id: int
) -> None:
    """DoD-3 — the per-character listing answers an error, not an empty list (R5, D12)."""
    with pytest.raises(CharacterNotFoundError):
        _list_character(engine, USER_A, character_id)

    with pytest.raises(CharacterNotFoundError):
        _list_character_all(engine, USER_A, character_id)


def test_a_refused_start_adds_no_row_to_an_already_populated_table__S011_002_DoD3(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-3 — the refused insert leaves the row count exactly as it was."""
    _start(engine, generator, USER_A, CHAR_A1)
    before = _count_sessions(engine)

    with pytest.raises(CharacterNotFoundError):
        _start(engine, generator, USER_A, CHAR_B1)

    assert _count_sessions(engine) == before


def test_start_and_listing_under_the_callers_archived_character_succeed__S011_002_DoD3(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-3 — the parent check carries no `archived_at` predicate (D2)."""
    created = _start(engine, generator, USER_A, CHAR_A_ARCHIVED)

    assert created.character_id == CHAR_A_ARCHIVED
    assert created.archived_at is None
    assert _ids(_list_character(engine, USER_A, CHAR_A_ARCHIVED)) == [created.id]
    assert _ids(_list_character_all(engine, USER_A, CHAR_A_ARCHIVED)) == [created.id]


# --- DoD-4: a setup that is not the caller's under that character ------------------------


@pytest.mark.parametrize(
    "setup_id",
    [SETUP_B1, UNKNOWN_SETUP_ID, SETUP_A2],
    ids=["another-users-setup", "nobodys-setup", "callers-setup-under-another-character"],
)
def test_a_setup_outside_this_character_is_not_found__S011_002_DoD4(
    engine: Engine, generator: SnowflakeGenerator, setup_id: int
) -> None:
    """DoD-4 — another user's setup, a setup that exists for nobody, and the caller's own
    setup under another of the caller's characters all raise `SetupNotFoundError`, and no
    session row is inserted (D12, R5)."""
    before = _count_sessions(engine)

    with pytest.raises(SetupNotFoundError):
        _start(engine, generator, USER_A, CHAR_A1, setup_id)

    assert _count_sessions(engine) == before


# --- DoD-5: the caller's archived setup under that character -----------------------------


def test_the_callers_archived_setup_is_refused_as_a_conflict__S011_002_DoD5(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-5 — the setup is the caller's under that character but archived, so the refusal
    is `SetupArchivedError`, not `SetupNotFoundError`, and nothing is inserted (D2, D12)."""
    before = _count_sessions(engine)

    with pytest.raises(SetupArchivedError):
        _start(engine, generator, USER_A, CHAR_A1, SETUP_A1_ARCHIVED)

    assert _count_sessions(engine) == before


# --- DoD-6: both listings are owner-scoped ----------------------------------------------


def test_the_all_characters_listing_carries_only_the_callers_sessions__S011_002_DoD6(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-6 — with two users each owning a character with sessions, `list_sessions`
    answers only the caller's rows, with and without the flag (US-029.AC-1, R5)."""
    mine = _start(engine, generator, USER_A, CHAR_A1)
    my_other = _start(engine, generator, USER_A, CHAR_A2)
    my_archived = _start(engine, generator, USER_A, CHAR_A1)
    _archive(engine, USER_A, my_archived.id)
    theirs = _start(engine, generator, USER_B, CHAR_B1)
    theirs_archived = _start(engine, generator, USER_B, CHAR_B1)
    _archive(engine, USER_B, theirs_archived.id)

    assert sorted(_ids(_list(engine, USER_A))) == sorted([mine.id, my_other.id])
    assert sorted(_ids(_list_all(engine, USER_A))) == sorted(
        [mine.id, my_other.id, my_archived.id]
    )
    assert _ids(_list(engine, USER_B)) == [theirs.id]
    assert sorted(_ids(_list_all(engine, USER_B))) == sorted([theirs.id, theirs_archived.id])


def test_the_per_character_listing_carries_only_that_characters_sessions__S011_002_DoD6(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-6 — the per-character listing is scoped to one owner and one character, with and
    without the flag; the caller's other character's sessions are excluded too (R5)."""
    mine = _start(engine, generator, USER_A, CHAR_A1)
    my_other = _start(engine, generator, USER_A, CHAR_A2)
    my_archived = _start(engine, generator, USER_A, CHAR_A1)
    _archive(engine, USER_A, my_archived.id)
    theirs = _start(engine, generator, USER_B, CHAR_B1)

    assert _ids(_list_character(engine, USER_A, CHAR_A1)) == [mine.id]
    assert sorted(_ids(_list_character_all(engine, USER_A, CHAR_A1))) == sorted(
        [mine.id, my_archived.id]
    )
    assert _ids(_list_character(engine, USER_A, CHAR_A2)) == [my_other.id]
    assert _ids(_list_character(engine, USER_B, CHAR_B1)) == [theirs.id]


# --- DoD-7: the order is by last use, not by creation -----------------------------------

#: Three rows whose `last_used_at` order is deliberately not their `created_at` order.
OUT_OF_ORDER_FIRST = 5_001
OUT_OF_ORDER_SECOND = 5_002
OUT_OF_ORDER_THIRD = 5_003


def _seed_out_of_order_sessions(engine: Engine) -> None:
    """Created 1 → 2 → 3; last used 3 (January) < 1 (March) < 2 (May)."""
    _insert_session(
        engine,
        session_id=OUT_OF_ORDER_FIRST,
        user_id=USER_A,
        character_id=CHAR_A1,
        created_at="2026-01-01T00:00:01.000000+00:00",
        last_used_at="2026-03-01T12:00:00.000000+00:00",
    )
    _insert_session(
        engine,
        session_id=OUT_OF_ORDER_SECOND,
        user_id=USER_A,
        character_id=CHAR_A1,
        created_at="2026-01-01T00:00:02.000000+00:00",
        last_used_at="2026-05-01T12:00:00.000000+00:00",
    )
    _insert_session(
        engine,
        session_id=OUT_OF_ORDER_THIRD,
        user_id=USER_A,
        character_id=CHAR_A1,
        created_at="2026-01-01T00:00:03.000000+00:00",
        last_used_at="2026-01-01T12:00:00.000000+00:00",
    )


def test_both_listings_order_by_last_use_not_by_creation__S011_002_DoD7(
    engine: Engine,
) -> None:
    """DoD-7 — rows whose `last_used_at` disagrees with their `created_at` come back in
    `last_used_at` descending order from both listings (US-028.AC-1, D14)."""
    _seed_out_of_order_sessions(engine)
    by_last_use = [OUT_OF_ORDER_SECOND, OUT_OF_ORDER_FIRST, OUT_OF_ORDER_THIRD]
    by_creation_descending = [OUT_OF_ORDER_THIRD, OUT_OF_ORDER_SECOND, OUT_OF_ORDER_FIRST]

    assert _ids(_list(engine, USER_A)) == by_last_use
    assert _ids(_list_character(engine, USER_A, CHAR_A1)) == by_last_use
    assert _ids(_list_all(engine, USER_A)) == by_last_use
    assert _ids(_list_character_all(engine, USER_A, CHAR_A1)) == by_last_use
    assert _ids(_list(engine, USER_A)) != by_creation_descending


def test_three_sessions_started_in_sequence_come_back_newest_first__S011_002_DoD7(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-7 — in 011 last use equals creation time (D3), so the newest start leads both
    listings (US-028.AC-1, D14)."""
    first = _start(engine, generator, USER_A, CHAR_A1)
    second = _start(engine, generator, USER_A, CHAR_A1)
    third = _start(engine, generator, USER_A, CHAR_A1)
    newest_first = [third.id, second.id, first.id]

    assert _ids(_list(engine, USER_A)) == newest_first
    assert _ids(_list_character(engine, USER_A, CHAR_A1)) == newest_first


# --- DoD-8: the archive flag -------------------------------------------------------------


def test_both_listings_exclude_archived_sessions_without_the_flag__S011_002_DoD8(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-8 — the default listing is the working list (US-027.AC-1, R6)."""
    working = _start(engine, generator, USER_A, CHAR_A1)
    archived = _start(engine, generator, USER_A, CHAR_A1)
    _archive(engine, USER_A, archived.id)

    assert _ids(_list(engine, USER_A)) == [working.id]
    assert _ids(_list_character(engine, USER_A, CHAR_A1)) == [working.id]


def test_both_listings_return_working_and_archived_with_the_flag__S011_002_DoD8(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-8 — the flag adds the archived rows to both listings (R6's explicit flag)."""
    working = _start(engine, generator, USER_A, CHAR_A1)
    archived = _start(engine, generator, USER_A, CHAR_A1)
    _archive(engine, USER_A, archived.id)

    assert sorted(_ids(_list_all(engine, USER_A))) == sorted([working.id, archived.id])
    assert sorted(_ids(_list_character_all(engine, USER_A, CHAR_A1))) == sorted(
        [working.id, archived.id]
    )


# --- DoD-9: a foreign or nonexistent session id -----------------------------------------


def test_another_users_session_is_not_found_and_is_left_untouched__S011_002_DoD9(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-9 — all three single-session operations raise `SessionNotFoundError` for another
    user's session, and the owner's row is unchanged afterwards (US-029.AC-1, R5, D12)."""
    theirs_working = _start(engine, generator, USER_B, CHAR_B1)
    theirs_archived = _start(engine, generator, USER_B, CHAR_B1)
    _archive(engine, USER_B, theirs_archived.id)

    for target in (theirs_working.id, theirs_archived.id):
        before = _stored_state(engine, target)

        with pytest.raises(SessionNotFoundError):
            _get(engine, USER_A, target)
        with pytest.raises(SessionNotFoundError):
            _archive(engine, USER_A, target)
        with pytest.raises(SessionNotFoundError):
            _restore(engine, USER_A, target)

        assert _stored_state(engine, target) == before


def test_a_session_id_that_exists_for_nobody_raises_the_same_error__S011_002_DoD9(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-9 — an unknown id and a foreign id are indistinguishable, and the caller's own
    rows are untouched (R5, D12)."""
    mine = _start(engine, generator, USER_A, CHAR_A1)
    before = _stored_state(engine, mine.id)

    with pytest.raises(SessionNotFoundError):
        _get(engine, USER_A, UNKNOWN_SESSION_ID)
    with pytest.raises(SessionNotFoundError):
        _archive(engine, USER_A, UNKNOWN_SESSION_ID)
    with pytest.raises(SessionNotFoundError):
        _restore(engine, USER_A, UNKNOWN_SESSION_ID)

    assert _stored_state(engine, mine.id) == before


# --- DoD-10: archive ---------------------------------------------------------------------


def test_archive_sets_archived_at_and_moves_the_row_out_of_the_lists__S011_002_DoD10(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-10 — the returned row carries `archived_at` in the fixed-width form, is absent
    from both default listings, present in both include-archived listings, and still
    answered by `get_session` (US-027.AC-1, D13)."""
    created = _start(engine, generator, USER_A, CHAR_A1, SETUP_A1)

    archived = _archive(engine, USER_A, created.id)

    assert archived.archived_at is not None
    assert FIXED_WIDTH_TIMESTAMP.match(archived.archived_at)
    assert _ids(_list(engine, USER_A)) == []
    assert _ids(_list_character(engine, USER_A, CHAR_A1)) == []
    assert _ids(_list_all(engine, USER_A)) == [created.id]
    assert _ids(_list_character_all(engine, USER_A, CHAR_A1)) == [created.id]
    assert _get(engine, USER_A, created.id) == archived


def test_archiving_an_archived_session_is_a_no_op__S011_002_DoD10(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-10 — the second archive keeps the original `archived_at` and writes nothing, so
    `updated_at` does not move either (D13)."""
    created = _start(engine, generator, USER_A, CHAR_A1)
    archived = _archive(engine, USER_A, created.id)

    again = _archive(engine, USER_A, created.id)

    assert again.archived_at == archived.archived_at
    assert again.updated_at == archived.updated_at


def test_archiving_never_moves_last_used_at__S011_002_DoD10(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-10 — `last_used_at` is unchanged throughout: only content writes bump it (D3)."""
    created = _start(engine, generator, USER_A, CHAR_A1)

    first = _archive(engine, USER_A, created.id)
    second = _archive(engine, USER_A, created.id)

    assert first.last_used_at == created.last_used_at
    assert second.last_used_at == created.last_used_at
    assert _get(engine, USER_A, created.id).last_used_at == created.last_used_at


# --- DoD-11: restore ---------------------------------------------------------------------


def test_restore_clears_archived_at_and_reopens_the_row_unchanged__S011_002_DoD11(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-11 — the restored row is back in both default listings and its identity fields,
    `created_at` and `last_used_at` equal the values from before the archive
    (US-027.AC-2, US-027.AC-3's row half, D13)."""
    created = _start(engine, generator, USER_A, CHAR_A1, SETUP_A1)
    _archive(engine, USER_A, created.id)

    restored = _restore(engine, USER_A, created.id)

    assert restored.archived_at is None
    assert restored.id == created.id
    assert restored.character_id == created.character_id
    assert restored.setup_id == created.setup_id
    assert restored.setup_name == created.setup_name
    assert restored.created_at == created.created_at
    assert restored.last_used_at == created.last_used_at
    assert _ids(_list(engine, USER_A)) == [created.id]
    assert _ids(_list_character(engine, USER_A, CHAR_A1)) == [created.id]


def test_restoring_a_working_session_is_a_no_op__S011_002_DoD11(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-11 — restoring a row that is not archived writes nothing, so `updated_at` and
    `last_used_at` stand (D13, D3)."""
    created = _start(engine, generator, USER_A, CHAR_A1)

    restored = _restore(engine, USER_A, created.id)

    assert restored.archived_at is None
    assert restored.updated_at == created.updated_at
    assert restored.last_used_at == created.last_used_at
    assert restored == created


# --- DoD-12: reads never write ----------------------------------------------------------


def test_reads_leave_last_used_at_and_updated_at_exactly_as_they_were__S011_002_DoD12(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-12 — `get_session` and either listing write nothing: there is no touch or resume
    operation (D3)."""
    created = _start(engine, generator, USER_A, CHAR_A1, SETUP_A1)
    before = _stored_state(engine, created.id)

    _get(engine, USER_A, created.id)
    _list(engine, USER_A)
    _list_all(engine, USER_A)
    _list_character(engine, USER_A, CHAR_A1)
    _list_character_all(engine, USER_A, CHAR_A1)

    after = _stored_state(engine, created.id)
    assert after == before
    assert after[1] == created.last_used_at
    assert after[2] == created.updated_at


# --- DoD-13: an archived setup still labels its sessions --------------------------------


def test_an_archived_setup_still_labels_its_sessions__S011_002_DoD13(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-13 — the join carries no predicate on `setups.archived_at`, so a session keeps
    its `setup_id` and `setup_name` after the setup is archived (D10, 010 D3)."""
    created = _start(engine, generator, USER_A, CHAR_A1, SETUP_A1)

    _archive_setup_row(engine, SETUP_A1)

    fetched = _get(engine, USER_A, created.id)
    assert fetched.setup_id == SETUP_A1
    assert fetched.setup_name == SETUP_A1_NAME
    for listing in (
        _list(engine, USER_A),
        _list_all(engine, USER_A),
        _list_character(engine, USER_A, CHAR_A1),
        _list_character_all(engine, USER_A, CHAR_A1),
    ):
        assert [(row.setup_id, row.setup_name) for row in listing] == [
            (SETUP_A1, SETUP_A1_NAME)
        ]


# --- DoD-14: a read leaves no transaction open ------------------------------------------


def _begin_and_roll_back(connection: Connection) -> None:
    """A following `connection.begin()` must succeed, so the read left nothing standing."""
    transaction = connection.begin()
    transaction.rollback()


def test_list_sessions_leaves_no_transaction_open__S011_002_DoD14(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-14 — after the all-characters listing, on the same connection."""
    _start(engine, generator, USER_A, CHAR_A1)

    with engine.connect() as connection:
        list_sessions(connection, USER_A)
        _begin_and_roll_back(connection)


def test_list_character_sessions_leaves_no_transaction_open__S011_002_DoD14(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-14 — the same for the per-character listing."""
    _start(engine, generator, USER_A, CHAR_A1)

    with engine.connect() as connection:
        list_character_sessions(connection, USER_A, CHAR_A1)
        _begin_and_roll_back(connection)


def test_a_refused_character_listing_leaves_no_transaction_open__S011_002_DoD14(
    engine: Engine,
) -> None:
    """DoD-14 — the rollback happens on the raising exit too: after
    `CharacterNotFoundError`, the same connection still accepts `begin()`."""
    with engine.connect() as connection:
        with pytest.raises(CharacterNotFoundError):
            list_character_sessions(connection, USER_A, CHAR_B1)
        _begin_and_roll_back(connection)


def test_get_session_leaves_no_transaction_open__S011_002_DoD14(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-14 — the same for a single read by id."""
    created = _start(engine, generator, USER_A, CHAR_A1)

    with engine.connect() as connection:
        get_session(connection, USER_A, created.id)
        _begin_and_roll_back(connection)


def test_a_refused_get_leaves_no_transaction_open__S011_002_DoD14(
    engine: Engine,
) -> None:
    """DoD-14 — and on `get_session`'s raising exit, after `SessionNotFoundError`."""
    with engine.connect() as connection:
        with pytest.raises(SessionNotFoundError):
            get_session(connection, USER_A, UNKNOWN_SESSION_ID)
        _begin_and_roll_back(connection)


# --- DoD-15: nothing is inserted into any table but `sessions` --------------------------


def test_starting_a_session_with_no_setup_creates_no_setup_row__S011_002_DoD15(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-15 — no default setup, no sentinel: the `setups` count is untouched by a start,
    while the `sessions` count grows by exactly one (R2)."""
    setups_before = _count_setups(engine)
    sessions_before = _count_sessions(engine)

    _start(engine, generator, USER_A, CHAR_A1)

    assert _count_setups(engine) == setups_before
    assert _count_sessions(engine) == sessions_before + 1


def test_no_other_operation_of_the_module_inserts_anywhere__S011_002_DoD15(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-15 — the reads, the archive and the restore add no row to either table (R2)."""
    created = _start(engine, generator, USER_A, CHAR_A1, SETUP_A1)
    setups_before = _count_setups(engine)
    sessions_before = _count_sessions(engine)

    _get(engine, USER_A, created.id)
    _list(engine, USER_A)
    _list_character(engine, USER_A, CHAR_A1)
    _archive(engine, USER_A, created.id)
    _restore(engine, USER_A, created.id)

    assert _count_setups(engine) == setups_before
    assert _count_sessions(engine) == sessions_before


# --- DoD-16: no delete path, no HTTP, no sibling service, no model capture --------------

_DELETE_CALL = re.compile(r"\bdelete\s*\(", re.IGNORECASE)
_DELETE_SQL_KEYWORD = re.compile(r"\bDELETE\b")
_DELETE_FROM = re.compile(r"\bdelete\s+from\b", re.IGNORECASE)
_FASTAPI_IMPORT = re.compile(r"^\s*(?:from|import)\s+fastapi\b", re.MULTILINE)

#: The package no statement of this service may import from (D11).
_FORBIDDEN_IMPORT_ROOT = "app.services"


def test_the_service_module_has_no_delete_path_and_no_fastapi_import__S011_002_DoD16() -> None:
    """DoD-16 — R6 and "Routers versus services": the source text carries no `delete(`
    call, no `DELETE` SQL keyword and no `fastapi` import."""
    source = inspect.getsource(sessions_module)

    assert "delete(" not in source.lower()
    assert _DELETE_CALL.search(source) is None
    assert _DELETE_SQL_KEYWORD.search(source) is None
    assert _DELETE_FROM.search(source) is None
    assert _FASTAPI_IMPORT.search(source) is None


def test_the_service_module_imports_no_other_service__S011_002_DoD16__S017_002_DoD11__S018_002_DoD10() -> None:
    """DoD-16 — D11: the parent and setup checks are this module's own scoped selects, so
    nothing is imported from any `app.services.` module (nor relatively from the package).

    Amended by 017 step 002 DoD-11 (017 D12): the one exception is
    `from app.services.llm_registry import ...` naming only the transaction-neutral reads,
    `ModelRefLevel`, `EnabledChatModel` and the `UNSET` / `Unset` sentinel. Any other
    `app.services.*` import, any other name from `llm_registry`, a star import, or a
    module-level import of `llm_registry` (which would expose every name) still fails.

    Amended by 018 step 002 DoD-10 (018 D3): a second exception is
    `from app.services.messages import ...` naming only the transaction-neutral zone insert
    helper `insert_zone_message` and the message value type `StreamMessage`."""
    allowed_names_by_module = {
        "app.services.llm_registry": {
            "list_enabled_chat_models",
            "first_enabled_chat_model",
            "validate_chat_model",
            "ModelRefLevel",
            "EnabledChatModel",
            "UNSET",
            "Unset",
        },
        "app.services.messages": {"insert_zone_message", "StreamMessage"},
    }
    tree = ast.parse(inspect.getsource(sessions_module))

    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level > 0:
                offenders.append(f"relative import, level {node.level}")
            elif node.module in allowed_names_by_module:
                for alias in node.names:
                    if alias.name not in allowed_names_by_module[node.module]:
                        offenders.append(f"from {node.module} import {alias.name}")
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


def test_the_service_module_never_mentions_a_model_reference__S011_002_DoD16() -> None:
    """DoD-16 — R4's model capture is `017`'s: 011's sessions carry no `model_ref`."""
    source = inspect.getsource(sessions_module)

    assert "model_ref" not in source


# =========================================================================================
# Feature 018, step 002 — create a session and seed its zone in one transaction.
#
# Expected values come from `docs/plans/018.character-page/002.create-and-seed-route.md`
# (Interface intent, DoD-1..5 and DoD-10), `002.context.md` ("Id-minting order": session id
# first, message id second) and the feature `context.md` (D3 — one transaction, one insert,
# `last_used_at` stays the creation instant; the Wire contract's current-zone row; R2, R4,
# R5, R6, R11). Binding: `## Skeleton` -> Step 002 — `StartedSession(session, opening_message)`
# and `start_seeded_session(connection, generator, user_id, character_id, opening_text,
# setup_id=None) -> StartedSession`. Test names end `__S018_002_DoD<n>`.
# =========================================================================================

OPENING_TEXT = "Hello there"

#: Registry rows for DoD-4 (017 "Registry fixtures"): the server ids and `models.id` order
#: disagree, so the first enabled model (D7 order: `llm_servers.id`, then `models.id`) is
#: SERVER_LOW's, not the model with the smaller `models.id`.
SERVER_LOW = 5_100
SERVER_HIGH = 5_200
MODEL_ON_HIGH = 61_001
MODEL_ON_HIGH_NAME = "alpha-chat"
MODEL_ON_LOW = 62_001
MODEL_ON_LOW_NAME = "beta-chat"


class _SecondIdFails(Exception):
    """Raised by `_FailOnSecondIdGenerator` on its second `next_id()` (DoD-3)."""


class _FailOnSecondIdGenerator:
    """Answers one known id first (the session's), then fails (the message's)."""

    def __init__(self, first: int) -> None:
        self.first = first
        self.calls = 0

    def next_id(self) -> int:
        self.calls += 1
        if self.calls == 1:
            return self.first
        raise _SecondIdFails("the message id cannot be minted")


def _seed(
    engine: Engine,
    generator: Any,
    user_id: int,
    character_id: int,
    opening_text: str,
    setup_id: int | None = None,
) -> StartedSession:
    with engine.connect() as connection:
        return start_seeded_session(
            connection, generator, user_id, character_id, opening_text, setup_id
        )


def _count_messages(engine: Engine) -> int:
    """Rows in the `messages` table, counted directly."""
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(schema.messages)).scalar_one())


def _all_message_rows(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(select(schema.messages).order_by(schema.messages.c.id)).all()
    return [dict(row._mapping) for row in rows]


def _session_ids(engine: Engine) -> set[int]:
    with engine.connect() as connection:
        return {int(value) for value in connection.execute(select(schema.sessions.c.id)).scalars()}


def _stored_session_row(engine: Engine, session_id: int) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(
            select(schema.sessions).where(schema.sessions.c.id == session_id)
        ).one()
    return dict(row._mapping)


def _captured_model(engine: Engine, session_id: int) -> tuple[Any, Any]:
    row = _stored_session_row(engine, session_id)
    return (row["model_server_id"], row["model_name"])


def _insert_llm_server(engine: Engine, *, server_id: int, name: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.metadata.tables["llm_servers"]
            .insert()
            .values(
                id=server_id,
                name=name,
                kind="llamaswap",
                base_url=f"http://llm-{server_id}.test:8080",
                api_key_ref=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_llm_model(engine: Engine, *, model_id: int, server_id: int, name: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.metadata.tables["models"]
            .insert()
            .values(
                id=model_id,
                server_id=server_id,
                model_name=name,
                is_enabled=True,
                is_embedding_designated=False,
                embedding_dim=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _seed_two_enabled_models(engine: Engine) -> None:
    _insert_llm_server(engine, server_id=SERVER_LOW, name="server low")
    _insert_llm_server(engine, server_id=SERVER_HIGH, name="server high")
    _insert_llm_model(engine, model_id=MODEL_ON_HIGH, server_id=SERVER_HIGH, name=MODEL_ON_HIGH_NAME)
    _insert_llm_model(engine, model_id=MODEL_ON_LOW, server_id=SERVER_LOW, name=MODEL_ON_LOW_NAME)


def _configure_character_model(engine: Engine, character_id: int, server_id: int, name: str) -> None:
    """A raw update of the character's model pair (017's write route is not under test)."""
    with engine.begin() as connection:
        connection.execute(
            schema.characters.update()
            .where(schema.characters.c.id == character_id)
            .values(model_server_id=server_id, model_name=name)
        )


# --- DoD-1: one session, one current-zone opening message --------------------------------


def test_create_and_seed_returns_the_session_and_its_opening_message__S018_002_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-1 — US-117.AC-1/AC-2, R2, R11: no setup; the opening message is a current-zone
    user row of the new session, text verbatim."""
    started = _seed(engine, generator, USER_A, CHAR_A1, OPENING_TEXT)

    assert isinstance(started, StartedSession)
    assert isinstance(started.session, RpSession)
    assert started.session.character_id == CHAR_A1
    assert started.session.setup_id is None
    message = started.opening_message
    assert isinstance(message, StreamMessage)
    assert message.session_id == started.session.id
    assert message.role == "user"
    assert message.kind is None
    assert message.settled_at is None
    assert message.text == OPENING_TEXT


def test_create_and_seed_stores_exactly_one_session_and_one_message__S018_002_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-1 — reading the database afterwards finds exactly one new session and exactly one
    message, for that session (a zone row: no kind, no settled_at)."""
    sessions_before = _session_ids(engine)
    assert _count_messages(engine) == 0

    started = _seed(engine, generator, USER_A, CHAR_A1, OPENING_TEXT)

    assert _session_ids(engine) - sessions_before == {started.session.id}
    assert len(_session_ids(engine)) == len(sessions_before) + 1
    rows = _all_message_rows(engine)
    assert len(rows) == 1
    (stored,) = rows
    assert stored["session_id"] == started.session.id
    assert started.opening_message is not None
    assert stored["id"] == started.opening_message.id
    assert stored["user_id"] == USER_A
    assert stored["role"] == "user"
    assert stored["kind"] is None
    assert stored["settled_at"] is None
    assert stored["text"] == OPENING_TEXT


# --- DoD-2: one instant ------------------------------------------------------------------


def test_the_opening_message_and_the_session_share_one_instant__S018_002_DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-2 — D3, 011 D3: the message's `created_at` is the session's `created_at`, and the
    session's `last_used_at`, `created_at` and `updated_at` are all equal (no second bump)."""
    started = _seed(engine, generator, USER_A, CHAR_A1, OPENING_TEXT)

    session = started.session
    assert started.opening_message is not None
    assert started.opening_message.created_at == session.created_at
    assert session.last_used_at == session.created_at == session.updated_at


def test_the_stored_session_row_keeps_the_creation_instant__S018_002_DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-2 — read back from the row: `last_used_at`, `created_at` and `updated_at` all equal
    the opening message's `created_at` (the session is not bumped a second time)."""
    started = _seed(engine, generator, USER_A, CHAR_A1, OPENING_TEXT)

    row = _stored_session_row(engine, started.session.id)
    (message_row,) = _all_message_rows(engine)
    assert row["last_used_at"] == row["created_at"] == row["updated_at"]
    assert message_row["created_at"] == row["created_at"]


# --- DoD-3: atomicity --------------------------------------------------------------------


def test_a_failed_message_insert_rolls_the_session_back__S018_002_DoD3(
    engine: Engine,
) -> None:
    """DoD-3 — US-117.AC-1, D3: the generator fails on its second id (the message's, after
    the session insert ran inside the transaction); the operation raises and the database
    holds no new session row and no message row."""
    sessions_before = _session_ids(engine)
    messages_before = _count_messages(engine)
    failing = _FailOnSecondIdGenerator(first=88_001)

    with pytest.raises(_SecondIdFails):
        _seed(engine, failing, USER_A, CHAR_A1, OPENING_TEXT)

    assert failing.calls == 2
    assert _session_ids(engine) == sessions_before
    assert 88_001 not in _session_ids(engine)
    assert _count_messages(engine) == messages_before


# --- DoD-4: the model capture is start_session's ----------------------------------------


def test_create_and_seed_captures_the_first_enabled_model_like_start__S018_002_DoD4(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-4 — R4, US-106.AC-1, 017 D1: a character without a model captures the first
    enabled model (D7 order), exactly as `start_session` does under the same registry."""
    _seed_two_enabled_models(engine)

    seeded = _seed(engine, generator, USER_A, CHAR_A1, OPENING_TEXT)
    plain = _start(engine, generator, USER_A, CHAR_A1)

    assert _captured_model(engine, seeded.session.id) == (SERVER_LOW, MODEL_ON_LOW_NAME)
    assert _captured_model(engine, seeded.session.id) == _captured_model(engine, plain.id)


def test_create_and_seed_captures_the_characters_configured_model_like_start__S018_002_DoD4(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-4 — US-139.AC-2, 017 D1: a character with a configured model captures that pair
    (not the first enabled), exactly as `start_session` does."""
    _seed_two_enabled_models(engine)
    _configure_character_model(engine, CHAR_A2, SERVER_HIGH, MODEL_ON_HIGH_NAME)

    seeded = _seed(engine, generator, USER_A, CHAR_A2, OPENING_TEXT)
    plain = _start(engine, generator, USER_A, CHAR_A2)

    assert _captured_model(engine, seeded.session.id) == (SERVER_HIGH, MODEL_ON_HIGH_NAME)
    assert _captured_model(engine, seeded.session.id) == _captured_model(engine, plain.id)


# --- DoD-5: owner scope; archive is not a lock -------------------------------------------


@pytest.mark.parametrize(
    "character_id",
    [CHAR_B1, UNKNOWN_CHARACTER_ID],
    ids=["another-users-character", "nobodys-character"],
)
def test_create_and_seed_on_a_parent_not_the_callers_is_refused__S018_002_DoD5(
    engine: Engine, generator: SnowflakeGenerator, character_id: int
) -> None:
    """DoD-5 — R5, 011 D2: `CharacterNotFoundError`, and neither a session nor a message is
    inserted."""
    sessions_before = _session_ids(engine)
    messages_before = _count_messages(engine)

    with pytest.raises(CharacterNotFoundError):
        _seed(engine, generator, USER_A, character_id, OPENING_TEXT)

    assert _session_ids(engine) == sessions_before
    assert _count_messages(engine) == messages_before


def test_create_and_seed_on_the_callers_archived_character_succeeds__S018_002_DoD5(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-5 — R6, 011 D2: archive is not a lock; the session and its opening message are
    created under the archived character."""
    started = _seed(engine, generator, USER_A, CHAR_A_ARCHIVED, OPENING_TEXT)

    assert started.session.character_id == CHAR_A_ARCHIVED
    assert started.opening_message is not None
    assert started.opening_message.session_id == started.session.id
    assert started.opening_message.text == OPENING_TEXT
    assert _ids(_list_character(engine, USER_A, CHAR_A_ARCHIVED)) == [started.session.id]
    assert _count_messages(engine) == 1


# --- DoD-10: the narrow import exception, read from disk ---------------------------------


def test_the_service_imports_only_the_zone_helper_and_message_type_and_no_fastapi__S018_002_DoD10() -> None:
    """DoD-10 — D3: from `app.services.messages` exactly the zone insert helper and the
    message value type are imported (no module-level import of it), and no `fastapi`."""
    source = Path(str(sessions_module.__file__)).read_text(encoding="utf-8")
    tree = ast.parse(source)

    names_from_messages: set[str] = set()
    module_imports_of_messages: list[str] = []
    fastapi_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module == "app.services.messages":
                names_from_messages.update(alias.name for alias in node.names)
            if node.module == "fastapi" or node.module.startswith("fastapi."):
                fastapi_imports.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "app.services.messages":
                    module_imports_of_messages.append(alias.name)
                if alias.name == "fastapi" or alias.name.startswith("fastapi."):
                    fastapi_imports.append(alias.name)

    assert names_from_messages == {"insert_zone_message", "StreamMessage"}
    assert module_imports_of_messages == []
    assert fastapi_imports == []
