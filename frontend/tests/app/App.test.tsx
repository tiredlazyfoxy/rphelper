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
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChangeEvent } from "react";
import { App } from "../../src/app/App";
import type { Character } from "../../src/app/charactersApi";
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

/** The declared routes whose centre is still empty (009 fills the two character routes). */
const EMPTY_CENTRE_ROUTES = ["/", "/sessions/1", "/settings", "/search"];

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

/**
 * The wire contract of `/api/characters` over an in-memory row set (009 context.md), with
 * every request recorded in order. Only the listing honours the include-archived flag; a
 * mutation answers the single row it changed.
 */
function stubWorkspace(rows: Character[]) {
  const store = new Map<string, Character>(rows.map((row) => [row.id, row]));
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>(async (input, init) => {
    const url = requestUrl(input);
    const method = requestMethod(input, init);
    const body = parseBody(init);
    calls.push({ method, path: url.pathname, search: url.search, body });

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
    stubFetch((input) =>
      requestPath(input) === COLLECTION_PATH
        ? Promise.resolve(jsonResponse({ characters: [] }, 200))
        : Promise.reject(new Error("no other request is expected in new mode")),
    );
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
