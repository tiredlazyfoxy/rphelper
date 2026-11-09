"""`LlmGateway.compose` over the library's streaming tool loop (feature 035, step 003).

Covers DoD-3..14: the `chat_with_tools` call shape, replayed history, verbatim text pieces, the
minted, signature-bearing tool callables, one ordered stream of text and runner events, how the
stream ends, fails and is closed, the no-tools case, and one library client per call.
Decisions: DEC-035-3 (the `library_clients` seam), DEC-035-4, DEC-035-6 (`ComposeTools` and the
wrapper), DEC-035-7 (one queue; cancel-and-await on close), DEC-035-8 (failure mapping),
DEC-035-10 (the tool loop even with no tools), `DEC-arch-llm-client-library-4`, `-5`, `-6`, `-8`.

No HTTP: the gateway is given a fake library client class through its keyword-only
`library_clients` map (`DEC-arch-llm-client-library-11`). The fake's `chat_with_tools` imitates
the library's 0.2.0 tool-call contract (feature 035 step 003's context): the pre-flight check that every
advertised tool has a callable, `on_delta` with scripted pieces (awaited when awaitable), the
offered-name check, the `inspect.signature` argument-name check, the call with keyword arguments
(awaited when awaitable), an `Exception` from the callable re-raised as `RuntimeError`, and a
`CancelledError` passed through untouched. Async code is driven with `asyncio.run` from sync
tests (the suite has no pytest-asyncio).

Feature 035 step 006 (DoD-2, DoD-4..DoD-8, DoD-14, tagged
`__S035_006_DoD<n>`; DEC-035-17, DEC-035-19, DEC-035-20, `DEC-arch-llm-client-library-14`,
`-15`, `-17`): the fake library now also imitates 0.2.1's tolerant tool loop. Called with
`tool_errors="result"` it plays each scripted call as the library does (feature 035 step 006's context,
"Test notes"): a `start` event first; then an unoffered name (`""` included) gives an `error` event of
kind `not_offered`, unreadable or non-object argument text `bad_arguments`, an argument name the
callable's `inspect.signature` lacks `unknown_argument` — each with the library's fixed text told
to the model and the callable never invoked — while a valid call is invoked and followed by a
`result` event. Every event goes to `on_tool_event` and is awaited when the observer returns an
awaitable. Called without `tool_errors` it keeps its 0.2.0 strict raising behaviour. Because the
gateway passes the tolerant mode, every step 003 test above the step 006 section now runs the
wrapper path against the tolerant fake (DoD-14). Library errors carry 0.2.1's `status`.
"""

import asyncio
import inspect
import json
import logging
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
from llm import LLMError
from loguru import logger

from app.errors import LlmUnreachableError
from app.services.llm.chat import ChatMessage, ToolCall, to_wire_message
from app.services.llm.gateway import (
    ComposeRejected,
    ComposeRejectionKind,
    ComposeText,
    ComposeTools,
    LlmGateway,
)

BASE_URL = "http://llm.test:8080"
TIMEOUT_SECONDS = 30.0
MODEL = "compose-model-y"

#: Strings that stand for provider text. Scripted library failures carry them; none may leave the
#: gateway (DoD-10).
PROVIDER_HOST = "secret-provider-host.test"
PROVIDER_BODY = "PROVIDER-BODY-SENTINEL"
PROVIDER_MARKERS = (PROVIDER_HOST, PROVIDER_BODY)

#: The library's final answer text. DoD-9 says it is never yielded.
LIBRARY_FINAL_TEXT = "LIBRARY-RETURNED-FINAL-TEXT"


def _declaration(name: str, properties: Mapping[str, object]) -> dict[str, object]:
    """A tool declaration in the nested shape `services/tools/definitions.py` uses."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"The {name} tool.",
            "parameters": {
                "type": "object",
                "properties": dict(properties),
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    }


#: One-property declaration, the shape of all three production tools.
SEARCH_MEMOS = _declaration("search_memos", {"query": {"type": "string", "description": "What to find."}})
#: Two-property declaration, so the signature and absent-argument rules (DoD-7) are observable.
LOOKUP_NOTES = _declaration(
    "lookup_notes",
    {"query": {"type": "string", "description": "What to find."}, "limit": {"type": "integer"}},
)

MESSAGES = (
    ChatMessage(role="system", content="You help the roleplayer write their side."),
    ChatMessage(role="user", content="Write my reply."),
)


@dataclass(frozen=True)
class Ev:
    """A runner event: any caller-chosen type passes through the stream unchanged (DEC-035-6)."""

    label: str


# --- The fake library ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Delta:
    """Script step: the library passes `text` to `on_delta`."""

    text: str


@dataclass(frozen=True)
class Call:
    """Script step: the model calls tool `name`; the library invokes its callable with `kwargs`."""

    name: str
    kwargs: Mapping[str, object]


@dataclass(frozen=True)
class Fail:
    """Script step: the library raises `error` (as a provider or loop failure would)."""

    error: BaseException


@dataclass(frozen=True)
class Block:
    """Script step: the library sets `reached`, then waits on `release` (never set by the test).

    It stands for an in-flight provider read, so DoD-12 can close the stream while it is running.
    """

    reached: asyncio.Event
    release: asyncio.Event


@dataclass(frozen=True)
class RawCall:
    """Script step (0.2.1): the model calls tool `name` with the raw argument text `arguments`.

    `provider_call_id` is the server's id for the call, which the library reports on each event
    and RPHelper never uses (`DEC-arch-llm-client-library-17`).
    """

    name: str
    arguments: str
    provider_call_id: str | None = None


@dataclass(frozen=True)
class Emit:
    """Script step (0.2.1): the library hands `event` to `on_tool_event` as given.

    It lets a test send any event shape the library can emit — e.g. an `error` of kind
    `tool_raised` or `unserialisable_result`, or events carrying an `output` sentinel.
    """

    event: Mapping[str, object]


Step = Delta | Call | RawCall | Emit | Fail | Block


class _NotPassed:
    """Marks a keyword the gateway did not pass to `chat_with_tools` (DoD-4 needs to tell)."""

    def __repr__(self) -> str:
        return "<not passed>"


NOT_PASSED = _NotPassed()


def tool_event(
    type_: str,
    name: str,
    arguments: str,
    *,
    call_id: str | None = None,
    output: str | None = None,
    error_kind: str | None = None,
) -> dict[str, object]:
    """One `ToolEvent` in 0.2.1's total shape: all six keys, `None` where none applies."""
    return {
        "type": type_,
        "name": name,
        "call_id": call_id,
        "arguments": arguments,
        "output": output,
        "error_kind": error_kind,
    }


def not_available_text(name: str) -> str:
    """The library's fixed model-facing text for an unoffered tool (feature 035 step 006's context)."""
    return f"Tool '{name}' is not available."


def invalid_arguments_text(name: str) -> str:
    """The library's fixed model-facing text for unreadable or non-object arguments."""
    return f"Invalid arguments for tool '{name}'."


def no_argument_text(name: str, argument: str) -> str:
    """The library's fixed model-facing text for an argument name the tool does not take."""
    return f"Tool '{name}' has no argument '{argument}'."


@dataclass
class LibraryRecord:
    """What the fake library classes observed, shared by every instance one test builds.

    `tool_events` are the events handed to the observer, in order; `told_model` the fixed texts
    the tolerant loop sent the model for rejected or failed calls.
    """

    constructed: list[dict[str, Any]] = field(default_factory=list)
    entered: int = 0
    exited: int = 0
    calls: list[dict[str, Any]] = field(default_factory=list)
    open_during_call: list[bool] = field(default_factory=list)
    tool_results: list[object] = field(default_factory=list)
    tool_events: list[dict[str, object]] = field(default_factory=list)
    told_model: list[str] = field(default_factory=list)
    cancelled: bool = False


def _definition_name(definition: Mapping[str, Any]) -> object:
    """The advertised name of a nested or flat definition, as the library reads it."""
    inner = definition.get("function", definition)
    return inner.get("name") if isinstance(inner, Mapping) else None


def fake_library_class(
    record: LibraryRecord,
    script: Sequence[Step] = (),
    *,
    require_token: bool = False,
) -> type:
    """A fake library client class bound to `record`, running `script` in `chat_with_tools`.

    It records the construction keywords exactly as passed (DEC-035-3 names four; 035 step 006
    DoD-4 checks that nothing else, such as a silence limit or a trace switch, is passed) and is
    an async context manager. With `require_token` it imitates `OpenAIAPIClient`, which refuses an
    empty bearer token with a `ValueError` at construction (`DEC-arch-llm-client-library-9`).
    """

    class FakeToolLibraryClient:
        def __init__(self, **keywords: Any) -> None:
            if require_token and not keywords.get("bearer_token"):
                raise ValueError(f"OpenAI credential not provided for {PROVIDER_HOST}")
            record.constructed.append(dict(keywords))
            self._open = False
            self._tolerant = False
            self._observer: Callable[[Any], Any] | None = None

        async def __aenter__(self) -> "FakeToolLibraryClient":
            record.entered += 1
            self._open = True
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            record.exited += 1
            self._open = False

        async def chat_with_tools(
            self,
            messages: list[dict[str, Any]],
            *,
            tools_definitions: list[dict[str, Any]],
            tools: dict[str, Callable[..., Any]],
            system: str | None = None,
            max_loops: int = 5,
            options: object = None,
            stream: bool = False,
            on_delta: Callable[[str], Any] | None = None,
            response_format: object = None,
            tool_errors: object = NOT_PASSED,
            on_tool_event: Callable[[Any], Any] | None = None,
            **unexpected: Any,
        ) -> str:
            record.calls.append(
                {
                    "messages": list(messages),
                    "tools_definitions": list(tools_definitions),
                    "tools": dict(tools),
                    "system": system,
                    "max_loops": max_loops,
                    "options": options,
                    "stream": stream,
                    "on_delta": on_delta,
                    "tool_errors": tool_errors,
                    "on_tool_event": on_tool_event,
                    "unexpected": dict(unexpected),
                }
            )
            record.open_during_call.append(self._open)
            # Tolerant only when asked explicitly; otherwise the 0.2.0 strict behaviour, which the
            # retired step 003 strict-mode tests relied on (feature 035 step 006's context, "Test notes").
            self._tolerant = tool_errors == "result"
            self._observer = on_tool_event
            # Pre-flight: every advertised name needs a callable, before any request.
            advertised = {_definition_name(definition) for definition in tools_definitions}
            if advertised - tools.keys():
                raise ValueError("Missing callables for advertised tools")
            offered = {name for name in advertised if isinstance(name, str)}
            try:
                for step in script:
                    await self._perform(step, tools, offered, on_delta)
            except asyncio.CancelledError:
                record.cancelled = True
                raise
            return LIBRARY_FINAL_TEXT

        async def _notify(self, event: dict[str, object]) -> None:
            """Hand one event to the observer inline, awaiting it when it returns an awaitable."""
            record.tool_events.append(event)
            if self._observer is not None:
                outcome = self._observer(event)
                if inspect.isawaitable(outcome):
                    await outcome

        async def _perform(
            self,
            step: Step,
            tools: Mapping[str, Callable[..., Any]],
            offered: set[str],
            on_delta: Callable[[str], Any] | None,
        ) -> None:
            if isinstance(step, Delta):
                if on_delta is not None:
                    delivered = on_delta(step.text)
                    if inspect.isawaitable(delivered):
                        await delivered
            elif isinstance(step, Call):
                arguments = json.dumps(dict(step.kwargs), ensure_ascii=False)
                await self._tool_call(step.name, arguments, None, tools, offered)
            elif isinstance(step, RawCall):
                await self._tool_call(step.name, step.arguments, step.provider_call_id, tools, offered)
            elif isinstance(step, Emit):
                await self._notify(dict(step.event))
            elif isinstance(step, Fail):
                raise step.error
            else:
                step.reached.set()
                await step.release.wait()

        async def _tool_call(
            self,
            name: str,
            arguments: str,
            provider_call_id: str | None,
            tools: Mapping[str, Callable[..., Any]],
            offered: set[str],
        ) -> None:
            """One model tool call, in the library's order: offered check, argument parse,
            argument-name check against `inspect.signature`, then the call."""
            await self._notify(tool_event("start", name, arguments, call_id=provider_call_id))
            kind: str | None = None
            told = ""
            strict_error: Exception | None = None
            parsed: object = None
            if name not in offered:
                kind, told = "not_offered", not_available_text(name)
                strict_error = LLMError(f"Model called tool '{name}' which was not offered", PROVIDER_BODY)
            else:
                try:
                    parsed = json.loads(arguments)
                except ValueError:
                    parsed = None
                if not isinstance(parsed, dict):
                    kind, told = "bad_arguments", invalid_arguments_text(name)
                    strict_error = LLMError(f"Arguments for tool '{name}' are not valid JSON", PROVIDER_BODY)
                else:
                    parameters = inspect.signature(tools[name]).parameters
                    unknown = [argument for argument in parsed if argument not in parameters]
                    if unknown:
                        kind, told = "unknown_argument", no_argument_text(name, unknown[0])
                        strict_error = ValueError(f"Bad args for tool '{name}': {PROVIDER_BODY}")
            if kind is not None:
                await self._notify(
                    tool_event("error", name, arguments, call_id=provider_call_id, error_kind=kind)
                )
                if not self._tolerant:
                    assert strict_error is not None
                    raise strict_error
                record.told_model.append(told)
                return
            assert isinstance(parsed, dict)
            try:
                result = tools[name](**parsed)
                if inspect.isawaitable(result):
                    result = await result
            except Exception as exc:
                if not self._tolerant:
                    raise RuntimeError(f"Tool '{name}' failed: {exc}") from exc
                await self._notify(
                    tool_event("error", name, arguments, call_id=provider_call_id, error_kind="tool_raised")
                )
                record.told_model.append(f"Tool '{name}' failed.")
                return
            record.tool_results.append(result)
            await self._notify(
                tool_event("result", name, arguments, call_id=provider_call_id, output=str(result))
            )

    return FakeToolLibraryClient


def gateway_over(fake_class: type, *, kind: str = "llamaswap", api_key: str | None = None) -> LlmGateway:
    """A gateway whose only library class, for `kind`, is `fake_class` (the DEC-035-3 seam)."""
    return LlmGateway(kind, BASE_URL, api_key, TIMEOUT_SECONDS, library_clients={kind: fake_class})


# --- Runner, drain and log helpers --------------------------------------------------------------


class RecordingRunner:
    """A runner (the caller's half of the wrapper) that records each `ToolCall` it receives.

    Per call it emits `Ev("start:<call_id>")`, yields to the loop once, emits
    `Ev("end:<call_id>")`, and returns `"output for <call_id>"`.
    """

    def __init__(self) -> None:
        self.calls: list[ToolCall] = []

    async def __call__(self, call: ToolCall, emit: Callable[[Ev], None]) -> str:
        self.calls.append(call)
        emit(Ev(f"start:{call.call_id}"))
        await asyncio.sleep(0)
        emit(Ev(f"end:{call.call_id}"))
        return f"output for {call.call_id}"


def tools_of(runner: Callable[[ToolCall, Callable[[Ev], None]], Awaitable[str]], *declarations: Any) -> Any:
    """A `ComposeTools` bundle over `declarations` (in that order) and `runner`."""
    return ComposeTools(declarations=list(declarations), runner=runner)


def run[T](awaitable: Awaitable[T]) -> T:
    """Drive one coroutine to completion; a 10 s cap turns a hang into a quick failure."""

    async def capped() -> T:
        return await asyncio.wait_for(awaitable, 10)

    return asyncio.run(capped())


async def drain(stream: AsyncIterator[Any]) -> list[Any]:
    """Every event the stream yields until it ends."""
    return [event async for event in stream]


async def drain_into(stream: AsyncIterator[Any], seen: list[Any]) -> None:
    """Append each event to `seen` until the stream ends or raises (the raise propagates)."""
    async for event in stream:
        seen.append(event)


def compose_events(
    record: LibraryRecord,
    script: Sequence[Step],
    *declarations: Any,
    runner: Any = None,
    messages: Sequence[ChatMessage] = MESSAGES,
) -> list[Any]:
    """Run one `compose` over a fake library playing `script`; return every event yielded."""
    gateway = gateway_over(fake_library_class(record, script))
    tools = tools_of(runner if runner is not None else RecordingRunner(), *declarations)
    return run(drain(gateway.compose(MODEL, messages, tools)))


@contextmanager
def captured_log_text(caplog: pytest.LogCaptureFixture) -> Iterator[list[str]]:
    """Collect every loguru record (all levels) and stdlib record while the block runs."""
    lines: list[str] = []
    sink_id = logger.add(lambda message: lines.append(str(message)), level="TRACE", format="{message} {extra}")
    caplog.set_level(logging.DEBUG)
    try:
        yield lines
    finally:
        logger.remove(sink_id)


# --- DoD-3: the chat_with_tools call shape ------------------------------------------------------


def test_compose_builds_one_client_with_the_model__DoD3() -> None:
    """DoD-3: one library client is built with the given model and `chat_with_tools` is called once."""
    record = LibraryRecord()
    compose_events(record, [Delta("hi")], SEARCH_MEMOS, LOOKUP_NOTES)

    assert len(record.constructed) == 1
    assert record.constructed[0]["model"] == MODEL
    assert len(record.calls) == 1


def test_compose_streams_with_no_loop_cap_system_or_options__DoD3() -> None:
    """DoD-3: `stream=True`, `max_loops=sys.maxsize`, no `system` keyword and no options."""
    record = LibraryRecord()
    compose_events(record, [Delta("hi")], SEARCH_MEMOS, LOOKUP_NOTES)

    call = record.calls[0]
    assert call["stream"] is True
    assert call["max_loops"] == sys.maxsize
    assert call["system"] is None
    assert call["options"] is None


def test_compose_passes_declarations_as_given_in_order__DoD3() -> None:
    """DoD-3: `tools_definitions` equals the declarations as given, in offered order."""
    record = LibraryRecord()
    compose_events(record, [Delta("hi")], LOOKUP_NOTES, SEARCH_MEMOS)

    assert record.calls[0]["tools_definitions"] == [LOOKUP_NOTES, SEARCH_MEMOS]


def test_compose_passes_one_callable_per_declaration_name__DoD3() -> None:
    """DoD-3: `tools` maps each declaration's name, and only those, to a callable."""
    record = LibraryRecord()
    compose_events(record, [Delta("hi")], SEARCH_MEMOS, LOOKUP_NOTES)

    tools = record.calls[0]["tools"]
    assert set(tools) == {"search_memos", "lookup_notes"}
    assert all(callable(func) for func in tools.values())


# --- DoD-4: replayed history --------------------------------------------------------------------


def test_compose_replays_tool_calls_and_tool_results_intact__DoD4() -> None:
    """DoD-4: an assistant tool call and its tool message reach the library with ids preserved."""
    replayed_call = ToolCall(call_id="call_1", name="search_memos", arguments='{"query": "the dragon"}')
    history = (
        ChatMessage(role="system", content="System prompt."),
        ChatMessage(role="user", content="Earlier question."),
        ChatMessage(role="assistant", content="Let me look.", tool_calls=(replayed_call,)),
        ChatMessage(role="tool", content="Memo: the dragon sleeps.", tool_call_id="call_1"),
        ChatMessage(role="assistant", content="The dragon sleeps."),
        ChatMessage(role="user", content="Continue."),
    )
    record = LibraryRecord()
    compose_events(record, [Delta("ok")], SEARCH_MEMOS, messages=history)

    sent = record.calls[0]["messages"]
    assert sent == [to_wire_message(message) for message in history]
    assert sent[2]["tool_calls"] == [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "search_memos", "arguments": '{"query": "the dragon"}'},
        }
    ]
    assert sent[3] == {"role": "tool", "tool_call_id": "call_1", "content": "Memo: the dragon sleeps."}


# --- DoD-5: verbatim text pieces ----------------------------------------------------------------


def test_compose_yields_one_compose_text_per_piece_verbatim__DoD5() -> None:
    """DoD-5: each `on_delta` piece yields exactly one `ComposeText` with identical text, in order."""
    pieces = ["<think>", "planning the reply", "</think>", "Hello", ", ", "world", "\n", " Привет "]
    record = LibraryRecord()
    events = compose_events(record, [Delta(piece) for piece in pieces], SEARCH_MEMOS)

    assert events == [ComposeText(piece) for piece in pieces]


def test_compose_passes_think_tags_through_inside_pieces__DoD5() -> None:
    """DoD-5: `<think>` / `</think>` prefixed on pieces pass through with nothing added or removed."""
    pieces = ["<think>Let me", " consider.", "</think>The answer", " is here."]
    record = LibraryRecord()
    events = compose_events(record, [Delta(piece) for piece in pieces], SEARCH_MEMOS)

    assert [event.text for event in events] == pieces
    assert all(isinstance(event, ComposeText) for event in events)


# --- DoD-6: the ToolCall the runner receives ----------------------------------------------------


def test_compose_mints_call_ids_in_invocation_order__DoD6() -> None:
    """DoD-6: `call_id` is `call_1`, `call_2`, `call_3` in invocation order within one compose."""
    runner = RecordingRunner()
    script = [
        Call("search_memos", {"query": "a"}),
        Call("lookup_notes", {"query": "b"}),
        Call("search_memos", {"query": "c"}),
    ]
    compose_events(LibraryRecord(), script, SEARCH_MEMOS, LOOKUP_NOTES, runner=runner)

    assert [call.call_id for call in runner.calls] == ["call_1", "call_2", "call_3"]


def test_compose_call_ids_restart_for_the_next_compose__DoD6() -> None:
    """DoD-6: the next `compose` call on the same gateway starts again at `call_1`."""
    record = LibraryRecord()
    gateway = gateway_over(
        fake_library_class(record, [Call("search_memos", {"query": "a"}), Call("search_memos", {"query": "b"})])
    )
    first, second = RecordingRunner(), RecordingRunner()

    run(drain(gateway.compose(MODEL, MESSAGES, tools_of(first, SEARCH_MEMOS))))
    run(drain(gateway.compose(MODEL, MESSAGES, tools_of(second, SEARCH_MEMOS))))

    assert [call.call_id for call in first.calls] == ["call_1", "call_2"]
    assert [call.call_id for call in second.calls] == ["call_1", "call_2"]


def test_compose_tool_call_carries_the_declaration_name__DoD6() -> None:
    """DoD-6: the `ToolCall`'s name is the name of the declaration whose callable was invoked."""
    runner = RecordingRunner()
    script = [Call("lookup_notes", {"query": "a"}), Call("search_memos", {"query": "b"})]
    compose_events(LibraryRecord(), script, SEARCH_MEMOS, LOOKUP_NOTES, runner=runner)

    assert [call.name for call in runner.calls] == ["lookup_notes", "search_memos"]


def test_compose_tool_call_arguments_are_json_of_the_kwargs_non_ascii_kept__DoD6() -> None:
    """DoD-6: `arguments` is `json.dumps` of the keyword arguments, non-ASCII unescaped."""
    runner = RecordingRunner()
    compose_events(
        LibraryRecord(), [Call("search_memos", {"query": "Привет, ça va?"})], SEARCH_MEMOS, runner=runner
    )

    arguments = runner.calls[0].arguments
    assert arguments == json.dumps({"query": "Привет, ça va?"}, ensure_ascii=False)
    assert arguments == '{"query": "Привет, ça va?"}'


def test_compose_tool_call_arguments_hold_every_given_kwarg__DoD6() -> None:
    """DoD-6: with several keyword arguments, the JSON holds each one with its value."""
    runner = RecordingRunner()
    compose_events(
        LibraryRecord(), [Call("lookup_notes", {"query": "dragons", "limit": 3})], LOOKUP_NOTES, runner=runner
    )

    assert json.loads(runner.calls[0].arguments) == {"query": "dragons", "limit": 3}


def test_compose_returns_the_runner_text_to_the_library__DoD6() -> None:
    """DoD-6: what the runner returns is what the tool callable returns to the library."""
    record = LibraryRecord()
    script = [Call("search_memos", {"query": "a"}), Call("search_memos", {"query": "b"})]
    compose_events(record, script, SEARCH_MEMOS)

    assert record.tool_results == ["output for call_1", "output for call_2"]


# --- DoD-7: the minted signature ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("declaration", "names"),
    [
        pytest.param(SEARCH_MEMOS, {"query"}, id="one-property"),
        pytest.param(LOOKUP_NOTES, {"query", "limit"}, id="two-properties"),
    ],
)
def test_compose_tool_callable_signature_is_the_declared_properties__DoD7(
    declaration: dict[str, object], names: set[str]
) -> None:
    """DoD-7: the callable's signature lists exactly the `properties` names, keyword-only, with defaults."""
    record = LibraryRecord()
    compose_events(record, [Delta("hi")], declaration)

    function = declaration["function"]
    assert isinstance(function, dict)
    parameters = inspect.signature(record.calls[0]["tools"][function["name"]]).parameters
    assert set(parameters) == names
    assert len(parameters) == len(names)
    for parameter in parameters.values():
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is not inspect.Parameter.empty


def test_compose_absent_declared_argument_is_left_out_of_the_json__DoD7() -> None:
    """DoD-7: a declared argument the library does not pass is absent from `arguments`."""
    runner = RecordingRunner()
    compose_events(LibraryRecord(), [Call("lookup_notes", {"query": "dragons"})], LOOKUP_NOTES, runner=runner)

    arguments = runner.calls[0].arguments
    assert json.loads(arguments) == {"query": "dragons"}
    assert arguments == json.dumps({"query": "dragons"}, ensure_ascii=False)


# --- DoD-8: one ordered stream of text and runner events ---------------------------------------


def test_compose_runner_events_appear_in_emit_order_between_the_text__DoD8() -> None:
    """DoD-8: text before a call precedes its events, events keep emit order, later text follows."""
    script = [
        Delta("before the tool"),
        Call("search_memos", {"query": "a"}),
        Delta("between"),
        Call("search_memos", {"query": "b"}),
        Delta("after the tools"),
    ]
    events = compose_events(LibraryRecord(), script, SEARCH_MEMOS)

    assert events == [
        ComposeText("before the tool"),
        Ev("start:call_1"),
        Ev("end:call_1"),
        ComposeText("between"),
        Ev("start:call_2"),
        Ev("end:call_2"),
        ComposeText("after the tools"),
    ]


# --- DoD-9: the stream ends with the library call ----------------------------------------------


def test_compose_ends_after_the_last_event_and_drops_the_returned_text__DoD9() -> None:
    """DoD-9: the stream ends after the last queued event; the library's return text is not yielded."""
    script = [Delta("streamed"), Call("search_memos", {"query": "a"})]
    events = compose_events(LibraryRecord(), script, SEARCH_MEMOS)

    assert events == [ComposeText("streamed"), Ev("start:call_1"), Ev("end:call_1")]
    assert all(LIBRARY_FINAL_TEXT not in getattr(event, "text", "") for event in events)


def test_compose_with_no_pieces_ends_empty__DoD9() -> None:
    """DoD-9: a library call that streams nothing ends the stream with no event at all."""
    assert compose_events(LibraryRecord(), [], SEARCH_MEMOS) == []


# --- DoD-10: failures ---------------------------------------------------------------------------


def _llm_error(message: str, status: int | None = None) -> LLMError:
    """An `LLMError` shaped like the library's, carrying the provider markers.

    `status` is 0.2.1's HTTP status attribute; since 035 step 006 it alone decides `auth_failed`
    (DEC-035-20), so every status case passes it.
    """
    return LLMError(message, PROVIDER_BODY, status=status, kind=None if status is None else "status")


def _status_failure(status: int, message_status: int | None = None) -> LLMError:
    """The library's non-2xx error: the message names `message_status` (default `status`)."""
    shown = status if message_status is None else message_status
    return _llm_error(f"Request to http://{PROVIDER_HOST}/v1/responses failed with status {shown}", status)


LIBRARY_FAILURES = [
    pytest.param(_status_failure(401), "auth_failed", id="status-401"),
    pytest.param(_status_failure(403), "auth_failed", id="status-403"),
    pytest.param(_status_failure(500), "unreachable", id="status-500"),
    pytest.param(
        _llm_error(f"Request to http://{PROVIDER_HOST}/v1/responses failed: timeout"),
        "unreachable",
        id="transport",
    ),
    pytest.param(
        _llm_error(f"Invalid response from http://{PROVIDER_HOST}/v1/responses"),
        "unreachable",
        id="invalid-response",
    ),
    pytest.param(
        RuntimeError(f"Tool loop failed at {PROVIDER_HOST}: {PROVIDER_BODY}"),
        "unreachable",
        id="runtime-error",
    ),
    pytest.param(
        ValueError(f"bad value from {PROVIDER_HOST}: {PROVIDER_BODY}"),
        "unreachable",
        id="value-error",
    ),
]


def _assert_clean_unreachable(error: LlmUnreachableError, reason: str, log_text: str) -> None:
    """The DoD-10 error shape: the reason, no chained cause (DEC-035-8), no provider text."""
    assert error.detail == {"reason": reason}
    assert error.__cause__ is None
    assert error.__suppress_context__ is True
    for marker in PROVIDER_MARKERS:
        for surface in (str(error), repr(error.args), repr(error.detail), log_text):
            assert marker not in surface


def _failing_compose(
    script: Sequence[Step], caplog: pytest.LogCaptureFixture, runner: Any = None
) -> tuple[list[Any], LlmUnreachableError, str]:
    """Drain a compose that must fail; return the events seen first, the error and the log text."""
    seen: list[Any] = []
    gateway = gateway_over(fake_library_class(LibraryRecord(), script))
    tools = tools_of(runner if runner is not None else RecordingRunner(), SEARCH_MEMOS)
    with captured_log_text(caplog) as lines, pytest.raises(LlmUnreachableError) as caught:
        run(drain_into(gateway.compose(MODEL, MESSAGES, tools), seen))
    return seen, caught.value, "".join(lines) + caplog.text


@pytest.mark.parametrize(("library_error", "reason"), LIBRARY_FAILURES)
def test_compose_failure_yields_queued_events_then_raises_mapped__DoD10(
    library_error: BaseException, reason: str, caplog: pytest.LogCaptureFixture
) -> None:
    """DoD-10: events queued before the failure come first; then `llm_unreachable` with the reason."""
    script = [Delta("partial"), Call("search_memos", {"query": "a"}), Delta(" more"), Fail(library_error)]
    seen, error, log_text = _failing_compose(script, caplog)

    assert seen == [ComposeText("partial"), Ev("start:call_1"), Ev("end:call_1"), ComposeText(" more")]
    _assert_clean_unreachable(error, reason, log_text)


# Retired by 035 step 006 (DoD-14), citing DEC-arch-llm-client-library-15: the three step 003
# strict-mode cases — `test_compose_unoffered_tool_name_is_unreachable__DoD10`,
# `test_compose_unknown_argument_name_is_unreachable__DoD10` and
# `test_compose_unparseable_arguments_is_unreachable__DoD10` — asserted that an unoffered tool
# name, an undeclared argument name and unparseable arguments ended the exchange as
# `unreachable`. Under 0.2.1's tolerant loop each is a `ComposeRejected` and the stream goes on;
# the step 006 DoD-5 / DoD-8 tests below assert that instead.


def test_compose_runner_exception_surfacing_as_runtime_error_is_unreachable__DoD10(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """DoD-10 (kept by 035 step 006 as a generic `RuntimeError` mapping check): after a runner
    emitted, the library raising `RuntimeError` → `unreachable`; the prior emits are still yielded."""

    async def emitting_runner(call: ToolCall, emit: Callable[[Ev], None]) -> str:
        emit(Ev("before the failure"))
        return "output"

    seen, error, log_text = _failing_compose(
        [
            Delta("partial"),
            Call("search_memos", {"query": "a"}),
            Fail(RuntimeError(f"Tool 'search_memos' failed at {PROVIDER_HOST}: {PROVIDER_BODY}")),
        ],
        caplog,
        runner=emitting_runner,
    )

    assert seen == [ComposeText("partial"), Ev("before the failure")]
    _assert_clean_unreachable(error, "unreachable", log_text)


# --- DoD-11: an OpenAI server with no credential -----------------------------------------------


def test_compose_openai_without_api_key_is_auth_failed_before_any_event__DoD11() -> None:
    """DoD-11: kind `openai`, no api key → `auth_failed` before any event; the library never runs."""
    record = LibraryRecord()
    fake_openai = fake_library_class(record, [Delta("must not appear")], require_token=True)
    gateway = gateway_over(fake_openai, kind="openai", api_key=None)
    seen: list[Any] = []

    with pytest.raises(LlmUnreachableError) as caught:
        run(drain_into(gateway.compose(MODEL, MESSAGES, tools_of(RecordingRunner(), SEARCH_MEMOS)), seen))

    assert caught.value.detail == {"reason": "auth_failed"}
    assert seen == []
    assert record.calls == []


# --- DoD-12: closing the stream while the library call runs ------------------------------------


def test_compose_aclose_cancels_the_running_library_call__DoD12() -> None:
    """DoD-12: `aclose` mid-call → the library call sees cancellation, its client exits, no raise."""
    record = LibraryRecord()

    async def scenario() -> tuple[Any, list[Any]]:
        reached, release = asyncio.Event(), asyncio.Event()
        script = [Delta("first"), Block(reached, release), Delta("never streamed")]
        gateway = gateway_over(fake_library_class(record, script))
        stream = gateway.compose(MODEL, MESSAGES, tools_of(RecordingRunner(), SEARCH_MEMOS))
        first = await anext(stream)
        await reached.wait()  # the library is now mid-call, waiting on a release that never comes
        await stream.aclose()  # must return without raising
        later: list[Any] = []
        async for event in stream:
            later.append(event)
        return first, later

    first, later = run(scenario())

    assert first == ComposeText("first")
    assert record.cancelled is True
    assert record.exited == 1
    assert later == []


def test_compose_aclose_cancels_a_runner_awaiting_inside_a_tool__DoD12() -> None:
    """DoD-12: a runner awaiting inside a tool observes cancellation and no later event is yielded."""
    record = LibraryRecord()
    observed: dict[str, bool] = {"runner_cancelled": False}

    async def scenario() -> tuple[list[Any], list[Any]]:
        inside, release = asyncio.Event(), asyncio.Event()

        async def waiting_runner(call: ToolCall, emit: Callable[[Ev], None]) -> str:
            emit(Ev("tool started"))
            inside.set()
            try:
                await release.wait()  # never set: the tool is still working when the stream closes
            except asyncio.CancelledError:
                observed["runner_cancelled"] = True
                emit(Ev("emitted after cancellation"))
                raise
            return "unreachable output"

        script = [Delta("first"), Call("search_memos", {"query": "a"}), Delta("never streamed")]
        gateway = gateway_over(fake_library_class(record, script))
        stream = gateway.compose(MODEL, MESSAGES, tools_of(waiting_runner, SEARCH_MEMOS))
        before = [await anext(stream), await anext(stream)]
        await inside.wait()
        await stream.aclose()
        later: list[Any] = []
        async for event in stream:
            later.append(event)
        return before, later

    before, later = run(scenario())

    assert before == [ComposeText("first"), Ev("tool started")]
    assert observed["runner_cancelled"] is True
    assert record.cancelled is True
    assert record.exited == 1
    assert later == []


# --- DoD-13: no tools offered -------------------------------------------------------------------


def test_compose_with_no_declarations_still_uses_the_tool_loop__DoD13() -> None:
    """DoD-13: empty declarations → `chat_with_tools` with empty definitions and an empty callables map."""
    record = LibraryRecord()
    gateway = gateway_over(fake_library_class(record, [Delta("plain reply")]))
    tools = ComposeTools(declarations=(), runner=RecordingRunner())

    events = run(drain(gateway.compose(MODEL, MESSAGES, tools)))

    assert len(record.calls) == 1
    assert record.calls[0]["tools_definitions"] == []
    assert record.calls[0]["tools"] == {}
    assert events == [ComposeText("plain reply")]


# --- DoD-14: exactly one library client per compose call ---------------------------------------


def _assert_one_client(record: LibraryRecord) -> None:
    """One client built, entered once and exited once; the library call ran while it was open."""
    assert len(record.constructed) == 1
    assert record.entered == 1
    assert record.exited == 1
    assert record.open_during_call == [True]


def test_compose_completed_call_enters_and_exits_one_client__DoD14() -> None:
    """DoD-14: a compose that completes enters and exits exactly one library client."""
    record = LibraryRecord()
    compose_events(record, [Delta("a"), Call("search_memos", {"query": "q"}), Delta("b")], SEARCH_MEMOS)

    _assert_one_client(record)


def test_compose_failed_call_enters_and_exits_one_client__DoD14() -> None:
    """DoD-14: a compose that fails enters and exits exactly one library client."""
    record = LibraryRecord()
    failure = _llm_error(f"Request to http://{PROVIDER_HOST}/v1/responses failed with status 500")
    gateway = gateway_over(fake_library_class(record, [Delta("a"), Fail(failure)]))

    with pytest.raises(LlmUnreachableError):
        run(drain(gateway.compose(MODEL, MESSAGES, tools_of(RecordingRunner(), SEARCH_MEMOS))))

    _assert_one_client(record)


def test_compose_closed_call_enters_and_exits_one_client__DoD14() -> None:
    """DoD-14: a compose closed mid-call enters and exits exactly one library client."""
    record = LibraryRecord()

    async def scenario() -> None:
        reached, release = asyncio.Event(), asyncio.Event()
        gateway = gateway_over(fake_library_class(record, [Delta("a"), Block(reached, release)]))
        stream = gateway.compose(MODEL, MESSAGES, tools_of(RecordingRunner(), SEARCH_MEMOS))
        await anext(stream)
        await reached.wait()
        await stream.aclose()

    run(scenario())

    _assert_one_client(record)


def test_compose_each_call_uses_its_own_client__DoD14() -> None:
    """DoD-14: two compose calls on one gateway build, enter and exit one client each."""
    record = LibraryRecord()
    gateway = gateway_over(fake_library_class(record, [Delta("a")]))

    run(drain(gateway.compose(MODEL, MESSAGES, tools_of(RecordingRunner(), SEARCH_MEMOS))))
    run(drain(gateway.compose(MODEL, MESSAGES, tools_of(RecordingRunner(), SEARCH_MEMOS))))

    assert len(record.constructed) == 2
    assert record.entered == 2
    assert record.exited == 2
    assert record.open_during_call == [True, True]


# =================================================================================================
# 035 step 006 — library 0.2.1: the tolerant tool loop and the status-based auth split
# =================================================================================================


# --- S035 006 DoD-2: auth_failed from the error's status -----------------------------------------

STATUS_SPLIT = [
    pytest.param(_llm_error(f"Refused by {PROVIDER_HOST}", 401), "auth_failed", id="status-401-opaque-message"),
    pytest.param(_llm_error(f"Refused by {PROVIDER_HOST}", 403), "auth_failed", id="status-403-opaque-message"),
    pytest.param(_status_failure(401, message_status=500), "auth_failed", id="status-401-message-says-500"),
    pytest.param(
        _llm_error(f"Request to http://{PROVIDER_HOST}/v1/responses failed with status 401"),
        "unreachable",
        id="message-401-no-status",
    ),
    pytest.param(
        _llm_error(f"Request to http://{PROVIDER_HOST}/v1/responses failed with status 403"),
        "unreachable",
        id="message-403-no-status",
    ),
    pytest.param(_status_failure(500, message_status=401), "unreachable", id="status-500-message-says-401"),
    pytest.param(_status_failure(400), "unreachable", id="status-400"),
    pytest.param(_status_failure(404), "unreachable", id="status-404"),
    pytest.param(_status_failure(429), "unreachable", id="status-429"),
]


@pytest.mark.parametrize(("library_error", "reason"), STATUS_SPLIT)
def test_compose_auth_failed_is_read_from_the_error_status__S035_006_DoD2(
    library_error: LLMError, reason: str, caplog: pytest.LogCaptureFixture
) -> None:
    """S035 006 DoD-2: status 401/403 → `auth_failed` whatever the message; a message naming
    401/403 with no status, or another status → `unreachable`. No provider text, no cause."""
    seen, error, log_text = _failing_compose([Delta("partial"), Fail(library_error)], caplog)

    assert seen == [ComposeText("partial")]
    assert error.code == "llm_unreachable"
    _assert_clean_unreachable(error, reason, log_text)


# --- S035 006 DoD-4: the call shape under 0.2.1 --------------------------------------------------


def test_compose_passes_tolerant_tool_errors_and_a_callable_observer__S035_006_DoD4() -> None:
    """S035 006 DoD-4: `chat_with_tools` gets `tool_errors="result"` and a callable `on_tool_event`,
    besides step 003 DoD-3's shape, and no other keyword."""
    record = LibraryRecord()
    compose_events(record, [Delta("hi")], SEARCH_MEMOS, LOOKUP_NOTES)

    call = record.calls[0]
    assert call["tool_errors"] == "result"
    assert callable(call["on_tool_event"])
    assert call["unexpected"] == {}
    assert call["stream"] is True
    assert call["max_loops"] == sys.maxsize
    assert call["system"] is None
    assert call["options"] is None


@pytest.mark.parametrize("declarations", [(SEARCH_MEMOS,), ()], ids=["with-tools", "no-tools"])
def test_compose_builds_the_client_with_exactly_four_keywords__S035_006_DoD4(
    declarations: tuple[Any, ...],
) -> None:
    """S035 006 DoD-4 / `DEC-arch-llm-client-library-17`: the library client is built with exactly
    `model`, `base_url`, `timeout` and `bearer_token` — no silence limit, no trace switch."""
    record = LibraryRecord()
    gateway = gateway_over(fake_library_class(record, [Delta("hi")]), api_key="sk-compose-key")

    run(drain(gateway.compose(MODEL, MESSAGES, tools_of(RecordingRunner(), *declarations))))

    assert len(record.constructed) == 1
    assert set(record.constructed[0]) == {"model", "base_url", "timeout", "bearer_token"}
    assert record.constructed[0]["model"] == MODEL
    assert record.constructed[0]["timeout"] == TIMEOUT_SECONDS
    assert record.constructed[0]["bearer_token"] == "sk-compose-key"


# --- S035 006 DoD-5: one ComposeRejected per rejection, in place --------------------------------

#: (kind, the model's call) — one per gateway-owned rejection kind (DEC-035-17).
REJECTED_CALLS = [
    pytest.param("not_offered", RawCall("ghost_tool", '{"query": "a"}', "prov-1"), id="not-offered"),
    pytest.param("not_offered", RawCall("", '{"query": "a"}', "prov-1"), id="not-offered-empty-name"),
    pytest.param("bad_arguments", RawCall("search_memos", '{"query": ', "prov-1"), id="bad-arguments-unreadable"),
    pytest.param("bad_arguments", RawCall("search_memos", "[1, 2]", "prov-1"), id="bad-arguments-non-object"),
    pytest.param("bad_arguments", RawCall("search_memos", "", None), id="bad-arguments-missing"),
    pytest.param(
        "unknown_argument",
        RawCall("search_memos", '{"query": "a", "undeclared": 1}', "prov-1"),
        id="unknown-argument",
    ),
]


@pytest.mark.parametrize(("kind", "model_call"), REJECTED_CALLS)
def test_compose_yields_one_rejection_between_the_surrounding_text__S035_006_DoD5(
    kind: str, model_call: RawCall
) -> None:
    """S035 006 DoD-5: the rejected call yields exactly one `ComposeRejected` after the text before
    it and before the text after it, carrying `call_1`, the model's name and argument text verbatim
    and the kind; the runner never sees it."""
    runner = RecordingRunner()
    record = LibraryRecord()
    events = compose_events(record, [Delta("before"), model_call, Delta("after")], SEARCH_MEMOS, runner=runner)

    expected = ComposeRejected(
        call=ToolCall(call_id="call_1", name=model_call.name, arguments=model_call.arguments),
        kind=ComposeRejectionKind(kind),
    )
    assert events == [ComposeText("before"), expected, ComposeText("after")]
    rejected = events[1]
    assert isinstance(rejected, ComposeRejected)
    assert isinstance(rejected.kind, ComposeRejectionKind)
    assert rejected.kind == kind
    assert rejected.call.name == model_call.name
    assert rejected.call.arguments == model_call.arguments
    assert runner.calls == []
    assert record.tool_results == []


def test_compose_rejection_kinds_are_the_three_gateway_values__S035_006_DoD5() -> None:
    """S035 006 DoD-5 / DEC-035-17: the kind is one of the gateway's own three values."""
    assert {member.value for member in ComposeRejectionKind} == {"not_offered", "bad_arguments", "unknown_argument"}


def test_compose_rejection_ids_share_the_wrappers_counter__S035_006_DoD5() -> None:
    """S035 006 DoD-5: a wrapper call, a rejection and a wrapper call are `call_1`, `call_2`, `call_3`."""
    runner = RecordingRunner()
    script = [
        Call("search_memos", {"query": "a"}),
        RawCall("ghost_tool", '{"query": "b"}', "prov-7"),
        Call("search_memos", {"query": "c"}),
    ]
    events = compose_events(LibraryRecord(), script, SEARCH_MEMOS, runner=runner)

    assert events == [
        Ev("start:call_1"),
        Ev("end:call_1"),
        ComposeRejected(
            call=ToolCall(call_id="call_2", name="ghost_tool", arguments='{"query": "b"}'),
            kind=ComposeRejectionKind.NOT_OFFERED,
        ),
        Ev("start:call_3"),
        Ev("end:call_3"),
    ]
    assert [call.call_id for call in runner.calls] == ["call_1", "call_3"]


def test_compose_never_uses_the_events_own_call_id__S035_006_DoD5() -> None:
    """S035 006 DoD-5: the event's `call_id` — even one shaped like a minted id — is never used."""
    script = [
        RawCall("ghost_tool", "{}", provider_call_id="call_7"),
        Emit(tool_event("error", "other_ghost", '{"q": 1}', call_id="call_9", error_kind="not_offered")),
    ]
    events = compose_events(LibraryRecord(), script, SEARCH_MEMOS)

    assert [event.call.call_id for event in events] == ["call_1", "call_2"]
    assert [event.call.name for event in events] == ["ghost_tool", "other_ghost"]


@pytest.mark.parametrize("kind", ["not_offered", "bad_arguments", "unknown_argument"])
def test_compose_each_error_event_of_a_rejection_kind_yields_exactly_one_rejection__S035_006_DoD5(
    kind: str,
) -> None:
    """S035 006 DoD-5: one library `error` event of each rejection kind yields exactly one value."""
    event = tool_event("error", "search_memos", '{"query": "z"}', call_id="prov-3", error_kind=kind)
    events = compose_events(LibraryRecord(), [Delta("x"), Emit(event), Delta("y")], SEARCH_MEMOS)

    assert events == [
        ComposeText("x"),
        ComposeRejected(
            call=ToolCall(call_id="call_1", name="search_memos", arguments='{"query": "z"}'),
            kind=ComposeRejectionKind(kind),
        ),
        ComposeText("y"),
    ]


def test_compose_undeclared_argument_is_rejected_by_the_explicit_signature__S035_006_DoD5() -> None:
    """S035 006 DoD-5 / DEC-035-19: with the minted keyword-only signature kept, an undeclared
    argument name is an `unknown_argument` rejection, never a wrapper call."""
    runner = RecordingRunner()
    record = LibraryRecord()
    events = compose_events(
        record, [Call("lookup_notes", {"query": "a", "page": 2})], LOOKUP_NOTES, runner=runner
    )

    assert len(events) == 1
    assert isinstance(events[0], ComposeRejected)
    assert events[0].kind == ComposeRejectionKind.UNKNOWN_ARGUMENT
    assert events[0].call.name == "lookup_notes"
    assert json.loads(events[0].call.arguments) == {"query": "a", "page": 2}
    assert runner.calls == []


# --- S035 006 DoD-6: other events yield nothing and consume no id -------------------------------


def test_compose_ignores_start_result_and_non_rejection_errors__S035_006_DoD6() -> None:
    """S035 006 DoD-6: `start`, `result`, and `error` of kind `tool_raised` / `unserialisable_result`
    yield nothing and consume no `call_id` — the next wrapper call is still `call_1`."""
    script = [
        Delta("a"),
        Emit(tool_event("start", "search_memos", '{"query": "a"}', call_id="prov-1")),
        Emit(tool_event("result", "search_memos", '{"query": "a"}', call_id="prov-1", output="text")),
        Emit(tool_event("error", "search_memos", '{"query": "a"}', call_id="prov-2", error_kind="tool_raised")),
        Emit(
            tool_event(
                "error", "search_memos", '{"query": "a"}', call_id="prov-3", error_kind="unserialisable_result"
            )
        ),
        Delta("b"),
        Call("search_memos", {"query": "c"}),
    ]
    runner = RecordingRunner()
    events = compose_events(LibraryRecord(), script, SEARCH_MEMOS, runner=runner)

    assert events == [ComposeText("a"), ComposeText("b"), Ev("start:call_1"), Ev("end:call_1")]
    assert [call.call_id for call in runner.calls] == ["call_1"]


def test_compose_a_wrapper_call_appears_once_through_the_runner__S035_006_DoD6() -> None:
    """S035 006 DoD-6: a call that reaches a wrapper (the library sends `start` and `result` for it)
    appears in the stream exactly once, through the runner's events."""
    record = LibraryRecord()
    script = [Delta("a"), Call("search_memos", {"query": "a"}), Call("search_memos", {"query": "b"}), Delta("b")]
    events = compose_events(record, script, SEARCH_MEMOS)

    assert events == [
        ComposeText("a"),
        Ev("start:call_1"),
        Ev("end:call_1"),
        Ev("start:call_2"),
        Ev("end:call_2"),
        ComposeText("b"),
    ]
    assert not any(isinstance(event, ComposeRejected) for event in events)
    # The fake library did send the observer a start and a result per call.
    assert [event["type"] for event in record.tool_events] == ["start", "result", "start", "result"]


# --- S035 006 DoD-7: nothing but name and argument text leaves a tool event ----------------------

# Assembled at runtime so no sentinel is a literal in this source (a traceback quoting this file
# can never produce a false positive).
OUTPUT_SENTINEL = "".join(("sntl", "tooloutput", "31c5"))
CALL_ID_SENTINEL = "".join(("sntl", "providercallid", "8d02"))


def test_compose_never_passes_on_output_call_id_or_library_text__S035_006_DoD7(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """S035 006 DoD-7: an event's `output`, its `call_id` and the library's model-facing text reach
    no yielded value and no log record."""
    script = [
        Delta("a"),
        Emit(
            tool_event(
                "result", "search_memos", '{"query": "a"}', call_id=CALL_ID_SENTINEL, output=OUTPUT_SENTINEL
            )
        ),
        Emit(
            tool_event(
                "error",
                "ghost_one",
                '{"query": "a"}',
                call_id=CALL_ID_SENTINEL,
                output=OUTPUT_SENTINEL,
                error_kind="not_offered",
            )
        ),
        RawCall("ghost_two", '{"query": "b"}', CALL_ID_SENTINEL),
        RawCall("search_memos", "{oops", CALL_ID_SENTINEL),
        RawCall("search_memos", '{"query": "c", "undeclared": 1}', CALL_ID_SENTINEL),
        Call("search_memos", {"query": "d"}),
        Delta("b"),
    ]
    record = LibraryRecord()
    gateway = gateway_over(fake_library_class(record, script))

    with captured_log_text(caplog) as lines:
        events = run(drain(gateway.compose(MODEL, MESSAGES, tools_of(RecordingRunner(), SEARCH_MEMOS))))

    rejections = [event for event in events if isinstance(event, ComposeRejected)]
    assert [(r.call.name, r.call.arguments) for r in rejections] == [
        ("ghost_one", '{"query": "a"}'),
        ("ghost_two", '{"query": "b"}'),
        ("search_memos", "{oops"),
        ("search_memos", '{"query": "c", "undeclared": 1}'),
    ]
    assert len(record.told_model) == 3
    surfaces = [repr(event) for event in events] + ["".join(lines), caplog.text]
    forbidden = [OUTPUT_SENTINEL, CALL_ID_SENTINEL, *record.told_model]
    for surface in surfaces:
        for text in forbidden:
            assert text not in surface


# --- S035 006 DoD-8: after a rejection the stream goes on --------------------------------------


def test_compose_stream_continues_after_rejections_and_ends_normally__S035_006_DoD8() -> None:
    """S035 006 DoD-8 / UC-051 / UC-053: after rejections, later text pieces and runner events are
    still yielded, and the stream ends normally when the library call returns."""
    record = LibraryRecord()
    script = [
        Delta("first"),
        RawCall("ghost_tool", '{"query": "a"}'),
        Delta("second"),
        RawCall("search_memos", "not json"),
        Call("search_memos", {"query": "b"}),
        Delta("third"),
    ]
    events = compose_events(record, script, SEARCH_MEMOS)

    assert events == [
        ComposeText("first"),
        ComposeRejected(
            call=ToolCall(call_id="call_1", name="ghost_tool", arguments='{"query": "a"}'),
            kind=ComposeRejectionKind.NOT_OFFERED,
        ),
        ComposeText("second"),
        ComposeRejected(
            call=ToolCall(call_id="call_2", name="search_memos", arguments="not json"),
            kind=ComposeRejectionKind.BAD_ARGUMENTS,
        ),
        Ev("start:call_3"),
        Ev("end:call_3"),
        ComposeText("third"),
    ]
    assert record.tool_results == ["output for call_3"]
    assert (record.entered, record.exited) == (1, 1)


def test_compose_a_rejection_as_the_last_step_still_ends_normally__S035_006_DoD8() -> None:
    """S035 006 DoD-8: a stream whose last library step is a rejection ends without error."""
    events = compose_events(LibraryRecord(), [Delta("only"), RawCall("ghost_tool", "{}")], SEARCH_MEMOS)

    assert events == [
        ComposeText("only"),
        ComposeRejected(
            call=ToolCall(call_id="call_1", name="ghost_tool", arguments="{}"),
            kind=ComposeRejectionKind.NOT_OFFERED,
        ),
    ]


# --- S035 006 DoD-14: the wrapper path is unchanged in tolerant mode ----------------------------


def test_compose_wrapper_path_runs_unchanged_against_the_tolerant_library__S035_006_DoD14() -> None:
    """S035 006 DoD-14: in tolerant mode, step 003's wrapper path holds — ids in invocation order,
    the runner's text returned to the library, runner events between the text in emit order."""
    record = LibraryRecord()
    runner = RecordingRunner()
    script = [
        Delta("before the tool"),
        Call("search_memos", {"query": "a"}),
        Delta("between"),
        Call("lookup_notes", {"query": "b", "limit": 2}),
        Delta("after the tools"),
    ]
    events = compose_events(record, script, SEARCH_MEMOS, LOOKUP_NOTES, runner=runner)

    assert record.calls[0]["tool_errors"] == "result"
    assert events == [
        ComposeText("before the tool"),
        Ev("start:call_1"),
        Ev("end:call_1"),
        ComposeText("between"),
        Ev("start:call_2"),
        Ev("end:call_2"),
        ComposeText("after the tools"),
    ]
    assert [(call.call_id, call.name) for call in runner.calls] == [
        ("call_1", "search_memos"),
        ("call_2", "lookup_notes"),
    ]
    assert json.loads(runner.calls[1].arguments) == {"query": "b", "limit": 2}
    assert record.tool_results == ["output for call_1", "output for call_2"]
    assert record.told_model == []
