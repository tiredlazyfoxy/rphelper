// Fast feature 004 — character-page-first-reply: the store-level first-reply compose
// (DoD-1..DoD-5) (docs/plans/fast/004.character-page-first-reply/plan.md).
//
// Expected values come from the plan's Interface intent ("composeFirstReply") and Definition of
// done, plus context.md D3 and D5:
//   - `composeFirstReply(state, signal)` starts one textless compose — one POST
//     /api/sessions/<id>/zone/compose with JSON body exactly {} — only when the state is ready,
//     not streaming or busy, the zone's last non-tool row has role "user", the signal is not
//     aborted, and no first-reply compose has been started on this StreamState before;
//   - otherwise it is a no-op and makes no request;
//   - it never rejects; failure goes through notifyFailure and the zone is re-read at the end;
//   - the once-flag lives on the StreamState instance, so a fresh StreamState is unaffected.
// Streamed bodies are a Response over a ReadableStream of TextEncoder chunks (the repo's
// streamCompose / streamRegenerate idiom); every await is bounded.
import { runInAction, toJS } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Message, MessageRole } from "../../src/app/streamApi";
import { StreamState, composeFirstReply, isStreaming, type ComposeHandle } from "../../src/app/streamState";
import { ApiError } from "../../src/shared/apiError";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; rawBody: unknown; signal: AbortSignal | undefined };
type Route = (request: Seen) => Response | Promise<Response>;

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "7270000000000000101";
const OTHER_SESSION_ID = "7270000000000000102";

function composePath(sessionId: string): string {
  return `/api/sessions/${sessionId}/zone/compose`;
}

function zonePath(sessionId: string): string {
  return `/api/sessions/${sessionId}/zone`;
}

const POST_COMPOSE = `POST ${composePath(SESSION_ID)}`;
const GET_ZONE = `GET ${zonePath(SESSION_ID)}`;
const OTHER_POST_COMPOSE = `POST ${composePath(OTHER_SESSION_ID)}`;
const OTHER_GET_ZONE = `GET ${zonePath(OTHER_SESSION_ID)}`;

const STAMP = "2026-10-07T09:00:00.000000+00:00";
const DONE_ID = "7280000000000000199";

const enc = new TextEncoder();

let nextId = 500;
function freshId(): string {
  nextId += 1;
  return `7280000000000000${String(nextId).padStart(3, "0")}`;
}

function zoneRow(role: MessageRole, text: string, id = freshId(), sessionId = SESSION_ID): Message {
  return { id, session_id: sessionId, role, kind: null, text, settled_at: null, created_at: STAMP, updated_at: STAMP };
}

function toolRow(text = "lookup", id = freshId()): Message {
  return { ...zoneRow("tool", text, id), tool_name: "memo_search", tool_status: "ok", tool_args: {} };
}

/** The opening message the character page seeded: the zone's only row. */
const OPENING_ROW = zoneRow("user", "The lighthouse keeper waits at the door.", "7280000000000000101");
const ASSISTANT_ROW = zoneRow("assistant", "Once upon a time.", DONE_ID);

type Seed = { zone?: Message[]; busy?: boolean; ready?: boolean; sessionId?: string };

function seeded(seed: Seed = {}): StreamState {
  const state = new StreamState(seed.sessionId ?? SESSION_ID);
  runInAction(() => {
    state.entries = [];
    if (seed.zone !== undefined) state.zone = seed.zone;
    if (seed.busy !== undefined) state.busy = seed.busy;
    if (seed.ready !== false) state.status = "ready";
  });
  return state;
}

function markStreaming(state: StreamState, text: string): ComposeHandle {
  const handle: ComposeHandle = { controller: new AbortController(), woundDown: Promise.resolve() };
  runInAction(() => {
    state.streamingText = text;
    state.composeHandle = handle;
  });
  return handle;
}

function liveSignal(): AbortSignal {
  return new AbortController().signal;
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
  return jsonResponse({ error: { code, message: "No model is enabled.", detail: {} } }, status);
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

/** Finishes compose stream #i with a done frame. */
function finish(compose: ReturnType<typeof composeStreams>, i: number): void {
  compose.nth(i).push({ event: "done", message_id: DONE_ID });
  compose.nth(i).close();
}

// ---------------------------------------------------------------- DoD-1
describe("composeFirstReply — one textless compose on the seeded zone (US-117.AC-3, D3)", () => {
  it("issues exactly one POST …/zone/compose with body {}, streams the token text as the live reply, and after done re-reads the zone holding the assistant row — DoD-1", async () => {
    const finalList = [OPENING_ROW, ASSISTANT_ROW];
    const compose = composeStreams();
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence(finalList) });
    const state = seeded({ zone: [OPENING_ROW] });

    expect(isStreaming(state)).toBe(false);
    const running = composeFirstReply(state, liveSignal());
    await until(() => compose.streams.length === 1, "compose POST issued");
    await until(() => isStreaming(state), "streaming while the body is held open");

    expect(backend.count(POST_COMPOSE)).toBe(1);
    const request = backend.calls.find((c) => keyOf(c) === POST_COMPOSE);
    expect(rawBodyJson(request?.rawBody)).toStrictEqual({});

    compose.nth(0).push({ event: "token", text: "Once " });
    compose.nth(0).push({ event: "token", text: "upon" });
    await until(() => state.streamingText === "Once upon", "tokens appended to the live reply");
    expect(state.streamingText).toBe("Once upon");
    const zoneGetsBeforeDone = backend.count(GET_ZONE);

    finish(compose, 0);
    await expect(within(running)).resolves.toBeUndefined();

    expect(backend.count(GET_ZONE)).toBeGreaterThan(zoneGetsBeforeDone);
    expect(backend.keys()[backend.keys().length - 1]).toBe(GET_ZONE);
    expect(toJS(state.zone)).toEqual(finalList);
    expect(state.streamingText).toBeNull();
    expect(isStreaming(state)).toBe(false);
    expect(backend.count(POST_COMPOSE)).toBe(1);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------- DoD-2
describe("composeFirstReply — at most once per StreamState (D3)", () => {
  it("a second call while the first is streaming issues no further compose request — DoD-2", async () => {
    const compose = composeStreams();
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([OPENING_ROW, ASSISTANT_ROW]) });
    const state = seeded({ zone: [OPENING_ROW] });

    const running = composeFirstReply(state, liveSignal());
    await until(() => compose.streams.length === 1, "compose POST issued");
    await until(() => isStreaming(state), "streaming");
    const callsBefore = backend.calls.length;

    await expect(within(composeFirstReply(state, liveSignal()))).resolves.toBeUndefined();
    await flush();
    expect(backend.calls.length).toBe(callsBefore);
    expect(backend.count(POST_COMPOSE)).toBe(1);

    finish(compose, 0);
    await within(running);
    expect(backend.count(POST_COMPOSE)).toBe(1);
  });

  it("a second call after the first has finished issues no further compose request — DoD-2", async () => {
    const compose = composeStreams();
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([OPENING_ROW, ASSISTANT_ROW]) });
    const state = seeded({ zone: [OPENING_ROW] });

    const running = composeFirstReply(state, liveSignal());
    await until(() => compose.streams.length === 1, "compose POST issued");
    finish(compose, 0);
    await within(running);
    expect(isStreaming(state)).toBe(false);
    const callsBefore = backend.calls.length;

    await expect(within(composeFirstReply(state, liveSignal()))).resolves.toBeUndefined();
    await flush();

    expect(backend.calls.length).toBe(callsBefore);
    expect(backend.count(POST_COMPOSE)).toBe(1);
  });

  it("a second call after a finished first compose issues no request even when the zone still ends with the user's row — DoD-2", async () => {
    // The re-read after the first compose serves the opening row alone, so only the once-flag
    // (not the last-row rule) can keep the second call from composing.
    const backend = serve({
      [POST_COMPOSE]: () => envelope("no_model_enabled", 409),
      [GET_ZONE]: zoneSequence([OPENING_ROW]),
    });
    const state = seeded({ zone: [OPENING_ROW] });

    await within(composeFirstReply(state, liveSignal()));
    expect(backend.count(POST_COMPOSE)).toBe(1);
    expect(toJS(state.zone)).toEqual([OPENING_ROW]);
    expect(isStreaming(state)).toBe(false);
    const callsBefore = backend.calls.length;

    await expect(within(composeFirstReply(state, liveSignal()))).resolves.toBeUndefined();
    await flush();

    expect(backend.calls.length).toBe(callsBefore);
    expect(backend.count(POST_COMPOSE)).toBe(1);
  });

  it("the once-flag is per instance: a fresh StreamState for another session still composes once — DoD-2", async () => {
    const backend = serve({
      [POST_COMPOSE]: () => envelope("no_model_enabled", 409),
      [GET_ZONE]: zoneSequence([OPENING_ROW]),
      [OTHER_POST_COMPOSE]: () => envelope("no_model_enabled", 409),
      [OTHER_GET_ZONE]: zoneSequence([zoneRow("user", "Another opening.", "7280000000000000102", OTHER_SESSION_ID)]),
    });
    const first = seeded({ zone: [OPENING_ROW] });
    await within(composeFirstReply(first, liveSignal()));
    expect(backend.count(POST_COMPOSE)).toBe(1);

    const otherOpening = zoneRow("user", "Another opening.", "7280000000000000102", OTHER_SESSION_ID);
    const second = seeded({ zone: [otherOpening], sessionId: OTHER_SESSION_ID });
    await within(composeFirstReply(second, liveSignal()));

    expect(backend.count(OTHER_POST_COMPOSE)).toBe(1);
    expect(backend.count(POST_COMPOSE)).toBe(1);
  });
});

// ---------------------------------------------------------------- DoD-3
describe("composeFirstReply — the zone's last non-tool row decides (D3)", () => {
  it.each([
    ["[user, assistant]", (): Message[] => [OPENING_ROW, ASSISTANT_ROW]],
    ["[user, assistant, tool]", (): Message[] => [OPENING_ROW, ASSISTANT_ROW, toolRow()]],
    ["[assistant]", (): Message[] => [ASSISTANT_ROW]],
  ])("issues no compose request when the zone is %s (last non-tool row is the assistant's) — DoD-3", async (_label, zone) => {
    const backend = serve({ [POST_COMPOSE]: composeStreams().route, [GET_ZONE]: zoneSequence(zone()) });
    const state = seeded({ zone: zone() });
    const zoneBefore = toJS(state.zone);

    await expect(within(composeFirstReply(state, liveSignal()))).resolves.toBeUndefined();
    await flush();

    expect(backend.count(POST_COMPOSE)).toBe(0);
    expect(backend.mock).not.toHaveBeenCalled();
    expect(toJS(state.zone)).toEqual(zoneBefore);
    expect(state.streamingText).toBeNull();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it.each([
    ["[user, tool]", (): Message[] => [OPENING_ROW, toolRow()]],
    ["[user, tool, tool]", (): Message[] => [OPENING_ROW, toolRow(), toolRow("lookup again")]],
  ])("trailing tool rows after the user's row do not block it: zone %s issues one compose with body {} — DoD-3", async (_label, zone) => {
    const compose = composeStreams();
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([OPENING_ROW, ASSISTANT_ROW]) });
    const state = seeded({ zone: zone() });

    const running = composeFirstReply(state, liveSignal());
    await until(() => compose.streams.length === 1, "compose POST issued");
    expect(backend.count(POST_COMPOSE)).toBe(1);
    const request = backend.calls.find((c) => keyOf(c) === POST_COMPOSE);
    expect(rawBodyJson(request?.rawBody)).toStrictEqual({});

    finish(compose, 0);
    await expect(within(running)).resolves.toBeUndefined();
    expect(backend.count(POST_COMPOSE)).toBe(1);
  });

  it.each([
    ["the zone is empty", (): StreamState => seeded({ zone: [] })],
    ["the zone holds only tool rows", (): StreamState => seeded({ zone: [toolRow(), toolRow("lookup again")] })],
    ["the state is busy", (): StreamState => seeded({ zone: [OPENING_ROW], busy: true })],
    ["the state is not ready", (): StreamState => seeded({ zone: [OPENING_ROW], ready: false })],
  ])("issues no compose request when %s (Interface intent gates) — DoD-3", async (_label, make) => {
    const backend = serve({ [POST_COMPOSE]: composeStreams().route, [GET_ZONE]: zoneSequence([OPENING_ROW]) });
    const state = make();

    await expect(within(composeFirstReply(state, liveSignal()))).resolves.toBeUndefined();
    await flush();

    expect(backend.count(POST_COMPOSE)).toBe(0);
    expect(state.streamingText).toBeNull();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("issues no compose request while another compose is streaming, and leaves its streaming text and handle alone (Interface intent gates) — DoD-3", async () => {
    const backend = serve({ [POST_COMPOSE]: composeStreams().route, [GET_ZONE]: zoneSequence([OPENING_ROW]) });
    const state = seeded({ zone: [OPENING_ROW] });
    const handle = markStreaming(state, "Partial");

    await expect(within(composeFirstReply(state, liveSignal()))).resolves.toBeUndefined();
    await flush();

    expect(backend.count(POST_COMPOSE)).toBe(0);
    expect(state.streamingText).toBe("Partial");
    expect(state.composeHandle).toBe(handle);
    expect(handle.controller.signal.aborted).toBe(false);
  });
});

// ---------------------------------------------------------------- DoD-4
describe("composeFirstReply — an aborted signal (D3)", () => {
  it("an already-aborted signal causes no compose request — DoD-4", async () => {
    const backend = serve({ [POST_COMPOSE]: composeStreams().route, [GET_ZONE]: zoneSequence([OPENING_ROW]) });
    const state = seeded({ zone: [OPENING_ROW] });
    const controller = new AbortController();
    controller.abort();

    await expect(within(composeFirstReply(state, controller.signal))).resolves.toBeUndefined();
    await flush();

    expect(backend.count(POST_COMPOSE)).toBe(0);
    expect(state.streamingText).toBeNull();
    expect(toJS(state.zone)).toEqual([OPENING_ROW]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("a call that did not start (aborted signal) is a no-op: a later call with a live signal still composes once — DoD-4", async () => {
    const compose = composeStreams();
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([OPENING_ROW, ASSISTANT_ROW]) });
    const state = seeded({ zone: [OPENING_ROW] });
    const aborted = new AbortController();
    aborted.abort();

    await within(composeFirstReply(state, aborted.signal));
    await flush();
    expect(backend.count(POST_COMPOSE)).toBe(0);

    const running = composeFirstReply(state, liveSignal());
    await until(() => compose.streams.length === 1, "compose POST issued");
    expect(backend.count(POST_COMPOSE)).toBe(1);
    finish(compose, 0);
    await expect(within(running)).resolves.toBeUndefined();
  });
});

// ---------------------------------------------------------------- DoD-5
describe("composeFirstReply — a refused compose (D5, R10)", () => {
  it("a 409 no_model_enabled answer does not reject, notifies once with that code, ends not streaming, and the opening row is still in the re-read zone — DoD-5", async () => {
    const backend = serve({
      [POST_COMPOSE]: () => envelope("no_model_enabled", 409),
      [GET_ZONE]: zoneSequence([OPENING_ROW]),
    });
    const state = seeded({ zone: [OPENING_ROW] });

    await expect(within(composeFirstReply(state, liveSignal()))).resolves.toBeUndefined();

    expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
    const error = notifyFailureSpy.mock.calls[0]?.[0];
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("no_model_enabled");

    expect(backend.count(POST_COMPOSE)).toBe(1);
    expect(backend.count(GET_ZONE)).toBeGreaterThanOrEqual(1);
    expect(backend.keys()[backend.keys().length - 1]).toBe(GET_ZONE);
    expect(isStreaming(state)).toBe(false);
    expect(state.streamingText).toBeNull();
    expect(toJS(state.zone)).toEqual([OPENING_ROW]);
  });
});
