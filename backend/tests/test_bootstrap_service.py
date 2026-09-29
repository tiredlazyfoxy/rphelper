"""Tests for ``app.services.bootstrap`` — the configured fact and the one-transaction creation.

Every expected value comes from ``docs/plans/003.first-run-bootstrap/002.bootstrap-service-and-error.md``
(Interface intent + Definition of done), ``002.context.md`` and the feature ``context.md``
(D3 what ``configured`` reads, D4 one definition, D8 create-all inside the transaction,
D15 what the insert writes). Bindings come from ``## Skeleton`` in ``status.md``.

Covers step 002 DoD-2, DoD-3, DoD-4, DoD-5, DoD-6, DoD-7, DoD-8, DoD-10 and DoD-11.
DoD-1 lives in ``test_errors.py``, DoD-9 in ``test_health.py``, DoD-15/16 in
``test_db_engine.py``; DoD-12..14 and DoD-17 are ``[manual/live]``.

Connection hygiene: the creation operation opens its own ``with conn.begin():`` block, so
every setup write here is committed and every post-condition is read on a *fresh*
connection — no test hands the operation a connection with a transaction already open.
"""

import ast
import inspect
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, MetaData, select

from app.db import schema
from app.errors import AlreadyConfiguredError
from app.ids import EPOCH_MS, SnowflakeGenerator
from app.roles import Role
from app.services import bootstrap as bootstrap_module
from app.services.bootstrap import BootstrapResult, create_first_administrator, is_configured
from app.services.health import probe_health
from app.services.passwords import verify_password

USERNAME = "founder"
PASSWORD = "correct horse battery staple"
OTHER_PASSWORD = "not the password at all"
TIMESTAMP = "2026-01-01T00:00:00+00:00"
EXISTING_ADMIN_HASH = "pre-existing-admin-hash-sentinel"


class _FixedIdGenerator:
    """A generator stand-in whose ``next_id()`` always answers one known value."""

    def __init__(self, value: int) -> None:
        self.value = value

    def next_id(self) -> int:
        return self.value


def _frozen_clock() -> int:
    """A clock stuck one day after the snowflake epoch."""
    return EPOCH_MS + 86_400_000


def _real_generator(node_id: int) -> SnowflakeGenerator:
    """A real snowflake generator on a frozen clock, so a twin yields the same sequence."""
    return SnowflakeGenerator(node_id=node_id, clock=_frozen_clock)


# --- setup helpers (all committed, never left with an open transaction) --------------


def _apply_registry(engine: Engine) -> None:
    with engine.connect() as connection:
        schema.metadata.create_all(connection)
        connection.commit()


def _create_users_table_only(engine: Engine) -> None:
    with engine.connect() as connection:
        schema.users.create(connection)
        connection.commit()


def _insert_user(
    engine: Engine,
    *,
    user_id: int,
    username: str,
    role: Role,
    password_hash: str = "not-a-real-hash",
) -> None:
    with engine.connect() as connection:
        connection.execute(
            schema.users.insert().values(
                id=user_id,
                username=username,
                password_hash=password_hash,
                role=role,
                is_enabled=True,
                rp_language=None,
                preferred_language=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )
        connection.commit()


def _table_names(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        rows = connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type = 'table'").all()
    return {row[0] for row in rows}


def _user_rows(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(select(schema.users)).mappings().all()]


def _admin_row_count_on(connection: Connection) -> int:
    """Administrator rows visible on ``connection``; zero when the table is absent."""
    present = connection.exec_driver_sql(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'users'"
    ).scalar_one()
    if not present:
        return 0
    count = connection.exec_driver_sql("SELECT COUNT(*) FROM users WHERE role = 'admin'").scalar_one()
    return int(count)


def _bootstrap(engine: Engine, generator: Any, username: str = USERNAME, password: str = PASSWORD) -> BootstrapResult:
    with engine.connect() as connection:
        return create_first_administrator(connection, generator, username, password)


# --- DoD-2: false with no schema, false with an empty users table -------------------


def test_predicate_is_false_with_no_schema_at_all__DoD2(db_engine: Engine) -> None:
    """DoD-2 — a database with no tables answers false rather than raising (US-003.AC-1)."""
    with db_engine.connect() as connection:
        assert is_configured(connection) is False


def test_predicate_is_false_with_an_empty_users_table__DoD2(db_engine: Engine) -> None:
    """DoD-2 — a present but unpopulated `users` table still means no administrator."""
    _create_users_table_only(db_engine)
    with db_engine.connect() as connection:
        assert is_configured(connection) is False


def test_predicate_is_false_with_the_whole_registry_but_no_rows__DoD2(db_engine: Engine) -> None:
    """DoD-2 — every registry table present and `users` empty is still unconfigured."""
    _apply_registry(db_engine)
    with db_engine.connect() as connection:
        assert is_configured(connection) is False


# --- DoD-3: non-admin rows are not enough; one admin row is ---------------------------


def test_predicate_is_false_with_only_roleplayer_rows__DoD3(db_engine: Engine) -> None:
    """DoD-3 — `users` holding only non-administrator rows answers false (US-003.AC-1)."""
    _apply_registry(db_engine)
    _insert_user(db_engine, user_id=101, username="reader", role=Role.ROLEPLAYER)
    _insert_user(db_engine, user_id=102, username="writer", role=Role.ROLEPLAYER)
    with db_engine.connect() as connection:
        assert is_configured(connection) is False


def test_predicate_is_true_with_one_administrator_row__DoD3(db_engine: Engine) -> None:
    """DoD-3 — one administrator row is enough (US-003.AC-1)."""
    _apply_registry(db_engine)
    _insert_user(db_engine, user_id=201, username="founder", role=Role.ADMIN)
    with db_engine.connect() as connection:
        assert is_configured(connection) is True


def test_predicate_is_true_with_an_administrator_among_roleplayers__DoD3(db_engine: Engine) -> None:
    """DoD-3 — "as soon as one administrator row exists", whatever else is there."""
    _apply_registry(db_engine)
    _insert_user(db_engine, user_id=301, username="reader", role=Role.ROLEPLAYER)
    _insert_user(db_engine, user_id=302, username="founder", role=Role.ADMIN)
    with db_engine.connect() as connection:
        assert is_configured(connection) is True


# --- DoD-4: creation against a database with no schema ------------------------------


def test_creation_applies_every_registry_table__DoD4(db_engine: Engine) -> None:
    """DoD-4 — every table declared in the registry is present afterwards (US-001.AC-1)."""
    _bootstrap(db_engine, _FixedIdGenerator(4_000_000_000_001))
    assert set(schema.metadata.tables) <= _table_names(db_engine)


def test_creation_leaves_exactly_one_administrator_row__DoD4(db_engine: Engine) -> None:
    """DoD-4 — exactly one `users` row, role admin, enabled, languages NULL (US-001.AC-1)."""
    _bootstrap(db_engine, _FixedIdGenerator(4_000_000_000_002))
    rows = _user_rows(db_engine)
    assert len(rows) == 1
    row = rows[0]
    assert row["username"] == USERNAME
    assert row["role"] == Role.ADMIN
    assert row["is_enabled"] is True
    assert row["rp_language"] is None
    assert row["preferred_language"] is None


def test_creation_stores_the_role_as_the_administrator_value__DoD4(db_engine: Engine) -> None:
    """DoD-4 — the stored role column literally holds the administrator value `admin`."""
    _bootstrap(db_engine, _FixedIdGenerator(4_000_000_000_003))
    with db_engine.connect() as connection:
        roles = [row[0] for row in connection.exec_driver_sql("SELECT role FROM users").all()]
    assert roles == ["admin"]


def test_creation_does_not_store_the_plaintext_password__DoD4(db_engine: Engine) -> None:
    """DoD-4 — `password_hash` is not the plaintext."""
    _bootstrap(db_engine, _FixedIdGenerator(4_000_000_000_004))
    stored = _user_rows(db_engine)[0]["password_hash"]
    assert stored
    assert stored != PASSWORD
    assert PASSWORD not in stored


def test_creation_returns_the_new_administrators_id_username_and_role__DoD4(db_engine: Engine) -> None:
    """DoD-4 — the plain result carries the new administrator's id, username and role."""
    result = _bootstrap(db_engine, _FixedIdGenerator(4_000_000_000_005))
    assert isinstance(result, BootstrapResult)
    assert result.id == 4_000_000_000_005
    assert result.username == USERNAME
    assert result.role == Role.ADMIN
    assert _user_rows(db_engine)[0]["id"] == result.id


def test_creation_leaves_the_instance_configured__DoD4(db_engine: Engine) -> None:
    """DoD-4 — after creation the one definition of the fact answers true."""
    _bootstrap(db_engine, _FixedIdGenerator(4_000_000_000_006))
    with db_engine.connect() as connection:
        assert is_configured(connection) is True


# --- DoD-5: the stored hash verifies through step 001's seam -------------------------


def test_stored_hash_verifies_against_the_supplied_password__DoD5(db_engine: Engine) -> None:
    """DoD-5 — `verify_password(stored_hash, password)` is true (US-001.AC-1)."""
    _bootstrap(db_engine, _FixedIdGenerator(5_000_000_000_001))
    stored = _user_rows(db_engine)[0]["password_hash"]
    assert verify_password(stored, PASSWORD) is True


def test_stored_hash_fails_against_a_different_password__DoD5(db_engine: Engine) -> None:
    """DoD-5 — the same stored hash rejects a different password."""
    _bootstrap(db_engine, _FixedIdGenerator(5_000_000_000_002))
    stored = _user_rows(db_engine)[0]["password_hash"]
    assert verify_password(stored, OTHER_PASSWORD) is False


# --- DoD-6: refusal when already configured, database untouched ----------------------


def _seed_configured_instance(engine: Engine) -> None:
    _apply_registry(engine)
    _insert_user(engine, user_id=601, username="original-admin", role=Role.ADMIN, password_hash=EXISTING_ADMIN_HASH)
    _insert_user(engine, user_id=602, username="some-reader", role=Role.ROLEPLAYER)


def test_creation_raises_already_configured_when_configured__DoD6(db_engine: Engine) -> None:
    """DoD-6 — a configured instance refuses with `already_configured` (US-003.AC-1)."""
    _seed_configured_instance(db_engine)
    with pytest.raises(AlreadyConfiguredError):
        _bootstrap(db_engine, _FixedIdGenerator(6_000_000_000_001), username="intruder")


def test_refused_creation_leaves_the_row_count_unchanged__DoD6(db_engine: Engine) -> None:
    """DoD-6 — the refused call adds no row."""
    _seed_configured_instance(db_engine)
    before = len(_user_rows(db_engine))
    with pytest.raises(AlreadyConfiguredError):
        _bootstrap(db_engine, _FixedIdGenerator(6_000_000_000_002), username="intruder")
    assert len(_user_rows(db_engine)) == before == 2


def test_refused_creation_leaves_the_existing_admin_hash_unchanged__DoD6(db_engine: Engine) -> None:
    """DoD-6 — the existing administrator's stored hash (and identity) are untouched."""
    _seed_configured_instance(db_engine)
    with pytest.raises(AlreadyConfiguredError):
        _bootstrap(db_engine, _FixedIdGenerator(6_000_000_000_003), username="original-admin")
    admins = [row for row in _user_rows(db_engine) if row["role"] == Role.ADMIN]
    assert len(admins) == 1
    assert admins[0]["id"] == 601
    assert admins[0]["username"] == "original-admin"
    assert admins[0]["password_hash"] == EXISTING_ADMIN_HASH
    assert all(row["id"] != 6_000_000_000_003 for row in _user_rows(db_engine))


# --- DoD-7: atomicity, provoked through the operation's own inputs -------------------
#
# Lever: the instance is *not* configured (only a roleplayer exists), so the operation
# passes its own re-check, applies the registry, mints and hashes — and then its insert
# collides with the table's own UNIQUE constraint on `username`. The observable claim is
# that no administrator row survives.


def _seed_unconfigured_instance_with_username(engine: Engine, username: str) -> None:
    _apply_registry(engine)
    _insert_user(engine, user_id=701, username=username, role=Role.ROLEPLAYER)


def _attempt_colliding_bootstrap(connection: Connection, username: str) -> bool:
    """Run the operation with a username the table rejects; True when it raised."""
    try:
        create_first_administrator(connection, _FixedIdGenerator(7_000_000_000_001), username, PASSWORD)
    except Exception:
        return True
    return False


def test_failed_insert_raises_rather_than_reporting_success__DoD7(db_engine: Engine) -> None:
    """DoD-7 — a username the table's constraints reject makes the operation fail."""
    _seed_unconfigured_instance_with_username(db_engine, "taken")
    with db_engine.connect() as connection:
        assert _attempt_colliding_bootstrap(connection, "taken") is True


def test_failed_insert_leaves_no_administrator_on_the_same_connection__DoD7(db_engine: Engine) -> None:
    """DoD-7 — the connection the operation ran on sees no administrator row afterwards."""
    _seed_unconfigured_instance_with_username(db_engine, "taken")
    with db_engine.connect() as connection:
        _attempt_colliding_bootstrap(connection, "taken")
        assert _admin_row_count_on(connection) == 0


def test_failed_insert_leaves_no_administrator_in_the_database__DoD7(db_engine: Engine) -> None:
    """DoD-7 — nothing partially bootstrapped is observable from a fresh connection either."""
    _seed_unconfigured_instance_with_username(db_engine, "taken")
    with db_engine.connect() as connection:
        _attempt_colliding_bootstrap(connection, "taken")
    with db_engine.connect() as fresh:
        assert _admin_row_count_on(fresh) == 0
        assert is_configured(fresh) is False
    rows = _user_rows(db_engine)
    assert [(row["id"], row["username"], row["role"]) for row in rows] == [(701, "taken", Role.ROLEPLAYER)]


# DoD-7 (strengthened) — "atomic, schema included". Lever: the database starts with NO
# schema, so nothing can collide; the failure is provoked through the generator
# parameter — a supplied generator that fails when asked to mint. The mint comes after
# the registry is applied, so a rollback that did not cover DDL would leave tables
# behind. Outcome asserted: no registry table and no administrator row, on the same
# connection and on a fresh one; the same connection then still serves a successful
# creation with a working generator.


class _MintFailure(Exception):
    """Raised by the failing generator stand-in; unrelated to anything in the app."""


class _FailingIdGenerator:
    """A generator stand-in whose ``next_id()`` always fails."""

    def next_id(self) -> int:
        raise _MintFailure("simulated id-generator failure")


def _registry_tables_on(connection: Connection) -> set[str]:
    """Registry table names present in the catalogue as seen on ``connection``."""
    rows = connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type = 'table'").all()
    return {row[0] for row in rows} & set(schema.metadata.tables)


def _attempt_failing_mint(connection: Connection) -> bool:
    """Run the operation with a generator that fails; True when the operation raised."""
    try:
        create_first_administrator(connection, _FailingIdGenerator(), USERNAME, PASSWORD)
    except Exception:
        return True
    return False


def test_failing_generator_makes_the_creation_raise__S002_DoD7(db_engine: Engine) -> None:
    """DoD-7 — on a no-schema database a generator that fails to mint makes the operation fail."""
    with db_engine.connect() as connection:
        assert _attempt_failing_mint(connection) is True


def test_failed_mint_on_no_schema_leaves_no_registry_table_on_the_same_connection__S002_DoD7(
    db_engine: Engine,
) -> None:
    """DoD-7 — the connection the operation ran on sees no registry table and no admin row."""
    assert _table_names(db_engine) & set(schema.metadata.tables) == set()
    with db_engine.connect() as connection:
        _attempt_failing_mint(connection)
        assert _registry_tables_on(connection) == set()
        assert _admin_row_count_on(connection) == 0


def test_failed_mint_on_no_schema_leaves_no_registry_table_on_a_fresh_connection__S002_DoD7(
    db_engine: Engine,
) -> None:
    """DoD-7 — a freshly acquired connection sees no registry table and no admin row either."""
    with db_engine.connect() as connection:
        _attempt_failing_mint(connection)
    with db_engine.connect() as fresh:
        assert _registry_tables_on(fresh) == set()
        assert _admin_row_count_on(fresh) == 0
        assert is_configured(fresh) is False
    assert _table_names(db_engine) & set(schema.metadata.tables) == set()


def test_same_connection_still_creates_after_a_failed_mint__S002_DoD7(db_engine: Engine) -> None:
    """DoD-7 — afterwards the same connection is usable: a working generator's creation succeeds."""
    with db_engine.connect() as connection:
        assert _attempt_failing_mint(connection) is True
        result = create_first_administrator(connection, _FixedIdGenerator(7_000_000_000_002), USERNAME, PASSWORD)
    assert isinstance(result, BootstrapResult)
    assert result.id == 7_000_000_000_002
    assert result.username == USERNAME
    assert result.role == Role.ADMIN
    assert set(schema.metadata.tables) <= _table_names(db_engine)
    rows = _user_rows(db_engine)
    assert [(row["id"], row["username"], row["role"]) for row in rows] == [
        (7_000_000_000_002, USERNAME, Role.ADMIN)
    ]
    with db_engine.connect() as fresh:
        assert is_configured(fresh) is True


# --- DoD-8: the id comes from the generator it is given ------------------------------


@pytest.mark.parametrize("given_id", [8_111_111_111_111_111, 8_222_222_222_222])
def test_creation_mints_the_id_from_the_given_generator__DoD8(db_engine: Engine, given_id: int) -> None:
    """DoD-8 — two different generators yield their own ids on the result and in the row."""
    result = _bootstrap(db_engine, _FixedIdGenerator(given_id))
    assert result.id == given_id
    assert [row["id"] for row in _user_rows(db_engine)] == [given_id]


def test_creation_uses_a_real_given_generator_and_not_another__DoD8(db_engine: Engine) -> None:
    """DoD-8 — with a real `SnowflakeGenerator`, the id is what that generator's sequence yields.

    A twin built with the same node id and the same frozen clock predicts the value; any
    other generator (a process-wide one, a fresh one with a live clock) would not match.
    """
    given = _real_generator(node_id=37)
    twin = _real_generator(node_id=37)
    expected = twin.next_id()
    result = _bootstrap(db_engine, given)
    assert result.id == expected
    assert [row["id"] for row in _user_rows(db_engine)] == [expected]


def test_module_holds_no_process_wide_generator__DoD8() -> None:
    """DoD-8 — nothing in the module is a generator instance it could reach for instead."""
    held = [name for name, value in vars(bootstrap_module).items() if isinstance(value, SnowflakeGenerator)]
    assert held == []


# --- DoD-10: health's `configured` and the predicate cannot disagree -----------------

_SCENARIOS = [
    # (users table present?, other registry tables present?, admin row?, roleplayer row?)
    pytest.param(False, False, False, False, id="no-tables"),
    pytest.param(True, False, False, False, id="users-only-empty"),
    pytest.param(True, False, False, True, id="users-only-roleplayer"),
    pytest.param(True, False, True, False, id="users-only-admin"),
    pytest.param(True, True, False, False, id="full-registry-empty"),
    pytest.param(True, True, False, True, id="full-registry-roleplayer"),
    pytest.param(True, True, True, False, id="full-registry-admin"),
    pytest.param(True, True, True, True, id="full-registry-admin-and-roleplayer"),
]


@pytest.mark.parametrize(("users_table", "full_registry", "admin", "roleplayer"), _SCENARIOS)
@pytest.mark.parametrize("registry_kind", ["production", "empty"])
def test_probe_configured_equals_the_predicate__DoD10(
    db_engine: Engine,
    users_table: bool,
    full_registry: bool,
    admin: bool,
    roleplayer: bool,
    registry_kind: str,
) -> None:
    """DoD-10 — table present/absent × administrator present/absent: probe and predicate agree."""
    if full_registry:
        _apply_registry(db_engine)
    elif users_table:
        _create_users_table_only(db_engine)
    if admin:
        _insert_user(db_engine, user_id=1001, username="founder", role=Role.ADMIN)
    if roleplayer:
        _insert_user(db_engine, user_id=1002, username="reader", role=Role.ROLEPLAYER)
    registry = schema.metadata if registry_kind == "production" else MetaData()

    with db_engine.connect() as connection:
        predicate_answer = is_configured(connection)
        probe_answer = probe_health(connection, registry).configured

    assert probe_answer == predicate_answer
    # And both equal the D3 definition: a users table holding at least one admin row.
    assert predicate_answer is (users_table and admin)


# --- DoD-11: no fastapi, no status codes, no Request ----------------------------------


def _module_tree() -> ast.Module:
    return ast.parse(inspect.getsource(bootstrap_module))


def test_module_imports_no_fastapi_or_starlette__DoD11() -> None:
    """DoD-11 — no `fastapi` (or its `starlette` base) import anywhere in the module."""
    imported: list[str] = []
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
    offenders = [name for name in imported if name.split(".")[0] in {"fastapi", "starlette"}]
    assert offenders == []


def test_module_binds_no_fastapi_symbol__DoD11() -> None:
    """DoD-11 — no module-level name is a fastapi/starlette object."""
    offenders = []
    for name, value in vars(bootstrap_module).items():
        origin = getattr(value, "__module__", None) or getattr(value, "__name__", "")
        if isinstance(origin, str) and origin.split(".")[0] in {"fastapi", "starlette"}:
            offenders.append(name)
    assert offenders == []


def test_module_references_no_http_status_code__DoD11() -> None:
    """DoD-11 — no HTTP status literal and no status-code vocabulary in the service."""
    status_words = {"HTTPStatus", "HTTPException", "status_code", "http_status"}
    literal_statuses: list[int] = []
    status_names: list[str] = []
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Constant) and type(node.value) is int and 100 <= node.value <= 599:
            literal_statuses.append(node.value)
        elif isinstance(node, ast.Name) and (node.id in status_words or node.id.startswith("HTTP_")):
            status_names.append(node.id)
        elif isinstance(node, ast.Attribute) and (node.attr in status_words or node.attr.startswith("HTTP_")):
            status_names.append(node.attr)
    assert literal_statuses == []
    assert status_names == []


@pytest.mark.parametrize(
    ("function", "expected_parameters"),
    [
        pytest.param(is_configured, ["connection"], id="is_configured"),
        pytest.param(
            create_first_administrator,
            ["connection", "generator", "username", "password"],
            id="create_first_administrator",
        ),
    ],
)
def test_entry_points_take_no_request__DoD11(function: Callable[..., Any], expected_parameters: list[str]) -> None:
    """DoD-11 — plain parameters only; no `Request`, no fastapi/starlette type in the contract."""
    signature = inspect.signature(function)
    assert list(signature.parameters) == expected_parameters
    rendered = " ".join(str(parameter) for parameter in signature.parameters.values())
    rendered = f"{rendered} {signature.return_annotation}"
    assert "fastapi" not in rendered.lower()
    assert "starlette" not in rendered.lower()
    assert "Request" not in rendered


def test_creation_is_callable_with_a_connection_a_generator_and_two_strings__DoD11(db_engine: Engine) -> None:
    """DoD-11 — a plain Core connection, a generator and two `str`s are all it needs."""
    with db_engine.connect() as connection:
        result = create_first_administrator(connection, _real_generator(node_id=3), "plain-name", "plain-secret")
    assert isinstance(result, BootstrapResult)
    assert result.username == "plain-name"
