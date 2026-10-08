/**
 * Feature 032 step 006 — the `admin` frontend entry's half of the privacy audit.
 *
 * Step file: `docs/plans/032.privacy-isolation-audit/006.admin-surfaces-and-reverse-lookup.md`.
 * This file covers **DoD-8** and **DoD-9**; DoD-1..DoD-7 are backend clauses and live in
 * `backend/tests/test_privacy_audit_admin.py`. DoD-10 is `[manual/live]` and has no test.
 *
 * Both items cite **US-084.AC-1**.
 *
 * A source-scanning test, which is this project's substitute for a lint rule (there is no
 * ESLint; `tsc --noEmit` is the gate and grep-style rules become Vitest tests). It reads the
 * files under `frontend/src/admin/` as text and never renders anything.
 *
 * Two mechanics the spec fixes, and the reason for each:
 *
 * - **Only the admin entry's own files are scanned.** `006.context.md`: "Shared client code the
 *   admin entry imports from outside `frontend/src/admin/` is not scanned; the assertion is
 *   about what the admin entry's own files call."
 * - **Comments are stripped first**, following the repo's own source-scan helpers
 *   (`tests/conventions.test.ts`, `tests/app/entryIsolation.test.ts`). A scan that kept
 *   comments would fail DoD-9 on explanatory prose that renders nothing, and DoD-8 on a
 *   documentation line naming a route the file does not call. Matching is **whole-identifier**
 *   for the same reason: a naive substring match treats `AdminUserRow` as a hit for `inUse`
 *   and `account` as a hit for `count`.
 *
 * `globals: false` in `vite.config.ts`, so every helper is imported explicitly.
 */

import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const FRONTEND_ROOT = path.resolve(__dirname, "..");
const ADMIN_ROOT = path.join(FRONTEND_ROOT, "src", "admin");

/** `006.context.md` "Allowed API prefixes for the admin entry (DoD-8)" — the whole list. */
const ALLOWED_PREFIXES: readonly string[] = ["/api/admin/", "/api/me", "/api/auth/", "/api/health"];

/** Every `/api/...` run of path characters. Stops before `${`, so a template's literal head
 *  (`` `/api/admin/users/${id}/disable` ``) is what gets checked — which is the only part of a
 *  composed path the admin files themselves spell out. */
const API_LITERAL = /\/api\/[A-Za-z0-9_\-./]*/g;

/**
 * `006.context.md` "Forbidden-name list (DoD-5, DoD-9)", case-insensitive, matched as whole
 * identifiers / words, plus the phrase family and the "N sessions use this model" shape named
 * by DoD-9. `embedding_dim` and the length of `enabled_model_names` are registry facts not
 * derived from user content and are exempt by name — the whole-identifier rules below cannot
 * match them.
 */
const FORBIDDEN_IDENTIFIERS: readonly string[] = [
  "session_count",
  "sessions_count",
  "sessionCount",
  "character_count",
  "characterCount",
  "memo_count",
  "memoCount",
  "message_count",
  "messageCount",
  "user_count",
  "userCount",
  "row_count",
  "rowCount",
  "vector_count",
  "vectorCount",
  "usage_count",
  "usageCount",
  "in_use",
  "inUse",
  "used_by",
  "usedBy",
  "dependent_sessions",
  "dependentSessions",
];

const FORBIDDEN_PHRASES: readonly string[] = ["sessions use", "sessions using", "in use by"];

type Rule = [string, RegExp];

function identifierRule(token: string): Rule {
  return [`forbidden name ${token}`, new RegExp(`(?<![A-Za-z0-9_$])${token}(?![A-Za-z0-9_$])`, "gi")];
}

function phraseRule(phrase: string): Rule {
  const spaced = phrase.split(" ").join("\\s+");
  return [`forbidden phrase "${phrase}"`, new RegExp(`\\b${spaced}\\b`, "gi")];
}

const FORBIDDEN_RULES: readonly Rule[] = [
  ...FORBIDDEN_IDENTIFIERS.map(identifierRule),
  ...FORBIDDEN_PHRASES.map(phraseRule),
  // The "N sessions use this model" pattern family: a number, or an interpolated value, read
  // as a quantity of sessions. R5 forbids the count itself, not only the words around it.
  ["a counted quantity of sessions", /(?:\d+|\$\{[^}]*\}|\{[^}]*\})\s*sessions?(?![A-Za-z0-9_$])/gi],
];

interface Offence {
  readonly file: string;
  readonly line: number;
  readonly rule: string;
  readonly text: string;
}

function allFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    return entry.isDirectory() ? allFiles(full) : [full];
  });
}

function relative(file: string): string {
  return path.relative(FRONTEND_ROOT, file).split(path.sep).join("/");
}

function adminCodeFiles(): string[] {
  return allFiles(ADMIN_ROOT).filter((file) => /\.(ts|tsx)$/.test(file));
}

/** Blank out comments while keeping every newline, so reported line numbers stay true. */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (match) => match.replace(/[^\n]/g, " "))
    .replace(/(^|[^:])\/\/[^\n]*/g, "$1");
}

function lineOf(source: string, index: number): number {
  return source.slice(0, index).split(/\r?\n/).length;
}

function formatOffence(offence: Offence): string {
  return `${offence.file}:${offence.line} — ${offence.rule} — ${offence.text}`;
}

function failureMessage(offences: readonly Offence[]): string {
  return offences.length === 0 ? "no offences" : offences.map(formatOffence).join("\n");
}

function apiLiteralsIn(source: string): string[] {
  return Array.from(stripComments(source).matchAll(API_LITERAL), (match) => match[0]);
}

/**
 * A prefix match on a path must respect segment boundaries. `/api/admin/` and `/api/auth/`
 * already end in `/`, so a bare `startsWith` is exact for them. The two bare-path prefixes
 * `/api/me` and `/api/health` are whole paths, so after them the literal must *end* or continue
 * with `/` or `?` — otherwise `/api/memos` and `/api/members` would count as allowed, and a real
 * admin-entry call to the user-content route `/api/memos` would pass DoD-8.
 */
function isAllowedLiteral(literal: string): boolean {
  return ALLOWED_PREFIXES.some((prefix) => {
    if (!literal.startsWith(prefix)) return false;
    if (prefix.endsWith("/")) return true;
    const next = literal.slice(prefix.length);
    return next === "" || next.startsWith("/") || next.startsWith("?");
  });
}

function prefixOffencesIn(file: string, source: string): Offence[] {
  const stripped = stripComments(source);
  const offences: Offence[] = [];
  for (const match of stripped.matchAll(API_LITERAL)) {
    if (!isAllowedLiteral(match[0])) {
      offences.push({
        file,
        line: lineOf(stripped, match.index ?? 0),
        rule: "an /api/ path outside the allowed prefixes",
        text: match[0],
      });
    }
  }
  return offences;
}

function forbiddenOffencesIn(file: string, source: string): Offence[] {
  const stripped = stripComments(source);
  const offences: Offence[] = [];
  for (const [rule, pattern] of FORBIDDEN_RULES) {
    for (const match of stripped.matchAll(pattern)) {
      offences.push({ file, line: lineOf(stripped, match.index ?? 0), rule, text: match[0] });
    }
  }
  return offences;
}

describe("the admin entry's source scan reaches the admin entry — DoD-8, DoD-9", () => {
  it("walks every TypeScript file under src/admin", () => {
    const files = adminCodeFiles().map(relative);
    expect(files.length).toBeGreaterThan(0);
    // The three admin pages `docs/architecture/admin-surfaces.md` names.
    expect(files).toEqual(
      expect.arrayContaining(["src/admin/UsersPage.tsx", "src/admin/LlmServersPage.tsx", "src/admin/DatabasePage.tsx"]),
    );
    // Nothing outside the admin entry is in scope (`006.context.md`: shared client code the
    // admin entry imports from outside `src/admin/` is not scanned).
    expect(files.filter((file) => !file.startsWith("src/admin/"))).toEqual([]);
  });

  it("blanks comments without moving line numbers", () => {
    const source = ['const a = 1; // row count (US-078)', "/* count of rows\n   and more */", "const b = 2;"].join(
      "\n",
    );
    const stripped = stripComments(source);
    expect(stripped).not.toContain("row count");
    expect(stripped).not.toContain("count of rows");
    expect(stripped.split("\n").length).toBe(source.split("\n").length);
    expect(stripComments('const url = "https://example.test/a";')).toContain("https://example.test/a");
  });
});

describe("every /api/ path literal in the admin entry begins with an allowed prefix — DoD-8", () => {
  it("pins the allowed prefixes to the four `006.context.md` names", () => {
    expect([...ALLOWED_PREFIXES].sort()).toEqual(["/api/admin/", "/api/auth/", "/api/health", "/api/me"]);
  });

  const flagged: readonly string[] = [
    'const p = "/api/sessions";',
    'await apiGet("/api/search?q=sentinel");',
    'const own = "/api/export";',
    // Both sides of the `/api/me` segment boundary: a longer path that merely starts with the
    // same characters is a different route and is not allowed.
    'const memos = "/api/memos";',
    'const members = "/api/members";',
    'const bare = "/api/";',
  ];
  const clean: readonly string[] = [
    'const USERS_PATH = "/api/admin/users";',
    'const SERVERS_PATH = "/api/admin/llm-servers";',
    'const TABLES = "/api/admin/database/tables";',
    'const ME_PATH = "/api/me";',
    // The boundary rule must not reject the allowed route itself, with a sub-path or a query.
    'const SETTINGS = "/api/me/settings";',
    'const PROBE = "/api/me?x=1";',
    'const OUT = "/api/auth/logout";',
    'const HEALTH = "/api/health";',
    'const LOGIN_PATH = "/login";',
    "const url = `${SERVERS_PATH}/${encodeURIComponent(id)}/models`;",
    "// documented at /api/sessions",
    "/* reads /api/search */",
  ];

  it.each(flagged)("flags %j — DoD-8", (line) => {
    expect(prefixOffencesIn("src/probe.ts", line).length).toBeGreaterThan(0);
  });

  it.each(clean)("does not flag %j — DoD-8", (line) => {
    expect(prefixOffencesIn("src/probe.ts", line)).toEqual([]);
  });

  it("finds the admin pages' own API paths, so the scan is not looking at nothing — DoD-8", () => {
    const literals = adminCodeFiles().flatMap((file) => apiLiteralsIn(readFileSync(file, "utf8")));
    expect(literals.length).toBeGreaterThan(0);
    // The three admin surfaces of `context.md`'s enumeration (rows 54, 60, 69) must be called
    // from the admin entry's own files, or an absence of offences would prove nothing.
    const distinct = [...new Set(literals)];
    expect(distinct).toEqual(
      expect.arrayContaining(["/api/admin/users", "/api/admin/llm-servers", "/api/admin/database/tables"]),
    );
  });

  it("finds no /api/ literal outside the allowed prefixes — DoD-8", () => {
    const offences = adminCodeFiles().flatMap((file) => prefixOffencesIn(relative(file), readFileSync(file, "utf8")));
    // An exact set, not a subset: a single stray literal fails this.
    expect(offences.map(formatOffence), failureMessage(offences)).toEqual([]);
  });
});

describe("no admin file names a count of, or a dependency on, another user's material — DoD-9", () => {
  it("pins the forbidden list to `006.context.md`", () => {
    expect(FORBIDDEN_IDENTIFIERS.length).toBe(23);
    expect([...FORBIDDEN_PHRASES].sort()).toEqual(["in use by", "sessions use", "sessions using"]);
  });

  const flagged: readonly string[] = [
    "const sessionCount = rows.length;",
    "type Row = { session_count: number };",
    "const n: number = payload.sessions_count;",
    "const c = payload.character_count;",
    "const m = payload.memoCount;",
    "const g = payload.message_count;",
    "const u = payload.user_count;",
    "const r = payload.rowCount;",
    "const v = payload.vector_count;",
    "const w = payload.usageCount;",
    "const inUse = true;",
    "const flag = row.in_use;",
    "const owner = row.used_by;",
    "const owners = row.usedBy;",
    "const list = row.dependentSessions;",
    "const other = row.dependent_sessions;",
    '<Text>4 sessions use this model</Text>',
    "const warning = `${count} sessions using this model`;",
    'const consequence = "It is in use by two other people.";',
    "<Text>{dependents} sessions</Text>",
  ];
  const clean: readonly string[] = [
    "import type { AdminUserRow } from './usersPageState';",
    "type List = AdminUserListResponse;",
    "const role: AdminUserRole = 'admin';",
    'const message = "The account could not be created.";',
    'const title = "Disable account?";',
    "const enabled = row.enabled_model_names.length;",
    "const dim = row.embedding_dim;",
    "const independent = true;",
    "const usage = probe.usage;",
    "const tokens = reply.usage_tokens;",
    'const label = "Delete LLM server?";',
    "// never a row count (US-078)",
    "/* reads nothing from the response but its byte count (US-078) */",
    "const size = formatByteSize(state.exportSizeBytes);",
  ];

  it.each(flagged)("flags %j — DoD-9", (line) => {
    expect(forbiddenOffencesIn("src/probe.ts", line).length).toBeGreaterThan(0);
  });

  it.each(clean)("does not flag %j — DoD-9", (line) => {
    const offences = forbiddenOffencesIn("src/probe.ts", line);
    expect(offences.map(formatOffence), failureMessage(offences)).toEqual([]);
  });

  it("finds no forbidden name, phrase or counted-sessions shape under src/admin — DoD-9", () => {
    const offences = adminCodeFiles().flatMap((file) =>
      forbiddenOffencesIn(relative(file), readFileSync(file, "utf8")),
    );
    // An exact set, not a subset.
    expect(offences.map(formatOffence), failureMessage(offences)).toEqual([]);
  });
});
