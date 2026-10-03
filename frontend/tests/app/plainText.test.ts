// Feature 014, step 002 — the pure markdown-to-plain-text module (DoD-1..DoD-6).
//
// Every expected value is transcribed from 002.context.md "Worked examples" (E/B/C/W/L).
// The examples there are JSON string literals; TS double-quoted strings use the same
// escapes (`\n`, `\r`, `\\`, `\"`), so each literal below is copied verbatim.
// No expectation is computed by calling the module.
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { toPlainText } from "../../src/app/plainText";

const PLAIN_TEXT_SOURCE = path.resolve(__dirname, "../../src/app/plainText.ts");

const show = (text: string): string => JSON.stringify(text);

type Example = [id: string, input: string, expected: string];

function convertsExactly(examples: Example[], dod: string): void {
  for (const [id, input, expected] of examples) {
    it(`${id}: converts ${show(input)} to exactly ${show(expected)} — ${dod}`, () => {
      expect(toPlainText(input)).toBe(expected);
    });
  }
}

// ---------------------------------------------------------------------------
describe("toPlainText — emphasis", () => {
  const EMPHASIS: Example[] = [
    ["E1", "Some **bold** and *italic* text.", "Some bold and italic text."],
    ["E2", "__strong__ and _em_", "strong and em"],
    ["E3", "***both*** and ___both___", "both and both"],
    ["E4", "**bold *nested* end**", "bold nested end"],
    ["E5", "*She smiles.*\n*He waits.*", "She smiles.\nHe waits."],
    ["E6", "*one\ntwo*", "one\ntwo"],
    // E7: a blank line ends the paragraph, so the emphasis never closes.
    ["E7", "*one\n\ntwo*", "*one\n\ntwo*"],
    ["E8", "snake_case_name and 2 * 3 * 4", "snake_case_name and 2 * 3 * 4"],
    ["E9", "\\*not italic\\* and a \\\\ backslash", "*not italic* and a \\ backslash"],
    ["E10", "*unclosed emphasis", "*unclosed emphasis"],
    ["E11", "un*frigging*believable", "unfriggingbelievable"],
  ];

  convertsExactly(EMPHASIS, "DoD-1");
});

// ---------------------------------------------------------------------------
describe("toPlainText — blocks", () => {
  const BLOCKS: Example[] = [
    ["B1", "# Title\n\nBody text", "Title\n\nBody text"],
    ["B2", "## Closed heading ##", "Closed heading"],
    ["B3", "#hashtag stays", "#hashtag stays"],
    ["B4", "Title\n=====\nBody", "Title\nBody"],
    ["B5", "> quoted line\n> > nested", "quoted line\nnested"],
    ["B6", "> - quoted item", "• quoted item"],
    [
      "B7",
      "- one\n- two\n  - nested\n* star\n+ plus",
      "• one\n• two\n  • nested\n• star\n• plus",
    ],
    ["B8", "1. first\n2) second", "1. first\n2) second"],
    ["B9", "Para one.\n\n***\n\nPara two.", "Para one.\n\nPara two."],
    ["B10", "# **Big** title\n- *item*", "Big title\n• item"],
  ];

  // The bullet is written as the escape • (U+2022) so the code point is unambiguous.
  convertsExactly(BLOCKS, "DoD-2");
});

// ---------------------------------------------------------------------------
describe("toPlainText — code and links", () => {
  const CODE_AND_LINKS: Example[] = [
    ["C1", "Use `code` here", "Use code here"],
    ["C2", "Run ``a`b`` now", "Run a`b now"],
    ["C3", "```js\nconst *a* = 1;\n```\nAfter", "const *a* = 1;\nAfter"],
    ["C4", "~~~\n# not a heading\n~~~", "# not a heading"],
    ["C5", "[the site](https://example.com \"Title\")", "the site"],
    ["C6", "![a map](map.png) here", "a map here"],
    ["C7", "See <https://example.com> now", "See https://example.com now"],
    ["C8", "[text][ref]\n\n[ref]: https://example.com", "text"],
  ];

  convertsExactly(CODE_AND_LINKS, "DoD-3");
});

// ---------------------------------------------------------------------------
describe("toPlainText — whitespace", () => {
  const WHITESPACE: Example[] = [
    ["W1", "Line one  \nLine two\\\nLine three", "Line one\nLine two\nLine three"],
    ["W2", "Crlf line\r\nnext\rlast", "Crlf line\nnext\nlast"],
    ["W3", "\n\n  \nText  \n\n\n\nMore\n\n", "Text\n\nMore"],
    ["W4", "", ""],
    // W5: a backslash ending the last line stays.
    ["W5", "Line a\\", "Line a\\"],
  ];

  convertsExactly(WHITESPACE, "DoD-4");
});

// ---------------------------------------------------------------------------
describe("toPlainText — left as typed", () => {
  const LEFT_AS_TYPED: Array<[id: string, input: string]> = [
    ["L1", "~~not strike~~ and | a | b |"],
    ["L2", "She said ((quietly)) hello. ((ooc))"],
    ["L3", "<b>raw</b> &amp; text"],
    ["L4", "Indented:\n\n    four spaces"],
    ["L5", "A plain line.\n\nAnother, with (parens) and 3.5 * 2."],
    ["L6", "First paragraph.\nSecond line.\n\nThird paragraph."],
  ];

  for (const [id, input] of LEFT_AS_TYPED) {
    it(`${id}: returns ${show(input)} byte-for-byte unchanged — DoD-5`, () => {
      expect(toPlainText(input)).toBe(input);
    });
  }
});

// ---------------------------------------------------------------------------
describe("plainText.ts is pure", () => {
  it("has no import statement, no re-export from a module and no require / dynamic import — DoD-6", () => {
    const source = readFileSync(PLAIN_TEXT_SOURCE, "utf8");
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

  it("names no react, mobx, @mantine/* or shared/ module specifier — DoD-6", () => {
    const source = readFileSync(PLAIN_TEXT_SOURCE, "utf8");
    const forbidden = /["'](?:react(?:\/[^"']*)?|react-dom(?:\/[^"']*)?|mobx(?:-react-lite)?|@mantine\/[^"']*|(?:\.\.?\/)+(?:[^"']*\/)?shared\/[^"']*)["']/;
    expect(source).not.toMatch(forbidden);
  });
});
