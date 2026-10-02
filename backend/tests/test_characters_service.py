"""Tests for `app/services/characters.py` — feature 009, step 002.

Every expected value comes from `docs/plans/009.characters/002.characters-service.md`
(its Definition of done), from the feature context's D7 / D9 / D10 and from the
owner-scope (R5) and no-delete (R6) constraints. Each test name ends `__DoD<n>` with the
DoD item it covers.

The file follows `tests/test_users_service.py`'s pattern: a file-local `engine` fixture
that applies the registry with `schema.metadata.create_all`, one connection obtained per
service call (writes too — the service opens its own transaction), the real
`SnowflakeGenerator` for ordinary tests and a file-local fake where a known id matters.
`characters.user_id` is a real foreign key, so every character row's owner is seeded
first, and the isolation tests seed two users.
"""

import inspect
import re
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import Connection, Engine

from app.db import schema
from app.errors import CharacterNotFoundError
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services import characters as characters_module
from app.services.characters import (
    Character,
    archive_character,
    create_character,
    get_character,
    list_characters,
    restore_character,
    update_character,
)

TIMESTAMP = "2026-01-01T00:00:00+00:00"

USER_A = 101
USER_B = 202

#: An id that belongs to no character of any user.
UNKNOWN_ID = 9_999_999_999

#: `YYYY-MM-DDTHH:MM:SS.ffffff+00:00` — the fixed-width form (DoD-1, DoD-7).
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
    """Seed one owner row; the character FK is enforced, so this must precede any create."""
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


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database with the registry applied and two owners seeded."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="alice")
    _insert_user(db_engine, user_id=USER_B, username="bob")
    return db_engine


@pytest.fixture
def generator() -> SnowflakeGenerator:
    """One real generator per test, so ids minted within a test never collide."""
    return SnowflakeGenerator(node_id=1)


def _create(
    engine: Engine,
    generator: Any,
    user_id: int,
    name: str,
    sheet: str = "",
) -> Character:
    with engine.connect() as connection:
        return create_character(connection, generator, user_id, name, sheet)


def _get(engine: Engine, user_id: int, character_id: int) -> Character:
    with engine.connect() as connection:
        return get_character(connection, user_id, character_id)


def _list(engine: Engine, user_id: int) -> list[Character]:
    """The default listing — a two-argument call, the flag left at its default."""
    with engine.connect() as connection:
        return list_characters(connection, user_id)


def _list_all(engine: Engine, user_id: int) -> list[Character]:
    with engine.connect() as connection:
        return list_characters(connection, user_id, include_archived=True)


def _update(
    engine: Engine,
    user_id: int,
    character_id: int,
    *,
    name: str | None = None,
    sheet: str | None = None,
) -> Character:
    with engine.connect() as connection:
        return update_character(connection, user_id, character_id, name=name, sheet=sheet)


def _archive(engine: Engine, user_id: int, character_id: int) -> Character:
    with engine.connect() as connection:
        return archive_character(connection, user_id, character_id)


def _restore(engine: Engine, user_id: int, character_id: int) -> Character:
    with engine.connect() as connection:
        return restore_character(connection, user_id, character_id)


def _ids(characters: list[Character]) -> list[int]:
    return [character.id for character in characters]


# --- DoD-1: what create returns -----------------------------------------------------


def test_create_returns_the_minted_id_with_both_timestamps_equal__DoD1(engine: Engine) -> None:
    """DoD-1 — US-020.AC-1: the supplied generator's id, the given name/sheet, no
    `archived_at`, and one instant stamped into both timestamps in the fixed-width form."""
    fixed = _FixedIdGenerator(7_412_345_678_901_234)

    created = _create(engine, fixed, USER_A, "Aria", "# Aria\n\nA persona.")

    assert created.id == 7_412_345_678_901_234
    assert created.name == "Aria"
    assert created.sheet == "# Aria\n\nA persona."
    assert created.archived_at is None
    assert created.created_at == created.updated_at
    assert FIXED_WIDTH_TIMESTAMP.match(created.created_at) is not None
    assert FIXED_WIDTH_TIMESTAMP.match(created.updated_at) is not None


# --- DoD-2: the created character is readable and listed ----------------------------


def test_created_character_is_returned_by_get_and_is_in_the_listing__DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-2 — US-020.AC-2: `get_character` answers an equal value and the listing has it."""
    created = _create(engine, generator, USER_A, "Aria", "# Aria")

    assert _get(engine, USER_A, created.id) == created
    assert created in _list(engine, USER_A)


# --- DoD-3: the listing is owner-scoped ---------------------------------------------


def test_listing_returns_only_the_callers_own_characters__DoD3(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-3 — US-022.AC-1, R5: with two owners, each listing carries only its owner's
    characters, both with and without `include_archived`."""
    a_working = _create(engine, generator, USER_A, "Aria", "a1")
    a_archived = _create(engine, generator, USER_A, "Astra", "a2")
    _archive(engine, USER_A, a_archived.id)
    b_working = _create(engine, generator, USER_B, "Bora", "b1")
    b_archived = _create(engine, generator, USER_B, "Bryn", "b2")
    _archive(engine, USER_B, b_archived.id)

    assert set(_ids(_list(engine, USER_A))) == {a_working.id}
    assert set(_ids(_list_all(engine, USER_A))) == {a_working.id, a_archived.id}
    assert set(_ids(_list(engine, USER_B))) == {b_working.id}
    assert set(_ids(_list_all(engine, USER_B))) == {b_working.id, b_archived.id}


# --- DoD-4: the archive filter and D10's order --------------------------------------


def test_default_listing_excludes_archived_and_is_newest_created_first__DoD4(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-4 — US-086.AC-1, R6, D10: without the flag, archived rows are absent and the
    rest come back newest created first."""
    first = _create(engine, generator, USER_A, "First", "1")
    second = _create(engine, generator, USER_A, "Second", "2")
    third = _create(engine, generator, USER_A, "Third", "3")
    _archive(engine, USER_A, second.id)

    assert _ids(_list(engine, USER_A)) == [third.id, first.id]


def test_include_archived_listing_carries_both_states_newest_created_first__DoD4(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-4 — D10: with the flag, working and archived come back together, newest first."""
    first = _create(engine, generator, USER_A, "First", "1")
    second = _create(engine, generator, USER_A, "Second", "2")
    third = _create(engine, generator, USER_A, "Third", "3")
    _archive(engine, USER_A, second.id)

    assert _ids(_list_all(engine, USER_A)) == [third.id, second.id, first.id]


# --- DoD-5: every id-addressed operation is owner-scoped ----------------------------

_ScopedOperation = Callable[[Connection, int, int], Character]

def _attempt_update(connection: Connection, user_id: int, character_id: int) -> Character:
    return update_character(connection, user_id, character_id, name="hijacked", sheet="hijacked")


_SCOPED_OPERATIONS: list[_ScopedOperation] = [
    get_character,
    _attempt_update,
    archive_character,
    restore_character,
]

_SCOPED_OPERATION_IDS = ["get", "update", "archive", "restore"]


@pytest.mark.parametrize("operation", _SCOPED_OPERATIONS, ids=_SCOPED_OPERATION_IDS)
def test_another_users_character_id_is_not_found_and_changes_nothing__DoD5(
    engine: Engine, generator: SnowflakeGenerator, operation: _ScopedOperation
) -> None:
    """DoD-5 — R5: addressing another user's character raises `CharacterNotFoundError`,
    and the owner's row is untouched afterwards (name, sheet, `archived_at`, `updated_at`)."""
    owned = _create(engine, generator, USER_A, "Aria", "# Aria")

    with pytest.raises(CharacterNotFoundError), engine.connect() as connection:
        operation(connection, USER_B, owned.id)

    after = _get(engine, USER_A, owned.id)
    assert after.name == owned.name
    assert after.sheet == owned.sheet
    assert after.archived_at == owned.archived_at
    assert after.updated_at == owned.updated_at


@pytest.mark.parametrize("operation", _SCOPED_OPERATIONS, ids=_SCOPED_OPERATION_IDS)
def test_an_id_that_exists_for_nobody_raises_the_same_error__DoD5(
    engine: Engine, operation: _ScopedOperation
) -> None:
    """DoD-5 — R5: a wholly unknown id is indistinguishable from another user's id."""
    with pytest.raises(CharacterNotFoundError), engine.connect() as connection:
        operation(connection, USER_A, UNKNOWN_ID)


# --- DoD-6: PATCH semantics (D7) ----------------------------------------------------


def test_update_with_only_the_name_keeps_the_sheet__DoD6(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-6 — US-021.AC-1, D7: only the supplied field is written; the change is visible
    through a later `get_character`, `created_at` is untouched, `updated_at` not earlier."""
    created = _create(engine, generator, USER_A, "Aria", "# Aria")

    updated = _update(engine, USER_A, created.id, name="Aria Reborn")

    assert updated.name == "Aria Reborn"
    assert updated.sheet == "# Aria"
    assert updated.created_at == created.created_at
    assert updated.updated_at >= created.updated_at
    assert _get(engine, USER_A, created.id) == updated


def test_update_with_only_the_sheet_keeps_the_name__DoD6(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-6 — US-021.AC-1, D7: the sheet alone changes and the name survives."""
    created = _create(engine, generator, USER_A, "Aria", "# Aria")

    updated = _update(engine, USER_A, created.id, sheet="# Aria, rewritten")

    assert updated.name == "Aria"
    assert updated.sheet == "# Aria, rewritten"
    assert updated.created_at == created.created_at
    assert updated.updated_at >= created.updated_at
    assert _get(engine, USER_A, created.id) == updated


def test_update_with_both_fields_changes_both__DoD6(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-6 — US-021.AC-1, D7: both supplied fields are written in one call."""
    created = _create(engine, generator, USER_A, "Aria", "# Aria")

    updated = _update(engine, USER_A, created.id, name="Bastian", sheet="# Bastian")

    assert updated.name == "Bastian"
    assert updated.sheet == "# Bastian"
    assert updated.created_at == created.created_at
    assert updated.updated_at >= created.updated_at
    assert _get(engine, USER_A, created.id) == updated


def test_update_with_neither_field_returns_the_row_with_updated_at_unchanged__DoD6(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-6 — D7: a PATCH supplying neither field writes nothing and answers the current row."""
    created = _create(engine, generator, USER_A, "Aria", "# Aria")

    unchanged = _update(engine, USER_A, created.id)

    assert unchanged == created
    assert unchanged.updated_at == created.updated_at


# --- DoD-7: archive ------------------------------------------------------------------


def test_archive_sets_archived_at_and_moves_it_out_of_the_working_list__DoD7(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-7 — US-086.AC-1, US-086.AC-3: archived is a stamped `archived_at`; the row leaves
    the default listing, stays in the include-archived listing and stays readable by id."""
    created = _create(engine, generator, USER_A, "Aria", "# Aria")

    archived = _archive(engine, USER_A, created.id)

    assert archived.archived_at is not None
    assert FIXED_WIDTH_TIMESTAMP.match(archived.archived_at) is not None
    assert _ids(_list(engine, USER_A)) == []
    assert _ids(_list_all(engine, USER_A)) == [created.id]
    assert _get(engine, USER_A, created.id) == archived


def test_archiving_an_already_archived_character_writes_nothing__DoD7(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-7 — D9: archive is idempotent — the original `archived_at` and `updated_at` stand."""
    created = _create(engine, generator, USER_A, "Aria", "# Aria")
    first = _archive(engine, USER_A, created.id)

    second = _archive(engine, USER_A, created.id)

    assert second.archived_at == first.archived_at
    assert second.updated_at == first.updated_at


# --- DoD-8: restore ------------------------------------------------------------------


def test_restore_clears_archived_at_and_returns_it_to_the_working_list__DoD8(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-8 — US-086.AC-2: restoring an archived character clears `archived_at` and the
    row is back in the default listing."""
    created = _create(engine, generator, USER_A, "Aria", "# Aria")
    _archive(engine, USER_A, created.id)

    restored = _restore(engine, USER_A, created.id)

    assert restored.archived_at is None
    assert _ids(_list(engine, USER_A)) == [created.id]


def test_restoring_a_working_character_returns_it_unchanged__DoD8(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-8 — D9: restore on a working character is a no-op; nothing is written."""
    created = _create(engine, generator, USER_A, "Aria", "# Aria")

    restored = _restore(engine, USER_A, created.id)

    assert restored == created
    assert restored.updated_at == created.updated_at


# --- DoD-9: editing an archived character -------------------------------------------


def test_update_on_an_archived_character_leaves_archived_at_unchanged__DoD9(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-9 — editing an archived character is allowed and does not change its archive stamp."""
    created = _create(engine, generator, USER_A, "Aria", "# Aria")
    archived = _archive(engine, USER_A, created.id)

    updated = _update(engine, USER_A, created.id, name="Aria Reborn", sheet="# Reborn")

    assert updated.name == "Aria Reborn"
    assert updated.sheet == "# Reborn"
    assert updated.archived_at == archived.archived_at
    assert _get(engine, USER_A, created.id) == updated


# --- DoD-10: a read leaves no transaction open ---------------------------------------


def test_list_characters_leaves_no_transaction_open__DoD10(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-10 — after a listing, a following `connection.begin()` on the same connection
    must succeed, so the read did not leave its autobegun transaction standing."""
    _create(engine, generator, USER_A, "Aria", "# Aria")

    with engine.connect() as connection:
        list_characters(connection, USER_A)
        transaction = connection.begin()
        transaction.rollback()


def test_get_character_leaves_no_transaction_open__DoD10(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-10 — the same for a single read by id."""
    created = _create(engine, generator, USER_A, "Aria", "# Aria")

    with engine.connect() as connection:
        get_character(connection, USER_A, created.id)
        transaction = connection.begin()
        transaction.rollback()


# --- DoD-11: the module carries no delete path and no HTTP -----------------------------

_DELETE_KEYWORD = re.compile(r"\bdelete\b", re.IGNORECASE)
_FASTAPI_IMPORT = re.compile(r"^\s*(?:from|import)\s+fastapi\b", re.MULTILINE)


def test_the_service_module_has_no_delete_path_and_no_fastapi_import__DoD11() -> None:
    """DoD-11 — R6 and "Routers versus services": the source text carries no `delete(`
    call, no `DELETE` SQL keyword and no `fastapi` import."""
    source = inspect.getsource(characters_module)

    assert "delete(" not in source.lower()
    assert _DELETE_KEYWORD.search(source) is None
    assert _FASTAPI_IMPORT.search(source) is None
