"""fast/010.unconfigured-to-bootstrap — a session cookie on an unconfigured instance.

Covers the plan's backend DoD items (``docs/plans/fast/010.unconfigured-to-bootstrap/plan.md``):

- DoD-8  a stale cookie on ``GET /api/me`` against a schema-less database answers 401
         ``not_authenticated``, not 500 (US-148.AC-3);
- DoD-9  the same through ``require_role``: ``GET /api/admin/users`` with a cookie answers 401;
- DoD-10 no cookie on an unconfigured instance still answers 401 on ``GET /api/me``;
- DoD-11 the guard writes nothing: no ``users`` table appears and ``/api/health`` still reports
         ``configured: false``;
- DoD-12 configured controls: a valid cookie gets 200 with its user, an unknown token 401,
         a valid admin cookie 200 on ``GET /api/admin/users`` (US-148.AC-4);
- DoD-17 (D4 amendment) a zero-user database (schema applied, ``users`` empty) refuses a cookie
         on ``/api/me`` and ``/api/admin/users`` with 401 ``not_authenticated``;
- DoD-18 (D4 amendment) a users-without-admin database is not refused by the guard: a valid
         roleplayer cookie gets ``/api/me`` 200 with that identity;
- DoD-19 (D4 amendment) ``any_user_exists`` called directly: false on schema-less and
         zero-user databases, true with users (with or without an administrator), and the
         connection can still ``begin()`` afterwards.

"Configured instance" (DoD-12) is a database with at least one administrator; the seeded
fixture here holds an administrator and a roleplayer.

Every expected value comes from the plan and its ``context.md``. The unconfigured application is
the ``health_client`` pattern of ``test_health.py`` (the real factory, settings pinned through
``dependency_overrides``, a fresh schema-less per-test database from conftest). The configured
one is seeded the way ``test_auth_router.py`` seeds it. Server exceptions are not re-raised into
the test, so a 500 is observed as a 500 rather than as a crash.
"""

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.config import Settings, get_settings
from app.db import schema
from app.main import create_app
from app.roles import Role
from app.services.bootstrap import any_user_exists
from app.services.passwords import hash_password

ME_PATH = "/api/me"
ADMIN_USERS_PATH = "/api/admin/users"
HEALTH_PATH = "/api/health"
LOGIN_PATH = "/api/auth/login"

NOT_AUTHENTICATED = "not_authenticated"

STALE_TOKEN = "a-token-from-a-database-that-no-longer-exists-0000"
UNISSUED_TOKEN = "this-token-was-never-issued-by-anyone-at-all-0000"

TIMESTAMP = "2026-01-01T00:00:00+00:00"

ADMIN_ID = 8_200_001
ADMIN_NAME = "founder"
ADMIN_PASSWORD = "correct horse battery staple"

PLAYER_ID = 8_200_002
PLAYER_NAME = "wanderer"
PLAYER_PASSWORD = "a quiet river at dusk"


# --- fixtures ------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _quiet_factory_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the factory's logging call so these tests touch no global sinks."""
    monkeypatch.setattr("app.main.configure_logging", lambda settings: None)


@pytest.fixture
def unconfigured_app(db_settings: Settings, db_engine: Engine) -> Iterator[FastAPI]:
    """The factory's application pinned to a fresh, schema-less per-test database."""
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: db_settings
    with db_engine.connect() as connection:
        connection.exec_driver_sql("SELECT 1")
    try:
        yield application
    finally:
        application.dependency_overrides.clear()


def _insert_user(engine: Engine, *, user_id: int, username: str, password: str, role: Role) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.users.insert().values(
                id=user_id,
                username=username,
                password_hash=hash_password(password),
                role=role,
                is_enabled=True,
                rp_language=None,
                preferred_language=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


@pytest.fixture
def configured_app(db_settings: Settings, db_engine: Engine) -> Iterator[FastAPI]:
    """The factory's application pinned to a seeded (configured) per-test database."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=ADMIN_ID, username=ADMIN_NAME, password=ADMIN_PASSWORD, role=Role.ADMIN)
    _insert_user(
        db_engine, user_id=PLAYER_ID, username=PLAYER_NAME, password=PLAYER_PASSWORD, role=Role.ROLEPLAYER
    )
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: db_settings
    try:
        yield application
    finally:
        application.dependency_overrides.clear()


# --- helpers -------------------------------------------------------------------------


def _client(application: FastAPI) -> TestClient:
    return TestClient(application, raise_server_exceptions=False)


def _with_cookie(application: FastAPI, cookie: tuple[str, str] | None) -> TestClient:
    """A fresh client carrying exactly this cookie (or none)."""
    fresh = _client(application)
    if cookie is not None:
        fresh.cookies.set(cookie[0], cookie[1])
    return fresh


def _assert_envelope(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error, dict)
    assert set(error) == {"code", "message", "detail"}
    assert error["code"] == code
    return body


def _users_table_exists(engine: Engine) -> bool:
    with engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'users'"
        ).fetchall()
    return len(rows) > 0


def _login_token(application: FastAPI, settings: Settings, username: str, password: str) -> str:
    response = _client(application).post(LOGIN_PATH, json={"username": username, "password": password})
    assert response.status_code == 200
    token = response.cookies.get(settings.session_cookie_name)
    assert token
    return str(token)


# =========================================================================== DoD-8


def test_stale_cookie_on_me_answers_401_not_500__DoD8(unconfigured_app: FastAPI, db_settings: Settings) -> None:
    """DoD-8 — US-148.AC-3: a leftover cookie on a schema-less database gets 401 ``not_authenticated``."""
    response = _with_cookie(unconfigured_app, (db_settings.session_cookie_name, STALE_TOKEN)).get(ME_PATH)
    assert response.status_code != 500
    _assert_envelope(response, 401, NOT_AUTHENTICATED)


@pytest.mark.parametrize("token", [STALE_TOKEN, UNISSUED_TOKEN, "x"], ids=["stale", "unissued", "one-char"])
def test_any_cookie_value_on_me_answers_401__DoD8(
    unconfigured_app: FastAPI, db_settings: Settings, token: str
) -> None:
    """DoD-8 — any token value: the cookie cannot name a session while the instance is unconfigured."""
    response = _with_cookie(unconfigured_app, (db_settings.session_cookie_name, token)).get(ME_PATH)
    _assert_envelope(response, 401, NOT_AUTHENTICATED)


# =========================================================================== DoD-9


def test_stale_cookie_on_admin_users_answers_401_not_500__DoD9(
    unconfigured_app: FastAPI, db_settings: Settings
) -> None:
    """DoD-9 — the administration address (``require_role``) refuses the cookie with the same 401."""
    response = _with_cookie(unconfigured_app, (db_settings.session_cookie_name, STALE_TOKEN)).get(
        ADMIN_USERS_PATH
    )
    assert response.status_code != 500
    _assert_envelope(response, 401, NOT_AUTHENTICATED)


def test_me_and_admin_users_refuse_the_cookie_identically__DoD9(
    unconfigured_app: FastAPI, db_settings: Settings
) -> None:
    """DoD-9 — ``require_user`` and ``require_role`` give the same status and code for the same cookie."""
    cookie = (db_settings.session_cookie_name, STALE_TOKEN)
    me = _with_cookie(unconfigured_app, cookie).get(ME_PATH)
    admin = _with_cookie(unconfigured_app, cookie).get(ADMIN_USERS_PATH)
    assert me.status_code == admin.status_code == 401
    assert me.json()["error"]["code"] == admin.json()["error"]["code"] == NOT_AUTHENTICATED


# =========================================================================== DoD-10


def test_no_cookie_on_unconfigured_me_answers_401__DoD10(unconfigured_app: FastAPI) -> None:
    """DoD-10 — the no-cookie path is unchanged on an unconfigured instance: 401 ``not_authenticated``."""
    _assert_envelope(_with_cookie(unconfigured_app, None).get(ME_PATH), 401, NOT_AUTHENTICATED)


# =========================================================================== DoD-11


def test_the_guard_creates_no_users_table__DoD11(
    unconfigured_app: FastAPI, db_settings: Settings, db_engine: Engine
) -> None:
    """DoD-11 — after the cookie-bearing requests of DoD-8 and DoD-9, no ``users`` table exists."""
    assert not _users_table_exists(db_engine)
    cookie = (db_settings.session_cookie_name, STALE_TOKEN)
    _with_cookie(unconfigured_app, cookie).get(ME_PATH)
    _with_cookie(unconfigured_app, cookie).get(ADMIN_USERS_PATH)
    assert not _users_table_exists(db_engine)


def test_health_still_reports_unconfigured_after_the_guard__DoD11(
    unconfigured_app: FastAPI, db_settings: Settings
) -> None:
    """DoD-11 — US-148.AC-3: ``/api/health`` still reports ``configured: false``; bootstrap stays reachable."""
    cookie = (db_settings.session_cookie_name, STALE_TOKEN)
    _with_cookie(unconfigured_app, cookie).get(ME_PATH)
    _with_cookie(unconfigured_app, cookie).get(ADMIN_USERS_PATH)
    health = _with_cookie(unconfigured_app, cookie).get(HEALTH_PATH)
    assert health.status_code == 200
    assert health.json()["configured"] is False


# =========================================================================== DoD-12


def test_valid_cookie_on_configured_me_answers_200_with_that_user__DoD12(
    configured_app: FastAPI, db_settings: Settings
) -> None:
    """DoD-12 — US-148.AC-4: a valid session cookie gets ``GET /api/me`` 200 with that user."""
    token = _login_token(configured_app, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    response = _with_cookie(configured_app, (db_settings.session_cookie_name, token)).get(ME_PATH)
    assert response.status_code == 200
    assert response.json() == {"id": str(PLAYER_ID), "username": PLAYER_NAME, "role": Role.ROLEPLAYER.value}


def test_unknown_cookie_on_configured_me_answers_401__DoD12(
    configured_app: FastAPI, db_settings: Settings
) -> None:
    """DoD-12 — an unknown token on a configured instance is still 401 ``not_authenticated``."""
    response = _with_cookie(configured_app, (db_settings.session_cookie_name, UNISSUED_TOKEN)).get(ME_PATH)
    _assert_envelope(response, 401, NOT_AUTHENTICATED)


def test_valid_admin_cookie_on_configured_admin_users_answers_200__DoD12(
    configured_app: FastAPI, db_settings: Settings
) -> None:
    """DoD-12 — a valid admin cookie gets ``GET /api/admin/users`` 200 on a configured instance."""
    token = _login_token(configured_app, db_settings, ADMIN_NAME, ADMIN_PASSWORD)
    response = _with_cookie(configured_app, (db_settings.session_cookie_name, token)).get(ADMIN_USERS_PATH)
    assert response.status_code == 200


# =========================================================================== D4 amendment fixtures


def _apply_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        schema.metadata.create_all(connection)


def _pinned_app(settings: Settings) -> FastAPI:
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: settings
    return application


@pytest.fixture
def zero_user_app(db_settings: Settings, db_engine: Engine) -> Iterator[FastAPI]:
    """The declared schema applied with no rows in ``users``."""
    _apply_schema(db_engine)
    application = _pinned_app(db_settings)
    try:
        yield application
    finally:
        application.dependency_overrides.clear()


@pytest.fixture
def users_without_admin_app(db_settings: Settings, db_engine: Engine) -> Iterator[FastAPI]:
    """The declared schema with one roleplayer account and no administrator."""
    _apply_schema(db_engine)
    _insert_user(
        db_engine, user_id=PLAYER_ID, username=PLAYER_NAME, password=PLAYER_PASSWORD, role=Role.ROLEPLAYER
    )
    application = _pinned_app(db_settings)
    try:
        yield application
    finally:
        application.dependency_overrides.clear()


# =========================================================================== DoD-17


@pytest.mark.parametrize("token", [STALE_TOKEN, UNISSUED_TOKEN], ids=["stale", "unissued"])
def test_cookie_on_zero_user_me_answers_401__DoD17(
    zero_user_app: FastAPI, db_settings: Settings, token: str
) -> None:
    """DoD-17 — US-148.AC-3: schema applied, no users: a cookie on ``/api/me`` is 401, not 500/200."""
    response = _with_cookie(zero_user_app, (db_settings.session_cookie_name, token)).get(ME_PATH)
    assert response.status_code not in (200, 500)
    _assert_envelope(response, 401, NOT_AUTHENTICATED)


def test_cookie_on_zero_user_admin_users_answers_401__DoD17(
    zero_user_app: FastAPI, db_settings: Settings
) -> None:
    """DoD-17 — the administration address answers the same 401 on a zero-user database."""
    response = _with_cookie(zero_user_app, (db_settings.session_cookie_name, STALE_TOKEN)).get(
        ADMIN_USERS_PATH
    )
    assert response.status_code not in (200, 500)
    _assert_envelope(response, 401, NOT_AUTHENTICATED)


# =========================================================================== DoD-18


def test_users_without_admin_are_not_refused_by_the_guard__DoD18(
    users_without_admin_app: FastAPI, db_settings: Settings
) -> None:
    """DoD-18 — a roleplayer's valid cookie gets ``/api/me`` 200 with that identity, no admin needed."""
    token = _login_token(users_without_admin_app, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    response = _with_cookie(users_without_admin_app, (db_settings.session_cookie_name, token)).get(ME_PATH)
    assert response.status_code == 200
    assert response.json() == {"id": str(PLAYER_ID), "username": PLAYER_NAME, "role": Role.ROLEPLAYER.value}


# =========================================================================== DoD-19


def _read_then_begin(engine: Engine) -> bool:
    """Call the read on a fresh connection, then prove a new transaction can still be opened."""
    with engine.connect() as connection:
        result = any_user_exists(connection)
        with connection.begin():
            connection.exec_driver_sql("SELECT 1")
    return result


def test_any_user_exists_is_false_on_a_schema_less_database__DoD19(db_engine: Engine) -> None:
    """DoD-19 — no ``users`` table: false, nothing raised, connection still usable."""
    assert _read_then_begin(db_engine) is False


def test_any_user_exists_is_false_on_a_zero_user_database__DoD19(db_engine: Engine) -> None:
    """DoD-19 — schema applied, ``users`` empty: false."""
    _apply_schema(db_engine)
    assert _read_then_begin(db_engine) is False


def test_any_user_exists_is_true_on_a_users_without_admin_database__DoD19(db_engine: Engine) -> None:
    """DoD-19 — one roleplayer and no administrator: true."""
    _apply_schema(db_engine)
    _insert_user(
        db_engine, user_id=PLAYER_ID, username=PLAYER_NAME, password=PLAYER_PASSWORD, role=Role.ROLEPLAYER
    )
    assert _read_then_begin(db_engine) is True


def test_any_user_exists_is_true_on_a_configured_instance__DoD19(db_engine: Engine) -> None:
    """DoD-19 — at least one administrator: true."""
    _apply_schema(db_engine)
    _insert_user(db_engine, user_id=ADMIN_ID, username=ADMIN_NAME, password=ADMIN_PASSWORD, role=Role.ADMIN)
    assert _read_then_begin(db_engine) is True
