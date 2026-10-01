// Feature 008, step 003 — the user menu (DoD-1..DoD-6, DoD-9).
// The logout effect's own clauses (DoD-6..DoD-8) live in logout.test.ts;
// DoD-10..DoD-12 are [manual/live] and carry no test.
// The accessible names "User menu", "Settings", "Admin area" and "Log out" are the contract
// (003.user-menu.md); controls are found by those names and never by structure.
import type * as React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { UserMenu } from "../../src/app/UserMenu";
import { documentNavigation } from "../../src/shared/api";
import { AppProviders } from "../../src/shared/AppProviders";
import type { CurrentUser } from "../../src/shared/currentUser";

const TRIGGER_NAME = /^user menu$/i;
const SETTINGS_ITEM = /^settings$/i;
const ADMIN_ITEM = /^admin area$/i;
const LOGOUT_ITEM = /^log out$/i;

/** Distinctive enough that its absence on the rail is meaningful. */
const USERNAME = "zmiraqua";
const USERNAME_TEXT = /^zmiraqua$/;

const ADMIN_HREF = "/admin";
const SETTINGS_PATH = "/settings";
const LOGOUT_PATH = "/api/auth/logout";
const LOGIN_PATH = "/login";

const ROLES: Array<CurrentUser["role"]> = ["roleplayer", "admin"];
const COMPACT_MODES: boolean[] = [false, true];

type User = ReturnType<typeof userEvent.setup>;

/** Mantine's floating layers set pointer-events; the house workaround for user-event. */
function newUser(): User {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

function identity(role: CurrentUser["role"]): CurrentUser {
  return { id: "9007199254740993", username: USERNAME, role };
}

function LocationProbe(): React.JSX.Element {
  const location = useLocation();
  return <output data-testid="probe-location">{location.pathname}</output>;
}

function currentPath(): string {
  return screen.getByTestId("probe-location").textContent ?? "";
}

function renderMenu(account: CurrentUser, compact: boolean, initialPath = "/") {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={[initialPath]}>
        <UserMenu user={account} compact={compact} />
        <LocationProbe />
      </MemoryRouter>
    </AppProviders>,
  );
}

function trigger(): HTMLElement {
  return screen.getByRole("button", { name: TRIGGER_NAME });
}

/** The menu item carrying `name`: the activatable element its label sits in. */
function item(name: RegExp): HTMLElement {
  const label = screen.getByText(name);
  return label.closest<HTMLElement>("a, button, [role='menuitem']") ?? label;
}

/** Opens the dropdown (a portal, mounted only while open) and waits for its content. */
async function openMenu(user: User): Promise<void> {
  await user.click(trigger());
  await screen.findByText(LOGOUT_ITEM);
}

/** Stops jsdom from acting on a real anchor's default navigation, after React has handled it. */
function suppressDefaultNavigation(): () => void {
  const onClick = (event: MouseEvent): void => {
    event.preventDefault();
  };
  window.addEventListener("click", onClick);
  return () => {
    window.removeEventListener("click", onClick);
  };
}

function elementsWithAdminHref(): Element[] {
  return Array.from(document.querySelectorAll(`[href="${ADMIN_HREF}"]`));
}

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

function stubFetch(impl: FetchFn) {
  const mock = vi.fn<FetchFn>(impl);
  vi.stubGlobal("fetch", mock);
  return mock;
}

function requestPath(input: RequestInfo | URL): string {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost").pathname;
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function requests(mock: ReturnType<typeof stubFetch>): Array<{ path: string; method: string }> {
  return mock.mock.calls.map(([input, init]) => ({
    path: requestPath(input),
    method: requestMethod(input, init),
  }));
}

let navigate: MockInstance<(url: string) => void>;

beforeEach(() => {
  navigate = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
describe("opening the menu from the User menu trigger", () => {
  it.each(ROLES)("a %s sees Settings and Log out — DoD-1", async (role) => {
    const user = newUser();
    renderMenu(identity(role), false);

    await user.click(trigger());

    expect(await screen.findByText(SETTINGS_ITEM)).toBeInTheDocument();
    expect(await screen.findByText(LOGOUT_ITEM)).toBeInTheDocument();
  });

  it("an administrator sees an Admin area item — DoD-2", async () => {
    const user = newUser();
    renderMenu(identity("admin"), false);

    await openMenu(user);

    expect(screen.getByText(ADMIN_ITEM)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
describe("a roleplayer has no admin entry point (US-093.AC-2)", () => {
  it("the open menu holds no Admin area item at all — DoD-3", async () => {
    const user = newUser();
    renderMenu(identity("roleplayer"), false);

    await openMenu(user);

    expect(screen.queryByText(ADMIN_ITEM)).toBeNull();
    expect(screen.queryByRole("menuitem", { name: ADMIN_ITEM })).toBeNull();
    expect(screen.queryByRole("link", { name: ADMIN_ITEM })).toBeNull();
    expect(screen.queryByRole("button", { name: ADMIN_ITEM })).toBeNull();
  });

  it("the rendered output holds no element with href /admin — DoD-3", async () => {
    const user = newUser();
    renderMenu(identity("roleplayer"), false);
    expect(elementsWithAdminHref()).toEqual([]);

    await openMenu(user);

    expect(elementsWithAdminHref()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("Admin area is a real anchor to the other document (US-093.AC-1)", () => {
  it("is an anchor element whose href is exactly /admin — DoD-4", async () => {
    const user = newUser();
    renderMenu(identity("admin"), false);

    await openMenu(user);
    const adminItem = item(ADMIN_ITEM);

    expect(adminItem.tagName.toLowerCase()).toBe("a");
    expect(adminItem.getAttribute("href")).toBe(ADMIN_HREF);
  });

  it("activating it leaves the in-entry router's location unchanged — DoD-4", async () => {
    const user = newUser();
    const restore = suppressDefaultNavigation();
    try {
      renderMenu(identity("admin"), false);
      await openMenu(user);
      expect(currentPath()).toBe("/");

      await user.click(item(ADMIN_ITEM));

      expect(currentPath()).toBe("/");
    } finally {
      restore();
    }
  });
});

// ---------------------------------------------------------------------------
describe("Settings is an in-entry router navigation (UC-071)", () => {
  it("choosing it moves the in-entry router to /settings — DoD-5", async () => {
    const user = newUser();
    renderMenu(identity("roleplayer"), false);
    await openMenu(user);
    expect(currentPath()).toBe("/");

    await user.click(item(SETTINGS_ITEM));

    await waitFor(() => {
      expect(currentPath()).toBe(SETTINGS_PATH);
    });
  });

  it("choosing it performs no document navigation — DoD-5", async () => {
    const user = newUser();
    renderMenu(identity("roleplayer"), false);
    await openMenu(user);

    await user.click(item(SETTINGS_ITEM));

    await waitFor(() => {
      expect(currentPath()).toBe(SETTINGS_PATH);
    });
    expect(navigate).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("Log out ends the session and lands on /login (US-091.AC-1)", () => {
  it("posts to /api/auth/logout and then navigates the document to exactly /login — DoD-6", async () => {
    const fetchMock = stubFetch(() => Promise.resolve(new Response(null, { status: 204 })));
    const user = newUser();
    renderMenu(identity("roleplayer"), false);
    await openMenu(user);

    await user.click(item(LOGOUT_ITEM));

    await waitFor(() => {
      expect(navigate.mock.calls).toEqual([[LOGIN_PATH]]);
    });
    expect(requests(fetchMock)).toEqual([{ path: LOGOUT_PATH, method: "POST" }]);
  });
});

// ---------------------------------------------------------------------------
describe("the trigger expanded and on the rail (US-090.AC-1)", () => {
  it("expanded, it shows the username as visible text — DoD-9", () => {
    renderMenu(identity("roleplayer"), false);

    expect(screen.getByText(USERNAME_TEXT)).toBeVisible();
  });

  it("compact, it shows no username text — DoD-9", () => {
    renderMenu(identity("roleplayer"), true);

    expect(screen.queryByText(USERNAME_TEXT)).toBeNull();
  });

  it.each(COMPACT_MODES)("it is found by the accessible name User menu, compact %s — DoD-9", (compact) => {
    renderMenu(identity("roleplayer"), compact);

    expect(trigger()).toBeInTheDocument();
  });

  it.each(COMPACT_MODES)("it opens the same menu, compact %s — DoD-9", async (compact) => {
    const user = newUser();
    renderMenu(identity("admin"), compact);

    await openMenu(user);

    expect(screen.getByText(SETTINGS_ITEM)).toBeInTheDocument();
    expect(screen.getByText(ADMIN_ITEM)).toBeInTheDocument();
    expect(screen.getByText(LOGOUT_ITEM)).toBeInTheDocument();
  });
});
