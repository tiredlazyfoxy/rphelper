// Markdown-to-plain-text (feature 014, step 002; D8): a pure, DOM-free, dependency-free
// stripper of CommonMark syntax that keeps the author's words and line structure, per
// `002.context.md` "The stripping rules, as spec". This module imports nothing.

/** A line after stage A; code lines are kept exactly and never touched again. */
type Line = { text: string; code: boolean };

/** One character of a paragraph; protected characters (B1, B2) never act as syntax. */
type Cell = { c: string; p: boolean };

/** A2 — a fence opener: a run of 3+ backticks or 3+ tildes after at most three spaces. */
const FENCE_OPEN = /^[ \t]{0,3}(`{3,}|~{3,})/;

/** A3 — one blockquote marker and the single space after it. */
const BLOCKQUOTE = /^[ \t]{0,3}>[ \t]?/;

/** A4 — a thematic break: three or more of one of `-`, `*`, `_`, optionally spaced. */
const THEMATIC_BREAK = /^[ \t]{0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$/;

/** A4 — a setext underline (dropped only after a non-blank, non-code line). */
const SETEXT_UNDERLINE = /^[ \t]{0,3}(?:=+|-+)[ \t]*$/;

/** A4 — a link reference definition. */
const LINK_DEFINITION = /^[ \t]{0,3}\[[^\]]+\]:[ \t]*\S/;

/** A5 — an ATX heading's opening hashes and the spaces after them. */
const ATX_OPEN = /^([ \t]{0,3})#{1,6}(?:[ \t]+|$)/;

/** A5 — an ATX heading's optional closing hashes. */
const ATX_CLOSE = /[ \t]+#+[ \t]*$/;

/** A6 — an unordered list bullet after any indentation. */
const BULLET = /^([ \t]*)[-*+][ \t]+/;

/** A7 — trailing spaces. */
const TRAILING_SPACES = /[ \t]+$/;

/** A7 — a line ending in a single (unescaped) backslash. */
const HARD_BREAK_BACKSLASH = /(?:^|[^\\])(?:\\\\)*\\$/;

/** B2 — ASCII punctuation. */
const ASCII_PUNCTUATION = /^[!-/:-@[-`{-~]$/;

const WHITESPACE = /\s/u;
const LETTER_OR_DIGIT = /[\p{L}\p{N}]/u;

/** Returns the plain-text form of a settled text. Never throws; never alters `(( ))`. */
export function toPlainText(text: string): string {
  if (text === "") return "";
  const kept = finishLineEnds(applyLineRules(text));
  return tidyWhitespace(applyInlineRules(kept));
}

// ---- Stage A — lines -----------------------------------------------------------------

function isBlank(line: Line | undefined): boolean {
  return line === undefined || line.code || line.text.trim() === "";
}

function isFenceClose(line: string, fence: { ch: string; len: number }): boolean {
  const match = /^[ \t]{0,3}(`+|~+)[ \t]*$/.exec(line);
  if (match === null) return false;
  const run = match[1];
  return run.charAt(0) === fence.ch && run.length >= fence.len;
}

/** A1–A6: line endings, fences, blockquotes, dropped lines, headings, bullets. */
function applyLineRules(text: string): Line[] {
  const lines = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  const kept: Line[] = [];
  let fence: { ch: string; len: number } | null = null;
  for (const raw of lines) {
    if (fence !== null) {
      if (isFenceClose(raw, fence)) fence = null;
      else kept.push({ text: raw, code: true });
      continue;
    }
    const open = FENCE_OPEN.exec(raw);
    if (open !== null) {
      fence = { ch: open[1].charAt(0), len: open[1].length };
      continue;
    }
    let line = raw;
    for (let quote = BLOCKQUOTE.exec(line); quote !== null; quote = BLOCKQUOTE.exec(line)) {
      line = line.slice(quote[0].length);
    }
    if (THEMATIC_BREAK.test(line)) continue;
    if (SETEXT_UNDERLINE.test(line) && !isBlank(kept[kept.length - 1])) continue;
    if (LINK_DEFINITION.test(line)) continue;
    const heading = ATX_OPEN.exec(line);
    if (heading !== null) {
      line = heading[1] + line.slice(heading[0].length);
      line = line.replace(ATX_CLOSE, "");
    }
    line = line.replace(BULLET, "$1• ");
    kept.push({ text: line, code: false });
  }
  return kept;
}

/** A7: trailing spaces removed; a single trailing backslash before a text line removed. */
function finishLineEnds(kept: Line[]): Line[] {
  return kept.map((line, index) => {
    if (line.code) return line;
    let text = line.text.replace(TRAILING_SPACES, "");
    if (HARD_BREAK_BACKSLASH.test(text) && !isBlank(kept[index + 1])) {
      text = text.slice(0, -1);
    }
    return { text, code: false };
  });
}

// ---- Stage B — inline, per paragraph -------------------------------------------------

function applyInlineRules(kept: Line[]): Line[] {
  const out: Line[] = [];
  let paragraph: string[] = [];
  const flush = (): void => {
    if (paragraph.length === 0) return;
    for (const text of stripInline(paragraph.join("\n")).split("\n")) {
      out.push({ text, code: false });
    }
    paragraph = [];
  };
  for (const line of kept) {
    if (line.code || line.text === "") {
      flush();
      out.push(line);
    } else {
      paragraph.push(line.text);
    }
  }
  flush();
  return out;
}

function stripInline(paragraph: string): string {
  let cells = escapes(codeSpans(paragraph));
  cells = linkLike(cells, true);
  cells = linkLike(cells, false);
  cells = autolinks(cells);
  for (const size of [3, 2, 1]) cells = emphasis(cells, size);
  return cells.map((cell) => cell.c).join("");
}

/** True when `cells[i]` is the unprotected character `ch`. */
function isAt(cells: Cell[], i: number, ch: string): boolean {
  const cell = cells[i];
  return cell !== undefined && !cell.p && cell.c === ch;
}

function runLength(chars: string[], from: number, ch: string): number {
  let end = from;
  while (end < chars.length && chars[end] === ch) end++;
  return end - from;
}

/** B1: code spans — content kept verbatim and protected; unmatched runs stay literal. */
function codeSpans(text: string): Cell[] {
  const chars = Array.from(text);
  const cells: Cell[] = [];
  let i = 0;
  while (i < chars.length) {
    if (chars[i] !== "`") {
      cells.push({ c: chars[i], p: false });
      i++;
      continue;
    }
    const size = runLength(chars, i, "`");
    let close = -1;
    let j = i + size;
    while (j < chars.length) {
      if (chars[j] !== "`") {
        j++;
        continue;
      }
      const length = runLength(chars, j, "`");
      if (length === size) {
        close = j;
        break;
      }
      j += length;
    }
    if (close < 0) {
      for (let k = 0; k < size; k++) cells.push({ c: "`", p: false });
      i += size;
      continue;
    }
    for (let k = i + size; k < close; k++) cells.push({ c: chars[k], p: true });
    i = close + size;
  }
  return cells;
}

/** B2: backslash escapes of ASCII punctuation become the character, protected. */
function escapes(cells: Cell[]): Cell[] {
  const out: Cell[] = [];
  let i = 0;
  while (i < cells.length) {
    const next = cells[i + 1];
    if (isAt(cells, i, "\\") && next !== undefined && !next.p && ASCII_PUNCTUATION.test(next.c)) {
      out.push({ c: next.c, p: true });
      i += 2;
      continue;
    }
    out.push(cells[i]);
    i++;
  }
  return out;
}

function skipSpaces(cells: Cell[], from: number): number {
  let i = from;
  while (i < cells.length && (cells[i].c === " " || cells[i].c === "\t")) i++;
  return i;
}

/** The index of the `]` matching the `[` at `open`, or -1. */
function matchBracket(cells: Cell[], open: number): number {
  let depth = 0;
  for (let i = open; i < cells.length; i++) {
    if (isAt(cells, i, "[")) depth++;
    else if (isAt(cells, i, "]")) {
      depth--;
      if (depth === 0) return i;
    }
  }
  return -1;
}

/** `(destination)` or `(destination "title")` at `from`; the index after `)`, or -1. */
function inlineTail(cells: Cell[], from: number): number {
  if (!isAt(cells, from, "(")) return -1;
  let i = skipSpaces(cells, from + 1);
  if (isAt(cells, i, "<")) {
    i++;
    while (i < cells.length && !isAt(cells, i, ">")) {
      if (cells[i].c === "\n" || isAt(cells, i, "<")) return -1;
      i++;
    }
    if (i >= cells.length) return -1;
    i++;
  } else {
    let depth = 0;
    while (i < cells.length && !WHITESPACE.test(cells[i].c)) {
      if (isAt(cells, i, "(")) depth++;
      else if (isAt(cells, i, ")")) {
        if (depth === 0) break;
        depth--;
      }
      i++;
    }
  }
  const afterDestination = i;
  i = skipSpaces(cells, i);
  if (i > afterDestination && (isAt(cells, i, '"') || isAt(cells, i, "'"))) {
    const quote = cells[i].c;
    i++;
    while (i < cells.length && !isAt(cells, i, quote)) i++;
    if (i >= cells.length) return -1;
    i = skipSpaces(cells, i + 1);
  }
  return isAt(cells, i, ")") ? i + 1 : -1;
}

/** `[label]` or `[]` at `from`; the index after `]`, or -1. */
function referenceTail(cells: Cell[], from: number): number {
  if (!isAt(cells, from, "[")) return -1;
  for (let i = from + 1; i < cells.length; i++) {
    if (isAt(cells, i, "[")) return -1;
    if (isAt(cells, i, "]")) return i + 1;
  }
  return -1;
}

/** B3 (images) / B4 (links): the construct becomes its bracketed text. */
function linkLike(cells: Cell[], image: boolean): Cell[] {
  const out: Cell[] = [];
  let i = 0;
  while (i < cells.length) {
    const open = image
      ? isAt(cells, i, "!") && isAt(cells, i + 1, "[")
        ? i + 1
        : -1
      : isAt(cells, i, "[")
        ? i
        : -1;
    if (open >= 0) {
      const close = matchBracket(cells, open);
      if (close >= 0) {
        let end = inlineTail(cells, close + 1);
        if (end < 0 && !image) end = referenceTail(cells, close + 1);
        if (end >= 0) {
          out.push(...cells.slice(open + 1, close));
          i = end;
          continue;
        }
      }
    }
    out.push(cells[i]);
    i++;
  }
  return out;
}

/** B5: `<…>` with no whitespace or angle brackets inside and a `:` or `@` → its inside. */
function autolinks(cells: Cell[]): Cell[] {
  const out: Cell[] = [];
  let i = 0;
  while (i < cells.length) {
    if (isAt(cells, i, "<")) {
      let j = i + 1;
      let valid = true;
      let marked = false;
      while (j < cells.length && !isAt(cells, j, ">")) {
        const c = cells[j].c;
        if (WHITESPACE.test(c) || c === "<" || c === ">") {
          valid = false;
          break;
        }
        if (c === ":" || c === "@") marked = true;
        j++;
      }
      if (valid && marked && j < cells.length) {
        out.push(...cells.slice(i + 1, j));
        i = j + 1;
        continue;
      }
    }
    out.push(cells[i]);
    i++;
  }
  return out;
}

/** The delimiter character when `cells[i..i+size)` is an unprotected `*`/`_` string. */
function delimiterAt(cells: Cell[], i: number, size: number): string | null {
  const first = cells[i];
  if (first === undefined || first.p || (first.c !== "*" && first.c !== "_")) return null;
  for (let k = 1; k < size; k++) {
    if (!isAt(cells, i + k, first.c)) return null;
  }
  return first.c;
}

function isWhitespaceCell(cell: Cell | undefined): boolean {
  return cell === undefined || WHITESPACE.test(cell.c);
}

function isLetterOrDigitCell(cell: Cell | undefined): boolean {
  return cell !== undefined && LETTER_OR_DIGIT.test(cell.c);
}

/** B6: one emphasis pass with delimiter strings of `size` characters. */
function emphasis(cells: Cell[], size: number): Cell[] {
  const out: Cell[] = [];
  let i = 0;
  while (i < cells.length) {
    const ch = delimiterAt(cells, i, size);
    if (
      ch !== null &&
      !isWhitespaceCell(cells[i + size]) &&
      !(ch === "_" && isLetterOrDigitCell(cells[i - 1]))
    ) {
      let close = -1;
      for (let j = i + size + 1; j + size <= cells.length; j++) {
        if (
          delimiterAt(cells, j, size) === ch &&
          !isWhitespaceCell(cells[j - 1]) &&
          !(ch === "_" && isLetterOrDigitCell(cells[j + size]))
        ) {
          close = j;
          break;
        }
      }
      if (close >= 0) {
        out.push(...cells.slice(i + size, close));
        i = close + size;
        continue;
      }
    }
    out.push(cells[i]);
    i++;
  }
  return out;
}

// ---- Stage C — whitespace ------------------------------------------------------------

/** C1–C2: blank-line runs collapsed, outer blank lines removed, joined with `\n`. */
function tidyWhitespace(lines: Line[]): string {
  const collapsed: Line[] = [];
  let previousBlank = false;
  for (const line of lines) {
    const blank = !line.code && line.text === "";
    if (blank && previousBlank) continue;
    collapsed.push(line);
    previousBlank = blank;
  }
  let start = 0;
  let end = collapsed.length;
  while (start < end && collapsed[start].text === "") start++;
  while (end > start && collapsed[end - 1].text === "") end--;
  return collapsed
    .slice(start, end)
    .map((line) => line.text)
    .join("\n");
}
