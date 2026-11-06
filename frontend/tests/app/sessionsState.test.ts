// Feature 011, step 004 — the workspace sessions state (DoD-4..DoD-9).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 004.context.md ("The insert position, concretely" and "orderCharactersByUse without
// importing 009") and context.md's D5 (the workspace list is working-only), D6 (character
// order), D14 (the server's order) and D15 (the upsert), plus the "No context, no methods"
// and "Ids are strings" constraints.
//
// loadSessions sets "loading", writes the server's rows in the server's order, writes
// "failed" without rejecting and writes nothing once aborted. applySession removes an
// archived row and never inserts one; a working row is removed if present and inserted
// before the first existing row whose last_used_at is less than the new one's, else at the
// end. Every fixture's last_used_at order is deliberately the reverse of its id order, so an
// accidental id-only sort would be caught; every id is past Number.MAX_SAFE_INTEGER.
//
// Amended by feature 034, step 005 (DoD-9; DEC-034-12): ties on last_used_at are now ordered by
// id descending — the server's own list order (last_used_at DESC, id DESC) — comparing the
// decimal-string ids as numbers, never as text and never through Number. Re-applying a row whose
// last_used_at is unchanged therefore keeps its index, even among several equal rows. 011's
// "equal values land after the equal rows" clause is replaced: TIED (higher id) now lands before
// SECOND.
import { autorun, isComputedProp, isObservableProp, runInAction, toJS } from "mobx";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Session } from "../../src/app/sessionsApi";
import {
  applySession,
  loadSessions,
  orderCharactersByUse,
  SessionsState,
  sessionsOfCharacter,
} from "../../src/app/sessionsState";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const LIST_PATH = "/api/sessions";
const FAILURE_MESSAGE = "The session ledger is on fire zq-63.";

const ALMA_ID = "7250000000000000001";
const BRENN_ID = "7250000000000000002";
const CORVIN_ID = "7250000000000000003";
const SETUP_ID = "7250000000000000009";

const ARCHIVED_AT = "2026-04-05T10:00:00.000000+00:00";

function makeSession(
  id: string,
  characterId: string,
  lastUsedAt: string,
  extra: Partial<Session> = {},
): Session {
  return {
    id,
    character_id: characterId,
    setup_id: null,
    setup_name: null,
    name: null, // 034 step 004: a required Session key; never renamed unless `extra` says so.
    archived_at: null,
    last_used_at: lastUsedAt,
    created_at: lastUsedAt,
    updated_at: lastUsedAt,
    ...extra,
  };
}

// Ids ascend while last_used_at descends: anything ordering by id would be caught.
const FIRST = makeSession("7270000000000000001", ALMA_ID, "2026-03-14T09:26:53.000000+00:00", {
  setup_id: SETUP_ID,
  setup_name: "The Gilded Tavern",
});
const SECOND = makeSession("7270000000000000002", BRENN_ID, "2026-03-10T11:00:00.000000+00:00");
const THIRD = makeSession("7270000000000000003", ALMA_ID, "2026-03-01T08:15:42.000000+00:00");

/** last_used_at newer than every row in WORKING. */
const NEWEST = makeSession("7270000000000000004", CORVIN_ID, "2026-04-02T00:00:00.000000+00:00");
/** last_used_at between SECOND's and THIRD's. */
const BETWEEN = makeSession("7270000000000000005", BRENN_ID, "2026-03-05T12:00:00.000000+00:00");
/** last_used_at older than every row in WORKING. */
const OLDEST = makeSession("7270000000000000006", CORVIN_ID, "2026-01-02T03:04:05.000000+00:00");
/**
 * last_used_at exactly equal to SECOND's, with a HIGHER id than SECOND's: the id DESC
 * tie-break (034 DEC-034-12) places it before SECOND.
 */
const TIED = makeSession("7270000000000000009", CORVIN_ID, SECOND.last_used_at);

/** The server's D14 order: most recent use first. */
const WORKING: Session[] = [FIRST, SECOND, THIRD];

function archivedCopy(session: Session): Session {
  return { ...session, archived_at: ARCHIVED_AT, updated_at: ARCHIVED_AT };
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

function copyRows(rows: Session[]): Session[] {
  return rows.map((row) => ({ ...row }));
}

function serveList(rows: Session[]) {
  return stubFetch(() => Promise.resolve(jsonResponse({ sessions: copyRows(rows) }, 200)));
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

type Seen = { method: string; path: string; search: string };

/** Every request the stub saw, keyed by exact pathname plus query string, never a prefix. */
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

function snapshot(state: SessionsState) {
  return { sessions: toJS(state.sessions), status: state.status };
}

function ids(state: SessionsState): string[] {
  return state.sessions.map((row) => row.id);
}

/** A state already loaded with rows, as the tree would be after its first load. */
function withSessions(rows: Session[]): SessionsState {
  const state = new SessionsState();
  runInAction(() => {
    state.sessions = copyRows(rows);
    state.status = "ready";
  });
  return state;
}

// ---------------------------------------------------------------------------
describe("a fresh SessionsState", () => {
  it("has no rows and status idle — DoD-4", () => {
    expect(snapshot(new SessionsState())).toEqual({ sessions: [], status: "idle" });
  });
});

// ---------------------------------------------------------------------------
describe("loadSessions", () => {
  it("is loading while the request is pending, then ready — DoD-4", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = new SessionsState();
    const running = loadSessions(state);
    await flush();
    expect(state.status).toBe("loading");
    pending.resolve(jsonResponse({ sessions: copyRows(WORKING) }, 200));
    await running;
    expect(state.status).toBe("ready");
  });

  it("goes back to loading while a reload of an already-ready state is pending — DoD-4", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = withSessions(WORKING);
    const running = loadSessions(state);
    await flush();
    expect(state.status).toBe("loading");
    pending.resolve(jsonResponse({ sessions: copyRows([FIRST]) }, 200));
    await running;
    expect(state.status).toBe("ready");
  });

  it("requests exactly GET /api/sessions, with no query string — DoD-4", async () => {
    const mock = serveList(WORKING);
    await loadSessions(new SessionsState());
    expect(seen(mock)).toEqual([{ method: "GET", path: LIST_PATH, search: "" }]);
  });

  it("writes exactly the server's rows with status ready — DoD-4", async () => {
    serveList(WORKING);
    const state = new SessionsState();
    await expect(loadSessions(state)).resolves.toBeUndefined();
    expect(snapshot(state)).toEqual({ sessions: [FIRST, SECOND, THIRD], status: "ready" });
  });

  it("keeps the server's order even when it is not the last_used_at order — DoD-4", async () => {
    serveList([THIRD, FIRST, SECOND]);
    const state = new SessionsState();
    await loadSessions(state);
    expect(ids(state)).toEqual([THIRD.id, FIRST.id, SECOND.id]);
  });

  it("an empty listing is ready with no rows — DoD-4", async () => {
    serveList([]);
    const state = new SessionsState();
    await loadSessions(state);
    expect(snapshot(state)).toEqual({ sessions: [], status: "ready" });
  });

  it("a failed request becomes failed, keeps the previous rows and does not reject — DoD-4", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    const state = withSessions(WORKING);
    await expect(loadSessions(state)).resolves.toBeUndefined();
    expect(state.status).toBe("failed");
    expect(toJS(state.sessions)).toEqual([FIRST, SECOND, THIRD]);
  });

  it("a first failed request becomes failed with no rows and does not reject — DoD-4", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    const state = new SessionsState();
    await expect(loadSessions(state)).resolves.toBeUndefined();
    expect(snapshot(state)).toEqual({ sessions: [], status: "failed" });
  });

  it("a transport failure is also failed, not a rejection — DoD-4", async () => {
    stubFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    const state = withSessions(WORKING);
    await expect(loadSessions(state)).resolves.toBeUndefined();
    expect(state.status).toBe("failed");
    expect(toJS(state.sessions)).toEqual([FIRST, SECOND, THIRD]);
  });

  it("writes nothing when its signal aborts before the response settles — DoD-4", async () => {
    stubFetch(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          const signal = init?.signal;
          signal?.addEventListener("abort", () => {
            reject(signal.reason ?? new DOMException("The operation was aborted.", "AbortError"));
          });
        }),
    );
    const state = withSessions(WORKING);
    const controller = new AbortController();
    const running = loadSessions(state, controller.signal);
    await flush();
    const atAbort = snapshot(state);
    controller.abort();
    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(snapshot(state)).toEqual(atAbort);
    expect(toJS(state.sessions)).toEqual([FIRST, SECOND, THIRD]);
  });

  it("writes nothing when a response arrives after the abort — DoD-4", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = withSessions(WORKING);
    const controller = new AbortController();
    const running = loadSessions(state, controller.signal);
    await flush();
    const atAbort = snapshot(state);
    controller.abort();
    pending.resolve(jsonResponse({ sessions: copyRows([NEWEST]) }, 200));
    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(snapshot(state)).toEqual(atAbort);
    expect(toJS(state.sessions)).toEqual([FIRST, SECOND, THIRD]);
  });
});

// ---------------------------------------------------------------------------
describe("applySession — an absent working row is inserted by last_used_at descending", () => {
  it("a row newer than every existing row lands first — DoD-5", () => {
    const state = withSessions(WORKING);
    applySession(state, NEWEST);
    expect(ids(state)).toEqual([NEWEST.id, FIRST.id, SECOND.id, THIRD.id]);
    expect(toJS(state.sessions)[0]).toEqual(NEWEST);
  });

  it("a row whose last_used_at falls between two rows lands between them — DoD-5", () => {
    const state = withSessions(WORKING);
    applySession(state, BETWEEN);
    expect(ids(state)).toEqual([FIRST.id, SECOND.id, BETWEEN.id, THIRD.id]);
    expect(toJS(state.sessions)).toEqual([FIRST, SECOND, BETWEEN, THIRD]);
  });

  it("a row older than every existing row lands last — DoD-5", () => {
    const state = withSessions(WORKING);
    applySession(state, OLDEST);
    expect(ids(state)).toEqual([FIRST.id, SECOND.id, THIRD.id, OLDEST.id]);
  });

  it("a row whose last_used_at equals an existing row's, with a higher id, lands before it — DoD-5, S034_005_DoD9", () => {
    const state = withSessions(WORKING);
    applySession(state, TIED);
    expect(ids(state)).toEqual([FIRST.id, TIED.id, SECOND.id, THIRD.id]);
  });

  it("the first row of an empty list is simply inserted — DoD-5", () => {
    const state = withSessions([]);
    applySession(state, BETWEEN);
    expect(toJS(state.sessions)).toEqual([BETWEEN]);
  });
});

// ---------------------------------------------------------------------------
describe("applySession — a present working row with unchanged last_used_at", () => {
  it("stays at the same index, carrying the new values — DoD-5", () => {
    const state = withSessions(WORKING);
    const relabelled: Session = {
      ...SECOND,
      setup_id: SETUP_ID,
      setup_name: "Nightfall Harbour",
      updated_at: "2026-04-06T12:00:00.000000+00:00",
    };
    applySession(state, relabelled);
    expect(toJS(state.sessions)).toEqual([FIRST, relabelled, THIRD]);
    expect(ids(state)).toEqual([FIRST.id, SECOND.id, THIRD.id]);
    expect(state.sessions[1].setup_name).toBe("Nightfall Harbour");
  });

  it("re-applying the first row unchanged leaves it first and the list the same length — DoD-5", () => {
    const state = withSessions(WORKING);
    applySession(state, FIRST);
    expect(toJS(state.sessions)).toEqual([FIRST, SECOND, THIRD]);
  });

  it("re-applying the last row unchanged leaves it last — DoD-5", () => {
    const state = withSessions(WORKING);
    applySession(state, { ...THIRD, updated_at: "2026-04-06T12:00:00.000000+00:00" });
    expect(ids(state)).toEqual([FIRST.id, SECOND.id, THIRD.id]);
  });
});

// ---------------------------------------------------------------------------
describe("applySession — archived rows never live in the workspace list", () => {
  it("removes the row with that id when it is present — DoD-6", () => {
    const state = withSessions(WORKING);
    applySession(state, archivedCopy(SECOND));
    expect(toJS(state.sessions)).toEqual([FIRST, THIRD]);
  });

  it("removes the first row as readily as a middle one — DoD-6", () => {
    const state = withSessions(WORKING);
    applySession(state, archivedCopy(FIRST));
    expect(ids(state)).toEqual([SECOND.id, THIRD.id]);
  });

  it("leaves the rows unchanged when that id is absent — DoD-6", () => {
    const state = withSessions(WORKING);
    applySession(state, archivedCopy(BETWEEN));
    expect(toJS(state.sessions)).toEqual([FIRST, SECOND, THIRD]);
  });

  it("does not insert an absent archived row even when it is the most recently used — DoD-6", () => {
    const state = withSessions(WORKING);
    applySession(state, archivedCopy(NEWEST));
    expect(ids(state)).toEqual([FIRST.id, SECOND.id, THIRD.id]);
  });

  it("leaves an empty list empty — DoD-6", () => {
    const state = withSessions([]);
    applySession(state, archivedCopy(NEWEST));
    expect(toJS(state.sessions)).toEqual([]);
  });

  it("applying the restored working version puts the row back at its last_used_at position — DoD-6", () => {
    const state = withSessions(WORKING);
    applySession(state, archivedCopy(SECOND));
    expect(ids(state)).toEqual([FIRST.id, THIRD.id]);
    applySession(state, SECOND);
    expect(toJS(state.sessions)).toEqual([FIRST, SECOND, THIRD]);
  });

  it("restores a row that was never in the list at its last_used_at position — DoD-6", () => {
    const state = withSessions(WORKING);
    applySession(state, BETWEEN);
    expect(ids(state)).toEqual([FIRST.id, SECOND.id, BETWEEN.id, THIRD.id]);
  });
});

// ---------------------------------------------------------------------------
// Feature 034 step 005, DoD-9 (DEC-034-12): ties on last_used_at order by id descending,
// compared as numbers. Every list below is built in the server's order (last_used_at DESC,
// id DESC), so "unchanged last_used_at keeps its index" is checked against that order.
describe("applySession — last_used_at ties order by id descending (034)", () => {
  const TIE_AT = "2026-03-20T00:00:00.000000+00:00";
  const ABOVE = makeSession("7270000000000000100", ALMA_ID, "2026-03-25T00:00:00.000000+00:00");
  const TIE_HIGH = makeSession("7270000000000000030", BRENN_ID, TIE_AT);
  const TIE_MID = makeSession("7270000000000000020", ALMA_ID, TIE_AT);
  const TIE_LOW = makeSession("7270000000000000010", CORVIN_ID, TIE_AT);
  const BELOW = makeSession("7270000000000000200", BRENN_ID, "2026-03-15T00:00:00.000000+00:00");
  const SERVER_ORDER: Session[] = [ABOVE, TIE_HIGH, TIE_MID, TIE_LOW, BELOW];

  /** The row a rename returns: a new name and updated_at, last_used_at unchanged. */
  function renamed(session: Session, name: string | null): Session {
    return { ...session, name, updated_at: "2026-04-06T12:00:00.000000+00:00" };
  }

  for (const [label, row, index] of [
    ["the highest-id tied row", TIE_HIGH, 1],
    ["the middle tied row", TIE_MID, 2],
    ["the lowest-id tied row", TIE_LOW, 3],
    ["the row above the ties", ABOVE, 0],
    ["the row below the ties", BELOW, 4],
  ] as const) {
    it(`re-applying ${label} renamed keeps its index — S034_005_DoD9`, () => {
      const state = withSessions(SERVER_ORDER);
      const next = renamed(row, "Dockside Truce");
      applySession(state, next);
      expect(ids(state)).toEqual(SERVER_ORDER.map((s) => s.id));
      expect(toJS(state.sessions)[index]).toEqual(next);
      expect(state.sessions).toHaveLength(SERVER_ORDER.length);
    });
  }

  it("re-applying every tied row in turn leaves the server order intact — S034_005_DoD9", () => {
    const state = withSessions(SERVER_ORDER);
    for (const row of [TIE_LOW, TIE_HIGH, TIE_MID, TIE_HIGH, TIE_LOW]) {
      applySession(state, renamed(row, `name of ${row.id}`));
      expect(ids(state)).toEqual(SERVER_ORDER.map((s) => s.id));
    }
  });

  it("clearing a name (null) on a tied row keeps its index — S034_005_DoD9", () => {
    const named = renamed(TIE_MID, "Harbour Night");
    const state = withSessions([ABOVE, TIE_HIGH, named, TIE_LOW, BELOW]);
    applySession(state, renamed(TIE_MID, null));
    expect(ids(state)).toEqual(SERVER_ORDER.map((s) => s.id));
    expect(state.sessions[2].name).toBeNull();
  });

  it("an absent tied row lands by id descending among the ties — S034_005_DoD9", () => {
    const highest = makeSession("7270000000000000040", CORVIN_ID, TIE_AT);
    const between = makeSession("7270000000000000025", CORVIN_ID, TIE_AT);
    const lowest = makeSession("7270000000000000005", CORVIN_ID, TIE_AT);

    const first = withSessions(SERVER_ORDER);
    applySession(first, highest);
    expect(ids(first)).toEqual([ABOVE.id, highest.id, TIE_HIGH.id, TIE_MID.id, TIE_LOW.id, BELOW.id]);

    const second = withSessions(SERVER_ORDER);
    applySession(second, between);
    expect(ids(second)).toEqual([ABOVE.id, TIE_HIGH.id, between.id, TIE_MID.id, TIE_LOW.id, BELOW.id]);

    const third = withSessions(SERVER_ORDER);
    applySession(third, lowest);
    expect(ids(third)).toEqual([ABOVE.id, TIE_HIGH.id, TIE_MID.id, TIE_LOW.id, lowest.id, BELOW.id]);
  });

  it("ids of unequal length compare as numbers, not as text — S034_005_DoD9", () => {
    // 19 digits vs 18 digits: numerically LONG > SHORT, but as text "9…" > "7…".
    const LONG = makeSession("7270000000000000010", ALMA_ID, TIE_AT);
    const SHORT = makeSession("999999999999999999", BRENN_ID, TIE_AT);
    const state = withSessions([LONG, SHORT]);
    applySession(state, renamed(SHORT, "Short Id"));
    expect(ids(state)).toEqual([LONG.id, SHORT.id]);
    applySession(state, renamed(LONG, "Long Id"));
    expect(ids(state)).toEqual([LONG.id, SHORT.id]);
  });

  it("an absent row with a mid-length id lands numerically between — S034_005_DoD9", () => {
    // 1000000000000000000 (19 digits) sits numerically between the two; as text it sorts last.
    const LONG = makeSession("7270000000000000010", ALMA_ID, TIE_AT);
    const SHORT = makeSession("999999999999999999", BRENN_ID, TIE_AT);
    const MIDDLE = makeSession("1000000000000000000", CORVIN_ID, TIE_AT);
    const state = withSessions([LONG, SHORT]);
    applySession(state, MIDDLE);
    expect(ids(state)).toEqual([LONG.id, MIDDLE.id, SHORT.id]);
  });

  it("ids that collide as JavaScript Numbers still order exactly — S034_005_DoD9", () => {
    // Past 2^53 these three ids round to the same Number; only an exact compare orders them.
    const ELEVEN = makeSession("7270000000000000011", ALMA_ID, TIE_AT);
    const TEN = makeSession("7270000000000000010", BRENN_ID, TIE_AT);
    const TWELVE = makeSession("7270000000000000012", CORVIN_ID, TIE_AT);
    const NINE = makeSession("7270000000000000009", CORVIN_ID, TIE_AT);

    const top = withSessions([ELEVEN, TEN]);
    applySession(top, TWELVE);
    expect(ids(top)).toEqual([TWELVE.id, ELEVEN.id, TEN.id]);

    const bottom = withSessions([ELEVEN, TEN]);
    applySession(bottom, NINE);
    expect(ids(bottom)).toEqual([ELEVEN.id, TEN.id, NINE.id]);

    const kept = withSessions([TWELVE, ELEVEN, TEN]);
    applySession(kept, renamed(ELEVEN, "Eleven"));
    expect(ids(kept)).toEqual([TWELVE.id, ELEVEN.id, TEN.id]);
  });

  it("a tied row with a newer last_used_at still moves to the top — S034_005_DoD9", () => {
    const state = withSessions(SERVER_ORDER);
    const used = { ...TIE_LOW, last_used_at: "2026-04-01T00:00:00.000000+00:00" };
    applySession(state, used);
    expect(ids(state)).toEqual([TIE_LOW.id, ABOVE.id, TIE_HIGH.id, TIE_MID.id, BELOW.id]);
    expect(toJS(state.sessions)[0]).toEqual(used);
  });

  it("the bottom row with a newer last_used_at moves to the top — S034_005_DoD9", () => {
    const state = withSessions(SERVER_ORDER);
    applySession(state, { ...BELOW, last_used_at: "2026-04-01T00:00:00.000000+00:00" });
    expect(ids(state)).toEqual([BELOW.id, ABOVE.id, TIE_HIGH.id, TIE_MID.id, TIE_LOW.id]);
  });

  it("an archived tied row is still dropped — S034_005_DoD9", () => {
    const state = withSessions(SERVER_ORDER);
    applySession(state, archivedCopy(TIE_MID));
    expect(ids(state)).toEqual([ABOVE.id, TIE_HIGH.id, TIE_LOW.id, BELOW.id]);
  });

  it("an absent archived row tied with others is not inserted — S034_005_DoD9", () => {
    const state = withSessions(SERVER_ORDER);
    applySession(state, archivedCopy(makeSession("7270000000000000025", CORVIN_ID, TIE_AT)));
    expect(ids(state)).toEqual(SERVER_ORDER.map((s) => s.id));
  });
});

// ---------------------------------------------------------------------------
describe("sessionsOfCharacter", () => {
  it("returns only that character's sessions, in the given order — DoD-7", () => {
    expect(sessionsOfCharacter(WORKING, ALMA_ID)).toEqual([FIRST, THIRD]);
    expect(sessionsOfCharacter(WORKING, BRENN_ID)).toEqual([SECOND]);
  });

  it("keeps the given order even when it is not the last_used_at order — DoD-7", () => {
    const scrambled = [THIRD, SECOND, FIRST];
    expect(sessionsOfCharacter(scrambled, ALMA_ID)).toEqual([THIRD, FIRST]);
  });

  it("returns an empty list for a character with no sessions — DoD-7", () => {
    expect(sessionsOfCharacter(WORKING, CORVIN_ID)).toEqual([]);
  });

  it("returns an empty list for an empty session list — DoD-7", () => {
    expect(sessionsOfCharacter([], ALMA_ID)).toEqual([]);
  });

  it("reads the workspace state's own rows the same way — DoD-7", () => {
    const state = withSessions(WORKING);
    expect(sessionsOfCharacter(state.sessions, ALMA_ID).map((row) => row.id)).toEqual([
      FIRST.id,
      THIRD.id,
    ]);
  });
});

// ---------------------------------------------------------------------------
describe("orderCharactersByUse", () => {
  // Only the id string is read, so plain objects with an id stand in for 009's Character.
  type Row = { id: string; label: string };
  const A: Row = { id: ALMA_ID, label: "Alma Vist" };
  const B: Row = { id: BRENN_ID, label: "Brenn Oduya" };
  const C: Row = { id: CORVIN_ID, label: "Corvin Hale" };
  const GIVEN: Row[] = [A, B, C];

  it("puts C first, then A, then the session-less B — DoD-8", () => {
    // C's session is the most recently used, A's is older, B has none.
    const ordered = orderCharactersByUse(GIVEN, [NEWEST, THIRD]);
    expect(ordered).toEqual([C, A, B]);
  });

  it("returns the given order when there are no sessions at all — DoD-8", () => {
    expect(orderCharactersByUse(GIVEN, [])).toEqual([A, B, C]);
  });

  it("keeps two session-less characters in their relative given order — DoD-8", () => {
    expect(orderCharactersByUse(GIVEN, [NEWEST])).toEqual([C, A, B]);
    expect(orderCharactersByUse([C, A, B], [NEWEST])).toEqual([C, A, B]);
    expect(orderCharactersByUse([B, A, C], [NEWEST])).toEqual([C, B, A]);
  });

  it("ranks a character by the greatest last_used_at among its sessions — DoD-8", () => {
    // A: 2026-03-14 (FIRST) and 2026-03-01 (THIRD); C: 2026-03-07 only.
    const corvinMid = makeSession(
      "7270000000000000007",
      CORVIN_ID,
      "2026-03-07T00:00:00.000000+00:00",
    );
    expect(orderCharactersByUse(GIVEN, [FIRST, corvinMid, THIRD])).toEqual([A, C, B]);
  });

  it("keeps the given order for characters whose greatest last_used_at is equal — DoD-8", () => {
    const sharedUse = "2026-03-20T00:00:00.000000+00:00";
    const almaTied = makeSession("7270000000000000011", ALMA_ID, sharedUse);
    const corvinTied = makeSession("7270000000000000010", CORVIN_ID, sharedUse);
    expect(orderCharactersByUse([A, C], [almaTied, corvinTied])).toEqual([A, C]);
    expect(orderCharactersByUse([C, A], [almaTied, corvinTied])).toEqual([C, A]);
  });

  it("ignores sessions of characters that are not in the list — DoD-8", () => {
    expect(orderCharactersByUse([A, B], [NEWEST, THIRD])).toEqual([A, B]);
  });

  it("does not mutate either input — DoD-8", () => {
    const characters: Row[] = [A, B, C];
    const sessions: Session[] = [NEWEST, THIRD];
    const charactersBefore = characters.map((row) => ({ ...row }));
    const sessionsBefore = sessions.map((row) => ({ ...row }));
    const ordered = orderCharactersByUse(characters, sessions);
    expect(characters).toEqual(charactersBefore);
    expect(sessions).toEqual(sessionsBefore);
    expect(characters).toEqual([A, B, C]);
    expect(ordered).not.toBe(characters);
    expect(ordered).toEqual([C, A, B]);
  });

  it("returns the very same character objects, not copies — DoD-8", () => {
    const ordered = orderCharactersByUse(GIVEN, [NEWEST, THIRD]);
    expect(ordered[0]).toBe(C);
    expect(ordered[1]).toBe(A);
    expect(ordered[2]).toBe(B);
  });
});

// ---------------------------------------------------------------------------
describe("the writes are MobX actions on observable fields", () => {
  it("an autorun reading sessions re-runs after applySession — DoD-9", () => {
    const state = withSessions(WORKING);
    const observed: string[][] = [];
    const dispose = autorun(() => {
      observed.push(state.sessions.map((row) => row.id));
    });
    expect(observed).toHaveLength(1);
    applySession(state, NEWEST);
    expect(observed.length).toBeGreaterThan(1);
    expect(observed[observed.length - 1]).toEqual([NEWEST.id, FIRST.id, SECOND.id, THIRD.id]);
    dispose();
  });

  it("an autorun reading sessions re-runs after an archived row is removed — DoD-9", () => {
    const state = withSessions(WORKING);
    const observed: string[][] = [];
    const dispose = autorun(() => {
      observed.push(state.sessions.map((row) => row.id));
    });
    expect(observed).toHaveLength(1);
    applySession(state, archivedCopy(SECOND));
    expect(observed.length).toBeGreaterThan(1);
    expect(observed[observed.length - 1]).toEqual([FIRST.id, THIRD.id]);
    dispose();
  });

  it("an autorun reading status re-runs after loadSessions settles — DoD-9", async () => {
    serveList(WORKING);
    const state = new SessionsState();
    const observed: string[] = [];
    const dispose = autorun(() => {
      observed.push(state.status);
    });
    expect(observed).toEqual(["idle"]);
    await loadSessions(state);
    expect(observed.length).toBeGreaterThan(1);
    expect(observed[observed.length - 1]).toBe("ready");
    dispose();
  });

  it("an autorun reading status re-runs when loadSessions fails — DoD-9", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    const state = new SessionsState();
    const observed: string[] = [];
    const dispose = autorun(() => {
      observed.push(state.status);
    });
    expect(observed).toEqual(["idle"]);
    await loadSessions(state);
    expect(observed[observed.length - 1]).toBe("failed");
    dispose();
  });

  it("sessions and status are the observable fields, and neither is computed — DoD-9", () => {
    const state = new SessionsState();
    const observed = Object.getOwnPropertyNames(state).filter((name) =>
      isObservableProp(state, name),
    );
    expect(observed.sort()).toEqual(["sessions", "status"]);
    for (const name of observed) {
      expect(isComputedProp(state, name), `field ${name}`).toBe(false);
    }
  });

  it("the class prototype carries no method and no getter — DoD-9", () => {
    expect(Object.getOwnPropertyNames(SessionsState.prototype)).toEqual(["constructor"]);
  });

  it("the load, the upsert and the derivations are free functions — DoD-9", () => {
    for (const fn of [loadSessions, applySession, sessionsOfCharacter, orderCharactersByUse]) {
      expect(typeof fn).toBe("function");
    }
    expect(Object.getOwnPropertyNames(SessionsState.prototype)).not.toContain("loadSessions");
  });
});
