// Feature 022, step 006 — the live reply beneath the zone rows (DoD-6..DoD-8)
// (docs/plans/022.discussion-ui/006.zone-rows-live-reply-regenerate.md).
//
// Expected values come from the step's Interface intent and Definition of done, context.md D4,
// D5, D6, D7, the UI strings table and 006.context.md:
//   - while streaming (streaming text non-null) a region "Live reply" renders after the
//     "Zone messages" list (a sibling, not an item), even with an empty zone;
//   - it holds the author label "Assistant", then one open tool block per live tool call in list
//     order (name, status word, arguments, summary), then the streaming text through the
//     assistant body with thinking open ("Hide thinking");
//   - it has no "Edit message" (nor any edit) control;
//   - a text change or a live tool status change does not remount the open blocks;
//   - with streaming text null nothing renders.
// "Assistant" lookups are scoped to the region or a list item (both carry it).
import { act, render, screen, waitFor, within } from "@testing-library/react";
import { runInAction } from "mobx";
import { describe, expect, it } from "vitest";
import { LiveMessage } from "../../src/app/LiveMessage";
import { ZoneList } from "../../src/app/ZoneList";
import type { Message, MessageRole } from "../../src/app/streamApi";
import { StreamState, type LiveToolCall } from "../../src/app/streamState";
import { AppProviders } from "../../src/shared/AppProviders";

// ---------------------------------------------------------------- strings (UI strings table)
const LIST_NAME = "Zone messages";
const LIVE_REPLY = "Live reply";
const EDIT_NAME = "Edit message";
const EDITOR_NAME = "Edit message text";
const HIDE_THINKING = "Hide thinking";
const HIDE_TOOL = "Hide tool call";
const QUERY_PAIR = '"query": "lighthouse"';

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "7250000000000000042";
const USER_ID = "7250000000000000101";
const STAMP = "2026-10-04T09:00:00.000000+00:00";

function row(id: string, role: MessageRole, text: string): Message {
  return { id, session_id: SESSION_ID, role, kind: null, text, settled_at: null, created_at: STAMP, updated_at: STAMP };
}

const FIND_IT = row(USER_ID, "user", "Find it");
const STREAMING = "<think>look up</think>Here it";

const C1_RUNNING: LiveToolCall = {
  callId: "c1",
  tool: "memo_search",
  args: { query: "lighthouse" },
  status: "running",
  summary: null,
};

type Seed = { zone?: Message[]; streamingText?: string | null; liveTools?: LiveToolCall[] };

function seeded(seed: Seed = {}): StreamState {
  const state = new StreamState(SESSION_ID);
  runInAction(() => {
    state.zone = seed.zone ?? [];
    if (seed.streamingText !== undefined) state.streamingText = seed.streamingText;
    if (seed.liveTools !== undefined) state.liveTools = seed.liveTools;
    state.status = "ready";
  });
  return state;
}

function streamingSeed(): StreamState {
  return seeded({ zone: [FIND_IT], streamingText: STREAMING, liveTools: [{ ...C1_RUNNING }] });
}

function renderZone(state: StreamState): void {
  render(
    <AppProviders>
      <ZoneList state={state} />
    </AppProviders>,
  );
}

function liveReply(): HTMLElement {
  return screen.getByRole("region", { name: LIVE_REPLY });
}

function precedes(first: Element, second: Element): boolean {
  return (first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

/** Index of `needle` in `haystack`, failing when absent. */
function at(haystack: string, needle: string): number {
  const index = haystack.indexOf(needle);
  expect(index, `expected ${JSON.stringify(needle)} in the live reply`).toBeGreaterThanOrEqual(0);
  return index;
}

// ---------------------------------------------------------------- DoD-6
describe("LiveMessage — the live reply while streaming (D6, U4)", () => {
  it('the "Live reply" region is present after the "Zone messages" list in document order, not inside it — DoD-6', () => {
    renderZone(streamingSeed());

    const list = screen.getByRole("list", { name: LIST_NAME });
    const region = liveReply();
    expect(precedes(list, region)).toBe(true);
    expect(list.contains(region)).toBe(false);
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
  });

  it("shows Assistant, then the open memo_search block (Running and the arguments), then look up (with Hide thinking) and Here it — DoD-6", () => {
    renderZone(streamingSeed());

    const region = liveReply();
    expect(within(region).getByText("Assistant")).toBeInTheDocument();
    expect(within(region).getByText("memo_search")).toBeInTheDocument();
    expect(within(region).getByText("Running")).toBeInTheDocument();
    expect(within(region).getByRole("button", { name: HIDE_TOOL })).toBeInTheDocument();
    expect(within(region).getByRole("button", { name: HIDE_THINKING })).toBeInTheDocument();

    const text = region.textContent ?? "";
    const assistantAt = at(text, "Assistant");
    const toolAt = at(text, "memo_search");
    const argsAt = at(text, QUERY_PAIR);
    const thinkAt = at(text, "look up");
    const answerAt = at(text, "Here it");
    expect(assistantAt).toBeLessThan(toolAt);
    expect(toolAt).toBeLessThan(argsAt);
    expect(argsAt).toBeLessThan(thinkAt);
    expect(thinkAt).toBeLessThan(answerAt);
    expect(text).not.toContain("<think>");
  });

  it('contains no "Edit message" control and no editor — DoD-6', () => {
    renderZone(streamingSeed());

    const region = liveReply();
    expect(within(region).queryByRole("button", { name: EDIT_NAME })).toBeNull();
    expect(within(region).queryByRole("textbox", { name: EDITOR_NAME })).toBeNull();
    expect(within(region).queryByRole("textbox")).toBeNull();
  });
});

// ---------------------------------------------------------------- DoD-7
describe("LiveMessage — updates without remounting the open blocks (D7)", () => {
  it("an appended token shows the new text and keeps the same open thinking block (Hide thinking stays) — DoD-7", async () => {
    const state = streamingSeed();
    renderZone(state);
    const thinkingToggle = within(liveReply()).getByRole("button", { name: HIDE_THINKING });

    act(() => {
      runInAction(() => {
        state.streamingText = `${STREAMING} is`;
      });
    });

    await waitFor(() => {
      expect(liveReply().textContent).toContain("Here it is");
    });
    const after = within(liveReply()).getByRole("button", { name: HIDE_THINKING });
    expect(after).toBe(thinkingToggle);
    expect(liveReply().textContent).toContain("look up");
  });

  it("when the live tool becomes ok with a summary, its block stays open and shows Done and the summary — DoD-7", async () => {
    const state = streamingSeed();
    renderZone(state);
    const toolToggle = within(liveReply()).getByRole("button", { name: HIDE_TOOL });

    act(() => {
      runInAction(() => {
        state.liveTools[0] = { ...C1_RUNNING, status: "ok", summary: "Found 2 memos." };
      });
    });

    await waitFor(() => {
      expect(within(liveReply()).getByText("Done")).toBeInTheDocument();
    });
    const region = liveReply();
    expect(region.textContent).toContain("Found 2 memos.");
    expect(region.textContent).toContain(QUERY_PAIR);
    expect(within(region).queryByText("Running")).toBeNull();
    expect(within(region).getByRole("button", { name: HIDE_TOOL })).toBe(toolToggle);
  });
});

// ---------------------------------------------------------------- DoD-8
describe("LiveMessage — before accepted, and not streaming (D6)", () => {
  it('with an empty zone and streaming text "" the Live reply renders with Assistant and no "Zone messages" list exists — DoD-8', () => {
    renderZone(seeded({ zone: [], streamingText: "" }));

    const region = liveReply();
    expect(within(region).getByText("Assistant")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: LIST_NAME })).toBeNull();
  });

  it("with streaming text null no Live reply region exists — DoD-8", () => {
    renderZone(seeded({ zone: [FIND_IT], streamingText: null }));

    expect(screen.queryByRole("region", { name: LIVE_REPLY })).toBeNull();
  });

  it("LiveMessage alone renders nothing when streaming text is null — DoD-8", () => {
    render(
      <AppProviders>
        <div data-testid="host">
          <LiveMessage state={seeded({ zone: [], streamingText: null })} />
        </div>
      </AppProviders>,
    );

    expect(screen.queryByRole("region", { name: LIVE_REPLY })).toBeNull();
    expect(screen.getByTestId("host").childElementCount).toBe(0);
  });
});
