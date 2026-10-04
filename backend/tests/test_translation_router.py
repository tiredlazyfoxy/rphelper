"""Tests for feature 023, step 003 — `POST /api/messages/{message_id}/translation`.

Every expected value comes from `docs/plans/023.partner-translation/003.translation-route.md`
(Goal, Interface intent, DoD-1..DoD-6), from `003.context.md` ("Built state at the touch sites",
"The probe", "Test shape") and from the feature `context.md` (the **Wire contract** — the success
shape and every failure code/status — plus **D1**, **D4**, **D5**, **D6**, **D12**). Nothing is
read from the implementation: the route, its status codes, its body keys and its failure codes are
the plan's.

Bindings come from `status.md` `## Skeleton` -> **Step 003 — frozen interface**:

- the route `POST /api/messages/{message_id}/translation`, `status_code=200`, handler
  `translate_partner_message`, an `async def`;
- **`get_translation_chat_client_factory`** — the one dependency these tests override, imported
  from `app.routers.translation`; its un-overridden body returns the real `LlmClient` (DoD-5);
- the handler takes its generator through `Depends(get_id_generator)` and its settings through
  `Depends(get_settings)`, so an override of `get_settings` alone pins the database **and** the
  timeout;
- step 001's `TranslationResponse` keys and step 001's `TranslationFailedError`
  (`translation_failed`, 502, `detail={"message_id": "<decimal>"}`).

Shape (feature `context.md` "Test conventions", `003.context.md` "Test shape"): the application is
always the real factory's (`create_app()`), pinned to a per-test SQLite **file** through
`dependency_overrides[get_settings]`; the chat-client factory is a file-local fake installed
through `dependency_overrides[get_translation_chat_client_factory]`; callers log in through the
real login route with a file-local `_as(...)`, modelled on `tests/test_stream_router.py`.
`conftest.py` is untouched — every fixture below is file-local.

`003.context.md` "The probe": under `TestClient` `request.is_disconnected()` reports `False`, so
DoD-1's cache write happens. The disconnected path is covered at the **service** level
(step 002 DoD-12), not here.

Covers step 003 DoD-1 .. DoD-6. DoD-7 is `[manual/live]` and carries no test.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import Engine, Table, select, update

from app.config import Settings, get_settings
from app.db import schema
from app.errors import LlmUnreachableError
from app.main import create_app
from app.roles import Role
from app.routers.translation import get_translation_chat_client_factory
from app.services.llm.chat import ChatMessage
from app.services.llm.client import ChatDelta
from app.services.passwords import hash_password

# --- the wire surface (feature context.md, Wire contract; step file DoD-6) ------------------

MESSAGES_PATH = "/api/messages"
LOGIN_PATH = "/api/auth/login"

#: The route as an OpenAPI path template (DoD-6).
TRANSLATION_PATH_TEMPLATE = "/api/messages/{message_id}/translation"

#: The success body's keys (Wire contract: `Translation`).
TRANSLATION_KEYS = {"message_id", "target_language", "text", "cached"}

NOT_AUTHENTICATED = "not_authenticated"
MESSAGE_NOT_FOUND = "message_not_found"
NO_MODEL_ENABLED = "no_model_enabled"
MODEL_NOT_ENABLED = "model_not_enabled"
TRANSLATION_FAILED = "translation_failed"

# --- seeded state ---------------------------------------------------------------------------

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
SETTLED_AT = "2026-01-01T00:00:01.000000+00:00"

USER_A_ID = 9_230_001
USER_A_NAME = "aster"
USER_A_PASSWORD = "a quiet river at dusk"

USER_B_ID = 9_230_002
USER_B_NAME = "briar"
USER_B_PASSWORD = "salt and lantern light"

CHAR_A = 1_001
CHAR_B = 2_001
SESSION_A = 5_001
SESSION_B = 6_001

#: Raw-seeded `messages` ids, as decimal strings on the wire.
PARTNER_A = 7_250_000_000_000_000_101
TURN_A = 7_250_000_000_000_000_102
ZONE_A = 7_250_000_000_000_000_103
PARTNER_B = 7_250_000_000_000_000_201
UNKNOWN_MESSAGE = 7_250_000_000_000_000_999

#: Registry rows (017's conventions). SERVER_A carries the session's captured model plus a second
#: enabled one, so "the captured model is disabled" and "nothing is enabled at all" differ (DoD-4).
SERVER_A = 8_501
MODEL_ROW_ON = 8_601
MODEL_ROW_OTHER = 8_602
MODEL_NAME = "story-model-7b"
OTHER_MODEL_NAME = "spare-model-1b"
BASE_URL = "http://chat-translate.test:8080"

#: DoD-5: an address nothing listens on, with a tiny timeout (`003.context.md` "Test shape").
UNROUTABLE_BASE_URL = "http://127.0.0.1:9"
TINY_TIMEOUT_SECONDS = 0.5

#: USER_A's preferred language, which the Wire contract echoes as `target_language` (DoD-1).
TARGET_LANGUAGE = "Russian"

PARTNER_A_TEXT = "She waves.\n\n*smiles*"
TURN_A_TEXT = "I nod and step closer."
ZONE_A_TEXT = "A zone draft."
PARTNER_B_TEXT = "Bob's settled partner entry."

#: DoD-1's translated text, verbatim from the DoD.
TRANSLATED_TEXT = "Привет"

#: DoD-2's second attempt, so "`cached: false` again" cannot pass on DoD-1's text by accident.
RETRY_TEXT = "Привет снова"

#: A non-numeric path id (DoD-3).
NOT_A_NUMBER = "not-a-number"


# --- seeding --------------------------------------------------------------------------------


def _servers() -> Table:
    return schema.metadata.tables["llm_servers"]


def _models() -> Table:
    return schema.metadata.tables["models"]


def _translations() -> Table:
    return schema.metadata.tables["translations"]


def _insert_user(engine: Engine, *, user_id: int, username: str, password: str, language: str | None) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.users.insert().values(
                id=user_id,
                username=username,
                password_hash=hash_password(password),
                role=Role.ROLEPLAYER,
                is_enabled=True,
                rp_language=None,
                preferred_language=language,
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
                model_server_id=SERVER_A,
                model_name=MODEL_NAME,
                preferred_language=None,
            )
        )


def _insert_message(
    engine: Engine,
    *,
    message_id: int,
    user_id: int,
    session_id: int,
    body: str,
    kind: str | None = "partner",
    settled_at: str | None = SETTLED_AT,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.messages.insert().values(
                id=message_id,
                user_id=user_id,
                session_id=session_id,
                role="user",
                kind=kind,
                text=body,
                related_to=None,
                settled_at=settled_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_server(engine: Engine, *, server_id: int, base_url: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            _servers()
            .insert()
            .values(
                id=server_id,
                name=f"server {server_id}",
                kind="llamaswap",
                base_url=base_url,
                api_key_ref=None,
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


def _set_model_enabled(engine: Engine, model_id: int, enabled: bool) -> None:
    with engine.begin() as connection:
        connection.execute(update(_models()).where(_models().c.id == model_id).values(is_enabled=enabled))


def _disable_every_model(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(update(_models()).values(is_enabled=False))


def _set_base_url(engine: Engine, server_id: int, base_url: str) -> None:
    with engine.begin() as connection:
        connection.execute(update(_servers()).where(_servers().c.id == server_id).values(base_url=base_url))


def _translation_rows(engine: Engine) -> list[dict[str, Any]]:
    table = _translations()
    with engine.connect() as connection:
        rows = connection.execute(select(table).order_by(table.c.id)).mappings().all()
    return [dict(row) for row in rows]


# --- fixtures -------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _quiet_factory_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the factory's logging call so these tests touch no global sinks."""
    monkeypatch.setattr("app.main.configure_logging", lambda settings: None)


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database: the schema, two owners (isolation) each with a character and a session,
    SERVER_A with the captured model plus one spare, and USER_A's settled stream — a partner row, a
    turn and a zone row — plus one settled partner row of USER_B.

    USER_A's preferred language is "Russian"; SESSION_A sets none (DoD-1, R1).
    """
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)

    _insert_user(
        db_engine,
        user_id=USER_A_ID,
        username=USER_A_NAME,
        password=USER_A_PASSWORD,
        language=TARGET_LANGUAGE,
    )
    _insert_user(
        db_engine,
        user_id=USER_B_ID,
        username=USER_B_NAME,
        password=USER_B_PASSWORD,
        language="Dutch",
    )
    _insert_character(db_engine, character_id=CHAR_A, user_id=USER_A_ID, name="Aria")
    _insert_character(db_engine, character_id=CHAR_B, user_id=USER_B_ID, name="Bram")

    _insert_server(db_engine, server_id=SERVER_A, base_url=BASE_URL)
    _insert_model(db_engine, model_id=MODEL_ROW_ON, server_id=SERVER_A, name=MODEL_NAME, enabled=True)
    _insert_model(db_engine, model_id=MODEL_ROW_OTHER, server_id=SERVER_A, name=OTHER_MODEL_NAME, enabled=True)

    _insert_session(db_engine, session_id=SESSION_A, user_id=USER_A_ID, character_id=CHAR_A)
    _insert_session(db_engine, session_id=SESSION_B, user_id=USER_B_ID, character_id=CHAR_B)

    _insert_message(
        db_engine, message_id=PARTNER_A, user_id=USER_A_ID, session_id=SESSION_A, body=PARTNER_A_TEXT
    )
    _insert_message(
        db_engine,
        message_id=TURN_A,
        user_id=USER_A_ID,
        session_id=SESSION_A,
        body=TURN_A_TEXT,
        kind="turn",
    )
    _insert_message(
        db_engine,
        message_id=ZONE_A,
        user_id=USER_A_ID,
        session_id=SESSION_A,
        body=ZONE_A_TEXT,
        kind=None,
        settled_at=None,
    )
    _insert_message(
        db_engine, message_id=PARTNER_B, user_id=USER_B_ID, session_id=SESSION_B, body=PARTNER_B_TEXT
    )
    return db_engine


@pytest.fixture
def application(db_settings: Settings, engine: Engine) -> Iterator[FastAPI]:
    """The real factory's application, pinned to the seeded per-test database.

    Only `get_settings` is overridden here, so a test that asks for no `factory` fixture runs
    against the route's own, production chat-client factory (DoD-5).
    """
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: db_settings
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


# --- login helpers (modelled on tests/test_stream_router.py) --------------------------------


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
    fresh = TestClient(application)
    fresh.cookies.set(settings.session_cookie_name, _login_token(application, settings, username, password))
    return fresh


def _anonymous(application: FastAPI) -> TestClient:
    return TestClient(application)


def _owner(application: FastAPI, settings: Settings) -> TestClient:
    return _as(application, settings, USER_A_NAME, USER_A_PASSWORD)


# --- the provider fake, its factory, and request helpers ------------------------------------

#: One scripted stream: deltas in order, optionally ending in an exception to raise.
Script = Sequence[ChatDelta | BaseException]


class ChatCall:
    """What one `chat_stream` call received."""

    def __init__(self, model: str, messages: list[ChatMessage], tools: list[Mapping[str, object]]) -> None:
        self.model = model
        self.messages = messages
        self.tools = tools


class FakeStream:
    """The object `chat_stream` returns: an async iterator with an explicit `aclose`."""

    def __init__(self, script: Script) -> None:
        self._script = list(script)
        self._inner = self._iterate()

    def __aiter__(self) -> FakeStream:
        return self

    async def __anext__(self) -> ChatDelta:
        return await self._inner.__anext__()

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def _iterate(self) -> Any:
        for item in self._script:
            if isinstance(item, BaseException):
                raise item
            yield item


class FakeChatClient:
    """Replays one scripted stream per `chat_stream` call, recording every call."""

    def __init__(self, script: Script) -> None:
        self.script = list(script)
        self.calls: list[ChatCall] = []

    def chat_stream(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        tools: Sequence[Mapping[str, object]],
    ) -> FakeStream:
        self.calls.append(ChatCall(model, list(messages), [dict(tool) for tool in tools]))
        return FakeStream(self.script)


class FakeFactory:
    """A `ChatClientFactory` standing in for the route's own dependency.

    `yields(...)` / `raises(...)` script the next client. Every client it ever handed out is kept,
    so "the model was called once in total" (DoD-1) is observable across two requests.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None, float]] = []
        self.clients: list[FakeChatClient] = []
        self._client = FakeChatClient([])

    def yields(self, text: str) -> None:
        self._client = FakeChatClient([ChatDelta(content=text)])

    def raises(self, error: BaseException) -> None:
        self._client = FakeChatClient([error])

    @property
    def chat_calls(self) -> list[ChatCall]:
        return [call for client in self.clients for call in client.calls]

    def __call__(self, base_url: str, api_key: str | None, timeout_seconds: float) -> Any:
        self.calls.append((base_url, api_key, timeout_seconds))
        self.clients.append(self._client)
        return self._client


@pytest.fixture
def factory(application: FastAPI) -> FakeFactory:
    """The fake installed over **this router's own** factory dependency (`## Skeleton`, step 003)."""
    fake = FakeFactory()
    application.dependency_overrides[get_translation_chat_client_factory] = lambda: fake
    return fake


def _translation_path(message_id: Any) -> str:
    return f"{MESSAGES_PATH}/{message_id}/translation"


def _post(client: TestClient, message_id: Any) -> httpx.Response:
    """The route takes no request body (Wire contract)."""
    return client.post(_translation_path(message_id))


def _assert_envelope(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error, dict)
    assert error["code"] == code
    return error


# --- DoD-1: the success body, and the second flick answering from the cache ------------------


def test_a_flick_answers_200_with_the_translation__S023_003_DoD1(
    application: FastAPI, db_settings: Settings, factory: FakeFactory
) -> None:
    """DoD-1 — US-045.AC-1, Wire contract: 200 with exactly the four keys, `message_id` a
    **string**, `target_language` the resolved preferred language and `cached` false."""
    factory.yields(TRANSLATED_TEXT)
    client = _owner(application, db_settings)

    response = _post(client, PARTNER_A)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "message_id": str(PARTNER_A),
        "target_language": TARGET_LANGUAGE,
        "text": TRANSLATED_TEXT,
        "cached": False,
    }
    assert set(response.json()) == TRANSLATION_KEYS


def test_a_second_flick_answers_cached_without_a_second_model_call__S023_003_DoD1(
    application: FastAPI, db_settings: Settings, factory: FakeFactory, engine: Engine
) -> None:
    """DoD-1 — US-046.AC-1: the same text comes back with `cached` true, and the fake client was
    called **once in total** — the server cache short-circuited the model."""
    factory.yields(TRANSLATED_TEXT)
    client = _owner(application, db_settings)

    first = _post(client, PARTNER_A)
    second = _post(client, PARTNER_A)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json() == {
        "message_id": str(PARTNER_A),
        "target_language": TARGET_LANGUAGE,
        "text": TRANSLATED_TEXT,
        "cached": True,
    }
    assert len(factory.chat_calls) == 1
    assert len(_translation_rows(engine)) == 1


# --- DoD-2: the 502 envelope, and that a failure memoised nothing ---------------------------


def test_an_unreachable_provider_answers_502_translation_failed__S023_003_DoD2(
    application: FastAPI, db_settings: Settings, factory: FakeFactory, engine: Engine
) -> None:
    """DoD-2 — US-048.AC-1, D5: 502 `translation_failed`, a non-empty message (the prose is not
    pinned here) and `detail` naming the message id as a decimal string. Nothing is cached."""
    factory.raises(LlmUnreachableError("the server is down"))
    client = _owner(application, db_settings)

    response = _post(client, PARTNER_A)

    error = _assert_envelope(response, 502, TRANSLATION_FAILED)
    assert set(error) == {"code", "message", "detail"}
    assert isinstance(error["message"], str)
    assert error["message"].strip() != ""
    assert error["detail"] == {"message_id": str(PARTNER_A)}
    assert _translation_rows(engine) == []


def test_a_flick_after_a_failure_reaches_the_model_again__S023_003_DoD2(
    application: FastAPI, db_settings: Settings, factory: FakeFactory
) -> None:
    """DoD-2 — US-048.AC-2: the failure memoised nothing, so the next POST translates afresh."""
    factory.raises(LlmUnreachableError("the server is down"))
    client = _owner(application, db_settings)
    assert _post(client, PARTNER_A).status_code == 502

    factory.yields(RETRY_TEXT)
    response = _post(client, PARTNER_A)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "message_id": str(PARTNER_A),
        "target_language": TARGET_LANGUAGE,
        "text": RETRY_TEXT,
        "cached": False,
    }


# --- DoD-3: the 404 cases, the 422 and the 401 ----------------------------------------------


@pytest.mark.parametrize(
    "message_id",
    [
        pytest.param(PARTNER_B, id="another-users-partner-row"),
        pytest.param(TURN_A, id="settled-turn"),
        pytest.param(ZONE_A, id="zone-row"),
        pytest.param(UNKNOWN_MESSAGE, id="unknown-id"),
    ],
)
def test_an_ineligible_row_answers_404_message_not_found__S023_003_DoD3(
    application: FastAPI, db_settings: Settings, factory: FakeFactory, message_id: int
) -> None:
    """DoD-3 — D6, R5: every ineligible row is indistinguishable from a missing one, and no
    provider client is ever built."""
    factory.yields(TRANSLATED_TEXT)
    client = _owner(application, db_settings)

    response = _post(client, message_id)

    _assert_envelope(response, 404, MESSAGE_NOT_FOUND)
    assert factory.calls == []
    assert factory.chat_calls == []


def test_a_non_numeric_path_id_answers_422__S023_003_DoD3(
    application: FastAPI, db_settings: Settings, factory: FakeFactory
) -> None:
    """DoD-3 — Wire contract: a non-numeric path id fails validation before the handler runs."""
    factory.yields(TRANSLATED_TEXT)
    client = _owner(application, db_settings)

    response = _post(client, NOT_A_NUMBER)

    assert response.status_code == 422, response.text
    assert factory.calls == []


def test_no_cookie_answers_401_not_authenticated__S023_003_DoD3(
    application: FastAPI, factory: FakeFactory
) -> None:
    """DoD-3 — D12: `require_user` sits on the router, so an anonymous POST never reaches it."""
    response = _post(_anonymous(application), PARTNER_A)

    _assert_envelope(response, 401, NOT_AUTHENTICATED)
    assert factory.calls == []


# --- DoD-4: the use-time model check refusing on a cache miss -------------------------------


def test_no_enabled_model_answers_409_no_model_enabled__S023_003_DoD4(
    application: FastAPI, db_settings: Settings, factory: FakeFactory, engine: Engine
) -> None:
    """DoD-4 — D5, Wire contract: 017's use-time check propagates unchanged, at 409."""
    factory.yields(TRANSLATED_TEXT)
    _disable_every_model(engine)
    client = _owner(application, db_settings)

    response = _post(client, PARTNER_A)

    _assert_envelope(response, 409, NO_MODEL_ENABLED)


def test_a_disabled_captured_model_answers_409_model_not_enabled__S023_003_DoD4(
    application: FastAPI, db_settings: Settings, factory: FakeFactory, engine: Engine
) -> None:
    """DoD-4 — D5: the session's captured model is off while another stays enabled, so the refusal
    is `model_not_enabled`, not `no_model_enabled`."""
    factory.yields(TRANSLATED_TEXT)
    _set_model_enabled(engine, MODEL_ROW_ON, False)
    client = _owner(application, db_settings)

    response = _post(client, PARTNER_A)

    _assert_envelope(response, 409, MODEL_NOT_ENABLED)


# --- DoD-5: the un-overridden factory dependency is the production one ----------------------


def test_the_unoverridden_factory_reaches_the_real_client__S023_003_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-5 — D12: with **only** `get_settings` overridden, the route resolves its own factory,
    which returns the real client. Pointed at an address nothing listens on, with a tiny timeout,
    the call fails and the wire shows 502 `translation_failed` (D5)."""
    custom = db_settings.model_copy(update={"llm_request_timeout_seconds": TINY_TIMEOUT_SECONDS})
    application.dependency_overrides[get_settings] = lambda: custom
    _set_base_url(engine, SERVER_A, UNROUTABLE_BASE_URL)
    client = _as(application, custom, USER_A_NAME, USER_A_PASSWORD)

    response = _post(client, PARTNER_A)

    error = _assert_envelope(response, 502, TRANSLATION_FAILED)
    assert error["detail"] == {"message_id": str(PARTNER_A)}
    assert _translation_rows(engine) == []


# --- DoD-6: the route surface ---------------------------------------------------------------


def _ordered_api_routes(routes: Any, found: list[APIRoute], seen: set[int]) -> None:
    """Depth-first, registration-order walk of every `APIRoute`, descending into included-router
    wrappers (entries exposing `.routes`, `.router.routes` or `.original_router.routes`), as
    `tests/test_configuration_router.py` does: under the pinned FastAPI / Starlette, `app.routes`
    does not flatten included routers."""
    if routes is None or id(routes) in seen:
        return
    seen.add(id(routes))
    for route in routes:
        if isinstance(route, APIRoute):
            if id(route) not in seen:
                seen.add(id(route))
                found.append(route)
            continue
        _ordered_api_routes(getattr(route, "routes", None), found, seen)
        _ordered_api_routes(getattr(getattr(route, "router", None), "routes", None), found, seen)
        _ordered_api_routes(getattr(getattr(route, "original_router", None), "routes", None), found, seen)


def test_the_translate_route_is_mounted_exactly_once_as_post__S023_003_DoD6(application: FastAPI) -> None:
    """DoD-6 — D12: one route, one path template, the POST method."""
    ordered: list[APIRoute] = []
    _ordered_api_routes(application.routes, ordered, set())

    matching = [route for route in ordered if route.path == TRANSLATION_PATH_TEMPLATE]

    assert len(matching) == 1
    assert {method.upper() for method in matching[0].methods} == {"POST"}
