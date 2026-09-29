"""`/api/bootstrap` — first-run bootstrap's transport layer, guarded at the router level.

The router owns HTTP and nothing else: no business rule, no SQL. Its only database
contact is `app.db.engine.get_connection`; every rule lives in `app.services.bootstrap`.

**`require_unconfigured` is attached to the router, not to a handler**
(`backend-structure.md` § the auth dependencies: "The check is a dependency rather than a
check inside each handler so that adding a bootstrap route cannot forget it."). A later
bootstrap route — `fast/003.bootstrap-from-export`'s `POST /api/bootstrap/import` —
inherits the guard by being declared on this router. That import route is **deliberately
absent** today; exactly one route exists.

The router translates no error by hand: `AlreadyConfiguredError` is a `DomainError`, and
the one base-class handler registered by `app.errors.register_exception_handlers`
renders it with its own `409`. No `try`/`except`, no `HTTPException`.

`POST /create` answers **201**, sets **no cookie** and adds **no `Location` header**.

The process's snowflake generator is the single instance the app factory holds on
`app.state.id_generator`; `get_id_generator` reads it off the request's application
state (HTTP plumbing) and the handler passes it into the service as an argument.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import Connection

from app.db.engine import get_connection
from app.errors import AlreadyConfiguredError
from app.ids import SnowflakeGenerator
from app.models.bootstrap import BootstrapCreateRequest, BootstrapCreateResponse
from app.services.bootstrap import create_first_administrator, is_configured


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
    connection: Annotated[Connection, Depends(get_connection)],
    generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)],
) -> BootstrapCreateResponse:
    """Create the first administrator and answer 201 with its id, username and role.

    Calls `app.services.bootstrap.create_first_administrator(connection, generator,
    body.username, body.password)` and maps the `BootstrapResult` onto the response
    model. Sets no cookie, adds no `Location` header, catches nothing.
    """
    result = create_first_administrator(connection, generator, body.username, body.password)
    return BootstrapCreateResponse(id=result.id, username=result.username, role=result.role)
