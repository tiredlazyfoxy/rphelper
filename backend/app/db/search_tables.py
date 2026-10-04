"""The virtual-table layer — FTS5 and `vec0` DDL, ensured on write (feature 024, D2).

Everything here is **outside** `app.db.schema`'s `metadata` on purpose. `create_all`, the
drift walk (`db/drift.py`) and the Sync executor (`db/sync.py`) each walk
`metadata.tables` and would mishandle a virtual table, so no `Table(...)` for `memo_fts`,
`message_fts`, `memo_vec` or `session_vec` is ever declared. The drift walk's resulting
gap over virtual tables is owned by `docs/architecture/admin-surfaces.md` and stays open.

`session_fts` is **not** created: `sessions` has no `title` / `partner_label` column, and
that deferral belongs to the feature that gives a session a text (`schema.py` L251-253).

Every function takes a Core `Connection` that is **already inside** the caller's
`with connection.begin():` block and emits its DDL there. `db/engine.py` runs the driver
with `isolation_level=None` plus a `begin` listener that sends the real `BEGIN`, so SQLite's
transactional DDL applies: a rolled-back write also rolls back a table, a trigger and every
shadow table it created. No function opens or commits a transaction of its own, and nothing
here runs at import or at startup.

The ensures are idempotent. Absence is detected from `sqlite_master`
(`type = 'table'`, by name); triggers use `CREATE TRIGGER IF NOT EXISTS`, so a trigger a
Sync rebuild of `memos` / `messages` dropped is restored even when its table survived.
A back-fill runs **only** in the call that created the table.
"""

import re

from sqlalchemy import Connection, text

from app.errors import NoEmbeddingModelError

#: External-content FTS5 index over `memos.body`, keyed on `memos.id` (US-119: no title).
MEMO_FTS_TABLE = "memo_fts"
#: External-content FTS5 index over `messages.text`, keyed on `messages.id` and holding
#: **record rows only** — `settled_at IS NOT NULL AND related_to IS NULL` (US-115).
MESSAGE_FTS_TABLE = "message_fts"
#: `vec0` table of memo-body vectors, keyed `memo_id` (D3: snowflake ids are the keys).
MEMO_VEC_TABLE = "memo_vec"
#: `vec0` table of composed session-text vectors, keyed `session_id` (D3, D6).
SESSION_VEC_TABLE = "session_vec"

# The `settled_entries` boundary as a SQL fragment over a trigger's NEW / OLD row: a record
# row is settled and not buried. Zone rows and buried rows are never indexed (US-115).
_RECORD_ROW_NEW = "NEW.settled_at IS NOT NULL AND NEW.related_to IS NULL"
_RECORD_ROW_OLD = "OLD.settled_at IS NOT NULL AND OLD.related_to IS NULL"

_MEMO_FTS_CREATE = f"CREATE VIRTUAL TABLE {MEMO_FTS_TABLE} USING fts5(body, content='memos', content_rowid='id')"
_MESSAGE_FTS_CREATE = (
    f"CREATE VIRTUAL TABLE {MESSAGE_FTS_TABLE} USING fts5(text, content='messages', content_rowid='id')"
)

# Every memo is indexed, so FTS5's own 'rebuild' command is the right one-time back-fill.
_MEMO_FTS_BACK_FILL = f"INSERT INTO {MEMO_FTS_TABLE}({MEMO_FTS_TABLE}) VALUES('rebuild')"
# Deliberately **not** 'rebuild': that walks all of `messages` and would index the zone and
# buried rows too. Only the record rows go in.
_MESSAGE_FTS_BACK_FILL = (
    f"INSERT INTO {MESSAGE_FTS_TABLE}(rowid, text) "
    "SELECT id, text FROM messages WHERE settled_at IS NOT NULL AND related_to IS NULL"
)

_FTS_TRIGGERS: tuple[str, ...] = (
    # --- `memo_fts`: the standard external-content trio --------------------------------
    f"""CREATE TRIGGER IF NOT EXISTS {MEMO_FTS_TABLE}_after_insert AFTER INSERT ON memos BEGIN
        INSERT INTO {MEMO_FTS_TABLE}(rowid, body) VALUES (NEW.id, NEW.body);
    END""",
    f"""CREATE TRIGGER IF NOT EXISTS {MEMO_FTS_TABLE}_after_delete AFTER DELETE ON memos BEGIN
        INSERT INTO {MEMO_FTS_TABLE}({MEMO_FTS_TABLE}, rowid, body) VALUES ('delete', OLD.id, OLD.body);
    END""",
    # `OF body`, not a plain `AFTER UPDATE`: a flag toggle (`is_enabled` / `is_forced`) and a
    # reorder (`sort_key`) must leave the index completely untouched (D5).
    f"""CREATE TRIGGER IF NOT EXISTS {MEMO_FTS_TABLE}_after_update AFTER UPDATE OF body ON memos BEGIN
        INSERT INTO {MEMO_FTS_TABLE}({MEMO_FTS_TABLE}, rowid, body) VALUES ('delete', OLD.id, OLD.body);
        INSERT INTO {MEMO_FTS_TABLE}(rowid, body) VALUES (NEW.id, NEW.body);
    END""",
    # --- `message_fts`: every statement conditional on the record-row predicate --------
    # Partner filing is born settled, so an insert can already be a record row.
    f"""CREATE TRIGGER IF NOT EXISTS {MESSAGE_FTS_TABLE}_after_insert AFTER INSERT ON messages
    WHEN {_RECORD_ROW_NEW} BEGIN
        INSERT INTO {MESSAGE_FTS_TABLE}(rowid, text) VALUES (NEW.id, NEW.text);
    END""",
    # **One** update trigger, whose two conditional statements run in this order: drop OLD
    # only if OLD was indexed, then add NEW only if NEW belongs in the index. That covers
    # settle (zone -> record: insert only), re-open (record -> zone: delete only), a record
    # text edit (delete then insert), and zone -> zone or a burial (neither). Two separate
    # triggers would not guarantee the order, and an *unconditional* update trigger would
    # issue 'delete' for zone rows that were never indexed — external-content FTS5 then
    # decrements terms that are not there and corrupts the index, which `integrity-check`
    # reports. `INSERT ... SELECT ... WHERE` is what makes a single statement conditional.
    f"""CREATE TRIGGER IF NOT EXISTS {MESSAGE_FTS_TABLE}_after_update
    AFTER UPDATE OF text, settled_at, related_to ON messages BEGIN
        INSERT INTO {MESSAGE_FTS_TABLE}({MESSAGE_FTS_TABLE}, rowid, text)
            SELECT 'delete', OLD.id, OLD.text WHERE {_RECORD_ROW_OLD};
        INSERT INTO {MESSAGE_FTS_TABLE}(rowid, text)
            SELECT NEW.id, NEW.text WHERE {_RECORD_ROW_NEW};
    END""",
    # No message delete exists today; the trigger set is complete all the same.
    f"""CREATE TRIGGER IF NOT EXISTS {MESSAGE_FTS_TABLE}_after_delete AFTER DELETE ON messages
    WHEN {_RECORD_ROW_OLD} BEGIN
        INSERT INTO {MESSAGE_FTS_TABLE}({MESSAGE_FTS_TABLE}, rowid, text) VALUES ('delete', OLD.id, OLD.text);
    END""",
)

#: The key column each `vec0` table declares, in creation order.
_VECTOR_KEY_COLUMNS: dict[str, str] = {MEMO_VEC_TABLE: "memo_id", SESSION_VEC_TABLE: "session_id"}

# sqlite-vec 0.1.9 stores the `CREATE VIRTUAL TABLE ... USING vec0(...)` statement verbatim
# in `sqlite_master.sql`, and its shadow tables carry no readable dimension, so that stored
# text is the only read-back source. Tolerant of case and spacing; the text read back is
# only ever what this module itself wrote.
_FLOAT_DIMENSION = re.compile(r"FLOAT\s*\[\s*(\d+)\s*\]", re.IGNORECASE)

#: `NoEmbeddingModelError` declares no default message, so the raise site supplies one.
_DIMENSION_MISMATCH_MESSAGE = (
    "The embedding index was built for a different dimension; an administrator must rebuild it."
)

_TABLE_PRESENT = text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name LIMIT 1")
_TABLE_DDL = text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :name LIMIT 1")


def _table_exists(connection: Connection, table_name: str) -> bool:
    """Answer whether a table of that name exists, virtual tables included."""
    return connection.execute(_TABLE_PRESENT, {"name": table_name}).first() is not None


def ensure_fts_tables(connection: Connection) -> None:
    """Create the two FTS5 tables, their triggers and the one-time back-fill if absent.

    `connection` is already inside the caller's transaction. Creates `memo_fts` over
    `memos.body` and `message_fts` over `messages.text`, both as external content keyed on
    `id`, then the trigger set from `001.context.md`: the standard trio for `memo_fts`
    (insert / delete / **update OF body**, so a flag toggle or a reorder never touches the
    index), and for `message_fts` the record-row-conditional set — insert when NEW is a
    record row, **one** update trigger whose two conditional statements delete OLD then
    insert NEW, and a conditional delete. An unconditional `message_fts` update trigger
    would issue `'delete'` for zone rows that were never indexed and corrupt the index.

    Back-fill, only in the call that created that table: `'rebuild'` for `memo_fts`,
    because every memo is indexed; for `message_fts` an explicit
    `INSERT INTO message_fts(rowid, text) SELECT id, text FROM messages WHERE <record row>`,
    because `'rebuild'` would index zone and buried rows.

    A missing trigger is created even when its table already exists. A second call changes
    nothing. Returns nothing.
    """
    if not _table_exists(connection, MEMO_FTS_TABLE):
        connection.execute(text(_MEMO_FTS_CREATE))
        connection.execute(text(_MEMO_FTS_BACK_FILL))
    if not _table_exists(connection, MESSAGE_FTS_TABLE):
        connection.execute(text(_MESSAGE_FTS_CREATE))
        connection.execute(text(_MESSAGE_FTS_BACK_FILL))
    # Unconditionally re-issued: `IF NOT EXISTS` makes each one a no-op when it is already
    # there, and restores a trigger a Sync rebuild of `memos` / `messages` dropped.
    for trigger_ddl in _FTS_TRIGGERS:
        connection.execute(text(trigger_ddl))


def vector_table_dimension(connection: Connection, table_name: str) -> int | None:
    """Return the dimension a `vec0` table was declared with, or `None` when it is absent.

    `table_name` is `MEMO_VEC_TABLE` or `SESSION_VEC_TABLE`. Read back by parsing
    `FLOAT[<n>]` out of the table's stored `sqlite_master.sql`, which sqlite-vec 0.1.9
    keeps verbatim as the `CREATE VIRTUAL TABLE … USING vec0(…)` statement that made it.
    Opens no transaction and writes nothing.
    """
    # An absent table returns no row at all, which is the `None` case.
    row = connection.execute(_TABLE_DDL, {"name": table_name}).first()
    if row is None:
        return None
    declaration: str | None = row[0]
    if declaration is None:
        return None
    found = _FLOAT_DIMENSION.search(declaration)
    if found is None:
        return None
    return int(found.group(1))


def ensure_vector_tables(connection: Connection, dimension: int) -> None:
    """Create `memo_vec` and `session_vec` at `dimension` if absent (D2, D8).

    `connection` is already inside the caller's transaction and `dimension` is the
    designated model's positive `embedding_dim`.

    If either table already exists with a different declared dimension, raises
    `NoEmbeddingModelError` with a fixed message and `detail` exactly
    `{"reason": "dimension_mismatch"}` — **before creating anything**. The tables are not
    re-declared and no data is touched; re-declaring is the administrator's rebuild's job
    (`fast/002`). A second call at the same dimension changes nothing. Returns nothing.
    """
    # Both declared dimensions are read before anything is created, so a mismatch on the
    # second table still leaves the first one uncreated: the call is a no-op but the raise.
    for table_name in _VECTOR_KEY_COLUMNS:
        declared = vector_table_dimension(connection, table_name)
        if declared is not None and declared != dimension:
            raise NoEmbeddingModelError(_DIMENSION_MISMATCH_MESSAGE, {"reason": "dimension_mismatch"})

    for table_name, key_column in _VECTOR_KEY_COLUMNS.items():
        if not _table_exists(connection, table_name):
            connection.execute(
                text(
                    f"CREATE VIRTUAL TABLE {table_name} USING vec0("
                    f"{key_column} INTEGER PRIMARY KEY, embedding FLOAT[{dimension}])"
                )
            )
