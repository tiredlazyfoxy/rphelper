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
import type { ChangeEvent } from "react";
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
  };
  return {
    MarkdownEditor: (props: StubProps) => {
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
const NOTES = "Notes";
const NOTE_LABEL = "Note";
const NEW_NOTE = "New note";
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

  it("New note, typing Voice: dry and blurring POSTs exactly scope, scope_id and body; the saved note shows the searchable reach; no listing follows — DoD-2", async () => {
    const { calls } = serveNotes([]);
    renderSection();
    await waitFor(() => {
      expect(within(notesRegion()).queryByText(EMPTY_LINE)).not.toBeNull();
    });

    await newUser().click(within(notesRegion()).getByRole("button", { name: NEW_NOTE }));
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

describe("the character's notes as a reorderable grid (US-096.AC-1, US-102, D8)", () => {
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

describe("015 009's behaviour kept in the grid (US-050.AC-1, D8)", () => {
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
