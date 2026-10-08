// Feature 022, step 007 — the collapsed, read-only Discussion group mounted under settled entries
// (DoD-1..DoD-4, DoD-8, DoD-9) (docs/plans/022.discussion-ui/007.discussion-group.md).
//
// Expected values come from the step's Interface intent and Definition of done, context.md D5,
// D11, D12, the UI strings table and 007.context.md:
//   - every settled non-partner entry carries a collapsed header: "Show discussion" toggle, the
//     text "Discussion" (exactly, before any load) and the marker "Read-only"; partner entries
//     carry none; nothing is requested while collapsed;
//   - first expand issues one GET /api/messages/<entry id>/discussion and renders the rows as a
//     list labelled "Discussion messages", one read-only row per served message in served order
//     (no "Edit message"), thinking and tool blocks collapsed; the header then reads
//     "Discussion (N)" and the toggle is "Hide discussion";
//   - collapsing removes the list; re-expanding after a success re-uses the kept rows (no GET);
//   - settle's re-read collapses the zone into the new entry, whose group starts collapsed;
//   - 013's re-open control keeps its rule.
// Every await is bounded.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { runInAction } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StreamRecord } from "../../src/app/StreamRecord";
import { ZoneList } from "../../src/app/ZoneList";
import type { Message, MessageKind, MessageRole } from "../../src/app/streamApi";
import { StreamState, settleComposer } from "../../src/app/streamState";
import { AppProviders } from "../../src/shared/AppProviders";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- strings (UI strings table)
const RECORD_NAME = "Settled record";
const ZONE_LIST_NAME = "Zone messages";
const DISCUSSION_LIST = "Discussion messages";
const SHOW_DISCUSSION = "Show discussion";
const HIDE_DISCUSSION = "Hide discussion";
const DISCUSSION = "Discussion";
const READ_ONLY = "Read-only";
const EDIT_NAME = "Edit message";
const SHOW_THINKING = "Show thinking";
const SHOW_TOOL = "Show tool call";
const REOPEN_NAME = "Re-open last entry";
const QUERY_PAIR = '"query": "lighthouse"';

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "7250000000000000042";
const ENTRIES_PATH = `/api/sessions/${SESSION_ID}/entries`;
const ZONE_PATH = `/api/sessions/${SESSION_ID}/zone`;
const SETTLE_PATH = `/api/sessions/${SESSION_ID}/settle`;
const discussionPath = (id: string): string => `/api/messages/${id}/discussion`;

const PARTNER_ID = "7250000000000000201";
const TURN_ID = "7250000000000000202";
const DECISION_ID = "7250000000000000203";

const BURIED_USER_ID = "7250000000000000211";
const BURIED_TOOL_ID = "7250000000000000212";
const BURIED_ASSISTANT_ID = "7250000000000000213";

const STAMP = "2026-10-04T09:00:00.000000+00:00";

function entry(id: string, kind: MessageKind, text: string): Message {
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

const PARTNER = entry(PARTNER_ID, "partner", "They wave.");
const TURN = entry(TURN_ID, "turn", "I wave back.");
const DECISION = entry(DECISION_ID, "decision", "((skip))");

function dodOneRecord(): Message[] {
  return [PARTNER, TURN, DECISION];
}

/** DoD-2's served discussion: [user, tool (memo_search, ok, {query: lighthouse}), assistant]. */
function dodTwoDiscussion(): Message[] {
  return [
    row(BURIED_USER_ID, "user", "Write me a reply"),
    {
      ...row(BURIED_TOOL_ID, "tool", "Found 2 memos."),
      tool_name: "memo_search",
      tool_status: "ok",
      tool_args: { query: "lighthouse" },
    },
    row(BURIED_ASSISTANT_ID, "assistant", "<think>plan</think>\n\nI wave back."),
  ];
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

/** Stubs fetch keyed on exact "METHOD /path"; logs every request line. Unknown routes answer 500. */
function stubFetch(routes: Record<string, () => Response>): string[] {
  const log: string[] = [];
  const impl: FetchFn = async (input, init) => {
    const line = `${requestMethod(input, init)} ${requestUrl(input).pathname}`;
    log.push(line);
    const route = routes[line];
    if (route !== undefined) return route();
    return envelope("unexpected", 500);
  };
  vi.stubGlobal("fetch", vi.fn(impl));
  return log;
}

function discussionLines(log: string[]): string[] {
  return log.filter((line) => line.includes("/discussion"));
}

async function flush(rounds = 8): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
    });
  }
}

async function bounded<T>(promise: Promise<T>, label: string, ms = 2000): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_resolve, reject) => {
    timer = setTimeout(() => reject(new Error(`not settled within ${ms}ms: ${label}`)), ms);
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}

function newUser(): ReturnType<typeof userEvent.setup> {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

function renderRecord(state: StreamState): void {
  render(
    <AppProviders>
      <StreamRecord state={state} />
    </AppProviders>,
  );
}

function recordList(): HTMLElement {
  return screen.getByRole("list", { name: RECORD_NAME });
}

/** The record's own entries: direct listitem children only (nested discussion items excluded). */
function recordItems(): HTMLElement[] {
  const list = recordList();
  return within(list)
    .getAllByRole("listitem")
    .filter((li) => li.parentElement?.closest("ul, ol") === list);
}

function recordItem(index: number): HTMLElement {
  const found = recordItems()[index];
  if (found === undefined) throw new Error(`no record item #${index}`);
  return found;
}

function discussionItems(scope: HTMLElement): HTMLElement[] {
  return within(within(scope).getByRole("list", { name: DISCUSSION_LIST })).getAllByRole("listitem");
}

/** Renders DoD-1's record, expands the turn entry's group, and waits for DoD-2's three rows. */
async function openTurnDiscussion(): Promise<{ log: string[]; user: ReturnType<typeof userEvent.setup> }> {
  const log = stubFetch({
    [`GET ${discussionPath(TURN_ID)}`]: () => jsonResponse({ messages: dodTwoDiscussion() }, 200),
  });
  const user = newUser();
  renderRecord(seeded(dodOneRecord(), []));

  await user.click(within(recordItem(1)).getByRole("button", { name: SHOW_DISCUSSION }));
  await within(recordItem(1)).findByRole("list", { name: DISCUSSION_LIST }, { timeout: 2000 });
  return { log, user };
}

// ---------------------------------------------------------------- DoD-1
describe("StreamRecord — the collapsed Discussion group (D11)", () => {
  it('turn and decision entries carry "Show discussion", "Discussion" and "Read-only"; the partner entry carries none; no /discussion request and no "Discussion messages" list — DoD-1', async () => {
    const log = stubFetch({});
    renderRecord(seeded(dodOneRecord(), []));
    await flush();

    const items = recordItems();
    expect(items).toHaveLength(3);
    const [partnerItem, turnItem, decisionItem] = items as [HTMLElement, HTMLElement, HTMLElement];

    for (const scoped of [turnItem, decisionItem]) {
      expect(within(scoped).getAllByRole("button", { name: SHOW_DISCUSSION })).toHaveLength(1);
      expect(within(scoped).getByText(DISCUSSION)).toBeInTheDocument();
      expect(within(scoped).getByText(READ_ONLY)).toBeInTheDocument();
    }

    expect(within(partnerItem).queryByRole("button", { name: SHOW_DISCUSSION })).toBeNull();
    expect(within(partnerItem).queryByText(DISCUSSION)).toBeNull();
    expect(within(partnerItem).queryByText(READ_ONLY)).toBeNull();
    expect(screen.getAllByRole("button", { name: SHOW_DISCUSSION })).toHaveLength(2);

    expect(discussionLines(log)).toEqual([]);
    expect(screen.queryByRole("list", { name: DISCUSSION_LIST })).toBeNull();
    expect(screen.queryByRole("button", { name: HIDE_DISCUSSION })).toBeNull();
  });
});

// ---------------------------------------------------------------- DoD-2
describe("StreamRecord — expanding a discussion (D11, US-040.AC-1)", () => {
  it('pressing "Show discussion" on the turn entry issues exactly one GET …/discussion and shows You, Tool, Assistant in order, "Discussion (3)" and "Hide discussion" — DoD-2', async () => {
    const { log } = await openTurnDiscussion();
    await flush();

    expect(discussionLines(log)).toEqual([`GET ${discussionPath(TURN_ID)}`]);

    const turnItem = recordItem(1);
    const items = discussionItems(turnItem);
    expect(items).toHaveLength(3);
    const [userItem, toolItem, assistantItem] = items as [HTMLElement, HTMLElement, HTMLElement];

    expect(within(userItem).getByText("You")).toBeInTheDocument();
    expect(within(toolItem).getByText("Tool")).toBeInTheDocument();
    expect(within(assistantItem).getByText("Assistant")).toBeInTheDocument();

    expect(userItem.textContent).toContain("Write me a reply");
    expect(within(toolItem).getByText("memo_search")).toBeInTheDocument();
    expect(assistantItem.textContent).toContain("I wave back.");

    expect(within(turnItem).getByText("Discussion (3)")).toBeInTheDocument();
    expect(within(turnItem).getByRole("button", { name: HIDE_DISCUSSION })).toBeInTheDocument();
    expect(within(turnItem).queryByRole("button", { name: SHOW_DISCUSSION })).toBeNull();

    // The decision entry's group stays collapsed and unrequested.
    const decisionItem = recordItem(2);
    expect(within(decisionItem).getByRole("button", { name: SHOW_DISCUSSION })).toBeInTheDocument();
    expect(within(decisionItem).getByText(DISCUSSION)).toBeInTheDocument();
    expect(log).not.toContain(`GET ${discussionPath(DECISION_ID)}`);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------- DoD-3
describe("StreamRecord — the open discussion is read-only, blocks collapsed (US-116.AC-1, US-114.AC-2/3)", () => {
  it('no item carries "Edit message"; thinking and the tool block start collapsed — DoD-3', async () => {
    await openTurnDiscussion();

    const turnItem = recordItem(1);
    const list = within(turnItem).getByRole("list", { name: DISCUSSION_LIST });
    const [, toolItem, assistantItem] = discussionItems(turnItem) as [HTMLElement, HTMLElement, HTMLElement];

    expect(within(list).queryAllByRole("button", { name: EDIT_NAME })).toEqual([]);
    expect(within(list).queryAllByRole("textbox")).toEqual([]);

    expect(within(assistantItem).getByRole("button", { name: SHOW_THINKING })).toBeInTheDocument();
    expect(list.textContent).not.toContain("plan");

    expect(within(toolItem).getByRole("button", { name: SHOW_TOOL })).toBeInTheDocument();
    expect(list.textContent).not.toContain(QUERY_PAIR);
  });

  it('pressing "Show thinking" reveals plan and pressing "Show tool call" reveals the arguments — DoD-3', async () => {
    const { user } = await openTurnDiscussion();

    const turnItem = recordItem(1);
    const [, toolItem, assistantItem] = discussionItems(turnItem) as [HTMLElement, HTMLElement, HTMLElement];

    await user.click(within(assistantItem).getByRole("button", { name: SHOW_THINKING }));
    await waitFor(() => {
      expect(assistantItem.textContent).toContain("plan");
    });

    await user.click(within(toolItem).getByRole("button", { name: SHOW_TOOL }));
    await waitFor(() => {
      expect(toolItem.textContent).toContain(QUERY_PAIR);
    });

    // Still read-only once the blocks are open.
    const list = within(turnItem).getByRole("list", { name: DISCUSSION_LIST });
    expect(within(list).queryAllByRole("button", { name: EDIT_NAME })).toEqual([]);
  });
});

// ---------------------------------------------------------------- DoD-4
describe("StreamRecord — collapse and re-expand after a success (D11)", () => {
  it('"Hide discussion" removes the list; "Show discussion" again shows the same three items with no second GET — DoD-4', async () => {
    const { log, user } = await openTurnDiscussion();

    await user.click(within(recordItem(1)).getByRole("button", { name: HIDE_DISCUSSION }));
    await waitFor(() => {
      expect(screen.queryByRole("list", { name: DISCUSSION_LIST })).toBeNull();
    });
    expect(within(recordItem(1)).getByRole("button", { name: SHOW_DISCUSSION })).toBeInTheDocument();

    await user.click(within(recordItem(1)).getByRole("button", { name: SHOW_DISCUSSION }));
    await within(recordItem(1)).findByRole("list", { name: DISCUSSION_LIST }, { timeout: 2000 });
    await flush();

    const items = discussionItems(recordItem(1));
    expect(items).toHaveLength(3);
    expect(within(items[0] as HTMLElement).getByText("You")).toBeInTheDocument();
    expect(within(items[1] as HTMLElement).getByText("Tool")).toBeInTheDocument();
    expect(within(items[2] as HTMLElement).getByText("Assistant")).toBeInTheDocument();
    expect(items[0]?.textContent).toContain("Write me a reply");
    expect(items[2]?.textContent).toContain("I wave back.");

    expect(discussionLines(log)).toEqual([`GET ${discussionPath(TURN_ID)}`]);
  });
});

// ---------------------------------------------------------------- DoD-8
describe("Settle collapses the zone into the new entry (D12, US-039.AC-1, US-113.AC-2)", () => {
  it('after settleComposer the "Zone messages" list is gone, the new "My turn" entry shows Final with a collapsed group and no Draft anywhere; expanding shows Draft read-only — DoD-8', async () => {
    const DRAFT_ID = "7250000000000000301";
    const FINAL_ID = "7250000000000000302";
    const settledTurn = entry(FINAL_ID, "turn", "Final");

    const log = stubFetch({
      [`POST ${SETTLE_PATH}`]: () =>
        jsonResponse({ entry_id: FINAL_ID, kind: "turn", buried_ids: [DRAFT_ID] }, 200),
      [`GET ${ENTRIES_PATH}`]: () => jsonResponse({ entries: [PARTNER, settledTurn] }, 200),
      [`GET ${ZONE_PATH}`]: () => jsonResponse({ messages: [] }, 200),
      [`GET ${discussionPath(FINAL_ID)}`]: () =>
        jsonResponse({ messages: [row(DRAFT_ID, "user", "Draft")] }, 200),
    });

    const state = seeded([PARTNER], [row(DRAFT_ID, "user", "Draft"), row(FINAL_ID, "assistant", "Final")]);
    runInAction(() => {
      state.kindOverride = "turn";
    });
    render(
      <AppProviders>
        <StreamRecord state={state} />
        <ZoneList state={state} />
      </AppProviders>,
    );
    expect(screen.getByRole("list", { name: ZONE_LIST_NAME })).toBeInTheDocument();

    await act(async () => {
      await bounded(settleComposer(state), "settleComposer");
    });
    await flush();

    expect(log).toContain(`POST ${SETTLE_PATH}`);
    await waitFor(() => {
      expect(screen.queryByRole("list", { name: ZONE_LIST_NAME })).toBeNull();
    });

    const items = recordItems();
    expect(items).toHaveLength(2);
    const turnItem = items[1] as HTMLElement;
    expect(within(turnItem).getByText("My turn")).toBeInTheDocument();
    expect(turnItem.textContent).toContain("Final");
    expect(within(turnItem).getByRole("button", { name: SHOW_DISCUSSION })).toBeInTheDocument();
    expect(within(turnItem).getByText(DISCUSSION)).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: DISCUSSION_LIST })).toBeNull();
    expect(document.body.textContent).not.toContain("Draft");
    expect(discussionLines(log)).toEqual([]);

    const user = newUser();
    await user.click(within(turnItem).getByRole("button", { name: SHOW_DISCUSSION }));
    const list = await within(recordItem(1)).findByRole("list", { name: DISCUSSION_LIST }, { timeout: 2000 });

    expect(discussionLines(log)).toEqual([`GET ${discussionPath(FINAL_ID)}`]);
    const discussion = within(list).getAllByRole("listitem");
    expect(discussion).toHaveLength(1);
    expect(within(discussion[0] as HTMLElement).getByText("You")).toBeInTheDocument();
    expect(discussion[0]?.textContent).toContain("Draft");
    expect(within(list).queryAllByRole("button", { name: EDIT_NAME })).toEqual([]);
    expect(within(list).queryAllByRole("textbox")).toEqual([]);
  });
});

// ---------------------------------------------------------------- DoD-9
describe("StreamRecord — 013's re-open control is unchanged (013 D4)", () => {
  it("with an empty zone, Re-open sits on the last non-partner entry beside its Discussion header — DoD-9", () => {
    stubFetch({});
    renderRecord(seeded([PARTNER, TURN], []));

    expect(screen.getAllByRole("button", { name: REOPEN_NAME })).toHaveLength(1);
    const items = recordItems();
    expect(items).toHaveLength(2);
    const last = items[1] as HTMLElement;
    expect(within(last).getByRole("button", { name: REOPEN_NAME })).toBeInTheDocument();
    expect(within(last).getByRole("button", { name: SHOW_DISCUSSION })).toBeInTheDocument();
    expect(within(items[0] as HTMLElement).queryByRole("button", { name: REOPEN_NAME })).toBeNull();
  });

  it("with an empty zone and the last entry a decision, Re-open sits in the decision entry — DoD-9", () => {
    stubFetch({});
    renderRecord(seeded(dodOneRecord(), []));

    expect(screen.getAllByRole("button", { name: REOPEN_NAME })).toHaveLength(1);
    expect(within(recordItem(2)).getByRole("button", { name: REOPEN_NAME })).toBeInTheDocument();
  });

  it("with zone rows, Re-open is absent while the Discussion headers remain — DoD-9", () => {
    stubFetch({});
    renderRecord(seeded([PARTNER, TURN], [row("7250000000000000401", "user", "Z1")]));

    expect(screen.queryByRole("button", { name: REOPEN_NAME })).toBeNull();
    expect(screen.queryByLabelText(REOPEN_NAME)).toBeNull();
    expect(within(recordItem(1)).getByRole("button", { name: SHOW_DISCUSSION })).toBeInTheDocument();
  });
});
