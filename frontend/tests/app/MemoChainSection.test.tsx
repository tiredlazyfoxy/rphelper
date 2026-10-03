// Feature 015, step 008 — the session's "Notes" section (DoD-2..DoD-6).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 008.context.md (titles and headings, test notes: the section renders alone in AppProviders,
// no router) and context.md: D1 (fixed level order, the setup group absent when the session has
// none), D5 (save on blur, never optimistic, nothing refetched after a mutation), D16, R2, R3,
// the UI strings table and the memos wire contract.
//
// Recognition conventions (for the verifier):
// - The section is the region named "Notes"; each level group is a region named by its title
//   ("Your notes", "Character notes", "Setup notes", "Session notes"), found inside it.
// - `src/shared/MarkdownEditor` is replaced by the labelled-`<textarea>` stub of step 007's
//   MemoLevelGroup.test.tsx (id from React's `useId`, since many editors labelled "Note" are on
//   screen at once). A note's text is its textarea's value. Focus loss is `fireEvent.blur`;
//   typing is `fireEvent.change`.
// - A Mantine `Loader`: `.mantine-Loader-root`. A notification: `.mantine-Notification-root`.
// - `fetch` is stubbed per test; requests are recorded by exact method + pathname + query
//   string with the parsed JSON body.
//
// Feature 016, step 004 amendments (DoD-7..DoD-9): every group is now reorderable inside the
// section's one DndContext, so each saved note's listitem is focusable and named
// "Note <n> of <total>" for its own group (016 context.md strings table). A just-created note is
// found FIRST in its group (016 D5). Keyboard activation is Space keydown on the focused card;
// dnd-kit's announcement live region (role "status") is read afterwards. Pointer and arrow-key
// movement are never exercised (jsdom zero-size rects, 016 D8).
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ChangeEvent } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoChainSection } from "../../src/app/MemoChainSection";
import type { Memo, MemoChainLevel, MemoScope } from "../../src/app/memosApi";
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
const YOUR_NOTES = "Your notes";
const CHARACTER_NOTES = "Character notes";
const SETUP_NOTES = "Setup notes";
const SESSION_NOTES = "Session notes";
const NOTE_LABEL = "Note";
const NEW_NOTE = "New note";
const ENABLE_NOTE = "Enable note";
const EMPTY_LINE = "No notes yet.";
const LOAD_FAILED = "Could not load notes";
const RETRY = "Retry";

const LOADER = ".mantine-Loader-root";
const NOTIFICATION = ".mantine-Notification-root";

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "9007199254740993";
const CHARACTER_ID = "7250000000000000011";
const SETUP_ID = "7250000000000000021";
const CREATED_ID = "9007199254740999";

const CHAIN_PATH = `/api/sessions/${SESSION_ID}/memo-chain`;
const MEMOS_PATH = "/api/memos";

const STAMP = "2026-10-02T09:26:53.000000+00:00";
const CREATED_STAMP = "2026-10-02T09:40:00.000000+00:00";

function memo(id: string, scope: MemoScope, scopeId: string | null, body: string, overrides: Partial<Memo> = {}): Memo {
  return {
    id,
    scope,
    scope_id: scopeId,
    body,
    is_enabled: true,
    is_forced: false,
    sort_key: 0,
    created_at: STAMP,
    updated_at: STAMP,
    ...overrides,
  };
}

const USER_BODIES = ["Write in British English.", "Never break character."];
const CHARACTER_BODIES = ["Mira limps on her left leg."];
const SETUP_BODIES = ["The tavern burned down last winter."];
const SESSION_BODIES = ["Tonight is the festival.", "The bell rang twice."];

const USER_LEVEL: MemoChainLevel = {
  scope: "user",
  scope_id: null,
  memos: [
    memo("7250000000000000201", "user", null, USER_BODIES[0]),
    memo("7250000000000000202", "user", null, USER_BODIES[1], { sort_key: 1 }),
  ],
};
const CHARACTER_LEVEL: MemoChainLevel = {
  scope: "character",
  scope_id: CHARACTER_ID,
  memos: [memo("7250000000000000203", "character", CHARACTER_ID, CHARACTER_BODIES[0])],
};
const SETUP_LEVEL: MemoChainLevel = {
  scope: "setup",
  scope_id: SETUP_ID,
  memos: [memo("7250000000000000204", "setup", SETUP_ID, SETUP_BODIES[0])],
};
const SESSION_LEVEL: MemoChainLevel = {
  scope: "session",
  scope_id: SESSION_ID,
  memos: [
    memo("7250000000000000205", "session", SESSION_ID, SESSION_BODIES[0]),
    memo("7250000000000000206", "session", SESSION_ID, SESSION_BODIES[1], { sort_key: 1 }),
  ],
};

const FOUR_LEVELS: MemoChainLevel[] = [USER_LEVEL, CHARACTER_LEVEL, SETUP_LEVEL, SESSION_LEVEL];
const THREE_LEVELS: MemoChainLevel[] = [USER_LEVEL, CHARACTER_LEVEL, SESSION_LEVEL];

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
  return envelope("session_not_found", 404);
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

function isChainRead(request: Seen): boolean {
  return request.method === "GET" && request.path === CHAIN_PATH && request.search === "";
}

/**
 * The chain GET answers the given levels by exact path; POST /api/memos answers 201 with the
 * created row (enabled, not forced) from the sent scope, scope_id and body. Everything else 404s.
 */
function serveChain(levels: MemoChainLevel[]) {
  return stubBackend((request) => {
    if (isChainRead(request)) return jsonResponse({ levels }, 200);
    if (request.method === "POST" && request.path === MEMOS_PATH && request.search === "") {
      const sent = request.body as { scope: MemoScope; scope_id: string | null; body: string };
      return jsonResponse(
        memo(CREATED_ID, sent.scope, sent.scope_id, sent.body, {
          sort_key: 9,
          created_at: CREATED_STAMP,
          updated_at: CREATED_STAMP,
        }),
        201,
      );
    }
    return notFoundResponse();
  });
}

function chainReads(calls: Seen[]): Seen[] {
  return calls.filter((call) => call.method === "GET" && call.path === CHAIN_PATH);
}

function memoListings(calls: Seen[]): Seen[] {
  return calls.filter((call) => call.method === "GET" && call.path === MEMOS_PATH);
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
function renderSection(sessionId: string = SESSION_ID) {
  return render(
    <AppProviders>
      <MemoChainSection sessionId={sessionId} />
    </AppProviders>,
  );
}

function notesRegion(): HTMLElement {
  return screen.getByRole("region", { name: NOTES });
}

function group(title: string): HTMLElement {
  return within(notesRegion()).getByRole("region", { name: title });
}

const ALL_TITLES = [YOUR_NOTES, CHARACTER_NOTES, SETUP_NOTES, SESSION_NOTES];

/**
 * The titles of the regions inside "Notes", in document order: each region found inside
 * "Notes" is matched against the region named by each known title (accessible names only).
 */
function groupTitles(): string[] {
  const notes = within(notesRegion());
  return notes.queryAllByRole("region").map((element) => {
    const title = ALL_TITLES.find((candidate) => notes.queryByRole("region", { name: candidate }) === element);
    return title ?? "<unnamed region>";
  });
}

function groupItems(title: string): HTMLElement[] {
  return within(group(title)).queryAllByRole("listitem");
}

/** The text of each note in a group, in order (each note's "Note" editor value). */
function groupBodies(title: string): string[] {
  return within(group(title))
    .queryAllByRole("textbox", { name: NOTE_LABEL })
    .map((box) => (box as HTMLTextAreaElement).value);
}

function headingLevel(heading: HTMLElement): number {
  const aria = heading.getAttribute("aria-level");
  if (aria !== null) return Number(aria);
  const match = /^H([1-6])$/.exec(heading.tagName);
  if (match === null) throw new Error(`not a heading element: ${heading.tagName}`);
  return Number(match[1]);
}

async function readyFour(): Promise<{ calls: Seen[] }> {
  const { calls } = serveChain(FOUR_LEVELS);
  renderSection();
  await waitFor(() => {
    expect(within(notesRegion()).queryByRole("region", { name: SESSION_NOTES })).not.toBeNull();
  });
  return { calls };
}

// ===========================================================================
describe("a four-level chain", () => {
  it("renders a Notes region with a Notes heading, holding Your, Character, Setup and Session notes in that order — DoD-2", async () => {
    await readyFour();

    const notes = notesRegion();
    expect(within(notes).getByRole("heading", { name: NOTES })).toBeInTheDocument();
    expect(groupTitles()).toEqual([YOUR_NOTES, CHARACTER_NOTES, SETUP_NOTES, SESSION_NOTES]);
  });

  it("each group lists its level's notes and only those — DoD-2", async () => {
    await readyFour();

    expect(groupBodies(YOUR_NOTES)).toEqual(USER_BODIES);
    expect(groupBodies(CHARACTER_NOTES)).toEqual(CHARACTER_BODIES);
    expect(groupBodies(SETUP_NOTES)).toEqual(SETUP_BODIES);
    expect(groupBodies(SESSION_NOTES)).toEqual(SESSION_BODIES);
    expect(groupItems(YOUR_NOTES)).toHaveLength(USER_BODIES.length);
    expect(groupItems(CHARACTER_NOTES)).toHaveLength(CHARACTER_BODIES.length);
    expect(groupItems(SETUP_NOTES)).toHaveLength(SETUP_BODIES.length);
    expect(groupItems(SESSION_NOTES)).toHaveLength(SESSION_BODIES.length);
  });

  it("each group's heading is one level below the Notes heading — DoD-2", async () => {
    await readyFour();

    const notesLevel = headingLevel(within(notesRegion()).getByRole("heading", { name: NOTES }));
    for (const title of [YOUR_NOTES, CHARACTER_NOTES, SETUP_NOTES, SESSION_NOTES]) {
      const heading = within(group(title)).getByRole("heading", { name: title });
      expect(headingLevel(heading)).toBe(notesLevel + 1);
    }
  });
});

// ===========================================================================
describe("a three-level chain — the session has no setup (US-057.AC-1, R2)", () => {
  it("holds exactly Your, Character and Session notes in that order, no Setup notes anywhere, and every note listed — DoD-3", async () => {
    serveChain(THREE_LEVELS);
    renderSection();
    await waitFor(() => {
      expect(within(notesRegion()).queryByRole("region", { name: SESSION_NOTES })).not.toBeNull();
    });

    expect(groupTitles()).toEqual([YOUR_NOTES, CHARACTER_NOTES, SESSION_NOTES]);
    expect(screen.queryByRole("region", { name: SETUP_NOTES })).toBeNull();
    expect(screen.queryByRole("heading", { name: SETUP_NOTES })).toBeNull();
    expect(screen.queryByText(SETUP_NOTES)).toBeNull();
    expect(groupBodies(YOUR_NOTES)).toEqual(USER_BODIES);
    expect(groupBodies(CHARACTER_NOTES)).toEqual(CHARACTER_BODIES);
    expect(groupBodies(SESSION_NOTES)).toEqual(SESSION_BODIES);
  });
});

// ===========================================================================
describe("empty levels and disabled notes", () => {
  it("a level with no notes renders its group with No notes yet. — DoD-4", async () => {
    serveChain([USER_LEVEL, { ...CHARACTER_LEVEL, memos: [] }, SETUP_LEVEL, SESSION_LEVEL]);
    renderSection();
    await waitFor(() => {
      expect(within(notesRegion()).queryByRole("region", { name: CHARACTER_NOTES })).not.toBeNull();
    });

    expect(within(group(CHARACTER_NOTES)).getByText(EMPTY_LINE)).toBeInTheDocument();
    expect(groupItems(CHARACTER_NOTES)).toHaveLength(0);
    expect(within(group(YOUR_NOTES)).queryByText(EMPTY_LINE)).toBeNull();
  });

  it("a disabled note renders in its group with Enable note — DoD-4", async () => {
    const disabledBody = "A forgotten rumour.";
    serveChain([
      USER_LEVEL,
      CHARACTER_LEVEL,
      {
        ...SETUP_LEVEL,
        memos: [
          memo("7250000000000000207", "setup", SETUP_ID, disabledBody, { is_enabled: false, is_forced: true }),
        ],
      },
      SESSION_LEVEL,
    ]);
    renderSection();
    await waitFor(() => {
      expect(within(notesRegion()).queryByRole("region", { name: SETUP_NOTES })).not.toBeNull();
    });

    expect(groupBodies(SETUP_NOTES)).toEqual([disabledBody]);
    const item = groupItems(SETUP_NOTES)[0];
    expect(within(item).getByRole("button", { name: ENABLE_NOTE })).toBeInTheDocument();
  });
});

// ===========================================================================
describe("creating a note in each group (US-049..US-053, D5)", () => {
  type CreateCase = [title: string, scope: MemoScope, scopeId: string | null, before: number];

  const CASES: CreateCase[] = [
    [YOUR_NOTES, "user", null, USER_BODIES.length],
    [CHARACTER_NOTES, "character", CHARACTER_ID, CHARACTER_BODIES.length],
    [SETUP_NOTES, "setup", SETUP_ID, SETUP_BODIES.length],
    [SESSION_NOTES, "session", SESSION_ID, SESSION_BODIES.length],
  ];

  it.each(CASES)(
    "%s: New note, typing and blurring POSTs that level's scope and scope id; the note appears first in that group only, with no chain or listing request after (015 008 DoD-5, amended by 016 D5) — DoD-7",
    async (title, scope, scopeId, before) => {
      const { calls } = await readyFour();
      const user = newUser();
      const counts = [YOUR_NOTES, CHARACTER_NOTES, SETUP_NOTES, SESSION_NOTES].map(
        (each) => [each, groupItems(each).length] as const,
      );
      const text = `A fresh note for ${scope}.`;

      await user.click(within(group(title)).getByRole("button", { name: NEW_NOTE }));
      await waitFor(() => {
        expect(groupItems(title)).toHaveLength(before + 1);
      });
      const fresh = within(groupItems(title)[0]).getByRole("textbox", { name: NOTE_LABEL });
      fireEvent.change(fresh, { target: { value: text } });
      fireEvent.blur(fresh);

      await waitFor(() => {
        expect(calls.filter((call) => call.method === "POST")).toHaveLength(1);
      });
      const postIndex = calls.findIndex((call) => call.method === "POST");
      expect(calls[postIndex]).toEqual({
        method: "POST",
        path: MEMOS_PATH,
        search: "",
        body: { scope, scope_id: scopeId, body: text },
      });

      // After the 201 the saved note is in this group (a saved note carries its flag controls).
      await waitFor(() => {
        expect(within(groupItems(title)[0]).queryByRole("button", { name: "Disable note" })).not.toBeNull();
      });
      await settle();
      expect(groupBodies(title)[0]).toBe(text);
      expect(groupItems(title)).toHaveLength(before + 1);
      for (const [each, count] of counts) {
        if (each === title) continue;
        expect(groupItems(each)).toHaveLength(count);
        expect(groupBodies(each)).not.toContain(text);
      }

      // Never refetched after a mutation: one chain read in all, none after the POST, no listing.
      expect(chainReads(calls)).toHaveLength(1);
      expect(chainReads(calls.slice(postIndex + 1))).toEqual([]);
      expect(memoListings(calls)).toEqual([]);
    },
  );
});

// ===========================================================================
describe("loading and failure (no notification)", () => {
  it("while the chain request is pending the Notes region shows a loader — DoD-6", async () => {
    const gate = deferred<Response>();
    const { calls } = stubBackend((request) => (isChainRead(request) ? gate.promise : notFoundResponse()));
    renderSection();
    await waitFor(() => {
      expect(chainReads(calls)).toHaveLength(1);
    });

    expect(notesRegion().querySelector(LOADER)).not.toBeNull();
    expect(within(notesRegion()).queryByRole("region")).toBeNull();
    expect(within(notesRegion()).queryByText(LOAD_FAILED)).toBeNull();

    await act(async () => {
      gate.resolve(jsonResponse({ levels: FOUR_LEVELS }, 200));
    });
    await waitFor(() => {
      expect(groupTitles()).toEqual([YOUR_NOTES, CHARACTER_NOTES, SETUP_NOTES, SESSION_NOTES]);
    });
    expect(notesRegion().querySelector(LOADER)).toBeNull();
  });

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
    "%s shows Could not load notes and Retry in the Notes region, with no notification — DoD-6",
    async (_label, answer) => {
      stubBackend(() => answer());
      renderSection();

      await waitFor(() => {
        expect(within(notesRegion()).queryByText(LOAD_FAILED)).not.toBeNull();
      });
      expect(within(notesRegion()).getByRole("button", { name: RETRY })).toBeInTheDocument();
      expect(within(notesRegion()).queryByRole("region")).toBeNull();
      await settle();
      expect(document.querySelector(NOTIFICATION)).toBeNull();
    },
  );

  it("Retry requests the chain again and, on success, the groups render — DoD-6", async () => {
    let failNext = true;
    const { calls } = stubBackend((request) => {
      if (isChainRead(request)) {
        if (failNext) {
          failNext = false;
          return serverError();
        }
        return jsonResponse({ levels: FOUR_LEVELS }, 200);
      }
      return notFoundResponse();
    });
    renderSection();
    await waitFor(() => {
      expect(within(notesRegion()).queryByText(LOAD_FAILED)).not.toBeNull();
    });
    expect(chainReads(calls)).toHaveLength(1);

    await newUser().click(within(notesRegion()).getByRole("button", { name: RETRY }));

    await waitFor(() => {
      expect(groupTitles()).toEqual([YOUR_NOTES, CHARACTER_NOTES, SETUP_NOTES, SESSION_NOTES]);
    });
    expect(chainReads(calls)).toHaveLength(2);
    expect(within(notesRegion()).queryByText(LOAD_FAILED)).toBeNull();
    expect(groupBodies(SESSION_NOTES)).toEqual(SESSION_BODIES);
    expect(document.querySelector(NOTIFICATION)).toBeNull();
  });
});

// ===========================================================================
// Feature 016, step 004 — the chain's drag context (D8; R2).

/** Every memo id string in a chain, in level order. */
function memoIds(levels: MemoChainLevel[]): string[] {
  return levels.flatMap((each) => each.memos.map((row) => row.id));
}

/** Each saved note's listitem in the group is focusable and named Note 1..n of n, in order. */
function expectReorderableGroup(title: string, count: number): void {
  const items = groupItems(title);
  expect(items).toHaveLength(count);
  items.forEach((item, index) => {
    expect(item.tabIndex).toBe(0);
    expect(item).toHaveAccessibleName(`Note ${index + 1} of ${count}`);
  });
}

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

describe("the chain's drag context — four levels (016 004)", () => {
  it("every saved note's listitem in all four groups is focusable and named Note <n> of <total> for its own group — DoD-7", async () => {
    await readyFour();

    expectReorderableGroup(YOUR_NOTES, USER_LEVEL.memos.length);
    expectReorderableGroup(CHARACTER_NOTES, CHARACTER_LEVEL.memos.length);
    expectReorderableGroup(SETUP_NOTES, SETUP_LEVEL.memos.length);
    expectReorderableGroup(SESSION_NOTES, SESSION_LEVEL.memos.length);
  });

  it("the Notes region, the group names and their order still hold with reorderable groups — DoD-7", async () => {
    await readyFour();

    expect(within(notesRegion()).getByRole("heading", { name: NOTES })).toBeInTheDocument();
    expect(groupTitles()).toEqual([YOUR_NOTES, CHARACTER_NOTES, SETUP_NOTES, SESSION_NOTES]);
    expect(groupBodies(YOUR_NOTES)).toEqual(USER_BODIES);
    expect(groupBodies(CHARACTER_NOTES)).toEqual(CHARACTER_BODIES);
    expect(groupBodies(SETUP_NOTES)).toEqual(SETUP_BODIES);
    expect(groupBodies(SESSION_NOTES)).toEqual(SESSION_BODIES);
  });

  it("the position names count per group: Your notes' second note is Note 2 of 2, the Setup note is Note 1 of 1 — DoD-7", async () => {
    await readyFour();

    expect(within(group(YOUR_NOTES)).getByRole("listitem", { name: "Note 2 of 2" })).toBe(groupItems(YOUR_NOTES)[1]);
    expect(within(group(SETUP_NOTES)).getByRole("listitem", { name: "Note 1 of 1" })).toBe(groupItems(SETUP_NOTES)[0]);
    expect(within(group(CHARACTER_NOTES)).queryByRole("listitem", { name: "Note 1 of 2" })).toBeNull();
  });
});

describe("the chain's drag context — three levels, no setup (US-057.AC-1, R2)", () => {
  it("renders exactly three reorderable groups and no Setup notes — DoD-8", async () => {
    serveChain(THREE_LEVELS);
    renderSection();
    await waitFor(() => {
      expect(within(notesRegion()).queryByRole("region", { name: SESSION_NOTES })).not.toBeNull();
    });

    expect(groupTitles()).toEqual([YOUR_NOTES, CHARACTER_NOTES, SESSION_NOTES]);
    expect(screen.queryByRole("region", { name: SETUP_NOTES })).toBeNull();
    expect(screen.queryByText(SETUP_NOTES)).toBeNull();
    expectReorderableGroup(YOUR_NOTES, USER_LEVEL.memos.length);
    expectReorderableGroup(CHARACTER_NOTES, CHARACTER_LEVEL.memos.length);
    expectReorderableGroup(SESSION_NOTES, SESSION_LEVEL.memos.length);
  });
});

describe("the chain's announcements (US-102 keyboard path; D8)", () => {
  type AnnounceCase = [title: string, index: number];

  const ANNOUNCE_CASES: AnnounceCase[] = [
    [SESSION_NOTES, 1],
    [YOUR_NOTES, 0],
  ];

  it.each(ANNOUNCE_CASES)(
    "Space on the focused saved note %s #%i fills dnd-kit's live region with a message that holds no memo id — DoD-9",
    async (title, index) => {
      await readyFour();
      const card = groupItems(title)[index];

      card.focus();
      expect(document.activeElement).toBe(card);
      pressSpace(card);

      await waitFor(() => {
        expect(liveRegionText()).not.toBe("");
      });
      const message = liveRegionText();
      for (const id of memoIds(FOUR_LEVELS)) {
        expect(message).not.toContain(id);
      }
    },
  );
});
