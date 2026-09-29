// Feature 005, step 005 — the admin shell, the flat route table and the 404
// (DoD-6..DoD-14). DoD-1..DoD-4 live in navItems.test.ts, DoD-5 in adminShellState.test.ts;
// DoD-15..DoD-18 are [manual/live].
//
// Expected behaviour comes from the step's Interface intent and DoD and from context.md D8,
// D11, D12 and D15. The app is rendered inside a MemoryRouter (the frozen interface requires a
// router), with two test-only probes beside it: one reports the router's current pathname, one
// drives a navigation that is not a nav-item click. Some checks also boot the real entry
// (002/006's recipe, as in AdminNotReady.test.tsx) so the `/admin` basename is in force.
//
// Shell-state constructions are counted by wrapping the class's module: the wrapper returns a
// real instance from the real constructor, so behaviour is unchanged.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { runInAction } from "mobx";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { AdminApp } from "../../src/admin/AdminApp";
import { AdminShell } from "../../src/admin/AdminShell";
import { NotFoundPage } from "../../src/admin/NotFoundPage";
import { AdminShellState } from "../../src/admin/adminShellState";
import { documentNavigation } from "../../src/shared/api";
import { AppProviders } from "../../src/shared/AppProviders";

const { constructed } = vi.hoisted(() => ({ constructed: [] as Array<{ navbarOpened: boolean }> }));

vi.mock("../../src/admin/adminShellState", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../src/admin/adminShellState")>();
  function CountedAdminShellState(): InstanceType<typeof actual.AdminShellState> {
    const instance = new actual.AdminShellState();
    constructed.push(instance);
    return instance;
  }
  return { ...actual, AdminShellState: CountedAdminShellState as unknown as typeof actual.AdminShellState };
});

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const ADMIN_SRC = path.join(FRONTEND_ROOT, "src", "admin");
const ADMIN_APP_SOURCE = path.join(ADMIN_SRC, "AdminApp.tsx");
const ADMIN_SHELL_SOURCE = path.join(ADMIN_SRC, "AdminShell.tsx");

/** The 404 element's statement that the page does not exist. */
const NOT_FOUND_TEXT = /not found|does not exist|doesn't exist|no such page|404/i;
/** The `/` placeholder names the Users page. */
const USERS_TEXT = /users/i;
const NAV_LABELS = ["Users", "LLM Servers", "Database"] as const;
const SIGN_OUT_NAME = /sign ?out|log ?out|logout/i;
const COLOR_SCHEME_NAME = /colou?r ?scheme|dark|light|theme/i;

let navigate: MockInstance<(url: string) => void>;

beforeEach(() => {
  constructed.length = 0;
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-mantine-color-scheme");
  navigate = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
  // `/` renders the Users page (step 006), which lists users on mount; keep every render off
  // the network. The shell tests assert shell behaviour only, never the page's contents.
  stubFetch(answerShellRequests);
});

afterEach(() => {
  // Unmount first: AppProviders portals Mantine Notifications onto document.body, so wiping
  // the body before Testing Library's cleanup would make the later unmount throw.
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.body.innerHTML = "";
  window.history.pushState({}, "", "/");
});

// ---------------------------------------------------------------- probes

let probeNavigate: ((to: string) => void) | null = null;

function LocationProbe(): React.JSX.Element {
  const location = useLocation();
  return <output data-testid="probe-location">{location.pathname}</output>;
}

function NavigateProbe(): null {
  const go = useNavigate();
  probeNavigate = (to: string) => {
    void go(to);
  };
  return null;
}

function currentPath(): string {
  return screen.getByTestId("probe-location").textContent ?? "";
}

function routerNavigate(to: string): void {
  act(() => {
    if (probeNavigate === null) throw new Error("test setup: navigate probe not mounted");
    probeNavigate(to);
  });
}

// ---------------------------------------------------------------- renders

function renderApp(initialPath: string) {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={[initialPath]}>
        <AdminApp />
        <LocationProbe />
        <NavigateProbe />
      </MemoryRouter>
    </AppProviders>,
  );
}

function renderShell(shell: AdminShellState, initialPath = "/") {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={[initialPath]}>
        <AdminShell shell={shell}>
          <p>shell child zq-55</p>
        </AdminShell>
        <LocationProbe />
      </MemoryRouter>
    </AppProviders>,
  );
}

function renderNotFound(initialPath = "/nope") {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={[initialPath]}>
        <NotFoundPage />
        <LocationProbe />
      </MemoryRouter>
    </AppProviders>,
  );
}

// ---------------------------------------------------------------- queries

function header(): HTMLElement {
  return screen.getByRole("banner");
}

function navbar(): HTMLElement {
  return screen.getByRole("navigation");
}

function mainRegion(): HTMLElement {
  return screen.getByRole("main");
}

function navLink(label: string): HTMLElement {
  return within(navbar()).getByRole("link", { name: new RegExp(`^\\s*${label}\\s*$`, "i"), hidden: true });
}

function isHighlighted(element: HTMLElement): boolean {
  return element.hasAttribute("data-active");
}

function headerButtons(): HTMLElement[] {
  return within(header()).queryAllByRole("button", { hidden: true });
}

function burger(): HTMLElement {
  const buttons = headerButtons();
  expect(buttons).toHaveLength(1);
  return buttons[0];
}

function anchorsTo(container: HTMLElement, href: string): HTMLElement[] {
  return within(container)
    .queryAllByRole("link", { hidden: true })
    .filter((link) => link.getAttribute("href") === href);
}

function markers(): Element[] {
  return Array.from(document.querySelectorAll("[data-entry]"));
}

function markerValues(): string[] {
  return markers().map((el) => el.getAttribute("data-entry") ?? "");
}

function onlyMarker(): Element {
  expect(markerValues()).toEqual(["admin"]);
  return markers()[0];
}

/** The one shell state the rendered shell is bound to: the instance the burger opens. */
function liveShellAfterOpening(): { navbarOpened: boolean } {
  fireEvent.click(burger());
  const opened = constructed.filter((instance) => instance.navbarOpened);
  expect(opened).toHaveLength(1);
  return opened[0];
}

/**
 * Clicks `element` and reports whether the click's default action was prevented — i.e.
 * whether an in-document handler (the router) took it instead of the browser. The default is
 * then suppressed so jsdom does not attempt a document navigation.
 */
function clickReportingPrevented(element: HTMLElement): boolean {
  let prevented = false;
  const listener = (event: Event) => {
    prevented = event.defaultPrevented;
    event.preventDefault();
  };
  window.addEventListener("click", listener);
  try {
    fireEvent.click(element);
  } finally {
    window.removeEventListener("click", listener);
  }
  return prevented;
}

// ---------------------------------------------------------------- entry boot

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
  return new URL(raw, "http://localhost").pathname.replace(/\/+$/, "");
}

/** Feature 005 step 003's list route: `GET /api/admin/users` -> `{ "users": [...] }`. */
function isUsersList(input: RequestInfo | URL, init?: RequestInit): boolean {
  const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
  return method === "GET" && requestPath(input) === "/api/admin/users";
}

/** MemoryRouter renders: the users list answers empty; anything else never settles. */
const answerShellRequests: FetchFn = (input, init) =>
  isUsersList(input, init)
    ? Promise.resolve(jsonResponse({ users: [] }, 200))
    : new Promise<Response>(() => {});

/** Booted entry: the users list answers empty; every other request answers as a signed-in admin. */
const answerAdmin: FetchFn = (input, init) =>
  isUsersList(input, init)
    ? Promise.resolve(jsonResponse({ users: [] }, 200))
    : Promise.resolve(jsonResponse({ id: "9007199254740993", username: "mira", role: "admin" }, 200));

async function flush(rounds = 6): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => setImmediate(resolve));
    });
  }
}

/** Evaluates the admin entry at `pathname` (real BrowserRouter, basename `/admin`) as an admin. */
async function bootAdmin(pathname: string): Promise<void> {
  vi.restoreAllMocks();
  vi.resetModules();
  document.body.innerHTML = '<div id="root"></div>';
  window.history.pushState({}, "", pathname);
  stubFetch(answerAdmin);
  const api = await import("../../src/shared/api");
  vi.spyOn(api.documentNavigation, "assign").mockImplementation(() => {});
  await act(async () => {
    await import("../../src/admin/main");
  });
  await flush();
}

// ---------------------------------------------------------------- source scans

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

function readSource(file: string): string {
  return stripComments(readFileSync(file, "utf8"));
}

function adminCodeFiles(): string[] {
  const walk = (dir: string): string[] =>
    readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
      const full = path.join(dir, entry.name);
      return entry.isDirectory() ? walk(full) : [full];
    });
  return walk(ADMIN_SRC).filter((file) => /\.(ts|tsx)$/.test(file));
}

// ===========================================================================
describe("the shell frame", () => {
  it("renders a header with a level-4 title, a navbar and its children in the main region — DoD-6", () => {
    renderShell(new AdminShellState());
    expect(header()).toBeInTheDocument();
    expect(within(header()).getByRole("heading", { level: 4, hidden: true })).toBeInTheDocument();
    expect(navbar()).toBeInTheDocument();
    expect(within(mainRegion()).getByText("shell child zq-55")).toBeInTheDocument();
  });

  it("the navbar lists the three nav items by their labels, in order — DoD-6", () => {
    renderShell(new AdminShellState());
    const links = within(navbar()).getAllByRole("link", { hidden: true });
    expect(links).toHaveLength(3);
    NAV_LABELS.forEach((label, index) => {
      expect(links[index]).toHaveTextContent(label);
      expect(navLink(label)).toBe(links[index]);
    });
  });

  it("the Burger toggles the navbar through the shell state — DoD-6", () => {
    const shell = new AdminShellState();
    renderShell(shell);
    expect(shell.navbarOpened).toBe(false);
    fireEvent.click(burger());
    expect(shell.navbarOpened).toBe(true);
    fireEvent.click(burger());
    expect(shell.navbarOpened).toBe(false);
  });

  it("the Burger reflects a state change made outside the component — DoD-6", () => {
    const shell = new AdminShellState();
    renderShell(shell);
    act(() => {
      runInAction(() => {
        shell.navbarOpened = true;
      });
    });
    fireEvent.click(burger());
    expect(shell.navbarOpened).toBe(false);
  });

  it.each(NAV_LABELS)("selecting the %s nav item closes an open navbar — DoD-6", (label) => {
    const shell = new AdminShellState();
    renderShell(shell, "/nope");
    act(() => {
      runInAction(() => {
        shell.navbarOpened = true;
      });
    });
    clickReportingPrevented(navLink(label));
    expect(shell.navbarOpened).toBe(false);
  });

  it("selecting a nav item leaves a closed navbar closed (it closes, not toggles) — DoD-6", () => {
    const shell = new AdminShellState();
    renderShell(shell);
    clickReportingPrevented(navLink("Database"));
    expect(shell.navbarOpened).toBe(false);
  });

  it("selecting a nav item navigates the router to its path — DoD-6", () => {
    renderShell(new AdminShellState());
    clickReportingPrevented(navLink("LLM Servers"));
    expect(currentPath()).toBe("/llm-servers");
  });

  it("inside the app, the Burger opens the navbar and selecting a nav item closes it — DoD-6", () => {
    renderApp("/");
    const live = liveShellAfterOpening();
    clickReportingPrevented(navLink("Database"));
    expect(live.navbarOpened).toBe(false);
    expect(currentPath()).toBe("/database");
  });
});

// ===========================================================================
describe("the back-to-app control", () => {
  it("is exactly one real anchor in the header whose href is / — DoD-7", () => {
    renderShell(new AdminShellState(), "/database");
    const anchors = anchorsTo(header(), "/");
    expect(anchors).toHaveLength(1);
    expect(anchors[0].tagName).toBe("A");
  });

  it("a click on it is left to the browser: not intercepted and no router navigation — DoD-7", () => {
    renderApp("/database");
    const [anchor] = anchorsTo(header(), "/");
    expect(clickReportingPrevented(anchor)).toBe(false);
    expect(currentPath()).toBe("/database");
  });

  it("under the entry's /admin basename its href is still / while in-entry links carry /admin — DoD-7", async () => {
    await bootAdmin("/admin/llm-servers");
    const anchors = anchorsTo(header(), "/");
    expect(anchors).toHaveLength(1);
    expect(anchors[0].tagName).toBe("A");
    expect(navLink("Users").getAttribute("href") ?? "").toMatch(/^\/admin\/?$/);
    expect(navLink("Database").getAttribute("href")).toBe("/admin/database");
  });
});

// ===========================================================================
describe("the header carries no user menu, no sign-out and no colour-scheme toggle", () => {
  it("the Burger is the header's only button — DoD-8", () => {
    renderApp("/");
    expect(headerButtons()).toHaveLength(1);
  });

  it("nothing in the header opens a menu or popup — DoD-8", () => {
    renderApp("/");
    expect(header().querySelectorAll("[aria-haspopup]")).toHaveLength(0);
    expect(within(header()).queryAllByRole("menu", { hidden: true })).toHaveLength(0);
    expect(within(header()).queryAllByRole("menuitem", { hidden: true })).toHaveLength(0);
  });

  it("no sign-out control anywhere in the admin area — DoD-8", () => {
    renderApp("/");
    for (const role of ["button", "link", "menuitem"] as const) {
      expect(screen.queryAllByRole(role, { name: SIGN_OUT_NAME, hidden: true })).toHaveLength(0);
    }
    expect(screen.queryByText(SIGN_OUT_NAME)).toBeNull();
  });

  it("no colour-scheme control in the header — DoD-8", () => {
    renderApp("/");
    for (const role of ["button", "switch", "checkbox", "radio", "link"] as const) {
      expect(within(header()).queryAllByRole(role, { name: COLOR_SCHEME_NAME, hidden: true })).toHaveLength(0);
    }
  });

  it("the header's only links are the one back-to-app anchor — DoD-8", () => {
    renderApp("/");
    const links = within(header()).queryAllByRole("link", { hidden: true });
    expect(links.map((link) => link.getAttribute("href"))).toEqual(["/"]);
  });
});

// ===========================================================================
describe("the route table is flat and the shell sits above it", () => {
  it("AdminApp declares exactly four route elements: /, /llm-servers, /database and * — DoD-9", () => {
    const source = readSource(ADMIN_APP_SOURCE);
    expect(source.match(/<Route(?![A-Za-z])/g) ?? []).toHaveLength(4);
    const paths = Array.from(source.matchAll(/\bpath\s*=\s*\{?\s*["'`]([^"'`]+)["'`]/g), (m) => m[1]);
    expect([...paths].sort()).toEqual(["*", "/", "/database", "/llm-servers"]);
  });

  it("the shell is not a route element and renders no routes of its own — DoD-9", () => {
    expect(readSource(ADMIN_APP_SOURCE)).not.toMatch(/element\s*=\s*\{\s*<AdminShell\b/);
    expect(readSource(ADMIN_SHELL_SOURCE)).not.toMatch(/<Route(?![A-Za-z])/);
  });

  it("no Outlet anywhere in the admin entry — DoD-9", () => {
    const offenders = adminCodeFiles().filter((file) => /\b(?:Outlet|useOutlet)\b/.test(readSource(file)));
    expect(offenders.map((file) => path.relative(FRONTEND_ROOT, file).split(path.sep).join("/"))).toEqual([]);
  });

  it.each(["/", "/llm-servers", "/database", "/nope"])(
    "at %s the one shell frame wraps the header, the navbar and the routed content — DoD-9",
    (pathname) => {
      renderApp(pathname);
      const marker = onlyMarker();
      expect(marker.contains(header())).toBe(true);
      expect(marker.contains(navbar())).toBe(true);
      expect(marker.contains(mainRegion())).toBe(true);
      expect((mainRegion().textContent ?? "").trim().length).toBeGreaterThan(0);
    },
  );

  it("the shell frame is the same element across every route — DoD-9", () => {
    renderApp("/");
    const marker = onlyMarker();
    const shellHeader = header();
    for (const pathname of ["/llm-servers", "/database", "/nope", "/"]) {
      routerNavigate(pathname);
      expect(currentPath()).toBe(pathname);
      expect(onlyMarker()).toBe(marker);
      expect(header()).toBe(shellHeader);
    }
  });
});

// ===========================================================================
describe("the declared-but-unbuilt rows and unknown paths render the 404", () => {
  it.each(["/llm-servers", "/database", "/nope", "/deeply/nested/unknown"])(
    "%s renders the 404 element — DoD-10",
    (pathname) => {
      renderApp(pathname);
      expect(mainRegion().textContent ?? "").toMatch(NOT_FOUND_TEXT);
    },
  );

  it("/ renders the Users placeholder, not the 404 — DoD-10", () => {
    renderApp("/");
    const text = mainRegion().textContent ?? "";
    expect(text).toMatch(USERS_TEXT);
    expect(text).not.toMatch(NOT_FOUND_TEXT);
  });

  it("the nav still lists the two unbuilt rows while they render the 404 — DoD-10", () => {
    renderApp("/database");
    expect(navLink("LLM Servers")).toBeInTheDocument();
    expect(navLink("Database")).toBeInTheDocument();
    expect(isHighlighted(navLink("Database"))).toBe(true);
  });

  it.each(["/admin/llm-servers", "/admin/database", "/admin/nope"])(
    "in the booted entry, %s renders the 404 element — DoD-10",
    async (pathname) => {
      await bootAdmin(pathname);
      expect(mainRegion().textContent ?? "").toMatch(NOT_FOUND_TEXT);
    },
  );
});

// ===========================================================================
describe("the 404 element", () => {
  it("states that the page does not exist and links back to the Users page — DoD-11", () => {
    renderNotFound();
    expect(document.body.textContent ?? "").toMatch(NOT_FOUND_TEXT);
    const backLinks = anchorsTo(document.body, "/");
    expect(backLinks.length).toBeGreaterThanOrEqual(1);
  });

  it("its link back goes to the Users page through the router — DoD-11", () => {
    renderNotFound();
    const [back] = anchorsTo(document.body, "/");
    expect(clickReportingPrevented(back)).toBe(true);
    expect(currentPath()).toBe("/");
    expect(navigate).not.toHaveBeenCalled();
  });

  it("performs no automatic redirect — DoD-11", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
    renderNotFound("/nope");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(currentPath()).toBe("/nope");
    expect(document.body.textContent ?? "").toMatch(NOT_FOUND_TEXT);
    expect(navigate).not.toHaveBeenCalled();
  });

  it("inside the app, the 404's link back lands on the Users page — DoD-11", () => {
    renderApp("/nope");
    const [back] = anchorsTo(mainRegion(), "/");
    expect(back).toBeDefined();
    clickReportingPrevented(back);
    expect(currentPath()).toBe("/");
    const text = mainRegion().textContent ?? "";
    expect(text).toMatch(USERS_TEXT);
    expect(text).not.toMatch(NOT_FOUND_TEXT);
    expect(isHighlighted(navLink("Users"))).toBe(true);
  });

  it("inside the app, an unknown path stays put with no redirect — DoD-11", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
    renderApp("/nope");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(currentPath()).toBe("/nope");
    expect(mainRegion().textContent ?? "").toMatch(NOT_FOUND_TEXT);
    expect(navigate).not.toHaveBeenCalled();
  });
});

// ===========================================================================
describe("in-entry navigation moves the highlight without reloading the document", () => {
  it("at / only Users is highlighted — DoD-12", () => {
    renderApp("/");
    expect(NAV_LABELS.map((label) => isHighlighted(navLink(label)))).toEqual([true, false, false]);
  });

  it("at /database only Database is highlighted — DoD-12", () => {
    renderApp("/database");
    expect(NAV_LABELS.map((label) => isHighlighted(navLink(label)))).toEqual([false, false, true]);
  });

  it("clicking Database then Users moves the highlight through the router — DoD-12", () => {
    renderApp("/");
    const marker = onlyMarker();

    expect(clickReportingPrevented(navLink("Database"))).toBe(true);
    expect(currentPath()).toBe("/database");
    expect(NAV_LABELS.map((label) => isHighlighted(navLink(label)))).toEqual([false, false, true]);

    expect(clickReportingPrevented(navLink("Users"))).toBe(true);
    expect(currentPath()).toBe("/");
    expect(NAV_LABELS.map((label) => isHighlighted(navLink(label)))).toEqual([true, false, false]);

    // same document, same mounted frame, no document navigation
    expect(onlyMarker()).toBe(marker);
    expect(navigate).not.toHaveBeenCalled();
  });

  it("a descendant path highlights its parent item and not Users — DoD-12", () => {
    renderApp("/llm-servers/anything");
    expect(NAV_LABELS.map((label) => isHighlighted(navLink(label)))).toEqual([false, true, false]);
  });

  it("an unknown path highlights no item — DoD-12", () => {
    renderApp("/nope");
    expect(NAV_LABELS.map((label) => isHighlighted(navLink(label)))).toEqual([false, false, false]);
  });

  it("the back-to-app anchor, unlike the nav, is not taken by the router — DoD-12", () => {
    renderApp("/database");
    expect(clickReportingPrevented(navLink("Users"))).toBe(true);
    expect(clickReportingPrevented(anchorsTo(header(), "/")[0])).toBe(false);
    expect(currentPath()).toBe("/");
  });
});

// ===========================================================================
describe("the data-entry marker is on every admin route", () => {
  it.each(["/", "/llm-servers", "/database", "/nope", "/deeply/nested/unknown"])(
    "at %s exactly one admin marker is rendered — DoD-13",
    (pathname) => {
      renderApp(pathname);
      onlyMarker();
    },
  );

  it("the marker persists, once, across route changes — DoD-13", () => {
    renderApp("/");
    for (const pathname of ["/llm-servers", "/nope", "/database", "/"]) {
      routerNavigate(pathname);
      onlyMarker();
    }
  });

  it.each(["/admin/", "/admin", "/admin/llm-servers", "/admin/database", "/admin/nope"])(
    "the booted entry at %s renders exactly one admin marker inside #root — DoD-13",
    async (pathname) => {
      await bootAdmin(pathname);
      expect(markerValues()).toEqual(["admin"]);
      expect(document.getElementById("root")?.querySelector('[data-entry="admin"]')).not.toBeNull();
    },
  );
});

// ===========================================================================
describe("one shell state per mount", () => {
  it("mounting constructs the shell state and binds the rendered shell to it — DoD-14", () => {
    renderApp("/");
    expect(constructed.length).toBeGreaterThanOrEqual(1);
    const live = liveShellAfterOpening();
    fireEvent.click(burger());
    expect(live.navbarOpened).toBe(false);
  });

  it("navigating between routes constructs no second shell state — DoD-14", () => {
    renderApp("/");
    const afterMount = constructed.length;
    expect(afterMount).toBeGreaterThanOrEqual(1);
    for (const pathname of ["/database", "/llm-servers", "/nope", "/"]) {
      routerNavigate(pathname);
      expect(constructed.length).toBe(afterMount);
    }
    clickReportingPrevented(navLink("Database"));
    clickReportingPrevented(navLink("Users"));
    expect(constructed.length).toBe(afterMount);
  });

  it("the navbar's opened flag survives a route change — DoD-14", () => {
    renderApp("/nope");
    const live = liveShellAfterOpening();
    routerNavigate("/database");
    expect(currentPath()).toBe("/database");
    expect(live.navbarOpened).toBe(true);
    routerNavigate("/");
    expect(live.navbarOpened).toBe(true);
    // the rendered Burger is still bound to the same instance
    fireEvent.click(burger());
    expect(live.navbarOpened).toBe(false);
  });

  it("following the 404's link back keeps the opened flag — DoD-14", () => {
    renderApp("/nope");
    const live = liveShellAfterOpening();
    const afterOpen = constructed.length;
    clickReportingPrevented(anchorsTo(mainRegion(), "/")[0]);
    expect(currentPath()).toBe("/");
    expect(live.navbarOpened).toBe(true);
    expect(constructed.length).toBe(afterOpen);
  });
});
