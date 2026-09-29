"""The `/api/admin/users` request and response models — five models, nothing else.

**Responses.** `AdminUserResponse` is the one account shape every route on the admin
users router answers with: `id`, `username`, `role`, `is_enabled` and `last_login_at`
(nullable; an ISO-8601 string on the wire). The id uses the outbound snowflake alias, so
it leaves as a **decimal string**; a bare `int` id field is the defect. It carries **no
password, no hash, no token, no language default and no count of anything** (R5,
UC-066). `AdminUserListResponse` wraps the accounts under one `users` field — a route
never returns a bare list.

**Requests.** `CreateUserRequest` carries `username`, `password` and `role`;
`SetPasswordRequest` carries one `password` (no current-password field, `context.md`
D6); `SetRoleRequest` carries one `role`. Username and password are constrained
non-empty, answered by FastAPI's own `422` — a defensive backstop, deliberately **not** a
domain error code. Values are used exactly as received: no trimming, no case folding, no
normalization. Undeclared fields are ignored.

This module imports neither `fastapi` nor anything from `app.routers` or `app.services`.
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.ids import SnowflakeOut
from app.roles import Role


class AdminUserResponse(BaseModel):
    """One account: `id` (decimal string), `username`, `role`, `is_enabled`, `last_login_at`."""

    id: SnowflakeOut
    username: str
    role: Role
    is_enabled: bool
    last_login_at: datetime | None


class AdminUserListResponse(BaseModel):
    """Every account, under the single `users` field."""

    users: list[AdminUserResponse]


class CreateUserRequest(BaseModel):
    """The create-account body: non-empty `username` and `password`, and a `role`."""

    model_config = ConfigDict(extra="ignore")

    username: Annotated[str, Field(min_length=1)]
    password: Annotated[str, Field(min_length=1)]
    role: Role


class SetPasswordRequest(BaseModel):
    """The set-password body: one non-empty plaintext `password`, no current password."""

    model_config = ConfigDict(extra="ignore")

    password: Annotated[str, Field(min_length=1)]


class SetRoleRequest(BaseModel):
    """The set-role body: one `role`."""

    model_config = ConfigDict(extra="ignore")

    role: Role
