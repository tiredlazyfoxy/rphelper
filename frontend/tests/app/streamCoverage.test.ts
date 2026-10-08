// Feature 024, step 007 — the search-coverage flag on `StreamState` (DoD-1..DoD-5).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done plus
// context.md's D10 (`search_coverage_incomplete` is optional on the wire and **absent reads as
// false**) and D11 (the flag is set by the latest record-keeping response — settle, re-open, and
// an edit or partner filing whose returned row has a non-null `settled_at`; a zone row and a
// failed request leave it unchanged; it starts false on mount):
//   - a settle carrying true sets it, a following settle carrying false clears it (DoD-1);
//   - a re-open carrying true sets it, one with the field absent makes it false (DoD-2);
//   - an edit answered with a settled row carrying true sets it; an edit answered with a row
//     whose `settled_at` is null and no flag leaves a previously true flag true (DoD-3);
//   - a pasted partner filing answered with a settled row carrying true sets it; one answered
//     with a zone row (`settled_at` null) does not change it (DoD-4);
//   - a failed settle (409 `zone_empty`) leaves the flag as it is, in both directions (DoD-5).
//
// Stubs key on the exact method + pathname (context.md "Test conventions"); the paths are the
// ones the plan pins: POST …/settle, POST …/reopen, POST …/entries, PATCH /api/messages/<id>.
import { runInAction } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Message, MessageKind, MessageRole } from "../../src/app/streamApi";
import {
  StreamState,
  editEntry,
  filePastedPartner,
  reopenLast,
  settleComposer,
} from "../../src/app/streamState";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; body: unknown };
type Route = (request: Seen) => Response | Promise<Response>;

// ---------------------------------------------------------------- the pinned paths
const SESSION_ID = "7250000000000000311";
const ENTRIES_PATH = `/api/sessions/${SESSION_ID}/entries`;
const ZONE_PATH = `/api/sessions/${SESSION_ID}/zone`;
const SETTLE_PATH = `/api/sessions/${SESSION_ID}/settle`;
const REOPEN_PATH = `/api/sessions/${SESSION_ID}/reopen`;

const GET_ENTRIES = `GET ${ENTRIES_PATH}`;
const GET_ZONE = `GET ${ZONE_PATH}`;
const POST_ENTRIES = `POST ${ENTRIES_PATH}`;
const POST_SETTLE = `POST ${SETTLE_PATH}`;
const POST_REOPEN = `POST ${REOPEN_PATH}`;
const patchMessage = (id: string): string => `PATCH /api/messages/${id}`;

// ---------------------------------------------------------------- fixtures
const STAMP = "2026-05-10T09:00:00.000000+00:00";
const LATER = "2026-05-10T09:05:00.000000+00:00";

let nextId = 600;
function freshId(): string {
  nextId += 1;
  return `7250000000000000${String(nextId).padStart(3, "0")}`;
}

/**
 * A settled record row with every key the `Message` type has today, and
 * `search_coverage_incomplete` present only when `flag` is given (D10's absent case).
 */
function settledRow(kind: MessageKind, text: string, flag?: boolean, id = freshId()): Message {
  const row: Message = {
    id,
    session_id: SESSION_ID,
    role: kind === "partner" ? "user" : "assistant",
    kind,
    text,
    settled_at: STAMP,
    created_at: STAMP,
    updated_at: STAMP,
    tool_name: null,
    tool_status: null,
    tool_args: null,
  };
  return flag === undefined ? row : { ...row, search_coverage_incomplete: flag };
}

/** A zone row: `kind` and `settled_at` null. Every other key present. */
function zoneRow(role: MessageRole, text: string, flag?: boolean, id = freshId()): Message {
  const row: Message = {
    id,
    session_id: SESSION_ID,
    role,
    kind: null,
    text,
    settled_at: null,
    created_at: STAMP,
    updated_at: STAMP,
    tool_name: null,
    tool_status: null,
    tool_args: null,
  };
  return flag === undefined ? row : { ...row, search_coverage_incomplete: flag };
}

/** A `SettleResult` body; the flag key is present only when `flag` is given. */
function settleBody(flag?: boolean): Record<string, unknown> {
  const body: Record<string, unknown> = {
    entry_id: freshId(),
    kind: "turn",
    buried_ids: [],
  };
  if (flag !== undefined) body.search_coverage_incomplete = flag;
  return body;
}

/** A `ReopenResult` body; the flag key is present only when `flag` is given. */
function reopenBody(flag?: boolean): Record<string, unknown> {
  const body: Record<string, unknown> = {
    reopened_id: freshId(),
    restored_ids: [],
  };
  if (flag !== undefined) body.search_coverage_incomplete = flag;
  return body;
}

type Seed = {
  entries?: Message[];
  zone?: Message[];
  draft?: string;
};

function seeded(seed: Seed): StreamState {
  const state = new StreamState(SESSION_ID);
  runInAction(() => {
    if (seed.entries !== undefined) state.entries = seed.entries;
    if (seed.zone !== undefined) state.zone = seed.zone;
    if (seed.draft !== undefined) state.draft = seed.draft;
  });
  return state;
}

beforeEach(() => {
  notifyFailureSpy.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- fetch harness
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

function requestBody(init?: RequestInit): unknown {
  const raw = init?.body;
  if (typeof raw !== "string") return undefined;
  return JSON.parse(raw) as unknown;
}

const keyOf = (request: Seen): string => `${request.method} ${request.path}`;

/** A backend keyed on exact "METHOD pathname"; unrouted requests answer a 418 envelope. */
function serve(routes: Record<string, Route>) {
  const calls: Seen[] = [];
  const impl: FetchFn = async (input, init) => {
    const request: Seen = {
      method: requestMethod(input, init),
      path: requestUrl(input).pathname,
      body: requestBody(init),
    };
    calls.push(request);
    const route = routes[keyOf(request)];
    if (route === undefined) return envelope(`unexpected_${request.method}_${request.path}`, 418);
    return route(request);
  };
  vi.stubGlobal("fetch", vi.fn<FetchFn>(impl));
  const keys = (): string[] => calls.map(keyOf);
  return { calls, keys };
}

const entriesList = (list: Message[]): Route => () => jsonResponse({ entries: list }, 200);
const zoneList = (list: Message[]): Route => () => jsonResponse({ messages: list }, 200);

/** The two list re-reads every record-keeping effect may perform, answered harmlessly. */
function readRoutes(entries: Message[] = [], zone: Message[] = []): Record<string, Route> {
  return { [GET_ENTRIES]: entriesList(entries), [GET_ZONE]: zoneList(zone) };
}

// ===========================================================================
// DoD-1 — settle
// ===========================================================================
describe("settleComposer and the coverage flag (US-112.AC-2, D11)", () => {
  it("a settle answered with search_coverage_incomplete true sets the flag, and a following successful settle answered with false clears it — DoD-1", async () => {
    let settleAnswer = (): Response => jsonResponse(settleBody(true), 200);
    const backend = serve({
      [POST_SETTLE]: () => settleAnswer(),
      ...readRoutes([settledRow("turn", "Settled once.")], []),
    });
    const state = seeded({ zone: [zoneRow("user", "A zone row.")], draft: "" });
    expect(state.searchCoverageIncomplete).toBe(false);

    await settleComposer(state);

    expect(state.searchCoverageIncomplete).toBe(true);

    settleAnswer = (): Response => jsonResponse(settleBody(false), 200);
    runInAction(() => {
      state.zone = [zoneRow("user", "Another zone row.")];
    });

    await settleComposer(state);

    expect(state.searchCoverageIncomplete).toBe(false);
    expect(backend.keys().filter((key) => key === POST_SETTLE)).toHaveLength(2);
  });
});

// ===========================================================================
// DoD-2 — re-open, and D10's absent field
// ===========================================================================
describe("reopenLast and the coverage flag (D10, D11)", () => {
  it("a re-open answered with search_coverage_incomplete true sets the flag — DoD-2", async () => {
    serve({
      [POST_REOPEN]: () => jsonResponse(reopenBody(true), 200),
      ...readRoutes([settledRow("partner", "Partner block.")], []),
    });
    const state = seeded({ entries: [settledRow("turn", "My last turn.")] });
    expect(state.searchCoverageIncomplete).toBe(false);

    await reopenLast(state);

    expect(state.searchCoverageIncomplete).toBe(true);
  });

  it("a re-open whose response omits the field reads as false and clears a previously true flag — DoD-2", async () => {
    let reopenAnswer = (): Response => jsonResponse(reopenBody(true), 200);
    serve({
      [POST_REOPEN]: () => reopenAnswer(),
      ...readRoutes([settledRow("partner", "Partner block.")], []),
    });
    const state = seeded({ entries: [settledRow("turn", "My last turn.")] });

    await reopenLast(state);
    expect(state.searchCoverageIncomplete).toBe(true);

    reopenAnswer = (): Response => jsonResponse(reopenBody(undefined), 200);

    await reopenLast(state);

    expect(state.searchCoverageIncomplete).toBe(false);
  });
});

// ===========================================================================
// DoD-3 — editEntry discriminates on the returned row's settled_at
// ===========================================================================
describe("editEntry and the coverage flag (D11)", () => {
  it("an edit answered with a settled row carrying search_coverage_incomplete true sets the flag — DoD-3", async () => {
    const target = settledRow("turn", "My original answer.");
    const served = settledRow("turn", "My revised answer.", true, target.id);
    serve({
      [patchMessage(target.id)]: () => jsonResponse({ ...served, updated_at: LATER }, 200),
      ...readRoutes([target], []),
    });
    const state = seeded({ entries: [target] });
    expect(state.searchCoverageIncomplete).toBe(false);

    await editEntry(state, target.id, "My revised answer.");

    expect(state.searchCoverageIncomplete).toBe(true);
  });

  it("an edit answered with a row whose settled_at is null and no flag leaves a previously true flag true — DoD-3", async () => {
    const target = settledRow("turn", "Reopened behind my back.");
    const servedZone = zoneRow("assistant", "Reopened text.", undefined, target.id);
    serve({
      [POST_SETTLE]: () => jsonResponse(settleBody(true), 200),
      [patchMessage(target.id)]: () => jsonResponse({ ...servedZone, updated_at: LATER }, 200),
      ...readRoutes([target], [servedZone]),
    });
    const state = seeded({ entries: [target], zone: [zoneRow("user", "A zone row.")], draft: "" });

    // Make the flag true through a settle, so the edit below has something to preserve.
    await settleComposer(state);
    expect(state.searchCoverageIncomplete).toBe(true);
    runInAction(() => {
      state.entries = [target];
    });

    await editEntry(state, target.id, "A corrected text.");

    expect(state.searchCoverageIncomplete).toBe(true);
  });
});

// ===========================================================================
// DoD-4 — partner filing discriminates the same way
// ===========================================================================
describe("filePastedPartner and the coverage flag (D11)", () => {
  it("filing a pasted partner block answered with a settled row carrying true sets the flag — DoD-4", async () => {
    const filed = settledRow("partner", "A pasted partner block.", true);
    serve({
      [POST_ENTRIES]: () => jsonResponse(filed, 201),
      ...readRoutes([filed], []),
    });
    const state = seeded({ entries: [] });
    expect(state.searchCoverageIncomplete).toBe(false);

    await filePastedPartner(state, "A pasted partner block.");

    expect(state.searchCoverageIncomplete).toBe(true);
  });

  it("a filing answered with a zone row (settled_at null) does not change the flag: a previously true flag stays true — DoD-4", async () => {
    const settledFiling = settledRow("partner", "First pasted block.", true);
    const zoneAnswer = zoneRow("user", "Second block, landed in the zone.");
    let filingAnswer = (): Response => jsonResponse(settledFiling, 201);
    serve({
      [POST_ENTRIES]: () => filingAnswer(),
      ...readRoutes([settledFiling], [zoneAnswer]),
    });
    const state = seeded({ entries: [] });

    await filePastedPartner(state, "First pasted block.");
    expect(state.searchCoverageIncomplete).toBe(true);

    filingAnswer = (): Response => jsonResponse(zoneAnswer, 201);

    await filePastedPartner(state, "Second block, landed in the zone.");

    expect(state.searchCoverageIncomplete).toBe(true);
  });
});

// ===========================================================================
// DoD-5 — a failed settle writes no flag
// ===========================================================================
describe("a failed record-keeping request leaves the coverage flag alone (D11)", () => {
  it("a settle refused with 409 zone_empty leaves the flag unchanged, both while false and while true — DoD-5", async () => {
    let settleAnswer = (): Response => envelope("zone_empty", 409);
    serve({
      [POST_SETTLE]: () => settleAnswer(),
      ...readRoutes([settledRow("turn", "Already there.")], [zoneRow("user", "A zone row.")]),
    });
    const state = seeded({ zone: [zoneRow("user", "A zone row.")], draft: "" });
    expect(state.searchCoverageIncomplete).toBe(false);

    await settleComposer(state);

    expect(state.searchCoverageIncomplete).toBe(false);

    // Now make it true with a successful settle, then fail again: still true.
    settleAnswer = (): Response => jsonResponse(settleBody(true), 200);
    await settleComposer(state);
    expect(state.searchCoverageIncomplete).toBe(true);

    settleAnswer = (): Response => envelope("zone_empty", 409);

    await settleComposer(state);

    expect(state.searchCoverageIncomplete).toBe(true);
  });
});
