"""Tests for `append_assistant_message` in `app/services/messages.py` — feature 019, step 001.

Every expected value comes from `docs/plans/019.streaming-transport-and-stop/
001.frames-and-assistant-append.md` (Interface intent + Definition of done), `001.context.md`
("Touch sites": `StreamMessage`'s fields, the `messages` columns, `current_zone` =
`related_to IS NULL AND settled_at IS NULL`) and the feature `context.md` (**D8**, R5, R11,
"Test conventions"). Bindings come from `status.md` `## Skeleton`, Step 001:
`append_assistant_message(connection, generator, user_id, session_id, text) -> StreamMessage`.

Each test name ends `__S019_001_DoD<n>`. DoD-5 .. DoD-8 are covered here; DoD-1 .. DoD-4 are
in `tests/test_llm_frames.py`.

Seeding follows 012's service tests: the registry through `schema.metadata.create_all`, then
raw-inserted users, characters and sessions. The router read (DoD-7) builds `create_app()`
with `dependency_overrides[get_settings]` and a logged-in `TestClient`. `conftest.py` is
untouched; every fixture below is file-local.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select

from app.config import Settings, get_settings
from app.db import schema
from app.errors import SessionNotFoundError
from app.ids import SnowflakeGenerator
from app.main import create_app
from app.roles import Role
from app.services.messages import (
    StreamMessage,
    append_assistant_message,
    append_message,
    list_zone,
)
from app.services.passwords import hash_password

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

USER_A = 9_401_001
USER_A_NAME = "aster"
USER_A_PASSWORD = "a quiet river at dusk"

USER_B = 9_401_002
USER_B_NAME = "briar"
USER_B_PASSWORD = "salt and lantern light"

CHAR_A = 1_001
CHAR_B = 2_001

SESSION_A = 5_001
SESSION_B = 6_001

#: An id that belongs to no session of any user.
UNKNOWN_SESSION_ID = 7_250_000_000_000_000_002

LOGIN_PATH = "/api/auth/login"


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
    """One real generator per test, so ids minted within a test never collide."""
    return SnowflakeGenerator(node_id=1)


# --- service call wrappers (one connection per call) -------------------------------------


def _append_assistant(
    engine: Engine, generator: SnowflakeGenerator, user_id: int, session_id: int, text: str
) -> StreamMessage:
    with engine.connect() as connection:
        return append_assistant_message(connection, generator, user_id, session_id, text)


def _append_user(
    engine: Engine, generator: SnowflakeGenerator, user_id: int, session_id: int, text: str
) -> StreamMessage:
    with engine.connect() as connection:
        return append_message(connection, generator, user_id, session_id, text)


# --- direct reads of stored state (tests may read the raw table) -------------------------


def _stored_message(engine: Engine, message_id: int) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(select(schema.messages).where(schema.messages.c.id == message_id)).one()
    return dict(row._mapping)


def _current_zone_rows(engine: Engine, user_id: int, session_id: int) -> list[dict[str, Any]]:
    """The session's current zone through the `current_zone` selectable, id ascending."""
    statement = schema.current_zone.where(
        schema.messages.c.session_id == session_id,
        schema.messages.c.user_id == user_id,
    ).order_by(schema.messages.c.id)
    with engine.connect() as connection:
        return [dict(row._mapping) for row in connection.execute(statement)]


def _all_messages(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(select(schema.messages).order_by(schema.messages.c.id)).all()
    return [dict(row._mapping) for row in rows]


def _count_messages(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(schema.messages)).scalar_one())


# --- DoD-5: an owned session gets one assistant zone row ---------------------------------

ASSISTANT_TEXT = "  Aria tilts her head. «Ну что ж…»\n\nShe waits.  "


def test_the_returned_value_is_an_assistant_zone_message__S019_001_DoD5(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-5 — role 'assistant', kind None, settled_at None, the text verbatim, the given
    session id (D8, US-132.AC-1)."""
    created = _append_assistant(engine, generator, USER_A, SESSION_A, ASSISTANT_TEXT)

    assert isinstance(created, StreamMessage)
    assert created.role == "assistant"
    assert created.kind is None
    assert created.settled_at is None
    assert created.text == ASSISTANT_TEXT
    assert created.session_id == SESSION_A


def test_the_row_is_readable_through_the_current_zone_view__S019_001_DoD5(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-5 — afterwards the `current_zone` selectable holds exactly that row, role
    'assistant', kind / related_to / settled_at NULL, the caller's user and session."""
    created = _append_assistant(engine, generator, USER_A, SESSION_A, ASSISTANT_TEXT)

    rows = _current_zone_rows(engine, USER_A, SESSION_A)

    assert [row["id"] for row in rows] == [created.id]
    (row,) = rows
    assert row["role"] == "assistant"
    assert row["kind"] is None
    assert row["related_to"] is None
    assert row["settled_at"] is None
    assert row["text"] == ASSISTANT_TEXT
    assert row["user_id"] == USER_A
    assert row["session_id"] == SESSION_A


def test_the_row_is_in_the_service_zone_read__S019_001_DoD5(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-5 — `list_zone` (which reads through `current_zone`) returns the same value."""
    created = _append_assistant(engine, generator, USER_A, SESSION_A, ASSISTANT_TEXT)

    with engine.connect() as connection:
        zone = list_zone(connection, USER_A, SESSION_A)

    assert zone == [created]


# --- DoD-6: another user's or an unknown session is not found, and nothing is written ----


@pytest.mark.parametrize("session_id", [SESSION_B, UNKNOWN_SESSION_ID])
def test_a_foreign_or_unknown_session_is_not_found_and_writes_nothing__S019_001_DoD6(
    engine: Engine, generator: SnowflakeGenerator, session_id: int
) -> None:
    """DoD-6 — `SessionNotFoundError`; the `messages` table is unchanged (D8, R5)."""
    _append_user(engine, generator, USER_B, SESSION_B, "Bob's own draft.")
    messages_before = _all_messages(engine)
    count_before = _count_messages(engine)

    with pytest.raises(SessionNotFoundError):
        _append_assistant(engine, generator, USER_A, session_id, "An intruding reply.")

    assert _count_messages(engine) == count_before
    assert _all_messages(engine) == messages_before


# --- DoD-7: the zone route serves the assistant row --------------------------------------


@pytest.fixture(autouse=True)
def _quiet_factory_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the factory's logging call so these tests touch no global sinks."""
    monkeypatch.setattr("app.main.configure_logging", lambda settings: None)


@pytest.fixture
def application(db_settings: Settings, engine: Engine) -> Iterator[FastAPI]:
    """The factory's application, pinned to the seeded per-test database."""
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
    response = TestClient(application).post(LOGIN_PATH, json={"username": username, "password": password})
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


def test_the_zone_route_lists_the_assistant_row_after_the_user_row__S019_001_DoD7(
    application: FastAPI, db_settings: Settings, engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-7 — `GET /api/sessions/{id}/zone` answers 200 and lists the earlier
    `append_message` row, then the assistant row with `"role":"assistant"`; each `id` a
    decimal string; id order (D8; the `models/stream.py` role check)."""
    user_row = _append_user(engine, generator, USER_A, SESSION_A, "Aria leans in.")
    assistant_row = _append_assistant(engine, generator, USER_A, SESSION_A, "She smiles back.")
    client = _logged_in(application, db_settings, USER_A_NAME, USER_A_PASSWORD)

    response = client.get(f"/api/sessions/{SESSION_A}/zone")

    assert response.status_code == 200, response.text
    rows = response.json()["messages"]
    assert [row["id"] for row in rows] == [str(user_row.id), str(assistant_row.id)]
    for row in rows:
        assert isinstance(row["id"], str)
        assert row["id"].isdigit()
    assert int(rows[0]["id"]) < int(rows[1]["id"])
    assert rows[0]["role"] == "user"
    assert rows[1]["role"] == "assistant"
    assert rows[1]["kind"] is None
    assert rows[1]["settled_at"] is None
    assert rows[1]["text"] == "She smiles back."
    assert rows[1]["session_id"] == str(SESSION_A)


# --- DoD-8: append_message still writes role 'user' --------------------------------------


def test_append_message_still_writes_role_user__S019_001_DoD8(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-8 — the returned value and the stored row both carry role 'user', kind NULL,
    settled_at NULL (D8: behaviour unchanged)."""
    created = _append_user(engine, generator, USER_A, SESSION_A, "A roleplayer's draft.")
    stored = _stored_message(engine, created.id)

    assert created.role == "user"
    assert created.kind is None
    assert created.settled_at is None
    assert stored["role"] == "user"
    assert stored["kind"] is None
    assert stored["settled_at"] is None
    assert stored["related_to"] is None


def test_the_two_appends_keep_their_own_roles_side_by_side__S019_001_DoD8(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-8 — an assistant append before and after does not change what `append_message`
    writes: the zone holds user, assistant, user in call order."""
    first = _append_user(engine, generator, USER_A, SESSION_A, "one")
    second = _append_assistant(engine, generator, USER_A, SESSION_A, "two")
    third = _append_user(engine, generator, USER_A, SESSION_A, "three")

    rows = _current_zone_rows(engine, USER_A, SESSION_A)

    assert [row["id"] for row in rows] == [first.id, second.id, third.id]
    assert [row["role"] for row in rows] == ["user", "assistant", "user"]
