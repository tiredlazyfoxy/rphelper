// Feature 009, step 007 — the character screen and its two routes (DoD-1..DoD-12).
// DoD-13 lives in App.test.tsx; DoD-14 is [manual/live] and carries no test.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 007.context.md and context.md (D1 explicit Create with `replace` navigation, D2 the
// labelled Save, D4/D9 an archived character's page opens and stays editable, D11 the one
// workspace characters state arrives as a prop, D12 every failure is inline and nothing is
// notified).
//
// Recognition conventions (from the spec's wording, for the verifier):
// - The screen's own names are the contract: headings "New character" / the character's
//   name / "Sessions"; textboxes "Name" and "Persona"; buttons "Create", "Save", "Archive",
//   "Restore", "Retry"; the badge text exactly "Archived"; the sentences "Character not
//   found", "Could not load the character", "Could not create the character.", "Could not
//   save the character.". Everything is queried by role + accessible name or by text.
// - The centre column: the harness wraps the two routes in a `<main>` landmark, which is
//   what the shell gives the screen in the application (008). "In the main region" means
//   inside it.
// - A Mantine `Loader`: `.mantine-Loader-root` (the repo's existing convention).
// - A notification: `.mantine-Notification-root`.
// - The router location and in-entry navigation: a probe rendered beside the routes inside
//   the same MemoryRouter; document navigation is `documentNavigation.assign` (the shared
//   client's only seam onto `window.location`).
// - `src/shared/MarkdownEditor` is replaced by the sanctioned stub (context.md "Test
//   conventions — TipTap in jsdom"): a labelled `<textarea>` honouring `label`, `value`,
//   `onChange` and `readOnly`, so persona edits are typed reliably in jsdom.
//
// Amended by feature 010, step 006 (DoD-13 and DoD-10..DoD-12): existing mode's "ready" render
// now carries the "Setups" section (010 D1), which loads `GET /api/characters/<id>/setups` on
// mount. Every stub whose character load succeeds therefore answers that path too, with
// `{ "setups": [] }` — an empty listing renders no setup rows, so no setup "Archived" badge, no
// row menu and no setups-side "Create" / "Save" / "Archive" / "Restore" / "Retry" control
// exists, and every 009 query below keeps its exact meaning. No 009 assertion was dropped: the
// one document-wide `loaders()` clause now waits for the section's own listing to settle as
// well. New mode and the loading / not-found / failed states mount no section (010 D1), so
// their stubs and their "no request at all" clauses are untouched. The three clauses at the
// bottom of this file are 010 step 006's own DoD-10..DoD-12; they scope every section
// assertion through `within(getByRole("region", { name: "Setups" }))` and reach the setup
// modal through `screen`, because Mantine renders it into a portal (010 context.md).
//
// Amended by feature 011, step 008 (DoD-16): `CharacterScreen` and `CharacterRoute` each take
// one required `sessions` prop — the one workspace `SessionsState` (011 D15) — so every render
// here passes a fresh instance, and 009's empty "Sessions" heading is now the "Sessions"
// region's own heading (011 D1). Consequences, all mechanical:
// - every stub whose character load succeeds answers `GET /api/characters/<id>/sessions` with
//   `{ "sessions": [] }` **and** tolerates a SECOND `GET /api/characters/<id>/setups` (the
//   section's Select choices beside 010's section's own listing), both routed by exact path —
//   the fallback 404/500 would otherwise drive the section into its failed state and put
//   "Could not load sessions" and a second "Retry" inside the main region;
// - 009 DoD-5's `expect(heading(SESSIONS_HEADING))` is unchanged and still passes: the region
//   carries a `Title order={3}` "Sessions" heading in the old heading's place;
// - 009 DoD-1's "no 'Sessions' heading at /characters/new" is unchanged and still passes: new
//   mode mounts no section (011 D1);
// - 010 DoD-12's `expect(listings).toHaveLength(1)` counted the Setups section's own listing;
//   with two sections on the screen that path is now requested by both, so the clause keeps
//   what it means — B's setups were requested, and never with `include_archived` — without
//   counting the Sessions section's request as the Setups section's;
// - no other 009 or 010 assertion changed. 011 step 008's own DoD-12..DoD-14 are the three
//   blocks at the bottom of this file.
//
// Amended by feature 015, step 009 (DoD-7): existing mode's "ready" render now carries the
// character-level "Notes" section (015 D1) after the "Sessions" region, which loads
// `GET /api/memos?scope=character&scope_id=<id>` on mount. Consequences, all mechanical:
// - `sectionListing` also answers that listing with `{ "memos": [] }`, matched on the exact
//   pathname **and** query string (the pathname `/api/memos` alone is shared with the POST and
//   with other levels' listings); the two hand-written stubs of 010 DoD-12 and 011 DoD-14 gain
//   the same branch. An empty listing renders no note, so no "Note" textbox and no note-side
//   button but "New note" exists, and every 009, 010 and 011 query keeps its meaning;
// - the `MarkdownEditor` stub now takes its textarea id from React's `useId` (step 007's stub),
//   because several editors labelled "Note" can be on screen at once and a label-derived id
//   would collide; every query here goes through the label, so nothing else changes;
// - 011 DoD-12's document order still holds (Notes comes after Sessions); 010 DoD-12's and 011
//   DoD-14's request counts are keyed on their own exact paths, so the notes listing is not
//   counted. New mode and the loading / not-found / failed states mount no Notes section, so
//   their stubs and their "no request at all" clauses are untouched. No assertion was dropped.
//   015 step 009's own DoD-4..DoD-6 are the three blocks at the bottom of this file.
//
// Amended by feature 018, step 009 (DoD-1..DoD-11): `/characters/new` is the draft page (018 D6:
// "Draft" badge, marker line, Name and Persona only, the create fires when Name loses focus
// holding non-blank text, replace navigation), and `/characters/:id` saves name and persona on
// focus loss with no Save (018 D7). The ready body runs Notes → Setups → Configuration →
// Sessions → Start a session (018 D10). Consequences:
// - `sectionListing` also answers `GET /api/characters/<id>/configuration` (five keys, all null)
//   and `GET /api/models` (`{ "models": [] }`) by exact path and empty query, and the two
//   hand-written stubs of 010 DoD-12 and 011 DoD-14 gain the same branch (018 DoD-11);
//   `serveCharacters` answers a PATCH of a held row with that row and the patch applied, because
//   any edit now saves when its field loses focus;
// - replaced (018 DoD-1..DoD-6): 009 DoD-1/DoD-2 (Create disabled / enabled), 009 DoD-3 ×2 and
//   DoD-4 (Create click → Name blur), 009 DoD-5's "Save is disabled" line, 009 DoD-6 (Save
//   PATCHes both fields — removed, superseded by 018 DoD-5), 009 DoD-8's "Save is enabled" line,
//   009 DoD-11 (Save click → focus loss), and 015 DoD-4's "Notes follows Sessions" (now Notes
//   precedes Setups). Each amended title ends with the 018 "— DoD-N" that amends it;
// - every other 009 / 010 / 011 / 015 assertion is unchanged. 018 step 009's own clauses are the
//   blocks at the bottom of this file.
//
// Amended by feature 033, step 001 (DoD-1..DoD-13; D1–D5, D8): the ready page is now a page
// header (saved-name Title, "Archived" badge, icon-only "Archive"/"Restore" and "Export") above a
// Mantine `Tabs` with five tabs — "Sessions" (selected on open), "Main info", "Configuration",
// "Notes", "Setups" — kept mounted (D2), so every section still loads once on open. Inactive tab
// panels are mounted but hidden, and role queries skip hidden elements by default. Consequences:
// - helpers `tab`, `tabPanel`, `openTab` were added; a clause that reads or types into Name /
//   Persona first opens "Main info", and a clause that interacts inside the Notes / Setups /
//   Configuration region first opens that tab. Moving to another character starts on "Sessions"
//   again (D1), so such clauses reopen the tab after navigating. Presence-only checks of a region
//   in an inactive tab query with `{ hidden: true }`; every "renders no X region" clause now also
//   queries with `{ hidden: true }`, which is strictly stronger;
// - replaced (superseded by the tabs): 010 DoD-10's "Setups between Persona and Sessions", 011
//   DoD-12's "Sessions after Persona and Setups", 015 DoD-4 / 018 DoD-6's body order
//   (`precedes` across the five regions) and the bug-fix clauses' order check — each now asserts
//   the region's tab panel instead. The composer region is "New session" (was "Start a session",
//   033 DoD-13);
// - no other assertion changed. 033 step 001's own clauses are the blocks at the bottom of this
//   file, each tagged "033 DoD-N".
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChangeEvent, ReactNode } from "react";
import { CharacterRoute, CharacterScreen } from "../../src/app/CharacterScreen";
import type { Character } from "../../src/app/charactersApi";
import type { CharacterConfiguration } from "../../src/app/configurationApi";
import type { Memo } from "../../src/app/memosApi";
import type { Session } from "../../src/app/sessionsApi";
import type { Setup } from "../../src/app/setupsApi";
import { CharactersState } from "../../src/app/charactersState";
import { SessionsState } from "../../src/app/sessionsState";
import { documentNavigation } from "../../src/shared/api";
import { AppProviders } from "../../src/shared/AppProviders";

vi.mock("../../src/shared/MarkdownEditor", async () => {
  // 015 step 009: the id comes from `useId`, so several "Note" editors never share one.
  const { createElement, useId } = await import("react");
  type StubProps = {
    label: string;
    value: string;
    onChange: (markdown: string) => void;
    readOnly?: boolean;
    toolbarActions?: ReactNode;
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
        // fast 012: the toolbar-actions prop (a saved note's flags) renders inside the root.
        props.toolbarActions === undefined || props.toolbarActions === null
          ? null
          : createElement("div", { "data-testid": "stub-toolbar-actions" }, props.toolbarActions),
      );
    },
  };
});

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string; body: unknown };
type User = ReturnType<typeof userEvent.setup>;

// ---------------------------------------------------------------- the spec's names
const NEW_HEADING = /^new character$/i;
const SESSIONS_HEADING = /^sessions$/i;
const NAME_LABEL = /^name$/i;
const PERSONA_LABEL = /^persona$/i;
const CREATE_NAME = /^create$/i;
const SAVE_NAME = /^save$/i;
const ARCHIVE_NAME = /^archive$/i;
const RESTORE_NAME = /^restore$/i;
const RETRY_NAME = /^retry$/i;
const ARCHIVED_BADGE = "Archived";
const NOT_FOUND_TEXT = "Character not found";
const LOAD_FAILED_TEXT = "Could not load the character";
const CREATE_FAILED_TEXT = "Could not create the character.";
const SAVE_FAILED_TEXT = "Could not save the character.";

const LOADER = ".mantine-Loader-root";
const NOTIFICATION = ".mantine-Notification-root";

// ------------------------------------- 010 step 006: the Setups section's own names (D1, D4)
const SETUPS_REGION = /^setups$/i;
const NEW_SETUP_NAME = /^new setup$/i;
// 033 step 003 (D7): the inline create form's Save icon button.
const SAVE_SETUP_NAME = /^save setup$/i;
const SHOW_ARCHIVED_SETUPS_NAME = /^show archived setups$/i;

// ------------------------------------- 011 step 008: the Sessions section's own names (D1, D5)
const SESSIONS_REGION = /^sessions$/i;
const SHOW_ARCHIVED_SESSIONS_NAME = /^show archived sessions$/i;
const START_SESSION_NAME = /^start session$/i;

// ---------------------------------------------------------------- fixtures
// Ids are decimal strings; CREATED_ID is past Number.MAX_SAFE_INTEGER, so any coercion of
// the response's id would show up in the location (context.md "Ids are strings").
const ID_A = "7250000000000000011";
const ID_B = "7250000000000000012";
const CREATED_ID = "9007199254740993"; // 2^53 + 1

const NEW_PATH = "/characters/new";
const COLLECTION_PATH = "/api/characters";

const TYPED_NAME = "Aria Vance";
const TYPED_SHEET = "A duelist with a borrowed name.";

const CHAR_A: Character = {
  id: ID_A,
  name: "Aria Vance",
  sheet: "A scribe who never finishes a sentence.",
  archived_at: null,
  created_at: "2026-03-14T09:26:53.000000+00:00",
  updated_at: "2026-03-14T09:26:53.000000+00:00",
};

const CHAR_B: Character = {
  id: ID_B,
  name: "Corvin Hale",
  sheet: "A duelist who counts his scars.",
  archived_at: null,
  created_at: "2026-02-01T08:15:42.000000+00:00",
  updated_at: "2026-02-01T08:15:42.000000+00:00",
};

const ARCHIVED_A: Character = {
  ...CHAR_A,
  archived_at: "2026-04-05T10:00:00.000000+00:00",
  updated_at: "2026-04-05T10:00:00.000000+00:00",
};

const CREATED: Character = {
  id: CREATED_ID,
  name: TYPED_NAME,
  sheet: TYPED_SHEET,
  archived_at: null,
  created_at: "2026-04-10T12:00:00.000000+00:00",
  updated_at: "2026-04-10T12:00:00.000000+00:00",
};

// 018 step 009: `SAVED_A` (009 DoD-6's PATCH answer) went with that removed clause.

const EDITED_NAME = "Bo";
const EDITED_SHEET = "Shorter now.";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- fetch harness
function itemPath(characterId: string): string {
  return `${COLLECTION_PATH}/${characterId}`;
}

/** 010 step 006: the section's listing, a different URL than the character's own. */
function setupsPath(characterId: string): string {
  return `${itemPath(characterId)}/setups`;
}

/** 011 step 008: the Sessions section's listing, a third URL under the same character. */
function sessionsPath(characterId: string): string {
  return `${itemPath(characterId)}/sessions`;
}

/** Every character route whose load succeeds now also answers the section's listing. */
const EMPTY_SETUPS = { setups: [] };

/** 011 step 008: the Sessions section's own listing, answered empty everywhere. */
const EMPTY_SESSIONS = { sessions: [] };

/** 015 step 009: the Notes section's listing — one pathname shared by every memo request. */
const MEMOS_PATH = "/api/memos";

/** 015 step 009: the exact query of one character's notes listing (memos wire contract). */
function notesSearch(characterId: string): string {
  return `?scope=character&scope_id=${characterId}`;
}

/** 015 step 009: true for exactly `GET /api/memos?scope=character&scope_id=<id>`. */
function isNotesListing(request: Seen, characterId: string): boolean {
  return (
    request.method === "GET" && request.path === MEMOS_PATH && request.search === notesSearch(characterId)
  );
}

/** 015 step 009: the Notes section's own listing, answered empty everywhere but its own blocks. */
const EMPTY_NOTES = { memos: [] };

/** 018 step 009: the configuration block's own read, under the character. */
function configurationPath(characterId: string): string {
  return `${itemPath(characterId)}/configuration`;
}

/** 018 step 009: the enabled-models read the configuration block makes. */
const MODELS_PATH = "/api/models";

/** 018 step 009: a character configuration with all five keys, nothing set. */
const UNSET_CONFIGURATION: CharacterConfiguration = {
  model: null,
  system_prompt: null,
  tool_memo_search: null,
  tool_session_search: null,
  tool_web_search: null,
};

/**
 * 018 step 009 (DoD-11): answers exactly `GET /api/characters/<id>/configuration` (nothing set)
 * and `GET /api/models` (none enabled), both with an empty query; null otherwise.
 */
function configurationListing(request: Seen, characterId: string): Response | null {
  if (request.method !== "GET" || request.search !== "") return null;
  if (request.path === configurationPath(characterId)) return jsonResponse(UNSET_CONFIGURATION, 200);
  if (request.path === MODELS_PATH) return jsonResponse({ models: [] }, 200);
  return null;
}

/** 018 step 009: the `updated_at` a PATCH answer carries — later than every fixture's. */
const PATCHED_STAMP = "2026-09-30T12:00:00.000000+00:00";

/**
 * 010 / 011: the two sections a loaded character's screen mounts ask for three listings under
 * that character — 010's setups, 011's sessions, and 011's own second request for the same
 * setups (the Select's choices). 015 step 009 adds a fourth: the Notes section's listing, matched
 * on the exact path **and** query. Answers all of them empty, any number of times; returns null
 * when the request is not one of them.
 */
function sectionListing(request: Seen, characterId: string): Response | null {
  if (request.method !== "GET") return null;
  // 018 step 009 (DoD-11): the configuration block's two reads.
  const configuration = configurationListing(request, characterId);
  if (configuration !== null) return configuration;
  if (request.path === setupsPath(characterId)) return jsonResponse(EMPTY_SETUPS, 200);
  if (request.path === sessionsPath(characterId)) return jsonResponse(EMPTY_SESSIONS, 200);
  if (isNotesListing(request, characterId)) return jsonResponse(EMPTY_NOTES, 200);
  return null;
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** A domain envelope — the shape every non-2xx of ours carries. */
function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: "ql-77 went wrong.", detail: {} } }, status);
}

function notFoundResponse(): Response {
  return envelope("character_not_found", 404);
}

function serverError(): Response {
  return envelope("internal_error", 500);
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function parseBody(init?: RequestInit): unknown {
  const body = init?.body;
  if (body === undefined || body === null) return undefined;
  return JSON.parse(String(body)) as unknown;
}

/** A URL-routed in-memory backend; every request is recorded in order. */
function stubBackend(handler: (request: Seen) => Response | Promise<Response>) {
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

/**
 * Answers GET of each given character, an empty setups listing for each (010 step 006) and an
 * empty sessions listing for each (011 step 008), and 404s everything else.
 */
function serveCharacters(...rows: Character[]) {
  return stubBackend((request) => {
    if (request.method === "GET") {
      const row = rows.find((candidate) => request.path === itemPath(candidate.id));
      if (row !== undefined) return jsonResponse(row, 200);
      for (const candidate of rows) {
        const listing = sectionListing(request, candidate.id);
        if (listing !== null) return listing;
      }
    }
    // 018 step 009: an edit now saves when its field loses focus (D7), so a PATCH of a held row
    // answers that row with the patch applied.
    if (request.method === "PATCH") {
      const row = rows.find((candidate) => request.path === itemPath(candidate.id));
      if (row !== undefined) {
        const patch = (request.body ?? {}) as Partial<Character>;
        return jsonResponse({ ...row, ...patch, updated_at: PATCHED_STAMP }, 200);
      }
    }
    return notFoundResponse();
  });
}

function matching(calls: Seen[], method: string, path: string): Seen[] {
  return calls.filter((call) => call.method === method && call.path === path);
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
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

// ---------------------------------------------------------------- render
const PROBE_NAVIGATE = /^probe navigate$/i;
const PROBE_BACK = /^probe back$/i;

function Probe(props: { to: string }) {
  const navigate = useNavigate();
  const location = useLocation();
  return (
    <div>
      <span data-testid="location">{location.pathname}</span>
      {/* 033 step 001 (DoD-3): the whole URL, so a tab change showing in search or hash is seen. */}
      <span data-testid="location-full">{`${location.pathname}${location.search}${location.hash}`}</span>
      <button type="button" onClick={() => void navigate(props.to)}>
        probe navigate
      </button>
      <button type="button" onClick={() => void navigate(-1)}>
        probe back
      </button>
    </div>
  );
}

/**
 * The two routes of this step, in the `<main>` landmark the shell gives them, with one
 * workspace `CharactersState` (D11), one workspace `SessionsState` (011 D15, a required prop of
 * both since 011 step 008) and a location/navigation probe beside them.
 */
function renderScreen(initialPath: string, probeTo = `/characters/${ID_B}`) {
  const characters = new CharactersState();
  const sessions = new SessionsState();
  const view = render(
    <AppProviders>
      <MemoryRouter initialEntries={[initialPath]}>
        <main>
          <Routes>
            <Route
              path="/characters/new"
              element={
                <CharacterScreen characters={characters} characterId={null} sessions={sessions} />
              }
            />
            <Route
              path="/characters/:id"
              element={<CharacterRoute characters={characters} sessions={sessions} />}
            />
          </Routes>
        </main>
        <Probe to={probeTo} />
      </MemoryRouter>
    </AppProviders>,
  );
  return { characters, sessions, view };
}

// ---------------------------------------------------------------- queries
function mainRegion(): HTMLElement {
  return screen.getByRole("main");
}

function locationPath(): string {
  return screen.getByTestId("location").textContent ?? "";
}

/** 033 step 001 (DoD-3): pathname + search + hash. */
function fullLocation(): string {
  return screen.getByTestId("location-full").textContent ?? "";
}

function nameInput(): HTMLInputElement {
  const element = within(mainRegion()).getByRole("textbox", { name: NAME_LABEL });
  if (!(element instanceof HTMLInputElement)) throw new Error('the "Name" textbox is not an input');
  return element;
}

function personaInput(): HTMLTextAreaElement {
  const element = within(mainRegion()).getByRole("textbox", { name: PERSONA_LABEL });
  if (!(element instanceof HTMLTextAreaElement)) {
    throw new Error('the "Persona" textbox is not the stubbed editor');
  }
  return element;
}

function button(name: RegExp): HTMLElement {
  return within(mainRegion()).getByRole("button", { name });
}

function queryButton(name: RegExp): HTMLElement | null {
  return within(mainRegion()).queryByRole("button", { name });
}

function heading(name: RegExp | string): HTMLElement {
  return within(mainRegion()).getByRole("heading", { name });
}

function queryHeading(name: RegExp | string): HTMLElement | null {
  return within(mainRegion()).queryByRole("heading", { name });
}

function loaders(): Element[] {
  return Array.from(document.querySelectorAll(LOADER));
}

function notificationsShown(): Element[] {
  return Array.from(document.querySelectorAll(NOTIFICATION));
}

// ------------------------------------- 010 step 006: the Setups section inside the screen
function setupsRegion(): HTMLElement {
  return screen.getByRole("region", { name: SETUPS_REGION });
}

/** 033 step 001: hidden included, so "no Setups region" also means "not even in a hidden tab". */
function querySetupsRegion(): HTMLElement | null {
  return screen.queryByRole("region", { name: SETUPS_REGION, hidden: true });
}

function setupsSwitch(): HTMLElement {
  const scope = within(setupsRegion());
  return (
    scope.queryByRole("switch", { name: SHOW_ARCHIVED_SETUPS_NAME }) ??
    scope.getByRole("checkbox", { name: SHOW_ARCHIVED_SETUPS_NAME })
  );
}

// ------------------------------------- 011 step 008: the Sessions section inside the screen
function sessionsRegion(): HTMLElement {
  return screen.getByRole("region", { name: SESSIONS_REGION });
}

/** 033 step 001: hidden included, so "no Sessions region" also means "not even in a hidden tab". */
function querySessionsRegion(): HTMLElement | null {
  return screen.queryByRole("region", { name: SESSIONS_REGION, hidden: true });
}

function sessionsSwitch(): HTMLElement {
  const scope = within(sessionsRegion());
  return (
    scope.queryByRole("switch", { name: SHOW_ARCHIVED_SESSIONS_NAME }) ??
    scope.getByRole("checkbox", { name: SHOW_ARCHIVED_SESSIONS_NAME })
  );
}

/** The section's session rows, in document order, by their `/sessions/<id>` href. */
function sessionHrefs(): string[] {
  return within(sessionsRegion())
    .queryAllByRole("link")
    .map((link) => link.getAttribute("href") ?? "")
    .filter((value) => value.startsWith("/sessions/"));
}

/** True when `first` comes before `second` in document order. */
function precedes(first: Element, second: Element): boolean {
  return (first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

/** Loads `character` at its own route and settles. */
async function renderLoaded(character: Character, extra: Character[] = []) {
  const server = serveCharacters(character, ...extra);
  const rendered = renderScreen(`/characters/${character.id}`);
  await flush();
  return { ...server, ...rendered };
}

async function typeInto(user: User, element: HTMLElement, text: string): Promise<void> {
  await user.clear(element);
  await user.type(element, text);
}

// ------------------------------------- 033 step 001: the page's tabs (D1, D2)
const SESSIONS_TAB = "Sessions";
const MAIN_INFO_TAB = "Main info";
const CONFIGURATION_TAB = "Configuration";
const NOTES_TAB = "Notes";
const SETUPS_TAB = "Setups";

/** The five tabs, in the order 033 D1 requires. */
const TAB_NAMES = [SESSIONS_TAB, MAIN_INFO_TAB, CONFIGURATION_TAB, NOTES_TAB, SETUPS_TAB];

function tablist(): HTMLElement {
  return within(mainRegion()).getByRole("tablist");
}

function queryTablistAnywhere(): HTMLElement | null {
  return screen.queryByRole("tablist", { hidden: true });
}

function tab(name: string): HTMLElement {
  return within(mainRegion()).getByRole("tab", { name });
}

/**
 * A tab's panel, found whether or not its tab is active. Inactive panels are `display: none`, for
 * which the accessible-name computation yields "", so the panel is matched through the WAI-ARIA
 * tabs pairing instead: the tab's `aria-controls` names the panel's id, and the panel's
 * `aria-labelledby` names the tab's id.
 */
function tabPanel(name: string): HTMLElement {
  const owner = tab(name);
  const controls = owner.getAttribute("aria-controls");
  const panels = within(mainRegion()).getAllByRole("tabpanel", { hidden: true });
  const match = panels.find(
    (panel) =>
      (controls !== null && controls !== "" && panel.id === controls) ||
      (owner.id !== "" && panel.getAttribute("aria-labelledby") === owner.id),
  );
  if (match === undefined) throw new Error(`no tab panel paired with the "${name}" tab`);
  return match;
}

/** Activates a tab the way a user does: a click on it. */
function openTab(name: string): void {
  fireEvent.click(tab(name));
}

/** 033 DoD-1: exactly five tabs in the page's one tab list, named in the D1 order. */
function expectFiveTabsInOrder(): void {
  expect(within(mainRegion()).getAllByRole("tablist")).toHaveLength(1);
  const tabs = within(tablist()).getAllByRole("tab");
  expect(tabs).toHaveLength(TAB_NAMES.length);
  tabs.forEach((element, index) => {
    expect(element).toHaveAccessibleName(TAB_NAMES[index]);
  });
}

// ---------------------------------------------------------------------------
describe("new mode at /characters/new (D1)", () => {
  it("(009 DoD-1, amended) shows the New character form with no Create and nothing of the existing screen — DoD-1", () => {
    stubBackend(() => notFoundResponse());
    renderScreen(NEW_PATH);

    expect(heading(NEW_HEADING)).toBeInTheDocument();
    expect(nameInput()).toBeInTheDocument();
    expect(personaInput()).toBeInTheDocument();
    expect(queryButton(CREATE_NAME)).toBeNull();
    expect(queryButton(ARCHIVE_NAME)).toBeNull();
    expect(queryHeading(SESSIONS_HEADING)).toBeNull();
  });

  it("(009 DoD-2, amended) typing a name without leaving the field sends no request — DoD-2", async () => {
    const user = newUser();
    const { mock, calls } = stubBackend(() => notFoundResponse());
    renderScreen(NEW_PATH);

    await user.type(nameInput(), TYPED_NAME);

    expect(queryButton(CREATE_NAME)).toBeNull();
    expect(calls).toEqual([]);
    expect(mock).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("Name losing focus posts once and hands the route over to the new id (018 D6, US-020.AC-1)", () => {
  it("(009 DoD-3, amended) blurring Name POSTs /api/characters once with the persona and moves the router to the returned id with no document navigation — DoD-3", async () => {
    const user = newUser();
    const assign = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    const { calls } = stubBackend((request) => {
      if (request.method === "POST" && request.path === COLLECTION_PATH) {
        return jsonResponse(CREATED, 201);
      }
      if (request.method === "GET" && request.path === itemPath(CREATED_ID)) {
        return jsonResponse(CREATED, 200);
      }
      // 010 step 006 / 011 step 008: the created character's screen mounts both sections.
      const listing = sectionListing(request, CREATED_ID);
      if (listing !== null) return listing;
      return notFoundResponse();
    });
    renderScreen(NEW_PATH);

    // The persona first: in a draft its focus loss does nothing, and it rides along with the
    // create that Name's focus loss fires (018 D6).
    await user.type(personaInput(), TYPED_SHEET);
    await user.type(nameInput(), TYPED_NAME);
    await user.tab();
    await flush();

    const posts = matching(calls, "POST", COLLECTION_PATH);
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({ name: TYPED_NAME, sheet: TYPED_SHEET });
    expect(locationPath()).toBe(`/characters/${CREATED_ID}`);
    expect(assign).not.toHaveBeenCalled();
  });

  it("(009 DoD-3, amended) navigates with replace, so going back does not return to the empty form — DoD-3", async () => {
    const user = newUser();
    stubBackend((request) => {
      if (request.method === "POST" && request.path === COLLECTION_PATH) {
        return jsonResponse(CREATED, 201);
      }
      if (request.method === "GET" && request.path === itemPath(CREATED_ID)) {
        return jsonResponse(CREATED, 200);
      }
      // 010 step 006 / 011 step 008: the created character's screen mounts both sections.
      const listing = sectionListing(request, CREATED_ID);
      if (listing !== null) return listing;
      return notFoundResponse();
    });
    renderScreen(NEW_PATH);

    await user.type(nameInput(), TYPED_NAME);
    await user.tab();
    await flush();
    expect(locationPath()).toBe(`/characters/${CREATED_ID}`);

    await user.click(screen.getByRole("button", { name: PROBE_BACK }));
    await flush();

    expect(locationPath()).toBe(`/characters/${CREATED_ID}`);
  });

  it("(009 DoD-4, amended) a failed create on Name's focus loss reports inline, stays on the form and keeps the typed name — DoD-4", async () => {
    const user = newUser();
    stubBackend(() => serverError());
    renderScreen(NEW_PATH);

    await user.type(nameInput(), TYPED_NAME);
    await user.tab();
    await flush();

    expect(within(mainRegion()).getByText(CREATE_FAILED_TEXT)).toBeInTheDocument();
    expect(locationPath()).toBe(NEW_PATH);
    expect(nameInput()).toHaveValue(TYPED_NAME);
    expect(notificationsShown()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("existing mode at /characters/:id", () => {
  it("(009 DoD-5, amended: no Save) shows a loader while the GET is pending, then the character — DoD-5", async () => {
    const gate = deferred<Response>();
    stubBackend((request) => {
      if (request.method === "GET" && request.path === itemPath(ID_A)) {
        return gate.promise;
      }
      // 010 step 006 / 011 step 008: once the character is ready both sections load.
      const listing = sectionListing(request, ID_A);
      if (listing !== null) return listing;
      return notFoundResponse();
    });
    renderScreen(`/characters/${ID_A}`);

    expect(loaders().length).toBeGreaterThan(0);

    gate.resolve(jsonResponse(CHAR_A, 200));
    await flush();

    // 010 step 006 (DoD-13): unchanged clause — document-wide, still exactly `[]`. It now
    // waits, because the section renders its own Loader until its listing settles.
    await waitFor(() => {
      expect(loaders()).toEqual([]);
    });
    expect(heading(CHAR_A.name)).toBeInTheDocument();
    // 018 step 009 (D7): Save is gone; name and persona save on focus loss.
    expect(queryButton(SAVE_NAME)).toBeNull();
    expect(button(ARCHIVE_NAME)).toBeInTheDocument();
    expect(within(mainRegion()).queryByText(ARCHIVED_BADGE)).toBeNull();
    // 033 step 001 (D1): the Sessions tab is open on arrival, so its region's heading shows.
    expect(heading(SESSIONS_HEADING)).toBeInTheDocument();
    // 033 step 001 (D4): Name and Persona live in "Main info".
    openTab(MAIN_INFO_TAB);
    expect(nameInput()).toHaveValue(CHAR_A.name);
    expect(personaInput()).toHaveValue(CHAR_A.sheet);
  });

  // 009 DoD-6 ("editing enables Save, which PATCHes name and sheet and re-renders from the
  // response") was removed by 018 step 009: Save is gone (018 D7), and the per-field saves on
  // focus loss are 018 DoD-5's clauses at the bottom of this file.

  it("Archive and Restore round-trip through their own routes — DoD-7 (and 033 DoD-9)", async () => {
    const user = newUser();
    const { calls } = stubBackend((request) => {
      if (request.method === "GET" && request.path === itemPath(ID_A)) {
        return jsonResponse(CHAR_A, 200);
      }
      if (request.method === "POST" && request.path === `${itemPath(ID_A)}/archive`) {
        return jsonResponse(ARCHIVED_A, 200);
      }
      if (request.method === "POST" && request.path === `${itemPath(ID_A)}/restore`) {
        return jsonResponse(CHAR_A, 200);
      }
      // 010 step 006 / 011 step 008: the ready screen mounts both sections.
      const listing = sectionListing(request, ID_A);
      if (listing !== null) return listing;
      return notFoundResponse();
    });
    renderScreen(`/characters/${ID_A}`);
    await flush();

    await user.click(button(ARCHIVE_NAME));
    await flush();

    expect(matching(calls, "POST", `${itemPath(ID_A)}/archive`)).toHaveLength(1);
    expect(within(mainRegion()).getByText(ARCHIVED_BADGE)).toBeInTheDocument();
    expect(button(RESTORE_NAME)).toBeInTheDocument();
    expect(queryButton(ARCHIVE_NAME)).toBeNull();

    await user.click(button(RESTORE_NAME));
    await flush();

    expect(matching(calls, "POST", `${itemPath(ID_A)}/restore`)).toHaveLength(1);
    expect(within(mainRegion()).queryByText(ARCHIVED_BADGE)).toBeNull();
    expect(button(ARCHIVE_NAME)).toBeInTheDocument();
  });

  it("(009 DoD-8, amended: no Save) an already-archived character opens badged, offers Restore and stays editable — DoD-5", async () => {
    const user = newUser();
    await renderLoaded(ARCHIVED_A);

    expect(within(mainRegion()).getByText(ARCHIVED_BADGE)).toBeInTheDocument();
    expect(button(RESTORE_NAME)).toBeInTheDocument();
    expect(queryButton(ARCHIVE_NAME)).toBeNull();

    // 033 step 001 (D4): Name and Persona live in "Main info".
    openTab(MAIN_INFO_TAB);
    expect(nameInput()).toBeEnabled();
    expect(personaInput()).toBeEnabled();

    await typeInto(user, nameInput(), EDITED_NAME);
    await typeInto(user, personaInput(), EDITED_SHEET);

    expect(nameInput()).toHaveValue(EDITED_NAME);
    expect(personaInput()).toHaveValue(EDITED_SHEET);
    // 018 step 009 (D7): there is no Save to enable.
    expect(queryButton(SAVE_NAME)).toBeNull();
  });

  it("a 404 character_not_found renders Character not found in main, with no Retry and no notification — DoD-9", async () => {
    stubBackend(() => notFoundResponse());
    renderScreen(`/characters/${ID_A}`);
    await flush();

    expect(within(mainRegion()).getByText(NOT_FOUND_TEXT)).toBeInTheDocument();
    expect(queryButton(RETRY_NAME)).toBeNull();
    expect(notificationsShown()).toEqual([]);
  });

  it("a 500 on load renders Could not load the character and Retry — DoD-10", async () => {
    stubBackend(() => serverError());
    renderScreen(`/characters/${ID_A}`);
    await flush();

    expect(within(mainRegion()).getByText(LOAD_FAILED_TEXT)).toBeInTheDocument();
    expect(button(RETRY_NAME)).toBeInTheDocument();
  });

  it("a transport failure on load renders Could not load the character and Retry — DoD-10", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<FetchFn>(() => Promise.reject(new TypeError("Failed to fetch"))),
    );
    renderScreen(`/characters/${ID_A}`);
    await flush();

    expect(within(mainRegion()).getByText(LOAD_FAILED_TEXT)).toBeInTheDocument();
    expect(button(RETRY_NAME)).toBeInTheDocument();
  });

  it("Retry requests the character again and renders it on success — DoD-10", async () => {
    const user = newUser();
    let failNext = true;
    const { calls } = stubBackend((request) => {
      if (request.method === "GET" && request.path === itemPath(ID_A)) {
        if (failNext) {
          failNext = false;
          return serverError();
        }
        return jsonResponse(CHAR_A, 200);
      }
      // 010 step 006 / 011 step 008: the ready screen mounts both sections.
      const listing = sectionListing(request, ID_A);
      if (listing !== null) return listing;
      return notFoundResponse();
    });
    renderScreen(`/characters/${ID_A}`);
    await flush();
    expect(matching(calls, "GET", itemPath(ID_A))).toHaveLength(1);

    await user.click(button(RETRY_NAME));
    await flush();

    expect(matching(calls, "GET", itemPath(ID_A))).toHaveLength(2);
    expect(heading(CHAR_A.name)).toBeInTheDocument();
    // 033 step 001 (D4): Name lives in "Main info".
    openTab(MAIN_INFO_TAB);
    expect(nameInput()).toHaveValue(CHAR_A.name);
    expect(within(mainRegion()).queryByText(LOAD_FAILED_TEXT)).toBeNull();
  });

  it("(009 DoD-11, amended: focus loss instead of Save) a failed save reports inline and keeps the edited values in the fields — DoD-5", async () => {
    const user = newUser();
    stubBackend((request) => {
      if (request.method === "GET" && request.path === itemPath(ID_A)) {
        return jsonResponse(CHAR_A, 200);
      }
      // 010 step 006 / 011 step 008: neither section's listing may fall through to the 500
      // below, or a section would render its own failure text and "Retry" inside the main
      // region.
      const listing = sectionListing(request, ID_A);
      if (listing !== null) return listing;
      return serverError();
    });
    renderScreen(`/characters/${ID_A}`);
    await flush();

    // 018 step 009 (D7): each field saves when it loses focus. 033 (D4): both are in "Main info".
    openTab(MAIN_INFO_TAB);
    await typeInto(user, nameInput(), EDITED_NAME);
    await typeInto(user, personaInput(), EDITED_SHEET);
    await user.tab();
    await flush();

    expect(within(mainRegion()).getByText(SAVE_FAILED_TEXT)).toBeInTheDocument();
    expect(nameInput()).toHaveValue(EDITED_NAME);
    expect(personaInput()).toHaveValue(EDITED_SHEET);
  });
});

// ---------------------------------------------------------------------------
describe("moving between characters builds a fresh screen (CharacterRoute is keyed by id)", () => {
  it("navigating from one character to another requests and shows the second, carrying no draft over — DoD-12", async () => {
    const user = newUser();
    const DRAFT_ONLY = "Draft only zq-55";
    const { calls } = serveCharacters(CHAR_A, CHAR_B);
    renderScreen(`/characters/${ID_A}`);
    await flush();

    // 033 step 001 (D4): Name and Persona live in "Main info".
    openTab(MAIN_INFO_TAB);
    await typeInto(user, nameInput(), DRAFT_ONLY);
    expect(nameInput()).toHaveValue(DRAFT_ONLY);

    await user.click(screen.getByRole("button", { name: PROBE_NAVIGATE }));
    await flush();

    expect(locationPath()).toBe(`/characters/${ID_B}`);
    expect(matching(calls, "GET", itemPath(ID_B))).toHaveLength(1);
    expect(heading(CHAR_B.name)).toBeInTheDocument();
    // 033 step 001 (D1): the new character's page starts on "Sessions" again.
    openTab(MAIN_INFO_TAB);
    expect(nameInput()).toHaveValue(CHAR_B.name);
    expect(personaInput()).toHaveValue(CHAR_B.sheet);
    expect(within(mainRegion()).queryByDisplayValue(DRAFT_ONLY)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Feature 010, step 006 — the "Setups" section's place on this screen (010 DoD-10..DoD-12).
// Expected behaviour comes from 010's step file and context.md: D1 (existing mode and "ready"
// only, between the persona block and the "Sessions" heading), D5 (an archived character
// carries the section too) and D11 (the section is keyed by the character id, so moving
// between characters builds fresh state — including the switch).
const SETUP_OF_A: Setup = {
  id: "7250000000000000031",
  character_id: ID_A,
  name: "Tavern brawl",
  description: "Someone has already thrown the first stool.",
  archived_at: null,
  created_at: "2026-05-03T09:26:53.000000+00:00",
  updated_at: "2026-05-03T09:26:53.000000+00:00",
};

const SETUP_OF_B: Setup = {
  id: "7250000000000000032",
  character_id: ID_B,
  name: "Harbour at dusk",
  description: "Lanterns, tar, and a ship that should not be here.",
  archived_at: null,
  created_at: "2026-04-02T08:15:42.000000+00:00",
  updated_at: "2026-04-02T08:15:42.000000+00:00",
};

const CREATED_SETUP: Setup = {
  id: "7250000000000000033",
  character_id: ID_A,
  name: "Night market",
  description: "",
  archived_at: null,
  created_at: "2026-06-01T12:00:00.000000+00:00",
  updated_at: "2026-06-01T12:00:00.000000+00:00",
};

const TYPED_SETUP_NAME = "Night market";

describe("the Setups section's place on the character screen (010 D1)", () => {
  it("(010 DoD-10, amended by 033 DoD-6: the Setups tab replaces the body position) renders the Setups region, with its heading, inside the Setups tab panel — DoD-10", async () => {
    await renderLoaded(CHAR_A);

    openTab(SETUPS_TAB);
    const section = setupsRegion();
    expect(section).toBeInTheDocument();
    expect(within(section).getByRole("heading", { name: SETUPS_REGION })).toBeInTheDocument();
    expect(tabPanel(SETUPS_TAB).contains(section)).toBe(true);
  });

  it("new mode at /characters/new renders no Setups region — DoD-10", async () => {
    const { calls } = stubBackend(() => notFoundResponse());
    renderScreen(NEW_PATH);
    await flush();

    expect(querySetupsRegion()).toBeNull();
    expect(calls).toEqual([]);
  });

  it("the Character not found state renders no Setups region — DoD-10", async () => {
    stubBackend(() => notFoundResponse());
    renderScreen(`/characters/${ID_A}`);
    await flush();

    expect(within(mainRegion()).getByText(NOT_FOUND_TEXT)).toBeInTheDocument();
    expect(querySetupsRegion()).toBeNull();
  });

  it("the Could not load the character state renders no Setups region — DoD-10", async () => {
    stubBackend(() => serverError());
    renderScreen(`/characters/${ID_A}`);
    await flush();

    expect(within(mainRegion()).getByText(LOAD_FAILED_TEXT)).toBeInTheDocument();
    expect(querySetupsRegion()).toBeNull();
  });
});

describe("an archived character still carries the Setups section (010 D5)", () => {
  it("renders the region and creates a setup under that character through the inline form — DoD-11 (and 033 step 003 DoD-4)", async () => {
    const user = newUser();
    const { calls } = stubBackend((request) => {
      if (request.method === "GET" && request.path === itemPath(ID_A)) {
        return jsonResponse(ARCHIVED_A, 200);
      }
      if (request.method === "POST" && request.path === setupsPath(ID_A)) {
        return jsonResponse(CREATED_SETUP, 201);
      }
      // 010 step 006 / 011 step 008: both sections' listings.
      const listing = sectionListing(request, ID_A);
      if (listing !== null) return listing;
      return notFoundResponse();
    });
    renderScreen(`/characters/${ID_A}`);
    await flush();

    expect(within(mainRegion()).getByText(ARCHIVED_BADGE)).toBeInTheDocument();
    expect(button(RESTORE_NAME)).toBeInTheDocument();
    // 033 step 001 (D1): the section lives in the "Setups" tab.
    openTab(SETUPS_TAB);
    expect(setupsRegion()).toBeInTheDocument();

    // 033 step 003 (D7): the header '+' "New setup" opens an inline create form inside the
    // section (no modal); "Save setup" sends the create.
    await user.click(within(setupsRegion()).getByRole("button", { name: NEW_SETUP_NAME }));
    const nameField = await within(setupsRegion()).findByRole("textbox", { name: NAME_LABEL });
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.type(nameField, TYPED_SETUP_NAME);
    await user.click(within(setupsRegion()).getByRole("button", { name: SAVE_SETUP_NAME }));
    await flush();

    const posts = matching(calls, "POST", setupsPath(ID_A));
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toMatchObject({ name: TYPED_SETUP_NAME });
    // 033 step 003 DoD-4: the created setup is listed and the form closed.
    expect(within(setupsRegion()).getByText(CREATED_SETUP.name)).toBeInTheDocument();
    expect(within(setupsRegion()).queryByRole("button", { name: SAVE_SETUP_NAME })).toBeNull();
  });
});

describe("moving between characters builds a fresh Setups section (010 D11)", () => {
  it("requests the second character's setups, shows only its rows and resets the switch — DoD-12", async () => {
    const user = newUser();
    const { calls } = stubBackend((request) => {
      if (request.method === "GET" && request.path === itemPath(ID_A)) {
        return jsonResponse(CHAR_A, 200);
      }
      if (request.method === "GET" && request.path === itemPath(ID_B)) {
        return jsonResponse(CHAR_B, 200);
      }
      if (request.method === "GET" && request.path === setupsPath(ID_A)) {
        return jsonResponse({ setups: [SETUP_OF_A] }, 200);
      }
      if (request.method === "GET" && request.path === setupsPath(ID_B)) {
        return jsonResponse({ setups: [SETUP_OF_B] }, 200);
      }
      // 018 step 009 (DoD-11): the configuration block's two reads, by exact path.
      const configuration = configurationListing(request, ID_A) ?? configurationListing(request, ID_B);
      if (configuration !== null) return configuration;
      // 011 step 008: the Sessions section lists each character's sessions, answered empty.
      if (request.method === "GET" && request.path === sessionsPath(ID_A)) {
        return jsonResponse(EMPTY_SESSIONS, 200);
      }
      if (request.method === "GET" && request.path === sessionsPath(ID_B)) {
        return jsonResponse(EMPTY_SESSIONS, 200);
      }
      // 015 step 009: the Notes section lists each character's notes, answered empty.
      if (isNotesListing(request, ID_A) || isNotesListing(request, ID_B)) {
        return jsonResponse(EMPTY_NOTES, 200);
      }
      return notFoundResponse();
    });
    renderScreen(`/characters/${ID_A}`);
    await flush();
    // 033 step 001 (D1): the section lives in the "Setups" tab.
    openTab(SETUPS_TAB);
    expect(within(setupsRegion()).getByText(SETUP_OF_A.name)).toBeInTheDocument();

    await user.click(setupsSwitch());
    await flush();
    expect(setupsSwitch()).toBeChecked();

    await user.click(screen.getByRole("button", { name: PROBE_NAVIGATE }));
    await flush();

    expect(locationPath()).toBe(`/characters/${ID_B}`);
    // 033 step 001 (D1): the other character's page starts on "Sessions" again.
    openTab(SETUPS_TAB);
    // 011 step 008: this path is now requested by both sections on the screen (010's listing
    // and 011's Select choices), so the clause asserts what it means — B's setups were
    // requested, and never with `include_archived` — instead of counting one request.
    const listings = matching(calls, "GET", setupsPath(ID_B));
    expect(listings.length).toBeGreaterThan(0);
    for (const call of listings) {
      expect(call.search).toBe("");
    }
    expect(within(setupsRegion()).getByText(SETUP_OF_B.name)).toBeInTheDocument();
    expect(within(setupsRegion()).queryByText(SETUP_OF_A.name)).toBeNull();
    expect(setupsSwitch()).not.toBeChecked();
  });
});

// ---------------------------------------------------------------------------
// Feature 011, step 008 — the "Sessions" region's place on this screen (011 DoD-12..DoD-14).
// Expected behaviour comes from 011's step file and context.md: D1 (existing mode and "ready"
// only, in the old empty heading's position after the "Setups" region; absent in new mode and
// in every non-ready state), D2 (an archived character may still start a session) and D15 (the
// section is keyed by the character id, so moving between characters builds fresh state —
// including the switch). Rows are identified by their `/sessions/<id>` href; the section's own
// behaviour is `SessionsSection.test.tsx`'s.
const SESSION_OF_A: Session = {
  id: "7250000000000000101",
  character_id: ID_A,
  setup_id: null,
  setup_name: null,
  archived_at: null,
  last_used_at: "2026-05-10T09:26:53.000000+00:00",
  created_at: "2026-05-10T09:26:53.000000+00:00",
  updated_at: "2026-05-10T09:26:53.000000+00:00",
};

const SESSION_OF_B: Session = {
  id: "7250000000000000102",
  character_id: ID_B,
  setup_id: null,
  setup_name: null,
  archived_at: null,
  last_used_at: "2026-04-02T08:15:42.000000+00:00",
  created_at: "2026-04-02T08:15:42.000000+00:00",
  updated_at: "2026-04-02T08:15:42.000000+00:00",
};

/** Past Number.MAX_SAFE_INTEGER, so a coerced id would show in the POST and the location. */
const STARTED_ID = "9007199254740995";

const STARTED_UNDER_A: Session = {
  id: STARTED_ID,
  character_id: ID_A,
  setup_id: null,
  setup_name: null,
  archived_at: null,
  last_used_at: "2026-06-01T12:00:00.000000+00:00",
  created_at: "2026-06-01T12:00:00.000000+00:00",
  updated_at: "2026-06-01T12:00:00.000000+00:00",
};

describe("the Sessions section's place on the character screen (011 D1)", () => {
  it("(011 DoD-12, amended by 033 DoD-5: the Sessions tab replaces the body position) renders the Sessions region, with its heading, inside the Sessions tab panel shown on arrival — DoD-12", async () => {
    await renderLoaded(CHAR_A);

    const section = sessionsRegion();
    expect(section).toBeInTheDocument();
    expect(within(section).getByRole("heading", { name: SESSIONS_REGION })).toBeInTheDocument();
    expect(tabPanel(SESSIONS_TAB).contains(section)).toBe(true);
  });

  it("new mode at /characters/new renders no Sessions region or heading — DoD-12", async () => {
    const { calls } = stubBackend(() => notFoundResponse());
    renderScreen(NEW_PATH);
    await flush();

    expect(querySessionsRegion()).toBeNull();
    expect(queryHeading(SESSIONS_HEADING)).toBeNull();
    expect(calls).toEqual([]);
  });

  it("the Character not found state renders no Sessions region or heading — DoD-12", async () => {
    stubBackend(() => notFoundResponse());
    renderScreen(`/characters/${ID_A}`);
    await flush();

    expect(within(mainRegion()).getByText(NOT_FOUND_TEXT)).toBeInTheDocument();
    expect(querySessionsRegion()).toBeNull();
    expect(queryHeading(SESSIONS_HEADING)).toBeNull();
  });

  it("the Could not load the character state renders no Sessions region or heading — DoD-12", async () => {
    stubBackend(() => serverError());
    renderScreen(`/characters/${ID_A}`);
    await flush();

    expect(within(mainRegion()).getByText(LOAD_FAILED_TEXT)).toBeInTheDocument();
    expect(querySessionsRegion()).toBeNull();
    expect(queryHeading(SESSIONS_HEADING)).toBeNull();
  });
});

describe("an archived character still carries the Sessions section (011 D2)", () => {
  // Amended by 033 step 005 (D9): the section has no "Start session" button any more; a session
  // starts only through the "New session" composer's send, with its opening message.
  it("renders the region and starts a session under that character — DoD-13 (and 033 step 005 DoD-1, DoD-4)", async () => {
    const user = newUser();
    const { calls } = stubBackend((request) => {
      if (request.method === "GET" && request.path === itemPath(ID_A)) {
        return jsonResponse(ARCHIVED_A, 200);
      }
      if (request.method === "POST" && request.path === sessionsPath(ID_A)) {
        return jsonResponse(STARTED_UNDER_A, 201);
      }
      const listing = sectionListing(request, ID_A);
      if (listing !== null) return listing;
      return notFoundResponse();
    });
    renderScreen(`/characters/${ID_A}`);
    await flush();

    expect(within(mainRegion()).getByText(ARCHIVED_BADGE)).toBeInTheDocument();
    expect(button(RESTORE_NAME)).toBeInTheDocument();
    expect(sessionsRegion()).toBeInTheDocument();
    expect(
      within(sessionsRegion()).queryByRole("button", { name: START_SESSION_NAME, hidden: true }),
    ).toBeNull();
    expect(matching(calls, "POST", sessionsPath(ID_A))).toEqual([]);

    const composer = within(region(START_REGION));
    await user.type(composer.getByRole("textbox", { name: COMPOSER_LABEL }), "Hello there");
    await user.click(composer.getByRole("button", { name: SEND_NAME }));
    await flush();

    const posts = matching(calls, "POST", sessionsPath(ID_A));
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({ opening_message: "Hello there" });
    expect(locationPath()).toBe(`/sessions/${STARTED_ID}`);
  });
});

describe("moving between characters builds a fresh Sessions section (011 D15)", () => {
  it("requests the second character's sessions, shows only its rows and resets the switch — DoD-14", async () => {
    const user = newUser();
    const { calls } = stubBackend((request) => {
      if (request.method === "GET" && request.path === itemPath(ID_A)) {
        return jsonResponse(CHAR_A, 200);
      }
      if (request.method === "GET" && request.path === itemPath(ID_B)) {
        return jsonResponse(CHAR_B, 200);
      }
      if (request.method === "GET" && request.path === sessionsPath(ID_A)) {
        return jsonResponse({ sessions: [SESSION_OF_A] }, 200);
      }
      if (request.method === "GET" && request.path === sessionsPath(ID_B)) {
        return jsonResponse({ sessions: [SESSION_OF_B] }, 200);
      }
      // 018 step 009 (DoD-11): the configuration block's two reads, by exact path.
      const configuration = configurationListing(request, ID_A) ?? configurationListing(request, ID_B);
      if (configuration !== null) return configuration;
      if (
        request.method === "GET" &&
        (request.path === setupsPath(ID_A) || request.path === setupsPath(ID_B))
      ) {
        return jsonResponse(EMPTY_SETUPS, 200);
      }
      // 015 step 009: the Notes section lists each character's notes, answered empty.
      if (isNotesListing(request, ID_A) || isNotesListing(request, ID_B)) {
        return jsonResponse(EMPTY_NOTES, 200);
      }
      return notFoundResponse();
    });
    renderScreen(`/characters/${ID_A}`);
    await flush();
    expect(sessionHrefs()).toEqual([`/sessions/${SESSION_OF_A.id}`]);

    await user.click(sessionsSwitch());
    await flush();
    expect(sessionsSwitch()).toBeChecked();

    await user.click(screen.getByRole("button", { name: PROBE_NAVIGATE }));
    await flush();

    expect(locationPath()).toBe(`/characters/${ID_B}`);
    const listings = matching(calls, "GET", sessionsPath(ID_B));
    expect(listings).toHaveLength(1);
    expect(listings[0].search).toBe("");
    expect(sessionHrefs()).toEqual([`/sessions/${SESSION_OF_B.id}`]);
    expect(sessionsSwitch()).not.toBeChecked();
  });
});

// ---------------------------------------------------------------------------
// Feature 015, step 009 — the character-level "Notes" region's place on this screen (015
// DoD-4..DoD-6). Expected behaviour comes from 015's step file, 009.context.md and context.md:
// D1 (existing mode and "ready" only, after the "Sessions" region, keyed by the character id;
// its heading at the same order as the page's "Setups" and "Sessions" headings), D5 (a new
// note POSTs on blur), D8 (an archived character is a valid target) and the memos wire
// contract. The section's own behaviour is CharacterNotesSection.test.tsx's.
const NOTES_REGION = "Notes";
const NOTE_LABEL = "Note";
const NEW_NOTE_NAME = "New note";
/** 033 step 002's draft save button — removed by fast 012 (DoD-5); asserted absent below. */
const SAVE_NEW_NOTE_NAME = "Save new note";
const NO_NOTES_TEXT = "No notes yet.";

const NOTE_STAMP = "2026-10-02T09:26:53.000000+00:00";

/** A character-level wire Memo with all nine keys. */
function characterNote(id: string, characterId: string, body: string, sortKey = 0): Memo {
  return {
    id,
    scope: "character",
    scope_id: characterId,
    body,
    is_enabled: true,
    is_forced: false,
    sort_key: sortKey,
    created_at: NOTE_STAMP,
    updated_at: NOTE_STAMP,
  };
}

const NOTE_OF_A_1 = characterNote("7250000000000000201", ID_A, "Aria hums when she lies.");
const NOTE_OF_A_2 = characterNote("7250000000000000202", ID_A, "Aria never says goodbye.", 1);
const NOTE_OF_B = characterNote("7250000000000000203", ID_B, "Corvin keeps a ledger of debts.");

/** Every memo request of any kind — the pathname `/api/memos` is shared by all of them. */
function memoRequests(calls: Seen[]): Seen[] {
  return calls.filter((call) => call.path === MEMOS_PATH || call.path.startsWith(`${MEMOS_PATH}/`));
}

function notesRegion(): HTMLElement {
  return screen.getByRole("region", { name: NOTES_REGION });
}

/** 033 step 001: hidden included, so "no Notes region" also means "not even in a hidden tab". */
function queryNotesRegion(): HTMLElement | null {
  return screen.queryByRole("region", { name: NOTES_REGION, hidden: true });
}

/** Each note's text in the Notes region, in document order (each note's "Note" editor value). */
function noteBodies(): string[] {
  return within(notesRegion())
    .queryAllByRole("textbox", { name: NOTE_LABEL })
    .map((box) => (box as HTMLTextAreaElement).value);
}

function headingLevel(element: HTMLElement): number {
  const aria = element.getAttribute("aria-level");
  if (aria !== null) return Number(aria);
  const match = /^H([1-6])$/.exec(element.tagName);
  if (match === null) throw new Error(`not a heading element: ${element.tagName}`);
  return Number(match[1]);
}

describe("015 step 009 — the Notes region's place on the character screen (D1)", () => {
  it("(015 009 DoD-4, amended by 033 DoD-6: the Notes tab replaces the body order) once loaded, the Notes region is present with its heading inside the Notes tab panel — DoD-6", async () => {
    const { calls } = await renderLoaded(CHAR_A);

    // 033 step 001 (D1): the section lives in the "Notes" tab.
    openTab(NOTES_TAB);
    const notes = await screen.findByRole("region", { name: NOTES_REGION });
    const notesHeading = within(notes).getByRole("heading", { name: NOTES_REGION });
    expect(notesHeading).toBeInTheDocument();
    expect(within(mainRegion()).getByRole("region", { name: NOTES_REGION })).toBe(notes);
    expect(tabPanel(NOTES_TAB).contains(notes)).toBe(true);
    // The same heading order as the page's "Sessions" heading (now in a hidden panel).
    const sessionsHeading = within(
      screen.getByRole("region", { name: SESSIONS_REGION, hidden: true }),
    ).getByRole("heading", { name: SESSIONS_REGION, hidden: true });
    expect(headingLevel(notesHeading)).toBe(headingLevel(sessionsHeading));

    const reads = memoRequests(calls);
    expect(reads).toHaveLength(1);
    expect(reads[0]).toMatchObject({ method: "GET", path: MEMOS_PATH, search: notesSearch(ID_A) });
  });

  it("new mode at /characters/new renders no Notes region and makes no /api/memos request — DoD-4", async () => {
    const { calls } = stubBackend(() => notFoundResponse());
    renderScreen(NEW_PATH);
    await flush();

    expect(queryNotesRegion()).toBeNull();
    expect(memoRequests(calls)).toEqual([]);
  });

  it("the Character not found state renders no Notes region and makes no /api/memos request — DoD-4", async () => {
    const { calls } = stubBackend(() => notFoundResponse());
    renderScreen(`/characters/${ID_A}`);
    await flush();

    expect(within(mainRegion()).getByText(NOT_FOUND_TEXT)).toBeInTheDocument();
    expect(queryNotesRegion()).toBeNull();
    expect(memoRequests(calls)).toEqual([]);
  });

  it("the Could not load the character state renders no Notes region and makes no /api/memos request — DoD-4", async () => {
    const { calls } = stubBackend(() => serverError());
    renderScreen(`/characters/${ID_A}`);
    await flush();

    expect(within(mainRegion()).getByText(LOAD_FAILED_TEXT)).toBeInTheDocument();
    expect(queryNotesRegion()).toBeNull();
    expect(memoRequests(calls)).toEqual([]);
  });
});

describe("015 step 009 — an archived character still carries the Notes region (D8)", () => {
  it("renders the region and a new note there (header '+', then focus leaving the draft) POSTs with that character's id — DoD-5 (and fast 012 DoD-3, DoD-5, DoD-6)", async () => {
    const typed = "Voice: dry";
    const { calls } = stubBackend((request) => {
      if (request.method === "GET" && request.path === itemPath(ID_A)) {
        return jsonResponse(ARCHIVED_A, 200);
      }
      if (request.method === "POST" && request.path === MEMOS_PATH && request.search === "") {
        return jsonResponse(characterNote("9007199254740999", ID_A, typed), 201);
      }
      const listing = sectionListing(request, ID_A);
      if (listing !== null) return listing;
      return notFoundResponse();
    });
    renderScreen(`/characters/${ID_A}`);
    await flush();

    expect(within(mainRegion()).getByText(ARCHIVED_BADGE)).toBeInTheDocument();
    // 033 step 001 (D1): the section lives in the "Notes" tab.
    openTab(NOTES_TAB);
    await waitFor(() => {
      expect(within(notesRegion()).queryByText(NO_NOTES_TEXT)).not.toBeNull();
    });

    // fast 012 DoD-3/DoD-6: "New note" is the header icon button (one, beside the heading), and
    // the draft is saved when focus leaves it — there is no "Save new note" button (DoD-5).
    const user = newUser();
    const plusButtons = within(notesRegion()).getAllByRole("button", { name: NEW_NOTE_NAME });
    expect(plusButtons).toHaveLength(1);
    expect(plusButtons[0].textContent ?? "").not.toContain(NEW_NOTE_NAME);
    const notesHeading = within(notesRegion()).getByRole("heading", { name: NOTES_REGION });
    expect(notesHeading.parentElement?.contains(plusButtons[0])).toBe(true);
    await user.click(plusButtons[0]);
    await waitFor(() => {
      expect(within(notesRegion()).queryAllByRole("textbox", { name: NOTE_LABEL })).toHaveLength(1);
    });
    const editor = within(notesRegion()).getByRole("textbox", { name: NOTE_LABEL });
    fireEvent.change(editor, { target: { value: typed } });
    expect(within(notesRegion()).queryByRole("button", { name: SAVE_NEW_NOTE_NAME })).toBeNull();
    fireEvent.blur(editor);

    await waitFor(() => {
      expect(matching(calls, "POST", MEMOS_PATH)).toHaveLength(1);
    });
    const posts = matching(calls, "POST", MEMOS_PATH);
    expect(posts[0].search).toBe("");
    expect(posts[0].body).toEqual({ scope: "character", scope_id: ID_A, body: typed });
  });
});

describe("015 step 009 — moving between characters builds a fresh Notes region (D1)", () => {
  it("navigating from a to b requests b's notes listing and shows b's notes, with none of a's — DoD-6", async () => {
    const user = newUser();
    const { calls } = stubBackend((request) => {
      if (request.method === "GET" && request.path === itemPath(ID_A)) {
        return jsonResponse(CHAR_A, 200);
      }
      if (request.method === "GET" && request.path === itemPath(ID_B)) {
        return jsonResponse(CHAR_B, 200);
      }
      if (isNotesListing(request, ID_A)) {
        return jsonResponse({ memos: [NOTE_OF_A_1, NOTE_OF_A_2] }, 200);
      }
      if (isNotesListing(request, ID_B)) {
        return jsonResponse({ memos: [NOTE_OF_B] }, 200);
      }
      const listing = sectionListing(request, ID_A) ?? sectionListing(request, ID_B);
      if (listing !== null) return listing;
      return notFoundResponse();
    });
    renderScreen(`/characters/${ID_A}`);
    await flush();
    // 033 step 001 (D1): the section lives in the "Notes" tab.
    openTab(NOTES_TAB);
    await waitFor(() => {
      expect(noteBodies()).toEqual([NOTE_OF_A_1.body, NOTE_OF_A_2.body]);
    });

    await user.click(screen.getByRole("button", { name: PROBE_NAVIGATE }));
    await flush();

    expect(locationPath()).toBe(`/characters/${ID_B}`);
    // 033 step 001 (D1): the other character's page starts on "Sessions" again.
    openTab(NOTES_TAB);
    await waitFor(() => {
      expect(noteBodies()).toEqual([NOTE_OF_B.body]);
    });
    const bReads = calls.filter((call) => isNotesListing(call, ID_B));
    expect(bReads).toHaveLength(1);
    expect(within(notesRegion()).queryByDisplayValue(NOTE_OF_A_1.body)).toBeNull();
    expect(within(notesRegion()).queryByDisplayValue(NOTE_OF_A_2.body)).toBeNull();
    expect(screen.queryByDisplayValue(NOTE_OF_A_1.body)).toBeNull();
    expect(screen.queryByDisplayValue(NOTE_OF_A_2.body)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Feature 018, step 009 — the character page, assembled (018 DoD-1, DoD-2, DoD-4..DoD-7,
// DoD-9..DoD-11; DoD-3 and DoD-8 are App.test.tsx's, DoD-12 is [manual/live]). Expected values
// come from 018's step file, 009.context.md and context.md: D6 (the draft page), D7 (save on
// focus loss, flush on leaving), D10 (body order, no wall) and the UI strings table.
const DRAFT_BADGE = "Draft";
const DRAFT_LINE = "Nothing is saved until you enter a name.";
const NAME_REQUIRED_TEXT = "A character needs a name.";
const SEND_NAME = /^send$/i;
const CONFIGURATION_REGION = "Configuration";
// 033 step 001 (DoD-13, D8): the composer region is "New session" (was "Start a session").
const START_REGION = "New session";
const COMPOSER_LABEL = "Composer";
const MODEL_UNSET_LINE = "Not set: new sessions take the first enabled model.";
const WALL_LABEL = "Note wall";
const OPEN_NOTES_NAME = "Open notes";
const YOUR_NOTES = "Your notes";
const SESSION_NOTES = "Session notes";

/**
 * The five section regions of the ready page. 033 step 001 supersedes 018 D10's single-scroll
 * order: each now lives in its own tab panel (see `REGION_TAB`), so no clause asserts an order
 * across them any more.
 */
const BODY_REGIONS = [NOTES_REGION, "Setups", CONFIGURATION_REGION, "Sessions", START_REGION];

/** 033 step 001 (D1, D8, DoD-5, DoD-6): the tab panel each section region belongs to. */
const REGION_TAB: Record<string, string> = {
  [NOTES_REGION]: NOTES_TAB,
  Setups: SETUPS_TAB,
  [CONFIGURATION_REGION]: CONFIGURATION_TAB,
  Sessions: SESSIONS_TAB,
  [START_REGION]: SESSIONS_TAB,
};

const ID_C = "7250000000000000021";
const C_STAMP = "2026-07-01T09:00:00.000000+00:00";

const CHAR_C: Character = {
  id: ID_C,
  name: "Aria",
  sheet: "# Aria",
  archived_at: null,
  created_at: C_STAMP,
  updated_at: C_STAMP,
};

const ARCHIVED_C: Character = {
  ...CHAR_C,
  archived_at: "2026-07-02T09:00:00.000000+00:00",
  updated_at: "2026-07-02T09:00:00.000000+00:00",
};

/** What the create answers in the draft-page clauses: the typed name and persona, a new id. */
const CREATED_ARIA: Character = {
  id: CREATED_ID,
  name: "Aria",
  sheet: "# Aria",
  archived_at: null,
  created_at: C_STAMP,
  updated_at: C_STAMP,
};

const NOTE_OF_C_1 = characterNote("7250000000000000211", ID_C, "Aria keeps her promises late.", 0);
const NOTE_OF_C_2 = characterNote("7250000000000000212", ID_C, "Aria fears deep water.", 1);

/**
 * 018 step 009: GET and PATCH of each held row (a PATCH answers the row with the patch applied
 * and a later `updated_at`), every section listing of each, the given notes for each, and an
 * optional create answer for `POST /api/characters`. Everything else is a 404.
 */
function serveRows(
  rows: Character[],
  options: { notes?: Memo[]; onCreate?: () => Response | Promise<Response> } = {},
) {
  return stubBackend((request) => {
    if (request.method === "POST" && request.path === COLLECTION_PATH && options.onCreate) {
      return options.onCreate();
    }
    for (const row of rows) {
      if (request.path === itemPath(row.id) && request.search === "") {
        if (request.method === "GET") return jsonResponse(row, 200);
        if (request.method === "PATCH") {
          const patch = (request.body ?? {}) as Partial<Character>;
          return jsonResponse({ ...row, ...patch, updated_at: PATCHED_STAMP }, 200);
        }
      }
      if (options.notes !== undefined && isNotesListing(request, row.id)) {
        return jsonResponse({ memos: options.notes.filter((note) => note.scope_id === row.id) }, 200);
      }
      const listing = sectionListing(request, row.id);
      if (listing !== null) return listing;
    }
    return notFoundResponse();
  });
}

/** 033 step 001: hidden included, because most section regions sit in an inactive tab panel. */
function region(name: string): HTMLElement {
  return within(mainRegion()).getByRole("region", { name, hidden: true });
}

function queryRegionAnywhere(name: string): HTMLElement | null {
  return screen.queryByRole("region", { name, hidden: true });
}

describe("018 step 009 — the draft page at /characters/new (D6)", () => {
  it("shows New character, the Draft badge, the marker line, Name and Persona, and no Create / Save / Archive / Send, no section and no request — DoD-1", async () => {
    const { calls } = stubBackend(() => notFoundResponse());
    renderScreen(NEW_PATH);
    await flush();

    const main = within(mainRegion());
    expect(heading(NEW_HEADING)).toBeInTheDocument();
    expect(main.getByText(DRAFT_BADGE)).toBeInTheDocument();
    expect(main.getByText(DRAFT_LINE)).toBeInTheDocument();
    expect(nameInput()).toBeInTheDocument();
    expect(personaInput()).toBeInTheDocument();

    for (const name of [CREATE_NAME, SAVE_NAME, ARCHIVE_NAME, SEND_NAME]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
    for (const name of BODY_REGIONS) {
      expect(queryRegionAnywhere(name)).toBeNull();
    }
    expect(calls).toEqual([]);
  });

  it("blurring an empty Name, typing a persona and blurring it, then unmounting with only the persona typed sends nothing — DoD-2", async () => {
    const user = newUser();
    const { calls } = stubBackend(() => notFoundResponse());
    const { view } = renderScreen(NEW_PATH);

    await user.click(nameInput());
    await user.tab();
    await flush();
    expect(calls).toEqual([]);

    await user.type(personaInput(), TYPED_SHEET);
    await user.tab();
    await flush();
    expect(calls).toEqual([]);
    expect(personaInput()).toHaveValue(TYPED_SHEET);

    view.unmount();
    await flush();
    expect(calls).toEqual([]);
  });

  it("while the create is pending Name and Persona are read-only and blurring Name again sends no second POST — DoD-4", async () => {
    const user = newUser();
    const gate = deferred<Response>();
    const { calls } = serveRows([CREATED_ARIA], { onCreate: () => gate.promise });
    renderScreen(NEW_PATH);

    await user.type(personaInput(), "# Aria");
    await user.type(nameInput(), "Aria");
    await user.tab();
    await flush();

    expect(matching(calls, "POST", COLLECTION_PATH)).toHaveLength(1);
    expect(nameInput()).toHaveAttribute("readonly");
    expect(personaInput()).toHaveAttribute("readonly");

    fireEvent.focus(nameInput());
    fireEvent.blur(nameInput());
    await flush();
    expect(matching(calls, "POST", COLLECTION_PATH)).toHaveLength(1);

    gate.resolve(jsonResponse(CREATED_ARIA, 201));
    await flush();
    expect(matching(calls, "POST", COLLECTION_PATH)).toHaveLength(1);
  });

  it("a failed create shows Could not create the character., keeps Aria and the persona, stays at /characters/new and still shows Draft — DoD-4", async () => {
    const user = newUser();
    const { calls } = serveRows([], { onCreate: () => serverError() });
    renderScreen(NEW_PATH);

    await user.type(personaInput(), "# Aria");
    await user.type(nameInput(), "Aria");
    await user.tab();
    await flush();

    expect(matching(calls, "POST", COLLECTION_PATH)).toHaveLength(1);
    expect(within(mainRegion()).getByText(CREATE_FAILED_TEXT)).toBeInTheDocument();
    expect(nameInput()).toHaveValue("Aria");
    expect(personaInput()).toHaveValue("# Aria");
    expect(locationPath()).toBe(NEW_PATH);
    expect(within(mainRegion()).getByText(DRAFT_BADGE)).toBeInTheDocument();
  });
});

describe("018 step 009 — name and persona save on focus loss at /characters/<id> (D7)", () => {
  it("there is no Save button, and changing Name to Aria Vale and blurring sends exactly PATCH {name} and the heading reads Aria Vale — DoD-5 (and 033 DoD-7)", async () => {
    const user = newUser();
    const { calls } = serveRows([CHAR_C]);
    renderScreen(`/characters/${ID_C}`);
    await flush();

    expect(heading(CHAR_C.name)).toBeInTheDocument();
    expect(queryButton(SAVE_NAME)).toBeNull();

    // 033 step 001 (D4): Name lives in "Main info".
    openTab(MAIN_INFO_TAB);
    await typeInto(user, nameInput(), "Aria Vale");
    await user.tab();
    await flush();

    const patches = matching(calls, "PATCH", itemPath(ID_C));
    expect(patches.map((call) => call.body)).toEqual([{ name: "Aria Vale" }]);
    expect(heading("Aria Vale")).toBeInTheDocument();
  });

  it("clearing Name and blurring sends nothing, shows A character needs a name. on the Name field and keeps the saved name as the heading — DoD-5 (and 033 DoD-7)", async () => {
    const user = newUser();
    const { calls } = serveRows([CHAR_C]);
    renderScreen(`/characters/${ID_C}`);
    await flush();

    // 033 step 001 (D4): Name lives in "Main info".
    openTab(MAIN_INFO_TAB);
    await user.clear(nameInput());
    await user.tab();
    await flush();

    expect(matching(calls, "PATCH", itemPath(ID_C))).toEqual([]);
    expect(nameInput()).toHaveAccessibleDescription(/A character needs a name\./);
    expect(within(mainRegion()).getByText(NAME_REQUIRED_TEXT)).toBeInTheDocument();
    expect(nameInput()).toHaveValue("");
    expect(heading(CHAR_C.name)).toBeInTheDocument();
  });

  it("changing the persona and blurring its editor sends exactly PATCH {sheet} — DoD-5 (and 033 DoD-7)", async () => {
    const user = newUser();
    const changed = "A duelist with a borrowed name.";
    const { calls } = serveRows([CHAR_C]);
    renderScreen(`/characters/${ID_C}`);
    await flush();

    // 033 step 001 (D4): Persona lives in "Main info".
    openTab(MAIN_INFO_TAB);
    await typeInto(user, personaInput(), changed);
    await user.tab();
    await flush();

    const patches = matching(calls, "PATCH", itemPath(ID_C));
    expect(patches.map((call) => call.body)).toEqual([{ sheet: changed }]);
  });

  it("leaving by an in-entry navigation after changing the persona without blurring sends exactly one PATCH {sheet} — DoD-9", async () => {
    const changed = "Changed and never blurred.";
    const { calls } = serveRows([CHAR_C, CHAR_B]);
    renderScreen(`/characters/${ID_C}`);
    await flush();

    // 033 step 001 (D4): Persona lives in "Main info".
    openTab(MAIN_INFO_TAB);
    // A change event alone: focus never enters the editor, so it never leaves it either.
    fireEvent.change(personaInput(), { target: { value: changed } });
    expect(matching(calls, "PATCH", itemPath(ID_C))).toEqual([]);

    // A click event alone moves no focus; the navigation unmounts the screen.
    fireEvent.click(screen.getByRole("button", { name: PROBE_NAVIGATE }));
    await flush();

    expect(locationPath()).toBe(`/characters/${ID_B}`);
    const patches = matching(calls, "PATCH", itemPath(ID_C));
    expect(patches.map((call) => call.body)).toEqual([{ sheet: changed }]);
  });
});

describe("018 step 009 — the page's sections, the notes cards and no wall (D10, amended by 033 D1)", () => {
  it("(018 DoD-6, amended by 033 DoD-6: tab panels replace the body order) once loaded each section region sits in its own tab panel, and the notes are focusable cards named Note <n> of <total> — DoD-6", async () => {
    serveRows([CHAR_C], { notes: [NOTE_OF_C_1, NOTE_OF_C_2] });
    renderScreen(`/characters/${ID_C}`);
    await flush();

    for (const name of BODY_REGIONS) {
      expect(tabPanel(REGION_TAB[name]).contains(region(name))).toBe(true);
    }

    openTab(NOTES_TAB);
    const notes = await within(mainRegion()).findByRole("region", { name: NOTES_REGION });
    await waitFor(() => {
      expect(within(notes).getByRole("listitem", { name: "Note 2 of 2" })).toBeInTheDocument();
    });

    const first = within(notes).getByRole("listitem", { name: "Note 1 of 2" });
    const second = within(notes).getByRole("listitem", { name: "Note 2 of 2" });
    expect(first.tabIndex).toBe(0);
    expect(second.tabIndex).toBe(0);
    expect(precedes(first, second)).toBe(true);
  });

  it("the page renders no Note wall, no Open notes, no Your notes / Session notes group and makes no /memo-chain request — DoD-7", async () => {
    const { calls } = serveRows([CHAR_C], { notes: [NOTE_OF_C_1] });
    renderScreen(`/characters/${ID_C}`);
    await flush();
    // 033 step 001: the Notes region sits in a (hidden) tab panel on arrival.
    await within(mainRegion()).findByRole("region", { name: NOTES_REGION, hidden: true });

    expect(
      screen
        .queryAllByRole("complementary", { hidden: true })
        .filter((element) => element.getAttribute("aria-label") === WALL_LABEL),
    ).toEqual([]);
    expect(document.querySelector(`[aria-label="${WALL_LABEL}"]`)).toBeNull();
    expect(screen.queryByRole("button", { name: OPEN_NOTES_NAME, hidden: true })).toBeNull();
    for (const name of [YOUR_NOTES, SESSION_NOTES]) {
      expect(queryRegionAnywhere(name)).toBeNull();
      expect(screen.queryByRole("heading", { name, hidden: true })).toBeNull();
    }
    expect(calls.filter((call) => call.path.endsWith("/memo-chain"))).toEqual([]);
  });

  it("an archived character still renders every section, the configuration block and the composer included, with Restore in place of Archive — DoD-10 (and 033 DoD-11)", async () => {
    serveRows([ARCHIVED_C]);
    renderScreen(`/characters/${ID_C}`);
    await flush();

    expect(within(mainRegion()).getByText(ARCHIVED_BADGE)).toBeInTheDocument();
    expect(button(RESTORE_NAME)).toBeInTheDocument();
    expect(queryButton(ARCHIVE_NAME)).toBeNull();

    // 033 step 001 (DoD-11): all five tabs, each section in its own tab panel.
    expectFiveTabsInOrder();
    for (const name of BODY_REGIONS) {
      expect(region(name)).toBeInTheDocument();
      expect(tabPanel(REGION_TAB[name]).contains(region(name))).toBe(true);
    }
    expect(await within(region(CONFIGURATION_REGION)).findByText(MODEL_UNSET_LINE)).toBeInTheDocument();
    expect(within(region(START_REGION)).getByRole("textbox", { name: COMPOSER_LABEL })).toBeInTheDocument();
    expect(within(region(START_REGION)).getByRole("button", { name: SEND_NAME })).toBeInTheDocument();
  });

  it("the ready page's configuration and models reads are answered by exact path, so the block loads with no failure — DoD-11", async () => {
    const { calls } = serveRows([CHAR_C]);
    renderScreen(`/characters/${ID_C}`);
    await flush();

    expect(await within(region(CONFIGURATION_REGION)).findByText(MODEL_UNSET_LINE)).toBeInTheDocument();
    expect(within(mainRegion()).queryByText("Could not load the configuration")).toBeNull();
    expect(matching(calls, "GET", configurationPath(ID_C))).toHaveLength(1);
    expect(matching(calls, "GET", MODELS_PATH)).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// Bug fix (018 step 009) — repro: typing into the Persona editor on a loaded character's page
// duplicated everything below Archive / Export (Notes, Setups, Configuration, Sessions, Start a
// session) on every keystroke. Spec: 018 DoD-6 (the five regions, once each, in that order) and
// DoD-5 (name and persona are edited in place and saved on focus loss) — editing must not change
// the body's structure. The stubbed editor calls `onChange` on every keystroke, so each typed
// character re-renders the screen.

/**
 * Asserts each of the five section regions occurs exactly once on the whole page — hidden tab
 * panels included — and sits in its own tab panel. 033 step 001 (DoD-10) replaces 018 D10's
 * order check with the tab-panel check; the exactly-once guarantee (commit 8f86926) is kept.
 */
function expectEachBodyRegionOnce(): void {
  for (const name of BODY_REGIONS) {
    expect(screen.getAllByRole("region", { name, hidden: true })).toHaveLength(1);
    expect(tabPanel(REGION_TAB[name]).contains(region(name))).toBe(true);
  }
  expect(screen.getAllByRole("tablist", { hidden: true })).toHaveLength(1);
}

describe("bug fix — editing the persona or name keeps one copy of each body region (018 D10, amended by 033 D1)", () => {
  it("typing abc keystroke by keystroke into Persona without blurring leaves Notes, Setups, Configuration, Sessions and New session exactly once each — DoD-6 (and 033 DoD-10)", async () => {
    const user = newUser();
    await renderLoaded(CHAR_A);
    await within(mainRegion()).findByRole("region", { name: NOTES_REGION, hidden: true });
    expectEachBodyRegionOnce();

    openTab(MAIN_INFO_TAB);
    await user.type(personaInput(), "abc");
    await flush();

    expect(personaInput()).toHaveValue(`${CHAR_A.sheet}abc`);
    expectEachBodyRegionOnce();
  });

  it("typing xyz keystroke by keystroke into Name without blurring leaves each body region exactly once — DoD-6 (and 033 DoD-10)", async () => {
    const user = newUser();
    await renderLoaded(CHAR_A);
    await within(mainRegion()).findByRole("region", { name: NOTES_REGION, hidden: true });
    expectEachBodyRegionOnce();

    openTab(MAIN_INFO_TAB);
    await user.type(nameInput(), "xyz");
    await flush();

    expect(nameInput()).toHaveValue(`${CHAR_A.name}xyz`);
    expectEachBodyRegionOnce();
  });
});

// ---------------------------------------------------------------------------
// Feature 033, step 001 — the tabbed character page (033 DoD-1..DoD-13; DoD-14 and DoD-15 are
// [manual/live]). Expected values come from 033's step file and context.md: D1 (five tabs in the
// order Sessions, Main info, Configuration, Notes, Setups; Sessions selected on open; the active
// tab is local state, not in the URL), D2 (keepMounted: every section mounts and loads once on
// open; the draft page has no tabs and no sections), D3 (page header: saved name, "Archived"
// badge, icon-only Archive/Restore and Export), D4 (Name + Persona in Main info), D5
// (Configuration moved as-is) and D8 (the Sessions tab: "New session" composer, a divider, then
// the sessions list). Tab structure is asserted through `tab` / `tabpanel` roles and
// `aria-selected` (context.md "Tests — feature-wide notes").
const DIVIDER = ".mantine-Divider-root";
const EXPORT_NAME = /^export$/i;
const HEADER_ACTION_NAMES = [ARCHIVE_NAME, RESTORE_NAME, EXPORT_NAME];

/** True when `element` sits in the page header: before the tab list and in no tab panel. */
function isInPageHeader(element: HTMLElement): boolean {
  return precedes(element, tablist()) && element.closest('[role="tabpanel"]') === null;
}

function expectSelectedTab(name: string): void {
  for (const candidate of TAB_NAMES) {
    expect(tab(candidate)).toHaveAttribute("aria-selected", candidate === name ? "true" : "false");
  }
}

describe("033 step 001 — the five tabs (D1)", () => {
  it("a saved character's page shows one tab list with exactly five tabs: Sessions, Main info, Configuration, Notes, Setups — 033 DoD-1", async () => {
    serveRows([CHAR_C]);
    renderScreen(`/characters/${ID_C}`);
    await flush();

    expectFiveTabsInOrder();
  });

  it("on opening /characters/<id> the Sessions tab is selected and its panel is the one shown — 033 DoD-2", async () => {
    serveRows([CHAR_C]);
    renderScreen(`/characters/${ID_C}`);
    await flush();

    expectSelectedTab(SESSIONS_TAB);
    const shown = within(mainRegion()).getAllByRole("tabpanel");
    expect(shown).toHaveLength(1);
    expect(shown[0]).toBe(tabPanel(SESSIONS_TAB));
  });

  it("selecting each other tab selects it and leaves the URL unchanged — 033 DoD-3", async () => {
    serveRows([CHAR_C]);
    renderScreen(`/characters/${ID_C}`);
    await flush();
    const before = fullLocation();
    expect(before).toBe(`/characters/${ID_C}`);

    for (const name of [MAIN_INFO_TAB, CONFIGURATION_TAB, NOTES_TAB, SETUPS_TAB, SESSIONS_TAB]) {
      openTab(name);
      await flush(2);
      expectSelectedTab(name);
      expect(fullLocation()).toBe(before);
    }
  });

  it("navigating to a different character's page lands on its Sessions tab again — 033 DoD-3", async () => {
    const user = newUser();
    serveRows([CHAR_C, CHAR_B]);
    renderScreen(`/characters/${ID_C}`);
    await flush();

    openTab(MAIN_INFO_TAB);
    expectSelectedTab(MAIN_INFO_TAB);

    await user.click(screen.getByRole("button", { name: PROBE_NAVIGATE }));
    await flush();

    expect(locationPath()).toBe(`/characters/${ID_B}`);
    expect(heading(CHAR_B.name)).toBeInTheDocument();
    expectSelectedTab(SESSIONS_TAB);
  });
});

describe("033 step 001 — every section mounts and loads once at page open (D2)", () => {
  it("every section region is in the document at open, each initial load is issued once (one notes memos GET), and switching through every tab issues no further request — 033 DoD-4", async () => {
    const { calls } = serveRows([CHAR_C]);
    renderScreen(`/characters/${ID_C}`);
    await flush();

    // Inactive tabs included: every section is mounted on arrival.
    for (const name of BODY_REGIONS) {
      expect(screen.getAllByRole("region", { name, hidden: true })).toHaveLength(1);
    }

    expect(matching(calls, "GET", itemPath(ID_C))).toHaveLength(1);
    // Notes: exactly one memos request, and it is the character's notes listing.
    expect(memoRequests(calls)).toHaveLength(1);
    expect(calls.filter((call) => isNotesListing(call, ID_C))).toHaveLength(1);
    // Configuration: its own read and the enabled-models read, once each.
    expect(matching(calls, "GET", configurationPath(ID_C))).toHaveLength(1);
    expect(matching(calls, "GET", MODELS_PATH)).toHaveLength(1);
    // Sessions: its listing, once.
    expect(matching(calls, "GET", sessionsPath(ID_C))).toHaveLength(1);
    // Setups: its listing was requested at open (the same path may also serve another section).
    expect(matching(calls, "GET", setupsPath(ID_C)).length).toBeGreaterThan(0);

    const requestsAtOpen = calls.length;
    for (const name of [MAIN_INFO_TAB, CONFIGURATION_TAB, NOTES_TAB, SETUPS_TAB, SESSIONS_TAB]) {
      openTab(name);
      await flush(2);
    }
    // And once more round, so a tab revisited is covered too.
    for (const name of [NOTES_TAB, SETUPS_TAB, CONFIGURATION_TAB, MAIN_INFO_TAB, SESSIONS_TAB]) {
      openTab(name);
      await flush(2);
    }
    await flush();

    expect(calls).toHaveLength(requestsAtOpen);
  });
});

describe("033 step 001 — what each tab panel holds (D4, D5, D8, US-096)", () => {
  it("the Sessions panel holds the New session region, then a divider, then the Sessions region — 033 DoD-5", async () => {
    serveRows([CHAR_C]);
    renderScreen(`/characters/${ID_C}`);
    await flush();

    const panel = tabPanel(SESSIONS_TAB);
    const composerRegion = within(panel).getByRole("region", { name: START_REGION });
    const listRegion = within(panel).getByRole("region", { name: "Sessions" });
    expect(precedes(composerRegion, listRegion)).toBe(true);

    const separating = Array.from(panel.querySelectorAll<HTMLElement>(DIVIDER)).filter(
      (divider) =>
        !composerRegion.contains(divider) &&
        !listRegion.contains(divider) &&
        precedes(composerRegion, divider) &&
        precedes(divider, listRegion),
    );
    expect(separating.length).toBeGreaterThan(0);
  });

  it("the Main info panel holds the Name input and the Persona editor; the Configuration, Notes and Setups panels hold their regions — 033 DoD-6", async () => {
    serveRows([CHAR_C]);
    renderScreen(`/characters/${ID_C}`);
    await flush();

    const mainInfo = within(tabPanel(MAIN_INFO_TAB));
    expect(mainInfo.getByRole("textbox", { name: NAME_LABEL, hidden: true })).toHaveValue(CHAR_C.name);
    expect(mainInfo.getByRole("textbox", { name: PERSONA_LABEL, hidden: true })).toHaveValue(
      CHAR_C.sheet,
    );
    // Name and Persona are not in the Sessions panel shown on arrival.
    expect(within(tabPanel(SESSIONS_TAB)).queryByRole("textbox", { name: NAME_LABEL, hidden: true })).toBeNull();
    expect(
      within(tabPanel(SESSIONS_TAB)).queryByRole("textbox", { name: PERSONA_LABEL, hidden: true }),
    ).toBeNull();

    for (const [tabName, regionName] of [
      [CONFIGURATION_TAB, CONFIGURATION_REGION],
      [NOTES_TAB, NOTES_REGION],
      [SETUPS_TAB, "Setups"],
    ] as const) {
      expect(
        within(tabPanel(tabName)).getByRole("region", { name: regionName, hidden: true }),
      ).toBeInTheDocument();
    }

    // Opening each tab shows its contents.
    openTab(MAIN_INFO_TAB);
    expect(nameInput()).toHaveValue(CHAR_C.name);
    expect(personaInput()).toHaveValue(CHAR_C.sheet);
    for (const [tabName, regionName] of [
      [CONFIGURATION_TAB, CONFIGURATION_REGION],
      [NOTES_TAB, NOTES_REGION],
      [SETUPS_TAB, "Setups"],
    ] as const) {
      openTab(tabName);
      const shown = within(mainRegion()).getByRole("region", { name: regionName });
      expect(tabPanel(tabName).contains(shown)).toBe(true);
    }
  });

  it("the composer region is named New session, and no Start a session region remains — 033 DoD-13", async () => {
    serveRows([CHAR_C]);
    renderScreen(`/characters/${ID_C}`);
    await flush();

    const composerRegion = within(mainRegion()).getByRole("region", { name: "New session" });
    expect(within(composerRegion).getByRole("heading", { name: "New session" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Start a session", hidden: true })).toBeNull();
  });
});

describe("033 step 001 — name and persona still save on focus loss from Main info (D4, UC-073)", () => {
  it("in Main info, a changed name and a changed persona each PATCH on focus loss, and a blank name is refused with no request — 033 DoD-7", async () => {
    const user = newUser();
    const { calls } = serveRows([CHAR_C]);
    renderScreen(`/characters/${ID_C}`);
    await flush();
    openTab(MAIN_INFO_TAB);

    await user.clear(nameInput());
    await user.tab();
    await flush();
    expect(matching(calls, "PATCH", itemPath(ID_C))).toEqual([]);
    expect(within(mainRegion()).getByText(NAME_REQUIRED_TEXT)).toBeInTheDocument();

    await user.type(nameInput(), "Aria Vale");
    await user.tab();
    await flush();
    // Rework (verifier TEST fault): serveRows answers each PATCH statelessly (loaded row + that
    // request's fields), and the header shows the name as last reported (018 D7). So the renamed
    // heading is asserted right after the name update, before the persona update.
    expect(heading("Aria Vale")).toBeInTheDocument();

    await typeInto(user, personaInput(), "Shorter.");
    await user.tab();
    await flush();

    const patches = matching(calls, "PATCH", itemPath(ID_C));
    expect(patches.map((call) => call.body)).toEqual([{ name: "Aria Vale" }, { sheet: "Shorter." }]);
  });
});

describe("033 step 001 — the page header (D3)", () => {
  it("the header shows the saved name and icon-only Archive and Export, above the tabs, and no labelled Archive/Restore/Export text remains — 033 DoD-8", async () => {
    serveRows([CHAR_C]);
    renderScreen(`/characters/${ID_C}`);
    await flush();

    const title = heading(CHAR_C.name);
    expect(isInPageHeader(title)).toBe(true);
    expect(within(mainRegion()).queryByText(ARCHIVED_BADGE)).toBeNull();

    for (const name of [ARCHIVE_NAME, EXPORT_NAME]) {
      // Exactly one such control on the whole page, hidden tab panels included.
      const all = within(mainRegion()).getAllByRole("button", { name, hidden: true });
      expect(all).toHaveLength(1);
      expect(all[0]).toBe(button(name));
      expect(isInPageHeader(all[0])).toBe(true);
      expect((all[0].textContent ?? "").trim()).toBe("");
    }
    expect(within(mainRegion()).queryByRole("button", { name: RESTORE_NAME, hidden: true })).toBeNull();
    // No text label reading Archive / Restore / Export anywhere in the page, hidden panels included.
    expect(within(mainRegion()).queryAllByText(/^(archive|restore|export)$/i)).toEqual([]);
  });

  it("an archived character's header shows the saved name, the Archived badge and icon-only Restore and Export — 033 DoD-8", async () => {
    serveRows([ARCHIVED_C]);
    renderScreen(`/characters/${ID_C}`);
    await flush();

    expect(isInPageHeader(heading(ARCHIVED_C.name))).toBe(true);
    const badge = within(mainRegion()).getByText(ARCHIVED_BADGE);
    expect(isInPageHeader(badge)).toBe(true);

    for (const name of [RESTORE_NAME, EXPORT_NAME]) {
      const all = within(mainRegion()).getAllByRole("button", { name, hidden: true });
      expect(all).toHaveLength(1);
      expect(isInPageHeader(all[0])).toBe(true);
      expect((all[0].textContent ?? "").trim()).toBe("");
    }
    expect(within(mainRegion()).queryByRole("button", { name: ARCHIVE_NAME, hidden: true })).toBeNull();
    expect(within(mainRegion()).queryAllByText(/^(archive|restore|export)$/i)).toEqual([]);
  });
});

describe("033 step 001 — the header's Archive and Restore still work (D3)", () => {
  it("clicking the header's Archive archives the character (badge, Restore in its place); clicking Restore restores it — 033 DoD-9", async () => {
    const user = newUser();
    const { calls } = stubBackend((request) => {
      if (request.method === "GET" && request.path === itemPath(ID_C)) {
        return jsonResponse(CHAR_C, 200);
      }
      if (request.method === "POST" && request.path === `${itemPath(ID_C)}/archive`) {
        return jsonResponse(ARCHIVED_C, 200);
      }
      if (request.method === "POST" && request.path === `${itemPath(ID_C)}/restore`) {
        return jsonResponse(CHAR_C, 200);
      }
      const listing = sectionListing(request, ID_C);
      if (listing !== null) return listing;
      return notFoundResponse();
    });
    renderScreen(`/characters/${ID_C}`);
    await flush();

    await user.click(button(ARCHIVE_NAME));
    await flush();

    expect(matching(calls, "POST", `${itemPath(ID_C)}/archive`)).toHaveLength(1);
    expect(isInPageHeader(within(mainRegion()).getByText(ARCHIVED_BADGE))).toBe(true);
    expect(isInPageHeader(button(RESTORE_NAME))).toBe(true);
    expect(queryButton(ARCHIVE_NAME)).toBeNull();
    // The tabs survive the archive.
    expectFiveTabsInOrder();

    await user.click(button(RESTORE_NAME));
    await flush();

    expect(matching(calls, "POST", `${itemPath(ID_C)}/restore`)).toHaveLength(1);
    expect(within(mainRegion()).queryByText(ARCHIVED_BADGE)).toBeNull();
    expect(isInPageHeader(button(ARCHIVE_NAME))).toBe(true);
  });
});

describe("033 step 001 — the draft page has no tabs (D2, US-097)", () => {
  it("/characters/new renders no tab list, no tab, no section region and no header icon action — 033 DoD-12", async () => {
    const { calls } = stubBackend(() => notFoundResponse());
    renderScreen(NEW_PATH);
    await flush();

    expect(heading(NEW_HEADING)).toBeInTheDocument();
    expect(nameInput()).toBeInTheDocument();
    expect(personaInput()).toBeInTheDocument();

    expect(queryTablistAnywhere()).toBeNull();
    expect(screen.queryAllByRole("tab", { hidden: true })).toEqual([]);
    expect(screen.queryAllByRole("tabpanel", { hidden: true })).toEqual([]);
    for (const name of [...BODY_REGIONS, "Start a session"]) {
      expect(queryRegionAnywhere(name)).toBeNull();
    }
    for (const name of HEADER_ACTION_NAMES) {
      expect(screen.queryByRole("button", { name, hidden: true })).toBeNull();
    }
    expect(calls).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Feature 033, step 004 — the composer's Setup select on the page (D8). The composer lists the
// character's setups on mount; `sectionListing` already answers that path with no setups, so the
// existing clauses keep their meaning (setups listings are never counted as exactly one here).
describe("033 step 004 — the New session composer carries a Setup select (D8)", () => {
  it('the Sessions tab\'s "New session" composer shows a "Setup" select reading "No setup" on open — 033 step 004 DoD-2', async () => {
    const { calls } = serveRows([CHAR_C]);
    renderScreen(`/characters/${ID_C}`);
    await flush();

    const composerRegion = within(tabPanel(SESSIONS_TAB)).getByRole("region", { name: START_REGION });
    const scope = within(composerRegion);
    const setupField =
      scope.queryByRole("combobox", { name: /^setup$/i }) ??
      scope.queryByRole("textbox", { name: /^setup$/i }) ??
      scope.getByLabelText(/^setup$/i);
    expect((setupField as HTMLInputElement).value).toBe("No setup");
    expect(matching(calls, "GET", setupsPath(ID_C)).length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// Feature 033, step 005 — the sessions list loses its message-less start (D9) and carries the
// icon-only "Import session" in its header (D8). The section's own behaviour is
// SessionsSection.test.tsx's; these clauses assert what the page shows on open.
describe("033 step 005 — the Sessions tab's list has no start control of its own (D8, D9)", () => {
  it("the Sessions region holds no Setup select and no Start session button; the only Setup select is the composer's — 033 step 005 DoD-1", async () => {
    serveRows([CHAR_C]);
    renderScreen(`/characters/${ID_C}`);
    await flush();

    const sessions = within(region("Sessions"));
    expect(sessions.queryByRole("button", { name: START_SESSION_NAME, hidden: true })).toBeNull();
    expect(sessions.queryByRole("combobox", { name: /^setup$/i, hidden: true })).toBeNull();
    expect(sessions.queryByRole("textbox", { name: /^setup$/i, hidden: true })).toBeNull();
    expect(sessions.queryByLabelText(/^setup$/i)).toBeNull();
    expect(sessions.queryByText("Could not load setups to choose from.")).toBeNull();
    // The page's one start control is the "New session" composer's.
    expect(screen.queryAllByRole("button", { name: START_SESSION_NAME, hidden: true })).toEqual([]);
  });

  it("the Sessions region's header carries an Import session button — 033 step 005 DoD-2", async () => {
    serveRows([CHAR_C]);
    renderScreen(`/characters/${ID_C}`);
    await flush();

    const sessions = within(region("Sessions"));
    expect(sessions.getAllByRole("button", { name: /^import session$/i })).toHaveLength(1);
  });

  it("opening the page sends no session create at all — 033 step 005 DoD-4", async () => {
    const { calls } = serveRows([CHAR_C]);
    renderScreen(`/characters/${ID_C}`);
    await flush();
    await within(mainRegion()).findByRole("region", { name: NOTES_REGION, hidden: true });
    await flush();

    expect(matching(calls, "POST", sessionsPath(ID_C))).toEqual([]);
  });
});
