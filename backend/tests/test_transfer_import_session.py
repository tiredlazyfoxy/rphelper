"""Tests for `import_session` — feature 031, step 003 (session import into a chosen character).

Every expected value comes from the spec — `docs/plans/031.import-and-id-remapping/
003.session-import.md` (Interface intent + Definition of done), `003.context.md`
(user decision U1, §"Order of checks", §"Memo policy"), the feature `context.md`
(§"Remap rules for the three roleplayer granularities", §"The failure contract",
§"Test conventions") and the `## Skeleton` record's step-003 policy table (ruling 23) —
and from the rows this file seeds itself. Nothing is read from the implementation.

**The only step-003 symbol named here is `import_session`.** The session reference policy
and the target-character lookup are module-private by design, so every behaviour below is
observed through `import_session` and the database it writes; no `_`-prefixed name from
`app.services.transfer_import` is imported or referenced. Step 001 contributes
`ExportInvalidError` and the `REASON_*` constants (**no reason string literal is
re-typed**), and `CharacterNotFoundError` comes from `app.errors`.

The seeding shape `003.context.md` prescribes: a source session lives under character
**X**, is exported with 030's `export_session`, and is imported into character **C** — a
*different* character of the **same** caller, with X still present, which is the only
configuration in which DoD-2 can fail.

How the old-id to new-id correspondence is recovered: imported rows are paired with the
payload rows **by ascending id per table**, which is sound because `context.md` §"Remap
rules" mints per table in ascending order of the old id from a monotonic generator. DoD-1
asserts message *order* independently, on the text sequence and on the three message
states, never on the pairing.

Orchestrator corrections honoured here:

- **decision 13** — `memos.scope` reads back as a plain `str`;
- **decision 14** — `settled_entries`, `current_zone` and `buried_messages` are Core
  `select()` objects, not SQL views, so they are executed directly;
- **harvest E9** — `message_fts` indexes **record rows only**: it skips buried rows as
  well as zone rows;
- `start_session` is **not** reused by the import (`003.context.md`), so nothing here
  models its behaviour.
"""

import copy
from collections.abc import Callable, Collection, Mapping, Sequence
from typing import Any

import pytest
from sqlalchemy import Column, Connection, Engine, Table, func, select, text

from app.db import schema
from app.db.search_tables import (
    MEMO_VEC_TABLE,
    MESSAGE_FTS_TABLE,
    SESSION_VEC_TABLE,
    ensure_vector_tables,
)
from app.errors import (
    REASON_MALFORMED_PAYLOAD,
    REASON_SCHEMA_MISMATCH,
    REASON_WRONG_GRANULARITY,
    CharacterNotFoundError,
    ExportInvalidError,
)
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services.transfer import (
    SCHEMA_VERSION,
    export_character,
    export_session,
    export_user,
)
from app.services.transfer_import import import_session

# --- seeded constants -----------------------------------------------------------------

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
SETTLED_AT = "2025-12-31T00:00:00.000000+00:00"
ARCHIVED_AT = "2026-02-01T00:00:00.000000+00:00"
LAST_USED_AT = "2026-03-03T03:03:03.000000+00:00"
OTHER_LAST_USED_AT = "2026-04-04T04:04:04.000000+00:00"

#: Every seeded id is above `2**60` (`context.md` §"Test conventions").
BASE = 1_152_921_504_606_847_000

USER_A = BASE + 1
USER_B = BASE + 2

SERVER_ID = BASE + 10
MODEL_ID = BASE + 11

#: X — the source session's character. It stays in the account for every import.
CHAR_X = BASE + 20
#: C — the chosen target, a **different** character of the same caller.
CHAR_C = BASE + 21
#: An archived target of the same caller (R6, DoD-4).
CHAR_C_ARCHIVED = BASE + 22
#: Another user's character (R5, DoD-5).
CHAR_B = BASE + 23

SETUP_X = BASE + 30

SESSION_X = BASE + 40
SESSION_X_UNKNOWN_MODEL = BASE + 41
SESSION_B = BASE + 42

#: `messages` of `SESSION_X`: two settled groups, then two zone rows. Each buried row has
#: a **lower** id than its own head (030's outcome note), which is the case the import's
#: two-pass write exists for.
MSG_BURIED_1 = BASE + 50
MSG_HEAD_1 = BASE + 51
MSG_BURIED_2 = BASE + 52
MSG_HEAD_2 = BASE + 53
MSG_ZONE_1 = BASE + 54
MSG_ZONE_2 = BASE + 55
MSG_UNKNOWN_MODEL = BASE + 56
MSG_B = BASE + 57

MEMO_SESSION_1 = BASE + 60
MEMO_SESSION_2 = BASE + 61
MEMO_CHARACTER_X = BASE + 62
MEMO_SETUP_X = BASE + 63
MEMO_USER_A = BASE + 64
MEMO_SESSION_UNKNOWN_MODEL = BASE + 65

#: An id no row carries: DoD-5's nonexistent target, and DoD-6's absent memo target.
SPARE_ID = BASE + 900

PASSWORD_HASH = "not-a-real-hash-but-stored-verbatim"

#: A `(server_id, model_name)` pair that **does** exist in this instance's `models`, so
#: `context.md` §"Remap rules" keeps it (DoD-8, kept case).
MODEL_NAME_KEPT = "seeded-model-one"
#: A pair no `models` row carries, so both halves are nulled (DoD-8, nulled case).
MODEL_NAME_MISSING = "no-such-model"

SYSTEM_PROMPT_X = "Keep every answer in the second person."

# --- FTS tokens (DoD-10): one unique, tokenizable word per message body ---------------

RECORD_TOKEN_1 = "obeliskalpha"
RECORD_TOKEN_2 = "obeliskbeta"
BURIED_TOKEN_1 = "cryptalpha"
BURIED_TOKEN_2 = "cryptbeta"
ZONE_TOKEN_1 = "lanternalpha"
ZONE_TOKEN_2 = "lanternbeta"
ZONE_TOKEN_UNKNOWN_MODEL = "lanterngamma"
ZONE_TOKEN_B = "lanterndelta"

MEMO_TOKENS: dict[int, str] = {
    MEMO_SESSION_1: "zephyrsessionone",
    MEMO_SESSION_2: "zephyrsessiontwo",
    MEMO_CHARACTER_X: "zephyrcharacter",
    MEMO_SETUP_X: "zephyrsetup",
    MEMO_USER_A: "zephyruser",
    MEMO_SESSION_UNKNOWN_MODEL: "zephyrsessionthree",
}

SCOPE_USER = "user"
SCOPE_CHARACTER = "character"
SCOPE_SETUP = "setup"
SCOPE_SESSION = "session"


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
    """Every column preserved verbatim: the whole table **minus** its id columns.

    Derived from `schema.metadata`, never hand-listed, so a column added to the registry
    later is compared without this file changing.
    """
    key_names = _primary_key_names(table)
    return [
        column.name
        for column in table.columns
        if not _spec_is_id_column(column, key_names)
    ]


# --- raw-insert helpers (file-local; `conftest.py` is untouched) ----------------------


def _insert(engine: Engine, table: Table, **values: Any) -> None:
    with engine.begin() as connection:
        connection.execute(table.insert().values(**values))


def _insert_user(engine: Engine, *, user_id: int, username: str) -> None:
    _insert(
        engine,
        schema.users,
        id=user_id,
        username=username,
        password_hash=PASSWORD_HASH,
        role=Role.ROLEPLAYER,
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
        model_server_id=None,
        model_name=None,
        system_prompt=None,
        tool_memo_search=True,
        tool_session_search=False,
        tool_web_search=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_setup(
    engine: Engine, *, setup_id: int, user_id: int, character_id: int, name: str
) -> None:
    _insert(
        engine,
        schema.setups,
        id=setup_id,
        user_id=user_id,
        character_id=character_id,
        name=name,
        description=f"A description of {name}.",
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
    setup_id: int | None,
    model_name: str | None,
    archived_at: str | None,
    last_used_at: str,
    rp_language: str | None,
    preferred_language: str | None,
    system_prompt: str | None,
) -> None:
    # `ck_sessions_model_both_or_neither`: the pair is written together or not at all.
    _insert(
        engine,
        schema.sessions,
        id=session_id,
        user_id=user_id,
        character_id=character_id,
        setup_id=setup_id,
        last_used_at=last_used_at,
        archived_at=archived_at,
        model_server_id=None if model_name is None else SERVER_ID,
        model_name=model_name,
        system_prompt=system_prompt,
        tool_memo_search=False,
        tool_session_search=None,
        tool_web_search=True,
        rp_language=rp_language,
        preferred_language=preferred_language,
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
    """A per-test database seeded in the shape `003.context.md` prescribes.

    User A owns character **X** (which holds the source session, its setup, its six
    messages in three states and its two session memos), the target **C**, and an
    **archived** target. User B owns one character and one session, as the R5 witness.
    One `(server_id, model_name)` pair exists in `models`, so `SESSION_X` keeps its pair
    while `SESSION_X_UNKNOWN_MODEL` must have both halves nulled.

    `conftest.py` is untouched: `db_engine` creates no schema, so the registry is applied
    here and **no FTS and no vec0 table exists when a test starts** (DoD-10's premise).
    """
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)

    _insert_user(db_engine, user_id=USER_A, username="alice")
    _insert_user(db_engine, user_id=USER_B, username="bob")

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
        model_name=MODEL_NAME_KEPT,
        is_enabled=True,
        is_embedding_designated=False,
        embedding_dim=8,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )

    _insert_character(db_engine, character_id=CHAR_X, user_id=USER_A, name="Xenia")
    _insert_character(db_engine, character_id=CHAR_C, user_id=USER_A, name="Cassia")
    _insert_character(
        db_engine,
        character_id=CHAR_C_ARCHIVED,
        user_id=USER_A,
        name="Cordelia",
        archived_at=ARCHIVED_AT,
    )
    _insert_character(db_engine, character_id=CHAR_B, user_id=USER_B, name="Bob's own")

    _insert_setup(
        db_engine, setup_id=SETUP_X, user_id=USER_A, character_id=CHAR_X, name="Inn"
    )

    # The source session: it **has** a setup (so DoD-3 is not vacuous), a non-null
    # `archived_at`, and a distinguishable value in each of DoD-8's five fields.
    _insert_session(
        db_engine,
        session_id=SESSION_X,
        user_id=USER_A,
        character_id=CHAR_X,
        setup_id=SETUP_X,
        model_name=MODEL_NAME_KEPT,
        archived_at=ARCHIVED_AT,
        last_used_at=LAST_USED_AT,
        rp_language="Russian",
        preferred_language="English",
        system_prompt=SYSTEM_PROMPT_X,
    )
    _insert_session(
        db_engine,
        session_id=SESSION_X_UNKNOWN_MODEL,
        user_id=USER_A,
        character_id=CHAR_X,
        setup_id=None,
        model_name=MODEL_NAME_MISSING,
        archived_at=None,
        last_used_at=OTHER_LAST_USED_AT,
        rp_language=None,
        preferred_language="German",
        system_prompt=None,
    )
    _insert_session(
        db_engine,
        session_id=SESSION_B,
        user_id=USER_B,
        character_id=CHAR_B,
        setup_id=None,
        model_name=None,
        archived_at=None,
        last_used_at=LAST_USED_AT,
        rp_language=None,
        preferred_language=None,
        system_prompt=None,
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
            session_id=SESSION_X,
            token=token,
            role=role,
            kind=kind,
            settled_at=settled_at,
        )
    _bury(db_engine, message_id=MSG_BURIED_1, head_id=MSG_HEAD_1)
    _bury(db_engine, message_id=MSG_BURIED_2, head_id=MSG_HEAD_2)

    _insert_message(
        db_engine,
        message_id=MSG_UNKNOWN_MODEL,
        user_id=USER_A,
        session_id=SESSION_X_UNKNOWN_MODEL,
        token=ZONE_TOKEN_UNKNOWN_MODEL,
    )
    _insert_message(
        db_engine,
        message_id=MSG_B,
        user_id=USER_B,
        session_id=SESSION_B,
        token=ZONE_TOKEN_B,
    )

    _insert_memo(
        db_engine,
        memo_id=MEMO_SESSION_1,
        user_id=USER_A,
        scope=SCOPE_SESSION,
        scope_id=SESSION_X,
        sort_key=100,
    )
    _insert_memo(
        db_engine,
        memo_id=MEMO_SESSION_2,
        user_id=USER_A,
        scope=SCOPE_SESSION,
        scope_id=SESSION_X,
        is_enabled=False,
        is_forced=True,
        sort_key=200,
    )
    # Memos of X that a session export never carries. They are DoD-2's witnesses.
    _insert_memo(
        db_engine,
        memo_id=MEMO_CHARACTER_X,
        user_id=USER_A,
        scope=SCOPE_CHARACTER,
        scope_id=CHAR_X,
    )
    _insert_memo(
        db_engine,
        memo_id=MEMO_SETUP_X,
        user_id=USER_A,
        scope=SCOPE_SETUP,
        scope_id=SETUP_X,
    )
    _insert_memo(
        db_engine, memo_id=MEMO_USER_A, user_id=USER_A, scope=SCOPE_USER, scope_id=USER_A
    )
    _insert_memo(
        db_engine,
        memo_id=MEMO_SESSION_UNKNOWN_MODEL,
        user_id=USER_A,
        scope=SCOPE_SESSION,
        scope_id=SESSION_X_UNKNOWN_MODEL,
    )
    return db_engine


# --- envelope helpers (every body starts life as 030's own export) --------------------

Payload = dict[str, list[dict[str, Any]]]


def _session_envelope(engine: Engine, session_id: int = SESSION_X) -> dict[str, Any]:
    with engine.connect() as connection:
        return copy.deepcopy(dict(export_session(connection, USER_A, session_id)))


def _user_envelope(engine: Engine) -> dict[str, Any]:
    with engine.connect() as connection:
        return copy.deepcopy(dict(export_user(connection, USER_A)))


def _character_envelope(engine: Engine) -> dict[str, Any]:
    with engine.connect() as connection:
        return copy.deepcopy(dict(export_character(connection, USER_A, CHAR_X)))


def _payload(envelope: Mapping[str, Any]) -> Payload:
    payload = envelope["payload"]
    assert isinstance(payload, dict)
    return payload


def _rows(envelope: Mapping[str, Any], table_name: str) -> list[dict[str, Any]]:
    """The payload rows of one table, ascending by id — 030 serializes ids as strings."""
    return sorted(_payload(envelope)[table_name], key=lambda row: int(str(row["id"])))


def _only_session_row(envelope: Mapping[str, Any]) -> dict[str, Any]:
    rows = _rows(envelope, schema.sessions.name)
    assert len(rows) == 1, "a session envelope carries exactly one `sessions` row"
    return rows[0]


# --- running the import ---------------------------------------------------------------


def _import(
    engine: Engine,
    user_id: int,
    character_id: int,
    body: Mapping[str, Any],
    generator: SnowflakeGenerator | None = None,
) -> int:
    """`import_session(connection, generator, user_id, character_id, body)` on a connection
    that is not already in a transaction, so its own `with connection.begin():` commits.

    A **real** `SnowflakeGenerator` (no monkeypatching, `context.md` §"Test conventions").
    """
    with engine.connect() as connection:
        return import_session(
            connection,
            generator or SnowflakeGenerator(node_id=0),
            user_id,
            character_id,
            body,
        )


# --- observation (tests may read the database and the search tables directly) ----------


def _ids(engine: Engine, table: Table) -> set[int]:
    with engine.connect() as connection:
        return {
            int(value) for value in connection.execute(select(table.c.id)).scalars().all()
        }


def _row_counts(engine: Engine) -> dict[str, int]:
    """The row count of **every** `schema.metadata.sorted_tables` table — the "stores
    nothing" measure DoD-5, DoD-6 and DoD-9 pair their refusals with."""
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


def _stored_row(engine: Engine, table: Table, row_id: int) -> dict[str, Any]:
    stored = _stored_rows(engine, table)
    assert row_id in stored, f"{table.name} has no row with id {row_id}"
    return stored[row_id]


def _session_messages(engine: Engine, session_id: int) -> list[dict[str, Any]]:
    """Every message of one session, ascending by id."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(schema.messages)
            .where(schema.messages.c.session_id == session_id)
            .order_by(schema.messages.c.id)
        ).all()
    return [dict(row._mapping) for row in rows]


def _session_memos(engine: Engine, session_id: int) -> list[dict[str, Any]]:
    """Every `scope='session'` memo of one session, ascending by id."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(schema.memos)
            .where(
                schema.memos.c.scope == SCOPE_SESSION,
                schema.memos.c.scope_id == session_id,
            )
            .order_by(schema.memos.c.id)
        ).all()
    return [dict(row._mapping) for row in rows]


def _sessions_of_character(engine: Engine, character_id: int) -> set[int]:
    with engine.connect() as connection:
        return {
            int(value)
            for value in connection.execute(
                select(schema.sessions.c.id).where(
                    schema.sessions.c.character_id == character_id
                )
            )
            .scalars()
            .all()
        }


def _selectable_texts(engine: Engine, selectable: Any, session_id: int) -> set[str]:
    """The `text` values a Core selectable returns for one session (decision 14: these are
    `select()` objects, not SQL views, so a test executes them directly)."""
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


def _text_of(token: str) -> str:
    """The body `_insert_message` writes for a token."""
    return f"{token} spoken aloud."


def _pairing(
    old_rows: Sequence[Mapping[str, Any]], new_rows: Sequence[Mapping[str, Any]]
) -> dict[int, int]:
    """Old id to new id, by ascending id per table (`context.md` §"Remap rules" mints in
    ascending order of the old id from a monotonic generator)."""
    old = sorted(int(str(row["id"])) for row in old_rows)
    new = sorted(int(row["id"]) for row in new_rows)
    assert len(old) == len(new), f"expected {len(old)} imported rows, found {len(new)}"
    return dict(zip(old, new, strict=True))


def _assert_preserved(
    table: Table, old_row: Mapping[str, Any], new_row: Mapping[str, Any]
) -> None:
    """`context.md` §"Remap rules": every non-id column is preserved as exported."""
    for name in _value_columns(table):
        assert new_row[name] == old_row[name], f"{table.name}.{name} must be preserved"


def _assert_refusal(reason: str, call: Callable[[], object]) -> None:
    """A refusal is anchored on the **specific** error and its exact `detail`, so the
    skeleton's `NotImplementedError` cannot satisfy it."""
    with pytest.raises(ExportInvalidError) as caught:
        call()
    assert caught.value.reason == reason
    assert caught.value.detail == {"reason": reason}


# --- DoD-1: the whole session comes across ---------------------------------------------


def test_import_creates_one_session_with_every_message__S031_003_DoD1(
    engine: Engine,
) -> None:
    """DoD-1 — exactly one new session, under C, owned by the caller, carrying all six
    messages (settled, buried and current-zone) in the same order, with its session-scoped
    memos re-pointed at the new session id (UC-064)."""
    envelope = _session_envelope(engine)
    payload_messages = _rows(envelope, schema.messages.name)
    payload_memos = _rows(envelope, schema.memos.name)
    assert len(payload_messages) == 6, "the source session has six messages"
    assert len(payload_memos) == 2, "the source session has two session-scoped memos"
    sessions_before = _ids(engine, schema.sessions)

    new_id = _import(engine, USER_A, CHAR_C, envelope)

    sessions_after = _ids(engine, schema.sessions)
    assert sessions_after - sessions_before == {new_id}, "exactly one new session"
    new_session = _stored_row(engine, schema.sessions, new_id)
    assert new_session["character_id"] == CHAR_C
    assert new_session["user_id"] == USER_A

    # Every message, in the same order, with its references rewritten.
    new_messages = _session_messages(engine, new_id)
    assert [str(row["text"]) for row in new_messages] == [
        str(row["text"]) for row in payload_messages
    ], "the messages keep their order"
    correspondence = _pairing(payload_messages, new_messages)
    for old_row, new_row in zip(payload_messages, new_messages, strict=True):
        _assert_preserved(schema.messages, old_row, new_row)
        assert new_row["user_id"] == USER_A
        assert new_row["session_id"] == new_id
        old_related = old_row["related_to"]
        if old_related is None:
            assert new_row["related_to"] is None
        else:
            assert new_row["related_to"] == correspondence[int(str(old_related))]

    # All three message states are present under the new session.
    assert _selectable_texts(engine, schema.settled_entries, new_id) == {
        _text_of(RECORD_TOKEN_1),
        _text_of(RECORD_TOKEN_2),
    }
    assert _selectable_texts(engine, schema.buried_messages, new_id) == {
        _text_of(BURIED_TOKEN_1),
        _text_of(BURIED_TOKEN_2),
    }
    assert _selectable_texts(engine, schema.current_zone, new_id) == {
        _text_of(ZONE_TOKEN_1),
        _text_of(ZONE_TOKEN_2),
    }

    # The session memos, re-pointed at the new session id.
    new_memos = _session_memos(engine, new_id)
    assert len(new_memos) == len(payload_memos)
    for old_row, new_row in zip(payload_memos, new_memos, strict=True):
        _assert_preserved(schema.memos, old_row, new_row)
        assert new_row["user_id"] == USER_A
        assert new_row["scope"] == SCOPE_SESSION
        assert new_row["scope_id"] == new_id


def test_import_returns_the_new_session_id__S031_003_DoD1(engine: Engine) -> None:
    """DoD-1 — `import_session` returns the id of the session it created."""
    sessions_before = _ids(engine, schema.sessions)

    new_id = _import(engine, USER_A, CHAR_C, _session_envelope(engine))

    assert new_id not in sessions_before
    assert _ids(engine, schema.sessions) - sessions_before == {new_id}


# --- DoD-2: the target character wins over the exported one ---------------------------


def test_imported_session_belongs_to_the_chosen_character__S031_003_DoD2(
    engine: Engine,
) -> None:
    """DoD-2 — the new session's `character_id` is C, not the exported session's, while X
    still exists in the same account; and X gains no session and no memo (US-082.AC-1)."""
    envelope = _session_envelope(engine)
    assert _only_session_row(envelope)["character_id"] == str(CHAR_X)
    # X is still in the account: this is the only configuration DoD-2 can fail in.
    assert _stored_row(engine, schema.characters, CHAR_X)["user_id"] == USER_A
    sessions_of_x_before = _sessions_of_character(engine, CHAR_X)
    assert sessions_of_x_before, "X owns sessions before the import"
    memos_before = _ids(engine, schema.memos)
    assert memos_before, "memos exist before the import"

    new_id = _import(engine, USER_A, CHAR_C, envelope)

    new_session = _stored_row(engine, schema.sessions, new_id)
    assert new_session["character_id"] == CHAR_C
    assert new_session["character_id"] != CHAR_X

    assert _sessions_of_character(engine, CHAR_X) == sessions_of_x_before, (
        "X gains no session"
    )
    new_memos = _ids(engine, schema.memos) - memos_before
    stored_memos = _stored_rows(engine, schema.memos)
    for memo_id in new_memos:
        assert stored_memos[memo_id]["scope"] == SCOPE_SESSION
        assert stored_memos[memo_id]["scope_id"] == new_id, "X gains no memo"


# --- DoD-3: no setup comes along ------------------------------------------------------


def test_imported_session_has_no_setup__S031_003_DoD3(engine: Engine) -> None:
    """DoD-3 — `setup_id` is null even though the exported session had a setup; no setup
    row and no setup-scoped memo is created (US-082.AC-2)."""
    envelope = _session_envelope(engine)
    assert _only_session_row(envelope)["setup_id"] == str(SETUP_X), (
        "the exported session must have a setup, or the clause is vacuous"
    )
    setups_before = _ids(engine, schema.setups)
    memos_before = _ids(engine, schema.memos)

    new_id = _import(engine, USER_A, CHAR_C, envelope)

    assert _stored_row(engine, schema.sessions, new_id)["setup_id"] is None
    assert _ids(engine, schema.setups) == setups_before, "no setup row is created"
    stored_memos = _stored_rows(engine, schema.memos)
    for memo_id in _ids(engine, schema.memos) - memos_before:
        assert stored_memos[memo_id]["scope"] != SCOPE_SETUP, (
            "no setup-scoped memo is created"
        )


# --- DoD-4: an archived target is allowed (R6) ----------------------------------------


def test_archived_target_character_accepts_the_import__S031_003_DoD4(
    engine: Engine,
) -> None:
    """DoD-4 — the target may be archived; the import succeeds and the session lands under
    it (R6)."""
    assert _stored_row(engine, schema.characters, CHAR_C_ARCHIVED)["archived_at"] == (
        ARCHIVED_AT
    ), "the target is archived before the import"
    sessions_before = _ids(engine, schema.sessions)

    new_id = _import(engine, USER_A, CHAR_C_ARCHIVED, _session_envelope(engine))

    assert _ids(engine, schema.sessions) - sessions_before == {new_id}
    assert _stored_row(engine, schema.sessions, new_id)["character_id"] == (
        CHAR_C_ARCHIVED
    )
    assert _stored_row(engine, schema.characters, CHAR_C_ARCHIVED)["archived_at"] == (
        ARCHIVED_AT
    ), "the target is still archived"


# --- DoD-5: a foreign or missing target is `character_not_found` (R5) -----------------


@pytest.mark.parametrize(
    ("case", "target"),
    [("foreign", CHAR_B), ("missing", SPARE_ID)],
)
def test_foreign_or_missing_target_is_refused__S031_003_DoD5(
    engine: Engine, case: str, target: int
) -> None:
    """DoD-5 — a target owned by another user, and a nonexistent character id, each raise
    `CharacterNotFoundError` and store nothing in any `metadata` table (R5)."""
    envelope = _session_envelope(engine)
    counts_before = _row_counts(engine)

    with pytest.raises(CharacterNotFoundError) as caught:
        _import(engine, USER_A, target, envelope)

    assert caught.value.code == "character_not_found"
    assert caught.value.http_status == 404
    assert _row_counts(engine) == counts_before, f"the {case} target stored something"


def test_foreign_and_missing_targets_are_indistinguishable__S031_003_DoD5(
    engine: Engine,
) -> None:
    """DoD-5 / R5 — no 403, and no leak of whether the character exists: both cases
    produce the very same error, with an empty `detail`."""
    envelope = _session_envelope(engine)
    assert _stored_row(engine, schema.characters, CHAR_B)["user_id"] == USER_B, (
        "the foreign target exists and belongs to another user"
    )
    assert SPARE_ID not in _ids(engine, schema.characters), (
        "the missing target exists nowhere"
    )

    with pytest.raises(CharacterNotFoundError) as foreign:
        _import(engine, USER_A, CHAR_B, envelope)
    with pytest.raises(CharacterNotFoundError) as missing:
        _import(engine, USER_A, SPARE_ID, envelope)

    assert type(foreign.value) is type(missing.value)
    assert foreign.value.code == missing.value.code
    assert foreign.value.http_status == missing.value.http_status
    assert foreign.value.detail == missing.value.detail == {}
    assert str(foreign.value) == str(missing.value)


# --- DoD-6: only `session` memos of the payload session are allowed -------------------


@pytest.mark.parametrize(
    ("case", "scope", "scope_id"),
    [
        ("character scope", SCOPE_CHARACTER, CHAR_X),
        ("setup scope", SCOPE_SETUP, SETUP_X),
        ("user scope", SCOPE_USER, USER_A),
        ("another session", SCOPE_SESSION, SPARE_ID),
    ],
)
def test_a_memo_outside_the_session_scope_is_malformed__S031_003_DoD6(
    engine: Engine, case: str, scope: str, scope_id: int
) -> None:
    """DoD-6 — a memo with scope `character`, `setup` or `user`, or a `session` memo whose
    `scope_id` is not the payload session's id, gives `malformed_payload` and stores
    nothing (`003.context.md` §"Memo policy")."""
    envelope = _session_envelope(engine)
    memos = _payload(envelope)[schema.memos.name]
    assert memos, "the payload carries a memo to corrupt"
    memos[0]["scope"] = scope
    memos[0]["scope_id"] = str(scope_id)
    counts_before = _row_counts(engine)

    _assert_refusal(
        REASON_MALFORMED_PAYLOAD, lambda: _import(engine, USER_A, CHAR_C, envelope)
    )

    assert _row_counts(engine) == counts_before, f"the {case} case stored something"


# --- DoD-7: importing twice yields two disjoint sessions ------------------------------


def test_importing_the_same_export_twice_is_disjoint__S031_003_DoD7(
    engine: Engine,
) -> None:
    """DoD-7 — two imports of one export give two sessions with disjoint message and memo
    ids, and the original session is untouched (US-136.AC-1, US-136.AC-2).

    One shared `SnowflakeGenerator` across both imports: two generators on the same node
    id can mint equal ids inside a millisecond, which is a harness artefact.
    """
    envelope = _session_envelope(engine)
    original_session = _stored_row(engine, schema.sessions, SESSION_X)
    original_messages = _session_messages(engine, SESSION_X)
    original_memos = _session_memos(engine, SESSION_X)
    assert original_messages and original_memos, "the original session has rows"
    generator = SnowflakeGenerator(node_id=0)

    first = _import(engine, USER_A, CHAR_C, envelope, generator)
    second = _import(engine, USER_A, CHAR_C, envelope, generator)

    assert first != second
    assert first != SESSION_X and second != SESSION_X
    first_messages = {int(row["id"]) for row in _session_messages(engine, first)}
    second_messages = {int(row["id"]) for row in _session_messages(engine, second)}
    assert len(first_messages) == len(original_messages)
    assert len(second_messages) == len(original_messages)
    assert not first_messages & second_messages, "message ids are disjoint"

    first_memos = {int(row["id"]) for row in _session_memos(engine, first)}
    second_memos = {int(row["id"]) for row in _session_memos(engine, second)}
    assert len(first_memos) == len(original_memos)
    assert len(second_memos) == len(original_memos)
    assert not first_memos & second_memos, "memo ids are disjoint"

    assert _stored_row(engine, schema.sessions, SESSION_X) == original_session
    assert _session_messages(engine, SESSION_X) == original_messages
    assert _session_memos(engine, SESSION_X) == original_memos


# --- DoD-8: the preserved fields and the model pair ----------------------------------


def test_imported_session_preserves_its_five_fields__S031_003_DoD8(
    engine: Engine,
) -> None:
    """DoD-8 — `archived_at`, `last_used_at`, `rp_language`, `preferred_language` and
    `system_prompt` are preserved as exported."""
    envelope = _session_envelope(engine)
    exported = _only_session_row(envelope)
    assert exported["archived_at"] is not None, "the source session is archived"

    new_id = _import(engine, USER_A, CHAR_C, envelope)

    stored = _stored_row(engine, schema.sessions, new_id)
    for name in (
        "archived_at",
        "last_used_at",
        "rp_language",
        "preferred_language",
        "system_prompt",
    ):
        assert stored[name] == exported[name], f"sessions.{name} must be preserved"
    assert stored["archived_at"] == ARCHIVED_AT
    assert stored["last_used_at"] == LAST_USED_AT
    assert stored["rp_language"] == "Russian"
    assert stored["preferred_language"] == "English"
    assert stored["system_prompt"] == SYSTEM_PROMPT_X


def test_a_known_model_pair_is_kept__S031_003_DoD8(engine: Engine) -> None:
    """DoD-8 — the model pair follows the shared rule: kept when that `(server_id,
    model_name)` pair exists in this instance's `models` (`context.md` §"Remap rules")."""
    envelope = _session_envelope(engine)
    exported = _only_session_row(envelope)
    assert exported["model_server_id"] == str(SERVER_ID)
    assert exported["model_name"] == MODEL_NAME_KEPT

    new_id = _import(engine, USER_A, CHAR_C, envelope)

    stored = _stored_row(engine, schema.sessions, new_id)
    assert stored["model_server_id"] == SERVER_ID
    assert stored["model_name"] == MODEL_NAME_KEPT


def test_an_unknown_model_pair_is_nulled__S031_003_DoD8(engine: Engine) -> None:
    """DoD-8 — the shared rule's other half: a pair that this instance's `models` does not
    carry is nulled on both halves, honouring the both-or-neither CHECK."""
    envelope = _session_envelope(engine, SESSION_X_UNKNOWN_MODEL)
    exported = _only_session_row(envelope)
    assert exported["model_server_id"] == str(SERVER_ID)
    assert exported["model_name"] == MODEL_NAME_MISSING

    new_id = _import(engine, USER_A, CHAR_C, envelope)

    stored = _stored_row(engine, schema.sessions, new_id)
    assert stored["model_server_id"] is None
    assert stored["model_name"] is None
    # The other preserved fields of this session still come across untouched.
    assert stored["last_used_at"] == OTHER_LAST_USED_AT
    assert stored["preferred_language"] == "German"


# --- DoD-9: the order of checks --------------------------------------------------------


def test_a_user_envelope_is_the_wrong_granularity__S031_003_DoD9(engine: Engine) -> None:
    """DoD-9 — a `user` envelope given to `import_session` raises `wrong_granularity`."""
    envelope = _user_envelope(engine)
    assert envelope["granularity"] == "user"
    counts_before = _row_counts(engine)

    _assert_refusal(
        REASON_WRONG_GRANULARITY, lambda: _import(engine, USER_A, CHAR_C, envelope)
    )

    assert _row_counts(engine) == counts_before


def test_a_character_envelope_is_the_wrong_granularity__S031_003_DoD9(
    engine: Engine,
) -> None:
    """DoD-9 — a `character` envelope given to `import_session` raises
    `wrong_granularity`."""
    envelope = _character_envelope(engine)
    assert envelope["granularity"] == "character"
    counts_before = _row_counts(engine)

    _assert_refusal(
        REASON_WRONG_GRANULARITY, lambda: _import(engine, USER_A, CHAR_C, envelope)
    )

    assert _row_counts(engine) == counts_before


def test_validation_precedes_the_target_lookup__S031_003_DoD9(engine: Engine) -> None:
    """DoD-9 — a well-formed `session` envelope with a wrong `schema_version` raises
    `schema_mismatch` **even for a foreign target**: validation runs before the character
    lookup (`003.context.md` §"Order of checks")."""
    foreign_target = CHAR_B
    # The target really is the one that would otherwise answer `character_not_found`.
    with pytest.raises(CharacterNotFoundError):
        _import(engine, USER_A, foreign_target, _session_envelope(engine))

    mismatched = _session_envelope(engine)
    mismatched["schema_version"] = SCHEMA_VERSION + 1
    counts_before = _row_counts(engine)

    _assert_refusal(
        REASON_SCHEMA_MISMATCH,
        lambda: _import(engine, USER_A, foreign_target, mismatched),
    )

    assert _row_counts(engine) == counts_before


# --- DoD-10: FTS is kept current, vectors are not written (U3) ------------------------


def test_imported_record_text_is_searchable_and_no_vector_row_appears__S031_003_DoD10(
    engine: Engine,
) -> None:
    """DoD-10 — a token from an imported record row is found in `message_fts` under its
    **new** id, and no `session_vec` row exists for the new session (U3).

    The vec0 tables are created *before* the import, so "no row" is measured against
    tables that exist: `context.md` says a roleplayer import never touches them.
    """
    assert not _exists(engine, MESSAGE_FTS_TABLE), (
        "the FTS table does not exist before the import"
    )
    with engine.begin() as connection:
        ensure_vector_tables(connection, 8)
    assert _exists(engine, SESSION_VEC_TABLE)
    assert _vector_row_count(engine, SESSION_VEC_TABLE) == 0

    envelope = _session_envelope(engine)
    payload_messages = _rows(envelope, schema.messages.name)

    new_id = _import(engine, USER_A, CHAR_C, envelope)

    correspondence = _pairing(payload_messages, _session_messages(engine, new_id))
    new_head_1 = correspondence[MSG_HEAD_1]
    new_head_2 = correspondence[MSG_HEAD_2]
    assert new_head_1 in _fts_match_ids(engine, MESSAGE_FTS_TABLE, RECORD_TOKEN_1)
    assert new_head_2 in _fts_match_ids(engine, MESSAGE_FTS_TABLE, RECORD_TOKEN_2)

    # `message_fts` indexes record rows only — it skips buried rows as well as zone rows.
    assert correspondence[MSG_BURIED_1] not in _fts_match_ids(
        engine, MESSAGE_FTS_TABLE, BURIED_TOKEN_1
    )
    assert correspondence[MSG_ZONE_1] not in _fts_match_ids(
        engine, MESSAGE_FTS_TABLE, ZONE_TOKEN_1
    )

    assert _exists(engine, SESSION_VEC_TABLE), "the import drops no vec0 table"
    assert _vector_row_count(engine, SESSION_VEC_TABLE) == 0, (
        "no session_vec row exists for the new session"
    )
    assert _vector_row_count(engine, MEMO_VEC_TABLE) == 0
