// Feature 010, step 004 — the setups section state (DoD-4..DoD-11).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 004.context.md and context.md's D4, D10, D11, D12 and the "No context, no methods" /
// "Ids are strings" / "Never optimistic" constraints: a data class with observable fields
// only; loadSetups sets "loading", writes the server's rows in the server's order, writes
// "failed" without rejecting and writes nothing once aborted; applySetup is D11's upsert —
// replace in place, drop an archived row while Show archived setups is off, and insert an
// absent visible row at its created_at-descending position (never by id); archiveRow and
// restoreRow hold pendingId while the request is in flight, keep the row listed until the
// server answers, and report D12's two fixed sentences on failure; setShowArchived only
// flips the flag.
import { autorun, runInAction, toJS } from "mobx";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Setup } from "../../src/app/setupsApi";
import {
  applySetup,
  archiveRow,
  loadSetups,
  restoreRow,
  SetupsSectionState,
  setShowArchived,
} from "../../src/app/setupsSectionState";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// Ids ascend while created_at descends: anything ordering by id would be caught.
// All ids are past Number.MAX_SAFE_INTEGER.
const CHARACTER_ID = "7250000000000000001";
const LIST_PATH = `/api/characters/${CHARACTER_ID}/setups`;
const FAILURE_MESSAGE = "The setup shelf collapsed zq-63.";

// D12's two sentences, verbatim.
const ARCHIVE_FAILED = "Could not archive the setup.";
const RESTORE_FAILED = "Could not restore the setup.";

const TAVERN: Setup = {
  id: "7260000000000000001",
  character_id: CHARACTER_ID,
  name: "The Gilded Tavern",
  description: "# The Gilded Tavern\n\nSmoke and lute strings.",
  archived_at: null,
  created_at: "2026-03-14T09:26:53.000000+00:00",
  updated_at: "2026-03-14T09:26:53.000000+00:00",
};
const HARBOUR: Setup = {
  id: "7260000000000000002",
  character_id: CHARACTER_ID,
  name: "Nightfall Harbour",
  description: "# Nightfall Harbour\n\nTwo ships, no harbourmaster.",
  archived_at: null,
  created_at: "2026-03-10T11:00:00.000000+00:00",
  updated_at: "2026-03-10T11:00:00.000000+00:00",
};
const CELLAR: Setup = {
  id: "7260000000000000003",
  character_id: CHARACTER_ID,
  name: "The Salt Cellar",
  description: "# The Salt Cellar\n\nA room below a room.",
  archived_at: null,
  created_at: "2026-03-01T08:15:42.000000+00:00",
  updated_at: "2026-03-01T08:15:42.000000+00:00",
};
/** created_at newer than every row in WORKING. */
const NEWEST: Setup = {
  id: "7260000000000000004",
  character_id: CHARACTER_ID,
  name: "Dawn Caravan",
  description: "# Dawn Caravan",
  archived_at: null,
  created_at: "2026-04-02T00:00:00.000000+00:00",
  updated_at: "2026-04-02T00:00:00.000000+00:00",
};
/** created_at between HARBOUR's and CELLAR's. */
const BETWEEN: Setup = {
  id: "7260000000000000005",
  character_id: CHARACTER_ID,
  name: "Esker Crossing",
  description: "# Esker Crossing",
  archived_at: null,
  created_at: "2026-03-05T12:00:00.000000+00:00",
  updated_at: "2026-03-05T12:00:00.000000+00:00",
};
/** created_at older than every row in WORKING. */
const OLDEST: Setup = {
  id: "7260000000000000006",
  character_id: CHARACTER_ID,
  name: "Fen Marrow Camp",
  description: "# Fen Marrow Camp",
  archived_at: null,
  created_at: "2026-01-02T03:04:05.000000+00:00",
  updated_at: "2026-01-02T03:04:05.000000+00:00",
};

/** The server's D10 order: newest created first. */
const WORKING: Setup[] = [TAVERN, HARBOUR, CELLAR];

const ARCHIVED_AT = "2026-04-05T10:00:00.000000+00:00";

function archivedCopy(setup: Setup): Setup {
  return { ...setup, archived_at: ARCHIVED_AT, updated_at: ARCHIVED_AT };
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

function copyRows(rows: Setup[]): Setup[] {
  return rows.map((row) => ({ ...row }));
}

function serveList(rows: Setup[]) {
  return stubFetch(() => Promise.resolve(jsonResponse({ setups: copyRows(rows) }, 200)));
}

function serveSetup(setup: Setup) {
  return stubFetch(() => Promise.resolve(jsonResponse({ ...setup }, 200)));
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

function snapshot(state: SetupsSectionState) {
  return {
    characterId: state.characterId,
    setups: toJS(state.setups),
    status: state.status,
    showArchived: state.showArchived,
    error: state.error,
    pendingId: state.pendingId,
  };
}

function ids(state: SetupsSectionState): string[] {
  return state.setups.map((row) => row.id);
}

function listed(state: SetupsSectionState, setupId: string): Setup | undefined {
  return toJS(state.setups).find((row) => row.id === setupId);
}

/** A state already loaded with rows, as the section would be after its first load. */
function withSetups(rows: Setup[], showArchived = false): SetupsSectionState {
  const state = new SetupsSectionState(CHARACTER_ID);
  runInAction(() => {
    state.setups = copyRows(rows);
    state.status = "ready";
    state.showArchived = showArchived;
  });
  return state;
}

// ---------------------------------------------------------------------------
describe("a fresh SetupsSectionState", () => {
  it("has the character id as constructed, no rows, idle, the switch off and no error or pending row — DoD-4", () => {
    expect(snapshot(new SetupsSectionState("c1"))).toEqual({
      characterId: "c1",
      setups: [],
      status: "idle",
      showArchived: false,
      error: null,
      pendingId: null,
    });
  });
});

// ---------------------------------------------------------------------------
describe("loadSetups", () => {
  it("is loading while the request is pending, then ready — DoD-5", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = new SetupsSectionState(CHARACTER_ID);
    const running = loadSetups(state);
    await flush();
    expect(state.status).toBe("loading");
    pending.resolve(jsonResponse({ setups: copyRows(WORKING) }, 200));
    await running;
    expect(state.status).toBe("ready");
  });

  it("goes back to loading while a reload of an already-ready state is pending — DoD-5", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = withSetups(WORKING);
    const running = loadSetups(state);
    await flush();
    expect(state.status).toBe("loading");
    pending.resolve(jsonResponse({ setups: copyRows([TAVERN]) }, 200));
    await running;
    expect(state.status).toBe("ready");
  });

  it("writes exactly the server's rows in the server's order — DoD-5", async () => {
    serveList(WORKING);
    const state = new SetupsSectionState(CHARACTER_ID);
    await expect(loadSetups(state)).resolves.toBeUndefined();
    expect(toJS(state.setups)).toEqual([TAVERN, HARBOUR, CELLAR]);
    expect(state.status).toBe("ready");
  });

  it("keeps the server's order even when it is not the created_at order — DoD-5", async () => {
    serveList([CELLAR, TAVERN, HARBOUR]);
    const state = new SetupsSectionState(CHARACTER_ID);
    await loadSetups(state);
    expect(ids(state)).toEqual([CELLAR.id, TAVERN.id, HARBOUR.id]);
  });

  it("an empty listing is ready with no rows — DoD-5", async () => {
    serveList([]);
    const state = new SetupsSectionState(CHARACTER_ID);
    await loadSetups(state);
    expect(toJS(state.setups)).toEqual([]);
    expect(state.status).toBe("ready");
  });

  it("requests the character's listing with no flag while showArchived is false — DoD-5", async () => {
    const mock = serveList(WORKING);
    await loadSetups(new SetupsSectionState(CHARACTER_ID));
    expect(seen(mock)).toEqual([{ method: "GET", path: LIST_PATH, search: "" }]);
  });

  it("requests include_archived=true while showArchived is true — DoD-5", async () => {
    const mock = serveList(WORKING);
    const state = new SetupsSectionState(CHARACTER_ID);
    setShowArchived(state, true);
    await loadSetups(state);
    expect(seen(mock)).toEqual([
      { method: "GET", path: LIST_PATH, search: "?include_archived=true" },
    ]);
  });

  it("a failed load becomes failed, keeps the previous rows and does not reject — DoD-5", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    const state = withSetups(WORKING);
    await expect(loadSetups(state)).resolves.toBeUndefined();
    expect(state.status).toBe("failed");
    expect(toJS(state.setups)).toEqual([TAVERN, HARBOUR, CELLAR]);
  });

  it("a first failed load becomes failed with no rows and does not reject — DoD-5", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    const state = new SetupsSectionState(CHARACTER_ID);
    await expect(loadSetups(state)).resolves.toBeUndefined();
    expect(state.status).toBe("failed");
    expect(toJS(state.setups)).toEqual([]);
  });

  it("a transport failure is also failed, not a rejection — DoD-5", async () => {
    stubFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    const state = withSetups(WORKING);
    await expect(loadSetups(state)).resolves.toBeUndefined();
    expect(state.status).toBe("failed");
    expect(toJS(state.setups)).toEqual([TAVERN, HARBOUR, CELLAR]);
  });

  it("writes nothing when its signal aborts before the response settles — DoD-5", async () => {
    stubFetch(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          const signal = init?.signal;
          signal?.addEventListener("abort", () => {
            reject(signal.reason ?? new DOMException("The operation was aborted.", "AbortError"));
          });
        }),
    );
    const state = withSetups(WORKING);
    const controller = new AbortController();
    const running = loadSetups(state, controller.signal);
    await flush();
    const atAbort = snapshot(state);
    controller.abort();
    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(snapshot(state)).toEqual(atAbort);
    expect(toJS(state.setups)).toEqual([TAVERN, HARBOUR, CELLAR]);
  });

  it("writes nothing when a response arrives after the abort — DoD-5", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = withSetups(WORKING);
    const controller = new AbortController();
    const running = loadSetups(state, controller.signal);
    await flush();
    const atAbort = snapshot(state);
    controller.abort();
    pending.resolve(jsonResponse({ setups: copyRows([NEWEST]) }, 200));
    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(snapshot(state)).toEqual(atAbort);
    expect(toJS(state.setups)).toEqual([TAVERN, HARBOUR, CELLAR]);
  });
});

// ---------------------------------------------------------------------------
describe("applySetup — a present row is replaced in place", () => {
  it("replaces a row by id at its own index, with the new values — DoD-6", () => {
    const state = withSetups(WORKING);
    const edited: Setup = {
      ...HARBOUR,
      name: "Nightfall Harbour, rebuilt",
      description: "# Nightfall Harbour\n\nA harbourmaster at last.",
      updated_at: "2026-04-06T12:00:00.000000+00:00",
    };
    applySetup(state, edited);
    expect(toJS(state.setups)).toEqual([TAVERN, edited, CELLAR]);
    expect(ids(state)).toEqual([TAVERN.id, HARBOUR.id, CELLAR.id]);
  });

  it("replacing the first row leaves it first, even though its created_at did not change — DoD-6", () => {
    const state = withSetups(WORKING);
    const edited: Setup = { ...TAVERN, name: "The Gilded Cage" };
    applySetup(state, edited);
    expect(toJS(state.setups)).toEqual([edited, HARBOUR, CELLAR]);
  });

  it("replaces in place while showArchived is true as well — DoD-6", () => {
    const state = withSetups(WORKING, true);
    const edited: Setup = { ...CELLAR, name: "The Salt Cellar, flooded" };
    applySetup(state, edited);
    expect(toJS(state.setups)).toEqual([TAVERN, HARBOUR, edited]);
  });
});

// ---------------------------------------------------------------------------
describe("applySetup — an absent working row is inserted by created_at descending", () => {
  it("a row newer than every existing row lands first — DoD-6", () => {
    const state = withSetups(WORKING);
    applySetup(state, NEWEST);
    expect(ids(state)).toEqual([NEWEST.id, TAVERN.id, HARBOUR.id, CELLAR.id]);
    expect(toJS(state.setups)[0]).toEqual(NEWEST);
  });

  it("a row whose created_at falls between two rows lands between them — DoD-6", () => {
    const state = withSetups(WORKING);
    applySetup(state, BETWEEN);
    expect(ids(state)).toEqual([TAVERN.id, HARBOUR.id, BETWEEN.id, CELLAR.id]);
  });

  it("a row older than every existing row lands last — DoD-6", () => {
    const state = withSetups(WORKING);
    applySetup(state, OLDEST);
    expect(ids(state)).toEqual([TAVERN.id, HARBOUR.id, CELLAR.id, OLDEST.id]);
  });

  it("the first row of an empty list is simply inserted — DoD-6", () => {
    const state = withSetups([]);
    applySetup(state, BETWEEN);
    expect(toJS(state.setups)).toEqual([BETWEEN]);
  });

  it("an absent archived row is inserted by created_at while showArchived is true — DoD-6", () => {
    const state = withSetups(WORKING, true);
    const archived = archivedCopy(BETWEEN);
    applySetup(state, archived);
    expect(ids(state)).toEqual([TAVERN.id, HARBOUR.id, BETWEEN.id, CELLAR.id]);
    expect(listed(state, BETWEEN.id)).toEqual(archived);
  });
});

// ---------------------------------------------------------------------------
describe("applySetup — an archived row against the Show archived setups flag", () => {
  it("removes a now-archived row while showArchived is false — DoD-7", () => {
    const state = withSetups(WORKING);
    applySetup(state, archivedCopy(HARBOUR));
    expect(toJS(state.setups)).toEqual([TAVERN, CELLAR]);
  });

  it("leaves the rows unchanged when the archived row's id is absent — DoD-7", () => {
    const state = withSetups(WORKING);
    applySetup(state, archivedCopy(BETWEEN));
    expect(toJS(state.setups)).toEqual([TAVERN, HARBOUR, CELLAR]);
  });

  it("does not insert an absent archived row even when it is newer than everything — DoD-7", () => {
    const state = withSetups(WORKING);
    applySetup(state, archivedCopy(NEWEST));
    expect(ids(state)).toEqual([TAVERN.id, HARBOUR.id, CELLAR.id]);
  });

  it("leaves an empty list empty for an absent archived row — DoD-7", () => {
    const state = withSetups([]);
    applySetup(state, archivedCopy(NEWEST));
    expect(toJS(state.setups)).toEqual([]);
  });

  it("replaces a now-archived row in place and keeps it while showArchived is true — DoD-7", () => {
    const state = withSetups(WORKING, true);
    const archived = archivedCopy(HARBOUR);
    applySetup(state, archived);
    expect(toJS(state.setups)).toEqual([TAVERN, archived, CELLAR]);
  });

  it("a restored row replaces its archived self in place while showArchived is true — DoD-7", () => {
    const state = withSetups([TAVERN, archivedCopy(HARBOUR), CELLAR], true);
    applySetup(state, HARBOUR);
    expect(toJS(state.setups)).toEqual([TAVERN, HARBOUR, CELLAR]);
  });
});

// ---------------------------------------------------------------------------
describe("archiveRow", () => {
  it("POSTs /api/setups/<id>/archive — DoD-8", async () => {
    const mock = serveSetup(archivedCopy(HARBOUR));
    const state = withSetups(WORKING);
    await archiveRow(state, HARBOUR.id);
    expect(seen(mock)).toEqual([
      { method: "POST", path: `/api/setups/${HARBOUR.id}/archive`, search: "" },
    ]);
  });

  it("holds pendingId and keeps the row listed while the request is pending — DoD-8", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = withSetups(WORKING);
    const running = archiveRow(state, HARBOUR.id);
    await flush();
    expect(state.pendingId).toBe(HARBOUR.id);
    expect(ids(state)).toEqual([TAVERN.id, HARBOUR.id, CELLAR.id]);
    expect(listed(state, HARBOUR.id)).toEqual(HARBOUR);
    pending.resolve(jsonResponse(archivedCopy(HARBOUR), 200));
    await expect(running).resolves.toBeUndefined();
  });

  it("drops the row and clears pendingId once the server answers, while showArchived is false — DoD-8", async () => {
    serveSetup(archivedCopy(HARBOUR));
    const state = withSetups(WORKING);
    await expect(archiveRow(state, HARBOUR.id)).resolves.toBeUndefined();
    expect(ids(state)).toEqual([TAVERN.id, CELLAR.id]);
    expect(state.pendingId).toBeNull();
  });

  it("keeps the row listed with the response's archived_at while showArchived is true — DoD-8", async () => {
    const archived = archivedCopy(HARBOUR);
    serveSetup(archived);
    const state = withSetups(WORKING, true);
    await archiveRow(state, HARBOUR.id);
    expect(ids(state)).toEqual([TAVERN.id, HARBOUR.id, CELLAR.id]);
    expect(listed(state, HARBOUR.id)).toEqual(archived);
    expect(listed(state, HARBOUR.id)?.archived_at).toBe(ARCHIVED_AT);
    expect(state.pendingId).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("restoreRow", () => {
  it("POSTs /api/setups/<id>/restore — DoD-9", async () => {
    const mock = serveSetup(HARBOUR);
    const state = withSetups([TAVERN, archivedCopy(HARBOUR), CELLAR], true);
    await restoreRow(state, HARBOUR.id);
    expect(seen(mock)).toEqual([
      { method: "POST", path: `/api/setups/${HARBOUR.id}/restore`, search: "" },
    ]);
  });

  it("holds pendingId while the request is pending, then clears it — DoD-9", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = withSetups([TAVERN, archivedCopy(HARBOUR), CELLAR], true);
    const running = restoreRow(state, HARBOUR.id);
    await flush();
    expect(state.pendingId).toBe(HARBOUR.id);
    pending.resolve(jsonResponse({ ...HARBOUR }, 200));
    await expect(running).resolves.toBeUndefined();
    expect(state.pendingId).toBeNull();
  });

  it("lists the row with archived_at null after the response — DoD-9", async () => {
    serveSetup(HARBOUR);
    const state = withSetups([TAVERN, archivedCopy(HARBOUR), CELLAR], true);
    await expect(restoreRow(state, HARBOUR.id)).resolves.toBeUndefined();
    expect(listed(state, HARBOUR.id)).toEqual(HARBOUR);
    expect(listed(state, HARBOUR.id)?.archived_at).toBeNull();
  });

  it("keeps the restored row listed once showArchived is set false — DoD-9", async () => {
    serveSetup(HARBOUR);
    const state = withSetups([TAVERN, archivedCopy(HARBOUR), CELLAR], true);
    await restoreRow(state, HARBOUR.id);
    setShowArchived(state, false);
    expect(ids(state)).toEqual([TAVERN.id, HARBOUR.id, CELLAR.id]);
    expect(listed(state, HARBOUR.id)).toEqual(HARBOUR);
  });
});

// ---------------------------------------------------------------------------
describe("a failed row action", () => {
  it("archiveRow reports \"Could not archive the setup.\", leaves the rows and resolves — DoD-10", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    const state = withSetups(WORKING);
    await expect(archiveRow(state, HARBOUR.id)).resolves.toBeUndefined();
    expect(state.error).toBe(ARCHIVE_FAILED);
    expect(toJS(state.setups)).toEqual([TAVERN, HARBOUR, CELLAR]);
    expect(state.pendingId).toBeNull();
  });

  it("restoreRow reports \"Could not restore the setup.\", leaves the rows and resolves — DoD-10", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    const rows = [TAVERN, archivedCopy(HARBOUR), CELLAR];
    const state = withSetups(rows, true);
    await expect(restoreRow(state, HARBOUR.id)).resolves.toBeUndefined();
    expect(state.error).toBe(RESTORE_FAILED);
    expect(toJS(state.setups)).toEqual(rows);
    expect(state.pendingId).toBeNull();
  });

  it("a transport failure reports the same sentence and does not reject — DoD-10", async () => {
    stubFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    const state = withSetups(WORKING);
    await expect(archiveRow(state, HARBOUR.id)).resolves.toBeUndefined();
    expect(state.error).toBe(ARCHIVE_FAILED);
    expect(toJS(state.setups)).toEqual([TAVERN, HARBOUR, CELLAR]);
    expect(state.pendingId).toBeNull();
  });

  it("a row action started after a failure has cleared the error before its request — DoD-10", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    const state = withSetups([TAVERN, archivedCopy(HARBOUR), CELLAR], true);
    await archiveRow(state, HARBOUR.id);
    expect(state.error).toBe(ARCHIVE_FAILED);

    const errorAtRequest: Array<string | null> = [];
    stubFetch(() => {
      errorAtRequest.push(state.error);
      return Promise.resolve(jsonResponse({ ...HARBOUR }, 200));
    });
    await expect(restoreRow(state, HARBOUR.id)).resolves.toBeUndefined();
    expect(errorAtRequest).toEqual([null]);
    expect(state.error).toBeNull();
  });

  it("a second archive started after a failure has cleared the error before its request — DoD-10", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    const state = withSetups(WORKING);
    await archiveRow(state, HARBOUR.id);
    expect(state.error).toBe(ARCHIVE_FAILED);

    const errorAtRequest: Array<string | null> = [];
    stubFetch(() => {
      errorAtRequest.push(state.error);
      return Promise.resolve(jsonResponse(archivedCopy(HARBOUR), 200));
    });
    await archiveRow(state, HARBOUR.id);
    expect(errorAtRequest).toEqual([null]);
  });
});

// ---------------------------------------------------------------------------
describe("setShowArchived and the observability of the writes", () => {
  it("sets the flag and issues no request — DoD-11", () => {
    const mock = stubFetch(() => Promise.resolve(jsonResponse({ setups: [] }, 200)));
    const state = withSetups(WORKING);
    setShowArchived(state, true);
    expect(state.showArchived).toBe(true);
    setShowArchived(state, false);
    expect(state.showArchived).toBe(false);
    expect(mock).not.toHaveBeenCalled();
  });

  it("leaves the rows and the status alone — DoD-11", () => {
    const state = withSetups(WORKING);
    setShowArchived(state, true);
    expect(toJS(state.setups)).toEqual([TAVERN, HARBOUR, CELLAR]);
    expect(state.status).toBe("ready");
  });

  it("an autorun reading setups re-runs after applySetup — DoD-11", () => {
    const state = withSetups(WORKING);
    const observed: string[][] = [];
    const dispose = autorun(() => {
      observed.push(state.setups.map((row) => row.id));
    });
    expect(observed).toHaveLength(1);
    applySetup(state, NEWEST);
    expect(observed.length).toBeGreaterThan(1);
    expect(observed[observed.length - 1]).toEqual([
      NEWEST.id,
      TAVERN.id,
      HARBOUR.id,
      CELLAR.id,
    ]);
    dispose();
  });

  it("an autorun reading setups re-runs after an in-place replacement — DoD-11", () => {
    const state = withSetups(WORKING);
    const observed: string[][] = [];
    const dispose = autorun(() => {
      observed.push(state.setups.map((row) => row.name));
    });
    expect(observed).toHaveLength(1);
    applySetup(state, { ...HARBOUR, name: "Nightfall Harbour, rebuilt" });
    expect(observed.length).toBeGreaterThan(1);
    expect(observed[observed.length - 1]).toEqual([
      TAVERN.name,
      "Nightfall Harbour, rebuilt",
      CELLAR.name,
    ]);
    dispose();
  });

  it("an autorun reading showArchived re-runs after setShowArchived — DoD-11", () => {
    const state = withSetups(WORKING);
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
});
