// Feature 002, step 004 — the API client (DoD-4..DoD-16).
// `fetch` is replaced per test with a stub answering platform `Response` objects;
// the 401 document navigation is observed through the frozen `documentNavigation` seam.
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import {
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  apiRequest,
  documentNavigation,
} from "../../src/shared/api";
import {
  ApiError,
  CLIENT_MALFORMED_ERROR,
  CLIENT_TRANSPORT_FAILED,
  isApiError,
} from "../../src/shared/apiError";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

let nav: MockInstance<(url: string) => void>;

beforeEach(() => {
  nav = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- helpers

function stubFetch(impl: FetchFn) {
  const mock = vi.fn<FetchFn>(impl);
  vi.stubGlobal("fetch", mock);
  return mock;
}

/** Every call answers a fresh Response built by `make` (a body can be read once). */
function respondWith(make: () => Response) {
  return stubFetch(() => Promise.resolve(make()));
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, message: string, detail: Record<string, unknown>) {
  return { error: { code, message, detail } };
}

type Recorded = {
  url: string;
  method: string;
  headers: Headers;
  credentials: RequestCredentials | undefined;
  body: unknown;
};

function recorded(mock: ReturnType<typeof stubFetch>, index = 0): Recorded {
  const call = mock.mock.calls[index];
  if (call === undefined) throw new Error(`fetch was not called (call #${index})`);
  const [input, init] = call;
  const req = input instanceof Request ? input : undefined;
  const url =
    typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  const headers = new Headers(req?.headers);
  new Headers(init?.headers).forEach((value, key) => headers.set(key, value));
  return {
    url,
    method: (init?.method ?? req?.method ?? "GET").toUpperCase(),
    headers,
    credentials: init?.credentials ?? req?.credentials,
    body: init?.body,
  };
}

const NO_REJECTION = Symbol("no rejection");

/** Runs `fn`, returning what it threw or rejected with (sync throw or async rejection). */
async function captureError(fn: () => unknown): Promise<unknown> {
  try {
    await fn();
  } catch (e) {
    return e;
  }
  return NO_REJECTION;
}

function expectApiError(value: unknown): ApiError {
  expect(value).not.toBe(NO_REJECTION);
  expect(value).toBeInstanceOf(ApiError);
  return value as ApiError;
}

function flush(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

// ---------------------------------------------------------------- 2xx

describe("successful responses", () => {
  it("resolves a 2xx JSON response to the parsed body with every id still a string__DoD4", async () => {
    type Payload = {
      id: string;
      name: string;
      character: { id: string; zone_id: string };
      messages: Array<{ id: string; parent_id?: string; tags?: Array<{ id: string }> }>;
    };
    const payload: Payload = {
      id: "9007199254740993",
      name: "Mira",
      character: { id: "0012", zone_id: "18446744073709551615" },
      messages: [
        { id: "1", parent_id: "2" },
        { id: "3", tags: [{ id: "4" }, { id: "0" }] },
      ],
    };
    respondWith(() => jsonResponse(payload, 200));

    const result = await apiGet<Payload>("/api/characters/9007199254740993");

    expect(result).toStrictEqual(payload);
    expect(result.id).toBe("9007199254740993");
    expect(result.character.id).toBe("0012");
    expect(result.character.zone_id).toBe("18446744073709551615");
    expect(typeof result.messages[0]?.id).toBe("string");
    expect(result.messages[0]?.parent_id).toBe("2");
    expect(result.messages[1]?.tags?.[0]?.id).toBe("4");
    expect(result.messages[1]?.tags?.[1]?.id).toBe("0");
  });

  it("resolves a 201 JSON response to the parsed body__DoD4", async () => {
    respondWith(() => jsonResponse({ id: "42" }, 201));
    await expect(apiPost("/api/characters", { name: "Mira" })).resolves.toStrictEqual({ id: "42" });
  });

  it("resolves a 204 to nothing rather than throwing__DoD5", async () => {
    respondWith(() => new Response(null, { status: 204 }));
    await expect(apiDelete("/api/characters/1")).resolves.toBeUndefined();
  });

  it("resolves an empty 200 body to nothing rather than throwing__DoD5", async () => {
    respondWith(() => new Response("", { status: 200 }));
    await expect(apiPost("/api/zones/1/reopen")).resolves.toBeUndefined();
  });

  it("resolves an empty 200 body labelled JSON to nothing rather than throwing__DoD5", async () => {
    respondWith(
      () => new Response("", { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    await expect(apiPatch("/api/characters/1", { name: "Mira" })).resolves.toBeUndefined();
  });
});

// ---------------------------------------------------------------- non-2xx

describe("error envelopes", () => {
  it.each([400, 404, 409, 422, 500, 502, 503])(
    "throws an ApiError carrying the envelope's code/message/detail and status %i__DoD6",
    async (status) => {
      const detail = { field: "name", conflicting_id: "77" };
      respondWith(() =>
        jsonResponse(envelope("zone_not_empty", "The zone is not empty.", detail), status),
      );

      const err = expectApiError(await captureError(() => apiGet("/api/zones/77")));

      expect(err.code).toBe("zone_not_empty");
      expect(err.message).toBe("The zone is not empty.");
      expect(err.detail).toStrictEqual({ field: "name", conflicting_id: "77" });
      expect(err.status).toBe(status);
    },
  );

  it("keeps a 5xx envelope's own code rather than a synthetic one__DoD6", async () => {
    respondWith(() =>
      jsonResponse(envelope("translation_failed", "Translation failed.", {}), 500),
    );
    const err = expectApiError(await captureError(() => apiPost("/api/translate", { text: "x" })));
    expect(err.code).toBe("translation_failed");
    expect(err.code).not.toBe(CLIENT_MALFORMED_ERROR);
    expect(err.status).toBe(500);
  });

  const malformed: Array<[string, number, () => Response]> = [
    ["an empty body", 500, () => new Response("", { status: 500 })],
    ["no body at all", 503, () => new Response(null, { status: 503 })],
    [
      "an HTML error page",
      502,
      () =>
        new Response("<html><body><h1>502 Bad Gateway</h1></body></html>", {
          status: 502,
          headers: { "Content-Type": "text/html" },
        }),
    ],
    [
      "plain text",
      400,
      () => new Response("Bad Request", { status: 400, headers: { "Content-Type": "text/plain" } }),
    ],
    [
      "invalid JSON labelled as JSON",
      500,
      () =>
        new Response("{not json", { status: 500, headers: { "Content-Type": "application/json" } }),
    ],
    ["JSON of another shape (object)", 404, () => jsonResponse({ detail: "Not Found" }, 404)],
    ["JSON of another shape (array)", 422, () => jsonResponse([{ code: "x" }], 422)],
    ["JSON of another shape (string)", 500, () => jsonResponse("Internal Server Error", 500)],
    ["JSON null", 500, () => jsonResponse(null, 500)],
    ["an error member that is not an object", 409, () => jsonResponse({ error: "conflict" }, 409)],
  ];

  it.each(malformed)(
    "throws an ApiError with the malformed-body code for %s, keeping the real status__DoD7",
    async (_label, status, make) => {
      respondWith(make);

      const err = expectApiError(await captureError(() => apiGet("/api/things")));

      expect(err.code).toBe(CLIENT_MALFORMED_ERROR);
      expect(err.code).toBe("client_malformed_error");
      expect(err.status).toBe(status);
    },
  );
});

// ---------------------------------------------------------------- transport and abort

describe("transport failure", () => {
  it("wraps a rejected fetch (no abort) into an ApiError with the transport code and status 0__DoD8", async () => {
    stubFetch(() => Promise.reject(new TypeError("Failed to fetch")));

    const err = expectApiError(await captureError(() => apiGet("/api/characters")));

    expect(err.code).toBe(CLIENT_TRANSPORT_FAILED);
    expect(err.code).toBe("client_transport_failed");
    expect(err.status).toBe(0);
  });

  it("wraps a rejected fetch as transport failure even when a signal was passed but never aborted__DoD8", async () => {
    stubFetch(() => Promise.reject(new TypeError("NetworkError when attempting to fetch resource.")));
    const controller = new AbortController();

    const err = expectApiError(
      await captureError(() => apiPost("/api/characters", { name: "Mira" }, controller.signal)),
    );

    expect(err.code).toBe(CLIENT_TRANSPORT_FAILED);
    expect(err.status).toBe(0);
  });
});

describe("caller abort", () => {
  /** Behaves like the platform fetch: rejects with the signal's reason once it aborts. */
  function abortableFetch(): FetchFn {
    return (_input, init) =>
      new Promise<Response>((_resolve, reject) => {
        const signal = init?.signal;
        if (!signal) return; // never settles without a signal
        if (signal.aborted) {
          reject(signal.reason);
          return;
        }
        signal.addEventListener("abort", () => reject(signal.reason), { once: true });
      });
  }

  function expectUnwrappedAbort(caught: unknown, controller: AbortController): void {
    expect(caught).not.toBe(NO_REJECTION);
    expect(caught).toBe(controller.signal.reason);
    expect(caught).not.toBeInstanceOf(ApiError);
    expect(isApiError(caught)).toBe(false);
    const code = (caught as { code?: unknown }).code;
    expect(code).not.toBe(CLIENT_TRANSPORT_FAILED);
    expect(code).not.toBe(CLIENT_MALFORMED_ERROR);
    expect((caught as { name?: unknown }).name).toBe("AbortError");
  }

  it("propagates an abort during fetch unchanged, not as an ApiError__DoD9", async () => {
    const mock = stubFetch(abortableFetch());
    const controller = new AbortController();

    const pending = captureError(() => apiGet("/api/characters", controller.signal));
    await vi.waitFor(() => expect(mock).toHaveBeenCalled());
    controller.abort();

    expectUnwrappedAbort(await pending, controller);
  });

  it("propagates a signal already aborted before the call unchanged__DoD9", async () => {
    stubFetch(abortableFetch());
    const controller = new AbortController();
    controller.abort();

    expectUnwrappedAbort(
      await captureError(() => apiPatch("/api/characters/1", { name: "x" }, controller.signal)),
      controller,
    );
  });

  it("propagates an abort during the body read unchanged, not as an ApiError__DoD9", async () => {
    const controller = new AbortController();
    const signal = controller.signal;

    const rejectOnAbort = <T>(): Promise<T> =>
      new Promise<T>((_resolve, reject) => {
        if (signal.aborted) {
          reject(signal.reason);
          return;
        }
        signal.addEventListener("abort", () => reject(signal.reason), { once: true });
      });

    const mock = stubFetch(() => {
      const stream = new ReadableStream<Uint8Array>({
        start(streamController) {
          signal.addEventListener("abort", () => streamController.error(signal.reason), {
            once: true,
          });
        },
      });
      const response = new Response(stream, {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
      // A body read in flight rejects with the abort reason, as the platform does.
      Object.defineProperty(response, "json", { value: () => rejectOnAbort<unknown>() });
      Object.defineProperty(response, "text", { value: () => rejectOnAbort<string>() });
      Object.defineProperty(response, "arrayBuffer", { value: () => rejectOnAbort<ArrayBuffer>() });
      Object.defineProperty(response, "blob", { value: () => rejectOnAbort<Blob>() });
      return Promise.resolve(response);
    });

    const pending = captureError(() => apiGet("/api/characters", signal));
    await vi.waitFor(() => expect(mock).toHaveBeenCalled());
    await flush();
    controller.abort();

    expectUnwrappedAbort(await pending, controller);
  });
});

// ---------------------------------------------------------------- 401 / 403

describe("authentication and authorization failures", () => {
  it("navigates the document to /login on a 401 and still rejects__DoD10", async () => {
    respondWith(() =>
      jsonResponse(envelope("not_authenticated", "Not signed in.", {}), 401),
    );

    const caught = await captureError(() => apiGet("/api/me"));

    expect(nav).toHaveBeenCalledWith("/login");
    expect(nav).toHaveBeenCalledTimes(1);
    const err = expectApiError(caught);
    expect(err.status).toBe(401);
  });

  it("navigates to /login on a 401 with an unreadable body and still rejects__DoD10", async () => {
    respondWith(() => new Response("", { status: 401 }));

    const caught = await captureError(() => apiPost("/api/characters", { name: "x" }));

    expect(nav).toHaveBeenCalledWith("/login");
    expect(caught).not.toBe(NO_REJECTION);
  });

  it("does not run the awaiting caller's continuation after a 401__DoD10", async () => {
    respondWith(() => jsonResponse(envelope("not_authenticated", "Not signed in.", {}), 401));
    const continuation = vi.fn();

    await captureError(async () => {
      await apiGet("/api/characters");
      continuation();
    });

    expect(nav).toHaveBeenCalledWith("/login");
    expect(continuation).not.toHaveBeenCalled();
  });

  it("does not navigate on a 403 and rejects with the envelope's code__DoD11", async () => {
    respondWith(() =>
      jsonResponse(envelope("account_disabled", "This account is disabled.", {}), 403),
    );

    const err = expectApiError(await captureError(() => apiGet("/api/admin/users")));

    expect(nav).not.toHaveBeenCalled();
    expect(err.code).toBe("account_disabled");
    expect(err.status).toBe(403);
  });
});

// ---------------------------------------------------------------- request shape

describe("request shape", () => {
  it.each(["/api/characters", "/api/characters/42/messages?limit=20&before=9007199254740993"])(
    "issues the request to %s exactly as given, with no host or scheme__DoD12",
    async (path) => {
      const mock = respondWith(() => jsonResponse({}, 200));

      await apiGet(path);

      expect(mock).toHaveBeenCalledTimes(1);
      const { url } = recorded(mock);
      expect(url).toBe(path);
      expect(url).not.toMatch(/^[a-z][a-z0-9+.-]*:/i);
      expect(url.startsWith("//")).toBe(false);
    },
  );

  it("sends credentials and no Authorization header on a bodiless request__DoD13", async () => {
    const mock = respondWith(() => jsonResponse({}, 200));

    await apiGet("/api/characters");

    const call = recorded(mock);
    expect(["include", "same-origin"]).toContain(call.credentials);
    expect(call.headers.has("Authorization")).toBe(false);
  });

  it("sends credentials and no Authorization header on a request with a body__DoD13", async () => {
    const mock = respondWith(() => jsonResponse({}, 200));

    await apiPost("/api/characters", { name: "Mira" });

    const call = recorded(mock);
    expect(["include", "same-origin"]).toContain(call.credentials);
    expect(call.headers.has("Authorization")).toBe(false);
  });

  it("sets no content-type header and sends no body when there is no body__DoD14", async () => {
    const mock = respondWith(() => jsonResponse({}, 200));

    await apiGet("/api/characters");
    await apiDelete("/api/characters/1");

    for (const index of [0, 1]) {
      const call = recorded(mock, index);
      expect(call.headers.has("Content-Type")).toBe(false);
      expect(call.body == null).toBe(true);
    }
  });

  it("sets a JSON content type and a JSON-serialised body when there is a body__DoD14", async () => {
    const mock = respondWith(() => jsonResponse({}, 200));
    const payload = {
      name: "Mira",
      zone_id: "9007199254740993",
      tags: ["a", "b"],
      nested: { parent_id: "0012", enabled: true, note: null },
    };

    await apiPatch("/api/characters/1", payload);

    const call = recorded(mock);
    expect(call.headers.get("Content-Type") ?? "").toMatch(/^application\/json\b/i);
    expect(typeof call.body).toBe("string");
    expect(call.body).toBe(JSON.stringify(payload));
    expect(JSON.parse(call.body as string)).toStrictEqual(payload);
  });

  it("rejects a path not beginning /api/ before any network call__DoD15", async () => {
    const mock = respondWith(() => jsonResponse({}, 200));

    // Control: a valid path does reach fetch.
    await apiGet("/api/ok");
    expect(mock).toHaveBeenCalledTimes(1);

    const badPaths = [
      "api/characters",
      "/api",
      "/apix/characters",
      "/login",
      "",
      "http://localhost:8184/api/characters",
      "https://example.com/api/characters",
      "//example.com/api/characters",
    ];
    for (const path of badPaths) {
      const caught = await captureError(() => apiRequest(path, "GET"));
      expect(caught, `path ${JSON.stringify(path)} should be rejected`).not.toBe(NO_REJECTION);
    }
    expect(await captureError(() => apiPost("/admin/users", { a: 1 }))).not.toBe(NO_REJECTION);

    expect(mock).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------- helpers' methods

describe("method helpers", () => {
  it("apiGet issues GET__DoD16", async () => {
    const mock = respondWith(() => jsonResponse({}, 200));
    await apiGet("/api/things");
    expect(recorded(mock).method).toBe("GET");
  });

  it("apiPost issues POST__DoD16", async () => {
    const mock = respondWith(() => jsonResponse({}, 200));
    await apiPost("/api/things", { a: "1" });
    expect(recorded(mock).method).toBe("POST");
  });

  it("apiPatch issues PATCH__DoD16", async () => {
    const mock = respondWith(() => jsonResponse({}, 200));
    await apiPatch("/api/things/1", { a: "1" });
    expect(recorded(mock).method).toBe("PATCH");
  });

  it("apiDelete issues DELETE__DoD16", async () => {
    const mock = respondWith(() => new Response(null, { status: 204 }));
    await apiDelete("/api/things/1");
    expect(recorded(mock).method).toBe("DELETE");
  });

  it("apiRequest issues the method it is given__DoD16", async () => {
    const mock = respondWith(() => jsonResponse({}, 200));
    await apiRequest("/api/things/1", "PATCH", { a: "1" });
    expect(recorded(mock).method).toBe("PATCH");
  });
});
