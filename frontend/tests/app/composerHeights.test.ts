// Bug fix against fast/011 (composer-send-icon-and-shortcut) — bug-fix: architecture 2026-10-08
// composer rule. Reproduces: "the character sessions page start text box must be resizable
// (vertical) but it's not", with the user's revised design — the dragged composer height is
// persisted per place in localStorage under `rphelper.composer-heights`.
//
// Defends fast/011 DoD-16 (drag-resize must hold), now with the persisted height of
// workspace-shell.md "Layout persistence" → "`ComposerHeights` rules":
//   - read is total and never throws; each field falls back independently to null on an absent
//     key, unparseable JSON, a throwing getItem, a wrong type, or a non-finite / non-positive
//     number; no upper clamp;
//   - write is best-effort and swallowed, merges its one field over a fresh total read (writing
//     `chat` cannot clobber `start`), and a non-size (non-finite or <= 0) writes nothing;
//   - the storage is a parameter. An in-memory fake is used throughout, never jsdom localStorage.
import { describe, expect, it, vi } from "vitest";
import {
  COMPOSER_HEIGHTS_KEY,
  readComposerHeights,
  writeComposerHeight,
  type ComposerHeights,
} from "../../src/app/composerHeights";
import type { LayoutStorage } from "../../src/app/workspaceLayout";

type GetItem = (key: string) => string | null;
type SetItem = (key: string, value: string) => void;

// ---------------------------------------------------------------- helpers
function fakeStorage(seed?: Record<string, string>) {
  const entries = new Map<string, string>(Object.entries(seed ?? {}));
  const getItem = vi.fn<GetItem>((key) => entries.get(key) ?? null);
  const setItem = vi.fn<SetItem>((key, value) => {
    entries.set(key, value);
  });
  const storage: LayoutStorage = { getItem, setItem };
  return { storage, getItem, setItem, entries };
}

function seededRaw(raw: string) {
  return fakeStorage({ [COMPOSER_HEIGHTS_KEY]: raw });
}

function seeded(payload: unknown) {
  return seededRaw(JSON.stringify(payload));
}

function throwingReadStorage() {
  const setItem = vi.fn<SetItem>();
  const storage: LayoutStorage = {
    getItem(): string | null {
      throw new Error("getItem is unavailable zq-read");
    },
    setItem,
  };
  return { storage, setItem };
}

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

const NONE: ComposerHeights = { chat: null, start: null };

// ---------------------------------------------------------------- key
describe("composerHeights — the key (bug-fix: architecture 2026-10-08 composer rule)", () => {
  it("the key is rphelper.composer-heights — fast/011 DoD-16", () => {
    expect(COMPOSER_HEIGHTS_KEY).toBe("rphelper.composer-heights");
  });
});

// ---------------------------------------------------------------- read
describe("readComposerHeights — total, never throws, per-field fallback (bug-fix: architecture 2026-10-08)", () => {
  it("null storage reads both fields as null — fast/011 DoD-16", () => {
    expect(readComposerHeights(null)).toEqual(NONE);
  });

  it("an absent key reads both fields as null — fast/011 DoD-16", () => {
    const { storage, getItem } = fakeStorage();
    expect(readComposerHeights(storage)).toEqual(NONE);
    expect(getItem).toHaveBeenCalledWith(COMPOSER_HEIGHTS_KEY);
  });

  it("a throwing getItem reads both fields as null and does not throw — fast/011 DoD-16", () => {
    const { storage } = throwingReadStorage();
    expect(() => readComposerHeights(storage)).not.toThrow();
    expect(readComposerHeights(storage)).toEqual(NONE);
  });

  it.each(["{not json", "", "undefined", "null", "[]", "[260, 400]", "260", '"260"', "true"])(
    "a stored %j that is unparseable or not an object reads both fields as null — fast/011 DoD-16",
    (raw) => {
      const { storage } = seededRaw(raw);
      expect(() => readComposerHeights(storage)).not.toThrow();
      expect(readComposerHeights(storage)).toEqual(NONE);
    },
  );

  it("a valid record reads back both heights — fast/011 DoD-16", () => {
    const { storage } = seeded({ chat: 260, start: 400 });
    expect(readComposerHeights(storage)).toEqual({ chat: 260, start: 400 });
  });

  it("a record with only one field reads the other as null — fast/011 DoD-16", () => {
    expect(readComposerHeights(seeded({ start: 400 }).storage)).toEqual({ chat: null, start: 400 });
    expect(readComposerHeights(seeded({ chat: 260 }).storage)).toEqual({ chat: 260, start: null });
  });

  it("unknown keys in the record are ignored — fast/011 DoD-16", () => {
    const { storage } = seeded({ chat: 260, start: 400, other: 7 });
    expect(readComposerHeights(storage)).toEqual({ chat: 260, start: 400 });
  });

  it.each<[string, unknown]>([
    ["a string", "260"],
    ["a boolean", true],
    ["null", null],
    ["an object", { px: 260 }],
    ["an array", [260]],
    ["zero", 0],
    ["a negative number", -40],
  ])("a bad chat (%s) costs only chat; start survives — fast/011 DoD-16", (_label, bad) => {
    const { storage } = seeded({ chat: bad, start: 400 });
    expect(readComposerHeights(storage)).toEqual({ chat: null, start: 400 });
  });

  it.each<[string, unknown]>([
    ["a string", "400"],
    ["a boolean", false],
    ["zero", 0],
    ["a negative number", -1],
  ])("a bad start (%s) costs only start; chat survives — fast/011 DoD-16", (_label, bad) => {
    const { storage } = seeded({ chat: 260, start: bad });
    expect(readComposerHeights(storage)).toEqual({ chat: 260, start: null });
  });

  it("a non-finite number (JSON 1e999 parses to Infinity) falls back to null for that field only — fast/011 DoD-16", () => {
    expect(readComposerHeights(seededRaw('{"chat":1e999,"start":400}').storage)).toEqual({ chat: null, start: 400 });
    expect(readComposerHeights(seededRaw('{"chat":260,"start":-1e999}').storage)).toEqual({ chat: 260, start: null });
  });

  it("there is no upper clamp: a very large positive height reads back unchanged — fast/011 DoD-16", () => {
    const { storage } = seeded({ chat: 100000, start: 54321 });
    expect(readComposerHeights(storage)).toEqual({ chat: 100000, start: 54321 });
  });
});

// ---------------------------------------------------------------- write
describe("writeComposerHeight — best-effort, merges one field over a fresh read (bug-fix: architecture 2026-10-08)", () => {
  it("null storage is a no-op and does not throw — fast/011 DoD-16", () => {
    expect(() => writeComposerHeight(null, "chat", 300)).not.toThrow();
  });

  it("writing chat into an empty storage stores it under the key as JSON; start stays null — fast/011 DoD-16", () => {
    const { storage, setItem, entries } = fakeStorage();

    writeComposerHeight(storage, "chat", 300);

    expect(setItem).toHaveBeenCalledTimes(1);
    expect(setItem.mock.calls[0]?.[0]).toBe(COMPOSER_HEIGHTS_KEY);
    const raw = entries.get(COMPOSER_HEIGHTS_KEY);
    expect(raw).toBeDefined();
    expect((JSON.parse(raw ?? "null") as Record<string, unknown>).chat).toBe(300);
    expect(readComposerHeights(storage)).toEqual({ chat: 300, start: null });
  });

  it("writing chat keeps a stored start — fast/011 DoD-16", () => {
    const { storage } = seeded({ chat: 260, start: 400 });

    writeComposerHeight(storage, "chat", 300);

    expect(readComposerHeights(storage)).toEqual({ chat: 300, start: 400 });
  });

  it("writing start keeps a stored chat — fast/011 DoD-16", () => {
    const { storage } = seeded({ chat: 260, start: 400 });

    writeComposerHeight(storage, "start", 520);

    expect(readComposerHeights(storage)).toEqual({ chat: 260, start: 520 });
  });

  it("the merge is over a fresh read: a value stored by someone else since is kept — fast/011 DoD-16", () => {
    const { storage, entries } = fakeStorage();
    writeComposerHeight(storage, "chat", 300);
    // Another tab writes start in between.
    entries.set(COMPOSER_HEIGHTS_KEY, JSON.stringify({ chat: 300, start: 640 }));

    writeComposerHeight(storage, "chat", 310);

    expect(readComposerHeights(storage)).toEqual({ chat: 310, start: 640 });
  });

  it("writing over a corrupt record replaces it with a readable one — fast/011 DoD-16", () => {
    const { storage } = seededRaw("{not json");

    writeComposerHeight(storage, "start", 400);

    expect(readComposerHeights(storage)).toEqual({ chat: null, start: 400 });
  });

  it("a throwing setItem is swallowed — fast/011 DoD-16", () => {
    const storage = throwingWriteStorage({ [COMPOSER_HEIGHTS_KEY]: JSON.stringify({ chat: 260, start: 400 }) });
    expect(() => writeComposerHeight(storage, "chat", 300)).not.toThrow();
  });

  it("a throwing getItem does not stop the write and does not throw — fast/011 DoD-16", () => {
    const { storage, setItem } = throwingReadStorage();

    expect(() => writeComposerHeight(storage, "chat", 300)).not.toThrow();

    expect(setItem).toHaveBeenCalledTimes(1);
    expect(setItem.mock.calls[0]?.[0]).toBe(COMPOSER_HEIGHTS_KEY);
    expect((JSON.parse(setItem.mock.calls[0]?.[1] ?? "null") as Record<string, unknown>).chat).toBe(300);
  });

  it.each([0, -10, Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY])(
    "a height of %s is not a size and writes nothing — fast/011 DoD-16",
    (height) => {
      const { storage, setItem } = seeded({ chat: 260, start: 400 });

      writeComposerHeight(storage, "chat", height);

      expect(setItem).not.toHaveBeenCalled();
      expect(readComposerHeights(storage)).toEqual({ chat: 260, start: 400 });
    },
  );

  it("there is no upper clamp on write: a very large height reads back unchanged — fast/011 DoD-16", () => {
    const { storage } = fakeStorage();

    writeComposerHeight(storage, "start", 100000);

    expect(readComposerHeights(storage)).toEqual({ chat: null, start: 100000 });
  });
});
