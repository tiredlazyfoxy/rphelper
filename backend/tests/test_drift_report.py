"""Tests for step 002 of feature 007 — the pure comparison and the registry walk.

Step file: ``docs/plans/007.schema-drift-and-remediation/002.comparison-walk-and-health-drift.md``.
Feature context: ``context.md`` D1 (the compared set and the deliberately uncompared set), D2 (the
three statuses), D3 (the ``metadata.tables``-only walk), R5 (no counts); ``002.context.md``
("Comparison rules that are easy to get subtly wrong").

DoD-1..DoD-10 live here. DoD-11..DoD-17 (the health roll-up) live in ``test_health.py``;
DoD-18 and DoD-19 are ``[manual/live]``.

Every database test runs against a real ``.sqlite`` file from the ``db_engine`` fixture, never
``:memory:`` and never a mock. Drift is produced by hand-written DDL on that file; the real
registry is never edited — every registry here is a purpose-built ``MetaData``.
"""

import builtins
import dataclasses
import re
import sqlite3
import typing
from collections.abc import Iterator
from datetime import date, datetime
from typing import Any

import pytest
from sqlalchemy import (
    CheckConstraint,
    Column,
    Connection,
    Engine,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    event,
    text,
)

from app.db.drift import (
    ColumnDifference,
    ColumnShape,
    DriftReport,
    IndexShape,
    TableReport,
    TableShape,
    TableStatus,
    build_drift_report,
    compare_table_shapes,
    read_declared_shape,
    read_live_shape,
    report_has_drift,
    report_has_missing,
)

# --------------------------------------------------------------------------- helpers

# The shape every "notes"-style table below declares, and the hand-written DDL that produces
# exactly that shape on disk (``id`` is written NOT NULL so it matches a declared primary key).
NOTES_COLUMNS_DDL = "id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL, note TEXT"

ID = ColumnShape(name="id", type_text="INTEGER", not_null=True)
NAME = ColumnShape(name="name", type_text="TEXT", not_null=True)
NOTE = ColumnShape(name="note", type_text="TEXT", not_null=False)
NAME_INDEX = IndexShape(columns=("name",), unique=False)

DECLARED_SHAPE = TableShape(columns=(ID, NAME, NOTE), indexes=frozenset({NAME_INDEX}))


def _notes(metadata: MetaData, name: str = "notes", *extra: Any) -> Table:
    """A purpose-made table: id INTEGER PK, name TEXT NOT NULL, note TEXT NULL (+ extras)."""
    return Table(
        name,
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("name", Text, nullable=False),
        Column("note", Text, nullable=True),
        *extra,
    )


def _ddl(engine: Engine, *statements: str) -> None:
    """Run hand-written DDL on the per-test SQLite file, committed."""
    with engine.connect() as conn:
        with conn.begin():
            for statement in statements:
                conn.execute(text(statement))


def _create(engine: Engine, *tables: Table) -> None:
    with engine.connect() as conn:
        with conn.begin():
            for table in tables:
                table.create(conn)


def _report(engine: Engine, metadata: MetaData) -> DriftReport:
    with engine.connect() as conn:
        return build_drift_report(conn, metadata)


def _entry(report: DriftReport, table_name: str) -> TableReport:
    matches = [entry for entry in report.tables if entry.table_name == table_name]
    assert len(matches) == 1, f"{table_name!r} appears {len(matches)} times in the report"
    return matches[0]


def _assert_no_differences(entry: TableReport) -> None:
    assert entry.missing_columns == ()
    assert entry.extra_columns == ()
    assert entry.changed_columns == ()
    assert entry.missing_indexes == ()
    assert entry.extra_indexes == ()


def _live_report(engine: Engine, table: Table) -> TableReport:
    """Compare ``table``'s declaration against whatever the file holds under its name."""
    with engine.connect() as conn:
        live = read_live_shape(conn, table.name)
    return compare_table_shapes(table.name, read_declared_shape(table), live)


# =========================================================================== DoD-1


def test_report_has_one_entry_per_registry_table_in_declaration_order__DoD1(db_engine: Engine) -> None:
    """DoD-1 — one entry per registry table, in declaration order (not alphabetical), each with
    its own status.

    Step 002 DoD-1 (US-017.AC-1, UC-014; 002.context.md "Declaration order, not alphabetical").
    """
    registry = MetaData()
    zeta = _notes(registry, "zeta_notes")
    _notes(registry, "alpha_notes")
    _notes(registry, "mid_notes")
    _create(db_engine, zeta)
    _ddl(db_engine, f"CREATE TABLE mid_notes ({NOTES_COLUMNS_DDL}, legacy TEXT)")

    report = _report(db_engine, registry)

    assert [entry.table_name for entry in report.tables] == ["zeta_notes", "alpha_notes", "mid_notes"]
    assert [entry.status for entry in report.tables] == [
        TableStatus.IN_SYNC,
        TableStatus.MISSING,
        TableStatus.DRIFTED,
    ]


def test_report_for_an_empty_registry_is_empty__DoD1(db_engine: Engine) -> None:
    """DoD-1 — one entry per registry table: a registry declaring nothing yields no entry.

    Step 002 DoD-1.
    """
    _create(db_engine, _notes(MetaData()))

    report = _report(db_engine, MetaData())

    assert report.tables == ()


# =========================================================================== DoD-2


def test_absent_live_shape_is_reported_missing_with_empty_lists__DoD2() -> None:
    """DoD-2 — an absent live shape reports status missing, and the difference lists stay empty
    (a missing table is one fact, not "every declared column is missing").

    Step 002 DoD-2 (US-017.AC-1, UC-014; 002.context.md "An absent live shape short-circuits").
    """
    entry = compare_table_shapes("notes", DECLARED_SHAPE, None)

    assert entry.table_name == "notes"
    assert entry.status == TableStatus.MISSING
    _assert_no_differences(entry)


def test_declared_table_absent_from_the_database_is_reported_missing__DoD2(db_engine: Engine) -> None:
    """DoD-2 — walking a registry whose table the file does not have reports it missing.

    Step 002 DoD-2.
    """
    registry = MetaData()
    _notes(registry, "notes", Index("ix_notes_name", "name"))
    _create(db_engine, _notes(MetaData(), "unrelated"))

    entry = _entry(_report(db_engine, registry), "notes")

    assert entry.status == TableStatus.MISSING
    _assert_no_differences(entry)


# =========================================================================== DoD-3


def test_identical_shapes_are_in_sync__DoD3() -> None:
    """DoD-3 — a live shape equal to the declared shape is in sync with every list empty.

    Step 002 DoD-3 (US-017.AC-1, UC-014; D2 — status is derived from the lists).
    """
    entry = compare_table_shapes("notes", DECLARED_SHAPE, DECLARED_SHAPE)

    assert entry.status == TableStatus.IN_SYNC
    _assert_no_differences(entry)


def test_table_created_from_its_declaration_is_in_sync__DoD3(db_engine: Engine) -> None:
    """DoD-3 — a table created from its own ``Table`` (with an explicit index) reports in sync.

    Step 002 DoD-3.
    """
    registry = MetaData()
    table = _notes(registry, "notes", Index("ix_notes_name", "name"))
    _create(db_engine, table)

    entry = _entry(_report(db_engine, registry), "notes")

    assert entry.status == TableStatus.IN_SYNC
    _assert_no_differences(entry)


def test_hand_written_table_matching_the_declaration_is_in_sync__DoD3(db_engine: Engine) -> None:
    """DoD-3 — a hand-written table whose shape matches the declaration exactly is in sync
    (the baseline every hand-drift test below departs from).

    Step 002 DoD-3.
    """
    registry = MetaData()
    _notes(registry)
    _ddl(db_engine, f"CREATE TABLE notes ({NOTES_COLUMNS_DDL})")

    entry = _entry(_report(db_engine, registry), "notes")

    assert entry.status == TableStatus.IN_SYNC
    _assert_no_differences(entry)


def test_unique_column_without_explicit_index_is_in_sync__DoD3(db_engine: Engine) -> None:
    """DoD-3 — a table whose only uniqueness is a ``unique=True`` column and which declares no
    explicit index reports in sync (SQLite's implicit index is not an extra index).

    Step 002 DoD-3 (context.md D1: implicit indexes are not live indexes).
    """
    registry = MetaData()
    table = Table(
        "accounts",
        registry,
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("username", Text, nullable=False, unique=True),
        Column("bio", Text, nullable=True),
    )
    _create(db_engine, table)

    entry = _entry(_report(db_engine, registry), "accounts")

    assert entry.status == TableStatus.IN_SYNC
    _assert_no_differences(entry)


# =========================================================================== DoD-4


def test_missing_column_is_drifted_and_listed_missing__DoD4() -> None:
    """DoD-4 — a declared column the live shape lacks lands in ``missing_columns`` only.

    Step 002 DoD-4 (US-017.AC-1, UC-014; context.md D1).
    """
    live = TableShape(columns=(ID, NAME), indexes=frozenset({NAME_INDEX}))

    entry = compare_table_shapes("notes", DECLARED_SHAPE, live)

    assert entry.status == TableStatus.DRIFTED
    assert entry.missing_columns == ("note",)
    assert entry.extra_columns == ()
    assert entry.changed_columns == ()
    assert entry.missing_indexes == ()
    assert entry.extra_indexes == ()


def test_extra_column_is_drifted_and_listed_extra__DoD4() -> None:
    """DoD-4 — a live column the registry no longer declares lands in ``extra_columns`` only.

    Step 002 DoD-4.
    """
    legacy = ColumnShape(name="legacy", type_text="TEXT", not_null=False)
    live = TableShape(columns=(ID, NAME, NOTE, legacy), indexes=frozenset({NAME_INDEX}))

    entry = compare_table_shapes("notes", DECLARED_SHAPE, live)

    assert entry.status == TableStatus.DRIFTED
    assert entry.missing_columns == ()
    assert entry.extra_columns == ("legacy",)
    assert entry.changed_columns == ()
    assert entry.missing_indexes == ()
    assert entry.extra_indexes == ()


def test_changed_type_is_drifted_with_expected_and_actual__DoD4() -> None:
    """DoD-4 — a column on both sides whose type differs lands in ``changed_columns`` only,
    carrying both the expected and the actual shape.

    Step 002 DoD-4.
    """
    retyped = ColumnShape(name="note", type_text="INTEGER", not_null=False)
    live = TableShape(columns=(ID, NAME, retyped), indexes=frozenset({NAME_INDEX}))

    entry = compare_table_shapes("notes", DECLARED_SHAPE, live)

    assert entry.status == TableStatus.DRIFTED
    assert entry.missing_columns == ()
    assert entry.extra_columns == ()
    assert entry.changed_columns == (ColumnDifference(name="note", expected=NOTE, actual=retyped),)


def test_changed_nullability_is_drifted_with_expected_and_actual__DoD4() -> None:
    """DoD-4 — a column on both sides whose NOT NULL flag differs lands in ``changed_columns``
    only, carrying both the expected and the actual shape.

    Step 002 DoD-4.
    """
    tightened = ColumnShape(name="note", type_text="TEXT", not_null=True)
    live = TableShape(columns=(ID, NAME, tightened), indexes=frozenset({NAME_INDEX}))

    entry = compare_table_shapes("notes", DECLARED_SHAPE, live)

    assert entry.status == TableStatus.DRIFTED
    assert entry.missing_columns == ()
    assert entry.extra_columns == ()
    assert entry.changed_columns == (ColumnDifference(name="note", expected=NOTE, actual=tightened),)


def test_live_table_missing_a_declared_column_is_drifted__DoD4(db_engine: Engine) -> None:
    """DoD-4 — on a real file: a table hand-created without a declared column is drifted and
    names that column as missing.

    Step 002 DoD-4.
    """
    registry = MetaData()
    _notes(registry)
    _ddl(db_engine, "CREATE TABLE notes (id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL)")

    entry = _entry(_report(db_engine, registry), "notes")

    assert entry.status == TableStatus.DRIFTED
    assert entry.missing_columns == ("note",)
    assert entry.extra_columns == ()
    assert entry.changed_columns == ()


def test_live_table_with_an_undeclared_column_is_drifted__DoD4(db_engine: Engine) -> None:
    """DoD-4 — on a real file: a table carrying a column the registry does not declare is drifted
    and names that column as extra.

    Step 002 DoD-4.
    """
    registry = MetaData()
    _notes(registry)
    _ddl(db_engine, f"CREATE TABLE notes ({NOTES_COLUMNS_DDL}, legacy TEXT)")

    entry = _entry(_report(db_engine, registry), "notes")

    assert entry.status == TableStatus.DRIFTED
    assert entry.missing_columns == ()
    assert entry.extra_columns == ("legacy",)
    assert entry.changed_columns == ()


def test_live_column_with_a_changed_type_is_drifted__DoD4(db_engine: Engine) -> None:
    """DoD-4 — on a real file: ``note`` written as INTEGER where TEXT is declared is a changed
    column with expected TEXT/nullable and actual INTEGER/nullable.

    Step 002 DoD-4.
    """
    registry = MetaData()
    _notes(registry)
    _ddl(db_engine, "CREATE TABLE notes (id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL, note INTEGER)")

    entry = _entry(_report(db_engine, registry), "notes")

    assert entry.status == TableStatus.DRIFTED
    assert entry.missing_columns == ()
    assert entry.extra_columns == ()
    assert entry.changed_columns == (
        ColumnDifference(
            name="note",
            expected=ColumnShape(name="note", type_text="TEXT", not_null=False),
            actual=ColumnShape(name="note", type_text="INTEGER", not_null=False),
        ),
    )


def test_live_column_with_changed_nullability_is_drifted__DoD4(db_engine: Engine) -> None:
    """DoD-4 — on a real file: ``note`` written NOT NULL where it is declared nullable is a
    changed column with expected nullable and actual NOT NULL, same type.

    Step 002 DoD-4.
    """
    registry = MetaData()
    _notes(registry)
    _ddl(
        db_engine,
        "CREATE TABLE notes (id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL, note TEXT NOT NULL)",
    )

    entry = _entry(_report(db_engine, registry), "notes")

    assert entry.status == TableStatus.DRIFTED
    assert entry.missing_columns == ()
    assert entry.extra_columns == ()
    assert entry.changed_columns == (
        ColumnDifference(
            name="note",
            expected=ColumnShape(name="note", type_text="TEXT", not_null=False),
            actual=ColumnShape(name="note", type_text="TEXT", not_null=True),
        ),
    )


def test_a_column_is_never_named_in_two_lists__DoD4() -> None:
    """DoD-4 — missing and extra are set differences over names and changed is over the
    intersection: with one column missing, one extra and one changed, each is named exactly once.

    Step 002 DoD-4 (002.context.md "missing and extra are set differences over names").
    """
    retyped_name = ColumnShape(name="name", type_text="VARCHAR(10)", not_null=True)
    legacy = ColumnShape(name="legacy", type_text="TEXT", not_null=False)
    live = TableShape(columns=(ID, retyped_name, legacy), indexes=frozenset({NAME_INDEX}))

    entry = compare_table_shapes("notes", DECLARED_SHAPE, live)

    assert entry.status == TableStatus.DRIFTED
    assert entry.missing_columns == ("note",)
    assert entry.extra_columns == ("legacy",)
    assert entry.changed_columns == (ColumnDifference(name="name", expected=NAME, actual=retyped_name),)


# =========================================================================== DoD-5


def test_missing_index_is_drifted_and_listed_missing__DoD5() -> None:
    """DoD-5 — a declared index absent from the live shape lands in ``missing_indexes``.

    Step 002 DoD-5 (US-017.AC-1; context.md D1).
    """
    live = TableShape(columns=(ID, NAME, NOTE), indexes=frozenset())

    entry = compare_table_shapes("notes", DECLARED_SHAPE, live)

    assert entry.status == TableStatus.DRIFTED
    assert entry.missing_indexes == (NAME_INDEX,)
    assert entry.extra_indexes == ()
    assert entry.missing_columns == ()
    assert entry.extra_columns == ()
    assert entry.changed_columns == ()


def test_extra_index_is_drifted_and_listed_extra__DoD5() -> None:
    """DoD-5 — a live index the registry no longer declares lands in ``extra_indexes``.

    Step 002 DoD-5.
    """
    note_index = IndexShape(columns=("note",), unique=False)
    live = TableShape(columns=(ID, NAME, NOTE), indexes=frozenset({NAME_INDEX, note_index}))

    entry = compare_table_shapes("notes", DECLARED_SHAPE, live)

    assert entry.status == TableStatus.DRIFTED
    assert entry.missing_indexes == ()
    assert entry.extra_indexes == (note_index,)
    assert entry.missing_columns == ()
    assert entry.extra_columns == ()
    assert entry.changed_columns == ()


def test_uniqueness_is_part_of_index_identity__DoD5() -> None:
    """DoD-5 — identity is (columns, uniqueness): the same columns declared unique but live
    non-unique is one missing index and one extra index.

    Step 002 DoD-5.
    """
    declared = TableShape(columns=(ID, NAME, NOTE), indexes=frozenset({IndexShape(columns=("name",), unique=True)}))
    live = TableShape(columns=(ID, NAME, NOTE), indexes=frozenset({IndexShape(columns=("name",), unique=False)}))

    entry = compare_table_shapes("notes", declared, live)

    assert entry.status == TableStatus.DRIFTED
    assert entry.missing_indexes == (IndexShape(columns=("name",), unique=True),)
    assert entry.extra_indexes == (IndexShape(columns=("name",), unique=False),)


def test_live_table_without_a_declared_index_is_drifted__DoD5(db_engine: Engine) -> None:
    """DoD-5 — on a real file: a declared index the table lacks is listed missing.

    Step 002 DoD-5.
    """
    registry = MetaData()
    _notes(registry, "notes", Index("ix_notes_name", "name"))
    _ddl(db_engine, f"CREATE TABLE notes ({NOTES_COLUMNS_DDL})")

    entry = _entry(_report(db_engine, registry), "notes")

    assert entry.status == TableStatus.DRIFTED
    assert entry.missing_indexes == (IndexShape(columns=("name",), unique=False),)
    assert entry.extra_indexes == ()
    assert entry.missing_columns == ()
    assert entry.extra_columns == ()
    assert entry.changed_columns == ()


def test_live_index_the_registry_does_not_declare_is_drifted__DoD5(db_engine: Engine) -> None:
    """DoD-5 — on a real file: a hand-created index the registry does not declare is listed extra.

    Step 002 DoD-5.
    """
    registry = MetaData()
    _notes(registry)
    _ddl(
        db_engine,
        f"CREATE TABLE notes ({NOTES_COLUMNS_DDL})",
        "CREATE UNIQUE INDEX ix_hand_made ON notes (name, note)",
    )

    entry = _entry(_report(db_engine, registry), "notes")

    assert entry.status == TableStatus.DRIFTED
    assert entry.missing_indexes == ()
    assert entry.extra_indexes == (IndexShape(columns=("name", "note"), unique=True),)
    assert entry.missing_columns == ()
    assert entry.extra_columns == ()
    assert entry.changed_columns == ()


def test_index_name_difference_alone_is_not_drift__DoD5(db_engine: Engine) -> None:
    """DoD-5 — a live index over the declared columns with the declared uniqueness but a
    different name leaves the table in sync.

    Step 002 DoD-5.
    """
    registry = MetaData()
    _notes(registry, "notes", Index("ix_notes_name_declared", "name"))
    _ddl(
        db_engine,
        f"CREATE TABLE notes ({NOTES_COLUMNS_DDL})",
        "CREATE INDEX some_other_name_entirely ON notes (name)",
    )

    entry = _entry(_report(db_engine, registry), "notes")

    assert entry.status == TableStatus.IN_SYNC
    _assert_no_differences(entry)


# =========================================================================== DoD-6


def test_live_default_check_and_foreign_key_absent_from_declaration_stay_in_sync__DoD6(
    db_engine: Engine,
) -> None:
    """DoD-6 — a server default, a CHECK constraint and a foreign-key clause present live but
    not declared leave the table in sync.

    Step 002 DoD-6 (context.md D1 — deliberately outside the compared set).
    """
    registry = MetaData()
    _notes(registry, "parent")
    child = Table(
        "child",
        registry,
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("name", Text, nullable=False),
        Column("parent_id", Integer, nullable=True),
    )
    _ddl(
        db_engine,
        f"CREATE TABLE parent ({NOTES_COLUMNS_DDL})",
        "CREATE TABLE child ("
        " id INTEGER NOT NULL PRIMARY KEY,"
        " name TEXT NOT NULL DEFAULT 'unnamed' CHECK (length(name) > 0),"
        " parent_id INTEGER REFERENCES parent (id) ON DELETE CASCADE,"
        " CHECK (id > 0))",
    )

    entry = _live_report(db_engine, child)
    walked = _entry(_report(db_engine, registry), "child")

    for report in (entry, walked):
        assert report.status == TableStatus.IN_SYNC
        _assert_no_differences(report)


def test_declared_default_check_and_foreign_key_absent_live_stay_in_sync__DoD6(db_engine: Engine) -> None:
    """DoD-6 — the reverse: a declared server default, CHECK constraint and foreign key that the
    live table does not carry leave the table in sync.

    Step 002 DoD-6.
    """
    registry = MetaData()
    _notes(registry, "parent")
    child = Table(
        "child",
        registry,
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("name", Text, nullable=False, server_default="unnamed"),
        Column("parent_id", Integer, ForeignKey("parent.id", ondelete="CASCADE"), nullable=True),
        CheckConstraint("length(name) > 0", name="ck_child_name_not_empty"),
    )
    _ddl(
        db_engine,
        f"CREATE TABLE parent ({NOTES_COLUMNS_DDL})",
        "CREATE TABLE child (id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL, parent_id INTEGER)",
    )

    entry = _live_report(db_engine, child)
    walked = _entry(_report(db_engine, registry), "child")

    for report in (entry, walked):
        assert report.status == TableStatus.IN_SYNC
        _assert_no_differences(report)


# =========================================================================== DoD-7


def test_comparison_takes_no_connection_parameter__DoD7() -> None:
    """DoD-7 — the comparison's parameters are the table name and two shapes; no connection.

    Step 002 DoD-7 (backend-structure.md, the drift/sync split).
    """
    hints = typing.get_type_hints(compare_table_shapes)
    hints.pop("return", None)

    assert Connection not in hints.values()
    assert all(hint is not Engine for hint in hints.values())


def test_comparison_returns_a_full_report_with_no_io_available__DoD7(monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD-7 — called with two shape values while opening a file or a SQLite database raises,
    the comparison still returns a complete report: it performs no I/O.

    Step 002 DoD-7.
    """

    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the pure comparison attempted I/O")

    legacy = ColumnShape(name="legacy", type_text="TEXT", not_null=False)
    live = TableShape(columns=(ID, NAME, legacy), indexes=frozenset())

    monkeypatch.setattr(sqlite3, "connect", refuse)
    monkeypatch.setattr(builtins, "open", refuse)
    entry = compare_table_shapes("notes", DECLARED_SHAPE, live)
    missing = compare_table_shapes("notes", DECLARED_SHAPE, None)
    monkeypatch.undo()

    assert isinstance(entry, TableReport)
    assert entry.table_name == "notes"
    assert entry.status == TableStatus.DRIFTED
    assert entry.missing_columns == ("note",)
    assert entry.extra_columns == ("legacy",)
    assert entry.changed_columns == ()
    assert entry.missing_indexes == (NAME_INDEX,)
    assert entry.extra_indexes == ()
    assert missing.status == TableStatus.MISSING


# =========================================================================== DoD-8


def test_undeclared_live_table_and_view_appear_nowhere_in_the_report__DoD8(db_engine: Engine) -> None:
    """DoD-8 — a table (and a view) the file has but the registry does not declare appears in no
    entry; the report has exactly the registry's tables.

    Step 002 DoD-8 (context.md D3).
    """
    registry = MetaData()
    _notes(registry)
    _ddl(
        db_engine,
        f"CREATE TABLE notes ({NOTES_COLUMNS_DDL})",
        "CREATE TABLE stranger_table (id INTEGER NOT NULL PRIMARY KEY, secret TEXT)",
        "CREATE VIEW stranger_view AS SELECT id FROM stranger_table",
    )

    report = _report(db_engine, registry)

    assert [entry.table_name for entry in report.tables] == ["notes"]
    assert "stranger" not in repr(report)


class _Recorder:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.events: list[str] = []


@pytest.fixture
def recorded_connection(db_engine: Engine) -> Iterator[tuple[Connection, _Recorder]]:
    """A connection with listeners recording every cursor statement and transaction event."""
    recorder = _Recorder()
    with db_engine.connect() as conn:

        def on_statement(
            _conn: Connection, _cursor: Any, statement: str, _params: Any, _context: Any, _many: bool
        ) -> None:
            recorder.statements.append(statement)

        def recording(event_name: str) -> Any:
            def on_event(*_args: Any) -> None:
                recorder.events.append(event_name)

            return on_event

        event.listen(conn, "before_cursor_execute", on_statement)
        for name in ("begin", "commit", "rollback", "savepoint", "release_savepoint", "rollback_savepoint"):
            event.listen(conn, name, recording(name))
        yield conn, recorder


def test_walk_never_inspects_an_undeclared_table__DoD8(
    db_engine: Engine, recorded_connection: tuple[Connection, _Recorder]
) -> None:
    """DoD-8 — the walk visits ``metadata.tables`` only: no statement it issues names a table
    the registry does not declare.

    Step 002 DoD-8.
    """
    registry = MetaData()
    _notes(registry)
    _ddl(
        db_engine,
        f"CREATE TABLE notes ({NOTES_COLUMNS_DDL})",
        "CREATE TABLE stranger_table (id INTEGER NOT NULL PRIMARY KEY, secret TEXT)",
    )
    conn, recorder = recorded_connection

    with conn.begin():
        recorder.statements.clear()
        build_drift_report(conn, registry)
        issued = list(recorder.statements)

    assert issued, "the walk issued no statement at all"
    assert [statement for statement in issued if "stranger" in statement.lower()] == []


# =========================================================================== DoD-9

_FORBIDDEN_FIELD = re.compile(r"count|rows|size|bytes|time|date|_at$", re.IGNORECASE)
_COUNT_CALL = re.compile(r"\bcount\s*\(", re.IGNORECASE)


def _populated(engine: Engine) -> MetaData:
    """A registry of three tables on disk — in sync, drifted, missing — with rows in two."""
    registry = MetaData()
    diary = _notes(registry, "diary", Index("ix_diary_name", "name"))
    _notes(registry, "ledger")
    _notes(registry, "absent_book")
    _create(engine, diary)
    _ddl(engine, f"CREATE TABLE ledger ({NOTES_COLUMNS_DDL}, legacy TEXT)")
    with engine.connect() as conn:
        with conn.begin():
            for table_name in ("diary", "ledger"):
                for row_id in range(1, 6):
                    conn.execute(
                        text(f"INSERT INTO {table_name} (id, name, note) VALUES (:id, :name, NULL)"),
                        {"id": row_id, "name": f"row {row_id}"},
                    )
    return registry


def _scalar_values(value: Any) -> Iterator[Any]:
    """Every leaf value reachable from a report value (dataclasses, tuples, sets flattened)."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        for field in dataclasses.fields(value):
            yield from _scalar_values(getattr(value, field.name))
    elif isinstance(value, tuple | list | set | frozenset):
        for item in value:
            yield from _scalar_values(item)
    else:
        yield value


def test_report_entries_carry_no_count_size_or_timestamp__DoD9(db_engine: Engine) -> None:
    """DoD-9 — no entry of a built report carries a row count, a byte size or a timestamp: no
    field is named for one, and no value anywhere in the report is a number or a date.

    Step 002 DoD-9 (R5, UC-066).
    """
    report = _report(db_engine, _populated(db_engine))

    assert len(report.tables) == 3
    for entry in report.tables:
        names = [field.name for field in dataclasses.fields(entry)]
        assert [name for name in names if _FORBIDDEN_FIELD.search(name)] == [], entry.table_name
    for leaf in _scalar_values(report):
        assert isinstance(leaf, str | bool), repr(leaf)
        assert not isinstance(leaf, datetime | date)


def test_building_the_report_issues_no_count__DoD9(
    db_engine: Engine, recorded_connection: tuple[Connection, _Recorder]
) -> None:
    """DoD-9 — building the whole report over populated tables issues no ``COUNT(`` statement.

    Step 002 DoD-9 (R5).
    """
    registry = _populated(db_engine)
    conn, recorder = recorded_connection

    with conn.begin():
        recorder.statements.clear()
        build_drift_report(conn, registry)
        issued = list(recorder.statements)

    assert issued, "the walk issued no statement at all"
    assert [statement for statement in issued if _COUNT_CALL.search(statement)] == []


# =========================================================================== DoD-10


def _snapshot(engine: Engine) -> tuple[Any, ...]:
    """sqlite_master, the schema version and every row, read from a separate connection."""
    with engine.connect() as conn:
        master = conn.execute(
            text("SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name")
        ).all()
        version = conn.execute(text("PRAGMA schema_version")).scalar()
        rows = tuple(
            tuple(conn.execute(text(f"SELECT id, name, note FROM {name} ORDER BY id")).all())
            for name in ("diary", "ledger")
        )
        conn.rollback()
    return (tuple(master), version, rows)


def test_building_the_report_leaves_schema_and_rows_unchanged__DoD10(db_engine: Engine) -> None:
    """DoD-10 — on a connection with no ``begin()`` around it, building the report over a
    database with a missing and a drifted table changes neither ``sqlite_master`` nor any row,
    and the connection records no change.

    Step 002 DoD-10 (backend-structure.md: "the code path that only reports cannot write").
    """
    registry = _populated(db_engine)
    before = _snapshot(db_engine)

    with db_engine.connect() as conn:
        changes_before = conn.execute(text("SELECT total_changes()")).scalar()
        conn.rollback()
        report = build_drift_report(conn, registry)
        changes_after = conn.execute(text("SELECT total_changes()")).scalar()

    assert [entry.status for entry in report.tables] == [
        TableStatus.IN_SYNC,
        TableStatus.DRIFTED,
        TableStatus.MISSING,
    ]
    assert changes_after == changes_before
    assert _snapshot(db_engine) == before


def test_building_the_report_opens_no_transaction__DoD10(
    db_engine: Engine, recorded_connection: tuple[Connection, _Recorder]
) -> None:
    """DoD-10 — inside the caller's transaction, the walk begins, commits, rolls back and
    savepoints nothing; the caller's transaction is still in force and still undoes the
    caller's own uncommitted change.

    Step 002 DoD-10.
    """
    registry = _populated(db_engine)
    before = _snapshot(db_engine)
    conn, recorder = recorded_connection

    outer = conn.begin()
    conn.execute(text("INSERT INTO diary (id, name, note) VALUES (99, 'uncommitted', NULL)"))
    recorder.statements.clear()
    recorder.events.clear()

    build_drift_report(conn, registry)

    assert recorder.events == []
    assert conn.get_transaction() is outer
    assert outer.is_active
    outer.rollback()
    assert _snapshot(db_engine) == before


def test_building_the_report_issues_only_pragma_reads_and_selects__DoD10(
    db_engine: Engine, recorded_connection: tuple[Connection, _Recorder]
) -> None:
    """DoD-10 — every statement the walk issues is a ``PRAGMA`` read or a ``SELECT``: no DDL, no
    DML, no transaction control, no pragma assignment.

    Step 002 DoD-10.
    """
    registry = _populated(db_engine)
    conn, recorder = recorded_connection

    with conn.begin():
        recorder.statements.clear()
        build_drift_report(conn, registry)
        issued = list(recorder.statements)

    assert issued, "the walk issued no statement at all"
    for statement in issued:
        head = statement.lstrip().upper()
        assert head.startswith(("PRAGMA", "SELECT")), statement
        if head.startswith("PRAGMA"):
            assert "=" not in head, statement


# ============================================ roll-up predicates (support DoD-11, 12, 14)


def _report_of(*statuses: TableStatus) -> DriftReport:
    return DriftReport(
        tables=tuple(
            TableReport(
                table_name=f"t{index}",
                status=status,
                missing_columns=(),
                extra_columns=("legacy",) if status == TableStatus.DRIFTED else (),
                changed_columns=(),
                missing_indexes=(),
                extra_indexes=(),
            )
            for index, status in enumerate(statuses)
        )
    )


@pytest.mark.parametrize(
    ("statuses", "has_missing", "has_drift"),
    [
        ((), False, False),
        ((TableStatus.IN_SYNC, TableStatus.IN_SYNC), False, False),
        ((TableStatus.IN_SYNC, TableStatus.MISSING), True, False),
        ((TableStatus.DRIFTED, TableStatus.IN_SYNC), False, True),
        ((TableStatus.MISSING, TableStatus.DRIFTED), True, True),
    ],
)
def test_roll_up_predicates_read_the_report_statuses__DoD11_DoD12_DoD14(
    statuses: tuple[TableStatus, ...], has_missing: bool, has_drift: bool
) -> None:
    """DoD-11 / DoD-12 / DoD-14 — the predicate pair the health roll-up consumes: "any table
    missing" and "any table drifted", read straight off the report's statuses.

    Step 002 Interface intent (the roll-up predicate pair); DoD-11, DoD-12, DoD-14.
    """
    report = _report_of(*statuses)

    assert report_has_missing(report) is has_missing
    assert report_has_drift(report) is has_drift
