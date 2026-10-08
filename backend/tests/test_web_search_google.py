"""Tests for the Google Custom Search provider (feature 028, step 001).

Covers DoD-5 .. DoD-12 of
``docs/plans/028.web-search-tool/001.search-settings-and-google-provider.md``. Every
expected value comes from that step file, from ``001.context.md`` ("The Google request",
"The Google response", "Exception mapping") and from feature 028's ``context.md`` (D1, D5,
D6, D7, D9). DoD-13 is ``[manual/live]`` and has no test here.

Outbound HTTP is faked with ``httpx.MockTransport`` through the frozen ``transport=`` seam,
so no test makes a real request; async code runs under ``asyncio.run``. Credentials are
obvious fakes.
"""

import ast
import asyncio
import io
import json
import logging
import sys
from collections.abc import Callable, Coroutine, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import httpx
import pytest
from loguru import logger

from app.config import Settings
from app.errors import ToolFailedError
from app.logging import configure_logging
from app.services.web_search import google as google_module
from app.services.web_search import provider as provider_module
from app.services.web_search.google import (
    DEFAULT_TIMEOUT_SECONDS,
    GOOGLE_CUSTOM_SEARCH_URL,
    GoogleCustomSearchProvider,
)
from app.services.web_search.provider import WebResult

QUERY = "bataille de Valmy"
LIMIT = 5

API_KEY = "test-key"
ENGINE_ID = "test-cx"

EXPECTED_SCHEME = "https"
EXPECTED_HOST = "www.googleapis.com"
EXPECTED_PATH = "/customsearch/v1"
KEY_HEADER = "x-goog-api-key"

EXPECTED_TOOL_NAME = "web_search"
EXPECTED_CODE = "tool_failed"
EXPECTED_DETAIL = {"tool": "web_search"}

THREE_ITEMS: list[dict[str, Any]] = [
    {"title": "Bataille de Valmy", "link": "https://example.test/valmy", "snippet": "20 septembre 1792."},
    {"title": "Valmy, le recit", "link": "https://example.test/recit", "snippet": "La canonnade."},
    {"title": "Kellermann", "link": "https://example.test/kellermann", "snippet": "Le general."},
]

THREE_RESULTS = [
    WebResult(title="Bataille de Valmy", url="https://example.test/valmy", snippet="20 septembre 1792."),
    WebResult(title="Valmy, le recit", url="https://example.test/recit", snippet="La canonnade."),
    WebResult(title="Kellermann", url="https://example.test/kellermann", snippet="Le general."),
]

Handler = Callable[[httpx.Request], httpx.Response]


# --------------------------------------------------------------------------- helpers


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run one coroutine to completion on a fresh event loop."""
    return asyncio.run(coro)


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


def json_handler(payload: Any, status: int = 200) -> Handler:
    """Answer every request with ``status`` and ``payload`` serialised as JSON."""

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return respond


def content_handler(status: int, body: bytes) -> Handler:
    """Answer every request with ``status`` and a raw, non-JSON body."""

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body)

    return respond


def status_handler(status: int) -> Handler:
    """Answer every request with a non-2xx status and a provider-shaped error body."""
    return json_handler({"error": {"message": "provider says no"}}, status=status)


def raising_handler(error_type: type[httpx.TransportError]) -> Handler:
    """A transport that fails instead of answering."""

    def respond(request: httpx.Request) -> httpx.Response:
        raise error_type("simulated transport failure", request=request)

    return respond


def _forbidden_forms(*secrets: str) -> tuple[str, ...]:
    """Each secret plus its URL-encoded form, de-duplicated and order-preserving.

    The redaction rule (`deployment.md`, D7) forbids the value, not one spelling of it. A
    secret that travels in a URL query string is percent-encoded on the way — `urlencode`
    turns a space into `+` — so a raw-substring sweep would miss exactly the item D7 names
    first: the query, which is message text composed from the discussion. The encoded form is
    produced with the stdlib rather than written out, so this stays honest if `QUERY` changes.
    """
    return tuple(dict.fromkeys(form for secret in secrets for form in (secret, quote_plus(secret))))


def make_provider(recorder: Recorder) -> GoogleCustomSearchProvider:
    """The provider under test, over the recorder's mock transport and the default timeout."""
    return GoogleCustomSearchProvider(API_KEY, ENGINE_ID, transport=recorder.transport)


@contextmanager
def _captured_logs() -> Iterator[list[str]]:
    """Every loguru line emitted while the block runs — formatted text, message, extra, exception."""
    lines: list[str] = []

    def sink(message: Any) -> None:
        record = message.record
        lines.append(str(message))
        lines.append(str(record["message"]))
        lines.append(repr(record["extra"]))
        if record["exception"] is not None:
            lines.append(repr(record["exception"].value))

    handler_id = logger.add(sink, level=0, format="{level} {name} {message}")
    try:
        yield lines
    finally:
        logger.remove(handler_id)


# --------------------------------------------------------------------------- DoD-5


def test_the_endpoint_constant_is_the_custom_search_url__S028_001_DoD5() -> None:
    """DoD-5 (D1): the module constant is the Custom Search JSON API endpoint, verbatim."""
    assert GOOGLE_CUSTOM_SEARCH_URL == "https://www.googleapis.com/customsearch/v1"


def test_one_get_request_carries_the_three_parameters_and_the_key_header__S028_001_DoD5() -> None:
    """DoD-5 (D1, D6): exactly one GET, the three query parameters and no others, key in a header."""
    recorder = Recorder(json_handler({"items": THREE_ITEMS}))

    run(make_provider(recorder).search(QUERY, LIMIT))

    assert len(recorder.requests) == 1
    request = recorder.requests[0]
    assert request.method == "GET"
    assert request.url.scheme == EXPECTED_SCHEME
    assert request.url.host == EXPECTED_HOST
    assert request.url.path == EXPECTED_PATH
    assert set(request.url.params) == {"cx", "q", "num"}
    assert request.url.params["cx"] == ENGINE_ID
    assert request.url.params["q"] == QUERY
    assert request.url.params["num"] == "5"
    assert request.headers[KEY_HEADER] == API_KEY
    assert request.content == b""


def test_the_key_appears_nowhere_in_the_request_url__S028_001_DoD5() -> None:
    """DoD-5 (`001.context.md`): the key travels in the header only, never in the URL."""
    recorder = Recorder(json_handler({"items": THREE_ITEMS}))

    run(make_provider(recorder).search(QUERY, LIMIT))

    rendered = str(recorder.requests[0].url)
    assert API_KEY not in rendered
    assert "key=" not in rendered


# --------------------------------------------------------------------------- DoD-6


def test_three_items_become_three_results_in_item_order__S028_001_DoD6() -> None:
    """DoD-6 (D1, D4): `title`, `link` and `snippet` map to `title`, `url` and `snippet`."""
    recorder = Recorder(json_handler({"items": THREE_ITEMS}))

    results = run(make_provider(recorder).search(QUERY, LIMIT))

    assert results == THREE_RESULTS


# --------------------------------------------------------------------------- DoD-7


def test_a_body_without_an_items_key_is_zero_results__S028_001_DoD7() -> None:
    """DoD-7: `items` absent means zero results, and is a success rather than a failure."""
    recorder = Recorder(json_handler({"kind": "customsearch#search"}))

    assert run(make_provider(recorder).search(QUERY, LIMIT)) == []


def test_items_that_are_not_objects_or_lack_a_string_link_are_skipped__S028_001_DoD7() -> None:
    """DoD-7: a non-object element, or one whose `link` is missing or not a string, is dropped."""
    items: list[Any] = [
        "a bare string",
        7,
        None,
        ["https://example.test/listy"],
        {"title": "no link at all", "snippet": "dropped"},
        {"title": "numeric link", "link": 5, "snippet": "dropped"},
        {"title": "Kept", "link": "https://example.test/kept", "snippet": "the only survivor"},
    ]
    recorder = Recorder(json_handler({"items": items}))

    results = run(make_provider(recorder).search(QUERY, LIMIT))

    assert results == [
        WebResult(title="Kept", url="https://example.test/kept", snippet="the only survivor")
    ]


def test_a_missing_or_non_string_title_or_snippet_becomes_an_empty_string__S028_001_DoD7() -> None:
    """DoD-7: only the two text fields degrade to `""`; the item itself is kept."""
    items: list[Any] = [
        {"link": "https://example.test/bare"},
        {"link": "https://example.test/typed", "title": 7, "snippet": ["x"]},
    ]
    recorder = Recorder(json_handler({"items": items}))

    results = run(make_provider(recorder).search(QUERY, LIMIT))

    assert results == [
        WebResult(title="", url="https://example.test/bare", snippet=""),
        WebResult(title="", url="https://example.test/typed", snippet=""),
    ]


def test_more_items_than_the_limit_are_truncated_to_the_limit__S028_001_DoD7() -> None:
    """DoD-7: at most `limit` results, taken from the front of the response order."""
    recorder = Recorder(json_handler({"items": THREE_ITEMS}))

    results = run(make_provider(recorder).search(QUERY, 2))

    assert results == THREE_RESULTS[:2]


# --------------------------------------------------------------------------- DoD-8

FAILURE_CASES = (
    pytest.param(status_handler(403), id="status-403"),
    pytest.param(status_handler(429), id="status-429"),
    pytest.param(status_handler(500), id="status-500"),
    pytest.param(raising_handler(httpx.ConnectError), id="connect-error"),
    pytest.param(raising_handler(httpx.ReadTimeout), id="read-timeout"),
    pytest.param(content_handler(200, b"<html>not json at all</html>"), id="body-not-json"),
    pytest.param(json_handler([{"link": "https://example.test/array"}]), id="body-json-array"),
    pytest.param(json_handler({"items": {"link": "https://example.test/object"}}), id="items-not-a-list"),
)


@pytest.mark.parametrize("handler", FAILURE_CASES)
def test_every_failure_raises_one_typed_tool_failure__S028_001_DoD8(handler: Handler) -> None:
    """DoD-8 (D5): one error shape for every failure — code, detail, and no chained cause."""
    recorder = Recorder(handler)

    with pytest.raises(ToolFailedError) as raised:
        run(make_provider(recorder).search(QUERY, LIMIT))

    error = raised.value
    assert error.code == EXPECTED_CODE
    assert error.detail == EXPECTED_DETAIL
    assert error.__cause__ is None
    assert error.__suppress_context__ is True


@pytest.mark.parametrize("handler", FAILURE_CASES)
def test_no_failure_leaks_the_query_the_key_the_engine_id_or_the_host__S028_001_DoD8(handler: Handler) -> None:
    """DoD-8 (D5, D6): the error's `str`, message and detail carry none of the four."""
    recorder = Recorder(handler)

    with pytest.raises(ToolFailedError) as raised:
        run(make_provider(recorder).search(QUERY, LIMIT))

    error = raised.value
    rendered = " ".join([str(error), error.message or "", json.dumps(error.detail)])
    for forbidden in (QUERY, API_KEY, ENGINE_ID, "googleapis"):
        assert forbidden not in rendered


# --------------------------------------------------------------------------- DoD-9

TIMEOUT_KEYS = ("connect", "read", "write", "pool")


def test_the_default_timeout_constant_is_ten_seconds__S028_001_DoD9() -> None:
    """DoD-9 (D9): the module constant is 10 seconds."""
    assert DEFAULT_TIMEOUT_SECONDS == pytest.approx(10.0)


def test_the_request_carries_the_ten_second_timeout_by_default__S028_001_DoD9() -> None:
    """DoD-9 (D9): all four timeout phases of the outgoing request are 10.0."""
    recorder = Recorder(json_handler({"items": THREE_ITEMS}))

    run(make_provider(recorder).search(QUERY, LIMIT))

    timeout = recorder.requests[0].extensions["timeout"]
    for key in TIMEOUT_KEYS:
        assert timeout[key] == pytest.approx(10.0)


def test_a_constructed_timeout_is_the_one_applied__S028_001_DoD9() -> None:
    """DoD-9 (D9): the constructor keyword wins over the constant."""
    recorder = Recorder(json_handler({"items": THREE_ITEMS}))
    provider = GoogleCustomSearchProvider(
        API_KEY, ENGINE_ID, timeout_seconds=2.5, transport=recorder.transport
    )

    run(provider.search(QUERY, LIMIT))

    timeout = recorder.requests[0].extensions["timeout"]
    for key in TIMEOUT_KEYS:
        assert timeout[key] == pytest.approx(2.5)


# --------------------------------------------------------------------------- DoD-10


def test_two_identical_searches_make_two_requests__S028_001_DoD10() -> None:
    """DoD-10 (D7, brief Out): nothing is cached between calls on one instance."""
    recorder = Recorder(json_handler({"items": THREE_ITEMS}))
    provider = make_provider(recorder)

    first = run(provider.search(QUERY, LIMIT))
    second = run(provider.search(QUERY, LIMIT))

    assert len(recorder.requests) == 2
    assert first == second
    for request in recorder.requests:
        assert request.url.params["q"] == QUERY


# --------------------------------------------------------------------------- DoD-11


def test_neither_a_success_nor_a_failure_logs_the_query_or_the_credentials__S028_001_DoD11() -> None:
    """DoD-11 (D7, deployment.md redaction rule): no record at any level carries the three.

    Each of the three is forbidden in both its raw and its URL-encoded spelling: the three
    travel in a request URL (the key in a header, the other two as query parameters), and a
    record quoting that URL carries the engine id verbatim but the query percent-encoded.
    """
    with _captured_logs() as lines:
        success = Recorder(json_handler({"items": THREE_ITEMS}))
        run(make_provider(success).search(QUERY, LIMIT))

        failing = Recorder(status_handler(500))
        with pytest.raises(ToolFailedError):
            run(make_provider(failing).search(QUERY, LIMIT))

    for line in lines:
        for forbidden in _forbidden_forms(QUERY, API_KEY, ENGINE_ID):
            assert forbidden not in line


#: The logger names httpx emits its own per-request record through. Both are checked because
#: httpx has used each across the supported range (`httpx>=0.27,<1.0`), and the requirement is
#: about httpx's request log, not about one spelling of its logger name.
HTTPX_REQUEST_LOGGER_NAMES = ("httpx", "httpx._client")

#: A logger that belongs to no library, used to prove the bridge and the sink are live.
CONTROL_LOGGER_NAME = "rphelper.tests.redaction"
CONTROL_MARKER = "redaction-control-marker"


@contextmanager
def _application_logging(
    monkeypatch: pytest.MonkeyPatch, log_file_path: Path
) -> Iterator[list[str]]:
    """The application's own logging configuration in force, with a capturing sink added after it.

    `configure_logging` mutates process-global state (loguru's sinks and the stdlib root
    logger), so this snapshots and restores both, and keeps the file sink inside `tmp_path` —
    the same discipline, and the same restore shape, as `tests/test_logging.py`.
    """
    real_stderr = sys.stderr
    root = logging.getLogger()
    saved_root_handlers = list(root.handlers)
    saved_root_level = root.level

    monkeypatch.setattr(sys, "stderr", io.StringIO())
    monkeypatch.setenv("RPHELPER_LOG_FILE_PATH", str(log_file_path))
    configure_logging(Settings(_env_file=None))  # type: ignore[call-arg]

    lines: list[str] = []

    def sink(message: Any) -> None:
        record = message.record
        lines.append(str(message))
        lines.append(str(record["message"]))

    logger.add(sink, level=0, format="{level} {name} {message}")
    try:
        yield lines
    finally:
        logger.remove()  # also closes the file sink `configure_logging` opened
        logger.add(real_stderr)
        root.handlers[:] = saved_root_handlers
        root.setLevel(saved_root_level)


@pytest.mark.parametrize("logger_name", HTTPX_REQUEST_LOGGER_NAMES)
def test_an_httpx_request_record_reaches_no_loguru_sink__S028_001_DoD11(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, logger_name: str
) -> None:
    """DoD-11 (D7, deployment.md redaction rule): httpx's own request log reaches no sink.

    DoD-11's subject is the sink, not the provider: with a sink capturing every level, a
    search must produce no record carrying the query, the key or the engine id. The provider
    emits nothing, but the HTTP client it uses logs every completed request as the full
    request URL — and this provider's URL carries the engine id and the query. So the clause
    holds only if httpx's request record never arrives, and this pins that property directly,
    so a later change to the logging configuration cannot silently re-open the leak.

    It asserts the observable property — a record emitted through httpx's own logger at the
    level its request log uses is absent from the sink — and not any mechanism: a raised
    level, a filter, `propagate` or anything else all satisfy it. The control record proves
    the bridge and the sink are working, so absence means suppression and not a dead sink.
    """
    leaky_record = (
        f"HTTP Request: GET {GOOGLE_CUSTOM_SEARCH_URL}"
        f"?cx={quote_plus(ENGINE_ID)}&q={quote_plus(QUERY)}&num={LIMIT}"
        ' "HTTP/1.1 200 OK"'
    )

    with _application_logging(monkeypatch, tmp_path / "logs" / "rphelper.log") as lines:
        logging.getLogger(logger_name).info(leaky_record)
        logging.getLogger(CONTROL_LOGGER_NAME).info(CONTROL_MARKER)

    assert any(CONTROL_MARKER in line for line in lines), (
        "precondition: the stdlib-to-loguru bridge and the capturing sink are live"
    )
    for line in lines:
        assert "HTTP Request" not in line
        for forbidden in _forbidden_forms(QUERY, API_KEY, ENGINE_ID):
            assert forbidden not in line


# --------------------------------------------------------------------------- DoD-12

FORBIDDEN_IMPORT_ROOTS = ("fastapi", "app.config", "app.secrets", "app.db", "app.services.tools")


def _module_imports(module: object) -> list[tuple[str, str | None]]:
    """Every import in the module's own source as `(module, imported name or None)`.

    Read as text with `ast`, so the answer does not depend on what the process imported.
    """
    module_file = getattr(module, "__file__", None)
    assert module_file is not None
    tree = ast.parse(Path(module_file).read_text(encoding="utf-8"))
    package = "app.services.web_search"
    found: list[tuple[str, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0:
                imported = node.module or ""
            else:
                parts = package.split(".")
                base = parts[: len(parts) - (node.level - 1)]
                imported = ".".join([*base, *([node.module] if node.module else [])])
            found.extend((imported, alias.name) for alias in node.names)
        elif isinstance(node, ast.Import):
            found.extend((alias.name, None) for alias in node.names)
    return found


def _under(name: str, package: str) -> bool:
    return name == package or name.startswith(package + ".")


def _offenders(module: object, forbidden: str) -> list[str]:
    offenders: list[str] = []
    for imported, name in _module_imports(module):
        full = imported if name is None else f"{imported}.{name}"
        if _under(imported, forbidden) or _under(full, forbidden):
            offenders.append(full)
    return offenders


@pytest.mark.parametrize("forbidden", FORBIDDEN_IMPORT_ROOTS)
def test_the_provider_module_imports_none_of_the_forbidden_packages__S028_001_DoD12(forbidden: str) -> None:
    """DoD-12 (D4): `provider.py` knows nothing of fastapi, settings, secrets, the db or tools."""
    assert _offenders(provider_module, forbidden) == []


@pytest.mark.parametrize("forbidden", FORBIDDEN_IMPORT_ROOTS)
def test_the_google_module_imports_none_of_the_forbidden_packages__S028_001_DoD12(forbidden: str) -> None:
    """DoD-12 (D4): `google.py` holds the same import ban."""
    assert _offenders(google_module, forbidden) == []


def test_the_provider_module_imports_no_httpx__S028_001_DoD12() -> None:
    """DoD-12 (D4): the seam is transport-free — only the implementation knows httpx."""
    assert _offenders(provider_module, "httpx") == []
