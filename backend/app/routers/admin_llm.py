"""`/api/admin/llm-servers` — the LLM registry's transport layer, guarded at the router level.

The router owns HTTP and nothing else: no business rule, no SQL, no secret resolution, no
transaction. Its only database contact is `app.db.engine.get_connection`; every rule lives
in `app.services.llm_registry`. Each handler calls **exactly one** registry operation and
maps its plain result onto a model. No handler translates a domain error by hand — the
single `DomainError` handler renders `llm_server_not_found` (404), `llm_unreachable`
(502) and `secret_ref_missing` (500).

**`require_role(Role.ADMIN)` is attached to the router, never to a handler**, so a route
added later cannot forget the guard.

Nine routes (`context.md` D17). `{server_id}` is declared with the inbound snowflake alias.
No query parameter exists anywhere on this router. Create, set-enabled-models and designate
take the process's snowflake generator from `app.state` via `get_id_generator`. The three
outbound routes (test, available-models, designate) are `async def`, take `Settings` from
`get_settings` and pass it down as a plain argument, and take the client factory from
`get_llm_client_factory`.

**Test seam:** `get_llm_client_factory` is the one place the router obtains the registry's
`LlmClientFactory`. Its production answer is the class `LlmClient` itself; tests replace it
with `app.dependency_overrides[get_llm_client_factory] = lambda: fake_factory`, where
`fake_factory(base_url, resolved_api_key, timeout_seconds)` returns an `LlmClientLike`.

`UpdateLlmServerRequest` → `update_server` mapping (`context.md` D9): each field is passed
as its value iff it is in `body.model_fields_set` and not `None`, else `UNSET`.

`ConnectionTestResult` → `ConnectionTestResponse`: `outcome` from the result, `ok` and
`tested_at` from the returned server's `last_test_ok` / `last_test_at`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Connection

from app.config import Settings, get_settings
from app.db.engine import get_connection
from app.dependencies import require_role
from app.ids import SnowflakeGenerator
from app.models.admin_llm import (
    AvailableModelsResponse,
    ConnectionTestResponse,
    CreateLlmServerRequest,
    DesignateEmbeddingModelRequest,
    EnabledModelsResponse,
    LlmServerListResponse,
    LlmServerResponse,
    SetEnabledModelsRequest,
    UpdateLlmServerRequest,
)
from app.models.ids import SnowflakeIn
from app.roles import Role
from app.routers.bootstrap import get_id_generator
from app.services.llm.client import LlmClient
from app.services.llm_registry import (
    UNSET,
    LlmClientFactory,
    check_server_connection,
    clear_embedding_designation,
    create_server,
    delete_server,
    designate_embedding_model,
    list_available_models,
    list_servers,
    set_enabled_models,
    update_server,
)

#: The router's one guard.
require_admin = require_role(Role.ADMIN)

router = APIRouter(
    prefix="/api/admin/llm-servers",
    tags=["admin-llm-servers"],
    dependencies=[Depends(require_admin)],
)


def get_llm_client_factory() -> LlmClientFactory:
    """The registry's client factory for outbound calls; production answer is `LlmClient`.

    Tests override this with `app.dependency_overrides[get_llm_client_factory]`.
    """
    return LlmClient


@router.get("", status_code=200)
def list_llm_servers(
    connection: Annotated[Connection, Depends(get_connection)],
) -> LlmServerListResponse:
    """Every registration, via `list_servers(connection)`."""
    servers = list_servers(connection)
    return LlmServerListResponse(
        servers=[LlmServerResponse.model_validate(s, from_attributes=True) for s in servers]
    )


@router.post("", status_code=201)
def create_llm_server(
    body: CreateLlmServerRequest,
    connection: Annotated[Connection, Depends(get_connection)],
    generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)],
) -> LlmServerResponse:
    """Register a connection via `create_server(connection, generator, name, kind, base_url, api_key_ref)`."""
    server = create_server(
        connection, generator, body.name, body.kind, body.base_url, body.api_key_ref
    )
    return LlmServerResponse.model_validate(server, from_attributes=True)


@router.patch("/{server_id}", status_code=200)
def update_llm_server(
    server_id: SnowflakeIn,
    body: UpdateLlmServerRequest,
    connection: Annotated[Connection, Depends(get_connection)],
) -> LlmServerResponse:
    """Partial update via `update_server(connection, server_id, **supplied)` (D9 mapping above)."""
    supplied = body.model_fields_set
    server = update_server(
        connection,
        server_id,
        name=body.name if "name" in supplied and body.name is not None else UNSET,
        kind=body.kind if "kind" in supplied and body.kind is not None else UNSET,
        base_url=(
            body.base_url if "base_url" in supplied and body.base_url is not None else UNSET
        ),
        api_key_ref=(
            body.api_key_ref
            if "api_key_ref" in supplied and body.api_key_ref is not None
            else UNSET
        ),
    )
    return LlmServerResponse.model_validate(server, from_attributes=True)


@router.delete("/{server_id}", status_code=204)
def delete_llm_server(
    server_id: SnowflakeIn,
    connection: Annotated[Connection, Depends(get_connection)],
) -> None:
    """Remove the registration and its models via `delete_server(connection, server_id)`."""
    delete_server(connection, server_id)


@router.post("/{server_id}/test", status_code=200)
async def run_connection_test(
    server_id: SnowflakeIn,
    connection: Annotated[Connection, Depends(get_connection)],
    settings: Annotated[Settings, Depends(get_settings)],
    client_factory: Annotated[LlmClientFactory, Depends(get_llm_client_factory)],
) -> ConnectionTestResponse:
    """Test the connection via `check_server_connection(connection, server_id, settings, client_factory=...)`."""
    result = await check_server_connection(
        connection, server_id, settings, client_factory=client_factory
    )
    return ConnectionTestResponse.model_validate(
        {
            "outcome": result.outcome,
            "ok": result.server.last_test_ok,
            "tested_at": result.server.last_test_at,
        }
    )


@router.get("/{server_id}/available-models", status_code=200)
async def list_llm_server_available_models(
    server_id: SnowflakeIn,
    connection: Annotated[Connection, Depends(get_connection)],
    settings: Annotated[Settings, Depends(get_settings)],
    client_factory: Annotated[LlmClientFactory, Depends(get_llm_client_factory)],
) -> AvailableModelsResponse:
    """The probe's listing via `list_available_models(connection, server_id, settings, client_factory=...)`."""
    names = await list_available_models(
        connection, server_id, settings, client_factory=client_factory
    )
    return AvailableModelsResponse(model_names=names)


@router.post("/{server_id}/models", status_code=200)
def set_llm_server_enabled_models(
    server_id: SnowflakeIn,
    body: SetEnabledModelsRequest,
    connection: Annotated[Connection, Depends(get_connection)],
    generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)],
) -> EnabledModelsResponse:
    """Replace the enabled set via `set_enabled_models(connection, generator, server_id, model_names)`."""
    names = set_enabled_models(connection, generator, server_id, body.model_names)
    return EnabledModelsResponse(enabled_model_names=names)


@router.post("/{server_id}/embedding-model", status_code=200)
async def designate_llm_server_embedding_model(
    server_id: SnowflakeIn,
    body: DesignateEmbeddingModelRequest,
    connection: Annotated[Connection, Depends(get_connection)],
    generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)],
    settings: Annotated[Settings, Depends(get_settings)],
    client_factory: Annotated[LlmClientFactory, Depends(get_llm_client_factory)],
) -> LlmServerResponse:
    """Designate via `designate_embedding_model(connection, generator, server_id, model_name, settings, ...)`."""
    server = await designate_embedding_model(
        connection, generator, server_id, body.model_name, settings, client_factory=client_factory
    )
    return LlmServerResponse.model_validate(server, from_attributes=True)


@router.delete("/{server_id}/embedding-model", status_code=204)
def clear_llm_server_embedding_model(
    server_id: SnowflakeIn,
    connection: Annotated[Connection, Depends(get_connection)],
) -> None:
    """Clear the designation via `clear_embedding_designation(connection, server_id)`."""
    clear_embedding_designation(connection, server_id)
