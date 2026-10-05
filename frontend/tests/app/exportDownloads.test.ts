// Feature 030 — export-granularities, step 006: the `app` entry's export module — the three
// path builders and the shared `runExport` effect (DoD-1, DoD-2). The three controls live in
// `UserMenu.export.test.tsx`, `CharacterScreen.export.test.tsx` and
// `SessionsSection.export.test.tsx`; DoD-9 and DoD-10 are [manual/live] and carry no test.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 006.context.md and the feature context.md (ids are strings and are never parsed; success is
// silent because the browser's download is the signal; `app`-entry failures go through
// `notifyFailure`). Bindings come from the frozen `### Step 006` record:
// `ownDataExportPath()`, `characterExportPath(characterId)`, `sessionExportPath(sessionId)` and
// `runExport(path)`, all from `src/app/exportDownloads`.
//
// Harness conventions:
// - `apiDownload` is replaced at module level (every other `shared/api` export passed through),
//   so `runExport`'s contract is observable with no network call and no jsdom download dance —
//   the step 005 precedent (`tests/admin/databasePageExport.test.ts`).
// - `notifyFailure` is replaced by a mock module, so "exactly once, with that value" and "not at
//   all" are both directly observable (the repo's `vi.hoisted` + `vi.mock` idiom).
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  characterExportPath,
  ownDataExportPath,
  runExport,
  sessionExportPath,
} from "../../src/app/exportDownloads";
import { ApiError } from "../../src/shared/apiError";

const { apiDownloadMock, notifyFailureSpy } = vi.hoisted(() => ({
  apiDownloadMock: vi.fn(),
  notifyFailureSpy: vi.fn(),
}));
vi.mock("../../src/shared/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../src/shared/api")>();
  return { ...actual, apiDownload: apiDownloadMock };
});
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

// ---------------------------------------------------------------- the spec's paths
const OWN_DATA_PATH = "/api/export";

/**
 * Ids are decimal strings, never numbers (context.md "Ids are strings"). The 19-digit values are
 * past `Number.MAX_SAFE_INTEGER` (2^53 - 1 = 9007199254740991) — DoD-1's point: a builder that
 * parsed or re-formatted its argument would change them.
 */
const IDS: string[] = [
  "1",
  "9007199254740993", // 2^53 + 1
  "7250000000000000011", // 19 digits
  "9999999999999999999", // 19 nines
];

const FILENAME = "rphelper-user-20260105T101112Z.json";
const FAILURE_MESSAGE = "That character does not exist (zq-404 marker).";

beforeEach(() => {
  apiDownloadMock.mockReset();
  notifyFailureSpy.mockReset();
});

// ---------------------------------------------------------------- helpers
function apiError(): ApiError {
  return new ApiError("character_not_found", FAILURE_MESSAGE, 404);
}

/** The canonical abort error an `AbortController` produces. */
function domExceptionAbort(): unknown {
  return new DOMException("The operation was aborted.", "AbortError");
}

/** An `Error` whose `name` is `AbortError` — the other shape an abort arrives in. */
function namedAbort(): unknown {
  const error = new Error("The operation was aborted.");
  error.name = "AbortError";
  return error;
}

const ABORTS: Array<[string, () => unknown]> = [
  ["a DOMException abort", domExceptionAbort],
  ["an Error named AbortError", namedAbort],
];

// ===========================================================================
describe("the three path builders (DoD-1)", () => {
  it("the own-data path is exactly /api/export and takes no input — DoD-1", () => {
    expect(ownDataExportPath()).toBe(OWN_DATA_PATH);
    expect(ownDataExportPath.length).toBe(0);
  });

  it.each(IDS)("the character path is /api/characters/%s/export — DoD-1", (id) => {
    expect(characterExportPath(id)).toBe(`/api/characters/${id}/export`);
  });

  it.each(IDS)("the session path is /api/sessions/%s/export — DoD-1", (id) => {
    expect(sessionExportPath(id)).toBe(`/api/sessions/${id}/export`);
  });

  it.each(IDS)("the id %s survives verbatim in both builders — DoD-1", (id) => {
    const fromCharacter = /^\/api\/characters\/(.+)\/export$/.exec(characterExportPath(id));
    const fromSession = /^\/api\/sessions\/(.+)\/export$/.exec(sessionExportPath(id));
    expect(fromCharacter).not.toBeNull();
    expect(fromSession).not.toBeNull();
    expect((fromCharacter as RegExpExecArray)[1]).toBe(id);
    expect((fromSession as RegExpExecArray)[1]).toBe(id);
  });

  it("a 19-digit id past Number.MAX_SAFE_INTEGER is not rounded — DoD-1", () => {
    const id = "7250000000000000011";
    // The proof the clause is about: going through Number would land on ...0000 here.
    expect(String(Number(id))).not.toBe(id);
    expect(characterExportPath(id)).toBe("/api/characters/7250000000000000011/export");
    expect(sessionExportPath(id)).toBe("/api/sessions/7250000000000000011/export");
  });

  it("the three builders answer three different routes — DoD-1", () => {
    const id = "9007199254740993";
    const paths = [ownDataExportPath(), characterExportPath(id), sessionExportPath(id)];
    expect(new Set(paths).size).toBe(3);
  });
});

// ===========================================================================
describe("runExport downloads the path it is given (DoD-2)", () => {
  it("awaits the download of exactly that path, once — DoD-2", async () => {
    apiDownloadMock.mockResolvedValue({ filename: FILENAME, size: 2048 });

    await runExport(OWN_DATA_PATH);

    expect(apiDownloadMock).toHaveBeenCalledTimes(1);
    expect(apiDownloadMock.mock.calls[0][0]).toBe(OWN_DATA_PATH);
  });
});

// ===========================================================================
describe("runExport is silent on success (DoD-2)", () => {
  it("calls notifyFailure nowhere and resolves with nothing — DoD-2", async () => {
    apiDownloadMock.mockResolvedValue({ filename: FILENAME, size: 2048 });

    await expect(runExport(OWN_DATA_PATH)).resolves.toBeUndefined();

    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ===========================================================================
describe("runExport routes a failure to notifyFailure, once (DoD-2)", () => {
  it("calls notifyFailure exactly once with the thrown ApiError — DoD-2", async () => {
    const thrown = apiError();
    apiDownloadMock.mockRejectedValue(thrown);

    await runExport(characterExportPath("7250000000000000011"));

    expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
    expect(notifyFailureSpy.mock.calls[0][0]).toBe(thrown);
  });

  it("the value it notifies carries the error's own message — DoD-2", async () => {
    apiDownloadMock.mockRejectedValue(apiError());

    await runExport(OWN_DATA_PATH);

    const notified = notifyFailureSpy.mock.calls[0][0];
    expect(notified).toBeInstanceOf(ApiError);
    expect((notified as ApiError).message).toBe(FAILURE_MESSAGE);
  });

  it("never rethrows: a failed download resolves — DoD-2", async () => {
    apiDownloadMock.mockRejectedValue(apiError());

    await expect(runExport(OWN_DATA_PATH)).resolves.toBeUndefined();
  });

  it("a non-ApiError thrown value is notified too, once — DoD-2", async () => {
    const thrown = new Error("something else went wrong (zq-500 marker)");
    apiDownloadMock.mockRejectedValue(thrown);

    await expect(runExport(OWN_DATA_PATH)).resolves.toBeUndefined();

    expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
    expect(notifyFailureSpy.mock.calls[0][0]).toBe(thrown);
  });
});

// ===========================================================================
describe("runExport says nothing about an abort (DoD-2)", () => {
  it.each(ABORTS)("%s notifies nothing and still resolves — DoD-2", async (_name, make) => {
    apiDownloadMock.mockRejectedValue(make());

    await expect(runExport(sessionExportPath("7250000000000000101"))).resolves.toBeUndefined();

    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});
