// Feature 031 — import-and-id-remapping, step 006: the shared read-and-post helper
// (`src/shared/importFile.ts`) — DoD-1, DoD-2, DoD-3, DoD-4.
//
// Expected values come from the spec alone:
// - `006.import-client.md` §"Interface intent" and its Definition of done;
// - `context.md` §"Frontend shared facts" — the unreadable-file failure is an `ApiError` with code
//   `client_unreadable_file`, status `0` and the message "The chosen file is not a readable export.",
//   raised **before any request**;
// - `context.md` §"Transport" — the browser reads the file as text, `JSON.parse`s it and posts the
//   parsed object as the JSON body;
// - `context.md` §"The failure contract" — a 400 `export_invalid` envelope.
//
// Bindings come from `status.md` → `## Skeleton` → `### Step 006 — frozen interface`:
// `CLIENT_UNREADABLE_FILE`, `ReadableTextFile`, `readExportFile(file)` and
// `postExportFile<T = unknown>(path, file, signal?)`, all from `src/shared/importFile`.
// Per orchestrator decision 18 this module raises no notification at all — it throws, and each
// entry routes the error — so nothing here observes `notifyFailure` or Mantine notifications.
//
// Harness conventions (harvest D.5): `globals: false`, so every vitest helper is imported;
// `fetch` is stubbed with `vi.fn<FetchFn>` + `vi.stubGlobal` and torn down in `afterEach`; jsdom
// 30.1.1 implements `Blob.prototype.text()`, so a real `File` and a hand-rolled `{ text() }` are
// both exercised.
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, isApiError } from "../../src/shared/apiError";
import {
  CLIENT_UNREADABLE_FILE,
  postExportFile,
  readExportFile,
  type ReadableTextFile,
} from "../../src/shared/importFile";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- the spec's pinned values
/** `context.md` §"Frontend shared facts" — verbatim. */
const UNREADABLE_MESSAGE = "The chosen file is not a readable export.";
const UNREADABLE_CODE = "client_unreadable_file";

const OWNED_PATH = "/api/import";
/** A 19-digit id, past `Number.MAX_SAFE_INTEGER`; ids are strings end to end. */
const CHARACTER_ID = "7250000000000000011";
const SESSION_PATH = `/api/characters/${CHARACTER_ID}/import`;

const EXPORT_INVALID_MESSAGE = "That file is not something this instance can import (zq-400 marker).";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- helpers
function stubFetch(impl: FetchFn) {
  const mock = vi.fn<FetchFn>(impl);
  vi.stubGlobal("fetch", mock);
  return mock;
}

/** Any request at all is a defect for `readExportFile`, so make one loud. */
function forbiddenFetch() {
  return stubFetch((input) =>
    Promise.reject(new Error(`unexpected fetch of ${String(input)} (readExportFile sends nothing)`)),
  );
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function textFile(text: string): ReadableTextFile {
  return { text: () => Promise.resolve(text) };
}

function unreadableFile(): ReadableTextFile {
  return { text: () => Promise.reject(new Error("the file could not be read (zq-read marker)")) };
}

function realFile(text: string): ReadableTextFile {
  return new File([text], "rphelper-export.json", { type: "application/json" });
}

/** Resolves to whatever the promise rejected with; fails when it resolves instead. */
async function rejection(promise: Promise<unknown>): Promise<unknown> {
  try {
    await promise;
  } catch (error: unknown) {
    return error;
  }
  throw new Error("expected the promise to reject, but it resolved");
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function contentType(init?: RequestInit): string {
  return new Headers(init?.headers).get("content-type") ?? "";
}

function parsedBody(init?: RequestInit): unknown {
  const body = init?.body;
  expect(typeof body).toBe("string");
  return JSON.parse(body as string);
}

/** Asserts the pinned unreadable-file failure, whatever the cause. */
function expectUnreadable(error: unknown): void {
  expect(isApiError(error)).toBe(true);
  const apiError = error as ApiError;
  expect(apiError.code).toBe(UNREADABLE_CODE);
  expect(apiError.status).toBe(0);
  expect(apiError.message).toBe(UNREADABLE_MESSAGE);
}

// ===========================================================================
describe("readExportFile — a readable export (DoD-1)", () => {
  const OBJECTS: Array<[string, Record<string, unknown>]> = [
    ["an empty object", {}],
    ["a flat object", { granularity: "character" }],
    [
      "a whole envelope shape",
      {
        format: "rphelper-export",
        version: 1,
        granularity: "character",
        created_at: "2026-10-05T10:11:12.000000+00:00",
        schema_version: 1,
        payload: { characters: [{ id: CHARACTER_ID, name: "Alma Vist" }], memos: [] },
      },
    ],
  ];

  it.each(OBJECTS)("resolves to the parsed object for %s — DoD-1", async (_label, object) => {
    const fetchMock = forbiddenFetch();

    const parsed = await readExportFile(textFile(JSON.stringify(object)));

    expect(parsed).toEqual(object);
    expect(fetchMock).toHaveBeenCalledTimes(0);
  });

  it("resolves to the parsed object for a real File, and sends nothing — DoD-1", async () => {
    const fetchMock = forbiddenFetch();
    const object = { format: "rphelper-export", payload: { sessions: [] } };

    const parsed = await readExportFile(realFile(JSON.stringify(object)));

    expect(parsed).toEqual(object);
    expect(fetchMock).toHaveBeenCalledTimes(0);
  });

  it("whitespace and key order in the file do not change the parsed object — DoD-1", async () => {
    const fetchMock = forbiddenFetch();

    const parsed = await readExportFile(
      textFile('{\n  "payload":  {"memos": []},\n\n  "granularity": "user"\n}\n'),
    );

    expect(parsed).toEqual({ granularity: "user", payload: { memos: [] } });
    expect(fetchMock).toHaveBeenCalledTimes(0);
  });
});

// ===========================================================================
describe("readExportFile — the unreadable-file failure (DoD-2)", () => {
  const CASES: Array<[string, () => ReadableTextFile]> = [
    ["text `not json`", () => textFile("not json")],
    ["text `[1,2]`", () => textFile("[1,2]")],
    ["text `null`", () => textFile("null")],
    ['text `"str"`', () => textFile('"str"')],
    ["a file whose text() rejects", unreadableFile],
  ];

  it.each(CASES)(
    "rejects with the pinned ApiError for %s, and makes no request — DoD-2",
    async (_label, makeFile) => {
      const fetchMock = forbiddenFetch();

      const error = await rejection(readExportFile(makeFile()));

      expectUnreadable(error);
      expect(fetchMock).toHaveBeenCalledTimes(0);
    },
  );

  it("the code constant is exactly the pinned client code — DoD-2", () => {
    expect(CLIENT_UNREADABLE_FILE).toBe(UNREADABLE_CODE);
  });

  it("the thrown error carries the pinned code constant itself — DoD-2", async () => {
    const fetchMock = forbiddenFetch();

    const error = await rejection(readExportFile(textFile("not json")));

    expect((error as ApiError).code).toBe(CLIENT_UNREADABLE_FILE);
    expect(fetchMock).toHaveBeenCalledTimes(0);
  });
});

// ===========================================================================
describe("postExportFile — the one request it makes (DoD-3)", () => {
  const RESULT = { granularity: "user", character_ids: [CHARACTER_ID] };

  it("posts the parsed object once to the given path, as JSON — DoD-3", async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(RESULT, 200)));
    const object = {
      format: "rphelper-export",
      granularity: "user",
      payload: { users: [{ id: CHARACTER_ID }], memos: [] },
    };

    const decoded = await postExportFile(OWNED_PATH, textFile(JSON.stringify(object)));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [input, init] = fetchMock.mock.calls[0] ?? [];
    expect(requestUrl(input as RequestInfo | URL).pathname).toBe(OWNED_PATH);
    expect(requestMethod(input as RequestInfo | URL, init)).toBe("POST");
    expect(contentType(init)).toMatch(/application\/json/i);
    expect(parsedBody(init)).toEqual(object);
    expect(decoded).toEqual(RESULT);
  });

  it("posts to the session path when that is the path it was given — DoD-3", async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse({ session_id: "1" }, 200)));
    const object = { granularity: "session", payload: { sessions: [{ id: "4" }] } };

    const decoded = await postExportFile(SESSION_PATH, realFile(JSON.stringify(object)));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [input, init] = fetchMock.mock.calls[0] ?? [];
    expect(requestUrl(input as RequestInfo | URL).pathname).toBe(SESSION_PATH);
    expect(requestMethod(input as RequestInfo | URL, init)).toBe("POST");
    expect(parsedBody(init)).toEqual(object);
    expect(decoded).toEqual({ session_id: "1" });
  });

  it("the body is the file's object re-serialized, not the file and not its raw text — DoD-3", async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(RESULT, 200)));
    const object = { payload: { characters: [{ id: CHARACTER_ID, name: "Alma" }] } };

    await postExportFile(OWNED_PATH, textFile(`  ${JSON.stringify(object)}  \n`));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] ?? [];
    const body = parsedBody(init);
    expect(body).toEqual(object);
    // The 19-digit id survives as a string: a body that round-tripped through a number would not.
    expect(((body as { payload: { characters: Array<{ id: unknown }> } }).payload.characters[0] ?? { id: null }).id).toBe(
      CHARACTER_ID,
    );
  });

  it("an unreadable file stops it before the request — DoD-3", async () => {
    const fetchMock = forbiddenFetch();

    const error = await rejection(postExportFile(OWNED_PATH, textFile("not json")));

    expectUnreadable(error);
    expect(fetchMock).toHaveBeenCalledTimes(0);
  });
});

// ===========================================================================
describe("postExportFile — the server's failure envelope (DoD-4)", () => {
  function exportInvalidResponse(): Response {
    return jsonResponse(
      {
        error: {
          code: "export_invalid",
          message: EXPORT_INVALID_MESSAGE,
          detail: { reason: "malformed_payload" },
        },
      },
      400,
    );
  }

  it("rejects with an ApiError carrying the envelope's code and message — DoD-4", async () => {
    const fetchMock = stubFetch(() => Promise.resolve(exportInvalidResponse()));
    const object = { format: "rphelper-export", payload: {} };

    const error = await rejection(postExportFile(OWNED_PATH, textFile(JSON.stringify(object))));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(isApiError(error)).toBe(true);
    const apiError = error as ApiError;
    expect(apiError.code).toBe("export_invalid");
    expect(apiError.message).toBe(EXPORT_INVALID_MESSAGE);
    expect(apiError.status).toBe(400);
    expect(apiError.code).not.toBe(CLIENT_UNREADABLE_FILE);
  });

  it("the 400 failure is reached through the one POST it made — DoD-4", async () => {
    const fetchMock = stubFetch(() => Promise.resolve(exportInvalidResponse()));

    await rejection(postExportFile(SESSION_PATH, textFile('{"payload":{}}')));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [input, init] = fetchMock.mock.calls[0] ?? [];
    expect(requestMethod(input as RequestInfo | URL, init)).toBe("POST");
    expect(requestUrl(input as RequestInfo | URL).pathname).toBe(SESSION_PATH);
  });
});
