"""Configuration-gated registration of `web_search` (feature 028, step 002).

Covers DoD-8 (the registry builder), DoD-9 (offered at the seam) and DoD-10 (offered at the
route) of `docs/plans/028.web-search-tool/002.web-search-tool-and-registration.md`. The
adapter, the formatter, the factory and the import shape are in
`tests/test_web_search_tool.py`; the DoD-14 amendment is one assertion in
`tests/test_tool_seam.py`. DoD-15 .. DoD-17 are `[manual/live]`.

Every expected value comes from the spec: the step file's Definition of done, `002.context.md`
("The router edit", "Test seeding notes") and the feature `context.md` — **D3** (offered iff
both credentials are non-blank **and** the session's `tool_web_search` resolves true; the
static registry constant is never mutated and the request registry is built per request),
D11 (the declaration is 021's and unchanged) and the literals table. 021's own rule (D5) is
that a declaration is offered iff its switch resolves true and its name is registered, in
declaration order.

Bindings come from `status.md` `## Skeleton` -> "Step 002 — frozen interface":

    def build_tool_registry(api_key: str | None, engine_id: str | None) -> ToolRegistry
    def get_tool_registry(settings: Annotated[Settings, Depends(get_settings)]) -> ToolRegistry

`build_tool_registry` is imported from `app.services.tools.seam`, not from the package
(it is deliberately not re-exported). The route's registry dependency is **not** overridden
here: these tests exercise the real one.

Mechanics (`context.md` "Test conventions", `002.context.md` "Test seeding notes"): the
engine is built file-locally with `schema.metadata.create_all` and file-local raw-insert
helpers, two users and ids above 2**60; the route tests use `create_app()` with
`dependency_overrides` for `get_settings` and the chat-client factory, a logged-in
`TestClient` and an SSE body split on `"\\n\\n"`. Credentials reach the route only through
the `Settings` the `get_settings` override returns, never through a real `.env`, and they
are obvious fakes. **No test here makes a network request**: the fake chat client yields
text and never calls a tool, so no provider ever runs. Each test name ends
`__S028_002_DoD<n>`.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, Table, update

from app.config import Settings, get_settings
from app.db import schema
from app.main import create_app
from app.roles import Role
from app.routers.stream import get_chat_client_factory
from app.services.configuration import ConfigLevel, ResolvedSetting, SessionConfiguration
from app.services.llm.chat import ChatMessage
from app.services.llm.client import ChatDelta
from app.services.passwords import hash_password
from app.services.tools.definitions import (
    MEMO_SEARCH,
    MEMO_SEARCH_NAME,
    SESSION_SEARCH,
    SESSION_SEARCH_NAME,
    WEB_SEARCH,
    WEB_SEARCH_NAME,
)
from app.services.tools.seam import PRODUCTION_TOOL_REGISTRY, build_tool_registry, offered_tools

#: The seeded instant, in the project's fixed-width UTC text form.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

#: Obvious fakes (D12). No test may reach Google.
API_KEY = "test-key"
ENGINE_ID = "test-cx"

#: The two environment variable names (D2's deliberate exception to the `RPHELPER_` prefix).
KEY_VARIABLE = "SEARCH_CSE_KEY"
ID_VARIABLE = "SEARCH_CSE_ID"

#: Literals — `context.md`'s table.
EXPECTED_TOOL_NAME = "web_search"

#: After 027 the production registry constant holds exactly these two, in this order.
REGISTERED_WITHOUT_WEB_SEARCH = ["memo_search", "session_search"]

LOGIN_PATH = "/api/auth/login"
COMPOSE_TEMPLATE = "/api/sessions/{session_id}/zone/compose"
COMPOSE_TEXT = "Write me a reply"

#: Bound for every HTTP call (the whole SSE body is collected inside it).
HTTP_TIMEOUT_SECONDS = 20.0

#: Every id below is above 2**60 = 1152921504606846976 (snowflake-sized).
USER_A = 1_803_000_000_000_000_001
USER_B = 1_803_000_000_000_000_002

USER_A_NAME = "aster"
USER_A_PASSWORD = "a quiet river at dusk"
USER_B_NAME = "briar"
USER_B_PASSWORD = "salt and lantern light"

CHARACTER_A = 1_803_000_000_000_000_101
CHARACTER_B = 1_803_000_000_000_000_102

SESSION_A = 1_803_000_000_000_000_201
SESSION_B = 1_803_000_000_000_000_202

SERVER_ID = 1_803_000_000_000_000_901
MODEL_ROW_ID = 1_803_000_000_000_000_902
MODEL_NAME = "story-model-7b"
BASE_URL = "http://chat-one.test:8080"


# =========================================================================================
# DoD-8: the registry builder (D3)
# =========================================================================================

UNCONFIGURED_COMBINATIONS: tuple[tuple[str | None, str | None], ...] = (
    (None, None),
    (None, ENGINE_ID),
    (API_KEY, None),
    ("", ""),
    ("", ENGINE_ID),
    (API_KEY, ""),
    ("   ", ENGINE_ID),
    (API_KEY, "   "),
)


@pytest.mark.parametrize(("api_key", "engine_id"), UNCONFIGURED_COMBINATIONS)
def test_an_unconfigured_builder_holds_only_the_registered_two__S028_002_DoD8(
    api_key: str | None, engine_id: str | None
) -> None:
    """DoD-8 / D3 — with either credential blank or none, `web_search` is not registered."""
    registry = build_tool_registry(api_key, engine_id)

    assert list(registry) == REGISTERED_WITHOUT_WEB_SEARCH


@pytest.mark.parametrize(("api_key", "engine_id"), UNCONFIGURED_COMBINATIONS)
def test_an_unconfigured_builder_reuses_the_constants_own_values__S028_002_DoD8(
    api_key: str | None, engine_id: str | None
) -> None:
    """DoD-8 — each value is the very object the production registry constant holds."""
    registry = build_tool_registry(api_key, engine_id)

    for name in REGISTERED_WITHOUT_WEB_SEARCH:
        assert registry[name] is PRODUCTION_TOOL_REGISTRY[name]


def test_a_configured_builder_adds_web_search_to_the_registered_two__S028_002_DoD8() -> None:
    """DoD-8 / D3 — with both credentials set, the keys are those two plus `web_search`."""
    registry = build_tool_registry(API_KEY, ENGINE_ID)

    assert set(registry) == {*REGISTERED_WITHOUT_WEB_SEARCH, EXPECTED_TOOL_NAME}
    assert len(registry) == 3
    assert registry[EXPECTED_TOOL_NAME].name == EXPECTED_TOOL_NAME


def test_a_configured_builder_still_reuses_the_constants_own_values__S028_002_DoD8() -> None:
    """DoD-8 — the two existing entries are the constant's instances, not fresh ones."""
    registry = build_tool_registry(API_KEY, ENGINE_ID)

    for name in REGISTERED_WITHOUT_WEB_SEARCH:
        assert registry[name] is PRODUCTION_TOOL_REGISTRY[name]


def test_building_a_registry_leaves_the_constant_with_its_two_keys__S028_002_DoD8() -> None:
    """DoD-8 / D3 — the builder returns a new mapping; the constant is never mutated."""
    build_tool_registry(API_KEY, ENGINE_ID)
    build_tool_registry(None, None)

    assert list(PRODUCTION_TOOL_REGISTRY) == REGISTERED_WITHOUT_WEB_SEARCH
    assert EXPECTED_TOOL_NAME not in PRODUCTION_TOOL_REGISTRY


@pytest.mark.parametrize(
    ("api_key", "engine_id"), [(API_KEY, ENGINE_ID), (None, None)], ids=["configured", "unconfigured"]
)
def test_the_built_registry_is_read_only__S028_002_DoD8(
    api_key: str | None, engine_id: str | None
) -> None:
    """DoD-8 — assigning into the returned mapping raises; it is not a plain dict to edit."""
    registry = build_tool_registry(api_key, engine_id)

    with pytest.raises(TypeError):
        registry[EXPECTED_TOOL_NAME] = PRODUCTION_TOOL_REGISTRY[MEMO_SEARCH_NAME]  # type: ignore[index]


# =========================================================================================
# DoD-9: offered at the seam (US-073.AC-1, D3, 021 D5)
# =========================================================================================


def _bool_setting(value: bool) -> ResolvedSetting[bool]:
    return ResolvedSetting(
        session=value, inherited=None, inherited_level=None, value=value, level=ConfigLevel.SESSION
    )


def _text_setting() -> ResolvedSetting[str]:
    return ResolvedSetting(session=None, inherited=None, inherited_level=None, value=None, level=None)


def _configuration(*, memo: bool, session: bool, web: bool) -> SessionConfiguration:
    return SessionConfiguration(
        model=None,
        system_prompt=_text_setting(),
        tool_memo_search=_bool_setting(memo),
        tool_session_search=_bool_setting(session),
        tool_web_search=_bool_setting(web),
        rp_language=_text_setting(),
        preferred_language=_text_setting(),
    )


def test_a_configured_registry_offers_all_three_declarations_in_order__S028_002_DoD9() -> None:
    """DoD-9 / 021 D5 — the three declarations, in declaration order."""
    registry = build_tool_registry(API_KEY, ENGINE_ID)

    offered = offered_tools(_configuration(memo=True, session=True, web=True), registry)

    assert list(offered) == [MEMO_SEARCH, SESSION_SEARCH, WEB_SEARCH]


def test_the_offered_web_search_declaration_is_the_declared_one__S028_002_DoD9() -> None:
    """DoD-9 / D11 — the `web_search` declaration is `definitions.py`'s, unchanged."""
    registry = build_tool_registry(API_KEY, ENGINE_ID)

    offered = offered_tools(_configuration(memo=True, session=True, web=True), registry)

    assert offered[2] == WEB_SEARCH
    function = offered[2]["function"]
    assert isinstance(function, Mapping)
    assert function["name"] == EXPECTED_TOOL_NAME


def test_the_switch_off_withholds_web_search_from_a_configured_registry__S028_002_DoD9() -> None:
    """DoD-9 / US-073.AC-1 — configured is not enough: the switch gates it."""
    registry = build_tool_registry(API_KEY, ENGINE_ID)

    offered = offered_tools(_configuration(memo=True, session=True, web=False), registry)

    assert list(offered) == [MEMO_SEARCH, SESSION_SEARCH]


def test_an_unconfigured_registry_offers_neither_web_search_nor_an_error__S028_002_DoD9() -> None:
    """DoD-9 / D3 — the switch on is not enough either: an unconfigured instance offers two."""
    registry = build_tool_registry(None, None)

    offered = offered_tools(_configuration(memo=True, session=True, web=True), registry)

    assert list(offered) == [MEMO_SEARCH, SESSION_SEARCH]


# =========================================================================================
# DoD-10: offered at the route (US-073.AC-1, D3)
# =========================================================================================


def _bounded[T](call: Callable[[], T]) -> T:
    """Run `call` on a worker thread; fail the test instead of hanging past the bound."""
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(call).result(timeout=HTTP_TIMEOUT_SECONDS)
    finally:
        pool.shutdown(wait=False)


# --- raw-insert helpers (file-local) --------------------------------------------------------


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


def _insert_session(engine: Engine, *, session_id: int, user_id: int, character_id: int) -> None:
    """A session with the captured model and **no** tool switch set at session level."""
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
                model_server_id=SERVER_ID,
                model_name=MODEL_NAME,
                system_prompt=None,
                tool_memo_search=None,
                tool_session_search=None,
                tool_web_search=None,
                rp_language=None,
                preferred_language=None,
            )
        )


def _insert_server_and_model(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            _servers()
            .insert()
            .values(
                id=SERVER_ID,
                name="the chat server",
                kind="llamaswap",
                base_url=BASE_URL,
                api_key_ref=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )
        connection.execute(
            _models()
            .insert()
            .values(
                id=MODEL_ROW_ID,
                server_id=SERVER_ID,
                model_name=MODEL_NAME,
                is_enabled=True,
                is_embedding_designated=False,
                embedding_dim=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _set_web_search_switch(engine: Engine, value: int) -> None:
    """`002.context.md`: the switch is set with a raw `UPDATE sessions SET tool_web_search`."""
    with engine.begin() as connection:
        connection.execute(
            update(schema.sessions)
            .where(schema.sessions.c.id == SESSION_A)
            .values(tool_web_search=value)
        )


@pytest.fixture(autouse=True)
def _quiet_factory_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the factory's logging call so these tests touch no global sinks."""
    monkeypatch.setattr("app.main.configure_logging", lambda settings: None)


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """Two roleplayers, each with a character and a session on one enabled model."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username=USER_A_NAME, password=USER_A_PASSWORD)
    _insert_user(db_engine, user_id=USER_B, username=USER_B_NAME, password=USER_B_PASSWORD)
    _insert_character(db_engine, character_id=CHARACTER_A, user_id=USER_A, name="Aria")
    _insert_character(db_engine, character_id=CHARACTER_B, user_id=USER_B, name="Bram")
    _insert_server_and_model(db_engine)
    _insert_session(db_engine, session_id=SESSION_A, user_id=USER_A, character_id=CHARACTER_A)
    _insert_session(db_engine, session_id=SESSION_B, user_id=USER_B, character_id=CHARACTER_B)
    return db_engine


# --- the fake chat client (records its tools; yields only text) -----------------------------


class ChatCall:
    """What one `chat_stream` call received."""

    def __init__(
        self, model: str, messages: list[ChatMessage], tools: list[Mapping[str, object]]
    ) -> None:
        self.model = model
        self.messages = messages
        self.tools = tools


class FakeChatClient:
    """Records every `chat_stream` call and answers with one text delta — never a tool call."""

    def __init__(self, text: str = "Hi") -> None:
        self.calls: list[ChatCall] = []
        self.text = text

    def chat_stream(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        tools: Sequence[Mapping[str, object]],
    ) -> AsyncIterator[ChatDelta]:
        self.calls.append(ChatCall(model, list(messages), [dict(tool) for tool in tools]))
        return self._stream()

    async def _stream(self) -> AsyncIterator[ChatDelta]:
        await asyncio.sleep(0)
        yield ChatDelta(content=self.text)


class FakeFactory:
    """A `ChatClientFactory` returning one fake client and recording its arguments."""

    def __init__(self, client: FakeChatClient) -> None:
        self.client = client
        self.calls: list[tuple[str, str | None, float]] = []

    def __call__(self, base_url: str, api_key: str | None, timeout_seconds: float) -> Any:
        self.calls.append((base_url, api_key, timeout_seconds))
        return self.client


# --- the application, the login and the SSE body -------------------------------------------


@pytest.fixture
def application(db_settings: Settings, engine: Engine) -> Iterator[FastAPI]:
    """The factory's application pinned to the seeded database.

    The tool-registry dependency is deliberately **not** overridden: DoD-10 exercises the real
    one. Each test replaces the `get_settings` override with its own credentialed `Settings`.
    """
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: db_settings
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


def _settings_with(
    monkeypatch: pytest.MonkeyPatch, db_settings: Settings, *, key: str, engine_id: str
) -> Settings:
    """A `Settings` for the per-test database carrying the two search credentials.

    The values arrive through the environment before construction (`002.context.md`), never
    through a real `.env`: the autouse isolation in `conftest.py` blanks both variables, and
    `db_settings` has already pointed the database variables at `tmp_path`.
    """
    monkeypatch.setenv(KEY_VARIABLE, key)
    monkeypatch.setenv(ID_VARIABLE, engine_id)
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.data_dir == db_settings.data_dir
    assert settings.db_filename == db_settings.db_filename
    return settings


def _use(application: FastAPI, settings: Settings, factory: FakeFactory) -> None:
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_chat_client_factory] = lambda: factory


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


def _compose(client: TestClient, session_id: Any) -> httpx.Response:
    path = COMPOSE_TEMPLATE.format(session_id=session_id)
    return _bounded(lambda: client.post(path, json={"text": COMPOSE_TEXT}))


def _events(response: httpx.Response) -> list[str]:
    """The `event` field of every SSE frame of a collected body, in order (test side only)."""
    assert response.status_code == 200, response.text
    events: list[str] = []
    for chunk in response.text.split("\n\n"):
        if not chunk.strip():
            continue
        data_lines = [line for line in chunk.split("\n") if line.startswith("data:")]
        assert len(data_lines) == 1, chunk
        payload = data_lines[0][len("data:") :]
        parsed = json.loads(payload.removeprefix(" "))
        assert isinstance(parsed, dict)
        events.append(parsed["event"])
    return events


def _recorded_tool_names(client_fake: FakeChatClient) -> list[str]:
    """The `function.name` of every declaration the one recorded round received, in order."""
    assert len(client_fake.calls) == 1, "the fake answers one round and never calls a tool"
    names: list[str] = []
    for tool in client_fake.calls[0].tools:
        function = tool["function"]
        assert isinstance(function, Mapping)
        names.append(str(function["name"]))
    return names


def test_the_route_offers_all_three_tools_when_configured__S028_002_DoD10(
    application: FastAPI, db_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-10 / D3 — credentials `test-key` / `test-cx`, no switch set: three declarations."""
    settings = _settings_with(monkeypatch, db_settings, key=API_KEY, engine_id=ENGINE_ID)
    client_fake = FakeChatClient()
    _use(application, settings, FakeFactory(client_fake))
    client = _login(application, settings, USER_A_NAME, USER_A_PASSWORD)

    response = _compose(client, SESSION_A)

    assert _events(response)[-1] == "done"
    assert client_fake.calls[0].tools == [dict(MEMO_SEARCH), dict(SESSION_SEARCH), dict(WEB_SEARCH)]


def test_the_route_withholds_web_search_when_the_switch_is_off__S028_002_DoD10(
    application: FastAPI, db_settings: Settings, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-10 / US-073.AC-1 — the session's `tool_web_search` raw-set false: the other two only."""
    _set_web_search_switch(engine, 0)
    settings = _settings_with(monkeypatch, db_settings, key=API_KEY, engine_id=ENGINE_ID)
    client_fake = FakeChatClient()
    _use(application, settings, FakeFactory(client_fake))
    client = _login(application, settings, USER_A_NAME, USER_A_PASSWORD)

    response = _compose(client, SESSION_A)

    assert _events(response)[-1] == "done"
    assert _recorded_tool_names(client_fake) == [MEMO_SEARCH_NAME, SESSION_SEARCH_NAME]
    assert WEB_SEARCH_NAME not in _recorded_tool_names(client_fake)


def test_the_route_withholds_web_search_when_the_key_is_blank__S028_002_DoD10(
    application: FastAPI, db_settings: Settings, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-10 / D3 — the switch on but the API key blank: `web_search` is absent."""
    _set_web_search_switch(engine, 1)
    settings = _settings_with(monkeypatch, db_settings, key="", engine_id=ENGINE_ID)
    client_fake = FakeChatClient()
    _use(application, settings, FakeFactory(client_fake))
    client = _login(application, settings, USER_A_NAME, USER_A_PASSWORD)

    response = _compose(client, SESSION_A)

    assert _events(response)[-1] == "done"
    assert _recorded_tool_names(client_fake) == [MEMO_SEARCH_NAME, SESSION_SEARCH_NAME]


def test_the_route_withholds_web_search_when_the_engine_id_is_blank__S028_002_DoD10(
    application: FastAPI, db_settings: Settings, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-10 / D3 — the switch on but the engine id blank: `web_search` is absent."""
    _set_web_search_switch(engine, 1)
    settings = _settings_with(monkeypatch, db_settings, key=API_KEY, engine_id="")
    client_fake = FakeChatClient()
    _use(application, settings, FakeFactory(client_fake))
    client = _login(application, settings, USER_A_NAME, USER_A_PASSWORD)

    response = _compose(client, SESSION_A)

    assert _events(response)[-1] == "done"
    assert _recorded_tool_names(client_fake) == [MEMO_SEARCH_NAME, SESSION_SEARCH_NAME]
