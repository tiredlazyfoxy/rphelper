// Feature 005, step 006 — the one shared confirm modal (DoD-1, DoD-2).
// The Users page's use of it is covered in tests/admin/UsersPage.test.tsx.
//
// Expected behaviour comes from the step's Interface intent and context.md D7: a caller
// supplies every word (title, one-sentence consequence, confirm label); cancel sits left of
// confirm; cancel invokes only the cancel callback and confirm only the confirm callback; the
// component holds no state of its own, so it renders nothing when closed and always renders
// the words it is currently given.
//
// Recognition conventions: the dialog is Mantine Modal's `role="dialog"`; the cancel button is
// the button named /cancel/i; "left of" is document order (jsdom has no layout).
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../../src/shared/AppProviders";
import { ConfirmModal, type ConfirmModalProps } from "../../src/shared/ConfirmModal";

const CANCEL_NAME = /cancel/i;

const WORDS_A = {
  title: "Extinguish the lantern zq-ka",
  consequence: "The lantern goes dark and stays dark until someone relights it zq-ka.",
  confirmLabel: "Extinguish zq-ka",
} as const;

const WORDS_B = {
  title: "Flood the courtyard zq-kb",
  consequence: "The courtyard fills with water and nobody can cross it zq-kb.",
  confirmLabel: "Flood zq-kb",
} as const;

type Words = { title: string; consequence: string; confirmLabel: string };

afterEach(() => {
  vi.restoreAllMocks();
});

function makeProps(words: Words, opened: boolean): ConfirmModalProps {
  return {
    opened,
    title: words.title,
    consequence: words.consequence,
    confirmLabel: words.confirmLabel,
    onCancel: vi.fn<() => void>(),
    onConfirm: vi.fn<() => void>(),
  };
}

function renderModal(props: ConfirmModalProps) {
  const view = render(
    <AppProviders>
      <ConfirmModal {...props} />
    </AppProviders>,
  );
  const rerender = (next: ConfirmModalProps) => {
    act(() => {
      view.rerender(
        <AppProviders>
          <ConfirmModal {...next} />
        </AppProviders>,
      );
    });
  };
  return { ...view, rerender };
}

function bodyText(): string {
  return document.body.textContent ?? "";
}

function expectWordsShown(dialog: HTMLElement, words: Words): void {
  expect(within(dialog).getByText(words.title)).toBeInTheDocument();
  expect(within(dialog).getByText(words.consequence)).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: words.confirmLabel })).toBeInTheDocument();
}

function expectWordsAbsent(words: Words): void {
  const text = bodyText();
  expect(text).not.toContain(words.title);
  expect(text).not.toContain(words.consequence);
  expect(text).not.toContain(words.confirmLabel);
}

// ---------------------------------------------------------------------------
describe("an open confirm modal", () => {
  it("renders its title, its consequence sentence and its confirm label — DoD-1", async () => {
    renderModal(makeProps(WORDS_A, true));
    const dialog = await screen.findByRole("dialog");
    expectWordsShown(dialog, WORDS_A);
  });

  it("renders a cancel button beside the confirm button — DoD-1", async () => {
    renderModal(makeProps(WORDS_A, true));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: CANCEL_NAME })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: WORDS_A.confirmLabel })).toBeInTheDocument();
  });

  it("places cancel left of (before) confirm — DoD-1", async () => {
    renderModal(makeProps(WORDS_A, true));
    const dialog = await screen.findByRole("dialog");
    const cancel = within(dialog).getByRole("button", { name: CANCEL_NAME });
    const confirm = within(dialog).getByRole("button", { name: WORDS_A.confirmLabel });
    expect(cancel).not.toBe(confirm);
    expect(cancel.compareDocumentPosition(confirm) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("cancel invokes only the cancel callback — DoD-1", async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const props = makeProps(WORDS_A, true);
    renderModal(props);
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: CANCEL_NAME }));
    expect(props.onCancel).toHaveBeenCalledTimes(1);
    expect(props.onConfirm).not.toHaveBeenCalled();
  });

  it("confirm invokes only the confirm callback — DoD-1", async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const props = makeProps(WORDS_A, true);
    renderModal(props);
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: WORDS_A.confirmLabel }));
    expect(props.onConfirm).toHaveBeenCalledTimes(1);
    expect(props.onCancel).not.toHaveBeenCalled();
  });

  it("a different caller's words are rendered as given — DoD-1", async () => {
    renderModal(makeProps(WORDS_B, true));
    const dialog = await screen.findByRole("dialog");
    expectWordsShown(dialog, WORDS_B);
    expectWordsAbsent(WORDS_A);
  });
});

// ---------------------------------------------------------------------------
describe("the confirm modal is closed and stateless", () => {
  it("renders nothing when closed — DoD-2", () => {
    const props = makeProps(WORDS_A, false);
    renderModal(props);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryAllByRole("button")).toEqual([]);
    expectWordsAbsent(WORDS_A);
    expect(props.onCancel).not.toHaveBeenCalled();
    expect(props.onConfirm).not.toHaveBeenCalled();
  });

  it("opening a closed modal renders its words — DoD-2", async () => {
    const view = renderModal(makeProps(WORDS_A, false));
    expect(screen.queryByRole("dialog")).toBeNull();
    view.rerender(makeProps(WORDS_A, true));
    const dialog = await screen.findByRole("dialog");
    expectWordsShown(dialog, WORDS_A);
  });

  it("closing an open modal removes it — DoD-2", async () => {
    const view = renderModal(makeProps(WORDS_A, true));
    await screen.findByRole("dialog");
    view.rerender(makeProps(WORDS_A, false));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expectWordsAbsent(WORDS_A);
  });

  it("reopening it with different words renders the new words, not the old — DoD-2", async () => {
    const view = renderModal(makeProps(WORDS_A, true));
    expectWordsShown(await screen.findByRole("dialog"), WORDS_A);

    view.rerender(makeProps(WORDS_A, false));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });

    view.rerender(makeProps(WORDS_B, true));
    const dialog = await screen.findByRole("dialog");
    expectWordsShown(dialog, WORDS_B);
    expectWordsAbsent(WORDS_A);
  });

  it("changing the words while open renders the new words at once — DoD-2", async () => {
    const view = renderModal(makeProps(WORDS_A, true));
    await screen.findByRole("dialog");
    view.rerender(makeProps(WORDS_B, true));
    const dialog = screen.getByRole("dialog");
    expectWordsShown(dialog, WORDS_B);
    expectWordsAbsent(WORDS_A);
  });

  it("the callbacks invoked are the ones currently given, not earlier ones — DoD-2", async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const first = makeProps(WORDS_A, true);
    const view = renderModal(first);
    await screen.findByRole("dialog");
    const second = makeProps(WORDS_B, true);
    view.rerender(second);

    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: WORDS_B.confirmLabel }));
    await user.click(within(dialog).getByRole("button", { name: CANCEL_NAME }));

    expect(second.onConfirm).toHaveBeenCalledTimes(1);
    expect(second.onCancel).toHaveBeenCalledTimes(1);
    expect(first.onConfirm).not.toHaveBeenCalled();
    expect(first.onCancel).not.toHaveBeenCalled();
  });

  it("clicking cancel or confirm does not close it by itself — the caller's opened prop decides — DoD-2", async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const props = makeProps(WORDS_A, true);
    renderModal(props);
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: WORDS_A.confirmLabel }));
    await user.click(within(dialog).getByRole("button", { name: CANCEL_NAME }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expectWordsShown(screen.getByRole("dialog"), WORDS_A);
  });
});
