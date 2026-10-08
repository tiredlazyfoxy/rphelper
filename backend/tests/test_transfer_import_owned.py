"""Tests for `import_owned` — feature 031, step 002 (remap engine + user/character import).

Every expected value comes from the spec — `docs/plans/031.import-and-id-remapping/
002.remap-and-owned-import.md` (Interface intent + Definition of done),
`002.context.md` (§"Registry facts", §"Test guidance"), the feature `context.md`
(§"Remap rules for the three roleplayer granularities", §"The failure contract") — and
from the rows this file seeds itself. Nothing is read from the implementation.

**The only step-002 symbols named here are `import_owned` and `OwnedImportResult`.** The
remap engine, the reference policy and the payload writer are module-private by design
(`002.context.md`: "Do not call the remap engine directly"), so every behaviour below is
observed through `import_owned` and the database it writes. No `_`-prefixed name from
`app.services.transfer_import` is imported or referenced. Step 001 contributes
`ExportInvalidError` and the `REASON_*` constants (**no reason string literal is
re-typed**).

How the old-id → new-id correspondence is recovered, per `002.context.md` §"Test
guidance": the source envelope is built as **user A** with 030's exporters, imported as
another user with a **real** `SnowflakeGenerator`, and the imported rows are paired with
the payload rows **by ascending id per table**. That is sound exactly because DoD-6
guarantees minting preserves order — and DoD-6 itself is therefore asserted
independently, on message *text* sequences and on the two settled groups, never on the
pairing.

Three users are seeded, each with ids above `2**60`: **A** owns everything the envelopes
carry, **B** is the isolation witness (R5, DoD-9), and **C** owns nothing and is the
caller most imports run as, so a second export of C's account is exactly the import.
`conftest.py` is untouched: the file-local `engine` fixture applies the registry with
`schema.metadata.create_all` over the per-test `tmp_path` database `db_engine` provides.
**`memo_fts` / `message_fts` / `memo_vec` / `session_vec` therefore do not exist when a
test starts**, which is DoD-10's premise.

Orchestrator corrections honoured here:

- **decision 13** — `memos.scope` reads back as a plain `str`; `users.role` as a `Role`;
- **decision 14** — `settled_entries` and `current_zone` are Core `select()` objects, not
  SQL views, so DoD-6 executes them directly;
- **harvest E9** — two precisions the plan omits and DoD-10 relies on: `message_fts`
  skips **buried** rows as well as zone rows, and `memo_fts` indexes **every** memo.
"""

import copy
from collections.abc import Callable, Collection, Mapping, Sequence
from typing import Any

import pytest
from sqlalchemy import Column, Connection, Engine, Table, func, select, text

from app.db import schema
from app.db.search_tables import (
    MEMO_FTS_TABLE,
    MEMO_VEC_TABLE,
    MESSAGE_FTS_TABLE,
    SESSION_VEC_TABLE,
    ensure_vector_tables,
)
from app.errors import (
    REASON_MALFORMED_PAYLOAD,
    REASON_WRONG_GRANULARITY,
    ExportInvalidError,
)
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services.transfer import (
    export_character,
    export_database,
    export_session,
    export_user,
)
from app.services.transfer_import import OwnedImportResult, import_owned

# --- seeded constants -----------------------------------------------------------------

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
SETTLED_AT = "2025-12-31T00:00:00.000000+00:00"
ARCHIVED_AT = "2026-02-01T00:00:00.000000+00:00"
LAST_USED_AT = "2026-03-03T03:03:03.000000+00:00"

#: Every seeded id is above `2**60` (`context.md` §"Test conventions").
BASE = 1_152_921_504_606_847_000

USER_A = BASE + 1
USER_B = BASE + 2
USER_C = BASE + 3

SERVER_ID = BASE + 10
MODEL_ID_1 = BASE + 11
MODEL_ID_2 = BASE + 12

CHAR_A1 = BASE + 20
CHAR_A2 = BASE + 21
CHAR_B1 = BASE + 22

SETUP_A1 = BASE + 30
SETUP_A2 = BASE + 31
SETUP_A3 = BASE + 32
SETUP_B1 = BASE + 33

SESSION_A1 = BASE + 40
SESSION_A2 = BASE + 41
SESSION_A3 = BASE + 42
SESSION_B1 = BASE + 43

#: `messages` of `SESSION_A1`: two settled groups then two zone rows. Each buried row has
#: a **lower** id than its own head (030's outcome note), which is why the write path is
#: two-pass — and why this file seeds `related_to` with a second UPDATE as well.
MSG_BURIED_1 = BASE + 50
MSG_HEAD_1 = BASE + 51
MSG_BURIED_2 = BASE + 52
MSG_HEAD_2 = BASE + 53
MSG_ZONE_1 = BASE + 54
MSG_ZONE_2 = BASE + 55
MSG_A2 = BASE + 56
MSG_A3 = BASE + 57
MSG_B1 = BASE + 58

MEMO_USER = BASE + 60
MEMO_CHAR_1 = BASE + 61
MEMO_SETUP_1 = BASE + 62
MEMO_SESSION_1 = BASE + 63
MEMO_CHAR_2 = BASE + 64
MEMO_B1 = BASE + 65

#: The id every DoD-8 dangling reference points at. It belongs to no payload row.
SPARE_ID = BASE + 900

#: An `llm_servers` id no row carries, for DoD-7's "names an unknown server id" case.
UNKNOWN_SERVER_ID = BASE + 901

PASSWORD_HASH = "not-a-real-hash-but-stored-verbatim"

#: Two `(server_id, model_name)` pairs that **do** exist in this instance's `models`, so
#: every seeded pair is kept and DoD-1 can compare `model_name` like any other column.
MODEL_NAME_1 = "seeded-model-one"
MODEL_NAME_2 = "seeded-model-two"

#: A model name no `models` row carries, for DoD-7's "the pair does not exist" case.
MISSING_MODEL_NAME = "no-such-model"

# --- FTS tokens (DoD-10): one unique, tokenizable word per indexed body ---------------

RECORD_TOKEN_1 = "obeliskalpha"
RECORD_TOKEN_2 = "obeliskbeta"
BURIED_TOKEN_1 = "cryptalpha"
BURIED_TOKEN_2 = "cryptbeta"
ZONE_TOKEN_1 = "lanternalpha"
ZONE_TOKEN_2 = "lanternbeta"
ZONE_TOKEN_A2 = "lanterngamma"
ZONE_TOKEN_A3 = "lanterndelta"

MEMO_TOKENS: dict[int, str] = {
    MEMO_USER: "zephyruser",
    MEMO_CHAR_1: "zephyrcharacter",
    MEMO_SETUP_1: "zephyrsetup",
    MEMO_SESSION_1: "zephyrsession",
    MEMO_CHAR_2: "zephyrcharactertwo",
    MEMO_B1: "zephyrwitness",
}

#: `context.md` §"Remap rules" — how a memo scope names the table its `scope_id` points
#: into. Scope `user` resolves to the caller, not to a payload row, so it has no entry.
SCOPE_TABLES: dict[str, str] = {
    "character": schema.characters.name,
    "setup": schema.setups.name,
    "session": schema.sessions.name,
}
SCOPE_USER = "user"

#: The five tables DoD-1 counts and compares. Written as registry names, never literals.
OWNED_TABLES: tuple[str, ...] = (
    schema.characters.name,
    schema.setups.name,
    schema.sessions.name,
    schema.messages.name,
    schema.memos.name,
)


# --- registry helpers (the spec's own rules, kept on the test side) -------------------


def _spec_is_id_column(column: Column[Any], primary_key_names: Collection[str]) -> bool:
    """030's id-column rule as the spec states it: primary key, foreign key, or the name
    `id` / a `_id` suffix (`context.md` §"Deserialization")."""
    name = column.name
    return (
        name in primary_key_names
        or bool(column.foreign_keys)
        or name == "id"
        or name.endswith("_id")
    )


def _primary_key_names(table: Table) -> set[str]:
    return {column.name for column in table.primary_key.columns}


def _value_columns(table: Table) -> list[str]:
    """Every column DoD-1 compares verbatim: the whole table **minus** ids and `user_id`.

    Derived from `schema.metadata`, never hand-listed, so a column added to the registry
    later is compared without this file changing.
    """
    key_names = _primary_key_names(table)
    return [
        column.name
        for column in table.columns
        if not _spec_is_id_column(column, key_names)
    ]


def _reference_columns(table: Table) -> list[Column[Any]]:
    """Every id column but the row's own `id` — each one the remap must rewrite."""
    key_names = _primary_key_names(table)
    return [
        column
        for column in table.columns
        if column.name != "id" and _spec_is_id_column(column, key_names)
    ]


def _fk_target_table(column: Column[Any]) -> str:
    return next(iter(column.foreign_keys)).column.table.name


# --- raw-insert helpers (file-local; `conftest.py` is untouched) ----------------------


def _insert(engine: Engine, table: Table, **values: Any) -> None:
    with engine.begin() as connection:
        connection.execute(table.insert().values(**values))


def _insert_user(engine: Engine, *, user_id: int, username: str, role: Role) -> None:
    _insert(
        engine,
        schema.users,
        id=user_id,
        username=username,
        password_hash=PASSWORD_HASH,
        role=role,
        is_enabled=True,
        rp_language="Russian",
        preferred_language="English",
        last_login_at=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_character(
    engine: Engine,
    *,
    character_id: int,
    user_id: int,
    name: str,
    model_name: str | None = None,
    archived_at: str | None = None,
) -> None:
    # `ck_characters_model_both_or_neither`: the pair is written together or not at all.
    _insert(
        engine,
        schema.characters,
        id=character_id,
        user_id=user_id,
        name=name,
        sheet=f"The sheet of {name}.",
        archived_at=archived_at,
        model_server_id=None if model_name is None else SERVER_ID,
        model_name=model_name,
        system_prompt=None if model_name is None else "Stay in character.",
        tool_memo_search=True,
        tool_session_search=False,
        tool_web_search=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_setup(
    engine: Engine,
    *,
    setup_id: int,
    user_id: int,
    character_id: int,
    name: str,
    archived_at: str | None = None,
) -> None:
    _insert(
        engine,
        schema.setups,
        id=setup_id,
        user_id=user_id,
        character_id=character_id,
        name=name,
        description=f"A description of {name}.",
        archived_at=archived_at,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_session(
    engine: Engine,
    *,
    session_id: int,
    user_id: int,
    character_id: int,
    setup_id: int | None = None,
    model_name: str | None = None,
    archived_at: str | None = None,
) -> None:
    # `ck_sessions_model_both_or_neither`: the pair is written together or not at all.
    _insert(
        engine,
        schema.sessions,
        id=session_id,
        user_id=user_id,
        character_id=character_id,
        setup_id=setup_id,
        last_used_at=LAST_USED_AT,
        archived_at=archived_at,
        model_server_id=None if model_name is None else SERVER_ID,
        model_name=model_name,
        system_prompt=None,
        tool_memo_search=False,
        tool_session_search=None,
        tool_web_search=True,
        rp_language="Russian",
        preferred_language=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_message(
    engine: Engine,
    *,
    message_id: int,
    user_id: int,
    session_id: int,
    token: str,
    role: str = "user",
    kind: str | None = None,
    settled_at: str | None = None,
) -> None:
    # `related_to` is always NULL here; `_bury` sets it afterwards, so a buried row may
    # carry a **lower** id than its own head. `ck_messages_buried_or_settled` holds at
    # both steps.
    _insert(
        engine,
        schema.messages,
        id=message_id,
        user_id=user_id,
        session_id=session_id,
        role=role,
        kind=kind,
        text=f"{token} spoken aloud.",
        related_to=None,
        settled_at=settled_at,
        tool_name=None,
        tool_payload=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _bury(engine: Engine, *, message_id: int, head_id: int) -> None:
    """Point a zone-shaped row at its head, the way settling does."""
    with engine.begin() as connection:
        connection.execute(
            schema.messages.update()
            .where(schema.messages.c.id == message_id)
            .values(related_to=head_id)
        )


def _insert_memo(
    engine: Engine,
    *,
    memo_id: int,
    user_id: int,
    scope: str,
    scope_id: int,
    is_enabled: bool = True,
    is_forced: bool = False,
    sort_key: int = 100,
) -> None:
    _insert(
        engine,
        schema.memos,
        id=memo_id,
        user_id=user_id,
        scope=scope,
        scope_id=scope_id,
        body=f"{MEMO_TOKENS[memo_id]} remembered.",
        is_enabled=is_enabled,
        is_forced=is_forced,
        sort_key=sort_key,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database: three users, one server with two models, and A's whole tree.

    A owns two characters (one archived), three setups (one archived), three sessions
    (one archived, one without a setup), the three message states in two settled groups,
    and a memo at each of the four scopes. B owns a parallel miniature tree, as the
    isolation witness. C owns nothing, so a second export of C's account is exactly what
    an import wrote. Both seeded `(model_server_id, model_name)` pairs exist in `models`.
    No FTS and no vec0 table is created here (DoD-10's premise).
    """
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)

    _insert_user(db_engine, user_id=USER_A, username="alice", role=Role.ROLEPLAYER)
    _insert_user(db_engine, user_id=USER_B, username="bob", role=Role.ROLEPLAYER)
    _insert_user(db_engine, user_id=USER_C, username="carol", role=Role.ROLEPLAYER)

    _insert(
        db_engine,
        schema.llm_servers,
        id=SERVER_ID,
        name="the seeded server",
        kind="llamaswap",
        base_url="http://127.0.0.1:9999",
        api_key_ref=None,
        last_test_at=TIMESTAMP,
        last_test_ok=True,
        last_test_error=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )
    for model_id, model_name in ((MODEL_ID_1, MODEL_NAME_1), (MODEL_ID_2, MODEL_NAME_2)):
        _insert(
            db_engine,
            schema.models,
            id=model_id,
            server_id=SERVER_ID,
            model_name=model_name,
            is_enabled=True,
            is_embedding_designated=False,
            embedding_dim=8,
            created_at=TIMESTAMP,
            updated_at=TIMESTAMP,
        )

    _insert_character(
        db_engine,
        character_id=CHAR_A1,
        user_id=USER_A,
        name="Aria",
        model_name=MODEL_NAME_1,
    )
    _insert_character(
        db_engine,
        character_id=CHAR_A2,
        user_id=USER_A,
        name="Brio",
        model_name=MODEL_NAME_2,
        archived_at=ARCHIVED_AT,
    )
    _insert_character(db_engine, character_id=CHAR_B1, user_id=USER_B, name="Bob's own")

    _insert_setup(
        db_engine, setup_id=SETUP_A1, user_id=USER_A, character_id=CHAR_A1, name="Inn"
    )
    _insert_setup(
        db_engine,
        setup_id=SETUP_A2,
        user_id=USER_A,
        character_id=CHAR_A1,
        name="Road",
        archived_at=ARCHIVED_AT,
    )
    _insert_setup(
        db_engine, setup_id=SETUP_A3, user_id=USER_A, character_id=CHAR_A2, name="Keep"
    )
    _insert_setup(
        db_engine, setup_id=SETUP_B1, user_id=USER_B, character_id=CHAR_B1, name="Bridge"
    )

    _insert_session(
        db_engine,
        session_id=SESSION_A1,
        user_id=USER_A,
        character_id=CHAR_A1,
        setup_id=SETUP_A1,
        model_name=MODEL_NAME_1,
    )
    _insert_session(
        db_engine,
        session_id=SESSION_A2,
        user_id=USER_A,
        character_id=CHAR_A1,
        setup_id=None,
        model_name=MODEL_NAME_2,
        archived_at=ARCHIVED_AT,
    )
    _insert_session(
        db_engine,
        session_id=SESSION_A3,
        user_id=USER_A,
        character_id=CHAR_A2,
        setup_id=SETUP_A3,
    )
    _insert_session(
        db_engine, session_id=SESSION_B1, user_id=USER_B, character_id=CHAR_B1
    )

    for message_id, token, settled_at, role, kind in (
        (MSG_BURIED_1, BURIED_TOKEN_1, None, "user", None),
        (MSG_HEAD_1, RECORD_TOKEN_1, SETTLED_AT, "assistant", "partner"),
        (MSG_BURIED_2, BURIED_TOKEN_2, None, "user", None),
        (MSG_HEAD_2, RECORD_TOKEN_2, SETTLED_AT, "assistant", "partner"),
        (MSG_ZONE_1, ZONE_TOKEN_1, None, "user", None),
        (MSG_ZONE_2, ZONE_TOKEN_2, None, "assistant", "draft"),
    ):
        _insert_message(
            db_engine,
            message_id=message_id,
            user_id=USER_A,
            session_id=SESSION_A1,
            token=token,
            role=role,
            kind=kind,
            settled_at=settled_at,
        )
    _bury(db_engine, message_id=MSG_BURIED_1, head_id=MSG_HEAD_1)
    _bury(db_engine, message_id=MSG_BURIED_2, head_id=MSG_HEAD_2)

    _insert_message(
        db_engine,
        message_id=MSG_A2,
        user_id=USER_A,
        session_id=SESSION_A2,
        token=ZONE_TOKEN_A2,
    )
    _insert_message(
        db_engine,
        message_id=MSG_A3,
        user_id=USER_A,
        session_id=SESSION_A3,
        token=ZONE_TOKEN_A3,
    )
    _insert_message(
        db_engine,
        message_id=MSG_B1,
        user_id=USER_B,
        session_id=SESSION_B1,
        token="bobsownword",
    )

    _insert_memo(db_engine, memo_id=MEMO_USER, user_id=USER_A, scope="user", scope_id=USER_A)
    _insert_memo(
        db_engine,
        memo_id=MEMO_CHAR_1,
        user_id=USER_A,
        scope="character",
        scope_id=CHAR_A1,
        is_forced=True,
        sort_key=200,
    )
    _insert_memo(
        db_engine,
        memo_id=MEMO_SETUP_1,
        user_id=USER_A,
        scope="setup",
        scope_id=SETUP_A1,
        is_enabled=False,
        sort_key=300,
    )
    _insert_memo(
        db_engine,
        memo_id=MEMO_SESSION_1,
        user_id=USER_A,
        scope="session",
        scope_id=SESSION_A1,
        sort_key=400,
    )
    _insert_memo(
        db_engine, memo_id=MEMO_CHAR_2, user_id=USER_A, scope="character", scope_id=CHAR_A2
    )
    _insert_memo(db_engine, memo_id=MEMO_B1, user_id=USER_B, scope="user", scope_id=USER_B)
    return db_engine


# --- envelope helpers (every body starts life as 030's own export) --------------------

Payload = dict[str, list[dict[str, Any]]]


def _user_envelope(engine: Engine, user_id: int = USER_A) -> dict[str, Any]:
    with engine.connect() as connection:
        return copy.deepcopy(dict(export_user(connection, user_id)))


def _character_envelope(engine: Engine, character_id: int = CHAR_A1) -> dict[str, Any]:
    with engine.connect() as connection:
        return copy.deepcopy(dict(export_character(connection, USER_A, character_id)))


def _session_envelope(engine: Engine) -> dict[str, Any]:
    with engine.connect() as connection:
        return copy.deepcopy(dict(export_session(connection, USER_A, SESSION_A1)))


def _database_envelope(engine: Engine) -> dict[str, Any]:
    with engine.connect() as connection:
        return copy.deepcopy(dict(export_database(connection)))


def _payload(envelope: Mapping[str, Any]) -> Payload:
    payload = envelope["payload"]
    assert isinstance(payload, dict)
    return payload


def _rows(envelope: Mapping[str, Any], table_name: str) -> list[dict[str, Any]]:
    """The payload rows of one table, ascending by id — 030 serializes ids as strings."""
    return sorted(_payload(envelope)[table_name], key=lambda row: int(str(row["id"])))


def _row_with_id(envelope: Mapping[str, Any], table_name: str, row_id: int) -> dict[str, Any]:
    matches = [row for row in _payload(envelope)[table_name] if row["id"] == str(row_id)]
    assert len(matches) == 1, f"expected exactly one {table_name} row with id {row_id}"
    return matches[0]


# --- running the import ---------------------------------------------------------------


def _import(
    engine: Engine,
    user_id: int,
    body: Mapping[str, Any],
    generator: SnowflakeGenerator | None = None,
) -> OwnedImportResult:
    """`import_owned(connection, generator, user_id, body)` on a connection that is not
    already in a transaction, so its own `with connection.begin():` commits.

    A **real** `SnowflakeGenerator` (no monkeypatching, `context.md` §"Test conventions").
    """
    with engine.connect() as connection:
        return import_owned(
            connection, generator or SnowflakeGenerator(node_id=0), user_id, body
        )


# --- observation (tests may read the database and the FTS tables directly) ------------


def _table_ids(engine: Engine) -> dict[str, set[int]]:
    """Every id of every `metadata` table, by table name."""
    with engine.connect() as connection:
        return {
            table.name: {
                int(value)
                for value in connection.execute(select(table.c.id)).scalars().all()
            }
            for table in schema.metadata.sorted_tables
        }


def _row_counts(engine: Engine) -> dict[str, int]:
    """The row count of **every** `schema.metadata.sorted_tables` table — DoD-8's
    "stores nothing" measure."""
    with engine.connect() as connection:
        return {
            table.name: int(
                connection.execute(select(func.count()).select_from(table)).scalar_one()
            )
            for table in schema.metadata.sorted_tables
        }


def _stored_rows(engine: Engine, table: Table) -> dict[int, dict[str, Any]]:
    """Every row of `table`, keyed by id, read straight from the database."""
    with engine.connect() as connection:
        rows = connection.execute(select(table)).all()
    return {int(row._mapping["id"]): dict(row._mapping) for row in rows}


def _all_stored_rows(engine: Engine) -> dict[str, dict[int, dict[str, Any]]]:
    return {table.name: _stored_rows(engine, table) for table in schema.metadata.sorted_tables}


def _texts_in_id_order(engine: Engine, session_id: int) -> list[str]:
    with engine.connect() as connection:
        rows = connection.execute(
            select(schema.messages.c.text)
            .where(schema.messages.c.session_id == session_id)
            .order_by(schema.messages.c.id)
        ).all()
    return [str(row[0]) for row in rows]


def _selectable_texts(engine: Engine, selectable: Any, session_id: int) -> set[str]:
    """The `text` values a Core selectable returns for one session (decision 14: these
    are `select()` objects, not SQL views, so a test executes them directly)."""
    with engine.connect() as connection:
        rows = connection.execute(
            selectable.where(schema.messages.c.session_id == session_id)
        ).all()
    return {str(row._mapping["text"]) for row in rows}


def _table_exists(connection: Connection, table_name: str) -> bool:
    row = connection.execute(
        text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name"),
        {"name": table_name},
    ).first()
    return row is not None


def _exists(engine: Engine, table_name: str) -> bool:
    with engine.connect() as connection:
        return _table_exists(connection, table_name)


def _fts_match_ids(engine: Engine, table_name: str, token: str) -> set[int]:
    """The rowids an FTS `MATCH` returns — the `024` convention a test may use."""
    with engine.connect() as connection:
        if not _table_exists(connection, table_name):
            return set()
        rows = connection.execute(
            text(f"SELECT rowid FROM {table_name} WHERE {table_name} MATCH :token"),
            {"token": token},
        ).all()
    return {int(row[0]) for row in rows}


def _vector_row_count(engine: Engine, table_name: str) -> int:
    """The number of rows in a vec0 table; `0` when the table does not exist."""
    with engine.connect() as connection:
        if not _table_exists(connection, table_name):
            return 0
        keys = connection.execute(
            text("SELECT name FROM pragma_table_info(:table_name) WHERE pk = 1"),
            {"table_name": table_name},
        ).all()
        assert keys, f"{table_name} exists but has no key column"
        key = str(keys[0][0])
        return len(connection.execute(text(f"SELECT {key} FROM {table_name}")).all())


# --- the id correspondence (pairing by ascending id, per `002.context.md`) ------------

Correspondence = dict[str, dict[int, int]]


def _pairing(old_rows: Sequence[Mapping[str, Any]], new_ids: Collection[int]) -> dict[int, int]:
    old = sorted(int(str(row["id"])) for row in old_rows)
    new = sorted(new_ids)
    assert len(old) == len(new), f"expected {len(old)} imported rows, found {len(new)}"
    return dict(zip(old, new, strict=True))


def _correspondence_from_diff(
    payload: Payload, before: Mapping[str, set[int]], after: Mapping[str, set[int]]
) -> Correspondence:
    """Old id → new id per table, from the ids the import added.

    Sound because DoD-6 fixes the minting order; DoD-6 is asserted independently.
    """
    return {
        name: _pairing(rows, after[name] - before[name])
        for name, rows in payload.items()
        if name != schema.users.name
    }


def _correspondence_from_payloads(source: Payload, imported: Payload) -> Correspondence:
    return {
        name: _pairing(rows, [int(str(row["id"])) for row in imported[name]])
        for name, rows in source.items()
        if name != schema.users.name
    }


def _assert_reference(
    table: Table,
    column: Column[Any],
    old_row: Mapping[str, Any],
    new_row: Mapping[str, Any],
    correspondence: Correspondence,
    caller_id: int,
) -> None:
    """`context.md` §"Remap rules", one id column at a time. Any id column the registry
    grows that no rule covers fails loudly instead of slipping through."""
    name = column.name
    old = old_row[name]
    new = new_row[name]
    where = f"{table.name}.{name}"
    if name == "user_id":
        assert new == str(caller_id), f"{where}: every user_id becomes the caller"
    elif name == "model_server_id":
        # Kept as stored when the pair exists in `models` (every seeded pair does);
        # DoD-7 covers the nulling case.
        assert new == old, f"{where}: a known model pair is kept as stored"
    elif name == "scope_id":
        scope = str(old_row["scope"])
        if scope == SCOPE_USER:
            assert new == str(caller_id), f"{where}: a user-scope memo points at the caller"
        else:
            assert int(str(new)) == correspondence[SCOPE_TABLES[scope]][int(str(old))], (
                f"{where}: scope {scope} must name the imported row of its own table"
            )
    elif column.foreign_keys:
        target = _fk_target_table(column)
        if old is None:
            assert new is None, f"{where}: a null reference stays null"
        else:
            assert int(str(new)) == correspondence[target][int(str(old))], (
                f"{where}: must name the imported {target} row"
            )
    else:  # pragma: no cover - a guard against an unhandled new id column
        pytest.fail(f"{where} is an id column with no remap rule in the spec")


def _assert_table_matches(
    table_name: str,
    source: Payload,
    imported: Payload,
    correspondence: Correspondence,
    caller_id: int,
) -> None:
    """DoD-1/DoD-3: one table, row by row — the same count, every value column equal, and
    every reference rewritten to the corresponding imported row."""
    table = schema.metadata.tables[table_name]
    old_rows = sorted(source[table_name], key=lambda row: int(str(row["id"])))
    new_rows = sorted(imported[table_name], key=lambda row: int(str(row["id"])))
    assert len(new_rows) == len(old_rows), f"{table_name}: the row count must be the same"
    for old_row, new_row in zip(old_rows, new_rows, strict=True):
        assert int(str(new_row["id"])) == correspondence[table_name][int(str(old_row["id"]))]
        for name in _value_columns(table):
            assert new_row[name] == old_row[name], f"{table_name}.{name} must be preserved"
        for column in _reference_columns(table):
            _assert_reference(table, column, old_row, new_row, correspondence, caller_id)


def _assert_refusal(reason: str, call: Callable[[], object]) -> None:
    """A refusal is anchored on the **specific** error and its exact `detail`, so the
    skeleton's `NotImplementedError` cannot satisfy it."""
    with pytest.raises(ExportInvalidError) as caught:
        call()
    assert caught.value.reason == reason
    assert caught.value.detail == {"reason": reason}


# --- DoD-1: the user round trip ------------------------------------------------------


def test_user_import_round_trips_every_column__S031_002_DoD1(engine: Engine) -> None:
    """DoD-1 — A's own `user` export, imported as C, makes C rows whose second export
    compares equal to the first in **every** column but ids and `user_id`: the same count
    of characters, setups, sessions, messages and memos, and the same names, sheets,
    descriptions, texts, bodies, flags, `sort_key`s, `archived_at`, `created_at`,
    `updated_at`, `last_used_at` and `settled_at`. (US-079.AC-2, UC-062)

    The compared column list is derived from `schema.metadata`, so a column added later is
    compared without this file changing.
    """
    source = _user_envelope(engine)
    source_payload = _payload(source)
    assert _rows(source, schema.characters.name), "the source export must carry rows"

    result = _import(engine, USER_C, source)

    imported_payload = _payload(_user_envelope(engine, USER_C))
    assert set(imported_payload) == set(source_payload), (
        "a user export of the importing account carries the same tables"
    )

    correspondence = _correspondence_from_payloads(source_payload, imported_payload)
    for table_name in OWNED_TABLES:
        _assert_table_matches(
            table_name, source_payload, imported_payload, correspondence, USER_C
        )

    assert result.granularity == "user"
    assert result.character_ids == sorted(correspondence[schema.characters.name].values())


def test_user_import_points_each_memo_scope_at_the_imported_row__S031_002_DoD1(
    engine: Engine,
) -> None:
    """DoD-1, last bullet — each memo scope points at the corresponding imported row: the
    three in-payload scopes at the new row of their own table, and `scope='user'` at the
    caller (`context.md` §"Remap rules")."""
    source = _user_envelope(engine)
    source_payload = _payload(source)
    scopes = {str(row["scope"]) for row in source_payload[schema.memos.name]}
    assert scopes == {SCOPE_USER, *SCOPE_TABLES}, "all four scopes must be exercised"

    _import(engine, USER_C, source)

    imported_payload = _payload(_user_envelope(engine, USER_C))
    correspondence = _correspondence_from_payloads(source_payload, imported_payload)
    old_memos = _rows(source, schema.memos.name)
    new_memos = sorted(
        imported_payload[schema.memos.name], key=lambda row: int(str(row["id"]))
    )
    for old_row, new_row in zip(old_memos, new_memos, strict=True):
        scope = str(old_row["scope"])
        assert new_row["scope"] == old_row["scope"]
        if scope == SCOPE_USER:
            assert new_row["scope_id"] == str(USER_C)
        else:
            expected = correspondence[SCOPE_TABLES[scope]][int(str(old_row["scope_id"]))]
            assert int(str(new_row["scope_id"])) == expected


# --- DoD-2: the caller's own account row ---------------------------------------------


def test_user_import_never_touches_the_callers_account_row__S031_002_DoD2(
    engine: Engine,
) -> None:
    """DoD-2 — after a `user` import the caller's `users` row is unchanged in **every**
    column, including `username`, `rp_language` and `preferred_language`, even though the
    payload's `users` row carries different values; and no new `users` row exists.
    (US-136.AC-1)
    """
    envelope = _user_envelope(engine)
    users_row = _row_with_id(envelope, schema.users.name, USER_A)
    users_row["username"] = "alice-renamed"
    users_row["rp_language"] = "Klingon"
    users_row["preferred_language"] = "Esperanto"

    before = _stored_rows(engine, schema.users)
    assert before[USER_C]["username"] == "carol", "the caller's row must exist first"

    _import(engine, USER_C, envelope)

    after = _stored_rows(engine, schema.users)
    assert set(after) == set(before), "no new users row may exist"
    assert after[USER_C] == before[USER_C], "the caller's row is unchanged in every column"
    assert "alice-renamed" not in {str(row["username"]) for row in after.values()}


# --- DoD-3: the character import -----------------------------------------------------


def test_character_import_creates_one_character_and_its_tree__S031_002_DoD3(
    engine: Engine,
) -> None:
    """DoD-3 — a `character` export creates exactly one new character owned by the caller,
    with its setups, its sessions (archived ones included, R6), their messages and its
    character-, setup- and session-scoped memos; each memo's `scope_id` names the new row
    of the right table; and `character_ids` is that one new id. (US-080.AC-2, UC-063)
    """
    source = _character_envelope(engine)
    source_payload = _payload(source)
    assert set(source_payload) == set(OWNED_TABLES), "a character payload carries no users"
    archived = [
        row for row in source_payload[schema.sessions.name] if row["archived_at"] is not None
    ]
    assert archived, "R6: the source must carry an archived session"
    memo_scopes = {str(row["scope"]) for row in source_payload[schema.memos.name]}
    assert memo_scopes == set(SCOPE_TABLES), "the three in-payload scopes must be exercised"

    result = _import(engine, USER_C, source)

    imported_payload = _payload(_user_envelope(engine, USER_C))
    new_characters = imported_payload[schema.characters.name]
    assert len(new_characters) == 1
    new_character_id = int(str(new_characters[0]["id"]))
    assert result.granularity == "character"
    assert result.character_ids == [new_character_id]

    stored = _stored_rows(engine, schema.characters)[new_character_id]
    assert int(stored["user_id"]) == USER_C, "the new character is owned by the caller"

    correspondence = _correspondence_from_payloads(source_payload, imported_payload)
    for table_name in OWNED_TABLES:
        _assert_table_matches(
            table_name, source_payload, imported_payload, correspondence, USER_C
        )


# --- DoD-4: fresh ids, originals untouched -------------------------------------------


def test_imported_ids_are_new_everywhere__S031_002_DoD4(engine: Engine) -> None:
    """DoD-4, first half — every imported row has an id that differs from every id in the
    database before the import and from every id in the payload. (US-136.AC-1)"""
    source = _user_envelope(engine)
    source_payload = _payload(source)
    payload_ids = {
        int(str(row["id"])) for rows in source_payload.values() for row in rows
    }
    before = _table_ids(engine)
    before_ids = {row_id for ids in before.values() for row_id in ids}

    _import(engine, USER_C, source)

    after = _table_ids(engine)
    correspondence = _correspondence_from_diff(source_payload, before, after)
    new_ids = {
        new_id for mapping in correspondence.values() for new_id in mapping.values()
    }
    assert new_ids, "the import must have written rows"
    assert not (new_ids & before_ids), "no imported id existed in the database before"
    assert not (new_ids & payload_ids), "no imported id is an id the payload carried"
    for table in schema.metadata.sorted_tables:
        if table.name not in source_payload:
            assert after[table.name] == before[table.name], (
                f"{table.name} is outside the payload and must gain no row"
            )


def test_reimport_leaves_the_originals_byte_for_byte__S031_002_DoD4(engine: Engine) -> None:
    """DoD-4, second half — importing the same export into the same account, whose
    originals still exist, leaves those originals byte-for-byte unchanged. (US-136.AC-2)"""
    source = _user_envelope(engine)
    source_payload = _payload(source)
    before_rows = _all_stored_rows(engine)
    before = {name: set(rows) for name, rows in before_rows.items()}
    assert before_rows[schema.characters.name], "the originals must exist first"

    _import(engine, USER_A, source)

    after_rows = _all_stored_rows(engine)
    for name, rows in before_rows.items():
        for row_id, row in rows.items():
            assert after_rows[name][row_id] == row, (
                f"{name} row {row_id} existed before the import and must be unchanged"
            )
    after = {name: set(rows) for name, rows in after_rows.items()}
    correspondence = _correspondence_from_diff(source_payload, before, after)
    new_ids = {
        new_id for mapping in correspondence.values() for new_id in mapping.values()
    }
    assert new_ids, "the second copy must have been written"


# --- DoD-5: importing the same export twice ------------------------------------------


def test_importing_one_character_twice_yields_disjoint_rows__S031_002_DoD5(
    engine: Engine,
) -> None:
    """DoD-5 — importing the same `character` export twice yields two characters with
    disjoint id sets across **every** table, and nothing warns or fails. A service has no
    warning channel (`OwnedImportResult` carries only the granularity and the ids), so
    "nothing warns or fails" is witnessed by both calls returning normally with two
    complete, independent copies. (US-136.AC-2, brief Out)
    """
    source = _character_envelope(engine)
    source_payload = _payload(source)
    # One shared generator across both calls: two generators on the same node id could
    # mint the same id inside one millisecond, which would be a harness artefact.
    generator = SnowflakeGenerator(node_id=0)

    before = _table_ids(engine)
    first = _import(engine, USER_C, source, generator)
    middle = _table_ids(engine)
    second = _import(engine, USER_C, source, generator)
    after = _table_ids(engine)

    first_map = _correspondence_from_diff(source_payload, before, middle)
    second_map = _correspondence_from_diff(source_payload, middle, after)
    for table_name in OWNED_TABLES:
        first_ids = set(first_map[table_name].values())
        second_ids = set(second_map[table_name].values())
        assert first_ids and second_ids, f"{table_name}: both copies must hold rows"
        assert not (first_ids & second_ids), f"{table_name}: the two copies must be disjoint"

    assert len(first.character_ids) == 1
    assert len(second.character_ids) == 1
    assert first.character_ids != second.character_ids
    characters = _stored_rows(engine, schema.characters)
    mine = [row for row in characters.values() if int(row["user_id"]) == USER_C]
    assert len(mine) == 2, "the caller now owns two characters"


# --- DoD-6: order and references -----------------------------------------------------


def test_imported_messages_keep_their_order__S031_002_DoD6(engine: Engine) -> None:
    """DoD-6, first bullet — the imported messages of a session, ordered by new id, are in
    the same order as the originals ordered by old id. Asserted on the message **texts**,
    so it does not restate the id pairing."""
    source = _user_envelope(engine)
    source_payload = _payload(source)
    before = _table_ids(engine)

    _import(engine, USER_C, source)

    correspondence = _correspondence_from_diff(source_payload, before, _table_ids(engine))
    for old_session_id in (SESSION_A1, SESSION_A2, SESSION_A3):
        old_texts = [
            str(row["text"])
            for row in _rows(source, schema.messages.name)
            if row["session_id"] == str(old_session_id)
        ]
        new_session_id = correspondence[schema.sessions.name][old_session_id]
        assert _texts_in_id_order(engine, new_session_id) == old_texts
    longest = [
        str(row["text"])
        for row in _rows(source, schema.messages.name)
        if row["session_id"] == str(SESSION_A1)
    ]
    assert len(longest) >= 4, "the ordering clause needs a session with several messages"


def test_each_buried_row_points_at_its_own_new_head__S031_002_DoD6(engine: Engine) -> None:
    """DoD-6, second bullet — every buried row's `related_to` names the new id of **its
    own** head. Two settled groups are seeded, so naming the other group's head fails."""
    source = _user_envelope(engine)
    source_payload = _payload(source)
    buried = [
        row for row in _rows(source, schema.messages.name) if row["related_to"] is not None
    ]
    assert len(buried) == 2, "two buried rows, in two different groups"
    assert len({str(row["related_to"]) for row in buried}) == 2, "two distinct heads"
    before = _table_ids(engine)

    _import(engine, USER_C, source)

    correspondence = _correspondence_from_diff(source_payload, before, _table_ids(engine))
    message_map = correspondence[schema.messages.name]
    stored = _stored_rows(engine, schema.messages)
    for old_row in buried:
        new_row = stored[message_map[int(str(old_row["id"]))]]
        expected_head = message_map[int(str(old_row["related_to"]))]
        assert int(new_row["related_to"]) == expected_head
        assert new_row["settled_at"] is None, "a buried row has no settled_at (the CHECK)"
        head = stored[expected_head]
        old_head = _row_with_id(source, schema.messages.name, int(str(old_row["related_to"])))
        assert str(head["text"]) == str(old_head["text"]), "it is that row's own head"


def test_record_and_zone_rows_keep_their_states__S031_002_DoD6(engine: Engine) -> None:
    """DoD-6, third bullet — the record rows and the zone rows each appear in
    `settled_entries` / `current_zone` exactly as the originals did. Decision 14: both are
    Core `select()` objects, executed here directly."""
    source = _user_envelope(engine)
    source_payload = _payload(source)
    session_rows = [
        row
        for row in _rows(source, schema.messages.name)
        if row["session_id"] == str(SESSION_A1)
    ]
    old_records = {
        str(row["text"])
        for row in session_rows
        if row["settled_at"] is not None and row["related_to"] is None
    }
    old_zone = {
        str(row["text"])
        for row in session_rows
        if row["settled_at"] is None and row["related_to"] is None
    }
    assert old_records and old_zone, "the originals must hold both record and zone rows"
    before = _table_ids(engine)

    _import(engine, USER_C, source)

    correspondence = _correspondence_from_diff(source_payload, before, _table_ids(engine))
    new_session_id = correspondence[schema.sessions.name][SESSION_A1]
    assert _selectable_texts(engine, schema.settled_entries, new_session_id) == old_records
    assert _selectable_texts(engine, schema.current_zone, new_session_id) == old_zone


# --- DoD-7: the model pair -----------------------------------------------------------


def _assert_model_check_holds(engine: Engine) -> None:
    """`ck_characters_model_both_or_neither` and its sessions counterpart: the two columns
    are null together or set together, never one alone."""
    for table in (schema.characters, schema.sessions):
        for row_id, row in _stored_rows(engine, table).items():
            both_null = row["model_server_id"] is None and row["model_name"] is None
            both_set = row["model_server_id"] is not None and row["model_name"] is not None
            assert both_null or both_set, f"{table.name} row {row_id} breaks both-or-neither"


def test_a_known_model_pair_is_kept__S031_002_DoD7(engine: Engine) -> None:
    """DoD-7, first half — a character and a session carrying a `(model_server_id,
    model_name)` pair that exists in this instance's `models` keep it, and the
    both-or-neither CHECK holds."""
    source = _user_envelope(engine)
    source_payload = _payload(source)
    old_character = _row_with_id(source, schema.characters.name, CHAR_A1)
    old_session = _row_with_id(source, schema.sessions.name, SESSION_A1)
    assert old_character["model_name"] == MODEL_NAME_1
    assert old_session["model_name"] == MODEL_NAME_1
    before = _table_ids(engine)

    _import(engine, USER_C, source)

    correspondence = _correspondence_from_diff(source_payload, before, _table_ids(engine))
    character = _stored_rows(engine, schema.characters)[
        correspondence[schema.characters.name][CHAR_A1]
    ]
    session = _stored_rows(engine, schema.sessions)[
        correspondence[schema.sessions.name][SESSION_A1]
    ]
    assert int(character["model_server_id"]) == SERVER_ID
    assert str(character["model_name"]) == MODEL_NAME_1
    assert int(session["model_server_id"]) == SERVER_ID
    assert str(session["model_name"]) == MODEL_NAME_1
    _assert_model_check_holds(engine)


def test_an_unknown_model_pair_is_nulled_on_both_columns__S031_002_DoD7(
    engine: Engine,
) -> None:
    """DoD-7, second half — when the pair does not exist in `models` (a model name no row
    carries) or names an unknown server id, **both** columns are null after the import,
    while a pair that does exist is untouched. The CHECK holds in every case."""
    source = _user_envelope(engine)
    # The character's pair no longer exists in `models`; the session's names a server id
    # no `llm_servers` row carries. `model_server_id` has no FK, so neither is refused.
    _row_with_id(source, schema.characters.name, CHAR_A1)["model_name"] = MISSING_MODEL_NAME
    _row_with_id(source, schema.sessions.name, SESSION_A1)["model_server_id"] = str(
        UNKNOWN_SERVER_ID
    )
    source_payload = _payload(source)
    before = _table_ids(engine)

    _import(engine, USER_C, source)

    correspondence = _correspondence_from_diff(source_payload, before, _table_ids(engine))
    characters = _stored_rows(engine, schema.characters)
    sessions = _stored_rows(engine, schema.sessions)
    nulled_character = characters[correspondence[schema.characters.name][CHAR_A1]]
    nulled_session = sessions[correspondence[schema.sessions.name][SESSION_A1]]
    assert nulled_character["model_server_id"] is None
    assert nulled_character["model_name"] is None
    assert nulled_session["model_server_id"] is None
    assert nulled_session["model_name"] is None

    kept_character = characters[correspondence[schema.characters.name][CHAR_A2]]
    kept_session = sessions[correspondence[schema.sessions.name][SESSION_A2]]
    assert int(kept_character["model_server_id"]) == SERVER_ID
    assert str(kept_character["model_name"]) == MODEL_NAME_2
    assert int(kept_session["model_server_id"]) == SERVER_ID
    assert str(kept_session["model_name"]) == MODEL_NAME_2
    _assert_model_check_holds(engine)


# --- DoD-8: the six refusals ---------------------------------------------------------


def _dangle_setup_character(envelope: dict[str, Any]) -> None:
    """A `setups` row whose `character_id` is not in the payload."""
    _row_with_id(envelope, schema.setups.name, SETUP_A1)["character_id"] = str(SPARE_ID)


def _dangle_session_setup(envelope: dict[str, Any]) -> None:
    """A `sessions` row whose `setup_id` names no payload setup."""
    _row_with_id(envelope, schema.sessions.name, SESSION_A1)["setup_id"] = str(SPARE_ID)


def _dangle_buried_head(envelope: dict[str, Any]) -> None:
    """A buried message whose `related_to` names no payload message."""
    _row_with_id(envelope, schema.messages.name, MSG_BURIED_1)["related_to"] = str(SPARE_ID)


def _user_scope_at_character_granularity(envelope: dict[str, Any]) -> None:
    """A character-granularity memo with scope `user` — a scope that granularity forbids."""
    _row_with_id(envelope, schema.memos.name, MEMO_CHAR_1)["scope"] = SCOPE_USER


def _dangle_memo_setup_scope(envelope: dict[str, Any]) -> None:
    """A memo whose `scope='setup'` `scope_id` names no payload setup."""
    _row_with_id(envelope, schema.memos.name, MEMO_SETUP_1)["scope_id"] = str(SPARE_ID)


def _foreign_user_id_on_a_character(envelope: dict[str, Any]) -> None:
    """A `user` payload whose `characters` row carries a `user_id` other than the payload
    user's id."""
    _row_with_id(envelope, schema.characters.name, CHAR_A1)["user_id"] = str(USER_B)


@pytest.mark.parametrize(
    ("granularity", "mutate"),
    [
        ("character", _dangle_setup_character),
        ("character", _dangle_session_setup),
        ("character", _dangle_buried_head),
        ("character", _user_scope_at_character_granularity),
        ("character", _dangle_memo_setup_scope),
        ("user", _foreign_user_id_on_a_character),
    ],
    ids=[
        "setup_character_id_not_in_payload",
        "session_setup_id_names_no_setup",
        "buried_related_to_names_no_message",
        "user_scope_at_character_granularity",
        "memo_setup_scope_names_no_setup",
        "character_user_id_is_not_the_payload_user",
    ],
)
def test_a_broken_payload_is_refused_and_stores_nothing__S031_002_DoD8(
    engine: Engine, granularity: str, mutate: Callable[[dict[str, Any]], None]
) -> None:
    """DoD-8 — each of the six cases gives `malformed_payload` and stores nothing: the row
    counts of **every** `metadata` table are unchanged. Anchored on the specific error and
    its exact `detail`, so neither a bare exception nor a count check alone would pass.
    """
    envelope = (
        _user_envelope(engine) if granularity == "user" else _character_envelope(engine)
    )
    mutate(envelope)
    before = _row_counts(engine)
    assert before[schema.characters.name] > 0, "the database holds rows to be left alone"

    _assert_refusal(REASON_MALFORMED_PAYLOAD, lambda: _import(engine, USER_C, envelope))

    assert _row_counts(engine) == before, "a refusal stores nothing"


# --- DoD-9: R5, the caller's user_id and nobody else's -------------------------------


def test_every_written_row_carries_the_caller__S031_002_DoD9(engine: Engine) -> None:
    """DoD-9 — every row the import writes carries the **caller's** `user_id`, whatever
    `user_id` the payload carried. The payload's rows are A's, and the caller is C. (R5)"""
    source = _user_envelope(engine)
    source_payload = _payload(source)
    carried = {
        str(row["user_id"])
        for name, rows in source_payload.items()
        if name != schema.users.name
        for row in rows
    }
    assert carried == {str(USER_A)}, "the payload carries a different user's id"
    before = _table_ids(engine)

    _import(engine, USER_C, source)

    correspondence = _correspondence_from_diff(source_payload, before, _table_ids(engine))
    for table_name, mapping in correspondence.items():
        stored = _stored_rows(engine, schema.metadata.tables[table_name])
        assert mapping, f"{table_name}: rows must have been written"
        for new_id in mapping.values():
            assert int(stored[new_id]["user_id"]) == USER_C, (
                f"{table_name} row {new_id} must be owned by the caller"
            )


def test_a_second_users_rows_are_untouched_by_an_import__S031_002_DoD9(
    engine: Engine,
) -> None:
    """DoD-9 — a second user's rows are untouched, and no row lands under them. Both the
    witness (B) and the exporting account (A) are checked, row by row. (R5)"""
    source = _user_envelope(engine)
    before = _all_stored_rows(engine)
    witnesses = {USER_A, USER_B}
    before_owned = {
        name: {
            row_id: row
            for row_id, row in rows.items()
            if "user_id" in row and int(row["user_id"]) in witnesses
        }
        for name, rows in before.items()
    }
    assert before_owned[schema.memos.name], "the witnesses own rows to begin with"

    _import(engine, USER_C, source)

    after = _all_stored_rows(engine)
    after_owned = {
        name: {
            row_id: row
            for row_id, row in rows.items()
            if "user_id" in row and int(row["user_id"]) in witnesses
        }
        for name, rows in after.items()
    }
    assert after_owned == before_owned, "no row of theirs changed, and none was added"
    assert after[schema.users.name] == before[schema.users.name]


# --- DoD-10: FTS kept current, no vectors written ------------------------------------


def test_the_import_creates_and_fills_the_fts_tables__S031_002_DoD10(
    engine: Engine,
) -> None:
    """DoD-10 — on a database where `memo_fts` / `message_fts` did not exist beforehand,
    both exist after an import; a `MATCH` on a token from an imported memo body returns
    that memo's **new** id, a token from an imported record row returns its new id, and a
    token from an imported zone row returns nothing. Harvest E9's two precisions: every
    memo is indexed, and buried rows are skipped just as zone rows are. (U3)
    """
    assert not _exists(engine, MEMO_FTS_TABLE), "DoD-10's premise: no memo_fts yet"
    assert not _exists(engine, MESSAGE_FTS_TABLE), "DoD-10's premise: no message_fts yet"
    source = _user_envelope(engine)
    source_payload = _payload(source)
    before = _table_ids(engine)

    _import(engine, USER_C, source)

    assert _exists(engine, MEMO_FTS_TABLE)
    assert _exists(engine, MESSAGE_FTS_TABLE)

    correspondence = _correspondence_from_diff(source_payload, before, _table_ids(engine))
    memo_map = correspondence[schema.memos.name]
    message_map = correspondence[schema.messages.name]

    # **Every** imported memo body is indexed under its new id (harvest E9).
    memos_checked = 0
    for row in _rows(source, schema.memos.name):
        old_memo_id = int(str(row["id"]))
        token = MEMO_TOKENS[old_memo_id]
        assert memo_map[old_memo_id] in _fts_match_ids(engine, MEMO_FTS_TABLE, token), (
            f"memo_fts must hold the imported memo {old_memo_id} under its new id"
        )
        memos_checked += 1
    assert memos_checked == len(memo_map) > 0, "every imported memo was checked"

    # Record rows are indexed; zone and buried rows are not.
    for old_message_id, token in (
        (MSG_HEAD_1, RECORD_TOKEN_1),
        (MSG_HEAD_2, RECORD_TOKEN_2),
    ):
        assert message_map[old_message_id] in _fts_match_ids(
            engine, MESSAGE_FTS_TABLE, token
        ), f"message_fts must hold the imported record row {old_message_id}"
    for token in (ZONE_TOKEN_1, ZONE_TOKEN_2, ZONE_TOKEN_A2, ZONE_TOKEN_A3):
        assert _fts_match_ids(engine, MESSAGE_FTS_TABLE, token) == set(), (
            "a zone row is not indexed"
        )
    for token in (BURIED_TOKEN_1, BURIED_TOKEN_2):
        assert _fts_match_ids(engine, MESSAGE_FTS_TABLE, token) == set(), (
            "a buried row is not indexed either (harvest E9)"
        )


def test_an_import_writes_no_vector_row_when_the_tables_are_absent__S031_002_DoD10(
    engine: Engine,
) -> None:
    """DoD-10, last clause — no `memo_vec` / `session_vec` row is written when those
    tables do not exist: the import neither creates them nor embeds anything, while still
    writing its rows. (U3)"""
    assert not _exists(engine, MEMO_VEC_TABLE)
    assert not _exists(engine, SESSION_VEC_TABLE)
    source = _user_envelope(engine)
    source_payload = _payload(source)
    before = _table_ids(engine)

    _import(engine, USER_C, source)

    correspondence = _correspondence_from_diff(source_payload, before, _table_ids(engine))
    assert correspondence[schema.memos.name], "memos were imported"
    assert correspondence[schema.sessions.name], "sessions were imported"
    assert not _exists(engine, MEMO_VEC_TABLE)
    assert not _exists(engine, SESSION_VEC_TABLE)


def test_an_import_writes_no_vector_row_when_the_tables_exist__S031_002_DoD10(
    engine: Engine,
) -> None:
    """DoD-10, last clause — and no `memo_vec` / `session_vec` row is written when those
    tables **do** exist. They are created here with 024's own helper (test setup only) and
    left empty; the import must leave them empty. (U3)"""
    with engine.begin() as connection:
        ensure_vector_tables(connection, 8)
    assert _exists(engine, MEMO_VEC_TABLE)
    assert _exists(engine, SESSION_VEC_TABLE)
    source = _user_envelope(engine)
    source_payload = _payload(source)
    before = _table_ids(engine)

    _import(engine, USER_C, source)

    correspondence = _correspondence_from_diff(source_payload, before, _table_ids(engine))
    assert correspondence[schema.memos.name], "memos were imported"
    assert correspondence[schema.sessions.name], "sessions were imported"
    assert _vector_row_count(engine, MEMO_VEC_TABLE) == 0
    assert _vector_row_count(engine, SESSION_VEC_TABLE) == 0


# --- DoD-11: the granularities this entry point does not accept ----------------------


@pytest.mark.parametrize("granularity", ["session", "database"])
def test_another_granularity_is_refused_as_wrong__S031_002_DoD11(
    engine: Engine, granularity: str
) -> None:
    """DoD-11 — a `session` or `database` envelope given to `import_owned` raises
    `wrong_granularity`: that exact reason, not merely a refusal."""
    envelope = (
        _session_envelope(engine) if granularity == "session" else _database_envelope(engine)
    )
    assert envelope["granularity"] == granularity
    before = _row_counts(engine)

    _assert_refusal(REASON_WRONG_GRANULARITY, lambda: _import(engine, USER_C, envelope))

    assert _row_counts(engine) == before, "a refusal stores nothing"
