"""The LLM gateway — the one module that knows the `llm-client` library.

Feature `035`. Holds the probe-outcome value set (`ProbeOutcome`, `ProbeResult`,
`EMBED_NO_VECTOR_REASON`), the compose-stream values (`ComposeText`, `ComposeTools`) and
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

from llm import LlamaSwapAPIClient, LLMClient, LLMError, OpenAIAPIClient

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
    """Whether a library error is a 401/403 refusal (DEC-arch-llm-client-library-3).

    Reads `exc.message` only — never `description`, which holds the provider's reply body.
    """
    message = exc.message
    return "status 401" in message or "status 403" in message


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

    A status 401/403 `LLMError` is `auth_failed`; every other failure — another `LLMError`, a
    `RuntimeError` (a tool raised, the round limit), a `ValueError` (missing callable, unknown
    argument names, a construction refusal) or any other exception — is `unreachable`. Only
    the `LLMError` message's status marker is read; nothing of the error is kept or logged.
    """
    if isinstance(exc, LLMError) and _is_auth_failure(exc):
        return ProbeOutcome.AUTH_FAILED.value
    return ProbeOutcome.UNREACHABLE.value


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
            `compose` reports as `unreachable` like any other library-side refusal.
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
    that signature and refuses unknown names itself (DEC-arch-llm-client-library-6). On call it
    drops the absent arguments and awaits `invoke(name, present_kwargs)`, returning its text.

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
            # Only the message's status marker is read; the message and description carry
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
            # Only the message's status / prefix markers are read; neither the message nor the
            # description (provider text) is logged or carried onward (DEC-035-8).
            if _is_auth_failure(exc):
                reason = ProbeOutcome.AUTH_FAILED.value
            elif exc.message.startswith("Invalid response"):
                reason = EMBED_NO_VECTOR_REASON
            else:
                reason = ProbeOutcome.UNREACHABLE.value
        except Exception:
            # Transport errors, construction refusals and library bugs all read as `unreachable`.
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
                every other `LLMError` and for a library `ValueError` (DEC-035-8). The raised
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
                # DEC-035-5: the library types messages as `List[LLMMessage]`; the wire dicts are
                # that shape at runtime.
                text = await client.chat(cast(Any, wire), stream=False)
        except Exception as exc:
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
    ) -> AsyncGenerator[ComposeText | E, None]:
        """Stream one compose exchange: text pieces and the runner's events, in order.

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

        Yields:
            `ComposeText` pieces and the runner's `E` events, in occurrence order.

        Raises:
            LlmUnreachableError: after every event queued before the failure is yielded —
                `detail` `{"reason": "auth_failed"}` for a status 401/403 `LLMError`;
                `{"reason": "unreachable"}` for any other `LLMError`, `RuntimeError` or
                `ValueError` (DEC-035-8). For kind `"openai"` with no api key, raised with
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
        queue: asyncio.Queue[ComposeText | E | _EndOfStream] = asyncio.Queue()
        # Per-`compose` counter: call ids restart at `call_1` for every exchange (DEC-035-6).
        call_numbers = itertools.count(1)

        async def on_delta(piece: str) -> None:
            """Queue one library text piece verbatim; `put_nowait` never blocks the read."""
            queue.put_nowait(ComposeText(piece))

        def emit(event: E) -> None:
            """The runner's `emit`: queue one caller event without blocking."""
            queue.put_nowait(event)

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
                # limit (DEC-arch-llm-client-library-12). DEC-035-5: the library's narrower
                # `messages` / `tools_definitions` types are cast at this boundary.
                await client.chat_with_tools(
                    messages=cast(Any, wire),
                    tools_definitions=cast(Any, declarations),
                    tools=callables,
                    stream=True,
                    max_loops=sys.maxsize,
                    on_delta=on_delta,
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
