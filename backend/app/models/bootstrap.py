"""The `POST /api/bootstrap/create` request and response models — two models, nothing else.

**Request.** A username and a plaintext password, both constrained to be non-empty
(`context.md` D16). A violating request is answered by FastAPI's own `422`, which is a
defensive backstop and deliberately **not** a domain error code. The model carries **no
role and no id field**: the first-run account is always the administrator (UC-001) with a
server-minted id. Undeclared fields are **ignored** (`extra="ignore"`), so a body naming a
`role` or an `id` is accepted and those keys are dropped before the handler ever sees
them — they can never influence the created account.

**Response.** The new administrator's id, username and role. The id uses the outbound
snowflake alias, so it leaves as a **decimal string** — a bare `int` id field is the
defect. It carries **no token and no session field** (`context.md` D9).

This module imports neither `fastapi` nor anything from `app.routers` or `app.services`.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.ids import SnowflakeOut
from app.roles import Role


class BootstrapCreateRequest(BaseModel):
    """The create-first-administrator request body: exactly `username` and `password`."""

    model_config = ConfigDict(extra="ignore")

    username: Annotated[str, Field(min_length=1)]
    password: Annotated[str, Field(min_length=1)]


class BootstrapCreateResponse(BaseModel):
    """The created administrator: `id` (decimal string on the wire), `username`, `role`."""

    id: SnowflakeOut
    username: str
    role: Role
