"""Tests for `app/services/embedding.py` — feature 024, step 002 (DoD-1..8 and DoD-10).

Every expected value comes from `docs/plans/024.embedding-lifecycle/002.embedding-service.md`
(its Interface intent and Definition of done), from `002.context.md` (the fake's contract,
the api_key_ref re-select, the sync-bridge notes) and from the feature `context.md`
(**D1** the sync bridge and one embed call per write, **D4** the vector-row forms, **D8** the
two failure codes and the `{"reason": "dimension_mismatch"}` detail, **D9** the shared
dependency and the field-derived timeout default, **R4** no substitution). Bindings come from
`## Skeleton` -> "Step 002 — frozen interface" (and "Step 001" for `ensure_vector_tables` and
the table-name constants) in `status.md`. Nothing here was derived from the implementation.

Each test name ends `__S024_002_DoD<n>`. DoD-9 lives in `test_dependencies.py`; DoD-11 is
regression fallout carried by the existing `test_admin_llm_router.py` / `test_dependencies.py`
suites.

Mechanics (`context.md` "Test conventions", `002.context.md` "Test shape"):
- a real SQLite file per test (`db_engine`) with `schema.metadata.create_all`;
- the `llm_servers` / `models` registry rows are **raw inserts**, so the designation is set up
  without calling any registry write path;
- the environment variable behind `api_key_ref` is set with `monkeypatch.setenv`, the idiom
  `test_llm_registry_models.py` already uses. **No module attribute is patched anywhere**;
- the outbound client is injected through the frozen `client_factory=` keyword seam, using the
  shared fake in `tests/llm_fakes.py`. No network;
- every row id is above 2^60 (D3 / U6: snowflake ids stay the vec0 keys).
"""

import ast
import inspect
import struct
import threading
from typing import Any

import pytest
import sqlite_vec
from sqlalchemy import Connection, Engine, Table, text

import app.services.embedding as embedding_module
from app.config import Settings
from app.db import schema
from app.db.search_tables import MEMO_VEC_TABLE, SESSION_VEC_TABLE, ensure_vector_tables
from app.errors import LlmUnreachableError, NoEmbeddingModelError, SecretRefError
from app.services.embedding import (
    DEFAULT_EMBED_TIMEOUT_SECONDS,
    EmbeddingModelHandle,
    delete_vector,
    embed_texts,
    open_embedding_model,
    write_vector,
)
from tests.llm_fakes import (
    FakeClientFactory,
    embedding_vector,
    fake_factory,
    unreachable_factory,
    vectors_for,
    wrong_length_factory,
)

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

#: Ids above 2^60 = 1152921504606846976.
SERVER_ID = 1_300_000_000_000_000_301
MODEL_ID = 1_300_000_000_000_000_302
ROW_ID = 1_300_000_000_000_000_401
OTHER_ROW_ID = 1_300_000_000_000_000_402

BASE_URL = "http://embedding.test:8080/v1"
MODEL_NAME = "the-designated-embedding-model"

#: Non-`RPHELPER_` names, so the conftest's autouse clearing never touches them (harvest F7).
KEY_VARIABLE = "S024_002_API_KEY"
POINTER = "$" + KEY_VARIABLE
RESOLVED_KEY = "sk-S024-002-RESOLVED-CREDENTIAL"
MISSING_VARIABLE = "S024_002_ABSENT_VARIABLE"
MISSING_POINTER = "$" + MISSING_VARIABLE

#: The designated dimension in these tests; 8 keeps them fast (``context.md``).
DIMENSION = 8

#: A timeout deliberately unequal to ``Settings``' declared default, so "the passed timeout"
#: is distinguishable from "the default" in DoD-1.
PASSED_TIMEOUT = 12.5

#: Three distinct texts; DoD-4 pins per-text vectors in input order.
TEXTS = ["the first text to embed", "a second, quite different text", "and a third"]

#: Exact float32 values (multiples of 2**-3), so a round-trip compares equal with no tolerance.
VECTOR_ONE = [0.5, -1.5, 2.25, 0.0, 1.0, -0.125, 3.5, -2.0]
VECTOR_TWO = [-0.25, 0.75, 1.5, -3.0, 0.125, 2.0, -1.0, 4.5]

VEC_TABLES = (MEMO_VEC_TABLE, SESSION_VEC_TABLE)


# --- seeding ---------------------------------------------------------------------------


def _servers() -> Table:
    return schema.metadata.tables["llm_servers"]


def _models() -> Table:
    return schema.metadata.tables["models"]


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database with the relational registry applied and nothing else."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    return db_engine


@pytest.fixture
def key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """`$S024_002_API_KEY` resolves; the absent-variable name is guaranteed unset (harvest F7)."""
    monkeypatch.setenv(KEY_VARIABLE, RESOLVED_KEY)
    monkeypatch.delenv(MISSING_VARIABLE, raising=False)


def _seed_designation(
    engine: Engine,
    *,
    dim: int | None = DIMENSION,
    is_enabled: bool = True,
    is_designated: bool = True,
    api_key_ref: str | None = POINTER,
) -> None:
    """Raw-insert one server and one model row — the designation, built without any service."""
    with engine.begin() as connection:
        connection.execute(
            _servers().insert().values(
                id=SERVER_ID,
                name="the embedding server",
                kind="llamaswap",
                base_url=BASE_URL,
                api_key_ref=api_key_ref,
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


def _open(engine: Engine, factory: FakeClientFactory, timeout: float = PASSED_TIMEOUT) -> EmbeddingModelHandle:
    with engine.connect() as connection:
        return open_embedding_model(connection, client_factory=factory, timeout_seconds=timeout)


def _opened(engine: Engine, factory: FakeClientFactory) -> EmbeddingModelHandle:
    """Seed the designation and open a handle through the fake factory."""
    _seed_designation(engine)
    return _open(engine, factory)


# --- reading the vector tables back ----------------------------------------------------


def _key_column(connection: Connection, table_name: str) -> str | None:
    """The vec0 table's key column, or `None` when the table does not exist.

    `rowid` is unusable on these tables (`status.md` step 002, probe finding 4), so the key
    column is discovered rather than re-typed here.
    """
    rows = connection.execute(
        text("SELECT name FROM pragma_table_info(:table_name) WHERE pk = 1"),
        {"table_name": table_name},
    ).all()
    return None if not rows else str(rows[0][0])


def _row_count(connection: Connection, table_name: str) -> int:
    return int(connection.execute(text(f"SELECT count(*) FROM {table_name}")).scalar_one())


def _read_blob(connection: Connection, table_name: str, row_id: int) -> bytes | None:
    key = _key_column(connection, table_name)
    assert key is not None
    query = text(f"SELECT embedding FROM {table_name} WHERE {key} = :row_id")
    blob = connection.execute(query, {"row_id": row_id}).scalar_one_or_none()
    return None if blob is None else bytes(blob)


def _read_vector(connection: Connection, table_name: str, row_id: int) -> list[float] | None:
    blob = _read_blob(connection, table_name, row_id)
    return None if blob is None else list(struct.unpack(f"<{DIMENSION}f", blob))


# =========================================================================== DoD-1


def test_open_returns_the_designated_name_and_dimension__S024_002_DoD1(
    engine: Engine, key_present: None
) -> None:
    """DoD-1 — the handle carries the designated model's name and its dimension (8)."""
    _seed_designation(engine)
    factory = fake_factory(dim=DIMENSION)

    handle = _open(engine, factory)

    assert handle.model_name == MODEL_NAME
    assert handle.embedding_dim == DIMENSION


def test_open_builds_exactly_one_client_with_url_resolved_key_and_timeout__S024_002_DoD1(
    engine: Engine, key_present: None
) -> None:
    """DoD-1 — one construction, with the server's base URL, the **variable's value** and the
    timeout that was passed (D1, R4). The resolved key is the environment value, not the
    `$NAME` pointer.
    """
    _seed_designation(engine)
    factory = fake_factory(dim=DIMENSION)

    handle = _open(engine, factory, timeout=PASSED_TIMEOUT)

    assert factory.call_count == 1
    assert factory.calls == [(BASE_URL, RESOLVED_KEY, PASSED_TIMEOUT)]
    assert handle.client is factory.clients[0]


def test_open_makes_no_outbound_call__S024_002_DoD1(engine: Engine, key_present: None) -> None:
    """DoD-1 / Interface intent — opening the model embeds and probes nothing."""
    _seed_designation(engine)
    factory = fake_factory(dim=DIMENSION)

    _open(engine, factory)

    assert factory.embed_calls == []
    assert factory.probe_calls == 0


def test_the_default_timeout_is_the_settings_field_default__S024_002_DoD1(
    engine: Engine, key_present: None
) -> None:
    """DoD-1 / D9 — omitting `timeout_seconds` passes `Settings`' declared default for
    `llm_request_timeout_seconds`. The expected value is read off that same field, never
    re-typed here.
    """
    expected = Settings.model_fields["llm_request_timeout_seconds"].default
    assert DEFAULT_EMBED_TIMEOUT_SECONDS == expected

    _seed_designation(engine)
    factory = fake_factory(dim=DIMENSION)
    with engine.connect() as connection:
        open_embedding_model(connection, client_factory=factory)

    assert factory.calls == [(BASE_URL, RESOLVED_KEY, expected)]


# =========================================================================== DoD-2


@pytest.mark.parametrize("case", ["no_designation", "designated_without_dimension"])
def test_an_unusable_designation_is_no_embedding_model_and_builds_nothing__S024_002_DoD2(
    engine: Engine, key_present: None, case: str
) -> None:
    """DoD-2 — no designated model, and a designation with no measured dimension, each raise
    `NoEmbeddingModelError` and construct **zero** clients: no substitution, and the refusal
    precedes any client (R4, the no-substitution rule).

    Revised 2026-10-08 (plan 006 step 004 DoD-18/19 spec revision): a designated-but-disabled
    model is no longer unusable — `is_enabled` is chat-set membership only — so that case moved
    to the success test below.
    """
    if case == "no_designation":
        _seed_designation(engine, is_designated=False)
    else:
        _seed_designation(engine, dim=None)
    factory = fake_factory(dim=DIMENSION)

    with engine.connect() as connection:
        with pytest.raises(NoEmbeddingModelError) as excinfo:
            open_embedding_model(connection, client_factory=factory, timeout_seconds=PASSED_TIMEOUT)

    assert excinfo.value.code == "no_embedding_model"
    assert factory.call_count == 0
    assert factory.embed_calls == []


def test_open_builds_a_handle_for_a_designated_but_disabled_model__S006_004_DoD18(
    engine: Engine, key_present: None
) -> None:
    """Bug fix 2026-10-08 repro — plan 006 step 004 DoD-18/DoD-19 as revised 2026-10-08
    (`is_enabled` is chat-set membership only; the embedding validator does not consult it).
    A designated, NOT enabled model with a measured dimension opens: one client is built and the
    handle carries the designated name and dimension (also S024_002 DoD-1).
    """
    _seed_designation(engine, is_enabled=False)
    factory = fake_factory(dim=DIMENSION)

    handle = _open(engine, factory, timeout=PASSED_TIMEOUT)

    assert handle.model_name == MODEL_NAME
    assert handle.embedding_dim == DIMENSION
    assert factory.call_count == 1
    assert factory.calls == [(BASE_URL, RESOLVED_KEY, PASSED_TIMEOUT)]
    assert handle.client is factory.clients[0]


def test_an_empty_registry_is_no_embedding_model_and_builds_nothing__S024_002_DoD2(
    engine: Engine, key_present: None
) -> None:
    """DoD-2 — with no registry row at all there is nothing to designate (R4)."""
    factory = fake_factory(dim=DIMENSION)

    with engine.connect() as connection:
        with pytest.raises(NoEmbeddingModelError) as excinfo:
            open_embedding_model(connection, client_factory=factory, timeout_seconds=PASSED_TIMEOUT)

    assert excinfo.value.code == "no_embedding_model"
    assert factory.call_count == 0


# =========================================================================== DoD-3


def test_an_unset_key_variable_raises_secret_ref_missing_and_builds_nothing__S024_002_DoD3(
    engine: Engine, key_present: None
) -> None:
    """DoD-3 — an `api_key_ref` naming an unset variable raises the `secret_ref_missing`
    error (`SecretRefError`, per the skeleton record) **before** any client exists.
    """
    _seed_designation(engine, api_key_ref=MISSING_POINTER)
    factory = fake_factory(dim=DIMENSION)

    with engine.connect() as connection:
        with pytest.raises(SecretRefError) as excinfo:
            open_embedding_model(connection, client_factory=factory, timeout_seconds=PASSED_TIMEOUT)

    assert excinfo.value.code == "secret_ref_missing"
    assert factory.call_count == 0
    assert factory.embed_calls == []


# =========================================================================== DoD-4


def test_embed_texts_answers_one_vector_per_text_in_input_order__S024_002_DoD4(
    engine: Engine, key_present: None
) -> None:
    """DoD-4 — three texts give three vectors, in input order, equal to the fake's
    deterministic vectors for exactly those texts.
    """
    handle = _opened(engine, factory := fake_factory(dim=DIMENSION))

    vectors = embed_texts(handle, TEXTS)

    assert vectors == vectors_for(TEXTS, DIMENSION)
    assert len(vectors) == len(TEXTS)
    assert [len(vector) for vector in vectors] == [DIMENSION] * len(TEXTS)
    # Each text got its own vector: a single vector broadcast three times would not pass.
    assert len({tuple(vector) for vector in vectors}) == len(TEXTS)
    assert factory.call_count == 1


def test_embed_texts_makes_exactly_one_call_carrying_the_batch_in_order__S024_002_DoD4(
    engine: Engine, key_present: None
) -> None:
    """DoD-4 / D1 — one `embed` call for the whole batch, with the designated model name and
    the three texts in input order; never one call per text.
    """
    handle = _opened(engine, factory := fake_factory(dim=DIMENSION))

    embed_texts(handle, TEXTS)

    assert factory.embed_calls == [(MODEL_NAME, tuple(TEXTS))]


def test_embed_texts_accepts_a_tuple_and_a_single_text__S024_002_DoD4(
    engine: Engine, key_present: None
) -> None:
    """DoD-4 / Interface intent — any non-empty sequence of texts binds, a one-element one
    included, and the answer is still one vector per text in order.
    """
    handle = _opened(engine, factory := fake_factory(dim=DIMENSION))

    vectors = embed_texts(handle, tuple(TEXTS[:1]))

    assert vectors == [embedding_vector(TEXTS[0], DIMENSION)]
    assert factory.embed_calls == [(MODEL_NAME, (TEXTS[0],))]


# =========================================================================== DoD-5


@pytest.mark.parametrize("returned_length", [7, 9])
def test_a_wrong_length_vector_is_a_dimension_mismatch__S024_002_DoD5(
    engine: Engine, key_present: None, returned_length: int
) -> None:
    """DoD-5 / D8 — a returned vector whose length is not `embedding_dim` raises
    `NoEmbeddingModelError` with `detail` exactly `{"reason": "dimension_mismatch"}`.
    """
    factory = wrong_length_factory(dim=DIMENSION, returned_length=returned_length)
    handle = _opened(engine, factory)

    with pytest.raises(NoEmbeddingModelError) as excinfo:
        embed_texts(handle, TEXTS)

    assert excinfo.value.code == "no_embedding_model"
    assert excinfo.value.detail == {"reason": "dimension_mismatch"}


def test_a_single_wrong_length_vector_in_the_batch_is_enough__S024_002_DoD5(
    engine: Engine, key_present: None
) -> None:
    """DoD-5 / Interface intent — "any returned vector": the whole batch is refused, so the
    one call's result is never partly used.
    """
    factory = wrong_length_factory(dim=DIMENSION, returned_length=DIMENSION + 4)
    handle = _opened(engine, factory)

    with pytest.raises(NoEmbeddingModelError) as excinfo:
        embed_texts(handle, TEXTS[:1])

    assert excinfo.value.detail == {"reason": "dimension_mismatch"}


# =========================================================================== DoD-6


def test_an_unreachable_provider_propagates_unchanged__S024_002_DoD6(
    engine: Engine, key_present: None
) -> None:
    """DoD-6 / D8 — the client's `LlmUnreachableError` propagates as that same error type,
    with code `llm_unreachable` and its detail unchanged. It is not converted into
    `no_embedding_model`.
    """
    factory = unreachable_factory(dim=DIMENSION, reason="unreachable")
    handle = _opened(engine, factory)

    with pytest.raises(LlmUnreachableError) as excinfo:
        embed_texts(handle, TEXTS)

    assert type(excinfo.value) is LlmUnreachableError
    assert excinfo.value.code == "llm_unreachable"
    assert excinfo.value.detail == {"reason": "unreachable"}
    assert not isinstance(excinfo.value, NoEmbeddingModelError)


def test_an_auth_failure_also_propagates_as_llm_unreachable__S024_002_DoD6(
    engine: Engine, key_present: None
) -> None:
    """DoD-6 — the reason the client chose survives; `embed` raises only this one class."""
    factory = unreachable_factory(dim=DIMENSION, reason="auth_failed")
    handle = _opened(engine, factory)

    with pytest.raises(LlmUnreachableError) as excinfo:
        embed_texts(handle, TEXTS)

    assert excinfo.value.code == "llm_unreachable"
    assert excinfo.value.detail == {"reason": "auth_failed"}


# =========================================================================== DoD-7


def test_embed_texts_runs_from_plain_synchronous_code__S024_002_DoD7(
    engine: Engine, key_present: None
) -> None:
    """DoD-7 / D1 — the sync bridge works from an ordinary sync caller with no event loop."""
    handle = _opened(engine, factory := fake_factory(dim=DIMENSION))

    vectors = embed_texts(handle, TEXTS)

    assert vectors == vectors_for(TEXTS, DIMENSION)
    assert factory.embed_calls == [(MODEL_NAME, tuple(TEXTS))]


def test_embed_texts_runs_on_a_worker_thread_with_no_event_loop__S024_002_DoD7(
    engine: Engine, key_present: None
) -> None:
    """DoD-7 / D1 — and from a `threading.Thread`, which is the shape of a sync route on the
    threadpool: no loop is running there either, and the same vectors come back.
    """
    handle = _opened(engine, factory := fake_factory(dim=DIMENSION))
    outcome: dict[str, Any] = {}

    def worker() -> None:
        try:
            outcome["vectors"] = embed_texts(handle, TEXTS)
        except Exception as error:  # reported to the main thread below, never swallowed
            outcome["error"] = error

    thread = threading.Thread(target=worker, name="s024-002-embed-worker")
    thread.start()
    thread.join(timeout=30)

    assert not thread.is_alive()
    assert outcome.get("error") is None
    assert outcome["vectors"] == vectors_for(TEXTS, DIMENSION)
    assert factory.embed_calls == [(MODEL_NAME, tuple(TEXTS))]


# =========================================================================== DoD-8


def _ensure_vectors(engine: Engine) -> None:
    with engine.begin() as connection:
        ensure_vector_tables(connection, DIMENSION)


@pytest.mark.parametrize("table_name", VEC_TABLES)
def test_writing_twice_leaves_one_row_holding_the_second_vector__S024_002_DoD8(
    engine: Engine, table_name: str
) -> None:
    """DoD-8 / D4 — the upsert is not `INSERT OR REPLACE`: a second write of the same
    snowflake id leaves exactly one row, holding the second vector.
    """
    _ensure_vectors(engine)

    with engine.begin() as connection:
        write_vector(connection, table_name, ROW_ID, VECTOR_ONE)
        write_vector(connection, table_name, ROW_ID, VECTOR_TWO)

    with engine.connect() as connection:
        assert _row_count(connection, table_name) == 1
        assert _read_vector(connection, table_name, ROW_ID) == VECTOR_TWO


@pytest.mark.parametrize("table_name", VEC_TABLES)
def test_a_written_vector_is_serialised_as_float32__S024_002_DoD8(
    engine: Engine, table_name: str
) -> None:
    """DoD-8 / D4 — the stored blob is byte-identical to `serialize_float32` of the vector."""
    _ensure_vectors(engine)

    with engine.begin() as connection:
        write_vector(connection, table_name, ROW_ID, VECTOR_ONE)

    with engine.connect() as connection:
        assert _read_blob(connection, table_name, ROW_ID) == sqlite_vec.serialize_float32(VECTOR_ONE)


@pytest.mark.parametrize("table_name", VEC_TABLES)
def test_writing_two_ids_keeps_them_apart__S024_002_DoD8(engine: Engine, table_name: str) -> None:
    """DoD-8 — the upsert touches only the row it was given (both ids above 2^60)."""
    _ensure_vectors(engine)

    with engine.begin() as connection:
        write_vector(connection, table_name, ROW_ID, VECTOR_ONE)
        write_vector(connection, table_name, OTHER_ROW_ID, VECTOR_TWO)
        write_vector(connection, table_name, ROW_ID, VECTOR_TWO)

    with engine.connect() as connection:
        assert _row_count(connection, table_name) == 2
        assert _read_vector(connection, table_name, ROW_ID) == VECTOR_TWO
        assert _read_vector(connection, table_name, OTHER_ROW_ID) == VECTOR_TWO


@pytest.mark.parametrize("table_name", VEC_TABLES)
def test_delete_removes_the_row__S024_002_DoD8(engine: Engine, table_name: str) -> None:
    """DoD-8 / D4 — delete is by id, and it removes that row and no other."""
    _ensure_vectors(engine)
    with engine.begin() as connection:
        write_vector(connection, table_name, ROW_ID, VECTOR_ONE)
        write_vector(connection, table_name, OTHER_ROW_ID, VECTOR_TWO)

    with engine.begin() as connection:
        delete_vector(connection, table_name, ROW_ID)

    with engine.connect() as connection:
        assert _read_vector(connection, table_name, ROW_ID) is None
        assert _read_vector(connection, table_name, OTHER_ROW_ID) == VECTOR_TWO
        assert _row_count(connection, table_name) == 1


@pytest.mark.parametrize("table_name", VEC_TABLES)
def test_deleting_an_absent_id_raises_nothing__S024_002_DoD8(engine: Engine, table_name: str) -> None:
    """DoD-8 / D4 — deleting an id with no row is not an error, and changes nothing."""
    _ensure_vectors(engine)
    with engine.begin() as connection:
        write_vector(connection, table_name, OTHER_ROW_ID, VECTOR_ONE)

    with engine.begin() as connection:
        delete_vector(connection, table_name, ROW_ID)  # never written
        delete_vector(connection, table_name, ROW_ID)  # and again

    with engine.connect() as connection:
        assert _row_count(connection, table_name) == 1
        assert _read_vector(connection, table_name, OTHER_ROW_ID) == VECTOR_ONE


@pytest.mark.parametrize("table_name", VEC_TABLES)
def test_deleting_when_the_table_was_never_created_raises_nothing__S024_002_DoD8(
    engine: Engine, table_name: str
) -> None:
    """DoD-8 / Interface intent — `delete_vector` is a no-op when the vector table does not
    exist. This is the tolerance a memo delete and a refresh rely on before any model has
    ever been designated (D2: the vector half is only ensured after a designation).
    """
    with engine.connect() as connection:
        assert _key_column(connection, table_name) is None  # never ensured

    with engine.begin() as connection:
        delete_vector(connection, table_name, ROW_ID)

    with engine.connect() as connection:
        assert _key_column(connection, table_name) is None  # and it was not created either


# =========================================================================== DoD-10


def _module_imports() -> list[str]:
    tree = ast.parse(inspect.getsource(embedding_module))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
    return imported


def test_the_module_imports_no_fastapi__S024_002_DoD10() -> None:
    """DoD-10 — `services/embedding.py` imports no `fastapi` (nor its `starlette` base):
    services take the factory and the timeout as parameters (`context.md` cross-cutting
    constraints).
    """
    offenders = [name for name in _module_imports() if name.split(".")[0] in {"fastapi", "starlette"}]
    assert offenders == []


def test_the_module_binds_no_fastapi_symbol__S024_002_DoD10() -> None:
    """DoD-10 — and no module-level name in it is a fastapi/starlette object."""
    offenders = []
    for name, value in vars(embedding_module).items():
        origin = getattr(value, "__module__", None) or getattr(value, "__name__", "")
        if isinstance(origin, str) and origin.split(".")[0] in {"fastapi", "starlette"}:
            offenders.append(name)
    assert offenders == []
