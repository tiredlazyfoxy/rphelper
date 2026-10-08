"""Tests for the transfer router's three roleplayer export routes — feature 030, step 003.

Covered routes: ``GET /api/export``, ``GET /api/characters/{character_id}/export`` and
``GET /api/sessions/{session_id}/export``.

Every expected value comes from ``docs/plans/030.export-granularities/003.export-routes.md``
(its Interface intent and DoD-3 .. DoD-10), from ``003.context.md`` (why the three routes live
in ``routers/transfer.py`` and why they answer a raw ``Response``), and from the feature
``context.md`` — §"Routes" (the guards, the 200/``application/json``/``Content-Disposition``
contract and "the filename **never** embeds user content: no name, no title, no id"),
§"Granularity boundaries" (what each envelope carries) and §"Cross-cutting constraints"
(R5: a foreign **or** missing character is ``character_not_found`` 404 and a foreign or missing
session is ``session_not_found`` 404 — **there is no 403 for a foreign row**). Bindings come
from ``## Skeleton`` in ``status.md`` (step 003: the four paths, the handler names and the
attachment shape; steps 001/002 for the envelope keys). Nothing is read from the
implementation.

The admin route ``GET /api/admin/database/export`` (DoD-1, DoD-2) lives in
``test_admin_db_export.py``.

The application is always the real factory's (``create_app()``), pinned to the per-test
``tmp_path`` database through ``dependency_overrides[get_settings]``. Each signed-in caller
gets its own ``TestClient`` carrying exactly one session cookie, so no cookie leaks between
users. ``conftest.py`` is untouched: every fixture and helper below is file-local, following
``tests/test_characters_router.py`` and ``tests/test_memos_router.py``.

Seeding is by raw insert over the ``schema.*`` Table objects (the step-002 idiom), so no memo
route and no embedding provider is involved. Owner A has a live character with a setup, a
session and a memo at every one of the four scopes, plus a **sibling** character with its own
session and session memo; owner B has a character and a session of their own. Ids are all
above 2**60.

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

CHARACTERS_PATH = "/api/characters"
SESSIONS_PATH = "/api/sessions"
USER_EXPORT_PATH = "/api/export"
LOGIN_PATH = "/api/auth/login"

#: The OpenAPI path templates of the two parameterised export routes (``## Skeleton``, step 003).
CHARACTER_EXPORT_TEMPLATE = "/api/characters/{character_id}/export"
SESSION_EXPORT_TEMPLATE = "/api/sessions/{session_id}/export"

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

BASE = 1_152_921_504_606_847_000

USER_A = BASE + 1
USER_B = BASE + 2

CHAR_A = BASE + 10
CHAR_A_SIBLING = BASE + 11
CHAR_B = BASE + 12

SETUP_A = BASE + 20

SESSION_A = BASE + 30
SESSION_A_SIBLING = BASE + 31
SESSION_B = BASE + 32

MSG_A = BASE + 40
MSG_A_SIBLING = BASE + 41
MSG_B = BASE + 42

MEMO_A_USER = BASE + 50
MEMO_A_CHARACTER = BASE + 51
MEMO_A_SETUP = BASE + 52
MEMO_A_SESSION = BASE + 53
MEMO_A_SIBLING_SESSION = BASE + 54
MEMO_B_USER = BASE + 55

#: Ids that exist for nobody (DoD-7: indistinguishable from another owner's id).
UNKNOWN_CHARACTER_ID = BASE + 900_001
UNKNOWN_SESSION_ID = BASE + 900_002

PLAYER_A_NAME = "aster"
PLAYER_A_PASSWORD = "a quiet river at dusk"
PLAYER_B_NAME = "briar"
PLAYER_B_PASSWORD = "salt and lantern light"

#: DoD-3 — distinctive user content that the opaque filename must never carry.
CHARACTER_NAME = "Zephyrine Quillhaven-XQ7"
SESSION_TITLE = "Nightfall over Brassgate-VV9"
SETUP_NAME = "The Lantern Wharf-LW3"

EXPORT_FORMAT = "rphelper-export"
NOT_AUTHENTICATED = "not_authenticated"
CHARACTER_NOT_FOUND = "character_not_found"
SESSION_NOT_FOUND = "session_not_found"

#: `context.md` §"Granularity boundaries" — owner A's memos at each granularity.
USER_MEMO_IDS = {
    MEMO_A_USER,
    MEMO_A_CHARACTER,
    MEMO_A_SETUP,
    MEMO_A_SESSION,
    MEMO_A_SIBLING_SESSION,
}
CHARACTER_MEMO_IDS = {MEMO_A_CHARACTER, MEMO_A_SETUP, MEMO_A_SESSION}
SESSION_MEMO_IDS = {MEMO_A_SESSION}


# --- fixtures ------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _quiet_factory_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the factory's logging call so these tests touch no global sinks."""
    monkeypatch.setattr("app.main.configure_logging", lambda settings: None)


def _insert(engine: Engine, table: Table, **values: Any) -> None:
    with engine.begin() as connection:
        connection.execute(table.insert().values(**values))


def _insert_user(engine: Engine, *, user_id: int, username: str, password: str) -> None:
    _insert(
        engine,
        schema.users,
        id=user_id,
        username=username,
        password_hash=hash_password(password),
        role=Role.ROLEPLAYER,
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

    _insert_user(engine, user_id=USER_A, username=PLAYER_A_NAME, password=PLAYER_A_PASSWORD)
    _insert_user(engine, user_id=USER_B, username=PLAYER_B_NAME, password=PLAYER_B_PASSWORD)

    _insert_character(engine, character_id=CHAR_A, user_id=USER_A, name=CHARACTER_NAME)
    _insert_character(engine, character_id=CHAR_A_SIBLING, user_id=USER_A, name="the understudy")
    _insert_character(engine, character_id=CHAR_B, user_id=USER_B, name="Bob's own")

    _insert_setup(engine, setup_id=SETUP_A, user_id=USER_A, character_id=CHAR_A, name=SETUP_NAME)

    _insert_session(
        engine, session_id=SESSION_A, user_id=USER_A, character_id=CHAR_A, setup_id=SETUP_A
    )
    _insert_session(
        engine, session_id=SESSION_A_SIBLING, user_id=USER_A, character_id=CHAR_A_SIBLING
    )
    _insert_session(engine, session_id=SESSION_B, user_id=USER_B, character_id=CHAR_B)

    _insert_message(engine, message_id=MSG_A, user_id=USER_A, session_id=SESSION_A, text="A line.")
    _insert_message(
        engine, message_id=MSG_A_SIBLING, user_id=USER_A, session_id=SESSION_A_SIBLING, text="Sibling line."
    )
    _insert_message(engine, message_id=MSG_B, user_id=USER_B, session_id=SESSION_B, text="Bob's line.")

    for memo_id, scope, scope_id, body in (
        (MEMO_A_USER, "user", USER_A, "Everywhere."),
        (MEMO_A_CHARACTER, "character", CHAR_A, "About Zephyrine."),
        (MEMO_A_SETUP, "setup", SETUP_A, "At the wharf."),
        (MEMO_A_SESSION, "session", SESSION_A, SESSION_TITLE),
        (MEMO_A_SIBLING_SESSION, "session", SESSION_A_SIBLING, "The sibling session only."),
    ):
        _insert_memo(engine, memo_id=memo_id, user_id=USER_A, scope=scope, scope_id=scope_id, body=body)
    _insert_memo(engine, memo_id=MEMO_B_USER, user_id=USER_B, scope="user", scope_id=USER_B, body="Bob's.")


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database with the registry applied and the two owners' material seeded."""
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


def _player_b(application: FastAPI, settings: Settings) -> TestClient:
    return _as(application, settings, PLAYER_B_NAME, PLAYER_B_PASSWORD)


# --- exact paths ---------------------------------------------------------------------


def _character_export_path(character_id: Any) -> str:
    return f"{CHARACTERS_PATH}/{character_id}/export"


def _session_export_path(session_id: Any) -> str:
    return f"{SESSIONS_PATH}/{session_id}/export"


# --- envelope / registry helpers (every expectation is computed, never a literal) -----


def _table(name: str) -> Table:
    return schema.metadata.tables[name]


def _primary_key_name(table: Table) -> str:
    names = [column.name for column in table.primary_key.columns]
    assert len(names) == 1, f"{table.name} is expected to have a single-column primary key"
    return names[0]


def _is_id_column(column: Column[Any]) -> bool:
    """`context.md` §"Row serialization rules" — the three arms of the id-column rule."""
    return bool(
        column.primary_key or column.foreign_keys or column.name == "id" or column.name.endswith("_id")
    )


def _ids(rows: list[dict[str, Any]], table_name: str) -> set[int]:
    key = _primary_key_name(_table(table_name))
    return {int(row[key]) for row in rows}


def _assert_envelope(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error, dict)
    assert error["code"] == code
    return body


def _export(response: httpx.Response, granularity: str) -> dict[str, Any]:
    """The step's download contract: 200, `application/json`, and the envelope's two header keys."""
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].split(";")[0] == "application/json"
    envelope = response.json()
    assert isinstance(envelope, dict)
    assert envelope["format"] == EXPORT_FORMAT
    assert envelope["granularity"] == granularity
    return envelope


def _payload_of(envelope: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    payload = envelope["payload"]
    assert isinstance(payload, dict)
    return payload


def _rows(envelope: dict[str, Any], table_name: str) -> list[dict[str, Any]]:
    rows = _payload_of(envelope)[table_name]
    assert isinstance(rows, list)
    return rows


def _attachment_pattern(granularity: str) -> re.Pattern[str]:
    """`context.md` §"Routes": `attachment; filename="rphelper-<granularity>-<timestamp>.json"`."""
    return re.compile(rf'^attachment; filename="rphelper-{granularity}-(?P<timestamp>[^"/\\]+)\.json"$')


def _assert_attachment_header(response: httpx.Response, granularity: str) -> str:
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment")
    match = _attachment_pattern(granularity).match(disposition)
    assert match is not None, disposition
    timestamp = match.group("timestamp")
    assert any(character.isdigit() for character in timestamp), disposition
    return disposition


def _assert_id_values_are_strings(envelope: dict[str, Any]) -> None:
    """DoD-9 — every id column of every exported row arrives as a decimal string (or null)."""
    payload = _payload_of(envelope)
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


def _parameter_schema_types(parameter: dict[str, Any]) -> set[str]:
    declared = parameter.get("schema", {})
    types = {declared["type"]} if "type" in declared else set()
    for member in declared.get("anyOf", []):
        if "type" in member:
            types.add(member["type"])
    return types


# --- DoD-3: the attachment header is opaque -------------------------------------------


#: The three roleplayer routes with the granularity `context.md` §"Routes" assigns each.
ROUTE_GRANULARITIES = [
    (USER_EXPORT_PATH, "user"),
    (_character_export_path(CHAR_A), "character"),
    (_session_export_path(SESSION_A), "session"),
]
ROUTE_IDS = ["user", "character", "session"]


@pytest.mark.parametrize(("path", "granularity"), ROUTE_GRANULARITIES, ids=ROUTE_IDS)
def test_every_route_names_an_opaque_attachment_for_its_granularity__S030_003_DoD3(
    application: FastAPI, db_settings: Settings, path: str, granularity: str
) -> None:
    """DoD-3 — US-078 opacity: `attachment; filename="rphelper-<granularity>-<timestamp>.json"`,
    and the seeded character name, session memo body, setup name and ids appear nowhere in it."""
    client = _player_a(application, db_settings)

    response = client.get(path)

    _export(response, granularity)
    disposition = _assert_attachment_header(response, granularity)
    for secret in (CHARACTER_NAME, SESSION_TITLE, SETUP_NAME, PLAYER_A_NAME):
        assert secret not in disposition
        assert secret.lower() not in disposition.lower()
    for identifier in (USER_A, CHAR_A, SETUP_A, SESSION_A, MEMO_A_SESSION):
        assert str(identifier) not in disposition


# --- DoD-4: the user export -----------------------------------------------------------


def test_the_user_export_answers_the_callers_own_row_without_the_password_hash__S030_003_DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-4 — US-079.AC-1: 200, granularity `user`, the caller's one `users` row minus
    `password_hash`, and the caller's memos."""
    client = _player_a(application, db_settings)

    response = client.get(USER_EXPORT_PATH)

    envelope = _export(response, "user")
    users = _rows(envelope, "users")
    assert len(users) == 1
    assert users[0]["id"] == str(USER_A)
    assert users[0]["username"] == PLAYER_A_NAME
    assert "password_hash" not in users[0]
    assert USER_MEMO_IDS <= _ids(_rows(envelope, "memos"), "memos")


def test_the_user_export_carries_no_password_hash_anywhere_in_its_bytes__S030_003_DoD4(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-4 — the exclusion is of the value as well as the key: the stored hash of the
    caller's password does not appear in the downloaded body."""
    with engine.connect() as connection:
        row = connection.execute(schema.users.select().where(schema.users.c.id == USER_A)).one()
    stored = str(row._mapping["password_hash"])
    client = _player_a(application, db_settings)

    response = client.get(USER_EXPORT_PATH)

    _export(response, "user")
    assert stored not in response.text


def test_the_user_export_carries_no_other_owners_user_row__S030_003_DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-4 — "its `users` row is the caller's": B's own export answers B's row, not A's."""
    client = _player_b(application, db_settings)

    envelope = _export(client.get(USER_EXPORT_PATH), "user")

    assert _ids(_rows(envelope, "users"), "users") == {USER_B}
    assert _ids(_rows(envelope, "memos"), "memos") == {MEMO_B_USER}


# --- DoD-5: the character export ------------------------------------------------------


def test_the_character_export_answers_that_character_and_its_memos__S030_003_DoD5(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-5 — US-080.AC-1: 200, granularity `character`, the one root character row, and the
    memos `context.md` scopes to it (character, its setups, its sessions) — not the sibling's."""
    client = _player_a(application, db_settings)

    envelope = _export(client.get(_character_export_path(CHAR_A)), "character")

    assert _ids(_rows(envelope, "characters"), "characters") == {CHAR_A}
    assert _ids(_rows(envelope, "memos"), "memos") == CHARACTER_MEMO_IDS


# --- DoD-6: the session export --------------------------------------------------------


def test_the_session_export_answers_only_that_sessions_memos__S030_003_DoD6(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-6 — US-081.AC-1: 200, granularity `session`, the one root session row, and memos
    scoped `(session, this session)` **only** — no user, character or setup memo."""
    client = _player_a(application, db_settings)

    envelope = _export(client.get(_session_export_path(SESSION_A)), "session")

    assert _ids(_rows(envelope, "sessions"), "sessions") == {SESSION_A}
    assert _ids(_rows(envelope, "memos"), "memos") == SESSION_MEMO_IDS


def test_a_sibling_sessions_export_carries_its_own_memo_only__S030_003_DoD6(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-6 — the "only" half from the other side: the sibling session's export carries the
    sibling's session memo and not the first session's."""
    client = _player_a(application, db_settings)

    envelope = _export(client.get(_session_export_path(SESSION_A_SIBLING)), "session")

    assert _ids(_rows(envelope, "sessions"), "sessions") == {SESSION_A_SIBLING}
    assert _ids(_rows(envelope, "memos"), "memos") == {MEMO_A_SIBLING_SESSION}


# --- DoD-7: a foreign or missing root is a 404, never a 403 ---------------------------


@pytest.mark.parametrize("character_id", [CHAR_B, UNKNOWN_CHARACTER_ID], ids=["foreign", "unknown"])
def test_a_foreign_or_unknown_character_answers_404_character_not_found__S030_003_DoD7(
    application: FastAPI, db_settings: Settings, character_id: int
) -> None:
    """DoD-7 — R5: both answer 404 `character_not_found` in the standard envelope, and a
    foreign row is **not** a 403."""
    client = _player_a(application, db_settings)

    response = client.get(_character_export_path(character_id))

    assert response.status_code != 403
    _assert_envelope(response, 404, CHARACTER_NOT_FOUND)


@pytest.mark.parametrize("session_id", [SESSION_B, UNKNOWN_SESSION_ID], ids=["foreign", "unknown"])
def test_a_foreign_or_unknown_session_answers_404_session_not_found__S030_003_DoD7(
    application: FastAPI, db_settings: Settings, session_id: int
) -> None:
    """DoD-7 — R5: both answer 404 `session_not_found` in the standard envelope, and a foreign
    row is **not** a 403."""
    client = _player_a(application, db_settings)

    response = client.get(_session_export_path(session_id))

    assert response.status_code != 403
    _assert_envelope(response, 404, SESSION_NOT_FOUND)


def test_a_foreign_root_is_indistinguishable_from_an_unknown_one__S030_003_DoD7(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-7 — the two refusals carry the same status and the same body, so a foreign id leaks
    nothing about another owner's material."""
    client = _player_a(application, db_settings)

    foreign_character = client.get(_character_export_path(CHAR_B))
    unknown_character = client.get(_character_export_path(UNKNOWN_CHARACTER_ID))
    foreign_session = client.get(_session_export_path(SESSION_B))
    unknown_session = client.get(_session_export_path(UNKNOWN_SESSION_ID))

    assert foreign_character.status_code == unknown_character.status_code == 404
    assert foreign_character.json() == unknown_character.json()
    assert foreign_session.status_code == unknown_session.status_code == 404
    assert foreign_session.json() == unknown_session.json()


# --- DoD-8: every route is behind the login cookie ------------------------------------


@pytest.mark.parametrize(
    "path",
    [USER_EXPORT_PATH, _character_export_path(CHAR_A), _session_export_path(SESSION_A)],
    ids=["user", "character", "session"],
)
def test_every_route_answers_401_without_a_login_cookie__S030_003_DoD8(
    application: FastAPI, path: str
) -> None:
    """DoD-8 — the router-level `require_user` guard: 401 `not_authenticated` on all three."""
    response = _anonymous(application).get(path)

    _assert_envelope(response, 401, NOT_AUTHENTICATED)


# --- DoD-9: ids are strings on the wire; a non-numeric path id never reaches a service -


@pytest.mark.parametrize(("path", "granularity"), ROUTE_GRANULARITIES, ids=ROUTE_IDS)
def test_every_id_in_a_response_body_is_a_json_string__S030_003_DoD9(
    application: FastAPI, db_settings: Settings, path: str, granularity: str
) -> None:
    """DoD-9 — the JSON id boundary holds through the raw `Response`: every id column of every
    exported row is a decimal string, or null."""
    client = _player_a(application, db_settings)

    envelope = _export(client.get(path), granularity)

    _assert_id_values_are_strings(envelope)


@pytest.mark.parametrize(
    "path",
    [_character_export_path("abc"), _session_export_path("abc")],
    ids=["character", "session"],
)
def test_a_non_numeric_path_id_is_refused_with_422__S030_003_DoD9(
    application: FastAPI, db_settings: Settings, path: str
) -> None:
    """DoD-9 — a non-numeric path id is a native 422, and not either not-found envelope: the
    refusal happens in validation, before any service runs."""
    client = _player_a(application, db_settings)

    response = client.get(path)

    assert response.status_code == 422, response.text
    assert CHARACTER_NOT_FOUND not in response.text
    assert SESSION_NOT_FOUND not in response.text


@pytest.mark.parametrize(
    ("template", "parameter_name"),
    [
        (CHARACTER_EXPORT_TEMPLATE, "character_id"),
        (SESSION_EXPORT_TEMPLATE, "session_id"),
    ],
    ids=["character", "session"],
)
def test_each_path_id_is_declared_an_integer_path_parameter_with_a_422__S030_003_DoD9(
    application: FastAPI, template: str, parameter_name: str
) -> None:
    """DoD-9 — the declaration that makes the 422 precede the service: the inbound snowflake
    alias puts one integer path parameter and a 422 response on each route."""
    operation = application.openapi()["paths"][template]["get"]
    path_parameters = [p for p in operation.get("parameters", []) if p["in"] == "path"]

    assert [p["name"] for p in path_parameters] == [parameter_name]
    assert "integer" in _parameter_schema_types(path_parameters[0])
    assert "422" in operation["responses"]


def test_the_user_export_route_declares_no_parameter__S030_003_DoD9(application: FastAPI) -> None:
    """DoD-9 — `GET /api/export` takes the caller's id from the session, so it declares no path
    or query parameter at all."""
    operation = application.openapi()["paths"][USER_EXPORT_PATH]["get"]

    assert operation.get("parameters", []) == []


# --- DoD-10: the earlier routers still answer -----------------------------------------


def test_earlier_routes_still_answer_with_the_transfer_router_registered__S030_003_DoD10(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-10 — one smoke request each: the character item read and the session item read are
    unaffected by the three longer `/export` paths registered after them."""
    client = _player_a(application, db_settings)

    character = client.get(f"{CHARACTERS_PATH}/{CHAR_A}")
    session = client.get(f"{SESSIONS_PATH}/{SESSION_A}")

    assert character.status_code == 200, character.text
    assert character.json()["id"] == str(CHAR_A)
    assert character.json()["name"] == CHARACTER_NAME
    assert session.status_code == 200, session.text
    assert session.json()["id"] == str(SESSION_A)
    assert session.json()["character_id"] == str(CHAR_A)
