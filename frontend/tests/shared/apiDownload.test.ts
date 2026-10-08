// Feature 030 — export-granularities, step 004: the blob-download call in the API client
// (DoD-1..DoD-9; DoD-10 is [manual/live]).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 004.context.md and the feature context.md. Bindings come from the frozen `### Step 004`
// record: `apiDownload(path, signal?) : Promise<DownloadResult>`,
// `filenameFromContentDisposition(header) : string` and the `DownloadResult` type, all from
// `src/shared/api`; `ApiError` / `isApiError` / the two `client_*` codes from
// `src/shared/apiError`; the 401 seam is the pre-existing `documentNavigation` export.
//
// Harness conventions:
// - `fetch` is stubbed per test with `vi.stubGlobal`, answering platform `Response` objects.
// - jsdom implements neither `URL.createObjectURL` nor `URL.revokeObjectURL`, so both are
//   installed per test and restored afterwards (004.context.md). Every created URL, every
//   revoked URL and the ordering of create/click/revoke are recorded.
// - The anchor click is observed through a spy on `HTMLAnchorElement.prototype.click`, which
//   records the element's `href` and `download` attributes at click time; the spy also keeps
//   jsdom from attempting a navigation.
// - `size` is the `Blob`'s byte count, never a character count, so the body fixture is
//   deliberately multi-byte.
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import {
  apiDownload,
  apiGet,
  apiPost,
  documentNavigation,
  filenameFromContentDisposition,
  type DownloadResult,
} from "../../src/shared/api";
import {
  ApiError,
  CLIENT_MALFORMED_ERROR,
  CLIENT_TRANSPORT_FAILED,
  isApiError,
} from "../../src/shared/apiError";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

/** context.md — the admin whole-database export route. Any `/api/...` path would do. */
const EXPORT_PATH = "/api/admin/database/export";
/** DoD-3 — the fallback when `Content-Disposition` is absent or unparseable. */
const FALLBACK_FILENAME = "rphelper-export.json";
/** context.md — the routes' filename shape; it embeds no user content. */
const HEADER_FILENAME = "rphelper-database-20260105T101112Z.json";
/** Multi-byte on purpose: its byte length differs from its character length. */
const BODY =
  '{"format":"rphelper-export","payload":{"memos":[{"body":"мемо — héllo"}]}}';
const BODY_BYTES = new TextEncoder().encode(BODY).length;

type ClickRecord = { href: string | null; download: string | null };

let created: unknown[];
let revoked: string[];
/** The create / click / revoke sequence, in the order the client performed it. */
let order: string[];
let clicks: ClickRecord[];
let nav: MockInstance<(url: string) => void>;
let hadCreateObjectUrl: boolean;
let hadRevokeObjectUrl: boolean;

beforeEach(() => {
  created = [];
  revoked = [];
  order = [];
  clicks = [];
  let issued = 0;

  hadCreateObjectUrl = typeof URL.createObjectURL === "function";
  hadRevokeObjectUrl = typeof URL.revokeObjectURL === "function";
  URL.createObjectURL = (obj: Blob | MediaSource): string => {
    created.push(obj);
    order.push("create");
    issued += 1;
    return `blob:rphelper/${issued}`;
  };
  URL.revokeObjectURL = (url: string): void => {
    revoked.push(url);
    order.push("revoke");
  };

  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    order.push("click");
    clicks.push({
      href: this.getAttribute("href"),
      download: this.getAttribute("download"),
    });
  });

  nav = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {
    order.push("navigate");
  });
});

afterEach(() => {
  if (!hadCreateObjectUrl) Reflect.deleteProperty(URL, "createObjectURL");
  if (!hadRevokeObjectUrl) Reflect.deleteProperty(URL, "revokeObjectURL");
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- helpers

function stubFetch(impl: FetchFn) {
  const mock = vi.fn<FetchFn>(impl);
  vi.stubGlobal("fetch", mock);
  return mock;
}

/** Every call answers a fresh `Response` built by `make` (a body can be read once). */
function respondWith(make: () => Response) {
  return stubFetch(() => Promise.resolve(make()));
}

function exportResponse(options: { filename?: string | null; body?: string } = {}): Response {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const filename = options.filename === undefined ? HEADER_FILENAME : options.filename;
  if (filename !== null) headers["Content-Disposition"] = `attachment; filename="${filename}"`;
  return new Response(options.body ?? BODY, { status: 200, headers });
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, message: string, detail: Record<string, unknown> = {}) {
  return { error: { code, message, detail } };
}

type Recorded = {
  url: string;
  method: string;
  credentials: RequestCredentials | undefined;
};

function recorded(mock: ReturnType<typeof stubFetch>, index = 0): Recorded {
  const call = mock.mock.calls[index];
  if (call === undefined) throw new Error(`fetch was not called (call #${index})`);
  const [input, init] = call;
  const req = input instanceof Request ? input : undefined;
  const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return {
    url,
    method: (init?.method ?? req?.method ?? "GET").toUpperCase(),
    credentials: init?.credentials ?? req?.credentials,
  };
}

const NO_REJECTION = Symbol("no rejection");

/** Runs `fn`, returning what it threw or rejected with (sync throw or async rejection). */
async function captureError(fn: () => unknown): Promise<unknown> {
  try {
    await fn();
  } catch (e) {
    return e;
  }
  return NO_REJECTION;
}

function expectApiError(value: unknown): ApiError {
  expect(value).not.toBe(NO_REJECTION);
  expect(value).toBeInstanceOf(ApiError);
  return value as ApiError;
}

type BlobLike = { size: number; text(): Promise<string> };

/**
 * The thing an object URL was created from, checked structurally rather than with
 * `instanceof` (the platform `Response.blob()` may come from another realm than jsdom's).
 */
function asBlobLike(value: unknown): BlobLike {
  const candidate = value as Partial<BlobLike> | null | undefined;
  expect(candidate ?? null, "the object URL's source").not.toBeNull();
  expect(typeof candidate?.size, "the object URL's source carries a byte size").toBe("number");
  expect(typeof candidate?.text, "the object URL's source is readable like a Blob").toBe(
    "function",
  );
  return candidate as BlobLike;
}

function anchorsInDocument(): Element[] {
  return Array.from(document.querySelectorAll("a"));
}

/** Behaves like the platform fetch: rejects with the signal's reason once it aborts. */
function abortableFetch(): FetchFn {
  return (_input, init) =>
    new Promise<Response>((_resolve, reject) => {
      const signal = init?.signal;
      if (!signal) return; // never settles without a signal
      if (signal.aborted) {
        reject(signal.reason);
        return;
      }
      signal.addEventListener("abort", () => reject(signal.reason), { once: true });
    });
}

// ---------------------------------------------------------------- the 200 path

describe("apiDownload on a 200", () => {
  it("issues one GET of the given path with same-origin credentials and resolves the body's byte size — DoD-1", async () => {
    const mock = respondWith(() => exportResponse());

    const result: DownloadResult = await apiDownload(EXPORT_PATH);

    expect(mock).toHaveBeenCalledTimes(1);
    const call = recorded(mock);
    expect(call.url).toBe(EXPORT_PATH);
    expect(call.method).toBe("GET");
    expect(call.credentials).toBe("same-origin");
    expect(result.size).toBe(BODY_BYTES);
    // 004.context.md — a byte count, not a character count.
    expect(result.size).not.toBe(BODY.length);
  });

  it("creates an object URL from the body, clicks an anchor carrying it exactly once, and revokes it afterwards — DoD-2", async () => {
    respondWith(() => exportResponse());

    await apiDownload(EXPORT_PATH);

    expect(created).toHaveLength(1);
    const source = asBlobLike(created[0]);
    expect(source.size).toBe(BODY_BYTES);
    expect(await source.text()).toBe(BODY);

    const objectUrl = "blob:rphelper/1";
    expect(clicks).toHaveLength(1);
    expect(clicks[0].href).toBe(objectUrl);
    expect(clicks[0].download).toBe(HEADER_FILENAME);

    await vi.waitFor(() => expect(revoked).toEqual([objectUrl]));
    expect(order).toEqual(["create", "click", "revoke"]);
  });

  it("resolves the quoted filename from Content-Disposition — DoD-3", async () => {
    respondWith(() => exportResponse({ filename: HEADER_FILENAME }));

    const result = await apiDownload(EXPORT_PATH);

    expect(result.filename).toBe(HEADER_FILENAME);
    expect(clicks[0]?.download).toBe(HEADER_FILENAME);
  });

  it("falls back to rphelper-export.json when there is no Content-Disposition header — DoD-3", async () => {
    respondWith(() => exportResponse({ filename: null }));

    const result = await apiDownload(EXPORT_PATH);

    expect(result.filename).toBe(FALLBACK_FILENAME);
    expect(clicks[0]?.download).toBe(FALLBACK_FILENAME);
  });

  it("leaves no anchor element in the document after the download — DoD-4", async () => {
    expect(anchorsInDocument()).toHaveLength(0);
    respondWith(() => exportResponse());

    await apiDownload(EXPORT_PATH);

    // The click proves a temporary anchor existed; nothing may survive it.
    expect(clicks).toHaveLength(1);
    expect(anchorsInDocument()).toHaveLength(0);
  });
});

// ---------------------------------------------------------------- the pure header reader

describe("filenameFromContentDisposition", () => {
  it.each([
    [`attachment; filename="${HEADER_FILENAME}"`, HEADER_FILENAME],
    [`attachment; filename="rphelper-user-20260105T101112Z.json"`, "rphelper-user-20260105T101112Z.json"],
    [`inline; filename="plain.json"`, "plain.json"],
  ])("reads the quoted filename out of %s — DoD-3", (header, expected) => {
    expect(filenameFromContentDisposition(header)).toBe(expected);
  });

  it.each([
    ["a null header", null],
    ["an empty header", ""],
    ["a header with no filename parameter", "attachment"],
    ["a header whose filename is unparseable", "attachment; filename="],
  ])("falls back to rphelper-export.json for %s — DoD-3", (_label, header) => {
    expect(filenameFromContentDisposition(header)).toBe(FALLBACK_FILENAME);
  });
});

// ---------------------------------------------------------------- the non-2xx path

/** Non-2xx bodies that are not the error envelope (DoD-7). */
const MALFORMED: Array<[string, number, () => Response]> = [
  ["an empty body", 500, () => new Response("", { status: 500 })],
  [
    "an HTML error page",
    502,
    () =>
      new Response("<html><body><h1>502 Bad Gateway</h1></body></html>", {
        status: 502,
        headers: { "Content-Type": "text/html" },
      }),
  ],
  [
    "plain text",
    400,
    () => new Response("Bad Request", { status: 400, headers: { "Content-Type": "text/plain" } }),
  ],
  ["JSON of another shape", 404, () => jsonResponse({ detail: "Not Found" }, 404)],
];

describe("apiDownload on a failure", () => {
  it.each([400, 404, 500, 503])(
    "rejects a non-2xx envelope (%i) with the envelope's code and message and the real status, creating no object URL — DoD-5",
    async (status) => {
      respondWith(() =>
        jsonResponse(envelope("export_failed", "The export could not be produced."), status),
      );

      const err = expectApiError(await captureError(() => apiDownload(EXPORT_PATH)));

      expect(err.code).toBe("export_failed");
      expect(err.message).toBe("The export could not be produced.");
      expect(err.status).toBe(status);
      expect(created).toEqual([]);
      expect(clicks).toEqual([]);
      expect(nav).not.toHaveBeenCalled();
    },
  );

  it("navigates the document to /login on a 401 and then rejects with an ApiError of status 401 — DoD-6", async () => {
    respondWith(() => jsonResponse(envelope("not_authenticated", "Not signed in."), 401));

    const err = expectApiError(await captureError(() => apiDownload(EXPORT_PATH)));

    expect(nav).toHaveBeenCalledWith("/login");
    expect(nav).toHaveBeenCalledTimes(1);
    expect(err.status).toBe(401);
    expect(created).toEqual([]);
    expect(order).toEqual(["navigate"]);
  });

  it.each(MALFORMED)(
    "rejects a non-2xx carrying %s with client_malformed_error and the real status — DoD-7",
    async (_label, status, make) => {
      respondWith(make);

      const err = expectApiError(await captureError(() => apiDownload(EXPORT_PATH)));

      expect(err.code).toBe(CLIENT_MALFORMED_ERROR);
      expect(err.code).toBe("client_malformed_error");
      expect(err.status).toBe(status);
      expect(created).toEqual([]);
    },
  );

  it("rejects a fetch rejection with client_transport_failed and status 0 — DoD-7", async () => {
    stubFetch(() => Promise.reject(new TypeError("Failed to fetch")));

    const err = expectApiError(await captureError(() => apiDownload(EXPORT_PATH)));

    expect(err.code).toBe(CLIENT_TRANSPORT_FAILED);
    expect(err.code).toBe("client_transport_failed");
    expect(err.status).toBe(0);
    expect(created).toEqual([]);
    expect(clicks).toEqual([]);
  });
});

// ---------------------------------------------------------------- abort

describe("apiDownload and an aborted signal", () => {
  function expectUnwrappedAbort(caught: unknown, controller: AbortController): void {
    expect(caught).not.toBe(NO_REJECTION);
    expect(caught).toBe(controller.signal.reason);
    expect(caught).not.toBeInstanceOf(ApiError);
    expect(isApiError(caught)).toBe(false);
    const code = (caught as { code?: unknown }).code;
    expect(code).not.toBe(CLIENT_TRANSPORT_FAILED);
    expect(code).not.toBe(CLIENT_MALFORMED_ERROR);
  }

  it("rejects with the original abort error when the signal is already aborted — DoD-8", async () => {
    stubFetch(abortableFetch());
    const controller = new AbortController();
    controller.abort();

    expectUnwrappedAbort(
      await captureError(() => apiDownload(EXPORT_PATH, controller.signal)),
      controller,
    );
    expect(created).toEqual([]);
    expect(clicks).toEqual([]);
  });

  it("rejects with the original abort error when the signal aborts mid-flight — DoD-8", async () => {
    const mock = stubFetch(abortableFetch());
    const controller = new AbortController();

    const pending = captureError(() => apiDownload(EXPORT_PATH, controller.signal));
    await vi.waitFor(() => expect(mock).toHaveBeenCalled());
    controller.abort();

    expectUnwrappedAbort(await pending, controller);
    expect(created).toEqual([]);
  });
});

// ---------------------------------------------------------------- regression: the JSON calls

describe("the existing JSON calls are unchanged", () => {
  it("apiGet still resolves a 2xx JSON body and still rejects an envelope with its code and status — DoD-9", async () => {
    const payload = { id: "9007199254740993", name: "Mira" };
    const ok = respondWith(() => jsonResponse(payload, 200));
    await expect(apiGet("/api/characters/9007199254740993")).resolves.toStrictEqual(payload);
    expect(recorded(ok).method).toBe("GET");

    respondWith(() => jsonResponse(envelope("character_not_found", "No such character."), 404));
    const err = expectApiError(await captureError(() => apiGet("/api/characters/1")));
    expect(err.code).toBe("character_not_found");
    expect(err.message).toBe("No such character.");
    expect(err.status).toBe(404);
  });

  it("apiPost still resolves a 2xx JSON body and still rejects an envelope with its code and status — DoD-9", async () => {
    const ok = respondWith(() => jsonResponse({ id: "42" }, 201));
    await expect(apiPost("/api/characters", { name: "Mira" })).resolves.toStrictEqual({ id: "42" });
    expect(recorded(ok).method).toBe("POST");

    respondWith(() => jsonResponse(envelope("validation_failed", "The name is required."), 422));
    const err = expectApiError(await captureError(() => apiPost("/api/characters", {})));
    expect(err.code).toBe("validation_failed");
    expect(err.message).toBe("The name is required.");
    expect(err.status).toBe(422);
  });
});
