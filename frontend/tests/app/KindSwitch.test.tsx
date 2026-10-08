// Feature 013, step 006 — the two-position kind switch (DoD-1, DoD-2).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done plus
// context.md's D8 and the UI strings table:
//   - a SegmentedControl group "Entry kind" with radios "Partner" and "My turn";
//   - its value is the effective position: the alternate of the last partner-or-turn entry
//     (decisions skipped), "My turn" when there is no such entry;
//   - choosing a segment sets the position and makes no request.
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { runInAction } from "mobx";
import { afterEach, describe, expect, it, vi } from "vitest";
import { KindSwitch } from "../../src/app/KindSwitch";
import type { Message, MessageKind } from "../../src/app/streamApi";
import { StreamState, effectiveKind } from "../../src/app/streamState";
import { AppProviders } from "../../src/shared/AppProviders";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "7250000000000000042";
const STAMP = "2026-05-10T09:00:00.000000+00:00";

/** A settled entry with all eight keys. */
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

function seeded(entries: Message[]): StreamState {
  const state = new StreamState(SESSION_ID);
  runInAction(() => {
    state.entries = entries;
    state.status = "ready";
  });
  return state;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- harness
function stubFetchLog(): string[] {
  const log: string[] = [];
  const impl: FetchFn = async (input, init) => {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    log.push(`${(init?.method ?? "GET").toUpperCase()} ${new URL(raw, "http://localhost").pathname}`);
    return new Response(JSON.stringify({ error: { code: "unexpected", message: "x", detail: {} } }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  };
  vi.stubGlobal("fetch", vi.fn(impl));
  return log;
}

function renderSwitch(state: StreamState): void {
  render(
    <AppProviders>
      <KindSwitch state={state} />
    </AppProviders>,
  );
}

function radio(name: "Partner" | "My turn"): HTMLElement {
  return screen.getByRole("radio", { name });
}

async function flush(): Promise<void> {
  await act(async () => {
    for (let round = 0; round < 6; round += 1) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  });
}

// ---------------------------------------------------------------- tests
describe("KindSwitch — shows the effective position (D8)", () => {
  it('renders a group "Entry kind" with radios "Partner" and "My turn" — DoD-1', () => {
    renderSwitch(seeded([]));

    expect(screen.getByRole("radiogroup", { name: "Entry kind" })).toBeInTheDocument();
    expect(radio("Partner")).toBeInTheDocument();
    expect(radio("My turn")).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(2);
  });

  it('with the last partner-or-turn entry a turn, "Partner" is checked — DoD-1', () => {
    renderSwitch(
      seeded([
        entry("7250000000000000101", "partner", "They arrive."),
        entry("7250000000000000102", "turn", "I greet them."),
      ]),
    );

    expect(radio("Partner")).toBeChecked();
    expect(radio("My turn")).not.toBeChecked();
  });

  it('with the last a partner followed by two decisions, "My turn" is checked — DoD-1', () => {
    renderSwitch(
      seeded([
        entry("7250000000000000101", "turn", "I wait."),
        entry("7250000000000000102", "partner", "They arrive."),
        entry("7250000000000000103", "decision", "((keep it slow))"),
        entry("7250000000000000104", "decision", "((no violence))"),
      ]),
    );

    expect(radio("My turn")).toBeChecked();
    expect(radio("Partner")).not.toBeChecked();
  });

  it('with no entries, "My turn" is checked — DoD-1', () => {
    renderSwitch(seeded([]));

    expect(radio("My turn")).toBeChecked();
    expect(radio("Partner")).not.toBeChecked();
  });
});

describe("KindSwitch — choosing a position (D8)", () => {
  it('choosing "Partner" sets the effective position to "partner" and makes no request — DoD-2', async () => {
    const log = stubFetchLog();
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const state = seeded([]);
    renderSwitch(state);

    expect(effectiveKind(state)).toBe("turn");

    await user.click(radio("Partner"));
    await flush();

    expect(effectiveKind(state)).toBe("partner");
    expect(radio("Partner")).toBeChecked();
    expect(radio("My turn")).not.toBeChecked();
    expect(log).toEqual([]);
  });
});
