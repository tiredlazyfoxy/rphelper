// Feature 022, step 007 — DiscussionGroup on its own: empty answer, inline failure with retry,
// and unmount while pending (DoD-5..DoD-7) (docs/plans/022.discussion-ui/007.discussion-group.md).
//
// Expected values come from the step's Interface intent and Definition of done, context.md D1,
// D11, the UI strings table and 007.context.md:
//   - an expand answered {"messages":[]} shows "No discussion behind this entry." and the header
//     reads "Discussion (0)";
//   - a failed expand shows "The discussion could not be loaded." inline, shows no list and does
//     not call notifyFailure; the failure is forgotten on collapse, so the next expand GETs again;
//   - the group's GET runs under its own AbortController, aborted on unmount; nothing is written
//     afterwards (no React warning, no error).
// Every await is bounded.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DiscussionGroup } from "../../src/app/DiscussionGroup";
import type { Message, MessageRole } from "../../src/app/streamApi";
import { StreamState } from "../../src/app/streamState";
import { AppProviders } from "../../src/shared/AppProviders";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- strings (UI strings table)
const DISCUSSION_LIST = "Discussion messages";
const SHOW_DISCUSSION = "Show discussion";
const HIDE_DISCUSSION = "Hide discussion";
const DISCUSSION = "Discussion";
const EMPTY_LINE = "No discussion behind this entry.";
const FAILURE_LINE = "The discussion could not be loaded.";

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "7250000000000000042";
const ENTRY_ID = "7250000000000000202";
const DISCUSSION_LINE = `GET /api/messages/${ENTRY_ID}/discussion`;
const STAMP = "2026-10-04T09:00:00.000000+00:00";

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

function twoRows(): Message[] {
  return [row("7250000000000000211", "user", "Write me a reply"), row("7250000000000000213", "assistant", "I wave back.")];
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

type Seen = { line: string; signal: AbortSignal | undefined };

/**
 * Stubs fetch; every request is logged as "METHOD /path" with its signal. `answer` is called
 * with the 0-based index of the discussion GET and the seen request.
 */
function stubDiscussion(answer: (index: number, seen: Seen) => Response | Promise<Response>): Seen[] {
  const log: Seen[] = [];
  let index = 0;
  const impl: FetchFn = async (input, init) => {
    const signal = init?.signal ?? (input instanceof Request ? input.signal : undefined) ?? undefined;
    const seen: Seen = { line: `${requestMethod(input, init)} ${requestUrl(input).pathname}`, signal };
    log.push(seen);
    if (seen.line !== DISCUSSION_LINE) return envelope("unexpected", 500);
    const current = index;
    index += 1;
    return answer(current, seen);
  };
  vi.stubGlobal("fetch", vi.fn(impl));
  return log;
}

function discussionGets(log: Seen[]): Seen[] {
  return log.filter((seen) => seen.line.includes("/discussion"));
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

function renderGroup(): ReturnType<typeof render> {
  const state = new StreamState(SESSION_ID);
  return render(
    <AppProviders>
      <DiscussionGroup entryId={ENTRY_ID} state={state} />
    </AppProviders>,
  );
}

// ---------------------------------------------------------------- DoD-5
describe("DiscussionGroup — an empty discussion (D11, D1)", () => {
  it('an expand answered {"messages":[]} shows "No discussion behind this entry." and the header reads "Discussion (0)" — DoD-5', async () => {
    const log = stubDiscussion(() => jsonResponse({ messages: [] }, 200));
    const user = newUser();
    renderGroup();

    expect(screen.getByText(DISCUSSION)).toBeInTheDocument();
    expect(discussionGets(log)).toEqual([]);

    await user.click(screen.getByRole("button", { name: SHOW_DISCUSSION }));

    expect(await screen.findByText(EMPTY_LINE, undefined, { timeout: 2000 })).toBeInTheDocument();
    expect(screen.getByText("Discussion (0)")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: DISCUSSION_LIST })).toBeNull();
    expect(screen.queryByText(FAILURE_LINE)).toBeNull();
    expect(screen.getByRole("button", { name: HIDE_DISCUSSION })).toBeInTheDocument();
    expect(discussionGets(log).map((seen) => seen.line)).toEqual([DISCUSSION_LINE]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------- DoD-6
describe("DiscussionGroup — an inline failure, forgotten on collapse (D11)", () => {
  it('a 404 message_not_found shows "The discussion could not be loaded.", no list, no notifyFailure; collapse + expand GETs again and the rows show — DoD-6', async () => {
    const log = stubDiscussion((index) =>
      index === 0 ? envelope("message_not_found", 404) : jsonResponse({ messages: twoRows() }, 200),
    );
    const user = newUser();
    renderGroup();

    await user.click(screen.getByRole("button", { name: SHOW_DISCUSSION }));

    expect(await screen.findByText(FAILURE_LINE, undefined, { timeout: 2000 })).toBeInTheDocument();
    await flush();
    expect(screen.queryByRole("list", { name: DISCUSSION_LIST })).toBeNull();
    expect(screen.queryByText(EMPTY_LINE)).toBeNull();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(discussionGets(log)).toHaveLength(1);
    // No successful load yet, so the header has no count.
    expect(screen.getByText(DISCUSSION)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: HIDE_DISCUSSION }));
    await waitFor(() => {
      expect(screen.queryByText(FAILURE_LINE)).toBeNull();
    });

    await user.click(screen.getByRole("button", { name: SHOW_DISCUSSION }));
    const list = await screen.findByRole("list", { name: DISCUSSION_LIST }, { timeout: 2000 });
    await flush();

    expect(discussionGets(log).map((seen) => seen.line)).toEqual([DISCUSSION_LINE, DISCUSSION_LINE]);
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]?.textContent).toContain("Write me a reply");
    expect(items[1]?.textContent).toContain("I wave back.");
    expect(screen.queryByText(FAILURE_LINE)).toBeNull();
    expect(screen.getByText("Discussion (2)")).toBeInTheDocument();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------- DoD-7
describe("DiscussionGroup — unmount while the GET is pending (D11)", () => {
  it("aborts the request's signal and writes nothing afterwards (no warning, no error) — DoD-7", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const log = stubDiscussion(
      (_index, seen) =>
        new Promise<Response>((_resolve, reject) => {
          const signal = seen.signal;
          if (signal === undefined) return; // never answers; the assertion below reports it
          if (signal.aborted) reject(abortError());
          else signal.addEventListener("abort", () => reject(abortError()), { once: true });
        }),
    );
    const user = newUser();
    const view = renderGroup();

    await user.click(screen.getByRole("button", { name: SHOW_DISCUSSION }));
    await until(() => discussionGets(log).length === 1, "discussion GET issued");

    const signal = discussionGets(log)[0]?.signal;
    expect(signal).toBeDefined();
    expect(signal?.aborted).toBe(false);

    view.unmount();
    await flush();

    expect(signal?.aborted).toBe(true);
    expect(consoleError).not.toHaveBeenCalled();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(discussionGets(log)).toHaveLength(1);
  });

  it("an answer that arrives after unmount is not written (no warning, no error) — DoD-7", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const gate: { release?: () => void } = {};
    const log = stubDiscussion(
      () =>
        new Promise<Response>((resolve) => {
          gate.release = () => resolve(jsonResponse({ messages: twoRows() }, 200));
        }),
    );
    const user = newUser();
    const view = renderGroup();

    await user.click(screen.getByRole("button", { name: SHOW_DISCUSSION }));
    await until(() => gate.release !== undefined, "discussion GET issued");
    const signal = discussionGets(log)[0]?.signal;

    view.unmount();
    expect(signal?.aborted).toBe(true);

    await act(async () => {
      gate.release?.();
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
    });
    await flush();

    expect(consoleError).not.toHaveBeenCalled();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(screen.queryByRole("list", { name: DISCUSSION_LIST })).toBeNull();
  });
});
