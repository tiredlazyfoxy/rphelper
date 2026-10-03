// Feature 013, step 007 — the assembled stream (DoD-1..DoD-5). The session-screen clauses
// (DoD-6..DoD-8) live in SessionScreen.test.tsx, the route clause (DoD-9) in App.test.tsx and the
// entry's stub widening (DoD-10) in entries.test.tsx; DoD-11 is [manual/live] and has no test.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done plus
// context.md's D2, D4, D7, D8, D12, D13, D15 and the UI strings table:
//   - while either GET is pending: a Mantine `Loader` (`.mantine-Loader-root`, the repo's
//     convention);
//   - a failed load: "Could not load the stream" + a "Retry" button, never a notification;
//   - ready: "Settled record" list, then the one `separator` named "Current zone", then the
//     "Entry kind" radiogroup, then the "Zone messages" list (absent for an empty zone), then
//     the "Composer" textbox with "Send" and "Settle".
// Stubs and logs key on the exact method + pathname (context.md "Test conventions").
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SessionStream } from "../../src/app/SessionStream";
import type { Message, MessageKind, MessageRole } from "../../src/app/streamApi";
import { AppProviders } from "../../src/shared/AppProviders";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type User = ReturnType<typeof userEvent.setup>;

// ---------------------------------------------------------------- the spec's names
const RECORD_LIST = "Settled record";
const ZONE_LIST = "Zone messages";
const RULER = "Current zone";
const KIND_GROUP = "Entry kind";
const COMPOSER = "Composer";
const SEND = "Send";
const SETTLE = "Settle";
const REOPEN = "Re-open last entry";
const LOAD_FAILED_TEXT = "Could not load the stream";
const RETRY = "Retry";

const LOADER = ".mantine-Loader-root";
const NOTIFICATION = ".mantine-Notification-root";

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "7250000000000000077";
const BASE = `/api/sessions/${SESSION_ID}`;
const ENTRIES_PATH = `${BASE}/entries`;
const ZONE_PATH = `${BASE}/zone`;
const APPEND_PATH = `${BASE}/zone/messages`;
const SETTLE_PATH = `${BASE}/settle`;

const GET_ENTRIES = `GET ${ENTRIES_PATH}`;
const GET_ZONE = `GET ${ZONE_PATH}`;
const POST_ENTRIES = `POST ${ENTRIES_PATH}`;
const POST_APPEND = `POST ${APPEND_PATH}`;
const POST_SETTLE = `POST ${SETTLE_PATH}`;

const STAMP = "2026-05-10T09:00:00.000000+00:00";

function entry(id: string, kind: MessageKind, text: string): Message {
  return {
    id,
    session_id: SESSION_ID,
    role: "user",
    kind,
    text,
    settled_at: STAMP,
    created_at: STAMP,
    updated_at: STAMP,
  };
}

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

beforeEach(() => {
  notifyFailureSpy.mockClear();
});

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

function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: `refused: ${code}`, detail: {} } }, status);
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

type Seen = { line: string; body: string | null };
type Answer = Response | Promise<Response> | undefined;

/** Stubs fetch by exact method + pathname; logs "METHOD /path" with the raw body. */
function stubFetch(route: (method: string, pathname: string) => Answer): Seen[] {
  const log: Seen[] = [];
  const impl: FetchFn = async (input, init) => {
    const method = requestMethod(input, init);
    const pathname = requestUrl(input).pathname;
    log.push({ line: `${method} ${pathname}`, body: typeof init?.body === "string" ? init.body : null });
    const answer = route(method, pathname);
    if (answer !== undefined) return answer;
    return envelope("unexpected", 500);
  };
  vi.stubGlobal("fetch", vi.fn(impl));
  return log;
}

function lines(log: Seen[]): string[] {
  return log.map((seen) => seen.line);
}

function count(log: Seen[], line: string): number {
  return lines(log).filter((candidate) => candidate === line).length;
}

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

async function flush(rounds = 6): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => setImmediate(resolve));
    });
  }
}

function newUser(): User {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

function renderStream(): void {
  render(
    <AppProviders>
      <SessionStream sessionId={SESSION_ID} />
    </AppProviders>,
  );
}

// ---------------------------------------------------------------- queries
function loaders(): Element[] {
  return Array.from(document.querySelectorAll(LOADER));
}

function notificationsShown(): Element[] {
  return Array.from(document.querySelectorAll(NOTIFICATION));
}

function recordList(): HTMLElement {
  return screen.getByRole("list", { name: RECORD_LIST });
}

function ruler(): HTMLElement {
  return screen.getByRole("separator", { name: RULER });
}

function composer(): HTMLElement {
  return screen.getByRole("textbox", { name: COMPOSER });
}

/** The record's listitem that holds the given text. */
function recordItemWith(text: string): HTMLElement {
  const item = within(recordList())
    .getAllByRole("listitem")
    .find((candidate) => (candidate.textContent ?? "").includes(text));
  if (item === undefined) throw new Error(`no record item holds ${JSON.stringify(text)}`);
  return item;
}

/** True when `first` precedes `second` in document order. */
function precedes(first: Element, second: Element): boolean {
  return (first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

// ---------------------------------------------------------------------------
describe("loading, then the assembled stream (US-125.AC-1, D12)", () => {
  it("shows a loader while both GETs are pending, then record, one ruler, switch and composer in order — DoD-1", async () => {
    const entriesGate = deferred<Response>();
    const zoneGate = deferred<Response>();
    stubFetch((method, pathname) => {
      if (method === "GET" && pathname === ENTRIES_PATH) return entriesGate.promise;
      if (method === "GET" && pathname === ZONE_PATH) return zoneGate.promise;
      return undefined;
    });
    renderStream();
    await flush(2);

    expect(loaders().length).toBeGreaterThan(0);
    expect(screen.queryByRole("textbox", { name: COMPOSER })).toBeNull();

    entriesGate.resolve(
      jsonResponse({ entries: [entry("7250000000000000101", "partner", "The gate creaks.")] }, 200),
    );
    await flush(2);
    // One answer is not enough: the zone is still pending.
    expect(screen.queryByRole("textbox", { name: COMPOSER })).toBeNull();

    zoneGate.resolve(jsonResponse({ messages: [] }, 200));
    await flush();

    expect(loaders()).toEqual([]);

    const record = recordList();
    expect(screen.getAllByRole("separator")).toHaveLength(1);
    const theRuler = ruler();
    expect(screen.getByText(RULER)).toBeInTheDocument();
    const kindSwitch = screen.getByRole("radiogroup", { name: KIND_GROUP });
    const textbox = composer();
    const send = screen.getByRole("button", { name: SEND });
    const settle = screen.getByRole("button", { name: SETTLE });

    expect(precedes(record, theRuler)).toBe(true);
    expect(precedes(theRuler, kindSwitch)).toBe(true);
    expect(precedes(kindSwitch, textbox)).toBe(true);
    expect(precedes(theRuler, send)).toBe(true);
    expect(precedes(theRuler, settle)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
describe("record above the ruler, zone below it (US-125.AC-1)", () => {
  it("renders the two entries in Settled record and the two zone rows in Zone messages, in that order around the ruler — DoD-2", async () => {
    const entries = [
      entry("7250000000000000111", "partner", "The partner knocks twice."),
      entry("7250000000000000112", "turn", "I open the door slowly."),
    ];
    const zone = [
      zoneRow("7250000000000000121", "user", "What does she see first?"),
      zoneRow("7250000000000000122", "assistant", "A lantern swinging in the wind."),
    ];
    stubFetch((method, pathname) => {
      if (method === "GET" && pathname === ENTRIES_PATH) return jsonResponse({ entries }, 200);
      if (method === "GET" && pathname === ZONE_PATH) return jsonResponse({ messages: zone }, 200);
      return undefined;
    });
    renderStream();
    await flush();

    const record = recordList();
    const recordItems = within(record).getAllByRole("listitem");
    expect(recordItems).toHaveLength(2);
    expect(recordItems[0].textContent).toContain("The partner knocks twice.");
    expect(recordItems[1].textContent).toContain("I open the door slowly.");

    const zoneLists = screen.getAllByRole("list", { name: ZONE_LIST });
    expect(zoneLists).toHaveLength(1);
    const zoneList = zoneLists[0];
    const zoneItems = within(zoneList).getAllByRole("listitem");
    expect(zoneItems).toHaveLength(2);
    expect(zoneItems[0].textContent).toContain("What does she see first?");
    expect(zoneItems[1].textContent).toContain("A lantern swinging in the wind.");

    // Neither list holds the other's rows.
    expect(record.textContent).not.toContain("What does she see first?");
    expect(zoneList.textContent).not.toContain("I open the door slowly.");

    const theRuler = ruler();
    expect(screen.getAllByRole("separator")).toHaveLength(1);
    expect(precedes(record, theRuler)).toBe(true);
    expect(precedes(theRuler, zoneList)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
describe("a failed load renders in place and retries (D15)", () => {
  type FailureCase = [label: string, failing: string];
  const FAILURES: FailureCase[] = [
    ["the entries GET", ENTRIES_PATH],
    ["the zone GET", ZONE_PATH],
  ];

  it.each(FAILURES)(
    "a 500 on %s renders Could not load the stream and Retry, with no notifyFailure call — DoD-3",
    async (_label, failing) => {
      stubFetch((method, pathname) => {
        if (method !== "GET") return undefined;
        if (pathname === failing) return envelope("internal_error", 500);
        if (pathname === ENTRIES_PATH) return jsonResponse({ entries: [] }, 200);
        if (pathname === ZONE_PATH) return jsonResponse({ messages: [] }, 200);
        return undefined;
      });
      renderStream();
      await flush();

      expect(screen.getByText(LOAD_FAILED_TEXT)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: RETRY })).toBeInTheDocument();
      expect(notifyFailureSpy).not.toHaveBeenCalled();
      expect(notificationsShown()).toEqual([]);
      expect(screen.queryByRole("textbox", { name: COMPOSER })).toBeNull();
      expect(screen.queryByRole("separator", { name: RULER })).toBeNull();
    },
  );

  it("pressing Retry requests both lists again and renders the stream on success — DoD-3", async () => {
    const user = newUser();
    let failing = true;
    const log = stubFetch((method, pathname) => {
      if (method !== "GET") return undefined;
      if (pathname === ENTRIES_PATH) {
        if (failing) return envelope("internal_error", 500);
        return jsonResponse(
          { entries: [entry("7250000000000000131", "turn", "Back on the road.")] },
          200,
        );
      }
      if (pathname === ZONE_PATH) return jsonResponse({ messages: [] }, 200);
      return undefined;
    });
    renderStream();
    await flush();
    expect(screen.getByText(LOAD_FAILED_TEXT)).toBeInTheDocument();

    const entriesBefore = count(log, GET_ENTRIES);
    const zoneBefore = count(log, GET_ZONE);
    failing = false;

    await user.click(screen.getByRole("button", { name: RETRY }));
    await flush();

    expect(count(log, GET_ENTRIES)).toBeGreaterThan(entriesBefore);
    expect(count(log, GET_ZONE)).toBeGreaterThan(zoneBefore);
    expect(screen.queryByText(LOAD_FAILED_TEXT)).toBeNull();
    expect(screen.queryByRole("button", { name: RETRY })).toBeNull();
    expect(recordItemWith("Back on the road.")).toBeInTheDocument();
    expect(ruler()).toBeInTheDocument();
    expect(composer()).toBeInTheDocument();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(notificationsShown()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("end to end on stubs: write directly and settle (US-031.AC-1, US-127, US-120.AC-1, D2, D4)", () => {
  it("typing First line. and pressing Settle appends, settles, re-reads, and the entry lands above the ruler — DoD-4", async () => {
    const user = newUser();
    const SETTLED_TEXT = "First line.";
    const settledEntry = entry("7250000000000000141", "turn", SETTLED_TEXT);
    let settled = false;
    const log = stubFetch((method, pathname) => {
      if (method === "GET" && pathname === ENTRIES_PATH)
        return jsonResponse({ entries: settled ? [settledEntry] : [] }, 200);
      if (method === "GET" && pathname === ZONE_PATH) return jsonResponse({ messages: [] }, 200);
      if (method === "POST" && pathname === APPEND_PATH)
        return jsonResponse(zoneRow("7250000000000000142", "user", SETTLED_TEXT), 201);
      if (method === "POST" && pathname === SETTLE_PATH) {
        settled = true;
        return jsonResponse({ entry_id: settledEntry.id, kind: "turn", buried_ids: ["7250000000000000142"] }, 200);
      }
      return undefined;
    });
    renderStream();
    await flush();
    // An empty record defaults the switch to *my turn* (D8).
    expect(screen.getByRole("radio", { name: "My turn" })).toBeChecked();

    await user.type(composer(), SETTLED_TEXT);
    const loadedUpTo = log.length;
    await user.click(screen.getByRole("button", { name: SETTLE }));
    await flush();

    const mutation = log.slice(loadedUpTo);
    expect(lines(mutation).slice(0, 2)).toEqual([POST_APPEND, POST_SETTLE]);
    expect(JSON.parse(mutation[0].body ?? "null")).toEqual({ text: SETTLED_TEXT });
    expect([...lines(mutation).slice(2)].sort()).toEqual([GET_ENTRIES, GET_ZONE].sort());

    const item = recordItemWith(SETTLED_TEXT);
    expect(precedes(recordList(), ruler())).toBe(true);
    expect(precedes(item, ruler())).toBe(true);
    expect(screen.queryByRole("list", { name: ZONE_LIST })).toBeNull();
    expect(composer()).toHaveValue("");
    expect(within(item).getByRole("button", { name: REOPEN })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Partner" })).toBeChecked();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("end to end on stubs: a pasted partner block files itself (US-030.AC-1, US-121.AC-1, US-120.AC-2)", () => {
  it("on Partner, a paste POSTs …/entries, re-reads, shows the entry in a blockquote and flips the switch to My turn — DoD-5", async () => {
    const PASTED = "She smiles and steps aside.";
    const priorTurn = entry("7250000000000000151", "turn", "I wait by the gate.");
    const filed = entry("7250000000000000152", "partner", PASTED);
    let filedYet = false;
    const log = stubFetch((method, pathname) => {
      if (method === "GET" && pathname === ENTRIES_PATH)
        return jsonResponse({ entries: filedYet ? [priorTurn, filed] : [priorTurn] }, 200);
      if (method === "GET" && pathname === ZONE_PATH) return jsonResponse({ messages: [] }, 200);
      if (method === "POST" && pathname === ENTRIES_PATH) {
        filedYet = true;
        return jsonResponse(filed, 201);
      }
      return undefined;
    });
    renderStream();
    await flush();
    // The last entry is a turn, so the switch defaults to *partner* (US-120).
    expect(screen.getByRole("radio", { name: "Partner" })).toBeChecked();

    const loadedUpTo = log.length;
    fireEvent.paste(composer(), { clipboardData: { getData: () => PASTED } });
    await flush();

    const mutation = log.slice(loadedUpTo);
    expect(mutation[0].line).toBe(POST_ENTRIES);
    expect(JSON.parse(mutation[0].body ?? "null")).toEqual({ kind: "partner", text: PASTED });
    expect(lines(mutation).slice(1)).toContain(GET_ENTRIES);
    expect(lines(mutation)).not.toContain(POST_APPEND);
    expect(lines(mutation)).not.toContain(POST_SETTLE);

    const item = recordItemWith(PASTED);
    const quote = item.querySelector("blockquote");
    expect(quote).not.toBeNull();
    expect(quote?.textContent ?? "").toContain(PASTED);
    expect(precedes(item, ruler())).toBe(true);
    expect(screen.getByRole("radio", { name: "My turn" })).toBeChecked();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});
