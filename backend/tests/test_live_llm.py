"""Opt-in checks of the LLM gateway against a real llama-swap server.

Plan 035 (llm-client-gateway), step 005: the live tests are the only place the real
``llm-client`` library and a real server meet (DEC-035-12). Every check builds
``LlmGateway("llamaswap", $LLAMA_SWITCH_URL, None, timeout)``. Covers the step's
``[manual/live]`` DoD-4 (probe, embed, closed port) and DoD-5 (``complete`` and a
no-tool ``compose``, which confirms the server accepts an empty ``tools`` list —
DEC-035-10's flip check). Step 006 keeps those checks for 0.2.1 and adds an optional
``[manual/live]`` DoD-15 check: a model-side tool mistake is yielded as ``ComposeRejected``
and the exchange continues; it skips when the model makes no mistake.

Marked ``live`` and deselected by default (``addopts`` carries ``-m 'not live'``), so the
normal and verifier runs never depend on a network service. Run with::

    <py> -m pytest -m live

The server URL comes from ``LLAMA_SWITCH_URL`` (the llama-swap base, with or without
``/v1``); the suite skips when it is unset. The DoD-5 chat checks also need a chat model
name on that server in ``LLAMA_SWITCH_CHAT_MODEL`` and skip without it. Every call uses a
bounded timeout, so an unreachable server fails within seconds.
"""

import asyncio
import os
from collections.abc import Callable

import pytest

from app.errors import LlmUnreachableError
from app.services.llm.chat import ChatMessage, ToolCall
from app.services.llm.gateway import (
    ComposeRejected,
    ComposeRejectionKind,
    ComposeText,
    ComposeTools,
    LlmGateway,
    ProbeOutcome,
)

LIVE_URL = os.environ.get("LLAMA_SWITCH_URL", "")
LIVE_EMBED_MODEL = "bge-large-en-v1.5.i1-Q6_K"
#: The chat model is server-specific, so it is supplied alongside the URL rather than guessed.
LIVE_CHAT_MODEL = os.environ.get("LLAMA_SWITCH_CHAT_MODEL", "")
LIVE_KIND = "llamaswap"

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not LIVE_URL, reason="LLAMA_SWITCH_URL is not set"),
]
#: Embedding or a short chat reply; generous for a cold model load, still bounded.
LIVE_TIMEOUT_SECONDS = 60.0
#: An unreachable or disabled server must fail fast, not after the production timeout.
DOWN_TIMEOUT_SECONDS = 2.0
#: Port 9 (discard) on loopback is closed on a normal host, so a connection is refused at once.
CLOSED_PORT_URL = "http://127.0.0.1:9/"

needs_chat_model = pytest.mark.skipif(not LIVE_CHAT_MODEL, reason="LLAMA_SWITCH_CHAT_MODEL is not set")

SHORT_PROMPT = [ChatMessage(role="user", content="Reply with one short friendly sentence.")]


def _live_gateway() -> LlmGateway:
    """A gateway onto the live server, built exactly as production builds it for a llama-swap row."""
    return LlmGateway(LIVE_KIND, LIVE_URL, None, LIVE_TIMEOUT_SECONDS)


def test_live_server_probes_reachable_with_models__S035_005_DoD4() -> None:
    """[manual/live] DoD-4: probing the live server reports reachable with a non-empty model list."""
    result = asyncio.run(_live_gateway().probe())
    assert result.outcome is ProbeOutcome.REACHABLE
    assert len(result.model_names) > 0
    assert LIVE_EMBED_MODEL in result.model_names


def test_live_embedding_returns_one_vector_per_input_in_order__S035_005_DoD4() -> None:
    """[manual/live] DoD-4: embedding returns a non-empty vector per input text."""
    vectors = asyncio.run(_live_gateway().embed(LIVE_EMBED_MODEL, ["the cat sat", "a dog ran"]))
    assert len(vectors) == 2
    assert len(vectors[0]) == len(vectors[1]) > 0
    assert vectors[0] != vectors[1]


def test_closed_port_probes_unreachable__S035_005_DoD4() -> None:
    """[manual/live] DoD-4: probing a closed local port reports unreachable, quickly."""
    gateway = LlmGateway(LIVE_KIND, CLOSED_PORT_URL, None, DOWN_TIMEOUT_SECONDS)
    result = asyncio.run(gateway.probe())
    assert result.outcome is ProbeOutcome.UNREACHABLE


def test_closed_port_embed_fails_fast_as_unreachable__S035_005_DoD4() -> None:
    """[manual/live] DoD-4: embedding against a closed local port raises ``llm_unreachable``."""
    gateway = LlmGateway(LIVE_KIND, CLOSED_PORT_URL, None, DOWN_TIMEOUT_SECONDS)
    with pytest.raises(LlmUnreachableError):
        asyncio.run(gateway.embed(LIVE_EMBED_MODEL, ["x"]))


@needs_chat_model
def test_live_complete_returns_text__S035_005_DoD5() -> None:
    """[manual/live] DoD-5: ``complete`` returns non-empty text for a short prompt."""
    text = asyncio.run(_live_gateway().complete(LIVE_CHAT_MODEL, SHORT_PROMPT))
    assert text.strip() != ""


async def _never_called_runner(call: ToolCall, emit: Callable[[object], None]) -> str:
    """No tool is offered, so the gateway must never run one."""
    raise AssertionError(f"no tool was offered, yet the gateway ran {call.name!r}")


async def _drain_compose(gateway: LlmGateway) -> list[object]:
    """Every event a no-tool ``compose`` yields, in order, until it ends."""
    tools: ComposeTools[object] = ComposeTools(declarations=(), runner=_never_called_runner)
    return [event async for event in gateway.compose(LIVE_CHAT_MODEL, SHORT_PROMPT, tools)]


@needs_chat_model
def test_live_compose_without_tools_streams_text__S035_005_DoD5() -> None:
    """[manual/live] DoD-5: a no-tool ``compose`` streams at least one ``ComposeText`` and ends cleanly.

    Ending without error confirms the server accepts an empty ``tools`` list (DEC-035-10).
    """
    events = asyncio.run(_drain_compose(_live_gateway()))
    texts = [event for event in events if isinstance(event, ComposeText)]
    assert len(texts) >= 1


# --- 035 step 006 DoD-15 [manual/live]: a model-side rejection on 0.2.1 -------------------------

#: The one tool offered; the prompt asks for a different one, inviting a `not_offered` mistake.
OFFERED_DECLARATION = {
    "type": "function",
    "function": {
        "name": "search_memos",
        "description": "Search the roleplayer's memos.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "What to find."}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}
REJECTION_PROMPT = [
    ChatMessage(
        role="user",
        content=(
            "Call the tool named fetch_weather with the argument city set to Paris, exactly once. "
            "Whatever it answers, then reply with one short sentence."
        ),
    )
]
#: A model that keeps repeating its mistake loops until stopped (DEC-arch-llm-client-library-15's
#: accepted exposure), so the check is bounded and skips rather than hangs.
REJECTION_BUDGET_SECONDS = 180.0


async def _memo_runner(call: ToolCall, emit: Callable[[object], None]) -> str:
    """The offered tool's runner: emits nothing and answers a fixed text."""
    return "No memos found."


async def _drain_rejection_prompt(gateway: LlmGateway) -> list[object]:
    """Every event of one `compose` offering only `search_memos` while asking for another tool."""
    tools: ComposeTools[object] = ComposeTools(declarations=(OFFERED_DECLARATION,), runner=_memo_runner)
    return [event async for event in gateway.compose(LIVE_CHAT_MODEL, REJECTION_PROMPT, tools)]


@needs_chat_model
def test_live_rejection_is_yielded_and_the_exchange_continues__S035_006_DoD15() -> None:
    """[manual/live] S035 006 DoD-15: when the real model calls a tool that was not offered, the
    gateway yields a `ComposeRejected` (the compose source's `tool_start` + `tool_fail`) and the
    exchange ends normally. Skips when the model makes no mistake, which cannot be forced."""

    async def bounded() -> list[object]:
        return await asyncio.wait_for(_drain_rejection_prompt(_live_gateway()), REJECTION_BUDGET_SECONDS)

    try:
        events = asyncio.run(bounded())
    except TimeoutError:
        pytest.skip("the model kept repeating its tool mistake past the budget")
    rejections = [event for event in events if isinstance(event, ComposeRejected)]
    if not rejections:
        pytest.skip("the model made no model-side tool mistake this run")
    for rejection in rejections:
        assert rejection.call.call_id.startswith("call_")
        assert rejection.kind in set(ComposeRejectionKind)
    # Reaching this line means the stream ended normally after the rejection (DoD-15, DoD-8).
