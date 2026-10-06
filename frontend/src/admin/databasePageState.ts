// The Database page's data: observable fields only, no methods, no computed getters.
// The report load, the status-badge derivation and the differences summary are the free
// functions below.
import { makeAutoObservable, runInAction } from "mobx";
import type { MantineColor } from "@mantine/core";
import {
  type DownloadResult,
  apiDownload,
  apiGet,
  apiPost,
  documentNavigation,
} from "../shared/api";
import { type ReadableTextFile, postExportFile } from "../shared/importFile";

/** The backend's closed three-value table status — never widened to `string`. */
export type TableStatus = "in_sync" | "missing" | "drifted";

/** One column's shape as the drift report sends it. */
export type ColumnShape = {
  name: string;
  type_text: string;
  not_null: boolean;
};

/** One index's shape as the drift report sends it: its columns in order and its unique flag. */
export type IndexShape = {
  columns: string[];
  unique: boolean;
};

/** A column present on both sides whose declared and live shapes differ. */
export type ChangedColumn = {
  name: string;
  expected: ColumnShape;
  actual: ColumnShape;
};

/**
 * One table's row, exactly as `GET /api/admin/database/tables` sends it. The row key is
 * `table_name`; there is no id, no row count, no size and no timestamp.
 */
export type DriftTableRow = {
  table_name: string;
  status: TableStatus;
  missing_columns: string[];
  extra_columns: string[];
  changed_columns: ChangedColumn[];
  missing_indexes: IndexShape[];
  extra_indexes: IndexShape[];
};

/** The report route's body: `{ tables: [...] }`, in registry declaration order. */
export type DriftReportResponse = {
  tables: DriftTableRow[];
};

/** Explicit load status: gates the Loader, not "rows are empty". */
export type DatabaseLoadStatus = "idle" | "loading" | "ready";

/** The whole-database export's own two-value status: gates the Export button's loading state. */
export type DatabaseExportStatus = "idle" | "exporting";

/**
 * The whole-database import's own two-value status, shaped like `DatabaseExportStatus`: gates
 * the Import button's and the replace confirm's loading state. Never widened to `string`.
 */
export type DatabaseImportStatus = "idle" | "importing";

/**
 * The index rebuild's own two-value status, shaped like `DatabaseExportStatus`: gates the
 * Rebuild index button's disabled state and the rebuild confirm's loading state.
 */
export type DatabaseRebuildStatus = "idle" | "rebuilding";

/** The status badge's rendering, derived by `statusBadgeOf`. The label is the status word. */
export type StatusBadge = {
  label: string;
  color: MantineColor;
};

/** The two summary cells' text, derived by `differencesSummaryOf`. */
export type DifferencesSummary = {
  /** Missing, extra and changed columns (a changed column with its expected and actual shape). */
  columns: string;
  /** Missing and extra indexes, each named by its column list. */
  indexes: string;
};

export class DatabasePageState {
  rows: DriftTableRow[] = [];
  status: DatabaseLoadStatus = "idle";
  errorMessage: string | null = null;
  /** The table a Create or Sync is currently being applied to; `null` when none is. */
  applyingTable: string | null = null;
  /** `"exporting"` while a whole-database export is in flight; `"idle"` otherwise. */
  exportStatus: DatabaseExportStatus = "idle";
  /**
   * The last successful export's size in bytes; `null` when no export has succeeded in this
   * page's lifetime. The only thing the page keeps about an export — never its content, never
   * a table name, never a row count (US-078).
   */
  exportSizeBytes: number | null = null;
  /**
   * The last export failure's message, for the page's inline red Alert; `null` when none.
   * Deliberately separate from `errorMessage` (the drift report's), so neither failure ever
   * overwrites the other's message.
   */
  exportErrorMessage: string | null = null;
  /**
   * The file the administrator chose for a whole-database import, or `null` when none is
   * chosen. There is no separate open flag: the replace confirm's openness is **derived** from
   * this field being non-null, and cancelling clears it. Nothing about the file's contents is
   * ever read into the store (US-078).
   */
  importFile: ReadableTextFile | null = null;
  /** `"importing"` while a whole-database import is in flight; `"idle"` otherwise. */
  importStatus: DatabaseImportStatus = "idle";
  /**
   * The last import failure's message, for the page's own inline red Alert; `null` when none.
   * Deliberately separate from `errorMessage` (the drift report's) and from
   * `exportErrorMessage`, so no failure ever overwrites another's message.
   */
  importErrorMessage: string | null = null;
  /** `"rebuilding"` while an index rebuild is in flight; `"idle"` otherwise. */
  rebuildStatus: DatabaseRebuildStatus = "idle";
  /**
   * The last rebuild failure's message, for the rebuild's own inline red Alert; `null` when
   * none. Separate from the drift report's, export's and import's slots.
   */
  rebuildErrorMessage: string | null = null;
  /** `true` after a successful rebuild; cleared when a new rebuild starts. Never a count. */
  rebuildComplete: boolean = false;

  constructor() {
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/** The drift report route. Sent with no query parameter. */
export const DRIFT_REPORT_PATH = "/api/admin/database/tables";

/** The whole-database export route. Sent with no query parameter and no body. */
const DATABASE_EXPORT_PATH = "/api/admin/database/export";

/** The whole-database import route. Answers 204 and clears the session cookie. */
const DATABASE_IMPORT_PATH = "/api/admin/database/import";

/** Where the browser goes after a successful replace: the replace signs the administrator out. */
const LOGIN_PATH = "/login";

const NO_DIFFERENCE = "—";

/** `formatByteSize`'s 1024-based thresholds. */
const BYTES_PER_KB = 1024;
const BYTES_PER_MB = 1024 * 1024;

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function failureMessageOf(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }
  return fallback;
}

function columnShapeText(shape: ColumnShape): string {
  return `${shape.type_text} ${shape.not_null ? "NOT NULL" : "NULL"}`;
}

function changedColumnText(change: ChangedColumn): string {
  return `${change.name} (expected ${columnShapeText(change.expected)}, actual ${columnShapeText(change.actual)})`;
}

function indexText(index: IndexShape): string {
  return `${index.unique ? "unique " : ""}(${index.columns.join(", ")})`;
}

/**
 * `GET /api/admin/database/tables`; writes `rows` and `status` (idle → loading → ready) in
 * `runInAction`. Returns without writing when `signal` is aborted. A failure sets
 * `errorMessage`. Does not reject.
 */
export async function loadDriftReport(state: DatabasePageState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  if (state.status !== "ready") {
    runInAction(() => {
      state.status = "loading";
    });
  }

  let body: DriftReportResponse | undefined;
  try {
    body = await apiGet<DriftReportResponse | undefined>(DRIFT_REPORT_PATH, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    const message = failureMessageOf(error, "The drift report could not be loaded.");
    runInAction(() => {
      state.status = "ready";
      state.errorMessage = message;
    });
    return;
  }

  if (signal?.aborted) {
    return;
  }
  const rows = body?.tables ?? [];
  runInAction(() => {
    state.rows = rows;
    state.status = "ready";
    state.errorMessage = null;
  });
}

/**
 * Pure: the badge's label (the status word) and colour from the row's status —
 * in sync → green, drifted → yellow, missing → red (`context.md` D11).
 */
export function statusBadgeOf(row: Pick<DriftTableRow, "status">): StatusBadge {
  switch (row.status) {
    case "in_sync":
      return { label: "In sync", color: "green" };
    case "drifted":
      return { label: "Drifted", color: "yellow" };
    case "missing":
      return { label: "Missing", color: "red" };
  }
}

/**
 * Pure: the Columns and Indexes cells' text from a row's five difference lists. Names the
 * columns, index column-lists and a changed column's expected and actual values; names no
 * count of rows and derives nothing from content.
 */
export function differencesSummaryOf(
  row: Pick<
    DriftTableRow,
    "missing_columns" | "extra_columns" | "changed_columns" | "missing_indexes" | "extra_indexes"
  >,
): DifferencesSummary {
  const columnParts: string[] = [];
  if (row.missing_columns.length > 0) {
    columnParts.push(`Missing: ${row.missing_columns.join(", ")}`);
  }
  if (row.extra_columns.length > 0) {
    columnParts.push(`Extra: ${row.extra_columns.join(", ")}`);
  }
  if (row.changed_columns.length > 0) {
    columnParts.push(`Changed: ${row.changed_columns.map(changedColumnText).join(", ")}`);
  }

  const indexParts: string[] = [];
  if (row.missing_indexes.length > 0) {
    indexParts.push(`Missing: ${row.missing_indexes.map(indexText).join(", ")}`);
  }
  if (row.extra_indexes.length > 0) {
    indexParts.push(`Extra: ${row.extra_indexes.map(indexText).join(", ")}`);
  }

  return {
    columns: columnParts.length > 0 ? columnParts.join("; ") : NO_DIFFERENCE,
    indexes: indexParts.length > 0 ? indexParts.join("; ") : NO_DIFFERENCE,
  };
}

/** The two apply operations' route suffixes. */
type ApplyOperation = "create" | "sync";

function applyPathOf(tableName: string, operation: ApplyOperation): string {
  return `${DRIFT_REPORT_PATH}/${encodeURIComponent(tableName)}/${operation}`;
}

async function applyDriftOperation(
  state: DatabasePageState,
  tableName: string,
  operation: ApplyOperation,
  fallback: string,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    state.applyingTable = tableName;
  });

  try {
    await apiPost<unknown>(applyPathOf(tableName, operation), undefined, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    const message = failureMessageOf(error, fallback);
    runInAction(() => {
      state.errorMessage = message;
      if (state.applyingTable === tableName) {
        state.applyingTable = null;
      }
    });
    return;
  }

  if (signal?.aborted) {
    return;
  }
  await loadDriftReport(state, signal);
  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    if (state.applyingTable === tableName) {
      state.applyingTable = null;
    }
  });
}

/**
 * `POST /api/admin/database/tables/{tableName}/create` with no body. Sets `applyingTable`
 * before the call and clears it on both paths, all in `runInAction`. On success re-loads the
 * whole report via `loadDriftReport` (never patches the row from the response). A failure
 * sets `errorMessage`. Returns without writing when `signal` is aborted. Does not reject.
 */
export async function createDriftTable(
  state: DatabasePageState,
  tableName: string,
  signal?: AbortSignal,
): Promise<void> {
  await applyDriftOperation(state, tableName, "create", "The table could not be created.", signal);
}

/**
 * `POST /api/admin/database/tables/{tableName}/sync` with no body — the same shape as
 * `createDriftTable`. Confirms nothing itself; the page's confirm callback invokes it.
 */
export async function syncDriftTable(
  state: DatabasePageState,
  tableName: string,
  signal?: AbortSignal,
): Promise<void> {
  await applyDriftOperation(state, tableName, "sync", "The table could not be synced.", signal);
}

/** Pure: a Sync is lossy exactly when the row lists at least one extra column (`context.md` D7). */
export function isLossySync(row: Pick<DriftTableRow, "extra_columns">): boolean {
  return row.extra_columns.length > 0;
}

/**
 * Pure: the lossy-Sync confirm's one sentence — names the table and every column that will
 * be dropped, and states that the data in every other column is preserved. Names no count.
 */
export function syncConsequenceOf(row: Pick<DriftTableRow, "table_name" | "extra_columns">): string {
  const noun = row.extra_columns.length === 1 ? "column" : "columns";
  const pronoun = row.extra_columns.length === 1 ? "it" : "them";
  return (
    `Syncing ${row.table_name} drops the ${noun} ${row.extra_columns.join(", ")} ` +
    `and the data in ${pronoun}; the data in every other column is preserved.`
  );
}

/**
 * `GET /api/admin/database/export` through `apiDownload`, which saves the file in the browser.
 * Sets `exportStatus` to `"exporting"` and clears `exportSizeBytes` and `exportErrorMessage`
 * first, then stores the resolved `size` on success or the failure's message on failure, and
 * returns `exportStatus` to `"idle"`. Every write is inside `runInAction`. Returns without
 * writing when `signal` is already aborted, and on an abort mid-flight. Raises **no**
 * notification — the admin page's failure place is its inline Alert and nothing else — and
 * reads nothing from the response but its byte count (US-078). Does not reject.
 */
export async function exportDatabase(state: DatabasePageState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    state.exportStatus = "exporting";
    state.exportSizeBytes = null;
    state.exportErrorMessage = null;
  });

  let result: DownloadResult;
  try {
    result = await apiDownload(DATABASE_EXPORT_PATH, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    const message = failureMessageOf(error, "The export could not be downloaded.");
    runInAction(() => {
      state.exportStatus = "idle";
      state.exportErrorMessage = message;
    });
    return;
  }

  if (signal?.aborted) {
    return;
  }
  const sizeBytes = result.size;
  runInAction(() => {
    state.exportStatus = "idle";
    state.exportSizeBytes = sizeBytes;
  });
}

/**
 * Pure: a byte count as short human text, 1024-based, with one decimal above bytes —
 * `0` → `"0 B"`, `512` → `"512 B"`, `12_600` → `"12.3 KB"`, `4_194_304` → `"4.0 MB"`. Bytes
 * carry no decimal. Never throws.
 */
export function formatByteSize(bytes: number): string {
  if (bytes < BYTES_PER_KB) {
    return `${bytes} B`;
  }
  if (bytes < BYTES_PER_MB) {
    return `${(bytes / BYTES_PER_KB).toFixed(1)} KB`;
  }
  return `${(bytes / BYTES_PER_MB).toFixed(1)} MB`;
}

/**
 * Stores the file the administrator chose for a whole-database import and clears the previous
 * import failure's message, both inside `runInAction`. It sends nothing and confirms nothing:
 * storing the file is what **opens** the replace confirm, because the confirm's openness is
 * derived from `importFile` being non-null. Reads nothing from the file.
 */
export function chooseImportFile(state: DatabasePageState, file: ReadableTextFile): void {
  runInAction(() => {
    state.importFile = file;
    state.importErrorMessage = null;
  });
}

/**
 * Clears the chosen import file inside `runInAction`, which is what **closes** the replace
 * confirm. It sends nothing, leaves `importStatus` and every message alone, and so leaves the
 * rest of the page exactly as it was.
 */
export function cancelImport(state: DatabasePageState): void {
  runInAction(() => {
    state.importFile = null;
  });
}

/**
 * The whole-database replace: posts the chosen `importFile` to
 * `/api/admin/database/import` through step 006's `postExportFile`, whose own unreadable-file
 * `ApiError` is raised before any request.
 *
 * Sets `importStatus` to `"importing"` first. On success — the route answers 204, so the
 * resolved value is `unknown` and nothing is read from it — it calls
 * `documentNavigation.assign("/login")`, because the replace signs the administrator out. On a
 * failure it stores the error's message in `importErrorMessage`, clears `importFile` (which
 * closes the confirm) and returns `importStatus` to `"idle"`. Every write is inside
 * `runInAction`. Returns without writing when `signal` is already aborted, and on an abort
 * mid-flight. Raises **no** notification — the admin page's failure place is its inline Alert
 * and nothing else — and renders nothing about the file. Does not reject.
 */
export async function importDatabase(state: DatabasePageState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  const file = state.importFile;
  if (file === null) {
    return;
  }
  runInAction(() => {
    state.importStatus = "importing";
  });

  try {
    // The 204 resolves with no body; nothing is read from the resolved value (US-078).
    await postExportFile(DATABASE_IMPORT_PATH, file, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    const message = failureMessageOf(error, "The database could not be replaced.");
    runInAction(() => {
      state.importStatus = "idle";
      state.importErrorMessage = message;
      state.importFile = null;
    });
    return;
  }

  if (signal?.aborted) {
    return;
  }
  // No write on success: the page is leaving. The confirm stays in its loading state until the
  // navigation takes effect.
  documentNavigation.assign(LOGIN_PATH);
}

/** The index rebuild route. Sent with no query parameter and no body. */
export const DATABASE_REBUILD_PATH = "/api/admin/database/rebuild";

/**
 * The index rebuild: posts `/api/admin/database/rebuild` through `apiPost`.
 *
 * Sets `rebuildStatus` to `"rebuilding"` and clears `rebuildErrorMessage` and
 * `rebuildComplete` first. On success sets `rebuildComplete` to `true`; on a failure stores
 * `failureMessageOf(error, <fallback>)` in `rebuildErrorMessage`. Always returns
 * `rebuildStatus` to `"idle"`. Every write is inside `runInAction`. Touches neither the drift
 * report, export nor import state. Raises no notification and does not reject.
 */
export async function rebuildIndex(state: DatabasePageState, signal?: AbortSignal): Promise<void> {
  runInAction(() => {
    state.rebuildStatus = "rebuilding";
    state.rebuildErrorMessage = null;
    state.rebuildComplete = false;
  });

  try {
    // The body is the fixed list of rebuilt table names; nothing is read from it.
    await apiPost<unknown>(DATABASE_REBUILD_PATH, undefined, signal);
  } catch (error) {
    const aborted = signal?.aborted === true || isAbortRejection(error);
    const message = aborted ? null : failureMessageOf(error, "The index could not be rebuilt.");
    runInAction(() => {
      state.rebuildStatus = "idle";
      if (message !== null) {
        state.rebuildErrorMessage = message;
      }
    });
    return;
  }

  runInAction(() => {
    state.rebuildStatus = "idle";
    state.rebuildComplete = true;
  });
}
