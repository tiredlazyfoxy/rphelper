"""Step 006 — `GET /api/health` and the health probe service.

Covers DoD-1 (the response's exact key set), DoD-2 (the empty-registry answer), DoD-3
(`schema` really reads `sqlite_master`), DoD-4 (the `status` roll-up's precedence),
DoD-5 (`configured`), DoD-6 (no authentication) and DoD-7 (the probe's plain,
FastAPI-free contract).

DoD-8..DoD-11 live in `test_main.py`. DoD-12, DoD-13 and DoD-14 are `[manual/live]`
and carry no test here.

Every expected value comes from `006.app-factory-and-health.md`, `006.context.md` and
decision D3 in the feature's `context.md`. The administrator role's stored value is
`'admin'` — `data-model.md` § `users` gives the column as `'roleplayer' | 'admin'` and
names the first-run account as the `admin` one.

All DDL here is test-local: a throwaway `users` table and throwaway registry tables in
throwaway `MetaData` objects. Nothing is added to `app/db/schema.py`'s registry.

Feature 003, step 002 (`002.bootstrap-service-and-error.md`) extends this file with its
DoD-9 (tests suffixed `S002_DoD9`): the fresh-database expectation is corrected per that
feature's context D5, and a bootstrapped database (the production registry applied plus
one administrator row) must report all-clear.

Feature 007, step 002 (`002.comparison-walk-and-health-drift.md`) extends this file with its
DoD-11..DoD-17 (tests suffixed `S007_002_DoD<n>`): the `schema` roll-up gains its `"drift"`
branch — `missing` when a declared table is absent, `drift` when all are present and one
differs, `ok` otherwise — with the `status` precedence and the one-word, table-free body
unchanged. Drift is produced by hand-written DDL on the per-test file; the registry is never
edited. Every earlier test in this file is left as it was (step 002 DoD-11).
"""

import ast
import dataclasses
import inspect
from collections.abc import Callable, Iterator
from types import ModuleType

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, Connection, Engine, Index, Integer, MetaData, Table, Text

import app.routers.health as health_router
import app.services.health as health_service
from app.config import Settings, get_settings
from app.db import schema
from app.main import create_app
from app.roles import Role
from app.services.health import HealthProbeResult, probe_health

ADMIN_ROLE = "admin"
ROLEPLAYER_ROLE = "roleplayer"

ABSENT_TABLE = "probe_absent_table"
PRESENT_TABLE = "probe_present_table"
SECOND_PRESENT_TABLE = "probe_second_present_table"

USERS_DDL = (
    "CREATE TABLE users ("
    " id INTEGER PRIMARY KEY,"
    " username TEXT NOT NULL UNIQUE,"
    " password_hash TEXT NOT NULL,"
    " role TEXT NOT NULL,"
    " is_enabled INTEGER NOT NULL DEFAULT 1)"
)


@pytest.fixture(autouse=True)
def _quiet_factory_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the factory's one logging call so these tests touch no global sinks.

    `app.main.configure_logging` is the patchable seam the step `006` freeze record
    names. Whether it is called at all is DoD-8's subject, not this file's.
    """
    monkeypatch.setattr("app.main.configure_logging", lambda settings: None)


@pytest.fixture
def health_client(db_settings: Settings, db_engine: Engine) -> Iterator[TestClient]:
    """An application built by the factory, pinned to the per-test database.

    Settings are pinned through `dependency_overrides`, never by mutating a global.
    `TestClient` is deliberately **not** used as a context manager: the lifespan is
    DoD-11's subject and is irrelevant to the endpoint's answer.
    """
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: db_settings
    with db_engine.connect() as connection:
        connection.exec_driver_sql("SELECT 1")
    try:
        yield TestClient(application)
    finally:
        application.dependency_overrides.clear()


def _registry_with(*table_names: str) -> MetaData:
    """A throwaway registry holding one trivial table per name."""
    registry = MetaData()
    for table_name in table_names:
        Table(table_name, registry, Column("id", Integer, primary_key=True))
    return registry


def _create_registry_tables(connection: Connection, registry: MetaData) -> None:
    registry.create_all(connection)
    connection.commit()


def _create_users_table(connection: Connection) -> None:
    connection.exec_driver_sql(USERS_DDL)
    connection.commit()


def _insert_user(connection: Connection, username: str, role: str) -> None:
    connection.exec_driver_sql(
        "INSERT INTO users (username, password_hash, role, is_enabled) VALUES (?, ?, ?, 1)",
        (username, "not-a-real-hash", role),
    )
    connection.commit()


# --- DoD-1: the response's exact key set --------------------------------------------


def test_health_answers_200__DoD1(health_client: TestClient) -> None:
    """DoD-1 — `GET /api/health` answers 200."""
    assert health_client.get("/api/health").status_code == 200


def test_health_body_carries_exactly_the_three_named_keys__DoD1(health_client: TestClient) -> None:
    """DoD-1 — the body's keys are literally `status`, `configured` and `schema`, nothing more."""
    body = health_client.get("/api/health").json()
    assert set(body) == {"status", "configured", "schema"}


def test_health_body_spells_the_schema_key_without_a_trailing_underscore__DoD1(health_client: TestClient) -> None:
    """DoD-1 — the wire key is `schema`; no `schema_` and no other spelling leaks out."""
    body = health_client.get("/api/health").json()
    assert "schema" in body
    assert "schema_" not in body


# --- DoD-2: the fresh-database answer -----------------------------------------------
#
# Corrected by feature 003, step 002, DoD-9 (feature context D5): the production registry
# now declares `users`, so a fresh database has a missing registry table. It therefore
# reports `schema: "missing"`, `configured: false` and — by 001's unchanged precedence —
# `status: "degraded"`. The 001-era "ok" / "unconfigured" expectations no longer hold.


def test_fresh_database_reports_schema_missing__DoD2__S002_DoD9(health_client: TestClient) -> None:
    """003/002 DoD-9 — no `users` table exists yet, so a registry table is absent: `"missing"`."""
    assert health_client.get("/api/health").json()["schema"] == "missing"


def test_fresh_database_reports_configured_false__DoD2__S002_DoD9(health_client: TestClient) -> None:
    """003/002 DoD-9 — no `users` table exists, so `configured` is `false`."""
    assert health_client.get("/api/health").json()["configured"] is False


def test_fresh_database_reports_status_degraded__DoD2__S002_DoD9(health_client: TestClient) -> None:
    """003/002 DoD-9 — a `"missing"` schema rolls up to `"degraded"` (D5: the roll-up is not re-decided)."""
    assert health_client.get("/api/health").json()["status"] == "degraded"


# --- Feature 003, step 002, DoD-9: a bootstrapped database reports all-clear ---------


def _bootstrap_production_schema_with_one_admin(engine: Engine) -> None:
    """Create every table of the production registry and insert one administrator row."""
    with engine.connect() as connection:
        schema.metadata.create_all(connection)
        connection.execute(
            schema.users.insert().values(
                id=1234567890123,
                username="founder",
                password_hash="not-a-real-hash",
                role=Role.ADMIN,
                is_enabled=True,
                rp_language=None,
                preferred_language=None,
                created_at="2026-01-01T00:00:00+00:00",
                updated_at="2026-01-01T00:00:00+00:00",
            )
        )
        connection.commit()


def test_bootstrapped_database_reports_configured_true__S002_DoD9(
    health_client: TestClient, db_engine: Engine
) -> None:
    """003/002 DoD-9 — every registry table plus one administrator: `configured` is `true`."""
    _bootstrap_production_schema_with_one_admin(db_engine)
    assert health_client.get("/api/health").json()["configured"] is True


def test_bootstrapped_database_reports_schema_ok__S002_DoD9(health_client: TestClient, db_engine: Engine) -> None:
    """003/002 DoD-9 — every registry table present: `schema` is `"ok"`."""
    _bootstrap_production_schema_with_one_admin(db_engine)
    assert health_client.get("/api/health").json()["schema"] == "ok"


def test_bootstrapped_database_reports_status_ok__S002_DoD9(health_client: TestClient, db_engine: Engine) -> None:
    """003/002 DoD-9 — `"ok"` schema and `configured` true roll up to `"ok"`."""
    _bootstrap_production_schema_with_one_admin(db_engine)
    body = health_client.get("/api/health").json()
    assert body == {"status": "ok", "configured": True, "schema": "ok"}


# --- DoD-3: `schema` is a real `sqlite_master` read ----------------------------------


def test_probe_reports_missing_when_a_registry_table_is_absent__DoD3(db_engine: Engine) -> None:
    """DoD-3 — a table declared in the supplied registry but absent from the database is `"missing"`."""
    registry = _registry_with(ABSENT_TABLE)
    with db_engine.connect() as connection:
        result = probe_health(connection, registry)
    assert result.schema == "missing"


def test_probe_reports_ok_when_every_registry_table_is_present__DoD3(db_engine: Engine) -> None:
    """DoD-3 — with every table of the supplied registry created, `schema` is `"ok"`."""
    registry = _registry_with(PRESENT_TABLE, SECOND_PRESENT_TABLE)
    with db_engine.connect() as connection:
        _create_registry_tables(connection, registry)
        result = probe_health(connection, registry)
    assert result.schema == "ok"


def test_probe_reports_missing_when_only_some_registry_tables_are_present__DoD3(db_engine: Engine) -> None:
    """DoD-3 — *any* absent table makes it `"missing"`, not just an entirely empty database."""
    present_only = _registry_with(PRESENT_TABLE)
    registry = _registry_with(PRESENT_TABLE, ABSENT_TABLE)
    with db_engine.connect() as connection:
        _create_registry_tables(connection, present_only)
        result = probe_health(connection, registry)
    assert result.schema == "missing"


# --- DoD-4: the `status` roll-up's precedence ---------------------------------------


def test_non_ok_schema_rolls_up_to_degraded_while_unconfigured__DoD4(db_engine: Engine) -> None:
    """DoD-4 — a non-`"ok"` schema gives `"degraded"` when `configured` is false."""
    registry = _registry_with(ABSENT_TABLE)
    with db_engine.connect() as connection:
        result = probe_health(connection, registry)
    assert result.schema != "ok"
    assert result.configured is False
    assert result.status == "degraded"


def test_non_ok_schema_rolls_up_to_degraded_even_when_configured__DoD4(db_engine: Engine) -> None:
    """DoD-4 — a non-`"ok"` schema gives `"degraded"` *regardless* of `configured`."""
    registry = _registry_with(ABSENT_TABLE)
    with db_engine.connect() as connection:
        _create_users_table(connection)
        _insert_user(connection, "founder", ADMIN_ROLE)
        result = probe_health(connection, registry)
    assert result.schema != "ok"
    assert result.configured is True
    assert result.status == "degraded"


def test_ok_schema_with_configured_false_rolls_up_to_unconfigured__DoD4(db_engine: Engine) -> None:
    """DoD-4 — an `"ok"` schema with `configured` false gives `"unconfigured"`."""
    with db_engine.connect() as connection:
        result = probe_health(connection, MetaData())
    assert result.schema == "ok"
    assert result.configured is False
    assert result.status == "unconfigured"


def test_ok_schema_with_configured_true_rolls_up_to_ok__DoD4(db_engine: Engine) -> None:
    """DoD-4 — an `"ok"` schema with `configured` true gives `"ok"`."""
    with db_engine.connect() as connection:
        _create_users_table(connection)
        _insert_user(connection, "founder", ADMIN_ROLE)
        result = probe_health(connection, MetaData())
    assert result.schema == "ok"
    assert result.configured is True
    assert result.status == "ok"


# --- DoD-5: `configured` ------------------------------------------------------------


def test_configured_is_false_without_a_users_table__DoD5(db_engine: Engine) -> None:
    """DoD-5 — no `users` table at all means `configured` is false."""
    with db_engine.connect() as connection:
        result = probe_health(connection, MetaData())
    assert result.configured is False


def test_configured_is_false_for_a_present_but_empty_users_table__DoD5(db_engine: Engine) -> None:
    """DoD-5 — a present-but-empty `users` table still reports false."""
    with db_engine.connect() as connection:
        _create_users_table(connection)
        result = probe_health(connection, MetaData())
    assert result.configured is False


def test_configured_is_false_when_no_row_is_an_administrator__DoD5(db_engine: Engine) -> None:
    """DoD-5 — rows alone are not enough; at least one must be an administrator."""
    with db_engine.connect() as connection:
        _create_users_table(connection)
        _insert_user(connection, "reader", ROLEPLAYER_ROLE)
        result = probe_health(connection, MetaData())
    assert result.configured is False


def test_configured_is_true_with_one_administrator_row__DoD5(db_engine: Engine) -> None:
    """DoD-5 — a `users` table holding at least one administrator row makes it true."""
    with db_engine.connect() as connection:
        _create_users_table(connection)
        _insert_user(connection, "founder", ADMIN_ROLE)
        result = probe_health(connection, MetaData())
    assert result.configured is True


def test_configured_is_true_when_an_administrator_sits_among_other_roles__DoD5(db_engine: Engine) -> None:
    """DoD-5 — "at least one" — a single administrator among other accounts suffices."""
    with db_engine.connect() as connection:
        _create_users_table(connection)
        _insert_user(connection, "reader", ROLEPLAYER_ROLE)
        _insert_user(connection, "founder", ADMIN_ROLE)
        result = probe_health(connection, MetaData())
    assert result.configured is True


# --- DoD-6: no authentication -------------------------------------------------------


def test_health_answers_with_no_cookie_and_no_credentials__DoD6(health_client: TestClient) -> None:
    """DoD-6 — sent with no cookie jar and no credential header, the endpoint still answers 200."""
    health_client.cookies.clear()
    response = health_client.get("/api/health")
    assert not health_client.cookies
    assert response.status_code == 200
    assert response.status_code not in (401, 403)
    assert "www-authenticate" not in {name.lower() for name in response.headers}


def test_health_declares_no_security_requirement__DoD6(health_client: TestClient) -> None:
    """DoD-6 — the published contract for the route carries no security requirement."""
    schema = health_client.get("/openapi.json").json()
    operation = schema["paths"]["/api/health"]["get"]
    assert not operation.get("security")


# --- DoD-7: the probe's plain, FastAPI-free contract --------------------------------


def test_probe_takes_exactly_a_connection_and_a_registry__DoD7() -> None:
    """DoD-7 — two parameters, `connection` then `registry`, and nothing else."""
    assert list(inspect.signature(probe_health).parameters) == ["connection", "registry"]


def test_probe_is_callable_with_no_fastapi_application_in_sight__DoD7(db_engine: Engine) -> None:
    """DoD-7 — a plain Core connection and a plain `MetaData` are sufficient to call it."""
    with db_engine.connect() as connection:
        result = probe_health(connection, MetaData())
    assert isinstance(result, HealthProbeResult)


def test_probe_result_carries_the_three_reported_values_and_no_http_status__DoD7(db_engine: Engine) -> None:
    """DoD-7 — the plain result reports the three values; no status code lives on it."""
    with db_engine.connect() as connection:
        result = probe_health(connection, MetaData())
    assert {field.name for field in dataclasses.fields(result)} == {"status", "configured", "schema"}
    assert not hasattr(result, "status_code")
    assert not hasattr(result, "http_status")
    assert not hasattr(result, "request")


def test_probe_contract_names_no_fastapi_type__DoD7() -> None:
    """DoD-7 — no FastAPI application, no `Request` and no HTTP status in the signature."""
    signature = inspect.signature(probe_health)
    rendered = " ".join(str(annotation) for annotation in signature.parameters.values())
    rendered = f"{rendered} {signature.return_annotation}"
    assert "fastapi" not in rendered.lower()
    assert "starlette" not in rendered.lower()
    assert "Request" not in rendered
    assert "Response" not in rendered


# =====================================================================================
# Feature 007, step 002 — the `"drift"` branch of the `schema` roll-up
# =====================================================================================

DRIFT_TABLE = "probe_drift_table"
INDEXED_TABLE = "probe_indexed_table"
DRIFT_EXTRA_COLUMN = "probe_leftover_column"

# The in-sync hand-written spelling of a `_registry_with(...)` table: `id INTEGER`, NOT NULL, PK.
IN_SYNC_DRIFT_TABLE_DDL = f"CREATE TABLE {DRIFT_TABLE} (id INTEGER NOT NULL PRIMARY KEY)"
EXTRA_COLUMN_DRIFT_TABLE_DDL = (
    f"CREATE TABLE {DRIFT_TABLE} (id INTEGER NOT NULL PRIMARY KEY, {DRIFT_EXTRA_COLUMN} TEXT)"
)
RETYPED_DRIFT_TABLE_DDL = f"CREATE TABLE {DRIFT_TABLE} (id TEXT NOT NULL PRIMARY KEY)"


def _run_ddl(engine: Engine, *statements: str) -> None:
    """Hand-written DDL on the per-test SQLite file, committed."""
    with engine.connect() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
        connection.commit()


def _indexed_registry() -> MetaData:
    """A throwaway registry with one table carrying an explicit index and a unique column."""
    registry = MetaData()
    Table(
        INDEXED_TABLE,
        registry,
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("label", Text, nullable=False, unique=True),
        Column("tag", Text, nullable=True),
        Index("ix_probe_indexed_table_tag", "tag"),
    )
    return registry


def _drift_production_users_table(engine: Engine) -> None:
    """Hand-drift the production `users` table by adding a column the registry does not declare."""
    _run_ddl(engine, f"ALTER TABLE users ADD COLUMN {DRIFT_EXTRA_COLUMN} TEXT")


# --- 007/002 DoD-11: `missing` is unchanged for the same input ------------------------


def test_absent_declared_table_still_reports_missing__S007_002_DoD11(db_engine: Engine) -> None:
    """007/002 DoD-11 — a declared table absent from the file reports `"missing"`, exactly as
    feature 001's presence test did for the same input."""
    registry = _registry_with(ABSENT_TABLE)
    with db_engine.connect() as connection:
        result = probe_health(connection, registry)
    assert result.schema == "missing"
    assert result.status == "degraded"


def test_partially_present_registry_still_reports_missing__S007_002_DoD11(db_engine: Engine) -> None:
    """007/002 DoD-11 — one registry table present and in sync, another absent: `"missing"`,
    as before the widening."""
    present_only = _registry_with(PRESENT_TABLE)
    registry = _registry_with(PRESENT_TABLE, ABSENT_TABLE)
    with db_engine.connect() as connection:
        _create_registry_tables(connection, present_only)
        result = probe_health(connection, registry)
    assert result.schema == "missing"


def test_fresh_database_against_the_production_registry_reports_missing__S007_002_DoD11(
    db_engine: Engine,
) -> None:
    """007/002 DoD-11 — a fresh file probed with the production registry is `"missing"`."""
    with db_engine.connect() as connection:
        result = probe_health(connection, schema.metadata)
    assert result.schema == "missing"


# --- 007/002 DoD-12: `drift` when every table is present and one differs --------------


@pytest.mark.parametrize(
    "drifted_ddl",
    [EXTRA_COLUMN_DRIFT_TABLE_DDL, RETYPED_DRIFT_TABLE_DDL],
    ids=["extra-column", "changed-type"],
)
def test_present_but_differing_table_reports_drift__S007_002_DoD12(db_engine: Engine, drifted_ddl: str) -> None:
    """007/002 DoD-12 — the only declared table is present but differs (an extra column, or a
    changed type): `schema` is `"drift"`."""
    registry = _registry_with(DRIFT_TABLE)
    _run_ddl(db_engine, drifted_ddl)
    with db_engine.connect() as connection:
        result = probe_health(connection, registry)
    assert result.schema == "drift"


def test_missing_declared_index_reports_drift__S007_002_DoD12(db_engine: Engine) -> None:
    """007/002 DoD-12 — every column matches but a declared index is absent: `"drift"`."""
    registry = _indexed_registry()
    _run_ddl(
        db_engine,
        f"CREATE TABLE {INDEXED_TABLE} (id INTEGER NOT NULL PRIMARY KEY, label TEXT NOT NULL UNIQUE, tag TEXT)",
    )
    with db_engine.connect() as connection:
        result = probe_health(connection, registry)
    assert result.schema == "drift"


def test_one_drifted_table_among_in_sync_tables_reports_drift__S007_002_DoD12(db_engine: Engine) -> None:
    """007/002 DoD-12 — all declared tables present, one in sync and one drifted: `"drift"`."""
    in_sync_part = _registry_with(PRESENT_TABLE)
    registry = _registry_with(PRESENT_TABLE, DRIFT_TABLE)
    with db_engine.connect() as connection:
        _create_registry_tables(connection, in_sync_part)
    _run_ddl(db_engine, EXTRA_COLUMN_DRIFT_TABLE_DDL)
    with db_engine.connect() as connection:
        result = probe_health(connection, registry)
    assert result.schema == "drift"


def test_endpoint_reports_drift_for_a_hand_drifted_production_table__S007_002_DoD12(
    health_client: TestClient, db_engine: Engine
) -> None:
    """007/002 DoD-12 — the production registry created and bootstrapped, then `users` given an
    undeclared column: `GET /api/health` answers `schema: "drift"`, `status: "degraded"`."""
    _bootstrap_production_schema_with_one_admin(db_engine)
    _drift_production_users_table(db_engine)
    body = health_client.get("/api/health").json()
    assert body == {"status": "degraded", "configured": True, "schema": "drift"}


# --- 007/002 DoD-13: `ok` for a database created from the registry -------------------


def test_registry_created_tables_report_ok__S007_002_DoD13(db_engine: Engine) -> None:
    """007/002 DoD-13 — tables created from the registry (including an explicit index and a
    `unique=True` column) report `schema: "ok"`."""
    registry = _indexed_registry()
    with db_engine.connect() as connection:
        _create_registry_tables(connection, registry)
        result = probe_health(connection, registry)
    assert result.schema == "ok"


def test_production_registry_created_fresh_reports_ok__S007_002_DoD13(db_engine: Engine) -> None:
    """007/002 DoD-13 — the production registry applied with `create_all`: `schema: "ok"`."""
    _bootstrap_production_schema_with_one_admin(db_engine)
    with db_engine.connect() as connection:
        result = probe_health(connection, schema.metadata)
    assert result.schema == "ok"


def test_hand_written_in_sync_table_reports_ok__S007_002_DoD13(db_engine: Engine) -> None:
    """007/002 DoD-13 — a hand-written table with exactly the declared shape is not drift."""
    registry = _registry_with(DRIFT_TABLE)
    _run_ddl(db_engine, IN_SYNC_DRIFT_TABLE_DDL)
    with db_engine.connect() as connection:
        result = probe_health(connection, registry)
    assert result.schema == "ok"


# --- 007/002 DoD-14: missing outranks drift ------------------------------------------


def test_missing_outranks_drift__S007_002_DoD14(db_engine: Engine) -> None:
    """007/002 DoD-14 — one declared table absent and another drifted: `"missing"`."""
    registry = _registry_with(DRIFT_TABLE, ABSENT_TABLE)
    _run_ddl(db_engine, EXTRA_COLUMN_DRIFT_TABLE_DDL)
    with db_engine.connect() as connection:
        result = probe_health(connection, registry)
    assert result.schema == "missing"
    assert result.status == "degraded"


def test_missing_outranks_drift_whatever_the_declaration_order__S007_002_DoD14(db_engine: Engine) -> None:
    """007/002 DoD-14 — the absent table declared after the drifted one or before it: `"missing"`."""
    _run_ddl(db_engine, EXTRA_COLUMN_DRIFT_TABLE_DDL)
    for registry in (_registry_with(ABSENT_TABLE, DRIFT_TABLE), _registry_with(DRIFT_TABLE, ABSENT_TABLE)):
        with db_engine.connect() as connection:
            result = probe_health(connection, registry)
        assert result.schema == "missing"


# --- 007/002 DoD-15: the `status` precedence is unchanged ----------------------------


def test_drift_rolls_up_to_degraded_while_unconfigured__S007_002_DoD15(db_engine: Engine) -> None:
    """007/002 DoD-15 — `schema: "drift"` with `configured` false gives `"degraded"`."""
    registry = _registry_with(DRIFT_TABLE)
    _run_ddl(db_engine, EXTRA_COLUMN_DRIFT_TABLE_DDL)
    with db_engine.connect() as connection:
        result = probe_health(connection, registry)
    assert (result.schema, result.configured, result.status) == ("drift", False, "degraded")


def test_drift_rolls_up_to_degraded_even_when_configured__S007_002_DoD15(db_engine: Engine) -> None:
    """007/002 DoD-15 — `schema: "drift"` with `configured` true still gives `"degraded"`."""
    registry = _registry_with(DRIFT_TABLE)
    _run_ddl(db_engine, EXTRA_COLUMN_DRIFT_TABLE_DDL)
    with db_engine.connect() as connection:
        _create_users_table(connection)
        _insert_user(connection, "founder", ADMIN_ROLE)
        result = probe_health(connection, registry)
    assert (result.schema, result.configured, result.status) == ("drift", True, "degraded")


def test_missing_rolls_up_to_degraded_even_when_configured__S007_002_DoD15(db_engine: Engine) -> None:
    """007/002 DoD-15 — `schema: "missing"` with `configured` true gives `"degraded"`."""
    registry = _registry_with(ABSENT_TABLE)
    with db_engine.connect() as connection:
        _create_users_table(connection)
        _insert_user(connection, "founder", ADMIN_ROLE)
        result = probe_health(connection, registry)
    assert (result.schema, result.configured, result.status) == ("missing", True, "degraded")


def test_in_sync_schema_while_unconfigured_rolls_up_to_unconfigured__S007_002_DoD15(db_engine: Engine) -> None:
    """007/002 DoD-15 — an in-sync registry table and no administrator gives `"unconfigured"`."""
    registry = _registry_with(DRIFT_TABLE)
    _run_ddl(db_engine, IN_SYNC_DRIFT_TABLE_DDL)
    with db_engine.connect() as connection:
        result = probe_health(connection, registry)
    assert (result.schema, result.configured, result.status) == ("ok", False, "unconfigured")


def test_in_sync_schema_while_configured_rolls_up_to_ok__S007_002_DoD15(db_engine: Engine) -> None:
    """007/002 DoD-15 — an in-sync registry table and an administrator gives `"ok"`."""
    registry = _registry_with(DRIFT_TABLE)
    _run_ddl(db_engine, IN_SYNC_DRIFT_TABLE_DDL)
    with db_engine.connect() as connection:
        _create_users_table(connection)
        _insert_user(connection, "founder", ADMIN_ROLE)
        result = probe_health(connection, registry)
    assert (result.schema, result.configured, result.status) == ("ok", True, "ok")


# --- 007/002 DoD-16: the body names no table, no column and no count -----------------


def _leave_fresh(engine: Engine) -> None:
    """No table at all: the `missing` state."""


def _bootstrap_then_drift(engine: Engine) -> None:
    """Production registry applied, one administrator, then `users` hand-drifted: `drift`."""
    _bootstrap_production_schema_with_one_admin(engine)
    _drift_production_users_table(engine)


HEALTH_STATES: list[tuple[str, Callable[[Engine], None], str]] = [
    ("missing", _leave_fresh, "missing"),
    ("drift", _bootstrap_then_drift, "drift"),
    ("ok", _bootstrap_production_schema_with_one_admin, "ok"),
]


@pytest.mark.parametrize(
    ("prepare", "expected_schema"),
    [(prepare, expected) for _, prepare, expected in HEALTH_STATES],
    ids=[state for state, _, _ in HEALTH_STATES],
)
def test_health_body_is_three_closed_values_and_names_nothing__S007_002_DoD16(
    health_client: TestClient,
    db_engine: Engine,
    prepare: Callable[[Engine], None],
    expected_schema: str,
) -> None:
    """007/002 DoD-16 — in every state the body is exactly `status`/`configured`/`schema`, each a
    closed one-word value (`schema` one of the three declared ones), with no table name, no
    column name and no number anywhere in it."""
    prepare(db_engine)
    response = health_client.get("/api/health")
    body = response.json()

    assert set(body) == {"status", "configured", "schema"}
    assert body["schema"] == expected_schema
    assert body["schema"] in {"ok", "drift", "missing"}
    assert body["status"] in {"ok", "unconfigured", "degraded"}
    assert isinstance(body["configured"], bool)

    raw = response.text
    assert not any(character.isdigit() for character in raw)
    assert DRIFT_EXTRA_COLUMN not in raw
    for table_name in schema.metadata.tables:
        assert table_name not in raw


# --- 007/002 DoD-17: the registry stays a parameter; the router is unchanged ---------


def test_probe_still_takes_a_connection_and_a_registry__S007_002_DoD17() -> None:
    """007/002 DoD-17 — the widened probe keeps exactly its two parameters."""
    assert list(inspect.signature(probe_health).parameters) == ["connection", "registry"]


def test_probe_answers_for_the_registry_it_is_given__S007_002_DoD17(db_engine: Engine) -> None:
    """007/002 DoD-17 — the registry is a real parameter: on one bootstrapped file, the production
    registry reports `"ok"`, a registry naming an absent table reports `"missing"`, and one
    naming a drifted table reports `"drift"`."""
    _bootstrap_production_schema_with_one_admin(db_engine)
    _run_ddl(db_engine, EXTRA_COLUMN_DRIFT_TABLE_DDL)
    with db_engine.connect() as connection:
        production = probe_health(connection, schema.metadata)
        absent = probe_health(connection, _registry_with(ABSENT_TABLE))
        drifted = probe_health(connection, _registry_with(DRIFT_TABLE))
    assert (production.schema, absent.schema, drifted.schema) == ("ok", "missing", "drift")


def _imported_module_names(module: ModuleType, package: str) -> list[str]:
    """Every module (and `module.name`) a module imports anywhere, relative imports resolved."""
    tree = ast.parse(inspect.getsource(module))
    package_parts = package.split(".")
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base_parts = package_parts[: len(package_parts) - (node.level - 1)]
                base = ".".join(base_parts + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            imported.append(base)
            imported.extend(f"{base}.{alias.name}" for alias in node.names)
    return imported


def test_health_service_imports_the_schema_registry_nowhere__S007_002_DoD17() -> None:
    """007/002 DoD-17 — `services/health.py` imports `app.db.schema` nowhere (module level or
    inside a function), and holds no `MetaData` of its own."""
    imported = _imported_module_names(health_service, "app.services")
    assert [name for name in imported if name == "app.db.schema" or name.startswith("app.db.schema.")] == []
    assert [name for name, value in vars(health_service).items() if isinstance(value, MetaData)] == []


def test_health_router_still_imports_the_registry_and_passes_it__S007_002_DoD17(
    health_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """007/002 DoD-17 — `routers/health.py` is unchanged in role: it still imports the registry
    from `app.db.schema` and hands that very object to `probe_health`."""
    assert "app.db.schema.metadata" in _imported_module_names(health_router, "app.routers")

    received: list[MetaData] = []
    real_probe = health_router.probe_health

    def spying_probe(connection: Connection, registry: MetaData) -> HealthProbeResult:
        received.append(registry)
        return real_probe(connection, registry)

    monkeypatch.setattr(health_router, "probe_health", spying_probe)
    assert health_client.get("/api/health").status_code == 200
    assert len(received) == 1
    assert received[0] is schema.metadata
