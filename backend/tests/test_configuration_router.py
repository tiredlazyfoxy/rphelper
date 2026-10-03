"""Tests for the configuration router: ``/api/models``, ``/api/me/settings``,
``/api/sessions/{session_id}/configuration`` and ``/api/characters/{character_id}/configuration``
— feature 017, step 005.

Every expected value comes from ``docs/plans/017.session-configuration/005.configuration-router.md``
(Interface intent, DoD-1 .. DoD-10), ``005.context.md`` and the feature ``context.md``: the **Wire
contract** (seven routes, the ``EnabledModel`` / ``UserSettings`` / ``CharacterConfiguration`` /
``Setting`` / ``SessionConfiguration`` shapes, the level rules, the request rules and the failure
table), **D1** (capture), **D5** (tools default on), **D6** (normalisation), **D7** (order:
``llm_servers.id`` then ``models.id``), **D9** (``Session`` unchanged, ``PATCH /api/sessions/{id}``
still 405), **D10** (set-time check, nothing written on failure, session ``model: null`` is 422),
**D11** (``updated_at`` bumped, ``last_used_at`` never), **D13** (router last), **D14**, R1, R5, R6.
No resolver is called to compute an expectation.

Bindings come from ``status.md`` ``## Skeleton`` -> Step 005 (the seven full literal paths and their
200 status, router-level ``require_user``, ``router`` in ``app.routers.configuration``, included last
by ``create_app()``) and Step 001 (wire shapes).

The application is the real factory's (``create_app()``), pinned to the per-test database through
``dependency_overrides[get_settings]``. Each signed-in caller has its own ``TestClient`` with exactly
one session cookie. Characters and sessions are created through 009's / 011's routes and archived
through their archive routes; ``llm_servers`` / ``models`` are raw-inserted and ``models.is_enabled``
is raw-updated between creations (005.context "Test fixtures"). ``conftest.py`` is untouched. Tests
are suffixed ``__S017_005_DoD<n>``. DoD-11 is ``[manual/live]`` and carries no test.
"""

import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import Engine, Table, update

from app.config import Settings, get_settings
from app.db import schema
from app.main import create_app
from app.roles import Role
from app.routers.configuration import router as configuration_router
from app.services.passwords import hash_password

CHARACTERS_PATH = "/api/characters"
SESSIONS_PATH = "/api/sessions"
MODELS_PATH = "/api/models"
ME_PATH = "/api/me"
ME_SETTINGS_PATH = "/api/me/settings"
LOGIN_PATH = "/api/auth/login"

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

ADMIN_ID = 9_700_001
ADMIN_NAME = "warden"
ADMIN_PASSWORD = "an iron gate in winter"

PLAYER_A_ID = 9_700_002
PLAYER_A_NAME = "aster"
PLAYER_A_PASSWORD = "a quiet river at dusk"

PLAYER_B_ID = 9_700_003
PLAYER_B_NAME = "briar"
PLAYER_B_PASSWORD = "salt and lantern light"

#: Large decimal id strings no row holds.
UNKNOWN_CHARACTER_ID = "7250000000000000501"
UNKNOWN_SESSION_ID = "7250000000000000502"

#: Registry ids chosen so server-id order and models.id order disagree (feature "Registry fixtures").
#: D7 order is server id ascending, then models.id ascending:
#:   LOW_FIRST (server 5_100, model 62_001), LOW_SECOND (5_100, 62_002), HIGH_FIRST (5_200, 61_001).
#: By models.id alone HIGH_FIRST would come first — the tests would catch that.
SERVER_LOW = 5_100
SERVER_LOW_NAME = "Zephyr box"
SERVER_HIGH = 5_200
SERVER_HIGH_NAME = "Atlas box"

MODEL_LOW_FIRST = 62_001
MODEL_LOW_FIRST_NAME = "low-first"
MODEL_LOW_SECOND = 62_002
MODEL_LOW_SECOND_NAME = "low-second"
MODEL_HIGH_FIRST = 61_001
MODEL_HIGH_FIRST_NAME = "high-first"
MODEL_LOW_OFF = 60_500
MODEL_LOW_OFF_NAME = "low-off"

MISSING_SERVER_ID = 7_777_777

#: The ``Session`` wire object's eight keys (011's Wire contract; D9 keeps it).
SESSION_KEYS = {
    "id",
    "character_id",
    "setup_id",
    "setup_name",
    "archived_at",
    "last_used_at",
    "created_at",
    "updated_at",
}

#: ``SessionConfiguration``'s seven keys; each ``Setting``'s five keys (Wire contract).
SESSION_CONFIGURATION_KEYS = {
    "model",
    "system_prompt",
    "tool_memo_search",
    "tool_session_search",
    "tool_web_search",
    "rp_language",
    "preferred_language",
}
SETTING_KEYS = {"session", "inherited", "inherited_level", "value", "level"}
TOOL_KEYS = ("tool_memo_search", "tool_session_search", "tool_web_search")

#: The seven routes of the Wire contract (D13).
CONFIGURATION_ROUTES = {
    ("/api/models", "GET"),
    ("/api/me/settings", "GET"),
    ("/api/me/settings", "PATCH"),
    ("/api/sessions/{session_id}/configuration", "GET"),
    ("/api/sessions/{session_id}/configuration", "PATCH"),
    ("/api/characters/{character_id}/configuration", "GET"),
    ("/api/characters/{character_id}/configuration", "PATCH"),
}

NOT_AUTHENTICATED = "not_authenticated"
SESSION_NOT_FOUND = "session_not_found"
CHARACTER_NOT_FOUND = "character_not_found"
MODEL_NOT_ENABLED = "model_not_enabled"


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
) -> None:
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


def _seed(engine: Engine) -> None:
    with engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(engine, user_id=ADMIN_ID, username=ADMIN_NAME, password=ADMIN_PASSWORD, role=Role.ADMIN)
    _insert_user(
        engine, user_id=PLAYER_A_ID, username=PLAYER_A_NAME, password=PLAYER_A_PASSWORD, role=Role.ROLEPLAYER
    )
    _insert_user(
        engine, user_id=PLAYER_B_ID, username=PLAYER_B_NAME, password=PLAYER_B_PASSWORD, role=Role.ROLEPLAYER
    )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database with the schema applied, an admin and two roleplayers seeded, no registry."""
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


# --- registry seeding (raw inserts) ---------------------------------------------------


def _servers() -> Table:
    return schema.metadata.tables["llm_servers"]


def _models() -> Table:
    return schema.metadata.tables["models"]


def _insert_server(engine: Engine, *, server_id: int, name: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            _servers()
            .insert()
            .values(
                id=server_id,
                name=name,
                kind="llamaswap",
                base_url=f"http://llm-{server_id}.test:8080",
                api_key_ref=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_model(engine: Engine, *, model_id: int, server_id: int, name: str, enabled: bool) -> None:
    with engine.begin() as connection:
        connection.execute(
            _models()
            .insert()
            .values(
                id=model_id,
                server_id=server_id,
                model_name=name,
                is_enabled=enabled,
                is_embedding_designated=False,
                embedding_dim=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _set_enabled(engine: Engine, model_id: int, enabled: bool) -> None:
    with engine.begin() as connection:
        connection.execute(update(_models()).where(_models().c.id == model_id).values(is_enabled=enabled))


def _seed_registry(engine: Engine, *, low_second_enabled: bool = True, high_first_enabled: bool = True) -> None:
    """Two servers; three chat models plus one disabled model; id orders disagree (D7)."""
    _insert_server(engine, server_id=SERVER_LOW, name=SERVER_LOW_NAME)
    _insert_server(engine, server_id=SERVER_HIGH, name=SERVER_HIGH_NAME)
    _insert_model(engine, model_id=MODEL_HIGH_FIRST, server_id=SERVER_HIGH, name=MODEL_HIGH_FIRST_NAME,
                  enabled=high_first_enabled)
    _insert_model(engine, model_id=MODEL_LOW_OFF, server_id=SERVER_LOW, name=MODEL_LOW_OFF_NAME, enabled=False)
    _insert_model(engine, model_id=MODEL_LOW_SECOND, server_id=SERVER_LOW, name=MODEL_LOW_SECOND_NAME,
                  enabled=low_second_enabled)
    _insert_model(engine, model_id=MODEL_LOW_FIRST, server_id=SERVER_LOW, name=MODEL_LOW_FIRST_NAME, enabled=True)


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


def _login(application: FastAPI, settings: Settings, username: str, password: str) -> TestClient:
    """A fresh client carrying exactly this account's session cookie — never shared."""
    fresh = TestClient(application)
    fresh.cookies.set(settings.session_cookie_name, _login_token(application, settings, username, password))
    return fresh


def _anonymous(application: FastAPI) -> TestClient:
    return TestClient(application)


def _admin(application: FastAPI, settings: Settings) -> TestClient:
    return _login(application, settings, ADMIN_NAME, ADMIN_PASSWORD)


def _player_a(application: FastAPI, settings: Settings) -> TestClient:
    return _login(application, settings, PLAYER_A_NAME, PLAYER_A_PASSWORD)


def _player_b(application: FastAPI, settings: Settings) -> TestClient:
    return _login(application, settings, PLAYER_B_NAME, PLAYER_B_PASSWORD)


# --- exact paths ---------------------------------------------------------------------


def _session_path(session_id: Any) -> str:
    return f"{SESSIONS_PATH}/{session_id}"


def _session_configuration_path(session_id: Any) -> str:
    return f"{SESSIONS_PATH}/{session_id}/configuration"


def _character_configuration_path(character_id: Any) -> str:
    return f"{CHARACTERS_PATH}/{character_id}/configuration"


def _character_sessions_path(character_id: Any) -> str:
    return f"{CHARACTERS_PATH}/{character_id}/sessions"


# --- request / assertion helpers -----------------------------------------------------


def _ref(server_id: int, model_name: str) -> dict[str, str]:
    """A ``ModelRef`` on the wire: decimal-string ``server_id``."""
    return {"server_id": str(server_id), "model_name": model_name}


def _setting(
    session: Any, inherited: Any, inherited_level: str | None, value: Any, level: str | None
) -> dict[str, Any]:
    return {
        "session": session,
        "inherited": inherited,
        "inherited_level": inherited_level,
        "value": value,
        "level": level,
    }


def _json(response: httpx.Response, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _assert_envelope(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error, dict)
    assert error["code"] == code
    return body


def _character(client: TestClient, name: str) -> dict[str, Any]:
    """009's create route."""
    created = _json(client.post(CHARACTERS_PATH, json={"name": name, "sheet": ""}), 201)
    assert isinstance(created, dict)
    return created


def _start(client: TestClient, character_id: Any) -> dict[str, Any]:
    """011's start route (unchanged)."""
    created = _json(client.post(_character_sessions_path(character_id), json={}), 201)
    assert isinstance(created, dict)
    return created


def _read_session(client: TestClient, session_id: Any) -> dict[str, Any]:
    body = _json(client.get(_session_path(session_id)))
    assert isinstance(body, dict)
    return body


def _models_list(client: TestClient) -> Any:
    return _json(client.get(MODELS_PATH))


def _session_configuration(client: TestClient, session_id: Any) -> dict[str, Any]:
    body = _json(client.get(_session_configuration_path(session_id)))
    assert isinstance(body, dict)
    assert set(body) == SESSION_CONFIGURATION_KEYS
    for key in SESSION_CONFIGURATION_KEYS - {"model"}:
        assert set(body[key]) == SETTING_KEYS, key
    return body


def _patch_session(client: TestClient, session_id: Any, body: Any) -> httpx.Response:
    return client.patch(_session_configuration_path(session_id), json=body)


def _character_configuration(client: TestClient, character_id: Any) -> dict[str, Any]:
    body = _json(client.get(_character_configuration_path(character_id)))
    assert isinstance(body, dict)
    return body


def _patch_character(client: TestClient, character_id: Any, body: Any) -> httpx.Response:
    return client.patch(_character_configuration_path(character_id), json=body)


def _patch_settings(client: TestClient, body: Any) -> httpx.Response:
    return client.patch(ME_SETTINGS_PATH, json=body)


def _assert_default_tools(configuration: dict[str, Any]) -> None:
    """Wire contract: a tool no level sets is on, inherited true at level ``default`` (D5)."""
    for key in TOOL_KEYS:
        assert configuration[key] == _setting(None, True, "default", True, "default"), key


# --- DoD-1: GET /api/models ----------------------------------------------------------


def test_models_lists_enabled_models_in_server_then_model_id_order__S017_005_DoD1(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-1 — D7: server id ascending then models.id ascending; disabled models absent."""
    _seed_registry(engine)
    client = _player_a(application, db_settings)

    body = _models_list(client)

    assert body == {
        "models": [
            {"server_id": str(SERVER_LOW), "server_name": SERVER_LOW_NAME, "model_name": MODEL_LOW_FIRST_NAME},
            {"server_id": str(SERVER_LOW), "server_name": SERVER_LOW_NAME, "model_name": MODEL_LOW_SECOND_NAME},
            {"server_id": str(SERVER_HIGH), "server_name": SERVER_HIGH_NAME, "model_name": MODEL_HIGH_FIRST_NAME},
        ]
    }


def test_each_listed_model_carries_exactly_three_keys__S017_005_DoD1(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-1 — Wire contract: `EnabledModel` never carries `base_url`, `kind`, `api_key_ref` or test status."""
    _seed_registry(engine)
    client = _player_a(application, db_settings)

    body = _models_list(client)

    assert set(body) == {"models"}
    assert body["models"]
    for item in body["models"]:
        assert set(item) == {"server_id", "server_name", "model_name"}
        assert isinstance(item["server_id"], str)
        assert item["server_id"].isdigit()
        for forbidden in ("base_url", "kind", "api_key_ref", "id"):
            assert forbidden not in item


def test_models_answers_an_empty_list_when_none_is_enabled__S017_005_DoD1(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-1 — Wire contract: `[]` when none (empty registry, then only disabled rows)."""
    client = _player_a(application, db_settings)
    assert _models_list(client) == {"models": []}

    _seed_registry(engine)
    for model_id in (MODEL_LOW_FIRST, MODEL_LOW_SECOND, MODEL_HIGH_FIRST):
        _set_enabled(engine, model_id, False)

    assert _models_list(client) == {"models": []}


def test_a_roleplayer_gets_the_same_models_answer_as_an_admin__S017_005_DoD1(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-1 — D13: the route is roleplayer-facing (`require_user`), not admin-only."""
    _seed_registry(engine)

    as_admin = _models_list(_admin(application, db_settings))
    as_roleplayer = _models_list(_player_a(application, db_settings))

    assert as_roleplayer == as_admin
    assert len(as_roleplayer["models"]) == 3


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", MODELS_PATH),
        ("GET", ME_SETTINGS_PATH),
        ("PATCH", ME_SETTINGS_PATH),
        ("GET", _session_configuration_path(UNKNOWN_SESSION_ID)),
        ("PATCH", _session_configuration_path(UNKNOWN_SESSION_ID)),
        ("GET", _character_configuration_path(UNKNOWN_CHARACTER_ID)),
        ("PATCH", _character_configuration_path(UNKNOWN_CHARACTER_ID)),
    ],
    ids=["models", "settings-get", "settings-patch", "session-get", "session-patch", "character-get",
         "character-patch"],
)
def test_every_configuration_route_answers_401_without_a_login__S017_005_DoD1(
    application: FastAPI, method: str, path: str
) -> None:
    """DoD-1 — Wire contract, D13: router-level `require_user` → 401 `not_authenticated`."""
    client = _anonymous(application)

    response = client.request(method, path, json={} if method == "PATCH" else None)

    _assert_envelope(response, 401, NOT_AUTHENTICATED)


# --- DoD-2: user settings -------------------------------------------------------------


def test_patching_settings_trims_and_persists_both_languages__S017_005_DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — US-058.AC-1, D6: languages trimmed; a later GET answers the same."""
    client = _player_a(application, db_settings)

    patched = _json(_patch_settings(client, {"rp_language": " Japanese ", "preferred_language": "English"}))

    assert patched == {"rp_language": "Japanese", "preferred_language": "English"}
    assert _json(client.get(ME_SETTINGS_PATH)) == {"rp_language": "Japanese", "preferred_language": "English"}
    fresh = _player_a(application, db_settings)
    assert _json(fresh.get(ME_SETTINGS_PATH)) == {"rp_language": "Japanese", "preferred_language": "English"}


def test_a_second_users_settings_are_unaffected__S017_005_DoD2(application: FastAPI, db_settings: Settings) -> None:
    """DoD-2 — R5: B's settings stay null after A saves."""
    owner = _player_a(application, db_settings)
    other = _player_b(application, db_settings)

    _json(_patch_settings(owner, {"rp_language": " Japanese ", "preferred_language": "English"}))

    assert _json(other.get(ME_SETTINGS_PATH)) == {"rp_language": None, "preferred_language": None}


def test_a_blank_rp_language_answers_null_and_leaves_the_other_untouched__S017_005_DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — D6: a blank language is stored as null; an absent key changes nothing."""
    client = _player_a(application, db_settings)
    _json(_patch_settings(client, {"rp_language": "Japanese", "preferred_language": "English"}))

    patched = _json(_patch_settings(client, {"rp_language": ""}))

    assert patched == {"rp_language": None, "preferred_language": "English"}
    assert _json(client.get(ME_SETTINGS_PATH)) == {"rp_language": None, "preferred_language": "English"}


def test_get_me_still_answers_exactly_id_username_role__S017_005_DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — D14: `GET /api/me` is unchanged after settings are saved."""
    client = _player_a(application, db_settings)
    _json(_patch_settings(client, {"rp_language": "Japanese", "preferred_language": "English"}))

    body = _json(client.get(ME_PATH))

    assert set(body) == {"id", "username", "role"}
    assert body["username"] == PLAYER_A_NAME


# --- DoD-3: end to end, default capture and inheritance -------------------------------


def test_a_new_session_captures_the_first_enabled_model_and_inherits_defaults__S017_005_DoD3__S018_002_DoD8(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-3 — US-106.AC-1, US-108.AC-1/AC-2, D1, D5: first enabled in D7 order, tools default on, no prompt.

    Amended by 018 step 002 DoD-8 (018 D3): the start route now answers `StartedSession`, the
    eight session keys plus `opening_message` (null here: none was sent)."""
    _seed_registry(engine, low_second_enabled=False)  # two enabled: LOW_FIRST, HIGH_FIRST
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")

    session = _start(client, character["id"])

    assert set(session) == SESSION_KEYS | {"opening_message"}
    configuration = _session_configuration(client, session["id"])
    assert configuration["model"] == _ref(SERVER_LOW, MODEL_LOW_FIRST_NAME)
    _assert_default_tools(configuration)
    assert configuration["system_prompt"] == _setting(None, None, None, None, None)
    assert configuration["rp_language"] == _setting(None, None, None, None, None)
    assert configuration["preferred_language"] == _setting(None, None, None, None, None)


def test_the_session_languages_come_from_the_user_once_set__S017_005_DoD3(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-3 — US-108.AC-2, R1: the language chain is user → session."""
    _seed_registry(engine, low_second_enabled=False)
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    session = _start(client, character["id"])

    _json(_patch_settings(client, {"rp_language": "Japanese", "preferred_language": "English"}))

    configuration = _session_configuration(client, session["id"])
    assert configuration["rp_language"] == _setting(None, "Japanese", "user", "Japanese", "user")
    assert configuration["preferred_language"] == _setting(None, "English", "user", "English", "user")
    assert configuration["model"] == _ref(SERVER_LOW, MODEL_LOW_FIRST_NAME)


# --- DoD-4: character overrides -------------------------------------------------------


def test_a_character_patch_answers_the_written_values__S017_005_DoD4(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-4 — US-059.AC-2: model, prompt and memo search come back; a later GET matches."""
    _seed_registry(engine)
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")

    patched = _json(
        _patch_character(
            client,
            character["id"],
            {
                "model": _ref(SERVER_HIGH, MODEL_HIGH_FIRST_NAME),
                "system_prompt": "Stay in character.",
                "tool_memo_search": False,
            },
        )
    )

    expected = {
        "model": _ref(SERVER_HIGH, MODEL_HIGH_FIRST_NAME),
        "system_prompt": "Stay in character.",
        "tool_memo_search": False,
        "tool_session_search": None,
        "tool_web_search": None,
    }
    assert patched == expected
    assert _character_configuration(client, character["id"]) == expected


def test_an_earlier_session_keeps_its_model_but_takes_the_live_prompt_and_tool__S017_005_DoD4(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-4 — US-139.AC-1, US-059.AC-1, US-062.AC-1: model captured; prompt and tools live from the character."""
    _seed_registry(engine)
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    before = _start(client, character["id"])

    _json(
        _patch_character(
            client,
            character["id"],
            {
                "model": _ref(SERVER_HIGH, MODEL_HIGH_FIRST_NAME),
                "system_prompt": "Stay in character.",
                "tool_memo_search": False,
            },
        )
    )

    configuration = _session_configuration(client, before["id"])
    assert configuration["model"] == _ref(SERVER_LOW, MODEL_LOW_FIRST_NAME)
    assert configuration["system_prompt"] == _setting(
        None, "Stay in character.", "character", "Stay in character.", "character"
    )
    assert configuration["tool_memo_search"] == _setting(None, False, "character", False, "character")
    assert configuration["tool_session_search"] == _setting(None, True, "default", True, "default")
    assert configuration["tool_web_search"] == _setting(None, True, "default", True, "default")


def test_a_later_session_captures_the_characters_model__S017_005_DoD4(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-4 — US-139.AC-2, D1: a session created after the character write captures its model."""
    _seed_registry(engine)
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    _start(client, character["id"])
    _json(
        _patch_character(
            client,
            character["id"],
            {
                "model": _ref(SERVER_HIGH, MODEL_HIGH_FIRST_NAME),
                "system_prompt": "Stay in character.",
                "tool_memo_search": False,
            },
        )
    )

    after = _start(client, character["id"])

    configuration = _session_configuration(client, after["id"])
    assert configuration["model"] == _ref(SERVER_HIGH, MODEL_HIGH_FIRST_NAME)
    assert configuration["system_prompt"]["value"] == "Stay in character."
    assert configuration["system_prompt"]["level"] == "character"
    assert configuration["tool_memo_search"]["value"] is False
    assert configuration["tool_memo_search"]["level"] == "character"


# --- DoD-5: session model -------------------------------------------------------------


def test_a_session_model_patch_answers_and_persists_the_model__S017_005_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-5 — US-105.AC-1/AC-2: 200 with that model; a later GET (new request) answers the same."""
    _seed_registry(engine)
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    session = _start(client, character["id"])

    patched = _json(_patch_session(client, session["id"], {"model": _ref(SERVER_HIGH, MODEL_HIGH_FIRST_NAME)}))

    assert patched["model"] == _ref(SERVER_HIGH, MODEL_HIGH_FIRST_NAME)
    fresh = _player_a(application, db_settings)
    assert _session_configuration(fresh, session["id"])["model"] == _ref(SERVER_HIGH, MODEL_HIGH_FIRST_NAME)


@pytest.mark.parametrize(
    ("server_id", "model_name"),
    [
        pytest.param(SERVER_LOW, MODEL_LOW_OFF_NAME, id="disabled-model"),
        pytest.param(MISSING_SERVER_ID, "ghost-chat", id="no-such-server"),
    ],
)
def test_a_session_model_that_is_not_enabled_answers_409_and_writes_nothing__S017_005_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine, server_id: int, model_name: str
) -> None:
    """DoD-5 — D10: 409 `model_not_enabled`, detail `{server_id, model_name, level: "session"}`; model kept."""
    _seed_registry(engine)
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    session = _start(client, character["id"])
    before = _session_configuration(client, session["id"])

    response = _patch_session(client, session["id"], {"model": _ref(server_id, model_name)})

    body = _assert_envelope(response, 409, MODEL_NOT_ENABLED)
    assert body["error"]["detail"] == {"server_id": str(server_id), "model_name": model_name, "level": "session"}
    after = _session_configuration(client, session["id"])
    assert after["model"] == _ref(SERVER_LOW, MODEL_LOW_FIRST_NAME)
    assert after == before


def test_a_refused_session_model_writes_no_other_field_either__S017_005_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-5 — D10: nothing in the request is written when its model is not enabled."""
    _seed_registry(engine)
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    session = _start(client, character["id"])
    before = _session_configuration(client, session["id"])

    response = _patch_session(
        client,
        session["id"],
        {"model": _ref(SERVER_LOW, MODEL_LOW_OFF_NAME), "system_prompt": "S", "tool_web_search": False},
    )

    _assert_envelope(response, 409, MODEL_NOT_ENABLED)
    assert _session_configuration(client, session["id"]) == before


def test_a_null_session_model_answers_422__S017_005_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-5 — D10: the session's model is only ever replaced; `model: null` is a 422."""
    _seed_registry(engine)
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    session = _start(client, character["id"])
    before = _session_configuration(client, session["id"])

    response = _patch_session(client, session["id"], {"model": None})

    assert response.status_code == 422, response.text
    assert _session_configuration(client, session["id"]) == before


# --- DoD-6: session overrides and clearing --------------------------------------------


#: DoD-6's first PATCH body, verbatim from the step file.
_SESSION_OVERRIDES = {"system_prompt": "S", "tool_web_search": False, "rp_language": "French"}


def _session_under_configured_character(
    application: FastAPI, settings: Settings, engine: Engine
) -> tuple[TestClient, dict[str, Any]]:
    """A's session under a character with prompt "C" and web search on; A's RP language "Japanese"."""
    _seed_registry(engine)
    client = _player_a(application, settings)
    character = _character(client, "Aria")
    _json(_patch_character(client, character["id"], {"system_prompt": "C", "tool_web_search": True}))
    _json(_patch_settings(client, {"rp_language": "Japanese"}))
    session = _start(client, character["id"])
    return client, session


def test_session_overrides_answer_at_level_session_with_inherited_shown__S017_005_DoD6(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-6 — US-060.AC-1, US-061.AC-2, US-062.AC-2, R1: session wins; `inherited` still the level above."""
    client, session = _session_under_configured_character(application, db_settings, engine)

    patched = _json(_patch_session(client, session["id"], _SESSION_OVERRIDES))

    assert patched["system_prompt"] == _setting("S", "C", "character", "S", "session")
    assert patched["tool_web_search"] == _setting(False, True, "character", False, "session")
    assert patched["rp_language"] == _setting("French", "Japanese", "user", "French", "session")
    assert _session_configuration(client, session["id"]) == patched


def test_null_clears_restore_inheritance_and_leave_other_overrides__S017_005_DoD6(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-6 — Wire contract request rules: an explicit null clears; an absent key changes nothing."""
    client, session = _session_under_configured_character(application, db_settings, engine)
    _json(_patch_session(client, session["id"], _SESSION_OVERRIDES))

    patched = _json(_patch_session(client, session["id"], {"system_prompt": None, "rp_language": None}))

    assert patched["system_prompt"] == _setting(None, "C", "character", "C", "character")
    assert patched["rp_language"] == _setting(None, "Japanese", "user", "Japanese", "user")
    assert patched["tool_web_search"] == _setting(False, True, "character", False, "session")
    assert _session_configuration(client, session["id"]) == patched


# --- DoD-7: character route has no language level; model checks and clear ------------


def test_language_keys_on_the_character_route_change_nothing__S017_005_DoD7(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-7 — US-061.AC-3, R1: unknown keys are ignored; 200 with the current state."""
    _seed_registry(engine)
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    _json(_patch_settings(client, {"rp_language": "Japanese", "preferred_language": "German"}))
    before = _character_configuration(client, character["id"])

    patched = _json(
        _patch_character(client, character["id"], {"rp_language": "French", "preferred_language": "English"})
    )

    assert patched == before
    assert _character_configuration(client, character["id"]) == before
    session = _start(client, character["id"])
    configuration = _session_configuration(client, session["id"])
    assert configuration["rp_language"] == _setting(None, "Japanese", "user", "Japanese", "user")
    assert configuration["preferred_language"] == _setting(None, "German", "user", "German", "user")


def test_a_disabled_character_model_answers_409_at_level_character__S017_005_DoD7(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-7 — D10: `model_not_enabled` with `detail.level` "character"; nothing written."""
    _seed_registry(engine)
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    before = _character_configuration(client, character["id"])

    response = _patch_character(
        client, character["id"], {"model": _ref(SERVER_LOW, MODEL_LOW_OFF_NAME), "system_prompt": "Stay."}
    )

    body = _assert_envelope(response, 409, MODEL_NOT_ENABLED)
    assert body["error"]["detail"] == {
        "server_id": str(SERVER_LOW),
        "model_name": MODEL_LOW_OFF_NAME,
        "level": "character",
    }
    assert _character_configuration(client, character["id"]) == before


def test_a_null_character_model_clears_it__S017_005_DoD7(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-7 — D10: on the character route `model: null` clears the override."""
    _seed_registry(engine)
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    _json(_patch_character(client, character["id"], {"model": _ref(SERVER_HIGH, MODEL_HIGH_FIRST_NAME)}))

    patched = _json(_patch_character(client, character["id"], {"model": None}))

    assert patched["model"] is None
    assert _character_configuration(client, character["id"])["model"] is None
    later = _start(client, character["id"])
    assert _session_configuration(client, later["id"])["model"] == _ref(SERVER_LOW, MODEL_LOW_FIRST_NAME)


# --- DoD-8: not found, and archive is not a lock --------------------------------------

_INTRUDER_SESSION_BODY = {
    "model": _ref(SERVER_LOW, MODEL_LOW_SECOND_NAME),
    "system_prompt": "Intruder",
    "tool_memo_search": False,
    "rp_language": "Klingon",
}
_INTRUDER_CHARACTER_BODY = {
    "model": _ref(SERVER_LOW, MODEL_LOW_SECOND_NAME),
    "system_prompt": "Intruder",
    "tool_memo_search": False,
}


@pytest.mark.parametrize("method", ["GET", "PATCH"])
@pytest.mark.parametrize("whose", ["other-user", "missing"])
def test_a_foreign_or_missing_session_answers_404_and_writes_nothing__S017_005_DoD8(
    application: FastAPI, db_settings: Settings, engine: Engine, method: str, whose: str
) -> None:
    """DoD-8 — R5: another user's or a missing session → 404 `session_not_found`; the owner's row unchanged."""
    _seed_registry(engine)
    owner = _player_a(application, db_settings)
    character = _character(owner, "Aria")
    session = _start(owner, character["id"])
    before_configuration = _session_configuration(owner, session["id"])
    before_session = _read_session(owner, session["id"])
    intruder = _player_b(application, db_settings)
    target = session["id"] if whose == "other-user" else UNKNOWN_SESSION_ID

    if method == "GET":
        response = intruder.get(_session_configuration_path(target))
    else:
        response = _patch_session(intruder, target, _INTRUDER_SESSION_BODY)

    _assert_envelope(response, 404, SESSION_NOT_FOUND)
    assert _session_configuration(owner, session["id"]) == before_configuration
    assert _read_session(owner, session["id"]) == before_session


@pytest.mark.parametrize("method", ["GET", "PATCH"])
@pytest.mark.parametrize("whose", ["other-user", "missing"])
def test_a_foreign_or_missing_character_answers_404_and_writes_nothing__S017_005_DoD8(
    application: FastAPI, db_settings: Settings, engine: Engine, method: str, whose: str
) -> None:
    """DoD-8 — R5: another user's or a missing character → 404 `character_not_found`; nothing written."""
    _seed_registry(engine)
    owner = _player_a(application, db_settings)
    character = _character(owner, "Aria")
    session = _start(owner, character["id"])
    before_character = _character_configuration(owner, character["id"])
    before_session = _session_configuration(owner, session["id"])
    intruder = _player_b(application, db_settings)
    target = character["id"] if whose == "other-user" else UNKNOWN_CHARACTER_ID

    if method == "GET":
        response = intruder.get(_character_configuration_path(target))
    else:
        response = _patch_character(intruder, target, _INTRUDER_CHARACTER_BODY)

    _assert_envelope(response, 404, CHARACTER_NOT_FOUND)
    assert _character_configuration(owner, character["id"]) == before_character
    assert _session_configuration(owner, session["id"]) == before_session


def test_an_archived_session_is_readable_and_writable__S017_005_DoD8(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-8 — R6: archive is not a lock."""
    _seed_registry(engine)
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    session = _start(client, character["id"])
    assert client.post(f"{SESSIONS_PATH}/{session['id']}/archive").status_code == 200

    _session_configuration(client, session["id"])
    patched = _json(
        _patch_session(
            client,
            session["id"],
            {"system_prompt": "Archived but alive", "model": _ref(SERVER_HIGH, MODEL_HIGH_FIRST_NAME)},
        )
    )

    assert patched["system_prompt"] == _setting("Archived but alive", None, None, "Archived but alive", "session")
    assert patched["model"] == _ref(SERVER_HIGH, MODEL_HIGH_FIRST_NAME)
    assert _session_configuration(client, session["id"]) == patched


def test_an_archived_character_is_readable_and_writable__S017_005_DoD8(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-8 — R6: archive is not a lock."""
    _seed_registry(engine)
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    assert client.post(f"{CHARACTERS_PATH}/{character['id']}/archive").status_code == 200

    _character_configuration(client, character["id"])
    patched = _json(
        _patch_character(client, character["id"], {"system_prompt": "Still here", "tool_web_search": False})
    )

    assert patched == {
        "model": None,
        "system_prompt": "Still here",
        "tool_memo_search": None,
        "tool_session_search": None,
        "tool_web_search": False,
    }
    assert _character_configuration(client, character["id"]) == patched


# --- DoD-9: 011's routes unchanged; router registered last ----------------------------


def test_get_session_still_answers_exactly_eight_keys__S017_005_DoD9(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-9 — D9: the `Session` wire shape is untouched, even after a configuration write."""
    _seed_registry(engine)
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    session = _start(client, character["id"])
    _json(_patch_session(client, session["id"], {"system_prompt": "S", "rp_language": "French"}))

    assert set(_read_session(client, session["id"])) == SESSION_KEYS


def test_patch_on_the_session_itself_still_answers_405__S017_005_DoD9(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-9 — D9, D13: 017 adds no route at `/api/sessions/{id}`; the session is unchanged."""
    _seed_registry(engine)
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    session = _start(client, character["id"])
    before = _session_configuration(client, session["id"])

    response = client.patch(_session_path(session["id"]), json={"system_prompt": "S"})

    assert response.status_code == 405, response.text
    assert _session_configuration(client, session["id"]) == before


def test_the_configuration_router_holds_exactly_the_seven_routes__S017_005_DoD9() -> None:
    """DoD-9 — D13: one router with the Wire contract's seven method/path pairs."""
    pairs = {
        (route.path, method)
        for route in configuration_router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }

    assert pairs == CONFIGURATION_ROUTES


def _ordered_api_routes(routes: Any, found: list[APIRoute], seen: set[int]) -> None:
    """Depth-first, registration-order walk of every `APIRoute`, descending into included-router
    wrappers (entries exposing `.routes`, `.router.routes` or `.original_router.routes`) whatever the
    framework's top-level layout."""
    if routes is None or id(routes) in seen:
        return
    seen.add(id(routes))
    for route in routes:
        if isinstance(route, APIRoute):
            if id(route) not in seen:
                seen.add(id(route))
                found.append(route)
            continue
        _ordered_api_routes(getattr(route, "routes", None), found, seen)
        _ordered_api_routes(getattr(getattr(route, "router", None), "routes", None), found, seen)
        _ordered_api_routes(getattr(getattr(route, "original_router", None), "routes", None), found, seen)


def test_the_configuration_router_is_included_last__S017_005_DoD9(application: FastAPI) -> None:
    """DoD-9 — D13: every configuration route follows every other router's route in the app."""
    ordered: list[APIRoute] = []
    _ordered_api_routes(application.routes, ordered, set())
    is_configuration = [
        any((route.path, method) in CONFIGURATION_ROUTES for method in route.methods) for route in ordered
    ]

    assert sum(is_configuration) == len(CONFIGURATION_ROUTES)
    first_configuration = is_configuration.index(True)
    assert all(is_configuration[first_configuration:])
    assert not all(is_configuration)


# --- DoD-10: write bookkeeping --------------------------------------------------------


def test_a_session_configuration_patch_bumps_updated_at_but_not_last_used_at__S017_005_DoD10(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-10 — D11: configuring is not use; `updated_at` advances, `last_used_at` stays."""
    _seed_registry(engine)
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    session = _start(client, character["id"])
    before = _read_session(client, session["id"])
    time.sleep(0.01)

    _json(_patch_session(client, session["id"], {"system_prompt": "S", "tool_memo_search": False}))

    after = _read_session(client, session["id"])
    assert after["last_used_at"] == before["last_used_at"]
    assert after["updated_at"] > before["updated_at"]
