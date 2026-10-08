"""Tests for `app/db/search_tables.py` — feature 024, step 001 (DoD-1..7, 9, 10).

Every expected value comes from `docs/plans/024.embedding-lifecycle/001.search-tables.md`
(its Interface intent and Definition of done), from `001.context.md` (the DDL forms, the
**record row predicate** `settled_at IS NOT NULL AND related_to IS NULL`, the trigger set
and the back-fill rule) and from the feature `context.md` (**D2** ensure-on-write and
virtual tables outside `metadata`, **D3** snowflake keys, **D8** the dimension-mismatch
error). Bindings come from `## Skeleton` → "Step 001 — frozen interface" in `status.md`.
Nothing here was derived from the implementation.

Each test name ends `__S024_001_DoD<n>` with the DoD item it covers. DoD-8
(`create_first_administrator` ensures the FTS half) lives in `test_bootstrap_service.py`.

Seeding: a file-local `engine` fixture applies the registry with
`schema.metadata.create_all` and raw-inserts **two users** (owner isolation), a character
and a session each. Every `memos` / `messages` row is a raw insert with an explicitly
chosen id **above 2^60** (`context.md` "Test conventions", D3). `conftest.py` is untouched
and no fixture is shared. The tables are observed only through `MATCH`,
`integrity-check`, point lookups and `sqlite_master` — 024 issues no query of its own.
"""

import struct
from collections.abc import Iterator
from typing import Any

import pytest
import sqlite_vec
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.db import schema
from app.db.search_tables import (
    MEMO_FTS_TABLE,
    MEMO_VEC_TABLE,
    MESSAGE_FTS_TABLE,
    SESSION_VEC_TABLE,
    ensure_fts_tables,
    ensure_vector_tables,
    vector_table_dimension,
)
from app.errors import NoEmbeddingModelError
from app.roles import Role

#: The seeded instant, in the project's fixed-width form.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
#: An instant for rows seeded already settled.
SEEDED_SETTLED_AT = "2025-12-31T00:00:00.000000+00:00"
#: The instant a settle-shaped UPDATE stamps.
SETTLED_AT = "2026-02-01T00:00:00.000000+00:00"

#: Every id is above 2^60 = 1152921504606846976 (D3 / U6: snowflake ids stay the keys).
MIN_SNOWFLAKE_ID = 2**60

USER_A = 1_300_000_000_000_000_001
USER_B = 1_300_000_000_000_000_002
CHAR_A = 1_300_000_000_000_000_011
CHAR_B = 1_300_000_000_000_000_012
SESSION_A = 1_300_000_000_000_000_021
SESSION_B = 1_300_000_000_000_000_022

MEMO_A = 1_300_000_000_000_000_101
MEMO_B = 1_300_000_000_000_000_102
MEMO_C = 1_300_000_000_000_000_103

MESSAGE_RECORD = 1_300_000_000_000_000_201
MESSAGE_ZONE = 1_300_000_000_000_000_202
MESSAGE_BURIED = 1_300_000_000_000_000_203
MESSAGE_PARTNER = 1_300_000_000_000_000_204
MESSAGE_EXTRA = 1_300_000_000_000_000_205

#: Distinct nonsense tokens, so a `MATCH` can only come from the row that carries one.
MEMO_TOKEN_A = "memoalphaxyz"
MEMO_TOKEN_B = "memobetaxyz"
MEMO_TOKEN_NEW = "memogammaxyz"
RECORD_TOKEN = "recordxyz"
ZONE_TOKEN = "zonexyz"
ZONE_TOKEN_EDITED = "zoneeditedxyz"
BURIED_TOKEN = "buriedxyz"
SETTLED_TOKEN = "settledxyz"
SETTLED_TOKEN_EDITED = "settlededitedxyz"
PARTNER_TOKEN = "partnerxyz"
ABSENT_TOKEN = "neverstoredxyz"

#: The designated model's dimension in these tests; 8 keeps them fast (Test conventions).
DIMENSION = 8
OTHER_DIMENSION = 16
VECTOR = [0.5, -1.5, 2.25, 0.0, 1.0, -0.125, 3.5, -2.0]
OTHER_VECTOR = [-0.25, 0.75, 1.5, -3.0, 0.125, 2.0, -1.0, 4.5]

VIRTUAL_TABLES = (MEMO_FTS_TABLE, MESSAGE_FTS_TABLE, MEMO_VEC_TABLE, SESSION_VEC_TABLE)


# --- seeding -------------------------------------------------------------------------


def _apply_registry(engine: Engine) -> None:
    with engine.begin() as connection:
        schema.metadata.create_all(connection)


def _insert_user(engine: Engine, *, user_id: int, username: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.users.insert().values(
                id=user_id,
                username=username,
                password_hash="not-a-real-hash",
                role=Role.ROLEPLAYER,
                is_enabled=True,
                rp_language=None,
                preferred_language=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_character(engine: Engine, *, character_id: int, user_id: int, name: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.characters.insert().values(
                id=character_id,
                user_id=user_id,
                name=name,
                sheet="",
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_session(engine: Engine, *, session_id: int, user_id: int, character_id: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.insert().values(
                id=session_id,
                user_id=user_id,
                character_id=character_id,
                setup_id=None,
                last_used_at=TIMESTAMP,
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_memo_on(
    connection: Connection,
    *,
    memo_id: int,
    body: str,
    user_id: int = USER_A,
    sort_key: int = 0,
    is_enabled: bool = True,
    is_forced: bool = False,
) -> None:
    """Raw-insert one `memos` row (the ten columns of harvest A3) and commit it."""
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
    connection.commit()


def _update_memo_on(connection: Connection, memo_id: int, **values: Any) -> None:
    connection.execute(schema.memos.update().where(schema.memos.c.id == memo_id).values(**values))
    connection.commit()


def _delete_memo_on(connection: Connection, memo_id: int) -> None:
    connection.execute(schema.memos.delete().where(schema.memos.c.id == memo_id))
    connection.commit()


def _insert_message_on(
    connection: Connection,
    *,
    message_id: int,
    body: str,
    user_id: int = USER_A,
    session_id: int = SESSION_A,
    role: str = "user",
    kind: str | None = None,
    related_to: int | None = None,
    settled_at: str | None = None,
) -> None:
    """Raw-insert one `messages` row in a chosen state and commit it."""
    connection.execute(
        schema.messages.insert().values(
            id=message_id,
            user_id=user_id,
            session_id=session_id,
            role=role,
            kind=kind,
            text=body,
            related_to=related_to,
            settled_at=settled_at,
            created_at=TIMESTAMP,
            updated_at=TIMESTAMP,
        )
    )
    connection.commit()


def _update_message_on(connection: Connection, message_id: int, **values: Any) -> None:
    """One UPDATE statement — several columns at once when several are given (DoD-4 case c)."""
    connection.execute(schema.messages.update().where(schema.messages.c.id == message_id).values(**values))
    connection.commit()


def _sentence(token: str) -> str:
    """A body / text carrying exactly one distinguishing token."""
    return f"the material mentions {token} and nothing else distinctive"


@pytest.fixture
def engine(db_engine: Engine) -> Iterator[Engine]:
    """The registry applied, two owners, a character and a session each."""
    _apply_registry(db_engine)
    _insert_user(db_engine, user_id=USER_A, username="alice")
    _insert_user(db_engine, user_id=USER_B, username="bob")
    _insert_character(db_engine, character_id=CHAR_A, user_id=USER_A, name="Aria")
    _insert_character(db_engine, character_id=CHAR_B, user_id=USER_B, name="Brynn")
    _insert_session(db_engine, session_id=SESSION_A, user_id=USER_A, character_id=CHAR_A)
    _insert_session(db_engine, session_id=SESSION_B, user_id=USER_B, character_id=CHAR_B)
    yield db_engine


# --- observation (tests may query the tables; application code never does) -------------


def _catalogue(connection: Connection) -> set[tuple[str, str]]:
    """Every `sqlite_master` table and trigger entry, as (type, name) pairs."""
    rows = connection.exec_driver_sql(
        "SELECT type, name FROM sqlite_master WHERE type IN ('table', 'trigger')"
    ).all()
    return {(str(row[0]), str(row[1])) for row in rows}


def _table_names(connection: Connection) -> set[str]:
    rows = connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type = 'table'").all()
    return {str(row[0]) for row in rows}


def _trigger_names(connection: Connection) -> set[str]:
    rows = connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type = 'trigger'").all()
    return {str(row[0]) for row in rows}


def _match_ids(connection: Connection, table_name: str, token: str) -> list[int]:
    """The rowids a full-text `MATCH` on one token returns, ascending."""
    query = text(f"SELECT rowid FROM {table_name} WHERE {table_name} MATCH :token ORDER BY rowid")
    return [int(row[0]) for row in connection.execute(query, {"token": token}).all()]


def _index_snapshot(connection: Connection, table_name: str, tokens: tuple[str, ...]) -> dict[str, list[int]]:
    """The indexed content, observed as "which ids does each token find"."""
    return {token: _match_ids(connection, table_name, token) for token in tokens}


def _integrity_ok(connection: Connection, table_name: str) -> bool:
    """FTS5's own `integrity-check`; False when the index disagrees with its content table."""
    try:
        connection.exec_driver_sql(f"INSERT INTO {table_name}({table_name}) VALUES('integrity-check')")
    except SQLAlchemyError:
        return False
    return True


def _both_indexes_sound(connection: Connection) -> bool:
    return _integrity_ok(connection, MEMO_FTS_TABLE) and _integrity_ok(connection, MESSAGE_FTS_TABLE)


def _read_vector(connection: Connection, table_name: str, key_column: str, row_id: int) -> list[float] | None:
    """A point lookup by snowflake id, deserialised back into floats."""
    query = text(f"SELECT embedding FROM {table_name} WHERE {key_column} = :row_id")
    blob = connection.execute(query, {"row_id": row_id}).scalar_one_or_none()
    if blob is None:
        return None
    return list(struct.unpack(f"<{DIMENSION}f", blob))


def _write_vector(connection: Connection, table_name: str, key_column: str, row_id: int, vector: list[float]) -> None:
    statement = text(f"INSERT INTO {table_name}({key_column}, embedding) VALUES (:row_id, :blob)")
    connection.execute(statement, {"row_id": row_id, "blob": sqlite_vec.serialize_float32(vector)})
    connection.commit()


# --- DoD-1: the ensure is idempotent ---------------------------------------------------


def test_ensure_creates_both_full_text_tables__S024_001_DoD1(engine: Engine) -> None:
    """DoD-1 — on a fresh `create_all` database a committed ensure leaves both tables present."""
    with engine.begin() as connection:
        ensure_fts_tables(connection)
    with engine.connect() as fresh:
        present = _table_names(fresh)
    assert MEMO_FTS_TABLE in present
    assert MESSAGE_FTS_TABLE in present


def test_a_second_ensure_changes_no_catalogue_entry_and_no_indexed_content__S024_001_DoD1(
    engine: Engine,
) -> None:
    """DoD-1 — a second call raises nothing and leaves the same tables, triggers and content (D2)."""
    tokens = (MEMO_TOKEN_A, MEMO_TOKEN_B, RECORD_TOKEN, ZONE_TOKEN, BURIED_TOKEN, ABSENT_TOKEN)
    with engine.connect() as connection:
        _insert_memo_on(connection, memo_id=MEMO_A, body=_sentence(MEMO_TOKEN_A))
        _insert_memo_on(connection, memo_id=MEMO_B, body=_sentence(MEMO_TOKEN_B), user_id=USER_B)
        _insert_message_on(
            connection,
            message_id=MESSAGE_RECORD,
            body=_sentence(RECORD_TOKEN),
            settled_at=SEEDED_SETTLED_AT,
        )
        _insert_message_on(connection, message_id=MESSAGE_ZONE, body=_sentence(ZONE_TOKEN))

    with engine.begin() as connection:
        ensure_fts_tables(connection)
    with engine.connect() as connection:
        first_catalogue = _catalogue(connection)
        first_memo_content = _index_snapshot(connection, MEMO_FTS_TABLE, tokens)
        first_message_content = _index_snapshot(connection, MESSAGE_FTS_TABLE, tokens)

    with engine.begin() as connection:
        ensure_fts_tables(connection)  # raises nothing

    with engine.connect() as connection:
        assert _catalogue(connection) == first_catalogue
        assert _index_snapshot(connection, MEMO_FTS_TABLE, tokens) == first_memo_content
        assert _index_snapshot(connection, MESSAGE_FTS_TABLE, tokens) == first_message_content
        assert _both_indexes_sound(connection)


# --- DoD-2: the one-time back-fill, and what it must leave out --------------------------


def _seed_backfill_rows(engine: Engine) -> None:
    """Two memos with distinct tokens, plus one session's record, zone and buried rows."""
    with engine.connect() as connection:
        _insert_memo_on(connection, memo_id=MEMO_A, body=_sentence(MEMO_TOKEN_A))
        _insert_memo_on(connection, memo_id=MEMO_B, body=_sentence(MEMO_TOKEN_B), user_id=USER_B)
        # A record row: `settled_at` set and `related_to` NULL (001.context.md's predicate).
        _insert_message_on(
            connection,
            message_id=MESSAGE_RECORD,
            body=_sentence(RECORD_TOKEN),
            settled_at=SEEDED_SETTLED_AT,
        )
        # A zone row: both NULL.
        _insert_message_on(connection, message_id=MESSAGE_ZONE, body=_sentence(ZONE_TOKEN))
        # A buried row: `related_to` set.
        _insert_message_on(
            connection,
            message_id=MESSAGE_BURIED,
            body=_sentence(BURIED_TOKEN),
            related_to=MESSAGE_RECORD,
        )


def test_backfill_indexes_every_existing_memo__S024_001_DoD2(engine: Engine) -> None:
    """DoD-2 — after the ensure, a `MATCH` on each memo token returns that memo's id as rowid."""
    _seed_backfill_rows(engine)
    with engine.begin() as connection:
        ensure_fts_tables(connection)
    with engine.connect() as connection:
        assert _match_ids(connection, MEMO_FTS_TABLE, MEMO_TOKEN_A) == [MEMO_A]
        assert _match_ids(connection, MEMO_FTS_TABLE, MEMO_TOKEN_B) == [MEMO_B]


def test_backfill_indexes_the_record_row__S024_001_DoD2(engine: Engine) -> None:
    """DoD-2 — a `MATCH` on the record row's token returns its id (R11)."""
    _seed_backfill_rows(engine)
    with engine.begin() as connection:
        ensure_fts_tables(connection)
    with engine.connect() as connection:
        assert _match_ids(connection, MESSAGE_FTS_TABLE, RECORD_TOKEN) == [MESSAGE_RECORD]


@pytest.mark.parametrize("token", [ZONE_TOKEN, BURIED_TOKEN])
def test_backfill_leaves_zone_and_buried_rows_unindexed__S024_001_DoD2(engine: Engine, token: str) -> None:
    """DoD-2 — the zone and buried rows' tokens return nothing (US-115; not `'rebuild'`)."""
    _seed_backfill_rows(engine)
    with engine.begin() as connection:
        ensure_fts_tables(connection)
    with engine.connect() as connection:
        assert _match_ids(connection, MESSAGE_FTS_TABLE, token) == []


def test_backfill_leaves_both_indexes_sound__S024_001_DoD2(engine: Engine) -> None:
    """DoD-2 — `integrity-check` passes on `memo_fts` and on `message_fts`."""
    _seed_backfill_rows(engine)
    with engine.begin() as connection:
        ensure_fts_tables(connection)
    with engine.connect() as connection:
        assert _integrity_ok(connection, MEMO_FTS_TABLE)
        assert _integrity_ok(connection, MESSAGE_FTS_TABLE)


# --- DoD-3: the memo triggers ----------------------------------------------------------


def test_memo_insert_update_and_delete_follow_the_index__S024_001_DoD3(engine: Engine) -> None:
    """DoD-3 — a memo written after the ensure is indexed, re-indexed on a body edit, dropped on delete."""
    with engine.begin() as connection:
        ensure_fts_tables(connection)

    with engine.connect() as connection:
        # A memo inserted afterwards is found by its token.
        _insert_memo_on(connection, memo_id=MEMO_C, body=_sentence(MEMO_TOKEN_A))
        assert _match_ids(connection, MEMO_FTS_TABLE, MEMO_TOKEN_A) == [MEMO_C]

        # After a `body` update the old token finds nothing and the new token finds it.
        _update_memo_on(connection, MEMO_C, body=_sentence(MEMO_TOKEN_NEW))
        assert _match_ids(connection, MEMO_FTS_TABLE, MEMO_TOKEN_A) == []
        assert _match_ids(connection, MEMO_FTS_TABLE, MEMO_TOKEN_NEW) == [MEMO_C]

        # After a delete, its token finds nothing.
        _delete_memo_on(connection, MEMO_C)
        assert _match_ids(connection, MEMO_FTS_TABLE, MEMO_TOKEN_NEW) == []

        # `integrity-check` passes after the sequence.
        assert _integrity_ok(connection, MEMO_FTS_TABLE)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        pytest.param("is_enabled", False, id="is_enabled"),
        pytest.param("is_forced", True, id="is_forced"),
        pytest.param("sort_key", 7, id="sort_key"),
    ],
)
def test_a_flag_or_order_only_memo_update_leaves_every_match_unchanged__S024_001_DoD3(
    engine: Engine, column: str, value: Any
) -> None:
    """DoD-3 — a toggle or a reorder touches no `MATCH` result (UC-044 / UC-075 / UC-076)."""
    tokens = (MEMO_TOKEN_A, MEMO_TOKEN_B, MEMO_TOKEN_NEW, ABSENT_TOKEN)
    with engine.begin() as connection:
        ensure_fts_tables(connection)

    with engine.connect() as connection:
        _insert_memo_on(connection, memo_id=MEMO_A, body=_sentence(MEMO_TOKEN_A), sort_key=0)
        _insert_memo_on(connection, memo_id=MEMO_B, body=_sentence(MEMO_TOKEN_B), user_id=USER_B, sort_key=1)
        before = _index_snapshot(connection, MEMO_FTS_TABLE, tokens)

        _update_memo_on(connection, MEMO_A, **{column: value})

        assert _index_snapshot(connection, MEMO_FTS_TABLE, tokens) == before
        assert _integrity_ok(connection, MEMO_FTS_TABLE)


# --- DoD-4: the message triggers, over all four state transitions -----------------------


def test_message_triggers_cover_every_state_transition__S024_001_DoD4(engine: Engine) -> None:
    """DoD-4 — (a)..(g) in order; only record rows are ever indexed, and both indexes stay sound.

    The record row predicate is `settled_at IS NOT NULL AND related_to IS NULL`
    (`001.context.md`). Case (c) is the settle-shaped **single** UPDATE that sets
    `settled_at` and rewrites `text` at once (US-110.AC-2, US-109.AC-2, US-115).
    """
    with engine.begin() as connection:
        ensure_fts_tables(connection)

    with engine.connect() as connection:
        # (a) a zone insert is not found.
        _insert_message_on(connection, message_id=MESSAGE_ZONE, body=_sentence(ZONE_TOKEN))
        assert _match_ids(connection, MESSAGE_FTS_TABLE, ZONE_TOKEN) == []
        assert _both_indexes_sound(connection)

        # (b) a zone-row text edit is not found.
        _update_message_on(connection, MESSAGE_ZONE, text=_sentence(ZONE_TOKEN_EDITED))
        assert _match_ids(connection, MESSAGE_FTS_TABLE, ZONE_TOKEN) == []
        assert _match_ids(connection, MESSAGE_FTS_TABLE, ZONE_TOKEN_EDITED) == []
        assert _both_indexes_sound(connection)

        # (c) one settle-shaped UPDATE: `settled_at` set and `text` rewritten together.
        _update_message_on(
            connection,
            MESSAGE_ZONE,
            settled_at=SETTLED_AT,
            text=_sentence(SETTLED_TOKEN),
        )
        assert _match_ids(connection, MESSAGE_FTS_TABLE, SETTLED_TOKEN) == [MESSAGE_ZONE]
        assert _match_ids(connection, MESSAGE_FTS_TABLE, ZONE_TOKEN_EDITED) == []
        assert _both_indexes_sound(connection)

        # (d) a text edit of the record row.
        _update_message_on(connection, MESSAGE_ZONE, text=_sentence(SETTLED_TOKEN_EDITED))
        assert _match_ids(connection, MESSAGE_FTS_TABLE, SETTLED_TOKEN_EDITED) == [MESSAGE_ZONE]
        assert _match_ids(connection, MESSAGE_FTS_TABLE, SETTLED_TOKEN) == []
        assert _both_indexes_sound(connection)

        # (e) a re-open-shaped UPDATE clearing `settled_at`.
        _update_message_on(connection, MESSAGE_ZONE, settled_at=None)
        assert _match_ids(connection, MESSAGE_FTS_TABLE, SETTLED_TOKEN_EDITED) == []
        assert _both_indexes_sound(connection)

        # (f) a row inserted already settled (partner filing) is found.
        _insert_message_on(
            connection,
            message_id=MESSAGE_PARTNER,
            body=_sentence(PARTNER_TOKEN),
            kind="partner",
            settled_at=SEEDED_SETTLED_AT,
        )
        assert _match_ids(connection, MESSAGE_FTS_TABLE, PARTNER_TOKEN) == [MESSAGE_PARTNER]
        assert _both_indexes_sound(connection)

        # (g) a row whose `related_to` is set (burial) is not found.
        _insert_message_on(
            connection,
            message_id=MESSAGE_BURIED,
            body=_sentence(BURIED_TOKEN),
            related_to=MESSAGE_PARTNER,
        )
        assert _match_ids(connection, MESSAGE_FTS_TABLE, BURIED_TOKEN) == []
        assert _both_indexes_sound(connection)


# --- DoD-5: the vector ensure and the dimension mismatch --------------------------------


def test_vector_ensure_creates_both_tables_at_the_given_dimension__S024_001_DoD5(engine: Engine) -> None:
    """DoD-5 — `ensure_vector_tables(conn, 8)` creates both, and each reports 8."""
    with engine.begin() as connection:
        ensure_vector_tables(connection, DIMENSION)
    with engine.connect() as fresh:
        present = _table_names(fresh)
        assert MEMO_VEC_TABLE in present
        assert SESSION_VEC_TABLE in present
        assert vector_table_dimension(fresh, MEMO_VEC_TABLE) == DIMENSION
        assert vector_table_dimension(fresh, SESSION_VEC_TABLE) == DIMENSION


def test_a_second_same_dimension_vector_ensure_preserves_an_existing_row__S024_001_DoD5(
    engine: Engine,
) -> None:
    """DoD-5 — a second call with 8 raises nothing and a previously inserted row survives."""
    with engine.begin() as connection:
        ensure_vector_tables(connection, DIMENSION)
    with engine.connect() as connection:
        _write_vector(connection, MEMO_VEC_TABLE, "memo_id", MEMO_A, VECTOR)

    with engine.begin() as connection:
        ensure_vector_tables(connection, DIMENSION)  # raises nothing

    with engine.connect() as connection:
        assert _read_vector(connection, MEMO_VEC_TABLE, "memo_id", MEMO_A) == pytest.approx(VECTOR)
        assert vector_table_dimension(connection, MEMO_VEC_TABLE) == DIMENSION


def test_a_different_dimension_is_refused_as_no_embedding_model__S024_001_DoD5(engine: Engine) -> None:
    """DoD-5 — a mismatch raises `no_embedding_model` with `detail` `{"reason": "dimension_mismatch"}` (D8)."""
    with engine.begin() as connection:
        ensure_vector_tables(connection, DIMENSION)

    with pytest.raises(NoEmbeddingModelError) as raised, engine.begin() as connection:
        ensure_vector_tables(connection, OTHER_DIMENSION)

    assert raised.value.code == "no_embedding_model"
    assert raised.value.detail == {"reason": "dimension_mismatch"}
    # The raise site passes its own fixed message (001.context.md); the class has no default.
    assert isinstance(raised.value.message, str)
    assert raised.value.message != ""


def test_a_refused_dimension_leaves_both_tables_at_the_original_one__S024_001_DoD5(engine: Engine) -> None:
    """DoD-5 — after the refused 16 call, both tables still report 8 (the rebuild re-declares, not this)."""
    with engine.begin() as connection:
        ensure_vector_tables(connection, DIMENSION)
    with pytest.raises(NoEmbeddingModelError), engine.begin() as connection:
        ensure_vector_tables(connection, OTHER_DIMENSION)
    with engine.connect() as fresh:
        assert vector_table_dimension(fresh, MEMO_VEC_TABLE) == DIMENSION
        assert vector_table_dimension(fresh, SESSION_VEC_TABLE) == DIMENSION


# --- DoD-6: no vector table at all --------------------------------------------------


@pytest.mark.parametrize("table_name", [MEMO_VEC_TABLE, SESSION_VEC_TABLE])
def test_dimension_is_none_when_the_vector_table_was_never_created__S024_001_DoD6(
    engine: Engine, table_name: str
) -> None:
    """DoD-6 — on a database where the vector tables were never created, the read-back is none."""
    with engine.connect() as connection:
        assert vector_table_dimension(connection, table_name) is None


# --- DoD-7: the DDL is transactional --------------------------------------------------


def test_a_rolled_back_transaction_leaves_no_virtual_table_and_no_trigger__S024_001_DoD7(
    engine: Engine,
) -> None:
    """DoD-7 — both ensures inside one rolled-back transaction leave nothing behind (U1, U2)."""
    with engine.connect() as connection:
        transaction = connection.begin()
        ensure_fts_tables(connection)
        ensure_vector_tables(connection, DIMENSION)
        transaction.rollback()

    with engine.connect() as fresh:
        remaining = _table_names(fresh)
        for table_name in VIRTUAL_TABLES:
            assert table_name not in remaining
            # No shadow table of a rolled-back virtual table survives either.
            assert [name for name in remaining if name.startswith(f"{table_name}_")] == []
        assert _trigger_names(fresh) == set()


# --- DoD-9: snowflake ids are the FTS5 and vec0 keys -----------------------------------


def test_snowflake_ids_are_the_full_text_rowids__S024_001_DoD9(engine: Engine) -> None:
    """DoD-9 — a memo and a message above 2^60 are indexed by the triggers, rowid == id (D3 / U6)."""
    assert MEMO_C > MIN_SNOWFLAKE_ID
    assert MESSAGE_EXTRA > MIN_SNOWFLAKE_ID

    with engine.begin() as connection:
        ensure_fts_tables(connection)
    with engine.connect() as connection:
        _insert_memo_on(connection, memo_id=MEMO_C, body=_sentence(MEMO_TOKEN_A))
        _insert_message_on(
            connection,
            message_id=MESSAGE_EXTRA,
            body=_sentence(RECORD_TOKEN),
            settled_at=SEEDED_SETTLED_AT,
        )
        assert _match_ids(connection, MEMO_FTS_TABLE, MEMO_TOKEN_A) == [MEMO_C]
        assert _match_ids(connection, MESSAGE_FTS_TABLE, RECORD_TOKEN) == [MESSAGE_EXTRA]
        assert _both_indexes_sound(connection)


@pytest.mark.parametrize(
    ("table_name", "key_column", "row_id", "vector"),
    [
        pytest.param(MEMO_VEC_TABLE, "memo_id", MEMO_C, VECTOR, id="memo_vec"),
        pytest.param(SESSION_VEC_TABLE, "session_id", SESSION_A, OTHER_VECTOR, id="session_vec"),
    ],
)
def test_a_vector_under_a_snowflake_id_round_trips__S024_001_DoD9(
    engine: Engine, table_name: str, key_column: str, row_id: int, vector: list[float]
) -> None:
    """DoD-9 — a point lookup by an id above 2^60 returns the vector that was inserted (D3)."""
    assert row_id > MIN_SNOWFLAKE_ID
    with engine.begin() as connection:
        ensure_vector_tables(connection, DIMENSION)
    with engine.connect() as connection:
        _write_vector(connection, table_name, key_column, row_id, vector)
        assert _read_vector(connection, table_name, key_column, row_id) == pytest.approx(vector)


# --- DoD-10: the virtual tables stay outside the registry ------------------------------


def test_no_virtual_or_shadow_table_is_registered_in_the_metadata__S024_001_DoD10() -> None:
    """DoD-10 — none of the four names, and no FTS5 / vec0 shadow table, is a `metadata` key (D2)."""
    registered = set(schema.metadata.tables)
    for table_name in VIRTUAL_TABLES:
        assert table_name not in registered
        assert [name for name in registered if name.startswith(f"{table_name}_")] == []
