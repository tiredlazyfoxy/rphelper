// Fast feature 002 — vector-index-rebuild: the admin Database page's store half — the three
// rebuild fields and the `rebuildIndex` free function (DoD-15, DoD-16). The page half lives in
// `DatabasePage.rebuild.test.tsx` (DoD-17..DoD-20). Backend DoD-1..DoD-14 live in
// `backend/tests/test_admin_db_rebuild.py`; DoD-21 is [manual/live] and carries no test.
//
// Expected behaviour comes from `docs/plans/fast/002.vector-index-rebuild/plan.md` (Interface
// intent "Rebuild fields" and "`rebuildIndex`", DoD-15, DoD-16) and `context.md` (free functions
// never reject, mutate inside `runInAction`, use `failureMessageOf` and `apiPost`). Bindings come
// from the frozen `## Skeleton` record:
// - `DatabaseRebuildStatus = "idle" | "rebuilding"`;
// - `DatabasePageState` fields `rebuildStatus`, `rebuildErrorMessage`, `rebuildComplete`;
// - `DATABASE_REBUILD_PATH` and `rebuildIndex(state, signal?)` from `src/admin/databasePageState`.
//
// `fetch` is stubbed and routed by method + exact pathname, so the effect is observed at the wire
// without assuming anything about how `apiPost` builds its request.
import { runInAction } from "mobx";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DATABASE_REBUILD_PATH,
  type DatabaseRebuildStatus,
  DatabasePageState,
  rebuildIndex,
} from "../../src/admin/databasePageState";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string };

/** plan.md — the route. */
const REBUILD_PATH = "/api/admin/database/rebuild";
/** plan.md "Rebuild report model" — the 200 body. */
const REPORT = { tables_rebuilt: ["memo_vec", "session_vec", "memo_fts", "message_fts"] };

const NO_MODEL_MESSAGE = "No embedding model is designated (zq-58 marker).";

/** The other operations' slots, seeded so "untouched" is observable. */
const DRIFT_ERROR = "The drift report is on fire (zq-33 marker).";
const IMPORT_ERROR = "A previous import failed (zq-71 marker).";
const EXPORT_ERROR = "The export could not be produced (zq-44 marker).";
const STALE_REBUILD_ERROR = "A previous rebuild failed (zq-90 marker).";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- helpers

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function settle(rounds = 4): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await new Promise<void>((resolve) => setImmediate(resolve));
  }
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function errorEnvelope(code: string, message: string, status: number): Response {
  return jsonResponse({ error: { code, message, detail: {} } }, status);
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

/** Stub `fetch`; the answer for the rebuild route comes from `answer`. */
function serve(answer: () => Promise<Response>) {
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>((input, init) => {
    const url = requestUrl(input);
    const method = requestMethod(input, init);
    calls.push({ method, path: url.pathname });
    if (method === "POST" && url.pathname === REBUILD_PATH) return answer();
    return Promise.resolve(errorEnvelope("not_found", `unexpected ${method} ${url.pathname}`, 404));
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

function withOtherSlots(): DatabasePageState {
  const state = new DatabasePageState();
  runInAction(() => {
    state.errorMessage = DRIFT_ERROR;
    state.importErrorMessage = IMPORT_ERROR;
    state.exportErrorMessage = EXPORT_ERROR;
  });
  return state;
}

// ---------------------------------------------------------------- success

describe("rebuildIndex on a 200", () => {
  it("POSTs exactly the rebuild route, once — DoD-15", async () => {
    const { calls } = serve(() => Promise.resolve(jsonResponse(REPORT, 200)));
    const state = new DatabasePageState();

    await rebuildIndex(state);

    expect(calls).toEqual([{ method: "POST", path: REBUILD_PATH }]);
    expect(DATABASE_REBUILD_PATH).toBe(REBUILD_PATH);
  });

  it("sets completion, leaves the error slot null and ends idle — DoD-15", async () => {
    serve(() => Promise.resolve(jsonResponse(REPORT, 200)));
    const state = new DatabasePageState();
    runInAction(() => {
      state.rebuildErrorMessage = STALE_REBUILD_ERROR;
    });

    await rebuildIndex(state);

    expect(state.rebuildComplete).toBe(true);
    expect(state.rebuildErrorMessage).toBeNull();
    expect(state.rebuildStatus).toBe("idle");
  });

  it("is rebuilding with completion and error cleared while the request is in flight — DoD-15", async () => {
    const pending = deferred<Response>();
    serve(() => pending.promise);
    const state = new DatabasePageState();
    runInAction(() => {
      state.rebuildComplete = true;
      state.rebuildErrorMessage = STALE_REBUILD_ERROR;
    });

    const running = rebuildIndex(state);
    await settle();

    const during: DatabaseRebuildStatus = state.rebuildStatus;
    expect(during).toBe("rebuilding");
    expect(state.rebuildComplete).toBe(false);
    expect(state.rebuildErrorMessage).toBeNull();

    pending.resolve(jsonResponse(REPORT, 200));
    await running;
    expect(state.rebuildStatus).toBe("idle");
    expect(state.rebuildComplete).toBe(true);
  });

  it("leaves the drift report, import and export slots untouched — DoD-15", async () => {
    serve(() => Promise.resolve(jsonResponse(REPORT, 200)));
    const state = withOtherSlots();

    await rebuildIndex(state);

    expect(state.rebuildComplete).toBe(true);
    expect(state.errorMessage).toBe(DRIFT_ERROR);
    expect(state.importErrorMessage).toBe(IMPORT_ERROR);
    expect(state.exportErrorMessage).toBe(EXPORT_ERROR);
  });
});

// ---------------------------------------------------------------- failure

const FAILURES: [string, () => Promise<Response>][] = [
  [
    "a 409 no_embedding_model",
    () => Promise.resolve(errorEnvelope("no_embedding_model", NO_MODEL_MESSAGE, 409)),
  ],
  ["a network failure", () => Promise.reject(new TypeError("Failed to fetch"))],
];

describe("rebuildIndex on a failure", () => {
  it.each(FAILURES)(
    "on %s stores a non-empty message, leaves completion false, ends idle and does not reject — DoD-16",
    async (_label, answer) => {
      const { calls } = serve(answer);
      const state = new DatabasePageState();

      await expect(rebuildIndex(state)).resolves.toBeUndefined();

      expect(calls.filter((call) => call.method === "POST" && call.path === REBUILD_PATH)).toHaveLength(1);
      expect(typeof state.rebuildErrorMessage).toBe("string");
      expect((state.rebuildErrorMessage ?? "").trim()).not.toBe("");
      expect(state.rebuildComplete).toBe(false);
      expect(state.rebuildStatus).toBe("idle");
    },
  );

  it.each(FAILURES)(
    "on %s leaves the drift report, import and export error slots untouched — DoD-16",
    async (_label, answer) => {
      serve(answer);
      const state = withOtherSlots();

      await rebuildIndex(state);

      // The rebuild's own slot took the failure, so no other slot did.
      expect((state.rebuildErrorMessage ?? "").trim()).not.toBe("");
      expect(state.errorMessage).toBe(DRIFT_ERROR);
      expect(state.importErrorMessage).toBe(IMPORT_ERROR);
      expect(state.exportErrorMessage).toBe(EXPORT_ERROR);
    },
  );

  it("a failure after an earlier success clears the earlier completion — DoD-16", async () => {
    serve(() => Promise.resolve(errorEnvelope("no_embedding_model", NO_MODEL_MESSAGE, 409)));
    const state = new DatabasePageState();
    runInAction(() => {
      state.rebuildComplete = true;
    });

    await rebuildIndex(state);

    expect(state.rebuildComplete).toBe(false);
    expect((state.rebuildErrorMessage ?? "").trim()).not.toBe("");
  });
});
