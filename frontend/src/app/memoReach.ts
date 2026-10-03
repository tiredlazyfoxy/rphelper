// The memo reach helper (feature 015, step 005; D7, R3): a pure derivation of where a note
// reaches from its two flags, `is_enabled` checked first, and its one-line statement. The
// three statements live here only; components render `reachStatement(...)`.

/** Where a note reaches the assistant. */
export type MemoReach = "forced" | "searchable" | "disabled";

/** Anything carrying the two reach flags (a `Memo`, or whatever a future card holds). */
export type MemoReachFlags = {
  is_enabled: boolean;
  is_forced: boolean;
};

const REACH_STATEMENTS: Record<MemoReach, string> = {
  forced: "Forced: always given to the assistant.",
  searchable: "Searchable: found only when the assistant searches.",
  disabled: "Disabled: never reaches the assistant.",
};

/** Pure: not enabled → "disabled"; enabled and forced → "forced"; else "searchable". */
export function memoReach(memo: MemoReachFlags): MemoReach {
  if (!memo.is_enabled) {
    return "disabled";
  }
  return memo.is_forced ? "forced" : "searchable";
}

/** Pure: the one-line statement for a reach (context.md UI strings table). */
export function reachStatement(reach: MemoReach): string {
  return REACH_STATEMENTS[reach];
}
