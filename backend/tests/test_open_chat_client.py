"""Tests for ``open_chat_client`` in ``app.services.llm_registry`` — feature 021, step 003.

Every expected value comes from ``docs/plans/021.compose-loop-and-tools/003.chat-stream-client.md``
(Interface intent, DoD-9), its ``003.context.md`` and the feature ``context.md`` D14: the helper
re-reads the server's ``api_key_ref``, resolves it with ``resolve_secret`` (a missing variable ->
``secret_ref_missing`` before any client is built) and returns the factory's client for the
server's ``base_url``, the key and the timeout; it writes nothing and leaves no transaction open.

Bindings come from ``status.md`` ``## Skeleton`` -> Step 003:
``open_chat_client(connection, enabled_model, timeout_seconds, client_factory) -> ChatClientLike``
and ``ChatClientFactory = Callable[[str, str | None, float], ChatClientLike]``. The
``EnabledChatModel`` is obtained through the built ``validate_chat_model``.

Fixtures: schema from ``create_all`` on the per-test engine; ``llm_servers`` and ``models`` rows are
raw-inserted; nothing is added to ``conftest.py``. Tests are suffixed ``__S021_003_DoD<n>``.
"""

from typing import Any

import pytest
from sqlalchemy import Engine, Table, select, update

from app.db import schema
from app.errors import SecretRefError
from app.services.llm_registry import EnabledChatModel, ModelRefLevel, open_chat_client, validate_chat_model

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

KEY_VARIABLE = "RPH_TEST_KEY"
KEY_POINTER = "$RPH_TEST_KEY"
KEY_VALUE = "sk-rph-test-resolved-value"
MISSING_VARIABLE = "RPH_MISSING"
MISSING_POINTER = "$RPH_MISSING"

SERVER_KEYED = 5_300
SERVER_BARE = 5_400
SERVER_MISSING = 5_500
BASE_KEYED = "http://chat-keyed.test:8080/v1"
BASE_BARE = "http://chat-bare.test:9090"
BASE_MISSING = "http://chat-missing.test:7070/"
MODEL_NAME = "chat-model"

TIMEOUT = 12.5


# --------------------------------------------------------------------------- helpers


class FakeClient:
    """Stands in for a chat-capable client; identity is what the tests check."""


class FakeFactory:
    """A chat-client factory recording each call's ``(base_url, api_key, timeout)``."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None, float]] = []
        self.made: list[FakeClient] = []

    def __call__(self, base_url: str, api_key: str | None, timeout_seconds: float) -> Any:
        self.calls.append((base_url, api_key, timeout_seconds))
        client = FakeClient()
        self.made.append(client)
        return client


def _servers() -> Table:
    return schema.metadata.tables["llm_servers"]


def _models() -> Table:
    return schema.metadata.tables["models"]


def _insert_server(engine: Engine, *, server_id: int, base_url: str, api_key_ref: str | None) -> None:
    with engine.begin() as connection:
        connection.execute(
            _servers()
            .insert()
            .values(
                id=server_id,
                name=f"server {server_id}",
                kind="llamaswap",
                base_url=base_url,
                api_key_ref=api_key_ref,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_model(engine: Engine, *, model_id: int, server_id: int, name: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            _models()
            .insert()
            .values(
                id=model_id,
                server_id=server_id,
                model_name=name,
                is_enabled=True,
                is_embedding_designated=False,
                embedding_dim=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _set_key_ref(engine: Engine, server_id: int, api_key_ref: str | None) -> None:
    with engine.begin() as connection:
        connection.execute(update(_servers()).where(_servers().c.id == server_id).values(api_key_ref=api_key_ref))


def _enabled(engine: Engine, server_id: int) -> EnabledChatModel:
    with engine.connect() as connection:
        return validate_chat_model(connection, server_id, MODEL_NAME, ModelRefLevel.SESSION)


def _snapshot(engine: Engine) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with engine.connect() as connection:
        servers = [dict(row) for row in connection.execute(select(_servers()).order_by(_servers().c.id)).mappings()]
        models = [dict(row) for row in connection.execute(select(_models()).order_by(_models().c.id)).mappings()]
    return servers, models


@pytest.fixture
def engine(db_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Engine:
    """Three servers (keyed, NULL ref, unset-variable ref), each with one enabled chat model."""
    monkeypatch.setenv(KEY_VARIABLE, KEY_VALUE)
    monkeypatch.delenv(MISSING_VARIABLE, raising=False)
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_server(db_engine, server_id=SERVER_KEYED, base_url=BASE_KEYED, api_key_ref=KEY_POINTER)
    _insert_server(db_engine, server_id=SERVER_BARE, base_url=BASE_BARE, api_key_ref=None)
    _insert_server(db_engine, server_id=SERVER_MISSING, base_url=BASE_MISSING, api_key_ref=MISSING_POINTER)
    _insert_model(db_engine, model_id=63_001, server_id=SERVER_KEYED, name=MODEL_NAME)
    _insert_model(db_engine, model_id=64_001, server_id=SERVER_BARE, name=MODEL_NAME)
    _insert_model(db_engine, model_id=65_001, server_id=SERVER_MISSING, name=MODEL_NAME)
    return db_engine


# --------------------------------------------------------------------------- DoD-9


def test_a_pointer_ref_is_resolved_and_the_factory_called_once__S021_003_DoD9(engine: Engine) -> None:
    """DoD-9 (D14): ``$RPH_TEST_KEY`` set -> factory called once with (base_url, value, timeout); result returned."""
    enabled = _enabled(engine, SERVER_KEYED)
    factory = FakeFactory()
    with engine.connect() as connection:
        result = open_chat_client(connection, enabled, TIMEOUT, factory)
        assert not connection.in_transaction()
    assert factory.calls == [(BASE_KEYED, KEY_VALUE, TIMEOUT)]
    assert result is factory.made[0]


def test_a_null_ref_gives_a_none_key__S021_003_DoD9(engine: Engine) -> None:
    """DoD-9: a NULL ``api_key_ref`` -> the factory gets ``None`` as the key."""
    enabled = _enabled(engine, SERVER_BARE)
    factory = FakeFactory()
    with engine.connect() as connection:
        result = open_chat_client(connection, enabled, TIMEOUT, factory)
        assert not connection.in_transaction()
    assert factory.calls == [(BASE_BARE, None, TIMEOUT)]
    assert result is factory.made[0]


def test_an_unset_variable_raises_secret_ref_missing_and_never_calls_the_factory__S021_003_DoD9(
    engine: Engine,
) -> None:
    """DoD-9: ``$RPH_MISSING`` unset -> ``secret_ref_missing``; the factory is never called."""
    enabled = _enabled(engine, SERVER_MISSING)
    factory = FakeFactory()
    with engine.connect() as connection:
        with pytest.raises(SecretRefError) as caught:
            open_chat_client(connection, enabled, TIMEOUT, factory)
        assert not connection.in_transaction()
    assert caught.value.code == "secret_ref_missing"
    assert factory.calls == []


def test_the_key_ref_is_re_read_at_call_time__S021_003_DoD9(engine: Engine) -> None:
    """DoD-9 (Interface intent: re-reads that server's ``api_key_ref``): a ref changed after the model was
    validated is the one resolved."""
    enabled = _enabled(engine, SERVER_BARE)
    _set_key_ref(engine, SERVER_BARE, KEY_POINTER)
    factory = FakeFactory()
    with engine.connect() as connection:
        open_chat_client(connection, enabled, TIMEOUT, factory)
    assert factory.calls == [(BASE_BARE, KEY_VALUE, TIMEOUT)]


def test_each_server_gets_its_own_key__S021_003_DoD9(engine: Engine) -> None:
    """DoD-9: the ref read is the model's own server's — a keyed and a key-less server never mix."""
    keyed = _enabled(engine, SERVER_KEYED)
    bare = _enabled(engine, SERVER_BARE)
    factory = FakeFactory()
    with engine.connect() as connection:
        open_chat_client(connection, bare, TIMEOUT, factory)
        open_chat_client(connection, keyed, 3.0, factory)
        assert not connection.in_transaction()
    assert factory.calls == [(BASE_BARE, None, TIMEOUT), (BASE_KEYED, KEY_VALUE, 3.0)]


def test_open_chat_client_writes_nothing__S021_003_DoD9(engine: Engine) -> None:
    """DoD-9 (Interface intent: writes nothing): registry rows are identical before and after, on every path."""
    before = _snapshot(engine)
    factory = FakeFactory()
    with engine.connect() as connection:
        open_chat_client(connection, _enabled(engine, SERVER_KEYED), TIMEOUT, factory)
        open_chat_client(connection, _enabled(engine, SERVER_BARE), TIMEOUT, factory)
        with pytest.raises(SecretRefError):
            open_chat_client(connection, _enabled(engine, SERVER_MISSING), TIMEOUT, factory)
        assert not connection.in_transaction()
    assert _snapshot(engine) == before
