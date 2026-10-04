"""Tests for the record-keeping write paths' degraded session refresh and the coverage flag
— feature 024, step 005 (DoD-1..8).

Every expected value comes from `docs/plans/024.embedding-lifecycle/005.record-keeping-paths.md`
(its Interface intent and Definition of done), from `005.context.md` (the placement — the
refresh is the **last** statement of settle's / re-open's block, so the composed text observes
the post-settle state — and the "Test shape") and from the feature `context.md`:

- **D5** the trigger table: settle, re-open, a settled-row text edit and partner filing refresh
  that session's `session_vec`; a zone append and a zone-row edit do **none**;
- **D6** what text represents a session (persona, then setup, then the `settled_entries` text in
  ascending id, joined with exactly `"\\n\\n"`), and the empty-text rule;
- **D8** the degraded posture catches `NoEmbeddingModelError` **and** `LlmUnreachableError`;
- **U5** a degraded write leaves any existing `session_vec` row exactly as it is (stale);
- the **Wire contract** — `search_coverage_incomplete` on `SettleResponse`, `ReopenResponse`
  and `MessageResponse`, always `false` for a zone row and a zone append.

Bindings come from `## Skeleton` → "Step 005 — frozen interface" (and steps 001 / 002 / 003
for `ensure_vector_tables`, `write_vector`, the table-name constants and the degraded refresh),
and the fake's contract from `## Tests` → "Step 002 — tests" in `status.md`. **Nothing here was
derived from the implementation**; `settle.py`, `messages.py`, `models/stream.py` and
`routers/stream.py` were never read.

Each test name ends `__S024_005_DoD<n>` with the DoD item it covers.

Mechanics (`context.md` "Test conventions", `005.context.md` "Test shape"):
- a real SQLite file per test (`db_engine`) with `schema.metadata.create_all`; `conftest.py` is
  untouched and every fixture is file-local;
- users, a character with a persona, a setup, sessions and `messages` rows in all three states
  are **raw inserts**, every id above 2^60;
- a designated model is raw `llm_servers` + `models` rows at dimension 8 with a null
  `api_key_ref`, so no secret has to resolve;
- the outbound client arrives through the frozen `client_factory=` keyword seam (services) or
  through `dependency_overrides` of the shared `get_llm_client_factory` (the DoD-8 wire cases),
  always using the shared fake in `tests/llm_fakes.py`. No network, no monkeypatching beyond the
  routers' established `configure_logging` neutralisation;
- pre-existing vectors are written with `002`'s `write_vector` after `001`'s
  `ensure_vector_tables`; the tables are then observed only from the test side, through
  `pragma_table_info`, point lookups and `MATCH`. 024 issues no query of its own.
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
from app.db.search_tables import MESSAGE_FTS_TABLE, SESSION_VEC_TABLE, ensure_vector_tables
from app.dependencies import get_llm_client_factory
from app.ids import SnowflakeGenerator
from app.main import create_app
from app.roles import Role
from app.services.embedding import write_vector
from app.services.messages import StreamMessage, append_message, edit_message_text, file_partner_entry
from app.services.passwords import hash_password
from app.services.settle import ReopenResult, SettleResult, reopen, settle
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
USER_A = 1_400_000_000_000_000_001
USER_B = 1_400_000_000_000_000_002

CHAR_A = 1_400_000_000_000_000_011
CHAR_B = 1_400_000_000_000_000_012

SETUP_X = 1_400_000_000_000_000_021

S_MAIN = 1_400_000_000_000_000_031
S_OTHER = 1_400_000_000_000_000_032
S_OF_B = 1_400_000_000_000_000_033

# The ids are chosen in the order the states need them: an earlier settled entry first, then
# the zone's draft, then the zone's head — the zone's **last** row by ascending id is the head
# a settle files, so `M_HEAD` must be the largest of the three (012 D10 / R11).
M_ALPHA = 1_400_000_000_000_000_101
M_DRAFT = 1_400_000_000_000_000_102
M_HEAD = 1_400_000_000_000_000_103
M_ZONE = 1_400_000_000_000_000_104
M_SETTLED = 1_400_000_000_000_000_105

SERVER_ID = 1_400_000_000_000_000_201
MODEL_ID = 1_400_000_000_000_000_202

BASE_URL = "http://embedding.test:8080/v1"
MODEL_NAME = "the-designated-embedding-model"

#: The designated dimension in these tests; 8 keeps them fast (`context.md`).
DIMENSION = 8

#: A timeout deliberately unequal to `Settings`' declared default, so it is distinguishable.
PASSED_TIMEOUT = 12.5

#: D6's first two parts, exactly as stored.
SHEET_A = "Persona P."
DESCRIPTION_X = "Setup S."

#: DoD-1's candidate, verbatim from the step file.
CANDIDATE_TEXT = "Hello there."
#: A token of it, so a `message_fts` MATCH can only come from that row.
CANDIDATE_TOKEN = "there"

#: DoD-3's surviving earlier entry.
TEXT_ALPHA = "Alpha"
#: DoD-4 / DoD-5's before and after, verbatim from the step file.
OLD_WORDS = "Old words"
NEW_WORDS = "New words"
#: DoD-7's filed partner block.
PARTNER_TEXT = "The partner wrote this."
#: DoD-6's zone texts — they must never reach a vector or an index.
ZONE_DRAFT = "A zone draft."
ZONE_EDITED = "A zone draft, revised."

#: Exact float32 values (multiples of 2**-3), so a round-trip compares equal with no tolerance.
#: This is the pre-existing vector U5 says a degraded write must leave exactly as it is.
VECTOR_V8 = [0.5, -1.5, 2.25, 0.0, 1.0, -0.125, 3.5, -2.0]

#: The three kinds a settled record row can carry (DoD-4).
SETTLED_KINDS = ["turn", "decision", "partner"]

LOGIN_PATH = "/api/auth/login"
CHARACTERS_PATH = "/api/characters"
SESSIONS_PATH = "/api/sessions"
MESSAGES_PATH = "/api/messages"

PLAYER_A_NAME = "aster"
PLAYER_A_PASSWORD = "a quiet river at dusk"
PLAYER_A_ID = 1_400_000_000_000_000_301

COVERAGE_FLAG = "search_coverage_incomplete"


# --- composition (D6, used to build the text a test expects to be embedded) --------------


def _composed(*entry_texts: str) -> str:
    """D6's session text for the seeded character and setup, with these settled entries."""
    return "\n\n".join([SHEET_A, DESCRIPTION_X, *entry_texts])


# --- seeding -----------------------------------------------------------------------------


def _servers() -> Table:
    return schema.metadata.tables["llm_servers"]


def _models() -> Table:
    return schema.metadata.tables["models"]


def _insert_user(
    engine: Engine, *, user_id: int, username: str, password: str = "not-a-real-password"
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.users.insert().values(
                id=user_id,
                username=username,
                password_hash=hash_password(password),
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
    setup_id: int | None = SETUP_X,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.insert().values(
                id=session_id,
                user_id=user_id,
                character_id=character_id,
                setup_id=setup_id,
                last_used_at=TIMESTAMP,
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_message(
    engine: Engine,
    *,
    message_id: int,
    body: str,
    session_id: int = S_MAIN,
    user_id: int = USER_A,
    role: str = "user",
    kind: str | None = None,
    related_to: int | None = None,
    settled_at: str | None = None,
) -> None:
    """Raw-insert one `messages` row in a chosen state.

    **zone** = `related_to` and `settled_at` both null; **settled record row** = `settled_at`
    set and `related_to` null; **buried** = `related_to` set (`context.md` Vocabulary).
    """
    with engine.begin() as connection:
        connection.execute(
            schema.messages.insert().values(
                id=message_id,
                user_id=user_id,
                session_id=session_id,
                role=role,
                kind=kind,
                text=body,
                related_to=related_to,
                settled_at=settled_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _zone_row(engine: Engine, message_id: int, body: str, **overrides: Any) -> None:
    _insert_message(engine, message_id=message_id, body=body, **overrides)


def _settled_row(engine: Engine, message_id: int, body: str, *, kind: str = "turn", **overrides: Any) -> None:
    _insert_message(
        engine, message_id=message_id, body=body, kind=kind, settled_at=SEEDED_SETTLED_AT, **overrides
    )


def _seed_designation(engine: Engine, *, dim: int | None = DIMENSION) -> None:
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
                is_enabled=True,
                is_embedding_designated=True,
                embedding_dim=dim,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """The registry applied, two owners, a character with a persona, a setup, three sessions.

    `create_all` only: no virtual table exists yet, so "no `session_vec` row was created"
    (DoD-2) starts from a database that has no such table at all.
    """
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="alice")
    _insert_user(db_engine, user_id=USER_B, username="bob")
    _insert_character(db_engine, character_id=CHAR_A, user_id=USER_A, name="Aria", sheet=SHEET_A)
    _insert_character(db_engine, character_id=CHAR_B, user_id=USER_B, name="Brynn", sheet="Persona B.")
    _insert_setup(
        db_engine, setup_id=SETUP_X, user_id=USER_A, character_id=CHAR_A, name="X", description=DESCRIPTION_X
    )
    _insert_session(db_engine, session_id=S_MAIN)
    _insert_session(db_engine, session_id=S_OTHER)
    _insert_session(db_engine, session_id=S_OF_B, user_id=USER_B, character_id=CHAR_B, setup_id=None)
    return db_engine


@pytest.fixture
def generator() -> SnowflakeGenerator:
    """One real generator per test, so ids minted within a test never collide."""
    return SnowflakeGenerator(node_id=1)


# --- calling the frozen interface (one connection per call) -------------------------------


def _settle(
    engine: Engine,
    factory: FakeClientFactory,
    *,
    user_id: int = USER_A,
    session_id: int = S_MAIN,
) -> SettleResult:
    with engine.connect() as connection:
        return settle(
            connection, user_id, session_id, client_factory=factory, timeout_seconds=PASSED_TIMEOUT
        )


def _reopen(
    engine: Engine,
    factory: FakeClientFactory,
    *,
    user_id: int = USER_A,
    session_id: int = S_MAIN,
) -> ReopenResult:
    with engine.connect() as connection:
        return reopen(
            connection, user_id, session_id, client_factory=factory, timeout_seconds=PASSED_TIMEOUT
        )


def _file_partner(
    engine: Engine,
    generator: SnowflakeGenerator,
    factory: FakeClientFactory,
    body: str,
    *,
    user_id: int = USER_A,
    session_id: int = S_MAIN,
) -> StreamMessage:
    with engine.connect() as connection:
        return file_partner_entry(
            connection,
            generator,
            user_id,
            session_id,
            body,
            client_factory=factory,
            timeout_seconds=PASSED_TIMEOUT,
        )


def _edit(
    engine: Engine,
    factory: FakeClientFactory,
    message_id: int,
    body: str,
    *,
    user_id: int = USER_A,
) -> StreamMessage:
    with engine.connect() as connection:
        return edit_message_text(
            connection,
            user_id,
            message_id,
            body,
            client_factory=factory,
            timeout_seconds=PASSED_TIMEOUT,
        )


def _append(
    engine: Engine,
    generator: SnowflakeGenerator,
    body: str,
    *,
    user_id: int = USER_A,
    session_id: int = S_MAIN,
) -> StreamMessage:
    """`append_message` is unchanged by this step and takes no factory (frozen interface)."""
    with engine.connect() as connection:
        return append_message(connection, generator, user_id, session_id, body)


# --- pre-existing state and observation (tests may query; application code never does) -----


def _preexisting_vector(engine: Engine, session_id: int, vector: list[float]) -> bytes:
    """A committed `session_vec` row, made with `001`'s ensure and `002`'s writer; its blob."""
    with engine.begin() as connection:
        ensure_vector_tables(connection, DIMENSION)
        write_vector(connection, SESSION_VEC_TABLE, session_id, vector)
    blob = _stored_blob(engine, session_id)
    assert blob is not None
    return blob


def _key_column(connection: Connection, table_name: str) -> str | None:
    """The vec0 table's key column, or `None` when the table does not exist."""
    rows = connection.execute(
        text("SELECT name FROM pragma_table_info(:table_name) WHERE pk = 1"),
        {"table_name": table_name},
    ).all()
    return None if not rows else str(rows[0][0])


def _stored_blob(engine: Engine, session_id: int) -> bytes | None:
    """The raw stored blob for one session id — `None` when there is no row (or no table)."""
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


def _vector_row_count(engine: Engine) -> int:
    with engine.connect() as connection:
        if _key_column(connection, SESSION_VEC_TABLE) is None:
            return 0
        return int(connection.execute(text(f"SELECT count(*) FROM {SESSION_VEC_TABLE}")).scalar_one())


def _match_ids(engine: Engine, table_name: str, token: str) -> list[int]:
    """The rowids a full-text `MATCH` on one token returns, ascending."""
    query = text(f"SELECT rowid FROM {table_name} WHERE {table_name} MATCH :token ORDER BY rowid")
    with engine.connect() as connection:
        return [int(row[0]) for row in connection.execute(query, {"token": token}).all()]


def _stored_text(engine: Engine, message_id: int) -> str:
    with engine.connect() as connection:
        return str(
            connection.execute(
                select(schema.messages.c.text).where(schema.messages.c.id == message_id)
            ).scalar_one()
        )


def _record(engine: Engine, *, user_id: int = USER_A, session_id: int = S_MAIN) -> list[tuple[int, Any]]:
    """The session's record through the `settled_entries` selectable: (id, kind), id ascending."""
    statement = schema.settled_entries.where(
        schema.messages.c.session_id == session_id,
        schema.messages.c.user_id == user_id,
    ).order_by(schema.messages.c.id)
    with engine.connect() as connection:
        return [(int(row.id), row.kind) for row in connection.execute(statement)]


def _record_ids(engine: Engine, *, user_id: int = USER_A, session_id: int = S_MAIN) -> list[int]:
    return [message_id for message_id, _ in _record(engine, user_id=user_id, session_id=session_id)]


def _zone_ids(engine: Engine, *, user_id: int = USER_A, session_id: int = S_MAIN) -> list[int]:
    statement = schema.current_zone.where(
        schema.messages.c.session_id == session_id,
        schema.messages.c.user_id == user_id,
    ).order_by(schema.messages.c.id)
    with engine.connect() as connection:
        return [int(row.id) for row in connection.execute(statement)]


def _settled_at(engine: Engine, message_id: int) -> str | None:
    with engine.connect() as connection:
        value = connection.execute(
            select(schema.messages.c.settled_at).where(schema.messages.c.id == message_id)
        ).scalar_one()
    return None if value is None else str(value)


def _kind(engine: Engine, message_id: int) -> str | None:
    with engine.connect() as connection:
        value = connection.execute(
            select(schema.messages.c.kind).where(schema.messages.c.id == message_id)
        ).scalar_one()
    return None if value is None else str(value)


# =========================================================================== DoD-1


def test_a_settle_with_a_model_embeds_the_post_settle_text__S024_005_DoD1(engine: Engine) -> None:
    """DoD-1 — D5 / D6 / R11 and `005.context.md` Placement: the refresh is the **last**
    statement of settle's block, so the composed text ends with the entry's **post-settle**
    stored text (settle rewrites the head's text in the same UPDATE that sets `settled_at`).

    The flag is false, the stored vector is the fake's vector for that composed text, exactly
    one client was built for exactly one embed call (D1), and `message_fts` finds the text.
    """
    _seed_designation(engine)
    _zone_row(engine, M_HEAD, CANDIDATE_TEXT, role="assistant")
    factory = fake_factory(DIMENSION)

    result = _settle(engine, factory)

    assert result.search_coverage_incomplete is False
    assert result.entry_id == M_HEAD
    assert _zone_ids(engine) == []
    assert _record_ids(engine) == [M_HEAD]

    # The text as now stored — what D6 composes, read after the settle rewrote it.
    stored = _stored_text(engine, M_HEAD)
    assert stored == CANDIDATE_TEXT
    expected_text = _composed(stored)
    assert _stored_vector(engine, S_MAIN) == embedding_vector(expected_text, DIMENSION)
    assert _vector_row_count(engine) == 1
    assert factory.call_count == 1
    assert factory.embed_calls == [(MODEL_NAME, (expected_text,))]
    assert _match_ids(engine, MESSAGE_FTS_TABLE, CANDIDATE_TOKEN) == [M_HEAD]


# =========================================================================== DoD-2


def test_a_settle_without_a_model_still_settles_and_flags_coverage__S024_005_DoD2(
    engine: Engine,
) -> None:
    """DoD-2 — US-112.AC-1 / D8: with **no** designated model `settle` raises nothing, the entry
    is settled and the zone is empty, the flag is true, and no `session_vec` row exists."""
    _zone_row(engine, M_HEAD, CANDIDATE_TEXT)
    factory = fake_factory(DIMENSION)

    result = _settle(engine, factory)

    assert result.search_coverage_incomplete is True
    assert result.entry_id == M_HEAD
    assert _record_ids(engine) == [M_HEAD]
    assert _settled_at(engine, M_HEAD) is not None
    assert _zone_ids(engine) == []
    assert _stored_blob(engine, S_MAIN) is None
    assert _vector_row_count(engine) == 0


def test_a_settle_without_a_model_leaves_a_stale_vector_byte_identical__S024_005_DoD2(
    engine: Engine,
) -> None:
    """DoD-2 — U5: a degraded write leaves an existing `session_vec` row exactly as it is, which
    makes it stale. Nothing records the staleness; the rebuild is the remedy."""
    before = _preexisting_vector(engine, S_MAIN, VECTOR_V8)
    _zone_row(engine, M_HEAD, CANDIDATE_TEXT)
    factory = fake_factory(DIMENSION)

    result = _settle(engine, factory)

    assert result.search_coverage_incomplete is True
    assert _record_ids(engine) == [M_HEAD]
    assert _zone_ids(engine) == []
    assert _stored_blob(engine, S_MAIN) == before
    assert _stored_vector(engine, S_MAIN) == VECTOR_V8
    assert _vector_row_count(engine) == 1


def test_a_settle_with_an_unreachable_provider_has_the_same_outcome__S024_005_DoD2(
    engine: Engine,
) -> None:
    """DoD-2 — D8: the degraded path catches `LlmUnreachableError` too, so the outcome is the
    same as the missing-designation one: settled, flag true, the old vector untouched."""
    _seed_designation(engine)
    before = _preexisting_vector(engine, S_MAIN, VECTOR_V8)
    _zone_row(engine, M_HEAD, CANDIDATE_TEXT)
    factory = unreachable_factory(DIMENSION)

    result = _settle(engine, factory)

    assert result.search_coverage_incomplete is True
    assert _record_ids(engine) == [M_HEAD]
    assert _zone_ids(engine) == []
    assert _stored_blob(engine, S_MAIN) == before
    # D1: one client per write operation, and the embed was really attempted.
    assert factory.call_count == 1


# =========================================================================== DoD-3


def _seed_reopenable(engine: Engine) -> None:
    """An earlier settled entry that survives, then a two-row zone — so a settle buries one row
    and the re-open has a group to restore while the record stays non-empty."""
    _settled_row(engine, M_ALPHA, TEXT_ALPHA)
    _zone_row(engine, M_DRAFT, "A draft line.")
    _zone_row(engine, M_HEAD, CANDIDATE_TEXT)


def test_a_reopen_with_a_model_embeds_a_text_without_the_reopened_entry__S024_005_DoD3(
    engine: Engine,
) -> None:
    """DoD-3 — D5 / D6 / R11: the re-open's refresh observes the post-re-open state, so the
    embedded text is the record **without** the re-opened entry: the flag is false and the row
    holds the fake's vector for the surviving entry alone."""
    _seed_designation(engine)
    _seed_reopenable(engine)
    settle_factory = fake_factory(DIMENSION)
    settled = _settle(engine, settle_factory)
    assert settled.entry_id == M_HEAD
    reopen_factory = fake_factory(DIMENSION)

    result = _reopen(engine, reopen_factory)

    assert result.search_coverage_incomplete is False
    assert result.reopened_id == M_HEAD
    assert result.restored_ids == [M_DRAFT]
    assert _record_ids(engine) == [M_ALPHA]

    expected_text = _composed(TEXT_ALPHA)
    assert _stored_vector(engine, S_MAIN) == embedding_vector(expected_text, DIMENSION)
    assert reopen_factory.embed_calls == [(MODEL_NAME, (expected_text,))]
    # The point of the clause: the re-opened entry's text is no longer in what was embedded.
    assert _stored_text(engine, M_HEAD) not in expected_text


def test_a_reopen_without_a_model_still_reopens_and_flags_coverage__S024_005_DoD3(
    engine: Engine,
) -> None:
    """DoD-3 — US-112.AC-1 / D8: with no designated model `reopen` succeeds and its flag is
    true; the group is back in the zone and the earlier entry is still recorded."""
    _seed_reopenable(engine)
    factory = fake_factory(DIMENSION)
    _settle(engine, factory)

    result = _reopen(engine, factory)

    assert result.search_coverage_incomplete is True
    assert result.reopened_id == M_HEAD
    assert result.restored_ids == [M_DRAFT]
    assert _zone_ids(engine) == [M_DRAFT, M_HEAD]
    assert _record_ids(engine) == [M_ALPHA]


# =========================================================================== DoD-4


@pytest.mark.parametrize("kind", SETTLED_KINDS)
def test_a_settled_edit_with_a_model_embeds_the_new_text__S024_005_DoD4(
    engine: Engine, kind: str
) -> None:
    """DoD-4 — US-110.AC-2 / US-109.AC-2 / UC-078: editing a settled record row of any kind (a
    turn, a decision, a settled partner block) re-embeds that session. The flag is false, and the
    embedded composed text carries `"New words"` and not `"Old words"`."""
    _seed_designation(engine)
    _settled_row(engine, M_SETTLED, OLD_WORDS, kind=kind)
    factory = fake_factory(DIMENSION)

    edited = _edit(engine, factory, M_SETTLED, NEW_WORDS)

    assert edited.search_coverage_incomplete is False
    assert edited.text == NEW_WORDS
    assert _stored_text(engine, M_SETTLED) == NEW_WORDS

    expected_text = _composed(NEW_WORDS)
    assert _stored_vector(engine, S_MAIN) == embedding_vector(expected_text, DIMENSION)
    assert factory.embed_calls == [(MODEL_NAME, (expected_text,))]
    (_, (embedded,)) = factory.embed_calls[0]
    assert NEW_WORDS in embedded
    assert OLD_WORDS not in embedded


# =========================================================================== DoD-5


def test_a_settled_edit_without_a_model_still_saves_and_flags_coverage__S024_005_DoD5(
    engine: Engine,
) -> None:
    """DoD-5 — US-112.AC-1 / US-112.AC-2 / U5: with no designated model the edit **saves** —
    the stored text and the returned row both carry `"New words"` — the flag is true, and the
    pre-existing `session_vec` row is byte-identical, hence stale."""
    before = _preexisting_vector(engine, S_MAIN, VECTOR_V8)
    _settled_row(engine, M_SETTLED, OLD_WORDS)
    factory = fake_factory(DIMENSION)

    edited = _edit(engine, factory, M_SETTLED, NEW_WORDS)

    assert edited.search_coverage_incomplete is True
    assert edited.text == NEW_WORDS
    assert _stored_text(engine, M_SETTLED) == NEW_WORDS
    assert _stored_blob(engine, S_MAIN) == before
    assert _stored_vector(engine, S_MAIN) == VECTOR_V8
    assert _vector_row_count(engine) == 1


# =========================================================================== DoD-6


def test_a_zone_append_does_no_vector_work__S024_005_DoD6(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-6 — US-115 / D5: a zone append is not a record-keeping write. With a designated model
    in place it returns the default flag false and leaves the `session_vec` row untouched, and
    the recording factory in play registers nothing.

    `append_message` is unchanged by this step and takes no factory (frozen interface), so
    "zero factory calls" is measured as "the one factory in play records nothing across it".
    """
    _seed_designation(engine)
    before = _preexisting_vector(engine, S_MAIN, VECTOR_V8)
    factory = fake_factory(DIMENSION)

    created = _append(engine, generator, ZONE_DRAFT)

    assert created.search_coverage_incomplete is False
    assert created.text == ZONE_DRAFT
    assert factory.call_count == 0
    assert factory.embed_calls == []
    assert _stored_blob(engine, S_MAIN) == before
    assert _vector_row_count(engine) == 1


def test_a_zone_row_edit_does_no_vector_work__S024_005_DoD6(engine: Engine) -> None:
    """DoD-6 — US-115 / D5 / Wire contract: a zone-row edit builds **no** client at all and
    leaves the `session_vec` row untouched; its flag is false. This is the record-row-vs-zone
    dispatch: the same call on a settled row does embed (DoD-4)."""
    _seed_designation(engine)
    before = _preexisting_vector(engine, S_MAIN, VECTOR_V8)
    _zone_row(engine, M_ZONE, ZONE_DRAFT)
    factory = fake_factory(DIMENSION)

    edited = _edit(engine, factory, M_ZONE, ZONE_EDITED)

    assert edited.search_coverage_incomplete is False
    assert edited.text == ZONE_EDITED
    assert _stored_text(engine, M_ZONE) == ZONE_EDITED
    assert factory.call_count == 0
    assert factory.embed_calls == []
    assert _stored_blob(engine, S_MAIN) == before
    assert _vector_row_count(engine) == 1


# =========================================================================== DoD-7


def test_partner_filing_with_a_model_embeds_the_filed_text__S024_005_DoD7(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-7 — D5: filing the partner's block is a record-keeping write, so the session is
    re-embedded inside the same transaction. The flag is false and the composed text embedded
    contains the filed text."""
    _seed_designation(engine)
    factory = fake_factory(DIMENSION)

    filed = _file_partner(engine, generator, factory, PARTNER_TEXT)

    assert filed.search_coverage_incomplete is False
    expected_text = _composed(PARTNER_TEXT)
    assert _stored_vector(engine, S_MAIN) == embedding_vector(expected_text, DIMENSION)
    assert factory.embed_calls == [(MODEL_NAME, (expected_text,))]
    (_, (embedded,)) = factory.embed_calls[0]
    assert PARTNER_TEXT in embedded


def test_partner_filing_without_a_model_still_files_and_flags_coverage__S024_005_DoD7(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-7 — US-121.AC-1 unchanged / US-112.AC-1: with no designated model the entry is still
    filed — born settled, kind `partner`, in the record — and the flag is true."""
    factory = fake_factory(DIMENSION)

    filed = _file_partner(engine, generator, factory, PARTNER_TEXT)

    assert filed.search_coverage_incomplete is True
    assert filed.text == PARTNER_TEXT
    assert filed.kind == "partner"
    assert filed.settled_at is not None
    assert _record(engine) == [(filed.id, "partner")]
    assert _kind(engine, filed.id) == "partner"
    assert _zone_ids(engine) == []
    assert _stored_blob(engine, S_MAIN) is None


# =========================================================================== DoD-8
# The wire, through `create_app()` with `dependency_overrides` for the two keys the skeleton
# recorded: `app.dependencies.get_llm_client_factory` and `app.config.get_settings`.


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
    """A fresh client carrying the roleplayer's session cookie — the stream-router login."""
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
    """The wire cases' database: the registry plus one roleplayer who logs in.

    Characters and sessions come from their own routes, as the stream router's tests do.
    """
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(
        db_engine, user_id=PLAYER_A_ID, username=PLAYER_A_NAME, password=PLAYER_A_PASSWORD
    )
    return db_engine


def _ok(response: httpx.Response, status: int) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def _new_session(client: TestClient) -> str:
    """A character with a non-blank persona (so the session text is never empty), then a session.

    The persona is non-blank on purpose: by D6 an empty session text is "nothing to embed" and
    counts as **complete**, which would not exercise the degraded answer these cases pin.
    """
    created = client.post(CHARACTERS_PATH, json={"name": "Aria", "sheet": SHEET_A})
    assert created.status_code == 201, created.text
    character = created.json()
    started = client.post(f"{CHARACTERS_PATH}/{character['id']}/sessions", json={})
    assert started.status_code == 201, started.text
    return str(started.json()["id"])


def _wire_append(client: TestClient, session_id: str, body: str) -> dict[str, Any]:
    return _ok(client.post(f"{SESSIONS_PATH}/{session_id}/zone/messages", json={"text": body}), 201)


def test_settle_answers_the_coverage_flag_true_without_a_model__S024_005_DoD8(
    wire_engine: Engine, db_settings: Settings
) -> None:
    """DoD-8 — US-112.AC-2 / Wire contract: `POST …/settle` answers 200 with
    `search_coverage_incomplete: true` alongside `entry_id`, `kind` and `buried_ids`."""
    factory = fake_factory(DIMENSION)
    with _application(db_settings, factory) as application:
        client = _player_a(application, db_settings)
        session_id = _new_session(client)
        message = _wire_append(client, session_id, CANDIDATE_TEXT)

        body = _ok(client.post(f"{SESSIONS_PATH}/{session_id}/settle"), 200)

    assert body == {
        "entry_id": message["id"],
        "kind": "turn",
        "buried_ids": [],
        COVERAGE_FLAG: True,
    }


def test_reopen_answers_the_coverage_flag_true_without_a_model__S024_005_DoD8(
    wire_engine: Engine, db_settings: Settings
) -> None:
    """DoD-8 — Wire contract: `POST …/reopen` answers 200 with the flag true.

    An earlier entry is settled first and stays recorded, so the session text after the re-open
    is non-empty and the write really does need a model (D6's empty-text rule would otherwise
    make the outcome complete).
    """
    factory = fake_factory(DIMENSION)
    with _application(db_settings, factory) as application:
        client = _player_a(application, db_settings)
        session_id = _new_session(client)
        _wire_append(client, session_id, "An earlier line.")
        _ok(client.post(f"{SESSIONS_PATH}/{session_id}/settle"), 200)
        buried = _wire_append(client, session_id, "A draft line.")
        head = _wire_append(client, session_id, CANDIDATE_TEXT)
        _ok(client.post(f"{SESSIONS_PATH}/{session_id}/settle"), 200)

        body = _ok(client.post(f"{SESSIONS_PATH}/{session_id}/reopen"), 200)

    assert body == {
        "reopened_id": head["id"],
        "restored_ids": [buried["id"]],
        COVERAGE_FLAG: True,
    }


def test_a_settled_row_patch_answers_the_coverage_flag_true_without_a_model__S024_005_DoD8(
    wire_engine: Engine, db_settings: Settings
) -> None:
    """DoD-8 — UC-078 / Wire contract: `PATCH /api/messages/{id}` on a settled row answers 200
    with the flag true, and the edited text on the wire."""
    factory = fake_factory(DIMENSION)
    with _application(db_settings, factory) as application:
        client = _player_a(application, db_settings)
        session_id = _new_session(client)
        message = _wire_append(client, session_id, OLD_WORDS)
        _ok(client.post(f"{SESSIONS_PATH}/{session_id}/settle"), 200)

        body = _ok(
            client.patch(f"{MESSAGES_PATH}/{message['id']}", json={"text": NEW_WORDS}), 200
        )

    assert body[COVERAGE_FLAG] is True
    assert body["text"] == NEW_WORDS
    assert body["settled_at"] is not None


def test_partner_filing_answers_the_coverage_flag_true_without_a_model__S024_005_DoD8(
    wire_engine: Engine, db_settings: Settings
) -> None:
    """DoD-8 — Wire contract: `POST /api/sessions/{id}/entries` answers its success status (201)
    with the flag true."""
    factory = fake_factory(DIMENSION)
    with _application(db_settings, factory) as application:
        client = _player_a(application, db_settings)
        session_id = _new_session(client)

        body = _ok(
            client.post(
                f"{SESSIONS_PATH}/{session_id}/entries",
                json={"kind": "partner", "text": PARTNER_TEXT},
            ),
            201,
        )

    assert body[COVERAGE_FLAG] is True
    assert body["kind"] == "partner"
    assert body["text"] == PARTNER_TEXT


def test_a_zone_append_answers_the_coverage_flag_false__S024_005_DoD8(
    wire_engine: Engine, db_settings: Settings
) -> None:
    """DoD-8 — Wire contract: a zone append carries **always `false`**, even with no designated
    model, because it does no vector work at all (D5)."""
    factory = fake_factory(DIMENSION)
    with _application(db_settings, factory) as application:
        client = _player_a(application, db_settings)
        session_id = _new_session(client)

        body = _ok(
            client.post(f"{SESSIONS_PATH}/{session_id}/zone/messages", json={"text": ZONE_DRAFT}),
            201,
        )

    assert body[COVERAGE_FLAG] is False
    assert body["settled_at"] is None


def test_settle_answers_the_coverage_flag_false_with_a_model__S024_005_DoD8(
    wire_engine: Engine, db_settings: Settings
) -> None:
    """DoD-8 — Wire contract: with a designated model and the fake factory override the very same
    settle answers `false`, so the flag reports the outcome and not a constant."""
    _seed_designation(wire_engine)
    factory = fake_factory(DIMENSION)
    with _application(db_settings, factory) as application:
        client = _player_a(application, db_settings)
        session_id = _new_session(client)
        message = _wire_append(client, session_id, CANDIDATE_TEXT)

        body = _ok(client.post(f"{SESSIONS_PATH}/{session_id}/settle"), 200)

    assert body == {
        "entry_id": message["id"],
        "kind": "turn",
        "buried_ids": [],
        COVERAGE_FLAG: False,
    }
    assert factory.call_count == 1
    assert factory.calls == [(BASE_URL, None, db_settings.llm_request_timeout_seconds)]
