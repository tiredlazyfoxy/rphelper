"""Tests for ``app.services.llm_registry`` — model enablement, the embedding designation and the
two use-time validators.

Feature 006, step 004 (``004.model-enablement-and-designation.md``). Every expected value comes
from that step's Interface intent and DoD-1 .. DoD-21, ``004.context.md`` and feature 006
``context.md`` (D2 the measured dimension, D4 use-time validation with no cascade, D5 no branch
on kind, D10 rows persist, D12 the validator's pair argument, R4 no substitution, R5 no reverse
lookup). Bindings come from ``## Skeleton`` -> ``Step 004`` (and ``Step 003`` for setup) in
feature 006's ``status.md``.

As ``004.context.md`` says, the validators ship with no call site, so DoD-15 .. DoD-20 are
tested directly against the service with rows written by each test's own setup.

Mechanics (same as ``test_llm_registry_servers.py``):
- a real SQLite file per test (``db_engine``) with ``metadata.create_all``;
- every operation is called on a *fresh* connection with no transaction open, and every
  post-condition is read on another fresh connection;
- the outbound client is faked through the frozen ``client_factory=`` seam — a callable taking
  ``(base_url, resolved_api_key, timeout_seconds)`` positionally and returning an object with
  async ``probe()`` / ``embed()``; a few DoD-10/12 tests use the real step-002 client over
  ``httpx.MockTransport`` instead; no network;
- async operations run under ``asyncio.run``.

Tests are suffixed ``__S006_004_DoD<n>``. DoD-22 and DoD-23 are ``[manual/live]``.
"""

import ast
import asyncio
import inspect
import json
import re
from collections.abc import Callable, Coroutine, Iterator, Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import Engine, Table, event, func, select, text
from sqlalchemy.exc import DBAPIError

import app.services.llm_registry as registry_module
from app.config import Settings
from app.db import schema
from app.errors import (
    LlmServerNotFoundError,
    LlmUnreachableError,
    ModelNotEnabledError,
    NoEmbeddingModelError,
    SecretRefError,
)
from app.services.llm.client import EMBED_NO_VECTOR_REASON, LlmClient, ProbeOutcome, ProbeResult
from app.services.llm_registry import (
    EMBEDDING_PROBE_TEXT,
    DesignatedEmbeddingModel,
    EnabledChatModel,
    LlmServer,
    ModelRefLevel,
    clear_embedding_designation,
    create_server,
    delete_server,
    designate_embedding_model,
    get_server,
    set_enabled_models,
    validate_chat_model,
    validate_embedding_model,
)

BASE_URL = "http://llm.test:8080"
OTHER_BASE_URL = "http://other.test:9090/v1"
KEY_VARIABLE = "S006_004_API_KEY"
POINTER = "$" + KEY_VARIABLE
RESOLVED_KEY = "sk-S006-004-RESOLVED-CREDENTIAL"
MISSING_VARIABLE = "S006_004_ABSENT_VARIABLE"
MISSING_POINTER = "$" + MISSING_VARIABLE
OLD_TEXT = "2020-01-01T00:00:00+00:00"
UNKNOWN_SERVER_ID = 9_999_999_999
BIG_SERVER_ID = 9_007_199_254_740_993  # > 2**53: only a decimal string carries it exactly

USER_SCOPED_WORDS = ("user", "session", "character", "memo", "count", "usage", "dependent", "owner")


# --------------------------------------------------------------------------- helpers


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run one coroutine to completion on a fresh event loop."""
    return asyncio.run(coro)


class CountingIdGenerator:
    """A generator stand-in whose ``next_id()`` answers ``start, start + 1, ...``."""

    def __init__(self, start: int) -> None:
        self._next = start
        self.calls = 0
        self.issued: list[int] = []

    def next_id(self) -> int:
        self.calls += 1
        value = self._next
        self._next += 1
        self.issued.append(value)
        return value


class FakeClient:
    """Implements the frozen ``LlmClientLike`` protocol; ``embed`` answers fixed vectors or raises."""

    def __init__(self, vectors: list[list[float]] | None, error: Exception | None) -> None:
        self._vectors = vectors
        self._error = error
        self.probe_calls = 0
        self.embed_calls: list[tuple[str, list[str]]] = []

    async def probe(self) -> ProbeResult:
        self.probe_calls += 1
        return ProbeResult(outcome=ProbeOutcome.REACHABLE, model_names=("m",))

    async def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
        self.embed_calls.append((model, list(texts)))
        if self._error is not None:
            raise self._error
        assert self._vectors is not None
        return [list(vector) for vector in self._vectors]


class FakeFactory:
    """A client factory recording every positional call it receives."""

    def __init__(self, vectors: list[list[float]] | None = None, error: Exception | None = None) -> None:
        self.vectors = vectors
        self.error = error
        self.calls: list[tuple[Any, ...]] = []
        self.clients: list[FakeClient] = []

    def __call__(self, base_url: str, api_key: str | None, timeout_seconds: float) -> FakeClient:
        self.calls.append((base_url, api_key, timeout_seconds))
        client = FakeClient(self.vectors, self.error)
        self.clients.append(client)
        return client

    @property
    def embed_calls(self) -> list[tuple[str, list[str]]]:
        return [call for client in self.clients for call in client.embed_calls]

    @property
    def probe_calls(self) -> int:
        return sum(client.probe_calls for client in self.clients)


def vectors_of(dim: int) -> list[list[float]]:
    return [[0.125] * dim]


def dim_factory(dim: int) -> FakeFactory:
    return FakeFactory(vectors=vectors_of(dim))


def failing_factory(reason: str) -> FakeFactory:
    return FakeFactory(error=LlmUnreachableError("embeddings call failed", {"reason": reason}))


def mock_transport_factory(handler: Callable[[httpx.Request], httpx.Response]) -> Callable[..., LlmClient]:
    """A factory building the real step-002 client over a mock transport."""

    def factory(base_url: str, api_key: str | None, timeout_seconds: float) -> LlmClient:
        return LlmClient(base_url, api_key, timeout_seconds, transport=httpx.MockTransport(handler))

    return factory


def _servers() -> Table:
    return schema.metadata.tables["llm_servers"]


def _models() -> Table:
    return schema.metadata.tables["models"]


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    return db_engine


@pytest.fixture
def key_present(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv(KEY_VARIABLE, RESOLVED_KEY)
    monkeypatch.delenv(MISSING_VARIABLE, raising=False)
    yield


def _new(engine: Engine, server_id: int, name: str | None = None, kind: str = "llamaswap",
         base_url: str = BASE_URL, **pointer: Any) -> LlmServer:
    with engine.connect() as connection:
        return create_server(
            connection, CountingIdGenerator(server_id), name or f"server {server_id}", kind, base_url, **pointer
        )


def _get(engine: Engine, server_id: int) -> LlmServer:
    with engine.connect() as connection:
        return get_server(connection, server_id)


def _set(engine: Engine, generator: Any, server_id: int, names: Any) -> list[str]:
    with engine.connect() as connection:
        return set_enabled_models(connection, generator, server_id, names)


def _designate(engine: Engine, generator: Any, server_id: int, model_name: str, settings: Settings,
               factory: Any) -> LlmServer:
    with engine.connect() as connection:
        return run(designate_embedding_model(
            connection, generator, server_id, model_name, settings, client_factory=factory
        ))


def _clear(engine: Engine, server_id: int) -> None:
    with engine.connect() as connection:
        return clear_embedding_designation(connection, server_id)


def _validate_chat(engine: Engine, server_id: int, model_name: str,
                   level: ModelRefLevel = ModelRefLevel.SESSION) -> EnabledChatModel:
    with engine.connect() as connection:
        return validate_chat_model(connection, server_id, model_name, level)


def _validate_embedding(engine: Engine) -> DesignatedEmbeddingModel:
    with engine.connect() as connection:
        return validate_embedding_model(connection)


def _model_rows(engine: Engine, server_id: int | None = None) -> list[dict[str, Any]]:
    statement = select(_models()).order_by(_models().c.id)
    if server_id is not None:
        statement = statement.where(_models().c.server_id == server_id)
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(statement).mappings().all()]


def _row(engine: Engine, server_id: int, name: str) -> dict[str, Any] | None:
    matches = [row for row in _model_rows(engine, server_id) if row["model_name"] == name]
    assert len(matches) <= 1
    return matches[0] if matches else None


def _snapshot(engine: Engine) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with engine.connect() as connection:
        servers = [dict(r) for r in connection.execute(select(_servers()).order_by(_servers().c.id)).mappings()]
    return servers, _model_rows(engine)


def _enabled_map(engine: Engine) -> dict[tuple[int, str], bool]:
    return {(row["server_id"], row["model_name"]): row["is_enabled"] for row in _model_rows(engine)}


def _designated_rows(engine: Engine) -> list[tuple[int, str]]:
    return [(row["server_id"], row["model_name"]) for row in _model_rows(engine) if row["is_embedding_designated"]]


def _insert_model(
    engine: Engine,
    *,
    model_id: int,
    server_id: int,
    name: str,
    enabled: bool = False,
    designated: bool = False,
    dim: int | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            _models().insert().values(
                id=model_id,
                server_id=server_id,
                model_name=name,
                is_enabled=enabled,
                is_embedding_designated=designated,
                embedding_dim=dim,
                created_at=OLD_TEXT,
                updated_at=OLD_TEXT,
            )
        )


def _module_tree() -> ast.Module:
    source_file = inspect.getsourcefile(registry_module)
    assert source_file is not None
    return ast.parse(Path(source_file).read_text(encoding="utf-8"))


def _docstring_nodes(tree: ast.Module) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                found.add(id(body[0].value))
    return found


def _mentions_kind(node: ast.AST) -> bool:
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name) and inner.id == "kind":
            return True
        if isinstance(inner, ast.Attribute) and inner.attr == "kind":
            return True
    return False


class StatementRecorder:
    """Records every SQL statement the engine sends while attached."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.statements: list[str] = []

    def _listener(self, conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        self.statements.append(statement)

    def __enter__(self) -> "StatementRecorder":
        event.listen(self.engine, "before_cursor_execute", self._listener)
        return self

    def __exit__(self, *exc: object) -> None:
        event.remove(self.engine, "before_cursor_execute", self._listener)

    def tables_touched(self) -> set[str]:
        touched: set[str] = set()
        pattern = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+[\"`\[]?([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
        for statement in self.statements:
            touched.update(match.lower() for match in pattern.findall(statement))
        return touched


# ============================================================================ DoD-1


def test_enabling_a_model_without_a_row_creates_one_enabled__S006_004_DoD1(engine: Engine) -> None:
    """DoD-1 — a named model with no row gets one, minted from the generator handed in, with
    `is_enabled` true; it then appears in the server's enabled names (US-014.AC-1, UC-012)."""
    _new(engine, 101)
    generator = CountingIdGenerator(700_001)

    returned = _set(engine, generator, 101, ["chat-a"])

    assert list(returned) == ["chat-a"]
    assert generator.calls == 1
    row = _row(engine, 101, "chat-a")
    assert row is not None
    assert row["id"] == 700_001
    assert row["is_enabled"] is True
    assert row["is_embedding_designated"] is False
    assert row["embedding_dim"] is None
    assert row["created_at"] and row["updated_at"]
    assert list(_get(engine, 101).enabled_model_names) == ["chat-a"]


def test_enabling_several_new_models_creates_one_row_each__S006_004_DoD1(engine: Engine) -> None:
    """DoD-1 — every named model without a row gets its own enabled row with its own id."""
    _new(engine, 102)
    generator = CountingIdGenerator(710_001)

    returned = _set(engine, generator, 102, ["m1", "m2", "m3"])

    assert sorted(returned) == ["m1", "m2", "m3"]
    rows = _model_rows(engine, 102)
    assert sorted(row["model_name"] for row in rows) == ["m1", "m2", "m3"]
    assert all(row["is_enabled"] is True for row in rows)
    assert sorted(row["id"] for row in rows) == sorted(generator.issued)
    assert generator.calls == 3
    assert sorted(_get(engine, 102).enabled_model_names) == ["m1", "m2", "m3"]


def test_naming_a_model_with_a_disabled_row_enables_that_row__S006_004_DoD1(engine: Engine) -> None:
    """DoD-1 / intent — a named model that already has a row has `is_enabled` set true; no new row."""
    _new(engine, 103)
    _insert_model(engine, model_id=1031, server_id=103, name="existing", enabled=False)
    generator = CountingIdGenerator(720_001)

    returned = _set(engine, generator, 103, ["existing"])

    assert list(returned) == ["existing"]
    assert generator.calls == 0
    rows = _model_rows(engine, 103)
    assert [(row["id"], row["is_enabled"]) for row in rows] == [(1031, True)]


# ============================================================================ DoD-2


def test_omitted_model_is_disabled_not_deleted__S006_004_DoD2(engine: Engine) -> None:
    """DoD-2 — a previously enabled model omitted from the set has `is_enabled` false and its row
    still exists (US-014.AC-2; D10)."""
    _new(engine, 201)
    _insert_model(engine, model_id=2011, server_id=201, name="keep", enabled=True)
    _insert_model(engine, model_id=2012, server_id=201, name="drop", enabled=True)

    returned = _set(engine, CountingIdGenerator(730_001), 201, ["keep"])

    assert list(returned) == ["keep"]
    rows = {row["model_name"]: row for row in _model_rows(engine, 201)}
    assert set(rows) == {"keep", "drop"}
    assert rows["keep"]["is_enabled"] is True
    assert rows["drop"]["is_enabled"] is False
    assert rows["drop"]["id"] == 2012
    assert list(_get(engine, 201).enabled_model_names) == ["keep"]


def test_a_disabled_row_stays_addressable_and_can_be_re_enabled__S006_004_DoD2(engine: Engine) -> None:
    """DoD-2 — the surviving row is the same row a later enable flips back; no new id is minted."""
    _new(engine, 202)
    _insert_model(engine, model_id=2021, server_id=202, name="stale", enabled=True)
    generator = CountingIdGenerator(740_001)

    _set(engine, generator, 202, [])
    after_disable = _row(engine, 202, "stale")
    assert after_disable is not None and after_disable["is_enabled"] is False

    _set(engine, generator, 202, ["stale"])
    after_enable = _row(engine, 202, "stale")
    assert after_enable is not None
    assert after_enable["id"] == 2021
    assert after_enable["is_enabled"] is True
    assert generator.calls == 0


def test_a_stale_enablement_not_offered_any_more_is_clearable__S006_004_DoD2(engine: Engine) -> None:
    """DoD-2 — a model that is enabled but no longer offered can be unchecked: submitting a set that
    omits it disables it, whatever the server currently offers."""
    _new(engine, 203)
    _set(engine, CountingIdGenerator(750_001), 203, ["gone-from-server", "still-offered"])
    returned = _set(engine, CountingIdGenerator(750_101), 203, ["still-offered"])
    assert list(returned) == ["still-offered"]
    gone = _row(engine, 203, "gone-from-server")
    assert gone is not None and gone["is_enabled"] is False


# ============================================================================ DoD-3


def test_empty_set_disables_everything_and_deletes_nothing__S006_004_DoD3(engine: Engine) -> None:
    """DoD-3 — submitting the empty set disables every model on that server and deletes no row."""
    _new(engine, 301)
    _insert_model(engine, model_id=3011, server_id=301, name="a", enabled=True)
    _insert_model(engine, model_id=3012, server_id=301, name="b", enabled=True)
    _insert_model(engine, model_id=3013, server_id=301, name="c", enabled=False)
    before_ids = [row["id"] for row in _model_rows(engine, 301)]

    returned = _set(engine, CountingIdGenerator(760_001), 301, [])

    assert list(returned) == []
    rows = _model_rows(engine, 301)
    assert [row["id"] for row in rows] == before_ids
    assert all(row["is_enabled"] is False for row in rows)
    assert list(_get(engine, 301).enabled_model_names) == []


def test_empty_set_on_one_server_leaves_other_servers_enabled__S006_004_DoD3(engine: Engine) -> None:
    """DoD-3 — "every model on that server": another server's enablements are untouched."""
    _new(engine, 302)
    _new(engine, 303)
    _insert_model(engine, model_id=3021, server_id=302, name="a", enabled=True)
    _insert_model(engine, model_id=3031, server_id=303, name="a", enabled=True)
    other_before = _model_rows(engine, 303)

    _set(engine, CountingIdGenerator(770_001), 302, [])

    assert _model_rows(engine, 303) == other_before


# ============================================================================ DoD-4


def test_resubmitting_the_same_set_is_idempotent__S006_004_DoD4(engine: Engine) -> None:
    """DoD-4 — no row is created, deleted or duplicated on a re-submit (UC-012)."""
    _new(engine, 401)
    first_generator = CountingIdGenerator(780_001)
    first = _set(engine, first_generator, 401, ["x", "y"])
    rows_after_first = [(row["id"], row["model_name"], row["is_enabled"]) for row in _model_rows(engine)]

    second_generator = CountingIdGenerator(790_001)
    second = _set(engine, second_generator, 401, ["x", "y"])
    rows_after_second = [(row["id"], row["model_name"], row["is_enabled"]) for row in _model_rows(engine)]

    assert sorted(first) == sorted(second) == ["x", "y"]
    assert second_generator.calls == 0
    assert rows_after_second == rows_after_first
    assert len(rows_after_second) == 2


def test_duplicate_names_in_one_submission_make_one_row__S006_004_DoD4(engine: Engine) -> None:
    """DoD-4 — the unique (server, model) pair holds even when a name is repeated in the input."""
    _new(engine, 402)
    returned = _set(engine, CountingIdGenerator(800_001), 402, ["dup", "dup"])
    assert list(returned) == ["dup"]
    assert [row["model_name"] for row in _model_rows(engine, 402)] == ["dup"]


def test_the_unique_pair_holds_after_mixed_submissions__S006_004_DoD4(engine: Engine) -> None:
    """DoD-4 — after enabling, disabling and re-enabling, each (server, model) pair has one row."""
    _new(engine, 403)
    generator = CountingIdGenerator(810_001)
    _set(engine, generator, 403, ["a", "b"])
    _set(engine, generator, 403, ["b", "c"])
    _set(engine, generator, 403, ["a", "b", "c"])
    _set(engine, generator, 403, ["a", "b", "c"])
    with engine.connect() as connection:
        groups = connection.execute(
            select(_models().c.server_id, _models().c.model_name, func.count())
            .group_by(_models().c.server_id, _models().c.model_name)
        ).all()
    assert sorted((row[1], row[2]) for row in groups) == [("a", 1), ("b", 1), ("c", 1)]
    assert generator.calls == 3


# ============================================================================ DoD-5


def test_same_name_is_enabled_independently_on_two_servers__S006_004_DoD5(engine: Engine) -> None:
    """DoD-5 — enabling a name on one server does not change the other (UC-012; D10)."""
    _new(engine, 501)
    _new(engine, 502)
    generator = CountingIdGenerator(820_001)

    _set(engine, generator, 501, ["gpt-4o"])
    assert _row(engine, 502, "gpt-4o") is None
    assert list(_get(engine, 502).enabled_model_names) == []

    _set(engine, generator, 502, ["gpt-4o"])
    a_row = _row(engine, 501, "gpt-4o")
    b_row = _row(engine, 502, "gpt-4o")
    assert a_row is not None and b_row is not None
    assert a_row["id"] != b_row["id"]
    assert a_row["is_enabled"] is True and b_row["is_enabled"] is True

    _set(engine, generator, 501, [])
    a_after = _row(engine, 501, "gpt-4o")
    b_after = _row(engine, 502, "gpt-4o")
    assert a_after is not None and a_after["is_enabled"] is False
    assert b_after == b_row
    assert list(_get(engine, 502).enabled_model_names) == ["gpt-4o"]


# ============================================================================ DoD-6


def test_set_enabled_models_has_no_way_to_report_a_dependency__S006_004_DoD6() -> None:
    """DoD-6 — the operation takes the connection, the generator, the server id and the names,
    nothing more; it is not async (no outbound call)."""
    signature = inspect.signature(set_enabled_models)
    assert list(signature.parameters) == ["connection", "generator", "server_id", "model_names"]
    assert not inspect.iscoroutinefunction(set_enabled_models)


def test_disabling_is_never_refused__S006_004_DoD6(engine: Engine) -> None:
    """DoD-6 — disabling every model, including a designated one, succeeds; the answer is the
    enabled names and nothing else (US-016.AC-1, R5)."""
    _new(engine, 601)
    _insert_model(engine, model_id=6011, server_id=601, name="chat", enabled=True)
    _insert_model(engine, model_id=6012, server_id=601, name="embed", enabled=True, designated=True, dim=64)

    returned = _set(engine, CountingIdGenerator(830_001), 601, [])

    assert isinstance(returned, list)
    assert returned == []
    assert all(row["is_enabled"] is False for row in _model_rows(engine, 601))


def test_set_enabled_models_returns_only_names__S006_004_DoD6(engine: Engine) -> None:
    """DoD-6 — the return value carries the enabled names as strings, no count and no dependents."""
    _new(engine, 602)
    returned = _set(engine, CountingIdGenerator(840_001), 602, ["a", "b"])
    assert isinstance(returned, list)
    assert all(isinstance(name, str) for name in returned)
    assert sorted(returned) == ["a", "b"]


def test_set_enabled_models_touches_only_the_two_registry_tables__S006_004_DoD6(engine: Engine) -> None:
    """DoD-6 — it issues no query against any table but `llm_servers` and `models` (R5)."""
    _new(engine, 603)
    _insert_model(engine, model_id=6031, server_id=603, name="old", enabled=True, designated=True, dim=8)
    with StatementRecorder(engine) as recorder:
        _set(engine, CountingIdGenerator(850_001), 603, ["new"])
        _set(engine, CountingIdGenerator(850_101), 603, [])
    assert recorder.statements
    touched = recorder.tables_touched()
    assert touched <= {"llm_servers", "models"}, touched
    other_tables = set(schema.metadata.tables) - {"llm_servers", "models"}
    # 023/001 DoD-3: `translations` joins the belt-and-braces list of tables the registry
    # must never name (feature 023 context.md R8 — only `services/translation.py` reads it).
    for statement in recorder.statements:
        for table_name in other_tables | {"sessions", "characters", "memos", "translations"}:
            assert not re.search(rf"\b{re.escape(table_name)}\b", statement, re.IGNORECASE), statement


def test_set_enabled_models_unknown_server_raises_not_found_and_writes_nothing__S006_004_DoD6(
    engine: Engine,
) -> None:
    """DoD-6 / intent — the only error is `llm_server_not_found` for an unknown server."""
    _new(engine, 604)
    _insert_model(engine, model_id=6041, server_id=604, name="m", enabled=True)
    before = _snapshot(engine)
    generator = CountingIdGenerator(860_001)
    with pytest.raises(LlmServerNotFoundError) as caught:
        _set(engine, generator, UNKNOWN_SERVER_ID, ["m", "n"])
    assert caught.value.code == "llm_server_not_found"
    assert _snapshot(engine) == before


# ============================================================================ DoD-7


def test_disabling_the_designated_model_keeps_the_designation__S006_004_DoD7(engine: Engine) -> None:
    """DoD-7 — disabling the designated embedding model succeeds and leaves the flag and
    `embedding_dim` in place: no cascade (D4)."""
    _new(engine, 701)
    _insert_model(engine, model_id=7011, server_id=701, name="embedder", enabled=True, designated=True, dim=768)
    _insert_model(engine, model_id=7012, server_id=701, name="chat", enabled=True)

    returned = _set(engine, CountingIdGenerator(870_001), 701, ["chat"])

    assert list(returned) == ["chat"]
    row = _row(engine, 701, "embedder")
    assert row is not None
    assert row["is_enabled"] is False
    assert row["is_embedding_designated"] is True
    assert row["embedding_dim"] == 768
    server = _get(engine, 701)
    assert server.embedding_model_name == "embedder"
    assert server.embedding_dim == 768


def test_enabling_never_touches_designation_or_dimension__S006_004_DoD7(engine: Engine) -> None:
    """DoD-7 — the enable set never writes `is_embedding_designated` or `embedding_dim`."""
    _new(engine, 702)
    _insert_model(engine, model_id=7021, server_id=702, name="embedder", enabled=False, designated=True, dim=384)
    _insert_model(engine, model_id=7022, server_id=702, name="measured", enabled=False, designated=False, dim=99)

    _set(engine, CountingIdGenerator(880_001), 702, ["embedder", "measured", "fresh"])

    rows = {row["model_name"]: row for row in _model_rows(engine, 702)}
    assert (rows["embedder"]["is_embedding_designated"], rows["embedder"]["embedding_dim"]) == (True, 384)
    assert (rows["measured"]["is_embedding_designated"], rows["measured"]["embedding_dim"]) == (False, 99)
    assert (rows["fresh"]["is_embedding_designated"], rows["fresh"]["embedding_dim"]) == (False, None)


# ============================================================================ DoD-8


def test_designating_makes_one_embeddings_call_and_records_the_measured_dimension__S006_004_DoD8(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-8 — exactly one embeddings call against that server; the flag is written true and
    `embedding_dim` equals the length of the returned vector (US-015.AC-1, UC-013; D2)."""
    _new(engine, 801, base_url=OTHER_BASE_URL)
    _insert_model(engine, model_id=8011, server_id=801, name="nomic-embed", enabled=True)
    factory = dim_factory(7)

    result = _designate(engine, CountingIdGenerator(890_001), 801, "nomic-embed", db_settings, factory)

    assert len(factory.calls) == 1
    assert factory.calls[0][0] == OTHER_BASE_URL
    assert factory.calls[0][2] == db_settings.llm_request_timeout_seconds
    assert len(factory.embed_calls) == 1
    assert factory.embed_calls[0][0] == "nomic-embed"
    assert factory.probe_calls == 0

    row = _row(engine, 801, "nomic-embed")
    assert row is not None
    assert row["is_embedding_designated"] is True
    assert row["embedding_dim"] == 7

    assert isinstance(result, LlmServer)
    assert result.id == 801
    assert result.embedding_model_name == "nomic-embed"
    assert result.embedding_dim == 7
    assert result == _get(engine, 801)


@pytest.mark.parametrize("dim", [1, 384, 1536])
def test_the_recorded_dimension_is_the_vector_length__S006_004_DoD8(
    engine: Engine, db_settings: Settings, dim: int
) -> None:
    """DoD-8 — `embedding_dim` is whatever length the returned vector has."""
    _new(engine, 802)
    _designate(engine, CountingIdGenerator(900_001), 802, "embedder", db_settings, dim_factory(dim))
    row = _row(engine, 802, "embedder")
    assert row is not None and row["embedding_dim"] == dim


def test_designating_a_model_without_a_row_creates_it__S006_004_DoD8(engine: Engine, db_settings: Settings) -> None:
    """DoD-8 / intent step 5 — the (server, model) row is upserted: created from the generator when
    absent, flagged and carrying the measured dimension."""
    _new(engine, 803)
    generator = CountingIdGenerator(910_001)
    result = _designate(engine, generator, 803, "brand-new-embed", db_settings, dim_factory(12))
    row = _row(engine, 803, "brand-new-embed")
    assert row is not None
    assert row["id"] == 910_001
    assert generator.calls == 1
    assert row["is_embedding_designated"] is True
    assert row["embedding_dim"] == 12
    assert row["created_at"] and row["updated_at"]
    assert (result.embedding_model_name, result.embedding_dim) == ("brand-new-embed", 12)


def test_re_designating_re_measures_without_complaint__S006_004_DoD8(engine: Engine, db_settings: Settings) -> None:
    """DoD-8 — designating the same model again re-measures; a changed dimension is simply
    recorded (UC-013: no rebuild is forced or prompted)."""
    _new(engine, 804)
    _designate(engine, CountingIdGenerator(920_001), 804, "embedder", db_settings, dim_factory(256))
    result = _designate(engine, CountingIdGenerator(920_101), 804, "embedder", db_settings, dim_factory(512))
    assert result.embedding_dim == 512
    rows = _model_rows(engine, 804)
    assert len(rows) == 1
    assert (rows[0]["is_embedding_designated"], rows[0]["embedding_dim"]) == (True, 512)


def test_designation_hands_the_resolved_credential_to_the_factory__S006_004_DoD8(
    engine: Engine, db_settings: Settings, key_present: None
) -> None:
    """DoD-8 / intent step 2-3 — the pointer is resolved and the factory gets the credential."""
    _new(engine, 805, api_key_ref=POINTER)
    handed = db_settings.model_copy(update={"llm_request_timeout_seconds": 6.5})
    factory = dim_factory(3)
    _designate(engine, CountingIdGenerator(930_001), 805, "embedder", handed, factory)
    assert factory.calls == [(BASE_URL, RESOLVED_KEY, 6.5)]


# ============================================================================ DoD-9


def test_designating_clears_the_flag_on_every_other_row_including_other_servers__S006_004_DoD9(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-9 — designating on server B clears the designation on server A: at most one row in the
    whole table carries the flag (UC-013; data-model.md)."""
    _new(engine, 901)
    _new(engine, 902)
    _insert_model(engine, model_id=9011, server_id=901, name="old-embed", enabled=True, designated=True, dim=384)
    _insert_model(engine, model_id=9012, server_id=901, name="chat", enabled=True)
    _insert_model(engine, model_id=9021, server_id=902, name="new-embed", enabled=True)

    _designate(engine, CountingIdGenerator(940_001), 902, "new-embed", db_settings, dim_factory(1024))

    assert _designated_rows(engine) == [(902, "new-embed")]
    old = _row(engine, 901, "old-embed")
    assert old is not None and old["is_embedding_designated"] is False
    assert _get(engine, 901).embedding_model_name is None
    assert _get(engine, 902).embedding_model_name == "new-embed"


def test_at_most_one_row_is_designated_across_repeated_designations__S006_004_DoD9(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-9 — after any sequence of designations, exactly one row carries the flag."""
    for server_id in (903, 904, 905):
        _new(engine, server_id)
    generator = CountingIdGenerator(950_001)
    for server_id, name, dim in [(903, "e1", 8), (904, "e2", 16), (905, "e3", 32), (903, "e4", 64), (903, "e1", 4)]:
        _designate(engine, generator, server_id, name, db_settings, dim_factory(dim))
        assert _designated_rows(engine) == [(server_id, name)]


def test_designating_on_the_same_server_moves_the_flag__S006_004_DoD9(engine: Engine, db_settings: Settings) -> None:
    """DoD-9 — a second model on the same server takes the flag from the first."""
    _new(engine, 906)
    _insert_model(engine, model_id=9061, server_id=906, name="first", enabled=True, designated=True, dim=10)
    _insert_model(engine, model_id=9062, server_id=906, name="second", enabled=True)
    _designate(engine, CountingIdGenerator(960_001), 906, "second", db_settings, dim_factory(20))
    assert _designated_rows(engine) == [(906, "second")]


_BLOCK_SET_TRIGGERS = (
    "CREATE TRIGGER s006_004_block_set_update BEFORE UPDATE ON models "
    "WHEN NEW.is_embedding_designated = 1 AND OLD.is_embedding_designated = 0 "
    "BEGIN SELECT RAISE(ABORT, 'injected failure'); END",
    "CREATE TRIGGER s006_004_block_set_insert BEFORE INSERT ON models "
    "WHEN NEW.is_embedding_designated = 1 "
    "BEGIN SELECT RAISE(ABORT, 'injected failure'); END",
)
_BLOCK_CLEAR_TRIGGERS = (
    "CREATE TRIGGER s006_004_block_clear BEFORE UPDATE ON models "
    "WHEN OLD.is_embedding_designated = 1 AND NEW.is_embedding_designated = 0 "
    "BEGIN SELECT RAISE(ABORT, 'injected failure'); END",
)


@pytest.mark.parametrize("triggers", [_BLOCK_SET_TRIGGERS, _BLOCK_CLEAR_TRIGGERS], ids=["set-fails", "clear-fails"])
def test_clear_and_set_are_one_transaction__S006_004_DoD9(
    engine: Engine, db_settings: Settings, triggers: tuple[str, ...]
) -> None:
    """DoD-9 — clearing the other rows and writing the new designation commit or roll back
    together: if either half fails, the previous designation is exactly as it was."""
    _new(engine, 907)
    _new(engine, 908)
    _insert_model(engine, model_id=9071, server_id=907, name="old-embed", enabled=True, designated=True, dim=384)
    _insert_model(engine, model_id=9081, server_id=908, name="new-embed", enabled=True)
    before = _snapshot(engine)
    with engine.begin() as connection:
        for statement in triggers:
            connection.execute(text(statement))

    with pytest.raises(DBAPIError):
        _designate(engine, CountingIdGenerator(970_001), 908, "new-embed", db_settings, dim_factory(1024))

    assert _snapshot(engine) == before
    assert _designated_rows(engine) == [(907, "old-embed")]


# ============================================================================ DoD-10


@pytest.mark.parametrize(
    "reason",
    [ProbeOutcome.UNREACHABLE.value, ProbeOutcome.AUTH_FAILED.value, EMBED_NO_VECTOR_REASON],
    ids=["unreachable", "auth_failed", "no_usable_vector"],
)
def test_failed_embeddings_call_raises_and_writes_nothing__S006_004_DoD10(
    engine: Engine, db_settings: Settings, reason: str
) -> None:
    """DoD-10 — a failing call propagates `llm_unreachable` and writes nothing: the previous
    designation survives untouched and no dimension is recorded (D2)."""
    _new(engine, 1001)
    _new(engine, 1002)
    _insert_model(engine, model_id=10011, server_id=1001, name="old-embed", enabled=True, designated=True, dim=384)
    _insert_model(engine, model_id=10021, server_id=1002, name="candidate", enabled=True)
    before = _snapshot(engine)
    generator = CountingIdGenerator(980_001)

    with pytest.raises(LlmUnreachableError) as caught:
        _designate(engine, generator, 1002, "candidate", db_settings, failing_factory(reason))

    assert caught.value.code == "llm_unreachable"
    assert caught.value.detail == {"reason": reason}
    assert _snapshot(engine) == before
    assert _designated_rows(engine) == [(1001, "old-embed")]


def test_failed_call_for_a_model_without_a_row_creates_no_row__S006_004_DoD10(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-10 — nothing at all is written, not even the (server, model) row."""
    _new(engine, 1003)
    before = _snapshot(engine)
    with pytest.raises(LlmUnreachableError):
        _designate(engine, CountingIdGenerator(990_001), 1003, "never-stored", db_settings,
                   failing_factory(ProbeOutcome.UNREACHABLE.value))
    assert _snapshot(engine) == before
    assert _row(engine, 1003, "never-stored") is None


@pytest.mark.parametrize("vectors", [[], [[]]], ids=["no-vector", "empty-vector"])
def test_a_response_with_no_usable_vector_raises_and_writes_nothing__S006_004_DoD10(
    engine: Engine, db_settings: Settings, vectors: list[list[float]]
) -> None:
    """DoD-10 — a successful call answering no usable vector blocks the designation with
    `llm_unreachable` and records no dimension."""
    _new(engine, 1004)
    _insert_model(engine, model_id=10041, server_id=1004, name="old-embed", enabled=True, designated=True, dim=64)
    _insert_model(engine, model_id=10042, server_id=1004, name="candidate", enabled=True)
    before = _snapshot(engine)
    with pytest.raises(LlmUnreachableError):
        _designate(engine, CountingIdGenerator(995_001), 1004, "candidate", db_settings, FakeFactory(vectors=vectors))
    assert _snapshot(engine) == before


def _embeddings_ok(dim: int) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"object": "list", "data": [{"index": 0, "embedding": [0.5] * dim}]})

    return handler


def _raise_connect(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def _raise_timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("timed out", request=request)


def _answer_401(request: httpx.Request) -> httpx.Response:
    return httpx.Response(401, json={"error": {"message": "bad key"}})


def _answer_no_vector(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"object": "list", "data": []})


@pytest.mark.parametrize(
    "handler",
    [_raise_connect, _raise_timeout, _answer_401, _answer_no_vector],
    ids=["transport", "timeout", "auth", "2xx-no-vector"],
)
def test_real_client_failures_block_the_designation__S006_004_DoD10(
    engine: Engine, db_settings: Settings, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    """DoD-10 — transport, timeout, auth, or a 2xx with no usable vector, through the real
    step-002 client: `llm_unreachable` is raised and nothing is written."""
    _new(engine, 1005)
    _insert_model(engine, model_id=10051, server_id=1005, name="old-embed", enabled=True, designated=True, dim=32)
    _insert_model(engine, model_id=10052, server_id=1005, name="candidate", enabled=False)
    before = _snapshot(engine)
    with pytest.raises(LlmUnreachableError):
        _designate(engine, CountingIdGenerator(996_001), 1005, "candidate", db_settings,
                   mock_transport_factory(handler))
    assert _snapshot(engine) == before


def test_real_client_success_records_the_measured_dimension__S006_004_DoD10(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-10 (control) / DoD-8 — the same real client over a healthy transport designates."""
    _new(engine, 1006)
    result = _designate(engine, CountingIdGenerator(997_001), 1006, "candidate", db_settings,
                        mock_transport_factory(_embeddings_ok(5)))
    assert (result.embedding_model_name, result.embedding_dim) == ("candidate", 5)


# ============================================================================ DoD-11


def test_designating_changes_no_rows_enabled_flag__S006_004_DoD11(engine: Engine, db_settings: Settings) -> None:
    """DoD-11 — designating a disabled model does not enable it, and no other row's `is_enabled`
    moves in either direction (D4)."""
    _new(engine, 1101)
    _new(engine, 1102)
    _insert_model(engine, model_id=11011, server_id=1101, name="disabled-target", enabled=False)
    _insert_model(engine, model_id=11012, server_id=1101, name="enabled-chat", enabled=True)
    _insert_model(engine, model_id=11013, server_id=1101, name="disabled-chat", enabled=False)
    _insert_model(engine, model_id=11021, server_id=1102, name="old-embed", enabled=True, designated=True, dim=16)
    _insert_model(engine, model_id=11022, server_id=1102, name="other", enabled=False)
    before = _enabled_map(engine)

    result = _designate(engine, CountingIdGenerator(998_001), 1101, "disabled-target", db_settings, dim_factory(9))

    assert _enabled_map(engine) == before
    target = _row(engine, 1101, "disabled-target")
    assert target is not None and target["is_enabled"] is False
    assert "disabled-target" not in list(result.enabled_model_names)


def test_designating_an_enabled_model_keeps_it_enabled__S006_004_DoD11(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-11 — the other direction: an enabled target stays enabled."""
    _new(engine, 1103)
    _insert_model(engine, model_id=11031, server_id=1103, name="target", enabled=True)
    _designate(engine, CountingIdGenerator(999_001), 1103, "target", db_settings, dim_factory(9))
    target = _row(engine, 1103, "target")
    assert target is not None and target["is_enabled"] is True


def test_designating_a_model_without_a_row_does_not_enable_it__S006_004_DoD11(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-11 — "designating does not enable": a row created by the designation is not enabled."""
    _new(engine, 1104)
    _designate(engine, CountingIdGenerator(999_101), 1104, "created-by-designation", db_settings, dim_factory(9))
    row = _row(engine, 1104, "created-by-designation")
    assert row is not None and row["is_enabled"] is False
    assert list(_get(engine, 1104).enabled_model_names) == []


# ============================================================================ DoD-12


def test_the_probe_text_is_a_fixed_module_constant__S006_004_DoD12() -> None:
    """DoD-12 — the fixed probe string is a non-empty string literal bound at module level, not
    configurable and not built from anything else."""
    assert isinstance(EMBEDDING_PROBE_TEXT, str)
    assert EMBEDDING_PROBE_TEXT.strip()
    assert registry_module.EMBEDDING_PROBE_TEXT is EMBEDDING_PROBE_TEXT
    literal_bindings = 0
    for node in _module_tree().body:
        target_names: list[str] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            target_names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_names = [node.target.id]
            value = node.value
        if "EMBEDDING_PROBE_TEXT" in target_names:
            assert isinstance(value, ast.Constant) and isinstance(value.value, str)
            assert value.value == EMBEDDING_PROBE_TEXT
            literal_bindings += 1
    assert literal_bindings == 1
    assert not any("probe_text" in name.lower() for name in Settings.model_fields)


def test_the_designation_sends_exactly_the_probe_text__S006_004_DoD12(
    engine: Engine, db_settings: Settings, key_present: None
) -> None:
    """DoD-12 — the one embeddings call carries exactly one input, the constant, and none of the
    registration's own data (R5; the redaction rule)."""
    _new(engine, 1201, name="Private Server Name", base_url=OTHER_BASE_URL, api_key_ref=POINTER)
    factory = dim_factory(4)
    _designate(engine, CountingIdGenerator(999_201), 1201, "embedder", db_settings, factory)
    assert factory.embed_calls == [("embedder", [EMBEDDING_PROBE_TEXT])]
    for forbidden in ("Private Server Name", OTHER_BASE_URL, POINTER, KEY_VARIABLE, RESOLVED_KEY):
        assert forbidden not in EMBEDDING_PROBE_TEXT


def test_the_probe_text_is_the_same_for_every_designation__S006_004_DoD12(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-12 — the input does not vary with the server or model designated."""
    _new(engine, 1202, name="alpha")
    _new(engine, 1203, name="beta", kind="openai")
    factory = dim_factory(4)
    generator = CountingIdGenerator(999_301)
    _designate(engine, generator, 1202, "embed-a", db_settings, factory)
    _designate(engine, generator, 1203, "embed-b", db_settings, factory)
    assert [texts for _model, texts in factory.embed_calls] == [[EMBEDDING_PROBE_TEXT], [EMBEDDING_PROBE_TEXT]]


def test_the_wire_request_carries_only_the_probe_text__S006_004_DoD12(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-12 — through the real client, the embeddings request's input is exactly the constant."""
    _new(engine, 1204)
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"object": "list", "data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]})

    _designate(engine, CountingIdGenerator(999_401), 1204, "embedder", db_settings, mock_transport_factory(handler))
    assert len(bodies) == 1
    assert bodies[0]["model"] == "embedder"
    assert bodies[0]["input"] == [EMBEDDING_PROBE_TEXT]


# ============================================================================ DoD-13


def test_missing_variable_raises_before_any_client_and_writes_nothing__S006_004_DoD13(
    engine: Engine, db_settings: Settings, key_present: None
) -> None:
    """DoD-13 — the pointer is resolved before a client is built: an absent variable raises
    `secret_ref_missing`, the factory is never called, nothing is written."""
    _new(engine, 1301)
    _new(engine, 1302, api_key_ref=MISSING_POINTER)
    _insert_model(engine, model_id=13011, server_id=1301, name="old-embed", enabled=True, designated=True, dim=48)
    _insert_model(engine, model_id=13021, server_id=1302, name="candidate", enabled=True)
    before = _snapshot(engine)
    factory = dim_factory(4)

    with pytest.raises(SecretRefError) as caught:
        _designate(engine, CountingIdGenerator(999_501), 1302, "candidate", db_settings, factory)

    assert caught.value.code == "secret_ref_missing"
    assert factory.calls == []
    assert _snapshot(engine) == before


def test_designating_on_an_unknown_server_raises_not_found__S006_004_DoD13(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-13 / intent step 1 — the server is read first: `llm_server_not_found`, no client,
    nothing written."""
    _new(engine, 1303)
    _insert_model(engine, model_id=13031, server_id=1303, name="old-embed", enabled=True, designated=True, dim=48)
    before = _snapshot(engine)
    factory = dim_factory(4)
    with pytest.raises(LlmServerNotFoundError):
        _designate(engine, CountingIdGenerator(999_601), UNKNOWN_SERVER_ID, "x", db_settings, factory)
    assert factory.calls == []
    assert _snapshot(engine) == before


# ============================================================================ DoD-14


def test_clearing_removes_the_flag_and_keeps_everything_else__S006_004_DoD14(engine: Engine) -> None:
    """DoD-14 — the flag goes; `is_enabled`, `embedding_dim` and every row stay (UC-013)."""
    _new(engine, 1401)
    _insert_model(engine, model_id=14011, server_id=1401, name="embedder", enabled=True, designated=True, dim=768)
    _insert_model(engine, model_id=14012, server_id=1401, name="chat", enabled=True)
    _insert_model(engine, model_id=14013, server_id=1401, name="off", enabled=False)
    before = _model_rows(engine)

    assert _clear(engine, 1401) is None

    after = _model_rows(engine)
    assert [row["id"] for row in after] == [row["id"] for row in before]
    assert [row["is_enabled"] for row in after] == [row["is_enabled"] for row in before]
    assert [row["embedding_dim"] for row in after] == [row["embedding_dim"] for row in before]
    assert _designated_rows(engine) == []
    server = _get(engine, 1401)
    assert server.embedding_model_name is None
    assert sorted(server.enabled_model_names) == ["chat", "embedder"]


def test_clearing_is_idempotent__S006_004_DoD14(engine: Engine) -> None:
    """DoD-14 — clearing twice, or on a server with no designation, succeeds and changes nothing more."""
    _new(engine, 1402)
    _insert_model(engine, model_id=14021, server_id=1402, name="embedder", enabled=True, designated=True, dim=64)
    _clear(engine, 1402)
    once = _snapshot(engine)
    assert _clear(engine, 1402) is None
    assert _snapshot(engine) == once

    _new(engine, 1403)
    _insert_model(engine, model_id=14031, server_id=1403, name="chat", enabled=True)
    before = _snapshot(engine)
    assert _clear(engine, 1403) is None
    assert _snapshot(engine) == before


def test_clearing_is_server_scoped__S006_004_DoD14(engine: Engine) -> None:
    """DoD-14 / intent — clearing acts on that server's rows; a designation elsewhere stays."""
    _new(engine, 1404)
    _new(engine, 1405)
    _insert_model(engine, model_id=14041, server_id=1404, name="chat", enabled=True)
    _insert_model(engine, model_id=14051, server_id=1405, name="embedder", enabled=True, designated=True, dim=32)
    before = _snapshot(engine)
    _clear(engine, 1404)
    assert _snapshot(engine) == before


def test_clearing_makes_no_outbound_call__S006_004_DoD14() -> None:
    """DoD-14 — the clear is synchronous and has no settings or client factory to call out with."""
    signature = inspect.signature(clear_embedding_designation)
    assert list(signature.parameters) == ["connection", "server_id"]
    assert not inspect.iscoroutinefunction(clear_embedding_designation)


def test_clearing_on_an_unknown_server_raises_not_found__S006_004_DoD14(engine: Engine) -> None:
    """DoD-14 / intent — `llm_server_not_found` for an unknown server, nothing written."""
    _new(engine, 1406)
    _insert_model(engine, model_id=14061, server_id=1406, name="embedder", enabled=True, designated=True, dim=32)
    before = _snapshot(engine)
    with pytest.raises(LlmServerNotFoundError):
        _clear(engine, UNKNOWN_SERVER_ID)
    assert _snapshot(engine) == before


def test_after_clearing_the_embedding_validator_fails__S006_004_DoD14(engine: Engine) -> None:
    """DoD-14 — with the designation cleared there is no embedding model at use time."""
    _new(engine, 1407)
    _insert_model(engine, model_id=14071, server_id=1407, name="embedder", enabled=True, designated=True, dim=32)
    _clear(engine, 1407)
    with pytest.raises(NoEmbeddingModelError):
        _validate_embedding(engine)


# ============================================================================ DoD-15


@pytest.mark.parametrize("level", [ModelRefLevel.CHARACTER, ModelRefLevel.SESSION], ids=["character", "session"])
def test_chat_validator_returns_the_enabled_model_and_its_server__S006_004_DoD15(
    engine: Engine, level: ModelRefLevel
) -> None:
    """DoD-15 — an enabled row answers the model with its server registration (US-014.AC-1)."""
    _new(engine, 1501, name="chat server", kind="openai", base_url=OTHER_BASE_URL)
    _insert_model(engine, model_id=15011, server_id=1501, name="gpt-4o", enabled=True)
    _insert_model(engine, model_id=15012, server_id=1501, name="other", enabled=True)

    result = _validate_chat(engine, 1501, "gpt-4o", level)

    assert isinstance(result, EnabledChatModel)
    assert result.model_name == "gpt-4o"
    assert isinstance(result.server, LlmServer)
    assert result.server.id == 1501
    assert result.server == _get(engine, 1501)


def test_chat_validator_picks_the_named_server_when_two_offer_the_name__S006_004_DoD15(engine: Engine) -> None:
    """DoD-15 — the pair decides: the same name on two servers answers the server asked for."""
    _new(engine, 1502)
    _new(engine, 1503)
    _insert_model(engine, model_id=15021, server_id=1502, name="shared", enabled=True)
    _insert_model(engine, model_id=15031, server_id=1503, name="shared", enabled=True)
    assert _validate_chat(engine, 1503, "shared").server.id == 1503
    assert _validate_chat(engine, 1502, "shared").server.id == 1502


def test_chat_validator_accepts_a_model_enabled_by_the_service__S006_004_DoD15(engine: Engine) -> None:
    """DoD-15 — a model enabled through the enable set validates."""
    _new(engine, 1504)
    _set(engine, CountingIdGenerator(999_701), 1504, ["freshly-enabled"])
    assert _validate_chat(engine, 1504, "freshly-enabled").model_name == "freshly-enabled"


# ============================================================================ DoD-16


def test_chat_validator_rejects_a_disabled_row_with_no_substitute__S006_004_DoD16(engine: Engine) -> None:
    """DoD-16 — a row with `is_enabled` false raises `model_not_enabled`, even though other enabled
    models exist on that server and the same name is enabled elsewhere (R4)."""
    _new(engine, 1601)
    _new(engine, 1602)
    _insert_model(engine, model_id=16011, server_id=1601, name="disabled", enabled=False)
    _insert_model(engine, model_id=16012, server_id=1601, name="first-enabled", enabled=True)
    _insert_model(engine, model_id=16021, server_id=1602, name="disabled", enabled=True)

    with pytest.raises(ModelNotEnabledError) as caught:
        _validate_chat(engine, 1601, "disabled")
    assert caught.value.code == "model_not_enabled"


def test_chat_validator_rejects_a_model_with_no_row__S006_004_DoD16(engine: Engine) -> None:
    """DoD-16 — no row for the pair raises `model_not_enabled`; no fallback to an enabled one."""
    _new(engine, 1603)
    _insert_model(engine, model_id=16031, server_id=1603, name="enabled", enabled=True)
    with pytest.raises(ModelNotEnabledError):
        _validate_chat(engine, 1603, "never-registered")


def test_chat_validator_rejects_after_a_disable__S006_004_DoD16(engine: Engine) -> None:
    """DoD-16 — a model disabled through the enable set stops validating (US-016.AC-2)."""
    _new(engine, 1604)
    generator = CountingIdGenerator(999_801)
    _set(engine, generator, 1604, ["a", "b"])
    assert _validate_chat(engine, 1604, "a").model_name == "a"
    _set(engine, generator, 1604, ["b"])
    with pytest.raises(ModelNotEnabledError):
        _validate_chat(engine, 1604, "a")


def test_chat_validator_rejects_when_the_server_is_gone__S006_004_DoD16(engine: Engine) -> None:
    """DoD-16 — a deleted server answers `model_not_enabled` (not a not-found error), with no
    substitute from another server offering the same name."""
    _new(engine, 1605)
    _new(engine, 1606)
    _insert_model(engine, model_id=16051, server_id=1605, name="gpt-4o", enabled=True)
    _insert_model(engine, model_id=16061, server_id=1606, name="gpt-4o", enabled=True)
    with engine.connect() as connection:
        delete_server(connection, 1605)

    with pytest.raises(ModelNotEnabledError) as caught:
        _validate_chat(engine, 1605, "gpt-4o")
    assert caught.value.code == "model_not_enabled"
    assert not isinstance(caught.value, LlmServerNotFoundError)

    with pytest.raises(ModelNotEnabledError):
        _validate_chat(engine, UNKNOWN_SERVER_ID, "gpt-4o")


def test_chat_validator_writes_nothing__S006_004_DoD16(engine: Engine) -> None:
    """DoD-16 — validation neither substitutes nor "sanitizes": the stored state is unchanged."""
    _new(engine, 1607)
    _insert_model(engine, model_id=16071, server_id=1607, name="disabled", enabled=False)
    _insert_model(engine, model_id=16072, server_id=1607, name="enabled", enabled=True)
    before = _snapshot(engine)
    with pytest.raises(ModelNotEnabledError):
        _validate_chat(engine, 1607, "disabled")
    _validate_chat(engine, 1607, "enabled")
    assert _snapshot(engine) == before


# ============================================================================ DoD-17


@pytest.mark.parametrize("level", [ModelRefLevel.CHARACTER, ModelRefLevel.SESSION], ids=["character", "session"])
def test_model_not_enabled_detail_is_the_pair_and_the_level__S006_004_DoD17(
    engine: Engine, level: ModelRefLevel
) -> None:
    """DoD-17 — `detail` carries the server id as a decimal string, the model name and the level,
    and nothing else."""
    _new(engine, BIG_SERVER_ID)
    _insert_model(engine, model_id=17011, server_id=BIG_SERVER_ID, name="gpt-4o", enabled=False)

    with pytest.raises(ModelNotEnabledError) as caught:
        _validate_chat(engine, BIG_SERVER_ID, "gpt-4o", level)

    detail = caught.value.detail
    assert detail == {"server_id": str(BIG_SERVER_ID), "model_name": "gpt-4o", "level": level.value}
    assert detail["server_id"] == "9007199254740993"
    assert all(isinstance(value, str) for value in detail.values())
    wire = json.dumps(caught.value.to_wire())
    assert "9007199254740993" in wire


def test_model_ref_level_is_character_or_session_never_user__S006_004_DoD17() -> None:
    """DoD-17 — the level has exactly two values; `user` is not one of them (UC-050, R1)."""
    assert {member.value for member in ModelRefLevel} == {"character", "session"}
    with pytest.raises(ValueError):
        ModelRefLevel("user")
    assert not any("user" in member.name.lower() for member in ModelRefLevel)


def test_model_not_enabled_detail_names_no_count_session_or_user__S006_004_DoD17(engine: Engine) -> None:
    """DoD-17 — no count and nothing about any session or user, in any failing case (R5)."""
    _new(engine, 1702)
    _insert_model(engine, model_id=17021, server_id=1702, name="disabled", enabled=False)
    _insert_model(engine, model_id=17022, server_id=1702, name="enabled", enabled=True)
    for server_id, name in [(1702, "disabled"), (1702, "missing"), (UNKNOWN_SERVER_ID, "enabled")]:
        with pytest.raises(ModelNotEnabledError) as caught:
            _validate_chat(engine, server_id, name, ModelRefLevel.CHARACTER)
        detail = caught.value.detail
        assert set(detail) == {"server_id", "model_name", "level"}
        for key in detail:
            assert not any(word in key.lower() for word in ("count", "session", "user", "dependent", "usage"))
        assert not any(isinstance(value, int) for value in detail.values())
        assert detail["server_id"] == str(server_id)


# ============================================================================ DoD-18


def test_embedding_validator_returns_the_designated_enabled_model__S006_004_DoD18(engine: Engine) -> None:
    """DoD-18 — a designated, enabled model answers its server, name and recorded dimension."""
    _new(engine, 1801)
    _new(engine, 1802, name="embedding host", base_url=OTHER_BASE_URL)
    _insert_model(engine, model_id=18011, server_id=1801, name="chat", enabled=True)
    _insert_model(engine, model_id=18021, server_id=1802, name="nomic-embed", enabled=True, designated=True, dim=768)

    result = _validate_embedding(engine)

    assert isinstance(result, DesignatedEmbeddingModel)
    assert result.model_name == "nomic-embed"
    assert result.embedding_dim == 768
    assert result.server.id == 1802
    assert result.server == _get(engine, 1802)


def test_embedding_validator_after_designating_through_the_service__S006_004_DoD18(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-18 — enable, then designate: the validator answers the measured dimension."""
    _new(engine, 1803)
    generator = CountingIdGenerator(999_901)
    _set(engine, generator, 1803, ["embedder"])
    _designate(engine, generator, 1803, "embedder", db_settings, dim_factory(1536))
    result = _validate_embedding(engine)
    assert (result.server.id, result.model_name, result.embedding_dim) == (1803, "embedder", 1536)


def test_embedding_validator_takes_only_the_connection__S006_004_DoD18() -> None:
    """DoD-18 / intent — the validator takes the connection and nothing else; it is not async."""
    assert list(inspect.signature(validate_embedding_model).parameters) == ["connection"]
    assert not inspect.iscoroutinefunction(validate_embedding_model)
    assert not inspect.iscoroutinefunction(validate_chat_model)


# ============================================================================ DoD-19


def test_embedding_validator_raises_with_no_designation__S006_004_DoD19(engine: Engine) -> None:
    """DoD-19 — no designation at all raises `no_embedding_model`, even with enabled models that
    carry a recorded dimension (no substitution; R4)."""
    _new(engine, 1901)
    _insert_model(engine, model_id=19011, server_id=1901, name="measured-once", enabled=True, dim=384)
    _insert_model(engine, model_id=19012, server_id=1901, name="chat", enabled=True)
    with pytest.raises(NoEmbeddingModelError) as caught:
        _validate_embedding(engine)
    assert caught.value.code == "no_embedding_model"


def test_embedding_validator_raises_with_an_empty_registry__S006_004_DoD19(engine: Engine) -> None:
    """DoD-19 — nothing registered at all is the same failure."""
    with pytest.raises(NoEmbeddingModelError):
        _validate_embedding(engine)


def test_embedding_validator_raises_when_the_designated_model_is_disabled__S006_004_DoD19(engine: Engine) -> None:
    """DoD-19 — designated but not enabled raises `no_embedding_model`, even when another enabled
    model with a dimension exists (the use-time half of D4)."""
    _new(engine, 1902)
    _new(engine, 1903)
    _insert_model(
        engine, model_id=19021, server_id=1902, name="designated-off", enabled=False, designated=True, dim=768
    )
    _insert_model(engine, model_id=19031, server_id=1903, name="enabled-embed", enabled=True, dim=768)
    with pytest.raises(NoEmbeddingModelError) as caught:
        _validate_embedding(engine)
    assert caught.value.code == "no_embedding_model"


def test_disabling_the_designated_model_fails_the_embedding_validator__S006_004_DoD19(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-19 — enable, designate, then disable: the designation stays (DoD-7) but use fails."""
    _new(engine, 1904)
    generator = CountingIdGenerator(1_000_001)
    _set(engine, generator, 1904, ["embedder", "chat"])
    _designate(engine, generator, 1904, "embedder", db_settings, dim_factory(256))
    assert _validate_embedding(engine).model_name == "embedder"
    _set(engine, generator, 1904, ["chat"])
    with pytest.raises(NoEmbeddingModelError):
        _validate_embedding(engine)
    assert _designated_rows(engine) == [(1904, "embedder")]


# ============================================================================ DoD-20


def _assert_nothing_user_scoped(detail: Any) -> None:
    assert isinstance(detail, dict)
    for key, value in detail.items():
        assert not any(word in str(key).lower() for word in USER_SCOPED_WORDS), key
        assert not any(word in str(value).lower() for word in ("session", "character", "memo")), value


def test_no_embedding_model_detail_carries_nothing_user_scoped__S006_004_DoD20(engine: Engine) -> None:
    """DoD-20 — in both failing cases, `detail` names no user, session, character, memo or count."""
    with pytest.raises(NoEmbeddingModelError) as no_designation:
        _validate_embedding(engine)
    _assert_nothing_user_scoped(no_designation.value.detail)

    _new(engine, 2001)
    _insert_model(engine, model_id=20011, server_id=2001, name="designated-off", enabled=False, designated=True, dim=8)
    with pytest.raises(NoEmbeddingModelError) as disabled:
        _validate_embedding(engine)
    _assert_nothing_user_scoped(disabled.value.detail)
    wire = disabled.value.to_wire()
    assert wire is not None
    assert "session" not in json.dumps(wire).lower()


# ============================================================================ DoD-21


def test_module_never_branches_on_kind__S006_004_DoD21() -> None:
    """DoD-21 — no equality/membership comparison or match on `kind`, and no provider-kind literal
    anywhere in the module's code (D5)."""
    tree = _module_tree()
    docstrings = _docstring_nodes(tree)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and _mentions_kind(node):
            if any(isinstance(op, ast.Eq | ast.NotEq | ast.In | ast.NotIn) for op in node.ops):
                offenders.append(ast.dump(node))
        elif isinstance(node, ast.Match) and _mentions_kind(node.subject):
            offenders.append("match on kind")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            lowered = node.value.lower()
            if "llamaswap" in lowered or "openai" in lowered:
                offenders.append(node.value)
    assert offenders == []


def test_both_kinds_designate_and_validate_identically__S006_004_DoD21(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-21 — two registrations differing only in kind build identical clients and behave alike."""
    _new(engine, 2101, name="same", kind="llamaswap")
    _new(engine, 2102, name="same", kind="openai")
    factory = dim_factory(11)
    generator = CountingIdGenerator(1_000_101)
    _set(engine, generator, 2101, ["m"])
    _set(engine, generator, 2102, ["m"])
    first = _designate(engine, generator, 2101, "m", db_settings, factory)
    second = _designate(engine, generator, 2102, "m", db_settings, factory)
    assert factory.calls[0] == factory.calls[1]
    assert factory.embed_calls[0] == factory.embed_calls[1]
    assert (first.embedding_model_name, first.embedding_dim) == (second.embedding_model_name, second.embedding_dim)
    assert _validate_chat(engine, 2101, "m").model_name == _validate_chat(engine, 2102, "m").model_name


def test_every_transaction_is_an_explicit_with_begin_block__S006_004_DoD21() -> None:
    """DoD-21 — every `.begin()` is the context expression of a `with`; nothing commits by hand."""
    tree = _module_tree()
    with_begin_calls: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.With | ast.AsyncWith):
            for item in node.items:
                expr = item.context_expr
                if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) and expr.func.attr == "begin":
                    with_begin_calls.add(id(expr))
    loose_begins: list[str] = []
    commits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "begin" and id(node) not in with_begin_calls:
                loose_begins.append(ast.dump(node))
            if node.func.attr == "commit":
                commits.append(ast.dump(node))
    assert with_begin_calls, "no `with conn.begin():` block at all"
    assert loose_begins == []
    assert commits == []


def test_step_004_operations_leave_no_transaction_open_and_commit__S006_004_DoD21(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-21 — each operation, handed a connection with no transaction open, leaves none open and
    its writes are visible on another connection."""
    _new(engine, 2103)
    factory = dim_factory(6)
    generator = CountingIdGenerator(1_000_201)
    with engine.connect() as connection:
        assert not connection.in_transaction()
        set_enabled_models(connection, generator, 2103, ["chat", "embedder"])
        assert not connection.in_transaction()
        assert sorted(_get(engine, 2103).enabled_model_names) == ["chat", "embedder"]

        run(designate_embedding_model(connection, generator, 2103, "embedder", db_settings, client_factory=factory))
        assert not connection.in_transaction()
        assert _designated_rows(engine) == [(2103, "embedder")]

        validate_chat_model(connection, 2103, "chat", ModelRefLevel.SESSION)
        assert not connection.in_transaction()
        validate_embedding_model(connection)
        assert not connection.in_transaction()

        clear_embedding_designation(connection, 2103)
        assert not connection.in_transaction()
        assert _designated_rows(engine) == []


def test_step_004_signatures_take_a_connection_first__S006_004_DoD21() -> None:
    """DoD-21 / intent — a Core connection first; only the designation is async."""
    functions = (
        set_enabled_models,
        designate_embedding_model,
        clear_embedding_designation,
        validate_chat_model,
        validate_embedding_model,
    )
    for function in functions:
        signature = inspect.signature(function)
        assert list(signature.parameters)[0] == "connection", function.__name__
        rendered = " ".join(str(parameter) for parameter in signature.parameters.values())
        assert "Request" not in rendered
        assert "fastapi" not in rendered.lower()
    assert inspect.iscoroutinefunction(designate_embedding_model)
    for function in (set_enabled_models, clear_embedding_designation, validate_chat_model, validate_embedding_model):
        assert not inspect.iscoroutinefunction(function), function.__name__
