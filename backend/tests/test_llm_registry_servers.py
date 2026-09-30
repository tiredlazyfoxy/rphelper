"""Tests for ``app.services.llm_registry`` — server registrations and the probe primitive.

Feature 006, step 003 (``003.server-registrations-and-probe.md``). Every expected value comes
from that step's Interface intent and DoD-1 .. DoD-21, ``003.context.md`` and feature 006
``context.md`` (D5 no branch on kind, D6 the outcome mapping, D9 the three pointer states,
D10 deleting a connection removes its ``models`` rows, D13 the timeout, D14
``secret_ref_missing`` propagates, R5 no reverse lookup). Bindings come from ``## Skeleton``
-> ``Step 003`` in feature 006's ``status.md``.

Step 004's clauses (enable set, designation, use-time validators) live in
``test_llm_registry_models.py``; nothing here covers them.

Mechanics:
- a real SQLite file per test (``db_engine``) with ``metadata.create_all``;
- every operation is called on a *fresh* connection with no transaction open, and every
  post-condition is read on another fresh connection;
- the outbound client is faked through the frozen ``client_factory=`` seam — a callable taking
  ``(base_url, resolved_api_key, timeout_seconds)`` positionally and returning an object with
  async ``probe()`` / ``embed()``; no network;
- async operations run under ``asyncio.run``.

Tests are suffixed ``__S006_003_DoD<n>``. DoD-22 is ``[manual/live]``.
"""

import ast
import asyncio
import dataclasses
import inspect
import re
from collections.abc import Callable, Coroutine, Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, Table, event, select, text
from sqlalchemy.exc import DBAPIError

import app.services.llm_registry as registry_module
from app.config import Settings, get_settings
from app.db import schema
from app.errors import LlmServerNotFoundError, LlmUnreachableError, SecretRefError
from app.services.llm.client import ProbeOutcome, ProbeResult
from app.services.llm_registry import (
    UNSET,
    ConnectionTestResult,
    LlmServer,
    check_server_connection,
    create_server,
    delete_server,
    get_server,
    list_available_models,
    list_servers,
    probe_server,
    update_server,
)

BASE_URL = "http://llm.test:8080"
OTHER_BASE_URL = "http://other.test:9090/v1"
KEY_VARIABLE = "S006_003_API_KEY"
POINTER = "$" + KEY_VARIABLE
RESOLVED_KEY = "sk-S006-003-RESOLVED-CREDENTIAL"
MISSING_VARIABLE = "S006_003_ABSENT_VARIABLE"
MISSING_POINTER = "$" + MISSING_VARIABLE
OLD_TEXT = "2020-01-01T00:00:00+00:00"
OLD = datetime(2020, 1, 1, tzinfo=UTC)
UNKNOWN_SERVER_ID = 9_999_999_999
PROVIDER_PROSE = "Provider says: your key sk-live-XYZ is revoked, contact billing"

EXPECTED_SERVER_FIELDS = {
    "id",
    "name",
    "kind",
    "base_url",
    "has_api_key",
    "enabled_model_names",
    "embedding_model_name",
    "embedding_dim",
    "last_test_at",
    "last_test_ok",
    "last_test_error",
    "created_at",
    "updated_at",
}

FAILING_OUTCOMES = [ProbeOutcome.UNREACHABLE, ProbeOutcome.AUTH_FAILED, ProbeOutcome.MODEL_LIST_EMPTY]
HTTP_STATUS_LITERALS = {200, 201, 204, 400, 401, 403, 404, 409, 422, 500, 502}


# --------------------------------------------------------------------------- helpers


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run one coroutine to completion on a fresh event loop."""
    return asyncio.run(coro)


class SequenceIdGenerator:
    """A generator stand-in whose ``next_id()`` answers a known sequence of ids."""

    def __init__(self, *values: int) -> None:
        self._values = list(values)
        self.calls = 0

    def next_id(self) -> int:
        self.calls += 1
        return self._values.pop(0)


class FakeClient:
    """Implements the frozen ``LlmClientLike`` protocol; answers a fixed probe result."""

    def __init__(self, result: ProbeResult) -> None:
        self._result = result
        self.probe_calls = 0

    async def probe(self) -> ProbeResult:
        self.probe_calls += 1
        return self._result

    async def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
        raise AssertionError("step 003 never embeds")


class FakeFactory:
    """A client factory recording every positional call it receives."""

    def __init__(self, result: ProbeResult) -> None:
        self.result = result
        self.calls: list[tuple[Any, ...]] = []
        self.clients: list[FakeClient] = []

    def __call__(self, base_url: str, api_key: str | None, timeout_seconds: float) -> FakeClient:
        self.calls.append((base_url, api_key, timeout_seconds))
        client = FakeClient(self.result)
        self.clients.append(client)
        return client

    @property
    def probe_calls(self) -> int:
        return sum(client.probe_calls for client in self.clients)


def outcome_result(outcome: ProbeOutcome, names: Sequence[str] = ()) -> ProbeResult:
    if outcome is ProbeOutcome.REACHABLE and not names:
        names = ("model-a",)
    return ProbeResult(outcome=outcome, model_names=tuple(names), note=PROVIDER_PROSE)


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


def _create(
    engine: Engine,
    generator: Any,
    name: str = "local llamaswap",
    kind: str = "llamaswap",
    base_url: str = BASE_URL,
    **pointer: Any,
) -> LlmServer:
    with engine.connect() as connection:
        return create_server(connection, generator, name, kind, base_url, **pointer)


def _new(engine: Engine, server_id: int, **kwargs: Any) -> LlmServer:
    return _create(engine, SequenceIdGenerator(server_id), **kwargs)


def _list(engine: Engine) -> list[LlmServer]:
    with engine.connect() as connection:
        return list_servers(connection)


def _get(engine: Engine, server_id: int) -> LlmServer:
    with engine.connect() as connection:
        return get_server(connection, server_id)


def _update(engine: Engine, server_id: int, **fields: Any) -> LlmServer:
    with engine.connect() as connection:
        return update_server(connection, server_id, **fields)


def _delete(engine: Engine, server_id: int) -> None:
    with engine.connect() as connection:
        return delete_server(connection, server_id)


def _probe(engine: Engine, server_id: int, settings: Settings, factory: Any) -> ProbeResult:
    with engine.connect() as connection:
        return run(probe_server(connection, server_id, settings, client_factory=factory))


def _check(engine: Engine, server_id: int, settings: Settings, factory: Any) -> ConnectionTestResult:
    with engine.connect() as connection:
        return run(check_server_connection(connection, server_id, settings, client_factory=factory))


def _available(engine: Engine, server_id: int, settings: Settings, factory: Any) -> list[str]:
    with engine.connect() as connection:
        return run(list_available_models(connection, server_id, settings, client_factory=factory))


def _server_row(engine: Engine, server_id: int) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = connection.execute(select(_servers()).where(_servers().c.id == server_id)).mappings().first()
    return dict(row) if row is not None else None


def _model_rows(engine: Engine, server_id: int | None = None) -> list[dict[str, Any]]:
    statement = select(_models()).order_by(_models().c.id)
    if server_id is not None:
        statement = statement.where(_models().c.server_id == server_id)
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(statement).mappings().all()]


def _snapshot(engine: Engine) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with engine.connect() as connection:
        servers = [dict(r) for r in connection.execute(select(_servers()).order_by(_servers().c.id)).mappings()]
    return servers, _model_rows(engine)


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


def _set_timestamps(engine: Engine, server_id: int, value: str = OLD_TEXT) -> None:
    with engine.begin() as connection:
        connection.execute(
            _servers().update().where(_servers().c.id == server_id).values(created_at=value, updated_at=value)
        )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _now() -> datetime:
    return datetime.now(UTC)


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


def test_create_stores_the_row_with_the_generator_id_and_both_timestamps__S006_003_DoD1(engine: Engine) -> None:
    """DoD-1 — name, kind, base URL and pointer are stored; the id is the one the generator
    handed out; both timestamps are set; the new row value is returned (US-012.AC-1)."""
    generator = SequenceIdGenerator(4_242_424_242)
    before = _now()
    created = _create(engine, generator, "my server", "openai", OTHER_BASE_URL, api_key_ref=POINTER)
    after = _now()

    assert generator.calls == 1
    assert isinstance(created, LlmServer)
    assert created.id == 4_242_424_242
    assert created.name == "my server"
    assert created.kind == "openai"
    assert created.base_url == OTHER_BASE_URL
    assert created.has_api_key is True
    assert created.created_at is not None and created.updated_at is not None
    assert before <= _aware(created.created_at) <= after
    assert before <= _aware(created.updated_at) <= after

    row = _server_row(engine, 4_242_424_242)
    assert row is not None
    assert row["name"] == "my server"
    assert row["kind"] == "openai"
    assert row["base_url"] == OTHER_BASE_URL
    assert row["api_key_ref"] == POINTER
    assert row["created_at"] and row["updated_at"]
    assert before <= _aware(datetime.fromisoformat(row["created_at"])) <= after
    assert before <= _aware(datetime.fromisoformat(row["updated_at"])) <= after


def test_created_server_has_never_been_tested_and_has_no_models__S006_003_DoD1(engine: Engine) -> None:
    """DoD-1 — a fresh registration carries no test result and no enabled models."""
    created = _new(engine, 101, api_key_ref=POINTER)
    assert created.last_test_at is None
    assert created.last_test_ok is None
    assert created.last_test_error is None
    assert list(created.enabled_model_names) == []
    assert created.embedding_model_name is None
    assert created.embedding_dim is None


def test_two_creates_use_two_generator_ids__S006_003_DoD1(engine: Engine) -> None:
    """DoD-1 — each create mints its id from the generator it was handed."""
    first = _create(engine, SequenceIdGenerator(5_000_001), "first")
    second = _create(engine, SequenceIdGenerator(9_000_002), "second")
    assert (first.id, second.id) == (5_000_001, 9_000_002)
    assert _server_row(engine, 5_000_001) is not None
    assert _server_row(engine, 9_000_002) is not None


# ============================================================================ DoD-2


def test_created_registration_appears_in_the_listing__S006_003_DoD2(engine: Engine) -> None:
    """DoD-2 — a created registration is in the listing's result (US-012.AC-2)."""
    created = _new(engine, 202, name="listed server", kind="openai", base_url=OTHER_BASE_URL)
    listed = _list(engine)
    assert [server.id for server in listed] == [202]
    only = listed[0]
    assert only.name == "listed server"
    assert only.kind == "openai"
    assert only.base_url == OTHER_BASE_URL
    assert only == created


def test_single_read_returns_the_created_value__S006_003_DoD2(engine: Engine) -> None:
    """DoD-2 — the single-registration read answers the same value the listing carries."""
    _new(engine, 203, api_key_ref=POINTER)
    assert _get(engine, 203) == _list(engine)[0]


# ============================================================================ DoD-3


def test_server_value_has_no_pointer_field__S006_003_DoD3() -> None:
    """DoD-3 — the value exposes a boolean only; the pointer is not a field at all."""
    names = {field.name for field in dataclasses.fields(LlmServer)}
    assert names == EXPECTED_SERVER_FIELDS
    assert "api_key_ref" not in names
    assert not any("ref" in name or "pointer" in name for name in names)
    assert "has_api_key" in names


@pytest.mark.parametrize(
    ("pointer_kwargs", "expected"),
    [({}, False), ({"api_key_ref": None}, False), ({"api_key_ref": ""}, False), ({"api_key_ref": POINTER}, True)],
    ids=["omitted", "none", "empty-string", "pointer"],
)
def test_has_api_key_reflects_the_stored_pointer__S006_003_DoD3(
    engine: Engine, pointer_kwargs: dict[str, Any], expected: bool
) -> None:
    """DoD-3 — no pointer and an empty-string pointer report false; `$NAME` reports true."""
    created = _new(engine, 301, **pointer_kwargs)
    assert created.has_api_key is expected
    assert _get(engine, 301).has_api_key is expected
    assert _list(engine)[0].has_api_key is expected


def test_empty_string_pointer_is_stored_as_null__S006_003_DoD3(engine: Engine) -> None:
    """DoD-3 — an empty pointer on create is stored as no pointer, not as ``""``."""
    _new(engine, 302, api_key_ref="")
    row = _server_row(engine, 302)
    assert row is not None
    assert row["api_key_ref"] is None


def test_no_returned_value_carries_the_pointer_text__S006_003_DoD3(
    engine: Engine, db_settings: Settings, key_present: None
) -> None:
    """DoD-3 — create, list, get, update and test-connection values never carry the pointer."""
    values: list[Any] = [_new(engine, 303, api_key_ref=POINTER)]
    values.extend(_list(engine))
    values.append(_get(engine, 303))
    values.append(_update(engine, 303, name="renamed"))
    tested = _check(engine, 303, db_settings, FakeFactory(outcome_result(ProbeOutcome.REACHABLE)))
    values.append(tested)
    values.append(tested.server)
    for value in values:
        assert POINTER not in repr(value)
        assert KEY_VARIABLE not in repr(value)
        assert RESOLVED_KEY not in repr(value)


# ============================================================================ DoD-4


def test_listing_carries_enabled_names_and_designation_per_server__S006_003_DoD4(engine: Engine) -> None:
    """DoD-4 — each server carries its enabled model names (in models-id order) and the
    designation with its dimension only when the designation is on that server."""
    _new(engine, 401, name="alpha")
    _new(engine, 402, name="beta")
    _new(engine, 403, name="gamma")
    # id order differs from name order on purpose.
    _insert_model(engine, model_id=1001, server_id=401, name="zeta-chat", enabled=True)
    _insert_model(engine, model_id=1002, server_id=401, name="alpha-chat", enabled=True)
    _insert_model(engine, model_id=1003, server_id=401, name="disabled-chat", enabled=False)
    _insert_model(engine, model_id=1004, server_id=402, name="nomic-embed", enabled=True, designated=True, dim=768)
    _insert_model(engine, model_id=1005, server_id=402, name="beta-chat", enabled=True)

    by_id = {server.id: server for server in _list(engine)}
    assert list(by_id[401].enabled_model_names) == ["zeta-chat", "alpha-chat"]
    assert by_id[401].embedding_model_name is None
    assert by_id[401].embedding_dim is None

    assert list(by_id[402].enabled_model_names) == ["nomic-embed", "beta-chat"]
    assert by_id[402].embedding_model_name == "nomic-embed"
    assert by_id[402].embedding_dim == 768

    assert list(by_id[403].enabled_model_names) == []
    assert by_id[403].embedding_model_name is None
    assert by_id[403].embedding_dim is None

    assert _get(engine, 402) == by_id[402]
    assert _get(engine, 401) == by_id[401]


def test_designation_on_a_disabled_row_is_still_reported_but_not_as_enabled__S006_003_DoD4(engine: Engine) -> None:
    """DoD-4 — the enabled names are the enabled rows; the designation is reported where it lives."""
    _new(engine, 404)
    _insert_model(engine, model_id=1101, server_id=404, name="embedder", enabled=False, designated=True, dim=384)
    server = _get(engine, 404)
    assert list(server.enabled_model_names) == []
    assert server.embedding_model_name == "embedder"
    assert server.embedding_dim == 384


def test_server_value_names_no_user_session_character_memo_or_count__S006_003_DoD4() -> None:
    """DoD-4 — nothing about any user, session, character or memo, and no count (R5)."""
    for field in dataclasses.fields(LlmServer):
        lowered = field.name.lower()
        for forbidden in ("user", "session", "character", "memo", "count", "usage", "dependent"):
            assert forbidden not in lowered, field.name


def test_listing_reads_only_the_two_registry_tables__S006_003_DoD4(engine: Engine) -> None:
    """DoD-4 — the listing consults nothing but `llm_servers` and `models` (R5)."""
    _new(engine, 405)
    _insert_model(engine, model_id=1201, server_id=405, name="m", enabled=True)
    with StatementRecorder(engine) as recorder:
        _list(engine)
        _get(engine, 405)
    assert recorder.statements
    assert recorder.tables_touched() <= {"llm_servers", "models"}


# ============================================================================ DoD-5


def test_listing_takes_only_the_connection__S006_003_DoD5() -> None:
    """DoD-5 — no filter, page or sort parameter."""
    assert list(inspect.signature(list_servers).parameters) == ["connection"]


def test_listing_returns_every_registration_in_id_order__S006_003_DoD5(engine: Engine) -> None:
    """DoD-5 — every registration, in a stable id order regardless of creation or name order."""
    _new(engine, 503, name="a-first-by-name")
    _new(engine, 501, name="z-last-by-name")
    _new(engine, 502, name="m-middle")
    first = _list(engine)
    assert [server.id for server in first] == [501, 502, 503]
    assert [server.id for server in _list(engine)] == [501, 502, 503]
    assert _list(engine) == first


def test_listing_of_no_registrations_is_empty__S006_003_DoD5(engine: Engine) -> None:
    """DoD-5 — with nothing registered, the listing is empty."""
    assert _list(engine) == []


# ============================================================================ DoD-6


def test_update_name_only_leaves_everything_else__S006_003_DoD6(engine: Engine) -> None:
    """DoD-6 — only the name changes; kind, base URL and pointer stay; updated_at moves,
    created_at does not (UC-010)."""
    _new(engine, 601, name="before", kind="openai", base_url=OTHER_BASE_URL, api_key_ref=POINTER)
    _set_timestamps(engine, 601)
    before_row = _server_row(engine, 601)
    assert before_row is not None

    updated = _update(engine, 601, name="after")

    assert updated.id == 601
    assert updated.name == "after"
    assert updated.kind == "openai"
    assert updated.base_url == OTHER_BASE_URL
    assert updated.has_api_key is True
    assert _aware(updated.created_at) == OLD
    assert _aware(updated.updated_at) > OLD

    after_row = _server_row(engine, 601)
    assert after_row is not None
    assert after_row["name"] == "after"
    assert after_row["kind"] == "openai"
    assert after_row["base_url"] == OTHER_BASE_URL
    assert after_row["api_key_ref"] == POINTER
    assert after_row["created_at"] == OLD_TEXT
    assert after_row["updated_at"] != OLD_TEXT
    assert _aware(datetime.fromisoformat(after_row["updated_at"])) > OLD
    for column in ("last_test_at", "last_test_ok", "last_test_error"):
        assert after_row[column] == before_row[column]


def test_update_kind_and_base_url_only_leave_name_and_pointer__S006_003_DoD6(engine: Engine) -> None:
    """DoD-6 — fields not supplied are not written, for any combination."""
    _new(engine, 602, name="keep me", kind="llamaswap", base_url=BASE_URL, api_key_ref=POINTER)
    updated = _update(engine, 602, kind="openai", base_url=OTHER_BASE_URL)
    assert (updated.name, updated.kind, updated.base_url, updated.has_api_key) == (
        "keep me",
        "openai",
        OTHER_BASE_URL,
        True,
    )
    row = _server_row(engine, 602)
    assert row is not None
    assert row["name"] == "keep me"
    assert row["api_key_ref"] == POINTER


def test_update_leaves_the_models_rows_alone__S006_003_DoD6(engine: Engine) -> None:
    """DoD-6 — the update touches the registration and nothing else."""
    _new(engine, 603)
    _insert_model(engine, model_id=1301, server_id=603, name="m", enabled=True, designated=True, dim=8)
    before = _model_rows(engine)
    updated = _update(engine, 603, name="renamed")
    assert _model_rows(engine) == before
    assert list(updated.enabled_model_names) == ["m"]
    assert updated.embedding_model_name == "m"
    assert updated.embedding_dim == 8


# ============================================================================ DoD-7


def test_unset_pointer_leaves_the_stored_pointer__S006_003_DoD7(engine: Engine) -> None:
    """DoD-7 — an update that does not supply the pointer leaves it unchanged (D9)."""
    _new(engine, 701, api_key_ref=POINTER)
    updated = _update(engine, 701, name="renamed")
    assert updated.has_api_key is True
    row = _server_row(engine, 701)
    assert row is not None and row["api_key_ref"] == POINTER


def test_explicit_unset_sentinel_leaves_the_stored_pointer__S006_003_DoD7(engine: Engine) -> None:
    """DoD-7 — passing the not-supplied sentinel explicitly is the same as omitting it."""
    _new(engine, 702, api_key_ref=POINTER)
    updated = _update(engine, 702, api_key_ref=UNSET)
    assert updated.has_api_key is True
    row = _server_row(engine, 702)
    assert row is not None and row["api_key_ref"] == POINTER


def test_empty_pointer_clears_the_stored_pointer__S006_003_DoD7(engine: Engine) -> None:
    """DoD-7 — a supplied empty pointer clears it, so the boolean turns false (D9)."""
    _new(engine, 703, api_key_ref=POINTER)
    updated = _update(engine, 703, api_key_ref="")
    assert updated.has_api_key is False
    assert _get(engine, 703).has_api_key is False
    row = _server_row(engine, 703)
    assert row is not None and row["api_key_ref"] is None


def test_new_pointer_replaces_the_stored_pointer__S006_003_DoD7(engine: Engine) -> None:
    """DoD-7 — a supplied non-empty pointer replaces the stored one (D9)."""
    _new(engine, 704, api_key_ref=POINTER)
    updated = _update(engine, 704, api_key_ref="$S006_003_ROTATED")
    assert updated.has_api_key is True
    row = _server_row(engine, 704)
    assert row is not None and row["api_key_ref"] == "$S006_003_ROTATED"


def test_new_pointer_on_a_server_without_one_sets_it__S006_003_DoD7(engine: Engine) -> None:
    """DoD-7 — supplying a pointer where none was stored sets it; the boolean turns true."""
    _new(engine, 705)
    assert _get(engine, 705).has_api_key is False
    updated = _update(engine, 705, api_key_ref=POINTER)
    assert updated.has_api_key is True
    row = _server_row(engine, 705)
    assert row is not None and row["api_key_ref"] == POINTER


def test_three_states_are_distinct_inputs_at_the_service_boundary__S006_003_DoD7() -> None:
    """DoD-7 — the not-supplied state is a default distinct from both ``""`` and ``None``."""
    parameter = inspect.signature(update_server).parameters["api_key_ref"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is UNSET
    assert parameter.default is not None
    assert parameter.default != ""
    for name in ("name", "kind", "base_url"):
        assert inspect.signature(update_server).parameters[name].default is UNSET


# ============================================================================ DoD-8


def _id_addressed_calls(settings: Settings, factory: FakeFactory) -> dict[str, Callable[[Any, int], Any]]:
    return {
        "get_server": lambda c, i: get_server(c, i),
        "update_server": lambda c, i: update_server(c, i, name="x", api_key_ref=""),
        "delete_server": lambda c, i: delete_server(c, i),
        "probe_server": lambda c, i: run(probe_server(c, i, settings, client_factory=factory)),
        "check_server_connection": lambda c, i: run(check_server_connection(c, i, settings, client_factory=factory)),
        "list_available_models": lambda c, i: run(list_available_models(c, i, settings, client_factory=factory)),
    }


@pytest.mark.parametrize(
    "operation",
    [
        "get_server",
        "update_server",
        "delete_server",
        "probe_server",
        "check_server_connection",
        "list_available_models",
    ],
)
def test_unknown_id_raises_llm_server_not_found_and_writes_nothing__S006_003_DoD8(
    engine: Engine, db_settings: Settings, operation: str
) -> None:
    """DoD-8 — every id-addressed operation raises `llm_server_not_found` for an id no row has,
    writes nothing, and builds no client."""
    _new(engine, 801, api_key_ref=POINTER)
    _insert_model(engine, model_id=1401, server_id=801, name="m", enabled=True)
    before = _snapshot(engine)
    factory = FakeFactory(outcome_result(ProbeOutcome.REACHABLE))
    call = _id_addressed_calls(db_settings, factory)[operation]

    with engine.connect() as connection, pytest.raises(LlmServerNotFoundError) as caught:
        call(connection, UNKNOWN_SERVER_ID)

    assert caught.value.code == "llm_server_not_found"
    assert _snapshot(engine) == before
    assert factory.calls == []


# ============================================================================ DoD-9


def test_delete_removes_the_server_and_all_its_models_rows__S006_003_DoD9(engine: Engine) -> None:
    """DoD-9 — the registration and every one of its `models` rows go; other servers' rows stay (D10)."""
    _new(engine, 901)
    _new(engine, 902)
    _insert_model(engine, model_id=1501, server_id=901, name="a-enabled", enabled=True)
    _insert_model(engine, model_id=1502, server_id=901, name="a-disabled", enabled=False)
    _insert_model(engine, model_id=1503, server_id=901, name="a-embed", enabled=True, designated=True, dim=16)
    _insert_model(engine, model_id=1504, server_id=902, name="b-enabled", enabled=True)
    other_server = _server_row(engine, 902)
    other_models = _model_rows(engine, 902)

    assert _delete(engine, 901) is None

    assert _server_row(engine, 901) is None
    assert _model_rows(engine, 901) == []
    assert _server_row(engine, 902) == other_server
    assert _model_rows(engine, 902) == other_models
    assert [server.id for server in _list(engine)] == [902]
    with pytest.raises(LlmServerNotFoundError):
        _get(engine, 901)


def test_delete_of_an_unknown_id_removes_nothing__S006_003_DoD9(engine: Engine) -> None:
    """DoD-9 — an unknown id removes nothing and raises `llm_server_not_found`."""
    _new(engine, 903)
    _insert_model(engine, model_id=1601, server_id=903, name="m", enabled=True)
    before = _snapshot(engine)
    with pytest.raises(LlmServerNotFoundError):
        _delete(engine, UNKNOWN_SERVER_ID)
    assert _snapshot(engine) == before


def test_delete_removes_models_rows_without_relying_on_the_cascade_pragma__S006_003_DoD9(engine: Engine) -> None:
    """DoD-9 — the child delete is explicit: with `foreign_keys` off on the connection, the
    server's `models` rows still go (D10; the behaviour does not depend on a pragma)."""
    _new(engine, 904)
    _new(engine, 905)
    _insert_model(engine, model_id=1701, server_id=904, name="m1", enabled=True)
    _insert_model(engine, model_id=1702, server_id=904, name="m2")
    _insert_model(engine, model_id=1703, server_id=905, name="keep", enabled=True)
    with engine.connect() as connection:
        raw = connection.connection.driver_connection
        assert raw is not None
        raw.execute("PRAGMA foreign_keys=OFF")
        try:
            if raw.execute("PRAGMA foreign_keys").fetchone()[0] != 0:
                pytest.skip("foreign keys could not be switched off on this connection")
            assert not connection.in_transaction()
            delete_server(connection, 904)
        finally:
            if connection.in_transaction():
                connection.rollback()
            raw.execute("PRAGMA foreign_keys=ON")
    assert _server_row(engine, 904) is None
    assert _model_rows(engine, 904) == []
    assert [row["model_name"] for row in _model_rows(engine, 905)] == ["keep"]


def test_delete_is_one_transaction__S006_003_DoD9(engine: Engine) -> None:
    """DoD-9 — if the server row cannot be removed, its `models` rows are not removed either:
    the two deletes commit or roll back together (D10)."""
    _new(engine, 906)
    _insert_model(engine, model_id=1801, server_id=906, name="m1", enabled=True)
    _insert_model(engine, model_id=1802, server_id=906, name="m2", designated=True, dim=4)
    before = _snapshot(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TRIGGER s006_003_block_server_delete BEFORE DELETE ON llm_servers "
                "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
            )
        )
    with pytest.raises(DBAPIError):
        _delete(engine, 906)
    assert _snapshot(engine) == before

    with engine.begin() as connection:
        connection.execute(text("DROP TRIGGER s006_003_block_server_delete"))
    _delete(engine, 906)
    assert _server_row(engine, 906) is None
    assert _model_rows(engine, 906) == []


# ============================================================================ DoD-10


def test_delete_touches_only_the_two_registry_tables__S006_003_DoD10(engine: Engine) -> None:
    """DoD-10 — the delete issues no query against any table but `llm_servers` and `models` (R5)."""
    _new(engine, 1001)
    _insert_model(engine, model_id=1901, server_id=1001, name="m", enabled=True, designated=True, dim=3)
    with StatementRecorder(engine) as recorder:
        _delete(engine, 1001)
    assert recorder.statements
    touched = recorder.tables_touched()
    assert touched <= {"llm_servers", "models"}, touched
    other_tables = set(schema.metadata.tables) - {"llm_servers", "models"}
    for statement in recorder.statements:
        for table_name in other_tables | {"sessions", "characters", "memos"}:
            assert not re.search(rf"\b{re.escape(table_name)}\b", statement, re.IGNORECASE), statement


def test_delete_has_no_way_to_report_a_dependency__S006_003_DoD10(engine: Engine) -> None:
    """DoD-10 — no parameter beyond the connection and id, no return value, and it refuses nothing."""
    signature = inspect.signature(delete_server)
    assert list(signature.parameters) == ["connection", "server_id"]
    assert signature.return_annotation in (None, "None")
    _new(engine, 1002)
    _insert_model(engine, model_id=2001, server_id=1002, name="in-use-maybe", enabled=True, designated=True, dim=5)
    assert _delete(engine, 1002) is None
    assert _server_row(engine, 1002) is None


# ============================================================================ DoD-11


def test_probe_resolves_the_pointer_and_hands_the_credential_to_the_factory__S006_003_DoD11(
    engine: Engine, db_settings: Settings, key_present: None
) -> None:
    """DoD-11 — the stored `$NAME` is resolved through the environment; the factory receives the
    resolved credential, never the pointer text."""
    _new(engine, 1101, base_url=OTHER_BASE_URL, api_key_ref=POINTER)
    factory = FakeFactory(outcome_result(ProbeOutcome.REACHABLE, ["m1", "m2"]))
    result = _probe(engine, 1101, db_settings, factory)
    assert result.outcome is ProbeOutcome.REACHABLE
    assert tuple(result.model_names) == ("m1", "m2")
    assert len(factory.calls) == 1
    base_url, api_key, _timeout = factory.calls[0]
    assert base_url == OTHER_BASE_URL
    assert api_key == RESOLVED_KEY
    assert factory.probe_calls == 1


def test_probe_without_a_pointer_hands_no_credential__S006_003_DoD11(engine: Engine, db_settings: Settings) -> None:
    """DoD-11 — no pointer resolves to no credential."""
    _new(engine, 1102)
    factory = FakeFactory(outcome_result(ProbeOutcome.REACHABLE))
    _probe(engine, 1102, db_settings, factory)
    assert len(factory.calls) == 1
    assert factory.calls[0][1] is None


def test_probe_missing_variable_raises_before_any_client_exists__S006_003_DoD11(
    engine: Engine, db_settings: Settings, key_present: None
) -> None:
    """DoD-11 — an absent variable raises `secret_ref_missing` and the factory is never called."""
    _new(engine, 1103, api_key_ref=MISSING_POINTER)
    before = _snapshot(engine)
    factory = FakeFactory(outcome_result(ProbeOutcome.REACHABLE))
    with pytest.raises(SecretRefError) as caught:
        _probe(engine, 1103, db_settings, factory)
    assert caught.value.code == "secret_ref_missing"
    assert factory.calls == []
    assert _snapshot(engine) == before


def test_probe_resolves_at_call_time__S006_003_DoD11(
    engine: Engine, db_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-11 — resolution happens at probe time: the variable may appear after registration,
    and a changed value is picked up on the next call."""
    monkeypatch.delenv(KEY_VARIABLE, raising=False)
    _new(engine, 1104, api_key_ref=POINTER)
    monkeypatch.setenv(KEY_VARIABLE, "first-value")
    factory = FakeFactory(outcome_result(ProbeOutcome.REACHABLE))
    _probe(engine, 1104, db_settings, factory)
    monkeypatch.setenv(KEY_VARIABLE, "rotated-value")
    _probe(engine, 1104, db_settings, factory)
    assert [call[1] for call in factory.calls] == ["first-value", "rotated-value"]


# ============================================================================ DoD-12


def test_probe_passes_the_configured_timeout_to_the_factory__S006_003_DoD12(
    engine: Engine, db_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-12 — the timeout from the Settings argument reaches the client, and the Settings the
    caller passes win over whatever the process-wide accessor would answer (D13)."""
    _new(engine, 1201)
    handed = db_settings.model_copy(update={"llm_request_timeout_seconds": 7.25})
    monkeypatch.setenv("RPHELPER_LLM_REQUEST_TIMEOUT_SECONDS", "99.0")
    get_settings.cache_clear()
    factory = FakeFactory(outcome_result(ProbeOutcome.REACHABLE))
    _probe(engine, 1201, handed, factory)
    assert len(factory.calls) == 1
    assert factory.calls[0][2] == 7.25


def test_probe_default_timeout_is_the_settings_default__S006_003_DoD12(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-12 — with the default settings, the client is built with 30.0 s."""
    _new(engine, 1202)
    factory = FakeFactory(outcome_result(ProbeOutcome.REACHABLE))
    _probe(engine, 1202, db_settings, factory)
    assert factory.calls[0][2] == 30.0


def test_the_timeout_reaches_the_client_through_every_route__S006_003_DoD12(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-12 — test-connection and list-available-models build their client with the same timeout."""
    _new(engine, 1203)
    handed = db_settings.model_copy(update={"llm_request_timeout_seconds": 4.5})
    factory = FakeFactory(outcome_result(ProbeOutcome.REACHABLE))
    _check(engine, 1203, handed, factory)
    _available(engine, 1203, handed, factory)
    assert [call[2] for call in factory.calls] == [4.5, 4.5]


def test_module_never_fetches_settings_itself__S006_003_DoD12() -> None:
    """DoD-12 — `Settings` arrives as a plain argument; the module never calls `get_settings`."""
    offenders: list[str] = []
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Name) and node.id == "get_settings":
            offenders.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr == "get_settings":
            offenders.append(node.attr)
        elif isinstance(node, ast.ImportFrom):
            offenders.extend(alias.name for alias in node.names if alias.name == "get_settings")
    assert offenders == []
    for function in (probe_server, check_server_connection, list_available_models):
        assert "settings" in inspect.signature(function).parameters


# ============================================================================ DoD-13


def test_test_connection_reachable_records_ok__S006_003_DoD13(
    engine: Engine, db_settings: Settings, key_present: None
) -> None:
    """DoD-13 — a reachable outcome answers reachable and records the time, ok = true and a
    NULL error (US-013.AC-1)."""
    _new(engine, 1301, api_key_ref=POINTER)
    factory = FakeFactory(outcome_result(ProbeOutcome.REACHABLE, ["m1"]))
    before = _now()
    result = _check(engine, 1301, db_settings, factory)
    after = _now()

    assert isinstance(result, ConnectionTestResult)
    assert result.outcome is ProbeOutcome.REACHABLE
    assert result.server.id == 1301
    assert result.server.last_test_ok is True
    assert result.server.last_test_error is None
    assert result.server.last_test_at is not None
    assert before <= _aware(result.server.last_test_at) <= after

    row = _server_row(engine, 1301)
    assert row is not None
    assert row["last_test_ok"] is True
    assert row["last_test_error"] is None
    assert row["last_test_at"] is not None
    assert before <= _aware(datetime.fromisoformat(row["last_test_at"])) <= after
    assert _get(engine, 1301) == result.server


def test_reachable_after_a_failure_clears_the_error__S006_003_DoD13(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-13 — a later reachable test overwrites a previous failure: ok true, error NULL."""
    _new(engine, 1302)
    _check(engine, 1302, db_settings, FakeFactory(outcome_result(ProbeOutcome.AUTH_FAILED)))
    result = _check(engine, 1302, db_settings, FakeFactory(outcome_result(ProbeOutcome.REACHABLE)))
    assert result.server.last_test_ok is True
    assert result.server.last_test_error is None
    row = _server_row(engine, 1302)
    assert row is not None
    assert row["last_test_ok"] is True
    assert row["last_test_error"] is None


# ============================================================================ DoD-14 / DoD-15


@pytest.mark.parametrize("outcome", FAILING_OUTCOMES, ids=[o.value for o in FAILING_OUTCOMES])
def test_failing_outcome_records_the_typed_value__S006_003_DoD14(
    engine: Engine, db_settings: Settings, key_present: None, outcome: ProbeOutcome
) -> None:
    """DoD-14 — ok = false and the error column holds the outcome value itself, never provider
    prose (US-013.AC-2)."""
    _new(engine, 1401, api_key_ref=POINTER)
    factory = FakeFactory(outcome_result(outcome))
    before = _now()
    result = _check(engine, 1401, db_settings, factory)
    after = _now()

    assert result.outcome is outcome
    assert result.server.last_test_ok is False
    assert result.server.last_test_error is outcome
    assert result.server.last_test_at is not None
    assert before <= _aware(result.server.last_test_at) <= after

    row = _server_row(engine, 1401)
    assert row is not None
    assert row["last_test_ok"] is False
    assert row["last_test_error"] == outcome.value
    assert PROVIDER_PROSE not in repr(row)
    assert PROVIDER_PROSE not in repr(result)


@pytest.mark.parametrize("outcome", FAILING_OUTCOMES, ids=[o.value for o in FAILING_OUTCOMES])
def test_failing_outcome_leaves_the_registration_otherwise_unchanged__S006_003_DoD14(
    engine: Engine, db_settings: Settings, key_present: None, outcome: ProbeOutcome
) -> None:
    """DoD-14 — the registration still exists and is unchanged apart from the three last-test
    columns; its `models` rows are untouched (UC-011's postcondition)."""
    _new(engine, 1402, name="keeper", kind="openai", base_url=OTHER_BASE_URL, api_key_ref=POINTER)
    _set_timestamps(engine, 1402)
    _insert_model(engine, model_id=2101, server_id=1402, name="m", enabled=True, designated=True, dim=12)
    before_row = _server_row(engine, 1402)
    before_models = _model_rows(engine)
    assert before_row is not None

    _check(engine, 1402, db_settings, FakeFactory(outcome_result(outcome)))

    after_row = _server_row(engine, 1402)
    assert after_row is not None
    last_test_columns = {"last_test_at", "last_test_ok", "last_test_error"}
    assert {k: v for k, v in after_row.items() if k not in last_test_columns} == {
        k: v for k, v in before_row.items() if k not in last_test_columns
    }
    assert _model_rows(engine) == before_models
    assert [server.id for server in _list(engine)] == [1402]
    server = _get(engine, 1402)
    assert (server.name, server.kind, server.base_url, server.has_api_key) == ("keeper", "openai", OTHER_BASE_URL, True)


def test_model_list_empty_records_ok_false__S006_003_DoD15(engine: Engine, db_settings: Settings) -> None:
    """DoD-15 — `model_list_empty` is a kind of not-reachable: ok = false (D6)."""
    _new(engine, 1501)
    result = _check(engine, 1501, db_settings, FakeFactory(outcome_result(ProbeOutcome.MODEL_LIST_EMPTY)))
    assert result.outcome is ProbeOutcome.MODEL_LIST_EMPTY
    assert result.server.last_test_ok is False
    assert result.server.last_test_error is ProbeOutcome.MODEL_LIST_EMPTY
    row = _server_row(engine, 1501)
    assert row is not None
    assert row["last_test_ok"] is False
    assert row["last_test_error"] == "model_list_empty"


# ============================================================================ DoD-16


def test_test_connection_propagates_secret_ref_missing_and_records_nothing__S006_003_DoD16(
    engine: Engine, db_settings: Settings, key_present: None
) -> None:
    """DoD-16 — `secret_ref_missing` propagates; no timestamp, flag or error value is written (D14)."""
    _new(engine, 1601, api_key_ref=MISSING_POINTER)
    before = _snapshot(engine)
    factory = FakeFactory(outcome_result(ProbeOutcome.REACHABLE))
    with pytest.raises(SecretRefError) as caught:
        _check(engine, 1601, db_settings, factory)
    assert caught.value.code == "secret_ref_missing"
    assert factory.calls == []
    assert _snapshot(engine) == before
    row = _server_row(engine, 1601)
    assert row is not None
    assert row["last_test_at"] is None
    assert row["last_test_ok"] is None
    assert row["last_test_error"] is None


def test_secret_ref_missing_keeps_a_previous_test_result__S006_003_DoD16(
    engine: Engine, db_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-16 — a prior recorded result survives a later `secret_ref_missing` untouched."""
    monkeypatch.setenv(KEY_VARIABLE, RESOLVED_KEY)
    _new(engine, 1602, api_key_ref=POINTER)
    _check(engine, 1602, db_settings, FakeFactory(outcome_result(ProbeOutcome.REACHABLE)))
    before = _server_row(engine, 1602)
    monkeypatch.delenv(KEY_VARIABLE)
    with pytest.raises(SecretRefError):
        _check(engine, 1602, db_settings, FakeFactory(outcome_result(ProbeOutcome.UNREACHABLE)))
    assert _server_row(engine, 1602) == before


# ============================================================================ DoD-17


def test_available_models_returns_names_for_reachable__S006_003_DoD17(
    engine: Engine, db_settings: Settings, key_present: None
) -> None:
    """DoD-17 — a reachable outcome answers the model names (UC-012)."""
    _new(engine, 1701, api_key_ref=POINTER)
    factory = FakeFactory(outcome_result(ProbeOutcome.REACHABLE, ["zeta", "alpha", "mid"]))
    names = _available(engine, 1701, db_settings, factory)
    assert list(names) == ["zeta", "alpha", "mid"]
    assert factory.calls[0][1] == RESOLVED_KEY


def test_available_models_returns_empty_for_model_list_empty__S006_003_DoD17(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-17 — `model_list_empty` answers an empty list, not an error."""
    _new(engine, 1702)
    assert list(_available(engine, 1702, db_settings, FakeFactory(outcome_result(ProbeOutcome.MODEL_LIST_EMPTY)))) == []


@pytest.mark.parametrize(
    "outcome", [ProbeOutcome.UNREACHABLE, ProbeOutcome.AUTH_FAILED], ids=["unreachable", "auth_failed"]
)
def test_available_models_raises_llm_unreachable_with_the_outcome__S006_003_DoD17(
    engine: Engine, db_settings: Settings, outcome: ProbeOutcome
) -> None:
    """DoD-17 — unreachable / auth_failed raise `llm_unreachable` whose detail carries the typed
    outcome and nothing else (D6, D7)."""
    _new(engine, 1703)
    with pytest.raises(LlmUnreachableError) as caught:
        _available(engine, 1703, db_settings, FakeFactory(outcome_result(outcome)))
    assert caught.value.code == "llm_unreachable"
    assert caught.value.detail == {"reason": outcome.value}
    assert PROVIDER_PROSE not in repr(caught.value.to_wire())


def test_available_models_propagates_secret_ref_missing__S006_003_DoD17(
    engine: Engine, db_settings: Settings, key_present: None
) -> None:
    """DoD-17 — the same primitive: a missing variable raises before any client is built."""
    _new(engine, 1704, api_key_ref=MISSING_POINTER)
    factory = FakeFactory(outcome_result(ProbeOutcome.REACHABLE))
    with pytest.raises(SecretRefError):
        _available(engine, 1704, db_settings, factory)
    assert factory.calls == []


# ============================================================================ DoD-18


@pytest.mark.parametrize("outcome", list(ProbeOutcome), ids=[o.value for o in ProbeOutcome])
def test_available_models_writes_nothing__S006_003_DoD18(
    engine: Engine, db_settings: Settings, outcome: ProbeOutcome
) -> None:
    """DoD-18 — a server whose last test succeeded still reports that test after a model listing
    of any outcome."""
    _new(engine, 1801)
    _insert_model(engine, model_id=2201, server_id=1801, name="m", enabled=True)
    tested = _check(engine, 1801, db_settings, FakeFactory(outcome_result(ProbeOutcome.REACHABLE)))
    assert tested.server.last_test_ok is True
    before = _snapshot(engine)

    factory = FakeFactory(outcome_result(outcome))
    if outcome in (ProbeOutcome.UNREACHABLE, ProbeOutcome.AUTH_FAILED):
        with pytest.raises(LlmUnreachableError):
            _available(engine, 1801, db_settings, factory)
    else:
        _available(engine, 1801, db_settings, factory)

    assert _snapshot(engine) == before
    server = _get(engine, 1801)
    assert server.last_test_ok is True
    assert server.last_test_error is None
    assert server.last_test_at == tested.server.last_test_at


def test_available_models_on_a_never_tested_server_leaves_it_untested__S006_003_DoD18(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-18 — opening a modal never manufactures a test result."""
    _new(engine, 1802)
    _available(engine, 1802, db_settings, FakeFactory(outcome_result(ProbeOutcome.REACHABLE)))
    server = _get(engine, 1802)
    assert (server.last_test_at, server.last_test_ok, server.last_test_error) == (None, None, None)


def test_probe_primitive_writes_nothing__S006_003_DoD18(engine: Engine, db_settings: Settings) -> None:
    """DoD-18 — the primitive itself records nothing on the row, for any outcome."""
    _new(engine, 1803)
    before = _snapshot(engine)
    for outcome in ProbeOutcome:
        result = _probe(engine, 1803, db_settings, FakeFactory(outcome_result(outcome)))
        assert result.outcome is outcome
    assert _snapshot(engine) == before


# ============================================================================ DoD-19


def test_one_factory_serves_both_routes__S006_003_DoD19(engine: Engine, db_settings: Settings) -> None:
    """DoD-19 — a single injected factory serves test-connection and list-available-models,
    each building one client and probing it once."""
    _new(engine, 1901, base_url=OTHER_BASE_URL)
    factory = FakeFactory(outcome_result(ProbeOutcome.REACHABLE, ["m"]))
    _check(engine, 1901, db_settings, factory)
    _available(engine, 1901, db_settings, factory)
    assert len(factory.calls) == 2
    assert factory.calls[0] == factory.calls[1]
    assert [client.probe_calls for client in factory.clients] == [1, 1]


def test_both_operations_go_through_the_probe_primitive__S006_003_DoD19(
    engine: Engine, db_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-19 — test-connection and list-available-models each call the one probe primitive."""
    _new(engine, 1902)
    original = registry_module.probe_server
    seen: list[int] = []

    async def spy(connection: Any, server_id: int, settings: Settings, **kwargs: Any) -> ProbeResult:
        seen.append(server_id)
        return await original(connection, server_id, settings, **kwargs)

    monkeypatch.setattr(registry_module, "probe_server", spy)
    factory = FakeFactory(outcome_result(ProbeOutcome.REACHABLE, ["m"]))
    _check(engine, 1902, db_settings, factory)
    _available(engine, 1902, db_settings, factory)
    assert seen == [1902, 1902]


def test_module_has_one_probe_call_site_and_no_direct_client__S006_003_DoD19() -> None:
    """DoD-19 — exactly one place in the module asks a client to probe; the real client is only
    ever a default factory, never constructed directly; no HTTP library is imported."""
    tree = _module_tree()
    probe_calls = 0
    direct_constructions = 0
    http_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "probe":
                probe_calls += 1
            if isinstance(node.func, ast.Name) and node.func.id == "LlmClient":
                direct_constructions += 1
        elif isinstance(node, ast.Import):
            http_imports.extend(a.name for a in node.names if a.name.split(".")[0] in {"httpx", "requests", "urllib"})
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module.split(".")[0] in {"httpx", "requests", "urllib", "aiohttp"}:
                http_imports.append(node.module)
    assert probe_calls == 1
    assert direct_constructions == 0
    assert http_imports == []


# ============================================================================ DoD-20


def test_module_never_branches_on_kind__S006_003_DoD20() -> None:
    """DoD-20 — no equality/membership comparison or match on `kind`, and no provider-kind
    literal anywhere in the module's code, so no dispatch table keyed on a kind either (D5)."""
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


def test_both_kinds_probe_identically__S006_003_DoD20(engine: Engine, db_settings: Settings) -> None:
    """DoD-20 — two registrations differing only in kind build identical clients and record
    identical results."""
    _new(engine, 2001, kind="llamaswap")
    _new(engine, 2002, kind="openai")
    factory = FakeFactory(outcome_result(ProbeOutcome.AUTH_FAILED))
    first = _check(engine, 2001, db_settings, factory)
    second = _check(engine, 2002, db_settings, factory)
    assert factory.calls[0] == factory.calls[1]
    assert first.outcome is second.outcome is ProbeOutcome.AUTH_FAILED
    assert (first.server.last_test_ok, first.server.last_test_error) == (
        second.server.last_test_ok,
        second.server.last_test_error,
    )


# ============================================================================ DoD-21


def _imported_modules() -> list[str]:
    imported: list[str] = []
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
    return imported


def test_module_imports_no_fastapi__S006_003_DoD21() -> None:
    """DoD-21 — no `fastapi` (or `starlette`) import, and no request-layer dependency module."""
    offenders = [name for name in _imported_modules() if name.split(".")[0] in {"fastapi", "starlette"}]
    assert offenders == []
    assert "app.dependencies" not in _imported_modules()
    for name, value in vars(registry_module).items():
        origin = getattr(value, "__module__", None) or ""
        assert not (isinstance(origin, str) and origin.split(".")[0] in {"fastapi", "starlette"}), name


def test_module_names_no_http_status_code__S006_003_DoD21() -> None:
    """DoD-21 — no HTTP status literal and no status-code name in the module."""
    status_words = {"HTTPStatus", "HTTPException", "status_code", "http_status", "Request"}
    offenders: list[Any] = []
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Constant) and type(node.value) is int and node.value in HTTP_STATUS_LITERALS:
            offenders.append(node.value)
        elif isinstance(node, ast.Name) and (node.id in status_words or node.id.startswith("HTTP_")):
            offenders.append(node.id)
        elif isinstance(node, ast.Attribute) and (node.attr in status_words or node.attr.startswith("HTTP_")):
            offenders.append(node.attr)
    assert offenders == []


def test_every_transaction_is_an_explicit_with_begin_block__S006_003_DoD21() -> None:
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


def test_operations_accept_a_fresh_connection_and_leave_none_open__S006_003_DoD21(
    engine: Engine, db_settings: Settings, key_present: None
) -> None:
    """DoD-21 — every operation is handed a connection with no transaction open, can run in
    sequence on that one connection, leaves no transaction open, and its writes are committed."""
    factory = FakeFactory(outcome_result(ProbeOutcome.REACHABLE, ["m"]))
    with engine.connect() as connection:
        assert not connection.in_transaction()
        create_server(connection, SequenceIdGenerator(2101), "one", "llamaswap", BASE_URL, api_key_ref=POINTER)
        assert not connection.in_transaction()
        list_servers(connection)
        assert not connection.in_transaction()
        get_server(connection, 2101)
        assert not connection.in_transaction()
        update_server(connection, 2101, name="renamed")
        assert not connection.in_transaction()
        run(probe_server(connection, 2101, db_settings, client_factory=factory))
        assert not connection.in_transaction()
        run(check_server_connection(connection, 2101, db_settings, client_factory=factory))
        assert not connection.in_transaction()
        run(list_available_models(connection, 2101, db_settings, client_factory=factory))
        assert not connection.in_transaction()

        # the writes so far are committed: another connection sees them
        row = _server_row(engine, 2101)
        assert row is not None
        assert row["name"] == "renamed"
        assert row["last_test_ok"] is True

        delete_server(connection, 2101)
        assert not connection.in_transaction()
    assert _server_row(engine, 2101) is None


def test_service_signatures_take_a_connection_first_and_plain_arguments__S006_003_DoD21() -> None:
    """DoD-21 / interface intent — a Core connection first; no Request, no current-user object."""
    functions = (
        list_servers,
        get_server,
        create_server,
        update_server,
        delete_server,
        probe_server,
        check_server_connection,
        list_available_models,
    )
    for function in functions:
        signature = inspect.signature(function)
        assert list(signature.parameters)[0] == "connection", function.__name__
        rendered = " ".join(str(parameter) for parameter in signature.parameters.values())
        assert "Request" not in rendered
        assert "CurrentUser" not in rendered
        assert "fastapi" not in rendered.lower()
    for function in (probe_server, check_server_connection, list_available_models):
        assert inspect.iscoroutinefunction(function), function.__name__
    for function in (list_servers, get_server, create_server, update_server, delete_server):
        assert not inspect.iscoroutinefunction(function), function.__name__
