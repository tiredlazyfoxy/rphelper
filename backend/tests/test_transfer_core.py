"""Tests for `app/services/transfer.py` — feature 030, step 001 (DoD-1..11).

Every expected value comes from `docs/plans/030.export-granularities/001.transfer-core.md`
(its Interface intent and Definition of done), from `001.context.md`, from the feature
`context.md` (§"The envelope", §"Row serialization rules", §"Granularity boundaries") and
from the rows this file seeds itself. Nothing is read from the implementation.

Four corrections recorded in `status.md` §"Ultra phase" are binding here and are cited at
the tests that honour them:

- **decision 4** — `schema.metadata.sorted_tables` is a stable *topological* sort, so the
  expected payload order is always **computed** from the registry, never a literal;
- **decision 5** — `memos.scope` arrives as a plain `str` and exercises no enum
  conversion; the column that arrives as an enum member is `users.role`, which is present
  only at **database** granularity. DoD-7 is therefore covered on both columns;
- **decision 6** — there is no `session_fts` table. DoD-4's real four are `memo_fts`,
  `message_fts`, `memo_vec` and `session_vec`;
- **decision 8** — `model_server_id` exists on **two** tables (`characters` and
  `sessions`), and `messages.related_to` is an id caught only by the foreign-key arm of
  the id rule, while `models.embedding_dim` and `memos.sort_key` are plain integers.

Seeding: a file-local `engine` fixture applies the registry with
`schema.metadata.create_all` and raw-inserts every included table, including two users
(one roleplayer, one admin), an archived character / setup / session, and the three
message states. Buried rows are produced by appending a zone and settling it through
`app/services/settle.py` (`002.context.md` "Seeding buried messages"): the non-head rows
become buried with `related_to` set to the head. Ids are all above 2**60 so that no id can
be confused with a compact timestamp. `conftest.py` is untouched; the database is the
per-test `tmp_path` file `db_engine` provides.
"""

import json
import re
from datetime import datetime
from typing import Any

import pytest
from sqlalchemy import Column, Engine, Table, select, update

from app.db import schema
from app.roles import Role
from app.services.settle import settle
from app.services.transfer import (
    DATABASE_EXCLUDED_TABLES,
    ENVELOPE_VERSION,
    EXPORT_FORMAT,
    SCHEMA_VERSION,
    encode_envelope,
    export_database,
    export_filename,
)

# --- seeded constants -----------------------------------------------------------------

#: The seeded instant, in the fixed-width UTC ISO-8601 text every service writes.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
SEEDED_SETTLED_AT = "2025-12-31T00:00:00.000000+00:00"
ARCHIVED_AT = "2026-02-01T00:00:00.000000+00:00"
EXPIRES_AT = "2026-03-01T00:00:00.000000+00:00"

#: Every seeded id is above 2**60 (1152921504606846976), so each is 19 decimal digits.
BASE = 1_152_921_504_606_847_000

USER_A = BASE + 1
USER_B = BASE + 2

SERVER_ID = BASE + 10
MODEL_ID = BASE + 11

CHAR_A1 = BASE + 20
CHAR_A2 = BASE + 21
CHAR_B1 = BASE + 22

SETUP_A1 = BASE + 30
SETUP_A2 = BASE + 31
SETUP_B1 = BASE + 32

SESSION_A1 = BASE + 40
SESSION_A2 = BASE + 41
SESSION_B1 = BASE + 42

ZONE_1 = BASE + 50
ZONE_2 = BASE + 51
ZONE_3 = BASE + 52
ZONE_4 = BASE + 53
PARTNER_1 = BASE + 54
MESSAGE_A2 = BASE + 55
MESSAGE_B1 = BASE + 56

MEMO_USER = BASE + 70
MEMO_CHARACTER = BASE + 71
MEMO_SETUP = BASE + 72
MEMO_SESSION = BASE + 73
MEMO_B = BASE + 74

AUTH_SESSION_ID = BASE + 90
TRANSLATION_ID = BASE + 91

#: DoD-8 — the `"$NAME"` pointer stored on `llm_servers.api_key_ref` and the environment
#: variable it names. The variable is deliberately **not** `RPHELPER_`-prefixed, so
#: `conftest.py`'s environment sweep cannot reach it and the sentinel is genuinely set.
API_KEY_REF = "$EXPORT_SECRET_SENTINEL_VAR"
SECRET_VARIABLE = "EXPORT_SECRET_SENTINEL_VAR"
SECRET_SENTINEL = "sentinel-secret-must-never-be-resolved-9f3c"

#: The model name seeded on `models`, and the companion value the two
#: `model_server_id`-carrying tables store alongside a non-null server reference.
#: `characters` and `sessions` each hold a CHECK (`ck_characters_model_both_or_neither`,
#: `ck_sessions_model_both_or_neither`, frozen by feature 017's skeleton) requiring
#: `model_server_id` and `model_name` to be **both NULL or both non-NULL**, so the two
#: insert helpers below always write them as a pair.
MODEL_NAME = "seeded-model"

#: DoD-8 — `users.password_hash` is carried as stored at database granularity.
PASSWORD_HASH = "not-a-real-hash-but-stored-verbatim"

#: DoD-10 — non-ASCII row text that must round-trip unchanged.
NON_ASCII_BODY = "Привет, мир — ünïcode ✓ 日本語"

#: DoD-11 — a probe string that must never reach a filename.
FILENAME_PROBE = "probe-row-content-must-not-appear"

#: DoD-11 — `rphelper-<granularity>-<digits/letters timestamp>.json`.
FILENAME_PATTERN = re.compile(r"^rphelper-database-[0-9A-Za-z]+\.json$")

#: DoD-4 / decision 6 — 024's four FTS5 / vec0 tables. None lives in `schema.metadata`.
SEARCH_TABLE_NAMES = ("memo_fts", "message_fts", "memo_vec", "session_vec")

#: DoD-2 / DoD-3 — the two tables the whole-database export skips, as the DoD names them.
EXCLUDED_TABLE_NAMES = {"auth_sessions", "translations"}


# --- registry helpers (every expectation is computed, never a literal order) ----------


def _table(name: str) -> Table:
    return schema.metadata.tables[name]


def _primary_key_name(table: Table) -> str:
    """The table's single primary-key column name (every table in the registry has one)."""
    names = [column.name for column in table.primary_key.columns]
    assert len(names) == 1, f"{table.name} is expected to have a single-column primary key"
    return names[0]


def _is_id_column(column: Column[Any]) -> bool:
    """`context.md` §"Row serialization rules" — the three arms of the id-column rule."""
    return bool(
        column.primary_key
        or column.foreign_keys
        or column.name == "id"
        or column.name.endswith("_id")
    )


def _expected_database_table_order() -> list[str]:
    """`sorted_tables` order restricted to the included tables — decision 4: computed."""
    return [
        table.name
        for table in schema.metadata.sorted_tables
        if table.name not in EXCLUDED_TABLE_NAMES
    ]


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
        preferred_language=None,
        last_login_at=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_server(engine: Engine) -> None:
    _insert(
        engine,
        _table("llm_servers"),
        id=SERVER_ID,
        name="the seeded server",
        kind="llamaswap",
        base_url="http://127.0.0.1:9999",
        api_key_ref=API_KEY_REF,
        last_test_at=None,
        last_test_ok=None,
        last_test_error=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_model(engine: Engine) -> None:
    _insert(
        engine,
        _table("models"),
        id=MODEL_ID,
        server_id=SERVER_ID,
        model_name=MODEL_NAME,
        is_enabled=True,
        is_embedding_designated=False,
        embedding_dim=8,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_character(
    engine: Engine,
    *,
    character_id: int,
    user_id: int,
    name: str,
    archived_at: str | None = None,
    model_server_id: int | None = None,
) -> None:
    # `ck_characters_model_both_or_neither`: the designated-model pair is written together.
    _insert(
        engine,
        schema.characters,
        id=character_id,
        user_id=user_id,
        name=name,
        sheet="",
        archived_at=archived_at,
        model_server_id=model_server_id,
        model_name=MODEL_NAME if model_server_id is not None else None,
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
        description="",
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
    archived_at: str | None = None,
    model_server_id: int | None = None,
) -> None:
    # `ck_sessions_model_both_or_neither`: the designated-model pair is written together.
    _insert(
        engine,
        schema.sessions,
        id=session_id,
        user_id=user_id,
        character_id=character_id,
        setup_id=setup_id,
        archived_at=archived_at,
        model_server_id=model_server_id,
        model_name=MODEL_NAME if model_server_id is not None else None,
        last_used_at=TIMESTAMP,
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


def _archive_session(engine: Engine, session_id: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            update(schema.sessions)
            .where(schema.sessions.c.id == session_id)
            .values(archived_at=ARCHIVED_AT)
        )


# --- stored-row snapshot (the test side's own reads) ----------------------------------


def _stored_rows(engine: Engine, table: Table) -> dict[int, dict[str, Any]]:
    """Every row of `table`, keyed by primary key, read straight from the database."""
    key = _primary_key_name(table)
    with engine.connect() as connection:
        rows = connection.execute(select(table)).all()
    return {int(row._mapping[key]): dict(row._mapping) for row in rows}


# --- fixture --------------------------------------------------------------------------


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database holding at least one row of every included table.

    Two owners, a global server and model, an archived character / setup / session, the
    three message states (settled head, buried rows, current zone), a memo at each scope,
    one `auth_sessions` row and one `translations` row (DoD-3), plus the null references
    DoD-6 needs.
    """
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)

    _insert_user(db_engine, user_id=USER_A, username="alice", role=Role.ROLEPLAYER)
    _insert_user(db_engine, user_id=USER_B, username="bob", role=Role.ADMIN)
    _insert_server(db_engine)
    _insert_model(db_engine)

    # `CHAR_A1` carries the non-null designated-model pair; `CHAR_A2` (archived) and
    # `CHAR_B1` leave both `model_server_id` and `model_name` NULL, which is DoD-6's
    # null-reference case on `characters`.
    _insert_character(
        db_engine, character_id=CHAR_A1, user_id=USER_A, name="Aria", model_server_id=SERVER_ID
    )
    _insert_character(
        db_engine, character_id=CHAR_A2, user_id=USER_A, name="Understudy", archived_at=ARCHIVED_AT
    )
    _insert_character(db_engine, character_id=CHAR_B1, user_id=USER_B, name="Bob's own")

    _insert_setup(db_engine, setup_id=SETUP_A1, user_id=USER_A, character_id=CHAR_A1, name="Inn")
    _insert_setup(
        db_engine,
        setup_id=SETUP_A2,
        user_id=USER_A,
        character_id=CHAR_A1,
        name="Old inn",
        archived_at=ARCHIVED_AT,
    )
    _insert_setup(db_engine, setup_id=SETUP_B1, user_id=USER_B, character_id=CHAR_B1, name="Road")

    # `SESSION_A1` carries a setup and the non-null designated-model pair; `SESSION_A2` is
    # archived with `setup_id` null, which is DoD-6's null-reference case, and both it and
    # `SESSION_B1` leave `model_server_id` / `model_name` NULL.
    _insert_session(
        db_engine,
        session_id=SESSION_A1,
        user_id=USER_A,
        character_id=CHAR_A1,
        setup_id=SETUP_A1,
        model_server_id=SERVER_ID,
    )
    _insert_session(db_engine, session_id=SESSION_A2, user_id=USER_A, character_id=CHAR_A1)
    _archive_session(db_engine, SESSION_A2)
    _insert_session(db_engine, session_id=SESSION_B1, user_id=USER_B, character_id=CHAR_B1)

    # Three zone rows, settled: the head keeps `settled_at`, the two earlier rows become
    # buried with `related_to` set to the head (`002.context.md` "Seeding buried messages").
    for message_id, text in ((ZONE_1, "First draft."), (ZONE_2, "Second draft."), (ZONE_3, "Head.")):
        _insert_message(
            db_engine, message_id=message_id, user_id=USER_A, session_id=SESSION_A1, text=text
        )
    with db_engine.connect() as connection:
        settle(connection, USER_A, SESSION_A1)

    # One current-zone row and one born-settled partner row, after the settle.
    _insert_message(
        db_engine, message_id=ZONE_4, user_id=USER_A, session_id=SESSION_A1, text="Still drafting."
    )
    _insert_message(
        db_engine,
        message_id=PARTNER_1,
        user_id=USER_A,
        session_id=SESSION_A1,
        text="The partner replied.",
        role="assistant",
        kind="partner",
        settled_at=SEEDED_SETTLED_AT,
    )
    _insert_message(
        db_engine,
        message_id=MESSAGE_A2,
        user_id=USER_A,
        session_id=SESSION_A2,
        text="In the archived session.",
    )
    _insert_message(
        db_engine, message_id=MESSAGE_B1, user_id=USER_B, session_id=SESSION_B1, text="Bob's line."
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
        body=NON_ASCII_BODY,
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
        body="This session only.",
    )
    _insert_memo(
        db_engine, memo_id=MEMO_B, user_id=USER_B, scope="user", scope_id=USER_B, body="Bob's memo."
    )

    _insert(
        db_engine,
        _table("auth_sessions"),
        id=AUTH_SESSION_ID,
        user_id=USER_A,
        token_hash="a-live-login-token-hash",
        created_at=TIMESTAMP,
        expires_at=EXPIRES_AT,
        revoked_at=None,
    )
    _insert(
        db_engine,
        _table("translations"),
        id=TRANSLATION_ID,
        user_id=USER_A,
        message_id=ZONE_3,
        target_language="Russian",
        text="Переведённый текст.",
        created_at=TIMESTAMP,
    )
    return db_engine


def _database_envelope(engine: Engine) -> dict[str, Any]:
    with engine.connect() as connection:
        return dict(export_database(connection))


def _payload(engine: Engine) -> dict[str, list[dict[str, Any]]]:
    payload = _database_envelope(engine)["payload"]
    assert isinstance(payload, dict)
    return payload


# =====================================================================================
# DoD-1 — the envelope header
# =====================================================================================


def test_database_envelope_has_exactly_the_six_envelope_keys__S030_001_DoD1(
    engine: Engine,
) -> None:
    """DoD-1 / `context.md` §"The envelope" — six keys, no more and no fewer."""
    envelope = _database_envelope(engine)
    assert set(envelope) == {
        "format",
        "version",
        "granularity",
        "created_at",
        "schema_version",
        "payload",
    }


def test_database_envelope_header_carries_the_declared_values__S030_001_DoD1(
    engine: Engine,
) -> None:
    """DoD-1 — `format` is the literal, `granularity` is `"database"`, and the two
    version fields are integers equal to the module's two separate constants."""
    envelope = _database_envelope(engine)
    assert envelope["format"] == "rphelper-export"
    assert envelope["format"] == EXPORT_FORMAT
    assert envelope["granularity"] == "database"
    # `bool` is a subclass of `int`, so the type is checked exactly.
    assert type(envelope["version"]) is int
    assert type(envelope["schema_version"]) is int
    assert envelope["version"] == ENVELOPE_VERSION == 1
    assert envelope["schema_version"] == SCHEMA_VERSION == 1


def test_database_envelope_created_at_is_utc_iso_8601_text__S030_001_DoD1(
    engine: Engine,
) -> None:
    """DoD-1 — `created_at` is text that parses as an ISO-8601 instant at UTC."""
    created_at = _database_envelope(engine)["created_at"]
    assert isinstance(created_at, str)
    parsed = datetime.fromisoformat(created_at)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() is not None
    assert parsed.utcoffset().total_seconds() == 0  # type: ignore[union-attr]


# =====================================================================================
# DoD-2 / DoD-3 / DoD-4 — which tables appear
# =====================================================================================


def test_database_payload_keys_are_sorted_tables_minus_the_exclusions__S030_001_DoD2(
    engine: Engine,
) -> None:
    """DoD-2 — the keys are `sorted_tables` minus `auth_sessions` and `translations`, in
    `sorted_tables` order.

    Decision 4: `sorted_tables` is a topological sort, so the expected sequence is
    computed from the registry rather than written out. The exclusion constant is pinned
    to the two names the DoD states.
    """
    assert DATABASE_EXCLUDED_TABLES == frozenset(EXCLUDED_TABLE_NAMES)
    assert list(_payload(engine)) == _expected_database_table_order()


def test_live_auth_session_and_translation_rows_are_not_exported__S030_001_DoD3(
    engine: Engine,
) -> None:
    """DoD-3 — with both rows present in the database, neither key is in the payload."""
    assert _stored_rows(engine, _table("auth_sessions")) != {}
    assert _stored_rows(engine, _table("translations")) != {}
    payload = _payload(engine)
    assert "auth_sessions" not in payload
    assert "translations" not in payload


def test_no_payload_key_names_a_table_outside_the_registry__S030_001_DoD4(
    engine: Engine,
) -> None:
    """DoD-4 — every key is a table in `schema.metadata.tables`."""
    assert set(_payload(engine)) <= set(schema.metadata.tables)


def test_no_fts_or_vector_table_appears_in_the_payload__S030_001_DoD4(engine: Engine) -> None:
    """DoD-4, as corrected by decision 6 — the real 024 tables are `memo_fts`,
    `message_fts`, `memo_vec` and `session_vec` (there is no `session_fts`); none of them
    is exported, which is what shows vectors are not exported."""
    payload = _payload(engine)
    for name in SEARCH_TABLE_NAMES:
        assert name not in schema.metadata.tables
        assert name not in payload


# =====================================================================================
# DoD-5 — every row, every column
# =====================================================================================


def test_every_seeded_row_of_every_included_table_appears__S030_001_DoD5(
    engine: Engine,
) -> None:
    """DoD-5 — for each included table the exported primary keys are exactly the stored
    ones, which covers both users' rows, the archived character / setup / session and the
    buried messages."""
    payload = _payload(engine)
    for name, rows in payload.items():
        table = _table(name)
        key = _primary_key_name(table)
        exported = {int(row[key]) for row in rows}  # type: ignore[arg-type]
        assert exported == set(_stored_rows(engine, table)), name

    # The rows that would be lost to an owner filter, an archive filter or a zone view.
    assert {USER_A, USER_B} <= {int(row["id"]) for row in payload["users"]}  # type: ignore[arg-type]
    assert CHAR_A2 in {int(row["id"]) for row in payload["characters"]}  # type: ignore[arg-type]
    assert SETUP_A2 in {int(row["id"]) for row in payload["setups"]}  # type: ignore[arg-type]
    assert SESSION_A2 in {int(row["id"]) for row in payload["sessions"]}  # type: ignore[arg-type]
    message_ids = {int(row["id"]) for row in payload["messages"]}  # type: ignore[arg-type]
    assert {ZONE_1, ZONE_2, ZONE_3, ZONE_4, PARTNER_1, MESSAGE_A2, MESSAGE_B1} <= message_ids


def test_every_row_object_carries_every_column_the_table_declares__S030_001_DoD5(
    engine: Engine,
) -> None:
    """DoD-5 — no granularity-level column exclusion applies at database granularity, so
    each row's keys are exactly the Table's column names."""
    for name, rows in _payload(engine).items():
        declared = {column.name for column in _table(name).columns}
        assert rows != [], name
        for row in rows:
            assert set(row) == declared, name


# =====================================================================================
# DoD-6 — id columns become decimal strings
# =====================================================================================


def test_every_id_column_is_the_stored_integer_as_a_decimal_string__S030_001_DoD6(
    engine: Engine,
) -> None:
    """DoD-6 — primary keys, foreign keys and `_id`-suffixed integers are decimal-digit
    strings whose integer value equals the stored one; a null reference stays null."""
    for name, rows in _payload(engine).items():
        table = _table(name)
        key = _primary_key_name(table)
        stored = _stored_rows(engine, table)
        for row in rows:
            source = stored[int(row[key])]  # type: ignore[arg-type]
            for column in table.columns:
                if not _is_id_column(column):
                    continue
                value = row[column.name]
                expected = source[column.name]
                if expected is None:
                    assert value is None, f"{name}.{column.name}"
                    continue
                assert type(value) is str, f"{name}.{column.name}"
                assert value.isdigit(), f"{name}.{column.name}"
                assert int(value) == int(expected), f"{name}.{column.name}"


def test_null_references_stay_null__S030_001_DoD6(engine: Engine) -> None:
    """DoD-6 — the seeded nulls: an archived session's `setup_id`, a current-zone
    message's `related_to`, and a character without a designated server."""
    payload = _payload(engine)
    sessions = {int(row["id"]): row for row in payload["sessions"]}  # type: ignore[arg-type]
    messages = {int(row["id"]): row for row in payload["messages"]}  # type: ignore[arg-type]
    characters = {int(row["id"]): row for row in payload["characters"]}  # type: ignore[arg-type]
    assert sessions[SESSION_A2]["setup_id"] is None
    assert messages[ZONE_4]["related_to"] is None
    assert characters[CHAR_A2]["model_server_id"] is None


def test_fk_less_and_fk_only_references_are_decimal_strings__S030_001_DoD6(
    engine: Engine,
) -> None:
    """DoD-6, with decision 8's two extra facts — `memos.scope_id` and
    `model_server_id` on **both** `characters` and `sessions` are caught by the name arm,
    while `messages.related_to` (a self-FK whose name does not end in `_id`) is caught
    only by the foreign-key arm. The buried rows carry it."""
    payload = _payload(engine)
    characters = {int(row["id"]): row for row in payload["characters"]}  # type: ignore[arg-type]
    sessions = {int(row["id"]): row for row in payload["sessions"]}  # type: ignore[arg-type]
    memos = {int(row["id"]): row for row in payload["memos"]}  # type: ignore[arg-type]
    messages = {int(row["id"]): row for row in payload["messages"]}  # type: ignore[arg-type]

    assert characters[CHAR_A1]["model_server_id"] == str(SERVER_ID)
    assert sessions[SESSION_A1]["model_server_id"] == str(SERVER_ID)
    assert memos[MEMO_CHARACTER]["scope_id"] == str(CHAR_A1)
    assert memos[MEMO_SESSION]["scope_id"] == str(SESSION_A1)

    buried = [
        row
        for message_id, row in messages.items()
        if message_id in {ZONE_1, ZONE_2} and row["related_to"] is not None
    ]
    assert buried != [], "settling a three-row zone must leave buried rows behind"
    for row in buried:
        related = row["related_to"]
        assert type(related) is str
        assert related.isdigit()
        assert int(related) in messages


# =====================================================================================
# DoD-7 — booleans, enums, timestamps and non-id integers
# =====================================================================================


def test_booleans_scope_text_and_timestamps_serialize_plainly__S030_001_DoD7(
    engine: Engine,
) -> None:
    """DoD-7 — boolean columns are JSON `true`/`false`, `memos.scope` is its string value
    (decision 5: it arrives as a plain `str`), and a timestamp is the stored text."""
    payload = _payload(engine)
    memos = {int(row["id"]): row for row in payload["memos"]}  # type: ignore[arg-type]
    users = {int(row["id"]): row for row in payload["users"]}  # type: ignore[arg-type]

    assert memos[MEMO_CHARACTER]["is_enabled"] is True
    assert memos[MEMO_CHARACTER]["is_forced"] is True
    assert memos[MEMO_SETUP]["is_enabled"] is False
    assert users[USER_A]["is_enabled"] is True

    assert memos[MEMO_USER]["scope"] == "user"
    assert memos[MEMO_CHARACTER]["scope"] == "character"
    assert memos[MEMO_SETUP]["scope"] == "setup"
    assert memos[MEMO_SESSION]["scope"] == "session"

    assert memos[MEMO_USER]["created_at"] == TIMESTAMP
    assert memos[MEMO_USER]["updated_at"] == TIMESTAMP
    messages = {int(row["id"]): row for row in payload["messages"]}  # type: ignore[arg-type]
    assert messages[PARTNER_1]["settled_at"] == SEEDED_SETTLED_AT
    assert messages[ZONE_4]["settled_at"] is None


def test_non_id_integer_columns_stay_json_numbers__S030_001_DoD7(engine: Engine) -> None:
    """DoD-7 — `models.embedding_dim` stays a number, and so does `memos.sort_key`
    (decision 8: neither is an id)."""
    payload = _payload(engine)
    models = {int(row["id"]): row for row in payload["models"]}  # type: ignore[arg-type]
    memos = {int(row["id"]): row for row in payload["memos"]}  # type: ignore[arg-type]
    assert type(models[MODEL_ID]["embedding_dim"]) is int
    assert models[MODEL_ID]["embedding_dim"] == 8
    assert type(memos[MEMO_CHARACTER]["sort_key"]) is int
    assert memos[MEMO_CHARACTER]["sort_key"] == 200


def test_the_users_role_enum_becomes_a_plain_string__S030_001_DoD7(engine: Engine) -> None:
    """DoD-7's enum arm, relocated by decision 5 — `users.role` is the one column that
    arrives as an enum member, and it appears only at database granularity. The serialized
    value is a plain `str` carrying the enum's string value, not the member itself."""
    users = {int(row["id"]): row for row in _payload(engine)["users"]}  # type: ignore[arg-type]
    for user_id, expected in ((USER_A, Role.ROLEPLAYER), (USER_B, Role.ADMIN)):
        value = users[user_id]["role"]
        assert type(value) is str, "an enum member must be converted, not passed through"
        assert value == expected.value


# =====================================================================================
# DoD-8 — credentials are carried as stored and never resolved
# =====================================================================================


def test_password_hash_and_api_key_ref_are_carried_as_stored__S030_001_DoD8(
    engine: Engine,
) -> None:
    """DoD-8 — database granularity keeps `users.password_hash` with its stored value and
    `llm_servers.api_key_ref` as the stored `"$NAME"` pointer."""
    payload = _payload(engine)
    users = {int(row["id"]): row for row in payload["users"]}  # type: ignore[arg-type]
    servers = {int(row["id"]): row for row in payload["llm_servers"]}  # type: ignore[arg-type]
    assert users[USER_A]["password_hash"] == PASSWORD_HASH
    assert users[USER_B]["password_hash"] == PASSWORD_HASH
    assert servers[SERVER_ID]["api_key_ref"] == API_KEY_REF


def test_no_resolved_secret_value_appears_in_the_encoded_bytes__S030_001_DoD8(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-8 / `context.md` §"Credentials" — with the environment variable the pointer
    names set to a sentinel, the sentinel appears nowhere in the encoded export. The
    pointer itself is still there, so the test cannot pass by exporting nothing."""
    monkeypatch.setenv(SECRET_VARIABLE, SECRET_SENTINEL)
    blob = encode_envelope(_database_envelope(engine))  # type: ignore[arg-type]
    assert SECRET_SENTINEL.encode("utf-8") not in blob
    assert SECRET_SENTINEL not in blob.decode("utf-8")
    assert API_KEY_REF in blob.decode("utf-8")


# =====================================================================================
# DoD-9 — row order
# =====================================================================================


def test_rows_within_each_table_are_in_ascending_primary_key_order__S030_001_DoD9(
    engine: Engine,
) -> None:
    """DoD-9 / `context.md` §"Row serialization rules" — ordered by primary key."""
    for name, rows in _payload(engine).items():
        key = _primary_key_name(_table(name))
        keys = [int(row[key]) for row in rows]  # type: ignore[arg-type]
        assert keys == sorted(keys), name


# =====================================================================================
# DoD-10 — encoding
# =====================================================================================


def test_encoded_bytes_are_utf8_json_that_loads_back_to_the_envelope__S030_001_DoD10(
    engine: Engine,
) -> None:
    """DoD-10 — `encode_envelope` returns UTF-8 bytes that `json.loads` restores."""
    envelope = _database_envelope(engine)
    blob = encode_envelope(envelope)  # type: ignore[arg-type]
    assert isinstance(blob, bytes)
    assert json.loads(blob.decode("utf-8")) == envelope


def test_non_ascii_row_text_round_trips_unchanged__S030_001_DoD10(engine: Engine) -> None:
    """DoD-10 — a memo body with Cyrillic, diacritics, a symbol and CJK survives the
    round trip character for character."""
    envelope = _database_envelope(engine)
    restored = json.loads(encode_envelope(envelope).decode("utf-8"))  # type: ignore[arg-type]
    bodies = {int(row["id"]): row["body"] for row in restored["payload"]["memos"]}
    assert bodies[MEMO_CHARACTER] == NON_ASCII_BODY


# =====================================================================================
# DoD-11 — the filename
# =====================================================================================


def _filename_envelope() -> dict[str, Any]:
    """An envelope built here, so the filename assertions depend only on `export_filename`.

    `ExportEnvelope` is a `TypedDict`, hence a plain `dict` at runtime (`## Skeleton`).
    """
    return {
        "format": EXPORT_FORMAT,
        "version": ENVELOPE_VERSION,
        "granularity": "database",
        "created_at": "2026-10-05T14:25:30.123456+00:00",
        "schema_version": SCHEMA_VERSION,
        "payload": {"users": [{"id": str(USER_A), "username": FILENAME_PROBE}]},
    }


def test_export_filename_names_the_granularity_and_a_timestamp__S030_001_DoD11() -> None:
    """DoD-11 — `rphelper-<granularity>-<digits/letters timestamp>.json`, derived from the
    envelope's `granularity` and `created_at` alone."""
    name = export_filename(_filename_envelope())  # type: ignore[arg-type]
    assert FILENAME_PATTERN.match(name), name
    assert "database" in name
    assert name.startswith("rphelper-database-")
    assert name.endswith(".json")


def test_export_filename_embeds_no_row_content__S030_001_DoD11() -> None:
    """DoD-11 / `context.md` §Routes — the filename never carries a name, title or id."""
    name = export_filename(_filename_envelope())  # type: ignore[arg-type]
    assert FILENAME_PROBE not in name
    assert str(USER_A) not in name
