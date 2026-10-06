"""`/api/bootstrap` — first-run bootstrap's transport layer, guarded at the router level.

The router owns HTTP and nothing else: no business rule, no SQL. Its only database
contact is `app.db.engine.get_connection`; every rule lives in `app.services.bootstrap`.

**`require_unconfigured` is attached to the router, not to a handler**
(`backend-structure.md` § the auth dependencies: "The check is a dependency rather than a
check inside each handler so that adding a bootstrap route cannot forget it."). A later
bootstrap route inherits the guard by being declared on this router. Two routes exist:
`POST /create` and `fast/003.bootstrap-from-export`'s `POST /import`, which names the guard
nowhere and inherits it from this router.

The router translates no error by hand: `AlreadyConfiguredError` is a `DomainError`, and
the one base-class handler registered by `app.errors.register_exception_handlers`
renders it with its own `409`. No `try`/`except`, no `HTTPException`.

`POST /create` answers **201**, sets the session cookie through
`app.dependencies.set_session_cookie` from the token the service returned, and adds **no
`Location` header**. The token never appears in the response body.

`POST /import` takes the raw JSON object body (`dict[str, Any]`, like the admin database
import), calls `app.services.bootstrap.restore_from_export`, and answers **204** with no body
and **no `Set-Cookie`**: no session exists and the import never restores `auth_sessions`. A
non-object body answers 422 from FastAPI; `export_invalid` (400), `already_configured` and
`database_not_empty` (409) travel through the single `DomainError` handler.

The process's snowflake generator is the single instance the app factory holds on
`app.state.id_generator`; `get_id_generator` reads it off the request's application
state (HTTP plumbing) and the handler passes it into the service as an argument.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import Connection

from app.config import Settings, get_settings
from app.db.engine import get_connection
from app.dependencies import set_session_cookie
from app.errors import AlreadyConfiguredError
from app.ids import SnowflakeGenerator
from app.models.bootstrap import BootstrapCreateRequest, BootstrapCreateResponse
from app.services.bootstrap import create_first_administrator, is_configured, restore_from_export


def require_unconfigured(connection: Annotated[Connection, Depends(get_connection)]) -> None:
    """Refuse every bootstrap route once the instance is configured (UC-003).

    Asks `app.services.bootstrap.is_configured(connection)`; raises
    `app.errors.AlreadyConfiguredError()` when it answers True, returns None otherwise.
    """
    if is_configured(connection):
        raise AlreadyConfiguredError()


def get_id_generator(request: Request) -> SnowflakeGenerator:
    """Return the process's single `SnowflakeGenerator` from `request.app.state.id_generator`."""
    generator: SnowflakeGenerator = request.app.state.id_generator
    return generator


router = APIRouter(
    prefix="/api/bootstrap",
    tags=["bootstrap"],
    dependencies=[Depends(require_unconfigured)],
)


@router.post("/create", status_code=201)
def create_administrator(
    body: BootstrapCreateRequest,
    response: Response,
    connection: Annotated[Connection, Depends(get_connection)],
    settings: Annotated[Settings, Depends(get_settings)],
    generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)],
) -> BootstrapCreateResponse:
    """Create the first administrator, sign them in, and answer 201 with id, username and role.

    Calls `app.services.bootstrap.create_first_administrator(connection, generator,
    body.username, body.password, settings.session_ttl_hours)`, sets the session cookie via
    `set_session_cookie(response, result.token, settings.session_ttl_hours, settings)`, and
    maps the `BootstrapResult` onto the response model (no token in the body). Adds no
    `Location` header, catches nothing.
    """
    result = create_first_administrator(
        connection, generator, body.username, body.password, settings.session_ttl_hours
    )
    set_session_cookie(response, result.token, settings.session_ttl_hours, settings)
    return BootstrapCreateResponse(id=result.id, username=result.username, role=result.role)


@router.post("/import", status_code=204)
def restore_database(
    body: dict[str, Any],
    connection: Annotated[Connection, Depends(get_connection)],
) -> None:
    """Restore the unconfigured instance from a whole-database export and answer 204, no body.

    Calls `app.services.bootstrap.restore_from_export(connection, body)`. Sets no cookie, adds no
    header, catches nothing.
    """
    restore_from_export(connection, body)
