// Feature 031 — import-and-id-remapping, step 008: the admin Database page's store half — the
// three import fields and the three free functions `chooseImportFile`, `cancelImport` and
// `importDatabase` (DoD-2..DoD-6, DoD-8, DoD-9). The page half lives in
// `DatabasePage.import.test.tsx`. DoD-1, DoD-7 and DoD-10 are page-level and live there.
// DoD-11 and DoD-12 are [manual/live] and carry no test.
//
// Expected behaviour comes from `008.admin-database-import.md` (Interface intent + Definition of
// done), `008.context.md` (the pinned confirm text, the unreadable-file message, "Why the admin
// page uses no notification") and the feature `context.md` ("Frontend shared facts", "Wire
// contract": the admin import answers 204 and the session cookie is cleared, so the browser goes
// to `/login`). Bindings come from the frozen `### Step 008` and `### Step 006` records:
// - `DatabasePageState` gains `importFile: ReadableTextFile | null`,
//   `importStatus: DatabaseImportStatus` (`"idle" | "importing"`) and
//   `importErrorMessage: string | null`, and no method;
// - `chooseImportFile(state, file)`, `cancelImport(state)` and
//   `importDatabase(state, signal?)` are free functions in `src/admin/databasePageState`;
// - `importDatabase` posts with step 006's `postExportFile(path, file, signal?)` and navigates
//   through `documentNavigation.assign` (exported from `src/shared/api`, decision 16).
//
// `postExportFile` is replaced at module level so the effect's contract is observable without a
// network call (030's `databasePageExport.test.ts` does the same with `apiDownload`); every other
// export of `shared/importFile` is passed through untouched. `documentNavigation.assign` is
// spied, never allowed to navigate. The file doubles are real `File` objects: a `File` is a class
// instance, so MobX stores it unconverted and identity comparisons hold.
import { isComputedProp, isObservableProp, runInAction } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cancelImport,
  chooseImportFile,
  type DatabaseImportStatus,
  DatabasePageState,
  importDatabase,
} from "../../src/admin/databasePageState";
import { documentNavigation } from "../../src/shared/api";
import { ApiError } from "../../src/shared/apiError";

const { postExportFileMock } = vi.hoisted(() => ({ postExportFileMock: vi.fn() }));
vi.mock("../../src/shared/importFile", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../src/shared/importFile")>();
  return { ...actual, postExportFile: postExportFileMock };
});

/** context.md "Wire contract" — the admin whole-database import route. */
const IMPORT_PATH = "/api/admin/database/import";
/** context.md "Wire contract" — a 204 clears the cookie, so the browser goes here. */
const LOGIN_PATH = "/login";

/** What a 409 `database_not_empty` carries; the page must show the server's own message. */
const NOT_EMPTY_MESSAGE =
  "The database can only be replaced while it holds no account other than a single administrator.";
/** What a 400 `export_invalid` carries. */
const EXPORT_INVALID_MESSAGE = "That file is not an export of this application (zq-19 marker).";
/** context.md "Frontend shared facts" — the unreadable-file message, verbatim. */
const UNREADABLE_MESSAGE = "The chosen file is not a readable export.";

/** Leftovers from an earlier attempt, so "clears the previous import error" is observable. */
const STALE_IMPORT_ERROR = "A previous import failed (stale qz-71 marker).";
/** The other two message slots, seeded so "no failure overwrites another's" is observable. */
const DRIFT_ERROR = "The drift report is on fire (zq-33 marker).";
const EXPORT_ERROR = "The export could not be produced (zq-44 marker).";
const EXPORT_SIZE_BYTES = 2048;

const ENVELOPE = {
  format: "rphelper-export",
  version: 1,
  granularity: "database",
  created_at: "2026-01-05T10:11:12Z",
  schema_version: 1,
  payload: {},
};

beforeEach(() => {
  postExportFileMock.mockReset();
  postExportFileMock.mockResolvedValue(undefined);
  vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- helpers

function exportFile(): File {
  return new File([JSON.stringify(ENVELOPE)], "transfer.json", { type: "application/json" });
}

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

/** A store that already holds a chosen file — the state the confirm's onConfirm runs from. */
function withChosenFile(file: File): DatabasePageState {
  const state = new DatabasePageState();
  runInAction(() => {
    state.importFile = file;
  });
  return state;
}

/** A page already carrying a drift error, an export error and an export size line. */
function withOtherMessages(state: DatabasePageState): DatabasePageState {
  runInAction(() => {
    state.errorMessage = DRIFT_ERROR;
    state.exportErrorMessage = EXPORT_ERROR;
    state.exportSizeBytes = EXPORT_SIZE_BYTES;
  });
  return state;
}

function assignCalls(): unknown[][] {
  const spy = documentNavigation.assign as unknown as { mock: { calls: unknown[][] } };
  return spy.mock.calls;
}

// ---------------------------------------------------------------- the route

describe("importDatabase posts the chosen file to the admin import route", () => {
  it("posts the chosen file to the admin database import route — DoD-4", async () => {
    const file = exportFile();
    const state = withChosenFile(file);

    await importDatabase(state);

    expect(postExportFileMock).toHaveBeenCalledTimes(1);
    expect(postExportFileMock.mock.calls[0][0]).toBe(IMPORT_PATH);
    expect(postExportFileMock.mock.calls[0][1]).toBe(file);
  });

  it("passes the signal it is given straight through to the post — DoD-4", async () => {
    const state = withChosenFile(exportFile());
    const controller = new AbortController();

    await importDatabase(state, controller.signal);

    expect(postExportFileMock.mock.calls[0][2]).toBe(controller.signal);
  });

  it("is importing while the post is in flight — DoD-4", async () => {
    const pending = deferred<undefined>();
    postExportFileMock.mockReturnValue(pending.promise);
    const state = withChosenFile(exportFile());

    const running = importDatabase(state);
    await settle();

    expect(state.importStatus).toBe("importing");

    pending.resolve(undefined);
    await running;
  });

  it("sends the browser to the sign-in page exactly once on success — DoD-4", async () => {
    const state = withChosenFile(exportFile());

    await importDatabase(state);

    expect(assignCalls()).toHaveLength(1);
    expect(assignCalls()[0][0]).toBe(LOGIN_PATH);
  });
});

// ---------------------------------------------------------------- failures

describe("a failed import writes its own message and nothing else", () => {
  it("stores a 409 refusal's own message, clears the file, returns to idle and does not navigate — DoD-5", async () => {
    postExportFileMock.mockRejectedValue(new ApiError("database_not_empty", NOT_EMPTY_MESSAGE, 409));
    const state = withChosenFile(exportFile());

    await importDatabase(state);

    expect(state.importErrorMessage).toBe(NOT_EMPTY_MESSAGE);
    expect(state.importFile).toBeNull();
    expect(state.importStatus).toBe("idle");
    expect(assignCalls()).toEqual([]);
  });

  it("leaves the drift error, the export error and the export size exactly as they were — DoD-5", async () => {
    postExportFileMock.mockRejectedValue(new ApiError("database_not_empty", NOT_EMPTY_MESSAGE, 409));
    const state = withOtherMessages(withChosenFile(exportFile()));

    await importDatabase(state);

    // The import's own slot took the message, so no other slot was touched.
    expect(state.importErrorMessage).toBe(NOT_EMPTY_MESSAGE);
    expect(state.errorMessage).toBe(DRIFT_ERROR);
    expect(state.exportErrorMessage).toBe(EXPORT_ERROR);
    expect(state.exportSizeBytes).toBe(EXPORT_SIZE_BYTES);
  });

  it("stores a 400 export_invalid refusal's own message and does not navigate — DoD-6", async () => {
    postExportFileMock.mockRejectedValue(new ApiError("export_invalid", EXPORT_INVALID_MESSAGE, 400));
    const state = withChosenFile(exportFile());

    await importDatabase(state);

    expect(state.importErrorMessage).toBe(EXPORT_INVALID_MESSAGE);
    expect(state.importFile).toBeNull();
    expect(state.importStatus).toBe("idle");
    expect(assignCalls()).toEqual([]);
  });

  it("stores the unreadable-file message unchanged when the file cannot be read — DoD-6", async () => {
    postExportFileMock.mockRejectedValue(
      new ApiError("client_unreadable_file", UNREADABLE_MESSAGE, 0),
    );
    const state = withChosenFile(exportFile());

    await importDatabase(state);

    expect(state.importErrorMessage).toBe(UNREADABLE_MESSAGE);
    expect(state.importFile).toBeNull();
    expect(state.importStatus).toBe("idle");
    expect(assignCalls()).toEqual([]);
  });
});

// ---------------------------------------------------------------- aborts

describe("an aborted import writes nothing", () => {
  it("writes nothing, posts nothing and does not navigate when its signal is already aborted — DoD-8", async () => {
    const file = exportFile();
    const state = withChosenFile(file);
    runInAction(() => {
      state.importErrorMessage = STALE_IMPORT_ERROR;
    });
    const controller = new AbortController();
    controller.abort();

    await importDatabase(state, controller.signal);
    await settle();

    expect(state.importFile).toBe(file);
    expect(state.importErrorMessage).toBe(STALE_IMPORT_ERROR);
    expect(state.importStatus).toBe("idle");
    // The first step of the effect is a write, so an effect that writes nothing never got
    // as far as the post or the navigation either.
    expect(postExportFileMock).not.toHaveBeenCalled();
    expect(assignCalls()).toEqual([]);
  });
});

// ---------------------------------------------------------------- choosing and cancelling

describe("choosing and cancelling a file only move the file", () => {
  it("chooseImportFile stores the file and clears a previous import error — DoD-8", () => {
    const file = exportFile();
    const state = new DatabasePageState();
    runInAction(() => {
      state.importErrorMessage = STALE_IMPORT_ERROR;
    });

    chooseImportFile(state, file);

    expect(state.importFile).toBe(file);
    expect(state.importErrorMessage).toBeNull();
    expect(state.importStatus).toBe("idle");
  });

  it("chooseImportFile sends nothing and navigates nowhere — DoD-2", async () => {
    const file = exportFile();
    const state = new DatabasePageState();

    chooseImportFile(state, file);
    await settle();

    // The file really was chosen — which is what opens the confirm — and still nothing was sent.
    expect(state.importFile).toBe(file);
    expect(postExportFileMock).not.toHaveBeenCalled();
    expect(assignCalls()).toEqual([]);
  });

  it("cancelImport clears the chosen file and touches nothing else — DoD-3", async () => {
    const state = withOtherMessages(withChosenFile(exportFile()));
    runInAction(() => {
      state.importErrorMessage = STALE_IMPORT_ERROR;
      state.status = "ready";
    });

    cancelImport(state);
    await settle();

    expect(state.importFile).toBeNull();
    expect(state.importErrorMessage).toBe(STALE_IMPORT_ERROR);
    expect(state.importStatus).toBe("idle");
    expect(state.errorMessage).toBe(DRIFT_ERROR);
    expect(state.exportErrorMessage).toBe(EXPORT_ERROR);
    expect(state.exportSizeBytes).toBe(EXPORT_SIZE_BYTES);
    expect(state.status).toBe("ready");
    expect(postExportFileMock).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------- the data contract

describe("DatabasePageState stays a pure data contract", () => {
  const NEW_FIELDS = ["importFile", "importStatus", "importErrorMessage"];

  it("the class prototype carries only the constructor — DoD-9", () => {
    expect(Object.getOwnPropertyNames(DatabasePageState.prototype)).toEqual(["constructor"]);
  });

  it("each import field is an observable field, never a method and never computed — DoD-9", () => {
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

  it("a fresh store has no chosen file, is idle and has no import error — DoD-9", () => {
    const state = new DatabasePageState();
    const statuses: DatabaseImportStatus[] = ["idle", "importing"];

    expect(state.importFile).toBeNull();
    expect(state.importStatus).toBe("idle");
    expect(statuses).toContain(state.importStatus);
    expect(state.importErrorMessage).toBeNull();
  });
});
