"""`/api/admin/database` — schema drift report and remediation, guarded at the router level.

The router owns HTTP and nothing else: no business rule, no SQL, no registry lookup, no
transaction. Its only database contact is `app.db.engine.get_connection`. Like
`routers/health.py`, it imports `metadata` from `app.db.schema` and passes it down as a
plain argument; `db/drift.py` and `db/sync.py` never import the registry.

Each handler calls **exactly one** operation — `build_drift_report` for the read,
`create_table` / `sync_table` for an apply, `export_database` for the export — and maps its
plain result onto a model, the export excepted: it answers a raw `Response` (see below). Each
apply route answers with the **re-derived** report row the operation returns. No handler
translates a domain error by hand: the single `DomainError` handler renders
`unknown_table` (404) and `schema_apply_failed` (500). `{table_name}` is passed down as a
plain string and never used to build SQL here; `db/sync.py` validates it.

**`require_role(Role.ADMIN)` is attached to the router, never to a handler**, so a route
added later cannot forget the guard.

**Four routes.** The first three are feature `007`'s (`context.md` D9); the fourth is feature
`030`'s `GET /export` — the whole-database export (FEAT-018, UC-061, US-077), which lives here
rather than in `routers/transfer.py` precisely so it inherits the router-level admin guard.
No route takes a query parameter or a request body, and there is still **no rebuild and no
import route** anywhere on this router.

`GET /export` is the one handler that answers a raw `Response` instead of a model: it is a JSON
**file download**, and the export envelope is column-agnostic, so no static model can describe
it (`003.context.md`, `outcome.md`). The JSON id boundary still holds, because
`services/transfer.py` stringifies every id before the router sees the envelope. The attachment
response is built **locally** here; this module and `routers/transfer.py` share the shape, not
an import.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
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
from app.services.transfer import encode_envelope, export_database, export_filename

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


@router.get("/export", status_code=200)
def export_whole_database(
    connection: Annotated[Connection, Depends(get_connection)],
) -> Response:
    """The whole-database export via `export_database(connection)`, as a JSON file attachment.

    Full path `/api/admin/database/export`; admin-only through the **router-level** guard, which
    this route names nowhere. It takes no path parameter, no query parameter and no body, like
    `GET /tables`.

    The response is built here, in a few lines, and is exactly: status **200**, body
    `encode_envelope(envelope)`, media type `application/json`, and `Content-Disposition:
    attachment; filename="<export_filename(envelope)>"`. Nothing else is set, and nothing about
    the response is derived from the payload — the filename comes from the envelope's
    `granularity` and `created_at` alone (US-078 opacity). `routers/transfer.py` builds the same
    shape independently; neither module imports the other.
    """
    envelope = export_database(connection)
    return Response(
        content=encode_envelope(envelope),
        status_code=200,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{export_filename(envelope)}"'},
    )
