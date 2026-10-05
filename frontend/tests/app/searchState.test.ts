// Feature 029, step 004 (DoD-1..8) — the results page's state (this file: DoD-3..DoD-8).
//
// Expected behaviour comes from `029.my-search/004.search-api-and-state.md`'s Interface intent
// and Definition of done, the "Targets" table in `004.context.md`, and `context.md`'s U4
// (navigation and the `/search?q=` URL), D1 (a blank `q` shows no results and makes no
// request), D8 (the landing params `entry` and `notes=open`), U1 (a failure is the envelope's
// message, shown inline) and the frontend constraints — "never rejects", "writes nothing once
// aborted", "ids are strings".
//
// `fetch` is stubbed per file and routed by the exact pathname `/api/search`; a request that is
// not supposed to happen is therefore observable as a call on the stub. Every id is a decimal
// string above Number.MAX_SAFE_INTEGER, so a target built by coercing an id would be visible.
import { runInAction, toJS } from "mobx";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  CharacterHit,
  EntryHit,
  MemoHit,
  MySearchResults,
  SessionHit,
  SetupHit,
} from "../../src/app/searchApi";
import {
  characterTarget,
  entryTarget,
  hasNoHits,
  isBlankQuery,
  loadSearch,
  memoTarget,
  SearchState,
  searchHref,
  sessionTarget,
  setupTarget,
  type SearchLoadStatus,
} from "../../src/app/searchState";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const SEARCH_PATH = "/api/search";
const QUERY = "Mira & co";
const BLANK_QUERIES = ["", "   "];
const UNREACHABLE_MESSAGE = "The embedding provider could not be reached zq-63.";

// Ids past Number.MAX_SAFE_INTEGER (2^53 - 1 = 9007199254740991).
const CHARACTER_ID = "7250000000000000021";
const SETUP_ID = "7250000000000000022";
const SETUP_CHARACTER_ID = "7250000000000000023";
const SESSION_ID = "7250000000000000024";
const ENTRY_ID = "7250000000000000025";
const ENTRY_SESSION_ID = "7250000000000000026";
const MEMO_ID = "7250000000000000027";
const MEMO_CHARACTER_SCOPE_ID = "7250000000000000028";
const MEMO_SETUP_SCOPE_ID = "7250000000000000029";
const MEMO_SETUPS_CHARACTER_ID = "7250000000000000030";
const MEMO_SESSION_SCOPE_ID = "7250000000000000031";

const CHARACTER_HIT: CharacterHit = {
  id: CHARACTER_ID,
  name: "Mira Vist",
  archived: false,
};
const SETUP_HIT: SetupHit = {
  id: SETUP_ID,
  name: "A night with Mira",
  character_id: SETUP_CHARACTER_ID,
  character_name: "Brenn Oduya",
  archived: true,
};
const SESSION_HIT: SessionHit = {
  id: SESSION_ID,
  character_name: "Corvin Hale",
  setup_name: "Harbour nights",
  created_at: "2026-03-14T09:26:53.000000+00:00",
  archived: false,
};
const ENTRY_HIT: EntryHit = {
  id: ENTRY_ID,
  session_id: ENTRY_SESSION_ID,
  snippet: "…and then Mira left the harbour…",
  character_name: "Dask Orrery",
  session_created_at: "2026-03-10T11:00:00.000000+00:00",
};
const MEMO_HIT: MemoHit = {
  id: MEMO_ID,
  scope: "character",
  scope_id: MEMO_CHARACTER_SCOPE_ID,
  character_id: MEMO_CHARACTER_SCOPE_ID,
  snippet: "Mira never travels by day.",
  is_enabled: false,
};

const RESULTS: MySearchResults = {
  characters: [CHARACTER_HIT],
  setups: [SETUP_HIT],
  sessions: [SESSION_HIT],
  entries: [ENTRY_HIT],
  memos: [MEMO_HIT],
};

const EMPTY_RESULTS: MySearchResults = {
  characters: [],
  setups: [],
  sessions: [],
  entries: [],
  memos: [],
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

function envelope(code: string, message: string): unknown {
  return { error: { code, message, detail: {} } };
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

/** Answers on the exact pathname `/api/search` only; anything else is a 404. */
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

/** A deep copy, so seeding a state never shares a row object with a fixture. */
function copyResults(results: MySearchResults): MySearchResults {
  return JSON.parse(JSON.stringify(results)) as MySearchResults;
}

function snapshot(state: SearchState) {
  return {
    status: state.status,
    query: state.query,
    results: toJS(state.results),
    failure: state.failure,
  };
}

/** A state as the page would hold it after one successful load. */
function withResults(results: MySearchResults, query = QUERY): SearchState {
  const state = new SearchState();
  runInAction(() => {
    state.status = "ready";
    state.query = query;
    state.results = copyResults(results);
    state.failure = null;
  });
  return state;
}

/** A state parked in one non-ready status, carrying results that are not empty-of-hits. */
function inStatus(status: SearchLoadStatus, results: MySearchResults | null): SearchState {
  const state = new SearchState();
  runInAction(() => {
    state.status = status;
    state.results = results === null ? null : copyResults(results);
  });
  return state;
}

// ---------------------------------------------------------------------------
describe("SearchState — the data contract (frontend constraints)", () => {
  it("starts idle, with no query, no results and no failure — DoD-3", () => {
    expect(snapshot(new SearchState())).toEqual({
      status: "idle",
      query: "",
      results: null,
      failure: null,
    });
  });
});

// ---------------------------------------------------------------------------
describe("isBlankQuery — the blank-query predicate (D1)", () => {
  it("is true for empty and whitespace-only text and false for real text — DoD-3", () => {
    expect(isBlankQuery("")).toBe(true);
    expect(isBlankQuery("   ")).toBe(true);
    expect(isBlankQuery("\n\t ")).toBe(true);
    expect(isBlankQuery(QUERY)).toBe(false);
    expect(isBlankQuery("  a  ")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("loadSearch — a blank query asks nothing and shows nothing (D1, U4)", () => {
  it("makes no request and leaves a fresh state idle with no results — DoD-3", async () => {
    for (const blank of BLANK_QUERIES) {
      const mock = serveSearch(RESULTS);
      const state = new SearchState();

      await expect(loadSearch(state, blank)).resolves.toBeUndefined();
      await flush();

      expect(mock).not.toHaveBeenCalled();
      expect(state.status).toBe("idle");
      expect(state.results).toBeNull();
      expect(state.failure).toBeNull();
      vi.unstubAllGlobals();
    }
  });

  it("clears a state that already held ready results, still without a request — DoD-3", async () => {
    for (const blank of BLANK_QUERIES) {
      const mock = serveSearch(RESULTS);
      const state = withResults(RESULTS);

      await expect(loadSearch(state, blank)).resolves.toBeUndefined();
      await flush();

      expect(mock).not.toHaveBeenCalled();
      expect(state.status).toBe("idle");
      expect(state.results).toBeNull();
      expect(state.failure).toBeNull();
      vi.unstubAllGlobals();
    }
  });
});

// ---------------------------------------------------------------------------
describe("loadSearch — loading, then the results or the failure inline (U1)", () => {
  it("is loading while the request is pending, then ready with the query it loaded — DoD-4", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = new SearchState();

    const running = loadSearch(state, QUERY);
    await flush();
    expect(state.status).toBe("loading");

    pending.resolve(jsonResponse(RESULTS, 200));
    await expect(running).resolves.toBeUndefined();

    expect(state.status).toBe("ready");
    expect(toJS(state.results)).toEqual(RESULTS);
    expect(state.query).toBe(QUERY);
    expect(state.failure).toBeNull();
  });

  it("writes the server's five groups exactly as received — DoD-4", async () => {
    serveSearch(RESULTS);
    const state = new SearchState();

    await loadSearch(state, QUERY);

    expect(toJS(state.results)).toEqual(RESULTS);
  });

  it("resolves and records the envelope's message when the provider is unreachable — DoD-4", async () => {
    serveSearch(envelope("llm_unreachable", UNREACHABLE_MESSAGE), 502);
    const state = new SearchState();

    await expect(loadSearch(state, QUERY)).resolves.toBeUndefined();

    expect(state.status).toBe("failed");
    expect(state.failure).toBe(UNREACHABLE_MESSAGE);
    expect(state.results).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("loadSearch — an aborted load writes nothing (frontend constraints)", () => {
  it("resolves and writes nothing when the request rejects as the abort — DoD-5", async () => {
    stubFetch(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          const signal = init?.signal;
          signal?.addEventListener("abort", () => {
            reject(signal.reason ?? new DOMException("The operation was aborted.", "AbortError"));
          });
        }),
    );
    const state = new SearchState();
    const controller = new AbortController();

    const running = loadSearch(state, QUERY, controller.signal);
    await flush();
    const atAbort = snapshot(state);
    expect(atAbort.status).toBe("loading");

    controller.abort();
    await expect(running).resolves.toBeUndefined();
    await flush();

    expect(snapshot(state)).toEqual(atAbort);
  });

  it("writes nothing when the response arrives after the abort — DoD-5", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = new SearchState();
    const controller = new AbortController();

    const running = loadSearch(state, QUERY, controller.signal);
    await flush();
    const atAbort = snapshot(state);
    expect(atAbort.status).toBe("loading");

    controller.abort();
    pending.resolve(jsonResponse(RESULTS, 200));
    await expect(running).resolves.toBeUndefined();
    await flush();

    expect(snapshot(state)).toEqual(atAbort);
    expect(state.results).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("hasNoHits — the Nothing found. condition (context.md literals)", () => {
  it("is true for a ready state whose five groups are all empty — DoD-6", () => {
    expect(hasNoHits(withResults(EMPTY_RESULTS))).toBe(true);
  });

  it("is false for a ready state with a hit in any one group — DoD-6", () => {
    const oneHitPerGroup: MySearchResults[] = [
      { ...EMPTY_RESULTS, characters: [CHARACTER_HIT] },
      { ...EMPTY_RESULTS, setups: [SETUP_HIT] },
      { ...EMPTY_RESULTS, sessions: [SESSION_HIT] },
      { ...EMPTY_RESULTS, entries: [ENTRY_HIT] },
      { ...EMPTY_RESULTS, memos: [MEMO_HIT] },
    ];

    for (const results of oneHitPerGroup) {
      expect(hasNoHits(withResults(results))).toBe(false);
    }
    expect(hasNoHits(withResults(RESULTS))).toBe(false);
  });

  it("is false whenever the state is not ready — DoD-6", () => {
    expect(hasNoHits(new SearchState())).toBe(false);
    expect(hasNoHits(inStatus("idle", EMPTY_RESULTS))).toBe(false);
    expect(hasNoHits(inStatus("loading", EMPTY_RESULTS))).toBe(false);
    expect(hasNoHits(inStatus("loading", null))).toBe(false);
    expect(hasNoHits(inStatus("failed", EMPTY_RESULTS))).toBe(false);
    expect(hasNoHits(inStatus("failed", null))).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("searchHref — the results page's own URL (U4, D8)", () => {
  it("is the bare /search for a blank query — DoD-7", () => {
    expect(searchHref("")).toBe("/search");
    expect(searchHref("  ")).toBe("/search");
  });

  it("carries the query as the q parameter, whatever the escaping — DoD-7", () => {
    const url = new URL(searchHref("a b&c"), "http://localhost");

    expect(url.pathname).toBe("/search");
    expect(url.searchParams.get("q")).toBe("a b&c");
  });
});

// ---------------------------------------------------------------------------
describe("the target helpers — a row lands on what it names (UC-060, U4, D8)", () => {
  it("a character hit targets its own character page — DoD-8", () => {
    expect(characterTarget(CHARACTER_HIT)).toBe(`/characters/${CHARACTER_ID}`);
  });

  it("a setup hit targets its character's page, not a setup route — DoD-8", () => {
    expect(setupTarget(SETUP_HIT)).toBe(`/characters/${SETUP_CHARACTER_ID}`);
  });

  it("a session hit targets its own session — DoD-8", () => {
    expect(sessionTarget(SESSION_HIT)).toBe(`/sessions/${SESSION_ID}`);
  });

  it("an entry hit targets its session with the entry anchor param — DoD-8", () => {
    expect(entryTarget(ENTRY_HIT)).toBe(`/sessions/${ENTRY_SESSION_ID}?entry=${ENTRY_ID}`);
  });

  it("a user-level note targets the settings page — DoD-8", () => {
    const hit: MemoHit = {
      id: MEMO_ID,
      scope: "user",
      scope_id: null,
      character_id: null,
      snippet: "Write short sentences.",
      is_enabled: true,
    };

    expect(memoTarget(hit)).toBe("/settings");
  });

  it("a character-level note targets that character's page — DoD-8", () => {
    const hit: MemoHit = {
      id: MEMO_ID,
      scope: "character",
      scope_id: MEMO_CHARACTER_SCOPE_ID,
      character_id: MEMO_CHARACTER_SCOPE_ID,
      snippet: "Mira never travels by day.",
      is_enabled: true,
    };

    expect(memoTarget(hit)).toBe(`/characters/${MEMO_CHARACTER_SCOPE_ID}`);
  });

  it("a setup-level note targets the setup's character page — DoD-8", () => {
    const hit: MemoHit = {
      id: MEMO_ID,
      scope: "setup",
      scope_id: MEMO_SETUP_SCOPE_ID,
      character_id: MEMO_SETUPS_CHARACTER_ID,
      snippet: "The harbour is always fog-bound.",
      is_enabled: false,
    };

    expect(memoTarget(hit)).toBe(`/characters/${MEMO_SETUPS_CHARACTER_ID}`);
  });

  it("a session-level note targets its session with the wall-open param — DoD-8", () => {
    const hit: MemoHit = {
      id: MEMO_ID,
      scope: "session",
      scope_id: MEMO_SESSION_SCOPE_ID,
      character_id: null,
      snippet: "Keep the tone dry tonight.",
      is_enabled: true,
    };

    expect(memoTarget(hit)).toBe(`/sessions/${MEMO_SESSION_SCOPE_ID}?notes=open`);
  });
});
