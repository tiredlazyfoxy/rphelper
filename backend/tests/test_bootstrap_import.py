"""Tests for ``POST /api/bootstrap/import`` and ``restore_from_export`` — fast/003.

Spec: ``docs/plans/fast/003.bootstrap-from-export/plan.md`` (Interface intent + Definition
of done) and ``context.md`` (Decisions 1-5, Accepted consequences). Bindings come from the
``## Skeleton`` record in that folder's ``status.md``:

* ``app.services.bootstrap.restore_from_export(connection, body) -> None``
* ``POST /api/bootstrap/import`` on the existing guarded bootstrap router, raw JSON object
  body, 204 with no body and no cookie.

Covers DoD-1 .. DoD-11. DoD-12 is the verifier's suite gate (no new test).

"Real export" (plan DoD preamble): a **source** database on its own file, seeded with two
admins, one roleplayer and a character owned by a non-first user, every user with a known
plaintext password; the export is built by ``export_database`` from it. The **target** is
the unconfigured, empty file of ``db_engine`` / ``db_settings``. The seed helpers are
defined here (``context.md``: a new test file re-creates equivalents rather than importing
from another test module).
"""

import copy
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from loguru import logger
from sqlalchemy import Engine, select, text

from app.config import Settings, get_settings
from app.db import schema
from app.db.engine import get_engine
from app.errors import AlreadyConfiguredError
from app.main import create_app
from app.roles import Role
from app.services.bootstrap import is_configured, restore_from_export
from app.services.passwords import hash_password
from app.services.transfer import export_database

IMPORT_PATH = "/api/bootstrap/import"
CREATE_PATH = "/api/bootstrap/create"
HEALTH_PATH = "/api/health"
LOGIN_PATH = "/api/auth/login"

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

#: Seeded ids, above 2**60, in a range no create-path id is expected to land on.
SOURCE_BASE = 1_152_921_504_606_850_000
FIRST_ADMIN_ID = SOURCE_BASE + 1
SECOND_ADMIN_ID = SOURCE_BASE + 2
PLAYER_ID = SOURCE_BASE + 3
CHARACTER_ID = SOURCE_BASE + 20

#: Distinctive usernames and plaintext passwords, so finding one in a log record is proof
#: of a leak (DoD-11).
FIRST_ADMIN_USERNAME = "restoreqx-first-admin"
SECOND_ADMIN_USERNAME = "restoreqx-second-admin"
PLAYER_USERNAME = "restoreqx-roleplayer"
FIRST_ADMIN_PASSWORD = "restoreqx first admin plaintext 7c1"
SECOND_ADMIN_PASSWORD = "restoreqx second admin plaintext 9d4"
PLAYER_PASSWORD = "restoreqx roleplayer plaintext 2b8"
WRONG_PASSWORD = "restoreqx certainly not any password"

SEEDED_USERS: tuple[tuple[int, str, Role, str], ...] = (
    (FIRST_ADMIN_ID, FIRST_ADMIN_USERNAME, Role.ADMIN, FIRST_ADMIN_PASSWORD),
    (SECOND_ADMIN_ID, SECOND_ADMIN_USERNAME, Role.ADMIN, SECOND_ADMIN_PASSWORD),
    (PLAYER_ID, PLAYER_USERNAME, Role.ROLEPLAYER, PLAYER_PASSWORD),
)

SECRETS: tuple[str, ...] = tuple(
    value for _id, username, _role, password in SEEDED_USERS for value in (username, password)
)

#: The create path's own administrator (DoD-6, DoD-8).
CREATE_USERNAME = "createqx-founder"
CREATE_PASSWORD = "createqx founder password"


# --- fixtures ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _quiet_factory_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the factory's logging call so these tests touch no global sinks."""
    monkeypatch.setattr("app.main.configure_logging", lambda settings: None)


@pytest.fixture
def application(db_settings: Settings, db_engine: Engine) -> Iterator[FastAPI]:
    """The factory's application, pinned to the per-test (target) database."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: db_settings
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client(application: FastAPI) -> TestClient:
    return TestClient(application)


@pytest.fixture
def source_engine(db_settings: Settings, tmp_path: Path) -> Engine:
    """The exported instance, on its own file inside the per-test ``tmp_path``."""
    source_settings = db_settings.model_copy(
        update={"data_dir": tmp_path / "source", "db_filename": "source.sqlite"}
    )
    engine = get_engine(source_settings)
    with engine.begin() as connection:
        schema.metadata.create_all(connection)
    _seed_source(engine)
    return engine


@pytest.fixture
def real_export(source_engine: Engine) -> dict[str, Any]:
    """The ``database`` envelope ``export_database`` builds from the seeded source."""
    with source_engine.connect() as connection:
        built = export_database(connection)
    decoded: dict[str, Any] = json.loads(json.dumps(built))
    return decoded


# --- seed helpers -----------------------------------------------------------------------


def _seed_source(engine: Engine) -> None:
    with engine.begin() as connection:
        for user_id, username, role, password in SEEDED_USERS:
            connection.execute(
                schema.users.insert().values(
                    id=user_id,
                    username=username,
                    password_hash=hash_password(password),
                    role=role,
                    is_enabled=True,
                    rp_language=None,
                    preferred_language=None,
                    last_login_at=None,
                    created_at=TIMESTAMP,
                    updated_at=TIMESTAMP,
                )
            )
        # The character belongs to a non-first user (the roleplayer).
        connection.execute(
            schema.characters.insert().values(
                id=CHARACTER_ID,
                user_id=PLAYER_ID,
                name="Restored Aria",
                sheet="The sheet of Restored Aria.",
                archived_at=None,
                model_server_id=None,
                model_name=None,
                system_prompt=None,
                tool_memo_search=True,
                tool_session_search=False,
                tool_web_search=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


# --- observation helpers ----------------------------------------------------------------


def _table_exists(engine: Engine, name: str) -> bool:
    with engine.connect() as connection:
        found = connection.execute(
            text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name"),
            {"name": name},
        ).first()
    return found is not None


def _table_names(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        rows = connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type = 'table'").all()
    return {row[0] for row in rows}


def _users(engine: Engine) -> list[tuple[int, str, Role, str]]:
    """``(id, username, role, password_hash)`` of every user, id ascending; [] if no table."""
    if not _table_exists(engine, "users"):
        return []
    query = select(
        schema.users.c.id, schema.users.c.username, schema.users.c.role, schema.users.c.password_hash
    ).order_by(schema.users.c.id)
    with engine.connect() as connection:
        rows = connection.execute(query).all()
    return [(int(row[0]), str(row[1]), Role(row[2]), str(row[3])) for row in rows]


def _all_user_rows(engine: Engine) -> list[dict[str, Any]]:
    if not _table_exists(engine, "users"):
        return []
    with engine.connect() as connection:
        result = connection.execute(select(schema.users).order_by(schema.users.c.id))
        return [dict(row) for row in result.mappings().all()]


def _auth_session_rows(engine: Engine) -> list[Any]:
    if not _table_exists(engine, "auth_sessions"):
        return []
    with engine.connect() as connection:
        return list(connection.execute(select(schema.auth_sessions)).all())


def _configured(engine: Engine) -> bool:
    with engine.connect() as connection:
        return is_configured(connection)


def _restore(client: TestClient, body: Any) -> httpx.Response:
    return client.post(IMPORT_PATH, json=body)


def _create(client: TestClient) -> httpx.Response:
    return client.post(CREATE_PATH, json={"username": CREATE_USERNAME, "password": CREATE_PASSWORD})


def _login(client: TestClient, username: str, password: str) -> httpx.Response:
    return client.post(LOGIN_PATH, json={"username": username, "password": password})


def _assert_error(response: httpx.Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert isinstance(body.get("error"), dict)
    assert body["error"]["code"] == code


def _without(body: dict[str, Any], key: str) -> dict[str, Any]:
    mutated = copy.deepcopy(body)
    assert key in mutated, f"the real export carries {key!r}"
    del mutated[key]
    return mutated


def _with_granularity(body: dict[str, Any], granularity: str) -> dict[str, Any]:
    mutated = copy.deepcopy(body)
    assert mutated["granularity"] == "database"
    mutated["granularity"] = granularity
    return mutated


def _with_duplicated_user_row(body: dict[str, Any]) -> dict[str, Any]:
    """The first ``users`` row appears twice — a primary-key / UNIQUE violation."""
    mutated = copy.deepcopy(body)
    rows = mutated["payload"]["users"]
    assert len(rows) == len(SEEDED_USERS)
    rows.append(copy.deepcopy(rows[0]))
    return mutated


INVALID_ENVELOPES = {
    "user_granularity": lambda body: _with_granularity(body, "user"),
    "missing_schema_version": lambda body: _without(body, "schema_version"),
    "missing_granularity": lambda body: _without(body, "granularity"),
}


@contextmanager
def _captured_logs(caplog: pytest.LogCaptureFixture) -> Iterator[list[tuple[str, str]]]:
    """Every record emitted while the block runs, as ``(logger name, rendered text)``.

    loguru is the project's logger (``deployment.md``); stdlib records under ``app`` are
    captured too, so a stdlib call site would not escape the sweep.
    """
    records: list[tuple[str, str]] = []

    def sink(message: Any) -> None:
        record = message.record
        parts = [str(message), str(record["message"]), repr(record["extra"])]
        if record["exception"] is not None:
            parts.append(repr(record["exception"].value))
        records.append((str(record["name"]), "\n".join(parts)))

    caplog.clear()
    caplog.set_level(logging.DEBUG, logger="app")
    handler_id = logger.add(sink, level=0, format="{level} {name} {message}")
    try:
        yield records
    finally:
        logger.remove(handler_id)
        for stdlib_record in caplog.records:
            rendered = stdlib_record.getMessage()
            if stdlib_record.exc_info and stdlib_record.exc_info[1] is not None:
                rendered += "\n" + repr(stdlib_record.exc_info[1])
            records.append((stdlib_record.name, rendered))
        caplog.clear()


def _is_bootstrap_record(name: str, rendered: str) -> bool:
    """A record from the application's bootstrap code: an ``app.*`` logger that names
    bootstrap (the module's own name, or the ``bootstrap outcome=...`` line).

    Restricted to ``app.*`` so a framework request line that merely quotes the URL
    ``/api/bootstrap/import`` cannot satisfy it."""
    if not (name == "app" or name.startswith("app.")):
        return False
    return "bootstrap" in name.lower() or "bootstrap" in rendered.lower()


# === DoD-1 ================================================================================


def test_restore_with_a_real_export_answers_204_with_an_empty_body__DoD1(
    client: TestClient, real_export: dict[str, Any]
) -> None:
    """DoD-1 — a real export on an unconfigured instance answers 204, no body."""
    response = _restore(client, real_export)
    assert response.status_code == 204, response.text
    assert response.content == b""


# === DoD-2 ================================================================================


def test_restored_users_are_exactly_the_source_users__DoD2(
    client: TestClient, real_export: dict[str, Any], source_engine: Engine, db_engine: Engine
) -> None:
    """DoD-2 — same ids, usernames, roles and password hashes; both admins present."""
    source_users = _users(source_engine)
    assert [row[0] for row in source_users] == sorted([FIRST_ADMIN_ID, SECOND_ADMIN_ID, PLAYER_ID])

    assert _restore(client, real_export).status_code == 204

    restored = _users(db_engine)
    assert restored == source_users
    admins = sorted(row[0] for row in restored if row[2] == Role.ADMIN)
    assert admins == sorted([FIRST_ADMIN_ID, SECOND_ADMIN_ID])
    assert {row[1] for row in restored} == {FIRST_ADMIN_USERNAME, SECOND_ADMIN_USERNAME, PLAYER_USERNAME}


def test_restored_character_keeps_its_id_and_owner__DoD2(
    client: TestClient, real_export: dict[str, Any], db_engine: Engine
) -> None:
    """DoD-2 — the seeded character exists in the target under the same id and owner."""
    assert _restore(client, real_export).status_code == 204
    with db_engine.connect() as connection:
        rows = connection.execute(
            select(schema.characters.c.id, schema.characters.c.user_id)
        ).all()
    assert [(int(row[0]), int(row[1])) for row in rows] == [(CHARACTER_ID, PLAYER_ID)]


# === DoD-3 ================================================================================


def test_restore_sets_no_cookie_and_opens_no_session__DoD3(
    client: TestClient, real_export: dict[str, Any], db_engine: Engine
) -> None:
    """DoD-3 — no ``Set-Cookie`` on the 204, and ``auth_sessions`` is empty afterwards."""
    response = _restore(client, real_export)
    assert response.status_code == 204
    assert response.headers.get_list("set-cookie") == []
    assert len(client.cookies) == 0
    assert _auth_session_rows(db_engine) == []


# === DoD-4 ================================================================================


@pytest.mark.parametrize(
    ("username", "password"),
    [
        (SECOND_ADMIN_USERNAME, SECOND_ADMIN_PASSWORD),
        (PLAYER_USERNAME, PLAYER_PASSWORD),
        (FIRST_ADMIN_USERNAME, FIRST_ADMIN_PASSWORD),
    ],
    ids=["non-first-admin", "roleplayer", "first-admin"],
)
def test_restored_credentials_sign_in__DoD4(
    application: FastAPI, real_export: dict[str, Any], username: str, password: str
) -> None:
    """DoD-4 — US-002.AC-2: the source credentials sign in through the existing login route."""
    assert _restore(TestClient(application), real_export).status_code == 204
    response = _login(TestClient(application), username, password)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    "username", [SECOND_ADMIN_USERNAME, PLAYER_USERNAME], ids=["non-first-admin", "roleplayer"]
)
def test_wrong_password_for_a_restored_user_is_refused__DoD4(
    application: FastAPI, real_export: dict[str, Any], username: str
) -> None:
    """DoD-4 — a wrong password for a restored user is still refused."""
    assert _restore(TestClient(application), real_export).status_code == 204
    response = _login(TestClient(application), username, WRONG_PASSWORD)
    assert response.status_code != 200
    assert response.status_code in (400, 401)


# === DoD-5 ================================================================================


def test_after_restore_health_reports_configured__DoD5(
    client: TestClient, real_export: dict[str, Any]
) -> None:
    """DoD-5 — ``GET /api/health`` reports the instance configured after a restore."""
    assert client.get(HEALTH_PATH).json()["configured"] is False
    assert _restore(client, real_export).status_code == 204
    assert client.get(HEALTH_PATH).json()["configured"] is True


def test_after_restore_both_bootstrap_routes_answer_already_configured__DoD5(
    client: TestClient, real_export: dict[str, Any], db_engine: Engine
) -> None:
    """DoD-5 — UC-003: create and import both answer 409 ``already_configured``."""
    assert _restore(client, real_export).status_code == 204
    users_after_restore = _users(db_engine)

    _assert_error(_create(client), 409, "already_configured")
    _assert_error(_restore(client, real_export), 409, "already_configured")

    assert _users(db_engine) == users_after_restore


# === DoD-6 ================================================================================


@pytest.mark.parametrize("case", sorted(INVALID_ENVELOPES))
def test_invalid_envelope_answers_400_export_invalid__DoD6(
    client: TestClient, real_export: dict[str, Any], case: str
) -> None:
    """DoD-6 — a non-``database`` granularity or a missing envelope field is ``export_invalid``."""
    response = _restore(client, INVALID_ENVELOPES[case](real_export))
    _assert_error(response, 400, "export_invalid")
    assert response.headers.get_list("set-cookie") == []


@pytest.mark.parametrize("case", sorted(INVALID_ENVELOPES))
def test_invalid_envelope_leaves_no_schema_and_create_still_works__DoD6(
    client: TestClient, real_export: dict[str, Any], db_engine: Engine, case: str
) -> None:
    """DoD-6 — afterwards: no ``users`` table, unconfigured, and create answers 201."""
    assert _restore(client, INVALID_ENVELOPES[case](real_export)).status_code == 400

    assert _table_exists(db_engine, "users") is False
    assert _configured(db_engine) is False
    assert client.get(HEALTH_PATH).json()["configured"] is False

    created = _create(client)
    assert created.status_code == 201, created.text


# === DoD-7 ================================================================================


def test_constraint_violating_payload_answers_400_export_invalid__DoD7(
    client: TestClient, real_export: dict[str, Any]
) -> None:
    """DoD-7 — a duplicated ``users`` row is refused as ``export_invalid``."""
    _assert_error(_restore(client, _with_duplicated_user_row(real_export)), 400, "export_invalid")


def test_constraint_violation_rolls_back_the_schema_too__DoD7(
    client: TestClient, real_export: dict[str, Any], db_engine: Engine
) -> None:
    """DoD-7 — the DDL created inside the transaction is rolled back with the import."""
    assert _restore(client, _with_duplicated_user_row(real_export)).status_code == 400

    assert _table_exists(db_engine, "users") is False
    assert _configured(db_engine) is False
    assert client.get(HEALTH_PATH).json()["configured"] is False


# === DoD-8 ================================================================================


def test_restore_on_an_instance_configured_by_create_is_refused__DoD8(
    client: TestClient, real_export: dict[str, Any], db_engine: Engine
) -> None:
    """DoD-8 — 409 ``already_configured``; the users table holds only the original admin."""
    created = _create(client)
    assert created.status_code == 201
    created_id = int(created.json()["id"])

    response = _restore(client, real_export)

    _assert_error(response, 409, "already_configured")
    users = _users(db_engine)
    assert [(row[0], row[1], row[2]) for row in users] == [(created_id, CREATE_USERNAME, Role.ADMIN)]


# === DoD-9 ================================================================================


@pytest.mark.parametrize(
    "body",
    [[], [{"granularity": "database"}], "a string", 42],
    ids=["empty-array", "array", "string", "number"],
)
def test_a_non_object_body_answers_422__DoD9(client: TestClient, db_engine: Engine, body: Any) -> None:
    """DoD-9 — a JSON body that is not an object answers 422."""
    response = _restore(client, body)
    assert response.status_code == 422
    assert _table_exists(db_engine, "users") is False


# === DoD-10 ===============================================================================


def test_service_refuses_a_configured_connection_and_changes_nothing__DoD10(
    client: TestClient, real_export: dict[str, Any], db_engine: Engine
) -> None:
    """DoD-10 — called directly (no router guard), the service raises and changes nothing."""
    assert _create(client).status_code == 201
    tables_before = _table_names(db_engine)
    rows_before = _all_user_rows(db_engine)
    sessions_before = _auth_session_rows(db_engine)
    assert len(rows_before) == 1

    with db_engine.connect() as connection:
        with pytest.raises(AlreadyConfiguredError):
            restore_from_export(connection, real_export)

    assert _table_names(db_engine) == tables_before
    assert _all_user_rows(db_engine) == rows_before
    assert _auth_session_rows(db_engine) == sessions_before


def test_service_restores_on_an_unconfigured_connection__DoD10(
    real_export: dict[str, Any], source_engine: Engine, db_engine: Engine
) -> None:
    """DoD-10 control — the same direct call on an unconfigured connection restores, so the
    refusal above is the configured check and not a general failure."""
    with db_engine.connect() as connection:
        restore_from_export(connection, real_export)
    assert _users(db_engine) == _users(source_engine)
    assert _configured(db_engine) is True


# === DoD-11 ===============================================================================


def test_restore_logs_carry_no_username_or_password__DoD11(
    client: TestClient,
    real_export: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """DoD-11 — across a failed and a successful restore no record carries a seeded
    username or plaintext password, and the success emits at least one bootstrap record."""
    with _captured_logs(caplog) as failed_records:
        failed = _restore(client, _with_duplicated_user_row(real_export))
    assert failed.status_code == 400

    with _captured_logs(caplog) as success_records:
        succeeded = _restore(client, real_export)
    assert succeeded.status_code == 204

    for name, rendered in failed_records + success_records:
        for secret in SECRETS:
            assert secret not in rendered, f"a log record from {name!r} carries seeded content"

    assert any(_is_bootstrap_record(name, rendered) for name, rendered in success_records), (
        f"no bootstrap log record for the successful restore: {success_records}"
    )
