// The session stream's state (feature 013, step 002): one data class holding the record,
// the zone, the load status, the composer draft, the kind override and the in-flight flag —
// observable fields only, no methods and no computed getters. Every derivation and every
// effect is a free function below, each taking the state first. `003` adds the mutations.
import { makeAutoObservable, runInAction } from "mobx";

import { ApiError } from "../shared/apiError";
import { notifyFailure } from "../shared/notifyFailure";
import type { SseOutcome, SseProgressFrame } from "../shared/sse";

import type { SettlePreview } from "./parens";
import { previewSettle } from "./parens";
import type { Message, ReopenResult, SettleResult } from "./streamApi";
import {
  appendZoneMessage,
  composeZone,
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
  /** 019 D11: the in-flight assistant text; `null` means not streaming. */
  streamingText: string | null = null;
  /** 019 D12: the in-flight compose's controller and wound-down promise. Not observable. */
  composeHandle: ComposeHandle | null = null;
  /** 022 D7: the in-flight compose's tool calls, in arrival order; emptied with the text. */
  liveTools: LiveToolCall[] = [];
  /**
   * 024 D11: whether the latest record-keeping write in this mount committed without being
   * indexed for search. False on construction — no staleness is persisted (024 U5) — and
   * written only by the effects below, never by a method on this class.
   */
  searchCoverageIncomplete = false;
  /**
   * fast/004 D3: whether `composeFirstReply` has already started a compose on this instance.
   * The once-flag; a fresh `StreamState` (another session) starts false. Not observable.
   */
  firstReplyStarted = false;

  constructor(sessionId: string) {
    this.sessionId = sessionId;
    makeAutoObservable(
      this,
      { composeHandle: false, firstReplyStarted: false },
      { autoBind: true },
    );
  }
}

/** 019 D12: the in-flight compose's own controller and the promise that settles at wind-down. */
export type ComposeHandle = {
  controller: AbortController;
  woundDown: Promise<void>;
};

/** 022 D7: a live tool call's status. */
export type LiveToolStatus = "running" | "ok" | "failed";

/** 022 D7: one live tool call, fed by the compose run's `tool_*` frames. */
export type LiveToolCall = {
  callId: string;
  tool: string;
  args: Record<string, unknown>;
  status: LiveToolStatus;
  summary: string | null;
};

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

/** 022 D9: pure: true when the row is not a tool row. */
function isNonToolRow(message: Message): boolean {
  return message.role !== "tool";
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

/** 019 D12: pure: true iff the streaming text is not null. */
export function isStreaming(state: StreamState): boolean {
  return state.streamingText !== null;
}

/** 019 D12, UC-085: action: aborts the compose handle's controller, if any; writes nothing. */
export function stopCompose(state: StreamState): void {
  state.composeHandle?.controller.abort();
}

/** Pure: true when the draft is not blank, nothing is in flight and not streaming (019 D13). */
export function canSend(state: StreamState): boolean {
  return !isBlank(state.draft) && !state.busy && !isStreaming(state);
}

/** Pure: true on *my turn*, not busy, with a zone row or a non-blank draft (US-135). */
export function canSettle(state: StreamState): boolean {
  if (effectiveKind(state) !== "turn" || state.busy) {
    return false;
  }
  return state.zone.some(isNonToolRow) || !isBlank(state.draft);
}

/** Pure: true when the zone is empty, the draft is blank and not streaming (D3, 019 D13). */
export function showsDiscard(state: StreamState): boolean {
  return state.zone.length === 0 && isBlank(state.draft) && !isStreaming(state);
}

/** 022 D8: pure: true iff not streaming, not busy, and the zone holds a non-tool row. */
export function showsRegenerate(state: StreamState): boolean {
  return !isStreaming(state) && !state.busy && state.zone.some(isNonToolRow);
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
  for (let index = state.zone.length - 1; index >= 0; index -= 1) {
    const row = state.zone[index];
    if (row !== undefined && isNonToolRow(row)) {
      return row.text;
    }
  }
  return null;
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

/**
 * Effect: on *my turn* composes the draft (021 D12, delegated to `composeMessage`, which owns
 * the outcome and never sets `busy`); on *partner* files the non-blank draft, then re-reads (D7).
 */
export async function sendComposer(state: StreamState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  const text = state.draft;
  if (isBlank(text)) {
    return;
  }
  const kind = effectiveKind(state);
  if (kind === "turn") {
    await composeMessage(state, signal);
    return;
  }
  const sessionId = state.sessionId;
  setBusy(state, true);

  // 024 007: the filed row is captured (it was discarded before) so its coverage flag can be
  // read. `undefined` means the request failed, which is exactly the old `sent === false`.
  let filed: Message | undefined;
  try {
    filed = await filePartnerEntry(sessionId, text, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    notifyFailure(error);
  }
  if (signal?.aborted) {
    return;
  }
  if (filed !== undefined) {
    clearDraftIfUnchanged(state, text);
  }

  // 024 007 (D10, D11): a settled filing reports its coverage; a zone row (null `settled_at`)
  // and a failed request both leave the flag as it is, so nothing is written in the `catch`.
  if (filed !== undefined && filed.settled_at !== null) {
    const incomplete = filed.search_coverage_incomplete ?? false;
    runInAction(() => {
      state.searchCoverageIncomplete = incomplete;
    });
  }

  const alive = await rereadEntries(state, signal);
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

  // 024 007: the filed row is captured (it was discarded before) for its coverage flag.
  let filed: Message | undefined;
  try {
    filed = await filePartnerEntry(state.sessionId, text, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    notifyFailure(error);
  }
  if (signal?.aborted) {
    return;
  }

  // 024 007 (D10, D11): same rule as `sendComposer`'s partner branch — only a settled filing
  // writes the flag. Zone rows and failures leave it unchanged.
  if (filed !== undefined && filed.settled_at !== null) {
    const incomplete = filed.search_coverage_incomplete ?? false;
    runInAction(() => {
      state.searchCoverageIncomplete = incomplete;
    });
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
  // 019 D16: a compose in flight is stopped and wound down (its re-read included) first.
  const handle = state.composeHandle;
  if (handle !== null) {
    setBusy(state, true);
    stopCompose(state);
    await handle.woundDown;
    if (signal?.aborted) {
      return;
    }
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

  // 024 007: the settle result is captured (it was discarded before) for its coverage flag.
  let settled: SettleResult | undefined;
  try {
    settled = await settleZone(sessionId, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    notifyFailure(error);
  }
  if (signal?.aborted) {
    return;
  }

  // 024 007 (D10, D11): the settle reports its coverage, an absent field reading as complete.
  // A failed settle leaves the flag as it is, so nothing is written in the `catch`.
  if (settled !== undefined) {
    const incomplete = settled.search_coverage_incomplete ?? false;
    runInAction(() => {
      state.searchCoverageIncomplete = incomplete;
    });
  }

  if (!(await rereadBoth(state, signal))) {
    return;
  }
  setBusy(state, false);
}

// ---- 019 005: the compose effect. Never optimistic; never rejects; never touches `busy`. ----

/** Effect: streams a compose of the draft into the zone; outcomes per 019 D14, D15 (UC-085). */
export async function composeMessage(state: StreamState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted || isStreaming(state) || state.composeHandle !== null) {
    return;
  }
  const sent = state.draft;
  if (isBlank(sent)) {
    return;
  }
  await runCompose(state, sent, signal);
}

/** 022 D7: action: applies one tool frame to the live tool list (unknown call ids ignored). */
function applyToolFrame(state: StreamState, frame: SseProgressFrame): void {
  runInAction(() => {
    if (frame.event === "tool_start") {
      state.liveTools.push({
        callId: frame.call_id,
        tool: frame.tool,
        args: frame.args,
        status: "running",
        summary: null,
      });
      return;
    }
    if (frame.event !== "tool_result" && frame.event !== "tool_fail") {
      return;
    }
    const entry = state.liveTools.find((call) => call.callId === frame.call_id);
    if (entry === undefined) {
      return;
    }
    if (frame.event === "tool_result") {
      entry.status = "ok";
      entry.summary = frame.summary;
    } else {
      entry.status = "failed";
      entry.summary = TOOL_FAILED_SUMMARY;
    }
  });
}

/** 022 D7: the live failed-tool summary, 021's failed-row literal. */
const TOOL_FAILED_SUMMARY = "The tool failed.";

/**
 * The compose run shared by `composeMessage` (with the sent text) and `regenerate` (textless,
 * `sent` undefined): 019 D11–D16 plus 022 D7's live tool list. Never rejects; never touches
 * `busy`; a textless run never reads or writes the draft.
 */
async function runCompose(
  state: StreamState,
  sent: string | undefined,
  signal?: AbortSignal,
): Promise<void> {
  const sessionId = state.sessionId;

  // The compose's own controller, linked so that a mount abort (unmount) aborts it (D12).
  const controller = new AbortController();
  let resolveWoundDown: () => void = () => undefined;
  const woundDown = new Promise<void>((resolve) => {
    resolveWoundDown = resolve;
  });
  const onMountAbort = (): void => {
    controller.abort();
  };
  signal?.addEventListener("abort", onMountAbort);

  runInAction(() => {
    state.streamingText = "";
    state.composeHandle = { controller, woundDown };
    state.liveTools = [];
  });

  try {
    let acceptedReread: Promise<boolean> | null = null;

    const onFrame = (frame: SseProgressFrame): void => {
      if (signal?.aborted) {
        return;
      }
      if (frame.event === "accepted") {
        // D15: the sent text is now a row; adopt its id through a zone re-read.
        // A textless run (022 D8) never touches the draft; it only re-reads.
        if (sent !== undefined) {
          clearDraftIfUnchanged(state, sent);
        }
        acceptedReread = rereadZone(state, signal);
      } else if (frame.event === "token") {
        runInAction(() => {
          state.streamingText = (state.streamingText ?? "") + frame.text;
        });
      } else {
        // 022 D7 (supersedes 019 D18): tool frames feed the live tool list, never `zone`.
        applyToolFrame(state, frame);
      }
    };

    let outcome: SseOutcome;
    try {
      outcome = await composeZone(sessionId, sent, onFrame, controller.signal);
    } catch (error) {
      // The consumer never rejects; this guards the "never rejects" contract regardless.
      outcome = controller.signal.aborted
        ? { kind: "stopped" }
        : {
            kind: "error",
            error: error instanceof ApiError
              ? error
              : new ApiError("client_transport_failed", "The server could not be reached.", 0),
          };
    }
    if (signal?.aborted) {
      return;
    }

    // D15: the terminal re-read never races ahead of the accepted-triggered one.
    if (acceptedReread !== null) {
      await acceptedReread;
    }
    if (signal?.aborted) {
      return;
    }

    // D14: done and a user stop notify nothing.
    if (outcome.kind === "error") {
      notifyFailure(outcome.error);
    } else if (outcome.kind === "unexpected_end") {
      notifyFailure(new ApiError("llm_unreachable", "The reply ended unexpectedly.", 0, {}));
    }

    // D14: the server's rows replace the in-flight text in one action.
    try {
      const zone = await fetchZone(sessionId, signal);
      if (signal?.aborted) {
        return;
      }
      runInAction(() => {
        state.zone = zone;
        state.streamingText = null;
        state.composeHandle = null;
        state.liveTools = [];
      });
    } catch (error) {
      if (signal?.aborted) {
        return;
      }
      if (!isAbortRejection(error)) {
        notifyFailure(error);
      }
      runInAction(() => {
        state.streamingText = null;
        state.composeHandle = null;
        state.liveTools = [];
      });
    }
  } finally {
    signal?.removeEventListener("abort", onMountAbort);
    resolveWoundDown();
  }
}

/**
 * 022 D8: effect: a textless compose (body `{}`) through `composeMessage`'s run machinery;
 * no-op unless `showsRegenerate`; never reads or writes the draft; never rejects.
 */
export async function regenerate(state: StreamState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted || !showsRegenerate(state) || state.composeHandle !== null) {
    return;
  }
  await runCompose(state, undefined, signal);
}

/**
 * fast/004 D3: effect: the first-reply compose after arrival from the character page — one
 * textless compose (body `{}`) through `runCompose`, at most once per `StreamState`. Starts
 * only when ready, not streaming or busy, the zone's last non-tool row is `role: "user"`, the
 * signal is not aborted and no first reply was started before; otherwise a no-op with no
 * request. Never rejects; failure goes through `notifyFailure`, the zone is re-read at the end.
 */
export async function composeFirstReply(state: StreamState, signal: AbortSignal): Promise<void> {
  if (
    state.firstReplyStarted ||
    signal.aborted ||
    state.status !== "ready" ||
    isStreaming(state) ||
    state.busy ||
    state.composeHandle !== null
  ) {
    return;
  }
  const lastNonTool = state.zone.filter(isNonToolRow).at(-1);
  if (lastNonTool === undefined || lastNonTool.role !== "user") {
    return;
  }
  state.firstReplyStarted = true;
  await runCompose(state, undefined, signal);
}

/** Effect: re-opens the last entry, then re-reads both lists (D4). */
export async function reopenLast(state: StreamState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  setBusy(state, true);

  // 024 007: the re-open result is captured (it was discarded before) for its coverage flag.
  let reopened: ReopenResult | undefined;
  try {
    reopened = await reopenLastEntry(state.sessionId, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    notifyFailure(error);
  }
  if (signal?.aborted) {
    return;
  }

  // 024 007 (D10, D11): the re-open reports its coverage, an absent field reading as complete.
  // A failed re-open leaves the flag as it is.
  if (reopened !== undefined) {
    const incomplete = reopened.search_coverage_incomplete ?? false;
    runInAction(() => {
      state.searchCoverageIncomplete = incomplete;
    });
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
    // Re-opened elsewhere: the row is no longer an entry, so both lists are re-read. 024 D11:
    // a zone row leaves the coverage flag unchanged, so this early return stays flagless.
    return rereadBoth(state, signal);
  }

  // Only the edited row is replaced; the id sequence is unchanged, so the override stays.
  // 024 007 (D10, D11): reached only on the settled path, so this is also where the edit's
  // coverage is recorded, an absent field reading as complete. Nothing is written in the
  // `catch`.
  runInAction(() => {
    state.entries = state.entries.map((message) => (message.id === messageId ? updated : message));
    state.searchCoverageIncomplete = updated.search_coverage_incomplete ?? false;
  });
  return true;
}
