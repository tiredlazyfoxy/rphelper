// Feature 019, step 003 — the SSE consumer and the shared failure decode
// (docs/plans/019.streaming-transport-and-stop/003.sse-consumer.md), DoD-1..DoD-12.
//
// Expected values come from the step's Interface intent and Definition of done and from
// `context.md` D9/D10 and `003.context.md` "Parsing a frame". `fetch` is stubbed per test
// with `vi.stubGlobal`; a streamed body is a `Response` over a `ReadableStream<Uint8Array>`
// built with `TextEncoder`. Every await on the consumer is bounded by `within`, and every
// wait on a side effect by `vi.waitFor`, so no test can hang.
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import {
  apiGet,
  decodeErrorResponse,
  documentNavigation,
  mapFetchRejection,
} from "../../src/shared/api";
import { ApiError, isApiError } from "../../src/shared/apiError";
import { postSse, type SseOutcome, type SseProgressFrame } from "../../src/shared/sse";

const { notifyFailureSpy } = vi.hoisted(() => ({ notifyFailureSpy: vi.fn() }));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const PATH = "/api/test/stream";
const enc = new TextEncoder();

let nav: MockInstance<(url: string) => void>;

beforeEach(() => {
  nav = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
  notifyFailureSpy.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- helpers

/** Rejects if `promise` has not settled within `ms`, so a stuck consumer fails instead of hanging. */
function within<T>(promise: Promise<T>, ms = 2000): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_resolve, reject) => {
    timer = setTimeout(() => reject(new Error(`timed out after ${ms}ms`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

function stubFetch(impl: FetchFn) {
  const mock = vi.fn<FetchFn>(impl);
  vi.stubGlobal("fetch", mock);
  return mock;
}

/** One SSE frame on the wire: `data: <json>\n\n`. */
function frame(payload: unknown): string {
  return `data: ${JSON.stringify(payload)}\n\n`;
}

function toBytes(chunk: string | Uint8Array): Uint8Array {
  return typeof chunk === "string" ? enc.encode(chunk) : chunk;
}

/** A body that delivers `chunks` in order, then closes. */
function closedBody(chunks: Array<string | Uint8Array>): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(toBytes(chunk));
      controller.close();
    },
  });
}

/**
 * A body the test drives by hand. When `signal` aborts, the stream errors with the
 * signal's reason, as the platform does for a fetch body in flight.
 */
function openBody(signal?: AbortSignal) {
  let ctrl: ReadableStreamDefaultController<Uint8Array> | undefined;
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      ctrl = controller;
    },
  });
  if (signal) {
    signal.addEventListener(
      "abort",
      () => {
        try {
          ctrl?.error(signal.reason);
        } catch {
          // already closed or cancelled
        }
      },
      { once: true },
    );
  }
  return {
    stream,
    push(chunk: string | Uint8Array): void {
      ctrl?.enqueue(toBytes(chunk));
    },
    fail(reason: unknown): void {
      ctrl?.error(reason);
    },
  };
}

function sseResponse(body: ReadableStream<Uint8Array>, status = 200): Response {
  return new Response(body, { status, headers: { "Content-Type": "text/event-stream" } });
}

function respondWithBody(chunks: Array<string | Uint8Array>, status = 200) {
  return stubFetch(() => Promise.resolve(sseResponse(closedBody(chunks), status)));
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Behaves like the platform fetch: never resolves; rejects with the signal's reason on abort. */
function abortableFetch(): FetchFn {
  return (_input, init) =>
    new Promise<Response>((_resolve, reject) => {
      const signal = init?.signal;
      if (!signal) return;
      if (signal.aborted) {
        reject(signal.reason);
        return;
      }
      signal.addEventListener("abort", () => reject(signal.reason), { once: true });
    });
}

function frameSpy() {
  return vi.fn<(frame: SseProgressFrame) => void>();
}

function delivered(spy: ReturnType<typeof frameSpy>): SseProgressFrame[] {
  return spy.mock.calls.map((call) => call[0]);
}

function errorOf(outcome: SseOutcome): ApiError {
  expect(outcome.kind).toBe("error");
  if (outcome.kind !== "error") throw new Error(`expected an error outcome, got ${outcome.kind}`);
  expect(outcome.error).toBeInstanceOf(ApiError);
  return outcome.error;
}

function run(onFrame = frameSpy(), signal = new AbortController().signal, body: unknown = {}) {
  return { onFrame, outcome: within(postSse(PATH, body, onFrame, signal)) };
}

/** Byte-splits `bytes` at the given ascending offsets. */
function splitAt(bytes: Uint8Array, offsets: number[]): Uint8Array[] {
  const parts: Uint8Array[] = [];
  let start = 0;
  for (const offset of offsets) {
    parts.push(bytes.slice(start, offset));
    start = offset;
  }
  parts.push(bytes.slice(start));
  return parts;
}

const ACCEPTED_ID = "7250416938275332095";
const DONE_ID = "7250416938275332096";

const HAPPY_WIRE =
  frame({ event: "accepted", message_id: ACCEPTED_ID }) +
  frame({ event: "token", text: "Hel" }) +
  frame({ event: "token", text: "lo" }) +
  frame({ event: "done", message_id: DONE_ID });

const HAPPY_FRAMES: SseProgressFrame[] = [
  { event: "accepted", message_id: ACCEPTED_ID },
  { event: "token", text: "Hel" },
  { event: "token", text: "lo" },
];

/** Sentinel for "the call resolved instead of rejecting". */
const NOT_ABORTED = Symbol("resolved instead of rejecting");

// ---------------------------------------------------------------- DoD-1 request shape

describe("the request", () => {
  it("POSTs to exactly the path with a JSON content type, the JSON body, same-origin credentials and the signal — DoD-1", async () => {
    const mock = respondWithBody([frame({ event: "done", message_id: DONE_ID })]);
    const controller = new AbortController();
    const body = { text: "Привет", session_id: "7250000000000000101", flags: [true, null] };

    await within(postSse(PATH, body, frameSpy(), controller.signal));

    expect(mock).toHaveBeenCalledTimes(1);
    const call = mock.mock.calls[0];
    if (call === undefined) throw new Error("fetch was not called");
    const [input, init] = call;
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    expect(url).toBe(PATH);
    expect(init?.method?.toUpperCase()).toBe("POST");
    const headers = new Headers(init?.headers);
    expect(headers.get("Content-Type") ?? "").toMatch(/^application\/json\b/i);
    expect(init?.body).toBe(JSON.stringify(body));
    expect(init?.credentials).toBe("same-origin");
    expect(init?.signal).toBe(controller.signal);
  });
});

// ---------------------------------------------------------------- DoD-2 happy path

describe("a complete stream", () => {
  it("delivers accepted (id kept as the exact string), then both tokens, and resolves done without passing done to the callback — DoD-2", async () => {
    respondWithBody([HAPPY_WIRE]);
    const { onFrame, outcome } = run();

    expect(await outcome).toStrictEqual({ kind: "done", messageId: DONE_ID });

    const frames = delivered(onFrame);
    expect(frames).toStrictEqual(HAPPY_FRAMES);
    const first = frames[0];
    if (first?.event !== "accepted") throw new Error("first frame is not accepted");
    expect(typeof first.message_id).toBe("string");
    expect(first.message_id).toBe("7250416938275332095");
    expect(frames.some((f) => (f as { event: string }).event === "done")).toBe(false);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("resolves done with the done frame's id as a string — DoD-2", async () => {
    respondWithBody([HAPPY_WIRE]);
    const result = await run().outcome;
    if (result.kind !== "done") throw new Error(`expected done, got ${result.kind}`);
    expect(typeof result.messageId).toBe("string");
    expect(result.messageId).toBe("7250416938275332096");
  });
});

// ---------------------------------------------------------------- DoD-3 chunking

describe("chunk boundaries", () => {
  it("has TextEncoder and TextDecoder available and round-tripping multi-byte text under jsdom — DoD-3", () => {
    const bytes = new TextEncoder().encode("Привет 🙂");
    // 6 two-byte Cyrillic letters + 1 space + a 4-byte emoji.
    expect(bytes.length).toBe(17);
    expect(new TextDecoder().decode(bytes)).toBe("Привет 🙂");
  });

  const secondData = HAPPY_WIRE.indexOf("data:", 1);
  const firstTerminator = HAPPY_WIRE.indexOf("\n\n");
  const cases: Array<[string, () => Array<string | Uint8Array>]> = [
    [
      "a boundary inside `data:`",
      () => [HAPPY_WIRE.slice(0, secondData + 2), HAPPY_WIRE.slice(secondData + 2)],
    ],
    [
      "a boundary between the two \\n of a terminator",
      () => [HAPPY_WIRE.slice(0, firstTerminator + 1), HAPPY_WIRE.slice(firstTerminator + 1)],
    ],
    ["all frames in one chunk", () => [HAPPY_WIRE]],
    ["one byte per chunk", () => Array.from(enc.encode(HAPPY_WIRE), (b) => Uint8Array.of(b))],
  ];

  it.each(cases)("gives the same frames and outcome for %s — DoD-3", async (_label, chunks) => {
    respondWithBody(chunks());
    const { onFrame, outcome } = run();

    expect(await outcome).toStrictEqual({ kind: "done", messageId: DONE_ID });
    expect(delivered(onFrame)).toStrictEqual(HAPPY_FRAMES);
  });

  it("delivers a token intact when a chunk boundary falls inside a multi-byte UTF-8 character — DoD-3", async () => {
    const text = "Привет 🙂";
    const wire =
      frame({ event: "accepted", message_id: ACCEPTED_ID }) +
      frame({ event: "token", text }) +
      frame({ event: "done", message_id: DONE_ID });
    const bytes = enc.encode(wire);
    // Inside "П" (2 bytes) and inside "🙂" (4 bytes).
    const cyrillicAt = enc.encode(wire.slice(0, wire.indexOf("П"))).length;
    const emojiAt = enc.encode(wire.slice(0, wire.indexOf("🙂"))).length;
    respondWithBody(splitAt(bytes, [cyrillicAt + 1, emojiAt + 2]));
    const { onFrame, outcome } = run();

    expect(await outcome).toStrictEqual({ kind: "done", messageId: DONE_ID });
    expect(delivered(onFrame)).toStrictEqual([
      { event: "accepted", message_id: ACCEPTED_ID },
      { event: "token", text: "Привет 🙂" },
    ]);
  });
});

// ---------------------------------------------------------------- DoD-4 error frame

describe("an error frame", () => {
  it("resolves (not rejects) to error with the frame's code, message, detail and the HTTP status — DoD-4", async () => {
    respondWithBody([
      frame({ event: "token", text: "x" }),
      'data: {"event":"error","code":"llm_unreachable","message":"down","detail":{"server_id":"7250000000000000007"}}\n\n',
    ]);
    const { onFrame, outcome } = run();

    const err = errorOf(await outcome);
    expect(err.code).toBe("llm_unreachable");
    expect(err.message).toBe("down");
    expect(err.detail).toStrictEqual({ server_id: "7250000000000000007" });
    expect(err.status).toBe(200);
    expect(delivered(onFrame)).toStrictEqual([{ event: "token", text: "x" }]);
  });

  it("uses an empty message when the frame's message is not a string and {} when detail is absent — DoD-4", async () => {
    respondWithBody([frame({ event: "error", code: "llm_unreachable", message: null })]);
    const err = errorOf(await run().outcome);
    expect(err.code).toBe("llm_unreachable");
    expect(err.message).toBe("");
    expect(err.detail).toStrictEqual({});
    expect(err.status).toBe(200);
  });
});

// ---------------------------------------------------------------- DoD-5 unexpected end

describe("a body that ends without a terminal frame", () => {
  it("resolves to unexpected end, notifying nothing and throwing nothing — DoD-5", async () => {
    respondWithBody([frame({ event: "token", text: "Hel" }), frame({ event: "token", text: "lo" })]);
    const { onFrame, outcome } = run();

    expect(await outcome).toStrictEqual({ kind: "unexpected_end" });
    expect(delivered(onFrame)).toStrictEqual([
      { event: "token", text: "Hel" },
      { event: "token", text: "lo" },
    ]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(nav).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------- DoD-6 stop

describe("stop", () => {
  it("resolves to stopped when the signal aborts while the body is open, after one token — DoD-6", async () => {
    const controller = new AbortController();
    const body = openBody(controller.signal);
    stubFetch(() => Promise.resolve(sseResponse(body.stream)));
    const onFrame = frameSpy();

    const outcome = within(postSse(PATH, {}, onFrame, controller.signal));
    body.push(frame({ event: "token", text: "Hel" }));
    await vi.waitFor(() => expect(onFrame).toHaveBeenCalledTimes(1));
    controller.abort();

    const result = await outcome;
    expect(result).toStrictEqual({ kind: "stopped" });
    expect(isApiError((result as { error?: unknown }).error)).toBe(false);
    expect(delivered(onFrame)).toStrictEqual([{ event: "token", text: "Hel" }]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("resolves to stopped when the abort lands before fetch resolves — DoD-6", async () => {
    const mock = stubFetch(abortableFetch());
    const controller = new AbortController();
    const onFrame = frameSpy();

    const outcome = within(postSse(PATH, {}, onFrame, controller.signal));
    await vi.waitFor(() => expect(mock).toHaveBeenCalled());
    controller.abort();

    expect(await outcome).toStrictEqual({ kind: "stopped" });
    expect(onFrame).not.toHaveBeenCalled();
  });

  it("resolves to stopped for a signal already aborted before the call — DoD-6", async () => {
    stubFetch(abortableFetch());
    const controller = new AbortController();
    controller.abort();
    const onFrame = frameSpy();

    expect(await within(postSse(PATH, {}, onFrame, controller.signal))).toStrictEqual({
      kind: "stopped",
    });
    expect(onFrame).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------- DoD-7 non-2xx

describe("a non-2xx response", () => {
  it("resolves a 409 envelope to error with its code, message, detail and status, never calling back — DoD-7", async () => {
    stubFetch(() =>
      Promise.resolve(
        jsonResponse(
          { error: { code: "model_not_enabled", message: "m", detail: { level: "session" } } },
          409,
        ),
      ),
    );
    const { onFrame, outcome } = run();

    const err = errorOf(await outcome);
    expect(err.code).toBe("model_not_enabled");
    expect(err.message).toBe("m");
    expect(err.detail).toStrictEqual({ level: "session" });
    expect(err.status).toBe(409);
    expect(onFrame).not.toHaveBeenCalled();
    expect(nav).not.toHaveBeenCalled();
  });

  it("resolves a 502 HTML page to error with client_malformed_error and status 502, never calling back — DoD-7", async () => {
    stubFetch(() =>
      Promise.resolve(
        new Response("<html><body><h1>502 Bad Gateway</h1></body></html>", {
          status: 502,
          headers: { "Content-Type": "text/html" },
        }),
      ),
    );
    const { onFrame, outcome } = run();

    const err = errorOf(await outcome);
    expect(err.code).toBe("client_malformed_error");
    expect(err.status).toBe(502);
    expect(onFrame).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------- DoD-8 401

describe("a 401 response", () => {
  it("navigates to /login exactly once and resolves to error with the envelope's code — DoD-8", async () => {
    stubFetch(() =>
      Promise.resolve(
        jsonResponse({ error: { code: "not_authenticated", message: "Not signed in.", detail: {} } }, 401),
      ),
    );
    const { onFrame, outcome } = run();

    const err = errorOf(await outcome);
    expect(nav).toHaveBeenCalledTimes(1);
    expect(nav).toHaveBeenCalledWith("/login");
    expect(err.code).toBe("not_authenticated");
    expect(err.status).toBe(401);
    expect(onFrame).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------- DoD-9 transport

describe("a transport failure", () => {
  it("resolves a rejected fetch (signal not aborted) to error client_transport_failed, status 0 — DoD-9", async () => {
    stubFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    const { onFrame, outcome } = run();

    const err = errorOf(await outcome);
    expect(err.code).toBe("client_transport_failed");
    expect(err.status).toBe(0);
    expect(onFrame).not.toHaveBeenCalled();
  });

  it("resolves a body read that rejects (signal not aborted) to error client_transport_failed, status 0 — DoD-9", async () => {
    const body = openBody();
    stubFetch(() => Promise.resolve(sseResponse(body.stream)));
    const onFrame = frameSpy();

    const outcome = within(postSse(PATH, {}, onFrame, new AbortController().signal));
    body.push(frame({ event: "token", text: "Hel" }));
    await vi.waitFor(() => expect(onFrame).toHaveBeenCalledTimes(1));
    body.fail(new TypeError("network error"));

    const err = errorOf(await outcome);
    expect(err.code).toBe("client_transport_failed");
    expect(err.status).toBe(0);
  });
});

// ---------------------------------------------------------------- DoD-10 parsing

describe("frame parsing", () => {
  it("resolves a frame whose data is not JSON to error client_malformed_error — DoD-10", async () => {
    respondWithBody([
      frame({ event: "token", text: "Hel" }),
      "data: {not json\n\n",
      frame({ event: "done", message_id: DONE_ID }),
    ]);
    const { onFrame, outcome } = run();

    const err = errorOf(await outcome);
    expect(err.code).toBe("client_malformed_error");
    expect(delivered(onFrame)).toStrictEqual([{ event: "token", text: "Hel" }]);
  });

  it.each([
    ["no event field", { text: "x" }],
    ["a non-string event", { event: 7, text: "x" }],
  ])("resolves a frame with %s to error client_malformed_error — DoD-10", async (_label, payload) => {
    respondWithBody([frame(payload), frame({ event: "done", message_id: DONE_ID })]);
    const { onFrame, outcome } = run();

    expect(errorOf(await outcome).code).toBe("client_malformed_error");
    expect(onFrame).not.toHaveBeenCalled();
  });

  it("skips an unknown event between two tokens and resolves to the following done — DoD-10", async () => {
    respondWithBody([
      frame({ event: "token", text: "Hel" }),
      frame({ event: "thinking", text: "hmm" }),
      frame({ event: "token", text: "lo" }),
      frame({ event: "done", message_id: DONE_ID }),
    ]);
    const { onFrame, outcome } = run();

    expect(await outcome).toStrictEqual({ kind: "done", messageId: DONE_ID });
    expect(delivered(onFrame)).toStrictEqual([
      { event: "token", text: "Hel" },
      { event: "token", text: "lo" },
    ]);
  });

  it("ignores a `: keepalive` comment — DoD-10", async () => {
    respondWithBody([
      ": keepalive\n\n",
      frame({ event: "token", text: "Hel" }),
      ": keepalive\n\n",
      frame({ event: "done", message_id: DONE_ID }),
    ]);
    const { onFrame, outcome } = run();

    expect(await outcome).toStrictEqual({ kind: "done", messageId: DONE_ID });
    expect(delivered(onFrame)).toStrictEqual([{ event: "token", text: "Hel" }]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------- DoD-11 after done

describe("bytes after a terminal frame", () => {
  it("never delivers a token that follows done in the same body — DoD-11", async () => {
    respondWithBody([
      frame({ event: "token", text: "Hel" }) +
        frame({ event: "done", message_id: DONE_ID }) +
        frame({ event: "token", text: "after" }),
    ]);
    const { onFrame, outcome } = run();

    expect(await outcome).toStrictEqual({ kind: "done", messageId: DONE_ID });
    expect(delivered(onFrame)).toStrictEqual([{ event: "token", text: "Hel" }]);
  });

  it("resolves done at once while the body is still open, and never delivers a later token — DoD-11", async () => {
    const body = openBody();
    stubFetch(() => Promise.resolve(sseResponse(body.stream)));
    body.push(frame({ event: "done", message_id: DONE_ID }));
    body.push(frame({ event: "token", text: "after" }));
    const onFrame = frameSpy();

    expect(await within(postSse(PATH, {}, onFrame, new AbortController().signal))).toStrictEqual({
      kind: "done",
      messageId: DONE_ID,
    });
    expect(onFrame).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------- DoD-12 apiRequest unchanged

describe("apiRequest after the refactor (D10)", () => {
  it("rejects a 401 with the envelope code after navigating to /login — DoD-12", async () => {
    stubFetch(() =>
      Promise.resolve(
        jsonResponse({ error: { code: "not_authenticated", message: "Not signed in.", detail: {} } }, 401),
      ),
    );
    const caught = await within(apiGet("/api/me").then(() => NOT_ABORTED, (e: unknown) => e));

    expect(nav).toHaveBeenCalledWith("/login");
    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).code).toBe("not_authenticated");
  });

  it("rejects a well-formed 409 with the envelope code and status — DoD-12", async () => {
    stubFetch(() =>
      Promise.resolve(jsonResponse({ error: { code: "zone_not_empty", message: "m", detail: {} } }, 409)),
    );
    const caught = await within(apiGet("/api/x").then(() => NOT_ABORTED, (e: unknown) => e));

    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).code).toBe("zone_not_empty");
    expect((caught as ApiError).status).toBe(409);
    expect(nav).not.toHaveBeenCalled();
  });

  it("rejects a malformed 500 with client_malformed_error — DoD-12", async () => {
    stubFetch(() => Promise.resolve(new Response("<html>oops</html>", { status: 500 })));
    const caught = await within(apiGet("/api/x").then(() => NOT_ABORTED, (e: unknown) => e));

    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).code).toBe("client_malformed_error");
    expect((caught as ApiError).status).toBe(500);
  });

  it("rejects a transport failure with client_transport_failed and status 0 — DoD-12", async () => {
    stubFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    const caught = await within(apiGet("/api/x").then(() => NOT_ABORTED, (e: unknown) => e));

    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).code).toBe("client_transport_failed");
    expect((caught as ApiError).status).toBe(0);
  });

  it("rejects an abort with the raw abort rejection, not an ApiError — DoD-12", async () => {
    const mock = stubFetch(abortableFetch());
    const controller = new AbortController();

    const pending = within(apiGet("/api/x", controller.signal).then(() => NOT_ABORTED, (e: unknown) => e));
    await vi.waitFor(() => expect(mock).toHaveBeenCalled());
    controller.abort();
    const caught = await pending;

    expect(caught).toBe(controller.signal.reason);
    expect(caught).not.toBeInstanceOf(ApiError);
    expect(isApiError(caught)).toBe(false);
  });

  it("decodeErrorResponse decodes a 401 envelope after navigating to /login, and an HTML body to the malformed fallback — DoD-12", async () => {
    const authErr = await within(
      decodeErrorResponse(
        jsonResponse({ error: { code: "not_authenticated", message: "Not signed in.", detail: {} } }, 401),
      ),
    );
    expect(nav).toHaveBeenCalledTimes(1);
    expect(nav).toHaveBeenCalledWith("/login");
    expect(authErr).toBeInstanceOf(ApiError);
    expect(authErr.code).toBe("not_authenticated");
    expect(authErr.status).toBe(401);

    const htmlErr = await within(decodeErrorResponse(new Response("<html></html>", { status: 502 })));
    expect(htmlErr.code).toBe("client_malformed_error");
    expect(htmlErr.status).toBe(502);
    expect(nav).toHaveBeenCalledTimes(1);
  });

  it("mapFetchRejection returns an abort unchanged and maps anything else to the transport error — DoD-12", () => {
    const controller = new AbortController();
    controller.abort();
    const reason: unknown = controller.signal.reason;
    expect(mapFetchRejection(reason, controller.signal)).toBe(reason);

    const mapped = mapFetchRejection(new TypeError("Failed to fetch"), new AbortController().signal);
    expect(mapped).toBeInstanceOf(ApiError);
    expect((mapped as ApiError).code).toBe("client_transport_failed");
    expect((mapped as ApiError).message).toBe("The server could not be reached.");
    expect((mapped as ApiError).status).toBe(0);

    const unsignalled = mapFetchRejection(new TypeError("Failed to fetch"));
    expect((unsignalled as ApiError).code).toBe("client_transport_failed");
  });
});
