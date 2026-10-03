// Feature 013, step 004 — the settled record (DoD-7..DoD-12).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done plus
// context.md's D4, D5, D11 and the UI strings table:
//   - a list labelled "Settled record", one listitem per entry in the given order, headed
//     "Partner" / "My turn" / "Decision";
//   - partner bodies sit in a blockquote and are never painted; decision bodies are the
//     out-of-character card (data-paren="ooc");
//   - no copy control on a decision or partner item (D11; amended by 014 step 005 DoD-3 —
//     014 D7 adds copy on turns);
//   - "Re-open last entry" sits in the last item only, present while the zone is empty and
//     the last entry is not a partner block, absent (not disabled) otherwise; pressing it
//     POSTs /api/sessions/<id>/reopen;
//   - with no entries, "No entries yet." and no listitem.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { runInAction } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StreamRecord } from "../../src/app/StreamRecord";
import type { Message, MessageKind, MessageRole } from "../../src/app/streamApi";
import { StreamState } from "../../src/app/streamState";
import { AppProviders } from "../../src/shared/AppProviders";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "7250000000000000042";
const ENTRIES_PATH = `/api/sessions/${SESSION_ID}/entries`;
const ZONE_PATH = `/api/sessions/${SESSION_ID}/zone`;
const REOPEN_PATH = `/api/sessions/${SESSION_ID}/reopen`;

const RECORD_NAME = "Settled record";
const REOPEN_NAME = "Re-open last entry";
const EMPTY_TEXT = "No entries yet.";

const STAMP = "2026-05-10T09:00:00.000000+00:00";

let nextId = 100;
function freshId(): string {
  nextId += 1;
  return `7250000000000000${String(nextId).padStart(3, "0")}`;
}

/** A settled entry with all eight keys. */
function entry(kind: MessageKind, text: string, id = freshId()): Message {
  return {
    id,
    session_id: SESSION_ID,
    role: kind === "partner" ? "user" : "assistant",
    kind,
    text,
    settled_at: STAMP,
    created_at: STAMP,
    updated_at: STAMP,
  };
}

/** A zone row with all eight keys: `kind` and `settled_at` null. */
function zoneRow(role: MessageRole, text: string, id = freshId()): Message {
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

function seeded(entries: Message[], zone: Message[] = []): StreamState {
  const state = new StreamState(SESSION_ID);
  runInAction(() => {
    state.entries = entries;
    state.zone = zone;
    state.status = "ready";
  });
  return state;
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

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

/**
 * Stubs the stream routes by exact method + pathname and logs every request as
 * "METHOD /path". Re-open answers ids only; the re-reads answer the given lists.
 */
function stubStream(entries: Message[], zone: Message[]): string[] {
  const log: string[] = [];
  const impl: FetchFn = async (input, init) => {
    const method = requestMethod(input, init);
    const pathname = requestUrl(input).pathname;
    log.push(`${method} ${pathname}`);
    if (method === "POST" && pathname === REOPEN_PATH) {
      return jsonResponse({ reopened_id: entries[entries.length - 1]?.id ?? "", restored_ids: [] }, 200);
    }
    if (method === "GET" && pathname === ENTRIES_PATH) return jsonResponse({ entries }, 200);
    if (method === "GET" && pathname === ZONE_PATH) return jsonResponse({ messages: zone }, 200);
    return jsonResponse({ error: { code: "unexpected", message: "unexpected request", detail: {} } }, 500);
  };
  vi.stubGlobal("fetch", vi.fn(impl));
  return log;
}

function renderRecord(state: StreamState, signal?: AbortSignal): void {
  render(
    <AppProviders>
      <StreamRecord state={state} signal={signal} />
    </AppProviders>,
  );
}

function recordList(): HTMLElement {
  return screen.getByRole("list", { name: RECORD_NAME });
}

function recordItems(): HTMLElement[] {
  return within(recordList()).getAllByRole("listitem");
}

function newUser(): ReturnType<typeof userEvent.setup> {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

// ---------------------------------------------------------------- tests
describe("StreamRecord — entries by kind", () => {
  it("renders the Settled record list with partner, my turn, decision items in order — DoD-7", () => {
    renderRecord(seeded([entry("partner", "P1"), entry("turn", "T1"), entry("decision", "((D1))")]));

    const items = recordItems();
    expect(items).toHaveLength(3);

    expect(within(items[0] as HTMLElement).getByText("Partner")).toBeInTheDocument();
    expect(within(items[1] as HTMLElement).getByText("My turn")).toBeInTheDocument();
    expect(within(items[2] as HTMLElement).getByText("Decision")).toBeInTheDocument();

    expect(items[0]?.textContent).toContain("P1");
    expect(items[1]?.textContent).toContain("T1");
    expect(items[2]?.textContent).toContain("((D1))");
  });

  it("puts the partner body inside a blockquote — DoD-7", () => {
    renderRecord(seeded([entry("partner", "P1"), entry("turn", "T1"), entry("decision", "((D1))")]));

    const partnerItem = recordItems()[0] as HTMLElement;
    const body = within(partnerItem).getByText("P1");
    expect(body.closest("blockquote")).not.toBeNull();
    expect(partnerItem.querySelector("blockquote")).not.toBeNull();
  });

  it("renders the decision item's body as the out-of-character card — DoD-7", () => {
    renderRecord(seeded([entry("partner", "P1"), entry("turn", "T1"), entry("decision", "((D1))")]));

    const items = recordItems();
    const decisionItem = items[2] as HTMLElement;
    const card = decisionItem.querySelector('[data-paren="ooc"]');
    expect(card).not.toBeNull();
    expect(card?.textContent).toContain("((D1))");

    expect((items[0] as HTMLElement).querySelector('[data-paren="ooc"]')).toBeNull();
    expect((items[1] as HTMLElement).querySelector('[data-paren="ooc"]')).toBeNull();
  });
});

describe("StreamRecord — partner text is never painted", () => {
  it("a partner entry whose text is wholly parenthesised renders no data-paren element — DoD-8", () => {
    renderRecord(seeded([entry("partner", "((wholly parenthesised))")]));

    const list = recordList();
    expect(list.querySelector("[data-paren]")).toBeNull();
    expect(list.textContent).toContain("((wholly parenthesised))");
  });
});

// Amended by feature 014, step 005 DoD-3: copy now exists on turns (014 D7), so the "no Copy
// anywhere" assertion is removed and the check is scoped to the decision and partner items.
describe("StreamRecord — no copy control on decision or partner (D11, 014 D7)", () => {
  it("neither the decision item nor the partner item offers a control named Copy — DoD-9 — DoD-3", () => {
    // Zone empty and last entry a decision, so the record's own controls are rendered too.
    stubStream([], []);
    renderRecord(seeded([entry("partner", "P1"), entry("turn", "T1"), entry("decision", "((D1))")]));

    const items = recordItems();
    const partnerItem = items[0] as HTMLElement;
    const decisionItem = items[2] as HTMLElement;
    for (const scoped of [partnerItem, decisionItem]) {
      expect(within(scoped).queryAllByRole("button", { name: /copy/i })).toEqual([]);
      expect(within(scoped).queryAllByRole("link", { name: /copy/i })).toEqual([]);
    }
  });

  it("no copy control in the decision or partner item while the zone holds a row either — DoD-9 — DoD-3", () => {
    renderRecord(
      seeded(
        [entry("partner", "P1"), entry("turn", "T1"), entry("decision", "((D1))")],
        [zoneRow("user", "Z1")],
      ),
    );

    const items = recordItems();
    for (const scoped of [items[0] as HTMLElement, items[2] as HTMLElement]) {
      expect(within(scoped).queryAllByRole("button", { name: /copy/i })).toEqual([]);
    }
  });
});

describe("StreamRecord — re-open control (D4)", () => {
  it.each<[string, MessageKind]>([
    ["turn", "turn"],
    ["decision", "decision"],
  ])(
    "with an empty zone and the last entry a %s, Re-open sits in the last item only — DoD-10",
    (_label, lastKind) => {
      const entries = [entry("partner", "P1"), entry(lastKind, lastKind === "decision" ? "((L1))" : "L1")];
      renderRecord(seeded(entries, []));

      expect(screen.getAllByRole("button", { name: REOPEN_NAME })).toHaveLength(1);
      const items = recordItems();
      expect(items).toHaveLength(2);
      const last = items[items.length - 1] as HTMLElement;
      expect(within(last).getByRole("button", { name: REOPEN_NAME })).toBeInTheDocument();
      expect(within(items[0] as HTMLElement).queryByRole("button", { name: REOPEN_NAME })).toBeNull();
    },
  );

  it.each<[string, MessageKind]>([
    ["turn", "turn"],
    ["decision", "decision"],
  ])("pressing Re-open with the last entry a %s POSTs /api/sessions/<id>/reopen — DoD-10", async (_label, lastKind) => {
    const entries = [entry("partner", "P1"), entry(lastKind, lastKind === "decision" ? "((L1))" : "L1")];
    const log = stubStream(entries, []);
    const user = newUser();
    renderRecord(seeded(entries, []));

    await user.click(screen.getByRole("button", { name: REOPEN_NAME }));

    await waitFor(() => {
      expect(log).toContain(`POST ${REOPEN_PATH}`);
    });
    expect(log.filter((line) => line === `POST ${REOPEN_PATH}`)).toHaveLength(1);
    // Let the follow-up re-reads settle before teardown.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  });

  it("with the last entry a partner block, Re-open is absent — DoD-10", () => {
    renderRecord(seeded([entry("turn", "T1"), entry("partner", "P1")], []));

    expect(recordItems()).toHaveLength(2);
    expect(screen.queryByRole("button", { name: REOPEN_NAME })).toBeNull();
  });

  it.each<[string, MessageKind]>([
    ["turn", "turn"],
    ["decision", "decision"],
  ])("with one zone row and the last entry a %s, Re-open is absent, not disabled — DoD-11", (_label, lastKind) => {
    renderRecord(
      seeded(
        [entry("partner", "P1"), entry(lastKind, lastKind === "decision" ? "((L1))" : "L1")],
        [zoneRow("user", "Z1")],
      ),
    );

    expect(recordItems()).toHaveLength(2);
    // queryByRole also finds disabled buttons, so null means the control is not rendered.
    expect(screen.queryByRole("button", { name: REOPEN_NAME })).toBeNull();
    expect(screen.queryByLabelText(REOPEN_NAME)).toBeNull();
  });
});

describe("StreamRecord — empty record", () => {
  it('with no entries shows "No entries yet." and renders no list item — DoD-12', () => {
    renderRecord(seeded([], []));

    expect(screen.getByText(EMPTY_TEXT)).toBeInTheDocument();
    expect(screen.queryAllByRole("listitem")).toEqual([]);
    expect(screen.queryByRole("button", { name: REOPEN_NAME })).toBeNull();
  });
});
