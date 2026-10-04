"""Tests for `app/services/session_index.py` — feature 024, step 003 (DoD-1..12).

Every expected value comes from `docs/plans/024.embedding-lifecycle/003.session-index.md`
(its Interface intent and Definition of done — **DoD-1 pins the composed string verbatim**),
from `003.context.md` (the test shape, the refresh order, the degraded catch) and from the
feature `context.md` (**D5** archived sessions included, **D6** the exact composition and the
empty-text rule, **D8** the two failure codes and the `{"reason": "dimension_mismatch"}`
detail, **U5** a degraded write leaves the existing row as it is, **R5** owner scope, **R11**
reads go through `settled_entries`). Bindings come from `## Skeleton` → "Step 003 — frozen
interface" (and steps 001 / 002 for `ensure_vector_tables`, `write_vector` and the table-name
constants), and the fake's contract from `## Tests` → "Step 002 — tests" in `status.md`.
Nothing here was derived from the implementation.

Each test name ends `__S024_003_DoD<n>` with the DoD item it covers.

Mechanics (`context.md` "Test conventions", `003.context.md` "Test shape"):
- a real SQLite file per test (`db_engine`) with `schema.metadata.create_all`; `conftest.py`
  is untouched and the only fixture is the file-local `engine`;
- users, characters, setups, sessions (one with `archived_at` set) and messages in all three
  states are **raw inserts**, every id above 2^60;
- a designated model is raw `llm_servers` + `models` rows at dimension 8, with a null
  `api_key_ref` so no secret has to resolve;
- the outbound client is injected through the frozen `client_factory=` keyword seam using the
  shared fake in `tests/llm_fakes.py`. No network, no monkeypatching;
- pre-existing vectors are written with `002`'s `write_vector` after `001`'s
  `ensure_vector_tables`; the tables are then observed only from the test side, through
  `pragma_table_info`, point lookups and `MATCH`.
"""

import ast
import inspect
import struct
from collections.abc import Collection, Iterator

import pytest
from sqlalchemy import Connection, Engine, Table, select, text

import app.services.session_index as session_index_module
from app.db import schema
from app.db.search_tables import MESSAGE_FTS_TABLE, SESSION_VEC_TABLE, ensure_vector_tables
from app.errors import LlmUnreachableError, NoEmbeddingModelError
from app.roles import Role
from app.services.embedding import write_vector
from app.services.session_index import (
    compose_session_text,
    refresh_session_vector_degraded,
    refresh_session_vectors,
    session_ids_for_character,
    session_ids_for_setup,
)
from tests.llm_fakes import (
    FakeClientFactory,
    embedding_vector,
    fake_factory,
    unreachable_factory,
    wrong_length_factory,
)

#: The seeded instant, in the project's fixed-width form.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
#: The instant rows seeded already settled carry.
SEEDED_SETTLED_AT = "2025-12-31T00:00:00.000000+00:00"
#: The instant the DoD-6 relational write stamps — distinct from `TIMESTAMP` so the commit shows.
BUMPED_AT = "2026-03-03T03:03:03.000000+00:00"

#: Every id is above 2^60 = 1152921504606846976 (D3 / U6: snowflake ids stay the keys).
MIN_SNOWFLAKE_ID = 2**60

USER_A = 1_300_000_000_000_000_001
USER_B = 1_300_000_000_000_000_002

#: `CHAR_A.sheet` is the persona part of D6; `CHAR_EMPTY.sheet` is `""` (harvest A3: NOT NULL,
#: may be empty); `CHAR_B` belongs to the other owner.
CHAR_A = 1_300_000_000_000_000_011
CHAR_EMPTY = 1_300_000_000_000_000_012
CHAR_B = 1_300_000_000_000_000_013

SETUP_X = 1_300_000_000_000_000_021
SETUP_Y = 1_300_000_000_000_000_022
SETUP_B = 1_300_000_000_000_000_023

S_MAIN = 1_300_000_000_000_000_031
S_NO_SETUP = 1_300_000_000_000_000_032
S_BARE = 1_300_000_000_000_000_033
S_SECOND = 1_300_000_000_000_000_034
S_THIRD = 1_300_000_000_000_000_035
S_ARCHIVED = 1_300_000_000_000_000_036
S_SETUP_Y = 1_300_000_000_000_000_037
S_OF_B = 1_300_000_000_000_000_038

M1 = 1_300_000_000_000_000_101
M2 = 1_300_000_000_000_000_102
M3 = 1_300_000_000_000_000_103
M4 = 1_300_000_000_000_000_104
M5 = 1_300_000_000_000_000_105

SERVER_ID = 1_300_000_000_000_000_201
MODEL_ID = 1_300_000_000_000_000_202

BASE_URL = "http://embedding.test:8080/v1"
MODEL_NAME = "the-designated-embedding-model"

#: The designated dimension in these tests; 8 keeps them fast (`context.md`).
DIMENSION = 8
#: DoD-5's third condition: an existing vector table declared at this dimension instead.
OTHER_DIMENSION = 16

#: A timeout deliberately unequal to `Settings`' declared default, so it is distinguishable.
PASSED_TIMEOUT = 12.5

#: D6's parts, exactly as stored (DoD-1).
SHEET_A = "Persona P."
DESCRIPTION_X = "Setup S."
DESCRIPTION_Y = "Setup Y."
TEXT_ALPHA = "Alpha"
TEXT_BURIED = "Buried"
TEXT_BETA = "Beta"
TEXT_GAMMA = "((Gamma))"
TEXT_DRAFT = "Draft"
WHITESPACE_ONLY = "   \n\t  "

#: DoD-1's expected result, verbatim from the step file.
EXPECTED_DOD1 = "Persona P.\n\nSetup S.\n\nAlpha\n\nBeta\n\n((Gamma))"

#: DoD-4's three composed texts (D6: persona, then setup when present, then the entries).
TEXT_MAIN = "Persona P.\n\nSetup S.\n\nAlpha"
TEXT_SECOND = "Persona P.\n\nBeta"
TEXT_THIRD = "Persona P.\n\nGamma"

#: Exact float32 values (multiples of 2**-3), so a round-trip compares equal with no tolerance.
VECTOR_V8 = [0.5, -1.5, 2.25, 0.0, 1.0, -0.125, 3.5, -2.0]
VECTOR_V16 = [
    0.5, -1.5, 2.25, 0.0, 1.0, -0.125, 3.5, -2.0,
    -0.25, 0.75, 1.5, -3.0, 0.125, 2.0, -1.0, 4.5,
]

#: A nonsense token, so a `MATCH` can only come from the row that carries it (DoD-11).
FTS_TOKEN = "settledtokenxyz"


# --- seeding ---------------------------------------------------------------------------


def _servers() -> Table:
    return schema.metadata.tables["llm_servers"]


def _models() -> Table:
    return schema.metadata.tables["models"]


def _insert_user(engine: Engine, *, user_id: int, username: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.users.insert().values(
                id=user_id,
                username=username,
                password_hash="not-a-real-hash",
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
    character_id: int = CHAR_A,
    setup_id: int | None = None,
    archived_at: str | None = None,
) -> None:
    """Raw-insert one `sessions` row (harvest A3: no title, no partner label)."""
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


def _insert_message(
    engine: Engine,
    *,
    message_id: int,
    body: str,
    session_id: int,
    user_id: int = USER_A,
    role: str = "user",
    related_to: int | None = None,
    settled_at: str | None = None,
) -> None:
    """Raw-insert one `messages` row in a chosen state.

    The three states of `003.context.md`'s test shape: **settled** (`settled_at` set,
    `related_to` null — a record row), **zone** (both null) and **buried** (`related_to` set).
    `kind` is left null throughout: D6 composes the `text` column alone, so no kind vocabulary
    is invented here.
    """
    with engine.begin() as connection:
        connection.execute(
            schema.messages.insert().values(
                id=message_id,
                user_id=user_id,
                session_id=session_id,
                role=role,
                kind=None,
                text=body,
                related_to=related_to,
                settled_at=settled_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _settled(engine: Engine, message_id: int, body: str, *, session_id: int, user_id: int = USER_A) -> None:
    _insert_message(
        engine,
        message_id=message_id,
        body=body,
        session_id=session_id,
        user_id=user_id,
        settled_at=SEEDED_SETTLED_AT,
    )


def _zone(engine: Engine, message_id: int, body: str, *, session_id: int) -> None:
    _insert_message(engine, message_id=message_id, body=body, session_id=session_id)


def _buried(engine: Engine, message_id: int, body: str, *, session_id: int, related_to: int) -> None:
    _insert_message(engine, message_id=message_id, body=body, session_id=session_id, related_to=related_to)


def _seed_designation(
    engine: Engine,
    *,
    dim: int | None = DIMENSION,
    is_enabled: bool = True,
    is_designated: bool = True,
) -> None:
    """Raw-insert one server and one model row — the designation, built without any service."""
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
                is_enabled=is_enabled,
                is_embedding_designated=is_designated,
                embedding_dim=dim,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


@pytest.fixture
def engine(db_engine: Engine) -> Iterator[Engine]:
    """The registry applied, two owners, their characters and setups. Sessions are per test.

    `create_all` only: no virtual table exists yet, which is the "never created" starting
    state DoD-11 needs.
    """
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="alice")
    _insert_user(db_engine, user_id=USER_B, username="bob")
    _insert_character(db_engine, character_id=CHAR_A, user_id=USER_A, name="Aria", sheet=SHEET_A)
    _insert_character(db_engine, character_id=CHAR_EMPTY, user_id=USER_A, name="Blank", sheet="")
    _insert_character(db_engine, character_id=CHAR_B, user_id=USER_B, name="Brynn", sheet="Persona B.")
    _insert_setup(
        db_engine, setup_id=SETUP_X, user_id=USER_A, character_id=CHAR_A, name="X", description=DESCRIPTION_X
    )
    _insert_setup(
        db_engine, setup_id=SETUP_Y, user_id=USER_A, character_id=CHAR_A, name="Y", description=DESCRIPTION_Y
    )
    _insert_setup(
        db_engine, setup_id=SETUP_B, user_id=USER_B, character_id=CHAR_B, name="B", description="Setup B."
    )
    yield db_engine


# --- calling the frozen interface -------------------------------------------------------


def _compose(engine: Engine, user_id: int, session_id: int) -> str:
    with engine.connect() as connection:
        return compose_session_text(connection, user_id, session_id)


def _refresh(engine: Engine, user_id: int, session_ids: Collection[int], factory: FakeClientFactory) -> None:
    """The strict refresh, inside a transaction, as every caller runs it (U1)."""
    with engine.begin() as connection:
        refresh_session_vectors(
            connection, user_id, session_ids, client_factory=factory, timeout_seconds=PASSED_TIMEOUT
        )


def _refresh_degraded(engine: Engine, user_id: int, session_id: int, factory: FakeClientFactory) -> bool:
    with engine.begin() as connection:
        return refresh_session_vector_degraded(
            connection, user_id, session_id, client_factory=factory, timeout_seconds=PASSED_TIMEOUT
        )


def _degraded_after_a_relational_write(
    engine: Engine, session_id: int, factory: FakeClientFactory, *, user_id: int = USER_A
) -> bool:
    """A real relational write, then the degraded refresh, in **one** transaction (U1, DoD-6)."""
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.update().where(schema.sessions.c.id == session_id).values(last_used_at=BUMPED_AT)
        )
        return refresh_session_vector_degraded(
            connection, user_id, session_id, client_factory=factory, timeout_seconds=PASSED_TIMEOUT
        )


def _preexisting_vector(engine: Engine, session_id: int, vector: list[float], *, dim: int) -> None:
    """A committed `session_vec` row, made with `001`'s ensure and `002`'s writer."""
    with engine.begin() as connection:
        ensure_vector_tables(connection, dim)
        write_vector(connection, SESSION_VEC_TABLE, session_id, vector)


# --- observation (tests may query the tables; application code never does) ---------------


def _key_column(connection: Connection, table_name: str) -> str | None:
    """The vec0 table's key column, or `None` when the table does not exist."""
    rows = connection.execute(
        text("SELECT name FROM pragma_table_info(:table_name) WHERE pk = 1"),
        {"table_name": table_name},
    ).all()
    return None if not rows else str(rows[0][0])


def _stored_vector(engine: Engine, session_id: int, *, dim: int = DIMENSION) -> list[float] | None:
    """The vector stored for one session id, or `None` when there is no row (or no table)."""
    with engine.connect() as connection:
        key = _key_column(connection, SESSION_VEC_TABLE)
        if key is None:
            return None
        query = text(f"SELECT embedding FROM {SESSION_VEC_TABLE} WHERE {key} = :row_id")
        blob = connection.execute(query, {"row_id": session_id}).scalar_one_or_none()
        return None if blob is None else list(struct.unpack(f"<{dim}f", bytes(blob)))


def _vector_row_count(engine: Engine) -> int:
    with engine.connect() as connection:
        if _key_column(connection, SESSION_VEC_TABLE) is None:
            return 0
        return int(connection.execute(text(f"SELECT count(*) FROM {SESSION_VEC_TABLE}")).scalar_one())


def _table_names(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        rows = connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type = 'table'").all()
    return {str(row[0]) for row in rows}


def _match_ids(engine: Engine, table_name: str, token: str) -> list[int]:
    """The rowids a full-text `MATCH` on one token returns, ascending."""
    query = text(f"SELECT rowid FROM {table_name} WHERE {table_name} MATCH :token ORDER BY rowid")
    with engine.connect() as connection:
        return [int(row[0]) for row in connection.execute(query, {"token": token}).all()]


def _last_used_at(engine: Engine, session_id: int) -> str:
    with engine.connect() as connection:
        value = connection.execute(
            select(schema.sessions.c.last_used_at).where(schema.sessions.c.id == session_id)
        ).scalar_one()
    return str(value)


# =========================================================================== DoD-1


def test_the_session_text_is_persona_setup_then_settled_entries__S024_003_DoD1(engine: Engine) -> None:
    """DoD-1 — the composition contract, pinned exactly (D6, US-138.AC-1, US-122.AC-2, US-115,
    UC-038, R11).

    One equality proves persona-first ordering, the `"\\n\\n"` join, the `settled_entries`
    boundary (the buried and zone rows are out) and ascending-id order.
    """
    _insert_session(engine, session_id=S_MAIN, character_id=CHAR_A, setup_id=SETUP_X)
    _settled(engine, M1, TEXT_ALPHA, session_id=S_MAIN)
    _buried(engine, M2, TEXT_BURIED, session_id=S_MAIN, related_to=M1)
    _settled(engine, M3, TEXT_BETA, session_id=S_MAIN)
    _settled(engine, M4, TEXT_GAMMA, session_id=S_MAIN)
    _zone(engine, M5, TEXT_DRAFT, session_id=S_MAIN)

    composed = _compose(engine, USER_A, S_MAIN)

    assert composed == EXPECTED_DOD1
    # Spelled out, because they are the point: zone and buried text is never searchable (US-115),
    # and a settled decision is (US-122.AC-2).
    assert TEXT_BURIED not in composed
    assert TEXT_DRAFT not in composed
    assert TEXT_GAMMA in composed


# =========================================================================== DoD-2


def test_a_session_with_no_setup_composes_without_a_setup_part__S024_003_DoD2(engine: Engine) -> None:
    """DoD-2 — `setup_id` null: the persona and the entries, nothing between them (D6)."""
    _insert_session(engine, session_id=S_NO_SETUP, character_id=CHAR_A, setup_id=None)
    _settled(engine, M1, TEXT_ALPHA, session_id=S_NO_SETUP)

    assert _compose(engine, USER_A, S_NO_SETUP) == "Persona P.\n\nAlpha"


def test_an_empty_sheet_and_no_setup_composes_from_the_entries_alone__S024_003_DoD2(engine: Engine) -> None:
    """DoD-2 — an empty `sheet` is a dropped part, so only the entries remain (D6)."""
    _insert_session(engine, session_id=S_BARE, character_id=CHAR_EMPTY, setup_id=None)
    _settled(engine, M1, TEXT_ALPHA, session_id=S_BARE)
    _settled(engine, M2, TEXT_BETA, session_id=S_BARE)

    assert _compose(engine, USER_A, S_BARE) == "Alpha\n\nBeta"


def test_a_whitespace_only_settled_entry_contributes_no_part__S024_003_DoD2(engine: Engine) -> None:
    """DoD-2 — a whitespace-only part is dropped, and leaves no doubled separator (D6)."""
    _insert_session(engine, session_id=S_NO_SETUP, character_id=CHAR_A, setup_id=None)
    _settled(engine, M1, TEXT_ALPHA, session_id=S_NO_SETUP)
    _settled(engine, M2, WHITESPACE_ONLY, session_id=S_NO_SETUP)
    _settled(engine, M3, TEXT_BETA, session_id=S_NO_SETUP)

    assert _compose(engine, USER_A, S_NO_SETUP) == "Persona P.\n\nAlpha\n\nBeta"


# =========================================================================== DoD-3


def test_another_users_session_composes_to_the_empty_string__S024_003_DoD3(engine: Engine) -> None:
    """DoD-3 — owner scope in SQL (R5): the session is not the caller's, so there is no text."""
    _insert_session(engine, session_id=S_MAIN, character_id=CHAR_A, setup_id=SETUP_X)
    _settled(engine, M1, TEXT_ALPHA, session_id=S_MAIN)

    assert _compose(engine, USER_B, S_MAIN) == ""


def test_a_strict_refresh_of_another_users_session_writes_no_row__S024_003_DoD3(engine: Engine) -> None:
    """DoD-3 — and the strict refresh writes no `session_vec` row for that id (R5, D6).

    No model is designated: a foreign session's text is empty, so none is needed.
    """
    _insert_session(engine, session_id=S_MAIN, character_id=CHAR_A, setup_id=SETUP_X)
    _settled(engine, M1, TEXT_ALPHA, session_id=S_MAIN)
    with engine.begin() as connection:
        ensure_vector_tables(connection, DIMENSION)
    factory = fake_factory(dim=DIMENSION)

    _refresh(engine, USER_B, [S_MAIN], factory)

    assert _stored_vector(engine, S_MAIN) is None
    assert _vector_row_count(engine) == 0
    assert factory.call_count == 0


# =========================================================================== DoD-4


def test_three_sessions_are_refreshed_in_one_embed_call__S024_003_DoD4(engine: Engine) -> None:
    """DoD-4 — one client, **one** `embed` call carrying the three composed texts, and one row
    per session holding that session's own vector (D1, US-138.AC-1).

    A per-session loop would show up as three calls or three constructions.
    """
    _seed_designation(engine)
    _insert_session(engine, session_id=S_MAIN, character_id=CHAR_A, setup_id=SETUP_X)
    _insert_session(engine, session_id=S_SECOND, character_id=CHAR_A, setup_id=None)
    _insert_session(engine, session_id=S_THIRD, character_id=CHAR_A, setup_id=None)
    _settled(engine, M1, TEXT_ALPHA, session_id=S_MAIN)
    _settled(engine, M2, TEXT_BETA, session_id=S_SECOND)
    _settled(engine, M3, "Gamma", session_id=S_THIRD)
    factory = fake_factory(dim=DIMENSION)

    _refresh(engine, USER_A, [S_MAIN, S_SECOND, S_THIRD], factory)

    assert _vector_row_count(engine) == 3
    assert _stored_vector(engine, S_MAIN) == embedding_vector(TEXT_MAIN, DIMENSION)
    assert _stored_vector(engine, S_SECOND) == embedding_vector(TEXT_SECOND, DIMENSION)
    assert _stored_vector(engine, S_THIRD) == embedding_vector(TEXT_THIRD, DIMENSION)
    assert factory.call_count == 1
    assert len(factory.embed_calls) == 1
    model, texts = factory.embed_calls[0]
    assert model == MODEL_NAME
    assert sorted(texts) == sorted([TEXT_MAIN, TEXT_SECOND, TEXT_THIRD])


# =========================================================================== DoD-5


def _session_with_a_preexisting_vector(engine: Engine, *, dim: int, vector: list[float]) -> None:
    """One session with a non-empty text (so a model is needed) and a committed vector row."""
    _insert_session(engine, session_id=S_MAIN, character_id=CHAR_A, setup_id=SETUP_X)
    _settled(engine, M1, TEXT_ALPHA, session_id=S_MAIN)
    _preexisting_vector(engine, S_MAIN, vector, dim=dim)


def test_no_designated_model_is_refused_and_leaves_the_row_alone__S024_003_DoD5(engine: Engine) -> None:
    """DoD-5 — no designation → `NoEmbeddingModelError`, and the existing row is unchanged (D8)."""
    _session_with_a_preexisting_vector(engine, dim=DIMENSION, vector=VECTOR_V8)
    factory = fake_factory(dim=DIMENSION)

    with pytest.raises(NoEmbeddingModelError) as raised:
        _refresh(engine, USER_A, [S_MAIN], factory)

    assert raised.value.code == "no_embedding_model"
    assert _stored_vector(engine, S_MAIN) == VECTOR_V8


def test_an_unreachable_provider_propagates_and_leaves_the_row_alone__S024_003_DoD5(engine: Engine) -> None:
    """DoD-5 — the embed call fails → `LlmUnreachableError` propagates; the row is unchanged (D8)."""
    _session_with_a_preexisting_vector(engine, dim=DIMENSION, vector=VECTOR_V8)
    _seed_designation(engine)
    factory = unreachable_factory(dim=DIMENSION)

    with pytest.raises(LlmUnreachableError) as raised:
        _refresh(engine, USER_A, [S_MAIN], factory)

    assert raised.value.code == "llm_unreachable"
    assert _stored_vector(engine, S_MAIN) == VECTOR_V8


def test_a_table_at_another_dimension_is_a_dimension_mismatch__S024_003_DoD5(engine: Engine) -> None:
    """DoD-5 — an existing `session_vec` at 16 while the designation says 8 is
    `NoEmbeddingModelError` with `detail` exactly `{"reason": "dimension_mismatch"}` (D8), and
    the existing row survives.
    """
    _session_with_a_preexisting_vector(engine, dim=OTHER_DIMENSION, vector=VECTOR_V16)
    _seed_designation(engine, dim=DIMENSION)
    factory = fake_factory(dim=DIMENSION)

    with pytest.raises(NoEmbeddingModelError) as raised:
        _refresh(engine, USER_A, [S_MAIN], factory)

    assert raised.value.code == "no_embedding_model"
    assert raised.value.detail == {"reason": "dimension_mismatch"}
    assert _stored_vector(engine, S_MAIN, dim=OTHER_DIMENSION) == VECTOR_V16


# =========================================================================== DoD-6


def test_a_degraded_refresh_without_a_model_commits_the_row_and_keeps_the_stale_vector__S024_003_DoD6(
    engine: Engine,
) -> None:
    """DoD-6 — US-112.AC-1: no designated model raises nothing, answers "incomplete", the earlier
    relational write commits, and the existing vector stays as it was (stale, U5).
    """
    _session_with_a_preexisting_vector(engine, dim=DIMENSION, vector=VECTOR_V8)
    factory = fake_factory(dim=DIMENSION)

    incomplete = _degraded_after_a_relational_write(engine, S_MAIN, factory)

    assert incomplete is True
    assert _last_used_at(engine, S_MAIN) == BUMPED_AT
    assert _stored_vector(engine, S_MAIN) == VECTOR_V8


def test_a_degraded_refresh_with_an_unreachable_provider_commits_the_row__S024_003_DoD6(
    engine: Engine,
) -> None:
    """DoD-6 — the same for a failed embed call: caught, flagged, row committed, vector stale."""
    _session_with_a_preexisting_vector(engine, dim=DIMENSION, vector=VECTOR_V8)
    _seed_designation(engine)
    factory = unreachable_factory(dim=DIMENSION)

    incomplete = _degraded_after_a_relational_write(engine, S_MAIN, factory)

    assert incomplete is True
    assert _last_used_at(engine, S_MAIN) == BUMPED_AT
    assert _stored_vector(engine, S_MAIN) == VECTOR_V8


def test_a_degraded_refresh_with_a_dimension_mismatch_commits_the_row__S024_003_DoD6(
    engine: Engine,
) -> None:
    """DoD-6 — a dimension mismatch is "unavailable" too (D8), so it degrades identically."""
    _session_with_a_preexisting_vector(engine, dim=OTHER_DIMENSION, vector=VECTOR_V16)
    _seed_designation(engine, dim=DIMENSION)
    factory = fake_factory(dim=DIMENSION)

    incomplete = _degraded_after_a_relational_write(engine, S_MAIN, factory)

    assert incomplete is True
    assert _last_used_at(engine, S_MAIN) == BUMPED_AT
    assert _stored_vector(engine, S_MAIN, dim=OTHER_DIMENSION) == VECTOR_V16


def test_a_wrong_length_vector_also_degrades_and_keeps_the_row__S024_003_DoD6(engine: Engine) -> None:
    """DoD-6 — a returned vector of the wrong length is the other dimension-mismatch raise site
    (D8), and the degraded path catches it just the same.
    """
    _session_with_a_preexisting_vector(engine, dim=DIMENSION, vector=VECTOR_V8)
    _seed_designation(engine)
    factory = wrong_length_factory(dim=DIMENSION, returned_length=DIMENSION - 1)

    incomplete = _degraded_after_a_relational_write(engine, S_MAIN, factory)

    assert incomplete is True
    assert _last_used_at(engine, S_MAIN) == BUMPED_AT
    assert _stored_vector(engine, S_MAIN) == VECTOR_V8


# =========================================================================== DoD-7


def test_a_degraded_success_answers_complete_and_rewrites_the_vector__S024_003_DoD7(engine: Engine) -> None:
    """DoD-7 — success returns false (coverage complete) and the row holds the fake's vector for
    the **current** composed text, replacing what was there (D5, D4's upsert).
    """
    _session_with_a_preexisting_vector(engine, dim=DIMENSION, vector=VECTOR_V8)
    _seed_designation(engine)
    factory = fake_factory(dim=DIMENSION)

    incomplete = _refresh_degraded(engine, USER_A, S_MAIN, factory)

    assert incomplete is False
    assert _stored_vector(engine, S_MAIN) == embedding_vector(TEXT_MAIN, DIMENSION)
    assert _vector_row_count(engine) == 1


# =========================================================================== DoD-8


def _empty_text_session_with_a_row(engine: Engine) -> None:
    """An empty sheet, no setup and no settled entry — D6's empty text — plus an existing row."""
    _insert_session(engine, session_id=S_BARE, character_id=CHAR_EMPTY, setup_id=None)
    _zone(engine, M1, TEXT_DRAFT, session_id=S_BARE)
    _preexisting_vector(engine, S_BARE, VECTOR_V8, dim=DIMENSION)


def test_an_empty_text_degraded_refresh_is_complete_and_drops_the_row__S024_003_DoD8(engine: Engine) -> None:
    """DoD-8 — empty text with **no** model: not degraded (false), the row is gone, and nothing
    was constructed (D6).
    """
    _empty_text_session_with_a_row(engine)
    factory = fake_factory(dim=DIMENSION)

    assert _compose(engine, USER_A, S_BARE) == ""

    incomplete = _refresh_degraded(engine, USER_A, S_BARE, factory)

    assert incomplete is False
    assert _stored_vector(engine, S_BARE) is None
    assert factory.call_count == 0


def test_an_empty_text_strict_refresh_raises_nothing_and_drops_the_row__S024_003_DoD8(engine: Engine) -> None:
    """DoD-8 — and the strict refresh of the same session needs no model either (D6)."""
    _empty_text_session_with_a_row(engine)
    factory = fake_factory(dim=DIMENSION)

    _refresh(engine, USER_A, [S_BARE], factory)

    assert _stored_vector(engine, S_BARE) is None
    assert factory.call_count == 0


# =========================================================================== DoD-9


def test_an_empty_id_collection_needs_no_model__S024_003_DoD9(engine: Engine) -> None:
    """DoD-9 — N = 0: nothing beyond the FTS ensure, so no model and no client (U4)."""
    factory = fake_factory(dim=DIMENSION)

    _refresh(engine, USER_A, [], factory)

    assert factory.call_count == 0
    assert factory.embed_calls == []


# =========================================================================== DoD-10


@pytest.fixture
def fanout(engine: Engine) -> Engine:
    """DoD-10's four sessions of A's character C, plus one of user B's own."""
    _insert_session(engine, session_id=S_MAIN, character_id=CHAR_A, setup_id=SETUP_X)
    _insert_session(
        engine, session_id=S_ARCHIVED, character_id=CHAR_A, setup_id=SETUP_X, archived_at=TIMESTAMP
    )
    _insert_session(engine, session_id=S_NO_SETUP, character_id=CHAR_A, setup_id=None)
    _insert_session(engine, session_id=S_SETUP_Y, character_id=CHAR_A, setup_id=SETUP_Y)
    _insert_session(engine, session_id=S_OF_B, user_id=USER_B, character_id=CHAR_B, setup_id=SETUP_B)
    return engine


def test_every_session_of_a_character_is_listed_archived_included__S024_003_DoD10(fanout: Engine) -> None:
    """DoD-10 — all four, with no archive predicate: a restored session must not be stale (U4)."""
    with fanout.connect() as connection:
        listed = session_ids_for_character(connection, USER_A, CHAR_A)

    assert set(listed) == {S_MAIN, S_ARCHIVED, S_NO_SETUP, S_SETUP_Y}


def test_only_the_sessions_using_a_setup_are_listed_archived_included__S024_003_DoD10(fanout: Engine) -> None:
    """DoD-10 — the setup fan-out is the two sessions on X, the archived one included (U4)."""
    with fanout.connect() as connection:
        listed = session_ids_for_setup(connection, USER_A, SETUP_X)

    assert set(listed) == {S_MAIN, S_ARCHIVED}


def test_another_users_character_and_setup_fan_out_to_nothing__S024_003_DoD10(fanout: Engine) -> None:
    """DoD-10 — owner scope in SQL (R5): user B gets nothing for A's character or setup."""
    with fanout.connect() as connection:
        by_character = session_ids_for_character(connection, USER_B, CHAR_A)
        by_setup = session_ids_for_setup(connection, USER_B, SETUP_X)

    assert set(by_character) == set()
    assert set(by_setup) == set()


# =========================================================================== DoD-11


def test_a_degraded_refresh_ensures_and_backfills_the_message_index__S024_003_DoD11(engine: Engine) -> None:
    """DoD-11 — on a database where the FTS tables were never created, the refresh ensures them
    **before** anything can fail, so a settled entry's token is found by `MATCH` afterwards (D2).
    """
    _insert_session(engine, session_id=S_MAIN, character_id=CHAR_A, setup_id=SETUP_X)
    _settled(engine, M1, f"the entry mentions {FTS_TOKEN} and nothing else", session_id=S_MAIN)
    assert MESSAGE_FTS_TABLE not in _table_names(engine)
    factory = fake_factory(dim=DIMENSION)

    incomplete = _refresh_degraded(engine, USER_A, S_MAIN, factory)

    assert incomplete is True
    assert MESSAGE_FTS_TABLE in _table_names(engine)
    assert _match_ids(engine, MESSAGE_FTS_TABLE, FTS_TOKEN) == [M1]


# =========================================================================== DoD-12


def _module_tree() -> ast.Module:
    return ast.parse(inspect.getsource(session_index_module))


def test_the_module_imports_no_fastapi__S024_003_DoD12() -> None:
    """DoD-12 — an AST import walk finds no `fastapi` (or its `starlette` base) import."""
    imported: list[str] = []
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
    offenders = [name for name in imported if name.split(".")[0] in {"fastapi", "starlette"}]
    assert offenders == []


def test_the_module_binds_no_fastapi_symbol__S024_003_DoD12() -> None:
    """DoD-12 — no module-level name is a fastapi/starlette object."""
    offenders = []
    for name, value in vars(session_index_module).items():
        origin = getattr(value, "__module__", None) or getattr(value, "__name__", "")
        if isinstance(origin, str) and origin.split(".")[0] in {"fastapi", "starlette"}:
            offenders.append(name)
    assert offenders == []
