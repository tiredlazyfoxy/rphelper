// Feature 015, step 006 — one level's notes: the shared level state (DoD-1..DoD-18).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 006.context.md (the draft-retention rule, applying rows, failure slots, the flush) and
// context.md: D2 (blank new note dropped, cleared saved note deleted), D5 (save on focus
// loss, never optimistic, apply-a-row by updated_at, failures inline), D6 (one key per
// toggle), D13 (the new-note lifecycle), D15 (blank = JavaScript trim), D16 (the shape), the
// UI strings table (the three failure sentences) and the memos wire contract.
//
// `fetch` is stubbed per test; requests are recorded by exact method + pathname + query
// string, with the JSON body parsed so whole-object comparison catches a stray key.
// Per-note bookkeeping is read only through noteText / noteFailure / isFlagWriteInFlight;
// the new note through `newNote`'s frozen fields.
import { autorun } from "mobx";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Memo, MemoScope } from "../../src/app/memosApi";
import {
  applyMemoRow,
  flushMemoLevel,
  isBlank,
  isFlagWriteInFlight,
  isReorderInFlight,
  loadMemoLevel,
  MemoLevelState,
  noteFailure,
  noteText,
  openNewNote,
  populateMemoLevel,
  reorderFailure,
  reorderMemoLevel,
  saveNewNote,
  saveNote,
  setNewNoteText,
  setNoteText,
  toggleEnabled,
  toggleForced,
} from "../../src/app/memoLevelState";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const CHARACTER_ID = "c1";
const SETUP_ID = "s1";

const MEMO_A = "7250000000000000201";
const MEMO_B = "7250000000000000202";
const MEMO_C = "7250000000000000203";
const MEMO_D = "7250000000000000204";
const NEW_MEMO = "7250000000000000299";

const STAMP = "2026-10-02T09:26:53.000000+00:00";
const LATER_STAMP = "2026-10-02T09:27:10.000000+00:00";
const LATEST_STAMP = "2026-10-02T09:28:45.000000+00:00";

const SAVE_FAILURE = "Could not save the note.";
const DELETE_FAILURE = "Could not delete the note.";
const CHANGE_FAILURE = "Could not change the note.";

/** A fixed-width stamp later than STAMP, distinct for each n (1..59). */
function stampAt(n: number): string {
  return `2026-10-02T09:30:${String(n).padStart(2, "0")}.000000+00:00`;
}

/** A wire Memo with all nine keys; a character-level note of c1 unless overridden. */
function memo(id: string, overrides: Partial<Memo> = {}): Memo {
  return {
    id,
    scope: "character",
    scope_id: CHARACTER_ID,
    body: "Old body",
    is_enabled: true,
    is_forced: false,
    sort_key: 0,
    created_at: STAMP,
    updated_at: STAMP,
    ...overrides,
  };
}

function memoPath(id: string): string {
  return `/api/memos/${id}`;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- fetch helpers

type Seen = { method: string; path: string; search: string; body: unknown };
type Handler = (request: Seen, init?: RequestInit) => Response | Promise<Response>;

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

function noContent(): Response {
  return new Response(null, { status: 204 });
}

function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: "ql-77 went wrong.", detail: {} } }, status);
}

function notFoundResponse(): Response {
  return envelope("memo_not_found", 404);
}

function serverError(): Response {
  return envelope("internal_error", 500);
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
    return handler(request, init);
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

type Deferred<T> = {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason: unknown) => void;
};

function deferred<T>(): Deferred<T> {
  let resolve: (value: T) => void = () => undefined;
  let reject: (reason: unknown) => void = () => undefined;
  const promise = new Promise<T>((ok, fail) => {
    resolve = ok;
    reject = fail;
  });
  return { promise, resolve, reject };
}

/** Every request is held open until the test resolves its deferred, in request order. */
function stubHeld() {
  const held: Deferred<Response>[] = [];
  const backend = stubBackend(() => {
    const next = deferred<Response>();
    held.push(next);
    return next.promise;
  });
  return { ...backend, held };
}

/** Wait until exactly `count` requests have been issued. */
async function untilRequests(calls: Seen[], count: number): Promise<void> {
  await vi.waitFor(() => {
    expect(calls).toHaveLength(count);
  });
}

/**
 * A server answering as the backend would: PATCH merges the supplied keys into the held
 * row with a later updated_at each time; DELETE answers 204; POST creates NEW_MEMO
 * (enabled, not forced) at the end of the level. Anything else is a 404 envelope.
 */
function serveEcho(rows: Memo[]) {
  const byId = new Map<string, Memo>(rows.map((row) => [row.id, row]));
  let tick = 0;
  return stubBackend((request) => {
    if (request.method === "PATCH") {
      const current = [...byId.values()].find((row) => memoPath(row.id) === request.path);
      if (current === undefined) return notFoundResponse();
      tick += 1;
      const next: Memo = {
        ...current,
        ...(request.body as Partial<Memo>),
        updated_at: stampAt(tick),
      };
      byId.set(next.id, next);
      return jsonResponse(next, 200);
    }
    if (request.method === "DELETE") {
      const current = [...byId.values()].find((row) => memoPath(row.id) === request.path);
      if (current === undefined) return notFoundResponse();
      byId.delete(current.id);
      return noContent();
    }
    if (request.method === "POST" && request.path === "/api/memos" && request.search === "") {
      const sent = request.body as { scope: MemoScope; scope_id: string | null; body: string };
      tick += 1;
      const created = memo(NEW_MEMO, {
        scope: sent.scope,
        scope_id: sent.scope_id,
        body: sent.body,
        is_enabled: true,
        is_forced: false,
        sort_key: 9,
        created_at: stampAt(tick),
        updated_at: stampAt(tick),
      });
      byId.set(created.id, created);
      return jsonResponse(created, 201);
    }
    return notFoundResponse();
  });
}

function heldMemo(state: MemoLevelState, id: string): Memo | undefined {
  return state.memos.find((row) => row.id === id);
}

function levelWith(...rows: Memo[]): MemoLevelState {
  const state = new MemoLevelState("character", CHARACTER_ID);
  populateMemoLevel(state, rows);
  return state;
}

// ---------------------------------------------------------------------------
describe("MemoLevelState", () => {
  it("a fresh character level holds its scope and id, is idle, has no memos and no new note — DoD-1", () => {
    const state = new MemoLevelState("character", "c1");
    expect(state.scope).toBe("character");
    expect(state.scopeId).toBe("c1");
    expect(state.status).toBe("idle");
    expect(state.memos).toEqual([]);
    expect(state.newNote).toBeNull();
  });

  it("a fresh user level has a null scopeId — DoD-1", () => {
    const state = new MemoLevelState("user", null);
    expect(state.scope).toBe("user");
    expect(state.scopeId).toBeNull();
    expect(state.status).toBe("idle");
    expect(state.memos).toEqual([]);
    expect(state.newNote).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("loadMemoLevel", () => {
  it("is loading while pending and requests exactly GET /api/memos?scope=character&scope_id=c1 — DoD-2", async () => {
    const { calls, held } = stubHeld();
    const state = new MemoLevelState("character", "c1");
    const pending = loadMemoLevel(state);
    await untilRequests(calls, 1);
    expect(calls).toEqual([
      { method: "GET", path: "/api/memos", search: "?scope=character&scope_id=c1", body: undefined },
    ]);
    expect(state.status).toBe("loading");
    held[0].resolve(jsonResponse({ memos: [] }, 200));
    await pending;
    expect(state.status).toBe("ready");
  });

  it("requests exactly GET /api/memos?scope=user for the user level — DoD-2", async () => {
    const { calls } = stubBackend(() => jsonResponse({ memos: [] }, 200));
    const state = new MemoLevelState("user", null);
    await loadMemoLevel(state);
    expect(calls).toEqual([{ method: "GET", path: "/api/memos", search: "?scope=user", body: undefined }]);
    expect(state.status).toBe("ready");
  });

  it("writes the server's rows in the server's order, disabled ones included, with ready — DoD-2", async () => {
    const rows = [
      memo(MEMO_C, { sort_key: 0, body: "first" }),
      memo(MEMO_A, { sort_key: 1, body: "second", is_enabled: false }),
      memo(MEMO_B, { sort_key: 2, body: "third", is_enabled: false, is_forced: true }),
    ];
    stubBackend(() => jsonResponse({ memos: rows }, 200));
    const state = new MemoLevelState("character", "c1");
    await loadMemoLevel(state);
    expect(state.status).toBe("ready");
    expect(state.memos).toEqual(rows);
    expect(state.memos.map((row) => row.id)).toEqual([MEMO_C, MEMO_A, MEMO_B]);
  });

  it("a failed request sets failed, keeps the rows already held and resolves without throwing — DoD-2", async () => {
    const rows = [memo(MEMO_A), memo(MEMO_B, { sort_key: 1 })];
    let answer: () => Response = () => jsonResponse({ memos: rows }, 200);
    stubBackend(() => answer());
    const state = new MemoLevelState("character", "c1");
    await loadMemoLevel(state);
    expect(state.memos).toEqual(rows);

    answer = () => serverError();
    await expect(loadMemoLevel(state)).resolves.toBeUndefined();
    expect(state.status).toBe("failed");
    expect(state.memos).toEqual(rows);
  });

  it("a transport failure sets failed and resolves without throwing — DoD-2", async () => {
    stubBackend(() => {
      throw new TypeError("Failed to fetch");
    });
    const state = new MemoLevelState("character", "c1");
    await expect(loadMemoLevel(state)).resolves.toBeUndefined();
    expect(state.status).toBe("failed");
    expect(state.memos).toEqual([]);
  });

  it("writes nothing when its signal is aborted before the response settles (response still arrives) — DoD-2", async () => {
    const { calls, held } = stubHeld();
    const state = new MemoLevelState("character", "c1");
    const controller = new AbortController();
    const pending = loadMemoLevel(state, controller.signal);
    await untilRequests(calls, 1);
    controller.abort();
    held[0].resolve(jsonResponse({ memos: [memo(MEMO_A)] }, 200));
    await expect(pending).resolves.toBeUndefined();
    expect(state.memos).toEqual([]);
    expect(state.status).toBe("loading");
  });

  it("writes nothing when its signal is aborted and the request rejects as aborted — DoD-2", async () => {
    stubBackend(
      (_request, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("The operation was aborted.", "AbortError"));
          });
        }),
    );
    const state = new MemoLevelState("character", "c1");
    const controller = new AbortController();
    const pending = loadMemoLevel(state, controller.signal);
    await vi.waitFor(() => {
      expect(state.status).toBe("loading");
    });
    controller.abort();
    await expect(pending).resolves.toBeUndefined();
    expect(state.memos).toEqual([]);
    expect(state.status).toBe("loading");
  });
});

// ---------------------------------------------------------------------------
describe("populateMemoLevel", () => {
  it("writes the given notes in the given order with ready and issues no request — DoD-3", () => {
    const { mock } = stubBackend(() => notFoundResponse());
    const rows = [
      memo(MEMO_B, { sort_key: 0, is_enabled: false }),
      memo(MEMO_A, { sort_key: 1 }),
      memo(MEMO_C, { sort_key: 2, is_forced: true }),
    ];
    const state = new MemoLevelState("setup", SETUP_ID);
    populateMemoLevel(state, rows);
    expect(state.status).toBe("ready");
    expect(state.memos).toEqual(rows);
    expect(state.memos.map((row) => row.id)).toEqual([MEMO_B, MEMO_A, MEMO_C]);
    expect(mock).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("noteText / setNoteText", () => {
  it("noteText is the body until setNoteText records other text, then that text; the body is unchanged — DoD-4", () => {
    stubBackend(() => notFoundResponse());
    const state = levelWith(memo(MEMO_A, { body: "Old body" }));
    expect(noteText(state, MEMO_A)).toBe("Old body");
    setNoteText(state, MEMO_A, "Edited text");
    expect(noteText(state, MEMO_A)).toBe("Edited text");
    expect(heldMemo(state, MEMO_A)?.body).toBe("Old body");
  });

  it("setNoteText on one note leaves another note's text as its body — DoD-4", () => {
    stubBackend(() => notFoundResponse());
    const state = levelWith(memo(MEMO_A, { body: "a" }), memo(MEMO_B, { body: "b", sort_key: 1 }));
    setNoteText(state, MEMO_A, "a2");
    expect(noteText(state, MEMO_B)).toBe("b");
    expect(heldMemo(state, MEMO_A)?.body).toBe("a");
  });
});

// ---------------------------------------------------------------------------
describe("saveNote — a body edit", () => {
  it("sends no request when the note was never edited — DoD-5", async () => {
    const { mock } = stubBackend(() => notFoundResponse());
    const state = levelWith(memo(MEMO_A));
    await saveNote(state, MEMO_A);
    expect(mock).not.toHaveBeenCalled();
  });

  it("sends no request when the editor text equals the body — DoD-5", async () => {
    const { mock } = stubBackend(() => notFoundResponse());
    const state = levelWith(memo(MEMO_A, { body: "Same" }));
    setNoteText(state, MEMO_A, "Changed");
    setNoteText(state, MEMO_A, "Same");
    await saveNote(state, MEMO_A);
    expect(mock).not.toHaveBeenCalled();
  });

  it("PATCHes /api/memos/<id> with exactly { body }; the old body holds while pending; the returned row applies — DoD-6", async () => {
    const { calls, held } = stubHeld();
    const original = memo(MEMO_A, { body: "Old body" });
    const state = levelWith(original);
    setNoteText(state, MEMO_A, "New body");

    const pending = saveNote(state, MEMO_A);
    await untilRequests(calls, 1);
    expect(calls).toEqual([{ method: "PATCH", path: memoPath(MEMO_A), search: "", body: { body: "New body" } }]);
    expect(heldMemo(state, MEMO_A)?.body).toBe("Old body");

    const returned = memo(MEMO_A, { body: "New body", updated_at: LATER_STAMP });
    held[0].resolve(jsonResponse(returned, 200));
    await pending;
    expect(heldMemo(state, MEMO_A)).toEqual(returned);
    expect(noteText(state, MEMO_A)).toBe("New body");
  });

  it("keeps text typed during the request as the editor text while the body becomes the returned one — DoD-6", async () => {
    const { calls, held } = stubHeld();
    const state = levelWith(memo(MEMO_A, { body: "Old body" }));
    setNoteText(state, MEMO_A, "New body");

    const pending = saveNote(state, MEMO_A);
    await untilRequests(calls, 1);
    setNoteText(state, MEMO_A, "Newer body");

    const returned = memo(MEMO_A, { body: "New body", updated_at: LATER_STAMP });
    held[0].resolve(jsonResponse(returned, 200));
    await pending;
    expect(heldMemo(state, MEMO_A)?.body).toBe("New body");
    expect(noteText(state, MEMO_A)).toBe("Newer body");
  });

  it("a failed save shows the save failure, keeps the editor text and body, and resolves — DoD-7", async () => {
    stubBackend(() => serverError());
    const state = levelWith(memo(MEMO_A, { body: "Old body" }));
    expect(noteFailure(state, MEMO_A)).toBeNull();
    setNoteText(state, MEMO_A, "New body");
    await expect(saveNote(state, MEMO_A)).resolves.toBeUndefined();
    expect(noteFailure(state, MEMO_A)).toBe(SAVE_FAILURE);
    expect(noteText(state, MEMO_A)).toBe("New body");
    expect(heldMemo(state, MEMO_A)?.body).toBe("Old body");
  });

  it("a transport failure on save also resolves with the save failure — DoD-7", async () => {
    stubBackend(() => {
      throw new TypeError("Failed to fetch");
    });
    const state = levelWith(memo(MEMO_A, { body: "Old body" }));
    setNoteText(state, MEMO_A, "New body");
    await expect(saveNote(state, MEMO_A)).resolves.toBeUndefined();
    expect(noteFailure(state, MEMO_A)).toBe(SAVE_FAILURE);
    expect(noteText(state, MEMO_A)).toBe("New body");
  });

  it("the next saveNote clears the failure before its request and it stays cleared on success — DoD-7", async () => {
    let failing = true;
    const held: Deferred<Response>[] = [];
    const { calls } = stubBackend(() => {
      if (failing) return serverError();
      const next = deferred<Response>();
      held.push(next);
      return next.promise;
    });
    const state = levelWith(memo(MEMO_A, { body: "Old body" }));
    setNoteText(state, MEMO_A, "New body");
    await saveNote(state, MEMO_A);
    expect(noteFailure(state, MEMO_A)).toBe(SAVE_FAILURE);

    failing = false;
    const retry = saveNote(state, MEMO_A);
    await untilRequests(calls, 2);
    expect(calls[1]).toEqual({ method: "PATCH", path: memoPath(MEMO_A), search: "", body: { body: "New body" } });
    expect(noteFailure(state, MEMO_A)).toBeNull();

    held[0].resolve(jsonResponse(memo(MEMO_A, { body: "New body", updated_at: LATER_STAMP }), 200));
    await retry;
    expect(noteFailure(state, MEMO_A)).toBeNull();
    expect(heldMemo(state, MEMO_A)?.body).toBe("New body");
  });

  it("a failure on one note never touches another note's failure — DoD-7", async () => {
    stubBackend(() => serverError());
    const state = levelWith(memo(MEMO_A), memo(MEMO_B, { sort_key: 1 }));
    setNoteText(state, MEMO_A, "Changed");
    await saveNote(state, MEMO_A);
    expect(noteFailure(state, MEMO_A)).toBe(SAVE_FAILURE);
    expect(noteFailure(state, MEMO_B)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("saveNote — clearing a saved note deletes it (D2)", () => {
  it.each([
    ["empty", ""],
    ["whitespace", "  \n"],
  ])("with %s text sends DELETE /api/memos/<id>, no PATCH, and the note is gone after the 204 — DoD-8", async (_label, text) => {
    const { calls } = stubBackend((request) =>
      request.method === "DELETE" && request.path === memoPath(MEMO_A) ? noContent() : notFoundResponse(),
    );
    const other = memo(MEMO_B, { sort_key: 1 });
    const state = levelWith(memo(MEMO_A), other);
    setNoteText(state, MEMO_A, text);
    await saveNote(state, MEMO_A);
    expect(calls).toEqual([{ method: "DELETE", path: memoPath(MEMO_A), search: "", body: undefined }]);
    expect(calls.some((request) => request.method === "PATCH")).toBe(false);
    expect(state.memos.map((row) => row.id)).toEqual([MEMO_B]);
    expect(heldMemo(state, MEMO_B)).toEqual(other);
  });

  it("a failed delete shows the delete failure and keeps the note and its text — DoD-8", async () => {
    stubBackend(() => serverError());
    const original = memo(MEMO_A, { body: "Old body" });
    const state = levelWith(original);
    setNoteText(state, MEMO_A, "");
    await expect(saveNote(state, MEMO_A)).resolves.toBeUndefined();
    expect(noteFailure(state, MEMO_A)).toBe(DELETE_FAILURE);
    expect(heldMemo(state, MEMO_A)).toEqual(original);
    expect(noteText(state, MEMO_A)).toBe("");
  });
});

// ---------------------------------------------------------------------------
describe("the new note — opening and dropping (D13, D2)", () => {
  it("openNewNote creates one new note with empty text — DoD-9", () => {
    stubBackend(() => notFoundResponse());
    const state = levelWith(memo(MEMO_A));
    openNewNote(state);
    expect(state.newNote).not.toBeNull();
    expect(state.newNote?.text).toBe("");
    expect(state.newNote?.saving).toBe(false);
    expect(state.newNote?.failure).toBeNull();
  });

  it("a second openNewNote leaves the existing new note as it is — DoD-9", () => {
    stubBackend(() => notFoundResponse());
    const state = levelWith(memo(MEMO_A));
    openNewNote(state);
    setNewNoteText(state, "Draft");
    openNewNote(state);
    expect(state.newNote?.text).toBe("Draft");
  });

  it.each([
    ["empty", ""],
    ["whitespace", "  \n"],
  ])("saveNewNote with %s text sends no request, drops the new note and leaves memos unchanged — DoD-9", async (_label, text) => {
    const { mock } = stubBackend(() => notFoundResponse());
    const existing = memo(MEMO_A);
    const state = levelWith(existing);
    openNewNote(state);
    setNewNoteText(state, text);
    await saveNewNote(state);
    expect(mock).not.toHaveBeenCalled();
    expect(state.newNote).toBeNull();
    expect(state.memos).toEqual([existing]);
  });
});

// ---------------------------------------------------------------------------
describe("saveNewNote — creating", () => {
  // Amended by feature 016 step 002 DoD-11 (D5): the saved new note is prepended, not appended.
  it("015 006 DoD-10: POSTs exactly { scope: setup, scope_id: s1, body: Plan }; saving while pending; the row lands first — DoD-11", async () => {
    const { calls, held } = stubHeld();
    const existing = memo(MEMO_A, { scope: "setup", scope_id: SETUP_ID });
    const state = new MemoLevelState("setup", "s1");
    populateMemoLevel(state, [existing]);
    openNewNote(state);
    setNewNoteText(state, "Plan");

    const pending = saveNewNote(state);
    await untilRequests(calls, 1);
    expect(calls).toEqual([
      { method: "POST", path: "/api/memos", search: "", body: { scope: "setup", scope_id: "s1", body: "Plan" } },
    ]);
    expect(state.newNote?.saving).toBe(true);
    expect(state.memos).toEqual([existing]);

    const created = memo(NEW_MEMO, {
      scope: "setup",
      scope_id: "s1",
      body: "Plan",
      is_enabled: true,
      is_forced: false,
      sort_key: 1,
      created_at: LATER_STAMP,
      updated_at: LATER_STAMP,
    });
    held[0].resolve(jsonResponse(created, 201));
    await pending;
    expect(state.memos).toHaveLength(2);
    expect(state.memos[0]).toEqual(created);
    expect(state.memos[0].is_enabled).toBe(true);
    expect(state.memos[0].is_forced).toBe(false);
    expect(state.memos[1]).toEqual(existing);
    expect(state.newNote).toBeNull();
    expect(noteText(state, NEW_MEMO)).toBe("Plan");
  });

  it("a second saveNewNote while the first is saving sends nothing — DoD-10", async () => {
    const { calls, held } = stubHeld();
    const state = new MemoLevelState("setup", "s1");
    populateMemoLevel(state, []);
    openNewNote(state);
    setNewNoteText(state, "Plan");

    const first = saveNewNote(state);
    await untilRequests(calls, 1);
    await saveNewNote(state);
    expect(calls).toHaveLength(1);

    held[0].resolve(
      jsonResponse(memo(NEW_MEMO, { scope: "setup", scope_id: "s1", body: "Plan", updated_at: LATER_STAMP }), 201),
    );
    await first;
    expect(calls).toHaveLength(1);
  });

  it("the user level POSTs exactly { scope: user, scope_id: null, body } — no flag keys — DoD-10", async () => {
    const created = memo(NEW_MEMO, { scope: "user", scope_id: null, body: "Plan", updated_at: LATER_STAMP });
    const { calls } = stubBackend((request) =>
      request.method === "POST" && request.path === "/api/memos" ? jsonResponse(created, 201) : notFoundResponse(),
    );
    const state = new MemoLevelState("user", null);
    populateMemoLevel(state, []);
    openNewNote(state);
    setNewNoteText(state, "Plan");
    await saveNewNote(state);
    expect(calls).toEqual([
      { method: "POST", path: "/api/memos", search: "", body: { scope: "user", scope_id: null, body: "Plan" } },
    ]);
    expect(state.memos).toEqual([created]);
    expect(state.newNote).toBeNull();
  });

  it("text typed during the request becomes the saved note's noteText — DoD-10", async () => {
    const { calls, held } = stubHeld();
    const state = new MemoLevelState("setup", "s1");
    populateMemoLevel(state, []);
    openNewNote(state);
    setNewNoteText(state, "Plan");

    const pending = saveNewNote(state);
    await untilRequests(calls, 1);
    setNewNoteText(state, "Plan and more");

    const created = memo(NEW_MEMO, { scope: "setup", scope_id: "s1", body: "Plan", updated_at: LATER_STAMP });
    held[0].resolve(jsonResponse(created, 201));
    await pending;
    expect(heldMemo(state, NEW_MEMO)?.body).toBe("Plan");
    expect(noteText(state, NEW_MEMO)).toBe("Plan and more");
    expect(state.newNote).toBeNull();
  });

  it("a failed create keeps the new note with its text, not saving, with the save failure; memos unchanged — DoD-11", async () => {
    stubBackend(() => envelope("setup_not_found", 404));
    const existing = memo(MEMO_A, { scope: "setup", scope_id: SETUP_ID });
    const state = new MemoLevelState("setup", "s1");
    populateMemoLevel(state, [existing]);
    openNewNote(state);
    setNewNoteText(state, "Plan");
    await expect(saveNewNote(state)).resolves.toBeUndefined();
    expect(state.newNote).not.toBeNull();
    expect(state.newNote?.text).toBe("Plan");
    expect(state.newNote?.saving).toBe(false);
    expect(state.newNote?.failure).toBe(SAVE_FAILURE);
    expect(state.memos).toEqual([existing]);
  });

  it("a later saveNewNote retries, clearing the failure before its request — DoD-11", async () => {
    let failing = true;
    const held: Deferred<Response>[] = [];
    const { calls } = stubBackend(() => {
      if (failing) {
        throw new TypeError("Failed to fetch");
      }
      const next = deferred<Response>();
      held.push(next);
      return next.promise;
    });
    const state = new MemoLevelState("setup", "s1");
    populateMemoLevel(state, []);
    openNewNote(state);
    setNewNoteText(state, "Plan");
    await saveNewNote(state);
    expect(state.newNote?.failure).toBe(SAVE_FAILURE);

    failing = false;
    const retry = saveNewNote(state);
    await untilRequests(calls, 2);
    expect(calls[1]).toEqual({
      method: "POST",
      path: "/api/memos",
      search: "",
      body: { scope: "setup", scope_id: "s1", body: "Plan" },
    });
    expect(state.newNote?.failure).toBeNull();
    expect(state.newNote?.saving).toBe(true);

    const created = memo(NEW_MEMO, { scope: "setup", scope_id: "s1", body: "Plan", updated_at: LATER_STAMP });
    held[0].resolve(jsonResponse(created, 201));
    await retry;
    expect(state.memos).toEqual([created]);
    expect(state.newNote).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("toggleEnabled (D6, R3)", () => {
  it("on an enabled, forced note: disables with exactly { is_enabled: false }, then re-enables still forced — DoD-12", async () => {
    const { calls } = serveEcho([memo(MEMO_A, { is_enabled: true, is_forced: true })]);
    const state = levelWith(memo(MEMO_A, { is_enabled: true, is_forced: true }));

    await toggleEnabled(state, MEMO_A);
    expect(calls).toEqual([{ method: "PATCH", path: memoPath(MEMO_A), search: "", body: { is_enabled: false } }]);
    expect(heldMemo(state, MEMO_A)?.is_enabled).toBe(false);
    expect(heldMemo(state, MEMO_A)?.is_forced).toBe(true);

    await toggleEnabled(state, MEMO_A);
    expect(calls[1]).toEqual({ method: "PATCH", path: memoPath(MEMO_A), search: "", body: { is_enabled: true } });
    expect(heldMemo(state, MEMO_A)?.is_enabled).toBe(true);
    expect(heldMemo(state, MEMO_A)?.is_forced).toBe(true);
    expect(calls).toHaveLength(2);
  });

  it("on an enabled, not-forced note: the same pair of toggles ends not forced — DoD-12", async () => {
    const { calls } = serveEcho([memo(MEMO_A, { is_enabled: true, is_forced: false })]);
    const state = levelWith(memo(MEMO_A, { is_enabled: true, is_forced: false }));

    await toggleEnabled(state, MEMO_A);
    expect(heldMemo(state, MEMO_A)?.is_enabled).toBe(false);
    expect(heldMemo(state, MEMO_A)?.is_forced).toBe(false);
    await toggleEnabled(state, MEMO_A);
    expect(heldMemo(state, MEMO_A)?.is_enabled).toBe(true);
    expect(heldMemo(state, MEMO_A)?.is_forced).toBe(false);

    expect(calls.map((request) => request.body)).toEqual([{ is_enabled: false }, { is_enabled: true }]);
  });

  it("no enable-toggle request body ever holds is_forced — DoD-12", async () => {
    const { calls } = serveEcho([
      memo(MEMO_A, { is_enabled: true, is_forced: true }),
      memo(MEMO_B, { is_enabled: false, is_forced: false, sort_key: 1 }),
    ]);
    const state = levelWith(
      memo(MEMO_A, { is_enabled: true, is_forced: true }),
      memo(MEMO_B, { is_enabled: false, is_forced: false, sort_key: 1 }),
    );
    await toggleEnabled(state, MEMO_A);
    await toggleEnabled(state, MEMO_B);
    await toggleEnabled(state, MEMO_A);
    expect(calls).toHaveLength(3);
    for (const request of calls) {
      expect(Object.keys(request.body as object)).toEqual(["is_enabled"]);
    }
  });
});

// ---------------------------------------------------------------------------
describe("toggleForced (D6)", () => {
  it("on an enabled, not-forced note PATCHes exactly { is_forced: true } — DoD-13", async () => {
    const { calls } = serveEcho([memo(MEMO_A, { is_enabled: true, is_forced: false })]);
    const state = levelWith(memo(MEMO_A, { is_enabled: true, is_forced: false }));
    await toggleForced(state, MEMO_A);
    expect(calls).toEqual([{ method: "PATCH", path: memoPath(MEMO_A), search: "", body: { is_forced: true } }]);
    expect(heldMemo(state, MEMO_A)?.is_forced).toBe(true);
    expect(heldMemo(state, MEMO_A)?.is_enabled).toBe(true);
  });

  it("on a forced note PATCHes exactly { is_forced: false } — DoD-13", async () => {
    const { calls } = serveEcho([memo(MEMO_A, { is_enabled: true, is_forced: true })]);
    const state = levelWith(memo(MEMO_A, { is_enabled: true, is_forced: true }));
    await toggleForced(state, MEMO_A);
    expect(calls).toEqual([{ method: "PATCH", path: memoPath(MEMO_A), search: "", body: { is_forced: false } }]);
    expect(heldMemo(state, MEMO_A)?.is_forced).toBe(false);
  });

  it("on a disabled note toggles forced and the note stays disabled; no body holds is_enabled — DoD-13", async () => {
    const { calls } = serveEcho([memo(MEMO_A, { is_enabled: false, is_forced: false })]);
    const state = levelWith(memo(MEMO_A, { is_enabled: false, is_forced: false }));

    await toggleForced(state, MEMO_A);
    expect(calls[0]).toEqual({ method: "PATCH", path: memoPath(MEMO_A), search: "", body: { is_forced: true } });
    expect(heldMemo(state, MEMO_A)?.is_forced).toBe(true);
    expect(heldMemo(state, MEMO_A)?.is_enabled).toBe(false);

    await toggleForced(state, MEMO_A);
    expect(calls[1]).toEqual({ method: "PATCH", path: memoPath(MEMO_A), search: "", body: { is_forced: false } });
    expect(heldMemo(state, MEMO_A)?.is_forced).toBe(false);
    expect(heldMemo(state, MEMO_A)?.is_enabled).toBe(false);

    for (const request of calls) {
      expect(Object.keys(request.body as object)).toEqual(["is_forced"]);
    }
  });
});

// ---------------------------------------------------------------------------
describe("flag writes in flight and their failures (D5, D6)", () => {
  it("while a toggle is pending it is in flight and the flags are the held ones; afterwards not — DoD-14", async () => {
    const { calls, held } = stubHeld();
    const state = levelWith(memo(MEMO_A, { is_enabled: true, is_forced: false }), memo(MEMO_B, { sort_key: 1 }));
    expect(isFlagWriteInFlight(state, MEMO_A)).toBe(false);

    const pending = toggleEnabled(state, MEMO_A);
    await untilRequests(calls, 1);
    expect(isFlagWriteInFlight(state, MEMO_A)).toBe(true);
    expect(isFlagWriteInFlight(state, MEMO_B)).toBe(false);
    expect(heldMemo(state, MEMO_A)?.is_enabled).toBe(true);
    expect(heldMemo(state, MEMO_A)?.is_forced).toBe(false);

    const returned = memo(MEMO_A, { is_enabled: false, is_forced: false, updated_at: LATER_STAMP });
    held[0].resolve(jsonResponse(returned, 200));
    await pending;
    expect(isFlagWriteInFlight(state, MEMO_A)).toBe(false);
    expect(heldMemo(state, MEMO_A)).toEqual(returned);
  });

  it("a pending forced toggle is in flight and does not change the flags early — DoD-14", async () => {
    const { calls, held } = stubHeld();
    const state = levelWith(memo(MEMO_A, { is_enabled: false, is_forced: true }));
    const pending = toggleForced(state, MEMO_A);
    await untilRequests(calls, 1);
    expect(isFlagWriteInFlight(state, MEMO_A)).toBe(true);
    expect(heldMemo(state, MEMO_A)?.is_forced).toBe(true);
    expect(heldMemo(state, MEMO_A)?.is_enabled).toBe(false);
    held[0].resolve(jsonResponse(memo(MEMO_A, { is_enabled: false, is_forced: false, updated_at: LATER_STAMP }), 200));
    await pending;
    expect(isFlagWriteInFlight(state, MEMO_A)).toBe(false);
  });

  it.each([
    ["toggleEnabled", toggleEnabled],
    ["toggleForced", toggleForced],
  ] as const)("a failed %s shows the change failure, leaves both flags, clears the mark and resolves — DoD-14", async (_name, toggle) => {
    stubBackend(() => serverError());
    const original = memo(MEMO_A, { is_enabled: true, is_forced: true });
    const state = levelWith(original);
    await expect(toggle(state, MEMO_A)).resolves.toBeUndefined();
    expect(noteFailure(state, MEMO_A)).toBe(CHANGE_FAILURE);
    expect(heldMemo(state, MEMO_A)?.is_enabled).toBe(true);
    expect(heldMemo(state, MEMO_A)?.is_forced).toBe(true);
    expect(heldMemo(state, MEMO_A)).toEqual(original);
    expect(isFlagWriteInFlight(state, MEMO_A)).toBe(false);
  });

  it("a toggle clears the note's failure before its request — DoD-14", async () => {
    let failing = true;
    const held: Deferred<Response>[] = [];
    const { calls } = stubBackend(() => {
      if (failing) return serverError();
      const next = deferred<Response>();
      held.push(next);
      return next.promise;
    });
    const state = levelWith(memo(MEMO_A, { is_enabled: true, is_forced: false }));
    await toggleEnabled(state, MEMO_A);
    expect(noteFailure(state, MEMO_A)).toBe(CHANGE_FAILURE);

    failing = false;
    const retry = toggleEnabled(state, MEMO_A);
    await untilRequests(calls, 2);
    expect(noteFailure(state, MEMO_A)).toBeNull();
    held[0].resolve(jsonResponse(memo(MEMO_A, { is_enabled: false, updated_at: LATER_STAMP }), 200));
    await retry;
    expect(noteFailure(state, MEMO_A)).toBeNull();
    expect(heldMemo(state, MEMO_A)?.is_enabled).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("applyMemoRow (D5 — apply a row by updated_at)", () => {
  it("replaces the held note when the returned updated_at is later — DoD-15", () => {
    stubBackend(() => notFoundResponse());
    const state = levelWith(memo(MEMO_A, { body: "Old body", updated_at: STAMP }));
    const newer = memo(MEMO_A, { body: "New body", is_forced: true, updated_at: LATER_STAMP });
    applyMemoRow(state, newer);
    expect(heldMemo(state, MEMO_A)).toEqual(newer);
  });

  it("replaces the held note when the returned updated_at is equal — DoD-15", () => {
    stubBackend(() => notFoundResponse());
    const state = levelWith(memo(MEMO_A, { body: "Old body", updated_at: LATER_STAMP }));
    const same = memo(MEMO_A, { body: "Same-instant body", updated_at: LATER_STAMP });
    applyMemoRow(state, same);
    expect(heldMemo(state, MEMO_A)).toEqual(same);
  });

  it("ignores a row whose updated_at is older than the held one — DoD-15", () => {
    stubBackend(() => notFoundResponse());
    const current = memo(MEMO_A, { body: "Current body", updated_at: LATER_STAMP });
    const state = levelWith(current);
    applyMemoRow(state, memo(MEMO_A, { body: "Stale body", is_enabled: false, updated_at: STAMP }));
    expect(heldMemo(state, MEMO_A)).toEqual(current);
  });

  it("never inserts a row whose id is not held — DoD-15", () => {
    stubBackend(() => notFoundResponse());
    const only = memo(MEMO_A);
    const state = levelWith(only);
    applyMemoRow(state, memo(MEMO_D, { updated_at: LATEST_STAMP }));
    expect(state.memos).toEqual([only]);
  });

  it("a body save and a toggle in flight together, answered newer-first, leave the newer row — DoD-15", async () => {
    const { calls, held } = stubHeld();
    const state = levelWith(memo(MEMO_A, { body: "Old body", is_enabled: true, updated_at: STAMP }));
    setNoteText(state, MEMO_A, "New body");

    const save = saveNote(state, MEMO_A);
    await untilRequests(calls, 1);
    const toggle = toggleEnabled(state, MEMO_A);
    await untilRequests(calls, 2);
    expect(calls[0].body).toEqual({ body: "New body" });
    expect(calls[1].body).toEqual({ is_enabled: false });

    // The server handled the body save first, then the toggle; the toggle's row is newer.
    const afterSave = memo(MEMO_A, { body: "New body", is_enabled: true, updated_at: LATER_STAMP });
    const afterToggle = memo(MEMO_A, { body: "New body", is_enabled: false, updated_at: LATEST_STAMP });

    held[1].resolve(jsonResponse(afterToggle, 200));
    await toggle;
    held[0].resolve(jsonResponse(afterSave, 200));
    await save;

    expect(heldMemo(state, MEMO_A)).toEqual(afterToggle);
    expect(noteText(state, MEMO_A)).toBe("New body");
  });
});

// ---------------------------------------------------------------------------
describe("flushMemoLevel (D5 — leaving keeps the edit)", () => {
  function flushLevel() {
    const changed = memo(MEMO_A, { body: "A body", sort_key: 0 });
    const unchanged = memo(MEMO_B, { body: "B body", sort_key: 1 });
    const cleared = memo(MEMO_C, { body: "C body", sort_key: 2 });
    const retyped = memo(MEMO_D, { body: "D body", sort_key: 3 });
    const rows = [changed, unchanged, cleared, retyped];
    const state = levelWith(...rows);
    setNoteText(state, MEMO_A, "A body, edited");
    setNoteText(state, MEMO_C, "");
    setNoteText(state, MEMO_D, "D body");
    return { state, rows };
  }

  it("sends exactly one PATCH (changed), one DELETE (cleared) and one POST (new note), nothing else — DoD-16", async () => {
    const { rows, state } = flushLevel();
    const { calls } = serveEcho(rows);
    openNewNote(state);
    setNewNoteText(state, "Later");

    await expect(flushMemoLevel(state)).resolves.toBeUndefined();
    expect(calls).toHaveLength(3);
    expect(calls).toEqual(
      expect.arrayContaining([
        { method: "PATCH", path: memoPath(MEMO_A), search: "", body: { body: "A body, edited" } },
        { method: "DELETE", path: memoPath(MEMO_C), search: "", body: undefined },
        {
          method: "POST",
          path: "/api/memos",
          search: "",
          body: { scope: "character", scope_id: CHARACTER_ID, body: "Later" },
        },
      ]),
    );
  });

  it.each([
    ["empty", ""],
    ["whitespace", "  \n"],
  ])("with the new note's text %s sends no POST — only the PATCH and the DELETE — DoD-16", async (_label, text) => {
    const { rows, state } = flushLevel();
    const { calls } = serveEcho(rows);
    openNewNote(state);
    setNewNoteText(state, text);

    await expect(flushMemoLevel(state)).resolves.toBeUndefined();
    expect(calls).toHaveLength(2);
    expect(calls).toEqual(
      expect.arrayContaining([
        { method: "PATCH", path: memoPath(MEMO_A), search: "", body: { body: "A body, edited" } },
        { method: "DELETE", path: memoPath(MEMO_C), search: "", body: undefined },
      ]),
    );
    expect(calls.some((request) => request.method === "POST")).toBe(false);
  });

  it("resolves without throwing when every write fails — DoD-16", async () => {
    const { state } = flushLevel();
    const { calls } = stubBackend(() => serverError());
    openNewNote(state);
    setNewNoteText(state, "Later");
    await expect(flushMemoLevel(state)).resolves.toBeUndefined();
    expect(calls).toHaveLength(3);
  });
});

// ---------------------------------------------------------------------------
describe("isBlank (D15)", () => {
  it.each(["", " ", "\n\t "])("is true for %j — DoD-17", (text) => {
    expect(isBlank(text)).toBe(true);
  });

  it.each(["a", " a "])("is false for %j — DoD-17", (text) => {
    expect(isBlank(text)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("observability (writes are MobX actions on observable fields)", () => {
  it("an autorun reading memos re-runs after applyMemoRow — DoD-18", () => {
    stubBackend(() => notFoundResponse());
    const state = levelWith(memo(MEMO_A, { updated_at: STAMP }));
    let runs = 0;
    const dispose = autorun(() => {
      void state.memos.map((row) => `${row.id}:${row.body}:${row.updated_at}`);
      runs += 1;
    });
    try {
      expect(runs).toBe(1);
      applyMemoRow(state, memo(MEMO_A, { body: "Applied body", updated_at: LATER_STAMP }));
      expect(runs).toBeGreaterThan(1);
    } finally {
      dispose();
    }
  });

  // The id-order clause is amended by feature 016 step 002 DoD-11 (D5: the new note is prepended).
  it("015 006 DoD-18: an autorun reading memos re-runs after a successful saveNewNote, the new note first — DoD-11", async () => {
    serveEcho([]);
    const state = levelWith(memo(MEMO_A));
    let runs = 0;
    const dispose = autorun(() => {
      void state.memos.map((row) => row.id);
      runs += 1;
    });
    try {
      openNewNote(state);
      setNewNoteText(state, "Plan");
      const before = runs;
      await saveNewNote(state);
      expect(runs).toBeGreaterThan(before);
      expect(state.memos.map((row) => row.id)).toEqual([NEW_MEMO, MEMO_A]);
    } finally {
      dispose();
    }
  });

  it("an autorun reading noteText for a note re-runs after setNoteText — DoD-18", () => {
    stubBackend(() => notFoundResponse());
    const state = levelWith(memo(MEMO_A, { body: "Old body" }));
    const texts: string[] = [];
    const dispose = autorun(() => {
      texts.push(noteText(state, MEMO_A));
    });
    try {
      expect(texts).toEqual(["Old body"]);
      setNoteText(state, MEMO_A, "Typed text");
      expect(texts[texts.length - 1]).toBe("Typed text");
      expect(texts.length).toBeGreaterThan(1);
    } finally {
      dispose();
    }
  });
});

// ===========================================================================
// Feature 016, step 002 — the optimistic reorder (DoD-4..DoD-12).
//
// Expected behaviour from 016 002's Interface intent / DoD, 002.context.md ("The orders,
// concretely", "What the effect must not do") and 016 context.md D5 (prepend) and D7
// (optimistic, merge on success, revert on failure, "Could not reorder the notes.").
// Stubs key on exact method + pathname + query: PUT /api/memos/order shares a prefix with
// /api/memos and /api/memos/<id>.

const ORDER_PATH = "/api/memos/order";
const REORDER_FAILURE = "Could not reorder the notes.";

function isOrderPut(request: Seen): boolean {
  return request.method === "PUT" && request.path === ORDER_PATH && request.search === "";
}

/**
 * PUT /api/memos/order is held open (one deferred per PUT, in order); POST /api/memos answers
 * 201 with `created` (when given); DELETE /api/memos/<id> answers 204; anything else is a 404.
 */
function stubReorderBackend(created?: Memo) {
  const puts: Deferred<Response>[] = [];
  const backend = stubBackend((request) => {
    if (isOrderPut(request)) {
      const next = deferred<Response>();
      puts.push(next);
      return next.promise;
    }
    if (created !== undefined && request.method === "POST" && request.path === "/api/memos" && request.search === "") {
      return jsonResponse(created, 201);
    }
    if (request.method === "DELETE" && request.path.startsWith("/api/memos/") && request.path !== ORDER_PATH) {
      return noContent();
    }
    return notFoundResponse();
  });
  return { ...backend, puts };
}

function putCalls(calls: Seen[]): Seen[] {
  return calls.filter(isOrderPut);
}

function ids(state: MemoLevelState): string[] {
  return state.memos.map((row) => row.id);
}

/** A ready character level (c1) holding A, B, C with sort_key 0, 1, 2. */
function abcLevel() {
  const a = memo(MEMO_A, { body: "A body", sort_key: 0 });
  const b = memo(MEMO_B, { body: "B body", sort_key: 1 });
  const c = memo(MEMO_C, { body: "C body", sort_key: 2 });
  return { state: levelWith(a, b, c), a, b, c };
}

/** The new note D the server creates during a pending reorder. */
const CREATED_D = memo(MEMO_D, {
  body: "D body",
  is_enabled: true,
  is_forced: false,
  sort_key: -1,
  created_at: LATER_STAMP,
  updated_at: LATER_STAMP,
});

// ---------------------------------------------------------------------------
describe("reorder fields (016 002)", () => {
  it("a fresh MemoLevelState is not reordering and has no reorder failure — DoD-4", () => {
    const state = new MemoLevelState("character", CHARACTER_ID);
    expect(isReorderInFlight(state)).toBe(false);
    expect(reorderFailure(state)).toBeNull();
  });

  it("a fresh user-level MemoLevelState is not reordering and has no reorder failure — DoD-4", () => {
    const state = new MemoLevelState("user", null);
    expect(isReorderInFlight(state)).toBe(false);
    expect(reorderFailure(state)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("reorderMemoLevel — optimistic write (U1/D7)", () => {
  it("before the response, memos are C, A, B, the reorder is in flight, and exactly one PUT carries C, A, B — DoD-5", async () => {
    const { calls, puts } = stubReorderBackend();
    const { state } = abcLevel();

    const pending = reorderMemoLevel(state, [MEMO_C, MEMO_A, MEMO_B]);
    await untilRequests(calls, 1);

    expect(ids(state)).toEqual([MEMO_C, MEMO_A, MEMO_B]);
    expect(isReorderInFlight(state)).toBe(true);
    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("PUT");
    expect(calls[0].path).toBe(ORDER_PATH);
    expect(calls[0].search).toBe("");
    expect(calls[0].body).toStrictEqual({
      scope: "character",
      scope_id: CHARACTER_ID,
      memo_ids: [MEMO_C, MEMO_A, MEMO_B],
    });

    puts[0].resolve(
      jsonResponse(
        {
          memos: [
            memo(MEMO_C, { body: "C body", sort_key: 0 }),
            memo(MEMO_A, { body: "A body", sort_key: 1 }),
            memo(MEMO_B, { body: "B body", sort_key: 2 }),
          ],
        },
        200,
      ),
    );
    await pending;
  });

  it("the PUT for the user level carries scope user and scope_id null — DoD-5", async () => {
    const { calls, puts } = stubReorderBackend();
    const a = memo(MEMO_A, { scope: "user", scope_id: null, sort_key: 0 });
    const b = memo(MEMO_B, { scope: "user", scope_id: null, sort_key: 1 });
    const state = new MemoLevelState("user", null);
    populateMemoLevel(state, [a, b]);

    const pending = reorderMemoLevel(state, [MEMO_B, MEMO_A]);
    await untilRequests(calls, 1);
    expect(ids(state)).toEqual([MEMO_B, MEMO_A]);
    expect(calls[0].body).toStrictEqual({ scope: "user", scope_id: null, memo_ids: [MEMO_B, MEMO_A] });

    puts[0].resolve(jsonResponse({ memos: [{ ...b, sort_key: 0 }, { ...a, sort_key: 1 }] }, 200));
    await pending;
  });
});

// ---------------------------------------------------------------------------
describe("reorderMemoLevel — success (D7)", () => {
  it("a 200 with C, A, B at sort_key 0, 1, 2 leaves those rows in that order, not in flight, no failure, no further request — DoD-6", async () => {
    const { calls, puts } = stubReorderBackend();
    const { state } = abcLevel();

    const pending = reorderMemoLevel(state, [MEMO_C, MEMO_A, MEMO_B]);
    await untilRequests(calls, 1);

    const returned = [
      memo(MEMO_C, { body: "C body", sort_key: 0 }),
      memo(MEMO_A, { body: "A body", sort_key: 1 }),
      memo(MEMO_B, { body: "B body", sort_key: 2 }),
    ];
    puts[0].resolve(jsonResponse({ memos: returned }, 200));
    await expect(pending).resolves.toBeUndefined();

    expect(state.memos).toEqual(returned);
    expect(state.memos.map((row) => row.sort_key)).toEqual([0, 1, 2]);
    expect(isReorderInFlight(state)).toBe(false);
    expect(reorderFailure(state)).toBeNull();

    // No listing or chain refetch follows.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(calls).toHaveLength(1);
    expect(calls.some((request) => request.method === "GET")).toBe(false);
  });

  it("a returned row with a later updated_at replaces the held row's body and flags — DoD-6", async () => {
    const { calls, puts } = stubReorderBackend();
    const { state } = abcLevel();

    const pending = reorderMemoLevel(state, [MEMO_C, MEMO_A, MEMO_B]);
    await untilRequests(calls, 1);

    const returned = [
      memo(MEMO_C, { body: "C newer", sort_key: 0, updated_at: LATER_STAMP }),
      memo(MEMO_A, { body: "A body", sort_key: 1, is_forced: true, updated_at: LATER_STAMP }),
      memo(MEMO_B, { body: "B body", sort_key: 2 }),
    ];
    puts[0].resolve(jsonResponse({ memos: returned }, 200));
    await pending;

    expect(state.memos).toEqual(returned);
  });
});

// ---------------------------------------------------------------------------
describe("reorderMemoLevel — failure reverts (U1/D7)", () => {
  const failures: Array<[string, (held: Deferred<Response>) => void]> = [
    ["a 500", (held) => held.resolve(serverError())],
    ["a transport failure", (held) => held.reject(new TypeError("Failed to fetch"))],
    ["a 409 memo_order_mismatch", (held) => held.resolve(envelope("memo_order_mismatch", 409))],
  ];

  it.each(failures)(
    "on %s the level returns to A, B, C with the reorder failure, not in flight, resolving without throwing — DoD-7",
    async (_label, fail) => {
      const { calls, puts } = stubReorderBackend();
      const { state, a, b, c } = abcLevel();

      const pending = reorderMemoLevel(state, [MEMO_C, MEMO_A, MEMO_B]);
      await untilRequests(calls, 1);
      expect(ids(state)).toEqual([MEMO_C, MEMO_A, MEMO_B]);

      fail(puts[0]);
      await expect(pending).resolves.toBeUndefined();

      expect(ids(state)).toEqual([MEMO_A, MEMO_B, MEMO_C]);
      expect(state.memos).toEqual([a, b, c]);
      expect(reorderFailure(state)).toBe(REORDER_FAILURE);
      expect(isReorderInFlight(state)).toBe(false);

      // The level is not refetched (D7's 409 case included).
      await new Promise((resolve) => setTimeout(resolve, 0));
      expect(calls).toHaveLength(1);
    },
  );

  it("a later successful reorder clears the reorder failure — DoD-7", async () => {
    const { calls, puts } = stubReorderBackend();
    const { state } = abcLevel();

    const first = reorderMemoLevel(state, [MEMO_C, MEMO_A, MEMO_B]);
    await untilRequests(calls, 1);
    puts[0].resolve(serverError());
    await first;
    expect(reorderFailure(state)).toBe(REORDER_FAILURE);

    const second = reorderMemoLevel(state, [MEMO_C, MEMO_A, MEMO_B]);
    await untilRequests(calls, 2);
    expect(putCalls(calls)).toHaveLength(2);
    puts[1].resolve(
      jsonResponse(
        {
          memos: [
            memo(MEMO_C, { body: "C body", sort_key: 0 }),
            memo(MEMO_A, { body: "A body", sort_key: 1 }),
            memo(MEMO_B, { body: "B body", sort_key: 2 }),
          ],
        },
        200,
      ),
    );
    await expect(second).resolves.toBeUndefined();

    expect(reorderFailure(state)).toBeNull();
    expect(ids(state)).toEqual([MEMO_C, MEMO_A, MEMO_B]);
    expect(isReorderInFlight(state)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("reorderMemoLevel — refusals (U1)", () => {
  it("while a reorder is pending, a second call sends no request and leaves the optimistic order — DoD-8", async () => {
    const { calls, puts } = stubReorderBackend();
    const { state } = abcLevel();

    const first = reorderMemoLevel(state, [MEMO_C, MEMO_A, MEMO_B]);
    await untilRequests(calls, 1);

    await expect(reorderMemoLevel(state, [MEMO_B, MEMO_C, MEMO_A])).resolves.toBeUndefined();
    expect(calls).toHaveLength(1);
    expect(ids(state)).toEqual([MEMO_C, MEMO_A, MEMO_B]);
    expect(isReorderInFlight(state)).toBe(true);

    puts[0].resolve(
      jsonResponse(
        {
          memos: [
            memo(MEMO_C, { body: "C body", sort_key: 0 }),
            memo(MEMO_A, { body: "A body", sort_key: 1 }),
            memo(MEMO_B, { body: "B body", sort_key: 2 }),
          ],
        },
        200,
      ),
    );
    await first;
    expect(calls).toHaveLength(1);
  });

  it("a call whose order equals the current order sends no request and changes nothing — DoD-8", async () => {
    const { mock } = stubReorderBackend();
    const { state, a, b, c } = abcLevel();

    await expect(reorderMemoLevel(state, [MEMO_A, MEMO_B, MEMO_C])).resolves.toBeUndefined();

    expect(mock).not.toHaveBeenCalled();
    expect(state.memos).toEqual([a, b, c]);
    expect(isReorderInFlight(state)).toBe(false);
    expect(reorderFailure(state)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("reorderMemoLevel — concurrency on revert (D7)", () => {
  it("a note D saved while the reorder is pending stays first after the revert: D, A, B, C — DoD-9", async () => {
    const { calls, puts } = stubReorderBackend(CREATED_D);
    const { state } = abcLevel();

    const pending = reorderMemoLevel(state, [MEMO_C, MEMO_A, MEMO_B]);
    await untilRequests(calls, 1);

    openNewNote(state);
    setNewNoteText(state, "D body");
    await saveNewNote(state);
    expect(calls.filter((request) => request.method === "POST" && request.path === "/api/memos")).toHaveLength(1);
    expect(state.memos.some((row) => row.id === MEMO_D)).toBe(true);
    expect(state.newNote).toBeNull();

    puts[0].resolve(serverError());
    await expect(pending).resolves.toBeUndefined();

    expect(ids(state)).toEqual([MEMO_D, MEMO_A, MEMO_B, MEMO_C]);
    expect(heldMemo(state, MEMO_D)).toEqual(CREATED_D);
    expect(reorderFailure(state)).toBe(REORDER_FAILURE);
    expect(isReorderInFlight(state)).toBe(false);
  });

  it("a note B deleted while the reorder is pending stays absent after the revert — DoD-9", async () => {
    const { calls, puts } = stubReorderBackend();
    const { state } = abcLevel();

    const pending = reorderMemoLevel(state, [MEMO_C, MEMO_A, MEMO_B]);
    await untilRequests(calls, 1);

    setNoteText(state, MEMO_B, "");
    await saveNote(state, MEMO_B);
    expect(calls.filter((request) => request.method === "DELETE" && request.path === memoPath(MEMO_B))).toHaveLength(1);
    expect(state.memos.some((row) => row.id === MEMO_B)).toBe(false);

    puts[0].resolve(serverError());
    await expect(pending).resolves.toBeUndefined();

    expect(ids(state)).toEqual([MEMO_A, MEMO_C]);
    expect(reorderFailure(state)).toBe(REORDER_FAILURE);
    expect(isReorderInFlight(state)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("reorderMemoLevel — concurrency on success (D7, 015 D5 apply-a-row)", () => {
  it("a returned row older than the held row keeps the held body and flags, at the returned position — DoD-10", async () => {
    const { calls, puts } = stubReorderBackend();
    const a = memo(MEMO_A, { body: "A current", is_forced: true, sort_key: 0, updated_at: LATER_STAMP });
    const b = memo(MEMO_B, { body: "B body", sort_key: 1 });
    const c = memo(MEMO_C, { body: "C body", sort_key: 2 });
    const state = levelWith(a, b, c);

    const pending = reorderMemoLevel(state, [MEMO_C, MEMO_A, MEMO_B]);
    await untilRequests(calls, 1);

    const staleA = memo(MEMO_A, { body: "A stale", is_forced: false, is_enabled: false, sort_key: 1, updated_at: STAMP });
    const newC = memo(MEMO_C, { body: "C body", sort_key: 0 });
    const newB = memo(MEMO_B, { body: "B body", sort_key: 2 });
    puts[0].resolve(jsonResponse({ memos: [newC, staleA, newB] }, 200));
    await expect(pending).resolves.toBeUndefined();

    expect(ids(state)).toEqual([MEMO_C, MEMO_A, MEMO_B]);
    const heldA = heldMemo(state, MEMO_A);
    expect(heldA?.body).toBe("A current");
    expect(heldA?.is_forced).toBe(true);
    expect(heldA?.is_enabled).toBe(true);
    expect(heldA?.updated_at).toBe(LATER_STAMP);
    expect(state.memos[0]).toEqual(newC);
    expect(state.memos[2]).toEqual(newB);
    expect(isReorderInFlight(state)).toBe(false);
    expect(reorderFailure(state)).toBeNull();
  });

  it("a note created while pending and absent from the response stays first — DoD-10", async () => {
    const { calls, puts } = stubReorderBackend(CREATED_D);
    const { state } = abcLevel();

    const pending = reorderMemoLevel(state, [MEMO_C, MEMO_A, MEMO_B]);
    await untilRequests(calls, 1);

    openNewNote(state);
    setNewNoteText(state, "D body");
    await saveNewNote(state);

    const returned = [
      memo(MEMO_C, { body: "C body", sort_key: 0 }),
      memo(MEMO_A, { body: "A body", sort_key: 1 }),
      memo(MEMO_B, { body: "B body", sort_key: 2 }),
    ];
    puts[0].resolve(jsonResponse({ memos: returned }, 200));
    await expect(pending).resolves.toBeUndefined();

    expect(ids(state)).toEqual([MEMO_D, MEMO_C, MEMO_A, MEMO_B]);
    expect(heldMemo(state, MEMO_D)).toEqual(CREATED_D);
    expect(state.memos.slice(1)).toEqual(returned);
  });

  it("a returned id no longer held (deleted while pending) is not inserted — DoD-10", async () => {
    const { calls, puts } = stubReorderBackend();
    const { state } = abcLevel();

    const pending = reorderMemoLevel(state, [MEMO_C, MEMO_A, MEMO_B]);
    await untilRequests(calls, 1);

    setNoteText(state, MEMO_B, "");
    await saveNote(state, MEMO_B);
    expect(state.memos.some((row) => row.id === MEMO_B)).toBe(false);

    const returnedC = memo(MEMO_C, { body: "C body", sort_key: 0 });
    const returnedA = memo(MEMO_A, { body: "A body", sort_key: 1 });
    puts[0].resolve(
      jsonResponse({ memos: [returnedC, returnedA, memo(MEMO_B, { body: "B body", sort_key: 2 })] }, 200),
    );
    await expect(pending).resolves.toBeUndefined();

    expect(ids(state)).toEqual([MEMO_C, MEMO_A]);
    expect(state.memos).toEqual([returnedC, returnedA]);
  });
});

// ---------------------------------------------------------------------------
describe("saveNewNote prepends (D5)", () => {
  it("on a level holding A and B, the saved new note is the first entry, enabled and not forced, newNote null — DoD-11", async () => {
    const created = memo(NEW_MEMO, {
      body: "Plan",
      is_enabled: true,
      is_forced: false,
      sort_key: -1,
      created_at: LATER_STAMP,
      updated_at: LATER_STAMP,
    });
    stubBackend((request) =>
      request.method === "POST" && request.path === "/api/memos" && request.search === ""
        ? jsonResponse(created, 201)
        : notFoundResponse(),
    );
    const a = memo(MEMO_A, { sort_key: 0 });
    const b = memo(MEMO_B, { sort_key: 1 });
    const state = levelWith(a, b);
    openNewNote(state);
    setNewNoteText(state, "Plan");

    await saveNewNote(state);

    expect(state.memos).toEqual([created, a, b]);
    expect(state.memos[0].is_enabled).toBe(true);
    expect(state.memos[0].is_forced).toBe(false);
    expect(state.newNote).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("reorder observability (writes are MobX actions)", () => {
  it("an autorun reading memos re-runs after the optimistic write and after the revert — DoD-12", async () => {
    const { calls, puts } = stubReorderBackend();
    const { state } = abcLevel();
    const orders: string[][] = [];
    const dispose = autorun(() => {
      orders.push(state.memos.map((row) => row.id));
    });
    try {
      expect(orders).toEqual([[MEMO_A, MEMO_B, MEMO_C]]);

      const pending = reorderMemoLevel(state, [MEMO_C, MEMO_A, MEMO_B]);
      await untilRequests(calls, 1);
      expect(orders.length).toBeGreaterThan(1);
      expect(orders[orders.length - 1]).toEqual([MEMO_C, MEMO_A, MEMO_B]);
      const afterOptimistic = orders.length;

      puts[0].resolve(serverError());
      await pending;
      expect(orders.length).toBeGreaterThan(afterOptimistic);
      expect(orders[orders.length - 1]).toEqual([MEMO_A, MEMO_B, MEMO_C]);
    } finally {
      dispose();
    }
  });

  it("an autorun reading reorderFailure re-runs when it is set — DoD-12", async () => {
    const { calls, puts } = stubReorderBackend();
    const { state } = abcLevel();
    const seenFailures: Array<string | null> = [];
    const dispose = autorun(() => {
      seenFailures.push(reorderFailure(state));
    });
    try {
      expect(seenFailures).toEqual([null]);

      const pending = reorderMemoLevel(state, [MEMO_C, MEMO_A, MEMO_B]);
      await untilRequests(calls, 1);
      puts[0].resolve(serverError());
      await pending;

      expect(seenFailures.length).toBeGreaterThan(1);
      expect(seenFailures[seenFailures.length - 1]).toBe(REORDER_FAILURE);
    } finally {
      dispose();
    }
  });
});
