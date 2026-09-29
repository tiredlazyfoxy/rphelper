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
"""

import dataclasses
import inspect
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, Connection, Engine, Integer, MetaData, Table

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
