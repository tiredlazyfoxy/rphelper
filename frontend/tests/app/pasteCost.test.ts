// Feature 014, step 003 — the pure paste-size estimate (DoD-1..DoD-3).
//
// Expected values come from the step's Definition of done and context.md D3:
//   - characters per token = 4, warning threshold = 32,000 tokens;
//   - estimate = ceil(length / 4), no trimming;
//   - enormous iff the estimate is strictly greater than 32,000 (fires above 128,000 chars);
//   - the module imports nothing.
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  CHARS_PER_TOKEN,
  PASTE_WARNING_THRESHOLD_TOKENS,
  estimateTokens,
  isEnormousPaste,
} from "../../src/app/pasteCost";

const PASTE_COST_SOURCE = path.resolve(__dirname, "../../src/app/pasteCost.ts");

describe("pasteCost — constants and estimate (D3)", () => {
  it("the characters-per-token constant is 4 — DoD-1", () => {
    expect(CHARS_PER_TOKEN).toBe(4);
  });

  it("the warning-threshold constant is 32,000 tokens — DoD-1", () => {
    expect(PASTE_WARNING_THRESHOLD_TOKENS).toBe(32_000);
  });

  it('estimateTokens("") is 0 — DoD-1', () => {
    expect(estimateTokens("")).toBe(0);
  });

  it('estimateTokens("abcd") is 1 — DoD-1', () => {
    expect(estimateTokens("abcd")).toBe(1);
  });

  it('estimateTokens("abcde") is 2 (rounded up) — DoD-1', () => {
    expect(estimateTokens("abcde")).toBe(2);
  });

  it("estimateTokens of a 128,000-character text is 32,000 — DoD-1", () => {
    expect(estimateTokens("a".repeat(128_000))).toBe(32_000);
  });
});

describe("pasteCost — isEnormousPaste boundary (D3, US-035.AC-1)", () => {
  it("a 128,000-character text is not enormous — DoD-2", () => {
    expect(isEnormousPaste("a".repeat(128_000))).toBe(false);
  });

  it("a 128,001-character text is enormous — DoD-2", () => {
    expect(isEnormousPaste("a".repeat(128_001))).toBe(true);
  });

  it("a 500,000-character text is enormous — DoD-2", () => {
    expect(isEnormousPaste("a".repeat(500_000))).toBe(true);
  });

  it('"" is not enormous — DoD-2', () => {
    expect(isEnormousPaste("")).toBe(false);
  });
});

describe("pasteCost.ts is pure (D3)", () => {
  it("has no import statement, no re-export from a module and no require / dynamic import — DoD-3", () => {
    const source = readFileSync(PASTE_COST_SOURCE, "utf8");
    const offending = source
      .split("\n")
      .filter(
        (line) =>
          /^\s*import[\s{*"']/.test(line) ||
          /^\s*export\b[^;]*\bfrom\s*["']/.test(line) ||
          /\brequire\s*\(\s*["'`]/.test(line) ||
          /\bimport\s*\(\s*["'`]/.test(line),
      );
    expect(offending).toEqual([]);
  });
});
