"""Tests for the admin users router: ``/api/admin/users`` and its four action routes.

Every expected value comes from ``docs/plans/005.admin-shell-and-users/003.admin-users-router.md``
(Interface intent + Definition of done), ``003.context.md`` and the feature ``context.md``
(D5 the route table, D6 password reset, D9 path ids, R5, the JSON id boundary), plus the
``004`` contracts this router's behaviour is observed through (``GET /api/me``,
``POST /api/auth/login``, ``not_authenticated``/401, ``insufficient_role``/403).
Bindings come from ``## Skeleton`` in ``status.md`` (steps 001, 002, 003).

Covers step 003 DoD-1 .. DoD-16. DoD-17 .. DoD-20 are ``[manual/live]`` and carry no test.

The application is always the real factory's (``create_app()``), pinned to the per-test
database through ``dependency_overrides[get_settings]``. Cookies are carried explicitly:
a token is read from a login response's ``Set-Cookie`` header and handed to a fresh client.
"""

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, func, select

from app.config import Settings, get_settings
from app.db import schema
from app.db.engine import get_connection, get_engine
from app.main import create_app
from app.roles import Role
from app.routers.admin_users import router as admin_users_router
from app.services.passwords import hash_password

LIST_PATH = "/api/admin/users"
LOGIN_PATH = "/api/auth/login"
ME_PATH = "/api/me"

GUARD_PROBE_PATH = "/guard-probe"
GUARD_PROBE_FULL_PATH = "/api/admin/users/guard-probe"

TIMESTAMP = "2026-01-01T00:00:00+00:00"

ADMIN_ID = 8_000_001
ADMIN_NAME = "founder"
ADMIN_PASSWORD = "correct horse battery staple"

SECOND_ADMIN_ID = 8_000_002
SECOND_ADMIN_NAME = "co-keeper"
SECOND_ADMIN_PASSWORD = "another admin secret"

PLAYER_ID = 8_000_003
PLAYER_NAME = "wanderer"
PLAYER_PASSWORD = "a quiet river at dusk"

OTHER_PLAYER_ID = 8_000_004
OTHER_PLAYER_NAME = "drifter"
OTHER_PLAYER_PASSWORD = "salt and lantern light"

DISABLED_ID = 8_000_005
DISABLED_NAME = "sleeper"
DISABLED_PASSWORD = "dormant but correct"

# DoD-15: beyond Number.MAX_SAFE_INTEGER (2**53 - 1). The neighbour is the value a float
# round-trip of BIG_ID would collapse onto, so addressing the wrong one is observable.
BIG_ID = 2**53 + 1  # 9007199254740993
BIG_ID_TEXT = "9007199254740993"
BIG_NAME = "far-numbered"
BIG_PASSWORD = "a very large number"
NEIGHBOR_ID = 2**53  # 9007199254740992
NEIGHBOR_NAME = "near-numbered"
NEIGHBOR_PASSWORD = "the number next door"

UNKNOWN_ID = 8_999_999

NEW_NAME = "newcomer"
NEW_PASSWORD = "freshly chosen secret"
REPLACEMENT_PASSWORD = "a brand new password"

FIXED_MINTED_ID = 914_000_000_000_001

ACCOUNT_KEYS = {"id", "username", "role", "is_enabled", "last_login_at"}

NOT_AUTHENTICATED = "not_authenticated"
INSUFFICIENT_ROLE = "insufficient_role"
USERNAME_TAKEN = "username_taken"
USER_NOT_FOUND = "user_not_found"
SELF_ROLE_CHANGE_REFUSED = "self_role_change_refused"
INVALID_CREDENTIALS = "invalid_credentials"

SEEDED_IDS = {ADMIN_ID, SECOND_ADMIN_ID, PLAYER_ID, OTHER_PLAYER_ID, DISABLED_ID, BIG_ID, NEIGHBOR_ID}


class _FixedIdGenerator:
    """A generator stand-in whose ``next_id()`` always answers one known value."""

    def __init__(self, value: int) -> None:
        self.value = value
        self.calls = 0

    def next_id(self) -> int:
        self.calls += 1
        return self.value


# --- fixtures ------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _quiet_factory_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the factory's logging call so these tests touch no global sinks."""
    monkeypatch.setattr("app.main.configure_logging", lambda settings: None)


def _insert_user(
    engine: Engine,
    *,
    user_id: int,
    username: str,
    password: str,
    role: Role,
    enabled: bool = True,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.users.insert().values(
                id=user_id,
                username=username,
                password_hash=hash_password(password),
                role=role,
                is_enabled=enabled,
                rp_language=None,
                preferred_language=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _seed(engine: Engine) -> None:
    with engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(engine, user_id=ADMIN_ID, username=ADMIN_NAME, password=ADMIN_PASSWORD, role=Role.ADMIN)
    _insert_user(
        engine,
        user_id=SECOND_ADMIN_ID,
        username=SECOND_ADMIN_NAME,
        password=SECOND_ADMIN_PASSWORD,
        role=Role.ADMIN,
    )
    _insert_user(engine, user_id=PLAYER_ID, username=PLAYER_NAME, password=PLAYER_PASSWORD, role=Role.ROLEPLAYER)
    _insert_user(
        engine,
        user_id=OTHER_PLAYER_ID,
        username=OTHER_PLAYER_NAME,
        password=OTHER_PLAYER_PASSWORD,
        role=Role.ROLEPLAYER,
    )
    _insert_user(
        engine,
        user_id=DISABLED_ID,
        username=DISABLED_NAME,
        password=DISABLED_PASSWORD,
        role=Role.ROLEPLAYER,
        enabled=False,
    )
    _insert_user(engine, user_id=BIG_ID, username=BIG_NAME, password=BIG_PASSWORD, role=Role.ROLEPLAYER)
    _insert_user(
        engine, user_id=NEIGHBOR_ID, username=NEIGHBOR_NAME, password=NEIGHBOR_PASSWORD, role=Role.ROLEPLAYER
    )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    _seed(db_engine)
    return db_engine


@pytest.fixture
def application(db_settings: Settings, engine: Engine) -> Iterator[FastAPI]:
    """The factory's application, pinned to the seeded per-test database."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: db_settings
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def guarded_probe_app(db_settings: Settings, engine: Engine) -> Iterator[FastAPI]:
    """DoD-4 — an app whose admin-users router carries a second, test-only route.

    The route is registered on the **same** router object the production module exports and
    declares no dependency of its own. It is added before the factory includes the router
    and removed again afterwards so it never leaks into another test.
    """

    def guard_probe() -> dict[str, bool]:
        return {"reached": True}

    before = list(admin_users_router.routes)
    admin_users_router.add_api_route(GUARD_PROBE_PATH, guard_probe, methods=["GET"])
    added = [route for route in admin_users_router.routes if route not in before]
    try:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: db_settings
        try:
            yield app
        finally:
            app.dependency_overrides.clear()
    finally:
        for route in added:
            admin_users_router.routes.remove(route)


# --- helpers -------------------------------------------------------------------------


def _action_path(user_id: int | str, action: str) -> str:
    return f"{LIST_PATH}/{user_id}/{action}"


def _parse_set_cookie(header: str) -> tuple[str, str]:
    first = header.split(";")[0]
    name, _, value = first.partition("=")
    return name.strip(), value.strip().strip('"')


def _login(application: FastAPI, username: str, password: str) -> httpx.Response:
    return TestClient(application).post(LOGIN_PATH, json={"username": username, "password": password})


def _token_from(response: httpx.Response, cookie_name: str) -> str:
    tokens = [
        value
        for name, value in (_parse_set_cookie(h) for h in response.headers.get_list("set-cookie"))
        if name == cookie_name
    ]
    assert len(tokens) == 1
    assert tokens[0]
    return tokens[0]


def _login_token(application: FastAPI, settings: Settings, username: str, password: str) -> str:
    response = _login(application, username, password)
    assert response.status_code == 200
    return _token_from(response, settings.session_cookie_name)


def _with_cookie(application: FastAPI, settings: Settings, token: str | None) -> TestClient:
    """A fresh client carrying exactly the session cookie (or none)."""
    fresh = TestClient(application)
    if token is not None:
        fresh.cookies.set(settings.session_cookie_name, token)
    return fresh


def _as(application: FastAPI, settings: Settings, username: str, password: str) -> TestClient:
    """A fresh client signed in as this account."""
    return _with_cookie(application, settings, _login_token(application, settings, username, password))


def _admin(application: FastAPI, settings: Settings) -> TestClient:
    return _as(application, settings, ADMIN_NAME, ADMIN_PASSWORD)


def _me(application: FastAPI, settings: Settings, token: str | None) -> httpx.Response:
    return _with_cookie(application, settings, token).get(ME_PATH)


def _assert_envelope(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error, dict)
    assert error["code"] == code
    return body


def _assert_not_domain_envelope(response: httpx.Response) -> None:
    body = response.json()
    envelope = body.get("error") if isinstance(body, dict) else None
    assert not (isinstance(envelope, dict) and "code" in envelope)


def _assert_account_shape(account: Any) -> None:
    assert isinstance(account, dict)
    assert set(account) == ACCOUNT_KEYS
    assert isinstance(account["id"], str)
    assert not isinstance(account["id"], bool | int | float)
    assert account["id"].isdecimal()
    assert isinstance(account["username"], str)
    assert account["role"] in {Role.ROLEPLAYER.value, Role.ADMIN.value}
    assert isinstance(account["is_enabled"], bool)
    assert account["last_login_at"] is None or isinstance(account["last_login_at"], str)


def _user_rows(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        query = select(schema.users).order_by(schema.users.c.id)
        return [dict(row) for row in connection.execute(query).mappings()]


def _user_row(engine: Engine, user_id: int) -> dict[str, Any]:
    rows = [row for row in _user_rows(engine) if row["id"] == user_id]
    assert len(rows) == 1
    return rows[0]


def _user_count(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(schema.users)).scalar_one())


def _listed(response: httpx.Response) -> dict[str, dict[str, Any]]:
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"users"}
    assert isinstance(body["users"], list)
    return {account["id"]: account for account in body["users"]}


def _all_routes(target_id: int) -> list[tuple[str, str, dict[str, Any] | None]]:
    """The six routes of D5, each with a well-formed body, addressed at ``target_id``."""
    return [
        ("GET", LIST_PATH, None),
        ("POST", LIST_PATH, {"username": NEW_NAME, "password": NEW_PASSWORD, "role": Role.ROLEPLAYER.value}),
        ("POST", _action_path(target_id, "disable"), None),
        ("POST", _action_path(target_id, "enable"), None),
        ("POST", _action_path(target_id, "password"), {"password": REPLACEMENT_PASSWORD}),
        ("POST", _action_path(target_id, "role"), {"role": Role.ADMIN.value}),
    ]


ROUTE_IDS = ["list", "create", "disable", "enable", "password", "role"]

ID_ROUTES: list[tuple[str, dict[str, Any] | None]] = [
    ("disable", None),
    ("enable", None),
    ("password", {"password": REPLACEMENT_PASSWORD}),
    ("role", {"role": Role.ADMIN.value}),
]
ID_ROUTE_IDS = ["disable", "enable", "password", "role"]


def _send(client: TestClient, method: str, path: str, body: dict[str, Any] | None) -> httpx.Response:
    if body is None:
        return client.request(method, path)
    return client.request(method, path, json=body)


# =========================================================================== DoD-1


def test_list_answers_200_with_every_account__DoD1(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-1 — US-011.AC-1: an administrator's list carries every account, disabled included."""
    listed = _listed(_admin(application, db_settings).get(LIST_PATH))
    assert set(listed) == {str(user_id) for user_id in SEEDED_IDS}


def test_list_entries_carry_identity_role_enabled_and_last_login__DoD1(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-1 — each entry: id, username, role, enabled flag and ``last_login_at``, with the seeded values."""
    listed = _listed(_admin(application, db_settings).get(LIST_PATH))
    for account in listed.values():
        _assert_account_shape(account)
    expected = {
        ADMIN_ID: (ADMIN_NAME, Role.ADMIN, True),
        SECOND_ADMIN_ID: (SECOND_ADMIN_NAME, Role.ADMIN, True),
        PLAYER_ID: (PLAYER_NAME, Role.ROLEPLAYER, True),
        OTHER_PLAYER_ID: (OTHER_PLAYER_NAME, Role.ROLEPLAYER, True),
        DISABLED_ID: (DISABLED_NAME, Role.ROLEPLAYER, False),
        BIG_ID: (BIG_NAME, Role.ROLEPLAYER, True),
        NEIGHBOR_ID: (NEIGHBOR_NAME, Role.ROLEPLAYER, True),
    }
    for user_id, (username, role, enabled) in expected.items():
        account = listed[str(user_id)]
        assert account["username"] == username
        assert account["role"] == role.value
        assert account["is_enabled"] is enabled


def test_list_ids_are_decimal_strings_never_json_numbers__DoD1(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-1 — every id crosses the wire as a decimal string."""
    response = _admin(application, db_settings).get(LIST_PATH)
    assert response.status_code == 200
    for account in response.json()["users"]:
        assert isinstance(account["id"], str)
        assert not isinstance(account["id"], bool | int | float)
        assert account["id"].isdecimal()
        assert int(account["id"]) in SEEDED_IDS


def test_list_last_login_is_null_until_login_and_set_after__DoD1(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-1 — ``last_login_at`` is null for a never-signed-in account and an ISO-8601 text once signed in."""
    listed = _listed(_admin(application, db_settings).get(LIST_PATH))
    assert listed[str(PLAYER_ID)]["last_login_at"] is None
    admin_stamp = listed[str(ADMIN_ID)]["last_login_at"]
    assert isinstance(admin_stamp, str)
    datetime.fromisoformat(admin_stamp)


# =========================================================================== DoD-2


FORBIDDEN_KEY_FRAGMENTS = (
    "password",
    "hash",
    "token",
    "language",
    "count",
    "character",
    "setup",
    "session",
    "entry",
    "entries",
    "memo",
)


def _assert_no_forbidden_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            lowered = key.lower()
            for fragment in FORBIDDEN_KEY_FRAGMENTS:
                assert fragment not in lowered, key
            _assert_no_forbidden_keys(inner)
    elif isinstance(value, list):
        for inner in value:
            _assert_no_forbidden_keys(inner)


def test_every_route_answers_only_the_account_fields__DoD2(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-2 — R5 / UC-066 / US-011.AC-2: all six routes answer accounts of exactly five fields."""
    admin = _admin(application, db_settings)
    responses = [_send(admin, method, path, body) for method, path, body in _all_routes(PLAYER_ID)]
    for response in responses:
        assert response.status_code in (200, 201)
        body = response.json()
        _assert_no_forbidden_keys(body)
        accounts = body["users"] if set(body) == {"users"} else [body]
        for account in accounts:
            _assert_account_shape(account)


def test_no_response_carries_a_password_hash_or_token__DoD2(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-2 — no plaintext password, stored hash or session token appears in any body."""
    admin_token = _login_token(application, db_settings, ADMIN_NAME, ADMIN_PASSWORD)
    player_token = _login_token(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    admin = _with_cookie(application, db_settings, admin_token)
    responses = [_send(admin, method, path, body) for method, path, body in _all_routes(PLAYER_ID)]
    hashes = [row["password_hash"] for row in _user_rows(engine)]
    secrets = [
        admin_token,
        player_token,
        ADMIN_PASSWORD,
        PLAYER_PASSWORD,
        NEW_PASSWORD,
        REPLACEMENT_PASSWORD,
        *hashes,
    ]
    for response in responses:
        assert response.status_code in (200, 201)
        for secret in secrets:
            assert secret not in response.text


EXPECTED_OPERATIONS = {
    ("/api/admin/users", "get"),
    ("/api/admin/users", "post"),
    ("/api/admin/users/{user_id}/disable", "post"),
    ("/api/admin/users/{user_id}/enable", "post"),
    ("/api/admin/users/{user_id}/password", "post"),
    ("/api/admin/users/{user_id}/role", "post"),
}


def _admin_operations(application: FastAPI) -> dict[tuple[str, str], dict[str, Any]]:
    paths = application.openapi()["paths"]
    found: dict[tuple[str, str], dict[str, Any]] = {}
    for path, operations in paths.items():
        if path == "/api/admin/users" or path.startswith("/api/admin/users/"):
            for method, operation in operations.items():
                found[(path, method.lower())] = operation
    return found


def test_router_declares_only_the_account_routes__DoD2(application: FastAPI) -> None:
    """DoD-2 — no route that could return a count, a session or anything a user owns: only D5's six."""
    assert set(_admin_operations(application)) == EXPECTED_OPERATIONS


def test_no_route_takes_a_query_parameter_or_any_key_but_the_account_id__DoD2(application: FastAPI) -> None:
    """DoD-2 — no route is keyed on anything but an account; no filter/page/sort query parameter anywhere."""
    for (path, _method), operation in _admin_operations(application).items():
        parameters = operation.get("parameters", [])
        assert [p for p in parameters if p.get("in") == "query"] == []
        path_names = {p["name"] for p in parameters if p.get("in") == "path"}
        if "{user_id}" in path:
            assert path_names == {"user_id"}
        else:
            assert path_names == set()


# =========================================================================== DoD-3


@pytest.mark.parametrize(("route_index"), range(6), ids=ROUTE_IDS)
def test_every_route_refuses_a_roleplayer_with_403__DoD3(
    application: FastAPI, db_settings: Settings, route_index: int
) -> None:
    """DoD-3 — a live roleplayer session: 403 ``insufficient_role`` on every route."""
    player = _as(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    method, path, body = _all_routes(OTHER_PLAYER_ID)[route_index]
    _assert_envelope(_send(player, method, path, body), 403, INSUFFICIENT_ROLE)


@pytest.mark.parametrize(("route_index"), range(6), ids=ROUTE_IDS)
def test_every_route_answers_401_without_a_session__DoD3(
    application: FastAPI, db_settings: Settings, route_index: int
) -> None:
    """DoD-3 — no session at all: 401 ``not_authenticated`` (401 before 403), never 403."""
    anonymous = _with_cookie(application, db_settings, None)
    method, path, body = _all_routes(OTHER_PLAYER_ID)[route_index]
    response = _send(anonymous, method, path, body)
    assert response.status_code != 403
    _assert_envelope(response, 401, NOT_AUTHENTICATED)


@pytest.mark.parametrize(("route_index"), range(6), ids=ROUTE_IDS)
def test_every_route_answers_401_for_an_unissued_cookie__DoD3(
    application: FastAPI, db_settings: Settings, route_index: int
) -> None:
    """DoD-3 — a cookie that resolves to no session is 'no session': 401, not 403."""
    stranger = _with_cookie(application, db_settings, "this-token-was-never-issued-by-anyone-0000")
    method, path, body = _all_routes(OTHER_PLAYER_ID)[route_index]
    _assert_envelope(_send(stranger, method, path, body), 401, NOT_AUTHENTICATED)


def test_refused_requests_change_nothing__DoD3(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-3 — a refused roleplayer or anonymous caller writes nothing through any route."""
    player = _as(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    before = _user_rows(engine)
    anonymous = _with_cookie(application, db_settings, None)
    for method, path, body in _all_routes(OTHER_PLAYER_ID):
        assert _send(player, method, path, body).status_code == 403
        assert _send(anonymous, method, path, body).status_code == 401
    assert _user_rows(engine) == before


def test_administrator_is_admitted_on_every_route__DoD3(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-3 — control: the same six requests from an administrator are not refused."""
    admin = _admin(application, db_settings)
    for method, path, body in _all_routes(OTHER_PLAYER_ID):
        assert _send(admin, method, path, body).status_code in (200, 201)


# =========================================================================== DoD-4


def test_route_without_its_own_dependency_is_refused_for_a_roleplayer__DoD4(
    guarded_probe_app: FastAPI, db_settings: Settings
) -> None:
    """DoD-4 — a route registered on this router with no dependency of its own is still 403 for a roleplayer."""
    player = _as(guarded_probe_app, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    _assert_envelope(player.get(GUARD_PROBE_FULL_PATH), 403, INSUFFICIENT_ROLE)


def test_route_without_its_own_dependency_is_401_without_a_session__DoD4(
    guarded_probe_app: FastAPI, db_settings: Settings
) -> None:
    """DoD-4 — the same probe route answers 401 with no session."""
    anonymous = _with_cookie(guarded_probe_app, db_settings, None)
    _assert_envelope(anonymous.get(GUARD_PROBE_FULL_PATH), 401, NOT_AUTHENTICATED)


def test_route_without_its_own_dependency_is_reachable_for_an_administrator__DoD4(
    guarded_probe_app: FastAPI, db_settings: Settings
) -> None:
    """DoD-4 — control: an administrator reaches the probe route."""
    admin = _admin(guarded_probe_app, db_settings)
    response = admin.get(GUARD_PROBE_FULL_PATH)
    assert response.status_code == 200
    assert response.json() == {"reached": True}


def test_probe_route_does_not_leak_into_other_applications__DoD4(application: FastAPI, db_settings: Settings) -> None:
    """DoD-4 — hygiene: an ordinary factory app exposes no test-only probe route."""
    admin = _admin(application, db_settings)
    assert admin.get(GUARD_PROBE_FULL_PATH).status_code in (404, 405)


# =========================================================================== DoD-5


@pytest.mark.parametrize("role", [Role.ROLEPLAYER, Role.ADMIN], ids=["roleplayer", "admin"])
def test_create_answers_201_with_an_enabled_account__DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine, role: Role
) -> None:
    """DoD-5 — US-008.AC-1: 201 with the created account, enabled, with the requested username and role."""
    admin = _admin(application, db_settings)
    response = admin.post(LIST_PATH, json={"username": NEW_NAME, "password": NEW_PASSWORD, "role": role.value})
    assert response.status_code == 201
    body = response.json()
    _assert_account_shape(body)
    assert body["username"] == NEW_NAME
    assert body["role"] == role.value
    assert body["is_enabled"] is True
    assert body["last_login_at"] is None
    assert int(body["id"]) not in SEEDED_IDS
    assert _user_count(engine) == len(SEEDED_IDS) + 1


def test_created_account_appears_in_a_subsequent_list__DoD5(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-5 — US-008.AC-2: the new account is listed, exactly as the create answered it."""
    admin = _admin(application, db_settings)
    created = admin.post(
        LIST_PATH, json={"username": NEW_NAME, "password": NEW_PASSWORD, "role": Role.ROLEPLAYER.value}
    )
    assert created.status_code == 201
    listed = _listed(admin.get(LIST_PATH))
    assert set(listed) == {str(user_id) for user_id in SEEDED_IDS} | {created.json()["id"]}
    assert listed[created.json()["id"]] == created.json()


def test_created_account_can_log_in_with_its_password__DoD5(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-5 — the created (enabled) account can sign in with the password it was given."""
    admin = _admin(application, db_settings)
    created = admin.post(
        LIST_PATH, json={"username": NEW_NAME, "password": NEW_PASSWORD, "role": Role.ROLEPLAYER.value}
    )
    assert created.status_code == 201
    response = _login(application, NEW_NAME, NEW_PASSWORD)
    assert response.status_code == 200
    assert response.json()["id"] == created.json()["id"]


# =========================================================================== DoD-6


def test_duplicate_username_answers_409_username_taken__DoD6(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-6 — an existing username: 409 ``{"error": {"code": "username_taken", ...}}`` and nothing created."""
    admin = _admin(application, db_settings)
    before = _user_rows(engine)
    response = admin.post(
        LIST_PATH, json={"username": PLAYER_NAME, "password": NEW_PASSWORD, "role": Role.ADMIN.value}
    )
    _assert_envelope(response, 409, USERNAME_TAKEN)
    assert _user_rows(engine) == before


def test_second_create_of_the_same_new_username_is_refused__DoD6(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-6 — creating the same new username twice: the second is 409 and leaves one account."""
    admin = _admin(application, db_settings)
    payload = {"username": NEW_NAME, "password": NEW_PASSWORD, "role": Role.ROLEPLAYER.value}
    assert admin.post(LIST_PATH, json=payload).status_code == 201
    count = _user_count(engine)
    _assert_envelope(admin.post(LIST_PATH, json=payload), 409, USERNAME_TAKEN)
    assert _user_count(engine) == count
    assert [row["username"] for row in _user_rows(engine)].count(NEW_NAME) == 1


# =========================================================================== DoD-7


EMPTY_CREATE_PAYLOADS = [
    {"username": "", "password": NEW_PASSWORD, "role": Role.ROLEPLAYER.value},
    {"username": NEW_NAME, "password": "", "role": Role.ROLEPLAYER.value},
    {"username": "", "password": "", "role": Role.ROLEPLAYER.value},
]
EMPTY_CREATE_IDS = ["empty-username", "empty-password", "both-empty"]


@pytest.mark.parametrize("payload", EMPTY_CREATE_PAYLOADS, ids=EMPTY_CREATE_IDS)
def test_empty_create_field_answers_422_and_writes_nothing__DoD7(
    application: FastAPI, db_settings: Settings, engine: Engine, payload: dict[str, str]
) -> None:
    """DoD-7 — an empty username or password is FastAPI's 422, before anything is written."""
    admin = _admin(application, db_settings)
    before = _user_rows(engine)
    response = admin.post(LIST_PATH, json=payload)
    assert response.status_code == 422
    assert _user_rows(engine) == before


@pytest.mark.parametrize("payload", EMPTY_CREATE_PAYLOADS, ids=EMPTY_CREATE_IDS)
def test_empty_create_field_refusal_is_not_the_domain_envelope__DoD7(
    application: FastAPI, db_settings: Settings, payload: dict[str, str]
) -> None:
    """DoD-7 — the 422 is not the domain-error envelope and adds no domain error code."""
    response = _admin(application, db_settings).post(LIST_PATH, json=payload)
    assert response.status_code == 422
    _assert_not_domain_envelope(response)


def test_empty_new_password_answers_422_and_changes_nothing__DoD7(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-7 — an empty set-password is the same 422 backstop; the old password still works."""
    admin = _admin(application, db_settings)
    before = _user_rows(engine)
    response = admin.post(_action_path(PLAYER_ID, "password"), json={"password": ""})
    assert response.status_code == 422
    _assert_not_domain_envelope(response)
    assert _user_rows(engine) == before
    assert _login(application, PLAYER_NAME, PLAYER_PASSWORD).status_code == 200


# =========================================================================== DoD-8


def test_disable_answers_200_with_the_account_disabled__DoD8(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-8 — 200 with the target's account, now disabled."""
    response = _admin(application, db_settings).post(_action_path(PLAYER_ID, "disable"))
    assert response.status_code == 200
    body = response.json()
    _assert_account_shape(body)
    assert body["id"] == str(PLAYER_ID)
    assert body["username"] == PLAYER_NAME
    assert body["is_enabled"] is False
    assert not _user_row(engine, PLAYER_ID)["is_enabled"]


def test_disable_ends_the_targets_existing_sessions_immediately__DoD8(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-8 — US-009.AC-1: the target's cookies answered 200 before and answer 401 on ``/api/me`` right after."""
    first = _login_token(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    second = _login_token(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    assert _me(application, db_settings, first).status_code == 200
    assert _me(application, db_settings, second).status_code == 200

    assert _admin(application, db_settings).post(_action_path(PLAYER_ID, "disable")).status_code == 200

    _assert_envelope(_me(application, db_settings, first), 401, NOT_AUTHENTICATED)
    _assert_envelope(_me(application, db_settings, second), 401, NOT_AUTHENTICATED)


def test_disable_leaves_other_accounts_sessions_alive__DoD8(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-8 — only the target's sessions end."""
    other = _login_token(application, db_settings, OTHER_PLAYER_NAME, OTHER_PLAYER_PASSWORD)
    admin_token = _login_token(application, db_settings, ADMIN_NAME, ADMIN_PASSWORD)
    admin = _with_cookie(application, db_settings, admin_token)
    assert admin.post(_action_path(PLAYER_ID, "disable")).status_code == 200
    assert _me(application, db_settings, other).status_code == 200
    assert _me(application, db_settings, admin_token).status_code == 200


# =========================================================================== DoD-9


def test_disabled_account_login_with_correct_credentials_is_refused__DoD9(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-9 — US-009.AC-2: after the disable, the correct password is refused (``invalid_credentials``)."""
    assert _login(application, PLAYER_NAME, PLAYER_PASSWORD).status_code == 200
    assert _admin(application, db_settings).post(_action_path(PLAYER_ID, "disable")).status_code == 200
    response = _login(application, PLAYER_NAME, PLAYER_PASSWORD)
    _assert_envelope(response, 400, INVALID_CREDENTIALS)
    assert response.headers.get_list("set-cookie") == []


# =========================================================================== DoD-10


def test_enable_answers_200_with_the_account_enabled__DoD10(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-10 — re-enabling a disabled account answers 200 with it enabled again."""
    admin = _admin(application, db_settings)
    assert admin.post(_action_path(PLAYER_ID, "disable")).status_code == 200
    response = admin.post(_action_path(PLAYER_ID, "enable"))
    assert response.status_code == 200
    body = response.json()
    _assert_account_shape(body)
    assert body["id"] == str(PLAYER_ID)
    assert body["is_enabled"] is True
    assert _user_row(engine, PLAYER_ID)["is_enabled"]


def test_enable_of_a_seeded_disabled_account_restores_login__DoD10(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-10 — UC-007 alternate flow: an account that was disabled can sign in once enabled."""
    assert _login(application, DISABLED_NAME, DISABLED_PASSWORD).status_code == 400
    response = _admin(application, db_settings).post(_action_path(DISABLED_ID, "enable"))
    assert response.status_code == 200
    assert response.json()["is_enabled"] is True
    assert _login(application, DISABLED_NAME, DISABLED_PASSWORD).status_code == 200


def test_reenabled_account_gets_a_new_session_and_old_ones_stay_revoked__DoD10(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-10 — after disable then enable: login gives a new working session; the old cookie stays 401."""
    old = _login_token(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    admin = _admin(application, db_settings)
    assert admin.post(_action_path(PLAYER_ID, "disable")).status_code == 200
    assert admin.post(_action_path(PLAYER_ID, "enable")).status_code == 200

    _assert_envelope(_me(application, db_settings, old), 401, NOT_AUTHENTICATED)

    new = _login_token(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    assert new != old
    me = _me(application, db_settings, new)
    assert me.status_code == 200
    assert me.json()["id"] == str(PLAYER_ID)
    _assert_envelope(_me(application, db_settings, old), 401, NOT_AUTHENTICATED)


# =========================================================================== DoD-11


def test_set_password_answers_200_with_no_password_or_hash__DoD11(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-11 — 200 with the account; the body carries neither the password nor the hash."""
    response = _admin(application, db_settings).post(
        _action_path(PLAYER_ID, "password"), json={"password": REPLACEMENT_PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    _assert_account_shape(body)
    assert body["id"] == str(PLAYER_ID)
    assert REPLACEMENT_PASSWORD not in response.text
    assert PLAYER_PASSWORD not in response.text
    assert _user_row(engine, PLAYER_ID)["password_hash"] not in response.text


def test_old_password_refused_and_new_one_works_after_set_password__DoD11(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-11 — US-010.AC-1 the old password is refused; US-010.AC-2 the new one signs in."""
    assert _login(application, PLAYER_NAME, PLAYER_PASSWORD).status_code == 200
    response = _admin(application, db_settings).post(
        _action_path(PLAYER_ID, "password"), json={"password": REPLACEMENT_PASSWORD}
    )
    assert response.status_code == 200
    _assert_envelope(_login(application, PLAYER_NAME, PLAYER_PASSWORD), 400, INVALID_CREDENTIALS)
    signed_in = _login(application, PLAYER_NAME, REPLACEMENT_PASSWORD)
    assert signed_in.status_code == 200
    assert signed_in.json()["id"] == str(PLAYER_ID)


def test_set_password_requires_no_current_password__DoD11(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-11 / D6 — the body is the new password alone; no current password is asked for."""
    response = _admin(application, db_settings).post(
        _action_path(OTHER_PLAYER_ID, "password"), json={"password": REPLACEMENT_PASSWORD}
    )
    assert response.status_code == 200
    assert _login(application, OTHER_PLAYER_NAME, REPLACEMENT_PASSWORD).status_code == 200


# =========================================================================== DoD-12


@pytest.mark.parametrize(
    ("user_id", "username", "password", "new_role"),
    [
        (PLAYER_ID, PLAYER_NAME, PLAYER_PASSWORD, Role.ADMIN),
        (SECOND_ADMIN_ID, SECOND_ADMIN_NAME, SECOND_ADMIN_PASSWORD, Role.ROLEPLAYER),
    ],
    ids=["promote", "demote"],
)
def test_role_change_answers_200_and_the_existing_session_sees_it__DoD12(
    application: FastAPI,
    db_settings: Settings,
    user_id: int,
    username: str,
    password: str,
    new_role: Role,
) -> None:
    """DoD-12 — 200 with the new role; the target's existing cookie reports it on the next ``/api/me``."""
    target_token = _login_token(application, db_settings, username, password)
    before = _me(application, db_settings, target_token)
    assert before.status_code == 200
    assert before.json()["role"] != new_role.value

    response = _admin(application, db_settings).post(_action_path(user_id, "role"), json={"role": new_role.value})
    assert response.status_code == 200
    body = response.json()
    _assert_account_shape(body)
    assert body["id"] == str(user_id)
    assert body["role"] == new_role.value

    after = _me(application, db_settings, target_token)
    assert after.status_code == 200
    assert after.json()["role"] == new_role.value


def test_promoted_existing_session_is_admitted_without_new_login__DoD12(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-12 — the role is read live: a promoted roleplayer's same cookie now passes this router's guard."""
    player_token = _login_token(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    player = _with_cookie(application, db_settings, player_token)
    assert player.get(LIST_PATH).status_code == 403
    response = _admin(application, db_settings).post(
        _action_path(PLAYER_ID, "role"), json={"role": Role.ADMIN.value}
    )
    assert response.status_code == 200
    assert player.get(LIST_PATH).status_code == 200


# =========================================================================== DoD-13


def test_self_role_change_answers_409_and_changes_nothing__DoD13(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-13 — the calling administrator targeting themself: 409 ``self_role_change_refused``, nothing written."""
    admin_token = _login_token(application, db_settings, ADMIN_NAME, ADMIN_PASSWORD)
    before = _user_rows(engine)
    response = _with_cookie(application, db_settings, admin_token).post(
        _action_path(ADMIN_ID, "role"), json={"role": Role.ROLEPLAYER.value}
    )
    _assert_envelope(response, 409, SELF_ROLE_CHANGE_REFUSED)
    assert _user_rows(engine) == before
    me = _me(application, db_settings, admin_token)
    assert me.status_code == 200
    assert me.json()["role"] == Role.ADMIN.value


def test_same_target_changed_by_a_different_administrator_succeeds__DoD13(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-13 — the same target, changed by another administrator, succeeds."""
    admin_token = _login_token(application, db_settings, ADMIN_NAME, ADMIN_PASSWORD)
    self_attempt = _with_cookie(application, db_settings, admin_token).post(
        _action_path(ADMIN_ID, "role"), json={"role": Role.ROLEPLAYER.value}
    )
    assert self_attempt.status_code == 409

    second = _as(application, db_settings, SECOND_ADMIN_NAME, SECOND_ADMIN_PASSWORD)
    response = second.post(_action_path(ADMIN_ID, "role"), json={"role": Role.ROLEPLAYER.value})
    assert response.status_code == 200
    assert response.json()["id"] == str(ADMIN_ID)
    assert response.json()["role"] == Role.ROLEPLAYER.value
    assert _user_row(engine, ADMIN_ID)["role"] == Role.ROLEPLAYER.value


# =========================================================================== DoD-14


@pytest.mark.parametrize(("action", "body"), ID_ROUTES, ids=ID_ROUTE_IDS)
def test_unknown_id_answers_404_user_not_found__DoD14(
    application: FastAPI, db_settings: Settings, engine: Engine, action: str, body: dict[str, Any] | None
) -> None:
    """DoD-14 — every id-addressed route: 404 ``{"error": {"code": "user_not_found", ...}}``, nothing written."""
    admin = _admin(application, db_settings)
    before = _user_rows(engine)
    response = _send(admin, "POST", _action_path(UNKNOWN_ID, action), body)
    _assert_envelope(response, 404, USER_NOT_FOUND)
    assert _user_rows(engine) == before


# =========================================================================== DoD-15


def test_list_carries_the_large_id_as_its_exact_string__DoD15(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-15 — an id beyond MAX_SAFE_INTEGER is listed as its exact decimal string."""
    listed = _listed(_admin(application, db_settings).get(LIST_PATH))
    assert listed[BIG_ID_TEXT]["username"] == BIG_NAME
    assert listed[str(NEIGHBOR_ID)]["username"] == NEIGHBOR_NAME


@pytest.mark.parametrize(("action", "body"), ID_ROUTES, ids=ID_ROUTE_IDS)
def test_large_path_id_round_trips_exactly__DoD15(
    application: FastAPI, db_settings: Settings, action: str, body: dict[str, Any] | None
) -> None:
    """DoD-15 / D9 — ``{user_id}`` beyond MAX_SAFE_INTEGER addresses that account and comes back as the same string."""
    response = _send(_admin(application, db_settings), "POST", _action_path(BIG_ID_TEXT, action), body)
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == BIG_ID_TEXT
    assert payload["username"] == BIG_NAME


def test_large_path_id_disable_touches_only_that_account__DoD15(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-15 — disabling the large id disables it and not the account one below it."""
    response = _admin(application, db_settings).post(_action_path(BIG_ID_TEXT, "disable"))
    assert response.status_code == 200
    assert response.json()["is_enabled"] is False
    assert not _user_row(engine, BIG_ID)["is_enabled"]
    assert _user_row(engine, NEIGHBOR_ID)["is_enabled"]


def test_large_path_id_role_change_touches_only_that_account__DoD15(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-15 — a role change on the large id lands on it and not on its neighbour."""
    response = _admin(application, db_settings).post(
        _action_path(BIG_ID_TEXT, "role"), json={"role": Role.ADMIN.value}
    )
    assert response.status_code == 200
    assert response.json()["role"] == Role.ADMIN.value
    assert _user_row(engine, BIG_ID)["role"] == Role.ADMIN.value
    assert _user_row(engine, NEIGHBOR_ID)["role"] == Role.ROLEPLAYER.value


# =========================================================================== DoD-16


def test_database_contact_goes_only_through_the_connection_dependency__DoD16(
    application: FastAPI, db_settings: Settings, engine: Engine, tmp_path: Path
) -> None:
    """DoD-16 — redirect ``get_connection`` elsewhere: listing and writing happen there only."""
    alternate_settings = db_settings.model_copy(
        update={"data_dir": tmp_path / "alternate", "db_filename": "alternate.sqlite"}
    )
    alternate_engine = get_engine(alternate_settings)
    with alternate_engine.begin() as connection:
        schema.metadata.create_all(connection)
    alternate_admin_id = 8_100_001
    alternate_player_id = 8_100_002
    _insert_user(
        alternate_engine,
        user_id=alternate_admin_id,
        username="alternate-admin",
        password="alternate admin password",
        role=Role.ADMIN,
    )
    _insert_user(
        alternate_engine,
        user_id=alternate_player_id,
        username="alternate-player",
        password="alternate player password",
        role=Role.ROLEPLAYER,
    )

    def alternate_connection() -> Iterator[Connection]:
        connection = alternate_engine.connect()
        try:
            yield connection
        finally:
            connection.close()

    application.dependency_overrides[get_connection] = alternate_connection
    main_before = _user_rows(engine)

    admin = _as(application, db_settings, "alternate-admin", "alternate admin password")
    listed = _listed(admin.get(LIST_PATH))
    assert set(listed) == {str(alternate_admin_id), str(alternate_player_id)}

    created = admin.post(
        LIST_PATH, json={"username": NEW_NAME, "password": NEW_PASSWORD, "role": Role.ROLEPLAYER.value}
    )
    assert created.status_code == 201
    assert int(created.json()["id"]) in {row["id"] for row in _user_rows(alternate_engine)}

    assert admin.post(_action_path(alternate_player_id, "disable")).status_code == 200
    assert not _user_row(alternate_engine, alternate_player_id)["is_enabled"]

    # A seeded account of the settings database is unknown through the dependency.
    _assert_envelope(admin.post(_action_path(PLAYER_ID, "disable")), 404, USER_NOT_FOUND)
    assert _user_rows(engine) == main_before


def test_created_id_comes_from_the_generator_on_application_state__DoD16(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-16 — the generator the route passes down is the one on ``app.state``, not a module global."""
    generator = _FixedIdGenerator(FIXED_MINTED_ID)
    admin = _admin(application, db_settings)
    application.state.id_generator = generator
    response = admin.post(
        LIST_PATH, json={"username": NEW_NAME, "password": NEW_PASSWORD, "role": Role.ROLEPLAYER.value}
    )
    assert response.status_code == 201
    assert response.json()["id"] == str(FIXED_MINTED_ID)
    assert _user_row(engine, FIXED_MINTED_ID)["username"] == NEW_NAME
    assert generator.calls >= 1


def test_generator_is_per_application_not_shared__DoD16(db_settings: Settings, engine: Engine) -> None:
    """DoD-16 — two applications with two generators each mint from their own."""
    first_id, second_id = 915_000_000_000_001, 915_000_000_000_002
    first_app, second_app = create_app(), create_app()
    try:
        for app in (first_app, second_app):
            app.dependency_overrides[get_settings] = lambda: db_settings
        # One session, minted once; the same cookie is honoured by both apps (same database).
        admin_token = _login_token(first_app, db_settings, ADMIN_NAME, ADMIN_PASSWORD)
        first_admin = _with_cookie(first_app, db_settings, admin_token)
        second_admin = _with_cookie(second_app, db_settings, admin_token)
        first_app.state.id_generator = _FixedIdGenerator(first_id)
        second_app.state.id_generator = _FixedIdGenerator(second_id)
        first = first_admin.post(
            LIST_PATH, json={"username": "first-new", "password": NEW_PASSWORD, "role": Role.ROLEPLAYER.value}
        )
        second = second_admin.post(
            LIST_PATH, json={"username": "second-new", "password": NEW_PASSWORD, "role": Role.ROLEPLAYER.value}
        )
    finally:
        first_app.dependency_overrides.clear()
        second_app.dependency_overrides.clear()
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == str(first_id)
    assert second.json()["id"] == str(second_id)
    assert _user_row(engine, first_id)["username"] == "first-new"
    assert _user_row(engine, second_id)["username"] == "second-new"


def test_stored_account_values_come_from_the_service__DoD16(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-16 — the stored row is the service's: enabled, a real hash (never the plaintext), no login yet."""
    admin = _admin(application, db_settings)
    response = admin.post(
        LIST_PATH, json={"username": NEW_NAME, "password": NEW_PASSWORD, "role": Role.ADMIN.value}
    )
    assert response.status_code == 201
    row = _user_row(engine, int(response.json()["id"]))
    assert row["username"] == NEW_NAME
    assert row["role"] == Role.ADMIN.value
    assert row["is_enabled"]
    assert row["password_hash"] != NEW_PASSWORD
    assert NEW_PASSWORD not in row["password_hash"]
    assert row["last_login_at"] is None
    assert _login(application, NEW_NAME, NEW_PASSWORD).status_code == 200
