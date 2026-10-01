// The persisted workspace-layout record (008 context.md D8): a total read and a
// best-effort write over a minimal storage that is passed in as a parameter. This module
// imports nothing, so every fallback path is a plain unit test.

/** The persisted record. Both fields are always present on a read. */
export type WorkspaceLayout = {
  navCollapsed: boolean;
  wallPinned: boolean;
};

/** The minimal storage this module needs; the caller supplies the real one. */
export type LayoutStorage = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
};

/** The one key the record is stored under. */
export const WORKSPACE_LAYOUT_KEY = "rphelper.workspace-layout";

/** The per-field fallbacks every read path lands on. */
export const DEFAULT_WORKSPACE_LAYOUT: WorkspaceLayout = {
  navCollapsed: false,
  wallPinned: false,
};

/**
 * Total and never throws: a missing storage, a throwing `getItem`, an absent key,
 * unparseable JSON, a payload that is not a plain object, a wrong-typed field and a
 * missing field each fall back per field to `DEFAULT_WORKSPACE_LAYOUT`. Unknown stored
 * keys are ignored. Always a complete record, never `null`.
 */
export function readWorkspaceLayout(storage: LayoutStorage | null): WorkspaceLayout {
  const stored = readStored(storage);
  return {
    navCollapsed: booleanField(stored, "navCollapsed"),
    wallPinned: booleanField(stored, "wallPinned"),
  };
}

/** The stored payload as a plain object, or `null` for every unusable case. Never throws. */
function readStored(storage: LayoutStorage | null): Record<string, unknown> | null {
  if (storage === null) {
    return null;
  }
  let raw: string | null;
  try {
    raw = storage.getItem(WORKSPACE_LAYOUT_KEY);
  } catch {
    return null;
  }
  if (raw === null) {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return null;
  }
  return parsed as Record<string, unknown>;
}

/** Per-field fallback: anything but a boolean under `key` yields that field's default. */
function booleanField(stored: Record<string, unknown> | null, key: keyof WorkspaceLayout): boolean {
  const value = stored === null ? undefined : stored[key];
  return typeof value === "boolean" ? value : DEFAULT_WORKSPACE_LAYOUT[key];
}

/**
 * Best-effort: merges `patch` over a fresh `readWorkspaceLayout` of the same storage and
 * stores the resulting complete two-field record. Any throw is swallowed; a missing
 * storage is a no-op.
 */
export function writeWorkspaceLayout(
  storage: LayoutStorage | null,
  patch: Partial<WorkspaceLayout>,
): void {
  if (storage === null) {
    return;
  }
  try {
    const current = readWorkspaceLayout(storage);
    const next: WorkspaceLayout = {
      navCollapsed: patch.navCollapsed ?? current.navCollapsed,
      wallPinned: patch.wallPinned ?? current.wallPinned,
    };
    storage.setItem(WORKSPACE_LAYOUT_KEY, JSON.stringify(next));
  } catch {
    // Best-effort: a full quota, a disabled storage or an unserialisable value is ignored.
  }
}
