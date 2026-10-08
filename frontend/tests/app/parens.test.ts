// Feature 013, step 001 — the pure `(( ))` module (DoD-6..DoD-10).
//
// Every expected value is copied from 001.context.md's worked tables ("Classification
// examples", "Segment examples", "Strip examples", "Preview examples"), which port 012 D8.
// No expectation is computed by calling the module. The "not pinned" oddity (nested /
// tripled parentheses inside a turn) is deliberately left untested.
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  isWhollyParenthesised,
  type ParenSegment,
  previewSettle,
  type SettlePreview,
  splitParenSegments,
  stripFragments,
} from "../../src/app/parens";

const PARENS_SOURCE = path.resolve(__dirname, "../../src/app/parens.ts");

const show = (text: string): string => JSON.stringify(text);

const P = (text: string): ParenSegment => ({ kind: "prose", text });
const F = (text: string): ParenSegment => ({ kind: "fragment", text });

// ---------------------------------------------------------------------------
describe("isWhollyParenthesised — the decision rule", () => {
  const DECISIONS = [
    "((x))",
    "  ((x))  \n",
    "((first line\nsecond line))",
    "((one)) ((two))",
    "((a)) prose ((b))",
    "(((x)))",
    "(())",
  ];
  const TURNS = [
    "((hint)) She walks.",
    "She walks. ((x))",
    "(( never closed",
    "a single (paren) pair",
    "",
  ];

  for (const text of DECISIONS) {
    it(`is true for the decision example ${show(text)} — DoD-6`, () => {
      expect(isWhollyParenthesised(text)).toBe(true);
    });
  }

  for (const text of TURNS) {
    it(`is false for the turn example ${show(text)} — DoD-6`, () => {
      expect(isWhollyParenthesised(text)).toBe(false);
    });
  }
});

// ---------------------------------------------------------------------------
describe("splitParenSegments — the one fragment scanner", () => {
  const SEGMENTS: Array<[string, ParenSegment[]]> = [
    ["a ((b)) c", [P("a "), F("((b))"), P(" c")]],
    ["((b))", [F("((b))")]],
    ["plain", [P("plain")]],
    ["", []],
    ["x ((a\nb)) y ((c))", [P("x "), F("((a\nb))"), P(" y "), F("((c))")]],
    ["(( open", [P("(( open")]],
    ["((a))((b))", [F("((a))"), F("((b))")]],
    ["x ((a)) y))", [P("x "), F("((a))"), P(" y))")]],
  ];

  for (const [input, expected] of SEGMENTS) {
    it(`returns exactly the listed segments for ${show(input)} — DoD-7`, () => {
      expect(splitParenSegments(input)).toEqual(expected);
    });
  }

  for (const [input] of SEGMENTS) {
    it(`segments of ${show(input)} concatenate to the input exactly — DoD-7`, () => {
      expect(
        splitParenSegments(input)
          .map((segment) => segment.text)
          .join(""),
      ).toBe(input);
    });
  }
});

// ---------------------------------------------------------------------------
describe("stripFragments — 012's four-step strip", () => {
  const STRIPS: Array<[string, string]> = [
    ["She walks. ((make it tense)) He waits.", "She walks. He waits."],
    ["((hint)) She walks.", "She walks."],
    ["She walks.\t((x))", "She walks."],
    ["a  ((x))  b", "a  b"],
    ["Line one.\n\n((note))\n\nLine two.", "Line one.\n\nLine two."],
    ["Para.\n  \n((n))\n\t\nNext.", "Para.\n\nNext."],
    ["A\n((x))\nB", "A\n\nB"],
    ["a ((x\ny)) b", "a b"],
    ["a ((x)) b ((y)) c", "a b c"],
    ["((a)) ((", "(("],
    ["x ((a))", "x"],
    ["x ((a)) y))", "x y))"],
  ];
  const UNCHANGED = ["  She walks.  \n", "A\n\n\n\nB", "a ((b"];

  for (const [input, expected] of STRIPS) {
    it(`strips ${show(input)} to exactly ${show(expected)} — DoD-8`, () => {
      expect(stripFragments(input)).toBe(expected);
    });
  }

  for (const input of UNCHANGED) {
    it(`returns ${show(input)} byte-for-byte unchanged (no fragment) — DoD-8`, () => {
      expect(stripFragments(input)).toBe(input);
    });
  }
});

// ---------------------------------------------------------------------------
describe("previewSettle — the kind a settle would file and whether it strips", () => {
  const PREVIEWS: Array<[string, SettlePreview]> = [
    ["((x))", { kind: "decision", strips: false }],
    ["((a)) prose ((b))", { kind: "decision", strips: false }],
    ["  ((x))  \n", { kind: "decision", strips: false }],
    ["She walks. ((x)) On.", { kind: "turn", strips: true }],
    ["((hint)) She walks.", { kind: "turn", strips: true }],
    ["She walks.", { kind: "turn", strips: false }],
    ["(( never closed", { kind: "turn", strips: false }],
  ];

  for (const [input, expected] of PREVIEWS) {
    it(`previews ${show(input)} as ${expected.kind}, strips ${String(expected.strips)} — DoD-9`, () => {
      expect(previewSettle(input)).toEqual(expected);
    });
  }
});

// ---------------------------------------------------------------------------
describe("parens.ts is pure", () => {
  it("has no import statement, no re-export from a module and no require / dynamic import — DoD-10", () => {
    const source = readFileSync(PARENS_SOURCE, "utf8");
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

  it("names no react, mobx, @mantine/* or shared/ module specifier — DoD-10", () => {
    const source = readFileSync(PARENS_SOURCE, "utf8");
    const forbidden = /["'](?:react(?:\/[^"']*)?|react-dom(?:\/[^"']*)?|mobx(?:-react-lite)?|@mantine\/[^"']*|(?:\.\.?\/)+(?:[^"']*\/)?shared\/[^"']*)["']/;
    expect(source).not.toMatch(forbidden);
  });
});
