// Feature 013, step 001 — the stream API client (DoD-1..DoD-5).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// context.md "Wire contract" and D14 / D15, and 012's wire contract as cited there: seven
// calls, each addressing exactly one route by exact pathname and method; the two reads
// unwrap their envelope key; the two text-carrying POSTs and the PATCH send their text
// verbatim; settle and re-open send no body; ids are never coerced; failures are the shared
// client's ApiErrors rethrown unchanged.
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, isApiError } from "../../src/shared/apiError";
import {
  appendZoneMessage,
  editMessage,
  fetchEntries,
  fetchZone,
  filePartnerEntry,
  type Message,
  type ReopenResult,
  reopenLastEntry,
  type SettleResult,
  settleZone,
} from "../../src/app/streamApi";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// Every id is > Number.MAX_SAFE_INTEGER: a silent numeric coercion would change it.
const SESSION_ID = "7250000000000000001";
const ENTRY_PARTNER_ID = "7250000000000000101";
const ENTRY_TURN_ID = "7250000000000000102";
const ENTRY_DECISION_ID = "7250000000000000103";
const ZONE_USER_ID = "7250000000000000104";
const ZONE_ASSISTANT_ID = "7250000000000000105";
const NEW_ENTRY_ID = "7250000000000000106";
const BURIED_ID_A = "7250000000000000107";
const BURIED_ID_B = "7250000000000000108";

const STAMP = "2026-10-02T09:26:53.000000+00:00";
const LATER = "2026-10-02T10:01:12.000000+00:00";

function message(overrides: Partial<Message> & Pick<Message, "id">): Message {
  return {
    session_id: SESSION_ID,
    role: "user",
    kind: null,
    text: "text",
    settled_at: null,
    created_at: STAMP,
    updated_at: STAMP,
    ...overrides,
  };
}

const PARTNER_ENTRY = message({
  id: ENTRY_PARTNER_ID,
  role: "user",
  kind: "partner",
  text: "The partner opens the scene.",
  settled_at: STAMP,
});
const TURN_ENTRY = message({
  id: ENTRY_TURN_ID,
  role: "assistant",
  kind: "turn",
  text: "She walks.",
  settled_at: LATER,
});
const DECISION_ENTRY = message({
  id: ENTRY_DECISION_ID,
  role: "user",
  kind: "decision",
  text: "((keep it slow))",
  settled_at: LATER,
});
const ZONE_USER = message({ id: ZONE_USER_ID, role: "user", text: "A draft line." });
const ZONE_ASSISTANT = message({
  id: ZONE_ASSISTANT_ID,
  role: "assistant",
  text: "A suggestion.",
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

/** The raw body of the n-th request, or undefined when none was sent. */
function rawBody(mock: ReturnType<typeof stubFetch>, index = 0): unknown {
  const raw = mock.mock.calls[index]?.[1]?.body;
  return raw === null ? undefined : raw;
}

function envelope(code: string, message: string): unknown {
  return { error: { code, message, detail: {} } };
}

/** The rejection of a call that must not resolve. */
async function rejection(call: () => Promise<unknown>): Promise<unknown> {
  return call().then(
    () => {
      throw new Error("the call resolved, but the route answered an error");
    },
    (reason: unknown) => reason,
  );
}

// ---------------------------------------------------------------------------
describe("fetchEntries", () => {
  it("requests exactly GET /api/sessions/7250000000000000001/entries — DoD-1", async () => {
    const mock = serve({ entries: [] });
    await fetchEntries("7250000000000000001");
    expect(seen(mock)).toEqual([
      { method: "GET", path: "/api/sessions/7250000000000000001/entries", search: "" },
    ]);
  });

  it("resolves to the payload's entries array, unwrapped and in the order received — DoD-1", async () => {
    serve({ entries: [TURN_ENTRY, PARTNER_ENTRY, DECISION_ENTRY] });
    await expect(fetchEntries(SESSION_ID)).resolves.toEqual([
      TURN_ENTRY,
      PARTNER_ENTRY,
      DECISION_ENTRY,
    ]);
  });

  it("keeps every id and session_id the identical string the payload carried — DoD-1", async () => {
    serve({ entries: [PARTNER_ENTRY, TURN_ENTRY, DECISION_ENTRY] });
    const rows = await fetchEntries(SESSION_ID);
    expect(rows.map((row) => row.id)).toEqual([
      ENTRY_PARTNER_ID,
      ENTRY_TURN_ID,
      ENTRY_DECISION_ID,
    ]);
    for (const row of rows) {
      expect(typeof row.id).toBe("string");
      expect(typeof row.session_id).toBe("string");
      expect(row.session_id).toBe(SESSION_ID);
    }
  });

  it("keeps kind and settled_at as carried, including null — DoD-1", async () => {
    const unsettled = message({ id: ZONE_USER_ID, kind: null, settled_at: null });
    serve({ entries: [PARTNER_ENTRY, TURN_ENTRY, DECISION_ENTRY, unsettled] });
    const rows = await fetchEntries(SESSION_ID);
    expect(rows.map((row) => row.kind)).toEqual(["partner", "turn", "decision", null]);
    expect(rows.map((row) => row.settled_at)).toEqual([STAMP, LATER, LATER, null]);
  });

  it("resolves to an empty array for an empty record — DoD-1", async () => {
    serve({ entries: [] });
    await expect(fetchEntries(SESSION_ID)).resolves.toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("fetchZone", () => {
  it("requests exactly GET /api/sessions/<id>/zone — DoD-1", async () => {
    const mock = serve({ messages: [] });
    await fetchZone(SESSION_ID);
    expect(seen(mock)).toEqual([
      { method: "GET", path: `/api/sessions/${SESSION_ID}/zone`, search: "" },
    ]);
  });

  it("resolves to the payload's messages array, unwrapped and in the order received — DoD-1", async () => {
    serve({ messages: [ZONE_ASSISTANT, ZONE_USER] });
    await expect(fetchZone(SESSION_ID)).resolves.toEqual([ZONE_ASSISTANT, ZONE_USER]);
  });

  it("keeps ids identical strings and kind / settled_at null as carried — DoD-1", async () => {
    serve({ messages: [ZONE_USER, ZONE_ASSISTANT] });
    const rows = await fetchZone(SESSION_ID);
    expect(rows.map((row) => row.id)).toEqual([ZONE_USER_ID, ZONE_ASSISTANT_ID]);
    expect(rows.map((row) => row.session_id)).toEqual([SESSION_ID, SESSION_ID]);
    expect(rows.map((row) => row.kind)).toEqual([null, null]);
    expect(rows.map((row) => row.settled_at)).toEqual([null, null]);
  });

  it("resolves to an empty array for an empty zone — DoD-1", async () => {
    serve({ messages: [] });
    await expect(fetchZone(SESSION_ID)).resolves.toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("filePartnerEntry", () => {
  it("POSTs /api/sessions/<sid>/entries with the JSON body exactly {\"kind\":\"partner\",\"text\":\"  Hi ((there))  \"} — DoD-2", async () => {
    const filed = message({
      id: NEW_ENTRY_ID,
      kind: "partner",
      text: "  Hi ((there))  ",
      settled_at: STAMP,
    });
    const mock = serve(filed, 201);
    await filePartnerEntry(SESSION_ID, "  Hi ((there))  ");
    expect(seen(mock)).toEqual([
      { method: "POST", path: `/api/sessions/${SESSION_ID}/entries`, search: "" },
    ]);
    expect(rawBody(mock)).toBe('{"kind":"partner","text":"  Hi ((there))  "}');
  });

  it("resolves to the response's Message — DoD-2", async () => {
    const filed = message({
      id: NEW_ENTRY_ID,
      kind: "partner",
      text: "  Hi ((there))  ",
      settled_at: STAMP,
    });
    serve(filed, 201);
    await expect(filePartnerEntry(SESSION_ID, "  Hi ((there))  ")).resolves.toEqual(filed);
  });
});

// ---------------------------------------------------------------------------
describe("appendZoneMessage", () => {
  it("POSTs /api/sessions/<sid>/zone/messages with the JSON body exactly {\"text\":\" x \"} — DoD-2", async () => {
    const appended = message({ id: NEW_ENTRY_ID, text: " x " });
    const mock = serve(appended, 201);
    await appendZoneMessage(SESSION_ID, " x ");
    expect(seen(mock)).toEqual([
      { method: "POST", path: `/api/sessions/${SESSION_ID}/zone/messages`, search: "" },
    ]);
    expect(rawBody(mock)).toBe('{"text":" x "}');
  });

  it("resolves to the response's Message — DoD-2", async () => {
    const appended = message({ id: NEW_ENTRY_ID, text: " x " });
    serve(appended, 201);
    await expect(appendZoneMessage(SESSION_ID, " x ")).resolves.toEqual(appended);
  });
});

// ---------------------------------------------------------------------------
describe("settleZone", () => {
  const SETTLED: SettleResult = {
    entry_id: NEW_ENTRY_ID,
    kind: "turn",
    buried_ids: [BURIED_ID_B, BURIED_ID_A],
  };

  it("POSTs exactly /api/sessions/<sid>/settle — DoD-3", async () => {
    const mock = serve(SETTLED);
    await settleZone(SESSION_ID);
    expect(seen(mock)).toEqual([
      { method: "POST", path: `/api/sessions/${SESSION_ID}/settle`, search: "" },
    ]);
  });

  it("sends no JSON body — DoD-3", async () => {
    const mock = serve(SETTLED);
    await settleZone(SESSION_ID);
    expect(rawBody(mock)).toBeUndefined();
  });

  it("resolves to {entry_id, kind, buried_ids} as received, ids strings and order kept — DoD-3", async () => {
    serve(SETTLED);
    const result = await settleZone(SESSION_ID);
    expect(result).toEqual({
      entry_id: NEW_ENTRY_ID,
      kind: "turn",
      buried_ids: [BURIED_ID_B, BURIED_ID_A],
    });
    expect(typeof result.entry_id).toBe("string");
    for (const id of result.buried_ids) expect(typeof id).toBe("string");
  });

  it("resolves a decision settle with no buried ids as received — DoD-3", async () => {
    serve({ entry_id: NEW_ENTRY_ID, kind: "decision", buried_ids: [] });
    await expect(settleZone(SESSION_ID)).resolves.toEqual({
      entry_id: NEW_ENTRY_ID,
      kind: "decision",
      buried_ids: [],
    });
  });
});

// ---------------------------------------------------------------------------
describe("reopenLastEntry", () => {
  const REOPENED: ReopenResult = {
    reopened_id: ENTRY_TURN_ID,
    restored_ids: [BURIED_ID_A, BURIED_ID_B],
  };

  it("POSTs exactly /api/sessions/<sid>/reopen — DoD-3", async () => {
    const mock = serve(REOPENED);
    await reopenLastEntry(SESSION_ID);
    expect(seen(mock)).toEqual([
      { method: "POST", path: `/api/sessions/${SESSION_ID}/reopen`, search: "" },
    ]);
  });

  it("sends no JSON body — DoD-3", async () => {
    const mock = serve(REOPENED);
    await reopenLastEntry(SESSION_ID);
    expect(rawBody(mock)).toBeUndefined();
  });

  it("resolves to {reopened_id, restored_ids} as received, ids strings and order kept — DoD-3", async () => {
    serve(REOPENED);
    const result = await reopenLastEntry(SESSION_ID);
    expect(result).toEqual({
      reopened_id: ENTRY_TURN_ID,
      restored_ids: [BURIED_ID_A, BURIED_ID_B],
    });
    expect(typeof result.reopened_id).toBe("string");
    for (const id of result.restored_ids) expect(typeof id).toBe("string");
  });
});

// ---------------------------------------------------------------------------
describe("editMessage", () => {
  it("PATCHes exactly /api/messages/7250000000000000105 with the JSON body exactly {\"text\":\"new\"} — DoD-4", async () => {
    const edited = message({
      id: "7250000000000000105",
      role: "assistant",
      text: "new",
      updated_at: LATER,
    });
    const mock = serve(edited);
    await editMessage("7250000000000000105", "new");
    expect(seen(mock)).toEqual([
      { method: "PATCH", path: "/api/messages/7250000000000000105", search: "" },
    ]);
    expect(rawBody(mock)).toBe('{"text":"new"}');
  });

  it("resolves to the response's Message — DoD-4", async () => {
    const edited = message({
      id: "7250000000000000105",
      role: "assistant",
      text: "new",
      updated_at: LATER,
    });
    serve(edited);
    const result = await editMessage("7250000000000000105", "new");
    expect(result).toEqual(edited);
    expect(result.id).toBe("7250000000000000105");
  });
});

// ---------------------------------------------------------------------------
describe("failures are the shared client's ApiErrors, rethrown unchanged", () => {
  it("a 409 zone_empty envelope rejects settleZone with an ApiError whose code is zone_empty — DoD-5", async () => {
    serve(envelope("zone_empty", "The current zone is empty."), 409);
    const error = await rejection(() => settleZone(SESSION_ID));
    expect(error).toBeInstanceOf(ApiError);
    expect(isApiError(error) ? error.code : null).toBe("zone_empty");
    expect(isApiError(error) ? error.status : null).toBe(409);
  });

  it("a 409 nothing_to_reopen envelope rejects reopenLastEntry with an ApiError whose code is nothing_to_reopen — DoD-5", async () => {
    serve(envelope("nothing_to_reopen", "There is nothing to re-open."), 409);
    const error = await rejection(() => reopenLastEntry(SESSION_ID));
    expect(error).toBeInstanceOf(ApiError);
    expect(isApiError(error) ? error.code : null).toBe("nothing_to_reopen");
    expect(isApiError(error) ? error.status : null).toBe(409);
  });

  it("a 409 message_not_editable envelope rejects editMessage with an ApiError whose code is message_not_editable — DoD-5", async () => {
    serve(envelope("message_not_editable", "That message is settled."), 409);
    const error = await rejection(() => editMessage(ZONE_ASSISTANT_ID, "new"));
    expect(error).toBeInstanceOf(ApiError);
    expect(isApiError(error) ? error.code : null).toBe("message_not_editable");
    expect(isApiError(error) ? error.status : null).toBe(409);
  });
});
