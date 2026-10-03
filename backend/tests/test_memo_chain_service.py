"""Tests for `app/services/memo_chain.py` — feature 015, step 003 (the memo chain service).

Every expected value comes from the step's Definition of done and the feature context
(R2, R3, R5, D4, D7, D8, D11, D12). The module is called only through the frozen interface
recorded under `## Skeleton` in `docs/plans/015.memos/status.md`:

- `MemoReach = Literal["forced", "searchable", "disabled"]`
- `MemoChainLevel` (frozen dataclass: `scope`, `scope_id`, `memos`)
- `resolve_chain(connection, user_id, session_id) -> list[MemoChainLevel]`
- `memo_reach(is_enabled, is_forced) -> MemoReach`

Users, characters, setups, sessions and every `memos` row are raw-inserted with their
committed columns, so these tests do not depend on step 002's create behaviour.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, get_args

import pytest
from sqlalchemy import Connection, Engine, event, select

from app.db import schema
from app.errors import SessionNotFoundError
from app.roles import Role
from app.services import memo_chain as memo_chain_module
from app.services.memo_chain import MemoChainLevel, MemoReach, memo_reach, resolve_chain

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
ARCHIVED_AT = "2026-02-01T00:00:00.000000+00:00"

USER_A = 101
USER_B = 202

CHAR_A1 = 1_001
CHAR_A2 = 1_002
CHAR_B1 = 1_101

SETUP_A1 = 2_001  # under CHAR_A1; the setup of SESSION_WITH_SETUP
SETUP_A2 = 2_002  # under CHAR_A1; another setup of the same character
SETUP_B1 = 2_101

SESSION_WITH_SETUP = 3_001  # USER_A, CHAR_A1, SETUP_A1
SESSION_NO_SETUP = 3_002  # USER_A, CHAR_A1, no setup
SESSION_OTHER = 3_003  # USER_A, CHAR_A1, SETUP_A2
SESSION_A2 = 3_004  # USER_A, CHAR_A2, no setup
SESSION_B1 = 3_101  # USER_B, CHAR_B1, SETUP_B1

UNKNOWN_SESSION_ID = 7_777_777_777

FOUR_SCOPES = ["user", "character", "setup", "session"]
THREE_SCOPES = ["user", "character", "session"]


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
    body: str | None = None,
    is_enabled: bool = True,
    is_forced: bool = False,
) -> None:
    """Raw-insert one `memos` row in a precise state (user level: `scope_id` = the owner)."""
    with engine.begin() as connection:
        connection.execute(
            schema.memos.insert().values(
                id=memo_id,
                user_id=user_id,
                scope=scope,
                scope_id=scope_id,
                body=body if body is not None else f"note {memo_id}",
                is_enabled=is_enabled,
                is_forced=is_forced,
                sort_key=sort_key,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


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
        db_engine,
        session_id=SESSION_WITH_SETUP,
        user_id=USER_A,
        character_id=CHAR_A1,
        setup_id=SETUP_A1,
    )
    _insert_session(
        db_engine, session_id=SESSION_NO_SETUP, user_id=USER_A, character_id=CHAR_A1, setup_id=None
    )
    _insert_session(
        db_engine, session_id=SESSION_OTHER, user_id=USER_A, character_id=CHAR_A1, setup_id=SETUP_A2
    )
    _insert_session(
        db_engine, session_id=SESSION_A2, user_id=USER_A, character_id=CHAR_A2, setup_id=None
    )
    _insert_session(
        db_engine, session_id=SESSION_B1, user_id=USER_B, character_id=CHAR_B1, setup_id=SETUP_B1
    )
    return db_engine


def _seed_full_chain(engine: Engine) -> None:
    """USER_A notes at all four levels of SESSION_WITH_SETUP, raw-inserted out of order.

    Expected orders (by `sort_key`, then `id`):
    - user:      5001 (0), 5002 (1), 5003 (1)  — a `sort_key` tie broken by id
    - character: 5102 (0, disabled), 5101 (2)
    - setup:     5202 (1, disabled and forced), 5201 (3)
    - session:   5301 (0, forced)
    """
    _insert_memo(engine, memo_id=5003, user_id=USER_A, scope="user", scope_id=USER_A, sort_key=1)
    _insert_memo(engine, memo_id=5002, user_id=USER_A, scope="user", scope_id=USER_A, sort_key=1)
    _insert_memo(engine, memo_id=5001, user_id=USER_A, scope="user", scope_id=USER_A, sort_key=0)
    _insert_memo(
        engine, memo_id=5101, user_id=USER_A, scope="character", scope_id=CHAR_A1, sort_key=2
    )
    _insert_memo(
        engine,
        memo_id=5102,
        user_id=USER_A,
        scope="character",
        scope_id=CHAR_A1,
        sort_key=0,
        is_enabled=False,
    )
    _insert_memo(engine, memo_id=5201, user_id=USER_A, scope="setup", scope_id=SETUP_A1, sort_key=3)
    _insert_memo(
        engine,
        memo_id=5202,
        user_id=USER_A,
        scope="setup",
        scope_id=SETUP_A1,
        sort_key=1,
        is_enabled=False,
        is_forced=True,
    )
    _insert_memo(
        engine,
        memo_id=5301,
        user_id=USER_A,
        scope="session",
        scope_id=SESSION_WITH_SETUP,
        sort_key=0,
        is_forced=True,
    )


EXPECTED_FULL_CHAIN_IDS: list[list[int]] = [
    [5001, 5002, 5003],
    [5102, 5101],
    [5202, 5201],
    [5301],
]


def _seed_no_setup_chain(engine: Engine) -> None:
    """USER_A notes for SESSION_NO_SETUP, plus a setup note of a setup under the same character."""
    _insert_memo(engine, memo_id=6002, user_id=USER_A, scope="user", scope_id=USER_A, sort_key=1)
    _insert_memo(engine, memo_id=6001, user_id=USER_A, scope="user", scope_id=USER_A, sort_key=0)
    _insert_memo(
        engine, memo_id=6101, user_id=USER_A, scope="character", scope_id=CHAR_A1, sort_key=0
    )
    _insert_memo(
        engine,
        memo_id=6301,
        user_id=USER_A,
        scope="session",
        scope_id=SESSION_NO_SETUP,
        sort_key=0,
    )
    _insert_memo(
        engine,
        memo_id=6302,
        user_id=USER_A,
        scope="session",
        scope_id=SESSION_NO_SETUP,
        sort_key=1,
        is_enabled=False,
    )
    # A setup-level note under the same character — must not appear in a no-setup chain.
    _insert_memo(engine, memo_id=6201, user_id=USER_A, scope="setup", scope_id=SETUP_A1, sort_key=0)
    _insert_memo(engine, memo_id=6202, user_id=USER_A, scope="setup", scope_id=SETUP_A2, sort_key=0)


# --- one connection per call ----------------------------------------------------------------


def _resolve(engine: Engine, user_id: int, session_id: int) -> list[MemoChainLevel]:
    with engine.connect() as connection:
        return resolve_chain(connection, user_id, session_id)


def _scopes(levels: list[MemoChainLevel]) -> list[str]:
    return [level.scope for level in levels]


def _ids(levels: list[MemoChainLevel]) -> list[list[int]]:
    return [[memo.id for memo in level.memos] for level in levels]


def _all_ids(levels: list[MemoChainLevel]) -> set[int]:
    return {memo.id for level in levels for memo in level.memos}


def _memos_snapshot(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(select(schema.memos).order_by(schema.memos.c.id)).mappings()
        return [dict(row) for row in rows]


@contextmanager
def _recording_statements(engine: Engine) -> Iterator[list[str]]:
    """Record every statement text sent to the cursor while the block runs."""
    statements: list[str] = []

    def _listener(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _listener)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", _listener)


def _select_count(statements: list[str]) -> int:
    return sum(1 for text in statements if text.lstrip().upper().startswith("SELECT"))


def _assert_no_open_transaction(connection: Connection) -> None:
    assert not connection.in_transaction()
    transaction = connection.begin()
    transaction.rollback()


# --- DoD-1: a session with a setup ----------------------------------------------------------


def test_chain_with_setup_has_four_levels_in_fixed_order__S015_003_DoD1(engine: Engine) -> None:
    _seed_full_chain(engine)

    levels = _resolve(engine, USER_A, SESSION_WITH_SETUP)

    assert len(levels) == 4
    assert all(isinstance(level, MemoChainLevel) for level in levels)
    assert _scopes(levels) == FOUR_SCOPES


def test_chain_with_setup_level_scope_ids__S015_003_DoD1(engine: Engine) -> None:
    _seed_full_chain(engine)

    levels = _resolve(engine, USER_A, SESSION_WITH_SETUP)

    assert [level.scope_id for level in levels] == [
        None,
        CHAR_A1,
        SETUP_A1,
        SESSION_WITH_SETUP,
    ]


def test_chain_with_setup_levels_hold_their_notes_ordered_by_sort_key_then_id__S015_003_DoD1(
    engine: Engine,
) -> None:
    _seed_full_chain(engine)

    levels = _resolve(engine, USER_A, SESSION_WITH_SETUP)

    assert _ids(levels) == EXPECTED_FULL_CHAIN_IDS
    for level in levels:
        assert all(memo.scope == level.scope for memo in level.memos)


def test_chain_includes_disabled_notes_with_their_flags__S015_003_DoD1(engine: Engine) -> None:
    _seed_full_chain(engine)

    levels = _resolve(engine, USER_A, SESSION_WITH_SETUP)

    by_id = {memo.id: memo for level in levels for memo in level.memos}
    assert 5102 in by_id
    assert by_id[5102].is_enabled is False
    assert by_id[5102].is_forced is False
    assert 5202 in by_id
    assert by_id[5202].is_enabled is False
    assert by_id[5202].is_forced is True
    assert by_id[5301].is_enabled is True
    assert by_id[5301].is_forced is True
    assert by_id[5101].is_enabled is True
    assert by_id[5101].is_forced is False


# --- DoD-2: a session without a setup -------------------------------------------------------


def test_chain_without_setup_has_exactly_three_levels__S015_003_DoD2(engine: Engine) -> None:
    _seed_no_setup_chain(engine)

    levels = _resolve(engine, USER_A, SESSION_NO_SETUP)

    assert len(levels) == 3
    assert _scopes(levels) == THREE_SCOPES
    assert "setup" not in _scopes(levels)
    assert [level.scope_id for level in levels] == [None, CHAR_A1, SESSION_NO_SETUP]


def test_chain_without_setup_holds_every_note_in_its_level__S015_003_DoD2(
    engine: Engine,
) -> None:
    _seed_no_setup_chain(engine)

    levels = _resolve(engine, USER_A, SESSION_NO_SETUP)

    assert _ids(levels) == [[6001, 6002], [6101], [6301, 6302]]


def test_chain_without_setup_omits_setup_notes_of_the_same_character__S015_003_DoD2(
    engine: Engine,
) -> None:
    _seed_no_setup_chain(engine)

    levels = _resolve(engine, USER_A, SESSION_NO_SETUP)

    present = _all_ids(levels)
    assert 6201 not in present
    assert 6202 not in present
    assert all(memo.scope != "setup" for level in levels for memo in level.memos)


# --- DoD-3: empty levels are still listed ---------------------------------------------------


def test_a_session_with_setup_and_no_notes_returns_four_empty_levels__S015_003_DoD3(
    engine: Engine,
) -> None:
    levels = _resolve(engine, USER_A, SESSION_WITH_SETUP)

    assert _scopes(levels) == FOUR_SCOPES
    assert [level.scope_id for level in levels] == [
        None,
        CHAR_A1,
        SETUP_A1,
        SESSION_WITH_SETUP,
    ]
    assert all(list(level.memos) == [] for level in levels)


def test_a_session_without_setup_and_no_notes_returns_three_empty_levels__S015_003_DoD3(
    engine: Engine,
) -> None:
    levels = _resolve(engine, USER_A, SESSION_NO_SETUP)

    assert _scopes(levels) == THREE_SCOPES
    assert [level.scope_id for level in levels] == [None, CHAR_A1, SESSION_NO_SETUP]
    assert all(list(level.memos) == [] for level in levels)


def test_an_existing_level_without_notes_is_returned_empty__S015_003_DoD3(
    engine: Engine,
) -> None:
    # Notes at the user and session levels only: character and setup levels are empty.
    _insert_memo(engine, memo_id=7001, user_id=USER_A, scope="user", scope_id=USER_A, sort_key=0)
    _insert_memo(
        engine,
        memo_id=7301,
        user_id=USER_A,
        scope="session",
        scope_id=SESSION_WITH_SETUP,
        sort_key=0,
    )

    levels = _resolve(engine, USER_A, SESSION_WITH_SETUP)

    assert _scopes(levels) == FOUR_SCOPES
    assert _ids(levels) == [[7001], [], [], [7301]]


# --- DoD-4: nothing outside this session's chain, nothing of another user -------------------


def test_chain_excludes_other_sessions_characters_and_setups__S015_003_DoD4(
    engine: Engine,
) -> None:
    _seed_full_chain(engine)
    # Another session of the same character (with another setup).
    _insert_memo(
        engine, memo_id=8301, user_id=USER_A, scope="session", scope_id=SESSION_OTHER, sort_key=0
    )
    _insert_memo(
        engine, memo_id=8302, user_id=USER_A, scope="session", scope_id=SESSION_NO_SETUP, sort_key=0
    )
    # Another character of the caller.
    _insert_memo(
        engine, memo_id=8101, user_id=USER_A, scope="character", scope_id=CHAR_A2, sort_key=0
    )
    # Another setup of the same character.
    _insert_memo(engine, memo_id=8201, user_id=USER_A, scope="setup", scope_id=SETUP_A2, sort_key=0)

    levels = _resolve(engine, USER_A, SESSION_WITH_SETUP)

    assert _ids(levels) == EXPECTED_FULL_CHAIN_IDS
    assert _all_ids(levels).isdisjoint({8301, 8302, 8101, 8201})


def test_chain_excludes_every_note_of_another_user__S015_003_DoD4(engine: Engine) -> None:
    _seed_full_chain(engine)
    # Another user's own chain.
    _insert_memo(engine, memo_id=9001, user_id=USER_B, scope="user", scope_id=USER_B, sort_key=0)
    _insert_memo(
        engine, memo_id=9101, user_id=USER_B, scope="character", scope_id=CHAR_B1, sort_key=0
    )
    _insert_memo(engine, memo_id=9201, user_id=USER_B, scope="setup", scope_id=SETUP_B1, sort_key=0)
    _insert_memo(
        engine, memo_id=9301, user_id=USER_B, scope="session", scope_id=SESSION_B1, sort_key=0
    )
    # Raw rows of the other user whose scope / scope_id equal this session's levels.
    _insert_memo(engine, memo_id=9002, user_id=USER_B, scope="user", scope_id=USER_A, sort_key=0)
    _insert_memo(
        engine, memo_id=9102, user_id=USER_B, scope="character", scope_id=CHAR_A1, sort_key=0
    )
    _insert_memo(engine, memo_id=9202, user_id=USER_B, scope="setup", scope_id=SETUP_A1, sort_key=0)
    _insert_memo(
        engine,
        memo_id=9302,
        user_id=USER_B,
        scope="session",
        scope_id=SESSION_WITH_SETUP,
        sort_key=0,
    )

    levels = _resolve(engine, USER_A, SESSION_WITH_SETUP)

    assert _ids(levels) == EXPECTED_FULL_CHAIN_IDS
    assert _all_ids(levels).isdisjoint({9001, 9101, 9201, 9301, 9002, 9102, 9202, 9302})


def test_another_users_chain_excludes_the_callers_notes__S015_003_DoD4(engine: Engine) -> None:
    _seed_full_chain(engine)
    _insert_memo(engine, memo_id=9001, user_id=USER_B, scope="user", scope_id=USER_B, sort_key=0)
    _insert_memo(
        engine, memo_id=9301, user_id=USER_B, scope="session", scope_id=SESSION_B1, sort_key=0
    )

    levels = _resolve(engine, USER_B, SESSION_B1)

    assert _scopes(levels) == FOUR_SCOPES
    assert _ids(levels) == [[9001], [], [], [9301]]


# --- DoD-5: foreign or unknown session ------------------------------------------------------


def test_another_users_session_raises_session_not_found__S015_003_DoD5(engine: Engine) -> None:
    _seed_full_chain(engine)

    with pytest.raises(SessionNotFoundError):
        _resolve(engine, USER_B, SESSION_WITH_SETUP)
    with pytest.raises(SessionNotFoundError):
        _resolve(engine, USER_A, SESSION_B1)


def test_an_unknown_session_raises_session_not_found__S015_003_DoD5(engine: Engine) -> None:
    with pytest.raises(SessionNotFoundError):
        _resolve(engine, USER_A, UNKNOWN_SESSION_ID)


# --- DoD-6: archived session, character and setup -------------------------------------------


def test_archived_session_character_and_setup_still_resolve__S015_003_DoD6(
    engine: Engine,
) -> None:
    _seed_full_chain(engine)
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.update()
            .where(schema.sessions.c.id == SESSION_WITH_SETUP)
            .values(archived_at=ARCHIVED_AT)
        )
        connection.execute(
            schema.characters.update()
            .where(schema.characters.c.id == CHAR_A1)
            .values(archived_at=ARCHIVED_AT)
        )
        connection.execute(
            schema.setups.update()
            .where(schema.setups.c.id == SETUP_A1)
            .values(archived_at=ARCHIVED_AT)
        )

    levels = _resolve(engine, USER_A, SESSION_WITH_SETUP)

    assert _scopes(levels) == FOUR_SCOPES
    assert [level.scope_id for level in levels] == [
        None,
        CHAR_A1,
        SETUP_A1,
        SESSION_WITH_SETUP,
    ]
    assert _ids(levels) == EXPECTED_FULL_CHAIN_IDS


# --- DoD-7: two SELECTs per resolution ------------------------------------------------------


def test_resolution_with_setup_executes_exactly_two_selects__S015_003_DoD7(
    engine: Engine,
) -> None:
    _seed_full_chain(engine)

    with engine.connect() as connection:
        with _recording_statements(engine) as statements:
            resolve_chain(connection, USER_A, SESSION_WITH_SETUP)

    assert _select_count(statements) == 2


def test_resolution_without_setup_executes_exactly_two_selects__S015_003_DoD7(
    engine: Engine,
) -> None:
    _seed_no_setup_chain(engine)

    with engine.connect() as connection:
        with _recording_statements(engine) as statements:
            resolve_chain(connection, USER_A, SESSION_NO_SETUP)

    assert _select_count(statements) == 2


# --- DoD-8: a read leaves no transaction open and writes nothing ----------------------------


def test_resolution_leaves_no_transaction_open_and_writes_nothing__S015_003_DoD8(
    engine: Engine,
) -> None:
    _seed_full_chain(engine)
    _seed_no_setup_chain(engine)
    before = _memos_snapshot(engine)

    with engine.connect() as connection:
        resolve_chain(connection, USER_A, SESSION_WITH_SETUP)
        _assert_no_open_transaction(connection)
        resolve_chain(connection, USER_A, SESSION_NO_SETUP)
        _assert_no_open_transaction(connection)

    assert _memos_snapshot(engine) == before


def test_refused_resolution_leaves_no_transaction_open_and_writes_nothing__S015_003_DoD8(
    engine: Engine,
) -> None:
    _seed_full_chain(engine)
    before = _memos_snapshot(engine)

    with engine.connect() as connection:
        with pytest.raises(SessionNotFoundError):
            resolve_chain(connection, USER_B, SESSION_WITH_SETUP)
        _assert_no_open_transaction(connection)
        with pytest.raises(SessionNotFoundError):
            resolve_chain(connection, USER_A, UNKNOWN_SESSION_ID)
        _assert_no_open_transaction(connection)

    assert _memos_snapshot(engine) == before


# --- DoD-9: memo_reach ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("is_enabled", "is_forced", "expected"),
    [
        (True, True, "forced"),
        (True, False, "searchable"),
        (False, True, "disabled"),
        (False, False, "disabled"),
    ],
)
def test_memo_reach_over_all_four_combinations__S015_003_DoD9(
    is_enabled: bool, is_forced: bool, expected: str
) -> None:
    assert memo_reach(is_enabled, is_forced) == expected


def test_memo_reach_literal_names_the_three_reaches__S015_003_DoD9() -> None:
    assert set(get_args(MemoReach)) == {"forced", "searchable", "disabled"}


# --- DoD-10: narrow imports, no HTTP, no writes ---------------------------------------------


def _module_source() -> str:
    return inspect.getsource(memo_chain_module)


def test_imports_from_app_services_only_memo_and_the_row_mapper__S015_003_DoD10() -> None:
    tree = ast.parse(_module_source())

    imported_from_memos: set[str] = set()
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level > 0:
                offenders.append(f"relative import, level {node.level}")
                continue
            module = node.module or ""
            if module == "app.services.memos":
                imported_from_memos.update(alias.name for alias in node.names)
            elif module == "app.services" or module.startswith("app.services."):
                offenders.append(f"from {module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "app.services" or alias.name.startswith("app.services."):
                    offenders.append(f"import {alias.name}")

    assert offenders == []
    assert imported_from_memos == {"Memo", "to_memo"}


def test_the_chain_module_has_no_fastapi_import__S015_003_DoD10() -> None:
    tree = ast.parse(_module_source())

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert node.module != "fastapi" and not node.module.startswith("fastapi.")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "fastapi" and not alias.name.startswith("fastapi.")


def test_the_chain_module_has_no_insert_update_or_delete_call__S015_003_DoD10() -> None:
    source = _module_source()

    assert "insert(" not in source
    assert "update(" not in source
    assert "delete(" not in source
