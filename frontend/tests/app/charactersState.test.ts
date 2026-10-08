// Feature 009, step 004 — the workspace characters state (DoD-5..DoD-11).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 004.context.md ("The insert position, concretely") and context.md's D4, D10, D11 and the
// "No context, no methods" / "Ids are strings" constraints: a data class with observable
// fields only; loadCharacters sets "loading", writes the server's rows in the server's
// order, writes "failed" without rejecting and writes nothing once aborted; applyCharacter
// is D11's upsert — replace in place, drop an archived row while Show archived is off, and
// insert an absent visible row at its created_at-descending position (never by id);
// setShowArchived only flips the flag.
import { autorun, isComputedProp, isObservableProp, runInAction, toJS } from "mobx";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Character } from "../../src/app/charactersApi";
import {
  applyCharacter,
  CharactersState,
  loadCharacters,
  setShowArchived,
} from "../../src/app/charactersState";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const LIST_PATH = "/api/characters";
const FAILURE_MESSAGE = "The character ledger is on fire zq-63.";

// Ids ascend while created_at descends: anything ordering by id would be caught.
// All ids are past Number.MAX_SAFE_INTEGER.
const ALMA: Character = {
  id: "7250000000000000001",
  name: "Alma Vist",
  sheet: "# Alma",
  archived_at: null,
  created_at: "2026-03-14T09:26:53.000000+00:00",
  updated_at: "2026-03-14T09:26:53.000000+00:00",
};
const BRENN: Character = {
  id: "7250000000000000002",
  name: "Brenn Oduya",
  sheet: "# Brenn",
  archived_at: null,
  created_at: "2026-03-10T11:00:00.000000+00:00",
  updated_at: "2026-03-10T11:00:00.000000+00:00",
};
const CORVIN: Character = {
  id: "7250000000000000003",
  name: "Corvin Hale",
  sheet: "# Corvin",
  archived_at: null,
  created_at: "2026-03-01T08:15:42.000000+00:00",
  updated_at: "2026-03-01T08:15:42.000000+00:00",
};
/** created_at newer than every row in WORKING. */
const NEWEST: Character = {
  id: "7250000000000000004",
  name: "Dask Orrery",
  sheet: "# Dask",
  archived_at: null,
  created_at: "2026-04-02T00:00:00.000000+00:00",
  updated_at: "2026-04-02T00:00:00.000000+00:00",
};
/** created_at between BRENN's and CORVIN's. */
const BETWEEN: Character = {
  id: "7250000000000000005",
  name: "Esker Lune",
  sheet: "# Esker",
  archived_at: null,
  created_at: "2026-03-05T12:00:00.000000+00:00",
  updated_at: "2026-03-05T12:00:00.000000+00:00",
};
/** created_at older than every row in WORKING. */
const OLDEST: Character = {
  id: "7250000000000000006",
  name: "Fen Marrow",
  sheet: "# Fen",
  archived_at: null,
  created_at: "2026-01-02T03:04:05.000000+00:00",
  updated_at: "2026-01-02T03:04:05.000000+00:00",
};

/** The server's D10 order: newest created first. */
const WORKING: Character[] = [ALMA, BRENN, CORVIN];

function archivedCopy(character: Character): Character {
  return { ...character, archived_at: "2026-04-05T10:00:00.000000+00:00" };
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

function copyRows(rows: Character[]): Character[] {
  return rows.map((row) => ({ ...row }));
}

function serveList(rows: Character[]) {
  return stubFetch(() => Promise.resolve(jsonResponse({ characters: copyRows(rows) }, 200)));
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

function snapshot(state: CharactersState) {
  return {
    characters: toJS(state.characters),
    status: state.status,
    showArchived: state.showArchived,
  };
}

function ids(state: CharactersState): string[] {
  return state.characters.map((row) => row.id);
}

/** A state already loaded with rows, as the tree would be after its first load. */
function withCharacters(rows: Character[], showArchived = false): CharactersState {
  const state = new CharactersState();
  runInAction(() => {
    state.characters = copyRows(rows);
    state.status = "ready";
    state.showArchived = showArchived;
  });
  return state;
}

// ---------------------------------------------------------------------------
describe("loadCharacters", () => {
  it("is loading while the request is pending, then ready — DoD-5", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = new CharactersState();
    const running = loadCharacters(state);
    await flush();
    expect(state.status).toBe("loading");
    pending.resolve(jsonResponse({ characters: copyRows(WORKING) }, 200));
    await running;
    expect(state.status).toBe("ready");
  });

  it("goes back to loading while a reload of an already-ready state is pending — DoD-5", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = withCharacters(WORKING);
    const running = loadCharacters(state);
    await flush();
    expect(state.status).toBe("loading");
    pending.resolve(jsonResponse({ characters: copyRows([ALMA]) }, 200));
    await running;
    expect(state.status).toBe("ready");
  });

  it("writes exactly the server's rows in the server's order — DoD-5", async () => {
    serveList(WORKING);
    const state = new CharactersState();
    await expect(loadCharacters(state)).resolves.toBeUndefined();
    expect(snapshot(state)).toEqual({
      characters: [ALMA, BRENN, CORVIN],
      status: "ready",
      showArchived: false,
    });
  });

  it("keeps the server's order even when it is not the created_at order — DoD-5", async () => {
    serveList([CORVIN, ALMA, BRENN]);
    const state = new CharactersState();
    await loadCharacters(state);
    expect(ids(state)).toEqual([CORVIN.id, ALMA.id, BRENN.id]);
  });

  it("an empty listing is ready with no rows — DoD-5", async () => {
    serveList([]);
    const state = new CharactersState();
    await loadCharacters(state);
    expect(snapshot(state)).toEqual({ characters: [], status: "ready", showArchived: false });
  });

  it("requests no flag while showArchived is false — DoD-5", async () => {
    const mock = serveList(WORKING);
    await loadCharacters(new CharactersState());
    expect(seen(mock)).toEqual([{ method: "GET", path: LIST_PATH, search: "" }]);
  });

  it("requests include_archived=true while showArchived is true — DoD-5", async () => {
    const mock = serveList(WORKING);
    const state = new CharactersState();
    setShowArchived(state, true);
    await loadCharacters(state);
    expect(seen(mock)).toEqual([
      { method: "GET", path: LIST_PATH, search: "?include_archived=true" },
    ]);
  });

  it("a failed load becomes failed, keeps the previous rows and does not reject — DoD-6", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    const state = withCharacters(WORKING);
    await expect(loadCharacters(state)).resolves.toBeUndefined();
    expect(state.status).toBe("failed");
    expect(toJS(state.characters)).toEqual([ALMA, BRENN, CORVIN]);
  });

  it("a first failed load becomes failed with no rows and does not reject — DoD-6", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    const state = new CharactersState();
    await expect(loadCharacters(state)).resolves.toBeUndefined();
    expect(snapshot(state)).toEqual({ characters: [], status: "failed", showArchived: false });
  });

  it("a transport failure is also failed, not a rejection — DoD-6", async () => {
    stubFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    const state = withCharacters(WORKING);
    await expect(loadCharacters(state)).resolves.toBeUndefined();
    expect(state.status).toBe("failed");
    expect(toJS(state.characters)).toEqual([ALMA, BRENN, CORVIN]);
  });

  it("writes nothing when its signal aborts before the response settles — DoD-6", async () => {
    stubFetch(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          const signal = init?.signal;
          signal?.addEventListener("abort", () => {
            reject(signal.reason ?? new DOMException("The operation was aborted.", "AbortError"));
          });
        }),
    );
    const state = withCharacters(WORKING);
    const controller = new AbortController();
    const running = loadCharacters(state, controller.signal);
    await flush();
    const atAbort = snapshot(state);
    controller.abort();
    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(snapshot(state)).toEqual(atAbort);
    expect(toJS(state.characters)).toEqual([ALMA, BRENN, CORVIN]);
  });

  it("writes nothing when a response arrives after the abort — DoD-6", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = withCharacters(WORKING);
    const controller = new AbortController();
    const running = loadCharacters(state, controller.signal);
    await flush();
    const atAbort = snapshot(state);
    controller.abort();
    pending.resolve(jsonResponse({ characters: copyRows([NEWEST]) }, 200));
    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(snapshot(state)).toEqual(atAbort);
    expect(toJS(state.characters)).toEqual([ALMA, BRENN, CORVIN]);
  });
});

// ---------------------------------------------------------------------------
describe("applyCharacter — a present row is replaced in place", () => {
  it("replaces a row by id at its own index, with the new values — DoD-7", () => {
    const state = withCharacters(WORKING);
    const renamed: Character = {
      ...BRENN,
      name: "Brenn the Lender",
      sheet: "# Brenn\n\nUpdated.",
      updated_at: "2026-04-06T12:00:00.000000+00:00",
    };
    applyCharacter(state, renamed);
    expect(toJS(state.characters)).toEqual([ALMA, renamed, CORVIN]);
    expect(ids(state)).toEqual([ALMA.id, BRENN.id, CORVIN.id]);
  });

  it("replacing the first row leaves it first, even though its created_at did not change — DoD-7", () => {
    const state = withCharacters(WORKING);
    const renamed: Character = { ...ALMA, name: "Alma Vistaro" };
    applyCharacter(state, renamed);
    expect(toJS(state.characters)).toEqual([renamed, BRENN, CORVIN]);
  });

  it("replaces in place while showArchived is true as well — DoD-7", () => {
    const state = withCharacters(WORKING, true);
    const renamed: Character = { ...CORVIN, name: "Corvin Halewright" };
    applyCharacter(state, renamed);
    expect(toJS(state.characters)).toEqual([ALMA, BRENN, renamed]);
  });
});

// ---------------------------------------------------------------------------
describe("applyCharacter — archiving against the Show archived flag", () => {
  it("removes a now-archived row while showArchived is false — DoD-8", () => {
    const state = withCharacters(WORKING);
    applyCharacter(state, archivedCopy(BRENN));
    expect(toJS(state.characters)).toEqual([ALMA, CORVIN]);
  });

  it("keeps a now-archived row in place while showArchived is true — DoD-8", () => {
    const state = withCharacters(WORKING, true);
    const archived = archivedCopy(BRENN);
    applyCharacter(state, archived);
    expect(toJS(state.characters)).toEqual([ALMA, archived, CORVIN]);
  });

  it("a restored row replaces its archived self in place while showArchived is true — DoD-8", () => {
    const state = withCharacters([ALMA, archivedCopy(BRENN), CORVIN], true);
    applyCharacter(state, BRENN);
    expect(toJS(state.characters)).toEqual([ALMA, BRENN, CORVIN]);
  });
});

// ---------------------------------------------------------------------------
describe("applyCharacter — an absent visible row is inserted by created_at descending", () => {
  it("a row newer than every existing row lands first — DoD-9", () => {
    const state = withCharacters(WORKING);
    applyCharacter(state, NEWEST);
    expect(ids(state)).toEqual([NEWEST.id, ALMA.id, BRENN.id, CORVIN.id]);
    expect(toJS(state.characters)[0]).toEqual(NEWEST);
  });

  it("a row whose created_at falls between two rows lands between them — DoD-9", () => {
    const state = withCharacters(WORKING);
    applyCharacter(state, BETWEEN);
    expect(ids(state)).toEqual([ALMA.id, BRENN.id, BETWEEN.id, CORVIN.id]);
  });

  it("a row older than every existing row lands last — DoD-9", () => {
    const state = withCharacters(WORKING);
    applyCharacter(state, OLDEST);
    expect(ids(state)).toEqual([ALMA.id, BRENN.id, CORVIN.id, OLDEST.id]);
  });

  it("the first row of an empty list is simply inserted — DoD-9", () => {
    const state = withCharacters([]);
    applyCharacter(state, BETWEEN);
    expect(toJS(state.characters)).toEqual([BETWEEN]);
  });

  it("an absent archived row is inserted by created_at while showArchived is true — DoD-9", () => {
    const state = withCharacters(WORKING, true);
    const archived = { ...BETWEEN, archived_at: "2026-04-05T10:00:00.000000+00:00" };
    applyCharacter(state, archived);
    expect(ids(state)).toEqual([ALMA.id, BRENN.id, BETWEEN.id, CORVIN.id]);
  });

  it("an absent archived row is not inserted while showArchived is false — DoD-10", () => {
    const state = withCharacters(WORKING);
    applyCharacter(state, archivedCopy(BETWEEN));
    expect(toJS(state.characters)).toEqual([ALMA, BRENN, CORVIN]);
  });

  it("an absent archived row newer than everything is still not inserted — DoD-10", () => {
    const state = withCharacters(WORKING);
    applyCharacter(state, archivedCopy(NEWEST));
    expect(ids(state)).toEqual([ALMA.id, BRENN.id, CORVIN.id]);
  });

  it("an absent archived row leaves an empty list empty — DoD-10", () => {
    const state = withCharacters([]);
    applyCharacter(state, archivedCopy(NEWEST));
    expect(toJS(state.characters)).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("setShowArchived and the observability of the writes", () => {
  it("sets the flag and issues no request — DoD-11", () => {
    const mock = stubFetch(() => Promise.resolve(jsonResponse({ characters: [] }, 200)));
    const state = withCharacters(WORKING);
    setShowArchived(state, true);
    expect(state.showArchived).toBe(true);
    setShowArchived(state, false);
    expect(state.showArchived).toBe(false);
    expect(mock).not.toHaveBeenCalled();
  });

  it("leaves the rows and the status alone — DoD-11", () => {
    const state = withCharacters(WORKING);
    setShowArchived(state, true);
    expect(toJS(state.characters)).toEqual([ALMA, BRENN, CORVIN]);
    expect(state.status).toBe("ready");
  });

  it("an autorun reading characters re-runs after applyCharacter — DoD-11", () => {
    const state = withCharacters(WORKING);
    const observed: string[][] = [];
    const dispose = autorun(() => {
      observed.push(state.characters.map((row) => row.id));
    });
    expect(observed).toHaveLength(1);
    applyCharacter(state, NEWEST);
    expect(observed.length).toBeGreaterThan(1);
    expect(observed[observed.length - 1]).toEqual([NEWEST.id, ALMA.id, BRENN.id, CORVIN.id]);
    dispose();
  });

  it("an autorun reading characters re-runs after an in-place replacement — DoD-11", () => {
    const state = withCharacters(WORKING);
    const observed: string[][] = [];
    const dispose = autorun(() => {
      observed.push(state.characters.map((row) => row.name));
    });
    expect(observed).toHaveLength(1);
    applyCharacter(state, { ...BRENN, name: "Brenn the Lender" });
    expect(observed.length).toBeGreaterThan(1);
    expect(observed[observed.length - 1]).toEqual([ALMA.name, "Brenn the Lender", CORVIN.name]);
    dispose();
  });

  it("an autorun reading showArchived re-runs after setShowArchived — DoD-11", () => {
    const state = withCharacters(WORKING);
    const observed: boolean[] = [];
    const dispose = autorun(() => {
      observed.push(state.showArchived);
    });
    expect(observed).toEqual([false]);
    setShowArchived(state, true);
    expect(observed.length).toBeGreaterThan(1);
    expect(observed[observed.length - 1]).toBe(true);
    dispose();
  });

  it("the class prototype carries no method and no getter — DoD-11", () => {
    expect(Object.getOwnPropertyNames(CharactersState.prototype)).toEqual(["constructor"]);
  });

  it("characters, status and showArchived are the observable fields, and none is computed — DoD-11", () => {
    const state = new CharactersState();
    const observed = Object.getOwnPropertyNames(state).filter((name) =>
      isObservableProp(state, name),
    );
    expect(observed.sort()).toEqual(["characters", "showArchived", "status"]);
    for (const name of observed) {
      expect(isComputedProp(state, name), `field ${name}`).toBe(false);
    }
  });

  it("no own property of an instance is a function or a computed value — DoD-11", () => {
    const state = new CharactersState();
    const record = state as unknown as Record<string, unknown>;
    for (const name of Object.getOwnPropertyNames(state)) {
      expect(typeof record[name], `own property ${name}`).not.toBe("function");
      expect(isComputedProp(state, name), `own property ${name}`).toBe(false);
    }
  });

  it("a fresh state is idle, with no rows and Show archived off — DoD-11", () => {
    expect(snapshot(new CharactersState())).toEqual({
      characters: [],
      status: "idle",
      showArchived: false,
    });
  });

  it("the load, the flag and the upsert are free functions taking the state — DoD-11", () => {
    for (const fn of [loadCharacters, setShowArchived, applyCharacter]) {
      expect(typeof fn).toBe("function");
    }
    expect(Object.getOwnPropertyNames(CharactersState.prototype)).not.toContain("loadCharacters");
  });
});
