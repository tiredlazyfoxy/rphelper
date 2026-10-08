"""Tests for the model capture in ``start_session`` — feature 017, step 002.

Every expected value comes from ``docs/plans/017.session-configuration/002.registry-reads-and-capture.md``
(Interface intent, DoD-4 .. DoD-10), ``002.context.md`` and the feature ``context.md``:
**D1** (inside the creation transaction, after the character and setup checks: the character's
own pair is captured as-is and unvalidated; otherwise the first enabled model; otherwise NULL),
**D7** (the enabled set and its order: ``llm_servers.id`` then ``models.id``), **R4** (the capture
is not approved against the registry; prompt and tools stay live, so nothing else is copied) and
011's error codes (``character_not_found``, ``setup_not_found``, ``setup_archived``).

Binding comes from ``status.md`` ``## Skeleton`` -> Step 002: ``start_session(connection,
generator, user_id, character_id, setup_id=None) -> RpSession`` (eight fields, unchanged). The
captured model is not part of ``RpSession`` (D9), so it is read back with a raw select on
``sessions``.

Fixtures (``002.context.md`` "Test fixtures"): the schema comes from ``create_all`` on the
per-test engine; users, characters (with or without the model pair, prompt and tools), setups,
``llm_servers`` and ``models`` rows are raw-inserted; ``start_session`` is called directly with a
real ``SnowflakeGenerator``. 011's test helpers are not imported; nothing is added to
``conftest.py``. Tests are suffixed ``__S017_002_DoD<n>``.
"""

import dataclasses
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import Engine, RowMapping, Table, func, select, update

from app.db import schema
from app.errors import CharacterNotFoundError, DomainError, SetupArchivedError, SetupNotFoundError
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services.sessions import RpSession, start_session

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

USER_A = 101
USER_B = 202

CHAR_PLAIN = 1_001  # user A, no model, no prompt, no tools
CHAR_CONFIGURED = 1_002  # user A, configured per test
CHAR_B = 2_001  # user B, carries a model pair

SETUP_A = 3_001  # user A, under CHAR_PLAIN
SETUP_A_ARCHIVED = 3_002  # user A, under CHAR_PLAIN, archived
SETUP_A_OTHER_CHARACTER = 3_003  # user A, under CHAR_CONFIGURED
SETUP_B = 4_001  # user B, under CHAR_B
UNKNOWN_CHARACTER_ID = 8_888_888_888
UNKNOWN_SETUP_ID = 9_999_999_999

#: Registry ids where server-id order and models.id order disagree (002.context.md):
#: server A has the larger server id, but its model has the smaller ``models.id``.
#: The expected first enabled model is server B's.
SERVER_B = 5_100
SERVER_A = 5_200
MODEL_A = 61_001
MODEL_A_NAME = "alpha-chat"
MODEL_B = 62_001
MODEL_B_NAME = "beta-chat"
#: A disabled model on server B.
MODEL_B_OFF = 62_500
MODEL_B_OFF_NAME = "beta-off"
#: A server id that names no ``llm_servers`` row.
MISSING_SERVER_ID = 7_777_777
#: A server added later in DoD-8 with the smallest id of all, so its model becomes first enabled.
SERVER_EARLY = 5_001
MODEL_EARLY = 63_001
MODEL_EARLY_NAME = "early-chat"

#: The six configuration columns ``sessions`` gains besides the model pair (step 001).
NOT_COPIED_COLUMNS = (
    "system_prompt",
    "tool_memo_search",
    "tool_session_search",
    "tool_web_search",
    "rp_language",
    "preferred_language",
)

#: RpSession's eight fields, in order (011's frozen value).
RP_SESSION_FIELDS = (
    "id",
    "character_id",
    "setup_id",
    "setup_name",
    "archived_at",
    "last_used_at",
    "created_at",
    "updated_at",
)


# --------------------------------------------------------------------------- helpers


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
                sheet="",
                archived_at=None,
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


def _set_character_model(engine: Engine, character_id: int, server_id: int | None, name: str | None) -> None:
    """A raw update of the character's model pair (the character write is step 004's)."""
    with engine.begin() as connection:
        connection.execute(
            update(schema.characters)
            .where(schema.characters.c.id == character_id)
            .values(model_server_id=server_id, model_name=name)
        )


def _insert_setup(
    engine: Engine,
    *,
    setup_id: int,
    user_id: int,
    character_id: int,
    name: str,
    archived_at: str | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.setups.insert().values(
                id=setup_id,
                user_id=user_id,
                character_id=character_id,
                name=name,
                description="",
                archived_at=archived_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
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


def _seed_two_enabled(engine: Engine) -> None:
    """Two servers, one enabled model each, ids disagreeing (first enabled = server B's)."""
    _insert_server(engine, server_id=SERVER_B, name="server B")
    _insert_server(engine, server_id=SERVER_A, name="server A")
    _insert_model(engine, model_id=MODEL_A, server_id=SERVER_A, name=MODEL_A_NAME, enabled=True)
    _insert_model(engine, model_id=MODEL_B, server_id=SERVER_B, name=MODEL_B_NAME, enabled=True)


def _start(
    engine: Engine,
    generator: SnowflakeGenerator,
    user_id: int,
    character_id: int,
    setup_id: int | None = None,
) -> RpSession:
    with engine.connect() as connection:
        return start_session(connection, generator, user_id, character_id, setup_id)


def _session_row(engine: Engine, session_id: int) -> RowMapping:
    with engine.connect() as connection:
        return (
            connection.execute(select(schema.sessions).where(schema.sessions.c.id == session_id))
            .mappings()
            .one()
        )


def _captured(engine: Engine, session_id: int) -> tuple[Any, Any]:
    row = _session_row(engine, session_id)
    return (row["model_server_id"], row["model_name"])


def _count_sessions(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(schema.sessions)).scalar_one())


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database: two owners, their characters and setups; no LLM rows."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="alice", rp_language="English", preferred_language="Russian")
    _insert_user(db_engine, user_id=USER_B, username="bob")
    _insert_character(db_engine, character_id=CHAR_PLAIN, user_id=USER_A, name="Aria")
    _insert_character(db_engine, character_id=CHAR_B, user_id=USER_B, name="Bram")
    _insert_setup(db_engine, setup_id=SETUP_A, user_id=USER_A, character_id=CHAR_PLAIN, name="Tavern")
    _insert_setup(
        db_engine,
        setup_id=SETUP_A_ARCHIVED,
        user_id=USER_A,
        character_id=CHAR_PLAIN,
        name="Retired",
        archived_at=TIMESTAMP,
    )
    _insert_setup(db_engine, setup_id=SETUP_B, user_id=USER_B, character_id=CHAR_B, name="Bob's scene")
    return db_engine


@pytest.fixture
def generator() -> SnowflakeGenerator:
    return SnowflakeGenerator(node_id=1)


# --------------------------------------------------------------------------- DoD-4


def test_no_character_model_and_nothing_enabled_captures_null__S017_002_DoD4(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-4 / D1 case 3 — no character model, no model enabled on the instance: the session is
    created with both model columns NULL."""
    created = _start(engine, generator, USER_A, CHAR_PLAIN)

    assert _captured(engine, created.id) == (None, None)


def test_only_disabled_models_still_captures_null__S017_002_DoD4(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-4 / D1 case 3 — registry rows exist, but none is enabled: still NULL (R4: no fallback
    to a disabled model)."""
    _insert_server(engine, server_id=SERVER_B, name="server B")
    _insert_model(engine, model_id=MODEL_B_OFF, server_id=SERVER_B, name=MODEL_B_OFF_NAME, enabled=False)

    created = _start(engine, generator, USER_A, CHAR_PLAIN)

    assert _captured(engine, created.id) == (None, None)


def test_the_returned_value_keeps_rp_sessions_eight_fields__S017_002_DoD4(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-4 — the returned ``RpSession`` is unchanged in shape: exactly the eight 011 fields."""
    created = _start(engine, generator, USER_A, CHAR_PLAIN)

    assert isinstance(created, RpSession)
    assert tuple(field.name for field in dataclasses.fields(created)) == RP_SESSION_FIELDS
    assert created.character_id == CHAR_PLAIN
    assert created.setup_id is None


def test_the_returned_value_keeps_its_shape_when_a_model_is_captured__S017_002_DoD4(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-4 — capturing a model adds nothing to the returned value (D9)."""
    _seed_two_enabled(engine)

    created = _start(engine, generator, USER_A, CHAR_PLAIN, SETUP_A)

    assert tuple(field.name for field in dataclasses.fields(created)) == RP_SESSION_FIELDS
    assert created.setup_id == SETUP_A


# --------------------------------------------------------------------------- DoD-5


def test_no_character_model_captures_the_first_enabled_model__S017_002_DoD5(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-5 / D1 case 2 / D7 / US-106.AC-1 — the first enabled model in D7 order is server B's
    (smaller server id), not server A's (smaller ``models.id``)."""
    _seed_two_enabled(engine)

    created = _start(engine, generator, USER_A, CHAR_PLAIN)

    assert _captured(engine, created.id) == (SERVER_B, MODEL_B_NAME)


def test_first_enabled_capture_skips_a_disabled_lower_model__S017_002_DoD5(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-5 / D7 — with server B's model disabled, the first enabled is server A's."""
    _seed_two_enabled(engine)
    with engine.begin() as connection:
        connection.execute(update(_models()).where(_models().c.id == MODEL_B).values(is_enabled=False))

    created = _start(engine, generator, USER_A, CHAR_PLAIN)

    assert _captured(engine, created.id) == (SERVER_A, MODEL_A_NAME)


def test_first_enabled_capture_also_applies_with_a_setup__S017_002_DoD5(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-5 — the capture happens whether or not a setup is chosen."""
    _seed_two_enabled(engine)

    created = _start(engine, generator, USER_A, CHAR_PLAIN, SETUP_A)

    assert _captured(engine, created.id) == (SERVER_B, MODEL_B_NAME)


# --------------------------------------------------------------------------- DoD-6


def test_an_enabled_character_model_is_captured_over_the_first_enabled__S017_002_DoD6(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-6 / D1 case 1 / US-139.AC-2 / US-059.AC-2 — the character's pair (server A's model,
    which is not first enabled) is what the new row holds."""
    _seed_two_enabled(engine)
    _insert_character(
        engine,
        character_id=CHAR_CONFIGURED,
        user_id=USER_A,
        name="Cass",
        model_server_id=SERVER_A,
        model_name=MODEL_A_NAME,
    )

    created = _start(engine, generator, USER_A, CHAR_CONFIGURED)

    assert _captured(engine, created.id) == (SERVER_A, MODEL_A_NAME)


# --------------------------------------------------------------------------- DoD-7


CHARACTER_PAIRS_NOT_ENABLED: list[Any] = [
    pytest.param((SERVER_B, MODEL_B_OFF_NAME), id="disabled-model"),
    pytest.param((MISSING_SERVER_ID, "ghost-chat"), id="missing-server"),
]


@pytest.mark.parametrize("pair", CHARACTER_PAIRS_NOT_ENABLED)
@pytest.mark.parametrize("others_enabled", [False, True], ids=["nothing-else-enabled", "others-enabled"])
def test_a_not_enabled_character_model_is_captured_unchanged__S017_002_DoD7(
    engine: Engine, generator: SnowflakeGenerator, pair: tuple[int, str], others_enabled: bool
) -> None:
    """DoD-7 / R4 / D1 — the character's pair names a disabled model or a server that does not
    exist; creation succeeds and the row holds that pair unchanged, with or without other models
    enabled (no validation at creation, no fallback to the first enabled)."""
    _insert_server(engine, server_id=SERVER_B, name="server B")
    _insert_model(engine, model_id=MODEL_B_OFF, server_id=SERVER_B, name=MODEL_B_OFF_NAME, enabled=False)
    if others_enabled:
        _insert_server(engine, server_id=SERVER_A, name="server A")
        _insert_model(engine, model_id=MODEL_A, server_id=SERVER_A, name=MODEL_A_NAME, enabled=True)
        _insert_model(engine, model_id=MODEL_B, server_id=SERVER_B, name=MODEL_B_NAME, enabled=True)
    server_id, model_name = pair
    _insert_character(
        engine,
        character_id=CHAR_CONFIGURED,
        user_id=USER_A,
        name="Cass",
        model_server_id=server_id,
        model_name=model_name,
    )
    before = _count_sessions(engine)

    created = _start(engine, generator, USER_A, CHAR_CONFIGURED)

    assert _count_sessions(engine) == before + 1
    assert created.character_id == CHAR_CONFIGURED
    assert _captured(engine, created.id) == (server_id, model_name)


# --------------------------------------------------------------------------- DoD-8


def test_a_captured_model_is_fixed_and_a_later_character_model_reaches_only_new_sessions__S017_002_DoD8(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-8 / US-139.AC-1 / US-139.AC-2 / US-059.AC-1 — the first session captured the only
    enabled model; after the character is given another model and another model becomes first
    enabled, the first session's row is unchanged and a new session holds the character's pair."""
    _insert_server(engine, server_id=SERVER_A, name="server A")
    _insert_model(engine, model_id=MODEL_A, server_id=SERVER_A, name=MODEL_A_NAME, enabled=True)

    first = _start(engine, generator, USER_A, CHAR_PLAIN)
    assert _captured(engine, first.id) == (SERVER_A, MODEL_A_NAME)

    _insert_server(engine, server_id=SERVER_B, name="server B")
    _insert_model(engine, model_id=MODEL_B, server_id=SERVER_B, name=MODEL_B_NAME, enabled=True)
    _insert_server(engine, server_id=SERVER_EARLY, name="server early")
    _insert_model(engine, model_id=MODEL_EARLY, server_id=SERVER_EARLY, name=MODEL_EARLY_NAME, enabled=True)
    _set_character_model(engine, CHAR_PLAIN, SERVER_B, MODEL_B_NAME)

    second = _start(engine, generator, USER_A, CHAR_PLAIN)

    assert _captured(engine, first.id) == (SERVER_A, MODEL_A_NAME)
    assert _captured(engine, second.id) == (SERVER_B, MODEL_B_NAME)


def test_a_cleared_character_model_lets_new_sessions_take_the_new_first_enabled__S017_002_DoD8(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-8 / US-139.AC-1 — a session captured from the character keeps it after the character's
    model is cleared; a later session takes the first enabled model at its own creation."""
    _seed_two_enabled(engine)
    _set_character_model(engine, CHAR_PLAIN, SERVER_A, MODEL_A_NAME)
    first = _start(engine, generator, USER_A, CHAR_PLAIN)

    _set_character_model(engine, CHAR_PLAIN, None, None)
    second = _start(engine, generator, USER_A, CHAR_PLAIN)

    assert _captured(engine, first.id) == (SERVER_A, MODEL_A_NAME)
    assert _captured(engine, second.id) == (SERVER_B, MODEL_B_NAME)


# --------------------------------------------------------------------------- DoD-9


@pytest.mark.parametrize("with_model", [False, True], ids=["character-without-model", "character-with-model"])
def test_prompt_tools_and_languages_are_not_copied_onto_the_session__S017_002_DoD9(
    engine: Engine, generator: SnowflakeGenerator, with_model: bool
) -> None:
    """DoD-9 / D1 / R4 — the character's system prompt and all three tool switches are set, the
    user has both languages set, yet the new session's ``system_prompt``, three ``tool_*``,
    ``rp_language`` and ``preferred_language`` are all NULL (they resolve live)."""
    _seed_two_enabled(engine)
    _insert_character(
        engine,
        character_id=CHAR_CONFIGURED,
        user_id=USER_A,
        name="Cass",
        model_server_id=SERVER_A if with_model else None,
        model_name=MODEL_A_NAME if with_model else None,
        system_prompt="Stay in character. Be terse.",
        tool_memo_search=False,
        tool_session_search=True,
        tool_web_search=False,
    )

    created = _start(engine, generator, USER_A, CHAR_CONFIGURED)

    row = _session_row(engine, created.id)
    for column in NOT_COPIED_COLUMNS:
        assert row[column] is None, column


# --------------------------------------------------------------------------- DoD-10


def _registry_none(engine: Engine) -> None:
    return None


def _registry_enabled(engine: Engine) -> None:
    _seed_two_enabled(engine)


REGISTRY_STATES: list[Any] = [
    pytest.param(_registry_none, id="no-model-enabled"),
    pytest.param(_registry_enabled, id="models-enabled"),
]

REFUSALS: list[Any] = [
    pytest.param(
        CHAR_B, None, CharacterNotFoundError, "character_not_found", id="another-users-character"
    ),
    pytest.param(
        UNKNOWN_CHARACTER_ID, None, CharacterNotFoundError, "character_not_found", id="unknown-character"
    ),
    pytest.param(
        CHAR_PLAIN, UNKNOWN_SETUP_ID, SetupNotFoundError, "setup_not_found", id="unknown-setup"
    ),
    pytest.param(
        CHAR_PLAIN, SETUP_B, SetupNotFoundError, "setup_not_found", id="another-users-setup"
    ),
    pytest.param(
        CHAR_PLAIN, SETUP_A_OTHER_CHARACTER, SetupNotFoundError, "setup_not_found", id="setup-of-another-character"
    ),
    pytest.param(
        CHAR_PLAIN, SETUP_A_ARCHIVED, SetupArchivedError, "setup_archived", id="archived-setup"
    ),
]


@pytest.mark.parametrize("registry", REGISTRY_STATES)
@pytest.mark.parametrize(("character_id", "setup_id", "error", "code"), REFUSALS)
def test_a_refused_creation_inserts_nothing_and_keeps_011s_codes__S017_002_DoD10(
    engine: Engine,
    generator: SnowflakeGenerator,
    registry: Callable[[Engine], None],
    character_id: int,
    setup_id: int | None,
    error: type[DomainError],
    code: str,
) -> None:
    """DoD-10 / 011 D12 — the character check and the setup checks refuse with 011's errors and
    codes, whatever the registry holds (so no registry state changes the outcome), and no
    session row is inserted."""
    _insert_character(
        engine,
        character_id=CHAR_CONFIGURED,
        user_id=USER_A,
        name="Cass",
        model_server_id=SERVER_A,
        model_name=MODEL_A_NAME,
    )
    _insert_setup(
        engine, setup_id=SETUP_A_OTHER_CHARACTER, user_id=USER_A, character_id=CHAR_CONFIGURED, name="Elsewhere"
    )
    _set_character_model(engine, CHAR_B, SERVER_B, MODEL_B_NAME)
    registry(engine)
    before = _count_sessions(engine)

    with pytest.raises(error) as raised:
        _start(engine, generator, USER_A, character_id, setup_id)

    assert raised.value.code == code
    assert _count_sessions(engine) == before == 0
