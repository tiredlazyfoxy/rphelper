"""Step 006 — the application factory and its lifespan.

Covers DoD-8 (`configure_logging` exactly once per factory call), DoD-9 (the one
snowflake generator on application state), DoD-10 (the domain-error handler is wired
into the factory) and DoD-11 (the lifespan runs no DDL).

DoD-1..DoD-7 live in `test_health.py`. DoD-12, DoD-13 and DoD-14 are `[manual/live]`
and carry no test here.

`app.main.configure_logging`, `app.main.build_id_generator` and
`app.main.register_exception_handlers` are imported into `app.main`'s namespace as
patchable seams (step `006` freeze record), so patching happens on `app.main`.

The module-level `app` object is deliberately **not** imported here: these clauses are
about the factory's behaviour, so each test builds its own application through
`create_app()`.
"""

from typing import Any

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine

from app.config import Settings, get_settings
from app.errors import SecretRefError
from app.ids import SnowflakeGenerator
from app.main import create_app

DOMAIN_ERROR_MESSAGE = "the secret pointer could not be resolved"
DOMAIN_ERROR_DETAIL = {"variable": "RPHELPER_A_MISSING_VARIABLE"}


@pytest.fixture(autouse=True)
def _quiet_factory_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the factory's logging call so no test here touches global sinks.

    DoD-8's own tests re-patch the same seam with a counter; `monkeypatch` undoes both
    at teardown, so nothing leaks into another test.
    """
    monkeypatch.setattr("app.main.configure_logging", lambda settings: None)


def _application_tables(connection: Connection) -> list[str]:
    """Every **application** table in `sqlite_master`, excluding SQLite's own objects."""
    rows = connection.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).scalars()
    return sorted(rows)


# --- DoD-8: `configure_logging` exactly once per factory call -----------------------


def test_factory_calls_configure_logging_exactly_once__DoD8(monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD-8 — one factory call produces exactly one `configure_logging` call."""
    calls: list[Settings] = []
    monkeypatch.setattr("app.main.configure_logging", lambda settings: calls.append(settings))
    create_app()
    assert len(calls) == 1


def test_factory_does_not_call_configure_logging_once_per_router__DoD8(monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD-8 — not zero times and not once per router: still exactly one."""
    calls: list[Settings] = []
    monkeypatch.setattr("app.main.configure_logging", lambda settings: calls.append(settings))
    application = create_app()
    assert len(application.routes) > 0
    assert len(calls) == 1


def test_two_factory_calls_configure_logging_twice__DoD8(monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD-8 — "per call": a second factory call adds exactly one more invocation."""
    calls: list[Settings] = []
    monkeypatch.setattr("app.main.configure_logging", lambda settings: calls.append(settings))
    create_app()
    assert len(calls) == 1
    create_app()
    assert len(calls) == 2


# --- DoD-9: one snowflake generator on application state ----------------------------


def test_application_state_holds_a_snowflake_generator__DoD9() -> None:
    """DoD-9 — the factory exposes the process's generator on application state."""
    application = create_app()
    assert isinstance(application.state.id_generator, SnowflakeGenerator)


def test_two_requests_observe_the_same_generator_instance__DoD9() -> None:
    """DoD-9 — the same instance serves both requests; it is not rebuilt per request."""
    application = create_app()
    seen: list[Any] = []

    @application.get("/_test/generator")
    def read_generator(request: Request) -> dict[str, bool]:
        seen.append(request.app.state.id_generator)
        return {"observed": True}

    client = TestClient(application)
    assert client.get("/_test/generator").status_code == 200
    assert client.get("/_test/generator").status_code == 200

    assert len(seen) == 2
    assert seen[0] is seen[1]
    assert seen[0] is application.state.id_generator


# --- DoD-10: the domain-error handler is wired into the factory ---------------------


def _application_raising_a_domain_error() -> TestClient:
    application = create_app()

    @application.get("/_test/domain-error")
    def raise_domain_error() -> dict[str, str]:
        raise SecretRefError(DOMAIN_ERROR_MESSAGE, DOMAIN_ERROR_DETAIL)

    return TestClient(application, raise_server_exceptions=False)


def test_domain_error_from_a_factory_built_route_uses_the_subclass_status__DoD10() -> None:
    """DoD-10 — the response status is `SecretRefError`'s own `http_status` (500)."""
    response = _application_raising_a_domain_error().get("/_test/domain-error")
    assert response.status_code == 500


def test_domain_error_from_a_factory_built_route_uses_the_wire_shape__DoD10() -> None:
    """DoD-10 — the body is the one wire shape: `error` holding `code`, `message`, `detail`."""
    body = _application_raising_a_domain_error().get("/_test/domain-error").json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "detail"}


def test_domain_error_wire_body_carries_the_errors_own_values__DoD10() -> None:
    """DoD-10 — the rendered code, message and detail are the raised error's."""
    body = _application_raising_a_domain_error().get("/_test/domain-error").json()
    assert body["error"]["code"] == "secret_ref_missing"
    assert body["error"]["message"] == DOMAIN_ERROR_MESSAGE
    assert body["error"]["detail"] == DOMAIN_ERROR_DETAIL


# --- DoD-11: the lifespan runs no DDL -----------------------------------------------


def test_lifespan_creates_no_application_table__DoD11(db_settings: Settings, db_engine: Engine) -> None:
    """DoD-11 — after startup against an empty database, `sqlite_master` holds no application table."""
    with db_engine.connect() as connection:
        assert _application_tables(connection) == []

    application = create_app()
    application.dependency_overrides[get_settings] = lambda: db_settings
    try:
        with TestClient(application):
            pass
    finally:
        application.dependency_overrides.clear()

    with db_engine.connect() as connection:
        assert _application_tables(connection) == []


def test_lifespan_creates_no_application_table_when_a_request_has_run__DoD11(
    db_settings: Settings, db_engine: Engine
) -> None:
    """DoD-11 — no create-if-missing convenience fires on the way through a request either."""
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: db_settings
    try:
        with TestClient(application) as client:
            assert client.get("/api/health").status_code == 200
    finally:
        application.dependency_overrides.clear()

    with db_engine.connect() as connection:
        assert _application_tables(connection) == []
