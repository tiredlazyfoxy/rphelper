"""Tests for the setups router: ``/api/characters/{character_id}/setups`` and ``/api/setups/...``.

Every expected value comes from ``docs/plans/010.setups/003.setups-router.md`` (Interface
intent + Definition of done), ``003.context.md`` and the feature ``context.md`` (the **Wire
contract** table, D5 the route surface and router-level auth, D8 the two 404 codes plus
native 422, D9 archive semantics, R2, R5, R6). Bindings come from ``## Skeleton`` in
``status.md`` (steps 001, 002, 003).

Covers step 003 DoD-1 .. DoD-14. DoD-15 is ``[manual/live]`` and carries no test.

The application is always the real factory's (``create_app()``), pinned to the per-test
database through ``dependency_overrides[get_settings]``. Each signed-in caller gets its own
``TestClient`` carrying exactly one session cookie, so no cookie leaks between users.
Characters are created through 009's ``POST /api/characters`` and setups through this step's
create route (the FK chain of the feature context's "Test conventions"). ``conftest.py`` is
untouched: every fixture below is file-local.
"""

import re
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
from app.services.passwords import hash_password

CHARACTERS_PATH = "/api/characters"
SETUPS_PATH = "/api/setups"
LOGIN_PATH = "/api/auth/login"

TIMESTAMP = "2026-01-01T00:00:00+00:00"

#: The fixed-width timestamp form from ``data-model.md``, cited by the feature context.
TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00$")

PLAYER_A_ID = 9_200_001
PLAYER_A_NAME = "aster"
PLAYER_A_PASSWORD = "a quiet river at dusk"

PLAYER_B_ID = 9_200_002
PLAYER_B_NAME = "briar"
PLAYER_B_PASSWORD = "salt and lantern light"

#: An id no row holds (D8: indistinguishable from another user's id).
UNKNOWN_ID = 9_999_999_999

#: The ``Setup`` wire object's keys, from the feature context's Wire contract. Never ``user_id``.
SETUP_KEYS = {"id", "character_id", "name", "description", "archived_at", "created_at", "updated_at"}

NOT_AUTHENTICATED = "not_authenticated"
CHARACTER_NOT_FOUND = "character_not_found"
SETUP_NOT_FOUND = "setup_not_found"


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


# --- helpers -------------------------------------------------------------------------


def _character_path(character_id: Any) -> str:
    return f"{CHARACTERS_PATH}/{character_id}"


def _character_action_path(character_id: Any, action: str) -> str:
    return f"{CHARACTERS_PATH}/{character_id}/{action}"


def _collection_path(character_id: Any) -> str:
    return f"{CHARACTERS_PATH}/{character_id}/setups"


def _setup_path(setup_id: Any) -> str:
    return f"{SETUPS_PATH}/{setup_id}"


def _setup_action_path(setup_id: Any, action: str) -> str:
    return f"{SETUPS_PATH}/{setup_id}/{action}"


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
    """009's create route: the parent row every setup needs (feature context, Test conventions)."""
    response = client.post(CHARACTERS_PATH, json={"name": name, "sheet": ""})
    assert response.status_code == 201, response.text
    created = response.json()
    assert isinstance(created, dict)
    return created


def _create_setup(
    client: TestClient,
    character_id: Any,
    name: str,
    description: str = "",
) -> dict[str, Any]:
    response = client.post(_collection_path(character_id), json={"name": name, "description": description})
    assert response.status_code == 201, response.text
    created = response.json()
    assert isinstance(created, dict)
    return created


def _listing(
    client: TestClient,
    character_id: Any,
    *,
    include_archived: bool | None = None,
) -> list[dict[str, Any]]:
    params = {} if include_archived is None else {"include_archived": str(include_archived).lower()}
    response = client.get(_collection_path(character_id), params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"setups"}
    rows = body["setups"]
    assert isinstance(rows, list)
    return rows


def _ids(rows: list[dict[str, Any]]) -> list[str]:
    return [row["id"] for row in rows]


def _read_setup(client: TestClient, setup_id: Any) -> dict[str, Any]:
    response = client.get(_setup_path(setup_id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def _assert_wire_shape(setup: dict[str, Any]) -> None:
    """The ``Setup`` wire object of the feature context's Wire contract."""
    assert set(setup) == SETUP_KEYS
    assert isinstance(setup["id"], str)
    assert setup["id"].isdigit()
    assert isinstance(setup["character_id"], str)
    assert setup["character_id"].isdigit()
    assert isinstance(setup["name"], str)
    assert isinstance(setup["description"], str)
    assert setup["archived_at"] is None or isinstance(setup["archived_at"], str)
    assert TIMESTAMP_PATTERN.match(setup["created_at"]) is not None
    assert TIMESTAMP_PATTERN.match(setup["updated_at"]) is not None


def _foreign_collection_request(client: TestClient, method: str, character_id: Any) -> httpx.Response:
    if method == "GET":
        return client.get(_collection_path(character_id))
    return client.post(_collection_path(character_id), json={"name": "Taken over", "description": "# Mine"})


def _foreign_setup_request(client: TestClient, method: str, setup_id: Any) -> httpx.Response:
    if method == "GET":
        return client.get(_setup_path(setup_id))
    if method == "PATCH":
        return client.patch(_setup_path(setup_id), json={"name": "Taken over"})
    return client.post(_setup_action_path(setup_id, method))


# --- DoD-1: router-level auth ----------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("GET", _collection_path(UNKNOWN_ID), None),
        ("POST", _collection_path(UNKNOWN_ID), {"name": "Tavern", "description": "# Night"}),
        ("GET", _setup_path(UNKNOWN_ID), None),
        ("PATCH", _setup_path(UNKNOWN_ID), {"name": "Inn"}),
        ("POST", _setup_action_path(UNKNOWN_ID, "archive"), None),
        ("POST", _setup_action_path(UNKNOWN_ID, "restore"), None),
    ],
    ids=["list", "create", "read", "update", "archive", "restore"],
)
def test_every_route_answers_401_without_a_session__S010_003_DoD1(
    application: FastAPI, method: str, path: str, json_body: dict[str, Any] | None
) -> None:
    """DoD-1 — D5: `require_user` sits on the router, so all six routes refuse anonymously."""
    response = _anonymous(application).request(method, path, json=json_body)

    _assert_envelope(response, 401, NOT_AUTHENTICATED)


# --- DoD-2: create, then listing and read-by-id ---------------------------------------


def test_create_answers_201_with_the_created_setup__S010_003_DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — US-023.AC-1: the create answers 201 with the Wire contract's `Setup`."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")

    response = client.post(_collection_path(character["id"]), json={"name": "Tavern", "description": "# Night"})

    assert response.status_code == 201, response.text
    created = response.json()
    _assert_wire_shape(created)
    assert created["name"] == "Tavern"
    assert created["description"] == "# Night"
    assert created["archived_at"] is None
    assert created["character_id"] == character["id"]


def test_created_ids_are_json_strings_of_decimal_digits__S010_003_DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — the JSON id boundary: both ids are JSON strings, not numbers."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")

    created = _create_setup(client, character["id"], "Tavern", "# Night")

    assert isinstance(created["id"], str)
    assert created["id"].isdigit()
    assert isinstance(created["character_id"], str)
    assert created["character_id"].isdigit()


def test_the_created_setup_is_listed_and_readable_by_id__S010_003_DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — the listing contains the created row and `GET /api/setups/<id>` answers it."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    created = _create_setup(client, character["id"], "Tavern", "# Night")

    rows = _listing(client, character["id"])

    assert created["id"] in _ids(rows)
    assert _read_setup(client, created["id"]) == created


# --- DoD-3: name validation and the two body conventions ------------------------------


@pytest.mark.parametrize(
    "json_body",
    [
        {"name": "", "description": "# Night"},
        {"name": "   ", "description": "# Night"},
        {"description": "# Night"},
    ],
    ids=["empty", "whitespace", "absent"],
)
def test_a_blank_or_missing_name_answers_422_and_changes_nothing__S010_003_DoD3(
    application: FastAPI, db_settings: Settings, json_body: dict[str, Any]
) -> None:
    """DoD-3 — D8: `name` is stripped then required non-empty; FastAPI's native 422, no domain code."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    _create_setup(client, character["id"], "Tavern", "# Night")
    before = _listing(client, character["id"])

    response = client.post(_collection_path(character["id"]), json=json_body)

    assert response.status_code == 422
    assert _listing(client, character["id"]) == before


def test_a_padded_name_is_stored_stripped__S010_003_DoD3(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-3 — D8: `"  Tavern "` is stored and answered as `"Tavern"`."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")

    created = _create_setup(client, character["id"], "  Tavern ", "# Night")

    assert created["name"] == "Tavern"
    assert _read_setup(client, created["id"])["name"] == "Tavern"


def test_a_missing_description_is_answered_as_empty__S010_003_DoD3(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-3 — D8: `description` may be omitted; the answer carries `""`."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")

    response = client.post(_collection_path(character["id"]), json={"name": "Tavern"})

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["description"] == ""
    assert _read_setup(client, created["id"])["description"] == ""


# --- DoD-4: a new character has no setups ---------------------------------------------


def test_a_fresh_characters_listing_is_empty__S010_003_DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-4 — R2: creating a character creates no setup, not even with the archived flag on."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")

    response = client.get(_collection_path(character["id"]), params={"include_archived": "true"})

    assert response.status_code == 200, response.text
    assert response.json() == {"setups": []}


# --- DoD-5: another user's (or nobody's) parent character ------------------------------


@pytest.mark.parametrize("method", ["GET", "POST"], ids=["list", "create"])
def test_a_foreign_parent_character_answers_404_character_not_found__S010_003_DoD5(
    application: FastAPI, db_settings: Settings, method: str
) -> None:
    """DoD-5 — R5, D8: a parent that is not the caller's answers 404 `character_not_found`."""
    owner = _player_a(application, db_settings)
    character = _character(owner, "Aria")
    intruder = _player_b(application, db_settings)

    body = _assert_envelope(_foreign_collection_request(intruder, method, character["id"]), 404, CHARACTER_NOT_FOUND)

    assert body["error"]["detail"] == {}


def test_a_refused_create_leaves_the_owners_listing_empty__S010_003_DoD5(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-5 — R5: the owner's listing holds no setup created by another user."""
    owner = _player_a(application, db_settings)
    character = _character(owner, "Aria")
    intruder = _player_b(application, db_settings)

    assert _foreign_collection_request(intruder, "POST", character["id"]).status_code == 404

    assert _listing(owner, character["id"], include_archived=True) == []


@pytest.mark.parametrize("method", ["GET", "POST"], ids=["list", "create"])
def test_a_foreign_parent_is_indistinguishable_from_an_unknown_one__S010_003_DoD5(
    application: FastAPI, db_settings: Settings, method: str
) -> None:
    """DoD-5 — R5, D8: another user's character id and nobody's id answer the same body."""
    owner = _player_a(application, db_settings)
    character = _character(owner, "Aria")
    intruder = _player_b(application, db_settings)

    foreign = _foreign_collection_request(intruder, method, character["id"])
    unknown = _foreign_collection_request(intruder, method, UNKNOWN_ID)

    assert foreign.status_code == unknown.status_code == 404
    assert foreign.json() == unknown.json()


# --- DoD-6: another user's (or nobody's) setup -----------------------------------------


@pytest.mark.parametrize("method", ["GET", "PATCH", "archive", "restore"])
def test_a_foreign_setup_answers_404_setup_not_found__S010_003_DoD6(
    application: FastAPI, db_settings: Settings, method: str
) -> None:
    """DoD-6 — R5, D8: another user's setup answers 404 `setup_not_found`, and is untouched."""
    owner = _player_a(application, db_settings)
    character = _character(owner, "Aria")
    created = _create_setup(owner, character["id"], "Tavern", "# Night")
    intruder = _player_b(application, db_settings)

    body = _assert_envelope(_foreign_setup_request(intruder, method, created["id"]), 404, SETUP_NOT_FOUND)

    assert body["error"]["detail"] == {}
    assert _read_setup(owner, created["id"]) == created


@pytest.mark.parametrize("method", ["GET", "PATCH", "archive", "restore"])
def test_a_foreign_setup_is_indistinguishable_from_an_unknown_one__S010_003_DoD6(
    application: FastAPI, db_settings: Settings, method: str
) -> None:
    """DoD-6 — R5, D8: another user's setup id and nobody's id answer the same body."""
    owner = _player_a(application, db_settings)
    character = _character(owner, "Aria")
    created = _create_setup(owner, character["id"], "Tavern", "# Night")
    intruder = _player_b(application, db_settings)

    foreign = _foreign_setup_request(intruder, method, created["id"])
    unknown = _foreign_setup_request(intruder, method, UNKNOWN_ID)

    assert foreign.status_code == unknown.status_code == 404
    assert foreign.json() == unknown.json()


# --- DoD-7: a listing carries only its own character's setups --------------------------


@pytest.mark.parametrize("include_archived", [None, True], ids=["default", "include_archived"])
def test_each_listing_carries_only_its_own_characters_setups__S010_003_DoD7(
    application: FastAPI, db_settings: Settings, include_archived: bool | None
) -> None:
    """DoD-7 — R5: two owners, three characters; no setup crosses a character or an owner."""
    owner = _player_a(application, db_settings)
    first = _character(owner, "Aria")
    second = _character(owner, "Bryn")
    first_a = _create_setup(owner, first["id"], "Tavern", "# Night")
    first_b = _create_setup(owner, first["id"], "Market", "# Day")
    second_a = _create_setup(owner, second["id"], "Keep", "# Walls")

    intruder = _player_b(application, db_settings)
    other = _character(intruder, "Cass")
    other_a = _create_setup(intruder, other["id"], "Harbour", "# Salt")

    first_rows = _listing(owner, first["id"], include_archived=include_archived)
    second_rows = _listing(owner, second["id"], include_archived=include_archived)

    assert set(_ids(first_rows)) == {first_a["id"], first_b["id"]}
    assert set(_ids(second_rows)) == {second_a["id"]}
    assert other_a["id"] not in _ids(first_rows) + _ids(second_rows)
    assert {row["character_id"] for row in first_rows} == {first["id"]}
    assert {row["character_id"] for row in second_rows} == {second["id"]}


# --- DoD-8: PATCH, and the keys a body can never set ----------------------------------


def test_patching_name_then_description_persists_both__S010_003_DoD8(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-8 — D5: two PATCHes, each answering the updated setup; both edits persist."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    created = _create_setup(client, character["id"], "Tavern", "# Night")

    renamed = client.patch(_setup_path(created["id"]), json={"name": "Inn"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Inn"

    rebodied = client.patch(_setup_path(created["id"]), json={"description": "new body"})
    assert rebodied.status_code == 200, rebodied.text
    assert rebodied.json()["description"] == "new body"

    read_back = _read_setup(client, created["id"])
    assert read_back["name"] == "Inn"
    assert read_back["description"] == "new body"


def test_patch_ignores_character_id_and_the_setup_cannot_move__S010_003_DoD8(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-8 — D5: `character_id` is not a field of the request model, so a body carrying it is ignored."""
    client = _player_a(application, db_settings)
    origin = _character(client, "Aria")
    elsewhere = _character(client, "Bryn")
    created = _create_setup(client, origin["id"], "Tavern", "# Night")

    response = client.patch(_setup_path(created["id"]), json={"character_id": elsewhere["id"]})

    assert response.status_code == 200, response.text
    assert response.json()["character_id"] == origin["id"]
    assert _read_setup(client, created["id"])["character_id"] == origin["id"]
    assert created["id"] in _ids(_listing(client, origin["id"], include_archived=True))
    assert created["id"] not in _ids(_listing(client, elsewhere["id"], include_archived=True))


def test_create_ignores_user_id_and_archived_at_in_the_body__S010_003_DoD8(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-8 — D8: unknown body keys are ignored; the owner is the caller and the row is not born archived."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")

    response = client.post(
        _collection_path(character["id"]),
        json={
            "name": "Tavern",
            "description": "# Night",
            "user_id": str(PLAYER_B_ID),
            "archived_at": TIMESTAMP,
        },
    )

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["archived_at"] is None
    assert _read_setup(client, created["id"]) == created
    intruder = _player_b(application, db_settings)
    _assert_envelope(intruder.get(_setup_path(created["id"])), 404, SETUP_NOT_FOUND)


def test_patch_ignores_user_id_and_archived_at_in_the_body__S010_003_DoD8(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-8 — D8: a PATCH can neither re-owner nor archive through the body."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    created = _create_setup(client, character["id"], "Tavern", "# Night")

    response = client.patch(
        _setup_path(created["id"]),
        json={"name": "Inn", "user_id": str(PLAYER_B_ID), "archived_at": TIMESTAMP},
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["name"] == "Inn"
    assert updated["archived_at"] is None
    assert _read_setup(client, created["id"]) == updated
    intruder = _player_b(application, db_settings)
    _assert_envelope(intruder.get(_setup_path(created["id"])), 404, SETUP_NOT_FOUND)


# --- DoD-9: archive -------------------------------------------------------------------


def test_archive_stamps_the_row_and_moves_it_out_of_the_working_list__S010_003_DoD9(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-9 — US-087.AC-1, R6: archived leaves the working list, stays readable by id and under the flag."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    created = _create_setup(client, character["id"], "Tavern", "# Night")

    response = client.post(_setup_action_path(created["id"], "archive"))

    assert response.status_code == 200, response.text
    archived = response.json()
    _assert_wire_shape(archived)
    assert isinstance(archived["archived_at"], str)

    assert created["id"] not in _ids(_listing(client, character["id"]))
    assert created["id"] in _ids(_listing(client, character["id"], include_archived=True))
    assert _read_setup(client, created["id"])["archived_at"] == archived["archived_at"]


def test_archiving_twice_keeps_the_first_archived_at__S010_003_DoD9(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-9 — D9: archive on an archived setup is a no-op keeping the original `archived_at`."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    created = _create_setup(client, character["id"], "Tavern", "# Night")
    first = client.post(_setup_action_path(created["id"], "archive"))
    assert first.status_code == 200, first.text

    second = client.post(_setup_action_path(created["id"], "archive"))

    assert second.status_code == 200, second.text
    assert second.json()["archived_at"] == first.json()["archived_at"]


# --- DoD-10: restore ------------------------------------------------------------------


def test_restore_clears_archived_at_and_returns_the_row_to_the_list__S010_003_DoD10(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-10 — US-087.AC-2: restore nulls `archived_at` and the default listing contains the row again."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    created = _create_setup(client, character["id"], "Tavern", "# Night")
    assert client.post(_setup_action_path(created["id"], "archive")).status_code == 200

    response = client.post(_setup_action_path(created["id"], "restore"))

    assert response.status_code == 200, response.text
    assert response.json()["archived_at"] is None
    assert created["id"] in _ids(_listing(client, character["id"]))


# --- DoD-11: no delete path -----------------------------------------------------------


def test_delete_on_the_setup_route_answers_405_and_destroys_nothing__S010_003_DoD11(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-11 — R6: no DELETE handler exists on `/api/setups/{setup_id}`; the setup survives."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    created = _create_setup(client, character["id"], "Tavern", "# Night")

    assert client.delete(_setup_path(created["id"])).status_code == 405

    assert _read_setup(client, created["id"]) == created


def test_delete_on_the_collection_route_answers_405_and_destroys_nothing__S010_003_DoD11(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-11 — R6: the collection route has no DELETE either; the setup survives."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    created = _create_setup(client, character["id"], "Tavern", "# Night")

    assert client.delete(_collection_path(character["id"])).status_code == 405

    assert _read_setup(client, created["id"]) == created


# --- DoD-12: an archived parent character still serves both routes --------------------


def test_an_archived_character_still_lists_and_accepts_setups__S010_003_DoD12(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-12 — D5: listing under and creating under an archived character both succeed."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")
    assert client.post(_character_action_path(character["id"], "archive")).status_code == 200

    listing = client.get(_collection_path(character["id"]))
    created = client.post(_collection_path(character["id"]), json={"name": "Tavern", "description": "# Night"})

    assert listing.status_code == 200, listing.text
    assert created.status_code == 201, created.text
    assert created.json()["character_id"] == character["id"]


# --- DoD-13: the JSON id boundary on the path -----------------------------------------


@pytest.mark.parametrize(
    "path",
    [_setup_path("abc"), _collection_path("abc")],
    ids=["setup", "collection"],
)
def test_a_non_numeric_path_id_answers_422__S010_003_DoD13(
    application: FastAPI, db_settings: Settings, path: str
) -> None:
    """DoD-13 — the JSON id boundary: `SnowflakeIn` rejects a non-numeric path id."""
    client = _player_a(application, db_settings)

    response = client.get(path)

    assert response.status_code == 422


# --- DoD-14: 009's routes still behave ------------------------------------------------


def test_the_characters_routes_still_behave_with_this_router_registered__S010_003_DoD14(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-14 — registration order, D5: 009's item and archive routes still match first."""
    client = _player_a(application, db_settings)
    character = _character(client, "Aria")

    read = client.get(_character_path(character["id"]))
    archived = client.post(_character_action_path(character["id"], "archive"))

    assert read.status_code == 200, read.text
    assert read.json()["id"] == character["id"]
    assert read.json()["name"] == "Aria"
    assert archived.status_code == 200, archived.text
