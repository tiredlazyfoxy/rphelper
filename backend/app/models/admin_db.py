"""The `/api/admin/database` response models — nothing else.

**There is no request model at all**: both apply routes take an empty body (`context.md`
D9). Every model here is a response.

The field names mirror `app.db.drift`'s value types one-for-one (`ColumnShape`,
`IndexShape`, `ColumnDifference`, `TableReport`, `DriftReport`), so a report maps onto the
wire without renaming. `DriftReportResponse` wraps the per-table reports under the single
`tables` field, in registry declaration order — a route never returns a bare list.

**No id field anywhere** — the report is keyed on table names, so `models/ids.py`'s aliases
are not imported. **No row count, no byte size, no timestamp**, and no field relating to a
user, character, setup, session, message or memo (R5, UC-066).

This module imports neither `fastapi` nor anything from `app.routers`.
"""

from typing import Literal

from pydantic import BaseModel

#: `context.md` D2's closed three-value status set — the values of `app.db.drift.TableStatus`.
TableStatusValue = Literal["in_sync", "missing", "drifted"]


class ColumnShapeResponse(BaseModel):
    """One column: its name, its normalised SQLite type text and its NOT NULL flag."""

    name: str
    type_text: str
    not_null: bool


class IndexShapeResponse(BaseModel):
    """One index: its column list (in index order) and its uniqueness flag."""

    columns: list[str]
    unique: bool


class ChangedColumnResponse(BaseModel):
    """A column present on both sides whose type or nullability differs: expected vs actual."""

    name: str
    expected: ColumnShapeResponse
    actual: ColumnShapeResponse


class TableReportResponse(BaseModel):
    """One registry table's report row. Also the answer of each apply route (re-derived)."""

    table_name: str
    status: TableStatusValue
    missing_columns: list[str]
    extra_columns: list[str]
    changed_columns: list[ChangedColumnResponse]
    missing_indexes: list[IndexShapeResponse]
    extra_indexes: list[IndexShapeResponse]


class DriftReportResponse(BaseModel):
    """The whole report — one entry per registry table, declaration order, under `tables`."""

    tables: list[TableReportResponse]
