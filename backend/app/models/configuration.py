"""The configuration request and response models — nothing else (feature `017`, D6, D9, D10).

**Levels.** `ConfigurationLevel` names exactly the four levels a resolved setting can come
from: `"session"`, `"character"`, `"user"`, `"default"`. The service hands them over as its
own `StrEnum` members, which equal these strings.

**Responses.** Every response model sets `from_attributes=True`, so a service's frozen
dataclasses (nested ones included) validate by attribute. Ids use the outbound snowflake
alias and leave as **decimal strings**. `SessionConfigurationResponse` is the wire
`SessionConfiguration`: exactly seven keys — the captured `model` (or `null`) and six
settings, each exactly `session`, `inherited`, `inherited_level`, `value`, `level`.
`CharacterConfigurationResponse` has exactly five keys. `EnabledModelResponse` never
carries `base_url`, `kind`, `api_key_ref` or test status. No model carries `user_id`.

**Requests.** Unknown keys are ignored. Which keys were sent is **`model_fields_set`**: an
explicit `null` is in it, an absent key is not (the router maps absent to `UNSET`).
Normalisation (D6) runs only on a supplied string: a language is trimmed and a blank one
becomes `None`; a system prompt is kept verbatim unless blank, which becomes `None`; a
`model_name` must be non-blank and is kept verbatim. Tool values are strict booleans. On the
session request an explicit `"model": null` fails validation (D10); on the character request
it is accepted and means "clear".

This module imports neither `app.services`, `app.routers`, `app.db` nor `fastapi`.
"""

from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, StrictBool, field_validator

from app.models.ids import SnowflakeIn, SnowflakeOut

#: Who supplied a resolved setting's value (or its inherited value).
ConfigurationLevel = Literal["session", "character", "user", "default"]


def _normalise_language(value: str | None) -> str | None:
    """Trim a supplied language; a blank one becomes `None`; `None` passes through (D6)."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _normalise_system_prompt(value: str | None) -> str | None:
    """Keep a supplied system prompt verbatim; a blank one becomes `None`; `None` passes (D6)."""
    if value is None or not value.strip():
        return None
    return value


def _require_non_blank_model_name(value: str) -> str:
    """Return `value` unchanged when it holds a non-whitespace character; else raise `ValueError`."""
    if not value.strip():
        raise ValueError("model_name must not be blank")
    return value


#: A nullable language as the PATCH routes accept it.
LanguageIn = Annotated[str | None, AfterValidator(_normalise_language)]

#: A nullable system prompt as the PATCH routes accept it.
SystemPromptIn = Annotated[str | None, AfterValidator(_normalise_system_prompt)]

#: A model name as a `ModelRefIn` accepts it: non-blank, verbatim.
ModelNameIn = Annotated[str, AfterValidator(_require_non_blank_model_name)]


# --- responses ------------------------------------------------------------------------


class ModelRefOut(BaseModel):
    """A `(server_id, model_name)` reference on the wire, unvalidated."""

    model_config = ConfigDict(from_attributes=True)

    server_id: SnowflakeOut
    model_name: str


class EnabledModelResponse(BaseModel):
    """One enabled model on the wire. Exactly three keys."""

    model_config = ConfigDict(from_attributes=True)

    server_id: SnowflakeOut
    server_name: str
    model_name: str


class EnabledModelListResponse(BaseModel):
    """The enabled models, in first-enabled order (D7), under the single `models` field."""

    model_config = ConfigDict(from_attributes=True)

    models: list[EnabledModelResponse]


class UserSettingsResponse(BaseModel):
    """The user's two language defaults."""

    model_config = ConfigDict(from_attributes=True)

    rp_language: str | None
    preferred_language: str | None


class CharacterConfigurationResponse(BaseModel):
    """The character level of the assistant chain. Exactly five keys."""

    model_config = ConfigDict(from_attributes=True)

    model: ModelRefOut | None
    system_prompt: str | None
    tool_memo_search: bool | None
    tool_session_search: bool | None
    tool_web_search: bool | None


class TextSettingResponse(BaseModel):
    """A resolved text setting (`Setting<string>`). Exactly five keys."""

    model_config = ConfigDict(from_attributes=True)

    session: str | None
    inherited: str | None
    inherited_level: ConfigurationLevel | None
    value: str | None
    level: ConfigurationLevel | None


class BooleanSettingResponse(BaseModel):
    """A resolved tool switch (`Setting<boolean>`); `value` is never null. Exactly five keys."""

    model_config = ConfigDict(from_attributes=True)

    session: bool | None
    inherited: bool | None
    inherited_level: ConfigurationLevel | None
    value: bool
    level: ConfigurationLevel | None


class SessionConfigurationResponse(BaseModel):
    """The session's resolved configuration. Exactly seven keys."""

    model_config = ConfigDict(from_attributes=True)

    model: ModelRefOut | None
    system_prompt: TextSettingResponse
    tool_memo_search: BooleanSettingResponse
    tool_session_search: BooleanSettingResponse
    tool_web_search: BooleanSettingResponse
    rp_language: TextSettingResponse
    preferred_language: TextSettingResponse


# --- requests -------------------------------------------------------------------------


class ModelRefIn(BaseModel):
    """A model reference in a PATCH body: a required snowflake and a non-blank name."""

    model_config = ConfigDict(extra="ignore")

    server_id: SnowflakeIn
    model_name: ModelNameIn


class UpdateUserSettingsRequest(BaseModel):
    """`PATCH /api/me/settings`: any subset of the two languages; sent keys in `model_fields_set`."""

    model_config = ConfigDict(extra="ignore")

    rp_language: LanguageIn = None
    preferred_language: LanguageIn = None


class UpdateSessionConfigurationRequest(BaseModel):
    """`PATCH /api/sessions/{id}/configuration`; `model` may be absent but never `null` (D10)."""

    model_config = ConfigDict(extra="ignore")

    model: ModelRefIn | None = None
    system_prompt: SystemPromptIn = None
    tool_memo_search: StrictBool | None = None
    tool_session_search: StrictBool | None = None
    tool_web_search: StrictBool | None = None
    rp_language: LanguageIn = None
    preferred_language: LanguageIn = None

    @field_validator("model", mode="before")
    @classmethod
    def _reject_null_model(cls, value: Any) -> Any:
        """Refuse an explicit `null` (a 422); an absent key never reaches this validator."""
        if value is None:
            raise ValueError("model may not be null; send a model to replace it")
        return value


class UpdateCharacterConfigurationRequest(BaseModel):
    """`PATCH /api/characters/{id}/configuration`; `model: null` clears; no language keys (R1)."""

    model_config = ConfigDict(extra="ignore")

    model: ModelRefIn | None = None
    system_prompt: SystemPromptIn = None
    tool_memo_search: StrictBool | None = None
    tool_session_search: StrictBool | None = None
    tool_web_search: StrictBool | None = None
