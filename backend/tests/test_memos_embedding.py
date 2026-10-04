"""Tests for the memo write paths' embedding lifecycle — feature 024, step 004 (DoD-1..9).

Every expected value comes from `docs/plans/024.embedding-lifecycle/004.memo-write-paths.md`
(its Interface intent and Definition of done — **DoD-1 pins the body verbatim**), from
`004.context.md` (the test shape, the transaction ordering, "body changed" compared against
the row as stored) and from the feature `context.md`: **D5** (the trigger table — flag-only
updates, an unchanged body and reorder do no vector work at all), **D7** (a memo embeds its
`body` alone, and a whitespace-only body has no vector and resolves no model), **D8** (the two
failure codes and the strict rollback), **D9** (the keyword-only factory / timeout pair) and
the **Wire contract** (`no_embedding_model` → 409, `llm_unreachable` → 502).

Bindings come from `## Skeleton` → "Step 004 — frozen interface" in `status.md` (the two
changed service signatures and the two router override keys), plus steps 001 and 002 for
`MEMO_FTS_TABLE` / `MEMO_VEC_TABLE`. The fake's contract comes from `## Tests` → "Step 002 —
tests". Nothing here was derived from the implementation.

Each test name ends `__S024_004_DoD<n>` with the DoD item it covers.

Mechanics (`context.md` "Test conventions", `004.context.md` "Test shape"):
- a real SQLite file per test (`db_engine`) with `schema.metadata.create_all`; `conftest.py`
  is untouched and every fixture below is file-local;
- users and memos needing a precise state are **raw inserts**, every id above 2^60;
- a designated model is raw `llm_servers` + `models` rows at dimension 8 with a null
  `api_key_ref`, so no secret has to resolve;
- the outbound client arrives through the frozen `client_factory=` keyword seam (service) or
  through `dependency_overrides` of the shared `get_llm_client_factory` (router), using the
  shared fake in `tests/llm_fakes.py`. No network, and no module attribute is patched beyond
  the routers' established `configure_logging` neutralisation;
- the virtual tables are observed only from the test side — `pragma_table_info`, point
  lookups and `MATCH`. 024 issues no query of its own.
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
from app.db.search_tables import MEMO_FTS_TABLE, MEMO_VEC_TABLE
from app.dependencies import get_llm_client_factory
from app.errors import LlmUnreachableError, NoEmbeddingModelError
from app.ids import SnowflakeGenerator
from app.main import create_app
from app.roles import Role
from app.services.memos import Memo, create_memo, delete_memo, reorder_memos, update_memo
from app.services.passwords import hash_password
from tests.llm_fakes import (
    FAKE_EMBEDDING_DIM,
    FakeClientFactory,
    embedding_vector,
    fake_factory,
    unreachable_factory,
)

#: The seeded instant, in the project's fixed-width form.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

#: Every id is above 2^60 = 1152921504606846976 (D3 / U6: snowflake ids stay the keys).
USER_A = 1_400_000_000_000_000_001
USER_B = 1_400_000_000_000_000_002

MEMO_SEEDED = 1_400_000_000_000_000_101
MEMO_SEEDED_2 = 1_400_000_000_000_000_102

SERVER_ID = 1_400_000_000_000_000_201
MODEL_ID = 1_400_000_000_000_000_202

PLAYER_A_NAME = "aster"
PLAYER_A_PASSWORD = "a quiet river at dusk"
PLAYER_B_NAME = "briar"
PLAYER_B_PASSWORD = "salt and lantern light"

BASE_URL = "http://embedding.test:8080/v1"
MODEL_NAME = "the-designated-embedding-model"

#: The designated dimension in these tests; 8 keeps them fast (`context.md`).
DIMENSION = FAKE_EMBEDDING_DIM

#: A timeout deliberately unequal to `Settings`' declared default, so it is distinguishable.
PASSED_TIMEOUT = 12.5

#: DoD-1's body, verbatim from the step file, and the token a `MATCH` looks for.
DOD1_BODY = "The innkeeper is Kaelith."
DOD1_TOKEN = "Kaelith"

#: A whitespace-only body (D7: blank, so no vector and no model resolved).
BLANK_BODY = "   \n\t  "

#: Wire codes (`context.md` Wire contract).
NO_EMBEDDING_MODEL = "no_embedding_model"
LLM_UNREACHABLE = "llm_unreachable"

#: The nine-key `Memo` wire object (015's Wire contract — unchanged by 024).
MEMO_KEYS = {
    "id",
    "scope",
    "scope_id",
    "body",
    "is_enabled",
    "is_forced",
    "sort_key",
    "created_at",
    "updated_at",
}

MEMOS_PATH = "/api/memos"
LOGIN_PATH = "/api/auth/login"


# --- seeding ------------------------------------------------------------------------------


def _servers() -> Table:
    return schema.metadata.tables["llm_servers"]


def _models() -> Table:
    return schema.metadata.tables["models"]


def _insert_user(engine: Engine, *, user_id: int, username: str, password: str) -> None:
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


def _insert_memo(
    engine: Engine,
    *,
    memo_id: int,
    user_id: int,
    body: str,
    sort_key: int = 0,
    is_enabled: bool = True,
    is_forced: bool = False,
) -> None:
    """Raw-insert one user-level `memos` row, bypassing the service entirely.

    A user-level row stores the owner's id as `scope_id` (harvest D13), so this is the shape
    `list_memos(..., "user", None)` and `PATCH /api/memos/{id}` both address.
    """
    with engine.begin() as connection:
        connection.execute(
            schema.memos.insert().values(
                id=memo_id,
                user_id=user_id,
                scope="user",
                scope_id=user_id,
                body=body,
                is_enabled=is_enabled,
                is_forced=is_forced,
                sort_key=sort_key,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _seed_designation(engine: Engine, *, dim: int | None = DIMENSION) -> None:
    """Raw-insert one server and one enabled, designated embedding model — no service used."""
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


def _withdraw_designation(engine: Engine) -> None:
    """Clear the designation, leaving the registry row in place (R4: no substitution)."""
    with engine.begin() as connection:
        connection.execute(
            _models().update().where(_models().c.id == MODEL_ID).values(is_embedding_designated=False)
        )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """Two owners and nothing else — `create_all` only, so no virtual table pre-exists.

    No model is designated here: the tests that need one call `_seed_designation` themselves,
    because "no designated model" is half of this step's contract.
    """
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username=PLAYER_A_NAME, password=PLAYER_A_PASSWORD)
    _insert_user(db_engine, user_id=USER_B, username=PLAYER_B_NAME, password=PLAYER_B_PASSWORD)
    return db_engine


@pytest.fixture
def generator() -> SnowflakeGenerator:
    return SnowflakeGenerator(node_id=1)


@pytest.fixture(autouse=True)
def _quiet_factory_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the factory's logging call — the routers' established idiom."""
    monkeypatch.setattr("app.main.configure_logging", lambda settings: None)


# --- calling the frozen interface ---------------------------------------------------------


def _create(
    engine: Engine,
    generator: SnowflakeGenerator,
    user_id: int,
    body: str,
    factory: FakeClientFactory,
) -> Memo:
    """A user-level create through the frozen keyword seam (D9)."""
    with engine.connect() as connection:
        return create_memo(
            connection,
            generator,
            user_id,
            "user",  # type: ignore[arg-type]
            None,
            body,
            client_factory=factory,
            timeout_seconds=PASSED_TIMEOUT,
        )


def _update(
    engine: Engine,
    user_id: int,
    memo_id: int,
    factory: FakeClientFactory,
    **changes: Any,
) -> Memo:
    with engine.connect() as connection:
        return update_memo(
            connection,
            user_id,
            memo_id,
            client_factory=factory,
            timeout_seconds=PASSED_TIMEOUT,
            **changes,
        )


def _delete(engine: Engine, user_id: int, memo_id: int) -> None:
    """`delete_memo` is unchanged: dropping a vector row needs no model and no factory."""
    with engine.connect() as connection:
        delete_memo(connection, user_id, memo_id)


def _reorder(engine: Engine, user_id: int, memo_ids: list[int]) -> list[Memo]:
    with engine.connect() as connection:
        return reorder_memos(connection, user_id, "user", None, memo_ids)  # type: ignore[arg-type]


# --- observation (tests may query the tables; application code never does) ----------------


def _table_exists(connection: Connection, table_name: str) -> bool:
    row = connection.execute(
        text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name"),
        {"name": table_name},
    ).first()
    return row is not None


def _key_column(connection: Connection, table_name: str) -> str | None:
    """The vec0 table's key column, or `None` when the table does not exist."""
    rows = connection.execute(
        text("SELECT name FROM pragma_table_info(:table_name) WHERE pk = 1"),
        {"table_name": table_name},
    ).all()
    return None if not rows else str(rows[0][0])


def _vector_blob(engine: Engine, memo_id: int) -> bytes | None:
    """The stored blob for one memo id, or `None` when there is no row (or no table)."""
    with engine.connect() as connection:
        key = _key_column(connection, MEMO_VEC_TABLE)
        if key is None:
            return None
        query = text(f"SELECT embedding FROM {MEMO_VEC_TABLE} WHERE {key} = :row_id")
        blob = connection.execute(query, {"row_id": memo_id}).scalar_one_or_none()
        return None if blob is None else bytes(blob)


def _stored_vector(engine: Engine, memo_id: int, *, dim: int = DIMENSION) -> list[float] | None:
    blob = _vector_blob(engine, memo_id)
    return None if blob is None else list(struct.unpack(f"<{dim}f", blob))


def _all_vector_blobs(engine: Engine) -> dict[int, bytes]:
    """Every `memo_vec` row, by id — the whole table, so "every row" can be compared."""
    with engine.connect() as connection:
        key = _key_column(connection, MEMO_VEC_TABLE)
        if key is None:
            return {}
        rows = connection.execute(text(f"SELECT {key}, embedding FROM {MEMO_VEC_TABLE}")).all()
    return {int(row[0]): bytes(row[1]) for row in rows}


def _vector_row_count(engine: Engine) -> int:
    return len(_all_vector_blobs(engine))


def _fts_match_ids(engine: Engine, token: str) -> list[int]:
    """The rowids a `memo_fts` `MATCH` returns, ascending; `[]` when the table does not exist."""
    with engine.connect() as connection:
        if not _table_exists(connection, MEMO_FTS_TABLE):
            return []
        query = text(f"SELECT rowid FROM {MEMO_FTS_TABLE} WHERE {MEMO_FTS_TABLE} MATCH :token ORDER BY rowid")
        return [int(row[0]) for row in connection.execute(query, {"token": token}).all()]


def _ids_with_body(engine: Engine, body: str) -> list[int]:
    with engine.connect() as connection:
        rows = connection.execute(select(schema.memos.c.id).where(schema.memos.c.body == body)).all()
    return [int(row[0]) for row in rows]


def _stored_body(engine: Engine, memo_id: int) -> str | None:
    with engine.connect() as connection:
        value = connection.execute(
            select(schema.memos.c.body).where(schema.memos.c.id == memo_id)
        ).scalar_one_or_none()
    return None if value is None else str(value)


def _flags(engine: Engine, memo_id: int) -> tuple[bool, bool]:
    with engine.connect() as connection:
        row = connection.execute(
            select(schema.memos.c.is_enabled, schema.memos.c.is_forced).where(schema.memos.c.id == memo_id)
        ).one()
    return bool(row[0]), bool(row[1])


# =========================================================================== DoD-1


def test_a_create_embeds_the_body_alone_and_indexes_it__S024_004_DoD1(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-1 — with a designated model at dimension 8 the create embeds **the body alone**
    (UC-042, US-119, D5, D7): the stored vector is the fake's vector for exactly that body,
    there is exactly one `embed` call carrying `[body]`, and the full-text index finds it.
    """
    _seed_designation(engine)
    factory = fake_factory(DIMENSION)

    memo = _create(engine, generator, USER_A, DOD1_BODY, factory)

    assert memo.body == DOD1_BODY
    assert _stored_vector(engine, memo.id) == embedding_vector(DOD1_BODY, DIMENSION)
    assert _vector_row_count(engine) == 1
    # Exactly one embed call, the designated name, and the body as the whole batch (D1, D7).
    assert factory.embed_calls == [(MODEL_NAME, (DOD1_BODY,))]
    assert factory.call_count == 1
    assert _fts_match_ids(engine, DOD1_TOKEN) == [memo.id]


# =========================================================================== DoD-2


def test_a_create_with_no_designated_model_stores_nothing__S024_004_DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-2 — strict (D8): `NoEmbeddingModelError`, and the whole transaction rolled back,
    DDL included, so there is no `memos` row, no `memo_vec` row and no `memo_fts` hit."""
    factory = fake_factory(DIMENSION)

    with pytest.raises(NoEmbeddingModelError) as raised:
        _create(engine, generator, USER_A, DOD1_BODY, factory)

    assert raised.value.code == NO_EMBEDDING_MODEL
    assert _ids_with_body(engine, DOD1_BODY) == []
    assert _vector_row_count(engine) == 0
    assert _fts_match_ids(engine, DOD1_TOKEN) == []


def test_a_create_with_an_unreachable_provider_stores_nothing__S024_004_DoD2(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-2 — the second condition: the embed call fails, `LlmUnreachableError` propagates and
    nothing at all is stored (D8, `backend-structure.md`'s transaction rule)."""
    _seed_designation(engine)
    factory = unreachable_factory(DIMENSION)

    with pytest.raises(LlmUnreachableError) as raised:
        _create(engine, generator, USER_A, DOD1_BODY, factory)

    assert raised.value.code == LLM_UNREACHABLE
    assert _ids_with_body(engine, DOD1_BODY) == []
    assert _vector_row_count(engine) == 0
    assert _fts_match_ids(engine, DOD1_TOKEN) == []


# =========================================================================== DoD-3


def test_a_changed_body_replaces_the_vector__S024_004_DoD3(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-3 — UC-043 / US-104: a body edit re-embeds strictly and rewrites the row."""
    _seed_designation(engine)
    memo = _create(engine, generator, USER_A, "The old body.", fake_factory(DIMENSION))
    assert _stored_vector(engine, memo.id) == embedding_vector("The old body.", DIMENSION)

    edit_factory = fake_factory(DIMENSION)
    updated = _update(engine, USER_A, memo.id, edit_factory, body="The innkeeper moved away.")

    assert updated.body == "The innkeeper moved away."
    assert _stored_vector(engine, memo.id) == embedding_vector("The innkeeper moved away.", DIMENSION)
    assert _vector_row_count(engine) == 1
    assert edit_factory.embed_calls == [(MODEL_NAME, ("The innkeeper moved away.",))]


def test_a_changed_body_without_a_model_changes_nothing__S024_004_DoD3(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-3's second half — strict (D8): the same call raises `NoEmbeddingModelError`, and both
    the stored body and the `memo_vec` row are left as they were."""
    _seed_designation(engine)
    memo = _create(engine, generator, USER_A, "The old body.", fake_factory(DIMENSION))
    blob_before = _vector_blob(engine, memo.id)
    assert blob_before is not None
    _withdraw_designation(engine)

    factory = fake_factory(DIMENSION)
    with pytest.raises(NoEmbeddingModelError) as raised:
        _update(engine, USER_A, memo.id, factory, body="The innkeeper moved away.")

    assert raised.value.code == NO_EMBEDDING_MODEL
    assert _stored_body(engine, memo.id) == "The old body."
    assert _vector_blob(engine, memo.id) == blob_before


# =========================================================================== DoD-4


FLAG_ONLY_CHANGES: list[tuple[str, dict[str, Any]]] = [
    ("is_enabled", {"is_enabled": False}),
    ("is_forced", {"is_forced": True}),
    ("both", {"is_enabled": False, "is_forced": True}),
]


@pytest.mark.parametrize(("label", "changes"), FLAG_ONLY_CHANGES, ids=[c[0] for c in FLAG_ONLY_CHANGES])
def test_a_flag_only_update_needs_no_model_at_all__S024_004_DoD4(
    engine: Engine, label: str, changes: dict[str, Any]
) -> None:
    """DoD-4 — UC-044 / UC-075 / D5: with **no** designated model a flag-only update succeeds
    and persists the flags. No registry state can make a toggle fail."""
    _insert_memo(engine, memo_id=MEMO_SEEDED, user_id=USER_A, body="unchanged body")
    factory = fake_factory(DIMENSION)

    updated = _update(engine, USER_A, MEMO_SEEDED, factory, **changes)

    expected_enabled = bool(changes.get("is_enabled", True))
    expected_forced = bool(changes.get("is_forced", False))
    assert (updated.is_enabled, updated.is_forced) == (expected_enabled, expected_forced)
    assert _flags(engine, MEMO_SEEDED) == (expected_enabled, expected_forced)
    assert updated.body == "unchanged body"
    assert factory.call_count == 0


def test_a_flag_only_update_does_no_vector_work__S024_004_DoD4(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-4 — the clause D5 exists for: with a designated model **and** a recording factory, the
    three flag-only updates make **zero** factory calls and leave the `memo_vec` row
    byte-identical before and after."""
    _seed_designation(engine)
    memo = _create(engine, generator, USER_A, DOD1_BODY, fake_factory(DIMENSION))
    blob_before = _vector_blob(engine, memo.id)
    assert blob_before is not None

    toggle_factory = fake_factory(DIMENSION)
    _update(engine, USER_A, memo.id, toggle_factory, is_enabled=False)
    _update(engine, USER_A, memo.id, toggle_factory, is_forced=True)
    _update(engine, USER_A, memo.id, toggle_factory, is_enabled=True, is_forced=False)

    assert toggle_factory.call_count == 0
    assert toggle_factory.embed_calls == []
    assert _vector_blob(engine, memo.id) == blob_before
    assert _vector_row_count(engine) == 1


# =========================================================================== DoD-5


def test_a_body_equal_to_the_stored_one_does_no_vector_work__S024_004_DoD5(engine: Engine) -> None:
    """DoD-5 — D5: a `body` sent but equal to the stored body (here alongside a flag change) is
    not a change, so it succeeds with **no** model designated and makes zero factory calls."""
    _insert_memo(engine, memo_id=MEMO_SEEDED, user_id=USER_A, body="The innkeeper is Kaelith.")
    factory = fake_factory(DIMENSION)

    updated = _update(
        engine, USER_A, MEMO_SEEDED, factory, body="The innkeeper is Kaelith.", is_forced=True
    )

    assert updated.body == "The innkeeper is Kaelith."
    assert updated.is_forced is True
    assert _flags(engine, MEMO_SEEDED) == (True, True)
    assert factory.call_count == 0
    assert factory.embed_calls == []


# =========================================================================== DoD-6


def test_a_delete_drops_the_row_its_vector_and_its_index_entry__S024_004_DoD6(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-6 — D5: a delete needs no model. The `memos` row, the `memo_vec` row and the
    `memo_fts` hit are all gone afterwards."""
    _seed_designation(engine)
    memo = _create(engine, generator, USER_A, DOD1_BODY, fake_factory(DIMENSION))
    assert _vector_blob(engine, memo.id) is not None
    assert _fts_match_ids(engine, DOD1_TOKEN) == [memo.id]
    _withdraw_designation(engine)

    _delete(engine, USER_A, memo.id)

    assert _stored_body(engine, memo.id) is None
    assert _vector_blob(engine, memo.id) is None
    assert _vector_row_count(engine) == 0
    assert _fts_match_ids(engine, DOD1_TOKEN) == []


# =========================================================================== DoD-7


def test_a_whitespace_only_create_has_no_vector__S024_004_DoD7(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-7 — a blank body has nothing to retrieve: the create succeeds with **no** model
    designated, resolves no model (zero factory calls) and leaves no `memo_vec` row."""
    factory = fake_factory(DIMENSION)

    memo = _create(engine, generator, USER_A, BLANK_BODY, factory)

    assert memo.body == BLANK_BODY
    assert _stored_body(engine, memo.id) == BLANK_BODY
    assert factory.call_count == 0
    assert factory.embed_calls == []
    assert _vector_blob(engine, memo.id) is None
    assert _vector_row_count(engine) == 0


def test_an_update_to_a_blank_body_removes_the_vector__S024_004_DoD7(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-7's second half — a memo that had a vector loses it when the body becomes blank, and
    that removal resolves no model and makes no embed call."""
    _seed_designation(engine)
    memo = _create(engine, generator, USER_A, DOD1_BODY, fake_factory(DIMENSION))
    assert _vector_blob(engine, memo.id) is not None
    _withdraw_designation(engine)

    blank_factory = fake_factory(DIMENSION)
    updated = _update(engine, USER_A, memo.id, blank_factory, body=BLANK_BODY)

    assert updated.body == BLANK_BODY
    assert blank_factory.call_count == 0
    assert blank_factory.embed_calls == []
    assert _vector_blob(engine, memo.id) is None
    assert _vector_row_count(engine) == 0


# =========================================================================== DoD-8


def test_a_reorder_does_no_vector_work__S024_004_DoD8(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-8 — UC-076 / D5: `reorder_memos` (016) is untouched by this step. With a designated
    model and the recording factory that built the three memos' vectors, the reorder adds **no**
    factory call and leaves **every** `memo_vec` row byte-identical.

    `reorder_memos` takes no factory (it is not modified), so "zero factory calls" is measured
    on the one recording factory in play: it must record nothing further across the reorder.
    """
    _seed_designation(engine)
    factory = fake_factory(DIMENSION)
    first = _create(engine, generator, USER_A, "First note.", factory)
    second = _create(engine, generator, USER_A, "Second note.", factory)
    third = _create(engine, generator, USER_A, "Third note.", factory)
    blobs_before = _all_vector_blobs(engine)
    assert set(blobs_before) == {first.id, second.id, third.id}
    calls_before = list(factory.calls)
    embeds_before = list(factory.embed_calls)

    reordered = _reorder(engine, USER_A, [first.id, third.id, second.id])

    assert [memo.id for memo in reordered] == [first.id, third.id, second.id]
    assert factory.calls == calls_before
    assert factory.embed_calls == embeds_before
    assert _all_vector_blobs(engine) == blobs_before


# =========================================================================== DoD-9
# The router, through `dependency_overrides` for the two keys the skeleton recorded:
# `app.dependencies.get_llm_client_factory` and `app.config.get_settings`.


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
    """A fresh client carrying player A's session cookie — the memos-router login pattern."""
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


def _error(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error, dict)
    assert error["code"] == code
    return error


def test_a_create_without_a_model_answers_409_and_lists_nothing__S024_004_DoD9(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-9 — Wire contract: `no_embedding_model` is 409, and the refused note is not stored,
    so the level's list does not contain it."""
    factory = fake_factory(DIMENSION)
    with _application(db_settings, factory) as application:
        client = _player_a(application, db_settings)

        response = client.post(MEMOS_PATH, json={"scope": "user", "body": DOD1_BODY})

        _error(response, 409, NO_EMBEDDING_MODEL)
        listed = client.get(MEMOS_PATH, params={"scope": "user"})
        assert listed.status_code == 200, listed.text
        assert [memo["body"] for memo in listed.json()["memos"]] == []
    assert _ids_with_body(engine, DOD1_BODY) == []


def test_a_create_with_a_designated_model_answers_201__S024_004_DoD9(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-9 — with a designated model and the fake, the route answers 201 with the usual
    `MemoResponse`: the nine wire keys, unchanged by 024."""
    _seed_designation(engine)
    factory = fake_factory(DIMENSION)
    with _application(db_settings, factory) as application:
        client = _player_a(application, db_settings)

        response = client.post(MEMOS_PATH, json={"scope": "user", "body": DOD1_BODY})

        assert response.status_code == 201, response.text
        created = response.json()
        assert set(created) == MEMO_KEYS
        assert created["body"] == DOD1_BODY
        assert created["scope"] == "user"
        assert created["scope_id"] is None

    assert _stored_vector(engine, int(created["id"])) == embedding_vector(DOD1_BODY, DIMENSION)
    # The route really resolved the overridden factory and passed the settings timeout (D9).
    assert factory.call_count == 1
    assert factory.calls[0][2] == db_settings.llm_request_timeout_seconds


def test_a_body_patch_with_an_unreachable_provider_answers_502__S024_004_DoD9(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-9 — Wire contract: `llm_unreachable` is 502, and nothing is stored, so the body is
    still the stored one."""
    _insert_memo(engine, memo_id=MEMO_SEEDED, user_id=USER_A, body="The old body.")
    _seed_designation(engine)
    factory = unreachable_factory(DIMENSION)
    with _application(db_settings, factory) as application:
        client = _player_a(application, db_settings)

        response = client.patch(f"{MEMOS_PATH}/{MEMO_SEEDED}", json={"body": "The innkeeper moved away."})

        _error(response, 502, LLM_UNREACHABLE)
    assert _stored_body(engine, MEMO_SEEDED) == "The old body."
    assert _ids_with_body(engine, "The innkeeper moved away.") == []


def test_a_flag_only_patch_answers_200_without_a_model__S024_004_DoD9(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-9 — a `PATCH` carrying only `is_enabled` reaches no embed path (D5), so it answers 200
    with no model designated at all."""
    _insert_memo(engine, memo_id=MEMO_SEEDED_2, user_id=USER_A, body="The innkeeper is Kaelith.")
    factory = fake_factory(DIMENSION)
    with _application(db_settings, factory) as application:
        client = _player_a(application, db_settings)

        response = client.patch(f"{MEMOS_PATH}/{MEMO_SEEDED_2}", json={"is_enabled": False})

        assert response.status_code == 200, response.text
        patched = response.json()
        assert set(patched) == MEMO_KEYS
        assert patched["is_enabled"] is False
        assert patched["body"] == "The innkeeper is Kaelith."

    assert _flags(engine, MEMO_SEEDED_2) == (False, False)
    assert factory.call_count == 0
