"""The auth request and response models — two models, nothing else.

**Request.** `LoginRequest` carries a username and a plaintext password, both constrained
to be non-empty (`003/context.md` D16, reused by feature `004`). A violating request is
answered by FastAPI's own `422` — a defensive backstop, deliberately **not** a domain
error code. Values are used **exactly as received**: no trimming, no case folding, no
normalization (`context.md` D13). Undeclared fields are ignored.

**Response.** `IdentityResponse` is the caller's id, username and role — the response
model of both `POST /api/auth/login` and `GET /api/me` (`context.md` D10). The id uses
the outbound snowflake alias, so it leaves as a **decimal string**; a bare `int` id field
is the defect. It carries **no token, no expiry and no session field**: the token lives
in the cookie and nowhere else.

This module imports neither `fastapi` nor anything from `app.routers` or `app.services`.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.ids import SnowflakeOut
from app.roles import Role


class LoginRequest(BaseModel):
    """The login request body: exactly `username` and `password`, both non-empty."""

    model_config = ConfigDict(extra="ignore")

    username: Annotated[str, Field(min_length=1)]
    password: Annotated[str, Field(min_length=1)]


class IdentityResponse(BaseModel):
    """The caller's identity: `id` (decimal string on the wire), `username`, `role`."""

    id: SnowflakeOut
    username: str
    role: Role
