// Feature 011, step 004 — the sessions API client (DoD-1..DoD-3).
// Feature 034, step 004 — `name` on every session (S034_004_DoD4) and renameSession
// (S034_004_DoD5); see the block at the end of the file.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done and
// context.md's "Wire contract — sessions" plus the "Ids are strings" constraint. The calls
// address the wire contract's path families exactly: a listing takes ?include_archived=true
// only when asked and nothing else, the two action routes are POSTs, and nothing coerces an id — a decimal string beyond Number.MAX_SAFE_INTEGER must
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
  renameSession,
  restoreSession,
  type Session,
  type StartedSession,
  startSessionWithMessage,
} from "../../src/app/sessionsApi";
import type { Message } from "../../src/app/streamApi";

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
  name: null,
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
  name: null,
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

  it("a 404 character_not_found envelope rejects the character-addressed calls with that code — DoD-3", async () => {
    for (const call of [
      () => fetchCharacterSessions(CHARACTER_ID, false),
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
// Feature 018, step 004 — the start-with-message call (DoD-1). Expected values: the step's
// Interface intent and DoD plus 018 context.md's Wire contract (StartedSession = the eight
// Session keys + opening_message, Message | null). The unused bare `startSession` (and its
// DoD-2 cases) was removed: the character page starts sessions only with a message.
// Feature 034, step 004 (S034_004_DoD4): `Session` gains `name`, so the Session key set is
// now nine keys and a StartedSession ten; the 018 clauses below assert the widened sets.

const SESSION_KEYS = [
  "archived_at",
  "character_id",
  "created_at",
  "id",
  "last_used_at",
  "name",
  "setup_id",
  "setup_name",
  "updated_at",
];

const S018_SESSION_ID = "7270000000000000101";
const S018_MESSAGE_ID = "7280000000000000101";
const S018_STAMP = "2026-10-03T09:26:53.000000+00:00";

/** The served session's nine keys (no setup: the page composer sends none, D1; never renamed). */
const S018_SESSION: Session = {
  id: S018_SESSION_ID,
  character_id: CHARACTER_ID,
  setup_id: null,
  setup_name: null,
  name: null,
  archived_at: null,
  last_used_at: S018_STAMP,
  created_at: S018_STAMP,
  updated_at: S018_STAMP,
};

/** The opening message: a current-zone user row (kind and settled_at null), all eight keys. */
function openingMessage(text: string): Message {
  return {
    id: S018_MESSAGE_ID,
    session_id: S018_SESSION_ID,
    role: "user",
    kind: null,
    text,
    settled_at: null,
    created_at: S018_STAMP,
    updated_at: S018_STAMP,
  };
}

/** A served StartedSession with all ten keys (the nine Session keys plus opening_message). */
function startedSession(opening: Message | null): StartedSession {
  return { ...S018_SESSION, opening_message: opening };
}

describe("startSessionWithMessage (018 step 004)", () => {
  it("sends exactly one POST /api/characters/<id>/sessions whose parsed body is exactly { opening_message: <text verbatim> } — DoD-1", async () => {
    const mock = serve(startedSession(openingMessage("  Hello\n")), 201);

    await startSessionWithMessage(CHARACTER_ID, "  Hello\n");

    expect(seen(mock)).toEqual([
      { method: "POST", path: "/api/characters/7250000000000000001/sessions", search: "" },
    ]);
    expect(sentBody(mock)).toEqual({ opening_message: "  Hello\n" });
    expect(bodyKeys(mock)).toEqual(["opening_message"]);
    expect(bodyKeys(mock)).not.toContain("setup_id");
  });

  it("resolves to the served ten-key StartedSession unchanged, ids the identical strings — DoD-1, S034_004_DoD4", async () => {
    const served = startedSession(openingMessage("  Hello\n"));
    serve(served, 201);

    const result = await startSessionWithMessage(CHARACTER_ID, "  Hello\n");

    expect(result).toEqual(served);
    expect(Object.keys(result).sort()).toEqual([...SESSION_KEYS, "opening_message"].sort());
    expect(result.id).toBe(S018_SESSION_ID);
    expect(typeof result.id).toBe("string");
    expect(result.character_id).toBe(CHARACTER_ID);
    expect(typeof result.character_id).toBe("string");
    expect(result.opening_message?.id).toBe(S018_MESSAGE_ID);
    expect(typeof result.opening_message?.id).toBe("string");
    expect(result.opening_message?.session_id).toBe(S018_SESSION_ID);
    expect(result.opening_message?.text).toBe("  Hello\n");
  });

  it("a 404 character_not_found envelope rejects with an ApiError carrying that code — DoD-1", async () => {
    serve(envelope("character_not_found", "That character does not exist."), 404);

    const error = await rejection(() => startSessionWithMessage(CHARACTER_ID, "  Hello\n"));

    expect(isApiError(error)).toBe(true);
    expect(isApiError(error) ? error.code : null).toBe("character_not_found");
    expect(isApiError(error) ? error.status : null).toBe(404);
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

// ===========================================================================
// Feature 034, step 004 — `name` on every session read (S034_004_DoD4) and the rename call
// (S034_004_DoD5). Expected values: the step's Interface intent and DoD, 034 context.md's
// "Wire shape of a session" (every session payload carries `name`, a string or null) and
// DEC-arch-session-names-2 (PATCH /api/sessions/{id} with a body of exactly { name }).
// ===========================================================================

/** A renamed session: the server answers its stored name verbatim. */
const NAMED_RUN: Session = { ...TAVERN_RUN, name: "Harbour at dusk" };
/** A second renamed session whose name looks like a date (it must not be reinterpreted). */
const DATE_NAMED_RUN: Session = { ...BARE_RUN, name: "2026-01-01" };

describe("every sessions-API read carries name as received (034 step 004)", () => {
  it("fetchSessions keeps each row's name, string or null — S034_004_DoD4", async () => {
    serve({ sessions: [NAMED_RUN, DATE_NAMED_RUN, { ...TAVERN_RUN, id: "7270000000000000003" }] });
    const rows = await fetchSessions(true);
    expect(rows.map((row) => row.name)).toEqual(["Harbour at dusk", "2026-01-01", null]);
  });

  it("fetchCharacterSessions keeps each row's name, string or null — S034_004_DoD4", async () => {
    serve({ sessions: [BARE_RUN, NAMED_RUN] });
    const rows = await fetchCharacterSessions(CHARACTER_ID, true);
    expect(rows.map((row) => row.name)).toEqual([null, "Harbour at dusk"]);
  });

  it("fetchSession resolves to the session with its name — S034_004_DoD4", async () => {
    serve(NAMED_RUN);
    const session = await fetchSession(SESSION_ID);
    expect(session.name).toBe("Harbour at dusk");
    expect(session).toEqual(NAMED_RUN);
  });

  it("fetchSession keeps a null name null — S034_004_DoD4", async () => {
    serve(TAVERN_RUN);
    const session = await fetchSession(SESSION_ID);
    expect(session.name).toBeNull();
  });

  it("archiveSession and restoreSession resolve to the session with its name — S034_004_DoD4", async () => {
    serve({ ...NAMED_RUN, archived_at: "2026-04-05T10:00:00.000000+00:00" });
    expect((await archiveSession(SESSION_ID)).name).toBe("Harbour at dusk");
    vi.unstubAllGlobals();
    serve(DATE_NAMED_RUN);
    expect((await restoreSession(OTHER_SESSION_ID)).name).toBe("2026-01-01");
  });

  it("startSessionWithMessage keeps the served name — S034_004_DoD4", async () => {
    serve(startedSession(openingMessage("Hi")), 201);
    const result = await startSessionWithMessage(CHARACTER_ID, "Hi");
    expect(result.name).toBeNull();
    expect(Object.keys(result).sort()).toEqual([...SESSION_KEYS, "opening_message"].sort());
  });
});

describe("renameSession (034 step 004)", () => {
  it("sends exactly one PATCH /api/sessions/<id> — S034_004_DoD5", async () => {
    const mock = serve(NAMED_RUN);
    await renameSession(SESSION_ID, "Harbour at dusk");
    expect(seen(mock)).toEqual([{ method: "PATCH", path: SESSION_PATH, search: "" }]);
  });

  it("the body's only key is name, holding the given string exactly — S034_004_DoD5", async () => {
    const mock = serve(NAMED_RUN);
    await renameSession(SESSION_ID, "Harbour at dusk");
    expect(sentBody(mock)).toEqual({ name: "Harbour at dusk" });
    expect(bodyKeys(mock)).toEqual(["name"]);
  });

  it("the string is sent as given, surrounding spaces included — S034_004_DoD5", async () => {
    // The server trims (DEC-034-1); the client sends exactly what it was handed.
    const mock = serve(NAMED_RUN);
    await renameSession(SESSION_ID, "  Harbour at dusk ");
    expect(sentBody(mock)).toEqual({ name: "  Harbour at dusk " });
  });

  it("a null name is sent as name: null, not omitted — S034_004_DoD5", async () => {
    const mock = serve(TAVERN_RUN);
    await renameSession(SESSION_ID, null);
    expect(sentBody(mock)).toEqual({ name: null });
    expect(bodyKeys(mock)).toEqual(["name"]);
  });

  it("resolves to the server's session, not to a locally built one — S034_004_DoD5", async () => {
    // The server's answer differs from the request (trimmed name, advanced updated_at).
    const answered: Session = {
      ...TAVERN_RUN,
      name: "Harbour at dusk",
      updated_at: "2026-04-01T08:00:00.000000+00:00",
    };
    serve(answered);
    await expect(renameSession(SESSION_ID, "  Harbour at dusk ")).resolves.toEqual(answered);
  });

  it("resolves to the server's null name after a clear — S034_004_DoD5", async () => {
    serve(TAVERN_RUN);
    const result = await renameSession(SESSION_ID, null);
    expect(result).toEqual(TAVERN_RUN);
    expect(result.name).toBeNull();
  });

  it("addresses an id beyond MAX_SAFE_INTEGER verbatim — S034_004_DoD5", async () => {
    const mock = serve(DATE_NAMED_RUN);
    await renameSession(OTHER_SESSION_ID, "2026-01-01");
    expect(seen(mock)[0].path).toBe(`/api/sessions/${OTHER_SESSION_ID}`);
  });

  it("a 404 session_not_found envelope rejects with that ApiError — S034_004_DoD5", async () => {
    serve(envelope("session_not_found", "That session does not exist."), 404);
    const error = await rejection(() => renameSession(SESSION_ID, "Harbour at dusk"));
    expect(isApiError(error)).toBe(true);
    expect(isApiError(error) ? error.code : null).toBe("session_not_found");
    expect(isApiError(error) ? error.status : null).toBe(404);
  });

  it("a 422 validation envelope rejects with an ApiError carrying status 422 — S034_004_DoD5", async () => {
    serve(envelope("validation_error", "The request is invalid."), 422);
    const error = await rejection(() => renameSession(SESSION_ID, "Harbour at dusk"));
    expect(isApiError(error)).toBe(true);
    expect(isApiError(error) ? error.status : null).toBe(422);
  });
});
