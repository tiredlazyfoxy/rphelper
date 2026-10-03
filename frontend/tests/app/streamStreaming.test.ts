// Feature 019, step 004 — the compose call and the streaming state surface
// (docs/plans/019.streaming-transport-and-stop/004.streaming-state-and-stop-slot.md), DoD-1..DoD-6.
//
// Expected values come from the step's Interface intent and Definition of done and from
// context.md D9, D11, D12, D13 and 004.context.md "Test notes":
//   - `composeZone` POSTs exactly /api/sessions/<encodeURIComponent(id)>/zone/compose with body
//     {"text": …} through 003's consumer, and resolves to that consumer's outcome unchanged;
//   - a fresh `StreamState` has streaming text null and compose handle null (not observable);
//     `isStreaming` is "streaming text is not null";
//   - `canSend` and `showsDiscard` additionally require not streaming; `canSettle` ignores it;
//   - `stopCompose` aborts the handle's controller and nothing else: no field write, no request,
//     no notification; with no handle it does nothing.
// Tests put the state into "streaming" by assigning the streaming text and a handle directly,
// inside `runInAction`. Every await on the call under test is bounded by `within`.
import { autorun, isObservableProp, runInAction, toJS } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { composeZone, type Message, type MessageRole } from "../../src/app/streamApi";
import {
  StreamState,
  canSend,
  canSettle,
  isStreaming,
  showsDiscard,
  stopCompose,
  type ComposeHandle,
} from "../../src/app/streamState";
import type { SseProgressFrame } from "../../src/shared/sse";

const { notifyFailureSpy } = vi.hoisted(() => ({ notifyFailureSpy: vi.fn() }));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "7250000000000000042";
const ACCEPTED_ID = "7250000000000000098";
const DONE_ID = "7250000000000000099";
const STAMP = "2026-10-04T09:00:00.000000+00:00";

const enc = new TextEncoder();

beforeEach(() => {
  notifyFailureSpy.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function zoneRow(id: string, role: MessageRole, text: string): Message {
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

type Seed = { zone?: Message[]; draft?: string; busy?: boolean };

function seeded(seed: Seed = {}): StreamState {
  const state = new StreamState(SESSION_ID);
  runInAction(() => {
    if (seed.zone !== undefined) state.zone = seed.zone;
    if (seed.draft !== undefined) state.draft = seed.draft;
    if (seed.busy !== undefined) state.busy = seed.busy;
    state.status = "ready";
  });
  return state;
}

function freshHandle(): ComposeHandle {
  return { controller: new AbortController(), woundDown: Promise.resolve() };
}

/** Puts the state into "streaming": a streaming text and a handle, assigned directly. */
function startStreaming(state: StreamState, text = "", handle: ComposeHandle | null = freshHandle()): void {
  runInAction(() => {
    state.streamingText = text;
    state.composeHandle = handle;
  });
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
    streamingText: state.streamingText,
  };
}

// ---------------------------------------------------------------- harness
/** Rejects if `promise` has not settled within `ms`, so a stuck call fails instead of hanging. */
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

function frame(payload: unknown): string {
  return `data: ${JSON.stringify(payload)}\n\n`;
}

function sseResponse(chunks: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(enc.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

function serveAcceptedThenDone() {
  return stubFetch(() =>
    Promise.resolve(
      sseResponse([
        frame({ event: "accepted", message_id: ACCEPTED_ID }),
        frame({ event: "done", message_id: DONE_ID }),
      ]),
    ),
  );
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

// ---------------------------------------------------------------- DoD-1
describe("composeZone — the compose call (D9, 013 D14)", () => {
  it('composeZone("7250000000000000042", "Hi ((short))", cb, signal) issues one POST to exactly /api/sessions/7250000000000000042/zone/compose with body exactly {"text":"Hi ((short))"} — DoD-1', async () => {
    const mock = serveAcceptedThenDone();
    const controller = new AbortController();
    const cb = vi.fn<(frame: SseProgressFrame) => void>();

    await within(composeZone("7250000000000000042", "Hi ((short))", cb, controller.signal));

    expect(mock).toHaveBeenCalledTimes(1);
    const [input, init] = mock.mock.calls[0] ?? [];
    expect(input).toBeDefined();
    if (input === undefined) return;
    expect(requestMethod(input, init)).toBe("POST");
    expect(requestUrl(input).pathname).toBe("/api/sessions/7250000000000000042/zone/compose");
    expect(requestUrl(input).search).toBe("");
    expect(init?.body).toBe('{"text":"Hi ((short))"}');
    expect(init?.signal).toBe(controller.signal);
  });

  it('resolves to the consumer\'s outcome unchanged: done with messageId "7250000000000000099", the frame callback fed the accepted frame — DoD-1', async () => {
    serveAcceptedThenDone();
    const controller = new AbortController();
    const cb = vi.fn<(frame: SseProgressFrame) => void>();

    const outcome = await within(composeZone(SESSION_ID, "Hi ((short))", cb, controller.signal));

    expect(outcome).toEqual({ kind: "done", messageId: DONE_ID });
    expect(cb.mock.calls.map(([seen]) => seen)).toEqual([{ event: "accepted", message_id: ACCEPTED_ID }]);
  });

  it("a session id containing / is percent-encoded in the path — DoD-1", async () => {
    const mock = serveAcceptedThenDone();
    const controller = new AbortController();

    await within(composeZone("a/b", "Hi ((short))", () => undefined, controller.signal));

    expect(mock).toHaveBeenCalledTimes(1);
    const input = mock.mock.calls[0]?.[0];
    expect(input).toBeDefined();
    if (input === undefined) return;
    expect(requestUrl(input).pathname).toBe(`/api/sessions/${encodeURIComponent("a/b")}/zone/compose`);
    expect(requestUrl(input).pathname).toBe("/api/sessions/a%2Fb/zone/compose");
  });
});

// ---------------------------------------------------------------- DoD-2
describe("StreamState — streaming text, compose handle and isStreaming (D11, D12)", () => {
  it("a fresh StreamState has streaming text null, compose handle null and isStreaming false — DoD-2", () => {
    const state = new StreamState(SESSION_ID);

    expect(state.streamingText).toBeNull();
    expect(state.composeHandle).toBeNull();
    expect(isStreaming(state)).toBe(false);
  });

  it('with streaming text "" isStreaming is true — DoD-2', () => {
    const state = new StreamState(SESSION_ID);
    runInAction(() => {
      state.streamingText = "";
    });

    expect(isStreaming(state)).toBe(true);
  });

  it("with streaming text back to null isStreaming is false again — DoD-2", () => {
    const state = new StreamState(SESSION_ID);
    runInAction(() => {
      state.streamingText = "Partial words";
    });
    expect(isStreaming(state)).toBe(true);

    runInAction(() => {
      state.streamingText = null;
    });
    expect(isStreaming(state)).toBe(false);
  });

  it("the streaming text is observable and the compose handle is not — DoD-2", () => {
    const state = new StreamState(SESSION_ID);

    expect(isObservableProp(state, "streamingText")).toBe(true);
    expect(isObservableProp(state, "composeHandle")).toBe(false);
  });

  it("isStreaming is reactive through the streaming text — DoD-2", () => {
    const state = new StreamState(SESSION_ID);
    const seen: boolean[] = [];
    const dispose = autorun(() => {
      seen.push(isStreaming(state));
    });
    try {
      runInAction(() => {
        state.streamingText = "";
      });
      runInAction(() => {
        state.streamingText = null;
      });
    } finally {
      dispose();
    }

    expect(seen).toEqual([false, true, false]);
  });
});

// ---------------------------------------------------------------- DoD-3
describe("canSend — also requires not streaming (D13)", () => {
  it("with a non-blank draft and busy false, canSend is true when not streaming — DoD-3", () => {
    const state = seeded({ draft: "Hello", busy: false });

    expect(isStreaming(state)).toBe(false);
    expect(canSend(state)).toBe(true);
  });

  it("with a non-blank draft and busy false, canSend is false while streaming — DoD-3", () => {
    const state = seeded({ draft: "Hello", busy: false });
    startStreaming(state, "");

    expect(isStreaming(state)).toBe(true);
    expect(canSend(state)).toBe(false);
  });

  it("canSend returns to true once the streaming text is null again — DoD-3", () => {
    const state = seeded({ draft: "Hello", busy: false });
    startStreaming(state, "Some partial reply");
    expect(canSend(state)).toBe(false);

    runInAction(() => {
      state.streamingText = null;
      state.composeHandle = null;
    });
    expect(canSend(state)).toBe(true);
  });
});

// ---------------------------------------------------------------- DoD-4
describe("canSettle — unchanged by streaming (D13, workspace-shell 'The stop control', US-135.AC-1)", () => {
  it("with one zone row on my turn, canSettle is true when not streaming — DoD-4", () => {
    const state = seeded({ zone: [zoneRow("7250000000000000101", "user", "Mine")] });

    expect(isStreaming(state)).toBe(false);
    expect(canSettle(state)).toBe(true);
  });

  it("with one zone row on my turn, canSettle is still true while streaming — DoD-4", () => {
    const state = seeded({ zone: [zoneRow("7250000000000000101", "user", "Mine")] });
    startStreaming(state, "Partial");

    expect(isStreaming(state)).toBe(true);
    expect(canSettle(state)).toBe(true);
  });

  it("with an empty zone and a blank draft, canSettle is false when not streaming — DoD-4", () => {
    const state = seeded({ zone: [], draft: "" });

    expect(canSettle(state)).toBe(false);
  });

  it("with an empty zone and a blank draft, canSettle is false while streaming — DoD-4", () => {
    const state = seeded({ zone: [], draft: "" });
    startStreaming(state, "");

    expect(isStreaming(state)).toBe(true);
    expect(canSettle(state)).toBe(false);
  });
});

// ---------------------------------------------------------------- DoD-5
describe("showsDiscard — also requires not streaming (D13)", () => {
  it("with an empty zone and a blank draft, showsDiscard is true when not streaming — DoD-5", () => {
    const state = seeded({ zone: [], draft: "" });

    expect(showsDiscard(state)).toBe(true);
  });

  it("with an empty zone and a blank draft, showsDiscard is false while streaming — DoD-5", () => {
    const state = seeded({ zone: [], draft: "" });
    startStreaming(state, "");

    expect(isStreaming(state)).toBe(true);
    expect(showsDiscard(state)).toBe(false);
  });
});

// ---------------------------------------------------------------- DoD-6
describe("stopCompose — aborts the compose controller and nothing else (D12, UC-085)", () => {
  it("with a handle whose controller is fresh, stopCompose aborts that controller — DoD-6", () => {
    stubFetch(() => Promise.reject(new Error("no request expected")));
    const state = seeded({ zone: [zoneRow("7250000000000000101", "user", "Mine")], draft: "Next line" });
    const handle = freshHandle();
    startStreaming(state, "Partial reply", handle);
    expect(handle.controller.signal.aborted).toBe(false);

    stopCompose(state);

    expect(handle.controller.signal.aborted).toBe(true);
  });

  it("the call itself leaves streaming text, zone, entries, draft and busy unchanged, makes no fetch and calls no notifyFailure — DoD-6", async () => {
    const mock = stubFetch(() => Promise.reject(new Error("no request expected")));
    const state = seeded({
      zone: [zoneRow("7250000000000000101", "user", "Mine"), zoneRow("7250000000000000102", "assistant", "Theirs")],
      draft: "Next line",
      busy: false,
    });
    const handle = freshHandle();
    startStreaming(state, "Partial reply", handle);
    const before = snapshot(state);

    stopCompose(state);
    // Let any stray microtask run before checking nothing happened.
    await within(new Promise<void>((resolve) => setTimeout(resolve, 0)));

    expect(snapshot(state)).toEqual(before);
    expect(state.streamingText).toBe("Partial reply");
    expect(state.composeHandle).toBe(handle);
    expect(mock).not.toHaveBeenCalled();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("stopCompose leaves busy true when it was true — DoD-6", () => {
    stubFetch(() => Promise.reject(new Error("no request expected")));
    const state = seeded({ draft: "Next line", busy: true });
    startStreaming(state, "Partial reply");

    stopCompose(state);

    expect(state.busy).toBe(true);
  });

  it("with no handle, stopCompose does nothing and does not throw — DoD-6", async () => {
    const mock = stubFetch(() => Promise.reject(new Error("no request expected")));
    const state = seeded({ zone: [zoneRow("7250000000000000101", "user", "Mine")], draft: "Next line" });
    expect(state.composeHandle).toBeNull();
    const before = snapshot(state);

    expect(() => {
      stopCompose(state);
    }).not.toThrow();
    await within(new Promise<void>((resolve) => setTimeout(resolve, 0)));

    expect(snapshot(state)).toEqual(before);
    expect(state.composeHandle).toBeNull();
    expect(mock).not.toHaveBeenCalled();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});
