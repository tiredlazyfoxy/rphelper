"""Tests for the LLM gateway's embed — feature 035 step 002.

Every expected value in this module comes from
``docs/plans/035.llm-client-gateway/002.embed-and-factory.md`` (DoD-1 .. DoD-5) and the
decisions it cites: DEC-035-3 (the ``library_clients`` seam), DEC-035-8 (embed failure
mapping, unrecognised ``kind``, no chained cause, nothing logged from the library error),
``DEC-arch-llm-client-library-3`` (``auth_failed`` read from the error *message*), ``-9``
(OpenAI with no credential) and ``-10`` (the provider's message and ``description`` never
leave a failure), plus the feature ``context.md`` rule "one library client per operation".
Covers UC-013 for the embed path.

Bound through the frozen interface only (``status.md`` ``## Skeleton`` steps 001 and 002):
``LlmGateway(kind, base_url, api_key, timeout_seconds, *, library_clients=...)`` and
``await gateway.embed(model, texts) -> list[list[float]]``. No HTTP is involved
(``DEC-arch-llm-client-library-11``): fake library client classes come from
``tests.llm_fakes.LibraryEmbedRecorder`` and library failures are the real ``llm.LLMError``.

The suite has no pytest-asyncio, so each coroutine is driven with ``asyncio.run``.
"""

import asyncio
import traceback
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

import pytest
from llm import LLMError
from loguru import logger

from app.errors import LlmUnreachableError
from app.services.llm.gateway import EMBED_NO_VECTOR_REASON, LlmGateway
from tests.llm_fakes import LibraryEmbedRecorder

BASE_URL = "http://embed.test:8080"
API_KEY = "sk-embed-test-key"
TIMEOUT_SECONDS = 9.5
MODEL = "the-embedding-model"
TEXTS = ("first text", "second, different text", "third")

#: Distinct per-position vectors, so "in the texts' order" cannot be met by any reordering.
LIBRARY_VECTORS = [[0.5, -1.0, 2.0], [-0.25, 0.75, 1.5], [3.0, 0.0, -2.5]]

REQUEST_FAILED = "Request to http://embed.test:8080/v1/embeddings failed"

KINDS = ["llamaswap", "openai"]


def _gateway(
    recorder: LibraryEmbedRecorder,
    *,
    kind: str = "llamaswap",
    api_key: str | None = API_KEY,
) -> LlmGateway:
    """A real gateway whose library clients are ``recorder``'s fake classes (DEC-035-3)."""
    return LlmGateway(kind, BASE_URL, api_key, TIMEOUT_SECONDS, library_clients=recorder.library_clients)


def _embed(gateway: LlmGateway, texts: Sequence[str] = TEXTS, model: str = MODEL) -> list[list[float]]:
    return asyncio.run(gateway.embed(model, texts))


def _embed_failure(gateway: LlmGateway) -> LlmUnreachableError:
    with pytest.raises(LlmUnreachableError) as caught:
        _embed(gateway)
    return caught.value


# =========================================================================== DoD-1


@pytest.mark.parametrize("kind", KINDS)
def test_embed_returns_the_library_vectors_in_order__DoD1(kind: str) -> None:
    """DoD-1 — ``embed`` returns the library's vectors, one per text, in the texts' order."""
    recorder = LibraryEmbedRecorder(vectors=LIBRARY_VECTORS)
    assert _embed(_gateway(recorder, kind=kind)) == LIBRARY_VECTORS


@pytest.mark.parametrize("kind", KINDS)
def test_embed_builds_one_library_client_with_that_model__DoD1(kind: str) -> None:
    """DoD-1 — one library client, of the class ``kind`` selects, built with the model given."""
    recorder = LibraryEmbedRecorder(vectors=LIBRARY_VECTORS)
    _embed(_gateway(recorder, kind=kind))
    assert [(c["kind"], c["model"]) for c in recorder.constructions] == [(kind, MODEL)]


def test_embed_calls_embed_batch_once_with_the_texts__DoD1() -> None:
    """DoD-1 — ``embed_batch`` is called once, with exactly the texts, in order."""
    recorder = LibraryEmbedRecorder(vectors=LIBRARY_VECTORS)
    _embed(_gateway(recorder), texts=TEXTS)
    assert recorder.embed_batch_calls == [list(TEXTS)]
    assert recorder.method_calls == ["embed_batch"]


def test_embed_of_a_single_text_answers_a_single_vector__DoD1() -> None:
    """DoD-1 — a one-text batch answers the one vector the library returned."""
    recorder = LibraryEmbedRecorder(vectors=[[0.125, 0.25]])
    assert _embed(_gateway(recorder), texts=["only"]) == [[0.125, 0.25]]
    assert recorder.embed_batch_calls == [["only"]]


# =========================================================================== DoD-2


def _status_message(status: int) -> str:
    return f"{REQUEST_FAILED} with status {status}"


#: (case id, library error, expected ``detail.reason``) — the DoD-2 mapping table.
FAILURE_MAPPING: list[tuple[str, LLMError, str]] = [
    ("status-401", LLMError(_status_message(401), "invalid api key"), "auth_failed"),
    ("status-403", LLMError(_status_message(403), "forbidden"), "auth_failed"),
    ("status-401-no-description", LLMError(_status_message(401)), "auth_failed"),
    (
        "invalid-response",
        LLMError("Invalid response from llama-swap API when embedding: missing data"),
        EMBED_NO_VECTOR_REASON,
    ),
    (
        "invalid-response-count",
        LLMError("Invalid response from OpenAI API when embedding: expected 3 vectors, got 2"),
        EMBED_NO_VECTOR_REASON,
    ),
    ("status-400", LLMError(_status_message(400), "bad request"), "unreachable"),
    ("status-404", LLMError(_status_message(404), "no such model"), "unreachable"),
    ("status-429", LLMError(_status_message(429), "slow down"), "unreachable"),
    ("status-500", LLMError(_status_message(500), "internal error"), "unreachable"),
    ("status-502", LLMError(_status_message(502)), "unreachable"),
    ("transport-timeout", LLMError(f"{REQUEST_FAILED}: timeout"), "unreachable"),
    ("transport-interrupted", LLMError(f"{REQUEST_FAILED}: interrupted transfer"), "unreachable"),
    ("transport-connection", LLMError(f"{REQUEST_FAILED}: connection failure"), "unreachable"),
    ("unreadable-reply", LLMError("Unreadable reply from llama-swap API when embedding"), "unreachable"),
    # The rule reads the *message*: a 500 whose body (``description``) mentions 401 is not auth.
    (
        "status-500-description-mentions-401",
        LLMError(_status_message(500), "upstream said status 401"),
        "unreachable",
    ),
]


@pytest.mark.parametrize(
    ("error", "reason"),
    [(error, reason) for _id, error, reason in FAILURE_MAPPING],
    ids=[case_id for case_id, _error, _reason in FAILURE_MAPPING],
)
@pytest.mark.parametrize("kind", KINDS)
def test_library_failures_map_to_llm_unreachable_with_the_reason__DoD2(
    kind: str, error: LLMError, reason: str
) -> None:
    """DoD-2 — 401/403 → ``auth_failed``; ``Invalid response…`` → ``no_usable_vector``;
    any other status, a transport message or ``Unreadable reply…`` → ``unreachable``."""
    recorder = LibraryEmbedRecorder(error=error)
    raised = _embed_failure(_gateway(recorder, kind=kind))
    assert type(raised) is LlmUnreachableError
    assert raised.code == "llm_unreachable"
    assert raised.detail == {"reason": reason}


def test_the_no_vector_reason_is_the_shared_constant__DoD2() -> None:
    """DoD-2 — ``EMBED_NO_VECTOR_REASON`` is the value ``no_usable_vector``."""
    assert EMBED_NO_VECTOR_REASON == "no_usable_vector"


# =========================================================================== DoD-3


def test_openai_without_an_api_key_is_auth_failed_and_calls_no_library_method__DoD3() -> None:
    """DoD-3 — ``kind`` ``openai`` with no api key: ``llm_unreachable`` / ``auth_failed``, and no
    library method is called (no ``embed_batch``, no ``async with``)."""
    recorder = LibraryEmbedRecorder(vectors=LIBRARY_VECTORS)
    raised = _embed_failure(_gateway(recorder, kind="openai", api_key=None))
    assert raised.code == "llm_unreachable"
    assert raised.detail == {"reason": "auth_failed"}
    assert recorder.method_calls == []
    assert recorder.embed_batch_calls == []
    assert recorder.entered == 0


def test_openai_without_an_api_key_raises_with_no_chained_cause__DoD3() -> None:
    """DoD-3 / DEC-035-8 — the no-credential error is raised with no chained cause or context."""
    recorder = LibraryEmbedRecorder(vectors=LIBRARY_VECTORS)
    raised = _embed_failure(_gateway(recorder, kind="openai", api_key=None))
    assert raised.__cause__ is None
    assert raised.__suppress_context__ is True


def test_llamaswap_without_an_api_key_embeds__DoD3() -> None:
    """DoD-3 (control) / DEC-arch-llm-client-library-9 — a llama-swap server needs no key."""
    recorder = LibraryEmbedRecorder(vectors=LIBRARY_VECTORS)
    assert _embed(_gateway(recorder, kind="llamaswap", api_key=None)) == LIBRARY_VECTORS


@pytest.mark.parametrize("kind", ["ollama", "mystery-kind"])
def test_an_unrecognised_kind_is_unreachable__DoD3(kind: str) -> None:
    """DoD-3 / DEC-035-8 — an unrecognised ``kind`` raises ``llm_unreachable`` / ``unreachable``,
    caught before any library client is built."""
    recorder = LibraryEmbedRecorder(vectors=LIBRARY_VECTORS)
    raised = _embed_failure(_gateway(recorder, kind=kind))
    assert raised.code == "llm_unreachable"
    assert raised.detail == {"reason": "unreachable"}
    assert recorder.constructions == []
    assert recorder.method_calls == []


# =========================================================================== DoD-4

# Assembled at runtime so neither sentinel is a literal in this source: a traceback quoting a
# line of this file can then never produce a false positive.
_MESSAGE_SENTINEL = "".join(("sntl", "embedmsg", "7f31"))
_DESCRIPTION_SENTINEL = "".join(("sntl", "embedbody", "c42d"))


def _sentinel_error(message_prefix: str) -> LLMError:
    """A library error with one sentinel in its message and another in its ``description``."""
    return LLMError(f"{message_prefix} {_MESSAGE_SENTINEL}", _DESCRIPTION_SENTINEL)


SENTINEL_ERRORS: list[tuple[str, str]] = [
    ("status-401", f"{REQUEST_FAILED} with status 401"),
    ("status-500", f"{REQUEST_FAILED} with status 500"),
    ("invalid-response", "Invalid response from llama-swap API when embedding:"),
    ("transport", f"{REQUEST_FAILED}: connection failure"),
    ("unreadable-reply", "Unreadable reply from llama-swap API when embedding:"),
]


@contextmanager
def captured_log_text(caplog: pytest.LogCaptureFixture) -> Iterator[list[str]]:
    """Everything logged while the block runs, through loguru *and* the stdlib.

    A level-0 loguru sink captures the rendered line, the message, ``extra`` and any attached
    exception; ``caplog`` at level 1 captures stdlib records. Both, because the gateway could
    log through either.
    """
    lines: list[str] = []

    def sink(message: Any) -> None:
        record = message.record
        lines.append(str(message))
        lines.append(str(record["message"]))
        lines.append(repr(record["extra"]))
        if record["exception"] is not None:
            lines.append(repr(record["exception"].value))

    handler_id = logger.add(sink, level=0, format="{level} {name} {message} {exception}")
    caplog.set_level(1)
    try:
        yield lines
    finally:
        logger.remove(handler_id)
        lines.append(caplog.text)
        for record in caplog.records:
            lines.append(record.getMessage())
            lines.append(repr(record.args))


def _assert_no_sentinel(text: str) -> None:
    assert _MESSAGE_SENTINEL not in text
    assert _DESCRIPTION_SENTINEL not in text


@pytest.mark.parametrize(
    "prefix", [prefix for _id, prefix in SENTINEL_ERRORS], ids=[case_id for case_id, _prefix in SENTINEL_ERRORS]
)
def test_the_library_message_and_description_never_leave_the_failure__DoD4(
    caplog: pytest.LogCaptureFixture, prefix: str
) -> None:
    """DoD-4 — the sentinel is in none of: the raised error's message, its ``detail``, or the log
    records of the call."""
    recorder = LibraryEmbedRecorder(error=_sentinel_error(prefix))
    with captured_log_text(caplog) as lines:
        raised = _embed_failure(_gateway(recorder))

    _assert_no_sentinel(str(raised))
    _assert_no_sentinel(repr(raised.args))
    _assert_no_sentinel(repr(raised.detail))
    _assert_no_sentinel("\n".join(lines))


@pytest.mark.parametrize(
    "prefix", [prefix for _id, prefix in SENTINEL_ERRORS], ids=[case_id for case_id, _prefix in SENTINEL_ERRORS]
)
def test_the_raised_error_has_no_cause_and_suppresses_its_context__DoD4(prefix: str) -> None:
    """DoD-4 — the raised error has no ``__cause__`` and ``__suppress_context__`` is true, so even a
    formatted traceback carries no library text."""
    recorder = LibraryEmbedRecorder(error=_sentinel_error(prefix))
    raised = _embed_failure(_gateway(recorder))

    assert raised.__cause__ is None
    assert raised.__suppress_context__ is True
    _assert_no_sentinel("".join(traceback.format_exception(raised)))


# =========================================================================== DoD-5


def test_constructing_the_gateway_builds_no_library_client__DoD5() -> None:
    """DoD-5 / context.md — the gateway object itself holds no library client."""
    recorder = LibraryEmbedRecorder(vectors=LIBRARY_VECTORS)
    _gateway(recorder)
    assert recorder.constructions == []
    assert recorder.entered == 0


def test_a_successful_embed_enters_and_exits_exactly_one_client__DoD5() -> None:
    """DoD-5 — on success: one library client built, entered once and exited once."""
    recorder = LibraryEmbedRecorder(vectors=LIBRARY_VECTORS)
    _embed(_gateway(recorder))
    assert len(recorder.constructions) == 1
    assert (recorder.entered, recorder.exited) == (1, 1)


@pytest.mark.parametrize(
    ("error", "reason"),
    [(error, reason) for _id, error, reason in FAILURE_MAPPING],
    ids=[case_id for case_id, _error, _reason in FAILURE_MAPPING],
)
def test_a_failing_embed_enters_and_exits_exactly_one_client__DoD5(error: LLMError, reason: str) -> None:
    """DoD-5 — on a library failure: one library client built, entered once and exited once."""
    recorder = LibraryEmbedRecorder(error=error)
    raised = _embed_failure(_gateway(recorder))
    assert raised.detail == {"reason": reason}
    assert len(recorder.constructions) == 1
    assert (recorder.entered, recorder.exited) == (1, 1)


def test_each_embed_call_uses_its_own_client__DoD5() -> None:
    """DoD-5 — two calls on one gateway: two clients, each entered and exited once."""
    recorder = LibraryEmbedRecorder(vectors=LIBRARY_VECTORS)
    gateway = _gateway(recorder)
    _embed(gateway)
    _embed(gateway)
    assert len(recorder.constructions) == 2
    assert (recorder.entered, recorder.exited) == (2, 2)
