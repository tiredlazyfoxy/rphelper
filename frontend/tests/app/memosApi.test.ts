// Feature 015, step 005 — the memos API client (DoD-1..DoD-7).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 005.context.md and context.md's "Wire contract — memos", D5 (mutations take no signal),
// D6 (a PATCH carries exactly the supplied keys) and the "Ids are strings" constraint.
// Requests are matched by exact pathname plus query string plus method, never by prefix.
// Every id used here is beyond Number.MAX_SAFE_INTEGER, so a silent numeric coercion would
// change it. Failures are the shared client's ApiErrors, rethrown unchanged.
import { afterEach, describe, expect, it, vi } from "vitest";
import { isApiError } from "../../src/shared/apiError";
import {
  createMemo,
  deleteMemo,
  fetchMemoChain,
  fetchMemos,
  type Memo,
  type MemoChainLevel,
  type MemoScope,
  reorderMemos,
  updateMemo,
} from "../../src/app/memosApi";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const CHARACTER_ID = "7250000000000000001";
const SETUP_ID = "7250000000000000003";
const SESSION_ID = "7250000000000000005";
const OTHER_SESSION_ID = "7250000000000000009";
const MEMO_ID = "7250000000000000201";
const OTHER_MEMO_ID = "7250000000000000202";
const THIRD_MEMO_ID = "7250000000000000203";
const FOURTH_MEMO_ID = "7250000000000000204";

const MEMO_PATH = `/api/memos/${MEMO_ID}`;

const STAMP = "2026-10-02T09:26:53.000000+00:00";
const LATER_STAMP = "2026-10-02T09:30:00.000000+00:00";

/** A wire Memo with all nine keys; scope_id null exactly for the user level. */
function memo(id: string, scope: MemoScope, scopeOf: string | null, overrides: Partial<Memo> = {}): Memo {
  return {
    id,
    scope,
    scope_id: scopeOf,
    body: "# Standing note\n\nKeep the tone dry.",
    is_enabled: true,
    is_forced: false,
    sort_key: 0,
    created_at: STAMP,
    updated_at: STAMP,
    ...overrides,
  };
}

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

function serve(body: unknown, status = 200) {
  return stubFetch(() => Promise.resolve(jsonResponse(body, status)));
}

function serveNoContent() {
  return stubFetch(() => Promise.resolve(new Response(null, { status: 204 })));
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

/** The JSON body of the n-th request, or undefined when none was sent. */
function sentBody(mock: ReturnType<typeof stubFetch>, index = 0): unknown {
  const raw = mock.mock.calls[index]?.[1]?.body;
  if (raw === undefined || raw === null) return undefined;
  return typeof raw === "string" ? (JSON.parse(raw) as unknown) : raw;
}

function bodyKeys(mock: ReturnType<typeof stubFetch>, index = 0): string[] {
  const body = sentBody(mock, index);
  return body === undefined ? [] : Object.keys(body as object);
}

/** The signal fetch was handed on the n-th call (undefined when none). */
function sentSignal(mock: ReturnType<typeof stubFetch>, index = 0): AbortSignal | null | undefined {
  const [input, init] = mock.mock.calls[index] ?? [];
  if (init?.signal !== undefined) return init.signal;
  return input instanceof Request ? input.signal : undefined;
}

function envelope(code: string, message: string): unknown {
  return { error: { code, message, detail: {} } };
}

/** The rejection of a call that must not resolve. */
async function rejection(call: () => Promise<unknown>): Promise<unknown> {
  return call().then(
    () => {
      throw new Error("the call resolved, but the route answered an error");
    },
    (reason: unknown) => reason,
  );
}

// ---------------------------------------------------------------------------
describe("fetchMemos", () => {
  it("requests exactly GET /api/memos?scope=user with no scope_id for the user level — DoD-1", async () => {
    const mock = serve({ memos: [] });
    await fetchMemos("user", null);
    expect(seen(mock)).toEqual([{ method: "GET", path: "/api/memos", search: "?scope=user" }]);
  });

  it("requests exactly GET /api/memos?scope=character&scope_id=<id> for a character — DoD-1", async () => {
    const mock = serve({ memos: [] });
    await fetchMemos("character", CHARACTER_ID);
    expect(seen(mock)).toEqual([
      { method: "GET", path: "/api/memos", search: `?scope=character&scope_id=${CHARACTER_ID}` },
    ]);
  });

  it("requests exactly GET /api/memos?scope=setup&scope_id=<id> for a setup — DoD-1", async () => {
    const mock = serve({ memos: [] });
    await fetchMemos("setup", SETUP_ID);
    expect(seen(mock)).toEqual([
      { method: "GET", path: "/api/memos", search: `?scope=setup&scope_id=${SETUP_ID}` },
    ]);
  });

  it("requests exactly GET /api/memos?scope=session&scope_id=<id> for a session — DoD-1", async () => {
    const mock = serve({ memos: [] });
    await fetchMemos("session", SESSION_ID);
    expect(seen(mock)).toEqual([
      { method: "GET", path: "/api/memos", search: `?scope=session&scope_id=${SESSION_ID}` },
    ]);
  });

  it("resolves to the payload's memos array, unwrapped and in the payload's order — DoD-1", async () => {
    const first = memo(MEMO_ID, "character", CHARACTER_ID, { sort_key: 0 });
    const second = memo(OTHER_MEMO_ID, "character", CHARACTER_ID, {
      sort_key: 1,
      is_enabled: false,
      is_forced: true,
    });
    serve({ memos: [first, second] });
    await expect(fetchMemos("character", CHARACTER_ID)).resolves.toEqual([first, second]);
  });

  it("resolves to an empty array for an empty level — DoD-1", async () => {
    serve({ memos: [] });
    await expect(fetchMemos("session", SESSION_ID)).resolves.toEqual([]);
  });

  it("keeps every id and scope_id the identical string the payload carried, past MAX_SAFE_INTEGER — DoD-1", async () => {
    const rows = [
      memo(MEMO_ID, "setup", SETUP_ID),
      memo(OTHER_MEMO_ID, "setup", SETUP_ID, { sort_key: 1 }),
    ];
    serve({ memos: rows });
    const got = await fetchMemos("setup", SETUP_ID);
    expect(got.map((row) => row.id)).toEqual([MEMO_ID, OTHER_MEMO_ID]);
    expect(got.map((row) => row.scope_id)).toEqual([SETUP_ID, SETUP_ID]);
    expect(typeof got[0].id).toBe("string");
    expect(typeof got[0].scope_id).toBe("string");
  });

  it("keeps a user-level note's null scope_id as null — DoD-1", async () => {
    serve({ memos: [memo(MEMO_ID, "user", null)] });
    const got = await fetchMemos("user", null);
    expect(got).toHaveLength(1);
    expect(got[0].id).toBe(MEMO_ID);
    expect(got[0].scope_id).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("createMemo", () => {
  it("POSTs /api/memos with exactly { scope, scope_id, body } for a session and resolves to the created Memo — DoD-2", async () => {
    const created = memo(MEMO_ID, "session", OTHER_SESSION_ID, { body: "  # h\n" });
    const mock = serve(created, 201);
    await expect(createMemo("session", OTHER_SESSION_ID, "  # h\n")).resolves.toEqual(created);
    expect(seen(mock)).toEqual([{ method: "POST", path: "/api/memos", search: "" }]);
    expect(sentBody(mock)).toEqual({
      scope: "session",
      scope_id: OTHER_SESSION_ID,
      body: "  # h\n",
    });
    expect(bodyKeys(mock).sort()).toEqual(["body", "scope", "scope_id"]);
  });

  it("POSTs exactly { scope: user, scope_id: null, body } for the user level and resolves to the created Memo — DoD-2", async () => {
    const created = memo(MEMO_ID, "user", null, { body: "x" });
    const mock = serve(created, 201);
    await expect(createMemo("user", null, "x")).resolves.toEqual(created);
    expect(seen(mock)).toEqual([{ method: "POST", path: "/api/memos", search: "" }]);
    expect(sentBody(mock)).toEqual({ scope: "user", scope_id: null, body: "x" });
    expect(bodyKeys(mock).sort()).toEqual(["body", "scope", "scope_id"]);
  });

  it("never sends is_enabled, is_forced or sort_key — DoD-2", async () => {
    for (const call of [
      () => createMemo("session", OTHER_SESSION_ID, "  # h\n"),
      () => createMemo("user", null, "x"),
      () => createMemo("character", CHARACTER_ID, "y"),
      () => createMemo("setup", SETUP_ID, "z"),
    ]) {
      const mock = serve(memo(MEMO_ID, "user", null), 201);
      await call();
      const keys = bodyKeys(mock);
      expect(keys).not.toContain("is_enabled");
      expect(keys).not.toContain("is_forced");
      expect(keys).not.toContain("sort_key");
      vi.unstubAllGlobals();
    }
  });

  it("sends the body verbatim, whitespace included — DoD-2", async () => {
    const mock = serve(memo(MEMO_ID, "session", OTHER_SESSION_ID, { body: "  # h\n" }), 201);
    await createMemo("session", OTHER_SESSION_ID, "  # h\n");
    expect((sentBody(mock) as { body: unknown }).body).toBe("  # h\n");
  });
});

// ---------------------------------------------------------------------------
describe("updateMemo", () => {
  it("PATCHes /api/memos/<id> with exactly { is_enabled: false } — no is_forced key — DoD-3", async () => {
    const updated = memo(MEMO_ID, "character", CHARACTER_ID, {
      is_enabled: false,
      is_forced: true,
      updated_at: LATER_STAMP,
    });
    const mock = serve(updated);
    await expect(updateMemo(MEMO_ID, { is_enabled: false })).resolves.toEqual(updated);
    expect(seen(mock)).toEqual([{ method: "PATCH", path: MEMO_PATH, search: "" }]);
    expect(sentBody(mock)).toEqual({ is_enabled: false });
    expect(bodyKeys(mock)).toEqual(["is_enabled"]);
  });

  it("PATCHes exactly { is_forced: true } for the forced toggle — DoD-3", async () => {
    const updated = memo(MEMO_ID, "character", CHARACTER_ID, {
      is_forced: true,
      updated_at: LATER_STAMP,
    });
    const mock = serve(updated);
    await expect(updateMemo(MEMO_ID, { is_forced: true })).resolves.toEqual(updated);
    expect(seen(mock)).toEqual([{ method: "PATCH", path: MEMO_PATH, search: "" }]);
    expect(sentBody(mock)).toEqual({ is_forced: true });
    expect(bodyKeys(mock)).toEqual(["is_forced"]);
  });

  it("PATCHes exactly { body: \"y\" } for a body edit — DoD-3", async () => {
    const updated = memo(MEMO_ID, "character", CHARACTER_ID, { body: "y", updated_at: LATER_STAMP });
    const mock = serve(updated);
    await expect(updateMemo(MEMO_ID, { body: "y" })).resolves.toEqual(updated);
    expect(seen(mock)).toEqual([{ method: "PATCH", path: MEMO_PATH, search: "" }]);
    expect(sentBody(mock)).toEqual({ body: "y" });
    expect(bodyKeys(mock)).toEqual(["body"]);
  });

  it("addresses the memo id verbatim, past MAX_SAFE_INTEGER — DoD-3", async () => {
    const mock = serve(memo(OTHER_MEMO_ID, "user", null));
    await updateMemo(OTHER_MEMO_ID, { is_enabled: true });
    expect(seen(mock)[0].path).toBe(`/api/memos/${OTHER_MEMO_ID}`);
  });
});

// ---------------------------------------------------------------------------
describe("deleteMemo", () => {
  it("sends DELETE /api/memos/<id> and resolves to undefined on a 204 — DoD-4", async () => {
    const mock = serveNoContent();
    await expect(deleteMemo(MEMO_ID)).resolves.toBeUndefined();
    expect(seen(mock)).toEqual([{ method: "DELETE", path: MEMO_PATH, search: "" }]);
  });
});

// ---------------------------------------------------------------------------
describe("fetchMemoChain", () => {
  const userLevel: MemoChainLevel = {
    scope: "user",
    scope_id: null,
    memos: [memo(MEMO_ID, "user", null)],
  };
  const characterLevel: MemoChainLevel = {
    scope: "character",
    scope_id: CHARACTER_ID,
    memos: [memo(OTHER_MEMO_ID, "character", CHARACTER_ID, { is_enabled: false })],
  };
  const setupLevel: MemoChainLevel = { scope: "setup", scope_id: SETUP_ID, memos: [] };
  const sessionLevel: MemoChainLevel = {
    scope: "session",
    scope_id: SESSION_ID,
    memos: [
      memo(THIRD_MEMO_ID, "session", SESSION_ID, { is_forced: true }),
      memo(FOURTH_MEMO_ID, "session", SESSION_ID, { sort_key: 1 }),
    ],
  };

  it("requests exactly GET /api/sessions/<id>/memo-chain — DoD-5", async () => {
    const mock = serve({ levels: [userLevel, characterLevel, sessionLevel] });
    await fetchMemoChain(SESSION_ID);
    expect(seen(mock)).toEqual([
      { method: "GET", path: `/api/sessions/${SESSION_ID}/memo-chain`, search: "" },
    ]);
  });

  it("resolves to the payload's levels array in the payload's order (four levels) — DoD-5", async () => {
    serve({ levels: [userLevel, characterLevel, setupLevel, sessionLevel] });
    await expect(fetchMemoChain(SESSION_ID)).resolves.toEqual([
      userLevel,
      characterLevel,
      setupLevel,
      sessionLevel,
    ]);
  });

  it("resolves to the payload's levels as received, including three levels when there is no setup — DoD-5", async () => {
    serve({ levels: [userLevel, characterLevel, sessionLevel] });
    const levels = await fetchMemoChain(SESSION_ID);
    expect(levels.map((level) => level.scope)).toEqual(["user", "character", "session"]);
    expect(levels).toEqual([userLevel, characterLevel, sessionLevel]);
  });

  it("keeps each level's scope_id the identical string or null the payload carried — DoD-5", async () => {
    serve({ levels: [userLevel, characterLevel, setupLevel, sessionLevel] });
    const levels = await fetchMemoChain(SESSION_ID);
    expect(levels.map((level) => level.scope_id)).toEqual([null, CHARACTER_ID, SETUP_ID, SESSION_ID]);
    expect(levels[0].scope_id).toBeNull();
    expect(typeof levels[1].scope_id).toBe("string");
    expect(levels[3].memos.map((row) => row.id)).toEqual([THIRD_MEMO_ID, FOURTH_MEMO_ID]);
  });
});

// ---------------------------------------------------------------------------
describe("failures are the shared client's ApiErrors", () => {
  it("a 404 memo_not_found envelope rejects updateMemo with an ApiError of that code — DoD-6", async () => {
    serve(envelope("memo_not_found", "That memo does not exist."), 404);
    const error = await rejection(() => updateMemo(MEMO_ID, { is_forced: true }));
    expect(isApiError(error)).toBe(true);
    expect(isApiError(error) ? error.code : null).toBe("memo_not_found");
    expect(isApiError(error) ? error.status : null).toBe(404);
  });

  it("a 404 memo_not_found envelope rejects deleteMemo with an ApiError of that code — DoD-6", async () => {
    serve(envelope("memo_not_found", "That memo does not exist."), 404);
    const error = await rejection(() => deleteMemo(MEMO_ID));
    expect(isApiError(error)).toBe(true);
    expect(isApiError(error) ? error.code : null).toBe("memo_not_found");
    expect(isApiError(error) ? error.status : null).toBe(404);
  });

  it("a 404 session_not_found envelope rejects fetchMemoChain with an ApiError of that code — DoD-6", async () => {
    serve(envelope("session_not_found", "That session does not exist."), 404);
    const error = await rejection(() => fetchMemoChain(SESSION_ID));
    expect(isApiError(error)).toBe(true);
    expect(isApiError(error) ? error.code : null).toBe("session_not_found");
    expect(isApiError(error) ? error.status : null).toBe(404);
  });

  it("a 422 rejects createMemo with an ApiError — DoD-6", async () => {
    serve(
      {
        detail: [
          { type: "value_error", loc: ["body", "body"], msg: "Value error, body must not be blank", input: " " },
        ],
      },
      422,
    );
    const error = await rejection(() => createMemo("session", SESSION_ID, " "));
    expect(isApiError(error)).toBe(true);
    expect(isApiError(error) ? error.status : null).toBe(422);
  });
});

// ---------------------------------------------------------------------------
describe("abort signals (D5)", () => {
  it("createMemo calls fetch with no abort signal — DoD-7", async () => {
    const mock = serve(memo(MEMO_ID, "user", null), 201);
    await createMemo("user", null, "x");
    expect(mock).toHaveBeenCalledTimes(1);
    expect(sentSignal(mock) ?? undefined).toBeUndefined();
  });

  it("updateMemo calls fetch with no abort signal — DoD-7", async () => {
    const mock = serve(memo(MEMO_ID, "user", null));
    await updateMemo(MEMO_ID, { is_enabled: false });
    expect(mock).toHaveBeenCalledTimes(1);
    expect(sentSignal(mock) ?? undefined).toBeUndefined();
  });

  it("deleteMemo calls fetch with no abort signal — DoD-7", async () => {
    const mock = serveNoContent();
    await deleteMemo(MEMO_ID);
    expect(mock).toHaveBeenCalledTimes(1);
    expect(sentSignal(mock) ?? undefined).toBeUndefined();
  });

  it("fetchMemos passes the signal it was given — DoD-7", async () => {
    const controller = new AbortController();
    const mock = serve({ memos: [] });
    await fetchMemos("character", CHARACTER_ID, controller.signal);
    expect(mock).toHaveBeenCalledTimes(1);
    expect(sentSignal(mock)).toBe(controller.signal);
  });

  it("fetchMemoChain passes the signal it was given — DoD-7", async () => {
    const controller = new AbortController();
    const mock = serve({ levels: [] });
    await fetchMemoChain(SESSION_ID, controller.signal);
    expect(mock).toHaveBeenCalledTimes(1);
    expect(sentSignal(mock)).toBe(controller.signal);
  });
});

// ===========================================================================
// Feature 016, step 002 — reorderMemos (DoD-2, DoD-3).
// Expected behaviour from 016 002's Interface intent / DoD and 016 context.md's
// "Wire contract — what 016 changes" (PUT /api/memos/order).
const ORDER_PATH = "/api/memos/order";
const REORDER_FIRST = "7250000000000000102";
const REORDER_SECOND = "7250000000000000101";

describe("reorderMemos (feature 016, step 002)", () => {
  it("PUTs /api/memos/order with exactly { scope, scope_id, memo_ids } for a character level — DoD-2", async () => {
    const rows = [
      memo(REORDER_FIRST, "character", CHARACTER_ID, { sort_key: 0 }),
      memo(REORDER_SECOND, "character", CHARACTER_ID, { sort_key: 1 }),
    ];
    const mock = serve({ memos: rows });
    await reorderMemos("character", CHARACTER_ID, [REORDER_FIRST, REORDER_SECOND]);
    expect(seen(mock)).toEqual([{ method: "PUT", path: ORDER_PATH, search: "" }]);
    expect(sentBody(mock)).toStrictEqual({
      scope: "character",
      scope_id: "7250000000000000001",
      memo_ids: ["7250000000000000102", "7250000000000000101"],
    });
    expect(bodyKeys(mock).sort()).toEqual(["memo_ids", "scope", "scope_id"]);
  });

  it("sends scope_id null for the user level — DoD-2", async () => {
    const rows = [memo(REORDER_FIRST, "user", null, { sort_key: 0 }), memo(REORDER_SECOND, "user", null, { sort_key: 1 })];
    const mock = serve({ memos: rows });
    await reorderMemos("user", null, [REORDER_FIRST, REORDER_SECOND]);
    expect(seen(mock)).toEqual([{ method: "PUT", path: ORDER_PATH, search: "" }]);
    expect(sentBody(mock)).toStrictEqual({
      scope: "user",
      scope_id: null,
      memo_ids: [REORDER_FIRST, REORDER_SECOND],
    });
    expect(bodyKeys(mock).sort()).toEqual(["memo_ids", "scope", "scope_id"]);
  });

  it("resolves to the response's memos array in its order, every id the identical string — DoD-2", async () => {
    const rows = [
      memo(REORDER_FIRST, "character", CHARACTER_ID, { sort_key: 0 }),
      memo(REORDER_SECOND, "character", CHARACTER_ID, { sort_key: 1, is_forced: true }),
    ];
    serve({ memos: rows });
    const got = await reorderMemos("character", CHARACTER_ID, [REORDER_FIRST, REORDER_SECOND]);
    expect(got).toEqual(rows);
    expect(got.map((row) => row.id)).toEqual(["7250000000000000102", "7250000000000000101"]);
    expect(typeof got[0].id).toBe("string");
  });

  it("the user level resolves to the response's memos array in its order — DoD-2", async () => {
    const rows = [memo(REORDER_SECOND, "user", null, { sort_key: 0 }), memo(REORDER_FIRST, "user", null, { sort_key: 1 })];
    serve({ memos: rows });
    const got = await reorderMemos("user", null, [REORDER_SECOND, REORDER_FIRST]);
    expect(got).toEqual(rows);
    expect(got.map((row) => row.id)).toEqual([REORDER_SECOND, REORDER_FIRST]);
  });

  it("calls fetch with no abort signal — DoD-3", async () => {
    const mock = serve({ memos: [memo(REORDER_FIRST, "character", CHARACTER_ID)] });
    await reorderMemos("character", CHARACTER_ID, [REORDER_FIRST]);
    expect(mock).toHaveBeenCalledTimes(1);
    expect(sentSignal(mock) ?? undefined).toBeUndefined();
  });

  it("a 409 memo_order_mismatch envelope rejects with an ApiError of that code — DoD-3", async () => {
    serve(envelope("memo_order_mismatch", "The notes changed."), 409);
    const error = await rejection(() =>
      reorderMemos("character", CHARACTER_ID, [REORDER_FIRST, REORDER_SECOND]),
    );
    expect(isApiError(error)).toBe(true);
    expect(isApiError(error) ? error.code : null).toBe("memo_order_mismatch");
    expect(isApiError(error) ? error.status : null).toBe(409);
  });
});
