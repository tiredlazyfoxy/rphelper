// Feature 011, step 005 — the start-time label formatter (DoD-1..DoD-4, and DoD-10 for
// src/app/sessionLabel.ts; treeCollapse.ts's half of DoD-10 lives in tests/app/treeCollapse.test.ts).
// Feature 034, step 004 — the session label rule (S034_004_DoD1, S034_004_DoD2) and the
// renamed local date-time formatter (S034_004_DoD3). 034 renames `formatSessionStart` to
// `formatLocalDateTime` with an unchanged contract (DEC-034-9), so the 011 clauses below now
// call it by its new name; their expected values are unchanged.
//
// This is the ONLY place exact start-time label values are asserted, and every such clause
// passes an explicit IANA zone (context.md "Test conventions" → "Start-time labels").
// The zone-less clauses compare against the runtime's own resolved zone and the label's fixed
// shape, never against a hard-coded local-time string, so the suite passes in any zone. Node
// ships full ICU (005.context.md), so Asia/Tokyo, Europe/Berlin and America/New_York resolve
// here as they do in a browser.
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  formatLocalDate,
  formatLocalDateTime,
  sessionLabel,
} from "../../src/app/sessionLabel";

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const SESSION_LABEL_SOURCE = path.join(FRONTEND_ROOT, "src", "app", "sessionLabel.ts");

/** The label's fixed shape: `YYYY-MM-DD HH:MM`, nothing before or after. */
const LABEL_SHAPE = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/;

/** The date-only shape of an unnamed session's label: `YYYY-MM-DD`, no time (DEC-034-9). */
const DATE_SHAPE = /^\d{4}-\d{2}-\d{2}$/;

/** One instant, in `data-model.md`'s fixed-width form, used by DoD-1 and DoD-2. */
const INSTANT = "2026-10-01T18:05:09.123456+00:00";

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

// ---------------------------------------------------------------------------
describe("the label is YYYY-MM-DD HH:MM in the given zone", () => {
  it('"2026-10-01T18:05:09.123456+00:00" in UTC is "2026-10-01 18:05" — DoD-1', () => {
    expect(formatLocalDateTime(INSTANT, "UTC")).toBe("2026-10-01 18:05");
  });

  it("the UTC label carries no seconds and no zone suffix — DoD-1", () => {
    expect(formatLocalDateTime(INSTANT, "UTC")).toMatch(LABEL_SHAPE);
  });

  it('the same instant in "Asia/Tokyo" is "2026-10-02 03:05" — the date rolls over — DoD-2', () => {
    expect(formatLocalDateTime(INSTANT, "Asia/Tokyo")).toBe("2026-10-02 03:05");
  });

  it('the same instant in "America/New_York" is "2026-10-01 14:05" — DoD-2', () => {
    expect(formatLocalDateTime(INSTANT, "America/New_York")).toBe("2026-10-01 14:05");
  });
});

// ---------------------------------------------------------------------------
describe("zero-padding, 24-hour form, and no rounding up", () => {
  it('"2026-01-05T03:04:00.000000+00:00" in UTC is "2026-01-05 03:04" — DoD-3', () => {
    expect(formatLocalDateTime("2026-01-05T03:04:00.000000+00:00", "UTC")).toBe("2026-01-05 03:04");
  });

  it('"2026-01-05T23:59:59.999999+00:00" in UTC is "2026-01-05 23:59" — DoD-3', () => {
    expect(formatLocalDateTime("2026-01-05T23:59:59.999999+00:00", "UTC")).toBe("2026-01-05 23:59");
  });

  it("midnight in UTC renders hour 00, never 24 — DoD-3", () => {
    expect(formatLocalDateTime("2026-01-05T00:00:00.000000+00:00", "UTC")).toBe("2026-01-05 00:00");
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
    expect(formatLocalDateTime(createdAt)).toMatch(LABEL_SHAPE);
  });

  it.each(INSTANTS)(
    "the zone-less label for %s equals the label for the resolved zone — DoD-4",
    (createdAt) => {
      expect(formatLocalDateTime(createdAt)).toBe(formatLocalDateTime(createdAt, RESOLVED_ZONE));
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

// ===========================================================================
// Feature 034, step 004 — sessionLabel and the local date-time formatter.
// Expected values: the step's DoD-1..DoD-3, DEC-034-9 (the label is the name, else the local
// YYYY-MM-DD of created_at), DEC-arch-session-names-1 (the default label is the LOCAL date)
// and DEC-arch-session-names-3 (last use as local YYYY-MM-DD HH:MM, fixed width).
// ===========================================================================

/** A start instant late on 5 November UTC: already 6 November in Berlin (UTC+1 in November). */
const LATE_UTC = "2026-11-05T23:30:00Z";

describe("sessionLabel returns a stored name verbatim (034 step 004)", () => {
  it("a plain name is returned unchanged, whatever the start date — S034_004_DoD1", () => {
    expect(sessionLabel({ name: "Harbour at dusk", created_at: LATE_UTC }, "UTC")).toBe(
      "Harbour at dusk",
    );
  });

  it("a name that looks like a date is returned as the name, not reformatted — S034_004_DoD1", () => {
    // The created_at is a different date, so a date-derived label could never produce this.
    expect(sessionLabel({ name: "2026-01-01", created_at: LATE_UTC }, "Europe/Berlin")).toBe(
      "2026-01-01",
    );
  });

  it("a name that looks like a date-time is returned verbatim, time included — S034_004_DoD1", () => {
    expect(sessionLabel({ name: "2025-12-31 23:59", created_at: LATE_UTC }, "UTC")).toBe(
      "2025-12-31 23:59",
    );
  });

  it("a non-Latin name with inner spacing is returned verbatim — S034_004_DoD1", () => {
    expect(sessionLabel({ name: "Ночь  в гавани", created_at: LATE_UTC }, "UTC")).toBe(
      "Ночь  в гавани",
    );
  });

  it("the name wins with no zone argument too — S034_004_DoD1", () => {
    expect(sessionLabel({ name: "Harbour at dusk", created_at: LATE_UTC })).toBe("Harbour at dusk");
  });
});

describe("sessionLabel with a null name is the local start date (034 step 004)", () => {
  it('"2026-11-05T23:30:00Z" in Europe/Berlin is "2026-11-06" — S034_004_DoD2', () => {
    expect(sessionLabel({ name: null, created_at: LATE_UTC }, "Europe/Berlin")).toBe("2026-11-06");
  });

  it('the same instant in UTC is "2026-11-05" — S034_004_DoD2', () => {
    expect(sessionLabel({ name: null, created_at: LATE_UTC }, "UTC")).toBe("2026-11-05");
  });

  it("a west-of-UTC zone rolls the date back across the boundary — S034_004_DoD2", () => {
    // 02:00 UTC on 6 November is 21:00 on 5 November in New York (UTC-5 after the DST end).
    expect(
      sessionLabel({ name: null, created_at: "2026-11-06T02:00:00Z" }, "America/New_York"),
    ).toBe("2026-11-05");
  });

  it("the data-model fixed-width timestamp form gives the local date too — S034_004_DoD2", () => {
    expect(sessionLabel({ name: null, created_at: INSTANT }, "Asia/Tokyo")).toBe("2026-10-02");
    expect(sessionLabel({ name: null, created_at: INSTANT }, "UTC")).toBe("2026-10-01");
  });

  it("the date is zero-padded — S034_004_DoD2", () => {
    expect(
      sessionLabel({ name: null, created_at: "2026-01-05T03:04:00.000000+00:00" }, "UTC"),
    ).toBe("2026-01-05");
  });

  it.each(["UTC", "Europe/Berlin", "Asia/Tokyo", "America/New_York"])(
    "in %s the date label never carries a time — S034_004_DoD2",
    (zone) => {
      const label = sessionLabel({ name: null, created_at: LATE_UTC }, zone);
      expect(label).toMatch(DATE_SHAPE);
      expect(label).not.toContain(":");
      expect(label).toHaveLength(10);
    },
  );

  it("with no zone argument the label is the runtime zone's date, date only — S034_004_DoD2", () => {
    const resolved = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const label = sessionLabel({ name: null, created_at: LATE_UTC });
    expect(label).toMatch(DATE_SHAPE);
    expect(label).toBe(sessionLabel({ name: null, created_at: LATE_UTC }, resolved));
  });

  it("accepts any value carrying name and created_at, ignoring other keys — S034_004_DoD2", () => {
    // A Session-shaped value carries more keys; the rule reads only name and created_at.
    const sessionLike = {
      id: "7270000000000000001",
      name: null,
      created_at: LATE_UTC,
      last_used_at: "2027-02-01T12:00:00Z",
    };
    expect(sessionLabel(sessionLike, "Europe/Berlin")).toBe("2026-11-06");
  });

  it("the local-date fallback formatter agrees with the unnamed label — S034_004_DoD2", () => {
    expect(formatLocalDate(LATE_UTC, "Europe/Berlin")).toBe("2026-11-06");
    expect(formatLocalDate(LATE_UTC, "UTC")).toBe("2026-11-05");
    expect(formatLocalDate(LATE_UTC, "UTC")).toMatch(DATE_SHAPE);
  });
});

describe("formatLocalDateTime is local YYYY-MM-DD HH:MM at a fixed width (034 step 004)", () => {
  it('"2026-11-05T23:30:00Z" in Europe/Berlin is "2026-11-06 00:30" — S034_004_DoD3', () => {
    expect(formatLocalDateTime(LATE_UTC, "Europe/Berlin")).toBe("2026-11-06 00:30");
  });

  it("single-digit month, day, hour and minute are zero-padded — S034_004_DoD3", () => {
    expect(formatLocalDateTime("2026-02-03T04:05:00Z", "UTC")).toBe("2026-02-03 04:05");
  });

  it("an afternoon hour is 24-hour, with no AM/PM marker — S034_004_DoD3", () => {
    const text = formatLocalDateTime("2026-02-03T16:45:00Z", "UTC");
    expect(text).toBe("2026-02-03 16:45");
    expect(text).not.toMatch(/[AaPp]\.?[Mm]/);
  });

  it("midnight is hour 00, never 24 — S034_004_DoD3", () => {
    expect(formatLocalDateTime("2026-11-05T23:00:00Z", "Europe/Berlin")).toBe("2026-11-06 00:00");
  });

  it.each([
    ["2026-01-01T00:00:00Z", "UTC"],
    ["2026-02-03T04:05:00Z", "Asia/Tokyo"],
    ["2026-12-31T23:59:59.999999+00:00", "America/New_York"],
    [LATE_UTC, "Europe/Berlin"],
  ])("%s in %s renders exactly 16 characters — S034_004_DoD3", (instant, zone) => {
    const text = formatLocalDateTime(instant, zone);
    expect(text).toHaveLength(16);
    expect(text).toMatch(LABEL_SHAPE);
  });
});
