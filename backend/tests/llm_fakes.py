"""The shared provider fake for feature 024 — one fake client, one fake factory, one pure
deterministic vector function.

Owned by feature 024 step `002`'s test-coder; **steps 003, 004, 005 and 006 import it**.
Its contract comes from `docs/plans/024.embedding-lifecycle/context.md` ("Test conventions"
-> "`backend/tests/llm_fakes.py`") and `002.context.md` ("The fake — what it must offer").
Nothing here was derived from any implementation.

Feature 035 step 002 moved the factory to the four-argument seam
`(kind, base_url, api_key, timeout_seconds)` (DEC-035-1) and the probe types to
`app.services.llm.gateway` (DEC-035-2); helper names are unchanged.

The public contract — bind to this, do not re-read the tests that use it
=======================================================================

`embedding_vector(text, dim) -> list[float]`
    A **pure function**. Same `(text, dim)` always gives the same list; **different texts
    give different vectors**; the length is exactly `dim`. Every component is a multiple of
    2**-8 in `[-0.5, 0.49609375]`, so the value is **exactly representable as float32** and
    a round-trip through `sqlite_vec.serialize_float32` / `struct.unpack("<{dim}f", ...)`
    compares **equal**, with no tolerance. This is the function a test calls to compute the
    vector it expects to find stored for a composed text.

`vectors_for(texts, dim) -> list[list[float]]`
    `[embedding_vector(text, dim) for text in texts]` — the expected answer of one
    `embed_texts(handle, texts)` call, in input order.

`FakeEmbeddingClient`
    Satisfies the registry's `LlmClientLike` protocol (`probe` + `embed`). Attributes:

    - `dim: int` — the dimension its vectors have.
    - `embed_calls: list[tuple[str, tuple[str, ...]]]` — **every** `embed` call, appended in
      call order, as `(model_name, tuple(texts))`. So `len(client.embed_calls)` is the call
      count and `client.embed_calls[0][1]` is the exact batch, in order.
    - `probe_calls: int`.

    Scripting (both are what the failure DoDs need):

    - `error: Exception | None` — raised by `embed` **after** the call is recorded.
    - `returned_length: int | None` — when set, `embed` returns vectors of **that** length
      instead of `dim`, which is the wrong-length / dimension-mismatch case.

`FakeClientFactory`
    A callable matching `LlmClientFactory = Callable[[str, str, str | None, float], LlmClientLike]`
    — the four-argument `(kind, base_url, api_key, timeout_seconds)` seam of feature 035
    (DEC-035-1).

    - `calls: list[tuple[str, str | None, float]]` — `(base_url, api_key, timeout_seconds)`
      per construction, in order. Kept three-wide so the many modules that unpack it are
      untouched.
    - `kinds: list[str]` — the `kind` each construction was called with, in the same order
      (feature 035 step 002, DoD-6..8).
    - `full_calls: list[tuple[str, str, str | None, float]]` — the whole four-argument call,
      `(kind, base_url, api_key, timeout_seconds)`, per construction.
    - `call_count: int` — the number of constructions. **`factory.call_count == 0` is the
      direct assertion for "this write did no vector work"**, which D5's no-vector-work
      clauses use throughout the feature.
    - `clients: list[FakeEmbeddingClient]` — one per construction.
    - `embed_calls` — every client's `embed_calls`, concatenated in construction order. For
      the usual one-client write operation (D1) this is the whole embed history, so
      `factory.embed_calls == [(MODEL, ("a", "b"))]` asserts "exactly one call carrying
      these texts in this order".

Constructors, for readability at the call site:

- `fake_factory(dim=...)` — the happy path.
- `wrong_length_factory(dim=..., returned_length=...)` — vectors of the wrong length.
- `unreachable_factory(dim=..., reason=...)` — `embed` raises `LlmUnreachableError` with
  `detail={"reason": reason}`; the error object is also exposed as `factory.error`.

No network, no event loop of its own, no monkeypatching: every user injects the factory
through the service's frozen `client_factory=` keyword seam.

Library-level fakes (feature 035 step 002)
==========================================

`LibraryEmbedRecorder`
    Stands in for the `llm-client` library *under* a real `LlmGateway`, through the
    gateway's keyword-only `library_clients` seam (DEC-035-3). `recorder.library_clients`
    is a `{kind: class}` mapping for `"llamaswap"` and `"openai"`; each class accepts the
    library constructor keywords (`model`, `base_url`, `timeout`, `bearer_token`), is an async
    context manager, and offers an async `embed_batch(texts)`. The `"openai"` class refuses
    an empty bearer token with `ValueError` at construction, as the real `OpenAIAPIClient`
    does (feature 035 `context.md`, "Library facts"). It records constructions, enters,
    exits and `embed_batch` calls, and answers `vectors` or raises `error` (a real
    `llm.LLMError` in tests).

`gateway_factory(recorder)`
    A four-argument factory `(kind, base_url, api_key, timeout_seconds)` that builds a real
    `LlmGateway` over the recorder's classes — what a test passes as `client_factory=` when
    it wants the production gateway in the path without a network.
"""

import hashlib
from collections.abc import Callable, Sequence
from typing import Any

from app.errors import LlmUnreachableError
from app.services.llm.gateway import LlmGateway, ProbeOutcome, ProbeResult

#: The dimension feature 024's tests designate; 8 keeps them fast (``context.md``).
FAKE_EMBEDDING_DIM = 8

#: The model name a fake answers ``probe`` with. Not the designated name — tests seed that.
PROBE_MODEL_NAME = "fake-probe-model"


def embedding_vector(text: str, dim: int) -> list[float]:
    """The deterministic, pure vector of ``text`` at ``dim`` — exactly float32-representable.

    Derived from a SHAKE-256 extendable digest of the UTF-8 text, one byte per component,
    mapped to ``(byte - 128) / 256``. Every value is therefore a multiple of ``2 ** -8``
    strictly inside ``(-1, 1)``: exact in float32, so a round-trip through
    ``sqlite_vec.serialize_float32`` compares equal with no tolerance.
    """
    if dim < 0:
        raise ValueError("dim must not be negative")
    digest = hashlib.shake_256(text.encode("utf-8")).digest(dim)
    return [(byte - 128) / 256.0 for byte in digest]


def vectors_for(texts: Sequence[str], dim: int) -> list[list[float]]:
    """The expected answer of one embed of ``texts`` — one vector per text, in input order."""
    return [embedding_vector(text, dim) for text in texts]


class FakeEmbeddingClient:
    """A fake provider client: records every ``embed`` call, then answers or raises."""

    def __init__(
        self,
        *,
        dim: int,
        error: Exception | None = None,
        returned_length: int | None = None,
    ) -> None:
        self.dim = dim
        self.error = error
        self.returned_length = returned_length
        self.embed_calls: list[tuple[str, tuple[str, ...]]] = []
        self.probe_calls = 0

    async def probe(self) -> ProbeResult:
        self.probe_calls += 1
        return ProbeResult(outcome=ProbeOutcome.REACHABLE, model_names=(PROBE_MODEL_NAME,))

    async def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
        """One deterministic vector per input text, in input order — unless scripted otherwise."""
        self.embed_calls.append((model, tuple(texts)))
        if self.error is not None:
            raise self.error
        length = self.dim if self.returned_length is None else self.returned_length
        return vectors_for(list(texts), length)


class FakeClientFactory:
    """A client factory recording every construction, and counting them."""

    def __init__(
        self,
        *,
        dim: int = FAKE_EMBEDDING_DIM,
        error: Exception | None = None,
        returned_length: int | None = None,
    ) -> None:
        self.dim = dim
        self.error = error
        self.returned_length = returned_length
        self.calls: list[tuple[str, str | None, float]] = []
        self.kinds: list[str] = []
        self.full_calls: list[tuple[str, str, str | None, float]] = []
        self.clients: list[FakeEmbeddingClient] = []

    def __call__(
        self, kind: str, base_url: str, api_key: str | None, timeout_seconds: float
    ) -> FakeEmbeddingClient:
        """Build one fake client, recording the four-argument factory call (DEC-035-1)."""
        self.calls.append((base_url, api_key, timeout_seconds))
        self.kinds.append(kind)
        self.full_calls.append((kind, base_url, api_key, timeout_seconds))
        client = FakeEmbeddingClient(dim=self.dim, error=self.error, returned_length=self.returned_length)
        self.clients.append(client)
        return client

    @property
    def call_count(self) -> int:
        """How many clients were constructed. ``== 0`` means no vector work happened."""
        return len(self.calls)

    @property
    def embed_calls(self) -> list[tuple[str, tuple[str, ...]]]:
        """Every ``embed`` call of every client it built, in order."""
        return [call for client in self.clients for call in client.embed_calls]

    @property
    def probe_calls(self) -> int:
        return sum(client.probe_calls for client in self.clients)


def fake_factory(dim: int = FAKE_EMBEDDING_DIM) -> FakeClientFactory:
    """The happy-path factory: its clients answer ``embedding_vector(text, dim)`` per text."""
    return FakeClientFactory(dim=dim)


def wrong_length_factory(
    dim: int = FAKE_EMBEDDING_DIM,
    returned_length: int = FAKE_EMBEDDING_DIM - 1,
) -> FakeClientFactory:
    """A factory whose clients answer vectors of ``returned_length``, not ``dim``."""
    return FakeClientFactory(dim=dim, returned_length=returned_length)


def unreachable_factory(
    dim: int = FAKE_EMBEDDING_DIM,
    reason: str = ProbeOutcome.UNREACHABLE.value,
) -> FakeClientFactory:
    """A factory whose clients raise ``LlmUnreachableError`` from ``embed`` (after recording it)."""
    error = LlmUnreachableError("the fake provider could not produce embeddings", {"reason": reason})
    return FakeClientFactory(dim=dim, error=error)


# --------------------------------------------------------------------------- library-level fakes


class LibraryEmbedRecorder:
    """Records what a real ``LlmGateway`` does to its library clients during ``embed``.

    The classes it hands out are built fresh per recorder, so parallel tests never share
    state (DEC-035-3 rejected module-global patching for exactly that reason).
    """

    def __init__(
        self,
        *,
        vectors: Sequence[Sequence[float]] | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.vectors: list[list[float]] | None = None if vectors is None else [list(v) for v in vectors]
        self.error = error
        #: One dict per construction: the keyword view of the constructor call, plus ``kind``.
        self.constructions: list[dict[str, Any]] = []
        #: Every ``embed_batch`` call's texts, as a list, in call order.
        self.embed_batch_calls: list[list[str]] = []
        #: Names of every library method called (``embed_batch``, ``list_models``, ``chat``, ...).
        self.method_calls: list[str] = []
        self.entered = 0
        self.exited = 0
        self.library_clients: dict[str, type] = {
            "llamaswap": self._client_class("llamaswap", refuse_empty_token=False),
            "openai": self._client_class("openai", refuse_empty_token=True),
        }

    def _client_class(self, kind: str, *, refuse_empty_token: bool) -> type:
        recorder = self

        class _FakeLibraryClient:
            """A library client class: the four constructor keywords, ``async with``, ``embed_batch``."""

            def __init__(
                self,
                model: str,
                base_url: str = "",
                timeout: float = 600.0,
                bearer_token: str | None = None,
                default_options: Any = None,
            ) -> None:
                recorder.constructions.append(
                    {
                        "kind": kind,
                        "model": model,
                        "base_url": base_url,
                        "timeout": timeout,
                        "bearer_token": bearer_token,
                    }
                )
                # Mirrors OpenAIAPIClient: an empty credential is refused at construction.
                if refuse_empty_token and not bearer_token:
                    raise ValueError("OpenAI credential not provided.")

            async def __aenter__(self) -> "_FakeLibraryClient":
                recorder.entered += 1
                return self

            async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
                recorder.exited += 1

            async def embed_batch(self, texts: list[str], *, options: Any = None) -> list[list[float]]:
                recorder.method_calls.append("embed_batch")
                recorder.embed_batch_calls.append(list(texts))
                if recorder.error is not None:
                    raise recorder.error
                if recorder.vectors is not None:
                    return [list(v) for v in recorder.vectors]
                return vectors_for(list(texts), FAKE_EMBEDDING_DIM)

            async def list_models(self) -> list[str]:
                recorder.method_calls.append("list_models")
                raise AssertionError("embed must not list models")

            async def chat(self, *args: Any, **kwargs: Any) -> str:
                recorder.method_calls.append("chat")
                raise AssertionError("embed must not chat")

            async def chat_with_tools(self, *args: Any, **kwargs: Any) -> str:
                recorder.method_calls.append("chat_with_tools")
                raise AssertionError("embed must not chat")

        return _FakeLibraryClient


def gateway_factory(recorder: LibraryEmbedRecorder) -> Callable[[str, str, str | None, float], LlmGateway]:
    """A four-argument client factory building the real ``LlmGateway`` over ``recorder``'s classes."""

    def factory(kind: str, base_url: str, api_key: str | None, timeout_seconds: float) -> LlmGateway:
        return LlmGateway(kind, base_url, api_key, timeout_seconds, library_clients=recorder.library_clients)

    return factory
