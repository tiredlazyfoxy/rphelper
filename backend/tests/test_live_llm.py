"""Opt-in checks against a real OpenAI-compatible server (llama-swap).

Marked ``live`` and deselected by default (``addopts`` carries ``-m 'not live'``), so the
normal and verifier runs never depend on a network service. Run with::

    <py> -m pytest -m live

The server URL comes from ``LLAMA_SWITCH_URL`` (the llama-swap base, with or without
``/v1``); the suite skips when it is unset. Every call uses a bounded timeout, so an
unreachable server fails within seconds.
"""

import asyncio
import os

import pytest

from app.errors import LlmUnreachableError
from app.services.llm.client import LlmClient, ProbeOutcome

LIVE_URL = os.environ.get("LLAMA_SWITCH_URL", "")
LIVE_EMBED_MODEL = "bge-large-en-v1.5.i1-Q6_K"

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not LIVE_URL, reason="LLAMA_SWITCH_URL is not set"),
]
#: Embedding a couple of short strings; generous for a cold model load, still bounded.
LIVE_TIMEOUT_SECONDS = 60.0
#: An unreachable or disabled server must fail fast, not after the production timeout.
DOWN_TIMEOUT_SECONDS = 2.0


def test_live_server_lists_the_embedding_model() -> None:
    result = asyncio.run(LlmClient(LIVE_URL, None, LIVE_TIMEOUT_SECONDS).probe())
    assert result.outcome is ProbeOutcome.REACHABLE
    assert LIVE_EMBED_MODEL in result.model_names


def test_live_embedding_returns_one_vector_per_input_in_order() -> None:
    client = LlmClient(LIVE_URL, None, LIVE_TIMEOUT_SECONDS)
    vectors = asyncio.run(client.embed(LIVE_EMBED_MODEL, ["the cat sat", "a dog ran"]))
    assert len(vectors) == 2
    assert len(vectors[0]) == len(vectors[1]) > 0
    assert vectors[0] != vectors[1]


def test_closed_port_fails_fast_as_unreachable() -> None:
    client = LlmClient("http://127.0.0.1:9/", None, DOWN_TIMEOUT_SECONDS)
    with pytest.raises(LlmUnreachableError):
        asyncio.run(client.embed(LIVE_EMBED_MODEL, ["x"]))
