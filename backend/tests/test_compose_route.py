"""Feature 021 step 006 — the compose route (`POST /api/sessions/{id}/zone/compose`).

Expected values come from `docs/plans/021.compose-loop-and-tools/006.compose-route.md`
(Interface intent, DoD-1..DoD-12), `006.context.md` and the feature `context.md` (D1 commit then
stream, D2 textless compose = retry, D3 model failures as `error` frames, D5 offered tools, D8
tool-only zone counts as empty, D14 the two overridable dependencies) and 019's frame wire
shapes (`{"event": ...}`, ids as decimal strings, `error` = `event`/`code`/`message`/`detail`).
Bindings come from `status.md` `## Skeleton` (Steps 003–006):

- `get_chat_client_factory`, `get_tool_registry` in `app.routers.stream` — override keys
- `ChatClientFactory = Callable[[str, str | None, float], ChatClientLike]`; `ChatDelta(content=...)`
- `ChatMessage` (frozen, comparable)

The application is the real factory's (`create_app()`) with `dependency_overrides` for
`get_settings` (the per-test file database), the chat-client factory (a file-local fake
recording its calls) and — except in DoD-10 — the tool registry. Users, characters, sessions,
registry rows and pre-existing zone rows are raw-inserted; callers log in through
`/api/auth/login`. SSE bodies are split on `"\\n\\n"` and each `data: ` line JSON-parsed. Every
HTTP call runs on a worker thread with a bounded wait. `conftest.py` is untouched.

DoD-12: `tests/test_stream_router.py` holds no assertion depending on the compose route's
absence, so it is not modified; its tests running unchanged is the other half of DoD-12.
DoD-13 and DoD-14 are `[manual/live]` and carry no test. Names end `__S021_006_DoD<n>`.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, Table, func, select, update

from app.config import Settings, get_settings
from app.db import schema
from app.errors import LlmUnreachableError
from app.main import create_app
from app.roles import Role
from app.routers.stream import get_chat_client_factory, get_tool_registry
from app.services.llm.chat import ChatMessage
from app.services.llm.client import ChatDelta
from app.services.passwords import hash_password
from app.services.tools.definitions import MEMO_SEARCH, SESSION_SEARCH

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

LOGIN_PATH = "/api/auth/login"
SESSIONS_PATH = "/api/sessions"
COMPOSE_TEMPLATE = "/api/sessions/{session_id}/zone/compose"

USER_A = 9_661_001
USER_A_NAME = "aster"
USER_A_PASSWORD = "a quiet river at dusk"
USER_B = 9_661_002
USER_B_NAME = "briar"
USER_B_PASSWORD = "salt and lantern light"

CHAR_A = 1_661
CHAR_B = 2_661
SESSION_A = 5_661
SESSION_B = 6_661

#: A decimal id no row holds.
UNKNOWN_SESSION_ID = "7250000000000000002"

SERVER_ONE = 8_661
SERVER_TWO = 8_662
SERVER_SECRET = 8_663
MODEL_ROW_ONE = 8_761
MODEL_ROW_OFF = 8_762
MODEL_ROW_TWO = 8_763
MODEL_ROW_SECRET = 8_764
MODEL_ONE = "story-model-7b"
MODEL_OFF = "retired-model-3b"
MODEL_TWO = "other-model-13b"
MODEL_SECRET = "keyed-model-8b"
BASE_ONE = "http://chat-one.test:8080"
BASE_TWO = "http://chat-two.test:9090"
BASE_SECRET = "http://chat-secret.test:7070"

MISSING_VARIABLE = "RPH_COMPOSE_ROUTE_UNSET_KEY"
MISSING_POINTER = f"${MISSING_VARIABLE}"

COMPOSE_TEXT = "Write me a reply"

#: Error codes (D3, D14, the error model).
LLM_UNREACHABLE = "llm_unreachable"
MODEL_NOT_ENABLED = "model_not_enabled"
NO_MODEL_ENABLED = "no_model_enabled"
MODEL_NOT_CHOSEN = "model_not_chosen"
SECRET_REF_MISSING = "secret_ref_missing"
ZONE_EMPTY = "zone_empty"
SESSION_NOT_FOUND = "session_not_found"
NOT_AUTHENTICATED = "not_authenticated"

#: Bound for every HTTP call (the whole SSE body is collected inside it).
HTTP_TIMEOUT_SECONDS = 20.0


# --- bounded calls ---------------------------------------------------------------------


def _bounded[T](call: Callable[[], T]) -> T:
    """Run `call` on a worker thread; fail the test instead of hanging past the bound."""
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(call).result(timeout=HTTP_TIMEOUT_SECONDS)
    finally:
        pool.shutdown(wait=False)


# --- seeding ---------------------------------------------------------------------------


def _servers() -> Table:
    return schema.metadata.tables["llm_servers"]


def _models() -> Table:
    return schema.metadata.tables["models"]


def _insert_user(engine: Engine, *, user_id: int, username: str, password: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.users.insert().values(
                id=user_id,
                username=username,
                password_hash=hash_password(password),
                role=Role.ROLEPLAYER,
                is_enabled=True,
                rp_language="English",
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
                model_server_id=None,
                model_name=None,
                system_prompt=None,
                tool_memo_search=None,
                tool_session_search=None,
                tool_web_search=None,
            )
        )


def _insert_session(
    engine: Engine,
    *,
    session_id: int,
    user_id: int,
    character_id: int,
    model_server_id: int | None,
    model_name: str | None,
) -> None:
    """A session with all three tool switches explicitly on."""
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
                model_server_id=model_server_id,
                model_name=model_name,
                system_prompt=None,
                tool_memo_search=True,
                tool_session_search=True,
                tool_web_search=True,
                rp_language=None,
                preferred_language=None,
            )
        )


def _insert_server(engine: Engine, *, server_id: int, base_url: str, api_key_ref: str | None = None) -> None:
    with engine.begin() as connection:
        connection.execute(
            _servers()
            .insert()
            .values(
                id=server_id,
                name=f"server {server_id}",
                kind="llamaswap",
                base_url=base_url,
                api_key_ref=api_key_ref,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_model(engine: Engine, *, model_id: int, server_id: int, name: str, enabled: bool) -> None:
    with engine.begin() as connection:
        connection.execute(
            _models()
            .insert()
            .values(
                id=model_id,
                server_id=server_id,
                model_name=name,
                is_enabled=enabled,
                is_embedding_designated=False,
                embedding_dim=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_tool_row(engine: Engine, *, message_id: int, session_id: int, user_id: int) -> None:
    payload = json.dumps(
        {"call_id": "call_a", "arguments": '{"query":"inn"}', "status": "ok", "content": "Memo."},
        separators=(",", ":"),
    )
    with engine.begin() as connection:
        connection.execute(
            schema.messages.insert().values(
                id=message_id,
                user_id=user_id,
                session_id=session_id,
                role="tool",
                kind=None,
                text="1 memo found",
                related_to=None,
                settled_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
                tool_name="memo_search",
                tool_payload=payload,
            )
        )


def _set_session_model(engine: Engine, server_id: int | None, name: str | None) -> None:
    with engine.begin() as connection:
        connection.execute(
            update(schema.sessions)
            .where(schema.sessions.c.id == SESSION_A)
            .values(model_server_id=server_id, model_name=name)
        )


def _set_model_enabled(engine: Engine, model_id: int, enabled: bool) -> None:
    with engine.begin() as connection:
        connection.execute(update(_models()).where(_models().c.id == model_id).values(is_enabled=enabled))


def _message_count(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(schema.messages)).scalar_one())


def _zone_user_rows_raw(engine: Engine, session_id: int) -> list[dict[str, Any]]:
    """Unsettled user rows of a session, read on a fresh connection (test side)."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(schema.messages)
            .where(schema.messages.c.session_id == session_id)
            .where(schema.messages.c.role == "user")
            .where(schema.messages.c.settled_at.is_(None))
            .order_by(schema.messages.c.id)
        ).mappings()
        return [dict(row) for row in rows]


@pytest.fixture(autouse=True)
def _quiet_factory_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the factory's logging call so these tests touch no global sinks."""
    monkeypatch.setattr("app.main.configure_logging", lambda settings: None)


@pytest.fixture
def engine(db_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Engine:
    """Two roleplayers, each with a character and a session (captured model: `MODEL_ONE` on
    server one, enabled; a disabled model on the same server; a second enabled server; a
    server whose key ref names an unset variable). Every zone starts empty."""
    monkeypatch.delenv(MISSING_VARIABLE, raising=False)
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username=USER_A_NAME, password=USER_A_PASSWORD)
    _insert_user(db_engine, user_id=USER_B, username=USER_B_NAME, password=USER_B_PASSWORD)
    _insert_character(db_engine, character_id=CHAR_A, user_id=USER_A, name="Aria")
    _insert_character(db_engine, character_id=CHAR_B, user_id=USER_B, name="Bram")
    _insert_server(db_engine, server_id=SERVER_ONE, base_url=BASE_ONE)
    _insert_server(db_engine, server_id=SERVER_TWO, base_url=BASE_TWO)
    _insert_server(db_engine, server_id=SERVER_SECRET, base_url=BASE_SECRET, api_key_ref=MISSING_POINTER)
    _insert_model(db_engine, model_id=MODEL_ROW_ONE, server_id=SERVER_ONE, name=MODEL_ONE, enabled=True)
    _insert_model(db_engine, model_id=MODEL_ROW_OFF, server_id=SERVER_ONE, name=MODEL_OFF, enabled=False)
    _insert_model(db_engine, model_id=MODEL_ROW_TWO, server_id=SERVER_TWO, name=MODEL_TWO, enabled=True)
    _insert_model(
        db_engine, model_id=MODEL_ROW_SECRET, server_id=SERVER_SECRET, name=MODEL_SECRET, enabled=True
    )
    _insert_session(
        db_engine,
        session_id=SESSION_A,
        user_id=USER_A,
        character_id=CHAR_A,
        model_server_id=SERVER_ONE,
        model_name=MODEL_ONE,
    )
    _insert_session(
        db_engine,
        session_id=SESSION_B,
        user_id=USER_B,
        character_id=CHAR_B,
        model_server_id=SERVER_ONE,
        model_name=MODEL_ONE,
    )
    return db_engine


# --- the fake chat client and factory ----------------------------------------------------

#: One round: deltas in order, optionally ending in an exception to raise.
Round = Sequence[ChatDelta | BaseException]


class ChatCall:
    """What one `chat_stream` call received."""

    def __init__(self, model: str, messages: list[ChatMessage], tools: list[Mapping[str, object]]) -> None:
        self.model = model
        self.messages = messages
        self.tools = tools


class FakeChatClient:
    """Replays one scripted round per `chat_stream` call; records every call.

    `on_enter`, when given, runs the first time a `chat_stream` iterator is entered.
    """

    def __init__(self, rounds: Sequence[Round], on_enter: Callable[[], None] | None = None) -> None:
        self.rounds = list(rounds)
        self.calls: list[ChatCall] = []
        self.on_enter = on_enter
        self.entered = 0

    def chat_stream(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        tools: Sequence[Mapping[str, object]],
    ) -> AsyncIterator[ChatDelta]:
        index = len(self.calls)
        self.calls.append(ChatCall(model, list(messages), [dict(tool) for tool in tools]))
        return self._stream(index)

    async def _stream(self, index: int) -> AsyncIterator[ChatDelta]:
        self.entered += 1
        if self.entered == 1 and self.on_enter is not None:
            self.on_enter()
        if index >= len(self.rounds):
            raise AssertionError(f"chat_stream called {index + 1} times; only {len(self.rounds)} scripted")
        for item in self.rounds[index]:
            if isinstance(item, BaseException):
                raise item
            await asyncio.sleep(0)
            yield item


class FakeFactory:
    """A `ChatClientFactory` returning one fake client and recording its arguments."""

    def __init__(self, client: FakeChatClient) -> None:
        self.client = client
        self.calls: list[tuple[str, str | None, float]] = []

    def __call__(self, base_url: str, api_key: str | None, timeout_seconds: float) -> Any:
        self.calls.append((base_url, api_key, timeout_seconds))
        return self.client


def _content(text: str) -> ChatDelta:
    return ChatDelta(content=text)


def _unreachable() -> LlmUnreachableError:
    return LlmUnreachableError("The provider is unreachable.")


# --- the application ---------------------------------------------------------------------


@pytest.fixture
def application(db_settings: Settings, engine: Engine) -> Iterator[FastAPI]:
    """The factory's application pinned to the seeded per-test database; the tool registry is
    overridden with an empty one (DoD-10 removes that override)."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: db_settings
    app.dependency_overrides[get_tool_registry] = lambda: {}
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


def _use_factory(app: FastAPI, factory: FakeFactory) -> None:
    app.dependency_overrides[get_chat_client_factory] = lambda: factory


def _parse_set_cookie(header: str) -> tuple[str, str]:
    first = header.split(";")[0]
    name, _, value = first.partition("=")
    return name.strip(), value.strip().strip('"')


def _login(app: FastAPI, settings: Settings, username: str, password: str) -> TestClient:
    response = _bounded(
        lambda: TestClient(app).post(LOGIN_PATH, json={"username": username, "password": password})
    )
    assert response.status_code == 200, response.text
    tokens = [
        value
        for name, value in (_parse_set_cookie(h) for h in response.headers.get_list("set-cookie"))
        if name == settings.session_cookie_name
    ]
    assert len(tokens) == 1
    client = TestClient(app)
    client.cookies.set(settings.session_cookie_name, tokens[0])
    return client


def _player_a(app: FastAPI, settings: Settings) -> TestClient:
    return _login(app, settings, USER_A_NAME, USER_A_PASSWORD)


def _player_b(app: FastAPI, settings: Settings) -> TestClient:
    return _login(app, settings, USER_B_NAME, USER_B_PASSWORD)


def _compose_path(session_id: Any) -> str:
    return COMPOSE_TEMPLATE.format(session_id=session_id)


def _compose(client: TestClient, session_id: Any, body: Mapping[str, Any]) -> httpx.Response:
    return _bounded(lambda: client.post(_compose_path(session_id), json=dict(body)))


def _frames(response: httpx.Response) -> list[dict[str, Any]]:
    """Every SSE frame of a collected body, JSON-parsed (test side only)."""
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    frames: list[dict[str, Any]] = []
    for chunk in response.text.split("\n\n"):
        if not chunk.strip():
            continue
        data_lines = [line for line in chunk.split("\n") if line.startswith("data:")]
        assert len(data_lines) == 1, chunk
        payload = data_lines[0][len("data:") :]
        if payload.startswith(" "):
            payload = payload[1:]
        parsed = json.loads(payload)
        assert isinstance(parsed, dict)
        frames.append(parsed)
    return frames


def _events(frames: Sequence[Mapping[str, Any]]) -> list[str]:
    return [frame["event"] for frame in frames]


def _zone(client: TestClient, session_id: Any) -> list[dict[str, Any]]:
    response = _bounded(lambda: client.get(f"{SESSIONS_PATH}/{session_id}/zone"))
    assert response.status_code == 200, response.text
    rows = response.json()["messages"]
    assert isinstance(rows, list)
    return rows


def _entries(client: TestClient, session_id: Any) -> list[dict[str, Any]]:
    response = _bounded(lambda: client.get(f"{SESSIONS_PATH}/{session_id}/entries"))
    assert response.status_code == 200, response.text
    rows = response.json()["entries"]
    assert isinstance(rows, list)
    return rows


def _is_decimal_string(value: Any) -> bool:
    return isinstance(value, str) and value.isdigit()


def _assert_envelope(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    return body


def _fail_once(client: TestClient) -> str:
    """DoD-3's failure: compose with text, the fake raises before yielding; returns the user row id."""
    frames = _frames(_compose(client, SESSION_A, {"text": COMPOSE_TEXT}))
    assert _events(frames) == ["accepted", "error"]
    assert frames[1]["code"] == LLM_UNREACHABLE
    accepted_id = frames[0]["message_id"]
    assert isinstance(accepted_id, str)
    return accepted_id


# =========================================================================================
# DoD-1: compose with text → accepted, token, done; the zone holds both rows
# =========================================================================================


def test_compose_with_text_streams_accepted_token_done__S021_006_DoD1(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-1 / UC-034 / D1 — 200, `text/event-stream`, `X-Accel-Buffering: no`; frames
    `accepted` (decimal-string id), token `Hi`, `done` (a different decimal-string id)."""
    factory = FakeFactory(FakeChatClient([[_content("Hi")]]))
    _use_factory(application, factory)
    client = _player_a(application, db_settings)

    response = _compose(client, SESSION_A, {"text": COMPOSE_TEXT})

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    frames = _frames(response)
    assert _events(frames) == ["accepted", "token", "done"]
    accepted, token, done = frames
    assert _is_decimal_string(accepted["message_id"])
    assert token["text"] == "Hi"
    assert _is_decimal_string(done["message_id"])
    assert done["message_id"] != accepted["message_id"]


def test_after_compose_the_zone_lists_the_user_row_then_the_assistant_row__S021_006_DoD1(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-1 / UC-032 / D1 — `GET …/zone`: the user row (the text, the accepted id) then the
    assistant row (`Hi`, the done id)."""
    factory = FakeFactory(FakeChatClient([[_content("Hi")]]))
    _use_factory(application, factory)
    client = _player_a(application, db_settings)

    frames = _frames(_compose(client, SESSION_A, {"text": COMPOSE_TEXT}))

    zone = _zone(client, SESSION_A)
    assert [(row["role"], row["text"]) for row in zone] == [("user", COMPOSE_TEXT), ("assistant", "Hi")]
    assert zone[0]["id"] == frames[0]["message_id"]
    assert zone[1]["id"] == frames[-1]["message_id"]


# =========================================================================================
# DoD-2: the text is committed before any model call
# =========================================================================================


def test_the_user_row_is_committed_before_the_model_is_called__S021_006_DoD2(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-2 / R10 / D1 — when `chat_stream` is first entered, a fresh connection already sees
    the user row (with the composed text) in the session's zone."""
    seen: list[list[str]] = []

    def probe() -> None:
        seen.append([row["text"] for row in _zone_user_rows_raw(engine, SESSION_A)])

    factory = FakeFactory(FakeChatClient([[_content("Hi")]], on_enter=probe))
    _use_factory(application, factory)
    client = _player_a(application, db_settings)

    frames = _frames(_compose(client, SESSION_A, {"text": COMPOSE_TEXT}))

    assert _events(frames)[-1] == "done"
    assert seen == [[COMPOSE_TEXT]]


# =========================================================================================
# DoD-3: provider failure before the first token
# =========================================================================================


def test_a_failure_before_any_token_gives_accepted_then_error__S021_006_DoD3(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-3 / US-044.AC-1 / US-044.AC-2 — `accepted`, then `error` `llm_unreachable` with a
    message; no `done`; the zone holds the user row only; entries unchanged."""
    factory = FakeFactory(FakeChatClient([[_unreachable()]]))
    _use_factory(application, factory)
    client = _player_a(application, db_settings)
    entries_before = _entries(client, SESSION_A)

    frames = _frames(_compose(client, SESSION_A, {"text": COMPOSE_TEXT}))

    assert _events(frames) == ["accepted", "error"]
    error = frames[1]
    assert error["code"] == LLM_UNREACHABLE
    assert isinstance(error["message"], str)
    assert error["message"].strip() != ""
    assert "done" not in _events(frames)
    zone = _zone(client, SESSION_A)
    assert [(row["role"], row["text"]) for row in zone] == [("user", COMPOSE_TEXT)]
    assert zone[0]["id"] == frames[0]["message_id"]
    assert _entries(client, SESSION_A) == entries_before


# =========================================================================================
# DoD-4: provider failure after a token keeps the partial
# =========================================================================================


def test_a_failure_after_a_token_keeps_the_partial_as_an_assistant_row__S021_006_DoD4(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-4 / US-044.AC-1 / US-132.AC-1 / 019 D4 — frames `accepted`, token `Par`, `error`;
    the zone holds the user row then an assistant row `Par`."""
    factory = FakeFactory(FakeChatClient([[_content("Par"), _unreachable()]]))
    _use_factory(application, factory)
    client = _player_a(application, db_settings)

    frames = _frames(_compose(client, SESSION_A, {"text": COMPOSE_TEXT}))

    assert _events(frames) == ["accepted", "token", "error"]
    assert frames[1]["text"] == "Par"
    assert frames[2]["code"] == LLM_UNREACHABLE
    zone = _zone(client, SESSION_A)
    assert [(row["role"], row["text"]) for row in zone] == [("user", COMPOSE_TEXT), ("assistant", "Par")]


# =========================================================================================
# DoD-5: use-time model failures are error frames after accepted
# =========================================================================================


def _captured_model_disabled(engine: Engine) -> None:
    _set_session_model(engine, SERVER_ONE, MODEL_OFF)


def _no_model_on_the_instance(engine: Engine) -> None:
    for model_id in (MODEL_ROW_ONE, MODEL_ROW_TWO, MODEL_ROW_SECRET):
        _set_model_enabled(engine, model_id, False)


def _no_captured_model(engine: Engine) -> None:
    _set_session_model(engine, None, None)


@pytest.mark.parametrize(
    ("arrange", "code"),
    [
        pytest.param(_captured_model_disabled, MODEL_NOT_ENABLED, id="captured-disabled"),
        pytest.param(_no_model_on_the_instance, NO_MODEL_ENABLED, id="none-enabled"),
        pytest.param(_no_captured_model, MODEL_NOT_CHOSEN, id="none-captured"),
    ],
)
def test_a_failed_model_check_is_an_error_frame_after_accepted__S021_006_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine, arrange: Any, code: str
) -> None:
    """DoD-5 / US-044.AC-2 / US-107 / R4 / D3 — `accepted` then `error` with the code; the user
    row is in the zone; the factory was never called."""
    arrange(engine)
    client_fake = FakeChatClient([[_content("never")]])
    factory = FakeFactory(client_fake)
    _use_factory(application, factory)
    client = _player_a(application, db_settings)

    frames = _frames(_compose(client, SESSION_A, {"text": COMPOSE_TEXT}))

    assert _events(frames) == ["accepted", "error"]
    assert frames[1]["code"] == code
    zone = _zone(client, SESSION_A)
    assert [(row["role"], row["text"]) for row in zone] == [("user", COMPOSE_TEXT)]
    assert zone[0]["id"] == frames[0]["message_id"]
    assert factory.calls == []
    assert client_fake.calls == []


def test_a_disabled_captured_model_error_carries_session_level_and_a_string_server_id__S021_006_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-5 / D3 — the `model_not_enabled` frame's `detail.level` is `"session"` and its
    `detail.server_id` is a string."""
    _captured_model_disabled(engine)
    factory = FakeFactory(FakeChatClient([[_content("never")]]))
    _use_factory(application, factory)
    client = _player_a(application, db_settings)

    frames = _frames(_compose(client, SESSION_A, {"text": COMPOSE_TEXT}))

    error = frames[-1]
    assert error["code"] == MODEL_NOT_ENABLED
    assert error["detail"]["level"] == "session"
    assert isinstance(error["detail"]["server_id"], str)


# =========================================================================================
# DoD-6: textless compose is the retry
# =========================================================================================


@pytest.mark.parametrize("body", [{}, {"text": None}], ids=["absent", "null"])
def test_a_textless_compose_retries_without_accepted_or_a_duplicate_row__S021_006_DoD6(
    application: FastAPI, db_settings: Settings, engine: Engine, body: dict[str, Any]
) -> None:
    """DoD-6 / US-044.AC-3 / D2 — after DoD-3's failure, a textless compose streams tokens and
    `done` with no `accepted`; the zone holds one user row then the assistant row; the fake
    received the same messages as in the failed attempt."""
    client_fake = FakeChatClient([[_unreachable()], [_content("Second "), _content("try.")]])
    factory = FakeFactory(client_fake)
    _use_factory(application, factory)
    client = _player_a(application, db_settings)
    user_row_id = _fail_once(client)

    frames = _frames(_compose(client, SESSION_A, body))

    assert "accepted" not in _events(frames)
    assert _events(frames) == ["token", "token", "done"]
    assert [frame["text"] for frame in frames[:2]] == ["Second ", "try."]
    assert _is_decimal_string(frames[-1]["message_id"])
    zone = _zone(client, SESSION_A)
    assert [(row["role"], row["text"]) for row in zone] == [
        ("user", COMPOSE_TEXT),
        ("assistant", "Second try."),
    ]
    assert zone[0]["id"] == user_row_id
    assert zone[1]["id"] == frames[-1]["message_id"]
    assert len(client_fake.calls) == 2
    assert client_fake.calls[1].messages == client_fake.calls[0].messages


# =========================================================================================
# DoD-7: the model is read at use time
# =========================================================================================


def test_a_retry_uses_the_model_set_after_the_failure__S021_006_DoD7(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-7 / R4 / D2 — the session's model is raw-updated to the second server's model
    between the failure and the retry; the retry's factory call gets the second base URL and
    its client call the new model name."""
    client_fake = FakeChatClient([[_unreachable()], [_content("Hi")]])
    factory = FakeFactory(client_fake)
    _use_factory(application, factory)
    client = _player_a(application, db_settings)
    _fail_once(client)
    assert factory.calls[0][0] == BASE_ONE
    assert client_fake.calls[0].model == MODEL_ONE

    _set_session_model(engine, SERVER_TWO, MODEL_TWO)
    frames = _frames(_compose(client, SESSION_A, {}))

    assert _events(frames)[-1] == "done"
    assert len(factory.calls) == 2
    assert factory.calls[1][0] == BASE_TWO
    assert len(client_fake.calls) == 2
    assert client_fake.calls[1].model == MODEL_TWO


# =========================================================================================
# DoD-8: textless compose with nothing to retry → 409 zone_empty
# =========================================================================================


@pytest.mark.parametrize("seed_tool_row", [False, True], ids=["empty-zone", "tool-row-only"])
def test_a_textless_compose_over_an_empty_zone_answers_409_zone_empty__S021_006_DoD8(
    application: FastAPI, db_settings: Settings, engine: Engine, seed_tool_row: bool
) -> None:
    """DoD-8 / D2 / D8 — an empty zone, or one holding only a tool row → 409 JSON `zone_empty`
    (not a stream); nothing written; the factory never called."""
    if seed_tool_row:
        _insert_tool_row(engine, message_id=4_661, session_id=SESSION_A, user_id=USER_A)
    factory = FakeFactory(FakeChatClient([[_content("never")]]))
    _use_factory(application, factory)
    client = _player_a(application, db_settings)
    zone_before = _zone(client, SESSION_A)
    entries_before = _entries(client, SESSION_A)
    count_before = _message_count(engine)

    response = _compose(client, SESSION_A, {})

    _assert_envelope(response, 409, ZONE_EMPTY)
    assert _message_count(engine) == count_before
    assert _zone(client, SESSION_A) == zone_before
    assert _entries(client, SESSION_A) == entries_before
    assert factory.calls == []


# =========================================================================================
# DoD-9: blank text, foreign / unknown session, no cookie
# =========================================================================================


def test_a_blank_text_answers_422_and_writes_nothing__S021_006_DoD9(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-9 / D2 — `{"text":"   "}` → 422; no row; the factory never called."""
    factory = FakeFactory(FakeChatClient([[_content("never")]]))
    _use_factory(application, factory)
    client = _player_a(application, db_settings)
    count_before = _message_count(engine)

    response = _compose(client, SESSION_A, {"text": "   "})

    assert response.status_code == 422, response.text
    assert _message_count(engine) == count_before
    assert factory.calls == []


@pytest.mark.parametrize("body", [{"text": COMPOSE_TEXT}, {}], ids=["with-text", "textless"])
@pytest.mark.parametrize("target", ["foreign", "unknown"])
def test_another_users_or_an_unknown_session_answers_404_json__S021_006_DoD9(
    application: FastAPI,
    db_settings: Settings,
    engine: Engine,
    body: dict[str, Any],
    target: str,
) -> None:
    """DoD-9 / R5 / D1 — as A, B's session and an unknown id → 404 `session_not_found` as JSON;
    no row written; the factory never called."""
    factory = FakeFactory(FakeChatClient([[_content("never")]]))
    _use_factory(application, factory)
    client = _player_a(application, db_settings)
    session_id: Any = SESSION_B if target == "foreign" else UNKNOWN_SESSION_ID
    count_before = _message_count(engine)

    response = _compose(client, session_id, body)

    _assert_envelope(response, 404, SESSION_NOT_FOUND)
    assert _message_count(engine) == count_before
    assert factory.calls == []


def test_the_foreign_session_owner_still_sees_an_empty_zone__S021_006_DoD9(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-9 / R5 — after A's refused compose on B's session, B's zone is still empty."""
    factory = FakeFactory(FakeChatClient([[_content("never")]]))
    _use_factory(application, factory)
    intruder = _player_a(application, db_settings)
    owner = _player_b(application, db_settings)

    _assert_envelope(_compose(intruder, SESSION_B, {"text": COMPOSE_TEXT}), 404, SESSION_NOT_FOUND)

    assert _zone(owner, SESSION_B) == []
    assert factory.calls == []


def test_compose_without_a_cookie_answers_401__S021_006_DoD9(
    application: FastAPI, engine: Engine
) -> None:
    """DoD-9 — no cookie → 401 `not_authenticated`; no row; the factory never called."""
    factory = FakeFactory(FakeChatClient([[_content("never")]]))
    _use_factory(application, factory)
    count_before = _message_count(engine)

    response = _compose(TestClient(application), SESSION_A, {"text": COMPOSE_TEXT})

    _assert_envelope(response, 401, NOT_AUTHENTICATED)
    assert _message_count(engine) == count_before
    assert factory.calls == []


# =========================================================================================
# DoD-10: the production registry dependency offers what is registered
# Amended by 026 step 002 (DoD-15), then by 027 step 003 (S027_003_DoD15): `memo_search` and
# `session_search` are both registered, so the real dependency now sends both declarations —
# hence the module-level import of `MEMO_SEARCH` and `SESSION_SEARCH` from
# `app.services.tools.definitions`. The `__S021_006_DoD10` tag is kept.
# =========================================================================================


# Amended by 026 step 002, then by 027 step 003 (S027_003_DoD15): the production registry now
# holds both `memo_search` and `session_search`.
def test_the_production_registry_dependency_sends_both_registered_tools__S021_006_DoD10(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-10 / D5 / U3 — the registry dependency is NOT overridden; all switches on; the fake
    client receives exactly the `memo_search` and `session_search` declarations, in order."""
    application.dependency_overrides.pop(get_tool_registry, None)
    client_fake = FakeChatClient([[_content("Hi")]])
    _use_factory(application, FakeFactory(client_fake))
    client = _player_a(application, db_settings)

    frames = _frames(_compose(client, SESSION_A, {"text": COMPOSE_TEXT}))

    assert _events(frames)[-1] == "done"
    assert len(client_fake.calls) == 1
    assert client_fake.calls[0].tools == [dict(MEMO_SEARCH), dict(SESSION_SEARCH)]


# Added by 026 step 002, then amended by 027 step 003 (S027_003_DoD15): the seeded session has
# all three switches on, so switching only `tool_memo_search` off would now still offer
# `session_search`. Both registered switches go off to keep the clause's point.
def test_the_production_registry_with_both_switches_off_sends_no_tools__S021_006_DoD10(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-10 / D5 / U3 — the registry dependency is NOT overridden, but the session's
    memo-search and session-search switches are both off, so the fake client receives an empty
    tools list."""
    application.dependency_overrides.pop(get_tool_registry, None)
    with engine.begin() as connection:
        connection.execute(
            update(schema.sessions)
            .where(schema.sessions.c.id == SESSION_A)
            .values(tool_memo_search=False, tool_session_search=False)
        )
    client_fake = FakeChatClient([[_content("Hi")]])
    _use_factory(application, FakeFactory(client_fake))
    client = _player_a(application, db_settings)

    frames = _frames(_compose(client, SESSION_A, {"text": COMPOSE_TEXT}))

    assert _events(frames)[-1] == "done"
    assert len(client_fake.calls) == 1
    assert client_fake.calls[0].tools == []


# Added by 027 step 003 (S027_003_DoD15): the third case of the matrix — only the session-search
# switch off, so the memo-search declaration alone is offered.
def test_the_production_registry_with_the_session_switch_off_sends_memo_search__S021_006_DoD10(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-10 / D5 / U3 — the registry dependency is NOT overridden and only the session's
    session-search switch is off, so the fake client receives the `memo_search` declaration."""
    application.dependency_overrides.pop(get_tool_registry, None)
    with engine.begin() as connection:
        connection.execute(
            update(schema.sessions)
            .where(schema.sessions.c.id == SESSION_A)
            .values(tool_session_search=False)
        )
    client_fake = FakeChatClient([[_content("Hi")]])
    _use_factory(application, FakeFactory(client_fake))
    client = _player_a(application, db_settings)

    frames = _frames(_compose(client, SESSION_A, {"text": COMPOSE_TEXT}))

    assert _events(frames)[-1] == "done"
    assert len(client_fake.calls) == 1
    assert client_fake.calls[0].tools == [dict(MEMO_SEARCH)]


# =========================================================================================
# DoD-11: a missing secret is an error frame; the user row is kept
# =========================================================================================


def test_an_unset_key_variable_gives_secret_ref_missing_after_accepted__S021_006_DoD11(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-11 / D14 / R10 — the captured model's server names an unset variable → `accepted`
    then `error` `secret_ref_missing`; the user row is kept."""
    _set_session_model(engine, SERVER_SECRET, MODEL_SECRET)
    factory = FakeFactory(FakeChatClient([[_content("never")]]))
    _use_factory(application, factory)
    client = _player_a(application, db_settings)

    frames = _frames(_compose(client, SESSION_A, {"text": COMPOSE_TEXT}))

    assert _events(frames) == ["accepted", "error"]
    assert frames[1]["code"] == SECRET_REF_MISSING
    zone = _zone(client, SESSION_A)
    assert [(row["role"], row["text"]) for row in zone] == [("user", COMPOSE_TEXT)]
    assert zone[0]["id"] == frames[0]["message_id"]


# =========================================================================================
# DoD-12: the compose route is present
# =========================================================================================


def test_the_compose_route_is_registered_as_post__S021_006_DoD12(application: FastAPI) -> None:
    """DoD-12 / D1 — the application exposes `POST /api/sessions/{session_id}/zone/compose`
    (the existing stream-router tests, which assert nothing about its absence, run unchanged)."""
    paths = application.openapi()["paths"]

    assert COMPOSE_TEMPLATE in paths
    assert "post" in paths[COMPOSE_TEMPLATE]
