"""Tests for the whole-database export route — feature 030, step 003.

Covered route: ``GET /api/admin/database/export``, added to the admin database router so that
it inherits that router's router-level ``require_admin`` guard (``003.context.md``).

Every expected value comes from ``docs/plans/030.export-granularities/003.export-routes.md``
(DoD-1, DoD-2, DoD-3, DoD-9, DoD-10), from ``003.context.md`` and from the feature
``context.md`` — §"Routes" (the 200 / ``application/json`` /
``Content-Disposition: attachment; filename="rphelper-<granularity>-<timestamp>.json"``
contract, and "the filename **never** embeds user content: no name, no title, no id") and
§"Granularity boundaries" (the `database` granularity is the one deliberately unscoped read,
admin-only). Bindings come from ``## Skeleton`` in ``status.md`` (step 003: the path, the
handler name ``export_whole_database`` and the attachment shape). Nothing is read from the
implementation.

The three roleplayer routes (DoD-4 .. DoD-8) live in ``test_transfer_router.py``.

The application is always the real factory's (``create_app()``), pinned to the per-test
``tmp_path`` database through ``dependency_overrides[get_settings]``. One admin and one
roleplayer are seeded by raw insert, and each signed-in caller gets its own ``TestClient``
carrying exactly one session cookie. ``conftest.py`` is untouched: every fixture and helper
below is file-local, following ``tests/test_admin_db_router.py``.

Note on DoD-3's wording: ``db/schema.py``'s ``sessions`` table carries no ``title`` column, so
the "distinctive title" is seeded as the session-scope memo body and the session's own id —
both are user content that the opaque filename must not carry either.
"""

import re
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Column, Engine, Table

from app.config import Settings, get_settings
from app.db import schema
from app.main import create_app
from app.roles import Role
from app.services.passwords import hash_password

PREFIX = "/api/admin/database"
EXPORT_PATH = f"{PREFIX}/export"
TABLES_PATH = f"{PREFIX}/tables"
LOGIN_PATH = "/api/auth/login"

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

BASE = 1_152_921_504_606_847_000

ADMIN_ID = BASE + 1
PLAYER_ID = BASE + 2
CHARACTER_ID = BASE + 10
SESSION_ID = BASE + 11
MEMO_ID = BASE + 12

ADMIN_NAME = "founder"
ADMIN_PASSWORD = "correct horse battery staple"
PLAYER_NAME = "wanderer"
PLAYER_PASSWORD = "a quiet river at dusk"

#: DoD-3 — distinctive user content that the opaque filename must never carry.
CHARACTER_NAME = "Zephyrine Quillhaven-XQ7"
SESSION_TITLE = "Nightfall over Brassgate-VV9"

EXPORT_FORMAT = "rphelper-export"
NOT_AUTHENTICATED = "not_authenticated"
INSUFFICIENT_ROLE = "insufficient_role"


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


def _seed(engine: Engine) -> None:
    with engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(
        engine, user_id=ADMIN_ID, username=ADMIN_NAME, password=ADMIN_PASSWORD, role=Role.ADMIN
    )
    _insert_user(
        engine, user_id=PLAYER_ID, username=PLAYER_NAME, password=PLAYER_PASSWORD, role=Role.ROLEPLAYER
    )
    _insert(
        engine,
        schema.characters,
        id=CHARACTER_ID,
        user_id=PLAYER_ID,
        name=CHARACTER_NAME,
        sheet="",
        archived_at=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )
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
        body=SESSION_TITLE,
        is_enabled=True,
        is_forced=False,
        sort_key=100,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database with the registry applied, two accounts and one seeded tree."""
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


def _administrator(application: FastAPI, settings: Settings) -> TestClient:
    return _as(application, settings, ADMIN_NAME, ADMIN_PASSWORD)


def _player(application: FastAPI, settings: Settings) -> TestClient:
    return _as(application, settings, PLAYER_NAME, PLAYER_PASSWORD)


# --- envelope / registry helpers ------------------------------------------------------


def _table(name: str) -> Table:
    return schema.metadata.tables[name]


def _is_id_column(column: Column[Any]) -> bool:
    """`context.md` §"Row serialization rules" — the three arms of the id-column rule."""
    return bool(
        column.primary_key or column.foreign_keys or column.name == "id" or column.name.endswith("_id")
    )


def _assert_envelope(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error, dict)
    assert error["code"] == code
    return body


def _export(response: httpx.Response) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].split(";")[0] == "application/json"
    envelope = response.json()
    assert isinstance(envelope, dict)
    return envelope


# --- DoD-1: the admin download --------------------------------------------------------


def test_an_admin_export_answers_200_with_the_database_envelope__S030_003_DoD1(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-1 — US-077.AC-1: 200, `application/json`, and a body that parses to an envelope with
    `format` "rphelper-export" and `granularity` "database"."""
    client = _administrator(application, db_settings)

    envelope = _export(client.get(EXPORT_PATH))

    assert envelope["format"] == EXPORT_FORMAT
    assert envelope["granularity"] == "database"


def test_the_database_envelope_carries_the_whole_instances_rows__S030_003_DoD1(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-1 — the one deliberately unscoped read: the admin's export carries the roleplayer's
    seeded character and session, which belong to nobody the caller owns."""
    client = _administrator(application, db_settings)

    envelope = _export(client.get(EXPORT_PATH))

    payload = envelope["payload"]
    assert isinstance(payload, dict)
    assert {row["id"] for row in payload["characters"]} == {str(CHARACTER_ID)}
    assert {row["id"] for row in payload["sessions"]} == {str(SESSION_ID)}


# --- DoD-2: the inherited admin guard -------------------------------------------------


def test_a_roleplayer_is_refused_with_403_insufficient_role__S030_003_DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — the route inherits the router-level `require_admin`: a signed-in roleplayer gets
    403 `insufficient_role` in the standard envelope."""
    client = _player(application, db_settings)

    response = client.get(EXPORT_PATH)

    _assert_envelope(response, 403, INSUFFICIENT_ROLE)


def test_an_unauthenticated_request_is_refused_with_401__S030_003_DoD2(application: FastAPI) -> None:
    """DoD-2 — without a session cookie the route answers 401 `not_authenticated` in the
    standard envelope."""
    response = _anonymous(application).get(EXPORT_PATH)

    _assert_envelope(response, 401, NOT_AUTHENTICATED)


def test_a_refused_export_carries_no_envelope_and_no_attachment__S030_003_DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — a refusal is only the error envelope: no payload leaks and no download is
    offered to a caller the guard turned away."""
    for response in (_player(application, db_settings).get(EXPORT_PATH), _anonymous(application).get(EXPORT_PATH)):
        assert EXPORT_FORMAT not in response.text
        assert CHARACTER_NAME not in response.text
        assert "attachment" not in response.headers.get("content-disposition", "")


# --- DoD-3: the attachment header is opaque -------------------------------------------


def test_the_attachment_names_the_database_granularity_and_no_user_content__S030_003_DoD3(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-3 — US-078 opacity: `attachment; filename="rphelper-database-<timestamp>.json"`, and
    the seeded character name, session memo body and ids appear nowhere in the header."""
    client = _administrator(application, db_settings)

    response = client.get(EXPORT_PATH)

    _export(response)
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment")
    match = re.match(r'^attachment; filename="rphelper-database-(?P<timestamp>[^"/\\]+)\.json"$', disposition)
    assert match is not None, disposition
    assert any(character.isdigit() for character in match.group("timestamp")), disposition
    for secret in (CHARACTER_NAME, SESSION_TITLE, ADMIN_NAME, PLAYER_NAME):
        assert secret not in disposition
        assert secret.lower() not in disposition.lower()
    for identifier in (ADMIN_ID, PLAYER_ID, CHARACTER_ID, SESSION_ID, MEMO_ID):
        assert str(identifier) not in disposition


# --- DoD-9: ids are strings on the wire -----------------------------------------------


def test_every_id_in_the_response_body_is_a_json_string__S030_003_DoD9(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-9 — the JSON id boundary holds through the raw `Response`: every id column of every
    exported row is a decimal string, or null."""
    client = _administrator(application, db_settings)

    envelope = _export(client.get(EXPORT_PATH))

    payload = envelope["payload"]
    checked = 0
    for table_name, rows in payload.items():
        table = _table(table_name)
        for row in rows:
            for column in table.columns:
                if not _is_id_column(column):
                    continue
                value = row[column.name]
                if value is None:
                    continue
                assert isinstance(value, str), (table_name, column.name, value)
                assert value.isdigit(), (table_name, column.name, value)
                checked += 1
    assert checked > 0


def test_the_export_route_declares_no_path_or_query_parameter__S030_003_DoD9(application: FastAPI) -> None:
    """DoD-9 — like `GET /tables`, the whole-database export takes no id at all, so no path or
    query parameter can be malformed."""
    operation = application.openapi()["paths"][EXPORT_PATH]["get"]

    assert operation.get("parameters", []) == []


# --- DoD-10: the earlier routes still answer ------------------------------------------


def test_the_drift_report_route_still_answers_with_the_export_route_added__S030_003_DoD10(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-10 — one smoke request: `GET /api/admin/database/tables` is unaffected by the fourth
    route on the same router."""
    client = _administrator(application, db_settings)

    response = client.get(TABLES_PATH)

    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"tables"}
    assert isinstance(body["tables"], list)
    assert body["tables"]
