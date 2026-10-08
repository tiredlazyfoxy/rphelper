// The composer heights record (workspace-shell.md "Layout persistence", 2026-10-08): the
// pixel height the roleplayer dragged each composer's text area to — `chat` for the session
// composer, `start` for the character page's start composer. Persisted under its own key with
// the same posture as `workspaceLayout.ts` and `treeCollapse.ts` — a total read and a
// best-effort write over a minimal storage passed in as a parameter. Each field falls back to
// `null` (the host's default rows) independently; there is no upper clamp.
import type { LayoutStorage } from "./workspaceLayout";

/** Which composer a height belongs to. */
export type ComposerHeightField = "chat" | "start";

/** Per-composer pixel heights; `null` means "use the default line count". */
export type ComposerHeights = { chat: number | null; start: number | null };

/** The one key this record is stored under — separate from the other two layout records. */
export const COMPOSER_HEIGHTS_KEY = "rphelper.composer-heights";

/** Positive and finite, or `null`. */
function heightOf(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : null;
}

/**
 * Total and never throws: each field is independently `null` on a missing storage, a
 * throwing `getItem`, an absent key, unparseable JSON, a non-object (or array) payload, a
 * wrong type, or a non-finite or non-positive number. Unknown keys are dropped.
 */
export function readComposerHeights(storage: LayoutStorage | null): ComposerHeights {
  const empty: ComposerHeights = { chat: null, start: null };
  if (storage === null) {
    return empty;
  }
  let raw: string | null;
  try {
    raw = storage.getItem(COMPOSER_HEIGHTS_KEY);
  } catch {
    return empty;
  }
  if (raw === null) {
    return empty;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return empty;
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return empty;
  }
  const stored = parsed as Record<string, unknown>;
  return { chat: heightOf(stored.chat), start: heightOf(stored.start) };
}

/**
 * Best-effort: merges `field` = `height` over a fresh total read and stores the complete
 * record. A missing storage is a no-op, a non-finite or non-positive height writes nothing,
 * and a throwing `setItem` is swallowed (a throwing `getItem` still writes, over nulls).
 */
export function writeComposerHeight(
  storage: LayoutStorage | null,
  field: ComposerHeightField,
  height: number,
): void {
  if (storage === null || heightOf(height) === null) {
    return;
  }
  const next: ComposerHeights = { ...readComposerHeights(storage), [field]: height };
  try {
    storage.setItem(COMPOSER_HEIGHTS_KEY, JSON.stringify(next));
  } catch {
    // Best-effort: a full quota or a disabled storage is ignored.
  }
}
