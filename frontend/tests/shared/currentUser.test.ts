// Feature 008, step 001 — the shared identity probe `fetchCurrentUser` (DoD-1, DoD-2).
// DoD-3 (the admin gate is unchanged) lives in tests/admin/adminAccess.test.ts; DoD-4 and
// DoD-13 in tests/app/entryIsolation.test.ts; DoD-5..DoD-12 in tests/app/workspaceLayout.test.ts.
//
// The module adds no error handling of its own (context.md D1), so a failure must arrive
// exactly as the shared client in src/shared/api.ts threw it. `fetch` is stubbed per test.
import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchCurrentUser, type CurrentUser } from "../../src/shared/currentUser";
import { ApiError, CLIENT_TRANSPORT_FAILED } from "../../src/shared/apiError";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

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

const answerIdentity = (role: CurrentUser["role"], id?: string) => () =>
  Promise.resolve(jsonResponse(identity(role, id), 200));

const answerEnvelope = (status: number, code: string, message: string) => () =>
  Promise.resolve(jsonResponse({ error: { code, message, detail: {} } }, status));

const transportFailure = () => Promise.reject(new TypeError("Failed to fetch"));

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
describe("fetchCurrentUser performs one GET /api/me and returns the body unchanged", () => {
  it("issues exactly one GET to /api/me and nothing else — DoD-1", async () => {
    const fetchMock = stubFetch(answerIdentity("admin"));
    await fetchCurrentUser();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(requests(fetchMock)).toEqual([{ path: "/api/me", method: "GET" }]);
  });

  it("resolves to the body's id, username and role unchanged — DoD-1", async () => {
    stubFetch(answerIdentity("admin", "9007199254740993"));
    const user = await fetchCurrentUser();
    expect(user).toEqual({ id: "9007199254740993", username: "mira", role: "admin" });
  });

  it("resolves a roleplayer's role unchanged too — DoD-1", async () => {
    stubFetch(answerIdentity("roleplayer", "1"));
    const user = await fetchCurrentUser();
    expect(user).toEqual({ id: "1", username: "mira", role: "roleplayer" });
  });

  it("keeps the id a string, never a number — DoD-1", async () => {
    stubFetch(answerIdentity("admin", "18446744073709551615"));
    const user = await fetchCurrentUser();
    expect(typeof user.id).toBe("string");
    expect(user.id).toBe("18446744073709551615");
  });

  it("two calls issue two requests, one each — DoD-1", async () => {
    const fetchMock = stubFetch(answerIdentity("admin"));
    await fetchCurrentUser();
    await fetchCurrentUser();
    expect(requests(fetchMock)).toEqual([
      { path: "/api/me", method: "GET" },
      { path: "/api/me", method: "GET" },
    ]);
  });
});

// ---------------------------------------------------------------------------
describe("a failure propagates exactly as the shared client threw it", () => {
  it("a well-formed 403 envelope rejects with an ApiError carrying the envelope's code — DoD-2", async () => {
    const message = "The identity probe was refused zq-403.";
    stubFetch(answerEnvelope(403, "insufficient_role", message));
    const caught = await captureError(() => fetchCurrentUser());
    expect(caught).not.toBe(NO_REJECTION);
    expect(caught).toBeInstanceOf(ApiError);
    expect(caught).toMatchObject({ code: "insufficient_role", status: 403, message });
  });

  it("a rejected fetch rejects with the client's transport-failure ApiError — DoD-2", async () => {
    stubFetch(transportFailure);
    const caught = await captureError(() => fetchCurrentUser());
    expect(caught).not.toBe(NO_REJECTION);
    expect(caught).toBeInstanceOf(ApiError);
    expect(caught).toMatchObject({ code: CLIENT_TRANSPORT_FAILED, status: 0, detail: {} });
  });

  it("a failure is not swallowed into a resolved value — DoD-2", async () => {
    stubFetch(transportFailure);
    let resolved: unknown = NO_REJECTION;
    try {
      resolved = await fetchCurrentUser();
    } catch {
      // rejection is the expected path
    }
    expect(resolved).toBe(NO_REJECTION);
  });
});
