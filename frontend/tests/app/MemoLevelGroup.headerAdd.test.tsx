// Fast feature 012 — notes-autosave-toolbar-flags: MemoLevelGroup's one behaviour at every
// mount (DoD-3..DoD-12 at the group level; the three mounts are covered again in
// CharacterNotesSection.test.tsx, MemoChainSection.test.tsx and SettingsScreen.test.tsx;
// DoD-1/DoD-2 live in tests/shared/MarkdownEditor.test.tsx; DoD-15..DoD-18 are [manual/live]).
// This file previously held 033 step 002's opt-in `headerAdd` tests; that prop is removed and
// its Save / Cancel draft is superseded (012 context.md "Contracts this supersedes").
//
// Expected behaviour comes from docs/plans/fast/012.notes-autosave-toolbar-flags/plan.md
// (Interface intent, Definition of done) and its context.md:
// - Header: the Title with a '+' icon button named "New note" beside it, ready state only,
//   disabled while a draft is open. No labelled "New note" button anywhere.
// - Draft: first list item, editor autofocused, saved when focus leaves it (trimmed blank →
//   dropped, no request; otherwise one create; failure keeps the text and shows the failure
//   inside the draft). No Save / Cancel, no flags.
// - Saved note: focus leaving it saves (blank → delete with no confirm; changed → body patch;
//   unchanged → nothing). Its two flag buttons are passed to the editor as toolbar actions; the
//   reach line and failure text stay after the editor. A flag click only toggles its flag.
//
// Recognition conventions (for the verifier):
// - The group is the region named by its title; queries go through `within(region())`.
// - `src/shared/MarkdownEditor` is a labelled-`<textarea>` stub (id from `useId`) whose root
//   is `[data-testid="markdown-editor-stub"]`; it renders the `toolbarActions` prop inside
//   that root as `[data-testid="stub-toolbar-actions"]` (as the real editor renders it in its
//   toolbar). It passes `autoFocus` to the textarea (React focuses it on mount).
// - Focus leaving is `fireEvent.blur` (relatedTarget null unless given); typing is
//   `fireEvent.change`.
// - `fetch` is stubbed per test and every request recorded, so "no request" is `calls` empty.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ChangeEvent, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoLevelGroup } from "../../src/app/MemoLevelGroup";
import type { Memo, MemoScope } from "../../src/app/memosApi";
import { loadMemoLevel, MemoLevelState, populateMemoLevel } from "../../src/app/memoLevelState";
import { AppProviders } from "../../src/shared/AppProviders";

vi.mock("../../src/shared/MarkdownEditor", async () => {
  const { createElement, useId } = await import("react");
  type StubProps = {
    label: string;
    value: string;
    onChange: (markdown: string) => void;
    readOnly?: boolean;
    autoFocus?: boolean;
    toolbarActions?: ReactNode;
  };
  return {
    MarkdownEditor: (props: StubProps) => {
      const id = `markdown-editor-${useId()}`;
      return createElement(
        "div",
        { "data-testid": "markdown-editor-stub" },
        createElement("label", { htmlFor: id }, props.label),
        createElement("textarea", {
          id,
          value: props.value,
          readOnly: props.readOnly ?? false,
          autoFocus: props.autoFocus === true,
          "data-autofocus": props.autoFocus === true ? "true" : "false",
          onChange: (event: ChangeEvent<HTMLTextAreaElement>) => props.onChange(event.target.value),
        }),
        props.toolbarActions === undefined || props.toolbarActions === null
          ? null
          : createElement("div", { "data-testid": "stub-toolbar-actions" }, props.toolbarActions),
      );
    },
  };
});

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string; body: unknown };
type Handler = (request: Seen) => Response | Promise<Response>;

// ---------------------------------------------------------------- the spec's names
const TITLE = "Notes";
const NOTE_LABEL = "Note";
const NEW_NOTE = "New note";
const SAVE_NEW_NOTE = "Save new note";
const CANCEL_NEW_NOTE = "Cancel new note";
const DISABLE_NOTE = "Disable note";
const ENABLE_NOTE = "Enable note";
const FORCE_NOTE = "Force note";
const STOP_FORCING_NOTE = "Stop forcing note";
const FLAG_LABELS = [DISABLE_NOTE, ENABLE_NOTE, FORCE_NOTE, STOP_FORCING_NOTE];
const SAVE_FAILURE = "Could not save the note.";
const CHANGE_FAILURE = "Could not change the note.";
const SEARCHABLE_LINE = "Searchable: found only when the assistant searches.";
const FORCED_LINE = "Forced: always given to the assistant.";
const DISABLED_LINE = "Disabled: never reaches the assistant.";
const EMPTY_LINE = "No notes yet.";
const LOAD_FAILED = "Could not load notes";
const NOTIFICATION = ".mantine-Notification-root";
const STUB_ROOT = '[data-testid="markdown-editor-stub"]';
const STUB_ACTIONS = '[data-testid="stub-toolbar-actions"]';

// ---------------------------------------------------------------- fixtures
const CHARACTER_ID = "7250000000000000011";
const MEMO_A = "7250000000000000201";
const MEMO_B = "7250000000000000202";
const MEMO_C = "7250000000000000203";
const MEMO_D = "7250000000000000204";
const CREATED_ID = "9007199254740993";
const STAMP = "2026-10-02T09:26:53.000000+00:00";
const MEMOS_PATH = "/api/memos";

const BODY_A = "Mira distrusts the harbour master.";
const BODY_B = "Keep replies under 150 words.";
const BODY_C = "The tavern burned down last winter.";
const BODY_D = "Never mention the brother.";
const TYPED = "Voice: dry";

function memo(id: string, body: string, overrides: Partial<Memo> = {}): Memo {
  return {
    id,
    scope: "character",
    scope_id: CHARACTER_ID,
    body,
    is_enabled: true,
    is_forced: false,
    sort_key: 0,
    created_at: STAMP,
    updated_at: STAMP,
    ...overrides,
  };
}

function rows(): Memo[] {
  return [memo(MEMO_A, BODY_A), memo(MEMO_B, BODY_B, { sort_key: 1 })];
}

function stampAt(n: number): string {
  return `2026-10-02T09:30:${String(n).padStart(2, "0")}.000000+00:00`;
}

function memoPath(id: string): string {
  return `${MEMOS_PATH}/${id}`;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- fetch helpers
function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function parseBody(init?: RequestInit): unknown {
  const raw = init?.body;
  if (raw === undefined || raw === null) return undefined;
  return JSON.parse(String(raw)) as unknown;
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: "ql-77 went wrong.", detail: {} } }, status);
}

function serverError(): Response {
  return envelope("internal_error", 500);
}

function stubBackend(handler: Handler) {
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>(async (input, init) => {
    const url = requestUrl(input);
    const request: Seen = {
      method: requestMethod(input, init),
      path: url.pathname,
      search: url.search,
      body: parseBody(init),
    };
    calls.push(request);
    return handler(request);
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

type Failing = { patch?: boolean; delete?: boolean; post?: boolean };

/**
 * A server answering as the backend would: PATCH merges the sent keys into the held row with a
 * later updated_at; DELETE answers 204; POST creates CREATED_ID (enabled, not forced) from the
 * sent scope, scope_id and body. A method named in `failing` answers 500 instead.
 */
function serveNotes(initial: Memo[], failing: Failing = {}) {
  const byId = new Map<string, Memo>(initial.map((row) => [row.id, row]));
  let tick = 0;
  return stubBackend((request) => {
    if (request.method === "PATCH" && request.search === "") {
      if (failing.patch === true) return serverError();
      const current = [...byId.values()].find((row) => memoPath(row.id) === request.path);
      if (current === undefined) return envelope("memo_not_found", 404);
      tick += 1;
      const next: Memo = { ...current, ...(request.body as Partial<Memo>), updated_at: stampAt(tick) };
      byId.set(next.id, next);
      return jsonResponse(next, 200);
    }
    if (request.method === "DELETE" && request.search === "") {
      if (failing.delete === true) return serverError();
      const current = [...byId.values()].find((row) => memoPath(row.id) === request.path);
      if (current === undefined) return envelope("memo_not_found", 404);
      byId.delete(current.id);
      return new Response(null, { status: 204 });
    }
    if (request.method === "POST" && request.path === MEMOS_PATH && request.search === "") {
      if (failing.post === true) return serverError();
      const sent = request.body as { scope: MemoScope; scope_id: string | null; body: string };
      tick += 1;
      const created = memo(CREATED_ID, sent.body, {
        scope: sent.scope,
        scope_id: sent.scope_id,
        sort_key: 9,
        created_at: stampAt(tick),
        updated_at: stampAt(tick),
      });
      byId.set(created.id, created);
      return jsonResponse(created, 201);
    }
    return envelope("memo_not_found", 404);
  });
}

type Held = { promise: Promise<Response>; resolve: (value: Response) => void };

function held(): Held {
  let resolve: (value: Response) => void = () => undefined;
  const promise = new Promise<Response>((ok) => {
    resolve = ok;
  });
  return { promise, resolve };
}

async function settle(): Promise<void> {
  await act(async () => {
    for (let round = 0; round < 6; round += 1) await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
    for (let round = 0; round < 6; round += 1) await Promise.resolve();
  });
}

// ---------------------------------------------------------------- render helpers
function newUser() {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

function readyLevel(...saved: Memo[]): MemoLevelState {
  const state = new MemoLevelState("character", CHARACTER_ID);
  populateMemoLevel(state, saved);
  return state;
}

function renderGroup(state: MemoLevelState) {
  const onRetry = vi.fn<() => void>();
  const result = render(
    <AppProviders>
      <MemoLevelGroup state={state} title={TITLE} headingOrder={3} onRetry={onRetry} />
    </AppProviders>,
  );
  return { ...result, onRetry };
}

function region(): HTMLElement {
  return screen.getByRole("region", { name: TITLE });
}

function heading(): HTMLElement {
  return within(region()).getByRole("heading", { name: TITLE });
}

function items(): HTMLElement[] {
  return within(region()).queryAllByRole("listitem");
}

function itemAt(index: number): HTMLElement {
  const all = items();
  const item = all[index];
  if (item === undefined) throw new Error(`no listitem at ${index} (have ${all.length})`);
  return item;
}

function noteBox(item: HTMLElement): HTMLTextAreaElement {
  return within(item).getByRole("textbox", { name: NOTE_LABEL }) as HTMLTextAreaElement;
}

function bodies(): string[] {
  return within(region())
    .queryAllByRole("textbox", { name: NOTE_LABEL })
    .map((box) => (box as HTMLTextAreaElement).value);
}

function button(scope: HTMLElement, name: string): HTMLElement {
  return within(scope).getByRole("button", { name });
}

function hasButton(scope: HTMLElement, name: string): boolean {
  return within(scope).queryByRole("button", { name }) !== null;
}

function newNoteButtons(): HTMLElement[] {
  return within(region()).queryAllByRole("button", { name: NEW_NOTE });
}

function newNoteButton(): HTMLElement {
  const all = newNoteButtons();
  expect(all).toHaveLength(1);
  return all[0];
}

function editorRoot(item: HTMLElement): HTMLElement {
  const root = item.querySelector(STUB_ROOT);
  if (root === null) throw new Error("no editor in this listitem");
  return root as HTMLElement;
}

function actionsOf(item: HTMLElement): HTMLElement | null {
  return item.querySelector(STUB_ACTIONS);
}

function precedes(first: Node, second: Node): boolean {
  return (first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

/** Whether a button shows the given text as its own visible content (a labelled button). */
function showsText(element: HTMLElement, text: string): boolean {
  return (element.textContent ?? "").includes(text);
}

function expectNoSaveOrCancel(): void {
  expect(screen.queryByRole("button", { name: SAVE_NEW_NOTE })).toBeNull();
  expect(screen.queryByRole("button", { name: CANCEL_NEW_NOTE })).toBeNull();
}

async function openDraft(user: ReturnType<typeof newUser>, savedCount: number): Promise<void> {
  await user.click(newNoteButton());
  await waitFor(() => {
    expect(items()).toHaveLength(savedCount + 1);
  });
}

// ===========================================================================
describe("the header '+' (one behaviour, every mount)", () => {
  it("renders exactly one New note button, icon-only, in the header beside the Title and before the list — DoD-3", () => {
    stubBackend(() => serverError());
    renderGroup(readyLevel(...rows()));

    const plus = newNoteButton();
    expect(showsText(plus, NEW_NOTE)).toBe(false);
    const list = itemAt(0).closest("ul");
    expect(list).not.toBeNull();
    const header = heading().parentElement;
    expect(header?.contains(plus)).toBe(true);
    expect(header?.contains(list as HTMLElement)).toBe(false);
    expect(precedes(heading(), plus)).toBe(true);
    expect(precedes(plus, list as HTMLElement)).toBe(true);
    for (const item of items()) {
      expect(item.contains(plus)).toBe(false);
    }
    expect(plus).toBeEnabled();
  });

  it("an empty ready level shows No notes yet. after the header '+', and that is the only New note button — DoD-3", () => {
    stubBackend(() => serverError());
    renderGroup(readyLevel());

    const plus = newNoteButton();
    expect(heading().parentElement?.contains(plus)).toBe(true);
    expect(precedes(plus, within(region()).getByText(EMPTY_LINE))).toBe(true);
    expect(plus).toBeEnabled();
  });

  it("renders no New note while the level is loading or after it failed to load (ready state only) — DoD-3", async () => {
    stubBackend(() => serverError());
    const loading = new MemoLevelState("character", CHARACTER_ID);
    const view = renderGroup(loading);
    expect(newNoteButtons()).toHaveLength(0);
    view.unmount();

    const failed = new MemoLevelState("character", CHARACTER_ID);
    await act(async () => {
      await loadMemoLevel(failed);
    });
    renderGroup(failed);
    await waitFor(() => {
      expect(within(region()).queryByText(LOAD_FAILED)).not.toBeNull();
    });
    expect(newNoteButtons()).toHaveLength(0);
  });
});

// ===========================================================================
describe("the draft", () => {
  it("New note opens an empty draft as the first item with focus in its editor, no flag buttons and no toolbar actions; New note is disabled while it is open — DoD-4", async () => {
    stubBackend(() => serverError());
    renderGroup(readyLevel(...rows()));
    const user = newUser();

    await openDraft(user, 2);

    const draft = itemAt(0);
    const editor = noteBox(draft);
    expect(editor).toHaveValue("");
    await waitFor(() => {
      expect(document.activeElement).toBe(editor);
    });
    for (const label of FLAG_LABELS) {
      expect(hasButton(draft, label)).toBe(false);
    }
    expect(actionsOf(draft)).toBeNull();
    expect(newNoteButton()).toBeDisabled();
    expect(bodies()).toEqual(["", BODY_A, BODY_B]);
  });

  it("focus leaving a draft holding text sends exactly one create for the level; the note appears first, the draft closes and New note is enabled again — DoD-6", async () => {
    const { calls } = serveNotes(rows());
    renderGroup(readyLevel(...rows()));
    const user = newUser();
    await openDraft(user, 2);
    fireEvent.change(noteBox(itemAt(0)), { target: { value: TYPED } });

    fireEvent.blur(noteBox(itemAt(0)));

    await waitFor(() => {
      expect(hasButton(itemAt(0), DISABLE_NOTE)).toBe(true);
    });
    await settle();
    expect(calls).toEqual([
      {
        method: "POST",
        path: MEMOS_PATH,
        search: "",
        body: { scope: "character", scope_id: CHARACTER_ID, body: TYPED },
      },
    ]);
    expect(bodies()).toEqual([TYPED, BODY_A, BODY_B]);
    expect(items()).toHaveLength(3);
    expect(newNoteButton()).toBeEnabled();
  });

  it("focus moving from the draft to an element outside it (the group's heading) also saves the draft — DoD-6", async () => {
    const { calls } = serveNotes(rows());
    renderGroup(readyLevel(...rows()));
    const user = newUser();
    await openDraft(user, 2);
    const editor = noteBox(itemAt(0));
    fireEvent.change(editor, { target: { value: TYPED } });

    fireEvent.blur(editor, { relatedTarget: heading() });

    await waitFor(() => {
      expect(calls.filter((call) => call.method === "POST")).toHaveLength(1);
    });
    await waitFor(() => {
      expect(newNoteButton()).toBeEnabled();
    });
    expect(bodies()).toEqual([TYPED, BODY_A, BODY_B]);
  });

  it.each<[string, string | null]>([
    ["untouched (empty)", null],
    ["whitespace only", "  \n\t  "],
  ])(
    "focus leaving a %s draft sends no request, closes the draft and enables New note again — DoD-7",
    async (_label, text) => {
      const { calls } = serveNotes(rows());
      renderGroup(readyLevel(...rows()));
      const user = newUser();
      await openDraft(user, 2);
      if (text !== null) fireEvent.change(noteBox(itemAt(0)), { target: { value: text } });

      fireEvent.blur(noteBox(itemAt(0)));

      await waitFor(() => {
        expect(items()).toHaveLength(2);
      });
      await settle();
      expect(calls).toEqual([]);
      expect(bodies()).toEqual([BODY_A, BODY_B]);
      expect(newNoteButton()).toBeEnabled();
    },
  );

  it("a failed create keeps the draft open as the first item with its typed text and shows the failure inside it — DoD-8", async () => {
    const response = held();
    const { calls } = stubBackend(() => response.promise);
    renderGroup(readyLevel(...rows()));
    const user = newUser();
    await openDraft(user, 2);
    fireEvent.change(noteBox(itemAt(0)), { target: { value: TYPED } });

    fireEvent.blur(noteBox(itemAt(0)));
    await waitFor(() => {
      expect(calls).toHaveLength(1);
    });
    await act(async () => {
      response.resolve(serverError());
    });

    await waitFor(() => {
      expect(within(itemAt(0)).queryByText(SAVE_FAILURE)).not.toBeNull();
    });
    await settle();
    expect(items()).toHaveLength(3);
    expect(noteBox(itemAt(0))).toHaveValue(TYPED);
    expect(within(region()).getAllByText(SAVE_FAILURE)).toHaveLength(1);
    expect(within(itemAt(1)).queryByText(SAVE_FAILURE)).toBeNull();
    expect(newNoteButton()).toBeDisabled();
    expect(calls).toHaveLength(1);
    expect(document.querySelector(NOTIFICATION)).toBeNull();
  });
});

// ===========================================================================
describe("no Save / Cancel new note in any state", () => {
  it("neither button renders: ready, draft open, draft typed, create in flight, create failed, draft saved — DoD-5", async () => {
    const response = held();
    let postCount = 0;
    stubBackend((request) => {
      if (request.method === "POST" && request.path === MEMOS_PATH) {
        postCount += 1;
        if (postCount === 1) return response.promise;
        const sent = request.body as { scope: MemoScope; scope_id: string | null; body: string };
        return jsonResponse(memo(CREATED_ID, sent.body, { scope: sent.scope, scope_id: sent.scope_id }), 201);
      }
      return serverError();
    });
    renderGroup(readyLevel(...rows()));
    const user = newUser();

    expectNoSaveOrCancel();
    await openDraft(user, 2);
    expectNoSaveOrCancel();
    fireEvent.change(noteBox(itemAt(0)), { target: { value: TYPED } });
    expectNoSaveOrCancel();

    fireEvent.blur(noteBox(itemAt(0)));
    await waitFor(() => {
      expect(postCount).toBe(1);
    });
    expectNoSaveOrCancel();

    await act(async () => {
      response.resolve(serverError());
    });
    await waitFor(() => {
      expect(within(itemAt(0)).queryByText(SAVE_FAILURE)).not.toBeNull();
    });
    expectNoSaveOrCancel();

    fireEvent.blur(noteBox(itemAt(0)));
    await waitFor(() => {
      expect(hasButton(itemAt(0), DISABLE_NOTE)).toBe(true);
    });
    expectNoSaveOrCancel();
  });
});

// ===========================================================================
describe("a saved note saves when focus leaves it", () => {
  it("text cleared to whitespace only, focus leaving → exactly one DELETE for that note, no confirm, and it leaves the list — DoD-9", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const { calls } = serveNotes(rows());
    renderGroup(readyLevel(...rows()));

    fireEvent.change(noteBox(itemAt(0)), { target: { value: "  \n  " } });
    fireEvent.blur(noteBox(itemAt(0)));

    await waitFor(() => {
      expect(items()).toHaveLength(1);
    });
    await settle();
    expect(calls).toEqual([{ method: "DELETE", path: memoPath(MEMO_A), search: "", body: undefined }]);
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(bodies()).toEqual([BODY_B]);
  });

  it("changed non-blank text, focus leaving → exactly one body patch — DoD-9", async () => {
    const { calls } = serveNotes(rows());
    renderGroup(readyLevel(...rows()));
    const typed = "Mira now trusts the harbour master.";

    fireEvent.change(noteBox(itemAt(1)), { target: { value: typed } });
    fireEvent.blur(noteBox(itemAt(1)));

    await waitFor(() => {
      expect(calls).toHaveLength(1);
    });
    await settle();
    expect(calls).toEqual([{ method: "PATCH", path: memoPath(MEMO_B), search: "", body: { body: typed } }]);
    expect(noteBox(itemAt(1))).toHaveValue(typed);
  });

  it("unchanged text, focus leaving → no request — DoD-9", async () => {
    const { calls } = serveNotes(rows());
    renderGroup(readyLevel(...rows()));

    fireEvent.blur(noteBox(itemAt(0)));
    fireEvent.blur(noteBox(itemAt(1)));
    await settle();

    expect(calls).toEqual([]);
  });
});

// ===========================================================================
describe("a saved note's flags are its editor's toolbar actions", () => {
  function fourCombinations(): Memo[] {
    return [
      memo(MEMO_A, BODY_A, { is_enabled: true, is_forced: true, sort_key: 0 }),
      memo(MEMO_B, BODY_B, { is_enabled: true, is_forced: false, sort_key: 1 }),
      memo(MEMO_C, BODY_C, { is_enabled: false, is_forced: true, sort_key: 2 }),
      memo(MEMO_D, BODY_D, { is_enabled: false, is_forced: false, sort_key: 3 }),
    ];
  }

  it("both flag buttons render inside the note's editor root (the toolbar-actions content), labelled by the flag state, and none renders outside it — DoD-10", () => {
    stubBackend(() => serverError());
    renderGroup(readyLevel(...fourCombinations()));

    const expected: Array<[number, string, string]> = [
      [0, DISABLE_NOTE, STOP_FORCING_NOTE],
      [1, DISABLE_NOTE, FORCE_NOTE],
      [2, ENABLE_NOTE, STOP_FORCING_NOTE],
      [3, ENABLE_NOTE, FORCE_NOTE],
    ];
    for (const [index, enabledLabel, forcedLabel] of expected) {
      const item = itemAt(index);
      const root = editorRoot(item);
      const actions = actionsOf(item);
      expect(actions).not.toBeNull();
      expect(root.contains(actions)).toBe(true);
      const shown = FLAG_LABELS.filter((label) => hasButton(actions as HTMLElement, label));
      expect(shown.sort()).toEqual([enabledLabel, forcedLabel].sort());
      // Every flag button of the item is inside the editor root: none in a row after it.
      const flagsInItem = FLAG_LABELS.flatMap((label) => within(item).queryAllByRole("button", { name: label }));
      expect(flagsInItem).toHaveLength(2);
      for (const flag of flagsInItem) {
        expect(root.contains(flag)).toBe(true);
      }
    }
  });

  it("both flag buttons, still inside the editor root, are disabled while a flag write is in flight and enabled after it — DoD-10", async () => {
    const response = held();
    const { calls } = stubBackend(() => response.promise);
    const row = memo(MEMO_B, BODY_B, { is_enabled: true, is_forced: false });
    renderGroup(readyLevel(row));
    const user = newUser();

    await user.click(button(itemAt(0), DISABLE_NOTE));
    await waitFor(() => {
      expect(calls).toHaveLength(1);
    });
    await waitFor(() => {
      expect(button(itemAt(0), DISABLE_NOTE)).toBeDisabled();
    });
    expect(button(itemAt(0), FORCE_NOTE)).toBeDisabled();
    const actions = actionsOf(itemAt(0)) as HTMLElement;
    expect(actions.contains(button(itemAt(0), DISABLE_NOTE))).toBe(true);
    expect(actions.contains(button(itemAt(0), FORCE_NOTE))).toBe(true);

    await act(async () => {
      response.resolve(jsonResponse({ ...row, is_enabled: false, updated_at: stampAt(1) }, 200));
    });
    await waitFor(() => {
      expect(button(itemAt(0), ENABLE_NOTE)).toBeEnabled();
    });
    expect(button(itemAt(0), FORCE_NOTE)).toBeEnabled();
    expect((actionsOf(itemAt(0)) as HTMLElement).contains(button(itemAt(0), ENABLE_NOTE))).toBe(true);
  });

  it("editing a saved note then clicking a flag sends only that flag's patch and keeps the edited text; the body is saved when focus later leaves the note — DoD-11", async () => {
    const { calls } = serveNotes(rows());
    renderGroup(readyLevel(...rows()));
    const user = newUser();
    const typed = "Mira now owes the harbour master.";

    const box = noteBox(itemAt(0));
    fireEvent.change(box, { target: { value: typed } });
    // Focus moves from the editor to the flag button inside the same note.
    const flag = button(itemAt(0), DISABLE_NOTE);
    fireEvent.blur(box, { relatedTarget: flag });
    await user.click(flag);

    await waitFor(() => {
      expect(hasButton(itemAt(0), ENABLE_NOTE)).toBe(true);
    });
    await settle();
    expect(calls).toEqual([{ method: "PATCH", path: memoPath(MEMO_A), search: "", body: { is_enabled: false } }]);
    expect(noteBox(itemAt(0))).toHaveValue(typed);

    // Focus now leaves the note (from the flag button to nowhere inside it).
    fireEvent.blur(button(itemAt(0), ENABLE_NOTE));

    await waitFor(() => {
      expect(calls).toHaveLength(2);
    });
    await settle();
    expect(calls).toEqual([
      { method: "PATCH", path: memoPath(MEMO_A), search: "", body: { is_enabled: false } },
      { method: "PATCH", path: memoPath(MEMO_A), search: "", body: { body: typed } },
    ]);
    expect(noteBox(itemAt(0))).toHaveValue(typed);
  });

  it("the Force note flag behaves the same: only is_forced is sent while the edited text stays — DoD-11", async () => {
    const { calls } = serveNotes(rows());
    renderGroup(readyLevel(...rows()));
    const user = newUser();
    const typed = "Keep replies under 120 words.";

    const box = noteBox(itemAt(1));
    fireEvent.change(box, { target: { value: typed } });
    const flag = button(itemAt(1), FORCE_NOTE);
    fireEvent.blur(box, { relatedTarget: flag });
    await user.click(flag);

    await waitFor(() => {
      expect(hasButton(itemAt(1), STOP_FORCING_NOTE)).toBe(true);
    });
    await settle();
    expect(calls).toEqual([{ method: "PATCH", path: memoPath(MEMO_B), search: "", body: { is_forced: true } }]);
    expect(noteBox(itemAt(1))).toHaveValue(typed);
  });
});

// ===========================================================================
describe("the reach line and the failure text stay after the editor", () => {
  it("the reach line renders after the editor root, outside it and outside the toolbar actions — DoD-12", () => {
    stubBackend(() => serverError());
    renderGroup(
      readyLevel(
        memo(MEMO_A, BODY_A, { is_enabled: true, is_forced: false }),
        memo(MEMO_B, BODY_B, { is_enabled: true, is_forced: true, sort_key: 1 }),
        memo(MEMO_C, BODY_C, { is_enabled: false, sort_key: 2 }),
      ),
    );

    const expected: Array<[number, string]> = [
      [0, SEARCHABLE_LINE],
      [1, FORCED_LINE],
      [2, DISABLED_LINE],
    ];
    for (const [index, line] of expected) {
      const item = itemAt(index);
      const root = editorRoot(item);
      const reach = within(item).getByText(line);
      expect(root.contains(reach)).toBe(false);
      expect(precedes(root, reach)).toBe(true);
    }
  });

  it("a failed body save's text renders after the editor root, outside it — DoD-12", async () => {
    serveNotes(rows(), { patch: true });
    renderGroup(readyLevel(...rows()));

    fireEvent.change(noteBox(itemAt(0)), { target: { value: "A rewrite that will not land." } });
    fireEvent.blur(noteBox(itemAt(0)));

    const failure = await within(itemAt(0)).findByText(SAVE_FAILURE);
    const root = editorRoot(itemAt(0));
    expect(root.contains(failure)).toBe(false);
    expect(precedes(root, failure)).toBe(true);
  });

  it("a failed flag write's text renders after the editor root, outside it — DoD-12", async () => {
    serveNotes(rows(), { patch: true });
    renderGroup(readyLevel(...rows()));

    await newUser().click(button(itemAt(1), FORCE_NOTE));

    const failure = await within(itemAt(1)).findByText(CHANGE_FAILURE);
    const root = editorRoot(itemAt(1));
    expect(root.contains(failure)).toBe(false);
    expect(precedes(root, failure)).toBe(true);
  });
});
