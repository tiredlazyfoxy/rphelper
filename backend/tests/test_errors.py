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

from app.errors import (
    AlreadyConfiguredError,
    DomainError,
    InsufficientRoleError,
    InvalidCredentialsError,
    NotAuthenticatedError,
    SecretRefError,
    SelfRoleChangeRefusedError,
    UsernameTakenError,
    UserNotFoundError,
    register_exception_handlers,
)

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


# ============================================================================
# Feature 003, step 002 (``002.bootstrap-service-and-error.md``) — DoD-1:
# ``already_configured`` is a ``DomainError`` subclass, code ``already_configured``,
# HTTP 409 (feature context D2), empty detail, rendered through the one existing handler.
# ============================================================================

EXPECTED_ALREADY_CONFIGURED_CODE = "already_configured"
EXPECTED_ALREADY_CONFIGURED_STATUS = 409


def test_already_configured_is_a_domain_error_subclass__S002_DoD1() -> None:
    """003/002 DoD-1: the new error follows the base's pattern as a subclass."""
    assert issubclass(AlreadyConfiguredError, DomainError)
    assert isinstance(AlreadyConfiguredError(), Exception)


def test_already_configured_sets_code_and_status_as_class_attributes__S002_DoD1() -> None:
    """003/002 DoD-1: code ``already_configured`` and status 409, set on the subclass itself."""
    assert "code" in vars(AlreadyConfiguredError)
    assert "http_status" in vars(AlreadyConfiguredError)
    assert AlreadyConfiguredError.code == EXPECTED_ALREADY_CONFIGURED_CODE
    assert AlreadyConfiguredError.http_status == EXPECTED_ALREADY_CONFIGURED_STATUS
    error = AlreadyConfiguredError()
    assert error.code == EXPECTED_ALREADY_CONFIGURED_CODE
    assert error.http_status == EXPECTED_ALREADY_CONFIGURED_STATUS


def test_already_configured_detail_is_empty__S002_DoD1() -> None:
    """003/002 DoD-1: ``detail`` carries nothing."""
    assert AlreadyConfiguredError().detail == {}


def test_already_configured_renders_the_one_wire_shape__S002_DoD1() -> None:
    """003/002 DoD-1: the inherited render produces the one wire shape with an empty detail."""
    body = AlreadyConfiguredError().to_wire()
    assert _is_wire_shape(body)
    assert body["error"]["code"] == EXPECTED_ALREADY_CONFIGURED_CODE
    assert body["error"]["detail"] == {}


def test_already_configured_from_a_route_is_409_in_the_wire_shape__S002_DoD1() -> None:
    """003/002 DoD-1: through the handler 001 already registers, the response is 409 + wire body."""
    app = _app_raising(AlreadyConfiguredError())
    response = TestClient(app).get("/boom")
    assert response.status_code == EXPECTED_ALREADY_CONFIGURED_STATUS
    payload = response.json()
    assert _is_wire_shape(payload)
    assert payload["error"]["code"] == EXPECTED_ALREADY_CONFIGURED_CODE
    assert payload["error"]["detail"] == {}


def test_no_second_handler_is_registered_for_already_configured__S002_DoD1() -> None:
    """003/002 DoD-1: the base-class handler covers the subclass; no handler keyed on it is added."""
    app = FastAPI()
    register_exception_handlers(app)
    assert DomainError in app.exception_handlers
    assert AlreadyConfiguredError not in app.exception_handlers


# 003/002 DoD-1 (extended): raised with no arguments, the error carries a non-empty,
# human-readable message — never null. The wording is not a contract; only "a non-empty
# string" is asserted.


def _is_non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def test_already_configured_without_arguments_has_a_non_empty_message__S002_DoD1() -> None:
    """003/002 DoD-1: ``AlreadyConfiguredError()`` carries a non-empty string ``message`` on the instance."""
    error = AlreadyConfiguredError()
    assert error.message is not None
    assert _is_non_empty_text(error.message)


def test_already_configured_without_arguments_renders_a_non_empty_message__S002_DoD1() -> None:
    """003/002 DoD-1: the rendered body's ``error.message`` is a non-empty string, not null."""
    body = AlreadyConfiguredError().to_wire()
    assert _is_wire_shape(body)
    assert body["error"]["message"] is not None
    assert _is_non_empty_text(body["error"]["message"])


def test_already_configured_from_a_route_carries_a_non_empty_message__S002_DoD1() -> None:
    """003/002 DoD-1: through the registered handler, the 409 body's ``message`` is a non-empty string."""
    app = _app_raising(AlreadyConfiguredError())
    response = TestClient(app).get("/boom")
    assert response.status_code == EXPECTED_ALREADY_CONFIGURED_STATUS
    payload = response.json()
    assert _is_wire_shape(payload)
    assert payload["error"]["message"] is not None
    assert _is_non_empty_text(payload["error"]["message"])


# ============================================================================
# Feature 004, step 001 (``001.auth-sessions-and-service.md``) — DoD-3:
# ``invalid_credentials`` is a ``DomainError`` subclass, code ``invalid_credentials``,
# HTTP 400 (feature context D2), empty detail, one fixed cause-free message, rendered in
# the one wire shape through the handler 001 already registers — no second handler.
# ============================================================================

EXPECTED_INVALID_CREDENTIALS_CODE = "invalid_credentials"
EXPECTED_INVALID_CREDENTIALS_STATUS = 400


def test_invalid_credentials_is_a_domain_error_subclass__S004_001_DoD3() -> None:
    """004/001 DoD-3: the refusal follows the base's pattern as a subclass."""
    assert issubclass(InvalidCredentialsError, DomainError)
    assert isinstance(InvalidCredentialsError(), Exception)


def test_invalid_credentials_sets_code_and_status_as_class_attributes__S004_001_DoD3() -> None:
    """004/001 DoD-3: code ``invalid_credentials`` and status 400, set on the subclass itself."""
    assert "code" in vars(InvalidCredentialsError)
    assert "http_status" in vars(InvalidCredentialsError)
    assert InvalidCredentialsError.code == EXPECTED_INVALID_CREDENTIALS_CODE
    assert InvalidCredentialsError.http_status == EXPECTED_INVALID_CREDENTIALS_STATUS
    error = InvalidCredentialsError()
    assert error.code == EXPECTED_INVALID_CREDENTIALS_CODE
    assert error.http_status == EXPECTED_INVALID_CREDENTIALS_STATUS


def test_invalid_credentials_detail_is_empty__S004_001_DoD3() -> None:
    """004/001 DoD-3: ``detail`` carries nothing."""
    assert InvalidCredentialsError().detail == {}


def test_invalid_credentials_has_one_fixed_non_empty_message__S004_001_DoD3() -> None:
    """004/001 DoD-3: raised with no arguments it carries a non-empty message, the same every time."""
    first = InvalidCredentialsError()
    second = InvalidCredentialsError()
    assert _is_non_empty_text(first.message)
    assert first.message == second.message


def test_invalid_credentials_renders_the_one_wire_shape__S004_001_DoD3() -> None:
    """004/001 DoD-3: the inherited render produces ``{"error": {code, message, detail}}``."""
    body = InvalidCredentialsError().to_wire()
    assert _is_wire_shape(body)
    assert body["error"]["code"] == EXPECTED_INVALID_CREDENTIALS_CODE
    assert _is_non_empty_text(body["error"]["message"])
    assert body["error"]["detail"] == {}


def test_invalid_credentials_from_a_route_is_400_in_the_wire_shape__S004_001_DoD3() -> None:
    """004/001 DoD-3: through the handler 001 registers, the response is 400 + the wire body."""
    app = _app_raising(InvalidCredentialsError())
    response = TestClient(app).get("/boom")
    assert response.status_code == EXPECTED_INVALID_CREDENTIALS_STATUS
    payload = response.json()
    assert _is_wire_shape(payload)
    assert payload["error"]["code"] == EXPECTED_INVALID_CREDENTIALS_CODE
    assert payload["error"]["message"] == InvalidCredentialsError().message
    assert payload["error"]["detail"] == {}


def test_no_second_handler_is_registered_for_invalid_credentials__S004_001_DoD3() -> None:
    """004/001 DoD-3: the base-class handler covers the subclass; no handler keyed on it is added."""
    app = FastAPI()
    register_exception_handlers(app)
    assert DomainError in app.exception_handlers
    assert InvalidCredentialsError not in app.exception_handlers


# ============================================================================
# Feature 004, step 002 (``002.ladder-and-dependencies.md``) — DoD-4:
# ``not_authenticated`` (401) and ``insufficient_role`` (403) are ``DomainError``
# subclasses with an empty detail, rendered in the one wire shape through the handler 001
# already registers — no second handler (feature context D3).
# ============================================================================

AUTH_GUARD_ERRORS: list[tuple[type[DomainError], str, int]] = [
    (NotAuthenticatedError, "not_authenticated", 401),
    (InsufficientRoleError, "insufficient_role", 403),
]


@pytest.mark.parametrize(("error_class", "code", "status"), AUTH_GUARD_ERRORS)
def test_guard_error_is_a_domain_error_subclass__S004_002_DoD4(
    error_class: type[DomainError], code: str, status: int
) -> None:
    """004/002 DoD-4: each guard error follows the base's pattern as a subclass."""
    assert issubclass(error_class, DomainError)
    assert isinstance(error_class(), Exception)


@pytest.mark.parametrize(("error_class", "code", "status"), AUTH_GUARD_ERRORS)
def test_guard_error_sets_code_and_status_as_class_attributes__S004_002_DoD4(
    error_class: type[DomainError], code: str, status: int
) -> None:
    """004/002 DoD-4: ``not_authenticated``/401 and ``insufficient_role``/403, set on the subclass itself."""
    assert "code" in vars(error_class)
    assert "http_status" in vars(error_class)
    assert error_class.code == code
    assert error_class.http_status == status
    error = error_class()
    assert error.code == code
    assert error.http_status == status


@pytest.mark.parametrize(("error_class", "code", "status"), AUTH_GUARD_ERRORS)
def test_guard_error_detail_is_empty__S004_002_DoD4(error_class: type[DomainError], code: str, status: int) -> None:
    """004/002 DoD-4: ``detail`` carries nothing."""
    assert error_class().detail == {}


@pytest.mark.parametrize(("error_class", "code", "status"), AUTH_GUARD_ERRORS)
def test_guard_error_renders_the_one_wire_shape__S004_002_DoD4(
    error_class: type[DomainError], code: str, status: int
) -> None:
    """004/002 DoD-4: the inherited render produces ``{"error": {code, message, detail}}``, detail empty."""
    body = error_class().to_wire()
    assert _is_wire_shape(body)
    assert body["error"]["code"] == code
    assert body["error"]["detail"] == {}


@pytest.mark.parametrize(("error_class", "code", "status"), AUTH_GUARD_ERRORS)
def test_guard_error_from_a_route_answers_its_status_in_the_wire_shape__S004_002_DoD4(
    error_class: type[DomainError], code: str, status: int
) -> None:
    """004/002 DoD-4: through the handler 001 registers, the response is 401/403 + the wire body."""
    app = _app_raising(error_class())
    response = TestClient(app).get("/boom")
    assert response.status_code == status
    payload = response.json()
    assert _is_wire_shape(payload)
    assert payload["error"]["code"] == code
    assert payload["error"]["detail"] == {}
    assert payload == error_class().to_wire()


def test_no_second_handler_is_registered_for_the_guard_errors__S004_002_DoD4() -> None:
    """004/002 DoD-4: the base-class handler covers both subclasses; no handler keyed on either is added."""
    app = FastAPI()
    register_exception_handlers(app)
    assert DomainError in app.exception_handlers
    assert NotAuthenticatedError not in app.exception_handlers
    assert InsufficientRoleError not in app.exception_handlers


def test_insufficient_role_renders_no_role_name__S004_002_DoD4() -> None:
    """004/002 DoD-4 (with DoD-10): the refusal names neither the caller's role nor the required one."""
    rendered = str(InsufficientRoleError().to_wire()).lower()
    for role_name in ("roleplayer", "admin"):
        assert role_name not in rendered


# ============================================================================
# Feature 005, step 002 (``002.users-service-and-errors.md``) — DoD-1:
# ``username_taken``/409, ``user_not_found``/404 and ``self_role_change_refused``/409 are
# ``DomainError`` subclasses with an empty detail, rendered in the one wire shape through
# the handler 001 already registers — no second handler.
# ============================================================================

ACCOUNT_ERRORS: list[tuple[type[DomainError], str, int]] = [
    (UsernameTakenError, "username_taken", 409),
    (UserNotFoundError, "user_not_found", 404),
    (SelfRoleChangeRefusedError, "self_role_change_refused", 409),
]


@pytest.mark.parametrize(("error_class", "code", "status"), ACCOUNT_ERRORS)
def test_account_error_is_a_domain_error_subclass__S005_002_DoD1(
    error_class: type[DomainError], code: str, status: int
) -> None:
    """005/002 DoD-1: each account error follows the base's pattern as a subclass."""
    assert issubclass(error_class, DomainError)
    assert isinstance(error_class(), Exception)


@pytest.mark.parametrize(("error_class", "code", "status"), ACCOUNT_ERRORS)
def test_account_error_sets_code_and_status_as_class_attributes__S005_002_DoD1(
    error_class: type[DomainError], code: str, status: int
) -> None:
    """005/002 DoD-1: the code and HTTP status are set on the subclass itself."""
    assert "code" in vars(error_class)
    assert "http_status" in vars(error_class)
    assert error_class.code == code
    assert error_class.http_status == status
    error = error_class()
    assert error.code == code
    assert error.http_status == status


@pytest.mark.parametrize(("error_class", "code", "status"), ACCOUNT_ERRORS)
def test_account_error_detail_is_empty__S005_002_DoD1(error_class: type[DomainError], code: str, status: int) -> None:
    """005/002 DoD-1: ``detail`` carries nothing."""
    assert error_class().detail == {}


@pytest.mark.parametrize(("error_class", "code", "status"), ACCOUNT_ERRORS)
def test_account_error_renders_the_one_wire_shape__S005_002_DoD1(
    error_class: type[DomainError], code: str, status: int
) -> None:
    """005/002 DoD-1: the inherited render produces ``{"error": {code, message, detail}}``, detail empty."""
    body = error_class().to_wire()
    assert _is_wire_shape(body)
    assert body["error"]["code"] == code
    assert body["error"]["detail"] == {}


@pytest.mark.parametrize(("error_class", "code", "status"), ACCOUNT_ERRORS)
def test_account_error_from_a_route_answers_its_status_in_the_wire_shape__S005_002_DoD1(
    error_class: type[DomainError], code: str, status: int
) -> None:
    """005/002 DoD-1: through the handler 001 registers, the response is 409/404/409 + the wire body."""
    app = _app_raising(error_class())
    response = TestClient(app).get("/boom")
    assert response.status_code == status
    payload = response.json()
    assert _is_wire_shape(payload)
    assert payload["error"]["code"] == code
    assert payload["error"]["detail"] == {}
    assert payload == error_class().to_wire()


def test_no_second_handler_is_registered_for_the_account_errors__S005_002_DoD1() -> None:
    """005/002 DoD-1: the base-class handler covers all three; no handler keyed on any is added."""
    app = FastAPI()
    register_exception_handlers(app)
    assert DomainError in app.exception_handlers
    for error_class, _code, _status in ACCOUNT_ERRORS:
        assert error_class not in app.exception_handlers


def test_the_three_account_errors_are_distinct_codes__S005_002_DoD1() -> None:
    """005/002 DoD-1: the two 409s stay distinguishable by code, and none reuses an existing code."""
    codes = [error_class.code for error_class, _code, _status in ACCOUNT_ERRORS]
    assert len(set(codes)) == 3
    existing = {
        SecretRefError.code,
        AlreadyConfiguredError.code,
        InvalidCredentialsError.code,
        NotAuthenticatedError.code,
        InsufficientRoleError.code,
    }
    assert not set(codes) & existing
