// Feature 008, step 004 — the in-entry route table (DoD-10, DoD-11).
// The shell component's own clauses (DoD-1..DoD-9) live in WorkspaceShell.test.tsx;
// 008's DoD-12 and DoD-13 are [manual/live] and carry no test.
// Four declared routes are still the same shell around an **empty** centre (008 D5), and an
// undeclared path renders "Page not found" inside that same shell. `App` creates no router,
// so every render here supplies a MemoryRouter (008 004.context.md).
//
// Amended by feature 009, step 007 (DoD-13): `/characters/new` and `/characters/1` no longer
// have empty centres — they render the character screen (009 D1, D11), so the two clauses
// that asserted an empty main region at those two paths are replaced by the block at the
// bottom of this file. The `/characters/1` case stubs `GET /api/characters/1`, and
// `src/shared/MarkdownEditor` is replaced by the sanctioned stub (009 context.md, "Test
// conventions — TipTap in jsdom").
//
// Amended by feature 009, step 008 (DoD-8..DoD-10): every route now mounts the character
// tree in the shell's expanded column, so every render stubs `GET /api/characters`. The three
// integration clauses at the bottom drive the character screen and assert what the tree shows
// (009 D11: the screen applies the server's returned row to the one workspace state, so a
// mutation never refetches the list).
//
// Amended by feature 010, step 006 (DoD-13): the character screen's "ready" render now carries
// the "Setups" section (010 D1), which loads `GET /api/characters/<id>/setups` on mount. Every
// stub whose character load succeeds answers that path with `{ "setups": [] }` — routed by URL,
// because `stubWorkspace`'s fallback would otherwise answer it 404 `character_not_found` and
// drive the section into its failed state. An empty listing renders no setup rows, so no setup
// badge, row menu or setups-side control exists and every assertion below keeps its meaning.
// `listRequests` stays keyed on the **exact** path `/api/characters`, so the section's listing
// is correctly not counted and 009 step 008 DoD-8 survives as written. `/characters/new` mounts
// no section (010 D1), so its stub — which rejects every other URL — is unchanged. The tree's
// switch is "Show archived" and the section's is "Show archived setups", so the anchored
// `/^show archived$/i` of `archivedSwitch()` still matches only the tree's.
//
// Amended by feature 011, step 006 (DoD-11): `App` now creates the one workspace
// `SessionsState` and the tree loads it on mount, so **every** route mounts a tree that issues
// `GET /api/sessions`. Every stub in this file answers that path — routed by the **exact**
// pathname, because `/api/characters` and `/api/characters/<id>/sessions` share a prefix — and
// `listRequests` stays keyed on the exact `/api/characters`, so 009 step 008 DoD-8's
// "no list request after the create" survives untouched. No 009 or 010 assertion is dropped,
// and `EMPTY_CENTRE_ROUTES` keeps `/sessions/1`: the centre is still empty in this step (the
// tree lives in the nav column), and removing that entry is step 009's edit.
//
// Amended by feature 011, step 008 (DoD-16): the character screen's "ready" render now carries
// the "Sessions" region (011 D1), which loads `GET /api/characters/<id>/sessions` on mount and
// a second `GET /api/characters/<id>/setups` for its Select's choices. Every stub whose
// character load succeeds answers both — routed by the **exact** pathname, because
// `/api/sessions`, `/api/characters` and `/api/characters/<id>/sessions` share prefixes — and
// `stubWorkspace` grew the rest of the sessions wire contract (start, archive, restore) for the
// DoD-15 block at the bottom. `listRequests` stays keyed on the exact `/api/characters`, so 009
// step 008 DoD-8's "no list request after the create" survives as written, and DoD-15's "no
// second `GET /api/sessions`" is written the same way, keyed on that exact path.
// `/characters/new` mounts no section (011 D1), so its stub — which rejects every other URL —
// is unchanged, and `EMPTY_CENTRE_ROUTES` is untouched (its `/sessions/1` entry is step 009's
// edit). No 009, 010 or 011 step 006 assertion is dropped.
//
// Amended by feature 011, step 009 (DoD-11): `/sessions/:id` is no longer an empty centre — it
// renders the session screen (011 D17), which loads `GET /api/sessions/<id>` on mount. So
// `EMPTY_CENTRE_ROUTES` **loses its `/sessions/1` entry**, which the two clauses at the bottom
// of this file cover instead; `/`, `/settings`, `/search` and the `*` "Page not found" clause
// are unchanged, as is every 009, 010 and 011 step 006 / 008 assertion. `stubWorkspace` gained
// one branch — a GET of `/api/sessions/<id>`, answered from the sessions it holds (archived or
// not) and 404 `session_not_found` otherwise — routed by the **exact** pathname, beside the
// tree's `/api/sessions` listing and the archive/restore action paths it already served. The
// DoD-15 clause above therefore also sees the started session's screen load; it asserts the
// location and the tree, which are untouched by that.
//
// Amended by feature 013, step 007 (DoD-9): the session screen's ready render mounts the stream,
// which reads `GET /api/sessions/<id>/entries` and `/zone`. `stubWorkspace` gained one branch
// answering both by exact pathname (empty lists for a held session, 404 `session_not_found`
// otherwise), so the `/sessions/1` clause, the tree-click clause and the DoD-15 started-session
// clause all see a loaded stream. "No entries yet." is now the empty record's line, so the two
// 011 step 009 clauses find it rather than get it. One clause is added at the bottom; no other
// route clause changes.
//
// Amended by feature 015, step 008 (DoD-10): the session screen's ready render also mounts the
// "Notes" section, which reads `GET /api/sessions/<id>/memo-chain`. `stubWorkspace` gained one
// branch answering that exact pathname (`{ "levels": [] }` for a held session, 404
// `session_not_found` otherwise), so the `/sessions/1` clause, the tree-click clause, the 013
// clause and the DoD-15 started-session clause all see a loaded section. One clause is added at
// the bottom ("— DoD-7" there is 015 step 008's); no other assertion changes.
//
// Amended by feature 015, step 009 (DoD-7): the character screen's ready render also mounts the
// character-level "Notes" section after the "Sessions" region, which reads
// `GET /api/memos?scope=character&scope_id=<id>`. Both character-screen stubs answer it with
// `{ "memos": [] }`, matched on the exact pathname **and** query string (the pathname
// `/api/memos` alone is shared with the POST and with other levels' listings): the
// `/characters/1` clause's own stub, and `stubWorkspace` (for a character it holds; 404
// `character_not_found` otherwise). `listRequests` and `sessionsListRequests` stay keyed on their
// own exact paths, so no count changes. `/characters/new` mounts no section, so its stub — which
// rejects every other URL — is unchanged; session routes are 015 step 008's. One clause is added
// at the bottom ("— DoD-4" there is 015 step 009's); no other assertion changes.
//
// Amended by feature 016, step 006 (DoD-9, DoD-11, DoD-12): the session screen's ready render is
// now the note wall's layout, and 015's "Notes" region sits inside the complementary "Note wall",
// which is closed (aria-hidden) unless the layout record pins it. `renderApp` takes an optional
// `storage` (default `null`, as before) and passes it to `App`. The 015 step 008 clause at
// `/sessions/1` is amended to find the region inside the wall with `{ hidden: true }` (its title
// now ends with 016 006's "— DoD-11"). A block at the bottom adds DoD-9: with a stored
// `wallPinned: true`, no wall and no "Open notes" at `/`, `/characters/<id>`, `/settings` and
// `/search`, and a pinned wall inside the main region at `/sessions/1` with the shell's `.app`
// grid still holding exactly the nav and the main. No other assertion changes.
//
// Amended by feature 017, step 007 (DoD-8, DoD-9): `/settings` is no longer an empty centre — it
// renders the settings screen (017 D15), which reads `GET /api/me/settings` and the user-level
// notes listing `GET /api/memos?scope=user` on mount. So `EMPTY_CENTRE_ROUTES` **loses its
// `/settings` entry**; `/` and `/search` keep their empty-centre clauses unchanged. `stubWorkspace`
// gained two branches, matched on the exact pathname and query: `GET /api/me/settings` (both
// languages null) and `GET /api/memos?scope=user` (`{ "memos": [] }`), so 016's `/settings` entry
// in `NO_SESSION_ROUTES` sees a well-formed screen and keeps its assertions. Two clauses are added
// at the bottom: `/settings` renders the screen inside the main region with the tree present
// (DoD-8), and the user menu's "Settings" item navigates there in-entry (DoD-9). "— DoD-8" and
// "— DoD-9" there are 017 step 007's. No other assertion changes.
//
// Amended by feature 017, step 011 (DoD-11): the session screen's ready header now ends with the
// "Session configuration" bar (017 D16), which reads `GET /api/sessions/<id>/configuration` and
// `GET /api/models` on mount. `stubWorkspace` gained two branches answering both by exact
// pathname (a seven-key configuration whose captured model is in the one-model list, for a held
// session; 404 `session_not_found` otherwise), so the `/sessions/1` clauses, the tree-click clause
// and the DoD-15 started-session clause all see a loaded bar. One clause is added at the bottom
// ("— DoD-11" there is 017 step 011's); no other assertion changes.
//
// Amended by feature 018, step 009 (DoD-1, DoD-3, DoD-5, DoD-6, DoD-11): `/characters/new` is the
// draft page (018 D6) with no Create, and `/characters/<id>` saves on focus loss with no Save
// (018 D7); its ready body also mounts the "Configuration" block (`GET
// /api/characters/<id>/configuration` + `GET /api/models`) and the page composer "Start a
// session", and runs Notes → Setups → Configuration → Sessions → Start a session (018 D10).
// Consequences:
// - `stubWorkspace` answers the character configuration GET by exact pathname (all five keys
//   null for a held character, 404 `character_not_found` otherwise; `/api/models` was already
//   answered), and its `POST /api/characters/<id>/sessions` answers the started-session wire
//   shape: the eight session keys plus `opening_message` (null, or the eight-key opening
//   message when one was sent). The `/characters/1` clause's own stub answers both reads too;
//   `/characters/new`'s stub (which rejects every other URL) is unchanged — the draft page
//   makes no request;
// - replaced: 009 step 007 DoD-13's "Create button at /characters/new" (→ the Draft badge and no
//   Create, 018 DoD-1), 009 step 008 DoD-8's Create click (→ Name losing focus, 018 DoD-3), 009
//   step 008 DoD-10's Save click (→ Name losing focus, 018 DoD-5), and 015 step 009 DoD-4's
//   "Notes after Sessions" (→ the 018 D10 order, 018 DoD-6). Each amended title ends with the
//   018 "— DoD-N" that amends it. No other assertion changes. 018 step 009's own clauses
//   (DoD-3, DoD-5, DoD-7, DoD-8) are the block at the bottom of this file.
//
// Amended by feature 029, step 005 (DoD-11, DoD-12): `/search` is no longer an empty centre — it
// renders `SearchScreen`, whose own box carries the accessible name "Search query" (029
// context.md literals), so `EMPTY_CENTRE_ROUTES` **loses its `/search` entry** and keeps only
// `/`; the two clauses at the bottom of this file cover `/search` instead. `NO_SESSION_ROUTES`
// **keeps** `/search`: the search screen grows no note wall, and that clause is what proves it.
// `stubWorkspace` needs **no** `/api/search` branch — a blank `q` makes no request (029 decision
// 10) and every render here reaches `/search` without one. Two clauses are added at the bottom:
// the collapsed rail's "Search" button lands on `/search` with the box focused, and `/search`
// with the tree expanded renders the box in the centre (029 U4, D9). A collapse is a stored
// `navCollapsed: true` layout record, WorkspaceShell.test.tsx's own mechanism. No other existing
// assertion is dropped, and `WorkspaceShell.test.tsx` is not amended.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChangeEvent } from "react";
import { App } from "../../src/app/App";
import type { Character } from "../../src/app/charactersApi";
import type { Session } from "../../src/app/sessionsApi";
import type { LayoutStorage } from "../../src/app/workspaceLayout";
import { AppProviders } from "../../src/shared/AppProviders";
import type { CurrentUser } from "../../src/shared/currentUser";

vi.mock("../../src/shared/MarkdownEditor", async () => {
  const { createElement } = await import("react");
  type StubProps = {
    label: string;
    value: string;
    onChange: (markdown: string) => void;
    readOnly?: boolean;
  };
  return {
    MarkdownEditor: (props: StubProps) => {
      const id = `markdown-editor-${props.label.toLowerCase().replace(/\s+/g, "-")}`;
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
type User = ReturnType<typeof userEvent.setup>;

const NAV_NAME = /^workspace navigation$/i;
const NOT_FOUND_TEXT = /page not found/i;

/**
 * The declared routes whose centre is still empty: 009 filled the two character routes, and
 * 011 step 009 filled `/sessions/:id` (D17), which is why that path is no longer listed here —
 * this step's own clauses at the bottom of the file cover it. 017 step 007 filled `/settings`
 * (D15), so it is no longer listed either; its clauses are at the bottom of the file. 029 step
 * 005 filled `/search` with `SearchScreen` (029 U4), which renders the "Search query" box, so
 * that path is no longer listed either; its clauses are at the bottom of the file too. Only `/`
 * is still an empty centre.
 */
const EMPTY_CENTRE_ROUTES = ["/"];

const UNDECLARED_ROUTE = "/nope";

const NEW_CHARACTER_ROUTE = "/characters/new";
const CHARACTER_ROUTE = "/characters/1";
const CHARACTER_PATH = "/api/characters/1";

const CHARACTER = {
  id: "1",
  name: "Thessaly Rune",
  sheet: "A cartographer of places that are not there.",
  archived_at: null,
  created_at: "2026-05-02T11:12:13.000000+00:00",
  updated_at: "2026-05-02T11:12:13.000000+00:00",
};

const USER: CurrentUser = { id: "9007199254740993", username: "zmiraqua", role: "roleplayer" };

// ------------------------------------------- 009 step 008: the tree and its listing
const COLLECTION_PATH = "/api/characters";
const INCLUDE_ARCHIVED_SEARCH = "?include_archived=true";

const SHOW_ARCHIVED_NAME = /^show archived$/i;
const CHARACTERS_LIST_NAME = /^characters$/i;
const NAME_LABEL = /^name$/i;
const CREATE_NAME = /^create$/i;
const SAVE_NAME = /^save$/i;
const ARCHIVE_NAME = /^archive$/i;
const RESTORE_NAME = /^restore$/i;
const ARCHIVED_BADGE = "Archived";

/** Past Number.MAX_SAFE_INTEGER, so a coerced id would show in the location and the href. */
const ID_A = "7250000000000000011";
const CREATED_ID = "9007199254740993";

const TYPED_NAME = "Aria";
const EDITED_NAME = "Bo Kestrel";

const STAMP = "2026-04-10T12:00:00.000000+00:00";
const LATER_STAMP = "2026-04-11T12:00:00.000000+00:00";

const CHAR_A: Character = {
  id: ID_A,
  name: "Corvin Hale",
  sheet: "A duelist who counts his scars.",
  archived_at: null,
  created_at: "2026-02-01T08:15:42.000000+00:00",
  updated_at: "2026-02-01T08:15:42.000000+00:00",
};

// ------------------------------------------- 011 step 006: the tree's sessions listing
/** The workspace sessions listing, answered empty everywhere but DoD-11's own clause. */
const SESSIONS_PATH = "/api/sessions";
const EMPTY_SESSIONS = { sessions: [] };

const SESSION_A_ID = "9007199254740993001";

// ------------------------------------------- 011 step 008: the Sessions section on the screen
/** The section's own listing — a different path than the tree's `/api/sessions`. */
function characterSessionsPath(characterId: string): string {
  return `${COLLECTION_PATH}/${characterId}/sessions`;
}

const CHARACTER_SESSIONS_PATTERN = /^\/api\/characters\/([^/]+)\/sessions$/;
const SESSION_ACTION_PATTERN = /^\/api\/sessions\/([^/]+)\/(archive|restore)$/;

// ------------------------------------------- 011 step 009: the session screen's own read
/** One session by id — the session screen's single source (011 D17), archived or not. */
const SESSION_ITEM_PATTERN = /^\/api\/sessions\/([^/]+)$/;

// ------------------------------------------- 013 step 007: the session stream's two reads
/** `GET /api/sessions/<id>/entries` and `GET /api/sessions/<id>/zone`, anchored both ends. */
const SESSION_STREAM_PATTERN = /^\/api\/sessions\/([^/]+)\/(entries|zone)$/;

// ------------------------------------------- 015 step 008: the session's Notes section read
/** `GET /api/sessions/<id>/memo-chain`, anchored both ends. */
const SESSION_MEMO_CHAIN_PATTERN = /^\/api\/sessions\/([^/]+)\/memo-chain$/;
const NOTES_REGION_NAME = "Notes";
const COMPOSER_NAME = "Composer";

// ------------------------------------------- 016 step 006: the note wall
const WALL_NAME = "Note wall";
const OPEN_NOTES_NAME = "Open notes";
const UNPIN_NOTES_NAME = "Unpin notes";
const LAYOUT_KEY = "rphelper.workspace-layout";
const PINNED_CLASS = "wall-pinned";
const SESSION_ROOT_CLASS = "app-session";

// ------------------------------------------- 015 step 009: the character page's Notes listing
/** One pathname shared by every memo request; listings differ only in the query string. */
const MEMOS_PATH = "/api/memos";
/** `?scope=character&scope_id=<id>`, anchored both ends; the id is captured. */
const CHARACTER_NOTES_SEARCH_PATTERN = /^\?scope=character&scope_id=([^&]+)$/;
const EMPTY_NOTES = { memos: [] };

function characterNotesSearch(characterId: string): string {
  return `?scope=character&scope_id=${characterId}`;
}

// ------------------------------------------- 017 step 007: the settings screen's two reads
const SETTINGS_ROUTE = "/settings";
const USER_SETTINGS_PATH = "/api/me/settings";
const EMPTY_USER_SETTINGS = { rp_language: null, preferred_language: null };
const USER_NOTES_SEARCH = "?scope=user";
const SETTINGS_HEADING = "Settings";
const LANGUAGES_REGION = "Languages";
const YOUR_NOTES_REGION = "Your notes";
const USER_MENU_NAME = /^user menu$/i;
const SETTINGS_ITEM = /^settings$/i;
const RULER_NAME = "Current zone";

// ------------------------------------------- 017 step 011: the session header bar's two reads
/** `GET /api/sessions/<id>/configuration`, anchored both ends. */
const SESSION_CONFIGURATION_PATTERN = /^\/api\/sessions\/([^/]+)\/configuration$/;
const MODELS_PATH = "/api/models";
const CONFIG_BAR_NAME = "Session configuration";
const MODEL_REF = { server_id: "7250000000000000401", model_name: "A" };
const ENABLED_MODELS = [{ server_id: "7250000000000000401", server_name: "S1", model_name: "A" }];
const EMPTY_TEXT_SETTING = { session: null, inherited: null, inherited_level: null, value: null, level: null };
const DEFAULT_TOOL_SETTING = {
  session: null,
  inherited: true,
  inherited_level: "default",
  value: true,
  level: "default",
};
/** Seven keys, nothing overridden, the captured model listed in `ENABLED_MODELS`. */
const USABLE_CONFIGURATION = {
  model: MODEL_REF,
  system_prompt: EMPTY_TEXT_SETTING,
  tool_memo_search: DEFAULT_TOOL_SETTING,
  tool_session_search: DEFAULT_TOOL_SETTING,
  tool_web_search: DEFAULT_TOOL_SETTING,
  rp_language: EMPTY_TEXT_SETTING,
  preferred_language: EMPTY_TEXT_SETTING,
};

// ------------------------------------------- 018 step 009: the character page's configuration read
/** `GET /api/characters/<id>/configuration`, anchored both ends. */
const CHARACTER_CONFIGURATION_PATTERN = /^\/api\/characters\/([^/]+)\/configuration$/;
/** A character configuration with all five keys, nothing set. */
const UNSET_CHARACTER_CONFIGURATION = {
  model: null,
  system_prompt: null,
  tool_memo_search: null,
  tool_session_search: null,
  tool_web_search: null,
};
/** The opening message id the started-session answer carries when one was sent. */
const OPENING_MESSAGE_ID = "9007199254740997";

const SESSION_NOT_FOUND_TEXT = "Session not found";
const NO_ENTRIES_TEXT = "No entries yet.";
const START_LABEL_HEADING = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/;

/** DoD-11's own route: `/sessions/1`, the entry `EMPTY_CENTRE_ROUTES` no longer lists. */
const SESSION_ONE_ROUTE = "/sessions/1";
const SESSION_ONE_ID = "1";

const SESSIONS_REGION = /^sessions$/i;
const START_SESSION_NAME = /^start session$/i;
const ROW_TRIGGER_NAME = /^actions for /i;
const ARCHIVE_ITEM = /^archive$/i;

/** Past Number.MAX_SAFE_INTEGER, so a coerced id would show in the location and the href. */
const STARTED_SESSION_ID = "9007199254740995";
const STARTED_STAMP = "2026-06-01T12:00:00.000000+00:00";

/** 011 step 009: the session behind `/sessions/1`, under the character the tree shows. */
const SESSION_ONE: Session = {
  id: SESSION_ONE_ID,
  character_id: ID_A,
  setup_id: null,
  setup_name: null,
  archived_at: null,
  last_used_at: "2026-05-09T08:00:00.000000+00:00",
  created_at: "2026-05-09T08:00:00.000000+00:00",
  updated_at: "2026-05-09T08:00:00.000000+00:00",
};

const SESSION_A: Session = {
  id: SESSION_A_ID,
  character_id: ID_A,
  setup_id: null,
  setup_name: null,
  archived_at: null,
  last_used_at: "2026-05-10T09:00:00.000000+00:00",
  created_at: "2026-05-10T09:00:00.000000+00:00",
  updated_at: "2026-05-10T09:00:00.000000+00:00",
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="probe-location">{location.pathname}</output>;
}

function renderApp(initialPath: string, storage: LayoutStorage | null = null) {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={[initialPath]}>
        <App user={USER} storage={storage} />
        <LocationProbe />
      </MemoryRouter>
    </AppProviders>,
  );
}

function currentPath(): string {
  return screen.getByTestId("probe-location").textContent ?? "";
}

function navElement(): HTMLElement {
  return screen.getByRole("navigation", { name: NAV_NAME });
}

function mainElement(): HTMLElement {
  return screen.getByRole("main");
}

function mainText(): string {
  return (mainElement().textContent ?? "").trim();
}

function stubFetch(impl: FetchFn) {
  const mock = vi.fn<FetchFn>(impl);
  vi.stubGlobal("fetch", mock);
  return mock;
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function requestPath(input: RequestInfo | URL): string {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost").pathname;
}

async function flush(rounds = 6): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => setImmediate(resolve));
    });
  }
}

// ------------------------------------------- 009 step 008: the in-memory characters backend
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

function notFoundResponse(): Response {
  return jsonResponse({ error: { code: "character_not_found", message: "", detail: {} } }, 404);
}

// ------------------------------------------- 010 step 006: the Setups section's listing
/** The section's own URL, a different path than the character's (010 wire contract). */
function setupsPath(characterId: string): string {
  return `${COLLECTION_PATH}/${characterId}/setups`;
}

const SETUPS_PATTERN = /^\/api\/characters\/([^/]+)\/setups$/;
const EMPTY_SETUPS = { setups: [] };

/**
 * The wire contract of `/api/characters` over an in-memory row set (009 context.md), with
 * every request recorded in order. Only the listing honours the include-archived flag; a
 * mutation answers the single row it changed.
 */
function stubWorkspace(rows: Character[], sessions: Session[] = []) {
  const store = new Map<string, Character>(rows.map((row) => [row.id, row]));
  /** 011 step 008: the sessions the wire holds, mutated by start / archive / restore. */
  const sessionOrder: Session[] = [...sessions];
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>(async (input, init) => {
    const url = requestUrl(input);
    const method = requestMethod(input, init);
    const body = parseBody(init);
    calls.push({ method, path: url.pathname, search: url.search, body });

    // 011 step 006: every route mounts the tree, which loads the workspace sessions on mount.
    // Matched on the exact pathname — the fallback 404 would otherwise drive the tree into its
    // failed sessions state. The tree only ever asks for the working list.
    if (url.pathname === SESSIONS_PATH && method === "GET") {
      return jsonResponse({ sessions: sessionOrder.filter((row) => row.archived_at === null) }, 200);
    }

    // 017 step 007: `/settings` renders the settings screen, which reads the user's settings.
    // Matched on the exact pathname and an empty query — `/api/me` shares the prefix.
    if (url.pathname === USER_SETTINGS_PATH && url.search === "" && method === "GET") {
      return jsonResponse(EMPTY_USER_SETTINGS, 200);
    }
    // 017 step 007: the settings screen's "Your notes" lists the user-level notes. Matched on the
    // exact pathname and query string, answered empty.
    if (url.pathname === MEMOS_PATH && url.search === USER_NOTES_SEARCH && method === "GET") {
      return jsonResponse(EMPTY_NOTES, 200);
    }

    // 015 step 009: the character screen's Notes section lists that character's notes. Matched
    // on the exact pathname and query string; answered empty for a held character, the
    // backend's own 404 code otherwise.
    if (url.pathname === MEMOS_PATH && method === "GET") {
      const notesFor = CHARACTER_NOTES_SEARCH_PATTERN.exec(url.search);
      if (notesFor !== null && store.has(notesFor[1])) return jsonResponse(EMPTY_NOTES, 200);
      return notFoundResponse();
    }

    // 011 step 008: the character screen's Sessions section lists, starts, archives and
    // restores. All four are matched on the exact pathname, beside the tree's own listing.
    const characterSessions = CHARACTER_SESSIONS_PATTERN.exec(url.pathname);
    if (characterSessions !== null) {
      const characterId = characterSessions[1];
      if (!store.has(characterId)) return notFoundResponse();
      if (method === "GET") {
        const includeArchived = url.search === INCLUDE_ARCHIVED_SEARCH;
        const listed = sessionOrder.filter(
          (row) => row.character_id === characterId && (includeArchived || row.archived_at === null),
        );
        return jsonResponse({ sessions: listed }, 200);
      }
      if (method === "POST") {
        const sent = (body ?? {}) as { setup_id?: string | null; opening_message?: string | null };
        const started: Session = {
          id: STARTED_SESSION_ID,
          character_id: characterId,
          setup_id: sent.setup_id ?? null,
          setup_name: null,
          archived_at: null,
          last_used_at: STARTED_STAMP,
          created_at: STARTED_STAMP,
          updated_at: STARTED_STAMP,
        };
        sessionOrder.unshift(started);
        // 018 step 009: the route answers the started session — the eight session keys plus
        // `opening_message`, null exactly when none was sent (018 context.md "Wire contract").
        const opening =
          typeof sent.opening_message === "string"
            ? {
                id: OPENING_MESSAGE_ID,
                session_id: STARTED_SESSION_ID,
                role: "user",
                kind: null,
                text: sent.opening_message,
                settled_at: null,
                created_at: STARTED_STAMP,
                updated_at: STARTED_STAMP,
              }
            : null;
        return jsonResponse({ ...started, opening_message: opening }, 201);
      }
    }

    // 018 step 009: the character page's "Configuration" block reads the character's own
    // configuration. Matched on the exact pathname; nothing set for a held character, the
    // backend's own 404 code otherwise. (`GET /api/models` is answered below, as before.)
    const characterConfiguration = CHARACTER_CONFIGURATION_PATTERN.exec(url.pathname);
    if (characterConfiguration !== null && method === "GET") {
      if (!store.has(characterConfiguration[1])) return notFoundResponse();
      return jsonResponse(UNSET_CHARACTER_CONFIGURATION, 200);
    }

    // 011 step 009: the session screen reads its one session by id, archived or not (D17).
    // Matched on the exact pathname, so the action paths below and the listing above are
    // unaffected; an unknown id answers the backend's own 404 code.
    const sessionItem = SESSION_ITEM_PATTERN.exec(url.pathname);
    if (sessionItem !== null && method === "GET") {
      const row = sessionOrder.find((candidate) => candidate.id === sessionItem[1]);
      if (row === undefined) {
        return jsonResponse({ error: { code: "session_not_found", message: "", detail: {} } }, 404);
      }
      return jsonResponse(row, 200);
    }

    // 013 step 007: the session screen's ready render mounts the stream, which reads that
    // session's entries and zone. Matched on the exact pathname; answered empty for a held
    // session, the backend's own 404 code otherwise.
    const sessionStream = SESSION_STREAM_PATTERN.exec(url.pathname);
    if (sessionStream !== null && method === "GET") {
      if (!sessionOrder.some((candidate) => candidate.id === sessionStream[1])) {
        return jsonResponse({ error: { code: "session_not_found", message: "", detail: {} } }, 404);
      }
      return jsonResponse(sessionStream[2] === "entries" ? { entries: [] } : { messages: [] }, 200);
    }

    // 015 step 008: the session screen's ready render mounts the Notes section, which reads that
    // session's memo chain. Matched on the exact pathname; answered with no levels for a held
    // session, the backend's own 404 code otherwise.
    const sessionChain = SESSION_MEMO_CHAIN_PATTERN.exec(url.pathname);
    if (sessionChain !== null && method === "GET") {
      if (!sessionOrder.some((candidate) => candidate.id === sessionChain[1])) {
        return jsonResponse({ error: { code: "session_not_found", message: "", detail: {} } }, 404);
      }
      return jsonResponse({ levels: [] }, 200);
    }

    // 017 step 011: the session screen's ready header mounts the "Session configuration" bar,
    // which reads that session's configuration and the enabled models. Matched on the exact
    // pathname; the configuration is answered for a held session (captured model listed in the
    // models answer), the backend's own 404 code otherwise.
    const sessionConfiguration = SESSION_CONFIGURATION_PATTERN.exec(url.pathname);
    if (sessionConfiguration !== null && method === "GET") {
      if (!sessionOrder.some((candidate) => candidate.id === sessionConfiguration[1])) {
        return jsonResponse({ error: { code: "session_not_found", message: "", detail: {} } }, 404);
      }
      return jsonResponse(USABLE_CONFIGURATION, 200);
    }
    if (url.pathname === MODELS_PATH && url.search === "" && method === "GET") {
      return jsonResponse({ models: ENABLED_MODELS }, 200);
    }

    const sessionAction = SESSION_ACTION_PATTERN.exec(url.pathname);
    if (sessionAction !== null && method === "POST") {
      const index = sessionOrder.findIndex((row) => row.id === sessionAction[1]);
      if (index < 0) {
        return jsonResponse({ error: { code: "session_not_found", message: "", detail: {} } }, 404);
      }
      const next: Session = {
        ...sessionOrder[index],
        archived_at: sessionAction[2] === "archive" ? LATER_STAMP : null,
        updated_at: LATER_STAMP,
      };
      sessionOrder[index] = next;
      return jsonResponse(next, 200);
    }

    if (url.pathname === COLLECTION_PATH && method === "GET") {
      const includeArchived = url.search === INCLUDE_ARCHIVED_SEARCH;
      const listed = Array.from(store.values()).filter(
        (row) => includeArchived || row.archived_at === null,
      );
      return jsonResponse({ characters: listed }, 200);
    }
    if (url.pathname === COLLECTION_PATH && method === "POST") {
      const sent = (body ?? {}) as { name?: string; sheet?: string };
      const created: Character = {
        id: CREATED_ID,
        name: sent.name ?? "",
        sheet: sent.sheet ?? "",
        archived_at: null,
        created_at: STAMP,
        updated_at: STAMP,
      };
      store.set(created.id, created);
      return jsonResponse(created, 201);
    }

    // 010 step 006: a loaded character's screen mounts the Setups section, which lists that
    // character's setups. Answered empty, so no setup row renders anywhere in this file.
    const setupsMatch = SETUPS_PATTERN.exec(url.pathname);
    if (setupsMatch !== null && method === "GET") {
      if (!store.has(setupsMatch[1])) return notFoundResponse();
      return jsonResponse(EMPTY_SETUPS, 200);
    }

    const match = /^\/api\/characters\/([^/]+)(\/archive|\/restore)?$/.exec(url.pathname);
    if (match !== null) {
      const row = store.get(match[1]);
      if (row === undefined) return notFoundResponse();
      const action = match[2];
      if (action === "/archive" && method === "POST") {
        const next: Character = { ...row, archived_at: LATER_STAMP, updated_at: LATER_STAMP };
        store.set(row.id, next);
        return jsonResponse(next, 200);
      }
      if (action === "/restore" && method === "POST") {
        const next: Character = { ...row, archived_at: null, updated_at: LATER_STAMP };
        store.set(row.id, next);
        return jsonResponse(next, 200);
      }
      if (action === undefined && method === "GET") return jsonResponse(row, 200);
      if (action === undefined && method === "PATCH") {
        const patch = (body ?? {}) as { name?: string; sheet?: string };
        const next: Character = {
          ...row,
          name: patch.name ?? row.name,
          sheet: patch.sheet ?? row.sheet,
          updated_at: LATER_STAMP,
        };
        store.set(row.id, next);
        return jsonResponse(next, 200);
      }
    }
    return notFoundResponse();
  });
  vi.stubGlobal("fetch", mock);
  return { calls, store };
}

function listRequests(calls: Seen[]): Seen[] {
  return calls.filter((call) => call.method === "GET" && call.path === COLLECTION_PATH);
}

function newUser(): User {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

// ------------------------------------------- 009 step 008: the tree, inside the nav column
/** The character level when it is named, the nav column otherwise: the tree's rows live here. */
function treeRowScope(): HTMLElement {
  const nav = within(navElement());
  return (
    nav.queryByRole("list", { name: CHARACTERS_LIST_NAME }) ??
    nav.queryByRole("navigation", { name: CHARACTERS_LIST_NAME }) ??
    navElement()
  );
}

function queryTreeRow(name: string): HTMLElement | null {
  return (
    within(treeRowScope())
      .queryAllByRole("link")
      .find((link) => (link.textContent ?? "").includes(name)) ?? null
  );
}

function treeRow(name: string): HTMLElement {
  const row = queryTreeRow(name);
  if (row === null) throw new Error(`no tree row for "${name}"`);
  return row;
}

/** A row's whole block: the link, or the list item it sits in when the badge is a sibling. */
function treeRowBlock(name: string): HTMLElement {
  const row = treeRow(name);
  return row.closest("li") ?? row;
}

function archivedSwitch(): HTMLElement {
  const nav = within(navElement());
  const asSwitch = nav.queryByRole("switch", { name: SHOW_ARCHIVED_NAME });
  if (asSwitch !== null) return asSwitch;
  return nav.getByRole("checkbox", { name: SHOW_ARCHIVED_NAME });
}

function screenControl(name: RegExp): HTMLElement {
  return within(mainElement()).getByRole("button", { name });
}

function screenNameField(): HTMLElement {
  return within(mainElement()).getByRole("textbox", { name: NAME_LABEL });
}

/** 018 step 009: the screen's Persona editor (the stubbed labelled textarea). */
function screenPersonaField(): HTMLElement {
  return within(mainElement()).getByRole("textbox", { name: /^persona$/i });
}

// ---------------------------------------------------------------------------
// 009 step 008: every route mounts the tree, so each clause below stubs the listing.
describe("every declared route is the same shell around an empty centre (D5)", () => {
  it.each(EMPTY_CENTRE_ROUTES)("renders the shell at %s — DoD-10", async (path) => {
    stubWorkspace([CHAR_A]);
    renderApp(path);
    await flush();

    expect(navElement()).toBeInTheDocument();
    expect(mainElement()).toBeInTheDocument();
  });

  it.each(EMPTY_CENTRE_ROUTES)("renders no centre content at %s — DoD-10", async (path) => {
    stubWorkspace([CHAR_A]);
    renderApp(path);
    await flush();

    expect(mainText()).toBe("");
    expect(within(mainElement()).queryByText(NOT_FOUND_TEXT)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("an undeclared path is a 404 inside the same shell (D5)", () => {
  it("renders the shell with Page not found inside the main region — DoD-11", async () => {
    stubWorkspace([CHAR_A]);
    renderApp(UNDECLARED_ROUTE);
    await flush();

    expect(navElement()).toBeInTheDocument();
    expect(within(mainElement()).getByText(NOT_FOUND_TEXT)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Feature 009, step 007 — the two character routes now render the character screen.
describe("the character routes render the character screen in the same shell (009 D1, D11)", () => {
  // 009 step 008: the tree's listing is the only request new mode makes.
  it("(009 007 DoD-13, amended: the draft page, no Create) renders the New character screen in the main region at /characters/new — DoD-1", async () => {
    stubFetch((input) => {
      const path = requestPath(input);
      if (path === COLLECTION_PATH) return Promise.resolve(jsonResponse({ characters: [] }, 200));
      // 011 step 006: the shell's tree loads the workspace sessions on every route.
      if (path === SESSIONS_PATH) return Promise.resolve(jsonResponse(EMPTY_SESSIONS, 200));
      return Promise.reject(new Error("no other request is expected in new mode"));
    });
    renderApp(NEW_CHARACTER_ROUTE);
    await flush();

    expect(navElement()).toBeInTheDocument();
    const main = within(mainElement());
    expect(main.getByRole("heading", { name: /^new character$/i })).toBeInTheDocument();
    expect(main.getByRole("textbox", { name: /^name$/i })).toBeInTheDocument();
    expect(main.getByRole("textbox", { name: /^persona$/i })).toBeInTheDocument();
    // 018 step 009 (D6): the draft marker replaces the Create button.
    expect(main.getByText("Draft")).toBeInTheDocument();
    expect(main.getByText("Nothing is saved until you enter a name.")).toBeInTheDocument();
    expect(main.queryByRole("button", { name: /^create$/i })).toBeNull();
  });

  it("renders the requested character in the main region at /characters/1 — DoD-13", async () => {
    stubFetch((input) => {
      const path = requestPath(input);
      // 015 step 009: the ready screen mounts the Notes section, which lists the character's
      // notes — matched on the exact pathname and query string.
      if (path === MEMOS_PATH && requestUrl(input).search === characterNotesSearch(CHARACTER.id)) {
        return Promise.resolve(jsonResponse(EMPTY_NOTES, 200));
      }
      if (path === CHARACTER_PATH) return Promise.resolve(jsonResponse(CHARACTER, 200));
      // 009 step 008: the shell's tree lists the characters on every route.
      if (path === COLLECTION_PATH) {
        return Promise.resolve(jsonResponse({ characters: [CHARACTER] }, 200));
      }
      // 010 step 006: the ready screen mounts the Setups section, which lists its setups.
      // 011 step 008: the Sessions section's Select asks the same path a second time.
      if (path === setupsPath(CHARACTER.id)) {
        return Promise.resolve(jsonResponse(EMPTY_SETUPS, 200));
      }
      // 011 step 008: the ready screen mounts the Sessions section, which lists its sessions.
      if (path === characterSessionsPath(CHARACTER.id)) {
        return Promise.resolve(jsonResponse(EMPTY_SESSIONS, 200));
      }
      // 018 step 009 (DoD-11): the ready screen mounts the Configuration block, which reads the
      // character's configuration and the enabled models — both by exact pathname.
      if (path === `${CHARACTER_PATH}/configuration`) {
        return Promise.resolve(jsonResponse(UNSET_CHARACTER_CONFIGURATION, 200));
      }
      if (path === MODELS_PATH) {
        return Promise.resolve(jsonResponse({ models: ENABLED_MODELS }, 200));
      }
      // 011 step 006: the shell's tree loads the workspace sessions on every route.
      if (path === SESSIONS_PATH) {
        return Promise.resolve(jsonResponse(EMPTY_SESSIONS, 200));
      }
      return Promise.resolve(
        jsonResponse({ error: { code: "character_not_found", message: "", detail: {} } }, 404),
      );
    });
    renderApp(CHARACTER_ROUTE);
    await flush();

    expect(navElement()).toBeInTheDocument();
    const main = within(mainElement());
    expect(main.getByRole("heading", { name: CHARACTER.name })).toBeInTheDocument();
    expect(main.getByRole("textbox", { name: /^name$/i })).toHaveValue(CHARACTER.name);
    expect(main.getByRole("textbox", { name: /^persona$/i })).toHaveValue(CHARACTER.sheet);
  });
});

// ---------------------------------------------------------------------------
// Feature 009, step 008 — the screen and the tree share the one workspace state (D11), so a
// create, an archive/restore or a save shows in the tree with no second listing request.
describe("creating a character shows it in the tree without refetching the list (US-020.AC-2, D11)", () => {
  it("(009 008 DoD-8, amended: Name losing focus creates) lands on the created id and marks that row current, with no list request after the create — DoD-3", async () => {
    const user = newUser();
    const { calls } = stubWorkspace([]);
    renderApp(NEW_CHARACTER_ROUTE);
    await flush();
    expect(listRequests(calls)).toHaveLength(1);

    await user.type(screenNameField(), TYPED_NAME);
    // 018 step 009 (D6): no Create button; the create fires when Name loses focus.
    await user.tab();
    await flush();

    expect(currentPath()).toBe(`/characters/${CREATED_ID}`);
    expect(treeRow(TYPED_NAME)).toHaveAttribute("aria-current", "page");

    const createIndex = calls.findIndex(
      (call) => call.method === "POST" && call.path === COLLECTION_PATH,
    );
    expect(createIndex).toBeGreaterThanOrEqual(0);
    expect(listRequests(calls.slice(createIndex + 1))).toEqual([]);
    expect(listRequests(calls)).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
describe("archiving and restoring from the screen move the row in the tree (US-086.AC-1, US-086.AC-2)", () => {
  it("Archive drops the row, Show archived brings it back badged, Restore unbadges it — DoD-9", async () => {
    const user = newUser();
    stubWorkspace([CHAR_A]);
    renderApp(`/characters/${ID_A}`);
    await flush();
    expect(queryTreeRow(CHAR_A.name)).not.toBeNull();

    await user.click(screenControl(ARCHIVE_NAME));
    await flush();
    expect(queryTreeRow(CHAR_A.name)).toBeNull();

    await user.click(archivedSwitch());
    await flush();
    expect(queryTreeRow(CHAR_A.name)).not.toBeNull();
    expect(within(treeRowBlock(CHAR_A.name)).getByText(ARCHIVED_BADGE)).toBeInTheDocument();

    await user.click(screenControl(RESTORE_NAME));
    await flush();
    expect(within(treeRowBlock(CHAR_A.name)).queryByText(ARCHIVED_BADGE)).toBeNull();

    await user.click(archivedSwitch());
    await flush();
    expect(queryTreeRow(CHAR_A.name)).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("saving a new name shows it in the tree (US-021.AC-1)", () => {
  it("(009 008 DoD-10, amended: Name losing focus saves) the tree row carries the saved name — DoD-5", async () => {
    const user = newUser();
    stubWorkspace([CHAR_A]);
    renderApp(`/characters/${ID_A}`);
    await flush();
    expect(queryTreeRow(CHAR_A.name)).not.toBeNull();

    await user.clear(screenNameField());
    await user.type(screenNameField(), EDITED_NAME);
    // 018 step 009 (D7): no Save button; the name saves when the field loses focus.
    await user.tab();
    await flush();

    expect(queryTreeRow(EDITED_NAME)).not.toBeNull();
    expect(queryTreeRow(CHAR_A.name)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Feature 011, step 006 — `App` creates the one workspace `SessionsState` and the tree shows
// its rows under the characters (D15, D16).
/** Session rows in the nav column, by their `/sessions/<id>` href. */
function navSessionHrefs(): string[] {
  return within(navElement())
    .queryAllByRole("link")
    .map((link) => link.getAttribute("href") ?? "")
    .filter((value) => value.startsWith("/sessions/"));
}

describe("the app's tree shows the workspace sessions under their characters (011 D15, D16)", () => {
  it("at / the stubbed session renders as a row under its character — DoD-11", async () => {
    const { calls } = stubWorkspace([CHAR_A], [SESSION_A]);
    renderApp("/");
    await flush();

    expect(queryTreeRow(CHAR_A.name)).not.toBeNull();
    expect(navSessionHrefs()).toEqual([`/sessions/${SESSION_A_ID}`]);
    // One characters listing and one sessions listing: the two effects are separate.
    expect(listRequests(calls)).toHaveLength(1);
    expect(
      calls.filter((call) => call.method === "GET" && call.path === SESSIONS_PATH),
    ).toHaveLength(1);
  });

  it("the centre at / stays empty while the tree carries the session rows — DoD-11", async () => {
    stubWorkspace([CHAR_A], [SESSION_A]);
    renderApp("/");
    await flush();

    expect(mainText()).toBe("");
    expect(navSessionHrefs()).toEqual([`/sessions/${SESSION_A_ID}`]);
  });
});

// ---------------------------------------------------------------------------
// Feature 011, step 008 — the character screen's Sessions section and the tree share the one
// workspace `SessionsState` (D15), so a start or an archive shows in the tree with no second
// listing request. The section's own behaviour is `SessionsSection.test.tsx`'s; what this block
// asserts is the wiring `App` provides.
/** The section on the character screen — a region named "Sessions" (011 D1). */
function sessionsRegion(): HTMLElement {
  return screen.getByRole("region", { name: SESSIONS_REGION });
}

function startSessionButton(): HTMLElement {
  return within(sessionsRegion()).getByRole("button", { name: START_SESSION_NAME });
}

/** The nested session list under one character in the tree (011 step 006). */
function treeSessionsListFor(characterName: string): HTMLElement {
  return within(navElement()).getByRole("list", {
    name: new RegExp(`^sessions of ${characterName}$`, "i"),
  });
}

function queryTreeSessionRow(sessionId: string): HTMLElement | null {
  return (
    within(navElement())
      .queryAllByRole("link")
      .find((link) => link.getAttribute("href") === `/sessions/${sessionId}`) ?? null
  );
}

/** One of the section's rows, located by its link's href (008.context.md). */
function sectionRow(sessionId: string): HTMLElement {
  const link = within(sessionsRegion())
    .getAllByRole("link")
    .find((candidate) => candidate.getAttribute("href") === `/sessions/${sessionId}`);
  if (link === undefined) throw new Error(`no section row for /sessions/${sessionId}`);
  const row = link.closest("tr");
  if (row === null) throw new Error(`the section row for /sessions/${sessionId} is not a table row`);
  return row;
}

/** Every workspace sessions listing — the tree's own `GET /api/sessions`, by exact path. */
function sessionsListRequests(calls: Seen[]): Seen[] {
  return calls.filter((call) => call.method === "GET" && call.path === SESSIONS_PATH);
}

describe("starting a session from the character screen lands on it and shows it in the tree (US-026.AC-1, D15)", () => {
  it("navigates to /sessions/<new id>, marks that tree row current and issues no second GET /api/sessions — DoD-15", async () => {
    const user = newUser();
    const { calls } = stubWorkspace([CHAR_A]);
    renderApp(`/characters/${ID_A}`);
    await flush();
    expect(sessionsListRequests(calls)).toHaveLength(1);

    await user.click(startSessionButton());
    await flush();

    expect(currentPath()).toBe(`/sessions/${STARTED_SESSION_ID}`);
    const started = queryTreeSessionRow(STARTED_SESSION_ID);
    expect(started).not.toBeNull();
    expect(started).toHaveAttribute("aria-current", "page");
    expect(
      within(treeSessionsListFor(CHAR_A.name))
        .queryAllByRole("link")
        .map((link) => link.getAttribute("href") ?? ""),
    ).toEqual([`/sessions/${STARTED_SESSION_ID}`]);

    const postIndex = calls.findIndex(
      (call) => call.method === "POST" && call.path === characterSessionsPath(ID_A),
    );
    expect(postIndex).toBeGreaterThanOrEqual(0);
    expect(sessionsListRequests(calls.slice(postIndex + 1))).toEqual([]);
    expect(sessionsListRequests(calls)).toHaveLength(1);
  });
});

describe("archiving a session from the section removes its row from the tree (US-027.AC-1, D15)", () => {
  it("the archived row is gone from the tree with no second GET /api/sessions — DoD-15", async () => {
    const user = newUser();
    const { calls } = stubWorkspace([CHAR_A], [SESSION_A]);
    renderApp(`/characters/${ID_A}`);
    await flush();
    expect(queryTreeSessionRow(SESSION_A_ID)).not.toBeNull();

    await user.click(within(sectionRow(SESSION_A_ID)).getByRole("button", { name: ROW_TRIGGER_NAME }));
    await user.click(await screen.findByRole("menuitem", { name: ARCHIVE_ITEM }));
    await flush();

    expect(
      calls.filter(
        (call) => call.method === "POST" && call.path === `/api/sessions/${SESSION_A_ID}/archive`,
      ),
    ).toHaveLength(1);
    expect(queryTreeSessionRow(SESSION_A_ID)).toBeNull();
    expect(sessionsListRequests(calls)).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// Feature 011, step 009 — `/sessions/:id` is a real centre now (D17): the session screen, keyed
// by the id, inside the same shell. The screen's own behaviour is SessionScreen.test.tsx's; what
// these two clauses assert is the route `App` declares and the tree's way into it. The empty
// centres (`/`, `/settings`, `/search`) and the `*` clause are the untouched block at the top.
/** Every read of one session by id — the screen's own request, by exact path. */
function sessionItemRequests(calls: Seen[], sessionId: string): Seen[] {
  return calls.filter((call) => call.method === "GET" && call.path === `/api/sessions/${sessionId}`);
}

describe("the session route renders the session screen in the same shell (D17, UC-024)", () => {
  it("at /sessions/1 the main region holds that session's screen — DoD-11", async () => {
    const { calls } = stubWorkspace([CHAR_A], [SESSION_ONE]);
    renderApp(SESSION_ONE_ROUTE);
    await flush();

    expect(navElement()).toBeInTheDocument();
    const main = within(mainElement());
    expect(main.getByRole("link", { name: CHAR_A.name })).toHaveAttribute(
      "href",
      `/characters/${ID_A}`,
    );
    expect(main.getByRole("heading", { name: START_LABEL_HEADING })).toBeInTheDocument();
    expect(await main.findByText(NO_ENTRIES_TEXT)).toBeInTheDocument();
    expect(main.queryByText(SESSION_NOT_FOUND_TEXT)).toBeNull();
    expect(main.queryByText(NOT_FOUND_TEXT)).toBeNull();
    expect(sessionItemRequests(calls, SESSION_ONE_ID)).toHaveLength(1);
  });

  it("from / a click on a session row in the tree opens that session's screen — DoD-11", async () => {
    const user = newUser();
    const { calls } = stubWorkspace([CHAR_A], [SESSION_A]);
    renderApp("/");
    await flush();
    expect(mainText()).toBe("");

    const row = queryTreeSessionRow(SESSION_A_ID);
    expect(row).not.toBeNull();
    await user.click(row as HTMLElement);
    await flush();

    expect(currentPath()).toBe(`/sessions/${SESSION_A_ID}`);
    expect(sessionItemRequests(calls, SESSION_A_ID)).toHaveLength(1);
    const main = within(mainElement());
    expect(await main.findByText(NO_ENTRIES_TEXT)).toBeInTheDocument();
    expect(main.getByRole("link", { name: CHAR_A.name })).toHaveAttribute(
      "href",
      `/characters/${ID_A}`,
    );
  });
});

// ---------------------------------------------------------------------------
// Feature 013, step 007 — the session screen now carries its stream (013 D13). `stubWorkspace`
// answers `GET /api/sessions/<id>/entries` and `/zone` by exact pathname (empty for a held
// session), so the two 011 step 009 clauses above keep their assertions; this clause is the
// route-level proof that the stream sits in the main region. "— DoD-9" is 013 step 007's.
describe("013 step 007 — /sessions/1 renders the session screen with its stream", () => {
  it("at /sessions/1 the main region holds the header and the stream, from the session, entries and zone reads — DoD-9", async () => {
    const { calls } = stubWorkspace([CHAR_A], [SESSION_ONE]);
    renderApp(SESSION_ONE_ROUTE);
    await flush();

    expect(navElement()).toBeInTheDocument();
    const main = within(mainElement());
    expect(main.getByRole("link", { name: CHAR_A.name })).toHaveAttribute(
      "href",
      `/characters/${ID_A}`,
    );
    expect(main.getByRole("heading", { name: START_LABEL_HEADING })).toBeInTheDocument();
    expect(await main.findByText(NO_ENTRIES_TEXT)).toBeInTheDocument();
    expect(main.getByRole("separator", { name: RULER_NAME })).toBeInTheDocument();
    expect(main.getByRole("textbox", { name: COMPOSER_NAME })).toBeInTheDocument();
    expect(main.getByRole("button", { name: "Send" })).toBeInTheDocument();
    expect(main.getByRole("button", { name: "Settle" })).toBeInTheDocument();
    expect(main.queryByText(SESSION_NOT_FOUND_TEXT)).toBeNull();
    expect(main.queryByText(NOT_FOUND_TEXT)).toBeNull();

    expect(sessionItemRequests(calls, SESSION_ONE_ID)).toHaveLength(1);
    expect(
      calls.filter((call) => call.method === "GET" && call.path === `/api/sessions/${SESSION_ONE_ID}/entries`),
    ).toHaveLength(1);
    expect(
      calls.filter((call) => call.method === "GET" && call.path === `/api/sessions/${SESSION_ONE_ID}/zone`),
    ).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// Feature 015, step 008 — the session screen's ready render carries the "Notes" section (D1).
// The section's own behaviour is MemoChainSection.test.tsx's; this clause is the route-level
// proof that it sits in the main region at `/sessions/1`. "— DoD-7" is 015 step 008's.
describe("015 step 008 — /sessions/1 renders the Notes section in the main region", () => {
  it("(015 008 DoD-7, amended) at /sessions/1 the main region holds the Note wall holding the Notes region after the session header, from one memo-chain read — DoD-11", async () => {
    const { calls } = stubWorkspace([CHAR_A], [SESSION_ONE]);
    renderApp(SESSION_ONE_ROUTE);
    await flush();

    const main = within(mainElement());
    // The closed wall carries aria-hidden="true", for which the installed dom-accessibility-api
    // computes an empty name — so find it unnamed and check its aria-label.
    const wall = await waitFor(() => {
      const walls = main
        .queryAllByRole("complementary", { hidden: true })
        .filter((el) => el.getAttribute("aria-label") === WALL_NAME);
      expect(walls).toHaveLength(1);
      return walls[0];
    });
    expect(wall.getAttribute("aria-label")).toBe(WALL_NAME);
    const notes = within(wall).getByRole("region", { name: NOTES_REGION_NAME, hidden: true });
    expect(
      within(notes).getByRole("heading", { name: NOTES_REGION_NAME, hidden: true }),
    ).toBeInTheDocument();
    const header = main.getByRole("heading", { name: START_LABEL_HEADING });
    expect(header.compareDocumentPosition(notes) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
    expect(
      calls.filter(
        (call) => call.method === "GET" && call.path === `/api/sessions/${SESSION_ONE_ID}/memo-chain`,
      ),
    ).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// Feature 015, step 009 — the character screen's ready render carries the character-level
// "Notes" section after the "Sessions" region (D1). The section's own behaviour is
// CharacterNotesSection.test.tsx's and its place on the screen CharacterScreen.test.tsx's; this
// clause is the route-level proof inside the shell. "— DoD-4" is 015 step 009's.
describe("015 step 009 — /characters/<id> renders the Notes section (order amended by 018 D10)", () => {
  it("(015 009 DoD-4, amended: Notes now precedes Setups, Configuration, Sessions and Start a session) the main region holds the Notes region, from one character notes listing — DoD-6", async () => {
    const { calls } = stubWorkspace([CHAR_A]);
    renderApp(`/characters/${ID_A}`);
    await flush();

    const main = within(mainElement());
    const notes = await main.findByRole("region", { name: NOTES_REGION_NAME });
    expect(within(notes).getByRole("heading", { name: NOTES_REGION_NAME })).toBeInTheDocument();
    // 018 D10: Notes → Setups → Configuration → Sessions → Start a session.
    const ordered = [
      notes,
      main.getByRole("region", { name: "Setups" }),
      main.getByRole("region", { name: "Configuration" }),
      sessionsRegion(),
      main.getByRole("region", { name: "Start a session" }),
    ];
    for (let index = 0; index + 1 < ordered.length; index += 1) {
      expect(
        ordered[index].compareDocumentPosition(ordered[index + 1]) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).not.toBe(0);
    }
    const listings = calls.filter((call) => call.method === "GET" && call.path === MEMOS_PATH);
    expect(listings).toHaveLength(1);
    expect(listings[0].search).toBe(characterNotesSearch(ID_A));
  });
});

// ---------------------------------------------------------------------------
// Feature 016, step 006 — the wall exists only on the ready session screen (US-095.AC-1,
// US-094.AC-2, D1). `App` is given an in-memory layout storage holding `wallPinned: true`.
// "— DoD-9" here is 016 step 006's.
type GetItem = (key: string) => string | null;
type SetItem = (key: string, value: string) => void;

/** A file-local in-memory `LayoutStorage` seeded with a pinned wall (the nav expanded). */
function pinnedStorage(): LayoutStorage {
  const entries = new Map<string, string>([
    [LAYOUT_KEY, JSON.stringify({ navCollapsed: false, wallPinned: true })],
  ]);
  const getItem = vi.fn<GetItem>((key) => entries.get(key) ?? null);
  const setItem = vi.fn<SetItem>((key, value) => {
    entries.set(key, value);
  });
  return { getItem, setItem };
}

const NO_SESSION_ROUTES = ["/", `/characters/${ID_A}`, "/settings", "/search"];

describe("016 step 006 — a stored pin shows the wall only on a session (US-095.AC-1, D1)", () => {
  it.each(NO_SESSION_ROUTES)(
    "with a stored wallPinned: true, %s has no Note wall (not even hidden) and no Open notes — DoD-9",
    async (path) => {
      stubWorkspace([CHAR_A], [SESSION_ONE]);
      renderApp(path, pinnedStorage());
      await flush();

      expect(navElement()).toBeInTheDocument();
      expect(screen.queryAllByRole("complementary", { hidden: true })).toHaveLength(0);
      expect(document.querySelector(`[aria-label="${WALL_NAME}"]`)).toBeNull();
      expect(screen.queryByRole("button", { name: OPEN_NOTES_NAME, hidden: true })).toBeNull();
    },
  );

  it("with a stored wallPinned: true, /sessions/1 shows the wall as a pinned column inside the main region, and the .app grid still has exactly the nav and the main — DoD-9", async () => {
    stubWorkspace([CHAR_A], [SESSION_ONE]);
    renderApp(SESSION_ONE_ROUTE, pinnedStorage());
    await flush();

    const wall = await within(mainElement()).findByRole("complementary", { name: WALL_NAME });
    expect(mainElement().contains(wall)).toBe(true);
    expect(within(wall).getByRole("button", { name: UNPIN_NOTES_NAME })).toBeInTheDocument();
    expect(within(wall).getByRole("region", { name: NOTES_REGION_NAME })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: OPEN_NOTES_NAME, hidden: true })).toBeNull();
    const sessionRoot = wall.closest(`.${SESSION_ROOT_CLASS}`);
    expect(sessionRoot).not.toBeNull();
    expect(sessionRoot?.classList.contains(PINNED_CLASS)).toBe(true);

    const grid = navElement().parentElement;
    expect(grid).not.toBeNull();
    expect(grid?.classList.contains("app")).toBe(true);
    const children = Array.from(grid?.children ?? []);
    expect(children).toHaveLength(2);
    expect(children[0]).toBe(navElement());
    expect(children[1]).toBe(mainElement());
  });
});

// ---------------------------------------------------------------------------
// Feature 017, step 007 — `/settings` renders the settings screen inside the shell (D15,
// US-092.AC-1). The screen's own behaviour is SettingsScreen.test.tsx's; these clauses assert the
// route `App` declares and the user menu's way into it. "— DoD-8" / "— DoD-9" are 017 step 007's.
/** Every request for one exact method + pathname + query. */
function requestsFor(calls: Seen[], method: string, path: string, search: string): Seen[] {
  return calls.filter((call) => call.method === method && call.path === path && call.search === search);
}

describe("017 step 007 — /settings renders the settings screen in the same shell (D15)", () => {
  it("at /settings the main region holds the Settings heading, the Languages and Your notes regions, with the tree still present — DoD-8", async () => {
    const { calls } = stubWorkspace([CHAR_A]);
    renderApp(SETTINGS_ROUTE);
    await flush();

    expect(navElement()).toBeInTheDocument();
    expect(queryTreeRow(CHAR_A.name)).not.toBeNull();
    const main = within(mainElement());
    expect(await main.findByRole("heading", { name: SETTINGS_HEADING })).toBeInTheDocument();
    expect(main.getByRole("region", { name: LANGUAGES_REGION })).toBeInTheDocument();
    expect(main.getByRole("region", { name: YOUR_NOTES_REGION })).toBeInTheDocument();
    expect(within(navElement()).queryByRole("heading", { name: SETTINGS_HEADING })).toBeNull();
    expect(main.queryByText(NOT_FOUND_TEXT)).toBeNull();
    expect(mainText()).not.toBe("");

    expect(requestsFor(calls, "GET", USER_SETTINGS_PATH, "")).toHaveLength(1);
    expect(requestsFor(calls, "GET", MEMOS_PATH, USER_NOTES_SEARCH)).toHaveLength(1);
  });

  it("the user menu's Settings item navigates in-entry to /settings, and the settings screen renders — DoD-9", async () => {
    const user = newUser();
    stubWorkspace([CHAR_A]);
    renderApp("/");
    await flush();
    expect(mainText()).toBe("");

    await user.click(within(navElement()).getByRole("button", { name: USER_MENU_NAME }));
    await user.click(await screen.findByRole("menuitem", { name: SETTINGS_ITEM }));
    await flush();

    expect(currentPath()).toBe(SETTINGS_ROUTE);
    const main = within(mainElement());
    expect(await main.findByRole("heading", { name: SETTINGS_HEADING })).toBeInTheDocument();
    expect(main.getByRole("region", { name: LANGUAGES_REGION })).toBeInTheDocument();
    expect(navElement()).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Feature 017, step 011 — the session screen's header bar at the route (D16). The bar's own
// behaviour is SessionConfigBar.test.tsx's; this clause proves the amended stub answers its two
// reads and the bar sits in the main region. "— DoD-11" is 017 step 011's.
describe("017 step 011 — /sessions/1 renders the session configuration bar", () => {
  it("at /sessions/1 the main region holds the Session configuration group, from one configuration read and one models read — DoD-11", async () => {
    const { calls } = stubWorkspace([CHAR_A], [SESSION_ONE]);
    renderApp(SESSION_ONE_ROUTE);
    await flush();

    const main = within(mainElement());
    expect(await main.findByRole("group", { name: CONFIG_BAR_NAME })).toBeInTheDocument();
    expect(main.getByRole("heading", { name: START_LABEL_HEADING })).toBeInTheDocument();
    expect(
      calls.filter(
        (call) => call.method === "GET" && call.path === `/api/sessions/${SESSION_ONE_ID}/configuration`,
      ),
    ).toHaveLength(1);
    expect(calls.filter((call) => call.method === "GET" && call.path === MODELS_PATH)).toHaveLength(1);
  });

  it("at / no configuration or models read is made — DoD-11", async () => {
    const { calls } = stubWorkspace([CHAR_A], [SESSION_ONE]);
    renderApp("/");
    await flush();

    expect(mainText()).toBe("");
    expect(calls.filter((call) => SESSION_CONFIGURATION_PATTERN.test(call.path))).toEqual([]);
    expect(calls.filter((call) => call.path === MODELS_PATH)).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Feature 018, step 009 — the character page inside the app (018 DoD-3, DoD-5, DoD-7, DoD-8).
// Expected values come from 018's step file and context.md: D5 (the page composer posts once,
// then pushes to the new session), D6 (the draft page creates on Name's focus loss and replaces
// the location), D7 (save on focus loss), D10 (no wall) and the UI strings table. Push versus
// replace is observed through the MemoryRouter's history (a Back probe), never a navigate spy.
const PROBE_BACK_NAME = /^probe back$/i;
const START_REGION_NAME = "Start a session";

function BackProbe() {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => void navigate(-1)}>
      probe back
    </button>
  );
}

/** `App` over a given history, with the location probe and a Back probe beside it. */
function renderAppWithHistory(initialEntries: string[], initialIndex: number) {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={initialEntries} initialIndex={initialIndex}>
        <App user={USER} storage={null} />
        <LocationProbe />
        <BackProbe />
      </MemoryRouter>
    </AppProviders>,
  );
}

const ID_ARIA = "7250000000000000021";
const CHAR_ARIA: Character = {
  id: ID_ARIA,
  name: "Aria",
  sheet: "# Aria",
  archived_at: null,
  // Older than `stubWorkspace`'s PATCH stamp (LATER_STAMP), as a real save answer is never
  // older than the row it saved (008 DoD-8 / D7 "not older" rule).
  created_at: "2026-04-01T09:00:00.000000+00:00",
  updated_at: "2026-04-01T09:00:00.000000+00:00",
};

function startRegion(): HTMLElement {
  return within(mainElement()).getByRole("region", { name: START_REGION_NAME });
}

describe("018 step 009 — the draft page creates on Name's focus loss and replaces the location (D6)", () => {
  it("typing Aria and the persona # Aria, then blurring Name, sends one exact POST, lists Aria, lands on the served id, and Back skips /characters/new — DoD-3", async () => {
    const user = newUser();
    const { calls } = stubWorkspace([]);
    renderAppWithHistory(["/", NEW_CHARACTER_ROUTE], 1);
    await flush();
    expect(within(mainElement()).queryByRole("button", { name: CREATE_NAME })).toBeNull();

    // The persona first — its focus loss does nothing in a draft — then Name, then Name's
    // focus loss, which creates with whatever persona the draft holds.
    await user.type(screenPersonaField(), "# Aria");
    await user.type(screenNameField(), "Aria");
    await user.tab();
    await flush();

    const posts = calls.filter((call) => call.method === "POST" && call.path === COLLECTION_PATH);
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({ name: "Aria", sheet: "# Aria" });
    expect(queryTreeRow("Aria")).not.toBeNull();
    expect(currentPath()).toBe(`/characters/${CREATED_ID}`);

    await user.click(screen.getByRole("button", { name: PROBE_BACK_NAME }));
    await flush();

    expect(currentPath()).not.toBe(NEW_CHARACTER_ROUTE);
    expect(currentPath()).toBe("/");
  });
});

describe("018 step 009 — a renamed character reads the new name in the heading and the tree (D7, US-021.AC-1)", () => {
  it("with no Save button, changing Name to Aria Vale and blurring sends exactly PATCH {name} and the heading and the tree row read Aria Vale — DoD-5", async () => {
    const user = newUser();
    const { calls } = stubWorkspace([CHAR_ARIA]);
    renderApp(`/characters/${ID_ARIA}`);
    await flush();

    const main = within(mainElement());
    expect(main.getByRole("heading", { name: "Aria" })).toBeInTheDocument();
    expect(main.queryByRole("button", { name: SAVE_NAME })).toBeNull();

    await user.clear(screenNameField());
    await user.type(screenNameField(), "Aria Vale");
    await user.tab();
    await flush();

    const patches = calls.filter(
      (call) => call.method === "PATCH" && call.path === `${COLLECTION_PATH}/${ID_ARIA}`,
    );
    expect(patches.map((call) => call.body)).toEqual([{ name: "Aria Vale" }]);
    expect(main.getByRole("heading", { name: "Aria Vale" })).toBeInTheDocument();
    expect(treeRow("Aria Vale")).toBeInTheDocument();
  });
});

describe("018 step 009 — the character page renders no note wall (D10, US-095.AC-1)", () => {
  it("even with a stored pin, /characters/<id> has no Note wall, no Open notes, no Your notes / Session notes group and no /memo-chain request — DoD-7", async () => {
    const { calls } = stubWorkspace([CHAR_A], [SESSION_ONE]);
    renderApp(`/characters/${ID_A}`, pinnedStorage());
    await flush();
    await within(mainElement()).findByRole("region", { name: NOTES_REGION_NAME });

    expect(screen.queryAllByRole("complementary", { hidden: true })).toHaveLength(0);
    expect(document.querySelector(`[aria-label="${WALL_NAME}"]`)).toBeNull();
    expect(screen.queryByRole("button", { name: OPEN_NOTES_NAME, hidden: true })).toBeNull();
    for (const name of [YOUR_NOTES_REGION, "Session notes"]) {
      expect(screen.queryByRole("region", { name, hidden: true })).toBeNull();
      expect(screen.queryByRole("heading", { name, hidden: true })).toBeNull();
    }
    expect(calls.filter((call) => call.path.endsWith("/memo-chain"))).toEqual([]);
  });
});

describe("018 step 009 — the page composer starts a session with its opening message (D5, US-117)", () => {
  it("the composer offers no Entry kind group and no Setup choice; Hello there + Send posts exactly {opening_message}, lands on /sessions/<served id> and the tree lists it under the character — DoD-8", async () => {
    const user = newUser();
    const { calls } = stubWorkspace([CHAR_A]);
    renderApp(`/characters/${ID_A}`);
    await flush();

    const composerRegion = startRegion();
    const scope = within(composerRegion);
    expect(scope.queryByRole("radiogroup", { name: /entry kind/i })).toBeNull();
    expect(scope.queryByRole("group", { name: /entry kind/i })).toBeNull();
    expect(scope.queryByRole("combobox", { name: /^setup$/i })).toBeNull();
    expect(scope.queryByRole("textbox", { name: /^setup$/i })).toBeNull();
    expect(scope.queryByRole("listbox", { name: /^setup$/i })).toBeNull();

    await user.type(scope.getByRole("textbox", { name: COMPOSER_NAME }), "Hello there");
    await user.click(scope.getByRole("button", { name: "Send" }));
    await flush();

    const posts = calls.filter(
      (call) => call.method === "POST" && call.path === characterSessionsPath(ID_A),
    );
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({ opening_message: "Hello there" });
    expect(currentPath()).toBe(`/sessions/${STARTED_SESSION_ID}`);
    expect(
      within(treeSessionsListFor(CHAR_A.name))
        .queryAllByRole("link")
        .map((link) => link.getAttribute("href") ?? ""),
    ).toEqual([`/sessions/${STARTED_SESSION_ID}`]);
  });
});

// ---------------------------------------------------------------------------
// Feature 029, step 005 — `/search` renders `SearchScreen` inside the same shell, and the
// collapsed rail's existing "Search" button reaches it with its box focused (029 U4, D9,
// US-118.AC-2). The screen's own behaviour is SearchScreen.test.tsx's; these clauses assert the
// route `App` declares, the rail's way into it and the two route-set amendments this step owns.
// "— DoD-11" / "— DoD-12" are 029 step 005's. Expected strings come from 029 context.md's
// Literals table. No `/api/search` branch is added to `stubWorkspace`: every render here lands on
// `/search` with a blank `q`, which makes no request (029 decision 10, step 005 DoD-7).
const SEARCH_ROUTE = "/search";
const SEARCH_BOX_NAME = "Search query";
const RAIL_SEARCH_NAME = /^search$/i;

/** A file-local in-memory `LayoutStorage` seeded with the nav collapsed to the rail. */
function collapsedStorage(): LayoutStorage {
  const entries = new Map<string, string>([
    [LAYOUT_KEY, JSON.stringify({ navCollapsed: true, wallPinned: false })],
  ]);
  const getItem = vi.fn<GetItem>((key) => entries.get(key) ?? null);
  const setItem = vi.fn<SetItem>((key, value) => {
    entries.set(key, value);
  });
  return { getItem, setItem };
}

function searchBox(): HTMLElement {
  return within(mainElement()).getByRole("textbox", { name: SEARCH_BOX_NAME });
}

describe("029 step 005 — the rail's Search trigger reaches the results page (US-118.AC-2, D9)", () => {
  it("with the tree collapsed to the rail, the rail's Search button lands on /search with the Search query box focused — DoD-11", async () => {
    const user = newUser();
    stubWorkspace([CHAR_A], [SESSION_ONE]);
    renderApp("/", collapsedStorage());
    await flush();

    await user.click(within(navElement()).getByRole("button", { name: RAIL_SEARCH_NAME }));
    await flush();

    expect(currentPath()).toBe(SEARCH_ROUTE);
    expect(searchBox()).toBeInTheDocument();
    expect(searchBox()).toHaveFocus();
  });

  it("with the tree expanded, /search renders the Search query box in the centre beside the tree — DoD-11", async () => {
    stubWorkspace([CHAR_A], [SESSION_ONE]);
    renderApp(SEARCH_ROUTE);
    await flush();

    expect(navElement()).toBeInTheDocument();
    expect(queryTreeRow(CHAR_A.name)).not.toBeNull();
    expect(searchBox()).toBeInTheDocument();
    expect(searchBox()).toHaveFocus();
    expect(within(mainElement()).queryByText(NOT_FOUND_TEXT)).toBeNull();
  });
});

describe("029 step 005 — the two route-set amendments this step owns (005.context.md)", () => {
  it("/search has left the empty-centre set and its centre now holds the Search query box — DoD-12", async () => {
    expect(EMPTY_CENTRE_ROUTES).toEqual(["/"]);

    stubWorkspace([CHAR_A], [SESSION_ONE]);
    renderApp(SEARCH_ROUTE);
    await flush();

    expect(searchBox()).toBeInTheDocument();
    expect(mainText()).not.toBe("");
    expect(within(mainElement()).queryByText(NOT_FOUND_TEXT)).toBeNull();
  });

  it("/search stays in the no-note-wall set: it renders the box and no wall, not even hidden — DoD-12", async () => {
    expect(NO_SESSION_ROUTES).toContain(SEARCH_ROUTE);

    stubWorkspace([CHAR_A], [SESSION_ONE]);
    renderApp(SEARCH_ROUTE, pinnedStorage());
    await flush();

    expect(searchBox()).toBeInTheDocument();
    expect(screen.queryAllByRole("complementary", { hidden: true })).toHaveLength(0);
    expect(document.querySelector(`[aria-label="${WALL_NAME}"]`)).toBeNull();
    expect(screen.queryByRole("button", { name: OPEN_NOTES_NAME, hidden: true })).toBeNull();
  });
});
