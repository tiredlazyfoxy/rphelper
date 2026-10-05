// Feature 029, step 004 (DoD-1..8) — the my-search API client (this file: DoD-1, DoD-2).
//
// Expected behaviour comes from `029.my-search/004.search-api-and-state.md`'s Interface
// intent and Definition of done, plus `context.md`'s "Wire contract — GET /api/search?q=<text>"
// (five groups, ids as decimal strings), D1 (one route, param `q`) and U1 (an embedding
// failure fails the whole search with the envelope unchanged). `fetch` is stubbed per file and
// the request is read off the stub as `new URL(input, "http://localhost")`: `fetchMySearch`
// takes the query text, not a prebuilt path, so there is no exported path helper to assert
// against. Every id is a decimal string above Number.MAX_SAFE_INTEGER, so a numeric coercion
// anywhere on the way in or out would be visible.
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  CharacterHit,
  EntryHit,
  MemoHit,
  MySearchResults,
  SessionHit,
  SetupHit,
} from "../../src/app/searchApi";
import { fetchMySearch } from "../../src/app/searchApi";
import { type ApiError, isApiError } from "../../src/shared/apiError";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const SEARCH_PATH = "/api/search";

/** The query the step file names, with a space and an ampersand so the encoding matters. */
const QUERY = "Mira & co";

// Every id is past Number.MAX_SAFE_INTEGER (2^53 - 1 = 9007199254740991): a silent numeric
// round trip would change the last digits of any of these.
const CHARACTER_ID = "7250000000000000011";
const SETUP_ID = "7250000000000000012";
const SETUP_CHARACTER_ID = "7250000000000000013";
const SESSION_ID = "7250000000000000014";
const ENTRY_ID = "7250000000000000015";
const ENTRY_SESSION_ID = "7250000000000000016";
const MEMO_ID = "7250000000000000017";
const MEMO_SCOPE_ID = "7250000000000000018";
const MEMO_CHARACTER_ID = "7250000000000000019";

const CHARACTER_HIT: CharacterHit = {
  id: CHARACTER_ID,
  name: "Mira & co's cartographer",
  archived: false,
};
const SETUP_HIT: SetupHit = {
  id: SETUP_ID,
  name: "A night with Mira & co",
  character_id: SETUP_CHARACTER_ID,
  character_name: "Brenn Oduya",
  archived: true,
};
const SESSION_HIT: SessionHit = {
  id: SESSION_ID,
  character_name: "Corvin Hale",
  setup_name: null,
  created_at: "2026-03-14T09:26:53.000000+00:00",
  archived: false,
};
const ENTRY_HIT: EntryHit = {
  id: ENTRY_ID,
  session_id: ENTRY_SESSION_ID,
  snippet: "…and then Mira & co left the harbour…",
  character_name: "Dask Orrery",
  session_created_at: "2026-03-10T11:00:00.000000+00:00",
};
const MEMO_HIT: MemoHit = {
  id: MEMO_ID,
  scope: "setup",
  scope_id: MEMO_SCOPE_ID,
  character_id: MEMO_CHARACTER_ID,
  snippet: "Mira & co never travel by day.",
  is_enabled: false,
};

const RESULTS: MySearchResults = {
  characters: [CHARACTER_HIT],
  setups: [SETUP_HIT],
  sessions: [SESSION_HIT],
  entries: [ENTRY_HIT],
  memos: [MEMO_HIT],
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

/** Answers the stubbed body on the exact pathname `/api/search`, and 404 anywhere else. */
function serveSearch(body: unknown, status = 200) {
  return stubFetch((input) => {
    const url = requestUrl(input);
    if (url.pathname === SEARCH_PATH) {
      return Promise.resolve(jsonResponse(body, status));
    }
    return Promise.resolve(
      jsonResponse({ error: { code: "not_found", message: "", detail: {} } }, 404),
    );
  });
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

type Seen = { method: string; path: string; query: string | null };

/** Every request the stub saw, with `q` decoded rather than pinned to one escaping. */
function seen(mock: ReturnType<typeof stubFetch>): Seen[] {
  return mock.mock.calls.map(([input, init]) => {
    const url = requestUrl(input);
    return {
      method: requestMethod(input, init),
      path: url.pathname,
      query: url.searchParams.get("q"),
    };
  });
}

function envelope(code: string, message: string): unknown {
  return { error: { code, message, detail: {} } };
}

/** The rejection of a call, or null when it resolved. */
async function rejection(promise: Promise<unknown>): Promise<unknown> {
  return promise.then(
    () => null,
    (error: unknown) => error,
  );
}

// ---------------------------------------------------------------------------
describe("fetchMySearch — the one route (D1, wire contract)", () => {
  it("GETs /api/search with the query as the decoded q parameter — DoD-1", async () => {
    const mock = serveSearch(RESULTS);

    await fetchMySearch(QUERY);

    expect(seen(mock)).toEqual([{ method: "GET", path: SEARCH_PATH, query: QUERY }]);
  });

  it("resolves to the five groups exactly as sent — DoD-1", async () => {
    serveSearch(RESULTS);

    const results = await fetchMySearch(QUERY);

    expect(results).toEqual(RESULTS);
  });

  it("keeps every id the exact decimal string the server sent — DoD-1", async () => {
    serveSearch(RESULTS);

    const results = await fetchMySearch(QUERY);

    expect(results.characters[0]?.id).toBe(CHARACTER_ID);
    expect(results.setups[0]?.id).toBe(SETUP_ID);
    expect(results.setups[0]?.character_id).toBe(SETUP_CHARACTER_ID);
    expect(results.sessions[0]?.id).toBe(SESSION_ID);
    expect(results.entries[0]?.id).toBe(ENTRY_ID);
    expect(results.entries[0]?.session_id).toBe(ENTRY_SESSION_ID);
    expect(results.memos[0]?.id).toBe(MEMO_ID);
    expect(results.memos[0]?.scope_id).toBe(MEMO_SCOPE_ID);
    expect(results.memos[0]?.character_id).toBe(MEMO_CHARACTER_ID);
  });
});

// ---------------------------------------------------------------------------
describe("fetchMySearch — an embedding failure fails the whole search (U1)", () => {
  it("rejects with the envelope's ApiError when the model is undesignated — DoD-2", async () => {
    serveSearch(envelope("no_embedding_model", "No embedding model is designated."), 409);

    const error = await rejection(fetchMySearch(QUERY));

    expect(isApiError(error)).toBe(true);
    expect((error as ApiError).code).toBe("no_embedding_model");
  });
});
