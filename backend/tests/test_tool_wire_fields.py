"""Feature 022, step 001 — tool name, status and arguments on the wire (DoD-1, 2, 4, 5, 6).

Every expected value comes from `docs/plans/022.discussion-ui/001.tool-fields-on-the-wire.md`
(Interface intent + Definition of done), `001.context.md` (the payload table, rows 1–12) and
the feature `context.md` (**D3**: the tool view, eleven wire keys, never `tool_payload` /
`call_id` / `content` / `code`). Bindings come from `status.md` `## Skeleton`, Step 001:

- `tool_view(role, tool_name, tool_payload) -> ToolView` (a NamedTuple
  `(tool_name, tool_status, tool_args)`, equal to the plain tuple)
- `StreamMessage` gains `tool_status` / `tool_args` (default None) after `tool_payload`
- `MessageResponse` gains `tool_name`, `tool_status`, `tool_args` — eleven keys
- `append_tool_message(connection, generator, user_id, session_id, text, tool_name,
  tool_payload) -> StreamMessage` (021 001, unchanged signature)

DoD-3 (the zone route with the four-row fixture) is the amended 021 test in
`tests/test_tool_rows.py` (`…__S021_001_DoD4__S022_001_DoD3`). Each test name here ends
`__S022_001_DoD<n>`. Seeding: registry via `schema.metadata.create_all`, raw-inserted users /
characters / sessions / messages; two users; `conftest.py` untouched.
"""

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.config import Settings, get_settings
from app.db import schema
from app.ids import SnowflakeGenerator
from app.main import create_app
from app.roles import Role
from app.services.messages import (
    StreamMessage,
    append_tool_message,
    list_zone,
    tool_view,
)
from app.services.passwords import hash_password

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
SEEDED_SETTLED_AT = "2025-12-31T00:00:00.000000+00:00"

PLAYER_A_ID = 9_422_001
PLAYER_A_NAME = "aster"
PLAYER_A_PASSWORD = "a quiet river at dusk"

PLAYER_B_ID = 9_422_002
PLAYER_B_NAME = "briar"
PLAYER_B_PASSWORD = "salt and lantern light"

CHAR_A = 1_101
CHAR_B = 2_101

SESSION_A = 5_101
SESSION_B = 6_101

LOGIN_PATH = "/api/auth/login"

#: D3 — the eight 012 keys plus `tool_name`, `tool_status`, `tool_args`.
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

#: `001.context.md` row 3 — the ok payload.
OK_PAYLOAD = (
    '{"call_id":"call_1","arguments":"{\\"query\\":\\"lighthouse\\"}","status":"ok",'
    '"content":"Memo: the lighthouse keeper"}'
)
#: `001.context.md` row 4 — the failed payload.
FAILED_PAYLOAD = '{"call_id":"c9","arguments":"{\\"query\\":\\"x\\"}","status":"failed","code":"tool_failed"}'

OK_SUMMARY = "Found 1 memo."
FAILED_TEXT = "The tool failed."


# =========================================================================================
# DoD-1: the derivation over `001.context.md`'s payload table
# =========================================================================================

#: (row, role, tool_name, tool_payload, expected (tool_name, tool_status, tool_args)).
PAYLOAD_TABLE: list[tuple[int, str, str | None, str | None, tuple[Any, Any, Any]]] = [
    (1, "user", None, None, (None, None, None)),
    (2, "assistant", None, None, (None, None, None)),
    (3, "tool", "memo_search", OK_PAYLOAD, ("memo_search", "ok", {"query": "lighthouse"})),
    (4, "tool", "session_search", FAILED_PAYLOAD, ("session_search", "failed", {"query": "x"})),
    (
        5,
        "tool",
        "web_search",
        '{"call_id":"c2","arguments":"not json","status":"ok","content":"r"}',
        ("web_search", "ok", {}),
    ),
    (
        6,
        "tool",
        "web_search",
        '{"call_id":"c3","arguments":"[1,2]","status":"ok","content":"r"}',
        ("web_search", "ok", {}),
    ),
    (
        7,
        "tool",
        "memo_search",
        '{"call_id":"c4","status":"ok","content":"r"}',
        ("memo_search", "ok", {}),
    ),
    (
        8,
        "tool",
        "memo_search",
        '{"call_id":"c5","arguments":"{}","status":"weird"}',
        ("memo_search", "failed", {}),
    ),
    (9, "tool", "memo_search", "not json at all", ("memo_search", "failed", {})),
    (10, "tool", "memo_search", None, ("memo_search", "failed", {})),
    (
        11,
        "tool",
        None,
        '{"call_id":"c6","arguments":"{\\"a\\":1}","status":"ok","content":"r"}',
        (None, "ok", {"a": 1}),
    ),
    (12, "tool", "memo_search", '"a string"', ("memo_search", "failed", {})),
]


@pytest.mark.parametrize(
    ("row", "role", "tool_name", "tool_payload", "expected"),
    PAYLOAD_TABLE,
    ids=[f"row{entry[0]}" for entry in PAYLOAD_TABLE],
)
def test_tool_view_maps_each_payload_table_row__S022_001_DoD1(
    row: int,
    role: str,
    tool_name: str | None,
    tool_payload: str | None,
    expected: tuple[Any, Any, Any],
) -> None:
    """DoD-1 — D3 / `001.context.md` payload table: each row's inputs give exactly its
    `(tool_name, tool_status, tool_args)`."""
    view = tool_view(role, tool_name, tool_payload)

    assert tuple(view) == expected
    assert view == expected
    assert view.tool_name == expected[0]
    assert view.tool_status == expected[1]
    assert view.tool_args == expected[2]


#: D3's "failed otherwise" / "`{}` otherwise" rules on further unreadable payloads.
UNREADABLE_PAYLOADS: list[tuple[str, str, tuple[Any, Any, Any]]] = [
    ("empty-string", "", ("memo_search", "failed", {})),
    ("truncated-object", '{"status":"ok"', ("memo_search", "failed", {})),
    ("json-null", "null", ("memo_search", "failed", {})),
    ("json-number", "123", ("memo_search", "failed", {})),
    ("json-array", '[{"status":"ok"}]', ("memo_search", "failed", {})),
    ("status-case-differs", '{"status":"OK","arguments":"{}"}', ("memo_search", "failed", {})),
    ("status-not-a-string", '{"status":true,"arguments":"{}"}', ("memo_search", "failed", {})),
    ("no-status", '{"arguments":"{\\"q\\":\\"y\\"}"}', ("memo_search", "failed", {"q": "y"})),
    ("arguments-null", '{"status":"ok","arguments":null}', ("memo_search", "ok", {})),
    ("arguments-an-object-not-a-string", '{"status":"ok","arguments":{"q":"y"}}', ("memo_search", "ok", {})),
    ("arguments-a-json-scalar", '{"status":"ok","arguments":"42"}', ("memo_search", "ok", {})),
    ("arguments-a-json-string", '{"status":"ok","arguments":"\\"q\\""}', ("memo_search", "ok", {})),
]


@pytest.mark.parametrize(
    ("tool_payload", "expected"),
    [(payload, expected) for _, payload, expected in UNREADABLE_PAYLOADS],
    ids=[name for name, _, _ in UNREADABLE_PAYLOADS],
)
def test_tool_view_never_raises_and_follows_d3_on_odd_payloads__S022_001_DoD1(
    tool_payload: str, expected: tuple[Any, Any, Any]
) -> None:
    """DoD-1 — D3: status is `"ok"` only for an object whose `status` is exactly `"ok"`;
    `tool_args` is the parsed `arguments` string only when it parses to an object, else `{}`.
    The derivation never raises."""
    view = tool_view("tool", "memo_search", tool_payload)

    assert tuple(view) == expected


def test_tool_view_keeps_nested_argument_values__S022_001_DoD1() -> None:
    """DoD-1 — D3: `tool_args` is the parsed object itself, nested JSON values included."""
    payload = '{"status":"ok","arguments":"{\\"q\\":\\"y\\",\\"opts\\":{\\"k\\":[1,2,null]},\\"n\\":2.5}"}'

    view = tool_view("tool", "memo_search", payload)

    assert view.tool_status == "ok"
    assert view.tool_args == {"q": "y", "opts": {"k": [1, 2, None]}, "n": 2.5}


@pytest.mark.parametrize("role", ["user", "assistant"])
def test_tool_view_is_all_none_for_a_non_tool_row_even_with_tool_columns__S022_001_DoD1(role: str) -> None:
    """DoD-1 — D3: all three fields are null on a non-tool row."""
    view = tool_view(role, "memo_search", OK_PAYLOAD)

    assert tuple(view) == (None, None, None)


# =========================================================================================
# Seeding
# =========================================================================================


def _insert_user(engine: Engine, *, user_id: int, username: str, password: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.users.insert().values(
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
        )


def _insert_character(engine: Engine, *, character_id: int, user_id: int, name: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.characters.insert().values(
                id=character_id,
                user_id=user_id,
                name=name,
                sheet="",
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_session(engine: Engine, *, session_id: int, user_id: int, character_id: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.insert().values(
                id=session_id,
                user_id=user_id,
                character_id=character_id,
                setup_id=None,
                last_used_at=TIMESTAMP,
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_message(
    engine: Engine,
    *,
    message_id: int,
    text: str,
    role: str = "user",
    user_id: int = PLAYER_A_ID,
    session_id: int = SESSION_A,
    kind: str | None = None,
    related_to: int | None = None,
    settled_at: str | None = None,
    tool_name: str | None = None,
    tool_payload: str | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.messages.insert().values(
                id=message_id,
                user_id=user_id,
                session_id=session_id,
                role=role,
                kind=kind,
                text=text,
                related_to=related_to,
                settled_at=settled_at,
                tool_name=tool_name,
                tool_payload=tool_payload,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _seed_four_row_zone(engine: Engine) -> None:
    """The DoD-2 zone: `[user, assistant, tool(ok, row 3), tool(failed, row 4)]`."""
    _insert_message(engine, message_id=31, text="Aria asks about the lighthouse.", role="user")
    _insert_message(engine, message_id=32, text="Let me look.", role="assistant")
    _insert_message(
        engine, message_id=33, text=OK_SUMMARY, role="tool", tool_name="memo_search", tool_payload=OK_PAYLOAD
    )
    _insert_message(
        engine,
        message_id=34,
        text=FAILED_TEXT,
        role="tool",
        tool_name="session_search",
        tool_payload=FAILED_PAYLOAD,
    )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database: the registry, two owners, a character and a session each."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=PLAYER_A_ID, username=PLAYER_A_NAME, password=PLAYER_A_PASSWORD)
    _insert_user(db_engine, user_id=PLAYER_B_ID, username=PLAYER_B_NAME, password=PLAYER_B_PASSWORD)
    _insert_character(db_engine, character_id=CHAR_A, user_id=PLAYER_A_ID, name="Aria")
    _insert_character(db_engine, character_id=CHAR_B, user_id=PLAYER_B_ID, name="Bob's own")
    _insert_session(db_engine, session_id=SESSION_A, user_id=PLAYER_A_ID, character_id=CHAR_A)
    _insert_session(db_engine, session_id=SESSION_B, user_id=PLAYER_B_ID, character_id=CHAR_B)
    return db_engine


@pytest.fixture
def generator() -> SnowflakeGenerator:
    return SnowflakeGenerator(node_id=1)


# =========================================================================================
# DoD-2: list_zone carries the tool view
# =========================================================================================


def test_list_zone_carries_the_tool_view_on_tool_rows_only__S022_001_DoD2(engine: Engine) -> None:
    """DoD-2 — D3 / 021 D7: user and assistant rows have all three tool fields None; the ok
    tool row is `ok` / `{"query": "lighthouse"}`; the failed one `failed` / `{"query": "x"}`."""
    _seed_four_row_zone(engine)

    with engine.connect() as connection:
        zone = list_zone(connection, PLAYER_A_ID, SESSION_A)

    assert [message.id for message in zone] == [31, 32, 33, 34]
    user_row, assistant_row, ok_row, failed_row = zone
    for plain in (user_row, assistant_row):
        assert plain.tool_name is None
        assert plain.tool_status is None
        assert plain.tool_args is None
    assert ok_row.role == "tool"
    assert ok_row.tool_name == "memo_search"
    assert ok_row.tool_status == "ok"
    assert ok_row.tool_args == {"query": "lighthouse"}
    assert failed_row.role == "tool"
    assert failed_row.tool_name == "session_search"
    assert failed_row.tool_status == "failed"
    assert failed_row.tool_args == {"query": "x"}


def test_a_stream_message_built_without_the_new_fields_defaults_them_to_none__S022_001_DoD2() -> None:
    """DoD-2 — Interface intent: `tool_status` / `tool_args` default to None, so the existing
    eight-field construction stays valid and a non-tool row carries none."""
    message = StreamMessage(
        id=1,
        session_id=2,
        role="user",
        kind=None,
        text="Hello",
        settled_at=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )

    assert message.tool_status is None
    assert message.tool_args is None


# =========================================================================================
# Router: application and login
# =========================================================================================


@pytest.fixture(autouse=True)
def _quiet_factory_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.main.configure_logging", lambda settings: None)


@pytest.fixture
def application(db_settings: Settings, engine: Engine) -> Iterator[FastAPI]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: db_settings
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


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
    return tokens[0]


def _as(application: FastAPI, settings: Settings, username: str, password: str) -> TestClient:
    client = TestClient(application)
    client.cookies.set(settings.session_cookie_name, _login_token(application, settings, username, password))
    return client


def _player_a(application: FastAPI, settings: Settings) -> TestClient:
    return _as(application, settings, PLAYER_A_NAME, PLAYER_A_PASSWORD)


def _assert_envelope(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    return body


def _assert_no_tool_internals(response: httpx.Response) -> None:
    """D3 / U2 — the raw payload, its call id and its content never leave the backend."""
    for forbidden in ("tool_payload", "call_id", "call_1", "Memo: the lighthouse keeper"):
        assert forbidden not in response.text


# =========================================================================================
# DoD-4: GET …/entries carries the eleven keys, tool fields null on settled rows
# =========================================================================================


def test_entries_route_messages_carry_eleven_keys_with_null_tool_fields__S022_001_DoD4(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-4 — D3: settled partner / turn / decision rows each have exactly the eleven keys,
    with `tool_name`, `tool_status` and `tool_args` all JSON null."""
    _insert_message(
        engine, message_id=41, text="The partner speaks.", role="user", kind="partner", settled_at=SEEDED_SETTLED_AT
    )
    _insert_message(engine, message_id=42, text="My turn.", role="user", kind="turn", settled_at=SEEDED_SETTLED_AT)
    _insert_message(
        engine, message_id=43, text="((skip ahead))", role="user", kind="decision", settled_at=SEEDED_SETTLED_AT
    )
    client = _player_a(application, db_settings)

    response = client.get(f"/api/sessions/{SESSION_A}/entries")

    assert response.status_code == 200, response.text
    rows = response.json()["entries"]
    assert [row["id"] for row in rows] == ["41", "42", "43"]
    assert [row["kind"] for row in rows] == ["partner", "turn", "decision"]
    for row in rows:
        assert set(row) == MESSAGE_KEYS
        assert row["tool_name"] is None
        assert row["tool_status"] is None
        assert row["tool_args"] is None


def test_zone_route_failed_tool_row_carries_its_view_and_no_internals__S022_001_DoD4(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-4 — D3: on the same wire, the failed tool row carries `session_search` / `failed` /
    `{"query": "x"}`; the user and assistant rows carry null tool fields; no internals leak."""
    _seed_four_row_zone(engine)
    client = _player_a(application, db_settings)

    response = client.get(f"/api/sessions/{SESSION_A}/zone")

    assert response.status_code == 200, response.text
    rows = response.json()["messages"]
    assert [row["id"] for row in rows] == ["31", "32", "33", "34"]
    for row in rows:
        assert set(row) == MESSAGE_KEYS
    for plain in rows[:2]:
        assert plain["tool_name"] is None
        assert plain["tool_status"] is None
        assert plain["tool_args"] is None
    failed = rows[3]
    assert failed["tool_name"] == "session_search"
    assert failed["tool_status"] == "failed"
    assert failed["tool_args"] == {"query": "x"}
    assert failed["text"] == FAILED_TEXT
    _assert_no_tool_internals(response)
    assert "tool_failed" not in response.text


# =========================================================================================
# DoD-5: PATCH answers eleven keys; the tool-row refusal is unchanged
# =========================================================================================


def test_patch_on_a_zone_assistant_row_answers_eleven_keys_with_null_tool_fields__S022_001_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-5 — D3: 200; the edited message has exactly the eleven keys, the new text and all
    three tool fields null."""
    _seed_four_row_zone(engine)
    client = _player_a(application, db_settings)

    response = client.patch("/api/messages/32", json={"text": "Let me look again."})

    assert response.status_code == 200, response.text
    edited = response.json()
    assert set(edited) == MESSAGE_KEYS
    assert edited["id"] == "32"
    assert edited["role"] == "assistant"
    assert edited["text"] == "Let me look again."
    assert edited["tool_name"] is None
    assert edited["tool_status"] is None
    assert edited["tool_args"] is None


def test_patch_on_a_tool_row_is_still_message_not_editable__S022_001_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-5 — 021 D8: PATCH of a tool row answers 409 `message_not_editable`, and the error
    body leaks no tool internals."""
    _seed_four_row_zone(engine)
    client = _player_a(application, db_settings)

    response = client.patch("/api/messages/33", json={"text": "Changed."})

    _assert_envelope(response, 409, "message_not_editable")
    _assert_no_tool_internals(response)


# =========================================================================================
# DoD-6: append_tool_message returns the derived view
# =========================================================================================


def test_append_tool_message_returns_the_derived_ok_view__S022_001_DoD6(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-6 — D3: given row 3's ok payload, the returned message is `ok` /
    `{"query": "lighthouse"}` with tool name `memo_search`."""
    with engine.connect() as connection:
        created = append_tool_message(
            connection, generator, PLAYER_A_ID, SESSION_A, OK_SUMMARY, "memo_search", OK_PAYLOAD
        )

    assert isinstance(created, StreamMessage)
    assert created.role == "tool"
    assert created.tool_name == "memo_search"
    assert created.tool_status == "ok"
    assert created.tool_args == {"query": "lighthouse"}


def test_append_tool_message_returns_the_derived_failed_view__S022_001_DoD6(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-6 — D3: given row 4's failed payload, the returned message is `failed` /
    `{"query": "x"}`."""
    with engine.connect() as connection:
        created = append_tool_message(
            connection, generator, PLAYER_A_ID, SESSION_A, FAILED_TEXT, "session_search", FAILED_PAYLOAD
        )

    assert created.tool_name == "session_search"
    assert created.tool_status == "failed"
    assert created.tool_args == {"query": "x"}


def test_append_tool_message_result_matches_the_zone_reread__S022_001_DoD6(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-6 — Interface intent: every path that builds a tool `StreamMessage` carries the
    same derived values, so the append result's view equals the re-read row's."""
    with engine.connect() as connection:
        created = append_tool_message(
            connection, generator, PLAYER_A_ID, SESSION_A, OK_SUMMARY, "memo_search", OK_PAYLOAD
        )
    with engine.connect() as connection:
        (listed,) = list_zone(connection, PLAYER_A_ID, SESSION_A)

    assert listed.id == created.id
    assert (listed.tool_name, listed.tool_status, listed.tool_args) == (
        created.tool_name,
        created.tool_status,
        created.tool_args,
    )
    assert (listed.tool_status, listed.tool_args) == ("ok", {"query": "lighthouse"})
