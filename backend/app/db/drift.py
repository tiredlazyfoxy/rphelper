"""Schema drift — diagnosis only (feature 007).

`docs/architecture/backend-structure.md`: "the code path that only reports cannot write".
This module issues `PRAGMA` reads and `SELECT`s only, opens **no** transaction, emits
**no** DDL, and never imports `app.db.sync`. It never imports `app.db.schema` either: the
registry and every `Table` arrive as arguments.

Step 001 declares the value types and the two shape readers (live via `PRAGMA`, declared
via the `Table` object), which answer in the **same** value types. Step 002 adds the pure
comparison and the registry walk that populate the report values declared here.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import Connection, MetaData, Table, text
from sqlalchemy.dialects import sqlite

#: Any run of whitespace, collapsed to one space by `normalize_type_text`.
_WHITESPACE = re.compile(r"\s+")
#: A space beside `(`, `)` or `,` carries no meaning in a type text: `VARCHAR (50)` is
#: `VARCHAR(50)` and `NUMERIC(10, 2)` is `NUMERIC(10,2)`.
_SPACE_AROUND_PUNCTUATION = re.compile(r" ?([(),]) ?")


class TableStatus(StrEnum):
    """The closed per-table status set (`context.md` D2). Values are the wire values."""

    IN_SYNC = "in_sync"
    MISSING = "missing"
    DRIFTED = "drifted"


@dataclass(frozen=True)
class ColumnShape:
    """A column's compared shape: name, normalised SQLite type text, NOT NULL flag."""

    name: str
    type_text: str
    not_null: bool


@dataclass(frozen=True)
class IndexShape:
    """An index's identity: its columns in indexed order and its uniqueness. No name."""

    columns: tuple[str, ...]
    unique: bool


@dataclass(frozen=True)
class TableShape:
    """A table's column shapes (column order) and its explicitly created index shapes."""

    columns: tuple[ColumnShape, ...]
    indexes: frozenset[IndexShape]


@dataclass(frozen=True)
class ColumnDifference:
    """A column present on both sides whose type text or NOT NULL flag differs."""

    name: str
    expected: ColumnShape
    actual: ColumnShape


@dataclass(frozen=True)
class TableReport:
    """One table's drift report. No row count, no size, no timestamp (R5)."""

    table_name: str
    status: TableStatus
    missing_columns: tuple[str, ...]
    extra_columns: tuple[str, ...]
    changed_columns: tuple[ColumnDifference, ...]
    missing_indexes: tuple[IndexShape, ...]
    extra_indexes: tuple[IndexShape, ...]


@dataclass(frozen=True)
class DriftReport:
    """The whole report: the per-table reports, in registry declaration order."""

    tables: tuple[TableReport, ...]


def normalize_type_text(type_text: str) -> str:
    """Upper-case and collapse whitespace so `text`/`TEXT`, `VARCHAR (50)`/`VARCHAR(50)` agree."""
    collapsed = _WHITESPACE.sub(" ", type_text.strip().upper())
    return _SPACE_AROUND_PUNCTUATION.sub(r"\1", collapsed)


def _quote_identifier(name: str) -> str:
    """Quote a name as an SQLite identifier, doubling any embedded double quote."""
    return '"' + name.replace('"', '""') + '"'


def read_live_shape(connection: Connection, table_name: str) -> TableShape | None:
    """Read a table's live shape via `PRAGMA table_info` / `index_list` / `index_info`.

    Returns `None` when the table does not exist. Writes nothing, opens no transaction.
    """
    # table_info rows: (cid, name, type, notnull, dflt_value, pk) — only the first four
    # are read; defaults and primary-key position are deliberately not compared (D1).
    column_rows = connection.execute(
        text(f"PRAGMA table_info({_quote_identifier(table_name)})")
    ).fetchall()
    if not column_rows:
        return None
    columns = tuple(
        ColumnShape(
            name=str(row[1]),
            type_text=normalize_type_text(str(row[2] or "")),
            not_null=bool(row[3]),
        )
        for row in sorted(column_rows, key=lambda row: int(row[0]))
    )

    # index_list rows: (seq, name, unique, origin, partial). Only origin 'c' — an index
    # created by CREATE INDEX — counts; 'u' (UNIQUE) and 'pk' are implicit (D1).
    index_rows = connection.execute(
        text(f"PRAGMA index_list({_quote_identifier(table_name)})")
    ).fetchall()
    indexes: set[IndexShape] = set()
    for index_row in index_rows:
        if str(index_row[3]) != "c":
            continue
        # index_info rows: (seqno, cid, name); seqno is the position in the index.
        info_rows = connection.execute(
            text(f"PRAGMA index_info({_quote_identifier(str(index_row[1]))})")
        ).fetchall()
        index_columns = tuple(
            str(info_row[2]) for info_row in sorted(info_rows, key=lambda info_row: int(info_row[0]))
        )
        indexes.add(IndexShape(columns=index_columns, unique=bool(index_row[2])))

    return TableShape(columns=columns, indexes=frozenset(indexes))


def read_declared_shape(table: Table) -> TableShape:
    """Read a registry `Table`'s declared shape, compiled through the SQLite dialect. No I/O."""
    dialect = sqlite.dialect()
    columns = tuple(
        ColumnShape(
            name=column.name,
            type_text=normalize_type_text(column.type.compile(dialect=dialect)),
            not_null=not column.nullable,
        )
        for column in table.columns
    )
    # `Table.indexes` only: a `unique=True` column is a constraint, not an index (D1).
    indexes = frozenset(
        IndexShape(
            columns=tuple(column.name for column in index.columns),
            unique=bool(index.unique),
        )
        for index in table.indexes
    )
    return TableShape(columns=columns, indexes=indexes)


def compare_table_shapes(table_name: str, declared: TableShape, live: TableShape | None) -> TableReport:
    """Compare one table's declared shape against its live shape. Pure: no I/O at all.

    `live is None` means the table does not exist: status missing, every list empty.
    Otherwise missing/extra are name set differences, changed is over the intersection
    (type text or NOT NULL differs), indexes compare by (columns, uniqueness); status is
    in sync when every list is empty and drifted otherwise.
    """
    if live is None:
        return TableReport(
            table_name=table_name,
            status=TableStatus.MISSING,
            missing_columns=(),
            extra_columns=(),
            changed_columns=(),
            missing_indexes=(),
            extra_indexes=(),
        )

    declared_by_name = {column.name: column for column in declared.columns}
    live_by_name = {column.name: column for column in live.columns}

    # Declared column order for missing/changed, live column order for extra.
    missing_columns = tuple(column.name for column in declared.columns if column.name not in live_by_name)
    extra_columns = tuple(column.name for column in live.columns if column.name not in declared_by_name)
    changed_columns = tuple(
        ColumnDifference(name=column.name, expected=column, actual=live_by_name[column.name])
        for column in declared.columns
        if column.name in live_by_name
        and (
            column.type_text != live_by_name[column.name].type_text
            or column.not_null != live_by_name[column.name].not_null
        )
    )
    # Index shapes are sets; sort the differences so the report is deterministic.
    missing_indexes = tuple(sorted(declared.indexes - live.indexes, key=lambda index: (index.columns, index.unique)))
    extra_indexes = tuple(sorted(live.indexes - declared.indexes, key=lambda index: (index.columns, index.unique)))

    has_difference = bool(missing_columns or extra_columns or changed_columns or missing_indexes or extra_indexes)
    return TableReport(
        table_name=table_name,
        status=TableStatus.DRIFTED if has_difference else TableStatus.IN_SYNC,
        missing_columns=missing_columns,
        extra_columns=extra_columns,
        changed_columns=changed_columns,
        missing_indexes=missing_indexes,
        extra_indexes=extra_indexes,
    )


def build_drift_report(connection: Connection, metadata: MetaData) -> DriftReport:
    """Walk `metadata.tables` only, in declaration order, reading and comparing each table.

    Tables the live database has but the registry does not declare are not reported.
    Writes nothing and opens no transaction.
    """
    return DriftReport(
        tables=tuple(
            compare_table_shapes(
                table.name,
                read_declared_shape(table),
                read_live_shape(connection, table.name),
            )
            for table in metadata.tables.values()
        )
    )


def report_has_missing(report: DriftReport) -> bool:
    """Whether any table in the report has status missing."""
    return any(table.status is TableStatus.MISSING for table in report.tables)


def report_has_drift(report: DriftReport) -> bool:
    """Whether any table in the report has status drifted."""
    return any(table.status is TableStatus.DRIFTED for table in report.tables)
