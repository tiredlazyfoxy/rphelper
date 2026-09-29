// Feature 005, step 004 — the admin gate's logic (DoD-1..DoD-7, plus the failed result's
// message and the interval constant for DoD-10). The rest of DoD-8..DoD-10 and DoD-12 live in
// AdminNotReady.test.tsx; DoD-11 in entries.test.tsx; DoD-13..DoD-16 are [manual/live].
// Re-bound 2026-09-29: `enforceAdminAccess` resolves to a result object; its outcome is read
// from `.decision`, and a failed result carries the error's message (context.md D13).
//
// The five outcomes and who navigates come from context.md D13: only the shared client's own
// /login (on a 401) and the gate's one navigation to / (role below administrator) ever leave
// the document. `fetch` is stubbed per test; the document-navigation seam is spied on.
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import {
  ADMIN_ACCESS_RETRY_INTERVAL_MS,
  classifyAdminAccessError,
  enforceAdminAccess,
  resolveAdminAccess,
  type CurrentUser,
} from "../../src/admin/adminAccess";
import { documentNavigation } from "../../src/shared/api";
import { ApiError, CLIENT_MALFORMED_ERROR, CLIENT_TRANSPORT_FAILED } from "../../src/shared/apiError";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

let navigate: MockInstance<(url: string) => void>;

beforeEach(() => {
  navigate = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
});

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

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function identity(role: CurrentUser["role"], id = "9007199254740993"): CurrentUser {
  return { id, username: "mira", role };
}

const answerIdentity = (role: CurrentUser["role"]) => () => Promise.resolve(jsonResponse(identity(role), 200));

const answerEnvelope = (status: number, code: string, message: string) => () =>
  Promise.resolve(jsonResponse({ error: { code, message, detail: {} } }, status));

const answer401 = answerEnvelope(401, "not_authenticated", "You are not signed in.");

const transportFailure = () => Promise.reject(new TypeError("Failed to fetch"));

const htmlPage = (status: number) => () =>
  Promise.resolve(
    new Response(`<html><body><h1>${status} Bad Gateway</h1><hr>nginx</body></html>`, {
      status,
      headers: { "Content-Type": "text/html" },
    }),
  );

/** Behaves like the platform fetch: never settles on its own, rejects with the signal's reason on abort. */
function abortableFetch(): FetchFn {
  return (_input, init) =>
    new Promise<Response>((_resolve, reject) => {
      const signal = init?.signal;
      if (!signal) return;
      if (signal.aborted) {
        reject(signal.reason);
        return;
      }
      signal.addEventListener("abort", () => reject(signal.reason), { once: true });
    });
}

function requestPath(input: RequestInfo | URL): string {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost").pathname;
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function requests(mock: ReturnType<typeof stubFetch>): Array<{ path: string; method: string }> {
  return mock.mock.calls.map(([input, init]) => ({ path: requestPath(input), method: requestMethod(input, init) }));
}

/** The gate's outcome, read from the result's `decision` discriminant (re-freeze 2026-09-29). */
async function decisionOf(signal?: AbortSignal): Promise<string> {
  const result = await enforceAdminAccess(signal);
  return result.decision;
}

const NO_REJECTION = Symbol("no rejection");

async function captureError(fn: () => unknown): Promise<unknown> {
  try {
    await fn();
  } catch (e) {
    return e;
  }
  return NO_REJECTION;
}

// ---------------------------------------------------------------------------
describe("resolveAdminAccess is a pure, total decision over the fetched identity", () => {
  it("an administrator identity is granted — DoD-1", () => {
    expect(resolveAdminAccess(identity("admin"))).toBe("granted");
  });

  it("an identity below administrator is denied-not-admin — DoD-1", () => {
    expect(resolveAdminAccess(identity("roleplayer"))).toBe("denied-not-admin");
  });

  it("nothing fetched is denied-no-session — DoD-1", () => {
    expect(resolveAdminAccess(null)).toBe("denied-no-session");
  });

  it("only the role decides — the id and username do not change the outcome — DoD-1", () => {
    for (const id of ["1", "9007199254740993", "18446744073709551615"]) {
      expect(resolveAdminAccess({ id, username: "someone else", role: "admin" })).toBe("granted");
      expect(resolveAdminAccess({ id, username: "someone else", role: "roleplayer" })).toBe("denied-not-admin");
    }
  });

  it("is callable with no network and navigates nothing — DoD-1", () => {
    const fetchMock = stubFetch(() => Promise.reject(new Error("the pure decision must not fetch")));
    resolveAdminAccess(identity("admin"));
    resolveAdminAccess(identity("roleplayer"));
    resolveAdminAccess(null);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("classifyAdminAccessError delegates the not-ready judgement", () => {
  it("the transport-failure code at status 0 is not-ready — DoD-2", () => {
    expect(
      classifyAdminAccessError(new ApiError(CLIENT_TRANSPORT_FAILED, "The server could not be reached.", 0)),
    ).toBe("not-ready");
  });

  it.each([500, 502, 503, 504])("the malformed-body code at %i is not-ready — DoD-2", (status) => {
    expect(classifyAdminAccessError(new ApiError(CLIENT_MALFORMED_ERROR, "Unexpected response.", status))).toBe(
      "not-ready",
    );
  });

  it("a well-formed backend envelope at 403 is failed — DoD-2", () => {
    expect(
      classifyAdminAccessError(new ApiError("insufficient_role", "You do not have access to this.", 403, {})),
    ).toBe("failed");
  });

  it("a well-formed backend envelope at 500 is failed — DoD-2", () => {
    expect(classifyAdminAccessError(new ApiError("internal_error", "Something went wrong.", 500, {}))).toBe(
      "failed",
    );
  });

  it.each([400, 403, 404, 409, 422, 499])("the malformed-body code at 4xx status %i is failed — DoD-2", (status) => {
    expect(classifyAdminAccessError(new ApiError(CLIENT_MALFORMED_ERROR, "Unexpected response.", status))).toBe(
      "failed",
    );
  });

  const NON_API_VALUES: Array<[string, unknown]> = [
    ["a plain Error", new Error("boom")],
    ["a TypeError like a raw fetch rejection", new TypeError("Failed to fetch")],
    ["a string", CLIENT_TRANSPORT_FAILED],
    ["undefined", undefined],
    ["null", null],
    ["a plain object shaped like a transport failure", { code: CLIENT_TRANSPORT_FAILED, status: 0, message: "x" }],
    ["a plain object shaped like a malformed 502", { code: CLIENT_MALFORMED_ERROR, status: 502, message: "x" }],
  ];

  it.each(NON_API_VALUES)("a value that is not an ApiError is failed: %s — DoD-2", (_name, value) => {
    expect(classifyAdminAccessError(value)).toBe("failed");
  });
});

// ---------------------------------------------------------------------------
describe("enforceAdminAccess issues exactly one GET /api/me per call", () => {
  const SCENARIOS: Array<[string, FetchFn]> = [
    ["an administrator", answerIdentity("admin")],
    ["a roleplayer", answerIdentity("roleplayer")],
    ["a 401", answer401],
    ["a transport failure", transportFailure],
    ["a raw 502 page", htmlPage(502)],
    ["a 403 envelope", answerEnvelope(403, "insufficient_role", "No.")],
  ];

  it.each(SCENARIOS)("answering %s, one GET /api/me and nothing else — DoD-3", async (_name, handler) => {
    const fetchMock = stubFetch(handler);
    await captureError(() => enforceAdminAccess());
    expect(requests(fetchMock)).toEqual([{ path: "/api/me", method: "GET" }]);
  });

  it("two calls issue two requests, one each — DoD-3", async () => {
    const fetchMock = stubFetch(answerIdentity("admin"));
    await enforceAdminAccess();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await enforceAdminAccess();
    expect(requests(fetchMock)).toEqual([
      { path: "/api/me", method: "GET" },
      { path: "/api/me", method: "GET" },
    ]);
  });

  it("an administrator identity resolves to granted and navigates nothing — DoD-3", async () => {
    stubFetch(answerIdentity("admin"));
    expect(await decisionOf()).toBe("granted");
    expect(navigate).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("a failed outcome carries the error's message (context.md D13)", () => {
  it("a well-formed 403 envelope resolves to failed with the envelope's message and navigates nothing — DoD-10", async () => {
    const message = "The identity probe was refused zq-403.";
    stubFetch(answerEnvelope(403, "insufficient_role", message));
    const result = await enforceAdminAccess();
    expect(result.decision).toBe("failed");
    expect(result).toMatchObject({ decision: "failed", message });
    expect(navigate).not.toHaveBeenCalled();
  });

  it("a well-formed 500 envelope resolves to failed with the envelope's message — DoD-10", async () => {
    const message = "Something went sideways zq-500.";
    stubFetch(answerEnvelope(500, "internal_error", message));
    const result = await enforceAdminAccess();
    expect(result).toMatchObject({ decision: "failed", message });
    expect(navigate).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("a 401 is denied-no-session and is not navigated twice", () => {
  it("resolves to denied-no-session — DoD-4", async () => {
    stubFetch(answer401);
    expect(await decisionOf()).toBe("denied-no-session");
  });

  it("the shared client's /login navigation is the only one — DoD-4", async () => {
    stubFetch(answer401);
    await captureError(() => enforceAdminAccess());
    expect(navigate.mock.calls).toEqual([["/login"]]);
  });
});

// ---------------------------------------------------------------------------
describe("a role below administrator is denied-not-admin with one navigation to /", () => {
  it("resolves to denied-not-admin — DoD-5", async () => {
    stubFetch(answerIdentity("roleplayer"));
    expect(await decisionOf()).toBe("denied-not-admin");
  });

  it("performs exactly one document navigation, to / and not to /login — DoD-5", async () => {
    stubFetch(answerIdentity("roleplayer"));
    await captureError(() => enforceAdminAccess());
    expect(navigate.mock.calls).toEqual([["/"]]);
  });

  it("does not end the session — no request besides GET /api/me — DoD-5", async () => {
    const fetchMock = stubFetch(answerIdentity("roleplayer"));
    await captureError(() => enforceAdminAccess());
    expect(requests(fetchMock)).toEqual([{ path: "/api/me", method: "GET" }]);
  });
});

// ---------------------------------------------------------------------------
describe("a transport failure or a 502 is not-ready, never a deny", () => {
  const NOT_READY: Array<[string, FetchFn]> = [
    ["a transport failure", transportFailure],
    ["a raw 502 page", htmlPage(502)],
  ];

  it.each(NOT_READY)("%s resolves to not-ready — DoD-6", async (_name, handler) => {
    stubFetch(handler);
    expect(await decisionOf()).toBe("not-ready");
  });

  it.each(NOT_READY)("%s performs no navigation at all — DoD-6", async (_name, handler) => {
    stubFetch(handler);
    await captureError(() => enforceAdminAccess());
    expect(navigate).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("the caller's own abort propagates unwrapped", () => {
  function expectUnwrappedAbort(caught: unknown, controller: AbortController): void {
    expect(caught).not.toBe(NO_REJECTION);
    expect(caught).toBe(controller.signal.reason);
    expect(caught).not.toBeInstanceOf(ApiError);
    expect(caught).not.toBe("not-ready");
    expect(caught).not.toBe("failed");
  }

  it("an abort during the request rejects with the signal's own reason — DoD-7", async () => {
    const fetchMock = stubFetch(abortableFetch());
    const controller = new AbortController();
    const pending = captureError(() => enforceAdminAccess(controller.signal));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    controller.abort();
    expectUnwrappedAbort(await pending, controller);
  });

  it("an already-aborted signal rejects with its own reason — DoD-7", async () => {
    stubFetch(abortableFetch());
    const controller = new AbortController();
    controller.abort();
    expectUnwrappedAbort(await captureError(() => enforceAdminAccess(controller.signal)), controller);
  });

  it("an abort resolves to neither not-ready nor failed — DoD-7", async () => {
    stubFetch(abortableFetch());
    const controller = new AbortController();
    controller.abort();
    let resolved: unknown = NO_REJECTION;
    try {
      resolved = await enforceAdminAccess(controller.signal);
    } catch {
      // rejection is the expected path
    }
    expect(resolved).toBe(NO_REJECTION);
    expect(navigate).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("the re-probe interval", () => {
  it("is a fixed 2000 ms — DoD-10", () => {
    expect(ADMIN_ACCESS_RETRY_INTERVAL_MS).toBe(2000);
  });
});
