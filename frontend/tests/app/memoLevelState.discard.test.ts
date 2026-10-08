// Fast feature 012 — notes-autosave-toolbar-flags. This file held 033 step 002's
// `discardNewNote` tests; fast 012 removes that function (its only caller was the draft's
// Cancel button), so those tests are gone. The plan lists this file for deletion; until it is
// removed it pins the replacement contract at the state level instead:
// - `discardNewNote` is no longer exported (DoD-15's source half; DoD-15 itself is
//   [manual/live]).
// - The draft closes only through `saveNewNote`: a trimmed-blank draft is dropped with no
//   request (DoD-7).
//
// `fetch` is stubbed per test; every request is recorded, so "no request" is `calls` empty.
import { afterEach, describe, expect, it, vi } from "vitest";
import * as levelState from "../../src/app/memoLevelState";
import type { Memo } from "../../src/app/memosApi";
import { MemoLevelState, openNewNote, populateMemoLevel, saveNewNote, setNewNoteText } from "../../src/app/memoLevelState";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const CHARACTER_ID = "9007199254740993";
const MEMO_A = "7250000000000000201";
const STAMP = "2026-10-02T09:26:53.000000+00:00";

function memo(id: string, body: string): Memo {
  return {
    id,
    scope: "character",
    scope_id: CHARACTER_ID,
    body,
    is_enabled: true,
    is_forced: false,
    sort_key: 0,
    created_at: STAMP,
    updated_at: STAMP,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function stubBackend() {
  const calls: unknown[] = [];
  const mock = vi.fn<FetchFn>(async (input) => {
    calls.push(input);
    return new Response(JSON.stringify({ error: { code: "internal_error", message: "x", detail: {} } }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", mock);
  return { calls };
}

describe("the draft has no discard: blank drafts close through saveNewNote (fast 012)", () => {
  it("memoLevelState no longer exports discardNewNote — DoD-7 (DoD-15 source half)", () => {
    expect(Object.keys(levelState)).not.toContain("discardNewNote");
  });

  it.each<[string, string | null]>([
    ["untouched (empty)", null],
    ["whitespace only", "  \n\t "],
  ])("saving a %s draft drops it and sends no request — DoD-7", async (_label, text) => {
    const { calls } = stubBackend();
    const saved = memo(MEMO_A, "Mira limps on her left leg.");
    const state = new MemoLevelState("character", CHARACTER_ID);
    populateMemoLevel(state, [saved]);
    openNewNote(state);
    if (text !== null) setNewNoteText(state, text);
    expect(state.newNote).not.toBeNull();

    await saveNewNote(state);

    expect(state.newNote).toBeNull();
    expect(calls).toEqual([]);
    expect(state.memos).toEqual([saved]);
  });
});
