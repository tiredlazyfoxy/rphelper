// Feature 015, step 008 — the session's chain state (DoD-1).
//
// Expected behaviour comes from the step file's Interface intent and DoD-1, 008.context.md
// ("Building the level states": one MemoLevelState per returned level, constructed from that
// level's scope and scope_id verbatim and populated with its notes, in the order received; no
// per-level listing request) and context.md D16 and the wire contract (the chain route and its
// `{ levels: [ { scope, scope_id, memos } ] }` answer, the user level's scope_id null).
//
// `fetch` is stubbed per test; requests are recorded by exact method + pathname + query string.
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Memo, MemoChainLevel, MemoScope } from "../../src/app/memosApi";
import { loadMemoChain, MemoChainState } from "../../src/app/memoChainState";
import { MemoLevelState } from "../../src/app/memoLevelState";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string };
type Handler = (request: Seen, init?: RequestInit) => Response | Promise<Response>;

const SESSION_ID = "s1";
const CHAIN_PATH = "/api/sessions/s1/memo-chain";

const CHARACTER_ID = "7250000000000000011";
const SETUP_ID = "7250000000000000021";
const SESSION_SCOPE_ID = "9007199254740993";

const STAMP = "2026-10-02T09:26:53.000000+00:00";

/** A wire Memo with all nine keys. */
function memo(id: string, scope: MemoScope, scopeId: string | null, body: string, overrides: Partial<Memo> = {}): Memo {
  return {
    id,
    scope,
    scope_id: scopeId,
    body,
    is_enabled: true,
    is_forced: false,
    sort_key: 0,
    created_at: STAMP,
    updated_at: STAMP,
    ...overrides,
  };
}

const USER_NOTES: Memo[] = [
  memo("7250000000000000201", "user", null, "Write in British English."),
  memo("7250000000000000202", "user", null, "Keep replies short.", { sort_key: 1, is_enabled: false }),
];
const CHARACTER_NOTES: Memo[] = [memo("7250000000000000203", "character", CHARACTER_ID, "Mira limps.")];
const SETUP_NOTES: Memo[] = [
  memo("7250000000000000204", "setup", SETUP_ID, "The tavern burned down.", { is_forced: true }),
];
const SESSION_NOTES: Memo[] = [
  memo("7250000000000000206", "session", SESSION_SCOPE_ID, "Tonight is the festival.", { sort_key: 0 }),
  memo("7250000000000000205", "session", SESSION_SCOPE_ID, "The bell rang twice.", { sort_key: 1 }),
];

const FOUR_LEVELS: MemoChainLevel[] = [
  { scope: "user", scope_id: null, memos: USER_NOTES },
  { scope: "character", scope_id: CHARACTER_ID, memos: CHARACTER_NOTES },
  { scope: "setup", scope_id: SETUP_ID, memos: SETUP_NOTES },
  { scope: "session", scope_id: SESSION_SCOPE_ID, memos: SESSION_NOTES },
];

const THREE_LEVELS: MemoChainLevel[] = [
  { scope: "user", scope_id: null, memos: USER_NOTES },
  { scope: "character", scope_id: CHARACTER_ID, memos: [] },
  { scope: "session", scope_id: SESSION_SCOPE_ID, memos: SESSION_NOTES },
];

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- fetch helpers
function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: "ql-77 went wrong.", detail: {} } }, status);
}

function notFoundResponse(): Response {
  return envelope("session_not_found", 404);
}

function serverError(): Response {
  return envelope("internal_error", 500);
}

function stubBackend(handler: Handler) {
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>(async (input, init) => {
    const url = requestUrl(input);
    const request: Seen = { method: requestMethod(input, init), path: url.pathname, search: url.search };
    calls.push(request);
    return handler(request, init);
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void };

function deferred<T>(): Deferred<T> {
  let resolve: (value: T) => void = () => undefined;
  const promise = new Promise<T>((ok) => {
    resolve = ok;
  });
  return { promise, resolve };
}

/** Every request is held open until the test resolves it, in request order. */
function stubHeld() {
  const held: Deferred<Response>[] = [];
  const backend = stubBackend(() => {
    const next = deferred<Response>();
    held.push(next);
    return next.promise;
  });
  return { ...backend, held };
}

/** Answers the chain GET of s1 with the given levels by exact path; 404s everything else. */
function serveChain(levels: MemoChainLevel[]) {
  return stubBackend((request) => {
    if (request.method === "GET" && request.path === CHAIN_PATH && request.search === "") {
      return jsonResponse({ levels }, 200);
    }
    return notFoundResponse();
  });
}

async function untilRequests(calls: Seen[], count: number): Promise<void> {
  await vi.waitFor(() => {
    expect(calls).toHaveLength(count);
  });
}

type LevelView = { scope: MemoScope; scopeId: string | null; memos: Memo[]; status: string };

function viewOf(state: MemoChainState): LevelView[] {
  return state.levels.map((level) => ({
    scope: level.scope,
    scopeId: level.scopeId,
    memos: level.memos.map((row) => ({ ...row })),
    status: level.status,
  }));
}

function expectedView(levels: MemoChainLevel[]): LevelView[] {
  return levels.map((level) => ({
    scope: level.scope,
    scopeId: level.scope_id,
    memos: level.memos.map((row) => ({ ...row })),
    status: "ready",
  }));
}

// ===========================================================================
describe("a fresh chain state", () => {
  it("has the session id, status idle and no levels — DoD-1", () => {
    const state = new MemoChainState(SESSION_ID);

    expect(state.sessionId).toBe(SESSION_ID);
    expect(state.status).toBe("idle");
    expect(state.levels).toEqual([]);
  });
});

// ===========================================================================
describe("loading the chain", () => {
  it("is loading while the request is pending, and requests exactly GET /api/sessions/s1/memo-chain — DoD-1", async () => {
    const { calls, held } = stubHeld();
    const state = new MemoChainState(SESSION_ID);

    const pending = loadMemoChain(state);
    await untilRequests(calls, 1);

    expect(state.status).toBe("loading");
    expect(calls).toEqual([{ method: "GET", path: CHAIN_PATH, search: "" }]);

    held[0].resolve(jsonResponse({ levels: FOUR_LEVELS }, 200));
    await expect(pending).resolves.toBeUndefined();
    expect(state.status).toBe("ready");
  });

  it("on success holds one ready level state per returned level, in the returned order, with scope, scopeId and notes — DoD-1", async () => {
    const { calls } = serveChain(FOUR_LEVELS);
    const state = new MemoChainState(SESSION_ID);

    await loadMemoChain(state);

    expect(state.status).toBe("ready");
    expect(state.levels).toHaveLength(4);
    for (const level of state.levels) {
      expect(level).toBeInstanceOf(MemoLevelState);
    }
    expect(viewOf(state)).toEqual(expectedView(FOUR_LEVELS));
    // The user level's scopeId is null; the others carry their id strings.
    expect(state.levels.map((level) => level.scopeId)).toEqual([null, CHARACTER_ID, SETUP_ID, SESSION_SCOPE_ID]);
    // One chain request and no per-level listing.
    expect(calls).toEqual([{ method: "GET", path: CHAIN_PATH, search: "" }]);
    expect(calls.filter((call) => call.path === "/api/memos" || call.path.startsWith("/api/memos/"))).toEqual([]);
  });

  it("a three-level chain (no setup) gives exactly three level states in the returned order, an empty level included — DoD-1", async () => {
    const { calls } = serveChain(THREE_LEVELS);
    const state = new MemoChainState(SESSION_ID);

    await loadMemoChain(state);

    expect(state.status).toBe("ready");
    expect(state.levels.map((level) => level.scope)).toEqual(["user", "character", "session"]);
    expect(viewOf(state)).toEqual(expectedView(THREE_LEVELS));
    expect(calls).toEqual([{ method: "GET", path: CHAIN_PATH, search: "" }]);
  });

  it("keeps the levels in the order received, not a client-side order — DoD-1", async () => {
    const received: MemoChainLevel[] = [
      { scope: "session", scope_id: SESSION_SCOPE_ID, memos: SESSION_NOTES },
      { scope: "user", scope_id: null, memos: USER_NOTES },
    ];
    serveChain(received);
    const state = new MemoChainState(SESSION_ID);

    await loadMemoChain(state);

    expect(viewOf(state)).toEqual(expectedView(received));
  });
});

// ===========================================================================
describe("a failed chain load", () => {
  it("a 500 sets failed and resolves without throwing — DoD-1", async () => {
    stubBackend(() => serverError());
    const state = new MemoChainState(SESSION_ID);

    await expect(loadMemoChain(state)).resolves.toBeUndefined();

    expect(state.status).toBe("failed");
    expect(state.levels).toEqual([]);
  });

  it("a transport failure sets failed and resolves without throwing — DoD-1", async () => {
    stubBackend(() => {
      throw new TypeError("Failed to fetch");
    });
    const state = new MemoChainState(SESSION_ID);

    await expect(loadMemoChain(state)).resolves.toBeUndefined();

    expect(state.status).toBe("failed");
  });

  it("a failure after a successful load keeps the levels already held — DoD-1", async () => {
    let fail = false;
    stubBackend((request) => {
      if (fail) return serverError();
      if (request.method === "GET" && request.path === CHAIN_PATH) return jsonResponse({ levels: FOUR_LEVELS }, 200);
      return notFoundResponse();
    });
    const state = new MemoChainState(SESSION_ID);
    await loadMemoChain(state);
    expect(state.status).toBe("ready");

    fail = true;
    await expect(loadMemoChain(state)).resolves.toBeUndefined();

    expect(state.status).toBe("failed");
    expect(viewOf(state)).toEqual(expectedView(FOUR_LEVELS));
  });
});

// ===========================================================================
describe("an aborted chain load writes nothing", () => {
  it("a signal aborted before the call leaves the state idle with no levels — DoD-1", async () => {
    serveChain(FOUR_LEVELS);
    const state = new MemoChainState(SESSION_ID);
    const controller = new AbortController();
    controller.abort();

    await expect(loadMemoChain(state, controller.signal)).resolves.toBeUndefined();

    expect(state.status).toBe("idle");
    expect(state.levels).toEqual([]);
  });

  it("aborting while pending, then the response arriving, writes no levels and no ready — DoD-1", async () => {
    const { calls, held } = stubHeld();
    const state = new MemoChainState(SESSION_ID);
    const controller = new AbortController();

    const pending = loadMemoChain(state, controller.signal);
    await untilRequests(calls, 1);
    controller.abort();
    held[0].resolve(jsonResponse({ levels: FOUR_LEVELS }, 200));

    await expect(pending).resolves.toBeUndefined();
    expect(state.levels).toEqual([]);
    expect(state.status).toBe("loading");
  });

  it("aborting while pending, with the request rejecting as aborted, writes no failure — DoD-1", async () => {
    stubBackend(
      (_request, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("The operation was aborted.", "AbortError"));
          });
        }),
    );
    const state = new MemoChainState(SESSION_ID);
    const controller = new AbortController();

    const pending = loadMemoChain(state, controller.signal);
    await vi.waitFor(() => {
      expect(state.status).toBe("loading");
    });
    controller.abort();

    await expect(pending).resolves.toBeUndefined();
    expect(state.levels).toEqual([]);
    expect(state.status).toBe("loading");
  });
});
