// Feature 002, step 006 — ids are strings (DoD-9).
// Pattern set from 006.context.md: (1) a binding named `id`/`Id` or ending in `id`/`Id`
// annotated `number` / `number[]` (whitespace and an optional `?` allowed before the colon);
// (2) any `parseInt`; (3) any `Number.parseInt`. No exception list, no suppression comment:
// comments are scanned too.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const FRONTEND_ROOT = path.resolve(__dirname, "..");
const SRC_ROOT = path.join(FRONTEND_ROOT, "src");

type Offence = { file: string; line: number; rule: string; text: string };

const RULES: Array<[string, RegExp]> = [
  ["id-like binding annotated as number", /\b\w*(?:id|Id)\s*\??\s*:\s*number\b/],
  ["parseInt", /\bparseInt\b/],
  ["Number.parseInt", /\bNumber\s*\.\s*parseInt\b/],
];

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(full);
    return /\.(ts|tsx)$/.test(entry.name) ? [full] : [];
  });
}

function relative(file: string): string {
  return path.relative(FRONTEND_ROOT, file).split(path.sep).join("/");
}

/** Scan one file's text; `file` is the path reported in each offence. */
function scanText(file: string, text: string): Offence[] {
  const offences: Offence[] = [];
  text.split(/\r?\n/).forEach((lineText, index) => {
    for (const [rule, pattern] of RULES) {
      if (pattern.test(lineText)) {
        offences.push({ file, line: index + 1, rule, text: lineText.trim() });
      }
    }
  });
  return offences;
}

function formatOffence(offence: Offence): string {
  return `${offence.file}:${offence.line} — ${offence.rule}: ${offence.text}`;
}

function failureMessage(offences: Offence[]): string {
  if (offences.length === 0) return "no offences";
  return `ids-are-strings violated; first offence at ${formatOffence(offences[0])}`;
}

// ---------------------------------------------------------------------------
describe("the scan itself", () => {
  const FLAGGED: string[] = [
    "  id: number;",
    "  Id: number;",
    "  sessionId: number;",
    "  message_id: number;",
    "  characterId: number[];",
    "  characterId?: number;",
    "  sessionId ?: number;",
    "  id   :   number",
    "function load(userId: number) {}",
    "const n = parseInt(raw, 10);",
    "const n = Number.parseInt(raw, 10);",
  ];

  const CLEAN: string[] = [
    "  id: string;",
    "  sessionId: string;",
    "  characterId?: string[];",
    "  count: number;",
    "  identity: number;",
    "  width: number;",
    "  const size = Number(raw);",
  ];

  it.each(FLAGGED)("flags %j — DoD-9", (line) => {
    expect(scanText("src/probe.ts", line).length).toBeGreaterThan(0);
  });

  it.each(CLEAN)("does not flag %j — DoD-9", (line) => {
    expect(scanText("src/probe.ts", line)).toEqual([]);
  });

  it("the failure message names the offending file and line number — DoD-9", () => {
    const text = ["export type Row = {", "  label: string;", "  rowId: number;", "};"].join("\n");
    const offences = scanText("src/shared/probe.ts", text);
    expect(offences.map((o) => [o.file, o.line])).toEqual([["src/shared/probe.ts", 3]]);
    expect(failureMessage(offences)).toContain("src/shared/probe.ts:3");
  });

  it("reports the first offence by line order — DoD-9", () => {
    const text = ["const a = 1;", "const b = parseInt(x);", "type T = { id: number };"].join("\n");
    const offences = scanText("src/x.tsx", text);
    expect(failureMessage(offences)).toContain("src/x.tsx:2");
  });
});

// ---------------------------------------------------------------------------
describe("frontend/src", () => {
  it("the scan reaches every .ts and .tsx file, recursively — DoD-9", () => {
    const files = sourceFiles(SRC_ROOT).map(relative);
    expect(files).toEqual(
      expect.arrayContaining([
        "src/shared/api.ts",
        "src/shared/AppProviders.tsx",
        "src/bootstrap/main.tsx",
        "src/login/main.tsx",
        "src/admin/main.tsx",
        "src/app/main.tsx",
      ]),
    );
  });

  it("no .ts/.tsx file under frontend/src contains a forbidden id pattern — DoD-9", () => {
    const offences = sourceFiles(SRC_ROOT).flatMap((file) =>
      scanText(relative(file), readFileSync(file, "utf8")),
    );
    expect(offences.map(formatOffence), failureMessage(offences)).toEqual([]);
  });
});
