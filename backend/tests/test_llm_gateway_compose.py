"""`LlmGateway.compose` over the library's streaming tool loop (feature 035, step 003).

Covers DoD-3..14: the `chat_with_tools` call shape, replayed history, verbatim text pieces, the
minted, signature-bearing tool callables, one ordered stream of text and runner events, how the
stream ends, fails and is closed, the no-tools case, and one library client per call.
Decisions: DEC-035-3 (the `library_clients` seam), DEC-035-4, DEC-035-6 (`ComposeTools` and the
wrapper), DEC-035-7 (one queue; cancel-and-await on close), DEC-035-8 (failure mapping),
DEC-035-10 (the tool loop even with no tools), `DEC-arch-llm-client-library-4`, `-5`, `-6`, `-8`.

No HTTP: the gateway is given a fake library client class through its keyword-only
`library_clients` map (`DEC-arch-llm-client-library-11`). The fake's `chat_with_tools` imitates
the library's 0.2.0 tool-call contract (`003.context.md`): the pre-flight check that every
advertised tool has a callable, `on_delta` with scripted pieces (awaited when awaitable), the
offered-name check, the `inspect.signature` argument-name check, the call with keyword arguments
(awaited when awaitable), an `Exception` from the callable re-raised as `RuntimeError`, and a
`CancelledError` passed through untouched. Async code is driven with `asyncio.run` from sync
tests (the suite has no pytest-asyncio).
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
from app.services.llm.gateway import ComposeText, ComposeTools, LlmGateway

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


Step = Delta | Call | Fail | Block


@dataclass
class LibraryRecord:
    """What the fake library classes observed, shared by every instance one test builds."""

    constructed: list[dict[str, Any]] = field(default_factory=list)
    entered: int = 0
    exited: int = 0
    calls: list[dict[str, Any]] = field(default_factory=list)
    open_during_call: list[bool] = field(default_factory=list)
    tool_results: list[object] = field(default_factory=list)
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

    It accepts the four construction keywords DEC-035-3 names and is an async context manager.
    With `require_token` it imitates `OpenAIAPIClient`, which refuses an empty bearer token with a
    `ValueError` at construction (`DEC-arch-llm-client-library-9`).
    """

    class FakeToolLibraryClient:
        def __init__(self, *, model: str, base_url: str, timeout: float, bearer_token: str | None = None) -> None:
            if require_token and not bearer_token:
                raise ValueError(f"OpenAI credential not provided for {PROVIDER_HOST}")
            record.constructed.append(
                {"model": model, "base_url": base_url, "timeout": timeout, "bearer_token": bearer_token}
            )
            self._open = False

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
                }
            )
            record.open_during_call.append(self._open)
            # 0.2.0 pre-flight: every advertised name needs a callable, before any request.
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
                # 0.2.0 order: offered check, argument-name check against the signature, then run.
                if step.name not in offered:
                    raise LLMError(f"Model called tool '{step.name}' which was not offered", PROVIDER_BODY)
                func = tools[step.name]
                parameters = inspect.signature(func).parameters
                if not all(name in parameters for name in step.kwargs):
                    raise ValueError(f"Bad args for tool '{step.name}': {PROVIDER_BODY}")
                try:
                    result = func(**step.kwargs)
                    if inspect.isawaitable(result):
                        result = await result
                except Exception as exc:
                    raise RuntimeError(f"Tool '{step.name}' failed: {exc}") from exc
                record.tool_results.append(result)
            elif isinstance(step, Fail):
                raise step.error
            else:
                step.reached.set()
                await step.release.wait()

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


def _llm_error(message: str) -> LLMError:
    """An `LLMError` shaped like the library's, carrying the provider markers."""
    return LLMError(message, PROVIDER_BODY)


LIBRARY_FAILURES = [
    pytest.param(
        _llm_error(f"Request to http://{PROVIDER_HOST}/v1/responses failed with status 401"),
        "auth_failed",
        id="status-401",
    ),
    pytest.param(
        _llm_error(f"Request to http://{PROVIDER_HOST}/v1/responses failed with status 403"),
        "auth_failed",
        id="status-403",
    ),
    pytest.param(
        _llm_error(f"Request to http://{PROVIDER_HOST}/v1/responses failed with status 500"),
        "unreachable",
        id="status-500",
    ),
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


def test_compose_unoffered_tool_name_is_unreachable__DoD10(caplog: pytest.LogCaptureFixture) -> None:
    """DoD-10 (temporary limitation): the library rejecting an unoffered tool → `unreachable`."""
    seen, error, log_text = _failing_compose([Delta("partial"), Call("not_offered", {"query": "a"})], caplog)

    assert seen == [ComposeText("partial")]
    _assert_clean_unreachable(error, "unreachable", log_text)


def test_compose_unknown_argument_name_is_unreachable__DoD10(caplog: pytest.LogCaptureFixture) -> None:
    """DoD-10 (temporary limitation): an argument name outside the signature → `unreachable`."""
    script = [Delta("partial"), Call("search_memos", {"query": "a", "undeclared": 1})]
    seen, error, log_text = _failing_compose(script, caplog)

    assert seen == [ComposeText("partial")]
    _assert_clean_unreachable(error, "unreachable", log_text)


def test_compose_unparseable_arguments_is_unreachable__DoD10(caplog: pytest.LogCaptureFixture) -> None:
    """DoD-10 (temporary limitation): the library's `LLMError` on unparseable arguments → `unreachable`."""
    error_in = _llm_error(f"Arguments for tool 'search_memos' from {PROVIDER_HOST} are not valid JSON")
    seen, error, log_text = _failing_compose([Delta("partial"), Fail(error_in)], caplog)

    assert seen == [ComposeText("partial")]
    _assert_clean_unreachable(error, "unreachable", log_text)


def test_compose_runner_exception_surfacing_as_runtime_error_is_unreachable__DoD10(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """DoD-10: the library's `RuntimeError` for a raising tool → `unreachable`; prior emits still yielded."""

    async def raising_runner(call: ToolCall, emit: Callable[[Ev], None]) -> str:
        emit(Ev("before the failure"))
        raise KeyError(f"{PROVIDER_HOST} {PROVIDER_BODY}")

    seen, error, log_text = _failing_compose(
        [Delta("partial"), Call("search_memos", {"query": "a"})], caplog, runner=raising_runner
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
