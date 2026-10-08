// Feature 015, step 009 — the character page's "Notes" section (DoD-1..DoD-3).
// DoD-4..DoD-6 are the section's place on the character screen and live in
// CharacterScreen.test.tsx (with a route-level clause in App.test.tsx); DoD-7 is the amendment
// of those two files; DoD-8 is [manual/live] and carries no test.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 009.context.md and the feature's context.md: D1 (one character-level group titled "Notes"),
// D5 (save on focus loss, never optimistic, nothing refetched after a mutation), R3, the UI
// strings table and the memos wire contract (`GET /api/memos?scope=character&scope_id=<id>`,
// `POST /api/memos` with `{ scope, scope_id, body }`, 201 the created row).
//
// Recognition conventions (for the verifier):
// - The section renders alone inside `AppProviders`; the group is the region named "Notes",
//   and every assertion about what it shows goes through `within(notesRegion())`, then
//   `listitem`s for notes.
// - `src/shared/MarkdownEditor` is replaced by the labelled-`<textarea>` stub of step 007's
//   MemoLevelGroup.test.tsx (id from React's `useId`, since several editors labelled "Note" are
//   on screen at once). A note's text is its textarea's value. Focus loss is `fireEvent.blur`;
//   typing is `fireEvent.change`.
// - A notification: `.mantine-Notification-root`.
// - `fetch` is stubbed per test; requests are recorded by exact method + pathname + query
//   string with the parsed JSON body, so whole-object comparison catches a stray key.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ChangeEvent, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CharacterNotesSection } from "../../src/app/CharacterNotesSection";
import type { Memo } from "../../src/app/memosApi";
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
          // 033 step 002: autoFocus is passed through (React focuses on mount) and mirrored.
          autoFocus: props.autoFocus === true,
          "data-autofocus": props.autoFocus === true ? "true" : "false",
          onChange: (event: ChangeEvent<HTMLTextAreaElement>) => props.onChange(event.target.value),
        }),
        // fast 012: the toolbar-actions prop renders inside the stub's root, as the real
        // editor renders it inside its toolbar (so focus moving to a flag stays in the note).
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
const NOTES = "Notes";
const NOTE_LABEL = "Note";
const NEW_NOTE = "New note";
// 033 step 002 (D6): the draft's icon buttons.
const SAVE_NEW_NOTE = "Save new note";
const CANCEL_NEW_NOTE = "Cancel new note";
const SAVE_FAILURE = "Could not save the note.";
const ORDER_PATH = "/api/memos/order";
const ENABLE_NOTE = "Enable note";
const DISABLE_NOTE = "Disable note";
const EMPTY_LINE = "No notes yet.";
const SEARCHABLE_LINE = "Searchable: found only when the assistant searches.";
const LOAD_FAILED = "Could not load notes";
const RETRY = "Retry";

const NOTIFICATION = ".mantine-Notification-root";

// ---------------------------------------------------------------- fixtures
/** Past Number.MAX_SAFE_INTEGER, so a coerced id would show in the query and the POST body. */
const CHARACTER_ID = "9007199254740993";
const CREATED_ID = "9007199254740999";

const MEMOS_PATH = "/api/memos";
const LISTING_SEARCH = `?scope=character&scope_id=${CHARACTER_ID}`;

const STAMP = "2026-10-02T09:26:53.000000+00:00";
const CREATED_STAMP = "2026-10-02T09:40:00.000000+00:00";

const TYPED = "Voice: dry";

/** A character-level wire Memo with all nine keys. */
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

const BODY_1 = "Mira limps on her left leg.";
const BODY_2 = "She owes the harbour master money.";
const BODY_3 = "Never mention the brother.";

/** The payload's order is the server's order (`sort_key, id`); the client never reorders. */
const PAYLOAD: Memo[] = [
  memo("7250000000000000201", BODY_1),
  memo("7250000000000000202", BODY_2, { sort_key: 1, is_enabled: false }),
  memo("7250000000000000203", BODY_3, { sort_key: 2, is_forced: true }),
];

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

function notFoundResponse(): Response {
  return envelope("character_not_found", 404);
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

/** The character's notes listing, by exact method + path + query. */
function isListing(request: Seen): boolean {
  return request.method === "GET" && request.path === MEMOS_PATH && request.search === LISTING_SEARCH;
}

function listings(calls: Seen[]): Seen[] {
  return calls.filter((call) => call.method === "GET" && call.path === MEMOS_PATH);
}

/**
 * The listing answers `memos`; `POST /api/memos` answers 201 with the created row (enabled, not
 * forced) from the sent scope, scope_id and body. Everything else 404s.
 */
function serveNotes(memos: Memo[]) {
  return stubBackend((request) => {
    if (isListing(request)) return jsonResponse({ memos }, 200);
    if (request.method === "POST" && request.path === MEMOS_PATH && request.search === "") {
      const sent = request.body as { scope: "character"; scope_id: string; body: string };
      return jsonResponse(
        memo(CREATED_ID, sent.body, {
          scope: sent.scope,
          scope_id: sent.scope_id,
          sort_key: 0,
          created_at: CREATED_STAMP,
          updated_at: CREATED_STAMP,
        }),
        201,
      );
    }
    return notFoundResponse();
  });
}

async function settle(): Promise<void> {
  await act(async () => {
    for (let round = 0; round < 6; round += 1) await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
    for (let round = 0; round < 6; round += 1) await Promise.resolve();
  });
}

function newUser() {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

// ---------------------------------------------------------------- render + queries
function renderSection(characterId: string = CHARACTER_ID) {
  return render(
    <AppProviders>
      <CharacterNotesSection characterId={characterId} />
    </AppProviders>,
  );
}

function notesRegion(): HTMLElement {
  return screen.getByRole("region", { name: NOTES });
}

function items(): HTMLElement[] {
  return within(notesRegion()).queryAllByRole("listitem");
}

/** Each listed note's text, in document order (each note's "Note" editor value). */
function bodies(): string[] {
  return within(notesRegion())
    .queryAllByRole("textbox", { name: NOTE_LABEL })
    .map((box) => (box as HTMLTextAreaElement).value);
}

// ===========================================================================
describe("the character's notes listing (UC-046, R3)", () => {
  it("requests exactly GET /api/memos?scope=character&scope_id=<C> — DoD-1", async () => {
    const { calls } = serveNotes(PAYLOAD);
    renderSection();
    await waitFor(() => {
      expect(bodies()).toHaveLength(PAYLOAD.length);
    });
    await settle();

    expect(calls).toEqual([{ method: "GET", path: MEMOS_PATH, search: LISTING_SEARCH, body: undefined }]);
  });

  it("renders a Notes region with a Notes heading listing the payload's notes in order — DoD-1", async () => {
    serveNotes(PAYLOAD);
    renderSection();
    await waitFor(() => {
      expect(bodies()).toHaveLength(PAYLOAD.length);
    });

    expect(within(notesRegion()).getByRole("heading", { name: NOTES })).toBeInTheDocument();
    expect(bodies()).toEqual([BODY_1, BODY_2, BODY_3]);
    expect(items()).toHaveLength(PAYLOAD.length);
  });

  it("the disabled note is listed among them with Enable note — DoD-1", async () => {
    serveNotes(PAYLOAD);
    renderSection();
    await waitFor(() => {
      expect(bodies()).toHaveLength(PAYLOAD.length);
    });

    const disabledItem = items()[1];
    expect(within(disabledItem).getByRole("textbox", { name: NOTE_LABEL })).toHaveValue(BODY_2);
    expect(within(disabledItem).getByRole("button", { name: ENABLE_NOTE })).toBeInTheDocument();
    expect(within(items()[0]).queryByRole("button", { name: ENABLE_NOTE })).toBeNull();
  });
});

// ===========================================================================
describe("an empty character level and a new note (US-050.AC-1, US-053.AC-1, D5)", () => {
  it("an empty listing shows No notes yet. in the region — DoD-2", async () => {
    serveNotes([]);
    renderSection();

    await waitFor(() => {
      expect(within(notesRegion()).queryByText(EMPTY_LINE)).not.toBeNull();
    });
    expect(items()).toHaveLength(0);
  });

  it("(amended by fast 012 DoD-6: focus leaving the draft saves it; no Save new note) New note, typing Voice: dry and blurring POSTs exactly scope, scope_id and body; the saved note shows the searchable reach; no listing follows — DoD-2", async () => {
    const { calls } = serveNotes([]);
    renderSection();
    await waitFor(() => {
      expect(within(notesRegion()).queryByText(EMPTY_LINE)).not.toBeNull();
    });

    const user = newUser();
    await user.click(within(notesRegion()).getByRole("button", { name: NEW_NOTE }));
    await waitFor(() => {
      expect(items()).toHaveLength(1);
    });
    const editor = within(items()[0]).getByRole("textbox", { name: NOTE_LABEL });
    fireEvent.change(editor, { target: { value: TYPED } });
    fireEvent.blur(editor);

    await waitFor(() => {
      expect(calls.filter((call) => call.method === "POST")).toHaveLength(1);
    });
    const postIndex = calls.findIndex((call) => call.method === "POST");
    expect(calls[postIndex]).toEqual({
      method: "POST",
      path: MEMOS_PATH,
      search: "",
      body: { scope: "character", scope_id: CHARACTER_ID, body: TYPED },
    });

    // After the 201 the note is the saved row: it carries its flag controls and its reach line.
    await waitFor(() => {
      expect(within(items()[0]).queryByRole("button", { name: DISABLE_NOTE })).not.toBeNull();
    });
    await settle();
    expect(items()).toHaveLength(1);
    expect(bodies()).toEqual([TYPED]);
    expect(within(items()[0]).getByText(SEARCHABLE_LINE)).toBeInTheDocument();

    // Never refetched after a mutation.
    expect(listings(calls.slice(postIndex + 1))).toEqual([]);
    expect(listings(calls)).toHaveLength(1);
  });
});

// ===========================================================================
describe("a failed load (no notification)", () => {
  type FailureCase = [label: string, answer: () => Response];

  const FAILURES: FailureCase[] = [
    ["a 500 envelope", serverError],
    [
      "a transport failure",
      () => {
        throw new TypeError("Failed to fetch");
      },
    ],
  ];

  it.each(FAILURES)(
    "%s shows Could not load notes and Retry in the Notes region, with no notification — DoD-3",
    async (_label, answer) => {
      stubBackend(() => answer());
      renderSection();

      await waitFor(() => {
        expect(within(notesRegion()).queryByText(LOAD_FAILED)).not.toBeNull();
      });
      expect(within(notesRegion()).getByRole("button", { name: RETRY })).toBeInTheDocument();
      await settle();
      expect(document.querySelector(NOTIFICATION)).toBeNull();
    },
  );

  it("Retry requests the listing again and, on success, the notes render — DoD-3", async () => {
    let failNext = true;
    const { calls } = stubBackend((request) => {
      if (isListing(request)) {
        if (failNext) {
          failNext = false;
          return serverError();
        }
        return jsonResponse({ memos: PAYLOAD }, 200);
      }
      return notFoundResponse();
    });
    renderSection();
    await waitFor(() => {
      expect(within(notesRegion()).queryByText(LOAD_FAILED)).not.toBeNull();
    });
    expect(listings(calls)).toHaveLength(1);

    await newUser().click(within(notesRegion()).getByRole("button", { name: RETRY }));

    await waitFor(() => {
      expect(bodies()).toEqual([BODY_1, BODY_2, BODY_3]);
    });
    const reads = listings(calls);
    expect(reads).toHaveLength(2);
    for (const read of reads) {
      expect(read.search).toBe(LISTING_SEARCH);
    }
    expect(within(notesRegion()).queryByText(LOAD_FAILED)).toBeNull();
    expect(document.querySelector(NOTIFICATION)).toBeNull();
  });
});

// ===========================================================================
// Feature 018, step 005 — the notes as a reorderable grid in the section's own drag context
// (DoD-5, DoD-6). Expected behaviour comes from 018's step file 005.notes-grid.md (Interface
// intent for CharacterNotesSection: grid + reorderable inside its own DndContext with the
// shared sensors and the builder's announcements for one group "Notes") and 018 context.md D8,
// which carries 016 D8 (cards named "Note <n> of <total>", announcements by position and group,
// never by id). Every 015 009 assertion above is kept unedited and is DoD-6's main half; the
// archived-character and character-to-character cases of 015 009 live in
// CharacterScreen.test.tsx (outside this step's Test files) and are not edited here.
// Keyboard activation is Space keydown on the focused card; dnd-kit's announcement live
// region (role "status") is read afterwards. Movement is never exercised (jsdom rects).
// ===========================================================================
function pressSpace(target: HTMLElement): void {
  fireEvent.keyDown(target, { code: "Space", key: " " });
}

/** dnd-kit's announcement live region(s): role "status" elements in the document. */
function liveRegionText(): string {
  return screen
    .queryAllByRole("status", { hidden: true })
    .map((element) => element.textContent ?? "")
    .join(" ")
    .trim();
}

const PAYLOAD_IDS = PAYLOAD.map((row) => row.id);

describe("the character's notes as a reorderable list (US-096.AC-1, US-102, D8; 033 D6 list layout)", () => {
  it("three served notes render in the Notes region as three listitems named Note 1 of 3, Note 2 of 3, Note 3 of 3 in served order, each focusable — DoD-5", async () => {
    serveNotes(PAYLOAD);
    renderSection();
    await waitFor(() => {
      expect(bodies()).toHaveLength(PAYLOAD.length);
    });

    const listed = items();
    expect(listed).toHaveLength(3);
    const expected: Array<[string, string]> = [
      ["Note 1 of 3", BODY_1],
      ["Note 2 of 3", BODY_2],
      ["Note 3 of 3", BODY_3],
    ];
    expected.forEach(([name, body], index) => {
      const item = listed[index];
      expect(item).toHaveAccessibleName(name);
      expect(within(notesRegion()).getByRole("listitem", { name })).toBe(item);
      expect(item.tabIndex).toBe(0);
      expect(within(item).getByRole("textbox", { name: NOTE_LABEL })).toHaveValue(body);
    });
  });

  it("focusing the first note and pressing Space fills the live region with a non-empty announcement holding no memo id — DoD-5", async () => {
    serveNotes(PAYLOAD);
    renderSection();
    await waitFor(() => {
      expect(bodies()).toHaveLength(PAYLOAD.length);
    });
    const card = items()[0];

    card.focus();
    expect(document.activeElement).toBe(card);
    pressSpace(card);

    await waitFor(() => {
      expect(liveRegionText()).not.toBe("");
    });
    const message = liveRegionText();
    for (const id of [...PAYLOAD_IDS, CHARACTER_ID]) {
      expect(message).not.toContain(id);
    }
    // The builder is fed the one group "Notes": the note is named by position and that title.
    expect(message).toMatch(/\b1\b/);
    expect(message).toContain(NOTES);
  });
});

describe("015 009's behaviour kept in the list (US-050.AC-1, D8)", () => {
  const OTHER_ID = "9007199254740995";
  const OTHER_SEARCH = `?scope=character&scope_id=${OTHER_ID}`;
  const OTHER_BODY = "Brann keeps a ledger of debts.";

  it("re-keyed for another character, the section requests that character's listing exactly and lists only its notes — DoD-6", async () => {
    const { calls } = stubBackend((request) => {
      if (isListing(request)) return jsonResponse({ memos: PAYLOAD }, 200);
      if (request.method === "GET" && request.path === MEMOS_PATH && request.search === OTHER_SEARCH) {
        return jsonResponse(
          { memos: [memo("7250000000000000209", OTHER_BODY, { scope_id: OTHER_ID })] },
          200,
        );
      }
      return notFoundResponse();
    });
    const { rerender } = render(
      <AppProviders>
        <CharacterNotesSection key={CHARACTER_ID} characterId={CHARACTER_ID} />
      </AppProviders>,
    );
    await waitFor(() => {
      expect(bodies()).toEqual([BODY_1, BODY_2, BODY_3]);
    });

    rerender(
      <AppProviders>
        <CharacterNotesSection key={OTHER_ID} characterId={OTHER_ID} />
      </AppProviders>,
    );

    await waitFor(() => {
      expect(bodies()).toEqual([OTHER_BODY]);
    });
    await settle();
    expect(items()).toHaveLength(1);
    expect(items()[0]).toHaveAccessibleName("Note 1 of 1");
    expect(listings(calls).map((call) => call.search)).toEqual([LISTING_SEARCH, OTHER_SEARCH]);
  });
});

// ===========================================================================
// Fast feature 012 (supersedes 033 step 002's Save / Cancel draft) — the Notes section's
// header '+', the inline draft that saves when focus leaves it, no Save / Cancel buttons, and
// the saved notes' flags passed to the editor as its toolbar actions. Expected behaviour comes
// from docs/plans/fast/012.notes-autosave-toolbar-flags/plan.md (Interface intent, DoD-3..DoD-8,
// DoD-10, DoD-13) and its context.md. 033 step 002's DoD-2 (header '+') and DoD-10 (keyboard
// reorder) still hold and are kept below, re-tagged.
// - "Focus in its editor": the MarkdownEditor stub passes `autoFocus` to its textarea (React
//   focuses it on mount) and mirrors it as `data-autofocus`.
// - The draft is the first listitem while "New note" is disabled (it carries no flag button).
// - Focus leaving is `fireEvent.blur` on the textarea (relatedTarget null).
// - The stub renders `toolbarActions` inside its root as `[data-testid="stub-toolbar-actions"]`.
// - The full keyboard reorder gives each list row a distinct, stacked client rect (jsdom
//   rects are all zero otherwise), then Space / ArrowDown / Space on the first card.
// ===========================================================================
function headerNewNote(): HTMLElement {
  return within(notesRegion()).getByRole("button", { name: NEW_NOTE });
}

/** The open draft: the first listitem while "New note" is disabled; it has no flag button. */
function queryDraft(): HTMLElement | undefined {
  const plus = within(notesRegion()).queryByRole("button", { name: NEW_NOTE });
  if (plus === null || !(plus as HTMLButtonElement).disabled) return undefined;
  const first = items()[0];
  if (first === undefined) return undefined;
  if (within(first).queryByRole("button", { name: DISABLE_NOTE }) !== null) return undefined;
  if (within(first).queryByRole("button", { name: ENABLE_NOTE }) !== null) return undefined;
  return first;
}

function draft(): HTMLElement {
  const found = queryDraft();
  if (found === undefined) throw new Error("no new-note draft in the Notes region");
  return found;
}

function draftEditor(): HTMLTextAreaElement {
  return within(draft()).getByRole("textbox", { name: NOTE_LABEL }) as HTMLTextAreaElement;
}

function noSaveOrCancel(): void {
  expect(screen.queryByRole("button", { name: SAVE_NEW_NOTE })).toBeNull();
  expect(screen.queryByRole("button", { name: CANCEL_NEW_NOTE })).toBeNull();
}

function precedes(first: Node, second: Node): boolean {
  return (first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

/** Every request that is not the section's own notes listing. */
function nonListing(calls: Seen[]): Seen[] {
  return calls.filter((call) => !isListing(call));
}

type HeldResponse = { promise: Promise<Response>; resolve: (value: Response) => void };

function heldResponse(): HeldResponse {
  let resolve: (value: Response) => void = () => undefined;
  const promise = new Promise<Response>((ok) => {
    resolve = ok;
  });
  return { promise, resolve };
}

async function renderReady(memos: Memo[]) {
  const server = serveNotes(memos);
  renderSection();
  await waitFor(() => {
    if (memos.length === 0) {
      expect(within(notesRegion()).queryByText(EMPTY_LINE)).not.toBeNull();
    } else {
      expect(bodies()).toHaveLength(memos.length);
    }
  });
  return server;
}

async function openDraft(user: ReturnType<typeof newUser>, savedCount: number): Promise<void> {
  await user.click(headerNewNote());
  await waitFor(() => {
    expect(items()).toHaveLength(savedCount + 1);
  });
}

describe("fast 012 — the Notes header '+' (033 step 002 DoD-2 kept)", () => {
  it("one New note icon button sits in the section header beside the Notes heading, before the list, and no labelled New note button renders below the list; no Save / Cancel new note — DoD-3, DoD-5", async () => {
    await renderReady(PAYLOAD);
    const region = notesRegion();
    const heading = within(region).getByRole("heading", { name: NOTES });

    const buttons = within(region).getAllByRole("button", { name: NEW_NOTE });
    expect(buttons).toHaveLength(1);
    const plus = buttons[0];
    // Icon-only: the label is the accessible name, not visible button text.
    expect(plus.textContent ?? "").not.toContain(NEW_NOTE);
    expect(within(region).queryByText(NEW_NOTE, { selector: "button, button *" })).toBeNull();

    // In the header, beside the heading — the heading's own row, which does not hold the list.
    const list = items()[0].closest("ul");
    expect(list).not.toBeNull();
    const header = heading.parentElement;
    expect(header).not.toBeNull();
    expect(header?.contains(plus)).toBe(true);
    expect(header?.contains(list as HTMLElement)).toBe(false);
    expect(precedes(heading, plus)).toBe(true);
    expect(precedes(plus, list as HTMLElement)).toBe(true);
    for (const item of items()) {
      expect(item.contains(plus)).toBe(false);
    }
    expect(plus).toBeEnabled();
    noSaveOrCancel();
  });

  it("an empty level shows No notes yet. with the header '+' and no labelled New note button — DoD-3", async () => {
    await renderReady([]);
    const region = notesRegion();
    const heading = within(region).getByRole("heading", { name: NOTES });

    const buttons = within(region).getAllByRole("button", { name: NEW_NOTE });
    expect(buttons).toHaveLength(1);
    expect(buttons[0].textContent ?? "").not.toContain(NEW_NOTE);
    expect(heading.parentElement?.contains(buttons[0])).toBe(true);
    expect(precedes(buttons[0], within(region).getByText(EMPTY_LINE))).toBe(true);
  });
});

describe("fast 012 — the inline new-note draft saves when focus leaves it", () => {
  it("activating '+' opens an empty draft as the first item, focused, with no flag buttons and no Save / Cancel new note; '+' is disabled while it is open — DoD-4, DoD-5", async () => {
    await renderReady(PAYLOAD);
    const user = newUser();

    await openDraft(user, PAYLOAD.length);

    const first = items()[0];
    const editor = within(first).getByRole("textbox", { name: NOTE_LABEL });
    expect(editor).toHaveValue("");
    expect(editor).toHaveAttribute("data-autofocus", "true");
    await waitFor(() => {
      expect(document.activeElement).toBe(editor);
    });
    expect(headerNewNote()).toBeDisabled();
    for (const label of [DISABLE_NOTE, ENABLE_NOTE, "Force note", "Stop forcing note"]) {
      expect(within(first).queryByRole("button", { name: label })).toBeNull();
    }
    noSaveOrCancel();
    // The saved notes follow the draft, in served order.
    expect(bodies()).toEqual(["", BODY_1, BODY_2, BODY_3]);
  });

  it("focus leaving the draft with text sends exactly one create for the character level; the new note is first, the draft closes and '+' is enabled again — DoD-6", async () => {
    const { calls } = await renderReady(PAYLOAD);
    const user = newUser();
    await openDraft(user, PAYLOAD.length);
    fireEvent.change(draftEditor(), { target: { value: TYPED } });

    fireEvent.blur(draftEditor());

    await waitFor(() => {
      expect(queryDraft()).toBeUndefined();
    });
    await waitFor(() => {
      expect(within(items()[0]).queryByRole("button", { name: DISABLE_NOTE })).not.toBeNull();
    });
    await settle();
    expect(nonListing(calls)).toEqual([
      {
        method: "POST",
        path: MEMOS_PATH,
        search: "",
        body: { scope: "character", scope_id: CHARACTER_ID, body: TYPED },
      },
    ]);
    expect(bodies()).toEqual([TYPED, BODY_1, BODY_2, BODY_3]);
    expect(items()).toHaveLength(PAYLOAD.length + 1);
    // The first item is now the saved note (it carries a saved note's flag control).
    expect(within(items()[0]).getByRole("button", { name: DISABLE_NOTE })).toBeInTheDocument();
    noSaveOrCancel();
    expect(headerNewNote()).toBeEnabled();
    expect(listings(calls)).toHaveLength(1);
  });

  it.each<[string, string | null]>([
    ["untouched (empty)", null],
    ["whitespace only", "   \n\t  "],
  ])(
    "focus leaving the draft with %s text sends no request, closes the draft and enables '+' again — DoD-7",
    async (_label, text) => {
      const { calls } = await renderReady(PAYLOAD);
      const user = newUser();
      await openDraft(user, PAYLOAD.length);
      if (text !== null) fireEvent.change(draftEditor(), { target: { value: text } });

      fireEvent.blur(draftEditor());

      await waitFor(() => {
        expect(items()).toHaveLength(PAYLOAD.length);
      });
      await settle();
      expect(nonListing(calls)).toEqual([]);
      expect(bodies()).toEqual([BODY_1, BODY_2, BODY_3]);
      expect(headerNewNote()).toBeEnabled();
    },
  );

  it("while the create is in flight no Save / Cancel new note renders; a failed create keeps the draft open with its typed text and shows the failure inside the draft — DoD-5, DoD-8", async () => {
    const held = heldResponse();
    const { calls } = stubBackend((request) => {
      if (isListing(request)) return jsonResponse({ memos: PAYLOAD }, 200);
      if (request.method === "POST" && request.path === MEMOS_PATH) return held.promise;
      return notFoundResponse();
    });
    renderSection();
    await waitFor(() => {
      expect(bodies()).toHaveLength(PAYLOAD.length);
    });
    const user = newUser();
    await openDraft(user, PAYLOAD.length);
    fireEvent.change(draftEditor(), { target: { value: TYPED } });

    fireEvent.blur(draftEditor());
    await waitFor(() => {
      expect(nonListing(calls)).toHaveLength(1);
    });
    expect(nonListing(calls)[0]).toEqual({
      method: "POST",
      path: MEMOS_PATH,
      search: "",
      body: { scope: "character", scope_id: CHARACTER_ID, body: TYPED },
    });
    noSaveOrCancel();

    await act(async () => {
      held.resolve(serverError());
    });
    await waitFor(() => {
      expect(within(items()[0]).queryByText(SAVE_FAILURE)).not.toBeNull();
    });
    await settle();

    expect(queryDraft()).toBe(items()[0]);
    expect(within(notesRegion()).getAllByText(SAVE_FAILURE)).toHaveLength(1);
    expect(draftEditor()).toHaveValue(TYPED);
    expect(items()).toHaveLength(PAYLOAD.length + 1);
    expect(nonListing(calls)).toHaveLength(1);
    expect(document.querySelector(NOTIFICATION)).toBeNull();
    expect(headerNewNote()).toBeDisabled();
    noSaveOrCancel();
  });
});

describe("fast 012 — a saved note's flags are the editor's toolbar actions (Notes section)", () => {
  it("each saved note's flag buttons render inside its editor's root (the stub's toolbar-actions content), and the reach line renders after the editor, outside it — DoD-10, DoD-12", async () => {
    await renderReady(PAYLOAD);

    const expected: Array<[number, string, string]> = [
      [0, DISABLE_NOTE, "Force note"],
      [1, ENABLE_NOTE, "Force note"],
      [2, DISABLE_NOTE, "Stop forcing note"],
    ];
    for (const [index, enabledLabel, forcedLabel] of expected) {
      const item = items()[index];
      const root = item.querySelector('[data-testid="markdown-editor-stub"]');
      expect(root).not.toBeNull();
      const actions = item.querySelector('[data-testid="stub-toolbar-actions"]');
      expect(actions).not.toBeNull();
      for (const label of [enabledLabel, forcedLabel]) {
        const flag = within(item).getByRole("button", { name: label });
        expect((actions as HTMLElement).contains(flag)).toBe(true);
      }
    }
    const searchable = within(items()[0]).getByText(SEARCHABLE_LINE);
    const root = items()[0].querySelector('[data-testid="markdown-editor-stub"]') as HTMLElement;
    expect(root.contains(searchable)).toBe(false);
    expect(precedes(root, searchable)).toBe(true);
  });
});

describe("fast 012 — character notes stay keyboard-reorderable in the list layout (US-102; 033 step 002 DoD-10 kept)", () => {
  /** Stack the list rows: row i of the notes list spans y = i*100 .. i*100+80. */
  function stackListRows(): void {
    const original = Element.prototype.getBoundingClientRect;
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
      const parent = this.parentElement;
      if (this.tagName === "LI" && parent !== null && parent.tagName === "UL") {
        const index = Array.from(parent.children).indexOf(this);
        const top = index * 100;
        return {
          x: 0,
          y: top,
          top,
          left: 0,
          right: 300,
          bottom: top + 80,
          width: 300,
          height: 80,
          toJSON: () => ({}),
        } as DOMRect;
      }
      return original.call(this);
    });
  }

  it("the cards are focusable listitems named Note <n> of <total>, and Space on the first card starts a keyboard drag — DoD-13", async () => {
    await renderReady(PAYLOAD);
    const listed = items();
    expect(listed).toHaveLength(3);
    expect(listed[0]).toHaveAccessibleName("Note 1 of 3");
    expect(listed[1]).toHaveAccessibleName("Note 2 of 3");
    expect(listed[2]).toHaveAccessibleName("Note 3 of 3");
    const card = listed[0];
    expect(card.tabIndex).toBe(0);

    card.focus();
    pressSpace(card);

    await waitFor(() => {
      expect(liveRegionText()).not.toBe("");
    });
    expect(liveRegionText()).toContain(NOTES);
  });

  it("moving the first card down one place by keyboard sends the level's whole order once — DoD-13", async () => {
    stackListRows();
    const { calls } = stubBackend((request) => {
      if (isListing(request)) return jsonResponse({ memos: PAYLOAD }, 200);
      if (request.method === "PUT" && request.path === ORDER_PATH && request.search === "") {
        const sent = request.body as { memo_ids: string[] };
        const byId = new Map(PAYLOAD.map((row) => [row.id, row]));
        const ordered = sent.memo_ids.map((id, index) => {
          const row = byId.get(id);
          if (row === undefined) throw new Error(`unknown memo id ${id}`);
          return { ...row, sort_key: index };
        });
        return jsonResponse({ memos: ordered }, 200);
      }
      return notFoundResponse();
    });
    renderSection();
    await waitFor(() => {
      expect(bodies()).toHaveLength(PAYLOAD.length);
    });

    const card = items()[0];
    card.focus();
    pressSpace(card);
    await settle();
    fireEvent.keyDown(document.activeElement ?? card, { code: "ArrowDown", key: "ArrowDown" });
    await settle();
    fireEvent.keyDown(document.activeElement ?? card, { code: "Space", key: " " });

    await waitFor(() => {
      expect(calls.filter((call) => call.method === "PUT")).toHaveLength(1);
    });
    await settle();
    // Rework (verifier TEST fault): the order update's body follows the 016 wire contract
    // { scope, scope_id, memo_ids } (pinned in memosApi.test.ts); assert the id order and the
    // character level rather than an exact body that omits the scope fields.
    const sentCalls = nonListing(calls);
    expect(sentCalls).toHaveLength(1);
    expect(sentCalls[0]).toMatchObject({ method: "PUT", path: ORDER_PATH, search: "" });
    expect(sentCalls[0].body).toMatchObject({
      scope: "character",
      scope_id: CHARACTER_ID,
      memo_ids: [PAYLOAD_IDS[1], PAYLOAD_IDS[0], PAYLOAD_IDS[2]],
    });
    await waitFor(() => {
      expect(bodies()).toEqual([BODY_2, BODY_1, BODY_3]);
    });
  });
});
