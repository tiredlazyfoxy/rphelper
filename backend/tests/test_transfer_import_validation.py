"""Tests for `app/services/transfer_import.py`'s validation half — feature 031, step 001.

Every expected value comes from the spec: `docs/plans/031.import-and-id-remapping/
001.envelope-validation.md` (Interface intent + Definition of done), `001.context.md`
(§"Pinned messages"), the feature `context.md` (§"The failure contract",
§"Granularity table sets", §"Deserialization") — and from the rows this file seeds
itself. Nothing is read from the implementation.

Bindings are the frozen signatures in `status.md` §Skeleton, "Step 001 — frozen
interface": `ExportInvalidError(reason)` (**one** argument), the five `REASON_*`
constants (**no test re-types a reason string literal**), `DatabaseNotEmptyError`,
`validate_envelope(body, accepted)`, `deserialize_row(table, row, *, allow_missing=())`,
`ValidatedExport(granularity, rows)`, `GRANULARITY_TABLES`, `ROOT_TABLES`,
`EXPORT_GRANULARITIES` and `is_id_column(column, primary_key_names)` (**two** arguments,
decision 11).

Orchestrator corrections honoured here:

- **decision 10** — `ExportGranularity` is a `Literal` type only; the runtime value set is
  `EXPORT_GRANULARITIES`;
- **decision 11** — the id-column predicate takes two arguments; this file keeps its own
  spec copy of the rule and asserts the public predicate agrees with it (DoD-12);
- **decision 13** — the only `Enum` columns in the whole registry are `users.role` (which
  reads back as a `Role` member) and `memos.scope` (which reads back as a plain `str`);
  `messages.role` / `messages.kind` are plain `Text`. Both enum columns are exercised;
- **decision 15** — the three cases nothing downstream can catch (a bad enum string, an id
  above `2**63 - 1`, a JSON `1` in a `Boolean` column) are load-bearing DoD-6 cases.

Envelopes come from 030's exporters over the seeded rows; every malformed body is a deep
copy of a valid envelope with exactly one mutation. This step issues no SQL, so the
database exists only to produce the source envelopes. `conftest.py` is untouched: the
file-local `engine` fixture applies the registry with `schema.metadata.create_all` over
the per-test `tmp_path` database `db_engine` provides, and seeds two users for isolation
with every id above `2**60`.
"""

import copy
from collections.abc import Callable, Collection
from enum import Enum
from typing import Any

import pytest
import sqlalchemy
from sqlalchemy import Boolean, Column, Engine, Integer, String, Table, select

from app.db import schema
from app.errors import (
    REASON_MALFORMED_PAYLOAD,
    REASON_NOT_AN_EXPORT,
    REASON_SCHEMA_MISMATCH,
    REASON_UNSUPPORTED_VERSION,
    REASON_WRONG_GRANULARITY,
    DatabaseNotEmptyError,
    DomainError,
    ExportInvalidError,
)
from app.roles import Role
from app.services.transfer import (
    DATABASE_EXCLUDED_TABLES,
    ENVELOPE_VERSION,
    EXPORT_FORMAT,
    SCHEMA_VERSION,
    USER_EXCLUDED_COLUMNS,
    ExportGranularity,
    export_character,
    export_database,
    export_session,
    export_user,
    is_id_column,
)
from app.services.transfer_import import (
    EXPORT_GRANULARITIES,
    GRANULARITY_TABLES,
    ROOT_TABLES,
    ImportRow,
    ValidatedExport,
    deserialize_row,
    validate_envelope,
)

# --- the pinned contract (`001.context.md` §"Pinned messages") -------------------------

#: The five `export_invalid` sentences, keyed by the reason **constant** — never by a
#: re-typed reason string. These are the messages the step pins verbatim.
PINNED_MESSAGES: dict[str, str] = {
    REASON_NOT_AN_EXPORT: "This file is not an RPHelper export.",
    REASON_UNSUPPORTED_VERSION: "This export was made by an incompatible version of RPHelper.",
    REASON_SCHEMA_MISMATCH: (
        "This export was made with a different database layout and cannot be imported here."
    ),
    REASON_WRONG_GRANULARITY: "This kind of export cannot be imported here.",
    REASON_MALFORMED_PAYLOAD: "This export is damaged or incomplete and cannot be imported.",
}

#: `database_not_empty`'s pinned default message.
DATABASE_NOT_EMPTY_MESSAGE = (
    "The database can only be replaced while it holds no account other than a single administrator."
)

#: `context.md` §"The envelope" (030) — the six header keys, and nothing else.
HEADER_KEYS = ("format", "version", "granularity", "created_at", "schema_version", "payload")

#: DoD-11 — the two tables a whole-database export leaves out.
DATABASE_EXCLUSIONS = {"auth_sessions", "translations"}

#: `001.context.md` §"Signed 64-bit range" — an id string must parse to `0 <= n <= 2**63 - 1`.
ABOVE_SIGNED_64_BIT = str(2**63)


# --- seeded constants -----------------------------------------------------------------

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
SETTLED_AT = "2025-12-31T00:00:00.000000+00:00"
ARCHIVED_AT = "2026-02-01T00:00:00.000000+00:00"

#: Every seeded id is above 2**60, so each is 19 decimal digits.
BASE = 1_152_921_504_606_847_000

USER_A = BASE + 1
USER_B = BASE + 2

SERVER_ID = BASE + 10
MODEL_ID = BASE + 11

CHAR_A1 = BASE + 20
CHAR_B1 = BASE + 21

SETUP_A1 = BASE + 30
SETUP_B1 = BASE + 31

SESSION_A1 = BASE + 40
SESSION_B1 = BASE + 41

MESSAGE_HEAD = BASE + 50
MESSAGE_BURIED = BASE + 51
MESSAGE_ZONE = BASE + 52
MESSAGE_B1 = BASE + 53

MEMO_USER = BASE + 60
MEMO_CHARACTER = BASE + 61
MEMO_SETUP = BASE + 62
MEMO_SESSION = BASE + 63
MEMO_B = BASE + 64

#: The id a DoD-8 duplicate row carries, so "two rows" never means "the same row twice".
SPARE_ID = BASE + 900

PASSWORD_HASH = "not-a-real-hash-but-stored-verbatim"
MODEL_NAME = "seeded-model"

#: DoD-9 — row text that could only have come from the payload. It is seeded on the memo
#: every granularity carries, so the malformed row genuinely holds it.
SENTINEL = "sentinel-payload-text-must-never-leak-7b1e"

#: DoD-9 — the bad id a malformed row carries; payload content too, so it may not leak.
BAD_ID_PROBE = "12a"


# --- registry helpers (the spec's own rules, kept on the test side) -------------------


def _spec_is_id_column(column: Column[Any], primary_key_names: Collection[str]) -> bool:
    """030's id-column rule as the spec states it: primary key, foreign key, or the name
    `id` / a `_id` suffix (`context.md` §"Deserialization" and 030's row-serialization
    rules). DoD-12 asserts the public predicate still agrees with this."""
    name = column.name
    return (
        name in primary_key_names
        or bool(column.foreign_keys)
        or name == "id"
        or name.endswith("_id")
    )


def _primary_key_names(table: Table) -> set[str]:
    return {column.name for column in table.primary_key.columns}


def _sorted_table_order(names: Collection[str]) -> list[str]:
    """`sorted_tables` order restricted to `names` — computed, never a literal order."""
    return [table.name for table in schema.metadata.sorted_tables if table.name in set(names)]


def _expected_cell(value: Any) -> Any:
    """The spec's deserialized value for a stored cell (`context.md` §"Deserialization").

    Ids are ints, booleans bools, timestamps the stored text, nulls `None`, and an enum
    value is its **stored value** — which matters because `users.role` reads back as a
    `Role` member while `memos.scope` reads back as a plain `str` (decision 13).
    """
    if value is None:
        return None
    if isinstance(value, Enum):
        return str(value.value)
    return value


def _assert_cell_type(column: Column[Any], primary_key_names: Collection[str], value: Any) -> None:
    """`context.md` §"Deserialization" — the Python type each column family yields."""
    if value is None:
        assert column.nullable, f"{column.name} is NOT NULL and may not deserialize to None"
        return
    if isinstance(column.type, sqlalchemy.Enum):
        # `Enum` is checked before `String`, because `Enum` subclasses `String`.
        assert type(value) is str, f"{column.name}: an enum value is a string"
        assert value in column.type.enums, f"{column.name}: {value!r} is outside the enum set"
    elif isinstance(column.type, Boolean):
        assert type(value) is bool, f"{column.name}: a boolean column yields a bool"
    elif _spec_is_id_column(column, primary_key_names):
        assert type(value) is int, f"{column.name}: an id column yields an int"
    elif isinstance(column.type, Integer):
        assert type(value) is int, f"{column.name}: an integer column yields a non-bool int"
    else:
        assert isinstance(column.type, String), f"{column.name}: expected a string family"
        assert type(value) is str, f"{column.name}: a text column yields a str"


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
        rp_language=None,
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
    model_server_id: int | None = None,
) -> None:
    # `ck_characters_model_both_or_neither`: the model pair is written together or not at all.
    _insert(
        engine,
        schema.characters,
        id=character_id,
        user_id=user_id,
        name=name,
        sheet="",
        archived_at=None,
        model_server_id=model_server_id,
        model_name=MODEL_NAME if model_server_id is not None else None,
        system_prompt=None,
        tool_memo_search=True,
        tool_session_search=False,
        tool_web_search=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_setup(engine: Engine, *, setup_id: int, user_id: int, character_id: int, name: str) -> None:
    _insert(
        engine,
        schema.setups,
        id=setup_id,
        user_id=user_id,
        character_id=character_id,
        name=name,
        description="",
        archived_at=None,
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
    model_server_id: int | None = None,
) -> None:
    # `ck_sessions_model_both_or_neither`: the model pair is written together or not at all.
    _insert(
        engine,
        schema.sessions,
        id=session_id,
        user_id=user_id,
        character_id=character_id,
        setup_id=setup_id,
        last_used_at=TIMESTAMP,
        archived_at=ARCHIVED_AT if setup_id is None else None,
        model_server_id=model_server_id,
        model_name=MODEL_NAME if model_server_id is not None else None,
        system_prompt=None,
        tool_memo_search=False,
        tool_session_search=None,
        tool_web_search=True,
        rp_language=None,
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
    text: str,
    role: str = "user",
    kind: str | None = None,
    related_to: int | None = None,
    settled_at: str | None = None,
) -> None:
    # `ck_messages_buried_or_settled`: `related_to IS NULL OR settled_at IS NULL`.
    _insert(
        engine,
        schema.messages,
        id=message_id,
        user_id=user_id,
        session_id=session_id,
        role=role,
        kind=kind,
        text=text,
        related_to=related_to,
        settled_at=settled_at,
        tool_name=None,
        tool_payload=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_memo(
    engine: Engine,
    *,
    memo_id: int,
    user_id: int,
    scope: str,
    scope_id: int,
    body: str,
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
        body=body,
        is_enabled=is_enabled,
        is_forced=is_forced,
        sort_key=sort_key,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database holding at least one row of every exported table.

    Two users for isolation, a server and a model, a character carrying the designated
    model pair, a setup, two sessions (one with a setup, one archived without), the three
    message states (a settled head, a buried row pointing at it, a current-zone row) and a
    memo at each of the four scopes. The memo every granularity carries holds DoD-9's
    sentinel.
    """
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)

    _insert_user(db_engine, user_id=USER_A, username="alice", role=Role.ROLEPLAYER)
    _insert_user(db_engine, user_id=USER_B, username="bob", role=Role.ADMIN)

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
    _insert(
        db_engine,
        schema.models,
        id=MODEL_ID,
        server_id=SERVER_ID,
        model_name=MODEL_NAME,
        is_enabled=True,
        is_embedding_designated=False,
        embedding_dim=8,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )

    _insert_character(
        db_engine, character_id=CHAR_A1, user_id=USER_A, name="Aria", model_server_id=SERVER_ID
    )
    _insert_character(db_engine, character_id=CHAR_B1, user_id=USER_B, name="Bob's own")

    _insert_setup(db_engine, setup_id=SETUP_A1, user_id=USER_A, character_id=CHAR_A1, name="Inn")
    _insert_setup(db_engine, setup_id=SETUP_B1, user_id=USER_B, character_id=CHAR_B1, name="Road")

    _insert_session(
        db_engine,
        session_id=SESSION_A1,
        user_id=USER_A,
        character_id=CHAR_A1,
        setup_id=SETUP_A1,
        model_server_id=SERVER_ID,
    )
    _insert_session(db_engine, session_id=SESSION_B1, user_id=USER_B, character_id=CHAR_B1)

    _insert_message(
        db_engine,
        message_id=MESSAGE_HEAD,
        user_id=USER_A,
        session_id=SESSION_A1,
        text="The settled head.",
        role="assistant",
        kind="partner",
        settled_at=SETTLED_AT,
    )
    _insert_message(
        db_engine,
        message_id=MESSAGE_BURIED,
        user_id=USER_A,
        session_id=SESSION_A1,
        text="A buried draft.",
        related_to=MESSAGE_HEAD,
    )
    _insert_message(
        db_engine,
        message_id=MESSAGE_ZONE,
        user_id=USER_A,
        session_id=SESSION_A1,
        text="Still drafting.",
    )
    _insert_message(
        db_engine,
        message_id=MESSAGE_B1,
        user_id=USER_B,
        session_id=SESSION_B1,
        text="Bob's line.",
    )

    _insert_memo(
        db_engine, memo_id=MEMO_USER, user_id=USER_A, scope="user", scope_id=USER_A, body="Global."
    )
    _insert_memo(
        db_engine,
        memo_id=MEMO_CHARACTER,
        user_id=USER_A,
        scope="character",
        scope_id=CHAR_A1,
        body="About Aria.",
        is_forced=True,
        sort_key=200,
    )
    _insert_memo(
        db_engine,
        memo_id=MEMO_SETUP,
        user_id=USER_A,
        scope="setup",
        scope_id=SETUP_A1,
        body="At the inn.",
        is_enabled=False,
    )
    _insert_memo(
        db_engine,
        memo_id=MEMO_SESSION,
        user_id=USER_A,
        scope="session",
        scope_id=SESSION_A1,
        body=SENTINEL,
    )
    _insert_memo(
        db_engine, memo_id=MEMO_B, user_id=USER_B, scope="user", scope_id=USER_B, body="Bob's memo."
    )
    return db_engine


# --- envelope helpers (every body starts life as 030's own export) --------------------


def _envelope(engine: Engine, granularity: ExportGranularity) -> dict[str, Any]:
    """A valid envelope at `granularity`, produced by 030's exporter over the seeded rows."""
    with engine.connect() as connection:
        if granularity == "database":
            exported: Any = export_database(connection)
        elif granularity == "user":
            exported = export_user(connection, USER_A)
        elif granularity == "character":
            exported = export_character(connection, USER_A, CHAR_A1)
        else:
            exported = export_session(connection, USER_A, SESSION_A1)
    return copy.deepcopy(dict(exported))


def _payload(envelope: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    payload = envelope["payload"]
    assert isinstance(payload, dict)
    return payload


def _raw_row(envelope: dict[str, Any], table_name: str, row_id: int) -> dict[str, Any]:
    """The payload row with `row_id` — 030 serializes every id as a decimal string."""
    matches = [row for row in _payload(envelope)[table_name] if row["id"] == str(row_id)]
    assert len(matches) == 1, f"expected exactly one {table_name} row with id {row_id}"
    return matches[0]


def _stored_rows(engine: Engine, table: Table) -> dict[int, dict[str, Any]]:
    """Every row of `table`, keyed by primary key, read straight from the database."""
    with engine.connect() as connection:
        rows = connection.execute(select(table)).all()
    return {int(row._mapping["id"]): dict(row._mapping) for row in rows}


def _rows_by_id(rows: list[ImportRow]) -> dict[int, ImportRow]:
    return {int(str(row["id"])): row for row in rows}


Mutator = Callable[[dict[str, Any]], None]


def _mutated(engine: Engine, granularity: ExportGranularity, mutate: Mutator) -> dict[str, Any]:
    """A deep copy of a valid envelope with exactly one mutation applied."""
    envelope = _envelope(engine, granularity)
    mutate(envelope)
    return envelope


# --- refusal assertions (anchored: the reason, the detail and the pinned message) ------


def _assert_refused(
    reason: str, body: object, accepted: Collection[ExportGranularity]
) -> ExportInvalidError:
    with pytest.raises(ExportInvalidError) as caught:
        validate_envelope(body, accepted)
    error = caught.value
    assert error.code == "export_invalid"
    assert error.http_status == 400
    assert error.detail == {"reason": reason}
    assert error.message == PINNED_MESSAGES[reason]
    assert str(error) == PINNED_MESSAGES[reason]
    return error


def _assert_row_refused(
    table: Table, row: object, *, allow_missing: Collection[str] = ()
) -> ExportInvalidError:
    with pytest.raises(ExportInvalidError) as caught:
        deserialize_row(table, row, allow_missing=allow_missing)
    error = caught.value
    assert error.code == "export_invalid"
    assert error.http_status == 400
    assert error.detail == {"reason": REASON_MALFORMED_PAYLOAD}
    assert str(error) == PINNED_MESSAGES[REASON_MALFORMED_PAYLOAD]
    return error


# =====================================================================================
# DoD-1 — a valid envelope at every granularity, row for row
# =====================================================================================


@pytest.mark.parametrize("granularity", ["database", "user", "character", "session"])
def test_valid_envelope_deserializes_every_stored_row__S031_001_DoD1(
    engine: Engine, granularity: str
) -> None:
    """DoD-1 (US-077.AC-2, US-079.AC-2, US-080.AC-2) — each exporter's envelope validates
    when its granularity is accepted, the rows come back keyed in `sorted_tables` order,
    and every row equals the stored row column for column.

    The `users` row at `user` granularity is the one row that legitimately omits columns,
    namely 030's `USER_EXCLUDED_COLUMNS` (`context.md` §"Granularity table sets").
    """
    envelope = _envelope(engine, granularity)
    payload = _payload(envelope)

    result = validate_envelope(envelope, frozenset({granularity}))

    assert isinstance(result, ValidatedExport)
    assert result.granularity == granularity
    assert list(result.rows) == _sorted_table_order(payload)
    for table_name, rows in result.rows.items():
        table = schema.metadata.tables[table_name]
        key_names = _primary_key_names(table)
        omitted = (
            set(USER_EXCLUDED_COLUMNS)
            if granularity == "user" and table_name == schema.users.name
            else set()
        )
        expected_columns = {column.name for column in table.columns} - omitted
        stored = _stored_rows(engine, table)

        assert rows, f"the seeded database must give {table_name} at least one row"
        assert [row["id"] for row in rows] == [int(raw["id"]) for raw in payload[table_name]]
        for row in rows:
            assert set(row) == expected_columns
            stored_row = stored[int(row["id"])]
            for column_name in sorted(expected_columns):
                column = table.columns[column_name]
                assert row[column_name] == _expected_cell(stored_row[column_name]), (
                    f"{table_name}.{column_name} must equal the stored value"
                )
                _assert_cell_type(column, key_names, row[column_name])


def test_deserialized_cells_carry_the_declared_python_values__S031_001_DoD1(engine: Engine) -> None:
    """DoD-1, cell by seeded cell: ids as ints, booleans as bools, enum values as their
    stored value, timestamps as the stored text, nulls as `None`.

    Both of the registry's enum columns are covered (decision 13): `users.role`, stored as
    a `Role` member, and `memos.scope`, stored as a plain `str`.
    """
    rows = validate_envelope(_envelope(engine, "database"), frozenset({"database"})).rows

    users = _rows_by_id(rows[schema.users.name])
    alice = users[USER_A]
    assert alice["id"] == USER_A
    assert type(alice["id"]) is int
    assert alice["role"] == Role.ROLEPLAYER.value
    assert type(alice["role"]) is str
    assert users[USER_B]["role"] == Role.ADMIN.value
    assert alice["is_enabled"] is True
    assert alice["created_at"] == TIMESTAMP
    assert alice["preferred_language"] == "English"
    assert alice["rp_language"] is None
    assert alice["last_login_at"] is None
    assert alice["password_hash"] == PASSWORD_HASH

    memos = _rows_by_id(rows[schema.memos.name])
    assert memos[MEMO_CHARACTER]["scope"] == "character"
    assert type(memos[MEMO_CHARACTER]["scope"]) is str
    assert memos[MEMO_CHARACTER]["scope_id"] == CHAR_A1
    assert memos[MEMO_CHARACTER]["sort_key"] == 200
    assert type(memos[MEMO_CHARACTER]["sort_key"]) is int
    assert memos[MEMO_CHARACTER]["is_forced"] is True
    assert memos[MEMO_SETUP]["is_enabled"] is False
    assert memos[MEMO_SESSION]["body"] == SENTINEL

    messages = _rows_by_id(rows[schema.messages.name])
    assert messages[MESSAGE_HEAD]["settled_at"] == SETTLED_AT
    assert messages[MESSAGE_HEAD]["kind"] == "partner"
    assert messages[MESSAGE_BURIED]["related_to"] == MESSAGE_HEAD
    assert type(messages[MESSAGE_BURIED]["related_to"]) is int
    assert messages[MESSAGE_ZONE]["related_to"] is None
    assert messages[MESSAGE_ZONE]["settled_at"] is None
    assert messages[MESSAGE_ZONE]["kind"] is None

    characters = _rows_by_id(rows[schema.characters.name])
    assert characters[CHAR_A1]["model_server_id"] == SERVER_ID
    assert characters[CHAR_A1]["model_name"] == MODEL_NAME
    assert characters[CHAR_A1]["tool_memo_search"] is True
    assert characters[CHAR_A1]["tool_session_search"] is False
    assert characters[CHAR_A1]["tool_web_search"] is None
    assert characters[CHAR_B1]["model_server_id"] is None

    models = _rows_by_id(rows[schema.models.name])
    assert models[MODEL_ID]["embedding_dim"] == 8
    assert type(models[MODEL_ID]["embedding_dim"]) is int
    assert models[MODEL_ID]["is_embedding_designated"] is False


# =====================================================================================
# DoD-2 — `not_an_export`
# =====================================================================================


def _drop_header_key(key: str) -> Mutator:
    def mutate(envelope: dict[str, Any]) -> None:
        del envelope[key]

    return mutate


@pytest.mark.parametrize("key", HEADER_KEYS)
def test_missing_header_key_is_not_an_export__S031_001_DoD2(engine: Engine, key: str) -> None:
    """DoD-2 / `context.md` §"The failure contract" case 1 — any of the six header keys
    missing is `not_an_export`."""
    body = _mutated(engine, "user", _drop_header_key(key))
    _assert_refused(REASON_NOT_AN_EXPORT, body, EXPORT_GRANULARITIES)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param([], id="empty-json-array"),
        pytest.param(["rphelper-export"], id="json-array"),
        pytest.param("rphelper-export", id="json-string"),
        pytest.param(None, id="json-null"),
    ],
)
def test_a_body_that_is_not_an_object_is_not_an_export__S031_001_DoD2(body: object) -> None:
    """DoD-2 — a JSON array (and any other non-object body) is `not_an_export`."""
    _assert_refused(REASON_NOT_AN_EXPORT, body, EXPORT_GRANULARITIES)


def _set_extra_header_key(envelope: dict[str, Any]) -> None:
    envelope["exported_by"] = "someone else"


def _wrong_format(envelope: dict[str, Any]) -> None:
    envelope["format"] = "not-an-rphelper-export"


def _unknown_granularity(envelope: dict[str, Any]) -> None:
    envelope["granularity"] = "everything"


def _wrong_format_and_version(envelope: dict[str, Any]) -> None:
    envelope["format"] = "not-an-rphelper-export"
    envelope["version"] = ENVELOPE_VERSION + 1


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_set_extra_header_key, id="extra-header-key"),
        pytest.param(_wrong_format, id="wrong-format"),
        pytest.param(_unknown_granularity, id="granularity-everything"),
        pytest.param(_wrong_format_and_version, id="wrong-format-decides-before-version"),
    ],
)
def test_bad_header_values_are_not_an_export__S031_001_DoD2(engine: Engine, mutate: Mutator) -> None:
    """DoD-2 — an extra header key, a `format` other than the literal, and a `granularity`
    outside the four are each `not_an_export`.

    The last case pins the order `001.context.md` calls load-bearing: a body with a wrong
    `format` **and** a wrong `version` still answers `not_an_export`.
    """
    assert EXPORT_FORMAT == "rphelper-export"
    _assert_refused(REASON_NOT_AN_EXPORT, _mutated(engine, "user", mutate), EXPORT_GRANULARITIES)


# =====================================================================================
# DoD-3 — `unsupported_version` and `schema_mismatch`
# =====================================================================================


def _version_one_higher(envelope: dict[str, Any]) -> None:
    envelope["version"] = ENVELOPE_VERSION + 1


def _version_as_string(envelope: dict[str, Any]) -> None:
    envelope["version"] = str(ENVELOPE_VERSION)


def _version_and_schema_version_both_wrong(envelope: dict[str, Any]) -> None:
    envelope["version"] = ENVELOPE_VERSION + 1
    envelope["schema_version"] = SCHEMA_VERSION + 1


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_version_one_higher, id="version-one-higher"),
        pytest.param(_version_as_string, id="version-as-a-string"),
        pytest.param(_version_and_schema_version_both_wrong, id="version-decides-before-schema"),
    ],
)
def test_bad_envelope_version_is_unsupported_version__S031_001_DoD3(
    engine: Engine, mutate: Mutator
) -> None:
    """DoD-3 — a `version` one higher than 030's, and a `version` given as a string, are
    each `unsupported_version`; the version check runs before the schema check."""
    _assert_refused(
        REASON_UNSUPPORTED_VERSION, _mutated(engine, "user", mutate), EXPORT_GRANULARITIES
    )


def _schema_version_one_higher(envelope: dict[str, Any]) -> None:
    envelope["schema_version"] = SCHEMA_VERSION + 1


def _schema_version_one_lower(envelope: dict[str, Any]) -> None:
    envelope["schema_version"] = SCHEMA_VERSION - 1


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_schema_version_one_higher, id="schema-version-one-higher"),
        pytest.param(_schema_version_one_lower, id="schema-version-one-lower"),
    ],
)
def test_unequal_schema_version_is_schema_mismatch__S031_001_DoD3(
    engine: Engine, mutate: Mutator
) -> None:
    """DoD-3 — only an equal `schema_version` is accepted: newer **and** older are refused,
    with everything else in the envelope valid."""
    _assert_refused(REASON_SCHEMA_MISMATCH, _mutated(engine, "user", mutate), EXPORT_GRANULARITIES)


# =====================================================================================
# DoD-4 — `wrong_granularity`
# =====================================================================================


@pytest.mark.parametrize("granularity", ["session", "database"])
def test_unaccepted_granularity_is_wrong_granularity__S031_001_DoD4(
    engine: Engine, granularity: str
) -> None:
    """DoD-4 — a valid `session` envelope and a valid `database` envelope each answer
    `wrong_granularity` when the accepted set is {`user`, `character`}."""
    _assert_refused(
        REASON_WRONG_GRANULARITY,
        _envelope(engine, granularity),
        frozenset({"user", "character"}),
    )


# =====================================================================================
# DoD-5 — `malformed_payload` for a wrong payload shape
# =====================================================================================


def _drop_memos_table(envelope: dict[str, Any]) -> None:
    del _payload(envelope)["memos"]


def _extra_table(table_name: str) -> Mutator:
    def mutate(envelope: dict[str, Any]) -> None:
        _payload(envelope)[table_name] = []

    return mutate


def _messages_as_object(envelope: dict[str, Any]) -> None:
    _payload(envelope)["messages"] = {"0": _payload(envelope)["messages"][0]}


def _row_as_string(envelope: dict[str, Any]) -> None:
    _payload(envelope)["memos"][0] = "this is not a row"


@pytest.mark.parametrize(
    ("granularity", "mutate"),
    [
        pytest.param("user", _drop_memos_table, id="user-payload-missing-memos"),
        pytest.param("character", _extra_table("llm_servers"), id="character-extra-llm_servers"),
        pytest.param("character", _extra_table("models"), id="character-extra-models"),
        pytest.param("character", _extra_table("auth_sessions"), id="character-extra-auth_sessions"),
        pytest.param("character", _extra_table("translations"), id="character-extra-translations"),
        pytest.param("session", _messages_as_object, id="session-messages-as-an-object"),
        pytest.param("session", _row_as_string, id="a-row-that-is-a-string"),
    ],
)
def test_wrong_payload_shape_is_malformed_payload__S031_001_DoD5(
    engine: Engine, granularity: str, mutate: Mutator
) -> None:
    """DoD-5 — a missing payload table, any of the four tables a roleplayer payload may not
    carry, a table whose value is an object rather than a list, and a row that is a string
    are each `malformed_payload`."""
    _assert_refused(
        REASON_MALFORMED_PAYLOAD, _mutated(engine, granularity, mutate), EXPORT_GRANULARITIES
    )


# =====================================================================================
# DoD-6 — `malformed_payload` for a bad row or cell
# =====================================================================================


def _memo_cell(key: str, value: Any) -> Mutator:
    """Set one cell on the memo every granularity carries (`MEMO_SESSION`)."""

    def mutate(envelope: dict[str, Any]) -> None:
        _raw_row(envelope, "memos", MEMO_SESSION)[key] = value

    return mutate


def _memo_drop_column(key: str) -> Mutator:
    def mutate(envelope: dict[str, Any]) -> None:
        del _raw_row(envelope, "memos", MEMO_SESSION)[key]

    return mutate


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_memo_drop_column("sort_key"), id="row-missing-one-column"),
        pytest.param(_memo_cell("unexpected_column", "x"), id="row-with-one-extra-column"),
        pytest.param(_memo_cell("id", BAD_ID_PROBE), id="id-that-is-not-decimal-digits"),
        pytest.param(_memo_cell("scope_id", 12), id="id-given-as-a-json-number"),
        pytest.param(_memo_cell("id", ABOVE_SIGNED_64_BIT), id="id-beyond-signed-64-bit"),
        pytest.param(_memo_cell("is_enabled", 1), id="boolean-column-holding-1"),
        pytest.param(_memo_cell("scope", "galaxy"), id="memos-scope-galaxy"),
        pytest.param(_memo_cell("body", None), id="null-in-a-not-null-text-column"),
        pytest.param(_memo_cell("sort_key", True), id="integer-non-id-column-holding-true"),
    ],
)
def test_bad_row_or_cell_is_malformed_payload__S031_001_DoD6(
    engine: Engine, mutate: Mutator
) -> None:
    """DoD-6 / `context.md` §"Deserialization" — a missing or extra column, an id that is
    not a decimal-digit string, an id given as a JSON number, an id beyond the signed
    64-bit range, a `Boolean` column holding `1`, an enum value outside its set, a null in
    a NOT NULL text column, and an integer non-id column holding `true`.

    Decision 15: the bad enum string, the out-of-range id and the JSON `1` in a boolean
    column are **only** catchable here — a write would raise `StatementError`,
    `OverflowError` or nothing at all, so nothing downstream can reject them.
    """
    _assert_refused(REASON_MALFORMED_PAYLOAD, _mutated(engine, "user", mutate), EXPORT_GRANULARITIES)


def _valid_memo_row(engine: Engine) -> dict[str, Any]:
    return _raw_row(_envelope(engine, "user"), "memos", MEMO_SESSION)


def test_deserialize_row_accepts_a_whole_valid_row__S031_001_DoD6(engine: Engine) -> None:
    """DoD-6's premise — the same row, unmutated, deserializes to the stored values, so the
    refusals above are about the mutation and not about the row."""
    row = deserialize_row(schema.memos, _valid_memo_row(engine))
    assert set(row) == {column.name for column in schema.memos.columns}
    assert row["id"] == MEMO_SESSION
    assert row["scope"] == "session"
    assert row["scope_id"] == SESSION_A1
    assert row["body"] == SENTINEL
    assert row["is_enabled"] is True
    assert row["is_forced"] is False
    assert row["sort_key"] == 100


@pytest.mark.parametrize(
    ("key", "value"),
    [
        pytest.param("id", BAD_ID_PROBE, id="id-that-is-not-decimal-digits"),
        pytest.param("id", ABOVE_SIGNED_64_BIT, id="id-beyond-signed-64-bit"),
        pytest.param("scope_id", 12, id="id-given-as-a-json-number"),
        pytest.param("is_forced", 1, id="boolean-column-holding-1"),
        pytest.param("scope", "galaxy", id="memos-scope-galaxy"),
        pytest.param("body", None, id="null-in-a-not-null-text-column"),
        pytest.param("sort_key", True, id="integer-non-id-column-holding-true"),
        pytest.param("unexpected_column", "x", id="row-with-one-extra-column"),
    ],
)
def test_deserialize_row_refuses_a_bad_cell__S031_001_DoD6(
    engine: Engine, key: str, value: Any
) -> None:
    """DoD-6 at the deserializer itself, bound to the frozen
    `deserialize_row(table, row, *, allow_missing=())`."""
    row = _valid_memo_row(engine)
    row[key] = value
    _assert_row_refused(schema.memos, row)


def test_deserialize_row_refuses_a_missing_column_and_a_non_object__S031_001_DoD6(
    engine: Engine,
) -> None:
    """DoD-6 — the row's key set must equal the table's columns minus the allowed
    omissions, and a row that is not an object is refused."""
    row = _valid_memo_row(engine)
    del row["sort_key"]
    _assert_row_refused(schema.memos, row)
    _assert_row_refused(schema.memos, "this is not a row")


# =====================================================================================
# DoD-7 — the one legitimately shortened row: `users` at `user` granularity
# =====================================================================================


def test_user_granularity_users_row_omits_exactly_the_excluded_columns__S031_001_DoD7(
    engine: Engine,
) -> None:
    """DoD-7 (US-136.AC-1's payload shape) — at `user` granularity the `users` row carries
    the table's columns **minus** 030's `USER_EXCLUDED_COLUMNS`, and that is accepted both
    through `validate_envelope` and through `deserialize_row`'s `allow_missing`."""
    # `context.md` §"Granularity table sets" names the three excluded columns.
    assert set(USER_EXCLUDED_COLUMNS) == {"password_hash", "role", "is_enabled"}
    expected = {column.name for column in schema.users.columns} - set(USER_EXCLUDED_COLUMNS)

    envelope = _envelope(engine, "user")
    raw = _raw_row(envelope, "users", USER_A)
    assert set(raw) == expected

    rows = validate_envelope(envelope, frozenset({"user"})).rows
    assert set(rows[schema.users.name][0]) == expected

    row = deserialize_row(schema.users, raw, allow_missing=USER_EXCLUDED_COLUMNS)
    assert set(row) == expected
    assert row["id"] == USER_A
    assert row["username"] == "alice"


def test_user_granularity_users_row_with_password_hash_is_malformed__S031_001_DoD7(
    engine: Engine,
) -> None:
    """DoD-7 — a `users` row that **includes** `password_hash` at `user` granularity is
    `malformed_payload`: the key set must equal the columns minus the omissions, so an
    omitted-column value present is as wrong as a column missing."""

    def mutate(envelope: dict[str, Any]) -> None:
        _raw_row(envelope, "users", USER_A)["password_hash"] = PASSWORD_HASH

    _assert_refused(REASON_MALFORMED_PAYLOAD, _mutated(engine, "user", mutate), frozenset({"user"}))

    raw = _raw_row(_envelope(engine, "user"), "users", USER_A)
    raw["password_hash"] = PASSWORD_HASH
    _assert_row_refused(schema.users, raw, allow_missing=USER_EXCLUDED_COLUMNS)


def test_database_granularity_users_row_without_password_hash_is_malformed__S031_001_DoD7(
    engine: Engine,
) -> None:
    """DoD-7 — at `database` granularity nothing may be omitted, so a `users` row missing
    `password_hash` is `malformed_payload`."""

    def mutate(envelope: dict[str, Any]) -> None:
        del _raw_row(envelope, "users", USER_A)["password_hash"]

    _assert_refused(
        REASON_MALFORMED_PAYLOAD, _mutated(engine, "database", mutate), frozenset({"database"})
    )

    raw = _raw_row(_envelope(engine, "database"), "users", USER_A)
    del raw["password_hash"]
    _assert_row_refused(schema.users, raw)


# =====================================================================================
# DoD-8 — the root count
# =====================================================================================


def _duplicate_root_row(table_name: str) -> Mutator:
    def mutate(envelope: dict[str, Any]) -> None:
        rows = _payload(envelope)[table_name]
        duplicate = copy.deepcopy(rows[0])
        duplicate["id"] = str(SPARE_ID)
        rows.append(duplicate)

    return mutate


def _empty_table(table_name: str) -> Mutator:
    def mutate(envelope: dict[str, Any]) -> None:
        _payload(envelope)[table_name] = []

    return mutate


@pytest.mark.parametrize(
    ("granularity", "mutate"),
    [
        pytest.param("character", _duplicate_root_row("characters"), id="two-characters-rows"),
        pytest.param("character", _empty_table("characters"), id="no-characters-row"),
        pytest.param("session", _duplicate_root_row("sessions"), id="two-sessions-rows"),
        pytest.param("user", _duplicate_root_row("users"), id="two-users-rows"),
    ],
)
def test_wrong_root_row_count_is_malformed_payload__S031_001_DoD8(
    engine: Engine, granularity: str, mutate: Mutator
) -> None:
    """DoD-8 / `context.md` §"Granularity table sets" root rule — the root table must hold
    exactly one row; two rows or none is `malformed_payload`."""
    _assert_refused(
        REASON_MALFORMED_PAYLOAD, _mutated(engine, granularity, mutate), EXPORT_GRANULARITIES
    )


def test_root_tables_name_the_table_that_must_hold_one_row__S031_001_DoD8() -> None:
    """DoD-8's subject, as the Interface intent fixes it: a module-level mapping from
    `user`, `character` and `session` to that granularity's root table. `database` has no
    root, so it is deliberately not a key."""
    assert ROOT_TABLES == {
        "user": schema.users.name,
        "character": schema.characters.name,
        "session": schema.sessions.name,
    }


# =====================================================================================
# DoD-9 — the wire detail, the redaction rule and the five pinned messages
# =====================================================================================


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_memo_cell("id", BAD_ID_PROBE), id="bad-id-on-the-sentinel-row"),
        pytest.param(_memo_cell("scope", "galaxy"), id="bad-enum-on-the-sentinel-row"),
        pytest.param(_memo_drop_column("sort_key"), id="missing-column-on-the-sentinel-row"),
    ],
)
def test_no_payload_content_reaches_the_error__S031_001_DoD9(
    engine: Engine, mutate: Mutator
) -> None:
    """DoD-9 (R5, `deployment.md`'s redaction rule) — the `detail` carries nothing but
    `reason`, and the sentinel string seeded on the malformed row appears in neither the
    `detail`, the message, nor the exception's text."""
    body = _mutated(engine, "user", mutate)
    # The sentinel really is in the body that is about to be refused.
    assert SENTINEL in str(body)

    error = _assert_refused(REASON_MALFORMED_PAYLOAD, body, EXPORT_GRANULARITIES)

    assert set(error.detail) == {"reason"}
    rendered = f"{error.detail} {error.message} {error} {error!r} {error.to_wire()}"
    assert SENTINEL not in rendered
    assert BAD_ID_PROBE not in rendered
    assert "memos" not in rendered
    assert str(MEMO_SESSION) not in rendered


@pytest.mark.parametrize("reason", sorted(PINNED_MESSAGES))
def test_export_invalid_error_carries_only_the_reason__S031_001_DoD9(reason: str) -> None:
    """DoD-9 — `ExportInvalidError(reason)` takes exactly one argument, its `detail` is
    exactly `{"reason": reason}`, and its message is that reason's sentence pinned in
    `001.context.md`."""
    error = ExportInvalidError(reason)
    assert isinstance(error, DomainError)
    assert error.code == "export_invalid"
    assert error.http_status == 400
    assert error.reason == reason
    assert error.detail == {"reason": reason}
    assert error.message == PINNED_MESSAGES[reason]
    assert str(error) == PINNED_MESSAGES[reason]
    assert error.to_wire() == {
        "error": {
            "code": "export_invalid",
            "message": PINNED_MESSAGES[reason],
            "detail": {"reason": reason},
        }
    }


def test_the_five_reasons_are_distinct_and_complete__S031_001_DoD9() -> None:
    """DoD-9 / `context.md` §"The failure contract" — the reason vocabulary is exactly five
    distinct values, and this file never re-types one of them."""
    reasons = (
        REASON_NOT_AN_EXPORT,
        REASON_UNSUPPORTED_VERSION,
        REASON_SCHEMA_MISMATCH,
        REASON_WRONG_GRANULARITY,
        REASON_MALFORMED_PAYLOAD,
    )
    assert len(set(reasons)) == 5
    assert all(isinstance(reason, str) for reason in reasons)
    assert len(set(PINNED_MESSAGES.values())) == 5


# =====================================================================================
# DoD-10 — `DatabaseNotEmptyError`
# =====================================================================================


def test_database_not_empty_error_is_the_pinned_409__S031_001_DoD10() -> None:
    """DoD-10 — code `database_not_empty`, status 409, empty `detail`, and the default
    message pinned in `001.context.md`."""
    error = DatabaseNotEmptyError()
    assert isinstance(error, DomainError)
    assert error.code == "database_not_empty"
    assert error.http_status == 409
    assert error.detail == {}
    assert error.message == DATABASE_NOT_EMPTY_MESSAGE
    assert str(error) == DATABASE_NOT_EMPTY_MESSAGE
    assert error.to_wire() == {
        "error": {
            "code": "database_not_empty",
            "message": DATABASE_NOT_EMPTY_MESSAGE,
            "detail": {},
        }
    }


# =====================================================================================
# DoD-11 — the per-granularity table sets
# =====================================================================================


def test_database_table_set_is_sorted_tables_minus_the_two_exclusions__S031_001_DoD11() -> None:
    """DoD-11 — the `database` set is `sorted_tables`'s names minus `auth_sessions` and
    `translations`. It is **derived** from the registry, never hand-listed."""
    assert set(DATABASE_EXCLUDED_TABLES) == DATABASE_EXCLUSIONS
    expected = {table.name for table in schema.metadata.sorted_tables} - DATABASE_EXCLUSIONS
    assert GRANULARITY_TABLES["database"] == expected
    assert set(GRANULARITY_TABLES) == set(EXPORT_GRANULARITIES)


@pytest.mark.parametrize("granularity", ["user", "character", "session"])
def test_roleplayer_table_sets_equal_what_030s_exporters_produce__S031_001_DoD11(
    engine: Engine, granularity: str
) -> None:
    """DoD-11 — the `user`, `character` and `session` sets equal the payload key sets 030's
    exporters actually produce, so the clause cannot drift from the exporters."""
    assert GRANULARITY_TABLES[granularity] == set(_payload(_envelope(engine, granularity)))


# =====================================================================================
# DoD-12 — the id-column predicate's behaviour is unchanged
# =====================================================================================


def test_public_id_column_predicate_still_follows_030s_rule__S031_001_DoD12() -> None:
    """DoD-12 — exposing the predicate under a public name changed no behaviour: for every
    column of every registry table, `is_id_column(column, primary_key_names)` (two
    arguments, decision 11) agrees with 030's rule — primary key, foreign key, the name
    `id`, or a `_id` suffix."""
    checked = 0
    for table in schema.metadata.sorted_tables:
        key_names = _primary_key_names(table)
        for column in table.columns:
            assert is_id_column(column, key_names) is _spec_is_id_column(column, key_names)
            checked += 1
    assert checked > 0

    # The two columns DoD-12 names, plus two that must stay outside the rule.
    assert is_id_column(schema.memos.c.scope_id, _primary_key_names(schema.memos)) is True
    assert (
        is_id_column(schema.characters.c.model_server_id, _primary_key_names(schema.characters))
        is True
    )
    assert is_id_column(schema.memos.c.sort_key, _primary_key_names(schema.memos)) is False
    assert is_id_column(schema.memos.c.body, _primary_key_names(schema.memos)) is False


def test_database_export_still_serializes_the_two_fk_less_ids_as_strings__S031_001_DoD12(
    engine: Engine,
) -> None:
    """DoD-12's regression case — a database export's `memos.scope_id` and
    `characters.model_server_id`, both caught by the name arm alone, are still decimal
    strings, and they still deserialize back to the seeded ints."""
    envelope = _envelope(engine, "database")
    assert _raw_row(envelope, "memos", MEMO_CHARACTER)["scope_id"] == str(CHAR_A1)
    assert _raw_row(envelope, "characters", CHAR_A1)["model_server_id"] == str(SERVER_ID)

    rows = validate_envelope(envelope, frozenset({"database"})).rows
    assert _rows_by_id(rows[schema.memos.name])[MEMO_CHARACTER]["scope_id"] == CHAR_A1
    assert _rows_by_id(rows[schema.characters.name])[CHAR_A1]["model_server_id"] == SERVER_ID
