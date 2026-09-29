// Feature 003, step 004 — the bootstrap entry's store and its free functions
// (DoD-6, DoD-7, DoD-8, DoD-10, DoD-12, DoD-13).
// `fetch` is stubbed per test (tests/setup.ts holds no stub). Timers are faked only for
// setTimeout/setInterval, so `setImmediate` stays real and is used to drain pending work.
import { isComputedProp, isObservableProp } from "mobx";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  BootstrapState,
  NOT_READY_RETRY_INTERVAL_MS,
  bootstrapPhase,
  probeHealth,
  startProbeLoop,
  stopProbeLoop,
  type ProbeLoop,
} from "../../src/bootstrap/bootstrapState";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const loops: ProbeLoop[] = [];

afterEach(() => {
  while (loops.length > 0) {
    const loop = loops.pop();
    if (loop !== undefined) stopProbeLoop(loop);
  }
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- helpers

function stubFetch(impl: FetchFn) {
  const mock = vi.fn<FetchFn>(impl);
  vi.stubGlobal("fetch", mock);
  return mock;
}

/** Answers the n-th request with the n-th handler; the last handler repeats. */
function stubSequence(handlers: Array<() => Promise<Response>>) {
  let index = 0;
  return stubFetch(() => {
    const handler = handlers[Math.min(index, handlers.length - 1)];
    index += 1;
    return handler();
  });
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function healthBody(configured: boolean, status: string, schema: string) {
  return { status, configured, schema };
}

const answerHealth = (configured: boolean, status = configured ? "ok" : "degraded", schema = configured ? "ok" : "missing") =>
  () => Promise.resolve(jsonResponse(healthBody(configured, status, schema), 200));

const transportFailure = () => Promise.reject(new TypeError("Failed to fetch"));

const htmlPage = (status: number) => () =>
  Promise.resolve(
    new Response(`<html><body><h1>${status} Bad Gateway</h1><hr>nginx</body></html>`, {
      status,
      headers: { "Content-Type": "text/html" },
    }),
  );

const envelope = (code: string, message: string, status: number) => () =>
  Promise.resolve(jsonResponse({ error: { code, message, detail: {} } }, status));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function drain(rounds = 4): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await new Promise<void>((resolve) => setImmediate(resolve));
  }
}

function useFakeTimers(): void {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
}

async function advance(ms: number): Promise<void> {
  await vi.advanceTimersByTimeAsync(ms);
  await drain();
}

function start(state: BootstrapState): ProbeLoop {
  const loop = startProbeLoop(state);
  loops.push(loop);
  return loop;
}

function pathOf(input: RequestInfo | URL): string {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost").pathname;
}

// ---------------------------------------------------------------------------
describe("the store is a data class with observable fields only", () => {
  it("the class prototype carries no method and no getter — DoD-13", () => {
    expect(Object.getOwnPropertyNames(BootstrapState.prototype)).toEqual(["constructor"]);
  });

  it("phase and failureMessage are observable, not computed — DoD-13", () => {
    const state = new BootstrapState();
    expect(isObservableProp(state, "phase")).toBe(true);
    expect(isObservableProp(state, "failureMessage")).toBe(true);
    expect(isComputedProp(state, "phase")).toBe(false);
    expect(isComputedProp(state, "failureMessage")).toBe(false);
  });

  it("no own property of an instance is a function or a computed value — DoD-13", () => {
    const state = new BootstrapState();
    const record = state as unknown as Record<string, unknown>;
    for (const name of Object.getOwnPropertyNames(state)) {
      expect(typeof record[name], `own property ${name}`).not.toBe("function");
      expect(isComputedProp(state, name), `own property ${name}`).toBe(false);
    }
  });

  it("the derivation and the effects are free functions taking the data object — DoD-13", () => {
    expect(typeof bootstrapPhase).toBe("function");
    expect(typeof probeHealth).toBe("function");
    expect(typeof startProbeLoop).toBe("function");
    expect(typeof stopProbeLoop).toBe("function");
    expect(bootstrapPhase.length).toBe(1);
  });

  it("a fresh store is in the probing phase — DoD-13", () => {
    expect(bootstrapPhase(new BootstrapState())).toBe("probing");
  });

  it("the derivation is pure: reading it writes nothing — DoD-13", async () => {
    stubFetch(answerHealth(true));
    const state = new BootstrapState();
    await probeHealth(state);
    const before = { phase: state.phase, failureMessage: state.failureMessage };
    expect(bootstrapPhase(state)).toBe("refusal");
    expect(bootstrapPhase(state)).toBe("refusal");
    expect({ phase: state.phase, failureMessage: state.failureMessage }).toEqual(before);
  });
});

// ---------------------------------------------------------------------------
describe("probeHealth reads GET /api/health and branches on configured alone", () => {
  it("issues one GET /api/health — DoD-6", async () => {
    const fetchMock = stubFetch(answerHealth(false));
    await probeHealth(new BootstrapState());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [input, init] = fetchMock.mock.calls[0];
    expect(pathOf(input)).toBe("/api/health");
    expect((init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase()).toBe("GET");
  });

  it.each([
    ["degraded", "missing"],
    ["unconfigured", "ok"],
    ["ok", "ok"],
  ])("configured:false with status %s / schema %s gives the offer — DoD-6", async (status, schema) => {
    stubFetch(answerHealth(false, status, schema));
    const state = new BootstrapState();
    await probeHealth(state);
    expect(bootstrapPhase(state)).toBe("offer");
  });

  it.each([
    ["ok", "ok"],
    ["degraded", "missing"],
    ["unconfigured", "ok"],
  ])("configured:true with status %s / schema %s gives the refusal — DoD-6", async (status, schema) => {
    stubFetch(answerHealth(true, status, schema));
    const state = new BootstrapState();
    await probeHealth(state);
    expect(bootstrapPhase(state)).toBe("refusal");
  });
});

// ---------------------------------------------------------------------------
describe("probeHealth classifies a failure", () => {
  it.each<[string, () => Promise<Response>]>([
    ["a transport failure", transportFailure],
    ["a raw 502 HTML page", htmlPage(502)],
    ["a raw 503 HTML page", htmlPage(503)],
    ["a raw 504 HTML page", htmlPage(504)],
  ])("%s gives not-ready — DoD-7, DoD-8", async (_name, handler) => {
    stubFetch(handler);
    const state = new BootstrapState();
    await probeHealth(state);
    expect(bootstrapPhase(state)).toBe("not-ready");
  });

  it("a well-formed backend error gives failed with that error's message kept — DoD-10", async () => {
    stubFetch(envelope("internal_error", "The health probe exploded zq-17.", 500));
    const state = new BootstrapState();
    await probeHealth(state);
    expect(bootstrapPhase(state)).toBe("failed");
    expect(state.failureMessage).toBe("The health probe exploded zq-17.");
  });

  it("a malformed 4xx body gives failed, not not-ready — DoD-10", async () => {
    stubFetch(htmlPage(404));
    const state = new BootstrapState();
    await probeHealth(state);
    expect(bootstrapPhase(state)).toBe("failed");
  });
});

// ---------------------------------------------------------------------------
describe("the retry loop", () => {
  it("the fixed interval is 2000 ms — DoD-8", () => {
    expect(NOT_READY_RETRY_INTERVAL_MS).toBe(2000);
  });

  it("re-probes every 2000 ms while not-ready, then stops once a probe succeeds — DoD-8", async () => {
    useFakeTimers();
    const fetchMock = stubSequence([transportFailure, transportFailure, answerHealth(false)]);
    const state = new BootstrapState();
    start(state);
    await drain();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(bootstrapPhase(state)).toBe("not-ready");

    await advance(1999);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await advance(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(bootstrapPhase(state)).toBe("not-ready");

    await advance(2000);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(bootstrapPhase(state)).toBe("offer");

    await advance(20000);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(bootstrapPhase(state)).toBe("offer");
  });

  it("the retry is uncapped: it keeps going while the backend stays down — DoD-8", async () => {
    useFakeTimers();
    const fetchMock = stubFetch(htmlPage(502));
    const state = new BootstrapState();
    start(state);
    await drain();
    for (let n = 2; n <= 12; n += 1) {
      await advance(2000);
      expect(fetchMock).toHaveBeenCalledTimes(n);
    }
    expect(bootstrapPhase(state)).toBe("not-ready");
  });

  it("resolving to the refusal also stops the interval — DoD-8", async () => {
    useFakeTimers();
    const fetchMock = stubSequence([htmlPage(502), answerHealth(true)]);
    const state = new BootstrapState();
    start(state);
    await drain();
    await advance(2000);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(bootstrapPhase(state)).toBe("refusal");
    await advance(20000);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("a failure that is not the not-ready condition starts no interval — DoD-10", async () => {
    useFakeTimers();
    const fetchMock = stubFetch(envelope("internal_error", "The health probe exploded zq-17.", 500));
    const state = new BootstrapState();
    start(state);
    await drain();
    expect(bootstrapPhase(state)).toBe("failed");
    await advance(20000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(bootstrapPhase(state)).toBe("failed");
  });

  it("a successful first probe starts no interval — DoD-8", async () => {
    useFakeTimers();
    const fetchMock = stubFetch(answerHealth(false));
    const state = new BootstrapState();
    start(state);
    await drain();
    await advance(20000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
describe("stopping cancels the timer and the in-flight request", () => {
  it("stopping while not-ready issues no further request — DoD-12", async () => {
    useFakeTimers();
    const fetchMock = stubFetch(transportFailure);
    const state = new BootstrapState();
    const loop = startProbeLoop(state);
    await drain();
    expect(bootstrapPhase(state)).toBe("not-ready");
    stopProbeLoop(loop);
    await advance(20000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(bootstrapPhase(state)).toBe("not-ready");
  });

  it("stopping aborts the in-flight request's signal — DoD-12", async () => {
    const pending = deferred<Response>();
    const fetchMock = stubFetch(() => pending.promise);
    const state = new BootstrapState();
    const loop = startProbeLoop(state);
    await drain();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    stopProbeLoop(loop);
    const signal = fetchMock.mock.calls[0][1]?.signal;
    expect(signal?.aborted).toBe(true);
    pending.resolve(jsonResponse(healthBody(false, "degraded", "missing"), 200));
    await drain();
  });

  it("a response arriving after stop writes nothing to the store — DoD-12", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = new BootstrapState();
    const loop = startProbeLoop(state);
    await drain();
    stopProbeLoop(loop);
    pending.resolve(jsonResponse(healthBody(false, "degraded", "missing"), 200));
    await drain();
    expect(bootstrapPhase(state)).toBe("probing");
    expect(state.phase).toBe("probing");
    expect(state.failureMessage).toBeNull();
  });

  it("an abort rejection after stop is not rendered as a failure — DoD-12", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = new BootstrapState();
    const loop = startProbeLoop(state);
    await drain();
    stopProbeLoop(loop);
    pending.reject(new DOMException("The operation was aborted.", "AbortError"));
    await drain();
    expect(bootstrapPhase(state)).toBe("probing");
    expect(state.failureMessage).toBeNull();
  });

  it("probeHealth with an already-aborted signal writes nothing — DoD-12", async () => {
    stubFetch(answerHealth(true));
    const controller = new AbortController();
    controller.abort();
    const state = new BootstrapState();
    await probeHealth(state, controller.signal).catch(() => undefined);
    expect(bootstrapPhase(state)).toBe("probing");
    expect(state.failureMessage).toBeNull();
  });

  it("probeHealth aborted mid-flight writes nothing even if a body still arrives — DoD-12", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const controller = new AbortController();
    const state = new BootstrapState();
    const probe = probeHealth(state, controller.signal).catch(() => undefined);
    await drain();
    controller.abort();
    pending.resolve(jsonResponse(healthBody(true, "ok", "ok"), 200));
    await probe;
    await drain();
    expect(bootstrapPhase(state)).toBe("probing");
    expect(state.failureMessage).toBeNull();
  });
});
