"""The `/api/admin/llm-servers` request and response models — nothing else.

**Responses.** `LlmServerResponse` is the one server shape the list, create, update and
designate routes answer with. Its `id` uses the outbound snowflake alias, so it leaves as a
**decimal string**; a bare `int` id is the defect. It carries the boolean `has_api_key`
and **never the pointer text**, and **no field or count relating to a user, session,
character, setup or memo** (R5, UC-066). `LlmServerListResponse` wraps the servers under
one `servers` field — a route never returns a bare list.

`ConnectionTestResponse` is the typed test outcome (step `002`'s closed four-value
`ProbeOutcome`), the `ok` flag and the instant tested — no free-text field.
`AvailableModelsResponse` / `EnabledModelsResponse` each carry names under one field.

**Requests.** `CreateLlmServerRequest`: non-empty `name` and `base_url`, `kind` as the
two-member `LlmServerKind` literal (`context.md` D5), and an optional `api_key_ref` typed
with step `001`'s `SecretRefIn`. Every refusal is FastAPI's own 422.

`UpdateLlmServerRequest` (`context.md` D9): the same four fields, **all optional**, each
defaulting to `None`. The set of fields the caller actually supplied is
`model_fields_set`. The router forwards a field to the registry's `update_server` **iff it
is in `model_fields_set` and its value is not `None`**; otherwise it passes `UNSET`. So:
omitted (or explicit `null`) = leave unchanged; `api_key_ref: ""` = clear; any other valid
pointer = replace.

`SetEnabledModelsRequest`: the **complete** list of names to enable; `[]` is legal and
means "none". `DesignateEmbeddingModelRequest`: one non-empty `model_name`.

Undeclared request fields are ignored. This module imports neither `fastapi` nor anything
from `app.routers`; it imports `ProbeOutcome` from the LLM client module as a type only.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.ids import SnowflakeOut
from app.models.secret_ref import SecretRefIn
from app.services.llm.client import ProbeOutcome

#: The two provider kinds (`context.md` D5) — a presentation label, never a dispatch key.
LlmServerKind = Literal["llamaswap", "openai"]


class LlmServerResponse(BaseModel):
    """One registration. No pointer text, no user/session/character/setup/memo anything."""

    id: SnowflakeOut
    name: str
    kind: str
    base_url: str
    has_api_key: bool
    enabled_model_names: list[str]
    embedding_model_name: str | None
    embedding_dim: int | None
    last_test_at: datetime | None
    last_test_ok: bool | None
    last_test_error: ProbeOutcome | None
    created_at: datetime
    updated_at: datetime


class LlmServerListResponse(BaseModel):
    """Every registration, under the single `servers` field."""

    servers: list[LlmServerResponse]


class ConnectionTestResponse(BaseModel):
    """The typed test outcome, the ok flag and the instant tested — no free text."""

    outcome: ProbeOutcome
    ok: bool
    tested_at: datetime


class AvailableModelsResponse(BaseModel):
    """The model names the probe returned, in server order, under `model_names`."""

    model_names: list[str]


class EnabledModelsResponse(BaseModel):
    """The enabled model names as stored after the replace, under `enabled_model_names`."""

    enabled_model_names: list[str]


class CreateLlmServerRequest(BaseModel):
    """The register-connection body."""

    model_config = ConfigDict(extra="ignore")

    name: Annotated[str, Field(min_length=1)]
    kind: LlmServerKind
    base_url: Annotated[str, Field(min_length=1)]
    api_key_ref: SecretRefIn | None = None


class UpdateLlmServerRequest(BaseModel):
    """The PATCH body: all four fields optional; `model_fields_set` says which were sent."""

    model_config = ConfigDict(extra="ignore")

    name: Annotated[str, Field(min_length=1)] | None = None
    kind: LlmServerKind | None = None
    base_url: Annotated[str, Field(min_length=1)] | None = None
    api_key_ref: SecretRefIn | None = None


class SetEnabledModelsRequest(BaseModel):
    """The complete set of names to enable; the empty list means "none"."""

    model_config = ConfigDict(extra="ignore")

    model_names: list[str]


class DesignateEmbeddingModelRequest(BaseModel):
    """The one non-empty model name to designate for embeddings."""

    model_config = ConfigDict(extra="ignore")

    model_name: Annotated[str, Field(min_length=1)]
