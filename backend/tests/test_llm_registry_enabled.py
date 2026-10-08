"""Tests for the enabled-model reads in ``app.services.llm_registry`` — feature 017, step 002.

Every expected value comes from ``docs/plans/017.session-configuration/002.registry-reads-and-capture.md``
(Interface intent, DoD-1 .. DoD-3), its ``002.context.md`` and the feature ``context.md``:
**D7** (the enabled set is exactly what ``validate_chat_model`` accepts — ``is_enabled`` rows whose
server exists, an enabled embedding-designated model included — ordered by ``llm_servers.id`` then
``models.id``, ascending; "first enabled" is the first row) and **D12** (the reads are safe inside a
caller's open ``with connection.begin():`` block and leave no transaction open standalone).

Bindings come from ``status.md`` ``## Skeleton`` -> Step 002:
``list_enabled_chat_models(connection) -> list[EnabledChatModel]``,
``first_enabled_chat_model(connection) -> EnabledChatModel | None`` and the unchanged
``validate_chat_model(connection, server_id, model_name, level) -> EnabledChatModel``.

Fixtures follow the feature's "Registry fixtures" convention: ``llm_servers`` and ``models`` rows are
raw-inserted, with ids chosen so that server-id order and model-id order **disagree** — server A has
the larger server id but the smaller ``models.id``, so the expected first model is server B's.
This file is separate from the existing registry test files and does not edit them; nothing is
added to ``conftest.py``. Tests are suffixed ``__S017_002_DoD<n>``.
"""

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, Table, delete, select, update

from app.db import schema
from app.errors import ModelNotEnabledError
from app.roles import Role
from app.services.llm_registry import (
    EnabledChatModel,
    ModelRefLevel,
    first_enabled_chat_model,
    list_enabled_chat_models,
    validate_chat_model,
)

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

#: Server B has the **smaller** server id; server A the larger one (D7 order: B before A).
SERVER_B = 5_100
SERVER_A = 5_200
#: A server with the smallest id of all, deleted by DoD-1's "deleted server" test.
SERVER_GONE = 5_050

#: Server A's model has a smaller ``models.id`` than every model of server B, so ordering by
#: ``models.id`` alone would put it first — D7 says it comes last.
MODEL_A_CHAT = 61_001
MODEL_A_CHAT_NAME = "alpha-chat"
#: Server B's models. Within B, ``models.id`` order is zeta-embed, then beta-chat (name order is
#: the other way round), and zeta-embed is the enabled embedding-designated model.
MODEL_B_EMBED = 61_900
MODEL_B_EMBED_NAME = "zeta-embed"
MODEL_B_CHAT = 62_001
MODEL_B_CHAT_NAME = "beta-chat"
MODEL_B_DISABLED = 61_500
MODEL_B_DISABLED_NAME = "beta-off"
#: The deleted server's enabled model, with the smallest model id of all.
MODEL_GONE = 60_001
MODEL_GONE_NAME = "gamma-chat"

#: D7's order for the full fixture: server B (by models.id), then server A.
EXPECTED_ORDER: list[tuple[int, str]] = [
    (SERVER_B, MODEL_B_EMBED_NAME),
    (SERVER_B, MODEL_B_CHAT_NAME),
    (SERVER_A, MODEL_A_CHAT_NAME),
]

#: Rows the DoD-3 tests insert inside a caller's transaction to prove it commits.
PROBE_USER_BEFORE = 9_001
PROBE_USER_AFTER = 9_002


# --------------------------------------------------------------------------- helpers


def _servers() -> Table:
    return schema.metadata.tables["llm_servers"]


def _models() -> Table:
    return schema.metadata.tables["models"]


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


def _insert_model(
    engine: Engine,
    *,
    model_id: int,
    server_id: int,
    name: str,
    enabled: bool,
    designated: bool = False,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            _models()
            .insert()
            .values(
                id=model_id,
                server_id=server_id,
                model_name=name,
                is_enabled=enabled,
                is_embedding_designated=designated,
                embedding_dim=384 if designated else None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _set_enabled(engine: Engine, model_id: int, enabled: bool) -> None:
    """A raw enablement flip — the test's own statement, not the service's."""
    with engine.begin() as connection:
        connection.execute(update(_models()).where(_models().c.id == model_id).values(is_enabled=enabled))


def _delete_server(engine: Engine, server_id: int) -> None:
    with engine.begin() as connection:
        connection.execute(delete(_servers()).where(_servers().c.id == server_id))


def _seed_full(engine: Engine) -> None:
    """Two servers whose id order disagrees with their models' id order, plus a disabled model."""
    _insert_server(engine, server_id=SERVER_B, name="server B")
    _insert_server(engine, server_id=SERVER_A, name="server A")
    _insert_model(engine, model_id=MODEL_A_CHAT, server_id=SERVER_A, name=MODEL_A_CHAT_NAME, enabled=True)
    _insert_model(
        engine,
        model_id=MODEL_B_EMBED,
        server_id=SERVER_B,
        name=MODEL_B_EMBED_NAME,
        enabled=True,
        designated=True,
    )
    _insert_model(engine, model_id=MODEL_B_CHAT, server_id=SERVER_B, name=MODEL_B_CHAT_NAME, enabled=True)
    _insert_model(
        engine, model_id=MODEL_B_DISABLED, server_id=SERVER_B, name=MODEL_B_DISABLED_NAME, enabled=False
    )


def _pairs(models: list[EnabledChatModel]) -> list[tuple[int, str]]:
    return [(model.server.id, model.model_name) for model in models]


def _list(engine: Engine) -> list[EnabledChatModel]:
    with engine.connect() as connection:
        return list_enabled_chat_models(connection)


def _first(engine: Engine) -> EnabledChatModel | None:
    with engine.connect() as connection:
        return first_enabled_chat_model(connection)


def _insert_probe_user(connection: Connection, user_id: int) -> None:
    connection.execute(
        schema.users.insert().values(
            id=user_id,
            username=f"probe-{user_id}",
            password_hash="not-a-real-hash",
            role=Role.ROLEPLAYER,
            is_enabled=True,
            rp_language=None,
            preferred_language=None,
            created_at=TIMESTAMP,
            updated_at=TIMESTAMP,
        )
    )


def _persisted_user_ids(engine: Engine) -> set[int]:
    with engine.connect() as connection:
        return set(connection.execute(select(schema.users.c.id)).scalars())


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database with the registry applied and no LLM rows."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    return db_engine


# --------------------------------------------------------------------------- DoD-1


def test_lists_exactly_the_enabled_models_by_server_id_then_model_id__S017_002_DoD1(engine: Engine) -> None:
    """DoD-1 / D7 — server B (smaller server id) before server A even though A's model has the
    smallest ``models.id``; within B, ``models.id`` order; the disabled model is absent."""
    _seed_full(engine)

    result = _list(engine)

    assert all(isinstance(item, EnabledChatModel) for item in result)
    assert _pairs(result) == EXPECTED_ORDER


def test_a_disabled_model_is_absent__S017_002_DoD1(engine: Engine) -> None:
    """DoD-1 — a ``models`` row with ``is_enabled`` false is not in the enabled set."""
    _seed_full(engine)

    names = [model.model_name for model in _list(engine)]

    assert MODEL_B_DISABLED_NAME not in names


def test_a_model_on_a_deleted_server_is_absent__S017_002_DoD1(engine: Engine) -> None:
    """DoD-1 / D7 — the enabled set needs the server to exist; a deleted server's enabled model
    (which would otherwise come first: smallest server id and smallest model id) is not listed."""
    _seed_full(engine)
    _insert_server(engine, server_id=SERVER_GONE, name="server gone")
    _insert_model(engine, model_id=MODEL_GONE, server_id=SERVER_GONE, name=MODEL_GONE_NAME, enabled=True)
    assert _pairs(_list(engine))[0] == (SERVER_GONE, MODEL_GONE_NAME)

    _delete_server(engine, SERVER_GONE)

    result = _pairs(_list(engine))
    assert (SERVER_GONE, MODEL_GONE_NAME) not in result
    assert all(server_id != SERVER_GONE for server_id, _ in result)
    assert result == EXPECTED_ORDER


def test_an_enabled_embedding_designated_model_is_present__S017_002_DoD1(engine: Engine) -> None:
    """DoD-1 / D7 — designation is independent of enablement, so an enabled designated model is in."""
    _seed_full(engine)

    assert (SERVER_B, MODEL_B_EMBED_NAME) in _pairs(_list(engine))


def test_an_enabled_model_on_a_server_with_nothing_else_is_listed__S017_002_DoD1(engine: Engine) -> None:
    """DoD-1 — one server, one enabled model: the list is exactly that model."""
    _insert_server(engine, server_id=SERVER_A, name="server A")
    _insert_model(engine, model_id=MODEL_A_CHAT, server_id=SERVER_A, name=MODEL_A_CHAT_NAME, enabled=True)

    assert _pairs(_list(engine)) == [(SERVER_A, MODEL_A_CHAT_NAME)]


def test_no_llm_rows_lists_an_empty_list__S017_002_DoD1(engine: Engine) -> None:
    """DoD-1 — with no server and no model at all the result is ``[]``."""
    assert _list(engine) == []


def test_only_disabled_models_lists_an_empty_list__S017_002_DoD1(engine: Engine) -> None:
    """DoD-1 — servers exist and models exist, but none is enabled: ``[]``."""
    _seed_full(engine)
    for model_id in (MODEL_A_CHAT, MODEL_B_EMBED, MODEL_B_CHAT):
        _set_enabled(engine, model_id, False)

    assert _list(engine) == []


# --------------------------------------------------------------------------- DoD-2


def test_first_enabled_is_the_first_item_of_the_d7_order__S017_002_DoD2(engine: Engine) -> None:
    """DoD-2 / D7 / US-106.AC-1 — first enabled is server B's lowest-id enabled model, not the
    model with the smallest ``models.id`` overall (server A's)."""
    _seed_full(engine)

    first = _first(engine)

    assert isinstance(first, EnabledChatModel)
    assert (first.server.id, first.model_name) == EXPECTED_ORDER[0]


def test_first_enabled_is_none_when_nothing_is_enabled__S017_002_DoD2(engine: Engine) -> None:
    """DoD-2 — no enabled model (no rows at all) answers none."""
    assert _first(engine) is None


def test_first_enabled_is_none_when_every_model_is_disabled__S017_002_DoD2(engine: Engine) -> None:
    """DoD-2 — rows exist but none is enabled: none."""
    _seed_full(engine)
    for model_id in (MODEL_A_CHAT, MODEL_B_EMBED, MODEL_B_CHAT):
        _set_enabled(engine, model_id, False)

    assert _first(engine) is None


def test_disabling_the_first_makes_the_next_one_first__S017_002_DoD2(engine: Engine) -> None:
    """DoD-2 — disabling the first enabled model promotes the next in D7 order; disabling
    every model of server B promotes server A's model."""
    _seed_full(engine)

    _set_enabled(engine, MODEL_B_EMBED, False)
    first = _first(engine)
    assert first is not None
    assert (first.server.id, first.model_name) == (SERVER_B, MODEL_B_CHAT_NAME)

    _set_enabled(engine, MODEL_B_CHAT, False)
    first = _first(engine)
    assert first is not None
    assert (first.server.id, first.model_name) == (SERVER_A, MODEL_A_CHAT_NAME)


# --------------------------------------------------------------------------- DoD-3


def _call_list(connection: Connection) -> Any:
    result = list_enabled_chat_models(connection)
    assert _pairs(result) == EXPECTED_ORDER
    return result


def _call_first(connection: Connection) -> Any:
    result = first_enabled_chat_model(connection)
    assert result is not None
    assert (result.server.id, result.model_name) == EXPECTED_ORDER[0]
    return result


def _call_validate_enabled(connection: Connection) -> Any:
    result = validate_chat_model(connection, SERVER_B, MODEL_B_CHAT_NAME, ModelRefLevel.SESSION)
    assert (result.server.id, result.model_name) == (SERVER_B, MODEL_B_CHAT_NAME)
    return result


def _call_validate_disabled(connection: Connection) -> Any:
    with pytest.raises(ModelNotEnabledError):
        validate_chat_model(connection, SERVER_B, MODEL_B_DISABLED_NAME, ModelRefLevel.SESSION)
    return None


READS: list[Any] = [
    pytest.param(_call_list, id="list_enabled_chat_models"),
    pytest.param(_call_first, id="first_enabled_chat_model"),
    pytest.param(_call_validate_enabled, id="validate_chat_model-enabled"),
    pytest.param(_call_validate_disabled, id="validate_chat_model-disabled"),
]


@pytest.mark.parametrize("read", READS)
def test_each_read_runs_inside_a_callers_open_transaction_that_then_commits__S017_002_DoD3(
    engine: Engine, read: Callable[[Connection], Any]
) -> None:
    """DoD-3 / D12 — inside ``with connection.begin():`` the read neither commits, rolls back nor
    begins anything: a row written before it and a row written after it both persist when the
    caller's block commits, and no transaction error occurs."""
    _seed_full(engine)

    with engine.connect() as connection:
        with connection.begin() as transaction:
            _insert_probe_user(connection, PROBE_USER_BEFORE)
            read(connection)
            assert connection.in_transaction()
            assert transaction.is_active
            _insert_probe_user(connection, PROBE_USER_AFTER)
        assert not connection.in_transaction()

    persisted = _persisted_user_ids(engine)
    assert PROBE_USER_BEFORE in persisted
    assert PROBE_USER_AFTER in persisted


@pytest.mark.parametrize("read", READS)
def test_each_read_called_standalone_leaves_no_transaction_in_progress__S017_002_DoD3(
    engine: Engine, read: Callable[[Connection], Any]
) -> None:
    """DoD-3 / D12 — called on a connection with no transaction, the read leaves none open."""
    _seed_full(engine)

    with engine.connect() as connection:
        assert not connection.in_transaction()
        read(connection)
        assert not connection.in_transaction()


@pytest.mark.parametrize("read", READS)
def test_a_standalone_read_lets_the_connection_begin_a_write_afterwards__S017_002_DoD3(
    engine: Engine, read: Callable[[Connection], Any]
) -> None:
    """DoD-3 / D12 — a standalone read followed by ``begin()`` on the same connection (the
    "read followed by begin()" shape) raises no transaction error and the write commits."""
    _seed_full(engine)

    with engine.connect() as connection:
        read(connection)
        with connection.begin():
            _insert_probe_user(connection, PROBE_USER_AFTER)

    assert PROBE_USER_AFTER in _persisted_user_ids(engine)
