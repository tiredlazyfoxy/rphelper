"""Session configuration — the two resolver chains, the one read, the use-time model check.

Feature `017`, steps `003` and `004` (skeleton; `004` adds the configuration writes).
Interface only; bodies are filled by the coder.

`resolve_model_for_use` has no call site until `021` wires compose (D2).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Connection, select

from app.db.schema import characters, sessions, users
from app.errors import CharacterNotFoundError, ModelNotChosenError, NoModelEnabledError, SessionNotFoundError
from app.services.llm_registry import (
    UNSET,
    EnabledChatModel,
    ModelRefLevel,
    Unset,
    first_enabled_chat_model,
    validate_chat_model,
)


class ConfigLevel(StrEnum):
    """Who supplied a resolved value (Wire contract `Level`)."""

    SESSION = "session"
    CHARACTER = "character"
    USER = "user"
    DEFAULT = "default"


@dataclass(frozen=True)
class ModelRef:
    """A stored model reference: the registry server id and the model name."""

    server_id: int
    model_name: str


@dataclass(frozen=True)
class ResolvedSetting[T]:
    """One setting resolved along its chain (Wire contract `Setting<T>`)."""

    session: T | None
    inherited: T | None
    inherited_level: ConfigLevel | None
    value: T | None
    level: ConfigLevel | None


@dataclass(frozen=True)
class CharacterAssistantLevel:
    """What the character level may hold for the assistant chain: no model, no language."""

    system_prompt: str | None
    tool_memo_search: bool | None
    tool_session_search: bool | None
    tool_web_search: bool | None


@dataclass(frozen=True)
class SessionAssistantLevel:
    """What the session level holds for the assistant chain, including the captured model."""

    model: ModelRef | None
    system_prompt: str | None
    tool_memo_search: bool | None
    tool_session_search: bool | None
    tool_web_search: bool | None


@dataclass(frozen=True)
class UserLanguageLevel:
    """What the user level may hold: the two languages and nothing else."""

    rp_language: str | None
    preferred_language: str | None


@dataclass(frozen=True)
class SessionLanguageLevel:
    """The session's language overrides."""

    rp_language: str | None
    preferred_language: str | None


@dataclass(frozen=True)
class AssistantConfiguration:
    """The assistant chain's result; `model` is the session's captured reference, unchanged."""

    model: ModelRef | None
    system_prompt: ResolvedSetting[str]
    tool_memo_search: ResolvedSetting[bool]
    tool_session_search: ResolvedSetting[bool]
    tool_web_search: ResolvedSetting[bool]


@dataclass(frozen=True)
class LanguageConfiguration:
    """The language chain's result."""

    rp_language: ResolvedSetting[str]
    preferred_language: ResolvedSetting[str]


@dataclass(frozen=True)
class SessionConfiguration:
    """The Wire contract's `SessionConfiguration`, assembled from both chains."""

    model: ModelRef | None
    system_prompt: ResolvedSetting[str]
    tool_memo_search: ResolvedSetting[bool]
    tool_session_search: ResolvedSetting[bool]
    tool_web_search: ResolvedSetting[bool]
    rp_language: ResolvedSetting[str]
    preferred_language: ResolvedSetting[str]


@dataclass(frozen=True)
class CharacterConfiguration:
    """A character's own stored configuration columns (no resolution)."""

    model: ModelRef | None
    system_prompt: str | None
    tool_memo_search: bool | None
    tool_session_search: bool | None
    tool_web_search: bool | None


@dataclass(frozen=True)
class UserSettings:
    """The caller's stored language settings."""

    rp_language: str | None
    preferred_language: str | None


def resolve_assistant_chain(
    character: CharacterAssistantLevel,
    session: SessionAssistantLevel,
) -> AssistantConfiguration:
    """Resolve system prompt and tools along character -> session; pass the model through."""
    # The model is the session's captured reference, unchanged: never validated, never
    # substituted, and the registry is never consulted here (R4).
    return AssistantConfiguration(
        model=session.model,
        system_prompt=_resolve_text(session.system_prompt, character.system_prompt, ConfigLevel.CHARACTER),
        tool_memo_search=_resolve_tool(session.tool_memo_search, character.tool_memo_search),
        tool_session_search=_resolve_tool(session.tool_session_search, character.tool_session_search),
        tool_web_search=_resolve_tool(session.tool_web_search, character.tool_web_search),
    )


def resolve_language_chain(
    user: UserLanguageLevel,
    session: SessionLanguageLevel,
) -> LanguageConfiguration:
    """Resolve the two languages along user -> session."""
    return LanguageConfiguration(
        rp_language=_resolve_text(session.rp_language, user.rp_language, ConfigLevel.USER),
        preferred_language=_resolve_text(session.preferred_language, user.preferred_language, ConfigLevel.USER),
    )


def get_session_configuration(
    connection: Connection,
    user_id: int,
    session_id: int,
) -> SessionConfiguration:
    """One owner-scoped read of session, character and user, then both resolvers."""
    # The character's model columns are deliberately not selected: the character input cannot
    # hold them, and the session's captured reference is the only model that counts (R4).
    statement = (
        select(
            sessions.c.model_server_id,
            sessions.c.model_name,
            sessions.c.system_prompt.label("session_system_prompt"),
            sessions.c.tool_memo_search.label("session_tool_memo_search"),
            sessions.c.tool_session_search.label("session_tool_session_search"),
            sessions.c.tool_web_search.label("session_tool_web_search"),
            sessions.c.rp_language.label("session_rp_language"),
            sessions.c.preferred_language.label("session_preferred_language"),
            characters.c.system_prompt.label("character_system_prompt"),
            characters.c.tool_memo_search.label("character_tool_memo_search"),
            characters.c.tool_session_search.label("character_tool_session_search"),
            characters.c.tool_web_search.label("character_tool_web_search"),
            users.c.rp_language.label("user_rp_language"),
            users.c.preferred_language.label("user_preferred_language"),
        )
        .select_from(
            sessions.join(
                characters,
                (characters.c.id == sessions.c.character_id) & (characters.c.user_id == user_id),
            ).join(users, users.c.id == user_id)
        )
        .where(sessions.c.id == session_id, sessions.c.user_id == user_id)
    )
    with _reading(connection):
        row = connection.execute(statement).first()
    if row is None:
        raise SessionNotFoundError()
    assistant = resolve_assistant_chain(
        CharacterAssistantLevel(
            system_prompt=row.character_system_prompt,
            tool_memo_search=row.character_tool_memo_search,
            tool_session_search=row.character_tool_session_search,
            tool_web_search=row.character_tool_web_search,
        ),
        SessionAssistantLevel(
            model=_model_ref(row.model_server_id, row.model_name),
            system_prompt=row.session_system_prompt,
            tool_memo_search=row.session_tool_memo_search,
            tool_session_search=row.session_tool_session_search,
            tool_web_search=row.session_tool_web_search,
        ),
    )
    language = resolve_language_chain(
        UserLanguageLevel(rp_language=row.user_rp_language, preferred_language=row.user_preferred_language),
        SessionLanguageLevel(rp_language=row.session_rp_language, preferred_language=row.session_preferred_language),
    )
    return SessionConfiguration(
        model=assistant.model,
        system_prompt=assistant.system_prompt,
        tool_memo_search=assistant.tool_memo_search,
        tool_session_search=assistant.tool_session_search,
        tool_web_search=assistant.tool_web_search,
        rp_language=language.rp_language,
        preferred_language=language.preferred_language,
    )


def resolve_model_for_use(
    connection: Connection,
    user_id: int,
    session_id: int,
) -> EnabledChatModel:
    """D2's use-time check; returns the session's captured model only when it is enabled now."""
    # No call site until `021` wires compose (D2). Reads only; never writes, never falls back.
    with _reading(connection):
        row = connection.execute(
            select(sessions.c.model_server_id, sessions.c.model_name).where(
                sessions.c.id == session_id,
                sessions.c.user_id == user_id,
            )
        ).first()
    if row is None:
        raise SessionNotFoundError()
    # D2 step 1: nothing enabled on the instance outranks the session's own state.
    if first_enabled_chat_model(connection) is None:
        raise NoModelEnabledError()
    captured = _model_ref(row.model_server_id, row.model_name)
    if captured is None:
        raise ModelNotChosenError()
    return validate_chat_model(connection, captured.server_id, captured.model_name, ModelRefLevel.SESSION)


def update_session_configuration(
    connection: Connection,
    user_id: int,
    session_id: int,
    *,
    model: ModelRef | Unset = UNSET,
    system_prompt: str | None | Unset = UNSET,
    tool_memo_search: bool | None | Unset = UNSET,
    tool_session_search: bool | None | Unset = UNSET,
    tool_web_search: bool | None | Unset = UNSET,
    rp_language: str | None | Unset = UNSET,
    preferred_language: str | None | Unset = UNSET,
) -> SessionConfiguration:
    """Write only the supplied session columns (set-time model check first); return the result."""
    values = _supplied(
        system_prompt=system_prompt,
        tool_memo_search=tool_memo_search,
        tool_session_search=tool_session_search,
        tool_web_search=tool_web_search,
        rp_language=rp_language,
        preferred_language=preferred_language,
    )
    if not isinstance(model, Unset):
        values["model_server_id"] = model.server_id
        values["model_name"] = model.model_name
    owned = (sessions.c.id == session_id) & (sessions.c.user_id == user_id)
    with connection.begin():
        if connection.execute(select(sessions.c.id).where(owned)).first() is None:
            raise SessionNotFoundError()
        if values:
            # D10: the set-time check runs inside this transaction, so a refusal writes nothing.
            if not isinstance(model, Unset):
                validate_chat_model(connection, model.server_id, model.model_name, ModelRefLevel.SESSION)
            # D11: `updated_at` only; `last_used_at` is never touched by configuration.
            connection.execute(sessions.update().where(owned).values(**values, updated_at=_now_text()))
    return get_session_configuration(connection, user_id, session_id)


def get_character_configuration(
    connection: Connection,
    user_id: int,
    character_id: int,
) -> CharacterConfiguration:
    """Owner-scoped read of a character's configuration columns (archived reads)."""
    statement = select(
        characters.c.model_server_id,
        characters.c.model_name,
        characters.c.system_prompt,
        characters.c.tool_memo_search,
        characters.c.tool_session_search,
        characters.c.tool_web_search,
    ).where(characters.c.id == character_id, characters.c.user_id == user_id)
    with _reading(connection):
        row = connection.execute(statement).first()
    if row is None:
        raise CharacterNotFoundError()
    return CharacterConfiguration(
        model=_model_ref(row.model_server_id, row.model_name),
        system_prompt=row.system_prompt,
        tool_memo_search=row.tool_memo_search,
        tool_session_search=row.tool_session_search,
        tool_web_search=row.tool_web_search,
    )


def update_character_configuration(
    connection: Connection,
    user_id: int,
    character_id: int,
    *,
    model: ModelRef | None | Unset = UNSET,
    system_prompt: str | None | Unset = UNSET,
    tool_memo_search: bool | None | Unset = UNSET,
    tool_session_search: bool | None | Unset = UNSET,
    tool_web_search: bool | None | Unset = UNSET,
) -> CharacterConfiguration:
    """Write only the supplied character columns (set-time model check first); never a session."""
    values = _supplied(
        system_prompt=system_prompt,
        tool_memo_search=tool_memo_search,
        tool_session_search=tool_session_search,
        tool_web_search=tool_web_search,
    )
    if not isinstance(model, Unset):
        # `None` clears the override: both columns NULL together (D4, D10).
        values["model_server_id"] = None if model is None else model.server_id
        values["model_name"] = None if model is None else model.model_name
    owned = (characters.c.id == character_id) & (characters.c.user_id == user_id)
    with connection.begin():
        if connection.execute(select(characters.c.id).where(owned)).first() is None:
            raise CharacterNotFoundError()
        if values:
            if isinstance(model, ModelRef):
                validate_chat_model(connection, model.server_id, model.model_name, ModelRefLevel.CHARACTER)
            # Only this character's configuration columns; no `sessions` row is touched (US-139.AC-1).
            connection.execute(characters.update().where(owned).values(**values, updated_at=_now_text()))
    return get_character_configuration(connection, user_id, character_id)


def get_user_settings(connection: Connection, user_id: int) -> UserSettings:
    """Read the caller's two language settings."""
    statement = select(users.c.rp_language, users.c.preferred_language).where(users.c.id == user_id)
    with _reading(connection):
        row = connection.execute(statement).one()
    return UserSettings(rp_language=row.rp_language, preferred_language=row.preferred_language)


def update_user_settings(
    connection: Connection,
    user_id: int,
    *,
    rp_language: str | None | Unset = UNSET,
    preferred_language: str | None | Unset = UNSET,
) -> UserSettings:
    """Write only the supplied language columns plus `users.updated_at`."""
    values = _supplied(rp_language=rp_language, preferred_language=preferred_language)
    if values:
        with connection.begin():
            connection.execute(users.update().where(users.c.id == user_id).values(**values, updated_at=_now_text()))
    return get_user_settings(connection, user_id)


def _supplied(**fields: object) -> dict[str, object]:
    """The keyword arguments that were supplied (not `UNSET`); `None` is kept, it clears."""
    return {name: value for name, value in fields.items() if not isinstance(value, Unset)}


def _now_text() -> str:
    """Now as the fixed-width UTC ISO-8601 text the other services write."""
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _resolve_text(session: str | None, inherited: str | None, inherited_from: ConfigLevel) -> ResolvedSetting[str]:
    """A text setting: the session wins, else the level above; nothing set -> value and level null."""
    inherited_level = inherited_from if inherited is not None else None
    if session is not None:
        return ResolvedSetting(session, inherited, inherited_level, session, ConfigLevel.SESSION)
    return ResolvedSetting(None, inherited, inherited_level, inherited, inherited_level)


def _resolve_tool(session: bool | None, character: bool | None) -> ResolvedSetting[bool]:
    """A tool switch: session, else character, else on with level `default` (D5) — never null."""
    if character is not None:
        inherited, inherited_level = character, ConfigLevel.CHARACTER
    else:
        inherited, inherited_level = True, ConfigLevel.DEFAULT
    if session is not None:
        return ResolvedSetting(session, inherited, inherited_level, session, ConfigLevel.SESSION)
    return ResolvedSetting(None, inherited, inherited_level, inherited, inherited_level)


def _model_ref(server_id: int | None, model_name: str | None) -> ModelRef | None:
    """The stored pair as a reference; both-or-neither is a schema CHECK (D4)."""
    if server_id is None or model_name is None:
        return None
    return ModelRef(server_id=server_id, model_name=model_name)


@contextmanager
def _reading(connection: Connection) -> Iterator[None]:
    """A read on a Core connection autobegins; end it again when the caller had none open."""
    opened_here = not connection.in_transaction()
    try:
        yield
    finally:
        if opened_here and connection.in_transaction():
            connection.rollback()
