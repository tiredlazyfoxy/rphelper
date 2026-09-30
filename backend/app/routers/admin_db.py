"""`/api/admin/database` — schema drift report and remediation, guarded at the router level.

The router owns HTTP and nothing else: no business rule, no SQL, no registry lookup, no
transaction. Its only database contact is `app.db.engine.get_connection`. Like
`routers/health.py`, it imports `metadata` from `app.db.schema` and passes it down as a
plain argument; `db/drift.py` and `db/sync.py` never import the registry.

Each handler calls **exactly one** operation — `build_drift_report` for the read,
`create_table` / `sync_table` for an apply — and maps its plain result onto a model. Each
apply route answers with the **re-derived** report row the operation returns. No handler
translates a domain error by hand: the single `DomainError` handler renders
`unknown_table` (404) and `schema_apply_failed` (500). `{table_name}` is passed down as a
plain string and never used to build SQL here; `db/sync.py` validates it.

**`require_role(Role.ADMIN)` is attached to the router, never to a handler**, so a route
added later cannot forget the guard.

Three routes (`context.md` D9). No query parameter, no request body, no rebuild, export or
import route anywhere on this router.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Connection

from app.db.drift import ColumnShape, IndexShape, TableReport, build_drift_report
from app.db.engine import get_connection
from app.db.schema import metadata
from app.db.sync import create_table, sync_table
from app.dependencies import require_role
from app.models.admin_db import (
    ChangedColumnResponse,
    ColumnShapeResponse,
    DriftReportResponse,
    IndexShapeResponse,
    TableReportResponse,
)
from app.roles import Role

#: The router's one guard.
require_admin = require_role(Role.ADMIN)

router = APIRouter(
    prefix="/api/admin/database",
    tags=["admin-database"],
    dependencies=[Depends(require_admin)],
)


def _column_response(column: ColumnShape) -> ColumnShapeResponse:
    return ColumnShapeResponse(name=column.name, type_text=column.type_text, not_null=column.not_null)


def _index_response(index: IndexShape) -> IndexShapeResponse:
    return IndexShapeResponse(columns=list(index.columns), unique=index.unique)


def _table_response(report: TableReport) -> TableReportResponse:
    """Map one plain `TableReport` onto the wire model — pure, never raises."""
    return TableReportResponse(
        table_name=report.table_name,
        status=report.status.value,
        missing_columns=list(report.missing_columns),
        extra_columns=list(report.extra_columns),
        changed_columns=[
            ChangedColumnResponse(
                name=change.name,
                expected=_column_response(change.expected),
                actual=_column_response(change.actual),
            )
            for change in report.changed_columns
        ],
        missing_indexes=[_index_response(index) for index in report.missing_indexes],
        extra_indexes=[_index_response(index) for index in report.extra_indexes],
    )


@router.get("/tables", status_code=200)
def read_drift_report(
    connection: Annotated[Connection, Depends(get_connection)],
) -> DriftReportResponse:
    """The whole per-table report via `build_drift_report(connection, metadata)`."""
    report = build_drift_report(connection, metadata)
    return DriftReportResponse(tables=[_table_response(table) for table in report.tables])


@router.post("/tables/{table_name}/create", status_code=200)
def create_registry_table(
    table_name: str,
    connection: Annotated[Connection, Depends(get_connection)],
) -> TableReportResponse:
    """D4's Create via `create_table(connection, metadata, table_name)`; answers the re-derived row."""
    return _table_response(create_table(connection, metadata, table_name))


@router.post("/tables/{table_name}/sync", status_code=200)
def sync_registry_table(
    table_name: str,
    connection: Annotated[Connection, Depends(get_connection)],
) -> TableReportResponse:
    """D4's Sync via `sync_table(connection, metadata, table_name)`; answers the re-derived row."""
    return _table_response(sync_table(connection, metadata, table_name))
