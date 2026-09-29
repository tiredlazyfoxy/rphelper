// Feature 002, step 005 — AppProviders (DoD-4..DoD-8).
// DoD-16 (stylesheet import order) and DoD-17 are [manual/live] and have no test here.
import { readFileSync } from "node:fs";
import path from "node:path";
import { Button, useMantineTheme } from "@mantine/core";
import { Notifications, notifications } from "@mantine/notifications";
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import * as appProvidersModule from "../../src/shared/AppProviders";
import { AppProviders } from "../../src/shared/AppProviders";
import { theme } from "../../src/shared/theme";

// Partial mock: the real outlet still renders (so notifications become visible);
// the wrapper only records the props AppProviders configured it with (DoD-7).
vi.mock("@mantine/notifications", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@mantine/notifications")>();
  const { createElement } = await import("react");
  return {
    ...actual,
    Notifications: vi.fn((props: Record<string, unknown>) =>
      createElement(actual.Notifications, props as never),
    ),
  };
});

const notificationsSpy = Notifications as unknown as Mock;

const STORAGE_KEY = "rphelper.color-scheme";
const FRONTEND_ROOT = path.resolve(__dirname, "../..");

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

function resolvedScheme(): string | null {
  return document.documentElement.getAttribute("data-mantine-color-scheme");
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-mantine-color-scheme");
  notificationsSpy.mockClear();
});

afterEach(() => {
  vi.useRealTimers();
  act(() => {
    notifications.clean();
  });
  window.localStorage.clear();
});

// ---------------------------------------------------------------------------
describe("colour scheme resolution", () => {
  it("resolves to dark with nothing persisted — DoD-4", async () => {
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
    render(
      <AppProviders>
        <span>content</span>
      </AppProviders>,
    );
    await waitFor(() => expect(resolvedScheme()).toBe("dark"));
  });

  it("resolves to a persisted light scheme rather than the default — DoD-5", async () => {
    window.localStorage.setItem(STORAGE_KEY, "light");
    render(
      <AppProviders>
        <span>content</span>
      </AppProviders>,
    );
    await waitFor(() => expect(resolvedScheme()).toBe("light"));
  });

  it("resolves to a persisted dark scheme — DoD-5", async () => {
    window.localStorage.setItem(STORAGE_KEY, "dark");
    render(
      <AppProviders>
        <span>content</span>
      </AppProviders>,
    );
    await waitFor(() => expect(resolvedScheme()).toBe("dark"));
  });
});

// ---------------------------------------------------------------------------
describe("children and theme", () => {
  it("renders its children — DoD-6", () => {
    render(
      <AppProviders>
        <p>child content probe</p>
      </AppProviders>,
    );
    expect(screen.getByText("child content probe")).toBeInTheDocument();
  });

  it("a Mantine component among the children renders styled by Mantine — DoD-6", () => {
    render(
      <AppProviders>
        <Button>Themed probe</Button>
      </AppProviders>,
    );
    const button = screen.getByRole("button", { name: "Themed probe" });
    expect(button.closest(".mantine-Button-root")).not.toBeNull();
  });

  it("the theme from shared/theme.ts is in effect for the children — DoD-6", () => {
    let seen: ReturnType<typeof useMantineTheme> | null = null;
    function ThemeProbe() {
      seen = useMantineTheme();
      return <span>probe</span>;
    }
    render(
      <AppProviders>
        <ThemeProbe />
      </AppProviders>,
    );
    expect(seen).not.toBeNull();
    const resolved = seen as unknown as Record<string, unknown>;
    const setTokens = Object.entries(theme).filter(([, value]) => value !== undefined);
    expect(setTokens.length).toBeGreaterThan(0);
    for (const [key, value] of setTokens) {
      expect({ key, value: resolved[key] }).toEqual({ key, value });
    }
  });

  it("the theme's font family reaches Mantine's CSS variables — DoD-6", () => {
    render(
      <AppProviders>
        <Button>Themed probe</Button>
      </AppProviders>,
    );
    const css = Array.from(document.querySelectorAll("style"))
      .map((style) => style.textContent ?? "")
      .filter((text) => text.includes("--mantine-"))
      .join("\n");
    const fontMatch = /--mantine-font-family:\s*([^;}]+)[;}]/.exec(css);
    expect(fontMatch).not.toBeNull();
    expect(fontMatch?.[1].trim()).toBe(theme.fontFamily);
  });
});

// ---------------------------------------------------------------------------
describe("notifications outlet", () => {
  it("mounts Mantine's notifications outlet configured with autoClose 5000 — DoD-7", () => {
    render(
      <AppProviders>
        <span>content</span>
      </AppProviders>,
    );
    expect(notificationsSpy).toHaveBeenCalled();
    const propsSeen = notificationsSpy.mock.calls.map((call) => call[0] as Record<string, unknown>);
    expect(propsSeen.every((props) => props.autoClose === 5000)).toBe(true);
  });

  it("a notification raised while mounted becomes visible — DoD-7", async () => {
    render(
      <AppProviders>
        <span>content</span>
      </AppProviders>,
    );
    act(() => {
      notifications.show({ message: "Outlet probe reason" });
    });
    expect(await screen.findByText("Outlet probe reason")).toBeInTheDocument();
  });

  it("a raised notification is still visible before 5000 ms and gone after — DoD-7", () => {
    vi.useFakeTimers();
    render(
      <AppProviders>
        <span>content</span>
      </AppProviders>,
    );
    act(() => {
      notifications.show({ message: "Timed probe reason" });
    });
    act(() => {
      vi.advanceTimersByTime(50);
    });
    expect(screen.getByText("Timed probe reason")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(4400);
    });
    expect(screen.getByText("Timed probe reason")).toBeInTheDocument();

    // Past 5000 ms plus generous room for the outlet's exit transition.
    act(() => {
      vi.advanceTimersByTime(2500);
    });
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.queryByText("Timed probe reason")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("no props but children, no context of its own", () => {
  it("the module exports exactly one thing, the AppProviders component — DoD-8", () => {
    expect(Object.keys(appProvidersModule)).toEqual(["AppProviders"]);
    expect(typeof AppProviders).toBe("function");
  });

  it("declares at most the one props parameter — DoD-8", () => {
    expect(AppProviders.length).toBeLessThanOrEqual(1);
    // Compile-time half (checked by `npm run typecheck`): any prop but children is rejected.
    void (() => (
      // @ts-expect-error — AppProviders takes no props but children (DoD-8)
      <AppProviders store={{}}>
        <span />
      </AppProviders>
    ));
  });

  it("renders with children alone — DoD-8", () => {
    render(
      <AppProviders>
        <span>only children</span>
      </AppProviders>,
    );
    expect(screen.getByText("only children")).toBeInTheDocument();
  });

  it("creates and provides no React context of its own — DoD-8", () => {
    const source = stripComments(
      readFileSync(path.join(FRONTEND_ROOT, "src/shared/AppProviders.tsx"), "utf8"),
    );
    expect(source).not.toMatch(/\bcreateContext\b/);
    expect(source).not.toMatch(/\.Provider\b/);
    expect(source).not.toMatch(/\buseContext\b/);
  });
});
