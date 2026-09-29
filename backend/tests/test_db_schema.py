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
