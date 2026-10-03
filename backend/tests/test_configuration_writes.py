"""Tests for the session, character and user configuration writes in
``app.services.configuration`` — feature 017, step 004.

Every expected value comes from ``docs/plans/017.session-configuration/004.configuration-writes.md``
(Interface intent, DoD-1 .. DoD-11), ``004.context.md`` and the feature ``context.md``: the Wire
contract's level rules (``system_prompt`` and each tool inherit from ``character``, a tool no level
sets is on with level ``default``, the languages inherit from ``user``, ``level`` is ``session``
exactly when ``session`` is non-null), **D9** (the character's other columns are untouched),
**D10** (set-time check inside the same transaction; failure writes nothing; level ``session`` or
``character`` by caller, never ``user``), **D11** (``updated_at`` bumped in the fixed-width form,
``last_used_at`` never; an empty update writes nothing), **D14**, **R1**, **R5**, **R6** and
**US-139.AC-1**. No resolver is called to compute an expectation.

Bindings come from ``status.md`` ``## Skeleton`` -> Step 004 (``CharacterConfiguration``,
``UserSettings``, ``update_session_configuration``, ``get_character_configuration``,
``update_character_configuration``, ``get_user_settings``, ``update_user_settings``; all update
arguments keyword-only, ``UNSET`` by default), Step 003 (``ConfigLevel``, ``ModelRef``,
``SessionConfiguration``, ``get_session_configuration``) and Step 002 (``start_session``).

Fixtures: schema from ``create_all`` on the per-test engine; users, characters, sessions,
``llm_servers`` and ``models`` are raw-inserted. Nothing is added to ``conftest.py``. Tests are
suffixed ``__S017_004_DoD<n>``.
"""

import re
from typing import Any

import pytest
from sqlalchemy import Engine, RowMapping, Table, select, update

from app.db import schema
from app.errors import CharacterNotFoundError, ModelNotEnabledError, SessionNotFoundError
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services.configuration import (
    CharacterConfiguration,
    ConfigLevel,
    ModelRef,
    SessionConfiguration,
    UserSettings,
    get_character_configuration,
    get_session_configuration,
    get_user_settings,
    update_character_configuration,
    update_session_configuration,
    update_user_settings,
)
from app.services.sessions import start_session

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
LAST_USED_AT = "2026-01-02T00:00:00.000000+00:00"
LAST_LOGIN_AT = "2026-01-03T00:00:00.000000+00:00"
ARCHIVED_AT = "2026-02-01T00:00:00.000000+00:00"

#: ``YYYY-MM-DDTHH:MM:SS.ffffff+00:00`` (004.context "Timestamps").
FIXED_WIDTH = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00$")

USER_A = 101
USER_B = 202

CHAR_A = 1_001
CHAR_A_ARCHIVED = 1_002
CHAR_B = 2_001
UNKNOWN_CHARACTER_ID = 8_888_888_888

SESSION_A = 3_001
SESSION_A2 = 3_002
SESSION_A_ARCHIVED = 3_003
SESSION_B = 4_001
UNKNOWN_SESSION_ID = 9_999_999_999

#: Registry ids: server-id order and models.id order disagree (feature "Registry fixtures").
SERVER_B = 5_100
SERVER_A = 5_200
MODEL_A = 61_001
MODEL_A_NAME = "alpha-chat"
MODEL_B = 62_001
MODEL_B_NAME = "beta-chat"
MODEL_A_OFF = 61_500
MODEL_A_OFF_NAME = "alpha-off"
MISSING_SERVER_ID = 7_777_777

SESSION = ConfigLevel.SESSION
CHARACTER = ConfigLevel.CHARACTER
USER = ConfigLevel.USER
DEFAULT = ConfigLevel.DEFAULT

#: Not-enabled references: a disabled model on an existing server, and a server that does not exist.
NOT_ENABLED_REFS = [
    pytest.param((SERVER_A, MODEL_A_OFF_NAME), id="disabled-model"),
    pytest.param((MISSING_SERVER_ID, "ghost-chat"), id="no-such-server"),
]


# --------------------------------------------------------------------------- helpers


def _setting(setting: Any) -> tuple[Any, Any, Any, Any, Any]:
    """The five Wire-contract fields of a resolved setting, in order."""
    return (setting.session, setting.inherited, setting.inherited_level, setting.value, setting.level)


def _model_pair(model: ModelRef | None) -> tuple[int, str] | None:
    return None if model is None else (model.server_id, model.model_name)


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
                password_hash=f"hash-of-{username}",
                role=Role.ROLEPLAYER,
                is_enabled=True,
                last_login_at=LAST_LOGIN_AT,
                rp_language=rp_language,
                preferred_language=preferred_language,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _set_user_languages(engine: Engine, user_id: int, rp_language: str | None, preferred: str | None) -> None:
    with engine.begin() as connection:
        connection.execute(
            update(schema.users)
            .where(schema.users.c.id == user_id)
            .values(rp_language=rp_language, preferred_language=preferred)
        )


def _insert_character(
    engine: Engine,
    *,
    character_id: int,
    user_id: int,
    name: str,
    sheet: str = "",
    archived_at: str | None = None,
    model_server_id: int | None = None,
    model_name: str | None = None,
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
                sheet=sheet,
                archived_at=archived_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
                model_server_id=model_server_id,
                model_name=model_name,
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
                last_used_at=LAST_USED_AT,
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


def _row(engine: Engine, table: Table, row_id: int) -> dict[str, Any]:
    with engine.connect() as connection:
        mapping: RowMapping = connection.execute(select(table).where(table.c.id == row_id)).mappings().one()
        return dict(mapping)


def _session_row(engine: Engine, session_id: int) -> dict[str, Any]:
    return _row(engine, schema.sessions, session_id)


def _character_row(engine: Engine, character_id: int) -> dict[str, Any]:
    return _row(engine, schema.characters, character_id)


def _user_row(engine: Engine, user_id: int) -> dict[str, Any]:
    return _row(engine, schema.users, user_id)


def _all_session_rows(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(select(schema.sessions).order_by(schema.sessions.c.id)).mappings().all()
        return [dict(row) for row in rows]


def _without(row: dict[str, Any], *columns: str) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in columns}


def _configuration(engine: Engine, user_id: int, session_id: int) -> SessionConfiguration:
    with engine.connect() as connection:
        return get_session_configuration(connection, user_id, session_id)


def _update_session(engine: Engine, user_id: int, session_id: int, **changes: Any) -> SessionConfiguration:
    with engine.connect() as connection:
        return update_session_configuration(connection, user_id, session_id, **changes)


def _update_character(engine: Engine, user_id: int, character_id: int, **changes: Any) -> CharacterConfiguration:
    with engine.connect() as connection:
        return update_character_configuration(connection, user_id, character_id, **changes)


def _character_configuration(engine: Engine, user_id: int, character_id: int) -> CharacterConfiguration:
    with engine.connect() as connection:
        return get_character_configuration(connection, user_id, character_id)


def _update_user(engine: Engine, user_id: int, **changes: Any) -> UserSettings:
    with engine.connect() as connection:
        return update_user_settings(connection, user_id, **changes)


def _user_settings(engine: Engine, user_id: int) -> UserSettings:
    with engine.connect() as connection:
        return get_user_settings(connection, user_id)


def _assert_bumped(value: Any) -> None:
    assert isinstance(value, str)
    assert FIXED_WIDTH.match(value), value
    assert value > TIMESTAMP


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """User A (no language defaults) with character A (prompt "C", memo search off, no model) and
    session A (captured server A's model, session search off, preferred language "Italian");
    user B (German / Dutch) with character B and session B. Registry: server B's model and server
    A's ``alpha-chat`` enabled, server A's ``alpha-off`` disabled."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="alice")
    _insert_user(db_engine, user_id=USER_B, username="bob", rp_language="German", preferred_language="Dutch")
    _insert_server(db_engine, server_id=SERVER_B, name="server B")
    _insert_server(db_engine, server_id=SERVER_A, name="server A")
    _insert_model(db_engine, model_id=MODEL_A, server_id=SERVER_A, name=MODEL_A_NAME, enabled=True)
    _insert_model(db_engine, model_id=MODEL_B, server_id=SERVER_B, name=MODEL_B_NAME, enabled=True)
    _insert_model(db_engine, model_id=MODEL_A_OFF, server_id=SERVER_A, name=MODEL_A_OFF_NAME, enabled=False)
    _insert_character(
        db_engine,
        character_id=CHAR_A,
        user_id=USER_A,
        name="Aria",
        sheet="Aria's sheet",
        system_prompt="C",
        tool_memo_search=False,
    )
    _insert_character(
        db_engine,
        character_id=CHAR_B,
        user_id=USER_B,
        name="Bram",
        sheet="Bram's sheet",
        system_prompt="B's prompt",
        model_server_id=SERVER_B,
        model_name=MODEL_B_NAME,
    )
    _insert_session(
        db_engine,
        session_id=SESSION_A,
        user_id=USER_A,
        character_id=CHAR_A,
        model_server_id=SERVER_A,
        model_name=MODEL_A_NAME,
        tool_session_search=False,
        preferred_language="Italian",
    )
    _insert_session(
        db_engine,
        session_id=SESSION_B,
        user_id=USER_B,
        character_id=CHAR_B,
        model_server_id=SERVER_B,
        model_name=MODEL_B_NAME,
        system_prompt="B's session prompt",
    )
    return db_engine


# --------------------------------------------------------------------------- DoD-1


def test_an_enabled_model_is_written_and_reported__S017_004_DoD1(engine: Engine) -> None:
    """DoD-1 / US-105.AC-1 — the session's captured model becomes the supplied enabled pair; the
    returned configuration and a later read both report it."""
    result = _update_session(engine, USER_A, SESSION_A, model=ModelRef(server_id=SERVER_B, model_name=MODEL_B_NAME))

    assert isinstance(result, SessionConfiguration)
    assert _model_pair(result.model) == (SERVER_B, MODEL_B_NAME)
    assert _model_pair(_configuration(engine, USER_A, SESSION_A).model) == (SERVER_B, MODEL_B_NAME)


def test_the_written_model_persists_on_a_fresh_connection__S017_004_DoD1(engine: Engine) -> None:
    """DoD-1 / US-105.AC-2 — committed: a new connection reads the pair from the row."""
    with engine.connect() as connection:
        update_session_configuration(
            connection, USER_A, SESSION_A, model=ModelRef(server_id=SERVER_B, model_name=MODEL_B_NAME)
        )

    with engine.connect() as fresh:
        assert _model_pair(get_session_configuration(fresh, USER_A, SESSION_A).model) == (SERVER_B, MODEL_B_NAME)
    row = _session_row(engine, SESSION_A)
    assert (row["model_server_id"], row["model_name"]) == (SERVER_B, MODEL_B_NAME)


# --------------------------------------------------------------------------- DoD-2


@pytest.mark.parametrize("pair", NOT_ENABLED_REFS)
def test_a_not_enabled_model_raises_with_level_session__S017_004_DoD2(
    engine: Engine, pair: tuple[int, str]
) -> None:
    """DoD-2 / D10 — ``model_not_enabled`` with the decimal-string server id and level ``session``."""
    with pytest.raises(ModelNotEnabledError) as raised:
        _update_session(engine, USER_A, SESSION_A, model=ModelRef(server_id=pair[0], model_name=pair[1]))

    assert raised.value.code == "model_not_enabled"
    assert dict(raised.value.detail) == {"server_id": str(pair[0]), "model_name": pair[1], "level": "session"}


@pytest.mark.parametrize("pair", NOT_ENABLED_REFS)
def test_a_not_enabled_model_writes_nothing_of_the_request__S017_004_DoD2(
    engine: Engine, pair: tuple[int, str]
) -> None:
    """DoD-2 / D10 — the same call also carried a prompt: neither the model, nor the prompt, nor
    ``updated_at`` changed (the whole row is unchanged)."""
    before = _session_row(engine, SESSION_A)

    with pytest.raises(ModelNotEnabledError):
        _update_session(
            engine,
            USER_A,
            SESSION_A,
            model=ModelRef(server_id=pair[0], model_name=pair[1]),
            system_prompt="S",
        )

    after = _session_row(engine, SESSION_A)
    assert (after["model_server_id"], after["model_name"]) == (SERVER_A, MODEL_A_NAME)
    assert after["system_prompt"] is None
    assert after["updated_at"] == TIMESTAMP
    assert after == before


# --------------------------------------------------------------------------- DoD-3


def test_supplying_only_a_prompt_leaves_everything_else_unchanged__S017_004_DoD3(engine: Engine) -> None:
    """DoD-3 / US-060.AC-1 — ``system_prompt="S"`` is written and wins; the captured model, the
    tools and the languages are as they were."""
    before = _session_row(engine, SESSION_A)

    result = _update_session(engine, USER_A, SESSION_A, system_prompt="S")

    after = _session_row(engine, SESSION_A)
    assert after["system_prompt"] == "S"
    assert _without(after, "system_prompt", "updated_at") == _without(before, "system_prompt", "updated_at")
    assert _setting(result.system_prompt) == ("S", "C", CHARACTER, "S", SESSION)
    assert _model_pair(result.model) == (SERVER_A, MODEL_A_NAME)
    assert _setting(result.tool_memo_search) == (None, False, CHARACTER, False, CHARACTER)
    assert _setting(result.tool_session_search) == (False, True, DEFAULT, False, SESSION)
    assert _setting(result.tool_web_search) == (None, True, DEFAULT, True, DEFAULT)
    assert _setting(result.preferred_language) == ("Italian", None, None, "Italian", SESSION)


def test_clearing_the_prompt_falls_back_to_the_characters__S017_004_DoD3(engine: Engine) -> None:
    """DoD-3 / R1 — ``system_prompt=None`` clears the session's own value; the resolved prompt is
    the character's again."""
    _update_session(engine, USER_A, SESSION_A, system_prompt="S")

    result = _update_session(engine, USER_A, SESSION_A, system_prompt=None)

    assert _session_row(engine, SESSION_A)["system_prompt"] is None
    assert _setting(result.system_prompt) == (None, "C", CHARACTER, "C", CHARACTER)
    reread = _configuration(engine, USER_A, SESSION_A)
    assert _setting(reread.system_prompt) == (None, "C", CHARACTER, "C", CHARACTER)


def test_a_tool_value_overrides_and_none_restores_inheritance__S017_004_DoD3(engine: Engine) -> None:
    """DoD-3 / US-062.AC-2 / R1 — memo search on beats the character's off, web search off beats
    the default; ``None`` then restores the character's and the default respectively."""
    result = _update_session(engine, USER_A, SESSION_A, tool_memo_search=True, tool_web_search=False)

    assert _setting(result.tool_memo_search) == (True, False, CHARACTER, True, SESSION)
    assert _setting(result.tool_web_search) == (False, True, DEFAULT, False, SESSION)
    assert _setting(result.tool_session_search) == (False, True, DEFAULT, False, SESSION)

    result = _update_session(engine, USER_A, SESSION_A, tool_memo_search=None, tool_web_search=None)

    assert _setting(result.tool_memo_search) == (None, False, CHARACTER, False, CHARACTER)
    assert _setting(result.tool_web_search) == (None, True, DEFAULT, True, DEFAULT)
    assert _setting(result.tool_session_search) == (False, True, DEFAULT, False, SESSION)

    result = _update_session(engine, USER_A, SESSION_A, tool_session_search=None)

    assert _setting(result.tool_session_search) == (None, True, DEFAULT, True, DEFAULT)
    row = _session_row(engine, SESSION_A)
    assert (row["tool_memo_search"], row["tool_session_search"], row["tool_web_search"]) == (None, None, None)
    assert _setting(result.system_prompt) == (None, "C", CHARACTER, "C", CHARACTER)


def test_a_language_value_overrides_and_none_restores_inheritance__S017_004_DoD3(engine: Engine) -> None:
    """DoD-3 / US-061.AC-2 / R1 — with user defaults Japanese / English: a session RP language
    wins; clearing either restores the user's."""
    _set_user_languages(engine, USER_A, "Japanese", "English")

    result = _update_session(engine, USER_A, SESSION_A, rp_language="French")

    assert _setting(result.rp_language) == ("French", "Japanese", USER, "French", SESSION)
    assert _setting(result.preferred_language) == ("Italian", "English", USER, "Italian", SESSION)

    result = _update_session(engine, USER_A, SESSION_A, rp_language=None, preferred_language=None)

    assert _setting(result.rp_language) == (None, "Japanese", USER, "Japanese", USER)
    assert _setting(result.preferred_language) == (None, "English", USER, "English", USER)
    row = _session_row(engine, SESSION_A)
    assert (row["rp_language"], row["preferred_language"]) == (None, None)
    assert (row["model_server_id"], row["model_name"]) == (SERVER_A, MODEL_A_NAME)


# --------------------------------------------------------------------------- DoD-4


def test_an_update_bumps_updated_at_and_not_last_used_at__S017_004_DoD4(engine: Engine) -> None:
    """DoD-4 / D11 — ``updated_at`` moves to a later fixed-width value; ``last_used_at`` stays."""
    _update_session(engine, USER_A, SESSION_A, system_prompt="S")

    row = _session_row(engine, SESSION_A)
    _assert_bumped(row["updated_at"])
    assert row["last_used_at"] == LAST_USED_AT


def test_a_model_update_bumps_updated_at_and_not_last_used_at__S017_004_DoD4(engine: Engine) -> None:
    """DoD-4 / D11 — the same bookkeeping for a model write."""
    _update_session(engine, USER_A, SESSION_A, model=ModelRef(server_id=SERVER_B, model_name=MODEL_B_NAME))

    row = _session_row(engine, SESSION_A)
    _assert_bumped(row["updated_at"])
    assert row["last_used_at"] == LAST_USED_AT


def test_an_update_with_nothing_supplied_writes_nothing__S017_004_DoD4(engine: Engine) -> None:
    """DoD-4 / D11 — the whole row is unchanged, and the current configuration is returned."""
    before = _session_row(engine, SESSION_A)

    result = _update_session(engine, USER_A, SESSION_A)

    assert _session_row(engine, SESSION_A) == before
    assert isinstance(result, SessionConfiguration)
    assert _model_pair(result.model) == (SERVER_A, MODEL_A_NAME)
    assert _setting(result.system_prompt) == (None, "C", CHARACTER, "C", CHARACTER)
    assert _setting(result.tool_memo_search) == (None, False, CHARACTER, False, CHARACTER)
    assert _setting(result.tool_session_search) == (False, True, DEFAULT, False, SESSION)
    assert _setting(result.tool_web_search) == (None, True, DEFAULT, True, DEFAULT)
    assert _setting(result.rp_language) == (None, None, None, None, None)
    assert _setting(result.preferred_language) == ("Italian", None, None, "Italian", SESSION)


# --------------------------------------------------------------------------- DoD-5


def test_an_archived_session_updates_normally__S017_004_DoD5(engine: Engine) -> None:
    """DoD-5 / R6 — archive is not a lock: the prompt and the model are written."""
    _insert_session(
        engine,
        session_id=SESSION_A_ARCHIVED,
        user_id=USER_A,
        character_id=CHAR_A,
        archived_at=ARCHIVED_AT,
        model_server_id=SERVER_A,
        model_name=MODEL_A_NAME,
    )

    result = _update_session(
        engine,
        USER_A,
        SESSION_A_ARCHIVED,
        system_prompt="S",
        model=ModelRef(server_id=SERVER_B, model_name=MODEL_B_NAME),
    )

    assert _setting(result.system_prompt) == ("S", "C", CHARACTER, "S", SESSION)
    assert _model_pair(result.model) == (SERVER_B, MODEL_B_NAME)
    row = _session_row(engine, SESSION_A_ARCHIVED)
    assert (row["system_prompt"], row["model_server_id"], row["model_name"]) == ("S", SERVER_B, MODEL_B_NAME)
    assert row["archived_at"] == ARCHIVED_AT


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"system_prompt": "S", "tool_web_search": False, "rp_language": "French"}, id="settings"),
        pytest.param({"model": ModelRef(server_id=SERVER_A, model_name=MODEL_A_NAME)}, id="enabled-model"),
        pytest.param({"model": ModelRef(server_id=SERVER_A, model_name=MODEL_A_OFF_NAME)}, id="disabled-model"),
        pytest.param({}, id="nothing-supplied"),
    ],
)
@pytest.mark.parametrize(
    "session_id",
    [pytest.param(SESSION_B, id="another-users-session"), pytest.param(UNKNOWN_SESSION_ID, id="missing")],
)
def test_another_users_or_a_missing_session_is_not_found_and_nothing_is_written__S017_004_DoD5(
    engine: Engine, session_id: int, changes: dict[str, Any]
) -> None:
    """DoD-5 / R5 / 004.context — the owner check comes first (before any model check, and also
    with nothing supplied); no session row changes."""
    before = _all_session_rows(engine)

    with pytest.raises(SessionNotFoundError) as raised:
        _update_session(engine, USER_A, session_id, **changes)

    assert raised.value.code == "session_not_found"
    assert _all_session_rows(engine) == before


# --------------------------------------------------------------------------- DoD-6


def test_a_character_update_writes_model_prompt_and_tool__S017_004_DoD6(engine: Engine) -> None:
    """DoD-6 / US-059.AC-2 — the returned and the re-read character configuration report them."""
    result = _update_character(
        engine,
        USER_A,
        CHAR_A,
        model=ModelRef(server_id=SERVER_A, model_name=MODEL_A_NAME),
        system_prompt="P",
        tool_web_search=False,
    )

    for configuration in (result, _character_configuration(engine, USER_A, CHAR_A)):
        assert isinstance(configuration, CharacterConfiguration)
        assert _model_pair(configuration.model) == (SERVER_A, MODEL_A_NAME)
        assert configuration.system_prompt == "P"
        assert configuration.tool_web_search is False
        assert configuration.tool_memo_search is False
        assert configuration.tool_session_search is None

    row = _character_row(engine, CHAR_A)
    assert (row["model_server_id"], row["model_name"], row["system_prompt"], row["tool_web_search"]) == (
        SERVER_A,
        MODEL_A_NAME,
        "P",
        False,
    )


def test_a_new_session_resolves_the_characters_prompt_and_web_search__S017_004_DoD6(engine: Engine) -> None:
    """DoD-6 / US-059.AC-2 / US-062.AC-1 — a session started after the character update shows the
    character's prompt and web search off, both at level ``character``."""
    _update_character(
        engine,
        USER_A,
        CHAR_A,
        model=ModelRef(server_id=SERVER_A, model_name=MODEL_A_NAME),
        system_prompt="P",
        tool_web_search=False,
    )

    with engine.connect() as connection:
        created = start_session(connection, SnowflakeGenerator(node_id=1), USER_A, CHAR_A)

    result = _configuration(engine, USER_A, created.id)
    assert _setting(result.system_prompt) == (None, "P", CHARACTER, "P", CHARACTER)
    assert _setting(result.tool_web_search) == (None, False, CHARACTER, False, CHARACTER)


# --------------------------------------------------------------------------- DoD-7


def test_a_character_model_change_touches_no_session_row__S017_004_DoD7(engine: Engine) -> None:
    """DoD-7 / US-139.AC-1 / R4 — every existing session of the character (and every other
    session) is unchanged, captured model and ``updated_at`` included."""
    _insert_session(
        engine,
        session_id=SESSION_A2,
        user_id=USER_A,
        character_id=CHAR_A,
        model_server_id=SERVER_B,
        model_name=MODEL_B_NAME,
    )
    before = _all_session_rows(engine)

    _update_character(
        engine,
        USER_A,
        CHAR_A,
        model=ModelRef(server_id=SERVER_B, model_name=MODEL_B_NAME),
        system_prompt="P",
        tool_memo_search=True,
    )
    _update_character(engine, USER_A, CHAR_A, model=ModelRef(server_id=SERVER_A, model_name=MODEL_A_NAME))

    after = _all_session_rows(engine)
    assert after == before
    session_a = _session_row(engine, SESSION_A)
    assert (session_a["model_server_id"], session_a["model_name"], session_a["updated_at"]) == (
        SERVER_A,
        MODEL_A_NAME,
        TIMESTAMP,
    )


def test_model_none_clears_the_characters_pair__S017_004_DoD7(engine: Engine) -> None:
    """DoD-7 / D10 — ``model=None`` sets both columns NULL; sessions are still untouched."""
    _update_character(engine, USER_A, CHAR_A, model=ModelRef(server_id=SERVER_B, model_name=MODEL_B_NAME))
    sessions_before = _all_session_rows(engine)

    result = _update_character(engine, USER_A, CHAR_A, model=None)

    assert result.model is None
    assert _character_configuration(engine, USER_A, CHAR_A).model is None
    row = _character_row(engine, CHAR_A)
    assert (row["model_server_id"], row["model_name"]) == (None, None)
    assert row["system_prompt"] == "C"
    assert _all_session_rows(engine) == sessions_before


# --------------------------------------------------------------------------- DoD-8


@pytest.mark.parametrize("pair", NOT_ENABLED_REFS)
def test_a_not_enabled_character_model_raises_with_level_character__S017_004_DoD8(
    engine: Engine, pair: tuple[int, str]
) -> None:
    """DoD-8 / D10 / backend-structure error table — level ``character``, never ``user``."""
    with pytest.raises(ModelNotEnabledError) as raised:
        _update_character(engine, USER_A, CHAR_A, model=ModelRef(server_id=pair[0], model_name=pair[1]))

    assert raised.value.code == "model_not_enabled"
    assert dict(raised.value.detail) == {"server_id": str(pair[0]), "model_name": pair[1], "level": "character"}
    assert raised.value.detail["level"] != "user"


@pytest.mark.parametrize("pair", NOT_ENABLED_REFS)
def test_a_not_enabled_character_model_writes_nothing__S017_004_DoD8(engine: Engine, pair: tuple[int, str]) -> None:
    """DoD-8 / D10 — the prompt and tool carried with it are not written either; no row changes."""
    character_before = _character_row(engine, CHAR_A)
    sessions_before = _all_session_rows(engine)

    with pytest.raises(ModelNotEnabledError):
        _update_character(
            engine,
            USER_A,
            CHAR_A,
            model=ModelRef(server_id=pair[0], model_name=pair[1]),
            system_prompt="P",
            tool_web_search=False,
        )

    assert _character_row(engine, CHAR_A) == character_before
    assert _all_session_rows(engine) == sessions_before


# --------------------------------------------------------------------------- DoD-9


def test_a_character_update_leaves_name_sheet_archived_at_and_bumps_updated_at__S017_004_DoD9(
    engine: Engine,
) -> None:
    """DoD-9 / D9 / D11 — only the configuration columns and ``updated_at`` move."""
    before = _character_row(engine, CHAR_A)

    _update_character(engine, USER_A, CHAR_A, system_prompt="P", tool_session_search=False)

    after = _character_row(engine, CHAR_A)
    assert (after["name"], after["sheet"], after["archived_at"]) == ("Aria", "Aria's sheet", None)
    assert (after["system_prompt"], after["tool_session_search"]) == ("P", False)
    _assert_bumped(after["updated_at"])
    assert _without(after, "system_prompt", "tool_session_search", "updated_at") == _without(
        before, "system_prompt", "tool_session_search", "updated_at"
    )


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"system_prompt": "P", "tool_web_search": False}, id="settings"),
        pytest.param({"model": ModelRef(server_id=SERVER_A, model_name=MODEL_A_NAME)}, id="enabled-model"),
        pytest.param({"model": ModelRef(server_id=SERVER_A, model_name=MODEL_A_OFF_NAME)}, id="disabled-model"),
        pytest.param({"model": None}, id="clear-model"),
        pytest.param({}, id="nothing-supplied"),
    ],
)
@pytest.mark.parametrize(
    "character_id",
    [pytest.param(CHAR_B, id="another-users-character"), pytest.param(UNKNOWN_CHARACTER_ID, id="missing")],
)
def test_another_users_or_a_missing_character_is_not_found_on_update__S017_004_DoD9(
    engine: Engine, character_id: int, changes: dict[str, Any]
) -> None:
    """DoD-9 / R5 / 004.context — the owner check comes first; user B's character is unchanged."""
    before = _character_row(engine, CHAR_B)

    with pytest.raises(CharacterNotFoundError) as raised:
        _update_character(engine, USER_A, character_id, **changes)

    assert raised.value.code == "character_not_found"
    assert _character_row(engine, CHAR_B) == before


@pytest.mark.parametrize(
    "character_id",
    [pytest.param(CHAR_B, id="another-users-character"), pytest.param(UNKNOWN_CHARACTER_ID, id="missing")],
)
def test_another_users_or_a_missing_character_is_not_found_on_read__S017_004_DoD9(
    engine: Engine, character_id: int
) -> None:
    """DoD-9 / R5 — the owner-scoped read takes the same not-found path."""
    with pytest.raises(CharacterNotFoundError):
        _character_configuration(engine, USER_A, character_id)


def test_an_archived_character_reads_and_updates_normally__S017_004_DoD9(engine: Engine) -> None:
    """DoD-9 / R6 — archive is not a lock; ``archived_at`` is kept."""
    _insert_character(
        engine,
        character_id=CHAR_A_ARCHIVED,
        user_id=USER_A,
        name="Old",
        archived_at=ARCHIVED_AT,
        system_prompt="Old prompt",
    )

    read = _character_configuration(engine, USER_A, CHAR_A_ARCHIVED)
    assert read.system_prompt == "Old prompt"
    assert read.model is None

    result = _update_character(
        engine,
        USER_A,
        CHAR_A_ARCHIVED,
        model=ModelRef(server_id=SERVER_B, model_name=MODEL_B_NAME),
        tool_memo_search=False,
    )

    assert _model_pair(result.model) == (SERVER_B, MODEL_B_NAME)
    assert result.tool_memo_search is False
    assert result.system_prompt == "Old prompt"
    row = _character_row(engine, CHAR_A_ARCHIVED)
    assert row["archived_at"] == ARCHIVED_AT
    assert (row["model_server_id"], row["model_name"], row["tool_memo_search"]) == (SERVER_B, MODEL_B_NAME, False)


# --------------------------------------------------------------------------- DoD-10


def test_user_settings_persist_and_resolve_at_level_user__S017_004_DoD10(engine: Engine) -> None:
    """DoD-10 / US-058.AC-1 / US-061.AC-1 / R5 — both languages are written and read back; a session
    with no language override resolves both at level ``user``; user B is untouched."""
    user_b_before = _user_row(engine, USER_B)
    _insert_session(engine, session_id=SESSION_A2, user_id=USER_A, character_id=CHAR_A)

    result = _update_user(engine, USER_A, rp_language="Japanese", preferred_language="English")

    assert isinstance(result, UserSettings)
    assert (result.rp_language, result.preferred_language) == ("Japanese", "English")
    read = _user_settings(engine, USER_A)
    assert (read.rp_language, read.preferred_language) == ("Japanese", "English")
    configuration = _configuration(engine, USER_A, SESSION_A2)
    assert _setting(configuration.rp_language) == (None, "Japanese", USER, "Japanese", USER)
    assert _setting(configuration.preferred_language) == (None, "English", USER, "English", USER)
    assert _user_row(engine, USER_B) == user_b_before


def test_clearing_one_user_language_leaves_the_other__S017_004_DoD10(engine: Engine) -> None:
    """DoD-10 / R5 — ``preferred_language=None`` clears only that one; user B is untouched."""
    user_b_before = _user_row(engine, USER_B)
    _update_user(engine, USER_A, rp_language="Japanese", preferred_language="English")

    result = _update_user(engine, USER_A, preferred_language=None)

    assert (result.rp_language, result.preferred_language) == ("Japanese", None)
    read = _user_settings(engine, USER_A)
    assert (read.rp_language, read.preferred_language) == ("Japanese", None)
    other = _user_settings(engine, USER_B)
    assert (other.rp_language, other.preferred_language) == ("German", "Dutch")
    assert _user_row(engine, USER_B) == user_b_before


# --------------------------------------------------------------------------- DoD-11


def test_a_user_settings_update_touches_no_other_users_column__S017_004_DoD11(engine: Engine) -> None:
    """DoD-11 / D11 / D14 — identity columns unchanged; ``updated_at`` bumped, fixed-width."""
    before = _user_row(engine, USER_A)

    _update_user(engine, USER_A, rp_language="Japanese")

    after = _user_row(engine, USER_A)
    for column in ("username", "password_hash", "role", "is_enabled", "last_login_at"):
        assert after[column] == before[column], column
    assert after["last_login_at"] == LAST_LOGIN_AT
    assert after["rp_language"] == "Japanese"
    _assert_bumped(after["updated_at"])
    assert _without(after, "rp_language", "updated_at") == _without(before, "rp_language", "updated_at")


def test_a_user_settings_update_with_nothing_supplied_writes_nothing__S017_004_DoD11(engine: Engine) -> None:
    """DoD-11 / D11 — the row is unchanged and the current settings are returned."""
    _set_user_languages(engine, USER_A, "Japanese", None)
    before = _user_row(engine, USER_A)

    result = _update_user(engine, USER_A)

    assert _user_row(engine, USER_A) == before
    assert (result.rp_language, result.preferred_language) == ("Japanese", None)
