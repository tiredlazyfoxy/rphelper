"""Tests for the memos router: ``/api/memos...`` and ``/api/sessions/{session_id}/memo-chain``.

Every expected value comes from ``docs/plans/015.memos/004.memos-router.md`` (Interface
intent + Definition of done), ``004.context.md`` and the feature ``context.md`` (the **Wire
contract** — the five routes, the nine-key ``Memo`` object, the request rules, the failure
codes — plus D2, D4, D6, D8, D9, D12, D15, R2, R3, R5). Bindings come from ``## Skeleton``
in ``status.md`` (steps 001..004): the five full literal paths and their status codes.

Covers step 004 DoD-1 .. DoD-15. DoD-16 is ``[manual/live]`` and carries no test.

Feature 016 step 001 (``docs/plans/016.note-wall/001.reorder-backend.md``) adds
``PUT /api/memos/order`` (D6) and amends the allocation (D5, newest first); its tests are
suffixed ``__S016_001_DoD<n>`` (DoD-10 .. DoD-14 here), and amended 015 tests carry that
suffix appended to their 015 name.

The application is the real factory's (``create_app()``), pinned to the per-test database
through ``dependency_overrides[get_settings]``. Each signed-in caller has its own
``TestClient`` carrying exactly one session cookie. Characters, setups and sessions are
created and archived through their own routes; disabled / forced states are reached through
``PATCH /api/memos/{id}``. ``conftest.py`` is untouched: every fixture below is file-local.

Feature 024 step 004 (``docs/plans/024.embedding-lifecycle/004.memo-write-paths.md``, DoD-10,
``context.md`` "Regression fallout") makes ``POST /api/memos`` and a body-changing
``PATCH /api/memos/{id}`` require a designated embedding model (D5, strict per D8). That is a
**precondition**, not a changed expectation: ``_seed`` now also seeds the designation (one
``llm_servers`` row and one enabled, designated ``models`` row at dimension 8), and the
``application`` fixture adds a ``dependency_overrides`` entry for the shared
``app.dependencies.get_llm_client_factory`` (D9) returning the fake from ``tests/llm_fakes.py``
alongside the existing ``get_settings`` override. **No assertion in this file was changed or
loosened**, and no route, status code or wire key moved.
"""

import ast
import inspect
import re
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select

from app.config import Settings, get_settings
from app.db import schema
from app.dependencies import get_llm_client_factory
from app.main import create_app
from app.roles import Role
from app.routers import memos as memos_router_module
from app.services.passwords import hash_password
from tests.llm_fakes import FAKE_EMBEDDING_DIM, FakeClientFactory, fake_factory

CHARACTERS_PATH = "/api/characters"
SETUPS_PATH = "/api/setups"
SESSIONS_PATH = "/api/sessions"
MEMOS_PATH = "/api/memos"
LOGIN_PATH = "/api/auth/login"

TIMESTAMP = "2026-01-01T00:00:00+00:00"

#: The fixed-width timestamp form named by the Wire contract.
TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00$")

PLAYER_A_ID = 9_500_001
PLAYER_A_NAME = "aster"
PLAYER_A_PASSWORD = "a quiet river at dusk"

PLAYER_B_ID = 9_500_002
PLAYER_B_NAME = "briar"
PLAYER_B_PASSWORD = "salt and lantern light"

#: 024 step 004: the designation every create / body edit now needs (``context.md`` D5, D9).
EMBEDDING_SERVER_ID = 1_400_000_000_000_000_311
EMBEDDING_MODEL_ID = 1_400_000_000_000_000_312
EMBEDDING_BASE_URL = "http://embedding.test:8080/v1"
EMBEDDING_MODEL_NAME = "the-designated-embedding-model"

#: Large decimal id strings no row holds (004.context.md "Test seeding").
UNKNOWN_CHARACTER_ID = "7250000000000000101"
UNKNOWN_SETUP_ID = "7250000000000000102"
UNKNOWN_SESSION_ID = "7250000000000000103"
UNKNOWN_MEMO_ID = "7250000000000000104"

#: The ``Memo`` wire object's keys — exactly nine, never ``user_id`` (Wire contract).
MEMO_KEYS = {
    "id",
    "scope",
    "scope_id",
    "body",
    "is_enabled",
    "is_forced",
    "sort_key",
    "created_at",
    "updated_at",
}

#: A chain level's wire keys (Wire contract: ``{ scope, scope_id, memos }``).
LEVEL_KEYS = {"scope", "scope_id", "memos"}

NOT_AUTHENTICATED = "not_authenticated"
CHARACTER_NOT_FOUND = "character_not_found"
SETUP_NOT_FOUND = "setup_not_found"
SESSION_NOT_FOUND = "session_not_found"
MEMO_NOT_FOUND = "memo_not_found"


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


def _seed_embedding_designation(engine: Engine) -> None:
    """One server and one enabled, designated embedding model at dimension 8.

    024 step 004's precondition for ``POST /api/memos`` and a body-changing ``PATCH``
    (``context.md`` D5 / D9). Raw inserts, no service, and a null ``api_key_ref`` so no secret
    has to resolve. It touches no table any assertion in this file reads.
    """
    servers = schema.metadata.tables["llm_servers"]
    models = schema.metadata.tables["models"]
    with engine.begin() as connection:
        connection.execute(
            servers.insert().values(
                id=EMBEDDING_SERVER_ID,
                name="the embedding server",
                kind="llamaswap",
                base_url=EMBEDDING_BASE_URL,
                api_key_ref=None,
                last_test_at=None,
                last_test_ok=None,
                last_test_error=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )
        connection.execute(
            models.insert().values(
                id=EMBEDDING_MODEL_ID,
                server_id=EMBEDDING_SERVER_ID,
                model_name=EMBEDDING_MODEL_NAME,
                is_enabled=True,
                is_embedding_designated=True,
                embedding_dim=FAKE_EMBEDDING_DIM,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _seed(engine: Engine) -> None:
    with engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(
        engine, user_id=PLAYER_A_ID, username=PLAYER_A_NAME, password=PLAYER_A_PASSWORD, role=Role.ROLEPLAYER
    )
    _insert_user(
        engine, user_id=PLAYER_B_ID, username=PLAYER_B_NAME, password=PLAYER_B_PASSWORD, role=Role.ROLEPLAYER
    )
    _seed_embedding_designation(engine)


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database with the registry applied, the two roleplayers and the designation."""
    _seed(db_engine)
    return db_engine


@pytest.fixture
def embedding_factory() -> FakeClientFactory:
    """024 step 004: the provider the overridden shared dependency hands every memo route."""
    return fake_factory(FAKE_EMBEDDING_DIM)


@pytest.fixture
def application(
    db_settings: Settings, engine: Engine, embedding_factory: FakeClientFactory
) -> Iterator[FastAPI]:
    """The factory's application, pinned to the seeded per-test database.

    024 step 004 adds the second override: the shared ``get_llm_client_factory`` (D9), so no
    route ever builds a real client.
    """
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: db_settings
    app.dependency_overrides[get_llm_client_factory] = lambda: embedding_factory
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


# --- login helpers -------------------------------------------------------------------


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


def _as(application: FastAPI, settings: Settings, username: str, password: str) -> TestClient:
    """A fresh client carrying exactly this account's session cookie — never shared."""
    fresh = TestClient(application)
    fresh.cookies.set(settings.session_cookie_name, _login_token(application, settings, username, password))
    return fresh


def _anonymous(application: FastAPI) -> TestClient:
    return TestClient(application)


def _player_a(application: FastAPI, settings: Settings) -> TestClient:
    return _as(application, settings, PLAYER_A_NAME, PLAYER_A_PASSWORD)


def _player_b(application: FastAPI, settings: Settings) -> TestClient:
    return _as(application, settings, PLAYER_B_NAME, PLAYER_B_PASSWORD)


# --- exact paths ---------------------------------------------------------------------


def _memo_path(memo_id: Any) -> str:
    return f"{MEMOS_PATH}/{memo_id}"


def _chain_path(session_id: Any) -> str:
    return f"{SESSIONS_PATH}/{session_id}/memo-chain"


# --- parent seeding through the real routes ------------------------------------------


def _json_object(response: httpx.Response, status: int) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def _character(client: TestClient, name: str = "Ilse") -> str:
    """009's create route; returns the character id string."""
    created = _json_object(client.post(CHARACTERS_PATH, json={"name": name, "sheet": ""}), 201)
    character_id = created["id"]
    assert isinstance(character_id, str)
    return character_id


def _setup(client: TestClient, character_id: str, name: str = "Harbour") -> str:
    """010's create route; returns the setup id string."""
    created = _json_object(
        client.post(f"{CHARACTERS_PATH}/{character_id}/setups", json={"name": name, "description": ""}), 201
    )
    setup_id = created["id"]
    assert isinstance(setup_id, str)
    return setup_id


def _session(client: TestClient, character_id: str, setup_id: str | None) -> str:
    """011's start route with ``{"setup_id": ...}``; returns the session id string."""
    created = _json_object(
        client.post(f"{CHARACTERS_PATH}/{character_id}/sessions", json={"setup_id": setup_id}), 201
    )
    session_id = created["id"]
    assert isinstance(session_id, str)
    return session_id


def _tree(client: TestClient) -> tuple[str, str, str]:
    """Character C, setup S under C, session X under C with S."""
    character_id = _character(client)
    setup_id = _setup(client, character_id)
    session_id = _session(client, character_id, setup_id)
    return character_id, setup_id, session_id


# --- memo request helpers ------------------------------------------------------------


def _create_request(client: TestClient, scope: str, scope_id: str | None, body: str) -> httpx.Response:
    payload: dict[str, Any] = {"scope": scope, "body": body}
    if scope_id is not None:
        payload["scope_id"] = scope_id
    return client.post(MEMOS_PATH, json=payload)


def _create(client: TestClient, scope: str, scope_id: str | None, body: str) -> dict[str, Any]:
    return _json_object(_create_request(client, scope, scope_id, body), 201)


def _list_request(client: TestClient, scope: str, scope_id: str | None) -> httpx.Response:
    params = {"scope": scope}
    if scope_id is not None:
        params["scope_id"] = scope_id
    return client.get(MEMOS_PATH, params=params)


def _list(client: TestClient, scope: str, scope_id: str | None) -> list[dict[str, Any]]:
    body = _json_object(_list_request(client, scope, scope_id), 200)
    assert set(body) == {"memos"}
    memos = body["memos"]
    assert isinstance(memos, list)
    return memos


def _patch(client: TestClient, memo_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _json_object(client.patch(_memo_path(memo_id), json=payload), 200)


def _chain(client: TestClient, session_id: str) -> list[dict[str, Any]]:
    body = _json_object(client.get(_chain_path(session_id)), 200)
    assert set(body) == {"levels"}
    levels = body["levels"]
    assert isinstance(levels, list)
    for level in levels:
        assert set(level) == LEVEL_KEYS
    return levels


def _ids(rows: list[dict[str, Any]]) -> list[str]:
    return [row["id"] for row in rows]


def _assert_envelope(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error, dict)
    assert error["code"] == code
    return body


def _assert_memo_shape(memo: dict[str, Any]) -> None:
    """The nine-key ``Memo`` wire object (Wire contract)."""
    assert set(memo) == MEMO_KEYS
    assert "user_id" not in memo
    assert isinstance(memo["id"], str) and memo["id"].isdigit()
    assert memo["scope"] in {"user", "character", "setup", "session"}
    if memo["scope"] == "user":
        assert memo["scope_id"] is None
    else:
        assert isinstance(memo["scope_id"], str) and memo["scope_id"].isdigit()
    assert isinstance(memo["body"], str)
    assert isinstance(memo["is_enabled"], bool)
    assert isinstance(memo["is_forced"], bool)
    assert isinstance(memo["sort_key"], int) and not isinstance(memo["sort_key"], bool)
    assert TIMESTAMP_PATTERN.match(memo["created_at"]) is not None
    assert TIMESTAMP_PATTERN.match(memo["updated_at"]) is not None


def _memo_count(engine: Engine) -> int:
    with engine.connect() as connection:
        count = connection.execute(select(func.count()).select_from(schema.memos)).scalar_one()
    assert isinstance(count, int)
    return count


# --- DoD-1: router-level auth ---------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", f"{MEMOS_PATH}?scope=user", None),
        ("POST", MEMOS_PATH, {"scope": "user", "body": "note"}),
        ("PATCH", _memo_path(UNKNOWN_MEMO_ID), {"body": "note"}),
        ("DELETE", _memo_path(UNKNOWN_MEMO_ID), None),
        ("GET", _chain_path(UNKNOWN_SESSION_ID), None),
    ],
    ids=["list", "create", "update", "delete", "chain"],
)
def test_every_route_answers_401_without_a_login_cookie__S015_004_DoD1(
    application: FastAPI, engine: Engine, method: str, path: str, payload: dict[str, Any] | None
) -> None:
    """DoD-1 — D9: ``require_user`` on the router refuses all five routes anonymously."""
    client = _anonymous(application)
    if payload is None:
        response = client.request(method, path)
    else:
        response = client.request(method, path, json=payload)
    _assert_envelope(response, 401, NOT_AUTHENTICATED)
    assert _memo_count(engine) == 0


# --- DoD-2: create at each level, wire shape, listed ----------------------------------


def test_a_note_is_created_and_listed_at_each_of_the_four_levels__S015_004_DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — US-049..053.AC-1: 201 with the nine wire keys, then the level lists it."""
    client = _player_a(application, db_settings)
    character_id, setup_id, session_id = _tree(client)

    targets: list[tuple[str, str | None]] = [
        ("user", None),
        ("character", character_id),
        ("setup", setup_id),
        ("session", session_id),
    ]
    for scope, scope_id in targets:
        body = f"a {scope} note"
        created = _create(client, scope, scope_id, body)

        _assert_memo_shape(created)
        assert created["scope"] == scope
        assert created["scope_id"] == scope_id
        assert created["body"] == body
        assert created["is_enabled"] is True
        assert created["is_forced"] is False
        assert created["sort_key"] == 0
        assert created["created_at"] == created["updated_at"]

        listed = _list(client, scope, scope_id)
        assert listed == [created]


# --- DoD-3: flags, sort_key, user_id and title in the request are ignored -------------


def test_a_create_ignores_flags_sort_key_user_id_and_title__S015_004_DoD3(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-3 — US-053.AC-1, US-119.AC-1, R5: the new note is enabled, not forced, allocated, the caller's."""
    client_a = _player_a(application, db_settings)
    client_b = _player_b(application, db_settings)

    response = client_a.post(
        MEMOS_PATH,
        json={
            "scope": "user",
            "body": "mine",
            "is_enabled": False,
            "is_forced": True,
            "sort_key": 9,
            "user_id": str(PLAYER_B_ID),
            "title": "t",
        },
    )
    created = _json_object(response, 201)

    _assert_memo_shape(created)
    assert "title" not in created
    assert created["is_enabled"] is True
    assert created["is_forced"] is False
    assert created["sort_key"] == 0
    assert created["body"] == "mine"

    assert _ids(_list(client_a, "user", None)) == [created["id"]]
    assert _list(client_b, "user", None) == []


def test_a_character_level_create_ignores_flags_and_sort_key__S015_004_DoD3(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-3 — the same ignored keys at a non-user level: defaults and allocation stand."""
    client = _player_a(application, db_settings)
    character_id = _character(client)

    response = client.post(
        MEMOS_PATH,
        json={
            "scope": "character",
            "scope_id": character_id,
            "body": "about her",
            "is_enabled": False,
            "is_forced": True,
            "sort_key": 9,
            "title": "t",
        },
    )
    created = _json_object(response, 201)
    assert "title" not in created
    assert created["is_enabled"] is True
    assert created["is_forced"] is False
    assert created["sort_key"] == 0


# --- DoD-4: verbatim body; user-level scope_id ignored --------------------------------


def test_the_body_is_answered_and_listed_verbatim__S015_004_DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-4 — D15: markdown whitespace is content; nothing is trimmed."""
    client = _player_a(application, db_settings)
    character_id = _character(client)
    body = "  # Heading\n\ntext  "

    created = _create(client, "character", character_id, body)
    assert created["body"] == body

    listed = _list(client, "character", character_id)
    assert [memo["body"] for memo in listed] == [body]


def test_a_user_create_with_another_scope_id_lands_at_the_callers_user_level__S015_004_DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-4 — request rules: for ``scope="user"`` a supplied ``scope_id`` is ignored."""
    client_a = _player_a(application, db_settings)
    client_b = _player_b(application, db_settings)

    created = _create(client_a, "user", str(PLAYER_B_ID), "for me")
    assert created["scope"] == "user"
    assert created["scope_id"] is None

    assert _ids(_list(client_a, "user", None)) == [created["id"]]
    assert _list(client_b, "user", None) == []


def test_a_user_create_with_a_character_id_as_scope_id_lands_at_the_user_level__S015_004_DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-4 — the ignored ``scope_id`` may be any id; the note is the caller's user note."""
    client = _player_a(application, db_settings)
    character_id = _character(client)

    created = _create(client, "user", character_id, "still mine")
    assert created["scope_id"] is None
    assert _ids(_list(client, "user", None)) == [created["id"]]
    assert _list(client, "character", character_id) == []


# --- DoD-5: 422s, nothing inserted ----------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"scope": "user", "body": ""},
        {"scope": "user", "body": "  \n"},
        {"scope": "user"},
        {"scope": "character", "body": "x"},
        {"scope": "setup", "body": "x"},
        {"scope": "session", "body": "x"},
        {"scope": "world", "body": "x"},
        {"scope": "character", "scope_id": "abc", "body": "x"},
    ],
    ids=[
        "empty-body",
        "whitespace-body",
        "missing-body",
        "character-no-scope-id",
        "setup-no-scope-id",
        "session-no-scope-id",
        "unknown-scope",
        "non-numeric-scope-id",
    ],
)
def test_an_invalid_create_answers_422_and_inserts_nothing__S015_004_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine, payload: dict[str, Any]
) -> None:
    """DoD-5 — D15: blank / missing body, missing ``scope_id``, unknown scope, non-numeric id."""
    client = _player_a(application, db_settings)
    response = client.post(MEMOS_PATH, json=payload)
    assert response.status_code == 422, response.text
    assert _memo_count(engine) == 0


def test_a_non_user_create_without_scope_id_for_an_existing_tree_answers_422__S015_004_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-5 — with real targets present, a missing ``scope_id`` still refuses and writes nothing."""
    client = _player_a(application, db_settings)
    _tree(client)
    for scope in ("character", "setup", "session"):
        response = client.post(MEMOS_PATH, json={"scope": scope, "body": "x"})
        assert response.status_code == 422, response.text
    assert _memo_count(engine) == 0


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?scope=world",
        "?scope=character",
    ],
    ids=["no-scope", "unknown-scope", "character-no-scope-id"],
)
def test_an_invalid_list_query_answers_422__S015_004_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine, query: str
) -> None:
    """DoD-5 — the list's required ``scope``, its literal, and the non-user ``scope_id`` rule."""
    client = _player_a(application, db_settings)
    response = client.get(f"{MEMOS_PATH}{query}")
    assert response.status_code == 422, response.text
    assert _memo_count(engine) == 0


@pytest.mark.parametrize("blank", ["", "   "], ids=["empty", "spaces"])
def test_a_patch_with_a_blank_body_answers_422_and_writes_nothing__S015_004_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine, blank: str
) -> None:
    """DoD-5 — D15: a supplied PATCH ``body`` must be non-blank too."""
    client = _player_a(application, db_settings)
    created = _create(client, "user", None, "kept")

    response = client.patch(_memo_path(created["id"]), json={"body": blank})
    assert response.status_code == 422, response.text
    assert _memo_count(engine) == 1
    assert _list(client, "user", None) == [created]


def test_patch_and_delete_on_a_non_numeric_memo_id_answer_422__S015_004_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-5 — D2: ``/api/memos/abc`` is a native 422 for PATCH and DELETE."""
    client = _player_a(application, db_settings)
    created = _create(client, "user", None, "kept")

    patch_response = client.patch(_memo_path("abc"), json={"body": "y"})
    assert patch_response.status_code == 422, patch_response.text
    delete_response = client.delete(_memo_path("abc"))
    assert delete_response.status_code == 422, delete_response.text

    assert _memo_count(engine) == 1
    assert _list(client, "user", None) == [created]


def test_the_chain_on_a_non_numeric_session_id_answers_422__S015_004_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-5 — ``GET /api/sessions/abc/memo-chain`` is a native 422."""
    client = _player_a(application, db_settings)
    response = client.get(_chain_path("abc"))
    assert response.status_code == 422, response.text
    assert _memo_count(engine) == 0


# --- DoD-6: owner scope ---------------------------------------------------------------


def test_another_users_targets_and_memos_answer_404_like_ids_that_exist_for_nobody__S015_004_DoD6(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-6 — R5, D12: B against A's objects gets the not-found body an unknown id gets."""
    client_a = _player_a(application, db_settings)
    client_b = _player_b(application, db_settings)
    character_id, setup_id, session_id = _tree(client_a)

    a_user_note = _create(client_a, "user", None, "A's user note")
    a_character_note = _create(client_a, "character", character_id, "A's character note")
    count_before = _memo_count(engine)

    level_cases = [
        ("character", character_id, UNKNOWN_CHARACTER_ID, CHARACTER_NOT_FOUND),
        ("setup", setup_id, UNKNOWN_SETUP_ID, SETUP_NOT_FOUND),
        ("session", session_id, UNKNOWN_SESSION_ID, SESSION_NOT_FOUND),
    ]
    for scope, foreign_id, unknown_id, code in level_cases:
        foreign_list = _assert_envelope(_list_request(client_b, scope, foreign_id), 404, code)
        unknown_list = _assert_envelope(_list_request(client_b, scope, unknown_id), 404, code)
        assert foreign_list["error"]["detail"] == {}
        assert foreign_list == unknown_list

        foreign_create = _assert_envelope(_create_request(client_b, scope, foreign_id, "intrude"), 404, code)
        unknown_create = _assert_envelope(_create_request(client_b, scope, unknown_id, "intrude"), 404, code)
        assert foreign_create["error"]["detail"] == {}
        assert foreign_create == unknown_create

    foreign_patch = _assert_envelope(
        client_b.patch(_memo_path(a_character_note["id"]), json={"body": "hijack", "is_enabled": False}),
        404,
        MEMO_NOT_FOUND,
    )
    unknown_patch = _assert_envelope(
        client_b.patch(_memo_path(UNKNOWN_MEMO_ID), json={"body": "hijack", "is_enabled": False}),
        404,
        MEMO_NOT_FOUND,
    )
    assert foreign_patch["error"]["detail"] == {}
    assert foreign_patch == unknown_patch

    foreign_delete = _assert_envelope(client_b.delete(_memo_path(a_character_note["id"])), 404, MEMO_NOT_FOUND)
    unknown_delete = _assert_envelope(client_b.delete(_memo_path(UNKNOWN_MEMO_ID)), 404, MEMO_NOT_FOUND)
    assert foreign_delete["error"]["detail"] == {}
    assert foreign_delete == unknown_delete

    foreign_chain = _assert_envelope(client_b.get(_chain_path(session_id)), 404, SESSION_NOT_FOUND)
    unknown_chain = _assert_envelope(client_b.get(_chain_path(UNKNOWN_SESSION_ID)), 404, SESSION_NOT_FOUND)
    assert foreign_chain["error"]["detail"] == {}
    assert foreign_chain == unknown_chain

    # Afterwards, read as A: nothing changed, nothing was added.
    assert _memo_count(engine) == count_before
    assert _list(client_a, "character", character_id) == [a_character_note]
    assert _list(client_a, "user", None) == [a_user_note]

    # B's own user level holds none of A's user-level notes.
    b_user_ids = _ids(_list(client_b, "user", None))
    assert a_user_note["id"] not in b_user_ids
    assert b_user_ids == []


# --- DoD-7: is_enabled never touches is_forced ----------------------------------------


def test_disabling_and_re_enabling_a_forced_note_keeps_it_forced__S015_004_DoD7(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-7 — US-101.AC-1, R3: re-enabling restores the forced mode."""
    client = _player_a(application, db_settings)
    created = _create(client, "user", None, "always")
    forced = _patch(client, created["id"], {"is_forced": True})
    assert forced["is_forced"] is True
    assert forced["is_enabled"] is True

    disabled = _patch(client, created["id"], {"is_enabled": False})
    assert disabled["is_enabled"] is False
    assert disabled["is_forced"] is True

    enabled = _patch(client, created["id"], {"is_enabled": True})
    assert enabled["is_enabled"] is True
    assert enabled["is_forced"] is True


def test_disabling_and_re_enabling_a_not_forced_note_keeps_it_not_forced__S015_004_DoD7(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-7 — US-101.AC-2, R3: re-enabling restores the not-forced mode."""
    client = _player_a(application, db_settings)
    created = _create(client, "user", None, "sometimes")

    disabled = _patch(client, created["id"], {"is_enabled": False})
    assert disabled["is_enabled"] is False
    assert disabled["is_forced"] is False

    enabled = _patch(client, created["id"], {"is_enabled": True})
    assert enabled["is_enabled"] is True
    assert enabled["is_forced"] is False


# --- DoD-8: PATCH writes only what was supplied ---------------------------------------


def test_forcing_a_disabled_note_keeps_it_disabled__S015_004_DoD8(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-8 — D6: ``is_forced`` alone leaves ``is_enabled`` as it was."""
    client = _player_a(application, db_settings)
    created = _create(client, "user", None, "quiet")
    _patch(client, created["id"], {"is_enabled": False})

    forced = _patch(client, created["id"], {"is_forced": True})
    assert forced["is_enabled"] is False
    assert forced["is_forced"] is True


def test_a_body_patch_changes_only_the_body__S015_004_DoD8(application: FastAPI, db_settings: Settings) -> None:
    """DoD-8 — D6: flags, ``sort_key`` and ``created_at`` unchanged; ``updated_at`` not earlier."""
    client = _player_a(application, db_settings)
    character_id = _character(client)
    _create(client, "character", character_id, "first")
    created = _create(client, "character", character_id, "second")
    shaped = _patch(client, created["id"], {"is_forced": True})

    updated = _patch(client, created["id"], {"body": "y"})
    _assert_memo_shape(updated)
    assert updated["body"] == "y"
    assert updated["id"] == shaped["id"]
    assert updated["scope"] == shaped["scope"]
    assert updated["scope_id"] == shaped["scope_id"]
    assert updated["is_enabled"] == shaped["is_enabled"]
    assert updated["is_forced"] == shaped["is_forced"]
    assert updated["sort_key"] == shaped["sort_key"]
    assert updated["created_at"] == shaped["created_at"]
    assert updated["updated_at"] >= shaped["updated_at"]


def test_a_null_body_in_a_patch_counts_as_not_supplied__S015_004_DoD8(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-8 — request rules: ``"body": null`` leaves the body; the flag still applies."""
    client = _player_a(application, db_settings)
    created = _create(client, "user", None, "unchanged body")

    updated = _patch(client, created["id"], {"body": None, "is_forced": True})
    assert updated["body"] == "unchanged body"
    assert updated["is_forced"] is True
    assert updated["is_enabled"] is True


def test_an_empty_patch_answers_200_with_the_note_unchanged__S015_004_DoD8(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-8 — ``PATCH {}`` supplies nothing and answers the note as it is."""
    client = _player_a(application, db_settings)
    created = _create(client, "user", None, "as is")

    updated = _patch(client, created["id"], {})
    assert updated == created
    assert _list(client, "user", None) == [created]


# --- DoD-9: delete --------------------------------------------------------------------


def test_delete_answers_204_and_the_note_is_gone_everywhere__S015_004_DoD9(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-9 — D2: 204 with an empty body; listing and chain omit it; later PATCH / DELETE 404."""
    client = _player_a(application, db_settings)
    _character_id, _setup_id, session_id = _tree(client)
    kept = _create(client, "session", session_id, "kept")
    doomed = _create(client, "session", session_id, "doomed")

    response = client.delete(_memo_path(doomed["id"]))
    assert response.status_code == 204, response.text
    assert response.content == b""

    assert _ids(_list(client, "session", session_id)) == [kept["id"]]

    levels = _chain(client, session_id)
    every_chain_id = [memo["id"] for level in levels for memo in level["memos"]]
    assert doomed["id"] not in every_chain_id
    assert kept["id"] in every_chain_id

    _assert_envelope(client.patch(_memo_path(doomed["id"]), json={"body": "back"}), 404, MEMO_NOT_FOUND)
    _assert_envelope(client.delete(_memo_path(doomed["id"])), 404, MEMO_NOT_FOUND)


# --- DoD-10 / DoD-11: the chain -------------------------------------------------------


def test_the_chain_of_a_session_with_a_setup_has_four_levels_in_order__S015_004_DoD10(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-10 — UC-046, R2: user, character, setup, session; scope_ids null, C, S, X."""
    client = _player_a(application, db_settings)
    character_id, setup_id, session_id = _tree(client)

    user_note = _create(client, "user", None, "user level")
    character_note = _create(client, "character", character_id, "character level")
    setup_note = _create(client, "setup", setup_id, "setup level")
    session_note = _create(client, "session", session_id, "session level")

    levels = _chain(client, session_id)
    assert [level["scope"] for level in levels] == ["user", "character", "setup", "session"]
    assert [level["scope_id"] for level in levels] == [None, character_id, setup_id, session_id]
    assert levels[0]["memos"] == [user_note]
    assert levels[1]["memos"] == [character_note]
    assert levels[2]["memos"] == [setup_note]
    assert levels[3]["memos"] == [session_note]
    for level in levels:
        for memo in level["memos"]:
            _assert_memo_shape(memo)


def test_the_chain_of_a_session_without_a_setup_has_three_levels__S015_004_DoD11(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-11 — US-057.AC-1, R2: user, character, session — no setup entry, no gap."""
    client = _player_a(application, db_settings)
    character_id = _character(client)
    session_id = _session(client, character_id, None)

    user_note = _create(client, "user", None, "user level")
    character_note = _create(client, "character", character_id, "character level")
    session_note = _create(client, "session", session_id, "session level")

    levels = _chain(client, session_id)
    assert len(levels) == 3
    assert [level["scope"] for level in levels] == ["user", "character", "session"]
    assert [level["scope_id"] for level in levels] == [None, character_id, session_id]
    assert levels[0]["memos"] == [user_note]
    assert levels[1]["memos"] == [character_note]
    assert levels[2]["memos"] == [session_note]


# --- DoD-12: the owner sees disabled notes --------------------------------------------


def test_disabled_notes_are_listed_and_in_the_chain_with_their_flags__S015_004_DoD12__S016_001_DoD12(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-12 — R3: a disabled note, and a disabled forced one, stay visible to the owner.

    Amended by 016/001 DoD-12 (D5): the level lists newest first."""
    client = _player_a(application, db_settings)
    character_id, _setup_id, session_id = _tree(client)

    disabled = _create(client, "character", character_id, "disabled")
    disabled = _patch(client, disabled["id"], {"is_enabled": False})
    disabled_forced = _create(client, "character", character_id, "disabled and forced")
    _patch(client, disabled_forced["id"], {"is_forced": True})
    disabled_forced = _patch(client, disabled_forced["id"], {"is_enabled": False})

    assert (disabled["is_enabled"], disabled["is_forced"]) == (False, False)
    assert (disabled_forced["is_enabled"], disabled_forced["is_forced"]) == (False, True)

    listed = _list(client, "character", character_id)
    assert listed == [disabled_forced, disabled]

    levels = _chain(client, session_id)
    character_level = [level for level in levels if level["scope"] == "character"]
    assert len(character_level) == 1
    assert character_level[0]["memos"] == [disabled_forced, disabled]


# --- DoD-13: archived parents are valid targets ---------------------------------------


def test_archived_character_setup_and_session_still_list_create_and_chain__S015_004_DoD13(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-13 — D8: archive does not cascade; list (200), create (201) and chain (200) succeed."""
    client = _player_a(application, db_settings)
    character_id, setup_id, session_id = _tree(client)

    for path in (
        f"{CHARACTERS_PATH}/{character_id}/archive",
        f"{SETUPS_PATH}/{setup_id}/archive",
        f"{SESSIONS_PATH}/{session_id}/archive",
    ):
        response = client.post(path)
        assert response.status_code == 200, response.text

    for scope, scope_id in (("character", character_id), ("setup", setup_id), ("session", session_id)):
        assert _list_request(client, scope, scope_id).status_code == 200
        created_response = _create_request(client, scope, scope_id, f"on an archived {scope}")
        assert created_response.status_code == 201, created_response.text
        listed = _list(client, scope, scope_id)
        assert _ids(listed) == [created_response.json()["id"]]

    chain_response = client.get(_chain_path(session_id))
    assert chain_response.status_code == 200, chain_response.text


# --- DoD-14: sort_key allocation through the route ------------------------------------


def test_sort_keys_are_allocated_in_creation_order_and_never_reused__S015_004_DoD14__S016_001_DoD12(
    application: FastAPI, db_settings: Settings
) -> None:
    """015 DoD-14, amended by 016/001 DoD-12 (D5): 0, -1, -2 listed newest first as -2, -1,
    0; delete the middle; the next create answers -3 and lists first."""
    client = _player_a(application, db_settings)
    character_id = _character(client)

    first = _create(client, "character", character_id, "one")
    second = _create(client, "character", character_id, "two")
    third = _create(client, "character", character_id, "three")
    assert [first["sort_key"], second["sort_key"], third["sort_key"]] == [0, -1, -2]
    listed = _list(client, "character", character_id)
    assert _ids(listed) == [third["id"], second["id"], first["id"]]
    assert [memo["sort_key"] for memo in listed] == [-2, -1, 0]

    assert client.delete(_memo_path(second["id"])).status_code == 204

    fourth = _create(client, "character", character_id, "four")
    assert fourth["sort_key"] == -3
    listed = _list(client, "character", character_id)
    assert _ids(listed) == [fourth["id"], third["id"], first["id"]]
    assert [memo["sort_key"] for memo in listed] == [-3, -2, 0]


# --- DoD-15: earlier routers still match first ----------------------------------------


def test_earlier_routers_still_answer_with_the_memos_router_registered__S015_004_DoD15(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-15 — D9, registration order: 011's session read and the character collections still answer."""
    client = _player_a(application, db_settings)
    character_id, setup_id, session_id = _tree(client)

    session = _json_object(client.get(f"{SESSIONS_PATH}/{session_id}"), 200)
    assert session["id"] == session_id
    assert session["character_id"] == character_id
    assert session["setup_id"] == setup_id

    sessions_response = client.get(f"{CHARACTERS_PATH}/{character_id}/sessions")
    assert sessions_response.status_code == 200, sessions_response.text
    assert session_id in [row["id"] for row in sessions_response.json()["sessions"]]

    setups_response = client.get(f"{CHARACTERS_PATH}/{character_id}/setups")
    assert setups_response.status_code == 200, setups_response.text


# ======================================================================================
# Feature 016, step 001 — ``PUT /api/memos/order``
# ======================================================================================

ORDER_PATH = "/api/memos/order"
MEMO_ORDER_MISMATCH = "memo_order_mismatch"


def _reorder_request(client: TestClient, payload: dict[str, Any]) -> httpx.Response:
    return client.put(ORDER_PATH, json=payload)


def _level_payload(scope: str, scope_id: str | None, memo_ids: list[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {"scope": scope, "memo_ids": memo_ids}
    if scope_id is not None:
        payload["scope_id"] = scope_id
    return payload


# --- DoD-10: route success ------------------------------------------------------------


def test_put_order_answers_the_level_in_the_given_order__S016_001_DoD10(
    application: FastAPI, db_settings: Settings
) -> None:
    """016/001 DoD-10 — UC-076, US-102: 200 ``{"memos": [...]}`` in the sent order, nine wire
    keys, decimal-string ids, ``sort_key`` 0, 1, 2; the listing and the chain agree."""
    client = _player_a(application, db_settings)
    _character_id, _setup_id, session_id = _tree(client)
    for body in ("one", "two", "three"):
        _create(client, "session", session_id, body)
    current = _ids(_list(client, "session", session_id))
    new_order = list(reversed(current))

    response = _reorder_request(client, _level_payload("session", session_id, new_order))
    answered = _json_object(response, 200)

    assert set(answered) == {"memos"}
    memos = answered["memos"]
    assert isinstance(memos, list)
    assert _ids(memos) == new_order
    for memo in memos:
        _assert_memo_shape(memo)
        assert isinstance(memo["id"], str) and memo["id"].isdigit()
        assert memo["scope"] == "session"
        assert memo["scope_id"] == session_id
    assert [memo["sort_key"] for memo in memos] == [0, 1, 2]

    assert _ids(_list(client, "session", session_id)) == new_order

    levels = _chain(client, session_id)
    session_levels = [level for level in levels if level["scope"] == "session"]
    assert len(session_levels) == 1
    assert _ids(session_levels[0]["memos"]) == new_order


# --- DoD-11: route failures -----------------------------------------------------------


def test_put_order_without_a_login_cookie_answers_401__S016_001_DoD11(
    application: FastAPI, db_settings: Settings
) -> None:
    """016/001 DoD-11 — no login cookie → 401 ``not_authenticated``; nothing changed."""
    owner = _player_a(application, db_settings)
    older = _create(owner, "user", None, "older")
    newer = _create(owner, "user", None, "newer")
    listed_before = _list(owner, "user", None)

    response = _reorder_request(
        _anonymous(application), _level_payload("user", None, [older["id"], newer["id"]])
    )

    _assert_envelope(response, 401, NOT_AUTHENTICATED)
    assert _list(owner, "user", None) == listed_before


def test_put_order_on_another_users_level_answers_its_not_found__S016_001_DoD11(
    application: FastAPI, db_settings: Settings
) -> None:
    """016/001 DoD-11 — R5: B reordering A's character / setup / session level answers 404
    with that level's code and an empty ``detail``; A's listing order is unchanged."""
    client_a = _player_a(application, db_settings)
    client_b = _player_b(application, db_settings)
    character_id, setup_id, session_id = _tree(client_a)

    cases = [
        ("character", character_id, CHARACTER_NOT_FOUND),
        ("setup", setup_id, SETUP_NOT_FOUND),
        ("session", session_id, SESSION_NOT_FOUND),
    ]
    for scope, scope_id, _code in cases:
        _create(client_a, scope, scope_id, f"{scope} older")
        _create(client_a, scope, scope_id, f"{scope} newer")
    before = {scope: _list(client_a, scope, scope_id) for scope, scope_id, _code in cases}

    for scope, scope_id, code in cases:
        reversed_ids = list(reversed(_ids(before[scope])))
        body = _assert_envelope(
            _reorder_request(client_b, _level_payload(scope, scope_id, reversed_ids)), 404, code
        )
        assert body["error"]["detail"] == {}

    for scope, scope_id, _code in cases:
        assert _list(client_a, scope, scope_id) == before[scope]


@pytest.mark.parametrize(
    "case",
    ["omit-one", "another-level", "another-users-note", "repeated-id"],
)
def test_put_order_with_a_stale_set_answers_409__S016_001_DoD11(
    application: FastAPI, db_settings: Settings, engine: Engine, case: str
) -> None:
    """016/001 DoD-11 — US-103.AC-2, D6: a ``memo_ids`` that omits a note, includes a note of
    another level or of user B, or repeats an id → 409 ``memo_order_mismatch``, empty
    ``detail``; A's listing order is unchanged."""
    client_a = _player_a(application, db_settings)
    client_b = _player_b(application, db_settings)
    _character_id, _setup_id, session_id = _tree(client_a)
    for body in ("one", "two", "three"):
        _create(client_a, "session", session_id, body)
    other_level = _create(client_a, "user", None, "A at the user level")
    b_note = _create(client_b, "user", None, "B's own")
    listed_before = _list(client_a, "session", session_id)
    count_before = _memo_count(engine)
    full = list(reversed(_ids(listed_before)))

    memo_ids = {
        "omit-one": full[:-1],
        "another-level": [*full, other_level["id"]],
        "another-users-note": [*full, b_note["id"]],
        "repeated-id": [*full, full[0]],
    }[case]

    body = _assert_envelope(
        _reorder_request(client_a, _level_payload("session", session_id, memo_ids)), 409, MEMO_ORDER_MISMATCH
    )
    assert body["error"]["detail"] == {}
    assert isinstance(body["error"]["message"], str) and body["error"]["message"].strip()

    assert _list(client_a, "session", session_id) == listed_before
    assert _list(client_a, "user", None) == [other_level]
    assert _list(client_b, "user", None) == [b_note]
    assert _memo_count(engine) == count_before


@pytest.mark.parametrize(
    "case",
    ["missing-memo-ids", "non-numeric-id", "unknown-scope", "non-user-scope-without-scope-id"],
)
def test_put_order_with_an_invalid_body_answers_422__S016_001_DoD11(
    application: FastAPI, db_settings: Settings, engine: Engine, case: str
) -> None:
    """016/001 DoD-11 — a missing ``memo_ids``, a non-numeric id, scope ``"world"``, or a
    non-user scope without ``scope_id`` → 422; nothing changed."""
    client = _player_a(application, db_settings)
    _character_id, _setup_id, session_id = _tree(client)
    for body in ("one", "two"):
        _create(client, "session", session_id, body)
    listed_before = _list(client, "session", session_id)
    count_before = _memo_count(engine)
    reversed_ids = list(reversed(_ids(listed_before)))

    payload: dict[str, Any] = {
        "missing-memo-ids": {"scope": "session", "scope_id": session_id},
        "non-numeric-id": {"scope": "session", "scope_id": session_id, "memo_ids": [reversed_ids[0], "abc"]},
        "unknown-scope": {"scope": "world", "scope_id": session_id, "memo_ids": reversed_ids},
        "non-user-scope-without-scope-id": {"scope": "session", "memo_ids": reversed_ids},
    }[case]

    response = _reorder_request(client, payload)

    assert response.status_code == 422, response.text
    assert _list(client, "session", session_id) == listed_before
    assert _memo_count(engine) == count_before


# --- DoD-13: the existing memo routes still answer ------------------------------------


def test_the_existing_memo_routes_still_answer_with_the_order_route_declared__S016_001_DoD13(
    application: FastAPI, db_settings: Settings
) -> None:
    """016/001 DoD-13 — route order: PATCH 200, DELETE 204, GET ``?scope=user`` 200."""
    client = _player_a(application, db_settings)
    created = _create(client, "user", None, "x")

    patched = client.patch(_memo_path(created["id"]), json={"body": "y"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["body"] == "y"

    deleted = client.delete(_memo_path(created["id"]))
    assert deleted.status_code == 204, deleted.text

    listed = client.get(f"{MEMOS_PATH}?scope=user")
    assert listed.status_code == 200, listed.text


# --- DoD-14: the router holds no SQL construct ----------------------------------------

_SQL_CONSTRUCTS = {"select", "update", "insert", "delete"}


def test_the_memos_router_contains_no_sql_construct__S016_001_DoD14() -> None:
    """016/001 DoD-14 — 015 D11: no ``select(`` / ``update(`` / ``insert(`` / ``delete(``
    construct in ``app/routers/memos.py``. The router's own route decorator
    (``router.delete(...)``) is the HTTP method, not a SQL construct."""
    tree = ast.parse(inspect.getsource(memos_router_module))

    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _SQL_CONSTRUCTS:
                offenders.append(ast.unparse(node))
            elif isinstance(func, ast.Attribute) and func.attr in _SQL_CONSTRUCTS:
                receiver = func.value
                if not (isinstance(receiver, ast.Name) and receiver.id == "router"):
                    offenders.append(ast.unparse(node))
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("sqlalchemy"):
            imported = {alias.name for alias in node.names}
            offenders.extend(f"from {node.module} import {name}" for name in imported & _SQL_CONSTRUCTS)

    assert offenders == []
