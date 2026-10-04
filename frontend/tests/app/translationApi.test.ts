// Feature 023, step 004 — the translate call (DoD-1).
//
// Expected values come from the step file's Interface intent and Definition of done plus
// context.md's "Wire contract" (POST /api/messages/{message_id}/translation, no request
// body, ids as decimal strings, `translation_failed` on 502) and 004.context.md
// ("Built state at the touch sites": apiPost threads the signal into fetch, throws
// ApiError on non-2xx and rethrows an abort raw). Never from code.
import { describe, expect, it, vi, afterEach } from "vitest";
import { translateMessage, type Translation } from "../../src/app/translationApi";
import { ApiError, isApiError } from "../../src/shared/apiError";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// > Number.MAX_SAFE_INTEGER: a silent numeric coercion would change it.
const MESSAGE_ID = "7250000000000000101";
const TRANSLATION_PATH = `/api/messages/${MESSAGE_ID}/translation`;

/** The wire payload, with all four keys (context.md "Wire contract"). */
const TRANSLATION: Translation = {
  message_id: MESSAGE_ID,
  target_language: "Russian",
  text: "Привет",
  cached: false,
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- harness
function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function stubFetch(impl: FetchFn) {
  const mock = vi.fn<FetchFn>(impl);
  vi.stubGlobal("fetch", mock);
  return mock;
}

function serve(body: unknown, status = 200) {
  return stubFetch(() => Promise.resolve(jsonResponse(body, status)));
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

type Seen = { method: string; path: string; search: string };

/** Every request the stub saw, keyed on exact pathname and method (never a prefix). */
function seen(mock: ReturnType<typeof stubFetch>): Seen[] {
  return mock.mock.calls.map(([input, init]) => {
    const url = requestUrl(input);
    return { method: requestMethod(input, init), path: url.pathname, search: url.search };
  });
}

function signalOf(mock: ReturnType<typeof stubFetch>, index: number): AbortSignal | undefined {
  const [input, init] = mock.mock.calls[index] ?? [];
  return init?.signal ?? (input instanceof Request ? input.signal : undefined);
}

function envelope(code: string): unknown {
  return { error: { code, message: "The translation failed. Showing the original.", detail: { message_id: MESSAGE_ID } } };
}

/** The rejection of a call that must not resolve. */
async function rejection(call: () => Promise<unknown>): Promise<unknown> {
  return call().then(
    () => {
      throw new Error("the call resolved, but it should have rejected");
    },
    (reason: unknown) => reason,
  );
}

// ===========================================================================
describe("translateMessage — the request", () => {
  it("issues exactly one POST /api/messages/7250000000000000101/translation — DoD-1", async () => {
    const mock = serve(TRANSLATION);
    await translateMessage(MESSAGE_ID);
    expect(seen(mock)).toEqual([{ method: "POST", path: TRANSLATION_PATH, search: "" }]);
  });

  it("passes the signal it was given to that one fetch — DoD-1", async () => {
    const controller = new AbortController();
    const mock = serve(TRANSLATION);
    await translateMessage(MESSAGE_ID, controller.signal);
    expect(mock).toHaveBeenCalledTimes(1);
    expect(seen(mock)).toEqual([{ method: "POST", path: TRANSLATION_PATH, search: "" }]);
    expect(signalOf(mock, 0)).toBe(controller.signal);
  });

  it("sends no request body — DoD-1", async () => {
    const mock = serve(TRANSLATION);
    await translateMessage(MESSAGE_ID);
    const init = mock.mock.calls[0]?.[1];
    expect(init?.body ?? undefined).toBeUndefined();
  });
});

// ===========================================================================
describe("translateMessage — the answer", () => {
  it("resolves to the stubbed Translation, with message_id a string — DoD-1", async () => {
    serve(TRANSLATION);
    const translation = await translateMessage(MESSAGE_ID);
    expect(translation).toEqual({
      message_id: MESSAGE_ID,
      target_language: "Russian",
      text: "Привет",
      cached: false,
    });
    expect(typeof translation.message_id).toBe("string");
    expect(translation.message_id).toBe(MESSAGE_ID);
  });

  it("resolves to a cached answer unchanged — DoD-1", async () => {
    const cached: Translation = { ...TRANSLATION, cached: true };
    serve(cached);
    await expect(translateMessage(MESSAGE_ID)).resolves.toEqual(cached);
  });

  it("a 502 translation_failed envelope rejects with an ApiError whose code is translation_failed — DoD-1", async () => {
    serve(envelope("translation_failed"), 502);
    const error = await rejection(() => translateMessage(MESSAGE_ID));
    expect(error).toBeInstanceOf(ApiError);
    expect(isApiError(error) ? error.code : null).toBe("translation_failed");
  });
});
