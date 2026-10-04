"""Tests for tool rows in `app/services/messages.py` and `ToolFailedError` — feature 021, step 001.

Every expected value comes from `docs/plans/021.compose-loop-and-tools/001.tool-rows-and-settle.md`
(Interface intent + Definition of done), `001.context.md` and the feature `context.md`
(**D7** tool-row columns and payload shape, **D8** edit refusal, **D13** `tool_failed`, R5,
012's eight-key wire contract). Bindings come from `status.md` `## Skeleton`, Step 001:

- `append_tool_message(connection, generator, user_id, session_id, text, tool_name,
  tool_payload) -> StreamMessage`
- `StreamMessage` gains `tool_name: str | None = None`, `tool_payload: str | None = None`
- `edit_message_text(connection, user_id, message_id, text) -> StreamMessage` (unchanged)
- `ToolFailedError(message=None, detail=None)`, `code = "tool_failed"`, `http_status = 502`

DoD-1, 2, 3, 4, 5, 14 are covered here. Each test name ends `__S021_001_DoD<n>`.
Seeding: registry via `schema.metadata.create_all`, raw-inserted users / characters /
sessions; two users for isolation; `conftest.py` untouched.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select

from app.config import Settings, get_settings
from app.db import schema
from app.errors import (
    DomainError,
    MessageNotEditableError,
    SessionNotFoundError,
    ToolFailedError,
)
from app.ids import SnowflakeGenerator
from app.main import create_app
from app.roles import Role
from app.services.messages import (
    StreamMessage,
    append_assistant_message,
    append_message,
    append_tool_message,
    edit_message_text,
    list_entries,
    list_zone,
)
from app.services.passwords import hash_password

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
SEEDED_SETTLED_AT = "2025-12-31T00:00:00.000000+00:00"

USER_A = 9_421_001
USER_A_NAME = "aster"
USER_A_PASSWORD = "a quiet river at dusk"

USER_B = 9_421_002
USER_B_NAME = "briar"
USER_B_PASSWORD = "salt and lantern light"

CHAR_A = 1_001
CHAR_B = 2_001

SESSION_A = 5_001
SESSION_B = 6_001

#: An id that belongs to no session of any user.
UNKNOWN_SESSION_ID = 7_250_000_000_000_000_002

LOGIN_PATH = "/api/auth/login"

#: 012's wire contract — the eight keys of a message object.
MESSAGE_KEYS = {"id", "session_id", "role", "kind", "text", "settled_at", "created_at", "updated_at"}

TOOL_NAME = "memo_search"
TOOL_TEXT = "1 memo found"
#: A D7-shaped ok payload (compact JSON) — passed and expected verbatim.
TOOL_PAYLOAD = (
    '{"call_id":"call_1","arguments":"{\\"query\\":\\"inn\\"}","status":"ok",'
    '"content":"The inn is called The Gilded Goose."}'
)
#: A D7-shaped failed payload.
FAILED_TOOL_TEXT = "The tool failed."
FAILED_TOOL_PAYLOAD = (
    '{"call_id":"call_2","arguments":"not json","status":"failed","code":"tool_failed"}'
)


# --- seeding -----------------------------------------------------------------------------


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
    user_id: int = USER_A,
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


def _insert_tool(engine: Engine, message_id: int) -> None:
    """A raw current-zone tool row (D7 columns)."""
    _insert_message(
        engine,
        message_id=message_id,
        text=TOOL_TEXT,
        role="tool",
        tool_name=TOOL_NAME,
        tool_payload=TOOL_PAYLOAD,
    )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database: the registry, two owners, a character and a session each."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username=USER_A_NAME, password=USER_A_PASSWORD)
    _insert_user(db_engine, user_id=USER_B, username=USER_B_NAME, password=USER_B_PASSWORD)
    _insert_character(db_engine, character_id=CHAR_A, user_id=USER_A, name="Aria")
    _insert_character(db_engine, character_id=CHAR_B, user_id=USER_B, name="Bob's own")
    _insert_session(db_engine, session_id=SESSION_A, user_id=USER_A, character_id=CHAR_A)
    _insert_session(db_engine, session_id=SESSION_B, user_id=USER_B, character_id=CHAR_B)
    return db_engine


@pytest.fixture
def generator() -> SnowflakeGenerator:
    return SnowflakeGenerator(node_id=1)


# --- service call wrappers (one connection per call) -------------------------------------


def _append_tool(
    engine: Engine,
    generator: SnowflakeGenerator,
    user_id: int,
    session_id: int,
    text: str = TOOL_TEXT,
    tool_name: str = TOOL_NAME,
    tool_payload: str = TOOL_PAYLOAD,
) -> StreamMessage:
    with engine.connect() as connection:
        return append_tool_message(
            connection, generator, user_id, session_id, text, tool_name, tool_payload
        )


def _append_user(
    engine: Engine, generator: SnowflakeGenerator, user_id: int, session_id: int, text: str
) -> StreamMessage:
    with engine.connect() as connection:
        return append_message(connection, generator, user_id, session_id, text)


def _append_assistant(
    engine: Engine, generator: SnowflakeGenerator, user_id: int, session_id: int, text: str
) -> StreamMessage:
    with engine.connect() as connection:
        return append_assistant_message(connection, generator, user_id, session_id, text)


def _zone(engine: Engine, user_id: int = USER_A, session_id: int = SESSION_A) -> list[StreamMessage]:
    with engine.connect() as connection:
        return list_zone(connection, user_id, session_id)


def _entries(
    engine: Engine, user_id: int = USER_A, session_id: int = SESSION_A
) -> list[StreamMessage]:
    with engine.connect() as connection:
        return list_entries(connection, user_id, session_id)


def _edit(engine: Engine, user_id: int, message_id: int, text: str) -> StreamMessage:
    with engine.connect() as connection:
        return edit_message_text(connection, user_id, message_id, text)


# --- direct reads of stored state ---------------------------------------------------------


def _stored_message(engine: Engine, message_id: int) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(
            select(schema.messages).where(schema.messages.c.id == message_id)
        ).one()
    return dict(row._mapping)


def _all_messages(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(select(schema.messages).order_by(schema.messages.c.id)).all()
    return [dict(row._mapping) for row in rows]


def _count_messages(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(select(func.count()).select_from(schema.messages)).scalar_one()
        )


# =========================================================================================
# DoD-1: append_tool_message on an owned session
# =========================================================================================


def test_append_tool_message_returns_a_tool_zone_message__S021_001_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-1 — D7: role `tool`, kind None, settled_at None; text, tool name and payload
    verbatim; the given session id."""
    created = _append_tool(engine, generator, USER_A, SESSION_A)

    assert isinstance(created, StreamMessage)
    assert created.role == "tool"
    assert created.kind is None
    assert created.settled_at is None
    assert created.text == TOOL_TEXT
    assert created.tool_name == TOOL_NAME
    assert created.tool_payload == TOOL_PAYLOAD
    assert created.session_id == SESSION_A


def test_append_tool_message_keeps_a_failed_payload_verbatim__S021_001_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-1 — D7: the failed-row literal and the failed payload come back unchanged; the
    payload is not interpreted."""
    created = _append_tool(
        engine, generator, USER_A, SESSION_A, FAILED_TOOL_TEXT, "web_search", FAILED_TOOL_PAYLOAD
    )

    assert created.text == FAILED_TOOL_TEXT
    assert created.tool_name == "web_search"
    assert created.tool_payload == FAILED_TOOL_PAYLOAD


def test_append_tool_message_stores_a_current_zone_tool_row__S021_001_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-1 — Interface intent: the stored row is role `tool`, kind / related_to /
    settled_at NULL, both tool columns set, owned by the caller."""
    created = _append_tool(engine, generator, USER_A, SESSION_A)

    stored = _stored_message(engine, created.id)
    assert stored["role"] == "tool"
    assert stored["kind"] is None
    assert stored["related_to"] is None
    assert stored["settled_at"] is None
    assert stored["text"] == TOOL_TEXT
    assert stored["tool_name"] == TOOL_NAME
    assert stored["tool_payload"] == TOOL_PAYLOAD
    assert stored["user_id"] == USER_A
    assert stored["session_id"] == SESSION_A


def test_list_zone_lists_the_tool_row_after_an_earlier_user_row__S021_001_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-1 — `list_zone` lists the user row then the tool row, id order, with the same
    `tool_name` / `tool_payload`."""
    user_row = _append_user(engine, generator, USER_A, SESSION_A, "Aria asks about the inn.")
    tool_row = _append_tool(engine, generator, USER_A, SESSION_A)

    zone = _zone(engine)

    assert [message.id for message in zone] == [user_row.id, tool_row.id]
    assert user_row.id < tool_row.id
    listed_tool = zone[1]
    assert listed_tool.role == "tool"
    assert listed_tool.tool_name == TOOL_NAME
    assert listed_tool.tool_payload == TOOL_PAYLOAD
    assert listed_tool == tool_row


# =========================================================================================
# DoD-2: foreign / unknown session
# =========================================================================================


@pytest.mark.parametrize("session_id", [SESSION_B, UNKNOWN_SESSION_ID], ids=["foreign", "unknown"])
def test_append_tool_message_on_a_foreign_or_unknown_session_is_not_found__S021_001_DoD2(
    engine: Engine, generator: SnowflakeGenerator, session_id: int
) -> None:
    """DoD-2 — R5 / D7: `SessionNotFoundError`; no row is written."""
    _append_user(engine, generator, USER_B, SESSION_B, "Bob's own draft.")
    messages_before = _all_messages(engine)
    count_before = _count_messages(engine)

    with pytest.raises(SessionNotFoundError):
        _append_tool(engine, generator, USER_A, session_id)

    assert _count_messages(engine) == count_before
    assert _all_messages(engine) == messages_before


# =========================================================================================
# DoD-3: tool fields default to None
# =========================================================================================


def test_zone_user_and_assistant_rows_carry_no_tool_fields__S021_001_DoD3(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-3 — D7: `list_zone`'s user and assistant rows have `tool_name` / `tool_payload`
    None."""
    _append_user(engine, generator, USER_A, SESSION_A, "A draft.")
    _append_assistant(engine, generator, USER_A, SESSION_A, "A reply.")

    zone = _zone(engine)

    assert [message.role for message in zone] == ["user", "assistant"]
    for message in zone:
        assert message.tool_name is None
        assert message.tool_payload is None


def test_settled_user_and_assistant_entries_carry_no_tool_fields__S021_001_DoD3(
    engine: Engine,
) -> None:
    """DoD-3 — D7: `list_entries`'s user and assistant rows have both tool fields None."""
    _insert_message(
        engine, message_id=11, text="My turn.", role="user", kind="turn", settled_at=SEEDED_SETTLED_AT
    )
    _insert_message(
        engine,
        message_id=12,
        text="The assistant's turn.",
        role="assistant",
        kind="turn",
        settled_at=SEEDED_SETTLED_AT,
    )

    entries = _entries(engine)

    assert [entry.id for entry in entries] == [11, 12]
    assert [entry.role for entry in entries] == ["user", "assistant"]
    for entry in entries:
        assert entry.tool_name is None
        assert entry.tool_payload is None


def test_a_stream_message_built_from_the_eight_fields_has_no_tool_fields__S021_001_DoD3() -> None:
    """DoD-3 — the original eight-field construction stays valid; both new fields None."""
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

    assert message.tool_name is None
    assert message.tool_payload is None
    assert message.text == "Hello"


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


def _logged_in(application: FastAPI, settings: Settings, username: str, password: str) -> TestClient:
    response = TestClient(application).post(
        LOGIN_PATH, json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    tokens = [
        value
        for name, value in (_parse_set_cookie(h) for h in response.headers.get_list("set-cookie"))
        if name == settings.session_cookie_name
    ]
    assert len(tokens) == 1
    client = TestClient(application)
    client.cookies.set(settings.session_cookie_name, tokens[0])
    return client


# =========================================================================================
# DoD-4: the zone route with a tool row keeps the eight wire keys
# =========================================================================================


def test_the_zone_route_lists_a_tool_row_with_only_the_eight_keys__S021_001_DoD4(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-4 — D7 / 012 wire contract: 200; the tool row appears with `"role":"tool"`; no
    message object carries `tool_name` or `tool_payload`."""
    _insert_message(engine, message_id=21, text="Aria asks about the inn.", role="user")
    _insert_tool(engine, 22)
    _insert_message(engine, message_id=23, text="She answers.", role="assistant")
    client = _logged_in(application, db_settings, USER_A_NAME, USER_A_PASSWORD)

    response = client.get(f"/api/sessions/{SESSION_A}/zone")

    assert response.status_code == 200, response.text
    rows = response.json()["messages"]
    assert [row["id"] for row in rows] == ["21", "22", "23"]
    assert [row["role"] for row in rows] == ["user", "tool", "assistant"]
    assert rows[1]["text"] == TOOL_TEXT
    for row in rows:
        assert set(row) == MESSAGE_KEYS
        assert "tool_name" not in row
        assert "tool_payload" not in row


# =========================================================================================
# DoD-5: tool rows are not editable
# =========================================================================================


def test_edit_message_text_refuses_a_zone_tool_row__S021_001_DoD5(engine: Engine) -> None:
    """DoD-5 — D8 / US-115.AC-1: `MessageNotEditableError`; the row is unchanged."""
    _insert_tool(engine, 31)
    before = _stored_message(engine, 31)
    messages_before = _all_messages(engine)

    with pytest.raises(MessageNotEditableError):
        _edit(engine, USER_A, 31, "A changed summary.")

    assert _stored_message(engine, 31) == before
    assert _stored_message(engine, 31)["text"] == TOOL_TEXT
    assert _all_messages(engine) == messages_before


def test_edit_message_text_still_edits_zone_user_and_assistant_rows__S021_001_DoD5(
    engine: Engine,
) -> None:
    """DoD-5 — D8: in a session holding a tool row, the zone user row and the zone assistant
    row are still edited."""
    _insert_message(engine, message_id=41, text="My draft.", role="user")
    _insert_tool(engine, 42)
    _insert_message(engine, message_id=43, text="The reply.", role="assistant")

    with pytest.raises(MessageNotEditableError):
        _edit(engine, USER_A, 42, "Changed.")
    edited_user = _edit(engine, USER_A, 41, "My better draft.")
    edited_assistant = _edit(engine, USER_A, 43, "The better reply.")

    assert edited_user.id == 41
    assert edited_user.text == "My better draft."
    assert edited_assistant.id == 43
    assert edited_assistant.text == "The better reply."
    assert _stored_message(engine, 41)["text"] == "My better draft."
    assert _stored_message(engine, 43)["text"] == "The better reply."
    assert _stored_message(engine, 42)["text"] == TOOL_TEXT


def test_patch_of_a_tool_row_answers_message_not_editable__S021_001_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-5 — `PATCH /api/messages/{tool row id}` → 409 `message_not_editable`; the row is
    unchanged."""
    _insert_tool(engine, 51)
    before = _stored_message(engine, 51)
    client = _logged_in(application, db_settings, USER_A_NAME, USER_A_PASSWORD)

    response = client.patch("/api/messages/51", json={"text": "Changed."})

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"]["code"] == "message_not_editable"
    assert _stored_message(engine, 51) == before


# =========================================================================================
# DoD-14: ToolFailedError
# =========================================================================================


def test_tool_failed_error_has_code_and_status__S021_001_DoD14() -> None:
    """DoD-14 — D13: a `DomainError`, code `tool_failed`, status 502."""
    assert issubclass(ToolFailedError, DomainError)
    assert ToolFailedError.code == "tool_failed"
    assert ToolFailedError.http_status == 502
    error = ToolFailedError()
    assert error.code == "tool_failed"
    assert error.http_status == 502


def test_tool_failed_error_has_a_non_empty_default_message__S021_001_DoD14() -> None:
    """DoD-14 — D13: the fixed default message is non-empty."""
    error = ToolFailedError()

    assert isinstance(error.message, str)
    assert error.message.strip() != ""


def test_tool_failed_error_keeps_its_detail__S021_001_DoD14() -> None:
    """DoD-14 — D13: given detail `{"tool": "memo_search"}` it keeps that detail, per
    instance."""
    error = ToolFailedError(detail={"tool": "memo_search"})
    other = ToolFailedError(detail={"tool": "web_search"})

    assert dict(error.detail) == {"tool": "memo_search"}
    assert dict(other.detail) == {"tool": "web_search"}
