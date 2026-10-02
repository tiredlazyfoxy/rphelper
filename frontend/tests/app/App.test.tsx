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
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChangeEvent } from "react";
import { App } from "../../src/app/App";
import type { Character } from "../../src/app/charactersApi";
import type { Session } from "../../src/app/sessionsApi";
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
 * this step's own clauses at the bottom of the file cover it.
 */
const EMPTY_CENTRE_ROUTES = ["/", "/settings", "/search"];

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

function renderApp(initialPath: string) {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={[initialPath]}>
        <App user={USER} storage={null} />
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
        const sent = (body ?? {}) as { setup_id?: string | null };
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
        return jsonResponse(started, 201);
      }
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
  it("renders the New character screen in the main region at /characters/new — DoD-13", async () => {
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
    expect(main.getByRole("button", { name: /^create$/i })).toBeInTheDocument();
  });

  it("renders the requested character in the main region at /characters/1 — DoD-13", async () => {
    stubFetch((input) => {
      const path = requestPath(input);
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
  it("lands on the created id and marks that row current, with no list request after the create — DoD-8", async () => {
    const user = newUser();
    const { calls } = stubWorkspace([]);
    renderApp(NEW_CHARACTER_ROUTE);
    await flush();
    expect(listRequests(calls)).toHaveLength(1);

    await user.type(screenNameField(), TYPED_NAME);
    await user.click(screenControl(CREATE_NAME));
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
  it("the tree row carries the saved name — DoD-10", async () => {
    const user = newUser();
    stubWorkspace([CHAR_A]);
    renderApp(`/characters/${ID_A}`);
    await flush();
    expect(queryTreeRow(CHAR_A.name)).not.toBeNull();

    await user.clear(screenNameField());
    await user.type(screenNameField(), EDITED_NAME);
    await user.click(screenControl(SAVE_NAME));
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
    expect(main.getByText(NO_ENTRIES_TEXT)).toBeInTheDocument();
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
    expect(main.getByText(NO_ENTRIES_TEXT)).toBeInTheDocument();
    expect(main.getByRole("link", { name: CHAR_A.name })).toHaveAttribute(
      "href",
      `/characters/${ID_A}`,
    );
  });
});
