"""Tests for the admin database router: ``/api/admin/database`` and its routes.

Feature 007, step 004 (``004.admin-database-router.md``). Every expected value comes from that
step's Interface intent and DoD-1 .. DoD-14, ``004.context.md`` and feature 007 ``context.md``
(D1 what a difference is, D2 the three statuses, D4 the two operations' postconditions, D5 what
a Sync preserves, D8 foreign keys during a rebuild, D9 the two error codes and the route table,
R5 no count anywhere). Bindings come from ``## Skeleton`` in feature 007's ``status.md``
(steps 001 .. 004): the wire keys, the three route paths, the handler names, and the
module-level names ``build_drift_report`` / ``create_table`` / ``sync_table`` / ``metadata`` the
router holds.

The application is always the real factory's (``create_app()``), built locally and never as a
context manager, pinned to the per-test database through ``dependency_overrides[get_settings]``.
The real registry (``users``, ``auth_sessions``, ``llm_servers``, ``models``) is created with
``metadata.create_all`` and then hand-drifted with raw DDL; the registry itself is never edited.
``users`` and ``auth_sessions`` must exist for login to work, so "missing" is manufactured by
dropping ``models``.

Tests are suffixed ``__DoD<n>``. DoD-15 .. DoD-18 are ``[manual/live]``.

Amended by feature 030, step 003 (``003.export-routes.md``, DoD-1), an approved deviation
recorded in 030's ``status.md``. That step adds a fourth route to this router, ``GET
/api/admin/database/export``, so the whole-database export inherits the router-level
``require_admin`` guard. Every amendment is cited inline with ``S030_003_DoD1`` (or
``S030_003_DoD10`` where it is the route-count guard) next to what changed:
``EXPECTED_OPERATIONS`` gains the operation, the no-path-parameter branch widens, and the
two DoD-14 scope guards are **narrowed** to admit that one route. They are not disarmed:
``rebuild``, ``import``, ``vector`` and ``vec0`` remain rejected across the whole surface,
and ``POST .../export`` remains rejected, because 031 owns Import and ``fast/002`` owns
Rebuild and neither may appear early. No behavioural assertion about the three original
routes changed.

Amended by fast feature 002 (``docs/plans/fast/002.vector-index-rebuild/plan.md``, DoD-22,
amendment 2026-10-07). That feature adds ``POST /api/admin/database/rebuild`` to this router,
deliberately overturning the earlier "no rebuild surface" rule. Every amendment is cited
inline with ``F002_DoD22``: ``EXPECTED_OPERATIONS`` gains the operation, the no-path-parameter
branch widens, the DoD-14 surface guard admits ``rebuild`` on that single operation only
(``vector`` and ``vec0`` stay rejected everywhere), the documentation guard skips that one
operation, and ``POST .../rebuild`` leaves the out-of-scope list. No other assertion changed.
"""

import ast
import inspect
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, MetaData, event, text

import app.routers.admin_db as admin_db_module
from app.config import Settings, get_settings
from app.db import schema
from app.db.drift import TableReport, TableStatus, build_drift_report
from app.db.engine import get_connection, get_engine
from app.db.sync import create_table, sync_table
from app.main import create_app
from app.models.admin_db import DriftReportResponse, TableReportResponse
from app.roles import Role
from app.routers.admin_db import router as admin_db_router
from app.services.passwords import hash_password

PREFIX = "/api/admin/database"
TABLES_PATH = f"{PREFIX}/tables"
LOGIN_PATH = "/api/auth/login"

GUARD_PROBE_PATH = "/guard-probe"
GUARD_PROBE_FULL_PATH = f"{PREFIX}/guard-probe"

CREATED_TEXT = "2026-01-01T00:00:00+00:00"
EXPIRES_TEXT = "2099-01-01T00:00:00+00:00"

ADMIN_ID = 9_000_001
ADMIN_NAME = "founder"
ADMIN_PASSWORD = "correct horse battery staple"

PLAYER_ID = 9_000_002
PLAYER_NAME = "wanderer"
PLAYER_PASSWORD = "a quiet river at dusk"

STATUS_VALUES = {"in_sync", "missing", "drifted"}
TABLE_REPORT_KEYS = {
    "table_name",
    "status",
    "missing_columns",
    "extra_columns",
    "changed_columns",
    "missing_indexes",
    "extra_indexes",
}
DIFFERENCE_LISTS = ("missing_columns", "extra_columns", "changed_columns", "missing_indexes", "extra_indexes")
COLUMN_SHAPE_KEYS = {"name", "type_text", "not_null"}
INDEX_SHAPE_KEYS = {"columns", "unique"}
CHANGED_COLUMN_KEYS = {"name", "expected", "actual"}

NOT_AUTHENTICATED = "not_authenticated"
INSUFFICIENT_ROLE = "insufficient_role"
UNKNOWN_TABLE = "unknown_table"
SCHEMA_APPLY_FAILED = "schema_apply_failed"

# R5 / UC-066: no key on this router's success payloads may name a count, a size, a time, or
# any per-user material.
FORBIDDEN_KEY = re.compile(
    r"count|rows?\b|size|bytes|length|total|time|date|_at$|created|updated|"
    r"user|character|setup|session|message|memo",
    re.IGNORECASE,
)

# Seeded llm_servers / models rows (raw SQL, so they survive hand-drifted shapes).
SERVER_ID = 7_400_001
SERVER_ROW: dict[str, Any] = {
    "id": SERVER_ID,
    "name": "local llamaswap",
    "kind": "llamaswap",
    "base_url": "http://llm.test:8080",
    "api_key_ref": "$S007_004_KEY",
    "last_test_at": "2026-02-02T10:00:00+00:00",
    "last_test_ok": 1,
    "last_test_error": None,
    "created_at": CREATED_TEXT,
    "updated_at": CREATED_TEXT,
}
MODEL_ROWS: list[dict[str, Any]] = [
    {
        "id": 7_410_001,
        "server_id": SERVER_ID,
        "model_name": "chat-a",
        "is_enabled": 1,
        "is_embedding_designated": 0,
        "embedding_dim": None,
        "created_at": CREATED_TEXT,
        "updated_at": CREATED_TEXT,
    },
    {
        "id": 7_410_002,
        "server_id": SERVER_ID,
        "model_name": "embed-a",
        "is_enabled": 1,
        "is_embedding_designated": 1,
        "embedding_dim": 384,
        "created_at": CREATED_TEXT,
        "updated_at": CREATED_TEXT,
    },
]

LEGACY_VALUE = "legacy content dropped with its column"

# A hand-drift of llm_servers that uses ALTER only (llm_servers is referenced by models):
#   missing column  last_test_error
#   extra columns   legacy_note, base_url_old, last_test_at_old
#   changed type    base_url         TEXT NOT NULL -> BLOB NOT NULL
#   changed null    last_test_at     TEXT NULL     -> TEXT NOT NULL
#   extra index     (name), not unique
LLM_SERVERS_DRIFT = (
    "ALTER TABLE llm_servers DROP COLUMN last_test_error",
    "ALTER TABLE llm_servers ADD COLUMN legacy_note TEXT",
    "ALTER TABLE llm_servers RENAME COLUMN base_url TO base_url_old",
    "ALTER TABLE llm_servers ADD COLUMN base_url BLOB NOT NULL DEFAULT x''",
    "ALTER TABLE llm_servers RENAME COLUMN last_test_at TO last_test_at_old",
    "ALTER TABLE llm_servers ADD COLUMN last_test_at TEXT NOT NULL DEFAULT ''",
    "CREATE INDEX ix_legacy_llm_servers_name ON llm_servers (name)",
)
# auth_sessions missing its declared non-unique index on user_id.
AUTH_SESSIONS_DRIFT = ("DROP INDEX ix_auth_sessions_user_id",)
# models with an extra column and a changed type (INTEGER -> TEXT) on embedding_dim.
MODELS_DRIFT = (
    "ALTER TABLE models ADD COLUMN legacy_note TEXT",
    "ALTER TABLE models RENAME COLUMN embedding_dim TO embedding_dim_old",
    "ALTER TABLE models ADD COLUMN embedding_dim TEXT",
)
DROP_MODELS = ("DROP TABLE models",)


# --- fixtures ------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _quiet_factory_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the factory's logging call so these tests touch no global sinks."""
    monkeypatch.setattr("app.main.configure_logging", lambda settings: None)


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


def _seed(engine: Engine) -> None:
    with engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(engine, user_id=ADMIN_ID, username=ADMIN_NAME, password=ADMIN_PASSWORD, role=Role.ADMIN)
    _insert_user(engine, user_id=PLAYER_ID, username=PLAYER_NAME, password=PLAYER_PASSWORD, role=Role.ROLEPLAYER)


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    _seed(db_engine)
    return db_engine


@pytest.fixture
def application(db_settings: Settings, engine: Engine) -> Iterator[FastAPI]:
    """The factory's application, pinned to the seeded database."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: db_settings
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def guarded_probe_app(db_settings: Settings, engine: Engine) -> Iterator[FastAPI]:
    """DoD-5 — an app whose database router carries a test-only route with no dependency of its own.

    The route is registered on the **same** router object the production module exports,
    before the factory includes it, and removed again afterwards.
    """

    def guard_probe() -> dict[str, bool]:
        return {"reached": True}

    before = list(admin_db_router.routes)
    admin_db_router.add_api_route(GUARD_PROBE_PATH, guard_probe, methods=["GET"])
    added = [route for route in admin_db_router.routes if route not in before]
    try:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: db_settings
        try:
            yield app
        finally:
            app.dependency_overrides.clear()
    finally:
        for route in added:
            admin_db_router.routes.remove(route)


# --- helpers -------------------------------------------------------------------------


def _apply_path(table_name: str, operation: str) -> str:
    return f"{TABLES_PATH}/{quote(table_name, safe='')}/{operation}"


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


def _player(application: FastAPI, settings: Settings) -> TestClient:
    return _as(application, settings, PLAYER_NAME, PLAYER_PASSWORD)


def _ddl(engine: Engine, statements: tuple[str, ...]) -> None:
    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)


def _insert_row(engine: Engine, table_name: str, values: dict[str, Any]) -> None:
    columns = ", ".join(values)
    params = ", ".join(f":{name}" for name in values)
    with engine.begin() as connection:
        connection.execute(text(f"INSERT INTO {table_name} ({columns}) VALUES ({params})"), values)


def _seed_server_and_models(engine: Engine) -> None:
    _insert_row(engine, "llm_servers", SERVER_ROW)
    for row in MODEL_ROWS:
        _insert_row(engine, "models", row)


def _schema_snapshot(engine: Engine) -> list[tuple[Any, ...]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name")
        ).all()
    return [tuple(row) for row in rows]


def _table_names(engine: Engine) -> set[str]:
    return {name for kind, name, _, _ in _schema_snapshot(engine) if kind == "table"}


def _rows(engine: Engine, table_name: str) -> list[tuple[Any, ...]]:
    with engine.connect() as connection:
        rows = connection.execute(text(f'SELECT * FROM "{table_name}" ORDER BY rowid')).all()
    return [tuple(row) for row in rows]


def _select_columns(engine: Engine, table_name: str, columns: list[str]) -> list[tuple[Any, ...]]:
    column_list = ", ".join(f'"{name}"' for name in columns)
    with engine.connect() as connection:
        rows = connection.execute(text(f'SELECT {column_list} FROM "{table_name}" ORDER BY id')).all()
    return [tuple(row) for row in rows]


def _live_column_names(engine: Engine, table_name: str) -> list[str]:
    with engine.connect() as connection:
        rows = connection.exec_driver_sql(f'PRAGMA table_info("{table_name}")').all()
    return [row[1] for row in rows]


def _declared_column_names(table_name: str) -> list[str]:
    return [column.name for column in schema.metadata.tables[table_name].columns]


def _assert_envelope(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error, dict)
    assert error["code"] == code
    return error


def _assert_table_report_shape(entry: Any) -> None:
    assert isinstance(entry, dict)
    assert set(entry) == TABLE_REPORT_KEYS
    assert isinstance(entry["table_name"], str)
    assert entry["status"] in STATUS_VALUES
    for name in ("missing_columns", "extra_columns"):
        assert isinstance(entry[name], list)
        assert all(isinstance(column, str) for column in entry[name])
    assert isinstance(entry["changed_columns"], list)
    for changed in entry["changed_columns"]:
        assert isinstance(changed, dict)
        assert set(changed) == CHANGED_COLUMN_KEYS
        for side in ("expected", "actual"):
            assert set(changed[side]) == COLUMN_SHAPE_KEYS
            assert isinstance(changed[side]["type_text"], str)
            assert isinstance(changed[side]["not_null"], bool)
    for name in ("missing_indexes", "extra_indexes"):
        assert isinstance(entry[name], list)
        for index in entry[name]:
            assert set(index) == INDEX_SHAPE_KEYS
            assert isinstance(index["columns"], list)
            assert isinstance(index["unique"], bool)


def _report_entries(client: TestClient) -> list[dict[str, Any]]:
    response = client.get(TABLES_PATH)
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"tables"}
    assert isinstance(body["tables"], list)
    for entry in body["tables"]:
        _assert_table_report_shape(entry)
    return list(body["tables"])


def _report(client: TestClient) -> dict[str, dict[str, Any]]:
    return {entry["table_name"]: entry for entry in _report_entries(client)}


def _assert_in_sync(entry: dict[str, Any], table_name: str) -> None:
    assert entry["table_name"] == table_name
    assert entry["status"] == "in_sync"
    for name in DIFFERENCE_LISTS:
        assert entry[name] == [], name


def _applied(response: httpx.Response, table_name: str) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    body = response.json()
    _assert_table_report_shape(body)
    assert body["table_name"] == table_name
    return dict(body)


def _all_keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        keys = list(value)
        for inner in value.values():
            keys.extend(_all_keys(inner))
        return keys
    if isinstance(value, list):
        keys = []
        for inner in value:
            keys.extend(_all_keys(inner))
        return keys
    return []


def _numeric_leaves(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return [leaf for inner in value.values() for leaf in _numeric_leaves(inner)]
    if isinstance(value, list):
        return [leaf for inner in value for leaf in _numeric_leaves(inner)]
    if isinstance(value, int | float) and not isinstance(value, bool):
        return [value]
    return []


def _feature_operations(application: FastAPI) -> dict[tuple[str, str], dict[str, Any]]:
    spec = application.openapi()
    operations: dict[tuple[str, str], dict[str, Any]] = {}
    for path, item in spec["paths"].items():
        if path == PREFIX or path.startswith(PREFIX + "/"):
            for method, operation in item.items():
                operations[(method.upper(), path)] = operation
    return operations


# S030_003_DoD10: feature 030 step 003 adds a fourth route to this router, `GET
# /api/admin/database/export`, so that the whole-database export inherits the router-level
# `require_admin` guard (030's `## Ultra phase` decision 2 of 2026-10-05). It declares no pydantic
# model — it answers a raw `Response` — so it adds no field to the count/size guard below. Its own
# behaviour is covered in `test_admin_db_export.py`.
# S031_005_DoD11: feature 031 step 005 adds a fifth route, `POST /api/admin/database/import`, for the
# same reason — the whole-database import inherits the router-level `require_admin` guard (031's
# `## Ultra phase` decision 2 of 2026-10-05). It declares no pydantic model either (it answers 204
# with no body), so it adds no field to the count/size guard below. Its own behaviour is covered in
# `test_admin_db_import.py`.
EXPECTED_OPERATIONS = {
    ("GET", f"{PREFIX}/tables"),
    ("POST", f"{PREFIX}/tables/{{table_name}}/create"),
    ("POST", f"{PREFIX}/tables/{{table_name}}/sync"),
    ("GET", f"{PREFIX}/export"),
    ("POST", f"{PREFIX}/import"),
    # F002_DoD22: fast/002 adds the rebuild route; its behaviour is in `test_admin_db_rebuild.py`.
    ("POST", f"{PREFIX}/rebuild"),
}


def _all_routes(table_name: str) -> list[tuple[str, str]]:
    return [
        ("GET", TABLES_PATH),
        ("POST", _apply_path(table_name, "create")),
        ("POST", _apply_path(table_name, "sync")),
    ]


ROUTE_IDS = ["read-report", "create", "sync"]


# =========================================================================== DoD-1


def test_report_lists_every_registry_table_in_declaration_order__DoD1(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-1 — US-017.AC-1, UC-014: 200, one entry per registry table, declaration order."""
    entries = _report_entries(_admin(application, db_settings))
    assert [entry["table_name"] for entry in entries] == list(schema.metadata.tables)


def test_every_entry_carries_a_status_from_the_closed_set__DoD1(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-1 — each entry's status is one of in_sync / missing / drifted, whatever the state."""
    admin = _admin(application, db_settings)
    _ddl(engine, DROP_MODELS + LLM_SERVERS_DRIFT + AUTH_SESSIONS_DRIFT)
    entries = _report_entries(admin)
    assert [entry["table_name"] for entry in entries] == list(schema.metadata.tables)
    assert all(entry["status"] in STATUS_VALUES for entry in entries)


def test_freshly_created_registry_reports_every_table_in_sync__DoD1(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-1 — a database made from the registry itself: every entry in sync, no differences."""
    report = _report(_admin(application, db_settings))
    assert list(report) == list(schema.metadata.tables)
    for table_name, entry in report.items():
        _assert_in_sync(entry, table_name)


# =========================================================================== DoD-2


@pytest.fixture
def mixed_state(engine: Engine) -> Engine:
    """users in sync; auth_sessions and llm_servers drifted; models missing."""
    _ddl(engine, DROP_MODELS + LLM_SERVERS_DRIFT + AUTH_SESSIONS_DRIFT)
    return engine


def test_report_distinguishes_in_sync_missing_and_drifted__DoD2(
    application: FastAPI, db_settings: Settings, mixed_state: Engine
) -> None:
    """DoD-2 — US-017.AC-1: each table's real state is reported as its status."""
    report = _report(_admin(application, db_settings))
    assert report["users"]["status"] == "in_sync"
    assert report["models"]["status"] == "missing"
    assert report["llm_servers"]["status"] == "drifted"
    assert report["auth_sessions"]["status"] == "drifted"


def test_in_sync_entry_carries_no_difference__DoD2(
    application: FastAPI, db_settings: Settings, mixed_state: Engine
) -> None:
    """DoD-2 — the in-sync table beside drifted ones lists nothing."""
    _assert_in_sync(_report(_admin(application, db_settings))["users"], "users")


def test_drifted_entry_carries_its_missing_and_extra_columns__DoD2(
    application: FastAPI, db_settings: Settings, mixed_state: Engine
) -> None:
    """DoD-2 — D1: declared-but-absent columns are missing; live-but-undeclared ones are extra."""
    entry = _report(_admin(application, db_settings))["llm_servers"]
    assert entry["missing_columns"] == ["last_test_error"]
    assert sorted(entry["extra_columns"]) == sorted(["legacy_note", "base_url_old", "last_test_at_old"])


def test_drifted_entry_carries_changed_columns_with_expected_and_actual__DoD2(
    application: FastAPI, db_settings: Settings, mixed_state: Engine
) -> None:
    """DoD-2 — D1: a type change and a nullability change, each with expected and actual shape."""
    entry = _report(_admin(application, db_settings))["llm_servers"]
    changed = {column["name"]: column for column in entry["changed_columns"]}
    assert set(changed) == {"base_url", "last_test_at"}
    assert changed["base_url"]["expected"] == {"name": "base_url", "type_text": "TEXT", "not_null": True}
    assert changed["base_url"]["actual"] == {"name": "base_url", "type_text": "BLOB", "not_null": True}
    assert changed["last_test_at"]["expected"] == {"name": "last_test_at", "type_text": "TEXT", "not_null": False}
    assert changed["last_test_at"]["actual"] == {"name": "last_test_at", "type_text": "TEXT", "not_null": True}


def test_a_column_is_named_in_one_list_only__DoD2(
    application: FastAPI, db_settings: Settings, mixed_state: Engine
) -> None:
    """DoD-2 — a changed column is neither missing nor extra."""
    entry = _report(_admin(application, db_settings))["llm_servers"]
    changed_names = {column["name"] for column in entry["changed_columns"]}
    assert changed_names.isdisjoint(entry["missing_columns"])
    assert changed_names.isdisjoint(entry["extra_columns"])


def test_drifted_entry_carries_its_extra_index__DoD2(
    application: FastAPI, db_settings: Settings, mixed_state: Engine
) -> None:
    """DoD-2 — D1: a live index the registry does not declare, keyed on (columns, unique)."""
    entry = _report(_admin(application, db_settings))["llm_servers"]
    assert entry["extra_indexes"] == [{"columns": ["name"], "unique": False}]
    assert entry["missing_indexes"] == []


def test_drifted_entry_carries_its_missing_index__DoD2(
    application: FastAPI, db_settings: Settings, mixed_state: Engine
) -> None:
    """DoD-2 — D1: a declared index absent from the live table; nothing else differs."""
    entry = _report(_admin(application, db_settings))["auth_sessions"]
    assert entry["status"] == "drifted"
    assert entry["missing_indexes"] == [{"columns": ["user_id"], "unique": False}]
    assert entry["extra_indexes"] == []
    assert entry["missing_columns"] == []
    assert entry["extra_columns"] == []
    assert entry["changed_columns"] == []


# =========================================================================== DoD-3


def test_report_payload_carries_no_count_size_time_or_user_material__DoD3(
    application: FastAPI, db_settings: Settings, mixed_state: Engine
) -> None:
    """DoD-3 — R5, UC-066: exact keys, no number anywhere, no forbidden key name."""
    admin = _admin(application, db_settings)
    response = admin.get(TABLES_PATH)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"tables"}
    for entry in body["tables"]:
        assert set(entry) == TABLE_REPORT_KEYS
    assert _numeric_leaves(body) == []
    assert [key for key in _all_keys(body) if FORBIDDEN_KEY.search(key)] == []


@pytest.mark.parametrize("operation", ["create", "sync"])
def test_apply_answers_carry_no_count_size_time_or_user_material__DoD3(
    application: FastAPI, db_settings: Settings, engine: Engine, operation: str
) -> None:
    """DoD-3 — R5: an apply answer is one report row and nothing counted (no "rows affected")."""
    admin = _admin(application, db_settings)
    _ddl(engine, DROP_MODELS)
    response = admin.post(_apply_path("models", operation))
    assert response.status_code == 200
    body = response.json()
    assert set(body) == TABLE_REPORT_KEYS
    assert _numeric_leaves(body) == []
    assert [key for key in _all_keys(body) if FORBIDDEN_KEY.search(key)] == []


def test_response_models_declare_no_count_size_or_time_field__DoD3() -> None:
    """DoD-3 — the models themselves: the report row carries exactly D2's fields."""
    assert set(TableReportResponse.model_fields) == TABLE_REPORT_KEYS
    assert set(DriftReportResponse.model_fields) == {"tables"}
    schema_text = json.dumps([TableReportResponse.model_json_schema(), DriftReportResponse.model_json_schema()])
    assert '"integer"' not in schema_text
    assert '"number"' not in schema_text


def test_router_declares_exactly_the_expected_routes__DoD3(application: FastAPI) -> None:
    """DoD-3 — this router's surface is exactly `EXPECTED_OPERATIONS`: the three 007 routes plus
    030's export, and nothing else. S030_003_DoD10: reworded from "only the three routes"; the
    count guard that DoD-3 owns is asserted on the response models, which the export has none of.
    """
    assert set(_feature_operations(application)) == EXPECTED_OPERATIONS


def test_router_declares_no_query_parameter_and_no_non_table_key__DoD3(application: FastAPI) -> None:
    """DoD-3 — D9: no query parameter anywhere; the only path parameter is the table name.

    S030_003_DoD10: 030's `GET /export` takes no id at all, like `GET /tables`, so it joins the
    no-path-parameter arm of the branch below. S031_005_DoD11: 031's `POST /import` takes no id
    either, so it joins that same arm. The query-parameter half is untouched and still holds for
    every operation, the two new ones included.

    F002_DoD22: fast/002's `POST /rebuild` takes no id either, so it joins that same arm.
    """
    for (method, path), operation in _feature_operations(application).items():
        parameters = operation.get("parameters", [])
        assert [p["name"] for p in parameters if p["in"] == "query"] == [], (method, path)
        path_names = [p["name"] for p in parameters if p["in"] == "path"]
        if path.endswith(("/tables", "/export", "/import", "/rebuild")):
            assert path_names == [], (method, path)
        else:
            assert path_names == ["table_name"], (method, path)


# =========================================================================== DoD-4


@pytest.mark.parametrize("route_index", range(3), ids=ROUTE_IDS)
def test_every_route_refuses_a_roleplayer_with_403__DoD4(
    application: FastAPI, db_settings: Settings, route_index: int
) -> None:
    """DoD-4 — a live roleplayer session: 403 ``insufficient_role`` on every route."""
    method, path = _all_routes("models")[route_index]
    response = _player(application, db_settings).request(method, path)
    _assert_envelope(response, 403, INSUFFICIENT_ROLE)


@pytest.mark.parametrize("route_index", range(3), ids=ROUTE_IDS)
def test_every_route_answers_401_without_a_session__DoD4(
    application: FastAPI, db_settings: Settings, route_index: int
) -> None:
    """DoD-4 — no session at all: 401 ``not_authenticated``, never 403."""
    method, path = _all_routes("models")[route_index]
    response = _with_cookie(application, db_settings, None).request(method, path)
    assert response.status_code != 403
    _assert_envelope(response, 401, NOT_AUTHENTICATED)


@pytest.mark.parametrize("route_index", range(3), ids=ROUTE_IDS)
def test_every_route_answers_401_for_an_unissued_cookie__DoD4(
    application: FastAPI, db_settings: Settings, route_index: int
) -> None:
    """DoD-4 — a cookie resolving to no session is 'no session': 401, not 403."""
    method, path = _all_routes("models")[route_index]
    stranger = _with_cookie(application, db_settings, "this-token-was-never-issued-by-anyone-0000")
    _assert_envelope(stranger.request(method, path), 401, NOT_AUTHENTICATED)


@pytest.mark.parametrize("operation", ["create", "sync"])
def test_guard_answers_before_the_table_name_is_looked_at__DoD4(
    application: FastAPI, db_settings: Settings, operation: str
) -> None:
    """DoD-4 — an undeclared name still gets 403 / 401 from the guard, never 404."""
    path = _apply_path("no_such_table", operation)
    _assert_envelope(_player(application, db_settings).post(path), 403, INSUFFICIENT_ROLE)
    _assert_envelope(_with_cookie(application, db_settings, None).post(path), 401, NOT_AUTHENTICATED)


def test_refused_apply_requests_change_nothing__DoD4(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-4 — a refused roleplayer or anonymous Create / Sync emits no DDL."""
    player = _player(application, db_settings)
    anonymous = _with_cookie(application, db_settings, None)
    _ddl(engine, DROP_MODELS + ("ALTER TABLE llm_servers ADD COLUMN legacy_note TEXT",))
    before = _schema_snapshot(engine)
    for table_name in ("models", "llm_servers"):
        for operation in ("create", "sync"):
            assert player.post(_apply_path(table_name, operation)).status_code == 403
            assert anonymous.post(_apply_path(table_name, operation)).status_code == 401
    assert _schema_snapshot(engine) == before


def test_administrator_is_admitted_on_every_route__DoD4(application: FastAPI, db_settings: Settings) -> None:
    """DoD-4 — control: the same three requests from an administrator answer 200."""
    admin = _admin(application, db_settings)
    for method, path in _all_routes("models"):
        assert admin.request(method, path).status_code == 200, (method, path)


# =========================================================================== DoD-5


def test_route_without_its_own_dependency_is_refused_for_a_roleplayer__DoD5(
    guarded_probe_app: FastAPI, db_settings: Settings
) -> None:
    """DoD-5 — a route on this router declaring no dependency is still 403 for a roleplayer."""
    player = _player(guarded_probe_app, db_settings)
    _assert_envelope(player.get(GUARD_PROBE_FULL_PATH), 403, INSUFFICIENT_ROLE)


def test_route_without_its_own_dependency_is_401_without_a_session__DoD5(
    guarded_probe_app: FastAPI, db_settings: Settings
) -> None:
    """DoD-5 — the same probe route answers 401 with no session."""
    anonymous = _with_cookie(guarded_probe_app, db_settings, None)
    _assert_envelope(anonymous.get(GUARD_PROBE_FULL_PATH), 401, NOT_AUTHENTICATED)


def test_route_without_its_own_dependency_is_reachable_for_an_administrator__DoD5(
    guarded_probe_app: FastAPI, db_settings: Settings
) -> None:
    """DoD-5 — control: an administrator reaches the probe route."""
    response = _admin(guarded_probe_app, db_settings).get(GUARD_PROBE_FULL_PATH)
    assert response.status_code == 200
    assert response.json() == {"reached": True}


def test_probe_route_does_not_leak_into_other_applications__DoD5(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-5 — hygiene: an ordinary factory app exposes no test-only probe route."""
    assert _admin(application, db_settings).get(GUARD_PROBE_FULL_PATH).status_code in (404, 405)


# =========================================================================== DoD-6


def test_create_on_a_missing_table_answers_it_in_sync__DoD6(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-6 — US-018.AC-1, UC-015: 200, and the answer is the re-derived row, in sync."""
    admin = _admin(application, db_settings)
    _ddl(engine, DROP_MODELS)
    assert _report(admin)["models"]["status"] == "missing"

    body = _applied(admin.post(_apply_path("models", "create")), "models")
    _assert_in_sync(body, "models")
    assert "models" in _table_names(engine)
    assert _live_column_names(engine, "models") == _declared_column_names("models")


def test_create_on_a_missing_table_is_reflected_by_the_next_report__DoD6(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-6 — US-018.AC-2: the report read afterwards shows the table in sync."""
    admin = _admin(application, db_settings)
    _ddl(engine, DROP_MODELS)
    assert admin.post(_apply_path("models", "create")).status_code == 200
    report = _report(admin)
    _assert_in_sync(report["models"], "models")
    assert all(entry["status"] == "in_sync" for entry in report.values())


def test_create_on_a_missing_table_leaves_every_other_table_alone__DoD6(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-6 — the Create touches only the named table's objects."""
    admin = _admin(application, db_settings)
    _ddl(engine, DROP_MODELS)
    before = [entry for entry in _schema_snapshot(engine) if entry[2] != "models"]
    users_before = _rows(engine, "users")
    assert admin.post(_apply_path("models", "create")).status_code == 200
    assert [entry for entry in _schema_snapshot(engine) if entry[2] != "models"] == before
    assert _rows(engine, "users") == users_before


# =========================================================================== DoD-7


def _prepare_models_drift(engine: Engine) -> None:
    _seed_server_and_models(engine)
    _ddl(engine, MODELS_DRIFT)
    with engine.begin() as connection:
        connection.execute(text("UPDATE models SET legacy_note = :value"), {"value": LEGACY_VALUE})


def _prepare_llm_servers_drift(engine: Engine) -> None:
    _seed_server_and_models(engine)
    _ddl(engine, LLM_SERVERS_DRIFT)


def _prepare_nothing(engine: Engine) -> None:
    return None


@pytest.mark.parametrize(
    ("table_name", "prepare", "expected_status"),
    [
        ("users", _prepare_nothing, "in_sync"),
        ("llm_servers", _prepare_nothing, "in_sync"),
        ("models", _prepare_models_drift, "drifted"),
        ("llm_servers", _prepare_llm_servers_drift, "drifted"),
    ],
    ids=["users-in-sync", "llm_servers-in-sync", "models-drifted", "llm_servers-drifted"],
)
def test_create_on_an_existing_table_changes_nothing__DoD7(
    application: FastAPI,
    db_settings: Settings,
    engine: Engine,
    table_name: str,
    prepare: Any,
    expected_status: str,
) -> None:
    """DoD-7 — D4: Create on an existing table answers 200 and adds, drops and touches nothing."""
    admin = _admin(application, db_settings)
    prepare(engine)
    schema_before = _schema_snapshot(engine)
    columns_before = _live_column_names(engine, table_name)
    rows_before = _rows(engine, table_name)

    body = _applied(admin.post(_apply_path(table_name, "create")), table_name)

    assert _schema_snapshot(engine) == schema_before
    assert _live_column_names(engine, table_name) == columns_before
    assert _rows(engine, table_name) == rows_before
    # D4: a no-op Create answers with the table's current truth.
    assert body["status"] == expected_status


def test_create_on_a_drifted_table_reports_its_drift_rather_than_fixing_it__DoD7(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-7 — D4: the extra column is still there and still reported after a Create."""
    admin = _admin(application, db_settings)
    _prepare_models_drift(engine)
    body = _applied(admin.post(_apply_path("models", "create")), "models")
    assert "legacy_note" in body["extra_columns"]
    assert "legacy_note" in _live_column_names(engine, "models")
    assert _report(admin)["models"]["status"] == "drifted"


# =========================================================================== DoD-8


def _prepare_auth_sessions_drift(engine: Engine) -> None:
    _ddl(engine, AUTH_SESSIONS_DRIFT)


def _prepare_models_missing_column(engine: Engine) -> None:
    _seed_server_and_models(engine)
    _ddl(engine, ("ALTER TABLE models DROP COLUMN embedding_dim",))


@pytest.mark.parametrize(
    ("table_name", "prepare"),
    [
        ("models", _prepare_models_drift),
        ("models", _prepare_models_missing_column),
        ("llm_servers", _prepare_llm_servers_drift),
        ("auth_sessions", _prepare_auth_sessions_drift),
    ],
    ids=["models-extra-and-retyped", "models-missing-column", "llm_servers-mixed", "auth_sessions-missing-index"],
)
def test_sync_on_a_drifted_table_answers_it_in_sync__DoD8(
    application: FastAPI, db_settings: Settings, engine: Engine, table_name: str, prepare: Any
) -> None:
    """DoD-8 — US-018.AC-1/AC-2: 200 with the re-derived row in sync, and the report agrees."""
    admin = _admin(application, db_settings)
    prepare(engine)
    assert _report(admin)[table_name]["status"] == "drifted"

    body = _applied(admin.post(_apply_path(table_name, "sync")), table_name)
    _assert_in_sync(body, table_name)

    _assert_in_sync(_report(admin)[table_name], table_name)
    assert set(_live_column_names(engine, table_name)) == set(_declared_column_names(table_name))


# =========================================================================== DoD-9


def test_sync_drops_an_undeclared_column_and_keeps_every_surviving_value__DoD9(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-9 — D5: the undeclared column is gone; every declared column's data is intact."""
    admin = _admin(application, db_settings)
    _seed_server_and_models(engine)
    _ddl(engine, ("ALTER TABLE models ADD COLUMN legacy_note TEXT",))
    with engine.begin() as connection:
        connection.execute(text("UPDATE models SET legacy_note = :value"), {"value": LEGACY_VALUE})
    survivors = _declared_column_names("models")
    before = _select_columns(engine, "models", survivors)
    assert len(before) == len(MODEL_ROWS)

    body = _applied(admin.post(_apply_path("models", "sync")), "models")
    assert body["status"] == "in_sync"

    assert "legacy_note" not in _live_column_names(engine, "models")
    assert _select_columns(engine, "models", survivors) == before


def test_sync_of_a_referenced_table_drops_its_extra_column_and_keeps_both_tables_data__DoD9(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-9 — D5 + D8: rebuilding llm_servers keeps its survivors and its dependent models rows."""
    admin = _admin(application, db_settings)
    _seed_server_and_models(engine)
    _ddl(engine, ("ALTER TABLE llm_servers ADD COLUMN legacy_note TEXT",))
    with engine.begin() as connection:
        connection.execute(text("UPDATE llm_servers SET legacy_note = :value"), {"value": LEGACY_VALUE})
    server_columns = _declared_column_names("llm_servers")
    model_columns = _declared_column_names("models")
    servers_before = _select_columns(engine, "llm_servers", server_columns)
    models_before = _select_columns(engine, "models", model_columns)

    body = _applied(admin.post(_apply_path("llm_servers", "sync")), "llm_servers")
    assert body["status"] == "in_sync"

    assert "legacy_note" not in _live_column_names(engine, "llm_servers")
    assert _select_columns(engine, "llm_servers", server_columns) == servers_before
    assert _select_columns(engine, "models", model_columns) == models_before


# =========================================================================== DoD-10


NOISE_BODIES: list[dict[str, Any]] = [
    {"json": {"table_name": "users", "operation": "sync", "drop_columns": ["username"]}},
    {"content": b"this is not json at all", "headers": {"content-type": "text/plain"}},
]


@pytest.mark.parametrize("noise", NOISE_BODIES, ids=["json-body", "text-body"])
def test_create_ignores_a_supplied_body__DoD10(
    application: FastAPI, db_settings: Settings, engine: Engine, noise: dict[str, Any]
) -> None:
    """DoD-10 — a body changes nothing: the named missing table is created, nothing else moves."""
    admin = _admin(application, db_settings)
    _ddl(engine, DROP_MODELS)
    users_columns = _live_column_names(engine, "users")
    users_rows = _rows(engine, "users")

    body = _applied(admin.post(_apply_path("models", "create"), **noise), "models")
    _assert_in_sync(body, "models")

    assert _live_column_names(engine, "users") == users_columns
    assert _rows(engine, "users") == users_rows


@pytest.mark.parametrize("noise", NOISE_BODIES, ids=["json-body", "text-body"])
def test_sync_ignores_a_supplied_body__DoD10(
    application: FastAPI, db_settings: Settings, engine: Engine, noise: dict[str, Any]
) -> None:
    """DoD-10 — a body changes nothing: the named drifted table is synced exactly as without one."""
    admin = _admin(application, db_settings)
    _prepare_models_drift(engine)
    users_columns = _live_column_names(engine, "users")

    body = _applied(admin.post(_apply_path("models", "sync"), **noise), "models")
    _assert_in_sync(body, "models")
    assert "legacy_note" not in _live_column_names(engine, "models")
    assert _live_column_names(engine, "users") == users_columns


@pytest.mark.parametrize("operation", ["create", "sync"])
def test_apply_routes_ignore_a_supplied_query_string__DoD10(
    application: FastAPI, db_settings: Settings, engine: Engine, operation: str
) -> None:
    """DoD-10 — a query string names nothing the route acts on: the path's table is applied."""
    admin = _admin(application, db_settings)
    _ddl(engine, DROP_MODELS)
    users_rows = _rows(engine, "users")
    response = admin.post(
        _apply_path("models", operation),
        params={"table_name": "users", "operation": "sync", "dry_run": "true"},
    )
    body = _applied(response, "models")
    _assert_in_sync(body, "models")
    assert "models" in _table_names(engine)
    assert _rows(engine, "users") == users_rows


def test_apply_routes_declare_no_request_body_and_no_query_parameter__DoD10(application: FastAPI) -> None:
    """DoD-10 — D9: neither apply route takes a request model or a query parameter."""
    operations = _feature_operations(application)
    for suffix in ("create", "sync"):
        operation = operations[("POST", f"{PREFIX}/tables/{{table_name}}/{suffix}")]
        assert "requestBody" not in operation
        assert [p for p in operation.get("parameters", []) if p["in"] == "query"] == []


# =========================================================================== DoD-11


UNDECLARED_NAMES = [
    # 010/001 DoD-9: was "characters" (009 registers it), then "setups" (010 registers it).
    # The chain ends here: "no_such_table" is a valid table identifier that belongs to no
    # feature's domain, so no planned feature will ever declare it and no later feature has
    # to swap this entry again.
    "no_such_table",
    "legacy_notes",
    "sqlite_master",
    'users"; DROP TABLE users; --',
    "models' OR '1'='1",
    "llm_servers)",
    "[auth_sessions]",
    "users--",
    "users; DELETE FROM users",
]


@pytest.fixture
def ddl_recorder(engine: Engine) -> Iterator[list[str]]:
    statements: list[str] = []

    def record(conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


DDL_OR_WRITE = re.compile(r"^\s*(CREATE|ALTER|DROP|INSERT|DELETE)\b", re.IGNORECASE)


@pytest.mark.parametrize("operation", ["create", "sync"])
@pytest.mark.parametrize("table_name", UNDECLARED_NAMES)
def test_undeclared_table_name_is_refused_404_with_no_ddl__DoD11(
    application: FastAPI,
    db_settings: Settings,
    engine: Engine,
    ddl_recorder: list[str],
    table_name: str,
    operation: str,
) -> None:
    """DoD-11 — D9: 404 ``unknown_table`` carrying the name; no DDL, whatever the punctuation."""
    admin = _admin(application, db_settings)
    _ddl(engine, ("CREATE TABLE legacy_notes (id INTEGER PRIMARY KEY, note TEXT)",))
    _insert_row(engine, "legacy_notes", {"id": 1, "note": "hand-made, not in the registry"})
    schema_before = _schema_snapshot(engine)
    users_before = _rows(engine, "users")
    notes_before = _rows(engine, "legacy_notes")
    ddl_recorder.clear()

    error = _assert_envelope(admin.post(_apply_path(table_name, operation)), 404, UNKNOWN_TABLE)
    assert error["detail"]["table_name"] == table_name

    assert [statement for statement in ddl_recorder if DDL_OR_WRITE.match(statement)] == []
    assert _schema_snapshot(engine) == schema_before
    assert _rows(engine, "users") == users_before
    assert _rows(engine, "legacy_notes") == notes_before


# =========================================================================== DoD-12


DUPLICATED_HASH = "duplicated-S007-004-token-hash-value"


def _prepare_not_null_over_nulls(engine: Engine) -> None:
    """models.model_name is declared NOT NULL; the live column is nullable and holds NULLs."""
    _seed_server_and_models(engine)
    _ddl(
        engine,
        (
            "ALTER TABLE models RENAME COLUMN model_name TO model_name_old",
            "ALTER TABLE models ADD COLUMN model_name TEXT",
        ),
    )


def _prepare_unique_over_duplicates(engine: Engine) -> None:
    """auth_sessions.token_hash is declared under a unique index; the live one is not, over duplicates."""
    _ddl(
        engine,
        (
            "DROP INDEX ix_auth_sessions_token_hash",
            "CREATE INDEX ix_legacy_token_hash ON auth_sessions (token_hash)",
        ),
    )
    for session_id in (7_500_001, 7_500_002):
        _insert_row(
            engine,
            "auth_sessions",
            {
                "id": session_id,
                "user_id": ADMIN_ID,
                "token_hash": DUPLICATED_HASH,
                "created_at": CREATED_TEXT,
                "expires_at": EXPIRES_TEXT,
                "revoked_at": None,
            },
        )


def _row_snapshot(engine: Engine, table_name: str) -> Any:
    if table_name == "auth_sessions":
        # Only the rows this test wrote: the live session may be refreshed by the guard itself.
        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT * FROM auth_sessions WHERE token_hash = :hash ORDER BY rowid"),
                {"hash": DUPLICATED_HASH},
            ).all()
        return [tuple(row) for row in rows]
    return _rows(engine, table_name)


FAILURE_CASES = [
    ("models", _prepare_not_null_over_nulls, ["models.model_name", "chat-a", "embed-a"]),
    ("auth_sessions", _prepare_unique_over_duplicates, ["auth_sessions.token_hash", DUPLICATED_HASH]),
]


@pytest.mark.parametrize(
    ("table_name", "prepare", "leak_markers"),
    FAILURE_CASES,
    ids=["not-null-over-nulls", "unique-over-duplicates"],
)
def test_sync_that_cannot_complete_answers_500_schema_apply_failed__DoD12(
    application: FastAPI,
    db_settings: Settings,
    engine: Engine,
    table_name: str,
    prepare: Any,
    leak_markers: list[str],
) -> None:
    """DoD-12 — D9: 500 ``schema_apply_failed``; detail is the table and the operation only."""
    admin = _admin(application, db_settings)
    prepare(engine)

    response = admin.post(_apply_path(table_name, "sync"))
    error = _assert_envelope(response, 500, SCHEMA_APPLY_FAILED)
    assert error["detail"] == {"table_name": table_name, "operation": "sync"}

    # No driver message: nothing SQLite would say, no constraint target, no stored value.
    lowered = response.text.lower()
    for fragment in ("constraint", "integrity", "sqlite", "operationalerror"):
        assert fragment not in lowered
    for marker in leak_markers:
        assert marker.lower() not in lowered


@pytest.mark.parametrize(
    ("table_name", "prepare", "leak_markers"),
    FAILURE_CASES,
    ids=["not-null-over-nulls", "unique-over-duplicates"],
)
def test_sync_that_cannot_complete_leaves_the_table_exactly_as_it_was__DoD12(
    application: FastAPI,
    db_settings: Settings,
    engine: Engine,
    table_name: str,
    prepare: Any,
    leak_markers: list[str],
) -> None:
    """DoD-12 — D5: a failed rebuild completes not at all; no temp table survives."""
    admin = _admin(application, db_settings)
    prepare(engine)
    schema_before = _schema_snapshot(engine)
    columns_before = _live_column_names(engine, table_name)
    rows_before = _row_snapshot(engine, table_name)

    assert admin.post(_apply_path(table_name, "sync")).status_code == 500

    assert _schema_snapshot(engine) == schema_before
    assert _live_column_names(engine, table_name) == columns_before
    assert _row_snapshot(engine, table_name) == rows_before
    assert [name for name in _table_names(engine) if name.startswith("_alembic_tmp")] == []
    assert _report(admin)[table_name]["status"] == "drifted"


# =========================================================================== DoD-13


def _router_tree() -> ast.Module:
    return ast.parse(inspect.getsource(admin_db_module))


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _docstring_nodes(tree: ast.Module) -> set[ast.AST]:
    found: set[ast.AST] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)):
            continue
        if isinstance(node.value.value, str):
            found.add(node.value)
    return found


HANDLER_NAMES = ("read_drift_report", "create_registry_table", "sync_registry_table")


def test_router_imports_the_registry_at_module_level__DoD13() -> None:
    """DoD-13 — the router imports ``metadata`` from ``app.db.schema`` at module level only."""
    tree = _router_tree()
    top_level = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and (
            (node.module == "app.db.schema" and any(alias.name == "metadata" for alias in node.names))
            or (node.module == "app.db" and any(alias.name == "schema" for alias in node.names))
        )
    ]
    assert top_level, "the registry must be imported at module level"
    nested = [
        node
        for function in ast.walk(tree)
        if isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef)
        for node in ast.walk(function)
        if isinstance(node, ast.Import | ast.ImportFrom)
    ]
    assert nested == []


def test_every_handler_passes_the_registry_down_and_never_looks_into_it__DoD13() -> None:
    """DoD-13 — each use of the registry is a plain call argument: no ``.tables``, no subscript."""
    tree = _router_tree()
    parents = _parents(tree)
    functions = {
        node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    for handler in HANDLER_NAMES:
        assert handler in functions, handler
    for handler in HANDLER_NAMES:
        uses = [
            node
            for node in ast.walk(functions[handler])
            if (isinstance(node, ast.Name) and node.id == "metadata")
            or (isinstance(node, ast.Attribute) and node.attr == "metadata")
        ]
        assert uses, f"{handler} must pass the registry down"
        for use in uses:
            parent = parents[use]
            if isinstance(parent, ast.keyword):
                parent = parents[parent]
            assert isinstance(parent, ast.Call), f"{handler}: registry used as something other than an argument"
            assert parent.func is not use


def test_router_issues_no_sql_opens_no_transaction_and_translates_no_error__DoD13() -> None:
    """DoD-13 — no SQL, no transaction, no ``try``/``except``, no ``HTTPException``, no raise."""
    tree = _router_tree()
    forbidden_calls = {
        "execute",
        "exec_driver_sql",
        "begin",
        "begin_nested",
        "commit",
        "rollback",
        "scalar",
        "scalars",
    }
    calls = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in forbidden_calls
    ]
    assert calls == []
    assert [node for node in ast.walk(tree) if isinstance(node, ast.Try | ast.TryStar | ast.Raise)] == []

    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }
    assert "HTTPException" not in names | imported
    assert "text" not in imported
    assert "sqlite3" not in imported

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("sqlalchemy"):
            assert {alias.name for alias in node.names} <= {"Connection"}, node.module
        if isinstance(node, ast.Import):
            assert not any(alias.name.startswith("sqlalchemy") for alias in node.names)

    docstrings = _docstring_nodes(tree)
    sql_keyword = re.compile(r"\b(SELECT|PRAGMA|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b")
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node not in docstrings
    ]
    assert [literal for literal in literals if sql_keyword.search(literal)] == []


def _values(args: tuple[Any, ...], kwargs: dict[str, Any]) -> list[Any]:
    return [*args, *kwargs.values()]


@pytest.fixture
def spies(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[list[Any]]]:
    """Wrap the router's three collaborators (by the names it holds) to record their arguments."""
    recorded: dict[str, list[list[Any]]] = {"report": [], "create": [], "sync": []}

    def spy_report(*args: Any, **kwargs: Any) -> Any:
        recorded["report"].append(_values(args, kwargs))
        return build_drift_report(*args, **kwargs)

    def spy_create(*args: Any, **kwargs: Any) -> Any:
        recorded["create"].append(_values(args, kwargs))
        return create_table(*args, **kwargs)

    def spy_sync(*args: Any, **kwargs: Any) -> Any:
        recorded["sync"].append(_values(args, kwargs))
        return sync_table(*args, **kwargs)

    monkeypatch.setattr(admin_db_module, "build_drift_report", spy_report, raising=False)
    monkeypatch.setattr(admin_db_module, "create_table", spy_create, raising=False)
    monkeypatch.setattr(admin_db_module, "sync_table", spy_sync, raising=False)
    return recorded


def _assert_passed_registry_and_connection(values: list[Any]) -> None:
    registries = [value for value in values if isinstance(value, MetaData)]
    assert len(registries) == 1
    assert registries[0] is schema.metadata
    assert len([value for value in values if isinstance(value, Connection)]) == 1


def test_report_route_calls_the_report_builder_once_with_the_registry__DoD13(
    application: FastAPI, db_settings: Settings, spies: dict[str, list[list[Any]]]
) -> None:
    """DoD-13 — the read calls exactly one operation, handing it the connection and the registry."""
    admin = _admin(application, db_settings)
    assert admin.get(TABLES_PATH).status_code == 200
    assert len(spies["report"]) == 1
    assert spies["create"] == [] and spies["sync"] == []
    _assert_passed_registry_and_connection(spies["report"][0])


@pytest.mark.parametrize("operation", ["create", "sync"])
def test_apply_route_calls_its_one_operation_with_the_registry_and_the_raw_name__DoD13(
    application: FastAPI, db_settings: Settings, spies: dict[str, list[list[Any]]], operation: str
) -> None:
    """DoD-13 — an apply calls exactly its own operation with the connection, registry and name."""
    admin = _admin(application, db_settings)
    assert admin.post(_apply_path("models", operation)).status_code == 200
    other = "sync" if operation == "create" else "create"
    assert len(spies[operation]) == 1
    assert spies[other] == [] and spies["report"] == []
    values = spies[operation][0]
    _assert_passed_registry_and_connection(values)
    assert "models" in [value for value in values if isinstance(value, str)]


@pytest.mark.parametrize("operation", ["create", "sync"])
def test_unknown_table_refusal_comes_from_the_service__DoD13(
    application: FastAPI, db_settings: Settings, spies: dict[str, list[list[Any]]], operation: str
) -> None:
    """DoD-13 — D9: the handler does no lookup; the undeclared raw name reaches the service."""
    name = 'users"; DROP TABLE users; --'
    admin = _admin(application, db_settings)
    _assert_envelope(admin.post(_apply_path(name, operation)), 404, UNKNOWN_TABLE)
    assert len(spies[operation]) == 1
    assert name in [value for value in spies[operation][0] if isinstance(value, str)]


@pytest.mark.parametrize("operation", ["create", "sync"])
def test_handler_maps_whatever_the_service_answers__DoD13(
    application: FastAPI, db_settings: Settings, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    """DoD-13 — no handler check: a service answer for any name is mapped straight onto the wire."""

    def canned(*args: Any, **kwargs: Any) -> TableReport:
        return TableReport(
            table_name="not_in_any_registry",
            status=TableStatus.IN_SYNC,
            missing_columns=(),
            extra_columns=(),
            changed_columns=(),
            missing_indexes=(),
            extra_indexes=(),
        )

    target = "create_table" if operation == "create" else "sync_table"
    monkeypatch.setattr(admin_db_module, target, canned, raising=False)
    admin = _admin(application, db_settings)
    body = _applied(admin.post(_apply_path("not_in_any_registry", operation)), "not_in_any_registry")
    _assert_in_sync(body, "not_in_any_registry")


def test_database_contact_goes_only_through_the_connection_dependency__DoD13(
    application: FastAPI, db_settings: Settings, engine: Engine, tmp_path: Path
) -> None:
    """DoD-13 — redirect ``get_connection``: the report and the apply happen on that database only."""
    alternate_settings = db_settings.model_copy(
        update={"data_dir": tmp_path / "alternate", "db_filename": "alternate.sqlite"}
    )
    alternate_engine = get_engine(alternate_settings)
    with alternate_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(
        alternate_engine,
        user_id=9_100_001,
        username="alternate-admin",
        password="alternate admin password",
        role=Role.ADMIN,
    )
    _ddl(alternate_engine, DROP_MODELS)

    def alternate_connection() -> Iterator[Connection]:
        connection = alternate_engine.connect()
        try:
            yield connection
        finally:
            connection.close()

    application.dependency_overrides[get_connection] = alternate_connection
    main_before = _schema_snapshot(engine)

    admin = _as(application, db_settings, "alternate-admin", "alternate admin password")
    assert _report(admin)["models"]["status"] == "missing"

    body = _applied(admin.post(_apply_path("models", "create")), "models")
    assert body["status"] == "in_sync"
    assert "models" in _table_names(alternate_engine)
    assert _schema_snapshot(engine) == main_before


# =========================================================================== DoD-14


# S030_003_DoD1: `export` leaves the blanket word list. Feature 030 step 003 ships exactly
# one export route on this router, `GET /api/admin/database/export`, so the word is admitted
# on that single operation and nowhere else. `rebuild`, `import`, `vector` and `vec0` stay
# rejected across the whole surface — 031 owns Import and `fast/002` owns Rebuild, and this
# guard is what keeps either from appearing early.
# S031_005_DoD11: `import` now has exactly one admitted operation too, `POST
# /api/admin/database/import`, which feature 031 step 005 delivers. The word list itself keeps all
# four members: `rebuild`, `vector` and `vec0` stay rejected on **every** operation, `export` on
# everything but 030's single export operation, and `import` on everything but that one import
# operation. `fast/002`'s Rebuild still cannot appear early.
# F002_DoD22: `rebuild` now has exactly one admitted operation, `POST /api/admin/database/rebuild`,
# which fast/002 delivers. `vector` and `vec0` stay rejected on every operation.
FORBIDDEN_SURFACE = ("rebuild", "import", "vector", "vec0")

#: S030_003_DoD1 — the one operation permitted to name an export.
PERMITTED_EXPORT_OPERATION = ("GET", f"{PREFIX}/export")

#: S031_005_DoD11 — the one operation permitted to name an import.
PERMITTED_IMPORT_OPERATION = ("POST", f"{PREFIX}/import")

#: F002_DoD22 — the one operation permitted to name a rebuild.
PERMITTED_REBUILD_OPERATION = ("POST", f"{PREFIX}/rebuild")


def test_route_surface_has_no_vector_route_one_import_route_and_one_rebuild_route__DoD14(
    application: FastAPI,
) -> None:
    """DoD-14 — brief Scope Out: exactly the expected routes, none of them naming
    out-of-scope work.

    S030_003_DoD1: narrowed, not disarmed. The surface is still pinned to
    `EXPECTED_OPERATIONS`, every path is still rejected for `rebuild` / `import` /
    `vector` / `vec0`, and `export` is still rejected on every operation other than the
    single `GET .../export` that 030 delivers.

    S031_005_DoD11: narrowed once more, the same way. `import` is now admitted on the single
    `POST .../import` that 031 delivers and on nothing else; `rebuild`, `vector` and `vec0`
    remain rejected everywhere.

    F002_DoD22: renamed from `..._has_no_rebuild_or_vector_route_and_one_import_route__DoD14`.
    The no-rebuild half is dropped the same way: `rebuild` is admitted on the single
    `POST .../rebuild` that fast/002 delivers and on nothing else; `vector` and `vec0` remain
    rejected everywhere, and the one-import-route half is unchanged.
    """
    operations = _feature_operations(application)
    assert set(operations) == EXPECTED_OPERATIONS
    for method, path in operations:
        for word in FORBIDDEN_SURFACE:
            if word == "import" and (method, path) == PERMITTED_IMPORT_OPERATION:
                continue
            if word == "rebuild" and (method, path) == PERMITTED_REBUILD_OPERATION:
                continue
            assert word not in path.lower(), (method, path)
        if (method, path) != PERMITTED_EXPORT_OPERATION:
            assert "export" not in path.lower(), (method, path)


def test_route_surface_documents_nothing_about_a_vector_index__DoD14(application: FastAPI) -> None:
    """DoD-14 — nothing in the operations or their models mentions a vector index or a rebuild.

    F002_DoD22: narrowed. fast/002's `POST .../rebuild` legitimately documents a rebuild of the
    vector and FTS tables, so that single operation is left out of the scan; every other
    operation and the two drift-report models are still checked for all three words.
    """
    operations = {
        f"{method} {path}": operation
        for (method, path), operation in _feature_operations(application).items()
        if (method, path) != PERMITTED_REBUILD_OPERATION
    }
    assert operations, "no operation left to scan: the guard would pass against nothing"
    documented = json.dumps(
        [
            operations,
            TableReportResponse.model_json_schema(),
            DriftReportResponse.model_json_schema(),
        ]
    ).lower()
    for word in ("vector", "vec0", "rebuild"):
        assert word not in documented


@pytest.mark.parametrize(
    ("method", "path"),
    [
        # F002_DoD22: `POST {PREFIX}/rebuild` has left this list — fast/002 delivers it.
        ("POST", f"{PREFIX}/vector-index/rebuild"),
        ("POST", f"{TABLES_PATH}/models/rebuild"),
        # S030_003_DoD1: `GET {PREFIX}/export` has left this list — 030 step 003 delivers
        # it. `POST {PREFIX}/export` stays: 030 ships a GET download and nothing else.
        ("POST", f"{PREFIX}/export"),
        # S031_005_DoD11: `POST {PREFIX}/import` has left this list — 031 step 005 delivers it.
        # `GET {PREFIX}/import` replaces it: 031 ships a POST and nothing else, so the GET answers
        # 405 and this entry pins the route as POST-only rather than disarming the guard.
        ("GET", f"{PREFIX}/import"),
        ("GET", f"{PREFIX}/vector-index"),
    ],
)
def test_out_of_scope_routes_do_not_exist__DoD14(
    application: FastAPI, db_settings: Settings, method: str, path: str
) -> None:
    """DoD-14 — an administrator reaching for a rebuild route, or for an export or import verb
    this feature does not offer, finds none.

    S030_003_DoD1: the one admitted route is `GET .../export`; every other member of this
    list stays armed, so 031's Import and `fast/002`'s Rebuild still cannot appear early.

    S031_005_DoD11: the one admitted import route is `POST .../import`; `fast/002`'s Rebuild
    entries and 030's `POST .../export` and `GET .../vector-index` entries all stay armed.

    F002_DoD22: fast/002 delivers `POST .../rebuild`, so that one entry has left the list; the
    other rebuild-shaped paths (`.../vector-index/rebuild`, `.../tables/models/rebuild`) and the
    rest stay armed.
    """
    assert _admin(application, db_settings).request(method, path).status_code in (404, 405)
