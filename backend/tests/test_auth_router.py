"""Tests for the auth router: ``POST /api/auth/login``, ``POST /api/auth/logout``, ``GET /api/me``.

Every expected value comes from ``docs/plans/004.authentication-session/003.auth-router.md``
(Interface intent + Definition of done), ``003.context.md`` and the feature ``context.md``
(D1 the uniform refusal, D2 400 never 401, D6 the cookie flags, D7 what a live session is,
D9 idempotent 204 logout, D10 the paths and the identity model, D13 no normalization).
Bindings come from ``## Skeleton`` in ``status.md`` (steps 001, 002, 003).

Covers step 003 DoD-1 .. DoD-13. DoD-14 .. DoD-17 are ``[manual/live]`` and carry no test.

The application is always the real factory's (``create_app()``), pinned to the per-test
database through ``dependency_overrides[get_settings]``. ``TestClient`` is not used as a
context manager. Cookies are carried explicitly: the token is read from the login
response's ``Set-Cookie`` header and handed to a fresh client, so a "same cookie after
logout" check really re-sends the old token.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, Table, func, select, update

from app.config import Settings, get_settings
from app.db import schema
from app.db.engine import get_connection, get_engine
from app.main import create_app
from app.roles import Role
from app.services.auth import resolve_session, revoke_session
from app.services.passwords import hash_password

LOGIN_PATH = "/api/auth/login"
LOGOUT_PATH = "/api/auth/logout"
ME_PATH = "/api/me"

TIMESTAMP = "2026-01-01T00:00:00+00:00"

ADMIN_ID = 8_000_001
ADMIN_NAME = "founder"
ADMIN_PASSWORD = "correct horse battery staple"

PLAYER_ID = 8_000_002
PLAYER_NAME = "wanderer"
PLAYER_PASSWORD = "a quiet river at dusk"

DISABLED_ID = 8_000_003
DISABLED_NAME = "sleeper"
DISABLED_PASSWORD = "dormant but correct"

SPACED_ID = 8_000_004
SPACED_NAME = " spaced"  # stored with a leading space, exactly as some creation form sent it
SPACED_PASSWORD = " padded secret "

UNISSUED_TOKEN = "this-token-was-never-issued-by-anyone-at-all-0000"
OTHER_COOKIE_NAME = "a_differently_named_session_cookie"
FIXED_SESSION_ID = 912_345_678_901_234

INVALID_CREDENTIALS = "invalid_credentials"
NOT_AUTHENTICATED = "not_authenticated"


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
    """Apply the registry and seed an admin, a roleplayer, a disabled account and a spaced name."""
    with engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(engine, user_id=ADMIN_ID, username=ADMIN_NAME, password=ADMIN_PASSWORD, role=Role.ADMIN)
    _insert_user(
        engine, user_id=PLAYER_ID, username=PLAYER_NAME, password=PLAYER_PASSWORD, role=Role.ROLEPLAYER
    )
    _insert_user(
        engine,
        user_id=DISABLED_ID,
        username=DISABLED_NAME,
        password=DISABLED_PASSWORD,
        role=Role.ROLEPLAYER,
        enabled=False,
    )
    _insert_user(
        engine, user_id=SPACED_ID, username=SPACED_NAME, password=SPACED_PASSWORD, role=Role.ROLEPLAYER
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
def client(application: FastAPI) -> TestClient:
    return TestClient(application)


# --- helpers -------------------------------------------------------------------------


def _sessions() -> Table:
    return schema.metadata.tables["auth_sessions"]


def _session_rows(engine: Engine) -> list[dict[str, Any]]:
    query = select(_sessions()).order_by(_sessions().c.id)
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(query).mappings()]


def _session_count(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(_sessions())).scalar_one())


def _live_rows_for(engine: Engine, user_id: int) -> list[dict[str, Any]]:
    return [row for row in _session_rows(engine) if row["user_id"] == user_id and row["revoked_at"] is None]


def _pushed_to_the_past(stored: str) -> str:
    """The same stored timestamp text with only the year rewritten — keeps the stored format."""
    return "2000" + stored[4:]


def _expire_all_sessions_of(engine: Engine, user_id: int) -> None:
    for row in _session_rows(engine):
        if row["user_id"] != user_id:
            continue
        with engine.begin() as connection:
            connection.execute(
                update(_sessions())
                .where(_sessions().c.id == row["id"])
                .values(
                    created_at=_pushed_to_the_past(row["created_at"]),
                    expires_at=_pushed_to_the_past(row["expires_at"]),
                )
            )


def _set_enabled(engine: Engine, user_id: int, enabled: bool) -> None:
    with engine.begin() as connection:
        connection.execute(update(schema.users).where(schema.users.c.id == user_id).values(is_enabled=enabled))


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _set_cookie_headers(response: httpx.Response) -> list[str]:
    return response.headers.get_list("set-cookie")


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
    for header in _set_cookie_headers(response):
        cookie_name, value, attributes = _parse_set_cookie(header)
        if cookie_name == name:
            found.append((value, attributes))
    return found


def _is_cleared(value: str, attributes: dict[str, str | None]) -> bool:
    """True when the header tells the browser to drop the cookie now."""
    max_age = attributes.get("max-age")
    if max_age is not None:
        try:
            if int(max_age) <= 0:
                return True
        except ValueError:
            pass
    expires = attributes.get("expires")
    if expires:
        try:
            when = parsedate_to_datetime(expires)
        except (TypeError, ValueError):
            return False
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        return when <= datetime.now(UTC)
    return False


def _login(client: TestClient, username: str, password: str) -> httpx.Response:
    return client.post(LOGIN_PATH, json={"username": username, "password": password})


def _token_from(response: httpx.Response, cookie_name: str) -> str:
    cookies = _cookies_named(response, cookie_name)
    assert len(cookies) == 1
    token = cookies[0][0]
    assert token
    return token


def _login_token(application: FastAPI, settings: Settings, username: str, password: str) -> str:
    response = _login(TestClient(application), username, password)
    assert response.status_code == 200
    return _token_from(response, settings.session_cookie_name)


def _with_cookie(application: FastAPI, cookie: tuple[str, str] | None) -> TestClient:
    """A fresh client carrying exactly this cookie (or none)."""
    fresh = TestClient(application)
    if cookie is not None:
        fresh.cookies.set(cookie[0], cookie[1])
    return fresh


def _me(application: FastAPI, cookie: tuple[str, str] | None) -> httpx.Response:
    return _with_cookie(application, cookie).get(ME_PATH)


def _logout(application: FastAPI, cookie: tuple[str, str] | None) -> httpx.Response:
    return _with_cookie(application, cookie).post(LOGOUT_PATH)


def _assert_envelope(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error, dict)
    assert error["code"] == code
    return body


# =========================================================================== DoD-1


def test_correct_login_answers_200__DoD1(client: TestClient) -> None:
    """DoD-1 — US-004.AC-1: a correct pair for an enabled account answers 200."""
    assert _login(client, ADMIN_NAME, ADMIN_PASSWORD).status_code == 200


def test_correct_login_sets_the_configured_session_cookie__DoD1(client: TestClient, db_settings: Settings) -> None:
    """DoD-1 — the response carries a ``Set-Cookie`` for the configured session cookie name."""
    response = _login(client, PLAYER_NAME, PLAYER_PASSWORD)
    assert response.status_code == 200
    cookies = _cookies_named(response, db_settings.session_cookie_name)
    assert len(cookies) == 1
    assert cookies[0][0] != ""


@pytest.mark.parametrize(
    ("user_id", "username", "password"),
    [(ADMIN_ID, ADMIN_NAME, ADMIN_PASSWORD), (PLAYER_ID, PLAYER_NAME, PLAYER_PASSWORD)],
    ids=["admin", "roleplayer"],
)
def test_correct_login_leaves_exactly_one_live_session_for_that_user__DoD1(
    client: TestClient, engine: Engine, user_id: int, username: str, password: str
) -> None:
    """DoD-1 — afterwards exactly one live ``auth_sessions`` row exists for that user, none for others."""
    assert _session_count(engine) == 0
    assert _login(client, username, password).status_code == 200
    rows = _session_rows(engine)
    assert len(rows) == 1
    assert rows[0]["user_id"] == user_id
    assert rows[0]["revoked_at"] is None
    assert _parse_utc(rows[0]["expires_at"]) > datetime.now(UTC)


def test_the_cookie_token_resolves_to_the_session_the_login_opened__DoD1(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-1 — the cookie's token is the live session's token: the service resolves it to that user."""
    token = _login_token(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    with engine.connect() as connection:
        resolved = resolve_session(connection, token)
    assert resolved is not None
    assert resolved.id == PLAYER_ID
    assert resolved.username == PLAYER_NAME
    assert resolved.role == Role.ROLEPLAYER


# =========================================================================== DoD-2


@pytest.mark.parametrize(
    ("user_id", "username", "password", "role"),
    [
        (ADMIN_ID, ADMIN_NAME, ADMIN_PASSWORD, Role.ADMIN),
        (PLAYER_ID, PLAYER_NAME, PLAYER_PASSWORD, Role.ROLEPLAYER),
    ],
    ids=["admin", "roleplayer"],
)
def test_login_body_carries_id_username_and_role__DoD2(
    client: TestClient, user_id: int, username: str, password: str, role: Role
) -> None:
    """DoD-2 — the body names the caller: id, username, role."""
    body = _login(client, username, password).json()
    assert body["id"] == str(user_id)
    assert body["username"] == username
    assert body["role"] == role.value


def test_login_body_id_is_a_decimal_string_never_a_number__DoD2(client: TestClient) -> None:
    """DoD-2 — the id crosses the wire as a decimal string, not a JSON number."""
    body = _login(client, ADMIN_NAME, ADMIN_PASSWORD).json()
    assert isinstance(body["id"], str)
    assert not isinstance(body["id"], bool | int | float)
    assert body["id"].isdecimal()
    assert int(body["id"]) == ADMIN_ID


def test_login_body_carries_no_token_expiry_or_session_field__DoD2(
    client: TestClient, db_settings: Settings
) -> None:
    """DoD-2 — no token, expiry or session field; the token appears nowhere in the body."""
    response = _login(client, ADMIN_NAME, ADMIN_PASSWORD)
    body = response.json()
    assert set(body) == {"id", "username", "role"}
    for key in body:
        lowered = key.lower()
        for forbidden in ("token", "expir", "session", "cookie"):
            assert forbidden not in lowered
    token = _token_from(response, db_settings.session_cookie_name)
    assert token not in response.text


# =========================================================================== DoD-3


def test_login_cookie_carries_the_d6_flags__DoD3(client: TestClient, db_settings: Settings) -> None:
    """DoD-3 — HttpOnly, SameSite=Lax, Path=/, no Secure, Max-Age = default TTL in seconds (D6)."""
    response = _login(client, ADMIN_NAME, ADMIN_PASSWORD)
    cookies = _cookies_named(response, db_settings.session_cookie_name)
    assert len(cookies) == 1
    _, attributes = cookies[0]
    assert "httponly" in attributes
    assert (attributes.get("samesite") or "").lower() == "lax"
    assert attributes.get("path") == "/"
    assert "secure" not in attributes
    assert attributes.get("max-age") == str(db_settings.session_ttl_hours * 3600)


@pytest.mark.parametrize("ttl_hours", [5, 48])
def test_login_cookie_max_age_follows_the_ttl_setting__DoD3(
    application: FastAPI, db_settings: Settings, ttl_hours: int
) -> None:
    """DoD-3 — overriding ``session_ttl_hours`` changes the cookie's ``Max-Age`` to match."""
    changed = db_settings.model_copy(update={"session_ttl_hours": ttl_hours})
    application.dependency_overrides[get_settings] = lambda: changed
    response = _login(TestClient(application), ADMIN_NAME, ADMIN_PASSWORD)
    assert response.status_code == 200
    cookies = _cookies_named(response, changed.session_cookie_name)
    assert len(cookies) == 1
    assert cookies[0][1].get("max-age") == str(ttl_hours * 3600)


def test_overriding_the_cookie_name_renames_the_login_cookie__DoD3(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-3 — with ``session_cookie_name`` overridden, the cookie is set under the new name only."""
    default_name = db_settings.session_cookie_name
    assert default_name != OTHER_COOKIE_NAME
    renamed = db_settings.model_copy(update={"session_cookie_name": OTHER_COOKIE_NAME})
    application.dependency_overrides[get_settings] = lambda: renamed
    response = _login(TestClient(application), ADMIN_NAME, ADMIN_PASSWORD)
    assert response.status_code == 200
    assert len(_cookies_named(response, OTHER_COOKIE_NAME)) == 1
    assert _cookies_named(response, default_name) == []


def test_renamed_login_cookie_is_accepted_by_me__DoD3(application: FastAPI, db_settings: Settings) -> None:
    """DoD-3 — the renamed cookie is the one the rest of the app then honours."""
    renamed = db_settings.model_copy(update={"session_cookie_name": OTHER_COOKIE_NAME})
    application.dependency_overrides[get_settings] = lambda: renamed
    token = _login_token(application, renamed, PLAYER_NAME, PLAYER_PASSWORD)
    assert _me(application, (OTHER_COOKIE_NAME, token)).status_code == 200


# =========================================================================== DoD-4


REFUSED_PAIRS = [
    ("no-such-user", ADMIN_PASSWORD),
    (ADMIN_NAME, "not the password"),
    (DISABLED_NAME, DISABLED_PASSWORD),
]
REFUSED_IDS = ["unknown-username", "wrong-password", "disabled-account-correct-password"]


@pytest.mark.parametrize(("username", "password"), REFUSED_PAIRS, ids=REFUSED_IDS)
def test_refused_login_answers_400_invalid_credentials__DoD4(
    client: TestClient, username: str, password: str
) -> None:
    """DoD-4 — US-005.AC-1 / US-006.AC-1: 400 with ``{"error": {"code": "invalid_credentials", ...}}``."""
    response = _login(client, username, password)
    body = _assert_envelope(response, 400, INVALID_CREDENTIALS)
    assert set(body["error"]) == {"code", "message", "detail"}


@pytest.mark.parametrize(("username", "password"), REFUSED_PAIRS, ids=REFUSED_IDS)
def test_refused_login_sets_no_cookie__DoD4(client: TestClient, username: str, password: str) -> None:
    """DoD-4 — a refusal sets no cookie at all."""
    response = _login(client, username, password)
    assert response.status_code == 400
    assert _set_cookie_headers(response) == []
    assert len(client.cookies) == 0


@pytest.mark.parametrize(("username", "password"), REFUSED_PAIRS, ids=REFUSED_IDS)
def test_refused_login_creates_no_session_row__DoD4(
    client: TestClient, engine: Engine, username: str, password: str
) -> None:
    """DoD-4 — a refusal writes no ``auth_sessions`` row."""
    _login(client, username, password)
    assert _session_count(engine) == 0


def test_the_three_refusals_are_indistinguishable__DoD4(client: TestClient) -> None:
    """DoD-4 / D1 — same status, same code, same message (and the whole body) in all three cases."""
    responses = [_login(client, username, password) for username, password in REFUSED_PAIRS]
    statuses = {response.status_code for response in responses}
    bodies = [response.json() for response in responses]
    assert statuses == {400}
    assert {body["error"]["code"] for body in bodies} == {INVALID_CREDENTIALS}
    assert len({body["error"]["message"] for body in bodies}) == 1
    assert all(body == bodies[0] for body in bodies)


def test_refusal_does_not_echo_the_username__DoD4(client: TestClient) -> None:
    """DoD-4 / D1 — the body says nothing about which username was tried."""
    response = _login(client, DISABLED_NAME, DISABLED_PASSWORD)
    assert response.status_code == 400
    assert DISABLED_NAME not in response.text


# =========================================================================== DoD-5


NEVER_401_PAYLOADS: list[tuple[str, Any]] = [
    ("correct", {"username": ADMIN_NAME, "password": ADMIN_PASSWORD}),
    ("unknown-user", {"username": "no-such-user", "password": "whatever"}),
    ("wrong-password", {"username": ADMIN_NAME, "password": "nope"}),
    ("disabled", {"username": DISABLED_NAME, "password": DISABLED_PASSWORD}),
    ("empty-username", {"username": "", "password": ADMIN_PASSWORD}),
    ("empty-password", {"username": ADMIN_NAME, "password": ""}),
    ("both-empty", {"username": "", "password": ""}),
    ("missing-password", {"username": ADMIN_NAME}),
    ("missing-username", {"password": ADMIN_PASSWORD}),
    ("empty-object", {}),
    ("wrong-types", {"username": 12, "password": None}),
    ("json-array", [ADMIN_NAME, ADMIN_PASSWORD]),
    ("json-null", None),
]


@pytest.mark.parametrize(
    "payload", [p for _, p in NEVER_401_PAYLOADS], ids=[name for name, _ in NEVER_401_PAYLOADS]
)
def test_login_never_answers_401_for_any_json_body__DoD5(client: TestClient, payload: Any) -> None:
    """DoD-5 — US-005.AC-2 / US-006.AC-2 / D2: whatever the body, the login route never says 401."""
    response = client.post(LOGIN_PATH, json=payload)
    assert response.status_code != 401


@pytest.mark.parametrize(
    ("content", "content_type"),
    [
        (b"", None),
        (b"not json at all", "application/json"),
        (b"username=a&password=b", "application/x-www-form-urlencoded"),
    ],
    ids=["no-body", "malformed-json", "form-encoded"],
)
def test_login_never_answers_401_for_malformed_bodies__DoD5(
    client: TestClient, content: bytes, content_type: str | None
) -> None:
    """DoD-5 — an empty or malformed body is not a 401 either."""
    headers = {"content-type": content_type} if content_type else {}
    response = client.post(LOGIN_PATH, content=content, headers=headers)
    assert response.status_code != 401


@pytest.mark.parametrize("cookie_kind", ["unissued", "revoked", "expired", "live"])
@pytest.mark.parametrize(("username", "password"), REFUSED_PAIRS + [(ADMIN_NAME, ADMIN_PASSWORD)])
def test_login_never_answers_401_whatever_cookie_is_already_held__DoD5(
    application: FastAPI,
    db_settings: Settings,
    engine: Engine,
    cookie_kind: str,
    username: str,
    password: str,
) -> None:
    """DoD-5 — the login route carries no auth dependency: a dead or live cookie never makes it 401."""
    if cookie_kind == "unissued":
        token = UNISSUED_TOKEN
    else:
        token = _login_token(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
        if cookie_kind == "revoked":
            with engine.connect() as connection:
                revoke_session(connection, token)
        elif cookie_kind == "expired":
            _expire_all_sessions_of(engine, PLAYER_ID)
    response = _with_cookie(application, (db_settings.session_cookie_name, token)).post(
        LOGIN_PATH, json={"username": username, "password": password}
    )
    assert response.status_code != 401
    assert response.status_code in (200, 400)


# =========================================================================== DoD-6


EMPTY_PAYLOADS = [
    {"username": "", "password": ADMIN_PASSWORD},
    {"username": ADMIN_NAME, "password": ""},
    {"username": "", "password": ""},
]
EMPTY_IDS = ["empty-username", "empty-password", "both-empty"]


@pytest.mark.parametrize("payload", EMPTY_PAYLOADS, ids=EMPTY_IDS)
def test_empty_credential_is_refused_with_422__DoD6(client: TestClient, payload: dict[str, str]) -> None:
    """DoD-6 — the non-empty backstop answers FastAPI's own 422, never a success."""
    response = client.post(LOGIN_PATH, json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize("payload", EMPTY_PAYLOADS, ids=EMPTY_IDS)
def test_empty_credential_writes_no_session_and_sets_no_cookie__DoD6(
    client: TestClient, engine: Engine, payload: dict[str, str]
) -> None:
    """DoD-6 — refused before anything is written: no ``auth_sessions`` row, no cookie."""
    response = client.post(LOGIN_PATH, json=payload)
    assert _session_count(engine) == 0
    assert _set_cookie_headers(response) == []


def test_empty_credential_refusal_adds_no_domain_error_code__DoD6(client: TestClient) -> None:
    """DoD-6 — the backstop is not the domain-error envelope and invents no code."""
    body = client.post(LOGIN_PATH, json={"username": "", "password": ""}).json()
    envelope = body.get("error") if isinstance(body, dict) else None
    assert not (isinstance(envelope, dict) and "code" in envelope)


# =========================================================================== DoD-7


@pytest.mark.parametrize(
    "username",
    [" " + ADMIN_NAME, ADMIN_NAME + " ", " " + ADMIN_NAME + " ", ADMIN_NAME.upper(), ADMIN_NAME.capitalize()],
    ids=["leading-space", "trailing-space", "both-spaces", "upper-case", "capitalized"],
)
def test_username_variant_is_refused__DoD7(client: TestClient, engine: Engine, username: str) -> None:
    """DoD-7 / D13 — a username differing only by surrounding whitespace or case is refused."""
    response = _login(client, username, ADMIN_PASSWORD)
    _assert_envelope(response, 400, INVALID_CREDENTIALS)
    assert _session_count(engine) == 0


@pytest.mark.parametrize(
    "password",
    [" " + ADMIN_PASSWORD, ADMIN_PASSWORD + " ", ADMIN_PASSWORD.upper(), ADMIN_PASSWORD.capitalize()],
    ids=["leading-space", "trailing-space", "upper-case", "capitalized"],
)
def test_password_variant_is_refused__DoD7(client: TestClient, engine: Engine, password: str) -> None:
    """DoD-7 / D13 — a password differing only by surrounding whitespace or case is refused."""
    response = _login(client, ADMIN_NAME, password)
    _assert_envelope(response, 400, INVALID_CREDENTIALS)
    assert _session_count(engine) == 0


def test_exact_credential_still_succeeds_after_variants_are_refused__DoD7(
    client: TestClient, engine: Engine
) -> None:
    """DoD-7 — the account's own exact credential still succeeds."""
    assert _login(client, ADMIN_NAME.upper(), ADMIN_PASSWORD).status_code == 400
    assert _login(client, ADMIN_NAME, ADMIN_PASSWORD + " ").status_code == 400
    response = _login(client, ADMIN_NAME, ADMIN_PASSWORD)
    assert response.status_code == 200
    assert response.json()["username"] == ADMIN_NAME
    assert len(_live_rows_for(engine, ADMIN_ID)) == 1


def test_stored_whitespace_is_part_of_the_credential__DoD7(client: TestClient, engine: Engine) -> None:
    """DoD-7 / D13 — an account created as " spaced" is reachable only as " spaced", with its padded password."""
    assert _login(client, SPACED_NAME.strip(), SPACED_PASSWORD).status_code == 400
    assert _login(client, SPACED_NAME, SPACED_PASSWORD.strip()).status_code == 400
    assert _session_count(engine) == 0
    response = _login(client, SPACED_NAME, SPACED_PASSWORD)
    assert response.status_code == 200
    assert response.json()["username"] == SPACED_NAME
    assert len(_live_rows_for(engine, SPACED_ID)) == 1


# =========================================================================== DoD-8


@pytest.mark.parametrize(
    ("user_id", "username", "password", "role"),
    [
        (ADMIN_ID, ADMIN_NAME, ADMIN_PASSWORD, Role.ADMIN),
        (PLAYER_ID, PLAYER_NAME, PLAYER_PASSWORD, Role.ROLEPLAYER),
    ],
    ids=["admin", "roleplayer"],
)
def test_me_with_the_login_cookie_answers_the_identity__DoD8(
    application: FastAPI, db_settings: Settings, user_id: int, username: str, password: str, role: Role
) -> None:
    """DoD-8 — US-004.AC-1: ``GET /api/me`` with the login's cookie answers 200 with id, username, role."""
    token = _login_token(application, db_settings, username, password)
    response = _me(application, (db_settings.session_cookie_name, token))
    assert response.status_code == 200
    body = response.json()
    assert body == {"id": str(user_id), "username": username, "role": role.value}


def test_me_id_is_a_decimal_string__DoD8(application: FastAPI, db_settings: Settings) -> None:
    """DoD-8 — the id is a decimal string on ``/api/me`` too."""
    token = _login_token(application, db_settings, ADMIN_NAME, ADMIN_PASSWORD)
    body = _me(application, (db_settings.session_cookie_name, token)).json()
    assert isinstance(body["id"], str)
    assert body["id"].isdecimal()


def test_me_works_through_the_clients_own_cookie_jar__DoD8(client: TestClient) -> None:
    """DoD-8 — the same client that logged in is recognised on its next call, with no manual cookie."""
    assert _login(client, PLAYER_NAME, PLAYER_PASSWORD).status_code == 200
    response = client.get(ME_PATH)
    assert response.status_code == 200
    assert response.json() == {"id": str(PLAYER_ID), "username": PLAYER_NAME, "role": Role.ROLEPLAYER.value}


# =========================================================================== DoD-9


def _dead_cookie_token(kind: str, application: FastAPI, settings: Settings, engine: Engine) -> str:
    if kind == "unissued":
        _login_token(application, settings, PLAYER_NAME, PLAYER_PASSWORD)  # a live session exists, not this one
        return UNISSUED_TOKEN
    token = _login_token(application, settings, PLAYER_NAME, PLAYER_PASSWORD)
    if kind == "revoked":
        with engine.connect() as connection:
            revoke_session(connection, token)
    elif kind == "expired":
        _expire_all_sessions_of(engine, PLAYER_ID)
    elif kind == "disabled":
        _set_enabled(engine, PLAYER_ID, False)
    else:  # pragma: no cover - parametrization guard
        raise AssertionError(kind)
    return token


def test_me_without_a_cookie_answers_401__DoD9(application: FastAPI) -> None:
    """DoD-9 — no cookie: 401 ``not_authenticated``."""
    _assert_envelope(_me(application, None), 401, NOT_AUTHENTICATED)


@pytest.mark.parametrize("kind", ["unissued", "revoked", "expired", "disabled"])
def test_me_with_a_dead_session_answers_401__DoD9(
    application: FastAPI, db_settings: Settings, engine: Engine, kind: str
) -> None:
    """DoD-9 — US-007.AC-2 / US-006.AC-1: unissued, revoked, expired, since-disabled all answer 401."""
    token = _dead_cookie_token(kind, application, db_settings, engine)
    response = _me(application, (db_settings.session_cookie_name, token))
    _assert_envelope(response, 401, NOT_AUTHENTICATED)


@pytest.mark.parametrize("kind", ["revoked", "expired", "disabled"])
def test_me_accepted_the_same_cookie_before_it_died__DoD9(
    application: FastAPI, db_settings: Settings, engine: Engine, kind: str
) -> None:
    """DoD-9 — control: the same token answered 200 before it was revoked / expired / disabled."""
    token = _login_token(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    cookie = (db_settings.session_cookie_name, token)
    assert _me(application, cookie).status_code == 200
    if kind == "revoked":
        with engine.connect() as connection:
            revoke_session(connection, token)
    elif kind == "expired":
        _expire_all_sessions_of(engine, PLAYER_ID)
    else:
        _set_enabled(engine, PLAYER_ID, False)
    _assert_envelope(_me(application, cookie), 401, NOT_AUTHENTICATED)


# =========================================================================== DoD-10


def test_logout_on_a_live_session_answers_204__DoD10(application: FastAPI, db_settings: Settings) -> None:
    """DoD-10 — US-007.AC-1: logging out of a live session answers 204."""
    token = _login_token(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    response = _logout(application, (db_settings.session_cookie_name, token))
    assert response.status_code == 204
    assert response.content == b""


def test_logout_on_a_live_session_clears_the_cookie__DoD10(application: FastAPI, db_settings: Settings) -> None:
    """DoD-10 — the response clears the configured cookie at ``Path=/``."""
    token = _login_token(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    response = _logout(application, (db_settings.session_cookie_name, token))
    cookies = _cookies_named(response, db_settings.session_cookie_name)
    assert len(cookies) == 1
    value, attributes = cookies[0]
    assert value != token
    assert attributes.get("path") == "/"
    assert _is_cleared(value, attributes)


def test_logout_marks_that_session_revoked__DoD10(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-10 — the session row is kept and marked revoked."""
    token = _login_token(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    assert len(_live_rows_for(engine, PLAYER_ID)) == 1
    _logout(application, (db_settings.session_cookie_name, token))
    rows = [row for row in _session_rows(engine) if row["user_id"] == PLAYER_ID]
    assert len(rows) == 1
    assert rows[0]["revoked_at"] is not None
    with engine.connect() as connection:
        assert resolve_session(connection, token) is None


def test_same_cookie_answers_401_on_me_right_after_logout__DoD10(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-10 — re-sending the very same cookie to ``GET /api/me`` immediately afterwards answers 401."""
    token = _login_token(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    cookie = (db_settings.session_cookie_name, token)
    assert _me(application, cookie).status_code == 200
    assert _logout(application, cookie).status_code == 204
    _assert_envelope(_me(application, cookie), 401, NOT_AUTHENTICATED)


def test_logout_through_the_clients_own_jar_ends_its_session__DoD10(client: TestClient) -> None:
    """DoD-10 — the natural flow: log in, log out, and the same client is no longer recognised."""
    assert _login(client, ADMIN_NAME, ADMIN_PASSWORD).status_code == 200
    assert client.get(ME_PATH).status_code == 200
    assert client.post(LOGOUT_PATH).status_code == 204
    assert client.get(ME_PATH).status_code == 401


# =========================================================================== DoD-11


def _logout_cookie(
    kind: str, application: FastAPI, settings: Settings, engine: Engine
) -> tuple[str, str] | None:
    if kind == "no-cookie":
        return None
    if kind == "unissued":
        return (settings.session_cookie_name, UNISSUED_TOKEN)
    token = _login_token(application, settings, PLAYER_NAME, PLAYER_PASSWORD)
    if kind == "revoked":
        with engine.connect() as connection:
            revoke_session(connection, token)
    elif kind == "expired":
        _expire_all_sessions_of(engine, PLAYER_ID)
    else:  # pragma: no cover - parametrization guard
        raise AssertionError(kind)
    return (settings.session_cookie_name, token)


DEAD_LOGOUT_KINDS = ["no-cookie", "unissued", "revoked", "expired"]


@pytest.mark.parametrize("kind", DEAD_LOGOUT_KINDS)
def test_logout_without_a_live_session_answers_204__DoD11(
    application: FastAPI, db_settings: Settings, engine: Engine, kind: str
) -> None:
    """DoD-11 / D9 — no cookie, unissued, revoked or expired: the same 204, never 401, never an error."""
    response = _logout(application, _logout_cookie(kind, application, db_settings, engine))
    assert response.status_code == 204
    assert response.status_code != 401


@pytest.mark.parametrize("kind", DEAD_LOGOUT_KINDS)
def test_logout_without_a_live_session_still_clears_the_cookie__DoD11(
    application: FastAPI, db_settings: Settings, engine: Engine, kind: str
) -> None:
    """DoD-11 / D9 — the cookie is cleared either way."""
    response = _logout(application, _logout_cookie(kind, application, db_settings, engine))
    cookies = _cookies_named(response, db_settings.session_cookie_name)
    assert len(cookies) == 1
    value, attributes = cookies[0]
    assert attributes.get("path") == "/"
    assert _is_cleared(value, attributes)


def test_dead_and_live_logouts_answer_the_same__DoD11(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-11 / D9 — a logout reveals nothing: live and every dead case share status and body."""
    token = _login_token(application, db_settings, ADMIN_NAME, ADMIN_PASSWORD)
    live = _logout(application, (db_settings.session_cookie_name, token))
    for kind in DEAD_LOGOUT_KINDS:
        dead = _logout(application, _logout_cookie(kind, application, db_settings, engine))
        assert dead.status_code == live.status_code == 204
        assert dead.content == live.content


def test_logging_out_twice_answers_204_both_times__DoD11(application: FastAPI, db_settings: Settings) -> None:
    """DoD-11 — a second logout with the already-revoked cookie is the same 204."""
    token = _login_token(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    cookie = (db_settings.session_cookie_name, token)
    assert _logout(application, cookie).status_code == 204
    assert _logout(application, cookie).status_code == 204


def test_logout_with_a_dead_cookie_leaves_other_sessions_live__DoD11(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-11 — an unissued token revokes nothing that exists."""
    token = _login_token(application, db_settings, ADMIN_NAME, ADMIN_PASSWORD)
    assert _logout(application, (db_settings.session_cookie_name, UNISSUED_TOKEN)).status_code == 204
    assert len(_live_rows_for(engine, ADMIN_ID)) == 1
    assert _me(application, (db_settings.session_cookie_name, token)).status_code == 200


# =========================================================================== DoD-12


def test_two_logins_produce_two_live_sessions__DoD12(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-12 — a second login mints a second row; both tokens are live and distinct."""
    first = _login_token(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    second = _login_token(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    assert first != second
    live = _live_rows_for(engine, PLAYER_ID)
    assert len(live) == 2
    assert live[0]["id"] != live[1]["id"]
    assert _me(application, (db_settings.session_cookie_name, first)).status_code == 200
    assert _me(application, (db_settings.session_cookie_name, second)).status_code == 200


def test_logout_revokes_only_the_calling_session__DoD12(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-12 — logging one out leaves the other working."""
    name = db_settings.session_cookie_name
    first = _login_token(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    second = _login_token(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)

    assert _logout(application, (name, first)).status_code == 204

    _assert_envelope(_me(application, (name, first)), 401, NOT_AUTHENTICATED)
    assert _me(application, (name, second)).status_code == 200
    rows = [row for row in _session_rows(engine) if row["user_id"] == PLAYER_ID]
    assert len(rows) == 2
    assert sorted(row["revoked_at"] is None for row in rows) == [False, True]


def test_logout_leaves_another_users_session_alone__DoD12(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-12 — logout is scoped to the calling session, never to anyone else's."""
    name = db_settings.session_cookie_name
    player = _login_token(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    admin = _login_token(application, db_settings, ADMIN_NAME, ADMIN_PASSWORD)
    assert _logout(application, (name, player)).status_code == 204
    assert _me(application, (name, admin)).status_code == 200
    assert len(_live_rows_for(engine, ADMIN_ID)) == 1


# =========================================================================== DoD-13


def test_database_contact_goes_only_through_the_connection_dependency__DoD13(
    application: FastAPI, db_settings: Settings, engine: Engine, tmp_path: Path
) -> None:
    """DoD-13 — redirect ``get_connection`` elsewhere: authentication and the session happen there only."""
    alternate_settings = db_settings.model_copy(
        update={"data_dir": tmp_path / "alternate", "db_filename": "alternate.sqlite"}
    )
    alternate_engine = get_engine(alternate_settings)
    with alternate_engine.begin() as connection:
        schema.metadata.create_all(connection)
    alternate_name = "only-in-the-alternate"
    alternate_password = "alternate password"
    alternate_id = 8_100_001
    _insert_user(
        alternate_engine,
        user_id=alternate_id,
        username=alternate_name,
        password=alternate_password,
        role=Role.ROLEPLAYER,
    )

    def alternate_connection() -> Iterator[Connection]:
        connection = alternate_engine.connect()
        try:
            yield connection
        finally:
            connection.close()

    application.dependency_overrides[get_connection] = alternate_connection

    # An account that exists only in the settings database is unknown through the dependency.
    assert _login(TestClient(application), ADMIN_NAME, ADMIN_PASSWORD).status_code == 400

    response = _login(TestClient(application), alternate_name, alternate_password)
    assert response.status_code == 200
    assert response.json()["id"] == str(alternate_id)
    assert len(_live_rows_for(alternate_engine, alternate_id)) == 1
    assert _session_count(engine) == 0

    token = _token_from(response, db_settings.session_cookie_name)
    assert _logout(application, (db_settings.session_cookie_name, token)).status_code == 204
    assert _live_rows_for(alternate_engine, alternate_id) == []


def test_session_id_comes_from_the_generator_on_application_state__DoD13(
    application: FastAPI, client: TestClient, engine: Engine
) -> None:
    """DoD-13 — the generator the route passes down is the one on ``app.state``, not a module global."""
    generator = _FixedIdGenerator(FIXED_SESSION_ID)
    application.state.id_generator = generator
    assert _login(client, PLAYER_NAME, PLAYER_PASSWORD).status_code == 200
    rows = _session_rows(engine)
    assert [row["id"] for row in rows] == [FIXED_SESSION_ID]
    assert generator.calls >= 1


def test_generator_is_per_application_not_shared__DoD13(
    db_settings: Settings, engine: Engine
) -> None:
    """DoD-13 — two applications with two generators each mint from their own."""
    first_id, second_id = 913_000_000_000_001, 913_000_000_000_002
    first_app, second_app = create_app(), create_app()
    for app, value in ((first_app, first_id), (second_app, second_id)):
        app.dependency_overrides[get_settings] = lambda: db_settings
        app.state.id_generator = _FixedIdGenerator(value)
    try:
        assert _login(TestClient(first_app), PLAYER_NAME, PLAYER_PASSWORD).status_code == 200
        assert _login(TestClient(second_app), ADMIN_NAME, ADMIN_PASSWORD).status_code == 200
    finally:
        first_app.dependency_overrides.clear()
        second_app.dependency_overrides.clear()
    ids_by_user = {row["user_id"]: row["id"] for row in _session_rows(engine)}
    assert ids_by_user == {PLAYER_ID: first_id, ADMIN_ID: second_id}


@pytest.mark.parametrize("ttl_hours", [1, 720])
def test_stored_session_values_come_from_the_service_with_the_settings_ttl__DoD13(
    application: FastAPI, db_settings: Settings, engine: Engine, ttl_hours: int
) -> None:
    """DoD-13 — the row is the session service's: token stored only as a digest, expiry = created + TTL setting."""
    changed = db_settings.model_copy(update={"session_ttl_hours": ttl_hours})
    application.dependency_overrides[get_settings] = lambda: changed
    token = _login_token(application, changed, PLAYER_NAME, PLAYER_PASSWORD)
    rows = _session_rows(engine)
    assert len(rows) == 1
    row = rows[0]
    assert row["user_id"] == PLAYER_ID
    assert row["token_hash"] != token
    assert token not in row["token_hash"]
    assert row["revoked_at"] is None
    assert _parse_utc(row["expires_at"]) - _parse_utc(row["created_at"]) == timedelta(hours=ttl_hours)
    with engine.connect() as connection:
        resolved = resolve_session(connection, token)
    assert resolved is not None and resolved.id == PLAYER_ID
