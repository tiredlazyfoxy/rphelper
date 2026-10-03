"""Tests for the resolvers, the session configuration read and the use-time model check in
``app.services.configuration`` — feature 017, step 003.

Every expected value comes from ``docs/plans/017.session-configuration/003.resolver-and-use-time-check.md``
(Interface intent, DoD-1 .. DoD-10), ``003.context.md`` and the feature ``context.md``: the Wire
contract's level rules (``system_prompt`` inherits from ``character`` else null; each tool inherits
from ``character`` else ``True`` with level ``default``; the languages inherit from ``user`` else
null; ``level`` is ``session`` exactly when ``session`` is non-null), **D2** (check order: nothing
enabled -> ``no_model_enabled``; captured model NULL -> ``model_not_chosen``; not enabled ->
``model_not_enabled``), **D3** (level ``session``), **D5**, **D8**, **D12**, **R1**, **R4**, **R5**
and **R6**. No resolver is called to compute an expectation.

Bindings come from ``status.md`` ``## Skeleton`` -> Step 003:
``resolve_assistant_chain(character, session) -> AssistantConfiguration``,
``resolve_language_chain(user, session) -> LanguageConfiguration``,
``get_session_configuration(connection, user_id, session_id) -> SessionConfiguration`` and
``resolve_model_for_use(connection, user_id, session_id) -> EnabledChatModel``, plus the frozen
value types (``ConfigLevel``, ``ModelRef``, ``ResolvedSetting``, the four per-level inputs).

Fixtures: schema from ``create_all`` on the per-test engine; users, characters, sessions,
``llm_servers`` and ``models`` are raw-inserted. Nothing is added to ``conftest.py``. Tests are
suffixed ``__S017_003_DoD<n>``.
"""

import ast
import dataclasses
import inspect
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import Engine, RowMapping, Table, select, update

import app.services.configuration as configuration_module
from app.db import schema
from app.errors import (
    ModelNotChosenError,
    ModelNotEnabledError,
    NoModelEnabledError,
    SessionNotFoundError,
)
from app.roles import Role
from app.services.configuration import (
    AssistantConfiguration,
    CharacterAssistantLevel,
    ConfigLevel,
    LanguageConfiguration,
    ModelRef,
    SessionAssistantLevel,
    SessionConfiguration,
    SessionLanguageLevel,
    UserLanguageLevel,
    get_session_configuration,
    resolve_assistant_chain,
    resolve_language_chain,
    resolve_model_for_use,
)
from app.services.llm_registry import EnabledChatModel

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
ARCHIVED_AT = "2026-02-01T00:00:00.000000+00:00"

USER_A = 101
USER_B = 202

CHAR_A = 1_001
CHAR_A_ARCHIVED = 1_002
CHAR_B = 2_001

SESSION_A = 3_001
SESSION_A_ARCHIVED = 3_002
SESSION_A_UNDER_ARCHIVED_CHARACTER = 3_003
SESSION_B = 4_001
UNKNOWN_SESSION_ID = 9_999_999_999

#: Registry ids: server-id order and models.id order disagree (feature "Registry fixtures"), so the
#: first enabled model (D7) is server B's, while the sessions below capture server A's model.
SERVER_B = 5_100
SERVER_A = 5_200
MODEL_A = 61_001
MODEL_A_NAME = "alpha-chat"
MODEL_B = 62_001
MODEL_B_NAME = "beta-chat"
MODEL_A_OFF = 61_500
MODEL_A_OFF_NAME = "alpha-off"
MISSING_SERVER_ID = 7_777_777

D12_NAMES = {
    "list_enabled_chat_models",
    "first_enabled_chat_model",
    "validate_chat_model",
    "ModelRefLevel",
    "EnabledChatModel",
    "UNSET",
    "Unset",
}

SESSION = ConfigLevel.SESSION
CHARACTER = ConfigLevel.CHARACTER
USER = ConfigLevel.USER
DEFAULT = ConfigLevel.DEFAULT


# --------------------------------------------------------------------------- helpers


def _setting(setting: Any) -> tuple[Any, Any, Any, Any, Any]:
    """The five Wire-contract fields of a resolved setting, in order."""
    return (setting.session, setting.inherited, setting.inherited_level, setting.value, setting.level)


def _model_pair(model: ModelRef | None) -> tuple[int, str] | None:
    return None if model is None else (model.server_id, model.model_name)


def _character_level(
    system_prompt: str | None = None,
    tool_memo_search: bool | None = None,
    tool_session_search: bool | None = None,
    tool_web_search: bool | None = None,
) -> CharacterAssistantLevel:
    return CharacterAssistantLevel(
        system_prompt=system_prompt,
        tool_memo_search=tool_memo_search,
        tool_session_search=tool_session_search,
        tool_web_search=tool_web_search,
    )


def _session_assistant_level(
    model: ModelRef | None = None,
    system_prompt: str | None = None,
    tool_memo_search: bool | None = None,
    tool_session_search: bool | None = None,
    tool_web_search: bool | None = None,
) -> SessionAssistantLevel:
    return SessionAssistantLevel(
        model=model,
        system_prompt=system_prompt,
        tool_memo_search=tool_memo_search,
        tool_session_search=tool_session_search,
        tool_web_search=tool_web_search,
    )


def _servers() -> Table:
    return schema.metadata.tables["llm_servers"]


def _models() -> Table:
    return schema.metadata.tables["models"]


def _insert_user(
    engine: Engine,
    *,
    user_id: int,
    username: str,
    rp_language: str | None = None,
    preferred_language: str | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.users.insert().values(
                id=user_id,
                username=username,
                password_hash="not-a-real-hash",
                role=Role.ROLEPLAYER,
                is_enabled=True,
                rp_language=rp_language,
                preferred_language=preferred_language,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_character(
    engine: Engine,
    *,
    character_id: int,
    user_id: int,
    name: str,
    archived_at: str | None = None,
    system_prompt: str | None = None,
    tool_memo_search: bool | None = None,
    tool_session_search: bool | None = None,
    tool_web_search: bool | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.characters.insert().values(
                id=character_id,
                user_id=user_id,
                name=name,
                sheet="",
                archived_at=archived_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
                model_server_id=None,
                model_name=None,
                system_prompt=system_prompt,
                tool_memo_search=tool_memo_search,
                tool_session_search=tool_session_search,
                tool_web_search=tool_web_search,
            )
        )


def _insert_session(
    engine: Engine,
    *,
    session_id: int,
    user_id: int,
    character_id: int,
    archived_at: str | None = None,
    model_server_id: int | None = None,
    model_name: str | None = None,
    system_prompt: str | None = None,
    tool_memo_search: bool | None = None,
    tool_session_search: bool | None = None,
    tool_web_search: bool | None = None,
    rp_language: str | None = None,
    preferred_language: str | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.insert().values(
                id=session_id,
                user_id=user_id,
                character_id=character_id,
                setup_id=None,
                last_used_at=TIMESTAMP,
                archived_at=archived_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
                model_server_id=model_server_id,
                model_name=model_name,
                system_prompt=system_prompt,
                tool_memo_search=tool_memo_search,
                tool_session_search=tool_session_search,
                tool_web_search=tool_web_search,
                rp_language=rp_language,
                preferred_language=preferred_language,
            )
        )


def _set_session_model(engine: Engine, session_id: int, server_id: int | None, name: str | None) -> None:
    with engine.begin() as connection:
        connection.execute(
            update(schema.sessions)
            .where(schema.sessions.c.id == session_id)
            .values(model_server_id=server_id, model_name=name)
        )


def _insert_server(engine: Engine, *, server_id: int, name: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            _servers()
            .insert()
            .values(
                id=server_id,
                name=name,
                kind="llamaswap",
                base_url=f"http://llm-{server_id}.test:8080",
                api_key_ref=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_model(engine: Engine, *, model_id: int, server_id: int, name: str, enabled: bool) -> None:
    with engine.begin() as connection:
        connection.execute(
            _models()
            .insert()
            .values(
                id=model_id,
                server_id=server_id,
                model_name=name,
                is_enabled=enabled,
                is_embedding_designated=False,
                embedding_dim=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _seed_disabled_only(engine: Engine) -> None:
    """Registry rows exist, but nothing is enabled."""
    _insert_server(engine, server_id=SERVER_A, name="server A")
    _insert_model(engine, model_id=MODEL_A_OFF, server_id=SERVER_A, name=MODEL_A_OFF_NAME, enabled=False)


def _seed_enabled(engine: Engine) -> None:
    """Server B's model is first enabled (D7); server A has one enabled and one disabled model."""
    _insert_server(engine, server_id=SERVER_B, name="server B")
    _insert_server(engine, server_id=SERVER_A, name="server A")
    _insert_model(engine, model_id=MODEL_A, server_id=SERVER_A, name=MODEL_A_NAME, enabled=True)
    _insert_model(engine, model_id=MODEL_B, server_id=SERVER_B, name=MODEL_B_NAME, enabled=True)
    _insert_model(engine, model_id=MODEL_A_OFF, server_id=SERVER_A, name=MODEL_A_OFF_NAME, enabled=False)


def _session_row(engine: Engine, session_id: int) -> RowMapping:
    with engine.connect() as connection:
        return (
            connection.execute(select(schema.sessions).where(schema.sessions.c.id == session_id))
            .mappings()
            .one()
        )


def _configuration(engine: Engine, user_id: int, session_id: int) -> SessionConfiguration:
    with engine.connect() as connection:
        result = get_session_configuration(connection, user_id, session_id)
        assert not connection.in_transaction()
        return result


def _use(engine: Engine, user_id: int, session_id: int) -> EnabledChatModel:
    with engine.connect() as connection:
        return resolve_model_for_use(connection, user_id, session_id)


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """Two owners: user A with both languages set and a character; user B with a session of
    their own. No LLM rows; tests add the sessions and registry they need."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="alice", rp_language="Japanese", preferred_language="English")
    _insert_user(db_engine, user_id=USER_B, username="bob", rp_language="German", preferred_language="Dutch")
    _insert_character(
        db_engine,
        character_id=CHAR_A,
        user_id=USER_A,
        name="Aria",
        system_prompt="C",
        tool_memo_search=False,
    )
    _insert_character(db_engine, character_id=CHAR_B, user_id=USER_B, name="Bram", system_prompt="B's prompt")
    _insert_session(
        db_engine,
        session_id=SESSION_B,
        user_id=USER_B,
        character_id=CHAR_B,
        model_server_id=SERVER_A,
        model_name=MODEL_A_NAME,
    )
    return db_engine


# --------------------------------------------------------------------------- DoD-1


def test_config_level_members_are_the_four_wire_strings__S017_003_DoD1() -> None:
    """DoD-1 / 003.context — the level enum serialises as the Wire contract's plain strings."""
    assert {member.value for member in ConfigLevel} == {"session", "character", "user", "default"}
    assert ConfigLevel.SESSION == "session"
    assert ConfigLevel.CHARACTER == "character"
    assert ConfigLevel.USER == "user"
    assert ConfigLevel.DEFAULT == "default"


def test_a_character_prompt_with_no_session_prompt_is_inherited__S017_003_DoD1() -> None:
    """DoD-1 / US-059.AC-2 / US-108.AC-1 — character "C", session none."""
    result = resolve_assistant_chain(_character_level(system_prompt="C"), _session_assistant_level())

    assert isinstance(result, AssistantConfiguration)
    assert _setting(result.system_prompt) == (None, "C", CHARACTER, "C", CHARACTER)


def test_a_session_prompt_wins_over_the_character_prompt__S017_003_DoD1() -> None:
    """DoD-1 / US-060.AC-1 — session "S" wins; inherited is still the character's "C"."""
    result = resolve_assistant_chain(
        _character_level(system_prompt="C"), _session_assistant_level(system_prompt="S")
    )

    assert _setting(result.system_prompt) == ("S", "C", CHARACTER, "S", SESSION)


def test_no_prompt_at_either_level_resolves_all_null__S017_003_DoD1() -> None:
    """DoD-1 / US-059.AC-1 — neither level sets a prompt: value, level, inherited and
    inherited_level are all null (and so is the session's own)."""
    result = resolve_assistant_chain(_character_level(), _session_assistant_level())

    assert _setting(result.system_prompt) == (None, None, None, None, None)


def test_a_session_prompt_with_no_character_prompt__S017_003_DoD1() -> None:
    """DoD-1 / Wire level rules — session "S" over nothing: level session, inherited null."""
    result = resolve_assistant_chain(_character_level(), _session_assistant_level(system_prompt="S"))

    assert _setting(result.system_prompt) == ("S", None, None, "S", SESSION)


# --------------------------------------------------------------------------- DoD-2


def test_tools_resolve_independently__S017_003_DoD2() -> None:
    """DoD-2 / US-062.AC-1 / US-062.AC-2 / D5 — character sets memo search off only; session sets
    web search off and session search on."""
    result = resolve_assistant_chain(
        _character_level(tool_memo_search=False),
        _session_assistant_level(tool_web_search=False, tool_session_search=True),
    )

    assert _setting(result.tool_memo_search) == (None, False, CHARACTER, False, CHARACTER)
    assert _setting(result.tool_session_search) == (True, True, DEFAULT, True, SESSION)
    assert _setting(result.tool_web_search) == (False, True, DEFAULT, False, SESSION)


def test_a_tool_set_by_neither_level_is_on_by_default__S017_003_DoD2() -> None:
    """DoD-2 / D5 — no level sets any tool: each is on, level default, inherited true from
    default, session null."""
    result = resolve_assistant_chain(_character_level(), _session_assistant_level())

    for setting in (result.tool_memo_search, result.tool_session_search, result.tool_web_search):
        assert _setting(setting) == (None, True, DEFAULT, True, DEFAULT)


@pytest.mark.parametrize(("character_value", "session_value"), [(False, True), (True, False)])
def test_a_session_tool_override_beats_a_contrary_character_override__S017_003_DoD2(
    character_value: bool, session_value: bool
) -> None:
    """DoD-2 / D5 — for the same tool, the session's value wins over the character's opposite."""
    result = resolve_assistant_chain(
        _character_level(
            tool_memo_search=character_value,
            tool_session_search=character_value,
            tool_web_search=character_value,
        ),
        _session_assistant_level(
            tool_memo_search=session_value,
            tool_session_search=session_value,
            tool_web_search=session_value,
        ),
    )

    for setting in (result.tool_memo_search, result.tool_session_search, result.tool_web_search):
        assert _setting(setting) == (session_value, character_value, CHARACTER, session_value, SESSION)


# --------------------------------------------------------------------------- DoD-3


@pytest.mark.parametrize(
    "model",
    [
        pytest.param(ModelRef(server_id=SERVER_A, model_name=MODEL_A_NAME), id="captured-pair"),
        pytest.param(ModelRef(server_id=MISSING_SERVER_ID, model_name="ghost-chat"), id="dead-reference"),
        pytest.param(None, id="none"),
    ],
)
def test_the_model_is_the_sessions_captured_reference_unchanged__S017_003_DoD3(model: ModelRef | None) -> None:
    """DoD-3 / R4 / D8 — the assistant chain passes the session's model through unchanged, a
    reference naming no server included, and none stays none (no substitution)."""
    result = resolve_assistant_chain(
        _character_level(system_prompt="C", tool_memo_search=False),
        _session_assistant_level(model=model),
    )

    assert _model_pair(result.model) == _model_pair(model)


def test_the_character_input_has_no_model_or_language_field__S017_003_DoD3() -> None:
    """DoD-3 / R4 / D8 / US-139.AC-1 — the character-level input type cannot carry a model or a
    language, so a character model cannot reach the result."""
    names = {field.name for field in dataclasses.fields(CharacterAssistantLevel)}

    assert "model" not in names
    assert "rp_language" not in names
    assert "preferred_language" not in names
    assert not any(name.startswith("model") for name in names)


# --------------------------------------------------------------------------- DoD-4


def test_user_languages_are_inherited_when_the_session_sets_none__S017_003_DoD4() -> None:
    """DoD-4 / US-061.AC-1 / US-108.AC-2 — user "Japanese" / "English", session none / none."""
    result = resolve_language_chain(
        UserLanguageLevel(rp_language="Japanese", preferred_language="English"),
        SessionLanguageLevel(rp_language=None, preferred_language=None),
    )

    assert isinstance(result, LanguageConfiguration)
    assert _setting(result.rp_language) == (None, "Japanese", USER, "Japanese", USER)
    assert _setting(result.preferred_language) == (None, "English", USER, "English", USER)


def test_a_session_rp_language_wins_and_preferred_stays_the_users__S017_003_DoD4() -> None:
    """DoD-4 / US-061.AC-2 — session RP language "French" wins; preferred is still the user's."""
    result = resolve_language_chain(
        UserLanguageLevel(rp_language="Japanese", preferred_language="English"),
        SessionLanguageLevel(rp_language="French", preferred_language=None),
    )

    assert _setting(result.rp_language) == ("French", "Japanese", USER, "French", SESSION)
    assert _setting(result.preferred_language) == (None, "English", USER, "English", USER)


def test_no_language_at_either_level_resolves_null__S017_003_DoD4() -> None:
    """DoD-4 — neither level sets a language: value and level null for each."""
    result = resolve_language_chain(
        UserLanguageLevel(rp_language=None, preferred_language=None),
        SessionLanguageLevel(rp_language=None, preferred_language=None),
    )

    assert _setting(result.rp_language) == (None, None, None, None, None)
    assert _setting(result.preferred_language) == (None, None, None, None, None)


def test_a_session_language_with_no_user_default__S017_003_DoD4() -> None:
    """DoD-4 / Wire level rules — a session value over no user default: level session,
    inherited null."""
    result = resolve_language_chain(
        UserLanguageLevel(rp_language=None, preferred_language=None),
        SessionLanguageLevel(rp_language=None, preferred_language="Spanish"),
    )

    assert _setting(result.rp_language) == (None, None, None, None, None)
    assert _setting(result.preferred_language) == ("Spanish", None, None, "Spanish", SESSION)


# --------------------------------------------------------------------------- DoD-5


def test_the_two_resolvers_are_distinct_functions__S017_003_DoD5() -> None:
    """DoD-5 / R1 — two functions, not one parameterised one."""
    assert inspect.isfunction(resolve_assistant_chain)
    assert inspect.isfunction(resolve_language_chain)
    assert resolve_assistant_chain is not resolve_language_chain


def test_the_assistant_chain_takes_exactly_a_character_and_a_session__S017_003_DoD5() -> None:
    """DoD-5 / R1 — no user parameter (names frozen in ``## Skeleton``)."""
    parameters = list(inspect.signature(resolve_assistant_chain).parameters)

    assert parameters == ["character", "session"]


def test_the_language_chain_takes_exactly_a_user_and_a_session__S017_003_DoD5() -> None:
    """DoD-5 / R1 — no character parameter (names frozen in ``## Skeleton``)."""
    parameters = list(inspect.signature(resolve_language_chain).parameters)

    assert parameters == ["user", "session"]


def test_the_user_level_input_has_exactly_the_two_languages__S017_003_DoD5() -> None:
    """DoD-5 / R1 — the user level holds no model, prompt or tool."""
    names = {field.name for field in dataclasses.fields(UserLanguageLevel)}

    assert names == {"rp_language", "preferred_language"}


# --------------------------------------------------------------------------- DoD-6


def _seed_dod6(engine: Engine) -> None:
    """User A (Japanese / English), character A (prompt "C", memo search off), and session A with
    an RP language override "French" and a captured model (server A's, not first enabled)."""
    _seed_enabled(engine)
    _insert_session(
        engine,
        session_id=SESSION_A,
        user_id=USER_A,
        character_id=CHAR_A,
        model_server_id=SERVER_A,
        model_name=MODEL_A_NAME,
        rp_language="French",
    )


def _assert_dod6_result(result: SessionConfiguration, prompt: str) -> None:
    assert isinstance(result, SessionConfiguration)
    assert _model_pair(result.model) == (SERVER_A, MODEL_A_NAME)
    assert _setting(result.system_prompt) == (None, prompt, CHARACTER, prompt, CHARACTER)
    assert _setting(result.tool_memo_search) == (None, False, CHARACTER, False, CHARACTER)
    assert _setting(result.tool_session_search) == (None, True, DEFAULT, True, DEFAULT)
    assert _setting(result.tool_web_search) == (None, True, DEFAULT, True, DEFAULT)
    assert _setting(result.rp_language) == ("French", "Japanese", USER, "French", SESSION)
    assert _setting(result.preferred_language) == (None, "English", USER, "English", USER)


def test_get_session_configuration_combines_both_chains__S017_003_DoD6(engine: Engine) -> None:
    """DoD-6 / US-059.AC-2 / US-061.AC-2 — the one read applies both chains to the raw rows."""
    _seed_dod6(engine)

    _assert_dod6_result(_configuration(engine, USER_A, SESSION_A), "C")


def test_the_prompt_is_live_and_the_captured_model_is_fixed__S017_003_DoD6(engine: Engine) -> None:
    """DoD-6 / US-059.AC-1 / US-139.AC-1 / R4 — after the character's prompt changes and its model
    columns are set, the same existing session reads the new prompt and the old captured model."""
    _seed_dod6(engine)
    _assert_dod6_result(_configuration(engine, USER_A, SESSION_A), "C")

    with engine.begin() as connection:
        connection.execute(
            update(schema.characters)
            .where(schema.characters.c.id == CHAR_A)
            .values(system_prompt="C2", model_server_id=SERVER_B, model_name=MODEL_B_NAME)
        )

    _assert_dod6_result(_configuration(engine, USER_A, SESSION_A), "C2")


def test_get_session_configuration_writes_nothing__S017_003_DoD6(engine: Engine) -> None:
    """DoD-6 / Interface intent — the read leaves the session row as it was."""
    _seed_dod6(engine)
    before = dict(_session_row(engine, SESSION_A))

    _configuration(engine, USER_A, SESSION_A)

    assert dict(_session_row(engine, SESSION_A)) == before


# --------------------------------------------------------------------------- DoD-7


@pytest.mark.parametrize(
    "session_id",
    [pytest.param(SESSION_B, id="another-users-session"), pytest.param(UNKNOWN_SESSION_ID, id="missing")],
)
def test_another_users_or_a_missing_session_is_not_found__S017_003_DoD7(engine: Engine, session_id: int) -> None:
    """DoD-7 / R5 — both take the same not-found path."""
    with pytest.raises(SessionNotFoundError) as raised:
        _configuration(engine, USER_A, session_id)

    assert raised.value.code == "session_not_found"


def test_an_archived_session_reads_normally__S017_003_DoD7(engine: Engine) -> None:
    """DoD-7 / R6 — archive is not a lock."""
    _insert_session(
        engine,
        session_id=SESSION_A_ARCHIVED,
        user_id=USER_A,
        character_id=CHAR_A,
        archived_at=ARCHIVED_AT,
        system_prompt="S",
    )

    result = _configuration(engine, USER_A, SESSION_A_ARCHIVED)

    assert _setting(result.system_prompt) == ("S", "C", CHARACTER, "S", SESSION)
    assert _setting(result.rp_language) == (None, "Japanese", USER, "Japanese", USER)


def test_a_session_under_an_archived_character_reads_normally__S017_003_DoD7(engine: Engine) -> None:
    """DoD-7 / R6 — the archived character's prompt and tools still apply."""
    _insert_character(
        engine,
        character_id=CHAR_A_ARCHIVED,
        user_id=USER_A,
        name="Old",
        archived_at=ARCHIVED_AT,
        system_prompt="Archived prompt",
        tool_web_search=False,
    )
    _insert_session(
        engine,
        session_id=SESSION_A_UNDER_ARCHIVED_CHARACTER,
        user_id=USER_A,
        character_id=CHAR_A_ARCHIVED,
    )

    result = _configuration(engine, USER_A, SESSION_A_UNDER_ARCHIVED_CHARACTER)

    assert _setting(result.system_prompt) == (None, "Archived prompt", CHARACTER, "Archived prompt", CHARACTER)
    assert _setting(result.tool_web_search) == (None, False, CHARACTER, False, CHARACTER)
    assert _model_pair(result.model) is None


# --------------------------------------------------------------------------- DoD-8 / DoD-9


def _registry_none(engine: Engine) -> None:
    return None


#: (registry seeding, captured pair or None, expected outcome) — the outcome is either an error
#: type or the pair the returned model must name.
USE_CASES: list[Any] = [
    pytest.param(_registry_none, None, NoModelEnabledError, id="nothing-registered-session-null"),
    pytest.param(_registry_none, (SERVER_A, MODEL_A_NAME), NoModelEnabledError, id="nothing-registered-session-pair"),
    pytest.param(_seed_disabled_only, None, NoModelEnabledError, id="only-disabled-session-null"),
    pytest.param(
        _seed_disabled_only, (SERVER_A, MODEL_A_OFF_NAME), NoModelEnabledError, id="only-disabled-session-pair"
    ),
    pytest.param(_seed_enabled, None, ModelNotChosenError, id="enabled-session-null"),
    pytest.param(_seed_enabled, (SERVER_A, MODEL_A_OFF_NAME), ModelNotEnabledError, id="enabled-session-disabled"),
    pytest.param(_seed_enabled, (MISSING_SERVER_ID, "ghost-chat"), ModelNotEnabledError, id="enabled-session-dead"),
    pytest.param(_seed_enabled, (SERVER_A, MODEL_A_NAME), (SERVER_A, MODEL_A_NAME), id="enabled-session-enabled"),
]


def _seed_use_case(engine: Engine, registry: Callable[[Engine], None], pair: tuple[int, str] | None) -> None:
    registry(engine)
    _insert_session(engine, session_id=SESSION_A, user_id=USER_A, character_id=CHAR_A)
    if pair is not None:
        _set_session_model(engine, SESSION_A, pair[0], pair[1])


@pytest.mark.parametrize(("registry", "pair", "outcome"), USE_CASES)
def test_resolve_model_for_use_follows_d2s_check_order__S017_003_DoD8(
    engine: Engine,
    registry: Callable[[Engine], None],
    pair: tuple[int, str] | None,
    outcome: Any,
) -> None:
    """DoD-8 / D2 / US-107.AC-1 / US-107.AC-2 — nothing enabled outranks the session's state;
    then NULL -> not chosen; then not enabled; else the session's own model is returned."""
    _seed_use_case(engine, registry, pair)

    if isinstance(outcome, type):
        with pytest.raises(outcome):
            _use(engine, USER_A, SESSION_A)
    else:
        result = _use(engine, USER_A, SESSION_A)
        assert isinstance(result, EnabledChatModel)
        assert (result.server.id, result.model_name) == outcome


@pytest.mark.parametrize(
    ("registry", "pair", "code"),
    [
        pytest.param(_registry_none, None, "no_model_enabled", id="no-model-enabled"),
        pytest.param(_registry_none, (SERVER_A, MODEL_A_NAME), "no_model_enabled", id="no-model-enabled-with-pair"),
        pytest.param(_seed_enabled, None, "model_not_chosen", id="model-not-chosen"),
    ],
)
def test_the_two_new_refusals_carry_their_codes_and_an_empty_detail__S017_003_DoD8(
    engine: Engine, registry: Callable[[Engine], None], pair: tuple[int, str] | None, code: str
) -> None:
    """DoD-8 / D2 / Wire failures — ``no_model_enabled`` and ``model_not_chosen`` with ``{}``."""
    _seed_use_case(engine, registry, pair)

    with pytest.raises((NoModelEnabledError, ModelNotChosenError)) as raised:
        _use(engine, USER_A, SESSION_A)

    assert raised.value.code == code
    assert dict(raised.value.detail) == {}


@pytest.mark.parametrize(
    "pair",
    [
        pytest.param((SERVER_A, MODEL_A_OFF_NAME), id="disabled-model"),
        pytest.param((MISSING_SERVER_ID, "ghost-chat"), id="missing-server"),
    ],
)
def test_a_not_enabled_captured_model_reports_level_session__S017_003_DoD8(
    engine: Engine, pair: tuple[int, str]
) -> None:
    """DoD-8 / D3 — the detail names the captured pair with a decimal-string server id and level
    ``session``, while another model is enabled."""
    _seed_use_case(engine, _seed_enabled, pair)

    with pytest.raises(ModelNotEnabledError) as raised:
        _use(engine, USER_A, SESSION_A)

    assert raised.value.code == "model_not_enabled"
    assert dict(raised.value.detail) == {
        "server_id": str(pair[0]),
        "model_name": pair[1],
        "level": "session",
    }


@pytest.mark.parametrize(
    "session_id",
    [pytest.param(SESSION_B, id="another-users-session"), pytest.param(UNKNOWN_SESSION_ID, id="missing")],
)
@pytest.mark.parametrize("registry", [_registry_none, _seed_enabled], ids=["no-model-enabled", "models-enabled"])
def test_resolve_model_for_use_on_another_users_session_is_not_found__S017_003_DoD8(
    engine: Engine, session_id: int, registry: Callable[[Engine], None]
) -> None:
    """DoD-8 / R5 — another user's (or a missing) session is not found, whatever the registry
    holds; user B's session holds an enabled pair in the models-enabled case."""
    registry(engine)

    with pytest.raises(SessionNotFoundError) as raised:
        _use(engine, USER_A, session_id)

    assert raised.value.code == "session_not_found"


@pytest.mark.parametrize(("registry", "pair", "outcome"), USE_CASES)
def test_resolve_model_for_use_never_writes_the_session_row__S017_003_DoD9(
    engine: Engine,
    registry: Callable[[Engine], None],
    pair: tuple[int, str] | None,
    outcome: Any,
) -> None:
    """DoD-9 / R4 — the whole session row is identical before and after every DoD-8 case."""
    _seed_use_case(engine, registry, pair)
    before = dict(_session_row(engine, SESSION_A))

    try:
        _use(engine, USER_A, SESSION_A)
    except (NoModelEnabledError, ModelNotChosenError, ModelNotEnabledError):
        pass

    assert dict(_session_row(engine, SESSION_A)) == before


def test_resolve_model_for_use_never_falls_back_to_the_first_enabled_model__S017_003_DoD9(
    engine: Engine,
) -> None:
    """DoD-9 / R4 — the session captured server A's model while server B's is first enabled: the
    result is server A's; a disabled capture raises rather than returning server B's."""
    _seed_use_case(engine, _seed_enabled, (SERVER_A, MODEL_A_NAME))

    result = _use(engine, USER_A, SESSION_A)
    assert (result.server.id, result.model_name) == (SERVER_A, MODEL_A_NAME)

    _set_session_model(engine, SESSION_A, SERVER_A, MODEL_A_OFF_NAME)
    with pytest.raises(ModelNotEnabledError):
        _use(engine, USER_A, SESSION_A)
    assert (
        _session_row(engine, SESSION_A)["model_server_id"],
        _session_row(engine, SESSION_A)["model_name"],
    ) == (SERVER_A, MODEL_A_OFF_NAME)


# --------------------------------------------------------------------------- DoD-10


def _module_tree() -> ast.Module:
    return ast.parse(inspect.getsource(configuration_module))


def test_imports_from_app_services_only_llm_registry_and_d12s_names__S017_003_DoD10() -> None:
    """DoD-10 / D12 — the only service module imported is ``llm_registry``, and only the names
    D12 lists."""
    imported: set[str] = set()
    offenders: list[str] = []
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.ImportFrom):
            if node.level > 0:
                offenders.append(f"relative import, level {node.level}")
                continue
            module = node.module or ""
            if module == "app.services.llm_registry":
                imported.update(alias.name for alias in node.names)
            elif module == "app.services" or module.startswith("app.services."):
                offenders.append(f"from {module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "app.services" or alias.name.startswith("app.services."):
                    offenders.append(f"import {alias.name}")

    assert offenders == []
    assert imported <= D12_NAMES, imported - D12_NAMES


def test_the_configuration_service_has_no_fastapi_import__S017_003_DoD10() -> None:
    """DoD-10 — services import no ``fastapi``."""
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert node.module != "fastapi" and not node.module.startswith("fastapi.")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "fastapi" and not alias.name.startswith("fastapi.")
