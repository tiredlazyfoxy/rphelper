// Feature 013, step 002 — the stream state: data class, derivations, load and the
// synchronous actions (DoD-1..DoD-12).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done plus
// context.md's D1, D2, D3, D4, D8, D13, D15, D16 and 002.context.md ("The load fetches both
// lists together", "The override rule, precisely"):
//   - `StreamState` is a data class: `sessionId` verbatim, empty `entries` / `zone`,
//     `status` "idle", `draft` "", `kindOverride` null, `busy` false;
//   - `loadStream` is "loading" while pending, requests exactly GET …/entries and GET …/zone,
//     writes both lists as served with "ready"; any failure is "failed" with the previous
//     lists kept; never rejects; writes nothing once aborted;
//   - the default position alternates on the last partner-or-turn entry (decisions skipped),
//     "turn" when there is none; the override holds until the entries' id sequence changes;
//   - Settle / Send / Discard / Re-open availability, the settle target and its preview,
//     exactly as the DoD enumerates them. Preview values come from 001.context.md's table.
import { autorun, runInAction, toJS } from "mobx";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Message, MessageKind, MessageRole } from "../../src/app/streamApi";
import {
  StreamState,
  applyEntries,
  canSend,
  canSettle,
  chooseKind,
  defaultKind,
  discardZone,
  effectiveKind,
  loadStream,
  setDraft,
  settlePreviewOf,
  settleTargetText,
  showsDiscard,
  showsReopen,
} from "../../src/app/streamState";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string };

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "s1";
const ENTRIES_PATH = `/api/sessions/${SESSION_ID}/entries`;
const ZONE_PATH = `/api/sessions/${SESSION_ID}/zone`;

const STAMP = "2026-05-10T09:00:00.000000+00:00";

let nextId = 101;
function freshId(): string {
  nextId += 1;
  return `7250000000000000${String(nextId).padStart(3, "0")}`;
}

/** A settled entry with all eight keys. */
function entry(kind: MessageKind, text = `entry text ${kind}`, id = freshId()): Message {
  return {
    id,
    session_id: SESSION_ID,
    role: kind === "partner" ? "user" : "assistant",
    kind,
    text,
    settled_at: STAMP,
    created_at: STAMP,
    updated_at: STAMP,
  };
}

/** A zone row with all eight keys: `kind` and `settled_at` null. */
function zoneRow(role: MessageRole, text = `zone text ${role}`, id = freshId()): Message {
  return {
    id,
    session_id: SESSION_ID,
    role,
    kind: null,
    text,
    settled_at: null,
    created_at: STAMP,
    updated_at: STAMP,
  };
}

type Seed = {
  entries?: Message[];
  zone?: Message[];
  draft?: string;
  kindOverride?: "partner" | "turn" | null;
  busy?: boolean;
};

function seeded(seed: Seed): StreamState {
  const state = new StreamState(SESSION_ID);
  runInAction(() => {
    if (seed.entries !== undefined) state.entries = seed.entries;
    if (seed.zone !== undefined) state.zone = seed.zone;
    if (seed.draft !== undefined) state.draft = seed.draft;
    if (seed.kindOverride !== undefined) state.kindOverride = seed.kindOverride;
    if (seed.busy !== undefined) state.busy = seed.busy;
  });
  return state;
}

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
  return jsonResponse({ error: { code, message: "ql-77 went wrong.", detail: {} } }, status);
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function stubFetch(impl: FetchFn) {
  const mock = vi.fn<FetchFn>(impl);
  vi.stubGlobal("fetch", mock);
  return mock;
}

/** A URL-routed backend keyed on exact pathname + method; every request is recorded. */
function stubBackend(handler: (request: Seen, init?: RequestInit) => Response | Promise<Response>) {
  const calls: Seen[] = [];
  const mock = stubFetch(async (input, init) => {
    const url = requestUrl(input);
    const request: Seen = { method: requestMethod(input, init), path: url.pathname, search: url.search };
    calls.push(request);
    return handler(request, init);
  });
  return { mock, calls };
}

function unexpected(request: Seen): Response {
  return envelope(`unexpected_${request.method}_${request.path}`, 418);
}

/** Answers GET …/entries and GET …/zone with the given lists, anything else unexpected. */
function serveLists(entries: Message[], zone: Message[]) {
  return stubBackend((request) => {
    if (request.method === "GET" && request.path === ENTRIES_PATH) {
      return jsonResponse({ entries }, 200);
    }
    if (request.method === "GET" && request.path === ZONE_PATH) {
      return jsonResponse({ messages: zone }, 200);
    }
    return unexpected(request);
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

async function flush(rounds = 6): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await new Promise<void>((resolve) => setImmediate(resolve));
  }
}

function snapshot(state: StreamState) {
  return {
    sessionId: state.sessionId,
    entries: toJS(state.entries),
    zone: toJS(state.zone),
    status: state.status,
    draft: state.draft,
    kindOverride: state.kindOverride,
    busy: state.busy,
  };
}

function byPath(a: Seen, b: Seen): number {
  return a.path < b.path ? -1 : a.path > b.path ? 1 : 0;
}

// ---------------------------------------------------------------------------
describe("a fresh stream state", () => {
  it("has the session id, empty lists, idle status, empty draft, no override, not busy — DoD-1", () => {
    expect(snapshot(new StreamState("s1"))).toEqual({
      sessionId: "s1",
      entries: [],
      zone: [],
      status: "idle",
      draft: "",
      kindOverride: null,
      busy: false,
    });
  });
});

// ---------------------------------------------------------------------------
describe("loadStream on the happy path", () => {
  // Served in an order that is not ascending, so any client-side sort would be visible.
  const SERVED_ENTRIES: Message[] = [
    entry("partner", "First partner block.", "9007199254740993"),
    entry("turn", "My reply.", "7250000000000000201"),
    entry("decision", "((plan))", "7250000000000000199"),
  ];
  const SERVED_ZONE: Message[] = [
    zoneRow("user", "Zone one.", "7250000000000000305"),
    zoneRow("assistant", "Zone two.", "7250000000000000302"),
  ];

  it("is loading while both requests are pending, then ready — DoD-2", async () => {
    const entriesAnswer = deferred<Response>();
    const zoneAnswer = deferred<Response>();
    stubBackend((request) => {
      if (request.method === "GET" && request.path === ENTRIES_PATH) return entriesAnswer.promise;
      if (request.method === "GET" && request.path === ZONE_PATH) return zoneAnswer.promise;
      return unexpected(request);
    });
    const state = new StreamState(SESSION_ID);

    const running = loadStream(state);
    await flush();
    expect(state.status).toBe("loading");

    entriesAnswer.resolve(jsonResponse({ entries: SERVED_ENTRIES }, 200));
    zoneAnswer.resolve(jsonResponse({ messages: SERVED_ZONE }, 200));
    await expect(running).resolves.toBeUndefined();
    expect(state.status).toBe("ready");
  });

  it("requests exactly GET /api/sessions/s1/entries and GET /api/sessions/s1/zone — DoD-2", async () => {
    const { calls } = serveLists(SERVED_ENTRIES, SERVED_ZONE);

    await expect(loadStream(new StreamState(SESSION_ID))).resolves.toBeUndefined();

    expect([...calls].sort(byPath)).toEqual([
      { method: "GET", path: ENTRIES_PATH, search: "" },
      { method: "GET", path: ZONE_PATH, search: "" },
    ]);
  });

  it("writes both lists exactly as served, in served order, ids the identical strings — DoD-2", async () => {
    serveLists(SERVED_ENTRIES, SERVED_ZONE);
    const state = new StreamState(SESSION_ID);

    await loadStream(state);

    expect(state.status).toBe("ready");
    expect(toJS(state.entries)).toEqual(SERVED_ENTRIES);
    expect(toJS(state.zone)).toEqual(SERVED_ZONE);
    expect(state.entries.map((m) => m.id)).toEqual([
      "9007199254740993",
      "7250000000000000201",
      "7250000000000000199",
    ]);
    expect(state.zone.map((m) => m.id)).toEqual(["7250000000000000305", "7250000000000000302"]);
  });
});

// ---------------------------------------------------------------------------
describe("loadStream's failures", () => {
  const HELD_ENTRIES: Message[] = [entry("partner", "Held partner.")];
  const HELD_ZONE: Message[] = [zoneRow("user", "Held zone row.")];
  const NEW_ENTRIES: Message[] = [entry("partner", "New partner."), entry("turn", "New turn.")];
  const NEW_ZONE: Message[] = [zoneRow("assistant", "New zone row.")];

  type Failure = [label: string, failEntries: boolean, failZone: boolean, answer: () => Response];
  const transport = (): Response => {
    throw new TypeError("Failed to fetch");
  };
  const FAILURES: Failure[] = [
    ["a 500 envelope on entries", true, false, () => envelope("internal_error", 500)],
    ["a 500 envelope on zone", false, true, () => envelope("internal_error", 500)],
    ["a transport failure on entries", true, false, transport],
    ["a transport failure on zone", false, true, transport],
    ["a 500 envelope on both", true, true, () => envelope("internal_error", 500)],
  ];

  it.each(FAILURES)(
    "%s is failed, keeps the previous lists, and does not reject — DoD-3",
    async (_label, failEntries, failZone, answer) => {
      stubBackend((request) => {
        if (request.method === "GET" && request.path === ENTRIES_PATH) {
          return failEntries ? answer() : jsonResponse({ entries: NEW_ENTRIES }, 200);
        }
        if (request.method === "GET" && request.path === ZONE_PATH) {
          return failZone ? answer() : jsonResponse({ messages: NEW_ZONE }, 200);
        }
        return unexpected(request);
      });
      const state = seeded({ entries: HELD_ENTRIES, zone: HELD_ZONE });

      await expect(loadStream(state)).resolves.toBeUndefined();

      expect(state.status).toBe("failed");
      expect(toJS(state.entries)).toEqual(HELD_ENTRIES);
      expect(toJS(state.zone)).toEqual(HELD_ZONE);
    },
  );
});

// ---------------------------------------------------------------------------
describe("loadStream and its signal", () => {
  it("writes nothing once its signal aborts before the responses settle (fetch rejects) — DoD-3", async () => {
    stubFetch(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          const signal = init?.signal;
          signal?.addEventListener("abort", () => {
            reject(signal.reason ?? new DOMException("The operation was aborted.", "AbortError"));
          });
        }),
    );
    const state = seeded({ entries: [entry("turn", "Held.")], zone: [zoneRow("user", "Held z.")] });
    const controller = new AbortController();

    const running = loadStream(state, controller.signal);
    await flush();
    const atAbort = snapshot(state);
    controller.abort();

    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(snapshot(state)).toEqual(atAbort);
  });

  it("writes nothing when the responses arrive after its signal aborted — DoD-3", async () => {
    const entriesAnswer = deferred<Response>();
    const zoneAnswer = deferred<Response>();
    stubBackend((request) => {
      if (request.method === "GET" && request.path === ENTRIES_PATH) return entriesAnswer.promise;
      if (request.method === "GET" && request.path === ZONE_PATH) return zoneAnswer.promise;
      return unexpected(request);
    });
    const state = seeded({ entries: [entry("turn", "Held.")], zone: [] });
    const controller = new AbortController();

    const running = loadStream(state, controller.signal);
    await flush();
    const atAbort = snapshot(state);
    controller.abort();
    entriesAnswer.resolve(jsonResponse({ entries: [entry("partner", "Late.")] }, 200));
    zoneAnswer.resolve(jsonResponse({ messages: [zoneRow("user", "Late z.")] }, 200));

    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(snapshot(state)).toEqual(atAbort);
  });

  it("writes nothing when its signal is already aborted — DoD-3", async () => {
    serveLists([entry("partner", "Never.")], [zoneRow("user", "Never z.")]);
    const state = new StreamState(SESSION_ID);
    const before = snapshot(state);
    const controller = new AbortController();
    controller.abort();

    await expect(loadStream(state, controller.signal)).resolves.toBeUndefined();
    await flush();
    expect(snapshot(state)).toEqual(before);
  });
});

// ---------------------------------------------------------------------------
describe("defaultKind", () => {
  it("is partner when the last partner-or-turn entry is a turn — DoD-4", () => {
    expect(defaultKind([entry("partner"), entry("turn")])).toBe("partner");
  });

  it("is turn when the last partner-or-turn entry is a partner — DoD-4", () => {
    expect(defaultKind([entry("turn"), entry("partner")])).toBe("turn");
  });

  it("skips decisions: [partner, turn, decision, decision] is partner — DoD-4", () => {
    expect(
      defaultKind([entry("partner"), entry("turn"), entry("decision"), entry("decision")]),
    ).toBe("partner");
  });

  it("skips decisions: [turn, partner, decision] is turn — DoD-4", () => {
    expect(defaultKind([entry("turn"), entry("partner"), entry("decision")])).toBe("turn");
  });

  it("is turn for an empty record — DoD-4", () => {
    expect(defaultKind([])).toBe("turn");
  });

  it("is turn for a record holding only a decision — DoD-4", () => {
    expect(defaultKind([entry("decision")])).toBe("turn");
  });
});

// ---------------------------------------------------------------------------
describe("effectiveKind and the override", () => {
  it("follows the default with no override — DoD-5", () => {
    expect(effectiveKind(seeded({ entries: [entry("turn")] }))).toBe("partner");
    expect(effectiveKind(seeded({ entries: [entry("partner")] }))).toBe("turn");
    expect(effectiveKind(seeded({ entries: [] }))).toBe("turn");
  });

  it("returns the override once chooseKind sets one — DoD-5", () => {
    const state = seeded({ entries: [entry("turn")] });
    chooseKind(state, "turn");
    expect(state.kindOverride).toBe("turn");
    expect(effectiveKind(state)).toBe("turn");

    const other = seeded({ entries: [entry("partner")] });
    chooseKind(other, "partner");
    expect(effectiveKind(other)).toBe("partner");
  });

  it("applyEntries with the same id sequence keeps the override and writes the list — DoD-5", () => {
    const a = entry("partner", "A");
    const b = entry("turn", "B");
    const state = seeded({ entries: [a, b] });
    chooseKind(state, "turn");

    const reread = [{ ...a }, { ...b, text: "B edited" }];
    applyEntries(state, reread);

    expect(state.kindOverride).toBe("turn");
    expect(toJS(state.entries)).toEqual(reread);
  });

  it("applyEntries with an entry added clears the override — DoD-5", () => {
    const a = entry("partner", "A");
    const state = seeded({ entries: [a] });
    chooseKind(state, "partner");

    const added = [a, entry("turn", "B")];
    applyEntries(state, added);

    expect(state.kindOverride).toBeNull();
    expect(toJS(state.entries)).toEqual(added);
  });

  it("applyEntries with an entry removed clears the override — DoD-5", () => {
    const a = entry("partner", "A");
    const b = entry("turn", "B");
    const state = seeded({ entries: [a, b] });
    chooseKind(state, "turn");

    applyEntries(state, [a]);

    expect(state.kindOverride).toBeNull();
    expect(toJS(state.entries)).toEqual([a]);
  });

  it("applyEntries with the same length but a different id clears the override — DoD-5", () => {
    const a = entry("partner", "A");
    const b = entry("turn", "B");
    const state = seeded({ entries: [a, b] });
    chooseKind(state, "turn");

    applyEntries(state, [a, entry("turn", "C")]);

    expect(state.kindOverride).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("canSettle", () => {
  it("my turn, one user zone row, blank draft → true — DoD-6", () => {
    const state = seeded({ entries: [], zone: [zoneRow("user", "Mine.")], draft: "" });
    expect(effectiveKind(state)).toBe("turn");
    expect(canSettle(state)).toBe(true);
  });

  it("my turn, empty zone, non-blank draft → true — DoD-6", () => {
    expect(canSettle(seeded({ entries: [], zone: [], draft: "She walks." }))).toBe(true);
  });

  it("my turn, empty zone, blank draft → false — DoD-6", () => {
    expect(canSettle(seeded({ entries: [], zone: [], draft: "  \n" }))).toBe(false);
  });

  it("partner position with zone rows and a draft → false — DoD-6", () => {
    const state = seeded({
      entries: [],
      zone: [zoneRow("user", "Mine."), zoneRow("assistant", "Theirs.")],
      draft: "More text.",
    });
    chooseKind(state, "partner");
    expect(canSettle(state)).toBe(false);
  });

  it("partner by default (last entry a turn) with zone rows and a draft → false — DoD-6", () => {
    const state = seeded({ entries: [entry("turn")], zone: [zoneRow("user")], draft: "x" });
    expect(canSettle(state)).toBe(false);
  });

  it("while busy → false — DoD-6", () => {
    expect(
      canSettle(seeded({ entries: [], zone: [zoneRow("user")], draft: "x", busy: true })),
    ).toBe(false);
  });

  it("my turn with a zone holding only an assistant row → true — DoD-6", () => {
    expect(canSettle(seeded({ entries: [], zone: [zoneRow("assistant", "Ai.")], draft: "" }))).toBe(
      true,
    );
  });
});

// ---------------------------------------------------------------------------
describe("canSend", () => {
  it("is true for a non-blank draft on my turn — DoD-7", () => {
    const state = seeded({ entries: [], draft: "Hello." });
    chooseKind(state, "turn");
    expect(canSend(state)).toBe(true);
  });

  it("is true for a non-blank draft on partner — DoD-7", () => {
    const state = seeded({ entries: [], draft: "Hello." });
    chooseKind(state, "partner");
    expect(canSend(state)).toBe(true);
  });

  it.each([[""], ["   "], ["  \n\t"]])("is false for the blank draft %j — DoD-7", (draft) => {
    expect(canSend(seeded({ entries: [], draft }))).toBe(false);
    const partner = seeded({ entries: [], draft });
    chooseKind(partner, "partner");
    expect(canSend(partner)).toBe(false);
  });

  it("is false while busy — DoD-7", () => {
    expect(canSend(seeded({ entries: [], draft: "Hello.", busy: true }))).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("showsDiscard", () => {
  it("empty zone and an empty draft → true — DoD-8", () => {
    expect(showsDiscard(seeded({ zone: [], draft: "" }))).toBe(true);
  });

  it("empty zone and a whitespace-only draft → true — DoD-8", () => {
    expect(showsDiscard(seeded({ zone: [], draft: "  \n\t " }))).toBe(true);
  });

  it("empty zone and the draft \"x\" → false — DoD-8", () => {
    expect(showsDiscard(seeded({ zone: [], draft: "x" }))).toBe(false);
  });

  it("one zone row and an empty draft → false — DoD-8", () => {
    expect(showsDiscard(seeded({ zone: [zoneRow("user")], draft: "" }))).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("discardZone", () => {
  it("clears the override and the whitespace-only draft, keeps the lists, makes no request — DoD-9", () => {
    const fetchMock = stubFetch(() => Promise.reject(new TypeError("no request expected")));
    const entries = [entry("partner", "P."), entry("turn", "T.")];
    const state = seeded({ entries, zone: [], draft: "  \n " });
    chooseKind(state, "turn");

    discardZone(state);

    expect(state.draft).toBe("");
    expect(state.kindOverride).toBeNull();
    expect(toJS(state.entries)).toEqual(entries);
    expect(toJS(state.zone)).toEqual([]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns the position to the computed default — DoD-9", () => {
    stubFetch(() => Promise.reject(new TypeError("no request expected")));
    const state = seeded({ entries: [entry("turn")], zone: [], draft: " " });
    chooseKind(state, "turn");
    expect(effectiveKind(state)).toBe("turn");

    discardZone(state);

    expect(effectiveKind(state)).toBe("partner");
  });
});

// ---------------------------------------------------------------------------
describe("showsReopen", () => {
  it("empty zone, last entry a turn → true — DoD-10", () => {
    expect(showsReopen(seeded({ entries: [entry("partner"), entry("turn")], zone: [] }))).toBe(true);
  });

  it("empty zone, last entry a decision → true — DoD-10", () => {
    expect(showsReopen(seeded({ entries: [entry("partner"), entry("decision")], zone: [] }))).toBe(
      true,
    );
  });

  it("last entry a partner, even with an earlier turn → false — DoD-10", () => {
    expect(showsReopen(seeded({ entries: [entry("turn"), entry("partner")], zone: [] }))).toBe(false);
  });

  it("one zone row → false — DoD-10", () => {
    expect(showsReopen(seeded({ entries: [entry("turn")], zone: [zoneRow("user")] }))).toBe(false);
  });

  it("no entries → false — DoD-10", () => {
    expect(showsReopen(seeded({ entries: [], zone: [] }))).toBe(false);
  });

  it("a non-blank draft with an empty zone does not change the answer — DoD-10", () => {
    expect(showsReopen(seeded({ entries: [entry("turn")], zone: [], draft: "Typed." }))).toBe(true);
    expect(showsReopen(seeded({ entries: [entry("partner")], zone: [], draft: "Typed." }))).toBe(
      false,
    );
    expect(showsReopen(seeded({ entries: [], zone: [], draft: "Typed." }))).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("settleTargetText", () => {
  it("a non-blank draft is the target — DoD-11", () => {
    expect(
      settleTargetText(seeded({ zone: [zoneRow("assistant", "Zone.")], draft: "My draft." })),
    ).toBe("My draft.");
  });

  it("a blank draft with zone rows targets the last zone row (an assistant's) — DoD-11", () => {
    const zone = [zoneRow("user", "First, mine."), zoneRow("assistant", "Last, assistant's.")];
    expect(settleTargetText(seeded({ zone, draft: "  " }))).toBe("Last, assistant's.");
  });

  it("a blank draft with zone rows targets the last zone row (the user's) — DoD-11", () => {
    const zone = [zoneRow("assistant", "First, assistant's."), zoneRow("user", "Last, mine.")];
    expect(settleTargetText(seeded({ zone, draft: "" }))).toBe("Last, mine.");
  });

  it("a blank draft and an empty zone → null — DoD-11", () => {
    expect(settleTargetText(seeded({ zone: [], draft: " \n" }))).toBeNull();
  });
});

describe("settlePreviewOf", () => {
  it("my turn with target \"((x))\" → decision, no strip — DoD-11", () => {
    const state = seeded({ entries: [], zone: [], draft: "((x))" });
    expect(settlePreviewOf(state)).toEqual({ kind: "decision", strips: false });
  });

  it("my turn with target \"She walks. ((x)) On.\" → turn, strips — DoD-11", () => {
    const state = seeded({ entries: [], zone: [zoneRow("assistant", "She walks. ((x)) On.")], draft: "" });
    expect(settlePreviewOf(state)).toEqual({ kind: "turn", strips: true });
  });

  it("on partner → null — DoD-11", () => {
    const state = seeded({ entries: [], zone: [zoneRow("user", "She walks.")], draft: "((x))" });
    chooseKind(state, "partner");
    expect(settlePreviewOf(state)).toBeNull();
  });

  it("with no target → null — DoD-11", () => {
    expect(settlePreviewOf(seeded({ entries: [], zone: [], draft: "   " }))).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("reactivity", () => {
  it("an autorun reading effectiveKind re-runs after chooseKind — DoD-12", () => {
    const state = seeded({ entries: [entry("turn")] });
    const seen: string[] = [];
    const dispose = autorun(() => {
      seen.push(effectiveKind(state));
    });
    try {
      chooseKind(state, "turn");
    } finally {
      dispose();
    }
    expect(seen).toEqual(["partner", "turn"]);
  });

  it("an autorun reading canSettle re-runs after setDraft — DoD-12", () => {
    const state = seeded({ entries: [], zone: [], draft: "" });
    const seen: boolean[] = [];
    const dispose = autorun(() => {
      seen.push(canSettle(state));
    });
    try {
      setDraft(state, "Now there is text.");
    } finally {
      dispose();
    }
    expect(state.draft).toBe("Now there is text.");
    expect(seen).toEqual([false, true]);
  });

  it("an autorun reading status re-runs after loadStream settles — DoD-12", async () => {
    serveLists([entry("partner", "P.")], []);
    const state = new StreamState(SESSION_ID);
    const seen: string[] = [];
    const dispose = autorun(() => {
      seen.push(state.status);
    });
    try {
      await loadStream(state);
    } finally {
      dispose();
    }
    expect(seen[0]).toBe("idle");
    expect(seen[seen.length - 1]).toBe("ready");
    expect(seen.length).toBeGreaterThanOrEqual(2);
  });
});
