// Feature 011, step 005 — the start-time label formatter (DoD-1..DoD-4, and DoD-10 for
// src/app/sessionLabel.ts; treeCollapse.ts's half of DoD-10 lives in tests/app/treeCollapse.test.ts).
//
// This is the ONLY place exact start-time label values are asserted, and every such clause
// passes an explicit IANA zone (context.md "Test conventions" → "Start-time labels").
// DoD-4 is the one zone-less clause: it compares against the runtime's own resolved zone and
// the label's fixed shape, never against a hard-coded local-time string, so the suite passes
// in any zone. Node ships full ICU (005.context.md), so Asia/Tokyo and America/New_York
// resolve here as they do in a browser.
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { formatSessionStart } from "../../src/app/sessionLabel";

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const SESSION_LABEL_SOURCE = path.join(FRONTEND_ROOT, "src", "app", "sessionLabel.ts");

/** The label's fixed shape: `YYYY-MM-DD HH:MM`, nothing before or after. */
const LABEL_SHAPE = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/;

/** One instant, in `data-model.md`'s fixed-width form, used by DoD-1 and DoD-2. */
const INSTANT = "2026-10-01T18:05:09.123456+00:00";

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

// ---------------------------------------------------------------------------
describe("the label is YYYY-MM-DD HH:MM in the given zone", () => {
  it('"2026-10-01T18:05:09.123456+00:00" in UTC is "2026-10-01 18:05" — DoD-1', () => {
    expect(formatSessionStart(INSTANT, "UTC")).toBe("2026-10-01 18:05");
  });

  it("the UTC label carries no seconds and no zone suffix — DoD-1", () => {
    expect(formatSessionStart(INSTANT, "UTC")).toMatch(LABEL_SHAPE);
  });

  it('the same instant in "Asia/Tokyo" is "2026-10-02 03:05" — the date rolls over — DoD-2', () => {
    expect(formatSessionStart(INSTANT, "Asia/Tokyo")).toBe("2026-10-02 03:05");
  });

  it('the same instant in "America/New_York" is "2026-10-01 14:05" — DoD-2', () => {
    expect(formatSessionStart(INSTANT, "America/New_York")).toBe("2026-10-01 14:05");
  });
});

// ---------------------------------------------------------------------------
describe("zero-padding, 24-hour form, and no rounding up", () => {
  it('"2026-01-05T03:04:00.000000+00:00" in UTC is "2026-01-05 03:04" — DoD-3', () => {
    expect(formatSessionStart("2026-01-05T03:04:00.000000+00:00", "UTC")).toBe("2026-01-05 03:04");
  });

  it('"2026-01-05T23:59:59.999999+00:00" in UTC is "2026-01-05 23:59" — DoD-3', () => {
    expect(formatSessionStart("2026-01-05T23:59:59.999999+00:00", "UTC")).toBe("2026-01-05 23:59");
  });

  it("midnight in UTC renders hour 00, never 24 — DoD-3", () => {
    expect(formatSessionStart("2026-01-05T00:00:00.000000+00:00", "UTC")).toBe("2026-01-05 00:00");
  });
});

// ---------------------------------------------------------------------------
describe("with no zone argument the runtime's own zone is used", () => {
  const RESOLVED_ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;

  const INSTANTS = [
    "2026-10-01T18:05:09.123456+00:00",
    "2026-01-05T03:04:00.000000+00:00",
    "2026-01-05T23:59:59.999999+00:00",
  ];

  it.each(INSTANTS)("the zone-less label for %s has the fixed shape — DoD-4", (createdAt) => {
    expect(formatSessionStart(createdAt)).toMatch(LABEL_SHAPE);
  });

  it.each(INSTANTS)(
    "the zone-less label for %s equals the label for the resolved zone — DoD-4",
    (createdAt) => {
      expect(formatSessionStart(createdAt)).toBe(formatSessionStart(createdAt, RESOLVED_ZONE));
    },
  );
});

// ---------------------------------------------------------------------------
describe("src/app/sessionLabel.ts is DOM-, React- and MobX-free", () => {
  const DOM_RULES: Array<[string, RegExp]> = [
    ["a window reference", /\bwindow\b/],
    ["a document reference", /\bdocument\b/],
    ["a localStorage global", /\blocalStorage\b/],
    ["a sessionStorage global", /\bsessionStorage\b/],
    ["a React import", /["']react(?:-dom)?(?:\/[^"']*)?["']/],
    ["a MobX import", /["']mobx(?:-react-lite)?(?:\/[^"']*)?["']/],
  ];

  it("the scan reads src/app/sessionLabel.ts from disk — DoD-10", () => {
    expect(readFileSync(SESSION_LABEL_SOURCE, "utf8").length).toBeGreaterThan(0);
  });

  it.each(DOM_RULES)("src/app/sessionLabel.ts references no %s — DoD-10", (rule, pattern) => {
    const source = stripComments(readFileSync(SESSION_LABEL_SOURCE, "utf8"));
    const matches = Array.from(source.matchAll(new RegExp(pattern.source, "g")), (m) => m[0]);
    expect(matches, `${rule}: ${matches[0] ?? "none"}`).toEqual([]);
  });
});
