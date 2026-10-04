"""Feature 022, step 002 — the buried-group read: `list_discussion` and `GET …/discussion`
(DoD-2..8).

Every expected value comes from `docs/plans/022.discussion-ui/002.discussion-read.md`
(Interface intent + Definition of done), `002.context.md` (seeding states), `001.context.md`
(payload row 3) and the feature `context.md` (**D1**'s answer table, **D3**'s tool view and
eleven wire keys, R5 owner scoping, R11 reads change nothing). Bindings come from `status.md`
`## Skeleton`, Steps 001–002:

- `list_discussion(connection, user_id, entry_id) -> list[StreamMessage]`; raises
  `MessageNotFoundError` (from `app.errors`) when `entry_id` is not an owned settled row
- `GET /api/messages/{message_id}/discussion` -> 200 `DiscussionResponse` (`{"messages": [...]}`)
- `StreamMessage` carries `tool_name` / `tool_status` / `tool_args` (001)

DoD-1 (the `buried_messages` selectable) lives in `tests/test_db_schema.py`
(`…__S022_002_DoD1`). DoD-9 is `[manual/live]`. Each test name here ends
`__S022_002_DoD<n>`. `StreamMessage` has no `related_to` field and `related_to` is not a
wire key, so `related_to` is checked on the seeded rows. Seeding: registry via
`schema.metadata.create_all`, raw-inserted users / characters / sessions / messages with
explicit `related_to` / `settled_at`; two users; `conftest.py` untouched.
"""

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy import text as sql_text

from app.config import Settings, get_settings
from app.db import schema
from app.errors import MessageNotFoundError
from app.main import create_app
from app.roles import Role
from app.services.messages import list_discussion
from app.services.passwords import hash_password

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
SEEDED_SETTLED_AT = "2025-12-31T00:00:00.000000+00:00"

PLAYER_A_ID = 9_422_101
PLAYER_A_NAME = "aster"
PLAYER_A_PASSWORD = "a quiet river at dusk"

PLAYER_B_ID = 9_422_102
PLAYER_B_NAME = "briar"
PLAYER_B_PASSWORD = "salt and lantern light"

CHAR_A = 1_201
CHAR_B = 2_201

SESSION_A = 5_201
SESSION_B = 6_201

LOGIN_PATH = "/api/auth/login"
NOT_AUTHENTICATED = "not_authenticated"
MESSAGE_NOT_FOUND = "message_not_found"

_BASE = 7_250_000_000_000_000_000

#: Player A's settled turn with three buried rows `[user, tool, assistant]` by id.
ENTRY_A = _BASE + 100
BURIED_USER = _BASE + 101
BURIED_TOOL = _BASE + 102
BURIED_ASSISTANT = _BASE + 103
#: Player A's settled partner block (nothing buried, R11).
PARTNER_A = _BASE + 200
#: Player A's lone directly-settled turn (nothing buried).
LONE_TURN_A = _BASE + 300
#: Player A's zone row (NULL / NULL).
ZONE_A = _BASE + 400
#: A second settled entry of player A in the same session, with its own buried rows (DoD-5).
SECOND_ENTRY_A = _BASE + 500
SECOND_BURIED_1 = _BASE + 501
SECOND_BURIED_2 = _BASE + 502
#: Player B's settled turn with a buried row, in B's session.
ENTRY_B = _BASE + 600
BURIED_B = _BASE + 601
#: An id no row carries.
UNKNOWN_ID = _BASE + 999

BURIED_USER_TEXT = "Should Aria tell him about the lighthouse?"
BURIED_TOOL_TEXT = "Found 1 memo."
BURIED_ASSISTANT_TEXT = "<think>check the memo</think>Yes, but keep it short."
SECOND_BURIED_1_TEXT = "Another question entirely."
SECOND_BURIED_2_TEXT = "Another answer entirely."
BURIED_B_TEXT = "Bob's private question."

#: The texts buried under player A's `ENTRY_A`.
ENTRY_A_BURIED_TEXTS = (BURIED_USER_TEXT, BURIED_TOOL_TEXT, BURIED_ASSISTANT_TEXT)

#: `001.context.md` row 3 — the ok payload.
OK_PAYLOAD = (
    '{"call_id":"call_1","arguments":"{\\"query\\":\\"lighthouse\\"}","status":"ok",'
    '"content":"Memo: the lighthouse keeper"}'
)

#: D3 — the eight 012 keys plus `tool_name`, `tool_status`, `tool_args`.
#: Amended by feature 024, step 005 (DoD-9 regression fallout; `context.md` **Wire contract**:
#: always present on the backend wire, and `false` on any route that is not a record-keeping
#: write) — plus `search_coverage_incomplete`, twelve keys. Scope here is this key set alone;
#: the flag's behaviour is covered in `test_record_keeping_embedding.py`.
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
    "search_coverage_incomplete",
}


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


def _settled(engine: Engine, message_id: int, text: str, *, kind: str = "turn", **extra: Any) -> None:
    """A settled entry: `settled_at` set, `related_to` NULL, `kind` set."""
    _insert_message(engine, message_id=message_id, text=text, kind=kind, settled_at=SEEDED_SETTLED_AT, **extra)


def _buried(engine: Engine, message_id: int, entry_id: int, text: str, **extra: Any) -> None:
    """A buried row: `related_to` = the entry, `settled_at` NULL, `kind` NULL."""
    _insert_message(engine, message_id=message_id, text=text, related_to=entry_id, **extra)


def _seed_stream(engine: Engine) -> None:
    """Every state D1's table names, for both players.

    The buried rows under `ENTRY_A` are inserted out of id order, so "ascending by id" is the
    read's ordering and not the insertion order.
    """
    _settled(engine, ENTRY_A, "Aria nods and answers him.")
    _buried(engine, BURIED_ASSISTANT, ENTRY_A, BURIED_ASSISTANT_TEXT, role="assistant")
    _buried(engine, BURIED_USER, ENTRY_A, BURIED_USER_TEXT, role="user")
    _buried(
        engine,
        BURIED_TOOL,
        ENTRY_A,
        BURIED_TOOL_TEXT,
        role="tool",
        tool_name="memo_search",
        tool_payload=OK_PAYLOAD,
    )
    _settled(engine, PARTNER_A, "The keeper asks a question.", kind="partner")
    _settled(engine, LONE_TURN_A, "Aria leaves without a word.")
    _insert_message(engine, message_id=ZONE_A, text="A zone draft.")
    _settled(engine, SECOND_ENTRY_A, "A later settled turn.")
    _buried(engine, SECOND_BURIED_1, SECOND_ENTRY_A, SECOND_BURIED_1_TEXT, role="user")
    _buried(engine, SECOND_BURIED_2, SECOND_ENTRY_A, SECOND_BURIED_2_TEXT, role="assistant")
    _settled(engine, ENTRY_B, "Bob's settled turn.", user_id=PLAYER_B_ID, session_id=SESSION_B)
    _buried(engine, BURIED_B, ENTRY_B, BURIED_B_TEXT, user_id=PLAYER_B_ID, session_id=SESSION_B)


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database: the registry, two owners, a character and a session each, and the
    seeded stream."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=PLAYER_A_ID, username=PLAYER_A_NAME, password=PLAYER_A_PASSWORD)
    _insert_user(db_engine, user_id=PLAYER_B_ID, username=PLAYER_B_NAME, password=PLAYER_B_PASSWORD)
    _insert_character(db_engine, character_id=CHAR_A, user_id=PLAYER_A_ID, name="Aria")
    _insert_character(db_engine, character_id=CHAR_B, user_id=PLAYER_B_ID, name="Bob's own")
    _insert_session(db_engine, session_id=SESSION_A, user_id=PLAYER_A_ID, character_id=CHAR_A)
    _insert_session(db_engine, session_id=SESSION_B, user_id=PLAYER_B_ID, character_id=CHAR_B)
    _seed_stream(db_engine)
    return db_engine


def _stored_related_to(engine: Engine, message_ids: list[int]) -> dict[int, Any]:
    id_list = ",".join(str(message_id) for message_id in message_ids)
    with engine.connect() as connection:
        rows = connection.execute(sql_text(f"SELECT id, related_to FROM messages WHERE id IN ({id_list})")).all()
    return {row[0]: row[1] for row in rows}


def _snapshot(engine: Engine) -> dict[int, tuple[Any, Any, Any, Any]]:
    """Every row's `(related_to, settled_at, text, updated_at)`, by id."""
    with engine.connect() as connection:
        rows = connection.execute(
            sql_text("SELECT id, related_to, settled_at, text, updated_at FROM messages")
        ).all()
    return {row[0]: (row[1], row[2], row[3], row[4]) for row in rows}


# =========================================================================================
# DoD-2: an owned settled turn's buried rows, ascending by id, with the tool view
# =========================================================================================


def test_list_discussion_returns_the_three_buried_rows_in_id_order__S022_002_DoD2(engine: Engine) -> None:
    """DoD-2 — D1 / US-040.AC-1: player A's settled turn with buried `[user, tool, assistant]`
    returns those three, ascending by id, role and text as stored."""
    with engine.connect() as connection:
        messages = list_discussion(connection, PLAYER_A_ID, ENTRY_A)

    assert [message.id for message in messages] == [BURIED_USER, BURIED_TOOL, BURIED_ASSISTANT]
    assert [message.role for message in messages] == ["user", "tool", "assistant"]
    assert [message.text for message in messages] == list(ENTRY_A_BURIED_TEXTS)
    assert all(message.session_id == SESSION_A for message in messages)


def test_list_discussion_returns_rows_whose_related_to_is_the_entry__S022_002_DoD2(engine: Engine) -> None:
    """DoD-2 — D1: every returned row is stored with `related_to` = the entry (checked on the
    seeded rows)."""
    with engine.connect() as connection:
        messages = list_discussion(connection, PLAYER_A_ID, ENTRY_A)

    ids = [message.id for message in messages]
    assert ids
    assert _stored_related_to(engine, ids) == {message_id: ENTRY_A for message_id in ids}


def test_list_discussion_tool_row_carries_the_derived_tool_view__S022_002_DoD2(engine: Engine) -> None:
    """DoD-2 — D3 / `001.context.md` row 3: the buried tool row carries `memo_search` / `ok` /
    `{"query": "lighthouse"}`; the user and assistant rows carry no tool view."""
    with engine.connect() as connection:
        user_row, tool_row, assistant_row = list_discussion(connection, PLAYER_A_ID, ENTRY_A)

    assert tool_row.tool_name == "memo_search"
    assert tool_row.tool_status == "ok"
    assert tool_row.tool_args == {"query": "lighthouse"}
    for plain in (user_row, assistant_row):
        assert plain.tool_name is None
        assert plain.tool_status is None
        assert plain.tool_args is None


# =========================================================================================
# DoD-3: a confirmed entry with nothing buried is an empty list
# =========================================================================================


@pytest.mark.parametrize("entry_id", [PARTNER_A, LONE_TURN_A], ids=["settled-partner", "lone-settled-turn"])
def test_list_discussion_on_an_entry_with_nothing_buried_is_empty__S022_002_DoD3(
    engine: Engine, entry_id: int
) -> None:
    """DoD-3 — D1: a settled partner row and a settled turn with nothing buried return `[]`."""
    with engine.connect() as connection:
        messages = list_discussion(connection, PLAYER_A_ID, entry_id)

    assert messages == []


# =========================================================================================
# DoD-4: not an owned settled row -> MessageNotFoundError
# =========================================================================================

NOT_FOUND_CASES: list[tuple[str, int, int]] = [
    ("unknown-id", PLAYER_A_ID, UNKNOWN_ID),
    ("b-entry-as-a", PLAYER_A_ID, ENTRY_B),
    ("a-entry-as-b", PLAYER_B_ID, ENTRY_A),
    ("zone-row", PLAYER_A_ID, ZONE_A),
    ("buried-row", PLAYER_A_ID, BURIED_USER),
]


@pytest.mark.parametrize(
    ("caller_id", "entry_id"),
    [(caller, entry) for _, caller, entry in NOT_FOUND_CASES],
    ids=[name for name, _, _ in NOT_FOUND_CASES],
)
def test_list_discussion_raises_message_not_found_for_a_non_entry__S022_002_DoD4(
    engine: Engine, caller_id: int, entry_id: int
) -> None:
    """DoD-4 — D1 / R5: an unknown id, B's entry as A, A's entry as B, a zone row and a buried
    row all raise `MessageNotFoundError`, and none of A's buried rows comes back."""
    with engine.connect() as connection:
        with pytest.raises(MessageNotFoundError) as caught:
            list_discussion(connection, caller_id, entry_id)

    for buried_text in ENTRY_A_BURIED_TEXTS:
        assert buried_text not in str(caught.value)


# =========================================================================================
# DoD-5: another entry's buried rows stay with that entry
# =========================================================================================


def test_list_discussion_excludes_rows_buried_under_another_entry__S022_002_DoD5(engine: Engine) -> None:
    """DoD-5 — D1: rows buried under a different settled entry in the same session are not
    returned for this entry, and vice versa."""
    with engine.connect() as connection:
        first = list_discussion(connection, PLAYER_A_ID, ENTRY_A)
        second = list_discussion(connection, PLAYER_A_ID, SECOND_ENTRY_A)

    first_ids = [message.id for message in first]
    second_ids = [message.id for message in second]
    assert SECOND_BURIED_1 not in first_ids
    assert SECOND_BURIED_2 not in first_ids
    assert first_ids == [BURIED_USER, BURIED_TOOL, BURIED_ASSISTANT]
    assert second_ids == [SECOND_BURIED_1, SECOND_BURIED_2]
    assert [message.text for message in second] == [SECOND_BURIED_1_TEXT, SECOND_BURIED_2_TEXT]


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


def _player_b(application: FastAPI, settings: Settings) -> TestClient:
    return _as(application, settings, PLAYER_B_NAME, PLAYER_B_PASSWORD)


def _assert_envelope(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    return body


def _discussion_path(message_id: int) -> str:
    return f"/api/messages/{message_id}/discussion"


# =========================================================================================
# DoD-6: the owner's GET answers the group
# =========================================================================================


def test_get_discussion_as_the_owner_answers_the_buried_rows__S022_002_DoD6(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-6 — D1 / US-040.AC-1: 200 `{"messages": [...]}`; each message has the eleven keys;
    ids are JSON strings; order is ascending by id."""
    client = _player_a(application, db_settings)

    response = client.get(_discussion_path(ENTRY_A))

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"messages"}
    rows = body["messages"]
    assert [row["id"] for row in rows] == [str(BURIED_USER), str(BURIED_TOOL), str(BURIED_ASSISTANT)]
    for row in rows:
        assert set(row) == MESSAGE_KEYS
        assert isinstance(row["id"], str)
    assert [row["role"] for row in rows] == ["user", "tool", "assistant"]
    assert [row["text"] for row in rows] == list(ENTRY_A_BURIED_TEXTS)


def test_get_discussion_rows_are_all_related_to_the_entry__S022_002_DoD6(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-6 — D1: `related_to` is not a wire key, so each returned id is checked on the seeded
    rows: every one has `related_to` = the entry."""
    client = _player_a(application, db_settings)

    response = client.get(_discussion_path(ENTRY_A))

    assert response.status_code == 200, response.text
    rows = response.json()["messages"]
    assert all("related_to" not in row for row in rows)
    ids = [int(row["id"]) for row in rows]
    assert ids
    assert _stored_related_to(engine, ids) == {message_id: ENTRY_A for message_id in ids}


def test_get_discussion_tool_row_carries_d3_fields_and_no_internals__S022_002_DoD6(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-6 — D3: the buried tool row carries `memo_search` / `ok` / `{"query": "lighthouse"}`;
    non-tool rows carry null tool fields; no tool internals leave the backend."""
    client = _player_a(application, db_settings)

    response = client.get(_discussion_path(ENTRY_A))

    assert response.status_code == 200, response.text
    user_row, tool_row, assistant_row = response.json()["messages"]
    assert tool_row["tool_name"] == "memo_search"
    assert tool_row["tool_status"] == "ok"
    assert tool_row["tool_args"] == {"query": "lighthouse"}
    for plain in (user_row, assistant_row):
        assert plain["tool_name"] is None
        assert plain["tool_status"] is None
        assert plain["tool_args"] is None
    for forbidden in ("tool_payload", "call_id", "call_1", "Memo: the lighthouse keeper"):
        assert forbidden not in response.text


# =========================================================================================
# DoD-7: 404 for a non-entry, 200 empty for a partner block, 401 anonymous
# =========================================================================================

ROUTE_NOT_FOUND_IDS: list[tuple[str, int]] = [
    ("unknown-id", UNKNOWN_ID),
    ("foreign-entry", ENTRY_B),
    ("zone-row", ZONE_A),
    ("buried-row", BURIED_USER),
]


@pytest.mark.parametrize(
    "message_id",
    [message_id for _, message_id in ROUTE_NOT_FOUND_IDS],
    ids=[name for name, _ in ROUTE_NOT_FOUND_IDS],
)
def test_get_discussion_answers_404_message_not_found__S022_002_DoD7(
    application: FastAPI, db_settings: Settings, engine: Engine, message_id: int
) -> None:
    """DoD-7 — D1 / R5: an unknown id, a foreign entry, a zone row id and a buried row id answer
    404 `message_not_found`, and no buried text leaks."""
    client = _player_a(application, db_settings)

    response = client.get(_discussion_path(message_id))

    _assert_envelope(response, 404, MESSAGE_NOT_FOUND)
    for buried_text in (*ENTRY_A_BURIED_TEXTS, BURIED_B_TEXT):
        assert buried_text not in response.text


def test_get_discussion_of_a_foreign_entry_is_404_for_player_b_too__S022_002_DoD7(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-7 — R5: player A's entry, requested by player B, answers 404 `message_not_found`."""
    client = _player_b(application, db_settings)

    response = client.get(_discussion_path(ENTRY_A))

    _assert_envelope(response, 404, MESSAGE_NOT_FOUND)
    for buried_text in ENTRY_A_BURIED_TEXTS:
        assert buried_text not in response.text


def test_get_discussion_of_an_owned_partner_block_is_an_empty_list__S022_002_DoD7(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-7 — D1: an owned settled partner block answers 200 `{"messages": []}`."""
    client = _player_a(application, db_settings)

    response = client.get(_discussion_path(PARTNER_A))

    assert response.status_code == 200, response.text
    assert response.json() == {"messages": []}


def test_get_discussion_answers_401_without_a_login__S022_002_DoD7(application: FastAPI, engine: Engine) -> None:
    """DoD-7 — D1: unauthenticated, the route answers 401 through the existing auth dependency."""
    client = TestClient(application)

    response = client.get(_discussion_path(ENTRY_A))

    _assert_envelope(response, 401, NOT_AUTHENTICATED)
    for buried_text in ENTRY_A_BURIED_TEXTS:
        assert buried_text not in response.text


# =========================================================================================
# DoD-8: reading a discussion changes nothing
# =========================================================================================


def test_get_discussion_changes_no_row__S022_002_DoD8(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-8 — R11: after the GET, every seeded row's `related_to`, `settled_at`, `text` and
    `updated_at` are unchanged."""
    before = _snapshot(engine)
    client = _player_a(application, db_settings)

    response = client.get(_discussion_path(ENTRY_A))
    assert response.status_code == 200, response.text
    empty = client.get(_discussion_path(PARTNER_A))
    assert empty.status_code == 200, empty.text

    after = _snapshot(engine)
    assert after == before
    assert len(after) == 12


def test_list_discussion_changes_no_row__S022_002_DoD8(engine: Engine) -> None:
    """DoD-8 — R11: the service read itself leaves every seeded row's `related_to`,
    `settled_at`, `text` and `updated_at` unchanged."""
    before = _snapshot(engine)

    with engine.connect() as connection:
        list_discussion(connection, PLAYER_A_ID, ENTRY_A)
        list_discussion(connection, PLAYER_A_ID, SECOND_ENTRY_A)

    assert _snapshot(engine) == before
