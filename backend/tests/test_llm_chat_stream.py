"""Tests for ``LlmClient.chat_stream`` and its delta values — feature 021, step 003.

Every expected value comes from ``docs/plans/021.compose-loop-and-tools/003.chat-stream-client.md``
(Interface intent, DoD-1 .. DoD-8), its ``003.context.md`` and the feature ``context.md`` (D4 the
reasoning delta, D10 ``chat_stream`` as built, D11 per-chunk tool-call fragments, 019 D6 / US-132.AC-2
closing the iterator unwinds the httpx stream).

Bindings come from ``status.md`` ``## Skeleton`` -> Step 003 (and Step 002 for ``ChatMessage``):
``ToolCallDelta(index, call_id=None, name=None, arguments=None)``,
``ChatDelta(content=None, reasoning=None, tool_calls=())``,
``LlmClient.chat_stream(model, messages, tools) -> AsyncIterator[ChatDelta]`` (an async generator).

Outbound HTTP is faked with ``httpx.MockTransport`` through the client's ``transport=`` seam, with
streamed SSE bodies; async code runs under ``asyncio.run`` and every wait is bounded. Tests are
suffixed ``__S021_003_DoD<n>``.
"""

import ast
import asyncio
import importlib
import inspect
import json
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Coroutine, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

import app.services.llm.client as client_module
from app.errors import LlmUnreachableError
from app.services.llm.chat import ChatMessage
from app.services.llm.client import ChatDelta, LlmClient, ToolCallDelta

HOST = "http://llm.test:8080"
CHAT_URL = "http://llm.test:8080/v1/chat/completions"
CREDENTIAL = "sk-S021-003-CHAT-CREDENTIAL"
TIMEOUT = 2.5
#: Upper bound on any single test's async work: a hang is a failure, never a stuck suite.
BOUND_SECONDS = 10.0

SYSTEM_USER = [ChatMessage(role="system", content="S"), ChatMessage(role="user", content="U")]

MEMO_TOOL: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "memo_search",
        "description": "Search the character's memos.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
}

Handler = Callable[[httpx.Request], httpx.Response]


# --------------------------------------------------------------------------- helpers


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run one coroutine on a fresh event loop, bounded so a hang fails instead of stalling."""

    async def bounded() -> T:
        return await asyncio.wait_for(coro, timeout=BOUND_SECONDS)

    return asyncio.run(bounded())


class Recorder:
    """An ``httpx.MockTransport`` handler that records every request it is given."""

    def __init__(self, respond: Handler) -> None:
        self.requests: list[httpx.Request] = []
        self._respond = respond

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._respond(request)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


class ChunkStream(httpx.AsyncByteStream):
    """A response body served chunk by chunk, recording how many chunks were pulled and closure."""

    def __init__(self, chunks: Iterable[bytes], fail_after: BaseException | None = None) -> None:
        self.chunks = list(chunks)
        self.served = 0
        self.closed = False
        self._fail_after = fail_after

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            self.served += 1
            yield chunk
        if self._fail_after is not None:
            raise self._fail_after

    async def aclose(self) -> None:
        self.closed = True


def make_client(recorder: Recorder, base_url: str = HOST, api_key: str | None = CREDENTIAL) -> LlmClient:
    return LlmClient(base_url, api_key, TIMEOUT, transport=recorder.transport)


def data(payload: Mapping[str, Any], *, ensure_ascii: bool = False) -> str:
    """One SSE ``data:`` event carrying ``payload`` as JSON."""
    return "data: " + json.dumps(payload, ensure_ascii=ensure_ascii) + "\n\n"


DONE = "data: [DONE]\n\n"


def chunk(delta: Mapping[str, Any]) -> dict[str, Any]:
    """An OpenAI-compatible streaming chunk whose ``choices[0].delta`` is ``delta``."""
    return {
        "id": "chatcmpl-S021",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "m1",
        "choices": [{"index": 0, "delta": dict(delta), "finish_reason": None}],
    }


def content(text: str) -> str:
    return data(chunk({"content": text}))


def sse_response(*events: str, status: int = 200) -> httpx.Response:
    body = "".join(events).encode("utf-8")
    return httpx.Response(status, headers={"content-type": "text/event-stream"}, content=body)


def streamed(stream: ChunkStream, status: int = 200) -> httpx.Response:
    return httpx.Response(status, headers={"content-type": "text/event-stream"}, stream=stream)


def answering(*events: str, status: int = 200) -> Handler:
    def respond(request: httpx.Request) -> httpx.Response:
        return sse_response(*events, status=status)

    return respond


def raising(error_type: type[httpx.TransportError]) -> Handler:
    def respond(request: httpx.Request) -> httpx.Response:
        raise error_type("simulated transport failure", request=request)

    return respond


async def _drain(iterator: AsyncIterator[ChatDelta], sink: list[ChatDelta]) -> None:
    async for delta in iterator:
        sink.append(delta)


def collect(
    client: LlmClient,
    messages: Sequence[ChatMessage] = SYSTEM_USER,
    tools: Sequence[Mapping[str, object]] = (),
    model: str = "m1",
) -> list[ChatDelta]:
    sink: list[ChatDelta] = []
    run(_drain(client.chat_stream(model, messages, tools), sink))
    return sink


def collect_until_error(client: LlmClient) -> tuple[list[ChatDelta], LlmUnreachableError]:
    sink: list[ChatDelta] = []
    with pytest.raises(LlmUnreachableError) as caught:
        run(_drain(client.chat_stream("m1", SYSTEM_USER, []), sink))
    return sink, caught.value


def contents(deltas: Sequence[ChatDelta]) -> list[str | None]:
    return [delta.content for delta in deltas]


# --------------------------------------------------------------------------- DoD-1


@pytest.mark.parametrize(
    "base_url",
    ["http://llm.test:8080", "http://llm.test:8080/", "http://llm.test:8080/v1", "http://llm.test:8080/v1/"],
)
def test_one_post_to_the_chat_completions_endpoint_for_each_base_url_form__S021_003_DoD1(base_url: str) -> None:
    """DoD-1: with or without a trailing ``/v1`` the stream POSTs once to ``<base>/v1/chat/completions``."""
    recorder = Recorder(answering(DONE))
    collect(make_client(recorder, base_url=base_url))
    assert len(recorder.requests) == 1
    request = recorder.requests[0]
    assert request.method == "POST"
    assert str(request.url) == CHAT_URL


def test_the_body_is_exactly_model_messages_and_stream_without_tools__S021_003_DoD1() -> None:
    """DoD-1: with no tools the JSON body is exactly ``{model, messages, stream: true}`` — no ``tools`` key."""
    recorder = Recorder(answering(DONE))
    collect(make_client(recorder), SYSTEM_USER, [])
    body = json.loads(recorder.requests[0].content)
    assert body == {
        "model": "m1",
        "messages": [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}],
        "stream": True,
    }
    assert "tools" not in body


def test_one_tool_definition_is_sent_as_the_tools_list__S021_003_DoD1() -> None:
    """DoD-1: with one tool definition the body also carries ``tools`` equal to that list."""
    recorder = Recorder(answering(DONE))
    collect(make_client(recorder), SYSTEM_USER, [MEMO_TOOL])
    body = json.loads(recorder.requests[0].content)
    assert body == {
        "model": "m1",
        "messages": [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}],
        "stream": True,
        "tools": [MEMO_TOOL],
    }


def test_the_bearer_header_is_sent_when_the_client_has_a_key__S021_003_DoD1() -> None:
    """DoD-1: a keyed client sends ``Authorization: Bearer <key>``."""
    recorder = Recorder(answering(DONE))
    collect(make_client(recorder, api_key=CREDENTIAL))
    assert recorder.requests[0].headers["authorization"] == f"Bearer {CREDENTIAL}"


def test_no_authorization_header_without_a_key__S021_003_DoD1() -> None:
    """DoD-1: a key-less client sends no authorization header at all."""
    recorder = Recorder(answering(DONE))
    collect(make_client(recorder, api_key=None))
    assert "authorization" not in recorder.requests[0].headers


# --------------------------------------------------------------------------- DoD-2


def test_content_deltas_stop_at_done__S021_003_DoD2() -> None:
    """DoD-2: ``Hel``, ``lo``, ``[DONE]``, then more -> exactly two deltas, nothing after ``[DONE]``."""
    recorder = Recorder(answering(content("Hel"), content("lo"), DONE, content("after done")))
    deltas = collect(make_client(recorder))
    assert contents(deltas) == ["Hel", "lo"]
    for delta in deltas:
        assert isinstance(delta, ChatDelta)
        assert delta.reasoning is None
        assert tuple(delta.tool_calls) == ()


def test_blank_comment_and_event_lines_are_ignored__S021_003_DoD2() -> None:
    """DoD-2: blank lines, ``:`` comments and ``event:`` lines yield nothing and disturb nothing."""
    recorder = Recorder(
        answering(
            ": keep-alive\n\n",
            "\n",
            "event: message\n",
            content("Hel"),
            ": another comment\n",
            "\n\n",
            "event: ping\n\n",
            content("lo"),
            DONE,
        )
    )
    assert contents(collect(make_client(recorder))) == ["Hel", "lo"]


def test_a_chunk_with_empty_choices_yields_nothing__S021_003_DoD2() -> None:
    """DoD-2: a chunk whose ``choices`` list is empty (e.g. a usage chunk) yields no delta."""
    usage_chunk = {
        "id": "chatcmpl-S021",
        "object": "chat.completion.chunk",
        "choices": [],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }
    recorder = Recorder(answering(content("Hel"), data(usage_chunk), content("lo"), DONE))
    assert contents(collect(make_client(recorder))) == ["Hel", "lo"]


def test_a_data_line_without_the_space_is_still_a_payload__S021_003_DoD2() -> None:
    """DoD-2 (Interface intent: one leading space dropped, not required): ``data:{...}`` is read too."""
    no_space = "data:" + json.dumps(chunk({"content": "Hel"})) + "\n\n"
    recorder = Recorder(answering(no_space, content("lo"), "data:[DONE]\n\n", content("after")))
    assert contents(collect(make_client(recorder))) == ["Hel", "lo"]


@pytest.mark.parametrize("ensure_ascii", [False, True], ids=["raw-utf8", "json-escaped"])
def test_cyrillic_content_arrives_intact__S021_003_DoD2(ensure_ascii: bool) -> None:
    """DoD-2: Cyrillic content arrives intact, whether sent as raw UTF-8 or as JSON escapes."""
    events = [
        data(chunk({"content": "Привет, "}), ensure_ascii=ensure_ascii),
        data(chunk({"content": "мир — ёж"}), ensure_ascii=ensure_ascii),
        DONE,
    ]
    recorder = Recorder(answering(*events))
    assert contents(collect(make_client(recorder))) == ["Привет, ", "мир — ёж"]


def test_cyrillic_split_across_network_chunks_arrives_intact__S021_003_DoD2() -> None:
    """DoD-2: a multi-byte character and a line split across two body chunks still arrive intact."""
    line = data(chunk({"content": "Привет"})).encode("utf-8")
    cut = line.index("Привет".encode()) + 1  # inside the two-byte "П"
    stream = ChunkStream([line[:cut], line[cut:], DONE.encode("utf-8")])
    recorder = Recorder(lambda request: streamed(stream))
    assert contents(collect(make_client(recorder))) == ["Привет"]


# --------------------------------------------------------------------------- DoD-3


def test_reasoning_content_becomes_reasoning__S021_003_DoD3() -> None:
    """DoD-3 (D4): a delta carrying ``reasoning_content`` ``r1`` yields ``reasoning`` ``r1``."""
    recorder = Recorder(answering(data(chunk({"reasoning_content": "r1"})), DONE))
    deltas = collect(make_client(recorder))
    assert len(deltas) == 1
    assert deltas[0].reasoning == "r1"
    assert deltas[0].content is None
    assert tuple(deltas[0].tool_calls) == ()


def test_reasoning_field_becomes_reasoning__S021_003_DoD3() -> None:
    """DoD-3 (D4): a delta carrying ``reasoning`` ``r2`` yields ``reasoning`` ``r2``."""
    recorder = Recorder(answering(data(chunk({"reasoning": "r2"})), DONE))
    deltas = collect(make_client(recorder))
    assert len(deltas) == 1
    assert deltas[0].reasoning == "r2"
    assert deltas[0].content is None


def test_content_and_reasoning_in_one_delta_are_both_kept__S021_003_DoD3() -> None:
    """DoD-3: one delta carrying both content and reasoning yields one delta holding both."""
    recorder = Recorder(answering(data(chunk({"content": "c", "reasoning_content": "r"})), DONE))
    deltas = collect(make_client(recorder))
    assert len(deltas) == 1
    assert (deltas[0].content, deltas[0].reasoning) == ("c", "r")


def test_reasoning_and_content_deltas_keep_arrival_order__S021_003_DoD3() -> None:
    """DoD-3: a reasoning delta then a content delta come through as two deltas, in order."""
    recorder = Recorder(
        answering(data(chunk({"reasoning_content": "think"})), data(chunk({"content": "say"})), DONE)
    )
    deltas = collect(make_client(recorder))
    assert [(delta.reasoning, delta.content) for delta in deltas] == [("think", None), (None, "say")]


# --------------------------------------------------------------------------- DoD-4


TOOL_CHUNKS = [
    {"tool_calls": [{"index": 0, "id": "call_a", "type": "function",
                     "function": {"name": "memo_search", "arguments": ""}}]},
    {"tool_calls": [{"index": 0, "function": {"arguments": "{\"query\":"}}]},
    {"tool_calls": [{"index": 0, "function": {"arguments": "\"inn\"}"}}]},
]


def test_tool_call_fragments_pass_through_per_chunk_unaccumulated__S021_003_DoD4() -> None:
    """DoD-4 (D10, D11): three tool-call chunks -> three deltas carrying exactly each chunk's values."""
    recorder = Recorder(answering(*(data(chunk(delta)) for delta in TOOL_CHUNKS), DONE))
    deltas = collect(make_client(recorder))
    assert len(deltas) == 3
    assert [tuple(delta.tool_calls) for delta in deltas] == [
        (ToolCallDelta(index=0, call_id="call_a", name="memo_search", arguments=""),),
        (ToolCallDelta(index=0, call_id=None, name=None, arguments="{\"query\":"),),
        (ToolCallDelta(index=0, call_id=None, name=None, arguments="\"inn\"}"),),
    ]
    for delta in deltas:
        assert delta.content is None
        assert delta.reasoning is None


def test_tool_call_delta_fields_are_read_individually__S021_003_DoD4() -> None:
    """DoD-4: id and name only on the first fragment; the argument fragments exactly as given."""
    recorder = Recorder(answering(*(data(chunk(delta)) for delta in TOOL_CHUNKS), DONE))
    calls = [tuple(delta.tool_calls)[0] for delta in collect(make_client(recorder))]
    assert [call.index for call in calls] == [0, 0, 0]
    assert [call.call_id for call in calls] == ["call_a", None, None]
    assert [call.name for call in calls] == ["memo_search", None, None]
    assert [call.arguments for call in calls] == ["", "{\"query\":", "\"inn\"}"]
    assert "".join(call.arguments or "" for call in calls) == "{\"query\":\"inn\"}"


# --------------------------------------------------------------------------- DoD-5


def test_a_body_ending_without_done_ends_iteration_normally__S021_003_DoD5() -> None:
    """DoD-5: a clean end of body with no ``[DONE]`` ends iteration after its deltas, raising nothing."""
    recorder = Recorder(answering(content("Hel"), content("lo")))
    assert contents(collect(make_client(recorder))) == ["Hel", "lo"]


def test_a_streamed_body_ending_without_done_ends_normally__S021_003_DoD5() -> None:
    """DoD-5: the same over a body served in separate chunks, with no ``[DONE]`` at its end."""
    stream = ChunkStream([content("Hel").encode("utf-8"), content("lo").encode("utf-8")])
    recorder = Recorder(lambda request: streamed(stream))
    assert contents(collect(make_client(recorder))) == ["Hel", "lo"]


# --------------------------------------------------------------------------- DoD-6


def test_a_500_raises_llm_unreachable_before_any_delta__S021_003_DoD6() -> None:
    """DoD-6: a 500 response raises ``llm_unreachable`` and yields no delta, even if its body has data lines."""
    recorder = Recorder(answering(content("should not surface"), DONE, status=500))
    deltas, error = collect_until_error(make_client(recorder))
    assert deltas == []
    assert error.code == "llm_unreachable"


def test_a_401_raises_llm_unreachable__S021_003_DoD6() -> None:
    """DoD-6 (US-044.AC-2): a 401 response raises ``llm_unreachable`` with no delta."""
    recorder = Recorder(lambda request: httpx.Response(401, json={"error": {"message": "bad key"}}))
    deltas, error = collect_until_error(make_client(recorder))
    assert deltas == []
    assert isinstance(error, LlmUnreachableError)
    assert error.code == "llm_unreachable"


def test_a_connect_error_raises_llm_unreachable__S021_003_DoD6() -> None:
    """DoD-6: a transport ``ConnectError`` raises ``llm_unreachable``."""
    deltas, error = collect_until_error(make_client(Recorder(raising(httpx.ConnectError))))
    assert deltas == []
    assert error.code == "llm_unreachable"


def test_a_read_timeout_raises_llm_unreachable__S021_003_DoD6() -> None:
    """DoD-6: a ``ReadTimeout`` raises ``llm_unreachable``."""
    deltas, error = collect_until_error(make_client(Recorder(raising(httpx.ReadTimeout))))
    assert deltas == []
    assert error.code == "llm_unreachable"


def test_a_read_timeout_mid_body_raises_after_the_earlier_deltas__S021_003_DoD6() -> None:
    """DoD-6: a timeout while the body is streaming raises ``llm_unreachable`` after the deltas before it."""
    stream = ChunkStream(
        [content("Hel").encode("utf-8")],
        fail_after=httpx.ReadTimeout("simulated read timeout"),
    )
    recorder = Recorder(lambda request: streamed(stream))
    deltas, error = collect_until_error(make_client(recorder))
    assert contents(deltas) == ["Hel"]
    assert error.code == "llm_unreachable"


def test_an_unparseable_data_line_raises_after_the_earlier_deltas__S021_003_DoD6() -> None:
    """DoD-6: a ``data:`` payload that is not JSON raises ``llm_unreachable`` after the deltas before it."""
    recorder = Recorder(answering(content("Hel"), "data: {this is not json\n\n", content("lo"), DONE))
    deltas, error = collect_until_error(make_client(recorder))
    assert contents(deltas) == ["Hel"]
    assert error.code == "llm_unreachable"


# --------------------------------------------------------------------------- DoD-7


def test_closing_after_the_first_delta_closes_the_response_stream__S021_003_DoD7() -> None:
    """DoD-7 (US-132.AC-2, 019 D6): ``aclose`` after the first delta closes the body; no further chunk is read."""
    stream = ChunkStream(
        [
            content("first").encode("utf-8"),
            content("second").encode("utf-8"),
            content("third").encode("utf-8"),
            DONE.encode("utf-8"),
        ]
    )
    recorder = Recorder(lambda request: streamed(stream))
    client = make_client(recorder)

    async def scenario() -> ChatDelta:
        iterator = client.chat_stream("m1", SYSTEM_USER, [])
        first = await iterator.__anext__()
        await cast(AsyncGenerator[ChatDelta, None], iterator).aclose()
        return first

    first = run(scenario())
    assert first.content == "first"
    assert stream.closed is True
    assert stream.served == 1


def test_a_closed_iterator_yields_nothing_more__S021_003_DoD7() -> None:
    """DoD-7: after ``aclose`` the iterator is finished — the pending body never surfaces as deltas."""
    stream = ChunkStream([content("first").encode("utf-8"), content("second").encode("utf-8")])
    recorder = Recorder(lambda request: streamed(stream))
    client = make_client(recorder)

    async def scenario() -> list[ChatDelta]:
        iterator = client.chat_stream("m1", SYSTEM_USER, [])
        await iterator.__anext__()
        await cast(AsyncGenerator[ChatDelta, None], iterator).aclose()
        rest: list[ChatDelta] = []
        async for delta in iterator:
            rest.append(delta)
        return rest

    assert run(scenario()) == []
    assert stream.closed is True


# --------------------------------------------------------------------------- DoD-8


def _client_imports() -> list[str]:
    source_file = inspect.getsourcefile(client_module)
    assert source_file is not None
    tree = ast.parse(Path(source_file).read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = "app.services.llm" if node.level == 1 else "app.services"
                names.append(f"{base}.{node.module}" if node.module else base)
            else:
                names.append(node.module or "")
    return names


def test_client_still_imports_no_fastapi_no_secrets_and_no_database__S021_003_DoD8() -> None:
    """DoD-8 (D10): adding ``chat_stream`` brought in no ``fastapi``, no ``app.secrets`` and nothing of ``app.db``."""
    forbidden = ("fastapi", "app.secrets", "app.db")
    offenders = [
        name for name in _client_imports()
        if any(name == root or name.startswith(root + ".") for root in forbidden)
    ]
    assert offenders == []
    secrets_module = importlib.import_module("app.secrets")
    for name, value in vars(client_module).items():
        if name.startswith("__"):
            continue
        assert value is not secrets_module, name


def test_chat_stream_now_exists_on_the_client__S021_003_DoD8() -> None:
    """DoD-8: the absence tests are gone because ``chat_stream`` is now part of the client."""
    assert hasattr(LlmClient, "chat_stream")
    iterator = make_client(Recorder(answering(DONE))).chat_stream("m1", SYSTEM_USER, [])
    assert hasattr(iterator, "__anext__")
    run(cast(AsyncGenerator[ChatDelta, None], iterator).aclose())
