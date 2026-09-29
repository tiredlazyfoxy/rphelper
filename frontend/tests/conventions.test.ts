// Feature 002, step 006 — convention guards over frontend/src (DoD-11, DoD-12).
// Feature 003, step 004 DoD-11 removed 002/006 DoD-10's pure-data-contract block.
// Every file under frontend/src is read from disk, recursively. Comments are stripped
// before matching so that prose about a rule is not mistaken for a breach of it.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const FRONTEND_ROOT = path.resolve(__dirname, "..");
const SRC_ROOT = path.join(FRONTEND_ROOT, "src");

function allFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    return entry.isDirectory() ? allFiles(full) : [full];
  });
}

function relative(file: string): string {
  return path.relative(FRONTEND_ROOT, file).split(path.sep).join("/");
}

function codeFiles(): string[] {
  return allFiles(SRC_ROOT).filter((file) => /\.(ts|tsx)$/.test(file));
}

function cssFiles(): string[] {
  return allFiles(SRC_ROOT).filter((file) => /\.css$/.test(file));
}

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

function lineOf(source: string, index: number): number {
  return source.slice(0, index).split(/\r?\n/).length;
}

/** `file:line — rule` for every match of every rule, over comment-stripped source. */
function scan(files: string[], rules: Array<[string, RegExp]>): string[] {
  const offences: string[] = [];
  for (const file of files) {
    const source = stripComments(readFileSync(file, "utf8"));
    for (const [rule, pattern] of rules) {
      const global = new RegExp(pattern.source, pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`);
      for (const match of source.matchAll(global)) {
        offences.push(`${relative(file)}:${lineOf(source, match.index ?? 0)} — ${rule}`);
      }
    }
  }
  return offences;
}

it("the scans see the source tree — DoD-11, DoD-12", () => {
  const files = codeFiles().map(relative);
  expect(files).toEqual(expect.arrayContaining(["src/shared/notifyFailure.ts", "src/app/main.tsx"]));
});

// The pure-data-contract clause (002/006 DoD-10: no makeAutoObservable, no *Draft.ts module,
// no page-store class) was deleted by feature 003, step 004 (DoD-11; 003 context.md D14):
// 003 creates the project's first store. It is deliberately not replaced — from 003 on the
// store convention is review-enforced. The styling and notification scans below stay.

// ---------------------------------------------------------------------------
describe("no forbidden styling mechanism", () => {
  it("no Tailwind directive in any stylesheet under frontend/src — DoD-11", () => {
    const rules: Array<[string, RegExp]> = [
      ["@tailwind directive", /@tailwind\b/],
      ["@apply directive", /@apply\b/],
      ["@config directive", /@config\b/],
      ["tailwindcss import", /@import\s+(?:url\(\s*)?["']tailwindcss/],
    ];
    expect(scan(cssFiles(), rules)).toEqual([]);
  });

  it("no Tailwind import from any module under frontend/src — DoD-11", () => {
    expect(scan(codeFiles(), [["tailwindcss import", /["']tailwindcss(?:\/[^"']*)?["']/]])).toEqual([]);
  });

  it("no .module.css import anywhere under frontend/src — DoD-11", () => {
    const rules: Array<[string, RegExp]> = [
      ["CSS module import", /["'][^"']*\.module\.(?:css|scss|sass|less)["']/],
    ];
    expect(scan(codeFiles(), rules)).toEqual([]);
    const moduleSheets = allFiles(SRC_ROOT)
      .filter((file) => /\.module\.(?:css|scss|sass|less)$/.test(file))
      .map(relative);
    expect(moduleSheets).toEqual([]);
  });

  it("no styled-components import anywhere under frontend/src — DoD-11", () => {
    const rules: Array<[string, RegExp]> = [
      ["styled-components import", /["']styled-components(?:\/[^"']*)?["']/],
    ];
    expect(scan(codeFiles(), rules)).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("one notification call site", () => {
  const API_NAMES = new Set([
    "notifications",
    "showNotification",
    "hideNotification",
    "updateNotification",
    "cleanNotifications",
    "cleanNotificationsQueue",
    "notificationsStore",
    "createNotificationsStore",
    "useNotifications",
  ]);

  /** True when the source imports (or re-exports) Mantine's notification API. */
  function importsNotificationApi(source: string): boolean {
    const code = stripComments(source);
    const named = /(?:import|export)\s+(?:type\s+)?(?:\w+\s*,\s*)?\{([^}]*)\}\s*from\s*["']@mantine\/notifications["']/g;
    for (const match of code.matchAll(named)) {
      const names = match[1]
        .split(",")
        .map((part) => part.trim().replace(/^type\s+/, "").split(/\s+as\s+/)[0].trim())
        .filter((name) => name.length > 0);
      if (names.some((name) => API_NAMES.has(name))) return true;
    }
    if (/import\s*\*\s*as\s+\w+\s+from\s*["']@mantine\/notifications["']/.test(code)) return true;
    if (/export\s*\*\s*(?:as\s+\w+\s+)?from\s*["']@mantine\/notifications["']/.test(code)) return true;
    if (/\b(?:import|require)\s*\(\s*["']@mantine\/notifications["']\s*\)/.test(code)) return true;
    return false;
  }

  it("Mantine's notification API is imported by shared/notifyFailure.ts alone — DoD-12", () => {
    const importers = codeFiles()
      .filter((file) => importsNotificationApi(readFileSync(file, "utf8")))
      .map(relative);
    expect(importers).toEqual(["src/shared/notifyFailure.ts"]);
  });
});
