// Feature 029, step 006 (DoD-1..6) — the landing half: `?entry=<message id>` scrolls the
// settled record to that entry and highlights it briefly, and `?notes=open` opens the note
// wall on arrival. DoD-1 and DoD-2 (the tree's search input and the tree census) live in
// CharacterTree.test.tsx; DoD-7 is [manual/live] and carries no test. So this file covers
// DoD-3, DoD-4, DoD-5 and DoD-6.
//
// Expected behaviour comes from the step file's Definition of done and Interface intent plus
// 029 context.md: U4 and D8 (the landing URL contract — `entry` is the message id to scroll to
// and highlight once the record loads, `notes=open` opens the wall on arrival, an `entry` id
// not present in the loaded record does nothing and no param is removed from the URL), and the
// Literals table: the highlight lasts exactly **2000 ms**, every entry always carries
// `data-entry-id="<message id>"`, and the highlighted entry carries `data-highlighted="true"`
// while highlighted.
//
// Recognition conventions (from the spec's wording, for the verifier):
// - An entry is recognised by its `data-entry-id` attribute, whose value is the message id
//   verbatim as a string (context.md literals; never `data-entry`, which is the Vite entry
//   marker other suites enumerate).
// - "Highlighted" is recognised **only** by `data-highlighted="true"` (context.md literals).
//   The colour it is drawn in is not part of the contract and is never asserted.
// - "Scrolled to" is recognised by a `scrollIntoView` call on that entry's element: tests/setup.ts
//   installs an inert `Element.prototype.scrollIntoView`, so this file spies on it and records
//   the `this` of every call (which element was scrolled). The options argument is not asserted.
// - The note wall is 016's complementary landmark "Note wall" holding the region "Notes", and
//   it is closed on arrival unless something opens it; its open control is "Open notes"
//   (SessionScreen.test.tsx's idiom, reused here).
// - The screen's failure texts are 011's: "Session not found" and "Could not load the session".
// - Stubs key on the **exact** pathname (context.md "Test conventions"); the stub set is
//   SessionScreen.test.tsx's, since this file renders the same screen.
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { runInAction } from "mobx";
import type { ChangeEvent } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SessionScreen } from "../../src/app/SessionScreen";
import type { Character } from "../../src/app/charactersApi";
import type {
  EnabledModel,
  ModelRef,
  SessionConfiguration,
  Setting,
} from "../../src/app/configurationApi";
import { CharactersState } from "../../src/app/charactersState";
import type { Session } from "../../src/app/sessionsApi";
import type { Message, MessageKind } from "../../src/app/streamApi";
import type { LayoutStorage } from "../../src/app/workspaceLayout";
import { AppProviders } from "../../src/shared/AppProviders";

// The notes' editor, exactly as SessionScreen.test.tsx stubs it (harness setup, not a
// contract): the real editor is TipTap, which this file has no reason to mount.
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
type Seen = { method: string; path: string; search: string };

// ---------------------------------------------------------------- the spec's names
const RECORD_NAME = "Settled record";
const WALL_NAME = "Note wall";
const NOTES_REGION = "Notes";
const OPEN_NOTES_NAME = "Open notes";
const NOT_FOUND_TEXT = "Session not found";
const LOAD_FAILED_TEXT = "Could not load the session";

/** context.md literals: the two attributes, and the highlight's exact lifetime. */
const ENTRY_ID_ATTRIBUTE = "data-entry-id";
const HIGHLIGHTED_ATTRIBUTE = "data-highlighted";
const HIGHLIGHTED_VALUE = "true";
const HIGHLIGHT_MS = 2000;

/** D8's two landing params, spelled as the contract spells them. */
const ENTRY_PARAM = "entry";
const NOTES_PARAM = "notes";
const NOTES_OPEN_VALUE = "open";

// ---------------------------------------------------------------- fixtures
// Every id is a decimal string past Number.MAX_SAFE_INTEGER, so a coerced id would not match
// the attribute's value character for character (context.md "Ids are strings").
const CHAR_ID = "7250000000000000011";
const SESSION_ID = "9007199254740993"; // 2^53 + 1
const SETUP_ID = "7250000000000000021";

const ENTRY_ONE_ID = "7250000000000000501";
const ENTRY_TWO_ID = "7250000000000000502";
const ENTRY_THREE_ID = "7250000000000000503";
const ENTRY_FOUR_ID = "7250000000000000504";
/** An id of no entry in the loaded record (DoD-5). */
const UNKNOWN_ENTRY_ID = "7250000000000000599";

const ENTRY_ONE_TEXT = "The first settled line.";
const ENTRY_TWO_TEXT = "The second settled line.";
const ENTRY_THREE_TEXT = "The third settled line.";
const ENTRY_FOUR_TEXT = "The fourth settled line.";

const STAMP = "2026-05-10T09:00:00.000000+00:00";
const ENTRY_STAMP = "2026-05-10T09:30:00.000000+00:00";

const CHARACTER: Character = {
  id: CHAR_ID,
  name: "Aria",
  sheet: "A scribe who never finishes a sentence.",
  archived_at: null,
  created_at: STAMP,
  updated_at: STAMP,
};

const SESSION: Session = {
  id: SESSION_ID,
  character_id: CHAR_ID,
  setup_id: SETUP_ID,
  setup_name: "Tavern",
  archived_at: null,
  last_used_at: STAMP,
  created_at: STAMP,
  updated_at: STAMP,
};

function settledEntry(id: string, kind: MessageKind, text: string): Message {
  return {
    id,
    session_id: SESSION_ID,
    role: "user",
    kind,
    text,
    settled_at: ENTRY_STAMP,
    created_at: ENTRY_STAMP,
    updated_at: ENTRY_STAMP,
  };
}

/** A record of four entries, in the order the server returns them. */
const RECORD: Message[] = [
  settledEntry(ENTRY_ONE_ID, "partner", ENTRY_ONE_TEXT),
  settledEntry(ENTRY_TWO_ID, "turn", ENTRY_TWO_TEXT),
  settledEntry(ENTRY_THREE_ID, "partner", ENTRY_THREE_TEXT),
  settledEntry(ENTRY_FOUR_ID, "turn", ENTRY_FOUR_TEXT),
];

const RECORD_IDS = RECORD.map((entry) => entry.id);

// ---------------------------------------------------------------- fetch harness
function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function notFoundResponse(): Response {
  return jsonResponse(
    { error: { code: "session_not_found", message: "ql-77 went wrong.", detail: {} } },
    404,
  );
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function stubBackend(handler: (request: Seen) => Response | Promise<Response>) {
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>(async (input, init) => {
    const url = requestUrl(input);
    const request: Seen = {
      method: requestMethod(input, init),
      path: url.pathname,
      search: url.search,
    };
    calls.push(request);
    return handler(request);
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

// Every path the screen loads, by exact pathname (SessionScreen.test.tsx's set).
const SESSION_PATH = `/api/sessions/${SESSION_ID}`;
const ENTRIES_PATH = `${SESSION_PATH}/entries`;
const ZONE_PATH = `${SESSION_PATH}/zone`;
const MEMO_CHAIN_PATH = `${SESSION_PATH}/memo-chain`;
const CONFIGURATION_PATH = `${SESSION_PATH}/configuration`;
const MODELS_PATH = "/api/models";

const SERVER_ID = "7250000000000000401";
const MODEL: EnabledModel = { server_id: SERVER_ID, server_name: "S1", model_name: "A" };
const MODEL_REF: ModelRef = { server_id: SERVER_ID, model_name: "A" };

function emptyTextSetting(): Setting<string> {
  return { session: null, inherited: null, inherited_level: null, value: null, level: null };
}

function defaultToolSetting(): Setting<boolean> {
  return { session: null, inherited: true, inherited_level: "default", value: true, level: "default" };
}

function sessionConfiguration(): SessionConfiguration {
  return {
    model: { ...MODEL_REF },
    system_prompt: emptyTextSetting(),
    tool_memo_search: defaultToolSetting(),
    tool_session_search: defaultToolSetting(),
    tool_web_search: defaultToolSetting(),
    rp_language: emptyTextSetting(),
    preferred_language: emptyTextSetting(),
  };
}

/** The whole screen's backend: the session, its record, and everything else it loads. */
function serveSession(entries: Message[] = RECORD) {
  return stubBackend((request) => {
    if (request.method !== "GET") return notFoundResponse();
    if (request.path === SESSION_PATH) return jsonResponse(SESSION, 200);
    if (request.path === ENTRIES_PATH) return jsonResponse({ entries }, 200);
    if (request.path === ZONE_PATH) return jsonResponse({ messages: [] }, 200);
    if (request.path === MEMO_CHAIN_PATH) return jsonResponse({ levels: [] }, 200);
    if (request.path === CONFIGURATION_PATH) return jsonResponse(sessionConfiguration(), 200);
    if (request.path === MODELS_PATH) return jsonResponse({ models: [MODEL] }, 200);
    return notFoundResponse();
  });
}

async function flush(rounds = 6): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => setImmediate(resolve));
    });
  }
}

// ---------------------------------------------------------------- the scroll spy
// tests/setup.ts installs an inert `Element.prototype.scrollIntoView`; this records which
// element each call was made on (`this`), which is how "scrolled that entry" is recognised.
function spyOnScroll(): Element[] {
  const scrolled: Element[] = [];
  vi.spyOn(Element.prototype, "scrollIntoView").mockImplementation(function (this: Element) {
    scrolled.push(this);
  });
  return scrolled;
}

/**
 * The recorded calls that scrolled an entry of the record — the clause's subject. Filtering
 * by the entry attribute keeps the count about the anchor and not about any unrelated
 * `scrollIntoView` a component library might make on its own elements.
 */
function entryScrolls(scrolled: Element[]): Element[] {
  return scrolled.filter((element) => element.closest(`[${ENTRY_ID_ATTRIBUTE}]`) !== null);
}

// ---------------------------------------------------------------- fake timers (DoD-4)
// AppBoot.test.tsx's idiom, including the explicit `toFake` allow-list — `flush()` awaits
// `setImmediate`, which must stay real or nothing ever settles.
function useFakeTimers(): void {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
}

async function advance(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
  await flush();
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- render
function workspaceWith(...rows: Character[]): CharactersState {
  const characters = new CharactersState();
  runInAction(() => {
    characters.characters = rows.map((row) => ({ ...row }));
    characters.status = rows.length > 0 ? "ready" : "idle";
  });
  return characters;
}

/**
 * The session screen at `path`, in the `<main>` landmark the shell gives it, with the one
 * workspace characters state and a null layout storage (so the wall starts unpinned, as
 * every delivered clause has it). `path` is the only way a landing param reaches the screen.
 */
function renderAt(path: string, storage: LayoutStorage | null = null) {
  const view = render(
    <AppProviders>
      <MemoryRouter initialEntries={[path]}>
        <main>
          <SessionScreen
            sessionId={SESSION_ID}
            characters={workspaceWith(CHARACTER)}
            storage={storage}
          />
        </main>
      </MemoryRouter>
    </AppProviders>,
  );
  return { view };
}

function sessionRoute(params: Record<string, string> = {}): string {
  const search = new URLSearchParams(params).toString();
  return search === "" ? `/sessions/${SESSION_ID}` : `/sessions/${SESSION_ID}?${search}`;
}

// ---------------------------------------------------------------- queries
function mainRegion(): HTMLElement {
  return screen.getByRole("main");
}

function recordList(): HTMLElement {
  return within(mainRegion()).getByRole("list", { name: RECORD_NAME });
}

/** Every entry of the record, in document order, found by the attribute they always carry. */
function entryItems(): HTMLElement[] {
  return Array.from(recordList().querySelectorAll<HTMLElement>(`[${ENTRY_ID_ATTRIBUTE}]`));
}

function entryIds(): (string | null)[] {
  return entryItems().map((item) => item.getAttribute(ENTRY_ID_ATTRIBUTE));
}

function entryWithId(id: string): HTMLElement {
  const found = entryItems().find((item) => item.getAttribute(ENTRY_ID_ATTRIBUTE) === id);
  if (found === undefined) {
    throw new Error(`no entry carries ${ENTRY_ID_ATTRIBUTE}="${id}"`);
  }
  return found;
}

/** Everything in the document marked as highlighted, by the contract's attribute and value. */
function highlighted(): Element[] {
  return Array.from(
    document.querySelectorAll(`[${HIGHLIGHTED_ATTRIBUTE}="${HIGHLIGHTED_VALUE}"]`),
  );
}

/** Asserts that `element` — and nothing else — is the highlighted one. */
function expectOnlyHighlighted(element: Element): void {
  const marked = highlighted();
  expect(marked).toHaveLength(1);
  expect(marked[0]).toBe(element);
}

function accessibleWall(): HTMLElement {
  return within(mainRegion()).getByRole("complementary", { name: WALL_NAME });
}

function wallIsAccessible(): boolean {
  return screen.queryByRole("complementary", { name: WALL_NAME }) !== null;
}

function queryOpenNotes(): HTMLElement | null {
  return within(mainRegion()).queryByRole("button", { name: OPEN_NOTES_NAME });
}

// ===========================================================================
// DoD-3 — the entry anchor
// ===========================================================================
describe("?entry= scrolls to that settled entry and highlights it (UC-060, D8)", () => {
  it("the named entry is scrolled to exactly once and is the only highlighted one, and every entry carries its own id — DoD-3", async () => {
    const scrolled = spyOnScroll();
    serveSession();
    renderAt(sessionRoute({ [ENTRY_PARAM]: ENTRY_THREE_ID }));
    await flush();

    // Every entry carries `data-entry-id` equal to its id, in the record's order.
    expect(entryIds()).toEqual(RECORD_IDS);

    const target = entryWithId(ENTRY_THREE_ID);
    expect(entryScrolls(scrolled)).toHaveLength(1);
    expect(entryScrolls(scrolled)[0]).toBe(target);
    expect(target.getAttribute(HIGHLIGHTED_ATTRIBUTE)).toBe(HIGHLIGHTED_VALUE);
    expectOnlyHighlighted(target);
  });

  it("the first and the last entry are each reachable the same way — DoD-3", async () => {
    for (const id of [ENTRY_ONE_ID, ENTRY_FOUR_ID]) {
      const scrolled = spyOnScroll();
      serveSession();
      const { view } = renderAt(sessionRoute({ [ENTRY_PARAM]: id }));
      await flush();

      const target = entryWithId(id);
      expect(entryIds()).toEqual(RECORD_IDS);
      expect(entryScrolls(scrolled)).toHaveLength(1);
      expect(entryScrolls(scrolled)[0]).toBe(target);
      expectOnlyHighlighted(target);

      view.unmount();
      vi.unstubAllGlobals();
      vi.restoreAllMocks();
    }
  });
});

// ===========================================================================
// DoD-4 — the highlight is brief
// ===========================================================================
describe("the highlight lasts exactly 2000 ms (D8, context.md literals)", () => {
  it("it is still there at 1999 ms and gone at 2000 ms, and nothing scrolls again after that, even when the record re-renders — DoD-4", async () => {
    useFakeTimers();
    const scrolled = spyOnScroll();
    serveSession();
    renderAt(sessionRoute({ [ENTRY_PARAM]: ENTRY_TWO_ID }));
    await flush();

    const target = entryWithId(ENTRY_TWO_ID);
    expect(entryScrolls(scrolled)).toHaveLength(1);
    expect(entryScrolls(scrolled)[0]).toBe(target);
    expectOnlyHighlighted(target);

    await advance(HIGHLIGHT_MS - 1);
    expectOnlyHighlighted(entryWithId(ENTRY_TWO_ID));

    await advance(1);
    expect(highlighted()).toHaveLength(0);
    expect(entryScrolls(scrolled)).toHaveLength(1);

    // A genuine re-render of the entry (its reveal state) and of the screen above it must
    // neither scroll again nor bring the highlight back.
    await act(async () => {
      fireEvent.mouseEnter(entryWithId(ENTRY_TWO_ID));
    });
    await flush();
    const open = queryOpenNotes();
    expect(open).not.toBeNull();
    await act(async () => {
      fireEvent.click(open as HTMLElement);
    });
    await flush();

    expect(entryScrolls(scrolled)).toHaveLength(1);
    expect(highlighted()).toHaveLength(0);
    expect(entryIds()).toEqual(RECORD_IDS);
  });

  it("the highlight does not come back after a further 2000 ms — DoD-4", async () => {
    useFakeTimers();
    const scrolled = spyOnScroll();
    serveSession();
    renderAt(sessionRoute({ [ENTRY_PARAM]: ENTRY_TWO_ID }));
    await flush();

    await advance(HIGHLIGHT_MS);
    expect(highlighted()).toHaveLength(0);

    await advance(HIGHLIGHT_MS);
    expect(highlighted()).toHaveLength(0);
    expect(entryScrolls(scrolled)).toHaveLength(1);
  });
});

// ===========================================================================
// DoD-5 — an unknown entry, and no entry at all
// ===========================================================================
describe("an entry id the record does not hold does nothing (D8)", () => {
  it("the session renders normally: all four entries, nothing scrolled, nothing highlighted, no failure text — DoD-5", async () => {
    const scrolled = spyOnScroll();
    serveSession();
    renderAt(sessionRoute({ [ENTRY_PARAM]: UNKNOWN_ENTRY_ID }));
    await flush();

    // The positive half: the record really did render, so the absences below mean something.
    expect(entryIds()).toEqual(RECORD_IDS);
    for (const text of [ENTRY_ONE_TEXT, ENTRY_TWO_TEXT, ENTRY_THREE_TEXT, ENTRY_FOUR_TEXT]) {
      expect(within(mainRegion()).getByText(text)).toBeInTheDocument();
    }

    expect(entryScrolls(scrolled)).toHaveLength(0);
    expect(highlighted()).toHaveLength(0);
    expect(within(mainRegion()).queryByText(NOT_FOUND_TEXT)).toBeNull();
    expect(within(mainRegion()).queryByText(LOAD_FAILED_TEXT)).toBeNull();
  });

  it("without the entry param the record renders with no entry highlighted and nothing scrolled — DoD-5", async () => {
    const scrolled = spyOnScroll();
    serveSession();
    renderAt(sessionRoute());
    await flush();

    expect(entryIds()).toEqual(RECORD_IDS);
    expect(within(mainRegion()).getByText(ENTRY_ONE_TEXT)).toBeInTheDocument();
    expect(entryScrolls(scrolled)).toHaveLength(0);
    expect(highlighted()).toHaveLength(0);
  });
});

// ===========================================================================
// DoD-6 — the wall opened on arrival
// ===========================================================================
describe("notes=open opens the note wall on arrival (UC-060, U4, D8)", () => {
  it("the wall's Notes region is visible without pressing Open notes — DoD-6", async () => {
    serveSession();
    renderAt(sessionRoute({ [NOTES_PARAM]: NOTES_OPEN_VALUE }));
    await flush();

    const wall = accessibleWall();
    expect(mainRegion().contains(wall)).toBe(true);
    expect(within(wall).getByRole("region", { name: NOTES_REGION })).toBeInTheDocument();
    expect(queryOpenNotes()).toBeNull();
  });

  it("without the param the wall is closed, as before, and Open notes is offered — DoD-6", async () => {
    serveSession();
    renderAt(sessionRoute());
    await flush();

    expect(wallIsAccessible()).toBe(false);
    expect(queryOpenNotes()).not.toBeNull();
  });

  it("the two landing params work together: the entry is highlighted and the wall is open — DoD-6", async () => {
    const scrolled = spyOnScroll();
    serveSession();
    renderAt(
      sessionRoute({ [ENTRY_PARAM]: ENTRY_TWO_ID, [NOTES_PARAM]: NOTES_OPEN_VALUE }),
    );
    await flush();

    const target = entryWithId(ENTRY_TWO_ID);
    expect(entryScrolls(scrolled)).toHaveLength(1);
    expect(entryScrolls(scrolled)[0]).toBe(target);
    expectOnlyHighlighted(target);
    expect(within(accessibleWall()).getByRole("region", { name: NOTES_REGION })).toBeInTheDocument();
  });
});
