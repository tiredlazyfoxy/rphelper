// Feature 008, step 004 — the in-entry route table (DoD-10, DoD-11).
// The shell component's own clauses (DoD-1..DoD-9) live in WorkspaceShell.test.tsx;
// DoD-12 and DoD-13 are [manual/live] and carry no test.
// All six routes are declared, flat, with the shell above them and an **empty** centre
// (D5); an undeclared path renders "Page not found" inside that same shell. `App` creates
// no router, so every render here supplies a MemoryRouter (004.context.md).
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { App } from "../../src/app/App";
import { AppProviders } from "../../src/shared/AppProviders";
import type { CurrentUser } from "../../src/shared/currentUser";

const NAV_NAME = /^workspace navigation$/i;
const NOT_FOUND_TEXT = /page not found/i;

const DECLARED_ROUTES = [
  "/",
  "/sessions/1",
  "/characters/1",
  "/characters/new",
  "/settings",
  "/search",
];

const UNDECLARED_ROUTE = "/nope";

const USER: CurrentUser = { id: "9007199254740993", username: "zmiraqua", role: "roleplayer" };

function renderApp(initialPath: string) {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={[initialPath]}>
        <App user={USER} storage={null} />
      </MemoryRouter>
    </AppProviders>,
  );
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

// ---------------------------------------------------------------------------
describe("every declared route is the same shell around an empty centre (D5)", () => {
  it.each(DECLARED_ROUTES)("renders the shell at %s — DoD-10", (path) => {
    renderApp(path);

    expect(navElement()).toBeInTheDocument();
    expect(mainElement()).toBeInTheDocument();
  });

  it.each(DECLARED_ROUTES)("renders no centre content at %s — DoD-10", (path) => {
    renderApp(path);

    expect(mainText()).toBe("");
    expect(within(mainElement()).queryByText(NOT_FOUND_TEXT)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("an undeclared path is a 404 inside the same shell (D5)", () => {
  it("renders the shell with Page not found inside the main region — DoD-11", () => {
    renderApp(UNDECLARED_ROUTE);

    expect(navElement()).toBeInTheDocument();
    expect(within(mainElement()).getByText(NOT_FOUND_TEXT)).toBeInTheDocument();
  });
});
