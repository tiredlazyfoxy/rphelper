// Feature 018, step 003 — the shared composer core (DoD-1..DoD-4, DoD-6; DoD-5 is covered in
// Composer.test.tsx / ComposerPasteWarning.test.tsx; DoD-7 is manual/live).
//
// Expected behaviour comes from the step's Interface intent and Definition of done plus
// context.md D4 and 014's paste rule (128,001 non-blank characters warn; whitespace-only and
// short pastes do not):
//   - a textbox "Composer" showing the draft; typing reports the new text; a labelled "Send"
//     enabled iff Send is enabled and no send-blocked reason is given;
//   - a non-null send-blocked reason is shown as text and disables Send;
//   - a paste warns first (synchronously), then runs the host hook; the core never prevents the
//     default;
//   - the under-area slot renders after the text area, the beside-Send slot after "Send"; the
//     core carries no Settle, no kind switch and no Discard of its own;
//   - source guard: Composer.tsx renders ComposerCore with no Textarea of its own, and
//     ComposerCore.tsx is the only src/app module importing notifyWarning.
// `fireEvent.paste(...)` returns false iff a handler prevented the default.
//
// Amended by feature 019, step 004 (user-approved deviation, 019 status.md "## Ultra phase"):
// `ComposerCoreProps` gained an optional `sendSlot`. Every 018 case above renders without it and
// is unchanged. The slot cases are in the block after DoD-4, under a describe naming 019 step 004,
// so their "— DoD-N" tags are 019 step 004's: a given slot renders in Send's place with "Send"
// absent and the send-blocked reason still shown; an omitted slot keeps the labelled Send.
//
// Amended by fast feature 011 (composer-send-icon-and-shortcut). Send is now an icon-only
// button (accessible name exactly "Send", no visible text) inside the text box's Mantine input
// wrapper; `sendSlot` takes that in-box position; the row under the box holds the blocked reason
// and `besideSend` only. So `buttonNames()` now reads accessible names, and the two order cases
// (018 DoD-4, 019 DoD-7) assert "inside the box" instead of "after the under-area" — tagged
// "fast/011 DoD-14". New fast/011 cases (DoD-6..DoD-12) are in the block at the end; the
// Ctrl/Cmd+Enter cases (DoD-1..DoD-5) live in ComposerCore.keyboard.test.tsx. jsdom has no
// layout, so layout is asserted on attributes and inline styles / CSS variables only.
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { useState, type ClipboardEvent, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ComposerCore, type ComposerCoreProps } from "../../src/app/ComposerCore";
import { AppProviders } from "../../src/shared/AppProviders";

const notifyWarningSpy = vi.hoisted(() => vi.fn<(id: "paste-context-cost") => void>());
vi.mock("../../src/shared/notifyWarning", () => ({ notifyWarning: notifyWarningSpy }));

// ---------------------------------------------------------------- fixtures
const PASTE_ID = "paste-context-cost";
const NO_MODEL_REASON = "Cannot send: no model is enabled on this instance.";

const OVER_THRESHOLD = "a".repeat(128_001);
const WHITESPACE_OVER_THRESHOLD = " ".repeat(128_001);
const SHORT_PASTE = "Some pasted words";

type PasteHook = (text: string, event: ClipboardEvent<HTMLTextAreaElement>) => void;

beforeEach(() => {
  notifyWarningSpy.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- harness
function baseProps(overrides: Partial<ComposerCoreProps> = {}): ComposerCoreProps {
  return {
    draft: "",
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

/** A host that keeps the draft in React state, so typing is realistic. */
function StatefulHost(props: { onDraftChange: (text: string) => void }): ReactNode {
  const [draft, setDraft] = useState("");
  return (
    <ComposerCore
      draft={draft}
      onDraftChange={(text) => {
        props.onDraftChange(text);
        setDraft(text);
      }}
      onSend={() => undefined}
      sendEnabled={true}
    />
  );
}

function composer(): HTMLElement {
  return screen.getByRole("textbox", { name: "Composer" });
}

function sendButton(): HTMLElement {
  return screen.getByRole("button", { name: "Send" });
}

/** Returns false iff a handler prevented the default. */
function paste(text: string): boolean {
  return fireEvent.paste(composer(), { clipboardData: { getData: () => text } });
}

function newUser(): ReturnType<typeof userEvent.setup> {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

function precedes(first: Node, second: Node): boolean {
  return (first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

/** Each button's accessible name: its aria-label when it has one, else its text (fast/011). */
function buttonNames(): string[] {
  return screen
    .getAllByRole("button")
    .map((button) => button.getAttribute("aria-label") ?? button.textContent?.trim() ?? "");
}

/**
 * fast/011: the Mantine input root/wrapper that contains the "Composer" textarea — the "text
 * box" Send now sits inside. The outermost of Mantine's input root / input wrapper.
 */
function inputBox(textarea: HTMLElement): HTMLElement {
  const box =
    textarea.closest<HTMLElement>(".mantine-InputWrapper-root, .mantine-Textarea-root") ??
    textarea.closest<HTMLElement>(".mantine-Input-wrapper, .mantine-Textarea-wrapper");
  if (box === null) throw new Error("the Composer textarea has no Mantine input wrapper");
  return box;
}

/** fast/011: every ancestor of `node` strictly inside document.body. */
function ancestors(node: HTMLElement): HTMLElement[] {
  const found: HTMLElement[] = [];
  for (let el = node.parentElement; el !== null && el !== document.body; el = el.parentElement) {
    found.push(el);
  }
  return found;
}

const CAP_720 = /(^|[^\d.])(720px|45rem)/;

/** fast/011: whether the element carries a 720px max-width (inline style, as Mantine emits `maw`). */
function carries720MaxWidth(el: HTMLElement): boolean {
  const raw = el.getAttribute("style") ?? "";
  const declared = [...raw.matchAll(/(?:^|;)\s*max-width\s*:\s*([^;]+)/g)].map((match) => match[1] ?? "");
  const candidates = [...declared, el.style.maxWidth, el.style.getPropertyValue("--maw")];
  return candidates.some((value) => CAP_720.test(value));
}

/** fast/011: every resize value set inline on the textarea or its ancestors. */
function resizeValues(textarea: HTMLElement): string[] {
  const values: string[] = [];
  for (const el of [textarea, ...ancestors(textarea)]) {
    const raw = el.getAttribute("style") ?? "";
    for (const match of raw.matchAll(/(?:^|;)\s*(?:--input-resize|resize)\s*:\s*([a-z-]+)/g)) {
      if (match[1] !== undefined) values.push(match[1]);
    }
    const variable = el.style.getPropertyValue("--input-resize").trim();
    if (variable !== "") values.push(variable);
    if (el.style.resize !== "") values.push(el.style.resize);
  }
  return values;
}

// ---------------------------------------------------------------- DoD-1
describe("ComposerCore — draft and Send (D4, ui-conventions labelled Send)", () => {
  it('with draft "Hello" it renders a textbox "Composer" holding "Hello" and an enabled "Send" — DoD-1', () => {
    renderCore(baseProps({ draft: "Hello" }));

    expect(composer()).toHaveValue("Hello");
    expect(sendButton()).toBeEnabled();
  });

  it("changing the text calls the draft-change callback with the new text — DoD-1", () => {
    const onDraftChange = vi.fn<(text: string) => void>();
    renderCore(baseProps({ draft: "Hello", onDraftChange }));

    fireEvent.change(composer(), { target: { value: "Hello there" } });

    expect(onDraftChange).toHaveBeenCalledWith("Hello there");
    expect(onDraftChange).toHaveBeenLastCalledWith("Hello there");
  });

  it('typing "Hello" into a stateful host reports each new text, ending with "Hello" — DoD-1', async () => {
    const onDraftChange = vi.fn<(text: string) => void>();
    const user = newUser();
    render(
      <AppProviders>
        <StatefulHost onDraftChange={onDraftChange} />
      </AppProviders>,
    );

    await user.type(composer(), "Hello");

    expect(onDraftChange).toHaveBeenLastCalledWith("Hello");
    expect(composer()).toHaveValue("Hello");
  });

  it('pressing "Send" calls the send callback once — DoD-1', async () => {
    const onSend = vi.fn<() => void>();
    const user = newUser();
    renderCore(baseProps({ draft: "Hello", onSend }));

    await user.click(sendButton());

    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it('with Send not enabled, "Send" is disabled and pressing it calls nothing — DoD-1', async () => {
    const onSend = vi.fn<() => void>();
    const user = newUser();
    renderCore(baseProps({ draft: "Hello", onSend, sendEnabled: false }));

    expect(sendButton()).toBeDisabled();
    await user.click(sendButton());

    expect(onSend).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------- DoD-2
describe("ComposerCore — send-blocked reason (D4, 017 D17)", () => {
  it("with a reason it shows the sentence and disables Send even when Send is enabled — DoD-2", async () => {
    const onSend = vi.fn<() => void>();
    const user = newUser();
    renderCore(baseProps({ draft: "Hello", onSend, sendEnabled: true, sendBlockedReason: NO_MODEL_REASON }));

    expect(screen.getByText(NO_MODEL_REASON)).toBeInTheDocument();
    expect(sendButton()).toBeDisabled();

    await user.click(sendButton());
    expect(onSend).not.toHaveBeenCalled();
  });

  it("with the reason null, no reason text is shown and Send follows sendEnabled — DoD-2", () => {
    renderCore(baseProps({ draft: "Hello", sendEnabled: true, sendBlockedReason: null }));

    expect(screen.queryByText(NO_MODEL_REASON)).toBeNull();
    expect(screen.queryByText(/^Cannot send:/)).toBeNull();
    expect(sendButton()).toBeEnabled();
  });

  it("with the reason omitted, no reason text is shown and Send follows sendEnabled — DoD-2", () => {
    renderCore(baseProps({ draft: "Hello", sendEnabled: true }));

    expect(screen.queryByText(NO_MODEL_REASON)).toBeNull();
    expect(screen.queryByText(/^Cannot send:/)).toBeNull();
    expect(sendButton()).toBeEnabled();
  });
});

// ---------------------------------------------------------------- DoD-3
describe("ComposerCore — paste (US-035.AC-1, US-035.AC-2, D4)", () => {
  it("pasting 128,001 non-blank characters warns once with the paste identifier before the hook runs, then calls the hook with that text — DoD-3", () => {
    const order: string[] = [];
    notifyWarningSpy.mockImplementation(() => {
      order.push("warning");
    });
    const onPaste = vi.fn<PasteHook>(() => {
      order.push("hook");
    });
    renderCore(baseProps({ onPaste }));

    paste(OVER_THRESHOLD);

    expect(notifyWarningSpy).toHaveBeenCalledTimes(1);
    expect(notifyWarningSpy).toHaveBeenCalledWith(PASTE_ID);
    expect(onPaste).toHaveBeenCalledTimes(1);
    expect(onPaste.mock.calls[0]?.[0]).toBe(OVER_THRESHOLD);
    expect(order).toEqual(["warning", "hook"]);
  });

  it("an enormous paste with a hook that does not prevent is not default-prevented by the core — DoD-3", () => {
    const onPaste = vi.fn<PasteHook>();
    renderCore(baseProps({ onPaste }));

    const notPrevented = paste(OVER_THRESHOLD);

    expect(notPrevented).toBe(true);
  });

  it("a hook may prevent the default itself, after the warning — DoD-3", () => {
    const onPaste = vi.fn<PasteHook>((_text, event) => {
      event.preventDefault();
    });
    renderCore(baseProps({ onPaste }));

    const notPrevented = paste(OVER_THRESHOLD);

    expect(notifyWarningSpy).toHaveBeenCalledTimes(1);
    expect(onPaste).toHaveBeenCalledTimes(1);
    expect(notPrevented).toBe(false);
  });

  it("a short paste calls no notifyWarning, still calls the hook with the text and is not prevented — DoD-3", () => {
    const onPaste = vi.fn<PasteHook>();
    renderCore(baseProps({ onPaste }));

    const notPrevented = paste(SHORT_PASTE);

    expect(notifyWarningSpy).not.toHaveBeenCalled();
    expect(onPaste).toHaveBeenCalledTimes(1);
    expect(onPaste.mock.calls[0]?.[0]).toBe(SHORT_PASTE);
    expect(notPrevented).toBe(true);
  });

  it("a 128,001-character whitespace-only paste calls no notifyWarning and still calls the hook — DoD-3", () => {
    const onPaste = vi.fn<PasteHook>();
    renderCore(baseProps({ onPaste }));

    const notPrevented = paste(WHITESPACE_OVER_THRESHOLD);

    expect(notifyWarningSpy).not.toHaveBeenCalled();
    expect(onPaste).toHaveBeenCalledTimes(1);
    expect(onPaste.mock.calls[0]?.[0]).toBe(WHITESPACE_OVER_THRESHOLD);
    expect(notPrevented).toBe(true);
  });

  it("with no hook given, an enormous paste warns, neither throws nor is prevented — DoD-3", () => {
    const errors: unknown[] = [];
    const onError = (event: ErrorEvent): void => {
      errors.push(event.error);
    };
    window.addEventListener("error", onError);
    try {
      renderCore(baseProps());

      let notPrevented = false;
      expect(() => {
        notPrevented = paste(OVER_THRESHOLD);
      }).not.toThrow();

      expect(notPrevented).toBe(true);
      expect(notifyWarningSpy).toHaveBeenCalledTimes(1);
      expect(errors).toEqual([]);
    } finally {
      window.removeEventListener("error", onError);
    }
  });

  it("with no hook given, a short paste neither throws nor is prevented — DoD-3", () => {
    const errors: unknown[] = [];
    const onError = (event: ErrorEvent): void => {
      errors.push(event.error);
    };
    window.addEventListener("error", onError);
    try {
      renderCore(baseProps());

      let notPrevented = false;
      expect(() => {
        notPrevented = paste(SHORT_PASTE);
      }).not.toThrow();

      expect(notPrevented).toBe(true);
      expect(notifyWarningSpy).not.toHaveBeenCalled();
      expect(errors).toEqual([]);
    } finally {
      window.removeEventListener("error", onError);
    }
  });
});

// ---------------------------------------------------------------- DoD-4
describe("ComposerCore — slots, and nothing of the stream's own (D4, US-117.AC-4)", () => {
  // Amended by fast/011 (DoD-9, DoD-14): Send moved inside the text box, so it no longer sits
  // after the under-area slot; the beside-Send slot still follows Send and the under-area.
  it("renders the under-area slot after the text area, Send inside the text box, and the beside-Send slot after Send and the under-area, in document order — DoD-4 (fast/011 DoD-14)", () => {
    renderCore(
      baseProps({
        draft: "Hello",
        underArea: <p>Under the text area</p>,
        besideSend: <button type="button">Beside Send</button>,
      }),
    );

    const textbox = composer();
    const under = screen.getByText("Under the text area");
    const send = sendButton();
    const beside = screen.getByRole("button", { name: "Beside Send" });

    expect(precedes(textbox, under)).toBe(true);
    expect(inputBox(textbox).contains(send)).toBe(true);
    expect(precedes(under, beside)).toBe(true);
    expect(precedes(send, beside)).toBe(true);
    expect(buttonNames()).toEqual(["Send", "Beside Send"]);
  });

  it("with both slots omitted it renders nothing in their place: Send is the only button — DoD-4", () => {
    renderCore(baseProps({ draft: "Hello" }));

    expect(screen.queryByText("Under the text area")).toBeNull();
    expect(screen.queryByRole("button", { name: "Beside Send" })).toBeNull();
    expect(buttonNames()).toEqual(["Send"]);
  });

  it('renders no "Settle", no "Entry kind" switch and no "Discard empty zone" of its own — DoD-4', () => {
    renderCore(baseProps({ draft: "" }));

    expect(screen.queryByRole("button", { name: "Settle" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Discard empty zone" })).toBeNull();
    expect(screen.queryByRole("radiogroup", { name: "Entry kind" })).toBeNull();
    expect(screen.queryByText("Entry kind")).toBeNull();
    expect(screen.queryByRole("radio", { name: "My turn" })).toBeNull();
    expect(screen.queryByRole("radio", { name: "Partner" })).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Feature 019, step 004 — `sendSlot` replaces Send (Stop in Send's slot). Every "— DoD-N" here is
// 019 step 004's: DoD-7 (slot present, Send absent) and DoD-9 (no slot, Send as before).
describe("019 step 004 — ComposerCore's sendSlot (workspace-shell 'The stop control')", () => {
  it('a given sendSlot renders in place of "Send": the slot is present and no "Send" button exists — DoD-7', () => {
    renderCore(baseProps({ draft: "Hello", sendSlot: <button type="button">Slot Stop</button> }));

    expect(screen.getByRole("button", { name: "Slot Stop" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send" })).toBeNull();
    expect(buttonNames()).toEqual(["Slot Stop"]);
  });

  // Amended by fast/011 (DoD-8, DoD-14): Send's place is now inside the text box, so the slot
  // sits there too — inside the box, ahead of the under-area slot and the beside-Send slot.
  it("the slot sits where Send sits: inside the text box, with the under-area after the text area and the beside-Send slot after both — DoD-7 (fast/011 DoD-14)", () => {
    renderCore(
      baseProps({
        draft: "Hello",
        underArea: <p>Under the text area</p>,
        besideSend: <button type="button">Beside Send</button>,
        sendSlot: <button type="button">Slot Stop</button>,
      }),
    );

    const textbox = composer();
    const under = screen.getByText("Under the text area");
    const slot = screen.getByRole("button", { name: "Slot Stop" });
    const beside = screen.getByRole("button", { name: "Beside Send" });

    expect(precedes(textbox, under)).toBe(true);
    expect(inputBox(textbox).contains(slot)).toBe(true);
    expect(precedes(under, beside)).toBe(true);
    expect(precedes(slot, beside)).toBe(true);
    expect(buttonNames()).toEqual(["Slot Stop", "Beside Send"]);
  });

  it("with a sendSlot, Send stays absent whatever sendEnabled says, and pressing the slot does not call onSend — DoD-7", async () => {
    const onSend = vi.fn<() => void>();
    const onSlot = vi.fn<() => void>();
    const user = newUser();
    renderCore(
      baseProps({
        draft: "Hello",
        onSend,
        sendEnabled: false,
        sendSlot: (
          <button type="button" onClick={onSlot}>
            Slot Stop
          </button>
        ),
      }),
    );

    expect(screen.queryByRole("button", { name: "Send" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Slot Stop" }));

    expect(onSlot).toHaveBeenCalledTimes(1);
    expect(onSend).not.toHaveBeenCalled();
  });

  it("with a sendSlot and a send-blocked reason, the reason text is still shown and Send is still absent — DoD-7", () => {
    renderCore(
      baseProps({
        draft: "Hello",
        sendBlockedReason: NO_MODEL_REASON,
        sendSlot: <button type="button">Slot Stop</button>,
      }),
    );

    expect(screen.getByText(NO_MODEL_REASON)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Slot Stop" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send" })).toBeNull();
  });

  it('with sendSlot omitted, the labelled "Send" renders as in 018 and follows sendEnabled — DoD-9', async () => {
    const onSend = vi.fn<() => void>();
    const user = newUser();
    renderCore(baseProps({ draft: "Hello", onSend, sendEnabled: true }));

    expect(sendButton()).toBeEnabled();
    expect(buttonNames()).toEqual(["Send"]);
    await user.click(sendButton());
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it('with sendSlot explicitly undefined, "Send" renders as in 018: disabled when Send is not enabled — DoD-9', () => {
    renderCore(baseProps({ draft: "Hello", sendEnabled: false, sendSlot: undefined }));

    expect(sendButton()).toBeDisabled();
    expect(buttonNames()).toEqual(["Send"]);
  });
});

// ---------------------------------------------------------------------------
// Fast feature 011 — Send as an in-box icon, the row under the box, resize and layout props.
// Every "fast/011 DoD-N" here is fast feature 011's.
describe("fast/011 — Send inside the text box (Interface intent: Send control)", () => {
  it('Send is a button named exactly "Send" with no visible "Send" text, an icon, inside the text box\'s input wrapper — fast/011 DoD-6', () => {
    renderCore(baseProps({ draft: "Hello", underArea: <p>Under the text area</p> }));

    const textbox = composer();
    const send = sendButton();

    expect(send.textContent ?? "").not.toMatch(/Send/);
    expect(send.querySelector("svg")).not.toBeNull();
    expect(screen.queryByText("Send")).toBeNull();
    expect(inputBox(textbox).contains(send)).toBe(true);
    // Not in the row under the box: it precedes the under-area slot.
    expect(precedes(send, screen.getByText("Under the text area"))).toBe(true);
  });

  it("Send is enabled when sendEnabled is true and no reason is set; clicking it calls onSend once — fast/011 DoD-7", async () => {
    const onSend = vi.fn<() => void>();
    const user = newUser();
    renderCore(baseProps({ draft: "Hello", onSend, sendEnabled: true, sendBlockedReason: null }));

    expect(sendButton()).toBeEnabled();
    await user.click(sendButton());

    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it("Send is disabled when sendEnabled is false — fast/011 DoD-7", () => {
    renderCore(baseProps({ draft: "Hello", sendEnabled: false }));

    expect(sendButton()).toBeDisabled();
  });

  it("Send is disabled when a blocked reason is set, even with sendEnabled true — fast/011 DoD-7", () => {
    renderCore(baseProps({ draft: "Hello", sendEnabled: true, sendBlockedReason: NO_MODEL_REASON }));

    expect(sendButton()).toBeDisabled();
  });

  it('with sendSlot provided, no "Send" button exists and the slot renders inside the text box\'s input wrapper — fast/011 DoD-8', () => {
    renderCore(baseProps({ draft: "Hello", sendSlot: <button type="button">Slot Stop</button> }));

    expect(screen.queryByRole("button", { name: "Send" })).toBeNull();
    const slot = screen.getByRole("button", { name: "Slot Stop" });
    expect(inputBox(composer()).contains(slot)).toBe(true);
  });
});

describe("fast/011 — the row under the box (Interface intent: Row under the box)", () => {
  it("besideSend and the blocked reason render outside the input wrapper, after the textarea and after underArea; underArea follows the textarea — fast/011 DoD-9", () => {
    renderCore(
      baseProps({
        draft: "Hello",
        sendBlockedReason: NO_MODEL_REASON,
        underArea: <p>Under the text area</p>,
        besideSend: <button type="button">Settle</button>,
      }),
    );

    const textbox = composer();
    const box = inputBox(textbox);
    const under = screen.getByText("Under the text area");
    const reason = screen.getByText(NO_MODEL_REASON);
    const settle = screen.getByRole("button", { name: "Settle" });

    expect(box.contains(under)).toBe(false);
    expect(box.contains(reason)).toBe(false);
    expect(box.contains(settle)).toBe(false);

    expect(precedes(textbox, under)).toBe(true);
    expect(precedes(textbox, reason)).toBe(true);
    expect(precedes(textbox, settle)).toBe(true);
    expect(precedes(under, reason)).toBe(true);
    expect(precedes(under, settle)).toBe(true);
  });

  it("with sendSlot given, besideSend still renders outside the input wrapper after underArea — fast/011 DoD-9", () => {
    renderCore(
      baseProps({
        draft: "Hello",
        underArea: <p>Under the text area</p>,
        besideSend: <button type="button">Settle</button>,
        sendSlot: <button type="button">Slot Stop</button>,
      }),
    );

    const textbox = composer();
    const settle = screen.getByRole("button", { name: "Settle" });
    const under = screen.getByText("Under the text area");

    expect(inputBox(textbox).contains(settle)).toBe(false);
    expect(precedes(textbox, under)).toBe(true);
    expect(precedes(under, settle)).toBe(true);
  });
});

describe("fast/011 — resize and layout props (Interface intent: Text box, full-width flag, minimum rows)", () => {
  it("the Composer textarea is resizable vertically only — fast/011 DoD-10", () => {
    renderCore(baseProps({ draft: "Hello" }));

    const values = resizeValues(composer());

    expect(values).toContain("vertical");
    expect(values).not.toContain("both");
    expect(values).not.toContain("horizontal");
  });

  it("with fullWidth and minRows set, the textarea is still resizable vertically only — fast/011 DoD-10", () => {
    renderCore(baseProps({ draft: "Hello", fullWidth: true, minRows: 10 }));

    const values = resizeValues(composer());

    expect(values).toContain("vertical");
    expect(values).not.toContain("both");
    expect(values).not.toContain("horizontal");
  });

  it("with defaults, the textarea has rows 2 and the composer's outer wrapper carries a 720px max-width — fast/011 DoD-11", () => {
    renderCore(baseProps({ draft: "Hello" }));

    const textbox = composer();

    expect(textbox).toHaveAttribute("rows", "2");
    expect(ancestors(textbox).some(carries720MaxWidth)).toBe(true);
  });

  it.each([1, 5, 10])("with minRows %i, the textarea's rows is that number — fast/011 DoD-11", (rows) => {
    renderCore(baseProps({ draft: "Hello", minRows: rows }));

    expect(composer()).toHaveAttribute("rows", String(rows));
  });

  it("with fullWidth on, no ancestor of the textarea carries a 720px max-width — fast/011 DoD-12", () => {
    renderCore(baseProps({ draft: "Hello", fullWidth: true }));

    expect(ancestors(composer()).filter(carries720MaxWidth)).toEqual([]);
  });

  it("with fullWidth explicitly false, the 720px max-width is kept — fast/011 DoD-11", () => {
    renderCore(baseProps({ draft: "Hello", fullWidth: false }));

    expect(ancestors(composer()).some(carries720MaxWidth)).toBe(true);
  });
});

// ---------------------------------------------------------------- DoD-6
const FRONTEND_ROOT = path.resolve(__dirname, "..", "..");
const APP_SRC = path.join(FRONTEND_ROOT, "src", "app");

function allFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    return entry.isDirectory() ? allFiles(full) : [full];
  });
}

function relative(file: string): string {
  return path.relative(FRONTEND_ROOT, file).split(path.sep).join("/");
}

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

function readSource(file: string): string {
  return stripComments(readFileSync(file, "utf8"));
}

/** Every module specifier a source file imports or re-exports from. */
function importSpecifiers(source: string): string[] {
  const specifiers: string[] = [];
  for (const match of source.matchAll(/\bfrom\s*["']([^"']+)["']/g)) {
    if (match[1] !== undefined) specifiers.push(match[1]);
  }
  for (const match of source.matchAll(/\bimport\s*["']([^"']+)["']/g)) {
    if (match[1] !== undefined) specifiers.push(match[1]);
  }
  for (const match of source.matchAll(/\bimport\s*\(\s*["']([^"']+)["']\s*\)/g)) {
    if (match[1] !== undefined) specifiers.push(match[1]);
  }
  return specifiers;
}

function importsNotifyWarning(source: string): boolean {
  return importSpecifiers(source).some((specifier) => /(^|\/)notifyWarning$/.test(specifier));
}

describe("ComposerCore — one composer, one paste-warning site (D4)", () => {
  it("Composer.tsx renders ComposerCore and contains no Textarea of its own — DoD-6", () => {
    const source = readSource(path.join(APP_SRC, "Composer.tsx"));

    expect(importSpecifiers(source)).toContain("./ComposerCore");
    expect(source).toMatch(/<ComposerCore\b/);
    expect(source).not.toMatch(/\bTextarea\b/);
    expect(source).not.toMatch(/<textarea\b/);
  });

  // Feature 031 step 006 (orchestrator decision 5): `src/app/importUploads.ts` raises the import
  // search-coverage warning, so it joins ComposerCore as a legitimate warner. The set stays EXACT,
  // so a third `src/app` warner still fails this clause.
  it("ComposerCore.tsx and importUploads.ts are the only src/app modules that import notifyWarning — DoD-6", () => {
    const files = allFiles(APP_SRC).filter((file) => /\.(ts|tsx)$/.test(file));
    expect(files.map(relative)).toEqual(expect.arrayContaining(["src/app/Composer.tsx", "src/app/ComposerCore.tsx"]));

    const importers = files.filter((file) => importsNotifyWarning(readSource(file))).map(relative);

    expect([...importers].sort()).toEqual(["src/app/ComposerCore.tsx", "src/app/importUploads.ts"]);
  });
});
