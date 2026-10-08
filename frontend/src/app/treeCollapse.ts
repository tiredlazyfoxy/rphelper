// The collapsed-characters record (feature 011, step 005, D7): which characters the tree
// shows with their session rows hidden. Persisted under its own key, with the same posture as
// `workspaceLayout.ts` — a total read and a best-effort write over a minimal storage that is
// passed in as a parameter, so every fallback path is a plain unit test. It is deliberately
// not a field of 008's workspace-layout record, whose reader drops unknown keys by design.
// The record is the whole collapsed set, so a write replaces it: there is no patch or merge.
// Nothing is pruned — an id for an archived or missing character stays harmlessly, and
// pruning would need a character list this module must not know about. Ids stay strings:
// non-string entries are dropped, never converted.
import type { LayoutStorage } from "./workspaceLayout";

/** The one key this record is stored under — separate from the workspace-layout record's. */
export const TREE_COLLAPSED_KEY = "rphelper.tree-collapsed";

/**
 * Total and never throws: a missing storage, a throwing `getItem`, an absent key,
 * unparseable JSON and a stored value that is not a JSON array each yield an empty array.
 * From an array it keeps only string entries, drops duplicates and preserves first-seen
 * order. Reads no key but `TREE_COLLAPSED_KEY`.
 */
export function readCollapsedCharacters(storage: LayoutStorage | null): string[] {
  if (storage === null) {
    return [];
  }
  let raw: string | null;
  try {
    raw = storage.getItem(TREE_COLLAPSED_KEY);
  } catch {
    return [];
  }
  if (raw === null) {
    return [];
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(parsed)) {
    return [];
  }
  const collapsed: string[] = [];
  for (const entry of parsed as readonly unknown[]) {
    if (typeof entry === "string" && !collapsed.includes(entry)) {
      collapsed.push(entry);
    }
  }
  return collapsed;
}

/**
 * Best-effort: stores `ids` as a JSON array under `TREE_COLLAPSED_KEY`, replacing whatever
 * was there. Any throw is swallowed, a missing storage is a no-op, and no other key is
 * written.
 */
export function writeCollapsedCharacters(
  storage: LayoutStorage | null,
  ids: readonly string[],
): void {
  if (storage === null) {
    return;
  }
  try {
    storage.setItem(TREE_COLLAPSED_KEY, JSON.stringify(ids));
  } catch {
    // Best-effort: a full quota or a disabled storage is ignored.
  }
}

/**
 * Pure: returns a new array with `characterId` appended when absent from `ids`, or removed
 * when present. Never mutates its input.
 */
export function toggleCollapsedCharacter(ids: readonly string[], characterId: string): string[] {
  if (ids.includes(characterId)) {
    return ids.filter((candidate) => candidate !== characterId);
  }
  return [...ids, characterId];
}
