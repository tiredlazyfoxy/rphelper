// Feature 008, step 004 — the workspace shell component (DoD-1..DoD-9).
// The route table's clauses (DoD-10, DoD-11) live in App.test.tsx; DoD-12 and DoD-13 are
// [manual/live] and carry no test.
// The accessible names "Workspace navigation", "Collapse tree", "Expand tree", "Search",
// "New character" and "User menu" are the contract (004.workspace-shell-and-routes.md);
// controls are found by those names and never by glyph, test id or structure (D10).
// jsdom applies no stylesheet, so the layout contract asserted here is the grid element's
// classes and the rendered content — never a computed width (004.context.md).
//
// Amended by feature 009, step 008 (DoD-7): `WorkspaceShellProps` gains the required
// `characters` prop, and the expanded column's body is now the character tree (009 D13), so
// every render supplies a fresh `CharactersState` and a `fetch` answering
// `GET /api/characters`. The block at the bottom of this file adds DoD-7's clauses; 008's own
// clauses (persistence, the narrow overlay, the two-child grid) are unchanged. The rail and
// the expanded column are mutually exclusive, so the rail clauses keep their meaning; their
// control lookups are scoped to the nav column to say so.
//
// Amended by feature 011, step 006 (DoD-10): `WorkspaceShellProps` gains the required
// `sessions` prop, which the shell hands — with its existing `storage` — to the tree, so every
// render below supplies a **fresh** `SessionsState` and `stubCharactersFetch` now also answers
// `GET /api/sessions`, routed by the exact pathname (it rejects anything else, so without the
// branch every clause in this file would fail on an unexpected request). 008's and 009's own
// assertions are unchanged: the tree's chevron labels are "Collapse <name>", never the
// anchored "Collapse tree" the shell's own control carries, and reading the collapsed set
// writes nothing, so the "writes nothing to the storage" clauses keep their meaning.
import type * as React from "react";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { WorkspaceShell } from "../../src/app/WorkspaceShell";
import { NARROW_VIEWPORT_QUERY } from "../../src/app/shellState";
import { CharactersState } from "../../src/app/charactersState";
import type { Character } from "../../src/app/charactersApi";
import type { Session } from "../../src/app/sessionsApi";
import { SessionsState } from "../../src/app/sessionsState";
import { WORKSPACE_LAYOUT_KEY } from "../../src/app/workspaceLayout";
import { documentNavigation } from "../../src/shared/api";
import { AppProviders } from "../../src/shared/AppProviders";
import type { CurrentUser } from "../../src/shared/currentUser";

const NAV_NAME = /^workspace navigation$/i;
const COLLAPSE_NAME = /^collapse tree$/i;
const EXPAND_NAME = /^expand tree$/i;
const SEARCH_NAME = /^search$/i;
const NEW_CHARACTER_NAME = /^new character$/i;
const USER_MENU_NAME = /^user menu$/i;

// 009 step 008 (D4, D13): the tree's own names inside the expanded column.
const SHOW_ARCHIVED_NAME = /^show archived$/i;
const CHARACTERS_LIST_NAME = /^characters$/i;

const SETTINGS_ITEM = /^settings$/i;
const LOGOUT_ITEM = /^log out$/i;

/** Distinctive enough that its presence as the menu trigger's text is meaningful. */
const USERNAME = "zmiraqua";
const USERNAME_TEXT = /^zmiraqua$/;

/** The centre column's content in these renders: the shell is a frame around children. */
const CENTRE_TEXT = "centre zq-55";

const SEARCH_PATH = "/search";
const NEW_CHARACTER_PATH = "/characters/new";
const SETTINGS_PATH = "/settings";

const COLLAPSED_CLASS = "nav-collapsed";
const OVERLAY_CLASS = "nav-overlay-open";
const SHELL_CLASS = "app";

type User = ReturnType<typeof userEvent.setup>;
type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

/** Mantine's floating layers set pointer-events; the house workaround for user-event. */
function newUser(): User {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

const USER: CurrentUser = { id: "9007199254740993", username: USERNAME, role: "roleplayer" };

// ------------------------------------------------- 009 step 008: the tree's one request
// The expanded column mounts the tree, which lists the characters on mount (009 D13), so
// every render here needs that one GET answered. Anything else is a test failure.

const CHARACTERS_PATH = "/api/characters";

const TREE_CHARACTER: Character = {
  id: "7250000000000000011",
  name: "Aria Vance",
  sheet: "A scribe who never finishes a sentence.",
  archived_at: null,
  created_at: "2026-03-14T09:26:53.000000+00:00",
  updated_at: "2026-03-14T09:26:53.000000+00:00",
};

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// 011 step 006: the tree also loads the workspace sessions on mount (D16). The stub answers
// that one too, by exact pathname; `sessions` defaults to empty, so the 008 / 009 clauses see
// the tree they always saw, and DoD-10 re-stubs with a row.
const SESSIONS_PATH = "/api/sessions";

const TREE_SESSION: Session = {
  id: "9007199254740993001",
  character_id: TREE_CHARACTER.id,
  setup_id: null,
  setup_name: null,
  archived_at: null,
  last_used_at: "2026-05-10T09:00:00.000000+00:00",
  created_at: "2026-05-10T09:00:00.000000+00:00",
  updated_at: "2026-05-10T09:00:00.000000+00:00",
};

function stubCharactersFetch(sessions: Session[] = []): void {
  vi.stubGlobal(
    "fetch",
    vi.fn<FetchFn>((input) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const url = new URL(raw, "http://localhost");
      if (url.pathname === SESSIONS_PATH) {
        return Promise.resolve(jsonResponse({ sessions }, 200));
      }
      if (url.pathname !== CHARACTERS_PATH) {
        return Promise.reject(new TypeError(`unexpected request in shell test: ${url.pathname}`));
      }
      return Promise.resolve(jsonResponse({ characters: [TREE_CHARACTER] }, 200));
    }),
  );
}

/** Lets the tree's listing settle so the expanded column reaches its ready state. */
async function flush(rounds = 6): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => setImmediate(resolve));
    });
  }
}

// ----------------------------------------------------------------- the storage
// A fake LayoutStorage with spy-able getItem/setItem, never jsdom's localStorage, so
// "no write happened" is assertable (004.context.md; D3).

function fakeStorage(storedNavCollapsed?: boolean) {
  const values = new Map<string, string>();
  if (storedNavCollapsed !== undefined) {
    values.set(
      WORKSPACE_LAYOUT_KEY,
      JSON.stringify({ navCollapsed: storedNavCollapsed, wallPinned: false }),
    );
  }
  const getItem = vi.fn((key: string): string | null => values.get(key) ?? null);
  const setItem = vi.fn((key: string, value: string): void => {
    values.set(key, value);
  });
  return { getItem, setItem, values };
}

function storedRecord(store: ReturnType<typeof fakeStorage>): Record<string, unknown> | null {
  const raw = store.values.get(WORKSPACE_LAYOUT_KEY);
  if (raw === undefined) {
    return null;
  }
  return JSON.parse(raw) as Record<string, unknown>;
}

// ------------------------------------------------------------------- the width
// tests/setup.ts's matchMedia polyfill reports `matches: false` for every query, so an
// un-stubbed render is the wide case. A narrow render replaces window.matchMedia with a
// stub matching exactly NARROW_VIEWPORT_QUERY; the original is restored after each test,
// because step 002's tests and tests/setup.ts share that global.

const originalMatchMedia = window.matchMedia;

function installMatchMedia(value: typeof window.matchMedia): void {
  Object.defineProperty(window, "matchMedia", { writable: true, configurable: true, value });
}

function stubNarrowViewport(): void {
  installMatchMedia(
    (query: string): MediaQueryList => ({
      matches: query === NARROW_VIEWPORT_QUERY,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  );
}

// ------------------------------------------------------------------ the render

function LocationProbe(): React.JSX.Element {
  const location = useLocation();
  return <output data-testid="probe-location">{location.pathname}</output>;
}

function currentPath(): string {
  return screen.getByTestId("probe-location").textContent ?? "";
}

// 009 step 008: the one render call site, now supplying the required `characters` prop —
// a fresh workspace state per render (009 D11).
function renderShell(store: ReturnType<typeof fakeStorage>) {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={["/"]}>
        {/* 011 step 006: `sessions` is required; a fresh workspace state per render (D15). */}
        <WorkspaceShell
          user={USER}
          storage={store}
          characters={new CharactersState()}
          sessions={new SessionsState()}
        >
          <p>{CENTRE_TEXT}</p>
        </WorkspaceShell>
        <LocationProbe />
      </MemoryRouter>
    </AppProviders>,
  );
}

// ------------------------------------------------------------------ the queries

function navElement(): HTMLElement {
  return screen.getByRole("navigation", { name: NAV_NAME });
}

function mainElement(): HTMLElement {
  return screen.getByRole("main");
}

/** The grid element: the one element the nav column sits in. */
function gridElement(): HTMLElement {
  const grid = navElement().parentElement;
  if (grid === null) {
    throw new Error("test setup: the shell's grid element is not mounted");
  }
  return grid;
}

function control(name: RegExp): HTMLElement {
  return screen.getByRole("button", { name });
}

function missingControl(name: RegExp): HTMLElement | null {
  return screen.queryByRole("button", { name });
}

/**
 * 009 step 008: the left column's own control. The rail and the expanded column are two
 * exclusive branches of the same nav, and from 009 both offer "Search" / "New character", so
 * the clauses about one branch say which element they mean.
 */
function navControl(name: RegExp): HTMLElement {
  return within(navElement()).getByRole("button", { name });
}

function navMissingControl(name: RegExp): HTMLElement | null {
  return within(navElement()).queryByRole("button", { name });
}

/** The tree's "Show archived" switch, however Mantine exposes it (role switch or checkbox). */
function queryArchivedSwitch(): HTMLElement | null {
  const nav = within(navElement());
  return (
    nav.queryByRole("switch", { name: SHOW_ARCHIVED_NAME }) ??
    nav.queryByRole("checkbox", { name: SHOW_ARCHIVED_NAME })
  );
}

/** The tree's character level, by its accessible name (a list or the equivalent landmark). */
function queryCharactersList(): HTMLElement | null {
  const nav = within(navElement());
  return (
    nav.queryByRole("list", { name: CHARACTERS_LIST_NAME }) ??
    nav.queryByRole("navigation", { name: CHARACTERS_LIST_NAME })
  );
}

/** The menu item carrying `name`: the activatable element its label sits in. */
function item(name: RegExp): HTMLElement {
  const label = screen.getByText(name);
  return label.closest<HTMLElement>("a, button, [role='menuitem']") ?? label;
}

/** Opens the user menu (a portal, mounted only while open) and waits for its content. */
async function openUserMenu(user: User): Promise<void> {
  await user.click(control(USER_MENU_NAME));
  await screen.findByText(LOGOUT_ITEM);
}

function hasClass(name: string): boolean {
  return gridElement().classList.contains(name);
}

/** The rail: expand, search, create and the user menu; no collapse control. */
function expectRail(): void {
  expect(navControl(EXPAND_NAME)).toBeInTheDocument();
  expect(navControl(SEARCH_NAME)).toBeInTheDocument();
  expect(navControl(NEW_CHARACTER_NAME)).toBeInTheDocument();
  expect(navControl(USER_MENU_NAME)).toBeInTheDocument();
  expect(navMissingControl(COLLAPSE_NAME)).toBeNull();
}

/** The expanded column: the collapse control and the user menu; no expand control. */
function expectExpandedColumn(): void {
  expect(navControl(COLLAPSE_NAME)).toBeInTheDocument();
  expect(navControl(USER_MENU_NAME)).toBeInTheDocument();
  expect(navMissingControl(EXPAND_NAME)).toBeNull();
}

let navigate: MockInstance<(url: string) => void>;

beforeEach(() => {
  navigate = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
  stubCharactersFetch(); // 009 step 008: the expanded column's tree lists on mount
});

afterEach(() => {
  installMatchMedia(originalMatchMedia);
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
describe("the expanded shell at wide width (UC-070)", () => {
  it("renders the Workspace navigation nav and a main region holding the centre — DoD-1", () => {
    renderShell(fakeStorage());

    expect(navElement()).toBeInTheDocument();
    expect(mainElement()).toBeInTheDocument();
    expect(within(mainElement()).getByText(CENTRE_TEXT)).toBeInTheDocument();
  });

  it("gives the grid element the app class without nav-collapsed — DoD-1", () => {
    renderShell(fakeStorage());

    expect(hasClass(SHELL_CLASS)).toBe(true);
    expect(hasClass(COLLAPSED_CLASS)).toBe(false);
    expect(hasClass(OVERLAY_CLASS)).toBe(false);
  });

  it("shows the Collapse tree control and the User menu trigger with the username — DoD-1", () => {
    renderShell(fakeStorage());

    expect(within(navElement()).getByRole("button", { name: COLLAPSE_NAME })).toBeInTheDocument();
    expect(within(navElement()).getByRole("button", { name: USER_MENU_NAME })).toBeInTheDocument();
    expect(within(navElement()).getByText(USERNAME_TEXT)).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
describe("collapsing to the rail at wide width (US-090.AC-1)", () => {
  it("adds nav-collapsed to the grid element — DoD-2", async () => {
    const user = newUser();
    renderShell(fakeStorage());

    await user.click(control(COLLAPSE_NAME));

    await waitFor(() => {
      expect(hasClass(COLLAPSED_CLASS)).toBe(true);
    });
    expect(hasClass(SHELL_CLASS)).toBe(true);
  });

  it("replaces the expanded column with the rail's search, create and expand — DoD-2", async () => {
    const user = newUser();
    renderShell(fakeStorage());

    await user.click(control(COLLAPSE_NAME));

    await waitFor(() => {
      expect(missingControl(COLLAPSE_NAME)).toBeNull();
    });
    expectRail();
  });
});

// ---------------------------------------------------------------------------
describe("the rail keeps the user menu reachable (US-090.AC-1)", () => {
  it("the User menu trigger opens the menu with Settings and Log out — DoD-3", async () => {
    const user = newUser();
    renderShell(fakeStorage(true));
    expectRail();

    await openUserMenu(user);

    expect(screen.getByText(SETTINGS_ITEM)).toBeInTheDocument();
    expect(screen.getByText(LOGOUT_ITEM)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
describe("the rail's two in-entry navigations (D4, US-090.AC-1)", () => {
  it("New character moves the in-entry router to /characters/new — DoD-4", async () => {
    const user = newUser();
    renderShell(fakeStorage(true));
    expect(currentPath()).toBe("/");

    await user.click(control(NEW_CHARACTER_NAME));

    await waitFor(() => {
      expect(currentPath()).toBe(NEW_CHARACTER_PATH);
    });
    expect(navigate).not.toHaveBeenCalled();
  });

  it("Search moves the in-entry router to /search — DoD-4", async () => {
    const user = newUser();
    renderShell(fakeStorage(true));
    expect(currentPath()).toBe("/");

    await user.click(control(SEARCH_NAME));

    await waitFor(() => {
      expect(currentPath()).toBe(SEARCH_PATH);
    });
    expect(navigate).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("the collapse survives a remount (UC-070)", () => {
  it("a collapse is stored, restored on a fresh mount, and reversed by Expand tree — DoD-5", async () => {
    const user = newUser();
    const store = fakeStorage();
    const first = renderShell(store);

    await user.click(control(COLLAPSE_NAME));

    await waitFor(() => {
      expect(storedRecord(store)).not.toBeNull();
    });
    expect(storedRecord(store)?.navCollapsed).toBe(true);

    first.unmount();
    renderShell(store);

    expect(hasClass(COLLAPSED_CLASS)).toBe(true);
    expectRail();

    await user.click(control(EXPAND_NAME));

    await waitFor(() => {
      expect(hasClass(COLLAPSED_CLASS)).toBe(false);
    });
    expectExpandedColumn();
    expect(storedRecord(store)?.navCollapsed).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("below the threshold the left column is always the rail (D3)", () => {
  it("an expanded stored record still shows the rail — DoD-6", () => {
    stubNarrowViewport();
    const store = fakeStorage(false);
    renderShell(store);

    expectRail();
    expect(hasClass(OVERLAY_CLASS)).toBe(false);
  });

  it("Expand tree shows the expanded column and adds nav-overlay-open — DoD-6", async () => {
    stubNarrowViewport();
    const user = newUser();
    renderShell(fakeStorage(false));

    await user.click(control(EXPAND_NAME));

    await waitFor(() => {
      expect(hasClass(OVERLAY_CLASS)).toBe(true);
    });
    expectExpandedColumn();
  });

  it("opening the overlay writes nothing to the storage — DoD-6", async () => {
    stubNarrowViewport();
    const user = newUser();
    const store = fakeStorage(false);
    renderShell(store);

    await user.click(control(EXPAND_NAME));

    await waitFor(() => {
      expect(hasClass(OVERLAY_CLASS)).toBe(true);
    });
    expect(store.setItem).not.toHaveBeenCalled();
    expect(storedRecord(store)?.navCollapsed).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("dismissing the overlay (D11)", () => {
  it("Collapse tree closes it and shows the rail again — DoD-7", async () => {
    stubNarrowViewport();
    const user = newUser();
    renderShell(fakeStorage(false));
    await user.click(control(EXPAND_NAME));
    await waitFor(() => {
      expect(hasClass(OVERLAY_CLASS)).toBe(true);
    });

    await user.click(control(COLLAPSE_NAME));

    await waitFor(() => {
      expect(hasClass(OVERLAY_CLASS)).toBe(false);
    });
    expectRail();
  });

  it("closing the overlay writes nothing to the storage — DoD-7", async () => {
    stubNarrowViewport();
    const user = newUser();
    const store = fakeStorage(false);
    renderShell(store);
    await user.click(control(EXPAND_NAME));
    await waitFor(() => {
      expect(hasClass(OVERLAY_CLASS)).toBe(true);
    });

    await user.click(control(COLLAPSE_NAME));

    await waitFor(() => {
      expect(hasClass(OVERLAY_CLASS)).toBe(false);
    });
    expect(store.setItem).not.toHaveBeenCalled();
  });

  it("an in-entry navigation from the user menu closes it — DoD-7", async () => {
    stubNarrowViewport();
    const user = newUser();
    renderShell(fakeStorage(false));
    await user.click(control(EXPAND_NAME));
    await waitFor(() => {
      expect(hasClass(OVERLAY_CLASS)).toBe(true);
    });

    await openUserMenu(user);
    await user.click(item(SETTINGS_ITEM));

    await waitFor(() => {
      expect(currentPath()).toBe(SETTINGS_PATH);
    });
    await waitFor(() => {
      expect(hasClass(OVERLAY_CLASS)).toBe(false);
    });
    expectRail();
  });
});

// ---------------------------------------------------------------------------
describe("the overlay is not persisted", () => {
  it("a fresh shell over the same storage starts with the overlay closed — DoD-8", async () => {
    stubNarrowViewport();
    const user = newUser();
    const store = fakeStorage(false);
    const first = renderShell(store);
    await user.click(control(EXPAND_NAME));
    await waitFor(() => {
      expect(hasClass(OVERLAY_CLASS)).toBe(true);
    });

    first.unmount();
    renderShell(store);

    expect(hasClass(OVERLAY_CLASS)).toBe(false);
    expectRail();
  });
});

// ---------------------------------------------------------------------------
// Re-titled by feature 016, step 006 (DoD-13; D1): the wall lives inside the session screen, so
// the shell grid never holds it. Every assertion below is unchanged.
describe("the shell grid is two columns and never holds the wall — the wall lives inside the session screen (016 006 DoD-13)", () => {
  it("the expanded shell's grid element has exactly two child elements — DoD-9", () => {
    renderShell(fakeStorage());

    const children = Array.from(gridElement().children);
    expect(children).toHaveLength(2);
    expect(children[0]).toBe(navElement());
    expect(children[1]).toBe(mainElement());
  });

  it("the collapsed shell's grid element has exactly two child elements — DoD-9", () => {
    renderShell(fakeStorage(true));

    const children = Array.from(gridElement().children);
    expect(children).toHaveLength(2);
    expect(children[0]).toBe(navElement());
    expect(children[1]).toBe(mainElement());
  });

  it("no wall control is rendered in either column state — DoD-9", () => {
    const first = renderShell(fakeStorage());
    expect(missingControl(/wall/i)).toBeNull();

    first.unmount();
    renderShell(fakeStorage(true));

    expect(missingControl(/wall/i)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Feature 009, step 008 — the expanded column's body is the character tree (009 D13).
describe("the expanded column carries the character tree (009 D13)", () => {
  it("the nav holds Collapse tree, the Show archived switch, the Characters list and the User menu — DoD-7", async () => {
    renderShell(fakeStorage());
    await flush();

    expect(navControl(COLLAPSE_NAME)).toBeInTheDocument();
    expect(queryArchivedSwitch()).not.toBeNull();
    expect(queryCharactersList()).not.toBeNull();
    expect(navControl(USER_MENU_NAME)).toBeInTheDocument();
  });

  it("the rail keeps Search, New character, Expand tree and User menu, and loses the switch — DoD-7", async () => {
    const user = newUser();
    renderShell(fakeStorage());
    await flush();
    expect(queryArchivedSwitch()).not.toBeNull();

    await user.click(navControl(COLLAPSE_NAME));
    await waitFor(() => {
      expect(navMissingControl(COLLAPSE_NAME)).toBeNull();
    });

    expectRail();
    expect(queryArchivedSwitch()).toBeNull();
    expect(queryCharactersList()).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Feature 011, step 006 — the shell hands the workspace sessions state to the tree (D15, D16).
/** Session rows anywhere in the nav column, identified by their `/sessions/<id>` href. */
function navSessionHrefs(): string[] {
  return within(navElement())
    .queryAllByRole("link")
    .map((link) => link.getAttribute("href") ?? "")
    .filter((value) => value.startsWith("/sessions/"));
}

describe("the expanded column's tree carries the session level (011 D16)", () => {
  it("the nav holds Collapse tree, the switch, the Characters list, the User menu and the session rows — DoD-10", async () => {
    stubCharactersFetch([TREE_SESSION]);
    renderShell(fakeStorage());
    await flush();

    expect(navControl(COLLAPSE_NAME)).toBeInTheDocument();
    expect(queryArchivedSwitch()).not.toBeNull();
    expect(queryCharactersList()).not.toBeNull();
    expect(navControl(USER_MENU_NAME)).toBeInTheDocument();
    expect(navSessionHrefs()).toEqual([`/sessions/${TREE_SESSION.id}`]);
  });

  it("the rail shows no session rows — DoD-10", async () => {
    const user = newUser();
    stubCharactersFetch([TREE_SESSION]);
    renderShell(fakeStorage());
    await flush();
    expect(navSessionHrefs()).toHaveLength(1);

    await user.click(navControl(COLLAPSE_NAME));
    await waitFor(() => {
      expect(navMissingControl(COLLAPSE_NAME)).toBeNull();
    });

    expectRail();
    expect(navSessionHrefs()).toEqual([]);
  });

  it("the centre column and the two-child grid are unchanged beside the session rows — DoD-10", async () => {
    stubCharactersFetch([TREE_SESSION]);
    renderShell(fakeStorage());
    await flush();

    expect(within(mainElement()).getByText(CENTRE_TEXT)).toBeInTheDocument();
    const children = Array.from(gridElement().children);
    expect(children).toHaveLength(2);
    expect(children[0]).toBe(navElement());
    expect(children[1]).toBe(mainElement());
  });
});
