"""The one OpenAI-compatible client — models-listing probe, embeddings and streaming chat.

Feature `006`, step `002`. Parameterised by base URL and an already-resolved credential;
there is no branch on provider kind. Resolves no secret, reads no settings, imports no
`fastapi`, touches no database. No log line, exception message or `detail` carries the
credential, the authorization header or a provider response body.

`chat_stream` (feature `021`, step `003`, D10) streams one chat-completions request and
yields the provider's deltas per chunk, unaccumulated; closing the iterator early exits the
httpx stream, which cancels the upstream request.
"""

import json
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import httpx

from app.errors import LlmUnreachableError
from app.services.llm.chat import ChatMessage, to_wire_message


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
class ToolCallDelta:
    """What one provider chunk carried for one tool call — unaccumulated (D10, D11).

    `index` identifies the call within the round; `call_id` / `name` are set only on the
    chunk that carried them; `arguments` is this chunk's argument fragment, verbatim.
    """

    index: int
    call_id: str | None = None
    name: str | None = None
    arguments: str | None = None


@dataclass(frozen=True)
class ChatDelta:
    """One provider chunk's `choices[0].delta` as `chat_stream` yields it (D10).

    `reasoning` comes from the delta's `reasoning_content`, else its `reasoning`.
    """

    content: str | None = None
    reasoning: str | None = None
    tool_calls: tuple[ToolCallDelta, ...] = ()


class LlmClient:
    """One OpenAI-compatible server, addressed by base URL and an optional bearer credential."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        timeout_seconds: float,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def _url(self, path: str) -> str:
        """Compose `<base>/v1/<path>` from a base URL with or without `/` and `/v1`."""
        base = self._base_url.strip().rstrip("/")
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        return f"{base}/{path}"

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _http(self) -> httpx.AsyncClient:
        # A fresh client per call: the timeout and the credential are per server, so no
        # transport is ever shared between two registrations.
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout_seconds),
            transport=self._transport,
        )

    async def probe(self) -> ProbeResult:
        """Issue the models-listing GET and classify it; never raises."""
        try:
            async with self._http() as http:
                response = await http.get(self._url("models"), headers=self._headers())
        except httpx.TimeoutException:
            return ProbeResult(ProbeOutcome.UNREACHABLE, note="timeout")
        except Exception as exc:  # the probe always answers
            return ProbeResult(ProbeOutcome.UNREACHABLE, note=type(exc).__name__)

        if response.status_code in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
            return ProbeResult(ProbeOutcome.AUTH_FAILED, note=f"HTTP {response.status_code}")
        if not response.is_success:
            return ProbeResult(ProbeOutcome.UNREACHABLE, note=f"HTTP {response.status_code}")

        names = _model_names(response)
        if names is None:
            return ProbeResult(ProbeOutcome.UNREACHABLE, note="unreadable models listing")
        if not names:
            return ProbeResult(ProbeOutcome.MODEL_LIST_EMPTY)
        return ProbeResult(ProbeOutcome.REACHABLE, model_names=names)

    async def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
        """Embed `texts` with `model`; one vector per input, in input order.

        Raises `LlmUnreachableError` on any failure, `detail == {"reason": ...}`.
        """
        payload = {"model": model, "input": list(texts)}
        try:
            async with self._http() as http:
                response = await http.post(self._url("embeddings"), headers=self._headers(), json=payload)
        except (httpx.HTTPError, httpx.InvalidURL):
            raise _unreachable(ProbeOutcome.UNREACHABLE.value) from None

        if response.status_code in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
            raise _unreachable(ProbeOutcome.AUTH_FAILED.value)
        if not response.is_success:
            raise _unreachable(ProbeOutcome.UNREACHABLE.value)

        vectors = _embedding_vectors(response, len(texts))
        if vectors is None:
            raise _unreachable(EMBED_NO_VECTOR_REASON)
        return vectors

    async def chat_stream(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        tools: Sequence[Mapping[str, object]],
    ) -> AsyncIterator[ChatDelta]:
        """Stream `POST <base>/v1/chat/completions` and yield one `ChatDelta` per non-empty chunk.

        Body `{"model", "messages": [to_wire_message(m)...], "stream": true}` plus `"tools"`
        only when `tools` is non-empty. Stops at `data: [DONE]` or a clean end of body. A
        non-2xx status (before any delta), a transport error or timeout, or an unparseable
        `data:` payload raises `LlmUnreachableError` via `_unreachable`. `aclose()` exits the
        httpx stream and client contexts.
        """
        payload: dict[str, object] = {
            "model": model,
            "messages": [to_wire_message(message) for message in messages],
            "stream": True,
        }
        if tools:
            payload["tools"] = [dict(tool) for tool in tools]
        try:
            # Both contexts are entered inside the generator, so `aclose()` unwinds them and
            # closing the response stream is what cancels the upstream request.
            async with self._http() as http:
                async with http.stream(
                    "POST", self._url("chat/completions"), headers=self._headers(), json=payload
                ) as response:
                    if response.status_code in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
                        raise _unreachable(ProbeOutcome.AUTH_FAILED.value)
                    if not response.is_success:
                        raise _unreachable(ProbeOutcome.UNREACHABLE.value)
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[len("data:") :]
                        if data.startswith(" "):
                            data = data[1:]
                        if data.strip() == "[DONE]":
                            return
                        if not data.strip():
                            continue
                        delta = _chat_delta(data)
                        if delta is not None:
                            yield delta
        except (httpx.HTTPError, httpx.InvalidURL):
            raise _unreachable(ProbeOutcome.UNREACHABLE.value) from None


def _unreachable(reason: str) -> LlmUnreachableError:
    """The one failure shape `embed` raises: a structured reason and nothing else."""
    return LlmUnreachableError("The LLM server could not produce embeddings.", {"reason": reason})


def _text_or_none(value: object) -> str | None:
    """A non-empty string as-is; anything else (absent, null, `""`, non-string) is `None`."""
    return value if isinstance(value, str) and value else None


def _chat_delta(data: str) -> ChatDelta | None:
    """One `data:` payload's `choices[0].delta`, or `None` when the chunk carries nothing.

    Raises `LlmUnreachableError` when the payload is not JSON.
    """
    try:
        chunk: object = json.loads(data)
    except ValueError:
        raise _unreachable(ProbeOutcome.UNREACHABLE.value) from None
    if not isinstance(chunk, dict):
        return None
    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    delta = choices[0].get("delta")
    if not isinstance(delta, dict):
        return None

    content = _text_or_none(delta.get("content"))
    reasoning = _text_or_none(delta.get("reasoning_content")) or _text_or_none(delta.get("reasoning"))
    tool_calls: list[ToolCallDelta] = []
    raw_calls = delta.get("tool_calls")
    if isinstance(raw_calls, list):
        for position, raw in enumerate(raw_calls):
            if not isinstance(raw, dict):
                continue
            index = raw.get("index", position)
            if isinstance(index, bool) or not isinstance(index, int):
                index = position
            function = raw.get("function")
            if not isinstance(function, dict):
                function = {}
            call_id = raw.get("id")
            name = function.get("name")
            arguments = function.get("arguments")
            tool_calls.append(
                ToolCallDelta(
                    index=index,
                    call_id=call_id if isinstance(call_id, str) else None,
                    name=name if isinstance(name, str) else None,
                    arguments=arguments if isinstance(arguments, str) else None,
                )
            )

    if content is None and reasoning is None and not tool_calls:
        return None
    return ChatDelta(content=content, reasoning=reasoning, tool_calls=tuple(tool_calls))


def _json_body(response: httpx.Response) -> object:
    try:
        body: object = response.json()
    except ValueError:
        return None
    return body


def _model_names(response: httpx.Response) -> tuple[str, ...] | None:
    """The listing's entry ids in server order, or `None` when the body is not a listing."""
    body = _json_body(response)
    if not isinstance(body, dict):
        return None
    data = body.get("data")
    if not isinstance(data, list):
        return None
    names: list[str] = []
    for entry in data:
        if not isinstance(entry, dict):
            return None
        name = entry.get("id")
        if not isinstance(name, str) or not name:
            return None
        names.append(name)
    return tuple(names)


def _embedding_vectors(response: httpx.Response, expected: int) -> list[list[float]] | None:
    """One non-empty float vector per input in input order, or `None` when none is usable."""
    body = _json_body(response)
    if not isinstance(body, dict):
        return None
    data = body.get("data")
    if not isinstance(data, list) or not data or len(data) != expected:
        return None

    entries: list[tuple[int, list[float]]] = []
    for position, entry in enumerate(data):
        if not isinstance(entry, dict):
            return None
        raw = entry.get("embedding")
        if not isinstance(raw, list) or not raw:
            return None
        vector: list[float] = []
        for value in raw:
            if isinstance(value, bool) or not isinstance(value, int | float):
                return None
            vector.append(float(value))
        index = entry.get("index", position)
        if isinstance(index, bool) or not isinstance(index, int):
            return None
        entries.append((index, vector))

    if sorted(index for index, _ in entries) != list(range(expected)):
        return None
    entries.sort(key=lambda item: item[0])
    return [vector for _, vector in entries]
