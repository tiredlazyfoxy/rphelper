"""Tests for the LLM gateway's probe — feature 035 step 001.

Every expected value in this module comes from
feature 035 step 001 (DoD-4 .. DoD-14) and the
decisions it cites: DEC-035-2 (probe value types re-homed), DEC-035-3 (the
``library_clients`` seam), DEC-035-8 (probe failure mapping, ``note`` never set),
DEC-035-11 (base-URL rule), ``DEC-arch-llm-client-library-3`` (``auth_failed`` read from
the error message), ``-9`` (OpenAI with no credential) and ``-10`` (the provider's
message and ``description`` are never logged). Covers UC-011 / US-013 for the probe.

The gateway is bound through the frozen interface only:
``LlmGateway(kind, base_url, api_key, timeout_seconds, *, library_clients=...)`` and
``await gateway.probe() -> ProbeResult``. No HTTP is involved
(``DEC-arch-llm-client-library-11``): fake library client classes are injected through
``library_clients``, and library failures are raised as the real ``llm.LLMError``.

Extended by feature 035 step 006 (DoD-2, tagged ``S035_006``): the
library is 0.2.1, whose ``LLMError`` carries a keyword-only ``status``. ``auth_failed`` is read
from that status (401 or 403) and never from the message (DEC-035-20,
``DEC-arch-llm-client-library-16``, which refines ``-3``), so every auth case here builds a
status-bearing error.

The suite has no pytest-asyncio, so each coroutine is driven with ``asyncio.run``.
"""

import asyncio
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
from llm import LLMError
from loguru import logger

from app.services.llm import gateway as gateway_module
from app.services.llm.gateway import LlmGateway, ProbeOutcome, ProbeResult

TIMEOUT_SECONDS = 12.5
API_KEY = "sk-test-key"
BASE_URL = "http://h:1"
NORMALISED_BASE_URL = "http://h:1/v1"

# Listed in a deliberately non-alphabetical order so that "the order the library returned
# them" cannot be satisfied by sorting (DoD-6).
LISTED_NAMES = ["zeta-model", "alpha-model", "mid-model"]


# --------------------------------------------------------------------------- fakes


@dataclass
class FakeLibraryInstance:
    """What one constructed fake library client saw: its keywords and its context lifecycle."""

    kwargs: dict[str, Any]
    entered: int = 0
    exited: int = 0
    list_calls: int = 0


@dataclass
class LibraryScript:
    """How a fake library class behaves, and everything its instances recorded.

    ``listing`` is what ``list_models`` returns; ``list_error`` / ``enter_error`` /
    ``construct_error`` make the matching step raise instead. ``requires_token`` mimics
    the real ``OpenAIAPIClient``, which refuses a falsy ``bearer_token`` with ``ValueError``
    at construction (feature 035 step 001's context, "What the probe reads from the library").
    """

    listing: Sequence[str] = ()
    list_error: BaseException | None = None
    enter_error: BaseException | None = None
    construct_error: BaseException | None = None
    requires_token: bool = False
    instances: list[FakeLibraryInstance] = field(default_factory=list)

    @property
    def constructions(self) -> int:
        return len(self.instances)

    @property
    def list_calls(self) -> int:
        return sum(instance.list_calls for instance in self.instances)


def fake_library_class(script: LibraryScript) -> type:
    """A fake library client class bound to ``script`` (DEC-035-3's fake shape).

    It accepts the keywords ``model``, ``base_url``, ``timeout`` and ``bearer_token`` (any
    further keyword is recorded, never refused), is an async context manager, and offers
    an async ``list_models``. A fresh class per script keeps parallel tests independent.
    """

    class FakeLibraryClient:
        def __init__(
            self,
            *,
            model: str,
            base_url: str,
            timeout: float,
            bearer_token: str | None = None,
            **extra: Any,
        ) -> None:
            if script.construct_error is not None:
                raise script.construct_error
            if script.requires_token and not bearer_token:
                raise ValueError("OpenAI credential not provided.")
            recorded: dict[str, Any] = {"model": model, "base_url": base_url, "timeout": timeout}
            recorded["bearer_token"] = bearer_token
            self._record = FakeLibraryInstance(kwargs={**recorded, **extra})
            script.instances.append(self._record)

        async def __aenter__(self) -> "FakeLibraryClient":
            self._record.entered += 1
            if script.enter_error is not None:
                raise script.enter_error
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            self._record.exited += 1

        async def list_models(self) -> list[str]:
            self._record.list_calls += 1
            if script.list_error is not None:
                raise script.list_error
            return list(script.listing)

    return FakeLibraryClient


@dataclass
class Library:
    """One fake class per kind, as the ``library_clients`` mapping the gateway is given."""

    openai: LibraryScript = field(default_factory=lambda: LibraryScript(requires_token=True))
    llamaswap: LibraryScript = field(default_factory=LibraryScript)

    def mapping(self) -> dict[str, type]:
        return {"openai": fake_library_class(self.openai), "llamaswap": fake_library_class(self.llamaswap)}

    def script(self, kind: str) -> LibraryScript:
        return {"openai": self.openai, "llamaswap": self.llamaswap}[kind]

    @property
    def total_constructions(self) -> int:
        return self.openai.constructions + self.llamaswap.constructions


def make_gateway(
    library: Library,
    kind: str = "llamaswap",
    base_url: str = BASE_URL,
    api_key: str | None = API_KEY,
    timeout_seconds: float = TIMEOUT_SECONDS,
) -> LlmGateway:
    """The gateway under test, built positionally as the frozen constructor declares."""
    return LlmGateway(kind, base_url, api_key, timeout_seconds, library_clients=library.mapping())


def probe(gateway: LlmGateway) -> ProbeResult:
    """Run one ``probe()`` to completion (no pytest-asyncio in this suite)."""
    return asyncio.run(gateway.probe())


# The library's request-failure message prefix (``DEC-arch-llm-client-library-3``).
REQUEST_FAILED = f"Request to {NORMALISED_BASE_URL}/models failed"


def status_error(status: int) -> LLMError:
    """The library's non-2xx error as 0.2.1 raises it: the message form plus ``status`` and ``kind``.

    Since 035 step 006 ``auth_failed`` is read from ``status`` alone (DEC-035-20,
    ``DEC-arch-llm-client-library-16``), so the status-bearing form is the realistic one.
    """
    return LLMError(f"{REQUEST_FAILED} with status {status}", description="body", status=status, kind="status")


# --------------------------------------------------------------------------- DoD-4


@pytest.mark.parametrize(("kind", "other"), [("openai", "llamaswap"), ("llamaswap", "openai")])
def test_kind_selects_its_library_class_with_timeout_token_and_url__S035_001_DoD4(kind: str, other: str) -> None:
    """DoD-4: ``kind`` builds its own ``library_clients`` entry with timeout, bearer token and normalised URL."""
    library = Library()
    library.script(kind).listing = LISTED_NAMES
    gateway = make_gateway(library, kind=kind)
    # Interface intent: construction builds no library client.
    assert library.total_constructions == 0

    probe(gateway)

    built = library.script(kind)
    assert built.constructions == 1
    assert library.script(other).constructions == 0
    kwargs = built.instances[0].kwargs
    assert kwargs["timeout"] == TIMEOUT_SECONDS
    assert kwargs["bearer_token"] == API_KEY
    assert kwargs["base_url"] == NORMALISED_BASE_URL


# --------------------------------------------------------------------------- DoD-5


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("http://h:1", "http://h:1/v1"),
        ("http://h:1/", "http://h:1/v1"),
        ("http://h:1/v1", "http://h:1/v1"),
        ("http://h:1/v1/", "http://h:1/v1"),
        ("http://h:1/api", "http://h:1/api/v1"),
    ],
)
@pytest.mark.parametrize("kind", ["llamaswap", "openai"])
def test_base_url_reaches_the_library_normalised__S035_001_DoD5(kind: str, configured: str, expected: str) -> None:
    """DoD-5: the configured base URL reaches the library client normalised to end in ``/v1``."""
    library = Library()
    library.script(kind).listing = LISTED_NAMES

    probe(make_gateway(library, kind=kind, base_url=configured))

    assert library.script(kind).instances[0].kwargs["base_url"] == expected


# --------------------------------------------------------------------------- DoD-6


@pytest.mark.parametrize("kind", ["llamaswap", "openai"])
def test_a_listing_gives_reachable_with_names_in_library_order__S035_001_DoD6(kind: str) -> None:
    """DoD-6 (UC-011, US-013): a listing gives ``reachable`` with the names in the order returned."""
    library = Library()
    library.script(kind).listing = LISTED_NAMES

    result = probe(make_gateway(library, kind=kind))

    assert result.outcome is ProbeOutcome.REACHABLE
    assert result.model_names == tuple(LISTED_NAMES)


# --------------------------------------------------------------------------- DoD-7


@pytest.mark.parametrize("kind", ["llamaswap", "openai"])
def test_an_empty_listing_gives_model_list_empty__S035_001_DoD7(kind: str) -> None:
    """DoD-7 (UC-011, US-013): an empty listing gives ``model_list_empty``."""
    library = Library()
    library.script(kind).listing = []

    result = probe(make_gateway(library, kind=kind))

    assert result.outcome is ProbeOutcome.MODEL_LIST_EMPTY
    assert result.model_names == ()


# --------------------------------------------------------------------------- DoD-8


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (status_error(401), ProbeOutcome.AUTH_FAILED),
        (status_error(403), ProbeOutcome.AUTH_FAILED),
        (status_error(500), ProbeOutcome.UNREACHABLE),
        (LLMError(f"{REQUEST_FAILED}: timeout"), ProbeOutcome.UNREACHABLE),
        (LLMError(f"{REQUEST_FAILED}: connection failure", description="refused"), ProbeOutcome.UNREACHABLE),
        (
            LLMError("Invalid response from llama-swap when listing models: the reply is not a JSON object"),
            ProbeOutcome.UNREACHABLE,
        ),
    ],
    ids=["status-401", "status-403", "status-500", "timeout", "connection-failure", "invalid-response"],
)
@pytest.mark.parametrize("kind", ["llamaswap", "openai"])
def test_library_error_maps_to_its_probe_outcome__S035_001_DoD8(
    kind: str, error: LLMError, expected: ProbeOutcome
) -> None:
    """DoD-8 (UC-011, US-013): status 401/403 give ``auth_failed``; other library errors ``unreachable``."""
    library = Library()
    library.script(kind).list_error = error

    result = probe(make_gateway(library, kind=kind))

    assert result.outcome is expected
    assert result.model_names == ()


# --------------------------------------------------------------------------- DoD-9


@pytest.mark.parametrize("api_key", [None, ""], ids=["none", "empty"])
def test_openai_without_a_key_is_auth_failed_without_listing__S035_001_DoD9(api_key: str | None) -> None:
    """DoD-9 (UC-011): ``openai`` with no api key gives ``auth_failed`` and never calls ``list_models``."""
    library = Library()
    library.openai.listing = LISTED_NAMES

    result = probe(make_gateway(library, kind="openai", api_key=api_key))

    assert result.outcome is ProbeOutcome.AUTH_FAILED
    assert library.openai.list_calls == 0
    assert library.llamaswap.constructions == 0


@pytest.mark.parametrize("api_key", [None, ""], ids=["none", "empty"])
def test_llamaswap_without_a_key_is_built_tokenless_and_proceeds__S035_001_DoD9(api_key: str | None) -> None:
    """DoD-9 (UC-011): ``llamaswap`` with no api key is built with no bearer token, and the probe proceeds."""
    library = Library()
    library.llamaswap.listing = LISTED_NAMES

    result = probe(make_gateway(library, kind="llamaswap", api_key=api_key))

    assert library.llamaswap.constructions == 1
    assert not library.llamaswap.instances[0].kwargs["bearer_token"]
    assert library.llamaswap.list_calls == 1
    assert result.outcome is ProbeOutcome.REACHABLE
    assert result.model_names == tuple(LISTED_NAMES)


# --------------------------------------------------------------------------- DoD-10


@pytest.mark.parametrize("kind", ["ollama", "bogus", ""])
def test_an_unrecognised_kind_is_unreachable_and_builds_nothing__S035_001_DoD10(kind: str) -> None:
    """DoD-10: an unrecognised ``kind`` gives ``unreachable`` and builds no library client."""
    library = Library()
    library.openai.listing = LISTED_NAMES
    library.llamaswap.listing = LISTED_NAMES

    result = probe(make_gateway(library, kind=kind))

    assert result.outcome is ProbeOutcome.UNREACHABLE
    assert library.total_constructions == 0


# --------------------------------------------------------------------------- DoD-11


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("library runtime failure"),
        ValueError("library value failure"),
        KeyError("missing"),
        TypeError("bad type"),
        OSError("socket gone"),
        Exception("plain exception"),
        LLMError("Unreadable reply from llama-swap when listing models"),
    ],
    ids=["runtime", "value", "key", "type", "os", "exception", "llm-error"],
)
def test_any_exception_from_list_models_gives_unreachable__S035_001_DoD11(error: Exception) -> None:
    """DoD-11 (UC-011): any exception out of ``list_models`` — ``LLMError`` or not — gives ``unreachable``."""
    library = Library()
    library.llamaswap.list_error = error

    result = probe(make_gateway(library))

    assert result.outcome is ProbeOutcome.UNREACHABLE


@pytest.mark.parametrize("error", [RuntimeError("enter failed"), OSError("no session")], ids=["runtime", "os"])
def test_an_exception_entering_the_client_gives_unreachable__S035_001_DoD11(error: Exception) -> None:
    """DoD-11 (UC-011): an exception from the library client's context entry still gives ``unreachable``."""
    library = Library()
    library.llamaswap.enter_error = error

    result = probe(make_gateway(library))

    assert result.outcome is ProbeOutcome.UNREACHABLE


@pytest.mark.parametrize("error", [TypeError("bad keyword"), RuntimeError("cannot build")], ids=["type", "runtime"])
def test_an_exception_building_the_client_gives_unreachable__S035_001_DoD11(error: Exception) -> None:
    """DoD-11 (UC-011): an exception from the library client's constructor still gives ``unreachable``."""
    library = Library()
    library.llamaswap.construct_error = error

    result = probe(make_gateway(library))

    assert result.outcome is ProbeOutcome.UNREACHABLE


# --------------------------------------------------------------------------- DoD-12


def test_a_successful_probe_enters_and_exits_one_client__S035_001_DoD12() -> None:
    """DoD-12: one successful ``probe()`` builds, enters and exits exactly one library client."""
    library = Library()
    library.llamaswap.listing = LISTED_NAMES

    probe(make_gateway(library))

    assert library.llamaswap.constructions == 1
    instance = library.llamaswap.instances[0]
    assert (instance.entered, instance.exited) == (1, 1)


@pytest.mark.parametrize(
    "error",
    [status_error(401), status_error(500), LLMError("Invalid response from llama-swap"), RuntimeError("boom")],
    ids=["status-401", "status-500", "invalid-response", "runtime"],
)
def test_a_failed_probe_still_enters_and_exits_one_client__S035_001_DoD12(error: Exception) -> None:
    """DoD-12: a ``probe()`` whose listing fails still enters and exits exactly one library client."""
    library = Library()
    library.llamaswap.list_error = error

    probe(make_gateway(library))

    assert library.llamaswap.constructions == 1
    instance = library.llamaswap.instances[0]
    assert (instance.entered, instance.exited) == (1, 1)


def test_each_probe_call_uses_its_own_single_client__S035_001_DoD12() -> None:
    """DoD-12: every ``probe()`` call on one gateway enters and exits exactly one (new) library client."""
    library = Library()
    library.llamaswap.listing = LISTED_NAMES
    gateway = make_gateway(library)

    probe(gateway)
    probe(gateway)
    probe(gateway)

    assert library.llamaswap.constructions == 3
    assert [(i.entered, i.exited) for i in library.llamaswap.instances] == [(1, 1), (1, 1), (1, 1)]


# --------------------------------------------------------------------------- DoD-13

# Assembled at runtime so neither sentinel is a literal in this source, and a traceback
# quoting this file cannot produce a false positive.
_MESSAGE_SENTINEL = "".join(("sntl", "providermsg", "5a1e"))
_DESCRIPTION_SENTINEL = "".join(("sntl", "providerbody", "9c07"))


@contextmanager
def captured_log_text(caplog: pytest.LogCaptureFixture) -> Iterator[list[str]]:
    """Everything logged while the block runs, through loguru *and* the stdlib.

    A level-0 loguru sink captures the rendered line, the message, ``extra`` and any
    attached exception; ``caplog`` at level 1 captures stdlib records (including any
    formatted traceback). Both are needed because the gateway may log through either.
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


def _sentinel_error(prefix: str, status: int | None = None) -> LLMError:
    """A library error carrying one sentinel in its message and another in its ``description``.

    ``status`` is the 0.2.1 HTTP status attribute (035 step 006, DEC-035-20).
    """
    return LLMError(f"{prefix} {_MESSAGE_SENTINEL}", description=_DESCRIPTION_SENTINEL, status=status)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_sentinel_error(f"{REQUEST_FAILED} with status 401", 401), ProbeOutcome.AUTH_FAILED),
        (_sentinel_error(f"{REQUEST_FAILED} with status 500", 500), ProbeOutcome.UNREACHABLE),
        (_sentinel_error(f"{REQUEST_FAILED}: timeout"), ProbeOutcome.UNREACHABLE),
        (_sentinel_error("Invalid response from llama-swap when listing models"), ProbeOutcome.UNREACHABLE),
    ],
    ids=["status-401", "status-500", "timeout", "invalid-response"],
)
def test_provider_text_reaches_neither_the_result_nor_a_log__S035_001_DoD13(
    error: LLMError, expected: ProbeOutcome, caplog: pytest.LogCaptureFixture
) -> None:
    """DoD-13: a sentinel in a library error's message and ``description`` is absent from the result and logs."""
    library = Library()
    library.llamaswap.list_error = error

    with captured_log_text(caplog) as lines:
        result = probe(make_gateway(library))

    assert result.outcome is expected
    assert result.note is None
    rendered_result = repr(result) + str(result) + repr(result.model_names)
    captured = "\n".join(lines)
    for sentinel in (_MESSAGE_SENTINEL, _DESCRIPTION_SENTINEL):
        assert sentinel not in rendered_result
        assert sentinel not in captured


def test_provider_text_in_a_non_library_exception_reaches_no_log__S035_001_DoD13(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """DoD-13: an arbitrary exception's text is equally kept out of the result and every log record."""
    library = Library()
    library.llamaswap.list_error = RuntimeError(f"{_MESSAGE_SENTINEL} {_DESCRIPTION_SENTINEL}")

    with captured_log_text(caplog) as lines:
        result = probe(make_gateway(library))

    assert result.outcome is ProbeOutcome.UNREACHABLE
    assert result.note is None
    captured = "\n".join(lines)
    for sentinel in (_MESSAGE_SENTINEL, _DESCRIPTION_SENTINEL):
        assert sentinel not in repr(result)
        assert sentinel not in captured


def _scenario_reachable(library: Library) -> LlmGateway:
    library.llamaswap.listing = LISTED_NAMES
    return make_gateway(library)


def _scenario_empty(library: Library) -> LlmGateway:
    library.llamaswap.listing = []
    return make_gateway(library)


def _scenario_auth_failed(library: Library) -> LlmGateway:
    library.llamaswap.list_error = status_error(403)
    return make_gateway(library)


def _scenario_unreachable(library: Library) -> LlmGateway:
    library.llamaswap.list_error = status_error(502)
    return make_gateway(library)


def _scenario_openai_no_key(library: Library) -> LlmGateway:
    return make_gateway(library, kind="openai", api_key=None)


def _scenario_unknown_kind(library: Library) -> LlmGateway:
    return make_gateway(library, kind="bogus")


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        (_scenario_reachable, ProbeOutcome.REACHABLE),
        (_scenario_empty, ProbeOutcome.MODEL_LIST_EMPTY),
        (_scenario_auth_failed, ProbeOutcome.AUTH_FAILED),
        (_scenario_unreachable, ProbeOutcome.UNREACHABLE),
        (_scenario_openai_no_key, ProbeOutcome.AUTH_FAILED),
        (_scenario_unknown_kind, ProbeOutcome.UNREACHABLE),
    ],
    ids=["reachable", "model-list-empty", "auth-failed", "unreachable", "openai-no-key", "unknown-kind"],
)
def test_note_is_none_in_every_outcome__S035_001_DoD13(scenario: Any, expected: ProbeOutcome) -> None:
    """DoD-13 (DEC-035-8): the gateway never sets ``ProbeResult.note``, whatever the outcome."""
    library = Library()

    result = probe(scenario(library))

    assert result.outcome is expected
    assert result.note is None


# --------------------------------------------------------------------------- DoD-14
# DEC-035-15: DoD-14's identity check against ``app.services.llm.client`` was transitional
# and is retired now that step 005 (DoD-1) deletes ``client.py``. Only the gateway-side
# checks remain: the four ``ProbeOutcome`` values, ``ProbeResult``'s defaults and
# ``EMBED_NO_VECTOR_REASON``.


def test_probe_outcome_values_are_unchanged__S035_001_DoD14() -> None:
    """DoD-14: the four ``ProbeOutcome`` members and their values are exactly the pre-move ones."""
    assert {member.name: member.value for member in ProbeOutcome} == {
        "REACHABLE": "reachable",
        "UNREACHABLE": "unreachable",
        "AUTH_FAILED": "auth_failed",
        "MODEL_LIST_EMPTY": "model_list_empty",
    }
    assert ProbeOutcome("auth_failed") is ProbeOutcome.AUTH_FAILED
    assert ProbeOutcome.REACHABLE == "reachable"


def test_probe_result_and_no_vector_reason_are_re_homed_unchanged__S035_001_DoD14() -> None:
    """DoD-14 (DEC-035-2, DEC-035-15): the gateway's ``ProbeResult`` defaults and
    ``EMBED_NO_VECTOR_REASON`` are unchanged."""
    assert gateway_module.EMBED_NO_VECTOR_REASON == "no_usable_vector"

    defaults = ProbeResult(outcome=ProbeOutcome.UNREACHABLE)
    assert defaults.model_names == ()
    assert defaults.note is None


# --------------------------------------------------------------------------- 035 step 006 DoD-2
# DEC-035-20 / DEC-arch-llm-client-library-16: ``auth_failed`` comes from ``LLMError.status``
# being 401 or 403, whatever the message says; a message naming 401/403 without a status, and
# any other status, are ``unreachable``.

#: (case id, library error, expected outcome) for the status-based auth split.
STATUS_SPLIT: list[tuple[str, LLMError, ProbeOutcome]] = [
    ("status-401-opaque-message", LLMError("request refused", status=401), ProbeOutcome.AUTH_FAILED),
    ("status-403-opaque-message", LLMError("request refused", status=403), ProbeOutcome.AUTH_FAILED),
    (
        "status-401-message-says-500",
        LLMError(f"{REQUEST_FAILED} with status 500", description="body", status=401, kind="status"),
        ProbeOutcome.AUTH_FAILED,
    ),
    ("status-403-with-kind", status_error(403), ProbeOutcome.AUTH_FAILED),
    (
        "message-401-no-status",
        LLMError(f"{REQUEST_FAILED} with status 401", description="body"),
        ProbeOutcome.UNREACHABLE,
    ),
    ("message-403-no-status", LLMError(f"{REQUEST_FAILED} with status 403"), ProbeOutcome.UNREACHABLE),
    (
        "status-500-message-says-401",
        LLMError(f"{REQUEST_FAILED} with status 401", status=500, kind="status"),
        ProbeOutcome.UNREACHABLE,
    ),
    ("status-400", status_error(400), ProbeOutcome.UNREACHABLE),
    ("status-402", status_error(402), ProbeOutcome.UNREACHABLE),
    ("status-404", status_error(404), ProbeOutcome.UNREACHABLE),
    ("status-407", status_error(407), ProbeOutcome.UNREACHABLE),
    ("status-429", status_error(429), ProbeOutcome.UNREACHABLE),
    ("status-502", status_error(502), ProbeOutcome.UNREACHABLE),
]


@pytest.mark.parametrize(
    ("error", "expected"),
    [(error, expected) for _id, error, expected in STATUS_SPLIT],
    ids=[case_id for case_id, _error, _expected in STATUS_SPLIT],
)
@pytest.mark.parametrize("kind", ["llamaswap", "openai"])
def test_probe_auth_failed_is_read_from_the_error_status__S035_006_DoD2(
    kind: str, error: LLMError, expected: ProbeOutcome
) -> None:
    """S035 006 DoD-2: status 401/403 → ``auth_failed`` whatever the message says.

    A message naming 401/403 with no status, and any other status, give ``unreachable``.
    """
    library = Library()
    library.script(kind).list_error = error

    result = probe(make_gateway(library, kind=kind))

    assert result.outcome is expected
    assert result.model_names == ()
    assert result.note is None


@pytest.mark.parametrize("status", [401, 403])
def test_probe_auth_failure_leaks_no_provider_text__S035_006_DoD2(
    status: int, caplog: pytest.LogCaptureFixture
) -> None:
    """S035 006 DoD-2: a 401/403 error's message and ``description`` reach neither the result nor a log."""
    library = Library()
    library.llamaswap.list_error = _sentinel_error(f"{REQUEST_FAILED} with status {status}", status)

    with captured_log_text(caplog) as lines:
        result = probe(make_gateway(library))

    assert result.outcome is ProbeOutcome.AUTH_FAILED
    rendered = repr(result) + str(result)
    captured = "\n".join(lines)
    for sentinel in (_MESSAGE_SENTINEL, _DESCRIPTION_SENTINEL):
        assert sentinel not in rendered
        assert sentinel not in captured

