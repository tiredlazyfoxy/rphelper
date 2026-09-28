"""The `/api/health` response model — and the two permitted-value types it is built on.

`docs/architecture/backend-structure.md` § `/api/health` prints the shape verbatim:

```json
{ "status": "ok" | "unconfigured" | "degraded",
  "configured": true|false,
  "schema": "ok" | "drift" | "missing" }
```

Three consumers make it load-bearing — the container healthcheck, the `bootstrap` and
`admin` entries' not-ready-yet handling, and `configured` as the signal the bootstrap
entry uses to decide whether to offer bootstrap at all — so the wire keys are exactly
those three names and nothing more.

**The `schema` naming gotcha.** `schema` is a member name on pydantic's `BaseModel`
(the deprecated v1 `Model.schema()` classmethod), so a field literally named `schema`
raises `NameError: Field name "schema" shadows an attribute in parent "BaseModel"` at
class-definition time. The field is therefore declared as `schema_` with an alias of
`"schema"`, and `serialize_by_alias=True` puts the alias on the wire unconditionally —
not only through FastAPI's `response_model_by_alias` default, so a direct
`model_dump()` emits `schema` too. `populate_by_name=True` means both
`HealthResponse(schema_=...)` and `HealthResponse(schema=...)` construct it.

`"drift"` is a permitted value that nothing in this feature produces; feature `007`'s
drift check fills it in. It is declared here anyway, because the wire contract is the
architecture's and not this feature's to narrow.

This module imports neither `fastapi` nor anything from `app.routers` or
`app.services`: `models/` is imported by both and imports neither.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: The roll-up. `"degraded"` when `schema` is not `"ok"`; otherwise `"unconfigured"`
#: while `configured` is false; otherwise `"ok"`.
HealthStatus = Literal["ok", "unconfigured", "degraded"]

#: The coarse schema roll-up. The detailed per-table report is admin-only and belongs
#: to feature `007`.
SchemaState = Literal["ok", "drift", "missing"]


class HealthResponse(BaseModel):
    """The `GET /api/health` body: exactly `status`, `configured` and `schema`."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    status: HealthStatus
    configured: bool
    schema_: SchemaState = Field(alias="schema")
