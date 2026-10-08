// Feature 019, step 005 — the compose effect and Settle-mid-stream
// (docs/plans/019.streaming-transport-and-stop/005.compose-effect.md), DoD-1..DoD-11.
//
// Expected values come from the step's Interface intent and Definition of done, context.md
// D11-D16, D18 and 005.context.md ("Ordering of re-reads", "Test notes"):
//   - `composeMessage` POSTs /api/sessions/<id>/zone/compose with exactly {"text": <draft>},
//     streams `token` text into the streaming text, never inserts a zone row and never touches
//     `busy`;
//   - `accepted` clears the draft only if it still equals the sent text and starts a zone re-read;
//   - on every outcome but an unmount: done/stopped notify nothing, error notifies its ApiError,
//     unexpected end notifies `llm_unreachable`; then (after the accepted re-read settled) the zone
//     is re-read and the streaming text and handle go back to null;
//   - an unmount (mount signal abort) aborts the compose request and writes, re-reads and
//     notifies nothing afterwards;
//   - `settleComposer` with a compose in flight stops it, waits for its wind-down (post-stop zone
//     re-read included), then runs the unchanged 013 settle flow.
// The streamed body is a Response over a ReadableStream the test controls; the stub honours the
// request's signal by erroring the body with an AbortError. Every await is bounded.
import { autorun, reaction, runInAction, toJS } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Message, MessageKind, MessageRole } from "../../src/app/streamApi";
import {
  StreamState,
  canSend,
  canSettle,
  composeMessage,
  isStreaming,
  settleComposer,
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

const DRAFT = "Write me a reply";
const ACCEPTED_ID = "7250000000000000098";
const DONE_ID = "7250000000000000099";
const STAMP = "2026-10-04T09:00:00.000000+00:00";
const SETTLE_RESULT = { entry_id: "7250000000000000990", kind: "turn", buried_ids: ["7250000000000000991"] };

const enc = new TextEncoder();

function zoneRow(id: string, role: MessageRole, text: string): Message {
  return { id, session_id: SESSION_ID, role, kind: null, text, settled_at: null, created_at: STAMP, updated_at: STAMP };
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

/** The roleplayer's committed message, as the server serves it after `accepted`. */
const USER_ROW = zoneRow(ACCEPTED_ID, "user", DRAFT);
/** The assistant row the server serves after `done`. */
const ASSISTANT_ROW = zoneRow(DONE_ID, "assistant", "Once upon a time.");
/** The persisted partial assistant row the server serves after a stop. */
const PARTIAL_ROW = zoneRow("7250000000000000101", "assistant", "Once ");

type Seed = { entries?: Message[]; zone?: Message[]; draft?: string; busy?: boolean; kindOverride?: "partner" | "turn" | null };

function seeded(seed: Seed = {}): StreamState {
  const state = new StreamState(SESSION_ID);
  runInAction(() => {
    if (seed.entries !== undefined) state.entries = seed.entries;
    if (seed.zone !== undefined) state.zone = seed.zone;
    if (seed.draft !== undefined) state.draft = seed.draft;
    if (seed.busy !== undefined) state.busy = seed.busy;
    if (seed.kindOverride !== undefined) state.kindOverride = seed.kindOverride;
    state.status = "ready";
  });
  return state;
}

beforeEach(() => {
  notifyFailureSpy.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- harness
/** Rejects if `promise` has not settled within `ms`, so a stuck call fails instead of hanging. */
function within<T>(promise: Promise<T>, ms = 2000): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_resolve, reject) => {
    timer = setTimeout(() => reject(new Error(`timed out after ${ms}ms`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

/** Waits until `predicate` holds; fails (never hangs) after `ms`. */
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

/**
 * A backend keyed on exact "METHOD pathname"; every request is recorded in order.
 * A request whose signal is already aborted rejects with an AbortError, as a browser does.
 * Anything not routed answers an unexpected 418 envelope.
 */
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

function sseFrame(payload: unknown): string {
  return `data: ${JSON.stringify(payload)}\n\n`;
}

type HeldSse = {
  response: Response;
  signal: AbortSignal | undefined;
  push: (payload: unknown) => void;
  close: () => void;
};

/** A streamed 200 body held open until the test closes it; an abort of `signal` errors it. */
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
        controller.enqueue(enc.encode(sseFrame(payload)));
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

/** The compose route: each POST gets a fresh held-open stream the test drives. */
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

/** Serves the given zone lists in turn, repeating the last one. */
function zoneSequence(...lists: Message[][]): Route {
  let i = 0;
  return () => {
    const list = lists[Math.min(i, lists.length - 1)] ?? [];
    i += 1;
    return zoneJson(list);
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

/** The first zone GET waits on a gate the test opens; later ones serve `later`. */
function gatedFirstZone(later: Message[]) {
  const gate = deferred<Response>();
  let first = true;
  const route: Route = () => {
    if (first) {
      first = false;
      return gate.promise;
    }
    return zoneJson(later);
  };
  return { route, open: (list: Message[]) => gate.resolve(zoneJson(list)) };
}

function expectNotifiedOnceWith(code: string): void {
  expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
  const error = notifyFailureSpy.mock.calls[0]?.[0];
  expect(error).toBeInstanceOf(ApiError);
  expect((error as ApiError).code).toBe(code);
}

// ---------------------------------------------------------------- DoD-1
describe("composeMessage — starts the compose (D12, D13)", () => {
  it('POSTs /api/sessions/s1/zone/compose with exactly {"text":"Write me a reply"} — DoD-1', async () => {
    const compose = composeStreams();
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([USER_ROW], [USER_ROW, ASSISTANT_ROW]) });
    const state = seeded({ draft: DRAFT, kindOverride: "turn" });

    const running = composeMessage(state);
    await until(() => compose.streams.length === 1, "compose POST issued");

    expect(backend.count(POST_COMPOSE)).toBe(1);
    const request = backend.calls.find((c) => keyOf(c) === POST_COMPOSE);
    expect(request?.rawBody).toBe('{"text":"Write me a reply"}');
    expect(backend.keys()[0]).toBe(POST_COMPOSE);

    compose.nth(0).push({ event: "accepted", message_id: ACCEPTED_ID });
    compose.nth(0).push({ event: "done", message_id: DONE_ID });
    compose.nth(0).close();
    await expect(within(running)).resolves.toBeUndefined();
  });

  it("sets isStreaming true before the body completes — DoD-1", async () => {
    const compose = composeStreams();
    serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([USER_ROW], [USER_ROW, ASSISTANT_ROW]) });
    const state = seeded({ draft: DRAFT, kindOverride: "turn" });
    expect(isStreaming(state)).toBe(false);

    const running = composeMessage(state);
    await until(() => compose.streams.length === 1, "compose POST issued");
    await until(() => isStreaming(state), "isStreaming true while the body is held open");

    expect(isStreaming(state)).toBe(true);

    compose.nth(0).push({ event: "accepted", message_id: ACCEPTED_ID });
    compose.nth(0).push({ event: "done", message_id: DONE_ID });
    compose.nth(0).close();
    await within(running);
  });

  it("leaves busy false throughout — DoD-1", async () => {
    const compose = composeStreams();
    serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([USER_ROW], [USER_ROW, ASSISTANT_ROW]) });
    const state = seeded({ draft: DRAFT, busy: false, kindOverride: "turn" });
    const seenBusy: boolean[] = [];
    const dispose = autorun(() => {
      seenBusy.push(state.busy);
    });
    try {
      const running = composeMessage(state);
      await until(() => compose.streams.length === 1, "compose POST issued");
      compose.nth(0).push({ event: "accepted", message_id: ACCEPTED_ID });
      compose.nth(0).push({ event: "token", text: "Once " });
      await flush();
      compose.nth(0).push({ event: "done", message_id: DONE_ID });
      compose.nth(0).close();
      await within(running);
    } finally {
      dispose();
    }

    expect(seenBusy.every((b) => !b)).toBe(true);
    expect(state.busy).toBe(false);
  });
});

// ---------------------------------------------------------------- DoD-2
describe("composeMessage — accepted and tokens (D11, D15, never optimistic)", () => {
  it('after accepted the draft is "" and a GET /api/sessions/s1/zone was issued — DoD-2', async () => {
    const compose = composeStreams();
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([USER_ROW], [USER_ROW, ASSISTANT_ROW]) });
    const state = seeded({ draft: DRAFT, kindOverride: "turn" });

    const running = composeMessage(state);
    await until(() => compose.streams.length === 1, "compose POST issued");
    expect(backend.count(GET_ZONE)).toBe(0);

    compose.nth(0).push({ event: "accepted", message_id: ACCEPTED_ID });
    await until(() => backend.count(GET_ZONE) >= 1, "zone GET after accepted");

    expect(state.draft).toBe("");
    expect(backend.count(GET_ZONE)).toBe(1);

    compose.nth(0).push({ event: "done", message_id: DONE_ID });
    compose.nth(0).close();
    await within(running);
  });

  it('after tokens "Once " and "upon" (held open) the streaming text is exactly "Once upon" — DoD-2', async () => {
    const compose = composeStreams();
    serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([USER_ROW], [USER_ROW, ASSISTANT_ROW]) });
    const state = seeded({ draft: DRAFT, kindOverride: "turn" });

    const running = composeMessage(state);
    await until(() => compose.streams.length === 1, "compose POST issued");
    compose.nth(0).push({ event: "accepted", message_id: ACCEPTED_ID });
    compose.nth(0).push({ event: "token", text: "Once " });
    compose.nth(0).push({ event: "token", text: "upon" });
    await flush();

    expect(state.streamingText).toBe("Once upon");
    expect(isStreaming(state)).toBe(true);

    compose.nth(0).push({ event: "done", message_id: DONE_ID });
    compose.nth(0).close();
    await within(running);
  });

  it("zone never holds a row the server did not serve (no placeholder), and no /api/messages/... request is made — DoD-2", async () => {
    const earlier = zoneRow("7250000000000000050", "assistant", "Earlier row.");
    const compose = composeStreams();
    const backend = serve({
      [POST_COMPOSE]: compose.route,
      [GET_ZONE]: zoneSequence([earlier, USER_ROW], [earlier, USER_ROW, ASSISTANT_ROW]),
    });
    const state = seeded({ zone: [earlier], draft: DRAFT, kindOverride: "turn" });
    const servedIds = new Set([earlier.id, USER_ROW.id, ASSISTANT_ROW.id]);
    const zoneIdsSeen: string[][] = [];
    const dispose = autorun(() => {
      zoneIdsSeen.push(state.zone.map((row) => row.id));
    });
    try {
      const running = composeMessage(state);
      await until(() => compose.streams.length === 1, "compose POST issued");
      compose.nth(0).push({ event: "accepted", message_id: ACCEPTED_ID });
      compose.nth(0).push({ event: "token", text: "Once " });
      compose.nth(0).push({ event: "token", text: "upon" });
      await until(() => backend.count(GET_ZONE) >= 1, "zone GET after accepted");
      await flush();

      // Held open: the zone is exactly the served list, the tokens live elsewhere.
      expect(toJS(state.zone)).toEqual([earlier, USER_ROW]);

      compose.nth(0).push({ event: "done", message_id: DONE_ID });
      compose.nth(0).close();
      await within(running);
    } finally {
      dispose();
    }

    for (const ids of zoneIdsSeen) {
      for (const id of ids) expect(servedIds.has(id)).toBe(true);
    }
    expect(backend.calls.some((c) => c.path.startsWith("/api/messages/") || c.path === "/api/messages")).toBe(false);
  });
});

// ---------------------------------------------------------------- DoD-3
describe("composeMessage — a draft changed before accepted is kept (D15, R10)", () => {
  it('"Write me a reply" sent, then "Write me a reply!" typed: the draft is kept after accepted — DoD-3', async () => {
    const compose = composeStreams();
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([USER_ROW], [USER_ROW, ASSISTANT_ROW]) });
    const state = seeded({ draft: DRAFT, kindOverride: "turn" });

    const running = composeMessage(state);
    await until(() => compose.streams.length === 1, "compose POST issued");
    runInAction(() => {
      state.draft = "Write me a reply!";
    });

    compose.nth(0).push({ event: "accepted", message_id: ACCEPTED_ID });
    await until(() => backend.count(GET_ZONE) >= 1, "zone GET after accepted");
    await flush();

    expect(state.draft).toBe("Write me a reply!");

    compose.nth(0).push({ event: "done", message_id: DONE_ID });
    compose.nth(0).close();
    await within(running);
    expect(state.draft).toBe("Write me a reply!");
  });
});

// ---------------------------------------------------------------- DoD-4
describe("composeMessage — done (D14, D15)", () => {
  it("accepted, a token and done: no notification; final zone GET only after the accepted GET resolved; zone the final list; streaming cleared — DoD-4", async () => {
    const finalList = [USER_ROW, ASSISTANT_ROW];
    const compose = composeStreams();
    const zone = gatedFirstZone(finalList);
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zone.route });
    const state = seeded({ draft: DRAFT, kindOverride: "turn" });

    const running = composeMessage(state);
    await until(() => compose.streams.length === 1, "compose POST issued");
    compose.nth(0).push({ event: "accepted", message_id: ACCEPTED_ID });
    compose.nth(0).push({ event: "token", text: "Once upon a time." });
    compose.nth(0).push({ event: "done", message_id: DONE_ID });
    compose.nth(0).close();
    await until(() => backend.count(GET_ZONE) >= 1, "accepted-triggered zone GET");
    await flush();

    // The accepted GET is still pending: the terminal GET must not have been issued yet.
    expect(backend.count(GET_ZONE)).toBe(1);

    zone.open([USER_ROW]);
    await expect(within(running)).resolves.toBeUndefined();

    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(backend.count(GET_ZONE)).toBe(2);
    expect(backend.keys()[backend.keys().length - 1]).toBe(GET_ZONE);
    expect(toJS(state.zone)).toEqual(finalList);
    expect(state.zone.some((row) => row.role === "assistant")).toBe(true);
    expect(state.streamingText).toBeNull();
    expect(isStreaming(state)).toBe(false);
  });
});

// ---------------------------------------------------------------- DoD-5
describe("composeMessage — error (D14, R10, US-044.AC-1)", () => {
  it("after one token an error frame llm_unreachable: notified once with that code, zone re-read, entries untouched, streaming text null — DoD-5", async () => {
    const earlierEntry = entry("7250000000000000060", "partner", "Partner opener.");
    const finalList = [USER_ROW, PARTIAL_ROW];
    const compose = composeStreams();
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([USER_ROW], finalList) });
    const state = seeded({ entries: [earlierEntry], draft: DRAFT, kindOverride: "turn" });
    const entriesBefore = state.entries;

    const running = composeMessage(state);
    await until(() => compose.streams.length === 1, "compose POST issued");
    compose.nth(0).push({ event: "accepted", message_id: ACCEPTED_ID });
    compose.nth(0).push({ event: "token", text: "Once " });
    await flush();
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
    expect(state.streamingText).toBeNull();
  });

  it("a non-2xx compose response (409 model_not_enabled): notified with that code, the draft kept, zone re-read, streaming text null — DoD-5", async () => {
    const held = zoneRow("7250000000000000050", "assistant", "Earlier row.");
    const backend = serve({
      [POST_COMPOSE]: () => envelope("model_not_enabled", 409),
      [GET_ZONE]: zoneSequence([held]),
    });
    const state = seeded({ zone: [held], draft: DRAFT, kindOverride: "turn" });

    await expect(within(composeMessage(state))).resolves.toBeUndefined();

    expectNotifiedOnceWith("model_not_enabled");
    expect(state.draft).toBe(DRAFT);
    expect(backend.keys()[backend.keys().length - 1]).toBe(GET_ZONE);
    expect(toJS(state.zone)).toEqual([held]);
    expect(state.streamingText).toBeNull();
    expect(isStreaming(state)).toBe(false);
  });
});

// ---------------------------------------------------------------- DoD-6
describe("composeMessage — unexpected end (D14, llm-and-streaming termination table)", () => {
  it("a body ending after one token with no terminal frame notifies llm_unreachable once, then re-reads the zone and clears the streaming text — DoD-6", async () => {
    const compose = composeStreams();
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([PARTIAL_ROW]) });
    const state = seeded({ draft: DRAFT, kindOverride: "turn" });
    let zoneGetsAtNotify = -1;
    notifyFailureSpy.mockImplementation(() => {
      zoneGetsAtNotify = backend.count(GET_ZONE);
    });

    const running = composeMessage(state);
    await until(() => compose.streams.length === 1, "compose POST issued");
    compose.nth(0).push({ event: "token", text: "Once " });
    await flush();
    compose.nth(0).close();
    await expect(within(running)).resolves.toBeUndefined();

    expectNotifiedOnceWith("llm_unreachable");
    // Notified first (no accepted, so no zone GET yet), then the zone is re-read.
    expect(zoneGetsAtNotify).toBe(0);
    expect(backend.count(GET_ZONE)).toBe(1);
    expect(backend.keys()[backend.keys().length - 1]).toBe(GET_ZONE);
    expect(toJS(state.zone)).toEqual([PARTIAL_ROW]);
    expect(state.streamingText).toBeNull();
  });
});

// ---------------------------------------------------------------- DoD-7
describe("composeMessage — user stop (US-132.AC-1, US-132.AC-2, D13, D14)", () => {
  async function stoppedMidBody() {
    const compose = composeStreams();
    const finalList = [USER_ROW, PARTIAL_ROW];
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([USER_ROW], finalList) });
    const state = seeded({ draft: DRAFT, busy: false, kindOverride: "turn" });
    const seenBusy: boolean[] = [];
    const dispose = autorun(() => {
      seenBusy.push(state.busy);
    });

    const running = composeMessage(state);
    await until(() => compose.streams.length === 1, "compose POST issued");
    compose.nth(0).push({ event: "accepted", message_id: ACCEPTED_ID });
    compose.nth(0).push({ event: "token", text: "Once " });
    await until(() => state.streamingText === "Once ", "one token received");

    stopCompose(state);
    await expect(within(running)).resolves.toBeUndefined();
    dispose();
    return { compose, backend, state, finalList, seenBusy };
  }

  it("notifyFailure is never called — DoD-7", async () => {
    await stoppedMidBody();
    await flush();

    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("the zone is re-read and becomes the served list including the persisted partial assistant row — DoD-7", async () => {
    const { backend, state, finalList } = await stoppedMidBody();

    expect(backend.keys()[backend.keys().length - 1]).toBe(GET_ZONE);
    expect(backend.count(GET_ZONE)).toBe(2);
    expect(toJS(state.zone)).toEqual(finalList);
    expect(state.zone.some((row) => row.id === PARTIAL_ROW.id && row.role === "assistant")).toBe(true);
  });

  it("the streaming text and handle are null and isStreaming is false — DoD-7", async () => {
    const { state } = await stoppedMidBody();

    expect(state.streamingText).toBeNull();
    expect(state.composeHandle).toBeNull();
    expect(isStreaming(state)).toBe(false);
  });

  it("busy is unchanged, canSend is true again for a non-blank draft, and a second composeMessage can start — DoD-7", async () => {
    const { compose, backend, state, seenBusy } = await stoppedMidBody();

    expect(seenBusy.every((b) => !b)).toBe(true);
    expect(state.busy).toBe(false);

    runInAction(() => {
      state.draft = "Another line";
    });
    expect(canSend(state)).toBe(true);

    const second = composeMessage(state);
    await until(() => compose.streams.length === 2, "second compose POST issued");
    expect(backend.count(POST_COMPOSE)).toBe(2);
    const secondRequest = backend.calls.filter((c) => keyOf(c) === POST_COMPOSE)[1];
    expect(secondRequest?.rawBody).toBe('{"text":"Another line"}');
    await until(() => isStreaming(state), "second compose streaming");

    compose.nth(1).push({ event: "accepted", message_id: "7250000000000000102" });
    compose.nth(1).push({ event: "done", message_id: "7250000000000000103" });
    compose.nth(1).close();
    await expect(within(second)).resolves.toBeUndefined();
  });
});

// ---------------------------------------------------------------- DoD-8
describe("composeMessage — unmount (D12, US-132.AC-2)", () => {
  it("a mount abort mid-body aborts the compose request's own signal; afterwards no request, no notification, no zone or streaming-text write — DoD-8", async () => {
    const mount = new AbortController();
    const compose = composeStreams();
    const zone = gatedFirstZone([USER_ROW, PARTIAL_ROW]);
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zone.route });
    const state = seeded({ zone: [], draft: DRAFT, kindOverride: "turn" });

    const running = composeMessage(state, mount.signal);
    await until(() => compose.streams.length === 1, "compose POST issued");
    const composeSignal = compose.nth(0).signal;
    expect(composeSignal).toBeDefined();
    expect(composeSignal?.aborted).toBe(false);

    compose.nth(0).push({ event: "accepted", message_id: ACCEPTED_ID });
    compose.nth(0).push({ event: "token", text: "Once " });
    await until(() => state.streamingText === "Once ", "one token received");
    await until(() => backend.count(GET_ZONE) === 1, "accepted-triggered zone GET");

    const callsAtAbort = backend.calls.length;
    const zoneAtAbort = toJS(state.zone);
    const textAtAbort = state.streamingText;
    let writesAfterAbort = 0;
    const dispose = reaction(
      () => ({ zone: state.zone, text: state.streamingText }),
      () => {
        writesAfterAbort += 1;
      },
    );
    try {
      mount.abort();
      expect(composeSignal?.aborted).toBe(true);

      // The accepted re-read lands only after the unmount: it must not be written.
      zone.open([USER_ROW]);
      await expect(within(running)).resolves.toBeUndefined();
      await flush();
    } finally {
      dispose();
    }

    expect(backend.calls.length).toBe(callsAtAbort);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(writesAfterAbort).toBe(0);
    expect(toJS(state.zone)).toEqual(zoneAtAbort);
    expect(state.streamingText).toBe(textAtAbort);
  });

  it("with the mount signal already aborted, it returns with no request — DoD-8", async () => {
    const mount = new AbortController();
    mount.abort();
    const backend = serve({ [POST_COMPOSE]: composeStreams().route, [GET_ZONE]: zoneSequence([]) });
    const state = seeded({ draft: DRAFT, kindOverride: "turn" });

    await expect(within(composeMessage(state, mount.signal))).resolves.toBeUndefined();
    await flush();

    expect(backend.mock).not.toHaveBeenCalled();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(state.streamingText).toBeNull();
  });
});

// ---------------------------------------------------------------- DoD-9
describe("composeMessage — no-ops (D13)", () => {
  it.each([
    ["an empty draft", ""],
    ["a whitespace-only draft", "  \n\t "],
  ])("with %s makes no request — DoD-9", async (_label, draft) => {
    const backend = serve({ [POST_COMPOSE]: composeStreams().route, [GET_ZONE]: zoneSequence([]) });
    const state = seeded({ draft, kindOverride: "turn" });

    await expect(within(composeMessage(state))).resolves.toBeUndefined();
    await flush();

    expect(backend.mock).not.toHaveBeenCalled();
    expect(state.streamingText).toBeNull();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("while already streaming (streaming text and handle set) makes no request — DoD-9", async () => {
    const backend = serve({ [POST_COMPOSE]: composeStreams().route, [GET_ZONE]: zoneSequence([]) });
    const state = seeded({ draft: DRAFT, kindOverride: "turn" });
    const handle: ComposeHandle = { controller: new AbortController(), woundDown: Promise.resolve() };
    runInAction(() => {
      state.streamingText = "Partial";
      state.composeHandle = handle;
    });

    await expect(within(composeMessage(state))).resolves.toBeUndefined();
    await flush();

    expect(backend.mock).not.toHaveBeenCalled();
    expect(state.streamingText).toBe("Partial");
    expect(state.composeHandle).toBe(handle);
    expect(handle.controller.signal.aborted).toBe(false);
  });

  it("a second call while a real compose is in flight issues no second compose request — DoD-9", async () => {
    const compose = composeStreams();
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([USER_ROW], [USER_ROW, ASSISTANT_ROW]) });
    const state = seeded({ draft: DRAFT, kindOverride: "turn" });

    const running = composeMessage(state);
    await until(() => compose.streams.length === 1, "compose POST issued");
    await until(() => isStreaming(state), "streaming");
    runInAction(() => {
      state.draft = "Something else";
    });
    const callsBefore = backend.calls.length;

    await expect(within(composeMessage(state))).resolves.toBeUndefined();
    await flush();

    expect(backend.calls.length).toBe(callsBefore);
    expect(backend.count(POST_COMPOSE)).toBe(1);

    compose.nth(0).push({ event: "accepted", message_id: ACCEPTED_ID });
    compose.nth(0).push({ event: "done", message_id: DONE_ID });
    compose.nth(0).close();
    await within(running);
  });
});

// ---------------------------------------------------------------- DoD-10
describe("settleComposer — Settle mid-stream (D16)", () => {
  it("stops the compose, waits for its post-stop zone GET, then POSTs settle and re-reads both; no notification; ends not streaming, not busy, lists the settle's re-reads — DoD-10", async () => {
    const settledEntry = entry("7250000000000000990", "turn", DRAFT);
    const compose = composeStreams();
    const backend = serve({
      [POST_COMPOSE]: compose.route,
      // accepted re-read, the compose's post-stop re-read, the settle's re-read
      [GET_ZONE]: zoneSequence([USER_ROW], [USER_ROW, PARTIAL_ROW], []),
      [POST_SETTLE]: () => jsonResponse(SETTLE_RESULT, 200),
      [GET_ENTRIES]: () => entriesJson([settledEntry]),
    });
    const state = seeded({ entries: [], zone: [], draft: DRAFT, busy: false, kindOverride: "turn" });

    const running = composeMessage(state);
    await until(() => compose.streams.length === 1, "compose POST issued");
    compose.nth(0).push({ event: "accepted", message_id: ACCEPTED_ID });
    compose.nth(0).push({ event: "token", text: "Once " });
    await until(() => state.streamingText === "Once ", "one token received");
    await until(() => state.zone.length === 1, "zone holds one row");

    expect(isStreaming(state)).toBe(true);
    expect(canSettle(state)).toBe(true);

    const handle = state.composeHandle;
    expect(handle).not.toBeNull();
    const composeSignal = compose.nth(0).signal;
    const callsAtSettle = backend.calls.length;
    expect(backend.keys()).toEqual([POST_COMPOSE, GET_ZONE]);

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
describe("settleComposer — no compose in flight is unchanged (D16)", () => {
  it("with draft text issues exactly POST zone/messages, POST settle, then both GETs — no extra GET — DoD-11", async () => {
    const appended = zoneRow("7250000000000000201", "user", "My turn text");
    const settledEntry = entry("7250000000000000990", "turn", "My turn text");
    const backend = serve({
      [POST_ZONE_MESSAGES]: () => jsonResponse(appended, 201),
      [POST_SETTLE]: () => jsonResponse(SETTLE_RESULT, 200),
      [GET_ENTRIES]: () => entriesJson([settledEntry]),
      [GET_ZONE]: zoneSequence([]),
    });
    const state = seeded({ draft: "My turn text", kindOverride: "turn" });
    expect(state.composeHandle).toBeNull();

    await expect(within(settleComposer(state))).resolves.toBeUndefined();

    const keys = backend.keys();
    expect(keys).toHaveLength(4);
    expect(keys.slice(0, 2)).toEqual([POST_ZONE_MESSAGES, POST_SETTLE]);
    expect(keys.slice(2).sort()).toEqual([GET_ENTRIES, GET_ZONE].sort());
    expect(state.composeHandle).toBeNull();
    expect(state.streamingText).toBeNull();
    expect(state.busy).toBe(false);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("with a blank draft and one zone row issues exactly POST settle, then both GETs — no extra GET — DoD-11", async () => {
    const row = zoneRow("7250000000000000202", "user", "The only zone row.");
    const settledEntry = entry("7250000000000000990", "turn", "The only zone row.");
    const backend = serve({
      [POST_SETTLE]: () => jsonResponse(SETTLE_RESULT, 200),
      [GET_ENTRIES]: () => entriesJson([settledEntry]),
      [GET_ZONE]: zoneSequence([]),
    });
    const state = seeded({ zone: [row], draft: "", kindOverride: "turn" });

    await expect(within(settleComposer(state))).resolves.toBeUndefined();

    const keys = backend.keys();
    expect(keys).toHaveLength(3);
    expect(keys[0]).toBe(POST_SETTLE);
    expect(keys.slice(1).sort()).toEqual([GET_ENTRIES, GET_ZONE].sort());
    expect(state.composeHandle).toBeNull();
    expect(toJS(state.entries)).toEqual([settledEntry]);
    expect(toJS(state.zone)).toEqual([]);
    expect(state.busy).toBe(false);
  });
});
