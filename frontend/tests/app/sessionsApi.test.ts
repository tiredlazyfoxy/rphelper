// Feature 011, step 004 — the sessions API client (DoD-1..DoD-3).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 004.context.md ("Why startSession always sends a body") and context.md's "Wire contract —
// sessions" plus the "Ids are strings" constraint. The six calls address the wire contract's
// path families exactly: a listing takes ?include_archived=true only when asked and nothing
// else, startSession always POSTs the single-key body { setup_id }, the two action routes are
// POSTs, and nothing coerces an id — a decimal string beyond Number.MAX_SAFE_INTEGER must
// survive a round trip character for character. Failures are the shared client's ApiErrors,
// rethrown unchanged.
import { afterEach, describe, expect, it, vi } from "vitest";
import { isApiError } from "../../src/shared/apiError";
import {
  archiveSession,
  fetchCharacterSessions,
  fetchSession,
  fetchSessions,
  isSessionArchived,
  restoreSession,
  type Session,
  startSession,
} from "../../src/app/sessionsApi";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// Every id is > Number.MAX_SAFE_INTEGER: a silent numeric coercion would change it.
const CHARACTER_ID = "7250000000000000001";
const SESSION_ID = "7270000000000000001";
const OTHER_SESSION_ID = "7270000000000000002";
const SETUP_ID = "7250000000000000009";

const ALL_SESSIONS_PATH = "/api/sessions";
const CHARACTER_SESSIONS_PATH = `/api/characters/${CHARACTER_ID}/sessions`;
const SESSION_PATH = `/api/sessions/${SESSION_ID}`;

/** A working session with a setup attached. */
const TAVERN_RUN: Session = {
  id: SESSION_ID,
  character_id: CHARACTER_ID,
  setup_id: SETUP_ID,
  setup_name: "The Gilded Tavern",
  archived_at: null,
  last_used_at: "2026-03-14T09:26:53.000000+00:00",
  created_at: "2026-03-14T09:26:53.000000+00:00",
  updated_at: "2026-03-14T09:26:53.000000+00:00",
};
/** An archived session with no setup (R2: setup_id is simply null). */
const BARE_RUN: Session = {
  id: OTHER_SESSION_ID,
  character_id: CHARACTER_ID,
  setup_id: null,
  setup_name: null,
  archived_at: "2026-03-20T18:04:11.000000+00:00",
  last_used_at: "2026-03-10T11:00:00.000000+00:00",
  created_at: "2026-03-10T11:00:00.000000+00:00",
  updated_at: "2026-03-20T18:04:11.000000+00:00",
};

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

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

type Seen = { method: string; path: string; search: string };

/** Every request the stub saw, keyed by exact pathname plus query string (never a prefix). */
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

function bodyKeys(mock: ReturnType<typeof stubFetch>): string[] {
  const body = sentBody(mock);
  return body === undefined ? [] : Object.keys(body as object);
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
describe("fetchSessions", () => {
  it("requests exactly GET /api/sessions with no query string when includeArchived is false — DoD-1", async () => {
    const mock = serve({ sessions: [TAVERN_RUN] });
    await fetchSessions(false);
    expect(seen(mock)).toEqual([{ method: "GET", path: ALL_SESSIONS_PATH, search: "" }]);
  });

  it("requests exactly GET /api/sessions?include_archived=true when includeArchived is true — DoD-1", async () => {
    const mock = serve({ sessions: [TAVERN_RUN, BARE_RUN] });
    await fetchSessions(true);
    expect(seen(mock)).toEqual([
      { method: "GET", path: ALL_SESSIONS_PATH, search: "?include_archived=true" },
    ]);
  });

  it("resolves to the payload's sessions array, unwrapped and in the payload's order — DoD-1", async () => {
    serve({ sessions: [TAVERN_RUN, BARE_RUN] });
    await expect(fetchSessions(true)).resolves.toEqual([TAVERN_RUN, BARE_RUN]);
  });

  it("resolves to an empty array for an empty listing — DoD-1", async () => {
    serve({ sessions: [] });
    await expect(fetchSessions(false)).resolves.toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("fetchCharacterSessions", () => {
  it("requests exactly GET /api/characters/<id>/sessions with no query string when includeArchived is false — DoD-1", async () => {
    const mock = serve({ sessions: [TAVERN_RUN] });
    await fetchCharacterSessions(CHARACTER_ID, false);
    expect(seen(mock)).toEqual([{ method: "GET", path: CHARACTER_SESSIONS_PATH, search: "" }]);
  });

  it("requests exactly GET /api/characters/<id>/sessions?include_archived=true when includeArchived is true — DoD-1", async () => {
    const mock = serve({ sessions: [TAVERN_RUN, BARE_RUN] });
    await fetchCharacterSessions(CHARACTER_ID, true);
    expect(seen(mock)).toEqual([
      { method: "GET", path: CHARACTER_SESSIONS_PATH, search: "?include_archived=true" },
    ]);
  });

  it("addresses the character id verbatim, without parsing it — DoD-1", async () => {
    const mock = serve({ sessions: [] });
    await fetchCharacterSessions(CHARACTER_ID, false);
    expect(seen(mock)[0].path).toBe(`/api/characters/${CHARACTER_ID}/sessions`);
  });

  it("resolves to the payload's sessions array, unwrapped and in the payload's order — DoD-1", async () => {
    serve({ sessions: [BARE_RUN, TAVERN_RUN] });
    await expect(fetchCharacterSessions(CHARACTER_ID, true)).resolves.toEqual([
      BARE_RUN,
      TAVERN_RUN,
    ]);
  });
});

// ---------------------------------------------------------------------------
describe("ids survive a listing round trip as the identical strings", () => {
  it("keeps every id, character_id and setup_id the payload's own string or null, past MAX_SAFE_INTEGER — DoD-1", async () => {
    serve({ sessions: [TAVERN_RUN, BARE_RUN] });
    const rows = await fetchSessions(true);
    expect(rows.map((row) => row.id)).toEqual([SESSION_ID, OTHER_SESSION_ID]);
    expect(rows.map((row) => row.character_id)).toEqual([CHARACTER_ID, CHARACTER_ID]);
    expect(rows.map((row) => row.setup_id)).toEqual([SETUP_ID, null]);
    expect(typeof rows[0].id).toBe("string");
    expect(typeof rows[0].character_id).toBe("string");
    expect(typeof rows[0].setup_id).toBe("string");
    expect(rows[0].id).toBe(SESSION_ID);
    expect(rows[0].setup_id).toBe(SETUP_ID);
    expect(rows[1].setup_id).toBeNull();
  });

  it("keeps them identical through the per-character listing too — DoD-1", async () => {
    serve({ sessions: [TAVERN_RUN] });
    const rows = await fetchCharacterSessions(CHARACTER_ID, false);
    expect(rows[0].id).toBe(SESSION_ID);
    expect(rows[0].character_id).toBe(CHARACTER_ID);
    expect(rows[0].setup_id).toBe(SETUP_ID);
  });
});

// ---------------------------------------------------------------------------
describe("fetchSession", () => {
  it("GETs exactly /api/sessions/<id> and resolves to the response's session — DoD-2", async () => {
    const mock = serve(TAVERN_RUN);
    await expect(fetchSession(SESSION_ID)).resolves.toEqual(TAVERN_RUN);
    expect(seen(mock)).toEqual([{ method: "GET", path: SESSION_PATH, search: "" }]);
  });

  it("reads an archived session by id just the same — DoD-2", async () => {
    const mock = serve(BARE_RUN);
    await expect(fetchSession(OTHER_SESSION_ID)).resolves.toEqual(BARE_RUN);
    expect(seen(mock)).toEqual([
      { method: "GET", path: `/api/sessions/${OTHER_SESSION_ID}`, search: "" },
    ]);
  });
});

// ---------------------------------------------------------------------------
describe("startSession always states the setup in its body", () => {
  it("POSTs /api/characters/<id>/sessions with the JSON body exactly { setup_id: null } for no setup — DoD-2", async () => {
    const created: Session = { ...TAVERN_RUN, setup_id: null, setup_name: null };
    const mock = serve(created, 201);
    await expect(startSession(CHARACTER_ID, null)).resolves.toEqual(created);
    expect(seen(mock)).toEqual([
      { method: "POST", path: CHARACTER_SESSIONS_PATH, search: "" },
    ]);
    expect(sentBody(mock)).toEqual({ setup_id: null });
    expect(bodyKeys(mock)).toEqual(["setup_id"]);
  });

  it("POSTs the JSON body exactly { setup_id: \"<id>\" } for a chosen setup — DoD-2", async () => {
    const mock = serve(TAVERN_RUN, 201);
    await expect(startSession(CHARACTER_ID, SETUP_ID)).resolves.toEqual(TAVERN_RUN);
    expect(seen(mock)).toEqual([
      { method: "POST", path: CHARACTER_SESSIONS_PATH, search: "" },
    ]);
    expect(sentBody(mock)).toEqual({ setup_id: SETUP_ID });
    expect(bodyKeys(mock)).toEqual(["setup_id"]);
  });

  it("sends the setup id as the identical string it was given, past MAX_SAFE_INTEGER — DoD-2", async () => {
    const mock = serve(TAVERN_RUN, 201);
    await startSession(CHARACTER_ID, SETUP_ID);
    const body = sentBody(mock) as { setup_id: unknown };
    expect(typeof body.setup_id).toBe("string");
    expect(body.setup_id).toBe(SETUP_ID);
  });
});

// ---------------------------------------------------------------------------
describe("the two action calls", () => {
  it("archiveSession POSTs /api/sessions/<id>/archive and resolves to the response's session — DoD-2", async () => {
    const archived: Session = { ...TAVERN_RUN, archived_at: "2026-04-05T10:00:00.000000+00:00" };
    const mock = serve(archived);
    await expect(archiveSession(SESSION_ID)).resolves.toEqual(archived);
    expect(seen(mock)).toEqual([
      { method: "POST", path: `${SESSION_PATH}/archive`, search: "" },
    ]);
  });

  it("restoreSession POSTs /api/sessions/<id>/restore and resolves to the response's session — DoD-2", async () => {
    const mock = serve(TAVERN_RUN);
    await expect(restoreSession(SESSION_ID)).resolves.toEqual(TAVERN_RUN);
    expect(seen(mock)).toEqual([
      { method: "POST", path: `${SESSION_PATH}/restore`, search: "" },
    ]);
  });

  it("an id beyond MAX_SAFE_INTEGER reaches every id-addressed route unchanged — DoD-2", async () => {
    for (const expected of [
      { call: () => fetchSession(SESSION_ID), path: SESSION_PATH },
      { call: () => archiveSession(SESSION_ID), path: `${SESSION_PATH}/archive` },
      { call: () => restoreSession(SESSION_ID), path: `${SESSION_PATH}/restore` },
    ]) {
      const mock = serve(TAVERN_RUN);
      await expected.call();
      expect(seen(mock)[0].path).toBe(expected.path);
      vi.unstubAllGlobals();
    }
  });
});

// ---------------------------------------------------------------------------
describe("failures are the shared client's ApiErrors, rethrown unchanged", () => {
  it("a 404 session_not_found envelope rejects fetchSession with that ApiError code — DoD-3", async () => {
    serve(envelope("session_not_found", "That session does not exist."), 404);
    const error = await rejection(() => fetchSession(SESSION_ID));
    expect(isApiError(error)).toBe(true);
    expect(isApiError(error) ? error.code : null).toBe("session_not_found");
    expect(isApiError(error) ? error.status : null).toBe(404);
  });

  it("the same 404 rejects the other session-addressed calls with session_not_found — DoD-3", async () => {
    for (const call of [
      () => archiveSession(SESSION_ID),
      () => restoreSession(SESSION_ID),
    ]) {
      serve(envelope("session_not_found", "That session does not exist."), 404);
      const error = await rejection(call);
      expect(isApiError(error)).toBe(true);
      expect(isApiError(error) ? error.code : null).toBe("session_not_found");
      vi.unstubAllGlobals();
    }
  });

  it("a 409 setup_archived envelope rejects startSession with that ApiError code — DoD-3", async () => {
    serve(envelope("setup_archived", "That setup is archived."), 409);
    const error = await rejection(() => startSession(CHARACTER_ID, SETUP_ID));
    expect(isApiError(error)).toBe(true);
    expect(isApiError(error) ? error.code : null).toBe("setup_archived");
    expect(isApiError(error) ? error.status : null).toBe(409);
  });

  it("a 404 character_not_found envelope rejects the character-addressed calls with that code — DoD-3", async () => {
    for (const call of [
      () => fetchCharacterSessions(CHARACTER_ID, false),
      () => startSession(CHARACTER_ID, null),
    ]) {
      serve(envelope("character_not_found", "That character does not exist."), 404);
      const error = await rejection(call);
      expect(isApiError(error)).toBe(true);
      expect(isApiError(error) ? error.code : null).toBe("character_not_found");
      vi.unstubAllGlobals();
    }
  });
});

// ---------------------------------------------------------------------------
describe("isSessionArchived", () => {
  it("is true when archived_at is a string — DoD-3", () => {
    expect(isSessionArchived(BARE_RUN)).toBe(true);
  });

  it("is false when archived_at is null — DoD-3", () => {
    expect(isSessionArchived(TAVERN_RUN)).toBe(false);
  });
});
