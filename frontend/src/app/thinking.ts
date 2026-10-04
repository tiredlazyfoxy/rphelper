// The pure, DOM-free think-segment parser (022 D4, consistent with 021 D4). Splits an
// assistant text into ordered think and answer segments. Tags are exactly `<think>` and
// `</think>`, case-sensitive. It never throws and never touches markdown or `(( ))`.

/** The opening think tag, exactly as the model emits it. */
export const THINK_OPEN = "<think>";

/** The closing think tag, exactly as the model emits it. */
export const THINK_CLOSE = "</think>";

/** One piece of a parsed assistant text. */
export type ThinkingSegment =
  | { kind: "answer"; text: string }
  | { kind: "think"; text: string; closed: boolean };

/** Splits `text` into ordered think / answer segments per 022 D4. */
export function splitThinking(text: string): ThinkingSegment[] {
  const segments: ThinkingSegment[] = [];
  let position = 0;
  let found = false;
  while (position <= text.length) {
    const open = text.indexOf(THINK_OPEN, position);
    if (open === -1) break;
    found = true;
    pushAnswer(segments, text.slice(position, open));
    const bodyStart = open + THINK_OPEN.length;
    const close = text.indexOf(THINK_CLOSE, bodyStart);
    if (close === -1) {
      segments.push({ kind: "think", text: text.slice(bodyStart), closed: false });
      return segments;
    }
    segments.push({ kind: "think", text: text.slice(bodyStart, close), closed: true });
    position = close + THINK_CLOSE.length;
  }
  if (!found) return [{ kind: "answer", text }];
  pushAnswer(segments, text.slice(position));
  return segments;
}

/** Appends a trimmed answer piece, dropping it when empty (only once a block was found). */
function pushAnswer(segments: ThinkingSegment[], piece: string): void {
  const trimmed = piece.trim();
  if (trimmed !== "") segments.push({ kind: "answer", text: trimmed });
}
