"""The shared two-user audit world for feature 032 — privacy-isolation-audit.

Written by step 002's test-coder against
``docs/plans/032.privacy-isolation-audit/002.audit-world-and-route-guard.md`` (Interface
intent), ``002.context.md`` (coverage list, sentinel fields, guard mechanics) and
``context.md`` (the 74-row enumeration, the class table, the shared vocabulary). Every
signature here is the one frozen by ``status.md`` ``## Skeleton`` -> "Step 002 — frozen
interface"; steps 003..007 bind to that record, so nothing here may be renamed or
re-shaped without amending it.

**Not a test module.** The name does not match ``test_*``, so pytest never collects it.
Steps 003..007 import it as ``from tests.privacy_audit_support import ...``.

Safety contract — read before touching the seam
===============================================

``install_fake_model_seam`` replaces **all four** dependency seams of
``FAKE_SEAM_OVERRIDE_KEYS`` or none. A half-installed seam lets the real
``app.services.llm.client.LlmClient`` run, which in a privacy audit means a real network
request to the operator's configured server. ``audit_world`` calls it **exactly once**;
**no later step may set any of those four keys itself** — re-script through
``world.fakes.chat_factory.script_*``, ``world.fakes.translation_factory.script_*``,
``world.fakes.web_recorder.script`` and ``world.fakes.use_embedding_factory``.

``backend/tests/llm_fakes.py`` is embedding-only and is **not modified**: this module
imports from it and adds the chat, probe and web fakes beside it, consolidating the
file-local copies in ``test_compose_route.py``, ``test_compose_source.py`` and
``test_translation_router.py``.

Nothing here was derived from reading an implementation body.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator, Callable, Iterable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Final, Literal

import httpx
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from loguru import logger
from sqlalchemy import Engine

import app.main as app_main
from app.config import Settings, get_settings
from app.dependencies import get_llm_client_factory
from app.models.memos import MemoScope
from app.routers.stream import get_chat_client_factory, get_tool_registry
from app.routers.translation import get_translation_chat_client_factory
from app.services.llm.chat import ChatMessage
from app.services.llm.client import ChatDelta, ProbeOutcome, ProbeResult, ToolCallDelta
from app.services.llm_registry import LlmClientFactory
from app.services.memo_chain import MemoReach
from app.services.tools.memo_search import MemoSearchTool
from app.services.tools.seam import ToolRegistry
from app.services.tools.session_search import SessionSearchTool
from app.services.tools.web_search import WebSearchTool
from app.services.web_search.google import GoogleCustomSearchProvider
from app.services.web_search.provider import WebResult
from tests.llm_fakes import FAKE_EMBEDDING_DIM, vectors_for

# --------------------------------------------------------------------------------------
# 1. Module constants
# --------------------------------------------------------------------------------------

#: A well-formed snowflake that exists nowhere (``context.md`` "Unknown id").
UNKNOWN_ID: Final[str] = "7250000000000000002"

#: The substitution for the ``{table_name}`` path parameter (``002.context.md``).
EXISTING_TABLE_NAME: Final[str] = "characters"

#: The three built tool names (``app/services/tools/definitions.py``).
MEMO_SEARCH_NAME: Final[str] = "memo_search"
SESSION_SEARCH_NAME: Final[str] = "session_search"
WEB_SEARCH_NAME: Final[str] = "web_search"

#: The four dependency callables ``install_fake_model_seam`` replaces, in this order.
#: Missing any one lets the real ``LlmClient`` run (orchestrator decision 7).
FAKE_SEAM_OVERRIDE_KEYS: Final[tuple[Callable[..., Any], ...]] = (
    get_llm_client_factory,
    get_chat_client_factory,
    get_translation_chat_client_factory,
    get_tool_registry,
)

#: The base URL the one seeded LLM server row carries. Never reached: all four seams are faked.
FAKE_SERVER_BASE_URL: Final[str] = "http://127.0.0.1:65535/v1"

#: Administrative names. No sentinel is a substring of any of them, because every
#: sentinel begins ``sntl`` and none of these contains that token (DoD-6).
FAKE_SERVER_NAME: Final[str] = "audit registry server"
FAKE_CHAT_MODEL_NAME: Final[str] = "audit-chat-model"
FAKE_EMBEDDING_MODEL_NAME: Final[str] = "audit-embedding-model"

#: The four real derived-store table names. There is no ``session_fts``.
DERIVED_STORE_TABLES: Final[tuple[str, ...]] = ("memo_vec", "session_vec", "memo_fts", "message_fts")

#: Every stdlib logger whose ``level``, ``handlers``, ``propagate`` **and** ``filters``
#: the log-capture managers snapshot and restore (orchestrator decision 9).
RESTORED_LOGGER_NAMES: Final[tuple[str, ...]] = (
    "",
    "uvicorn",
    "uvicorn.access",
    "uvicorn.error",
    "sqlalchemy",
    "sqlalchemy.engine",
    "httpx",
)

LOGIN_PATH: Final[str] = "/api/auth/login"
BOOTSTRAP_PATH: Final[str] = "/api/bootstrap/create"
ADMIN_USERS_PATH: Final[str] = "/api/admin/users"
ADMIN_SERVERS_PATH: Final[str] = "/api/admin/llm-servers"

#: How long the world waits for one compose exchange. The SSE POST runs on a worker
#: thread, following ``test_compose_route.py``'s precedent.
COMPOSE_TIMEOUT_SECONDS: Final[float] = 30.0


# --------------------------------------------------------------------------------------
# 2. Identities and clients
# --------------------------------------------------------------------------------------

AuditUser = Literal["A", "B", "ADM"]


@dataclass(frozen=True)
class AuditIdentity:
    """One account of the audit world. ``username`` is administrative: never a sentinel."""

    label: AuditUser
    user_id: str
    username: str
    password: str


@dataclass(frozen=True)
class AuditClients:
    """One cookie-authenticated client per identity, plus anon, over one application."""

    a: TestClient
    b: TestClient
    adm: TestClient
    anon: TestClient

    def of(self, user: AuditUser) -> TestClient:
        """The client of ``user``; ``anon`` has no label and is reached as ``clients.anon``."""
        if user == "A":
            return self.a
        if user == "B":
            return self.b
        if user == "ADM":
            return self.adm
        raise KeyError(f"unknown audit user {user!r}")


# --------------------------------------------------------------------------------------
# 3. Seeded content
# --------------------------------------------------------------------------------------

MEMO_SCOPES: Final[tuple[MemoScope, ...]] = ("user", "character", "setup", "session")
MEMO_REACHES: Final[tuple[MemoReach, ...]] = ("forced", "searchable", "disabled")


@dataclass(frozen=True)
class SeededMessages:
    """Every message row the world seeds for one user, by the kind the plan names."""

    partner_id: str
    zone_id: str
    turn_head_id: str
    buried_ids: tuple[str, ...]
    decision_id: str
    assistant_id: str
    tool_id: str

    def all_ids(self) -> tuple[str, ...]:
        return (
            self.partner_id,
            self.zone_id,
            self.turn_head_id,
            *self.buried_ids,
            self.decision_id,
            self.assistant_id,
            self.tool_id,
        )


@dataclass(frozen=True)
class SeededMemos:
    """All twelve scope x reach memos of one user, plus the level put in a non-default order."""

    ids: Mapping[tuple[MemoScope, MemoReach], str]
    reordered_scope: MemoScope
    reordered_ids: tuple[str, ...]

    def of(self, scope: MemoScope, reach: MemoReach) -> str:
        return self.ids[(scope, reach)]

    def all_ids(self) -> tuple[str, ...]:
        return tuple(self.ids[key] for key in sorted(self.ids))


@dataclass(frozen=True)
class SeededUserContent:
    """Every row id the world seeded for one roleplayer."""

    identity: AuditIdentity
    character_id: str
    setup_id: str
    session_with_setup_id: str
    session_without_setup_id: str
    archived_session_id: str
    messages: SeededMessages
    memos: SeededMemos
    translated_message_id: str
    translation_target_language: str

    def all_ids(self) -> tuple[str, ...]:
        return (
            self.identity.user_id,
            self.character_id,
            self.setup_id,
            *self.all_session_ids(),
            *self.messages.all_ids(),
            *self.memos.all_ids(),
        )

    def all_session_ids(self) -> tuple[str, ...]:
        return (self.session_with_setup_id, self.session_without_setup_id, self.archived_session_id)


@dataclass(frozen=True)
class SeededModels:
    """The one registry server and its two model names. Administrative: no sentinel."""

    server_id: str
    server_name: str
    chat_model_name: str
    embedding_model_name: str


# --------------------------------------------------------------------------------------
# 4. Sentinel registry
# --------------------------------------------------------------------------------------

SentinelKey = tuple[AuditUser, str, str]


@dataclass(frozen=True)
class SentinelCarrier:
    """One (table, field) that carries a sentinel, seeded once for each of A and B."""

    table: str
    field: str
    stored: bool
    note: str


#: ``(table, field, tag, stored, note)`` for every carrier that is not a memo. ``tag`` is
#: this module's 10-character identifier for the carrier; the sentinel is
#: ``"sntl" + user letter + tag`` padded to one fixed width, which is what makes DoD-6's
#: "none is a substring of another" **structural**: every sentinel has the same length and
#: they are all distinct, and equal-length distinct strings cannot contain one another.
_CARRIER_ROWS: Final[tuple[tuple[str, str, str, bool, str], ...]] = (
    ("characters", "name", "charname", True, ""),
    ("characters", "sheet", "charsheet", True, "the persona text"),
    (
        "characters",
        "system_prompt",
        "charprompt",
        True,
        "character configuration is columns on characters, not a table",
    ),
    ("setups", "name", "setupname", True, "002.context.md's 'setup title'"),
    ("setups", "description", "setupdesc", True, "002.context.md's 'setup text'"),
    (
        "sessions",
        "system_prompt",
        "sessprompt",
        True,
        "schema.sessions has no content text column: no title, no partner_label",
    ),
    ("users", "rp_language", "rplang", True, "user settings are two columns on users"),
    ("users", "preferred_language", "preflang", True, "second user-settings column"),
    ("messages", "text[partner]", "msgpartner", True, "the pasted partner block, born settled"),
    ("messages", "text[zone]", "msgzone", True, "the current-zone roleplayer message"),
    ("messages", "text[turn]", "msgturn", True, "the settled turn head"),
    ("messages", "text[buried]", "msgburied", True, "a row buried under the turn head"),
    ("messages", "text[decision]", "msgdecide", True, "the settled decision"),
    ("messages", "text[assistant]", "msgassist", True, "written by compose from the scripted completion"),
    (
        "messages",
        "tool_payload[arguments]",
        "toolquery",
        True,
        "the scripted tool call's query — the tool-call-query sentinel",
    ),
    (
        "messages",
        "tool_payload[content]",
        "toolresult",
        True,
        "the tool-result text: planted in the searchable session-scope memo the tool finds",
    ),
    ("translations", "text", "transtext", True, ""),
    (
        "memo_vec",
        "embedded_text",
        "memovec",
        False,
        "binary vector; witnessed by row presence or a memo_fts MATCH, never by substring",
    ),
    (
        "session_vec",
        "embedded_text",
        "sessvec",
        False,
        "binary vector; witnessed by row presence, never by substring",
    ),
)

_MEMO_SCOPE_LETTER: Final[Mapping[str, str]] = {"user": "u", "character": "c", "setup": "p", "session": "s"}
_MEMO_REACH_LETTER: Final[Mapping[str, str]] = {"forced": "f", "searchable": "r", "disabled": "d"}

_SENTINEL_PREFIX: Final[str] = "sntl"
_SENTINEL_TAG_WIDTH: Final[int] = 10
_SENTINEL_PAD: Final[str] = "x"


def memo_carrier_field(scope: MemoScope, reach: MemoReach) -> str:
    """The ``SentinelKey`` field component of one memo carrier: ``body[<scope>/<reach>]``."""
    return f"body[{scope}/{reach}]"


def _build_carriers() -> tuple[tuple[SentinelCarrier, ...], Mapping[tuple[str, str], str]]:
    carriers: list[SentinelCarrier] = []
    tags: dict[tuple[str, str], str] = {}
    for table, carrier_field, tag, stored, note in _CARRIER_ROWS:
        carriers.append(SentinelCarrier(table=table, field=carrier_field, stored=stored, note=note))
        tags[(table, carrier_field)] = tag
    for scope in MEMO_SCOPES:
        for reach in MEMO_REACHES:
            carrier_field = memo_carrier_field(scope, reach)
            carriers.append(
                SentinelCarrier(
                    table="memos",
                    field=carrier_field,
                    stored=True,
                    note="memos has no title column: body alone carries the sentinel",
                )
            )
            tags[("memos", carrier_field)] = f"memo{_MEMO_SCOPE_LETTER[scope]}{_MEMO_REACH_LETTER[reach]}"
    return tuple(carriers), tags


SENTINEL_CARRIERS, _CARRIER_TAGS = _build_carriers()


def sentinel_for(user: AuditUser, table: str, carrier_field: str) -> str:
    """``sntl`` + the user letter + the padded carrier tag — one lowercase alphanumeric token.

    Single token with no space, hyphen or punctuation, so FTS5 tokenizes it as one term
    (``context.md`` "Sentinel"). Every sentinel is the same length.
    """
    tag = _CARRIER_TAGS[(table, carrier_field)]
    padded = tag.ljust(_SENTINEL_TAG_WIDTH, _SENTINEL_PAD)[:_SENTINEL_TAG_WIDTH]
    return f"{_SENTINEL_PREFIX}{user.lower()}{padded}"


class SentinelRegistry:
    """(user, table, field) -> sentinel, with the reverse lookup the sweeps need."""

    def __init__(self) -> None:
        self._by_key: dict[SentinelKey, str] = {}
        self._owner: dict[str, AuditUser] = {}

    def register(self, *, user: AuditUser, table: str, field: str, sentinel: str) -> str:
        key: SentinelKey = (user, table, field)
        if key in self._by_key:
            raise AssertionError(f"sentinel key already registered: {key}")
        if sentinel in self._owner:
            raise AssertionError(f"sentinel {sentinel!r} is already registered to {self._owner[sentinel]}")
        self._by_key[key] = sentinel
        self._owner[sentinel] = user
        return sentinel

    def get(self, *, user: AuditUser, table: str, field: str) -> str:
        return self._by_key[(user, table, field)]

    def of_user(self, user: AuditUser) -> tuple[str, ...]:
        return tuple(sentinel for (owner, _table, _field), sentinel in self._by_key.items() if owner == user)

    def all_sentinels(self) -> tuple[str, ...]:
        return tuple(self._by_key.values())

    def keys(self) -> tuple[SentinelKey, ...]:
        return tuple(self._by_key)

    def carriers_of_user(self, user: AuditUser) -> tuple[SentinelCarrier, ...]:
        owned = {(table, carrier_field) for (owner, table, carrier_field) in self._by_key if owner == user}
        return tuple(carrier for carrier in SENTINEL_CARRIERS if (carrier.table, carrier.field) in owned)

    def owner_of(self, sentinel: str) -> AuditUser:
        return self._owner[sentinel]


# --------------------------------------------------------------------------------------
# 5. The fake model seam — one atomic installation (decision 7)
# --------------------------------------------------------------------------------------

ChatRound = Sequence[ChatDelta | BaseException]


@dataclass(frozen=True)
class ChatCall:
    """What one ``chat_stream`` call was asked, recorded at call time."""

    model: str
    messages: tuple[ChatMessage, ...]
    tools: tuple[Mapping[str, object], ...]


def text_round(text: str) -> ChatRound:
    """One completion round carrying ``text`` as a single content delta."""
    return (ChatDelta(content=text),)


def tool_call_round(*, name: str, arguments: str, call_id: str | None = None, index: int = 0) -> ChatRound:
    """One round carrying a single whole tool call with caller-chosen ``arguments``."""
    return (ChatDelta(tool_calls=(ToolCallDelta(index=index, call_id=call_id, name=name, arguments=arguments),)),)


def failure_round(error: BaseException) -> ChatRound:
    """One round that raises ``error`` — the caller chooses both class and message."""
    return (error,)


class FakeChatClient:
    """A scripted ``ChatClientLike``: replays rounds and records what it was asked."""

    def __init__(self, rounds: Sequence[ChatRound] = (), *, on_enter: Callable[[], None] | None = None) -> None:
        self._rounds: list[tuple[ChatDelta | BaseException, ...]] = [tuple(one) for one in rounds]
        self._on_enter = on_enter
        self._index = 0
        self.calls: list[ChatCall] = []

    def chat_stream(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        tools: Sequence[Mapping[str, object]],
    ) -> AsyncIterator[ChatDelta]:
        self.calls.append(ChatCall(model=model, messages=tuple(messages), tools=tuple(dict(one) for one in tools)))
        index = self._index
        self._index += 1
        if index >= len(self._rounds):
            raise AssertionError(
                f"the fake chat client was called {index + 1} times but only "
                f"{len(self._rounds)} rounds were scripted"
            )
        items = self._rounds[index]
        on_enter = self._on_enter

        async def stream() -> AsyncIterator[ChatDelta]:
            if on_enter is not None:
                on_enter()
            for item in items:
                if isinstance(item, BaseException):
                    raise item
                yield item

        return stream()


class FakeChatClientFactory:
    """A ``ChatClientFactory`` recording every construction and every call."""

    def __init__(self, *, rounds: Sequence[ChatRound] = ()) -> None:
        self._rounds: tuple[ChatRound, ...] = tuple(rounds)
        self.calls: list[tuple[str, str | None, float]] = []
        self.clients: list[FakeChatClient] = []

    def __call__(self, base_url: str, api_key: str | None, timeout_seconds: float) -> FakeChatClient:
        self.calls.append((base_url, api_key, timeout_seconds))
        client = FakeChatClient(self._rounds)
        self.clients.append(client)
        return client

    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def chat_calls(self) -> list[ChatCall]:
        """Every ``ChatCall`` of every client it built, in order."""
        return [call for client in self.clients for call in client.calls]

    def script(self, *rounds: ChatRound) -> None:
        """Replace the script. Clients built from now on replay it; nothing recorded is cleared."""
        self._rounds = tuple(rounds)

    def script_text(self, text: str) -> None:
        """One completion round carrying ``text``, then end of exchange."""
        self.script(text_round(text))

    def script_tool_call(
        self,
        *,
        name: str,
        arguments: str,
        call_id: str | None = None,
        then_text: str | None = None,
    ) -> None:
        """One tool-call round with caller-chosen ``arguments``, then ``then_text`` or nothing."""
        rounds: list[ChatRound] = [tool_call_round(name=name, arguments=arguments, call_id=call_id)]
        rounds.append(text_round(then_text) if then_text is not None else ())
        self.script(*rounds)

    def script_failure(self, error: BaseException) -> None:
        """Raise ``error`` from the first round — caller-chosen class **and** message (decision 12)."""
        self.script(failure_round(error))


class ScriptedProbeClient:
    """An ``LlmClientLike`` whose probe and embed can both be scripted to fail.

    ``llm_fakes.FakeEmbeddingClient`` always probes REACHABLE; step 007 needs a probe that
    fails, so the failable variant lives here.
    """

    def __init__(
        self,
        *,
        dim: int = FAKE_EMBEDDING_DIM,
        probe_result: ProbeResult | None = None,
        probe_error: BaseException | None = None,
        embed_error: BaseException | None = None,
    ) -> None:
        self.dim = dim
        self.probe_result = probe_result
        self.probe_error = probe_error
        self.embed_error = embed_error
        self.embed_calls: list[tuple[str, tuple[str, ...]]] = []
        self.probe_calls = 0

    async def probe(self) -> ProbeResult:
        self.probe_calls += 1
        if self.probe_error is not None:
            raise self.probe_error
        if self.probe_result is not None:
            return self.probe_result
        return ProbeResult(
            outcome=ProbeOutcome.REACHABLE,
            model_names=(FAKE_CHAT_MODEL_NAME, FAKE_EMBEDDING_MODEL_NAME),
        )

    async def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
        self.embed_calls.append((model, tuple(texts)))
        if self.embed_error is not None:
            raise self.embed_error
        return vectors_for(list(texts), self.dim)


class ScriptedProbeFactory:
    """An ``LlmClientFactory`` over ``ScriptedProbeClient``, recording every construction."""

    def __init__(
        self,
        *,
        dim: int = FAKE_EMBEDDING_DIM,
        probe_result: ProbeResult | None = None,
        probe_error: BaseException | None = None,
        embed_error: BaseException | None = None,
    ) -> None:
        self.dim = dim
        self.probe_result = probe_result
        self.probe_error = probe_error
        self.embed_error = embed_error
        self.calls: list[tuple[str, str | None, float]] = []
        self.clients: list[ScriptedProbeClient] = []

    def __call__(self, base_url: str, api_key: str | None, timeout_seconds: float) -> ScriptedProbeClient:
        self.calls.append((base_url, api_key, timeout_seconds))
        client = ScriptedProbeClient(
            dim=self.dim,
            probe_result=self.probe_result,
            probe_error=self.probe_error,
            embed_error=self.embed_error,
        )
        self.clients.append(client)
        return client

    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def embed_calls(self) -> list[tuple[str, tuple[str, ...]]]:
        return [call for client in self.clients for call in client.embed_calls]

    @property
    def probe_calls(self) -> int:
        return sum(client.probe_calls for client in self.clients)


class WebSearchRecorder:
    """The ``httpx.MockTransport`` seam of ``GoogleCustomSearchProvider``.

    The provider takes its HTTP transport as a constructor argument, so this is the only
    place a web search can be captured. The body it answers is the Google Custom Search
    JSON shape (``items[].title`` / ``.link`` / ``.snippet``).
    """

    def __init__(
        self,
        *,
        results: Sequence[WebResult] = (),
        status_code: int = 200,
        error: BaseException | None = None,
    ) -> None:
        self.requests: list[httpx.Request] = []
        self._results: tuple[WebResult, ...] = tuple(results)
        self._status_code = status_code
        self._error = error

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        items = [{"title": one.title, "link": one.url, "snippet": one.snippet} for one in self._results]
        return httpx.Response(self._status_code, json={"items": items}, request=request)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    @property
    def queries(self) -> list[str]:
        """The ``q`` parameter of every recorded request, in order."""
        return [one.url.params.get("q", "") for one in self.requests]

    def script(self, *results: WebResult) -> None:
        self._results = tuple(results)


@dataclass
class FakeModelSeam:
    """The four installed fakes, and the only way later steps re-script them."""

    application: FastAPI
    embedding_factory: LlmClientFactory
    chat_factory: FakeChatClientFactory
    translation_factory: FakeChatClientFactory
    tool_registry: ToolRegistry
    web_recorder: WebSearchRecorder

    def use_embedding_factory(self, factory: LlmClientFactory) -> None:
        """Re-point the live override (and the tool adapters, which delegate through it)."""
        self.embedding_factory = factory

    def override_keys(self) -> tuple[Callable[..., Any], ...]:
        return FAKE_SEAM_OVERRIDE_KEYS

    def reset_records(self) -> None:
        """Clear every recorded call and request; keep every script."""
        for factory in (self.chat_factory, self.translation_factory):
            factory.calls.clear()
            factory.clients.clear()
        self.web_recorder.requests.clear()
        calls = getattr(self.embedding_factory, "calls", None)
        if isinstance(calls, list):
            calls.clear()
        clients = getattr(self.embedding_factory, "clients", None)
        if isinstance(clients, list):
            clients.clear()


@contextmanager
def install_fake_model_seam(
    application: FastAPI,
    settings: Settings,
    *,
    embedding_dim: int = FAKE_EMBEDDING_DIM,
    tool_names: Sequence[str] = (MEMO_SEARCH_NAME, SESSION_SEARCH_NAME, WEB_SEARCH_NAME),
) -> Iterator[FakeModelSeam]:
    """Install **all four** model seams, or none, and remove exactly those four on exit.

    The production memo and session tool adapters take their client factory by constructor
    injection and the web adapter takes the whole provider, so the tool registry must be
    rebuilt here rather than left alone. ``conftest.py`` blanks ``SEARCH_CSE_KEY`` and
    ``SEARCH_CSE_ID``, so the production registry would omit ``web_search`` entirely — the
    override is mandatory, not optional.
    """
    overrides = application.dependency_overrides
    already = [key for key in FAKE_SEAM_OVERRIDE_KEYS if key in overrides]
    if already:
        raise AssertionError(
            "the fake model seam is installed exactly once; these keys are already overridden: "
            f"{[getattr(key, '__name__', repr(key)) for key in already]}"
        )

    seam = FakeModelSeam(
        application=application,
        embedding_factory=ScriptedProbeFactory(dim=embedding_dim),
        chat_factory=FakeChatClientFactory(),
        translation_factory=FakeChatClientFactory(),
        tool_registry={},
        web_recorder=WebSearchRecorder(),
    )

    def delegating_embedding_factory(base_url: str, api_key: str | None, timeout_seconds: float) -> Any:
        # Reads ``seam.embedding_factory`` at call time, so ``use_embedding_factory``
        # re-points the tool adapters too.
        return seam.embedding_factory(base_url, api_key, timeout_seconds)

    timeout_seconds = settings.llm_request_timeout_seconds
    built: dict[str, Any] = {
        MEMO_SEARCH_NAME: MemoSearchTool(
            client_factory=delegating_embedding_factory, timeout_seconds=timeout_seconds
        ),
        SESSION_SEARCH_NAME: SessionSearchTool(
            client_factory=delegating_embedding_factory, timeout_seconds=timeout_seconds
        ),
        WEB_SEARCH_NAME: WebSearchTool(
            GoogleCustomSearchProvider(
                "audit-dummy-key",
                "audit-dummy-engine",
                transport=seam.web_recorder.transport,
            )
        ),
    }
    seam.tool_registry = {name: tool for name, tool in built.items() if name in tuple(tool_names)}

    overrides[get_llm_client_factory] = lambda: seam.embedding_factory
    overrides[get_chat_client_factory] = lambda: seam.chat_factory
    overrides[get_translation_chat_client_factory] = lambda: seam.translation_factory
    overrides[get_tool_registry] = lambda: seam.tool_registry
    try:
        yield seam
    finally:
        for key in FAKE_SEAM_OVERRIDE_KEYS:
            overrides.pop(key, None)


# --------------------------------------------------------------------------------------
# 6. Assertions
# --------------------------------------------------------------------------------------


def assert_envelope(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    """The typed error envelope, returned so ``assert_empty_detail`` reads as one line."""
    assert response.status_code == status, response.text
    body = response.json()
    assert isinstance(body, dict), response.text
    assert set(body) == {"error"}, body
    error = body["error"]
    assert isinstance(error, dict), body
    assert error["code"] == code, body
    return body


def assert_empty_detail(body: Mapping[str, Any]) -> None:
    """``detail == {}``: nothing about the refused row is distinguishable."""
    assert body["error"]["detail"] == {}, body


def assert_refusal_identity(
    foreign: httpx.Response,
    unknown: httpx.Response,
    *,
    status: int,
    code: str,
) -> None:
    """``context.md`` "refusal identity": same status, same code, empty detail, identical body."""
    foreign_body = assert_envelope(foreign, status, code)
    unknown_body = assert_envelope(unknown, status, code)
    assert_empty_detail(foreign_body)
    assert_empty_detail(unknown_body)
    assert foreign_body == unknown_body, (foreign_body, unknown_body)
    assert foreign.content == unknown.content, (foreign.content, unknown.content)


def rendered_text(payload: object) -> str:
    """The one string the absence assertions search, whatever shape the payload has."""
    if isinstance(payload, httpx.Response):
        return payload.text
    if isinstance(payload, str):
        return payload
    if isinstance(payload, bytes | bytearray):
        return bytes(payload).decode("utf-8", errors="replace")
    return json.dumps(payload, default=str, ensure_ascii=False)


def assert_no_sentinel_of_user(
    payload: object,
    *,
    registry: SentinelRegistry,
    user: AuditUser,
    allowed: Iterable[str] = (),
) -> None:
    """No sentinel of ``user`` appears in ``payload``.

    ``allowed`` is the documented carve-out channel and the only one; every use carries a
    comment naming the DoD clause and the decision that permits it.
    """
    text = rendered_text(payload)
    permitted = set(allowed)
    found = sorted(one for one in registry.of_user(user) if one not in permitted and one in text)
    assert not found, f"sentinels of {user} present: {found}"


def assert_no_identifier_of(
    payload: object,
    *,
    content: SeededUserContent,
    allowed: Iterable[str] = (),
) -> None:
    """No seeded id of ``content``'s owner appears in ``payload``."""
    text = rendered_text(payload)
    permitted = set(allowed)
    found = sorted(one for one in content.all_ids() if one not in permitted and one in text)
    assert not found, f"identifiers of {content.identity.label} present: {found}"


# --------------------------------------------------------------------------------------
# 7. Log capture (decision 9)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CapturedRecord:
    """One loguru record, in the four pieces the redaction sweep needs."""

    level: str
    name: str | None
    message: str
    formatted: str
    extra_repr: str
    exception_text: str | None


@dataclass
class LogCapture:
    """Every record emitted while the capture block ran."""

    records: list[CapturedRecord]

    @property
    def texts(self) -> list[str]:
        """Every string of every record, flattened."""
        out: list[str] = []
        for record in self.records:
            out.extend([record.message, record.formatted, record.extra_repr])
            if record.exception_text is not None:
                out.append(record.exception_text)
        return out

    def joined(self) -> str:
        return "\n".join(self.texts)


def _logger_snapshot(logger_names: Sequence[str]) -> list[tuple[logging.Logger, int, list[Any], bool, list[Any]]]:
    return [
        (
            logging.getLogger(name),
            logging.getLogger(name).level,
            list(logging.getLogger(name).handlers),
            logging.getLogger(name).propagate,
            list(logging.getLogger(name).filters),
        )
        for name in logger_names
    ]


def _logger_restore(snapshot: Sequence[tuple[logging.Logger, int, list[Any], bool, list[Any]]]) -> None:
    for stdlib_logger, level, handlers, propagate, filters in snapshot:
        stdlib_logger.setLevel(level)
        stdlib_logger.handlers[:] = handlers
        stdlib_logger.propagate = propagate
        stdlib_logger.filters[:] = filters


@contextmanager
def restored_logging_state(*, logger_names: Sequence[str] = RESTORED_LOGGER_NAMES) -> Iterator[None]:
    """Snapshot and restore ``level``, ``handlers``, ``propagate`` **and** ``filters``.

    Nothing in the delivered suite restores ``.filters``, and ``app/main.py`` runs
    ``create_app()`` at import, so the real ``configure_logging`` has already mutated
    global state before any fixture runs.
    """
    snapshot = _logger_snapshot(logger_names)
    try:
        yield
    finally:
        _logger_restore(snapshot)


@contextmanager
def captured_logs(
    *,
    logger_names: Sequence[str] = RESTORED_LOGGER_NAMES,
    restore_stdlib: bool = True,
) -> Iterator[LogCapture]:
    """A level-0 loguru sink collecting every record, removed by id on exit.

    ``restore_stdlib=False`` is for a caller already inside ``restored_logging_state``.
    """
    capture = LogCapture(records=[])

    def sink(message: Any) -> None:
        record = message.record
        exception = record["exception"]
        capture.records.append(
            CapturedRecord(
                level=str(record["level"].name),
                name=record["name"],
                message=str(record["message"]),
                formatted=str(message),
                extra_repr=repr(record["extra"]),
                exception_text=None if exception is None else repr(exception.value),
            )
        )

    snapshot = _logger_snapshot(logger_names) if restore_stdlib else None
    handler_id = logger.add(sink, level=0, format="{level} {name} {message}")
    try:
        yield capture
    finally:
        logger.remove(handler_id)
        if snapshot is not None:
            _logger_restore(snapshot)


# --------------------------------------------------------------------------------------
# 8. The enumeration literal, the route walk, and the unbuilt-surface guard
# --------------------------------------------------------------------------------------

RouteClass = Literal["public", "self", "registry", "owner", "admin"]


@dataclass(frozen=True)
class EnumeratedRoute:
    """One row of ``context.md``'s enumeration table, as data."""

    row: int
    method: str
    path: str
    route_class: RouteClass
    not_found_code: str | None

    def key(self) -> tuple[str, str]:
        return (self.method, self.path)


#: Rows 5 and 74 are excluded **by name, with the reason inline** (orientation decision 1):
#: they belong to ``fast/003`` (bootstrap from export) and ``fast/002`` (vector rebuild),
#: which hold only a ``brief.md``, so neither feature is planned and no route exists. They
#: are never silently dropped and DoD-1 is never loosened to a subset check;
#: ``UNBUILT_SURFACES`` arms the absence instead.
EXCLUDED_ROWS: Final[Mapping[int, str]] = {
    5: (
        "fast/003 bootstrap-from-export: the folder holds only brief.md, so the feature is "
        "unplanned and unbuilt and no method or path may be invented. Absence armed by "
        "UNBUILT_SURFACES row 5."
    ),
    74: (
        "fast/002 vector-index-rebuild: the folder holds only brief.md, so the feature is "
        "unplanned and unbuilt and no method or path may be invented. Absence armed by "
        "UNBUILT_SURFACES row 74."
    ),
}

#: The enumeration of ``context.md``, with every ``†`` method taken from the step 002
#: skeleton record (calling interface only; the class and outcome stay the plan's).
ENUMERATED_ROUTES: Final[tuple[EnumeratedRoute, ...]] = (
    EnumeratedRoute(1, "GET", "/api/health", "public", None),
    EnumeratedRoute(2, "POST", "/api/bootstrap/create", "public", None),
    EnumeratedRoute(3, "POST", "/api/auth/login", "public", None),
    EnumeratedRoute(4, "POST", "/api/auth/logout", "public", None),
    EnumeratedRoute(6, "GET", "/api/me", "self", None),
    EnumeratedRoute(7, "GET", "/api/me/settings", "self", None),
    EnumeratedRoute(8, "PATCH", "/api/me/settings", "self", None),
    EnumeratedRoute(9, "GET", "/api/models", "registry", None),
    EnumeratedRoute(10, "GET", "/api/characters", "self", None),
    EnumeratedRoute(11, "POST", "/api/characters", "self", None),
    EnumeratedRoute(12, "GET", "/api/sessions", "self", None),
    EnumeratedRoute(13, "GET", "/api/memos", "self", None),
    EnumeratedRoute(14, "POST", "/api/memos", "self", None),
    EnumeratedRoute(15, "PUT", "/api/memos/order", "self", None),
    EnumeratedRoute(16, "GET", "/api/search", "self", None),
    EnumeratedRoute(17, "GET", "/api/export", "self", None),
    EnumeratedRoute(18, "POST", "/api/import", "self", None),
    EnumeratedRoute(19, "GET", "/api/characters/{}", "owner", "character_not_found"),
    EnumeratedRoute(20, "PATCH", "/api/characters/{}", "owner", "character_not_found"),
    EnumeratedRoute(21, "POST", "/api/characters/{}/archive", "owner", "character_not_found"),
    EnumeratedRoute(22, "POST", "/api/characters/{}/restore", "owner", "character_not_found"),
    EnumeratedRoute(23, "GET", "/api/characters/{}/setups", "owner", "character_not_found"),
    EnumeratedRoute(24, "POST", "/api/characters/{}/setups", "owner", "character_not_found"),
    EnumeratedRoute(25, "GET", "/api/setups/{}", "owner", "setup_not_found"),
    EnumeratedRoute(26, "PATCH", "/api/setups/{}", "owner", "setup_not_found"),
    EnumeratedRoute(27, "POST", "/api/setups/{}/archive", "owner", "setup_not_found"),
    EnumeratedRoute(28, "POST", "/api/setups/{}/restore", "owner", "setup_not_found"),
    EnumeratedRoute(29, "GET", "/api/characters/{}/sessions", "owner", "character_not_found"),
    EnumeratedRoute(30, "POST", "/api/characters/{}/sessions", "owner", "character_not_found"),
    EnumeratedRoute(31, "GET", "/api/sessions/{}", "owner", "session_not_found"),
    EnumeratedRoute(32, "POST", "/api/sessions/{}/archive", "owner", "session_not_found"),
    EnumeratedRoute(33, "POST", "/api/sessions/{}/restore", "owner", "session_not_found"),
    EnumeratedRoute(34, "GET", "/api/sessions/{}/entries", "owner", "session_not_found"),
    EnumeratedRoute(35, "POST", "/api/sessions/{}/entries", "owner", "session_not_found"),
    EnumeratedRoute(36, "GET", "/api/sessions/{}/zone", "owner", "session_not_found"),
    EnumeratedRoute(37, "POST", "/api/sessions/{}/zone/messages", "owner", "session_not_found"),
    EnumeratedRoute(38, "POST", "/api/sessions/{}/zone/compose", "owner", "session_not_found"),
    EnumeratedRoute(39, "POST", "/api/sessions/{}/settle", "owner", "session_not_found"),
    EnumeratedRoute(40, "POST", "/api/sessions/{}/reopen", "owner", "session_not_found"),
    EnumeratedRoute(41, "GET", "/api/sessions/{}/memo-chain", "owner", "session_not_found"),
    EnumeratedRoute(42, "GET", "/api/sessions/{}/configuration", "owner", "session_not_found"),
    EnumeratedRoute(43, "PATCH", "/api/sessions/{}/configuration", "owner", "session_not_found"),
    EnumeratedRoute(44, "GET", "/api/sessions/{}/export", "owner", "session_not_found"),
    EnumeratedRoute(45, "PATCH", "/api/messages/{}", "owner", "message_not_found"),
    EnumeratedRoute(46, "GET", "/api/messages/{}/discussion", "owner", "message_not_found"),
    # Row 47's 404 code is the generic ``message_not_found`` (decision 6).
    EnumeratedRoute(47, "POST", "/api/messages/{}/translation", "owner", "message_not_found"),
    EnumeratedRoute(48, "PATCH", "/api/memos/{}", "owner", "memo_not_found"),
    EnumeratedRoute(49, "DELETE", "/api/memos/{}", "owner", "memo_not_found"),
    EnumeratedRoute(50, "GET", "/api/characters/{}/configuration", "owner", "character_not_found"),
    EnumeratedRoute(51, "PATCH", "/api/characters/{}/configuration", "owner", "character_not_found"),
    EnumeratedRoute(52, "GET", "/api/characters/{}/export", "owner", "character_not_found"),
    EnumeratedRoute(53, "POST", "/api/characters/{}/import", "owner", "character_not_found"),
    EnumeratedRoute(54, "GET", "/api/admin/users", "admin", None),
    EnumeratedRoute(55, "POST", "/api/admin/users", "admin", None),
    EnumeratedRoute(56, "POST", "/api/admin/users/{}/disable", "admin", None),
    EnumeratedRoute(57, "POST", "/api/admin/users/{}/enable", "admin", None),
    EnumeratedRoute(58, "POST", "/api/admin/users/{}/password", "admin", None),
    EnumeratedRoute(59, "POST", "/api/admin/users/{}/role", "admin", None),
    EnumeratedRoute(60, "GET", "/api/admin/llm-servers", "admin", None),
    EnumeratedRoute(61, "POST", "/api/admin/llm-servers", "admin", None),
    EnumeratedRoute(62, "PATCH", "/api/admin/llm-servers/{}", "admin", None),
    EnumeratedRoute(63, "DELETE", "/api/admin/llm-servers/{}", "admin", None),
    EnumeratedRoute(64, "POST", "/api/admin/llm-servers/{}/test", "admin", None),
    EnumeratedRoute(65, "GET", "/api/admin/llm-servers/{}/available-models", "admin", None),
    EnumeratedRoute(66, "POST", "/api/admin/llm-servers/{}/models", "admin", None),
    EnumeratedRoute(67, "POST", "/api/admin/llm-servers/{}/embedding-model", "admin", None),
    EnumeratedRoute(68, "DELETE", "/api/admin/llm-servers/{}/embedding-model", "admin", None),
    EnumeratedRoute(69, "GET", "/api/admin/database/tables", "admin", None),
    EnumeratedRoute(70, "POST", "/api/admin/database/tables/{}/create", "admin", None),
    EnumeratedRoute(71, "POST", "/api/admin/database/tables/{}/sync", "admin", None),
    EnumeratedRoute(72, "GET", "/api/admin/database/export", "admin", None),
    EnumeratedRoute(73, "POST", "/api/admin/database/import", "admin", None),
)

ENUMERATED_OPERATIONS: Final[frozenset[tuple[str, str]]] = frozenset(
    route.key() for route in ENUMERATED_ROUTES
)


@dataclass(frozen=True)
class UnbuiltSurface:
    """A surface the enumeration names but no built feature delivers yet."""

    row: int
    description: str
    path_pattern: str
    allowed_paths: frozenset[str]


#: One entry per excluded row. The pattern is matched case-insensitively with
#: ``re.search`` against each **normalized** registered path; every matching path must be
#: in ``allowed_paths``. Row 5's pattern deliberately cannot match the three built
#: ``.../restore`` routes (it requires ``restore`` followed by ``from``), and row 74's
#: cannot match ``/api/admin/llm-servers/{}/embedding-model``.
UNBUILT_SURFACES: Final[tuple[UnbuiltSurface, ...]] = (
    UnbuiltSurface(
        row=5,
        description="fast/003 bootstrap-from-export (public, swept by 005) — unplanned, unbuilt",
        path_pattern=r"bootstrap|from[-_]?export|restore[-_]?from",
        allowed_paths=frozenset({"/api/bootstrap/create"}),
    ),
    UnbuiltSurface(
        row=74,
        description="fast/002 vector-index rebuild (admin, swept by 006) — unplanned, unbuilt",
        path_pattern=r"rebuild|re-?index|vector",
        allowed_paths=frozenset(),
    ),
)

_PARAMETER = re.compile(r"\{[^{}]*\}")


def _collect_api_routes(routes: Any, found: list[APIRoute], seen: set[int]) -> None:
    """The delivered in-suite recursive walk (``test_search_router.py``,
    ``test_configuration_router.py``): depth-first through the router wrappers."""
    for route in routes or ():
        if id(route) in seen:
            continue
        seen.add(id(route))
        if isinstance(route, APIRoute):
            found.append(route)
            continue
        _collect_api_routes(getattr(route, "routes", None), found, seen)
        for holder in ("router", "original_router"):
            nested = getattr(route, holder, None)
            if nested is not None:
                _collect_api_routes(getattr(nested, "routes", None), found, seen)


def api_routes(application: FastAPI) -> tuple[APIRoute, ...]:
    """Every ``APIRoute`` of the application, found by the recursive walk.

    Under the installed FastAPI, ``app.routes`` holds **no** ``APIRoute`` — documentation
    ``Route`` objects plus router wrappers — so a flat ``isinstance`` filter would compare
    an empty set against the enumeration and pass against nothing. This raises when the
    walk finds nothing: an inventory guard that can silently iterate an empty set is worse
    than none.
    """
    found: list[APIRoute] = []
    _collect_api_routes(application.routes, found, set())
    if not found:
        raise AssertionError("the walk found no API routes at all")
    return tuple(found)


def normalize_path(path: str) -> str:
    """Rewrite every ``{param}`` / ``{param:type}`` segment to ``{}``."""
    return _PARAMETER.sub("{}", path)


def route_operations(application: FastAPI) -> frozenset[tuple[str, str]]:
    """``(METHOD, normalized path)`` for every API route and method, ``HEAD`` excluded."""
    operations = {
        (method.upper(), normalize_path(route.path))
        for route in api_routes(application)
        for method in (route.methods or ())
        if method.upper() != "HEAD"
    }
    if not operations:
        raise AssertionError("the walk found no API operations at all")
    return frozenset(operations)


def registered_paths_by_operation(application: FastAPI) -> Mapping[tuple[str, str], str]:
    """``(METHOD, normalized path) -> the registered path``, for parameter substitution."""
    return {
        (method.upper(), normalize_path(route.path)): route.path
        for route in api_routes(application)
        for method in (route.methods or ())
        if method.upper() != "HEAD"
    }


def fill_path(path: str, *, unknown_id: str = UNKNOWN_ID, table_name: str = EXISTING_TABLE_NAME) -> str:
    """Substitute into the **registered** path: the unknown id everywhere but ``{table_name}``."""

    def replace(match: re.Match[str]) -> str:
        name = match.group(0)[1:-1].split(":", 1)[0]
        return table_name if name == "table_name" else unknown_id

    return _PARAMETER.sub(replace, path)


# --------------------------------------------------------------------------------------
# 9. The world builder
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditWorld:
    """The seeded two-user world every sweep of steps 003..007 runs inside."""

    settings: Settings
    engine: Engine
    application: FastAPI
    clients: AuditClients
    adm: AuditIdentity
    a: SeededUserContent
    b: SeededUserContent
    models: SeededModels
    sentinels: SentinelRegistry
    fakes: FakeModelSeam

    def content_of(self, user: AuditUser) -> SeededUserContent:
        if user == "A":
            return self.a
        if user == "B":
            return self.b
        raise KeyError("ADM owns no content")

    def identity_of(self, user: AuditUser) -> AuditIdentity:
        if user == "ADM":
            return self.adm
        return self.content_of(user).identity


_ADM_USERNAME: Final[str] = "auditfounder"
_ADM_PASSWORD: Final[str] = "founder-pass-032"
_USERNAMES: Final[Mapping[str, str]] = {"A": "auditaster", "B": "auditbriar"}
_PASSWORDS: Final[Mapping[str, str]] = {"A": "aster-pass-032", "B": "briar-pass-032"}


def _no_op_configure_logging(_settings: Settings) -> None:
    """The no-op the 28 delivered router-test modules monkeypatch in. Step 007 opts out."""
    return None


def _parse_set_cookie(header: str) -> tuple[str, str]:
    first = header.split(";")[0]
    name, _, value = first.partition("=")
    return name.strip(), value.strip().strip('"')


def _login_token(application: FastAPI, settings: Settings, username: str, password: str) -> str:
    response = TestClient(application).post(LOGIN_PATH, json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    tokens = [
        value
        for name, value in (_parse_set_cookie(header) for header in response.headers.get_list("set-cookie"))
        if name == settings.session_cookie_name
    ]
    assert len(tokens) == 1, response.headers.get_list("set-cookie")
    assert tokens[0]
    return tokens[0]


def _as(application: FastAPI, settings: Settings, username: str, password: str) -> TestClient:
    """A fresh client carrying only this identity's cookie, so cookies never cross users."""
    client = TestClient(application)
    client.cookies.set(settings.session_cookie_name, _login_token(application, settings, username, password))
    return client


def _ok(response: httpx.Response, status: int) -> Any:
    assert response.status_code == status, f"{response.request.method} {response.request.url}: {response.text}"
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def _frames(body: str) -> list[dict[str, Any]]:
    """Parse an SSE body into its ``data:`` frames."""
    frames: list[dict[str, Any]] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("data:"):
            frames.append(json.loads(stripped.removeprefix("data:").strip()))
    return frames


def _compose(client: TestClient, session_id: str, text: str) -> list[dict[str, Any]]:
    """One compose exchange, posted on a worker thread with a bound (compose streams SSE)."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            client.post, f"/api/sessions/{session_id}/zone/compose", json={"text": text}
        )
        response = future.result(timeout=COMPOSE_TIMEOUT_SECONDS)
    assert response.status_code == 200, response.text
    frames = _frames(response.text)
    errors = [frame for frame in frames if frame.get("event") == "error"]
    assert not errors, errors
    return frames


def _seed_models(adm: TestClient) -> SeededModels:
    """Enable both models, then designate the embedding model (decision 13's order)."""
    server = _ok(
        adm.post(
            ADMIN_SERVERS_PATH,
            json={"name": FAKE_SERVER_NAME, "kind": "llamaswap", "base_url": FAKE_SERVER_BASE_URL},
        ),
        201,
    )
    server_id = str(server["id"])
    enabled = _ok(
        adm.post(
            f"{ADMIN_SERVERS_PATH}/{server_id}/models",
            json={"model_names": [FAKE_CHAT_MODEL_NAME, FAKE_EMBEDDING_MODEL_NAME]},
        ),
        200,
    )
    assert set(enabled["enabled_model_names"]) == {FAKE_CHAT_MODEL_NAME, FAKE_EMBEDDING_MODEL_NAME}, enabled
    designated = _ok(
        adm.post(
            f"{ADMIN_SERVERS_PATH}/{server_id}/embedding-model",
            json={"model_name": FAKE_EMBEDDING_MODEL_NAME},
        ),
        200,
    )
    assert designated["embedding_model_name"] == FAKE_EMBEDDING_MODEL_NAME, designated
    return SeededModels(
        server_id=server_id,
        server_name=FAKE_SERVER_NAME,
        chat_model_name=FAKE_CHAT_MODEL_NAME,
        embedding_model_name=FAKE_EMBEDDING_MODEL_NAME,
    )


def _seed_user_content(
    *,
    client: TestClient,
    identity: AuditIdentity,
    user: AuditUser,
    registry: SentinelRegistry,
    models: SeededModels,
    fakes: FakeModelSeam,
) -> SeededUserContent:
    """Seed every coverage-list table for one roleplayer, each field carrying its sentinel."""

    def mark(table: str, carrier_field: str) -> str:
        return registry.register(
            user=user,
            table=table,
            field=carrier_field,
            sentinel=sentinel_for(user, table, carrier_field),
        )

    # user settings — before the translation, because the target language is read from them.
    rp_language = mark("users", "rp_language")
    preferred_language = mark("users", "preferred_language")
    settings_body = _ok(
        client.patch(
            "/api/me/settings",
            json={"rp_language": rp_language, "preferred_language": preferred_language},
        ),
        200,
    )
    assert settings_body == {"rp_language": rp_language, "preferred_language": preferred_language}, settings_body

    # character, character configuration (the model pair, so every session captures it).
    character = _ok(
        client.post(
            "/api/characters",
            json={
                "name": f"audit character {mark('characters', 'name')}",
                "sheet": f"audit persona {mark('characters', 'sheet')}",
            },
        ),
        201,
    )
    character_id = str(character["id"])
    _ok(
        client.patch(
            f"/api/characters/{character_id}/configuration",
            json={
                "model": {"server_id": models.server_id, "model_name": models.chat_model_name},
                "system_prompt": f"audit character prompt {mark('characters', 'system_prompt')}",
            },
        ),
        200,
    )

    # setup.
    setup = _ok(
        client.post(
            f"/api/characters/{character_id}/setups",
            json={
                "name": f"audit setup {mark('setups', 'name')}",
                "description": f"audit setup text {mark('setups', 'description')}",
            },
        ),
        201,
    )
    setup_id = str(setup["id"])

    # sessions: one with a setup, one without, one to archive last.
    with_setup = _ok(
        client.post(f"/api/characters/{character_id}/sessions", json={"setup_id": setup_id}), 201
    )
    session_with_setup_id = str(with_setup["id"])
    without_setup = _ok(client.post(f"/api/characters/{character_id}/sessions", json={}), 201)
    session_without_setup_id = str(without_setup["id"])
    to_archive = _ok(client.post(f"/api/characters/{character_id}/sessions", json={}), 201)
    archived_session_id = str(to_archive["id"])

    _ok(
        client.patch(
            f"/api/sessions/{session_with_setup_id}/configuration",
            json={"system_prompt": f"audit session prompt {mark('sessions', 'system_prompt')}"},
        ),
        200,
    )

    # memos: the twelve scope x reach combinations. Seeded **before** compose, so the
    # scripted memo_search call has a searchable chain memo to find and the tool-result
    # sentinel really reaches ``messages.tool_payload``.
    memo_vec_sentinel = mark("memo_vec", "embedded_text")
    tool_result_sentinel = mark("messages", "tool_payload[content]")
    scope_ids: Mapping[str, str | None] = {
        "user": None,
        "character": character_id,
        "setup": setup_id,
        "session": session_with_setup_id,
    }
    memo_ids: dict[tuple[MemoScope, MemoReach], str] = {}
    for scope in MEMO_SCOPES:
        for reach in MEMO_REACHES:
            carrier_field = memo_carrier_field(scope, reach)
            body_parts = [f"memo {mark('memos', carrier_field)}"]
            if scope == "user" and reach == "searchable":
                body_parts.append(memo_vec_sentinel)
            if scope == "session" and reach == "searchable":
                body_parts.append(tool_result_sentinel)
            payload: dict[str, Any] = {"scope": scope, "body": " ".join(body_parts)}
            scope_id = scope_ids[scope]
            if scope_id is not None:
                payload["scope_id"] = scope_id
            created = _ok(client.post("/api/memos", json=payload), 201)
            memo_id = str(created["id"])
            memo_ids[(scope, reach)] = memo_id
            if reach == "forced":
                _ok(client.patch(f"/api/memos/{memo_id}", json={"is_forced": True}), 200)
            elif reach == "disabled":
                _ok(client.patch(f"/api/memos/{memo_id}", json={"is_enabled": False}), 200)

    # a non-default order at one level. The default is newest-first, so the order below is
    # compared against the level as listed *before* the reorder and must differ from it.
    reordered_scope: MemoScope = "character"
    before = _ok(client.get(f"/api/memos?scope={reordered_scope}&scope_id={character_id}"), 200)
    default_order = [str(one["id"]) for one in before["memos"]]
    reordered_ids = tuple(memo_ids[(reordered_scope, reach)] for reach in MEMO_REACHES)
    assert set(reordered_ids) == set(default_order), (reordered_ids, default_order)
    assert list(reordered_ids) != default_order, "the seeded memo order must differ from the default"
    reordered = _ok(
        client.put(
            "/api/memos/order",
            json={
                "scope": reordered_scope,
                "scope_id": character_id,
                "memo_ids": list(reordered_ids),
            },
        ),
        200,
    )
    assert [str(one["id"]) for one in reordered["memos"]] == list(reordered_ids), reordered

    # messages. The pasted partner block also carries the session_vec sentinel: the
    # composed session text is persona + setup description + settled entries.
    partner = _ok(
        client.post(
            f"/api/sessions/{session_with_setup_id}/entries",
            json={
                "kind": "partner",
                "text": (
                    f"audit partner block {mark('messages', 'text[partner]')} "
                    f"{mark('session_vec', 'embedded_text')}"
                ),
            },
        ),
        201,
    )
    partner_id = str(partner["id"])
    assert partner["search_coverage_incomplete"] is False, partner

    buried = _ok(
        client.post(
            f"/api/sessions/{session_with_setup_id}/zone/messages",
            json={"text": f"audit buried line {mark('messages', 'text[buried]')}"},
        ),
        201,
    )
    buried_first_id = str(buried["id"])

    # the compose exchange: one scripted tool call, then the assistant completion.
    tool_query = mark("messages", "tool_payload[arguments]")
    assistant_sentinel = mark("messages", "text[assistant]")
    fakes.chat_factory.script_tool_call(
        name=MEMO_SEARCH_NAME,
        arguments=json.dumps({"query": tool_query}),
        call_id=f"audit-call-{user.lower()}",
        then_text=f"audit assistant reply {assistant_sentinel}",
    )
    frames = _compose(client, session_with_setup_id, "audit compose prompt")
    done = [frame for frame in frames if frame.get("event") == "done"]
    assert len(done) == 1, frames
    assistant_id = str(done[0]["message_id"])

    zone_rows = _ok(client.get(f"/api/sessions/{session_with_setup_id}/zone"), 200)["messages"]
    tool_rows = [row for row in zone_rows if row["role"] == "tool"]
    assert len(tool_rows) == 1, zone_rows
    tool_id = str(tool_rows[0]["id"])

    # the settled turn: the last non-tool zone row becomes the head, everything else is buried.
    turn = _ok(
        client.post(
            f"/api/sessions/{session_with_setup_id}/zone/messages",
            json={"text": f"audit my turn {mark('messages', 'text[turn]')}"},
        ),
        201,
    )
    turn_zone_id = str(turn["id"])
    settled = _ok(client.post(f"/api/sessions/{session_with_setup_id}/settle", json=None), 200)
    assert settled["kind"] == "turn", settled
    assert str(settled["entry_id"]) == turn_zone_id, settled
    assert settled["search_coverage_incomplete"] is False, settled
    turn_head_id = str(settled["entry_id"])
    buried_ids = tuple(str(one) for one in settled["buried_ids"])
    assert buried_first_id in buried_ids, settled
    assert assistant_id in buried_ids, settled
    assert tool_id in buried_ids, settled

    # the decision: a zone row wrapped in double parentheses, settled on its own.
    _ok(
        client.post(
            f"/api/sessions/{session_with_setup_id}/zone/messages",
            json={"text": f"(({mark('messages', 'text[decision]')}))"},
        ),
        201,
    )
    decided = _ok(client.post(f"/api/sessions/{session_with_setup_id}/settle", json=None), 200)
    assert decided["kind"] == "decision", decided
    decision_id = str(decided["entry_id"])

    # the current-zone roleplayer message, left unsettled in the zone.
    zone = _ok(
        client.post(
            f"/api/sessions/{session_with_setup_id}/zone/messages",
            json={"text": f"audit zone line {mark('messages', 'text[zone]')}"},
        ),
        201,
    )
    zone_id = str(zone["id"])

    # the translation of the settled partner block.
    translation_sentinel = mark("translations", "text")
    fakes.translation_factory.script_text(f"audit translation {translation_sentinel}")
    translated = _ok(client.post(f"/api/messages/{partner_id}/translation", json=None), 200)
    assert translation_sentinel in translated["text"], translated
    assert translated["cached"] is False, translated
    translation_target_language = str(translated["target_language"])

    # the archived session, archived last.
    _ok(client.post(f"/api/sessions/{archived_session_id}/archive", json=None), 200)

    return SeededUserContent(
        identity=identity,
        character_id=character_id,
        setup_id=setup_id,
        session_with_setup_id=session_with_setup_id,
        session_without_setup_id=session_without_setup_id,
        archived_session_id=archived_session_id,
        messages=SeededMessages(
            partner_id=partner_id,
            zone_id=zone_id,
            turn_head_id=turn_head_id,
            buried_ids=buried_ids,
            decision_id=decision_id,
            assistant_id=assistant_id,
            tool_id=tool_id,
        ),
        memos=SeededMemos(
            ids=memo_ids,
            reordered_scope=reordered_scope,
            reordered_ids=reordered_ids,
        ),
        translated_message_id=partner_id,
        translation_target_language=translation_target_language,
    )


@contextmanager
def audit_world(
    settings: Settings,
    engine: Engine,
    *,
    real_logging: bool = False,
    embedding_dim: int = FAKE_EMBEDDING_DIM,
) -> Iterator[AuditWorld]:
    """Build the whole audit world: the real application, ADM, A, B and all their content.

    ``real_logging`` is the caller's choice: ``False`` replaces ``app.main.configure_logging``
    with a no-op for the duration of the ``create_app()`` call, exactly as the delivered
    router-test modules do; ``True`` lets the real one run, which is what step 007 needs.

    Seeding runs **only through routes** — nothing is ever raw-inserted into a user-content
    table — in the order the built validation forces (decision 13), with the memo block
    moved ahead of the compose exchange so the scripted tool call has something to find.
    """
    original_configure = app_main.configure_logging
    if not real_logging:
        app_main.configure_logging = _no_op_configure_logging
    try:
        application = app_main.create_app()
    finally:
        app_main.configure_logging = original_configure

    application.dependency_overrides[get_settings] = lambda: settings
    try:
        with install_fake_model_seam(application, settings, embedding_dim=embedding_dim) as fakes:
            # 1. bootstrap ADM (this also creates the schema and the FTS tables), log in.
            bootstrapped = _ok(
                TestClient(application).post(
                    BOOTSTRAP_PATH, json={"username": _ADM_USERNAME, "password": _ADM_PASSWORD}
                ),
                201,
            )
            adm_identity = AuditIdentity(
                label="ADM",
                user_id=str(bootstrapped["id"]),
                username=_ADM_USERNAME,
                password=_ADM_PASSWORD,
            )
            adm_client = _as(application, settings, _ADM_USERNAME, _ADM_PASSWORD)

            # 2-3. enable both models, then designate the embedding model.
            models = _seed_models(adm_client)

            # 4-5. create the roleplayers and seed their content.
            registry = SentinelRegistry()
            identities: dict[str, AuditIdentity] = {}
            player_clients: dict[str, TestClient] = {}
            for label in ("A", "B"):
                created = _ok(
                    adm_client.post(
                        ADMIN_USERS_PATH,
                        json={
                            "username": _USERNAMES[label],
                            "password": _PASSWORDS[label],
                            "role": "roleplayer",
                        },
                    ),
                    201,
                )
                identities[label] = AuditIdentity(
                    label=label,
                    user_id=str(created["id"]),
                    username=_USERNAMES[label],
                    password=_PASSWORDS[label],
                )
                player_clients[label] = _as(
                    application, settings, _USERNAMES[label], _PASSWORDS[label]
                )

            content: dict[str, SeededUserContent] = {}
            for label in ("A", "B"):
                content[label] = _seed_user_content(
                    client=player_clients[label],
                    identity=identities[label],
                    user=label,
                    registry=registry,
                    models=models,
                    fakes=fakes,
                )

            clients = AuditClients(
                a=player_clients["A"],
                b=player_clients["B"],
                adm=adm_client,
                anon=TestClient(application),
            )
            yield AuditWorld(
                settings=settings,
                engine=engine,
                application=application,
                clients=clients,
                adm=adm_identity,
                a=content["A"],
                b=content["B"],
                models=models,
                sentinels=registry,
                fakes=fakes,
            )
    finally:
        application.dependency_overrides.clear()
