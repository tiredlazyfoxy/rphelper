"""Tests for ``app.errors`` — the base domain error, its wire body and its one handler.

Every expected value here comes from ``003.errors-and-secrets.md`` (Definition of done),
``003.context.md`` (the ``http_status`` ruling and the redaction rule) and the frozen
interface recorded under ``## Skeleton`` → ``Step 003`` in ``status.md``. Covers DoD-1 ..
DoD-5 of ``003.errors-and-secrets.md``.
"""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.errors import DomainError, SecretRefError, register_exception_handlers

# From 003.context.md § "The http_status gap": this step chooses 500 for secret_ref_missing.
EXPECTED_SECRET_REF_CODE = "secret_ref_missing"
EXPECTED_SECRET_REF_STATUS = 500

# The wire shape, verbatim from DoD-2 / the Interface intent.
EXPECTED_ENVELOPE_KEYS = {"error"}
EXPECTED_ERROR_KEYS = {"code", "message", "detail"}


def _is_wire_shape(payload: Any) -> bool:
    """True when ``payload`` is the DoD-2 wire body: one ``error`` key over three keys."""
    if not isinstance(payload, dict):
        return False
    if set(payload) != EXPECTED_ENVELOPE_KEYS:
        return False
    inner = payload["error"]
    return isinstance(inner, dict) and set(inner) == EXPECTED_ERROR_KEYS


# --------------------------------------------------------------------------- DoD-1


def test_base_class_carries_code_http_status_and_detail__DoD1() -> None:
    """DoD-1: the base class declares ``code``, ``http_status`` and ``detail``."""
    annotations = DomainError.__dict__.get("__annotations__", {})
    assert {"code", "http_status", "detail"} <= set(annotations)


def test_subclass_sets_code_and_http_status_as_class_attributes__DoD1() -> None:
    """DoD-1: the concrete subclass sets both as class attributes, readable off the class."""
    assert issubclass(SecretRefError, DomainError)
    assert "code" in vars(SecretRefError)
    assert "http_status" in vars(SecretRefError)
    assert SecretRefError.code == EXPECTED_SECRET_REF_CODE
    assert SecretRefError.http_status == EXPECTED_SECRET_REF_STATUS


def test_instance_reports_its_class_attributes__DoD1() -> None:
    """DoD-1: an instance reports the subclass's ``code`` and ``http_status``."""
    error = SecretRefError()
    assert isinstance(error, Exception)
    assert error.code == EXPECTED_SECRET_REF_CODE
    assert error.http_status == EXPECTED_SECRET_REF_STATUS


def test_detail_is_per_instance_and_defaults_to_empty__DoD1() -> None:
    """DoD-1: ``detail`` is per instance — it defaults to empty and differs between instances."""
    default = SecretRefError()
    assert default.detail == {}

    first = SecretRefError(detail={"variable": "ALPHA_TOKEN"})
    second = SecretRefError(detail={"variable": "BETA_TOKEN"})
    assert first.detail == {"variable": "ALPHA_TOKEN"}
    assert second.detail == {"variable": "BETA_TOKEN"}
    assert default.detail == {}


# --------------------------------------------------------------------------- DoD-2


def test_wire_body_has_exactly_the_envelope_and_three_keys__DoD2() -> None:
    """DoD-2: exactly one top-level ``error`` key over exactly ``code``/``message``/``detail``."""
    body = SecretRefError("the pointer cannot be resolved", {"variable": "ALPHA_TOKEN"}).to_wire()
    assert set(body) == EXPECTED_ENVELOPE_KEYS
    assert set(body["error"]) == EXPECTED_ERROR_KEYS


def test_wire_body_carries_the_errors_own_values__DoD2() -> None:
    """DoD-2: the three keys hold the error's code, the given message and the given detail."""
    body = SecretRefError("the pointer cannot be resolved", {"variable": "ALPHA_TOKEN"}).to_wire()
    assert body["error"]["code"] == EXPECTED_SECRET_REF_CODE
    assert body["error"]["message"] == "the pointer cannot be resolved"
    assert body["error"]["detail"] == {"variable": "ALPHA_TOKEN"}


def test_wire_body_key_set_is_unchanged_without_a_message_or_detail__DoD2() -> None:
    """DoD-2: an error built with neither argument renders the same key sets, detail empty."""
    body = SecretRefError().to_wire()
    assert set(body) == EXPECTED_ENVELOPE_KEYS
    assert set(body["error"]) == EXPECTED_ERROR_KEYS
    assert body["error"]["code"] == EXPECTED_SECRET_REF_CODE
    assert body["error"]["detail"] == {}


# --------------------------------------------------------------------------- DoD-3


def _app_raising(exc: BaseException) -> FastAPI:
    """A throwaway application with the handlers registered and one route that raises ``exc``."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom() -> dict[str, str]:
        raise exc

    return app


def test_domain_error_from_a_route_becomes_its_subclasss_http_status__DoD3() -> None:
    """DoD-3: the response status is the raised subclass's ``http_status``."""
    app = _app_raising(SecretRefError("the pointer cannot be resolved", {"variable": "ALPHA_TOKEN"}))
    response = TestClient(app).get("/boom")
    assert response.status_code == EXPECTED_SECRET_REF_STATUS
    assert response.status_code == SecretRefError.http_status


def test_domain_error_from_a_route_becomes_the_dod2_wire_body__DoD3() -> None:
    """DoD-3: the response body is exactly the DoD-2 wire body for that error."""
    app = _app_raising(SecretRefError("the pointer cannot be resolved", {"variable": "ALPHA_TOKEN"}))
    payload = TestClient(app).get("/boom").json()
    assert _is_wire_shape(payload)
    assert payload == {
        "error": {
            "code": EXPECTED_SECRET_REF_CODE,
            "message": "the pointer cannot be resolved",
            "detail": {"variable": "ALPHA_TOKEN"},
        }
    }


# --------------------------------------------------------------------------- DoD-4


def test_ordinary_exception_is_not_converted_into_the_wire_shape__DoD4() -> None:
    """DoD-4: a non-domain exception raised in a route does not come back as the wire body."""
    app = _app_raising(RuntimeError("an ordinary failure"))
    # ``raise_server_exceptions=False`` makes the unhandled case observable as a response
    # instead of a propagated exception; either outcome satisfies "not converted", and the
    # clause is about the shape, not the status.
    response = TestClient(app, raise_server_exceptions=False).get("/boom")
    try:
        payload = response.json()
    except ValueError:
        payload = None
    assert not _is_wire_shape(payload)


def test_ordinary_exception_still_is_not_the_wire_shape_when_it_propagates__DoD4() -> None:
    """DoD-4: with propagation enabled the ordinary exception escapes rather than being converted."""
    app = _app_raising(RuntimeError("an ordinary failure"))
    client = TestClient(app)
    try:
        response = client.get("/boom")
    except RuntimeError:
        return  # propagated: never turned into a domain-error response at all
    try:
        payload = response.json()
    except ValueError:
        payload = None
    assert not _is_wire_shape(payload)


# --------------------------------------------------------------------------- DoD-5


def test_secret_pointer_error_code_is_secret_ref_missing__DoD5() -> None:
    """DoD-5: the secret-pointer error's code is exactly ``secret_ref_missing``."""
    assert SecretRefError.code == "secret_ref_missing"
    assert SecretRefError().code == "secret_ref_missing"


@pytest.mark.parametrize("attribute", ["code", "http_status"])
def test_the_base_class_declares_no_value_for_the_subclass_attributes__DoD1(attribute: str) -> None:
    """DoD-1: ``code``/``http_status`` are the subclass's to set — the base declares no value."""
    assert attribute not in vars(DomainError)
