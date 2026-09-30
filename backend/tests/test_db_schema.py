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
from sqlalchemy import BigInteger, Boolean, Connection, Engine, MetaData, String, Table, UniqueConstraint, text
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
    """006/001 DoD-5 — beside the tables that pre-date this step, only the two new ones exist."""
    assert set(schema.metadata.tables) - PRE_006_TABLES == NEW_006_TABLES


def test_create_all_on_a_fresh_file_database_creates_both_tables__S006_001_DoD5(
    llm_connection: Connection,
) -> None:
    """006/001 DoD-5 — `create_all` against a fresh file creates both, and no other new table."""
    created = _created_table_names(llm_connection)
    assert NEW_006_TABLES <= created
    assert created - PRE_006_TABLES == NEW_006_TABLES


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
