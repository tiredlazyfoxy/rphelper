// Feature 024, step 007 — the coverage banner above the stream record (DoD-6, DoD-7).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done plus
// 007.context.md (which pins the sentence verbatim) and context.md's D11 / U5 (the flag starts
// false on mount, because no staleness is persisted):
//   - after a settle whose stubbed response carries `search_coverage_incomplete: true`, the ready
//     view shows one `role="alert"` whose text is exactly the pinned sentence, placed before the
//     first record entry in document order, and that entry's "Edit entry" control is still
//     present and enabled — the banner disables nothing (DoD-6);
//   - the same settle answered with `false` renders no such alert (DoD-6);
//   - a fresh mount whose stream load succeeds, with no write, renders no alert (DoD-7, U5).
//
// There is no seam to pre-set the flag (`## Skeleton`, step 007), so DoD-6 drives a stubbed settle
// through the UI. Stubs key on the exact method + pathname (context.md "Test conventions").
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SessionStream } from "../../src/app/SessionStream";
import type { Message, MessageKind, MessageRole } from "../../src/app/streamApi";
import { AppProviders } from "../../src/shared/AppProviders";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type User = ReturnType<typeof userEvent.setup>;

// ---------------------------------------------------------------- the spec's strings
/** 007.context.md, "The banner sentence (exact)". */
const COVERAGE_SENTENCE =
  "Search coverage is incomplete. Your latest change was saved, but it could not be indexed for search.";

const RECORD_LIST = "Settled record";
const COMPOSER = "Composer";
const SETTLE = "Settle";
const EDIT_ENTRY = "Edit entry";

// ---------------------------------------------------------------- the pinned paths
const SESSION_ID = "7250000000000000411";
const ENTRIES_PATH = `/api/sessions/${SESSION_ID}/entries`;
const ZONE_PATH = `/api/sessions/${SESSION_ID}/zone`;
const APPEND_PATH = `/api/sessions/${SESSION_ID}/zone/messages`;
const SETTLE_PATH = `/api/sessions/${SESSION_ID}/settle`;

const STAMP = "2026-05-10T09:00:00.000000+00:00";
const SETTLED_TEXT = "The lantern swings once.";

let nextId = 700;
function freshId(): string {
  nextId += 1;
  return `7250000000000000${String(nextId).padStart(3, "0")}`;
}

/** A settled record row with every key the `Message` type has today. */
function settledRow(kind: MessageKind, text: string, id = freshId()): Message {
  return {
    id,
    session_id: SESSION_ID,
    role: kind === "partner" ? "user" : "assistant",
    kind,
    text,
    settled_at: STAMP,
    created_at: STAMP,
    updated_at: STAMP,
    tool_name: null,
    tool_status: null,
    tool_args: null,
  };
}

/** A zone row: `kind` and `settled_at` null. Every other key present. */
function zoneRowOf(role: MessageRole, text: string, id = freshId()): Message {
  return {
    id,
    session_id: SESSION_ID,
    role,
    kind: null,
    text,
    settled_at: null,
    created_at: STAMP,
    updated_at: STAMP,
    tool_name: null,
    tool_status: null,
    tool_args: null,
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

type Answer = Response | Promise<Response> | undefined;

/** Stubs fetch by exact method + pathname; logs "METHOD /path". */
function stubFetch(route: (method: string, pathname: string) => Answer): string[] {
  const log: string[] = [];
  const impl: FetchFn = async (input, init) => {
    const method = requestMethod(input, init);
    const pathname = requestUrl(input).pathname;
    log.push(`${method} ${pathname}`);
    const answer = route(method, pathname);
    if (answer !== undefined) return answer;
    return envelope("unexpected", 500);
  };
  vi.stubGlobal("fetch", vi.fn(impl));
  return log;
}

async function flush(rounds = 6): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => setImmediate(resolve));
    });
  }
}

function renderStream(): void {
  render(
    <AppProviders>
      <SessionStream sessionId={SESSION_ID} />
    </AppProviders>,
  );
}

function newUser(): User {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

// ---------------------------------------------------------------- queries
function alerts(): HTMLElement[] {
  return screen.queryAllByRole("alert");
}

function recordList(): HTMLElement {
  return screen.getByRole("list", { name: RECORD_LIST });
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

/**
 * Stubs a stream whose load succeeds and whose settle answers with the given coverage flag,
 * landing one settled entry in the record.
 */
function serveSettle(coverage: boolean | undefined): { settledEntry: Message; log: string[] } {
  const settledEntry = settledRow("turn", SETTLED_TEXT);
  let settled = false;
  const log = stubFetch((method, pathname) => {
    if (method === "GET" && pathname === ENTRIES_PATH)
      return jsonResponse({ entries: settled ? [settledEntry] : [] }, 200);
    if (method === "GET" && pathname === ZONE_PATH) return jsonResponse({ messages: [] }, 200);
    if (method === "POST" && pathname === APPEND_PATH)
      return jsonResponse(zoneRowOf("user", SETTLED_TEXT), 201);
    if (method === "POST" && pathname === SETTLE_PATH) {
      settled = true;
      const body: Record<string, unknown> = {
        entry_id: settledEntry.id,
        kind: "turn",
        buried_ids: [],
      };
      if (coverage !== undefined) body.search_coverage_incomplete = coverage;
      return jsonResponse(body, 200);
    }
    return undefined;
  });
  return { settledEntry, log };
}

/** Types the settle text into the composer and presses Settle. */
async function settleThroughTheUi(user: User): Promise<void> {
  await user.type(screen.getByRole("textbox", { name: COMPOSER }), SETTLED_TEXT);
  await user.click(screen.getByRole("button", { name: SETTLE }));
  await flush();
}

// ===========================================================================
// DoD-6
// ===========================================================================
describe("the coverage banner in the ready view (US-112.AC-2, workspace-shell.md banner)", () => {
  it("after a settle answered with search_coverage_incomplete true, one alert holds exactly the pinned sentence, precedes the first record entry, and leaves that entry's edit control enabled — DoD-6", async () => {
    const user = newUser();
    serveSettle(true);
    renderStream();
    await flush();
    expect(alerts()).toEqual([]);

    await settleThroughTheUi(user);

    const shown = alerts();
    expect(shown).toHaveLength(1);
    const banner = shown[0] as HTMLElement;
    expect(banner.textContent).toBe(COVERAGE_SENTENCE);

    const item = recordItemWith(SETTLED_TEXT);
    expect(precedes(banner, item)).toBe(true);
    expect(precedes(banner, recordList())).toBe(true);

    const edit = within(item).getByRole("button", { name: EDIT_ENTRY });
    expect(edit).toBeInTheDocument();
    expect(edit).toBeEnabled();
    expect(screen.getByRole("textbox", { name: COMPOSER })).toBeEnabled();
  });

  it("after the same settle answered with search_coverage_incomplete false, no alert and no banner sentence are rendered — DoD-6", async () => {
    const user = newUser();
    serveSettle(false);
    renderStream();
    await flush();

    await settleThroughTheUi(user);

    // The settle did land, so the absent banner is the flag's doing and not a missing write.
    expect(recordItemWith(SETTLED_TEXT)).toBeInTheDocument();
    expect(alerts()).toEqual([]);
    expect(screen.queryByText(COVERAGE_SENTENCE)).toBeNull();
  });
});

// ===========================================================================
// DoD-7
// ===========================================================================
describe("a fresh mount carries no banner (D11, U5)", () => {
  it("with a successful initial stream load and no write, no alert and no banner sentence are rendered — DoD-7", async () => {
    const held = settledRow("partner", "The partner knocks twice.");
    const log = stubFetch((method, pathname) => {
      if (method === "GET" && pathname === ENTRIES_PATH)
        return jsonResponse({ entries: [held] }, 200);
      if (method === "GET" && pathname === ZONE_PATH) return jsonResponse({ messages: [] }, 200);
      return undefined;
    });
    renderStream();
    await flush();

    // The load succeeded: the held entry is in the record and the composer is there.
    expect(recordItemWith("The partner knocks twice.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: COMPOSER })).toBeInTheDocument();
    expect(alerts()).toEqual([]);
    expect(screen.queryByText(COVERAGE_SENTENCE)).toBeNull();
    expect(log.every((line) => line.startsWith("GET "))).toBe(true);
  });
});
