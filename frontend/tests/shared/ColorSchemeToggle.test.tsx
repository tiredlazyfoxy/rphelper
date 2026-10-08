// Feature 002, step 005 — ColorSchemeToggle (DoD-9, DoD-10, DoD-11; persistence also DoD-3).
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import * as toggleModule from "../../src/shared/ColorSchemeToggle";
import { AppProviders } from "../../src/shared/AppProviders";
import { ColorSchemeToggle } from "../../src/shared/ColorSchemeToggle";

const STORAGE_KEY = "rphelper.color-scheme";

function resolvedScheme(): string | null {
  return document.documentElement.getAttribute("data-mantine-color-scheme");
}

function renderToggle() {
  return render(
    <AppProviders>
      <ColorSchemeToggle />
    </AppProviders>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-mantine-color-scheme");
});

afterEach(() => {
  window.localStorage.clear();
});

// ---------------------------------------------------------------------------
describe("flipping the scheme", () => {
  it("flips dark to light, then back to dark — DoD-9", async () => {
    const user = userEvent.setup();
    renderToggle();
    await waitFor(() => expect(resolvedScheme()).toBe("dark"));

    await user.click(screen.getByRole("button"));
    await waitFor(() => expect(resolvedScheme()).toBe("light"));

    await user.click(screen.getByRole("button"));
    await waitFor(() => expect(resolvedScheme()).toBe("dark"));
  });

  it("flips a persisted light scheme to dark — DoD-9", async () => {
    window.localStorage.setItem(STORAGE_KEY, "light");
    const user = userEvent.setup();
    renderToggle();
    await waitFor(() => expect(resolvedScheme()).toBe("light"));

    await user.click(screen.getByRole("button"));
    await waitFor(() => expect(resolvedScheme()).toBe("dark"));
  });

  it("the flipped choice is persisted under the storage key — DoD-9, DoD-3", async () => {
    const user = userEvent.setup();
    renderToggle();
    await waitFor(() => expect(resolvedScheme()).toBe("dark"));

    await user.click(screen.getByRole("button"));
    await waitFor(() => expect(window.localStorage.getItem(STORAGE_KEY)).toBe("light"));

    await user.click(screen.getByRole("button"));
    await waitFor(() => expect(window.localStorage.getItem(STORAGE_KEY)).toBe("dark"));
  });
});

// ---------------------------------------------------------------------------
describe("accessible name is the action", () => {
  it("under dark, the name names switching to light — DoD-10", async () => {
    renderToggle();
    await waitFor(() => expect(resolvedScheme()).toBe("dark"));
    await waitFor(() => expect(screen.getByRole("button", { name: /light/i })).toBeInTheDocument());
  });

  it("under light, the name names switching to dark — DoD-10", async () => {
    window.localStorage.setItem(STORAGE_KEY, "light");
    renderToggle();
    await waitFor(() => expect(resolvedScheme()).toBe("light"));
    await waitFor(() => expect(screen.getByRole("button", { name: /dark/i })).toBeInTheDocument());
  });

  it("the name changes when the scheme changes — DoD-10", async () => {
    const user = userEvent.setup();
    renderToggle();
    const inDark = await screen.findByRole("button", { name: /light/i });
    const darkName = (inDark.getAttribute("aria-label") ?? inDark.textContent ?? "").trim();
    expect(darkName.length).toBeGreaterThan(0);
    expect(inDark).toHaveAccessibleName(darkName);

    await user.click(inDark);
    await waitFor(() => expect(resolvedScheme()).toBe("light"));
    const inLight = await screen.findByRole("button", { name: /dark/i });
    expect(inLight).not.toHaveAccessibleName(darkName);
  });
});

// ---------------------------------------------------------------------------
describe("rendered through IconButton", () => {
  it("exposes an accessible name and a tooltip carrying the same string — DoD-11", async () => {
    const user = userEvent.setup();
    renderToggle();
    const button = await screen.findByRole("button", { name: /light/i });

    await user.hover(button);
    const candidates = await screen.findAllByText(/light/i);
    const tips = candidates.filter((element) => !button.contains(element));
    expect(tips.length).toBeGreaterThan(0);
    const tipText = (tips[tips.length - 1].textContent ?? "").trim();
    expect(tipText.length).toBeGreaterThan(0);
    expect(button).toHaveAccessibleName(tipText);
  });

  it("the tooltip follows the scheme, still equal to the accessible name — DoD-11", async () => {
    window.localStorage.setItem(STORAGE_KEY, "light");
    const user = userEvent.setup();
    renderToggle();
    const button = await screen.findByRole("button", { name: /dark/i });

    await user.hover(button);
    const candidates = await screen.findAllByText(/dark/i);
    const tips = candidates.filter((element) => !button.contains(element));
    expect(tips.length).toBeGreaterThan(0);
    const tipText = (tips[tips.length - 1].textContent ?? "").trim();
    expect(button).toHaveAccessibleName(tipText);
  });

  it('renders its icon at the "main" size (18) inside the button — DoD-11', async () => {
    renderToggle();
    const button = await screen.findByRole("button", { name: /light/i });
    const icon = button.querySelector("svg");
    expect(icon).not.toBeNull();
    expect(icon?.getAttribute("width")).toBe("18");
  });

  it("the module exports exactly one thing, the component — DoD-11", () => {
    expect(Object.keys(toggleModule)).toEqual(["ColorSchemeToggle"]);
  });
});
