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


class InvalidCredentialsError(DomainError):
    """A login was refused: unknown username, wrong password, or disabled account.

    Raised **identically** for all three causes (feature `004`, D1): one code, one status,
    one fixed message that names no cause, and a `detail` that carries nothing. The status
    is 400, never 401, so the SPA's 401 hand-off to `/login` is not triggered on the login
    screen itself (feature `004`, D2).
    """

    code = "invalid_credentials"
    http_status = 400

    def __init__(self, message: str | None = None, detail: Mapping[str, Any] | None = None) -> None:
        # Raised with no arguments by `app.services.auth.authenticate`, so the subclass
        # supplies its one fixed, cause-free default message (D1). An explicit message wins.
        if message is None:
            message = "The username or password is incorrect."
        super().__init__(message, detail)



class NotAuthenticatedError(DomainError):
    """The request carries no session cookie, or one that does not resolve to a live session.

    Raised by `app.dependencies.require_user` for every such case alike (feature `004`,
    D3, D7). `detail` carries nothing. The status is 401 — the client's cue to return to
    the login screen (US-007.AC-2).
    """

    code = "not_authenticated"
    http_status = 401

    def __init__(self, message: str | None = None, detail: Mapping[str, Any] | None = None) -> None:
        # Raised with no arguments by `require_user`, so the subclass supplies its one fixed
        # default message; an explicit message still wins.
        if message is None:
            message = "You are not signed in, or your session has ended."
        super().__init__(message, detail)


class InsufficientRoleError(DomainError):
    """An authenticated, enabled caller's role is below the rung a route requires.

    Raised by the callable `app.dependencies.require_role` returns (feature `004`, D3).
    `detail` carries nothing and the message names neither the caller's role nor the
    required one: a refusal that reports the policy teaches it. The status is 403.
    """

    code = "insufficient_role"
    http_status = 403

    def __init__(self, message: str | None = None, detail: Mapping[str, Any] | None = None) -> None:
        # Raised with no arguments; the fixed default names no role, neither the caller's
        # nor the required one (D3). An explicit message still wins.
        if message is None:
            message = "You do not have permission to perform this action."
        super().__init__(message, detail)


class UsernameTakenError(DomainError):
    """An account create was refused because the username already belongs to an account.

    Raised by `app.services.users.create_user` when the `users.username` unique index
    rejects the insert (feature `005`). `detail` carries nothing: echoing the caller's own
    input buys nothing, and naming the owning account would be a disclosure. The status is
    409 — the request is well formed and refused by the instance's current state.
    """

    code = "username_taken"
    http_status = 409

    def __init__(self, message: str | None = None, detail: Mapping[str, Any] | None = None) -> None:
        # Raised with no arguments; the fixed default names no username. An explicit
        # message still wins.
        if message is None:
            message = "That username is already taken."
        super().__init__(message, detail)


class UserNotFoundError(DomainError):
    """An id-addressed account operation named an id no account has.

    Raised by `app.services.users` before any write (feature `005`). `detail` carries
    nothing. The status is 404.
    """

    code = "user_not_found"
    http_status = 404

    def __init__(self, message: str | None = None, detail: Mapping[str, Any] | None = None) -> None:
        # Raised with no arguments; an explicit message still wins.
        if message is None:
            message = "That account does not exist."
        super().__init__(message, detail)


class SelfRoleChangeRefusedError(DomainError):
    """A role change whose target is the acting administrator.

    Raised by `app.services.users.set_user_role` before any write (feature `005`), so an
    instance cannot lose its last administrator through one mis-click. `detail` carries
    nothing. The status is 409, distinct from `insufficient_role`'s 403.
    """

    code = "self_role_change_refused"
    http_status = 409

    def __init__(self, message: str | None = None, detail: Mapping[str, Any] | None = None) -> None:
        # Raised with no arguments; an explicit message still wins.
        if message is None:
            message = "You cannot change your own role."
        super().__init__(message, detail)



class LlmUnreachableError(DomainError):
    """An outbound call to a registered LLM server failed upstream of this instance.

    Feature `006` (`context.md` D7): a transport failure, a timeout or a non-2xx answer.
    502, because the fault is upstream, not in the caller's request. Callers supply
    `detail`; nothing is hard-coded into it.
    """

    code = "llm_unreachable"
    http_status = 502


class NoEmbeddingModelError(DomainError):
    """An operation needs the designated embedding model and none is designated.

    Feature `006` (`context.md` D7): a configuration conflict, hence 409.
    """

    code = "no_embedding_model"
    http_status = 409


class ModelNotEnabledError(DomainError):
    """A model reference names a model that is not enabled at the level asked for.

    Feature `006` (`context.md` D7): a configuration conflict, hence 409. `detail` is
    free to carry the model name and the level; the handler never logs it.
    """

    code = "model_not_enabled"
    http_status = 409


class LlmServerNotFoundError(DomainError):
    """An id-addressed LLM-server operation names no existing registration.

    Feature `006` (`context.md` D7): the sibling of `user_not_found`, 404.
    """

    code = "llm_server_not_found"
    http_status = 404


class UnknownTableError(DomainError):
    """A schema apply named a table the registry does not declare.

    Feature `007` (`context.md` D9): raised by `app.db.sync` before any DDL, including for
    a name that exists in the live database but not in the registry. `detail` carries the
    name under `"table_name"`. 404.
    """

    code = "unknown_table"
    http_status = 404


class SchemaApplyFailedError(DomainError):
    """A Create or a Sync could not be applied and was rolled back.

    Feature `007` (`context.md` D9): a driver error, a failed cast, or a
    `foreign_key_check` violation. `detail` carries `"table_name"` and `"operation"`
    (`"create"` or `"sync"`) and never the driver's message. 500.
    """

    code = "schema_apply_failed"
    http_status = 500


class CharacterNotFoundError(DomainError):
    """An id-addressed character operation names no character the caller owns.

    Raised by `app.services.characters` (feature `009`, `context.md` D8) for both "no such
    id" and "another user's id" — the two are indistinguishable on the wire, which is R5's
    no-existence-leak posture. `detail` carries nothing. The status is 404.
    """

    code = "character_not_found"
    http_status = 404

    def __init__(self, message: str | None = None, detail: Mapping[str, Any] | None = None) -> None:
        # Raised with no arguments; an explicit message still wins.
        if message is None:
            message = "That character does not exist."
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
