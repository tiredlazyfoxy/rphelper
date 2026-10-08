// Fast feature 011 — composer-send-icon-and-shortcut: Ctrl/Cmd+Enter sends from the composer
// (docs/plans/fast/011.composer-send-icon-and-shortcut/plan.md, DoD-1..DoD-5).
//
// Expected behaviour comes from the plan's Interface intent ("Keyboard send") and DoD:
//   - Ctrl+Enter or Cmd+Enter (metaKey) in the "Composer" text box calls onSend exactly once iff
//     Send would be enabled and visible: sendEnabled, no blocked reason, no sendSlot;
//   - when it sends, or when it is the combo but sending is not allowed, the default is prevented
//     (no newline inserted);
//   - ignored entirely during an IME composition (isComposing);
//   - plain Enter and Shift+Enter keep inserting a newline (default not prevented), never send.
// `fireEvent.keyDown(...)` returns false iff a handler prevented the default.
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ComposerCore, type ComposerCoreProps } from "../../src/app/ComposerCore";
import { AppProviders } from "../../src/shared/AppProviders";

const NO_MODEL_REASON = "Cannot send: no model is enabled on this instance.";

afterEach(() => {
  vi.restoreAllMocks();
});

function baseProps(overrides: Partial<ComposerCoreProps> = {}): ComposerCoreProps {
  return {
    draft: "Hello",
    onDraftChange: vi.fn<(text: string) => void>(),
    onSend: vi.fn<() => void>(),
    sendEnabled: true,
    ...overrides,
  };
}

function renderCore(props: ComposerCoreProps): void {
  render(
    <AppProviders>
      <ComposerCore {...props} />
    </AppProviders>,
  );
}

function composer(): HTMLElement {
  return screen.getByRole("textbox", { name: "Composer" });
}

type KeyInit = { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean; isComposing?: boolean };

/** Fires an Enter keydown on the composer; returns false iff the default was prevented. */
function pressEnter(init: KeyInit = {}): boolean {
  return fireEvent.keyDown(composer(), { key: "Enter", code: "Enter", ...init });
}

// ---------------------------------------------------------------- DoD-1, DoD-2
describe("fast/011 — Ctrl/Cmd+Enter sends when Send is enabled", () => {
  it("Ctrl+Enter with Send enabled calls onSend exactly once — fast/011 DoD-1", () => {
    const onSend = vi.fn<() => void>();
    renderCore(baseProps({ onSend }));

    pressEnter({ ctrlKey: true });

    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it("Cmd+Enter (metaKey) with Send enabled calls onSend exactly once — fast/011 DoD-2", () => {
    const onSend = vi.fn<() => void>();
    renderCore(baseProps({ onSend }));

    pressEnter({ metaKey: true });

    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it("two Ctrl+Enter presses call onSend once each — fast/011 DoD-1", () => {
    const onSend = vi.fn<() => void>();
    renderCore(baseProps({ onSend }));

    pressEnter({ ctrlKey: true });
    pressEnter({ ctrlKey: true });

    expect(onSend).toHaveBeenCalledTimes(2);
  });
});

// ---------------------------------------------------------------- DoD-3
describe("fast/011 — Ctrl+Enter does nothing when Send would not be enabled and visible", () => {
  it("sendEnabled false: Ctrl+Enter calls nothing — fast/011 DoD-3", () => {
    const onSend = vi.fn<() => void>();
    renderCore(baseProps({ onSend, sendEnabled: false }));

    pressEnter({ ctrlKey: true });

    expect(onSend).not.toHaveBeenCalled();
  });

  it("a blocked reason set: Ctrl+Enter calls nothing even with sendEnabled true — fast/011 DoD-3", () => {
    const onSend = vi.fn<() => void>();
    renderCore(baseProps({ onSend, sendEnabled: true, sendBlockedReason: NO_MODEL_REASON }));

    pressEnter({ ctrlKey: true });

    expect(onSend).not.toHaveBeenCalled();
  });

  it("sendSlot provided: Ctrl+Enter calls nothing even with sendEnabled true — fast/011 DoD-3", () => {
    const onSend = vi.fn<() => void>();
    const onSlot = vi.fn<() => void>();
    renderCore(
      baseProps({
        onSend,
        sendEnabled: true,
        sendSlot: (
          <button type="button" onClick={onSlot}>
            Slot Stop
          </button>
        ),
      }),
    );

    pressEnter({ ctrlKey: true });

    expect(onSend).not.toHaveBeenCalled();
    expect(onSlot).not.toHaveBeenCalled();
  });

  it("Cmd+Enter is likewise ignored when sendEnabled is false — fast/011 DoD-3", () => {
    const onSend = vi.fn<() => void>();
    renderCore(baseProps({ onSend, sendEnabled: false }));

    pressEnter({ metaKey: true });

    expect(onSend).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------- DoD-4
describe("fast/011 — plain Enter and Shift+Enter never send", () => {
  it("plain Enter does not call onSend and is not default-prevented — fast/011 DoD-4", () => {
    const onSend = vi.fn<() => void>();
    renderCore(baseProps({ onSend }));

    const notPrevented = pressEnter();

    expect(onSend).not.toHaveBeenCalled();
    expect(notPrevented).toBe(true);
  });

  it("Shift+Enter does not call onSend and is not default-prevented — fast/011 DoD-4", () => {
    const onSend = vi.fn<() => void>();
    renderCore(baseProps({ onSend }));

    const notPrevented = pressEnter({ shiftKey: true });

    expect(onSend).not.toHaveBeenCalled();
    expect(notPrevented).toBe(true);
  });

  it("Ctrl with a key other than Enter does not call onSend — fast/011 DoD-4", () => {
    const onSend = vi.fn<() => void>();
    renderCore(baseProps({ onSend }));

    fireEvent.keyDown(composer(), { key: "a", code: "KeyA", ctrlKey: true });

    expect(onSend).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------- DoD-5
describe("fast/011 — default prevention and IME composition", () => {
  it("a Ctrl+Enter keydown that sends has its default prevented — fast/011 DoD-5", () => {
    const onSend = vi.fn<() => void>();
    renderCore(baseProps({ onSend }));

    const notPrevented = pressEnter({ ctrlKey: true });

    expect(onSend).toHaveBeenCalledTimes(1);
    expect(notPrevented).toBe(false);
  });

  it("a Cmd+Enter keydown that sends has its default prevented — fast/011 DoD-5", () => {
    const onSend = vi.fn<() => void>();
    renderCore(baseProps({ onSend }));

    const notPrevented = pressEnter({ metaKey: true });

    expect(onSend).toHaveBeenCalledTimes(1);
    expect(notPrevented).toBe(false);
  });

  it("the combo when sending is not allowed still has its default prevented (no newline) — fast/011 DoD-5", () => {
    const onSend = vi.fn<() => void>();
    renderCore(baseProps({ onSend, sendEnabled: false }));

    const notPrevented = pressEnter({ ctrlKey: true });

    expect(onSend).not.toHaveBeenCalled();
    expect(notPrevented).toBe(false);
  });

  it("a Ctrl+Enter keydown during IME composition does not call onSend — fast/011 DoD-5", () => {
    const onSend = vi.fn<() => void>();
    renderCore(baseProps({ onSend }));

    pressEnter({ ctrlKey: true, isComposing: true });

    expect(onSend).not.toHaveBeenCalled();
  });

  it("a Cmd+Enter keydown during IME composition does not call onSend — fast/011 DoD-5", () => {
    const onSend = vi.fn<() => void>();
    renderCore(baseProps({ onSend }));

    pressEnter({ metaKey: true, isComposing: true });

    expect(onSend).not.toHaveBeenCalled();
  });
});
