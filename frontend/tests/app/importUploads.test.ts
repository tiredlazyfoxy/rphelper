// Feature 031 — import-and-id-remapping, step 006: the `app` entry's two import effects
// (`src/app/importUploads.ts`) — DoD-5, DoD-6, DoD-7, DoD-8, DoD-9, DoD-10.
// DoD-1..DoD-4 live in `tests/shared/importFile.test.ts`; DoD-11 is [manual/live] and carries no test.
//
// Expected values come from the spec alone:
// - `006.import-client.md` §"Interface intent" and its Definition of done;
// - `006.context.md` — the pinned coverage sentence, raised once per successful import and never on
//   failure, and the success order: the section-or-characters reload, then `loadSessions`, then the
//   warning, run sequentially so the request order is deterministic;
// - `context.md` §"Frontend shared facts" — reload scope per granularity, the unreadable-file
//   `ApiError` (code `client_unreadable_file`, status 0, pinned message), ids are strings end to end,
//   a failed import reloads nothing, and no success toast;
// - `context.md` §"Wire contract" — `POST /api/import` → `{granularity, character_ids}` and
//   `POST /api/characters/{character_id}/import` → `{session_id}`; a foreign or missing target
//   answers `character_not_found` (404); a bad payload answers `export_invalid` (400);
// - `context.md` §"Error routing" (via `006.context.md`) — `notifyFailure` unless aborted, never rethrow.
//
// Bindings come from `status.md` → `## Skeleton` → `### Step 006 — frozen interface`:
// `ownedImportPath()`, `sessionImportPath(characterId)`,
// `runOwnedImport(file, charactersState, sessionsState, navigate, signal?)`,
// `runSessionImport(characterId, file, sessionsState, reloadSection, signal?)`, and the
// `NavigateTo` / `ReloadSection` / `OwnedImportResponse` / `SessionImportResponse` types.
// The three list-reload URL paths are the ones that record records: `loadCharacters` →
// `GET /api/characters` (no query while `showArchived` is false) and `loadSessions` →
// `GET /api/sessions`, never with a query. Neither reload ever rejects.
//
// Observation choices (harvest D.5):
// - `shared/notifyFailure` is replaced by a mock module, so "exactly once, with that ApiError" and
//   "not at all" are both directly observable (the `tests/app/exportDownloads.test.ts` idiom);
// - `notifyWarning` is left REAL and `@mantine/notifications`' `show` is spied instead (the
//   `tests/shared/notifyWarning.test.ts` idiom), so the warning is observed as the pinned sentence
//   itself rather than as an identifier. With `notifyFailure` mocked away, every `show` call is a warning;
// - `fetch` is stubbed with `vi.fn<FetchFn>` + `vi.stubGlobal`, keyed on method + pathname, appending
//   every request to one ordered log so the success order is asserted as a sequence. An unmatched
//   request rejects loudly;
// - `documentNavigation.assign` is spied, because it is the only navigation seam `runSessionImport`
//   could reach (a 401 inside `apiPost`), and DoD-8 requires that no navigation happens.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CharactersState } from "../../src/app/charactersState";
import {
  ownedImportPath,
  runOwnedImport,
  runSessionImport,
  sessionImportPath,
  type NavigateTo,
  type OwnedImportResponse,
  type ReloadSection,
  type SessionImportResponse,
} from "../../src/app/importUploads";
import { SessionsState } from "../../src/app/sessionsState";
import { documentNavigation } from "../../src/shared/api";
import { ApiError, isApiError } from "../../src/shared/apiError";
import type { ReadableTextFile } from "../../src/shared/importFile";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- mocks
const { notifyFailureSpy, showSpy } = vi.hoisted(() => ({
  notifyFailureSpy: vi.fn(),
  showSpy: vi.fn<(data: unknown) => string>(() => "notification-id"),
}));

vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));
vi.mock("@mantine/notifications", async (importOriginal) => {
  const original = await importOriginal<typeof import("@mantine/notifications")>();
  return { ...original, notifications: { ...original.notifications, show: showSpy } };
});

// ---------------------------------------------------------------- the spec's pinned values
/** `006.context.md`, verbatim — including the apostrophe in "won't" and the final full stop. */
const COVERAGE_SENTENCE =
  "Imported material won't appear in semantic search until an administrator rebuilds the search index.";

const OWNED_PATH = "/api/import";
const CHARACTERS_LIST = "GET /api/characters";
const SESSIONS_LIST = "GET /api/sessions";

/** Ids are decimal strings, never numbers; all 19 digits, past `Number.MAX_SAFE_INTEGER`. */
const TARGET_ID = "7250000000000000011";
const IMPORTED_CHARACTER_ID = "7250000000000000021";
const SECOND_CHARACTER_ID = "7250000000000000022";
const IMPORTED_SESSION_ID = "7250000000000000031";

const SESSION_PATH = `/api/characters/${TARGET_ID}/import`;
const OWNED_POST = `POST ${OWNED_PATH}`;
const SESSION_POST = `POST ${SESSION_PATH}`;

const EXPORT_INVALID_MESSAGE = "That file is not something this instance can import (zq-400 marker).";
const CHARACTER_NOT_FOUND_MESSAGE = "That character does not exist (zq-404 marker).";
/** `context.md` §"Frontend shared facts", verbatim. */
const UNREADABLE_MESSAGE = "The chosen file is not a readable export.";
const UNREADABLE_CODE = "client_unreadable_file";

const CHARACTER_RESULT: OwnedImportResponse = {
  granularity: "character",
  character_ids: [IMPORTED_CHARACTER_ID],
};
const USER_RESULT: OwnedImportResponse = {
  granularity: "user",
  character_ids: [IMPORTED_CHARACTER_ID, SECOND_CHARACTER_ID],
};
const SESSION_RESULT: SessionImportResponse = { session_id: IMPORTED_SESSION_ID };

const ENVELOPE = {
  format: "rphelper-export",
  version: 1,
  granularity: "character",
  created_at: "2026-10-05T10:11:12.000000+00:00",
  schema_version: 1,
  payload: { characters: [{ id: "4242", name: "Alma Vist" }], memos: [] },
};

// ---------------------------------------------------------------- per-test state
let calls: string[] = [];

beforeEach(() => {
  calls = [];
  notifyFailureSpy.mockReset();
  showSpy.mockClear();
  vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- helpers
function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function errorResponse(code: string, message: string, status: number): Response {
  return jsonResponse({ error: { code, message, detail: {} } }, status);
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

type Handler = () => Promise<Response>;

/** The two list reloads, answered with empty lists. */
function reloadHandlers(): Record<string, Handler> {
  return {
    [CHARACTERS_LIST]: () => Promise.resolve(jsonResponse({ characters: [] }, 200)),
    [SESSIONS_LIST]: () => Promise.resolve(jsonResponse({ sessions: [] }, 200)),
  };
}

/**
 * Stubs `fetch`, logging every request as "<METHOD> <pathname>" into the shared ordered log.
 * An unmatched request rejects, so a stray call is loud rather than silently absorbed.
 */
function stubRoutes(handlers: Record<string, Handler>) {
  const mock = vi.fn<FetchFn>((input, init) => {
    const key = `${requestMethod(input, init)} ${requestUrl(input).pathname}`;
    calls.push(key);
    const handler = handlers[key];
    if (handler === undefined) return Promise.reject(new Error(`unexpected fetch of ${key}`));
    return handler();
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

function textFile(value: unknown): ReadableTextFile {
  return { text: () => Promise.resolve(JSON.stringify(value)) };
}

function unparsableFile(): ReadableTextFile {
  return { text: () => Promise.resolve("not json") };
}

function realEnvelopeFile(): ReadableTextFile {
  return new File([JSON.stringify(ENVELOPE)], "rphelper-export.json", { type: "application/json" });
}

async function flush(rounds = 4): Promise<void> {
  for (let index = 0; index < rounds; index += 1) {
    await new Promise<void>((resolve) => setImmediate(resolve));
  }
}

/** Every message Mantine was asked to show. With `notifyFailure` mocked out, these are the warnings. */
function warnings(): unknown[] {
  return showSpy.mock.calls.map(([data]) => (data as Record<string, unknown>).message);
}

function warningColours(): unknown[] {
  return showSpy.mock.calls.map(([data]) => (data as Record<string, unknown>).color);
}

function onlyFailure(): ApiError {
  expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
  const [error] = notifyFailureSpy.mock.calls[0] ?? [];
  expect(isApiError(error)).toBe(true);
  return error as ApiError;
}

// ===========================================================================
describe("the two path builders (DoD-5)", () => {
  it("the owned-import path is exactly /api/import and takes no input — DoD-5", () => {
    expect(ownedImportPath()).toBe(OWNED_PATH);
    expect(ownedImportPath.length).toBe(0);
  });

  it.each([TARGET_ID, IMPORTED_CHARACTER_ID, "1", "9007199254740993"])(
    "the session-import path for %s is /api/characters/<id>/import — DoD-5",
    (id) => {
      expect(sessionImportPath(id)).toBe(`/api/characters/${id}/import`);
    },
  );

  it("a 19-digit id is inserted verbatim, never parsed or rounded — DoD-5", () => {
    // The proof the clause is about: going through Number would land elsewhere.
    expect(String(Number(TARGET_ID))).not.toBe(TARGET_ID);

    const path = sessionImportPath(TARGET_ID);

    expect(path).toBe("/api/characters/7250000000000000011/import");
    const captured = /^\/api\/characters\/(.+)\/import$/.exec(path);
    expect(captured).not.toBeNull();
    expect((captured as RegExpExecArray)[1]).toBe(TARGET_ID);
  });

  it("the two builders answer two different routes — DoD-5", () => {
    expect(new Set([ownedImportPath(), sessionImportPath(TARGET_ID)]).size).toBe(2);
  });
});

// ===========================================================================
describe("runOwnedImport — a character result (DoD-6, US-080.AC-2)", () => {
  function serve() {
    return stubRoutes({
      ...reloadHandlers(),
      [OWNED_POST]: () => Promise.resolve(jsonResponse(CHARACTER_RESULT, 200)),
    });
  }

  it("posts, then reloads the characters list, then the sessions list — DoD-6", async () => {
    serve();
    const charactersState = new CharactersState();
    const sessionsState = new SessionsState();
    const navigate = vi.fn<NavigateTo>();

    await expect(
      runOwnedImport(realEnvelopeFile(), charactersState, sessionsState, navigate),
    ).resolves.toBeUndefined();

    expect(calls).toEqual([OWNED_POST, CHARACTERS_LIST, SESSIONS_LIST]);
    expect(charactersState.status).toBe("ready");
    expect(sessionsState.status).toBe("ready");
  });

  it("navigates to /characters/<the returned id> — DoD-6", async () => {
    serve();
    const navigate = vi.fn<NavigateTo>();

    await expect(
      runOwnedImport(textFile(ENVELOPE), new CharactersState(), new SessionsState(), navigate),
    ).resolves.toBeUndefined();

    expect(calls).toContain(OWNED_POST);
    expect(navigate).toHaveBeenCalledTimes(1);
    expect(navigate).toHaveBeenCalledWith(`/characters/${IMPORTED_CHARACTER_ID}`);
  });

  it("raises exactly one warning, the pinned coverage sentence — DoD-6", async () => {
    serve();

    await expect(
      runOwnedImport(textFile(ENVELOPE), new CharactersState(), new SessionsState(), vi.fn<NavigateTo>()),
    ).resolves.toBeUndefined();

    expect(calls).toContain(OWNED_POST);
    expect(warnings()).toEqual([COVERAGE_SENTENCE]);
    expect(warningColours()).toEqual(["yellow"]);
  });

  it("raises no failure notification — DoD-6", async () => {
    serve();

    await expect(
      runOwnedImport(textFile(ENVELOPE), new CharactersState(), new SessionsState(), vi.fn<NavigateTo>()),
    ).resolves.toBeUndefined();

    expect(calls).toEqual([OWNED_POST, CHARACTERS_LIST, SESSIONS_LIST]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ===========================================================================
describe("runOwnedImport — a user result (DoD-7, US-079.AC-2)", () => {
  function serve() {
    return stubRoutes({
      ...reloadHandlers(),
      [OWNED_POST]: () => Promise.resolve(jsonResponse(USER_RESULT, 200)),
    });
  }

  it("reloads the characters list and then the sessions list — DoD-7", async () => {
    serve();
    const charactersState = new CharactersState();
    const sessionsState = new SessionsState();

    await expect(
      runOwnedImport(textFile(ENVELOPE), charactersState, sessionsState, vi.fn<NavigateTo>()),
    ).resolves.toBeUndefined();

    expect(calls).toEqual([OWNED_POST, CHARACTERS_LIST, SESSIONS_LIST]);
    expect(charactersState.status).toBe("ready");
    expect(sessionsState.status).toBe("ready");
  });

  it("does not navigate, even though the result carries character ids — DoD-7", async () => {
    serve();
    const navigate = vi.fn<NavigateTo>();

    await expect(
      runOwnedImport(textFile(ENVELOPE), new CharactersState(), new SessionsState(), navigate),
    ).resolves.toBeUndefined();

    // Positive anchor: the post and both reloads really happened.
    expect(calls).toEqual([OWNED_POST, CHARACTERS_LIST, SESSIONS_LIST]);
    expect(navigate).not.toHaveBeenCalled();
    expect(documentNavigation.assign).not.toHaveBeenCalled();
  });

  it("raises exactly one warning, the pinned coverage sentence — DoD-7", async () => {
    serve();

    await expect(
      runOwnedImport(textFile(ENVELOPE), new CharactersState(), new SessionsState(), vi.fn<NavigateTo>()),
    ).resolves.toBeUndefined();

    expect(calls).toContain(OWNED_POST);
    expect(warnings()).toEqual([COVERAGE_SENTENCE]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ===========================================================================
describe("runSessionImport — success (DoD-8, UC-064)", () => {
  function serve() {
    return stubRoutes({
      ...reloadHandlers(),
      [SESSION_POST]: () => Promise.resolve(jsonResponse(SESSION_RESULT, 200)),
    });
  }

  /** Logs into the shared order log and resolves only after several ticks, so "awaits" is observable. */
  function reloadSectionDouble() {
    return vi.fn<ReloadSection>(async () => {
      calls.push("reloadSection:start");
      await flush(3);
      calls.push("reloadSection:end");
    });
  }

  it("posts to /api/characters/<id>/import — DoD-8", async () => {
    serve();

    await expect(
      runSessionImport(TARGET_ID, textFile(ENVELOPE), new SessionsState(), reloadSectionDouble()),
    ).resolves.toBeUndefined();

    expect(calls[0]).toBe(SESSION_POST);
  });

  it("awaits reloadSection exactly once, then reloads the sessions list — DoD-8", async () => {
    serve();
    const sessionsState = new SessionsState();
    const reloadSection = reloadSectionDouble();

    await expect(
      runSessionImport(TARGET_ID, textFile(ENVELOPE), sessionsState, reloadSection),
    ).resolves.toBeUndefined();

    expect(reloadSection).toHaveBeenCalledTimes(1);
    // The section reload finishes before the sessions-list GET starts: it is awaited, not fired off.
    expect(calls).toEqual([SESSION_POST, "reloadSection:start", "reloadSection:end", SESSIONS_LIST]);
    expect(sessionsState.status).toBe("ready");
  });

  it("issues no characters-list GET — DoD-8", async () => {
    serve();

    await expect(
      runSessionImport(TARGET_ID, realEnvelopeFile(), new SessionsState(), reloadSectionDouble()),
    ).resolves.toBeUndefined();

    expect(calls).toContain(SESSION_POST);
    expect(calls).toContain(SESSIONS_LIST);
    expect(calls).not.toContain(CHARACTERS_LIST);
  });

  it("raises one warning and does not navigate — DoD-8", async () => {
    serve();

    await expect(
      runSessionImport(TARGET_ID, textFile(ENVELOPE), new SessionsState(), reloadSectionDouble()),
    ).resolves.toBeUndefined();

    expect(calls).toContain(SESSION_POST);
    expect(warnings()).toEqual([COVERAGE_SENTENCE]);
    expect(warningColours()).toEqual(["yellow"]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(documentNavigation.assign).not.toHaveBeenCalled();
  });
});

// ===========================================================================
describe("both effects — failure (DoD-9)", () => {
  it("runOwnedImport: a 400 export_invalid notifies once with that ApiError and nothing else — DoD-9", async () => {
    stubRoutes({
      ...reloadHandlers(),
      [OWNED_POST]: () =>
        Promise.resolve(errorResponse("export_invalid", EXPORT_INVALID_MESSAGE, 400)),
    });
    const navigate = vi.fn<NavigateTo>();

    await expect(
      runOwnedImport(textFile(ENVELOPE), new CharactersState(), new SessionsState(), navigate),
    ).resolves.toBeUndefined();

    // Positive anchor: the POST was made and answered.
    expect(calls).toEqual([OWNED_POST]);
    const error = onlyFailure();
    expect(error.code).toBe("export_invalid");
    expect(error.message).toBe(EXPORT_INVALID_MESSAGE);
    expect(error.status).toBe(400);
    expect(warnings()).toEqual([]);
    expect(navigate).not.toHaveBeenCalled();
  });

  it("runOwnedImport: an unreadable file notifies once with the pinned ApiError and sends nothing — DoD-9", async () => {
    stubRoutes(reloadHandlers());
    const navigate = vi.fn<NavigateTo>();

    await expect(
      runOwnedImport(unparsableFile(), new CharactersState(), new SessionsState(), navigate),
    ).resolves.toBeUndefined();

    // Positive anchor: the failure arrived, and it arrived before any request.
    const error = onlyFailure();
    expect(error.code).toBe(UNREADABLE_CODE);
    expect(error.message).toBe(UNREADABLE_MESSAGE);
    expect(error.status).toBe(0);
    expect(calls).toEqual([]);
    expect(warnings()).toEqual([]);
    expect(navigate).not.toHaveBeenCalled();
  });

  it("runSessionImport: a 404 character_not_found notifies once and reloads nothing — DoD-9", async () => {
    stubRoutes({
      ...reloadHandlers(),
      [SESSION_POST]: () =>
        Promise.resolve(errorResponse("character_not_found", CHARACTER_NOT_FOUND_MESSAGE, 404)),
    });
    const reloadSection = vi.fn<ReloadSection>(async () => {
      calls.push("reloadSection");
    });

    await expect(
      runSessionImport(TARGET_ID, textFile(ENVELOPE), new SessionsState(), reloadSection),
    ).resolves.toBeUndefined();

    expect(calls).toEqual([SESSION_POST]);
    const error = onlyFailure();
    expect(error.code).toBe("character_not_found");
    expect(error.message).toBe(CHARACTER_NOT_FOUND_MESSAGE);
    expect(error.status).toBe(404);
    expect(warnings()).toEqual([]);
    expect(reloadSection).not.toHaveBeenCalled();
    expect(documentNavigation.assign).not.toHaveBeenCalled();
  });

  it("runSessionImport: an unreadable file notifies once with the pinned ApiError and sends nothing — DoD-9", async () => {
    stubRoutes(reloadHandlers());
    const reloadSection = vi.fn<ReloadSection>(async () => {
      calls.push("reloadSection");
    });

    await expect(
      runSessionImport(TARGET_ID, unparsableFile(), new SessionsState(), reloadSection),
    ).resolves.toBeUndefined();

    const error = onlyFailure();
    expect(error.code).toBe(UNREADABLE_CODE);
    expect(error.message).toBe(UNREADABLE_MESSAGE);
    expect(error.status).toBe(0);
    expect(calls).toEqual([]);
    expect(warnings()).toEqual([]);
    expect(reloadSection).not.toHaveBeenCalled();
    expect(documentNavigation.assign).not.toHaveBeenCalled();
  });

  it("a failed owned import leaves both lists unloaded — DoD-9", async () => {
    stubRoutes({
      ...reloadHandlers(),
      [OWNED_POST]: () =>
        Promise.resolve(errorResponse("export_invalid", EXPORT_INVALID_MESSAGE, 400)),
    });
    const charactersState = new CharactersState();
    const sessionsState = new SessionsState();

    await expect(
      runOwnedImport(textFile(ENVELOPE), charactersState, sessionsState, vi.fn<NavigateTo>()),
    ).resolves.toBeUndefined();

    expect(calls).toEqual([OWNED_POST]);
    expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
    expect(charactersState.status).toBe("idle");
    expect(sessionsState.status).toBe("idle");
  });
});

// ===========================================================================
describe("both effects — an aborted signal (DoD-10)", () => {
  /**
   * The two shapes an abort arrives in (decision 17). Both abort the real `AbortController`, which is
   * what the browser does; the first rejects with the real `DOMException` named `AbortError` (which is
   * NOT an `instanceof Error` in jsdom), the second with a plain error whose name says nothing, so the
   * signal's own `aborted` state is the only tell.
   */
  const SHAPES: Array<[string, (controller: AbortController) => unknown]> = [
    [
      "a DOMException named AbortError from a real AbortController",
      (controller) => {
        controller.abort();
        return new DOMException("The operation was aborted.", "AbortError");
      },
    ],
    [
      "an aborted signal with an unnamed rejection",
      (controller) => {
        controller.abort();
        return new Error("the request was torn down");
      },
    ],
  ];

  it.each(SHAPES)(
    "runOwnedImport: %s — no notification, no warning, no reload, no navigation — DoD-10",
    async (_label, abort) => {
      const controller = new AbortController();
      stubRoutes({
        ...reloadHandlers(),
        [OWNED_POST]: () => Promise.reject(abort(controller)),
      });
      const charactersState = new CharactersState();
      const sessionsState = new SessionsState();
      const navigate = vi.fn<NavigateTo>();

      await expect(
        runOwnedImport(
          textFile(ENVELOPE),
          charactersState,
          sessionsState,
          navigate,
          controller.signal,
        ),
      ).resolves.toBeUndefined();

      // Positive anchor: the POST really was issued, and it was the only request.
      expect(calls).toEqual([OWNED_POST]);
      expect(notifyFailureSpy).not.toHaveBeenCalled();
      expect(warnings()).toEqual([]);
      expect(navigate).not.toHaveBeenCalled();
      expect(documentNavigation.assign).not.toHaveBeenCalled();
      expect(charactersState.status).toBe("idle");
      expect(sessionsState.status).toBe("idle");
    },
  );

  it.each(SHAPES)(
    "runSessionImport: %s — no notification, no warning, no section reload — DoD-10",
    async (_label, abort) => {
      const controller = new AbortController();
      stubRoutes({
        ...reloadHandlers(),
        [SESSION_POST]: () => Promise.reject(abort(controller)),
      });
      const sessionsState = new SessionsState();
      const reloadSection = vi.fn<ReloadSection>(async () => {
        calls.push("reloadSection");
      });

      await expect(
        runSessionImport(
          TARGET_ID,
          textFile(ENVELOPE),
          sessionsState,
          reloadSection,
          controller.signal,
        ),
      ).resolves.toBeUndefined();

      expect(calls).toEqual([SESSION_POST]);
      expect(notifyFailureSpy).not.toHaveBeenCalled();
      expect(warnings()).toEqual([]);
      expect(reloadSection).not.toHaveBeenCalled();
      expect(documentNavigation.assign).not.toHaveBeenCalled();
      expect(sessionsState.status).toBe("idle");
    },
  );
});
