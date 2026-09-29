// Feature 005, step 006 — the Users page's MobX store and its free functions
// (DoD-3, DoD-7, DoD-11, DoD-13, DoD-14, DoD-15, DoD-16, DoD-17 at the store level).
// The rendered page is covered in UsersPage.test.tsx; the confirm modal in
// tests/shared/ConfirmModal.test.tsx. DoD-18..DoD-21 are [manual/live].
//
// Expected behaviour comes from the step's Interface intent, 006.context.md and context.md D5
// and D16: a data class with observable fields only (rows, an explicit load status, an error
// message) and no methods or getters; loadUsers GETs /api/admin/users and early-returns on an
// aborted signal before writing; disableUser / enableUser POST the matching action route and
// then re-load — never optimistic; a failure lands in the error field and leaves the rows as
// they were. The frozen record says the three functions never reject.
import { readFileSync } from "node:fs";
import path from "node:path";
import { isComputedProp, isObservableProp, runInAction, toJS } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  type AdminUserRow,
  disableUser,
  enableUser,
  loadUsers,
  UsersPageState,
} from "../../src/admin/usersPageState";

const { notifyFailureSpy } = vi.hoisted(() => ({ notifyFailureSpy: vi.fn() }));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const STATE_SOURCE = path.join(FRONTEND_ROOT, "src", "admin", "usersPageState.ts");

const LIST_PATH = "/api/admin/users";
const ACTION_PATH = /^\/api\/admin\/users\/([^/]+)\/(disable|enable)$/;
const FAILURE_MESSAGE = "The account ledger is on fire zq-63.";
const BIG_ID = "9007199254740993"; // 2^53 + 1 — not representable as a JS number

const MIREILLE: AdminUserRow = {
  id: "7340032000000101",
  username: "mireille",
  role: "roleplayer",
  is_enabled: true,
  last_login_at: "2026-03-14T09:26:53.000000+00:00",
};
const ZORA: AdminUserRow = {
  id: "7340032000000102",
  username: "zora",
  role: "roleplayer",
  is_enabled: false,
  last_login_at: null,
};
const ANSELM: AdminUserRow = {
  id: "7340032000000103",
  username: "anselm",
  role: "admin",
  is_enabled: true,
  last_login_at: null,
};

beforeEach(() => {
  notifyFailureSpy.mockClear();
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

function failureResponse(): Response {
  return jsonResponse({ error: { code: "internal_error", message: FAILURE_MESSAGE, detail: {} } }, 500);
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

type Seen = { method: string; path: string; search: string };

function seen(mock: ReturnType<typeof stubFetch>): Seen[] {
  return mock.mock.calls.map(([input, init]) => {
    const url = requestUrl(input);
    return { method: requestMethod(input, init), path: url.pathname, search: url.search };
  });
}

function copyRows(rows: AdminUserRow[]): AdminUserRow[] {
  return rows.map((row) => ({ ...row }));
}

type Override = (method: string, path: string) => Promise<Response> | undefined;

/** A tiny in-memory backend for the three routes this store calls. */
function serveUsers(initial: AdminUserRow[], override?: Override) {
  const rows = copyRows(initial);
  const mock = stubFetch((input, init) => {
    const method = requestMethod(input, init);
    const pathname = requestUrl(input).pathname;
    const custom = override?.(method, pathname);
    if (custom !== undefined) return custom;
    if (method === "GET" && pathname === LIST_PATH) {
      return Promise.resolve(jsonResponse({ users: copyRows(rows) }, 200));
    }
    const match = ACTION_PATH.exec(pathname);
    if (method === "POST" && match !== null) {
      const row = rows.find((candidate) => candidate.id === match[1]);
      if (row === undefined) {
        return Promise.resolve(
          jsonResponse({ error: { code: "user_not_found", message: "That account does not exist.", detail: {} } }, 404),
        );
      }
      row.is_enabled = match[2] === "enable";
      return Promise.resolve(jsonResponse({ ...row }, 200));
    }
    return Promise.resolve(jsonResponse({ error: { code: "not_found", message: "no such route", detail: {} } }, 404));
  });
  return { mock, rows };
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

function snapshot(state: UsersPageState) {
  return { rows: toJS(state.rows), status: state.status, errorMessage: state.errorMessage };
}

function withRows(rows: AdminUserRow[]): UsersPageState {
  const state = new UsersPageState();
  runInAction(() => {
    state.rows = copyRows(rows);
    state.status = "ready";
  });
  return state;
}

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

function importSpecifiers(source: string): string[] {
  const pattern = /(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)["']([^"']+)["']/g;
  return Array.from(stripComments(source).matchAll(pattern), (m) => m[1]);
}

// ---------------------------------------------------------------------------
describe("the store is a data class with observable fields only", () => {
  it("the class prototype carries no method and no getter — DoD-16", () => {
    expect(Object.getOwnPropertyNames(UsersPageState.prototype)).toEqual(["constructor"]);
  });

  it("rows, status and errorMessage are the observable fields, and none is computed — DoD-16", () => {
    const state = new UsersPageState();
    const observed = Object.getOwnPropertyNames(state).filter((name) => isObservableProp(state, name));
    expect(observed.sort()).toEqual(["errorMessage", "rows", "status"]);
    for (const name of observed) {
      expect(isComputedProp(state, name), `field ${name}`).toBe(false);
    }
  });

  it("no own property of an instance is a function or a computed value — DoD-16", () => {
    const state = new UsersPageState();
    const record = state as unknown as Record<string, unknown>;
    for (const name of Object.getOwnPropertyNames(state)) {
      expect(typeof record[name], `own property ${name}`).not.toBe("function");
      expect(isComputedProp(state, name), `own property ${name}`).toBe(false);
    }
  });

  it("holds no modal open flag and no modal target — DoD-16", () => {
    const state = new UsersPageState();
    const names = Object.getOwnPropertyNames(state);
    expect(names.filter((name) => /open|modal|confirm|target|dialog/i.test(name))).toEqual([]);
  });

  it("a fresh store is idle, with no rows and no error — DoD-16", () => {
    const state = new UsersPageState();
    expect(snapshot(state)).toEqual({ rows: [], status: "idle", errorMessage: null });
  });

  it("the load and both mutations are free functions taking the store — DoD-16", () => {
    for (const fn of [loadUsers, disableUser, enableUser]) {
      expect(typeof fn).toBe("function");
    }
    expect(Object.getOwnPropertyNames(UsersPageState.prototype)).not.toContain("loadUsers");
  });
});

// ---------------------------------------------------------------------------
describe("loadUsers", () => {
  it("requests the admin users list exactly once, with no query — DoD-3", async () => {
    const { mock } = serveUsers([MIREILLE, ZORA, ANSELM]);
    await loadUsers(new UsersPageState());
    expect(seen(mock)).toEqual([{ method: "GET", path: LIST_PATH, search: "" }]);
  });

  it("the explicit status is loading while the request is in flight — DoD-3", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = new UsersPageState();
    const running = loadUsers(state);
    await flush();
    expect(state.status).toBe("loading");
    pending.resolve(jsonResponse({ users: copyRows([MIREILLE]) }, 200));
    await running;
    expect(state.status).toBe("ready");
  });

  it("a successful load writes the rows exactly as sent and becomes ready — DoD-3, DoD-4", async () => {
    serveUsers([MIREILLE, ZORA, ANSELM]);
    const state = new UsersPageState();
    await expect(loadUsers(state)).resolves.toBeUndefined();
    expect(snapshot(state)).toEqual({ rows: [MIREILLE, ZORA, ANSELM], status: "ready", errorMessage: null });
  });

  it("an empty list is ready with no rows — the status, not the rows, says it has loaded — DoD-3", async () => {
    serveUsers([]);
    const state = new UsersPageState();
    await loadUsers(state);
    expect(snapshot(state)).toEqual({ rows: [], status: "ready", errorMessage: null });
  });

  it("keeps the server's order — nothing is sorted — DoD-17", async () => {
    const rows: AdminUserRow[] = [
      { ...MIREILLE, id: "20" },
      { ...ZORA, id: "3" },
      { ...ANSELM, id: "100" },
    ];
    serveUsers(rows);
    const state = new UsersPageState();
    await loadUsers(state);
    expect(state.rows.map((row) => row.id)).toEqual(["20", "3", "100"]);
  });

  it("a failed load puts its message in the error field and does not reject — DoD-7", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    const state = new UsersPageState();
    await expect(loadUsers(state)).resolves.toBeUndefined();
    expect(state.errorMessage).toEqual(expect.stringContaining(FAILURE_MESSAGE));
    expect(state.rows).toEqual([]);
  });

  it("a transport failure also lands in the error field, as a non-empty message — DoD-7", async () => {
    stubFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    const state = new UsersPageState();
    await expect(loadUsers(state)).resolves.toBeUndefined();
    expect(typeof state.errorMessage).toBe("string");
    expect((state.errorMessage ?? "").length).toBeGreaterThan(0);
  });

  it("a failed load clears nothing already loaded — DoD-7", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    const state = withRows([MIREILLE, ZORA]);
    await loadUsers(state);
    expect(toJS(state.rows)).toEqual([MIREILLE, ZORA]);
    expect(state.errorMessage).toEqual(expect.stringContaining(FAILURE_MESSAGE));
  });
});

// ---------------------------------------------------------------------------
describe("disableUser", () => {
  it("posts to that account's disable route, then re-loads the list — DoD-11", async () => {
    const { mock } = serveUsers([MIREILLE, ZORA, ANSELM]);
    const state = withRows([MIREILLE, ZORA, ANSELM]);
    await expect(disableUser(state, MIREILLE.id)).resolves.toBeUndefined();

    const calls = seen(mock);
    expect(calls[0]).toEqual({ method: "POST", path: `${LIST_PATH}/${MIREILLE.id}/disable`, search: "" });
    expect(calls.slice(1)).toEqual([{ method: "GET", path: LIST_PATH, search: "" }]);
  });

  it("after the re-load the account's row is disabled and the others are unchanged — DoD-11", async () => {
    serveUsers([MIREILLE, ZORA, ANSELM]);
    const state = withRows([MIREILLE, ZORA, ANSELM]);
    await disableUser(state, MIREILLE.id);
    expect(toJS(state.rows)).toEqual([{ ...MIREILLE, is_enabled: false }, ZORA, ANSELM]);
    expect(state.errorMessage).toBeNull();
  });

  it("the rows come from the re-load — a change only the server knows appears — DoD-11", async () => {
    const newcomer: AdminUserRow = { ...ZORA, id: "7340032000000199", username: "newcomer", is_enabled: true };
    const { rows } = serveUsers([MIREILLE, ZORA]);
    const state = withRows([MIREILLE, ZORA]);
    rows.push({ ...newcomer });
    await disableUser(state, MIREILLE.id);
    expect(toJS(state.rows)).toEqual([{ ...MIREILLE, is_enabled: false }, ZORA, newcomer]);
  });

  it("is never optimistic: nothing is written while the post is in flight — DoD-11", async () => {
    const pending = deferred<Response>();
    serveUsers([MIREILLE, ZORA], (method) => (method === "POST" ? pending.promise : undefined));
    const state = withRows([MIREILLE, ZORA]);
    const before = snapshot(state);
    const running = disableUser(state, MIREILLE.id);
    await flush();
    expect(snapshot(state).rows).toEqual(before.rows);
    pending.resolve(jsonResponse({ ...MIREILLE, is_enabled: false }, 200));
    await running;
  });

  it("a failed disable lands in the error field and leaves the rows as they were — DoD-7", async () => {
    serveUsers([MIREILLE, ZORA], (method) => (method === "POST" ? Promise.resolve(failureResponse()) : undefined));
    const state = withRows([MIREILLE, ZORA]);
    await expect(disableUser(state, MIREILLE.id)).resolves.toBeUndefined();
    expect(state.errorMessage).toEqual(expect.stringContaining(FAILURE_MESSAGE));
    expect(toJS(state.rows)).toEqual([MIREILLE, ZORA]);
  });
});

// ---------------------------------------------------------------------------
describe("enableUser", () => {
  it("posts to that account's enable route, then re-loads the list — DoD-13", async () => {
    const { mock } = serveUsers([MIREILLE, ZORA, ANSELM]);
    const state = withRows([MIREILLE, ZORA, ANSELM]);
    await expect(enableUser(state, ZORA.id)).resolves.toBeUndefined();

    const calls = seen(mock);
    expect(calls[0]).toEqual({ method: "POST", path: `${LIST_PATH}/${ZORA.id}/enable`, search: "" });
    expect(calls.slice(1)).toEqual([{ method: "GET", path: LIST_PATH, search: "" }]);
  });

  it("after the re-load the account's row is enabled — DoD-13", async () => {
    serveUsers([MIREILLE, ZORA, ANSELM]);
    const state = withRows([MIREILLE, ZORA, ANSELM]);
    await enableUser(state, ZORA.id);
    expect(toJS(state.rows)).toEqual([MIREILLE, { ...ZORA, is_enabled: true }, ANSELM]);
  });

  it("a failed re-enable lands in the error field and leaves the rows as they were — DoD-7", async () => {
    serveUsers([MIREILLE, ZORA], (method) => (method === "POST" ? Promise.resolve(failureResponse()) : undefined));
    const state = withRows([MIREILLE, ZORA]);
    await expect(enableUser(state, ZORA.id)).resolves.toBeUndefined();
    expect(state.errorMessage).toEqual(expect.stringContaining(FAILURE_MESSAGE));
    expect(toJS(state.rows)).toEqual([MIREILLE, ZORA]);
  });
});

// ---------------------------------------------------------------------------
describe("ids are strings end to end", () => {
  it("an id beyond MAX_SAFE_INTEGER is posted verbatim and survives the re-load unchanged — DoD-17", async () => {
    const big: AdminUserRow = { ...MIREILLE, id: BIG_ID };
    const { mock } = serveUsers([big, ZORA]);
    const state = new UsersPageState();
    await loadUsers(state);
    expect(state.rows[0].id).toBe(BIG_ID);

    await disableUser(state, BIG_ID);
    const posts = seen(mock).filter((call) => call.method === "POST");
    expect(posts).toEqual([{ method: "POST", path: `${LIST_PATH}/${BIG_ID}/disable`, search: "" }]);
    expect(state.rows[0]).toEqual({ ...big, is_enabled: false });
    expect(typeof state.rows[0].id).toBe("string");
    expect(state.rows[0].id).toBe(BIG_ID);

    await enableUser(state, BIG_ID);
    expect(seen(mock).filter((call) => call.method === "POST").map((call) => call.path)).toEqual([
      `${LIST_PATH}/${BIG_ID}/disable`,
      `${LIST_PATH}/${BIG_ID}/enable`,
    ]);
    expect(state.rows[0]).toEqual(big);
  });

  it("the store module uses no parseInt and types no id as a number — DoD-17", () => {
    const source = stripComments(readFileSync(STATE_SOURCE, "utf8"));
    expect(source).not.toMatch(/\bparseInt\b/);
    expect(source).not.toMatch(/\b\w*(?:id|Id)\s*\??\s*:\s*number\b/);
  });
});

// ---------------------------------------------------------------------------
describe("an aborted load writes nothing", () => {
  it("a signal aborted mid-flight leaves the store exactly as it was at the abort — DoD-15", async () => {
    stubFetch(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          const signal = init?.signal;
          signal?.addEventListener("abort", () => {
            reject(signal.reason ?? new DOMException("The operation was aborted.", "AbortError"));
          });
        }),
    );
    const state = new UsersPageState();
    const controller = new AbortController();
    const running = loadUsers(state, controller.signal);
    await flush();
    const atAbort = snapshot(state);
    controller.abort();
    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(snapshot(state)).toEqual(atAbort);
    expect(state.errorMessage).toBeNull();
    expect(state.rows).toEqual([]);
  });

  it("a response arriving after the abort is not written — DoD-15", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = new UsersPageState();
    const controller = new AbortController();
    const running = loadUsers(state, controller.signal);
    await flush();
    const atAbort = snapshot(state);
    controller.abort();
    pending.resolve(jsonResponse({ users: copyRows([MIREILLE, ZORA]) }, 200));
    await running;
    await flush();
    expect(snapshot(state)).toEqual(atAbort);
    expect(state.rows).toEqual([]);
  });

  it("an already-aborted signal leaves a fresh store untouched — DoD-15", async () => {
    serveUsers([MIREILLE, ZORA]);
    const state = new UsersPageState();
    const controller = new AbortController();
    controller.abort();
    await expect(loadUsers(state, controller.signal)).resolves.toBeUndefined();
    await flush();
    expect(snapshot(state)).toEqual({ rows: [], status: "idle", errorMessage: null });
  });
});

// ---------------------------------------------------------------------------
describe("no notification from the store", () => {
  it.each<[string, (state: UsersPageState) => Promise<void>, boolean]>([
    ["a successful load", (state) => loadUsers(state), false],
    ["a failed load", (state) => loadUsers(state), true],
    ["a successful disable", (state) => disableUser(state, MIREILLE.id), false],
    ["a failed disable", (state) => disableUser(state, MIREILLE.id), true],
    ["a successful re-enable", (state) => enableUser(state, ZORA.id), false],
    ["a failed re-enable", (state) => enableUser(state, ZORA.id), true],
  ])("%s calls notifyFailure nowhere — DoD-14", async (_name, run, fails) => {
    serveUsers([MIREILLE, ZORA], () => (fails ? Promise.resolve(failureResponse()) : undefined));
    const state = withRows([MIREILLE, ZORA]);
    await run(state);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("the store module imports neither notifyFailure nor Mantine's notifications — DoD-14", () => {
    const offenders = importSpecifiers(readFileSync(STATE_SOURCE, "utf8")).filter((spec) =>
      /notifyFailure|@mantine\/notifications/.test(spec),
    );
    expect(offenders).toEqual([]);
  });
});
