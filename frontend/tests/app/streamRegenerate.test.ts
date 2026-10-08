// Feature 022, step 005 — regenerate, showsRegenerate and the non-tool zone derivations
// (DoD-6..DoD-13) (docs/plans/022.discussion-ui/005.live-tools-and-regenerate.md).
//
// Expected values come from the step's Interface intent and Definition of done, context.md D8,
// D9, D13 and 005.context.md:
//   - `showsRegenerate` is true iff not streaming, not busy, and the zone holds a non-tool row;
//   - `regenerate` is a textless compose: one POST …/zone/compose with body exactly {}, the same
//     streaming text / handle / outcome table / terminal zone re-read as `composeMessage`; it never
//     reads or writes the draft, never touches `entries`, `busy` or `kindOverride`, and is a no-op
//     when `showsRegenerate` is false; `stopCompose` and 019 D16's settle-mid-stream apply to it;
//   - `canSettle` counts only non-tool zone rows (or a non-blank draft); the settle target with a
//     blank draft is the last non-tool zone row's text; the preview strings are 013's.
// Streamed bodies are a Response over a ReadableStream of TextEncoder chunks; every await is bounded.
import { autorun, runInAction, toJS } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Message, MessageKind, MessageRole } from "../../src/app/streamApi";
import {
  StreamState,
  canSettle,
  composeMessage,
  isStreaming,
  regenerate,
  settleComposer,
  settlePreviewOf,
  settleTargetText,
  showsRegenerate,
  stopCompose,
  type ComposeHandle,
} from "../../src/app/streamState";
import { ApiError } from "../../src/shared/apiError";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; rawBody: unknown; signal: AbortSignal | undefined };
type Route = (request: Seen) => Response | Promise<Response>;

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "s1";
const COMPOSE_PATH = `/api/sessions/${SESSION_ID}/zone/compose`;
const ZONE_PATH = `/api/sessions/${SESSION_ID}/zone`;
const ENTRIES_PATH = `/api/sessions/${SESSION_ID}/entries`;
const SETTLE_PATH = `/api/sessions/${SESSION_ID}/settle`;
const ZONE_MESSAGES_PATH = `/api/sessions/${SESSION_ID}/zone/messages`;

const POST_COMPOSE = `POST ${COMPOSE_PATH}`;
const GET_ZONE = `GET ${ZONE_PATH}`;
const GET_ENTRIES = `GET ${ENTRIES_PATH}`;
const POST_SETTLE = `POST ${SETTLE_PATH}`;
const POST_ZONE_MESSAGES = `POST ${ZONE_MESSAGES_PATH}`;

const HALF_TYPED = "half typed";
const DONE_ID = "7250000000000000099";
const STAMP = "2026-10-04T09:00:00.000000+00:00";
const SETTLE_RESULT = { entry_id: "7250000000000000990", kind: "turn", buried_ids: ["7250000000000000991"] };

// 013's preview strings (013 D1 / 001.context.md).
const PREVIEW_TURN = "Settles as a turn.";
const PREVIEW_STRIPPING = "Settles as a turn; the (( )) instructions will be removed.";
const PREVIEW_DECISION = "Settles as a decision (out of character).";

const enc = new TextEncoder();

let nextId = 500;
function freshId(): string {
  nextId += 1;
  return `7250000000000000${String(nextId).padStart(3, "0")}`;
}

function zoneRow(role: MessageRole, text: string, id = freshId()): Message {
  return { id, session_id: SESSION_ID, role, kind: null, text, settled_at: null, created_at: STAMP, updated_at: STAMP };
}

/** A tool row per 005.context.md's fixture: text "lookup", memo_search, ok, {} args. */
function toolRow(text = "lookup", id = freshId()): Message {
  return { ...zoneRow("tool", text, id), tool_name: "memo_search", tool_status: "ok", tool_args: {} };
}

function entry(id: string, kind: MessageKind, text: string): Message {
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

const USER_ROW = zoneRow("user", "The lighthouse keeper waits.", "7250000000000000201");
const ASSISTANT_ROW = zoneRow("assistant", "Once upon a time.", DONE_ID);
const PARTIAL_ROW = zoneRow("assistant", "Once ", "7250000000000000202");

type Seed = { entries?: Message[]; zone?: Message[]; draft?: string; busy?: boolean; kindOverride?: "partner" | "turn" | null };

function seeded(seed: Seed = {}): StreamState {
  const state = new StreamState(SESSION_ID);
  runInAction(() => {
    state.entries = seed.entries ?? [];
    if (seed.zone !== undefined) state.zone = seed.zone;
    if (seed.draft !== undefined) state.draft = seed.draft;
    if (seed.busy !== undefined) state.busy = seed.busy;
    if (seed.kindOverride !== undefined) state.kindOverride = seed.kindOverride;
    state.status = "ready";
  });
  return state;
}

/** Puts the state in a streaming condition with a live (unaborted) handle. */
function markStreaming(state: StreamState, text: string): ComposeHandle {
  const handle: ComposeHandle = { controller: new AbortController(), woundDown: Promise.resolve() };
  runInAction(() => {
    state.streamingText = text;
    state.composeHandle = handle;
  });
  return handle;
}

beforeEach(() => {
  notifyFailureSpy.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- harness
function within<T>(promise: Promise<T>, ms = 2000): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_resolve, reject) => {
    timer = setTimeout(() => reject(new Error(`timed out after ${ms}ms`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

async function until(predicate: () => boolean, label: string, ms = 2000): Promise<void> {
  const start = Date.now();
  while (!predicate()) {
    if (Date.now() - start > ms) throw new Error(`condition not met within ${ms}ms: ${label}`);
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
  }
}

async function flush(rounds = 10): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
  }
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: "ql-77 went wrong.", detail: {} } }, status);
}

const zoneJson = (list: Message[]): Response => jsonResponse({ messages: list }, 200);
const entriesJson = (list: Message[]): Response => jsonResponse({ entries: list }, 200);

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function abortError(): DOMException {
  return new DOMException("The operation was aborted.", "AbortError");
}

const keyOf = (request: Seen): string => `${request.method} ${request.path}`;

function serve(routes: Record<string, Route>) {
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>(async (input, init) => {
    const signal = init?.signal ?? (input instanceof Request ? input.signal : undefined) ?? undefined;
    const request: Seen = {
      method: requestMethod(input, init),
      path: requestUrl(input).pathname,
      rawBody: init?.body,
      signal,
    };
    calls.push(request);
    if (signal?.aborted === true) throw abortError();
    const route = routes[keyOf(request)];
    if (route === undefined) return envelope(`unexpected_${request.method}_${request.path}`, 418);
    return route(request);
  });
  vi.stubGlobal("fetch", mock);
  const keys = (): string[] => calls.map(keyOf);
  const count = (key: string): number => keys().filter((k) => k === key).length;
  return { mock, calls, keys, count };
}

type HeldSse = {
  response: Response;
  signal: AbortSignal | undefined;
  push: (payload: unknown) => void;
  close: () => void;
};

function heldSse(signal: AbortSignal | undefined): HeldSse {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  let ended = false;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  const fail = (): void => {
    if (ended) return;
    ended = true;
    try {
      controller.error(abortError());
    } catch {
      // already cancelled by the reader
    }
  };
  if (signal !== undefined) {
    if (signal.aborted) fail();
    else signal.addEventListener("abort", fail, { once: true });
  }
  return {
    response: new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } }),
    signal,
    push(payload) {
      if (ended) return;
      try {
        controller.enqueue(enc.encode(`data: ${JSON.stringify(payload)}\n\n`));
      } catch {
        // already cancelled by the reader
      }
    },
    close() {
      if (ended) return;
      ended = true;
      try {
        controller.close();
      } catch {
        // already cancelled by the reader
      }
    },
  };
}

function composeStreams() {
  const streams: HeldSse[] = [];
  const route: Route = (request) => {
    const held = heldSse(request.signal);
    streams.push(held);
    return held.response;
  };
  const nth = (i: number): HeldSse => {
    const held = streams[i];
    if (held === undefined) throw new Error(`no compose stream #${i}`);
    return held;
  };
  return { streams, route, nth };
}

function zoneSequence(...lists: Message[][]): Route {
  let i = 0;
  return () => {
    const list = lists[Math.min(i, lists.length - 1)] ?? [];
    i += 1;
    return zoneJson(list);
  };
}

function rawBodyJson(raw: unknown): unknown {
  expect(typeof raw).toBe("string");
  return JSON.parse(raw as string) as unknown;
}

function expectNotifiedOnceWith(code: string): void {
  expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
  const error = notifyFailureSpy.mock.calls[0]?.[0];
  expect(error).toBeInstanceOf(ApiError);
  expect((error as ApiError).code).toBe(code);
}

/** 013's preview strings, keyed by settlePreviewOf's result. */
function previewString(state: StreamState): string | null {
  const preview = settlePreviewOf(state);
  if (preview === null) return null;
  if (preview.kind === "decision") return PREVIEW_DECISION;
  return preview.strips ? PREVIEW_STRIPPING : PREVIEW_TURN;
}

// ---------------------------------------------------------------- DoD-6
describe("showsRegenerate (D8)", () => {
  it.each([
    ["[user]", () => [zoneRow("user", "Mine.")]],
    ["[user, assistant]", () => [zoneRow("user", "Mine."), zoneRow("assistant", "Theirs.")]],
    ["[user, tool, assistant]", () => [zoneRow("user", "Mine."), toolRow(), zoneRow("assistant", "Theirs.")]],
  ])("is true for zone %s when not streaming and not busy — DoD-6", (_label, zone) => {
    const state = seeded({ zone: zone(), busy: false });
    expect(isStreaming(state)).toBe(false);
    expect(showsRegenerate(state)).toBe(true);
  });

  it("is false for an empty zone — DoD-6", () => {
    expect(showsRegenerate(seeded({ zone: [] }))).toBe(false);
  });

  it("is false for a zone of [tool] only — DoD-6", () => {
    expect(showsRegenerate(seeded({ zone: [toolRow()] }))).toBe(false);
  });

  it('is false while streaming (streaming text "") — DoD-6', () => {
    const state = seeded({ zone: [zoneRow("user", "Mine.")] });
    markStreaming(state, "");
    expect(isStreaming(state)).toBe(true);
    expect(showsRegenerate(state)).toBe(false);
  });

  it("is false while busy — DoD-6", () => {
    expect(showsRegenerate(seeded({ zone: [zoneRow("user", "Mine.")], busy: true }))).toBe(false);
  });
});

// ---------------------------------------------------------------- DoD-7
describe("regenerate — the textless compose (D8, US-044.AC-3, R10)", () => {
  it('issues exactly one POST /api/sessions/s1/zone/compose with body exactly {}, streams tokens, re-reads the zone on done, and keeps the draft "half typed" throughout; no /zone/messages request — DoD-7', async () => {
    const finalList = [USER_ROW, ASSISTANT_ROW];
    const compose = composeStreams();
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence(finalList) });
    const state = seeded({ zone: [USER_ROW], draft: HALF_TYPED, kindOverride: "turn" });
    const draftsSeen: string[] = [];
    const dispose = autorun(() => {
      draftsSeen.push(state.draft);
    });
    try {
      expect(isStreaming(state)).toBe(false);
      const running = regenerate(state);
      await until(() => compose.streams.length === 1, "compose POST issued");
      await until(() => isStreaming(state), "isStreaming while the body is held open");

      expect(backend.count(POST_COMPOSE)).toBe(1);
      const request = backend.calls.find((c) => keyOf(c) === POST_COMPOSE);
      expect(rawBodyJson(request?.rawBody)).toStrictEqual({});

      compose.nth(0).push({ event: "token", text: "Once " });
      compose.nth(0).push({ event: "token", text: "upon" });
      await until(() => state.streamingText === "Once upon", "tokens appended");
      expect(state.streamingText).toBe("Once upon");
      expect(state.draft).toBe(HALF_TYPED);
      const zoneGetsBeforeDone = backend.count(GET_ZONE);

      compose.nth(0).push({ event: "done", message_id: DONE_ID });
      compose.nth(0).close();
      await expect(within(running)).resolves.toBeUndefined();

      expect(backend.count(GET_ZONE)).toBeGreaterThan(zoneGetsBeforeDone);
      expect(backend.keys()[backend.keys().length - 1]).toBe(GET_ZONE);
      expect(toJS(state.zone)).toEqual(finalList);
      expect(state.streamingText).toBeNull();
      expect(isStreaming(state)).toBe(false);
      expect(notifyFailureSpy).not.toHaveBeenCalled();
    } finally {
      dispose();
    }

    expect(state.draft).toBe(HALF_TYPED);
    expect(draftsSeen.every((d) => d === HALF_TYPED)).toBe(true);
    expect(backend.count(POST_COMPOSE)).toBe(1);
    expect(backend.count(POST_ZONE_MESSAGES)).toBe(0);
    expect(backend.calls.some((c) => c.path === ZONE_MESSAGES_PATH)).toBe(false);
  });

  it("an accepted frame during a regenerate only triggers a zone re-read: the draft stays, busy, entries and kindOverride are untouched — DoD-7", async () => {
    const earlierEntry = entry("7250000000000000060", "partner", "Partner opener.");
    const compose = composeStreams();
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([USER_ROW], [USER_ROW, ASSISTANT_ROW]) });
    const state = seeded({ entries: [earlierEntry], zone: [USER_ROW], draft: HALF_TYPED, kindOverride: "turn" });
    const entriesBefore = state.entries;
    const busySeen: boolean[] = [];
    const dispose = autorun(() => {
      busySeen.push(state.busy);
    });
    try {
      const running = regenerate(state);
      await until(() => compose.streams.length === 1, "compose POST issued");
      compose.nth(0).push({ event: "accepted", message_id: USER_ROW.id });
      await until(() => backend.count(GET_ZONE) >= 1, "zone GET after accepted");
      await flush();

      expect(state.draft).toBe(HALF_TYPED);

      compose.nth(0).push({ event: "done", message_id: DONE_ID });
      compose.nth(0).close();
      await expect(within(running)).resolves.toBeUndefined();
    } finally {
      dispose();
    }

    expect(state.draft).toBe(HALF_TYPED);
    expect(state.kindOverride).toBe("turn");
    expect(state.entries).toBe(entriesBefore);
    expect(toJS(state.entries)).toEqual([earlierEntry]);
    expect(backend.count(GET_ENTRIES)).toBe(0);
    expect(busySeen.every((b) => !b)).toBe(true);
    expect(backend.count(POST_ZONE_MESSAGES)).toBe(0);
  });
});

// ---------------------------------------------------------------- DoD-8
describe("regenerate — failures and the persistent retry (D8, D13, US-044.AC-2/3/4)", () => {
  it("an error frame llm_unreachable notifies once with that code, re-reads the zone, leaves entries and the draft untouched, clears the streaming text; showsRegenerate is true again — DoD-8", async () => {
    const earlierEntry = entry("7250000000000000060", "partner", "Partner opener.");
    const finalList = [USER_ROW, PARTIAL_ROW];
    const compose = composeStreams();
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence(finalList) });
    const state = seeded({ entries: [earlierEntry], zone: [USER_ROW], draft: HALF_TYPED, kindOverride: "turn" });
    const entriesBefore = state.entries;

    const running = regenerate(state);
    await until(() => compose.streams.length === 1, "compose POST issued");
    compose.nth(0).push({ event: "token", text: "Once " });
    await until(() => state.streamingText === "Once ", "one token");
    const zoneGetsBeforeError = backend.count(GET_ZONE);
    compose.nth(0).push({ event: "error", code: "llm_unreachable", message: "down", detail: {} });
    compose.nth(0).close();
    await expect(within(running)).resolves.toBeUndefined();

    expectNotifiedOnceWith("llm_unreachable");
    expect(backend.count(GET_ZONE)).toBeGreaterThan(zoneGetsBeforeError);
    expect(backend.keys()[backend.keys().length - 1]).toBe(GET_ZONE);
    expect(toJS(state.zone)).toEqual(finalList);
    expect(state.entries).toBe(entriesBefore);
    expect(toJS(state.entries)).toEqual([earlierEntry]);
    expect(backend.count(GET_ENTRIES)).toBe(0);
    expect(state.draft).toBe(HALF_TYPED);
    expect(state.streamingText).toBeNull();
    expect(showsRegenerate(state)).toBe(true);
  });

  it("a non-2xx 409 zone_empty answer notifies zone_empty and re-reads the zone; with a non-tool row served, showsRegenerate is true again — DoD-8", async () => {
    const backend = serve({
      [POST_COMPOSE]: () => envelope("zone_empty", 409),
      [GET_ZONE]: zoneSequence([USER_ROW]),
    });
    const state = seeded({ zone: [USER_ROW], draft: HALF_TYPED, kindOverride: "turn" });

    await expect(within(regenerate(state))).resolves.toBeUndefined();

    expectNotifiedOnceWith("zone_empty");
    expect(backend.count(POST_COMPOSE)).toBe(1);
    expect(backend.count(GET_ZONE)).toBeGreaterThanOrEqual(1);
    expect(backend.keys()[backend.keys().length - 1]).toBe(GET_ZONE);
    expect(toJS(state.zone)).toEqual([USER_ROW]);
    expect(state.draft).toBe(HALF_TYPED);
    expect(state.streamingText).toBeNull();
    expect(isStreaming(state)).toBe(false);
    expect(showsRegenerate(state)).toBe(true);
  });
});

// ---------------------------------------------------------------- DoD-9
describe("regenerate — no-ops (D8)", () => {
  it.each([
    ["the zone is empty", (): StreamState => seeded({ zone: [], draft: HALF_TYPED })],
    ["the zone holds only tool rows", (): StreamState => seeded({ zone: [toolRow(), toolRow("lookup again")] })],
    ["busy", (): StreamState => seeded({ zone: [USER_ROW], busy: true })],
  ])("makes no request when %s — DoD-9", async (_label, make) => {
    const backend = serve({ [POST_COMPOSE]: composeStreams().route, [GET_ZONE]: zoneSequence([USER_ROW]) });
    const state = make();
    const zoneBefore = toJS(state.zone);
    const draftBefore = state.draft;

    await expect(within(regenerate(state))).resolves.toBeUndefined();
    await flush();

    expect(backend.mock).not.toHaveBeenCalled();
    expect(state.streamingText).toBeNull();
    expect(toJS(state.zone)).toEqual(zoneBefore);
    expect(state.draft).toBe(draftBefore);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("makes no request while streaming, and leaves the streaming text and handle alone — DoD-9", async () => {
    const backend = serve({ [POST_COMPOSE]: composeStreams().route, [GET_ZONE]: zoneSequence([USER_ROW]) });
    const state = seeded({ zone: [USER_ROW] });
    const handle = markStreaming(state, "Partial");

    await expect(within(regenerate(state))).resolves.toBeUndefined();
    await flush();

    expect(backend.mock).not.toHaveBeenCalled();
    expect(state.streamingText).toBe("Partial");
    expect(state.composeHandle).toBe(handle);
    expect(handle.controller.signal.aborted).toBe(false);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("a second regenerate while one is in flight issues no second compose request — DoD-9", async () => {
    const compose = composeStreams();
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([USER_ROW, ASSISTANT_ROW]) });
    const state = seeded({ zone: [USER_ROW] });

    const running = regenerate(state);
    await until(() => compose.streams.length === 1, "compose POST issued");
    await until(() => isStreaming(state), "streaming");
    const callsBefore = backend.calls.length;

    await expect(within(regenerate(state))).resolves.toBeUndefined();
    await flush();
    expect(backend.calls.length).toBe(callsBefore);
    expect(backend.count(POST_COMPOSE)).toBe(1);

    compose.nth(0).push({ event: "done", message_id: DONE_ID });
    compose.nth(0).close();
    await within(running);
  });
});

// ---------------------------------------------------------------- DoD-10
describe("regenerate — Stop and Settle mid-regenerate (D8, 019 D16)", () => {
  it("stopCompose aborts its request; it ends with no notification, a zone re-read and the streaming text cleared — DoD-10", async () => {
    const stoppedList = [USER_ROW, PARTIAL_ROW];
    const compose = composeStreams();
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence(stoppedList) });
    const state = seeded({ zone: [USER_ROW], draft: HALF_TYPED });

    const running = regenerate(state);
    await until(() => compose.streams.length === 1, "compose POST issued");
    compose.nth(0).push({ event: "token", text: "Once " });
    await until(() => state.streamingText === "Once ", "one token");
    const composeSignal = compose.nth(0).signal;
    expect(composeSignal?.aborted).toBe(false);
    const zoneGetsBeforeStop = backend.count(GET_ZONE);

    stopCompose(state);
    await expect(within(running)).resolves.toBeUndefined();
    await flush();

    expect(composeSignal?.aborted).toBe(true);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(backend.count(GET_ZONE)).toBeGreaterThan(zoneGetsBeforeStop);
    expect(backend.keys()[backend.keys().length - 1]).toBe(GET_ZONE);
    expect(toJS(state.zone)).toEqual(stoppedList);
    expect(state.streamingText).toBeNull();
    expect(state.composeHandle).toBeNull();
    expect(state.draft).toBe(HALF_TYPED);
  });

  it("settleComposer during a regenerate stops it, waits for its post-stop zone GET, then POSTs settle and re-reads both; no notification — DoD-10", async () => {
    const settledEntry = entry("7250000000000000990", "turn", PARTIAL_ROW.text);
    const compose = composeStreams();
    const backend = serve({
      [POST_COMPOSE]: compose.route,
      // the regenerate's post-stop re-read, then the settle's re-read
      [GET_ZONE]: zoneSequence([USER_ROW, PARTIAL_ROW], []),
      [POST_SETTLE]: () => jsonResponse(SETTLE_RESULT, 200),
      [GET_ENTRIES]: () => entriesJson([settledEntry]),
    });
    const state = seeded({ entries: [], zone: [USER_ROW], draft: "", busy: false, kindOverride: "turn" });

    const running = regenerate(state);
    await until(() => compose.streams.length === 1, "compose POST issued");
    compose.nth(0).push({ event: "token", text: "Once " });
    await until(() => state.streamingText === "Once ", "one token");
    expect(isStreaming(state)).toBe(true);

    const handle = state.composeHandle;
    expect(handle).not.toBeNull();
    const composeSignal = compose.nth(0).signal;
    const callsAtSettle = backend.calls.length;
    expect(backend.keys()).toEqual([POST_COMPOSE]);

    await expect(within(settleComposer(state))).resolves.toBeUndefined();
    await expect(within(running)).resolves.toBeUndefined();

    expect(handle?.controller.signal.aborted).toBe(true);
    expect(composeSignal?.aborted).toBe(true);
    expect(notifyFailureSpy).not.toHaveBeenCalled();

    const after = backend.keys().slice(callsAtSettle);
    expect(after.slice(0, 2)).toEqual([GET_ZONE, POST_SETTLE]);
    expect(after.slice(2).sort()).toEqual([GET_ENTRIES, GET_ZONE].sort());
    expect(after).not.toContain(POST_ZONE_MESSAGES);

    expect(state.streamingText).toBeNull();
    expect(state.busy).toBe(false);
    expect(toJS(state.entries)).toEqual([settledEntry]);
    expect(toJS(state.zone)).toEqual([]);
  });
});

// ---------------------------------------------------------------- DoD-11
describe("canSettle counts only non-tool zone rows (D9, US-135.AC-1)", () => {
  it("my turn, not busy, blank draft, zone [user] → true — DoD-11", () => {
    expect(canSettle(seeded({ zone: [zoneRow("user", "Mine.")], draft: "" }))).toBe(true);
  });

  it("my turn, not busy, blank draft, zone [user, tool] → true — DoD-11", () => {
    expect(canSettle(seeded({ zone: [zoneRow("user", "Mine."), toolRow()], draft: "  " }))).toBe(true);
  });

  it("my turn, not busy, blank draft, zone [tool] → false — DoD-11", () => {
    expect(canSettle(seeded({ zone: [toolRow()], draft: "" }))).toBe(false);
  });

  it('my turn, not busy, draft "x", zone [tool] → true — DoD-11', () => {
    expect(canSettle(seeded({ zone: [toolRow()], draft: "x" }))).toBe(true);
  });
});

// ---------------------------------------------------------------- DoD-12
describe("the settle target skips tool rows (D9, US-126.AC-1, 013 D1)", () => {
  it('over [user "Mine", assistant "Theirs", tool "lookup"] with a blank draft the target is "Theirs" and the preview reads "Settles as a turn." — DoD-12', () => {
    const state = seeded({
      zone: [zoneRow("user", "Mine"), zoneRow("assistant", "Theirs"), toolRow("lookup")],
      draft: "",
    });
    expect(settleTargetText(state)).toBe("Theirs");
    expect(settlePreviewOf(state)).toEqual({ kind: "turn", strips: false });
    expect(previewString(state)).toBe(PREVIEW_TURN);
  });

  it('over [user "((ooc))", tool "lookup"] with a blank draft the preview reads "Settles as a decision (out of character)." — DoD-12', () => {
    const state = seeded({ zone: [zoneRow("user", "((ooc))"), toolRow("lookup")], draft: " " });
    expect(settleTargetText(state)).toBe("((ooc))");
    expect(settlePreviewOf(state)?.kind).toBe("decision");
    expect(previewString(state)).toBe(PREVIEW_DECISION);
  });

  it("over a zone of only tool rows with a blank draft there is nothing to settle (as for an empty zone) — DoD-12", () => {
    const toolsOnly = seeded({ zone: [toolRow("lookup")], draft: "" });
    const empty = seeded({ zone: [], draft: "" });
    expect(settleTargetText(toolsOnly)).toBe(settleTargetText(empty));
    expect(settlePreviewOf(toolsOnly)).toEqual(settlePreviewOf(empty));
  });
});

// ---------------------------------------------------------------- DoD-13
describe("composeMessage is unchanged by the tool handling (019 D11–D16)", () => {
  it('composeMessage still POSTs exactly {"text": <draft>}, clears the sent draft on accepted, and ends not streaming with an empty live list — DoD-13', async () => {
    const draft = "Find it";
    const accepted = zoneRow("user", draft, "7250000000000000300");
    const compose = composeStreams();
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([accepted], [accepted, ASSISTANT_ROW]) });
    const state = seeded({ draft, kindOverride: "turn" });

    const running = composeMessage(state);
    await until(() => compose.streams.length === 1, "compose POST issued");
    const request = backend.calls.find((c) => keyOf(c) === POST_COMPOSE);
    expect(rawBodyJson(request?.rawBody)).toStrictEqual({ text: draft });

    compose.nth(0).push({ event: "accepted", message_id: accepted.id });
    await until(() => backend.count(GET_ZONE) >= 1, "zone GET after accepted");
    await flush();
    expect(state.draft).toBe("");

    compose.nth(0).push({ event: "done", message_id: DONE_ID });
    compose.nth(0).close();
    await expect(within(running)).resolves.toBeUndefined();

    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(toJS(state.zone)).toEqual([accepted, ASSISTANT_ROW]);
    expect(state.streamingText).toBeNull();
    expect(toJS(state.liveTools)).toEqual([]);
    expect(isStreaming(state)).toBe(false);
  });
});
