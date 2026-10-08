// Feature 022, step 006 — role-aware zone rows, the read-only row mode, the live -> persisted
// transition and the Regenerate control (DoD-1..DoD-5, DoD-9, DoD-10)
// (docs/plans/022.discussion-ui/006.zone-rows-live-reply-regenerate.md).
//
// Expected values come from the step's Interface intent and Definition of done, context.md D4
// (row 3), D5, D6, D8, D9, D10, D12, D14, the UI strings table and 006.context.md:
//   - user rows render painted; assistant rows through the assistant body with thinking
//     collapsed ("Show thinking", think text absent); tool rows as a collapsed tool block (name,
//     status word, "Show tool call", arguments and summary absent until opened);
//   - "Edit message" renders iff editable (default true) and the role is not "tool" — absent,
//     not disabled; the assistant editor holds the raw stored text, think tags included;
//   - "Regenerate" (a labelled button) follows the zone list iff not streaming, not busy and a
//     non-tool row exists; pressing it POSTs …/zone/compose with body {} under the mount signal.
// Every await is bounded.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { runInAction } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ZoneList, ZoneMessage } from "../../src/app/ZoneList";
import type { Message, MessageRole } from "../../src/app/streamApi";
import { StreamState, type LiveToolCall } from "../../src/app/streamState";
import { AppProviders } from "../../src/shared/AppProviders";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- strings (UI strings table)
const LIST_NAME = "Zone messages";
const LIVE_REPLY = "Live reply";
const EDIT_NAME = "Edit message";
const EDITOR_NAME = "Edit message text";
const SHOW_THINKING = "Show thinking";
const SHOW_TOOL = "Show tool call";
const REGENERATE = "Regenerate";
const QUERY_PAIR = '"query": "lighthouse"';

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "7250000000000000042";
const ZONE_PATH = `/api/sessions/${SESSION_ID}/zone`;
const COMPOSE_PATH = `/api/sessions/${SESSION_ID}/zone/compose`;

const USER_ID = "7250000000000000101";
const ASSISTANT_ID = "7250000000000000102";
const TOOL_ID = "7250000000000000103";
const ASSISTANT_PATH = `/api/messages/${ASSISTANT_ID}`;

const ASSISTANT_RAW = "<think>plan</think>\n\nHello there";

const STAMP = "2026-10-04T09:00:00.000000+00:00";
const LATER = "2026-10-04T09:05:00.000000+00:00";

function row(id: string, role: MessageRole, text: string, updatedAt = STAMP): Message {
  return {
    id,
    session_id: SESSION_ID,
    role,
    kind: null,
    text,
    settled_at: null,
    created_at: STAMP,
    updated_at: updatedAt,
    tool_name: null,
    tool_status: null,
    tool_args: null,
  };
}

function toolRow(id: string, text: string, args: Record<string, unknown> = { query: "lighthouse" }): Message {
  return { ...row(id, "tool", text), tool_name: "memo_search", tool_status: "ok", tool_args: args };
}

const USER_ROW = row(USER_ID, "user", "Hi");
const ASSISTANT_ROW = row(ASSISTANT_ID, "assistant", ASSISTANT_RAW);
const TOOL_ROW = toolRow(TOOL_ID, "Found 2 memos.");

function dodOneZone(): Message[] {
  return [USER_ROW, ASSISTANT_ROW, TOOL_ROW];
}

type Seed = { zone?: Message[]; streamingText?: string | null; busy?: boolean; liveTools?: LiveToolCall[] };

function seeded(seed: Seed = {}): StreamState {
  const state = new StreamState(SESSION_ID);
  runInAction(() => {
    state.zone = seed.zone ?? [];
    if (seed.streamingText !== undefined) state.streamingText = seed.streamingText;
    if (seed.busy !== undefined) state.busy = seed.busy;
    if (seed.liveTools !== undefined) state.liveTools = seed.liveTools;
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

function abortError(): DOMException {
  return new DOMException("The operation was aborted.", "AbortError");
}

type Seen = { line: string; body: string | null; signal: AbortSignal | undefined };

function stubFetch(route: (seen: Seen) => Response | Promise<Response> | undefined): Seen[] {
  const log: Seen[] = [];
  const impl: FetchFn = async (input, init) => {
    const signal = init?.signal ?? (input instanceof Request ? input.signal : undefined) ?? undefined;
    const seen: Seen = {
      line: `${requestMethod(input, init)} ${requestUrl(input).pathname}`,
      body: typeof init?.body === "string" ? init.body : null,
      signal,
    };
    log.push(seen);
    if (signal?.aborted === true) throw abortError();
    const answer = route(seen);
    if (answer !== undefined) return answer;
    return envelope("unexpected", 500);
  };
  vi.stubGlobal("fetch", vi.fn(impl));
  return log;
}

function lines(log: Seen[]): string[] {
  return log.map((seen) => seen.line);
}

const enc = new TextEncoder();

type HeldSse = { response: Response; push: (payload: unknown) => void };

/** An SSE body held open; it errors when the request's signal aborts. */
function heldSse(signal: AbortSignal | undefined): HeldSse {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  let ended = false;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  const fail = (): void => {
    if (ended) return;
    ended = true;
    try {
      controller.error(abortError());
    } catch {
      // already cancelled by the reader
    }
  };
  if (signal !== undefined) {
    if (signal.aborted) fail();
    else signal.addEventListener("abort", fail, { once: true });
  }
  return {
    response: new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } }),
    push(payload) {
      if (ended) return;
      try {
        controller.enqueue(enc.encode(`data: ${JSON.stringify(payload)}\n\n`));
      } catch {
        // already cancelled by the reader
      }
    },
  };
}

async function until(predicate: () => boolean, label: string, ms = 2000): Promise<void> {
  const start = Date.now();
  while (!predicate()) {
    if (Date.now() - start > ms) throw new Error(`condition not met within ${ms}ms: ${label}`);
    await act(async () => {
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
    });
  }
}

async function flush(rounds = 8): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
    });
  }
}

function newUser(): ReturnType<typeof userEvent.setup> {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

function renderZone(state: StreamState, signal?: AbortSignal): void {
  render(
    <AppProviders>
      <ZoneList state={state} signal={signal} />
    </AppProviders>,
  );
}

function zoneList(): HTMLElement {
  return screen.getByRole("list", { name: LIST_NAME });
}

function zoneItems(): HTMLElement[] {
  return within(zoneList()).getAllByRole("listitem");
}

function item(index: number): HTMLElement {
  const found = zoneItems()[index];
  if (found === undefined) throw new Error(`no zone item #${index}`);
  return found;
}

function precedes(first: Element, second: Element): boolean {
  return (first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

/** The body checks shared by DoD-1 and DoD-5, over the three items [user, assistant, tool]. */
function expectDodOneBodies(items: HTMLElement[]): void {
  const [userItem, assistantItem, toolItem] = items as [HTMLElement, HTMLElement, HTMLElement];

  expect(userItem.textContent).toContain("Hi");

  expect(assistantItem.textContent).toContain("Hello there");
  expect(within(assistantItem).getByRole("button", { name: SHOW_THINKING })).toBeInTheDocument();
  expect(assistantItem.textContent).not.toContain("plan");

  expect(within(toolItem).getByText("memo_search")).toBeInTheDocument();
  expect(within(toolItem).getByText("Done")).toBeInTheDocument();
  expect(within(toolItem).getByRole("button", { name: SHOW_TOOL })).toBeInTheDocument();
  expect(toolItem.textContent).not.toContain(QUERY_PAIR);
  expect(toolItem.textContent).not.toContain("lighthouse");
}

// ---------------------------------------------------------------- DoD-1, DoD-2
describe("ZoneMessage — bodies by role (D5)", () => {
  it('renders three "Zone messages" items labelled You, Assistant, Tool in order; the assistant shows Hello there with Show thinking and no plan; the tool shows memo_search, Done and Show tool call with no arguments — DoD-1', () => {
    renderZone(seeded({ zone: dodOneZone() }));

    const items = zoneItems();
    expect(items).toHaveLength(3);
    expect(within(items[0] as HTMLElement).getByText("You")).toBeInTheDocument();
    expect(within(items[1] as HTMLElement).getByText("Assistant")).toBeInTheDocument();
    expect(within(items[2] as HTMLElement).getByText("Tool")).toBeInTheDocument();

    expectDodOneBodies(items);
  });

  it('"Edit message" is present once on the user and assistant items and absent on the tool item — DoD-2', () => {
    renderZone(seeded({ zone: dodOneZone() }));

    expect(within(item(0)).getAllByRole("button", { name: EDIT_NAME })).toHaveLength(1);
    expect(within(item(1)).getAllByRole("button", { name: EDIT_NAME })).toHaveLength(1);
    expect(within(item(2)).queryByRole("button", { name: EDIT_NAME })).toBeNull();
    expect(screen.getAllByRole("button", { name: EDIT_NAME })).toHaveLength(2);
  });
});

// ---------------------------------------------------------------- DoD-3
describe("ZoneMessage — persisted blocks re-expand (US-114.AC-3)", () => {
  it('pressing Show thinking on the assistant item reveals plan — DoD-3', async () => {
    const user = newUser();
    renderZone(seeded({ zone: dodOneZone() }));

    expect(item(1).textContent).not.toContain("plan");
    await user.click(within(item(1)).getByRole("button", { name: SHOW_THINKING }));

    await waitFor(() => {
      expect(item(1).textContent).toContain("plan");
    });
    expect(item(1).textContent).toContain("Hello there");
  });

  it('pressing Show tool call on the tool item reveals "query": "lighthouse" and Found 2 memos. — DoD-3', async () => {
    const user = newUser();
    renderZone(seeded({ zone: dodOneZone() }));

    expect(item(2).textContent).not.toContain(QUERY_PAIR);
    await user.click(within(item(2)).getByRole("button", { name: SHOW_TOOL }));

    await waitFor(() => {
      expect(item(2).textContent).toContain(QUERY_PAIR);
    });
    expect(item(2).textContent).toContain("Found 2 memos.");
  });
});

// ---------------------------------------------------------------- DoD-4
describe("ZoneMessage — the assistant editor holds the raw text (D10)", () => {
  it('"Edit message" on the assistant item opens "Edit message text" holding the raw think-tagged text; Hello, friend + blur PATCHes exactly {"text":"Hello, friend"} and the item shows the served text — DoD-4', async () => {
    const log = stubFetch((seen) =>
      seen.line === `PATCH ${ASSISTANT_PATH}`
        ? jsonResponse(row(ASSISTANT_ID, "assistant", "Hello, friend", LATER), 200)
        : undefined,
    );
    const user = newUser();
    renderZone(seeded({ zone: dodOneZone() }));

    await user.click(within(item(1)).getByRole("button", { name: EDIT_NAME }));
    const textbox = screen.getByRole("textbox", { name: EDITOR_NAME });
    expect(textbox).toHaveValue(ASSISTANT_RAW);

    fireEvent.change(textbox, { target: { value: "Hello, friend" } });
    fireEvent.blur(textbox);

    await waitFor(() => {
      expect(screen.queryByRole("textbox", { name: EDITOR_NAME })).toBeNull();
    });
    await waitFor(() => {
      expect(item(1).textContent).toContain("Hello, friend");
    });
    await flush();

    expect(lines(log)).toEqual([`PATCH ${ASSISTANT_PATH}`]);
    expect(log[0]?.body).toBe('{"text":"Hello, friend"}');
    expect(item(1).textContent).not.toContain("Hello there");
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------- DoD-5
describe("ZoneMessage — read-only mode (D12, US-116.AC-1)", () => {
  it('with editable false, user, assistant and tool rows show no "Edit message" and their bodies render as in DoD-1 — DoD-5', () => {
    const state = seeded({ zone: [] });
    render(
      <AppProviders>
        <ul aria-label="Read-only rows">
          {dodOneZone().map((message) => (
            <ZoneMessage key={message.id} state={state} message={message} editable={false} />
          ))}
        </ul>
      </AppProviders>,
    );

    const items = within(screen.getByRole("list", { name: "Read-only rows" })).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    for (const listItem of items) {
      expect(within(listItem).queryByRole("button", { name: EDIT_NAME })).toBeNull();
    }
    expect(screen.queryByRole("button", { name: EDIT_NAME })).toBeNull();
    expect(screen.queryByRole("textbox", { name: EDITOR_NAME })).toBeNull();

    expect(within(items[0] as HTMLElement).getByText("You")).toBeInTheDocument();
    expect(within(items[1] as HTMLElement).getByText("Assistant")).toBeInTheDocument();
    expect(within(items[2] as HTMLElement).getByText("Tool")).toBeInTheDocument();
    expectDodOneBodies(items);
  });
});

// ---------------------------------------------------------------- DoD-9
describe("ZoneList — the live -> persisted transition (D5, D6)", () => {
  it("after the zone re-read and the clearing action, no Live reply exists, the assistant item shows Here it is with thinking collapsed and the tool item is collapsed — DoD-9", async () => {
    const liveC1: LiveToolCall = {
      callId: "c1",
      tool: "memo_search",
      args: { query: "lighthouse" },
      status: "running",
      summary: null,
    };
    const findIt = row(USER_ID, "user", "Find it");
    const state = seeded({
      zone: [findIt],
      streamingText: "<think>look up</think>Here it",
      liveTools: [liveC1],
    });
    renderZone(state);
    expect(screen.getByRole("region", { name: LIVE_REPLY })).toBeInTheDocument();

    act(() => {
      runInAction(() => {
        state.zone = [
          findIt,
          toolRow(TOOL_ID, "Found 2 memos."),
          row(ASSISTANT_ID, "assistant", "<think>look up</think>Here it is"),
        ];
        state.streamingText = null;
        state.liveTools = [];
      });
    });

    await waitFor(() => {
      expect(screen.queryByRole("region", { name: LIVE_REPLY })).toBeNull();
    });

    const items = zoneItems();
    expect(items).toHaveLength(3);
    const toolItem = items[1] as HTMLElement;
    const assistantItem = items[2] as HTMLElement;

    expect(within(assistantItem).getByText("Assistant")).toBeInTheDocument();
    expect(assistantItem.textContent).toContain("Here it is");
    expect(within(assistantItem).getByRole("button", { name: SHOW_THINKING })).toBeInTheDocument();
    expect(assistantItem.textContent).not.toContain("look up");

    expect(within(toolItem).getByText("Tool")).toBeInTheDocument();
    expect(within(toolItem).getByRole("button", { name: SHOW_TOOL })).toBeInTheDocument();
    expect(toolItem.textContent).not.toContain(QUERY_PAIR);
    expect(toolItem.textContent).not.toContain("Found 2 memos.");

    expect(document.body.textContent).not.toContain("look up");
  });
});

// ---------------------------------------------------------------- DoD-10
describe("ZoneList — the Regenerate control (D8, D14)", () => {
  it("is present after the zone list when not streaming, not busy, and the zone holds a non-tool row — DoD-10", () => {
    renderZone(seeded({ zone: dodOneZone(), busy: false }));

    const button = screen.getByRole("button", { name: REGENERATE });
    expect(precedes(zoneList(), button)).toBe(true);
    expect(zoneList().contains(button)).toBe(false);
  });

  it.each<[string, Seed]>([
    ["the zone is empty", { zone: [] }],
    ["the zone is [tool] only", { zone: [TOOL_ROW] }],
    ["streaming", { zone: [USER_ROW], streamingText: "" }],
    ["busy", { zone: [USER_ROW], busy: true }],
  ])("is absent when %s — DoD-10", (_label, seed) => {
    renderZone(seeded(seed));

    expect(screen.queryByRole("button", { name: REGENERATE })).toBeNull();
  });

  it("pressing it POSTs /api/sessions/<id>/zone/compose with body {} and runs under the mount signal — DoD-10", async () => {
    const streams: HeldSse[] = [];
    const log = stubFetch((seen) => {
      if (seen.line === `POST ${COMPOSE_PATH}`) {
        const held = heldSse(seen.signal);
        streams.push(held);
        return held.response;
      }
      if (seen.line === `GET ${ZONE_PATH}`) return jsonResponse({ messages: [USER_ROW] }, 200);
      return undefined;
    });
    const mount = new AbortController();
    const state = seeded({ zone: [USER_ROW] });
    const user = newUser();
    renderZone(state, mount.signal);

    await user.click(screen.getByRole("button", { name: REGENERATE }));
    await until(() => streams.length === 1, "compose POST issued");

    const posts = log.filter((seen) => seen.line === `POST ${COMPOSE_PATH}`);
    expect(posts).toHaveLength(1);
    expect(JSON.parse(posts[0]?.body ?? "null")).toStrictEqual({});
    expect(lines(log)).not.toContain(`POST /api/sessions/${SESSION_ID}/zone/messages`);

    const stream = streams[0] as HeldSse;
    stream.push({ event: "token", text: "A" });
    await until(() => state.streamingText === "A", "first token streamed");

    // The mount signal reaches the run: after it aborts, nothing more is written.
    mount.abort();
    stream.push({ event: "token", text: "B" });
    await flush();

    expect(state.streamingText ?? "").not.toContain("B");
  });
});
