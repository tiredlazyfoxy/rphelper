// Feature 008, step 001 — the persisted workspace-layout record (DoD-5..DoD-12; UC-070).
// DoD-13 (the module is DOM-free) lives in tests/app/entryIsolation.test.ts, together with
// DoD-4; DoD-1 and DoD-2 in tests/shared/currentUser.test.ts; DoD-3 in tests/admin/adminAccess.test.ts.
//
// The storage is a parameter, never a global (context.md D8): every clause below passes a
// small in-memory fake with spy-able getItem/setItem, or `null`. jsdom's own localStorage is
// deliberately not used — the module touches no DOM.
import { describe, expect, it, vi } from "vitest";
import {
  DEFAULT_WORKSPACE_LAYOUT,
  readWorkspaceLayout,
  WORKSPACE_LAYOUT_KEY,
  writeWorkspaceLayout,
  type LayoutStorage,
} from "../../src/app/workspaceLayout";

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

/** A storage holding `raw` verbatim under the record's key. */
function seededRaw(raw: string) {
  return fakeStorage({ [WORKSPACE_LAYOUT_KEY]: raw });
}

/** A storage holding `JSON.stringify(payload)` under the record's key. */
function seeded(payload: unknown) {
  return seededRaw(JSON.stringify(payload));
}

/** A storage whose `getItem` throws; its `setItem` records nothing and is inert. */
function throwingReadStorage(): LayoutStorage {
  return {
    getItem(): string | null {
      throw new Error("getItem is unavailable zq-read");
    },
    setItem(): void {},
  };
}

/** A readable storage whose `setItem` throws (a full or denied quota). */
function throwingWriteStorage(seed?: Record<string, string>): LayoutStorage {
  const entries = new Map<string, string>(Object.entries(seed ?? {}));
  return {
    getItem(key: string): string | null {
      return entries.get(key) ?? null;
    },
    setItem(): void {
      throw new Error("setItem is unavailable zq-write");
    },
  };
}

const DEFAULTS = { navCollapsed: false, wallPinned: false };

// ---------------------------------------------------------------------------
describe("the key and the defaults are the agreed ones", () => {
  it("the key is rphelper.workspace-layout — DoD-9", () => {
    expect(WORKSPACE_LAYOUT_KEY).toBe("rphelper.workspace-layout");
  });

  it("both fields default to false — DoD-5", () => {
    expect(DEFAULT_WORKSPACE_LAYOUT).toEqual(DEFAULTS);
  });
});

// ---------------------------------------------------------------------------
describe("the read is total: no storage, no value, and an unusable storage", () => {
  it("a null storage yields the defaults — DoD-5", () => {
    expect(readWorkspaceLayout(null)).toEqual(DEFAULTS);
  });

  it("a storage with no value under the key yields the defaults — DoD-5", () => {
    const { storage } = fakeStorage();
    expect(readWorkspaceLayout(storage)).toEqual(DEFAULTS);
  });

  it("a storage holding other keys only yields the defaults — DoD-5", () => {
    const { storage } = fakeStorage({ "rphelper.color-scheme": "dark" });
    expect(readWorkspaceLayout(storage)).toEqual(DEFAULTS);
  });

  it("a storage whose getItem throws yields the defaults and does not throw — DoD-5", () => {
    const storage = throwingReadStorage();
    expect(() => readWorkspaceLayout(storage)).not.toThrow();
    expect(readWorkspaceLayout(storage)).toEqual(DEFAULTS);
  });
});

// ---------------------------------------------------------------------------
describe("the read is total: a stored value that is not a record", () => {
  const NOT_A_RECORD: Array<[string, string]> = [
    ["unparseable JSON", "{ navCollapsed: true, "],
    ["an empty string", ""],
    ["an array", "[true, false]"],
    ["an array of records", '[{"navCollapsed":true,"wallPinned":true}]'],
    ["a string", '"navCollapsed"'],
    ["a number", "42"],
    ["null", "null"],
    ["a boolean", "true"],
  ];

  it.each(NOT_A_RECORD)("a stored %s yields the defaults — DoD-6", (_name, raw) => {
    const { storage } = seededRaw(raw);
    expect(readWorkspaceLayout(storage)).toEqual(DEFAULTS);
  });

  it.each(NOT_A_RECORD)("a stored %s never throws — DoD-6", (_name, raw) => {
    const { storage } = seededRaw(raw);
    expect(() => readWorkspaceLayout(storage)).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
describe("the read falls back per field", () => {
  it("a valid navCollapsed survives a non-boolean wallPinned — DoD-7", () => {
    const { storage } = seeded({ navCollapsed: true, wallPinned: "true" });
    expect(readWorkspaceLayout(storage)).toEqual({ navCollapsed: true, wallPinned: false });
  });

  it("a valid wallPinned survives a non-boolean navCollapsed — DoD-7", () => {
    const { storage } = seeded({ navCollapsed: 1, wallPinned: true });
    expect(readWorkspaceLayout(storage)).toEqual({ navCollapsed: false, wallPinned: true });
  });

  it("a record missing wallPinned keeps the stored navCollapsed — DoD-7", () => {
    const { storage } = seeded({ navCollapsed: true });
    expect(readWorkspaceLayout(storage)).toEqual({ navCollapsed: true, wallPinned: false });
  });

  it("a record missing navCollapsed keeps the stored wallPinned — DoD-7", () => {
    const { storage } = seeded({ wallPinned: true });
    expect(readWorkspaceLayout(storage)).toEqual({ navCollapsed: false, wallPinned: true });
  });

  it("a record with both fields stored returns both — DoD-7", () => {
    const { storage } = seeded({ navCollapsed: true, wallPinned: true });
    expect(readWorkspaceLayout(storage)).toEqual({ navCollapsed: true, wallPinned: true });
  });

  it("an empty record yields the defaults — DoD-7", () => {
    const { storage } = seeded({});
    expect(readWorkspaceLayout(storage)).toEqual(DEFAULTS);
  });

  it("a null field value falls back to that field's default — DoD-7", () => {
    const { storage } = seeded({ navCollapsed: null, wallPinned: true });
    expect(readWorkspaceLayout(storage)).toEqual({ navCollapsed: false, wallPinned: true });
  });
});

// ---------------------------------------------------------------------------
describe("the read tolerates and ignores unknown keys", () => {
  it("asideWidth and answerBoxHeight beside both known fields are ignored — DoD-8", () => {
    const { storage } = seeded({
      asideWidth: 320,
      answerBoxHeight: 180,
      navCollapsed: true,
      wallPinned: true,
    });
    expect(readWorkspaceLayout(storage)).toEqual({ navCollapsed: true, wallPinned: true });
  });

  it("the result carries no key besides navCollapsed and wallPinned — DoD-8", () => {
    const { storage } = seeded({
      asideWidth: 320,
      answerBoxHeight: 180,
      navCollapsed: true,
      wallPinned: true,
      somethingElse: "zq-77",
    });
    expect(Object.keys(readWorkspaceLayout(storage)).sort()).toEqual(["navCollapsed", "wallPinned"]);
  });

  it("an unknown key never fails the parse of the known fields — DoD-8", () => {
    const { storage } = seeded({ asideWidth: "wide", navCollapsed: true });
    expect(readWorkspaceLayout(storage)).toEqual({ navCollapsed: true, wallPinned: false });
  });
});

// ---------------------------------------------------------------------------
describe("the read asks for one key and no other", () => {
  it("only rphelper.workspace-layout is requested — DoD-9", () => {
    const { storage, getItem } = seeded({ navCollapsed: true, wallPinned: true });
    readWorkspaceLayout(storage);
    const keys = getItem.mock.calls.map(([key]) => key);
    expect(keys.length).toBeGreaterThan(0);
    expect([...new Set(keys)]).toEqual([WORKSPACE_LAYOUT_KEY]);
  });

  it("an absent value is still only one key asked for — DoD-9", () => {
    const { storage, getItem } = fakeStorage();
    readWorkspaceLayout(storage);
    const keys = getItem.mock.calls.map(([key]) => key);
    expect(keys.length).toBeGreaterThan(0);
    expect([...new Set(keys)]).toEqual([WORKSPACE_LAYOUT_KEY]);
  });
});

// ---------------------------------------------------------------------------
describe("the write merges a patch over a fresh read of the same storage", () => {
  it("a navCollapsed patch stores the patched value under the key — DoD-10", () => {
    const { storage, setItem } = seeded({ navCollapsed: false, wallPinned: true });
    writeWorkspaceLayout(storage, { navCollapsed: true });
    expect(setItem.mock.calls).toEqual([[WORKSPACE_LAYOUT_KEY, expect.any(String)]]);
    expect(JSON.parse(setItem.mock.calls[0][1]) as unknown).toEqual({ navCollapsed: true, wallPinned: true });
  });

  it("a navCollapsed patch keeps the previously stored wallPinned — DoD-10", () => {
    const { storage } = seeded({ navCollapsed: false, wallPinned: true });
    writeWorkspaceLayout(storage, { navCollapsed: true });
    expect(readWorkspaceLayout(storage)).toEqual({ navCollapsed: true, wallPinned: true });
  });

  it("a navCollapsed patch over an empty storage round-trips with the other default — DoD-10", () => {
    const { storage } = fakeStorage();
    writeWorkspaceLayout(storage, { navCollapsed: true });
    expect(readWorkspaceLayout(storage)).toEqual({ navCollapsed: true, wallPinned: false });
  });

  it("a wallPinned patch keeps the previously stored navCollapsed — DoD-10", () => {
    const { storage } = seeded({ navCollapsed: true, wallPinned: false });
    writeWorkspaceLayout(storage, { wallPinned: true });
    expect(readWorkspaceLayout(storage)).toEqual({ navCollapsed: true, wallPinned: true });
  });

  it("a patch of both fields stores both — DoD-10", () => {
    const { storage } = seeded({ navCollapsed: false, wallPinned: false });
    writeWorkspaceLayout(storage, { navCollapsed: true, wallPinned: true });
    expect(readWorkspaceLayout(storage)).toEqual({ navCollapsed: true, wallPinned: true });
  });

  it("two successive writes of one field each keep both values — DoD-10", () => {
    const { storage } = fakeStorage();
    writeWorkspaceLayout(storage, { wallPinned: true });
    writeWorkspaceLayout(storage, { navCollapsed: true });
    expect(readWorkspaceLayout(storage)).toEqual({ navCollapsed: true, wallPinned: true });
  });
});

// ---------------------------------------------------------------------------
describe("the write stores the two known fields only", () => {
  it("a stored asideWidth is dropped by the write — DoD-11", () => {
    const { storage, setItem } = seeded({ asideWidth: 320, navCollapsed: false, wallPinned: true });
    writeWorkspaceLayout(storage, { navCollapsed: true });
    const written = JSON.parse(setItem.mock.calls[0][1]) as Record<string, unknown>;
    expect(Object.keys(written).sort()).toEqual(["navCollapsed", "wallPinned"]);
    expect(written).toEqual({ navCollapsed: true, wallPinned: true });
  });

  it("a later read sees no unknown key either — DoD-11", () => {
    const { storage } = seeded({ asideWidth: 320, answerBoxHeight: 180, navCollapsed: false });
    writeWorkspaceLayout(storage, { navCollapsed: true });
    expect(Object.keys(readWorkspaceLayout(storage)).sort()).toEqual(["navCollapsed", "wallPinned"]);
  });
});

// ---------------------------------------------------------------------------
describe("the write is best-effort and never throws", () => {
  it("a storage whose setItem throws returns normally — DoD-12", () => {
    const storage = throwingWriteStorage({ [WORKSPACE_LAYOUT_KEY]: JSON.stringify({ navCollapsed: false }) });
    expect(() => {
      writeWorkspaceLayout(storage, { navCollapsed: true });
    }).not.toThrow();
  });

  it("a storage whose getItem throws returns normally — DoD-12", () => {
    const storage = throwingReadStorage();
    expect(() => {
      writeWorkspaceLayout(storage, { navCollapsed: true });
    }).not.toThrow();
  });

  it("a null storage is a no-op that returns normally — DoD-12", () => {
    expect(() => {
      writeWorkspaceLayout(null, { navCollapsed: true });
    }).not.toThrow();
    expect(readWorkspaceLayout(null)).toEqual(DEFAULTS);
  });

  it("an empty patch returns normally — DoD-12", () => {
    const { storage } = fakeStorage();
    expect(() => {
      writeWorkspaceLayout(storage, {});
    }).not.toThrow();
  });

  it("a storage holding unparseable JSON is written without throwing — DoD-12", () => {
    const { storage } = seededRaw("{ not json");
    expect(() => {
      writeWorkspaceLayout(storage, { navCollapsed: true });
    }).not.toThrow();
    expect(readWorkspaceLayout(storage)).toEqual({ navCollapsed: true, wallPinned: false });
  });
});
