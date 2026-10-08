// Feature 013, step 003 — the stream's mutation effects (DoD-1..DoD-15).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done plus
// context.md's D2, D4, D6, D7, D8, D10, D15 and 003.context.md ("Which re-read follows which
// mutation", "Abort posture"):
//   - send on *my turn* appends to the zone then re-reads the zone; on *partner* files a
//     partner entry then re-reads the entries; the draft clears only on success;
//   - a pasted partner block files itself then re-reads the entries; the draft is untouched;
//   - settle appends unsent composer text first (stopping on append failure with a zone
//     re-read), then settles, then re-reads both lists whatever the settle outcome;
//   - re-open requests re-open then re-reads both lists;
//   - a zone edit PATCHes and replaces that one row with the response; blank / unchanged text
//     makes no request; a failure notifies, re-reads the zone and resolves false;
//   - every failure goes through notifyFailure with the thrown error; no success path calls it;
//   - nothing is written once the signal is aborted, and no effect rejects.
//
// Amended by feature 021, step 007 (DoD-7, D12): Send on *my turn* now composes through 019's
// `composeMessage` — POST …/zone/compose {"text"} streamed, then a zone re-read; it never sets
// `busy` and never posts …/zone/messages. The 013 *my turn* `sendComposer` cases (DoD-1, DoD-3's
// failed append, DoD-4's busy case, and the my-turn rows of DoD-14 / DoD-15) are rewritten to
// that path; DoD-4's busy-while-pending case moves to the *partner* branch, which keeps `busy`.
// Partner, paste, settle, re-open and edit cases are unchanged (settle still appends via
// …/zone/messages).
import { runInAction, toJS } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Message, MessageKind, MessageRole } from "../../src/app/streamApi";
import {
  StreamState,
  editZoneMessage,
  effectiveKind,
  filePastedPartner,
  reopenLast,
  sendComposer,
  settleComposer,
} from "../../src/app/streamState";
import { ApiError } from "../../src/shared/apiError";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; body: unknown };
type Route = (request: Seen) => Response | Promise<Response>;

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "s1";
const ENTRIES_PATH = `/api/sessions/${SESSION_ID}/entries`;
const ZONE_PATH = `/api/sessions/${SESSION_ID}/zone`;
const ZONE_MESSAGES_PATH = `/api/sessions/${SESSION_ID}/zone/messages`;
const COMPOSE_PATH = `/api/sessions/${SESSION_ID}/zone/compose`;
const SETTLE_PATH = `/api/sessions/${SESSION_ID}/settle`;
const REOPEN_PATH = `/api/sessions/${SESSION_ID}/reopen`;
const messagePath = (id: string): string => `/api/messages/${id}`;

const GET_ENTRIES = `GET ${ENTRIES_PATH}`;
const GET_ZONE = `GET ${ZONE_PATH}`;
const POST_ENTRIES = `POST ${ENTRIES_PATH}`;
const POST_ZONE_MESSAGES = `POST ${ZONE_MESSAGES_PATH}`;
const POST_COMPOSE = `POST ${COMPOSE_PATH}`;
const POST_SETTLE = `POST ${SETTLE_PATH}`;
const POST_REOPEN = `POST ${REOPEN_PATH}`;
const patchMessage = (id: string): string => `PATCH ${messagePath(id)}`;

const STAMP = "2026-05-10T09:00:00.000000+00:00";
const LATER = "2026-05-10T09:05:00.000000+00:00";

let nextId = 400;
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
};

function seeded(seed: Seed): StreamState {
  const state = new StreamState(SESSION_ID);
  runInAction(() => {
    if (seed.entries !== undefined) state.entries = seed.entries;
    if (seed.zone !== undefined) state.zone = seed.zone;
    if (seed.draft !== undefined) state.draft = seed.draft;
    if (seed.kindOverride !== undefined) state.kindOverride = seed.kindOverride;
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

function requestBody(init?: RequestInit): unknown {
  const raw = init?.body;
  if (typeof raw !== "string") return undefined;
  return JSON.parse(raw) as unknown;
}

function stubFetch(impl: FetchFn) {
  const mock = vi.fn<FetchFn>(impl);
  vi.stubGlobal("fetch", mock);
  return mock;
}

const keyOf = (request: Seen): string => `${request.method} ${request.path}`;

/**
 * A backend keyed on exact "METHOD pathname"; every request is recorded in order.
 * Anything not routed answers an unexpected 418 envelope.
 */
function serve(routes: Record<string, Route>) {
  const calls: Seen[] = [];
  const mock = stubFetch(async (input, init) => {
    const url = requestUrl(input);
    const request: Seen = {
      method: requestMethod(input, init),
      path: url.pathname,
      body: requestBody(init),
    };
    calls.push(request);
    const route = routes[keyOf(request)];
    if (route === undefined) return envelope(`unexpected_${request.method}_${request.path}`, 418);
    return route(request);
  });
  const keys = (): string[] => calls.map(keyOf);
  const bodyOf = (key: string): unknown => calls.find((c) => keyOf(c) === key)?.body;
  return { mock, calls, keys, bodyOf };
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

const entriesList = (list: Message[]): Route => () => jsonResponse({ entries: list }, 200);
const zoneList = (list: Message[]): Route => () => jsonResponse({ messages: list }, 200);
const created = (message: Message): Route => () => jsonResponse(message, 201);
const ok = (body: unknown): Route => () => jsonResponse(body, 200);
const fails = (code: string, status: number): Route => () => envelope(code, status);

// 021 step 007: the compose route's streamed body (accepted, token, done), built fresh per call.
const enc = new TextEncoder();
function sseResponse(payloads: unknown[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const payload of payloads) controller.enqueue(enc.encode(`data: ${JSON.stringify(payload)}\n\n`));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}
const COMPOSE_ACCEPTED_ID = "7250000000000000970";
const COMPOSE_DONE_ID = "7250000000000000971";
const composedOk = (): Response =>
  sseResponse([
    { event: "accepted", message_id: COMPOSE_ACCEPTED_ID },
    { event: "token", text: "A reply." },
    { event: "done", message_id: COMPOSE_DONE_ID },
  ]);
const composes: Route = () => composedOk();

/** Rejects if `promise` has not settled within `ms`, so a stuck call fails instead of hanging. */
function within<T>(promise: Promise<T>, ms = 2000): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_resolve, reject) => {
    timer = setTimeout(() => reject(new Error(`timed out after ${ms}ms`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

function expectNotifiedOnceWith(code: string): void {
  expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
  const error = notifyFailureSpy.mock.calls[0]?.[0];
  expect(error).toBeInstanceOf(ApiError);
  expect((error as ApiError).code).toBe(code);
}

/** The first key, then the remaining keys as an unordered set. */
function expectFirstThenBothReads(keys: string[], first: string[]): void {
  expect(keys.slice(0, first.length)).toEqual(first);
  expect(keys.slice(first.length).sort()).toEqual([GET_ENTRIES, GET_ZONE].sort());
}

const SETTLE_RESULT = { entry_id: "7250000000000000990", kind: "turn", buried_ids: ["7250000000000000991"] };
const REOPEN_RESULT = { reopened_id: "7250000000000000980", restored_ids: ["7250000000000000981"] };

// ---------------------------------------------------------------------------
describe("sendComposer on my turn", () => {
  // 021 step 007 (DoD-7): was POST …/zone/messages; Send on my turn now composes.
  it("[021 step 007 DoD-7] POSTs exactly …/zone/compose with the draft verbatim, then GETs the zone; draft cleared, zone the re-read list — DoD-1", async () => {
    const held = zoneRow("assistant", "Earlier zone row.");
    const appended = zoneRow("user", "Hello ((calm))", COMPOSE_ACCEPTED_ID);
    const reread = [held, appended, zoneRow("assistant", "A reply.", COMPOSE_DONE_ID)];
    const backend = serve({
      [POST_COMPOSE]: composes,
      [GET_ZONE]: zoneList(reread),
    });
    const state = seeded({ zone: [held], draft: "Hello ((calm))", kindOverride: "turn" });

    await expect(within(sendComposer(state))).resolves.toBeUndefined();

    const keys = backend.keys();
    expect(keys[0]).toBe(POST_COMPOSE);
    expect(keys.slice(1).every((k) => k === GET_ZONE)).toBe(true);
    expect(keys.length).toBeGreaterThan(1);
    expect(backend.bodyOf(POST_COMPOSE)).toStrictEqual({ text: "Hello ((calm))" });
    expect(state.draft).toBe("");
    expect(toJS(state.zone)).toEqual(reread);
    expect(keys).not.toContain(POST_ZONE_MESSAGES);
    expect(keys).not.toContain(GET_ENTRIES);
    expect(keys).not.toContain(POST_ENTRIES);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

describe("sendComposer on partner", () => {
  it("POSTs …/entries with exactly {kind:partner, text}, then GETs the entries; draft cleared, entries the re-read list — DoD-2", async () => {
    const earlier = entry("turn", "My earlier turn.");
    const filed = entry("partner", "Partner says ((hi))");
    const reread = [earlier, filed];
    const backend = serve({
      [POST_ENTRIES]: created(filed),
      [GET_ENTRIES]: entriesList(reread),
    });
    const state = seeded({ entries: [earlier], draft: "Partner says ((hi))", kindOverride: "partner" });

    await expect(sendComposer(state)).resolves.toBeUndefined();

    expect(backend.keys()).toEqual([POST_ENTRIES, GET_ENTRIES]);
    expect(backend.bodyOf(POST_ENTRIES)).toStrictEqual({ kind: "partner", text: "Partner says ((hi))" });
    expect(state.draft).toBe("");
    expect(toJS(state.entries)).toEqual(reread);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

describe("sendComposer failures and blank drafts", () => {
  // 021 step 007 (DoD-7): was a 500 on POST …/zone/messages; the my-turn request is now the compose.
  it("[021 step 007 DoD-7] a 500 on the compose notifies once with that ApiError, keeps the draft, re-reads the zone, ends not busy — DoD-3", async () => {
    const held = zoneRow("user", "Held row.");
    const reread = [held, zoneRow("assistant", "Arrived meanwhile.")];
    const backend = serve({
      [POST_COMPOSE]: fails("internal_error", 500),
      [GET_ZONE]: zoneList(reread),
    });
    const state = seeded({ zone: [held], draft: "Do not lose me.", kindOverride: "turn" });

    await expect(within(sendComposer(state))).resolves.toBeUndefined();

    expectNotifiedOnceWith("internal_error");
    expect(state.draft).toBe("Do not lose me.");
    expect(backend.keys()).toEqual([POST_COMPOSE, GET_ZONE]);
    expect(toJS(state.zone)).toEqual(reread);
    expect(state.busy).toBe(false);
  });

  it("a 500 on the partner filing notifies once, keeps the draft, re-reads the entries, ends not busy — DoD-3", async () => {
    const reread = [entry("turn", "Re-read turn.")];
    const backend = serve({
      [POST_ENTRIES]: fails("internal_error", 500),
      [GET_ENTRIES]: entriesList(reread),
    });
    const state = seeded({ draft: "Partner words.", kindOverride: "partner" });

    await expect(sendComposer(state)).resolves.toBeUndefined();

    expectNotifiedOnceWith("internal_error");
    expect(state.draft).toBe("Partner words.");
    expect(backend.keys()).toEqual([POST_ENTRIES, GET_ENTRIES]);
    expect(toJS(state.entries)).toEqual(reread);
    expect(state.busy).toBe(false);
  });

  const BLANKS: [label: string, draft: string, position: "partner" | "turn"][] = [
    ["an empty draft on my turn", "", "turn"],
    ["a whitespace-only draft on my turn", "  \n\t ", "turn"],
    ["a whitespace-only draft on partner", "   ", "partner"],
  ];

  it.each(BLANKS)("%s makes no request at all — DoD-3", async (_label, draft, position) => {
    const backend = serve({});
    const state = seeded({ zone: [zoneRow("user", "Row.")], draft, kindOverride: position });

    await expect(sendComposer(state)).resolves.toBeUndefined();

    expect(backend.mock).not.toHaveBeenCalled();
    expect(state.draft).toBe(draft);
    expect(state.busy).toBe(false);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

describe("sendComposer and busy", () => {
  // 021 step 007 (DoD-7): the my-turn Send no longer sets busy (019 D13); the busy-while-pending
  // case now runs on the partner branch, which keeps 013's busy handling exactly.
  it("[021 step 007 DoD-7] on partner, is busy while the POST is pending and not busy after it settles — DoD-4", async () => {
    const answer = deferred<Response>();
    const filed = entry("partner", "Pending text.");
    serve({
      [POST_ENTRIES]: () => answer.promise,
      [GET_ENTRIES]: entriesList([filed]),
    });
    const state = seeded({ draft: "Pending text.", kindOverride: "partner" });
    expect(state.busy).toBe(false);

    const running = sendComposer(state);
    await flush();
    expect(state.busy).toBe(true);

    answer.resolve(jsonResponse(filed, 201));
    await expect(within(running)).resolves.toBeUndefined();
    expect(state.busy).toBe(false);
  });

  it("[021 step 007 DoD-7] on my turn, is never busy while the compose is pending or after it settles — DoD-4", async () => {
    const answer = deferred<Response>();
    serve({
      [POST_COMPOSE]: () => answer.promise,
      [GET_ZONE]: zoneList([zoneRow("user", "Pending text.", COMPOSE_ACCEPTED_ID)]),
    });
    const state = seeded({ draft: "Pending text.", kindOverride: "turn" });
    expect(state.busy).toBe(false);

    const running = sendComposer(state);
    await flush();
    expect(state.busy).toBe(false);

    answer.resolve(composedOk());
    await expect(within(running)).resolves.toBeUndefined();
    expect(state.busy).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("filePastedPartner", () => {
  it("POSTs …/entries with exactly {kind:partner, text}, then GETs the entries; the draft unchanged throughout — DoD-5", async () => {
    const answer = deferred<Response>();
    const filed = entry("partner", "Pasted block");
    const reread = [filed];
    const backend = serve({
      [POST_ENTRIES]: () => answer.promise,
      [GET_ENTRIES]: entriesList(reread),
    });
    const state = seeded({ draft: "Half-typed reply", kindOverride: "partner" });

    const running = filePastedPartner(state, "Pasted block");
    await flush();
    expect(state.draft).toBe("Half-typed reply");

    answer.resolve(jsonResponse(filed, 201));
    await expect(running).resolves.toBeUndefined();

    expect(backend.keys()).toEqual([POST_ENTRIES, GET_ENTRIES]);
    expect(backend.bodyOf(POST_ENTRIES)).toStrictEqual({ kind: "partner", text: "Pasted block" });
    expect(state.draft).toBe("Half-typed reply");
    expect(toJS(state.entries)).toEqual(reread);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("still files when the zone holds rows (no zone guard) — DoD-5", async () => {
    const filed = entry("partner", "Pasted block");
    const backend = serve({
      [POST_ENTRIES]: created(filed),
      [GET_ENTRIES]: entriesList([filed]),
    });
    const zone = [zoneRow("user", "Zone row one."), zoneRow("assistant", "Zone row two.")];
    const state = seeded({ zone, kindOverride: "partner" });

    await expect(filePastedPartner(state, "Pasted block")).resolves.toBeUndefined();

    expect(backend.keys()).toEqual([POST_ENTRIES, GET_ENTRIES]);
    expect(backend.bodyOf(POST_ENTRIES)).toStrictEqual({ kind: "partner", text: "Pasted block" });
  });

  it.each([
    ["an empty paste", ""],
    ["a whitespace-only paste", " \n\t  "],
  ])("%s makes no request — DoD-5", async (_label, text) => {
    const backend = serve({});
    const state = seeded({ draft: "Kept.", kindOverride: "partner" });

    await expect(filePastedPartner(state, text)).resolves.toBeUndefined();

    expect(backend.mock).not.toHaveBeenCalled();
    expect(state.draft).toBe("Kept.");
    expect(state.busy).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("a partner filing and the override", () => {
  type Filing = [label: string, run: (state: StreamState) => Promise<void>];
  const FILINGS: Filing[] = [
    ["sendComposer on partner", (state) => sendComposer(state)],
    ["filePastedPartner", (state) => filePastedPartner(state, "Filed partner block.")],
  ];

  it.each(FILINGS)(
    "after a successful %s whose re-read adds an entry, the override is cleared and the position is my turn — DoD-6",
    async (_label, run) => {
      const filed = entry("partner", "Filed partner block.");
      serve({
        [POST_ENTRIES]: created(filed),
        [GET_ENTRIES]: entriesList([filed]),
      });
      const state = seeded({ entries: [], draft: "Filed partner block.", kindOverride: "partner" });
      expect(effectiveKind(state)).toBe("partner");

      await run(state);

      expect(state.kindOverride).toBeNull();
      expect(effectiveKind(state)).toBe("turn");
    },
  );
});

// ---------------------------------------------------------------------------
describe("settleComposer", () => {
  it("with a blank draft and one zone row POSTs only …/settle, then GETs both lists; both lists the re-read ones — DoD-7", async () => {
    const row = zoneRow("user", "The only zone row.");
    const settled = entry("turn", "The only zone row.");
    const rereadEntries = [entry("partner", "Partner opener."), settled];
    const backend = serve({
      [POST_SETTLE]: ok(SETTLE_RESULT),
      [GET_ENTRIES]: entriesList(rereadEntries),
      [GET_ZONE]: zoneList([]),
    });
    const state = seeded({ entries: [rereadEntries[0] as Message], zone: [row], draft: "   ", kindOverride: "turn" });

    await expect(settleComposer(state)).resolves.toBeUndefined();

    expectFirstThenBothReads(backend.keys(), [POST_SETTLE]);
    expect(backend.keys()).not.toContain(POST_ZONE_MESSAGES);
    expect(toJS(state.entries)).toEqual(rereadEntries);
    expect(toJS(state.zone)).toEqual([]);
    expect(state.busy).toBe(false);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("with draft text POSTs …/zone/messages with it, then …/settle, then re-reads both; the draft is cleared — DoD-8", async () => {
    const appended = zoneRow("user", "My turn text");
    const settled = entry("turn", "My turn text");
    const backend = serve({
      [POST_ZONE_MESSAGES]: created(appended),
      [POST_SETTLE]: ok(SETTLE_RESULT),
      [GET_ENTRIES]: entriesList([settled]),
      [GET_ZONE]: zoneList([]),
    });
    const state = seeded({ draft: "My turn text", kindOverride: "turn" });

    await expect(settleComposer(state)).resolves.toBeUndefined();

    expectFirstThenBothReads(backend.keys(), [POST_ZONE_MESSAGES, POST_SETTLE]);
    expect(backend.bodyOf(POST_ZONE_MESSAGES)).toStrictEqual({ text: "My turn text" });
    expect(state.draft).toBe("");
    expect(toJS(state.entries)).toEqual([settled]);
    expect(toJS(state.zone)).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("whose append fails notifies, makes no settle request, re-reads the zone, keeps the draft, ends not busy — DoD-9", async () => {
    const held = zoneRow("assistant", "Held row.");
    const reread = [held];
    const backend = serve({
      [POST_ZONE_MESSAGES]: fails("internal_error", 500),
      [POST_SETTLE]: ok(SETTLE_RESULT),
      [GET_ENTRIES]: entriesList([]),
      [GET_ZONE]: zoneList(reread),
    });
    const state = seeded({ zone: [held], draft: "Unsent text", kindOverride: "turn" });

    await expect(settleComposer(state)).resolves.toBeUndefined();

    expectNotifiedOnceWith("internal_error");
    expect(backend.keys()).not.toContain(POST_SETTLE);
    expect(backend.keys()).toEqual([POST_ZONE_MESSAGES, GET_ZONE]);
    expect(toJS(state.zone)).toEqual(reread);
    expect(state.draft).toBe("Unsent text");
    expect(state.busy).toBe(false);
  });

  it("whose append succeeds and settle fails with 409 zone_empty notifies that code, clears the draft, re-reads both — DoD-10", async () => {
    const appended = zoneRow("user", "Appended then refused.");
    const rereadEntries = [entry("partner", "Partner block.")];
    const backend = serve({
      [POST_ZONE_MESSAGES]: created(appended),
      [POST_SETTLE]: fails("zone_empty", 409),
      [GET_ENTRIES]: entriesList(rereadEntries),
      [GET_ZONE]: zoneList([appended]),
    });
    const state = seeded({ draft: "Appended then refused.", kindOverride: "turn" });

    await expect(settleComposer(state)).resolves.toBeUndefined();

    expectNotifiedOnceWith("zone_empty");
    expect(state.draft).toBe("");
    expectFirstThenBothReads(backend.keys(), [POST_ZONE_MESSAGES, POST_SETTLE]);
    expect(toJS(state.entries)).toEqual(rereadEntries);
    expect(toJS(state.zone)).toEqual([appended]);
    expect(state.busy).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("reopenLast", () => {
  it("POSTs …/reopen, then re-reads both lists — DoD-11", async () => {
    const rereadEntries = [entry("partner", "Partner block.")];
    const rereadZone = [zoneRow("user", "Restored one."), zoneRow("assistant", "Restored two.")];
    const backend = serve({
      [POST_REOPEN]: ok(REOPEN_RESULT),
      [GET_ENTRIES]: entriesList(rereadEntries),
      [GET_ZONE]: zoneList(rereadZone),
    });
    const state = seeded({ entries: [rereadEntries[0] as Message, entry("turn", "Settled turn.")], zone: [] });

    await expect(reopenLast(state)).resolves.toBeUndefined();

    expectFirstThenBothReads(backend.keys(), [POST_REOPEN]);
    expect(toJS(state.entries)).toEqual(rereadEntries);
    expect(toJS(state.zone)).toEqual(rereadZone);
    expect(state.busy).toBe(false);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("a 409 nothing_to_reopen notifies that code and still re-reads both lists — DoD-11", async () => {
    const rereadEntries = [entry("turn", "Lone directly-settled turn.")];
    const backend = serve({
      [POST_REOPEN]: fails("nothing_to_reopen", 409),
      [GET_ENTRIES]: entriesList(rereadEntries),
      [GET_ZONE]: zoneList([]),
    });
    const state = seeded({ entries: [entry("turn", "Stale held turn.")], zone: [] });

    await expect(reopenLast(state)).resolves.toBeUndefined();

    expectNotifiedOnceWith("nothing_to_reopen");
    expectFirstThenBothReads(backend.keys(), [POST_REOPEN]);
    expect(toJS(state.entries)).toEqual(rereadEntries);
    expect(toJS(state.zone)).toEqual([]);
    expect(state.busy).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("editZoneMessage", () => {
  const EDITED_ROLES: MessageRole[] = ["user", "assistant"];

  it.each(EDITED_ROLES)(
    "with changed text on a %s row PATCHes /api/messages/<id> with exactly {text}, replaces only that row, makes no GET, resolves true — DoD-12",
    async (role) => {
      const before = zoneRow("user", "Before row.");
      const target = zoneRow(role, "Original text.");
      const after = zoneRow("tool", "After row.");
      const response: Message = { ...target, text: "Edited text.", updated_at: LATER };
      const backend = serve({
        [patchMessage(target.id)]: ok(response),
        [GET_ZONE]: zoneList([zoneRow("user", "Should not be read.")]),
        [GET_ENTRIES]: entriesList([]),
      });
      const state = seeded({ zone: [before, target, after] });

      await expect(editZoneMessage(state, target.id, "Edited text.")).resolves.toBe(true);

      expect(backend.keys()).toEqual([patchMessage(target.id)]);
      expect(backend.bodyOf(patchMessage(target.id))).toStrictEqual({ text: "Edited text." });
      expect(toJS(state.zone)).toEqual([before, response, after]);
      expect(notifyFailureSpy).not.toHaveBeenCalled();
    },
  );

  it.each([
    ["empty text", ""],
    ["whitespace-only text", "  \n "],
    ["text identical to the row's current text", "Unchanged text."],
  ])("with %s makes no request and resolves true — DoD-13", async (_label, text) => {
    const backend = serve({});
    const row = zoneRow("user", "Unchanged text.");
    const state = seeded({ zone: [row] });

    await expect(editZoneMessage(state, row.id, text)).resolves.toBe(true);

    expect(backend.mock).not.toHaveBeenCalled();
    expect(toJS(state.zone)).toEqual([row]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("a 409 message_not_editable notifies that code, re-reads the zone, resolves false — DoD-13", async () => {
    const keep = zoneRow("user", "Kept row.");
    const gone = zoneRow("assistant", "Settled elsewhere.");
    const reread = [keep];
    const backend = serve({
      [patchMessage(gone.id)]: fails("message_not_editable", 409),
      [GET_ZONE]: zoneList(reread),
    });
    const state = seeded({ zone: [keep, gone] });

    await expect(editZoneMessage(state, gone.id, "My edit.")).resolves.toBe(false);

    expectNotifiedOnceWith("message_not_editable");
    expect(backend.keys()).toEqual([patchMessage(gone.id), GET_ZONE]);
    expect(toJS(state.zone)).toEqual(reread);
  });
});

// ---------------------------------------------------------------------------
type AbortCase = {
  label: string;
  seed: () => StreamState;
  run: (state: StreamState, signal: AbortSignal) => Promise<unknown>;
  firstKey: () => string;
  firstOk: () => Response;
};

const ABORT_ROW = zoneRow("user", "Held zone row.");
const ABORT_ENTRY = entry("turn", "Held turn.");
const LATE_ENTRIES = [entry("partner", "Late entry.")];
const LATE_ZONE = [zoneRow("assistant", "Late zone row.")];

const ABORT_CASES: AbortCase[] = [
  {
    label: "sendComposer on my turn",
    seed: () => seeded({ entries: [ABORT_ENTRY], zone: [ABORT_ROW], draft: "Unsent words.", kindOverride: "turn" }),
    run: (state, signal) => sendComposer(state, signal),
    // 021 step 007 (DoD-7): the my-turn Send's first request is now the compose.
    firstKey: () => POST_COMPOSE,
    firstOk: () => composedOk(),
  },
  {
    label: "sendComposer on partner",
    seed: () => seeded({ entries: [ABORT_ENTRY], zone: [ABORT_ROW], draft: "Partner words.", kindOverride: "partner" }),
    run: (state, signal) => sendComposer(state, signal),
    firstKey: () => POST_ENTRIES,
    firstOk: () => jsonResponse(entry("partner", "Partner words."), 201),
  },
  {
    label: "filePastedPartner",
    seed: () => seeded({ entries: [ABORT_ENTRY], zone: [ABORT_ROW], draft: "Kept draft.", kindOverride: "partner" }),
    run: (state, signal) => filePastedPartner(state, "Pasted block", signal),
    firstKey: () => POST_ENTRIES,
    firstOk: () => jsonResponse(entry("partner", "Pasted block"), 201),
  },
  {
    label: "settleComposer with draft text",
    seed: () => seeded({ entries: [ABORT_ENTRY], zone: [ABORT_ROW], draft: "Settle me.", kindOverride: "turn" }),
    run: (state, signal) => settleComposer(state, signal),
    firstKey: () => POST_ZONE_MESSAGES,
    firstOk: () => jsonResponse(zoneRow("user", "Settle me."), 201),
  },
  {
    label: "settleComposer with a blank draft",
    seed: () => seeded({ entries: [ABORT_ENTRY], zone: [ABORT_ROW], draft: "", kindOverride: "turn" }),
    run: (state, signal) => settleComposer(state, signal),
    firstKey: () => POST_SETTLE,
    firstOk: () => jsonResponse(SETTLE_RESULT, 200),
  },
  {
    label: "reopenLast",
    seed: () => seeded({ entries: [ABORT_ENTRY], zone: [], draft: "Typed.", kindOverride: null }),
    run: (state, signal) => reopenLast(state, signal),
    firstKey: () => POST_REOPEN,
    firstOk: () => jsonResponse(REOPEN_RESULT, 200),
  },
  {
    label: "editZoneMessage",
    seed: () => seeded({ entries: [ABORT_ENTRY], zone: [ABORT_ROW], draft: "Typed." }),
    run: (state, signal) => editZoneMessage(state, ABORT_ROW.id, "A changed text.", signal),
    firstKey: () => patchMessage(ABORT_ROW.id),
    firstOk: () => jsonResponse({ ...ABORT_ROW, text: "A changed text.", updated_at: LATER }, 200),
  },
];

function written(state: StreamState) {
  return { entries: toJS(state.entries), zone: toJS(state.zone), draft: state.draft };
}

const ABORT_ROWS: [label: string, c: AbortCase][] = ABORT_CASES.map((c): [string, AbortCase] => [c.label, c]);

describe("every effect and its signal", () => {
  it.each(ABORT_ROWS)(
    "%s aborted while its first request is pending (fetch rejects) writes nothing and notifies nothing — DoD-14",
    async (_label, c) => {
      stubFetch(
        (_input, init) =>
          new Promise<Response>((_resolve, reject) => {
            const signal = init?.signal;
            signal?.addEventListener("abort", () => {
              reject(signal.reason ?? new DOMException("The operation was aborted.", "AbortError"));
            });
          }),
      );
      const state = c.seed();
      const before = written(state);
      const controller = new AbortController();

      const running = c.run(state, controller.signal);
      await flush();
      controller.abort();

      await running;
      await flush();
      expect(written(state)).toEqual(before);
      expect(notifyFailureSpy).not.toHaveBeenCalled();
    },
  );

  it.each(ABORT_ROWS)(
    "%s whose first response arrives successfully after the abort writes nothing and notifies nothing — DoD-14",
    async (_label, c) => {
      const answer = deferred<Response>();
      serve({
        [POST_ZONE_MESSAGES]: () => jsonResponse(zoneRow("user", "Late append."), 201),
        [POST_COMPOSE]: composes,
        [POST_ENTRIES]: () => jsonResponse(entry("partner", "Late filing."), 201),
        [POST_SETTLE]: ok(SETTLE_RESULT),
        [POST_REOPEN]: ok(REOPEN_RESULT),
        [patchMessage(ABORT_ROW.id)]: () =>
          jsonResponse({ ...ABORT_ROW, text: "A changed text.", updated_at: LATER }, 200),
        [GET_ENTRIES]: entriesList(LATE_ENTRIES),
        [GET_ZONE]: zoneList(LATE_ZONE),
        [c.firstKey()]: () => answer.promise,
      });
      const state = c.seed();
      const before = written(state);
      const controller = new AbortController();

      const running = c.run(state, controller.signal);
      await flush();
      controller.abort();
      answer.resolve(c.firstOk());

      await running;
      await flush();
      expect(written(state)).toEqual(before);
      expect(notifyFailureSpy).not.toHaveBeenCalled();
    },
  );
});

// ---------------------------------------------------------------------------
describe("success paths never notify", () => {
  type SuccessCase = [label: string, setup: () => StreamState, run: (state: StreamState) => Promise<unknown>];

  function serveAllSuccess(): void {
    serve({
      [POST_ZONE_MESSAGES]: created(zoneRow("user", "Ok text.")),
      // 021 step 007 (DoD-7): Send on my turn composes.
      [POST_COMPOSE]: composes,
      [POST_ENTRIES]: created(entry("partner", "Ok text.")),
      [POST_SETTLE]: ok(SETTLE_RESULT),
      [POST_REOPEN]: ok(REOPEN_RESULT),
      [patchMessage(ABORT_ROW.id)]: ok({ ...ABORT_ROW, text: "Ok edit.", updated_at: LATER }),
      [GET_ENTRIES]: entriesList([entry("turn", "Read entry.")]),
      [GET_ZONE]: zoneList([zoneRow("user", "Read row.")]),
    });
  }

  const SUCCESSES: SuccessCase[] = [
    ["sendComposer on my turn", () => seeded({ draft: "Ok text.", kindOverride: "turn" }), (s) => sendComposer(s)],
    ["sendComposer on partner", () => seeded({ draft: "Ok text.", kindOverride: "partner" }), (s) => sendComposer(s)],
    ["filePastedPartner", () => seeded({ kindOverride: "partner" }), (s) => filePastedPartner(s, "Ok text.")],
    ["settleComposer with draft", () => seeded({ draft: "Ok text.", kindOverride: "turn" }), (s) => settleComposer(s)],
    ["settleComposer without draft", () => seeded({ zone: [zoneRow("user", "Z.")], kindOverride: "turn" }), (s) => settleComposer(s)],
    ["reopenLast", () => seeded({ entries: [entry("turn", "T.")] }), (s) => reopenLast(s)],
    ["editZoneMessage", () => seeded({ zone: [ABORT_ROW] }), (s) => editZoneMessage(s, ABORT_ROW.id, "Ok edit.")],
  ];

  it.each(SUCCESSES)("%s calls no notifyFailure — DoD-15", async (_label, setup, run) => {
    serveAllSuccess();
    const state = setup();

    await run(state);

    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});
