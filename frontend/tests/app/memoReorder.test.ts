// Feature 016, step 004 — the drop decision and the drop effect (DoD-1..DoD-6).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 004.context.md (level keys are the scope; the decision is pure and testable with plain
// arrays; the effect is testable with level states and a stubbed fetch) and context.md: D7
// (optimistic reorder, the in-flight guard), D8 (the pure decision, cross-level refusal in the
// handler), the wire contract for PUT /api/memos/order and the strings table.
//
// Recognition conventions (for the verifier):
// - The decision is bound to the frozen `decideMemoDrop(levels, activeId, overId)`; its input
//   is built literally as `{ key, ids }` per level, the over id absent is `null`.
// - The effect is bound to the frozen `applyMemoDrop(levelStates, activeId, overId)`; level
//   states are built with `new MemoLevelState(scope, scopeId)` + `populateMemoLevel`.
// - `fetch` is stubbed per test; requests are recorded by exact method + pathname + query
//   string with the parsed JSON body. PUT /api/memos/order is held open where a test needs to
//   observe the in-flight window.
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Memo, MemoScope } from "../../src/app/memosApi";
import {
  isReorderInFlight,
  MemoLevelState,
  populateMemoLevel,
  reorderFailure,
} from "../../src/app/memoLevelState";
import { applyMemoDrop, decideMemoDrop, type MemoDropLevel } from "../../src/app/memoReorder";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string; body: unknown };
type Handler = (request: Seen) => Response | Promise<Response>;

const ORDER_PATH = "/api/memos/order";
const REORDER_FAILURE = "Could not reorder the notes.";

const CHARACTER_ID = "7250000000000000011";
const SESSION_ID = "9007199254740993";

const STAMP = "2026-10-02T09:26:53.000000+00:00";

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

function parseBody(init?: RequestInit): unknown {
  const raw = init?.body;
  if (raw === undefined || raw === null) return undefined;
  return JSON.parse(String(raw)) as unknown;
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

function stubBackend(handler: Handler) {
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>(async (input, init) => {
    const url = requestUrl(input);
    const request: Seen = {
      method: requestMethod(input, init),
      path: url.pathname,
      search: url.search,
      body: parseBody(init),
    };
    calls.push(request);
    return handler(request);
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

function isOrderPut(request: Seen): boolean {
  return request.method === "PUT" && request.path === ORDER_PATH && request.search === "";
}

/** Every PUT /api/memos/order is held open (one deferred per PUT); anything else is a 404. */
function stubHeldOrder() {
  const puts: Deferred<Response>[] = [];
  const backend = stubBackend((request) => {
    if (isOrderPut(request)) {
      const next = deferred<Response>();
      puts.push(next);
      return next.promise;
    }
    return envelope("memo_not_found", 404);
  });
  return { ...backend, puts };
}

async function flush(): Promise<void> {
  for (let round = 0; round < 6; round += 1) await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
  for (let round = 0; round < 6; round += 1) await Promise.resolve();
}

// ---------------------------------------------------------------- level-state fixtures
function memo(id: string, scope: MemoScope, scopeId: string | null, sortKey: number): Memo {
  return {
    id,
    scope,
    scope_id: scopeId,
    body: `Body of ${id}`,
    is_enabled: true,
    is_forced: false,
    sort_key: sortKey,
    created_at: STAMP,
    updated_at: STAMP,
  };
}

function level(scope: MemoScope, scopeId: string | null, ids: string[]): MemoLevelState {
  const state = new MemoLevelState(scope, scopeId);
  populateMemoLevel(
    state,
    ids.map((id, index) => memo(id, scope, scopeId, index)),
  );
  return state;
}

/** Level states for user [u1, u2], character [c1, c2, c3] and session [s1]. */
function chainStates() {
  const user = level("user", null, ["u1", "u2"]);
  const character = level("character", CHARACTER_ID, ["c1", "c2", "c3"]);
  const session = level("session", SESSION_ID, ["s1"]);
  return { user, character, session, all: [user, character, session] as const };
}

function ids(state: MemoLevelState): string[] {
  return state.memos.map((row) => row.id);
}

/** A plain copy of a level's rows, for "untouched" comparisons. */
function snapshot(state: MemoLevelState): Memo[] {
  return state.memos.map((row) => ({ ...row }));
}

// ---------------------------------------------------------------- decision fixtures
function decisionLevels(): MemoDropLevel[] {
  return [
    { key: "user", ids: ["u1", "u2"] },
    { key: "character", ids: ["c1", "c2", "c3"] },
    { key: "session", ids: ["s1"] },
  ];
}

// ===========================================================================
describe("decideMemoDrop — same level (UC-076, US-102)", () => {
  it("active c1 over c3 returns the character level with c2, c3, c1 — DoD-1", () => {
    expect(decideMemoDrop(decisionLevels(), "c1", "c3")).toEqual({
      key: "character",
      ids: ["c2", "c3", "c1"],
    });
  });

  it("active c3 over c1 returns the character level with c3, c1, c2 — DoD-1", () => {
    expect(decideMemoDrop(decisionLevels(), "c3", "c1")).toEqual({
      key: "character",
      ids: ["c3", "c1", "c2"],
    });
  });
});

// ===========================================================================
describe("decideMemoDrop — cross-level refusal (US-103.AC-2)", () => {
  it.each([
    ["c1", "u2"],
    ["u1", "s1"],
    ["s1", "c2"],
  ])("active %s over %s returns null — DoD-2", (activeId, overId) => {
    expect(decideMemoDrop(decisionLevels(), activeId, overId)).toBeNull();
  });
});

// ===========================================================================
describe("decideMemoDrop — other refusals and purity", () => {
  it("an absent over id returns null — DoD-3", () => {
    expect(decideMemoDrop(decisionLevels(), "c1", null)).toBeNull();
  });

  it("active equal to over returns null — DoD-3", () => {
    expect(decideMemoDrop(decisionLevels(), "c2", "c2")).toBeNull();
  });

  it("an active id found in no level returns null — DoD-3", () => {
    expect(decideMemoDrop(decisionLevels(), "x9", "c1")).toBeNull();
  });

  it("an over id found in no level returns null — DoD-3", () => {
    expect(decideMemoDrop(decisionLevels(), "c1", "x9")).toBeNull();
  });

  it("its inputs are not mutated, by an accepted drop or by any refused one — DoD-3", () => {
    const levels = decisionLevels();
    const before = decisionLevels();

    decideMemoDrop(levels, "c1", "c3");
    expect(levels).toEqual(before);
    decideMemoDrop(levels, "c3", "c1");
    expect(levels).toEqual(before);
    decideMemoDrop(levels, "c1", "u2");
    decideMemoDrop(levels, "c1", null);
    decideMemoDrop(levels, "c2", "c2");
    decideMemoDrop(levels, "x9", "c1");
    decideMemoDrop(levels, "c1", "x9");
    expect(levels).toEqual(before);
  });
});

// ===========================================================================
describe("applyMemoDrop — cross-level (US-103.AC-2, refused in the handler)", () => {
  it("a character note dropped over a user note sends no request and leaves every level's order unchanged — DoD-4", async () => {
    const { calls } = stubHeldOrder();
    const { user, character, session, all } = chainStates();
    const before = all.map(snapshot);

    await applyMemoDrop(all, "c1", "u2");
    await flush();

    expect(calls).toEqual([]);
    expect(ids(user)).toEqual(["u1", "u2"]);
    expect(ids(character)).toEqual(["c1", "c2", "c3"]);
    expect(ids(session)).toEqual(["s1"]);
    expect(all.map(snapshot)).toEqual(before);
    for (const state of all) expect(isReorderInFlight(state)).toBe(false);
  });

  it.each([
    ["c3", "u1"],
    ["u1", "s1"],
    ["s1", "c2"],
  ])("active %s over %s (another level) sends no request and changes no order — DoD-4", async (activeId, overId) => {
    const { calls } = stubHeldOrder();
    const { all } = chainStates();
    const before = all.map(snapshot);

    await applyMemoDrop(all, activeId, overId);
    await flush();

    expect(calls).toEqual([]);
    expect(all.map(snapshot)).toEqual(before);
  });
});

// ===========================================================================
describe("applyMemoDrop — same level (UC-076, US-102, D7)", () => {
  it("c1 over c3 orders the character level c2, c3, c1 at once and sends exactly one PUT /api/memos/order with string ids; other levels untouched — DoD-5", async () => {
    const { calls, puts } = stubHeldOrder();
    const { user, character, session, all } = chainStates();
    const userBefore = snapshot(user);
    const sessionBefore = snapshot(session);

    const pending = applyMemoDrop(all, "c1", "c3");
    await vi.waitFor(() => {
      expect(calls).toHaveLength(1);
    });

    // Before the response: the dropped order already shows (optimistic, D7).
    expect(ids(character)).toEqual(["c2", "c3", "c1"]);
    expect(calls[0].method).toBe("PUT");
    expect(calls[0].path).toBe(ORDER_PATH);
    expect(calls[0].search).toBe("");
    expect(calls[0].body).toStrictEqual({
      scope: "character",
      scope_id: CHARACTER_ID,
      memo_ids: ["c2", "c3", "c1"],
    });
    expect(snapshot(user)).toEqual(userBefore);
    expect(snapshot(session)).toEqual(sessionBefore);

    puts[0].resolve(
      jsonResponse(
        {
          memos: [
            memo("c2", "character", CHARACTER_ID, 0),
            memo("c3", "character", CHARACTER_ID, 1),
            memo("c1", "character", CHARACTER_ID, 2),
          ],
        },
        200,
      ),
    );
    await pending;
    await flush();

    expect(ids(character)).toEqual(["c2", "c3", "c1"]);
    expect(calls.filter(isOrderPut)).toHaveLength(1);
    expect(calls).toHaveLength(1);
    expect(snapshot(user)).toEqual(userBefore);
    expect(snapshot(session)).toEqual(sessionBefore);
    expect(reorderFailure(character)).toBeNull();
  });

  it("the drop effect resolves (never rejects) when the PUT fails — DoD-5", async () => {
    stubBackend((request) => (isOrderPut(request) ? envelope("internal_error", 500) : envelope("memo_not_found", 404)));
    const { all } = chainStates();

    await expect(applyMemoDrop(all, "c1", "c3")).resolves.toBeUndefined();
  });
});

// ===========================================================================
describe("applyMemoDrop — in flight and refused drops (D7, D8)", () => {
  it("while the character level's reorder is in flight, another drop in that level sends nothing more — DoD-6", async () => {
    const { calls, puts } = stubHeldOrder();
    const { character, all } = chainStates();

    const first = applyMemoDrop(all, "c1", "c3");
    await vi.waitFor(() => {
      expect(calls).toHaveLength(1);
    });
    expect(isReorderInFlight(character)).toBe(true);

    await applyMemoDrop(all, "c2", "c1");
    await applyMemoDrop(all, "c3", "c2");
    await flush();
    expect(calls).toHaveLength(1);

    puts[0].resolve(
      jsonResponse(
        {
          memos: [
            memo("c2", "character", CHARACTER_ID, 0),
            memo("c3", "character", CHARACTER_ID, 1),
            memo("c1", "character", CHARACTER_ID, 2),
          ],
        },
        200,
      ),
    );
    await first;
    await flush();
    expect(calls).toHaveLength(1);
  });

  it("a refused drop leaves a level's reorder failure exactly as it was, set or null — DoD-6", async () => {
    stubBackend((request) => (isOrderPut(request) ? envelope("internal_error", 500) : envelope("memo_not_found", 404)));
    const { user, character, session, all } = chainStates();

    // A failed reorder in the character level sets its failure text.
    await applyMemoDrop(all, "c1", "c3");
    await flush();
    expect(reorderFailure(character)).toBe(REORDER_FAILURE);
    expect(reorderFailure(user)).toBeNull();
    expect(reorderFailure(session)).toBeNull();

    // Refused drops of every kind: cross-level, absent over, same id, unknown ids.
    const refused: [string, string | null][] = [
      ["c1", "u2"],
      ["u1", "c2"],
      ["c2", null],
      ["c2", "c2"],
      ["x9", "c1"],
      ["c1", "x9"],
      ["s1", "u1"],
    ];
    for (const [activeId, overId] of refused) {
      await applyMemoDrop(all, activeId, overId);
      await flush();
      expect(reorderFailure(character)).toBe(REORDER_FAILURE);
      expect(reorderFailure(user)).toBeNull();
      expect(reorderFailure(session)).toBeNull();
    }
  });
});
