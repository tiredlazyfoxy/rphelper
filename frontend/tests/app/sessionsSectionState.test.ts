// Feature 011, step 007 — the Sessions section's state (DoD-1..DoD-12).
//
// Amended by feature 033, step 005 (D9): the message-less start is dropped, so
// `startSessionFromSection`, `selectSetup`, `loadSetupChoices` and the fields `setups`,
// `setupsStatus`, `selectedSetupId`, `startStatus` and `startError` are removed from the state.
// 011's DoD-3 (the setup choices), DoD-4 (the selection), DoD-5..DoD-7 (the start) clauses and
// every assertion on those fields are retired; the remaining clauses are unchanged.
//
// Every expected value here comes from the specification, never from the implementation:
// `007.sessions-section-state.md`'s Interface intent and Definition of done, and `context.md`'s
// D1, D5, D15 (apply the returned row to **both** states), D18 (the fixed sentences, asserted as
// literals), plus the "Never optimistic" and "Ids are strings" constraints. Bindings come from
// status.md's `### Step 007 — frozen interface` (011) and `### Step 005 — frozen interface` (033).
//
// Test conventions: Vitest with `globals: false` (every symbol imported explicitly), one
// `fetch` stub per test via `vi.stubGlobal`, each `it` title ending `— DoD-N`, and stubs /
// request assertions keyed on the **exact pathname plus query string** — never a prefix.
// Fixture ids are past Number.MAX_SAFE_INTEGER and their `last_used_at` order is
// deliberately the reverse of their id order, so anything ordering by id is caught.
import { autorun, runInAction, toJS } from "mobx";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Session } from "../../src/app/sessionsApi";
import {
  applySectionSession,
  archiveSectionRow,
  loadSectionSessions,
  restoreSectionRow,
  SessionsSectionState,
  setShowArchived,
} from "../../src/app/sessionsSectionState";
import { SessionsState } from "../../src/app/sessionsState";
import type { Setup } from "../../src/app/setupsApi";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const CHARACTER_ID = "7250000000000000001";
const SESSIONS_PATH = `/api/characters/${CHARACTER_ID}/sessions`;
const FAILURE_MESSAGE = "The session ledger tore gq-41.";

// D18's sentences, verbatim from the step file. Deliberately literal: the module's own
// constants are not exported and nothing may assert against them.
const ARCHIVE_FAILED = "Could not archive the session.";
const RESTORE_FAILED = "Could not restore the session.";

// ------------------------------------------------------------------ setups (row labels only)

const SETUP_ONE: Setup = {
  id: "7260000000000000001",
  character_id: CHARACTER_ID,
  name: "The Gilded Tavern",
  description: "# The Gilded Tavern\n\nSmoke and lute strings.",
  archived_at: null,
  created_at: "2026-02-01T10:00:00.000000+00:00",
  updated_at: "2026-02-01T10:00:00.000000+00:00",
};
const SETUP_TWO: Setup = {
  id: "7260000000000000002",
  character_id: CHARACTER_ID,
  name: "Nightfall Harbour",
  description: "# Nightfall Harbour\n\nTwo ships, no harbourmaster.",
  archived_at: null,
  created_at: "2026-02-02T10:00:00.000000+00:00",
  updated_at: "2026-02-02T10:00:00.000000+00:00",
};
const SETUP_THREE: Setup = {
  id: "7260000000000000003",
  character_id: CHARACTER_ID,
  name: "The Salt Cellar",
  description: "# The Salt Cellar\n\nA room below a room.",
  archived_at: null,
  created_at: "2026-02-03T10:00:00.000000+00:00",
  updated_at: "2026-02-03T10:00:00.000000+00:00",
};

// ------------------------------------------------------------------ sessions
// Ids ascend while last_used_at descends.

const DAWN: Session = {
  id: "7270000000000000001",
  character_id: CHARACTER_ID,
  setup_id: SETUP_ONE.id,
  setup_name: SETUP_ONE.name,
  archived_at: null,
  last_used_at: "2026-03-14T09:26:53.000000+00:00",
  created_at: "2026-03-14T09:26:53.000000+00:00",
  updated_at: "2026-03-14T09:26:53.000000+00:00",
};
const NOON: Session = {
  id: "7270000000000000002",
  character_id: CHARACTER_ID,
  setup_id: SETUP_TWO.id,
  setup_name: SETUP_TWO.name,
  archived_at: null,
  last_used_at: "2026-03-10T11:00:00.000000+00:00",
  created_at: "2026-03-10T11:00:00.000000+00:00",
  updated_at: "2026-03-10T11:00:00.000000+00:00",
};
const DUSK: Session = {
  id: "7270000000000000003",
  character_id: CHARACTER_ID,
  setup_id: null,
  setup_name: null,
  archived_at: null,
  last_used_at: "2026-03-01T08:15:42.000000+00:00",
  created_at: "2026-03-01T08:15:42.000000+00:00",
  updated_at: "2026-03-01T08:15:42.000000+00:00",
};

/** The server's D14 order: newest last use first. */
const WORKING: Session[] = [DAWN, NOON, DUSK];

/** last_used_at newer than every row in WORKING. */
const NEWEST: Session = {
  id: "7270000000000000004",
  character_id: CHARACTER_ID,
  setup_id: null,
  setup_name: null,
  archived_at: null,
  last_used_at: "2026-04-02T00:00:00.000000+00:00",
  created_at: "2026-04-02T00:00:00.000000+00:00",
  updated_at: "2026-04-02T00:00:00.000000+00:00",
};
/** last_used_at between NOON's and DUSK's. */
const BETWEEN: Session = {
  id: "7270000000000000005",
  character_id: CHARACTER_ID,
  setup_id: SETUP_ONE.id,
  setup_name: SETUP_ONE.name,
  archived_at: null,
  last_used_at: "2026-03-05T12:00:00.000000+00:00",
  created_at: "2026-03-05T12:00:00.000000+00:00",
  updated_at: "2026-03-05T12:00:00.000000+00:00",
};
/** last_used_at older than every row in WORKING. */
const OLDEST: Session = {
  id: "7270000000000000006",
  character_id: CHARACTER_ID,
  setup_id: null,
  setup_name: null,
  archived_at: null,
  last_used_at: "2026-01-02T03:04:05.000000+00:00",
  created_at: "2026-01-02T03:04:05.000000+00:00",
  updated_at: "2026-01-02T03:04:05.000000+00:00",
};
/** last_used_at exactly equal to NOON's, with a *lower* id than NOON. */
const TIED_WITH_NOON: Session = {
  id: "7270000000000000000",
  character_id: CHARACTER_ID,
  setup_id: null,
  setup_name: null,
  archived_at: null,
  last_used_at: NOON.last_used_at,
  created_at: NOON.created_at,
  updated_at: NOON.updated_at,
};

const ARCHIVED_AT = "2026-05-05T10:00:00.000000+00:00";

function archivedCopy(session: Session): Session {
  return { ...session, archived_at: ARCHIVED_AT, updated_at: ARCHIVED_AT };
}

function restoredCopy(session: Session): Session {
  return { ...session, archived_at: null, updated_at: "2026-05-06T10:00:00.000000+00:00" };
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

function failureResponse(): Response {
  return jsonResponse(
    { error: { code: "internal_error", message: FAILURE_MESSAGE, detail: {} } },
    500,
  );
}

function copyRows<T extends object>(rows: readonly T[]): T[] {
  return rows.map((row) => ({ ...row }));
}

function serveSessionList(rows: readonly Session[]) {
  return stubFetch(() => Promise.resolve(jsonResponse({ sessions: copyRows(rows) }, 200)));
}

function serveSession(session: Session, status = 200) {
  return stubFetch(() => Promise.resolve(jsonResponse({ ...session }, status)));
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

type Seen = { method: string; path: string; search: string };

/** Exact pathname plus query string per call — never a prefix match. */
function seen(mock: ReturnType<typeof stubFetch>): Seen[] {
  return mock.mock.calls.map(([input, init]) => {
    const url = requestUrl(input);
    return { method: requestMethod(input, init), path: url.pathname, search: url.search };
  });
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

/** Every one of the remaining observable fields (033 D9), for an "unchanged" comparison. */
function snapshot(state: SessionsSectionState) {
  return {
    characterId: state.characterId,
    sessions: toJS(state.sessions),
    status: state.status,
    showArchived: state.showArchived,
    error: state.error,
    pendingId: state.pendingId,
  };
}

function ids(state: SessionsSectionState): string[] {
  return state.sessions.map((row) => row.id);
}

function listed(state: SessionsSectionState, sessionId: string): Session | undefined {
  return toJS(state.sessions).find((row) => row.id === sessionId);
}

function workspaceIds(workspace: SessionsState): string[] {
  return workspace.sessions.map((row) => row.id);
}

function workspaceRow(workspace: SessionsState, sessionId: string): Session | undefined {
  return toJS(workspace.sessions).find((row) => row.id === sessionId);
}

/** A section state already loaded with rows, as it would be after its first load. */
function withSessions(rows: readonly Session[], showArchived = false): SessionsSectionState {
  const state = new SessionsSectionState(CHARACTER_ID);
  runInAction(() => {
    state.sessions = copyRows(rows);
    state.status = "ready";
    state.showArchived = showArchived;
  });
  return state;
}

/** A real workspace SessionsState holding the working list the tree would show. */
function workspaceWith(rows: readonly Session[]): SessionsState {
  const workspace = new SessionsState();
  runInAction(() => {
    workspace.sessions = copyRows(rows);
    workspace.status = "ready";
  });
  return workspace;
}

// ---------------------------------------------------------------------------
describe("a fresh SessionsSectionState", () => {
  it("has the character id as constructed and every other field at its initial value — DoD-1", () => {
    expect(snapshot(new SessionsSectionState("c1"))).toEqual({
      characterId: "c1",
      sessions: [],
      status: "idle",
      showArchived: false,
      error: null,
      pendingId: null,
    });
  });
});

// ---------------------------------------------------------------------------
describe("loadSectionSessions", () => {
  it("is loading while the request is pending, then ready — DoD-2", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = new SessionsSectionState(CHARACTER_ID);
    const running = loadSectionSessions(state);
    await flush();
    expect(state.status).toBe("loading");
    pending.resolve(jsonResponse({ sessions: copyRows(WORKING) }, 200));
    await expect(running).resolves.toBeUndefined();
    expect(state.status).toBe("ready");
  });

  it("requests exactly GET /api/characters/c1/sessions with no query string while showArchived is false — DoD-2", async () => {
    const mock = serveSessionList(WORKING);
    await loadSectionSessions(new SessionsSectionState(CHARACTER_ID));
    expect(seen(mock)).toEqual([{ method: "GET", path: SESSIONS_PATH, search: "" }]);
  });

  it("requests ?include_archived=true only while showArchived is true — DoD-2", async () => {
    const mock = serveSessionList(WORKING);
    const state = new SessionsSectionState(CHARACTER_ID);
    setShowArchived(state, true);
    await loadSectionSessions(state);
    expect(seen(mock)).toEqual([
      { method: "GET", path: SESSIONS_PATH, search: "?include_archived=true" },
    ]);
  });

  it("writes exactly the server's rows in the server's order — DoD-2", async () => {
    serveSessionList(WORKING);
    const state = new SessionsSectionState(CHARACTER_ID);
    await loadSectionSessions(state);
    expect(toJS(state.sessions)).toEqual([DAWN, NOON, DUSK]);
    expect(state.status).toBe("ready");
  });

  it("keeps the server's order verbatim and never re-sorts it client-side — DoD-2", async () => {
    serveSessionList([DUSK, DAWN, NOON]);
    const state = new SessionsSectionState(CHARACTER_ID);
    await loadSectionSessions(state);
    expect(ids(state)).toEqual([DUSK.id, DAWN.id, NOON.id]);
  });

  it("an empty listing is ready with no rows — DoD-2", async () => {
    serveSessionList([]);
    const state = new SessionsSectionState(CHARACTER_ID);
    await loadSectionSessions(state);
    expect(toJS(state.sessions)).toEqual([]);
    expect(state.status).toBe("ready");
  });

  it("a failed request is failed, keeps the rows and resolves without throwing — DoD-2", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    const state = withSessions(WORKING);
    await expect(loadSectionSessions(state)).resolves.toBeUndefined();
    expect(state.status).toBe("failed");
    expect(toJS(state.sessions)).toEqual([DAWN, NOON, DUSK]);
  });

  it("a transport failure is failed too, not a rejection — DoD-2", async () => {
    stubFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    const state = withSessions(WORKING);
    await expect(loadSectionSessions(state)).resolves.toBeUndefined();
    expect(state.status).toBe("failed");
    expect(toJS(state.sessions)).toEqual([DAWN, NOON, DUSK]);
  });

  it("writes nothing once its signal has aborted — DoD-2", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = withSessions(WORKING);
    const controller = new AbortController();
    const running = loadSectionSessions(state, controller.signal);
    await flush();
    const atAbort = snapshot(state);
    controller.abort();
    pending.resolve(jsonResponse({ sessions: copyRows([NEWEST]) }, 200));
    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(snapshot(state)).toEqual(atAbort);
  });

  it("writes nothing when an abort rejection arrives instead of a response — DoD-2", async () => {
    stubFetch(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          const signal = init?.signal;
          signal?.addEventListener("abort", () => {
            const abortError = new Error("The operation was aborted.");
            abortError.name = "AbortError";
            reject(abortError);
          });
        }),
    );
    const state = withSessions(WORKING);
    const controller = new AbortController();
    const running = loadSectionSessions(state, controller.signal);
    await flush();
    const atAbort = snapshot(state);
    controller.abort();
    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(snapshot(state)).toEqual(atAbort);
  });
});

// ---------------------------------------------------------------------------
describe("applySectionSession — an absent working row is inserted by last_used_at descending", () => {
  it("a row with the newest last use lands first — DoD-8", () => {
    const state = withSessions(WORKING);
    applySectionSession(state, NEWEST);
    expect(ids(state)).toEqual([NEWEST.id, DAWN.id, NOON.id, DUSK.id]);
    expect(toJS(state.sessions)[0]).toEqual(NEWEST);
  });

  it("a row whose last use falls between two rows lands between them — DoD-8", () => {
    const state = withSessions(WORKING);
    applySectionSession(state, BETWEEN);
    expect(ids(state)).toEqual([DAWN.id, NOON.id, BETWEEN.id, DUSK.id]);
  });

  it("a row with the oldest last use lands last — DoD-8", () => {
    const state = withSessions(WORKING);
    applySectionSession(state, OLDEST);
    expect(ids(state)).toEqual([DAWN.id, NOON.id, DUSK.id, OLDEST.id]);
  });

  it("a row whose last use equals an existing one lands after the equal rows, never by id — DoD-8", () => {
    const state = withSessions(WORKING);
    applySectionSession(state, TIED_WITH_NOON);
    expect(ids(state)).toEqual([DAWN.id, NOON.id, TIED_WITH_NOON.id, DUSK.id]);
  });

  it("the first row of an empty list is simply inserted — DoD-8", () => {
    const state = withSessions([]);
    applySectionSession(state, BETWEEN);
    expect(toJS(state.sessions)).toEqual([BETWEEN]);
  });
});

// ---------------------------------------------------------------------------
describe("applySectionSession — a present row", () => {
  it("keeps its index with the new values when last_used_at is unchanged — DoD-8", () => {
    const state = withSessions(WORKING);
    const relabelled: Session = {
      ...NOON,
      setup_name: "Nightfall Harbour, renamed",
      updated_at: "2026-05-07T12:00:00.000000+00:00",
    };
    applySectionSession(state, relabelled);
    expect(ids(state)).toEqual([DAWN.id, NOON.id, DUSK.id]);
    expect(toJS(state.sessions)).toEqual([DAWN, relabelled, DUSK]);
  });

  it("keeps the first row first when its last_used_at is unchanged — DoD-8", () => {
    const state = withSessions(WORKING);
    const relabelled: Session = { ...DAWN, setup_name: "The Gilded Cage" };
    applySectionSession(state, relabelled);
    expect(toJS(state.sessions)).toEqual([relabelled, NOON, DUSK]);
  });

  it("keeps its index with the new values while showArchived is true as well — DoD-8", () => {
    const state = withSessions(WORKING, true);
    const relabelled: Session = { ...DUSK, setup_name: SETUP_THREE.name, setup_id: SETUP_THREE.id };
    applySectionSession(state, relabelled);
    expect(toJS(state.sessions)).toEqual([DAWN, NOON, relabelled]);
  });
});

// ---------------------------------------------------------------------------
describe("applySectionSession — an archived row against the Show archived sessions flag", () => {
  it("removes a now-archived row while showArchived is false — DoD-8", () => {
    const state = withSessions(WORKING);
    applySectionSession(state, archivedCopy(NOON));
    expect(toJS(state.sessions)).toEqual([DAWN, DUSK]);
  });

  it("is a no-op for an archived row that is absent while showArchived is false — DoD-8", () => {
    const state = withSessions(WORKING);
    applySectionSession(state, archivedCopy(NEWEST));
    expect(toJS(state.sessions)).toEqual([DAWN, NOON, DUSK]);
  });

  it("leaves an empty list empty for an absent archived row while showArchived is false — DoD-8", () => {
    const state = withSessions([]);
    applySectionSession(state, archivedCopy(NEWEST));
    expect(toJS(state.sessions)).toEqual([]);
  });

  it("keeps a now-archived row in place with its archived_at while showArchived is true — DoD-8", () => {
    const state = withSessions(WORKING, true);
    const archived = archivedCopy(NOON);
    applySectionSession(state, archived);
    expect(toJS(state.sessions)).toEqual([DAWN, archived, DUSK]);
    expect(listed(state, NOON.id)?.archived_at).toBe(ARCHIVED_AT);
  });

  it("inserts an absent archived row by last_used_at while showArchived is true — DoD-8", () => {
    const state = withSessions(WORKING, true);
    const archived = archivedCopy(BETWEEN);
    applySectionSession(state, archived);
    expect(ids(state)).toEqual([DAWN.id, NOON.id, BETWEEN.id, DUSK.id]);
    expect(listed(state, BETWEEN.id)).toEqual(archived);
  });

  it("a restored row replaces its archived self in place while showArchived is true — DoD-8", () => {
    const restored = restoredCopy(NOON);
    const state = withSessions([DAWN, archivedCopy(NOON), DUSK], true);
    applySectionSession(state, restored);
    expect(toJS(state.sessions)).toEqual([DAWN, restored, DUSK]);
  });
});

// ---------------------------------------------------------------------------
describe("archiveSectionRow", () => {
  it("POSTs /api/sessions/<id>/archive, once — DoD-9", async () => {
    const mock = serveSession(archivedCopy(NOON));
    const state = withSessions(WORKING);
    await archiveSectionRow(state, workspaceWith(WORKING), NOON.id);
    expect(seen(mock)).toEqual([
      { method: "POST", path: `/api/sessions/${NOON.id}/archive`, search: "" },
    ]);
  });

  it("holds pendingId and keeps the row in both states while the request is pending — DoD-9", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = withSessions(WORKING);
    const workspace = workspaceWith(WORKING);

    const running = archiveSectionRow(state, workspace, NOON.id);
    await flush();
    expect(state.pendingId).toBe(NOON.id);
    expect(ids(state)).toEqual([DAWN.id, NOON.id, DUSK.id]);
    expect(listed(state, NOON.id)).toEqual(NOON);
    expect(workspaceIds(workspace)).toEqual([DAWN.id, NOON.id, DUSK.id]);

    pending.resolve(jsonResponse(archivedCopy(NOON), 200));
    await expect(running).resolves.toBeUndefined();
    expect(state.pendingId).toBeNull();
  });

  it("with showArchived false drops the row from the section and the workspace state — DoD-9", async () => {
    serveSession(archivedCopy(NOON));
    const state = withSessions(WORKING);
    const workspace = workspaceWith(WORKING);
    await expect(archiveSectionRow(state, workspace, NOON.id)).resolves.toBeUndefined();
    expect(ids(state)).toEqual([DAWN.id, DUSK.id]);
    expect(workspaceIds(workspace)).toEqual([DAWN.id, DUSK.id]);
    expect(state.pendingId).toBeNull();
    expect(state.error).toBeNull();
  });

  it("with showArchived true keeps the row in the section with the response's archived_at — DoD-9", async () => {
    const archived = archivedCopy(NOON);
    serveSession(archived);
    const state = withSessions(WORKING, true);
    const workspace = workspaceWith(WORKING);
    await archiveSectionRow(state, workspace, NOON.id);
    expect(ids(state)).toEqual([DAWN.id, NOON.id, DUSK.id]);
    expect(listed(state, NOON.id)).toEqual(archived);
    expect(listed(state, NOON.id)?.archived_at).toBe(ARCHIVED_AT);
    expect(state.pendingId).toBeNull();
  });

  it("with showArchived true the row is still gone from the working workspace list — DoD-9", async () => {
    serveSession(archivedCopy(NOON));
    const state = withSessions(WORKING, true);
    const workspace = workspaceWith(WORKING);
    await archiveSectionRow(state, workspace, NOON.id);
    expect(workspaceIds(workspace)).toEqual([DAWN.id, DUSK.id]);
    expect(workspaceRow(workspace, NOON.id)).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
describe("restoreSectionRow", () => {
  it("POSTs /api/sessions/<id>/restore, once — DoD-10", async () => {
    const mock = serveSession(restoredCopy(NOON));
    const state = withSessions([DAWN, archivedCopy(NOON), DUSK], true);
    await restoreSectionRow(state, workspaceWith([DAWN, DUSK]), NOON.id);
    expect(seen(mock)).toEqual([
      { method: "POST", path: `/api/sessions/${NOON.id}/restore`, search: "" },
    ]);
  });

  it("leaves the section row with archived_at null — DoD-10", async () => {
    const restored = restoredCopy(NOON);
    serveSession(restored);
    const state = withSessions([DAWN, archivedCopy(NOON), DUSK], true);
    await expect(
      restoreSectionRow(state, workspaceWith([DAWN, DUSK]), NOON.id),
    ).resolves.toBeUndefined();
    expect(listed(state, NOON.id)).toEqual(restored);
    expect(listed(state, NOON.id)?.archived_at).toBeNull();
    expect(state.pendingId).toBeNull();
  });

  it("puts the row back into the workspace state at its last_used_at position — DoD-10", async () => {
    const restored = restoredCopy(NOON);
    serveSession(restored);
    const state = withSessions([DAWN, archivedCopy(NOON), DUSK], true);
    const workspace = workspaceWith([DAWN, DUSK]);
    await restoreSectionRow(state, workspace, NOON.id);
    expect(workspaceIds(workspace)).toEqual([DAWN.id, NOON.id, DUSK.id]);
    expect(workspaceRow(workspace, NOON.id)).toEqual(restored);
  });

  it("holds pendingId while the request is pending, then clears it — DoD-10", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = withSessions([DAWN, archivedCopy(NOON), DUSK], true);
    const workspace = workspaceWith([DAWN, DUSK]);
    const running = restoreSectionRow(state, workspace, NOON.id);
    await flush();
    expect(state.pendingId).toBe(NOON.id);
    expect(workspaceIds(workspace)).toEqual([DAWN.id, DUSK.id]);
    pending.resolve(jsonResponse(restoredCopy(NOON), 200));
    await expect(running).resolves.toBeUndefined();
    expect(state.pendingId).toBeNull();
  });

  it("a row restored while showArchived is false still lands in both lists — DoD-10", async () => {
    const restored = restoredCopy(NOON);
    serveSession(restored);
    const state = withSessions([DAWN, archivedCopy(NOON), DUSK], false);
    const workspace = workspaceWith([DAWN, DUSK]);
    await restoreSectionRow(state, workspace, NOON.id);
    expect(ids(state)).toEqual([DAWN.id, NOON.id, DUSK.id]);
    expect(workspaceIds(workspace)).toEqual([DAWN.id, NOON.id, DUSK.id]);
  });
});

// ---------------------------------------------------------------------------
describe("a failed row action", () => {
  it("archiveSectionRow reports \"Could not archive the session.\" and changes neither state — DoD-11", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    const state = withSessions(WORKING);
    const workspace = workspaceWith(WORKING);
    await expect(archiveSectionRow(state, workspace, NOON.id)).resolves.toBeUndefined();
    expect(state.error).toBe(ARCHIVE_FAILED);
    expect(toJS(state.sessions)).toEqual([DAWN, NOON, DUSK]);
    expect(toJS(workspace.sessions)).toEqual([DAWN, NOON, DUSK]);
    expect(state.pendingId).toBeNull();
  });

  it("restoreSectionRow reports \"Could not restore the session.\" and changes neither state — DoD-11", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    const rows = [DAWN, archivedCopy(NOON), DUSK];
    const state = withSessions(rows, true);
    const workspace = workspaceWith([DAWN, DUSK]);
    await expect(restoreSectionRow(state, workspace, NOON.id)).resolves.toBeUndefined();
    expect(state.error).toBe(RESTORE_FAILED);
    expect(toJS(state.sessions)).toEqual(rows);
    expect(toJS(workspace.sessions)).toEqual([DAWN, DUSK]);
    expect(state.pendingId).toBeNull();
  });

  it("a transport failure reports the same sentence and does not reject — DoD-11", async () => {
    stubFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    const state = withSessions(WORKING);
    const workspace = workspaceWith(WORKING);
    await expect(archiveSectionRow(state, workspace, NOON.id)).resolves.toBeUndefined();
    expect(state.error).toBe(ARCHIVE_FAILED);
    expect(toJS(state.sessions)).toEqual([DAWN, NOON, DUSK]);
    expect(toJS(workspace.sessions)).toEqual([DAWN, NOON, DUSK]);
    expect(state.pendingId).toBeNull();
  });

  it("a later restore has cleared the previous error before its request — DoD-11", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    const state = withSessions([DAWN, archivedCopy(NOON), DUSK], true);
    const workspace = workspaceWith([DAWN, DUSK]);
    await archiveSectionRow(state, workspace, DAWN.id);
    expect(state.error).toBe(ARCHIVE_FAILED);

    const errorAtRequest: Array<string | null> = [];
    stubFetch(() => {
      errorAtRequest.push(state.error);
      return Promise.resolve(jsonResponse(restoredCopy(NOON), 200));
    });
    await expect(restoreSectionRow(state, workspace, NOON.id)).resolves.toBeUndefined();
    expect(errorAtRequest).toEqual([null]);
    expect(state.error).toBeNull();
  });

  it("a later archive that also fails has cleared the previous error before its request — DoD-11", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    const state = withSessions(WORKING);
    const workspace = workspaceWith(WORKING);
    await archiveSectionRow(state, workspace, NOON.id);

    const errorAtRequest: Array<string | null> = [];
    stubFetch(() => {
      errorAtRequest.push(state.error);
      return Promise.resolve(failureResponse());
    });
    await archiveSectionRow(state, workspace, DAWN.id);
    expect(errorAtRequest).toEqual([null]);
    expect(state.error).toBe(ARCHIVE_FAILED);
  });
});

// ---------------------------------------------------------------------------
describe("setShowArchived and the observability of the writes", () => {
  it("sets the flag and issues no request — DoD-12", () => {
    const mock = stubFetch(() => Promise.resolve(jsonResponse({ sessions: [] }, 200)));
    const state = withSessions(WORKING);
    setShowArchived(state, true);
    expect(state.showArchived).toBe(true);
    setShowArchived(state, false);
    expect(state.showArchived).toBe(false);
    expect(mock).not.toHaveBeenCalled();
  });

  it("leaves the rows and the status alone — DoD-12", () => {
    const state = withSessions(WORKING);
    setShowArchived(state, true);
    expect(toJS(state.sessions)).toEqual([DAWN, NOON, DUSK]);
    expect(state.status).toBe("ready");
  });

  it("an autorun reading sessions re-runs after applySectionSession — DoD-12", () => {
    const state = withSessions(WORKING);
    const observed: string[][] = [];
    const dispose = autorun(() => {
      observed.push(state.sessions.map((row) => row.id));
    });
    expect(observed).toHaveLength(1);
    applySectionSession(state, NEWEST);
    expect(observed.length).toBeGreaterThan(1);
    expect(observed[observed.length - 1]).toEqual([NEWEST.id, DAWN.id, NOON.id, DUSK.id]);
    dispose();
  });

  it("an autorun reading sessions re-runs after an archived row is dropped — DoD-12", () => {
    const state = withSessions(WORKING);
    const observed: string[][] = [];
    const dispose = autorun(() => {
      observed.push(state.sessions.map((row) => row.id));
    });
    expect(observed).toHaveLength(1);
    applySectionSession(state, archivedCopy(NOON));
    expect(observed.length).toBeGreaterThan(1);
    expect(observed[observed.length - 1]).toEqual([DAWN.id, DUSK.id]);
    dispose();
  });

  it("an autorun reading showArchived re-runs after setShowArchived — DoD-12", () => {
    const state = withSessions(WORKING);
    const observed: boolean[] = [];
    const dispose = autorun(() => {
      observed.push(state.showArchived);
    });
    expect(observed).toEqual([false]);
    setShowArchived(state, true);
    expect(observed).toEqual([false, true]);
    dispose();
  });
});
