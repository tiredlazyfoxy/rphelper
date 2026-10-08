# Feature 007 — Schema drift and remediation

| Step | File                                          | Status  | Verifier | Date |
|------|-----------------------------------------------|---------|----------|------|
| 001  | `001.drift-value-types-and-shape-readers.md`  | done    | PASS     | 2026-09-30 |
| 002  | `002.comparison-walk-and-health-drift.md`     | done    | PASS     | 2026-09-30 |
| 003  | `003.batch-ddl-executor-and-errors.md`        | done    | PASS     | 2026-09-30 |
| 004  | `004.admin-database-router.md`                | done    | PASS     | 2026-09-30 |
| 005  | `005.database-page-report-table.md`           | done    | PASS     | 2026-09-30 |
| 006  | `006.row-actions-and-lossy-sync-confirm.md`   | done    | PASS     | 2026-09-30 |

## Files Changed

### Step 001 — drift value types and shape readers
- `backend/app/db/drift.py` — filled `normalize_type_text` (upper-case, collapse whitespace, drop spaces around `(`/`)`/`,`), `read_live_shape` (quoted-identifier PRAGMA table_info/index_list/index_info, origin `c` only, `None` when absent), `read_declared_shape` (SQLite-dialect type compile, `Table.indexes` only); step 002 stubs untouched

### Step 002 — comparison, registry walk, health drift branch
- `backend/app/db/drift.py` — filled `compare_table_shapes` (absent live → missing with empty lists; missing/extra by name set difference in declared/live column order; changed over the intersection on type text or NOT NULL; index set differences sorted by (columns, unique); status derived from the lists), `build_drift_report` (walks `metadata.tables.values()` in declaration order via the two readers; no transaction, no DDL, no COUNT), `report_has_missing` / `report_has_drift`
- `backend/app/services/health.py` — `probe_health`'s presence test replaced by the drift report's roll-up (missing > drift > ok) via `app.db.drift`; `sqlite_master` read and `text` import removed; signature, `HealthProbeResult`, `status` precedence unchanged; no cache; docstrings updated

### Step 003 — batch DDL executor and errors
- `backend/app/db/sync.py` — filled `create_table` (registry lookup → `UnknownTableError`; absent → `Table.create` with its indexes in one `begin()`; present in any state → no-op returning the current report) and `sync_table` (missing → same create; in sync → no-op; drifted → end the autobegun read txn, `PRAGMA foreign_keys = OFF` on the raw DBAPI cursor, then one `begin()` holding: `ADD COLUMN` for missing columns as untyped BLOB carrying the declared server default, `batch_alter_table(recreate="always", copy_from=<registry Table>)`, creation of declared indexes Alembic skips, a `typeof` probe refusing uncastable values in numerically retyped columns, `PRAGMA foreign_key_check`; any failure → rollback + `SchemaApplyFailedError(detail={table_name, operation})` raised `from None`, log line carries code/table/operation only; FK pragma back ON in `finally`); report re-derived via `app.db.drift` after commit, read txn committed before returning. `errors.py` / `pyproject.toml` were already complete from the skeleton and are unchanged here.

### Step 004 — admin database router
- `backend/app/routers/admin_db.py` — filled the three handler bodies: module-level imports of `metadata` (`app.db.schema`), `build_drift_report` (`app.db.drift`) and `create_table` / `sync_table` (`app.db.sync`) as bare names; each handler makes exactly one call with `metadata` passed as a plain argument and maps the plain result via pure helpers `_table_response` / `_column_response` / `_index_response` (tuples → lists, `TableStatus` → its string value). No SQL, no try/except, no registry lookup, no status branching. `models/admin_db.py` and `main.py` unchanged from the skeleton.

### Step 005 — Database page report table
- `frontend/src/admin/databasePageState.ts` — filled `loadDriftReport` (aborted → no writes; "loading" only when not already "ready"; `apiGet(DRIFT_REPORT_PATH, signal)` with no query; rows/status/errorMessage in `runInAction`; failure message → `errorMessage`, never rejects), `statusBadgeOf` (In sync/green, Drifted/yellow, Missing/red, exhaustive switch), `differencesSummaryOf` ("Missing: …; Extra: …; Changed: name (expected TYPE NOT NULL, actual TYPE NULL)" and index column lists with a "unique" prefix; em dash when empty; no counts); private helpers added; step 006 stubs untouched
- `frontend/src/admin/DatabasePage.tsx` — filled `DatabasePage`: mount `useEffect` with `AbortController` (abort on unmount), `Container size="lg" py="md"`, "Database" title, inline red `Alert` above the table, centered `Loader` gated on `status !== "ready"`, `Table striped highlightOnHover` with Table / Status (Badge from `statusBadgeOf`) / Columns / Indexes / empty `w={60}` column, row key `table_name`

### Step 006 — row actions and lossy-Sync confirm
- `frontend/src/admin/databasePageState.ts` — filled `createDriftTable` / `syncDriftTable` via one private `applyDriftOperation` helper (aborted → no writes; `applyingTable` set in `runInAction`; `apiPost` to `${DRIFT_REPORT_PATH}/${encodeURIComponent(name)}/create|sync` with no body; failure → `errorMessage` + clear `applyingTable`; success → `loadDriftReport` then clear `applyingTable`; never rejects), `isLossySync` (extra_columns non-empty), `syncConsequenceOf` (names table + every dropped column, states every other column's data is preserved, no count); `apiPost` import added
- `frontend/src/admin/DatabasePage.tsx` — trailing `w={60}` cell: for missing/drifted rows one `IconDots` `IconButton` (label `Actions for <table>`, disabled while that table is applying) inside `Menu.Target > Box span`, text items Create (missing only) / Sync (drifted only); in-sync rows render an empty cell; Create fires directly; Sync fires directly unless `isLossySync`, else opens the shared `ConfirmModal` (title `Sync <table>?`, `syncConsequenceOf`, `confirmLabel="Sync"`, `confirmColor="red"`) with component-local open flag + target `useState`; handlers `void`-ed with a non-rethrowing catch; unmount-aborted `AbortController` shared via ref

## Skeleton

### Step 001 — frozen interface (2026-09-30)
All in `backend/app/db/drift.py` (new module; imports only `dataclasses`, `enum.StrEnum`, `sqlalchemy.Connection`, `sqlalchemy.Table`).
- `class TableStatus(StrEnum)` — new — members `IN_SYNC = "in_sync"`, `MISSING = "missing"`, `DRIFTED = "drifted"` (exactly three; these strings are the wire values for 004's model and 005's frontend union `"in_sync" | "missing" | "drifted"`)
- `@dataclass(frozen=True) class ColumnShape: name: str; type_text: str; not_null: bool` — new
- `@dataclass(frozen=True) class IndexShape: columns: tuple[str, ...]; unique: bool` — new (no name field; identity = dataclass equality over columns-in-order + unique)
- `@dataclass(frozen=True) class TableShape: columns: tuple[ColumnShape, ...]; indexes: frozenset[IndexShape]` — new (columns in table column order; indexes a set, so both readers compare equal regardless of index enumeration order)
- `@dataclass(frozen=True) class ColumnDifference: name: str; expected: ColumnShape; actual: ColumnShape` — new
- `@dataclass(frozen=True) class TableReport: table_name: str; status: TableStatus; missing_columns: tuple[str, ...]; extra_columns: tuple[str, ...]; changed_columns: tuple[ColumnDifference, ...]; missing_indexes: tuple[IndexShape, ...]; extra_indexes: tuple[IndexShape, ...]` — new (populated in 002; no count/size/timestamp field)
- `@dataclass(frozen=True) class DriftReport: tables: tuple[TableReport, ...]` — new
- `def normalize_type_text(type_text: str) -> str` — new (stub raises `NotImplementedError`)
- `def read_live_shape(connection: Connection, table_name: str) -> TableShape | None` — new (`None` = table absent; stub raises `NotImplementedError`)
- `def read_declared_shape(table: Table) -> TableShape` — new (stub raises `NotImplementedError`)
- Caller-compile edits (out of Source-files scope): None.
- Gates: `mypy app` clean (36 files), `ruff check .` clean.

### Step 002 — frozen interface (2026-09-30)
`backend/app/db/drift.py` (added beside 001's symbols, which are unchanged; import line widened to `from sqlalchemy import Connection, MetaData, Table`; still no import of `app.db.sync` / `app.db.schema`):
- `def compare_table_shapes(table_name: str, declared: TableShape, live: TableShape | None) -> TableReport` — new (pure, no I/O; `live=None` = table absent; stub raises `NotImplementedError`)
- `def build_drift_report(connection: Connection, metadata: MetaData) -> DriftReport` — new (walks `metadata.tables` only, declaration order; stub raises `NotImplementedError`)
- `def report_has_missing(report: DriftReport) -> bool` — new (any table status `MISSING`; stub raises `NotImplementedError`)
- `def report_has_drift(report: DriftReport) -> bool` — new (any table status `DRIFTED`; stub raises `NotImplementedError`)

`backend/app/services/health.py` — **frozen unchanged** (not edited by skeleton; existing working body kept, the coder widens it):
- `@dataclass(frozen=True) class HealthProbeResult: status: HealthStatus; configured: bool; schema: SchemaState` — unchanged
- `def probe_health(connection: Connection, registry: MetaData) -> HealthProbeResult` — unchanged (registry stays a parameter)
- Caller-compile edits (out of Source-files scope): None. `routers/health.py` untouched.
- Gates: `mypy app` clean (36 files), `ruff check .` clean.

### Step 003 — frozen interface (2026-09-30)
`backend/pyproject.toml` — runtime `dependencies` gains `"alembic>=1.14,<2.0"` (nothing else changed). `uv lock` + `uv sync --inexact` run: installed alembic 1.20.0 (+ mako 1.4.3, markupsafe 3.0.3) beside SQLAlchemy 2.1.1; dev tools (pytest 8.4.2, mypy 1.20.2, ruff 0.16.9) kept. alembic ships `py.typed`; `MigrationContext.configure(connection)` + `Operations(context).batch_alter_table(name, recreate="always")` typecheck clean under the project mypy config. No `alembic.ini` / `migrations/` / `env.py` / `versions/` created.

`backend/app/errors.py` (appended after `LlmServerNotFoundError`; nothing else touched, no handler added):
- `class UnknownTableError(DomainError)` — new — `code = "unknown_table"`, `http_status = 404`; **no custom `__init__`** (base `__init__(message: str | None = None, detail: Mapping[str, Any] | None = None)`, message defaults to `None`). Raiser passes `detail={"table_name": <name>}`.
- `class SchemaApplyFailedError(DomainError)` — new — `code = "schema_apply_failed"`, `http_status = 500`; **no custom `__init__`**. Raiser passes `detail={"table_name": <name>, "operation": <SchemaOperation>}`; no driver message in `message` or `detail`.

`backend/app/db/sync.py` (new module; imports `typing.Literal`, `sqlalchemy.Connection, MetaData`, `app.db.drift.TableReport`; coder adds `alembic.migration.MigrationContext` / `alembic.operations.Operations` and further `app.db.drift` names as needed; never `app.db.schema`, never `fastapi`):
- `SchemaOperation = Literal["create", "sync"]` — new — the `detail["operation"]` value type.
- `def create_table(connection: Connection, registry: MetaData, table_name: str) -> TableReport` — new (stub raises `NotImplementedError`)
- `def sync_table(connection: Connection, registry: MetaData, table_name: str) -> TableReport` — new (stub raises `NotImplementedError`)
- Both raise `UnknownTableError` for a name absent from `registry.tables` and `SchemaApplyFailedError` on a failed apply; the returned `TableReport` is re-derived via `app.db.drift` after commit.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `mypy app` clean (37 files), `ruff check .` clean.

### Step 004 — frozen interface (2026-09-30)
`backend/app/models/admin_db.py` (new; imports only `typing.Literal`, `pydantic.BaseModel`; no request model, no id alias, plain `BaseModel`, no `ConfigDict`):
- `TableStatusValue = Literal["in_sync", "missing", "drifted"]` — new
- `class ColumnShapeResponse(BaseModel): name: str; type_text: str; not_null: bool` — new
- `class IndexShapeResponse(BaseModel): columns: list[str]; unique: bool` — new
- `class ChangedColumnResponse(BaseModel): name: str; expected: ColumnShapeResponse; actual: ColumnShapeResponse` — new
- `class TableReportResponse(BaseModel): table_name: str; status: TableStatusValue; missing_columns: list[str]; extra_columns: list[str]; changed_columns: list[ChangedColumnResponse]; missing_indexes: list[IndexShapeResponse]; extra_indexes: list[IndexShapeResponse]` — new
- `class DriftReportResponse(BaseModel): tables: list[TableReportResponse]` — new
- Field names mirror `app.db.drift`'s dataclasses one-for-one (tuples become JSON arrays).

JSON wire shapes (exact keys; step 005's frontend binds to these):
```
ColumnShape   = {"name": str, "type_text": str, "not_null": bool}
IndexShape    = {"columns": [str, ...], "unique": bool}
ChangedColumn = {"name": str, "expected": ColumnShape, "actual": ColumnShape}
TableReport   = {"table_name": str, "status": "in_sync" | "missing" | "drifted",
                 "missing_columns": [str], "extra_columns": [str],
                 "changed_columns": [ChangedColumn],
                 "missing_indexes": [IndexShape], "extra_indexes": [IndexShape]}
GET  /api/admin/database/tables                      -> 200 {"tables": [TableReport, ...]}   (registry declaration order)
POST /api/admin/database/tables/{table_name}/create  -> 200 TableReport   (re-derived row; no body, no query)
POST /api/admin/database/tables/{table_name}/sync    -> 200 TableReport   (re-derived row; no body, no query)
Errors: 404 {"error": {"code": "unknown_table", "message": str | null, "detail": {"table_name": ...}}};
        500 {"error": {"code": "schema_apply_failed", "message": str | null, "detail": {"table_name": ..., "operation": "create"|"sync"}}};
        401 not_authenticated / 403 insufficient_role from the router guard.
```

`backend/app/routers/admin_db.py` (new):
- `require_admin = require_role(Role.ADMIN)` — new (module-level, the one guard)
- `router = APIRouter(prefix="/api/admin/database", tags=["admin-database"], dependencies=[Depends(require_admin)])` — new
- `@router.get("/tables", status_code=200) def read_drift_report(connection: Annotated[Connection, Depends(get_connection)]) -> DriftReportResponse` — new (stub raises `NotImplementedError`)
- `@router.post("/tables/{table_name}/create", status_code=200) def create_registry_table(table_name: str, connection: Annotated[Connection, Depends(get_connection)]) -> TableReportResponse` — new (stub raises `NotImplementedError`)
- `@router.post("/tables/{table_name}/sync", status_code=200) def sync_registry_table(table_name: str, connection: Annotated[Connection, Depends(get_connection)]) -> TableReportResponse` — new (stub raises `NotImplementedError`)
- The stub does not yet import `metadata` (`app.db.schema`), `build_drift_report` (`app.db.drift`) or `create_table` / `sync_table` (`app.db.sync`) — ruff F401 would flag them unused; the coder adds these module-level imports.

`backend/app/main.py` — changed: added `from app.routers.admin_db import router as admin_db_router` (bare-name import) and `app.include_router(admin_db_router)` appended after `admin_llm_router`; docstring router lists updated (also now name the pre-existing `admin_llm_router`). `create_app() -> FastAPI` signature and lifespan unchanged.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `mypy app` clean (39 files), `ruff check .` clean; the three routes register at the D9 paths.

### Step 005 — frozen interface (2026-09-30)
`frontend/src/admin/databasePageState.ts` (new; imports only `mobx.makeAutoObservable` and `type MantineColor` from `@mantine/core` — the coder adds `runInAction` and `apiGet` from `../shared/api`):
- `export type TableStatus = "in_sync" | "missing" | "drifted"` — new (closed union, never `string`)
- `export type ColumnShape = { name: string; type_text: string; not_null: boolean }` — new
- `export type IndexShape = { columns: string[]; unique: boolean }` — new
- `export type ChangedColumn = { name: string; expected: ColumnShape; actual: ColumnShape }` — new
- `export type DriftTableRow = { table_name: string; status: TableStatus; missing_columns: string[]; extra_columns: string[]; changed_columns: ChangedColumn[]; missing_indexes: IndexShape[]; extra_indexes: IndexShape[] }` — new (row key = `table_name`; no id / count / size / timestamp)
- `export type DriftReportResponse = { tables: DriftTableRow[] }` — new
- `export type DatabaseLoadStatus = "idle" | "loading" | "ready"` — new
- `export type StatusBadge = { label: string; color: MantineColor }` — new (label = the status word)
- `export type DifferencesSummary = { columns: string; indexes: string }` — new (the Columns and Indexes cells' text)
- `export class DatabasePageState { rows: DriftTableRow[] = []; status: DatabaseLoadStatus = "idle"; errorMessage: string | null = null; constructor() { makeAutoObservable(this, {}, { autoBind: true }); } }` — new, **complete** (no methods, no getters)
- `export const DRIFT_REPORT_PATH = "/api/admin/database/tables"` — new (the endpoint; sent with no query parameter)
- `export async function loadDriftReport(state: DatabasePageState, signal?: AbortSignal): Promise<void>` — new (stub throws)
- `export function statusBadgeOf(row: Pick<DriftTableRow, "status">): StatusBadge` — new, pure (stub throws)
- `export function differencesSummaryOf(row: Pick<DriftTableRow, "missing_columns" | "extra_columns" | "changed_columns" | "missing_indexes" | "extra_indexes">): DifferencesSummary` — new, pure (stub throws)

`frontend/src/admin/DatabasePage.tsx` (new):
- `export type DatabasePageProps = { state: DatabasePageState }` — new
- `export const DatabasePage = observer(function DatabasePage(props: DatabasePageProps): React.JSX.Element)` — new (stub body throws)
- `export function DatabaseRoute(): React.JSX.Element` — new, **complete**: `const [state] = useState(() => new DatabasePageState()); return <DatabasePage state={state} />;`

`frontend/src/admin/AdminApp.tsx` — changed: `<Route path="/database" element={<NotFoundPage />} />` → `<Route path="/database" element={<DatabaseRoute />} />`, plus `import { DatabaseRoute } from "./DatabasePage";`. `<Routes>` still flat, four elements; `NotFoundPage` still used by `*`. `navItems.ts` untouched.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `npm run typecheck` clean (from `frontend/`).
- Known expected breakage (outside every 007 Test-files list): `frontend/tests/admin/AdminApp.test.tsx` and `llmServersPage.test.tsx` assert `/database` renders the 404.

### Step 006 — frozen interface (2026-09-30)
`frontend/src/admin/databasePageState.ts` (step 005's symbols unchanged except the one added field; the coder adds `apiPost` from `../shared/api` and `runInAction` as needed):
- `DatabasePageState.applyingTable: string | null = null` — new observable field (the table a Create/Sync is being applied to; the class still has no methods and no getters)
- `export async function createDriftTable(state: DatabasePageState, tableName: string, signal?: AbortSignal): Promise<void>` — new (stub throws) — `POST /api/admin/database/tables/{tableName}/create`, no body; sets/clears `applyingTable`; on success `loadDriftReport`s the whole report; failure → `errorMessage`; aborted signal → no writes; does not reject
- `export async function syncDriftTable(state: DatabasePageState, tableName: string, signal?: AbortSignal): Promise<void>` — new (stub throws) — same shape against `.../sync`; confirms nothing itself
- `export function isLossySync(row: Pick<DriftTableRow, "extra_columns">): boolean` — new, pure (stub throws) — true iff `extra_columns` non-empty
- `export function syncConsequenceOf(row: Pick<DriftTableRow, "table_name" | "extra_columns">): string` — new, pure (stub throws) — the confirm sentence: table name, every dropped column, other columns' data preserved; no count

`frontend/src/admin/DatabasePage.tsx` — **unchanged** (still the step-005 throwing placeholder; `DatabasePageProps`, `DatabasePage`, `DatabaseRoute` signatures frozen as in 005). The row menu (`IconDots` via `shared/IconButton` + Mantine `Menu`) and the component-local `useState` confirm target / open flag with `shared/ConfirmModal` are internal to `DatabasePage` — no new exports.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `npm run typecheck` clean (from `frontend/`).

## Tests

### Step 001 — tests (2026-09-30)
- `backend/tests/test_drift_introspection.py` — covers DoD-1..DoD-11 — status set, both shape readers against real `.sqlite` files, normalisation, implicit-index filtering, index identity, absent table, no-write/no-transaction, no count fields/queries, import boundaries.
  - DoD-1: `test_status_set_has_exactly_in_sync_missing_and_drifted__DoD1`, `test_status_set_has_no_seed_missing_member__DoD1`
  - DoD-2: `test_live_reader_reports_name_type_and_not_null_per_column__DoD2`, `test_live_reader_reports_no_index_for_a_table_without_one__DoD2`
  - DoD-3: `test_declared_reader_returns_the_expected_columns_without_a_database__DoD3`, `test_fresh_table_compares_identical_on_both_readers__DoD3`, `test_every_registry_table_compares_identical_when_created_fresh__DoD3`
  - DoD-4: `test_variant_enum_and_text_types_match_across_readers_on_a_purpose_table__DoD4`, `test_users_id_role_and_text_columns_match_across_readers__DoD4`
  - DoD-5: `test_case_and_internal_whitespace_are_not_differences__DoD5` (parametrized), `test_normalised_text_is_upper_case__DoD5` (parametrized), `test_live_reader_normalises_hand_written_type_text__DoD5`, `test_declared_reader_normalises_compiled_type_text__DoD5`
  - DoD-6: `test_unique_column_and_primary_key_are_not_live_indexes__DoD6`, `test_users_reports_no_index_on_either_reader__DoD6`, `test_explicit_indexes_are_reported_by_both_readers__DoD6`
  - DoD-7: `test_index_shapes_with_same_columns_and_uniqueness_are_equal__DoD7`, `test_differently_named_indexes_over_same_columns_are_the_same_shape__DoD7`, `test_two_live_indexes_with_different_names_same_shape_collapse__DoD7`
  - DoD-8: `test_absent_table_is_reported_absent_on_an_empty_database__DoD8`, `test_absent_table_is_reported_absent_beside_other_tables__DoD8`
  - DoD-9: `test_reader_without_begin_leaves_schema_and_rows_untouched__DoD9`, `test_reader_inside_callers_transaction_opens_none_and_commits_nothing__DoD9`, `test_reader_issues_only_pragma_reads_and_selects__DoD9`
  - DoD-10: `test_table_report_carries_exactly_the_specified_fields__DoD10`, `test_report_value_types_carry_no_count_size_or_timestamp_field__DoD10`, `test_module_source_contains_no_count_query__DoD10`, `test_reader_issues_no_count_statement__DoD10`
  - DoD-11: `test_drift_module_imports_neither_sync_nor_schema__DoD11` (parametrized), `test_drift_module_holds_no_registry_or_table_of_its_own__DoD11`
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 [manual/live, no test], DoD-13 [manual/live, no test]

### Step 002 — tests (2026-09-30)
- `backend/tests/test_drift_report.py` (new) — covers DoD-1..DoD-10 (+ roll-up predicate pair) — pure `compare_table_shapes` over hand-built shapes and `build_drift_report` over purpose-built `MetaData` on real `.sqlite` files hand-drifted with raw DDL: declaration order, missing (empty lists), in sync (incl. unique-column-only table), missing/extra/changed columns with expected+actual, index (columns, uniqueness) identity, default/CHECK/FK ignored both ways, no I/O, undeclared tables/views absent, no count/number fields or COUNT statements, no writes / no transaction events.
  - DoD-1: `test_report_has_one_entry_per_registry_table_in_declaration_order__DoD1`, `test_report_for_an_empty_registry_is_empty__DoD1`
  - DoD-2: `test_absent_live_shape_is_reported_missing_with_empty_lists__DoD2`, `test_declared_table_absent_from_the_database_is_reported_missing__DoD2`
  - DoD-3: `test_identical_shapes_are_in_sync__DoD3`, `test_table_created_from_its_declaration_is_in_sync__DoD3`, `test_hand_written_table_matching_the_declaration_is_in_sync__DoD3`, `test_unique_column_without_explicit_index_is_in_sync__DoD3`
  - DoD-4: `test_missing_column_is_drifted_and_listed_missing__DoD4`, `test_extra_column_is_drifted_and_listed_extra__DoD4`, `test_changed_type_is_drifted_with_expected_and_actual__DoD4`, `test_changed_nullability_is_drifted_with_expected_and_actual__DoD4`, `test_live_table_missing_a_declared_column_is_drifted__DoD4`, `test_live_table_with_an_undeclared_column_is_drifted__DoD4`, `test_live_column_with_a_changed_type_is_drifted__DoD4`, `test_live_column_with_changed_nullability_is_drifted__DoD4`, `test_a_column_is_never_named_in_two_lists__DoD4`
  - DoD-5: `test_missing_index_is_drifted_and_listed_missing__DoD5`, `test_extra_index_is_drifted_and_listed_extra__DoD5`, `test_uniqueness_is_part_of_index_identity__DoD5`, `test_live_table_without_a_declared_index_is_drifted__DoD5`, `test_live_index_the_registry_does_not_declare_is_drifted__DoD5`, `test_index_name_difference_alone_is_not_drift__DoD5`
  - DoD-6: `test_live_default_check_and_foreign_key_absent_from_declaration_stay_in_sync__DoD6`, `test_declared_default_check_and_foreign_key_absent_live_stay_in_sync__DoD6`
  - DoD-7: `test_comparison_takes_no_connection_parameter__DoD7`, `test_comparison_returns_a_full_report_with_no_io_available__DoD7`
  - DoD-8: `test_undeclared_live_table_and_view_appear_nowhere_in_the_report__DoD8`, `test_walk_never_inspects_an_undeclared_table__DoD8`
  - DoD-9: `test_report_entries_carry_no_count_size_or_timestamp__DoD9`, `test_building_the_report_issues_no_count__DoD9`
  - DoD-10: `test_building_the_report_leaves_schema_and_rows_unchanged__DoD10`, `test_building_the_report_opens_no_transaction__DoD10`, `test_building_the_report_issues_only_pragma_reads_and_selects__DoD10`
  - predicates (DoD-11/12/14 support): `test_roll_up_predicates_read_the_report_statuses__DoD11_DoD12_DoD14` (parametrized)
- `backend/tests/test_health.py` (extended; every pre-existing test untouched) — covers DoD-11..DoD-17 — `schema` roll-up missing/drift/ok, missing outranks drift, unchanged `status` precedence, closed one-word table-free body, registry still a parameter / service never imports `app.db.schema` / router still passes `schema.metadata`.
  - DoD-11: `test_absent_declared_table_still_reports_missing__S007_002_DoD11`, `test_partially_present_registry_still_reports_missing__S007_002_DoD11`, `test_fresh_database_against_the_production_registry_reports_missing__S007_002_DoD11` (plus the pre-existing `__DoD3` / `__S002_DoD9` tests, which must keep passing)
  - DoD-12: `test_present_but_differing_table_reports_drift__S007_002_DoD12` (parametrized), `test_missing_declared_index_reports_drift__S007_002_DoD12`, `test_one_drifted_table_among_in_sync_tables_reports_drift__S007_002_DoD12`, `test_endpoint_reports_drift_for_a_hand_drifted_production_table__S007_002_DoD12`
  - DoD-13: `test_registry_created_tables_report_ok__S007_002_DoD13`, `test_production_registry_created_fresh_reports_ok__S007_002_DoD13`, `test_hand_written_in_sync_table_reports_ok__S007_002_DoD13`
  - DoD-14: `test_missing_outranks_drift__S007_002_DoD14`, `test_missing_outranks_drift_whatever_the_declaration_order__S007_002_DoD14`
  - DoD-15: `test_drift_rolls_up_to_degraded_while_unconfigured__S007_002_DoD15`, `test_drift_rolls_up_to_degraded_even_when_configured__S007_002_DoD15`, `test_missing_rolls_up_to_degraded_even_when_configured__S007_002_DoD15`, `test_in_sync_schema_while_unconfigured_rolls_up_to_unconfigured__S007_002_DoD15`, `test_in_sync_schema_while_configured_rolls_up_to_ok__S007_002_DoD15`
  - DoD-16: `test_health_body_is_three_closed_values_and_names_nothing__S007_002_DoD16` (parametrized over missing / drift / ok)
  - DoD-17: `test_probe_still_takes_a_connection_and_a_registry__S007_002_DoD17`, `test_probe_answers_for_the_registry_it_is_given__S007_002_DoD17`, `test_health_service_imports_the_schema_registry_nowhere__S007_002_DoD17`, `test_health_router_still_imports_the_registry_and_passes_it__S007_002_DoD17`
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓, DoD-16 ✓, DoD-17 ✓, DoD-18 [manual/live, no test], DoD-19 [manual/live, no test]

### Step 003 — tests (2026-09-30)
- `backend/tests/test_sync_executor.py` (new) — covers DoD-1..DoD-15, DoD-17..DoD-19 — `create_table` / `sync_table` against real `.sqlite` files, purpose-made `MetaData` registries (a `notes` table with one index; a `parents`/`children` FK pair), hand-drifted with raw DDL; state snapshots via `sqlite_master` SQL, `PRAGMA table_info` / `index_list`, `SELECT *` and a fresh `build_drift_report`; statements recorded with a `before_cursor_execute` listener; loguru captured with a temporary sink. DoD-11 failures are NOT NULL tightening over existing NULLs and a declared UNIQUE index over duplicates (no cast-failure case: SQLite affinity does not reliably refuse a cast).
  - DoD-1: `test_create_on_a_missing_table_builds_every_declared_column_nullability_and_index__DoD1`, `test_create_on_a_missing_table_leaves_other_tables_alone__DoD1`
  - DoD-2: `test_create_on_an_existing_table_changes_nothing_and_answers_the_current_truth__DoD2` (parametrized: in sync, extra+missing column, changed type, changed nullability, missing index, extra index), `test_create_on_a_drifted_table_reports_its_drift_rather_than_fixing_it__DoD2`
  - DoD-3: `test_create_never_drops_a_column_the_registry_no_longer_declares__DoD3` (parametrized), `test_create_issues_no_drop_in_any_state__DoD3` (parametrized: missing, in sync, drifted)
  - DoD-4: `test_sync_on_a_missing_table_creates_it_in_sync__DoD4`
  - DoD-5: `test_sync_on_an_in_sync_table_touches_neither_schema_nor_rows__DoD5` (parametrized: registry-made, hand-written)
  - DoD-6: `test_sync_adds_a_missing_column_and_keeps_every_row__DoD6`
  - DoD-7: `test_sync_rebuilds_a_changed_column_and_preserves_every_value__DoD7` (parametrized: type, loosened, tightened over no NULLs)
  - DoD-8: `test_sync_drops_an_undeclared_column_and_preserves_the_survivors__DoD8` (parametrized)
  - DoD-9: `test_sync_brings_the_index_set_into_line__DoD9` (parametrized: missing, extra, uniqueness differs, missing+extra)
  - DoD-10: `test_answer_for_a_missing_table_is_re_derived_after_the_apply__DoD10` (both operations), `test_sync_answer_for_a_drifted_table_is_re_derived_after_the_apply__DoD10`
  - DoD-11: `test_a_rebuild_that_cannot_complete_raises_and_leaves_the_table_exactly_as_it_was__DoD11` (parametrized: NOT NULL over NULLs, UNIQUE over duplicates)
  - DoD-12: `test_no_alembic_temp_table_survives_a_failed_rebuild__DoD12` (parametrized incl. FK violation; same and fresh connection)
  - DoD-13: `test_foreign_keys_are_back_on_and_clean_after_rebuilding_a_referenced_table__DoD13`, `test_foreign_keys_are_back_on_after_a_successful_plain_rebuild__DoD13`, `test_foreign_keys_are_back_on_after_a_failed_rebuild__DoD13` (parametrized)
  - DoD-14: `test_a_rebuild_that_would_leave_a_foreign_key_violation_is_refused__DoD14`
  - DoD-15: `test_an_undeclared_table_name_is_refused_with_no_ddl__DoD15` (both operations x absent, live-but-undeclared, five SQL-punctuation names)
  - DoD-17: `test_failed_sync_detail_is_table_and_operation_with_no_driver_text__DoD17` (parametrized), `test_failed_creation_names_its_operation_and_carries_no_driver_text__DoD17` (both operations; index-name collision), `test_foreign_key_refusal_log_carries_no_stored_value__DoD17`
  - DoD-18: `test_no_count_is_issued_by_any_apply__DoD18`, `test_answers_and_errors_carry_no_count__DoD18`, `test_sync_module_source_contains_no_count_query__DoD18`
  - DoD-19: `test_sync_module_imports_no_fastapi_name__DoD19`, `test_import_boundaries_hold__DoD19` (parametrized: sync/schema, drift/schema, drift/sync), `test_the_registry_arrives_as_an_argument__DoD19`
- `backend/tests/test_errors.py` (extended; every pre-existing test untouched) — covers DoD-16 — `unknown_table`/404 and `schema_apply_failed`/500 as `DomainError` subclasses with only `code`/`http_status` (no own `__init__`), caller detail kept, wire shape via `to_wire()` and via the registered handler, no second handler, distinct new codes.
  - DoD-16: `test_schema_error_is_a_domain_error_subclass__S007_003_DoD16`, `test_schema_error_sets_code_and_status_as_class_attributes__S007_003_DoD16`, `test_schema_error_carries_only_code_and_http_status__S007_003_DoD16`, `test_schema_error_keeps_the_callers_detail__S007_003_DoD16`, `test_schema_error_renders_the_one_wire_shape__S007_003_DoD16`, `test_schema_error_from_a_route_answers_its_status_in_the_wire_shape__S007_003_DoD16`, `test_schema_error_without_a_message_still_renders_the_wire_shape__S007_003_DoD16` (all parametrized over the two), `test_no_second_handler_is_registered_for_the_schema_errors__S007_003_DoD16`, `test_the_two_schema_errors_carry_distinct_new_codes__S007_003_DoD16`
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓, DoD-16 ✓, DoD-17 ✓, DoD-18 ✓, DoD-19 ✓, DoD-20 [manual/live, no test], DoD-21 [manual/live, no test], DoD-22 [manual/live, no test]

### Step 004 — tests (2026-09-30)
- `backend/tests/test_admin_db_router.py` (new) — covers DoD-1..DoD-14 — real `create_app()` built locally (not a context manager), `dependency_overrides[get_settings]`, seeded admin + roleplayer, cookies via `/api/auth/login`; the real registry made with `metadata.create_all` then hand-drifted with raw DDL (models dropped for "missing"; llm_servers drifted by ALTER only — missing/extra/retyped/re-nulled columns + extra index; auth_sessions missing `user_id` index; models extra + retyped column); snapshots via `sqlite_master` / `PRAGMA table_info` / `SELECT`; OpenAPI for the route surface; ast scans + spies on the router's module-level `build_drift_report` / `create_table` / `sync_table` names for DoD-13.
  - DoD-1: `test_report_lists_every_registry_table_in_declaration_order__DoD1`, `test_every_entry_carries_a_status_from_the_closed_set__DoD1`, `test_freshly_created_registry_reports_every_table_in_sync__DoD1`
  - DoD-2: `test_report_distinguishes_in_sync_missing_and_drifted__DoD2`, `test_in_sync_entry_carries_no_difference__DoD2`, `test_drifted_entry_carries_its_missing_and_extra_columns__DoD2`, `test_drifted_entry_carries_changed_columns_with_expected_and_actual__DoD2`, `test_a_column_is_named_in_one_list_only__DoD2`, `test_drifted_entry_carries_its_extra_index__DoD2`, `test_drifted_entry_carries_its_missing_index__DoD2`
  - DoD-3: `test_report_payload_carries_no_count_size_time_or_user_material__DoD3`, `test_apply_answers_carry_no_count_size_time_or_user_material__DoD3` (both ops), `test_response_models_declare_no_count_size_or_time_field__DoD3`, `test_router_declares_only_the_three_routes__DoD3`, `test_router_declares_no_query_parameter_and_no_non_table_key__DoD3`
  - DoD-4: `test_every_route_refuses_a_roleplayer_with_403__DoD4`, `test_every_route_answers_401_without_a_session__DoD4`, `test_every_route_answers_401_for_an_unissued_cookie__DoD4` (all x3 routes), `test_guard_answers_before_the_table_name_is_looked_at__DoD4`, `test_refused_apply_requests_change_nothing__DoD4`, `test_administrator_is_admitted_on_every_route__DoD4`
  - DoD-5: `test_route_without_its_own_dependency_is_refused_for_a_roleplayer__DoD5`, `..._is_401_without_a_session__DoD5`, `..._is_reachable_for_an_administrator__DoD5`, `test_probe_route_does_not_leak_into_other_applications__DoD5` (`guarded_probe_app` adds a route to the production router object)
  - DoD-6: `test_create_on_a_missing_table_answers_it_in_sync__DoD6`, `test_create_on_a_missing_table_is_reflected_by_the_next_report__DoD6`, `test_create_on_a_missing_table_leaves_every_other_table_alone__DoD6`
  - DoD-7: `test_create_on_an_existing_table_changes_nothing__DoD7` (users/llm_servers in sync, models/llm_servers drifted), `test_create_on_a_drifted_table_reports_its_drift_rather_than_fixing_it__DoD7`
  - DoD-8: `test_sync_on_a_drifted_table_answers_it_in_sync__DoD8` (models extra+retyped, models missing column, llm_servers mixed, auth_sessions missing index)
  - DoD-9: `test_sync_drops_an_undeclared_column_and_keeps_every_surviving_value__DoD9`, `test_sync_of_a_referenced_table_drops_its_extra_column_and_keeps_both_tables_data__DoD9`
  - DoD-10: `test_create_ignores_a_supplied_body__DoD10`, `test_sync_ignores_a_supplied_body__DoD10` (JSON and text bodies), `test_apply_routes_ignore_a_supplied_query_string__DoD10`, `test_apply_routes_declare_no_request_body_and_no_query_parameter__DoD10`
  - DoD-11: `test_undeclared_table_name_is_refused_404_with_no_ddl__DoD11` (9 names incl. live-undeclared, `sqlite_master` and SQL punctuation x both ops; statement recorder + schema/row snapshots)
  - DoD-12: `test_sync_that_cannot_complete_answers_500_schema_apply_failed__DoD12`, `test_sync_that_cannot_complete_leaves_the_table_exactly_as_it_was__DoD12` (NOT NULL over NULLs on models; UNIQUE over duplicates on auth_sessions) — Sync only: no Create failure is reachable on the real registry without dropping a login-critical table
  - DoD-13: `test_router_imports_the_registry_at_module_level__DoD13`, `test_every_handler_passes_the_registry_down_and_never_looks_into_it__DoD13`, `test_router_issues_no_sql_opens_no_transaction_and_translates_no_error__DoD13`, `test_report_route_calls_the_report_builder_once_with_the_registry__DoD13`, `test_apply_route_calls_its_one_operation_with_the_registry_and_the_raw_name__DoD13`, `test_unknown_table_refusal_comes_from_the_service__DoD13`, `test_handler_maps_whatever_the_service_answers__DoD13`, `test_database_contact_goes_only_through_the_connection_dependency__DoD13`
  - DoD-14: `test_route_surface_has_no_rebuild_export_import_or_vector_route__DoD14`, `test_route_surface_documents_nothing_about_a_vector_index__DoD14`, `test_out_of_scope_routes_do_not_exist__DoD14`
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 [manual/live, no test], DoD-16 [manual/live, no test], DoD-17 [manual/live, no test], DoD-18 [manual/live, no test]

### Step 005 — tests (2026-09-30)
- `frontend/tests/admin/databasePage.test.tsx` (new) — covers DoD-1..DoD-14 — `<DatabasePage state={new DatabasePageState()} />` under `AppProviders` + `MemoryRouter`; `fetch` stubbed per test; `notifyFailure` mocked; the store module wrapped pass-through to observe `loadDriftReport` / `statusBadgeOf` / `differencesSummaryOf` calls; full `AdminApp` rendered for the route block. Store-shape assertions tolerate step 006's `applyingTable` (allowed, never required); snapshots cover whatever own fields exist.
  - DoD-1: one GET of `/api/admin/database/tables` with no query; `DRIFT_REPORT_PATH` equals it; one row per table in response order (two orders); name + status shown; load writes rows verbatim, status `ready`.
  - DoD-2: helper labels are the three status words and distinct; each row renders one badge whose text is its word.
  - DoD-3: helper colours in_sync→green, drifted→yellow, missing→red; pure, reads only status; rendered badge carries its colour (Mantine CSS variable in the badge's inline style); page source names no `green`/`yellow` literal and references `statusBadgeOf`.
  - DoD-4: summary names missing/extra/changed columns, expected+actual type, nullability, expected≠actual when swapped, missing≠extra wording, index column lists; pure; drifted row's Columns/Indexes cells render the helper's text.
  - DoD-5: payload count/size/timestamp extras never rendered; no rendered piece is a digit-bearing claim about rows/users/etc., a byte size or a date; helper output likewise.
  - DoD-6: Loader and no tbody while in flight; status idle→loading→ready; Loader gated on status with rows present; empty ready report = four headers, no rows, no Loader.
  - DoD-7: failure → Alert (above any table), no notification, `notifyFailure` never called; errorMessage-with-table renders Alert above the table; load never rejects; transport failure → Alert; no notification import in either module; success raises no Alert/notification.
  - DoD-8: no `id`/`*Id`/`*_id`/`ID`/`parseInt` in either module; row `key` uses `table_name`; no id-like store field; loaded rows carry no id; load called with (state, signal) only.
  - DoD-9: no sort control/filter input/pagination; no request has a query; plain `<Table`, no data-table lib, no `.sort`.
  - DoD-10: no control or text naming Export/Import/Rebuild (loaded and empty); no control outside the report table; no such wording in the page source's literals/JSX text.
  - DoD-11: prototype is `["constructor"]`; own fields ⊆ {rows,status,errorMessage,applyingTable}, required three observable, none computed/function; fresh store idle; page calls load with store first + signal; strict-MobX no warnings; pre-aborted signal and post-abort response write nothing; `useState(() => new DatabasePageState(` scan, no `useMemo`, `runInAction` in the store module.
  - DoD-12: unmount aborts the in-flight request's signal; neither a late success nor a late failure is written.
  - DoD-13: `/database` renders the page (one report GET, 3 rows, not 404); `/` and `/llm-servers` unchanged; `/nope` still 404; AdminApp source: four flat self-closing `<Route>`s, path set, no `Outlet`, `/database` element no longer `NotFoundPage`.
  - DoD-14: no stylesheet file or stylesheet import under `src/admin/`; no `className=` / `<style` in the page source.
  - Rework (TEST fault, DoD-10): rendered-text helpers (`readableText`, `readablePieces`, `controlName`, the route tests' `main()` text) now read only visible text nodes, skipping `style`/`script`/`noscript`/`template` contents; the Export/Import/Rebuild pattern matches whole words only. No test names changed.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 [manual/live, no test], DoD-16 [manual/live, no test], DoD-17 [manual/live, no test]

### Step 006 — tests (2026-09-30)
- `frontend/tests/admin/databaseActions.test.tsx` (new) — covers DoD-1..DoD-16 — `<DatabasePage state={...} />` under `AppProviders` + `MemoryRouter`; `fetch` stubbed per test by an in-memory backend honouring D4 (GET report; POST `.../{name}/create` turns a missing table in sync, else no-op; POST `.../{name}/sync` turns any table in sync; both answer the row) with a per-test override hook; `notifyFailure` mocked; the store module wrapped pass-through to observe `createDriftTable` / `syncDriftTable` / `loadDriftReport` / `isLossySync` / `syncConsequenceOf`. Row trigger = the row's single icon-only control (accessible name not relied on); menu-race workaround (`openRowMenu` + `waitFor(dropdownFor)`, `findByRole("menuitem")`, `pointerEventsCheck: 0`) reused from 006/006. Fixtures: users in sync, models missing, llm_servers drifted without extra column, auth_sessions drifted with two extra columns; all names digit-free.
  - DoD-1: missing offers Create not Sync; drifted (safe + lossy) offers Sync not Create; in-sync row has no control and an empty trailing cell; every offered item enabled and the other action's word absent from the dropdown.
  - DoD-2: Create → exactly one POST to `.../models/create`, no dialog (also while the POST is pending), effect called (state, name); no request body.
  - DoD-3: GET after the POST and badge turns in sync; rows come from the re-load, not the apply answer (stale-report case); another table's change arriving with the re-load is shown; effect writes no row before the re-load answers.
  - DoD-4: non-lossy Sync → one POST to `.../llm_servers/sync`, no dialog, no body, re-load, badge in sync; predicate false for no extra column (drifted/missing/in-sync).
  - DoD-5: lossy Sync opens a dialog with no request; dialog names table + every extra column + drop wording and contains `syncConsequenceOf(row)`; predicate true for one/several extras; extra-only row still confirms; helper names table + columns.
  - DoD-6: cancel → no request, dialog closes, row text/badge/store unchanged; confirm → one POST sync then GET, effect called (state, name), badge turns in sync; cancel-then-reopen-confirm.
  - DoD-7: page imports `shared/ConfirmModal`, renders `<ConfirmModal`, no `<Modal`/Mantine `Modal` import; no open/modal/confirm/target/dialog store field; opening/cancelling changes no store field; confirm button named exactly "Sync", red in its inline style, after Cancel in DOM order.
  - DoD-8: dialog has no count claim, no digit, no number word, no "rows affected" even with count extras in the payload; no rendered piece (menus + dialog open) is a count claim or shows a payload count; helper output count-free and count-independent.
  - DoD-9: helper and rendered dialog state other columns' data preserved; helper names no surviving (missing) column.
  - DoD-10: failed Create / direct Sync / confirmed Sync (500 `schema_apply_failed`) and a transport failure → message in an Alert above the table, `applyingTable` null, no notification, `notifyFailure` not called, menu usable again; effect marks `applyingTable` = name in flight then clears it and writes `errorMessage`; no notification import.
  - DoD-11: failed effect leaves `rows` exactly as before; row still shows missing/drifted after failure, turns in sync after a later successful apply.
  - DoD-12: successful Create + Sync + confirmed Sync raise no notification, no Alert, no "success" text; badges turn in sync; neither module imports a notif/toast specifier.
  - DoD-13: each actionable row has exactly one icon-only control in its trailing cell, with an accessible name; menu items text-labelled; source: `shared/IconButton` import, `<IconButton … icon={IconDots}`, one `<IconButton`, `<Menu`/`<Menu.Item`, `w={60}`, no `ActionIcon`.
  - DoD-14: no Rebuild/Export/Import/re-index item in any row's menu; no such control on the page.
  - DoD-15: prototype `["constructor"]`; own fields ⊆ {rows,status,errorMessage,applyingTable}, all observable, none computed/function, `applyingTable` null when fresh; page calls effects (state, name, signal?); strict-MobX no warnings over success/failure/transport; pre-aborted signal and mid-request abort write nothing; effects never reject; predicate and helper pure without a render; `runInAction` + exported async effect functions in the store source.
  - DoD-16: unmount mid-Create aborts the POST's signal; late success (Sync) and late failure (Create) after unmount write nothing.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓, DoD-16 ✓, DoD-17 [manual/live, no test], DoD-18 [manual/live, no test]

## Notes & Issues

- Step 005: the coder's session-start read of `status.md` displayed the `## Tests` section (same file); no test file was opened and the implementation follows the step spec and frozen signatures.
- Step 003: a scratch experiment accidentally ran against the dev database `backend/data/rphelper.sqlite` (`Settings(data_dir=...)` is ignored because the field has a `validation_alias`) and left scratch tables `parent` and `child` (plus index `ix_parent_name`) in it; dropping them was denied by the permission system — the user should drop them by hand.
- Step 003: once `db/schema.py` declares SQL views (`data-model.md`), a Sync rebuild of a table a view references may fail at the rename step (SQLite re-parses views on `ALTER TABLE ... RENAME` while the old table is already dropped); the failure is safe (rollback, `schema_apply_failed`) but the table would be un-syncable until views are handled around the rebuild.
- Step 003: the D5 "value that will not cast" refusal is a post-copy `typeof` probe applied only to columns whose type text changed to an INTEGER/REAL/NUMERIC/DECIMAL/BOOLEAN declaration; DATE/TIME/JSON targets (NUMERIC affinity, stored as text by SQLAlchemy) and text targets are never refused.
- Step 006: the coder's session-start read of `status.md` displayed the `## Tests` section (same file); no test file was opened and the implementation follows the step spec and frozen signatures.

## Ultra phase

- orient: done 2026-09-30
- harvest: done — docs/.cache/ultra/007.schema-drift-and-remediation/harvest.md (2 reports)   (note: frontend/tests/admin/AdminApp.test.tsx + llmServersPage.test.tsx carry stale '/database renders 404' assertions outside every 007 step's Test files — expected to fail at verify, as in 006)
- skeleton: done — steps 001, 002, 003, 004, 005, 006   (003: alembic>=1.14,<2.0 added, 1.20.0 installed via uv lock + uv sync --inexact)
- tests: done — steps 001, 002, 003, 004, 005, 006
- red-gate: FAIL (run 1) — 004 TEST (DoD-14 test json.dumps on tuple-keyed dict); 001–003, 005, 006 PASS. Note: 15 AdminApp.test.tsx cases + 1 llmServersPage.test.tsx case visit /database and break on the new route (cross-feature, outside 007 Test files)
- red-gate: PASS (run 2) — cross-feature /database breakage set unchanged (15 AdminApp.test.tsx + 1 llmServersPage.test.tsx)
- code: done — steps 001, 002, 003, 004, 005, 006   (no re-freeze; 003 coder's scratch run wrote parent/child/ix_parent_name into backend/data/rphelper.sqlite — user to clean up; coders saw ## Tests headings in status.md, opened no test file)
- verify: FAIL (run 1) — 005 TEST (DoD-10 text scan reads injected <style> content, matches "!important" as "import"); 001–004, 006 PASS; backend 1701/1701; frontend 5 fail (2 × 005, 3 cross-feature stale '/database 404' cases in AdminApp.test.tsx ×2, llmServersPage.test.tsx ×1)
- verify: PASS (run 2) — backend 1701/1701; 007 frontend tests 149/149; full npm test 1727/1730 — the 3 failures are cross-feature stale "/database renders 404" cases (AdminApp.test.tsx:491, :519; llmServersPage.test.tsx:1473), outside 007 scope
