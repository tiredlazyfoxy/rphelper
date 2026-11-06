// Feature 034 — session-names, step 005: the rename state and its free-function effects
// (DoD-1..DoD-7). The editor component's clauses (DoD-8) live in `SessionNameEditor.test.tsx`;
// `applySession`'s tie rule (DoD-9) lives in `sessionsState.test.ts`.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 005.context.md (the effect shape: in-flight guard, abort check before every post-await write,
// pending cleared only when not aborted) and DEC-034-11 (unchanged sends nothing, one request in
// flight, inline failure with the fixed sentence, apply the returned row, never optimistic).
// Bindings come from the frozen `### Step 005` skeleton record: "closed" means
// `editingId === null`.
//
// Harness conventions:
// - `fetch` is stubbed per test and routed by exact method + pathname; the rename route is
//   `PATCH /api/sessions/<id>` with body `{ name }` (step 004's `renameSession`).
// - `shared/notifyFailure` is replaced by a spy so "no notification is raised" is observable
//   without importing `@mantine/notifications` here (tests/conventions.test.ts).
// - Every id is past Number.MAX_SAFE_INTEGER (ids are decimal strings).
import { runInAction, toJS } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Session } from "../../src/app/sessionsApi";
import {
  beginRename,
  cancelRename,
  commitRename,
  SessionRenameState,
} from "../../src/app/sessionRenameState";
import { SessionsState } from "../../src/app/sessionsState";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- fixtures
const FAILURE_SENTENCE = "Could not rename the session.";

const CHARACTER_ID = "7250000000000000001";
const NAMED_ID = "7270000000000000003";
const UNNAMED_ID = "7270000000000000002";
const OTHER_ID = "7270000000000000001";

const OLD_USE = "2026-03-01T08:00:00.000000+00:00";
const MID_USE = "2026-03-10T08:00:00.000000+00:00";
const NEW_USE = "2026-03-14T08:00:00.000000+00:00";
const RENAMED_AT = "2026-04-06T12:00:00.000000+00:00";

function makeSession(id: string, lastUsedAt: string, name: string | null): Session {
  return {
    id,
    character_id: CHARACTER_ID,
    setup_id: null,
    setup_name: null,
    name,
    archived_at: null,
    last_used_at: lastUsedAt,
    created_at: lastUsedAt,
    updated_at: lastUsedAt,
  };
}

const NAMED = makeSession(NAMED_ID, NEW_USE, "Harbour Night");
const UNNAMED = makeSession(UNNAMED_ID, MID_USE, null);
const OTHER = makeSession(OTHER_ID, OLD_USE, null);

/** The workspace list in the server's order (last_used_at descending). */
const WORKING: Session[] = [NAMED, UNNAMED, OTHER];

/** The server's answer to a rename: same row, the stored name, a later updated_at. */
function served(session: Session, name: string | null): Session {
  return { ...session, name, updated_at: RENAMED_AT };
}

beforeEach(() => {
  notifyFailureSpy.mockClear();
});

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

function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: `refused: ${code}`, detail: {} } }, status);
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

type Seen = { line: string; body: unknown };

/** Stubs fetch; every request is logged as "METHOD /path" with its parsed JSON body. */
function stubFetch(answer: (init?: RequestInit) => Promise<Response>): Seen[] {
  const log: Seen[] = [];
  const impl: FetchFn = (input, init) => {
    const raw = typeof init?.body === "string" ? init.body : null;
    log.push({
      line: `${requestMethod(input, init)} ${requestUrl(input).pathname}`,
      body: raw === null ? null : (JSON.parse(raw) as unknown),
    });
    return answer(init);
  };
  vi.stubGlobal("fetch", vi.fn<FetchFn>(impl));
  return log;
}

/** Every request answers the given session as a 200. */
function serveRenamed(session: Session): Seen[] {
  return stubFetch(() => Promise.resolve(jsonResponse(session, 200)));
}

/** A request held open until the test resolves it. */
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

function withSessions(rows: Session[]): SessionsState {
  const state = new SessionsState();
  runInAction(() => {
    state.sessions = rows.map((row) => ({ ...row }));
    state.status = "ready";
  });
  return state;
}

/** Sets the draft as the editor's typing would (a MobX action from outside). */
function type(state: SessionRenameState, draft: string): void {
  runInAction(() => {
    state.draft = draft;
  });
}

/** An open editor for `session` with `draft` typed into it. */
function editing(session: Session, draft: string): SessionRenameState {
  const state = new SessionRenameState();
  beginRename(state, session);
  type(state, draft);
  return state;
}

function renameSnapshot(state: SessionRenameState) {
  return {
    editingId: state.editingId,
    draft: state.draft,
    originalName: state.originalName,
    pending: state.pending,
    error: state.error,
  };
}

const sessionPath = (id: string): string => `/api/sessions/${id}`;

// ---------------------------------------------------------------------------
describe("beginRename", () => {
  it("a fresh state has no editor open, nothing pending and no error — S034_005_DoD1", () => {
    const state = new SessionRenameState();
    expect(state.editingId).toBeNull();
    expect(state.pending).toBe(false);
    expect(state.error).toBeNull();
  });

  it("opens editing for a named session with the draft pre-filled with its name — S034_005_DoD1", () => {
    const state = new SessionRenameState();
    beginRename(state, NAMED);
    expect(state.editingId).toBe(NAMED_ID);
    expect(state.draft).toBe("Harbour Night");
    expect(state.originalName).toBe("Harbour Night");
  });

  it("opens editing for a never-renamed session with an empty draft — S034_005_DoD1", () => {
    const state = new SessionRenameState();
    beginRename(state, UNNAMED);
    expect(state.editingId).toBe(UNNAMED_ID);
    expect(state.draft).toBe("");
    expect(state.originalName).toBeNull();
  });

  it("clears an earlier error and replaces an earlier draft — S034_005_DoD1", () => {
    const state = new SessionRenameState();
    runInAction(() => {
      state.error = FAILURE_SENTENCE;
      state.draft = "left over";
    });
    beginRename(state, UNNAMED);
    expect(state.error).toBeNull();
    expect(state.draft).toBe("");
  });

  it("switching to another session pre-fills from that session — S034_005_DoD1", () => {
    const state = new SessionRenameState();
    beginRename(state, UNNAMED);
    beginRename(state, NAMED);
    expect(state.editingId).toBe(NAMED_ID);
    expect(state.draft).toBe("Harbour Night");
  });
});

// ---------------------------------------------------------------------------
describe("commitRename — a changed draft sends one normalised name", () => {
  it("sends exactly PATCH /api/sessions/<id> with the trimmed name — S034_005_DoD2", async () => {
    const log = serveRenamed(served(UNNAMED, "Dockside Truce"));
    const state = editing(UNNAMED, "  Dockside Truce \t");
    await commitRename(state, withSessions(WORKING));
    expect(log).toEqual([{ line: `PATCH ${sessionPath(UNNAMED_ID)}`, body: { name: "Dockside Truce" } }]);
  });

  it("keeps inner spacing and sends a changed name for a named session — S034_005_DoD2", async () => {
    const log = serveRenamed(served(NAMED, "Harbour  Night II"));
    const state = editing(NAMED, " Harbour  Night II ");
    await commitRename(state, withSessions(WORKING));
    expect(log).toEqual([{ line: `PATCH ${sessionPath(NAMED_ID)}`, body: { name: "Harbour  Night II" } }]);
  });

  it("an empty draft for a named session sends name null — S034_005_DoD2", async () => {
    const log = serveRenamed(served(NAMED, null));
    const state = editing(NAMED, "");
    await commitRename(state, withSessions(WORKING));
    expect(log).toEqual([{ line: `PATCH ${sessionPath(NAMED_ID)}`, body: { name: null } }]);
  });

  it("a whitespace-only draft for a named session sends name null — S034_005_DoD2", async () => {
    const log = serveRenamed(served(NAMED, null));
    const state = editing(NAMED, "   \t ");
    await commitRename(state, withSessions(WORKING));
    expect(log).toHaveLength(1);
    expect(log[0].body).toEqual({ name: null });
    expect(Object.keys(log[0].body as object)).toEqual(["name"]);
  });

  it("resolves without a value — S034_005_DoD2", async () => {
    serveRenamed(served(UNNAMED, "Dockside Truce"));
    const state = editing(UNNAMED, "Dockside Truce");
    await expect(commitRename(state, withSessions(WORKING))).resolves.toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
describe("commitRename — an unchanged draft sends nothing and closes", () => {
  it("the original name untouched sends nothing and closes — S034_005_DoD3", async () => {
    const log = serveRenamed(NAMED);
    const state = editing(NAMED, "Harbour Night");
    await commitRename(state, withSessions(WORKING));
    expect(log).toEqual([]);
    expect(state.editingId).toBeNull();
  });

  it("the original name with surrounding whitespace sends nothing and closes — S034_005_DoD3", async () => {
    const log = serveRenamed(NAMED);
    const state = editing(NAMED, "  Harbour Night  ");
    await commitRename(state, withSessions(WORKING));
    expect(log).toEqual([]);
    expect(state.editingId).toBeNull();
  });

  it("an empty draft on a never-renamed session sends nothing and closes — S034_005_DoD3", async () => {
    const log = serveRenamed(UNNAMED);
    const state = editing(UNNAMED, "");
    await commitRename(state, withSessions(WORKING));
    expect(log).toEqual([]);
    expect(state.editingId).toBeNull();
  });

  it("a whitespace-only draft on a never-renamed session sends nothing and closes — S034_005_DoD3", async () => {
    const log = serveRenamed(UNNAMED);
    const state = editing(UNNAMED, "    ");
    await commitRename(state, withSessions(WORKING));
    expect(log).toEqual([]);
    expect(state.editingId).toBeNull();
  });

  it("changes no list, calls no callback and stays without an error — S034_005_DoD3", async () => {
    serveRenamed(NAMED);
    const sessions = withSessions(WORKING);
    const onRenamed = vi.fn<(session: Session) => void>();
    const state = editing(NAMED, "Harbour Night");
    await commitRename(state, sessions, onRenamed);
    expect(toJS(sessions.sessions)).toEqual(WORKING);
    expect(onRenamed).not.toHaveBeenCalled();
    expect(state.error).toBeNull();
    expect(state.pending).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("commitRename — one request in flight", () => {
  it("a second commit while the first is pending sends nothing (Enter then blur) — S034_005_DoD4", async () => {
    const answer = deferred<Response>();
    const log = stubFetch(() => answer.promise);
    const sessions = withSessions(WORKING);
    const state = editing(UNNAMED, "Dockside Truce");
    const first = commitRename(state, sessions);
    await flush();
    expect(state.pending).toBe(true);
    const second = commitRename(state, sessions);
    await flush();
    expect(log).toHaveLength(1);
    answer.resolve(jsonResponse(served(UNNAMED, "Dockside Truce"), 200));
    await expect(first).resolves.toBeUndefined();
    await expect(second).resolves.toBeUndefined();
    await flush();
    expect(log).toHaveLength(1);
  });

  it("a second commit with a different draft while pending also sends nothing — S034_005_DoD4", async () => {
    const answer = deferred<Response>();
    const log = stubFetch(() => answer.promise);
    const sessions = withSessions(WORKING);
    const state = editing(UNNAMED, "Dockside Truce");
    const first = commitRename(state, sessions);
    await flush();
    type(state, "Something Else");
    void commitRename(state, sessions);
    await flush();
    expect(log).toEqual([{ line: `PATCH ${sessionPath(UNNAMED_ID)}`, body: { name: "Dockside Truce" } }]);
    answer.resolve(jsonResponse(served(UNNAMED, "Dockside Truce"), 200));
    await first;
  });

  it("cancelRename while pending is ignored: the editor stays open — S034_005_DoD4", async () => {
    const answer = deferred<Response>();
    stubFetch(() => answer.promise);
    const state = editing(UNNAMED, "Dockside Truce");
    const running = commitRename(state, withSessions(WORKING));
    await flush();
    cancelRename(state);
    expect(state.editingId).toBe(UNNAMED_ID);
    expect(state.pending).toBe(true);
    answer.resolve(jsonResponse(served(UNNAMED, "Dockside Truce"), 200));
    await running;
  });

  it("beginRename while pending does nothing — S034_005_DoD4", async () => {
    const answer = deferred<Response>();
    stubFetch(() => answer.promise);
    const state = editing(UNNAMED, "Dockside Truce");
    const running = commitRename(state, withSessions(WORKING));
    await flush();
    const atPending = renameSnapshot(state);
    beginRename(state, NAMED);
    expect(renameSnapshot(state)).toEqual(atPending);
    answer.resolve(jsonResponse(served(UNNAMED, "Dockside Truce"), 200));
    await running;
  });

  it("cancelRename when nothing is pending closes and sends nothing — S034_005_DoD4", () => {
    const log = serveRenamed(NAMED);
    const state = editing(NAMED, "Changed but cancelled");
    cancelRename(state);
    expect(state.editingId).toBeNull();
    expect(log).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("commitRename — success applies the returned session, never optimistically", () => {
  it("before the response arrives the workspace list still holds the old session — S034_005_DoD5", async () => {
    const answer = deferred<Response>();
    stubFetch(() => answer.promise);
    const sessions = withSessions(WORKING);
    const onRenamed = vi.fn<(session: Session) => void>();
    const state = editing(UNNAMED, "Dockside Truce");
    const running = commitRename(state, sessions, onRenamed);
    await flush();
    expect(toJS(sessions.sessions)).toEqual(WORKING);
    expect(sessions.sessions[1].name).toBeNull();
    expect(onRenamed).not.toHaveBeenCalled();
    expect(state.editingId).toBe(UNNAMED_ID);
    expect(state.pending).toBe(true);
    answer.resolve(jsonResponse(served(UNNAMED, "Dockside Truce"), 200));
    await running;
  });

  it("on success the list holds the returned session at its index — S034_005_DoD5", async () => {
    const returned = served(UNNAMED, "Dockside Truce");
    serveRenamed(returned);
    const sessions = withSessions(WORKING);
    const state = editing(UNNAMED, "Dockside Truce");
    await commitRename(state, sessions);
    expect(toJS(sessions.sessions)).toEqual([NAMED, returned, OTHER]);
  });

  it("on success the callback receives the returned session exactly once — S034_005_DoD5", async () => {
    const returned = served(NAMED, "Harbour Night II");
    serveRenamed(returned);
    const onRenamed = vi.fn<(session: Session) => void>();
    const state = editing(NAMED, "Harbour Night II");
    await commitRename(state, withSessions(WORKING), onRenamed);
    expect(onRenamed).toHaveBeenCalledTimes(1);
    expect(onRenamed.mock.calls[0][0]).toEqual(returned);
  });

  it("on success the editor is closed, nothing pending and no error — S034_005_DoD5", async () => {
    serveRenamed(served(NAMED, null));
    const state = editing(NAMED, "  ");
    await commitRename(state, withSessions(WORKING));
    expect(state.editingId).toBeNull();
    expect(state.pending).toBe(false);
    expect(state.error).toBeNull();
  });

  it("the list holds what the server returned, not the draft — S034_005_DoD5", async () => {
    // The server's stored value is authoritative; the client applies the returned row.
    const returned = served(UNNAMED, "Dockside Truce (stored)");
    serveRenamed(returned);
    const sessions = withSessions(WORKING);
    const onRenamed = vi.fn<(session: Session) => void>();
    const state = editing(UNNAMED, "Dockside Truce");
    await commitRename(state, sessions, onRenamed);
    expect(sessions.sessions[1].name).toBe("Dockside Truce (stored)");
    expect(onRenamed.mock.calls[0][0].name).toBe("Dockside Truce (stored)");
  });

  it("succeeds without a callback — S034_005_DoD5", async () => {
    const returned = served(OTHER, "Old Road");
    serveRenamed(returned);
    const sessions = withSessions(WORKING);
    const state = editing(OTHER, "Old Road");
    await expect(commitRename(state, sessions)).resolves.toBeUndefined();
    expect(toJS(sessions.sessions)).toEqual([NAMED, UNNAMED, returned]);
    expect(state.editingId).toBeNull();
  });

  it("raises no notification on success — S034_005_DoD5", async () => {
    serveRenamed(served(UNNAMED, "Dockside Truce"));
    const state = editing(UNNAMED, "Dockside Truce");
    await commitRename(state, withSessions(WORKING));
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("commitRename — failure is inline and changes no list", () => {
  const failures: Array<[string, () => Promise<Response>]> = [
    ["a 404 session_not_found", () => Promise.resolve(envelope("session_not_found", 404))],
    ["a 422 validation refusal", () => Promise.resolve(envelope("validation_error", 422))],
    ["a 500", () => Promise.resolve(envelope("internal_error", 500))],
    ["a transport failure", () => Promise.reject(new TypeError("Failed to fetch"))],
  ];

  for (const [label, answer] of failures) {
    it(`${label}: the error is the fixed sentence and the editor stays open with the draft — S034_005_DoD6`, async () => {
      stubFetch(answer);
      const state = editing(UNNAMED, "  Dockside Truce ");
      await expect(commitRename(state, withSessions(WORKING))).resolves.toBeUndefined();
      expect(state.error).toBe(FAILURE_SENTENCE);
      expect(state.editingId).toBe(UNNAMED_ID);
      expect(state.draft).toBe("  Dockside Truce ");
      expect(state.pending).toBe(false);
    });

    it(`${label}: the workspace list is unchanged, no callback, no notification — S034_005_DoD6`, async () => {
      stubFetch(answer);
      const sessions = withSessions(WORKING);
      const onRenamed = vi.fn<(session: Session) => void>();
      const state = editing(NAMED, "Harbour Night II");
      await commitRename(state, sessions, onRenamed);
      expect(toJS(sessions.sessions)).toEqual(WORKING);
      expect(onRenamed).not.toHaveBeenCalled();
      expect(notifyFailureSpy).not.toHaveBeenCalled();
    });
  }

  it("after a failure the same draft can be committed again and succeeds — S034_005_DoD6", async () => {
    let calls = 0;
    const returned = served(UNNAMED, "Dockside Truce");
    const log = stubFetch(() => {
      calls += 1;
      return Promise.resolve(calls === 1 ? envelope("internal_error", 500) : jsonResponse(returned, 200));
    });
    const sessions = withSessions(WORKING);
    const state = editing(UNNAMED, "Dockside Truce");
    await commitRename(state, sessions);
    expect(state.error).toBe(FAILURE_SENTENCE);
    await commitRename(state, sessions);
    expect(log).toHaveLength(2);
    expect(state.editingId).toBeNull();
    expect(toJS(sessions.sessions)).toEqual([NAMED, returned, OTHER]);
  });
});

// ---------------------------------------------------------------------------
describe("commitRename — an aborted commit writes nothing", () => {
  it("abort before the response settles: neither store changes after the abort — S034_005_DoD7", async () => {
    stubFetch(
      (init) =>
        new Promise<Response>((_resolve, reject) => {
          const signal = init?.signal;
          signal?.addEventListener("abort", () => {
            reject(signal.reason ?? new DOMException("The operation was aborted.", "AbortError"));
          });
        }),
    );
    const sessions = withSessions(WORKING);
    const onRenamed = vi.fn<(session: Session) => void>();
    const state = editing(UNNAMED, "Dockside Truce");
    const controller = new AbortController();
    const running = commitRename(state, sessions, onRenamed, controller.signal);
    await flush();
    const atAbort = renameSnapshot(state);
    controller.abort();
    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(renameSnapshot(state)).toEqual(atAbort);
    expect(state.error).toBeNull();
    expect(toJS(sessions.sessions)).toEqual(WORKING);
    expect(onRenamed).not.toHaveBeenCalled();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("a success arriving after the abort is not applied — S034_005_DoD7", async () => {
    const answer = deferred<Response>();
    stubFetch(() => answer.promise);
    const sessions = withSessions(WORKING);
    const onRenamed = vi.fn<(session: Session) => void>();
    const state = editing(UNNAMED, "Dockside Truce");
    const controller = new AbortController();
    const running = commitRename(state, sessions, onRenamed, controller.signal);
    await flush();
    const atAbort = renameSnapshot(state);
    controller.abort();
    answer.resolve(jsonResponse(served(UNNAMED, "Dockside Truce"), 200));
    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(renameSnapshot(state)).toEqual(atAbort);
    expect(toJS(sessions.sessions)).toEqual(WORKING);
    expect(onRenamed).not.toHaveBeenCalled();
  });

  it("a failure arriving after the abort writes no error — S034_005_DoD7", async () => {
    const answer = deferred<Response>();
    stubFetch(() => answer.promise);
    const sessions = withSessions(WORKING);
    const state = editing(UNNAMED, "Dockside Truce");
    const controller = new AbortController();
    const running = commitRename(state, sessions, undefined, controller.signal);
    await flush();
    const atAbort = renameSnapshot(state);
    controller.abort();
    answer.resolve(envelope("internal_error", 500));
    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(renameSnapshot(state)).toEqual(atAbort);
    expect(state.error).toBeNull();
    expect(toJS(sessions.sessions)).toEqual(WORKING);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});
