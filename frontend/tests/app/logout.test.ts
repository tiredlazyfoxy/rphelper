// Feature 008, step 003 — the logout effect (DoD-6, DoD-7, DoD-8).
// DoD-1..DoD-5, DoD-9 and the menu's half of DoD-6 live in UserMenu.test.tsx;
// DoD-10..DoD-12 are [manual/live] and carry no test.
// `shared/notifyFailure` is replaced by a mock module so the failure channel is observed
// without this file ever importing `@mantine/notifications` (tests/conventions.test.ts).
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { logOut } from "../../src/app/logout";
import { documentNavigation } from "../../src/shared/api";
import { ApiError, CLIENT_TRANSPORT_FAILED } from "../../src/shared/apiError";
import { notifyFailure } from "../../src/shared/notifyFailure";

vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: vi.fn() }));

const LOGOUT_PATH = "/api/auth/logout";
const LOGIN_PATH = "/login";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

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

/** The verified answer of `POST /api/auth/logout`: 204 with an empty body (003.context.md). */
const answerNoContent: FetchFn = () => Promise.resolve(new Response(null, { status: 204 }));

const transportFailure: FetchFn = () => Promise.reject(new TypeError("Failed to fetch"));

const answerEnvelope =
  (status: number, code: string, message: string): FetchFn =>
  () =>
    Promise.resolve(jsonResponse({ error: { code, message, detail: {} } }, status));

/** Behaves like the platform fetch: never settles on its own, rejects with the signal's reason. */
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
  return mock.mock.calls.map(([input, init]) => ({
    path: requestPath(input),
    method: requestMethod(input, init),
  }));
}

function requestBodies(mock: ReturnType<typeof stubFetch>): unknown[] {
  return mock.mock.calls.map(([, init]) => init?.body);
}

const NO_REJECTION = Symbol("no rejection");

async function captureError(fn: () => unknown): Promise<unknown> {
  try {
    await fn();
  } catch (error) {
    return error;
  }
  return NO_REJECTION;
}

function notified(): unknown[] {
  return vi.mocked(notifyFailure).mock.calls.map(([value]) => value);
}

let navigate: MockInstance<(url: string) => void>;

beforeEach(() => {
  navigate = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
  vi.mocked(notifyFailure).mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
describe("logOut posts, then navigates the document to /login", () => {
  it("issues exactly one POST to /api/auth/logout and nothing else — DoD-6", async () => {
    const fetchMock = stubFetch(answerNoContent);
    await logOut();
    expect(requests(fetchMock)).toEqual([{ path: LOGOUT_PATH, method: "POST" }]);
  });

  it("sends no request body — DoD-6", async () => {
    const fetchMock = stubFetch(answerNoContent);
    await logOut();
    expect(requestBodies(fetchMock)).toEqual([undefined]);
  });

  it("navigates the document to exactly /login, once — DoD-6", async () => {
    stubFetch(answerNoContent);
    await logOut();
    expect(navigate.mock.calls).toEqual([[LOGIN_PATH]]);
  });

  it("resolves without throwing on a 204 with an empty body — DoD-6", async () => {
    stubFetch(answerNoContent);
    await expect(logOut()).resolves.toBeUndefined();
  });

  it("a successful logout raises no notification — DoD-6", async () => {
    stubFetch(answerNoContent);
    await logOut();
    expect(notified()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("a failure notifies and stays where it is (context.md D7)", () => {
  it("a transport failure notifies with the thrown error — DoD-7", async () => {
    stubFetch(transportFailure);
    await logOut();
    const seen = notified();
    expect(seen).toHaveLength(1);
    expect(seen[0]).toBeInstanceOf(ApiError);
    expect((seen[0] as ApiError).code).toBe(CLIENT_TRANSPORT_FAILED);
  });

  it("a transport failure navigates the document nowhere — DoD-7", async () => {
    stubFetch(transportFailure);
    await logOut();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("a transport failure resolves without throwing — DoD-7", async () => {
    stubFetch(transportFailure);
    await expect(logOut()).resolves.toBeUndefined();
  });

  it("a well-formed 500 envelope notifies with the thrown error — DoD-7", async () => {
    stubFetch(answerEnvelope(500, "internal_error", "The request could not be completed."));
    await logOut();
    const seen = notified();
    expect(seen).toHaveLength(1);
    expect(seen[0]).toBeInstanceOf(ApiError);
    expect((seen[0] as ApiError).code).toBe("internal_error");
    expect((seen[0] as ApiError).message).toBe("The request could not be completed.");
  });

  it("a well-formed 500 envelope navigates the document nowhere — DoD-7", async () => {
    stubFetch(answerEnvelope(500, "internal_error", "The request could not be completed."));
    await logOut();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("a well-formed 500 envelope resolves without throwing — DoD-7", async () => {
    stubFetch(answerEnvelope(500, "internal_error", "The request could not be completed."));
    await expect(logOut()).resolves.toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
describe("an already-aborted signal is neither a logout nor a failure", () => {
  it("navigates the document nowhere — DoD-8", async () => {
    stubFetch(abortableFetch());
    const controller = new AbortController();
    controller.abort();
    await captureError(() => logOut(controller.signal));
    expect(navigate).not.toHaveBeenCalled();
  });

  it("raises no notification — DoD-8", async () => {
    stubFetch(abortableFetch());
    const controller = new AbortController();
    controller.abort();
    await captureError(() => logOut(controller.signal));
    expect(notified()).toEqual([]);
  });
});
