"""Step 005 — the table-definition registry (`app/db/schema.py`).

Covers DoD-7: `db.schema` exposes a module-level metadata object whose table collection
is enumerable by name — the shape feature 007 will walk.

Feature 003, step 001 edits this file: the 001-era assertion that the collection is
**empty** is deleted deliberately (003/001 DoD-7, `context.md` D14), the enumerability
assertion now also requires `users`, and the `users` table (003/001 DoD-1..3) and the role
enum (003/001 DoD-4) are covered below.
"""

import importlib
import sys
from collections.abc import Iterator, Mapping
from enum import Enum
from typing import Any

import pytest
from sqlalchemy import (
    BigInteger,
    Boolean,
    Connection,
    Engine,
    MetaData,
    Select,
    String,
    Table,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

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

# 005/001 DoD-2 (feature 005 context.md D2): the 003/001 "exactly nine columns" set is
# deliberately widened to ten by adding `last_login_at`. Nothing else in this file changes
# because of it.
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
    "last_login_at",
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
    """003/001 DoD-1 — exactly the documented columns, and no others.

    005/001 DoD-2 — updated deliberately from nine to ten: `last_login_at` joins the set.
    """
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
    """003/001 DoD-1 — the created table in SQLite carries exactly the documented columns.

    005/001 DoD-2 — ten since `last_login_at` was added.
    """
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


# 004/002 DoD-3 (feature 004 context.md D15, item 1): the 003/001 DoD-4 purity clause —
# "`app/roles.py` defines nothing but the enum: no ladder mapping, no comparison helper" —
# was deleted here deliberately, because step 004/002 adds `ROLE_LADDER` and the pure
# comparison to that module. The two-members and member-value assertions above stay, and
# the enum *class* still carries no helper (the ladder is module-level). The module's new
# surface, and that it still exposes no dependency / `Request` / `fastapi` import, is
# asserted in `test_dependencies.py` (`__DoD3`).


# ======================================================================================
# Feature 004, step 001 (`001.auth-sessions-and-service.md`) — the `auth_sessions` table.
# Expected values come from that step's DoD-1 / DoD-2 and `data-model.md`'s column list
# as the step file restates it. Tests are suffixed `__S004_001_DoD<n>` to keep them apart
# from the 001/003 items above.
# ======================================================================================

AUTH_SESSIONS_COLUMNS = {"id", "user_id", "token_hash", "created_at", "expires_at", "revoked_at"}

RAW_SESSION_INSERT = text(
    "INSERT INTO auth_sessions (id, user_id, token_hash, created_at, expires_at, revoked_at) "
    "VALUES (:id, :user_id, :token_hash, :created_at, :expires_at, :revoked_at)"
)


def _auth_sessions() -> Table:
    return schema.metadata.tables["auth_sessions"]


def _raw_session(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": 100,
        "user_id": 1,
        "token_hash": "digest-one",
        "created_at": TIMESTAMP,
        "expires_at": "2026-10-29T12:00:00+00:00",
        "revoked_at": None,
    }
    row.update(overrides)
    return row


@pytest.fixture
def registry_connection(db_engine: Engine) -> Iterator[Connection]:
    """A connection to a per-test SQLite file with the whole registry created, one user seeded."""
    with db_engine.connect() as connection:
        schema.metadata.create_all(connection)
        connection.execute(RAW_INSERT, _raw_row(id=1, username="someone"))
        connection.commit()
        yield connection


# --- 004/001 DoD-1: exactly the six columns, and their nullability ---------------------


def test_registry_exposes_an_auth_sessions_table__S004_001_DoD1() -> None:
    """004/001 DoD-1 — the registry carries a table named `auth_sessions`."""
    assert "auth_sessions" in schema.metadata.tables
    assert isinstance(_auth_sessions(), Table)
    assert _auth_sessions().name == "auth_sessions"


def test_auth_sessions_has_exactly_the_data_model_columns__S004_001_DoD1() -> None:
    """004/001 DoD-1 — exactly id, user_id, token_hash, created_at, expires_at, revoked_at."""
    names = [column.name for column in _auth_sessions().columns]
    assert len(names) == len(set(names))
    assert set(names) == AUTH_SESSIONS_COLUMNS


def test_auth_sessions_revoked_at_is_nullable__S004_001_DoD1() -> None:
    """004/001 DoD-1 — `revoked_at` is nullable (NULL until revoked)."""
    assert _auth_sessions().c.revoked_at.nullable is True


@pytest.mark.parametrize("column", ["id", "user_id", "token_hash", "created_at", "expires_at"])
def test_auth_sessions_other_columns_are_not_nullable__S004_001_DoD1(column: str) -> None:
    """004/001 DoD-1 — every column but `revoked_at` is NOT NULL."""
    assert _auth_sessions().c[column].nullable is False


def test_auth_sessions_created_in_a_real_database_has_exactly_the_columns__S004_001_DoD1(
    registry_connection: Connection,
) -> None:
    """004/001 DoD-1 — the created SQLite table carries exactly the six columns."""
    rows = registry_connection.execute(text("PRAGMA table_info(auth_sessions)")).all()
    assert {row[1] for row in rows} == AUTH_SESSIONS_COLUMNS


def test_auth_sessions_row_without_revoked_at_is_accepted__S004_001_DoD1(
    registry_connection: Connection,
) -> None:
    """004/001 DoD-1 — a fresh (unrevoked) row stores NULL in `revoked_at`."""
    registry_connection.execute(RAW_SESSION_INSERT, _raw_session())
    stored = registry_connection.execute(text("SELECT revoked_at FROM auth_sessions")).scalar_one()
    assert stored is None


@pytest.mark.parametrize("column", ["user_id", "token_hash", "created_at", "expires_at"])
def test_auth_sessions_rejects_null_in_required_columns__S004_001_DoD1(
    registry_connection: Connection, column: str
) -> None:
    """004/001 DoD-1 — SQLite itself refuses NULL in a NOT NULL column."""
    with pytest.raises(IntegrityError):
        registry_connection.execute(RAW_SESSION_INSERT, _raw_session(**{column: None}))


def test_registry_still_contains_users_beside_auth_sessions__S004_001_DoD1() -> None:
    """004/001 DoD-1 — adding the second table leaves `users` in the registry."""
    assert {"users", "auth_sessions"} <= set(schema.metadata.tables)


# --- 004/001 DoD-2: key, unique digest index, foreign key, user_id index ---------------


def test_auth_sessions_id_is_the_sole_primary_key__S004_001_DoD2() -> None:
    """004/001 DoD-2 — `id` is the primary key, alone."""
    assert [column.name for column in _auth_sessions().primary_key.columns] == ["id"]


def test_auth_sessions_id_does_not_autoincrement__S004_001_DoD2() -> None:
    """004/001 DoD-2 — the id is a minted snowflake, never autoincremented."""
    assert _auth_sessions().c.id.autoincrement is False


def test_auth_sessions_ddl_contains_no_autoincrement__S004_001_DoD2() -> None:
    """004/001 DoD-2 — the SQLite DDL for `auth_sessions` never says AUTOINCREMENT."""
    ddl = str(CreateTable(_auth_sessions()).compile(dialect=sqlite.dialect()))
    assert "AUTOINCREMENT" not in ddl.upper()


def test_auth_sessions_explicit_64_bit_id_is_stored_as_given__S004_001_DoD2(
    registry_connection: Connection,
) -> None:
    """004/001 DoD-2 — an application-minted 64-bit id is kept verbatim."""
    minted = 2**62 + 54321
    registry_connection.execute(RAW_SESSION_INSERT, _raw_session(id=minted))
    stored = registry_connection.execute(text("SELECT id FROM auth_sessions")).scalar_one()
    assert stored == minted


def _single_column_indexes(table: Table, column: str) -> list[Any]:
    return [index for index in table.indexes if [c.name for c in index.columns] == [column]]


def test_token_hash_is_uniquely_indexed__S004_001_DoD2() -> None:
    """004/001 DoD-2 — a unique index covers exactly `token_hash`."""
    indexes = _single_column_indexes(_auth_sessions(), "token_hash")
    assert any(index.unique for index in indexes)


def test_duplicate_token_hash_is_rejected_by_the_database__S004_001_DoD2(
    registry_connection: Connection,
) -> None:
    """004/001 DoD-2 — a second row with the same digest is refused by SQLite."""
    registry_connection.execute(RAW_SESSION_INSERT, _raw_session(id=100, token_hash="same"))
    with pytest.raises(IntegrityError):
        registry_connection.execute(RAW_SESSION_INSERT, _raw_session(id=101, token_hash="same"))


def test_user_id_declares_a_foreign_key_to_users_id__S004_001_DoD2() -> None:
    """004/001 DoD-2 — `user_id` carries a declared foreign key targeting `users.id`."""
    targets = {fk.target_fullname for fk in _auth_sessions().c.user_id.foreign_keys}
    assert targets == {"users.id"}


def test_user_id_foreign_key_is_enforced_in_a_real_database__S004_001_DoD2(
    registry_connection: Connection,
) -> None:
    """004/001 DoD-2 — a row naming no existing user is refused (the engine turns FKs on)."""
    with pytest.raises(IntegrityError):
        registry_connection.execute(RAW_SESSION_INSERT, _raw_session(user_id=999_999))


def test_user_id_is_indexed__S004_001_DoD2() -> None:
    """004/001 DoD-2 — an index covers exactly `user_id`."""
    assert _single_column_indexes(_auth_sessions(), "user_id") != []


def test_user_id_index_exists_in_a_real_database__S004_001_DoD2(registry_connection: Connection) -> None:
    """004/001 DoD-2 — the created table has an index on `user_id` and a unique one on `token_hash`."""
    index_rows = registry_connection.execute(text("PRAGMA index_list(auth_sessions)")).all()
    by_columns: dict[tuple[str, ...], bool] = {}
    for row in index_rows:
        name, unique = row[1], bool(row[2])
        info = registry_connection.execute(text(f'PRAGMA index_info("{name}")')).all()
        columns = tuple(info_row[2] for info_row in info)
        by_columns[columns] = by_columns.get(columns, False) or unique
    assert ("user_id",) in by_columns
    assert by_columns.get(("token_hash",)) is True


# ======================================================================================
# Feature 005, step 001 (`001.last-login-and-session-revoke.md`) — `users.last_login_at`.
# Expected values come from that step's DoD-1 / DoD-2 and `001.context.md`'s column list.
# Tests are suffixed `__S005_001_DoD<n>`.
# ======================================================================================

# The nullability 003/001 asserted for the original nine, plus the new tenth column.
USERS_NULLABILITY = {
    "id": False,
    "username": False,
    "password_hash": False,
    "role": False,
    "is_enabled": False,
    "rp_language": True,
    "preferred_language": True,
    "created_at": False,
    "updated_at": False,
    "last_login_at": True,
}


# --- 005/001 DoD-1: `last_login_at` exists and is nullable; the others keep theirs -----


def test_users_table_carries_a_last_login_at_column__S005_001_DoD1() -> None:
    """005/001 DoD-1 — the registry's `users` table has a `last_login_at` column."""
    assert "last_login_at" in _users().c


def test_last_login_at_is_nullable__S005_001_DoD1() -> None:
    """005/001 DoD-1 — `last_login_at` is nullable."""
    assert _users().c.last_login_at.nullable is True


@pytest.mark.parametrize(("column", "nullable"), sorted(USERS_NULLABILITY.items()))
def test_every_users_column_keeps_its_nullability__S005_001_DoD1(column: str, nullable: bool) -> None:
    """005/001 DoD-1 — the other nine columns keep the nullability 003/001 asserted."""
    assert _users().c[column].nullable is nullable


def test_last_login_at_is_nullable_in_a_real_database__S005_001_DoD1(users_connection: Connection) -> None:
    """005/001 DoD-1 — the created SQLite column carries no NOT NULL flag."""
    rows = users_connection.execute(text("PRAGMA table_info(users)")).all()
    notnull_by_name = {row[1]: bool(row[3]) for row in rows}
    assert notnull_by_name["last_login_at"] is False


def test_row_without_last_login_at_is_accepted_and_stores_null__S005_001_DoD1(
    users_connection: Connection,
) -> None:
    """005/001 DoD-1 — an insert that names no `last_login_at` is accepted and stores NULL."""
    users_connection.execute(RAW_INSERT, _raw_row())
    stored = users_connection.execute(text("SELECT last_login_at FROM users")).scalar_one()
    assert stored is None


def test_last_login_at_holds_an_iso_8601_text_value__S005_001_DoD1(users_connection: Connection) -> None:
    """005/001 DoD-1 — the column stores a UTC ISO-8601 instant as text, read back verbatim."""
    users_connection.execute(RAW_INSERT, _raw_row())
    users_connection.execute(
        _users().update().where(_users().c.id == 1).values(last_login_at=TIMESTAMP)
    )
    stored = users_connection.execute(text("SELECT last_login_at FROM users")).scalar_one()
    assert stored == TIMESTAMP


# --- 005/001 DoD-2: the column set is now exactly ten ----------------------------------


def test_users_table_has_exactly_ten_columns__S005_001_DoD2() -> None:
    """005/001 DoD-2 — the 003/001 nine plus `last_login_at`, and no others."""
    names = [column.name for column in _users().columns]
    assert len(names) == 10
    assert set(names) == USERS_COLUMNS
    assert "last_login_at" in USERS_COLUMNS
    assert USERS_COLUMNS - {"last_login_at"} == {
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


def test_users_created_in_a_real_database_has_exactly_ten_columns__S005_001_DoD2(
    users_connection: Connection,
) -> None:
    """005/001 DoD-2 — the created SQLite `users` table has the same ten columns."""
    rows = users_connection.execute(text("PRAGMA table_info(users)")).all()
    names = [row[1] for row in rows]
    assert len(names) == 10
    assert set(names) == USERS_COLUMNS


def test_auth_sessions_columns_are_unchanged_by_the_users_edit__S005_001_DoD2() -> None:
    """005/001 DoD-2 — the `auth_sessions` column set from 004/001 is untouched."""
    assert {column.name for column in _auth_sessions().columns} == AUTH_SESSIONS_COLUMNS
    assert "last_login_at" not in _auth_sessions().c


# ======================================================================================
# Feature 006, step 001 (`001.tables-errors-and-secret-ref.md`) — `llm_servers` + `models`.
# Expected values come from that step's DoD-1..DoD-7, `data-model.md`'s `llm_servers` and
# `models` sections, and feature 006 `context.md` D1 / D10. Tests are suffixed
# `__S006_001_DoD<n>`.
# ======================================================================================

LLM_SERVERS_COLUMNS = {
    "id",
    "name",
    "kind",
    "base_url",
    "api_key_ref",
    "last_test_at",
    "last_test_ok",
    "last_test_error",
    "created_at",
    "updated_at",
}

MODELS_COLUMNS = {
    "id",
    "server_id",
    "model_name",
    "is_enabled",
    "is_embedding_designated",
    "embedding_dim",
    "created_at",
    "updated_at",
}

# The registry as it stood before this step (users: 003/001 + 005/001; auth_sessions: 004/001).
PRE_006_TABLES = {"users", "auth_sessions"}
NEW_006_TABLES = {"llm_servers", "models"}

# 009/001 DoD-11: tables declared by features *after* 006. A delta written as
# `set(tables) - PRE == NEW` is only true until the next feature adds a table, which is
# what registering `characters` broke. Every feature's delta below is therefore
# "the registry, minus what pre-dated it, minus what later features added". A feature
# that adds a table appends it here and gives its own delta a `LATER_THAN_<n>_TABLES`
# set of its own, so the shape stays the same for 010 and beyond.
LATER_THAN_006_TABLES = {"characters", "setups", "sessions", "messages"}  # 009/001, 010/001, 011/001, 012/001

# context.md D1: the "active" switch admin-surfaces.md describes is deliberately dropped.
FORBIDDEN_SERVER_FLAG_COLUMNS = ("active", "is_active", "enabled")


def _llm_servers() -> Table:
    return schema.metadata.tables["llm_servers"]


def _models() -> Table:
    return schema.metadata.tables["models"]


def _server_values(server_id: int, name: str = "local") -> dict[str, Any]:
    return {
        "id": server_id,
        "name": name,
        "kind": "llamaswap",
        "base_url": "http://127.0.0.1:8080/v1",
        "api_key_ref": None,
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
    }


def _model_values(model_id: int, server_id: int, model_name: str, **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "id": model_id,
        "server_id": server_id,
        "model_name": model_name,
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
    }
    values.update(overrides)
    return values


def _insert_server(connection: Connection, server_id: int, name: str = "local") -> None:
    connection.execute(_llm_servers().insert().values(**_server_values(server_id, name)))


def _insert_model(connection: Connection, model_id: int, server_id: int, model_name: str, **overrides: Any) -> None:
    connection.execute(_models().insert().values(**_model_values(model_id, server_id, model_name, **overrides)))


def _created_table_names(connection: Connection) -> set[str]:
    rows = connection.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'")).all()
    return {row[0] for row in rows if not str(row[0]).startswith("sqlite_")}


@pytest.fixture
def llm_connection(db_engine: Engine) -> Iterator[Connection]:
    """A connection to a fresh per-test SQLite file with the whole registry created."""
    with db_engine.connect() as connection:
        schema.metadata.create_all(connection)
        connection.commit()
        yield connection


# --- 006/001 DoD-1: `llm_servers` has exactly data-model.md's columns; big-int PK ------


def test_registry_exposes_an_llm_servers_table__S006_001_DoD1() -> None:
    """006/001 DoD-1 — the registry carries a table named `llm_servers`."""
    assert "llm_servers" in schema.metadata.tables
    assert isinstance(_llm_servers(), Table)
    assert _llm_servers().name == "llm_servers"


def test_llm_servers_has_exactly_the_data_model_columns__S006_001_DoD1() -> None:
    """006/001 DoD-1 — exactly the columns `data-model.md` names, no more, no fewer."""
    names = [column.name for column in _llm_servers().columns]
    assert len(names) == len(set(names))
    assert set(names) == LLM_SERVERS_COLUMNS


def test_llm_servers_id_is_the_sole_primary_key__S006_001_DoD1() -> None:
    """006/001 DoD-1 — `id` is the primary key, alone."""
    assert [column.name for column in _llm_servers().primary_key.columns] == ["id"]


def test_llm_servers_id_is_a_big_integer__S006_001_DoD1() -> None:
    """006/001 DoD-1 — the snowflake primary key is a big integer."""
    assert isinstance(_llm_servers().c.id.type, BigInteger)


def test_llm_servers_id_does_not_autoincrement__S006_001_DoD1() -> None:
    """006/001 DoD-1 — the id is minted before the INSERT: not autoincrementing."""
    assert _llm_servers().c.id.autoincrement is False


def test_llm_servers_ddl_contains_no_autoincrement__S006_001_DoD1() -> None:
    """006/001 DoD-1 — the SQLite DDL for `llm_servers` never says AUTOINCREMENT."""
    ddl = str(CreateTable(_llm_servers()).compile(dialect=sqlite.dialect()))
    assert "AUTOINCREMENT" not in ddl.upper()


def test_llm_servers_explicit_64_bit_id_is_stored_as_given__S006_001_DoD1(llm_connection: Connection) -> None:
    """006/001 DoD-1 — an application-minted 64-bit id is kept verbatim."""
    minted = 2**62 + 777
    _insert_server(llm_connection, minted)
    stored = llm_connection.execute(text("SELECT id FROM llm_servers")).scalar_one()
    assert stored == minted


@pytest.mark.parametrize("column", ["api_key_ref", "last_test_at", "last_test_ok", "last_test_error"])
def test_llm_servers_pointer_and_last_test_columns_are_nullable__S006_001_DoD1(column: str) -> None:
    """006/001 DoD-1 — the API-key pointer and the three last-test columns are nullable."""
    assert _llm_servers().c[column].nullable is True


@pytest.mark.parametrize("column", ["last_test_at", "created_at", "updated_at"])
def test_llm_servers_timestamps_are_text__S006_001_DoD1(column: str) -> None:
    """006/001 DoD-1 — instants are UTC ISO-8601 text, matching the file's convention."""
    assert isinstance(_llm_servers().c[column].type, String)


def test_llm_servers_last_test_ok_is_a_boolean__S006_001_DoD1() -> None:
    """006/001 DoD-1 — the last-test outcome flag is a boolean."""
    assert isinstance(_llm_servers().c.last_test_ok.type, Boolean)


def test_llm_servers_created_in_a_real_database_has_exactly_the_columns__S006_001_DoD1(
    llm_connection: Connection,
) -> None:
    """006/001 DoD-1 — the created SQLite table carries exactly the documented columns."""
    rows = llm_connection.execute(text("PRAGMA table_info(llm_servers)")).all()
    assert {row[1] for row in rows} == LLM_SERVERS_COLUMNS


def test_llm_servers_row_without_pointer_or_test_result_stores_nulls__S006_001_DoD1(
    llm_connection: Connection,
) -> None:
    """006/001 DoD-1 — a never-tested registration with no pointer is accepted with NULLs there."""
    _insert_server(llm_connection, 1)
    row = llm_connection.execute(
        text("SELECT api_key_ref, last_test_at, last_test_ok, last_test_error FROM llm_servers")
    ).one()
    assert tuple(row) == (None, None, None, None)


# --- 006/001 DoD-2: no active flag on a server (context.md D1) --------------------------


@pytest.mark.parametrize("column", FORBIDDEN_SERVER_FLAG_COLUMNS)
def test_llm_servers_declares_no_active_flag__S006_001_DoD2(column: str) -> None:
    """006/001 DoD-2 — no `active` / `is_active` / `enabled` column on `llm_servers`."""
    assert column not in {c.name for c in _llm_servers().columns}


def test_llm_servers_created_in_a_real_database_has_no_active_flag__S006_001_DoD2(
    llm_connection: Connection,
) -> None:
    """006/001 DoD-2 — the created SQLite table carries none of the forbidden flag columns."""
    rows = llm_connection.execute(text("PRAGMA table_info(llm_servers)")).all()
    names = {row[1] for row in rows}
    for column in FORBIDDEN_SERVER_FLAG_COLUMNS:
        assert column not in names


# --- 006/001 DoD-3: `models` columns; `server_id` FK -> llm_servers.id ON DELETE CASCADE -


def test_registry_exposes_a_models_table__S006_001_DoD3() -> None:
    """006/001 DoD-3 — the registry carries a table named `models`."""
    assert "models" in schema.metadata.tables
    assert isinstance(_models(), Table)
    assert _models().name == "models"


def test_models_has_exactly_the_data_model_columns__S006_001_DoD3() -> None:
    """006/001 DoD-3 — the columns `data-model.md` names, including `embedding_dim`."""
    names = [column.name for column in _models().columns]
    assert len(names) == len(set(names))
    assert set(names) == MODELS_COLUMNS


def test_models_id_is_a_non_autoincrementing_big_integer_primary_key__S006_001_DoD3() -> None:
    """006/001 DoD-3 — the snowflake primary key, alone, big integer, never autoincremented."""
    assert [column.name for column in _models().primary_key.columns] == ["id"]
    assert isinstance(_models().c.id.type, BigInteger)
    assert _models().c.id.autoincrement is False
    ddl = str(CreateTable(_models()).compile(dialect=sqlite.dialect()))
    assert "AUTOINCREMENT" not in ddl.upper()


def test_models_embedding_dim_is_nullable__S006_001_DoD3() -> None:
    """006/001 DoD-3 — `embedding_dim` is nullable (meaningful only on the designated row)."""
    assert _models().c.embedding_dim.nullable is True


def test_models_server_id_is_a_foreign_key_to_llm_servers_id__S006_001_DoD3() -> None:
    """006/001 DoD-3 — `server_id` carries exactly one declared FK, targeting `llm_servers.id`."""
    foreign_keys = list(_models().c.server_id.foreign_keys)
    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "llm_servers.id"


def test_models_server_id_foreign_key_declares_on_delete_cascade__S006_001_DoD3() -> None:
    """006/001 DoD-3 — the FK is declared `ON DELETE CASCADE` (what feature 007 introspects)."""
    foreign_key = next(iter(_models().c.server_id.foreign_keys))
    assert foreign_key.ondelete is not None
    assert foreign_key.ondelete.upper() == "CASCADE"


def test_models_cascade_is_present_in_a_real_database__S006_001_DoD3(llm_connection: Connection) -> None:
    """006/001 DoD-3 — the created SQLite table reports the FK to llm_servers(id) with CASCADE."""
    rows = llm_connection.execute(text("PRAGMA foreign_key_list(models)")).all()
    # PRAGMA foreign_key_list columns: id, seq, table, from, to, on_update, on_delete, match
    matching = [row for row in rows if row[2] == "llm_servers" and row[3] == "server_id"]
    assert len(matching) == 1
    assert matching[0][4] == "id"
    assert str(matching[0][6]).upper() == "CASCADE"


def test_models_created_in_a_real_database_has_exactly_the_columns__S006_001_DoD3(
    llm_connection: Connection,
) -> None:
    """006/001 DoD-3 — the created SQLite table carries exactly the documented columns."""
    rows = llm_connection.execute(text("PRAGMA table_info(models)")).all()
    assert {row[1] for row in rows} == MODELS_COLUMNS


def test_models_row_without_embedding_dim_stores_null__S006_001_DoD3(llm_connection: Connection) -> None:
    """006/001 DoD-3 — a row that names no dimension is accepted and stores NULL there."""
    _insert_server(llm_connection, 1)
    _insert_model(llm_connection, 10, 1, "qwen")
    stored = llm_connection.execute(text("SELECT embedding_dim FROM models")).scalar_one()
    assert stored is None


# --- 006/001 DoD-4: unique (server_id, model_name); non-null flags defaulting to false --


def _has_unique_pair(table: Table, columns: set[str]) -> bool:
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint) and {c.name for c in constraint.columns} == columns:
            return True
    return any(index.unique and {c.name for c in index.columns} == columns for index in table.indexes)


def test_models_declares_a_unique_constraint_on_server_and_model_name__S006_001_DoD4() -> None:
    """006/001 DoD-4 — a uniqueness declaration covers exactly the (server id, model name) pair."""
    assert _has_unique_pair(_models(), {"server_id", "model_name"})


def test_models_does_not_make_model_name_unique_on_its_own__S006_001_DoD4() -> None:
    """006/001 DoD-4 — uniqueness is on the pair, not on the model name alone."""
    assert _models().c.model_name.unique is not True
    assert not _has_unique_pair(_models(), {"model_name"})


@pytest.mark.parametrize("column", ["is_enabled", "is_embedding_designated"])
def test_models_flags_are_non_nullable_booleans__S006_001_DoD4(column: str) -> None:
    """006/001 DoD-4 — the enabled and designation flags are non-nullable booleans."""
    assert _models().c[column].nullable is False
    assert isinstance(_models().c[column].type, Boolean)


def test_models_flags_default_to_false_when_not_supplied__S006_001_DoD4(llm_connection: Connection) -> None:
    """006/001 DoD-4 — a row inserted without either flag reads back false for both."""
    _insert_server(llm_connection, 1)
    _insert_model(llm_connection, 10, 1, "qwen")
    row = llm_connection.execute(
        _models().select().where(_models().c.id == 10)
    ).one()
    assert row.is_enabled is False
    assert row.is_embedding_designated is False
    raw = llm_connection.execute(
        text("SELECT is_enabled, is_embedding_designated FROM models WHERE id = 10")
    ).one()
    assert tuple(raw) == (0, 0)


# --- 006/001 DoD-5: create_all adds exactly the two tables; the pair is enforced ---------


def test_registry_gains_exactly_the_two_new_tables__S006_001_DoD5() -> None:
    """006/001 DoD-5 — beside the tables that pre-date this step, only the two new ones exist.

    009/001 DoD-11 — rescoped: the tables later features declare are subtracted too, so the
    assertion still means "006 added exactly these two" once `characters` and its successors
    exist. It still fails if either 006 table is removed, and if a pre-006 table disappears.
    """
    assert PRE_006_TABLES <= set(schema.metadata.tables)
    assert set(schema.metadata.tables) - PRE_006_TABLES - LATER_THAN_006_TABLES == NEW_006_TABLES


def test_create_all_on_a_fresh_file_database_creates_both_tables__S006_001_DoD5(
    llm_connection: Connection,
) -> None:
    """006/001 DoD-5 — `create_all` against a fresh file creates both, and no other new table.

    009/001 DoD-11 — rescoped the same way as the registry delta above: later features'
    tables are subtracted, 006's two must still be there.
    """
    created = _created_table_names(llm_connection)
    assert NEW_006_TABLES <= created
    assert PRE_006_TABLES <= created
    assert created - PRE_006_TABLES - LATER_THAN_006_TABLES == NEW_006_TABLES


def test_duplicate_server_and_model_name_pair_is_refused__S006_001_DoD5(llm_connection: Connection) -> None:
    """006/001 DoD-5 — a second row with the same (server id, model name) is refused by SQLite."""
    _insert_server(llm_connection, 1)
    _insert_model(llm_connection, 10, 1, "qwen")
    with pytest.raises(IntegrityError):
        _insert_model(llm_connection, 11, 1, "qwen")


def test_same_model_name_under_two_servers_is_accepted__S006_001_DoD5(llm_connection: Connection) -> None:
    """006/001 DoD-5 — the same model name under two different servers is two legal rows."""
    _insert_server(llm_connection, 1, "first")
    _insert_server(llm_connection, 2, "second")
    _insert_model(llm_connection, 10, 1, "gpt-4o")
    _insert_model(llm_connection, 11, 2, "gpt-4o")
    rows = llm_connection.execute(
        text("SELECT server_id FROM models WHERE model_name = 'gpt-4o' ORDER BY server_id")
    ).all()
    assert [row[0] for row in rows] == [1, 2]


def test_two_different_model_names_under_one_server_are_accepted__S006_001_DoD5(
    llm_connection: Connection,
) -> None:
    """006/001 DoD-5 — the constraint is on the pair: distinct names under one server coexist."""
    _insert_server(llm_connection, 1)
    _insert_model(llm_connection, 10, 1, "qwen")
    _insert_model(llm_connection, 11, 1, "llama")
    count = llm_connection.execute(text("SELECT COUNT(*) FROM models WHERE server_id = 1")).scalar_one()
    assert count == 2


# --- 006/001 DoD-6: deleting a server cascades to its models rows only -------------------


def test_deleting_a_server_removes_only_its_models_rows__S006_001_DoD6(db_engine: Engine) -> None:
    """006/001 DoD-6 — with `PRAGMA foreign_keys = ON`, deleting a server removes its `models`
    rows and leaves every other server's rows untouched."""
    with db_engine.connect() as setup:
        schema.metadata.create_all(setup)
        setup.commit()

    with db_engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = ON")
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1

        _insert_server(connection, 1, "doomed")
        _insert_server(connection, 2, "kept")
        _insert_server(connection, 3, "also-kept")
        _insert_model(connection, 10, 1, "qwen")
        _insert_model(connection, 11, 1, "llama")
        _insert_model(connection, 20, 2, "qwen")
        _insert_model(connection, 21, 2, "embed", is_embedding_designated=True, embedding_dim=768)
        _insert_model(connection, 30, 3, "llama", is_enabled=True)
        connection.commit()

        connection.execute(_llm_servers().delete().where(_llm_servers().c.id == 1))
        connection.commit()

        servers = connection.execute(text("SELECT id FROM llm_servers ORDER BY id")).all()
        assert [row[0] for row in servers] == [2, 3]

        remaining = connection.execute(
            text(
                "SELECT id, server_id, model_name, is_enabled, is_embedding_designated, embedding_dim "
                "FROM models ORDER BY id"
            )
        ).all()
        assert [tuple(row) for row in remaining] == [
            (20, 2, "qwen", 0, 0, None),
            (21, 2, "embed", 0, 1, 768),
            (30, 3, "llama", 1, 0, None),
        ]
        orphaned = connection.execute(text("SELECT COUNT(*) FROM models WHERE server_id = 1")).scalar_one()
        assert orphaned == 0


# --- 006/001 DoD-7: one shared metadata; no import-side-effect registration --------------


def test_every_registry_table_uses_the_one_shared_metadata__S006_001_DoD7() -> None:
    """006/001 DoD-7 — every table in the registry, the two new ones included, is bound to `metadata`."""
    tables = schema.metadata.tables
    assert NEW_006_TABLES <= set(tables)
    for table in tables.values():
        assert table.metadata is schema.metadata


def test_every_registry_table_is_a_literal_in_the_schema_module__S006_001_DoD7() -> None:
    """006/001 DoD-7 — each registered table is a `Table` object bound in `app.db.schema` itself."""
    module_tables = [value for value in vars(schema).values() if isinstance(value, Table)]
    for table in schema.metadata.tables.values():
        assert any(candidate is table for candidate in module_tables), table.name
    for table in module_tables:
        assert table.metadata is schema.metadata


def test_importing_this_steps_modules_registers_no_table__S006_001_DoD7() -> None:
    """006/001 DoD-7 — importing the step's other modules adds nothing to the registry."""
    before = set(schema.metadata.tables)
    for module_name in ("app.errors", "app.config", "app.models.secret_ref", "app.models"):
        importlib.import_module(module_name)
    assert set(schema.metadata.tables) == before


def test_no_other_app_module_defines_its_own_table__S006_001_DoD7() -> None:
    """006/001 DoD-7 — no loaded `app.*` module holds a `Table` that is not one of the registry's
    own objects, and no `app.*` module defines a second `MetaData`."""
    importlib.import_module("app.models.secret_ref")
    registry_tables = list(schema.metadata.tables.values())
    for module_name, module in list(sys.modules.items()):
        if module is None or not (module_name == "app" or module_name.startswith("app.")):
            continue
        if module_name == "app.db.schema":
            continue
        for value in list(vars(module).values()):
            if isinstance(value, Table):
                assert any(value is table for table in registry_tables), (module_name, value.name)
            if isinstance(value, MetaData):
                assert value is schema.metadata, module_name


# ======================================================================================
# Feature 009, step 001 (`001.table-error-models.md`) — the `characters` table.
# Expected values come from that step's DoD-1..4 and feature 009's context.md D5.
# Tests are suffixed `__S009_001_DoD<n>`.
# ======================================================================================

# The registry as it stood before this step (003/001 + 005/001, 004/001, 006/001).
PRE_009_TABLES = PRE_006_TABLES | NEW_006_TABLES
NEW_009_TABLES = {"characters"}
# DoD-1/DoD-11's shared shape: features after 009 append their tables here (010/001 DoD-8
# added "setups"; 011/001 DoD-9 added "sessions"; 012/001 DoD-1 added "messages"), so this
# delta keeps meaning "009 added exactly `characters`".
LATER_THAN_009_TABLES: set[str] = {"setups", "sessions", "messages"}

CHARACTERS_COLUMNS = {"id", "user_id", "name", "sheet", "archived_at", "created_at", "updated_at"}

# D5 / data-model.md R1: columns 009 must NOT declare — three deferred to 017, two never.
FORBIDDEN_CHARACTERS_COLUMNS = ("model_ref", "system_prompt", "tools", "rp_language", "preferred_language")

RAW_CHARACTER_INSERT = text(
    "INSERT INTO characters (id, user_id, name, sheet, archived_at, created_at, updated_at) "
    "VALUES (:id, :user_id, :name, :sheet, :archived_at, :created_at, :updated_at)"
)


def _characters() -> Table:
    return schema.metadata.tables["characters"]


def _raw_character(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": 10,
        "user_id": 1,
        "name": "Aria",
        "sheet": "# Aria\n",
        "archived_at": None,
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
    }
    row.update(overrides)
    return row


# --- 009/001 DoD-1: the registry gains `characters` and nothing else --------------------


def test_registry_gains_exactly_the_characters_table__S009_001_DoD1() -> None:
    """009/001 DoD-1 — `characters` is registered, and it is the only table 009 declares."""
    assert "characters" in schema.metadata.tables
    assert isinstance(_characters(), Table)
    assert _characters().name == "characters"
    assert set(schema.metadata.tables) - PRE_009_TABLES - LATER_THAN_009_TABLES == NEW_009_TABLES


def test_registry_still_carries_every_pre_009_table__S009_001_DoD1() -> None:
    """009/001 DoD-1 — 009 only adds: every table declared before it is still registered."""
    assert PRE_009_TABLES <= set(schema.metadata.tables)


# --- 009/001 DoD-2: exactly seven columns, the primary key and nullability --------------


def test_characters_has_exactly_the_seven_declared_columns__S009_001_DoD2() -> None:
    """009/001 DoD-2 — exactly id, user_id, name, sheet, archived_at, created_at, updated_at."""
    names = [column.name for column in _characters().columns]
    assert len(names) == len(set(names))
    assert set(names) == CHARACTERS_COLUMNS


def test_characters_id_is_the_primary_key__S009_001_DoD2() -> None:
    """009/001 DoD-2 — `id` alone is the primary key."""
    assert [column.name for column in _characters().primary_key.columns] == ["id"]
    assert _characters().c.id.primary_key is True


def test_characters_archived_at_is_nullable__S009_001_DoD2() -> None:
    """009/001 DoD-2 — `archived_at` is nullable (NULL until archived)."""
    assert _characters().c.archived_at.nullable is True


@pytest.mark.parametrize("column", ["id", "user_id", "name", "sheet", "created_at", "updated_at"])
def test_characters_other_columns_are_not_nullable__S009_001_DoD2(column: str) -> None:
    """009/001 DoD-2 — every column but `archived_at` is NOT NULL."""
    assert _characters().c[column].nullable is False


@pytest.mark.parametrize("column", FORBIDDEN_CHARACTERS_COLUMNS)
def test_characters_declares_no_deferred_or_forbidden_column__S009_001_DoD2(column: str) -> None:
    """009/001 DoD-2 — D5/R1: model_ref, system_prompt and tools are 017's; the two language
    columns are never declared."""
    assert column not in _characters().c


# --- 009/001 DoD-3: the owner foreign key and the `user_id` index -----------------------


def test_characters_user_id_declares_a_foreign_key_to_users_id__S009_001_DoD3() -> None:
    """009/001 DoD-3 — `user_id` carries a declared foreign key targeting `users.id`."""
    targets = {fk.target_fullname for fk in _characters().c.user_id.foreign_keys}
    assert targets == {"users.id"}


def test_characters_declares_a_non_unique_index_on_user_id__S009_001_DoD3() -> None:
    """009/001 DoD-3 — an index covers exactly `user_id`, and it is not unique (D5)."""
    indexes = _single_column_indexes(_characters(), "user_id")
    assert indexes != []
    assert not any(index.unique for index in indexes)


# --- 009/001 DoD-4: `create_all` creates the table, and the FK is enforced ---------------


def test_create_all_creates_characters_and_enforces_the_user_fk__S009_001_DoD4(db_engine: Engine) -> None:
    """009/001 DoD-4 — `create_all` on a fresh engine creates `characters`; with foreign keys on,
    a row whose `user_id` names no `users` row is refused."""
    with db_engine.connect() as setup:
        schema.metadata.create_all(setup)
        setup.commit()

    with db_engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = ON")
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert "characters" in _created_table_names(connection)

        connection.execute(RAW_INSERT, _raw_row(id=1, username="owner"))
        connection.execute(RAW_CHARACTER_INSERT, _raw_character(id=10, user_id=1))
        connection.commit()
        assert connection.execute(text("SELECT COUNT(*) FROM characters")).scalar_one() == 1

        with pytest.raises(IntegrityError):
            connection.execute(RAW_CHARACTER_INSERT, _raw_character(id=11, user_id=999_999))


# ======================================================================================
# Feature 010, step 001 (`001.table-error-models.md`) — the `setups` table.
# Expected values come from that step's DoD-1..4 and DoD-8 and feature 010's context.md D7
# (eight columns, both bare FKs, one non-unique composite index) and R2 (no configuration
# columns, no default-setup flag). Tests are suffixed `__S010_001_DoD<n>`.
# ======================================================================================

# The registry as it stood before this step (003/001 + 005/001, 004/001, 006/001, 009/001).
PRE_010_TABLES = PRE_009_TABLES | NEW_009_TABLES
NEW_010_TABLES = {"setups"}
# 010/001 DoD-1, in 009/001 DoD-11's shape: features after 010 append their tables here, so
# this delta keeps meaning "010 added exactly `setups`" once a later feature declares one.
# 011/001 DoD-9 appended "sessions" — the first entry this set ever needed; 012/001 DoD-1
# appended "messages".
LATER_THAN_010_TABLES: set[str] = {"sessions", "messages"}

SETUPS_COLUMNS = {
    "id",
    "user_id",
    "character_id",
    "name",
    "description",
    "archived_at",
    "created_at",
    "updated_at",
}

# 010/001 DoD-2 — D7 / data-model.md `setups` / R1-R2: columns 010 must never declare.
FORBIDDEN_SETUPS_COLUMNS = (
    "model_ref",
    "system_prompt",
    "tools",
    "rp_language",
    "preferred_language",
    "is_default",
)

RAW_SETUP_INSERT = text(
    "INSERT INTO setups (id, user_id, character_id, name, description, archived_at, created_at, updated_at) "
    "VALUES (:id, :user_id, :character_id, :name, :description, :archived_at, :created_at, :updated_at)"
)


def _setups() -> Table:
    return schema.metadata.tables["setups"]


def _raw_setup(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": 20,
        "user_id": 1,
        "character_id": 10,
        "name": "Tavern",
        "description": "# Scene\n",
        "archived_at": None,
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
    }
    row.update(overrides)
    return row


def _indexes_over(table: Table, columns: list[str]) -> list[Any]:
    """Every index of `table` whose column list is exactly `columns`, in that order."""
    return [index for index in table.indexes if [c.name for c in index.columns] == columns]


def _seeded_setups_connection(db_engine: Engine) -> Connection:
    """A connection on a fresh file: whole registry created, foreign keys **on**, one owner
    (`id=1`) and one of their characters (`id=10`) committed, so a valid setup row has parents."""
    with db_engine.connect() as setup:
        schema.metadata.create_all(setup)
        setup.commit()

    connection = db_engine.connect()
    connection.exec_driver_sql("PRAGMA foreign_keys = ON")
    assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    connection.execute(RAW_INSERT, _raw_row(id=1, username="owner"))
    connection.execute(RAW_CHARACTER_INSERT, _raw_character(id=10, user_id=1))
    connection.commit()
    return connection


# --- 010/001 DoD-1: the registry gains `setups` and nothing else ------------------------


def test_registry_gains_exactly_the_setups_table__S010_001_DoD1() -> None:
    """010/001 DoD-1 — `setups` is registered, and it is the only table 010 declares."""
    assert "setups" in schema.metadata.tables
    assert isinstance(_setups(), Table)
    assert _setups().name == "setups"
    assert set(schema.metadata.tables) - PRE_010_TABLES - LATER_THAN_010_TABLES == NEW_010_TABLES


def test_registry_still_carries_every_pre_010_table__S010_001_DoD1() -> None:
    """010/001 DoD-1 — 010 only adds: every table declared before it is still registered."""
    assert PRE_010_TABLES <= set(schema.metadata.tables)


def test_the_010_delta_survives_a_table_a_later_feature_declares__S010_001_DoD1() -> None:
    """010/001 DoD-1 — the delta is later-table-proof: it reads "the registry, minus what
    pre-dated 010, minus what later features declared", so a future table named in the
    later-features set leaves it meaning "010 added exactly `setups`"."""
    future_table = "a_table_a_later_feature_declares"
    future_registry = set(schema.metadata.tables) | {future_table}
    future_later = LATER_THAN_010_TABLES | {future_table}

    assert future_registry - PRE_010_TABLES - future_later == NEW_010_TABLES


# --- 010/001 DoD-2: exactly eight columns, the primary key and nullability ---------------


def test_setups_has_exactly_the_eight_declared_columns__S010_001_DoD2() -> None:
    """010/001 DoD-2 — exactly id, user_id, character_id, name, description, archived_at,
    created_at, updated_at."""
    names = [column.name for column in _setups().columns]
    assert len(names) == len(set(names))
    assert set(names) == SETUPS_COLUMNS


def test_setups_id_is_the_primary_key__S010_001_DoD2() -> None:
    """010/001 DoD-2 — `id` alone is the primary key."""
    assert [column.name for column in _setups().primary_key.columns] == ["id"]
    assert _setups().c.id.primary_key is True


def test_setups_archived_at_is_nullable__S010_001_DoD2() -> None:
    """010/001 DoD-2 — `archived_at` is nullable (NULL until archived)."""
    assert _setups().c.archived_at.nullable is True


@pytest.mark.parametrize(
    "column", ["id", "user_id", "character_id", "name", "description", "created_at", "updated_at"]
)
def test_setups_other_columns_are_not_nullable__S010_001_DoD2(column: str) -> None:
    """010/001 DoD-2 — every column but `archived_at` is NOT NULL."""
    assert _setups().c[column].nullable is False


@pytest.mark.parametrize("column", FORBIDDEN_SETUPS_COLUMNS)
def test_setups_declares_no_configuration_or_default_column__S010_001_DoD2(column: str) -> None:
    """010/001 DoD-2 — D7/R2: no configuration override columns and no default-setup flag."""
    assert column not in _setups().c


# --- 010/001 DoD-3: the two foreign keys and the composite index -------------------------


def test_setups_user_id_declares_a_foreign_key_to_users_id__S010_001_DoD3() -> None:
    """010/001 DoD-3 — `user_id` carries a declared foreign key targeting `users.id`."""
    targets = {fk.target_fullname for fk in _setups().c.user_id.foreign_keys}
    assert targets == {"users.id"}


def test_setups_character_id_declares_a_foreign_key_to_characters_id__S010_001_DoD3() -> None:
    """010/001 DoD-3 — `character_id` carries a declared foreign key targeting `characters.id`."""
    targets = {fk.target_fullname for fk in _setups().c.character_id.foreign_keys}
    assert targets == {"characters.id"}


def test_setups_declares_a_non_unique_index_on_user_id_then_character_id__S010_001_DoD3() -> None:
    """010/001 DoD-3 — D7: one index whose columns are exactly `user_id`, `character_id` in
    that order, and it is not unique."""
    indexes = _indexes_over(_setups(), ["user_id", "character_id"])
    assert indexes != []
    assert not any(index.unique for index in indexes)


# --- 010/001 DoD-4: `create_all` creates the table, and both FKs are enforced ------------


def test_create_all_creates_setups_and_accepts_a_row_with_both_parents__S010_001_DoD4(
    db_engine: Engine,
) -> None:
    """010/001 DoD-4 — `create_all` on a fresh engine creates `setups`, and a row naming an
    existing user and an existing character is accepted."""
    with _seeded_setups_connection(db_engine) as connection:
        assert "setups" in _created_table_names(connection)

        connection.execute(RAW_SETUP_INSERT, _raw_setup(id=20, user_id=1, character_id=10))
        connection.commit()
        assert connection.execute(text("SELECT COUNT(*) FROM setups")).scalar_one() == 1


def test_setups_refuses_a_row_whose_character_id_names_no_character__S010_001_DoD4(
    db_engine: Engine,
) -> None:
    """010/001 DoD-4 — with foreign keys on, the `characters` FK is enforced."""
    with _seeded_setups_connection(db_engine) as connection:
        with pytest.raises(IntegrityError):
            connection.execute(RAW_SETUP_INSERT, _raw_setup(id=21, user_id=1, character_id=999_999))


def test_setups_refuses_a_row_whose_user_id_names_no_user__S010_001_DoD4(db_engine: Engine) -> None:
    """010/001 DoD-4 — with foreign keys on, the `users` FK is enforced too."""
    with _seeded_setups_connection(db_engine) as connection:
        with pytest.raises(IntegrityError):
            connection.execute(RAW_SETUP_INSERT, _raw_setup(id=22, user_id=999_999, character_id=10))


# --- 010/001 DoD-8: 006's and 009's deltas still mean what they meant --------------------


def test_the_006_delta_still_holds_with_setups_registered__S010_001_DoD8() -> None:
    """010/001 DoD-8 — 006's registry delta still means "006 added exactly `llm_servers` and
    `models`" now that `setups` exists."""
    assert PRE_006_TABLES <= set(schema.metadata.tables)
    assert set(schema.metadata.tables) - PRE_006_TABLES - LATER_THAN_006_TABLES == NEW_006_TABLES


def test_the_009_delta_still_holds_with_setups_registered__S010_001_DoD8() -> None:
    """010/001 DoD-8 — 009's registry delta still means "009 added exactly `characters`" now
    that `setups` exists."""
    assert PRE_009_TABLES <= set(schema.metadata.tables)
    assert set(schema.metadata.tables) - PRE_009_TABLES - LATER_THAN_009_TABLES == NEW_009_TABLES


# ======================================================================================
# Feature 011, step 001 (`001.table-errors-models.md`) — the `sessions` table.
# Expected values come from that step's DoD-1..4 and DoD-9 and feature 011's context.md D8
# (eight columns, three bare FKs, one non-unique composite index, no `ON DELETE`, no status
# column), D4 (no `title` / `partner_label`) and R2 (`setup_id` nullable, no server default,
# no sentinel). Tests are suffixed `__S011_001_DoD<n>`.
# ======================================================================================

# The registry as it stood before this step (003/001 + 005/001, 004/001, 006/001, 009/001,
# 010/001).
PRE_011_TABLES = PRE_010_TABLES | NEW_010_TABLES
NEW_011_TABLES = {"sessions"}
# 011/001 DoD-1, in 009/001 DoD-11's shape: features after 011 append their tables here, so
# this delta keeps meaning "011 added exactly `sessions`" once a later feature declares one.
# 012/001 DoD-1 appended "messages" — the first entry this set ever needed.
LATER_THAN_011_TABLES: set[str] = {"messages"}

SESSIONS_COLUMNS = {
    "id",
    "user_id",
    "character_id",
    "setup_id",
    "last_used_at",
    "archived_at",
    "created_at",
    "updated_at",
}

# 011/001 DoD-2 — D4 (title/partner_label deferred to the feature that labels a session),
# R4 (model capture deferred to 017) and data-model.md `sessions` (no status column).
FORBIDDEN_SESSIONS_COLUMNS = (
    "title",
    "partner_label",
    "rp_language",
    "preferred_language",
    "model_ref",
    "system_prompt",
    "tools",
    "status",
    "state",
)

# Named for the `sessions` table (not `RAW_SESSION_INSERT`): feature 004 already owns a
# module-level `RAW_SESSION_INSERT`/`_raw_session` pair for `auth_sessions`, and a same-named
# pair here would shadow it for the whole module.
RAW_SESSIONS_INSERT = text(
    "INSERT INTO sessions "
    "(id, user_id, character_id, setup_id, last_used_at, archived_at, created_at, updated_at) "
    "VALUES (:id, :user_id, :character_id, :setup_id, :last_used_at, :archived_at, :created_at, :updated_at)"
)


def _sessions() -> Table:
    return schema.metadata.tables["sessions"]


def _raw_sessions_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": 30,
        "user_id": 1,
        "character_id": 10,
        "setup_id": None,
        "last_used_at": TIMESTAMP,
        "archived_at": None,
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
    }
    row.update(overrides)
    return row


def _seeded_sessions_connection(db_engine: Engine) -> Connection:
    """A connection on a fresh file: whole registry created, foreign keys **on**, one owner
    (`id=1`), one of their characters (`id=10`) and one of their setups (`id=20`) committed, so
    a valid session row has every parent a row can name."""
    with db_engine.connect() as setup:
        schema.metadata.create_all(setup)
        setup.commit()

    connection = db_engine.connect()
    connection.exec_driver_sql("PRAGMA foreign_keys = ON")
    assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    connection.execute(RAW_INSERT, _raw_row(id=1, username="owner"))
    connection.execute(RAW_CHARACTER_INSERT, _raw_character(id=10, user_id=1))
    connection.execute(RAW_SETUP_INSERT, _raw_setup(id=20, user_id=1, character_id=10))
    connection.commit()
    return connection


# --- 011/001 DoD-1: the registry gains `sessions` and nothing else ----------------------


def test_registry_gains_exactly_the_sessions_table__S011_001_DoD1() -> None:
    """011/001 DoD-1 — `sessions` is registered, and it is the only table 011 declares."""
    assert "sessions" in schema.metadata.tables
    assert isinstance(_sessions(), Table)
    assert _sessions().name == "sessions"
    assert set(schema.metadata.tables) - PRE_011_TABLES - LATER_THAN_011_TABLES == NEW_011_TABLES


def test_registry_still_carries_every_pre_011_table__S011_001_DoD1() -> None:
    """011/001 DoD-1 — 011 only adds: every table declared before it is still registered."""
    assert PRE_011_TABLES <= set(schema.metadata.tables)


def test_the_011_delta_survives_a_table_a_later_feature_declares__S011_001_DoD1() -> None:
    """011/001 DoD-1 — the delta is later-table-proof: it reads "the registry, minus what
    pre-dated 011, minus what later features declared", so a future table named in the
    later-features set leaves it meaning "011 added exactly `sessions`"."""
    future_table = "a_table_a_later_feature_declares"
    future_registry = set(schema.metadata.tables) | {future_table}
    future_later = LATER_THAN_011_TABLES | {future_table}

    assert future_registry - PRE_011_TABLES - future_later == NEW_011_TABLES


# --- 011/001 DoD-2: exactly eight columns, the primary key and nullability ---------------


def test_sessions_has_exactly_the_eight_declared_columns__S011_001_DoD2() -> None:
    """011/001 DoD-2 — exactly id, user_id, character_id, setup_id, last_used_at, archived_at,
    created_at, updated_at."""
    names = [column.name for column in _sessions().columns]
    assert len(names) == len(set(names))
    assert set(names) == SESSIONS_COLUMNS


def test_sessions_id_is_the_primary_key__S011_001_DoD2() -> None:
    """011/001 DoD-2 — `id` alone is the primary key."""
    assert [column.name for column in _sessions().primary_key.columns] == ["id"]
    assert _sessions().c.id.primary_key is True


@pytest.mark.parametrize("column", ["setup_id", "archived_at"])
def test_sessions_setup_id_and_archived_at_are_nullable__S011_001_DoD2(column: str) -> None:
    """011/001 DoD-2 — R2: a session with no setup has `setup_id` NULL; a working session has
    `archived_at` NULL."""
    assert _sessions().c[column].nullable is True


@pytest.mark.parametrize(
    "column", ["id", "user_id", "character_id", "last_used_at", "created_at", "updated_at"]
)
def test_sessions_other_columns_are_not_nullable__S011_001_DoD2(column: str) -> None:
    """011/001 DoD-2 — every column but `setup_id` and `archived_at` is NOT NULL."""
    assert _sessions().c[column].nullable is False


@pytest.mark.parametrize("column", FORBIDDEN_SESSIONS_COLUMNS)
def test_sessions_declares_no_deferred_or_status_column__S011_001_DoD2(column: str) -> None:
    """011/001 DoD-2 — D8/D4/R4: the deferred columns are absent, and there is no status or
    state column at all."""
    assert column not in _sessions().c


# --- 011/001 DoD-3: the three foreign keys, no default, and the composite index -----------


def test_sessions_user_id_declares_a_foreign_key_to_users_id__S011_001_DoD3() -> None:
    """011/001 DoD-3 — `user_id` carries a declared foreign key targeting `users.id`."""
    targets = {fk.target_fullname for fk in _sessions().c.user_id.foreign_keys}
    assert targets == {"users.id"}


def test_sessions_character_id_declares_a_foreign_key_to_characters_id__S011_001_DoD3() -> None:
    """011/001 DoD-3 — `character_id` carries a declared foreign key targeting `characters.id`."""
    targets = {fk.target_fullname for fk in _sessions().c.character_id.foreign_keys}
    assert targets == {"characters.id"}


def test_sessions_setup_id_declares_a_foreign_key_to_setups_id__S011_001_DoD3() -> None:
    """011/001 DoD-3 — `setup_id` carries a declared foreign key targeting `setups.id`."""
    targets = {fk.target_fullname for fk in _sessions().c.setup_id.foreign_keys}
    assert targets == {"setups.id"}


def test_sessions_setup_id_declares_no_server_default__S011_001_DoD3() -> None:
    """011/001 DoD-3 — R2: "no default, no sentinel" is a column property here, not only a
    service habit."""
    assert _sessions().c.setup_id.server_default is None
    assert _sessions().c.setup_id.default is None


def test_sessions_declares_exactly_one_non_unique_composite_index__S011_001_DoD3() -> None:
    """011/001 DoD-3 — D8: exactly one index, whose columns are `user_id`, `character_id` in
    that order, and it is not unique."""
    assert len(_sessions().indexes) == 1
    indexes = _indexes_over(_sessions(), ["user_id", "character_id"])
    assert len(indexes) == 1
    assert not any(index.unique for index in indexes)


# --- 011/001 DoD-4: `create_all` creates the table, and all three FKs are enforced --------


def test_create_all_creates_sessions_and_accepts_a_row_with_no_setup__S011_001_DoD4(
    db_engine: Engine,
) -> None:
    """011/001 DoD-4 — `create_all` on a fresh engine creates `sessions`, and R2's session with
    no setup (`setup_id` NULL) inserts."""
    with _seeded_sessions_connection(db_engine) as connection:
        assert "sessions" in _created_table_names(connection)

        connection.execute(RAW_SESSIONS_INSERT, _raw_sessions_row(id=30, user_id=1, character_id=10, setup_id=None))
        connection.commit()
        assert connection.execute(text("SELECT COUNT(*) FROM sessions")).scalar_one() == 1
        assert connection.execute(text("SELECT setup_id FROM sessions WHERE id = 30")).scalar_one() is None


def test_sessions_accepts_a_row_naming_an_existing_setup__S011_001_DoD4(db_engine: Engine) -> None:
    """011/001 DoD-4 — a row whose `setup_id` names an existing setup is accepted, so the
    nullable FK is a real reference and not merely an unconstrained column."""
    with _seeded_sessions_connection(db_engine) as connection:
        connection.execute(RAW_SESSIONS_INSERT, _raw_sessions_row(id=31, user_id=1, character_id=10, setup_id=20))
        connection.commit()
        assert connection.execute(text("SELECT setup_id FROM sessions WHERE id = 31")).scalar_one() == 20


def test_sessions_refuses_a_row_whose_character_id_names_no_character__S011_001_DoD4(
    db_engine: Engine,
) -> None:
    """011/001 DoD-4 — with foreign keys on, the `characters` FK is enforced."""
    with _seeded_sessions_connection(db_engine) as connection:
        with pytest.raises(IntegrityError):
            connection.execute(
                RAW_SESSIONS_INSERT, _raw_sessions_row(id=32, user_id=1, character_id=999_999, setup_id=None)
            )


def test_sessions_refuses_a_row_whose_setup_id_names_no_setup__S011_001_DoD4(db_engine: Engine) -> None:
    """011/001 DoD-4 — with foreign keys on, the `setups` FK is enforced for a non-NULL value."""
    with _seeded_sessions_connection(db_engine) as connection:
        with pytest.raises(IntegrityError):
            connection.execute(
                RAW_SESSIONS_INSERT, _raw_sessions_row(id=33, user_id=1, character_id=10, setup_id=999_999)
            )


def test_sessions_refuses_a_row_whose_user_id_names_no_user__S011_001_DoD4(db_engine: Engine) -> None:
    """011/001 DoD-4 — with foreign keys on, the `users` FK is enforced too."""
    with _seeded_sessions_connection(db_engine) as connection:
        with pytest.raises(IntegrityError):
            connection.execute(
                RAW_SESSIONS_INSERT, _raw_sessions_row(id=34, user_id=999_999, character_id=10, setup_id=None)
            )


# --- 011/001 DoD-9: 006's, 009's and 010's deltas still mean what they meant --------------


def test_the_006_delta_still_holds_with_sessions_registered__S011_001_DoD9() -> None:
    """011/001 DoD-9 — 006's registry delta still means "006 added exactly `llm_servers` and
    `models`" now that `sessions` exists."""
    assert PRE_006_TABLES <= set(schema.metadata.tables)
    assert set(schema.metadata.tables) - PRE_006_TABLES - LATER_THAN_006_TABLES == NEW_006_TABLES


def test_the_009_delta_still_holds_with_sessions_registered__S011_001_DoD9() -> None:
    """011/001 DoD-9 — 009's registry delta still means "009 added exactly `characters`" now
    that `sessions` exists."""
    assert PRE_009_TABLES <= set(schema.metadata.tables)
    assert set(schema.metadata.tables) - PRE_009_TABLES - LATER_THAN_009_TABLES == NEW_009_TABLES


def test_the_010_delta_still_holds_with_sessions_registered__S011_001_DoD9() -> None:
    """011/001 DoD-9 — 010's registry delta still means "010 added exactly `setups`" now that
    `sessions` exists."""
    assert PRE_010_TABLES <= set(schema.metadata.tables)
    assert set(schema.metadata.tables) - PRE_010_TABLES - LATER_THAN_010_TABLES == NEW_010_TABLES


def test_every_earlier_later_features_set_now_names_sessions__S011_001_DoD9() -> None:
    """011/001 DoD-9 — the later-table-proof shape is kept by *adding* to each earlier delta's
    later-features set rather than by rewriting its assertion."""
    assert "sessions" in LATER_THAN_006_TABLES
    assert "sessions" in LATER_THAN_009_TABLES
    assert "sessions" in LATER_THAN_010_TABLES
    assert "sessions" not in PRE_011_TABLES


# ======================================================================================
# Feature 012, step 001 (`001.table-selectables-errors-models.md`) — the `messages` table and
# its three named read selectables. Expected values come from that step's DoD-1..6 and
# feature 012's context.md "The `messages` table" (twelve columns, three bare FKs including
# the self-reference, one named CHECK, two non-unique indexes, no `ON DELETE`), D1 (the
# selectables are Core `select()`s, not SQL views) and D7 (`message_states` projects only
# the five state columns). Tests are suffixed `__S012_001_DoD<n>`.
# ======================================================================================

# The registry as it stood before this step (003/001 + 005/001, 004/001, 006/001, 009/001,
# 010/001, 011/001).
PRE_012_TABLES = PRE_011_TABLES | NEW_011_TABLES
NEW_012_TABLES = {"messages"}
# 012/001 DoD-1, in 009/001 DoD-11's shape: features after 012 append their tables here, so
# this delta keeps meaning "012 added exactly `messages`" once a later feature declares one.
LATER_THAN_012_TABLES: set[str] = set()

MESSAGES_COLUMNS = {
    "id",
    "user_id",
    "session_id",
    "role",
    "kind",
    "text",
    "related_to",
    "settled_at",
    "tool_name",
    "tool_payload",
    "created_at",
    "updated_at",
}
MESSAGES_NULLABLE_COLUMNS = ("kind", "related_to", "settled_at", "tool_name", "tool_payload")
MESSAGES_NOT_NULL_COLUMNS = ("id", "user_id", "session_id", "role", "text", "created_at", "updated_at")

# 012/001 DoD-2 — data-model.md: `ORDER BY id` is stream order (no position), no discussion
# table, no per-message language, and the four states are column predicates (no status).
FORBIDDEN_MESSAGES_COLUMNS = ("position", "discussion_id", "language", "status")

# D7: `message_states` can classify a row's state but carries no content.
MESSAGE_STATES_COLUMNS = {"id", "user_id", "session_id", "related_to", "settled_at"}

SELECTABLE_NAMES = ("settled_entries", "current_zone", "message_states")

SETTLED_AT = "2026-09-30T08:15:30.123456+00:00"

RAW_MESSAGES_INSERT = text(
    "INSERT INTO messages "
    "(id, user_id, session_id, role, kind, text, related_to, settled_at, tool_name, tool_payload, "
    "created_at, updated_at) "
    "VALUES (:id, :user_id, :session_id, :role, :kind, :text, :related_to, :settled_at, :tool_name, "
    ":tool_payload, :created_at, :updated_at)"
)


def _messages() -> Table:
    return schema.metadata.tables["messages"]


def _raw_message(**overrides: Any) -> dict[str, Any]:
    """A current-zone row (NULL/NULL) by default, owned by user 1 in session 30."""
    row: dict[str, Any] = {
        "id": 100,
        "user_id": 1,
        "session_id": 30,
        "role": "user",
        "kind": None,
        "text": "She leans on the rail.",
        "related_to": None,
        "settled_at": None,
        "tool_name": None,
        "tool_payload": None,
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
    }
    row.update(overrides)
    return row


def _seeded_messages_connection(db_engine: Engine) -> Connection:
    """A connection on a fresh file: whole registry created, foreign keys **on**, one owner
    (`id=1`), one of their characters (`id=10`) and one of their sessions (`id=30`, no setup)
    committed, so a valid `messages` row has every parent it can name (001.context.md
    "Test seeding")."""
    with db_engine.connect() as setup:
        schema.metadata.create_all(setup)
        setup.commit()

    connection = db_engine.connect()
    connection.exec_driver_sql("PRAGMA foreign_keys = ON")
    assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    connection.execute(RAW_INSERT, _raw_row(id=1, username="owner"))
    connection.execute(RAW_CHARACTER_INSERT, _raw_character(id=10, user_id=1))
    connection.execute(RAW_SESSIONS_INSERT, _raw_sessions_row(id=30, user_id=1, character_id=10, setup_id=None))
    connection.commit()
    return connection


def _message_ids(connection: Connection) -> set[int]:
    return {row[0] for row in connection.execute(text("SELECT id FROM messages")).all()}


# --- 012/001 DoD-1: the registry gains `messages` and nothing else ----------------------


def test_registry_gains_exactly_the_messages_table__S012_001_DoD1() -> None:
    """012/001 DoD-1 — `messages` is registered, and it is the only table 012 declares."""
    assert "messages" in schema.metadata.tables
    assert isinstance(_messages(), Table)
    assert _messages().name == "messages"
    assert set(schema.metadata.tables) - PRE_012_TABLES - LATER_THAN_012_TABLES == NEW_012_TABLES


def test_registry_still_carries_every_pre_012_table__S012_001_DoD1() -> None:
    """012/001 DoD-1 — 012 only adds: every table declared before it is still registered."""
    assert PRE_012_TABLES <= set(schema.metadata.tables)


def test_the_012_delta_survives_a_table_a_later_feature_declares__S012_001_DoD1() -> None:
    """012/001 DoD-1 — the delta is later-table-proof: a future table named in the
    later-features set leaves it meaning "012 added exactly `messages`"."""
    future_table = "a_table_a_later_feature_declares"
    future_registry = set(schema.metadata.tables) | {future_table}
    future_later = LATER_THAN_012_TABLES | {future_table}

    assert future_registry - PRE_012_TABLES - future_later == NEW_012_TABLES


def test_the_006_delta_still_holds_with_messages_registered__S012_001_DoD1() -> None:
    """012/001 DoD-1 — 006's delta still means "006 added exactly `llm_servers` and `models`"."""
    assert PRE_006_TABLES <= set(schema.metadata.tables)
    assert set(schema.metadata.tables) - PRE_006_TABLES - LATER_THAN_006_TABLES == NEW_006_TABLES


def test_the_009_delta_still_holds_with_messages_registered__S012_001_DoD1() -> None:
    """012/001 DoD-1 — 009's delta still means "009 added exactly `characters`"."""
    assert PRE_009_TABLES <= set(schema.metadata.tables)
    assert set(schema.metadata.tables) - PRE_009_TABLES - LATER_THAN_009_TABLES == NEW_009_TABLES


def test_the_010_delta_still_holds_with_messages_registered__S012_001_DoD1() -> None:
    """012/001 DoD-1 — 010's delta still means "010 added exactly `setups`"."""
    assert PRE_010_TABLES <= set(schema.metadata.tables)
    assert set(schema.metadata.tables) - PRE_010_TABLES - LATER_THAN_010_TABLES == NEW_010_TABLES


def test_the_011_delta_still_holds_with_messages_registered__S012_001_DoD1() -> None:
    """012/001 DoD-1 — 011's delta still means "011 added exactly `sessions`"."""
    assert PRE_011_TABLES <= set(schema.metadata.tables)
    assert set(schema.metadata.tables) - PRE_011_TABLES - LATER_THAN_011_TABLES == NEW_011_TABLES


def test_every_earlier_later_features_set_now_names_messages__S012_001_DoD1() -> None:
    """012/001 DoD-1 — the later-table-proof shape is kept by *adding* `messages` to each
    earlier delta's later-features set rather than by rewriting its assertion."""
    assert "messages" in LATER_THAN_006_TABLES
    assert "messages" in LATER_THAN_009_TABLES
    assert "messages" in LATER_THAN_010_TABLES
    assert "messages" in LATER_THAN_011_TABLES
    assert "messages" not in PRE_012_TABLES


# --- 012/001 DoD-2: exactly twelve columns, the primary key and nullability ---------------


def test_messages_has_exactly_the_twelve_declared_columns__S012_001_DoD2() -> None:
    """012/001 DoD-2 — exactly id, user_id, session_id, role, kind, text, related_to,
    settled_at, tool_name, tool_payload, created_at, updated_at."""
    names = [column.name for column in _messages().columns]
    assert len(names) == len(set(names))
    assert set(names) == MESSAGES_COLUMNS


def test_messages_id_is_the_primary_key__S012_001_DoD2() -> None:
    """012/001 DoD-2 — `id` alone is the primary key."""
    assert [column.name for column in _messages().primary_key.columns] == ["id"]
    assert _messages().c.id.primary_key is True


@pytest.mark.parametrize("column", MESSAGES_NULLABLE_COLUMNS)
def test_messages_state_kind_and_tool_columns_are_nullable__S012_001_DoD2(column: str) -> None:
    """012/001 DoD-2 — `kind`, `related_to`, `settled_at`, `tool_name`, `tool_payload` are
    nullable."""
    assert _messages().c[column].nullable is True


@pytest.mark.parametrize("column", MESSAGES_NOT_NULL_COLUMNS)
def test_messages_other_columns_are_not_nullable__S012_001_DoD2(column: str) -> None:
    """012/001 DoD-2 — every other column is NOT NULL."""
    assert _messages().c[column].nullable is False


@pytest.mark.parametrize("column", FORBIDDEN_MESSAGES_COLUMNS)
def test_messages_declares_no_position_discussion_language_or_status_column__S012_001_DoD2(
    column: str,
) -> None:
    """012/001 DoD-2 — there is no `position`, `discussion_id`, `language` or `status` column."""
    assert column not in _messages().c


# --- 012/001 DoD-3: the three bare foreign keys and the two indexes -----------------------


def test_messages_user_id_declares_a_foreign_key_to_users_id__S012_001_DoD3() -> None:
    """012/001 DoD-3 — `user_id` carries a declared foreign key targeting `users.id`."""
    targets = {fk.target_fullname for fk in _messages().c.user_id.foreign_keys}
    assert targets == {"users.id"}


def test_messages_session_id_declares_a_foreign_key_to_sessions_id__S012_001_DoD3() -> None:
    """012/001 DoD-3 — `session_id` carries a declared foreign key targeting `sessions.id`."""
    targets = {fk.target_fullname for fk in _messages().c.session_id.foreign_keys}
    assert targets == {"sessions.id"}


def test_messages_related_to_declares_a_self_foreign_key_to_messages_id__S012_001_DoD3() -> None:
    """012/001 DoD-3 — `related_to` carries a declared foreign key targeting `messages.id`."""
    targets = {fk.target_fullname for fk in _messages().c.related_to.foreign_keys}
    assert targets == {"messages.id"}


def test_messages_declares_exactly_the_three_foreign_keys__S012_001_DoD3() -> None:
    """012/001 DoD-3 — the table's foreign keys are those three and no other."""
    pairs = {(fk.parent.name, fk.target_fullname) for fk in _messages().foreign_keys}
    assert pairs == {("user_id", "users.id"), ("session_id", "sessions.id"), ("related_to", "messages.id")}


def test_messages_foreign_keys_declare_no_on_delete_action__S012_001_DoD3() -> None:
    """012/001 DoD-3 — the archive rule: no foreign key declares an `ON DELETE` action."""
    assert _messages().foreign_keys
    for fk in _messages().foreign_keys:
        assert fk.ondelete is None, f"{fk.parent.name} declares ON DELETE {fk.ondelete}"


def test_messages_declares_exactly_two_indexes__S012_001_DoD3() -> None:
    """012/001 DoD-3 — the table declares exactly two indexes, and neither is unique."""
    assert len(_messages().indexes) == 2
    assert not any(index.unique for index in _messages().indexes)


def test_messages_declares_a_non_unique_index_on_session_id_then_settled_at__S012_001_DoD3() -> None:
    """012/001 DoD-3 — one non-unique index whose columns are `session_id`, `settled_at` in
    that order."""
    indexes = _indexes_over(_messages(), ["session_id", "settled_at"])
    assert len(indexes) == 1
    assert not indexes[0].unique


def test_messages_declares_a_non_unique_index_on_related_to__S012_001_DoD3() -> None:
    """012/001 DoD-3 — one non-unique index on `related_to` alone."""
    indexes = _indexes_over(_messages(), ["related_to"])
    assert len(indexes) == 1
    assert not indexes[0].unique


# --- 012/001 DoD-4: the CHECK and the foreign keys hold in a real database ----------------


def test_create_all_creates_messages_and_accepts_a_settled_row__S012_001_DoD4(db_engine: Engine) -> None:
    """012/001 DoD-4 — `related_to` NULL and `settled_at` set (the record state) inserts."""
    with _seeded_messages_connection(db_engine) as connection:
        assert "messages" in _created_table_names(connection)

        connection.execute(
            RAW_MESSAGES_INSERT, _raw_message(id=100, kind="turn", related_to=None, settled_at=SETTLED_AT)
        )
        connection.commit()
        assert _message_ids(connection) == {100}


def test_messages_accepts_a_buried_row_under_an_existing_message__S012_001_DoD4(db_engine: Engine) -> None:
    """012/001 DoD-4 — `related_to` naming an existing message and `settled_at` NULL (the
    buried state) inserts."""
    with _seeded_messages_connection(db_engine) as connection:
        connection.execute(
            RAW_MESSAGES_INSERT, _raw_message(id=100, kind="turn", related_to=None, settled_at=SETTLED_AT)
        )
        connection.execute(RAW_MESSAGES_INSERT, _raw_message(id=101, related_to=100, settled_at=None))
        connection.commit()
        assert _message_ids(connection) == {100, 101}
        assert connection.execute(text("SELECT related_to FROM messages WHERE id = 101")).scalar_one() == 100


def test_messages_refuses_a_row_both_buried_and_settled__S012_001_DoD4(db_engine: Engine) -> None:
    """012/001 DoD-4 — the CHECK: a row with **both** `related_to` and `settled_at` set is
    rejected by the database."""
    with _seeded_messages_connection(db_engine) as connection:
        connection.execute(
            RAW_MESSAGES_INSERT, _raw_message(id=100, kind="turn", related_to=None, settled_at=SETTLED_AT)
        )
        connection.commit()
        with pytest.raises(IntegrityError):
            connection.execute(
                RAW_MESSAGES_INSERT, _raw_message(id=101, kind="turn", related_to=100, settled_at=SETTLED_AT)
            )


def test_messages_refuses_a_row_whose_session_id_names_no_session__S012_001_DoD4(db_engine: Engine) -> None:
    """012/001 DoD-4 — with foreign keys on, the `sessions` FK is enforced."""
    with _seeded_messages_connection(db_engine) as connection:
        with pytest.raises(IntegrityError):
            connection.execute(RAW_MESSAGES_INSERT, _raw_message(id=102, session_id=999_999))


def test_messages_refuses_a_row_whose_related_to_names_no_message__S012_001_DoD4(db_engine: Engine) -> None:
    """012/001 DoD-4 — with foreign keys on, the self-referencing `related_to` FK is enforced."""
    with _seeded_messages_connection(db_engine) as connection:
        with pytest.raises(IntegrityError):
            connection.execute(RAW_MESSAGES_INSERT, _raw_message(id=103, related_to=999_999, settled_at=None))


def test_messages_accepts_an_assistant_row_with_no_kind__S012_001_DoD4(db_engine: Engine) -> None:
    """012/001 DoD-4 — no DB CHECK on `role` / `kind`: `role` 'assistant' with `kind` NULL
    inserts."""
    with _seeded_messages_connection(db_engine) as connection:
        connection.execute(RAW_MESSAGES_INSERT, _raw_message(id=104, role="assistant", kind=None))
        connection.commit()
        row = connection.execute(text("SELECT role, kind FROM messages WHERE id = 104")).one()
        assert row[0] == "assistant"
        assert row[1] is None


# --- 012/001 DoD-5: the three selectables split the four states ---------------------------

ZONE_ID = 200
SETTLED_ID = 201
BURIED_ID = 202


def _three_state_connection(db_engine: Engine) -> Connection:
    """One session (30) holding a zone row (NULL/NULL), a settled row (NULL/set) and a buried
    row (set/NULL) whose `related_to` is the settled row."""
    connection = _seeded_messages_connection(db_engine)
    connection.execute(RAW_MESSAGES_INSERT, _raw_message(id=ZONE_ID, related_to=None, settled_at=None))
    connection.execute(
        RAW_MESSAGES_INSERT,
        _raw_message(id=SETTLED_ID, kind="turn", related_to=None, settled_at=SETTLED_AT),
    )
    connection.execute(RAW_MESSAGES_INSERT, _raw_message(id=BURIED_ID, related_to=SETTLED_ID, settled_at=None))
    connection.commit()
    return connection


def test_settled_entries_returns_exactly_the_settled_row__S012_001_DoD5(db_engine: Engine) -> None:
    """012/001 DoD-5 — `settled_entries` returns the settled row and neither the zone nor the
    buried row."""
    with _three_state_connection(db_engine) as connection:
        rows = connection.execute(schema.settled_entries).all()
        assert [row._mapping["id"] for row in rows] == [SETTLED_ID]


def test_current_zone_returns_exactly_the_zone_row__S012_001_DoD5(db_engine: Engine) -> None:
    """012/001 DoD-5 — `current_zone` returns the zone row and neither the settled nor the
    buried row."""
    with _three_state_connection(db_engine) as connection:
        rows = connection.execute(schema.current_zone).all()
        assert [row._mapping["id"] for row in rows] == [ZONE_ID]


def test_message_states_returns_all_three_rows__S012_001_DoD5(db_engine: Engine) -> None:
    """012/001 DoD-5 — `message_states` has no filter: zone, settled and buried rows all come
    back."""
    with _three_state_connection(db_engine) as connection:
        rows = connection.execute(schema.message_states).all()
        ids = [row._mapping["id"] for row in rows]
        assert len(ids) == 3
        assert set(ids) == {ZONE_ID, SETTLED_ID, BURIED_ID}


@pytest.mark.parametrize("name", ["settled_entries", "current_zone"])
def test_settled_entries_and_current_zone_return_every_messages_column__S012_001_DoD5(
    db_engine: Engine, name: str
) -> None:
    """012/001 DoD-5 — the two reading selectables return every `messages` column, under the
    table's own column names."""
    with _three_state_connection(db_engine) as connection:
        result = connection.execute(getattr(schema, name))
        keys = list(result.keys())
        result.close()
        assert len(keys) == len(set(keys))
        assert set(keys) == MESSAGES_COLUMNS
        assert set(keys) == {column.name for column in _messages().columns}


def test_message_states_returns_only_the_five_state_columns__S012_001_DoD5(db_engine: Engine) -> None:
    """012/001 DoD-5 — D7: `message_states` projects exactly `id`, `user_id`, `session_id`,
    `related_to`, `settled_at` — no `text`, no `kind`."""
    with _three_state_connection(db_engine) as connection:
        result = connection.execute(schema.message_states)
        keys = list(result.keys())
        result.close()
        assert len(keys) == len(set(keys))
        assert set(keys) == MESSAGE_STATES_COLUMNS
        assert "text" not in keys
        assert "kind" not in keys


def test_settled_entries_returns_the_settled_rows_values__S012_001_DoD5(db_engine: Engine) -> None:
    """012/001 DoD-5 — the settled row comes back as stored (state and content columns)."""
    with _three_state_connection(db_engine) as connection:
        row = connection.execute(schema.settled_entries).one()._mapping
        assert row["id"] == SETTLED_ID
        assert row["session_id"] == 30
        assert row["kind"] == "turn"
        assert row["related_to"] is None
        assert row["settled_at"] == SETTLED_AT


# --- 012/001 DoD-6: the selectables are not views and not tables --------------------------


@pytest.mark.parametrize("name", SELECTABLE_NAMES)
def test_each_selectable_is_a_module_level_core_select__S012_001_DoD6(name: str) -> None:
    """012/001 DoD-6 — D1: each name is a module-level Core `select()`, not a `Table`."""
    value = getattr(schema, name)
    assert isinstance(value, Select)
    assert not isinstance(value, Table)


@pytest.mark.parametrize("name", SELECTABLE_NAMES)
def test_no_selectable_name_is_a_registry_table__S012_001_DoD6(name: str) -> None:
    """012/001 DoD-6 — none of the three selectable names is a key of `metadata.tables`."""
    assert name not in schema.metadata.tables


def test_create_all_creates_no_sql_view__S012_001_DoD6(db_engine: Engine) -> None:
    """012/001 DoD-6 — D1: after `create_all`, `sqlite_master` holds no row of type `view`."""
    with db_engine.connect() as connection:
        schema.metadata.create_all(connection)
        connection.commit()
        views = connection.execute(text("SELECT name FROM sqlite_master WHERE type = 'view'")).all()
        assert views == []
        names = {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master")).all()}
        for name in SELECTABLE_NAMES:
            assert name not in names
