"""Tests for the sessions router: ``/api/sessions...`` and ``/api/characters/{character_id}/sessions``.

Every expected value comes from ``docs/plans/011.rp-sessions/003.sessions-router.md``
(Interface intent + Definition of done), ``003.context.md`` and the feature ``context.md``
(the **Wire contract** table — routes, the eight-key ``Session`` object, the four failure
codes and the native 422 — plus **D2** the body semantics, **D9** the route surface and
router-level auth, **D12** not-found / conflict / validation, **D13** archive semantics,
**D14** the order, **D3** last-use, **D10** ``setup_name``, R2, R5, R6). Bindings come from
``## Skeleton`` in ``status.md`` (steps 001, 002, 003): the six full paths with their status
codes and the optional-body form ``body: StartSessionRequest | None = None``.

Covers step 003 DoD-1 .. DoD-17. DoD-18 is ``[manual/live]`` and carries no test.

The application is always the real factory's (``create_app()``), pinned to the per-test
database through ``dependency_overrides[get_settings]``. Each signed-in caller gets its own
``TestClient`` carrying exactly one session cookie, so no cookie leaks between users.
The FK chain is built through the real routes (feature context, "Test conventions"):
characters through 009's ``POST /api/characters``, setups through 010's
``POST /api/characters/{id}/setups``, a setup archived through
``POST /api/setups/{id}/archive`` and a character through ``POST /api/characters/{id}/archive``.
Every path helper builds an **exact** path (``/api/sessions``, ``/api/sessions/<id>``,
``/api/characters/<id>/sessions`` and ``/api/characters/<id>/setups`` share prefixes).
``conftest.py`` is untouched: every fixture below is file-local.

Extended by feature 034, step 002 (``docs/plans/034.session-names/002.rename-route.md``): the
narrow ``PATCH /api/sessions/{id}`` rename. 011's DoD-13 "PATCH answers 405" clause is
replaced accordingly (a PATCH with a non-``name`` key is now 422). See the section at the end.
"""

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
from app.services.passwords import hash_password
from tests.llm_fakes import FakeClientFactory, fake_factory

CHARACTERS_PATH = "/api/characters"
SETUPS_PATH = "/api/setups"
SESSIONS_PATH = "/api/sessions"
LOGIN_PATH = "/api/auth/login"

TIMESTAMP = "2026-01-01T00:00:00+00:00"

#: The fixed-width timestamp form from ``data-model.md``, cited by the feature context's Wire contract.
TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00$")

PLAYER_A_ID = 9_300_001
PLAYER_A_NAME = "aster"
PLAYER_A_PASSWORD = "a quiet river at dusk"

PLAYER_B_ID = 9_300_002
PLAYER_B_NAME = "briar"
PLAYER_B_PASSWORD = "salt and lantern light"

#: Large decimal id strings no row holds (D12: indistinguishable from another user's id).
UNKNOWN_CHARACTER_ID = "7250000000000000001"
UNKNOWN_SESSION_ID = "7250000000000000002"
UNKNOWN_SETUP_ID = "7250000000000000003"

#: The ``Session`` wire object's keys, from the feature context's Wire contract. Never ``user_id``.
#: Amended by feature 034, step 001 (DoD-2; 034 ``context.md`` "Wire shape of a session"): plus
#: ``name`` — nine keys. The tests' "eight keys" wording below predates the amendment and
#: means exactly ``SESSION_KEYS``.
SESSION_KEYS = {
    "id",
    "character_id",
    "setup_id",
    "setup_name",
    "name",
    "archived_at",
    "last_used_at",
    "created_at",
    "updated_at",
}

#: 018 D3 / Wire contract: the start route answers ``StartedSession`` — the session keys
#: plus ``opening_message``. Every other session route keeps exactly ``SESSION_KEYS``.
STARTED_SESSION_KEYS = SESSION_KEYS | {"opening_message"}

#: 012's eight-key ``Message`` wire shape, cited by 018's Wire contract.
#: Amended by feature 022, step 001 (D3, DoD-4): plus `tool_name`, `tool_status`, `tool_args`
#: — eleven keys.
#: Amended by feature 024, step 005 (DoD-9 regression fallout; ``context.md`` **Wire
#: contract**: the field is always present on the backend wire, and ``false`` wherever the
#: source carries ``StreamMessage``'s default — which the opening message does): plus
#: ``search_coverage_incomplete`` — twelve keys. Scope here is this key set alone; the flag's
#: behaviour is covered in ``test_record_keeping_embedding.py``.
MESSAGE_KEYS = {
    "id",
    "session_id",
    "role",
    "kind",
    "text",
    "settled_at",
    "created_at",
    "updated_at",
    "tool_name",
    "tool_status",
    "tool_args",
    "search_coverage_incomplete",
}

NOT_AUTHENTICATED = "not_authenticated"
CHARACTER_NOT_FOUND = "character_not_found"
SETUP_NOT_FOUND = "setup_not_found"
SETUP_ARCHIVED = "setup_archived"
SESSION_NOT_FOUND = "session_not_found"

#: Sentinel distinguishing "send no body at all" from "send this JSON body" (D2, DoD-2).
_OMITTED: Any = object()


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
    _insert_user(
        engine, user_id=PLAYER_A_ID, username=PLAYER_A_NAME, password=PLAYER_A_PASSWORD, role=Role.ROLEPLAYER
    )
    _insert_user(
        engine, user_id=PLAYER_B_ID, username=PLAYER_B_NAME, password=PLAYER_B_PASSWORD, role=Role.ROLEPLAYER
    )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database with the registry applied and the two roleplayers seeded."""
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


# --- exact paths ---------------------------------------------------------------------


def _character_path(character_id: Any) -> str:
    return f"{CHARACTERS_PATH}/{character_id}"


def _character_action_path(character_id: Any, action: str) -> str:
    return f"{CHARACTERS_PATH}/{character_id}/{action}"


def _character_setups_path(character_id: Any) -> str:
    return f"{CHARACTERS_PATH}/{character_id}/setups"


def _setup_action_path(setup_id: Any, action: str) -> str:
    return f"{SETUPS_PATH}/{setup_id}/{action}"


def _character_sessions_path(character_id: Any) -> str:
    return f"{CHARACTERS_PATH}/{character_id}/sessions"


def _session_path(session_id: Any) -> str:
    return f"{SESSIONS_PATH}/{session_id}"


def _session_action_path(session_id: Any, action: str) -> str:
    return f"{SESSIONS_PATH}/{session_id}/{action}"


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


# --- request / assertion helpers -----------------------------------------------------


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
    """009's create route: the parent row every session needs (feature context, Test conventions)."""
    response = client.post(CHARACTERS_PATH, json={"name": name, "sheet": ""})
    assert response.status_code == 201, response.text
    created = response.json()
    assert isinstance(created, dict)
    return created


def _create_setup(client: TestClient, character_id: Any, name: str, description: str = "") -> dict[str, Any]:
    """010's create route: the setup a session may be started with."""
    response = client.post(_character_setups_path(character_id), json={"name": name, "description": description})
    assert response.status_code == 201, response.text
    created = response.json()
    assert isinstance(created, dict)
    return created


def _archive_setup(client: TestClient, setup_id: Any) -> dict[str, Any]:
    """010's archive route, used only as seeding (DoD-5, DoD-15)."""
    response = client.post(_setup_action_path(setup_id, "archive"))
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def _archive_character(client: TestClient, character_id: Any) -> dict[str, Any]:
    """009's archive route, used only as seeding (DoD-14)."""
    response = client.post(_character_action_path(character_id, "archive"))
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def _start_request(client: TestClient, character_id: Any, body: Any = _OMITTED) -> httpx.Response:
    """POST the start route. ``_OMITTED`` sends **no body at all** (D2's third shape)."""
    path = _character_sessions_path(character_id)
    if body is _OMITTED:
        return client.post(path)
    return client.post(path, json=body)


def _start_started(client: TestClient, character_id: Any, body: Any = _OMITTED) -> dict[str, Any]:
    """The start route's whole 201 answer: a ``StartedSession`` (018 D3)."""
    response = _start_request(client, character_id, body)
    assert response.status_code == 201, response.text
    created = response.json()
    assert isinstance(created, dict)
    assert set(created) == STARTED_SESSION_KEYS
    return created


def _start(client: TestClient, character_id: Any, body: Any = _OMITTED) -> dict[str, Any]:
    """Start a session and return its eight ``Session`` keys.

    Amended by 018 step 002 DoD-8: the start answer carries the eight session keys plus
    ``opening_message`` (checked exactly here); the session part is what 011's callers compare
    against the eight-key reads, listings, archive and restore answers."""
    started = _start_started(client, character_id, body)
    return {key: started[key] for key in SESSION_KEYS}


def _sessions_of(response: httpx.Response) -> list[dict[str, Any]]:
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"sessions"}
    rows = body["sessions"]
    assert isinstance(rows, list)
    return rows


def _query(include_archived: bool | None) -> dict[str, str]:
    return {} if include_archived is None else {"include_archived": str(include_archived).lower()}


def _all_sessions(client: TestClient, *, include_archived: bool | None = None) -> list[dict[str, Any]]:
    """``GET /api/sessions`` — the exact collection path, never a prefix."""
    return _sessions_of(client.get(SESSIONS_PATH, params=_query(include_archived)))


def _character_sessions(
    client: TestClient, character_id: Any, *, include_archived: bool | None = None
) -> list[dict[str, Any]]:
    """``GET /api/characters/<id>/sessions`` — the exact child-collection path."""
    return _sessions_of(client.get(_character_sessions_path(character_id), params=_query(include_archived)))


def _read_session(client: TestClient, session_id: Any) -> dict[str, Any]:
    response = client.get(_session_path(session_id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def _archive_session(client: TestClient, session_id: Any) -> httpx.Response:
    return client.post(_session_action_path(session_id, "archive"))


def _restore_session(client: TestClient, session_id: Any) -> httpx.Response:
    return client.post(_session_action_path(session_id, "restore"))


def _ids(rows: list[dict[str, Any]]) -> list[str]:
    return [row["id"] for row in rows]


def _assert_wire_shape(session: dict[str, Any]) -> None:
    """The ``Session`` wire object of the feature context's Wire contract."""
    assert set(session) == SESSION_KEYS
    assert isinstance(session["id"], str)
    assert session["id"].isdigit()
    assert isinstance(session["character_id"], str)
    assert session["character_id"].isdigit()
    assert session["setup_id"] is None or (isinstance(session["setup_id"], str) and session["setup_id"].isdigit())
    assert session["setup_name"] is None or isinstance(session["setup_name"], str)
    # 034/001 DoD-2 — `name` is a string, or null when never renamed.
    assert session["name"] is None or isinstance(session["name"], str)
    assert session["archived_at"] is None or TIMESTAMP_PATTERN.match(session["archived_at"]) is not None
    assert TIMESTAMP_PATTERN.match(session["last_used_at"]) is not None
    assert TIMESTAMP_PATTERN.match(session["created_at"]) is not None
    assert TIMESTAMP_PATTERN.match(session["updated_at"]) is not None


def _assert_started_wire_shape(started: dict[str, Any]) -> None:
    """The start route's answer (018 step 002 DoD-8 amends 011's exact-keys check for this
    route only): exactly the eight session keys plus ``opening_message``, the session part
    being 011's ``Session`` wire object."""
    assert set(started) == STARTED_SESSION_KEYS
    _assert_wire_shape({key: started[key] for key in SESSION_KEYS})


def _foreign_collection_request(client: TestClient, method: str, character_id: Any) -> httpx.Response:
    if method == "GET":
        return client.get(_character_sessions_path(character_id))
    return _start_request(client, character_id, {})


def _foreign_session_request(client: TestClient, method: str, session_id: Any) -> httpx.Response:
    if method == "GET":
        return client.get(_session_path(session_id))
    return client.post(_session_action_path(session_id, method))


# --- DoD-1: router-level auth ---------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "send_body"),
    [
        ("GET", SESSIONS_PATH, False),
        ("GET", _character_sessions_path(UNKNOWN_CHARACTER_ID), False),
        ("POST", _character_sessions_path(UNKNOWN_CHARACTER_ID), True),
        ("GET", _session_path(UNKNOWN_SESSION_ID), False),
        ("POST", _session_action_path(UNKNOWN_SESSION_ID, "archive"), False),
        ("POST", _session_action_path(UNKNOWN_SESSION_ID, "restore"), False),
    ],
    ids=["list-all", "list-character", "start", "read", "archive", "restore"],
)
def test_every_route_answers_401_without_a_session__S011_003_DoD1(
    application: FastAPI, method: str, path: str, send_body: bool
) -> None:
    """DoD-1 — D9: `require_user` sits on the router, so all six routes refuse anonymously."""
    client = _anonymous(application)

    response = client.request(method, path, json={} if send_body else None)

    _assert_envelope(response, 401, NOT_AUTHENTICATED)


# --- DoD-2: start with no setup, then read and list -----------------------------------


def test_starting_with_an_empty_body_answers_201_with_no_setup__S011_003_DoD2__S018_002_DoD8(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — US-026.AC-1, US-024.AC-1, R2: 201, ids as decimal strings, no setup, last use == creation.

    Amended by 018 step 002 DoD-8: the answer's exact keys are the eight plus `opening_message`."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")

    response = _start_request(client, character["id"], {})

    assert response.status_code == 201, response.text
    created = response.json()
    _assert_started_wire_shape(created)
    assert created["character_id"] == character["id"]
    assert created["setup_id"] is None
    assert created["setup_name"] is None
    assert created["archived_at"] is None
    assert created["last_used_at"] == created["created_at"]


def test_a_started_session_reads_by_id_and_appears_in_both_listings__S011_003_DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — US-026.AC-1: `GET /api/sessions/<id>` answers it and both listings hold its id."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    created = _start(client, character["id"], {})

    assert _read_session(client, created["id"]) == created
    assert created["id"] in _ids(_all_sessions(client))
    assert created["id"] in _ids(_character_sessions(client, character["id"]))


@pytest.mark.parametrize("body", [_OMITTED, {}, {"setup_id": None}], ids=["no-body", "empty-object", "explicit-null"])
def test_all_three_no_setup_request_shapes_answer_201__S011_003_DoD2__S018_002_DoD8(
    application: FastAPI, db_settings: Settings, body: Any
) -> None:
    """DoD-2 — D2, US-024.AC-3, R2: no body, `{}` and `{"setup_id": null}` all start a session with none.

    Amended by 018 step 002 DoD-8: the answer's exact keys are the eight plus `opening_message`."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")

    response = _start_request(client, character["id"], body)

    assert response.status_code == 201, response.text
    created = response.json()
    _assert_started_wire_shape(created)
    assert created["setup_id"] is None
    assert created["setup_name"] is None
    assert created["character_id"] == character["id"]
    assert created["last_used_at"] == created["created_at"]


# --- DoD-3: start with a setup, and one setup backing two sessions --------------------


def test_starting_with_a_setup_answers_its_id_and_name__S011_003_DoD3__S018_002_DoD8(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-3 — US-025.AC-1, D10: the chosen setup comes back as `setup_id` plus its current name.

    Amended by 018 step 002 DoD-8: the answer's exact keys are the eight plus `opening_message`."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    setup = _create_setup(client, character["id"], "Tavern", "# Night")

    response = _start_request(client, character["id"], {"setup_id": setup["id"]})

    assert response.status_code == 201, response.text
    created = response.json()
    _assert_started_wire_shape(created)
    assert created["setup_id"] == setup["id"]
    assert created["setup_name"] == setup["name"]


def test_one_setup_backs_two_sessions__S011_003_DoD3(application: FastAPI, db_settings: Settings) -> None:
    """DoD-3 — UC-022: a second session with the same setup is allowed and both list with it."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    setup = _create_setup(client, character["id"], "Tavern", "# Night")

    first = _start(client, character["id"], {"setup_id": setup["id"]})
    second = _start(client, character["id"], {"setup_id": setup["id"]})

    assert first["id"] != second["id"]
    rows = _character_sessions(client, character["id"])
    assert {first["id"], second["id"]} <= set(_ids(rows))
    for row in rows:
        if row["id"] in {first["id"], second["id"]}:
            assert row["setup_id"] == setup["id"]
            assert row["setup_name"] == setup["name"]


# --- DoD-4: a setup that is not choosable under this character ------------------------


def _unchoosable_setup_ids(
    application: FastAPI, settings: Settings
) -> tuple[TestClient, dict[str, Any], dict[str, str]]:
    """Seed A's character C plus the three ids DoD-4 names, and return them by case."""
    owner = _player_a(application, settings)
    character = _character(owner, "Aria")
    other_character = _character(owner, "Bramble")
    own_elsewhere = _create_setup(owner, other_character["id"], "Elsewhere", "# Far")
    intruder = _player_b(application, settings)
    their_character = _character(intruder, "Cinder")
    their_setup = _create_setup(intruder, their_character["id"], "Theirs", "# Mine")
    return (
        owner,
        character,
        {
            "other_character": own_elsewhere["id"],
            "other_user": their_setup["id"],
            "nobody": UNKNOWN_SETUP_ID,
        },
    )


@pytest.mark.parametrize("case", ["other_character", "other_user", "nobody"])
def test_an_unchoosable_setup_answers_404_setup_not_found__S011_003_DoD4(
    application: FastAPI, db_settings: Settings, case: str
) -> None:
    """DoD-4 — D12, R5: a setup not the caller's under that character answers 404 `setup_not_found`."""
    owner, character, setup_ids = _unchoosable_setup_ids(application, db_settings)
    _start(owner, character["id"], {})
    before = _character_sessions(owner, character["id"], include_archived=True)

    response = _start_request(owner, character["id"], {"setup_id": setup_ids[case]})

    body = _assert_envelope(response, 404, SETUP_NOT_FOUND)
    assert body["error"]["detail"] == {}
    assert _character_sessions(owner, character["id"], include_archived=True) == before


@pytest.mark.parametrize("case", ["other_character", "other_user"])
def test_an_unchoosable_setup_is_indistinguishable_from_an_unknown_one__S011_003_DoD4(
    application: FastAPI, db_settings: Settings, case: str
) -> None:
    """DoD-4 — R5, D12: another user's (or another character's) setup answers the same body as nobody's."""
    owner, character, setup_ids = _unchoosable_setup_ids(application, db_settings)

    refused = _start_request(owner, character["id"], {"setup_id": setup_ids[case]})
    unknown = _start_request(owner, character["id"], {"setup_id": setup_ids["nobody"]})

    assert refused.status_code == unknown.status_code == 404
    assert refused.json() == unknown.json()


# --- DoD-5: an archived setup conflicts ----------------------------------------------


def test_an_archived_setup_answers_409_setup_archived__S011_003_DoD5(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-5 — D2, D12: the caller owns it, so it is a 409 conflict, not a 404, and nothing is created."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    setup = _create_setup(client, character["id"], "Tavern", "# Night")
    _start(client, character["id"], {})
    _archive_setup(client, setup["id"])
    before = _character_sessions(client, character["id"], include_archived=True)

    response = _start_request(client, character["id"], {"setup_id": setup["id"]})

    body = _assert_envelope(response, 409, SETUP_ARCHIVED)
    assert body["error"]["detail"] == {}
    assert _character_sessions(client, character["id"], include_archived=True) == before


# --- DoD-6: another user's (or nobody's) parent character ----------------------------


@pytest.mark.parametrize("method", ["GET", "POST"], ids=["list", "start"])
def test_a_foreign_parent_character_answers_404_character_not_found__S011_003_DoD6(
    application: FastAPI, db_settings: Settings, method: str
) -> None:
    """DoD-6 — R5, D12: a character that is not the caller's answers 404 `character_not_found`."""
    owner = _player_a(application, db_settings)
    character = _character(owner, "Aria")
    intruder = _player_b(application, db_settings)

    response = _foreign_collection_request(intruder, method, character["id"])

    body = _assert_envelope(response, 404, CHARACTER_NOT_FOUND)
    assert body["error"]["detail"] == {}


@pytest.mark.parametrize("method", ["GET", "POST"], ids=["list", "start"])
def test_a_foreign_parent_is_indistinguishable_from_an_unknown_one__S011_003_DoD6(
    application: FastAPI, db_settings: Settings, method: str
) -> None:
    """DoD-6 — R5, D12: another user's character id and an id that exists for nobody answer the same body."""
    owner = _player_a(application, db_settings)
    character = _character(owner, "Aria")
    intruder = _player_b(application, db_settings)

    foreign = _foreign_collection_request(intruder, method, character["id"])
    unknown = _foreign_collection_request(intruder, method, UNKNOWN_CHARACTER_ID)

    assert foreign.status_code == unknown.status_code == 404
    assert foreign.json() == unknown.json()


def test_a_refused_start_leaves_the_owners_listing_unchanged__S011_003_DoD6(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-6 — R5: A's listing holds no session created by B."""
    owner = _player_a(application, db_settings)
    character = _character(owner, "Aria")
    _start(owner, character["id"], {})
    before = _character_sessions(owner, character["id"], include_archived=True)
    intruder = _player_b(application, db_settings)

    assert _foreign_collection_request(intruder, "POST", character["id"]).status_code == 404

    assert _character_sessions(owner, character["id"], include_archived=True) == before
    assert _all_sessions(owner, include_archived=True) == before


# --- DoD-7: another user's (or nobody's) session --------------------------------------


@pytest.mark.parametrize("method", ["GET", "archive", "restore"])
def test_a_foreign_session_answers_404_session_not_found__S011_003_DoD7(
    application: FastAPI, db_settings: Settings, method: str
) -> None:
    """DoD-7 — US-029.AC-1, R5, D12: another user's session answers 404 `session_not_found`, untouched."""
    owner = _player_a(application, db_settings)
    character = _character(owner, "Aria")
    created = _start(owner, character["id"], {})
    intruder = _player_b(application, db_settings)

    response = _foreign_session_request(intruder, method, created["id"])

    body = _assert_envelope(response, 404, SESSION_NOT_FOUND)
    assert body["error"]["detail"] == {}
    assert _read_session(owner, created["id"]) == created


@pytest.mark.parametrize("method", ["GET", "archive", "restore"])
def test_a_foreign_session_is_indistinguishable_from_an_unknown_one__S011_003_DoD7(
    application: FastAPI, db_settings: Settings, method: str
) -> None:
    """DoD-7 — R5, D12: another user's session id and an id that exists for nobody answer the same body."""
    owner = _player_a(application, db_settings)
    character = _character(owner, "Aria")
    created = _start(owner, character["id"], {})
    intruder = _player_b(application, db_settings)

    foreign = _foreign_session_request(intruder, method, created["id"])
    unknown = _foreign_session_request(intruder, method, UNKNOWN_SESSION_ID)

    assert foreign.status_code == unknown.status_code == 404
    assert foreign.json() == unknown.json()


# --- DoD-8: the listings carry only the caller's (and only that character's) ----------


@pytest.mark.parametrize("include_archived", [None, True], ids=["default", "include_archived"])
def test_the_all_sessions_listing_carries_only_the_callers__S011_003_DoD8(
    application: FastAPI, db_settings: Settings, include_archived: bool | None
) -> None:
    """DoD-8 — US-029.AC-1, R5: A's two characters' sessions and never B's, with or without the flag."""
    owner = _player_a(application, db_settings)
    first = _character(owner, "Aria")
    second = _character(owner, "Bramble")
    own_first = _start(owner, first["id"], {})
    own_second = _start(owner, second["id"], {})
    own_archived = _start(owner, first["id"], {})
    assert _archive_session(owner, own_archived["id"]).status_code == 200
    intruder = _player_b(application, db_settings)
    their_character = _character(intruder, "Cinder")
    theirs = _start(intruder, their_character["id"], {})

    rows = _all_sessions(owner, include_archived=include_archived)

    expected = {own_first["id"], own_second["id"]}
    if include_archived:
        expected |= {own_archived["id"]}
    assert set(_ids(rows)) == expected
    assert theirs["id"] not in _ids(rows)
    assert set(_ids(_all_sessions(intruder, include_archived=include_archived))) == {theirs["id"]}


@pytest.mark.parametrize("include_archived", [None, True], ids=["default", "include_archived"])
def test_each_per_character_listing_carries_only_that_characters__S011_003_DoD8(
    application: FastAPI, db_settings: Settings, include_archived: bool | None
) -> None:
    """DoD-8 — US-029.AC-1, R5: the child collection is scoped to its own character."""
    owner = _player_a(application, db_settings)
    first = _character(owner, "Aria")
    second = _character(owner, "Bramble")
    under_first = _start(owner, first["id"], {})
    under_second = _start(owner, second["id"], {})
    intruder = _player_b(application, db_settings)
    their_character = _character(intruder, "Cinder")
    theirs = _start(intruder, their_character["id"], {})

    rows = _character_sessions(owner, first["id"], include_archived=include_archived)

    assert set(_ids(rows)) == {under_first["id"]}
    assert under_second["id"] not in _ids(rows)
    assert theirs["id"] not in _ids(rows)


# --- DoD-9: archive ------------------------------------------------------------------


def test_archive_answers_200_and_moves_the_session_out_of_both_working_lists__S011_003_DoD9(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-9 — US-027.AC-1, R6, D13: archived leaves both default listings, stays readable with the flag."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    created = _start(client, character["id"], {})

    response = _archive_session(client, created["id"])

    assert response.status_code == 200, response.text
    archived = response.json()
    _assert_wire_shape(archived)
    assert isinstance(archived["archived_at"], str)
    assert archived["id"] == created["id"]
    assert created["id"] not in _ids(_all_sessions(client))
    assert created["id"] not in _ids(_character_sessions(client, character["id"]))
    assert created["id"] in _ids(_all_sessions(client, include_archived=True))
    assert created["id"] in _ids(_character_sessions(client, character["id"], include_archived=True))
    assert _read_session(client, created["id"])["id"] == created["id"]


def test_archiving_twice_keeps_the_original_archived_at_and_last_use__S011_003_DoD9(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-9 — D13, D3: archive is idempotent and never bumps `last_used_at`."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    created = _start(client, character["id"], {})

    first = _archive_session(client, created["id"])
    assert first.status_code == 200, first.text
    second = _archive_session(client, created["id"])

    assert second.status_code == 200, second.text
    assert second.json()["archived_at"] == first.json()["archived_at"]
    assert first.json()["last_used_at"] == created["last_used_at"]
    assert second.json()["last_used_at"] == created["last_used_at"]


# --- DoD-10: restore -----------------------------------------------------------------


def test_restore_brings_the_session_back_field_for_field__S011_003_DoD10(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-10 — US-027.AC-2, US-027.AC-3 (the row half): restored is `archived_at` null and unchanged."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    setup = _create_setup(client, character["id"], "Tavern", "# Night")
    created = _start(client, character["id"], {"setup_id": setup["id"]})
    assert _archive_session(client, created["id"]).status_code == 200

    response = _restore_session(client, created["id"])

    assert response.status_code == 200, response.text
    restored = response.json()
    _assert_wire_shape(restored)
    assert restored["archived_at"] is None
    assert created["id"] in _ids(_all_sessions(client))
    assert created["id"] in _ids(_character_sessions(client, character["id"]))
    read_back = _read_session(client, created["id"])
    preserved = ("id", "character_id", "setup_id", "setup_name", "created_at", "last_used_at")
    assert {key: read_back[key] for key in preserved} == {key: created[key] for key in preserved}


# --- DoD-11: order is newest use first -----------------------------------------------


def test_three_sessions_under_one_character_come_back_newest_first__S011_003_DoD11(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-11 — US-028.AC-1, D14, D3: with no content writes, last use equals start order."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    first = _start(client, character["id"], {})
    second = _start(client, character["id"], {})
    third = _start(client, character["id"], {})

    expected = [third["id"], second["id"], first["id"]]
    assert _ids(_character_sessions(client, character["id"])) == expected
    assert _ids(_all_sessions(client)) == expected


def test_the_all_sessions_order_ignores_the_character__S011_003_DoD11(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-11 — US-028.AC-1, D14: sessions started alternately under two characters interleave by last use."""
    client = _player_a(application, db_settings)
    first_character = _character(client, "Aria")
    second_character = _character(client, "Bramble")
    started = [
        _start(client, first_character["id"], {}),
        _start(client, second_character["id"], {}),
        _start(client, first_character["id"], {}),
        _start(client, second_character["id"], {}),
    ]

    assert _ids(_all_sessions(client)) == [row["id"] for row in reversed(started)]


# --- DoD-12: reading never writes ----------------------------------------------------


def test_reading_a_session_twice_bumps_nothing__S011_003_DoD12(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-12 — D3: `GET /api/sessions/<id>` is a pure read; there is no touch route."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    created = _start(client, character["id"], {})

    first = _read_session(client, created["id"])
    second = _read_session(client, created["id"])

    assert first["last_used_at"] == second["last_used_at"] == created["last_used_at"]
    assert first["updated_at"] == second["updated_at"] == created["updated_at"]


# --- DoD-13: no delete (and, since 034/002, only the narrow rename edit) ---------------


def test_delete_answers_405_and_the_session_survives__S011_003_DoD13__S034_002_DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-13 — R6, D9: no delete route exists; status only.

    Amended by feature 034, step 002: `PATCH /api/sessions/{id}` now exists as the narrow
    rename (DEC-arch-session-names-2), so the old "PATCH answers 405" clause no longer holds.
    A PATCH carrying any key other than `name` (here 011's `setup_id`) answers 422 and
    changes nothing (034/002 DoD-4)."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    created = _start(client, character["id"], {})

    assert client.delete(_session_path(created["id"])).status_code == 405
    assert client.delete(SESSIONS_PATH).status_code == 405
    assert client.delete(_character_sessions_path(character["id"])).status_code == 405
    assert client.patch(_session_path(created["id"]), json={"setup_id": None}).status_code == 422

    assert _read_session(client, created["id"]) == created


# --- DoD-14: an archived character still hosts sessions ------------------------------


def test_an_archived_character_still_lists_and_starts_sessions__S011_003_DoD14(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-14 — D2: archive does not cascade and nothing forbids starting under an archived character."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    existing = _start(client, character["id"], {})
    _archive_character(client, character["id"])

    listing = client.get(_character_sessions_path(character["id"]))
    started = _start_request(client, character["id"], {})

    assert listing.status_code == 200, listing.text
    assert started.status_code == 201, started.text
    assert client.get(_session_path(existing["id"])).status_code == 200
    assert existing["id"] in _ids(_character_sessions(client, character["id"]))


# --- DoD-15: an archived setup keeps labelling its sessions --------------------------


def test_an_archived_setup_still_labels_its_sessions__S011_003_DoD15(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-15 — D10, 010 D3: `setup_name` is joined at read time and shown even when archived."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    setup = _create_setup(client, character["id"], "Tavern", "# Night")
    created = _start(client, character["id"], {"setup_id": setup["id"]})

    _archive_setup(client, setup["id"])

    read_back = _read_session(client, created["id"])
    assert read_back["setup_id"] == setup["id"]
    assert read_back["setup_name"] == setup["name"]
    for rows in (_all_sessions(client), _character_sessions(client, character["id"])):
        matched = [row for row in rows if row["id"] == created["id"]]
        assert len(matched) == 1
        assert matched[0]["setup_id"] == setup["id"]
        assert matched[0]["setup_name"] == setup["name"]


# --- DoD-16: native 422 --------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", f"{SESSIONS_PATH}/abc"),
        ("POST", f"{SESSIONS_PATH}/abc/archive"),
        ("POST", f"{SESSIONS_PATH}/abc/restore"),
        ("GET", f"{CHARACTERS_PATH}/abc/sessions"),
        ("POST", f"{CHARACTERS_PATH}/abc/sessions"),
    ],
    ids=["read", "archive", "restore", "list-character", "start"],
)
def test_a_non_numeric_path_id_answers_422__S011_003_DoD16(
    application: FastAPI, db_settings: Settings, method: str, path: str
) -> None:
    """DoD-16 — the Wire contract: a non-numeric path id is FastAPI's native 422, not a domain code."""
    client = _player_a(application, db_settings)

    response = client.request(method, path, json={} if method == "POST" else None)

    assert response.status_code == 422, response.text


def test_a_non_numeric_setup_id_answers_422__S011_003_DoD16(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-16 — the Wire contract: a non-numeric `setup_id` in the body is a native 422."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    before = _character_sessions(client, character["id"], include_archived=True)

    response = _start_request(client, character["id"], {"setup_id": "abc"})

    assert response.status_code == 422, response.text
    assert _character_sessions(client, character["id"], include_archived=True) == before


# --- DoD-17: registration order ------------------------------------------------------


def test_009_and_010_routes_still_answer_with_this_router_registered__S011_003_DoD17(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-17 — D9: registering after setups keeps 009's and 010's paths matching first."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    _create_setup(client, character["id"], "Tavern", "# Night")

    assert client.get(_character_path(character["id"])).status_code == 200
    assert client.get(_character_setups_path(character["id"])).status_code == 200
    assert client.post(_character_action_path(character["id"], "archive")).status_code == 200


# =====================================================================================
# Feature 018, step 002 — the start route creates and seeds in one request.
#
# Expected values come from `docs/plans/018.character-page/002.create-and-seed-route.md`
# (DoD-6 .. DoD-9) and the feature `context.md`'s Wire contract (201 `StartedSession`: the
# eight session keys plus `opening_message`, 012's eight-key `Message` or null; a present
# `opening_message` must be non-blank, else 422 and nothing is created; 011's failures
# unchanged; "a refusal creates nothing"). The zone and entries are read back through 012's
# `GET /api/sessions/{id}/zone` and `/entries`. Test names end `__S018_002_DoD<n>`.
# =====================================================================================

OPENING_TEXT = "Hello there"


def _zone_path(session_id: Any) -> str:
    return f"{SESSIONS_PATH}/{session_id}/zone"


def _entries_path(session_id: Any) -> str:
    return f"{SESSIONS_PATH}/{session_id}/entries"


def _zone(client: TestClient, session_id: Any) -> Any:
    response = client.get(_zone_path(session_id))
    assert response.status_code == 200, response.text
    return response.json()


def _entries(client: TestClient, session_id: Any) -> Any:
    response = client.get(_entries_path(session_id))
    assert response.status_code == 200, response.text
    return response.json()


def _count_rows(engine: Engine, table: Any) -> int:
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(table)).scalar_one())


def _assert_message_wire_shape(message: Any) -> None:
    """012's `Message`: exactly eleven keys (022 001 DoD-4), ids as decimal strings."""
    assert isinstance(message, dict)
    assert set(message) == MESSAGE_KEYS
    assert isinstance(message["id"], str)
    assert message["id"].isdigit()
    assert isinstance(message["session_id"], str)
    assert message["session_id"].isdigit()


# --- DoD-6: the opening message arrives as a current-zone row --------------------------


def test_starting_with_an_opening_message_answers_the_started_session__S018_002_DoD6__S022_001_DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-6 — US-117.AC-1/AC-2, R11: 201, the eight session keys plus `opening_message`, a
    current-zone user message of the new session with the text verbatim."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")

    response = _start_request(client, character["id"], {"opening_message": OPENING_TEXT})

    assert response.status_code == 201, response.text
    started = response.json()
    _assert_started_wire_shape(started)
    assert started["character_id"] == character["id"]
    message = started["opening_message"]
    _assert_message_wire_shape(message)
    assert message["session_id"] == started["id"]
    assert message["role"] == "user"
    assert message["kind"] is None
    assert message["settled_at"] is None
    assert message["text"] == OPENING_TEXT


def test_the_opening_message_is_the_zone_and_the_entries_stay_empty__S018_002_DoD6(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-6 — US-117.AC-2, R11: `GET …/zone` lists exactly that message; `GET …/entries` is
    empty (nothing settled is created)."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    started = _start_started(client, character["id"], {"opening_message": OPENING_TEXT})

    assert _zone(client, started["id"]) == {"messages": [started["opening_message"]]}
    assert _entries(client, started["id"]) == {"entries": []}


# --- DoD-7: a blank opening message, and a foreign character ----------------------------


@pytest.mark.parametrize("blank", ["   ", ""], ids=["whitespace-only", "empty"])
def test_a_blank_opening_message_answers_422_and_creates_nothing__S018_002_DoD7(
    application: FastAPI, db_settings: Settings, engine: Engine, blank: str
) -> None:
    """DoD-7 — Wire contract: a present `opening_message` must be non-blank; 422, and the
    character's session listing is unchanged (no session row, no message row)."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    _start(client, character["id"], {})
    before = _character_sessions(client, character["id"], include_archived=True)
    messages_before = _count_rows(engine, schema.messages)

    response = _start_request(client, character["id"], {"opening_message": blank})

    assert response.status_code == 422, response.text
    assert _character_sessions(client, character["id"], include_archived=True) == before
    assert _count_rows(engine, schema.messages) == messages_before


def test_another_users_character_answers_404_with_an_opening_message__S018_002_DoD7(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-7 — R5: player B posting a valid `opening_message` to A's character answers 404
    `character_not_found`, and A's session listing is unchanged (nothing created)."""
    owner = _player_a(application, db_settings)
    character = _character(owner, "Aria")
    _start(owner, character["id"], {})
    before = _character_sessions(owner, character["id"], include_archived=True)
    sessions_before = _count_rows(engine, schema.sessions)
    messages_before = _count_rows(engine, schema.messages)
    intruder = _player_b(application, db_settings)

    response = _start_request(intruder, character["id"], {"opening_message": OPENING_TEXT})

    _assert_envelope(response, 404, CHARACTER_NOT_FOUND)
    assert _character_sessions(owner, character["id"], include_archived=True) == before
    assert _count_rows(engine, schema.sessions) == sessions_before
    assert _count_rows(engine, schema.messages) == messages_before


# --- DoD-8: no opening message is 011's start, answering `opening_message: null` --------


@pytest.mark.parametrize("body", [_OMITTED, {}], ids=["no-body", "empty-object"])
def test_a_start_without_an_opening_message_answers_null_and_an_empty_zone__S018_002_DoD8(
    application: FastAPI, db_settings: Settings, body: Any
) -> None:
    """DoD-8 — 011 D2, 018 D3: the session is created as 011 built it (no setup, last use ==
    creation), the answer's `opening_message` is null, and the new zone is empty."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")

    response = _start_request(client, character["id"], body)

    assert response.status_code == 201, response.text
    started = response.json()
    _assert_started_wire_shape(started)
    assert started["opening_message"] is None
    assert started["character_id"] == character["id"]
    assert started["setup_id"] is None
    assert started["setup_name"] is None
    assert started["last_used_at"] == started["created_at"]
    assert _zone(client, started["id"]) == {"messages": []}
    assert started["id"] in _ids(_character_sessions(client, character["id"]))


def test_a_start_with_a_working_setup_and_no_opening_message_answers_null__S018_002_DoD8(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-8 — 011 D2: `{"setup_id": <A's working setup>}` starts with that setup, answers
    `opening_message: null`, and the new zone is empty."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    setup = _create_setup(client, character["id"], "Tavern", "# Night")

    response = _start_request(client, character["id"], {"setup_id": setup["id"]})

    assert response.status_code == 201, response.text
    started = response.json()
    _assert_started_wire_shape(started)
    assert started["opening_message"] is None
    assert started["setup_id"] == setup["id"]
    assert started["setup_name"] == setup["name"]
    assert _zone(client, started["id"]) == {"messages": []}


def test_every_other_session_route_still_answers_exactly_eight_keys__S018_002_DoD8(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-8 — the amendment is for the start route only: read, both listings, archive and
    restore keep exactly the eight `Session` keys, even for a session started with an
    opening message."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    started = _start_started(client, character["id"], {"opening_message": OPENING_TEXT})
    session_id = started["id"]

    assert set(_read_session(client, session_id)) == SESSION_KEYS
    for row in _all_sessions(client) + _character_sessions(client, character["id"]):
        assert set(row) == SESSION_KEYS
    archived = _archive_session(client, session_id)
    assert archived.status_code == 200, archived.text
    assert set(archived.json()) == SESSION_KEYS
    restored = _restore_session(client, session_id)
    assert restored.status_code == 200, restored.text
    assert set(restored.json()) == SESSION_KEYS


# --- DoD-9: an archived setup refuses, and the refusal creates nothing ------------------


def test_an_archived_setup_with_an_opening_message_answers_409_and_creates_nothing__S018_002_DoD9(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-9 — 011 D12: `{"setup_id": <A's archived setup>, "opening_message": "Hi"}` answers
    409 `setup_archived`; no session and no message is created."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    setup = _create_setup(client, character["id"], "Tavern", "# Night")
    _archive_setup(client, setup["id"])
    before = _character_sessions(client, character["id"], include_archived=True)
    sessions_before = _count_rows(engine, schema.sessions)
    messages_before = _count_rows(engine, schema.messages)

    response = _start_request(client, character["id"], {"setup_id": setup["id"], "opening_message": "Hi"})

    _assert_envelope(response, 409, SETUP_ARCHIVED)
    assert _character_sessions(client, character["id"], include_archived=True) == before
    assert _count_rows(engine, schema.sessions) == sessions_before
    assert _count_rows(engine, schema.messages) == messages_before


# =====================================================================================
# Feature 034, step 001 — every session payload carries `name`.
#
# Expected values come from `docs/plans/034.session-names/001.session-name-column.md`
# (DoD-2, DoD-3, DoD-4) and the feature `context.md` ("Wire shape of a session": `name` is a
# string, or null when never renamed; the server never computes a default label). US-150.AC-1,
# US-150.AC-6. A stored name is written straight into `sessions.name` in test setup — there is
# no rename route in this step. Test names end `__S034_001_DoD<n>`.
# =====================================================================================

#: A stored session name with non-ASCII text, so an exact-value read-back is meaningful.
STORED_SESSION_NAME = "Le phare — chapitre deux"


def _store_session_name(engine: Engine, session_id: str, name: str | None) -> None:
    """Write `sessions.name` directly (DoD-4: "written directly in test setup")."""
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.update().where(schema.sessions.c.id == int(session_id)).values(name=name)
        )


def _stored_session_name(engine: Engine, session_id: str) -> Any:
    with engine.connect() as connection:
        return connection.execute(
            select(schema.sessions.c.name).where(schema.sessions.c.id == int(session_id))
        ).scalar_one()


def _matching(rows: list[dict[str, Any]], session_id: str) -> dict[str, Any]:
    matched = [row for row in rows if row["id"] == session_id]
    assert len(matched) == 1
    return matched[0]


# --- DoD-2: a new session reads `name` null on every payload ------------------------------


@pytest.mark.parametrize("body", [_OMITTED, {}], ids=["no-body", "empty-object"])
def test_the_start_answer_carries_name_null__S034_001_DoD2(
    application: FastAPI, db_settings: Settings, body: Any
) -> None:
    """DoD-2 — US-150.AC-1: `POST /api/characters/{id}/sessions` answers `name: null`."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")

    started = _start_started(client, character["id"], body)

    _assert_started_wire_shape(started)
    assert "name" in started
    assert started["name"] is None


def test_the_create_and_seed_answer_carries_name_null__S034_001_DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — US-150.AC-1: the create-and-seed answer (start with `opening_message`) carries
    `name: null` beside its opening message."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")

    started = _start_started(client, character["id"], {"opening_message": OPENING_TEXT})

    _assert_started_wire_shape(started)
    assert started["name"] is None
    assert started["opening_message"] is not None


def test_every_read_of_a_new_session_carries_name_null__S034_001_DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — US-150.AC-1: `GET /api/sessions`, `GET /api/characters/{id}/sessions`,
    `GET /api/sessions/{id}`, archive and restore all carry `name: null` for a new session."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    session_id = _start(client, character["id"], {})["id"]

    for row in (
        _matching(_all_sessions(client), session_id),
        _matching(_character_sessions(client, character["id"]), session_id),
        _read_session(client, session_id),
    ):
        _assert_wire_shape(row)
        assert row["name"] is None

    archived = _archive_session(client, session_id)
    assert archived.status_code == 200, archived.text
    _assert_wire_shape(archived.json())
    assert archived.json()["name"] is None
    assert _matching(_all_sessions(client, include_archived=True), session_id)["name"] is None

    restored = _restore_session(client, session_id)
    assert restored.status_code == 200, restored.text
    _assert_wire_shape(restored.json())
    assert restored.json()["name"] is None


def test_a_new_session_with_a_setup_still_carries_name_null__S034_001_DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — the setup's name travels as `setup_name`, never as the session's `name`."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    setup = _create_setup(client, character["id"], "Tavern", "# Night")

    started = _start_started(client, character["id"], {"setup_id": setup["id"]})

    assert started["setup_name"] == setup["name"]
    assert started["name"] is None
    read_back = _read_session(client, started["id"])
    assert read_back["setup_name"] == setup["name"]
    assert read_back["name"] is None


# --- DoD-3: starting needs no name, and a sent `name` is ignored --------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"name": "Chosen at start"},
        {"name": "Chosen at start", "opening_message": OPENING_TEXT},
    ],
    ids=["plain-start", "create-and-seed"],
)
def test_a_name_in_the_start_body_is_ignored__S034_001_DoD3(
    application: FastAPI, db_settings: Settings, engine: Engine, body: dict[str, Any]
) -> None:
    """DoD-3 — US-150.AC-6: a `name` key in a start body (either start) is ignored: 201, the
    answer carries `name: null`, the stored column is NULL and the read-back is null."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")

    response = _start_request(client, character["id"], body)

    assert response.status_code == 201, response.text
    started = response.json()
    _assert_started_wire_shape(started)
    assert started["name"] is None
    assert _stored_session_name(engine, started["id"]) is None
    assert _read_session(client, started["id"])["name"] is None


@pytest.mark.parametrize(
    "body",
    [_OMITTED, {}, {"opening_message": OPENING_TEXT}],
    ids=["no-body", "empty-object", "create-and-seed"],
)
def test_starting_needs_no_name__S034_001_DoD3(
    application: FastAPI, db_settings: Settings, engine: Engine, body: Any
) -> None:
    """DoD-3 — US-150.AC-6: starting either way with no name succeeds and stores `name` NULL."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")

    response = _start_request(client, character["id"], body)

    assert response.status_code == 201, response.text
    assert response.json()["name"] is None
    assert _stored_session_name(engine, response.json()["id"]) is None


# --- DoD-4: a stored name reads back exactly on every payload ------------------------------


def test_a_stored_name_reads_back_on_every_session_read__S034_001_DoD4(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-4 — a session whose `name` is stored returns that exact value from both listings,
    the single read, archive (and the archived listing) and restore."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    setup = _create_setup(client, character["id"], "Tavern", "# Night")
    session_id = _start(client, character["id"], {"setup_id": setup["id"]})["id"]
    _store_session_name(engine, session_id, STORED_SESSION_NAME)

    for row in (
        _matching(_all_sessions(client), session_id),
        _matching(_character_sessions(client, character["id"]), session_id),
        _read_session(client, session_id),
    ):
        _assert_wire_shape(row)
        assert row["name"] == STORED_SESSION_NAME
        # The joined setup name stays distinguishable from the session's own name.
        assert row["setup_name"] == setup["name"]

    archived = _archive_session(client, session_id)
    assert archived.status_code == 200, archived.text
    assert archived.json()["name"] == STORED_SESSION_NAME
    assert _matching(_all_sessions(client, include_archived=True), session_id)["name"] == STORED_SESSION_NAME
    assert (
        _matching(_character_sessions(client, character["id"], include_archived=True), session_id)["name"]
        == STORED_SESSION_NAME
    )

    restored = _restore_session(client, session_id)
    assert restored.status_code == 200, restored.text
    assert restored.json()["name"] == STORED_SESSION_NAME


def test_a_stored_name_is_per_session__S034_001_DoD4(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-4 — only the session whose name is stored carries it; its sibling stays null."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    named_id = _start(client, character["id"], {})["id"]
    unnamed_id = _start(client, character["id"], {})["id"]
    _store_session_name(engine, named_id, STORED_SESSION_NAME)

    rows = _character_sessions(client, character["id"])

    assert _matching(rows, named_id)["name"] == STORED_SESSION_NAME
    assert _matching(rows, unnamed_id)["name"] is None
    assert _read_session(client, unnamed_id)["name"] is None


# =====================================================================================
# Feature 034, step 002 — `PATCH /api/sessions/{session_id}` renames an owned session.
#
# Expected values come from `docs/plans/034.session-names/002.rename-route.md` (Interface
# intent; DoD-1..DoD-9 and DoD-11 here), DEC-034-1 (`name` is a required key, a string or
# null, trimmed, blank -> null), DEC-034-2 (any other key is a 422), DEC-034-5 (a rename
# embeds nothing and needs no embedding model), DEC-arch-session-names-6 (a rename writes
# `name` and `updated_at`, never `last_used_at`, so no list order moves) and 011's refusal
# identity (R5: foreign and unknown ids answer the same 404 `session_not_found`). Binding:
# `## Skeleton` -> Step 002 — `PATCH /api/sessions/{session_id}`, status 200, answering
# `SessionResponse`. Test names end `__S034_002_DoD<n>`.
# =====================================================================================

#: DoD-1's name as sent, and as it must come back trimmed.
RENAME_SENT = "  The Docks  "
RENAME_TRIMMED = "The Docks"

#: A name stored before a refused rename, so "the row is unchanged" covers `name` too.
NAME_BEFORE = "Before the storm"

#: The two keys a rename may change; every other session key must come back as it was.
RENAME_WRITES = {"name", "updated_at"}

#: Registry rows for DoD-9's designated-model case (raw inserts, null `api_key_ref`, so no
#: secret has to resolve — the same seeding shape `test_record_keeping_embedding.py` uses).
EMBEDDING_SERVER_ID = 7_250_000_000_000_000_501
EMBEDDING_MODEL_ID = 7_250_000_000_000_000_502
EMBEDDING_MODEL_NAME = "the-designated-embedding-model"


def _rename_request(client: TestClient, session_id: Any, body: Any) -> httpx.Response:
    """`PATCH /api/sessions/<id>` with ``body`` as its JSON body — the exact single-session path."""
    return client.patch(_session_path(session_id), json=body)


def _rename(client: TestClient, session_id: Any, name: Any) -> dict[str, Any]:
    """A rename that must succeed: 200 and the `Session` wire object (DoD-1)."""
    response = _rename_request(client, session_id, {"name": name})
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    _assert_wire_shape(body)
    return body


def _unchanged_by_rename(before: dict[str, Any], after: dict[str, Any]) -> None:
    """Every key a rename does not write is exactly what it was."""
    assert {key: value for key, value in after.items() if key not in RENAME_WRITES} == {
        key: value for key, value in before.items() if key not in RENAME_WRITES
    }


def _stored_times(engine: Engine, session_id: str) -> tuple[Any, Any, Any]:
    """`(last_used_at, updated_at, archived_at)` read straight from the row (DoD-3, DoD-7)."""
    with engine.connect() as connection:
        row = connection.execute(
            select(
                schema.sessions.c.last_used_at,
                schema.sessions.c.updated_at,
                schema.sessions.c.archived_at,
            ).where(schema.sessions.c.id == int(session_id))
        ).one()
    return (row[0], row[1], row[2])


def _stored_row(engine: Engine, session_id: str) -> dict[str, Any]:
    """The whole `sessions` row, for "the row is unchanged" (DoD-4, DoD-5, DoD-6)."""
    with engine.connect() as connection:
        row = connection.execute(select(schema.sessions).where(schema.sessions.c.id == int(session_id))).one()
    return dict(row._mapping)


def _designate_embedding_model(engine: Engine) -> None:
    """Seed one server and one enabled, embedding-designated model (DoD-9's second case)."""
    with engine.begin() as connection:
        connection.execute(
            schema.metadata.tables["llm_servers"].insert().values(
                id=EMBEDDING_SERVER_ID,
                name="the embedding server",
                kind="llamaswap",
                base_url="http://embedding.test:8080/v1",
                api_key_ref=None,
                last_test_at=None,
                last_test_ok=None,
                last_test_error=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )
        connection.execute(
            schema.metadata.tables["models"].insert().values(
                id=EMBEDDING_MODEL_ID,
                server_id=EMBEDDING_SERVER_ID,
                model_name=EMBEDDING_MODEL_NAME,
                is_enabled=True,
                is_embedding_designated=True,
                embedding_dim=8,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


# --- DoD-1: a rename answers 200 with the session, trimmed, and later reads agree --------


def test_a_rename_answers_200_with_the_trimmed_name__S034_002_DoD1(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-1 — US-150.AC-2: `{"name": "  The Docks  "}` answers 200 with the nine-key session
    whose `name` is `"The Docks"`; every key a rename does not write is unchanged."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    setup = _create_setup(client, character["id"], "Tavern", "# Night")
    created = _start(client, character["id"], {"setup_id": setup["id"]})

    renamed = _rename(client, created["id"], RENAME_SENT)

    assert renamed["name"] == RENAME_TRIMMED
    assert renamed["id"] == created["id"]
    _unchanged_by_rename(created, renamed)
    assert renamed["setup_name"] == setup["name"]
    assert _stored_session_name(engine, created["id"]) == RENAME_TRIMMED


def test_later_reads_return_the_new_name__S034_002_DoD1(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-1 — US-150.AC-2: after a rename, the single read and both listings return the name,
    and each equals the rename's own answer."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    session_id = _start(client, character["id"], {})["id"]

    renamed = _rename(client, session_id, RENAME_SENT)

    assert _read_session(client, session_id) == renamed
    assert _matching(_all_sessions(client), session_id) == renamed
    assert _matching(_character_sessions(client, character["id"]), session_id) == renamed


def test_a_second_rename_replaces_the_first__S034_002_DoD1(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-1 — US-150.AC-2: renaming an already-named session stores the new name."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    session_id = _start(client, character["id"], {})["id"]
    _rename(client, session_id, "First name")

    renamed = _rename(client, session_id, STORED_SESSION_NAME)

    assert renamed["name"] == STORED_SESSION_NAME
    assert _read_session(client, session_id)["name"] == STORED_SESSION_NAME


# --- DoD-2: blank or null clears the name --------------------------------------------------


@pytest.mark.parametrize(
    "cleared",
    ["", "   ", " \t\n ", None],
    ids=["empty", "spaces", "mixed-whitespace", "null"],
)
def test_a_blank_or_null_name_clears_it__S034_002_DoD2(
    application: FastAPI, db_settings: Settings, engine: Engine, cleared: str | None
) -> None:
    """DoD-2 — US-150.AC-3, DEC-034-1: `name` as `""`, whitespace only or `null` answers 200
    with `name` null; the stored column is NULL and later reads return null."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    session_id = _start(client, character["id"], {})["id"]
    _store_session_name(engine, session_id, NAME_BEFORE)

    renamed = _rename(client, session_id, cleared)

    assert renamed["name"] is None
    assert _stored_session_name(engine, session_id) is None
    assert _read_session(client, session_id)["name"] is None
    assert _matching(_all_sessions(client), session_id)["name"] is None
    assert _matching(_character_sessions(client, character["id"]), session_id)["name"] is None


def test_clearing_a_never_named_session_answers_200_with_null__S034_002_DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — US-150.AC-3: `null` on a session that has no name is still a 200 with null."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    session_id = _start(client, character["id"], {})["id"]

    renamed = _rename(client, session_id, None)

    assert renamed["name"] is None
    assert _read_session(client, session_id)["name"] is None


# --- DoD-3: updated_at advances, last_used_at and list order do not move --------------------


def test_a_rename_advances_updated_at_and_keeps_last_used_at__S034_002_DoD3(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-3 — US-150.AC-4, DEC-arch-session-names-6: `updated_at` moves forward; the stored
    `last_used_at` is byte-identical to what it was before the rename."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    created = _start(client, character["id"], {})
    last_used_before, updated_before, _archived = _stored_times(engine, created["id"])

    renamed = _rename(client, created["id"], RENAME_TRIMMED)

    last_used_after, updated_after, _archived_after = _stored_times(engine, created["id"])
    assert last_used_after == last_used_before
    assert renamed["last_used_at"] == created["last_used_at"]
    # The fixed-width timestamp form orders lexically.
    assert updated_after > updated_before
    assert renamed["updated_at"] > created["updated_at"]
    assert renamed["updated_at"] == updated_after
    assert _read_session(client, created["id"])["updated_at"] == renamed["updated_at"]


def test_a_rename_moves_no_session_in_either_listing__S034_002_DoD3(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-3 — US-150.AC-4: renaming the oldest and a middle session leaves the order of
    `GET /api/sessions` and of `GET /api/characters/{id}/sessions` exactly as it was."""
    client = _player_a(application, db_settings)
    aria = _character(client, "Aria")
    bramble = _character(client, "Bramble")
    oldest = _start(client, aria["id"], {})
    middle = _start(client, bramble["id"], {})
    _start(client, aria["id"], {})
    all_before = _ids(_all_sessions(client))
    aria_before = _ids(_character_sessions(client, aria["id"]))
    bramble_before = _ids(_character_sessions(client, bramble["id"]))

    _rename(client, oldest["id"], "Renamed oldest")
    _rename(client, middle["id"], "Renamed middle")

    assert _ids(_all_sessions(client)) == all_before
    assert _ids(_character_sessions(client, aria["id"])) == aria_before
    assert _ids(_character_sessions(client, bramble["id"])) == bramble_before
    assert all_before[-1] == oldest["id"]


# --- DoD-4: any key other than `name` is a 422 and changes nothing --------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"model": {"server_id": "7250000000000000009", "model_name": "x"}},
        {"system_prompt": "a prompt"},
        {"archived_at": None},
        {"name": "Changed", "model": None},
        {"name": "Changed", "system_prompt": "a prompt"},
        {"name": "Changed", "archived_at": "2026-01-01T00:00:00.000000+00:00"},
        {"name": "Changed", "setup_id": None},
        {"name": "Changed", "last_used_at": "2030-01-01T00:00:00.000000+00:00"},
    ],
    ids=[
        "model-alone",
        "system-prompt-alone",
        "archived-at-alone",
        "name-and-model",
        "name-and-system-prompt",
        "name-and-archived-at",
        "name-and-setup-id",
        "name-and-last-used-at",
    ],
)
def test_any_other_key_answers_422_and_leaves_the_row_unchanged__S034_002_DoD4(
    application: FastAPI, db_settings: Settings, engine: Engine, body: dict[str, Any]
) -> None:
    """DoD-4 — DEC-arch-session-names-2, DEC-034-2: a body with any key other than `name`,
    alone or beside `name`, answers 422; the stored row and the read are unchanged."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    session_id = _start(client, character["id"], {})["id"]
    _store_session_name(engine, session_id, NAME_BEFORE)
    read_before = _read_session(client, session_id)
    row_before = _stored_row(engine, session_id)

    response = _rename_request(client, session_id, body)

    assert response.status_code == 422, response.text
    assert _stored_row(engine, session_id) == row_before
    assert _read_session(client, session_id) == read_before


# --- DoD-5: a missing `name`, a non-object body, a non-string `name` -------------------------


@pytest.mark.parametrize(
    "body",
    [{}, [], ["The Docks"], "The Docks", 42],
    ids=["empty-object", "empty-list", "list", "string", "number"],
)
def test_a_body_without_name_or_not_an_object_answers_422__S034_002_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine, body: Any
) -> None:
    """DoD-5 — DEC-034-1: `{}` (no `name`) and a non-object body each answer 422; nothing is
    written."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    session_id = _start(client, character["id"], {})["id"]
    _store_session_name(engine, session_id, NAME_BEFORE)
    row_before = _stored_row(engine, session_id)

    response = _rename_request(client, session_id, body)

    assert response.status_code == 422, response.text
    assert _stored_row(engine, session_id) == row_before


def test_a_json_null_body_answers_422__S034_002_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-5 — DEC-034-1: a JSON `null` body is not an object and carries no `name`: 422."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    session_id = _start(client, character["id"], {})["id"]
    row_before = _stored_row(engine, session_id)

    response = client.patch(
        _session_path(session_id), content=b"null", headers={"content-type": "application/json"}
    )

    assert response.status_code == 422, response.text
    assert _stored_row(engine, session_id) == row_before


@pytest.mark.parametrize(
    "value",
    [42, 4.5, ["The Docks"], [], True, False, {"text": "The Docks"}],
    ids=["integer", "float", "list", "empty-list", "true", "false", "object"],
)
def test_a_non_string_non_null_name_answers_422__S034_002_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine, value: Any
) -> None:
    """DoD-5 — DEC-034-1: `name` as a number, a list or a boolean (or an object) answers 422;
    nothing is written."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    session_id = _start(client, character["id"], {})["id"]
    _store_session_name(engine, session_id, NAME_BEFORE)
    row_before = _stored_row(engine, session_id)

    response = _rename_request(client, session_id, {"name": value})

    assert response.status_code == 422, response.text
    assert _stored_row(engine, session_id) == row_before


# --- DoD-6: foreign and unknown ids are one 404; a malformed id is a 422 ---------------------


def test_renaming_another_users_session_answers_404_and_changes_nothing__S034_002_DoD6(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-6 — US-029.AC-1, R5: A renaming B's session answers 404 `session_not_found`; B's
    stored row and B's own read are unchanged."""
    owner = _player_b(application, db_settings)
    foreign_character = _character(owner, "Bramble")
    foreign_id = _start(owner, foreign_character["id"], {})["id"]
    _store_session_name(engine, foreign_id, NAME_BEFORE)
    owner_read_before = _read_session(owner, foreign_id)
    row_before = _stored_row(engine, foreign_id)
    intruder = _player_a(application, db_settings)

    response = _rename_request(intruder, foreign_id, {"name": "Taken over"})

    _assert_envelope(response, 404, SESSION_NOT_FOUND)
    assert response.json()["error"]["detail"] == {}
    assert _stored_row(engine, foreign_id) == row_before
    assert _read_session(owner, foreign_id) == owner_read_before


def test_a_foreign_rename_is_indistinguishable_from_an_unknown_id__S034_002_DoD6(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-6 — R5 refusal identity: the foreign-id answer equals the unknown-id answer, body
    for body, and the unknown id answers 404 `session_not_found` too."""
    owner = _player_b(application, db_settings)
    foreign_id = _start(owner, _character(owner, "Bramble")["id"], {})["id"]
    intruder = _player_a(application, db_settings)

    foreign = _rename_request(intruder, foreign_id, {"name": "Taken over"})
    unknown = _rename_request(intruder, UNKNOWN_SESSION_ID, {"name": "Taken over"})

    _assert_envelope(foreign, 404, SESSION_NOT_FOUND)
    _assert_envelope(unknown, 404, SESSION_NOT_FOUND)
    assert foreign.json() == unknown.json()


def test_a_malformed_session_id_answers_422__S034_002_DoD6(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-6 — the Wire contract: a non-numeric path id is FastAPI's native 422."""
    client = _player_a(application, db_settings)

    response = _rename_request(client, "abc", {"name": "Anything"})

    assert response.status_code == 422, response.text


# --- DoD-7: an archived session can be renamed and stays archived ---------------------------


def test_an_archived_session_can_be_renamed_and_stays_archived__S034_002_DoD7(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-7: renaming an archived session answers 200 with the name; `archived_at` is
    unchanged, it stays out of the working lists and appears renamed in the archived view."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    session_id = _start(client, character["id"], {})["id"]
    archived = _archive_session(client, session_id)
    assert archived.status_code == 200, archived.text
    archived_at = archived.json()["archived_at"]
    assert archived_at is not None

    renamed = _rename(client, session_id, RENAME_SENT)

    assert renamed["name"] == RENAME_TRIMMED
    assert renamed["archived_at"] == archived_at
    assert _stored_times(engine, session_id)[2] == archived_at
    assert session_id not in _ids(_all_sessions(client))
    assert session_id not in _ids(_character_sessions(client, character["id"]))
    assert _matching(_all_sessions(client, include_archived=True), session_id)["name"] == RENAME_TRIMMED
    assert _read_session(client, session_id)["archived_at"] == archived_at


# --- DoD-8: names are not unique -------------------------------------------------------------


def test_two_sessions_can_hold_the_same_name__S034_002_DoD8(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-8 — UC-089 exception flows: the same name on two sessions (here under two
    characters, and twice under one) is accepted every time and reads back on each."""
    client = _player_a(application, db_settings)
    aria = _character(client, "Aria")
    bramble = _character(client, "Bramble")
    first = _start(client, aria["id"], {})["id"]
    second = _start(client, aria["id"], {})["id"]
    third = _start(client, bramble["id"], {})["id"]

    for session_id in (first, second, third):
        assert _rename(client, session_id, RENAME_TRIMMED)["name"] == RENAME_TRIMMED

    for session_id in (first, second, third):
        assert _read_session(client, session_id)["name"] == RENAME_TRIMMED


# --- DoD-9: no embedding model needed, no embedding call made --------------------------------


def test_a_rename_succeeds_with_no_embedding_model_designated__S034_002_DoD9(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-9 — DEC-034-5: the seeded instance designates no embedding model (it holds no
    server at all); a rename still answers 200, and the provider seam builds no client."""
    factory: FakeClientFactory = fake_factory()
    application.dependency_overrides[get_llm_client_factory] = lambda: factory
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    session_id = _start(client, character["id"], {})["id"]
    constructions_before = factory.call_count

    renamed = _rename(client, session_id, RENAME_SENT)

    assert renamed["name"] == RENAME_TRIMMED
    assert factory.call_count == constructions_before
    assert factory.embed_calls == []


def test_a_rename_makes_no_embedding_call_even_with_a_designated_model__S034_002_DoD9(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-9 — DEC-034-5: with an embedding model designated, a rename still constructs no
    provider client and issues no embed call (the name is not part of the session text)."""
    _designate_embedding_model(engine)
    factory: FakeClientFactory = fake_factory()
    application.dependency_overrides[get_llm_client_factory] = lambda: factory
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    session_id = _start(client, character["id"], {})["id"]
    constructions_before = factory.call_count
    embeds_before = list(factory.embed_calls)

    renamed = _rename(client, session_id, RENAME_SENT)

    assert renamed["name"] == RENAME_TRIMMED
    assert factory.call_count == constructions_before
    assert factory.embed_calls == embeds_before


# --- DoD-11: the rename route refuses anonymous callers --------------------------------------


@pytest.mark.parametrize(
    "body",
    [{"name": "Anything"}, {}],
    ids=["valid-body", "empty-body"],
)
def test_an_anonymous_rename_answers_401__S034_002_DoD11(
    application: FastAPI, db_settings: Settings, engine: Engine, body: dict[str, Any]
) -> None:
    """DoD-11: with no session cookie, `PATCH /api/sessions/{id}` answers 401
    `not_authenticated` — for an existing session and for an unknown id — and writes nothing."""
    owner = _player_a(application, db_settings)
    session_id = _start(owner, _character(owner, "Aria")["id"], {})["id"]
    row_before = _stored_row(engine, session_id)
    anonymous = _anonymous(application)

    for target in (session_id, UNKNOWN_SESSION_ID):
        _assert_envelope(_rename_request(anonymous, target, body), 401, NOT_AUTHENTICATED)

    assert _stored_row(engine, session_id) == row_before
