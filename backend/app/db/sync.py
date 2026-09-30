"""Schema remediation — the only DDL writer outside bootstrap (feature 007, step 003).

Create and Sync, each defined by postcondition (`context.md` D4). Both take a connection,
the registry and a raw table **name**; the name is resolved against `registry.tables`
here, and an undeclared name raises `UnknownTableError` before any DDL — the raw string is
never interpolated into SQL (D9). Sync's drifted case rebuilds the table through Alembic's
`batch_alter_table` in recreate mode (D5), inside one transaction, wrapped in the
foreign-key pragma dance (D8). Both answer with the per-table report re-derived from
`app.db.drift` after the apply. No row is ever counted (R5).

This module imports `app.db.drift`; the reverse import is a defect. It never imports
`app.db.schema` (the registry arrives as an argument) nor any `fastapi` name. From Alembic
only `alembic.migration.MigrationContext` and `alembic.operations.Operations` are used.

Transaction discipline. The engine sends a real `BEGIN` for every SQLAlchemy transaction,
explicit or autobegun (`db/engine.py`), so a read issued outside a `begin()` block leaves
a transaction open. `PRAGMA foreign_keys` is silently ignored inside a transaction, so the
pragma is only ever switched once no transaction is open, and it is sent straight to the
DBAPI connection — a SQLAlchemy `execute` would autobegin first and the pragma would do
nothing.
"""

from typing import Literal

from alembic.migration import MigrationContext
from alembic.operations import Operations
from loguru import logger
from sqlalchemy import Column, Connection, DefaultClause, LargeBinary, MetaData, Table, func, literal, select

from app.db.drift import (
    IndexShape,
    TableReport,
    TableStatus,
    compare_table_shapes,
    read_declared_shape,
    read_live_shape,
)
from app.errors import SchemaApplyFailedError, UnknownTableError

SchemaOperation = Literal["create", "sync"]
"""The operation name `SchemaApplyFailedError.detail["operation"]` carries."""


class _RebuildRefusedError(Exception):
    """Internal: the rebuild ran but its result may not be committed (cast or FK check)."""


def _resolve_table(registry: MetaData, table_name: str) -> Table:
    """Look the raw name up in the registry; an undeclared name is `unknown_table`."""
    table = registry.tables.get(table_name)
    if table is None:
        raise UnknownTableError(detail={"table_name": table_name})
    return table


def _current_report(connection: Connection, table: Table) -> TableReport:
    """Read the live shape and compare it with the declaration. Reads only."""
    return compare_table_shapes(table.name, read_declared_shape(table), read_live_shape(connection, table.name))


def _end_transaction(connection: Connection) -> None:
    """Commit the transaction a read autobegan (or the caller left open), if any."""
    if connection.in_transaction():
        connection.commit()


def _set_foreign_keys(connection: Connection, enabled: bool) -> None:
    """Switch `PRAGMA foreign_keys` on the raw DBAPI connection, outside any transaction."""
    cursor = connection.connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys = ON" if enabled else "PRAGMA foreign_keys = OFF")
    finally:
        cursor.close()


def _fail(table: Table, operation: SchemaOperation) -> SchemaApplyFailedError:
    """Build the apply-failed error and log it — code, table and operation only (D9)."""
    logger.warning("schema apply failed code=schema_apply_failed table={} operation={}", table.name, operation)
    return SchemaApplyFailedError(detail={"table_name": table.name, "operation": operation})


def _create_absent(connection: Connection, table: Table, operation: SchemaOperation) -> None:
    """CREATE TABLE plus the declared indexes, in one transaction. Never drops anything."""
    _end_transaction(connection)
    try:
        with connection.begin():
            table.create(connection, checkfirst=False)
    except Exception:
        raise _fail(table, operation) from None


def _numeric_storage_expected(type_text: str) -> bool:
    """Whether a declared type text means values must be stored as numbers.

    SQLite's affinity rules: `INT` → INTEGER; `REAL`/`FLOA`/`DOUB` → REAL. `NUMERIC`,
    `DECIMAL` and `BOOLEAN` are numeric declarations too. Date/time and JSON types are
    NUMERIC affinity in SQLite but are stored as text by SQLAlchemy, so they are excluded.
    """
    if "INT" in type_text:
        return True
    if any(marker in type_text for marker in ("CHAR", "CLOB", "TEXT", "BLOB")):
        return False
    if any(marker in type_text for marker in ("REAL", "FLOA", "DOUB")):
        return True
    return type_text.startswith(("NUMERIC", "DECIMAL", "BOOLEAN"))


def _rebuild(connection: Connection, table: Table, report: TableReport) -> None:
    """Recreate-mode batch rebuild of a drifted table, in the transaction already open.

    Columns the registry declares but the live table lacks are first added (as untyped
    `BLOB`, carrying the declared server default) so the batch copy can select them; the
    batch then builds the new table from the registry's `Table` itself, copies every
    declared column, drops the old table (and with it every column and index the registry
    no longer declares) and renames the new one. Declared indexes Alembic does not recreate
    are created afterwards, still inside the transaction.
    """
    operations = Operations(MigrationContext.configure(connection))

    for column_name in report.missing_columns:
        declared_default = table.c[column_name].server_default
        default = DefaultClause(declared_default.arg) if isinstance(declared_default, DefaultClause) else None
        operations.add_column(table.name, Column(column_name, LargeBinary(), nullable=True, server_default=default))

    with operations.batch_alter_table(table.name, recreate="always", copy_from=table):
        pass

    live = read_live_shape(connection, table.name)
    live_indexes = live.indexes if live is not None else frozenset()
    for index in table.indexes:
        shape = IndexShape(columns=tuple(column.name for column in index.columns), unique=bool(index.unique))
        if shape not in live_indexes:
            index.create(connection)

    # A type change must not be a silent lossy cast (D5): a value SQLite could not convert
    # to a number stays stored as text/blob, and that refuses the rebuild.
    for difference in report.changed_columns:
        if difference.expected.type_text == difference.actual.type_text:
            continue
        if not _numeric_storage_expected(difference.expected.type_text):
            continue
        uncast = connection.execute(
            select(literal(1))
            .select_from(table)
            .where(func.typeof(table.c[difference.name]).not_in(["integer", "real", "null"]))
            .limit(1)
        ).first()
        if uncast is not None:
            raise _RebuildRefusedError

    violation = connection.exec_driver_sql("PRAGMA foreign_key_check").first()
    if violation is not None:
        raise _RebuildRefusedError


def create_table(connection: Connection, registry: MetaData, table_name: str) -> TableReport:
    """Ensure the declared table exists; never alter or drop an existing one.

    Absent → emit the registry `Table`'s CREATE TABLE plus its declared indexes in one
    transaction. Present (in sync or drifted) → do nothing. Returns the table's report
    re-derived after the apply. Raises `UnknownTableError` for an undeclared name and
    `SchemaApplyFailedError` (operation `"create"`) when the apply fails.
    """
    table = _resolve_table(registry, table_name)
    report = _current_report(connection, table)
    if report.status is TableStatus.MISSING:
        _create_absent(connection, table, "create")
        report = _current_report(connection, table)
    _end_transaction(connection)
    return report


def sync_table(connection: Connection, registry: MetaData, table_name: str) -> TableReport:
    """Make the live table match the declared shape.

    Missing → create. In sync → no-op. Drifted → recreate-mode batch rebuild in one
    transaction (copy every column declared and live, drop the old, rename the new,
    reconcile indexes), wrapped in the foreign-key pragma dance. Returns the table's report
    re-derived after the apply. Raises `UnknownTableError` for an undeclared name and
    `SchemaApplyFailedError` (operation `"sync"`) when the apply fails or leaves a
    foreign-key violation.
    """
    table = _resolve_table(registry, table_name)
    report = _current_report(connection, table)
    if report.status is TableStatus.MISSING:
        _create_absent(connection, table, "sync")
    elif report.status is TableStatus.DRIFTED:
        _end_transaction(connection)
        _set_foreign_keys(connection, enabled=False)
        try:
            try:
                with connection.begin():
                    _rebuild(connection, table, report)
            except Exception:
                raise _fail(table, "sync") from None
        finally:
            if connection.in_transaction():
                connection.rollback()
            _set_foreign_keys(connection, enabled=True)
    else:
        _end_transaction(connection)
        return report
    report = _current_report(connection, table)
    _end_transaction(connection)
    return report
