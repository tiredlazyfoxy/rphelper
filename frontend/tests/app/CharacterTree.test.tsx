// Feature 009, step 008 — the tree's header and character level (DoD-1..DoD-6).
// DoD-7 lives in WorkspaceShell.test.tsx, DoD-8..DoD-10 in App.test.tsx, and DoD-11 is the
// stub amendment in AppBoot.test.tsx / entries.test.tsx. DoD-12 is [manual/live] and carries
// no test.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 008.context.md and context.md (D4 the non-persisted "Show archived" switch, D12 every
// failure is inline and nothing is notified, D13 the header's two actions, no chevron and no
// session rows).
//
// Recognition conventions (from the spec's wording, for the verifier):
// - The tree's names are the contract: the search box named "Search" (029 step 006; an icon
//   button named "Search" until then), the icon button "New character", the
//   switch "Show archived", the list's accessible name "Characters", the badge text exactly
//   "Archived", the failure sentence "Could not load characters" and its button "Retry".
// - The list: 008.context.md sanctions either a `ul` with `aria-label` (role `list`) or the
//   equivalent landmark, so `charactersList()` accepts role `list` or role `navigation`
//   carrying that name.
// - The switch: Mantine's `Switch` exposes role `switch` (older markup exposes `checkbox`),
//   so `showArchivedSwitch()` accepts either, found by its accessible name.
// - A row: the router link whose text carries the character's name; its badge may sit in the
//   link or in the surrounding list item, so badge queries scope to `rowBlock`.
// - In-entry navigation: a location probe rendered beside the tree in the same MemoryRouter;
//   document navigation is `documentNavigation.assign` (the shared client's only seam onto
//   `window.location`).
// - A notification: `.mantine-Notification-root`.
//
// Amended by feature 011, step 006 (DoD-1..DoD-9, DoD-13). `CharacterTree` gains two required
// props, `sessions` (the workspace `SessionsState`) and `storage` (`LayoutStorage | null`), so
// every render below supplies a fresh state and a storage, and every stub answers
// `GET /api/sessions` — routed by the **exact** pathname, because `/api/characters` and
// `/api/characters/<id>/sessions` share a prefix (011 context.md "Test conventions").
// 009's own clauses are kept, with an **empty** sessions payload, which is exactly the form
// 011 step 006 DoD-13 requires: "payload order" (009 DoD-1) and "no chevron / only Search and
// New character" (009 DoD-6) stay true and keep meaning something, while the
// sessions-present behaviour is covered by 011's DoD-1..DoD-9 blocks at the bottom.
// Start-time labels are asserted only by their fixed shape (never an exact local-time string,
// never by calling the formatter), and session rows are identified by their `/sessions/<id>`
// href and their setup label (011 context.md "Test conventions").
//
// Amended by feature 029, step 006 (DoD-1, DoD-2): the header's "Search" icon button is
// **replaced** by a text input whose accessible name is still "Search" (029 context.md
// literals, "tree input accessible name"), and Enter on it navigates in-entry to
// `/search?q=<encodeURIComponent(text)>` — `/search` when the box is empty (029 U4, D8).
// Four sites change, each marked `S029_006_DoD1` / `S029_006_DoD2` beside the amended line:
//  - "Search moves the in-entry router to /search" (009 008 DoD-3) is replaced by the three
//    029 DoD-1 clauses in the same describe block, which drive the **textbox** instead of a
//    button; the sibling "New character" clause is untouched;
//  - "the ready tree's only buttons are Search and New character" (009 008 DoD-6) and
//    "no chevron, no session row, …" (011 006 DoD-13) each carry a button-name-set
//    assertion, which becomes `["New character"]`;
//  - "the switch is the tree's only other control …" (009 008 DoD-6) asserted the tree held
//    **no** textbox; it now asserts exactly one, the search field.
// The location probe also renders `location.search`, so a clause can read the submitted `q`
// back **decoded** (`URLSearchParams.get`), never as a pinned `%`-encoding. No other
// assertion is dropped or weakened.
//
// Amended by feature 034, step 004 (S034_004_DoD7): a session row's label is the session
// LABEL — the stored name, else the local `YYYY-MM-DD` of `created_at` with no time
// (DEC-034-9). `Session` gains a required `name`; the `session()` builder defaults it to null.
// 011 DoD-3's two shape clauses now expect the date-only shape (START_LABEL_SHAPE /
// START_LABEL_IN_TEXT). The named-row clauses are in the last block. Expected local dates are
// computed with Intl in the runtime zone (`localDate`), never by calling the module under test.
//
// Amended by feature 034, step 006 (S034_006_DoD1..DoD4, DoD6): the tree session row has two
// lines — line 1 the label, line 2 the last-use time `YYYY-MM-DD HH:MM` (local, of
// `last_used_at`), then ` · <setup name>` when there is a setup (DEC-034-9) — and a "Rename
// session" icon button beside (never inside) its link (DEC-034-10). So the clauses above that
// asserted a row's WHOLE text equals its label (011 DoD-3's unnamed row, 004's named row, the
// relabel clause) now read the row's label as "the row's text with its expected line 2 taken
// out" (`rowLabelText`), and the clauses that found the setup name as an element of its own now
// look for it inside line 2. The step 006 clauses are in the last two blocks. The expected
// last-use time comes from an Intl oracle (`localDateTime`), never from the module under test.
// Recognition: line 1 / line 2 are elements whose whole (whitespace-normalised) text is exactly
// the label / exactly the line-2 string, line 1 before line 2 in document order; a row's block
// is the `li` holding its link (or, while editing, its editor); the editor is the textbox
// "Session name"; the failure sentence is "Could not rename the session.".
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { CharacterTree } from "../../src/app/CharacterTree";
import type { Character } from "../../src/app/charactersApi";
import { CharactersState } from "../../src/app/charactersState";
import type { Session } from "../../src/app/sessionsApi";
import { applySession, SessionsState } from "../../src/app/sessionsState";
import { TREE_COLLAPSED_KEY } from "../../src/app/treeCollapse";
import { WORKSPACE_LAYOUT_KEY } from "../../src/app/workspaceLayout";
import { documentNavigation } from "../../src/shared/api";
import { AppProviders } from "../../src/shared/AppProviders";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string };
type User = ReturnType<typeof userEvent.setup>;
type StorageFake = ReturnType<typeof fakeStorage>;

// ---------------------------------------------------------------- the spec's names
const SEARCH_NAME = /^search$/i;
const NEW_CHARACTER_NAME = /^new character$/i;
const SHOW_ARCHIVED_NAME = /^show archived$/i;
const CHARACTERS_LIST_NAME = /^characters$/i;
const RETRY_NAME = /^retry$/i;
const ARCHIVED_BADGE = "Archived";
const LOAD_FAILED_TEXT = "Could not load characters";

const NOTIFICATION = ".mantine-Notification-root";

// 011 step 006 (D7, D16, D18): the session level's own names.
const SESSIONS_FAILED_TEXT = "Could not load sessions";
// 034 step 004: a never-renamed session's label is the local start DATE, no time (DEC-034-9).
const START_LABEL_SHAPE = /^\d{4}-\d{2}-\d{2}$/;
/** The same shape, matched inside a row that also carries a setup label. */
const START_LABEL_IN_TEXT = /\d{4}-\d{2}-\d{2}/;

/**
 * 034 step 004: the local `YYYY-MM-DD` of `instant` in the runtime's zone — the expected label
 * of a never-renamed session, from Intl directly (independent of the code under test).
 */
function localDate(instant: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(instant));
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((candidate) => candidate.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

/**
 * 034 step 006: the local `YYYY-MM-DD HH:MM` (24-hour, zero-padded) of `instant` in the runtime's
 * zone — the expected last-use time on a row's line 2, from Intl directly.
 */
function localDateTime(instant: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(instant));
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((candidate) => candidate.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")} ${part("hour")}:${part("minute")}`;
}

/**
 * 034 step 006 (DEC-034-9): a row's expected line 2 — the last-use time, then ` · ` and the
 * setup name when there is one, the time alone otherwise.
 */
function expectedLine2(row: Session): string {
  const time = localDateTime(row.last_used_at);
  return row.setup_name === null ? time : `${time} · ${row.setup_name}`;
}

/** Collapses runs of whitespace and trims — how a reader sees an element's text. */
function normalised(text: string | null | undefined): string {
  return (text ?? "").replace(/\s+/g, " ").trim();
}

/** Every element under `container` whose whole normalised text is exactly `text`. */
function elementsWithText(container: HTMLElement, text: string): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>("*")).filter(
    (element) => normalised(element.textContent) === text,
  );
}

const COLLECTION_PATH = "/api/characters";
const SESSIONS_PATH = "/api/sessions";
const INCLUDE_ARCHIVED_SEARCH = "?include_archived=true";
const SEARCH_PATH = "/search";
const NEW_CHARACTER_PATH = "/characters/new";

// ---------------------------------------------------------------- fixtures
// Both ids are past Number.MAX_SAFE_INTEGER (9007199254740991), so any coercion of the
// payload's id would show up in the row's href (context.md "Ids are strings"). The payload
// order below is neither alphabetical nor id-ordered, so "in the payload's order" is
// distinguishable from any sort the tree might apply.
const ID_CORVIN = "9007199254740993";
const ID_ARIA = "7250000000000000011";

const CORVIN: Character = {
  id: ID_CORVIN,
  name: "Corvin Hale",
  sheet: "A duelist who counts his scars.",
  archived_at: null,
  created_at: "2026-02-01T08:15:42.000000+00:00",
  updated_at: "2026-02-01T08:15:42.000000+00:00",
};

const ARIA: Character = {
  id: ID_ARIA,
  name: "Aria Vance",
  sheet: "A scribe who never finishes a sentence.",
  archived_at: null,
  created_at: "2026-03-14T09:26:53.000000+00:00",
  updated_at: "2026-03-14T09:26:53.000000+00:00",
};

const ARCHIVED_ARIA: Character = {
  ...ARIA,
  archived_at: "2026-04-05T10:00:00.000000+00:00",
  updated_at: "2026-04-05T10:00:00.000000+00:00",
};

/** The payload order the tree must preserve. */
const PAYLOAD = [CORVIN, ARIA];

// -------------------------------------------- 011 step 006 fixtures (D6, D7, D16)
// A third character, so DoD-1's three-way order (C, A, B) is distinguishable from both the
// payload order (A, B, C) and any alphabetical or id order. The letters below are the step
// file's: A = Corvin Hale (older session), B = Aria Vance (no session), C = Thea Brightwater
// (the most recent session).
const ID_THEA = "9007199254740997";

const THEA: Character = {
  id: ID_THEA,
  name: "Thea Brightwater",
  sheet: "A tidewatcher who writes in salt.",
  archived_at: null,
  created_at: "2026-01-09T07:01:02.000000+00:00",
  updated_at: "2026-01-09T07:01:02.000000+00:00",
};

/** The characters payload's order for DoD-1: A, B, C. */
const PAYLOAD_ABC = [CORVIN, ARIA, THEA];

// Every session id is past Number.MAX_SAFE_INTEGER, and `created_at` deliberately runs in a
// different order than `last_used_at`, so an ordering taken from either the id or the creation
// stamp would show up (011 context.md "Ids are strings"; the `setupsSectionState` convention).
const SID_A_NEW = "9007199254740993001";
const SID_A_OLD = "7250000000000000021";
const SID_B = "7250000000000000031";
const SID_C = "9007199254740999";
const SID_APPLIED = "9123456789012345678";

const SETUP_ID = "8100000000000000001";
const SETUP_NAME = "Tavern";

function session(fields: {
  id: string;
  characterId: string;
  lastUsedAt: string;
  createdAt: string;
  setupName?: string;
  archivedAt?: string;
  /** 034 step 004: the stored session name; omitted means never renamed (null). */
  name?: string;
}): Session {
  const named = fields.setupName !== undefined;
  return {
    id: fields.id,
    character_id: fields.characterId,
    setup_id: named ? SETUP_ID : null,
    setup_name: named ? fields.setupName ?? null : null,
    name: fields.name ?? null,
    archived_at: fields.archivedAt ?? null,
    last_used_at: fields.lastUsedAt,
    created_at: fields.createdAt,
    updated_at: fields.lastUsedAt,
  };
}

/** A's newer session, the one carrying a setup label (DoD-3). */
const SESSION_A_NEW = session({
  id: SID_A_NEW,
  characterId: ID_CORVIN,
  lastUsedAt: "2026-05-10T09:00:00.000000+00:00",
  createdAt: "2026-05-10T09:00:00.000000+00:00",
  setupName: SETUP_NAME,
});

/** A's older session, with no setup at all (DoD-3's second half). */
const SESSION_A_OLD = session({
  id: SID_A_OLD,
  characterId: ID_CORVIN,
  lastUsedAt: "2026-05-01T18:30:00.000000+00:00",
  createdAt: "2026-06-30T18:30:00.000000+00:00",
});

/** B's only session, used where B must have one (the archived-character clause, DoD-7). */
const SESSION_B = session({
  id: SID_B,
  characterId: ID_ARIA,
  lastUsedAt: "2026-04-01T11:11:11.000000+00:00",
  createdAt: "2026-04-01T11:11:11.000000+00:00",
});

/** C's session: the most recent last use in the payload, so C sorts first (DoD-1). */
const SESSION_C = session({
  id: SID_C,
  characterId: ID_THEA,
  lastUsedAt: "2026-06-20T23:59:00.000000+00:00",
  createdAt: "2026-02-02T23:59:00.000000+00:00",
});

/**
 * The server's order for both listings: `last_used_at DESC` (D14). C, then A's two, then B's.
 */
const SESSIONS_PAYLOAD = [SESSION_C, SESSION_A_NEW, SESSION_A_OLD];

let navigate: MockInstance<(url: string) => void>;

beforeEach(() => {
  navigate = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- fetch harness
function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function serverError(): Response {
  return jsonResponse({ error: { code: "internal_error", message: "ql-77.", detail: {} } }, 500);
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

/** Records every request in order and answers through `handler`. */
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

/**
 * Answers the listing from `rows`, honouring the include-archived flag, and — 011 step 006 —
 * the workspace sessions listing from `sessions` (empty by default, which is the form 009's
 * clauses keep: DoD-13). Both are matched on the **exact** pathname.
 */
function serveListing(working: Character[], archived: Character[] = [], sessions: Session[] = []) {
  return stubBackend((request) => {
    if (request.method === "GET" && request.path === COLLECTION_PATH) {
      const includeArchived = request.search === INCLUDE_ARCHIVED_SEARCH;
      const rows = includeArchived ? [...working, ...archived] : working;
      return jsonResponse({ characters: rows }, 200);
    }
    if (request.method === "GET" && request.path === SESSIONS_PATH) {
      return jsonResponse({ sessions }, 200);
    }
    return jsonResponse({ error: { code: "not_found", message: "", detail: {} } }, 404);
  });
}

function listRequests(calls: Seen[]): Seen[] {
  return calls.filter((call) => call.method === "GET" && call.path === COLLECTION_PATH);
}

/** 011 step 006: keyed on the exact sessions path, never on a prefix of `/api/characters`. */
function sessionsRequests(calls: Seen[]): Seen[] {
  return calls.filter((call) => call.method === "GET" && call.path === SESSIONS_PATH);
}

/**
 * 011 step 006, DoD-8: the characters listing succeeds; the sessions listing fails once and
 * then answers `SESSIONS_PAYLOAD`, so one "Retry" press is the whole clause.
 */
function serveFailingSessions() {
  let failNext = true;
  return stubBackend((request) => {
    if (request.method === "GET" && request.path === COLLECTION_PATH) {
      return jsonResponse({ characters: PAYLOAD_ABC }, 200);
    }
    if (request.method === "GET" && request.path === SESSIONS_PATH) {
      if (failNext) {
        failNext = false;
        return serverError();
      }
      return jsonResponse({ sessions: SESSIONS_PAYLOAD }, 200);
    }
    return jsonResponse({ error: { code: "not_found", message: "", detail: {} } }, 404);
  });
}

async function flush(rounds = 6): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => setImmediate(resolve));
    });
  }
}

function newUser(): User {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

// -------------------------------------------------- 011 step 006: the collapse storage
// An in-memory `LayoutStorage` with spy-able getItem/setItem (008's own test convention), so
// "which keys were written" is assertable — DoD-6 needs 008's workspace-layout key to stay
// untouched by a chevron toggle.

function fakeStorage(collapsed?: readonly string[]) {
  const values = new Map<string, string>();
  if (collapsed !== undefined) {
    values.set(TREE_COLLAPSED_KEY, JSON.stringify([...collapsed]));
  }
  const getItem = vi.fn((key: string): string | null => values.get(key) ?? null);
  const setItem = vi.fn((key: string, value: string): void => {
    values.set(key, value);
  });
  return { getItem, setItem, values };
}

/** Whatever sits under `rphelper.tree-collapsed`, parsed; `null` when nothing was stored. */
function storedCollapsed(store: StorageFake): unknown {
  const raw = store.values.get(TREE_COLLAPSED_KEY);
  return raw === undefined ? null : (JSON.parse(raw) as unknown);
}

/** Every key the component wrote, in order. */
function writtenKeys(store: StorageFake): string[] {
  return store.setItem.mock.calls.map((call) => call[0]);
}

// ---------------------------------------------------------------- render
function LocationProbe() {
  const location = useLocation();
  return (
    <>
      <output data-testid="probe-location">{location.pathname}</output>
      {/* S029_006_DoD1: the query string, so a clause can read the submitted `q` back. */}
      <output data-testid="probe-search">{location.search}</output>
    </>
  );
}

const TREE_HOST = "tree-host";

/**
 * The tree alone, at `initialPath`, with one workspace `CharactersState` (D11) and a location
 * probe beside it. The tree sits outside `<Routes>` in the shell (008.context.md), so nothing
 * declares routes here.
 */
function renderTree(
  initialPath = "/",
  characters = new CharactersState(),
  // 011 step 006: both props are required; a fresh workspace sessions state per render (D15)
  // and a storage that holds nothing unless a clause puts something in it (D7).
  sessions = new SessionsState(),
  storage: StorageFake | null = null,
) {
  const view = render(
    <AppProviders>
      <MemoryRouter initialEntries={[initialPath]}>
        <div data-testid={TREE_HOST}>
          <CharacterTree characters={characters} sessions={sessions} storage={storage} />
        </div>
        <LocationProbe />
      </MemoryRouter>
    </AppProviders>,
  );
  return { characters, sessions, storage, view };
}

// ---------------------------------------------------------------- queries
function tree(): HTMLElement {
  return screen.getByTestId(TREE_HOST);
}

function currentPath(): string {
  return screen.getByTestId("probe-location").textContent ?? "";
}

// S029_006_DoD1: the location's query string, and the `q` it carries read back **decoded**.
function currentSearch(): string {
  return screen.getByTestId("probe-search").textContent ?? "";
}

function currentQuery(): string | null {
  return new URLSearchParams(currentSearch()).get("q");
}

/** The character level, by its accessible name (a list or the equivalent landmark). */
function charactersList(): HTMLElement {
  const asList = within(tree()).queryByRole("list", { name: CHARACTERS_LIST_NAME });
  if (asList !== null) {
    return asList;
  }
  return within(tree()).getByRole("navigation", { name: CHARACTERS_LIST_NAME });
}

function rowLinks(): HTMLElement[] {
  return within(charactersList()).queryAllByRole("link");
}

function rowTexts(): string[] {
  return rowLinks().map((link) => (link.textContent ?? "").trim());
}

function queryRowFor(name: string): HTMLElement | null {
  return rowLinks().find((link) => (link.textContent ?? "").includes(name)) ?? null;
}

function rowFor(name: string): HTMLElement {
  const link = queryRowFor(name);
  if (link === null) {
    throw new Error(`no tree row for "${name}"`);
  }
  return link;
}

/** A row's whole block: the link, or the list item it sits in when the badge is a sibling. */
function rowBlock(name: string): HTMLElement {
  const link = rowFor(name);
  return link.closest("li") ?? link;
}

function treeButton(name: RegExp): HTMLElement {
  return within(tree()).getByRole("button", { name });
}

/** S029_006_DoD1: the header's search field, by its accessible name "Search". */
function searchBox(): HTMLElement {
  return within(tree()).getByRole("textbox", { name: SEARCH_NAME });
}

function showArchivedSwitch(): HTMLElement {
  const asSwitch = within(tree()).queryByRole("switch", { name: SHOW_ARCHIVED_NAME });
  if (asSwitch !== null) {
    return asSwitch;
  }
  return within(tree()).getByRole("checkbox", { name: SHOW_ARCHIVED_NAME });
}

function switchCount(): number {
  return (
    within(tree()).queryAllByRole("switch").length +
    within(tree()).queryAllByRole("checkbox").length
  );
}

function notificationsShown(): Element[] {
  return Array.from(document.querySelectorAll(NOTIFICATION));
}

// ------------------------------------------- 011 step 006: the session level's queries
// 009's `rowLinks()` collects every link inside the "Characters" list, which from 011 also
// holds the nested session rows, so the clauses below separate the two levels by `href`:
// a character row points at `/characters/<id>`, a session row at `/sessions/<id>`.

function href(element: Element): string {
  return element.getAttribute("href") ?? "";
}

function characterLinks(): HTMLElement[] {
  return rowLinks().filter((link) => href(link).startsWith("/characters/"));
}

function characterTexts(): string[] {
  return characterLinks().map((link) => (link.textContent ?? "").trim());
}

/** Every session row anywhere in the tree. */
function sessionLinks(): HTMLElement[] {
  return within(tree())
    .queryAllByRole("link")
    .filter((link) => href(link).startsWith("/sessions/"));
}

function sessionHrefs(): string[] {
  return sessionLinks().map((link) => href(link));
}

function sessionsListName(characterName: string): RegExp {
  return new RegExp(`^sessions of ${characterName}$`, "i");
}

/** The nested list under a character, by its accessible name "Sessions of <name>". */
function querySessionsListFor(characterName: string): HTMLElement | null {
  return within(tree()).queryByRole("list", { name: sessionsListName(characterName) });
}

function sessionsListFor(characterName: string): HTMLElement {
  return within(tree()).getByRole("list", { name: sessionsListName(characterName) });
}

/** The session rows under one character, in rendered order, as hrefs. */
function sessionHrefsUnder(characterName: string): string[] {
  return within(sessionsListFor(characterName))
    .queryAllByRole("link")
    .map((link) => href(link));
}

function sessionRow(sessionId: string): HTMLElement {
  const row = sessionLinks().find((link) => href(link) === `/sessions/${sessionId}`);
  if (row === undefined) {
    throw new Error(`no session row for /sessions/${sessionId}`);
  }
  return row;
}

function querySessionRow(sessionId: string): HTMLElement | null {
  return sessionLinks().find((link) => href(link) === `/sessions/${sessionId}`) ?? null;
}

/** 034 step 006: a session row's whole block — the `li` holding its link (011 harvest). */
function sessionItem(sessionId: string): HTMLElement {
  const link = sessionRow(sessionId);
  const item = link.closest("li");
  if (item === null) throw new Error(`the session row for /sessions/${sessionId} is not in a li`);
  return item;
}

/**
 * 034 step 006: what a row shows besides its line 2 — the row block's text with the expected
 * line 2 taken out. For a row showing "label + line 2" (and an icon-only button), this is the
 * label; it replaces 004's "the link's whole text is the label".
 */
function rowLabelText(row: Session): string {
  return normalised(normalised(sessionItem(row.id).textContent).replace(expectedLine2(row), ""));
}

function queryChevron(characterName: string, verb: "collapse" | "expand"): HTMLElement | null {
  return within(tree()).queryByRole("button", {
    name: new RegExp(`^${verb} ${characterName}$`, "i"),
  });
}

function chevron(characterName: string, verb: "collapse" | "expand"): HTMLElement {
  const button = queryChevron(characterName, verb);
  if (button === null) {
    throw new Error(`no "${verb} ${characterName}" control in the tree`);
  }
  return button;
}

// ---------------------------------------------------------------------------
describe("the character level renders the server's rows (US-022.AC-1)", () => {
  it("requests the listing once and renders one link per character in the payload's order — DoD-1", async () => {
    const { calls } = serveListing(PAYLOAD);
    renderTree();
    await flush();

    const requests = listRequests(calls);
    expect(requests).toHaveLength(1);
    expect(requests[0]).toEqual({ method: "GET", path: COLLECTION_PATH, search: "" });
    // 011 step 006: the tree now also loads the workspace sessions once on mount, so the
    // "nothing else is requested" half of this clause is the two listings and nothing more.
    expect(sessionsRequests(calls)).toHaveLength(1);
    expect(calls).toHaveLength(2);

    expect(charactersList()).toBeInTheDocument();
    expect(rowTexts()).toEqual([CORVIN.name, ARIA.name]);
  });

  it("each row links to /characters/<id> with the id string verbatim — DoD-1", async () => {
    serveListing(PAYLOAD);
    renderTree();
    await flush();

    expect(rowFor(CORVIN.name)).toHaveAttribute("href", `/characters/${ID_CORVIN}`);
    expect(rowFor(ARIA.name)).toHaveAttribute("href", `/characters/${ID_ARIA}`);
  });

  it("an empty listing renders no rows — DoD-1", async () => {
    serveListing([]);
    renderTree();
    await flush();

    expect(rowLinks()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("a row is an in-entry link that marks its own route", () => {
  it("clicking a row moves the in-entry router to /characters/<id> with no document navigation — DoD-2", async () => {
    const user = newUser();
    serveListing(PAYLOAD);
    renderTree();
    await flush();
    expect(currentPath()).toBe("/");

    await user.click(rowFor(ARIA.name));
    await flush();

    expect(currentPath()).toBe(`/characters/${ID_ARIA}`);
    expect(navigate).not.toHaveBeenCalled();
  });

  it("rendered at /characters/<id>, that row alone carries aria-current=page — DoD-2", async () => {
    serveListing(PAYLOAD);
    renderTree(`/characters/${ID_ARIA}`);
    await flush();

    expect(rowFor(ARIA.name)).toHaveAttribute("aria-current", "page");
    expect(rowFor(CORVIN.name).getAttribute("aria-current")).not.toBe("page");
  });

  it("at /characters/new no row is current — DoD-2", async () => {
    serveListing(PAYLOAD);
    renderTree(NEW_CHARACTER_PATH);
    await flush();

    for (const link of rowLinks()) {
      expect(link.getAttribute("aria-current")).not.toBe("page");
    }
  });
});

// ---------------------------------------------------------------------------
describe("the header's two actions navigate in-entry (D13; 029 U4, US-118.AC-1)", () => {
  // S029_006_DoD1: this clause replaces 009 008 DoD-3's "Search moves the in-entry router to
  // /search", which clicked a button. The header now holds a textbox named "Search", and
  // Enter submits it to `/search?q=<text>`; the three cases below are 029 step 006 DoD-1.
  it("(009 008 DoD-3, amended: Search was an icon button) typing mira and pressing Enter moves the in-entry router to /search with q decoding to mira — DoD-1", async () => {
    const user = newUser();
    serveListing(PAYLOAD);
    renderTree();
    await flush();

    await user.type(searchBox(), "mira{Enter}");
    await flush();

    expect(currentPath()).toBe(SEARCH_PATH);
    expect(currentQuery()).toBe("mira");
    expect(navigate).not.toHaveBeenCalled();
  });

  it("a query holding an ampersand and a space submits a q that decodes to it unchanged — DoD-1", async () => {
    const user = newUser();
    serveListing(PAYLOAD);
    renderTree();
    await flush();

    await user.type(searchBox(), "a&b c{Enter}");
    await flush();

    expect(currentPath()).toBe(SEARCH_PATH);
    expect(currentQuery()).toBe("a&b c");
    expect(navigate).not.toHaveBeenCalled();
  });

  it("Enter on an empty box moves the in-entry router to /search — DoD-1", async () => {
    const user = newUser();
    serveListing(PAYLOAD);
    renderTree();
    await flush();

    const box = searchBox();
    expect(box).toHaveValue("");
    await user.type(box, "{Enter}");
    await flush();

    expect(currentPath()).toBe(SEARCH_PATH);
    expect(currentSearch()).toBe("");
    expect(navigate).not.toHaveBeenCalled();
  });

  it("New character moves the in-entry router to /characters/new — DoD-3", async () => {
    const user = newUser();
    serveListing(PAYLOAD);
    renderTree();
    await flush();

    await user.click(treeButton(NEW_CHARACTER_NAME));
    await flush();

    expect(currentPath()).toBe(NEW_CHARACTER_PATH);
    expect(navigate).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("the Show archived switch re-requests the listing (D4, R6)", () => {
  it("is off on a fresh mount and the first request carries no flag — DoD-4", async () => {
    const { calls } = serveListing([CORVIN], [ARCHIVED_ARIA]);
    renderTree();
    await flush();

    expect(showArchivedSwitch()).not.toBeChecked();
    expect(listRequests(calls)).toHaveLength(1);
    expect(listRequests(calls)[0].search).toBe("");
    expect(queryRowFor(ARIA.name)).toBeNull();
  });

  it("turning it on requests include_archived=true and badges the archived row — DoD-4", async () => {
    const user = newUser();
    const { calls } = serveListing([CORVIN], [ARCHIVED_ARIA]);
    renderTree();
    await flush();

    await user.click(showArchivedSwitch());
    await flush();

    const requests = listRequests(calls);
    expect(requests).toHaveLength(2);
    expect(requests[1]).toEqual({
      method: "GET",
      path: COLLECTION_PATH,
      search: INCLUDE_ARCHIVED_SEARCH,
    });

    expect(within(rowBlock(ARIA.name)).getByText(ARCHIVED_BADGE)).toBeInTheDocument();
    expect(within(rowBlock(CORVIN.name)).queryByText(ARCHIVED_BADGE)).toBeNull();
  });

  it("turning it off again requests the working list and drops the archived row — DoD-4", async () => {
    const user = newUser();
    const { calls } = serveListing([CORVIN], [ARCHIVED_ARIA]);
    renderTree();
    await flush();

    await user.click(showArchivedSwitch());
    await flush();
    expect(queryRowFor(ARIA.name)).not.toBeNull();

    await user.click(showArchivedSwitch());
    await flush();

    const requests = listRequests(calls);
    expect(requests).toHaveLength(3);
    expect(requests[2]).toEqual({ method: "GET", path: COLLECTION_PATH, search: "" });
    expect(showArchivedSwitch()).not.toBeChecked();
    expect(queryRowFor(ARIA.name)).toBeNull();
    expect(queryRowFor(CORVIN.name)).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
// 011 step 006: the clauses below are about the **characters** load failing. The sessions
// listing is answered (empty) in each, so the tree's single "Retry" is unambiguously the
// character level's — the sessions failure has its own text and its own Retry (011 DoD-8).
describe("a failed load reports inside the tree (D12)", () => {
  it("renders Could not load characters and Retry, and raises no notification — DoD-5", async () => {
    stubBackend((request) =>
      request.path === SESSIONS_PATH ? jsonResponse({ sessions: [] }, 200) : serverError(),
    );
    renderTree();
    await flush();

    expect(within(tree()).getByText(LOAD_FAILED_TEXT)).toBeInTheDocument();
    expect(treeButton(RETRY_NAME)).toBeInTheDocument();
    expect(notificationsShown()).toEqual([]);
  });

  it("a transport failure reports the same way — DoD-5", async () => {
    stubBackend((request) => {
      if (request.path === SESSIONS_PATH) return jsonResponse({ sessions: [] }, 200);
      return Promise.reject(new TypeError("Failed to fetch"));
    });
    renderTree();
    await flush();

    expect(within(tree()).getByText(LOAD_FAILED_TEXT)).toBeInTheDocument();
    expect(treeButton(RETRY_NAME)).toBeInTheDocument();
    expect(notificationsShown()).toEqual([]);
  });

  it("Retry requests the listing again and renders the rows on success — DoD-5", async () => {
    const user = newUser();
    let failNext = true;
    const { calls } = stubBackend((request) => {
      if (request.method === "GET" && request.path === COLLECTION_PATH) {
        if (failNext) {
          failNext = false;
          return serverError();
        }
        return jsonResponse({ characters: PAYLOAD }, 200);
      }
      // 011 step 006: the sessions listing succeeds, so "Retry" names one control only.
      if (request.method === "GET" && request.path === SESSIONS_PATH) {
        return jsonResponse({ sessions: [] }, 200);
      }
      return serverError();
    });
    renderTree();
    await flush();
    expect(listRequests(calls)).toHaveLength(1);

    await user.click(treeButton(RETRY_NAME));
    await flush();

    expect(listRequests(calls)).toHaveLength(2);
    expect(rowTexts()).toEqual([CORVIN.name, ARIA.name]);
    expect(within(tree()).queryByText(LOAD_FAILED_TEXT)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// 011 step 006, DoD-13: every clause in this block renders with an **empty** sessions payload
// (`serveListing`'s default), which is the form in which they stay true and keep meaning
// something — a character with no session carries no chevron and contributes no session row
// (011 D7, D16). The sessions-present behaviour they would otherwise contradict is covered by
// 011's DoD-5, DoD-6 and DoD-2 blocks below. Nothing here was deleted.
describe("no chevron and no session rows in 009 (D13)", () => {
  it("the ready tree's only button is New character — DoD-6", async () => {
    serveListing([CORVIN], [ARCHIVED_ARIA]);
    renderTree();
    await flush();
    expect(rowLinks()).toHaveLength(1);

    const names = within(tree())
      .getAllByRole("button")
      .map((button) => (button.getAttribute("aria-label") ?? button.textContent ?? "").trim());
    // S029_006_DoD2: "Search" has left the button set — it is the header's textbox now.
    expect([...names].sort()).toEqual(["New character"]);
  });

  it("the switch and the search field are the tree's only other controls and the rows are links — DoD-6", async () => {
    serveListing(PAYLOAD);
    renderTree();
    await flush();

    expect(switchCount()).toBe(1);
    expect(showArchivedSwitch()).toBeInTheDocument();
    // S029_006_DoD2: the tree held no textbox before 029; it now holds exactly one, the
    // header's search field, found by its accessible name "Search".
    const textboxes = within(tree()).queryAllByRole("textbox");
    expect(textboxes).toHaveLength(1);
    expect(textboxes[0]).toBe(searchBox());
    expect(rowLinks()).toHaveLength(PAYLOAD.length);
    expect(within(tree()).getAllByRole("link")).toHaveLength(PAYLOAD.length);
  });

  it("no row carries an expand or collapse control — DoD-6", async () => {
    serveListing(PAYLOAD);
    renderTree();
    await flush();

    for (const name of [CORVIN.name, ARIA.name]) {
      expect(within(rowBlock(name)).queryAllByRole("button")).toEqual([]);
    }
    expect(within(tree()).queryByRole("button", { name: /expand|collapse/i })).toBeNull();
  });
});

// ===========================================================================
// Feature 011, step 006 — the session level, the chevron and the character order.
// ===========================================================================

// ---------------------------------------------------------------------------
describe("the 009-era clauses hold unchanged with an empty sessions payload (011 D7, D16)", () => {
  it("no chevron, no session row, and the characters keep the payload's order — DoD-13", async () => {
    serveListing(PAYLOAD_ABC, [], []);
    renderTree();
    await flush();

    expect(characterTexts()).toEqual([CORVIN.name, ARIA.name, THEA.name]);
    expect(sessionLinks()).toEqual([]);
    expect(within(tree()).queryByRole("button", { name: /expand|collapse/i })).toBeNull();

    const names = within(tree())
      .getAllByRole("button")
      .map((button) => (button.getAttribute("aria-label") ?? button.textContent ?? "").trim());
    // S029_006_DoD2: same amendment as the 009-era census — "Search" is a textbox now.
    expect([...names].sort()).toEqual(["New character"]);
  });
});

// ---------------------------------------------------------------------------
describe("characters are ordered by newest session use (D6)", () => {
  it("the payload order A, B, C renders as C, A, B — DoD-1", async () => {
    serveListing(PAYLOAD_ABC, [], SESSIONS_PAYLOAD);
    renderTree();
    await flush();

    expect(characterTexts()).toEqual([THEA.name, CORVIN.name, ARIA.name]);
  });

  it("a character with no session follows the ones that have sessions — DoD-1", async () => {
    serveListing(PAYLOAD_ABC, [], SESSIONS_PAYLOAD);
    renderTree();
    await flush();

    const order = characterTexts();
    expect(order.indexOf(ARIA.name)).toBe(order.length - 1);
    expect(querySessionsListFor(ARIA.name)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("an expanded character lists its own sessions in last-use order (US-089.AC-1, UC-069)", () => {
  it("the Sessions of <name> list holds exactly that character's rows, in payload order — DoD-2", async () => {
    serveListing(PAYLOAD_ABC, [], SESSIONS_PAYLOAD);
    renderTree();
    await flush();

    expect(sessionHrefsUnder(CORVIN.name)).toEqual([
      `/sessions/${SID_A_NEW}`,
      `/sessions/${SID_A_OLD}`,
    ]);
    expect(sessionHrefsUnder(THEA.name)).toEqual([`/sessions/${SID_C}`]);
  });

  it("no session of another character appears under a character — DoD-2", async () => {
    serveListing(PAYLOAD_ABC, [], SESSIONS_PAYLOAD);
    renderTree();
    await flush();

    expect(sessionHrefsUnder(CORVIN.name)).not.toContain(`/sessions/${SID_C}`);
    expect(sessionHrefsUnder(THEA.name)).not.toContain(`/sessions/${SID_A_NEW}`);
    expect(sessionHrefs().sort()).toEqual(
      [`/sessions/${SID_A_NEW}`, `/sessions/${SID_A_OLD}`, `/sessions/${SID_C}`].sort(),
    );
  });
});

// ---------------------------------------------------------------------------
describe("a session row shows its setup as a label, or nothing (US-088.AC-1, US-088.AC-2)", () => {
  it("the row of a session whose setup_name is Tavern shows Tavern — DoD-3", async () => {
    serveListing(PAYLOAD_ABC, [], SESSIONS_PAYLOAD);
    renderTree();
    await flush();

    // S034_006_DoD1: the setup name now sits in line 2, after the last-use time and ` · `.
    expect(sessionItem(SID_A_NEW).textContent ?? "").toContain(SETUP_NAME);
    expect(elementsWithText(sessionItem(SID_A_NEW), expectedLine2(SESSION_A_NEW))).not.toEqual([]);
  });

  it("a session with no setup shows only its label, the local start date — DoD-3, S034_004_DoD7, S034_006_DoD1", async () => {
    serveListing(PAYLOAD_ABC, [], SESSIONS_PAYLOAD);
    renderTree();
    await flush();

    // 034: never renamed, so the label is the local date of created_at (not of last_used_at,
    // which this fixture deliberately puts on another day), with no time. S034_006_DoD1: the
    // row also carries line 2 (the last-use time alone), so the label is read beside it.
    const text = rowLabelText(SESSION_A_OLD);
    expect(text).toMatch(START_LABEL_SHAPE);
    expect(text).toBe(localDate(SESSION_A_OLD.created_at));
    expect(sessionItem(SID_A_OLD).textContent ?? "").not.toContain(SETUP_NAME);
  });

  it("the labelled row also carries its date label — DoD-3, S034_004_DoD7", async () => {
    serveListing(PAYLOAD_ABC, [], SESSIONS_PAYLOAD);
    renderTree();
    await flush();

    // Beside the setup label, so the shape is matched inside the row's text rather than over
    // the whole of it; the exact value stays 005's formatter's business.
    expect(sessionRow(SID_A_NEW).textContent ?? "").toMatch(START_LABEL_IN_TEXT);
    expect(sessionRow(SID_A_NEW).textContent ?? "").toContain(localDate(SESSION_A_NEW.created_at));
  });
});

// ---------------------------------------------------------------------------
describe("a session row is an in-entry link that marks its own route (UC-069, UC-024)", () => {
  it("clicking a session row moves the in-entry router to /sessions/<id> — DoD-4", async () => {
    const user = newUser();
    serveListing(PAYLOAD_ABC, [], SESSIONS_PAYLOAD);
    renderTree();
    await flush();
    expect(currentPath()).toBe("/");

    await user.click(sessionRow(SID_A_OLD));
    await flush();

    expect(currentPath()).toBe(`/sessions/${SID_A_OLD}`);
    expect(navigate).not.toHaveBeenCalled();
  });

  it("rendered at /sessions/<id>, that session row alone is aria-current=page — DoD-4", async () => {
    serveListing(PAYLOAD_ABC, [], SESSIONS_PAYLOAD);
    renderTree(`/sessions/${SID_A_OLD}`);
    await flush();

    expect(sessionRow(SID_A_OLD)).toHaveAttribute("aria-current", "page");
    for (const row of sessionLinks()) {
      if (href(row) === `/sessions/${SID_A_OLD}`) continue;
      expect(row.getAttribute("aria-current")).not.toBe("page");
    }
    for (const row of characterLinks()) {
      expect(row.getAttribute("aria-current")).not.toBe("page");
    }
  });
});

// ---------------------------------------------------------------------------
describe("the per-character chevron and the collapsed set (D7)", () => {
  it("with an empty storage a character with sessions is expanded and one without has no chevron — DoD-5", async () => {
    serveListing(PAYLOAD_ABC, [], SESSIONS_PAYLOAD);
    renderTree("/", new CharactersState(), new SessionsState(), fakeStorage());
    await flush();

    expect(chevron(CORVIN.name, "collapse")).toBeInTheDocument();
    expect(chevron(THEA.name, "collapse")).toBeInTheDocument();
    expect(queryChevron(CORVIN.name, "expand")).toBeNull();
    expect(sessionHrefsUnder(CORVIN.name)).toHaveLength(2);

    expect(queryChevron(ARIA.name, "collapse")).toBeNull();
    expect(queryChevron(ARIA.name, "expand")).toBeNull();
  });

  it("Collapse A hides A's rows, becomes Expand A and stores A's id — DoD-5", async () => {
    const user = newUser();
    const store = fakeStorage();
    serveListing(PAYLOAD_ABC, [], SESSIONS_PAYLOAD);
    renderTree("/", new CharactersState(), new SessionsState(), store);
    await flush();

    await user.click(chevron(CORVIN.name, "collapse"));
    await flush();

    expect(querySessionRow(SID_A_NEW)).toBeNull();
    expect(querySessionRow(SID_A_OLD)).toBeNull();
    expect(chevron(CORVIN.name, "expand")).toBeInTheDocument();
    expect(queryChevron(CORVIN.name, "collapse")).toBeNull();
    // C stays expanded: the set is per character.
    expect(querySessionRow(SID_C)).not.toBeNull();

    const stored = storedCollapsed(store);
    expect(Array.isArray(stored)).toBe(true);
    expect(stored as string[]).toContain(ID_CORVIN);
    expect(writtenKeys(store)).toContain(TREE_COLLAPSED_KEY);
  });

  it("a tree mounted over a stored A starts A collapsed and B expanded — DoD-6", async () => {
    serveListing(
      PAYLOAD_ABC,
      [],
      [SESSION_A_NEW, SESSION_A_OLD, SESSION_B],
    );
    renderTree("/", new CharactersState(), new SessionsState(), fakeStorage([ID_CORVIN]));
    await flush();

    expect(chevron(CORVIN.name, "expand")).toBeInTheDocument();
    expect(querySessionsListFor(CORVIN.name)).toBeNull();
    expect(querySessionRow(SID_A_NEW)).toBeNull();

    expect(chevron(ARIA.name, "collapse")).toBeInTheDocument();
    expect(querySessionRow(SID_B)).not.toBeNull();
  });

  it("Expand A shows A's rows and removes A's id from the stored array — DoD-6", async () => {
    const user = newUser();
    const store = fakeStorage([ID_CORVIN]);
    serveListing(PAYLOAD_ABC, [], [SESSION_A_NEW, SESSION_A_OLD, SESSION_B]);
    renderTree("/", new CharactersState(), new SessionsState(), store);
    await flush();

    await user.click(chevron(CORVIN.name, "expand"));
    await flush();

    expect(sessionHrefsUnder(CORVIN.name)).toEqual([
      `/sessions/${SID_A_NEW}`,
      `/sessions/${SID_A_OLD}`,
    ]);
    expect(chevron(CORVIN.name, "collapse")).toBeInTheDocument();

    const stored = storedCollapsed(store);
    expect(Array.isArray(stored)).toBe(true);
    expect(stored as string[]).not.toContain(ID_CORVIN);
  });

  it("a toggle never writes 008's workspace-layout record — DoD-6", async () => {
    const user = newUser();
    const store = fakeStorage([ID_CORVIN]);
    serveListing(PAYLOAD_ABC, [], [SESSION_A_NEW, SESSION_A_OLD, SESSION_B]);
    renderTree("/", new CharactersState(), new SessionsState(), store);
    await flush();

    await user.click(chevron(CORVIN.name, "expand"));
    await flush();
    await user.click(chevron(ARIA.name, "collapse"));
    await flush();

    expect(writtenKeys(store)).not.toContain(WORKSPACE_LAYOUT_KEY);
    expect(store.values.has(WORKSPACE_LAYOUT_KEY)).toBe(false);
    for (const key of writtenKeys(store)) {
      expect(key).toBe(TREE_COLLAPSED_KEY);
    }
  });
});

// ---------------------------------------------------------------------------
describe("the sessions load is its own effect, independent of Show archived (D5, D16)", () => {
  it("the sessions listing is requested once on mount and never with include_archived — DoD-7", async () => {
    const { calls } = serveListing(PAYLOAD_ABC, [], SESSIONS_PAYLOAD);
    renderTree();
    await flush();

    const requests = sessionsRequests(calls);
    expect(requests).toHaveLength(1);
    expect(requests[0]).toEqual({ method: "GET", path: SESSIONS_PATH, search: "" });
  });

  it("Show archived re-requests the characters listing but not the sessions listing — DoD-7", async () => {
    const user = newUser();
    const { calls } = serveListing([CORVIN], [ARCHIVED_ARIA], [SESSION_A_NEW, SESSION_B]);
    renderTree();
    await flush();
    expect(listRequests(calls)).toHaveLength(1);
    expect(sessionsRequests(calls)).toHaveLength(1);

    await user.click(showArchivedSwitch());
    await flush();

    expect(listRequests(calls)).toHaveLength(2);
    expect(sessionsRequests(calls)).toHaveLength(1);
  });

  it("an archived character's sessions appear with it and go away with it — DoD-7", async () => {
    const user = newUser();
    serveListing([CORVIN], [ARCHIVED_ARIA], [SESSION_A_NEW, SESSION_B]);
    renderTree();
    await flush();
    expect(queryRowFor(ARIA.name)).toBeNull();
    expect(querySessionRow(SID_B)).toBeNull();

    await user.click(showArchivedSwitch());
    await flush();

    expect(queryRowFor(ARIA.name)).not.toBeNull();
    expect(sessionHrefsUnder(ARIA.name)).toEqual([`/sessions/${SID_B}`]);

    await user.click(showArchivedSwitch());
    await flush();

    expect(queryRowFor(ARIA.name)).toBeNull();
    expect(querySessionRow(SID_B)).toBeNull();
    expect(querySessionRow(SID_A_NEW)).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("a failed sessions load reports inside the tree (D18)", () => {
  it("shows Could not load sessions and Retry, keeps the characters, notifies nothing — DoD-8", async () => {
    serveFailingSessions();
    renderTree();
    await flush();

    expect(within(tree()).getByText(SESSIONS_FAILED_TEXT)).toBeInTheDocument();
    expect(treeButton(RETRY_NAME)).toBeInTheDocument();
    expect(characterTexts()).toEqual([CORVIN.name, ARIA.name, THEA.name]);
    expect(within(tree()).queryByText(LOAD_FAILED_TEXT)).toBeNull();
    expect(sessionLinks()).toEqual([]);
    expect(notificationsShown()).toEqual([]);
  });

  it("Retry requests the sessions listing again and the rows render on success — DoD-8", async () => {
    const user = newUser();
    const { calls } = serveFailingSessions();
    renderTree();
    await flush();
    expect(sessionsRequests(calls)).toHaveLength(1);

    await user.click(treeButton(RETRY_NAME));
    await flush();

    expect(sessionsRequests(calls)).toHaveLength(2);
    expect(within(tree()).queryByText(SESSIONS_FAILED_TEXT)).toBeNull();
    expect(sessionHrefsUnder(CORVIN.name)).toEqual([
      `/sessions/${SID_A_NEW}`,
      `/sessions/${SID_A_OLD}`,
    ]);
  });
});

// ---------------------------------------------------------------------------
describe("applying a row to the workspace state re-renders the tree with no fetch (D15, US-027.AC-1)", () => {
  it("a new working session shows first under its character and moves it to the top — DoD-9", async () => {
    const { calls } = serveListing(PAYLOAD_ABC, [], SESSIONS_PAYLOAD);
    const { sessions } = renderTree();
    await flush();
    expect(characterTexts()).toEqual([THEA.name, CORVIN.name, ARIA.name]);
    const before = sessionsRequests(calls).length;

    const applied = session({
      id: SID_APPLIED,
      characterId: ID_CORVIN,
      lastUsedAt: "2026-07-01T06:00:00.000000+00:00",
      createdAt: "2026-07-01T06:00:00.000000+00:00",
    });
    await act(async () => {
      applySession(sessions, applied);
    });
    await flush();

    expect(sessionHrefsUnder(CORVIN.name)).toEqual([
      `/sessions/${SID_APPLIED}`,
      `/sessions/${SID_A_NEW}`,
      `/sessions/${SID_A_OLD}`,
    ]);
    expect(characterTexts()[0]).toBe(CORVIN.name);
    expect(sessionsRequests(calls)).toHaveLength(before);
  });

  it("the archived version of a listed session loses its row — DoD-9", async () => {
    const { calls } = serveListing(PAYLOAD_ABC, [], SESSIONS_PAYLOAD);
    const { sessions } = renderTree();
    await flush();
    expect(querySessionRow(SID_C)).not.toBeNull();
    const before = sessionsRequests(calls).length;

    await act(async () => {
      applySession(sessions, { ...SESSION_C, archived_at: "2026-06-21T00:00:00.000000+00:00" });
    });
    await flush();

    expect(querySessionRow(SID_C)).toBeNull();
    expect(querySessionRow(SID_A_NEW)).not.toBeNull();
    expect(sessionsRequests(calls)).toHaveLength(before);
  });
});

// ===========================================================================
// Feature 034, step 004 — S034_004_DoD7 on the tree row: a renamed session's row shows its
// name, a never-renamed one its local start date with no time (US-150.AC-1, US-150.AC-2,
// DEC-034-9). Only the row's label is asserted here; the two-line row is step 006's.
// ===========================================================================
describe("034 step 004 — a tree session row shows the session label", () => {
  /** A's older session, renamed (no setup, so the row's only text is the label). */
  const NAMED_A_OLD: Session = { ...SESSION_A_OLD, name: "Harbour at dusk" };
  /** A's newer session (with the Tavern setup), renamed to something date-like. */
  const DATE_NAMED_A_NEW: Session = { ...SESSION_A_NEW, name: "1999-12-31" };

  it("a renamed session's row shows its name — S034_004_DoD7", async () => {
    serveListing(PAYLOAD_ABC, [], [SESSION_C, SESSION_A_NEW, NAMED_A_OLD]);
    renderTree();
    await flush();

    expect(within(sessionItem(SID_A_OLD)).getByText("Harbour at dusk")).toBeInTheDocument();
    // S034_006_DoD1: the row's text besides its line 2 is exactly the name.
    expect(rowLabelText(NAMED_A_OLD)).toBe("Harbour at dusk");
  });

  it("a renamed session's row shows neither its start date nor a time in its label — S034_004_DoD7", async () => {
    serveListing(PAYLOAD_ABC, [], [SESSION_C, SESSION_A_NEW, NAMED_A_OLD]);
    renderTree();
    await flush();

    // S034_006_DoD1: line 2 carries the last-use time by design, so the label is checked apart.
    const text = rowLabelText(NAMED_A_OLD);
    expect(text).toContain("Harbour at dusk");
    expect(text).not.toContain(localDate(NAMED_A_OLD.created_at));
    expect(text).not.toMatch(/\d{2}:\d{2}/);
  });

  it("a date-like name is shown verbatim beside the setup label — S034_004_DoD7", async () => {
    serveListing(PAYLOAD_ABC, [], [SESSION_C, DATE_NAMED_A_NEW, SESSION_A_OLD]);
    renderTree();
    await flush();

    const item = sessionItem(SID_A_NEW);
    expect(within(item).getByText("1999-12-31")).toBeInTheDocument();
    // S034_006_DoD1: the setup name is in line 2, after the last-use time.
    expect(item.textContent ?? "").toContain(SETUP_NAME);
    expect(rowLabelText(DATE_NAMED_A_NEW)).toBe("1999-12-31");
  });

  it("a never-renamed session's row beside a renamed one shows its local start date, no time — S034_004_DoD7", async () => {
    serveListing(PAYLOAD_ABC, [], [SESSION_C, SESSION_A_NEW, NAMED_A_OLD]);
    renderTree();
    await flush();

    const text = rowLabelText(SESSION_C);
    expect(text).toBe(localDate(SESSION_C.created_at));
    expect(text).not.toMatch(/\d{2}:\d{2}/);
  });

  it("applying the renamed version of a listed session relabels its row with no fetch — S034_004_DoD7", async () => {
    const { calls } = serveListing(PAYLOAD_ABC, [], SESSIONS_PAYLOAD);
    const { sessions } = renderTree();
    await flush();
    expect(rowLabelText(SESSION_A_OLD)).toBe(localDate(SESSION_A_OLD.created_at));
    const before = sessionsRequests(calls).length;

    await act(async () => {
      applySession(sessions, NAMED_A_OLD);
    });
    await flush();

    expect(rowLabelText(NAMED_A_OLD)).toBe("Harbour at dusk");
    expect(sessionsRequests(calls)).toHaveLength(before);
  });
});

// ===========================================================================
// Feature 034, step 006 — the two-line tree row and the rename in place (S034_006_DoD1..DoD4,
// DoD6). Expected values: the step's Interface intent and DoD; DEC-034-9 (line 2 =
// `formatLocalDateTime(last_used_at)` then ` · <setup>`, or the time alone); DEC-034-10 (an
// "Rename session" button beside the link, never inside it; the editor replaces the link while
// that row is edited); DEC-034-11 (never optimistic, the returned row applied, Escape sends
// nothing, an inline failure keeps the draft); DEC-034-12 / US-150.AC-4 (a rename keeps the
// row's position). The step 005 editor's names: the textbox "Session name".
// ===========================================================================

const RENAME_BUTTON = /^rename session$/i;
const NAME_INPUT = /^session name$/i;
const RENAME_FAILED_TEXT = "Could not rename the session.";
/** Strictly newer than every fixture's `updated_at` — the rename answer's stamp. */
const RENAME_STAMP = "2026-08-01T12:00:00.000000+00:00";
const NEW_NAME = "Lantern Row";

/** A third session of A, between A's two in last use, created after both (DoD-2). */
const SID_A_MID = "8000000000000000041";
const SESSION_A_MID = session({
  id: SID_A_MID,
  characterId: ID_CORVIN,
  lastUsedAt: "2026-05-05T07:05:00.000000+00:00",
  createdAt: "2026-07-20T07:05:00.000000+00:00",
  setupName: SETUP_NAME,
});

type Patch = { path: string; body: unknown };

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

/**
 * The tree's two listings (characters `PAYLOAD_ABC`, sessions `rows`) plus the rename route
 * `PATCH /api/sessions/<id>`, every PATCH recorded with its parsed body. A successful rename
 * answers the stored row with the trimmed name (blank → null) and `updated_at` advanced, and
 * `last_used_at` unchanged (context.md "A rename writes name and updated_at only"). `gate`
 * holds the answer back until resolved; `fail` answers 500.
 */
function serveRenamable(rows: Session[], options: { fail?: boolean; gate?: Promise<void> } = {}) {
  const held = rows.map((row) => ({ ...row }));
  const patches: Patch[] = [];
  const mock = vi.fn<FetchFn>(async (input, init) => {
    const url = requestUrl(input);
    const method = requestMethod(input, init);
    if (method === "GET" && url.pathname === COLLECTION_PATH) {
      return jsonResponse({ characters: PAYLOAD_ABC }, 200);
    }
    if (method === "GET" && url.pathname === SESSIONS_PATH) {
      return jsonResponse({ sessions: held }, 200);
    }
    const item = /^\/api\/sessions\/([^/]+)$/.exec(url.pathname);
    if (method === "PATCH" && item !== null) {
      const raw = init?.body;
      const body: unknown = raw === undefined || raw === null ? undefined : JSON.parse(String(raw));
      patches.push({ path: url.pathname, body });
      if (options.gate !== undefined) await options.gate;
      if (options.fail === true) return serverError();
      const index = held.findIndex((row) => row.id === item[1]);
      if (index < 0) {
        return jsonResponse({ error: { code: "session_not_found", message: "", detail: {} } }, 404);
      }
      const sent = (body ?? {}) as { name?: unknown };
      const name =
        typeof sent.name === "string" && sent.name.trim() !== "" ? sent.name.trim() : null;
      const next: Session = { ...held[index], name, updated_at: RENAME_STAMP };
      held[index] = next;
      return jsonResponse(next, 200);
    }
    return jsonResponse({ error: { code: "not_found", message: "", detail: {} } }, 404);
  });
  vi.stubGlobal("fetch", mock);
  return { mock, patches };
}

function renameButtonOf(sessionId: string): HTMLElement {
  return within(sessionItem(sessionId)).getByRole("button", { name: RENAME_BUTTON });
}

function nameInput(): HTMLElement {
  return within(tree()).getByRole("textbox", { name: NAME_INPUT });
}

function queryNameInput(): HTMLElement | null {
  return within(tree()).queryByRole("textbox", { name: NAME_INPUT });
}

/** The workspace store's copy of one session. */
function storedRow(sessions: SessionsState, sessionId: string): Session | undefined {
  return sessions.sessions.find((row) => row.id === sessionId);
}

/** Whether `first` comes before `second` in document order. */
function precedes(first: Node, second: Node): boolean {
  return (first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

describe("034 step 006 — the tree session row has two lines (US-151.AC-1, US-088)", () => {
  it("a renamed row with a setup: line 1 is the name, line 2 is `YYYY-MM-DD HH:MM · <setup>` — S034_006_DoD1", async () => {
    const named: Session = { ...SESSION_A_NEW, name: "Harbour at dusk" };
    serveListing(PAYLOAD_ABC, [], [SESSION_C, named, SESSION_A_OLD]);
    renderTree();
    await flush();

    const item = sessionItem(SID_A_NEW);
    const line1 = elementsWithText(item, "Harbour at dusk");
    const line2 = elementsWithText(item, expectedLine2(named));
    expect(line1).not.toEqual([]);
    expect(line2).not.toEqual([]);
    expect(expectedLine2(named)).toBe(`${localDateTime(named.last_used_at)} · ${SETUP_NAME}`);
    expect(precedes(line1[0], line2[0])).toBe(true);
    expect(rowLabelText(named)).toBe("Harbour at dusk");
  });

  it("a never-renamed row with a setup: line 1 is the local start date, line 2 the last-use time and setup — S034_006_DoD1", async () => {
    serveListing(PAYLOAD_ABC, [], [SESSION_C, SESSION_A_MID]);
    renderTree();
    await flush();

    // created_at and last_used_at fall on different days, so line 1 and line 2 cannot be confused.
    const item = sessionItem(SID_A_MID);
    const line1 = elementsWithText(item, localDate(SESSION_A_MID.created_at));
    const line2 = elementsWithText(item, expectedLine2(SESSION_A_MID));
    expect(line1).not.toEqual([]);
    expect(line2).not.toEqual([]);
    expect(precedes(line1[0], line2[0])).toBe(true);
    expect(rowLabelText(SESSION_A_MID)).toBe(localDate(SESSION_A_MID.created_at));
  });

  it("a row with no setup: line 2 is the last-use time alone, with no separator — S034_006_DoD1", async () => {
    serveListing(PAYLOAD_ABC, [], SESSIONS_PAYLOAD);
    renderTree();
    await flush();

    const item = sessionItem(SID_A_OLD);
    const time = localDateTime(SESSION_A_OLD.last_used_at);
    expect(time).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
    const line1 = elementsWithText(item, localDate(SESSION_A_OLD.created_at));
    const line2 = elementsWithText(item, time);
    expect(line1).not.toEqual([]);
    expect(line2).not.toEqual([]);
    expect(precedes(line1[0], line2[0])).toBe(true);
    expect(item.textContent ?? "").not.toContain("·");
    expect(item.textContent ?? "").not.toContain(SETUP_NAME);
  });

  it("line 2 shows the last use, not the start: a row created later than it was last used — S034_006_DoD1", async () => {
    serveListing(PAYLOAD_ABC, [], SESSIONS_PAYLOAD);
    renderTree();
    await flush();

    const item = sessionItem(SID_A_OLD);
    expect(item.textContent ?? "").toContain(localDateTime(SESSION_A_OLD.last_used_at));
    expect(item.textContent ?? "").not.toContain(localDateTime(SESSION_A_OLD.created_at));
  });
});

describe("034 step 006 — a character's rows read most recent use first (US-151.AC-2, US-089.AC-1)", () => {
  it("three sessions under one character are ordered by last use and their line-2 times descend — S034_006_DoD2", async () => {
    // The server's order (last_used_at DESC); creation order and id order both differ from it.
    serveListing(PAYLOAD_ABC, [], [SESSION_C, SESSION_A_NEW, SESSION_A_MID, SESSION_A_OLD]);
    renderTree();
    await flush();

    expect(sessionHrefsUnder(CORVIN.name)).toEqual([
      `/sessions/${SID_A_NEW}`,
      `/sessions/${SID_A_MID}`,
      `/sessions/${SID_A_OLD}`,
    ]);
    const shown = within(sessionsListFor(CORVIN.name))
      .queryAllByRole("link")
      .map((link) => {
        const item = link.closest("li") ?? link;
        return /\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.exec(item.textContent ?? "")?.[0] ?? "";
      });
    expect(shown).toEqual([
      localDateTime(SESSION_A_NEW.last_used_at),
      localDateTime(SESSION_A_MID.last_used_at),
      localDateTime(SESSION_A_OLD.last_used_at),
    ]);
    expect([...shown].sort().reverse()).toEqual(shown);
  });
});

describe("034 step 006 — renaming from a tree row (US-150.AC-2, US-150.AC-4)", () => {
  it("every session row offers Rename session beside its link, never inside it — S034_006_DoD3", async () => {
    serveListing(PAYLOAD_ABC, [], SESSIONS_PAYLOAD);
    renderTree();
    await flush();

    for (const id of [SID_C, SID_A_NEW, SID_A_OLD]) {
      const button = renameButtonOf(id);
      expect(button).toBeInTheDocument();
      expect(sessionRow(id).contains(button)).toBe(false);
    }
  });

  it("activating it on a never-renamed row shows an empty Session name input in place of the link — S034_006_DoD3", async () => {
    const user = newUser();
    serveRenamable(SESSIONS_PAYLOAD);
    renderTree();
    await flush();

    await user.click(renameButtonOf(SID_A_OLD));
    await flush();

    expect(nameInput()).toHaveValue("");
    expect(querySessionRow(SID_A_OLD)).toBeNull();
    // Only that row is being edited; its neighbours keep their links.
    expect(querySessionRow(SID_A_NEW)).not.toBeNull();
    expect(within(tree()).getAllByRole("textbox", { name: NAME_INPUT })).toHaveLength(1);
  });

  it("activating it on a renamed row pre-fills the input with the current name — S034_006_DoD3", async () => {
    const user = newUser();
    const named: Session = { ...SESSION_A_OLD, name: "Harbour at dusk" };
    serveRenamable([SESSION_C, SESSION_A_NEW, named]);
    renderTree();
    await flush();

    await user.click(renameButtonOf(SID_A_OLD));
    await flush();

    expect(nameInput()).toHaveValue("Harbour at dusk");
  });

  it("typing a name and pressing Enter sends one PATCH /api/sessions/<id> with { name } — S034_006_DoD3", async () => {
    const user = newUser();
    const { patches } = serveRenamable(SESSIONS_PAYLOAD);
    renderTree();
    await flush();

    await user.click(renameButtonOf(SID_A_OLD));
    await user.type(nameInput(), `${NEW_NAME}{Enter}`);
    await flush();

    expect(patches).toEqual([{ path: `/api/sessions/${SID_A_OLD}`, body: { name: NEW_NAME } }]);
  });

  it("the row shows the new label only after the server answers — S034_006_DoD3", async () => {
    const user = newUser();
    const gate = deferred<void>();
    const { patches } = serveRenamable(SESSIONS_PAYLOAD, { gate: gate.promise });
    const { sessions } = renderTree();
    await flush();

    await user.click(renameButtonOf(SID_A_OLD));
    await user.type(nameInput(), `${NEW_NAME}{Enter}`);
    await flush();

    // Sent, not answered: nothing in the tree reads the new name and the store is untouched.
    expect(patches).toHaveLength(1);
    expect(elementsWithText(tree(), NEW_NAME)).toEqual([]);
    expect(storedRow(sessions, SID_A_OLD)?.name).toBeNull();

    await act(async () => {
      gate.resolve();
    });
    await flush();

    expect(queryNameInput()).toBeNull();
    expect(rowLabelText({ ...SESSION_A_OLD, name: NEW_NAME })).toBe(NEW_NAME);
    expect(storedRow(sessions, SID_A_OLD)?.name).toBe(NEW_NAME);
  });

  it("the renamed row keeps its position under its character, and the characters keep theirs — S034_006_DoD3", async () => {
    const user = newUser();
    serveRenamable([SESSION_C, SESSION_A_NEW, SESSION_A_MID, SESSION_A_OLD]);
    renderTree();
    await flush();
    const rowsBefore = sessionHrefsUnder(CORVIN.name);
    const charactersBefore = characterTexts();

    // The middle row, so a move either way would show.
    await user.click(renameButtonOf(SID_A_MID));
    await user.type(nameInput(), `${NEW_NAME}{Enter}`);
    await flush();

    expect(sessionHrefsUnder(CORVIN.name)).toEqual(rowsBefore);
    expect(rowsBefore).toEqual([
      `/sessions/${SID_A_NEW}`,
      `/sessions/${SID_A_MID}`,
      `/sessions/${SID_A_OLD}`,
    ]);
    expect(characterTexts()).toEqual(charactersBefore);
    expect(rowLabelText({ ...SESSION_A_MID, name: NEW_NAME })).toBe(NEW_NAME);
  });

  it("a name typed with surrounding spaces is shown trimmed, as the server answers it — S034_006_DoD3", async () => {
    const user = newUser();
    serveRenamable(SESSIONS_PAYLOAD);
    renderTree();
    await flush();

    // DEC-034-1 / DEC-034-11: the name is trimmed; the row shows the answered (trimmed) name.
    await user.click(renameButtonOf(SID_A_OLD));
    await user.type(nameInput(), `   ${NEW_NAME}   {Enter}`);
    await flush();

    expect(rowLabelText({ ...SESSION_A_OLD, name: NEW_NAME })).toBe(NEW_NAME);
  });
});

describe("034 step 006 — Escape in the tree editor (DEC-034-11)", () => {
  it("Escape restores the row with its old label and sends nothing — S034_006_DoD4", async () => {
    const user = newUser();
    const named: Session = { ...SESSION_A_OLD, name: "Harbour at dusk" };
    const { patches } = serveRenamable([SESSION_C, SESSION_A_NEW, named]);
    const { sessions } = renderTree();
    await flush();

    await user.click(renameButtonOf(SID_A_OLD));
    await user.clear(nameInput());
    await user.type(nameInput(), `${NEW_NAME}{Escape}`);
    await flush();

    expect(queryNameInput()).toBeNull();
    expect(sessionRow(SID_A_OLD)).toHaveAttribute("href", `/sessions/${SID_A_OLD}`);
    expect(rowLabelText(named)).toBe("Harbour at dusk");
    expect(elementsWithText(tree(), NEW_NAME)).toEqual([]);
    expect(patches).toEqual([]);
    expect(storedRow(sessions, SID_A_OLD)?.name).toBe("Harbour at dusk");
  });

  it("Escape on a never-renamed row restores its local start date and sends nothing — S034_006_DoD4", async () => {
    const user = newUser();
    const { patches } = serveRenamable(SESSIONS_PAYLOAD);
    renderTree();
    await flush();

    await user.click(renameButtonOf(SID_A_OLD));
    await user.type(nameInput(), `${NEW_NAME}{Escape}`);
    await flush();

    expect(queryNameInput()).toBeNull();
    expect(rowLabelText(SESSION_A_OLD)).toBe(localDate(SESSION_A_OLD.created_at));
    expect(patches).toEqual([]);
  });
});

describe("034 step 006 — a failed rename from the tree (DEC-034-11)", () => {
  it("shows Could not rename the session. under the editor, keeps the typed text and the old label — S034_006_DoD6", async () => {
    const user = newUser();
    const { patches } = serveRenamable(SESSIONS_PAYLOAD, { fail: true });
    const { sessions } = renderTree();
    await flush();

    await user.click(renameButtonOf(SID_A_OLD));
    await user.type(nameInput(), `${NEW_NAME}{Enter}`);
    await flush();

    expect(patches).toHaveLength(1);
    const input = nameInput();
    expect(input).toHaveValue(NEW_NAME);
    const item = input.closest("li");
    expect(item).not.toBeNull();
    const sentence = within(item as HTMLElement).getByText(RENAME_FAILED_TEXT);
    expect(precedes(input, sentence)).toBe(true);

    // The label elsewhere — the workspace store the tree and the header read — is unchanged.
    expect(storedRow(sessions, SID_A_OLD)?.name).toBeNull();
    expect(elementsWithText(tree(), NEW_NAME)).toEqual([]);
    expect(notificationsShown()).toEqual([]);
  });

  it("the failure is inline only, and Escape afterwards restores the old label — S034_006_DoD6", async () => {
    const user = newUser();
    serveRenamable(SESSIONS_PAYLOAD, { fail: true });
    renderTree();
    await flush();

    await user.click(renameButtonOf(SID_A_OLD));
    await user.type(nameInput(), `${NEW_NAME}{Enter}`);
    await flush();
    expect(within(tree()).getByText(RENAME_FAILED_TEXT)).toBeInTheDocument();

    await user.type(nameInput(), "{Escape}");
    await flush();

    expect(queryNameInput()).toBeNull();
    expect(rowLabelText(SESSION_A_OLD)).toBe(localDate(SESSION_A_OLD.created_at));
  });
});
