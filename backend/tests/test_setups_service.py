"""Tests for `app/services/setups.py` — feature 010, step 002.

Every expected value comes from `docs/plans/010.setups/002.setups-service.md` (its
Definition of done and Interface intent), from `002.context.md` (the scope-predicate
table, the list read's rollback) and from the feature context's D3 / D5 / D6 / D8 / D9 /
D10 plus the owner-scope (R5), no-delete (R6) and no-default-setup (R2) constraints. Each
test name ends `__S010_002_DoD<n>` with the DoD item it covers.

The file follows `tests/test_characters_service.py`'s pattern: a file-local `engine`
fixture that applies the registry with `schema.metadata.create_all`, one connection per
service call (writes too — the service opens its own transaction), the real
`SnowflakeGenerator` for ordinary tests and a file-local fake where a known id matters.

`setups.user_id` and `setups.character_id` are real foreign keys and the engine turns
`PRAGMA foreign_keys` on, so the FK chain is seeded in order: users, then characters
(a raw insert into the `characters` Table — this module offers no character operation),
then setups through `create_setup`.
"""

import ast
import inspect
import re
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, func, select

from app.db import schema
from app.errors import CharacterNotFoundError, SetupNotFoundError
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services import setups as setups_module
from app.services.setups import (
    Setup,
    archive_setup,
    create_setup,
    get_setup,
    list_setups,
    restore_setup,
    update_setup,
)

TIMESTAMP = "2026-01-01T00:00:00+00:00"

USER_A = 101
USER_B = 202

#: Characters seeded by the `engine` fixture. `CHAR_A_ARCHIVED` carries `archived_at`.
CHAR_A1 = 1_001
CHAR_A2 = 1_002
CHAR_A_ARCHIVED = 1_003
CHAR_B1 = 2_001

#: An id that belongs to no character of any user.
UNKNOWN_CHARACTER_ID = 8_888_888_888

#: An id that belongs to no setup of any user.
UNKNOWN_SETUP_ID = 9_999_999_999

#: `YYYY-MM-DDTHH:MM:SS.ffffff+00:00` — the fixed-width form (DoD-1, DoD-8).
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


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database with the registry applied, two owners and four characters."""
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
    return db_engine


@pytest.fixture
def generator() -> SnowflakeGenerator:
    """One real generator per test, so ids minted within a test never collide."""
    return SnowflakeGenerator(node_id=1)


def _create(
    engine: Engine,
    generator: Any,
    user_id: int,
    character_id: int,
    name: str,
    description: str = "",
) -> Setup:
    with engine.connect() as connection:
        return create_setup(connection, generator, user_id, character_id, name, description)


def _get(engine: Engine, user_id: int, setup_id: int) -> Setup:
    with engine.connect() as connection:
        return get_setup(connection, user_id, setup_id)


def _list(engine: Engine, user_id: int, character_id: int) -> list[Setup]:
    """The default listing — the flag left at its default."""
    with engine.connect() as connection:
        return list_setups(connection, user_id, character_id)


def _list_all(engine: Engine, user_id: int, character_id: int) -> list[Setup]:
    with engine.connect() as connection:
        return list_setups(connection, user_id, character_id, include_archived=True)


def _update(
    engine: Engine,
    user_id: int,
    setup_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Setup:
    with engine.connect() as connection:
        return update_setup(connection, user_id, setup_id, name=name, description=description)


def _archive(engine: Engine, user_id: int, setup_id: int) -> Setup:
    with engine.connect() as connection:
        return archive_setup(connection, user_id, setup_id)


def _restore(engine: Engine, user_id: int, setup_id: int) -> Setup:
    with engine.connect() as connection:
        return restore_setup(connection, user_id, setup_id)


def _ids(values: list[Setup]) -> list[int]:
    return [value.id for value in values]


def _count_setups(engine: Engine) -> int:
    """Rows in the `setups` table, counted directly (DoD-2, DoD-10)."""
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(schema.setups)).scalar_one())


# --- DoD-1: create under the user's own character ---------------------------------------


def test_create_returns_the_minted_id_with_both_timestamps_equal__S010_002_DoD1(
    engine: Engine,
) -> None:
    """DoD-1 — the returned value carries the generator's id, the addressed
    `character_id`, the given name and description, a null `archived_at`, and one instant
    stamped into both timestamps in the fixed-width form."""
    fixed = _FixedIdGenerator(77_777)

    created = _create(engine, fixed, USER_A, CHAR_A1, "Tavern", "# Scene\n\nA tavern.")

    assert created.id == 77_777
    assert created.character_id == CHAR_A1
    assert created.name == "Tavern"
    assert created.description == "# Scene\n\nA tavern."
    assert created.archived_at is None
    assert created.created_at == created.updated_at
    assert FIXED_WIDTH_TIMESTAMP.match(created.created_at)
    assert FIXED_WIDTH_TIMESTAMP.match(created.updated_at)


def test_created_setup_is_returned_by_get_and_is_in_the_listing__S010_002_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-1 — `get_setup` answers an equal value and the character's listing contains
    it."""
    created = _create(engine, generator, USER_A, CHAR_A1, "Tavern", "A tavern.")

    assert _get(engine, USER_A, created.id) == created
    assert created in _list(engine, USER_A, CHAR_A1)


# --- DoD-2: a foreign or nonexistent parent character -----------------------------------


@pytest.mark.parametrize(
    "character_id",
    [CHAR_B1, UNKNOWN_CHARACTER_ID],
    ids=["another-users-character", "nobodys-character"],
)
def test_create_under_a_parent_that_is_not_the_users_is_refused__S010_002_DoD2(
    engine: Engine, generator: SnowflakeGenerator, character_id: int
) -> None:
    """DoD-2 — another user's character id and an id that exists for nobody follow the
    same path: `CharacterNotFoundError`, and nothing is inserted."""
    with pytest.raises(CharacterNotFoundError):
        _create(engine, generator, USER_A, character_id, "Tavern", "A tavern.")

    assert _count_setups(engine) == 0


@pytest.mark.parametrize(
    "character_id",
    [CHAR_B1, UNKNOWN_CHARACTER_ID],
    ids=["another-users-character", "nobodys-character"],
)
def test_listing_under_a_parent_that_is_not_the_users_is_refused__S010_002_DoD2(
    engine: Engine, character_id: int
) -> None:
    """DoD-2 — the same for `list_setups`: not an empty list, an error."""
    with pytest.raises(CharacterNotFoundError):
        _list(engine, USER_A, character_id)

    with pytest.raises(CharacterNotFoundError):
        _list_all(engine, USER_A, character_id)


def test_a_refused_create_adds_no_row_to_an_already_populated_table__S010_002_DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-2 — the refused insert leaves the row count exactly as it was."""
    _create(engine, generator, USER_A, CHAR_A1, "Tavern", "A tavern.")
    before = _count_setups(engine)

    with pytest.raises(CharacterNotFoundError):
        _create(engine, generator, USER_A, CHAR_B1, "Hijacked", "")

    assert _count_setups(engine) == before


# --- DoD-3: an archived parent character is allowed (D5) --------------------------------


def test_create_under_the_users_archived_character_succeeds__S010_002_DoD3(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-3 — the parent check carries no `archived_at` predicate (D5)."""
    created = _create(engine, generator, USER_A, CHAR_A_ARCHIVED, "Tavern", "A tavern.")

    assert created.character_id == CHAR_A_ARCHIVED
    assert created.archived_at is None


def test_listing_under_the_users_archived_character_succeeds__S010_002_DoD3(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-3 — the archived parent's setups list like any other character's."""
    created = _create(engine, generator, USER_A, CHAR_A_ARCHIVED, "Tavern", "A tavern.")

    assert _ids(_list(engine, USER_A, CHAR_A_ARCHIVED)) == [created.id]
    assert _ids(_list_all(engine, USER_A, CHAR_A_ARCHIVED)) == [created.id]


# --- DoD-4: the listing is scoped to one owner and one character ------------------------


def test_listing_returns_only_the_addressed_characters_setups__S010_002_DoD4(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-4 — with two users each owning a character with setups, the listing carries
    only the addressed character's rows (R5), with and without the flag. The caller's
    other character's setups are excluded too."""
    mine = _create(engine, generator, USER_A, CHAR_A1, "Mine", "")
    my_other = _create(engine, generator, USER_A, CHAR_A2, "My other", "")
    theirs = _create(engine, generator, USER_B, CHAR_B1, "Theirs", "")

    assert _ids(_list(engine, USER_A, CHAR_A1)) == [mine.id]
    assert _ids(_list_all(engine, USER_A, CHAR_A1)) == [mine.id]
    assert _ids(_list(engine, USER_A, CHAR_A2)) == [my_other.id]
    assert _ids(_list(engine, USER_B, CHAR_B1)) == [theirs.id]
    assert _ids(_list_all(engine, USER_B, CHAR_B1)) == [theirs.id]


def test_a_foreign_setup_is_absent_even_from_the_include_archived_listing__S010_002_DoD4(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-4 — the flag widens the archive filter only, never the owner scope."""
    theirs = _create(engine, generator, USER_B, CHAR_B1, "Theirs", "")
    _archive(engine, USER_B, theirs.id)

    assert theirs.id not in _ids(_list_all(engine, USER_A, CHAR_A1))
    assert theirs.id not in _ids(_list_all(engine, USER_A, CHAR_A2))


# --- DoD-5: the archive filter and the order (D10) -------------------------------------


def test_default_listing_excludes_archived_and_is_newest_created_first__S010_002_DoD5(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-5 — without the flag the archived row is gone and the rest come back newest
    created first (`created_at DESC, id DESC`, D10)."""
    first = _create(engine, generator, USER_A, CHAR_A1, "First", "")
    second = _create(engine, generator, USER_A, CHAR_A1, "Second", "")
    third = _create(engine, generator, USER_A, CHAR_A1, "Third", "")
    _archive(engine, USER_A, second.id)

    assert _ids(_list(engine, USER_A, CHAR_A1)) == [third.id, first.id]


def test_include_archived_listing_carries_both_states_newest_first__S010_002_DoD5(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-5 — with the flag the working and archived rows come back together, still
    newest created first."""
    first = _create(engine, generator, USER_A, CHAR_A1, "First", "")
    second = _create(engine, generator, USER_A, CHAR_A1, "Second", "")
    third = _create(engine, generator, USER_A, CHAR_A1, "Third", "")
    _archive(engine, USER_A, second.id)

    assert _ids(_list_all(engine, USER_A, CHAR_A1)) == [third.id, second.id, first.id]


# --- DoD-6: a setup id that is not the caller's ----------------------------------------

_ScopedOperation = Callable[[Connection, int, int], Setup]


def _attempt_update(connection: Connection, user_id: int, setup_id: int) -> Setup:
    return update_setup(connection, user_id, setup_id, name="hijacked", description="hijacked")


_SCOPED_OPERATIONS: list[_ScopedOperation] = [
    get_setup,
    _attempt_update,
    archive_setup,
    restore_setup,
]

_SCOPED_OPERATION_IDS = ["get", "update", "archive", "restore"]


@pytest.mark.parametrize("operation", _SCOPED_OPERATIONS, ids=_SCOPED_OPERATION_IDS)
def test_another_users_setup_id_is_not_found_and_changes_nothing__S010_002_DoD6(
    engine: Engine, generator: SnowflakeGenerator, operation: _ScopedOperation
) -> None:
    """DoD-6 — every setup-addressed operation refuses a setup the caller does not own
    with `SetupNotFoundError` (R5, D8), and the owner's row is unchanged afterwards."""
    owned = _create(engine, generator, USER_A, CHAR_A1, "Tavern", "A tavern.")

    with engine.connect() as connection:
        with pytest.raises(SetupNotFoundError):
            operation(connection, USER_B, owned.id)

    assert _get(engine, USER_A, owned.id) == owned


@pytest.mark.parametrize("operation", _SCOPED_OPERATIONS, ids=_SCOPED_OPERATION_IDS)
def test_a_setup_id_that_exists_for_nobody_raises_the_same_error__S010_002_DoD6(
    engine: Engine, operation: _ScopedOperation
) -> None:
    """DoD-6 — "no such setup" and "not yours" are one code path and one error: there is
    no "exists but not yours" branch."""
    with engine.connect() as connection:
        with pytest.raises(SetupNotFoundError):
            operation(connection, USER_A, UNKNOWN_SETUP_ID)


# --- DoD-7: the partial update ---------------------------------------------------------


def test_update_with_only_the_name_keeps_the_description__S010_002_DoD7(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-7 — only the supplied field is written; `created_at` and `character_id` stand
    and `updated_at` is not earlier than before. The change is visible through `get`."""
    created = _create(engine, generator, USER_A, CHAR_A1, "Tavern", "A tavern.")

    updated = _update(engine, USER_A, created.id, name="Inn")

    assert updated.name == "Inn"
    assert updated.description == "A tavern."
    assert updated.character_id == created.character_id
    assert updated.created_at == created.created_at
    assert updated.updated_at >= created.updated_at
    assert _get(engine, USER_A, created.id) == updated


def test_update_with_only_the_description_keeps_the_name__S010_002_DoD7(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-7 — the mirror case."""
    created = _create(engine, generator, USER_A, CHAR_A1, "Tavern", "A tavern.")

    updated = _update(engine, USER_A, created.id, description="# Later\n\nA cellar.")

    assert updated.name == "Tavern"
    assert updated.description == "# Later\n\nA cellar."
    assert updated.character_id == created.character_id
    assert updated.created_at == created.created_at
    assert updated.updated_at >= created.updated_at
    assert _get(engine, USER_A, created.id) == updated


def test_update_with_both_fields_changes_both__S010_002_DoD7(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-7 — one call writes both supplied fields."""
    created = _create(engine, generator, USER_A, CHAR_A1, "Tavern", "A tavern.")

    updated = _update(engine, USER_A, created.id, name="Inn", description="A cellar.")

    assert updated.name == "Inn"
    assert updated.description == "A cellar."
    assert updated.character_id == created.character_id
    assert updated.created_at == created.created_at
    assert updated.updated_at >= created.updated_at
    assert _get(engine, USER_A, created.id) == updated


def test_update_with_neither_field_returns_the_row_unchanged__S010_002_DoD7(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-7 — with nothing supplied the operation writes nothing and returns the current
    row, `updated_at` included."""
    created = _create(engine, generator, USER_A, CHAR_A1, "Tavern", "A tavern.")

    updated = _update(engine, USER_A, created.id)

    assert updated == created
    assert updated.updated_at == created.updated_at


# --- DoD-8: archive -------------------------------------------------------------------


def test_archive_sets_archived_at_and_moves_it_out_of_the_working_list__S010_002_DoD8(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-8 — the archived row carries a fixed-width `archived_at`, leaves the default
    listing, stays in the include-archived listing and is still readable by id (R6)."""
    created = _create(engine, generator, USER_A, CHAR_A1, "Tavern", "A tavern.")

    archived = _archive(engine, USER_A, created.id)

    assert archived.archived_at is not None
    assert FIXED_WIDTH_TIMESTAMP.match(archived.archived_at)
    assert created.id not in _ids(_list(engine, USER_A, CHAR_A1))
    assert created.id in _ids(_list_all(engine, USER_A, CHAR_A1))
    assert _get(engine, USER_A, created.id) == archived


def test_archiving_an_already_archived_setup_writes_nothing__S010_002_DoD8(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-8 — idempotent (D9): the second archive keeps the original `archived_at` and
    the same `updated_at`, because a no-op writes nothing."""
    created = _create(engine, generator, USER_A, CHAR_A1, "Tavern", "A tavern.")
    archived = _archive(engine, USER_A, created.id)

    again = _archive(engine, USER_A, created.id)

    assert again.archived_at == archived.archived_at
    assert again.updated_at == archived.updated_at
    assert again == archived


# --- DoD-9: restore, and editing an archived setup -------------------------------------


def test_restore_clears_archived_at_and_returns_it_to_the_working_list__S010_002_DoD9(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-9 — restore nulls `archived_at` and the row is back in the default listing."""
    created = _create(engine, generator, USER_A, CHAR_A1, "Tavern", "A tavern.")
    _archive(engine, USER_A, created.id)

    restored = _restore(engine, USER_A, created.id)

    assert restored.archived_at is None
    assert created.id in _ids(_list(engine, USER_A, CHAR_A1))
    assert _get(engine, USER_A, created.id) == restored


def test_restoring_a_working_setup_returns_it_unchanged__S010_002_DoD9(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-9 — a no-op restore writes nothing: same value, same `updated_at`."""
    created = _create(engine, generator, USER_A, CHAR_A1, "Tavern", "A tavern.")

    restored = _restore(engine, USER_A, created.id)

    assert restored == created
    assert restored.updated_at == created.updated_at


def test_update_on_an_archived_setup_leaves_archived_at_unchanged__S010_002_DoD9(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-9 — editing an archived setup is allowed and never touches its archive
    stamp."""
    created = _create(engine, generator, USER_A, CHAR_A1, "Tavern", "A tavern.")
    archived = _archive(engine, USER_A, created.id)

    updated = _update(engine, USER_A, created.id, name="Inn", description="A cellar.")

    assert updated.name == "Inn"
    assert updated.description == "A cellar."
    assert updated.archived_at == archived.archived_at


# --- DoD-10: no default setup (R2) ----------------------------------------------------


def test_a_fresh_character_has_no_setups_at_all__S010_002_DoD10(engine: Engine) -> None:
    """DoD-10 — a character row exists with no `create_setup` call, so the
    include-archived listing is empty and the table holds no row (R2: no sentinel or
    default setup)."""
    assert _list_all(engine, USER_A, CHAR_A1) == []
    assert _list(engine, USER_A, CHAR_A1) == []
    assert _count_setups(engine) == 0


def test_no_operation_but_create_inserts_a_row__S010_002_DoD10(engine: Engine) -> None:
    """DoD-10 — exercising every other operation of the module leaves the table empty."""
    _list(engine, USER_A, CHAR_A1)
    _list_all(engine, USER_A, CHAR_A1)
    for operation in _SCOPED_OPERATIONS:
        with engine.connect() as connection:
            with pytest.raises(SetupNotFoundError):
                operation(connection, USER_A, UNKNOWN_SETUP_ID)

    assert _count_setups(engine) == 0


# --- DoD-11: a read leaves no transaction open ----------------------------------------


def test_list_setups_leaves_no_transaction_open__S010_002_DoD11(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-11 — after a listing, a following `connection.begin()` on the same connection
    must succeed, so the read did not leave its autobegun transaction standing."""
    _create(engine, generator, USER_A, CHAR_A1, "Tavern", "A tavern.")

    with engine.connect() as connection:
        list_setups(connection, USER_A, CHAR_A1)
        transaction = connection.begin()
        transaction.rollback()


def test_get_setup_leaves_no_transaction_open__S010_002_DoD11(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-11 — the same for a single read by id."""
    created = _create(engine, generator, USER_A, CHAR_A1, "Tavern", "A tavern.")

    with engine.connect() as connection:
        get_setup(connection, USER_A, created.id)
        transaction = connection.begin()
        transaction.rollback()


def test_a_refused_listing_leaves_no_transaction_open__S010_002_DoD11(
    engine: Engine,
) -> None:
    """DoD-11 — the rollback happens on the raising exit too: after `list_setups` raised
    `CharacterNotFoundError`, a following `connection.begin()` still succeeds."""
    with engine.connect() as connection:
        with pytest.raises(CharacterNotFoundError):
            list_setups(connection, USER_A, CHAR_B1)
        transaction = connection.begin()
        transaction.rollback()


# --- DoD-12: no delete path, no HTTP, no sibling service ------------------------------

_DELETE_KEYWORD = re.compile(r"\bdelete\b", re.IGNORECASE)
_FASTAPI_IMPORT = re.compile(r"^\s*(?:from|import)\s+fastapi\b", re.MULTILINE)

#: The module no statement of this service may import from (D6).
_FORBIDDEN_IMPORT = "app.services.characters"


def test_the_service_module_has_no_delete_path_and_no_fastapi_import__S010_002_DoD12() -> None:
    """DoD-12 — R6 and "Routers versus services": the source text carries no `delete(`
    call, no `DELETE` SQL keyword and no `fastapi` import."""
    source = inspect.getsource(setups_module)

    assert "delete(" not in source.lower()
    assert _DELETE_KEYWORD.search(source) is None
    assert _FASTAPI_IMPORT.search(source) is None


def test_the_service_module_does_not_import_the_characters_service__S010_002_DoD12() -> None:
    """DoD-12 — D6: the parent check is this module's own scoped select, so nothing is
    imported from `app.services.characters`."""
    tree = ast.parse(inspect.getsource(setups_module))

    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module == _FORBIDDEN_IMPORT or node.module.startswith(
                _FORBIDDEN_IMPORT + "."
            ):
                offenders.append(f"from {node.module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == _FORBIDDEN_IMPORT or alias.name.startswith(
                    _FORBIDDEN_IMPORT + "."
                ):
                    offenders.append(f"import {alias.name}")

    assert offenders == []
