// Feature 002, step 005 — the colour-scheme module (DoD-1, DoD-2, DoD-3).
import { readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  COLOR_SCHEME_STORAGE_KEY,
  DEFAULT_COLOR_SCHEME,
  colorSchemeManager,
} from "../../src/shared/colorScheme";

const FRONTEND_ROOT = path.resolve(__dirname, "../..");

/** The four source files this step writes. */
const STEP_FILES = [
  "src/shared/colorScheme.ts",
  "src/shared/AppProviders.tsx",
  "src/shared/ColorSchemeToggle.tsx",
  "src/shared/notifyFailure.ts",
];

function readSource(relative: string): string {
  return readFileSync(path.join(FRONTEND_ROOT, relative), "utf8");
}

/** Removes block and line comments so a comment cannot trip a scan. */
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  window.localStorage.clear();
});

describe("the storage key", () => {
  it("is exactly rphelper.color-scheme — DoD-1", () => {
    expect(COLOR_SCHEME_STORAGE_KEY).toBe("rphelper.color-scheme");
  });

  it("is not the workspace-layout key — DoD-1", () => {
    expect(COLOR_SCHEME_STORAGE_KEY).not.toBe("rphelper.workspace-layout");
  });

  it("is the key the manager persists under — DoD-1, DoD-3", () => {
    colorSchemeManager.set("light");
    expect(window.localStorage.getItem("rphelper.color-scheme")).toBe("light");
    expect(window.localStorage.getItem("rphelper.workspace-layout")).toBeNull();
  });

  it("is the key the manager reads from — DoD-1, DoD-3", () => {
    window.localStorage.setItem("rphelper.color-scheme", "light");
    expect(colorSchemeManager.get("dark")).toBe("light");
  });

  it("with nothing persisted, the manager hands back the default it is given — DoD-3", () => {
    expect(colorSchemeManager.get("dark")).toBe("dark");
  });
});

describe("the default scheme", () => {
  it('is "dark" — DoD-2', () => {
    expect(DEFAULT_COLOR_SCHEME).toBe("dark");
  });
});

describe("no hand-rolled storage access", () => {
  // Direct access patterns. The bare word `localStorage` is NOT flagged, because
  // Mantine's own `localStorageColorSchemeManager` identifier contains it.
  const DIRECT_ACCESS: Array<[string, RegExp]> = [
    ["localStorage.<member>", /\blocalStorage\s*\??\.\s*[A-Za-z_$]/],
    ["localStorage[...]", /\blocalStorage\s*\[/],
    ["getItem(", /\bgetItem\s*\(/],
    ["setItem(", /\bsetItem\s*\(/],
    ["removeItem(", /\bremoveItem\s*\(/],
  ];

  it.each(STEP_FILES)("%s performs no direct localStorage read or write — DoD-3", (file) => {
    const source = stripComments(readSource(file));
    const offenders = source
      .split(/\r?\n/)
      .map((line, index) => ({ line, number: index + 1 }))
      .flatMap(({ line, number }) =>
        DIRECT_ACCESS.filter(([, pattern]) => pattern.test(line)).map(
          ([name]) => `${file}:${number} (${name}): ${line.trim()}`,
        ),
      );
    expect(offenders).toEqual([]);
  });
});
