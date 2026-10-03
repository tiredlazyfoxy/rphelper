// The session stream's state (feature 013, step 002): one data class holding the record,
// the zone, the load status, the composer draft, the kind override and the in-flight flag —
// observable fields only, no methods and no computed getters. Every derivation and every
// effect is a free function below, each taking the state first. `003` adds the mutations.
import { makeAutoObservable, runInAction } from "mobx";

import { notifyFailure } from "../shared/notifyFailure";

import type { SettlePreview } from "./parens";
import { previewSettle } from "./parens";
import type { Message } from "./streamApi";
import {
  appendZoneMessage,
  editMessage,
  fetchEntries,
  fetchZone,
  filePartnerEntry,
  reopenLastEntry,
  settleZone,
} from "./streamApi";

/** The kind switch's two positions. */
export type StreamKind = "partner" | "turn";

/** Explicit load status for the stream. */
export type StreamStatus = "idle" | "loading" | "ready" | "failed";

export class StreamState {
  /** The session whose stream this is. Never parsed. */
  sessionId: string;
  /** The record: settled entries, in served order. */
  entries: Message[] = [];
  /** The zone: unsettled rows, in served order. */
  zone: Message[] = [];
  status: StreamStatus = "idle";
  /** The composer text, as typed. */
  draft = "";
  /** The user's switch choice, or null to follow the default (D8). */
  kindOverride: StreamKind | null = null;
  /** Whether a send / file / settle / re-open is in flight (written by `003`). */
  busy = false;

  constructor(sessionId: string) {
    this.sessionId = sessionId;
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/** True when the two lists hold the same id strings in the same order. */
function sameIdSequence(a: readonly Message[], b: readonly Message[]): boolean {
  if (a.length !== b.length) {
    return false;
  }
  return a.every((message, index) => message.id === b[index]?.id);
}

/** Pure: true when the text is empty or whitespace only (D16). */
export function isBlank(text: string): boolean {
  return text.trim().length === 0;
}

/** Pure: the switch default after the last partner-or-turn entry; `"turn"` when none (D8). */
export function defaultKind(entries: readonly Message[]): StreamKind {
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const kind = entries[index]?.kind;
    if (kind === "partner") {
      return "turn";
    }
    if (kind === "turn") {
      return "partner";
    }
  }
  return "turn";
}

/** Pure: the override when set, else the default of the state's entries. */
export function effectiveKind(state: StreamState): StreamKind {
  return state.kindOverride ?? defaultKind(state.entries);
}

/** Pure: true when the draft is not blank and nothing is in flight. */
export function canSend(state: StreamState): boolean {
  return !isBlank(state.draft) && !state.busy;
}

/** Pure: true on *my turn*, not busy, with a zone row or a non-blank draft (US-135). */
export function canSettle(state: StreamState): boolean {
  if (effectiveKind(state) !== "turn" || state.busy) {
    return false;
  }
  return state.zone.length > 0 || !isBlank(state.draft);
}

/** Pure: true when the zone is empty and the draft is blank (D3). */
export function showsDiscard(state: StreamState): boolean {
  return state.zone.length === 0 && isBlank(state.draft);
}

/** Pure: true when the zone is empty and the last record entry exists and is not a partner (D4). */
export function showsReopen(state: StreamState): boolean {
  if (state.zone.length > 0) {
    return false;
  }
  const last = state.entries[state.entries.length - 1];
  return last !== undefined && last.kind !== "partner";
}

/** Pure: the non-blank draft, else the last zone row's text, else null (D1, D2). */
export function settleTargetText(state: StreamState): string | null {
  if (!isBlank(state.draft)) {
    return state.draft;
  }
  const last = state.zone[state.zone.length - 1];
  return last === undefined ? null : last.text;
}

/** Pure: the settle preview of the target on *my turn*; null otherwise or with no target. */
export function settlePreviewOf(state: StreamState): SettlePreview | null {
  if (effectiveKind(state) !== "turn") {
    return null;
  }
  const target = settleTargetText(state);
  return target === null ? null : previewSettle(target);
}

/** Effect: loads the record and the zone together; never rejects; writes nothing once aborted. */
export async function loadStream(state: StreamState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  const sessionId = state.sessionId;

  runInAction(() => {
    state.status = "loading";
  });

  let entries: Message[];
  let zone: Message[];
  try {
    // Both GETs go out together; the state is written once, after both succeed.
    [entries, zone] = await Promise.all([
      fetchEntries(sessionId, signal),
      fetchZone(sessionId, signal),
    ]);
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
    applyEntries(state, entries);
    state.zone = zone;
    state.status = "ready";
  });
}

/** Action: writes the entries; clears the override iff the id sequence changed (D8). */
export function applyEntries(state: StreamState, entries: Message[]): void {
  runInAction(() => {
    if (!sameIdSequence(state.entries, entries)) {
      state.kindOverride = null;
    }
    state.entries = entries;
  });
}

/** Action: writes the composer draft. */
export function setDraft(state: StreamState, draft: string): void {
  runInAction(() => {
    state.draft = draft;
  });
}

/** Action: writes the kind override. */
export function chooseKind(state: StreamState, kind: StreamKind): void {
  runInAction(() => {
    state.kindOverride = kind;
  });
}

/** Action: clears the draft and the override; makes no request (R11, D3). */
export function discardZone(state: StreamState): void {
  runInAction(() => {
    state.draft = "";
    state.kindOverride = null;
  });
}

// ---- 003: mutation effects. Never optimistic; never reject; write nothing once aborted. ----

/** Action: clears the draft only if it still equals the text that was sent (R10). */
function clearDraftIfUnchanged(state: StreamState, sent: string): void {
  runInAction(() => {
    if (state.draft === sent) {
      state.draft = "";
    }
  });
}

/** Action: writes the in-flight flag. */
function setBusy(state: StreamState, busy: boolean): void {
  runInAction(() => {
    state.busy = busy;
  });
}

/** Re-reads the entries; a failure is notified and the held list kept. False once aborted. */
async function rereadEntries(state: StreamState, signal?: AbortSignal): Promise<boolean> {
  try {
    const entries = await fetchEntries(state.sessionId, signal);
    if (signal?.aborted) {
      return false;
    }
    applyEntries(state, entries);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return false;
    }
    notifyFailure(error);
  }
  return true;
}

/** Re-reads the zone; a failure is notified and the held list kept. False once aborted. */
async function rereadZone(state: StreamState, signal?: AbortSignal): Promise<boolean> {
  try {
    const zone = await fetchZone(state.sessionId, signal);
    if (signal?.aborted) {
      return false;
    }
    runInAction(() => {
      state.zone = zone;
    });
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return false;
    }
    notifyFailure(error);
  }
  return true;
}

/** Re-reads both lists, each written (or notified) on its own. False once aborted. */
async function rereadBoth(state: StreamState, signal?: AbortSignal): Promise<boolean> {
  const [entriesAlive, zoneAlive] = await Promise.all([
    rereadEntries(state, signal),
    rereadZone(state, signal),
  ]);
  return entriesAlive && zoneAlive && !signal?.aborted;
}

/** Effect: appends (my turn) or files as partner the non-blank draft, then re-reads (D6, D7). */
export async function sendComposer(state: StreamState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  const text = state.draft;
  if (isBlank(text)) {
    return;
  }
  const sessionId = state.sessionId;
  const kind = effectiveKind(state);
  setBusy(state, true);

  let sent = false;
  try {
    if (kind === "turn") {
      await appendZoneMessage(sessionId, text, signal);
    } else {
      await filePartnerEntry(sessionId, text, signal);
    }
    sent = true;
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    notifyFailure(error);
  }
  if (signal?.aborted) {
    return;
  }
  if (sent) {
    clearDraftIfUnchanged(state, text);
  }

  const alive = kind === "turn"
    ? await rereadZone(state, signal)
    : await rereadEntries(state, signal);
  if (!alive) {
    return;
  }
  setBusy(state, false);
}

/** Effect: files the non-blank pasted text as a partner entry, then re-reads entries (D7). */
export async function filePastedPartner(
  state: StreamState,
  text: string,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted || isBlank(text)) {
    return;
  }
  setBusy(state, true);

  try {
    await filePartnerEntry(state.sessionId, text, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    notifyFailure(error);
  }
  if (signal?.aborted) {
    return;
  }

  if (!(await rereadEntries(state, signal))) {
    return;
  }
  setBusy(state, false);
}

/** Effect: appends a non-blank draft, settles, then re-reads both lists (D2). */
export async function settleComposer(state: StreamState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  const sessionId = state.sessionId;
  const text = state.draft;
  setBusy(state, true);

  if (!isBlank(text)) {
    try {
      await appendZoneMessage(sessionId, text, signal);
    } catch (error) {
      if (signal?.aborted || isAbortRejection(error)) {
        return;
      }
      notifyFailure(error);
      // The append failed: no settle request; the draft stays where it was (R10).
      if (!(await rereadZone(state, signal))) {
        return;
      }
      setBusy(state, false);
      return;
    }
    if (signal?.aborted) {
      return;
    }
    clearDraftIfUnchanged(state, text);
  }

  try {
    await settleZone(sessionId, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    notifyFailure(error);
  }
  if (signal?.aborted) {
    return;
  }

  if (!(await rereadBoth(state, signal))) {
    return;
  }
  setBusy(state, false);
}

/** Effect: re-opens the last entry, then re-reads both lists (D4). */
export async function reopenLast(state: StreamState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  setBusy(state, true);

  try {
    await reopenLastEntry(state.sessionId, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    notifyFailure(error);
  }
  if (signal?.aborted) {
    return;
  }

  if (!(await rereadBoth(state, signal))) {
    return;
  }
  setBusy(state, false);
}

/** Effect: commits an in-place zone edit; resolves to whether the editor may close (D10). */
export async function editZoneMessage(
  state: StreamState,
  messageId: string,
  text: string,
  signal?: AbortSignal,
): Promise<boolean> {
  if (isBlank(text)) {
    return true;
  }
  const current = state.zone.find((message) => message.id === messageId);
  if (current !== undefined && current.text === text) {
    return true;
  }
  if (signal?.aborted) {
    return false;
  }

  let updated: Message;
  try {
    updated = await editMessage(messageId, text, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return false;
    }
    notifyFailure(error);
    await rereadZone(state, signal);
    return false;
  }
  if (signal?.aborted) {
    return false;
  }

  // Only the edited row is replaced; every other row and the order are left as held.
  runInAction(() => {
    state.zone = state.zone.map((message) => (message.id === messageId ? updated : message));
  });
  return true;
}

// ---- 014 004: settled-entry edit. Never optimistic; never rejects; does not set `busy`. ----

/** Effect: commits a settled entry's edit; resolves to whether the editor may close (D10). */
export async function editEntry(
  state: StreamState,
  messageId: string,
  text: string,
  signal?: AbortSignal,
): Promise<boolean> {
  if (isBlank(text)) {
    return true;
  }
  const current = state.entries.find((message) => message.id === messageId);
  if (current !== undefined && current.text === text) {
    return true;
  }
  if (signal?.aborted) {
    return false;
  }

  let updated: Message;
  try {
    updated = await editMessage(messageId, text, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return false;
    }
    notifyFailure(error);
    await rereadEntries(state, signal);
    return false;
  }
  if (signal?.aborted) {
    return false;
  }

  if (updated.settled_at === null) {
    // Re-opened elsewhere: the row is no longer an entry, so both lists are re-read.
    return rereadBoth(state, signal);
  }

  // Only the edited row is replaced; the id sequence is unchanged, so the override stays.
  runInAction(() => {
    state.entries = state.entries.map((message) => (message.id === messageId ? updated : message));
  });
  return true;
}
