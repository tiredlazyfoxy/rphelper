// The `(( ))` rules (feature 013, step 001; D1): a pure, DOM-free port of 012 D8 / 012
// `003.context.md` "The parser, as spec". Classifies a text as a decision or a turn, segments
// it into prose and fragments, strips fragments, and previews what a settle would file.
// This module imports nothing (DoD-10).

/** Which side of the `(( ))` scan a segment came from. */
export type ParenSegmentKind = "prose" | "fragment";

/** One segment of a text, verbatim; a fragment's text includes its `((` and `))`. */
export type ParenSegment = {
  kind: ParenSegmentKind;
  text: string;
};

/** What a settle of a text would file, and whether fragments would be stripped. */
export type SettlePreview = {
  kind: "turn" | "decision";
  strips: boolean;
};

/** A fragment: the shortest `((`…`))` span, left to right, across line breaks. */
const FRAGMENT_PATTERN = /\(\([\s\S]*?\)\)/g;

/** Spaces / tabs at the end of a prose run (never line breaks). */
const TRAILING_BLANKS = /[ \t]+$/;

/** A run of three or more line breaks with only spaces / tabs between them. */
const LINE_BREAK_RUN = /\n(?:[ \t]*\n){2,}/g;

/** The decision rule: the trimmed text starts with `((` and ends with `))`. */
export function isWhollyParenthesised(text: string): boolean {
  const trimmed = text.trim();
  return trimmed.startsWith("((") && trimmed.endsWith("))");
}

/** The one fragment scanner: the text's prose / fragment segments, in order. */
export function splitParenSegments(text: string): ParenSegment[] {
  const segments: ParenSegment[] = [];
  const pattern = new RegExp(FRAGMENT_PATTERN.source, "g");
  let cursor = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) {
      segments.push({ kind: "prose", text: text.slice(cursor, match.index) });
    }
    segments.push({ kind: "fragment", text: match[0] });
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length) {
    segments.push({ kind: "prose", text: text.slice(cursor) });
  }
  return segments;
}

/** 012's four-step strip; does not consult the decision rule. */
export function stripFragments(text: string): string {
  const segments = splitParenSegments(text);
  // (1) No fragment: unchanged.
  if (!segments.some((segment) => segment.kind === "fragment")) {
    return text;
  }
  // (2) Remove each fragment and the run of spaces / tabs immediately before it.
  let stripped = "";
  segments.forEach((segment, index) => {
    if (segment.kind === "fragment") {
      return;
    }
    const next = segments[index + 1];
    stripped +=
      next !== undefined && next.kind === "fragment"
        ? segment.text.replace(TRAILING_BLANKS, "")
        : segment.text;
  });
  // (3) Collapse line-break runs of three or more to one blank line; (4) trim.
  return stripped.replace(LINE_BREAK_RUN, "\n\n").trim();
}

/** The kind a settle of this text would file, and whether it would strip fragments. */
export function previewSettle(text: string): SettlePreview {
  if (isWhollyParenthesised(text)) {
    return { kind: "decision", strips: false };
  }
  const strips = splitParenSegments(text).some((segment) => segment.kind === "fragment");
  return { kind: "turn", strips };
}
