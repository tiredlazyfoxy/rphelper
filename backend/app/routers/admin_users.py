"""`/api/admin/users` — account management's transport layer, guarded at the router level.

The router owns HTTP and nothing else: no business rule, no SQL, no password handling,
no transaction. Its only database contact is `app.db.engine.get_connection`; every rule
lives in `app.services.users`.

**`require_role(Role.ADMIN)` is attached to the router, never to a handler**
(`backend-structure.md`, "Authorization as router dependencies"), so a route added later
cannot forget the guard. The single guard callable is held as the module-level
`require_admin`; set-role receives the `CurrentUser` that same guard yields by naming
`require_admin` as a parameter dependency — FastAPI's per-request dependency cache
resolves it once, so this is the router's guard handing over its value, not a second
authorization check.

Six routes (`context.md` D5): `GET ""` and `POST ""` on the collection, and
`POST /{user_id}/disable|enable|password|role`. Create answers **201**, the rest **200**.
`{user_id}` is declared with the inbound snowflake alias (`context.md` D9). No route
translates a domain error by hand; no query parameter exists anywhere on this router.

The process's snowflake generator is the single instance on `app.state.id_generator`,
obtained through the delivered `get_id_generator` accessor and passed into the service.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Connection

from app.db.engine import get_connection
from app.dependencies import CurrentUser, require_role
from app.ids import SnowflakeGenerator
from app.models.admin_users import (
    AdminUserListResponse,
    AdminUserResponse,
    CreateUserRequest,
    SetPasswordRequest,
    SetRoleRequest,
)
from app.models.ids import SnowflakeIn
from app.roles import Role
from app.routers.bootstrap import get_id_generator
from app.services.users import (
    create_user,
    disable_user,
    enable_user,
    list_users,
    set_user_password,
    set_user_role,
)

#: The router's one guard. Shared so set-role can receive the `CurrentUser` it yields.
require_admin = require_role(Role.ADMIN)

router = APIRouter(
    prefix="/api/admin/users",
    tags=["admin-users"],
    dependencies=[Depends(require_admin)],
)


@router.get("", status_code=200)
def list_accounts(
    connection: Annotated[Connection, Depends(get_connection)],
) -> AdminUserListResponse:
    """Every account, via `services.users.list_users(connection)`."""
    accounts = list_users(connection)
    return AdminUserListResponse(
        users=[AdminUserResponse.model_validate(a, from_attributes=True) for a in accounts]
    )


@router.post("", status_code=201)
def create_account(
    body: CreateUserRequest,
    connection: Annotated[Connection, Depends(get_connection)],
    generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)],
) -> AdminUserResponse:
    """Create an enabled account via `create_user(connection, generator, username, password, role)`."""
    account = create_user(connection, generator, body.username, body.password, body.role)
    return AdminUserResponse.model_validate(account, from_attributes=True)


@router.post("/{user_id}/disable", status_code=200)
def disable_account(
    user_id: SnowflakeIn,
    connection: Annotated[Connection, Depends(get_connection)],
) -> AdminUserResponse:
    """Disable the account and end its sessions via `disable_user(connection, user_id)`."""
    account = disable_user(connection, user_id)
    return AdminUserResponse.model_validate(account, from_attributes=True)


@router.post("/{user_id}/enable", status_code=200)
def enable_account(
    user_id: SnowflakeIn,
    connection: Annotated[Connection, Depends(get_connection)],
) -> AdminUserResponse:
    """Re-enable the account via `enable_user(connection, user_id)`."""
    account = enable_user(connection, user_id)
    return AdminUserResponse.model_validate(account, from_attributes=True)


@router.post("/{user_id}/password", status_code=200)
def set_account_password(
    user_id: SnowflakeIn,
    body: SetPasswordRequest,
    connection: Annotated[Connection, Depends(get_connection)],
) -> AdminUserResponse:
    """Set a new password via `set_user_password(connection, user_id, body.password)`."""
    account = set_user_password(connection, user_id, body.password)
    return AdminUserResponse.model_validate(account, from_attributes=True)


@router.post("/{user_id}/role", status_code=200)
def set_account_role(
    user_id: SnowflakeIn,
    body: SetRoleRequest,
    connection: Annotated[Connection, Depends(get_connection)],
    current_user: Annotated[CurrentUser, Depends(require_admin)],
) -> AdminUserResponse:
    """Set the role via `set_user_role(connection, user_id, body.role, current_user.id)`."""
    account = set_user_role(connection, user_id, body.role, current_user.id)
    return AdminUserResponse.model_validate(account, from_attributes=True)
