"""The setups request and response models — nothing else.

**Responses.** `SetupResponse` is the one setup shape every route in `routers/setups.py`
answers with — list, create, read, update, archive and restore (`context.md` Wire contract).
Both `id` **and** `character_id` use the outbound snowflake alias, so each leaves as a
**decimal string**; a bare `int` would put a JS-unsafe number on the wire (`data-model.md`
§ Identifiers). It carries **no `user_id`**: ownership is a server-side scope, never wire
data (R5). The three timestamps are passed through as the fixed-width UTC text the row
stores (`data-model.md` § Timestamps), so they are `str`, not `datetime` — nothing here
re-formats them. `archived_at` is `None` for a working setup. `SetupListResponse` wraps the
rows under one `setups` field — a route never returns a bare list.

**Requests.** `CreateSetupRequest`: a required `name` that is **stripped and then required
non-empty**, and an optional `description` defaulting to `""`. `UpdateSetupRequest`
(`context.md` D5, D8): both fields optional, each defaulting to `None`; the set of fields the
caller actually supplied is `model_fields_set`, and the router forwards a field **iff it is
in `model_fields_set` and its value is not `None`** — so omitted or an explicit `null` both
mean "leave unchanged". Neither request model has a `character_id` field: on create the
parent comes from the path, and a setup can never move (D5).

`SetupName`'s rule is `StringConstraints(strip_whitespace=True, min_length=1)`: a bare
`Field(min_length=1)` would accept `"   "` because it does not strip. The stored name is the
stripped value, and a whitespace-only name is refused by FastAPI's own **422** — there is no
domain code for it (D8). `description` is **never** stripped: markdown whitespace is
significant, and `""` is legal.

Undeclared request fields are ignored. This module imports neither `app.services` nor
`app.routers`.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.models.ids import SnowflakeOut

#: A setup name as the API accepts it: stripped first, then required non-empty (D8). Declared
#: once here because both request models apply the identical rule.
SetupName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SetupResponse(BaseModel):
    """One setup on the wire. Seven keys, never `user_id`."""

    id: SnowflakeOut
    character_id: SnowflakeOut
    name: str
    description: str
    archived_at: str | None
    created_at: str
    updated_at: str


class SetupListResponse(BaseModel):
    """The setups of one character the caller owns, under the single `setups` field."""

    setups: list[SetupResponse]


class CreateSetupRequest(BaseModel):
    """The create-setup body: a stripped non-empty `name`, an optional verbatim `description`."""

    model_config = ConfigDict(extra="ignore")

    name: SetupName
    description: str = ""


class UpdateSetupRequest(BaseModel):
    """The PATCH body: both fields optional; `model_fields_set` says which were sent."""

    model_config = ConfigDict(extra="ignore")

    name: SetupName | None = None
    description: str | None = None
