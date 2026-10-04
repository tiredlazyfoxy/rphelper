// Feature 022, step 005 — live tool calls fed by the compose run's tool frames (DoD-1..DoD-5)
// (docs/plans/022.discussion-ui/005.live-tools-and-regenerate.md).
//
// Expected values come from the step's Interface intent and Definition of done, context.md D7
// (supersedes 019 D18) and 005.context.md ("The atomic clear"):
//   - a fresh `StreamState` has an empty `liveTools` list;
//   - tool_start appends {callId, tool, args, "running", null}; tool_result sets that call "ok"
//     with the frame's summary; tool_fail sets it "failed" with "The tool failed."; a result or
//     failure for an unknown call id is ignored; arrival order is kept;
//   - tool frames never touch `zone`;
//   - the list is emptied in the same action that writes the terminal re-read and clears the
//     streaming text, so the served tool rows and the live list are never seen together;
//   - a user stop empties it with the streaming text and notifies nothing; nothing is written
//     after a mount abort.
// The streamed body is a Response over a ReadableStream the test drives with TextEncoder chunks;
// an abort of the request's signal errors it. Every await is bounded.
import { autorun, reaction, toJS, runInAction } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Message, MessageRole } from "../../src/app/streamApi";
import {
  StreamState,
  composeMessage,
  isStreaming,
  stopCompose,
  type LiveToolCall,
} from "../../src/app/streamState";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; rawBody: unknown; signal: AbortSignal | undefined };
type Route = (request: Seen) => Response | Promise<Response>;

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "s1";
const COMPOSE_PATH = `/api/sessions/${SESSION_ID}/zone/compose`;
const ZONE_PATH = `/api/sessions/${SESSION_ID}/zone`;
const POST_COMPOSE = `POST ${COMPOSE_PATH}`;
const GET_ZONE = `GET ${ZONE_PATH}`;

const DRAFT = "Find it";
const ACCEPTED_ID = "7250000000000000042";
const DONE_ID = "7250000000000000045";
const STAMP = "2026-10-04T09:00:00.000000+00:00";

const enc = new TextEncoder();

function zoneRow(id: string, role: MessageRole, text: string, extra: Partial<Message> = {}): Message {
  return {
    id,
    session_id: SESSION_ID,
    role,
    kind: null,
    text,
    settled_at: null,
    created_at: STAMP,
    updated_at: STAMP,
    ...extra,
  };
}

const USER_ROW = zoneRow(ACCEPTED_ID, "user", DRAFT);
const TOOL_OK_ROW = zoneRow("7250000000000000043", "tool", "Found 2 memos.", {
  tool_name: "memo_search",
  tool_status: "ok",
  tool_args: { query: "lighthouse" },
});
const TOOL_FAILED_ROW = zoneRow("7250000000000000044", "tool", "The tool failed.", {
  tool_name: "memo_search",
  tool_status: "failed",
  tool_args: {},
});
const ASSISTANT_ROW = zoneRow(DONE_ID, "assistant", "The lighthouse keeper.");
const FINAL_LIST = [USER_ROW, TOOL_OK_ROW, TOOL_FAILED_ROW, ASSISTANT_ROW];

const C1_START = { event: "tool_start", tool: "memo_search", call_id: "c1", args: { query: "lighthouse" } };
const C1_RESULT = { event: "tool_result", tool: "memo_search", call_id: "c1", summary: "Found 2 memos." };
const C2_START = { event: "tool_start", tool: "memo_search", call_id: "c2", args: {} };
const C2_FAIL = { event: "tool_fail", tool: "memo_search", call_id: "c2", code: "tool_failed" };

const C1_RUNNING: LiveToolCall = {
  callId: "c1",
  tool: "memo_search",
  args: { query: "lighthouse" },
  status: "running",
  summary: null,
};
const C1_OK: LiveToolCall = { ...C1_RUNNING, status: "ok", summary: "Found 2 memos." };
const C2_FAILED: LiveToolCall = {
  callId: "c2",
  tool: "memo_search",
  args: {},
  status: "failed",
  summary: "The tool failed.",
};

function seeded(draft: string): StreamState {
  const state = new StreamState(SESSION_ID);
  runInAction(() => {
    state.entries = [];
    state.zone = [];
    state.draft = draft;
    state.kindOverride = "turn";
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

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

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

const live = (state: StreamState): LiveToolCall[] => toJS(state.liveTools);

/** Starts a compose of "Find it", pushes `accepted` and waits for its zone re-read to land. */
async function startedCompose(zone: Route, signal?: AbortSignal) {
  const compose = composeStreams();
  const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zone });
  const state = seeded(DRAFT);
  const running = composeMessage(state, signal);
  await until(() => compose.streams.length === 1, "compose POST issued");
  compose.nth(0).push({ event: "accepted", message_id: ACCEPTED_ID });
  return { compose, backend, state, running, body: compose.nth(0) };
}

// ---------------------------------------------------------------- DoD-1
describe("a fresh StreamState (D7)", () => {
  it("has an empty live tool list — DoD-1", () => {
    const state = new StreamState(SESSION_ID);
    expect(Array.isArray(state.liveTools)).toBe(true);
    expect(live(state)).toEqual([]);
  });
});

// ---------------------------------------------------------------- DoD-2
describe("composeMessage — tool_start (D7, US-114.AC-1)", () => {
  it('a held-open tool_start for c1 gives exactly one running entry: c1, memo_search, {"query":"lighthouse"}, summary null — DoD-2', async () => {
    const { backend, state, running, body } = await startedCompose(zoneSequence([USER_ROW], FINAL_LIST));
    body.push(C1_START);
    await until(() => state.liveTools.length > 0, "a live tool call appears");
    await flush();

    expect(live(state)).toEqual([C1_RUNNING]);
    expect(isStreaming(state)).toBe(true);

    body.push({ event: "done", message_id: DONE_ID });
    body.close();
    await within(running);
    expect(backend.count(POST_COMPOSE)).toBe(1);
  });

  it("zone contains no row the server did not serve while a tool call is live — DoD-2", async () => {
    const zone = zoneSequence([USER_ROW], FINAL_LIST);
    const compose = composeStreams();
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zone });
    const state = seeded(DRAFT);
    const servedIds = new Set(FINAL_LIST.map((row) => row.id));
    const zoneIdsSeen: string[][] = [];
    const dispose = autorun(() => {
      zoneIdsSeen.push(state.zone.map((row) => row.id));
    });
    try {
      const running = composeMessage(state);
      await until(() => compose.streams.length === 1, "compose POST issued");
      compose.nth(0).push({ event: "accepted", message_id: ACCEPTED_ID });
      await until(() => backend.count(GET_ZONE) >= 1 && state.zone.length === 1, "accepted re-read landed");
      compose.nth(0).push(C1_START);
      await until(() => state.liveTools.length === 1, "c1 live");
      await flush();

      // Held open: the zone is exactly the served list; the tool call lives elsewhere.
      expect(toJS(state.zone)).toEqual([USER_ROW]);
      expect(state.zone.some((row) => row.role === "tool")).toBe(false);

      compose.nth(0).push({ event: "done", message_id: DONE_ID });
      compose.nth(0).close();
      await within(running);
    } finally {
      dispose();
    }
    for (const ids of zoneIdsSeen) {
      for (const id of ids) expect(servedIds.has(id)).toBe(true);
    }
  });
});

// ---------------------------------------------------------------- DoD-3
describe("composeMessage — tool_result, tool_fail and unknown ids (D7)", () => {
  it('tool_result for c1 sets it ok with summary "Found 2 memos." — DoD-3', async () => {
    const { state, running, body } = await startedCompose(zoneSequence([USER_ROW], FINAL_LIST));
    body.push(C1_START);
    body.push(C1_RESULT);
    await until(() => state.liveTools[0]?.status === "ok", "c1 ok");

    expect(live(state)).toEqual([C1_OK]);

    body.push({ event: "done", message_id: DONE_ID });
    body.close();
    await within(running);
  });

  it('tool_start c2 then tool_fail c2 sets c2 failed with "The tool failed."; order is [c1, c2] — DoD-3', async () => {
    const { state, running, body } = await startedCompose(zoneSequence([USER_ROW], FINAL_LIST));
    body.push(C1_START);
    body.push(C1_RESULT);
    body.push(C2_START);
    body.push(C2_FAIL);
    await until(() => state.liveTools[1]?.status === "failed", "c2 failed");

    expect(live(state)).toEqual([C1_OK, C2_FAILED]);
    expect(state.liveTools.map((call) => call.callId)).toEqual(["c1", "c2"]);

    body.push({ event: "done", message_id: DONE_ID });
    body.close();
    await within(running);
  });

  it("a tool_result for unknown c9 changes nothing — DoD-3", async () => {
    const { state, running, body } = await startedCompose(zoneSequence([USER_ROW], FINAL_LIST));
    body.push(C1_START);
    body.push(C1_RESULT);
    body.push(C2_START);
    body.push(C2_FAIL);
    await until(() => state.liveTools[1]?.status === "failed", "c2 failed");
    const before = live(state);

    body.push({ event: "tool_result", tool: "memo_search", call_id: "c9", summary: "Ghost." });
    // A later token proves the c9 frame has been handled.
    body.push({ event: "token", text: "Marker" });
    await until(() => (state.streamingText ?? "").includes("Marker"), "frames after c9 handled");

    expect(live(state)).toEqual(before);
    expect(live(state)).toEqual([C1_OK, C2_FAILED]);

    body.push({ event: "done", message_id: DONE_ID });
    body.close();
    await within(running);
  });

  it("a tool_fail for unknown c9 changes nothing either — DoD-3", async () => {
    const { state, running, body } = await startedCompose(zoneSequence([USER_ROW], FINAL_LIST));
    body.push(C1_START);
    await until(() => state.liveTools.length === 1, "c1 live");

    body.push({ event: "tool_fail", tool: "memo_search", call_id: "c9", code: "tool_failed" });
    body.push({ event: "token", text: "Marker" });
    await until(() => (state.streamingText ?? "").includes("Marker"), "frames after c9 handled");

    expect(live(state)).toEqual([C1_RUNNING]);

    body.push({ event: "done", message_id: DONE_ID });
    body.close();
    await within(running);
  });
});

// ---------------------------------------------------------------- DoD-4
describe("composeMessage — done clears the live list atomically (D7, 019 D14, US-114.AC-2)", () => {
  it("the live list empties in the same state where zone is the final served list and the streaming text is null; tool rows and live calls are never seen together; no notification — DoD-4", async () => {
    const compose = composeStreams();
    const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([USER_ROW], FINAL_LIST) });
    const state = seeded(DRAFT);
    const finalIds = FINAL_LIST.map((row) => row.id).join(",");
    type Snap = { zoneHasTool: boolean; liveNonEmpty: boolean; textNull: boolean; zoneIsFinal: boolean };
    const seen: Snap[] = [];
    const dispose = autorun(() => {
      seen.push({
        zoneHasTool: state.zone.some((row) => row.role === "tool"),
        liveNonEmpty: state.liveTools.length > 0,
        textNull: state.streamingText === null,
        zoneIsFinal: state.zone.map((row) => row.id).join(",") === finalIds,
      });
    });
    try {
      const running = composeMessage(state);
      await until(() => compose.streams.length === 1, "compose POST issued");
      const body = compose.nth(0);
      body.push({ event: "accepted", message_id: ACCEPTED_ID });
      body.push(C1_START);
      body.push(C1_RESULT);
      body.push(C2_START);
      body.push(C2_FAIL);
      body.push({ event: "token", text: "The lighthouse keeper." });
      await until(() => state.liveTools.length === 2, "two live calls");
      await until(() => backend.count(GET_ZONE) >= 1 && state.zone.length === 1, "accepted re-read landed");

      body.push({ event: "done", message_id: DONE_ID });
      body.close();
      await expect(within(running)).resolves.toBeUndefined();
    } finally {
      dispose();
    }

    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(live(state)).toEqual([]);
    expect(toJS(state.zone)).toEqual(FINAL_LIST);
    expect(state.streamingText).toBeNull();

    // The live list was non-empty at some point, so the clear is observable.
    expect(seen.some((s) => s.liveNonEmpty)).toBe(true);
    // No render ever saw served tool rows and live tool calls together.
    expect(seen.some((s) => s.zoneHasTool && s.liveNonEmpty)).toBe(false);
    // Every state holding the final list already has an empty live list and no streaming text.
    for (const s of seen.filter((x) => x.zoneIsFinal)) {
      expect(s.liveNonEmpty).toBe(false);
      expect(s.textNull).toBe(true);
    }
    // And the streaming text never went null while the live list was still non-empty.
    expect(seen.some((s) => s.textNull && s.liveNonEmpty)).toBe(false);
  });
});

// ---------------------------------------------------------------- DoD-5
describe("composeMessage — stop and unmount with live tool calls (D7, 019 D12, D14)", () => {
  it("a user stop after a tool_start empties the live list together with the streaming text and notifies nothing — DoD-5", async () => {
    const stoppedList = [USER_ROW, TOOL_OK_ROW];
    const { state, running, body } = await startedCompose(zoneSequence([USER_ROW], stoppedList));
    const seen: { textNull: boolean; liveNonEmpty: boolean }[] = [];
    const dispose = autorun(() => {
      seen.push({ textNull: state.streamingText === null, liveNonEmpty: state.liveTools.length > 0 });
    });
    try {
      body.push(C1_START);
      body.push({ event: "token", text: "Looking" });
      await until(() => state.liveTools.length === 1 && state.streamingText === "Looking", "c1 live, a token in");

      stopCompose(state);
      await expect(within(running)).resolves.toBeUndefined();
      await flush();
    } finally {
      dispose();
    }

    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(live(state)).toEqual([]);
    expect(state.streamingText).toBeNull();
    expect(isStreaming(state)).toBe(false);
    expect(seen.some((s) => s.textNull && s.liveNonEmpty)).toBe(false);
  });

  it("a mount abort after a tool_start writes nothing to the live list afterwards — DoD-5", async () => {
    const mount = new AbortController();
    const zone = gatedFirstZone([USER_ROW, TOOL_OK_ROW]);
    const { backend, state, running, body } = await startedCompose(zone.route, mount.signal);
    body.push(C1_START);
    await until(() => state.liveTools.length === 1, "c1 live");
    await until(() => backend.count(GET_ZONE) === 1, "accepted-triggered zone GET");

    const liveAtAbort = live(state);
    let liveWritesAfterAbort = 0;
    const dispose = reaction(
      () => toJS(state.liveTools),
      () => {
        liveWritesAfterAbort += 1;
      },
    );
    try {
      mount.abort();
      // Frames offered after the abort and a late re-read must not reach the list.
      body.push(C1_RESULT);
      zone.open([USER_ROW]);
      await expect(within(running)).resolves.toBeUndefined();
      await flush();
    } finally {
      dispose();
    }

    expect(liveWritesAfterAbort).toBe(0);
    expect(live(state)).toEqual(liveAtAbort);
    expect(live(state)).toEqual([C1_RUNNING]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});
