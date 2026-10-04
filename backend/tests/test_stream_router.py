"""Tests for the stream router: the seven JSON routes of feature 012's wire contract.

Every expected value comes from ``docs/plans/012.messages-and-settle/004.stream-router.md``
(Interface intent + Definition of done), ``004.context.md`` and the feature ``context.md``
(the **Wire contract** — the seven routes, the eight-key ``Message`` object, the failure
table — plus **D2** zone-only edit, **D3** every content write bumps the session, **D9** text
validation, **D10** re-open, **D12** the route surface, **D14** partner filing, R5, R6, R10,
R11, R12). Bindings come from ``## Skeleton`` in ``status.md`` (step 004's full paths and
status codes; step 001's ``messages`` Table for the one raw insert DoD-5 needs).

Covers step 004 DoD-1 .. DoD-20. DoD-21 is ``[manual/live]`` and carries no test.

Amended by feature 014, step 001 (``docs/plans/014.entry-editing-and-copy-out/
001.settled-edit-backend.md``, D1 / D2): ``PATCH /api/messages/{id}`` now edits a settled
entry of any kind; only a buried message stays 409 ``message_not_editable``. 012 DoD-13's
settled-refusal cases are rewritten as successes; the 014 cases carry ``__S014_001_DoD<n>``.

The application is always the real factory's (``create_app()``), pinned to the per-test
database through ``dependency_overrides[get_settings]``. Each signed-in caller gets its own
``TestClient`` carrying exactly one session cookie. Characters come from 009's
``POST /api/characters``, sessions from 011's ``POST /api/characters/{id}/sessions`` with
``{}`` (no setup). ``conftest.py`` is untouched: every fixture below is file-local.
"""

import ast
import re
import time
from collections.abc import Iterator
from pathlib import Path
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
SESSIONS_PATH = "/api/sessions"
MESSAGES_PATH = "/api/messages"
LOGIN_PATH = "/api/auth/login"

TIMESTAMP = "2026-01-01T00:00:00+00:00"
RAW_ROW_TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

#: The fixed-width timestamp form (feature context, Test conventions).
TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00$")

PLAYER_A_ID = 9_400_001
PLAYER_A_NAME = "aster"
PLAYER_A_PASSWORD = "a quiet river at dusk"

PLAYER_B_ID = 9_400_002
PLAYER_B_NAME = "briar"
PLAYER_B_PASSWORD = "salt and lantern light"

#: Large decimal id strings no row holds ("Nobody's" ids, 004.context.md Test seeding).
UNKNOWN_SESSION_ID = "7250000000000000002"
UNKNOWN_MESSAGE_ID = "7250000000000000004"

#: The ``Message`` wire object's keys — eight in 012 (feature context, Wire contract).
#: Amended by feature 022, step 001 (D3, DoD-4): plus ``tool_name``, ``tool_status`` and
#: ``tool_args`` — eleven keys. Tests that pin the key set chain ``__S022_001_DoD4``.
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
}

NOT_AUTHENTICATED = "not_authenticated"
SESSION_NOT_FOUND = "session_not_found"
MESSAGE_NOT_FOUND = "message_not_found"
MESSAGE_NOT_EDITABLE = "message_not_editable"
ZONE_EMPTY = "zone_empty"
ZONE_NOT_EMPTY = "zone_not_empty"
NOTHING_TO_REOPEN = "nothing_to_reopen"

#: The seven stream routes as OpenAPI path templates (Wire contract).
STREAM_PATH_TEMPLATES = {
    "/api/sessions/{session_id}/entries",
    "/api/sessions/{session_id}/zone",
    "/api/sessions/{session_id}/zone/messages",
    "/api/sessions/{session_id}/settle",
    "/api/sessions/{session_id}/reopen",
    "/api/messages/{message_id}",
}

#: Sentinel: the key ``text`` is absent from the body.
_MISSING: Any = object()

STREAM_ROUTER_SOURCE = Path(__file__).resolve().parents[1] / "app" / "routers" / "stream.py"


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


def _session_path(session_id: Any) -> str:
    return f"{SESSIONS_PATH}/{session_id}"


def _entries_path(session_id: Any) -> str:
    return f"{SESSIONS_PATH}/{session_id}/entries"


def _zone_path(session_id: Any) -> str:
    return f"{SESSIONS_PATH}/{session_id}/zone"


def _zone_messages_path(session_id: Any) -> str:
    return f"{SESSIONS_PATH}/{session_id}/zone/messages"


def _settle_path(session_id: Any) -> str:
    return f"{SESSIONS_PATH}/{session_id}/settle"


def _reopen_path(session_id: Any) -> str:
    return f"{SESSIONS_PATH}/{session_id}/reopen"


def _message_path(message_id: Any) -> str:
    return f"{MESSAGES_PATH}/{message_id}"


# --- seeding and request helpers -----------------------------------------------------


def _assert_envelope(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error, dict)
    assert error["code"] == code
    return body


def _assert_empty_detail(body: dict[str, Any]) -> None:
    assert body["error"]["detail"] == {}


def _new_session(client: TestClient, character_name: str = "Aria") -> dict[str, Any]:
    """A character through 009's route, then a session with no setup through 011's route."""
    created_character = client.post(CHARACTERS_PATH, json={"name": character_name, "sheet": ""})
    assert created_character.status_code == 201, created_character.text
    character = created_character.json()
    started = client.post(f"{CHARACTERS_PATH}/{character['id']}/sessions", json={})
    assert started.status_code == 201, started.text
    session = started.json()
    assert isinstance(session, dict)
    return session


def _append(client: TestClient, session_id: Any, text: str) -> dict[str, Any]:
    response = client.post(_zone_messages_path(session_id), json={"text": text})
    assert response.status_code == 201, response.text
    message = response.json()
    assert isinstance(message, dict)
    return message


def _file_partner(client: TestClient, session_id: Any, text: str) -> dict[str, Any]:
    response = client.post(_entries_path(session_id), json={"kind": "partner", "text": text})
    assert response.status_code == 201, response.text
    message = response.json()
    assert isinstance(message, dict)
    return message


def _settle(client: TestClient, session_id: Any) -> dict[str, Any]:
    response = client.post(_settle_path(session_id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def _reopen(client: TestClient, session_id: Any) -> dict[str, Any]:
    response = client.post(_reopen_path(session_id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def _entries(client: TestClient, session_id: Any) -> list[dict[str, Any]]:
    response = client.get(_entries_path(session_id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"entries"}
    rows = body["entries"]
    assert isinstance(rows, list)
    return rows


def _zone(client: TestClient, session_id: Any) -> list[dict[str, Any]]:
    response = client.get(_zone_path(session_id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"messages"}
    rows = body["messages"]
    assert isinstance(rows, list)
    return rows


def _read_session(client: TestClient, session_id: Any) -> dict[str, Any]:
    response = client.get(_session_path(session_id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def _ids(rows: list[dict[str, Any]]) -> list[str]:
    return [row["id"] for row in rows]


def _is_decimal_string(value: Any) -> bool:
    return isinstance(value, str) and value.isdigit()


def _assert_message_shape(message: dict[str, Any]) -> None:
    """The ``Message`` wire object: exactly eleven keys (022 001 DoD-4), ids as decimal strings."""
    assert set(message) == MESSAGE_KEYS
    assert _is_decimal_string(message["id"])
    assert _is_decimal_string(message["session_id"])
    assert message["role"] in {"user", "assistant", "tool"}
    assert message["kind"] in {"partner", "turn", "decision", None}
    assert isinstance(message["text"], str)
    assert message["settled_at"] is None or isinstance(message["settled_at"], str)
    assert isinstance(message["created_at"], str)
    assert isinstance(message["updated_at"], str)


def _text_body(text: Any) -> dict[str, Any]:
    return {} if text is _MISSING else {"text": text}


def _pause() -> None:
    """Keep consecutive microsecond instants apart so 'later' comparisons are meaningful."""
    time.sleep(0.002)


# --- DoD-1: router-level auth ---------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", _entries_path(UNKNOWN_SESSION_ID), None),
        ("POST", _entries_path(UNKNOWN_SESSION_ID), {"kind": "partner", "text": "hello"}),
        ("GET", _zone_path(UNKNOWN_SESSION_ID), None),
        ("POST", _zone_messages_path(UNKNOWN_SESSION_ID), {"text": "hello"}),
        ("POST", _settle_path(UNKNOWN_SESSION_ID), None),
        ("POST", _reopen_path(UNKNOWN_SESSION_ID), None),
        ("PATCH", _message_path(UNKNOWN_MESSAGE_ID), {"text": "hello"}),
    ],
    ids=["list-entries", "file-partner", "list-zone", "append", "settle", "reopen", "edit"],
)
def test_every_stream_route_answers_401_without_a_login__S012_004_DoD1(
    application: FastAPI, method: str, path: str, body: dict[str, Any] | None
) -> None:
    """DoD-1 — D12: `require_user` sits on the router; all seven routes refuse anonymously."""
    client = _anonymous(application)

    response = client.request(method, path, json=body)

    _assert_envelope(response, 401, NOT_AUTHENTICATED)


# --- DoD-2: append, then read zone and entries ----------------------------------------


def test_append_answers_201_with_the_message__S012_004_DoD2__S022_001_DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2 — UC-083 step 2: 201, eleven keys (022 001 DoD-4), decimal ids, role user,
    kind/settled_at null, text verbatim."""
    client = _player_a(application, db_settings)
    session = _new_session(client)

    response = client.post(_zone_messages_path(session["id"]), json={"text": "Hello there."})

    assert response.status_code == 201, response.text
    message = response.json()
    _assert_message_shape(message)
    assert _is_decimal_string(message["id"])
    assert message["session_id"] == session["id"]
    assert message["role"] == "user"
    assert message["kind"] is None
    assert message["settled_at"] is None
    assert message["text"] == "Hello there."


def test_appended_message_is_the_zone_and_entries_stay_empty__S012_004_DoD2(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-2: `GET …/zone` returns exactly `{messages: [that message]}`; `GET …/entries` is `{entries: []}`."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    message = _append(client, session["id"], "Hello there.")

    zone_response = client.get(_zone_path(session["id"]))
    entries_response = client.get(_entries_path(session["id"]))

    assert zone_response.status_code == 200, zone_response.text
    assert zone_response.json() == {"messages": [message]}
    assert entries_response.status_code == 200, entries_response.text
    assert entries_response.json() == {"entries": []}


def test_a_role_in_the_append_body_is_ignored__S012_004_DoD2(application: FastAPI, db_settings: Settings) -> None:
    """DoD-2 — D12: a body carrying `"role": "assistant"` still stores role `user`."""
    client = _player_a(application, db_settings)
    session = _new_session(client)

    response = client.post(_zone_messages_path(session["id"]), json={"text": "Hello there.", "role": "assistant"})

    assert response.status_code == 201, response.text
    assert response.json()["role"] == "user"
    zone = _zone(client, session["id"])
    assert len(zone) == 1
    assert zone[0]["role"] == "user"


# --- DoD-3: settle a lone own message -------------------------------------------------


def test_settle_a_lone_message_answers_the_turn__S012_004_DoD3(application: FastAPI, db_settings: Settings) -> None:
    """DoD-3 — US-031.AC-1, US-034.AC-1, US-135.AC-1: entry_id = message id, kind turn, no buried ids."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    message = _append(client, session["id"], "Hello there.")

    response = client.post(_settle_path(session["id"]))

    assert response.status_code == 200, response.text
    assert response.json() == {"entry_id": message["id"], "kind": "turn", "buried_ids": []}


def test_after_settle_the_zone_is_empty_and_the_entry_is_recorded__S012_004_DoD3__S022_001_DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-3 — US-127.AC-1, US-127.AC-2: zone empty; entries hold the message as a settled turn, text unchanged."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    message = _append(client, session["id"], "Hello there.")

    _settle(client, session["id"])

    assert _zone(client, session["id"]) == []
    entries = _entries(client, session["id"])
    assert len(entries) == 1
    entry = entries[0]
    _assert_message_shape(entry)
    assert entry["id"] == message["id"]
    assert entry["kind"] == "turn"
    assert isinstance(entry["settled_at"], str)
    assert entry["text"] == "Hello there."
    assert entry["role"] == "user"


# --- DoD-4: the (( )) rules through the routes ----------------------------------------


def test_a_turn_settles_with_its_fragment_stripped__S012_004_DoD4(application: FastAPI, db_settings: Settings) -> None:
    """DoD-4 — US-130.AC-1: `She walks. ((be dramatic)) Then sits.` settles as `She walks. Then sits.`."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    message = _append(client, session["id"], "She walks. ((be dramatic)) Then sits.")

    settled = _settle(client, session["id"])

    assert settled["kind"] == "turn"
    entries = _entries(client, session["id"])
    assert [entry["id"] for entry in entries] == [message["id"]]
    assert entries[0]["text"] == "She walks. Then sits."
    assert entries[0]["kind"] == "turn"


def test_a_wholly_parenthesised_message_settles_as_a_decision__S012_004_DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-4 — US-129.AC-1, US-122 precondition: `((Let's skip ahead))` settles as a verbatim decision."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    first = _append(client, session["id"], "She walks. ((be dramatic)) Then sits.")
    _settle(client, session["id"])
    decision = _append(client, session["id"], "((Let's skip ahead))")

    settled = _settle(client, session["id"])

    assert settled == {"entry_id": decision["id"], "kind": "decision", "buried_ids": []}
    entries = _entries(client, session["id"])
    assert _ids(entries) == [first["id"], decision["id"]]
    assert entries[1]["kind"] == "decision"
    assert entries[1]["text"] == "((Let's skip ahead))"
    assert entries[0]["kind"] == "turn"


# --- DoD-5: the last zone row is the head, whoever wrote it ---------------------------


def test_settle_takes_a_trailing_assistant_row_as_head__S012_004_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-5 — US-126.AC-1, R11: an assistant row after two appends is the head; the two are buried."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    first = _append(client, session["id"], "First line.")
    second = _append(client, session["id"], "Second line.")
    assistant_id = max(int(first["id"]), int(second["id"])) + 1
    with engine.begin() as connection:
        connection.execute(
            schema.messages.insert().values(
                id=assistant_id,
                user_id=PLAYER_A_ID,
                session_id=int(session["id"]),
                role="assistant",
                kind=None,
                text="A suggestion from the assistant.",
                related_to=None,
                settled_at=None,
                tool_name=None,
                tool_payload=None,
                created_at=RAW_ROW_TIMESTAMP,
                updated_at=RAW_ROW_TIMESTAMP,
            )
        )

    settled = _settle(client, session["id"])

    assert settled["entry_id"] == str(assistant_id)
    assert settled["buried_ids"] == [first["id"], second["id"]]
    assert [int(i) for i in settled["buried_ids"]] == sorted(int(i) for i in settled["buried_ids"])
    entries = _entries(client, session["id"])
    assert _ids(entries) == [str(assistant_id)]
    assert entries[0]["role"] == "assistant"
    zone = _zone(client, session["id"])
    for appended in (first, second):
        assert appended["id"] not in _ids(entries)
        assert appended["id"] not in _ids(zone)
    assert zone == []


# --- DoD-6: born-settled partner blocks -----------------------------------------------


def test_a_partner_block_is_filed_born_settled_and_verbatim__S012_004_DoD6__S022_001_DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-6 — US-121.AC-1, US-121.AC-2: 201, kind partner, role user, settled, text byte-for-byte."""
    client = _player_a(application, db_settings)
    session = _new_session(client)

    response = client.post(_entries_path(session["id"]), json={"kind": "partner", "text": "Partner says ((hi)) there"})

    assert response.status_code == 201, response.text
    filed = response.json()
    _assert_message_shape(filed)
    assert filed["session_id"] == session["id"]
    assert filed["kind"] == "partner"
    assert filed["role"] == "user"
    assert isinstance(filed["settled_at"], str)
    assert filed["text"] == "Partner says ((hi)) there"
    entries = _entries(client, session["id"])
    assert _ids(entries) == [filed["id"]]
    assert entries[0]["text"] == "Partner says ((hi)) there"
    assert entries[0]["kind"] == "partner"
    assert filed["id"] not in _ids(_zone(client, session["id"]))
    assert _zone(client, session["id"]) == []


def test_several_partner_blocks_in_a_row_are_listed_in_posting_order__S012_004_DoD6(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-6 — UC-031: three partner posts in a row all appear in `GET …/entries` in posting order."""
    client = _player_a(application, db_settings)
    session = _new_session(client)

    filed = [
        _file_partner(client, session["id"], "Partner says ((hi)) there"),
        _file_partner(client, session["id"], "Second block."),
        _file_partner(client, session["id"], "Third block."),
    ]

    entries = _entries(client, session["id"])
    assert _ids(entries) == [f["id"] for f in filed]
    assert [e["text"] for e in entries] == ["Partner says ((hi)) there", "Second block.", "Third block."]
    assert all(e["kind"] == "partner" for e in entries)


# --- DoD-7: entries kind must be exactly "partner" -------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "turn", "text": "Some text"},
        {"kind": "decision", "text": "Some text"},
        {"text": "Some text"},
        {"kind": None, "text": "Some text"},
    ],
    ids=["turn", "decision", "missing", "null"],
)
def test_a_non_partner_kind_is_refused_with_422__S012_004_DoD7(
    application: FastAPI, db_settings: Settings, body: dict[str, Any]
) -> None:
    """DoD-7 — R11's single exception at the boundary: any kind but `partner` → 422, entries unchanged."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    _file_partner(client, session["id"], "Already filed.")
    before = _entries(client, session["id"])

    response = client.post(_entries_path(session["id"]), json=body)

    assert response.status_code == 422, response.text
    assert _entries(client, session["id"]) == before


# --- DoD-8: text validation (D9, R10) -------------------------------------------------

BLANK_TEXTS = pytest.mark.parametrize(
    "text", ["", "   ", _MISSING, None], ids=["empty", "whitespace", "missing", "null"]
)


@BLANK_TEXTS
def test_append_refuses_blank_text_and_stores_nothing__S012_004_DoD8(
    application: FastAPI, db_settings: Settings, text: Any
) -> None:
    """DoD-8 — D9: append with blank / missing / null text → 422; the zone is unchanged."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    _append(client, session["id"], "Existing draft.")
    zone_before = _zone(client, session["id"])
    entries_before = _entries(client, session["id"])

    response = client.post(_zone_messages_path(session["id"]), json=_text_body(text))

    assert response.status_code == 422, response.text
    assert _zone(client, session["id"]) == zone_before
    assert _entries(client, session["id"]) == entries_before


@BLANK_TEXTS
def test_partner_post_refuses_blank_text_and_stores_nothing__S012_004_DoD8(
    application: FastAPI, db_settings: Settings, text: Any
) -> None:
    """DoD-8 — D9: partner post with blank / missing / null text → 422; entries unchanged."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    _file_partner(client, session["id"], "Existing partner block.")
    entries_before = _entries(client, session["id"])
    zone_before = _zone(client, session["id"])
    body = {"kind": "partner", **_text_body(text)}

    response = client.post(_entries_path(session["id"]), json=body)

    assert response.status_code == 422, response.text
    assert _entries(client, session["id"]) == entries_before
    assert _zone(client, session["id"]) == zone_before


@BLANK_TEXTS
def test_patch_refuses_blank_text_and_changes_nothing__S012_004_DoD8(
    application: FastAPI, db_settings: Settings, text: Any
) -> None:
    """DoD-8 — D9: PATCH with blank / missing / null text → 422; the zone message is unchanged."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    message = _append(client, session["id"], "Original text.")
    zone_before = _zone(client, session["id"])

    response = client.patch(_message_path(message["id"]), json=_text_body(text))

    assert response.status_code == 422, response.text
    assert _zone(client, session["id"]) == zone_before


def test_append_accepts_a_500000_character_text__S012_004_DoD8(application: FastAPI, db_settings: Settings) -> None:
    """DoD-8 — R10, US-035.AC-2: no maximum length; an enormous text is accepted (201)."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    enormous = "a" * 500_000

    response = client.post(_zone_messages_path(session["id"]), json={"text": enormous})

    assert response.status_code == 201, response.text
    assert response.json()["text"] == enormous


def test_partner_post_accepts_a_500000_character_text__S012_004_DoD8(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-8 — R10, US-035.AC-2: the partner route also accepts 500 000 characters (201)."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    enormous = "b" * 500_000

    response = client.post(_entries_path(session["id"]), json={"kind": "partner", "text": enormous})

    assert response.status_code == 201, response.text
    assert response.json()["text"] == enormous


# --- DoD-9: settle on an empty zone ---------------------------------------------------


def test_settle_on_an_empty_zone_answers_409_zone_empty__S012_004_DoD9(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-9 — R11: 409 `zone_empty`, a non-empty message and an empty detail."""
    client = _player_a(application, db_settings)
    session = _new_session(client)

    response = client.post(_settle_path(session["id"]))

    body = _assert_envelope(response, 409, ZONE_EMPTY)
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"].strip() != ""
    _assert_empty_detail(body)


# --- DoD-10: re-open restores the group -----------------------------------------------


def test_reopen_restores_the_group_in_its_original_order__S012_004_DoD10__S022_001_DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-10 — US-041.AC-1, US-128.AC-1, D10: reopened head, restored ids ascending, zone restored."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    appended = [
        _append(client, session["id"], "First line."),
        _append(client, session["id"], "Second line."),
        _append(client, session["id"], "Third line."),
    ]
    settled = _settle(client, session["id"])
    assert settled["entry_id"] == appended[2]["id"]
    assert _zone(client, session["id"]) == []

    response = client.post(_reopen_path(session["id"]))

    assert response.status_code == 200, response.text
    assert response.json() == {
        "reopened_id": appended[2]["id"],
        "restored_ids": [appended[0]["id"], appended[1]["id"]],
    }
    zone = _zone(client, session["id"])
    assert _ids(zone) == [m["id"] for m in appended]
    for row in zone:
        _assert_message_shape(row)
        assert row["kind"] is None
        assert row["settled_at"] is None
    assert [row["text"] for row in zone] == ["First line.", "Second line.", "Third line."]
    assert appended[2]["id"] not in _ids(_entries(client, session["id"]))


def test_a_reopened_head_is_editable_again__S012_004_DoD10(application: FastAPI, db_settings: Settings) -> None:
    """DoD-10 — D2: after re-open the head is a zone row again, so PATCH on it answers 200."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    _append(client, session["id"], "First line.")
    _append(client, session["id"], "Second line.")
    head = _append(client, session["id"], "Third line.")
    _settle(client, session["id"])
    _reopen(client, session["id"])

    response = client.patch(_message_path(head["id"]), json={"text": "Third line, revised."})

    assert response.status_code == 200, response.text
    assert response.json()["text"] == "Third line, revised."


# --- DoD-11: re-open refused while the zone holds a message ---------------------------


def test_reopen_with_a_non_empty_zone_answers_409_zone_not_empty__S012_004_DoD11(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-11 — US-042.AC-1, US-128.AC-2: 409 `zone_not_empty`; head stays recorded, zone only the new message."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    _append(client, session["id"], "First line.")
    head = _append(client, session["id"], "Second line.")
    _settle(client, session["id"])
    newcomer = _append(client, session["id"], "A new draft.")

    response = client.post(_reopen_path(session["id"]))

    body = _assert_envelope(response, 409, ZONE_NOT_EMPTY)
    _assert_empty_detail(body)
    assert head["id"] in _ids(_entries(client, session["id"]))
    assert _zone(client, session["id"]) == [newcomer]


# --- DoD-12: nothing to re-open -------------------------------------------------------


def test_reopen_on_a_new_session_answers_nothing_to_reopen__S012_004_DoD12(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-12 — D10: no settled row at all → 409 `nothing_to_reopen`, empty detail."""
    client = _player_a(application, db_settings)
    session = _new_session(client)

    body = _assert_envelope(client.post(_reopen_path(session["id"])), 409, NOTHING_TO_REOPEN)

    _assert_empty_detail(body)


def test_reopen_after_a_lone_settled_turn_answers_nothing_to_reopen__S012_004_DoD12(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-12 — D10: a lone directly-settled turn has no buried group → 409, entry stays."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    lone = _append(client, session["id"], "Only line.")
    _settle(client, session["id"])
    entries_before = _entries(client, session["id"])

    body = _assert_envelope(client.post(_reopen_path(session["id"])), 409, NOTHING_TO_REOPEN)

    _assert_empty_detail(body)
    assert _entries(client, session["id"]) == entries_before
    assert lone["id"] in _ids(entries_before)
    assert _zone(client, session["id"]) == []


def test_reopen_when_the_last_entry_is_a_lone_partner_block_answers_nothing_to_reopen__S012_004_DoD12(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-12 — D10: a filed partner block as the last entry is not re-openable."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    _file_partner(client, session["id"], "Partner block.")

    body = _assert_envelope(client.post(_reopen_path(session["id"])), 409, NOTHING_TO_REOPEN)

    _assert_empty_detail(body)


def test_reopen_when_a_partner_block_follows_a_group_answers_nothing_to_reopen__S012_004_DoD12(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-12 — D10: a partner block filed after a settled group is the last entry → 409; nothing moves."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    _append(client, session["id"], "First line.")
    _append(client, session["id"], "Second line.")
    _settle(client, session["id"])
    _file_partner(client, session["id"], "Partner block.")
    entries_before = _entries(client, session["id"])

    body = _assert_envelope(client.post(_reopen_path(session["id"])), 409, NOTHING_TO_REOPEN)

    _assert_empty_detail(body)
    assert _entries(client, session["id"]) == entries_before
    assert _zone(client, session["id"]) == []


# --- DoD-13: editing ------------------------------------------------------------------


def test_patch_on_a_zone_message_answers_the_edited_message__S012_004_DoD13__S022_001_DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-13 — US-115.AC-1, R12: 200, the exact text (parens untouched), kind null; the zone shows it."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    message = _append(client, session["id"], "Original text.")

    response = client.patch(_message_path(message["id"]), json={"text": "Edited ((keep))"})

    assert response.status_code == 200, response.text
    edited = response.json()
    _assert_message_shape(edited)
    assert edited["id"] == message["id"]
    assert edited["text"] == "Edited ((keep))"
    assert edited["kind"] is None
    zone = _zone(client, session["id"])
    assert _ids(zone) == [message["id"]]
    assert zone[0]["text"] == "Edited ((keep))"


def test_patch_on_a_filed_partner_block_answers_the_edited_entry__S012_004_DoD13__S014_001_DoD10__S022_001_DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-13 (amended by 014 001 DoD-10) — 014 D1: a filed partner block is editable; 200 with
    kind `partner`, the new text and the same `settled_at`; entries show it (US-109.AC-1)."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    filed = _file_partner(client, session["id"], "Partner block.")

    response = client.patch(_message_path(filed["id"]), json={"text": "Changed."})

    assert response.status_code == 200, response.text
    edited = response.json()
    _assert_message_shape(edited)
    assert edited["id"] == filed["id"]
    assert edited["kind"] == "partner"
    assert edited["text"] == "Changed."
    assert edited["settled_at"] == filed["settled_at"]
    entries = _entries(client, session["id"])
    assert _ids(entries) == [filed["id"]]
    assert entries[0]["text"] == "Changed."
    assert entries[0]["kind"] == "partner"


def test_patch_on_a_settled_decision_keeps_the_kind__S012_004_DoD13__S014_001_DoD10__S022_001_DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-13 (amended by 014 001 DoD-10) — a settled decision (`((skip ahead))`, settled)
    edited to `Skip to morning.` answers 200 with kind `decision` (US-110.AC-1, R12)."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    _append(client, session["id"], "((skip ahead))")
    settled = _settle(client, session["id"])
    assert settled["kind"] == "decision"
    decision_id = settled["entry_id"]
    (before,) = _entries(client, session["id"])

    response = client.patch(_message_path(decision_id), json={"text": "Skip to morning."})

    assert response.status_code == 200, response.text
    edited = response.json()
    _assert_message_shape(edited)
    assert edited["id"] == decision_id
    assert edited["kind"] == "decision"
    assert edited["text"] == "Skip to morning."
    assert edited["settled_at"] == before["settled_at"]
    entries = _entries(client, session["id"])
    assert _ids(entries) == [decision_id]
    assert entries[0]["kind"] == "decision"
    assert entries[0]["text"] == "Skip to morning."


def test_patch_on_a_buried_message_answers_message_not_editable__S012_004_DoD13__S014_001_DoD10(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-13 (kept by 014 001 DoD-10) — US-116.AC-1: a buried message → 409; re-opening shows
    its text unchanged."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    buried = _append(client, session["id"], "Buried line.")
    _append(client, session["id"], "Head line.")
    settled = _settle(client, session["id"])
    assert settled["buried_ids"] == [buried["id"]]

    response = client.patch(_message_path(buried["id"]), json={"text": "Changed."})

    _assert_envelope(response, 409, MESSAGE_NOT_EDITABLE)
    _reopen(client, session["id"])
    zone = _zone(client, session["id"])
    restored = [row for row in zone if row["id"] == buried["id"]]
    assert len(restored) == 1
    assert restored[0]["text"] == "Buried line."


# --- DoD-14: owner scope (R5) ---------------------------------------------------------


def _session_route_requests(client: TestClient, session_id: Any) -> list[httpx.Response]:
    """Every `/api/sessions/<id>/…` route of this router, in a fixed order."""
    return [
        client.get(_entries_path(session_id)),
        client.post(_entries_path(session_id), json={"kind": "partner", "text": "Intruding block."}),
        client.get(_zone_path(session_id)),
        client.post(_zone_messages_path(session_id), json={"text": "Intruding draft."}),
        client.post(_settle_path(session_id)),
        client.post(_reopen_path(session_id)),
    ]


def test_another_users_session_answers_404_like_an_unknown_one__S012_004_DoD14(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-14 — R5: as B, each session route on A's session → 404 `session_not_found`, same body as nobody's."""
    owner = _player_a(application, db_settings)
    session = _new_session(owner)
    _append(owner, session["id"], "First line.")
    _append(owner, session["id"], "Second line.")
    _settle(owner, session["id"])
    _append(owner, session["id"], "A's draft.")
    entries_before = _entries(owner, session["id"])
    zone_before = _zone(owner, session["id"])
    intruder = _player_b(application, db_settings)

    foreign = _session_route_requests(intruder, session["id"])
    unknown = _session_route_requests(intruder, UNKNOWN_SESSION_ID)

    for foreign_response, unknown_response in zip(foreign, unknown, strict=True):
        body = _assert_envelope(foreign_response, 404, SESSION_NOT_FOUND)
        _assert_empty_detail(body)
        assert unknown_response.status_code == 404, unknown_response.text
        assert body == unknown_response.json()
    assert _entries(owner, session["id"]) == entries_before
    assert _zone(owner, session["id"]) == zone_before


def test_another_users_message_answers_404_like_an_unknown_one__S012_004_DoD14(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-14 — R5: as B, PATCH on A's message → 404 `message_not_found`, same body as nobody's."""
    owner = _player_a(application, db_settings)
    session = _new_session(owner)
    message = _append(owner, session["id"], "A's draft.")
    zone_before = _zone(owner, session["id"])
    entries_before = _entries(owner, session["id"])
    intruder = _player_b(application, db_settings)

    foreign = intruder.patch(_message_path(message["id"]), json={"text": "Hijacked."})
    unknown = intruder.patch(_message_path(UNKNOWN_MESSAGE_ID), json={"text": "Hijacked."})

    body = _assert_envelope(foreign, 404, MESSAGE_NOT_FOUND)
    _assert_empty_detail(body)
    assert unknown.status_code == 404, unknown.text
    assert body == unknown.json()
    assert _zone(owner, session["id"]) == zone_before
    assert _entries(owner, session["id"]) == entries_before


# --- DoD-15: last use (D3) ------------------------------------------------------------


def test_reads_never_move_last_use__S012_004_DoD15(application: FastAPI, db_settings: Settings) -> None:
    """DoD-15 — D3, 011 D3: `GET …/entries` and `GET …/zone` leave `last_used_at` unchanged."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    _append(client, session["id"], "A draft.")
    before = _read_session(client, session["id"])["last_used_at"]
    _pause()

    _entries(client, session["id"])
    _zone(client, session["id"])

    assert _read_session(client, session["id"])["last_used_at"] == before


def test_every_content_write_keeps_last_use_moving_forward__S012_004_DoD15(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-15 — D3: append, partner post, PATCH, settle and reopen each leave `last_used_at` not earlier."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    sid = session["id"]
    previous = _read_session(client, sid)["last_used_at"]

    def _check_not_earlier() -> None:
        nonlocal previous
        current = _read_session(client, sid)["last_used_at"]
        assert TIMESTAMP_PATTERN.match(current) is not None
        assert current >= previous
        previous = current

    _pause()
    _file_partner(client, sid, "Partner block.")
    _check_not_earlier()
    _pause()
    first = _append(client, sid, "First line.")
    _check_not_earlier()
    _pause()
    _append(client, sid, "Second line.")
    _check_not_earlier()
    _pause()
    patched = client.patch(_message_path(first["id"]), json={"text": "First line, revised."})
    assert patched.status_code == 200, patched.text
    _check_not_earlier()
    _pause()
    _settle(client, sid)
    _check_not_earlier()
    _pause()
    _reopen(client, sid)
    _check_not_earlier()


def test_a_refused_settle_leaves_last_use_unchanged__S012_004_DoD15(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-15 — D3: a refusal writes nothing, the bump included."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    _file_partner(client, session["id"], "Partner block.")
    before = _read_session(client, session["id"])["last_used_at"]
    _pause()

    _assert_envelope(client.post(_settle_path(session["id"])), 409, ZONE_EMPTY)

    assert _read_session(client, session["id"])["last_used_at"] == before


def test_writing_to_the_older_session_moves_it_to_the_top__S012_004_DoD15(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-15 — US-028.AC-1, 011 D3: an append to the older of two sessions puts it first in `GET /api/sessions`."""
    client = _player_a(application, db_settings)
    older = _new_session(client, "Aria")
    _pause()
    newer = _new_session(client, "Bram")
    listing_before = client.get(SESSIONS_PATH)
    assert listing_before.status_code == 200, listing_before.text
    assert [s["id"] for s in listing_before.json()["sessions"]][:2] == [newer["id"], older["id"]]
    _pause()

    _append(client, older["id"], "Back to the older story.")

    listing = client.get(SESSIONS_PATH)
    assert listing.status_code == 200, listing.text
    assert [s["id"] for s in listing.json()["sessions"]][:2] == [older["id"], newer["id"]]


# --- DoD-16: archive is not a lock (R6) -----------------------------------------------


def test_every_write_succeeds_on_an_archived_session__S012_004_DoD16(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-16 — R6, US-024.AC-2: on an archived no-setup session, partner, append, PATCH, settle, reopen all succeed."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    assert session["setup_id"] is None
    sid = session["id"]
    archived = client.post(f"{SESSIONS_PATH}/{sid}/archive")
    assert archived.status_code == 200, archived.text

    partner = client.post(_entries_path(sid), json={"kind": "partner", "text": "Partner block."})
    assert partner.status_code == 201, partner.text
    first = client.post(_zone_messages_path(sid), json={"text": "First line."})
    assert first.status_code == 201, first.text
    second = client.post(_zone_messages_path(sid), json={"text": "Second line."})
    assert second.status_code == 201, second.text
    patched = client.patch(_message_path(first.json()["id"]), json={"text": "First line, revised."})
    assert patched.status_code == 200, patched.text
    settled = client.post(_settle_path(sid))
    assert settled.status_code == 200, settled.text
    reopened = client.post(_reopen_path(sid))
    assert reopened.status_code == 200, reopened.text


def test_archive_then_restore_leaves_entries_and_zone_exactly_as_before__S012_004_DoD16(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-16 — US-027.AC-3 entries half: archive → restore returns entries and zone exactly as before."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    assert session["setup_id"] is None
    sid = session["id"]
    _file_partner(client, sid, "Partner block.")
    _append(client, sid, "First line.")
    _append(client, sid, "Second line.")
    _settle(client, sid)
    _append(client, sid, "A draft in the zone.")
    entries_before = _entries(client, sid)
    zone_before = _zone(client, sid)

    archived = client.post(f"{SESSIONS_PATH}/{sid}/archive")
    assert archived.status_code == 200, archived.text
    restored = client.post(f"{SESSIONS_PATH}/{sid}/restore")
    assert restored.status_code == 200, restored.text

    assert _entries(client, sid) == entries_before
    assert _zone(client, sid) == zone_before


def test_writes_made_while_archived_survive_restore__S012_004_DoD16(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-16 — R6: what was written while archived reads back unchanged after restore."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    sid = session["id"]
    assert client.post(f"{SESSIONS_PATH}/{sid}/archive").status_code == 200
    _file_partner(client, sid, "Partner block.")
    _append(client, sid, "First line.")
    _append(client, sid, "Second line.")
    _settle(client, sid)
    _append(client, sid, "A draft.")
    entries_before = _entries(client, sid)
    zone_before = _zone(client, sid)

    assert client.post(f"{SESSIONS_PATH}/{sid}/restore").status_code == 200

    assert _entries(client, sid) == entries_before
    assert _zone(client, sid) == zone_before


# --- DoD-17: no discard, stop or delete surface ---------------------------------------


def _flatten_routes(routes: Any, found: list[tuple[str, set[str]]]) -> None:
    """Walk a route list, tolerating entries without ``.path`` (e.g. included-router wrappers)."""
    for route in routes or []:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if isinstance(path, str):
            found.append((path, {m.upper() for m in (methods or set())}))
        nested = getattr(route, "routes", None)
        if nested is not None and nested is not routes:
            _flatten_routes(nested, found)
        inner_router = getattr(route, "router", None)
        inner_routes = getattr(inner_router, "routes", None)
        if inner_routes is not None:
            _flatten_routes(inner_routes, found)


def _application_routes(app: FastAPI) -> list[tuple[str, set[str]]]:
    """Every (path, methods) pair the application exposes, from OpenAPI plus a tolerant route walk."""
    found: list[tuple[str, set[str]]] = []
    for path, operations in app.openapi()["paths"].items():
        found.append((path, {method.upper() for method in operations}))
    _flatten_routes(app.routes, found)
    return found


def test_no_discard_stop_or_delete_route_exists__S012_004_DoD17(application: FastAPI) -> None:
    """DoD-17 — R11, UC-086, US-134: no session/message path names discard or stop, none accepts DELETE."""
    routes = _application_routes(application)
    paths = {path for path, _ in routes}
    assert STREAM_PATH_TEMPLATES <= paths

    scoped = [
        (path, methods)
        for path, methods in routes
        if path.startswith("/api/sessions/") or path.startswith("/api/messages/")
    ]
    assert scoped
    for path, methods in scoped:
        assert "discard" not in path.lower(), path
        assert "stop" not in path.lower(), path
        assert "DELETE" not in methods, path


def test_delete_on_a_message_answers_405_and_the_message_survives__S012_004_DoD17(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-17: `DELETE /api/messages/<id>` → 405; the message is still readable."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    message = _append(client, session["id"], "Keep me.")

    response = client.delete(_message_path(message["id"]))

    assert response.status_code == 405, response.text
    assert _zone(client, session["id"]) == [message]


# --- DoD-18: non-numeric path ids -----------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", f"{SESSIONS_PATH}/abc/zone", None),
        ("GET", f"{SESSIONS_PATH}/abc/entries", None),
        ("POST", f"{SESSIONS_PATH}/abc/settle", None),
        ("PATCH", f"{MESSAGES_PATH}/abc", {"text": "Some text"}),
    ],
    ids=["zone", "entries", "settle", "edit"],
)
def test_a_non_numeric_path_id_answers_422__S012_004_DoD18(
    application: FastAPI, db_settings: Settings, method: str, path: str, body: dict[str, Any] | None
) -> None:
    """DoD-18 — Wire contract: a non-numeric path id is a native 422."""
    client = _player_a(application, db_settings)

    response = client.request(method, path, json=body)

    assert response.status_code == 422, response.text


# --- DoD-19: source check -------------------------------------------------------------


def _router_imports() -> tuple[list[ast.Import], list[ast.ImportFrom]]:
    tree = ast.parse(STREAM_ROUTER_SOURCE.read_text(encoding="utf-8"))
    plain = [node for node in ast.walk(tree) if isinstance(node, ast.Import)]
    from_imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    return plain, from_imports


def test_the_router_imports_only_connection_from_sqlalchemy__S012_004_DoD19() -> None:
    """DoD-19 — routers own HTTP, services own SQL: only the `Connection` type comes from sqlalchemy."""
    plain, from_imports = _router_imports()

    for node in plain:
        for alias in node.names:
            assert alias.name != "sqlalchemy" and not alias.name.startswith("sqlalchemy."), alias.name
    for node in from_imports:
        module = node.module or ""
        if module == "sqlalchemy" or module.startswith("sqlalchemy."):
            assert module == "sqlalchemy", module
            assert [alias.name for alias in node.names] == ["Connection"]


def test_the_router_does_not_import_the_schema_module__S012_004_DoD19() -> None:
    """DoD-19 — the router contains no SQL, so nothing from `app.db.schema`."""
    plain, from_imports = _router_imports()

    for node in plain:
        for alias in node.names:
            assert not alias.name.startswith("app.db.schema"), alias.name
    for node in from_imports:
        module = node.module or ""
        assert not module.startswith("app.db.schema"), module
        if module == "app.db":
            assert "schema" not in {alias.name for alias in node.names}


def test_the_router_does_not_import_the_parens_module__S012_004_DoD19() -> None:
    """DoD-19 — R12 parse-once: `app.services.parens` is settle's alone."""
    plain, from_imports = _router_imports()

    for node in plain:
        for alias in node.names:
            assert not alias.name.startswith("app.services.parens"), alias.name
    for node in from_imports:
        module = node.module or ""
        assert not module.startswith("app.services.parens"), module
        if module == "app.services":
            assert "parens" not in {alias.name for alias in node.names}


# --- DoD-20: 011's routes still answer ------------------------------------------------


def test_011_routes_still_answer_with_this_router_registered__S012_004_DoD20(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-20 — registration order: read, archive and restore of a session answer 200."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    sid = session["id"]

    assert client.get(_session_path(sid)).status_code == 200
    assert client.post(f"{SESSIONS_PATH}/{sid}/archive").status_code == 200
    assert client.post(f"{SESSIONS_PATH}/{sid}/restore").status_code == 200


# =====================================================================================
# Feature 014, step 001 — PATCH on settled entries (D1, D2)
#
# Expected values come from ``docs/plans/014.entry-editing-and-copy-out/
# 001.settled-edit-backend.md`` (DoD-9 .. DoD-12) and ``001.context.md``. The route and
# its wire shapes are 012's, unchanged.
# =====================================================================================


def _settled_turn_between_partners(client: TestClient) -> tuple[str, dict[str, Any]]:
    """A session whose entries are [partner, settled turn, partner] and whose zone holds a draft.

    Returns the session id and the settled turn as read from ``GET …/entries``.
    """
    session = _new_session(client)
    sid = session["id"]
    _file_partner(client, sid, "Opening block.")
    turn = _append(client, sid, "A turn with a typpo.")
    settled = _settle(client, sid)
    assert settled["entry_id"] == turn["id"]
    assert settled["kind"] == "turn"
    _file_partner(client, sid, "Closing block.")
    _append(client, sid, "A draft in the zone.")
    entries = _entries(client, sid)
    assert len(entries) == 3
    assert entries[1]["id"] == turn["id"]
    return sid, entries[1]


# --- 014 DoD-9: a settled turn is edited in place -----------------------------------


def test_patch_on_a_settled_turn_answers_200_with_the_edited_entry__S014_001_DoD9__S022_001_DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """014 DoD-9 — US-110.AC-1, US-032.AC-1: 200, the exact text, kind `turn`, the same
    `settled_at` as read from `GET …/entries`."""
    client = _player_a(application, db_settings)
    sid, turn = _settled_turn_between_partners(client)

    response = client.patch(_message_path(turn["id"]), json={"text": "Edited turn."})

    assert response.status_code == 200, response.text
    edited = response.json()
    _assert_message_shape(edited)
    assert edited["id"] == turn["id"]
    assert edited["session_id"] == sid
    assert edited["text"] == "Edited turn."
    assert edited["kind"] == "turn"
    assert edited["settled_at"] == turn["settled_at"]
    assert edited["created_at"] == turn["created_at"]


def test_a_settled_edit_keeps_the_entry_position_and_leaves_the_zone__S014_001_DoD9(
    application: FastAPI, db_settings: Settings
) -> None:
    """014 DoD-9 — `GET …/entries` shows the new text at the same position (neighbours
    unchanged); `GET …/zone` is unchanged."""
    client = _player_a(application, db_settings)
    sid, turn = _settled_turn_between_partners(client)
    entries_before = _entries(client, sid)
    zone_before = _zone(client, sid)

    response = client.patch(_message_path(turn["id"]), json={"text": "Edited turn."})
    assert response.status_code == 200, response.text

    entries = _entries(client, sid)
    assert _ids(entries) == _ids(entries_before)
    assert entries[1]["text"] == "Edited turn."
    assert entries[1]["kind"] == "turn"
    assert entries[1]["settled_at"] == turn["settled_at"]
    assert entries[0] == entries_before[0]
    assert entries[2] == entries_before[2]
    assert _zone(client, sid) == zone_before


# --- 014 DoD-11: text validation on a settled entry ---------------------------------


@pytest.mark.parametrize("text", ["", "   ", _MISSING], ids=["empty", "whitespace", "missing"])
def test_patch_on_a_settled_entry_refuses_blank_text__S014_001_DoD11(
    application: FastAPI, db_settings: Settings, text: Any
) -> None:
    """014 DoD-11 — 012 D9: blank or missing text → 422; the entry is unchanged."""
    client = _player_a(application, db_settings)
    sid, turn = _settled_turn_between_partners(client)
    entries_before = _entries(client, sid)

    response = client.patch(_message_path(turn["id"]), json=_text_body(text))

    assert response.status_code == 422, response.text
    assert _entries(client, sid) == entries_before


def test_patch_on_a_settled_entry_accepts_a_500000_character_text__S014_001_DoD11(
    application: FastAPI, db_settings: Settings
) -> None:
    """014 DoD-11 — R10: no application layer refuses an enormous settled edit (200)."""
    client = _player_a(application, db_settings)
    _, turn = _settled_turn_between_partners(client)
    enormous = "c" * 500_000

    response = client.patch(_message_path(turn["id"]), json={"text": enormous})

    assert response.status_code == 200, response.text
    assert response.json()["text"] == enormous


# --- 014 DoD-12: last use, refusals and owner scope ---------------------------------


def test_a_settled_patch_keeps_last_use_moving_forward__S014_001_DoD12(
    application: FastAPI, db_settings: Settings
) -> None:
    """014 DoD-12 — D2: after a settled PATCH, `last_used_at` is not earlier than before."""
    client = _player_a(application, db_settings)
    sid, turn = _settled_turn_between_partners(client)
    before = _read_session(client, sid)["last_used_at"]
    _pause()

    response = client.patch(_message_path(turn["id"]), json={"text": "Edited turn."})
    assert response.status_code == 200, response.text

    after = _read_session(client, sid)["last_used_at"]
    assert TIMESTAMP_PATTERN.match(after) is not None
    assert after >= before


def test_a_refused_buried_patch_leaves_last_use_unchanged__S014_001_DoD12(
    application: FastAPI, db_settings: Settings
) -> None:
    """014 DoD-12 — a refused (buried) PATCH writes nothing, the bump included."""
    client = _player_a(application, db_settings)
    session = _new_session(client)
    sid = session["id"]
    buried = _append(client, sid, "Buried line.")
    _append(client, sid, "Head line.")
    settled = _settle(client, sid)
    assert settled["buried_ids"] == [buried["id"]]
    before = _read_session(client, sid)["last_used_at"]
    _pause()

    response = client.patch(_message_path(buried["id"]), json={"text": "Changed."})

    _assert_envelope(response, 409, MESSAGE_NOT_EDITABLE)
    assert _read_session(client, sid)["last_used_at"] == before


def test_another_users_settled_entry_answers_404_message_not_found__S014_001_DoD12(
    application: FastAPI, db_settings: Settings
) -> None:
    """014 DoD-12 — R5: as B, PATCH on A's settled entry → 404 `message_not_found`, the same
    body as for nobody's id; A's entries are unchanged."""
    owner = _player_a(application, db_settings)
    sid, turn = _settled_turn_between_partners(owner)
    entries_before = _entries(owner, sid)
    intruder = _player_b(application, db_settings)

    foreign = intruder.patch(_message_path(turn["id"]), json={"text": "Hijacked."})
    unknown = intruder.patch(_message_path(UNKNOWN_MESSAGE_ID), json={"text": "Hijacked."})

    body = _assert_envelope(foreign, 404, MESSAGE_NOT_FOUND)
    assert unknown.status_code == 404, unknown.text
    assert body == unknown.json()
    assert _entries(owner, sid) == entries_before
