"""`/api/auth/login`, `/api/auth/logout` and `/api/me` — authentication's transport layer.

The router owns HTTP and nothing else: no business rule, no SQL, no password handling.
Its only database contact is `app.db.engine.get_connection`; every rule lives in
`app.services.auth`, and the cookie's name and flags live in `app.dependencies`'
`set_session_cookie` / `clear_session_cookie`.

- **`POST /api/auth/login`** — no authorization dependency (it is the route that creates
  the session). Authenticates, opens a session with `Settings.session_ttl_hours`, sets
  the cookie on the injected `Response`, and answers **200** with `IdentityResponse`.
  It must **never answer 401** (`context.md` D2): `InvalidCredentialsError` is a
  `DomainError` rendered as `400` by the one base-class handler — no `try`/`except`, no
  `HTTPException` here.
- **`POST /api/auth/logout`** — no `require_user` (`context.md` D9). Reads the cookie by
  the configured name, revokes **that** session when a token is present, clears the
  cookie, and answers **204** whether or not a live session resolved.
- **`GET /api/me`** — carries `require_user`; returns the `IdentityResponse` built from the
  `CurrentUser` it yields and nothing else. Path fixed by `backend-structure.md`; not
  moved under `/api/auth/`.

The process's snowflake generator is the single instance on `app.state.id_generator`,
obtained through the delivered `get_id_generator` accessor (HTTP plumbing) and passed
into the service as an argument.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import Connection

from app.config import Settings, get_settings
from app.db.engine import get_connection
from app.dependencies import (
    CurrentUser,
    clear_session_cookie,
    require_user,
    set_session_cookie,
)
from app.ids import SnowflakeGenerator
from app.models.auth import IdentityResponse, LoginRequest
from app.routers.bootstrap import get_id_generator
from app.services.auth import authenticate, open_session, revoke_session

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/login", status_code=200)
def login(
    body: LoginRequest,
    response: Response,
    connection: Annotated[Connection, Depends(get_connection)],
    settings: Annotated[Settings, Depends(get_settings)],
    generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)],
) -> IdentityResponse:
    """Sign in: authenticate, open a session, set the cookie, answer 200 with the identity.

    Calls `authenticate(connection, body.username, body.password)`, then
    `open_session(connection, generator, user.id, settings.session_ttl_hours)`, then
    `set_session_cookie(response, opened.token, settings.session_ttl_hours, settings)`.
    Catches nothing.
    """
    user = authenticate(connection, body.username, body.password)
    opened = open_session(connection, generator, user.id, settings.session_ttl_hours)
    set_session_cookie(response, opened.token, settings.session_ttl_hours, settings)
    return IdentityResponse(id=user.id, username=user.username, role=user.role)


@router.post("/auth/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    connection: Annotated[Connection, Depends(get_connection)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Sign out the calling session only; always 204 and always clears the cookie.

    Reads `request.cookies.get(settings.session_cookie_name)`; when non-empty calls
    `revoke_session(connection, token)`; then `clear_session_cookie(response, settings)`.
    """
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        revoke_session(connection, token)
    clear_session_cookie(response, settings)


@router.get("/me")
def me(current_user: Annotated[CurrentUser, Depends(require_user)]) -> IdentityResponse:
    """Return the caller's id, username and role from the `CurrentUser` `require_user` yielded."""
    return IdentityResponse(
        id=current_user.id, username=current_user.username, role=current_user.role
    )
