"""The one OpenAI-compatible client — models-listing probe and embeddings.

Feature `006`, step `002`. Parameterised by base URL and an already-resolved credential;
there is no branch on provider kind. Resolves no secret, reads no settings, imports no
`fastapi`, touches no database. No log line, exception message or `detail` carries the
credential, the authorization header or a provider response body.

`chat_stream` is deliberately absent (features `019`/`021`).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import httpx

from app.errors import LlmUnreachableError


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


def _unreachable(reason: str) -> LlmUnreachableError:
    """The one failure shape `embed` raises: a structured reason and nothing else."""
    return LlmUnreachableError("The LLM server could not produce embeddings.", {"reason": reason})


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
