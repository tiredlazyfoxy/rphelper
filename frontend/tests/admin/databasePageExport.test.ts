// Feature 030 — export-granularities, step 005: the Database page's store half — the three
// export fields, the `exportDatabase` effect and `formatByteSize` (DoD-1, DoD-8, DoD-9,
// DoD-10). The page half lives in `DatabasePage.export.test.tsx`.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 005.context.md and the feature context.md (the size is the one permitted report; admin
// failures are inline only and never notified). Bindings come from the frozen `### Step 005`
// record: `DatabaseExportStatus`, the fields `exportStatus` / `exportSizeBytes` /
// `exportErrorMessage`, `exportDatabase(state, signal?)` and `formatByteSize(bytes)`, all
// from `src/admin/databasePageState`.
//
// `apiDownload` is replaced at module level so the effect's contract is observable without a
// network call; every other export of `shared/api` is passed through untouched.
import { isComputedProp, isObservableProp, runInAction } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  type DatabaseExportStatus,
  DatabasePageState,
  exportDatabase,
  formatByteSize,
} from "../../src/admin/databasePageState";
import { ApiError } from "../../src/shared/apiError";

const { apiDownloadMock } = vi.hoisted(() => ({ apiDownloadMock: vi.fn() }));
vi.mock("../../src/shared/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../src/shared/api")>();
  return { ...actual, apiDownload: apiDownloadMock };
});

/** context.md — the admin whole-database export route. */
const EXPORT_PATH = "/api/admin/database/export";
const FILENAME = "rphelper-database-20260105T101112Z.json";
const FAILURE_MESSAGE = "The export could not be produced (qz-71 marker).";

/** A previous export's leftovers, so "clears both at the start" is observable. */
const STALE_SIZE = 4096;
const STALE_ERROR = "A previous export failed (stale marker).";

beforeEach(() => {
  apiDownloadMock.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- helpers

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function settle(rounds = 4): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await new Promise<void>((resolve) => setImmediate(resolve));
  }
}

function withStaleExport(): DatabasePageState {
  const state = new DatabasePageState();
  runInAction(() => {
    state.exportSizeBytes = STALE_SIZE;
    state.exportErrorMessage = STALE_ERROR;
  });
  return state;
}

function failure(): ApiError {
  return new ApiError("export_failed", FAILURE_MESSAGE, 500);
}

// ---------------------------------------------------------------- the route

describe("exportDatabase asks the client for the whole-database export", () => {
  it("downloads the admin whole-database export route — DoD-1", async () => {
    apiDownloadMock.mockResolvedValue({ filename: FILENAME, size: 2048 });
    const state = new DatabasePageState();

    await exportDatabase(state);

    expect(apiDownloadMock).toHaveBeenCalledTimes(1);
    expect(apiDownloadMock.mock.calls[0][0]).toBe(EXPORT_PATH);
  });

  it("passes the signal it is given straight through to the download — DoD-1", async () => {
    apiDownloadMock.mockResolvedValue({ filename: FILENAME, size: 2048 });
    const state = new DatabasePageState();
    const controller = new AbortController();

    await exportDatabase(state, controller.signal);

    expect(apiDownloadMock.mock.calls[0][1]).toBe(controller.signal);
  });
});

// ---------------------------------------------------------------- what the effect writes

describe("exportDatabase writes only a size or an error", () => {
  it("stores the downloaded size on success, leaves no export error and returns to idle — DoD-8", async () => {
    apiDownloadMock.mockResolvedValue({ filename: FILENAME, size: 12595 });
    const state = new DatabasePageState();

    await exportDatabase(state);

    expect(state.exportSizeBytes).toBe(12595);
    expect(state.exportErrorMessage).toBeNull();
    expect(state.exportStatus).toBe("idle");
    // The drift report's own message is a separate field and stays untouched.
    expect(state.errorMessage).toBeNull();
  });

  it("stores the failure's message on failure, leaves no size and returns to idle — DoD-8", async () => {
    apiDownloadMock.mockRejectedValue(failure());
    const state = new DatabasePageState();

    await exportDatabase(state);

    expect(state.exportErrorMessage).toBe(FAILURE_MESSAGE);
    expect(state.exportSizeBytes).toBeNull();
    expect(state.exportStatus).toBe("idle");
    expect(state.errorMessage).toBeNull();
  });

  it("clears the previous size and the previous export error at the start of a new export — DoD-8", async () => {
    const pending = deferred<{ filename: string; size: number }>();
    apiDownloadMock.mockReturnValue(pending.promise);
    const state = withStaleExport();

    const running = exportDatabase(state);
    await settle();

    expect(state.exportSizeBytes).toBeNull();
    expect(state.exportErrorMessage).toBeNull();
    expect(state.exportStatus).toBe("exporting");

    pending.resolve({ filename: FILENAME, size: 1024 });
    await running;

    expect(state.exportSizeBytes).toBe(1024);
    expect(state.exportErrorMessage).toBeNull();
    expect(state.exportStatus).toBe("idle");
  });

  it("clears a previous size when the new export fails, so only the error remains — DoD-8", async () => {
    apiDownloadMock.mockRejectedValue(failure());
    const state = withStaleExport();

    await exportDatabase(state);

    expect(state.exportSizeBytes).toBeNull();
    expect(state.exportErrorMessage).toBe(FAILURE_MESSAGE);
  });

  it("writes nothing when its signal is already aborted — DoD-8", async () => {
    apiDownloadMock.mockResolvedValue({ filename: FILENAME, size: 2048 });
    const state = withStaleExport();
    const controller = new AbortController();
    controller.abort();

    await exportDatabase(state, controller.signal);
    await settle();

    expect(state.exportSizeBytes).toBe(STALE_SIZE);
    expect(state.exportErrorMessage).toBe(STALE_ERROR);
    expect(state.exportStatus).toBe("idle");
  });
});

// ---------------------------------------------------------------- the formatter

describe("formatByteSize", () => {
  it.each([
    [0, "0 B"],
    [1, "1 B"],
    [512, "512 B"],
    [1023, "1023 B"],
  ])("renders %i in whole bytes — DoD-9", (bytes, expected) => {
    expect(formatByteSize(bytes)).toBe(expected);
  });

  it.each([
    [1024, "1.0 KB"],
    [1536, "1.5 KB"],
    [12595, "12.3 KB"],
    [1048000, "1023.4 KB"],
  ])("renders %i in KB with one decimal — DoD-9", (bytes, expected) => {
    expect(formatByteSize(bytes)).toBe(expected);
  });

  it.each([
    [1048576, "1.0 MB"],
    [4194304, "4.0 MB"],
    [13107200, "12.5 MB"],
    [1073741824, "1024.0 MB"],
  ])("renders %i in MB with one decimal — DoD-9", (bytes, expected) => {
    expect(formatByteSize(bytes)).toBe(expected);
  });
});

// ---------------------------------------------------------------- the data contract

describe("DatabasePageState stays a pure data contract", () => {
  const NEW_FIELDS = ["exportStatus", "exportSizeBytes", "exportErrorMessage"];

  it("the class prototype carries only the constructor — DoD-10", () => {
    expect(Object.getOwnPropertyNames(DatabasePageState.prototype)).toEqual(["constructor"]);
  });

  it("each export field is an observable field, never a method and never computed — DoD-10", () => {
    const state = new DatabasePageState();
    const record = state as unknown as Record<string, unknown>;
    const own = Object.getOwnPropertyNames(state);

    for (const name of NEW_FIELDS) {
      expect(own, `own property ${name}`).toContain(name);
      expect(isObservableProp(state, name), `observable ${name}`).toBe(true);
      expect(isComputedProp(state, name), `computed ${name}`).toBe(false);
      expect(typeof record[name], `type of ${name}`).not.toBe("function");
    }
  });

  it("a fresh store is idle, with no export size and no export error — DoD-10", () => {
    const state = new DatabasePageState();
    const statuses: DatabaseExportStatus[] = ["idle", "exporting"];

    expect(state.exportStatus).toBe("idle");
    expect(statuses).toContain(state.exportStatus);
    expect(state.exportSizeBytes).toBeNull();
    expect(state.exportErrorMessage).toBeNull();
  });
});
