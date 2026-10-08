// Feature 023, step 004 — the per-row flicker state, its view derivation and its effects
// (DoD-2..DoD-11).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done plus
// context.md's D4 (client half: while pending the flicker cancels; the original stays, no
// notification, because a stop is not a failure), D13 (the state shape, the per-mount cache,
// a cached flick makes no request), D14 (invalidate aborts, drops the cached text, un-shows,
// and a late answer writes nothing), the "Wire contract" and the frontend cross-cutting
// constraints (effects never reject; no success notification; ids are strings), and
// 004.context.md "Test shape" (a deferred promise per fetch call; an aborted stub rejects
// with a DOMException named "AbortError"; pure state tests, no rendering). Never from code.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Translation } from "../../src/app/translationApi";
import {
  TranslationState,
  cancelTranslation,
  disposeTranslations,
  flickTranslation,
  invalidateTranslation,
  translationView,
} from "../../src/app/translationState";
import { ApiError } from "../../src/shared/apiError";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- fixtures
// Both > Number.MAX_SAFE_INTEGER: a silent numeric coercion would change them.
const ROW_A = "7250000000000000101";
const ROW_B = "7250000000000000102";

const pathOf = (id: string): string => `/api/messages/${id}/translation`;
const postOf = (id: string): string => `POST ${pathOf(id)}`;

const TEXT_A = "Привет";
const TEXT_B = "Здравствуй";

/** The wire payload, with all four keys (context.md "Wire contract"). */
function translation(messageId: string, text: string, cached = false): Translation {
  return { message_id: messageId, target_language: "Russian", text, cached };
}

beforeEach(() => {
  notifyFailureSpy.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- fetch harness
function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelopeBody(code: string, messageId: string): unknown {
  return {
    error: {
      code,
      message: "The translation failed. Showing the original.",
      detail: { message_id: messageId },
    },
  };
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

type Call = {
  /** "METHOD pathname", keyed exactly — never a prefix. */
  readonly key: string;
  readonly method: string;
  readonly path: string;
  readonly signal: AbortSignal | undefined;
  /** Answer this one call. */
  respond: (body: unknown, status?: number) => void;
  /** Make this one call's fetch reject (a network error, say). */
  rejectWith: (reason: unknown) => void;
};

/** Named so `ReturnType` can give the mock a type without an instantiation expression. */
function fetchMock(impl: FetchFn) {
  return vi.fn<FetchFn>(impl);
}
type FetchMock = ReturnType<typeof fetchMock>;

type Backend = {
  readonly mock: FetchMock;
  readonly calls: Call[];
  keys: () => string[];
  call: (index: number) => Call;
};

/**
 * A fetch stub with one deferred promise per call, so a test can observe "pending" and then
 * resolve, reject or abort on demand (004.context.md "Test shape").
 *
 * With `rejectOnAbort` (the platform's behaviour, the default) a call rejects with a
 * `DOMException` named "AbortError" as soon as its signal aborts. With it off, the deferred
 * stays open after an abort, which is how a *late* answer to an aborted request is served.
 */
function stubDeferredFetch(options: { rejectOnAbort?: boolean } = {}): Backend {
  const rejectOnAbort = options.rejectOnAbort ?? true;
  const calls: Call[] = [];
  const mock = fetchMock((input, init) => {
    const url = requestUrl(input);
    const signal = init?.signal ?? (input instanceof Request ? input.signal : undefined);
    let settle!: (response: Response) => void;
    let fail!: (reason: unknown) => void;
    const promise = new Promise<Response>((resolve, reject) => {
      settle = resolve;
      fail = reject;
    });
    if (rejectOnAbort && signal !== undefined) {
      const onAbort = (): void => {
        fail(new DOMException("The operation was aborted.", "AbortError"));
      };
      if (signal.aborted) onAbort();
      else signal.addEventListener("abort", onAbort, { once: true });
    }
    calls.push({
      key: `${requestMethod(input, init)} ${url.pathname}`,
      method: requestMethod(input, init),
      path: url.pathname,
      signal,
      respond: (body, status = 200) => settle(jsonResponse(body, status)),
      rejectWith: fail,
    });
    return promise;
  });
  vi.stubGlobal("fetch", mock);
  return {
    mock,
    calls,
    keys: () => calls.map((entry) => entry.key),
    call: (index) => {
      const entry = calls[index];
      if (entry === undefined) throw new Error(`no fetch call at index ${index}`);
      return entry;
    },
  };
}

async function flush(rounds = 6): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await new Promise<void>((resolve) => setImmediate(resolve));
  }
}

function expectNotifiedOnceWith(code: string): void {
  expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
  const error = notifyFailureSpy.mock.calls[0]?.[0];
  expect(error).toBeInstanceOf(ApiError);
  expect((error as ApiError).code).toBe(code);
}

/** Flick a fresh row and let its request resolve with `text`: the row ends up translated. */
async function translateRow(
  state: TranslationState,
  backend: Backend,
  messageId: string,
  text: string,
): Promise<void> {
  const index = backend.calls.length;
  const flick = flickTranslation(state, messageId);
  await flush();
  backend.call(index).respond(translation(messageId, text));
  await flick;
}

// ===========================================================================
// DoD-2 — the first flick
// ===========================================================================
describe("flickTranslation — a fresh row", () => {
  it("is on the original before any flick — DoD-2", () => {
    stubDeferredFetch();
    const state = new TranslationState();
    expect(translationView(state, ROW_A)).toEqual({ status: "original" });
  });

  it("makes exactly one POST to that row's path and the view is pending while it is unresolved — DoD-2", async () => {
    const backend = stubDeferredFetch();
    const state = new TranslationState();

    const flick = flickTranslation(state, ROW_A);
    await flush();

    expect(backend.keys()).toEqual([postOf(ROW_A)]);
    expect(translationView(state, ROW_A)).toEqual({ status: "pending" });

    backend.call(0).respond(translation(ROW_A, TEXT_A));
    await flick;
    expect(backend.keys()).toEqual([postOf(ROW_A)]);
  });

  it("shows the answered text once the request resolves — DoD-2", async () => {
    const backend = stubDeferredFetch();
    const state = new TranslationState();

    await translateRow(state, backend, ROW_A, TEXT_A);

    expect(translationView(state, ROW_A)).toEqual({ status: "translated", text: TEXT_A });
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("the effect resolves and notifies nothing on success — DoD-2", async () => {
    const backend = stubDeferredFetch();
    const state = new TranslationState();
    const flick = flickTranslation(state, ROW_A);
    await flush();
    backend.call(0).respond(translation(ROW_A, TEXT_A));
    await expect(flick).resolves.toBeUndefined();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ===========================================================================
// DoD-3 / DoD-4 — flicking back, and flicking a cached row again
// ===========================================================================
describe("flickTranslation — the flick cycle and the request count", () => {
  it("flicking the translated row again shows the original and makes no request — DoD-3", async () => {
    const backend = stubDeferredFetch();
    const state = new TranslationState();
    await translateRow(state, backend, ROW_A, TEXT_A);
    expect(backend.mock).toHaveBeenCalledTimes(1);

    await flickTranslation(state, ROW_A);

    expect(translationView(state, ROW_A)).toEqual({ status: "original" });
    expect(backend.mock).toHaveBeenCalledTimes(1);
    expect(backend.keys()).toEqual([postOf(ROW_A)]);
  });

  it("a third flick shows the cached translation immediately, without awaiting, with fetch still called once in total — DoD-4", async () => {
    const backend = stubDeferredFetch();
    const state = new TranslationState();
    await translateRow(state, backend, ROW_A, TEXT_A);
    await flickTranslation(state, ROW_A);
    expect(translationView(state, ROW_A)).toEqual({ status: "original" });

    const third = flickTranslation(state, ROW_A);

    // Not awaited: the cached answer is on screen the moment the call returns.
    expect(translationView(state, ROW_A)).toEqual({ status: "translated", text: TEXT_A });
    expect(backend.mock).toHaveBeenCalledTimes(1);

    await third;
    await flush();
    expect(translationView(state, ROW_A)).toEqual({ status: "translated", text: TEXT_A });
    expect(backend.mock).toHaveBeenCalledTimes(1);
    expect(backend.keys()).toEqual([postOf(ROW_A)]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ===========================================================================
// DoD-5 / DoD-6 — the failure paths
// ===========================================================================
describe("flickTranslation — a 502 translation_failed answer", () => {
  it("leaves the view on the original, notifies exactly once with that code, and resolves — DoD-5", async () => {
    const backend = stubDeferredFetch();
    const state = new TranslationState();

    const flick = flickTranslation(state, ROW_A);
    await flush();
    backend.call(0).respond(envelopeBody("translation_failed", ROW_A), 502);

    await expect(flick).resolves.toBeUndefined();
    expect(translationView(state, ROW_A)).toEqual({ status: "original" });
    expectNotifiedOnceWith("translation_failed");
  });

  it("caches nothing, so the next flick makes a new POST — DoD-5", async () => {
    const backend = stubDeferredFetch();
    const state = new TranslationState();
    const failed = flickTranslation(state, ROW_A);
    await flush();
    backend.call(0).respond(envelopeBody("translation_failed", ROW_A), 502);
    await failed;

    const again = flickTranslation(state, ROW_A);
    await flush();

    expect(backend.keys()).toEqual([postOf(ROW_A), postOf(ROW_A)]);
    expect(translationView(state, ROW_A)).toEqual({ status: "pending" });

    backend.call(1).respond(translation(ROW_A, TEXT_A));
    await again;
    expect(translationView(state, ROW_A)).toEqual({ status: "translated", text: TEXT_A });
  });
});

describe("flickTranslation — a fetch rejecting with a TypeError", () => {
  it("leaves the view on the original, notifies exactly once, and resolves — DoD-6", async () => {
    const backend = stubDeferredFetch();
    const state = new TranslationState();

    const flick = flickTranslation(state, ROW_A);
    await flush();
    backend.call(0).rejectWith(new TypeError("Failed to fetch"));

    await expect(flick).resolves.toBeUndefined();
    expect(translationView(state, ROW_A)).toEqual({ status: "original" });
    expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
  });

  it("caches nothing, so the next flick makes a new POST — DoD-6", async () => {
    const backend = stubDeferredFetch();
    const state = new TranslationState();
    const failed = flickTranslation(state, ROW_A);
    await flush();
    backend.call(0).rejectWith(new TypeError("Failed to fetch"));
    await failed;

    const again = flickTranslation(state, ROW_A);
    await flush();

    expect(backend.keys()).toEqual([postOf(ROW_A), postOf(ROW_A)]);
    expect(translationView(state, ROW_A)).toEqual({ status: "pending" });

    backend.call(1).respond(translation(ROW_A, TEXT_A));
    await again;
    expect(translationView(state, ROW_A)).toEqual({ status: "translated", text: TEXT_A });
  });
});

// ===========================================================================
// DoD-7 — a stop is not a failure
// ===========================================================================
describe("cancelling a pending row", () => {
  it("flicking a pending row aborts its signal, returns the view to the original, notifies nothing and issues no second request — DoD-7", async () => {
    const backend = stubDeferredFetch();
    const state = new TranslationState();

    const first = flickTranslation(state, ROW_A);
    await flush();
    const inflight = backend.call(0);
    expect(inflight.signal?.aborted).toBe(false);
    expect(translationView(state, ROW_A)).toEqual({ status: "pending" });

    const second = flickTranslation(state, ROW_A);
    await flush();
    await Promise.all([first, second]);
    await flush();

    expect(inflight.signal?.aborted).toBe(true);
    expect(translationView(state, ROW_A)).toEqual({ status: "original" });
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(backend.keys()).toEqual([postOf(ROW_A)]);
  });

  it("cancelTranslation on a pending row aborts its signal, returns the view to the original and notifies nothing — DoD-7", async () => {
    const backend = stubDeferredFetch();
    const state = new TranslationState();

    const flick = flickTranslation(state, ROW_A);
    await flush();
    const inflight = backend.call(0);
    expect(inflight.signal?.aborted).toBe(false);

    cancelTranslation(state, ROW_A);
    expect(inflight.signal?.aborted).toBe(true);

    await flick;
    await flush();
    expect(translationView(state, ROW_A)).toEqual({ status: "original" });
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(backend.keys()).toEqual([postOf(ROW_A)]);
  });

  it("after a cancel the next flick makes a new POST, whose answer is shown — DoD-7", async () => {
    const backend = stubDeferredFetch();
    const state = new TranslationState();
    const cancelled = flickTranslation(state, ROW_A);
    await flush();
    cancelTranslation(state, ROW_A);
    await cancelled;
    await flush();

    const again = flickTranslation(state, ROW_A);
    await flush();
    expect(backend.keys()).toEqual([postOf(ROW_A), postOf(ROW_A)]);
    expect(translationView(state, ROW_A)).toEqual({ status: "pending" });

    backend.call(1).respond(translation(ROW_A, TEXT_A));
    await again;
    expect(translationView(state, ROW_A)).toEqual({ status: "translated", text: TEXT_A });
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("cancelTranslation on a row with nothing in flight changes nothing and notifies nothing — DoD-7", async () => {
    const backend = stubDeferredFetch();
    const state = new TranslationState();

    cancelTranslation(state, ROW_A);
    await flush();

    expect(translationView(state, ROW_A)).toEqual({ status: "original" });
    expect(backend.keys()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ===========================================================================
// DoD-8 — invalidation
// ===========================================================================
describe("invalidateTranslation", () => {
  it("on a translated row shows the original, and the next flick POSTs again and shows the new answer — DoD-8", async () => {
    const backend = stubDeferredFetch();
    const state = new TranslationState();
    await translateRow(state, backend, ROW_A, TEXT_A);
    expect(translationView(state, ROW_A)).toEqual({ status: "translated", text: TEXT_A });

    invalidateTranslation(state, ROW_A);
    expect(translationView(state, ROW_A)).toEqual({ status: "original" });

    const again = flickTranslation(state, ROW_A);
    await flush();
    expect(backend.keys()).toEqual([postOf(ROW_A), postOf(ROW_A)]);

    backend.call(1).respond(translation(ROW_A, "Добрый день"));
    await again;
    expect(translationView(state, ROW_A)).toEqual({ status: "translated", text: "Добрый день" });
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("on a pending row aborts the request, leaves the original showing and notifies nothing — DoD-8", async () => {
    const backend = stubDeferredFetch();
    const state = new TranslationState();
    const flick = flickTranslation(state, ROW_A);
    await flush();
    const inflight = backend.call(0);
    expect(inflight.signal?.aborted).toBe(false);

    invalidateTranslation(state, ROW_A);
    expect(inflight.signal?.aborted).toBe(true);

    await flick;
    await flush();
    expect(translationView(state, ROW_A)).toEqual({ status: "original" });
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("a response arriving after an invalidation writes nothing: the view stays original and nothing is cached — DoD-8", async () => {
    // The stub keeps the deferred open past the abort, so the answer lands *late*.
    const backend = stubDeferredFetch({ rejectOnAbort: false });
    const state = new TranslationState();
    const flick = flickTranslation(state, ROW_A);
    await flush();
    const inflight = backend.call(0);

    invalidateTranslation(state, ROW_A);
    expect(inflight.signal?.aborted).toBe(true);

    inflight.respond(translation(ROW_A, TEXT_A));
    await flick;
    await flush();

    expect(translationView(state, ROW_A)).toEqual({ status: "original" });
    expect(notifyFailureSpy).not.toHaveBeenCalled();

    // Nothing cached: the next flick has to ask again.
    const again = flickTranslation(state, ROW_A);
    await flush();
    expect(backend.keys()).toEqual([postOf(ROW_A), postOf(ROW_A)]);
    expect(translationView(state, ROW_A)).toEqual({ status: "pending" });

    backend.call(1).respond(translation(ROW_A, TEXT_A));
    await again;
    expect(translationView(state, ROW_A)).toEqual({ status: "translated", text: TEXT_A });
  });
});

// ===========================================================================
// DoD-9 — rows are independent
// ===========================================================================
describe("rows are independent", () => {
  it("with A pending and B translated, flicking B shows its original and cancelling A leaves B's cached text intact, each on its own path — DoD-9", async () => {
    const backend = stubDeferredFetch();
    const state = new TranslationState();

    await translateRow(state, backend, ROW_B, TEXT_B);
    const pendingA = flickTranslation(state, ROW_A);
    await flush();

    expect(backend.keys()).toEqual([postOf(ROW_B), postOf(ROW_A)]);
    expect(backend.call(0).path).toBe(pathOf(ROW_B));
    expect(backend.call(1).path).toBe(pathOf(ROW_A));
    expect(translationView(state, ROW_A)).toEqual({ status: "pending" });
    expect(translationView(state, ROW_B)).toEqual({ status: "translated", text: TEXT_B });

    // Flicking B back touches neither A's request nor A's view.
    await flickTranslation(state, ROW_B);
    expect(translationView(state, ROW_B)).toEqual({ status: "original" });
    expect(translationView(state, ROW_A)).toEqual({ status: "pending" });
    expect(backend.call(1).signal?.aborted).toBe(false);

    cancelTranslation(state, ROW_A);
    await pendingA;
    await flush();
    expect(backend.call(1).signal?.aborted).toBe(true);
    expect(translationView(state, ROW_A)).toEqual({ status: "original" });

    // B's cached text survived A's cancel: flicking it costs no request.
    await flickTranslation(state, ROW_B);
    expect(translationView(state, ROW_B)).toEqual({ status: "translated", text: TEXT_B });
    expect(backend.keys()).toEqual([postOf(ROW_B), postOf(ROW_A)]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ===========================================================================
// DoD-10 — dispose
// ===========================================================================
describe("disposeTranslations", () => {
  it("aborts both pending rows' signals and notifies neither — DoD-10", async () => {
    const backend = stubDeferredFetch();
    const state = new TranslationState();

    const pendingA = flickTranslation(state, ROW_A);
    const pendingB = flickTranslation(state, ROW_B);
    await flush();
    expect(backend.keys()).toEqual([postOf(ROW_A), postOf(ROW_B)]);
    expect(backend.call(0).signal?.aborted).toBe(false);
    expect(backend.call(1).signal?.aborted).toBe(false);

    disposeTranslations(state);

    expect(backend.call(0).signal?.aborted).toBe(true);
    expect(backend.call(1).signal?.aborted).toBe(true);

    await Promise.all([pendingA, pendingB]);
    await flush();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("with nothing pending it notifies nothing and issues no request — DoD-10", async () => {
    const backend = stubDeferredFetch();
    const state = new TranslationState();

    disposeTranslations(state);
    await flush();

    expect(backend.keys()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ===========================================================================
// DoD-11 — pure data contracts
// ===========================================================================
describe("TranslationState — observable fields only", () => {
  it("its prototype has no own property besides constructor (no methods, no getters) — DoD-11", () => {
    // Only string-named own properties are meaningful here: a method or a getter on
    // TranslationState would show up in getOwnPropertyNames. Symbol keys are not checked,
    // because MobX stores a Symbol(mobx-keys) bookkeeping key on the prototype of any class
    // whose instances have been built with makeAutoObservable — present on a correct
    // implementation, and unrelated to the no-methods/no-getters contract.
    expect(Object.getOwnPropertyNames(TranslationState.prototype)).toEqual(["constructor"]);
  });
});
