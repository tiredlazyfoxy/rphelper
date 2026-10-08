"""Tests for ``app.services.users`` — list, create, disable, enable, set password, set role.

Every expected value comes from
``docs/plans/005.admin-shell-and-users/002.users-service-and-errors.md`` (Interface intent +
Definition of done), ``002.context.md`` and the feature ``context.md`` (D3, D4, D6, R5, the
routers-versus-services rule). Bindings come from ``## Skeleton`` -> ``Step 002`` (and
``Step 001`` for the bulk revoke helper) in feature 005's ``status.md``.

Covers step 002 DoD-2 .. DoD-19. DoD-1 lives in ``test_errors.py``; DoD-20..22 are
``[manual/live]``.

Connection hygiene: every write operation opens its own ``with conn.begin():`` block, so
every operation here is called on a *fresh* connection, every setup write is committed,
and every post-condition is read on another fresh connection.
"""

import ast
import dataclasses
import inspect
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, Table, func, select, text
from sqlalchemy.exc import DBAPIError

from app.db import schema
from app.errors import (
    InvalidCredentialsError,
    SelfRoleChangeRefusedError,
    UsernameTakenError,
    UserNotFoundError,
)
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services import users as users_module
from app.services.auth import authenticate, open_session, resolve_session
from app.services.passwords import hash_password, verify_password
from app.services.users import (
    UserAccount,
    create_user,
    disable_user,
    enable_user,
    list_users,
    set_user_password,
    set_user_role,
)

TIMESTAMP = "2026-01-01T00:00:00+00:00"
KNOWN_LAST_LOGIN_TEXT = "2026-03-04T05:06:07.123456+00:00"
KNOWN_LAST_LOGIN = datetime(2026, 3, 4, 5, 6, 7, 123456, tzinfo=UTC)

# Ids chosen so that id order differs from username (alphabetical) order.
ADMIN_ID = 7_000_001
ADMIN_NAME = "founder"
ADMIN_PASSWORD = "correct horse battery staple"

PLAYER_ID = 7_000_002
PLAYER_NAME = "wanderer"
PLAYER_PASSWORD = "a quiet river at dusk"

DISABLED_ID = 7_000_003
DISABLED_NAME = "sleeper"
DISABLED_PASSWORD = "dormant but correct"

SECOND_ADMIN_ID = 7_000_004
SECOND_ADMIN_NAME = "custodian"
SECOND_ADMIN_PASSWORD = "keeper of the keys"

SEEDED_IDS_IN_ID_ORDER = [ADMIN_ID, PLAYER_ID, DISABLED_ID, SECOND_ADMIN_ID]

UNKNOWN_USER_ID = 9_999_999_999
TTL_HOURS = 720

EXPECTED_ACCOUNT_FIELDS = {"id", "username", "role", "is_enabled", "last_login_at"}


class _FixedIdGenerator:
    """A generator stand-in whose ``next_id()`` always answers one known value."""

    def __init__(self, value: int) -> None:
        self.value = value
        self.calls = 0

    def next_id(self) -> int:
        self.calls += 1
        return self.value


def _users() -> Table:
    return schema.metadata.tables["users"]


def _sessions() -> Table:
    return schema.metadata.tables["auth_sessions"]


# --- setup helpers (all committed, never left with an open transaction) --------------


def _insert_user(
    engine: Engine,
    *,
    user_id: int,
    username: str,
    password: str,
    role: Role,
    enabled: bool = True,
    last_login_at: str | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            _users().insert().values(
                id=user_id,
                username=username,
                password_hash=hash_password(password),
                role=role,
                is_enabled=enabled,
                rp_language=None,
                preferred_language=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
                last_login_at=last_login_at,
            )
        )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database with the registry applied and four accounts seeded.

    Inserted out of id order on purpose; ``wanderer`` carries a known ``last_login_at``.
    """
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(
        db_engine,
        user_id=DISABLED_ID,
        username=DISABLED_NAME,
        password=DISABLED_PASSWORD,
        role=Role.ROLEPLAYER,
        enabled=False,
    )
    _insert_user(
        db_engine,
        user_id=SECOND_ADMIN_ID,
        username=SECOND_ADMIN_NAME,
        password=SECOND_ADMIN_PASSWORD,
        role=Role.ADMIN,
    )
    _insert_user(db_engine, user_id=ADMIN_ID, username=ADMIN_NAME, password=ADMIN_PASSWORD, role=Role.ADMIN)
    _insert_user(
        db_engine,
        user_id=PLAYER_ID,
        username=PLAYER_NAME,
        password=PLAYER_PASSWORD,
        role=Role.ROLEPLAYER,
        last_login_at=KNOWN_LAST_LOGIN_TEXT,
    )
    return db_engine


# --- call helpers: one fresh connection per operation -------------------------------


def _list(engine: Engine) -> list[UserAccount]:
    with engine.connect() as connection:
        return list_users(connection)


def _create(engine: Engine, generator: Any, username: str, password: str, role: Role) -> UserAccount:
    with engine.connect() as connection:
        return create_user(connection, generator, username, password, role)


def _disable(engine: Engine, user_id: int) -> UserAccount:
    with engine.connect() as connection:
        return disable_user(connection, user_id)


def _enable(engine: Engine, user_id: int) -> UserAccount:
    with engine.connect() as connection:
        return enable_user(connection, user_id)


def _set_password(engine: Engine, user_id: int, password: str) -> UserAccount:
    with engine.connect() as connection:
        return set_user_password(connection, user_id, password)


def _set_role(engine: Engine, user_id: int, role: Role, acting_user_id: int) -> UserAccount:
    with engine.connect() as connection:
        return set_user_role(connection, user_id, role, acting_user_id)


def _open(engine: Engine, user_id: int) -> str:
    with engine.connect() as connection:
        return open_session(connection, SnowflakeGenerator(node_id=1), user_id, TTL_HOURS).token


def _resolves(engine: Engine, token: str) -> bool:
    with engine.connect() as connection:
        return resolve_session(connection, token) is not None


# --- read helpers ---------------------------------------------------------------------


def _user_row(engine: Engine, user_id: int) -> dict[str, Any]:
    with engine.connect() as connection:
        return dict(connection.execute(select(_users()).where(_users().c.id == user_id)).mappings().one())


def _all_user_rows(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(select(_users()).order_by(_users().c.id)).mappings()]


def _user_count(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(_users())).scalar_one())


def _session_rows(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        return [
            dict(row) for row in connection.execute(select(_sessions()).order_by(_sessions().c.id)).mappings()
        ]


def _sessions_of(engine: Engine, user_id: int) -> list[dict[str, Any]]:
    return [row for row in _session_rows(engine) if row["user_id"] == user_id]


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _assert_current_instant(value: Any, before: datetime, after: datetime) -> None:
    assert isinstance(value, str)
    instant = _parse_utc(value)
    assert instant.utcoffset() == timedelta(0)
    assert before - timedelta(seconds=1) <= instant <= after + timedelta(seconds=1)


def _without(row: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in keys}


# ===================================================================================
# DoD-2 — listing returns id, username, role, enabled flag and last_login_at, nothing else
# ===================================================================================


def test_account_result_carries_exactly_the_five_listed_fields__DoD2() -> None:
    """DoD-2 — the one result shape is id, username, role, enabled flag, last_login_at (US-011.AC-1)."""
    names = {field.name for field in dataclasses.fields(UserAccount)}
    assert names == EXPECTED_ACCOUNT_FIELDS


def test_listing_returns_every_seeded_accounts_values__DoD2(engine: Engine) -> None:
    """DoD-2 — each listed account reports its own id, username, role and enabled flag (US-011.AC-1)."""
    accounts = {account.id: account for account in _list(engine)}
    assert set(accounts) == set(SEEDED_IDS_IN_ID_ORDER)
    assert all(isinstance(account, UserAccount) for account in accounts.values())
    expected = {
        ADMIN_ID: (ADMIN_NAME, Role.ADMIN, True),
        PLAYER_ID: (PLAYER_NAME, Role.ROLEPLAYER, True),
        DISABLED_ID: (DISABLED_NAME, Role.ROLEPLAYER, False),
        SECOND_ADMIN_ID: (SECOND_ADMIN_NAME, Role.ADMIN, True),
    }
    for user_id, (username, role, enabled) in expected.items():
        account = accounts[user_id]
        assert account.username == username
        assert account.role == role
        assert account.is_enabled is enabled


def test_listing_reports_last_login_at_as_the_stored_instant__DoD2(engine: Engine) -> None:
    """DoD-2 — `last_login_at` is carried: the stored instant for an account that has one,
    nothing for an account that never signed in."""
    accounts = {account.id: account for account in _list(engine)}
    stamped = accounts[PLAYER_ID].last_login_at
    assert isinstance(stamped, datetime)
    assert stamped.tzinfo is not None
    assert stamped == KNOWN_LAST_LOGIN
    assert accounts[ADMIN_ID].last_login_at is None
    assert accounts[DISABLED_ID].last_login_at is None


def test_listing_carries_no_password_hash_and_no_language_default__DoD2(engine: Engine) -> None:
    """DoD-2 — no hash and no language default ride on a listed account (US-011.AC-2, R5)."""
    hashes = {row["password_hash"] for row in _all_user_rows(engine)}
    for account in _list(engine):
        for forbidden in ("password", "password_hash", "hash", "rp_language", "preferred_language"):
            assert not hasattr(account, forbidden)
        rendered = repr(account) + str(dataclasses.asdict(account))
        for stored_hash in hashes:
            assert stored_hash not in rendered
        for password in (ADMIN_PASSWORD, PLAYER_PASSWORD, DISABLED_PASSWORD, SECOND_ADMIN_PASSWORD):
            assert password not in rendered


def test_listing_carries_no_count_of_anything__DoD2(engine: Engine) -> None:
    """DoD-2 — no session count or any other count appears, even for an account with sessions (R5)."""
    for _ in range(3):
        _open(engine, PLAYER_ID)
    for account in _list(engine):
        assert set(dataclasses.asdict(account)) == EXPECTED_ACCOUNT_FIELDS
        assert not any("count" in name for name in dataclasses.asdict(account))


# ===================================================================================
# DoD-3 — no filter/page/sort argument, the full set, ordered by id ascending
# ===================================================================================


def test_listing_takes_only_the_connection__DoD3() -> None:
    """DoD-3 — no filter, page or sort parameter exists on the list operation."""
    assert list(inspect.signature(list_users).parameters) == ["connection"]


def test_listing_returns_the_full_set_in_id_order__DoD3(engine: Engine) -> None:
    """DoD-3 — every account, ordered by id ascending — not by username, not by insertion."""
    ids = [account.id for account in _list(engine)]
    assert ids == SEEDED_IDS_IN_ID_ORDER
    usernames = [account.username for account in _list(engine)]
    assert usernames != sorted(usernames)


def test_listing_includes_disabled_accounts__DoD3(engine: Engine) -> None:
    """DoD-3 — the full set: a disabled account is not filtered out."""
    assert DISABLED_ID in [account.id for account in _list(engine)]


def test_a_newly_added_account_is_listed_last__DoD3(engine: Engine) -> None:
    """DoD-3 — a fresh snowflake is the largest id, so the new account comes last."""
    created = _create(engine, SnowflakeGenerator(node_id=1), "newcomer", "fresh password", Role.ROLEPLAYER)
    listed = _list(engine)
    assert [account.id for account in listed] == [*SEEDED_IDS_IN_ID_ORDER, created.id]
    assert listed[-1].username == "newcomer"


# ===================================================================================
# DoD-4 — create inserts one enabled row with the given role, a real hash, NULL extras
# ===================================================================================


@pytest.mark.parametrize("role", [Role.ROLEPLAYER, Role.ADMIN])
def test_create_inserts_exactly_one_enabled_row__DoD4(engine: Engine, role: Role) -> None:
    """DoD-4 — one new `users` row, enabled, with the given role (US-008.AC-1)."""
    before = _user_count(engine)
    created = _create(engine, SnowflakeGenerator(node_id=1), "newcomer", "fresh password", role)
    assert _user_count(engine) == before + 1
    row = _user_row(engine, created.id)
    assert row["username"] == "newcomer"
    assert row["is_enabled"] is True
    assert row["role"] == role


def test_create_stores_a_hash_not_the_plaintext__DoD4(engine: Engine) -> None:
    """DoD-4 — `password_hash` is not the plaintext and does not contain it."""
    created = _create(engine, SnowflakeGenerator(node_id=1), "newcomer", "fresh password", Role.ROLEPLAYER)
    stored = _user_row(engine, created.id)["password_hash"]
    assert isinstance(stored, str)
    assert stored != ""
    assert stored != "fresh password"
    assert "fresh password" not in stored


def test_create_leaves_languages_and_last_login_null__DoD4(engine: Engine) -> None:
    """DoD-4 — `rp_language`, `preferred_language` and `last_login_at` are all NULL."""
    created = _create(engine, SnowflakeGenerator(node_id=1), "newcomer", "fresh password", Role.ROLEPLAYER)
    row = _user_row(engine, created.id)
    assert row["rp_language"] is None
    assert row["preferred_language"] is None
    assert row["last_login_at"] is None


def test_create_returns_the_account_in_the_list_shape__DoD4(engine: Engine) -> None:
    """DoD-4 — the returned account is the created one: enabled, given role, never signed in."""
    created = _create(engine, SnowflakeGenerator(node_id=1), "newcomer", "fresh password", Role.ADMIN)
    assert isinstance(created, UserAccount)
    assert created.username == "newcomer"
    assert created.role == Role.ADMIN
    assert created.is_enabled is True
    assert created.last_login_at is None
    assert "fresh password" not in repr(created)


def test_create_leaves_the_other_accounts_untouched__DoD4(engine: Engine) -> None:
    """DoD-4 — exactly one row is inserted: every pre-existing row is unchanged."""
    before = _all_user_rows(engine)
    _create(engine, SnowflakeGenerator(node_id=1), "newcomer", "fresh password", Role.ROLEPLAYER)
    after = [row for row in _all_user_rows(engine) if row["id"] in SEEDED_IDS_IN_ID_ORDER]
    assert after == before


# ===================================================================================
# DoD-5 — the created account appears in a subsequent listing
# ===================================================================================


def test_created_account_appears_in_the_next_listing__DoD5(engine: Engine) -> None:
    """DoD-5 — list after create includes the new account with its own values (US-008.AC-2)."""
    created = _create(engine, SnowflakeGenerator(node_id=1), "newcomer", "fresh password", Role.ROLEPLAYER)
    listed = {account.id: account for account in _list(engine)}
    assert created.id in listed
    assert listed[created.id] == created
    assert listed[created.id].username == "newcomer"
    assert listed[created.id].is_enabled is True


# ===================================================================================
# DoD-6 — the stored password verifies against its plaintext and nothing else
# ===================================================================================


def test_created_password_verifies_against_its_plaintext__DoD6(engine: Engine) -> None:
    """DoD-6 — 003's verification operation accepts the creating plaintext."""
    created = _create(engine, SnowflakeGenerator(node_id=1), "newcomer", "fresh password", Role.ROLEPLAYER)
    assert verify_password(_user_row(engine, created.id)["password_hash"], "fresh password") is True


@pytest.mark.parametrize(
    "candidate",
    ["", "Fresh password", "fresh password ", " fresh password", "fresh", "fresh passwordx", ADMIN_PASSWORD],
)
def test_created_password_verifies_against_nothing_else__DoD6(engine: Engine, candidate: str) -> None:
    """DoD-6 — any other candidate, including a near miss, is refused."""
    created = _create(engine, SnowflakeGenerator(node_id=1), "newcomer", "fresh password", Role.ROLEPLAYER)
    assert verify_password(_user_row(engine, created.id)["password_hash"], candidate) is False


def test_created_account_can_authenticate_with_its_password__DoD6(engine: Engine) -> None:
    """DoD-6 — the created credentials work end to end through the auth service."""
    created = _create(engine, SnowflakeGenerator(node_id=1), "newcomer", "fresh password", Role.ROLEPLAYER)
    with engine.connect() as connection:
        identity = authenticate(connection, "newcomer", "fresh password")
    assert identity.id == created.id


# ===================================================================================
# DoD-7 — the id comes from the generator given, never a process-wide one
# ===================================================================================


def test_create_mints_the_id_from_the_given_generator__DoD7(engine: Engine) -> None:
    """DoD-7 — two calls with two generators produce exactly those generators' ids."""
    first_generator = _FixedIdGenerator(4_242_424_242)
    second_generator = _FixedIdGenerator(9_191_919_191)
    first = _create(engine, first_generator, "first-newcomer", "fresh password", Role.ROLEPLAYER)
    second = _create(engine, second_generator, "second-newcomer", "fresh password", Role.ROLEPLAYER)
    assert first_generator.calls >= 1
    assert second_generator.calls >= 1
    assert first.id == 4_242_424_242
    assert second.id == 9_191_919_191
    assert _user_row(engine, 4_242_424_242)["username"] == "first-newcomer"
    assert _user_row(engine, 9_191_919_191)["username"] == "second-newcomer"


def _module_tree() -> ast.Module:
    return ast.parse(inspect.getsource(users_module))


def test_module_reaches_no_process_wide_generator__DoD7() -> None:
    """DoD-7 — nothing in the module builds, holds or fetches a generator of its own."""
    held = [name for name, value in vars(users_module).items() if isinstance(value, SnowflakeGenerator)]
    assert held == []
    offenders: list[str] = []
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Call):
            callee = node.func
            name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", "")
            if name in {"SnowflakeGenerator", "build_id_generator"}:
                offenders.append(name)
        elif isinstance(node, ast.Attribute) and node.attr in {"id_generator", "state"}:
            offenders.append(node.attr)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            offenders.extend(alias.name for alias in node.names if alias.name == "build_id_generator")
    assert offenders == []


# ===================================================================================
# DoD-8 — a duplicate username raises username_taken and writes nothing
# ===================================================================================


def test_duplicate_username_raises_username_taken__DoD8(engine: Engine) -> None:
    """DoD-8 — creating an account under an existing username is refused with `username_taken`."""
    with pytest.raises(UsernameTakenError) as excinfo:
        _create(engine, SnowflakeGenerator(node_id=1), PLAYER_NAME, "another password", Role.ADMIN)
    assert excinfo.value.code == "username_taken"
    assert excinfo.value.detail == {}
    assert PLAYER_NAME not in str(excinfo.value.to_wire())


def test_duplicate_username_writes_nothing__DoD8(engine: Engine) -> None:
    """DoD-8 — the account count is unchanged and the existing row is untouched."""
    before = _all_user_rows(engine)
    with pytest.raises(UsernameTakenError):
        _create(engine, SnowflakeGenerator(node_id=1), PLAYER_NAME, "another password", Role.ADMIN)
    assert _user_count(engine) == len(before)
    assert _all_user_rows(engine) == before
    assert verify_password(_user_row(engine, PLAYER_ID)["password_hash"], PLAYER_PASSWORD) is True


def test_username_created_through_the_service_cannot_be_created_again__DoD8(engine: Engine) -> None:
    """DoD-8 — the refusal also holds for an account the service itself created."""
    generator = SnowflakeGenerator(node_id=1)
    created = _create(engine, generator, "newcomer", "fresh password", Role.ROLEPLAYER)
    before = _all_user_rows(engine)
    with pytest.raises(UsernameTakenError):
        _create(engine, generator, "newcomer", "other password", Role.ADMIN)
    assert _all_user_rows(engine) == before
    assert _user_row(engine, created.id)["role"] == Role.ROLEPLAYER


# ===================================================================================
# DoD-9 — the username is stored exactly as received
# ===================================================================================

CASE_AND_SPACE_VARIANTS = ["alice", "Alice", "ALICE", " alice", "alice ", "\talice\n"]


def test_case_and_whitespace_variants_are_all_creatable__DoD9(engine: Engine) -> None:
    """DoD-9 — variants differing by case or surrounding whitespace never collide (004's D13)."""
    generator = SnowflakeGenerator(node_id=1)
    created = [
        _create(engine, generator, name, "fresh password", Role.ROLEPLAYER) for name in CASE_AND_SPACE_VARIANTS
    ]
    assert len({account.id for account in created}) == len(CASE_AND_SPACE_VARIANTS)
    assert _user_count(engine) == len(SEEDED_IDS_IN_ID_ORDER) + len(CASE_AND_SPACE_VARIANTS)


def test_username_is_stored_and_returned_verbatim__DoD9(engine: Engine) -> None:
    """DoD-9 — no trimming, no case folding: the stored and returned username is the input."""
    generator = SnowflakeGenerator(node_id=1)
    for name in CASE_AND_SPACE_VARIANTS:
        created = _create(engine, generator, name, "fresh password", Role.ROLEPLAYER)
        assert created.username == name
        assert _user_row(engine, created.id)["username"] == name
    listed = {account.username for account in _list(engine)}
    assert set(CASE_AND_SPACE_VARIANTS) <= listed


@pytest.mark.parametrize("variant", ["Wanderer", "WANDERER", " wanderer", "wanderer "])
def test_variant_of_an_existing_username_does_not_collide__DoD9(engine: Engine, variant: str) -> None:
    """DoD-9 — a variant of a seeded username is a different username."""
    created = _create(engine, SnowflakeGenerator(node_id=1), variant, "fresh password", Role.ROLEPLAYER)
    assert _user_row(engine, created.id)["username"] == variant
    assert _user_row(engine, PLAYER_ID)["username"] == PLAYER_NAME


# ===================================================================================
# DoD-10 — disable flips the flag and revokes every live session of that account
# ===================================================================================


def test_disable_sets_is_enabled_false__DoD10(engine: Engine) -> None:
    """DoD-10 — the account is stored disabled and reported disabled (US-009.AC-1)."""
    result = _disable(engine, PLAYER_ID)
    assert _user_row(engine, PLAYER_ID)["is_enabled"] is False
    assert isinstance(result, UserAccount)
    assert result.id == PLAYER_ID
    assert result.is_enabled is False
    assert result.username == PLAYER_NAME


def test_disable_revokes_every_live_session_of_the_account__DoD10(engine: Engine) -> None:
    """DoD-10 — every live `auth_sessions` row of the account gains a `revoked_at` (US-009.AC-1)."""
    for _ in range(3):
        _open(engine, PLAYER_ID)
    assert all(row["revoked_at"] is None for row in _sessions_of(engine, PLAYER_ID))
    _disable(engine, PLAYER_ID)
    rows = _sessions_of(engine, PLAYER_ID)
    assert len(rows) == 3
    assert all(row["revoked_at"] is not None for row in rows)


def test_after_disable_none_of_the_accounts_tokens_resolves__DoD10(engine: Engine) -> None:
    """DoD-10 — none of the account's tokens resolves afterwards (US-009.AC-1)."""
    tokens = [_open(engine, PLAYER_ID) for _ in range(3)]
    assert all(_resolves(engine, token) for token in tokens)
    _disable(engine, PLAYER_ID)
    assert not any(_resolves(engine, token) for token in tokens)


def test_revocations_persist_even_after_re_enable__DoD10(engine: Engine) -> None:
    """DoD-10 — the sessions are revoked, not merely hidden by the flag: re-enabling does
    not bring any of them back."""
    tokens = [_open(engine, PLAYER_ID) for _ in range(2)]
    _disable(engine, PLAYER_ID)
    _enable(engine, PLAYER_ID)
    assert not any(_resolves(engine, token) for token in tokens)


# ===================================================================================
# DoD-11 — disable is one transaction
# ===================================================================================

# Two injected failures, installed as SQLite triggers so they need nothing from the module
# under test: one aborts the flag flip, one aborts the revocation. Whatever order the two
# writes run in, one of the two triggers fails the *second* write, after the first has
# been made — and neither write may survive.

_REFUSE_FLAG_FLIP = (
    "CREATE TRIGGER inject_refuse_flag_flip BEFORE UPDATE ON users "
    "WHEN NEW.is_enabled = 0 BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
)
_REFUSE_REVOCATION = (
    "CREATE TRIGGER inject_refuse_revocation BEFORE UPDATE ON auth_sessions "
    "WHEN NEW.revoked_at IS NOT NULL BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
)
_TRIGGERS = {
    "flag_flip_fails": ("inject_refuse_flag_flip", _REFUSE_FLAG_FLIP),
    "revocation_fails": ("inject_refuse_revocation", _REFUSE_REVOCATION),
}


@pytest.mark.parametrize("failure", sorted(_TRIGGERS))
def test_disable_is_all_or_nothing_when_either_write_fails__DoD11(engine: Engine, failure: str) -> None:
    """DoD-11 — when the operation fails part-way, neither the flag nor the revocations survive:
    never disabled-with-live-sessions, never revoked-but-still-enabled (US-009.AC-1)."""
    tokens = [_open(engine, PLAYER_ID) for _ in range(2)]
    user_before = _user_row(engine, PLAYER_ID)
    sessions_before = _session_rows(engine)
    trigger_name, trigger_sql = _TRIGGERS[failure]
    with engine.begin() as connection:
        connection.execute(text(trigger_sql))

    # The injected abort surfaces as a database error; the service has no reason to catch it.
    with pytest.raises(DBAPIError):
        _disable(engine, PLAYER_ID)

    assert _user_row(engine, PLAYER_ID) == user_before
    assert _user_row(engine, PLAYER_ID)["is_enabled"] is True
    assert _session_rows(engine) == sessions_before
    assert all(row["revoked_at"] is None for row in _sessions_of(engine, PLAYER_ID))
    assert all(_resolves(engine, token) for token in tokens)

    # With the injected failure removed, the same disable goes through whole.
    with engine.begin() as connection:
        connection.execute(text(f"DROP TRIGGER {trigger_name}"))
    _disable(engine, PLAYER_ID)
    assert _user_row(engine, PLAYER_ID)["is_enabled"] is False
    assert all(row["revoked_at"] is not None for row in _sessions_of(engine, PLAYER_ID))
    assert not any(_resolves(engine, token) for token in tokens)


# ===================================================================================
# DoD-12 — disable touches no other account; disabling twice raises nothing
# ===================================================================================


def test_disable_touches_no_other_account__DoD12(engine: Engine) -> None:
    """DoD-12 — every other account's row and sessions are unchanged, its tokens still resolve."""
    admin_tokens = [_open(engine, ADMIN_ID) for _ in range(2)]
    _open(engine, PLAYER_ID)
    others_before = [row for row in _all_user_rows(engine) if row["id"] != PLAYER_ID]
    admin_sessions_before = _sessions_of(engine, ADMIN_ID)
    _disable(engine, PLAYER_ID)
    assert [row for row in _all_user_rows(engine) if row["id"] != PLAYER_ID] == others_before
    assert _sessions_of(engine, ADMIN_ID) == admin_sessions_before
    assert all(_resolves(engine, token) for token in admin_tokens)


def test_disabling_an_already_disabled_account_raises_nothing__DoD12(engine: Engine) -> None:
    """DoD-12 — a second disable is not an error; the account stays disabled."""
    result = _disable(engine, DISABLED_ID)
    assert result.is_enabled is False
    assert _user_row(engine, DISABLED_ID)["is_enabled"] is False

    _disable(engine, PLAYER_ID)
    again = _disable(engine, PLAYER_ID)
    assert again.id == PLAYER_ID
    assert again.is_enabled is False
    assert _user_row(engine, PLAYER_ID)["is_enabled"] is False


def test_disabling_twice_keeps_every_session_revoked_and_deletes_none__DoD12(engine: Engine) -> None:
    """DoD-12 — the repeated revoke is idempotent: all rows still there, all still revoked."""
    for _ in range(2):
        _open(engine, PLAYER_ID)
    _disable(engine, PLAYER_ID)
    after_first = _sessions_of(engine, PLAYER_ID)
    _disable(engine, PLAYER_ID)
    after_second = _sessions_of(engine, PLAYER_ID)
    assert len(after_second) == len(after_first) == 2
    assert all(row["revoked_at"] is not None for row in after_second)


# ===================================================================================
# DoD-13 — re-enable flips the flag back, creates no session, leaves revocations alone
# ===================================================================================


def test_enable_sets_is_enabled_true__DoD13(engine: Engine) -> None:
    """DoD-13 — a disabled account is stored and reported enabled again (UC-007 alternate flow)."""
    result = _enable(engine, DISABLED_ID)
    assert _user_row(engine, DISABLED_ID)["is_enabled"] is True
    assert isinstance(result, UserAccount)
    assert result.id == DISABLED_ID
    assert result.is_enabled is True


def test_enable_creates_no_session__DoD13(engine: Engine) -> None:
    """DoD-13 — no `auth_sessions` row is created by re-enabling."""
    _open(engine, PLAYER_ID)
    _disable(engine, PLAYER_ID)
    count_before = len(_session_rows(engine))
    _enable(engine, PLAYER_ID)
    _enable(engine, DISABLED_ID)
    assert len(_session_rows(engine)) == count_before


def test_enable_leaves_revoked_sessions_revoked__DoD13(engine: Engine) -> None:
    """DoD-13 — the sessions the disable revoked stay revoked, byte for byte."""
    tokens = [_open(engine, PLAYER_ID) for _ in range(2)]
    _disable(engine, PLAYER_ID)
    revoked_before = _sessions_of(engine, PLAYER_ID)
    _enable(engine, PLAYER_ID)
    assert _sessions_of(engine, PLAYER_ID) == revoked_before
    assert not any(_resolves(engine, token) for token in tokens)


def test_re_enabled_account_can_authenticate_again__DoD13(engine: Engine) -> None:
    """DoD-13 — re-enabling restores the ability to log in (UC-007 alternate flow)."""
    _enable(engine, DISABLED_ID)
    with engine.connect() as connection:
        identity = authenticate(connection, DISABLED_NAME, DISABLED_PASSWORD)
    assert identity.id == DISABLED_ID


# ===================================================================================
# DoD-14 — set password replaces the hash, returns no secret, keeps sessions live
# ===================================================================================


def test_set_password_replaces_the_stored_hash__DoD14(engine: Engine) -> None:
    """DoD-14 — the old plaintext no longer verifies and the new one does (US-010.AC-1, AC-2)."""
    before_hash = _user_row(engine, PLAYER_ID)["password_hash"]
    _set_password(engine, PLAYER_ID, "a brand new secret")
    stored = _user_row(engine, PLAYER_ID)["password_hash"]
    assert stored != before_hash
    assert stored != "a brand new secret"
    assert verify_password(stored, PLAYER_PASSWORD) is False
    assert verify_password(stored, "a brand new secret") is True


def test_set_password_changes_what_login_accepts__DoD14(engine: Engine) -> None:
    """DoD-14 — login with the old password is refused and with the new one succeeds (US-010)."""
    _set_password(engine, PLAYER_ID, "a brand new secret")
    with engine.connect() as connection:
        with pytest.raises(InvalidCredentialsError):
            authenticate(connection, PLAYER_NAME, PLAYER_PASSWORD)
    with engine.connect() as connection:
        assert authenticate(connection, PLAYER_NAME, "a brand new secret").id == PLAYER_ID


def test_set_password_result_carries_no_password_and_no_hash__DoD14(engine: Engine) -> None:
    """DoD-14 — the returned account is the one shape, with neither the password nor the hash."""
    result = _set_password(engine, PLAYER_ID, "a brand new secret")
    assert isinstance(result, UserAccount)
    assert {field.name for field in dataclasses.fields(result)} == EXPECTED_ACCOUNT_FIELDS
    assert result.id == PLAYER_ID
    stored = _user_row(engine, PLAYER_ID)["password_hash"]
    rendered = repr(result) + str(dataclasses.asdict(result))
    assert "a brand new secret" not in rendered
    assert stored not in rendered


def test_set_password_leaves_live_sessions_live__DoD14(engine: Engine) -> None:
    """DoD-14 — the target's sessions are not revoked by a reset (context.md D6)."""
    tokens = [_open(engine, PLAYER_ID) for _ in range(2)]
    sessions_before = _sessions_of(engine, PLAYER_ID)
    _set_password(engine, PLAYER_ID, "a brand new secret")
    assert _sessions_of(engine, PLAYER_ID) == sessions_before
    assert all(row["revoked_at"] is None for row in _sessions_of(engine, PLAYER_ID))
    assert all(_resolves(engine, token) for token in tokens)


def test_set_password_takes_no_current_password__DoD14() -> None:
    """DoD-14 — the reset is administrator-initiated: target id and new password only (D6)."""
    assert list(inspect.signature(set_user_password).parameters) == ["connection", "user_id", "password"]


# ===================================================================================
# DoD-15 — set role writes the role and nothing else but updated_at (no product id)
# ===================================================================================


@pytest.mark.parametrize(
    ("target_id", "new_role"),
    [(PLAYER_ID, Role.ADMIN), (SECOND_ADMIN_ID, Role.ROLEPLAYER)],
)
def test_set_role_writes_the_new_role__DoD15(engine: Engine, target_id: int, new_role: Role) -> None:
    """DoD-15 — the stored and returned role is the new one (admin-surfaces.md "Change Role")."""
    result = _set_role(engine, target_id, new_role, ADMIN_ID)
    assert _user_row(engine, target_id)["role"] == new_role
    assert isinstance(result, UserAccount)
    assert result.id == target_id
    assert result.role == new_role


@pytest.mark.parametrize(
    ("target_id", "new_role"),
    [(PLAYER_ID, Role.ADMIN), (SECOND_ADMIN_ID, Role.ROLEPLAYER)],
)
def test_set_role_changes_no_other_column_but_updated_at__DoD15(
    engine: Engine, target_id: int, new_role: Role
) -> None:
    """DoD-15 — every column except `role` and `updated_at` is unchanged (data-model.md `users.role`)."""
    before = _user_row(engine, target_id)
    _set_role(engine, target_id, new_role, ADMIN_ID)
    after = _user_row(engine, target_id)
    assert _without(after, "role", "updated_at") == _without(before, "role", "updated_at")


def test_set_role_touches_no_other_account_and_revokes_nothing__DoD15(engine: Engine) -> None:
    """DoD-15 — other accounts are unchanged and the target's sessions stay live (004's D7)."""
    token = _open(engine, PLAYER_ID)
    others_before = [row for row in _all_user_rows(engine) if row["id"] != PLAYER_ID]
    sessions_before = _session_rows(engine)
    _set_role(engine, PLAYER_ID, Role.ADMIN, ADMIN_ID)
    assert [row for row in _all_user_rows(engine) if row["id"] != PLAYER_ID] == others_before
    assert _session_rows(engine) == sessions_before
    with engine.connect() as connection:
        resolved = resolve_session(connection, token)
    assert resolved is not None
    assert resolved.role == Role.ADMIN


# ===================================================================================
# DoD-16 — a self-targeted role change is refused and writes nothing (no product id)
# ===================================================================================


@pytest.mark.parametrize("new_role", [Role.ROLEPLAYER, Role.ADMIN])
def test_self_role_change_is_refused__DoD16(engine: Engine, new_role: Role) -> None:
    """DoD-16 — target == acting administrator raises `self_role_change_refused`
    (admin-surfaces.md "Change Role")."""
    with pytest.raises(SelfRoleChangeRefusedError) as excinfo:
        _set_role(engine, ADMIN_ID, new_role, ADMIN_ID)
    assert excinfo.value.code == "self_role_change_refused"
    assert excinfo.value.detail == {}


def test_self_role_change_writes_nothing__DoD16(engine: Engine) -> None:
    """DoD-16 — after the refusal the account's role and every other column are unchanged."""
    before = _all_user_rows(engine)
    sessions_before = _session_rows(engine)
    with pytest.raises(SelfRoleChangeRefusedError):
        _set_role(engine, ADMIN_ID, Role.ROLEPLAYER, ADMIN_ID)
    assert _user_row(engine, ADMIN_ID)["role"] == Role.ADMIN
    assert _all_user_rows(engine) == before
    assert _session_rows(engine) == sessions_before


def test_same_target_by_a_different_administrator_succeeds__DoD16(engine: Engine) -> None:
    """DoD-16 — the refusal is about self-targeting only: another administrator may change it."""
    with pytest.raises(SelfRoleChangeRefusedError):
        _set_role(engine, ADMIN_ID, Role.ROLEPLAYER, ADMIN_ID)
    result = _set_role(engine, ADMIN_ID, Role.ROLEPLAYER, SECOND_ADMIN_ID)
    assert result.id == ADMIN_ID
    assert result.role == Role.ROLEPLAYER
    assert _user_row(engine, ADMIN_ID)["role"] == Role.ROLEPLAYER


# ===================================================================================
# DoD-17 — every id-addressed operation raises user_not_found for an unknown id
# ===================================================================================

ID_ADDRESSED_OPERATIONS: dict[str, Callable[[Engine, int], UserAccount]] = {
    "disable": _disable,
    "enable": _enable,
    "set_password": lambda engine, user_id: _set_password(engine, user_id, "a brand new secret"),
    "set_role_to_admin": lambda engine, user_id: _set_role(engine, user_id, Role.ADMIN, ADMIN_ID),
    "set_role_to_roleplayer": lambda engine, user_id: _set_role(engine, user_id, Role.ROLEPLAYER, ADMIN_ID),
}


@pytest.mark.parametrize("operation", sorted(ID_ADDRESSED_OPERATIONS))
def test_unknown_id_raises_user_not_found__DoD17(engine: Engine, operation: str) -> None:
    """DoD-17 — an id no account has is refused with `user_not_found`, empty detail."""
    with pytest.raises(UserNotFoundError) as excinfo:
        ID_ADDRESSED_OPERATIONS[operation](engine, UNKNOWN_USER_ID)
    assert excinfo.value.code == "user_not_found"
    assert excinfo.value.detail == {}


@pytest.mark.parametrize("operation", sorted(ID_ADDRESSED_OPERATIONS))
def test_unknown_id_writes_nothing__DoD17(engine: Engine, operation: str) -> None:
    """DoD-17 — no account row and no session row changes, and no row is created."""
    for user_id in (ADMIN_ID, PLAYER_ID):
        _open(engine, user_id)
    users_before = _all_user_rows(engine)
    sessions_before = _session_rows(engine)
    with pytest.raises(UserNotFoundError):
        ID_ADDRESSED_OPERATIONS[operation](engine, UNKNOWN_USER_ID)
    assert _all_user_rows(engine) == users_before
    assert _session_rows(engine) == sessions_before


# ===================================================================================
# DoD-18 — every mutation updates updated_at, none writes last_login_at
# ===================================================================================


def test_create_sets_updated_at_to_the_creation_instant__DoD18(engine: Engine) -> None:
    """DoD-18 — a created account's `updated_at` is now, the same instant as `created_at`,
    and `last_login_at` is not written."""
    before = datetime.now(UTC)
    created = _create(engine, SnowflakeGenerator(node_id=1), "newcomer", "fresh password", Role.ROLEPLAYER)
    after = datetime.now(UTC)
    row = _user_row(engine, created.id)
    _assert_current_instant(row["updated_at"], before, after)
    assert _parse_utc(row["updated_at"]) == _parse_utc(row["created_at"])
    assert row["last_login_at"] is None


MUTATIONS: dict[str, tuple[int, Callable[[Engine], UserAccount]]] = {
    "disable": (PLAYER_ID, lambda engine: _disable(engine, PLAYER_ID)),
    "enable": (DISABLED_ID, lambda engine: _enable(engine, DISABLED_ID)),
    "set_password": (PLAYER_ID, lambda engine: _set_password(engine, PLAYER_ID, "a brand new secret")),
    "set_role": (PLAYER_ID, lambda engine: _set_role(engine, PLAYER_ID, Role.ADMIN, ADMIN_ID)),
}


@pytest.mark.parametrize("mutation", sorted(MUTATIONS))
def test_mutation_updates_updated_at__DoD18(engine: Engine, mutation: str) -> None:
    """DoD-18 — disable, enable, set password and set role each move `updated_at` to now."""
    target_id, run = MUTATIONS[mutation]
    assert _user_row(engine, target_id)["updated_at"] == TIMESTAMP
    before = datetime.now(UTC)
    run(engine)
    after = datetime.now(UTC)
    row = _user_row(engine, target_id)
    assert row["updated_at"] != TIMESTAMP
    _assert_current_instant(row["updated_at"], before, after)
    assert row["created_at"] == TIMESTAMP


@pytest.mark.parametrize("mutation", sorted(MUTATIONS))
def test_mutation_does_not_write_last_login_at__DoD18(engine: Engine, mutation: str) -> None:
    """DoD-18 — the account's `last_login_at` is exactly what it was before the mutation."""
    target_id, run = MUTATIONS[mutation]
    before = _user_row(engine, target_id)["last_login_at"]
    run(engine)
    assert _user_row(engine, target_id)["last_login_at"] == before


def test_mutations_keep_a_known_last_login_at_verbatim__DoD18(engine: Engine) -> None:
    """DoD-18 — an account that has a login instant keeps it through every mutation."""
    assert _user_row(engine, PLAYER_ID)["last_login_at"] == KNOWN_LAST_LOGIN_TEXT
    _set_password(engine, PLAYER_ID, "a brand new secret")
    _set_role(engine, PLAYER_ID, Role.ADMIN, ADMIN_ID)
    _disable(engine, PLAYER_ID)
    _enable(engine, PLAYER_ID)
    assert _user_row(engine, PLAYER_ID)["last_login_at"] == KNOWN_LAST_LOGIN_TEXT
    listed = {account.id: account for account in _list(engine)}
    assert listed[PLAYER_ID].last_login_at == KNOWN_LAST_LOGIN


def test_successive_mutations_advance_updated_at__DoD18(engine: Engine) -> None:
    """DoD-18 — each mutation writes its own instant, so a later one moves `updated_at` forward."""
    _set_password(engine, PLAYER_ID, "a brand new secret")
    first = _parse_utc(_user_row(engine, PLAYER_ID)["updated_at"])
    time.sleep(0.05)
    _set_role(engine, PLAYER_ID, Role.ADMIN, ADMIN_ID)
    second = _parse_utc(_user_row(engine, PLAYER_ID)["updated_at"])
    assert second > first


# ===================================================================================
# DoD-19 — no fastapi, no status code, no Request, no settings; plain arguments only
# ===================================================================================


def _imported_modules() -> list[str]:
    imported: list[str] = []
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
    return imported


def test_module_imports_no_fastapi_or_starlette__DoD19() -> None:
    """DoD-19 — no `fastapi` (or its `starlette` base) import anywhere in the module."""
    offenders = [name for name in _imported_modules() if name.split(".")[0] in {"fastapi", "starlette"}]
    assert offenders == []


def test_module_does_not_import_the_request_dependencies__DoD19() -> None:
    """DoD-19 — `app.dependencies` imports fastapi, so the service may not import it or
    `CurrentUser` (002.context.md: the acting administrator arrives as a plain id)."""
    assert "app.dependencies" not in _imported_modules()
    names = [
        node.id if isinstance(node, ast.Name) else node.attr
        for node in ast.walk(_module_tree())
        if isinstance(node, ast.Name | ast.Attribute)
    ]
    assert "CurrentUser" not in names


def test_module_binds_no_fastapi_symbol__DoD19() -> None:
    """DoD-19 — no module-level name is a fastapi/starlette object."""
    offenders = []
    for name, value in vars(users_module).items():
        origin = getattr(value, "__module__", None) or getattr(value, "__name__", "")
        if isinstance(origin, str) and origin.split(".")[0] in {"fastapi", "starlette"}:
            offenders.append(name)
    assert offenders == []


HTTP_STATUS_LITERALS = {200, 201, 204, 400, 401, 403, 404, 409, 422, 500}


def test_module_references_no_http_status_code__DoD19() -> None:
    """DoD-19 — no HTTP status literal and no status-code name appears in the module."""
    status_words = {"HTTPStatus", "HTTPException", "status_code", "http_status"}
    literal_statuses: list[int] = []
    status_names: list[str] = []
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Constant) and type(node.value) is int and node.value in HTTP_STATUS_LITERALS:
            literal_statuses.append(node.value)
        elif isinstance(node, ast.Name) and (node.id in status_words or node.id.startswith("HTTP_")):
            status_names.append(node.id)
        elif isinstance(node, ast.Attribute) and (node.attr in status_words or node.attr.startswith("HTTP_")):
            status_names.append(node.attr)
    assert literal_statuses == []
    assert status_names == []


def test_module_reads_no_settings__DoD19() -> None:
    """DoD-19 — the module imports no config and names no settings object."""
    assert not any(name == "app.config" or name.startswith("app.config.") for name in _imported_modules())
    forbidden = {"get_settings", "Settings"}
    seen: list[str] = []
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Name) and node.id in forbidden:
            seen.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in forbidden:
            seen.append(node.attr)
        elif isinstance(node, ast.alias) and node.name in forbidden:
            seen.append(node.name)
    assert seen == []


@pytest.mark.parametrize(
    ("function", "expected_parameters"),
    [
        (list_users, ["connection"]),
        (create_user, ["connection", "generator", "username", "password", "role"]),
        (disable_user, ["connection", "user_id"]),
        (enable_user, ["connection", "user_id"]),
        (set_user_password, ["connection", "user_id", "password"]),
        (set_user_role, ["connection", "user_id", "role", "acting_user_id"]),
    ],
)
def test_operations_take_plain_arguments_and_no_request__DoD19(
    function: Callable[..., Any], expected_parameters: list[str]
) -> None:
    """DoD-19 — a Core connection first, then plain values; no `Request`, settings or
    fastapi/starlette type anywhere in the contract."""
    signature = inspect.signature(function)
    assert list(signature.parameters) == expected_parameters
    rendered = " ".join(str(parameter) for parameter in signature.parameters.values())
    rendered = f"{rendered} {signature.return_annotation}"
    assert "fastapi" not in rendered.lower()
    assert "starlette" not in rendered.lower()
    assert "Request" not in rendered
    assert "Settings" not in rendered
    assert "CurrentUser" not in rendered


def test_every_operation_is_callable_with_plain_values__DoD19(engine: Engine) -> None:
    """DoD-19 — a plain connection, a generator and plain values drive all six operations."""
    generator = SnowflakeGenerator(node_id=3)
    created = _create(engine, generator, "plain-caller", "plain password", Role.ROLEPLAYER)
    assert _disable(engine, created.id).is_enabled is False
    assert _enable(engine, created.id).is_enabled is True
    assert _set_password(engine, created.id, "another plain password").id == created.id
    assert _set_role(engine, created.id, Role.ADMIN, ADMIN_ID).role == Role.ADMIN
    assert created.id in [account.id for account in _list(engine)]
