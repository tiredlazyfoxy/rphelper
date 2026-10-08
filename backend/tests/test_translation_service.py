"""Tests for feature 023, step 002 — `app/services/translation.py`, the translate flow.

Every expected value comes from `docs/plans/023.partner-translation/002.translation-service.md`
(Goal, Interface intent, DoD-1..DoD-18), from `002.context.md` ("The eligible-row read", "The
write transaction", "The model call", "Cause sentences", "Logging", "Test shape") and from the
feature `context.md` (**D2**, **D3**, **D4**, **D5**, **D6**, **D8**, **D9**, **D10**, the Wire
contract, the cross-cutting constraints). No expected value is read from the implementation; the
only file this suite *reads* is the one DoD-16 asks it to scan.

Bindings come from `status.md` `## Skeleton` -> **Step 002 — frozen interface**:

- `FALLBACK_TARGET_LANGUAGE` (its value is part of the freeze, DoD-16)
- `DisconnectProbe = Callable[[], Awaitable[bool]]`
- `TranslationResult(message_id: int, target_language: str, text: str, cached: bool)` (frozen)
- `get_cached_translation(connection, user_id, message_id, target_language) -> str | None`
- `async translate_message(engine, generator, user_id, message_id, timeout_seconds,
  client_factory, is_disconnected) -> TranslationResult` — **the generator is the second
  positional parameter**, and this file builds its own `SnowflakeGenerator(node_id=0)`.
- Upstream: `ChatMessage(role, content, ...)`, `ChatDelta(content, reasoning, tool_calls)`,
  `ChatClientFactory = Callable[[base_url, api_key, timeout], ChatClientLike]`,
  `LlmUnreachableError` from **`app.errors`**, `assemble_context(connection, user_id,
  session_id)`.

Seeding follows feature 023's **Test conventions**: a file-local `engine` fixture applies the
registry with `schema.metadata.create_all`, raw-inserts two users (isolation), a character and a
session each, the registry rows (`llm_servers` + `models`, per 017's conventions) and USER_A's
stream (two settled partner rows, a settled turn, a settled decision, a row buried under the
turn, a zone row) plus one settled partner row of USER_B. Async service code is driven with
`asyncio.run(...)`, bounded by `asyncio.wait_for`. The provider fake is file-local: it yields
scripted `ChatDelta`s or raises, records each call's model name, messages and tools and whether
its iterator was closed, runs a per-test hook on first entry (DoD-13 / 14 / 18) and is built by a
file-local factory recording its `(base_url, api_key, timeout)`. **No fixture is added to
`conftest.py`.** Each test name ends `__S023_002_DoD<n>`.
"""

from __future__ import annotations

import ast
import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from loguru import logger
from sqlalchemy import Engine, Table, select, update

from app.db import schema
from app.errors import (
    LlmUnreachableError,
    MessageNotFoundError,
    ModelNotChosenError,
    ModelNotEnabledError,
    NoModelEnabledError,
    SecretRefError,
    TranslationFailedError,
)
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services import compose as compose_module
from app.services import context as context_module
from app.services import translation as translation_module
from app.services.context import assemble_context
from app.services.llm.chat import ChatMessage
from app.services.llm.client import ChatDelta
from app.services.translation import (
    FALLBACK_TARGET_LANGUAGE,
    TranslationResult,
    get_cached_translation,
    translate_message,
)

#: The seeded instants, in the schema's fixed-width timestamp form.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
SETTLED_AT = "2026-01-01T00:00:01.000000+00:00"

USER_A = 101
USER_B = 202
CHAR_A = 1_001
CHAR_B = 2_001
SESSION_A = 5_001
SESSION_B = 6_001

#: Raw-seeded `messages` ids. Small, so nothing collides with a minted snowflake.
PARTNER_A = 11
PARTNER_A2 = 12
TURN_A = 13
BURIED_A = 14
ZONE_A = 15
DECISION_A = 16
PARTNER_B = 21
UNKNOWN_MESSAGE = 7_777_777_777

#: Raw-seeded `translations` id (DoD-4's pre-cached row).
CACHED_A_RUSSIAN = 901

#: A character minted by DoD-18's hook, into a table the service never touches.
LOCK_PROBE_CHARACTER = 1_777

#: Registry rows (017's conventions). SERVER_A carries three models: the session's captured one,
#: a disabled one and a second enabled one, so "the captured model is disabled" and "no model is
#: enabled at all" are distinguishable states (DoD-3, DoD-11).
SERVER_A = 8_501
MODEL_ROW_ON = 8_601
MODEL_ROW_OFF = 8_602
MODEL_ROW_OTHER = 8_603
MODEL_NAME = "story-model-7b"
MODEL_OFF_NAME = "retired-model-3b"
OTHER_MODEL_NAME = "spare-model-1b"
BASE_URL = "http://chat-translate.test:8080"

MISSING_VARIABLE = "RPH_MISSING_TRANSLATION_KEY"
MISSING_POINTER = "$RPH_MISSING_TRANSLATION_KEY"

#: The timeout the caller hands the service (DoD-1: the factory receives this value).
TIMEOUT = 17.5

#: Bound for every asyncio run.
RUN_TIMEOUT_SECONDS = 10.0

#: DoD-1's row text and deltas, verbatim from the DoD.
PARTNER_A_TEXT = "She waves.\n\n*smiles*"
DELTA_ONE = "При"
DELTA_TWO = "вет"
JOINED = "Привет"

#: DoD-17's redaction markers: distinctive enough that a leak into a log record is unmistakable.
SOURCE_MARKER = "ZZSOURCEMARKERZZ"
TRANSLATED_MARKER = "QQTRANSLATEDMARKERQQ"
PARTNER_A2_TEXT = f"He answers from the jetty. {SOURCE_MARKER}"
PARTNER_A2_TRANSLATION = f"Он отвечает с причала. {TRANSLATED_MARKER}"

TURN_A_TEXT = "I nod and step closer."
BURIED_A_TEXT = "A buried draft."
ZONE_A_TEXT = "A zone draft."
DECISION_A_TEXT = "((skip ahead))"
PARTNER_B_TEXT = "Bob's settled partner entry."

CHAR_A_SHEET = "Aria keeps the lighthouse and speaks little."

#: DoD-4's pre-cached Russian row, and the French text the model then produces.
RUSSIAN_CACHED_TEXT = "Она машет рукой."
FRENCH_TEXT = "Elle fait signe de la main."

#: DoD-13's row, inserted by the hook while the model call is in flight.
EARLIER_TEXT = "Earlier"

#: DoD-14's new text, written by the hook while the model call is in flight.
EDITED_TEXT = "She waits by the pier instead."

#: Events recorded into the one ordered list shared by the fake and the probe (DoD-12).
DELTA_EVENT = "delta"
EXHAUSTED_EVENT = "stream-exhausted"
PROBE_EVENT = "probe"


# --- seeding ------------------------------------------------------------------------------


def _servers() -> Table:
    return schema.metadata.tables["llm_servers"]


def _models() -> Table:
    return schema.metadata.tables["models"]


def _translations() -> Table:
    return schema.metadata.tables["translations"]


def _insert_user(
    engine: Engine,
    *,
    user_id: int,
    username: str,
    preferred_language: str | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.users.insert().values(
                id=user_id,
                username=username,
                password_hash="not-a-real-hash",
                role=Role.ROLEPLAYER,
                is_enabled=True,
                rp_language=None,
                preferred_language=preferred_language,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_character(engine: Engine, *, character_id: int, user_id: int, name: str, sheet: str = "") -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.characters.insert().values(
                id=character_id,
                user_id=user_id,
                name=name,
                sheet=sheet,
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_session(
    engine: Engine,
    *,
    session_id: int,
    user_id: int,
    character_id: int,
    model_server_id: int | None = None,
    model_name: str | None = None,
    preferred_language: str | None = None,
) -> None:
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
                preferred_language=preferred_language,
            )
        )


def _insert_message(
    engine: Engine,
    *,
    message_id: int,
    user_id: int,
    session_id: int,
    body: str,
    role: str = "user",
    kind: str | None = "partner",
    related_to: int | None = None,
    settled_at: str | None = SETTLED_AT,
) -> None:
    """Raw-insert one `messages` row in a chosen state (kind / settled_at / related_to)."""
    with engine.begin() as connection:
        connection.execute(
            schema.messages.insert().values(
                id=message_id,
                user_id=user_id,
                session_id=session_id,
                role=role,
                kind=kind,
                text=body,
                related_to=related_to,
                settled_at=settled_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_translation(
    engine: Engine,
    *,
    translation_id: int,
    user_id: int,
    message_id: int,
    target_language: str,
    body: str,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            _translations()
            .insert()
            .values(
                id=translation_id,
                user_id=user_id,
                message_id=message_id,
                target_language=target_language,
                text=body,
                created_at=TIMESTAMP,
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


# --- mutations the individual tests need ---------------------------------------------------


def _set_user_preferred_language(engine: Engine, user_id: int, value: str | None) -> None:
    with engine.begin() as connection:
        connection.execute(
            update(schema.users).where(schema.users.c.id == user_id).values(preferred_language=value)
        )


def _set_session_preferred_language(engine: Engine, session_id: int, value: str | None) -> None:
    with engine.begin() as connection:
        connection.execute(
            update(schema.sessions).where(schema.sessions.c.id == session_id).values(preferred_language=value)
        )


def _set_session_model(engine: Engine, session_id: int, server_id: int | None, name: str | None) -> None:
    with engine.begin() as connection:
        connection.execute(
            update(schema.sessions)
            .where(schema.sessions.c.id == session_id)
            .values(model_server_id=server_id, model_name=name)
        )


def _set_model_enabled(engine: Engine, model_id: int, enabled: bool) -> None:
    with engine.begin() as connection:
        connection.execute(update(_models()).where(_models().c.id == model_id).values(is_enabled=enabled))


def _disable_every_model(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(update(_models()).values(is_enabled=False))


def _set_api_key_ref(engine: Engine, server_id: int, ref: str | None) -> None:
    with engine.begin() as connection:
        connection.execute(update(_servers()).where(_servers().c.id == server_id).values(api_key_ref=ref))


def _set_message_text(engine: Engine, message_id: int, body: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            update(schema.messages).where(schema.messages.c.id == message_id).values(text=body)
        )


# --- reads of stored state ----------------------------------------------------------------


def _translation_rows(engine: Engine) -> list[dict[str, Any]]:
    table = _translations()
    with engine.connect() as connection:
        rows = connection.execute(select(table).order_by(table.c.id)).mappings().all()
    return [dict(row) for row in rows]


def _pairs(engine: Engine) -> list[tuple[int, str, str]]:
    """Every stored translation as `(message_id, target_language, text)`, in insertion order."""
    return [(int(row["message_id"]), row["target_language"], row["text"]) for row in _translation_rows(engine)]


def _cached(engine: Engine, user_id: int, message_id: int, target_language: str) -> str | None:
    with engine.connect() as connection:
        result = get_cached_translation(connection, user_id, message_id, target_language)
        assert not connection.in_transaction()
        return result


def _character_names(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        return {row[0] for row in connection.execute(select(schema.characters.c.name)).all()}


@pytest.fixture
def engine(db_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Engine:
    """A per-test database: the schema, two owners with a character and a session each, SERVER_A
    with three models (the session's captured one enabled, one disabled, one spare enabled) and
    USER_A's stream — two settled partner rows, a settled turn with a row buried under it, a
    settled decision and a zone row — plus one settled partner row of USER_B.

    USER_A's preferred language is "Russian" and SESSION_A sets none (DoD-1).
    """
    monkeypatch.delenv(MISSING_VARIABLE, raising=False)
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)

    _insert_user(db_engine, user_id=USER_A, username="alice", preferred_language="Russian")
    _insert_user(db_engine, user_id=USER_B, username="bob", preferred_language="Dutch")
    _insert_character(db_engine, character_id=CHAR_A, user_id=USER_A, name="Aria", sheet=CHAR_A_SHEET)
    _insert_character(db_engine, character_id=CHAR_B, user_id=USER_B, name="Bram")

    _insert_server(db_engine, server_id=SERVER_A, base_url=BASE_URL, api_key_ref=None)
    _insert_model(db_engine, model_id=MODEL_ROW_ON, server_id=SERVER_A, name=MODEL_NAME, enabled=True)
    _insert_model(db_engine, model_id=MODEL_ROW_OFF, server_id=SERVER_A, name=MODEL_OFF_NAME, enabled=False)
    _insert_model(db_engine, model_id=MODEL_ROW_OTHER, server_id=SERVER_A, name=OTHER_MODEL_NAME, enabled=True)

    _insert_session(
        db_engine,
        session_id=SESSION_A,
        user_id=USER_A,
        character_id=CHAR_A,
        model_server_id=SERVER_A,
        model_name=MODEL_NAME,
    )
    _insert_session(
        db_engine,
        session_id=SESSION_B,
        user_id=USER_B,
        character_id=CHAR_B,
        model_server_id=SERVER_A,
        model_name=MODEL_NAME,
    )

    _insert_message(db_engine, message_id=PARTNER_A, user_id=USER_A, session_id=SESSION_A, body=PARTNER_A_TEXT)
    _insert_message(db_engine, message_id=PARTNER_A2, user_id=USER_A, session_id=SESSION_A, body=PARTNER_A2_TEXT)
    _insert_message(
        db_engine,
        message_id=TURN_A,
        user_id=USER_A,
        session_id=SESSION_A,
        body=TURN_A_TEXT,
        kind="turn",
    )
    _insert_message(
        db_engine,
        message_id=DECISION_A,
        user_id=USER_A,
        session_id=SESSION_A,
        body=DECISION_A_TEXT,
        kind="decision",
    )
    _insert_message(
        db_engine,
        message_id=BURIED_A,
        user_id=USER_A,
        session_id=SESSION_A,
        body=BURIED_A_TEXT,
        kind=None,
        related_to=TURN_A,
        settled_at=None,
    )
    _insert_message(
        db_engine,
        message_id=ZONE_A,
        user_id=USER_A,
        session_id=SESSION_A,
        body=ZONE_A_TEXT,
        kind=None,
        settled_at=None,
    )
    _insert_message(db_engine, message_id=PARTNER_B, user_id=USER_B, session_id=SESSION_B, body=PARTNER_B_TEXT)
    return db_engine


@pytest.fixture
def generator() -> SnowflakeGenerator:
    """The service takes its id generator as a parameter (`## Skeleton`, step 002)."""
    return SnowflakeGenerator(node_id=0)


# --- the provider fake, its factory and the disconnect probe --------------------------------

#: One scripted stream: deltas in order, optionally ending in an exception to raise.
Script = Sequence[ChatDelta | BaseException]


class ChatCall:
    """What one `chat_stream` call received, and what became of its iterator."""

    def __init__(self, model: str, messages: list[ChatMessage], tools: list[Mapping[str, object]]) -> None:
        self.model = model
        self.messages = messages
        self.tools = tools
        self.closed = False
        self.exhausted = False


class FakeStream:
    """The object `chat_stream` returns: an async iterator with an explicit `aclose`.

    `002.context.md` ("The model call") requires the iterator always to be closed, with
    `contextlib.aclosing` or an `aclose()` in a `finally`. Recording `aclose` here makes that
    observable even on the path where the stream raised (DoD-7), where a generator's own
    `GeneratorExit` would never fire.
    """

    def __init__(
        self,
        call: ChatCall,
        script: Script,
        order: list[str],
        hook: Callable[[], None] | None,
    ) -> None:
        self._call = call
        self._script = list(script)
        self._order = order
        self._hook = hook
        self._inner = self._iterate()

    def __aiter__(self) -> FakeStream:
        return self

    async def __anext__(self) -> ChatDelta:
        return await self._inner.__anext__()

    async def aclose(self) -> None:
        self._call.closed = True
        await self._inner.aclose()

    async def _iterate(self) -> AsyncIterator[ChatDelta]:
        try:
            if self._hook is not None:
                self._hook()
            for item in self._script:
                if isinstance(item, BaseException):
                    raise item
                await asyncio.sleep(0)
                self._order.append(DELTA_EVENT)
                yield item
            self._call.exhausted = True
            self._order.append(EXHAUSTED_EVENT)
        except GeneratorExit:
            self._call.closed = True
            raise


class FakeChatClient:
    """Replays one scripted stream per `chat_stream` call; records every call.

    `hook`, when given, runs on first entry of the **first** stream, before any delta — the seam
    DoD-13, DoD-14 and DoD-18 use to touch the database while the model call is in flight.
    """

    def __init__(
        self,
        script: Script,
        *,
        hook: Callable[[], None] | None = None,
        order: list[str] | None = None,
    ) -> None:
        self.script = list(script)
        self.hook = hook
        self.order: list[str] = order if order is not None else []
        self.calls: list[ChatCall] = []
        self.streams: list[FakeStream] = []

    def chat_stream(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        tools: Sequence[Mapping[str, object]],
    ) -> FakeStream:
        call = ChatCall(model, list(messages), [dict(tool) for tool in tools])
        hook = self.hook if not self.calls else None
        self.calls.append(call)
        stream = FakeStream(call, self.script, self.order, hook)
        self.streams.append(stream)
        return stream


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


def _reasoning(text: str) -> ChatDelta:
    return ChatDelta(reasoning=text)


def _probe(order: list[str], *, disconnected: bool = False) -> Callable[[], Awaitable[bool]]:
    """A `DisconnectProbe`: it records its await into the shared ordered list (D4, DoD-12)."""

    async def probe() -> bool:
        order.append(PROBE_EVENT)
        return disconnected

    return probe


def _two_deltas(order: list[str] | None = None, hook: Callable[[], None] | None = None) -> FakeChatClient:
    """DoD-1's script: content "При" then "вет"."""
    return FakeChatClient([_content(DELTA_ONE), _content(DELTA_TWO)], hook=hook, order=order)


# --- drivers --------------------------------------------------------------------------------


def _translate(
    engine: Engine,
    generator: SnowflakeGenerator,
    factory: FakeFactory,
    *,
    message_id: int = PARTNER_A,
    user_id: int = USER_A,
    probe: Callable[[], Awaitable[bool]] | None = None,
    order: list[str] | None = None,
    timeout: float = TIMEOUT,
) -> TranslationResult:
    """Run the async service from a sync test (`context.md` Test conventions)."""
    is_disconnected = probe if probe is not None else _probe(order if order is not None else [])
    return asyncio.run(
        asyncio.wait_for(
            translate_message(engine, generator, user_id, message_id, timeout, factory, is_disconnected),
            timeout=RUN_TIMEOUT_SECONDS,
        )
    )


@contextmanager
def _captured_logs() -> Iterator[list[str]]:
    """A loguru sink collecting every formatted message, removed again afterwards (DoD-17)."""
    records: list[str] = []
    sink_id = logger.add(records.append, level=0, format="{message}")
    try:
        yield records
    finally:
        logger.remove(sink_id)


def _imported_modules(module: ModuleType) -> list[str]:
    """Every absolutely-imported module name in `module`'s source, read AST-wise."""
    module_file = module.__file__
    assert module_file is not None
    tree = ast.parse(Path(module_file).read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0:
                found.append(node.module or "")
        elif isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
    return found


def _imports_the_translation_service(module: ModuleType) -> bool:
    """Whether `module` imports `app.services.translation`, in any of the three spellings."""
    module_file = module.__file__
    assert module_file is not None
    tree = ast.parse(Path(module_file).read_text(encoding="utf-8"))
    target = "app.services.translation"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == target or alias.name.startswith(f"{target}.") for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            name = node.module or ""
            if name == target or name.startswith(f"{target}."):
                return True
            if name == "app.services" and any(alias.name == "translation" for alias in node.names):
                return True
    return False


def _module_source(module: ModuleType) -> str:
    module_file = module.__file__
    assert module_file is not None
    return Path(module_file).read_text(encoding="utf-8")


# ====================================================================== DoD-1
# US-045.AC-1 / D2 / D8 — the happy path, end to end.


def test_a_first_flick_translates_caches_and_reports_the_target_language__S023_002_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-1 — user "Russian", session none; the fake yields "При" then "вет": the result is
    "Привет" / "Russian" / cached false with the row's id, and one row is stored for the caller."""
    client = _two_deltas()
    factory = FakeFactory(client)

    result = _translate(engine, generator, factory)

    assert isinstance(result, TranslationResult)
    assert (result.message_id, result.target_language, result.text, result.cached) == (
        PARTNER_A,
        "Russian",
        JOINED,
        False,
    )
    rows = _translation_rows(engine)
    assert len(rows) == 1
    assert (
        int(rows[0]["message_id"]),
        rows[0]["target_language"],
        rows[0]["text"],
        int(rows[0]["user_id"]),
    ) == (PARTNER_A, "Russian", JOINED, USER_A)


def test_the_stored_row_is_readable_only_by_its_owner__S023_002_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-1 / R5 — the cached text comes back for the caller's own pair and for nobody else."""
    _translate(engine, generator, FakeFactory(_two_deltas()))

    assert _cached(engine, USER_A, PARTNER_A, "Russian") == JOINED
    assert _cached(engine, USER_B, PARTNER_A, "Russian") is None
    assert _cached(engine, USER_A, PARTNER_A, "French") is None
    assert _cached(engine, USER_A, PARTNER_A2, "Russian") is None


def test_the_model_is_called_with_the_captured_name_and_no_tools__S023_002_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-1 / D2 — one call, with the session's captured model name and an empty tools list."""
    client = _two_deltas()

    _translate(engine, generator, FakeFactory(client))

    assert len(client.calls) == 1
    assert client.calls[0].model == MODEL_NAME
    assert client.calls[0].tools == []


def test_exactly_two_messages_a_system_then_the_row_text__S023_002_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-1 / D8 — exactly two messages: a `system` one naming the target language, then a
    `user` one whose content is the row's text verbatim."""
    client = _two_deltas()

    _translate(engine, generator, FakeFactory(client))

    messages = client.calls[0].messages
    assert len(messages) == 2
    assert messages[0].role == "system"
    assert "Russian" in messages[0].content
    assert messages[1].role == "user"
    assert messages[1].content == PARTNER_A_TEXT


def test_the_factory_receives_the_servers_base_url_and_the_given_timeout__S023_002_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-1 — the chat-client factory is called once, with the server's base URL and the
    timeout the caller passed in."""
    factory = FakeFactory(_two_deltas())

    _translate(engine, generator, factory, timeout=TIMEOUT)

    assert [(call[0], call[2]) for call in factory.calls] == [(BASE_URL, TIMEOUT)]


# ====================================================================== DoD-2
# US-046.AC-1 / UC-041 — the second flick is a cache hit.


def test_a_second_call_answers_from_the_cache__S023_002_DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-2 — the second call returns the same text and target language with cached true, and
    touches neither the factory nor the client."""
    first = _translate(engine, generator, FakeFactory(_two_deltas()))

    second_client = _two_deltas()
    second_factory = FakeFactory(second_client)
    second = _translate(engine, generator, second_factory)

    assert (second.message_id, second.target_language, second.text, second.cached) == (
        PARTNER_A,
        "Russian",
        JOINED,
        True,
    )
    assert (second.target_language, second.text) == (first.target_language, first.text)
    assert second_factory.calls == []
    assert second_client.calls == []
    assert len(_translation_rows(engine)) == 1


# ====================================================================== DoD-3
# D8 — a hit never resolves a model, so no model needs to be enabled.


@pytest.mark.parametrize(
    "break_the_registry",
    [
        pytest.param(lambda engine: _set_model_enabled(engine, MODEL_ROW_ON, False), id="session-model-disabled"),
        pytest.param(_disable_every_model, id="every-model-disabled"),
    ],
)
def test_a_cache_hit_needs_no_enabled_model__S023_002_DoD3(
    engine: Engine, generator: SnowflakeGenerator, break_the_registry: Callable[[Engine], None]
) -> None:
    """DoD-3 / D8 — once the row is cached, the model resolution never runs: the cached text
    still comes back with cached true, with the session's model disabled and, separately, with
    every model disabled."""
    _translate(engine, generator, FakeFactory(_two_deltas()))

    break_the_registry(engine)
    client = _two_deltas()
    factory = FakeFactory(client)
    result = _translate(engine, generator, factory)

    assert (result.target_language, result.text, result.cached) == ("Russian", JOINED, True)
    assert factory.calls == []
    assert client.calls == []


# ====================================================================== DoD-4
# R1 / R8 cache key — a session override beats the user's language, under its own key.


def test_a_session_override_beats_the_users_language_and_caches_separately__S023_002_DoD4(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-4 / R1 — session "French" over user "Russian", with a "Russian" row already cached:
    the call is a miss, the model is asked for "French", a second row lands under "French" and
    both rows remain."""
    _set_session_preferred_language(engine, SESSION_A, "French")
    _insert_translation(
        engine,
        translation_id=CACHED_A_RUSSIAN,
        user_id=USER_A,
        message_id=PARTNER_A,
        target_language="Russian",
        body=RUSSIAN_CACHED_TEXT,
    )
    client = FakeChatClient([_content(FRENCH_TEXT)])

    result = _translate(engine, generator, FakeFactory(client))

    assert (result.target_language, result.text, result.cached) == ("French", FRENCH_TEXT, False)
    assert len(client.calls) == 1
    assert "French" in client.calls[0].messages[0].content
    assert set(_pairs(engine)) == {
        (PARTNER_A, "Russian", RUSSIAN_CACHED_TEXT),
        (PARTNER_A, "French", FRENCH_TEXT),
    }


# ====================================================================== DoD-5
# D3 — nothing resolved at either level means the fallback target language.


def test_no_preferred_language_falls_back_to_english__S023_002_DoD5(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-5 / D3 — neither the user nor the session sets a preferred language: the target is
    "English", in the result, in the stored row and in the system message."""
    _set_user_preferred_language(engine, USER_A, None)
    _set_session_preferred_language(engine, SESSION_A, None)
    client = _two_deltas()

    result = _translate(engine, generator, FakeFactory(client))

    assert (result.target_language, result.text, result.cached) == ("English", JOINED, False)
    assert _pairs(engine) == [(PARTNER_A, "English", JOINED)]
    assert "English" in client.calls[0].messages[0].content


def test_a_fallback_translation_is_cached_under_english__S023_002_DoD5(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-5 / D3 — the cache key uses the effective target, so the second call is a hit."""
    _set_user_preferred_language(engine, USER_A, None)
    _set_session_preferred_language(engine, SESSION_A, None)
    _translate(engine, generator, FakeFactory(_two_deltas()))

    second_client = _two_deltas()
    result = _translate(engine, generator, FakeFactory(second_client))

    assert (result.target_language, result.text, result.cached) == ("English", JOINED, True)
    assert second_client.calls == []
    assert len(_translation_rows(engine)) == 1


# ====================================================================== DoD-6
# D6 / R5 — everything ineligible is the same missing row.


@pytest.mark.parametrize(
    "message_id",
    [
        pytest.param(PARTNER_B, id="another-users-settled-partner-row"),
        pytest.param(ZONE_A, id="zone-row"),
        pytest.param(BURIED_A, id="buried-row"),
        pytest.param(TURN_A, id="settled-turn"),
        pytest.param(DECISION_A, id="settled-decision"),
        pytest.param(UNKNOWN_MESSAGE, id="id-that-exists-for-nobody"),
    ],
)
def test_an_ineligible_row_is_indistinguishable_from_a_missing_one__S023_002_DoD6(
    engine: Engine, generator: SnowflakeGenerator, message_id: int
) -> None:
    """DoD-6 / D6 / R5 — each ineligible case raises `MessageNotFoundError`, never reaches the
    factory and writes no row."""
    client = _two_deltas()
    factory = FakeFactory(client)

    with pytest.raises(MessageNotFoundError):
        _translate(engine, generator, factory, message_id=message_id)

    assert factory.calls == []
    assert client.calls == []
    assert _translation_rows(engine) == []


# ====================================================================== DoD-7
# US-048.AC-1 / D5 — an unreachable provider fails, caches nothing and closes the iterator.


@pytest.mark.parametrize(
    "script",
    [
        pytest.param([LlmUnreachableError("the server is down")], id="raises-before-any-delta"),
        pytest.param([_content(DELTA_ONE), LlmUnreachableError("the server is down")], id="raises-mid-stream"),
    ],
)
def test_an_unreachable_provider_fails_with_translation_failed__S023_002_DoD7(
    engine: Engine, generator: SnowflakeGenerator, script: Script
) -> None:
    """DoD-7 / D5 — `LlmUnreachableError` before any delta and after one both become
    `TranslationFailedError` with code `translation_failed` and the message id in `detail`; no
    row is written and the fake's iterator was closed."""
    client = FakeChatClient(script)

    with pytest.raises(TranslationFailedError) as raised:
        _translate(engine, generator, FakeFactory(client))

    assert raised.value.code == "translation_failed"
    assert dict(raised.value.detail) == {"message_id": str(PARTNER_A)}
    assert _translation_rows(engine) == []
    assert len(client.calls) == 1
    assert client.calls[0].closed is True


# ====================================================================== DoD-8
# US-048.AC-2 — a failure memoises nothing.


def test_a_call_after_a_failure_tries_the_model_again__S023_002_DoD8(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-8 / US-048.AC-2 — after DoD-7's failure a succeeding fake is called and its result is
    cached."""
    with pytest.raises(TranslationFailedError):
        _translate(engine, generator, FakeFactory(FakeChatClient([LlmUnreachableError("down")])))

    second_client = _two_deltas()
    result = _translate(engine, generator, FakeFactory(second_client))

    assert len(second_client.calls) == 1
    assert (result.text, result.cached) == (JOINED, False)
    assert _pairs(engine) == [(PARTNER_A, "Russian", JOINED)]


# ====================================================================== DoD-9
# D5 / D10 — an empty result is a failure, and caches nothing.


@pytest.mark.parametrize(
    "script",
    [
        pytest.param([], id="no-content-at-all"),
        pytest.param([_reasoning("plan"), _reasoning(" more")], id="only-reasoning-deltas"),
        pytest.param([_content("   \n")], id="whitespace-only-content"),
        pytest.param([_content("<think>only reasoning</think>")], id="only-a-think-block"),
    ],
)
def test_an_empty_result_fails_and_caches_nothing__S023_002_DoD9(
    engine: Engine, generator: SnowflakeGenerator, script: Script
) -> None:
    """DoD-9 / D5 / D10 — nothing, only reasoning, whitespace only and a bare `<think>` block
    each raise `TranslationFailedError` and write no row."""
    client = FakeChatClient(script)

    with pytest.raises(TranslationFailedError) as raised:
        _translate(engine, generator, FakeFactory(client))

    assert raised.value.code == "translation_failed"
    assert dict(raised.value.detail) == {"message_id": str(PARTNER_A)}
    assert _translation_rows(engine) == []


# ====================================================================== DoD-10
# D2 / D10 — reasoning is ignored and a `<think>` block is stripped.


def test_reasoning_is_ignored_and_a_think_block_is_stripped__S023_002_DoD10(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-10 — a reasoning delta "plan", then content "<think>x</think>\\n\\n", then "Hola":
    "Hola" is returned and stored."""
    client = FakeChatClient([_reasoning("plan"), _content("<think>x</think>\n\n"), _content("Hola")])

    result = _translate(engine, generator, FakeFactory(client))

    assert (result.text, result.cached) == ("Hola", False)
    assert _pairs(engine) == [(PARTNER_A, "Russian", "Hola")]


# ====================================================================== DoD-11
# D5 / R4 — 017's and 021's refusals propagate unchanged and write nothing.


def _break_no_model_enabled(engine: Engine) -> None:
    _disable_every_model(engine)


def _break_model_not_chosen(engine: Engine) -> None:
    _set_session_model(engine, SESSION_A, None, None)


def _break_model_not_enabled(engine: Engine) -> None:
    _set_model_enabled(engine, MODEL_ROW_ON, False)


def _break_secret_ref_missing(engine: Engine) -> None:
    _set_api_key_ref(engine, SERVER_A, MISSING_POINTER)


@pytest.mark.parametrize(
    ("break_it", "error"),
    [
        pytest.param(_break_no_model_enabled, NoModelEnabledError, id="no-enabled-model"),
        pytest.param(_break_model_not_chosen, ModelNotChosenError, id="no-captured-model"),
        pytest.param(_break_model_not_enabled, ModelNotEnabledError, id="disabled-captured-model"),
        pytest.param(_break_secret_ref_missing, SecretRefError, id="unset-key-variable"),
    ],
)
def test_the_upstream_refusals_propagate_unchanged__S023_002_DoD11(
    engine: Engine,
    generator: SnowflakeGenerator,
    break_it: Callable[[Engine], None],
    error: type[Exception],
) -> None:
    """DoD-11 / D5 / R4 — 017's three model refusals and 021's `secret_ref_missing` reach the
    caller as themselves; the client is never called and no row is written."""
    break_it(engine)
    client = _two_deltas()

    with pytest.raises(error):
        _translate(engine, generator, FakeFactory(client))

    assert client.calls == []
    assert _translation_rows(engine) == []


def test_a_disabled_captured_model_names_the_session_level__S023_002_DoD11(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-11 — the captured model being disabled refuses at the `session` level (017 D3)."""
    _break_model_not_enabled(engine)

    with pytest.raises(ModelNotEnabledError) as raised:
        _translate(engine, generator, FakeFactory(_two_deltas()))

    assert dict(raised.value.detail)["level"] == "session"


def test_an_unset_key_variable_refuses_with_secret_ref_missing__S023_002_DoD11(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-11 — the server's `api_key_ref` naming an unset variable refuses with that code."""
    _break_secret_ref_missing(engine)

    with pytest.raises(SecretRefError) as raised:
        _translate(engine, generator, FakeFactory(_two_deltas()))

    assert raised.value.code == "secret_ref_missing"
    assert _translation_rows(engine) == []


# ====================================================================== DoD-12
# US-133.AC-2 (best-effort half) / D4 — the disconnected-before-write path only.


def test_a_disconnect_before_the_write_skips_the_row_but_returns_the_text__S023_002_DoD12(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-12 / D4 — the probe reports a disconnect: the produced text still comes back with
    cached false, and no row is written."""
    order: list[str] = []
    client = _two_deltas(order)

    result = _translate(
        engine, generator, FakeFactory(client), probe=_probe(order, disconnected=True), order=order
    )

    assert (result.message_id, result.target_language, result.text, result.cached) == (
        PARTNER_A,
        "Russian",
        JOINED,
        False,
    )
    assert _translation_rows(engine) == []


def test_the_probe_is_awaited_once_after_the_stream_finished__S023_002_DoD12(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-12 / D4 — the fake and the probe record into one ordered list: the probe is awaited
    exactly once, and after the fake's iterator finished."""
    order: list[str] = []
    client = _two_deltas(order)

    _translate(engine, generator, FakeFactory(client), probe=_probe(order, disconnected=True), order=order)

    assert order.count(PROBE_EVENT) == 1
    assert EXHAUSTED_EVENT in order
    assert order.index(PROBE_EVENT) > order.index(EXHAUSTED_EVENT)


def test_a_probe_reporting_no_disconnect_lets_the_row_land__S023_002_DoD12(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-12 — the same path with a probe reporting no disconnect writes the row (DoD-1)."""
    order: list[str] = []
    client = _two_deltas(order)

    result = _translate(
        engine, generator, FakeFactory(client), probe=_probe(order, disconnected=False), order=order
    )

    assert (result.text, result.cached) == (JOINED, False)
    assert _pairs(engine) == [(PARTNER_A, "Russian", JOINED)]
    assert order.count(PROBE_EVENT) == 1


# ====================================================================== DoD-13
# D8 — two concurrent first flicks never collide.


def test_a_row_inserted_during_the_call_is_kept_and_nothing_raises__S023_002_DoD13(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-13 / D8 — the pair is raw-inserted with "Earlier" while the model call is in flight:
    the call still returns its own produced text with cached false, raises nothing, and exactly
    one row survives for the pair — the "Earlier" one."""
    inserted_id = 950

    def hook() -> None:
        _insert_translation(
            engine,
            translation_id=inserted_id,
            user_id=USER_A,
            message_id=PARTNER_A,
            target_language="Russian",
            body=EARLIER_TEXT,
        )

    client = _two_deltas(hook=hook)

    result = _translate(engine, generator, FakeFactory(client))

    assert (result.target_language, result.text, result.cached) == ("Russian", JOINED, False)
    assert _pairs(engine) == [(PARTNER_A, "Russian", EARLIER_TEXT)]


# ====================================================================== DoD-14
# D9 / US-111.AC-2 — an edit during the call leaves no stale cache row.


def test_an_edit_during_the_call_writes_no_row__S023_002_DoD14(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-14 / D9 — the message's text is raw-updated while the model call is in flight: the
    produced text is returned and **no** row is written."""

    def hook() -> None:
        _set_message_text(engine, PARTNER_A, EDITED_TEXT)

    client = _two_deltas(hook=hook)

    result = _translate(engine, generator, FakeFactory(client))

    assert (result.target_language, result.text, result.cached) == ("Russian", JOINED, False)
    assert _translation_rows(engine) == []


def test_the_next_call_after_an_edit_sends_the_new_text__S023_002_DoD14(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-14 / US-111.AC-2 — the following call is a miss that sends the **new** text as the
    user message."""

    def hook() -> None:
        _set_message_text(engine, PARTNER_A, EDITED_TEXT)

    _translate(engine, generator, FakeFactory(_two_deltas(hook=hook)))

    second_client = FakeChatClient([_content(FRENCH_TEXT)])
    second = _translate(engine, generator, FakeFactory(second_client))

    assert second.cached is False
    assert len(second_client.calls) == 1
    assert second_client.calls[0].messages[1].content == EDITED_TEXT
    assert _pairs(engine) == [(PARTNER_A, "Russian", FRENCH_TEXT)]


# ====================================================================== DoD-15
# US-047.AC-1 / R8 — a translation never reaches context.


def test_a_cached_translation_does_not_change_the_assembled_context__S023_002_DoD15(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-15 / US-047.AC-1 / R8 — 020's `assemble_context` for the session gives an equal
    result before and after a successful translation is cached, and the translated text appears
    in neither."""
    with engine.connect() as connection:
        before = assemble_context(connection, USER_A, SESSION_A)

    result = _translate(engine, generator, FakeFactory(_two_deltas()))
    assert result.cached is False
    assert len(_translation_rows(engine)) == 1

    with engine.connect() as connection:
        after = assemble_context(connection, USER_A, SESSION_A)

    assert after == before
    for assembled in (before, after):
        assert JOINED not in assembled.system_prompt
        for message in assembled.messages:
            assert JOINED not in message.content


# ====================================================================== DoD-16
# R8 / D3 — source conventions.


def test_the_translation_service_imports_no_fastapi__S023_002_DoD16() -> None:
    """DoD-16 — `services/translation.py` imports no `fastapi`. Asserted AST-wise, because the
    module's docstring mentions `fastapi` in prose (`## Skeleton`, step 002)."""
    offenders = [
        module
        for module in _imported_modules(translation_module)
        if module == "fastapi" or module.startswith("fastapi.")
    ]
    assert offenders == []


@pytest.mark.parametrize(
    "module",
    [pytest.param(context_module, id="context"), pytest.param(compose_module, id="compose")],
)
def test_no_context_feeding_module_imports_the_translation_service__S023_002_DoD16(
    module: ModuleType,
) -> None:
    """DoD-16 / R8 — neither `services/context.py` nor `services/compose.py` imports
    `app.services.translation`."""
    assert _imports_the_translation_service(module) is False


@pytest.mark.parametrize(
    "module",
    [pytest.param(context_module, id="context"), pytest.param(compose_module, id="compose")],
)
def test_no_context_feeding_module_names_the_translations_table__S023_002_DoD16(
    module: ModuleType,
) -> None:
    """DoD-16 / R8 — neither source contains the substring `translations`."""
    assert "translations" not in _module_source(module)


def test_the_fallback_target_language_is_english__S023_002_DoD16() -> None:
    """DoD-16 / D3 — the module constant's value is the literal "English"."""
    assert FALLBACK_TARGET_LANGUAGE == "English"


# ====================================================================== DoD-17
# deployment.md's redaction rule — ids, booleans, codes and durations; never text.


def test_a_miss_logs_cached_false_with_the_id_and_a_duration__S023_002_DoD17(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-17 — a miss logs one line containing `translate cached=false message=<id>` and `ms=`."""
    client = FakeChatClient([_content(PARTNER_A2_TRANSLATION)])

    with _captured_logs() as records:
        _translate(engine, generator, FakeFactory(client), message_id=PARTNER_A2)

    expected = f"translate cached=false message={PARTNER_A2}"
    matched = [record for record in records if expected in record]
    assert len(matched) == 1
    assert "ms=" in matched[0]


def test_a_hit_logs_cached_true_with_the_id__S023_002_DoD17(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-17 — a cache hit logs a line containing `translate cached=true message=<id>`."""
    _translate(
        engine,
        generator,
        FakeFactory(FakeChatClient([_content(PARTNER_A2_TRANSLATION)])),
        message_id=PARTNER_A2,
    )

    with _captured_logs() as records:
        result = _translate(engine, generator, FakeFactory(_two_deltas()), message_id=PARTNER_A2)

    assert result.cached is True
    expected = f"translate cached=true message={PARTNER_A2}"
    assert len([record for record in records if expected in record]) == 1


def test_a_failure_logs_its_code_with_the_id_and_a_duration__S023_002_DoD17(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-17 / `002.context.md` "Logging" — the failure path logs
    `translate failed message=<id> code=translation_failed` and a duration."""
    with _captured_logs() as records:
        with pytest.raises(TranslationFailedError):
            _translate(
                engine,
                generator,
                FakeFactory(FakeChatClient([LlmUnreachableError("down")])),
                message_id=PARTNER_A2,
            )

    expected = f"translate failed message={PARTNER_A2} code=translation_failed"
    matched = [record for record in records if expected in record]
    assert len(matched) == 1
    assert "ms=" in matched[0]


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("miss", id="miss"),
        pytest.param("hit", id="hit"),
        pytest.param("failure", id="failure"),
    ],
)
def test_no_log_record_carries_the_source_or_translated_text__S023_002_DoD17(
    engine: Engine, generator: SnowflakeGenerator, path: str
) -> None:
    """DoD-17 — on the miss, hit and failure paths alike (DoD-1 / 2 / 7), no record contains the
    source text or the translated text. Both carry distinctive markers."""
    with _captured_logs() as records:
        if path == "failure":
            with pytest.raises(TranslationFailedError):
                _translate(
                    engine,
                    generator,
                    FakeFactory(FakeChatClient([LlmUnreachableError("down")])),
                    message_id=PARTNER_A2,
                )
        else:
            _translate(
                engine,
                generator,
                FakeFactory(FakeChatClient([_content(PARTNER_A2_TRANSLATION)])),
                message_id=PARTNER_A2,
            )
            if path == "hit":
                _translate(engine, generator, FakeFactory(_two_deltas()), message_id=PARTNER_A2)

    assert records != []
    for record in records:
        assert SOURCE_MARKER not in record
        assert TRANSLATED_MARKER not in record
        assert PARTNER_A2_TEXT not in record
        assert PARTNER_A2_TRANSLATION not in record


# ====================================================================== DoD-18
# D8 — no connection, and no lock, is held across the model call.


def test_another_writer_can_commit_during_the_model_call__S023_002_DoD18(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-18 / D8 — inside the fake's `chat_stream`, a write transaction on a separate
    connection (an insert into an unrelated table) commits without a "database is locked"
    error, and the translation itself still completes."""
    failures: list[BaseException] = []

    def hook() -> None:
        try:
            _insert_character(
                engine, character_id=LOCK_PROBE_CHARACTER, user_id=USER_A, name="lock probe"
            )
        except BaseException as error:
            failures.append(error)

    client = _two_deltas(hook=hook)

    result = _translate(engine, generator, FakeFactory(client))

    assert [str(failure) for failure in failures] == []
    assert "lock probe" in _character_names(engine)
    assert (result.text, result.cached) == (JOINED, False)
    assert _pairs(engine) == [(PARTNER_A, "Russian", JOINED)]
