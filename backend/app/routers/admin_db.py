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

**Six routes.** The first three are feature `007`'s (`context.md` D9); the fourth is feature
`030`'s `GET /export` — the whole-database export (FEAT-018, UC-061, US-077) — and the fifth is
feature `031`'s `POST /import`, its mirror image (UC-061, US-077.AC-2). Both live here rather than
in `routers/transfer.py` precisely so they inherit the router-level admin guard. No route takes a
query parameter; `POST /import` is the **only** route with a request body.
`POST /rebuild` (feature `fast/002`, FEAT-005) re-derives every vector and FTS index via `rebuild_index`.

**This module contains no `try`, no `except` and no `raise`, and that is load-bearing.** Every
refusal of the whole-database import — `database_not_empty` (409) for an ineligible instance, the
typed 400 for a payload the service or the database rejects — is raised inside
`app.services.transfer_import` and rendered by the one `DomainError` handler, exactly as the drift
routes' `unknown_table` is. The constraint translation that wraps the import's write pass lives in
that service and never here.

`GET /export` is the one handler that answers a raw `Response` instead of a model: it is a JSON
**file download**, and the export envelope is column-agnostic, so no static model can describe
it (`003.context.md`, `outcome.md`). The JSON id boundary still holds, because
`services/transfer.py` stringifies every id before the router sees the envelope. The attachment
response is built **locally** here; this module and `routers/transfer.py` share the shape, not
an import.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy import Connection

from app.config import Settings, get_settings
from app.db.drift import ColumnShape, IndexShape, TableReport, build_drift_report
from app.db.engine import get_connection
from app.db.schema import metadata
from app.db.sync import create_table, sync_table
from app.dependencies import clear_session_cookie, get_llm_client_factory, require_role
from app.models.admin_db import (
    ChangedColumnResponse,
    ColumnShapeResponse,
    DriftReportResponse,
    IndexShapeResponse,
    RebuildReportResponse,
    TableReportResponse,
)
from app.roles import Role
from app.services.index_rebuild import rebuild_index
from app.services.llm_registry import LlmClientFactory
from app.services.transfer import encode_envelope, export_database, export_filename
from app.services.transfer_import import import_database

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


@router.post("/import", status_code=204)
def import_whole_database(
    body: dict[str, Any],
    response: Response,
    connection: Annotated[Connection, Depends(get_connection)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Replace the whole database from a `database`-granularity payload via `import_database`.

    Full path `/api/admin/database/import`; admin-only through the **router-level** guard, which
    this route names nowhere, like the other four. It takes no path parameter and no query
    parameter — the body is all it reads.

    `body` is the raw JSON object (`031/005.context.md`): the payload is column-agnostic, so no
    static model can describe it, and `app.services.transfer_import` validates it before writing
    anything. A body that is not a JSON object answers **422** from FastAPI before this handler
    runs; an object that is not a recognised envelope answers **400** from the service.

    Answers **204** with no body. It then clears the session cookie on the injected `Response`
    through `clear_session_cookie(response, settings)` — `app/dependencies.py`'s writer, the same
    one `POST /api/auth/logout` uses. A successful replace deletes every `auth_sessions` row,
    including the caller's, so the browser would otherwise keep sending a token the server can no
    longer resolve; the frontend navigates to the login page regardless.

    Translates nothing, catches nothing, and contains neither `try` nor `raise`: an ineligible
    instance (`database_not_empty`, 409) and a payload the service or the database refuses (400,
    `app/errors.py`) both travel through the single `DomainError` handler.
    """
    import_database(connection, body)
    clear_session_cookie(response, settings)


@router.post("/rebuild", status_code=200)
def rebuild_search_index(
    connection: Annotated[Connection, Depends(get_connection)],
    settings: Annotated[Settings, Depends(get_settings)],
    client_factory: Annotated[LlmClientFactory, Depends(get_llm_client_factory)],
) -> RebuildReportResponse:
    """Re-derive both vector tables and both FTS5 indexes via `rebuild_index`; answers 200.

    Full path `/api/admin/database/rebuild`; admin-only through the **router-level** guard. No
    body, no path or query parameter. Passes `client_factory` and
    `settings.llm_request_timeout_seconds` by keyword and catches nothing: `no_embedding_model`
    (409) and an unreachable server travel through the single `DomainError` handler.
    """
    return rebuild_index(
        connection,
        client_factory=client_factory,
        timeout_seconds=settings.llm_request_timeout_seconds,
    )
