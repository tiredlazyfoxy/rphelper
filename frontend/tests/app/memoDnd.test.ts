// Feature 018, step 005 — the shared drag configuration (DoD-1, DoD-7).
//
// Expected behaviour comes from 018's step file 005.notes-grid.md (Interface intent for
// `app/memoDnd.ts`, DoD-1, DoD-7), 005.context.md ("Test-file notes": this file tests the pure
// builder only; the hook is covered through the two components and the source read) and 018
// context.md D8 (sensors and position-only announcements factored out of MemoChainSection,
// not copied), which carries 016 D8 (a note is named by its position in its group and the
// group's title, never by its id).
//
// Recognition conventions (for the verifier):
// - The builder is called directly with `MemoDndGroup`s; its dnd-kit announcement callbacks
//   are invoked with minimal `active` / `over` objects (only `id` is meaningful to the spec).
// - An announcement callback may return `undefined` (dnd-kit allows it); "contains no id" is
//   checked on `result ?? ""`. Only the unknown-id drag start is required to be a non-empty
//   message (Interface intent: "a generic message").
// - The source read (DoD-7) strips comments before matching, as ComposerCore.test.tsx does.
import type { Active, Announcements, Over } from "@dnd-kit/core";
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { memoAnnouncements, type MemoDndGroup } from "../../src/app/memoDnd";

// ---------------------------------------------------------------- fixtures (DoD-1)
const YOUR_NOTES = "Your notes";
const CHARACTER_NOTES = "Character notes";

const U1 = "7250000000000000301";
const C1 = "7250000000000000311";
const C2 = "7250000000000000312";
const C3 = "7250000000000000313";
const UNKNOWN = "7250000000000000399";

const ALL_IDS = [U1, C1, C2, C3, UNKNOWN];

const GROUPS: MemoDndGroup[] = [
  { title: YOUR_NOTES, ids: [U1] },
  { title: CHARACTER_NOTES, ids: [C1, C2, C3] },
];

function activeOf(id: string): Active {
  return {
    id,
    data: { current: undefined },
    rect: { current: { initial: null, translated: null } },
  } as unknown as Active;
}

function overOf(id: string): Over {
  return {
    id,
    rect: { width: 0, height: 0, top: 0, left: 0, right: 0, bottom: 0 },
    disabled: false,
    data: { current: undefined },
  } as unknown as Over;
}

/** Every message the announcements produce for one active id and one over id (or none). */
function everyMessage(announcements: Announcements, activeId: string, overId: string | null): string[] {
  const args = { active: activeOf(activeId), over: overId === null ? null : overOf(overId) };
  const produced: Array<string | undefined> = [
    announcements.onDragStart({ active: args.active }),
    announcements.onDragOver(args),
    announcements.onDragEnd(args),
    announcements.onDragCancel(args),
  ];
  if (announcements.onDragMove !== undefined) produced.push(announcements.onDragMove(args));
  return produced.map((message) => message ?? "");
}

function expectNoId(message: string): void {
  for (const id of ALL_IDS) {
    expect(message).not.toContain(id);
  }
}

// ===========================================================================
describe("memoAnnouncements — position and group, never the id (016 D8, US-102)", () => {
  it("the drag-start announcement for c2 names its position 2 and the group Character notes, and holds none of the ids — DoD-1", () => {
    const announcements = memoAnnouncements(GROUPS);

    const message = announcements.onDragStart({ active: activeOf(C2) });

    expect(typeof message).toBe("string");
    const text = message ?? "";
    expect(text).toMatch(/\b2\b/);
    expect(text).toContain(CHARACTER_NOTES);
    expectNoId(text);
  });

  it("the drag-start announcement for u1 names its position 1 and the group Your notes, and holds none of the ids — DoD-1", () => {
    const announcements = memoAnnouncements(GROUPS);

    const text = announcements.onDragStart({ active: activeOf(U1) }) ?? "";

    expect(text).toMatch(/\b1\b/);
    expect(text).toContain(YOUR_NOTES);
    expectNoId(text);
  });

  it("every start, over, end and cancel announcement, for every known note over every note or over nothing, holds no id string — DoD-1", () => {
    const announcements = memoAnnouncements(GROUPS);
    const known = [U1, C1, C2, C3];

    for (const activeId of known) {
      for (const overId of [...known, null]) {
        for (const message of everyMessage(announcements, activeId, overId)) {
          expectNoId(message);
        }
      }
    }
  });

  it("an unknown active id yields a non-empty generic drag-start message that holds no id — DoD-1", () => {
    const announcements = memoAnnouncements(GROUPS);

    const message = announcements.onDragStart({ active: activeOf(UNKNOWN) });

    expect(typeof message).toBe("string");
    expect((message ?? "").trim()).not.toBe("");
    expectNoId(message ?? "");
  });

  it("with an unknown id as the active note or as the note it is over, no start, over, end or cancel announcement holds an id — DoD-1", () => {
    const announcements = memoAnnouncements(GROUPS);

    const cases: Array<[string, string | null]> = [
      [UNKNOWN, null],
      [UNKNOWN, C1],
      [UNKNOWN, UNKNOWN],
      [C2, UNKNOWN],
      [U1, UNKNOWN],
    ];
    for (const [activeId, overId] of cases) {
      for (const message of everyMessage(announcements, activeId, overId)) {
        expectNoId(message);
      }
    }
  });
});

// ---------------------------------------------------------------- DoD-7
const FRONTEND_ROOT = path.resolve(__dirname, "..", "..");
const APP_SRC = path.join(FRONTEND_ROOT, "src", "app");

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

function readSource(name: string): string {
  return stripComments(readFileSync(path.join(APP_SRC, name), "utf8"));
}

/** The names a source imports, by name, from one module specifier (aliases resolved to the imported name). */
function namedImportsFrom(source: string, specifier: string): string[] {
  const names: string[] = [];
  for (const match of source.matchAll(/\bimport\s+(?:type\s+)?\{([^}]*)\}\s*from\s*["']([^"']+)["']/g)) {
    if (match[2] !== specifier || match[1] === undefined) continue;
    for (const part of match[1].split(",")) {
      const name = part.trim().replace(/^type\s+/, "").split(/\s+as\s+/)[0]?.trim() ?? "";
      if (name !== "") names.push(name);
    }
  }
  return names;
}

describe("the sensor setup lives in one place (D8 — factored, not copied)", () => {
  const CONSUMERS = ["MemoChainSection.tsx", "CharacterNotesSection.tsx"];

  it.each(CONSUMERS)("%s imports the sensors hook and the announcements builder from ./memoDnd — DoD-7", (file) => {
    const imported = namedImportsFrom(readSource(file), "./memoDnd");

    expect(imported).toContain("useMemoDndSensors");
    expect(imported).toContain("memoAnnouncements");
  });

  it.each(CONSUMERS)("%s constructs no PointerSensor and no KeyboardSensor of its own — DoD-7", (file) => {
    const source = readSource(file);

    expect(source).not.toMatch(/\bPointerSensor\b/);
    expect(source).not.toMatch(/\bKeyboardSensor\b/);
  });

  it("memoDnd.ts is where the PointerSensor and the KeyboardSensor with sortableKeyboardCoordinates are set up — DoD-7", () => {
    const source = readSource("memoDnd.ts");

    expect(source).toMatch(/\bPointerSensor\b/);
    expect(source).toMatch(/\bKeyboardSensor\b/);
    expect(source).toMatch(/\bsortableKeyboardCoordinates\b/);
  });
});
