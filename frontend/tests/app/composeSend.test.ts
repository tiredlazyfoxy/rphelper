// Feature 021, step 007 — Send on *my turn* composes; `composeZone` text becomes optional
// (docs/plans/021.compose-loop-and-tools/007.send-to-compose.md), DoD-1..DoD-6 (DoD-7 is the
// amendment of 013's tests in streamMutations.test.ts / Composer.test.tsx; DoD-8 is manual/live).
//
// Expected values come from the step's Interface intent and Definition of done, context.md D2 and
// D12, and 019 step 005's compose-effect contract that `sendComposer` now delegates to:
//   - `composeZone(id, text, cb, signal)` POSTs /api/sessions/<id>/zone/compose with body exactly
//     {"text": <text>}; with no text (`undefined`, per the frozen signature) the body is exactly {};
//   - `sendComposer` on *my turn* issues one POST to …/zone/compose with {"text": <draft>} and never
//     touches …/zone/messages; it never sets `busy` (019 D13), so Settle stays available mid-stream;
//   - a typed `error` frame after `accepted` reaches `notifyFailure` once as an `ApiError` with the
//     frame's code and message; the zone is re-read; `entries` untouched; nothing optimistic;
//   - on `done` nothing is notified and the zone is the final served list;
//   - on *partner* Send still files POST …/entries {"kind":"partner","text"} and never composes.
// Streamed bodies are Responses over a ReadableStream of TextEncoder chunks the test drives; the
// stub honours the request's signal. Every await on the code under test is bounded.
import { autorun, runInAction, toJS } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { composeZone, type Message, type MessageKind, type MessageRole } from "../../src/app/streamApi";
import { StreamState, canSettle, isStreaming, sendComposer } from "../../src/app/streamState";
import { ApiError } from "../../src/shared/apiError";
import type { SseProgressFrame } from "../../src/shared/sse";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; rawBody: unknown; signal: AbortSignal | undefined };
type Route = (request: Seen) => Response | Promise<Response>;

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "s1";
const COMPOSE_PATH = `/api/sessions/${SESSION_ID}/zone/compose`;
const ZONE_PATH = `/api/sessions/${SESSION_ID}/zone`;
const ZONE_MESSAGES_PATH = `/api/sessions/${SESSION_ID}/zone/messages`;
const ENTRIES_PATH = `/api/sessions/${SESSION_ID}/entries`;

const POST_COMPOSE = `POST ${COMPOSE_PATH}`;
const POST_ZONE_MESSAGES = `POST ${ZONE_MESSAGES_PATH}`;
const GET_ZONE = `GET ${ZONE_PATH}`;
const GET_ENTRIES = `GET ${ENTRIES_PATH}`;
const POST_ENTRIES = `POST ${ENTRIES_PATH}`;

const DRAFT = "Write me a reply";
const ACCEPTED_ID = "7250000000000000101";
const DONE_ID = "7250000000000000102";
const STAMP = "2026-10-04T09:00:00.000000+00:00";

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

const EARLIER_ROW = zoneRow("7250000000000000100", "assistant", "Earlier zone row.");
/** The roleplayer's committed message, as served after `accepted`. */
const USER_ROW = zoneRow(ACCEPTED_ID, "user", DRAFT);
/** The assistant row served after `done`. */
const ASSISTANT_ROW = zoneRow(DONE_ID, "assistant", "Once upon a time.");
/** A persisted partial assistant row, served after a failed compose. */
const PARTIAL_ROW = zoneRow("7250000000000000103", "assistant", "Once ");

type Seed = { entries?: Message[]; zone?: Message[]; draft?: string; kindOverride?: "partner" | "turn" | null };

function seeded(seed: Seed = {}): StreamState {
  const state = new StreamState(SESSION_ID);
  runInAction(() => {
    if (seed.entries !== undefined) state.entries = seed.entries;
    if (seed.zone !== undefined) state.zone = seed.zone;
    if (seed.draft !== undefined) state.draft = seed.draft;
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
  const posts = (): Seen[] => calls.filter((c) => c.method === "POST");
  return { mock, calls, keys, count, posts };
}

function sseFrame(payload: unknown): string {
  return `data: ${JSON.stringify(payload)}\n\n`;
}

/** A complete streamed 200 body of the given frames. */
function sseResponse(payloads: unknown[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const payload of payloads) controller.enqueue(enc.encode(sseFrame(payload)));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

type HeldSse = {
  response: Response;
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

function rawBodyJson(raw: unknown): unknown {
  expect(typeof raw).toBe("string");
  return JSON.parse(raw as string) as unknown;
}

// ---------------------------------------------------------------- DoD-1
describe("composeZone — the text is optional (D2, D12)", () => {
  function stubCompose() {
    const mock = vi.fn<FetchFn>(() =>
      Promise.resolve(
        sseResponse([
          { event: "accepted", message_id: ACCEPTED_ID },
          { event: "done", message_id: DONE_ID },
        ]),
      ),
    );
    vi.stubGlobal("fetch", mock);
    return mock;
  }

  it('composeZone("7250000000000000042", "Hi", cb, signal) POSTs /api/sessions/7250000000000000042/zone/compose with body exactly {"text":"Hi"} — DoD-1', async () => {
    const mock = stubCompose();
    const controller = new AbortController();
    const cb = vi.fn<(frame: SseProgressFrame) => void>();

    await within(composeZone("7250000000000000042", "Hi", cb, controller.signal));

    expect(mock).toHaveBeenCalledTimes(1);
    const [input, init] = mock.mock.calls[0] ?? [];
    expect(input).toBeDefined();
    if (input === undefined) return;
    expect(requestMethod(input, init)).toBe("POST");
    expect(requestUrl(input).pathname).toBe("/api/sessions/7250000000000000042/zone/compose");
    expect(init?.body).toBe('{"text":"Hi"}');
    expect(rawBodyJson(init?.body)).toStrictEqual({ text: "Hi" });
  });

  it("composeZone with no text POSTs the same path with body exactly {} — DoD-1", async () => {
    const mock = vi.fn<FetchFn>(() =>
      Promise.resolve(
        sseResponse([
          { event: "token", text: "Again" },
          { event: "done", message_id: DONE_ID },
        ]),
      ),
    );
    vi.stubGlobal("fetch", mock);
    const controller = new AbortController();
    const cb = vi.fn<(frame: SseProgressFrame) => void>();

    const outcome = await within(composeZone("7250000000000000042", undefined, cb, controller.signal));

    expect(mock).toHaveBeenCalledTimes(1);
    const [input, init] = mock.mock.calls[0] ?? [];
    expect(input).toBeDefined();
    if (input === undefined) return;
    expect(requestMethod(input, init)).toBe("POST");
    expect(requestUrl(input).pathname).toBe("/api/sessions/7250000000000000042/zone/compose");
    expect(requestUrl(input).search).toBe("");
    expect(rawBodyJson(init?.body)).toStrictEqual({});
    expect(init?.body).toBe("{}");
    // Frame callback, signal and outcome are unchanged from the with-text call.
    expect(init?.signal).toBe(controller.signal);
    expect(outcome).toEqual({ kind: "done", messageId: DONE_ID });
    expect(cb.mock.calls.map(([seen]) => seen)).toEqual([{ event: "token", text: "Again" }]);
  });
});

// ---------------------------------------------------------------- DoD-2
describe("sendComposer on my turn composes (D12)", () => {
  it('with draft "Write me a reply" issues exactly one POST, to /api/sessions/s1/zone/compose with {"text":"Write me a reply"}, and no request to …/zone/messages — DoD-2', async () => {
    const compose = composeStreams();
    const backend = serve({
      [POST_COMPOSE]: compose.route,
      [GET_ZONE]: zoneSequence([USER_ROW], [USER_ROW, ASSISTANT_ROW]),
    });
    const state = seeded({ draft: DRAFT, kindOverride: "turn" });

    const running = sendComposer(state);
    await until(() => compose.streams.length === 1, "compose POST issued");
    compose.nth(0).push({ event: "accepted", message_id: ACCEPTED_ID });
    compose.nth(0).push({ event: "token", text: "Once upon a time." });
    compose.nth(0).push({ event: "done", message_id: DONE_ID });
    compose.nth(0).close();
    await expect(within(running)).resolves.toBeUndefined();
    await flush();

    const posts = backend.posts();
    expect(posts).toHaveLength(1);
    expect(keyOf(posts[0] as Seen)).toBe(POST_COMPOSE);
    expect(rawBodyJson(posts[0]?.rawBody)).toStrictEqual({ text: "Write me a reply" });
    expect(backend.calls.some((c) => c.path === ZONE_MESSAGES_PATH)).toBe(false);
    expect(backend.count(POST_ZONE_MESSAGES)).toBe(0);
  });
});

// ---------------------------------------------------------------- DoD-3
describe("sendComposer on my turn while the compose streams (019 D13)", () => {
  it("with a token received and the body held open: busy is false, isStreaming is true, and with a zone row canSettle is true — DoD-3", async () => {
    const compose = composeStreams();
    serve({
      [POST_COMPOSE]: compose.route,
      [GET_ZONE]: zoneSequence([EARLIER_ROW, USER_ROW], [EARLIER_ROW, USER_ROW, ASSISTANT_ROW]),
    });
    const state = seeded({ zone: [EARLIER_ROW], draft: DRAFT, kindOverride: "turn" });
    const seenBusy: boolean[] = [];
    const dispose = autorun(() => {
      seenBusy.push(state.busy);
    });
    try {
      const running = sendComposer(state);
      await until(() => compose.streams.length === 1, "compose POST issued");
      compose.nth(0).push({ event: "accepted", message_id: ACCEPTED_ID });
      compose.nth(0).push({ event: "token", text: "Once " });
      await until(() => state.streamingText === "Once ", "one token received");
      await flush();

      expect(state.busy).toBe(false);
      expect(isStreaming(state)).toBe(true);
      expect(state.zone.length).toBeGreaterThan(0);
      expect(canSettle(state)).toBe(true);

      compose.nth(0).push({ event: "done", message_id: DONE_ID });
      compose.nth(0).close();
      await expect(within(running)).resolves.toBeUndefined();
    } finally {
      dispose();
    }

    expect(seenBusy.every((b) => !b)).toBe(true);
    expect(state.busy).toBe(false);
  });
});

// ---------------------------------------------------------------- DoD-4
const FAILURE_CODES = ["llm_unreachable", "no_model_enabled", "model_not_chosen", "model_not_enabled"] as const;

describe("sendComposer on my turn — a typed error frame after accepted (US-044.AC-2, US-044.AC-4, R10)", () => {
  it.each(FAILURE_CODES)(
    "an error frame %s after accepted: notifyFailure once with an ApiError of that code and message, the zone re-read, entries untouched, zone only served rows — DoD-4",
    async (code) => {
      const earlierEntry = entry("7250000000000000060", "partner", "Partner opener.");
      const message = `Reason for ${code}.`;
      const finalList = [EARLIER_ROW, USER_ROW, PARTIAL_ROW];
      const compose = composeStreams();
      const backend = serve({
        [POST_COMPOSE]: compose.route,
        [GET_ZONE]: zoneSequence([EARLIER_ROW, USER_ROW], finalList),
      });
      const state = seeded({ entries: [earlierEntry], zone: [EARLIER_ROW], draft: DRAFT, kindOverride: "turn" });
      const entriesBefore = state.entries;
      const servedIds = new Set([EARLIER_ROW.id, USER_ROW.id, PARTIAL_ROW.id]);
      const zoneIdsSeen: string[][] = [];
      const dispose = autorun(() => {
        zoneIdsSeen.push(state.zone.map((row) => row.id));
      });
      try {
        const running = sendComposer(state);
        await until(() => compose.streams.length === 1, "compose POST issued");
        compose.nth(0).push({ event: "accepted", message_id: ACCEPTED_ID });
        await until(() => backend.count(GET_ZONE) >= 1, "zone GET after accepted");
        await flush();
        const zoneGetsBeforeError = backend.count(GET_ZONE);

        compose.nth(0).push({ event: "error", code, message, detail: {} });
        compose.nth(0).close();
        await expect(within(running)).resolves.toBeUndefined();
        await flush();

        expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
        const error = notifyFailureSpy.mock.calls[0]?.[0];
        expect(error).toBeInstanceOf(ApiError);
        expect((error as ApiError).code).toBe(code);
        expect((error as ApiError).message).toBe(message);

        expect(backend.count(GET_ZONE)).toBeGreaterThan(zoneGetsBeforeError);
        expect(backend.keys()[backend.keys().length - 1]).toBe(GET_ZONE);
        expect(toJS(state.zone)).toEqual(finalList);

        expect(state.entries).toBe(entriesBefore);
        expect(toJS(state.entries)).toEqual([earlierEntry]);
        expect(backend.count(GET_ENTRIES)).toBe(0);
        expect(backend.count(POST_ZONE_MESSAGES)).toBe(0);
      } finally {
        dispose();
      }

      for (const ids of zoneIdsSeen) {
        for (const id of ids) expect(servedIds.has(id)).toBe(true);
      }
    },
  );
});

// ---------------------------------------------------------------- DoD-5
describe("sendComposer on my turn — done (D12, never optimistic)", () => {
  it("on done notifyFailure is not called and the zone equals the final served list — DoD-5", async () => {
    const finalList = [EARLIER_ROW, USER_ROW, ASSISTANT_ROW];
    const compose = composeStreams();
    const backend = serve({
      [POST_COMPOSE]: compose.route,
      [GET_ZONE]: zoneSequence([EARLIER_ROW, USER_ROW], finalList),
    });
    const state = seeded({ zone: [EARLIER_ROW], draft: DRAFT, kindOverride: "turn" });
    const servedIds = new Set(finalList.map((row) => row.id));
    const zoneIdsSeen: string[][] = [];
    const dispose = autorun(() => {
      zoneIdsSeen.push(state.zone.map((row) => row.id));
    });
    try {
      const running = sendComposer(state);
      await until(() => compose.streams.length === 1, "compose POST issued");
      compose.nth(0).push({ event: "accepted", message_id: ACCEPTED_ID });
      compose.nth(0).push({ event: "token", text: "Once upon a time." });
      compose.nth(0).push({ event: "done", message_id: DONE_ID });
      compose.nth(0).close();
      await expect(within(running)).resolves.toBeUndefined();
      await flush();
    } finally {
      dispose();
    }

    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(backend.keys()[backend.keys().length - 1]).toBe(GET_ZONE);
    expect(toJS(state.zone)).toEqual(finalList);
    for (const ids of zoneIdsSeen) {
      for (const id of ids) expect(servedIds.has(id)).toBe(true);
    }
  });
});

// ---------------------------------------------------------------- DoD-6
describe("sendComposer on partner is unchanged (D12)", () => {
  it('Send POSTs /api/sessions/s1/entries with {"kind":"partner","text":…} and never …/zone/compose — DoD-6', async () => {
    const filed = entry("7250000000000000301", "partner", "Partner says hi.");
    const backend = serve({
      [POST_ENTRIES]: () => jsonResponse(filed, 201),
      [GET_ENTRIES]: () => jsonResponse({ entries: [filed] }, 200),
      [POST_COMPOSE]: composeStreams().route,
    });
    const state = seeded({ draft: "Partner says hi.", kindOverride: "partner" });

    await expect(within(sendComposer(state))).resolves.toBeUndefined();
    await flush();

    const posts = backend.posts();
    expect(posts).toHaveLength(1);
    expect(keyOf(posts[0] as Seen)).toBe(POST_ENTRIES);
    expect(rawBodyJson(posts[0]?.rawBody)).toStrictEqual({ kind: "partner", text: "Partner says hi." });
    expect(backend.count(POST_COMPOSE)).toBe(0);
    expect(backend.calls.some((c) => c.path === COMPOSE_PATH)).toBe(false);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});
