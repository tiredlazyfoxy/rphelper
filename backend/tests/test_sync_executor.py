"""Tests for step 003 of feature 007 — the DDL executor ``app.db.sync``.

Step file: ``docs/plans/007.schema-drift-and-remediation/003.batch-ddl-executor-and-errors.md``.
Feature context: ``context.md`` D4 (Create and Sync by postcondition), D5 (the rebuild and its
all-or-nothing failure), D7 (Create never drops), D8 (the foreign-key dance), D9 (the two error
codes and the table-name safety rule), R5 (no counts); ``003.context.md``.

DoD-1..DoD-15 and DoD-17..DoD-19 live here. DoD-16 (the two error classes themselves) lives in
``test_errors.py``; DoD-20..DoD-22 are ``[manual/live]``.

Every database test runs against a real ``.sqlite`` file from the ``db_engine`` fixture, never
``:memory:`` and never a mock: what is under test is what the create-copy-drop-rename rebuild
actually does to real rows. Drift is produced by hand-written DDL on that file; every registry is
a purpose-built ``MetaData``. Each operation is called the way the router will call it — on a
connection with no transaction open.

A "value that will not cast" (DoD-11) is not used: SQLite's type affinity accepts almost any
value in any declared type, so no such cast is reliably refused. DoD-11 is exercised through the
two failures SQLite genuinely enforces during a rebuild — a NOT NULL tightening over existing
NULLs, and a declared UNIQUE index over duplicate values.
"""

import ast
import inspect
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import ModuleType
from typing import Any

import pytest
from loguru import logger
from sqlalchemy import Column, Connection, Engine, ForeignKey, Index, Integer, MetaData, Table, Text, event, text

import app.db.drift as drift_module
import app.db.sync as sync_module
from app.db.drift import TableReport, TableStatus, build_drift_report
from app.db.sync import create_table, sync_table
from app.errors import SchemaApplyFailedError, UnknownTableError

Operation = Callable[[Connection, MetaData, str], TableReport]

OPERATIONS = [
    pytest.param(create_table, "create", id="create"),
    pytest.param(sync_table, "sync", id="sync"),
]

# --------------------------------------------------------------------------- the purpose-made registry

# The "notes" table every test below declares: id INTEGER PK, name TEXT NOT NULL, note TEXT NULL,
# and one explicit non-unique index over ``name``.
DECLARED_COLUMNS = [("id", "INTEGER", True), ("name", "TEXT", True), ("note", "TEXT", False)]
DECLARED_INDEXES = {(("name",), False)}

# Hand-written DDL that produces exactly the declared shape on disk (``id`` is written NOT NULL so
# it matches a declared primary key).
NOTES_DDL = "CREATE TABLE notes (id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL, note TEXT)"
NOTES_INDEX_DDL = "CREATE INDEX ix_notes_name ON notes (name)"

# A stored value no error payload or log line may ever carry (the redaction rule, D9).
ROW_SECRET = "row-secret-4471"

# Substrings of SQLite driver messages; none may appear in an error payload or a log line (D9).
DRIVER_TEXT_MARKERS = (
    "constraint failed",
    "not null constraint",
    "unique constraint",
    "foreign key constraint",
    "ix_notes_name already exists",
    "datatype mismatch",
    "integrityerror",
    "operationalerror",
    "sqlite3.",
    "_alembic_tmp_notes.",
)

WRITE_STATEMENT = re.compile(r"^\s*(DROP|ALTER|INSERT|UPDATE|DELETE|REPLACE)\b", re.IGNORECASE)
DROP_STATEMENT = re.compile(r"\bDROP\s+(TABLE|INDEX|COLUMN|VIEW|TRIGGER)\b", re.IGNORECASE)
COUNT_CALL = re.compile(r"\bcount\s*\(", re.IGNORECASE)


def _notes_registry(*, name_index_unique: bool = False, extra: tuple[Any, ...] = ()) -> MetaData:
    registry = MetaData()
    Table(
        "notes",
        registry,
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("name", Text, nullable=False),
        Column("note", Text, nullable=True),
        Index("ix_notes_name", "name", unique=name_index_unique),
        *extra,
    )
    return registry


def _family_registry() -> MetaData:
    """A parent/child pair: ``children.parent_id`` references ``parents.id`` (D8)."""
    registry = MetaData()
    Table(
        "parents",
        registry,
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("label", Text, nullable=False),
    )
    Table(
        "children",
        registry,
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("parent_id", Integer, ForeignKey("parents.id"), nullable=False),
        Column("note", Text, nullable=True),
    )
    return registry


# --------------------------------------------------------------------------- helpers


def _ddl(engine: Engine, *statements: str) -> None:
    """Run hand-written DDL / DML on the per-test SQLite file, committed."""
    with engine.connect() as conn:
        with conn.begin():
            for statement in statements:
                conn.execute(text(statement))


def _create_all(engine: Engine, registry: MetaData) -> None:
    with engine.connect() as conn:
        with conn.begin():
            registry.create_all(conn)


def _read(engine: Engine, sql: str) -> list[tuple[Any, ...]]:
    with engine.connect() as conn:
        return [tuple(row) for row in conn.exec_driver_sql(sql).all()]


def _columns(engine: Engine, table_name: str) -> list[tuple[str, str, bool]]:
    """(name, upper-cased declared type, NOT NULL) per live column, in table order."""
    rows = _read(engine, f'PRAGMA table_info("{table_name}")')
    return [(row[1], str(row[2]).upper(), bool(row[3])) for row in rows]


def _column_names(engine: Engine, table_name: str) -> list[str]:
    return [name for name, _type, _not_null in _columns(engine, table_name)]


def _indexes(engine: Engine, table_name: str) -> set[tuple[tuple[str, ...], bool]]:
    """Explicitly created indexes (origin ``c``) as (column list, unique)."""
    found: set[tuple[tuple[str, ...], bool]] = set()
    with engine.connect() as conn:
        for row in conn.exec_driver_sql(f'PRAGMA index_list("{table_name}")').all():
            _seq, index_name, unique, origin = row[0], row[1], row[2], row[3]
            if origin != "c":
                continue
            info = sorted(conn.exec_driver_sql(f'PRAGMA index_info("{index_name}")').all(), key=lambda r: r[0])
            found.add((tuple(r[2] for r in info), bool(unique)))
    return found


def _master(engine: Engine) -> list[tuple[Any, ...]]:
    """Every ``sqlite_master`` entry with its stored SQL — the whole schema, byte for byte."""
    return _read(engine, "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name")


def _table_names(engine: Engine) -> set[str]:
    return {row[0] for row in _read(engine, "SELECT name FROM sqlite_master WHERE type = 'table'")}


def _rows(engine: Engine, table_name: str, columns: str = "*") -> list[tuple[Any, ...]]:
    return _read(engine, f"SELECT {columns} FROM {table_name} ORDER BY id")


def _report_of(engine: Engine, registry: MetaData, table_name: str) -> TableReport:
    """The step-002 report entry for ``table_name``, read on a fresh connection."""
    with engine.connect() as conn:
        report = build_drift_report(conn, registry)
    matches = [entry for entry in report.tables if entry.table_name == table_name]
    assert len(matches) == 1
    return matches[0]


def _apply(engine: Engine, operation: Operation, registry: MetaData, table_name: str) -> TableReport:
    with engine.connect() as conn:
        return operation(conn, registry, table_name)


def _tmp_tables_on(conn: Connection) -> list[str]:
    names = [row[0] for row in conn.exec_driver_sql("SELECT name FROM sqlite_master").all()]
    return [name for name in names if name.startswith("_alembic_tmp_")]


def _foreign_keys_on(conn: Connection) -> int:
    return int(conn.exec_driver_sql("PRAGMA foreign_keys").scalar_one())


def _assert_in_sync(report: TableReport, table_name: str) -> None:
    assert isinstance(report, TableReport)
    assert report.table_name == table_name
    assert report.status == TableStatus.IN_SYNC
    assert report.missing_columns == ()
    assert report.extra_columns == ()
    assert report.changed_columns == ()
    assert report.missing_indexes == ()
    assert report.extra_indexes == ()


@contextmanager
def _recording(conn: Connection) -> Iterator[list[str]]:
    """Record every statement the connection sends to the driver while the block runs."""
    statements: list[str] = []

    def on_statement(_conn: Any, _cursor: Any, statement: str, _params: Any, _context: Any, _many: bool) -> None:
        statements.append(statement)

    event.listen(conn, "before_cursor_execute", on_statement)
    try:
        yield statements
    finally:
        event.remove(conn, "before_cursor_execute", on_statement)


@contextmanager
def _captured_logs() -> Iterator[list[str]]:
    """Every loguru line emitted while the block runs — formatted text, message, extra, exception."""
    lines: list[str] = []

    def sink(message: Any) -> None:
        record = message.record
        lines.append(str(message))
        lines.append(str(record["message"]))
        lines.append(repr(record["extra"]))
        if record["exception"] is not None:
            lines.append(repr(record["exception"].value))

    handler_id = logger.add(sink, level=0, format="{level} {name} {message}")
    try:
        yield lines
    finally:
        logger.remove(handler_id)


def _carries_driver_text(value: str) -> bool:
    lowered = value.lower()
    return ROW_SECRET in value or any(marker in lowered for marker in DRIVER_TEXT_MARKERS)


# --------------------------------------------------------------------------- failing rebuilds


def _arrange_not_null_over_nulls(engine: Engine) -> MetaData:
    """Declared ``name`` NOT NULL; the live column is nullable and holds a NULL (D5 / DoD-11)."""
    _ddl(
        engine,
        "CREATE TABLE notes (id INTEGER NOT NULL PRIMARY KEY, name TEXT, note TEXT, legacy TEXT)",
        NOTES_INDEX_DDL,
        "CREATE INDEX ix_notes_legacy ON notes (legacy)",
        f"INSERT INTO notes (id, name, note, legacy) VALUES (1, NULL, '{ROW_SECRET}', 'legacy-a')",
        "INSERT INTO notes (id, name, note, legacy) VALUES (2, 'beta', NULL, 'legacy-b')",
    )
    return _notes_registry()


def _arrange_unique_index_over_duplicates(engine: Engine) -> MetaData:
    """Declared ``ix_notes_name`` UNIQUE; the live index is not, and ``name`` holds duplicates."""
    _ddl(
        engine,
        NOTES_DDL,
        NOTES_INDEX_DDL,
        f"INSERT INTO notes (id, name, note) VALUES (1, 'twin', '{ROW_SECRET}')",
        "INSERT INTO notes (id, name, note) VALUES (2, 'twin', NULL)",
    )
    return _notes_registry(name_index_unique=True)


FAILING_REBUILDS = [
    pytest.param(_arrange_not_null_over_nulls, id="not_null_over_existing_nulls"),
    pytest.param(_arrange_unique_index_over_duplicates, id="unique_index_over_duplicates"),
]


def _arrange_orphaned_children(engine: Engine) -> MetaData:
    """``children`` is drifted (an extra column) and written without its FK clause, so it holds a
    row whose ``parent_id`` names no parent. Rebuilding it from the registry — which declares the
    FK — would leave a foreign-key violation (D8 / DoD-14)."""
    registry = _family_registry()
    with engine.connect() as conn:
        with conn.begin():
            registry.tables["parents"].create(conn)
    _ddl(
        engine,
        "CREATE TABLE children "
        "(id INTEGER NOT NULL PRIMARY KEY, parent_id INTEGER NOT NULL, note TEXT, legacy TEXT)",
        "INSERT INTO parents (id, label) VALUES (1, 'one')",
        "INSERT INTO children (id, parent_id, note, legacy) VALUES (10, 1, 'fine', 'x')",
        f"INSERT INTO children (id, parent_id, note, legacy) VALUES (11, 99, '{ROW_SECRET}', 'y')",
    )
    return registry


# =========================================================================== DoD-1


def test_create_on_a_missing_table_builds_every_declared_column_nullability_and_index__DoD1(
    db_engine: Engine,
) -> None:
    """DoD-1 — Create on a missing table creates it with every declared column, its declared
    nullability and its declared indexes; the table is afterwards reported in sync.

    Step 003 DoD-1 (US-018.AC-1, UC-015).
    """
    registry = _notes_registry(extra=(Index("ix_notes_note", "note", unique=True),))
    assert "notes" not in _table_names(db_engine)

    report = _apply(db_engine, create_table, registry, "notes")

    assert _columns(db_engine, "notes") == DECLARED_COLUMNS
    assert _indexes(db_engine, "notes") == {(("name",), False), (("note",), True)}
    _assert_in_sync(report, "notes")
    _assert_in_sync(_report_of(db_engine, registry, "notes"), "notes")


def test_create_on_a_missing_table_leaves_other_tables_alone__DoD1(db_engine: Engine) -> None:
    """DoD-1 — Create addresses the one named table: another registry table stays absent and an
    existing unrelated table keeps its rows.

    Step 003 DoD-1 (US-018.AC-1, UC-015).
    """
    registry = _notes_registry()
    Table("others", registry, Column("id", Integer, primary_key=True, autoincrement=False))
    _ddl(
        db_engine,
        "CREATE TABLE bystander (id INTEGER NOT NULL PRIMARY KEY, value TEXT)",
        "INSERT INTO bystander (id, value) VALUES (1, 'stays')",
    )

    _apply(db_engine, create_table, registry, "notes")

    assert "notes" in _table_names(db_engine)
    assert "others" not in _table_names(db_engine)
    assert _rows(db_engine, "bystander") == [(1, "stays")]


# =========================================================================== DoD-2

EXISTING_STATES = {
    "in_sync": (
        [NOTES_DDL, NOTES_INDEX_DDL],
        [
            "INSERT INTO notes (id, name, note) VALUES (1, 'alpha', 'first')",
            "INSERT INTO notes (id, name, note) VALUES (2, 'beta', NULL)",
        ],
        TableStatus.IN_SYNC,
    ),
    "extra_and_missing_column": (
        [
            "CREATE TABLE notes (id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL, legacy TEXT)",
            NOTES_INDEX_DDL,
        ],
        [
            "INSERT INTO notes (id, name, legacy) VALUES (1, 'alpha', 'old-1')",
            "INSERT INTO notes (id, name, legacy) VALUES (2, 'beta', 'old-2')",
        ],
        TableStatus.DRIFTED,
    ),
    "changed_type": (
        [
            "CREATE TABLE notes (id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL, note VARCHAR(10))",
            NOTES_INDEX_DDL,
        ],
        ["INSERT INTO notes (id, name, note) VALUES (1, 'alpha', 'first')"],
        TableStatus.DRIFTED,
    ),
    "changed_nullability": (
        [
            "CREATE TABLE notes (id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL, note TEXT NOT NULL)",
            NOTES_INDEX_DDL,
        ],
        ["INSERT INTO notes (id, name, note) VALUES (1, 'alpha', 'first')"],
        TableStatus.DRIFTED,
    ),
    "missing_index": (
        [NOTES_DDL],
        ["INSERT INTO notes (id, name, note) VALUES (1, 'alpha', 'first')"],
        TableStatus.DRIFTED,
    ),
    "extra_index": (
        [NOTES_DDL, NOTES_INDEX_DDL, "CREATE INDEX ix_notes_extra ON notes (note)"],
        ["INSERT INTO notes (id, name, note) VALUES (1, 'alpha', 'first')"],
        TableStatus.DRIFTED,
    ),
}


@pytest.mark.parametrize("state", list(EXISTING_STATES))
def test_create_on_an_existing_table_changes_nothing_and_answers_the_current_truth__DoD2(
    db_engine: Engine, state: str
) -> None:
    """DoD-2 — Create on a table that already exists (in sync or drifted) changes nothing at all:
    no column added or dropped, no index touched, no row touched; the answer is the table's
    current truth.

    Step 003 DoD-2 (context.md D4).
    """
    ddl, inserts, expected_status = EXISTING_STATES[state]
    _ddl(db_engine, *ddl, *inserts)
    registry = _notes_registry()
    before_master = _master(db_engine)
    before_rows = _rows(db_engine, "notes")
    before_report = _report_of(db_engine, registry, "notes")
    assert before_report.status == expected_status

    with db_engine.connect() as conn:
        with _recording(conn) as statements:
            report = create_table(conn, registry, "notes")

    assert _master(db_engine) == before_master
    assert _rows(db_engine, "notes") == before_rows
    assert not [s for s in statements if WRITE_STATEMENT.search(s)]
    assert report == before_report
    assert report == _report_of(db_engine, registry, "notes")
    assert report.status == expected_status


def test_create_on_a_drifted_table_reports_its_drift_rather_than_fixing_it__DoD2(db_engine: Engine) -> None:
    """DoD-2 — a Create against a drifted table answers with the drift it left in place.

    Step 003 DoD-2 (context.md D4).
    """
    ddl, inserts, _status = EXISTING_STATES["extra_and_missing_column"]
    _ddl(db_engine, *ddl, *inserts)

    report = _apply(db_engine, create_table, _notes_registry(), "notes")

    assert report.status == TableStatus.DRIFTED
    assert report.missing_columns == ("note",)
    assert report.extra_columns == ("legacy",)
    assert _column_names(db_engine, "notes") == ["id", "name", "legacy"]


# =========================================================================== DoD-3

EXTRA_COLUMN_STATES = {
    "extra_column": [
        "CREATE TABLE notes (id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL, note TEXT, legacy TEXT)",
        NOTES_INDEX_DDL,
    ],
    "extra_column_and_changed_type": [
        "CREATE TABLE notes (id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL, note VARCHAR(10), legacy TEXT)",
        NOTES_INDEX_DDL,
    ],
    "extra_column_and_extra_index": [
        "CREATE TABLE notes (id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL, note TEXT, legacy TEXT)",
        NOTES_INDEX_DDL,
        "CREATE INDEX ix_notes_legacy ON notes (legacy)",
    ],
    "extra_column_and_missing_column": [
        "CREATE TABLE notes (id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL, legacy TEXT)",
        NOTES_INDEX_DDL,
    ],
}


@pytest.mark.parametrize("state", list(EXTRA_COLUMN_STATES))
def test_create_never_drops_a_column_the_registry_no_longer_declares__DoD3(db_engine: Engine, state: str) -> None:
    """DoD-3 — Create never drops a column, including one the registry no longer declares: the
    undeclared column, its data and every extra index survive.

    Step 003 DoD-3 (context.md D4, D7).
    """
    _ddl(
        db_engine,
        *EXTRA_COLUMN_STATES[state],
        "INSERT INTO notes (id, name, legacy) VALUES (1, 'alpha', 'kept-legacy-1')",
        "INSERT INTO notes (id, name, legacy) VALUES (2, 'beta', 'kept-legacy-2')",
    )
    before_master = _master(db_engine)

    report = _apply(db_engine, create_table, _notes_registry(), "notes")

    assert "legacy" in _column_names(db_engine, "notes")
    assert _rows(db_engine, "notes", "id, name, legacy") == [
        (1, "alpha", "kept-legacy-1"),
        (2, "beta", "kept-legacy-2"),
    ]
    assert _master(db_engine) == before_master
    assert "legacy" in report.extra_columns


@pytest.mark.parametrize("state", ["missing", "in_sync", "extra_column"])
def test_create_issues_no_drop_in_any_state__DoD3(db_engine: Engine, state: str) -> None:
    """DoD-3 — in every state (missing, in sync, drifted) Create sends no DROP of anything.

    Step 003 DoD-3 (context.md D4, D7).
    """
    if state == "in_sync":
        _ddl(db_engine, NOTES_DDL, NOTES_INDEX_DDL)
    elif state == "extra_column":
        _ddl(db_engine, *EXTRA_COLUMN_STATES["extra_column"])

    with db_engine.connect() as conn:
        with _recording(conn) as statements:
            create_table(conn, _notes_registry(), "notes")

    assert not [s for s in statements if DROP_STATEMENT.search(s)]


# =========================================================================== DoD-4


def test_sync_on_a_missing_table_creates_it_in_sync__DoD4(db_engine: Engine) -> None:
    """DoD-4 — Sync on a missing table creates it (declared columns, nullability, indexes) and the
    table is afterwards reported in sync.

    Step 003 DoD-4 (US-018.AC-1, UC-015).
    """
    registry = _notes_registry()
    assert "notes" not in _table_names(db_engine)

    report = _apply(db_engine, sync_table, registry, "notes")

    assert _columns(db_engine, "notes") == DECLARED_COLUMNS
    assert _indexes(db_engine, "notes") == DECLARED_INDEXES
    _assert_in_sync(report, "notes")
    _assert_in_sync(_report_of(db_engine, registry, "notes"), "notes")


# =========================================================================== DoD-5


@pytest.mark.parametrize("made_by", ["registry", "hand_written_ddl"])
def test_sync_on_an_in_sync_table_touches_neither_schema_nor_rows__DoD5(db_engine: Engine, made_by: str) -> None:
    """DoD-5 — Sync on an in-sync table is a no-op: the schema is byte-for-byte unchanged, every
    row is unchanged, and no write statement is sent.

    Step 003 DoD-5 (context.md D4).
    """
    registry = _notes_registry()
    if made_by == "registry":
        _create_all(db_engine, registry)
    else:
        _ddl(db_engine, NOTES_DDL, NOTES_INDEX_DDL)
    _ddl(
        db_engine,
        "INSERT INTO notes (id, name, note) VALUES (1, 'alpha', 'first')",
        "INSERT INTO notes (id, name, note) VALUES (2, 'beta', NULL)",
    )
    before_master = _master(db_engine)
    before_rows = _rows(db_engine, "notes")

    with db_engine.connect() as conn:
        with _recording(conn) as statements:
            report = sync_table(conn, registry, "notes")

    assert _master(db_engine) == before_master
    assert _rows(db_engine, "notes") == before_rows
    assert not [s for s in statements if WRITE_STATEMENT.search(s)]
    _assert_in_sync(report, "notes")


# =========================================================================== DoD-6


def test_sync_adds_a_missing_column_and_keeps_every_row__DoD6(db_engine: Engine) -> None:
    """DoD-6 — Sync on a table missing a declared column adds it; afterwards in sync, and every
    pre-existing row survives with its other column values intact.

    Step 003 DoD-6 (US-018.AC-1, US-018.AC-2, UC-015).
    """
    _ddl(
        db_engine,
        "CREATE TABLE notes (id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL)",
        NOTES_INDEX_DDL,
        "INSERT INTO notes (id, name) VALUES (1, 'alpha')",
        "INSERT INTO notes (id, name) VALUES (2, 'beta')",
        "INSERT INTO notes (id, name) VALUES (3, 'gamma')",
    )
    registry = _notes_registry()
    assert _report_of(db_engine, registry, "notes").missing_columns == ("note",)

    report = _apply(db_engine, sync_table, registry, "notes")

    assert _columns(db_engine, "notes") == DECLARED_COLUMNS
    assert _rows(db_engine, "notes", "id, name, note") == [(1, "alpha", None), (2, "beta", None), (3, "gamma", None)]
    _assert_in_sync(report, "notes")
    _assert_in_sync(_report_of(db_engine, registry, "notes"), "notes")


# =========================================================================== DoD-7

CHANGED_COLUMN_STATES = {
    "type_changed": (
        "CREATE TABLE notes (id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL, note VARCHAR(10))"
    ),
    "nullability_loosened": (
        "CREATE TABLE notes (id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL, note TEXT NOT NULL)"
    ),
    "nullability_tightened_over_no_nulls": (
        "CREATE TABLE notes (id INTEGER NOT NULL PRIMARY KEY, name TEXT, note TEXT)"
    ),
}


@pytest.mark.parametrize("state", list(CHANGED_COLUMN_STATES))
def test_sync_rebuilds_a_changed_column_and_preserves_every_value__DoD7(db_engine: Engine, state: str) -> None:
    """DoD-7 — Sync on a table whose column changed type or nullability rebuilds it; afterwards in
    sync, and every surviving column's data is preserved.

    Step 003 DoD-7 (US-018.AC-1; context.md D5).
    """
    _ddl(
        db_engine,
        CHANGED_COLUMN_STATES[state],
        NOTES_INDEX_DDL,
        "INSERT INTO notes (id, name, note) VALUES (1, 'alpha', 'first')",
        "INSERT INTO notes (id, name, note) VALUES (2, 'beta', 'second')",
        "INSERT INTO notes (id, name, note) VALUES (3, 'gamma', 'third')",
    )
    registry = _notes_registry()
    before = _report_of(db_engine, registry, "notes")
    assert before.status == TableStatus.DRIFTED
    assert len(before.changed_columns) == 1

    report = _apply(db_engine, sync_table, registry, "notes")

    assert _columns(db_engine, "notes") == DECLARED_COLUMNS
    assert _indexes(db_engine, "notes") == DECLARED_INDEXES
    assert _rows(db_engine, "notes", "id, name, note") == [
        (1, "alpha", "first"),
        (2, "beta", "second"),
        (3, "gamma", "third"),
    ]
    _assert_in_sync(report, "notes")
    _assert_in_sync(_report_of(db_engine, registry, "notes"), "notes")


# =========================================================================== DoD-8

DROPPED_COLUMN_STATES = {
    "extra_column": "CREATE TABLE notes (id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL, note TEXT, legacy TEXT)",
    "extra_column_and_changed_type": (
        "CREATE TABLE notes (id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL, note VARCHAR(10), legacy TEXT)"
    ),
}


@pytest.mark.parametrize("state", list(DROPPED_COLUMN_STATES))
def test_sync_drops_an_undeclared_column_and_preserves_the_survivors__DoD8(db_engine: Engine, state: str) -> None:
    """DoD-8 — Sync on a table carrying a column the registry no longer declares drops that column
    and preserves the data of every column that survives the rebuild.

    Step 003 DoD-8 (US-018.AC-1; context.md D5, D7).
    """
    _ddl(
        db_engine,
        DROPPED_COLUMN_STATES[state],
        NOTES_INDEX_DDL,
        "INSERT INTO notes (id, name, note, legacy) VALUES (1, 'alpha', 'first', 'old-1')",
        "INSERT INTO notes (id, name, note, legacy) VALUES (2, 'beta', NULL, 'old-2')",
    )
    registry = _notes_registry()
    assert _report_of(db_engine, registry, "notes").extra_columns == ("legacy",)

    report = _apply(db_engine, sync_table, registry, "notes")

    assert "legacy" not in _column_names(db_engine, "notes")
    assert _columns(db_engine, "notes") == DECLARED_COLUMNS
    assert _rows(db_engine, "notes", "id, name, note") == [(1, "alpha", "first"), (2, "beta", None)]
    _assert_in_sync(report, "notes")


# =========================================================================== DoD-9

INDEX_DRIFT_STATES = {
    "missing_index": [NOTES_DDL],
    "extra_index": [NOTES_DDL, NOTES_INDEX_DDL, "CREATE INDEX ix_notes_extra ON notes (note)"],
    "uniqueness_differs": [NOTES_DDL, "CREATE UNIQUE INDEX ix_notes_name ON notes (name)"],
    "missing_and_extra_index": [NOTES_DDL, "CREATE INDEX ix_notes_note_only ON notes (note)"],
}


@pytest.mark.parametrize("state", list(INDEX_DRIFT_STATES))
def test_sync_brings_the_index_set_into_line__DoD9(db_engine: Engine, state: str) -> None:
    """DoD-9 — Sync on a table with a missing or extra index brings the index set into line; the
    table is afterwards reported in sync and its rows are kept.

    Step 003 DoD-9 (US-018.AC-1; context.md D1).
    """
    _ddl(
        db_engine,
        *INDEX_DRIFT_STATES[state],
        "INSERT INTO notes (id, name, note) VALUES (1, 'alpha', 'first')",
        "INSERT INTO notes (id, name, note) VALUES (2, 'beta', 'second')",
    )
    registry = _notes_registry()
    assert _report_of(db_engine, registry, "notes").status == TableStatus.DRIFTED

    report = _apply(db_engine, sync_table, registry, "notes")

    assert _indexes(db_engine, "notes") == DECLARED_INDEXES
    assert _rows(db_engine, "notes", "id, name, note") == [(1, "alpha", "first"), (2, "beta", "second")]
    _assert_in_sync(report, "notes")
    _assert_in_sync(_report_of(db_engine, registry, "notes"), "notes")


# =========================================================================== DoD-10


@pytest.mark.parametrize(("operation", "_name"), OPERATIONS)
def test_answer_for_a_missing_table_is_re_derived_after_the_apply__DoD10(
    db_engine: Engine, operation: Operation, _name: str
) -> None:
    """DoD-10 — the answer reflects the corrected state: the table was missing before, and the
    returned report says in sync and equals a fresh report taken afterwards.

    Step 003 DoD-10 (US-018.AC-2, UC-015).
    """
    registry = _notes_registry()
    assert _report_of(db_engine, registry, "notes").status == TableStatus.MISSING

    report = _apply(db_engine, operation, registry, "notes")

    _assert_in_sync(report, "notes")
    assert report == _report_of(db_engine, registry, "notes")


def test_sync_answer_for_a_drifted_table_is_re_derived_after_the_apply__DoD10(db_engine: Engine) -> None:
    """DoD-10 — Sync's answer for a table that was drifted is the post-rebuild report, not the
    pre-rebuild one.

    Step 003 DoD-10 (US-018.AC-2, UC-015).
    """
    _ddl(db_engine, *EXTRA_COLUMN_STATES["extra_column_and_changed_type"])
    registry = _notes_registry()
    before = _report_of(db_engine, registry, "notes")
    assert before.status == TableStatus.DRIFTED

    report = _apply(db_engine, sync_table, registry, "notes")

    assert report != before
    _assert_in_sync(report, "notes")
    assert report == _report_of(db_engine, registry, "notes")


# =========================================================================== DoD-11


@pytest.mark.parametrize("arrange", FAILING_REBUILDS)
def test_a_rebuild_that_cannot_complete_raises_and_leaves_the_table_exactly_as_it_was__DoD11(
    db_engine: Engine, arrange: Callable[[Engine], MetaData]
) -> None:
    """DoD-11 — a rebuild that cannot complete raises ``schema_apply_failed`` and leaves the table
    exactly as it was: same columns, same indexes, same rows, same drift status.

    Step 003 DoD-11 (context.md D5, D9).
    """
    registry = arrange(db_engine)
    before_master = _master(db_engine)
    before_columns = _columns(db_engine, "notes")
    before_indexes = _indexes(db_engine, "notes")
    before_rows = _rows(db_engine, "notes")
    before_report = _report_of(db_engine, registry, "notes")
    assert before_report.status == TableStatus.DRIFTED

    with pytest.raises(SchemaApplyFailedError) as raised:
        _apply(db_engine, sync_table, registry, "notes")

    assert raised.value.code == "schema_apply_failed"
    assert _master(db_engine) == before_master
    assert _columns(db_engine, "notes") == before_columns
    assert _indexes(db_engine, "notes") == before_indexes
    assert _rows(db_engine, "notes") == before_rows
    assert _report_of(db_engine, registry, "notes") == before_report


# =========================================================================== DoD-12


@pytest.mark.parametrize(
    "arrange", [*FAILING_REBUILDS, pytest.param(_arrange_orphaned_children, id="foreign_key_violation")]
)
def test_no_alembic_temp_table_survives_a_failed_rebuild__DoD12(
    db_engine: Engine, arrange: Callable[[Engine], MetaData]
) -> None:
    """DoD-12 — after a failed rebuild no ``_alembic_tmp_*`` table remains in ``sqlite_master``,
    seen from the operation's own connection and from a fresh one.

    Step 003 DoD-12 (context.md D5).
    """
    registry = arrange(db_engine)
    table_name = "children" if "children" in registry.tables else "notes"

    with db_engine.connect() as conn:
        with pytest.raises(SchemaApplyFailedError):
            sync_table(conn, registry, table_name)
        assert _tmp_tables_on(conn) == []

    assert not [name for name in _table_names(db_engine) if name.startswith("_alembic_tmp_")]
    assert not [row for row in _master(db_engine) if str(row[1]).startswith("_alembic_tmp_")]


# =========================================================================== DoD-13


def test_foreign_keys_are_back_on_and_clean_after_rebuilding_a_referenced_table__DoD13(db_engine: Engine) -> None:
    """DoD-13 — a successful Sync that rebuilds a table another table references leaves
    ``PRAGMA foreign_keys`` ON on the connection and ``foreign_key_check`` reporting nothing; the
    referencing rows and the rebuilt table's surviving data are intact.

    Step 003 DoD-13 (context.md D8).
    """
    registry = _family_registry()
    _create_all(db_engine, registry)
    _ddl(
        db_engine,
        "ALTER TABLE parents ADD COLUMN legacy TEXT",
        "INSERT INTO parents (id, label, legacy) VALUES (1, 'one', 'old-1')",
        "INSERT INTO parents (id, label, legacy) VALUES (2, 'two', 'old-2')",
        "INSERT INTO children (id, parent_id, note) VALUES (10, 1, 'first child')",
        "INSERT INTO children (id, parent_id, note) VALUES (11, 2, 'second child')",
    )
    assert _report_of(db_engine, registry, "parents").status == TableStatus.DRIFTED

    with db_engine.connect() as conn:
        report = sync_table(conn, registry, "parents")
        assert _foreign_keys_on(conn) == 1
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []

    _assert_in_sync(report, "parents")
    assert _column_names(db_engine, "parents") == ["id", "label"]
    assert _rows(db_engine, "parents") == [(1, "one"), (2, "two")]
    assert _rows(db_engine, "children") == [(10, 1, "first child"), (11, 2, "second child")]
    assert _read(db_engine, "PRAGMA foreign_key_check") == []


def test_foreign_keys_are_back_on_after_a_successful_plain_rebuild__DoD13(db_engine: Engine) -> None:
    """DoD-13 — after a successful Sync rebuild the connection reports ``foreign_keys`` ON.

    Step 003 DoD-13 (context.md D8).
    """
    _ddl(db_engine, *EXTRA_COLUMN_STATES["extra_column"])

    with db_engine.connect() as conn:
        sync_table(conn, _notes_registry(), "notes")
        assert _foreign_keys_on(conn) == 1


@pytest.mark.parametrize(
    "arrange", [*FAILING_REBUILDS, pytest.param(_arrange_orphaned_children, id="foreign_key_violation")]
)
def test_foreign_keys_are_back_on_after_a_failed_rebuild__DoD13(
    db_engine: Engine, arrange: Callable[[Engine], MetaData]
) -> None:
    """DoD-13 — the failure path restores ``PRAGMA foreign_keys`` ON on the connection too.

    Step 003 DoD-13 (context.md D8; 003.context.md "The pragma-inside-a-transaction trap").
    """
    registry = arrange(db_engine)
    table_name = "children" if "children" in registry.tables else "notes"

    with db_engine.connect() as conn:
        with pytest.raises(SchemaApplyFailedError):
            sync_table(conn, registry, table_name)
        assert _foreign_keys_on(conn) == 1


# =========================================================================== DoD-14


def test_a_rebuild_that_would_leave_a_foreign_key_violation_is_refused__DoD14(db_engine: Engine) -> None:
    """DoD-14 — a rebuild whose result fails ``foreign_key_check`` is rolled back and raises
    ``schema_apply_failed``; the table, its rows and its drift status are as they were.

    Step 003 DoD-14 (context.md D8).
    """
    registry = _arrange_orphaned_children(db_engine)
    before_master = _master(db_engine)
    before_rows = _rows(db_engine, "children")
    before_report = _report_of(db_engine, registry, "children")
    assert before_report.status == TableStatus.DRIFTED

    with pytest.raises(SchemaApplyFailedError) as raised:
        _apply(db_engine, sync_table, registry, "children")

    assert raised.value.code == "schema_apply_failed"
    assert raised.value.detail == {"table_name": "children", "operation": "sync"}
    assert _master(db_engine) == before_master
    assert _column_names(db_engine, "children") == ["id", "parent_id", "note", "legacy"]
    assert _rows(db_engine, "children") == before_rows
    assert _report_of(db_engine, registry, "children") == before_report


# =========================================================================== DoD-15

UNKNOWN_NAMES = [
    pytest.param("ghosts", id="absent_everywhere"),
    pytest.param("stranger", id="live_but_not_declared"),
    pytest.param("notes; DROP TABLE notes; --", id="semicolon_and_comment"),
    pytest.param('notes"; DROP TABLE stranger; --', id="double_quote"),
    pytest.param("notes' OR '1'='1", id="single_quote"),
    pytest.param("notes/* */", id="block_comment"),
    pytest.param("stranger)", id="parenthesis"),
]


@pytest.mark.parametrize(("operation", "_name"), OPERATIONS)
@pytest.mark.parametrize("table_name", UNKNOWN_NAMES)
def test_an_undeclared_table_name_is_refused_with_no_ddl__DoD15(
    db_engine: Engine, operation: Operation, _name: str, table_name: str
) -> None:
    """DoD-15 — a name the registry does not declare raises ``unknown_table`` (detail: the name)
    and emits no DDL — including a name that exists live but not in the registry, and a name
    carrying SQL punctuation, which is refused rather than executed.

    Step 003 DoD-15 (context.md D9).
    """
    _ddl(
        db_engine,
        NOTES_DDL,
        NOTES_INDEX_DDL,
        "INSERT INTO notes (id, name, note) VALUES (1, 'alpha', 'first')",
        "CREATE TABLE stranger (id INTEGER NOT NULL PRIMARY KEY, legacy TEXT)",
        "INSERT INTO stranger (id, legacy) VALUES (1, 'unknown to the registry')",
    )
    registry = _notes_registry()
    before_master = _master(db_engine)

    with db_engine.connect() as conn:
        with _recording(conn) as statements:
            with pytest.raises(UnknownTableError) as raised:
                operation(conn, registry, table_name)

    assert raised.value.code == "unknown_table"
    assert raised.value.http_status == 404
    assert raised.value.detail == {"table_name": table_name}
    assert not [s for s in statements if WRITE_STATEMENT.search(s) or s.lstrip().upper().startswith("CREATE")]
    assert not [s for s in statements if table_name in s]
    assert _master(db_engine) == before_master
    assert _rows(db_engine, "notes") == [(1, "alpha", "first")]
    assert _rows(db_engine, "stranger") == [(1, "unknown to the registry")]


# =========================================================================== DoD-17


@pytest.mark.parametrize("arrange", FAILING_REBUILDS)
def test_failed_sync_detail_is_table_and_operation_with_no_driver_text__DoD17(
    db_engine: Engine, arrange: Callable[[Engine], MetaData]
) -> None:
    """DoD-17 — ``schema_apply_failed``'s detail carries the table name and the operation, and
    neither the error nor any log line emitted during the failure carries a driver message or a
    stored value.

    Step 003 DoD-17 (context.md D9; deployment.md's redaction rule).
    """
    registry = arrange(db_engine)

    with _captured_logs() as lines:
        with pytest.raises(SchemaApplyFailedError) as raised:
            _apply(db_engine, sync_table, registry, "notes")

    error = raised.value
    assert error.detail == {"table_name": "notes", "operation": "sync"}
    for rendered in (str(error), repr(error.message), repr(error.detail), repr(error.to_wire())):
        assert not _carries_driver_text(rendered)
    assert not [line for line in lines if _carries_driver_text(line)]


@pytest.mark.parametrize(("operation", "operation_name"), OPERATIONS)
def test_failed_creation_names_its_operation_and_carries_no_driver_text__DoD17(
    db_engine: Engine, operation: Operation, operation_name: str
) -> None:
    """DoD-17 — a creation that fails in the driver (the declared index's name is already taken by
    another table's index) raises ``schema_apply_failed`` naming the table and the operation that
    was pressed, with no driver message in the error or the log. Create is one transaction, so the
    half-made table does not remain.

    Step 003 DoD-17 (context.md D9; Interface intent "One transaction").
    """
    _ddl(
        db_engine,
        "CREATE TABLE others (id INTEGER NOT NULL PRIMARY KEY, name TEXT)",
        "CREATE INDEX ix_notes_name ON others (name)",
    )
    before_master = _master(db_engine)

    with _captured_logs() as lines:
        with pytest.raises(SchemaApplyFailedError) as raised:
            _apply(db_engine, operation, _notes_registry(), "notes")

    error = raised.value
    assert error.detail == {"table_name": "notes", "operation": operation_name}
    for rendered in (str(error), repr(error.message), repr(error.detail), repr(error.to_wire())):
        assert not _carries_driver_text(rendered)
    assert not [line for line in lines if _carries_driver_text(line)]
    assert "notes" not in _table_names(db_engine)
    assert _master(db_engine) == before_master


def test_foreign_key_refusal_log_carries_no_stored_value__DoD17(db_engine: Engine) -> None:
    """DoD-17 — the ``foreign_key_check`` refusal logs no stored value and no driver text.

    Step 003 DoD-17 (context.md D9).
    """
    registry = _arrange_orphaned_children(db_engine)

    with _captured_logs() as lines:
        with pytest.raises(SchemaApplyFailedError) as raised:
            _apply(db_engine, sync_table, registry, "children")

    assert raised.value.detail == {"table_name": "children", "operation": "sync"}
    assert not _carries_driver_text(repr(raised.value.to_wire()))
    assert not [line for line in lines if _carries_driver_text(line)]


# =========================================================================== DoD-18


def test_no_count_is_issued_by_any_apply__DoD18(db_engine: Engine) -> None:
    """DoD-18 — neither operation counts rows: no statement sent for a create, a rebuild or a
    failed rebuild is a ``COUNT(...)``.

    Step 003 DoD-18 (R5, UC-066).
    """
    sent: list[str] = []
    with db_engine.connect() as conn:
        with _recording(conn) as statements:
            create_table(conn, _notes_registry(), "notes")
        sent.extend(statements)
    _ddl(db_engine, "DROP TABLE notes", *EXTRA_COLUMN_STATES["extra_column"])
    _ddl(db_engine, "INSERT INTO notes (id, name, note, legacy) VALUES (1, 'alpha', 'first', 'old')")
    with db_engine.connect() as conn:
        with _recording(conn) as statements:
            sync_table(conn, _notes_registry(), "notes")
        sent.extend(statements)
    _ddl(db_engine, "DROP TABLE notes")
    registry = _arrange_not_null_over_nulls(db_engine)
    with db_engine.connect() as conn:
        with _recording(conn) as statements:
            with pytest.raises(SchemaApplyFailedError):
                sync_table(conn, registry, "notes")
        sent.extend(statements)

    assert sent, "the operations were expected to send statements"
    assert not [s for s in sent if COUNT_CALL.search(s)]


def test_answers_and_errors_carry_no_count__DoD18(db_engine: Engine) -> None:
    """DoD-18 — the answer is the per-table report and nothing counted; the errors' detail carries
    only the names the spec gives them.

    Step 003 DoD-18 (R5).
    """
    report = _apply(db_engine, sync_table, _notes_registry(), "notes")
    assert type(report) is TableReport

    with pytest.raises(UnknownTableError) as unknown:
        _apply(db_engine, sync_table, _notes_registry(), "ghosts")
    assert set(unknown.value.detail) == {"table_name"}

    _ddl(db_engine, "DROP TABLE notes")
    registry = _arrange_not_null_over_nulls(db_engine)
    with pytest.raises(SchemaApplyFailedError) as failed:
        _apply(db_engine, sync_table, registry, "notes")
    assert set(failed.value.detail) == {"table_name", "operation"}
    for value in (*unknown.value.detail.values(), *failed.value.detail.values()):
        assert not isinstance(value, int)


def test_sync_module_source_contains_no_count_query__DoD18() -> None:
    """DoD-18 — ``db/sync.py`` contains no ``COUNT(`` SQL and no ``func.count``.

    Step 003 DoD-18 (R5).
    """
    source = inspect.getsource(sync_module)
    assert not re.search(r"\bCOUNT\s*\(", source)
    assert not re.search(r"\bfunc\s*\.\s*count\b", source)


# =========================================================================== DoD-19


def _imported_names(module: ModuleType) -> set[str]:
    """Every module (and ``module.name``) the given module imports, relative imports resolved."""
    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = module.__name__.split(".")[: -node.level]
                base = ".".join([*parts, *([node.module] if node.module else [])])
            names.add(base)
            names.update(f"{base}.{alias.name}" for alias in node.names)
    return names


def test_sync_module_imports_no_fastapi_name__DoD19() -> None:
    """DoD-19 — ``db/sync.py`` imports no ``fastapi`` name.

    Step 003 DoD-19 (backend-structure.md, routers versus services).
    """
    names = _imported_names(sync_module)
    assert not [name for name in names if name == "fastapi" or name.startswith("fastapi.")]


@pytest.mark.parametrize(("module", "forbidden"), [
    pytest.param(sync_module, "app.db.schema", id="sync_imports_no_schema"),
    pytest.param(drift_module, "app.db.schema", id="drift_imports_no_schema"),
    pytest.param(drift_module, "app.db.sync", id="drift_imports_no_sync"),
])
def test_import_boundaries_hold__DoD19(module: ModuleType, forbidden: str) -> None:
    """DoD-19 — ``db/sync.py`` imports ``app.db.schema`` nowhere, and ``db/drift.py`` imports
    neither the registry module nor ``db/sync.py`` (the drift/sync split is one-way).

    Step 003 DoD-19 (backend-structure.md, the drift/sync split).
    """
    names = _imported_names(module)
    assert not [name for name in names if name == forbidden or name.startswith(f"{forbidden}.")]


def test_the_registry_arrives_as_an_argument__DoD19() -> None:
    """DoD-19 — both operations take the registry as a parameter and the module holds no registry
    of its own.

    Step 003 DoD-19.
    """
    for operation in (create_table, sync_table):
        assert list(inspect.signature(operation).parameters) == ["connection", "registry", "table_name"]
    assert not [value for value in vars(sync_module).values() if isinstance(value, MetaData)]
