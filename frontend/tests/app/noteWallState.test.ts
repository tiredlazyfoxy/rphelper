// Feature 016, step 005 — the note wall's data class, its derivations and its actions
// (DoD-1..DoD-6; D2, US-094.AC-1/AC-2, UC-072 steps 4–5).
// DoD-7..DoD-11 (the layout component) live in tests/app/NoteWallLayout.test.tsx, DoD-12 in
// tests/stylesheets.test.ts; DoD-13 is [manual/live] and carries no test.
//
// No DOM is needed here. The storage is always a file-local in-memory `LayoutStorage` fake
// whose writes are recorded; writes are asserted by parsing the JSON stored under
// "rphelper.workspace-layout", never by calling `readWorkspaceLayout` for the expectation
// (016 context.md, "Test conventions").
import { runInAction } from "mobx";
import { describe, expect, it, vi } from "vitest";
import {
  createNoteWallState,
  dismissWall,
  isWallVisible,
  NoteWallState,
  openWall,
  sessionLayoutClassName,
  toggleWallPin,
  wallClassName,
  wallMode,
} from "../../src/app/noteWallState";
import type { LayoutStorage } from "../../src/app/workspaceLayout";

/** The record's key, spelled as the spec spells it (016 context.md). */
const LAYOUT_KEY = "rphelper.workspace-layout";

type GetItem = (key: string) => string | null;
type SetItem = (key: string, value: string) => void;

// ---------------------------------------------------------------- helpers

/** An in-memory `LayoutStorage` whose two members are spies. */
function fakeStorage(seed?: Record<string, string>) {
  const entries = new Map<string, string>(Object.entries(seed ?? {}));
  const getItem = vi.fn<GetItem>((key) => entries.get(key) ?? null);
  const setItem = vi.fn<SetItem>((key, value) => {
    entries.set(key, value);
  });
  const storage: LayoutStorage = { getItem, setItem };
  return { storage, getItem, setItem, entries };
}

/** A storage holding the given record under the layout key. */
function storageHolding(record: { navCollapsed: boolean; wallPinned: boolean }) {
  return fakeStorage({ [LAYOUT_KEY]: JSON.stringify(record) });
}

/** The record as stored, parsed from the raw JSON under the layout key. */
function storedRecord(entries: Map<string, string>): Record<string, unknown> {
  const raw = entries.get(LAYOUT_KEY);
  expect(raw).toBeDefined();
  return JSON.parse(raw ?? "null") as Record<string, unknown>;
}

/** A state in an exact condition; `open` is a plain observable field set inside an action. */
function stateOf(pinned: boolean, open: boolean): NoteWallState {
  const state = new NoteWallState(pinned);
  runInAction(() => {
    state.open = open;
  });
  return state;
}

// ---------------------------------------------------------------------------
describe("createNoteWallState starts from the persisted pin", () => {
  it("a stored wallPinned true starts pinned — DoD-1", () => {
    const { storage } = storageHolding({ navCollapsed: false, wallPinned: true });
    expect(createNoteWallState(storage).pinned).toBe(true);
  });

  it("a stored wallPinned true still starts closed — DoD-1", () => {
    const { storage } = storageHolding({ navCollapsed: false, wallPinned: true });
    expect(createNoteWallState(storage).open).toBe(false);
  });

  it("a stored wallPinned false starts unpinned and closed — DoD-1", () => {
    const { storage } = storageHolding({ navCollapsed: true, wallPinned: false });
    const state = createNoteWallState(storage);
    expect(state.pinned).toBe(false);
    expect(state.open).toBe(false);
  });

  it("null storage starts unpinned and closed — DoD-1", () => {
    const state = createNoteWallState(null);
    expect(state.pinned).toBe(false);
    expect(state.open).toBe(false);
  });

  it("an absent key starts unpinned and closed — DoD-1", () => {
    const state = createNoteWallState(fakeStorage().storage);
    expect(state.pinned).toBe(false);
    expect(state.open).toBe(false);
  });

  it("unparseable JSON under the key starts unpinned and closed — DoD-1", () => {
    const { storage } = fakeStorage({ [LAYOUT_KEY]: "{not json zq" });
    const state = createNoteWallState(storage);
    expect(state.pinned).toBe(false);
    expect(state.open).toBe(false);
  });

  it("creating a state writes nothing — DoD-1", () => {
    const { storage, setItem } = storageHolding({ navCollapsed: false, wallPinned: true });
    createNoteWallState(storage);
    expect(setItem).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("wallMode and isWallVisible over the full table", () => {
  // [pinned, narrow, open, mode, visible]
  const TABLE: Array<[boolean, boolean, boolean, "pinned" | "floating", boolean]> = [
    [true, false, false, "pinned", true],
    [true, false, true, "pinned", true],
    [true, true, false, "floating", false],
    [true, true, true, "floating", true],
    [false, false, false, "floating", false],
    [false, false, true, "floating", true],
    [false, true, false, "floating", false],
    [false, true, true, "floating", true],
  ];

  it.each(TABLE)(
    "pinned %s, narrow %s, open %s → mode %s — DoD-2",
    (pinned, narrow, open, mode) => {
      expect(wallMode(stateOf(pinned, open), narrow)).toBe(mode);
    },
  );

  it.each(TABLE)(
    "pinned %s, narrow %s, open %s (mode %s) → visible %s — DoD-2",
    (pinned, narrow, open, _mode, visible) => {
      expect(isWallVisible(stateOf(pinned, open), narrow)).toBe(visible);
    },
  );
});

// ---------------------------------------------------------------------------
describe("the two class derivations are the CSS contract", () => {
  it.each<[boolean]>([[false], [true]])(
    "pinned mode (wide, open %s): the root is exactly app-session wall-pinned — DoD-3",
    (open) => {
      expect(sessionLayoutClassName(stateOf(true, open), false)).toBe(
        "app-session wall-pinned",
      );
    },
  );

  it.each<[boolean, boolean, boolean]>([
    [true, true, false],
    [true, true, true],
    [false, false, false],
    [false, false, true],
    [false, true, false],
    [false, true, true],
  ])(
    "floating (pinned %s, narrow %s, open %s): the root is exactly app-session — DoD-3",
    (pinned, narrow, open) => {
      expect(sessionLayoutClassName(stateOf(pinned, open), narrow)).toBe("app-session");
    },
  );

  it.each<[boolean, boolean]>([
    [false, false],
    [false, true],
    [true, true],
  ])(
    "floating and visible (pinned %s, narrow %s, open): the wall is exactly app-wall wall-open — DoD-3",
    (pinned, narrow) => {
      expect(wallClassName(stateOf(pinned, true), narrow)).toBe("app-wall wall-open");
    },
  );

  it.each<[boolean]>([[false], [true]])(
    "pinned mode (wide, open %s): the wall is exactly app-wall — DoD-3",
    (open) => {
      expect(wallClassName(stateOf(true, open), false)).toBe("app-wall");
    },
  );

  it.each<[boolean, boolean]>([
    [false, false],
    [false, true],
    [true, true],
  ])(
    "floating and closed (pinned %s, narrow %s): the wall is exactly app-wall — DoD-3",
    (pinned, narrow) => {
      expect(wallClassName(stateOf(pinned, false), narrow)).toBe("app-wall");
    },
  );
});

// ---------------------------------------------------------------------------
describe("openWall opens and persists nothing", () => {
  it("sets open — DoD-4", () => {
    const state = stateOf(false, false);
    openWall(state);
    expect(state.open).toBe(true);
  });

  it("leaves pinned as it was — DoD-4", () => {
    const state = stateOf(false, false);
    openWall(state);
    expect(state.pinned).toBe(false);
  });

  it("makes no setItem call and leaves the stored record untouched — DoD-4", () => {
    const seeded = JSON.stringify({ navCollapsed: true, wallPinned: false });
    const { storage, setItem, entries } = fakeStorage({ [LAYOUT_KEY]: seeded });
    const state = createNoteWallState(storage);
    openWall(state);
    expect(state.open).toBe(true);
    expect(setItem).not.toHaveBeenCalled();
    expect(entries.get(LAYOUT_KEY)).toBe(seeded);
  });
});

// ---------------------------------------------------------------------------
describe("toggleWallPin pins and unpins, writing the record", () => {
  it("from unpinned sets pinned — DoD-5", () => {
    const { storage } = storageHolding({ navCollapsed: false, wallPinned: false });
    const state = createNoteWallState(storage);
    toggleWallPin(state, storage);
    expect(state.pinned).toBe(true);
  });

  it("from unpinned leaves open unchanged — DoD-5", () => {
    const { storage } = storageHolding({ navCollapsed: false, wallPinned: false });
    const state = createNoteWallState(storage);
    toggleWallPin(state, storage);
    expect(state.open).toBe(false);
  });

  it("from unpinned stores wallPinned true under rphelper.workspace-layout — DoD-5", () => {
    const { storage, entries } = storageHolding({ navCollapsed: false, wallPinned: false });
    toggleWallPin(createNoteWallState(storage), storage);
    expect(storedRecord(entries).wallPinned).toBe(true);
  });

  it("from unpinned into an empty storage stores wallPinned true — DoD-5", () => {
    const { storage, entries } = fakeStorage();
    toggleWallPin(createNoteWallState(storage), storage);
    expect(storedRecord(entries).wallPinned).toBe(true);
  });

  it("a stored navCollapsed true stays true in the same record — DoD-5", () => {
    const { storage, entries } = storageHolding({ navCollapsed: true, wallPinned: false });
    toggleWallPin(createNoteWallState(storage), storage);
    const record = storedRecord(entries);
    expect(record.navCollapsed).toBe(true);
    expect(record.wallPinned).toBe(true);
  });

  it("from pinned sets pinned false and open true — DoD-5", () => {
    const { storage } = storageHolding({ navCollapsed: false, wallPinned: true });
    const state = createNoteWallState(storage);
    toggleWallPin(state, storage);
    expect(state.pinned).toBe(false);
    expect(state.open).toBe(true);
  });

  it("from pinned stores wallPinned false — DoD-5", () => {
    const { storage, entries } = storageHolding({ navCollapsed: false, wallPinned: true });
    toggleWallPin(createNoteWallState(storage), storage);
    expect(storedRecord(entries).wallPinned).toBe(false);
  });

  it("from pinned keeps a stored navCollapsed true in the same record — DoD-5", () => {
    const { storage, entries } = storageHolding({ navCollapsed: true, wallPinned: true });
    toggleWallPin(createNoteWallState(storage), storage);
    const record = storedRecord(entries);
    expect(record.navCollapsed).toBe(true);
    expect(record.wallPinned).toBe(false);
  });

  it("pin then unpin leaves the wall floating and open — DoD-5", () => {
    const { storage, entries } = storageHolding({ navCollapsed: false, wallPinned: false });
    const state = createNoteWallState(storage);
    toggleWallPin(state, storage);
    toggleWallPin(state, storage);
    expect(state.pinned).toBe(false);
    expect(state.open).toBe(true);
    expect(wallMode(state, false)).toBe("floating");
    expect(isWallVisible(state, false)).toBe(true);
    expect(storedRecord(entries).wallPinned).toBe(false);
  });

  it("over null storage still toggles the state — DoD-5", () => {
    const state = createNoteWallState(null);
    toggleWallPin(state, null);
    expect(state.pinned).toBe(true);
    toggleWallPin(state, null);
    expect(state.pinned).toBe(false);
    expect(state.open).toBe(true);
  });
});

// ---------------------------------------------------------------------------
describe("dismissWall closes, and unpins only an effectively pinned wall", () => {
  it("pinned at wide width: sets open and pinned false — DoD-6", () => {
    const { storage } = storageHolding({ navCollapsed: false, wallPinned: true });
    const state = createNoteWallState(storage);
    dismissWall(state, storage, false);
    expect(state.open).toBe(false);
    expect(state.pinned).toBe(false);
  });

  it("pinned at wide width: stores wallPinned false — DoD-6", () => {
    const { storage, entries } = storageHolding({ navCollapsed: true, wallPinned: true });
    dismissWall(createNoteWallState(storage), storage, false);
    const record = storedRecord(entries);
    expect(record.wallPinned).toBe(false);
    expect(record.navCollapsed).toBe(true);
  });

  it("pinned at wide width: the wall is no longer visible — DoD-6", () => {
    const { storage } = storageHolding({ navCollapsed: false, wallPinned: true });
    const state = createNoteWallState(storage);
    dismissWall(state, storage, false);
    expect(isWallVisible(state, false)).toBe(false);
  });

  it("pinned at narrow width and open: sets open false, leaves pinned true — DoD-6", () => {
    const { storage } = storageHolding({ navCollapsed: false, wallPinned: true });
    const state = createNoteWallState(storage);
    openWall(state);
    dismissWall(state, storage, true);
    expect(state.open).toBe(false);
    expect(state.pinned).toBe(true);
  });

  it("pinned at narrow width and open: writes nothing — DoD-6", () => {
    const seeded = JSON.stringify({ navCollapsed: false, wallPinned: true });
    const { storage, setItem, entries } = fakeStorage({ [LAYOUT_KEY]: seeded });
    const state = createNoteWallState(storage);
    openWall(state);
    dismissWall(state, storage, true);
    expect(setItem).not.toHaveBeenCalled();
    expect(entries.get(LAYOUT_KEY)).toBe(seeded);
  });

  it("pinned at narrow width: widening again restores the pinned column — DoD-6", () => {
    const { storage } = storageHolding({ navCollapsed: false, wallPinned: true });
    const state = createNoteWallState(storage);
    openWall(state);
    dismissWall(state, storage, true);
    expect(wallMode(state, false)).toBe("pinned");
  });

  it("unpinned and open: sets open false — DoD-6", () => {
    const { storage } = storageHolding({ navCollapsed: false, wallPinned: false });
    const state = createNoteWallState(storage);
    openWall(state);
    dismissWall(state, storage, false);
    expect(state.open).toBe(false);
    expect(state.pinned).toBe(false);
  });

  it.each<[boolean]>([[false], [true]])(
    "unpinned and open (narrow %s): writes nothing — DoD-6",
    (narrow) => {
      const { storage, setItem } = storageHolding({ navCollapsed: false, wallPinned: false });
      const state = createNoteWallState(storage);
      openWall(state);
      dismissWall(state, storage, narrow);
      expect(state.open).toBe(false);
      expect(setItem).not.toHaveBeenCalled();
    },
  );
});
