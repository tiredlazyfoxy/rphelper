"""`/api/models`, `/api/me/settings` and the session / character configuration routes.

Feature `017`, step `005`. Transport layer only: no business rule, no SQL, no
transaction, no `app.db.schema` import. Its only database contact is
`app.db.engine.get_connection`; every rule lives in `app.services.configuration` and
`app.services.llm_registry`.

Declared with **no prefix**; each handler carries its own full literal path.
`require_user` is attached to the **router** so a route added later cannot forget the
guard; each handler also names it as a parameter to receive the `CurrentUser`. Path ids
use the inbound snowflake alias, so a non-numeric id answers 422.

Each PATCH handler maps its request model's sent fields (`model_fields_set`) to service
keyword arguments: a field not sent becomes `UNSET`, a field sent as `null` becomes
`None`. The router catches nothing; domain errors propagate to the one `DomainError`
handler in `app.main`. Registered **last** in `app.main`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Connection

from app.db.engine import get_connection
from app.dependencies import CurrentUser, require_user
from app.models.configuration import (
    CharacterConfigurationResponse,
    EnabledModelListResponse,
    EnabledModelResponse,
    SessionConfigurationResponse,
    UpdateCharacterConfigurationRequest,
    UpdateSessionConfigurationRequest,
    UpdateUserSettingsRequest,
    UserSettingsResponse,
)
from app.models.ids import SnowflakeIn
from app.services.configuration import (
    ModelRef,
    get_character_configuration,
    get_session_configuration,
    get_user_settings,
    update_character_configuration,
    update_session_configuration,
    update_user_settings,
)
from app.services.llm_registry import UNSET, Unset, list_enabled_chat_models

router = APIRouter(
    tags=["configuration"],
    dependencies=[Depends(require_user)],
)


@router.get("/api/models", status_code=200)
def list_models(
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> EnabledModelListResponse:
    """Every enabled chat model via `list_enabled_chat_models`, in service order (D7)."""
    models = list_enabled_chat_models(connection)
    return EnabledModelListResponse(
        models=[
            EnabledModelResponse(
                server_id=item.server.id,
                server_name=item.server.name,
                model_name=item.model_name,
            )
            for item in models
        ]
    )


@router.get("/api/me/settings", status_code=200)
def read_own_settings(
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> UserSettingsResponse:
    """The caller's language settings via `get_user_settings`."""
    settings = get_user_settings(connection, current_user.id)
    return UserSettingsResponse.model_validate(settings, from_attributes=True)


@router.patch("/api/me/settings", status_code=200)
def update_own_settings(
    body: UpdateUserSettingsRequest,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> UserSettingsResponse:
    """Write the sent language settings via `update_user_settings`; unsent keys are `UNSET`."""
    settings = update_user_settings(
        connection,
        current_user.id,
        rp_language=_sent(body, "rp_language", body.rp_language),
        preferred_language=_sent(body, "preferred_language", body.preferred_language),
    )
    return UserSettingsResponse.model_validate(settings, from_attributes=True)


@router.get("/api/sessions/{session_id}/configuration", status_code=200)
def read_session_configuration(
    session_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> SessionConfigurationResponse:
    """The session's resolved configuration via `get_session_configuration`."""
    configuration = get_session_configuration(connection, current_user.id, session_id)
    return SessionConfigurationResponse.model_validate(configuration, from_attributes=True)


@router.patch("/api/sessions/{session_id}/configuration", status_code=200)
def update_session_configuration_route(
    session_id: SnowflakeIn,
    body: UpdateSessionConfigurationRequest,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> SessionConfigurationResponse:
    """Write the sent session overrides via `update_session_configuration`.

    The `model` sub-object becomes a service `ModelRef`; unsent keys are `UNSET`.
    """
    model: ModelRef | Unset = UNSET
    if "model" in body.model_fields_set and body.model is not None:
        model = ModelRef(server_id=body.model.server_id, model_name=body.model.model_name)
    configuration = update_session_configuration(
        connection,
        current_user.id,
        session_id,
        model=model,
        system_prompt=_sent(body, "system_prompt", body.system_prompt),
        tool_memo_search=_sent(body, "tool_memo_search", body.tool_memo_search),
        tool_session_search=_sent(body, "tool_session_search", body.tool_session_search),
        tool_web_search=_sent(body, "tool_web_search", body.tool_web_search),
        rp_language=_sent(body, "rp_language", body.rp_language),
        preferred_language=_sent(body, "preferred_language", body.preferred_language),
    )
    return SessionConfigurationResponse.model_validate(configuration, from_attributes=True)


@router.get("/api/characters/{character_id}/configuration", status_code=200)
def read_character_configuration(
    character_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> CharacterConfigurationResponse:
    """The character's own configuration level via `get_character_configuration`."""
    configuration = get_character_configuration(connection, current_user.id, character_id)
    return CharacterConfigurationResponse.model_validate(configuration, from_attributes=True)


@router.patch("/api/characters/{character_id}/configuration", status_code=200)
def update_character_configuration_route(
    character_id: SnowflakeIn,
    body: UpdateCharacterConfigurationRequest,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> CharacterConfigurationResponse:
    """Write the sent character fields via `update_character_configuration`.

    An explicit `model: null` is passed as `None` (clear); unsent keys are `UNSET`.
    """
    model: ModelRef | None | Unset = UNSET
    if "model" in body.model_fields_set:
        model = (
            None
            if body.model is None
            else ModelRef(server_id=body.model.server_id, model_name=body.model.model_name)
        )
    configuration = update_character_configuration(
        connection,
        current_user.id,
        character_id,
        model=model,
        system_prompt=_sent(body, "system_prompt", body.system_prompt),
        tool_memo_search=_sent(body, "tool_memo_search", body.tool_memo_search),
        tool_session_search=_sent(body, "tool_session_search", body.tool_session_search),
        tool_web_search=_sent(body, "tool_web_search", body.tool_web_search),
    )
    return CharacterConfigurationResponse.model_validate(configuration, from_attributes=True)


def _sent[T](body: BaseModel, name: str, value: T) -> T | Unset:
    """`value` when `name` was sent in `body` (an explicit `null` included), else `UNSET`."""
    return value if name in body.model_fields_set else UNSET
