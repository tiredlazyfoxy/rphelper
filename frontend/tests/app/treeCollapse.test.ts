// Feature 011, step 005 — the collapsed-characters record (DoD-5..DoD-9, and DoD-10 for
// src/app/treeCollapse.ts; sessionLabel.ts's half of DoD-10 lives in tests/app/sessionLabel.test.ts).
//
// The storage is a parameter, never a global (D7, 008's posture): every clause below passes a
// small in-memory fake with spy-able getItem/setItem, or `null`. jsdom's own localStorage is
// deliberately not used — the module touches no DOM. The fakes are built here rather than
// imported from 008's tests, so this file depends on nothing but the frozen interface.
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it, vi } from "vitest";
import {
  readCollapsedCharacters,
  toggleCollapsedCharacter,
  TREE_COLLAPSED_KEY,
  writeCollapsedCharacters,
} from "../../src/app/treeCollapse";

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const TREE_COLLAPSE_SOURCE = path.join(FRONTEND_ROOT, "src", "app", "treeCollapse.ts");

/** 008's key, which this module must never read or write (D7). */
const WORKSPACE_LAYOUT_KEY = "rphelper.workspace-layout";
const KEY = "rphelper.tree-collapsed";

/** The `LayoutStorage` shape, declared locally so the fakes bind to it without an import. */
type FakeLayoutStorage = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
};
type GetItem = (key: string) => string | null;
type SetItem = (key: string, value: string) => void;

// ---------------------------------------------------------------- helpers

/** An in-memory storage whose two members are spies. */
function fakeStorage(seed?: Record<string, string>) {
  const entries = new Map<string, string>(Object.entries(seed ?? {}));
  const getItem = vi.fn<GetItem>((key) => entries.get(key) ?? null);
  const setItem = vi.fn<SetItem>((key, value) => {
    entries.set(key, value);
  });
  const storage: FakeLayoutStorage = { getItem, setItem };
  return { storage, getItem, setItem, entries };
}

/** A storage holding `raw` verbatim under the collapsed-characters key. */
function seededRaw(raw: string) {
  return fakeStorage({ [KEY]: raw });
}

/** A storage holding `JSON.stringify(payload)` under the collapsed-characters key. */
function seeded(payload: unknown) {
  return seededRaw(JSON.stringify(payload));
}

/** A storage whose `getItem` throws. */
function throwingReadStorage(): FakeLayoutStorage {
  return {
    getItem(): string | null {
      throw new Error("getItem is unavailable zq-read");
    },
    setItem(): void {},
  };
}

/** A readable storage whose `setItem` throws (a full or denied quota). */
function throwingWriteStorage(seed?: Record<string, string>): FakeLayoutStorage {
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

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

// ---------------------------------------------------------------------------
describe("the key, and the read is total", () => {
  it("TREE_COLLAPSED_KEY is rphelper.tree-collapsed — DoD-5", () => {
    expect(TREE_COLLAPSED_KEY).toBe("rphelper.tree-collapsed");
  });

  it("a null storage reads as the empty set — DoD-5", () => {
    expect(readCollapsedCharacters(null)).toEqual([]);
  });

  it("a null storage does not throw — DoD-5", () => {
    expect(() => readCollapsedCharacters(null)).not.toThrow();
  });

  it("a storage with no value under the key reads as the empty set — DoD-5", () => {
    const { storage } = fakeStorage();
    expect(readCollapsedCharacters(storage)).toEqual([]);
  });

  it("a storage holding other keys only reads as the empty set — DoD-5", () => {
    const { storage } = fakeStorage({ [WORKSPACE_LAYOUT_KEY]: '{"navCollapsed":true}' });
    expect(readCollapsedCharacters(storage)).toEqual([]);
  });

  it("a storage whose getItem throws reads as the empty set and does not throw — DoD-5", () => {
    const storage = throwingReadStorage();
    expect(() => readCollapsedCharacters(storage)).not.toThrow();
    expect(readCollapsedCharacters(storage)).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("the read is total: a stored value that is not a JSON array", () => {
  const NOT_AN_ARRAY: Array<[string, string]> = [
    ["unparseable JSON", '["7250000000000000001", '],
    ["an empty string", ""],
    ["an object", '{"7250000000000000001":true}'],
    ["a string", '"7250000000000000001"'],
    ["a number", "42"],
    ["null", "null"],
    ["a boolean", "true"],
  ];

  it.each(NOT_AN_ARRAY)("a stored %s reads as the empty set — DoD-6", (_name, raw) => {
    const { storage } = seededRaw(raw);
    expect(readCollapsedCharacters(storage)).toEqual([]);
  });

  it.each(NOT_AN_ARRAY)("a stored %s never throws — DoD-6", (_name, raw) => {
    const { storage } = seededRaw(raw);
    expect(() => readCollapsedCharacters(storage)).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
describe("the read keeps strings, drops duplicates, and preserves first-seen order", () => {
  it("non-strings and duplicates are dropped, order preserved — DoD-6", () => {
    const { storage } = seeded([
      "7250000000000000001",
      5,
      "7250000000000000002",
      "7250000000000000001",
      null,
    ]);
    expect(readCollapsedCharacters(storage)).toEqual([
      "7250000000000000001",
      "7250000000000000002",
    ]);
  });

  it("a non-string entry is dropped, not converted to a string — DoD-6", () => {
    const { storage } = seeded([5, "7250000000000000002"]);
    expect(readCollapsedCharacters(storage)).toEqual(["7250000000000000002"]);
  });

  it("an empty stored array reads as the empty set — DoD-6", () => {
    const { storage } = seeded([]);
    expect(readCollapsedCharacters(storage)).toEqual([]);
  });

  it("an array of only non-strings reads as the empty set — DoD-6", () => {
    const { storage } = seeded([1, null, true, {}, []]);
    expect(readCollapsedCharacters(storage)).toEqual([]);
  });

  it("the read asks for rphelper.tree-collapsed and no other key — DoD-6", () => {
    const { storage, getItem } = seeded(["7250000000000000001"]);
    readCollapsedCharacters(storage);
    const keys = getItem.mock.calls.map(([key]) => key);
    expect(keys.length).toBeGreaterThan(0);
    expect([...new Set(keys)]).toEqual([KEY]);
  });

  it("an absent value is still only rphelper.tree-collapsed asked for — DoD-6", () => {
    const { storage, getItem } = fakeStorage();
    readCollapsedCharacters(storage);
    const keys = getItem.mock.calls.map(([key]) => key);
    expect(keys.length).toBeGreaterThan(0);
    expect([...new Set(keys)]).toEqual([KEY]);
  });
});

// ---------------------------------------------------------------------------
describe("the write stores the whole set under its own key", () => {
  it('["a", "b"] is stored as the JSON array ["a","b"] under rphelper.tree-collapsed — DoD-7', () => {
    const { storage, setItem, entries } = fakeStorage();
    writeCollapsedCharacters(storage, ["a", "b"]);
    expect(setItem.mock.calls).toEqual([[KEY, expect.any(String)]]);
    expect(JSON.parse(entries.get(KEY) ?? "null") as unknown).toEqual(["a", "b"]);
  });

  it("a following read returns [\"a\", \"b\"] — DoD-7", () => {
    const { storage } = fakeStorage();
    writeCollapsedCharacters(storage, ["a", "b"]);
    expect(readCollapsedCharacters(storage)).toEqual(["a", "b"]);
  });

  it("setItem is never called with rphelper.workspace-layout — DoD-7", () => {
    const { storage, setItem } = fakeStorage({ [WORKSPACE_LAYOUT_KEY]: '{"navCollapsed":true}' });
    writeCollapsedCharacters(storage, ["a", "b"]);
    const keys = setItem.mock.calls.map(([key]) => key);
    expect(keys).not.toContain(WORKSPACE_LAYOUT_KEY);
    expect([...new Set(keys)]).toEqual([KEY]);
  });

  it("the stored workspace-layout value is left untouched by the write — DoD-7", () => {
    const { storage, entries } = fakeStorage({ [WORKSPACE_LAYOUT_KEY]: '{"navCollapsed":true}' });
    writeCollapsedCharacters(storage, ["a", "b"]);
    expect(entries.get(WORKSPACE_LAYOUT_KEY)).toBe('{"navCollapsed":true}');
  });

  it("a write replaces the whole previously stored set — DoD-7", () => {
    const { storage } = seeded(["x", "y", "z"]);
    writeCollapsedCharacters(storage, ["a", "b"]);
    expect(readCollapsedCharacters(storage)).toEqual(["a", "b"]);
  });

  it("an empty set round-trips as the empty set — DoD-7", () => {
    const { storage } = seeded(["x"]);
    writeCollapsedCharacters(storage, []);
    expect(readCollapsedCharacters(storage)).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("the write is best-effort and never throws", () => {
  it("a storage whose setItem throws returns normally — DoD-8", () => {
    const storage = throwingWriteStorage({ [KEY]: JSON.stringify(["x"]) });
    expect(() => {
      writeCollapsedCharacters(storage, ["a", "b"]);
    }).not.toThrow();
  });

  it("a null storage is a no-op that returns normally — DoD-8", () => {
    expect(() => {
      writeCollapsedCharacters(null, ["a", "b"]);
    }).not.toThrow();
    expect(readCollapsedCharacters(null)).toEqual([]);
  });

  it("a storage whose getItem throws is written without throwing — DoD-8", () => {
    const storage = throwingReadStorage();
    expect(() => {
      writeCollapsedCharacters(storage, ["a", "b"]);
    }).not.toThrow();
  });

  it("an empty set written to a null storage returns normally — DoD-8", () => {
    expect(() => {
      writeCollapsedCharacters(null, []);
    }).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
describe("the toggle is pure", () => {
  it('toggleCollapsedCharacter(["a"], "b") is ["a", "b"] — DoD-9', () => {
    expect(toggleCollapsedCharacter(["a"], "b")).toEqual(["a", "b"]);
  });

  it('toggleCollapsedCharacter(["a", "b"], "a") is ["b"] — DoD-9', () => {
    expect(toggleCollapsedCharacter(["a", "b"], "a")).toEqual(["b"]);
  });

  it("the input array is unchanged after an add — DoD-9", () => {
    const input = ["a"];
    const result = toggleCollapsedCharacter(input, "b");
    expect(input).toEqual(["a"]);
    expect(result).not.toBe(input);
  });

  it("the input array is unchanged after a removal — DoD-9", () => {
    const input = ["a", "b"];
    const result = toggleCollapsedCharacter(input, "a");
    expect(input).toEqual(["a", "b"]);
    expect(result).not.toBe(input);
  });

  it("toggling the same id twice returns to the original set — DoD-9", () => {
    const input = ["a"];
    const added = toggleCollapsedCharacter(input, "b");
    expect(toggleCollapsedCharacter(added, "b")).toEqual(["a"]);
    expect(input).toEqual(["a"]);
  });

  it("an id added to the empty set lands as the only entry — DoD-9", () => {
    const input: string[] = [];
    expect(toggleCollapsedCharacter(input, "a")).toEqual(["a"]);
    expect(input).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("src/app/treeCollapse.ts is DOM-, React- and MobX-free", () => {
  const DOM_RULES: Array<[string, RegExp]> = [
    ["a window reference", /\bwindow\b/],
    ["a document reference", /\bdocument\b/],
    ["a localStorage global", /\blocalStorage\b/],
    ["a sessionStorage global", /\bsessionStorage\b/],
    ["a React import", /["']react(?:-dom)?(?:\/[^"']*)?["']/],
    ["a MobX import", /["']mobx(?:-react-lite)?(?:\/[^"']*)?["']/],
  ];

  it("the scan reads src/app/treeCollapse.ts from disk — DoD-10", () => {
    expect(readFileSync(TREE_COLLAPSE_SOURCE, "utf8").length).toBeGreaterThan(0);
  });

  it.each(DOM_RULES)("src/app/treeCollapse.ts references no %s — DoD-10", (rule, pattern) => {
    const source = stripComments(readFileSync(TREE_COLLAPSE_SOURCE, "utf8"));
    const matches = Array.from(source.matchAll(new RegExp(pattern.source, "g")), (m) => m[0]);
    expect(matches, `${rule}: ${matches[0] ?? "none"}`).toEqual([]);
  });
});
