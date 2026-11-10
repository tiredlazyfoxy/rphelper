"""The LLM gateway — the one module that knows the `llm-client` library.

Feature `035`. Holds the probe-outcome value set (`ProbeOutcome`, `ProbeResult`,
`EMBED_NO_VECTOR_REASON`), the compose-stream values (`ComposeText`, `ComposeRejected`,
`ComposeRejectionKind`, `ComposeTools`) and
`LlmGateway`, which selects a library client class by server `kind` and answers
RPHelper's operations through it. Library typing gaps are
absorbed here and nowhere else (DEC-035-5).
"""

import asyncio
import inspect
import itertools
import json
import sys
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final, cast

from llm import LlamaSwapAPIClient, LLMClient, LLMError, OpenAIAPIClient, ToolEvent

from app.errors import LlmUnreachableError
from app.services.llm.chat import ChatMessage, ToolCall, to_wire_message


class ProbeOutcome(StrEnum):
    """The closed four-value probe taxonomy — declared here and nowhere else."""

    REACHABLE = "reachable"
    UNREACHABLE = "unreachable"
    AUTH_FAILED = "auth_failed"
    MODEL_LIST_EMPTY = "model_list_empty"


EMBED_NO_VECTOR_REASON: Final = "no_usable_vector"
"""`LlmUnreachableError.detail["reason"]` when an embeddings 2xx carries no usable vector."""


@dataclass(frozen=True)
class ProbeResult:
    """The typed result of one models-listing call.

    `model_names` is empty for every outcome but `REACHABLE`. `note` is a short
    provider-side diagnostic that no caller persists.
    """

    outcome: ProbeOutcome
    model_names: tuple[str, ...] = ()
    note: str | None = None


@dataclass(frozen=True)
class ComposeText:
    """One streamed text piece of a `compose` exchange, verbatim (DEC-035-6).

    `text` is exactly what the library handed to `on_delta` — `<think>` / `</think>`
    markers included, nothing added, removed or re-joined.
    """

    text: str


class ComposeRejectionKind(StrEnum):
    """The three model-side rejection kinds a `compose` stream reports (DEC-035-17).

    RPHelper's own spellings, not the library's `ToolErrorKind`, so no library type leaves
    this module (DEC-035-5). Only these three become a `ComposeRejected`; the library's
    `tool_raised` and `unserialisable_result` kinds never do (`DEC-arch-llm-client-library-15`).
    """

    NOT_OFFERED = "not_offered"
    """The model called a tool name that was not offered (`""` included)."""
    BAD_ARGUMENTS = "bad_arguments"
    """The model's argument text is unreadable or not a JSON object."""
    UNKNOWN_ARGUMENT = "unknown_argument"
    """The model passed an argument name the tool's declaration does not have."""


@dataclass(frozen=True)
class ComposeRejected:
    """One model-side tool rejection in a `compose` stream (DEC-035-17).

    The library refused the call before any tool callable ran, told the model so, and the
    exchange goes on. `call` carries the gateway-minted `call_<n>` (from the same
    per-`compose` counter the tool wrappers use; the provider's own call id is never used),
    the model's tool name verbatim (`""` kept) and the model's argument text verbatim (not a
    re-serialisation). `kind` says which check refused it. Nothing else from the library's
    tool event is carried — not its `output`, `call_id` or model-facing text.
    """

    call: ToolCall
    kind: ComposeRejectionKind


@dataclass(frozen=True)
class ComposeTools[E]:
    """The tools one `compose` call offers, and how to run one (DEC-035-6).

    `declarations` are the offered tool declarations, in offered order, in the nested
    `{"type": "function", "function": {"name", "description", "parameters": {...,
    "properties": {...}}}}` shape — typed structurally so the gateway imports nothing
    from the tool seam. They reach the library unchanged as `tools_definitions`; an
    empty sequence offers no tools (DEC-035-10).

    `runner` is the caller's half of the per-tool wrapper: it is awaited once per tool
    call with the gateway-built `ToolCall` and an `emit` callback, and returns the tool's
    output text, which goes back to the library as the tool result. `emit` is
    synchronous and non-blocking; each value passed to it is yielded by `compose`
    unchanged, in emit order, interleaved with `ComposeText` in the order things
    happened. `E` is the caller's own event type.
    """

    declarations: Sequence[Mapping[str, object]]
    runner: Callable[[ToolCall, Callable[[E], None]], Awaitable[str]]


DEFAULT_LIBRARY_CLIENTS: Final[Mapping[str, type[LLMClient]]] = MappingProxyType(
    {"openai": OpenAIAPIClient, "llamaswap": LlamaSwapAPIClient}
)
"""The production `kind` → library client class map (DEC-035-3); read-only."""


def _normalise_base_url(base_url: str) -> str:
    """Return `base_url` ending in exactly one `/v1` (DEC-035-11).

    Trailing `/` characters are stripped, then `/v1` is appended unless already present.
    Scheme, host, port and any other path are kept, so a mistyped path still reaches the
    server and shows up as `unreachable` rather than being silently rewritten.
    """
    stripped = base_url.rstrip("/")
    if stripped.endswith("/v1"):
        return stripped
    return f"{stripped}/v1"


def _is_auth_failure(exc: LLMError) -> bool:
    """Whether a library error is a 401/403 refusal (DEC-035-20, DEC-arch-llm-client-library-16).

    Reads the error's structured `status` only — never its message or `description` (which
    holds the provider's reply body). An error carrying no `status` is never an auth failure,
    whatever its message says. The one auth test behind all four operations.
    """
    return exc.status in (401, 403)


def _embed_unreachable(reason: str) -> LlmUnreachableError:
    """Build the one failure `embed` raises: a fixed RPHelper message and `{"reason": reason}`.

    The message never carries provider text (DEC-035-8); `reason` is one of RPHelper's own
    values (`auth_failed`, `unreachable`, `EMBED_NO_VECTOR_REASON`).
    """
    return LlmUnreachableError("The LLM server could not produce embeddings.", {"reason": reason})


def _chat_unreachable(reason: str) -> LlmUnreachableError:
    """Build the one failure `complete` and `compose` raise: a fixed message and `{"reason": reason}`.

    The message never carries provider text (DEC-035-8); `reason` is `auth_failed` or
    `unreachable`.
    """
    return LlmUnreachableError("The LLM server could not answer.", {"reason": reason})


def _chat_failure_reason(exc: BaseException) -> str:
    """Classify a library chat failure into `complete`/`compose`'s reason (DEC-035-8).

    An `LLMError` whose `status` is 401/403 is `auth_failed` (DEC-035-20); every other
    failure — another `LLMError`, a `RuntimeError` (a tool raised, the round limit), a
    `ValueError` (missing callable, a construction refusal) or any other exception — is
    `unreachable`. Only the `LLMError`'s `status` is read; nothing of the error is kept or
    logged.
    """
    if isinstance(exc, LLMError) and _is_auth_failure(exc):
        return ProbeOutcome.AUTH_FAILED.value
    return ProbeOutcome.UNREACHABLE.value


_REJECTION_KINDS: Final[Mapping[str, ComposeRejectionKind]] = MappingProxyType(
    {kind.value: kind for kind in ComposeRejectionKind}
)
"""Library `error_kind` spelling → the gateway's own kind, for the three rejection kinds only.

The library spells them identically; any other kind (`tool_raised`, `unserialisable_result`)
is absent and so ignored by the `compose` observer (DEC-035-17).
"""


class _Absent:
    """Type of `_ABSENT`, the default of every minted tool-callable parameter (DEC-035-6).

    A private marker rather than `None`, so an argument the model explicitly sent as JSON
    `null` stays distinguishable from one it did not send at all.
    """

    def __repr__(self) -> str:
        """Render as `<absent>` so a minted signature reads cleanly in a debugger."""
        return "<absent>"


_ABSENT: Final = _Absent()
"""Marks a declared tool argument the library did not pass; never reaches the runner."""


@dataclass(frozen=True)
class _EndOfStream:
    """The end marker the `compose` task's done-callback queues (DEC-035-7).

    `error` is the library task's exception, or `None` when it returned (or was cancelled —
    then nobody reads the queue any more).
    """

    error: BaseException | None


def _declaration_function(declaration: Mapping[str, object]) -> Mapping[str, object]:
    """Return the nested `function` object of one tool declaration.

    Raises:
        ValueError: the declaration has no `function` mapping — a malformed offer, which
            `compose` reports as `unreachable` like any other library-side refusal
            (DEC-035-16).
    """
    function = declaration.get("function")
    if not isinstance(function, Mapping):
        raise ValueError("tool declaration has no function object")
    return cast(Mapping[str, object], function)


def _declaration_name(declaration: Mapping[str, object]) -> str:
    """Return `function.name` of one tool declaration.

    Raises:
        ValueError: the name is missing or not a string.
    """
    name = _declaration_function(declaration).get("name")
    if not isinstance(name, str):
        raise ValueError("tool declaration has no name")
    return name


def _declaration_properties(declaration: Mapping[str, object]) -> list[str]:
    """Return the names in `function.parameters.properties`, in declared order.

    A declaration with no `parameters` or no `properties` takes no arguments.
    """
    parameters = _declaration_function(declaration).get("parameters")
    if not isinstance(parameters, Mapping):
        return []
    properties = parameters.get("properties")
    if not isinstance(properties, Mapping):
        return []
    return [str(key) for key in properties]


def _tool_callable(
    name: str,
    properties: Sequence[str],
    invoke: Callable[[str, dict[str, object]], Awaitable[str]],
) -> Callable[..., Awaitable[str]]:
    """Mint the library-facing callable for one offered tool (DEC-035-6).

    The callable's `inspect.signature` lists exactly `properties` as keyword-only parameters,
    each defaulting to `_ABSENT`: the library checks every model-sent argument name against
    that signature and refuses unknown names itself (DEC-arch-llm-client-library-6, DEC-035-19)
    — in tolerant mode that refusal reaches `compose`'s observer as an `unknown_argument`
    rejection, never this callable. On call it drops the absent arguments and awaits
    `invoke(name, present_kwargs)`, returning its text.

    Raises:
        ValueError: a property name is not a valid Python identifier (`inspect.Parameter`
            refuses it) — reported by `compose` as `unreachable`.
    """

    async def call(**kwargs: object) -> str:
        """Forward one library tool call with only the arguments the model actually sent."""
        present = {key: value for key, value in kwargs.items() if value is not _ABSENT}
        return await invoke(name, present)

    # The library reads `inspect.signature`, which honours `__signature__` over the real
    # `**kwargs` one; mypy does not know function objects carry this attribute.
    call.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        [inspect.Parameter(prop, inspect.Parameter.KEYWORD_ONLY, default=_ABSENT) for prop in properties]
    )
    return call


class LlmGateway:
    """One registered LLM server, reached through the `llm-client` library.

    The server's `kind` selects the library client class from `library_clients`; every
    library client is built through that mapping with the keyword arguments `model`,
    `base_url` (normalised to end in `/v1`), `timeout` and `bearer_token`, and is used as
    an async context manager for exactly one operation. Construction builds no library
    client and performs no I/O. No log line, exception message or result field carries
    the credential or a provider response body.
    """

    def __init__(
        self,
        kind: str,
        base_url: str,
        api_key: str | None,
        timeout_seconds: float,
        *,
        library_clients: Mapping[str, type[LLMClient]] = DEFAULT_LIBRARY_CLIENTS,
    ) -> None:
        """Remember the server's coordinates; build nothing.

        Args:
            kind: The server kind (`"openai"` or `"llamaswap"`); selects the library
                client class from `library_clients`. An unrecognised kind is not an
                error here — operations answer for it.
            base_url: The server's base URL, with or without a trailing `/` and `/v1`.
            api_key: The already-resolved credential, or `None` / `""` for none.
            timeout_seconds: The per-request timeout handed to the library as `timeout`.
            library_clients: Test seam (DEC-035-3) — `kind` → library client class.
                Production callers never pass it.
        """
        self._kind = kind
        self._base_url = _normalise_base_url(base_url)
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._library_clients = library_clients

    def _library_class(self) -> type[LLMClient] | None:
        """Return the library client class for this server's `kind`, or `None` if unrecognised.

        The `kind` column has no `CHECK`, so an unknown value is answered by the operations
        without building anything (DEC-035-8).
        """
        return self._library_clients.get(self._kind)

    def _missing_credential(self) -> bool:
        """Whether this server needs an api key it does not have.

        Only kind `"openai"` requires one: `OpenAIAPIClient` refuses a falsy `bearer_token`
        with `ValueError` at construction, which a generic catch would misreport as
        `unreachable`; checking first classifies it as `auth_failed`
        (DEC-arch-llm-client-library-9). A llama-swap server may run without a key.
        """
        return self._kind == "openai" and not self._api_key

    def _build_client(self, library_class: type[LLMClient], model: str) -> LLMClient:
        """Build one library client for `model` with this server's coordinates (DEC-035-3).

        No I/O: the library opens its session only on `async with` entry. An absent or empty
        key is passed as `None`, so a key-less llama-swap client sends no bearer header.
        """
        return library_class(
            model=model,
            base_url=self._base_url,
            timeout=self._timeout_seconds,
            bearer_token=self._api_key or None,
        )

    async def probe(self) -> ProbeResult:
        """List the server's models and classify the answer; never raises.

        Builds one library client with `model=""` and calls `list_models` inside one
        `async with`. Outcomes: `REACHABLE` with the names in library order;
        `MODEL_LIST_EMPTY` for an empty listing; `AUTH_FAILED` for a status 401/403
        failure, or for kind `"openai"` with no api key (checked before any client is
        built); `UNREACHABLE` for an unrecognised kind (no client built) and for every
        other failure, including non-`LLMError` exceptions. `note` is always `None`;
        no library message or description reaches the result or any log record.

        Returns:
            The classified `ProbeResult`.
        """
        library_class = self._library_class()
        if library_class is None:
            return ProbeResult(outcome=ProbeOutcome.UNREACHABLE)
        if self._missing_credential():
            return ProbeResult(outcome=ProbeOutcome.AUTH_FAILED)
        try:
            # DEC-035-9: listing never sends the model, so the required argument is empty.
            client = self._build_client(library_class, "")
            async with client:
                names = await client.list_models()
        except LLMError as exc:
            # Only the error's `status` is read (DEC-035-20); the message and description carry
            # provider text and are never logged or returned (DEC-035-8).
            if _is_auth_failure(exc):
                return ProbeResult(outcome=ProbeOutcome.AUTH_FAILED)
            return ProbeResult(outcome=ProbeOutcome.UNREACHABLE)
        except Exception:
            # DEC-035-8: probe never raises — a construction refusal, a transport error or a
            # library bug all read as `unreachable` to the administrator.
            return ProbeResult(outcome=ProbeOutcome.UNREACHABLE)
        if not names:
            return ProbeResult(outcome=ProbeOutcome.MODEL_LIST_EMPTY)
        return ProbeResult(outcome=ProbeOutcome.REACHABLE, model_names=tuple(names))

    async def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
        """Embed `texts` with `model`: one vector per text, in the texts' order.

        Builds exactly one library client with `model=model` and calls its `embed_batch`
        with the texts inside one `async with`, entered and exited once on success and on
        failure. For kind `"openai"` with no api key, raises before any client is built;
        an unrecognised kind also raises without building one.

        Args:
            model: The embedding model name, passed to the library client as `model`.
            texts: The texts to embed.

        Returns:
            The library's vectors, one `list[float]` per text, in order.

        Raises:
            LlmUnreachableError: `detail` `{"reason": "auth_failed"}` for a status 401/403
                failure or kind `"openai"` with no api key; `{"reason": EMBED_NO_VECTOR_REASON}`
                for a library `Invalid response …` failure; `{"reason": "unreachable"}` for an
                unrecognised kind and every other failure (DEC-035-8). The raised error has no
                `__cause__` and suppresses its context; no library message or description
                reaches its message, its `detail` or any log record.
        """
        library_class = self._library_class()
        # DEC-035-8: every `llm_unreachable` is raised `from None`, the up-front ones too, so
        # `__suppress_context__` is set uniformly whichever branch fails.
        if library_class is None:
            raise _embed_unreachable(ProbeOutcome.UNREACHABLE.value) from None
        if self._missing_credential():
            raise _embed_unreachable(ProbeOutcome.AUTH_FAILED.value) from None
        reason: str
        try:
            client = self._build_client(library_class, model)
            async with client:
                vectors = await client.embed_batch(list(texts))
        except LLMError as exc:
            # Only the error's `status` (DEC-035-20) and the message's `Invalid response` prefix
            # (kept per DEC-arch-llm-client-library-16) are read; neither the message nor the
            # description (provider text) is logged or carried onward (DEC-035-8).
            if _is_auth_failure(exc):
                reason = ProbeOutcome.AUTH_FAILED.value
            elif exc.message.startswith("Invalid response"):
                reason = EMBED_NO_VECTOR_REASON
            else:
                reason = ProbeOutcome.UNREACHABLE.value
        except Exception:
            # DEC-035-16: transport errors, construction refusals and library bugs — any other
            # exception out of the library — all read as `unreachable`.
            reason = ProbeOutcome.UNREACHABLE.value
        else:
            return [list(vector) for vector in vectors]
        # Raised outside the `except` blocks with `from None` so neither `__cause__` nor
        # `__context__` links the library error, whose text could surface in a formatted
        # traceback (DEC-035-8).
        raise _embed_unreachable(reason) from None

    async def complete(self, model: str, messages: Sequence[ChatMessage]) -> str:
        """Ask `model` for one whole, non-streamed answer to `messages` (DEC-035-4).

        Builds exactly one library client with `model=model` and calls its `chat`
        non-streamed inside one `async with`, with no `system` keyword and no options; the
        messages go as their `to_wire_message` forms, in order (a leading system message is
        the first item). For kind `"openai"` with no api key, raises before any client is
        built.

        Args:
            model: The chat model name, passed to the library client as `model`.
            messages: The conversation, oldest first.

        Returns:
            The library's answer text, unchanged.

        Raises:
            LlmUnreachableError: `detail` `{"reason": "auth_failed"}` for a status 401/403
                failure or kind `"openai"` with no api key; `{"reason": "unreachable"}` for
                any other exception from the library (DEC-035-8, DEC-035-16). The raised
                error has no `__cause__` and suppresses its context; no provider text
                reaches its message, its `detail` or any log record.
        """
        library_class = self._library_class()
        # DEC-035-8: the up-front refusals are raised `from None` too, so
        # `__suppress_context__` is set uniformly whichever branch fails.
        if library_class is None:
            raise _chat_unreachable(ProbeOutcome.UNREACHABLE.value) from None
        if self._missing_credential():
            raise _chat_unreachable(ProbeOutcome.AUTH_FAILED.value) from None
        # DEC-035-4: the leading system message stays a message item, so no `system=` keyword.
        wire = [to_wire_message(message) for message in messages]
        reason: str
        try:
            client = self._build_client(library_class, model)
            async with client:
                # DEC-035-5: still cast under 0.2.1 — `chat` takes `List[LLMMessage]` (a TypedDict),
                # so mypy rejects the `list[dict[str, object]]` wire dicts [arg-type]; they are that
                # shape at runtime.
                text = await client.chat(cast(Any, wire), stream=False)
        except Exception as exc:
            # DEC-035-16: every exception out of the library is caught, not only `LLMError`;
            # `_chat_failure_reason` keeps 401/403 as `auth_failed`, all else is `unreachable`.
            reason = _chat_failure_reason(exc)
        else:
            return text
        # Raised outside the `except` with `from None`: no `__cause__` / `__context__` links the
        # library error, whose text could surface in a formatted traceback (DEC-035-8).
        raise _chat_unreachable(reason) from None

    async def compose[E](
        self,
        model: str,
        messages: Sequence[ChatMessage],
        tools: ComposeTools[E],
    ) -> AsyncGenerator[ComposeText | ComposeRejected | E, None]:
        """Stream one compose exchange: text pieces, rejections and the runner's events, in order.

        An async generator (DEC-035-7). On first iteration it starts one task that builds
        exactly one library client with `model=model` and, inside one `async with`, awaits
        `chat_with_tools(stream=True, max_loops=sys.maxsize)` with the messages as their
        `to_wire_message` forms, `tools_definitions` equal to `tools.declarations` in order,
        one private callable per declaration name, no `system` keyword and no options.
        Every `on_delta` piece yields one `ComposeText`; every value the runner emits is
        yielded unchanged, in the order things happened. Each tool call reaches the runner
        as `ToolCall("call_<n>", name, json.dumps(present_kwargs, ensure_ascii=False))`,
        `<n>` counting from 1 per `compose` call; the runner's text is the tool result.
        The library's returned text is not yielded; the stream ends after the last queued
        event. Closing the generator (`aclose`) cancels the library task and awaits it, so
        the library client is exited before `aclose` returns.

        Args:
            model: The chat model name, passed to the library client as `model`.
            messages: The conversation, oldest first; replayed tool pairs included.
            tools: The offered declarations and the runner (`ComposeTools`).

        From step 006 (DEC-035-17, `DEC-arch-llm-client-library-14`, `-15`, `-17`), the
        `chat_with_tools` call also passes `tool_errors="result"` and a private synchronous
        `on_tool_event` observer, and nothing else (no silence limit, no trace switch). The
        observer turns each library `error` event of kind `not_offered`, `bad_arguments` or
        `unknown_argument` into one `ComposeRejected` — the next `call_<n>` from the shared
        counter, the event's name and argument text verbatim — queued in occurrence order;
        it ignores every other event and consumes no id for them. After a rejection the
        stream goes on.

        Yields:
            `ComposeText` pieces, `ComposeRejected` values and the runner's `E` events, in
            occurrence order.

        Raises:
            LlmUnreachableError: after every event queued before the failure is yielded —
                `detail` `{"reason": "auth_failed"}` for a status 401/403 `LLMError`;
                `{"reason": "unreachable"}` for any other exception from the library
                (DEC-035-8, DEC-035-16). For kind `"openai"` with no api key, raised with
                `{"reason": "auth_failed"}` before any event. No `__cause__`, no provider
                text.
        """
        library_class = self._library_class()
        # DEC-035-8: the up-front refusals are raised `from None`, like the mapped failures.
        if library_class is None:
            raise _chat_unreachable(ProbeOutcome.UNREACHABLE.value) from None
        if self._missing_credential():
            # Checked before the task starts, so the refusal precedes any event (DoD-11).
            raise _chat_unreachable(ProbeOutcome.AUTH_FAILED.value) from None

        wire = [to_wire_message(message) for message in messages]
        declarations = list(tools.declarations)
        # DEC-035-7: one unbounded queue carries text pieces, runner events and the end marker
        # in the order they happened. Unbounded because `on_delta` runs inline on the library's
        # read path — backpressure there would stall the provider read for no benefit.
        queue: asyncio.Queue[ComposeText | ComposeRejected | E | _EndOfStream] = asyncio.Queue()
        # Per-`compose` counter: call ids restart at `call_1` for every exchange (DEC-035-6).
        call_numbers = itertools.count(1)

        async def on_delta(piece: str) -> None:
            """Queue one library text piece verbatim; `put_nowait` never blocks the read."""
            queue.put_nowait(ComposeText(piece))

        def emit(event: E) -> None:
            """The runner's `emit`: queue one caller event without blocking."""
            queue.put_nowait(event)

        def on_tool_event(event: ToolEvent) -> None:
            """The library's tool-event observer: queue one `ComposeRejected` per model-side rejection.

            Only an `error` event whose kind is one of `_REJECTION_KINDS` produces anything:
            the next `call_<n>` from the counter `invoke` uses, the event's `name` verbatim
            (`""` kept) and its `arguments` text verbatim. Every other event — `start`,
            `result`, and `error` of `tool_raised` / `unserialisable_result` — is ignored and
            consumes no id, because a call that reached a wrapper is already reported by the
            runner (DEC-035-17, `DEC-arch-llm-client-library-15`). The event's `call_id`,
            `output` and any library text are never read (DoD-7).

            Synchronous and non-raising: it runs inline on the library's loop, and a raising
            observer would make the library warn and tell the model the tool failed a second
            time, so every read below tolerates a malformed event. No I/O — `put_nowait` only,
            like `on_delta` and `emit` (DEC-035-7).
            """
            if event.get("type") != "error":
                return
            kind = _REJECTION_KINDS.get(str(event.get("error_kind")))
            if kind is None:
                return
            name = event.get("name")
            arguments = event.get("arguments")
            # The id is minted here, when the rejection reaches the observer, from the same
            # counter as `invoke`: the library delivers events inline in call order, so ids
            # keep following the order calls happened in across wrappers and rejections
            # (llm-and-streaming.md § Model-side tool mistakes — the observer).
            call = ToolCall(
                call_id=f"call_{next(call_numbers)}",
                name=name if isinstance(name, str) else "",
                arguments=arguments if isinstance(arguments, str) else "",
            )
            queue.put_nowait(ComposeRejected(call=call, kind=kind))

        async def invoke(name: str, present: dict[str, object]) -> str:
            """Mint the call id, build the `ToolCall` and await the runner's output text."""
            # Minted at invocation, before the runner awaits, so ids follow invocation order.
            call = ToolCall(
                call_id=f"call_{next(call_numbers)}",
                name=name,
                arguments=json.dumps(present, ensure_ascii=False),
            )
            return await tools.runner(call, emit)

        async def run() -> None:
            """The library task: one client, one `chat_with_tools`; its returned text is discarded."""
            callables = {
                _declaration_name(declaration): _tool_callable(
                    _declaration_name(declaration), _declaration_properties(declaration), invoke
                )
                for declaration in declarations
            }
            client = self._build_client(library_class, model)
            async with client:
                # DEC-035-10: the tool loop even with nothing offered, so replayed tool pairs
                # still reach the library. `max_loops=sys.maxsize`: RPHelper sets no round
                # limit (DEC-arch-llm-client-library-4). 0.2.1 types `messages` as
                # `Sequence[Mapping[str, Any]]`, so it needs no cast. DEC-035-5: `tools_definitions`
                # is still `List[Dict[str, Any]]`, which mypy refuses for the read-only
                # `list[Mapping[str, object]]` declarations [arg-type], so it stays cast.
                await client.chat_with_tools(
                    messages=wire,
                    tools_definitions=cast(Any, declarations),
                    tools=callables,
                    stream=True,
                    max_loops=sys.maxsize,
                    on_delta=on_delta,
                    # DEC-arch-llm-client-library-14: tolerant mode asked for explicitly, not
                    # left to the library default; a model-side mistake reaches the observer and
                    # the loop continues. No `read_timeout` / `trace` (`-17`).
                    tool_errors="result",
                    on_tool_event=on_tool_event,
                )

        def finished(done: asyncio.Task[None]) -> None:
            """Queue the end marker carrying the task's exception (DEC-035-7 step 3).

            Reading `exception()` here also marks it retrieved, so asyncio logs nothing for it.
            A cancelled task carries none — only the `finally` below cancels it, and by then
            nobody reads the queue.
            """
            queue.put_nowait(_EndOfStream(None if done.cancelled() else done.exception()))

        task = asyncio.create_task(run())
        task.add_done_callback(finished)
        try:
            while True:
                item = await queue.get()
                if isinstance(item, _EndOfStream):
                    if item.error is None:
                        return
                    # Every item queued before the marker has already been yielded, so the
                    # failure arrives last (DoD-10). Raised `from None` (DEC-035-8).
                    raise _chat_unreachable(_chat_failure_reason(item.error)) from None
                yield item
        finally:
            # Runs on normal end, failure, `aclose()` / `GeneratorExit` and consumer
            # cancellation. Cancelling and then awaiting the task means the library's request
            # and client are closed before this generator returns (DEC-035-7 step 5, UC-085):
            # the library passes `CancelledError` through, and its `async with` exits on it.
            task.cancel()
            # Wait with `asyncio.wait`, not `await task`: on CPython 3.12, an async generator
            # whose `finally` (run by `aclose()`) catches a `CancelledError` raised into its
            # own frame is left flagged as running, so a later `__anext__` raises
            # `RuntimeError` instead of `StopAsyncIteration` (fixed in 3.13). `asyncio.wait`
            # returns once the task is done without raising its outcome here (DoD-12). A
            # consumer cancellation already in flight is not swallowed: it is the exception
            # this `finally` is unwinding, and it re-raises after the block.
            await asyncio.wait([task])
            # DEC-035-7: the outcome is suppressed — the task ends cancelled, or with the error
            # already mapped above; neither has anyone left to report to. Reading
            # `exception()` marks it retrieved so asyncio logs nothing for it.
            if not task.cancelled():
                task.exception()
