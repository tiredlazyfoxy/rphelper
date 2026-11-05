// Feature 019, step 005 — bug-fix repro: a failed send whose text was already stored must not
// leave the draft for a duplicate re-send (docs/plans/019.streaming-transport-and-stop/
// 005.compose-effect.md, narrowed by DEC-019-BF1 in outcome.md `## Decisions`).
//
// Reproduces: "in the chat, when I'm doing retry it duplicates my last message" — a text-bearing
// compose committed the user row, then failed without the client handling an `accepted` frame, so
// the draft stayed in the composer and the next send re-posted the same text.
//
// Expected values come from DEC-019-BF1, context.md D14/D15 and R10:
//   - after a failed text-bearing compose with no handled `accepted`, the terminal zone re-read
//     decides: if the served zone's last non-tool row is a `user` row whose text equals the sent
//     text, the draft is cleared — only while it still equals the sent text (D15's own rule);
//   - the retry is then the textless compose (`regenerate`, body exactly `{}`): no text re-sent;
//   - when the re-read does not show the sent text stored, the draft is kept (D15, R10).
// Failure shapes covered: an SSE body whose first frame is `error` (no `accepted`), and a
// transport failure (fetch rejects). Every await is bounded.
import { runInAction, toJS } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Message, MessageRole } from "../../src/app/streamApi";
import { StreamState, composeMessage, isStreaming, regenerate } from "../../src/app/streamState";

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

const POST_COMPOSE = `POST ${COMPOSE_PATH}`;
const GET_ZONE = `GET ${ZONE_PATH}`;
const POST_ZONE_MESSAGES = `POST ${ZONE_MESSAGES_PATH}`;

const SENT = "The lighthouse keeper lifts the lantern and waits.";
const EDITED = "The lighthouse keeper lifts the lantern and waits, shivering.";
const STAMP = "2026-11-05T09:00:00.000000+00:00";

const enc = new TextEncoder();

function zoneRow(id: string, role: MessageRole, text: string): Message {
  return { id, session_id: SESSION_ID, role, kind: null, text, settled_at: null, created_at: STAMP, updated_at: STAMP };
}

/** A tool row (the "non-tool" rule of DEC-019-BF1 must look past it). */
function toolRow(id: string): Message {
  return { ...zoneRow(id, "tool", "lookup"), tool_name: "memo_search", tool_status: "ok", tool_args: {} };
}

/** The roleplayer's row the server committed before the compose failed. */
const STORED_ROW = zoneRow("7250000000000000301", "user", SENT);
/** An assistant row from an earlier exchange, already in the zone. */
const EARLIER_ASSISTANT = zoneRow("7250000000000000300", "assistant", "The storm rolls in.");
/** An earlier, different user row — the sent text is NOT what the server holds last. */
const OTHER_USER = zoneRow("7250000000000000299", "user", "A different earlier line.");
/** The reply the regenerate's terminal re-read serves. */
const REPLY_ROW = zoneRow("7250000000000000302", "assistant", "The lantern flickers.");

function seeded(seed: { zone?: Message[]; draft?: string }): StreamState {
  const state = new StreamState(SESSION_ID);
  runInAction(() => {
    state.entries = [];
    if (seed.zone !== undefined) state.zone = seed.zone;
    if (seed.draft !== undefined) state.draft = seed.draft;
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
  return { mock, calls, keys, count };
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

/** Serves the given zone lists in turn, repeating the last one. */
function zoneSequence(...lists: Message[][]): Route {
  let i = 0;
  return () => {
    const list = lists[Math.min(i, lists.length - 1)] ?? [];
    i += 1;
    return zoneJson(list);
  };
}

type FailureShape = "error-frame" | "transport";

/**
 * The compose route. The FIRST compose request is held pending until the test calls `fail()`,
 * so a test can edit the draft while the request is in flight; it then fails in the given shape
 * without ever sending `accepted` (the bug's precondition):
 *   - "error-frame": a 200 SSE body whose first and only frame is `error`, then the body ends;
 *   - "transport": the fetch itself rejects (a network / proxy drop).
 * Every LATER compose request (the retry) gets a held-open SSE stream the test drives.
 */
function failingThenStreaming(shape: FailureShape) {
  let settleFirst: ((response: Response) => void) | undefined;
  let rejectFirst: ((reason: unknown) => void) | undefined;
  let firstSignal: AbortSignal | undefined;
  let seen = 0;
  const later: HeldSse[] = [];
  const route: Route = (request) => {
    seen += 1;
    if (seen === 1) {
      firstSignal = request.signal;
      return new Promise<Response>((resolve, reject) => {
        settleFirst = resolve;
        rejectFirst = reject;
      });
    }
    const held = heldSse(request.signal);
    later.push(held);
    return held.response;
  };
  const fail = (): void => {
    if (settleFirst === undefined || rejectFirst === undefined) throw new Error("no first compose request yet");
    if (shape === "transport") {
      rejectFirst(new TypeError("Failed to fetch"));
      return;
    }
    const held = heldSse(firstSignal);
    held.push({ event: "error", code: "llm_unreachable", message: "down", detail: {} });
    held.close();
    settleFirst(held.response);
  };
  return { route, fail, later, issued: () => seen };
}

const SHAPES: [string, FailureShape][] = [
  ["an SSE body whose first frame is error (no accepted)", "error-frame"],
  ["a transport failure (fetch rejects)", "transport"],
];

/** Runs one failed text-bearing compose of `state`, failing after `beforeFail` ran mid-request. */
async function failedCompose(state: StreamState, compose: ReturnType<typeof failingThenStreaming>, beforeFail?: () => void) {
  const running = composeMessage(state);
  await until(() => compose.issued() === 1, "compose POST issued");
  beforeFail?.();
  compose.fail();
  await expect(within(running)).resolves.toBeUndefined();
}

const userRows = (state: StreamState): Message[] => state.zone.filter((row) => row.role === "user");

// ---------------------------------------------------------------- DEC-019-BF1: stored -> cleared
describe("composeMessage — a failed send whose text the re-read shows stored clears the draft (DEC-019-BF1)", () => {
  it.each(SHAPES)(
    'with %s and the zone serving [user row "SENT"]: draft "" and exactly one user row with the sent text — DEC-019-BF1',
    async (_label, shape) => {
      const compose = failingThenStreaming(shape);
      const backend = serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([STORED_ROW]) });
      const state = seeded({ zone: [], draft: SENT });

      await failedCompose(state, compose);

      // The sent body was the text-bearing compose.
      expect(backend.calls.find((c) => keyOf(c) === POST_COMPOSE)?.rawBody).toBe(JSON.stringify({ text: SENT }));
      // The terminal re-read happened and is the zone.
      expect(backend.keys()[backend.keys().length - 1]).toBe(GET_ZONE);
      expect(toJS(state.zone)).toEqual([STORED_ROW]);
      expect(userRows(state)).toHaveLength(1);
      expect(userRows(state)[0]?.text).toBe(SENT);
      // The text is stored, so nothing is lost by clearing it.
      expect(state.draft).toBe("");
      expect(isStreaming(state)).toBe(false);
      // The failure itself is still reported (R10 / D14).
      expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
    },
  );

  it.each(SHAPES)(
    "with %s and earlier rows before the stored user row plus a trailing tool row: draft cleared (last NON-tool row decides) — DEC-019-BF1",
    async (_label, shape) => {
      const served = [EARLIER_ASSISTANT, STORED_ROW, toolRow("7250000000000000303")];
      const compose = failingThenStreaming(shape);
      serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence(served) });
      const state = seeded({ zone: [EARLIER_ASSISTANT], draft: SENT });

      await failedCompose(state, compose);

      expect(toJS(state.zone)).toEqual(served);
      expect(state.draft).toBe("");
    },
  );

  it.each(SHAPES)(
    "with %s, the retry is regenerate: one more compose POST with body exactly {}, no text re-sent, no second user row — DEC-019-BF1",
    async (_label, shape) => {
      const compose = failingThenStreaming(shape);
      const backend = serve({
        [POST_COMPOSE]: compose.route,
        // failed compose's terminal re-read, then the regenerate's terminal re-read
        [GET_ZONE]: zoneSequence([STORED_ROW], [STORED_ROW, REPLY_ROW]),
      });
      const state = seeded({ zone: [], draft: SENT });

      await failedCompose(state, compose);
      expect(state.draft).toBe("");

      const retry = regenerate(state);
      await until(() => compose.later.length === 1, "regenerate compose POST issued");
      compose.later[0]?.push({ event: "done", message_id: REPLY_ROW.id });
      compose.later[0]?.close();
      await expect(within(retry)).resolves.toBeUndefined();

      const composeBodies = backend.calls.filter((c) => keyOf(c) === POST_COMPOSE).map((c) => c.rawBody);
      expect(composeBodies).toHaveLength(2);
      expect(composeBodies[1]).toBe("{}");
      // The sent text went over the wire exactly once, in the original compose.
      expect(composeBodies.filter((body) => typeof body === "string" && body.includes(SENT))).toHaveLength(1);
      expect(backend.count(POST_ZONE_MESSAGES)).toBe(0);

      expect(toJS(state.zone)).toEqual([STORED_ROW, REPLY_ROW]);
      expect(userRows(state)).toHaveLength(1);
      expect(state.draft).toBe("");
    },
  );
});

// ---------------------------------------------------------------- D15 / R10 guards: not stored -> kept
describe("composeMessage — a failed send the re-read does not show stored keeps the draft (D15, R10, DEC-019-BF1 guard)", () => {
  it.each(SHAPES)("with %s and an empty served zone: the draft is kept — D15, R10", async (_label, shape) => {
    const compose = failingThenStreaming(shape);
    serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([]) });
    const state = seeded({ zone: [], draft: SENT });

    await failedCompose(state, compose);

    expect(toJS(state.zone)).toEqual([]);
    expect(state.draft).toBe(SENT);
    expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
  });

  it.each(SHAPES)(
    "with %s and a served zone whose last non-tool row is an assistant row (no stored sent text): the draft is kept — D15, R10",
    async (_label, shape) => {
      const compose = failingThenStreaming(shape);
      serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([EARLIER_ASSISTANT]) });
      const state = seeded({ zone: [EARLIER_ASSISTANT], draft: SENT });

      await failedCompose(state, compose);

      expect(toJS(state.zone)).toEqual([EARLIER_ASSISTANT]);
      expect(state.draft).toBe(SENT);
    },
  );

  it.each(SHAPES)(
    "with %s and a served zone whose last non-tool row is a user row with DIFFERENT text: the draft is kept — D15, R10",
    async (_label, shape) => {
      const compose = failingThenStreaming(shape);
      serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([EARLIER_ASSISTANT, OTHER_USER]) });
      const state = seeded({ zone: [EARLIER_ASSISTANT, OTHER_USER], draft: SENT });

      await failedCompose(state, compose);

      expect(toJS(state.zone)).toEqual([EARLIER_ASSISTANT, OTHER_USER]);
      expect(state.draft).toBe(SENT);
    },
  );
});

// ---------------------------------------------------------------- D15: edited draft is never cleared
describe("composeMessage — a draft edited during the failed send is kept even when the sent text is stored (D15, DEC-019-BF1)", () => {
  it.each(SHAPES)(
    "with %s, the draft retyped mid-request and the zone serving [user row SENT]: the edited draft is kept — D15, DEC-019-BF1",
    async (_label, shape) => {
      const compose = failingThenStreaming(shape);
      serve({ [POST_COMPOSE]: compose.route, [GET_ZONE]: zoneSequence([STORED_ROW]) });
      const state = seeded({ zone: [], draft: SENT });

      await failedCompose(state, compose, () => {
        runInAction(() => {
          state.draft = EDITED;
        });
      });

      expect(toJS(state.zone)).toEqual([STORED_ROW]);
      expect(state.draft).toBe(EDITED);
    },
  );
});
