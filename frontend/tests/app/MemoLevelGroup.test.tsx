// Feature 015, step 007 — the shared level group component (DoD-1..DoD-16; DoD-17 is
// [manual/live] and carries no test).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 007.context.md (the region and its name, focus leave, the flush, test notes) and the
// feature's context.md: D2 (blank new note dropped, cleared saved note deleted, no confirm),
// D5 (save on focus loss, never optimistic, failures inline, leaving keeps the edit), D6 (one
// key per toggle, both controls always shown), D13 (the new note: no flags, no reach line),
// D14 (the four action labels), R3 (is_enabled gates first) and the UI strings table.
//
// Recognition conventions (for the verifier):
// - The group is a region whose accessible name is its `title`; every assertion about what
//   the group shows goes through `within(region())`, then `getAllByRole("listitem")`.
// - `src/shared/MarkdownEditor` is replaced by a labelled `<textarea>` stub (context.md
//   "Test conventions"). It is the SetupsSection.test.tsx stub with two changes this step
//   needs: the textarea id comes from React's `useId` (several editors labelled "Note" are
//   on screen at once, and a label-derived id would collide, leaving all but the first
//   textarea unnamed), and the stub records the `label` / `value` props it receives (DoD-2).
// - Focus loss is `fireEvent.blur` on the textarea (its relatedTarget is null, so it counts
//   as leaving the wrapper); typing is `fireEvent.change`.
// - A Mantine `Loader`: `.mantine-Loader-root`. A notification: `.mantine-Notification-root`.
// - `fetch` is stubbed per test; requests are recorded by exact method + pathname + query
//   string with the parsed JSON body, so whole-object comparison catches a stray key.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ChangeEvent } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoLevelGroup } from "../../src/app/MemoLevelGroup";
import type { Memo, MemoScope } from "../../src/app/memosApi";
import { loadMemoLevel, MemoLevelState, populateMemoLevel } from "../../src/app/memoLevelState";
import { AppProviders } from "../../src/shared/AppProviders";

type EditorCall = { label: string; value: string; onChangeIsFunction: boolean };

const editorRecord = vi.hoisted(() => ({ received: [] as EditorCall[] }));

vi.mock("../../src/shared/MarkdownEditor", async () => {
  const { createElement, useId } = await import("react");
  type StubProps = {
    label: string;
    value: string;
    onChange: (markdown: string) => void;
    readOnly?: boolean;
  };
  return {
    MarkdownEditor: (props: StubProps) => {
      editorRecord.received.push({
        label: props.label,
        value: props.value,
        onChangeIsFunction: typeof props.onChange === "function",
      });
      const id = `markdown-editor-${useId()}`;
      return createElement(
        "div",
        null,
        createElement("label", { htmlFor: id }, props.label),
        createElement("textarea", {
          id,
          value: props.value,
          readOnly: props.readOnly ?? false,
          onChange: (event: ChangeEvent<HTMLTextAreaElement>) => props.onChange(event.target.value),
        }),
      );
    },
  };
});

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string; body: unknown };
type Handler = (request: Seen) => Response | Promise<Response>;

// ---------------------------------------------------------------- the spec's names
const TITLE = "Character notes";
const NOTE_LABEL = "Note";
const NEW_NOTE = "New note";
const DISABLE_NOTE = "Disable note";
const ENABLE_NOTE = "Enable note";
const FORCE_NOTE = "Force note";
const STOP_FORCING_NOTE = "Stop forcing note";
const RETRY = "Retry";

const FORCED_LINE = "Forced: always given to the assistant.";
const SEARCHABLE_LINE = "Searchable: found only when the assistant searches.";
const DISABLED_LINE = "Disabled: never reaches the assistant.";
const EMPTY_LINE = "No notes yet.";
const LOAD_FAILED = "Could not load notes";
const SAVE_FAILURE = "Could not save the note.";
const DELETE_FAILURE = "Could not delete the note.";
const CHANGE_FAILURE = "Could not change the note.";

const LOADER = ".mantine-Loader-root";
const NOTIFICATION = ".mantine-Notification-root";

const FLAG_LABELS = [DISABLE_NOTE, ENABLE_NOTE, FORCE_NOTE, STOP_FORCING_NOTE];
const REACH_LINES = [FORCED_LINE, SEARCHABLE_LINE, DISABLED_LINE];

// ---------------------------------------------------------------- fixtures
const CHARACTER_ID = "7250000000000000011";
const MEMO_A = "7250000000000000201";
const MEMO_B = "7250000000000000202";
const MEMO_C = "7250000000000000203";
const MEMO_D = "7250000000000000204";
const CREATED_ID = "9007199254740993";

const STAMP = "2026-10-02T09:26:53.000000+00:00";

const BODY_A = "Mira distrusts the harbour master.";
const BODY_B = "Keep replies under 150 words.";
const BODY_C = "The tavern burned down last winter.";
const BODY_D = "Never mention the brother.";

function stampAt(n: number): string {
  return `2026-10-02T09:30:${String(n).padStart(2, "0")}.000000+00:00`;
}

/** A wire Memo with all nine keys; a character-level note unless overridden. */
function memo(id: string, overrides: Partial<Memo> = {}): Memo {
  return {
    id,
    scope: "character",
    scope_id: CHARACTER_ID,
    body: BODY_A,
    is_enabled: true,
    is_forced: false,
    sort_key: 0,
    created_at: STAMP,
    updated_at: STAMP,
    ...overrides,
  };
}

function memoPath(id: string): string {
  return `/api/memos/${id}`;
}

beforeEach(() => {
  editorRecord.received.length = 0;
});

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

function noContent(): Response {
  return new Response(null, { status: 204 });
}

function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: "ql-77 went wrong.", detail: {} } }, status);
}

function notFoundResponse(): Response {
  return envelope("memo_not_found", 404);
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

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void };

function deferred<T>(): Deferred<T> {
  let resolve: (value: T) => void = () => undefined;
  const promise = new Promise<T>((ok) => {
    resolve = ok;
  });
  return { promise, resolve };
}

/** Every request is held open until the test resolves it, in request order. */
function stubHeld() {
  const held: Deferred<Response>[] = [];
  const backend = stubBackend(() => {
    const next = deferred<Response>();
    held.push(next);
    return next.promise;
  });
  return { ...backend, held };
}

type Failing = { patch?: boolean; delete?: boolean; post?: boolean };

/**
 * A server answering as the backend would: PATCH merges the supplied keys into the held row
 * with a later updated_at; DELETE answers 204; POST creates CREATED_ID (enabled, not forced)
 * from the sent scope, scope_id and body. A method named in `failing` answers 500 instead.
 */
function serveNotes(rows: Memo[], failing: Failing = {}) {
  const byId = new Map<string, Memo>(rows.map((row) => [row.id, row]));
  let tick = 0;
  return stubBackend((request) => {
    if (request.method === "PATCH" && request.search === "") {
      if (failing.patch === true) return serverError();
      const current = [...byId.values()].find((row) => memoPath(row.id) === request.path);
      if (current === undefined) return notFoundResponse();
      tick += 1;
      const next: Memo = { ...current, ...(request.body as Partial<Memo>), updated_at: stampAt(tick) };
      byId.set(next.id, next);
      return jsonResponse(next, 200);
    }
    if (request.method === "DELETE" && request.search === "") {
      if (failing.delete === true) return serverError();
      const current = [...byId.values()].find((row) => memoPath(row.id) === request.path);
      if (current === undefined) return notFoundResponse();
      byId.delete(current.id);
      return noContent();
    }
    if (request.method === "POST" && request.path === "/api/memos" && request.search === "") {
      if (failing.post === true) return serverError();
      const sent = request.body as { scope: MemoScope; scope_id: string | null; body: string };
      tick += 1;
      const created = memo(CREATED_ID, {
        scope: sent.scope,
        scope_id: sent.scope_id,
        body: sent.body,
        is_enabled: true,
        is_forced: false,
        sort_key: 9,
        created_at: stampAt(tick),
        updated_at: stampAt(tick),
      });
      byId.set(created.id, created);
      return jsonResponse(created, 201);
    }
    return notFoundResponse();
  });
}

/** Let pending microtasks and a macrotask run, so a request that would be sent has been. */
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

function readyLevel(...rows: Memo[]): MemoLevelState {
  const state = new MemoLevelState("character", CHARACTER_ID);
  populateMemoLevel(state, rows);
  return state;
}

function renderGroup(state: MemoLevelState, options: { title?: string; headingOrder?: 2 | 3 | 4 } = {}) {
  const onRetry = vi.fn<() => void>();
  const result = render(
    <AppProviders>
      <MemoLevelGroup
        state={state}
        title={options.title ?? TITLE}
        headingOrder={options.headingOrder ?? 3}
        onRetry={onRetry}
      />
    </AppProviders>,
  );
  return { ...result, onRetry };
}

function region(title: string = TITLE): HTMLElement {
  return screen.getByRole("region", { name: title });
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

function lastItem(): HTMLElement {
  return itemAt(items().length - 1);
}

function noteBox(item: HTMLElement): HTMLTextAreaElement {
  return within(item).getByRole("textbox", { name: NOTE_LABEL }) as HTMLTextAreaElement;
}

function button(scope: HTMLElement, name: string): HTMLElement {
  return within(scope).getByRole("button", { name });
}

function hasButton(scope: HTMLElement, name: string): boolean {
  return within(scope).queryByRole("button", { name }) !== null;
}

function newNoteButton(): HTMLElement {
  return button(region(), NEW_NOTE);
}

// ===========================================================================
describe("the ready group's region, list and editors", () => {
  it("a ready state with two notes renders a region named by title, its heading, and a list of exactly two listitems in state order — DoD-1", () => {
    stubBackend(() => notFoundResponse());
    renderGroup(readyLevel(memo(MEMO_B, { body: BODY_B }), memo(MEMO_A, { body: BODY_A, sort_key: 1 })));

    const group = region();
    expect(within(group).getByRole("heading", { name: TITLE })).toBeInTheDocument();
    expect(within(group).getAllByRole("list")).toHaveLength(1);
    const listed = within(group).getAllByRole("listitem");
    expect(listed).toHaveLength(2);
    expect(noteBox(listed[0]).value).toBe(BODY_B);
    expect(noteBox(listed[1]).value).toBe(BODY_A);
  });

  it("each listitem holds exactly one textbox, labelled Note, and the region holds no other textbox — DoD-1", () => {
    stubBackend(() => notFoundResponse());
    renderGroup(readyLevel(memo(MEMO_A, { body: BODY_A }), memo(MEMO_B, { body: BODY_B, sort_key: 1 })));

    for (const item of items()) {
      const boxes = within(item).getAllByRole("textbox");
      expect(boxes).toHaveLength(1);
      expect(boxes[0]).toBe(within(item).getByRole("textbox", { name: NOTE_LABEL }));
    }
    expect(within(region()).getAllByRole("textbox")).toHaveLength(2);
    expect(within(region()).getAllByRole("textbox", { name: NOTE_LABEL })).toHaveLength(2);
  });

  it("the heading is at the level headingOrder names — DoD-1", () => {
    stubBackend(() => notFoundResponse());
    const { unmount } = renderGroup(readyLevel(memo(MEMO_A)), { headingOrder: 3 });
    expect(within(region()).getByRole("heading", { name: TITLE, level: 3 })).toBeInTheDocument();
    unmount();

    renderGroup(readyLevel(memo(MEMO_A)), { title: "Your notes", headingOrder: 4 });
    expect(within(region("Your notes")).getByRole("heading", { name: "Your notes", level: 4 })).toBeInTheDocument();
  });

  it("the editor is the shared MarkdownEditor: each note's editor receives label Note and that note's text — DoD-2", () => {
    stubBackend(() => notFoundResponse());
    renderGroup(readyLevel(memo(MEMO_A, { body: BODY_A }), memo(MEMO_B, { body: BODY_B, sort_key: 1 })));

    expect(editorRecord.received.length).toBeGreaterThan(0);
    for (const call of editorRecord.received) {
      expect(call.label).toBe(NOTE_LABEL);
      expect(call.onChangeIsFunction).toBe(true);
    }
    const values = editorRecord.received.map((call) => call.value);
    expect(values).toContain(BODY_A);
    expect(values).toContain(BODY_B);
    // The rendered textareas are the stub's, not some other editor.
    expect(within(region()).getAllByRole("textbox", { name: NOTE_LABEL }).every((box) => box.tagName === "TEXTAREA")).toBe(true);
  });
});

// ===========================================================================
describe("reach lines and flag controls", () => {
  function fourCombinations(): MemoLevelState {
    return readyLevel(
      memo(MEMO_A, { body: BODY_A, is_enabled: true, is_forced: true, sort_key: 0 }),
      memo(MEMO_B, { body: BODY_B, is_enabled: true, is_forced: false, sort_key: 1 }),
      memo(MEMO_C, { body: BODY_C, is_enabled: false, is_forced: true, sort_key: 2 }),
      memo(MEMO_D, { body: BODY_D, is_enabled: false, is_forced: false, sort_key: 3 }),
    );
  }

  function reachLinesIn(item: HTMLElement): string[] {
    return REACH_LINES.filter((line) => within(item).queryByText(line) !== null);
  }

  it("an enabled forced note shows the forced line, enabled not-forced the searchable line, and both disabled notes the disabled line — DoD-3", () => {
    stubBackend(() => notFoundResponse());
    renderGroup(fourCombinations());

    expect(reachLinesIn(itemAt(0))).toEqual([FORCED_LINE]);
    expect(reachLinesIn(itemAt(1))).toEqual([SEARCHABLE_LINE]);
    expect(reachLinesIn(itemAt(2))).toEqual([DISABLED_LINE]);
    expect(reachLinesIn(itemAt(3))).toEqual([DISABLED_LINE]);
  });

  it("enabled notes show Disable note, disabled ones Enable note; not-forced notes show Force note, forced ones Stop forcing note — DoD-4", () => {
    stubBackend(() => notFoundResponse());
    renderGroup(fourCombinations());

    const expected: Array<[number, string, string]> = [
      [0, DISABLE_NOTE, STOP_FORCING_NOTE],
      [1, DISABLE_NOTE, FORCE_NOTE],
      [2, ENABLE_NOTE, STOP_FORCING_NOTE],
      [3, ENABLE_NOTE, FORCE_NOTE],
    ];
    for (const [index, enabledControl, forcedControl] of expected) {
      const item = itemAt(index);
      const shown = FLAG_LABELS.filter((label) => hasButton(item, label));
      expect(shown.sort()).toEqual([enabledControl, forcedControl].sort());
    }
  });

  it("a disabled, forced note shows both Enable note and Stop forcing note — the forced control stays visible — DoD-4", () => {
    stubBackend(() => notFoundResponse());
    renderGroup(readyLevel(memo(MEMO_C, { is_enabled: false, is_forced: true })));

    const item = itemAt(0);
    expect(button(item, ENABLE_NOTE)).toBeInTheDocument();
    expect(button(item, STOP_FORCING_NOTE)).toBeInTheDocument();
    expect(hasButton(item, DISABLE_NOTE)).toBe(false);
    expect(hasButton(item, FORCE_NOTE)).toBe(false);
  });
});

// ===========================================================================
describe("toggling the flags", () => {
  it("Disable then Enable on an enabled, forced note sends exactly one key each and ends on the forced line — DoD-5", async () => {
    const { calls } = serveNotes([memo(MEMO_A, { is_enabled: true, is_forced: true })]);
    renderGroup(readyLevel(memo(MEMO_A, { is_enabled: true, is_forced: true })));
    const user = newUser();

    await user.click(button(itemAt(0), DISABLE_NOTE));
    await waitFor(() => {
      expect(hasButton(itemAt(0), ENABLE_NOTE)).toBe(true);
    });
    expect(calls).toEqual([{ method: "PATCH", path: memoPath(MEMO_A), search: "", body: { is_enabled: false } }]);
    expect(button(itemAt(0), STOP_FORCING_NOTE)).toBeInTheDocument();
    expect(within(itemAt(0)).getByText(DISABLED_LINE)).toBeInTheDocument();

    await user.click(button(itemAt(0), ENABLE_NOTE));
    await waitFor(() => {
      expect(within(itemAt(0)).queryByText(FORCED_LINE)).not.toBeNull();
    });
    expect(calls).toEqual([
      { method: "PATCH", path: memoPath(MEMO_A), search: "", body: { is_enabled: false } },
      { method: "PATCH", path: memoPath(MEMO_A), search: "", body: { is_enabled: true } },
    ]);
    expect(button(itemAt(0), DISABLE_NOTE)).toBeInTheDocument();
    expect(button(itemAt(0), STOP_FORCING_NOTE)).toBeInTheDocument();
    expect(within(itemAt(0)).queryByText(DISABLED_LINE)).toBeNull();
  });

  it("the same sequence on an enabled, not-forced note ends on the searchable line — DoD-5", async () => {
    const { calls } = serveNotes([memo(MEMO_B, { is_enabled: true, is_forced: false })]);
    renderGroup(readyLevel(memo(MEMO_B, { is_enabled: true, is_forced: false })));
    const user = newUser();

    await user.click(button(itemAt(0), DISABLE_NOTE));
    await waitFor(() => {
      expect(hasButton(itemAt(0), ENABLE_NOTE)).toBe(true);
    });
    expect(button(itemAt(0), FORCE_NOTE)).toBeInTheDocument();
    expect(within(itemAt(0)).getByText(DISABLED_LINE)).toBeInTheDocument();

    await user.click(button(itemAt(0), ENABLE_NOTE));
    await waitFor(() => {
      expect(within(itemAt(0)).queryByText(SEARCHABLE_LINE)).not.toBeNull();
    });
    expect(calls).toEqual([
      { method: "PATCH", path: memoPath(MEMO_B), search: "", body: { is_enabled: false } },
      { method: "PATCH", path: memoPath(MEMO_B), search: "", body: { is_enabled: true } },
    ]);
    expect(button(itemAt(0), DISABLE_NOTE)).toBeInTheDocument();
    expect(button(itemAt(0), FORCE_NOTE)).toBeInTheDocument();
  });

  it("Force note on a disabled note sends exactly is_forced true and the note stays disabled — DoD-6", async () => {
    const { calls } = serveNotes([memo(MEMO_D, { is_enabled: false, is_forced: false })]);
    renderGroup(readyLevel(memo(MEMO_D, { is_enabled: false, is_forced: false })));
    const user = newUser();

    await user.click(button(itemAt(0), FORCE_NOTE));
    await waitFor(() => {
      expect(hasButton(itemAt(0), STOP_FORCING_NOTE)).toBe(true);
    });
    expect(calls).toEqual([{ method: "PATCH", path: memoPath(MEMO_D), search: "", body: { is_forced: true } }]);
    expect(button(itemAt(0), ENABLE_NOTE)).toBeInTheDocument();
    expect(within(itemAt(0)).getByText(DISABLED_LINE)).toBeInTheDocument();
    expect(within(itemAt(0)).queryByText(FORCED_LINE)).toBeNull();
  });

  it("while a flag PATCH is pending both flag buttons are disabled and nothing changes; after the response they are enabled again — DoD-7", async () => {
    const { calls, held } = stubHeld();
    const row = memo(MEMO_B, { is_enabled: true, is_forced: false });
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
    expect(hasButton(itemAt(0), ENABLE_NOTE)).toBe(false);
    expect(hasButton(itemAt(0), STOP_FORCING_NOTE)).toBe(false);
    expect(within(itemAt(0)).getByText(SEARCHABLE_LINE)).toBeInTheDocument();

    await act(async () => {
      held[0].resolve(jsonResponse({ ...row, is_enabled: false, updated_at: stampAt(1) }, 200));
    });
    await waitFor(() => {
      expect(button(itemAt(0), ENABLE_NOTE)).toBeEnabled();
    });
    expect(button(itemAt(0), FORCE_NOTE)).toBeEnabled();
    expect(within(itemAt(0)).getByText(DISABLED_LINE)).toBeInTheDocument();
  });
});

// ===========================================================================
describe("editing a saved note", () => {
  it("typing and blurring sends exactly PATCH { body: <typed text> } — DoD-8", async () => {
    const { calls } = serveNotes([memo(MEMO_A, { body: BODY_A }), memo(MEMO_B, { body: BODY_B, sort_key: 1 })]);
    renderGroup(readyLevel(memo(MEMO_A, { body: BODY_A }), memo(MEMO_B, { body: BODY_B, sort_key: 1 })));
    const typed = "Mira now trusts the harbour master.";

    fireEvent.change(noteBox(itemAt(1)), { target: { value: typed } });
    fireEvent.blur(noteBox(itemAt(1)));

    await waitFor(() => {
      expect(calls).toHaveLength(1);
    });
    expect(calls).toEqual([{ method: "PATCH", path: memoPath(MEMO_B), search: "", body: { body: typed } }]);
    await settle();
    expect(noteBox(itemAt(1)).value).toBe(typed);
  });

  it("blurring a textbox whose text is unchanged sends nothing — DoD-8", async () => {
    const { calls } = serveNotes([memo(MEMO_A, { body: BODY_A })]);
    renderGroup(readyLevel(memo(MEMO_A, { body: BODY_A })));

    fireEvent.blur(noteBox(itemAt(0)));
    await settle();

    expect(calls).toEqual([]);
  });

  it("clearing a saved note and blurring sends DELETE with no PATCH and no confirm; after the 204 its listitem is gone — DoD-9", async () => {
    const { calls } = serveNotes([memo(MEMO_A, { body: BODY_A }), memo(MEMO_B, { body: BODY_B, sort_key: 1 })]);
    renderGroup(readyLevel(memo(MEMO_A, { body: BODY_A }), memo(MEMO_B, { body: BODY_B, sort_key: 1 })));

    fireEvent.change(noteBox(itemAt(0)), { target: { value: "" } });
    fireEvent.blur(noteBox(itemAt(0)));

    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => {
      expect(items()).toHaveLength(1);
    });
    expect(calls).toEqual([{ method: "DELETE", path: memoPath(MEMO_A), search: "", body: undefined }]);
    expect(noteBox(itemAt(0)).value).toBe(BODY_B);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

// ===========================================================================
describe("failures render inside the note's listitem", () => {
  it("a failed body save shows Could not save the note. in that listitem, keeps the typed text, and notifies nothing — DoD-10", async () => {
    serveNotes([memo(MEMO_A, { body: BODY_A }), memo(MEMO_B, { body: BODY_B, sort_key: 1 })], { patch: true });
    renderGroup(readyLevel(memo(MEMO_A, { body: BODY_A }), memo(MEMO_B, { body: BODY_B, sort_key: 1 })));
    const typed = "A rewrite that will not land.";

    fireEvent.change(noteBox(itemAt(0)), { target: { value: typed } });
    fireEvent.blur(noteBox(itemAt(0)));

    await waitFor(() => {
      expect(within(itemAt(0)).queryByText(SAVE_FAILURE)).not.toBeNull();
    });
    expect(noteBox(itemAt(0)).value).toBe(typed);
    expect(within(itemAt(1)).queryByText(SAVE_FAILURE)).toBeNull();
    expect(screen.getAllByText(SAVE_FAILURE)).toHaveLength(1);
    expect(document.querySelector(NOTIFICATION)).toBeNull();
  });

  it("a failed delete shows Could not delete the note. and the listitem stays — DoD-10", async () => {
    serveNotes([memo(MEMO_A, { body: BODY_A }), memo(MEMO_B, { body: BODY_B, sort_key: 1 })], { delete: true });
    renderGroup(readyLevel(memo(MEMO_A, { body: BODY_A }), memo(MEMO_B, { body: BODY_B, sort_key: 1 })));

    fireEvent.change(noteBox(itemAt(0)), { target: { value: "" } });
    fireEvent.blur(noteBox(itemAt(0)));

    await waitFor(() => {
      expect(within(itemAt(0)).queryByText(DELETE_FAILURE)).not.toBeNull();
    });
    expect(items()).toHaveLength(2);
    expect(within(itemAt(1)).queryByText(DELETE_FAILURE)).toBeNull();
    expect(document.querySelector(NOTIFICATION)).toBeNull();
  });

  it("a failed toggle shows Could not change the note. in that listitem — DoD-10", async () => {
    serveNotes([memo(MEMO_A, { body: BODY_A }), memo(MEMO_B, { body: BODY_B, sort_key: 1 })], { patch: true });
    renderGroup(readyLevel(memo(MEMO_A, { body: BODY_A }), memo(MEMO_B, { body: BODY_B, sort_key: 1 })));
    const user = newUser();

    await user.click(button(itemAt(1), FORCE_NOTE));

    await waitFor(() => {
      expect(within(itemAt(1)).queryByText(CHANGE_FAILURE)).not.toBeNull();
    });
    expect(within(itemAt(0)).queryByText(CHANGE_FAILURE)).toBeNull();
    expect(document.querySelector(NOTIFICATION)).toBeNull();
  });
});

// ===========================================================================
describe("the new note", () => {
  async function expectBlankNewNoteDropped(blankText: string | null): Promise<void> {
    const { calls } = serveNotes([memo(MEMO_A, { body: BODY_A })]);
    renderGroup(readyLevel(memo(MEMO_A, { body: BODY_A })));
    const user = newUser();

    await user.click(newNoteButton());
    await waitFor(() => {
      expect(items()).toHaveLength(2);
    });
    if (blankText !== null) {
      fireEvent.change(noteBox(lastItem()), { target: { value: blankText } });
    }
    fireEvent.blur(noteBox(lastItem()));

    await waitFor(() => {
      expect(items()).toHaveLength(1);
    });
    expect(newNoteButton()).toBeEnabled();
    expect(noteBox(itemAt(0)).value).toBe(BODY_A);
    await settle();
    expect(calls).toEqual([]);
  }

  it("New note adds a last listitem with one empty Note textbox, no flag controls, no reach line, and disables New note — DoD-11", async () => {
    const { calls } = serveNotes([memo(MEMO_A, { body: BODY_A })]);
    renderGroup(readyLevel(memo(MEMO_A, { body: BODY_A })));
    const user = newUser();

    expect(newNoteButton()).toBeEnabled();
    await user.click(newNoteButton());

    await waitFor(() => {
      expect(items()).toHaveLength(2);
    });
    const fresh = lastItem();
    const boxes = within(fresh).getAllByRole("textbox");
    expect(boxes).toHaveLength(1);
    expect(noteBox(fresh).value).toBe("");
    for (const label of FLAG_LABELS) {
      expect(hasButton(fresh, label)).toBe(false);
    }
    for (const line of REACH_LINES) {
      expect(within(fresh).queryByText(line)).toBeNull();
    }
    expect(newNoteButton()).toBeDisabled();
    expect(noteBox(itemAt(0)).value).toBe(BODY_A);
    await settle();
    expect(calls).toEqual([]);
  });

  it("blurring the new note while empty removes it, re-enables New note and sends no request — DoD-11", async () => {
    await expectBlankNewNoteDropped(null);
  });

  it("blurring the new note holding only spaces and a newline removes it, re-enables New note and sends no request — DoD-11", async () => {
    await expectBlankNewNoteDropped("  \n");
  });

  it("typing Plan and blurring POSTs exactly scope, scope_id and body; after the 201 the last listitem is a searchable saved note and New note is enabled — DoD-12", async () => {
    const { calls } = serveNotes([memo(MEMO_A, { body: BODY_A })]);
    renderGroup(readyLevel(memo(MEMO_A, { body: BODY_A })));
    const user = newUser();

    await user.click(newNoteButton());
    await waitFor(() => {
      expect(items()).toHaveLength(2);
    });
    fireEvent.change(noteBox(lastItem()), { target: { value: "Plan" } });
    fireEvent.blur(noteBox(lastItem()));

    await waitFor(() => {
      expect(hasButton(lastItem(), DISABLE_NOTE)).toBe(true);
    });
    expect(calls).toEqual([
      {
        method: "POST",
        path: "/api/memos",
        search: "",
        body: { scope: "character", scope_id: CHARACTER_ID, body: "Plan" },
      },
    ]);
    expect(items()).toHaveLength(2);
    const saved = lastItem();
    expect(noteBox(saved).value).toBe("Plan");
    expect(button(saved, DISABLE_NOTE)).toBeInTheDocument();
    expect(button(saved, FORCE_NOTE)).toBeInTheDocument();
    expect(within(saved).getByText(SEARCHABLE_LINE)).toBeInTheDocument();
    expect(newNoteButton()).toBeEnabled();
  });

  it("at the user level the POST carries scope user and a null scope_id, and no flag keys — DoD-12", async () => {
    const { calls } = serveNotes([]);
    const state = new MemoLevelState("user", null);
    populateMemoLevel(state, []);
    renderGroup(state, { title: "Your notes" });
    const user = newUser();

    await user.click(button(region("Your notes"), NEW_NOTE));
    const fresh = await within(region("Your notes")).findByRole("textbox", { name: NOTE_LABEL });
    fireEvent.change(fresh, { target: { value: "Plan" } });
    fireEvent.blur(fresh);

    await waitFor(() => {
      expect(calls).toHaveLength(1);
    });
    expect(calls).toEqual([
      { method: "POST", path: "/api/memos", search: "", body: { scope: "user", scope_id: null, body: "Plan" } },
    ]);
    await waitFor(() => {
      expect(within(region("Your notes")).queryByText(SEARCHABLE_LINE)).not.toBeNull();
    });
    expect(button(region("Your notes"), NEW_NOTE)).toBeEnabled();
  });

  it("a failed create keeps the new listitem with its typed text and Could not save the note., and New note stays disabled — DoD-13", async () => {
    serveNotes([memo(MEMO_A, { body: BODY_A })], { post: true });
    renderGroup(readyLevel(memo(MEMO_A, { body: BODY_A })));
    const user = newUser();

    await user.click(newNoteButton());
    await waitFor(() => {
      expect(items()).toHaveLength(2);
    });
    fireEvent.change(noteBox(lastItem()), { target: { value: "Plan" } });
    fireEvent.blur(noteBox(lastItem()));

    await waitFor(() => {
      expect(within(lastItem()).queryByText(SAVE_FAILURE)).not.toBeNull();
    });
    expect(items()).toHaveLength(2);
    expect(noteBox(lastItem()).value).toBe("Plan");
    expect(within(itemAt(0)).queryByText(SAVE_FAILURE)).toBeNull();
    expect(newNoteButton()).toBeDisabled();
    expect(document.querySelector(NOTIFICATION)).toBeNull();
  });
});

// ===========================================================================
describe("empty, loading and failed states", () => {
  it("a ready level with no notes shows No notes yet. and an enabled New note, and no listitem — DoD-14", () => {
    stubBackend(() => notFoundResponse());
    renderGroup(readyLevel());

    const group = region();
    expect(within(group).getByText(EMPTY_LINE)).toBeInTheDocument();
    expect(button(group, NEW_NOTE)).toBeEnabled();
    expect(within(group).queryAllByRole("listitem")).toHaveLength(0);
  });

  it("a loading state shows a loader and no New note — DoD-15", async () => {
    const { calls } = stubHeld();
    const state = new MemoLevelState("character", CHARACTER_ID);
    void loadMemoLevel(state);
    await waitFor(() => {
      expect(calls).toHaveLength(1);
    });

    renderGroup(state);

    expect(region().querySelector(LOADER)).not.toBeNull();
    expect(screen.queryByRole("button", { name: NEW_NOTE })).toBeNull();
    expect(screen.queryByText(LOAD_FAILED)).toBeNull();
  });

  it("a failed state shows Could not load notes and Retry, and pressing Retry calls onRetry once — DoD-15", async () => {
    stubBackend(() => serverError());
    const state = new MemoLevelState("character", CHARACTER_ID);
    await loadMemoLevel(state);

    const { onRetry } = renderGroup(state);
    const group = region();
    expect(within(group).getByText(LOAD_FAILED)).toBeInTheDocument();
    const retry = button(group, RETRY);
    expect(onRetry).not.toHaveBeenCalled();

    await newUser().click(retry);

    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});

// ===========================================================================
describe("the flush on unmount", () => {
  it("unmounting after typing into a saved note without blurring PATCHes that note's new body — DoD-16", async () => {
    const { calls } = serveNotes([memo(MEMO_A, { body: BODY_A }), memo(MEMO_B, { body: BODY_B, sort_key: 1 })]);
    const { unmount } = renderGroup(
      readyLevel(memo(MEMO_A, { body: BODY_A }), memo(MEMO_B, { body: BODY_B, sort_key: 1 })),
    );
    const typed = "Typed but never blurred.";

    fireEvent.change(noteBox(itemAt(0)), { target: { value: typed } });
    await settle();
    expect(calls).toEqual([]);

    unmount();

    await waitFor(() => {
      expect(calls).toHaveLength(1);
    });
    await settle();
    expect(calls).toEqual([{ method: "PATCH", path: memoPath(MEMO_A), search: "", body: { body: typed } }]);
  });

  it("unmounting with a new note holding Later POSTs it — DoD-16", async () => {
    const { calls } = serveNotes([memo(MEMO_A, { body: BODY_A })]);
    const { unmount } = renderGroup(readyLevel(memo(MEMO_A, { body: BODY_A })));
    const user = newUser();

    await user.click(newNoteButton());
    await waitFor(() => {
      expect(items()).toHaveLength(2);
    });
    fireEvent.change(noteBox(lastItem()), { target: { value: "Later" } });
    await settle();
    expect(calls).toEqual([]);

    unmount();

    await waitFor(() => {
      expect(calls).toHaveLength(1);
    });
    await settle();
    expect(calls).toEqual([
      {
        method: "POST",
        path: "/api/memos",
        search: "",
        body: { scope: "character", scope_id: CHARACTER_ID, body: "Later" },
      },
    ]);
  });

  it("unmounting with nothing changed sends nothing — DoD-16", async () => {
    const { calls } = serveNotes([memo(MEMO_A, { body: BODY_A }), memo(MEMO_B, { body: BODY_B, sort_key: 1 })]);
    const { unmount } = renderGroup(
      readyLevel(memo(MEMO_A, { body: BODY_A }), memo(MEMO_B, { body: BODY_B, sort_key: 1 })),
    );

    unmount();
    await settle();

    expect(calls).toEqual([]);
  });
});
