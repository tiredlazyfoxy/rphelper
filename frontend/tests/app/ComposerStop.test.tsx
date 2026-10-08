// Feature 019, step 004 — Stop in Send's slot
// (docs/plans/019.streaming-transport-and-stop/004.streaming-state-and-stop-slot.md), DoD-7..DoD-9;
// DoD-10 (glyph, size, tooltip in a browser) is manual/live.
//
// Expected behaviour comes from the step's Interface intent and Definition of done, context.md
// D13 and workspace-shell.md "The stop control" as cited there:
//   - while streaming the slot holds a button named "Stop" and **no** "Send" button exists
//     (absent, not disabled); pressing "Stop" aborts the compose handle's controller;
//   - Settle is unaffected: on my turn with a zone row it stays present and enabled;
//   - when not streaming, "Send" renders as before and there is no "Stop".
// "Streaming" is set up by assigning the streaming text and a handle directly in `runInAction`
// (004.context.md "Test notes"). Rendered with AppProviders; controls are found by name.
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { runInAction } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { Composer } from "../../src/app/Composer";
import type { Message, MessageRole } from "../../src/app/streamApi";
import { StreamState, type ComposeHandle } from "../../src/app/streamState";
import { AppProviders } from "../../src/shared/AppProviders";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "7250000000000000042";
const STAMP = "2026-10-04T09:00:00.000000+00:00";

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

type Seed = { zone?: Message[]; draft?: string };

function seeded(seed: Seed = {}): StreamState {
  const state = new StreamState(SESSION_ID);
  runInAction(() => {
    state.entries = [];
    state.zone = seed.zone ?? [];
    state.draft = seed.draft ?? "";
    state.status = "ready";
  });
  return state;
}

function freshHandle(): ComposeHandle {
  return { controller: new AbortController(), woundDown: Promise.resolve() };
}

function startStreaming(state: StreamState, handle: ComposeHandle, text = "Partial reply"): void {
  runInAction(() => {
    state.streamingText = text;
    state.composeHandle = handle;
  });
}

beforeEach(() => {
  notifyFailureSpy.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- harness
/** Records every request; none is expected in this file, so each answers a 500. */
function stubFetch(): Mock<FetchFn> {
  const mock = vi.fn<FetchFn>(() =>
    Promise.resolve(
      new Response(JSON.stringify({ error: { code: "unexpected", message: "unexpected", detail: {} } }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
  vi.stubGlobal("fetch", mock);
  return mock;
}

function renderComposer(state: StreamState): void {
  render(
    <AppProviders>
      <Composer state={state} />
    </AppProviders>,
  );
}

function newUser(): ReturnType<typeof userEvent.setup> {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

function precedes(first: Node, second: Node): boolean {
  return (first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

async function flush(): Promise<void> {
  await act(async () => {
    for (let round = 0; round < 3; round += 1) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  });
}

// ---------------------------------------------------------------- DoD-7
describe("Composer while streaming — Stop holds Send's slot (UC-085, workspace-shell, ui-conventions)", () => {
  it('a button named "Stop" is present and no button named "Send" exists (absent, not disabled) — DoD-7', () => {
    stubFetch();
    const state = seeded({ draft: "Next line" });
    startStreaming(state, freshHandle());
    renderComposer(state);

    expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send" })).toBeNull();
    expect(screen.queryAllByRole("button", { name: "Send", hidden: true })).toEqual([]);
  });

  it('pressing "Stop" aborts the handle\'s controller — DoD-7', async () => {
    const mock = stubFetch();
    const user = newUser();
    const state = seeded({ draft: "Next line" });
    const handle = freshHandle();
    startStreaming(state, handle);
    renderComposer(state);
    expect(handle.controller.signal.aborted).toBe(false);

    await user.click(screen.getByRole("button", { name: "Stop" }));
    await flush();

    expect(handle.controller.signal.aborted).toBe(true);
    expect(mock).not.toHaveBeenCalled();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  // Amended by fast/011 (DoD-8, DoD-14): Send's place is now inside the text box, so Stop sits
  // there — inside the composer's input wrapper, ahead of "Settle" (which stays under the box).
  it('"Stop" sits where Send sits: inside the composer text box and before "Settle" — DoD-7 (fast/011 DoD-14)', () => {
    stubFetch();
    const state = seeded({ zone: [zoneRow("7250000000000000101", "user", "Mine")] });
    startStreaming(state, freshHandle());
    renderComposer(state);

    const textbox = screen.getByRole("textbox", { name: "Composer" });
    const stop = screen.getByRole("button", { name: "Stop" });
    const settle = screen.getByRole("button", { name: "Settle" });
    const box =
      textbox.closest<HTMLElement>(".mantine-InputWrapper-root, .mantine-Textarea-root") ??
      textbox.closest<HTMLElement>(".mantine-Input-wrapper, .mantine-Textarea-wrapper");
    expect(box).not.toBeNull();
    expect(box?.contains(stop)).toBe(true);
    expect(box?.contains(settle)).toBe(false);
    expect(precedes(stop, settle)).toBe(true);
  });

  it('when streaming starts after render, "Send" is replaced by "Stop" — DoD-7', () => {
    stubFetch();
    const state = seeded({ draft: "Next line" });
    renderComposer(state);
    expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument();

    act(() => {
      startStreaming(state, freshHandle());
    });

    expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send" })).toBeNull();
  });
});

// ---------------------------------------------------------------- DoD-8
describe("Composer while streaming — Settle unaffected (D13, workspace-shell 'The stop control')", () => {
  it('on my turn with one zone row, "Settle" is present and enabled while streaming — DoD-8', () => {
    stubFetch();
    const state = seeded({ zone: [zoneRow("7250000000000000101", "user", "Mine")] });
    startStreaming(state, freshHandle());
    renderComposer(state);

    const settle = screen.getByRole("button", { name: "Settle" });
    expect(settle).toBeInTheDocument();
    expect(settle).toBeEnabled();
    expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------- DoD-9
describe("Composer when not streaming — Send as before (D13)", () => {
  it('a fresh state: "Send" is present and no "Stop" button exists — DoD-9', () => {
    stubFetch();
    const state = seeded({ draft: "Next line" });
    renderComposer(state);

    expect(state.streamingText).toBeNull();
    expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Stop" })).toBeNull();
  });

  it('when the streaming text returns to null, "Send" returns and "Stop" is gone — DoD-9', () => {
    stubFetch();
    const state = seeded({ draft: "Next line" });
    startStreaming(state, freshHandle());
    renderComposer(state);
    expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();

    act(() => {
      runInAction(() => {
        state.streamingText = null;
        state.composeHandle = null;
      });
    });

    expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Stop" })).toBeNull();
  });
});
