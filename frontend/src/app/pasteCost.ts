// The enormous-paste estimate (feature 014, step 003, D3): a pure, DOM-free heuristic —
// characters divided by four, rounded up; enormous above 32,000 tokens. Advisory only.

export const CHARS_PER_TOKEN = 4;

export const PASTE_WARNING_THRESHOLD_TOKENS = 32_000;

/** The token estimate of a text: its `length` over `CHARS_PER_TOKEN`, rounded up (D3). */
export function estimateTokens(text: string): number {
  return Math.ceil(text.length / CHARS_PER_TOKEN);
}

/** True iff the estimate is strictly greater than the threshold (D3). No trimming. */
export function isEnormousPaste(text: string): boolean {
  return estimateTokens(text) > PASTE_WARNING_THRESHOLD_TOKENS;
}
