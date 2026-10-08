"""Tests for ``app.services.llm.client`` — the one OpenAI-compatible client.

Feature 006, step 002 (``002.openai-compatible-client.md``). Every expected value comes from
that step's Interface intent and DoD-1 .. DoD-15, ``002.context.md`` and feature 006
``context.md`` D2 / D3 / D5 / D6 / D7 / D13:

- the probe outcome is one of ``reachable`` / ``unreachable`` / ``auth_failed`` /
  ``model_list_empty`` (D6's table: 2xx with names -> reachable; 2xx with none ->
  model_list_empty; 401/403 -> auth_failed; transport failure, timeout, any other non-2xx,
  or an unreadable 2xx -> unreachable), and the probe never raises;
- ``embed`` raises ``llm_unreachable`` with a structured reason (``unreachable`` /
  ``auth_failed`` / the distinct no-usable-vector reason) and never returns an empty vector;
- the base URL may be pasted as ``http://host:8080``, ``http://host:8080/`` or
  ``http://host:8080/v1`` and all reach the same OpenAI-compatible ``/v1/...`` endpoint;
- the credential is sent as a bearer header when present and no authorization header at all
  when absent; the client resolves nothing and reads no environment.

Outbound HTTP is faked with ``httpx.MockTransport`` through the frozen ``transport=`` seam;
async code runs under ``asyncio.run``. Tests are suffixed ``__S006_002_DoD<n>``.
"""

import ast
import asyncio
import importlib
import inspect
import json
import re
import socket
import time
import tomllib
from collections.abc import Callable, Coroutine, Sequence
from importlib.metadata import version as installed_version
from pathlib import Path
from typing import Any

import httpx
import pytest
from packaging.requirements import Requirement
from packaging.version import Version

import app.services.llm.client as client_module
from app.errors import LlmUnreachableError
from app.services.llm.client import EMBED_NO_VECTOR_REASON, LlmClient, ProbeOutcome, ProbeResult

BACKEND_DIR = Path(__file__).resolve().parents[1]
PYPROJECT = BACKEND_DIR / "pyproject.toml"

HOST = "http://llm.test:8080"
MODELS_URL = "http://llm.test:8080/v1/models"
EMBEDDINGS_URL = "http://llm.test:8080/v1/embeddings"
CREDENTIAL = "sk-S006-SECRET-CREDENTIAL"
TIMEOUT = 2.5

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


def models_listing(*names: str) -> dict[str, Any]:
    """An OpenAI-compatible models listing naming ``names`` in order."""
    return {
        "object": "list",
        "data": [{"id": name, "object": "model", "created": 0, "owned_by": "test"} for name in names],
    }


def embeddings_listing(vectors: Sequence[Sequence[float]], order: Sequence[int] | None = None) -> dict[str, Any]:
    """An OpenAI-compatible embeddings response; ``order`` permutes the entries (indices kept)."""
    entries = [
        {"object": "embedding", "index": index, "embedding": list(vector)} for index, vector in enumerate(vectors)
    ]
    if order is not None:
        entries = [entries[position] for position in order]
    return {"object": "list", "data": entries, "model": "embed-model", "usage": {"prompt_tokens": 1, "total_tokens": 1}}


def ok_router(request: httpx.Request) -> httpx.Response:
    """Answer a models listing or an embeddings response depending on the path."""
    if request.url.path.endswith("/embeddings"):
        return httpx.Response(200, json=embeddings_listing([[0.5, 0.25]]))
    return httpx.Response(200, json=models_listing("model-a"))


def per_input_router(request: httpx.Request) -> httpx.Response:
    """Like ``ok_router``, but the embeddings answer holds exactly one vector per requested input."""
    if request.url.path.endswith("/embeddings"):
        inputs = json.loads(request.content)["input"]
        count = len(inputs) if isinstance(inputs, list) else 1
        return httpx.Response(200, json=embeddings_listing([[0.5, float(index)] for index in range(count)]))
    return httpx.Response(200, json=models_listing("model-a"))


def status_handler(status: int, body: Any = None) -> Handler:
    def respond(request: httpx.Request) -> httpx.Response:
        if body is None:
            return httpx.Response(status, json={"error": {"message": "provider says no"}})
        if isinstance(body, str | bytes):
            return httpx.Response(status, content=body)
        return httpx.Response(status, json=body)

    return respond


def raising_handler(error_type: type[httpx.TransportError]) -> Handler:
    def respond(request: httpx.Request) -> httpx.Response:
        raise error_type("simulated transport failure", request=request)

    return respond


def make_client(recorder: Recorder, base_url: str = HOST, api_key: str | None = CREDENTIAL,
                timeout: float = TIMEOUT) -> LlmClient:
    return LlmClient(base_url, api_key, timeout, transport=recorder.transport)


def probe_with(handler: Handler, api_key: str | None = CREDENTIAL) -> tuple[ProbeResult, Recorder]:
    recorder = Recorder(handler)
    result = run(make_client(recorder, api_key=api_key).probe())
    return result, recorder


def embed_failure(handler: Handler, texts: Sequence[str] = ("hello",)) -> LlmUnreachableError:
    recorder = Recorder(handler)
    client = make_client(recorder)
    with pytest.raises(LlmUnreachableError) as caught:
        run(client.embed("embed-model", list(texts)))
    return caught.value


def module_tree() -> ast.Module:
    source_file = inspect.getsourcefile(client_module)
    assert source_file is not None
    return ast.parse(Path(source_file).read_text(encoding="utf-8"))


def package_init_tree() -> ast.Module:
    package = importlib.import_module("app.services.llm")
    source_file = inspect.getsourcefile(package)
    assert source_file is not None
    return ast.parse(Path(source_file).read_text(encoding="utf-8"))


def docstring_nodes(tree: ast.Module) -> set[int]:
    """``id()`` of every docstring constant (module, class, function)."""
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                found.add(id(body[0].value))
    return found


def code_strings(tree: ast.Module) -> list[str]:
    """Every string constant in the module that is not a docstring."""
    skip = docstring_nodes(tree)
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip]


def imported_modules(tree: ast.Module, package: str) -> list[str]:
    """Absolute module names imported anywhere in ``tree`` (relative ones resolved against ``package``)."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                base_parts = parts[: len(parts) - (node.level - 1)]
                base = ".".join(base_parts)
                module = f"{base}.{node.module}" if node.module else base
            else:
                module = node.module or ""
            names.append(module)
            names.extend(f"{module}.{alias.name}" for alias in node.names)
    return names


def identifiers(tree: ast.AST) -> set[str]:
    """Every Name id, Attribute attr, argument name and def/class name in ``tree``."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            found.add(node.name)
        elif isinstance(node, ast.keyword) and node.arg is not None:
            found.add(node.arg)
    return found


# --------------------------------------------------------------------------- DoD-1


def _pyproject() -> dict[str, Any]:
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)


def _requirements_named(entries: Sequence[str], name: str) -> list[Requirement]:
    parsed = [Requirement(entry) for entry in entries if isinstance(entry, str)]
    return [requirement for requirement in parsed if requirement.name.lower() == name]


def test_httpx_is_a_runtime_dependency__S006_002_DoD1() -> None:
    """006/002 DoD-1: ``httpx`` appears exactly once in ``[project] dependencies``."""
    runtime = _pyproject()["project"]["dependencies"]
    assert len(_requirements_named(runtime, "httpx")) == 1


def test_httpx_is_no_longer_named_by_the_dev_group__S006_002_DoD1() -> None:
    """006/002 DoD-1 (002.context gotcha): the dev group stops naming httpx rather than duplicating it."""
    groups = _pyproject().get("dependency-groups", {})
    dev = [entry for entry in groups.get("dev", []) if isinstance(entry, str)]
    assert _requirements_named(dev, "httpx") == []


def test_httpx_constraint_is_compatible_with_the_previous_one__S006_002_DoD1() -> None:
    """006/002 DoD-1: the promoted constraint admits what ``>=0.27,<1.0`` admitted, incl. the installed httpx."""
    (requirement,) = _requirements_named(_pyproject()["project"]["dependencies"], "httpx")
    specifier = requirement.specifier
    assert specifier.contains(Version(installed_version("httpx")))
    assert specifier.contains(Version("0.27.0"))
    assert specifier.contains(Version("0.28.1"))
    assert not specifier.contains(Version("0.26.0"))
    assert not specifier.contains(Version("1.0.0"))


# --------------------------------------------------------------------------- DoD-2


def test_constructing_the_client_issues_no_request__S006_002_DoD2() -> None:
    """006/002 DoD-2: construction from base URL, credential and timeout touches no network."""
    recorder = Recorder(ok_router)
    LlmClient(HOST, CREDENTIAL, TIMEOUT, transport=recorder.transport)
    LlmClient(HOST, None, TIMEOUT, transport=recorder.transport)
    assert recorder.requests == []


def test_probe_without_a_credential_sends_no_authorization_header__S006_002_DoD2() -> None:
    """006/002 DoD-2: given no credential, the probe request carries no authorization header at all."""
    _, recorder = probe_with(ok_router, api_key=None)
    assert len(recorder.requests) == 1
    assert "authorization" not in recorder.requests[0].headers


def test_embed_without_a_credential_sends_no_authorization_header__S006_002_DoD2() -> None:
    """006/002 DoD-2: given no credential, the embeddings request carries no authorization header."""
    recorder = Recorder(ok_router)
    run(make_client(recorder, api_key=None).embed("embed-model", ["hello"]))
    assert len(recorder.requests) == 1
    assert "authorization" not in recorder.requests[0].headers


def test_a_pointer_shaped_credential_is_sent_verbatim_not_resolved__S006_002_DoD2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """006/002 DoD-2: the client resolves nothing — a ``$NAME`` string is the credential itself.

    With ``S006_POINTER_VAR`` unset, a client that resolved would raise ``secret_ref_missing``;
    with it set, a client that resolved would send the variable's value.
    """
    monkeypatch.delenv("S006_POINTER_VAR", raising=False)
    recorder = Recorder(ok_router)
    result = run(make_client(recorder, api_key="$S006_POINTER_VAR").probe())
    assert result.outcome == ProbeOutcome.REACHABLE
    assert recorder.requests[0].headers["authorization"] == "Bearer $S006_POINTER_VAR"

    monkeypatch.setenv("S006_POINTER_VAR", "resolved-value-must-not-appear")
    recorder = Recorder(ok_router)
    run(make_client(recorder, api_key="$S006_POINTER_VAR").probe())
    assert recorder.requests[0].headers["authorization"] == "Bearer $S006_POINTER_VAR"


def test_no_credential_is_picked_up_from_the_environment__S006_002_DoD2(monkeypatch: pytest.MonkeyPatch) -> None:
    """006/002 DoD-2: with credential-looking variables set, a credential-less client still sends none."""
    traps = {
        "OPENAI_API_KEY": "trap-openai-key",
        "LLM_API_KEY": "trap-llm-key",
        "API_KEY": "trap-api-key",
        "LLAMASWAP_API_KEY": "trap-llamaswap-key",
        "RPHELPER_LLM_API_KEY": "trap-rphelper-key",
    }
    for name, value in traps.items():
        monkeypatch.setenv(name, value)
    recorder = Recorder(ok_router)
    client = make_client(recorder, api_key=None)
    run(client.probe())
    run(client.embed("embed-model", ["hello"]))
    assert len(recorder.requests) == 2
    for request in recorder.requests:
        assert "authorization" not in request.headers
        rendered = str(request.url) + " ".join(f"{k}:{v}" for k, v in request.headers.items())
        rendered += request.content.decode("utf-8", errors="replace")
        for value in traps.values():
            assert value not in rendered


def test_module_reads_no_environment_and_imports_no_secret_resolution__S006_002_DoD2() -> None:
    """006/002 DoD-2: the module neither touches ``os.environ``/``getenv`` nor pulls in ``resolve_secret``."""
    tree = module_tree()
    names = identifiers(tree)
    assert "environ" not in names
    assert "getenv" not in names
    assert "resolve_secret" not in names
    imported = imported_modules(tree, "app.services.llm")
    assert not [name for name in imported if name == "app.secrets" or name.startswith("app.secrets.")]
    secrets_module = importlib.import_module("app.secrets")
    for name, value in vars(client_module).items():
        if name.startswith("__"):
            continue
        assert value is not secrets_module, name
        assert value is not secrets_module.resolve_secret, name


def test_one_clients_credential_does_not_leak_into_anothers_request__S006_002_DoD2() -> None:
    """006/002 DoD-2 (002.context: no shared client): a credential-less client after a keyed one sends none."""
    keyed = Recorder(ok_router)
    run(make_client(keyed, api_key=CREDENTIAL).probe())
    bare = Recorder(ok_router)
    run(make_client(bare, api_key=None).probe())
    assert keyed.requests[0].headers["authorization"] == f"Bearer {CREDENTIAL}"
    assert "authorization" not in bare.requests[0].headers


# --------------------------------------------------------------------------- DoD-3


def test_probe_sends_the_credential_as_a_bearer_header__S006_002_DoD3() -> None:
    """006/002 DoD-3: the models-listing request carries ``Authorization: Bearer <credential>``."""
    _, recorder = probe_with(ok_router, api_key=CREDENTIAL)
    assert recorder.requests[0].headers["authorization"] == f"Bearer {CREDENTIAL}"


def test_embed_sends_the_credential_as_a_bearer_header__S006_002_DoD3() -> None:
    """006/002 DoD-3: the embeddings request carries ``Authorization: Bearer <credential>``."""
    recorder = Recorder(ok_router)
    run(make_client(recorder).embed("embed-model", ["hello"]))
    assert recorder.requests[0].headers["authorization"] == f"Bearer {CREDENTIAL}"


def test_every_request_of_a_reused_client_carries_the_bearer_header__S006_002_DoD3() -> None:
    """006/002 DoD-3: repeated probe and embed calls on one client all carry the bearer credential."""
    recorder = Recorder(per_input_router)
    client = make_client(recorder, api_key="sk-another-credential")
    run(client.probe())
    run(client.embed("embed-model", ["one"]))
    run(client.probe())
    run(client.embed("embed-model", ["two", "three"]))
    assert len(recorder.requests) == 4
    for request in recorder.requests:
        assert request.headers["authorization"] == "Bearer sk-another-credential"


def test_bearer_header_is_sent_on_failing_responses_too__S006_002_DoD3() -> None:
    """006/002 DoD-3: the header is on the request even when the server answers 401."""
    _, recorder = probe_with(status_handler(401), api_key=CREDENTIAL)
    assert recorder.requests[0].headers["authorization"] == f"Bearer {CREDENTIAL}"


# --------------------------------------------------------------------------- DoD-4

BASE_URL_FORMS = [
    "http://llm.test:8080",
    "http://llm.test:8080/",
    "http://llm.test:8080/v1",
    "http://llm.test:8080/v1/",
]


@pytest.mark.parametrize("base_url", BASE_URL_FORMS)
def test_probe_reaches_the_same_models_endpoint_for_every_base_url_form__S006_002_DoD4(base_url: str) -> None:
    """006/002 DoD-4: with or without a trailing slash, with or without ``/v1`` — one models endpoint."""
    recorder = Recorder(ok_router)
    run(make_client(recorder, base_url=base_url).probe())
    assert len(recorder.requests) == 1
    request = recorder.requests[0]
    assert request.method == "GET"
    assert str(request.url) == MODELS_URL
    assert "//" not in request.url.path
    assert "/v1/v1" not in request.url.path


@pytest.mark.parametrize("base_url", BASE_URL_FORMS)
def test_embed_reaches_the_same_embeddings_endpoint_for_every_base_url_form__S006_002_DoD4(base_url: str) -> None:
    """006/002 DoD-4: the embeddings path composes the same way from each base-URL form."""
    recorder = Recorder(ok_router)
    run(make_client(recorder, base_url=base_url).embed("embed-model", ["hello"]))
    assert len(recorder.requests) == 1
    request = recorder.requests[0]
    assert request.method == "POST"
    assert str(request.url) == EMBEDDINGS_URL
    assert "//" not in request.url.path
    assert "/v1/v1" not in request.url.path


def test_the_three_pasted_forms_produce_identical_urls__S006_002_DoD4() -> None:
    """006/002 DoD-4: ``host``, ``host/`` and ``host/v1`` are indistinguishable on the wire."""
    urls: set[str] = set()
    for base_url in ("http://llm.test:8080", "http://llm.test:8080/", "http://llm.test:8080/v1"):
        recorder = Recorder(ok_router)
        run(make_client(recorder, base_url=base_url).probe())
        urls.add(str(recorder.requests[0].url))
    assert urls == {MODELS_URL}


# --------------------------------------------------------------------------- DoD-5


def test_listing_with_models_is_reachable_with_names_in_server_order__S006_002_DoD5() -> None:
    """006/002 DoD-5: a 2xx listing naming models -> ``reachable`` with the names, server order kept."""
    names = ("zeta-chat", "alpha-embed", "Mistral-7B-Instruct", "gpt-4o")
    result, _ = probe_with(lambda request: httpx.Response(200, json=models_listing(*names)))
    assert isinstance(result, ProbeResult)
    assert result.outcome == ProbeOutcome.REACHABLE
    assert result.outcome == "reachable"
    assert tuple(result.model_names) == names


def test_listing_with_one_model_is_reachable__S006_002_DoD5() -> None:
    """006/002 DoD-5: "at least one" — a single model is enough for ``reachable``."""
    result, _ = probe_with(lambda request: httpx.Response(200, json=models_listing("only-model")))
    assert result.outcome == ProbeOutcome.REACHABLE
    assert tuple(result.model_names) == ("only-model",)


def test_any_2xx_status_with_models_is_reachable__S006_002_DoD5() -> None:
    """006/002 DoD-5 (D6: "2xx"): a non-200 success status still classifies as ``reachable``."""
    result, _ = probe_with(lambda request: httpx.Response(203, json=models_listing("m1", "m2")))
    assert result.outcome == ProbeOutcome.REACHABLE
    assert tuple(result.model_names) == ("m1", "m2")


def test_probe_outcome_is_the_closed_four_value_set__S006_002_DoD5() -> None:
    """006/002 DoD-5 (D6): the outcome values are exactly the four strings of the taxonomy."""
    assert {member.value for member in ProbeOutcome} == {
        "reachable",
        "unreachable",
        "auth_failed",
        "model_list_empty",
    }


# --------------------------------------------------------------------------- DoD-6


def test_listing_with_no_models_is_model_list_empty__S006_002_DoD6() -> None:
    """006/002 DoD-6: a 2xx listing naming no models -> ``model_list_empty`` with no names."""
    result, _ = probe_with(lambda request: httpx.Response(200, json=models_listing()))
    assert result.outcome == ProbeOutcome.MODEL_LIST_EMPTY
    assert result.outcome == "model_list_empty"
    assert tuple(result.model_names) == ()


# --------------------------------------------------------------------------- DoD-7


@pytest.mark.parametrize("status", [401, 403])
def test_401_and_403_are_auth_failed__S006_002_DoD7(status: int) -> None:
    """006/002 DoD-7: a 401 and a 403 each yield ``auth_failed`` with no model names."""
    result, _ = probe_with(status_handler(status))
    assert result.outcome == ProbeOutcome.AUTH_FAILED
    assert result.outcome == "auth_failed"
    assert tuple(result.model_names) == ()


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_with_a_non_json_body_is_still_auth_failed__S006_002_DoD7(status: int) -> None:
    """006/002 DoD-7: the status decides; an HTML/plain-text 401/403 body does not change the outcome."""
    result, _ = probe_with(status_handler(status, "<html>Forbidden</html>"))
    assert result.outcome == ProbeOutcome.AUTH_FAILED


# --------------------------------------------------------------------------- DoD-8

TRANSPORT_FAILURES: list[type[httpx.TransportError]] = [
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.ReadError,
    httpx.RemoteProtocolError,
]


@pytest.mark.parametrize("error_type", TRANSPORT_FAILURES)
def test_transport_failures_and_timeouts_are_unreachable__S006_002_DoD8(
    error_type: type[httpx.TransportError],
) -> None:
    """006/002 DoD-8: a transport failure or timeout -> ``unreachable``; the probe raises nothing."""
    result, recorder = probe_with(raising_handler(error_type))
    assert len(recorder.requests) >= 1
    assert result.outcome == ProbeOutcome.UNREACHABLE
    assert result.outcome == "unreachable"
    assert tuple(result.model_names) == ()


@pytest.mark.parametrize("status", [500, 400, 404, 405, 422, 429, 502, 503, 504])
def test_other_non_2xx_statuses_are_unreachable__S006_002_DoD8(status: int) -> None:
    """006/002 DoD-8: a 500 — and any other non-2xx besides 401/403 — -> ``unreachable``."""
    result, _ = probe_with(status_handler(status))
    assert result.outcome == ProbeOutcome.UNREACHABLE
    assert tuple(result.model_names) == ()


def test_error_status_carrying_a_valid_listing_is_still_unreachable__S006_002_DoD8() -> None:
    """006/002 DoD-8: a 500 is ``unreachable`` even if its body happens to look like a listing."""
    result, _ = probe_with(lambda request: httpx.Response(500, json=models_listing("m1")))
    assert result.outcome == ProbeOutcome.UNREACHABLE
    assert tuple(result.model_names) == ()


UNREADABLE_2XX_BODIES: list[tuple[str, bytes]] = [
    ("not json", b"this is not json at all"),
    ("html page", b"<html><body>llama-swap UI</body></html>"),
    ("truncated json", b'{"object": "list", "data": [{"id": "m1"'),
    ("empty body", b""),
    ("json null", b"null"),
    ("json string", b'"models"'),
    ("json number", b"42"),
    ("top-level array", b'["m1", "m2"]'),
    ("no data key", b'{"object": "list", "models": [{"id": "m1"}]}'),
    ("data is a string", b'{"object": "list", "data": "m1"}'),
    ("data is an object", b'{"object": "list", "data": {"id": "m1"}}'),
    ("data is null", b'{"object": "list", "data": null}'),
]


@pytest.mark.parametrize(("label", "body"), UNREADABLE_2XX_BODIES, ids=[label for label, _ in UNREADABLE_2XX_BODIES])
def test_unreadable_or_misshapen_2xx_body_is_unreachable__S006_002_DoD8(label: str, body: bytes) -> None:
    """006/002 DoD-8: a 2xx body that is unparseable or not a models listing -> ``unreachable``, no raise."""
    result, _ = probe_with(
        lambda request: httpx.Response(200, content=body, headers={"content-type": "application/json"})
    )
    assert result.outcome == ProbeOutcome.UNREACHABLE, label
    assert tuple(result.model_names) == (), label


# --------------------------------------------------------------------------- DoD-9


def test_probe_request_carries_the_constructed_timeout__S006_002_DoD9() -> None:
    """006/002 DoD-9 (D13): the timeout the client was built with bounds the outgoing request."""
    recorder = Recorder(ok_router)
    run(make_client(recorder, timeout=2.5).probe())
    timeout = recorder.requests[0].extensions["timeout"]
    assert timeout["connect"] == pytest.approx(2.5)
    assert timeout["read"] == pytest.approx(2.5)


def test_probe_timeout_follows_the_constructor_argument__S006_002_DoD9() -> None:
    """006/002 DoD-9: a different constructed timeout is the one applied (not a fixed default)."""
    recorder = Recorder(ok_router)
    run(make_client(recorder, timeout=0.75).probe())
    timeout = recorder.requests[0].extensions["timeout"]
    assert timeout["connect"] == pytest.approx(0.75)
    assert timeout["read"] == pytest.approx(0.75)


def test_probe_timeout_is_classified_as_unreachable__S006_002_DoD9() -> None:
    """006/002 DoD-9: a server that times out yields ``unreachable`` rather than an exception."""
    result, _ = probe_with(raising_handler(httpx.ReadTimeout))
    assert result.outcome == ProbeOutcome.UNREACHABLE


def test_silent_server_yields_unreachable_within_the_timeout__S006_002_DoD9(monkeypatch: pytest.MonkeyPatch) -> None:
    """006/002 DoD-9: against a real loopback socket that never answers, the probe returns promptly.

    The socket accepts the connection (backlog) and never writes a byte. With a 0.3 s timeout
    the probe must come back ``unreachable`` well before httpx's own 5 s default would.
    """
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setenv("no_proxy", "*")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.bind(("127.0.0.1", 0))
        server.listen(8)
        port = server.getsockname()[1]
        client = LlmClient(f"http://127.0.0.1:{port}", None, 0.3)

        async def bounded() -> ProbeResult:
            return await asyncio.wait_for(client.probe(), timeout=15.0)

        started = time.monotonic()
        result = run(bounded())
        elapsed = time.monotonic() - started
    finally:
        server.close()

    assert result.outcome == ProbeOutcome.UNREACHABLE
    assert elapsed < 3.0


# --------------------------------------------------------------------------- DoD-10


def test_embed_returns_one_vector_per_input_in_input_order__S006_002_DoD10() -> None:
    """006/002 DoD-10: a 2xx embeddings response -> one float vector per input, input order kept."""
    vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]]
    recorder = Recorder(lambda request: httpx.Response(200, json=embeddings_listing(vectors)))
    result = run(make_client(recorder).embed("embed-model", ["first", "second", "third"]))
    assert result == vectors
    assert all(isinstance(value, float) for vector in result for value in vector)


def test_embed_orders_vectors_by_input_index__S006_002_DoD10() -> None:
    """006/002 DoD-10: entries answered out of order are returned in input order (by their ``index``)."""
    vectors = [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]
    recorder = Recorder(lambda request: httpx.Response(200, json=embeddings_listing(vectors, order=[2, 0, 1])))
    result = run(make_client(recorder).embed("embed-model", ["a", "b", "c"]))
    assert result == vectors


def test_embed_single_input_returns_a_single_vector__S006_002_DoD10() -> None:
    """006/002 DoD-10: one input string -> a list holding exactly one vector."""
    recorder = Recorder(lambda request: httpx.Response(200, json=embeddings_listing([[0.25, -0.5, 0.75, 1.0]])))
    result = run(make_client(recorder).embed("embed-model", ["RPHelper embedding dimension probe"]))
    assert result == [[0.25, -0.5, 0.75, 1.0]]
    assert len(result[0]) == 4


def test_embed_posts_the_model_and_the_inputs__S006_002_DoD10() -> None:
    """006/002 DoD-10: the request names the model and carries the input strings, in order."""
    recorder = Recorder(lambda request: httpx.Response(200, json=embeddings_listing([[0.1], [0.2]])))
    run(make_client(recorder).embed("nomic-embed-text", ["alpha", "beta"]))
    request = recorder.requests[0]
    assert request.method == "POST"
    assert str(request.url) == EMBEDDINGS_URL
    payload = json.loads(request.content)
    assert payload["model"] == "nomic-embed-text"
    assert payload["input"] == ["alpha", "beta"]


# --------------------------------------------------------------------------- DoD-11

SENSITIVE_TEXT = "PRIVATE-INPUT-TEXT-S006"
PROVIDER_MARKER = "PROVIDER-BODY-MARKER-S006"


def _assert_redacted(error: LlmUnreachableError) -> None:
    rendered = " ".join(
        [
            str(error),
            repr(error),
            str(error.message),
            json.dumps(error.detail, default=str),
            json.dumps(error.to_wire(), default=str),
        ]
    )
    assert CREDENTIAL not in rendered
    assert "Bearer" not in rendered
    assert SENSITIVE_TEXT not in rendered
    assert PROVIDER_MARKER not in rendered


@pytest.mark.parametrize("error_type", TRANSPORT_FAILURES)
def test_embed_transport_failure_or_timeout_raises_llm_unreachable__S006_002_DoD11(
    error_type: type[httpx.TransportError],
) -> None:
    """006/002 DoD-11: a transport failure or timeout raises ``llm_unreachable`` with reason ``unreachable``."""
    error = embed_failure(raising_handler(error_type), texts=[SENSITIVE_TEXT])
    assert error.code == "llm_unreachable"
    assert error.detail == {"reason": "unreachable"}
    _assert_redacted(error)


@pytest.mark.parametrize("status", [401, 403])
def test_embed_auth_failure_raises_llm_unreachable_with_auth_failed__S006_002_DoD11(status: int) -> None:
    """006/002 DoD-11: a 401/403 raises ``llm_unreachable`` with reason ``auth_failed``."""
    body = {"error": {"message": f"invalid key {PROVIDER_MARKER}"}}
    error = embed_failure(status_handler(status, body), texts=[SENSITIVE_TEXT])
    assert error.code == "llm_unreachable"
    assert error.detail == {"reason": "auth_failed"}
    _assert_redacted(error)


@pytest.mark.parametrize("status", [400, 404, 422, 429, 500, 502, 503])
def test_embed_other_non_2xx_raises_llm_unreachable_with_unreachable__S006_002_DoD11(status: int) -> None:
    """006/002 DoD-11: any other non-2xx raises ``llm_unreachable`` with reason ``unreachable``."""
    body = {"error": {"message": f"upstream said {PROVIDER_MARKER} about {SENSITIVE_TEXT}"}}
    error = embed_failure(status_handler(status, body), texts=[SENSITIVE_TEXT])
    assert error.code == "llm_unreachable"
    assert error.detail == {"reason": "unreachable"}
    _assert_redacted(error)


def test_embed_failure_is_the_llm_unreachable_domain_error__S006_002_DoD11() -> None:
    """006/002 DoD-11 (D7): the raised error is the ``llm_unreachable`` subclass, answered as 502."""
    error = embed_failure(status_handler(500))
    assert isinstance(error, LlmUnreachableError)
    assert error.http_status == 502
    assert error.to_wire()["error"]["code"] == "llm_unreachable"
    assert error.to_wire()["error"]["detail"] == {"reason": "unreachable"}


def test_embed_failure_detail_carries_no_request_body__S006_002_DoD11() -> None:
    """006/002 DoD-11: neither the inputs nor the model-bearing request body appear in the error."""
    error = embed_failure(status_handler(500), texts=[SENSITIVE_TEXT, "second " + SENSITIVE_TEXT])
    _assert_redacted(error)
    assert set(error.detail) == {"reason"}


# --------------------------------------------------------------------------- DoD-12

NO_VECTOR_BODIES: list[tuple[str, dict[str, Any]]] = [
    ("empty data", {"object": "list", "data": [], "model": "chat-model"}),
    ("empty embedding", {"object": "list", "data": [{"object": "embedding", "index": 0, "embedding": []}]}),
    ("no data key", {"object": "list", "model": "chat-model"}),
    ("entry without embedding", {"object": "list", "data": [{"object": "embedding", "index": 0}]}),
]


def test_no_vector_reason_is_distinct_from_the_other_reasons__S006_002_DoD12() -> None:
    """006/002 DoD-12: the no-usable-vector reason is a distinct structured value."""
    assert isinstance(EMBED_NO_VECTOR_REASON, str)
    assert EMBED_NO_VECTOR_REASON
    assert EMBED_NO_VECTOR_REASON not in {"unreachable", "auth_failed"}
    assert EMBED_NO_VECTOR_REASON not in {member.value for member in ProbeOutcome}


@pytest.mark.parametrize(("label", "body"), NO_VECTOR_BODIES, ids=[label for label, _ in NO_VECTOR_BODIES])
def test_2xx_without_a_usable_vector_raises_the_distinct_reason__S006_002_DoD12(
    label: str, body: dict[str, Any]
) -> None:
    """006/002 DoD-12: 2xx with no usable vector -> ``llm_unreachable`` with the distinct reason, no success."""
    error = embed_failure(lambda request: httpx.Response(200, json=body), texts=["probe"])
    assert error.code == "llm_unreachable", label
    assert error.detail == {"reason": EMBED_NO_VECTOR_REASON}, label


def test_empty_data_never_returns_an_empty_success__S006_002_DoD12() -> None:
    """006/002 DoD-12: the "you designated a chat model" case never comes back as ``[]`` or ``[[]]``."""
    recorder = Recorder(lambda request: httpx.Response(200, json={"object": "list", "data": []}))
    client = make_client(recorder)
    outcome: object = None
    try:
        outcome = run(client.embed("chat-model", ["probe"]))
    except LlmUnreachableError as error:
        assert error.detail == {"reason": EMBED_NO_VECTOR_REASON}
    else:  # pragma: no cover - the failure this test exists to catch
        pytest.fail(f"embed returned {outcome!r} as a success for a response with no vector")


# --------------------------------------------------------------------------- DoD-13

PROVIDER_KIND_LITERALS = {"llamaswap", "openai"}


def _conditional_tests(tree: ast.Module) -> list[ast.AST]:
    tests: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If | ast.IfExp | ast.While | ast.Assert):
            tests.append(node.test)
        elif isinstance(node, ast.Match):
            tests.append(node.subject)
            tests.extend(case.pattern for case in node.cases)
            tests.extend(case.guard for case in node.cases if case.guard is not None)
        elif isinstance(node, ast.comprehension):
            tests.extend(node.ifs)
    return tests


def test_no_provider_kind_literal_appears_in_code__S006_002_DoD13() -> None:
    """006/002 DoD-13 (D5): no ``llamaswap`` / ``openai`` literal exists to reach a conditional."""
    offending = [value for value in code_strings(module_tree()) if value.strip().lower() in PROVIDER_KIND_LITERALS]
    assert offending == []


def test_no_conditional_mentions_a_provider_kind__S006_002_DoD13() -> None:
    """006/002 DoD-13 (D5): no conditional tests ``kind``/``provider`` or a provider-kind string."""
    for test in _conditional_tests(module_tree()):
        names = {name.lower() for name in identifiers(test)}
        assert "kind" not in names, ast.unparse(test)
        assert "provider_kind" not in names, ast.unparse(test)
        for node in ast.walk(test):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                lowered = node.value.lower()
                assert "llamaswap" not in lowered, ast.unparse(test)
                assert "openai" not in lowered, ast.unparse(test)


def test_client_takes_no_kind_parameter__S006_002_DoD13() -> None:
    """006/002 DoD-13: nothing about the client's construction or calls can dispatch on kind."""
    for function in (LlmClient.__init__, LlmClient.probe, LlmClient.embed):
        assert "kind" not in inspect.signature(function).parameters


@pytest.mark.parametrize(
    ("base_url", "expected_models_url"),
    [
        ("http://llamaswap.local:8080", "http://llamaswap.local:8080/v1/models"),
        ("https://api.openai.com/v1", "https://api.openai.com/v1/models"),
    ],
)
def test_the_same_request_serves_both_provider_styles__S006_002_DoD13(base_url: str, expected_models_url: str) -> None:
    """006/002 DoD-13 (D5): a llamaswap-style and an OpenAI-style base URL get the identical request shape."""
    recorder = Recorder(ok_router)
    result = run(make_client(recorder, base_url=base_url).probe())
    assert result.outcome == ProbeOutcome.REACHABLE
    request = recorder.requests[0]
    assert request.method == "GET"
    assert str(request.url) == expected_models_url
    assert request.headers["authorization"] == f"Bearer {CREDENTIAL}"


# --------------------------------------------------------------------------- DoD-14

FORBIDDEN_IMPORT_ROOTS = ("fastapi", "starlette", "sqlalchemy", "sqlite3", "sqlite_vec", "app.db", "app.routers")
SQL_PATTERN = re.compile(
    r"\b(select\s+.+\s+from|insert\s+into|update\s+\w+\s+set|delete\s+from|create\s+table|drop\s+table)\b",
    re.IGNORECASE | re.DOTALL,
)


def _is_forbidden(name: str) -> bool:
    return any(name == root or name.startswith(root + ".") for root in FORBIDDEN_IMPORT_ROOTS)


def test_module_imports_no_fastapi_and_no_database__S006_002_DoD14() -> None:
    """006/002 DoD-14: no ``fastapi``/``starlette`` symbol and no database layer is imported."""
    for tree in (module_tree(), package_init_tree()):
        imported = imported_modules(tree, "app.services.llm")
        assert [name for name in imported if _is_forbidden(name)] == []


def test_module_binds_no_fastapi_object__S006_002_DoD14() -> None:
    """006/002 DoD-14: no name in the module is a FastAPI/Starlette object."""
    for name, value in vars(client_module).items():
        if name.startswith("__"):
            continue
        owner = getattr(value, "__module__", None)
        if inspect.ismodule(value):
            owner = value.__name__
        if not isinstance(owner, str):
            owner = ""
        assert not owner.startswith(("fastapi", "starlette")), name


def test_module_names_no_response_status_of_its_own__S006_002_DoD14() -> None:
    """006/002 DoD-14: no ``status_code=`` response building, no ``http_status``, no 409/422/502 literal."""
    tree = module_tree()
    names = identifiers(tree)
    assert "http_status" not in names
    assert "HTTPException" not in names
    assert "JSONResponse" not in names
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            assert not [kw for kw in node.keywords if kw.arg == "status_code"], ast.unparse(node)
        if isinstance(node, ast.Constant) and type(node.value) is int:
            assert node.value not in {409, 422, 502}, node.value


def test_module_issues_no_sql__S006_002_DoD14() -> None:
    """006/002 DoD-14: no SQL text and no statement execution in the module."""
    tree = module_tree()
    assert [value for value in code_strings(tree) if SQL_PATTERN.search(value)] == []
    names = identifiers(tree)
    assert "execute" not in names
    assert "executescript" not in names
    assert "Connection" not in names
    assert "Engine" not in names


# 006/002 DoD-15's two ``chat_stream``-absence tests were removed by feature 021 step 003
# (``003.chat-stream-client.md`` DoD-8): ``chat_stream`` now exists by design.
