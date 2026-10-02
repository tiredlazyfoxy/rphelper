"""Tests for the characters router: ``/api/characters`` and its six routes.

Every expected value comes from ``docs/plans/009.characters/003.characters-router.md``
(Interface intent + Definition of done), ``003.context.md`` and the feature ``context.md``
(the **Wire contract** table, D6 router-level auth, D7 the route surface, D8 one 404 plus
native 422, D9 archive semantics, D10 list order, R5, R6). Bindings come from
``## Skeleton`` in ``status.md`` (steps 001, 002, 003).

Covers step 003 DoD-1 .. DoD-13. DoD-14 is ``[manual/live]`` and carries no test.

The application is always the real factory's (``create_app()``), pinned to the per-test
database through ``dependency_overrides[get_settings]``. Each signed-in caller gets its
own ``TestClient`` carrying exactly one session cookie, so no cookie leaks between users.
``conftest.py`` is untouched: every fixture below is file-local.
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

LIST_PATH = "/api/characters"
LOGIN_PATH = "/api/auth/login"

TIMESTAMP = "2026-01-01T00:00:00+00:00"

#: The fixed-width timestamp form from ``data-model.md``, cited by the feature context.
TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00$")

PLAYER_A_ID = 9_100_001
PLAYER_A_NAME = "aster"
PLAYER_A_PASSWORD = "a quiet river at dusk"

PLAYER_B_ID = 9_100_002
PLAYER_B_NAME = "briar"
PLAYER_B_PASSWORD = "salt and lantern light"

ADMIN_ID = 9_100_003
ADMIN_NAME = "founder"
ADMIN_PASSWORD = "correct horse battery staple"

#: An id that exists for nobody (D8: indistinguishable from another user's id).
UNKNOWN_ID = 9_999_999_999

CHARACTER_KEYS = {"id", "name", "sheet", "archived_at", "created_at", "updated_at"}

NOT_AUTHENTICATED = "not_authenticated"
CHARACTER_NOT_FOUND = "character_not_found"


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
    _insert_user(engine, user_id=ADMIN_ID, username=ADMIN_NAME, password=ADMIN_PASSWORD, role=Role.ADMIN)


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database with the registry applied and the three accounts seeded."""
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


def _item_path(character_id: Any) -> str:
    return f"{LIST_PATH}/{character_id}"


def _action_path(character_id: Any, action: str) -> str:
    return f"{LIST_PATH}/{character_id}/{action}"


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


def _administrator(application: FastAPI, settings: Settings) -> TestClient:
    return _as(application, settings, ADMIN_NAME, ADMIN_PASSWORD)


def _assert_envelope(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error, dict)
    assert error["code"] == code
    return body


def _created(client: TestClient, name: str, sheet: str = "") -> dict[str, Any]:
    response = client.post(LIST_PATH, json={"name": name, "sheet": sheet})
    assert response.status_code == 201, response.text
    created = response.json()
    assert isinstance(created, dict)
    return created


def _listing(client: TestClient, *, include_archived: bool | None = None) -> list[dict[str, Any]]:
    params = {} if include_archived is None else {"include_archived": str(include_archived).lower()}
    response = client.get(LIST_PATH, params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"characters"}
    rows = body["characters"]
    assert isinstance(rows, list)
    return rows


def _ids(rows: list[dict[str, Any]]) -> list[str]:
    return [row["id"] for row in rows]


def _read(client: TestClient, character_id: Any) -> dict[str, Any]:
    response = client.get(_item_path(character_id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def _assert_wire_shape(character: dict[str, Any]) -> None:
    """The ``Character`` wire object of the feature context's Wire contract."""
    assert set(character) == CHARACTER_KEYS
    assert isinstance(character["id"], str)
    assert character["id"].isdigit()
    assert isinstance(character["name"], str)
    assert isinstance(character["sheet"], str)
    assert character["archived_at"] is None or isinstance(character["archived_at"], str)
    assert TIMESTAMP_PATTERN.match(character["created_at"]) is not None
    assert TIMESTAMP_PATTERN.match(character["updated_at"]) is not None


# --- DoD-1: every route is behind the session guard ----------------------------------


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("GET", LIST_PATH, None),
        ("POST", LIST_PATH, {"name": "Aria", "sheet": "# Aria"}),
        ("GET", _item_path(UNKNOWN_ID), None),
        ("PATCH", _item_path(UNKNOWN_ID), {"name": "Aria"}),
        ("POST", _action_path(UNKNOWN_ID, "archive"), None),
        ("POST", _action_path(UNKNOWN_ID, "restore"), None),
    ],
    ids=["list", "create", "read", "update", "archive", "restore"],
)
def test_every_route_answers_401_without_a_session__DoD1(
    application: FastAPI, method: str, path: str, json_body: dict[str, Any] | None
) -> None:
    """DoD-1 — D6: `require_user` sits on the router, so all six routes refuse anonymously."""
    response = _anonymous(application).request(method, path, json=json_body)
    _assert_envelope(response, 401, NOT_AUTHENTICATED)


# --- DoD-2: create ---------------------------------------------------------------------


def test_create_answers_201_with_the_created_character__DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — US-020.AC-1: the created row comes back whole, with a string id."""
    client = _player_a(application, db_settings)
    response = client.post(LIST_PATH, json={"name": "Aria", "sheet": "# Aria"})

    assert response.status_code == 201
    created = response.json()
    _assert_wire_shape(created)
    assert created["name"] == "Aria"
    assert created["sheet"] == "# Aria"
    assert created["archived_at"] is None


def test_created_id_is_a_json_string_of_decimal_digits__DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — the JSON id boundary: `id` is a string on the wire, never a number.

    ``json.loads`` yields ``str`` only for a quoted JSON value, so the type assertion
    below *is* the assertion that the wire carries it quoted.
    """
    response = _player_a(application, db_settings).post(LIST_PATH, json={"name": "Aria", "sheet": "# Aria"})
    assert response.status_code == 201
    created = response.json()

    assert isinstance(created["id"], str)
    assert created["id"].isdigit()
    assert int(created["id"]) > 0
    assert f'"{created["id"]}"' in response.text


def test_created_character_appears_in_the_listing__DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — US-020.AC-2: a following `GET /api/characters` contains the new row."""
    client = _player_a(application, db_settings)
    created = _created(client, "Aria", "# Aria")

    rows = _listing(client)
    assert created["id"] in _ids(rows)
    assert created in rows


# --- DoD-3: name validation is native 422 ---------------------------------------------


@pytest.mark.parametrize(
    "body",
    [{"name": "", "sheet": "x"}, {"name": "   ", "sheet": "x"}, {"sheet": "x"}],
    ids=["empty", "whitespace-only", "absent"],
)
def test_blank_or_missing_name_answers_422_and_changes_nothing__DoD3(
    application: FastAPI, db_settings: Settings, body: dict[str, Any]
) -> None:
    """DoD-3 — D8: a blank name is FastAPI's native 422, with no row written."""
    client = _player_a(application, db_settings)
    _created(client, "Existing", "body")
    before = _listing(client)

    response = client.post(LIST_PATH, json=body)

    assert response.status_code == 422
    assert _listing(client) == before


def test_a_padded_name_is_stored_stripped__DoD3(application: FastAPI, db_settings: Settings) -> None:
    """DoD-3 — D8: the stored name is the stripped value, and reads agree."""
    client = _player_a(application, db_settings)
    created = _created(client, "  Aria ", "# Aria")

    assert created["name"] == "Aria"
    assert _read(client, created["id"])["name"] == "Aria"


# --- DoD-4: listings are owner-scoped --------------------------------------------------


def test_each_listing_carries_only_its_own_owners_characters__DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-4 — US-022.AC-1, R5: with and without the flag, a listing never crosses owners."""
    client_a = _player_a(application, db_settings)
    client_b = _player_b(application, db_settings)

    a_working = _created(client_a, "A working", "a1")
    a_archived = _created(client_a, "A archived", "a2")
    assert client_a.post(_action_path(a_archived["id"], "archive")).status_code == 200
    b_working = _created(client_b, "B working", "b1")
    b_archived = _created(client_b, "B archived", "b2")
    assert client_b.post(_action_path(b_archived["id"], "archive")).status_code == 200

    assert _ids(_listing(client_a)) == [a_working["id"]]
    assert set(_ids(_listing(client_a, include_archived=True))) == {a_working["id"], a_archived["id"]}
    assert _ids(_listing(client_b)) == [b_working["id"]]
    assert set(_ids(_listing(client_b, include_archived=True))) == {b_working["id"], b_archived["id"]}


# --- DoD-5: another user's id is the one 404 -------------------------------------------


def _foreign_request(client: TestClient, method: str, character_id: Any) -> httpx.Response:
    if method == "GET":
        return client.get(_item_path(character_id))
    if method == "PATCH":
        return client.patch(_item_path(character_id), json={"name": "Taken over"})
    return client.post(_action_path(character_id, method))


@pytest.mark.parametrize("method", ["GET", "PATCH", "archive", "restore"])
def test_another_users_character_answers_404_character_not_found__DoD5(
    application: FastAPI, db_settings: Settings, method: str
) -> None:
    """DoD-5 — R5, D8: B is told the id does not exist, with an empty `detail`."""
    client_a = _player_a(application, db_settings)
    client_b = _player_b(application, db_settings)
    owned = _created(client_a, "Aria", "# Aria")

    response = _foreign_request(client_b, method, owned["id"])

    body = _assert_envelope(response, 404, CHARACTER_NOT_FOUND)
    assert body["error"]["detail"] == {}


@pytest.mark.parametrize("method", ["GET", "PATCH", "archive", "restore"])
def test_another_users_character_is_untouched_by_the_attempt__DoD5(
    application: FastAPI, db_settings: Settings, method: str
) -> None:
    """DoD-5 — R5: a refused request writes nothing; A reads back exactly what it had."""
    client_a = _player_a(application, db_settings)
    client_b = _player_b(application, db_settings)
    owned = _created(client_a, "Aria", "# Aria")

    assert _foreign_request(client_b, method, owned["id"]).status_code == 404

    assert _read(client_a, owned["id"]) == owned


@pytest.mark.parametrize("method", ["GET", "PATCH", "archive", "restore"])
def test_another_users_id_is_indistinguishable_from_an_unknown_id__DoD5(
    application: FastAPI, db_settings: Settings, method: str
) -> None:
    """DoD-5 — D8: no existence leak — both refusals are byte-for-byte the same body."""
    client_a = _player_a(application, db_settings)
    client_b = _player_b(application, db_settings)
    owned = _created(client_a, "Aria", "# Aria")

    foreign = _foreign_request(client_b, method, owned["id"])
    unknown = _foreign_request(client_b, method, UNKNOWN_ID)

    assert foreign.status_code == unknown.status_code == 404
    assert foreign.json() == unknown.json()


# --- DoD-6: PATCH ----------------------------------------------------------------------


def test_patching_name_then_sheet_persists_both__DoD6(application: FastAPI, db_settings: Settings) -> None:
    """DoD-6 — US-021.AC-1, D7: each PATCH answers the updated row and both edits stick."""
    client = _player_a(application, db_settings)
    created = _created(client, "Aria", "# Aria")

    renamed = client.patch(_item_path(created["id"]), json={"name": "Bo"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Bo"
    assert renamed.json()["sheet"] == "# Aria"

    rewritten = client.patch(_item_path(created["id"]), json={"sheet": "new body"})
    assert rewritten.status_code == 200
    assert rewritten.json()["name"] == "Bo"
    assert rewritten.json()["sheet"] == "new body"

    read_back = _read(client, created["id"])
    assert read_back["name"] == "Bo"
    assert read_back["sheet"] == "new body"
    assert read_back["id"] == created["id"]


# --- DoD-7: archive --------------------------------------------------------------------


def test_archive_stamps_the_row_and_moves_it_out_of_the_working_list__DoD7(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-7 — US-086.AC-1, US-086.AC-3, R6: archived, still listable by flag and by id."""
    client = _player_a(application, db_settings)
    created = _created(client, "Aria", "# Aria")

    archived = client.post(_action_path(created["id"], "archive"))
    assert archived.status_code == 200
    archived_body = archived.json()
    _assert_wire_shape(archived_body)
    assert isinstance(archived_body["archived_at"], str)
    assert TIMESTAMP_PATTERN.match(archived_body["archived_at"]) is not None

    assert created["id"] not in _ids(_listing(client))
    assert created["id"] in _ids(_listing(client, include_archived=True))

    read_back = client.get(_item_path(created["id"]))
    assert read_back.status_code == 200
    assert read_back.json()["archived_at"] == archived_body["archived_at"]


# --- DoD-8: restore --------------------------------------------------------------------


def test_restore_clears_archived_at_and_returns_the_row_to_the_list__DoD8(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-8 — US-086.AC-2: restore puts the character back in the working list."""
    client = _player_a(application, db_settings)
    created = _created(client, "Aria", "# Aria")
    assert client.post(_action_path(created["id"], "archive")).status_code == 200

    restored = client.post(_action_path(created["id"], "restore"))
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None

    assert created["id"] in _ids(_listing(client))


# --- DoD-9: no delete path -------------------------------------------------------------


def test_delete_on_the_item_route_answers_405_and_destroys_nothing__DoD9(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-9 — R6, US-086.AC-3: no DELETE handler exists; the character survives."""
    client = _player_a(application, db_settings)
    created = _created(client, "Aria", "# Aria")

    assert client.delete(_item_path(created["id"])).status_code == 405

    assert _read(client, created["id"]) == created


def test_delete_on_the_collection_route_answers_405_and_destroys_nothing__DoD9(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-9 — R6: the collection route has no DELETE either."""
    client = _player_a(application, db_settings)
    created = _created(client, "Aria", "# Aria")

    assert client.delete(LIST_PATH).status_code == 405

    assert _read(client, created["id"]) == created


# --- DoD-10: archive is idempotent ------------------------------------------------------


def test_archiving_twice_keeps_the_first_archived_at__DoD10(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-10 — D9: 'when was this archived' stays true; the second archive is a no-op."""
    client = _player_a(application, db_settings)
    created = _created(client, "Aria", "# Aria")

    first = client.post(_action_path(created["id"], "archive"))
    assert first.status_code == 200
    second = client.post(_action_path(created["id"], "archive"))
    assert second.status_code == 200

    assert second.json()["archived_at"] == first.json()["archived_at"]
    assert _read(client, created["id"])["archived_at"] == first.json()["archived_at"]


# --- DoD-11: an administrator is an account too -----------------------------------------


def test_an_administrator_owns_its_own_characters__DoD11(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-11 — D6: any authenticated account owns characters, scoped by its own id."""
    admin_client = _administrator(application, db_settings)
    player_client = _player_a(application, db_settings)
    players = _created(player_client, "Aria", "# Aria")

    created = _created(admin_client, "Keeper", "# Keeper")
    _assert_wire_shape(created)

    admin_ids = _ids(_listing(admin_client))
    assert created["id"] in admin_ids
    assert players["id"] not in admin_ids
    assert created["id"] not in _ids(_listing(player_client))


# --- DoD-12: a non-numeric path id -------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [_item_path("abc"), _action_path("abc", "archive")],
    ids=["read", "archive"],
)
def test_a_non_numeric_path_id_answers_422__DoD12(
    application: FastAPI, db_settings: Settings, path: str
) -> None:
    """DoD-12 — the JSON id boundary: `SnowflakeIn` rejects a non-numeric path id."""
    client = _player_a(application, db_settings)

    response = client.get(path) if path.endswith("abc") else client.post(path)

    assert response.status_code == 422


# --- DoD-13: body keys that cannot be set ------------------------------------------------


def test_create_ignores_user_id_and_archived_at_in_the_body__DoD13(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-13 — D8: the character belongs to the caller and is not born archived."""
    client_a = _player_a(application, db_settings)
    client_b = _player_b(application, db_settings)

    created = client_a.post(
        LIST_PATH,
        json={
            "name": "Aria",
            "sheet": "# Aria",
            "user_id": str(PLAYER_B_ID),
            "archived_at": "2020-01-01T00:00:00.000000+00:00",
        },
    )
    assert created.status_code == 201
    body = created.json()
    _assert_wire_shape(body)
    assert body["archived_at"] is None

    assert body["id"] in _ids(_listing(client_a))
    assert _ids(_listing(client_b, include_archived=True)) == []
    assert client_b.get(_item_path(body["id"])).status_code == 404


def test_patch_ignores_user_id_and_archived_at_in_the_body__DoD13(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-13 — D8: a PATCH cannot re-owner a character and cannot archive it."""
    client_a = _player_a(application, db_settings)
    client_b = _player_b(application, db_settings)
    created = _created(client_a, "Aria", "# Aria")

    patched = client_a.patch(
        _item_path(created["id"]),
        json={
            "name": "Bo",
            "user_id": str(PLAYER_B_ID),
            "archived_at": "2020-01-01T00:00:00.000000+00:00",
        },
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["name"] == "Bo"
    assert body["archived_at"] is None

    assert body["id"] in _ids(_listing(client_a))
    assert _ids(_listing(client_b, include_archived=True)) == []
    assert client_b.get(_item_path(created["id"])).status_code == 404
