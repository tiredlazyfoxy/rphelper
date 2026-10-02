"""The `/api/characters` request and response models — nothing else.

**Responses.** `CharacterResponse` is the one character shape every route in
`routers/characters.py` answers with — list, create, read, update, archive and restore.
Its `id` uses the outbound snowflake alias, so it leaves as a **decimal string**; a bare
`int` id is the defect. It carries **no `user_id`**: ownership is a server-side scope, never
wire data (`context.md` Wire contract, R5). The three timestamps are passed through as the
fixed-width UTC text the row stores (`data-model.md` § Timestamps), so they are `str`, not
`datetime` — nothing here re-formats them. `archived_at` is `None` for a working character.
`CharacterListResponse` wraps the rows under one `characters` field — a route never returns
a bare list.

**Requests.** `CreateCharacterRequest`: a required `name` that is **stripped and then
required non-empty**, and an optional `sheet` defaulting to `""`. `UpdateCharacterRequest`
(`context.md` D7): both fields optional, each defaulting to `None`; the set of fields the
caller actually supplied is `model_fields_set`, and the router forwards a field **iff it is
in `model_fields_set` and its value is not `None`** — so omitted or an explicit `null` both
mean "leave unchanged".

`name`'s rule is `StringConstraints(strip_whitespace=True, min_length=1)`: a bare
`Field(min_length=1)` would accept `"   "` because it does not strip. The stored name is the
stripped value, and a whitespace-only name is refused by FastAPI's own **422** — there is no
domain code for it (`context.md` D8). `sheet` is **never** stripped: markdown whitespace is
significant, and `""` is legal.

Undeclared request fields are ignored. This module imports neither `app.services` nor
`app.routers`.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.models.ids import SnowflakeOut


class CharacterResponse(BaseModel):
    """One character on the wire. Six keys, never `user_id`."""

    id: SnowflakeOut
    name: str
    sheet: str
    archived_at: str | None
    created_at: str
    updated_at: str


class CharacterListResponse(BaseModel):
    """The characters the caller owns, under the single `characters` field."""

    characters: list[CharacterResponse]


class CreateCharacterRequest(BaseModel):
    """The create-character body: a stripped non-empty `name`, an optional verbatim `sheet`."""

    model_config = ConfigDict(extra="ignore")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    sheet: str = ""


class UpdateCharacterRequest(BaseModel):
    """The PATCH body: both fields optional; `model_fields_set` says which were sent."""

    model_config = ConfigDict(extra="ignore")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None = None
    sheet: str | None = None
