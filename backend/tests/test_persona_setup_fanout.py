"""Tests for the persona / setup-text fan-out — feature 024, step 006 (DoD-1..7).

Every expected value comes from `docs/plans/024.embedding-lifecycle/006.persona-setup-fanout.md`
(its Interface intent and Definition of done — **DoD-1 pins the new sheet verbatim**), from
`006.context.md` (the test shape and the placement) and from the feature `context.md`:

- **D5** — "changed" means the submitted value **differs from the stored one**; **archived
  sessions are included** in both fan-outs with no archive predicate (U4); the fan-out applies
  **only when N > 0**; creates, name-only edits, an unchanged sheet / description and
  archive / restore do **no vector work at all**;
- **D6** — the composed session text is the character's `sheet`, then the setup's
  `description` when `sessions.setup_id` is not null, then the `settled_entries` text in
  ascending id, joined with exactly `"\\n\\n"`. **Persona and setup lead**;
- **D8** — authoring writes are strict: `NoEmbeddingModelError` (409) and
  `LlmUnreachableError` (502) propagate, the transaction rolls back and **nothing is stored**;
- **D1** — one client and **one** `embed` call per write operation: a fan-out over N sessions
  sends one request carrying N texts;
- **D9** / the **Wire contract** — the shared factory and settings dependencies, and the two
  authoring failure codes on the two PATCH routes.

Bindings come from `## Skeleton` → "Step 006 — frozen interface" (and steps 001 / 002 / 003
for `ensure_vector_tables`, `write_vector` and `SESSION_VEC_TABLE`), and the fake's contract
from `## Tests` → "Step 002 — tests" in `status.md`. Nothing here was derived from the
implementation; no source file was read.

Each test name ends `__S024_006_DoD<n>` with the DoD item it covers.

Mechanics (`context.md` "Test conventions", `006.context.md` "Test shape"):
- a real SQLite file per test (`db_engine`) with `schema.metadata.create_all`; `conftest.py`
  is untouched and every fixture below is file-local;
- users, characters, setups, sessions (**including an archived one, `archived_at` set**) and
  settled messages are raw inserts, every id above 2^60;
- a designated model is raw `llm_servers` + `models` rows at dimension 8 with a null
  `api_key_ref`, so no secret has to resolve;
- the outbound client arrives through the frozen `client_factory=` keyword seam (services) or
  through `dependency_overrides` of the shared `get_llm_client_factory` (the DoD-7 wire
  cases), always using the shared fake in `tests/llm_fakes.py`. No network, and no
  monkeypatching beyond the routers' established `configure_logging` neutralisation;
- pre-existing vectors are written with `002`'s `write_vector` after `001`'s
  `ensure_vector_tables`; `session_vec` is then observed only from the test side, through
  `pragma_table_info`, point lookups and `struct.unpack`.
"""

import struct
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, Table, select, text

from app.config import Settings, get_settings
from app.db import schema
from app.db.search_tables import SESSION_VEC_TABLE, ensure_vector_tables
from app.dependencies import get_llm_client_factory
from app.errors import LlmUnreachableError, NoEmbeddingModelError
from app.ids import SnowflakeGenerator
from app.main import create_app
from app.roles import Role
from app.services.characters import Character, create_character, update_character
from app.services.embedding import write_vector
from app.services.passwords import hash_password
from app.services.setups import Setup, create_setup, update_setup
from tests.llm_fakes import (
    FakeClientFactory,
    embedding_vector,
    fake_factory,
    unreachable_factory,
)

#: The seeded instant, in the project's fixed-width form.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
#: The instant rows seeded already settled carry.
SEEDED_SETTLED_AT = "2025-12-31T00:00:00.000000+00:00"

#: Every id is above 2^60 = 1152921504606846976 (D3 / U6: snowflake ids stay the keys).
USER_A = 1_600_000_000_000_000_001
USER_B = 1_600_000_000_000_000_002

#: `CHAR_C` is DoD-1's character C; `CHAR_LONELY` never gets a session (DoD-3).
CHAR_C = 1_600_000_000_000_000_011
CHAR_LONELY = 1_600_000_000_000_000_012
CHAR_B = 1_600_000_000_000_000_013

SETUP_X = 1_600_000_000_000_000_021
SETUP_Y = 1_600_000_000_000_000_022
#: A setup no session uses (DoD-6's N = 0 case).
SETUP_LONELY = 1_600_000_000_000_000_023

S1 = 1_600_000_000_000_000_031
S2 = 1_600_000_000_000_000_032
S3 = 1_600_000_000_000_000_033
S4 = 1_600_000_000_000_000_034

E1 = 1_600_000_000_000_000_101
E2 = 1_600_000_000_000_000_102
E3 = 1_600_000_000_000_000_103
E4 = 1_600_000_000_000_000_104

SERVER_ID = 1_600_000_000_000_000_201
MODEL_ID = 1_600_000_000_000_000_202

BASE_URL = "http://embedding.test:8080/v1"
MODEL_NAME = "the-designated-embedding-model"

#: The designated dimension in these tests; 8 keeps them fast (`context.md`).
DIMENSION = 8

#: A timeout deliberately unequal to `Settings`' declared default, so it is distinguishable.
PASSED_TIMEOUT = 12.5

#: D6's parts, exactly as stored.
SHEET_OLD = "Short, wiry, loud."
#: DoD-1's new sheet, verbatim from the step file.
SHEET_NEW = "Tall, scarred, soft-spoken."
DESCRIPTION_X = "A smoky tavern on the river road."
DESCRIPTION_Y = "A cliff-top monastery in winter."
DESCRIPTION_LONELY = "An abandoned lighthouse."
#: DoD-5's new description for setup X.
DESCRIPTION_X_NEW = "A rain-soaked harbour at dusk."

TEXT_ALPHA = "Alpha one."
TEXT_BETA = "Beta two."
TEXT_GAMMA = "Gamma three."
TEXT_DELTA = "Delta four."

NAME_OLD = "Aria"
NAME_NEW = "Aria the Quiet"
SETUP_NAME_OLD = "X"
SETUP_NAME_NEW = "X, renamed"

#: Exact float32 values (multiples of 2**-3), so a round-trip compares equal with no tolerance.
VECTOR_V8 = [0.5, -1.5, 2.25, 0.0, 1.0, -0.125, 3.5, -2.0]

NO_EMBEDDING_MODEL = "no_embedding_model"
LLM_UNREACHABLE = "llm_unreachable"


def _composed(sheet: str, description: str | None, entries: list[str]) -> str:
    """D6's session text: persona, then the setup when present, then the settled entries."""
    parts = [sheet] if sheet.strip() else []
    if description is not None and description.strip():
        parts.append(description)
    parts.extend(entry for entry in entries if entry.strip())
    return "\n\n".join(parts)


# --- seeding ---------------------------------------------------------------------------


def _servers() -> Table:
    return schema.metadata.tables["llm_servers"]


def _models() -> Table:
    return schema.metadata.tables["models"]


def _insert_user(engine: Engine, *, user_id: int, username: str, password: str | None = None) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.users.insert().values(
                id=user_id,
                username=username,
                password_hash="not-a-real-hash" if password is None else hash_password(password),
                role=Role.ROLEPLAYER,
                is_enabled=True,
                rp_language=None,
                preferred_language=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_character(engine: Engine, *, character_id: int, user_id: int, name: str, sheet: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.characters.insert().values(
                id=character_id,
                user_id=user_id,
                name=name,
                sheet=sheet,
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_setup(
    engine: Engine, *, setup_id: int, user_id: int, character_id: int, name: str, description: str
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.setups.insert().values(
                id=setup_id,
                user_id=user_id,
                character_id=character_id,
                name=name,
                description=description,
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_session(
    engine: Engine,
    *,
    session_id: int,
    user_id: int = USER_A,
    character_id: int = CHAR_C,
    setup_id: int | None = None,
    archived_at: str | None = None,
) -> None:
    """Raw-insert one `sessions` row. `archived_at` set is U4's archived session."""
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.insert().values(
                id=session_id,
                user_id=user_id,
                character_id=character_id,
                setup_id=setup_id,
                last_used_at=TIMESTAMP,
                archived_at=archived_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_settled_entry(
    engine: Engine, *, message_id: int, session_id: int, body: str, user_id: int = USER_A
) -> None:
    """One record row: `settled_at` set, `related_to` null (`context.md` Vocabulary).

    `kind` is left null: D6 composes the `text` column alone, so no kind vocabulary is invented.
    """
    with engine.begin() as connection:
        connection.execute(
            schema.messages.insert().values(
                id=message_id,
                user_id=user_id,
                session_id=session_id,
                role="user",
                kind=None,
                text=body,
                related_to=None,
                settled_at=SEEDED_SETTLED_AT,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _seed_designation(engine: Engine, *, dim: int | None = DIMENSION) -> None:
    """Raw-insert one server and one enabled, designated model — built without any service."""
    with engine.begin() as connection:
        connection.execute(
            _servers().insert().values(
                id=SERVER_ID,
                name="the embedding server",
                kind="llamaswap",
                base_url=BASE_URL,
                api_key_ref=None,
                last_test_at=None,
                last_test_ok=None,
                last_test_error=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )
        connection.execute(
            _models().insert().values(
                id=MODEL_ID,
                server_id=SERVER_ID,
                model_name=MODEL_NAME,
                is_enabled=True,
                is_embedding_designated=True,
                embedding_dim=dim,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """Two owners, character C (with sessions to come), a session-free character, three setups.

    `create_all` only, so no virtual table exists until a test makes one.
    """
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="alice")
    _insert_user(db_engine, user_id=USER_B, username="bob")
    _insert_character(db_engine, character_id=CHAR_C, user_id=USER_A, name=NAME_OLD, sheet=SHEET_OLD)
    _insert_character(db_engine, character_id=CHAR_LONELY, user_id=USER_A, name="Solo", sheet=SHEET_OLD)
    _insert_character(db_engine, character_id=CHAR_B, user_id=USER_B, name="Brynn", sheet="Persona B.")
    _insert_setup(
        db_engine,
        setup_id=SETUP_X,
        user_id=USER_A,
        character_id=CHAR_C,
        name=SETUP_NAME_OLD,
        description=DESCRIPTION_X,
    )
    _insert_setup(
        db_engine, setup_id=SETUP_Y, user_id=USER_A, character_id=CHAR_C, name="Y", description=DESCRIPTION_Y
    )
    _insert_setup(
        db_engine,
        setup_id=SETUP_LONELY,
        user_id=USER_A,
        character_id=CHAR_C,
        name="Lonely",
        description=DESCRIPTION_LONELY,
    )
    return db_engine


@pytest.fixture
def generator() -> SnowflakeGenerator:
    """One real generator per test, so ids minted within a test never collide."""
    return SnowflakeGenerator(node_id=1)


def _seed_three_sessions_of_the_character(engine: Engine) -> None:
    """DoD-1's shape: S1 active with setup X, S2 **archived**, S3 active with no setup.

    Each has one settled entry, so each composed text is distinct (D6).
    """
    _insert_session(engine, session_id=S1, setup_id=SETUP_X)
    _insert_session(engine, session_id=S2, setup_id=SETUP_X, archived_at=TIMESTAMP)
    _insert_session(engine, session_id=S3, setup_id=None)
    _insert_settled_entry(engine, message_id=E1, session_id=S1, body=TEXT_ALPHA)
    _insert_settled_entry(engine, message_id=E2, session_id=S2, body=TEXT_BETA)
    _insert_settled_entry(engine, message_id=E3, session_id=S3, body=TEXT_GAMMA)


def _seed_four_sessions_of_the_setups(engine: Engine) -> None:
    """DoD-5's shape: S1 active on X, S2 **archived** on X, S3 on Y, S4 with no setup."""
    _insert_session(engine, session_id=S1, setup_id=SETUP_X)
    _insert_session(engine, session_id=S2, setup_id=SETUP_X, archived_at=TIMESTAMP)
    _insert_session(engine, session_id=S3, setup_id=SETUP_Y)
    _insert_session(engine, session_id=S4, setup_id=None)
    _insert_settled_entry(engine, message_id=E1, session_id=S1, body=TEXT_ALPHA)
    _insert_settled_entry(engine, message_id=E2, session_id=S2, body=TEXT_BETA)
    _insert_settled_entry(engine, message_id=E3, session_id=S3, body=TEXT_GAMMA)
    _insert_settled_entry(engine, message_id=E4, session_id=S4, body=TEXT_DELTA)


# --- calling the frozen interface (one connection per call) -------------------------------


def _update_character(
    engine: Engine,
    *,
    character_id: int,
    factory: FakeClientFactory,
    user_id: int = USER_A,
    name: str | None = None,
    sheet: str | None = None,
) -> Character:
    with engine.connect() as connection:
        return update_character(
            connection,
            user_id,
            character_id,
            name,
            sheet,
            client_factory=factory,
            timeout_seconds=PASSED_TIMEOUT,
        )


def _update_setup(
    engine: Engine,
    *,
    setup_id: int,
    factory: FakeClientFactory,
    user_id: int = USER_A,
    name: str | None = None,
    description: str | None = None,
) -> Setup:
    with engine.connect() as connection:
        return update_setup(
            connection,
            user_id,
            setup_id,
            name,
            description,
            client_factory=factory,
            timeout_seconds=PASSED_TIMEOUT,
        )


def _create_character(
    engine: Engine, generator: SnowflakeGenerator, *, name: str, sheet: str, user_id: int = USER_A
) -> Character:
    with engine.connect() as connection:
        return create_character(connection, generator, user_id, name, sheet)


def _create_setup(
    engine: Engine,
    generator: SnowflakeGenerator,
    *,
    character_id: int,
    name: str,
    description: str,
    user_id: int = USER_A,
) -> Setup:
    with engine.connect() as connection:
        return create_setup(connection, generator, user_id, character_id, name, description)


def _preexisting_vector(engine: Engine, session_ids: list[int], vector: list[float]) -> None:
    """Committed `session_vec` rows, made with `001`'s ensure and `002`'s writer."""
    with engine.begin() as connection:
        ensure_vector_tables(connection, DIMENSION)
        for session_id in session_ids:
            write_vector(connection, SESSION_VEC_TABLE, session_id, vector)


# --- observation (tests may query the tables; application code never does) ---------------


def _key_column(connection: Connection, table_name: str) -> str | None:
    """The vec0 table's key column, or `None` when the table does not exist."""
    rows = connection.execute(
        text("SELECT name FROM pragma_table_info(:table_name) WHERE pk = 1"),
        {"table_name": table_name},
    ).all()
    return None if not rows else str(rows[0][0])


def _stored_blob(engine: Engine, session_id: int) -> bytes | None:
    """The raw stored blob for one session id, or `None` when there is no row (or no table)."""
    with engine.connect() as connection:
        key = _key_column(connection, SESSION_VEC_TABLE)
        if key is None:
            return None
        query = text(f"SELECT embedding FROM {SESSION_VEC_TABLE} WHERE {key} = :row_id")
        blob = connection.execute(query, {"row_id": session_id}).scalar_one_or_none()
        return None if blob is None else bytes(blob)


def _stored_vector(engine: Engine, session_id: int) -> list[float] | None:
    blob = _stored_blob(engine, session_id)
    return None if blob is None else list(struct.unpack(f"<{DIMENSION}f", blob))


def _blobs(engine: Engine, session_ids: list[int]) -> dict[int, bytes | None]:
    return {session_id: _stored_blob(engine, session_id) for session_id in session_ids}


def _stored_sheet(engine: Engine, character_id: int) -> str:
    with engine.connect() as connection:
        value = connection.execute(
            select(schema.characters.c.sheet).where(schema.characters.c.id == character_id)
        ).scalar_one()
    return str(value)


def _stored_character_name(engine: Engine, character_id: int) -> str:
    with engine.connect() as connection:
        value = connection.execute(
            select(schema.characters.c.name).where(schema.characters.c.id == character_id)
        ).scalar_one()
    return str(value)


def _stored_description(engine: Engine, setup_id: int) -> str:
    with engine.connect() as connection:
        value = connection.execute(
            select(schema.setups.c.description).where(schema.setups.c.id == setup_id)
        ).scalar_one()
    return str(value)


def _stored_setup_name(engine: Engine, setup_id: int) -> str:
    with engine.connect() as connection:
        value = connection.execute(
            select(schema.setups.c.name).where(schema.setups.c.id == setup_id)
        ).scalar_one()
    return str(value)


# =========================================================================== DoD-1


def test_a_changed_sheet_refreshes_every_session_of_the_character__S024_006_DoD1(engine: Engine) -> None:
    """DoD-1 — US-021.AC-1, US-138.AC-1, U4: character C has S1 (active, setup X), S2
    (**archived**) and S3 (active, no setup), each with a settled entry. Changing the sheet
    leaves each of the three holding the fake's vector for **its own** composed text (D6).

    The archived session is in, because a restored session must not come back silently stale.
    """
    _seed_three_sessions_of_the_character(engine)
    _seed_designation(engine)
    factory = fake_factory(DIMENSION)

    _update_character(engine, character_id=CHAR_C, factory=factory, sheet=SHEET_NEW)

    expected = {
        S1: _composed(SHEET_NEW, DESCRIPTION_X, [TEXT_ALPHA]),
        S2: _composed(SHEET_NEW, DESCRIPTION_X, [TEXT_BETA]),
        S3: _composed(SHEET_NEW, None, [TEXT_GAMMA]),
    }
    for session_id, composed in expected.items():
        assert _stored_vector(engine, session_id) == embedding_vector(composed, DIMENSION)
    assert _stored_sheet(engine, CHAR_C) == SHEET_NEW


def test_each_refreshed_text_begins_with_the_new_sheet__S024_006_DoD1(engine: Engine) -> None:
    """DoD-1 — D6: persona leads. Every text sent to the provider **begins** with the new sheet,
    which is what keeps US-138.AC-2's "similar person" half alive in a long session.
    """
    _seed_three_sessions_of_the_character(engine)
    _seed_designation(engine)
    factory = fake_factory(DIMENSION)

    _update_character(engine, character_id=CHAR_C, factory=factory, sheet=SHEET_NEW)

    assert len(factory.embed_calls) == 1
    _, texts = factory.embed_calls[0]
    assert len(texts) == 3
    for sent in texts:
        assert sent.startswith(SHEET_NEW)
        assert SHEET_OLD not in sent


def test_the_fan_out_is_one_client_and_one_embed_call__S024_006_DoD1(engine: Engine) -> None:
    """DoD-1 — D1: one client per write operation and **one** `embed` call carrying all three
    texts. A per-session loop would record three constructions or three calls and fail here.

    The batch is compared as a set: the plan pins "one call carried all three texts", never
    which order the fan-out iterates them in.
    """
    _seed_three_sessions_of_the_character(engine)
    _seed_designation(engine)
    factory = fake_factory(DIMENSION)

    _update_character(engine, character_id=CHAR_C, factory=factory, sheet=SHEET_NEW)

    assert factory.call_count == 1
    assert len(factory.embed_calls) == 1
    model_name, texts = factory.embed_calls[0]
    assert model_name == MODEL_NAME
    assert set(texts) == {
        _composed(SHEET_NEW, DESCRIPTION_X, [TEXT_ALPHA]),
        _composed(SHEET_NEW, DESCRIPTION_X, [TEXT_BETA]),
        _composed(SHEET_NEW, None, [TEXT_GAMMA]),
    }
    # The one construction carries the designated server's base URL and the timeout it was given
    # (D9). The resolved key is deliberately not pinned here — the plan does not fix what a null
    # `api_key_ref` resolves to.
    assert [(call[0], call[2]) for call in factory.calls] == [(BASE_URL, PASSED_TIMEOUT)]


# =========================================================================== DoD-2


def test_a_persona_edit_without_a_model_stores_nothing__S024_006_DoD2(engine: Engine) -> None:
    """DoD-2 — D8, authoring fail-hard: with **no** designated model and N > 0 the sheet change
    raises `no_embedding_model`, the stored sheet is the old one, and every `session_vec` row is
    byte-identical to before. The whole transaction rolled back.
    """
    _seed_three_sessions_of_the_character(engine)
    _preexisting_vector(engine, [S1, S2, S3], VECTOR_V8)
    before = _blobs(engine, [S1, S2, S3])
    factory = fake_factory(DIMENSION)

    with pytest.raises(NoEmbeddingModelError) as caught:
        _update_character(engine, character_id=CHAR_C, factory=factory, sheet=SHEET_NEW)

    assert caught.value.code == NO_EMBEDDING_MODEL
    assert _stored_sheet(engine, CHAR_C) == SHEET_OLD
    assert _blobs(engine, [S1, S2, S3]) == before


def test_a_persona_edit_with_an_unreachable_provider_stores_nothing__S024_006_DoD2(engine: Engine) -> None:
    """DoD-2 — D8: with a designation in place and the provider raising, the sheet change raises
    `llm_unreachable`, the stored sheet is the old one and every row is byte-identical.
    """
    _seed_three_sessions_of_the_character(engine)
    _seed_designation(engine)
    _preexisting_vector(engine, [S1, S2, S3], VECTOR_V8)
    before = _blobs(engine, [S1, S2, S3])
    factory = unreachable_factory(DIMENSION)

    with pytest.raises(LlmUnreachableError) as caught:
        _update_character(engine, character_id=CHAR_C, factory=factory, sheet=SHEET_NEW)

    assert caught.value.code == LLM_UNREACHABLE
    assert _stored_sheet(engine, CHAR_C) == SHEET_OLD
    assert _blobs(engine, [S1, S2, S3]) == before


# =========================================================================== DoD-3


def test_a_sheet_change_with_no_sessions_needs_no_model__S024_006_DoD3(engine: Engine) -> None:
    """DoD-3 — U4: N = 0. A character with no sessions has its sheet changed with **no** model
    designated: the change succeeds, is stored, and no client is ever built.
    """
    factory = fake_factory(DIMENSION)

    result = _update_character(engine, character_id=CHAR_LONELY, factory=factory, sheet=SHEET_NEW)

    assert result.sheet == SHEET_NEW
    assert _stored_sheet(engine, CHAR_LONELY) == SHEET_NEW
    assert factory.call_count == 0
    assert factory.embed_calls == []


# =========================================================================== DoD-4


def test_a_name_only_character_update_does_no_vector_work__S024_006_DoD4(engine: Engine) -> None:
    """DoD-4 — D5: a name-only edit on a character **with** sessions needs no model at all, and
    leaves every `session_vec` row untouched.
    """
    _seed_three_sessions_of_the_character(engine)
    _preexisting_vector(engine, [S1, S2, S3], VECTOR_V8)
    before = _blobs(engine, [S1, S2, S3])
    factory = fake_factory(DIMENSION)

    result = _update_character(engine, character_id=CHAR_C, factory=factory, name=NAME_NEW)

    assert result.name == NAME_NEW
    assert _stored_character_name(engine, CHAR_C) == NAME_NEW
    assert _stored_sheet(engine, CHAR_C) == SHEET_OLD
    assert factory.call_count == 0
    assert factory.embed_calls == []
    assert _blobs(engine, [S1, S2, S3]) == before


def test_a_sheet_equal_to_the_stored_one_does_no_vector_work__S024_006_DoD4(engine: Engine) -> None:
    """DoD-4 — D5: "changed" means **differs from the stored value**. Re-sending the unchanged
    persona alongside a new name is a name-only edit: it succeeds with no model designated, the
    factory records nothing, and the rows are byte-identical.
    """
    _seed_three_sessions_of_the_character(engine)
    _preexisting_vector(engine, [S1, S2, S3], VECTOR_V8)
    before = _blobs(engine, [S1, S2, S3])
    factory = fake_factory(DIMENSION)

    result = _update_character(engine, character_id=CHAR_C, factory=factory, name=NAME_NEW, sheet=SHEET_OLD)

    assert result.name == NAME_NEW
    assert result.sheet == SHEET_OLD
    assert _stored_character_name(engine, CHAR_C) == NAME_NEW
    assert _stored_sheet(engine, CHAR_C) == SHEET_OLD
    assert factory.call_count == 0
    assert factory.embed_calls == []
    assert _blobs(engine, [S1, S2, S3]) == before


def test_creating_a_character_needs_no_model__S024_006_DoD4(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-4 — D5: a character create does no vector work. It succeeds with no designated model,
    and the recording factory in play registers nothing.

    `create_character` is frozen without the factory seam (it can never need a model), so "zero
    factory calls" is measured as "the factory this test holds records nothing across the call".
    """
    factory = fake_factory(DIMENSION)

    created = _create_character(engine, generator, name="Newcomer", sheet=SHEET_NEW)

    assert created.name == "Newcomer"
    assert created.sheet == SHEET_NEW
    assert _stored_sheet(engine, created.id) == SHEET_NEW
    assert factory.call_count == 0
    assert factory.embed_calls == []


# =========================================================================== DoD-5


def test_a_changed_description_refreshes_only_the_sessions_using_that_setup__S024_006_DoD5(
    engine: Engine,
) -> None:
    """DoD-5 — US-138.AC-1, U4: S1 (active, X), S2 (**archived**, X), S3 (Y) and S4 (no setup).
    Changing X's description refreshes **exactly** S1 and S2 — one `embed` call carrying two
    texts, each containing the new description — and S3's and S4's rows stay byte-identical.

    The archived session being in and S3 / S4 being out is what proves the selection filters on
    the setup and carries no archive predicate.
    """
    _seed_four_sessions_of_the_setups(engine)
    _seed_designation(engine)
    _preexisting_vector(engine, [S1, S2, S3, S4], VECTOR_V8)
    untouched_before = _blobs(engine, [S3, S4])
    factory = fake_factory(DIMENSION)

    _update_setup(engine, setup_id=SETUP_X, factory=factory, description=DESCRIPTION_X_NEW)

    assert factory.call_count == 1
    assert len(factory.embed_calls) == 1
    model_name, texts = factory.embed_calls[0]
    assert model_name == MODEL_NAME
    assert len(texts) == 2
    for sent in texts:
        assert DESCRIPTION_X_NEW in sent
        assert DESCRIPTION_X not in sent
    expected = {
        S1: _composed(SHEET_OLD, DESCRIPTION_X_NEW, [TEXT_ALPHA]),
        S2: _composed(SHEET_OLD, DESCRIPTION_X_NEW, [TEXT_BETA]),
    }
    assert set(texts) == set(expected.values())
    for session_id, composed in expected.items():
        assert _stored_vector(engine, session_id) == embedding_vector(composed, DIMENSION)
    assert _blobs(engine, [S3, S4]) == untouched_before
    assert _stored_description(engine, SETUP_X) == DESCRIPTION_X_NEW


# =========================================================================== DoD-6


def test_a_description_edit_without_a_model_stores_nothing__S024_006_DoD6(engine: Engine) -> None:
    """DoD-6 — D8, mirroring DoD-2: with sessions on the setup and **no** designated model the
    description change raises `no_embedding_model`, the stored description is the old one, and
    every row is byte-identical.
    """
    _seed_four_sessions_of_the_setups(engine)
    _preexisting_vector(engine, [S1, S2, S3, S4], VECTOR_V8)
    before = _blobs(engine, [S1, S2, S3, S4])
    factory = fake_factory(DIMENSION)

    with pytest.raises(NoEmbeddingModelError) as caught:
        _update_setup(engine, setup_id=SETUP_X, factory=factory, description=DESCRIPTION_X_NEW)

    assert caught.value.code == NO_EMBEDDING_MODEL
    assert _stored_description(engine, SETUP_X) == DESCRIPTION_X
    assert _blobs(engine, [S1, S2, S3, S4]) == before


def test_a_description_edit_with_an_unreachable_provider_stores_nothing__S024_006_DoD6(
    engine: Engine,
) -> None:
    """DoD-6 — D8: the provider raising has the same outcome — the error propagates, the
    description is unchanged and every row is byte-identical.
    """
    _seed_four_sessions_of_the_setups(engine)
    _seed_designation(engine)
    _preexisting_vector(engine, [S1, S2, S3, S4], VECTOR_V8)
    before = _blobs(engine, [S1, S2, S3, S4])
    factory = unreachable_factory(DIMENSION)

    with pytest.raises(LlmUnreachableError) as caught:
        _update_setup(engine, setup_id=SETUP_X, factory=factory, description=DESCRIPTION_X_NEW)

    assert caught.value.code == LLM_UNREACHABLE
    assert _stored_description(engine, SETUP_X) == DESCRIPTION_X
    assert _blobs(engine, [S1, S2, S3, S4]) == before


def test_a_description_change_with_no_sessions_needs_no_model__S024_006_DoD6(engine: Engine) -> None:
    """DoD-6 — U4: N = 0 for setups. A setup no session uses has its description changed with no
    model designated: it succeeds, is stored, and no client is built.
    """
    _seed_four_sessions_of_the_setups(engine)
    factory = fake_factory(DIMENSION)

    result = _update_setup(engine, setup_id=SETUP_LONELY, factory=factory, description=DESCRIPTION_X_NEW)

    assert result.description == DESCRIPTION_X_NEW
    assert _stored_description(engine, SETUP_LONELY) == DESCRIPTION_X_NEW
    assert factory.call_count == 0
    assert factory.embed_calls == []


def test_a_name_only_setup_update_does_no_vector_work__S024_006_DoD6(engine: Engine) -> None:
    """DoD-6 — D5: a name-only setup edit, on a setup **with** sessions, needs no model and
    leaves every row untouched.
    """
    _seed_four_sessions_of_the_setups(engine)
    _preexisting_vector(engine, [S1, S2, S3, S4], VECTOR_V8)
    before = _blobs(engine, [S1, S2, S3, S4])
    factory = fake_factory(DIMENSION)

    result = _update_setup(engine, setup_id=SETUP_X, factory=factory, name=SETUP_NAME_NEW)

    assert result.name == SETUP_NAME_NEW
    assert _stored_setup_name(engine, SETUP_X) == SETUP_NAME_NEW
    assert _stored_description(engine, SETUP_X) == DESCRIPTION_X
    assert factory.call_count == 0
    assert factory.embed_calls == []
    assert _blobs(engine, [S1, S2, S3, S4]) == before


def test_a_description_equal_to_the_stored_one_does_no_vector_work__S024_006_DoD6(engine: Engine) -> None:
    """DoD-6 — D5: re-sending the unchanged description alongside a new name is a name-only edit:
    it succeeds with no model designated and does no vector work.
    """
    _seed_four_sessions_of_the_setups(engine)
    _preexisting_vector(engine, [S1, S2, S3, S4], VECTOR_V8)
    before = _blobs(engine, [S1, S2, S3, S4])
    factory = fake_factory(DIMENSION)

    result = _update_setup(
        engine, setup_id=SETUP_X, factory=factory, name=SETUP_NAME_NEW, description=DESCRIPTION_X
    )

    assert result.name == SETUP_NAME_NEW
    assert result.description == DESCRIPTION_X
    assert _stored_description(engine, SETUP_X) == DESCRIPTION_X
    assert factory.call_count == 0
    assert factory.embed_calls == []
    assert _blobs(engine, [S1, S2, S3, S4]) == before


def test_creating_a_setup_needs_no_model__S024_006_DoD6(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-6 — D5: a setup create does no vector work. It succeeds with no designated model.

    `create_setup` is frozen without the factory seam, so "zero factory calls" is measured as
    "the factory this test holds records nothing across the call".
    """
    factory = fake_factory(DIMENSION)

    created = _create_setup(
        engine, generator, character_id=CHAR_C, name="Fresh", description=DESCRIPTION_X_NEW
    )

    assert created.description == DESCRIPTION_X_NEW
    assert _stored_description(engine, created.id) == DESCRIPTION_X_NEW
    assert factory.call_count == 0
    assert factory.embed_calls == []


# =========================================================================== DoD-7
# The wire, through `create_app()` with `dependency_overrides` for the two keys the skeleton
# recorded: `app.dependencies.get_llm_client_factory` and `app.config.get_settings`.

CHARACTERS_PATH = "/api/characters"
SETUPS_PATH = "/api/setups"
LOGIN_PATH = "/api/auth/login"

PLAYER_A_ID = 1_600_000_000_000_000_301
PLAYER_A_NAME = "aster"
PLAYER_A_PASSWORD = "a quiet river at dusk"

WIRE_SESSION = 1_600_000_000_000_000_311
WIRE_ENTRY = 1_600_000_000_000_000_312


@pytest.fixture(autouse=True)
def _quiet_factory_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the factory's logging call so these tests touch no global sinks."""
    monkeypatch.setattr("app.main.configure_logging", lambda settings: None)


@contextmanager
def _application(db_settings: Settings, factory: FakeClientFactory) -> Iterator[FastAPI]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: db_settings
    app.dependency_overrides[get_llm_client_factory] = lambda: factory
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


def _parse_set_cookie(header: str) -> tuple[str, str]:
    first = header.split(";")[0]
    name, _, value = first.partition("=")
    return name.strip(), value.strip().strip('"')


def _player_a(application: FastAPI, settings: Settings) -> TestClient:
    """A fresh client carrying the roleplayer's session cookie — the routers' login pattern."""
    response = TestClient(application).post(
        LOGIN_PATH, json={"username": PLAYER_A_NAME, "password": PLAYER_A_PASSWORD}
    )
    assert response.status_code == 200, response.text
    tokens = [
        value
        for name, value in (_parse_set_cookie(header) for header in response.headers.get_list("set-cookie"))
        if name == settings.session_cookie_name
    ]
    assert len(tokens) == 1 and tokens[0]
    fresh = TestClient(application)
    fresh.cookies.set(settings.session_cookie_name, tokens[0])
    return fresh


@pytest.fixture
def wire_engine(db_engine: Engine) -> Engine:
    """The wire cases' database: the registry plus one roleplayer who logs in."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=PLAYER_A_ID, username=PLAYER_A_NAME, password=PLAYER_A_PASSWORD)
    return db_engine


def _ok(response: httpx.Response, status: int) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def _assert_envelope(response: httpx.Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"error"}
    assert body["error"]["code"] == code


def _wire_character(client: TestClient, sheet: str = SHEET_OLD) -> dict[str, Any]:
    return _ok(client.post(CHARACTERS_PATH, json={"name": NAME_OLD, "sheet": sheet}), 201)


def _wire_setup(client: TestClient, character_id: Any, description: str = DESCRIPTION_X) -> dict[str, Any]:
    return _ok(
        client.post(
            f"{CHARACTERS_PATH}/{character_id}/setups",
            json={"name": SETUP_NAME_OLD, "description": description},
        ),
        201,
    )


def _attach_session(
    engine: Engine, *, character_id: int, setup_id: int | None, entry: str = TEXT_ALPHA
) -> None:
    """One session with one settled entry, raw-inserted for a route-created character / setup.

    The session makes N > 0, which is the only condition under which these PATCHes need a model.
    """
    _insert_session(
        engine,
        session_id=WIRE_SESSION,
        user_id=PLAYER_A_ID,
        character_id=character_id,
        setup_id=setup_id,
    )
    _insert_settled_entry(
        engine, message_id=WIRE_ENTRY, session_id=WIRE_SESSION, body=entry, user_id=PLAYER_A_ID
    )


def test_a_sheet_patch_without_a_model_answers_409_and_keeps_the_old_sheet__S024_006_DoD7(
    wire_engine: Engine, db_settings: Settings
) -> None:
    """DoD-7 — Wire contract: `PATCH /api/characters/{id}` changing the sheet of a character with
    sessions, with no designated model, answers 409 `no_embedding_model`; a following GET shows
    the **old** sheet, because nothing was stored (D8).
    """
    factory = fake_factory(DIMENSION)
    with _application(db_settings, factory) as application:
        client = _player_a(application, db_settings)
        character = _wire_character(client)
        _attach_session(wire_engine, character_id=int(character["id"]), setup_id=None)

        response = client.patch(f"{CHARACTERS_PATH}/{character['id']}", json={"sheet": SHEET_NEW})

        _assert_envelope(response, 409, NO_EMBEDDING_MODEL)
        after = _ok(client.get(f"{CHARACTERS_PATH}/{character['id']}"), 200)

    assert after["sheet"] == SHEET_OLD


def test_a_sheet_patch_with_a_designated_model_answers_200__S024_006_DoD7(
    wire_engine: Engine, db_settings: Settings
) -> None:
    """DoD-7 — Wire contract: the very same PATCH with a designation and the fake answers 200
    with the new sheet, so the 409 above reports the condition and not a constant.
    """
    _seed_designation(wire_engine)
    factory = fake_factory(DIMENSION)
    with _application(db_settings, factory) as application:
        client = _player_a(application, db_settings)
        character = _wire_character(client)
        _attach_session(wire_engine, character_id=int(character["id"]), setup_id=None)

        body = _ok(client.patch(f"{CHARACTERS_PATH}/{character['id']}", json={"sheet": SHEET_NEW}), 200)

    assert body["sheet"] == SHEET_NEW
    assert factory.call_count == 1
    assert len(factory.embed_calls) == 1


def test_a_description_patch_with_an_unreachable_provider_answers_502__S024_006_DoD7(
    wire_engine: Engine, db_settings: Settings
) -> None:
    """DoD-7 — Wire contract: `PATCH /api/setups/{id}` changing the description of a setup with
    sessions, against a provider that raises, answers 502 `llm_unreachable`, and the stored
    description is still the old one (D8).
    """
    _seed_designation(wire_engine)
    factory = unreachable_factory(DIMENSION)
    with _application(db_settings, factory) as application:
        client = _player_a(application, db_settings)
        character = _wire_character(client)
        setup = _wire_setup(client, character["id"])
        _attach_session(wire_engine, character_id=int(character["id"]), setup_id=int(setup["id"]))

        response = client.patch(f"{SETUPS_PATH}/{setup['id']}", json={"description": DESCRIPTION_X_NEW})

        _assert_envelope(response, 502, LLM_UNREACHABLE)
        after = _ok(client.get(f"{SETUPS_PATH}/{setup['id']}"), 200)

    assert after["description"] == DESCRIPTION_X


def test_a_description_patch_with_no_sessions_answers_200_without_a_model__S024_006_DoD7(
    wire_engine: Engine, db_settings: Settings
) -> None:
    """DoD-7 — U4 on the wire: the same setup PATCH, with **no** session using the setup and no
    model designated, answers 200 with the new description and builds no client.
    """
    factory = fake_factory(DIMENSION)
    with _application(db_settings, factory) as application:
        client = _player_a(application, db_settings)
        character = _wire_character(client)
        setup = _wire_setup(client, character["id"])

        body = _ok(
            client.patch(f"{SETUPS_PATH}/{setup['id']}", json={"description": DESCRIPTION_X_NEW}), 200
        )

    assert body["description"] == DESCRIPTION_X_NEW
    assert factory.call_count == 0
    assert factory.embed_calls == []
