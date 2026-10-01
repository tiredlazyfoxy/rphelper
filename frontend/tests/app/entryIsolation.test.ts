// Feature 008, step 001 — the app entry's isolation from src/admin and the layout record's
// DOM-freedom (DoD-4, DoD-13). Source scans, not behaviour tests: every file is read from
// disk, comments stripped first so prose about a rule is not mistaken for a breach of it.
//
// The bundles are separate on purpose (context.md: "The `app` entry imports nothing from
// src/admin/"), which is why identity lives in src/shared/currentUser.ts and names no
// /admin route. The scans walk the directory, so files added by later steps are covered.
// DoD-1/DoD-2 live in tests/shared/currentUser.test.ts; DoD-3 in tests/admin/adminAccess.test.ts;
// DoD-5..DoD-12 in tests/app/workspaceLayout.test.ts.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const SRC_ROOT = path.join(FRONTEND_ROOT, "src");
const APP_ROOT = path.join(SRC_ROOT, "app");
const ADMIN_ROOT = path.join(SRC_ROOT, "admin");
const CURRENT_USER_SOURCE = path.join(SRC_ROOT, "shared", "currentUser.ts");
const WORKSPACE_LAYOUT_SOURCE = path.join(APP_ROOT, "workspaceLayout.ts");

// ---------------------------------------------------------------- helpers

function allFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    return entry.isDirectory() ? allFiles(full) : [full];
  });
}

function relative(file: string): string {
  return path.relative(FRONTEND_ROOT, file).split(path.sep).join("/");
}

function codeFiles(dir: string): string[] {
  return allFiles(dir).filter((file) => /\.(ts|tsx)$/.test(file));
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

/** Every module specifier a source file imports (static, side-effect, dynamic, re-export, require). */
function importSpecifiers(source: string): string[] {
  const pattern = /(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)["']([^"']+)["']/g;
  return Array.from(stripComments(source).matchAll(pattern), (m) => m[1]);
}

function isInsideAdmin(resolved: string): boolean {
  return resolved === ADMIN_ROOT || resolved.startsWith(`${ADMIN_ROOT}${path.sep}`);
}

/** `file — imports "<specifier>"` for every specifier under src/app that reaches src/admin. */
function adminImportOffences(): string[] {
  const offences: string[] = [];
  for (const file of codeFiles(APP_ROOT)) {
    for (const spec of importSpecifiers(readFileSync(file, "utf8"))) {
      const reaches = spec.startsWith(".")
        ? isInsideAdmin(path.resolve(path.dirname(file), spec))
        : /(^|\/)admin(\/|$)/.test(spec);
      if (reaches) {
        offences.push(`${relative(file)} — imports "${spec}"`);
      }
    }
  }
  return offences;
}

// ---------------------------------------------------------------------------
describe("the app entry imports nothing from src/admin", () => {
  it("the scan reaches every .ts and .tsx file under src/app, recursively — DoD-4", () => {
    const files = codeFiles(APP_ROOT).map(relative);
    expect(files).toEqual(expect.arrayContaining(["src/app/main.tsx", "src/app/workspaceLayout.ts"]));
  });

  it("the scan sees the import specifiers of a module it reads — DoD-4", () => {
    const specs = importSpecifiers(readFileSync(path.join(APP_ROOT, "main.tsx"), "utf8"));
    expect(specs.length).toBeGreaterThan(0);
  });

  it("no module under src/app imports from src/admin — DoD-4", () => {
    const offences = adminImportOffences();
    expect(offences, offences[0] ?? "no offences").toEqual([]);
  });

  it("the admin-reaching check would flag a relative import of src/admin — DoD-4", () => {
    expect(isInsideAdmin(path.resolve(APP_ROOT, "../admin/adminAccess"))).toBe(true);
    expect(isInsideAdmin(path.resolve(APP_ROOT, "../shared/currentUser"))).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("shared/currentUser names no admin route", () => {
  it("src/shared/currentUser.ts contains no /admin path string — DoD-4", () => {
    const source = stripComments(readFileSync(CURRENT_USER_SOURCE, "utf8"));
    expect(source.length).toBeGreaterThan(0);
    expect(source).not.toContain("/admin");
  });

  it("src/shared/currentUser.ts imports nothing from src/admin — DoD-4", () => {
    const specs = importSpecifiers(readFileSync(CURRENT_USER_SOURCE, "utf8"));
    const reaching = specs.filter((spec) =>
      spec.startsWith(".")
        ? isInsideAdmin(path.resolve(path.dirname(CURRENT_USER_SOURCE), spec))
        : /(^|\/)admin(\/|$)/.test(spec),
    );
    expect(reaching).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("the layout record is DOM-free", () => {
  const DOM_RULES: Array<[string, RegExp]> = [
    ["a window reference", /\bwindow\b/],
    ["a document reference", /\bdocument\b/],
    ["a localStorage global", /\blocalStorage\b/],
    ["a sessionStorage global", /\bsessionStorage\b/],
    ["a React import", /["']react(?:-dom)?(?:\/[^"']*)?["']/],
    ["a MobX import", /["']mobx(?:-react-lite)?(?:\/[^"']*)?["']/],
  ];

  it("the scan reads src/app/workspaceLayout.ts — DoD-13", () => {
    expect(readFileSync(WORKSPACE_LAYOUT_SOURCE, "utf8").length).toBeGreaterThan(0);
  });

  it.each(DOM_RULES)("src/app/workspaceLayout.ts references no %s — DoD-13", (rule, pattern) => {
    const offences = scan([WORKSPACE_LAYOUT_SOURCE], [[rule, pattern]]);
    expect(offences, offences[0] ?? "no offences").toEqual([]);
  });
});
