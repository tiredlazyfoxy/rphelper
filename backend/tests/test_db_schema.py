"""Step 005 — the table-definition registry (`app/db/schema.py`).

Covers DoD-7: `db.schema` exposes a module-level metadata object whose table collection
is enumerable by name — the shape feature 007 will walk.

Feature 003, step 001 edits this file: the 001-era assertion that the collection is
**empty** is deleted deliberately (003/001 DoD-7, `context.md` D14), the enumerability
assertion now also requires `users`, and the `users` table (003/001 DoD-1..3) and the role
enum (003/001 DoD-4) are covered below.
"""

from collections.abc import Iterator, Mapping
from enum import Enum
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, MetaData, Table, UniqueConstraint, text
from sqlalchemy.dialects import sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from app import roles
from app.db import schema
from app.roles import Role


def test_schema_module_exposes_a_module_level_metadata_object__DoD7() -> None:
    """DoD-7 — the registry is a module-level `MetaData` on `app.db.schema`."""
    assert hasattr(schema, "metadata")
    assert isinstance(schema.metadata, MetaData)


def test_registry_table_collection_is_enumerable_by_name__DoD7() -> None:
    """DoD-7 — the collection is a name-keyed mapping, which is what 007 walks.

    003/001 DoD-7 — the emptiness sub-clause is deleted; the collection contains `users`.
    """
    tables = schema.metadata.tables
    assert isinstance(tables, Mapping)
    names = list(tables)
    assert all(isinstance(name, str) for name in names)
    assert "users" in names
    assert "users" in [table.name for table in tables.values()]


# --- Feature 003 / step 001 -----------------------------------------------------------

USERS_COLUMNS = {
    "id",
    "username",
    "password_hash",
    "role",
    "is_enabled",
    "rp_language",
    "preferred_language",
    "created_at",
    "updated_at",
}

TIMESTAMP = "2026-09-29T12:00:00+00:00"
FAKE_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdHNhbHQ$aGFzaGhhc2hoYXNoaGFzaA"

RAW_INSERT = text(
    "INSERT INTO users (id, username, password_hash, role, is_enabled, created_at, updated_at) "
    "VALUES (:id, :username, :password_hash, :role, :is_enabled, :created_at, :updated_at)"
)


def _users() -> Table:
    return schema.metadata.tables["users"]


def _raw_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": 1,
        "username": "someone",
        "password_hash": FAKE_HASH,
        "role": "roleplayer",
        "is_enabled": 1,
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
    }
    row.update(overrides)
    return row


@pytest.fixture
def users_connection(db_engine: Engine) -> Iterator[Connection]:
    """A connection to a real per-test SQLite file with the registry's `users` table created."""
    with db_engine.connect() as connection:
        _users().create(connection)
        connection.commit()
        yield connection


# --- 003/001 DoD-1: exactly data-model.md's columns ------------------------------------


def test_registry_exposes_a_users_table__DoD1() -> None:
    """003/001 DoD-1 — the registry carries a table named `users`."""
    assert "users" in schema.metadata.tables
    assert isinstance(_users(), Table)
    assert _users().name == "users"


def test_users_table_has_exactly_the_data_model_columns__DoD1() -> None:
    """003/001 DoD-1 — exactly the nine documented columns, and no others."""
    names = [column.name for column in _users().columns]
    assert len(names) == len(set(names))
    assert set(names) == USERS_COLUMNS


def test_users_table_carries_no_removed_or_forbidden_column__DoD1() -> None:
    """003/001 DoD-1 — no `is_admin` boolean and none of the three removed defaults."""
    names = {column.name for column in _users().columns}
    for forbidden in ("is_admin", "default_model_ref", "default_system_prompt", "default_tools"):
        assert forbidden not in names


def test_users_table_created_in_a_real_database_has_exactly_the_columns__DoD1(
    users_connection: Connection,
) -> None:
    """003/001 DoD-1 — the created table in SQLite carries exactly the nine columns."""
    rows = users_connection.execute(text("PRAGMA table_info(users)")).all()
    assert {row[1] for row in rows} == USERS_COLUMNS


# --- 003/001 DoD-2: keys, uniqueness, nullability --------------------------------------


def test_id_is_the_sole_primary_key__DoD2() -> None:
    """003/001 DoD-2 — `id` is the primary key, alone."""
    assert [column.name for column in _users().primary_key.columns] == ["id"]


def test_id_does_not_autoincrement__DoD2() -> None:
    """003/001 DoD-2 — the id is minted before the INSERT: no autoincrement."""
    assert _users().c.id.autoincrement is False


def test_users_ddl_contains_no_autoincrement__DoD2() -> None:
    """003/001 DoD-2 — the SQLite DDL for `users` never says AUTOINCREMENT."""
    ddl = str(CreateTable(_users()).compile(dialect=sqlite.dialect()))
    assert "AUTOINCREMENT" not in ddl.upper()


def test_explicit_application_minted_id_is_stored_as_given__DoD2(users_connection: Connection) -> None:
    """003/001 DoD-2 — an id supplied by the application (a 64-bit value) is kept verbatim."""
    minted = 2**62 + 12345
    users_connection.execute(RAW_INSERT, _raw_row(id=minted))
    stored = users_connection.execute(text("SELECT id FROM users")).scalar_one()
    assert stored == minted


def _username_is_unique_in_metadata(table: Table) -> bool:
    if table.c.username.unique:
        return True
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint) and [c.name for c in constraint.columns] == ["username"]:
            return True
    return any(index.unique and [c.name for c in index.columns] == ["username"] for index in table.indexes)


def test_username_is_declared_unique__DoD2() -> None:
    """003/001 DoD-2 — `username` is unique in the table declaration."""
    assert _username_is_unique_in_metadata(_users())


def test_duplicate_username_is_rejected_by_the_database__DoD2(users_connection: Connection) -> None:
    """003/001 DoD-2 — a second row with the same username is refused by SQLite."""
    users_connection.execute(RAW_INSERT, _raw_row(id=1, username="alice"))
    with pytest.raises(IntegrityError):
        users_connection.execute(RAW_INSERT, _raw_row(id=2, username="alice"))


@pytest.mark.parametrize("column", ["rp_language", "preferred_language"])
def test_language_columns_are_nullable__DoD2(column: str) -> None:
    """003/001 DoD-2 — the two user-level language defaults are nullable."""
    assert _users().c[column].nullable is True


@pytest.mark.parametrize("column", ["username", "password_hash", "role", "is_enabled"])
def test_required_columns_are_not_nullable__DoD2(column: str) -> None:
    """003/001 DoD-2 — username, password_hash, role and is_enabled are NOT NULL."""
    assert _users().c[column].nullable is False


def test_row_without_language_values_is_accepted__DoD2(users_connection: Connection) -> None:
    """003/001 DoD-2 — a row omitting both language columns stores NULLs for them."""
    users_connection.execute(RAW_INSERT, _raw_row())
    row = users_connection.execute(text("SELECT rp_language, preferred_language FROM users")).one()
    assert tuple(row) == (None, None)


# --- 003/001 DoD-3: the role domain is enforced by the table ---------------------------


@pytest.mark.parametrize("value", ["roleplayer", "admin"])
def test_role_column_accepts_each_documented_value_raw__DoD3(users_connection: Connection, value: str) -> None:
    """003/001 DoD-3 — each of the two documented strings is accepted by SQLite."""
    users_connection.execute(RAW_INSERT, _raw_row(role=value))
    stored = users_connection.execute(text("SELECT role FROM users")).scalar_one()
    assert stored == value


@pytest.mark.parametrize("value", ["superuser", "ADMIN", "Admin", "ROLEPLAYER", "", "moderator"])
def test_role_column_rejects_a_third_value_in_a_real_database__DoD3(
    users_connection: Connection, value: str
) -> None:
    """003/001 DoD-3 — any other value is refused by the database itself, not by Python."""
    with pytest.raises(IntegrityError):
        users_connection.execute(RAW_INSERT, _raw_row(role=value))


@pytest.mark.parametrize(("member", "stored"), [(Role.ROLEPLAYER, "roleplayer"), (Role.ADMIN, "admin")])
def test_role_enum_member_inserted_through_core_stores_its_documented_value__DoD3(
    users_connection: Connection, member: Role, stored: str
) -> None:
    """003/001 DoD-3 — writing a member through the table stores the documented string."""
    users_connection.execute(
        _users().insert().values(
            id=7,
            username="bob",
            password_hash=FAKE_HASH,
            role=member,
            is_enabled=True,
            created_at=TIMESTAMP,
            updated_at=TIMESTAMP,
        )
    )
    raw = users_connection.execute(text("SELECT role FROM users WHERE id = 7")).scalar_one()
    assert raw == stored
    read_back = users_connection.execute(_users().select().where(_users().c.id == 7)).one()
    assert read_back.role == member
    assert read_back.role == stored


# --- 003/001 DoD-4: the role enum -------------------------------------------------------


def test_role_enum_has_exactly_two_members__DoD4() -> None:
    """003/001 DoD-4 — two members, no more."""
    assert issubclass(Role, Enum)
    assert len(list(Role)) == 2


def test_role_enum_values_are_the_stored_strings__DoD4() -> None:
    """003/001 DoD-4 — the member values are exactly `roleplayer` and `admin`."""
    assert {member.value for member in Role} == {"roleplayer", "admin"}
    assert Role("roleplayer") is Role.ROLEPLAYER
    assert Role("admin") is Role.ADMIN


def test_role_members_compare_equal_to_their_strings__DoD4() -> None:
    """003/001 DoD-4 — a string enum: each member equals the text the column stores."""
    assert Role.ADMIN == "admin"
    assert Role.ROLEPLAYER == "roleplayer"
    assert isinstance(Role.ADMIN, str)


def test_role_enum_class_carries_no_helper__DoD4() -> None:
    """003/001 DoD-4 — no ladder, comparison or dependency helper on the enum class."""
    extras = [
        name
        for name in vars(Role)
        if not name.startswith("_") and name not in Role.__members__
    ]
    assert extras == []


def test_roles_module_defines_nothing_but_the_enum__DoD4() -> None:
    """003/001 DoD-4 — no ladder mapping, comparison helper or dependency factory in the module."""
    public = {name: value for name, value in vars(roles).items() if not name.startswith("_")}
    defined_here = [
        name
        for name, value in public.items()
        if getattr(value, "__module__", None) == roles.__name__
    ]
    assert defined_here == ["Role"]
    assert not any(isinstance(value, Mapping) for value in public.values())
    assert not any(
        callable(value) and getattr(value, "__module__", None) == roles.__name__ and value is not Role
        for value in public.values()
    )
