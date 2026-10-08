"""Tests for the two roleplayer import routes — feature 031, step 005.

Covered routes: ``POST /api/import`` and ``POST /api/characters/{character_id}/import``, both
added to 030's ``routers/transfer.py`` so that they inherit its router-level ``require_user``
guard.

Every expected value comes from ``docs/plans/031.import-and-id-remapping/005.import-routes.md``
(its Interface intent and DoD-1 .. DoD-7, DoD-11), from ``005.context.md`` (why the bodies are
raw JSON objects, and the rule that **every envelope a router test posts is fetched from one of
030's ``GET`` export routes in the same test** — these tests never hand-build a valid envelope)
and from the feature ``context.md`` — §"Wire contract" (the two 200 bodies, ``character_ids``
ascending and as decimal strings, and "a foreign or missing target character answers
``character_not_found`` (404) … R5 applies: no 403, and no leak of whether the character
exists"), §"The failure contract" (``export_invalid`` is 400 with ``detail`` exactly
``{"reason": <one of five>}``), §"Remap rules …" (every payload row gets a fresh snowflake) and
§"Transport" (a body that is not a JSON object is refused with FastAPI's own 422 before any
service runs — the ``{"detail": [...]}`` shape, **not** the ``{"error": ...}`` envelope, because
no ``RequestValidationError`` handler is registered). Bindings come from ``## Skeleton`` in
``status.md`` (step 005: the two paths, their 200 status codes and the two response models;
step 001 for the error codes and reasons). Nothing is read from the implementation.

The admin route ``POST /api/admin/database/import`` (DoD-8 .. DoD-10) lives in
``test_admin_db_import.py``.

The application is always the real factory's (``create_app()``), pinned to the per-test
``tmp_path`` database through ``dependency_overrides[get_settings]``. Each signed-in caller gets
its own ``TestClient`` carrying exactly one session cookie, so no cookie leaks between accounts.
``conftest.py`` is untouched: every fixture and helper below is file-local, following
``tests/test_transfer_router.py`` and ``tests/test_characters_router.py``.

Owner A has **two** characters, so a ``user`` export carries two of them: one with a setup, a
session on that setup, a message and a memo at each of the four scopes, and a bare second
character. Owner B has a character and a session of their own, which give DoD-4 its foreign
target. One administrator is seeded as well, for the single purpose of fetching a real
``database``-granularity envelope from ``GET /api/admin/database/export`` for DoD-5's third
case. Ids are all above 2**60.
"""

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, Table

from app.config import Settings, get_settings
from app.db import schema
from app.main import create_app
from app.roles import Role
from app.services.passwords import hash_password

CHARACTERS_PATH = "/api/characters"
SESSIONS_PATH = "/api/sessions"
USER_EXPORT_PATH = "/api/export"
DATABASE_EXPORT_PATH = "/api/admin/database/export"
OWNED_IMPORT_PATH = "/api/import"
LOGIN_PATH = "/api/auth/login"

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

BASE = 1_152_921_504_606_847_000

ADMIN_ID = BASE + 1
USER_A = BASE + 2
USER_B = BASE + 3

CHAR_A1 = BASE + 10
CHAR_A2 = BASE + 11
CHAR_B = BASE + 12

SETUP_A = BASE + 20

SESSION_A = BASE + 30
SESSION_B = BASE + 31

MSG_A = BASE + 40
MSG_B = BASE + 41

MEMO_A_USER = BASE + 50
MEMO_A_CHARACTER = BASE + 51
MEMO_A_SETUP = BASE + 52
MEMO_A_SESSION = BASE + 53

#: An id that exists for nobody (DoD-4: indistinguishable from another owner's id).
UNKNOWN_CHARACTER_ID = BASE + 900_001

ADMIN_NAME = "founder"
ADMIN_PASSWORD = "correct horse battery staple"
PLAYER_A_NAME = "aster"
PLAYER_A_PASSWORD = "a quiet river at dusk"
PLAYER_B_NAME = "briar"
PLAYER_B_PASSWORD = "salt and lantern light"

#: `005.import-routes.md` DoD-6 — the body that is a JSON object but not an export.
NOT_AN_EXPORT_BODY = {"format": "nope"}

#: `005.context.md` / `context.md` §"Transport" — a body that is not a JSON object.
ARRAY_BODY = ["not", "an", "object"]

EXPORT_INVALID = "export_invalid"
NOT_AUTHENTICATED = "not_authenticated"
CHARACTER_NOT_FOUND = "character_not_found"

REASON_NOT_AN_EXPORT = "not_an_export"
REASON_WRONG_GRANULARITY = "wrong_granularity"

#: `## Skeleton` step 005 — the whole 200 body of each route.
OWNED_IMPORT_KEYS = {"granularity", "character_ids"}
SESSION_IMPORT_KEYS = {"session_id"}


# --- fixtures ------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _quiet_factory_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the factory's logging call so these tests touch no global sinks."""
    monkeypatch.setattr("app.main.configure_logging", lambda settings: None)


def _insert(engine: Engine, table: Table, **values: Any) -> None:
    with engine.begin() as connection:
        connection.execute(table.insert().values(**values))


def _insert_user(engine: Engine, *, user_id: int, username: str, password: str, role: Role) -> None:
    _insert(
        engine,
        schema.users,
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


def _insert_character(engine: Engine, *, character_id: int, user_id: int, name: str) -> None:
    _insert(
        engine,
        schema.characters,
        id=character_id,
        user_id=user_id,
        name=name,
        sheet="",
        archived_at=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_setup(engine: Engine, *, setup_id: int, user_id: int, character_id: int, name: str) -> None:
    _insert(
        engine,
        schema.setups,
        id=setup_id,
        user_id=user_id,
        character_id=character_id,
        name=name,
        description="",
        archived_at=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_session(
    engine: Engine, *, session_id: int, user_id: int, character_id: int, setup_id: int | None = None
) -> None:
    _insert(
        engine,
        schema.sessions,
        id=session_id,
        user_id=user_id,
        character_id=character_id,
        setup_id=setup_id,
        archived_at=None,
        last_used_at=TIMESTAMP,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_message(engine: Engine, *, message_id: int, user_id: int, session_id: int, text: str) -> None:
    _insert(
        engine,
        schema.messages,
        id=message_id,
        user_id=user_id,
        session_id=session_id,
        role="user",
        kind=None,
        text=text,
        related_to=None,
        settled_at=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_memo(engine: Engine, *, memo_id: int, user_id: int, scope: str, scope_id: int, body: str) -> None:
    _insert(
        engine,
        schema.memos,
        id=memo_id,
        user_id=user_id,
        scope=scope,
        scope_id=scope_id,
        body=body,
        is_enabled=True,
        is_forced=False,
        sort_key=100,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _seed(engine: Engine) -> None:
    with engine.begin() as connection:
        schema.metadata.create_all(connection)

    _insert_user(engine, user_id=ADMIN_ID, username=ADMIN_NAME, password=ADMIN_PASSWORD, role=Role.ADMIN)
    _insert_user(
        engine, user_id=USER_A, username=PLAYER_A_NAME, password=PLAYER_A_PASSWORD, role=Role.ROLEPLAYER
    )
    _insert_user(
        engine, user_id=USER_B, username=PLAYER_B_NAME, password=PLAYER_B_PASSWORD, role=Role.ROLEPLAYER
    )

    _insert_character(engine, character_id=CHAR_A1, user_id=USER_A, name="Zephyrine Quillhaven")
    _insert_character(engine, character_id=CHAR_A2, user_id=USER_A, name="the understudy")
    _insert_character(engine, character_id=CHAR_B, user_id=USER_B, name="Briar's own")

    _insert_setup(engine, setup_id=SETUP_A, user_id=USER_A, character_id=CHAR_A1, name="The Lantern Wharf")

    _insert_session(engine, session_id=SESSION_A, user_id=USER_A, character_id=CHAR_A1, setup_id=SETUP_A)
    _insert_session(engine, session_id=SESSION_B, user_id=USER_B, character_id=CHAR_B)

    _insert_message(engine, message_id=MSG_A, user_id=USER_A, session_id=SESSION_A, text="A line.")
    _insert_message(engine, message_id=MSG_B, user_id=USER_B, session_id=SESSION_B, text="Briar's line.")

    for memo_id, scope, scope_id, body in (
        (MEMO_A_USER, "user", USER_A, "Everywhere."),
        (MEMO_A_CHARACTER, "character", CHAR_A1, "About Zephyrine."),
        (MEMO_A_SETUP, "setup", SETUP_A, "At the wharf."),
        (MEMO_A_SESSION, "session", SESSION_A, "Nightfall over Brassgate."),
    ):
        _insert_memo(engine, memo_id=memo_id, user_id=USER_A, scope=scope, scope_id=scope_id, body=body)


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database with the registry applied and the three accounts' material seeded."""
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


# --- login helpers -------------------------------------------------------------------


def _parse_set_cookie(header: str) -> tuple[str, str]:
    first = header.split(";")[0]
    name, _, value = first.partition("=")
    return name.strip(), value.strip().strip('"')


def _login_token(application: FastAPI, settings: Settings, username: str, password: str) -> str:
    response = TestClient(application).post(LOGIN_PATH, json={"username": username, "password": password})
    assert response.status_code == 200, response.text
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


def _admin(application: FastAPI, settings: Settings) -> TestClient:
    return _as(application, settings, ADMIN_NAME, ADMIN_PASSWORD)


# --- exact paths ---------------------------------------------------------------------


def _character_export_path(character_id: Any) -> str:
    return f"{CHARACTERS_PATH}/{character_id}/export"


def _session_export_path(session_id: Any) -> str:
    return f"{SESSIONS_PATH}/{session_id}/export"


def _session_import_path(character_id: Any) -> str:
    return f"{CHARACTERS_PATH}/{character_id}/import"


def _character_path(character_id: Any) -> str:
    return f"{CHARACTERS_PATH}/{character_id}"


def _session_path(session_id: Any) -> str:
    return f"{SESSIONS_PATH}/{session_id}"


# --- envelope helpers: every envelope comes from one of 030's GET routes ---------------


def _fetched_envelope(response: httpx.Response, granularity: str) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    envelope = response.json()
    assert isinstance(envelope, dict)
    assert envelope["granularity"] == granularity
    return envelope


def _user_envelope(client: TestClient) -> dict[str, Any]:
    return _fetched_envelope(client.get(USER_EXPORT_PATH), "user")


def _character_envelope(client: TestClient, character_id: Any) -> dict[str, Any]:
    return _fetched_envelope(client.get(_character_export_path(character_id)), "character")


def _session_envelope(client: TestClient, session_id: Any) -> dict[str, Any]:
    return _fetched_envelope(client.get(_session_export_path(session_id)), "session")


def _database_envelope(client: TestClient) -> dict[str, Any]:
    return _fetched_envelope(client.get(DATABASE_EXPORT_PATH), "database")


def _exported_ids(envelope: dict[str, Any], table_name: str) -> set[str]:
    rows = envelope["payload"][table_name]
    assert isinstance(rows, list)
    return {str(row["id"]) for row in rows}


# --- response assertions -------------------------------------------------------------


def _owned_import(response: httpx.Response, granularity: str) -> list[str]:
    """`## Skeleton` step 005 — the whole 200 body of `POST /api/import`."""
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == OWNED_IMPORT_KEYS
    assert body["granularity"] == granularity
    character_ids = body["character_ids"]
    assert isinstance(character_ids, list)
    for value in character_ids:
        assert isinstance(value, str), character_ids
        assert value.isdigit(), character_ids
    # `context.md` §"Wire contract": the new ids, in ascending order.
    assert [int(value) for value in character_ids] == sorted(int(value) for value in character_ids)
    return [str(value) for value in character_ids]


def _session_import(response: httpx.Response) -> str:
    """`## Skeleton` step 005 — the whole 200 body of `POST /api/characters/{id}/import`."""
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == SESSION_IMPORT_KEYS
    session_id = body["session_id"]
    assert isinstance(session_id, str), body
    assert session_id.isdigit(), body
    return session_id


def _assert_error(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    """`context.md` §"Wire contract": the standard `{"error": {code, message, detail}}` body."""
    assert response.status_code == status, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error, dict)
    assert set(error) == {"code", "message", "detail"}
    assert error["code"] == code, error
    assert isinstance(error["message"], str) and error["message"]
    return error


def _assert_export_invalid(response: httpx.Response, reason: str) -> None:
    """Step 001's frozen contract: 400, `export_invalid`, `detail` exactly `{"reason": reason}`."""
    error = _assert_error(response, 400, EXPORT_INVALID)
    assert error["detail"] == {"reason": reason}, error


def _assert_native_422(response: httpx.Response) -> None:
    """`context.md` §"Transport" / harvest E13 — FastAPI's own 422, not the error envelope."""
    assert response.status_code == 422, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert "error" not in body, body
    assert "detail" in body, body


# =========================================================================== DoD-1


def test_posting_my_own_user_export_answers_user_granularity_and_new_character_ids__S031_005_DoD1(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-1 — US-079.AC-2: a `user` export fetched from `GET /api/export` comes back in at 200
    with `granularity` `"user"`, `character_ids` as JSON strings, and each returned id readable
    by the caller."""
    player = _player_a(application, db_settings)
    envelope = _user_envelope(player)
    exported_character_ids = _exported_ids(envelope, "characters")

    character_ids = _owned_import(player.post(OWNED_IMPORT_PATH, json=envelope), "user")

    assert len(character_ids) == len(exported_character_ids)
    # `context.md` §"Remap rules": every payload row gets a fresh snowflake.
    assert set(character_ids).isdisjoint(exported_character_ids)
    for character_id in character_ids:
        read_back = player.get(_character_path(character_id))
        assert read_back.status_code == 200, read_back.text
        assert read_back.json()["id"] == character_id


# =========================================================================== DoD-2


def test_posting_a_character_export_answers_character_granularity_and_one_new_id__S031_005_DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — US-080.AC-2, US-136.AC-2: a `character` export answers `granularity`
    `"character"` and exactly one id, which is not the exported character's."""
    player = _player_a(application, db_settings)
    envelope = _character_envelope(player, CHAR_A1)

    character_ids = _owned_import(player.post(OWNED_IMPORT_PATH, json=envelope), "character")

    assert len(character_ids) == 1, character_ids
    assert character_ids[0] != str(CHAR_A1)


# =========================================================================== DoD-3


def test_posting_a_session_export_under_a_character_answers_the_new_session_id__S031_005_DoD3(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-3 — US-082.AC-1, US-082.AC-2: a `session` export imported under character A2 answers
    `session_id` as a string, and that session reads back under A2 with no setup."""
    player = _player_a(application, db_settings)
    envelope = _session_envelope(player, SESSION_A)

    session_id = _session_import(player.post(_session_import_path(CHAR_A2), json=envelope))

    assert session_id != str(SESSION_A)
    read_back = player.get(_session_path(session_id))
    assert read_back.status_code == 200, read_back.text
    session = read_back.json()
    assert session["id"] == session_id
    assert session["character_id"] == str(CHAR_A2)
    assert session["setup_id"] is None, session


# =========================================================================== DoD-4


def test_a_foreign_or_missing_target_character_answers_the_same_404__S031_005_DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-4 — R5: another owner's character and an id that exists for nobody both answer 404
    `character_not_found`, with the **same** body, so existence never leaks."""
    player = _player_a(application, db_settings)
    envelope = _session_envelope(player, SESSION_A)

    foreign = player.post(_session_import_path(CHAR_B), json=envelope)
    unknown = player.post(_session_import_path(UNKNOWN_CHARACTER_ID), json=envelope)

    foreign_error = _assert_error(foreign, 404, CHARACTER_NOT_FOUND)
    unknown_error = _assert_error(unknown, 404, CHARACTER_NOT_FOUND)
    assert foreign_error == unknown_error


def test_a_non_numeric_target_character_id_answers_a_native_422__S031_005_DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-4 — the path id is the inbound snowflake alias, so a non-numeric id is a 422 before
    the service runs."""
    player = _player_a(application, db_settings)
    envelope = _session_envelope(player, SESSION_A)

    _assert_native_422(player.post(_session_import_path("abc"), json=envelope))


# =========================================================================== DoD-5


def test_a_session_export_posted_to_the_owned_route_is_wrong_granularity__S031_005_DoD5(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-5 — `POST /api/import` accepts `user` and `character` only."""
    player = _player_a(application, db_settings)
    envelope = _session_envelope(player, SESSION_A)

    _assert_export_invalid(player.post(OWNED_IMPORT_PATH, json=envelope), REASON_WRONG_GRANULARITY)


def test_a_character_export_posted_to_the_session_route_is_wrong_granularity__S031_005_DoD5(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-5 — `POST /api/characters/{C}/import` accepts `session` only."""
    player = _player_a(application, db_settings)
    envelope = _character_envelope(player, CHAR_A1)

    _assert_export_invalid(
        player.post(_session_import_path(CHAR_A2), json=envelope), REASON_WRONG_GRANULARITY
    )


def test_a_database_envelope_is_wrong_granularity_on_both_roleplayer_routes__S031_005_DoD5(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-5 — the `database` granularity is accepted by the admin route only. The envelope is
    the real one from `GET /api/admin/database/export`."""
    envelope = _database_envelope(_admin(application, db_settings))
    player = _player_a(application, db_settings)

    _assert_export_invalid(player.post(OWNED_IMPORT_PATH, json=envelope), REASON_WRONG_GRANULARITY)
    _assert_export_invalid(
        player.post(_session_import_path(CHAR_A2), json=envelope), REASON_WRONG_GRANULARITY
    )


# =========================================================================== DoD-6


def test_a_body_that_is_not_an_export_answers_not_an_export_on_both_routes__S031_005_DoD6(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-6 — `{"format": "nope"}` answers 400 `export_invalid` with `detail` exactly
    `{"reason": "not_an_export"}`."""
    player = _player_a(application, db_settings)

    _assert_export_invalid(player.post(OWNED_IMPORT_PATH, json=NOT_AN_EXPORT_BODY), REASON_NOT_AN_EXPORT)
    _assert_export_invalid(
        player.post(_session_import_path(CHAR_A2), json=NOT_AN_EXPORT_BODY), REASON_NOT_AN_EXPORT
    )


def test_a_json_array_body_answers_a_native_422_on_both_routes__S031_005_DoD6(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-6 — the raw-object body parameter makes a JSON array FastAPI's own 422, with the
    `{"detail": [...]}` shape and not the `{"error": ...}` envelope."""
    player = _player_a(application, db_settings)

    _assert_native_422(player.post(OWNED_IMPORT_PATH, json=ARRAY_BODY))
    _assert_native_422(player.post(_session_import_path(CHAR_A2), json=ARRAY_BODY))


# =========================================================================== DoD-7


def test_both_roleplayer_routes_refuse_an_anonymous_caller_with_401__S031_005_DoD7(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-7 — without a session cookie both routes answer 401 `not_authenticated`; the guard
    runs before the body is even looked at."""
    envelope = _session_envelope(_player_a(application, db_settings), SESSION_A)
    anonymous = _anonymous(application)

    _assert_error(anonymous.post(OWNED_IMPORT_PATH, json=envelope), 401, NOT_AUTHENTICATED)
    _assert_error(
        anonymous.post(_session_import_path(CHAR_A2), json=envelope), 401, NOT_AUTHENTICATED
    )


# =========================================================================== DoD-11


def test_the_three_export_routes_still_answer_200__S031_005_DoD11(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-11 — regression smoke: 030's three roleplayer `GET` export routes are untouched."""
    player = _player_a(application, db_settings)

    assert player.get(USER_EXPORT_PATH).status_code == 200
    assert player.get(_character_export_path(CHAR_A1)).status_code == 200
    assert player.get(_session_export_path(SESSION_A)).status_code == 200
    assert _user_envelope(player)["granularity"] == "user"
    assert _character_envelope(player, CHAR_A1)["granularity"] == "character"
    assert _session_envelope(player, SESSION_A)["granularity"] == "session"
