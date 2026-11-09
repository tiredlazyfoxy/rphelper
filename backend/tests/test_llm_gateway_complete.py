"""`LlmGateway.complete` over the library's non-streamed `chat` (feature 035, step 003).

Covers DoD-1 (one library client, `chat` non-streamed with the wire messages, the text returned
unchanged) and DoD-2 (failure mapping to `llm_unreachable` with RPHelper's own reasons, no provider
text anywhere, no chained cause). Decisions: DEC-035-3 (the `library_clients` seam), DEC-035-4
(`to_wire_message` builds `messages`, no `system=`), DEC-035-8 (the failure mapping),
`DEC-arch-llm-client-library-9` (an `openai` server with no credential).

No HTTP: the gateway is given fake library client classes through its keyword-only
`library_clients` map (`DEC-arch-llm-client-library-11`). Async code is driven with `asyncio.run`
from sync tests (the suite has no pytest-asyncio).
"""

import asyncio
import logging
from collections.abc import Awaitable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
from llm import LLMError
from loguru import logger

from app.errors import LlmUnreachableError
from app.services.llm.chat import ChatMessage, ToolCall, to_wire_message
from app.services.llm.gateway import LlmGateway

BASE_URL = "http://llm.test:8080"
TIMEOUT_SECONDS = 30.0
MODEL = "chat-model-x"

#: Strings that stand for provider text. A scripted library failure carries them in its message
#: (the request URL's host) and its `description` (the provider body); none may leave the gateway.
PROVIDER_HOST = "secret-provider-host.test"
PROVIDER_BODY = "PROVIDER-BODY-SENTINEL"
PROVIDER_MARKERS = (PROVIDER_HOST, PROVIDER_BODY)

#: The conversation `complete` is given: a leading system message, then ordinary turns, including
#: an assistant turn with a tool call and its tool reply, so the order check covers every role.
MESSAGES = (
    ChatMessage(role="system", content="You translate roleplay text."),
    ChatMessage(role="user", content="Bonjour, ça va ?"),
    ChatMessage(
        role="assistant",
        content="",
        tool_calls=(ToolCall(call_id="call_1", name="search_memos", arguments='{"query": "ça"}'),),
    ),
    ChatMessage(role="tool", content="no memos", tool_call_id="call_1"),
    ChatMessage(role="user", content="Translate it."),
)


def run[T](awaitable: Awaitable[T]) -> T:
    """Drive one coroutine to completion; a 10 s cap turns a hang into a quick failure."""

    async def capped() -> T:
        return await asyncio.wait_for(awaitable, 10)

    return asyncio.run(capped())


@dataclass
class LibraryRecord:
    """What the fake library classes observed, shared by every instance one test builds."""

    constructed: list[dict[str, Any]] = field(default_factory=list)
    entered: int = 0
    exited: int = 0
    chat_calls: list[dict[str, Any]] = field(default_factory=list)
    open_during_chat: list[bool] = field(default_factory=list)


def fake_library_class(
    record: LibraryRecord,
    *,
    reply: str = "the answer",
    error: BaseException | None = None,
    require_token: bool = False,
) -> type:
    """A fake library client class bound to `record`.

    It accepts the four construction keywords DEC-035-3 names, is an async context manager, and
    offers `chat` with the library's 0.2.0 signature. `chat` returns `reply`, or raises `error`.
    With `require_token` it imitates `OpenAIAPIClient`, which refuses an empty bearer token with a
    `ValueError` at construction (`DEC-arch-llm-client-library-9`).
    """

    class FakeChatLibraryClient:
        def __init__(self, *, model: str, base_url: str, timeout: float, bearer_token: str | None = None) -> None:
            if require_token and not bearer_token:
                raise ValueError(f"OpenAI credential not provided for {PROVIDER_HOST}")
            record.constructed.append(
                {"model": model, "base_url": base_url, "timeout": timeout, "bearer_token": bearer_token}
            )
            self._open = False

        async def __aenter__(self) -> "FakeChatLibraryClient":
            record.entered += 1
            self._open = True
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            record.exited += 1
            self._open = False

        async def chat(
            self,
            messages: list[dict[str, Any]],
            *,
            system: str | None = None,
            options: object = None,
            stream: bool = False,
            on_delta: object = None,
        ) -> str:
            record.chat_calls.append(
                {
                    "messages": list(messages),
                    "system": system,
                    "options": options,
                    "stream": stream,
                    "on_delta": on_delta,
                }
            )
            record.open_during_chat.append(self._open)
            if error is not None:
                raise error
            return reply

    return FakeChatLibraryClient


def gateway_over(fake_class: type, *, kind: str = "llamaswap", api_key: str | None = None) -> LlmGateway:
    """A gateway whose only library class, for `kind`, is `fake_class` (the DEC-035-3 seam)."""
    return LlmGateway(kind, BASE_URL, api_key, TIMEOUT_SECONDS, library_clients={kind: fake_class})


@contextmanager
def captured_log_text(caplog: pytest.LogCaptureFixture) -> Iterator[list[str]]:
    """Collect every loguru record (all levels) and stdlib record while the block runs.

    The list holds the loguru lines; `caplog.text` holds the stdlib ones. Together they are "the
    log" DoD-2 says carries no provider text.
    """
    lines: list[str] = []
    sink_id = logger.add(lambda message: lines.append(str(message)), level="TRACE", format="{message} {extra}")
    caplog.set_level(logging.DEBUG)
    try:
        yield lines
    finally:
        logger.remove(sink_id)


def assert_no_provider_text(error: LlmUnreachableError, log_text: str) -> None:
    """No provider marker in the error's message, args, detail, or the captured log (DoD-2)."""
    surfaces = (str(error), repr(error.args), repr(error.detail), log_text)
    for marker in PROVIDER_MARKERS:
        for surface in surfaces:
            assert marker not in surface


# --- DoD-1: one client, non-streamed chat, wire messages, text unchanged ----------------------


def test_complete_builds_one_client_with_the_model__DoD1() -> None:
    """DoD-1: `complete` builds exactly one library client, with the given model, and uses it."""
    record = LibraryRecord()
    gateway = gateway_over(fake_library_class(record))

    run(gateway.complete(MODEL, MESSAGES))

    assert len(record.constructed) == 1
    assert record.constructed[0]["model"] == MODEL
    assert len(record.chat_calls) == 1


def test_complete_calls_chat_inside_the_entered_client__DoD1() -> None:
    """DoD-1 (one client per operation, entered with `async with`): chat runs while it is open."""
    record = LibraryRecord()
    gateway = gateway_over(fake_library_class(record))

    run(gateway.complete(MODEL, MESSAGES))

    assert record.entered == 1
    assert record.exited == 1
    assert record.open_during_chat == [True]


def test_complete_calls_chat_non_streamed_without_system_or_options__DoD1() -> None:
    """DoD-1: `chat` is called non-streamed, with no `system` keyword and no options."""
    record = LibraryRecord()
    gateway = gateway_over(fake_library_class(record))

    run(gateway.complete(MODEL, MESSAGES))

    call = record.chat_calls[0]
    assert call["stream"] is False
    assert call["system"] is None
    assert call["options"] is None


def test_complete_passes_the_wire_messages_in_order__DoD1() -> None:
    """DoD-1: the library gets each message's `to_wire_message` form, in order, system first."""
    record = LibraryRecord()
    gateway = gateway_over(fake_library_class(record))

    run(gateway.complete(MODEL, MESSAGES))

    sent = record.chat_calls[0]["messages"]
    assert sent == [to_wire_message(message) for message in MESSAGES]
    assert sent[0] == {"role": "system", "content": "You translate roleplay text."}


def test_complete_returns_the_library_text_unchanged__DoD1() -> None:
    """DoD-1: the library's text comes back verbatim — whitespace and think tags untouched."""
    reply = "  <think>pondering</think>Hello, how are you?\n "
    record = LibraryRecord()
    gateway = gateway_over(fake_library_class(record, reply=reply))

    assert run(gateway.complete(MODEL, MESSAGES)) == reply


# --- DoD-2: failure mapping --------------------------------------------------------------------


def _llm_error(message: str) -> LLMError:
    """An `LLMError` shaped like the library's, carrying the provider markers."""
    return LLMError(message, PROVIDER_BODY)


FAILURE_CASES = [
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
        _llm_error(f"Request to http://{PROVIDER_HOST}/v1/responses failed with status 404"),
        "unreachable",
        id="status-404",
    ),
    pytest.param(
        _llm_error(f"Request to http://{PROVIDER_HOST}/v1/responses failed: timeout"),
        "unreachable",
        id="transport-timeout",
    ),
    pytest.param(
        _llm_error(f"Request to http://{PROVIDER_HOST}/v1/responses failed: connection failure"),
        "unreachable",
        id="transport-connection",
    ),
    pytest.param(
        _llm_error(f"Request to http://{PROVIDER_HOST}/v1/responses failed: interrupted transfer"),
        "unreachable",
        id="transport-interrupted",
    ),
    pytest.param(
        _llm_error(f"Invalid response from http://{PROVIDER_HOST}/v1/responses"),
        "unreachable",
        id="invalid-response",
    ),
    pytest.param(
        _llm_error(f"Unreadable reply from http://{PROVIDER_HOST}/v1/responses"),
        "unreachable",
        id="unreadable-reply",
    ),
    pytest.param(
        ValueError(f"bad value from {PROVIDER_HOST}: {PROVIDER_BODY}"),
        "unreachable",
        id="value-error",
    ),
]


@pytest.mark.parametrize(("library_error", "reason"), FAILURE_CASES)
def test_complete_maps_library_failures_to_llm_unreachable__DoD2(
    library_error: BaseException, reason: str, caplog: pytest.LogCaptureFixture
) -> None:
    """DoD-2: 401/403 → `auth_failed`; any other `LLMError` or a `ValueError` → `unreachable`."""
    record = LibraryRecord()
    gateway = gateway_over(fake_library_class(record, error=library_error))

    with captured_log_text(caplog) as lines, pytest.raises(LlmUnreachableError) as caught:
        run(gateway.complete(MODEL, MESSAGES))

    assert caught.value.detail == {"reason": reason}
    assert_no_provider_text(caught.value, "".join(lines) + caplog.text)


@pytest.mark.parametrize(("library_error", "reason"), FAILURE_CASES)
def test_complete_failure_has_no_chained_cause__DoD2(library_error: BaseException, reason: str) -> None:
    """DoD-2: the raised error has no `__cause__` and suppresses its context (DEC-035-8)."""
    record = LibraryRecord()
    gateway = gateway_over(fake_library_class(record, error=library_error))

    with pytest.raises(LlmUnreachableError) as caught:
        run(gateway.complete(MODEL, MESSAGES))

    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True


def test_complete_openai_without_api_key_is_auth_failed_and_calls_nothing__DoD2(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """DoD-2: kind `openai` with no api key → `auth_failed`, and the library's `chat` never runs."""
    record = LibraryRecord()
    fake_openai = fake_library_class(record, require_token=True)
    gateway = gateway_over(fake_openai, kind="openai", api_key=None)

    with captured_log_text(caplog) as lines, pytest.raises(LlmUnreachableError) as caught:
        run(gateway.complete(MODEL, MESSAGES))

    assert caught.value.detail == {"reason": "auth_failed"}
    assert record.chat_calls == []
    assert record.entered == 0
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True
    assert_no_provider_text(caught.value, "".join(lines) + caplog.text)
