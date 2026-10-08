"""Tests for ``POST /api/bootstrap/create`` and the router-level ``require_unconfigured`` guard.

Every expected value comes from ``docs/plans/003.first-run-bootstrap/003.bootstrap-router-and-guard.md``
(Interface intent + Definition of done), ``003.context.md`` and the feature ``context.md``
(D2 the 409, D6 the router-level guard, D9 no cookie, D15 what the insert writes, D16 the
422 backstop). Bindings come from ``## Skeleton`` in ``status.md`` (steps 001, 002, 003).

Covers step 003 DoD-1 .. DoD-9. DoD-10 .. DoD-13 are ``[manual/live]`` and carry no test.

Feature 004 step 004 (``docs/plans/004.authentication-session/004.bootstrap-signs-in.md``)
makes the 201 set the session cookie: 003 DoD-2's ``Set-Cookie`` half is deleted and the
new tests (suffix ``__S004_004_DoD<n>``) cover 004/004 DoD-1, DoD-2, DoD-3, DoD-4, DoD-6.

The application is always the real factory's (``create_app()``), pinned to the per-test
database through ``dependency_overrides[get_settings]``. ``TestClient`` is not used as a
context manager: the lifespan is irrelevant to these answers.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, select

from app.config import Settings, get_settings
from app.db import schema
from app.db.engine import get_connection, get_engine
from app.main import create_app
from app.roles import Role
from app.routers.bootstrap import router as bootstrap_router
from app.services.auth import resolve_session
from app.services.bootstrap import is_configured
from app.services.passwords import verify_password

CREATE_PATH = "/api/bootstrap/create"
HEALTH_PATH = "/api/health"
ME_PATH = "/api/me"
GUARD_PROBE_PATH = "/guard-probe"
GUARD_PROBE_FULL_PATH = "/api/bootstrap/guard-probe"

USERNAME = "founder"
PASSWORD = "correct horse battery staple"
EXISTING_ADMIN_ID = 424242
EXISTING_ADMIN_USERNAME = "already-here"
EXISTING_ADMIN_HASH = "pre-existing-admin-hash-sentinel"
TIMESTAMP = "2026-01-01T00:00:00+00:00"

FIXED_MINTED_ID = 987_654_321_012_345
SMUGGLED_ID = 12345


class _FixedIdGenerator:
    """A generator stand-in whose ``next_id()`` always answers one known value."""

    def __init__(self, value: int) -> None:
        self.value = value

    def next_id(self) -> int:
        return self.value


@pytest.fixture(autouse=True)
def _quiet_factory_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the factory's logging call so these tests touch no global sinks."""
    monkeypatch.setattr("app.main.configure_logging", lambda settings: None)


@pytest.fixture
def application(db_settings: Settings, db_engine: Engine) -> Iterator[FastAPI]:
    """The factory's application, pinned to the per-test database."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: db_settings
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client(application: FastAPI) -> TestClient:
    return TestClient(application)


@pytest.fixture
def guarded_probe_client(db_settings: Settings, db_engine: Engine) -> Iterator[TestClient]:
    """DoD-4 — an app whose bootstrap router carries a second, test-only route.

    The route is registered on the **same** router object the production module exports,
    and declares no dependency of its own. It is added before the factory includes the
    router and removed again afterwards so it never leaks into another test.
    """

    def guard_probe() -> dict[str, bool]:
        return {"reached": True}

    before = list(bootstrap_router.routes)
    bootstrap_router.add_api_route(GUARD_PROBE_PATH, guard_probe, methods=["GET"])
    added = [route for route in bootstrap_router.routes if route not in before]
    try:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: db_settings
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.clear()
    finally:
        for route in added:
            bootstrap_router.routes.remove(route)


# --- helpers -------------------------------------------------------------------------


def _make_configured(engine: Engine) -> None:
    """Apply the registry and insert one administrator — a configured instance (D3)."""
    with engine.connect() as connection:
        schema.metadata.create_all(connection)
        connection.execute(
            schema.users.insert().values(
                id=EXISTING_ADMIN_ID,
                username=EXISTING_ADMIN_USERNAME,
                password_hash=EXISTING_ADMIN_HASH,
                role=Role.ADMIN,
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


def _users_table_present(connection: Connection) -> bool:
    count = connection.exec_driver_sql(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'users'"
    ).scalar_one()
    return bool(count)


def _user_rows(engine: Engine) -> list[dict[str, Any]]:
    """Every ``users`` row, ordered by id; empty when the table does not exist."""
    with engine.connect() as connection:
        if not _users_table_present(connection):
            return []
        result = connection.execute(select(schema.users).order_by(schema.users.c.id))
        return [dict(row) for row in result.mappings().all()]


def _admin_rows(engine: Engine) -> list[dict[str, Any]]:
    return [row for row in _user_rows(engine) if row["role"] == Role.ADMIN]


def _create(client: TestClient, payload: dict[str, Any] | None = None) -> Any:
    body = payload if payload is not None else {"username": USERNAME, "password": PASSWORD}
    return client.post(CREATE_PATH, json=body)


def _assert_already_configured_wire_shape(body: Any) -> None:
    assert isinstance(body, dict)
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error, dict)
    assert set(error) == {"code", "message", "detail"}
    assert error["code"] == "already_configured"
    assert error["message"] is None or isinstance(error["message"], str)
    assert error["detail"] == {}


# --- DoD-1: 201 with id (decimal string), username, role; the admin is persisted -----


def test_create_on_unconfigured_instance_answers_201__DoD1(client: TestClient) -> None:
    """DoD-1 — an unconfigured instance accepts the creation with 201."""
    assert _create(client).status_code == 201


def test_create_response_carries_id_username_and_admin_role__DoD1(client: TestClient) -> None:
    """DoD-1 — the body names the new administrator: id, the submitted username, role ``admin``."""
    body = _create(client).json()
    assert "id" in body
    assert body["username"] == USERNAME
    assert body["role"] == "admin"


def test_create_response_id_is_a_decimal_string_never_a_number__DoD1(client: TestClient) -> None:
    """DoD-1 — the id crosses the wire as a decimal string, not a JSON number."""
    body = _create(client).json()
    assert isinstance(body["id"], str)
    assert body["id"].isdecimal()
    assert int(body["id"]) > 0


def test_create_persists_the_administrator_the_response_names__DoD1(client: TestClient, db_engine: Engine) -> None:
    """DoD-1 — afterwards the database holds exactly that administrator."""
    body = _create(client).json()
    admins = _admin_rows(db_engine)
    assert len(admins) == 1
    assert admins[0]["id"] == int(body["id"])
    assert admins[0]["username"] == USERNAME
    assert admins[0]["role"] == Role.ADMIN


# --- DoD-2: no token / session / cookie, no Set-Cookie --------------------------------


def test_create_response_body_has_no_token_session_or_cookie_field__DoD2(client: TestClient) -> None:
    """DoD-2 — D9: the create response carries no token, session or cookie field."""
    body = _create(client).json()
    for key in body:
        lowered = key.lower()
        assert "token" not in lowered
        assert "session" not in lowered
        assert "cookie" not in lowered


# 004/004 DoD-4 (context.md D15 item 2): 003/003 DoD-2's ``Set-Cookie`` half —
# ``test_create_response_sets_no_cookie__DoD2`` — is deleted here, deliberately, and replaced
# by the opposite assertion (004/004 DoD-1, below). The body half above stays.


# =====================================================================================
# Feature 004, step 004 — the create route signs the operator in.
# Expected values: 004.bootstrap-signs-in.md DoD-1..DoD-4, DoD-6 and 004/context.md D6,
# D11. Bindings: ``## Skeleton`` → Step 004 (route), Step 003 (``GET /api/me``), Step 001
# (``resolve_session``, the ``auth_sessions`` table).
# =====================================================================================


def _parse_set_cookie(header: str) -> tuple[str, str, dict[str, str | None]]:
    """Split one ``Set-Cookie`` header into (name, value, lower-cased attribute map)."""
    parts = [part.strip() for part in header.split(";")]
    name, _, value = parts[0].partition("=")
    attributes: dict[str, str | None] = {}
    for part in parts[1:]:
        if not part:
            continue
        key, sep, attr_value = part.partition("=")
        attributes[key.strip().lower()] = attr_value.strip() if sep else None
    return name.strip(), value.strip().strip('"'), attributes


def _cookies_named(response: httpx.Response, name: str) -> list[tuple[str, dict[str, str | None]]]:
    found = []
    for header in response.headers.get_list("set-cookie"):
        cookie_name, value, attributes = _parse_set_cookie(header)
        if cookie_name == name:
            found.append((value, attributes))
    return found


def _session_token(response: httpx.Response, settings: Settings) -> str:
    cookies = _cookies_named(response, settings.session_cookie_name)
    assert len(cookies) == 1
    token = cookies[0][0]
    assert token
    return token


def _session_rows(engine: Engine) -> list[dict[str, Any]]:
    """Every ``auth_sessions`` row, ordered by id; empty when the table does not exist."""
    with engine.connect() as connection:
        present = connection.exec_driver_sql(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'auth_sessions'"
        ).scalar_one()
        if not present:
            return []
        query = select(schema.auth_sessions).order_by(schema.auth_sessions.c.id)
        return [dict(row) for row in connection.execute(query).mappings().all()]


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _with_ttl(application: FastAPI, settings: Settings, ttl_hours: int) -> Settings:
    changed = settings.model_copy(update={"session_ttl_hours": ttl_hours})
    application.dependency_overrides[get_settings] = lambda: changed
    return changed


# --- DoD-1: 201 plus the session cookie with D6's flags -------------------------------


def test_create_answers_201_and_sets_the_configured_session_cookie__S004_004_DoD1(
    client: TestClient, db_settings: Settings
) -> None:
    """DoD-1 — US-001.AC-2: the 201 carries one ``Set-Cookie`` for the configured cookie name."""
    response = _create(client)
    assert response.status_code == 201
    cookies = _cookies_named(response, db_settings.session_cookie_name)
    assert len(cookies) == 1
    assert cookies[0][0] != ""


def test_create_cookie_carries_the_d6_flags__S004_004_DoD1(client: TestClient, db_settings: Settings) -> None:
    """DoD-1 — HttpOnly, SameSite=Lax, Path=/, no Secure, Max-Age = the TTL setting in seconds."""
    response = _create(client)
    assert response.status_code == 201
    cookies = _cookies_named(response, db_settings.session_cookie_name)
    assert len(cookies) == 1
    _, attributes = cookies[0]
    assert "httponly" in attributes
    assert (attributes.get("samesite") or "").lower() == "lax"
    assert attributes.get("path") == "/"
    assert "secure" not in attributes
    assert attributes.get("max-age") == str(db_settings.session_ttl_hours * 3600)


@pytest.mark.parametrize("ttl_hours", [3, 96])
def test_create_cookie_max_age_follows_the_ttl_setting__S004_004_DoD1(
    application: FastAPI, db_settings: Settings, ttl_hours: int
) -> None:
    """DoD-1 — overriding ``session_ttl_hours`` changes the cookie's ``Max-Age`` to match."""
    changed = _with_ttl(application, db_settings, ttl_hours)
    response = _create(TestClient(application))
    assert response.status_code == 201
    cookies = _cookies_named(response, changed.session_cookie_name)
    assert len(cookies) == 1
    assert cookies[0][1].get("max-age") == str(ttl_hours * 3600)


def test_create_cookie_uses_an_overridden_cookie_name__S004_004_DoD1(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-1 — the cookie is named by ``session_cookie_name``, never a literal."""
    other_name = "another_session_cookie_name"
    assert db_settings.session_cookie_name != other_name
    renamed = db_settings.model_copy(update={"session_cookie_name": other_name})
    application.dependency_overrides[get_settings] = lambda: renamed
    response = _create(TestClient(application))
    assert response.status_code == 201
    assert len(_cookies_named(response, other_name)) == 1
    assert _cookies_named(response, db_settings.session_cookie_name) == []


# --- DoD-2: the cookie is a live session — /api/me answers with no login in between ---


def test_create_cookie_is_accepted_by_me__S004_004_DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — US-001.AC-2: ``GET /api/me`` with that cookie answers 200 naming the new admin."""
    application.state.id_generator = _FixedIdGenerator(FIXED_MINTED_ID)
    response = _create(TestClient(application))
    assert response.status_code == 201
    token = _session_token(response, db_settings)

    fresh = TestClient(application)
    fresh.cookies.set(db_settings.session_cookie_name, token)
    me = fresh.get(ME_PATH)

    assert me.status_code == 200
    body = me.json()
    assert body["id"] == str(FIXED_MINTED_ID)
    assert body["username"] == USERNAME
    assert body["role"] == "admin"


def test_the_creating_client_is_signed_in_afterwards__S004_004_DoD2(client: TestClient) -> None:
    """DoD-2 — the same client, with no login request, is recognised by ``GET /api/me``."""
    created = _create(client)
    assert created.status_code == 201
    me = client.get(ME_PATH)
    assert me.status_code == 200
    assert me.json()["id"] == created.json()["id"]
    assert me.json()["username"] == USERNAME
    assert me.json()["role"] == "admin"


def test_me_without_the_create_cookie_is_not_signed_in__S004_004_DoD2(application: FastAPI) -> None:
    """DoD-2 — control: it is the cookie that signs in; a client without it answers 401."""
    assert _create(TestClient(application)).status_code == 201
    assert TestClient(application).get(ME_PATH).status_code == 401


# --- DoD-3: exactly one live session row for the new admin; expiry = created + TTL ----


def test_create_leaves_exactly_one_live_session_for_the_new_admin__S004_004_DoD3(
    application: FastAPI, db_settings: Settings, db_engine: Engine
) -> None:
    """DoD-3 — one ``auth_sessions`` row, owned by the new admin, not revoked; the cookie resolves to it."""
    application.state.id_generator = _FixedIdGenerator(FIXED_MINTED_ID)
    response = _create(TestClient(application))
    assert response.status_code == 201
    rows = _session_rows(db_engine)
    assert len(rows) == 1
    assert rows[0]["user_id"] == FIXED_MINTED_ID
    assert rows[0]["revoked_at"] is None
    with db_engine.connect() as connection:
        resolved = resolve_session(connection, _session_token(response, db_settings))
    assert resolved is not None
    assert resolved.id == FIXED_MINTED_ID
    assert resolved.role == Role.ADMIN


def test_create_session_expires_at_creation_plus_the_default_ttl__S004_004_DoD3(
    client: TestClient, db_settings: Settings, db_engine: Engine
) -> None:
    """DoD-3 — ``expires_at`` is the row's creation instant plus ``Settings.session_ttl_hours``."""
    before = datetime.now(UTC)
    assert _create(client).status_code == 201
    after = datetime.now(UTC)
    row = _session_rows(db_engine)[0]
    created = _parse_utc(row["created_at"])
    assert _parse_utc(row["expires_at"]) - created == timedelta(hours=db_settings.session_ttl_hours)
    assert before - timedelta(seconds=1) <= created <= after + timedelta(seconds=1)


@pytest.mark.parametrize("ttl_hours", [3, 96])
def test_create_session_expiry_follows_the_ttl_setting__S004_004_DoD3(
    application: FastAPI, db_settings: Settings, db_engine: Engine, ttl_hours: int
) -> None:
    """DoD-3 — with ``session_ttl_hours`` overridden, the stored expiry follows it."""
    _with_ttl(application, db_settings, ttl_hours)
    assert _create(TestClient(application)).status_code == 201
    rows = _session_rows(db_engine)
    assert len(rows) == 1
    assert _parse_utc(rows[0]["expires_at"]) - _parse_utc(rows[0]["created_at"]) == timedelta(hours=ttl_hours)


# --- DoD-4: the body is exactly what 003 shipped — no token, session or expiry --------


def test_create_body_is_exactly_id_username_and_role__S004_004_DoD4(
    client: TestClient, db_settings: Settings
) -> None:
    """DoD-4 — only id (decimal string), username and role; the token appears nowhere in the body."""
    response = _create(client)
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "username", "role"}
    assert isinstance(body["id"], str) and body["id"].isdecimal()
    for key in body:
        lowered = key.lower()
        for forbidden in ("token", "session", "expir", "cookie"):
            assert forbidden not in lowered
    assert _session_token(response, db_settings) not in response.text


# --- DoD-6: the refusal path is untouched — 409, no session row, no cookie -----------


def test_refused_create_answers_409_opens_no_session_and_sets_no_cookie__S004_004_DoD6(
    client: TestClient, db_engine: Engine
) -> None:
    """DoD-6 — US-003.AC-1: configured instance → 409 ``already_configured``, no session, no cookie."""
    _make_configured(db_engine)
    response = _create(client)
    assert response.status_code == 409
    _assert_already_configured_wire_shape(response.json())
    assert _session_rows(db_engine) == []
    assert response.headers.get_list("set-cookie") == []
    assert len(client.cookies) == 0


def test_second_create_after_success_opens_no_second_session__S004_004_DoD6(
    application: FastAPI, db_engine: Engine
) -> None:
    """DoD-6 — a repeat create on the now-configured instance is refused, adds no session, sets no cookie."""
    assert _create(TestClient(application)).status_code == 201
    second = _create(TestClient(application))
    assert second.status_code == 409
    _assert_already_configured_wire_shape(second.json())
    assert second.headers.get_list("set-cookie") == []
    assert len(_session_rows(db_engine)) == 1


# --- DoD-3: configured instance → 409 already_configured, database untouched ---------


def test_create_on_configured_instance_answers_409__DoD3(client: TestClient, db_engine: Engine) -> None:
    """DoD-3 — US-003.AC-1: a configured instance refuses with 409."""
    _make_configured(db_engine)
    assert _create(client).status_code == 409


def test_create_on_configured_instance_answers_the_domain_error_wire_shape__DoD3(
    client: TestClient, db_engine: Engine
) -> None:
    """DoD-3 — the refusal is ``{"error": {"code": "already_configured", "message", "detail": {}}}``."""
    _make_configured(db_engine)
    _assert_already_configured_wire_shape(_create(client).json())


def test_create_on_configured_instance_leaves_the_database_untouched__DoD3(
    client: TestClient, db_engine: Engine
) -> None:
    """DoD-3 — the existing database is untouched: same tables, same rows, same admin hash."""
    _make_configured(db_engine)
    tables_before = _table_names(db_engine)
    rows_before = _user_rows(db_engine)

    _create(client)

    assert _table_names(db_engine) == tables_before
    assert _user_rows(db_engine) == rows_before
    assert len(rows_before) == 1
    assert rows_before[0]["password_hash"] == EXISTING_ADMIN_HASH


def test_create_on_configured_instance_with_the_existing_username_still_refuses__DoD3(
    client: TestClient, db_engine: Engine
) -> None:
    """DoD-3 — the refusal is the state conflict, whatever the credentials submitted."""
    _make_configured(db_engine)
    rows_before = _user_rows(db_engine)
    response = _create(client, {"username": EXISTING_ADMIN_USERNAME, "password": PASSWORD})
    assert response.status_code == 409
    _assert_already_configured_wire_shape(response.json())
    assert _user_rows(db_engine) == rows_before


# --- DoD-4: the guard is router-level ------------------------------------------------


def test_second_route_on_the_router_is_refused_on_configured_instance__DoD4(
    guarded_probe_client: TestClient, db_engine: Engine
) -> None:
    """DoD-4 — a route declaring no dependency, registered on the same router, is refused."""
    _make_configured(db_engine)
    response = guarded_probe_client.get(GUARD_PROBE_FULL_PATH)
    assert response.status_code == 409
    _assert_already_configured_wire_shape(response.json())


def test_second_route_on_the_router_is_reachable_on_unconfigured_instance__DoD4(
    guarded_probe_client: TestClient,
) -> None:
    """DoD-4 — control: the same test route answers normally when the instance is unconfigured."""
    response = guarded_probe_client.get(GUARD_PROBE_FULL_PATH)
    assert response.status_code == 200
    assert response.json() == {"reached": True}


def test_test_only_route_does_not_leak_into_other_applications__DoD4(client: TestClient) -> None:
    """DoD-4 — hygiene: an ordinary factory app exposes no test-only probe route."""
    assert client.get(GUARD_PROBE_FULL_PATH).status_code == 404


# --- DoD-5: reachable with no credentials --------------------------------------------


def test_create_is_reachable_with_no_cookie_and_no_authorization_header__DoD5(
    application: FastAPI, db_engine: Engine
) -> None:
    """DoD-5 — no cookie, no ``Authorization`` header, and the unconfigured instance still creates."""
    anonymous = TestClient(application)
    assert len(anonymous.cookies) == 0
    assert "authorization" not in {name.lower() for name in anonymous.headers.keys()}

    response = anonymous.post(CREATE_PATH, json={"username": USERNAME, "password": PASSWORD})

    assert response.status_code == 201
    assert response.status_code not in (401, 403)
    assert len(_admin_rows(db_engine)) == 1


# --- DoD-6: empty username / password refused before anything is written -------------


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "", "password": PASSWORD},
        {"username": USERNAME, "password": ""},
        {"username": "", "password": ""},
    ],
    ids=["empty-username", "empty-password", "both-empty"],
)
def test_empty_credentials_are_refused_with_422__DoD6(client: TestClient, payload: dict[str, str]) -> None:
    """DoD-6 — D16: the non-empty backstop answers FastAPI's own 422, not 201."""
    assert _create(client, payload).status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "", "password": PASSWORD},
        {"username": USERNAME, "password": ""},
        {"username": "", "password": ""},
    ],
    ids=["empty-username", "empty-password", "both-empty"],
)
def test_empty_credentials_leave_no_administrator_and_write_nothing__DoD6(
    client: TestClient, db_engine: Engine, payload: dict[str, str]
) -> None:
    """DoD-6 — refused before anything is written: no administrator, no schema created."""
    _create(client, payload)
    assert _admin_rows(db_engine) == []
    assert _table_names(db_engine) == set()
    with db_engine.connect() as connection:
        assert is_configured(connection) is False


def test_empty_credential_refusal_is_not_a_new_domain_error_code__DoD6(client: TestClient) -> None:
    """DoD-6 — D16: the backstop adds no domain error code; the body is not the error envelope."""
    body = _create(client, {"username": "", "password": ""}).json()
    envelope = body.get("error") if isinstance(body, dict) else None
    assert not (isinstance(envelope, dict) and "code" in envelope)


# --- DoD-7: undeclared fields cannot choose the role or the id ------------------------


def test_smuggled_role_id_and_flags_do_not_shape_the_account__DoD7(
    application: FastAPI, client: TestClient, db_engine: Engine
) -> None:
    """DoD-7 — UC-001: a named role, id or other undeclared field never lands on the account."""
    application.state.id_generator = _FixedIdGenerator(FIXED_MINTED_ID)
    response = _create(
        client,
        {
            "username": USERNAME,
            "password": PASSWORD,
            "role": "roleplayer",
            "id": SMUGGLED_ID,
            "is_enabled": False,
            "password_hash": "smuggled-hash",
        },
    )

    rows = _user_rows(db_engine)
    assert all(row["role"] == Role.ADMIN for row in rows)
    assert all(row["id"] != SMUGGLED_ID for row in rows)
    assert all(row["is_enabled"] is True for row in rows)
    assert all(row["password_hash"] != "smuggled-hash" for row in rows)
    if response.status_code == 201:
        body = response.json()
        assert body["role"] == "admin"
        assert body["id"] != str(SMUGGLED_ID)


def test_smuggled_string_id_does_not_become_the_account_id__DoD7(
    application: FastAPI, client: TestClient, db_engine: Engine
) -> None:
    """DoD-7 — a decimal-string id in the request is not honoured either; the id is server-minted."""
    application.state.id_generator = _FixedIdGenerator(FIXED_MINTED_ID)
    _create(
        client,
        {"username": USERNAME, "password": PASSWORD, "id": str(SMUGGLED_ID), "role": "admin"},
    )
    rows = _user_rows(db_engine)
    assert all(row["id"] != SMUGGLED_ID for row in rows)
    assert all(row["id"] == FIXED_MINTED_ID for row in rows)


def test_created_account_id_is_minted_by_the_server__DoD7(
    application: FastAPI, client: TestClient, db_engine: Engine
) -> None:
    """DoD-7 — the id comes from the process's generator on application state, not from the caller."""
    application.state.id_generator = _FixedIdGenerator(FIXED_MINTED_ID)
    response = _create(
        client,
        {"username": USERNAME, "password": PASSWORD, "id": SMUGGLED_ID, "role": "roleplayer"},
    )
    assert response.status_code == 201
    assert response.json()["id"] == str(FIXED_MINTED_ID)
    assert response.json()["role"] == "admin"
    assert [row["id"] for row in _admin_rows(db_engine)] == [FIXED_MINTED_ID]


# --- DoD-8: the predicate sees the new admin; health reports configured at once -----


def test_created_administrator_satisfies_the_configured_predicate__DoD8(
    client: TestClient, db_engine: Engine
) -> None:
    """DoD-8 — step 002's predicate finds the administrator created through the route."""
    with db_engine.connect() as connection:
        assert is_configured(connection) is False
    assert _create(client).status_code == 201
    with db_engine.connect() as connection:
        assert is_configured(connection) is True


def test_health_reports_configured_true_immediately_after_create__DoD8(client: TestClient) -> None:
    """DoD-8 — US-001.AC-1: ``/api/health`` flips to ``configured: true`` without a restart."""
    assert client.get(HEALTH_PATH).json()["configured"] is False
    assert _create(client).status_code == 201
    assert client.get(HEALTH_PATH).json()["configured"] is True


def test_second_create_after_first_is_refused_by_the_same_application__DoD8(client: TestClient) -> None:
    """DoD-8 — the same running app sees the new state at once: a repeat create is refused."""
    assert _create(client).status_code == 201
    second = _create(client)
    assert second.status_code == 409
    _assert_already_configured_wire_shape(second.json())


# --- DoD-9: database contact only through the connection dependency; row from service


def test_database_contact_goes_only_through_the_connection_dependency__DoD9(
    application: FastAPI, client: TestClient, db_settings: Settings, db_engine: Engine, tmp_path: Path
) -> None:
    """DoD-9 — redirect ``get_connection`` elsewhere: the admin lands there, never in the settings DB."""
    alternate_settings = db_settings.model_copy(
        update={"data_dir": tmp_path / "alternate", "db_filename": "alternate.sqlite"}
    )
    alternate_engine = get_engine(alternate_settings)

    def alternate_connection() -> Iterator[Connection]:
        connection = alternate_engine.connect()
        try:
            yield connection
        finally:
            connection.close()

    application.dependency_overrides[get_connection] = alternate_connection

    response = _create(client)

    assert response.status_code == 201
    alternate_admins = _admin_rows(alternate_engine)
    assert len(alternate_admins) == 1
    assert alternate_admins[0]["id"] == int(response.json()["id"])
    assert _admin_rows(db_engine) == []
    assert "users" not in _table_names(db_engine)


def test_created_row_carries_the_service_values__DoD9(
    application: FastAPI, client: TestClient, db_engine: Engine
) -> None:
    """DoD-9 / D15 — every column holds what the creation operation writes, nothing router-made."""
    application.state.id_generator = _FixedIdGenerator(FIXED_MINTED_ID)
    assert _create(client).status_code == 201

    rows = _user_rows(db_engine)
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == FIXED_MINTED_ID
    assert row["username"] == USERNAME
    assert row["role"] == Role.ADMIN
    assert row["is_enabled"] is True
    assert row["rp_language"] is None
    assert row["preferred_language"] is None
    assert row["password_hash"] != PASSWORD
    assert verify_password(row["password_hash"], PASSWORD) is True
    assert verify_password(row["password_hash"], "not the password") is False
    assert isinstance(row["created_at"], str) and row["created_at"]
    assert isinstance(row["updated_at"], str) and row["updated_at"]
