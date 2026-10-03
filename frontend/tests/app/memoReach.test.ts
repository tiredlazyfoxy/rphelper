// Feature 015, step 005 — the reach helper (DoD-8, DoD-9).
//
// Expected values come from R3's reach table (is_enabled gates first, so disabled-plus-
// forced is disabled), D7 and context.md's UI strings table. The statements are compared
// against the literal strings, never against a call to the helper itself.
import { describe, expect, it } from "vitest";
import type { Memo } from "../../src/app/memosApi";
import { memoReach, reachStatement } from "../../src/app/memoReach";

function note(isEnabled: boolean, isForced: boolean): Memo {
  return {
    id: "7250000000000000201",
    scope: "character",
    scope_id: "7250000000000000001",
    body: "# Standing note",
    is_enabled: isEnabled,
    is_forced: isForced,
    sort_key: 0,
    created_at: "2026-10-02T09:26:53.000000+00:00",
    updated_at: "2026-10-02T09:26:53.000000+00:00",
  };
}

describe("memoReach", () => {
  it("enabled and forced is forced — DoD-8", () => {
    expect(memoReach(note(true, true))).toBe("forced");
  });

  it("enabled and not forced is searchable — DoD-8", () => {
    expect(memoReach(note(true, false))).toBe("searchable");
  });

  it("not enabled but forced is disabled (is_enabled gates first) — DoD-8", () => {
    expect(memoReach(note(false, true))).toBe("disabled");
  });

  it("not enabled and not forced is disabled — DoD-8", () => {
    expect(memoReach(note(false, false))).toBe("disabled");
  });

  it("accepts any object carrying the two flags, not only a full Memo — DoD-8", () => {
    expect(memoReach({ is_enabled: true, is_forced: true })).toBe("forced");
    expect(memoReach({ is_enabled: true, is_forced: false })).toBe("searchable");
    expect(memoReach({ is_enabled: false, is_forced: true })).toBe("disabled");
    expect(memoReach({ is_enabled: false, is_forced: false })).toBe("disabled");
  });
});

describe("reachStatement", () => {
  it("states the forced reach exactly — DoD-9", () => {
    expect(reachStatement("forced")).toBe("Forced: always given to the assistant.");
  });

  it("states the searchable reach exactly — DoD-9", () => {
    expect(reachStatement("searchable")).toBe(
      "Searchable: found only when the assistant searches.",
    );
  });

  it("states the disabled reach exactly — DoD-9", () => {
    expect(reachStatement("disabled")).toBe("Disabled: never reaches the assistant.");
  });
});
