// One level's notes (feature 015, step 006, D16): the `MemoLevelState` data class —
// observable fields only, no methods and no computed getters — and the free functions that
// load it, populate it from a chain, track each note's editor text and save on focus loss
// (D5 / D2 / D13), the two independent flag toggles (D6) and the unmount flush. Shared by
// the session screen's groups and the character page.
// Ids are decimal strings, used only as keys and compared only for equality.
import { makeAutoObservable, runInAction } from "mobx";

import type { Memo, MemoPatch, MemoScope } from "./memosApi";
import { createMemo, deleteMemo, fetchMemos, reorderMemos, updateMemo } from "./memosApi";

/** Explicit load status: gates the loading and failure renders, not "notes are empty". */
export type MemoLevelStatus = "idle" | "loading" | "ready" | "failed";

/** The unsaved new note (D13). It has no id; the component gives it a fixed key. */
export type MemoNewNote = {
  /** The new note's editor text. */
  text: string;
  /** True while its create request is in flight. */
  saving: boolean;
  /** Its failure text, or null. */
  failure: string | null;
};

export class MemoLevelState {
  scope: MemoScope;
  /** The level's owner id, or null for the user level. A string, never parsed. */
  scopeId: string | null;
  status: MemoLevelStatus = "idle";
  /** The level's notes in server order. */
  memos: Memo[] = [];
  /** Editor text of each saved note that differs from its body, by memo id (absent = the body). */
  editorTexts: Record<string, string> = {};
  /** The unsaved new note, or null. */
  newNote: MemoNewNote | null = null;
  /** Per-note failure text, by memo id (absent = no failure). */
  failures: Record<string, string> = {};
  /** Per-note "a flag write is in flight" marks, by memo id (absent = none). */
  flagWritesInFlight: Record<string, true> = {};
  /** True while a reorder of this level awaits its response (016 D7). */
  reorderInFlight: boolean = false;
  /** The level's reorder failure text, or null (016 D7; level-wide, not per note). */
  reorderFailureText: string | null = null;

  constructor(scope: MemoScope, scopeId: string | null) {
    this.scope = scope;
    this.scopeId = scopeId;
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/** The three fixed per-note failure sentences (the UI strings table). */
const SAVE_FAILED = "Could not save the note.";
const DELETE_FAILED = "Could not delete the note.";
const CHANGE_FAILED = "Could not change the note.";

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/** A copy of the record without `key` (replacing the field keeps the write observable). */
function without<T>(record: Record<string, T>, key: string): Record<string, T> {
  const next = { ...record };
  delete next[key];
  return next;
}

function findMemo(state: MemoLevelState, memoId: string): Memo | undefined {
  return state.memos.find((memo) => memo.id === memoId);
}

/** Pure: the note's editor text — its held edit, else its body. */
export function noteText(state: MemoLevelState, memoId: string): string {
  const held = state.editorTexts[memoId];
  if (held !== undefined) {
    return held;
  }
  return findMemo(state, memoId)?.body ?? "";
}

/** Pure: the note's failure text, or null. */
export function noteFailure(state: MemoLevelState, memoId: string): string | null {
  return state.failures[memoId] ?? null;
}

/** Pure: true while a flag toggle on that note awaits its response. */
export function isFlagWriteInFlight(state: MemoLevelState, memoId: string): boolean {
  return state.flagWritesInFlight[memoId] === true;
}

/** Pure: true when the text is empty or whitespace only (JavaScript `trim`, D15). */
export function isBlank(text: string): boolean {
  return text.trim() === "";
}

/**
 * Effect: sets "loading", requests the level's listing, then "ready" with the rows in the
 * order received, or "failed" keeping the rows. Writes nothing once aborted; never rejects.
 */
export async function loadMemoLevel(state: MemoLevelState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  const scope = state.scope;
  const scopeId = state.scopeId;
  runInAction(() => {
    state.status = "loading";
  });

  let memos: Memo[];
  try {
    memos = await fetchMemos(scope, scopeId, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    runInAction(() => {
      state.status = "failed";
    });
    return;
  }

  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    state.memos = memos.slice();
    state.status = "ready";
  });
}

/** Action: writes the given notes in the given order with "ready"; issues no request. */
export function populateMemoLevel(state: MemoLevelState, memos: Memo[]): void {
  runInAction(() => {
    state.memos = memos.slice();
    state.status = "ready";
  });
}

/** Action: records the note's editor text. Never touches the note's `body`. */
export function setNoteText(state: MemoLevelState, memoId: string, text: string): void {
  runInAction(() => {
    state.editorTexts = { ...state.editorTexts, [memoId]: text };
  });
}

/** Drop the note's held edit when it equals the held body (indistinguishable from none). */
function dropHeldEditIfBody(state: MemoLevelState, memoId: string): void {
  const held = state.editorTexts[memoId];
  const memo = findMemo(state, memoId);
  if (held !== undefined && memo !== undefined && held === memo.body) {
    state.editorTexts = without(state.editorTexts, memoId);
  }
}

/**
 * Effect, on focus loss: unchanged → nothing; blank → DELETE; otherwise PATCH `{ body }`.
 * Clears the note's failure first; never rejects.
 */
export async function saveNote(state: MemoLevelState, memoId: string): Promise<void> {
  const memo = findMemo(state, memoId);
  if (memo === undefined) {
    return;
  }
  const snapshot = noteText(state, memoId);
  if (snapshot === memo.body) {
    return;
  }
  runInAction(() => {
    state.failures = without(state.failures, memoId);
  });

  if (isBlank(snapshot)) {
    try {
      await deleteMemo(memoId);
    } catch {
      runInAction(() => {
        state.failures = { ...state.failures, [memoId]: DELETE_FAILED };
      });
      return;
    }
    runInAction(() => {
      state.memos = state.memos.filter((row) => row.id !== memoId);
      state.editorTexts = without(state.editorTexts, memoId);
      state.failures = without(state.failures, memoId);
    });
    return;
  }

  let row: Memo;
  try {
    row = await updateMemo(memoId, { body: snapshot });
  } catch {
    runInAction(() => {
      state.failures = { ...state.failures, [memoId]: SAVE_FAILED };
    });
    return;
  }
  runInAction(() => {
    applyMemoRow(state, row);
    // Text typed during the request differs from the new body and stays held.
    dropHeldEditIfBody(state, memoId);
  });
}

/** Action: creates an empty new note when there is none; otherwise does nothing. */
export function openNewNote(state: MemoLevelState): void {
  runInAction(() => {
    if (state.newNote !== null) {
      return;
    }
    state.newNote = { text: "", saving: false, failure: null };
  });
}

/** Action: records the new note's editor text. */
export function setNewNoteText(state: MemoLevelState, text: string): void {
  runInAction(() => {
    const current = state.newNote;
    if (current === null) {
      return;
    }
    state.newNote = { ...current, text };
  });
}

/**
 * Effect, on focus loss: no new note or saving → nothing; blank → dropped, no request;
 * otherwise POSTs a create for the level and prepends the returned row (016 D5). Never
 * rejects.
 */
export async function saveNewNote(state: MemoLevelState): Promise<void> {
  const current = state.newNote;
  if (current === null || current.saving) {
    return;
  }
  if (isBlank(current.text)) {
    runInAction(() => {
      state.newNote = null;
    });
    return;
  }
  const snapshot = current.text;
  runInAction(() => {
    state.newNote = { text: snapshot, saving: true, failure: null };
  });

  let row: Memo;
  try {
    row = await createMemo(state.scope, state.scopeId, snapshot);
  } catch {
    runInAction(() => {
      const text = state.newNote?.text ?? snapshot;
      state.newNote = { text, saving: false, failure: SAVE_FAILED };
    });
    return;
  }
  runInAction(() => {
    const typed = state.newNote?.text ?? snapshot;
    state.memos = [row, ...state.memos];
    state.newNote = null;
    if (typed !== snapshot && typed !== row.body) {
      state.editorTexts = { ...state.editorTexts, [row.id]: typed };
    }
  });
}

/**
 * The shared toggle shape: clear the note's failure, mark its flag write in flight, PATCH
 * exactly one key and apply the returned row; a failure sets the change sentence and leaves
 * the flags as held. The in-flight mark is cleared either way. Never rejects.
 */
async function runToggle(
  state: MemoLevelState,
  memoId: string,
  patchFor: (memo: Memo) => MemoPatch,
): Promise<void> {
  const memo = findMemo(state, memoId);
  if (memo === undefined) {
    return;
  }
  const patch = patchFor(memo);
  runInAction(() => {
    state.failures = without(state.failures, memoId);
    state.flagWritesInFlight = { ...state.flagWritesInFlight, [memoId]: true };
  });

  let row: Memo;
  try {
    row = await updateMemo(memoId, patch);
  } catch {
    runInAction(() => {
      state.failures = { ...state.failures, [memoId]: CHANGE_FAILED };
      state.flagWritesInFlight = without(state.flagWritesInFlight, memoId);
    });
    return;
  }
  runInAction(() => {
    applyMemoRow(state, row);
    state.flagWritesInFlight = without(state.flagWritesInFlight, memoId);
  });
}

/** Effect: PATCHes exactly `{ is_enabled: <opposite> }` and applies the row. Never rejects. */
export async function toggleEnabled(state: MemoLevelState, memoId: string): Promise<void> {
  await runToggle(state, memoId, (memo) => ({ is_enabled: !memo.is_enabled }));
}

/** Effect: PATCHes exactly `{ is_forced: <opposite> }` and applies the row. Never rejects. */
export async function toggleForced(state: MemoLevelState, memoId: string): Promise<void> {
  await runToggle(state, memoId, (memo) => ({ is_forced: !memo.is_forced }));
}

/**
 * Action: replaces the held note with that id only if the returned `updated_at` is not
 * older (fixed-width text compare). A row whose id is not held is ignored.
 */
export function applyMemoRow(state: MemoLevelState, memo: Memo): void {
  runInAction(() => {
    const index = state.memos.findIndex((row) => row.id === memo.id);
    if (index < 0) {
      return;
    }
    const held = state.memos[index];
    if (held !== undefined && memo.updated_at < held.updated_at) {
      return;
    }
    const next = state.memos.slice();
    next[index] = memo;
    state.memos = next;
  });
}

/** Pure: true while a reorder of the level awaits its response (016 D7). */
export function isReorderInFlight(state: MemoLevelState): boolean {
  return state.reorderInFlight;
}

/** Pure: the level's reorder failure text, or null (016 D7). */
export function reorderFailure(state: MemoLevelState): string | null {
  return state.reorderFailureText;
}

const REORDER_FAILED = "Could not reorder the notes.";

/** True when the two id lists hold the same ids in the same order. */
function sameOrder(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((id, index) => id === b[index]);
}

/**
 * Pure: the held rows in the given id order. Ids given but not held are ignored; held ids
 * not given keep their relative order at the front.
 */
function orderRows(rows: readonly Memo[], ids: readonly string[]): Memo[] {
  const byId = new Map(rows.map((row) => [row.id, row] as const));
  const given = new Set(ids);
  const front = rows.filter((row) => !given.has(row.id));
  const ordered: Memo[] = [];
  const placed = new Set<string>();
  for (const id of ids) {
    const row = byId.get(id);
    if (row !== undefined && !placed.has(id)) {
      ordered.push(row);
      placed.add(id);
    }
  }
  return [...front, ...ordered];
}

/**
 * Pure: the success merge. The returned order, each returned row taken only when its
 * `updated_at` is not older than the held row's; returned ids not held dropped; held ids
 * absent from the response first, in their current relative order.
 */
function mergeReturnedRows(held: readonly Memo[], returned: readonly Memo[]): Memo[] {
  const heldById = new Map(held.map((row) => [row.id, row] as const));
  const returnedIds = new Set(returned.map((row) => row.id));
  const front = held.filter((row) => !returnedIds.has(row.id));
  const merged: Memo[] = [];
  const placed = new Set<string>();
  for (const row of returned) {
    const current = heldById.get(row.id);
    if (current === undefined || placed.has(row.id)) {
      continue;
    }
    merged.push(row.updated_at < current.updated_at ? current : row);
    placed.add(row.id);
  }
  return [...front, ...merged];
}

/**
 * Pure: the revert. The current rows sorted by each id's index in the remembered order;
 * ids not remembered first, in their current relative order.
 */
function revertRows(rows: readonly Memo[], remembered: readonly string[]): Memo[] {
  const index = new Map(remembered.map((id, position) => [id, position] as const));
  const front = rows.filter((row) => !index.has(row.id));
  const known = rows
    .filter((row) => index.has(row.id))
    .sort((a, b) => (index.get(a.id) ?? 0) - (index.get(b.id) ?? 0));
  return [...front, ...known];
}

/**
 * Effect (016 D7): optimistically rewrites `memos` into the given saved-note id order,
 * sends the whole level's order, merges the returned rows on success or reverts to the
 * pre-drop relative order with "Could not reorder the notes." on failure. Does nothing
 * while a reorder is in flight or when the order is unchanged. Passes no signal; never
 * rejects.
 */
export async function reorderMemoLevel(state: MemoLevelState, memoIds: string[]): Promise<void> {
  if (state.reorderInFlight) {
    return;
  }
  const remembered = state.memos.map((memo) => memo.id);
  if (sameOrder(remembered, memoIds)) {
    return;
  }
  const scope = state.scope;
  const scopeId = state.scopeId;
  const sentIds = memoIds.slice();
  runInAction(() => {
    state.memos = orderRows(state.memos, sentIds);
    state.reorderInFlight = true;
    state.reorderFailureText = null;
  });

  let returned: Memo[];
  try {
    returned = await reorderMemos(scope, scopeId, sentIds);
  } catch {
    runInAction(() => {
      state.memos = revertRows(state.memos, remembered);
      state.reorderFailureText = REORDER_FAILED;
      state.reorderInFlight = false;
    });
    return;
  }
  runInAction(() => {
    state.memos = mergeReturnedRows(state.memos, returned);
    state.reorderInFlight = false;
  });
}

/**
 * Effect, on unmount: saves every changed note and a non-blank, not-saving new note, all
 * at once. Resolves when they settle; never rejects.
 */
export async function flushMemoLevel(state: MemoLevelState): Promise<void> {
  const pending: Promise<void>[] = [];
  for (const memo of state.memos) {
    const held = state.editorTexts[memo.id];
    if (held !== undefined && held !== memo.body) {
      pending.push(saveNote(state, memo.id));
    }
  }
  const newNote = state.newNote;
  if (newNote !== null && !newNote.saving && !isBlank(newNote.text)) {
    pending.push(saveNewNote(state));
  }
  await Promise.allSettled(pending);
}
