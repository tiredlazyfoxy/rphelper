"""The typed error hierarchy — one base class, one wire shape, one handler.

`docs/architecture/backend-structure.md` § The error model declares the base class's
shape: a stable machine-readable `code`, an `http_status`, and a structured `detail`
mapping that is never free prose the UI has to parse. Per this feature's decision D7,
`code` and `http_status` are class attributes each concrete subclass sets — the
architecture tables twelve codes but assigns an HTTP status to none of them, so the
status is decided by the feature that introduces the code.

This module defines the base class, the single handler, the handler's registration
entry point, and the concrete subclasses introduced so far: `SecretRefError`
(`secret_ref_missing`) and `AlreadyConfiguredError` (`already_configured`, feature
`003`). The remaining codes arrive with the features that raise them.

The handler logs the `code` and the HTTP status and nothing else — never `detail`,
never the message text (`deployment.md`'s redaction rule).
"""

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger


class DomainError(Exception):
    """Base class for every typed domain failure the SPA is expected to render.

    `code` and `http_status` are class attributes each concrete subclass sets; the
    human-readable message and the structured `detail` are per instance.
    """

    code: str
    http_status: int

    message: str | None
    detail: dict[str, Any]

    def __init__(self, message: str | None = None, detail: Mapping[str, Any] | None = None) -> None:
        if message is None:
            super().__init__()
        else:
            super().__init__(message)
        self.message = message
        self.detail = dict(detail) if detail is not None else {}

    def to_wire(self) -> dict[str, Any]:
        """Render the wire body: exactly `{"error": {"code", "message", "detail"}}`."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "detail": dict(self.detail),
            }
        }


class SecretRefError(DomainError):
    """A `"$ENV_VAR"` reference naming a variable absent from the process environment.

    `detail` carries the variable's name under the key `"variable"`, and never a
    resolved secret value. The status is 500 because the caller cannot fix the failure
    by changing the request — only by changing the deployment's environment.
    """

    code = "secret_ref_missing"
    http_status = 500


class AlreadyConfiguredError(DomainError):
    """A bootstrap operation was attempted on an instance that is already configured.

    `detail` carries nothing. The status is 409: the request conflicts with the
    instance's current state — an administrator already exists (UC-003).
    """

    code = "already_configured"
    http_status = 409

    def __init__(self, message: str | None = None, detail: Mapping[str, Any] | None = None) -> None:
        # Raised with no arguments (the router's guard, the service's re-check), so the
        # subclass supplies its own human-readable default; the base keeps none, so other
        # errors' rendering is unchanged. An explicit message still wins.
        if message is None:
            message = "This instance is already configured: an administrator already exists."
        super().__init__(message, detail)


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """Render a raised `DomainError` as its `http_status` plus `to_wire()`'s body."""
    # Redaction rule: the code and the status, and nothing else. `detail` is where later
    # features put model references, tool names and ids, and the message is free prose.
    logger.warning("domain error code={} status={}", exc.code, exc.http_status)
    return JSONResponse(status_code=exc.http_status, content=exc.to_wire())


def register_exception_handlers(app: FastAPI) -> None:
    """Install `domain_error_handler` for `DomainError`, covering every subclass."""
    # The decorator form rather than `add_exception_handler`: Starlette types the latter's
    # parameter invariantly on `Exception`, so passing `DomainError` fails mypy, and
    # `warn_unused_ignores = true` forbids silencing it with a `type: ignore`.
    app.exception_handler(DomainError)(domain_error_handler)
