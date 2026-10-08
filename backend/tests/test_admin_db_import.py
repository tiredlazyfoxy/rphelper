"""Tests for the whole-database import route — feature 031, step 005.

Covered route: ``POST /api/admin/database/import``, added to the admin database router so that
it inherits that router's router-level ``require_admin`` guard (``005.context.md``).

Every expected value comes from ``docs/plans/031.import-and-id-remapping/005.import-routes.md``
(its Interface intent and DoD-6, DoD-8, DoD-9, DoD-10, DoD-11), from ``005.context.md``
(§"Why 204 + cookie clear on the database import", and the rule that **every envelope a router
test posts is fetched from one of 030's ``GET`` export routes in the same test**, with
"from another instance" meaning a second temp database) and from the feature ``context.md`` —
§"Wire contract" (``204`` and the session cookie cleared; the standard
``{"error": {code, message, detail}}`` failure body), §"The failure contract" (``export_invalid``
is 400 with ``detail`` exactly ``{"reason": …}``; ``database_not_empty`` is 409 with ``{}``),
§"Database import" (allowed only when the instance has no users, or exactly one user whose role
is admin — otherwise nothing changes) and §"Transport" (a body that is not a JSON object is
FastAPI's own 422, the ``{"detail": [...]}`` shape and not the error envelope). Bindings come
from ``## Skeleton`` in ``status.md`` (step 005: the path, the 204 status, no response model,
and ``clear_session_cookie(response, settings)`` as the cookie writer; step 001 for the two
error codes and the reason vocabulary). Nothing is read from the implementation.

The two roleplayer import routes (DoD-1 .. DoD-7) live in ``test_transfer_import_router.py``.

The application is always the real factory's (``create_app()``), pinned to the per-test
``tmp_path`` database through ``dependency_overrides[get_settings]``. Two primary instances are
offered as fixtures: an **eligible** one holding a single administrator and nothing else, and an
**occupied** one holding that administrator plus a roleplayer with a small tree. The second
instance DoD-8 needs is a ``db_settings.model_copy`` pointing at another directory inside the
same ``tmp_path``, reached through a temporary ``dependency_overrides[get_connection]`` while its
export is fetched — the idiom ``tests/test_admin_db_router.py`` already uses. ``conftest.py`` is
untouched: every fixture and helper below is file-local, following
``tests/test_admin_db_export.py``.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, Table

from app.config import Settings, get_settings
from app.db import schema
from app.db.engine import get_connection, get_engine
from app.main import create_app
from app.roles import Role
from app.services.passwords import hash_password

PREFIX = "/api/admin/database"
TABLES_PATH = f"{PREFIX}/tables"
EXPORT_PATH = f"{PREFIX}/export"
IMPORT_PATH = f"{PREFIX}/import"
LOGIN_PATH = "/api/auth/login"

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

BASE = 1_152_921_504_606_847_000

ADMIN_ID = BASE + 1
PLAYER_ID = BASE + 2
CHARACTER_ID = BASE + 10
SESSION_ID = BASE + 11
MEMO_ID = BASE + 12

#: The second instance's accounts (DoD-8: "another instance"), on their own ids.
OTHER_ADMIN_ID = BASE + 100
OTHER_PLAYER_ID = BASE + 101
OTHER_CHARACTER_ID = BASE + 110

ADMIN_NAME = "founder"
ADMIN_PASSWORD = "correct horse battery staple"
PLAYER_NAME = "wanderer"
PLAYER_PASSWORD = "a quiet river at dusk"

OTHER_ADMIN_NAME = "steward"
OTHER_ADMIN_PASSWORD = "nine lanterns on the pier"
OTHER_PLAYER_NAME = "ferryman"
OTHER_PLAYER_PASSWORD = "salt and lantern light"

#: `005.import-routes.md` DoD-6 — a body that is a JSON object but not an export.
NOT_AN_EXPORT_BODY = {"format": "nope"}

#: `context.md` §"Transport" — a body that is not a JSON object at all.
ARRAY_BODY = ["not", "an", "object"]

EXPORT_INVALID = "export_invalid"
DATABASE_NOT_EMPTY = "database_not_empty"
NOT_AUTHENTICATED = "not_authenticated"
INSUFFICIENT_ROLE = "insufficient_role"

REASON_NOT_AN_EXPORT = "not_an_export"


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


def _create_registry(engine: Engine) -> None:
    with engine.begin() as connection:
        schema.metadata.create_all(connection)


def _seed_eligible(engine: Engine) -> None:
    """`context.md` §"Database import": exactly one user, whose role is admin."""
    _create_registry(engine)
    _insert_user(engine, user_id=ADMIN_ID, username=ADMIN_NAME, password=ADMIN_PASSWORD, role=Role.ADMIN)


def _seed_occupied(engine: Engine) -> None:
    """The admin plus a second account — the instance DoD-9 refuses to replace."""
    _seed_eligible(engine)
    _insert_user(
        engine, user_id=PLAYER_ID, username=PLAYER_NAME, password=PLAYER_PASSWORD, role=Role.ROLEPLAYER
    )
    _insert_character(engine, character_id=CHARACTER_ID, user_id=PLAYER_ID, name="Zephyrine Quillhaven")
    _insert(
        engine,
        schema.sessions,
        id=SESSION_ID,
        user_id=PLAYER_ID,
        character_id=CHARACTER_ID,
        setup_id=None,
        archived_at=None,
        last_used_at=TIMESTAMP,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )
    _insert(
        engine,
        schema.memos,
        id=MEMO_ID,
        user_id=PLAYER_ID,
        scope="session",
        scope_id=SESSION_ID,
        body="Nightfall over Brassgate.",
        is_enabled=True,
        is_forced=False,
        sort_key=100,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


@pytest.fixture
def eligible_engine(db_engine: Engine) -> Engine:
    """A per-test database holding the registry and one administrator only."""
    _seed_eligible(db_engine)
    return db_engine


@pytest.fixture
def occupied_engine(db_engine: Engine) -> Engine:
    """A per-test database holding the registry, the administrator and a second account."""
    _seed_occupied(db_engine)
    return db_engine


def _pinned_application(db_settings: Settings) -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: db_settings
    return app


@pytest.fixture
def eligible_application(db_settings: Settings, eligible_engine: Engine) -> Iterator[FastAPI]:
    """The factory's application, pinned to the single-administrator database."""
    app = _pinned_application(db_settings)
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def occupied_application(db_settings: Settings, occupied_engine: Engine) -> Iterator[FastAPI]:
    """The factory's application, pinned to the two-account database."""
    app = _pinned_application(db_settings)
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


def _client_with_token(application: FastAPI, settings: Settings, token: str) -> TestClient:
    fresh = TestClient(application)
    fresh.cookies.set(settings.session_cookie_name, token)
    return fresh


def _as(application: FastAPI, settings: Settings, username: str, password: str) -> TestClient:
    """A fresh client carrying exactly this account's session cookie — never shared."""
    return _client_with_token(
        application, settings, _login_token(application, settings, username, password)
    )


def _admin(application: FastAPI, settings: Settings) -> TestClient:
    return _as(application, settings, ADMIN_NAME, ADMIN_PASSWORD)


def _player(application: FastAPI, settings: Settings) -> TestClient:
    return _as(application, settings, PLAYER_NAME, PLAYER_PASSWORD)


def _anonymous(application: FastAPI) -> TestClient:
    return TestClient(application)


# --- the second instance (DoD-8) -----------------------------------------------------


def _other_instance(db_settings: Settings, tmp_path: Path) -> Engine:
    """A second temp database inside the same ``tmp_path``, with its own accounts and tree."""
    other_settings = db_settings.model_copy(
        update={"data_dir": tmp_path / "other-instance", "db_filename": "other.sqlite"}
    )
    engine = get_engine(other_settings)
    _create_registry(engine)
    _insert_user(
        engine,
        user_id=OTHER_ADMIN_ID,
        username=OTHER_ADMIN_NAME,
        password=OTHER_ADMIN_PASSWORD,
        role=Role.ADMIN,
    )
    _insert_user(
        engine,
        user_id=OTHER_PLAYER_ID,
        username=OTHER_PLAYER_NAME,
        password=OTHER_PLAYER_PASSWORD,
        role=Role.ROLEPLAYER,
    )
    _insert_character(
        engine, character_id=OTHER_CHARACTER_ID, user_id=OTHER_PLAYER_ID, name="Thessaly of the Weir"
    )
    return engine


def _envelope_from_other_instance(
    application: FastAPI, settings: Settings, other: Engine
) -> dict[str, Any]:
    """`005.context.md`: the envelope is fetched from 030's own `GET` route, on that instance."""

    def other_connection() -> Iterator[Connection]:
        connection = other.connect()
        try:
            yield connection
        finally:
            connection.close()

    application.dependency_overrides[get_connection] = other_connection
    try:
        other_admin = _as(application, settings, OTHER_ADMIN_NAME, OTHER_ADMIN_PASSWORD)
        return _database_envelope(other_admin)
    finally:
        application.dependency_overrides.pop(get_connection, None)


# --- envelope and response assertions ------------------------------------------------


def _database_envelope(client: TestClient) -> dict[str, Any]:
    response = client.get(EXPORT_PATH)
    assert response.status_code == 200, response.text
    envelope = response.json()
    assert isinstance(envelope, dict)
    assert envelope["granularity"] == "database"
    return envelope


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


def _assert_native_422(response: httpx.Response) -> None:
    """`context.md` §"Transport" — FastAPI's own 422, not the error envelope."""
    assert response.status_code == 422, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert "error" not in body, body
    assert "detail" in body, body


def _assert_clears_the_session_cookie(response: httpx.Response, settings: Settings) -> None:
    """`## Skeleton` step 005 — `clear_session_cookie(response, settings)` is applied to the 204."""
    headers = [
        header
        for header in response.headers.get_list("set-cookie")
        if _parse_set_cookie(header)[0] == settings.session_cookie_name
    ]
    assert len(headers) == 1, response.headers
    header = headers[0]
    assert _parse_set_cookie(header)[1] == "", header
    lowered = header.lower()
    assert "max-age=0" in lowered or "expires=" in lowered, header


# =========================================================================== DoD-8


def test_an_export_from_another_instance_replaces_the_database_and_signs_me_out__S031_005_DoD8(
    eligible_application: FastAPI, db_settings: Settings, tmp_path: Path
) -> None:
    """DoD-8 — US-077.AC-2: the only administrator posts a `database` export taken from another
    instance. The answer is 204 with an empty body and a `Set-Cookie` that clears the session
    cookie; the old cookie then answers 401; and a restored account logs in with its original
    password."""
    other = _other_instance(db_settings, tmp_path)
    envelope = _envelope_from_other_instance(eligible_application, db_settings, other)

    token = _login_token(eligible_application, db_settings, ADMIN_NAME, ADMIN_PASSWORD)
    admin = _client_with_token(eligible_application, db_settings, token)

    response = admin.post(IMPORT_PATH, json=envelope)

    assert response.status_code == 204, response.text
    assert response.content == b""
    _assert_clears_the_session_cookie(response, db_settings)

    replayed = _client_with_token(eligible_application, db_settings, token)
    _assert_error(replayed.get(TABLES_PATH), 401, NOT_AUTHENTICATED)

    restored_token = _login_token(
        eligible_application, db_settings, OTHER_PLAYER_NAME, OTHER_PLAYER_PASSWORD
    )
    assert restored_token


# =========================================================================== DoD-9


def test_a_second_account_makes_the_replace_refuse_with_409_and_wipe_nothing__S031_005_DoD9(
    occupied_application: FastAPI, db_settings: Settings
) -> None:
    """DoD-9 — with a second user present the replace answers 409 `database_not_empty` with an
    empty `detail`, and the administrator's next authenticated request still succeeds, which is
    what shows nothing was wiped."""
    admin = _admin(occupied_application, db_settings)
    envelope = _database_envelope(admin)

    error = _assert_error(admin.post(IMPORT_PATH, json=envelope), 409, DATABASE_NOT_EMPTY)
    assert error["detail"] == {}, error

    after = admin.get(TABLES_PATH)
    assert after.status_code == 200, after.text
    assert isinstance(after.json(), dict)


# =========================================================================== DoD-10


def test_a_roleplayer_is_refused_with_403__S031_005_DoD10(
    occupied_application: FastAPI, db_settings: Settings
) -> None:
    """DoD-10 — the route inherits the router-level admin guard, so a roleplayer posting a valid
    `database` envelope answers 403 `insufficient_role`."""
    envelope = _database_envelope(_admin(occupied_application, db_settings))

    _assert_error(
        _player(occupied_application, db_settings).post(IMPORT_PATH, json=envelope),
        403,
        INSUFFICIENT_ROLE,
    )


def test_an_anonymous_caller_is_refused_with_401__S031_005_DoD10(
    occupied_application: FastAPI, db_settings: Settings
) -> None:
    """DoD-10 — without a session cookie the route answers 401 `not_authenticated`; the guard runs
    before the body is looked at."""
    envelope = _database_envelope(_admin(occupied_application, db_settings))

    _assert_error(
        _anonymous(occupied_application).post(IMPORT_PATH, json=envelope), 401, NOT_AUTHENTICATED
    )


# =========================================================================== DoD-6


def test_a_body_that_is_not_an_export_answers_not_an_export_on_an_eligible_instance__S031_005_DoD6(
    eligible_application: FastAPI, db_settings: Settings
) -> None:
    """DoD-6 — on an eligible instance (so the 409 guard cannot answer first), `{"format": "nope"}`
    answers 400 `export_invalid` with `detail` exactly `{"reason": "not_an_export"}`."""
    admin = _admin(eligible_application, db_settings)

    error = _assert_error(admin.post(IMPORT_PATH, json=NOT_AN_EXPORT_BODY), 400, EXPORT_INVALID)
    assert error["detail"] == {"reason": REASON_NOT_AN_EXPORT}, error


def test_a_json_array_body_answers_a_native_422__S031_005_DoD6(
    eligible_application: FastAPI, db_settings: Settings
) -> None:
    """DoD-6 — the raw-object body parameter makes a JSON array FastAPI's own 422, with the
    `{"detail": [...]}` shape and not the `{"error": ...}` envelope."""
    _assert_native_422(_admin(eligible_application, db_settings).post(IMPORT_PATH, json=ARRAY_BODY))


# =========================================================================== DoD-11


def test_the_admin_drift_report_route_still_answers_200__S031_005_DoD11(
    eligible_application: FastAPI, db_settings: Settings
) -> None:
    """DoD-11 — regression smoke: `GET /api/admin/database/tables` is untouched by this step."""
    response = _admin(eligible_application, db_settings).get(TABLES_PATH)

    assert response.status_code == 200, response.text
    assert isinstance(response.json(), dict)
