// Feature 011, step 009 — the session screen's state (DoD-1).
// The screen's own clauses (DoD-2..DoD-10) live in SessionScreen.test.tsx, DoD-11 in
// App.test.tsx, DoD-12 in entries.test.tsx; DoD-13 is [manual/live] and carries no test.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done plus
// context.md's D3 (reading never bumps: this module issues one GET and no write) and D17:
//   - a data class with observable fields only — `sessionId` verbatim, `session` null,
//     `status` "idle";
//   - `loadSessionScreen` sets "loading" while the request is pending, requests exactly
//     `GET /api/sessions/<sessionId>`, writes the returned row with "ready" (every id still
//     the payload's own string), maps a 404 `session_not_found` to "not-found" and every
//     other failure — a 500 or a transport failure — to "failed", never rejects, and writes
//     nothing once its signal has aborted.
import { runInAction, toJS } from "mobx";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Session } from "../../src/app/sessionsApi";
import { SessionScreenState, loadSessionScreen } from "../../src/app/sessionScreenState";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string };

// ---------------------------------------------------------------- fixtures
/** DoD-1's own id: the request the spec names is exactly `GET /api/sessions/s1`. */
const SESSION_ID = "s1";
const SESSION_PATH = `/api/sessions/${SESSION_ID}`;

/** Payload ids past Number.MAX_SAFE_INTEGER, so any coercion would be visible. */
const PAYLOAD_SESSION_ID = "9007199254740993"; // 2^53 + 1
const PAYLOAD_CHARACTER_ID = "7250000000000000011";
const PAYLOAD_SETUP_ID = "7250000000000000012";

const STAMP = "2026-05-10T09:00:00.000000+00:00";

const LOADED: Session = {
  id: PAYLOAD_SESSION_ID,
  character_id: PAYLOAD_CHARACTER_ID,
  setup_id: PAYLOAD_SETUP_ID,
  setup_name: "Tavern",
  archived_at: null,
  last_used_at: STAMP,
  created_at: STAMP,
  updated_at: STAMP,
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- harness
function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** A domain envelope — the shape every non-2xx of ours carries. */
function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: "ql-77 went wrong.", detail: {} } }, status);
}

function notFound(): Response {
  return envelope("session_not_found", 404);
}

function serverError(): Response {
  return envelope("internal_error", 500);
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function stubFetch(impl: FetchFn) {
  const mock = vi.fn<FetchFn>(impl);
  vi.stubGlobal("fetch", mock);
  return mock;
}

/** A URL-routed in-memory backend; every request is recorded in order, by exact pathname. */
function stubBackend(handler: (request: Seen) => Response | Promise<Response>) {
  const calls: Seen[] = [];
  const mock = stubFetch(async (input, init) => {
    const url = requestUrl(input);
    const request: Seen = {
      method: requestMethod(input, init),
      path: url.pathname,
      search: url.search,
    };
    calls.push(request);
    return handler(request);
  });
  return { mock, calls };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

async function flush(rounds = 4): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await new Promise<void>((resolve) => setImmediate(resolve));
  }
}

function snapshot(state: SessionScreenState) {
  return {
    sessionId: state.sessionId,
    status: state.status,
    session: toJS(state.session),
  };
}

type FailureCase = [label: string, answer: () => Response | never];

// ---------------------------------------------------------------------------
describe("a fresh session screen state", () => {
  it("carries the id it was built with, no session and an idle status — DoD-1", () => {
    expect(snapshot(new SessionScreenState(SESSION_ID))).toEqual({
      sessionId: SESSION_ID,
      status: "idle",
      session: null,
    });
  });

  it("keeps an id past Number.MAX_SAFE_INTEGER as the string it was given — DoD-1", () => {
    expect(new SessionScreenState(PAYLOAD_SESSION_ID).sessionId).toBe(PAYLOAD_SESSION_ID);
  });
});

// ---------------------------------------------------------------------------
describe("loadSessionScreen on the happy path", () => {
  it("is loading while the request is pending, then ready with the session — DoD-1", async () => {
    const pending = deferred<Response>();
    stubBackend(() => pending.promise);
    const state = new SessionScreenState(SESSION_ID);

    const running = loadSessionScreen(state);
    await flush();
    expect(state.status).toBe("loading");
    expect(state.session).toBeNull();

    pending.resolve(jsonResponse(LOADED, 200));
    await expect(running).resolves.toBeUndefined();
    expect(state.status).toBe("ready");
    expect(toJS(state.session)).toEqual(LOADED);
  });

  it("requests exactly GET /api/sessions/s1 and nothing else — DoD-1", async () => {
    const { calls } = stubBackend(() => jsonResponse(LOADED, 200));

    await expect(loadSessionScreen(new SessionScreenState(SESSION_ID))).resolves.toBeUndefined();

    expect(calls).toEqual([{ method: "GET", path: SESSION_PATH, search: "" }]);
  });

  it("keeps every id of the loaded row as the payload's own string — DoD-1", async () => {
    stubBackend(() => jsonResponse(LOADED, 200));
    const state = new SessionScreenState(SESSION_ID);

    await loadSessionScreen(state);

    expect(state.session?.id).toBe(PAYLOAD_SESSION_ID);
    expect(state.session?.character_id).toBe(PAYLOAD_CHARACTER_ID);
    expect(state.session?.setup_id).toBe(PAYLOAD_SETUP_ID);
  });

  it("shows loading again when it is re-run after a failure — DoD-1", async () => {
    const pending = deferred<Response>();
    stubBackend(() => pending.promise);
    const state = new SessionScreenState(SESSION_ID);
    runInAction(() => {
      state.status = "failed";
    });

    const running = loadSessionScreen(state);
    await flush();
    expect(state.status).toBe("loading");

    pending.resolve(jsonResponse(LOADED, 200));
    await expect(running).resolves.toBeUndefined();
    expect(state.status).toBe("ready");
  });
});

// ---------------------------------------------------------------------------
describe("loadSessionScreen's failures", () => {
  it("a 404 session_not_found is not-found, with no session and no rejection — DoD-1", async () => {
    stubBackend(() => notFound());
    const state = new SessionScreenState(SESSION_ID);

    await expect(loadSessionScreen(state)).resolves.toBeUndefined();

    expect(state.status).toBe("not-found");
    expect(state.session).toBeNull();
  });

  const FAILURES: FailureCase[] = [
    ["a 500 envelope", serverError],
    [
      "a transport failure",
      () => {
        throw new TypeError("Failed to fetch");
      },
    ],
  ];

  it.each(FAILURES)("%s is failed, with no session and no rejection — DoD-1", async (_label, answer) => {
    stubBackend(() => answer());
    const state = new SessionScreenState(SESSION_ID);

    await expect(loadSessionScreen(state)).resolves.toBeUndefined();

    expect(state.status).toBe("failed");
    expect(state.session).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("loadSessionScreen and its signal", () => {
  it("writes nothing once its signal aborts before the response settles — DoD-1", async () => {
    stubFetch(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          const signal = init?.signal;
          signal?.addEventListener("abort", () => {
            reject(signal.reason ?? new DOMException("The operation was aborted.", "AbortError"));
          });
        }),
    );
    const state = new SessionScreenState(SESSION_ID);
    const controller = new AbortController();

    const running = loadSessionScreen(state, controller.signal);
    await flush();
    const atAbort = snapshot(state);
    controller.abort();

    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(snapshot(state)).toEqual(atAbort);
  });
});
