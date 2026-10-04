// Feature 022, step 003 — the discussion read and the client Message tool fields (DoD-4..6).
//
// Expected values come from the step file's Interface intent and DoD, context.md D1 (the
// route and its {"messages": [...]} envelope), D3 (the tool view shapes) and D15 (the three
// tool fields are optional and nullable), and frontend-structure.md "The API client"
// (ApiErrors rethrown unchanged; an abort is not wrapped). Never from code.
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, isApiError } from "../../src/shared/apiError";
import { fetchDiscussion, type Message, type ToolStatus } from "../../src/app/streamApi";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// Every id is > Number.MAX_SAFE_INTEGER: a silent numeric coercion would change it.
const ENTRY_ID = "7250000000000000042";
const SESSION_ID = "7250000000000000001";
// Deliberately not ascending in served order: the client must never re-sort.
const USER_ROW_ID = "7250000000000000203";
const TOOL_ROW_ID = "7250000000000000201";
const ASSISTANT_ROW_ID = "7250000000000000202";

const STAMP = "2026-10-02T09:26:53.000000+00:00";

const USER_ROW: Message = {
  id: USER_ROW_ID,
  session_id: SESSION_ID,
  role: "user",
  kind: null,
  text: "Where is the keeper?",
  settled_at: null,
  created_at: STAMP,
  updated_at: STAMP,
  tool_name: null,
  tool_status: null,
  tool_args: null,
};

const TOOL_ROW: Message = {
  id: TOOL_ROW_ID,
  session_id: SESSION_ID,
  role: "tool",
  kind: null,
  text: "Found 2 memos.",
  settled_at: null,
  created_at: STAMP,
  updated_at: STAMP,
  tool_name: "memo_search",
  tool_status: "ok",
  tool_args: { query: "lighthouse" },
};

const ASSISTANT_ROW: Message = {
  id: ASSISTANT_ROW_ID,
  session_id: SESSION_ID,
  role: "assistant",
  kind: null,
  text: "<think>plan</think>\n\nShe climbs the stairs.",
  settled_at: null,
  created_at: STAMP,
  updated_at: STAMP,
  tool_name: null,
  tool_status: null,
  tool_args: null,
};

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

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
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

/** Every request the stub saw, by exact pathname plus query string (never a prefix). */
function seen(mock: ReturnType<typeof stubFetch>): Seen[] {
  return mock.mock.calls.map(([input, init]) => {
    const url = requestUrl(input);
    return { method: requestMethod(input, init), path: url.pathname, search: url.search };
  });
}

function envelope(code: string, message: string): unknown {
  return { error: { code, message, detail: {} } };
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

// ---------------------------------------------------------------------------
describe("fetchDiscussion — the request and the unwrapped answer", () => {
  it("issues exactly one GET /api/messages/7250000000000000042/discussion — DoD-4", async () => {
    const mock = serve({ messages: [] });
    await fetchDiscussion("7250000000000000042");
    expect(seen(mock)).toEqual([
      { method: "GET", path: "/api/messages/7250000000000000042/discussion", search: "" },
    ]);
  });

  it("resolves to the served messages array, unwrapped, in the served order — DoD-4", async () => {
    serve({ messages: [USER_ROW, TOOL_ROW, ASSISTANT_ROW] });
    const rows = await fetchDiscussion(ENTRY_ID);
    expect(rows).toEqual([USER_ROW, TOOL_ROW, ASSISTANT_ROW]);
    expect(rows.map((row) => row.id)).toEqual([USER_ROW_ID, TOOL_ROW_ID, ASSISTANT_ROW_ID]);
  });

  it("resolves to an empty array for {\"messages\": []} — DoD-4", async () => {
    serve({ messages: [] });
    await expect(fetchDiscussion(ENTRY_ID)).resolves.toEqual([]);
  });

  it("a tool message's tool_name, tool_status and tool_args come through unchanged — DoD-4", async () => {
    serve({ messages: [USER_ROW, TOOL_ROW, ASSISTANT_ROW] });
    const rows = await fetchDiscussion(ENTRY_ID);
    const tool = rows.find((row) => row.id === TOOL_ROW_ID);
    expect(tool?.role).toBe("tool");
    expect(tool?.tool_name).toBe("memo_search");
    expect(tool?.tool_status).toBe("ok");
    expect(tool?.tool_args).toEqual({ query: "lighthouse" });
  });

  it("a failed tool row's status and empty args come through unchanged — DoD-4", async () => {
    const failed: Message = {
      ...TOOL_ROW,
      text: "The tool failed.",
      tool_status: "failed",
      tool_args: {},
    };
    serve({ messages: [failed] });
    const rows = await fetchDiscussion(ENTRY_ID);
    expect(rows).toEqual([failed]);
    expect(rows[0]?.tool_status).toBe("failed");
    expect(rows[0]?.tool_args).toEqual({});
  });

  it("keeps every id the identical string the payload carried — DoD-4", async () => {
    serve({ messages: [USER_ROW, TOOL_ROW, ASSISTANT_ROW] });
    const rows = await fetchDiscussion(ENTRY_ID);
    for (const row of rows) {
      expect(typeof row.id).toBe("string");
      expect(row.session_id).toBe(SESSION_ID);
    }
  });

  it("percent-encodes an id containing / in the path — DoD-4", async () => {
    const mock = serve({ messages: [] });
    await fetchDiscussion("a/b");
    expect(seen(mock)).toEqual([
      { method: "GET", path: `/api/messages/${encodeURIComponent("a/b")}/discussion`, search: "" },
    ]);
    expect(seen(mock)[0]?.path).toBe("/api/messages/a%2Fb/discussion");
  });

  it("passes the signal it was given to fetch — DoD-5", async () => {
    const controller = new AbortController();
    const mock = serve({ messages: [] });
    await fetchDiscussion(ENTRY_ID, controller.signal);
    expect(mock).toHaveBeenCalledTimes(1);
    const [input, init] = mock.mock.calls[0] ?? [];
    const signal = init?.signal ?? (input instanceof Request ? input.signal : undefined);
    expect(signal).toBe(controller.signal);
  });
});

// ---------------------------------------------------------------------------
describe("fetchDiscussion — failures and aborts", () => {
  it("a 404 message_not_found envelope rejects with an ApiError whose code is message_not_found — DoD-5", async () => {
    serve(envelope("message_not_found", "No such message."), 404);
    const error = await rejection(() => fetchDiscussion(ENTRY_ID));
    expect(error).toBeInstanceOf(ApiError);
    expect(isApiError(error) ? error.code : null).toBe("message_not_found");
    expect(isApiError(error) ? error.status : null).toBe(404);
  });

  it("an abort during the read rejects with the abort, not wrapped in an ApiError — DoD-5", async () => {
    const mock = stubFetch(abortableFetch());
    const controller = new AbortController();
    const pending = rejection(() => fetchDiscussion(ENTRY_ID, controller.signal));
    await vi.waitFor(() => expect(mock).toHaveBeenCalled());
    controller.abort();
    const caught = await pending;
    expect(isApiError(caught)).toBe(false);
    expect(caught).toBe(controller.signal.reason);
    expect((caught as { name?: unknown }).name).toBe("AbortError");
  });

  it("an already-aborted signal rejects with the abort, not wrapped in an ApiError — DoD-5", async () => {
    stubFetch(abortableFetch());
    const controller = new AbortController();
    controller.abort();
    const caught = await rejection(() => fetchDiscussion(ENTRY_ID, controller.signal));
    expect(isApiError(caught)).toBe(false);
    expect((caught as { name?: unknown }).name).toBe("AbortError");
  });
});

// ---------------------------------------------------------------------------
// Type-level pins (D15). These literals must compile under `npm run typecheck`; the `it`
// below runs trivially. A required tool field would break EIGHT_KEY_MESSAGE; a missing or
// mistyped one would break ELEVEN_KEY_MESSAGE.
const EIGHT_KEY_MESSAGE: Message = {
  id: "7250000000000000301",
  session_id: SESSION_ID,
  role: "assistant",
  kind: null,
  text: "A suggestion.",
  settled_at: null,
  created_at: STAMP,
  updated_at: STAMP,
};

const ELEVEN_KEY_MESSAGE: Message = {
  id: "7250000000000000302",
  session_id: SESSION_ID,
  role: "tool",
  kind: null,
  text: "Found 2 memos.",
  settled_at: null,
  created_at: STAMP,
  updated_at: STAMP,
  tool_name: "memo_search",
  tool_status: "ok",
  tool_args: { query: "lighthouse" },
};

const ELEVEN_KEY_NULL_TOOL_MESSAGE: Message = {
  ...EIGHT_KEY_MESSAGE,
  tool_name: null,
  tool_status: null,
  tool_args: null,
};

const TOOL_STATUSES: ToolStatus[] = ["ok", "failed"];

// @ts-expect-error — tool_status is only "ok", "failed" or null (D15).
const BAD_STATUS: Message = { ...EIGHT_KEY_MESSAGE, tool_status: "running" };

describe("Message — the tool fields are optional and nullable", () => {
  it("an eight-key literal and an eleven-key literal both type-check — DoD-6", () => {
    expect(Object.keys(EIGHT_KEY_MESSAGE)).toHaveLength(8);
    expect(Object.keys(ELEVEN_KEY_MESSAGE)).toHaveLength(11);
    expect(Object.keys(ELEVEN_KEY_NULL_TOOL_MESSAGE)).toHaveLength(11);
    expect(TOOL_STATUSES).toEqual(["ok", "failed"]);
    expect(BAD_STATUS.id).toBe(EIGHT_KEY_MESSAGE.id);
  });
});
