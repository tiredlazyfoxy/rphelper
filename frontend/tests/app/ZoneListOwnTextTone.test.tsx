// Fast feature 016 — own-text-muted: the roleplayer's own (user-role) message bodies render
// inside a muted-tone wrapper, in the zone and in the read-only Discussion group (DoD-1..DoD-5)
// (docs/plans/fast/016.own-text-muted/plan.md).
//
// Expected values come from the plan's Interface intent and Definition of done and the frozen
// test hook in status.md `## Skeleton`:
//   - a user row's body sits inside exactly one element carrying data-tone="muted", which holds
//     the row's rendered text; assistant and tool rows carry no data-tone="muted" element;
//   - DiscussionGroup reuses the same row, so its "You" item is muted and its "Assistant" is not;
//   - fragment chips (data-paren="fragment") and the OOC card (data-paren="ooc") survive inside
//     the wrapper;
//   - the edit textarea ("Edit message text") is never inside a data-tone="muted" element, and
//     the muted body returns when the editor closes.
// Tests bind to data-* markers and accessible names, never to computed colours.
// DoD-6 (the existing suites, typecheck and build stay green) is covered by running those
// suites unchanged; this file adds no test for it. DoD-7 is manual/live.
// Every await is bounded.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { runInAction } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DiscussionGroup } from "../../src/app/DiscussionGroup";
import { ZoneList, ZoneMessage } from "../../src/app/ZoneList";
import type { Message, MessageRole } from "../../src/app/streamApi";
import { StreamState } from "../../src/app/streamState";
import { AppProviders } from "../../src/shared/AppProviders";

// Failures would surface as notifications; the spy keeps them out of the DOM and observable.
const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- strings / hooks
const MUTED = '[data-tone="muted"]';
const LIST_NAME = "Zone messages";
const DISCUSSION_LIST = "Discussion messages";
const SHOW_DISCUSSION = "Show discussion";
const EDIT_NAME = "Edit message";
const EDITOR_NAME = "Edit message text";

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "7250000000000000042";
const USER_ID = "7250000000000000101";
const ASSISTANT_ID = "7250000000000000102";
const TOOL_ID = "7250000000000000103";
const ENTRY_ID = "7250000000000000202";
const DISCUSSION_LINE = `GET /api/messages/${ENTRY_ID}/discussion`;
const STAMP = "2026-11-05T09:00:00.000000+00:00";

/** A zone row with every Message key; tool fields null. */
function row(id: string, role: MessageRole, text: string): Message {
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

/** A completed memo_search tool row, as named in DoD-1. */
function toolRow(id: string, text: string): Message {
  return { ...row(id, "tool", text), tool_name: "memo_search", tool_status: "ok", tool_args: { query: "lighthouse" } };
}

/** DoD-1's zone: user, assistant, tool. */
function dodOneZone(): Message[] {
  return [row(USER_ID, "user", "Hi there"), row(ASSISTANT_ID, "assistant", "Hello back"), toolRow(TOOL_ID, "Found 2 memos.")];
}

/** A ready StreamState holding `zone`; seeded directly so no load request is needed. */
function seeded(zone: Message[]): StreamState {
  const state = new StreamState(SESSION_ID);
  runInAction(() => {
    state.zone = zone;
    state.status = "ready";
  });
  return state;
}

beforeEach(() => {
  notifyFailureSpy.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- harness
function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

/**
 * Stubs fetch: the discussion GET for ENTRY_ID answers `messages`; anything else is a 500 so an
 * unexpected request cannot pass silently. Returns the "METHOD /path" log.
 */
function stubFetch(messages: Message[] = []): string[] {
  const log: string[] = [];
  const impl: FetchFn = async (input, init) => {
    const line = `${requestMethod(input, init)} ${requestUrl(input).pathname}`;
    log.push(line);
    if (line === DISCUSSION_LINE) return jsonResponse({ messages }, 200);
    return jsonResponse({ error: { code: "unexpected", message: "unexpected", detail: {} } }, 500);
  };
  vi.stubGlobal("fetch", vi.fn(impl));
  return log;
}

function newUser(): ReturnType<typeof userEvent.setup> {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

async function flush(rounds = 6): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
    });
  }
}

function renderZone(state: StreamState): void {
  render(
    <AppProviders>
      <ZoneList state={state} />
    </AppProviders>,
  );
}

function zoneItems(): HTMLElement[] {
  return within(screen.getByRole("list", { name: LIST_NAME })).getAllByRole("listitem");
}

function muted(root: Element): Element[] {
  return Array.from(root.querySelectorAll(MUTED));
}

// ---------------------------------------------------------------- DoD-1
describe("ZoneList — the user row's body is muted (DEC-F016-2, DEC-F016-4)", () => {
  it('the "You" item holds exactly one data-tone="muted" element containing "Hi there"; "Assistant" and "Tool" hold none — DoD-1', () => {
    stubFetch();
    renderZone(seeded(dodOneZone()));

    const items = zoneItems();
    expect(items).toHaveLength(3);
    const [you, assistant, tool] = items as [HTMLElement, HTMLElement, HTMLElement];
    expect(within(you).getByText("You")).toBeInTheDocument();
    expect(within(assistant).getByText("Assistant")).toBeInTheDocument();
    expect(within(tool).getByText("Tool")).toBeInTheDocument();

    const youMuted = muted(you);
    expect(youMuted).toHaveLength(1);
    expect(youMuted[0]?.textContent).toContain("Hi there");

    expect(muted(assistant)).toEqual([]);
    expect(muted(tool)).toEqual([]);
  });
});

// ---------------------------------------------------------------- DoD-2
describe("ZoneMessage — read-only rows (editable={false})", () => {
  /** Renders each row as a read-only ZoneMessage inside a labelled list. */
  function renderReadOnly(rows: Message[]): HTMLElement[] {
    const state = seeded([]);
    render(
      <AppProviders>
        <ul aria-label="Read-only rows">
          {rows.map((message) => (
            <ZoneMessage key={message.id} state={state} message={message} editable={false} />
          ))}
        </ul>
      </AppProviders>,
    );
    return within(screen.getByRole("list", { name: "Read-only rows" })).getAllByRole("listitem");
  }

  it("a read-only user row shows its body inside a data-tone=\"muted\" element — DoD-2", () => {
    stubFetch();
    const [you] = renderReadOnly([row(USER_ID, "user", "Hi there")]) as [HTMLElement];

    const youMuted = muted(you);
    expect(youMuted).toHaveLength(1);
    expect(youMuted[0]?.textContent).toContain("Hi there");
  });

  it("read-only assistant and tool rows carry no data-tone=\"muted\" element — DoD-2", () => {
    stubFetch();
    const items = renderReadOnly([row(ASSISTANT_ID, "assistant", "Hello back"), toolRow(TOOL_ID, "Found 2 memos.")]);

    expect(items).toHaveLength(2);
    for (const item of items) {
      expect(muted(item)).toEqual([]);
    }
  });
});

// ---------------------------------------------------------------- DoD-3
describe("DiscussionGroup — the reused row keeps the tone (US-040.AC-1)", () => {
  it('expanded, the "You" item has its text inside a data-tone="muted" element and the "Assistant" item has none — DoD-3', async () => {
    const log = stubFetch([row("7250000000000000211", "user", "Write me a reply"), row("7250000000000000213", "assistant", "I wave back.")]);
    const user = newUser();
    render(
      <AppProviders>
        <DiscussionGroup entryId={ENTRY_ID} state={new StreamState(SESSION_ID)} />
      </AppProviders>,
    );

    await user.click(screen.getByRole("button", { name: SHOW_DISCUSSION }));
    const list = await screen.findByRole("list", { name: DISCUSSION_LIST }, { timeout: 2000 });
    await flush();

    expect(log).toContain(DISCUSSION_LINE);
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    const [you, assistant] = items as [HTMLElement, HTMLElement];
    expect(within(you).getByText("You")).toBeInTheDocument();
    expect(within(assistant).getByText("Assistant")).toBeInTheDocument();

    const youMuted = muted(you);
    expect(youMuted).toHaveLength(1);
    expect(youMuted[0]?.textContent).toContain("Write me a reply");
    expect(muted(assistant)).toEqual([]);
  });
});

// ---------------------------------------------------------------- DoD-4
describe("ZoneList — painting survives inside the muted wrapper (DEC-F016-3)", () => {
  // The painter's shapes (MessageBody.test.tsx): a wholly-parenthesised text is the OOC card
  // with no chips, any other text paints its (( )) fragments as chips — so one row cannot hold
  // both; the two shapes are seeded as two user rows.
  it('a user row "Text ((hint)) more" keeps its data-paren="fragment" chip inside the muted wrapper — DoD-4', () => {
    stubFetch();
    renderZone(seeded([row(USER_ID, "user", "Text ((hint)) more")]));

    const [you] = zoneItems() as [HTMLElement];
    const wrappers = muted(you);
    expect(wrappers).toHaveLength(1);
    const chips = (wrappers[0] as Element).querySelectorAll('[data-paren="fragment"]');
    expect(chips).toHaveLength(1);
    expect(chips[0]?.textContent).toBe("((hint))");
  });

  it('a wholly-parenthesised user row keeps its data-paren="ooc" card inside the muted wrapper — DoD-4', () => {
    stubFetch();
    renderZone(seeded([row(USER_ID, "user", "((just a note))")]));

    const [you] = zoneItems() as [HTMLElement];
    const wrappers = muted(you);
    expect(wrappers).toHaveLength(1);
    const card = (wrappers[0] as Element).querySelector('[data-paren="ooc"]');
    expect(card).not.toBeNull();
    expect(card?.textContent).toContain("((just a note))");
  });
});

// ---------------------------------------------------------------- DoD-5
describe("ZoneList — editing a user row (DEC-F016-4, US-115.AC-1)", () => {
  it('"Edit message" shows the "Edit message text" textarea with the row\'s text, not inside any data-tone="muted" element — DoD-5', async () => {
    stubFetch();
    const user = newUser();
    renderZone(seeded(dodOneZone()));

    await user.click(within(zoneItems()[0] as HTMLElement).getByRole("button", { name: EDIT_NAME }));

    const textarea = screen.getByRole("textbox", { name: EDITOR_NAME });
    expect(textarea).toHaveValue("Hi there");
    expect(textarea.closest(MUTED)).toBeNull();
  });

  it("leaving the editor unchanged brings the muted body back — DoD-5", async () => {
    const log = stubFetch();
    const user = newUser();
    renderZone(seeded(dodOneZone()));

    await user.click(within(zoneItems()[0] as HTMLElement).getByRole("button", { name: EDIT_NAME }));
    fireEvent.blur(screen.getByRole("textbox", { name: EDITOR_NAME }));

    await waitFor(
      () => {
        expect(screen.queryByRole("textbox", { name: EDITOR_NAME })).toBeNull();
      },
      { timeout: 2000 },
    );
    await flush();

    expect(log).toEqual([]);
    const youMuted = muted(zoneItems()[0] as HTMLElement);
    expect(youMuted).toHaveLength(1);
    expect(youMuted[0]?.textContent).toContain("Hi there");
  });
});
