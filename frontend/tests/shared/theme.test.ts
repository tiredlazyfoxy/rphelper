// Feature 002, step 002 — the Mantine theme (DoD-5..DoD-8).
import { readFileSync } from "node:fs";
import path from "node:path";
import { Alert, DEFAULT_THEME, MantineProvider } from "@mantine/core";
import { render } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { theme } from "../../src/shared/theme";

const FRONTEND_ROOT = path.resolve(__dirname, "../..");

function readText(relative: string): string {
  return readFileSync(path.join(FRONTEND_ROOT, relative), "utf8");
}

function stripCssComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, "");
}

/** Keys the theme actually sets (a key carrying `undefined` sets nothing). */
function setKeys(): string[] {
  return Object.entries(theme)
    .filter(([, value]) => value !== undefined)
    .map(([key]) => key)
    .sort();
}

describe("theme tokens", () => {
  it("sets exactly primaryColor, fontFamily and defaultRadius — DoD-5", () => {
    expect(setKeys()).toEqual(["defaultRadius", "fontFamily", "primaryColor"]);
  });

  it("sets the primary colour explicitly to Mantine's built-in blue — DoD-5", () => {
    expect(theme.primaryColor).toBe("blue");
  });

  it("sets a non-empty font family — DoD-5", () => {
    expect(typeof theme.fontFamily).toBe("string");
    expect((theme.fontFamily ?? "").trim().length).toBeGreaterThan(0);
  });

  it("sets a default radius — DoD-5", () => {
    const radius: unknown = theme.defaultRadius;
    expect(["string", "number"]).toContain(typeof radius);
    expect(String(radius).trim().length).toBeGreaterThan(0);
  });
});

describe("theme carries no component defaults and no custom palette", () => {
  it("declares no components key — DoD-6", () => {
    expect(Object.prototype.hasOwnProperty.call(theme, "components")).toBe(false);
  });

  it("adds no custom entry to the colour palette — DoD-6", () => {
    const colors = theme.colors ?? {};
    expect(Object.keys(colors)).toEqual([]);
  });

  it("uses a primary colour from Mantine's built-in palette — DoD-6", () => {
    expect(Object.keys(DEFAULT_THEME.colors)).toContain(theme.primaryColor);
  });
});

describe("no remotely-hosted font", () => {
  it("the font family is a plain stack with no URL — DoD-7", () => {
    const family = theme.fontFamily ?? "";
    expect(family).not.toMatch(/url\(/i);
    expect(family).not.toMatch(/https?:/i);
    expect(family).not.toContain("//");
  });

  it.each(["src/global.css", "src/shell.css"])(
    "%s has no @font-face, no url( and no remote URL — DoD-7",
    (file) => {
      const css = stripCssComments(readText(file));
      expect(css).not.toMatch(/@font-face/i);
      expect(css).not.toMatch(/url\(/i);
      expect(css).not.toMatch(/https?:\/\//i);
    },
  );

  it("src/shared/theme.ts has no @font-face and no url( — DoD-7", () => {
    const source = readText("src/shared/theme.ts");
    expect(source).not.toMatch(/@font-face/i);
    expect(source).not.toMatch(/url\(/i);
  });
});

describe("the theme resolves under both colour schemes", () => {
  function renderUnder(scheme: "dark" | "light"): HTMLElement {
    const { container } = render(
      createElement(MantineProvider, {
        theme,
        forceColorScheme: scheme,
        children: createElement(Alert, { children: "Probe" }),
      }),
    );
    return container;
  }

  function mantineStyleText(): string {
    return Array.from(document.querySelectorAll("style"))
      .map((style) => style.textContent ?? "")
      .filter((text) => text.includes("--mantine-"))
      .join("\n");
  }

  it.each(["dark", "light"] as const)(
    "applies the %s scheme to the document — DoD-8",
    (scheme) => {
      renderUnder(scheme);
      expect(document.documentElement.getAttribute("data-mantine-color-scheme")).toBe(
        scheme,
      );
    },
  );

  it.each(["dark", "light"] as const)(
    "renders the component styled by Mantine under %s — DoD-8",
    (scheme) => {
      const container = renderUnder(scheme);
      const root = container.querySelector(".mantine-Alert-root");
      expect(root).not.toBeNull();
      expect(root?.textContent).toContain("Probe");
    },
  );

  it.each(["dark", "light"] as const)(
    "resolves the theme's font token into Mantine's CSS variables under %s — DoD-8",
    (scheme) => {
      renderUnder(scheme);
      const css = mantineStyleText();

      // Mantine only emits variables that differ from its own defaults, so the
      // effective font family is the emitted value when present, else Mantine's
      // default. Either way it must be the theme's font family.
      const fontMatch = /--mantine-font-family:\s*([^;}]+)[;}]/.exec(css);
      const effectiveFont = fontMatch ? fontMatch[1].trim() : DEFAULT_THEME.fontFamily;
      expect(effectiveFont).toBe(theme.fontFamily);

      // Nothing the provider wrote is unresolved.
      expect(css).not.toMatch(/\bundefined\b/);
      expect(css).not.toMatch(/\bNaN\b/);
    },
  );
});
