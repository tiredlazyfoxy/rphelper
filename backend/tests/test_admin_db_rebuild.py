"""Tests for the vector-index rebuild route — fast feature 002 (vector-index-rebuild).

Covered route: ``POST /api/admin/database/rebuild`` on the admin database router (router-level
``require_admin``), which calls ``app.services.index_rebuild.rebuild_index`` once.

Every expected value comes from ``docs/plans/fast/002.vector-index-rebuild/plan.md`` (Interface
intent + Definition of done DoD-1 .. DoD-14) and ``context.md`` (the record-row predicate
``settled_at IS NOT NULL AND related_to IS NULL``; memo text is the raw body; session text is
``compose_session_text`` with the owning user; one all-or-nothing transaction; the response is the
fixed list of the four derived table names and nothing derived from user content). The status of
an unreachable LLM (502 ``llm_unreachable``) is the existing error model's (``test_errors.py``).
Bindings come from ``## Skeleton`` in ``status.md``: the route path and 200 status,
``RebuildReportResponse.tables_rebuilt`` and the module constant
``app.services.index_rebuild.REBUILD_EMBED_BATCH_SIZE`` (read at call time, so monkeypatchable).
Nothing is read from the implementation.

Each test name ends ``__F002_DoD<n>``. DoD-15 .. DoD-20 are frontend tests
(``frontend/tests/admin/databasePageRebuild.test.ts`` and ``DatabasePage.rebuild.test.tsx``);
DoD-21 is ``[manual/live]`` and carries no test.

Mechanics, following ``test_admin_db_import.py``, ``test_memos_router.py`` and
``test_session_index.py``: the real ``create_app()`` pinned to the per-test ``tmp_path`` database
through ``dependency_overrides[get_settings]``, with the shared ``get_llm_client_factory``
overridden by a fake from ``tests/llm_fakes.py``; raw inserts with ids above 2^60; the FTS tables
are ensured before content is inserted (so their triggers index it), and pre-existing vectors are
written with ``ensure_vector_tables`` + ``write_vector``. The derived tables are observed only from
the test side — ``vector_table_dimension``, point lookups and ``MATCH``.
"""

import struct
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, Table, text

from app.config import Settings, get_settings
from app.db import schema
from app.db.search_tables import (
    MEMO_FTS_TABLE,
    MEMO_VEC_TABLE,
    MESSAGE_FTS_TABLE,
    SESSION_VEC_TABLE,
    ensure_fts_tables,
    ensure_vector_tables,
    vector_table_dimension,
)
from app.dependencies import get_llm_client_factory
from app.main import create_app
from app.roles import Role
from app.services.embedding import write_vector
from app.services.passwords import hash_password
from app.services.session_index import compose_session_text
from tests.llm_fakes import (
    FakeClientFactory,
    embedding_vector,
    fake_factory,
    unreachable_factory,
)

PREFIX = "/api/admin/database"
REBUILD_PATH = f"{PREFIX}/rebuild"
MEMOS_PATH = "/api/memos"
LOGIN_PATH = "/api/auth/login"

#: plan.md "Rebuild report model" / DoD-1 — always these four, in this order.
EXPECTED_TABLES = ["memo_vec", "session_vec", "memo_fts", "message_fts"]

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
SEEDED_SETTLED_AT = "2025-12-31T00:00:00.000000+00:00"

#: The designated dimension; 8 keeps the tests fast. 16 is "some other dimension" (DoD-5, DoD-12).
DIMENSION = 8
OTHER_DIMENSION = 16

BASE = 1_400_000_000_000_002_000

ADMIN_ID = BASE + 1
USER_A = BASE + 2
USER_B = BASE + 3

CHAR_A = BASE + 11
CHAR_B = BASE + 12

SESSION_A = BASE + 21
SESSION_B = BASE + 22

MEMO_A = BASE + 31
MEMO_B = BASE + 32
MEMO_A2 = BASE + 33
MEMO_BLANK = BASE + 34

MESSAGE_RECORD_A = BASE + 41
MESSAGE_RECORD_B = BASE + 42
MESSAGE_ZONE = BASE + 43
MESSAGE_BURIED = BASE + 44

#: DoD-4 — vector ids that match no memo / session.
ORPHAN_MEMO_ID = BASE + 91
ORPHAN_SESSION_ID = BASE + 92

SERVER_ID = BASE + 201
MODEL_ID = BASE + 202
BASE_URL = "http://embedding.test:8080/v1"
MODEL_NAME = "the-designated-embedding-model"

ADMIN_NAME = "founder"
ADMIN_PASSWORD = "correct horse battery staple"
PLAYER_A_NAME = "aster"
PLAYER_A_PASSWORD = "a quiet river at dusk"
PLAYER_B_NAME = "briar"
PLAYER_B_PASSWORD = "salt and lantern light"

#: Nonsense tokens, so a `MATCH` can only come from the row that carries one.
MEMO_A_TOKEN = "memoalpharebuildxyz"
MEMO_B_TOKEN = "memobetarebuildxyz"
MEMO_A2_TOKEN = "memogammarebuildxyz"
RECORD_A_TOKEN = "recordalpharebuildxyz"
RECORD_B_TOKEN = "recordbetarebuildxyz"
ZONE_TOKEN = "zonerebuildxyz"
BURIED_TOKEN = "buriedrebuildxyz"
NEW_MEMO_TOKEN = "freshmemorebuildxyz"

MEMO_A_BODY = f"Aster remembers the {MEMO_A_TOKEN} by the harbour."
MEMO_B_BODY = f"Briar keeps the {MEMO_B_TOKEN} under the floorboards."
MEMO_A2_BODY = f"A second note of Aster's about the {MEMO_A2_TOKEN}."
BLANK_BODY = ""

SHEET_A = "Persona of Aria, a lighthouse keeper."
SHEET_B = "Persona of Brynn, a river smuggler."
RECORD_A_TEXT = f"Aria lights the lamp and mentions {RECORD_A_TOKEN}."
RECORD_B_TEXT = f"Brynn slips past the weir and mentions {RECORD_B_TOKEN}."
ZONE_TEXT = f"An unsettled draft that mentions {ZONE_TOKEN}."
BURIED_TEXT = f"A superseded take that mentions {BURIED_TOKEN}."

#: Every piece of user-authored text seeded, for the "no user text in the response" check.
USER_TEXTS = (
    MEMO_A_BODY,
    MEMO_B_BODY,
    MEMO_A2_BODY,
    SHEET_A,
    SHEET_B,
    RECORD_A_TEXT,
    RECORD_B_TEXT,
    ZONE_TEXT,
    BURIED_TEXT,
)

ALL_TOKENS = (
    MEMO_A_TOKEN,
    MEMO_B_TOKEN,
    MEMO_A2_TOKEN,
    RECORD_A_TOKEN,
    RECORD_B_TOKEN,
    ZONE_TOKEN,
    BURIED_TOKEN,
)

NO_EMBEDDING_MODEL = "no_embedding_model"
LLM_UNREACHABLE = "llm_unreachable"
NOT_AUTHENTICATED = "not_authenticated"
INSUFFICIENT_ROLE = "insufficient_role"


# --- fixtures ------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _quiet_factory_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the factory's logging call so these tests touch no global sinks."""
    monkeypatch.setattr("app.main.configure_logging", lambda settings: None)


def _insert(engine: Engine, table: Table, **values: Any) -> None:
    with engine.begin() as connection:
        connection.execute(table.insert().values(**values))


def _insert_user(engine: Engine, *, user_id: int, username: str, password: str, role: Role) -> None:
    _insert(
        engine,
        schema.users,
        id=user_id,
        username=username,
        password_hash=hash_password(password),
        role=role,
        is_enabled=True,
        rp_language=None,
        preferred_language=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_character(engine: Engine, *, character_id: int, user_id: int, name: str, sheet: str) -> None:
    _insert(
        engine,
        schema.characters,
        id=character_id,
        user_id=user_id,
        name=name,
        sheet=sheet,
        archived_at=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_session(engine: Engine, *, session_id: int, user_id: int, character_id: int) -> None:
    _insert(
        engine,
        schema.sessions,
        id=session_id,
        user_id=user_id,
        character_id=character_id,
        setup_id=None,
        last_used_at=TIMESTAMP,
        archived_at=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_memo(engine: Engine, *, memo_id: int, user_id: int, character_id: int, body: str) -> None:
    _insert(
        engine,
        schema.memos,
        id=memo_id,
        user_id=user_id,
        scope="character",
        scope_id=character_id,
        body=body,
        is_enabled=True,
        is_forced=False,
        sort_key=100,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_message(
    engine: Engine,
    *,
    message_id: int,
    body: str,
    user_id: int,
    session_id: int,
    related_to: int | None = None,
    settled_at: str | None = None,
) -> None:
    """A `messages` row: record (settled, not related), zone (unsettled, not related) or buried
    (related, unsettled — the schema forbids `related_to` and `settled_at` together)."""
    _insert(
        engine,
        schema.messages,
        id=message_id,
        user_id=user_id,
        session_id=session_id,
        role="user",
        kind=None,
        text=body,
        related_to=related_to,
        settled_at=settled_at,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _seed_designation(engine: Engine, *, dim: int = DIMENSION) -> None:
    """One server and one enabled, designated embedding model; null `api_key_ref`."""
    _insert(
        engine,
        schema.metadata.tables["llm_servers"],
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
    _insert(
        engine,
        schema.metadata.tables["models"],
        id=MODEL_ID,
        server_id=SERVER_ID,
        model_name=MODEL_NAME,
        is_enabled=True,
        is_embedding_designated=True,
        embedding_dim=dim,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _seed_accounts(engine: Engine) -> None:
    """Registry, both FTS tables (with triggers), one admin and two roleplayers."""
    with engine.begin() as connection:
        schema.metadata.create_all(connection)
        ensure_fts_tables(connection)
    _insert_user(engine, user_id=ADMIN_ID, username=ADMIN_NAME, password=ADMIN_PASSWORD, role=Role.ADMIN)
    _insert_user(
        engine, user_id=USER_A, username=PLAYER_A_NAME, password=PLAYER_A_PASSWORD, role=Role.ROLEPLAYER
    )
    _insert_user(
        engine, user_id=USER_B, username=PLAYER_B_NAME, password=PLAYER_B_PASSWORD, role=Role.ROLEPLAYER
    )


def _seed_content(engine: Engine) -> None:
    """Content owned by two different users: memos (one blank), sessions and messages in all states."""
    _insert_character(engine, character_id=CHAR_A, user_id=USER_A, name="Aria", sheet=SHEET_A)
    _insert_character(engine, character_id=CHAR_B, user_id=USER_B, name="Brynn", sheet=SHEET_B)
    _insert_session(engine, session_id=SESSION_A, user_id=USER_A, character_id=CHAR_A)
    _insert_session(engine, session_id=SESSION_B, user_id=USER_B, character_id=CHAR_B)

    _insert_memo(engine, memo_id=MEMO_A, user_id=USER_A, character_id=CHAR_A, body=MEMO_A_BODY)
    _insert_memo(engine, memo_id=MEMO_B, user_id=USER_B, character_id=CHAR_B, body=MEMO_B_BODY)
    _insert_memo(engine, memo_id=MEMO_A2, user_id=USER_A, character_id=CHAR_A, body=MEMO_A2_BODY)
    _insert_memo(engine, memo_id=MEMO_BLANK, user_id=USER_B, character_id=CHAR_B, body=BLANK_BODY)

    _insert_message(
        engine,
        message_id=MESSAGE_RECORD_A,
        body=RECORD_A_TEXT,
        user_id=USER_A,
        session_id=SESSION_A,
        settled_at=SEEDED_SETTLED_AT,
    )
    _insert_message(
        engine,
        message_id=MESSAGE_RECORD_B,
        body=RECORD_B_TEXT,
        user_id=USER_B,
        session_id=SESSION_B,
        settled_at=SEEDED_SETTLED_AT,
    )
    _insert_message(engine, message_id=MESSAGE_ZONE, body=ZONE_TEXT, user_id=USER_A, session_id=SESSION_A)
    _insert_message(
        engine,
        message_id=MESSAGE_BURIED,
        body=BURIED_TEXT,
        user_id=USER_A,
        session_id=SESSION_A,
        related_to=MESSAGE_RECORD_A,
        settled_at=None,
    )


ELIGIBLE_MEMOS = {MEMO_A: MEMO_A_BODY, MEMO_B: MEMO_B_BODY, MEMO_A2: MEMO_A2_BODY}
SESSIONS = {SESSION_A: USER_A, SESSION_B: USER_B}


@pytest.fixture
def factory() -> FakeClientFactory:
    return fake_factory(DIMENSION)


def _pinned_application(db_settings: Settings, client_factory: FakeClientFactory) -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: db_settings
    app.dependency_overrides[get_llm_client_factory] = lambda: client_factory
    return app


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """Accounts, the designation at dimension 8, and content for two users."""
    _seed_accounts(db_engine)
    _seed_designation(db_engine)
    _seed_content(db_engine)
    return db_engine


@pytest.fixture
def application(db_settings: Settings, engine: Engine, factory: FakeClientFactory) -> Iterator[FastAPI]:
    app = _pinned_application(db_settings, factory)
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


# --- login helpers -------------------------------------------------------------------


def _parse_set_cookie(header: str) -> tuple[str, str]:
    first = header.split(";")[0]
    name, _, value = first.partition("=")
    return name.strip(), value.strip().strip('"')


def _as(application: FastAPI, settings: Settings, username: str, password: str) -> TestClient:
    """A fresh client carrying exactly this account's session cookie — never shared."""
    response = TestClient(application).post(LOGIN_PATH, json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    tokens = [
        value
        for name, value in (_parse_set_cookie(h) for h in response.headers.get_list("set-cookie"))
        if name == settings.session_cookie_name
    ]
    assert len(tokens) == 1 and tokens[0]
    fresh = TestClient(application)
    fresh.cookies.set(settings.session_cookie_name, tokens[0])
    return fresh


def _admin(application: FastAPI, settings: Settings) -> TestClient:
    return _as(application, settings, ADMIN_NAME, ADMIN_PASSWORD)


def _player_a(application: FastAPI, settings: Settings) -> TestClient:
    return _as(application, settings, PLAYER_A_NAME, PLAYER_A_PASSWORD)


def _anonymous(application: FastAPI) -> TestClient:
    return TestClient(application)


def _rebuild(client: TestClient) -> httpx.Response:
    return client.post(REBUILD_PATH)


def _assert_error(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error, dict)
    assert error["code"] == code, error
    return error


# --- pre-existing derived state ----------------------------------------------------------


def _vector(dim: int, seed: str) -> list[float]:
    return embedding_vector(seed, dim)


def _preexisting_vectors(engine: Engine, *, dim: int = DIMENSION, orphans: bool = True) -> None:
    """Committed vector rows at `dim`: one per real memo/session (stale values) plus orphans."""
    with engine.begin() as connection:
        ensure_vector_tables(connection, dim)
        for memo_id in (MEMO_A, MEMO_B, MEMO_BLANK):
            write_vector(connection, MEMO_VEC_TABLE, memo_id, _vector(dim, f"stale memo {memo_id}"))
        write_vector(connection, SESSION_VEC_TABLE, SESSION_A, _vector(dim, "stale session a"))
        if orphans:
            write_vector(connection, MEMO_VEC_TABLE, ORPHAN_MEMO_ID, _vector(dim, "orphan memo"))
            write_vector(connection, SESSION_VEC_TABLE, ORPHAN_SESSION_ID, _vector(dim, "orphan session"))


def _drop_memo_fts_row(engine: Engine, memo_id: int, body: str) -> None:
    """FTS5's own external-content 'delete' command — the index loses this memo's row."""
    with engine.begin() as connection:
        connection.execute(
            text(f"INSERT INTO {MEMO_FTS_TABLE}({MEMO_FTS_TABLE}, rowid, body) VALUES('delete', :id, :body)"),
            {"id": memo_id, "body": body},
        )


def _drop_message_fts_row(engine: Engine, message_id: int, body: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                f"INSERT INTO {MESSAGE_FTS_TABLE}({MESSAGE_FTS_TABLE}, rowid, text) "
                "VALUES('delete', :id, :body)"
            ),
            {"id": message_id, "body": body},
        )


def _plant_message_fts_row(engine: Engine, message_id: int, body: str) -> None:
    """A stale index row for a message that must not be indexed (zone / buried)."""
    with engine.begin() as connection:
        connection.execute(
            text(f"INSERT INTO {MESSAGE_FTS_TABLE}(rowid, text) VALUES(:id, :body)"),
            {"id": message_id, "body": body},
        )


# --- observation ---------------------------------------------------------------------


def _key_column(table_name: str) -> str:
    return "memo_id" if table_name == MEMO_VEC_TABLE else "session_id"


def _vector_ids(engine: Engine, table_name: str) -> set[int]:
    with engine.connect() as connection:
        if vector_table_dimension(connection, table_name) is None:
            return set()
        rows = connection.execute(text(f"SELECT {_key_column(table_name)} FROM {table_name}")).all()
    return {int(row[0]) for row in rows}


def _stored_vector(engine: Engine, table_name: str, row_id: int, *, dim: int = DIMENSION) -> list[float] | None:
    with engine.connect() as connection:
        if vector_table_dimension(connection, table_name) is None:
            return None
        query = text(f"SELECT embedding FROM {table_name} WHERE {_key_column(table_name)} = :row_id")
        blob = connection.execute(query, {"row_id": row_id}).scalar_one_or_none()
    return None if blob is None else list(struct.unpack(f"<{dim}f", bytes(blob)))


def _vector_rows(engine: Engine, table_name: str) -> dict[int, bytes]:
    """Every row of a vector table as id -> raw blob; empty when the table is absent."""
    with engine.connect() as connection:
        if vector_table_dimension(connection, table_name) is None:
            return {}
        rows = connection.execute(
            text(f"SELECT {_key_column(table_name)}, embedding FROM {table_name}")
        ).all()
    return {int(row[0]): bytes(row[1]) for row in rows}


def _dimensions(engine: Engine) -> tuple[int | None, int | None]:
    with engine.connect() as connection:
        return (
            vector_table_dimension(connection, MEMO_VEC_TABLE),
            vector_table_dimension(connection, SESSION_VEC_TABLE),
        )


def _match_ids(engine: Engine, table_name: str, token: str) -> list[int]:
    query = text(f"SELECT rowid FROM {table_name} WHERE {table_name} MATCH :token ORDER BY rowid")
    with engine.connect() as connection:
        return [int(row[0]) for row in connection.execute(query, {"token": token}).all()]


def _fts_snapshot(engine: Engine) -> dict[tuple[str, str], list[int]]:
    return {
        (table_name, token): _match_ids(engine, table_name, token)
        for table_name in (MEMO_FTS_TABLE, MESSAGE_FTS_TABLE)
        for token in ALL_TOKENS
    }


def _index_snapshot(engine: Engine) -> dict[str, Any]:
    """Everything all-or-nothing must preserve: vector rows, vector dimensions, FTS contents."""
    return {
        "dimensions": _dimensions(engine),
        MEMO_VEC_TABLE: _vector_rows(engine, MEMO_VEC_TABLE),
        SESSION_VEC_TABLE: _vector_rows(engine, SESSION_VEC_TABLE),
        "fts": _fts_snapshot(engine),
    }


def _composed(engine: Engine, user_id: int, session_id: int) -> str:
    with engine.connect() as connection:
        return compose_session_text(connection, user_id, session_id)


def _assert_every_eligible_vector(engine: Engine) -> None:
    """Each non-blank memo holds its body's vector; each session holds its composed text's."""
    assert _vector_ids(engine, MEMO_VEC_TABLE) == set(ELIGIBLE_MEMOS)
    for memo_id, body in ELIGIBLE_MEMOS.items():
        assert _stored_vector(engine, MEMO_VEC_TABLE, memo_id) == embedding_vector(body, DIMENSION), memo_id
    assert _vector_ids(engine, SESSION_VEC_TABLE) == set(SESSIONS)
    for session_id, user_id in SESSIONS.items():
        composed = _composed(engine, user_id, session_id)
        assert composed != ""
        assert _stored_vector(engine, SESSION_VEC_TABLE, session_id) == embedding_vector(composed, DIMENSION)


# =========================================================================== DoD-1


def test_an_admin_rebuild_answers_200_with_only_the_four_table_names__F002_DoD1(
    application: FastAPI, db_settings: Settings
) -> None:
    """DoD-1 — 200; the body's only key is `tables_rebuilt`, exactly the four names in order."""
    response = _rebuild(_admin(application, db_settings))

    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"tables_rebuilt"}
    assert body["tables_rebuilt"] == EXPECTED_TABLES


# =========================================================================== DoD-2


def test_every_non_blank_memo_of_every_user_gets_a_vector_and_the_blank_one_none__F002_DoD2(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-2 — memos of two owners (A and B) each hold their body's vector; the blank memo,
    which had a stale vector before, holds none."""
    _preexisting_vectors(engine)
    assert MEMO_BLANK in _vector_ids(engine, MEMO_VEC_TABLE)

    response = _rebuild(_admin(application, db_settings))

    assert response.status_code == 200, response.text
    ids = _vector_ids(engine, MEMO_VEC_TABLE)
    assert {MEMO_A, MEMO_A2, MEMO_B} <= ids
    assert MEMO_BLANK not in ids
    for memo_id, body in ELIGIBLE_MEMOS.items():
        assert _stored_vector(engine, MEMO_VEC_TABLE, memo_id) == embedding_vector(body, DIMENSION), memo_id


# =========================================================================== DoD-3


def test_every_session_with_text_of_every_user_gets_a_vector__F002_DoD3(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-3 — sessions owned by A and B each hold the vector of their composed text."""
    response = _rebuild(_admin(application, db_settings))

    assert response.status_code == 200, response.text
    assert set(SESSIONS) <= _vector_ids(engine, SESSION_VEC_TABLE)
    for session_id, user_id in SESSIONS.items():
        composed = _composed(engine, user_id, session_id)
        assert composed != ""
        assert _stored_vector(engine, SESSION_VEC_TABLE, session_id) == embedding_vector(composed, DIMENSION)


# =========================================================================== DoD-4


def test_orphan_vectors_are_gone_after_a_rebuild__F002_DoD4(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-4 — a vector whose id matches no memo / session before the rebuild is absent after."""
    _preexisting_vectors(engine)
    assert ORPHAN_MEMO_ID in _vector_ids(engine, MEMO_VEC_TABLE)
    assert ORPHAN_SESSION_ID in _vector_ids(engine, SESSION_VEC_TABLE)

    response = _rebuild(_admin(application, db_settings))

    assert response.status_code == 200, response.text
    assert ORPHAN_MEMO_ID not in _vector_ids(engine, MEMO_VEC_TABLE)
    assert ORPHAN_SESSION_ID not in _vector_ids(engine, SESSION_VEC_TABLE)


# =========================================================================== DoD-5


def test_tables_at_another_dimension_are_redeclared_at_the_designated_one__F002_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-5 — both tables exist at 16 while the designation says 8; after the rebuild both are
    at 8 and populated."""
    _preexisting_vectors(engine, dim=OTHER_DIMENSION)
    assert _dimensions(engine) == (OTHER_DIMENSION, OTHER_DIMENSION)

    response = _rebuild(_admin(application, db_settings))

    assert response.status_code == 200, response.text
    assert _dimensions(engine) == (DIMENSION, DIMENSION)
    _assert_every_eligible_vector(engine)


# =========================================================================== DoD-6


def test_absent_vector_tables_are_created_and_populated__F002_DoD6(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-6 — neither vector table exists (as after a whole-database import); the rebuild
    creates both at the designated dimension and fills them."""
    assert _dimensions(engine) == (None, None)

    response = _rebuild(_admin(application, db_settings))

    assert response.status_code == 200, response.text
    assert _dimensions(engine) == (DIMENSION, DIMENSION)
    _assert_every_eligible_vector(engine)


# =========================================================================== DoD-7


@pytest.mark.parametrize("batch_size", [1, 2])
def test_chunk_boundaries_lose_no_memo_or_session__F002_DoD7(
    application: FastAPI,
    db_settings: Settings,
    engine: Engine,
    factory: FakeClientFactory,
    monkeypatch: pytest.MonkeyPatch,
    batch_size: int,
) -> None:
    """DoD-7 — with the batch size below the three eligible memos, every memo and session still
    gets its vector, and no single embed call carries more than the batch size."""
    monkeypatch.setattr("app.services.index_rebuild.REBUILD_EMBED_BATCH_SIZE", batch_size)
    assert batch_size < len(ELIGIBLE_MEMOS)

    response = _rebuild(_admin(application, db_settings))

    assert response.status_code == 200, response.text
    _assert_every_eligible_vector(engine)
    assert factory.embed_calls, "the rebuild made no embed call"
    assert max(len(texts) for _model, texts in factory.embed_calls) <= batch_size
    embedded = [text_ for _model, texts in factory.embed_calls for text_ in texts]
    for body in ELIGIBLE_MEMOS.values():
        assert body in embedded


# =========================================================================== DoD-8


def test_lost_memo_and_record_fts_rows_are_restored__F002_DoD8(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-8 — a memo's and a record message's FTS rows are deleted beforehand; after the
    rebuild a word from each matches again."""
    _drop_memo_fts_row(engine, MEMO_A, MEMO_A_BODY)
    _drop_message_fts_row(engine, MESSAGE_RECORD_A, RECORD_A_TEXT)
    assert _match_ids(engine, MEMO_FTS_TABLE, MEMO_A_TOKEN) == []
    assert _match_ids(engine, MESSAGE_FTS_TABLE, RECORD_A_TOKEN) == []

    response = _rebuild(_admin(application, db_settings))

    assert response.status_code == 200, response.text
    assert _match_ids(engine, MEMO_FTS_TABLE, MEMO_A_TOKEN) == [MEMO_A]
    assert _match_ids(engine, MESSAGE_FTS_TABLE, RECORD_A_TOKEN) == [MESSAGE_RECORD_A]
    # The other owner's rows are indexed too (all users).
    assert _match_ids(engine, MEMO_FTS_TABLE, MEMO_B_TOKEN) == [MEMO_B]
    assert _match_ids(engine, MESSAGE_FTS_TABLE, RECORD_B_TOKEN) == [MESSAGE_RECORD_B]


# =========================================================================== DoD-9


def test_the_message_index_holds_no_zone_and_no_buried_row__F002_DoD9(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-9 — stale index rows for a zone and a buried message are planted beforehand; after the
    rebuild neither is in `message_fts`, while the record rows are."""
    _plant_message_fts_row(engine, MESSAGE_ZONE, ZONE_TEXT)
    _plant_message_fts_row(engine, MESSAGE_BURIED, BURIED_TEXT)
    assert _match_ids(engine, MESSAGE_FTS_TABLE, ZONE_TOKEN) == [MESSAGE_ZONE]
    assert _match_ids(engine, MESSAGE_FTS_TABLE, BURIED_TOKEN) == [MESSAGE_BURIED]

    response = _rebuild(_admin(application, db_settings))

    assert response.status_code == 200, response.text
    assert _match_ids(engine, MESSAGE_FTS_TABLE, ZONE_TOKEN) == []
    assert _match_ids(engine, MESSAGE_FTS_TABLE, BURIED_TOKEN) == []
    assert _match_ids(engine, MESSAGE_FTS_TABLE, RECORD_A_TOKEN) == [MESSAGE_RECORD_A]


def test_a_clean_message_index_stays_free_of_zone_and_buried_rows__F002_DoD9(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-9 — without any planted row, the rebuild itself indexes neither the zone nor the
    buried message (an FTS5 `'rebuild'` over `messages` would)."""
    response = _rebuild(_admin(application, db_settings))

    assert response.status_code == 200, response.text
    assert _match_ids(engine, MESSAGE_FTS_TABLE, ZONE_TOKEN) == []
    assert _match_ids(engine, MESSAGE_FTS_TABLE, BURIED_TOKEN) == []


# =========================================================================== DoD-10


def _drop_triggers_on(engine: Engine, table_name: str) -> None:
    """Simulate a Sync that took the FTS triggers with it."""
    with engine.begin() as connection:
        names = [
            str(row[0])
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = ?", (table_name,)
            ).all()
        ]
        for name in names:
            connection.exec_driver_sql(f'DROP TRIGGER "{name}"')


def test_a_memo_created_after_a_rebuild_is_full_text_searchable__F002_DoD10(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-10 — after the rebuild (taken from a state whose memo triggers were lost), a memo
    created through `POST /api/memos` is found by `MATCH` in `memo_fts`."""
    _drop_triggers_on(engine, "memos")

    response = _rebuild(_admin(application, db_settings))
    assert response.status_code == 200, response.text

    created = _player_a(application, db_settings).post(
        MEMOS_PATH, json={"scope": "user", "body": f"A brand new note about the {NEW_MEMO_TOKEN}."}
    )
    assert created.status_code == 201, created.text
    new_id = int(created.json()["id"])

    assert _match_ids(engine, MEMO_FTS_TABLE, NEW_MEMO_TOKEN) == [new_id]


# =========================================================================== DoD-11


@pytest.fixture
def undesignated_application(
    db_settings: Settings, db_engine: Engine, factory: FakeClientFactory
) -> Iterator[FastAPI]:
    """The same content, but no embedding model designated."""
    _seed_accounts(db_engine)
    _seed_content(db_engine)
    app = _pinned_application(db_settings, factory)
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


def test_no_designation_answers_409_and_changes_nothing__F002_DoD11(
    undesignated_application: FastAPI, db_settings: Settings, db_engine: Engine
) -> None:
    """DoD-11 — 409 `no_embedding_model`; vector rows, dimensions and FTS contents (including a
    deliberately lost memo row and a planted zone row) are exactly as they were."""
    _preexisting_vectors(db_engine)
    _drop_memo_fts_row(db_engine, MEMO_A, MEMO_A_BODY)
    _plant_message_fts_row(db_engine, MESSAGE_ZONE, ZONE_TEXT)
    before = _index_snapshot(db_engine)
    assert before["dimensions"] == (DIMENSION, DIMENSION)
    assert before[MEMO_VEC_TABLE]

    response = _rebuild(_admin(undesignated_application, db_settings))

    _assert_error(response, 409, NO_EMBEDDING_MODEL)
    assert _index_snapshot(db_engine) == before


# =========================================================================== DoD-12


@pytest.fixture
def unreachable() -> FakeClientFactory:
    return unreachable_factory(DIMENSION)


@pytest.fixture
def unreachable_application(
    db_settings: Settings, engine: Engine, unreachable: FakeClientFactory
) -> Iterator[FastAPI]:
    app = _pinned_application(db_settings, unreachable)
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


def test_an_unreachable_server_answers_502_and_rolls_everything_back__F002_DoD12(
    unreachable_application: FastAPI, db_settings: Settings, engine: Engine, unreachable: FakeClientFactory
) -> None:
    """DoD-12 — the existing error model's 502 `llm_unreachable`; the vector tables keep their
    previous dimension (16, not the designated 8) and rows, and the FTS contents (a lost memo row,
    a planted zone row) are untouched — all-or-nothing."""
    _preexisting_vectors(engine, dim=OTHER_DIMENSION)
    _drop_memo_fts_row(engine, MEMO_A, MEMO_A_BODY)
    _plant_message_fts_row(engine, MESSAGE_ZONE, ZONE_TEXT)
    before = _index_snapshot(engine)
    assert before["dimensions"] == (OTHER_DIMENSION, OTHER_DIMENSION)

    response = _rebuild(_admin(unreachable_application, db_settings))

    _assert_error(response, 502, LLM_UNREACHABLE)
    # The failure really came from the provider.
    assert unreachable.embed_calls
    assert _index_snapshot(engine) == before


# =========================================================================== DoD-13


def test_a_roleplayer_is_refused_with_403_and_no_vector_changes__F002_DoD13(
    application: FastAPI, db_settings: Settings, engine: Engine, factory: FakeClientFactory
) -> None:
    """DoD-13 — a roleplayer gets 403 `insufficient_role`; no vector row changes."""
    _preexisting_vectors(engine)
    before = _index_snapshot(engine)

    _assert_error(_rebuild(_player_a(application, db_settings)), 403, INSUFFICIENT_ROLE)

    assert _index_snapshot(engine) == before
    assert factory.embed_calls == []


def test_an_anonymous_caller_is_refused_with_401_and_no_vector_changes__F002_DoD13(
    application: FastAPI, engine: Engine, factory: FakeClientFactory
) -> None:
    """DoD-13 — without a session cookie, 401 `not_authenticated`; no vector row changes."""
    _preexisting_vectors(engine)
    before = _index_snapshot(engine)

    _assert_error(_rebuild(_anonymous(application)), 401, NOT_AUTHENTICATED)

    assert _index_snapshot(engine) == before
    assert factory.embed_calls == []


# =========================================================================== DoD-14


def test_the_response_is_identical_for_an_empty_and_a_populated_instance__F002_DoD14(
    db_settings: Settings, db_engine: Engine, factory: FakeClientFactory
) -> None:
    """DoD-14 — the body on an instance with no memos / sessions equals the body after content
    for two users is added; no user text appears in either."""
    _seed_accounts(db_engine)
    _seed_designation(db_engine)
    app = _pinned_application(db_settings, factory)
    try:
        empty = _rebuild(_admin(app, db_settings))
        assert empty.status_code == 200, empty.text

        _seed_content(db_engine)
        populated = _rebuild(_admin(app, db_settings))
        assert populated.status_code == 200, populated.text
    finally:
        app.dependency_overrides.clear()

    # The populated run really did embed content, so the equality below is not vacuous.
    assert _vector_ids(db_engine, MEMO_VEC_TABLE) == set(ELIGIBLE_MEMOS)
    assert populated.json() == empty.json()
    assert populated.content == empty.content
    for user_text in USER_TEXTS:
        assert user_text not in populated.text
    for token in ALL_TOKENS:
        assert token not in populated.text
