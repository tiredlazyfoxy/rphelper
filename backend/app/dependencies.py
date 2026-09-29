"""The HTTP-side authentication seam — who is calling, and the one cookie that says so.

A top-level leaf beside `config.py`, `errors.py` and `roles.py` (feature `004`, D8). It
imports `fastapi`; nothing under `db/` or `services/` imports it. It holds five things:

- `CurrentUser` — the immutable identity a guarded route receives (id, username, role).
- `require_user` — reads the session cookie **by the name in
  `Settings.session_cookie_name`** off the request (not `Cookie(...)`, whose name is fixed
  at import time), resolves it through `app.services.auth.resolve_session`, and returns a
  `CurrentUser`. A missing, empty or unresolvable cookie raises `NotAuthenticatedError`.
- `require_role(min_role)` — a dependency **factory**: the callable it returns resolves the
  caller through `require_user` (one definition of "who is calling"), then compares via
  `app.roles.role_at_least`, raising `InsufficientRoleError` below the rung. No session is
  401, never 403.
- `set_session_cookie` / `clear_session_cookie` — the only place the cookie's name and
  flags are spelled (D6): configured name, `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure`
  **off** (HTTP only; mandatory once TLS exists), `Max-Age` = the TTL in seconds. The
  clearer uses the same name and path.

No SQL, no route path, no status-code literal and no business rule appear here.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy import Connection

from app.config import Settings, get_settings
from app.db.engine import get_connection
from app.errors import InsufficientRoleError, NotAuthenticatedError
from app.roles import Role, role_at_least
from app.services.auth import resolve_session


@dataclass(frozen=True)
class CurrentUser:
    """The authenticated caller: id, username and role (role read live from `users`)."""

    id: int
    username: str
    role: Role


def require_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> CurrentUser:
    """Resolve the session cookie to a live caller, or raise `NotAuthenticatedError`."""
    token = request.cookies.get(settings.session_cookie_name)
    resolved = resolve_session(connection, token) if token else None
    if resolved is None:
        raise NotAuthenticatedError()
    return CurrentUser(id=resolved.id, username=resolved.username, role=resolved.role)


def require_role(min_role: Role) -> Callable[..., CurrentUser]:
    """Return a dependency admitting only callers at least `min_role` on the ladder."""

    def dependency(current_user: Annotated[CurrentUser, Depends(require_user)]) -> CurrentUser:
        if not role_at_least(current_user.role, min_role):
            raise InsufficientRoleError()
        return current_user

    return dependency


def set_session_cookie(response: Response, token: str, ttl_hours: int, settings: Settings) -> None:
    """Set the session cookie carrying `token`, with `Max-Age` of `ttl_hours` in seconds."""
    # `Secure` is deliberately off: the deployment is HTTP only, and a `Secure` cookie on an
    # HTTP origin is never sent back. It becomes mandatory once TLS exists (D6).
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=ttl_hours * 3600,
        path="/",
        secure=False,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    """Clear the session cookie under the same name and path it was set with."""
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=False,
        httponly=True,
        samesite="lax",
    )
