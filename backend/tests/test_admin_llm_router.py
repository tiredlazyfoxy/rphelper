"""Tests for the admin LLM router: ``/api/admin/llm-servers`` and its nine routes.

Feature 006, step 005 (``005.admin-llm-router.md``). Every expected value comes from that
step's Interface intent and DoD-1 .. DoD-22, ``005.context.md`` and feature 006 ``context.md``
(D5 the kind literal, D6 the four-value taxonomy, D7 the codes and statuses, D8 the 422
posture, D9 the three pointer states, D10 persistent ``models`` rows, D14
``secret_ref_missing`` as 500, D17 the route table, R5 no reverse lookup, the JSON id
boundary). Bindings come from ``## Skeleton`` in feature 006's ``status.md`` (steps 001 ..
005), notably ``get_llm_client_factory`` — the dependency swapped through
``app.dependency_overrides`` so no test ever reaches the network.

The application is always the real factory's (``create_app()``), pinned to the per-test
database through ``dependency_overrides[get_settings]``; cookies are carried explicitly, as
in ``test_admin_users_router.py``.

Tests are suffixed ``__S006_005_DoD<n>``. DoD-23 .. DoD-26 are ``[manual/live]``.
"""

import json
from collections.abc import Iterator, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, Table, select

from app.config import Settings, get_settings
from app.db import schema
from app.db.engine import get_connection, get_engine
from app.errors import LlmUnreachableError
from app.main import create_app
from app.roles import Role
from app.routers.admin_llm import get_llm_client_factory
from app.routers.admin_llm import router as admin_llm_router
from app.services.llm.client import ProbeOutcome, ProbeResult
from app.services.passwords import hash_password

LIST_PATH = "/api/admin/llm-servers"
LOGIN_PATH = "/api/auth/login"

GUARD_PROBE_PATH = "/guard-probe"
GUARD_PROBE_FULL_PATH = "/api/admin/llm-servers/guard-probe"

CREATED_TEXT = "2026-01-01T00:00:00+00:00"
TESTED_TEXT = "2026-02-02T10:00:00+00:00"

ADMIN_ID = 8_000_001
ADMIN_NAME = "founder"
ADMIN_PASSWORD = "correct horse battery staple"

PLAYER_ID = 8_000_003
PLAYER_NAME = "wanderer"
PLAYER_PASSWORD = "a quiet river at dusk"

KEY_VARIABLE = "S006_005_API_KEY"
POINTER = "$" + KEY_VARIABLE
RESOLVED_KEY = "sk-S006-005-RESOLVED-CREDENTIAL"
NEW_KEY_VARIABLE = "S006_005_REPLACEMENT_KEY"
NEW_POINTER = "$" + NEW_KEY_VARIABLE
NEW_RESOLVED_KEY = "sk-S006-005-REPLACEMENT-CREDENTIAL"
MISSING_VARIABLE = "S006_005_ABSENT_VARIABLE"
MISSING_POINTER = "$" + MISSING_VARIABLE

PROVIDER_PROSE = "Provider says: your key sk-live-XYZ is revoked, contact billing"

# Seeded registrations.
SERVER_A = 7_000_001
SERVER_A_NAME = "local llamaswap"
SERVER_A_URL = "http://llm.test:8080"

SERVER_B = 7_000_002
SERVER_B_NAME = "hosted openai"
SERVER_B_URL = "https://api.example.test/v1"

SERVER_C = 7_000_003
SERVER_C_NAME = "misconfigured"
SERVER_C_URL = "http://broken.test:7000"

# DoD-21: beyond Number.MAX_SAFE_INTEGER; the neighbour is what a float round-trip collapses onto.
BIG_ID = 2**53 + 1  # 9007199254740993
BIG_ID_TEXT = "9007199254740993"
BIG_NAME = "far-numbered"
BIG_URL = "http://far.test:1111"
NEIGHBOR_ID = 2**53  # 9007199254740992
NEIGHBOR_NAME = "near-numbered"
NEIGHBOR_URL = "http://near.test:2222"

SEEDED_SERVER_IDS = {SERVER_A, SERVER_B, SERVER_C, BIG_ID, NEIGHBOR_ID}

UNKNOWN_ID = 7_999_999

# Seeded models rows (id, server, name, enabled, designated, dim).
SEEDED_MODELS: list[tuple[int, int, str, bool, bool, int | None]] = [
    (7_100_001, SERVER_A, "chat-a", True, False, None),
    (7_100_002, SERVER_A, "embed-a", True, True, 384),
    (7_100_003, SERVER_A, "retired-a", False, False, None),
    (7_100_004, SERVER_B, "chat-b", True, False, None),
]

NEW_SERVER_NAME = "fresh connection"
NEW_SERVER_URL = "http://fresh.test:3333"

FIXED_MINTED_ID = 914_000_000_000_001
BIG_MINTED_ID = 2**53 + 7  # 9007199254740999

OUTCOME_VALUES = {"reachable", "unreachable", "auth_failed", "model_list_empty"}

EXPECTED_SERVER_FIELDS = {
    "id",
    "name",
    "kind",
    "base_url",
    "has_api_key",
    "enabled_model_names",
    "embedding_model_name",
    "embedding_dim",
    "last_test_at",
    "last_test_ok",
    "last_test_error",
    "created_at",
    "updated_at",
}
LAST_TEST_FIELDS = {"last_test_at", "last_test_ok", "last_test_error"}
TEST_RESULT_FIELDS = {"outcome", "ok", "tested_at"}

NOT_AUTHENTICATED = "not_authenticated"
INSUFFICIENT_ROLE = "insufficient_role"
LLM_SERVER_NOT_FOUND = "llm_server_not_found"
LLM_UNREACHABLE = "llm_unreachable"
SECRET_REF_MISSING = "secret_ref_missing"


# --- fakes ---------------------------------------------------------------------------


class _FixedIdGenerator:
    """A generator stand-in whose ``next_id()`` always answers one known value."""

    def __init__(self, value: int) -> None:
        self.value = value
        self.calls = 0

    def next_id(self) -> int:
        self.calls += 1
        return self.value


class _SequenceIdGenerator:
    """A generator stand-in answering a known sequence of distinct ids."""

    def __init__(self, first: int) -> None:
        self.next_value = first
        self.minted: list[int] = []

    def next_id(self) -> int:
        value = self.next_value
        self.next_value += 1
        self.minted.append(value)
        return value


class _FakeClient:
    """Implements the frozen ``LlmClientLike`` protocol against its factory's configuration."""

    def __init__(self, factory: "_FakeFactory") -> None:
        self._factory = factory

    async def probe(self) -> ProbeResult:
        self._factory.probe_calls += 1
        return self._factory.probe_result

    async def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
        self._factory.embed_calls.append((model, list(texts)))
        if self._factory.embed_error is not None:
            raise self._factory.embed_error
        return [[0.25] * self._factory.embed_dim for _ in texts]


class _FakeFactory:
    """The client factory tests install; records every positional call."""

    def __init__(self) -> None:
        self.probe_result = ProbeResult(
            outcome=ProbeOutcome.REACHABLE, model_names=("model-one", "model-two"), note=PROVIDER_PROSE
        )
        self.embed_dim = 768
        self.embed_error: Exception | None = None
        self.calls: list[tuple[Any, ...]] = []
        self.probe_calls = 0
        self.embed_calls: list[tuple[str, list[str]]] = []

    def __call__(self, base_url: str, api_key: str | None, timeout_seconds: float) -> _FakeClient:
        self.calls.append((base_url, api_key, timeout_seconds))
        return _FakeClient(self)

    def answer(self, outcome: ProbeOutcome, names: Sequence[str] = ()) -> None:
        self.probe_result = ProbeResult(outcome=outcome, model_names=tuple(names), note=PROVIDER_PROSE)


# --- fixtures ------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _quiet_factory_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the factory's logging call so these tests touch no global sinks."""
    monkeypatch.setattr("app.main.configure_logging", lambda settings: None)


@pytest.fixture(autouse=True)
def _pointer_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(KEY_VARIABLE, RESOLVED_KEY)
    monkeypatch.setenv(NEW_KEY_VARIABLE, NEW_RESOLVED_KEY)
    monkeypatch.delenv(MISSING_VARIABLE, raising=False)


def _servers() -> Table:
    return schema.metadata.tables["llm_servers"]


def _models() -> Table:
    return schema.metadata.tables["models"]


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
                created_at=CREATED_TEXT,
                updated_at=CREATED_TEXT,
            )
        )


def _insert_server(
    engine: Engine,
    *,
    server_id: int,
    name: str,
    kind: str,
    base_url: str,
    api_key_ref: str | None = None,
    last_test_at: str | None = None,
    last_test_ok: bool | None = None,
    last_test_error: str | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            _servers()
            .insert()
            .values(
                id=server_id,
                name=name,
                kind=kind,
                base_url=base_url,
                api_key_ref=api_key_ref,
                last_test_at=last_test_at,
                last_test_ok=last_test_ok,
                last_test_error=last_test_error,
                created_at=CREATED_TEXT,
                updated_at=CREATED_TEXT,
            )
        )


def _insert_model(
    engine: Engine,
    *,
    model_id: int,
    server_id: int,
    name: str,
    enabled: bool,
    designated: bool,
    dim: int | None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            _models()
            .insert()
            .values(
                id=model_id,
                server_id=server_id,
                model_name=name,
                is_enabled=enabled,
                is_embedding_designated=designated,
                embedding_dim=dim,
                created_at=CREATED_TEXT,
                updated_at=CREATED_TEXT,
            )
        )


def _seed(engine: Engine) -> None:
    with engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(engine, user_id=ADMIN_ID, username=ADMIN_NAME, password=ADMIN_PASSWORD, role=Role.ADMIN)
    _insert_user(engine, user_id=PLAYER_ID, username=PLAYER_NAME, password=PLAYER_PASSWORD, role=Role.ROLEPLAYER)
    _insert_server(
        engine,
        server_id=SERVER_A,
        name=SERVER_A_NAME,
        kind="llamaswap",
        base_url=SERVER_A_URL,
        api_key_ref=POINTER,
        last_test_at=TESTED_TEXT,
        last_test_ok=True,
        last_test_error=None,
    )
    _insert_server(engine, server_id=SERVER_B, name=SERVER_B_NAME, kind="openai", base_url=SERVER_B_URL)
    _insert_server(
        engine,
        server_id=SERVER_C,
        name=SERVER_C_NAME,
        kind="openai",
        base_url=SERVER_C_URL,
        api_key_ref=MISSING_POINTER,
        last_test_at=TESTED_TEXT,
        last_test_ok=False,
        last_test_error="auth_failed",
    )
    _insert_server(engine, server_id=BIG_ID, name=BIG_NAME, kind="llamaswap", base_url=BIG_URL)
    _insert_server(engine, server_id=NEIGHBOR_ID, name=NEIGHBOR_NAME, kind="llamaswap", base_url=NEIGHBOR_URL)
    for model_id, server_id, name, enabled, designated, dim in SEEDED_MODELS:
        _insert_model(
            engine,
            model_id=model_id,
            server_id=server_id,
            name=name,
            enabled=enabled,
            designated=designated,
            dim=dim,
        )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    _seed(db_engine)
    return db_engine


@pytest.fixture
def fake() -> _FakeFactory:
    return _FakeFactory()


@pytest.fixture
def application(db_settings: Settings, engine: Engine, fake: _FakeFactory) -> Iterator[FastAPI]:
    """The factory's application, pinned to the seeded database, with the fake client factory."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: db_settings
    app.dependency_overrides[get_llm_client_factory] = lambda: fake
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def guarded_probe_app(db_settings: Settings, engine: Engine, fake: _FakeFactory) -> Iterator[FastAPI]:
    """DoD-5 — an app whose LLM router carries a second, test-only route with no dependency of its own.

    The route is registered on the **same** router object the production module exports,
    before the factory includes it, and removed again afterwards.
    """

    def guard_probe() -> dict[str, bool]:
        return {"reached": True}

    before = list(admin_llm_router.routes)
    admin_llm_router.add_api_route(GUARD_PROBE_PATH, guard_probe, methods=["GET"])
    added = [route for route in admin_llm_router.routes if route not in before]
    try:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: db_settings
        app.dependency_overrides[get_llm_client_factory] = lambda: fake
        try:
            yield app
        finally:
            app.dependency_overrides.clear()
    finally:
        for route in added:
            admin_llm_router.routes.remove(route)


# --- helpers -------------------------------------------------------------------------


def _path(server_id: int | str, suffix: str = "") -> str:
    return f"{LIST_PATH}/{server_id}{suffix}"


def _parse_set_cookie(header: str) -> tuple[str, str]:
    first = header.split(";")[0]
    name, _, value = first.partition("=")
    return name.strip(), value.strip().strip('"')


def _login_token(application: FastAPI, settings: Settings, username: str, password: str) -> str:
    response = TestClient(application).post(LOGIN_PATH, json={"username": username, "password": password})
    assert response.status_code == 200
    tokens = [
        value
        for name, value in (_parse_set_cookie(h) for h in response.headers.get_list("set-cookie"))
        if name == settings.session_cookie_name
    ]
    assert len(tokens) == 1
    assert tokens[0]
    return tokens[0]


def _with_cookie(application: FastAPI, settings: Settings, token: str | None) -> TestClient:
    fresh = TestClient(application)
    if token is not None:
        fresh.cookies.set(settings.session_cookie_name, token)
    return fresh


def _as(application: FastAPI, settings: Settings, username: str, password: str) -> TestClient:
    return _with_cookie(application, settings, _login_token(application, settings, username, password))


def _admin(application: FastAPI, settings: Settings) -> TestClient:
    return _as(application, settings, ADMIN_NAME, ADMIN_PASSWORD)


def _send(client: TestClient, method: str, path: str, body: dict[str, Any] | None) -> httpx.Response:
    if body is None:
        return client.request(method, path)
    return client.request(method, path, json=body)


def _assert_envelope(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error, dict)
    assert error["code"] == code
    return error


def _assert_not_domain_envelope(response: httpx.Response) -> None:
    body = response.json()
    envelope = body.get("error") if isinstance(body, dict) else None
    assert not (isinstance(envelope, dict) and "code" in envelope)


def _assert_id_text(value: Any) -> None:
    assert isinstance(value, str)
    assert not isinstance(value, bool | int | float)
    assert value.isdecimal()


def _assert_server_shape(entry: Any) -> None:
    assert isinstance(entry, dict)
    assert set(entry) == EXPECTED_SERVER_FIELDS
    _assert_id_text(entry["id"])
    assert isinstance(entry["name"], str)
    assert entry["kind"] in {"llamaswap", "openai"}
    assert isinstance(entry["base_url"], str)
    assert isinstance(entry["has_api_key"], bool)
    assert isinstance(entry["enabled_model_names"], list)
    assert all(isinstance(name, str) for name in entry["enabled_model_names"])
    assert entry["embedding_model_name"] is None or isinstance(entry["embedding_model_name"], str)
    dim = entry["embedding_dim"]
    assert dim is None or (isinstance(dim, int) and not isinstance(dim, bool))
    assert entry["last_test_at"] is None or isinstance(entry["last_test_at"], str)
    assert entry["last_test_ok"] is None or isinstance(entry["last_test_ok"], bool)
    assert entry["last_test_error"] is None or entry["last_test_error"] in OUTCOME_VALUES
    assert isinstance(entry["created_at"], str)
    assert isinstance(entry["updated_at"], str)


def _same_instant(wire: str | None, expected_text: str) -> bool:
    return wire is not None and datetime.fromisoformat(wire) == datetime.fromisoformat(expected_text)


def _listed(response: httpx.Response) -> dict[str, dict[str, Any]]:
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"servers"}
    assert isinstance(body["servers"], list)
    return {entry["id"]: entry for entry in body["servers"]}


def _list(client: TestClient) -> dict[str, dict[str, Any]]:
    return _listed(client.get(LIST_PATH))


def _server_rows(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        query = select(_servers()).order_by(_servers().c.id)
        return [dict(row) for row in connection.execute(query).mappings()]


def _server_row(engine: Engine, server_id: int) -> dict[str, Any]:
    rows = [row for row in _server_rows(engine) if row["id"] == server_id]
    assert len(rows) == 1
    return rows[0]


def _model_rows(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        query = select(_models()).order_by(_models().c.id)
        return [dict(row) for row in connection.execute(query).mappings()]


def _snapshot(engine: Engine) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return _server_rows(engine), _model_rows(engine)


def _designations(listing: dict[str, dict[str, Any]]) -> dict[str, tuple[Any, Any]]:
    return {
        server_id: (entry["embedding_model_name"], entry["embedding_dim"])
        for server_id, entry in listing.items()
        if entry["embedding_model_name"] is not None or entry["embedding_dim"] is not None
    }


def _create_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"name": NEW_SERVER_NAME, "kind": "openai", "base_url": NEW_SERVER_URL}
    body.update(overrides)
    return body


def _all_routes(server_id: int | str) -> list[tuple[str, str, dict[str, Any] | None]]:
    """D17's nine routes, each well-formed, addressed at ``server_id``; the server delete is last."""
    return [
        ("GET", LIST_PATH, None),
        ("POST", LIST_PATH, _create_body()),
        ("PATCH", _path(server_id), {"name": "renamed"}),
        ("POST", _path(server_id, "/test"), None),
        ("GET", _path(server_id, "/available-models"), None),
        ("POST", _path(server_id, "/models"), {"model_names": ["chat-a"]}),
        ("POST", _path(server_id, "/embedding-model"), {"model_name": "embed-a"}),
        ("DELETE", _path(server_id, "/embedding-model"), None),
        ("DELETE", _path(server_id), None),
    ]


ROUTE_IDS = [
    "list",
    "create",
    "update",
    "test",
    "available-models",
    "set-models",
    "designate",
    "clear-designation",
    "delete",
]
ADMIN_STATUSES = [200, 201, 200, 200, 200, 200, 200, 204, 204]


def _id_routes(server_id: int | str) -> list[tuple[str, str, dict[str, Any] | None]]:
    """The seven id-addressed routes of D17."""
    return [route for route in _all_routes(server_id) if route[1] != LIST_PATH]


ID_ROUTE_IDS = ROUTE_IDS[2:]


# =========================================================================== DoD-1


def test_list_answers_200_with_every_registration__S006_005_DoD1(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-1 — US-012.AC-2: an administrator's list carries every registration."""
    listed = _list(_admin(application, db_settings))
    assert set(listed) == {str(server_id) for server_id in SEEDED_SERVER_IDS}
    for entry in listed.values():
        _assert_server_shape(entry)


def test_list_ids_are_decimal_strings_never_json_numbers__S006_005_DoD1(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-1 — every id crosses the wire as a decimal string, never a JSON number."""
    response = _admin(application, db_settings).get(LIST_PATH)
    assert response.status_code == 200
    for entry in response.json()["servers"]:
        _assert_id_text(entry["id"])
        assert int(entry["id"]) in SEEDED_SERVER_IDS
    assert f'"id":{SERVER_A}' not in response.text.replace(" ", "")


def test_list_entries_carry_the_seeded_values__S006_005_DoD1(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-1 — name, kind, base URL, has-API-key, enabled names, designation + dimension, last test."""
    listed = _list(_admin(application, db_settings))

    a = listed[str(SERVER_A)]
    assert (a["name"], a["kind"], a["base_url"]) == (SERVER_A_NAME, "llamaswap", SERVER_A_URL)
    assert a["has_api_key"] is True
    assert sorted(a["enabled_model_names"]) == ["chat-a", "embed-a"]
    assert a["embedding_model_name"] == "embed-a"
    assert a["embedding_dim"] == 384
    assert _same_instant(a["last_test_at"], TESTED_TEXT)
    assert a["last_test_ok"] is True
    assert a["last_test_error"] is None

    b = listed[str(SERVER_B)]
    assert (b["name"], b["kind"], b["base_url"]) == (SERVER_B_NAME, "openai", SERVER_B_URL)
    assert b["has_api_key"] is False
    assert b["enabled_model_names"] == ["chat-b"]
    assert b["embedding_model_name"] is None
    assert b["embedding_dim"] is None
    assert b["last_test_at"] is None
    assert b["last_test_ok"] is None
    assert b["last_test_error"] is None

    c = listed[str(SERVER_C)]
    assert (c["name"], c["kind"], c["base_url"]) == (SERVER_C_NAME, "openai", SERVER_C_URL)
    assert c["has_api_key"] is True
    assert c["enabled_model_names"] == []
    assert c["embedding_model_name"] is None
    assert _same_instant(c["last_test_at"], TESTED_TEXT)
    assert c["last_test_ok"] is False
    assert c["last_test_error"] == "auth_failed"


def test_disabled_model_is_not_among_the_enabled_names__S006_005_DoD1(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-1 — the enabled names are the enabled ones only; a disabled row is not listed as enabled."""
    listed = _list(_admin(application, db_settings))
    assert "retired-a" not in listed[str(SERVER_A)]["enabled_model_names"]


# =========================================================================== DoD-2


POINTER_TEXTS = (POINTER, NEW_POINTER, KEY_VARIABLE, NEW_KEY_VARIABLE, RESOLVED_KEY, NEW_RESOLVED_KEY)


def _assert_no_key_named(value: Any, forbidden: str) -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            assert key != forbidden, key
            _assert_no_key_named(inner, forbidden)
    elif isinstance(value, list):
        for inner in value:
            _assert_no_key_named(inner, forbidden)


def _assert_no_pointer_text(response: httpx.Response) -> None:
    for text in POINTER_TEXTS:
        assert text not in response.text, text
    if response.content:
        _assert_no_key_named(response.json(), "api_key_ref")


def test_create_response_carries_no_pointer_text__S006_005_DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — creating with a pointer answers the boolean only, never the pointer."""
    response = _admin(application, db_settings).post(LIST_PATH, json=_create_body(api_key_ref=NEW_POINTER))
    assert response.status_code == 201
    assert response.json()["has_api_key"] is True
    _assert_no_pointer_text(response)


def test_update_responses_carry_no_pointer_text__S006_005_DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — update answers carry no pointer, whether it was left, replaced or cleared."""
    admin = _admin(application, db_settings)
    for body in ({"name": "renamed"}, {"api_key_ref": NEW_POINTER}, {"api_key_ref": ""}):
        response = admin.patch(_path(SERVER_A), json=body)
        assert response.status_code == 200
        _assert_no_pointer_text(response)


def test_list_carries_no_pointer_text__S006_005_DoD2(application: FastAPI, db_settings: Settings) -> None:
    """DoD-2 — the list shows has-API-key only."""
    response = _admin(application, db_settings).get(LIST_PATH)
    assert response.status_code == 200
    _assert_no_pointer_text(response)
    assert MISSING_POINTER not in response.text


def test_test_and_designate_responses_carry_no_pointer_text__S006_005_DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — the test and designate answers carry neither the pointer nor the resolved key."""
    admin = _admin(application, db_settings)
    tested = admin.post(_path(SERVER_A, "/test"))
    assert tested.status_code == 200
    _assert_no_pointer_text(tested)
    designated = admin.post(_path(SERVER_A, "/embedding-model"), json={"model_name": "embed-a"})
    assert designated.status_code == 200
    _assert_no_pointer_text(designated)


def test_no_route_on_the_router_carries_pointer_text__S006_005_DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — sweep all nine routes against a pointer-bearing registration."""
    admin = _admin(application, db_settings)
    for method, path, body in _all_routes(SERVER_A):
        response = _send(admin, method, path, body)
        assert response.status_code in (200, 201, 204)
        _assert_no_pointer_text(response)


# =========================================================================== DoD-3


FORBIDDEN_KEY_FRAGMENTS = ("user", "session", "character", "setup", "memo", "count")


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


def test_no_response_carries_a_user_scoped_field_or_count__S006_005_DoD3(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-3 — UC-066 / R5: no field relating to a user, session, character, setup or memo, and no count."""
    admin = _admin(application, db_settings)
    for method, path, body in _all_routes(SERVER_A):
        response = _send(admin, method, path, body)
        assert response.status_code in (200, 201, 204)
        if response.content:
            _assert_no_forbidden_keys(response.json())


EXPECTED_OPERATIONS = {
    ("/api/admin/llm-servers", "get"),
    ("/api/admin/llm-servers", "post"),
    ("/api/admin/llm-servers/{server_id}", "patch"),
    ("/api/admin/llm-servers/{server_id}", "delete"),
    ("/api/admin/llm-servers/{server_id}/test", "post"),
    ("/api/admin/llm-servers/{server_id}/available-models", "get"),
    ("/api/admin/llm-servers/{server_id}/models", "post"),
    ("/api/admin/llm-servers/{server_id}/embedding-model", "post"),
    ("/api/admin/llm-servers/{server_id}/embedding-model", "delete"),
}


def _llm_operations(application: FastAPI) -> dict[tuple[str, str], dict[str, Any]]:
    paths = application.openapi()["paths"]
    found: dict[tuple[str, str], dict[str, Any]] = {}
    for path, operations in paths.items():
        if path == LIST_PATH or path.startswith(LIST_PATH + "/"):
            for method, operation in operations.items():
                found[(path, method.lower())] = operation
    return found


def test_router_declares_only_the_nine_routes__S006_005_DoD3(application: FastAPI) -> None:
    """DoD-3 — no route that could return a session, a user or a count: only D17's nine."""
    assert set(_llm_operations(application)) == EXPECTED_OPERATIONS


def test_no_route_takes_a_query_parameter_or_any_key_but_the_server_id__S006_005_DoD3(
    application: FastAPI,
) -> None:
    """DoD-3 — no query parameter at all; no route keyed on anything but a server id."""
    for (path, _method), operation in _llm_operations(application).items():
        parameters = operation.get("parameters", [])
        assert [p for p in parameters if p.get("in") == "query"] == []
        path_names = {p["name"] for p in parameters if p.get("in") == "path"}
        if "{server_id}" in path:
            assert path_names == {"server_id"}
        else:
            assert path_names == set()


def test_no_route_path_names_a_user_scoped_resource__S006_005_DoD3(application: FastAPI) -> None:
    """DoD-3 — no path segment names a user, session, character, setup, memo or count."""
    for path, _method in _llm_operations(application):
        lowered = path.lower()
        for fragment in FORBIDDEN_KEY_FRAGMENTS:
            assert fragment not in lowered, path


# =========================================================================== DoD-4


@pytest.mark.parametrize("route_index", range(9), ids=ROUTE_IDS)
def test_every_route_refuses_a_roleplayer_with_403__S006_005_DoD4(
    application: FastAPI, db_settings: Settings, route_index: int
) -> None:
    """DoD-4 — a live roleplayer session: 403 ``insufficient_role`` on every route."""
    player = _as(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    method, path, body = _all_routes(SERVER_A)[route_index]
    _assert_envelope(_send(player, method, path, body), 403, INSUFFICIENT_ROLE)


@pytest.mark.parametrize("route_index", range(9), ids=ROUTE_IDS)
def test_every_route_answers_401_without_a_session__S006_005_DoD4(
    application: FastAPI, db_settings: Settings, route_index: int
) -> None:
    """DoD-4 — no session at all: 401 ``not_authenticated``, never 403."""
    anonymous = _with_cookie(application, db_settings, None)
    method, path, body = _all_routes(SERVER_A)[route_index]
    response = _send(anonymous, method, path, body)
    assert response.status_code != 403
    _assert_envelope(response, 401, NOT_AUTHENTICATED)


@pytest.mark.parametrize("route_index", range(9), ids=ROUTE_IDS)
def test_every_route_answers_401_for_an_unissued_cookie__S006_005_DoD4(
    application: FastAPI, db_settings: Settings, route_index: int
) -> None:
    """DoD-4 — a cookie resolving to no session is 'no session': 401, not 403."""
    stranger = _with_cookie(application, db_settings, "this-token-was-never-issued-by-anyone-0000")
    method, path, body = _all_routes(SERVER_A)[route_index]
    _assert_envelope(_send(stranger, method, path, body), 401, NOT_AUTHENTICATED)


def test_refused_requests_change_nothing_and_reach_no_server__S006_005_DoD4(
    application: FastAPI, db_settings: Settings, engine: Engine, fake: _FakeFactory
) -> None:
    """DoD-4 — a refused roleplayer or anonymous caller writes nothing and builds no client."""
    player = _as(application, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    anonymous = _with_cookie(application, db_settings, None)
    before = _snapshot(engine)
    for method, path, body in _all_routes(SERVER_A):
        assert _send(player, method, path, body).status_code == 403
        assert _send(anonymous, method, path, body).status_code == 401
    assert _snapshot(engine) == before
    assert fake.calls == []


def test_administrator_is_admitted_on_every_route__S006_005_DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-4 — control: the same nine requests from an administrator are admitted."""
    admin = _admin(application, db_settings)
    for (method, path, body), status in zip(_all_routes(SERVER_A), ADMIN_STATUSES, strict=True):
        assert _send(admin, method, path, body).status_code == status, (method, path)


# =========================================================================== DoD-5


def test_route_without_its_own_dependency_is_refused_for_a_roleplayer__S006_005_DoD5(
    guarded_probe_app: FastAPI, db_settings: Settings
) -> None:
    """DoD-5 — a route on this router declaring no dependency is still 403 for a roleplayer."""
    player = _as(guarded_probe_app, db_settings, PLAYER_NAME, PLAYER_PASSWORD)
    _assert_envelope(player.get(GUARD_PROBE_FULL_PATH), 403, INSUFFICIENT_ROLE)


def test_route_without_its_own_dependency_is_401_without_a_session__S006_005_DoD5(
    guarded_probe_app: FastAPI, db_settings: Settings
) -> None:
    """DoD-5 — the same probe route answers 401 with no session."""
    anonymous = _with_cookie(guarded_probe_app, db_settings, None)
    _assert_envelope(anonymous.get(GUARD_PROBE_FULL_PATH), 401, NOT_AUTHENTICATED)


def test_route_without_its_own_dependency_is_reachable_for_an_administrator__S006_005_DoD5(
    guarded_probe_app: FastAPI, db_settings: Settings
) -> None:
    """DoD-5 — control: an administrator reaches the probe route."""
    response = _admin(guarded_probe_app, db_settings).get(GUARD_PROBE_FULL_PATH)
    assert response.status_code == 200
    assert response.json() == {"reached": True}


def test_probe_route_does_not_leak_into_other_applications__S006_005_DoD5(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-5 — hygiene: an ordinary factory app exposes no test-only probe route."""
    assert _admin(application, db_settings).get(GUARD_PROBE_FULL_PATH).status_code in (404, 405)


# =========================================================================== DoD-6


@pytest.mark.parametrize("kind", ["llamaswap", "openai"])
def test_create_answers_201_with_the_created_registration__S006_005_DoD6(
    application: FastAPI, db_settings: Settings, engine: Engine, kind: str
) -> None:
    """DoD-6 — US-012.AC-1: 201 with the new registration as submitted, untested, no models."""
    response = _admin(application, db_settings).post(
        LIST_PATH, json=_create_body(kind=kind, api_key_ref=NEW_POINTER)
    )
    assert response.status_code == 201
    body = response.json()
    _assert_server_shape(body)
    assert int(body["id"]) not in SEEDED_SERVER_IDS
    assert body["name"] == NEW_SERVER_NAME
    assert body["kind"] == kind
    assert body["base_url"] == NEW_SERVER_URL
    assert body["has_api_key"] is True
    assert body["enabled_model_names"] == []
    assert body["embedding_model_name"] is None
    assert body["embedding_dim"] is None
    assert body["last_test_at"] is None
    assert body["last_test_ok"] is None
    assert body["last_test_error"] is None
    assert len(_server_rows(engine)) == len(SEEDED_SERVER_IDS) + 1


def test_create_without_a_pointer_has_no_api_key__S006_005_DoD6(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-6 — a registration created with no pointer reports has-API-key false."""
    response = _admin(application, db_settings).post(LIST_PATH, json=_create_body())
    assert response.status_code == 201
    assert response.json()["has_api_key"] is False


def test_created_registration_appears_in_a_subsequent_list__S006_005_DoD6(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-6 — US-012.AC-2: the new registration is listed exactly as the create answered it."""
    admin = _admin(application, db_settings)
    created = admin.post(LIST_PATH, json=_create_body(api_key_ref=NEW_POINTER))
    assert created.status_code == 201
    listed = _list(admin)
    assert set(listed) == {str(server_id) for server_id in SEEDED_SERVER_IDS} | {created.json()["id"]}
    assert listed[created.json()["id"]] == created.json()


# =========================================================================== DoD-7


INVALID_CREATE_BODIES = [
    _create_body(kind="ollama"),
    _create_body(kind=""),
    _create_body(name=""),
    _create_body(base_url=""),
    _create_body(api_key_ref="sk-raw-provider-key"),
    _create_body(api_key_ref="S006_005_API_KEY"),
    _create_body(api_key_ref=" $S006_005_API_KEY"),
]
INVALID_CREATE_IDS = [
    "unknown-kind",
    "empty-kind",
    "empty-name",
    "empty-base-url",
    "raw-key-pointer",
    "bare-name-pointer",
    "leading-space-pointer",
]


@pytest.mark.parametrize("body", INVALID_CREATE_BODIES, ids=INVALID_CREATE_IDS)
def test_invalid_create_answers_422_and_writes_nothing__S006_005_DoD7(
    application: FastAPI, db_settings: Settings, engine: Engine, fake: _FakeFactory, body: dict[str, Any]
) -> None:
    """DoD-7 — D5 / D8: a bad kind, empty name/base URL or non-``$`` pointer is FastAPI's 422, nothing written."""
    admin = _admin(application, db_settings)
    before = _snapshot(engine)
    response = admin.post(LIST_PATH, json=body)
    assert response.status_code == 422
    assert _snapshot(engine) == before
    assert fake.calls == []


@pytest.mark.parametrize("body", INVALID_CREATE_BODIES, ids=INVALID_CREATE_IDS)
def test_invalid_create_refusal_is_not_the_domain_envelope__S006_005_DoD7(
    application: FastAPI, db_settings: Settings, body: dict[str, Any]
) -> None:
    """DoD-7 — the 422 is FastAPI's own, not the domain-error envelope."""
    response = _admin(application, db_settings).post(LIST_PATH, json=body)
    assert response.status_code == 422
    _assert_not_domain_envelope(response)


INVALID_UPDATE_BODIES = [
    {"kind": "ollama"},
    {"name": ""},
    {"base_url": ""},
    {"api_key_ref": "sk-raw-provider-key"},
]
INVALID_UPDATE_IDS = ["unknown-kind", "empty-name", "empty-base-url", "raw-key-pointer"]


@pytest.mark.parametrize("body", INVALID_UPDATE_BODIES, ids=INVALID_UPDATE_IDS)
def test_invalid_update_answers_422_and_changes_nothing__S006_005_DoD7(
    application: FastAPI, db_settings: Settings, engine: Engine, body: dict[str, Any]
) -> None:
    """DoD-7 — the update model carries the same field shapes: 422, not the envelope, nothing changed."""
    admin = _admin(application, db_settings)
    before = _snapshot(engine)
    response = admin.patch(_path(SERVER_A), json=body)
    assert response.status_code == 422
    _assert_not_domain_envelope(response)
    assert _snapshot(engine) == before


# =========================================================================== DoD-8


def test_patch_omitting_the_pointer_keeps_it__S006_005_DoD8(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-8 / D9 — a body without ``api_key_ref`` leaves the stored pointer; has-API-key stays true."""
    response = _admin(application, db_settings).patch(_path(SERVER_A), json={"name": "renamed"})
    assert response.status_code == 200
    assert response.json()["has_api_key"] is True
    assert _server_row(engine, SERVER_A)["api_key_ref"] == POINTER


def test_patch_with_an_empty_pointer_clears_it__S006_005_DoD8(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-8 / D9 — ``api_key_ref: ""`` clears the pointer; has-API-key turns false (response and list)."""
    admin = _admin(application, db_settings)
    response = admin.patch(_path(SERVER_A), json={"api_key_ref": ""})
    assert response.status_code == 200
    assert response.json()["has_api_key"] is False
    assert _list(admin)[str(SERVER_A)]["has_api_key"] is False
    assert _server_row(engine, SERVER_A)["api_key_ref"] is None


def test_patch_with_a_new_pointer_replaces_it__S006_005_DoD8(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-8 / D9 — a new pointer replaces the stored one."""
    response = _admin(application, db_settings).patch(_path(SERVER_A), json={"api_key_ref": NEW_POINTER})
    assert response.status_code == 200
    assert response.json()["has_api_key"] is True
    assert _server_row(engine, SERVER_A)["api_key_ref"] == NEW_POINTER


def test_patch_with_a_pointer_sets_it_on_a_keyless_registration__S006_005_DoD8(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-8 — supplying a pointer where none was stored makes has-API-key true."""
    response = _admin(application, db_settings).patch(_path(SERVER_B), json={"api_key_ref": NEW_POINTER})
    assert response.status_code == 200
    assert response.json()["has_api_key"] is True
    assert _server_row(engine, SERVER_B)["api_key_ref"] == NEW_POINTER


def test_patch_of_only_the_name_changes_only_the_name__S006_005_DoD8(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-8 — a name-only PATCH changes the name and nothing else."""
    admin = _admin(application, db_settings)
    before_entry = _list(admin)[str(SERVER_A)]
    before_row = _server_row(engine, SERVER_A)
    before_models = _model_rows(engine)

    response = admin.patch(_path(SERVER_A), json={"name": "renamed llamaswap"})
    assert response.status_code == 200
    body = response.json()
    _assert_server_shape(body)
    assert body["id"] == str(SERVER_A)
    assert body["name"] == "renamed llamaswap"

    unchanged = EXPECTED_SERVER_FIELDS - {"name", "updated_at"}
    assert {k: body[k] for k in unchanged} == {k: before_entry[k] for k in unchanged}
    after_row = _server_row(engine, SERVER_A)
    assert after_row["name"] == "renamed llamaswap"
    row_unchanged = set(before_row) - {"name", "updated_at"}
    assert {k: after_row[k] for k in row_unchanged} == {k: before_row[k] for k in row_unchanged}
    assert _model_rows(engine) == before_models


# =========================================================================== DoD-9


def test_delete_answers_204_and_the_registration_is_gone__S006_005_DoD9(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-9 — 204 with no body; the registration is absent from the list."""
    admin = _admin(application, db_settings)
    response = admin.delete(_path(SERVER_A))
    assert response.status_code == 204
    assert response.content == b""
    listed = _list(admin)
    assert str(SERVER_A) not in listed
    assert set(listed) == {str(server_id) for server_id in SEEDED_SERVER_IDS - {SERVER_A}}


def test_delete_removes_the_registrations_models_with_it__S006_005_DoD9(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-9 / D10 — its ``models`` rows are gone; another server's rows are untouched."""
    others_before = [row for row in _model_rows(engine) if row["server_id"] != SERVER_A]
    assert _admin(application, db_settings).delete(_path(SERVER_A)).status_code == 204
    after = _model_rows(engine)
    assert [row for row in after if row["server_id"] == SERVER_A] == []
    assert after == others_before
    assert [row["id"] for row in _server_rows(engine)] == sorted(SEEDED_SERVER_IDS - {SERVER_A})


# =========================================================================== DoD-10


def test_test_route_reports_reachable_with_ok__S006_005_DoD10(
    application: FastAPI, db_settings: Settings, fake: _FakeFactory
) -> None:
    """DoD-10 — US-013.AC-1: 200 with outcome ``reachable`` and ok true."""
    fake.answer(ProbeOutcome.REACHABLE, ("model-one",))
    response = _admin(application, db_settings).post(_path(SERVER_B, "/test"))
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "reachable"
    assert body["ok"] is True
    assert isinstance(body["tested_at"], str)
    datetime.fromisoformat(body["tested_at"])


def test_test_route_changes_only_the_three_last_test_fields__S006_005_DoD10(
    application: FastAPI, db_settings: Settings, fake: _FakeFactory, engine: Engine
) -> None:
    """DoD-10 — the registration is unchanged apart from its last-test fields, which record the result."""
    fake.answer(ProbeOutcome.REACHABLE, ("model-one",))
    admin = _admin(application, db_settings)
    before = _list(admin)
    before_models = _model_rows(engine)

    response = admin.post(_path(SERVER_B, "/test"))
    assert response.status_code == 200
    after = _list(admin)

    entry = after[str(SERVER_B)]
    untouched = EXPECTED_SERVER_FIELDS - LAST_TEST_FIELDS
    assert {k: entry[k] for k in untouched} == {k: before[str(SERVER_B)][k] for k in untouched}
    assert entry["last_test_ok"] is True
    assert entry["last_test_error"] is None
    assert entry["last_test_at"] is not None
    assert datetime.fromisoformat(entry["last_test_at"]) == datetime.fromisoformat(response.json()["tested_at"])
    for server_id, other in before.items():
        if server_id != str(SERVER_B):
            assert after[server_id] == other
    assert _model_rows(engine) == before_models


def test_test_route_hands_the_resolved_key_to_the_client__S006_005_DoD10(
    application: FastAPI, db_settings: Settings, fake: _FakeFactory
) -> None:
    """DoD-10 — the probe targets this server's base URL with the pointer resolved at call time."""
    fake.answer(ProbeOutcome.REACHABLE, ("model-one",))
    assert _admin(application, db_settings).post(_path(SERVER_A, "/test")).status_code == 200
    assert len(fake.calls) == 1
    base_url, api_key, _timeout = fake.calls[0]
    assert base_url == SERVER_A_URL
    assert api_key == RESOLVED_KEY


# =========================================================================== DoD-11


FAILING_OUTCOMES = [ProbeOutcome.UNREACHABLE, ProbeOutcome.AUTH_FAILED, ProbeOutcome.MODEL_LIST_EMPTY]


@pytest.mark.parametrize("outcome", FAILING_OUTCOMES, ids=[o.value for o in FAILING_OUTCOMES])
def test_test_route_answers_200_for_a_failing_outcome__S006_005_DoD11(
    application: FastAPI, db_settings: Settings, fake: _FakeFactory, outcome: ProbeOutcome
) -> None:
    """DoD-11 — US-013.AC-2: a failed connection is a 200 reporting the outcome, ok false."""
    fake.answer(outcome)
    response = _admin(application, db_settings).post(_path(SERVER_B, "/test"))
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == outcome.value
    assert body["ok"] is False


@pytest.mark.parametrize("outcome", FAILING_OUTCOMES, ids=[o.value for o in FAILING_OUTCOMES])
def test_registration_survives_a_failed_test_and_can_be_retested__S006_005_DoD11(
    application: FastAPI, db_settings: Settings, fake: _FakeFactory, outcome: ProbeOutcome
) -> None:
    """DoD-11 — UC-011's postcondition: still listed (recording the failure) and re-testable."""
    admin = _admin(application, db_settings)
    fake.answer(outcome)
    assert admin.post(_path(SERVER_B, "/test")).status_code == 200

    listed = _list(admin)
    assert str(SERVER_B) in listed
    assert listed[str(SERVER_B)]["name"] == SERVER_B_NAME
    assert listed[str(SERVER_B)]["last_test_ok"] is False
    assert listed[str(SERVER_B)]["last_test_error"] == outcome.value

    fake.answer(ProbeOutcome.REACHABLE, ("model-one",))
    retest = admin.post(_path(SERVER_B, "/test"))
    assert retest.status_code == 200
    assert retest.json()["outcome"] == "reachable"
    assert retest.json()["ok"] is True
    relisted = _list(admin)[str(SERVER_B)]
    assert relisted["last_test_ok"] is True
    assert relisted["last_test_error"] is None


# =========================================================================== DoD-12


@pytest.mark.parametrize("outcome", list(ProbeOutcome), ids=[o.value for o in ProbeOutcome])
def test_test_result_is_a_typed_value_with_no_free_text__S006_005_DoD12(
    application: FastAPI, db_settings: Settings, fake: _FakeFactory, outcome: ProbeOutcome
) -> None:
    """DoD-12 / D6 — exactly outcome, ok, tested_at; the outcome from the closed four-value set; no prose."""
    fake.answer(outcome, ("model-one",) if outcome is ProbeOutcome.REACHABLE else ())
    response = _admin(application, db_settings).post(_path(SERVER_B, "/test"))
    assert response.status_code == 200
    body = response.json()
    assert set(body) == TEST_RESULT_FIELDS
    assert body["outcome"] in OUTCOME_VALUES
    assert body["outcome"] == outcome.value
    assert isinstance(body["ok"], bool)
    assert body["ok"] is (outcome is ProbeOutcome.REACHABLE)
    datetime.fromisoformat(body["tested_at"])
    assert PROVIDER_PROSE not in response.text


def test_last_test_error_on_the_list_is_a_typed_value__S006_005_DoD12(
    application: FastAPI, db_settings: Settings, fake: _FakeFactory
) -> None:
    """DoD-12 — the recorded failure on the list is the outcome value itself, never provider prose."""
    fake.answer(ProbeOutcome.UNREACHABLE)
    admin = _admin(application, db_settings)
    assert admin.post(_path(SERVER_B, "/test")).status_code == 200
    response = admin.get(LIST_PATH)
    assert _listed(response)[str(SERVER_B)]["last_test_error"] == "unreachable"
    assert PROVIDER_PROSE not in response.text


# =========================================================================== DoD-13


def test_missing_environment_variable_answers_500_secret_ref_missing__S006_005_DoD13(
    application: FastAPI, db_settings: Settings, fake: _FakeFactory
) -> None:
    """DoD-13 / D14 — 500 ``secret_ref_missing`` carrying the variable name; no client built."""
    response = _admin(application, db_settings).post(_path(SERVER_C, "/test"))
    error = _assert_envelope(response, 500, SECRET_REF_MISSING)
    assert MISSING_VARIABLE in json.dumps(error.get("detail"))
    assert fake.calls == []


def test_missing_environment_variable_records_nothing__S006_005_DoD13(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-13 — nothing is recorded on the row (or anywhere); the registration is still listed."""
    admin = _admin(application, db_settings)
    before = _snapshot(engine)
    assert admin.post(_path(SERVER_C, "/test")).status_code == 500
    assert _snapshot(engine) == before
    assert str(SERVER_C) in _list(admin)


# =========================================================================== DoD-14


def test_available_models_answers_200_with_the_names__S006_005_DoD14(
    application: FastAPI, db_settings: Settings, fake: _FakeFactory
) -> None:
    """DoD-14 — UC-012: a reachable server's listing, under one field."""
    fake.answer(ProbeOutcome.REACHABLE, ("model-one", "model-two", "model-three"))
    response = _admin(application, db_settings).get(_path(SERVER_A, "/available-models"))
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"model_names"}
    assert body["model_names"] == ["model-one", "model-two", "model-three"]


def test_available_models_answers_an_empty_list_for_an_empty_listing__S006_005_DoD14(
    application: FastAPI, db_settings: Settings, fake: _FakeFactory
) -> None:
    """DoD-14 — an empty listing is a 200 with an empty list, not an error."""
    fake.answer(ProbeOutcome.MODEL_LIST_EMPTY)
    response = _admin(application, db_settings).get(_path(SERVER_A, "/available-models"))
    assert response.status_code == 200
    assert response.json() == {"model_names": []}


@pytest.mark.parametrize(
    "outcome", [ProbeOutcome.UNREACHABLE, ProbeOutcome.AUTH_FAILED], ids=["unreachable", "auth_failed"]
)
def test_available_models_answers_502_for_a_failed_probe__S006_005_DoD14(
    application: FastAPI, db_settings: Settings, fake: _FakeFactory, outcome: ProbeOutcome
) -> None:
    """DoD-14 / D7 — unreachable or auth-failed: 502 ``llm_unreachable``."""
    fake.answer(outcome)
    response = _admin(application, db_settings).get(_path(SERVER_A, "/available-models"))
    _assert_envelope(response, 502, LLM_UNREACHABLE)


@pytest.mark.parametrize("outcome", list(ProbeOutcome), ids=[o.value for o in ProbeOutcome])
def test_available_models_never_touches_the_last_test_fields__S006_005_DoD14(
    application: FastAPI, db_settings: Settings, fake: _FakeFactory, engine: Engine, outcome: ProbeOutcome
) -> None:
    """DoD-14 / D6 — in every case the row (last-test fields included) is untouched."""
    fake.answer(outcome, ("model-one",) if outcome is ProbeOutcome.REACHABLE else ())
    before = _snapshot(engine)
    response = _admin(application, db_settings).get(_path(SERVER_A, "/available-models"))
    assert response.status_code in (200, 502)
    assert _snapshot(engine) == before


# =========================================================================== DoD-15


def test_set_enabled_models_answers_200_with_the_enabled_names__S006_005_DoD15(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-15 — US-014.AC-1: the full set answers 200 with the enabled names as stored, also on the list."""
    admin = _admin(application, db_settings)
    response = admin.post(_path(SERVER_B, "/models"), json={"model_names": ["chat-b", "new-b"]})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"enabled_model_names"}
    assert sorted(body["enabled_model_names"]) == ["chat-b", "new-b"]
    assert sorted(_list(admin)[str(SERVER_B)]["enabled_model_names"]) == ["chat-b", "new-b"]


def test_omitted_model_is_reported_gone_while_rows_survive__S006_005_DoD15(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-15 — US-014.AC-2: a set omitting a previously enabled model disables it; registration and rows remain."""
    admin = _admin(application, db_settings)
    assert admin.post(_path(SERVER_B, "/models"), json={"model_names": ["chat-b", "new-b"]}).status_code == 200

    response = admin.post(_path(SERVER_B, "/models"), json={"model_names": ["new-b"]})
    assert response.status_code == 200
    assert response.json()["enabled_model_names"] == ["new-b"]

    listed = _list(admin)
    assert str(SERVER_B) in listed
    assert listed[str(SERVER_B)]["enabled_model_names"] == ["new-b"]

    b_rows = {row["model_name"]: row for row in _model_rows(engine) if row["server_id"] == SERVER_B}
    assert set(b_rows) == {"chat-b", "new-b"}
    assert not b_rows["chat-b"]["is_enabled"]
    assert b_rows["new-b"]["is_enabled"]


def test_set_enabled_models_on_one_server_leaves_others_alone__S006_005_DoD15(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-15 — the set is per server: another server's enabled names are unchanged."""
    admin = _admin(application, db_settings)
    before = _list(admin)[str(SERVER_A)]["enabled_model_names"]
    assert admin.post(_path(SERVER_B, "/models"), json={"model_names": []}).status_code == 200
    assert _list(admin)[str(SERVER_A)]["enabled_model_names"] == before


# =========================================================================== DoD-16


@pytest.mark.parametrize(
    "names", [[], ["chat-a"], ["retired-a"]], ids=["disable-all", "drop-designated", "swap"]
)
def test_disable_is_never_refused__S006_005_DoD16(
    application: FastAPI, db_settings: Settings, names: list[str]
) -> None:
    """DoD-16 — US-016.AC-1: disabling (even the designated embedding model) is a plain 200."""
    response = _admin(application, db_settings).post(_path(SERVER_A, "/models"), json={"model_names": names})
    assert response.status_code == 200
    assert response.json() == {"enabled_model_names": names}


def test_disable_response_offers_no_dependency_report__S006_005_DoD16(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-16 / R5 — the answer has one field, the enabled names; nothing that could say 'N sessions use this'."""
    response = _admin(application, db_settings).post(_path(SERVER_A, "/models"), json={"model_names": []})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"enabled_model_names"}
    _assert_no_forbidden_keys(body)
    assert "error" not in body


def test_set_models_route_declares_no_query_parameter__S006_005_DoD16(application: FastAPI) -> None:
    """DoD-16 — no mechanism (such as a force/confirm flag) exists by which a disable could be gated."""
    operation = _llm_operations(application)[("/api/admin/llm-servers/{server_id}/models", "post")]
    assert [p for p in operation.get("parameters", []) if p.get("in") != "path"] == []


# =========================================================================== DoD-17


def test_designation_answers_200_with_the_measured_dimension__S006_005_DoD17(
    application: FastAPI, db_settings: Settings, fake: _FakeFactory
) -> None:
    """DoD-17 — US-015.AC-1: 200 with the server carrying the designation and its measured dimension."""
    fake.embed_dim = 768
    admin = _admin(application, db_settings)
    response = admin.post(_path(SERVER_B, "/embedding-model"), json={"model_name": "embed-b"})
    assert response.status_code == 200
    body = response.json()
    _assert_server_shape(body)
    assert body["id"] == str(SERVER_B)
    assert body["embedding_model_name"] == "embed-b"
    assert body["embedding_dim"] == 768
    assert [model for model, _texts in fake.embed_calls] == ["embed-b"]

    listed = _list(admin)
    assert listed[str(SERVER_B)]["embedding_model_name"] == "embed-b"
    assert listed[str(SERVER_B)]["embedding_dim"] == 768


def test_designating_on_a_second_server_moves_it__S006_005_DoD17(
    application: FastAPI, db_settings: Settings, fake: _FakeFactory
) -> None:
    """DoD-17 — UC-013: exactly one designation across every server after each designation."""
    admin = _admin(application, db_settings)
    assert _designations(_list(admin)) == {str(SERVER_A): ("embed-a", 384)}

    fake.embed_dim = 768
    assert admin.post(_path(SERVER_B, "/embedding-model"), json={"model_name": "embed-b"}).status_code == 200
    assert _designations(_list(admin)) == {str(SERVER_B): ("embed-b", 768)}

    fake.embed_dim = 1536
    assert admin.post(_path(SERVER_A, "/embedding-model"), json={"model_name": "embed-a2"}).status_code == 200
    assert _designations(_list(admin)) == {str(SERVER_A): ("embed-a2", 1536)}


# =========================================================================== DoD-18


EMBED_FAILURES = [
    LlmUnreachableError("embeddings call failed", {"reason": "unreachable"}),
    LlmUnreachableError("embeddings call failed", {"reason": "auth_failed"}),
    LlmUnreachableError("embeddings call failed", {"reason": "no_usable_vector"}),
]


@pytest.mark.parametrize("error", EMBED_FAILURES, ids=["unreachable", "auth_failed", "no_usable_vector"])
def test_failed_designation_answers_502_and_keeps_the_previous_one__S006_005_DoD18(
    application: FastAPI, db_settings: Settings, fake: _FakeFactory, engine: Engine, error: Exception
) -> None:
    """DoD-18 / D2 — a failing embeddings call: 502 ``llm_unreachable``, previous designation exactly as it was."""
    fake.embed_error = error
    admin = _admin(application, db_settings)
    before_listing = _list(admin)
    before = _snapshot(engine)

    response = admin.post(_path(SERVER_B, "/embedding-model"), json={"model_name": "embed-b"})
    _assert_envelope(response, 502, LLM_UNREACHABLE)

    assert _snapshot(engine) == before
    after_listing = _list(admin)
    assert after_listing == before_listing
    assert _designations(after_listing) == {str(SERVER_A): ("embed-a", 384)}


# =========================================================================== DoD-19


def test_clear_designation_answers_204_and_none_remains__S006_005_DoD19(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-19 — 204 with no body; the list then shows no designation anywhere."""
    admin = _admin(application, db_settings)
    response = admin.delete(_path(SERVER_A, "/embedding-model"))
    assert response.status_code == 204
    assert response.content == b""
    listed = _list(admin)
    assert _designations(listed) == {}
    for entry in listed.values():
        assert entry["embedding_model_name"] is None
        assert entry["embedding_dim"] is None


def test_clear_designation_keeps_the_enabled_names__S006_005_DoD19(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-19 — clearing touches only the designation; the registration and its enabled names stand."""
    admin = _admin(application, db_settings)
    before = _list(admin)[str(SERVER_A)]["enabled_model_names"]
    assert admin.delete(_path(SERVER_A, "/embedding-model")).status_code == 204
    assert _list(admin)[str(SERVER_A)]["enabled_model_names"] == before


# =========================================================================== DoD-20


@pytest.mark.parametrize("route_index", range(7), ids=ID_ROUTE_IDS)
def test_unknown_id_answers_404_llm_server_not_found__S006_005_DoD20(
    application: FastAPI, db_settings: Settings, engine: Engine, fake: _FakeFactory, route_index: int
) -> None:
    """DoD-20 / D7 — every id-addressed route: 404 ``llm_server_not_found``, nothing written, no client."""
    admin = _admin(application, db_settings)
    before = _snapshot(engine)
    method, path, body = _id_routes(UNKNOWN_ID)[route_index]
    _assert_envelope(_send(admin, method, path, body), 404, LLM_SERVER_NOT_FOUND)
    assert _snapshot(engine) == before
    assert fake.calls == []


# =========================================================================== DoD-21


def test_list_carries_the_large_id_as_its_exact_string__S006_005_DoD21(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-21 — an id beyond MAX_SAFE_INTEGER is listed as its exact decimal string."""
    listed = _list(_admin(application, db_settings))
    assert listed[BIG_ID_TEXT]["name"] == BIG_NAME
    assert listed[str(NEIGHBOR_ID)]["name"] == NEIGHBOR_NAME


def test_large_path_id_update_round_trips_exactly__S006_005_DoD21(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-21 — PATCH on the large id addresses it (not its neighbour) and answers the same string."""
    response = _admin(application, db_settings).patch(_path(BIG_ID_TEXT), json={"name": "renamed far"})
    assert response.status_code == 200
    assert response.json()["id"] == BIG_ID_TEXT
    assert response.json()["name"] == "renamed far"
    assert _server_row(engine, BIG_ID)["name"] == "renamed far"
    assert _server_row(engine, NEIGHBOR_ID)["name"] == NEIGHBOR_NAME


def test_large_path_id_reaches_that_registration_on_the_outbound_routes__S006_005_DoD21(
    application: FastAPI, db_settings: Settings, fake: _FakeFactory, engine: Engine
) -> None:
    """DoD-21 — test, available-models and designate on the large id probe its base URL and answer its id."""
    admin = _admin(application, db_settings)
    fake.answer(ProbeOutcome.REACHABLE, ("model-one",))

    assert admin.post(_path(BIG_ID_TEXT, "/test")).status_code == 200
    assert _server_row(engine, BIG_ID)["last_test_ok"]
    assert _server_row(engine, NEIGHBOR_ID)["last_test_ok"] is None

    assert admin.get(_path(BIG_ID_TEXT, "/available-models")).status_code == 200

    designated = admin.post(_path(BIG_ID_TEXT, "/embedding-model"), json={"model_name": "far-embed"})
    assert designated.status_code == 200
    assert designated.json()["id"] == BIG_ID_TEXT

    assert [call[0] for call in fake.calls] == [BIG_URL, BIG_URL, BIG_URL]


def test_large_path_id_models_and_delete_touch_only_that_registration__S006_005_DoD21(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-21 — the enabled set lands on the large id; deleting it leaves its neighbour."""
    admin = _admin(application, db_settings)
    response = admin.post(_path(BIG_ID_TEXT, "/models"), json={"model_names": ["far-chat"]})
    assert response.status_code == 200
    assert response.json() == {"enabled_model_names": ["far-chat"]}
    assert {row["server_id"] for row in _model_rows(engine) if row["model_name"] == "far-chat"} == {BIG_ID}
    listed = _list(admin)
    assert listed[BIG_ID_TEXT]["enabled_model_names"] == ["far-chat"]
    assert listed[str(NEIGHBOR_ID)]["enabled_model_names"] == []

    assert admin.delete(_path(BIG_ID_TEXT)).status_code == 204
    listed = _list(admin)
    assert BIG_ID_TEXT not in listed
    assert str(NEIGHBOR_ID) in listed


def test_large_created_id_comes_back_as_the_same_string__S006_005_DoD21(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-21 — a minted id beyond MAX_SAFE_INTEGER is answered exactly and addresses that registration."""
    admin = _admin(application, db_settings)
    application.state.id_generator = _FixedIdGenerator(BIG_MINTED_ID)
    created = admin.post(LIST_PATH, json=_create_body())
    assert created.status_code == 201
    assert created.json()["id"] == str(BIG_MINTED_ID)
    renamed = admin.patch(_path(str(BIG_MINTED_ID)), json={"name": "minted far"})
    assert renamed.status_code == 200
    assert renamed.json()["id"] == str(BIG_MINTED_ID)
    assert _server_row(engine, BIG_MINTED_ID)["name"] == "minted far"


# =========================================================================== DoD-22


def test_database_contact_goes_only_through_the_connection_dependency__S006_005_DoD22(
    application: FastAPI, db_settings: Settings, engine: Engine, tmp_path: Path
) -> None:
    """DoD-22 — redirect ``get_connection``: listing and writing happen on that database only."""
    alternate_settings = db_settings.model_copy(
        update={"data_dir": tmp_path / "alternate", "db_filename": "alternate.sqlite"}
    )
    alternate_engine = get_engine(alternate_settings)
    with alternate_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(
        alternate_engine,
        user_id=8_100_001,
        username="alternate-admin",
        password="alternate admin password",
        role=Role.ADMIN,
    )
    alternate_server = 7_200_001
    _insert_server(
        alternate_engine,
        server_id=alternate_server,
        name="alternate server",
        kind="openai",
        base_url="http://alternate.test",
    )

    def alternate_connection() -> Iterator[Connection]:
        connection = alternate_engine.connect()
        try:
            yield connection
        finally:
            connection.close()

    application.dependency_overrides[get_connection] = alternate_connection
    main_before = _snapshot(engine)

    admin = _as(application, db_settings, "alternate-admin", "alternate admin password")
    assert set(_list(admin)) == {str(alternate_server)}

    created = admin.post(LIST_PATH, json=_create_body())
    assert created.status_code == 201
    assert int(created.json()["id"]) in {row["id"] for row in _server_rows(alternate_engine)}

    assert admin.patch(_path(alternate_server), json={"name": "renamed alternate"}).status_code == 200
    assert _server_row(alternate_engine, alternate_server)["name"] == "renamed alternate"

    # A registration of the settings database is unknown through the dependency.
    _assert_envelope(admin.patch(_path(SERVER_A), json={"name": "x"}), 404, LLM_SERVER_NOT_FOUND)
    assert _snapshot(engine) == main_before


def test_created_id_comes_from_the_generator_on_application_state__S006_005_DoD22(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-22 — the generator create uses is the one on ``app.state``, not a module global."""
    generator = _FixedIdGenerator(FIXED_MINTED_ID)
    admin = _admin(application, db_settings)
    application.state.id_generator = generator
    response = admin.post(LIST_PATH, json=_create_body(api_key_ref=NEW_POINTER))
    assert response.status_code == 201
    assert response.json()["id"] == str(FIXED_MINTED_ID)
    assert generator.calls >= 1

    row = _server_row(engine, FIXED_MINTED_ID)
    assert row["name"] == NEW_SERVER_NAME
    assert row["kind"] == "openai"
    assert row["base_url"] == NEW_SERVER_URL
    assert row["api_key_ref"] == NEW_POINTER
    datetime.fromisoformat(row["created_at"])
    datetime.fromisoformat(row["updated_at"])


def test_new_model_rows_come_from_the_generator_on_application_state__S006_005_DoD22(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-22 — enabling new names mints their row ids from the ``app.state`` generator."""
    generator = _SequenceIdGenerator(916_000_000_000_001)
    admin = _admin(application, db_settings)
    application.state.id_generator = generator
    response = admin.post(_path(SERVER_B, "/models"), json={"model_names": ["chat-b", "gen-one", "gen-two"]})
    assert response.status_code == 200
    new_ids = {row["id"] for row in _model_rows(engine) if row["model_name"] in {"gen-one", "gen-two"}}
    assert len(new_ids) == 2
    assert new_ids <= set(generator.minted)


def test_settings_reach_the_outbound_routes_from_the_settings_dependency__S006_005_DoD22(
    application: FastAPI, db_settings: Settings, fake: _FakeFactory
) -> None:
    """DoD-22 — test, available-models and designate hand the dependency's timeout to the client."""
    custom = db_settings.model_copy(update={"llm_request_timeout_seconds": 7.25})
    application.dependency_overrides[get_settings] = lambda: custom
    admin = _admin(application, db_settings)
    fake.answer(ProbeOutcome.REACHABLE, ("model-one",))

    assert admin.post(_path(SERVER_A, "/test")).status_code == 200
    assert admin.get(_path(SERVER_A, "/available-models")).status_code == 200
    assert admin.post(_path(SERVER_A, "/embedding-model"), json={"model_name": "embed-a"}).status_code == 200

    assert fake.calls == [
        (SERVER_A_URL, RESOLVED_KEY, 7.25),
        (SERVER_A_URL, RESOLVED_KEY, 7.25),
        (SERVER_A_URL, RESOLVED_KEY, 7.25),
    ]


def test_default_settings_timeout_reaches_the_client__S006_005_DoD22(
    application: FastAPI, db_settings: Settings, fake: _FakeFactory
) -> None:
    """DoD-22 — with the unmodified settings the client gets the default 30-second timeout."""
    fake.answer(ProbeOutcome.REACHABLE, ("model-one",))
    assert _admin(application, db_settings).post(_path(SERVER_B, "/test")).status_code == 200
    assert fake.calls == [(SERVER_B_URL, None, 30.0)]
