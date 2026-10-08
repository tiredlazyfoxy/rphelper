// The partner flicker's state (feature 023, step 004): one data class holding, per settled
// partner row, whether its translation is shown, the text of its last success, whether a
// request is in flight and that request's controller — observable fields only, no methods and
// no computed getters (D13). The view derivation and every effect is a free function below,
// each taking the state first. `005` reads `translationView` and calls the effects.
import { makeAutoObservable, runInAction } from "mobx";

import { notifyFailure } from "../shared/notifyFailure";

import { translateMessage } from "./translationApi";

/** A row's display status: the original, a request in flight, or the translation (D13). */
export type TranslationView =
  | { status: "original" }
  | { status: "pending" }
  | { status: "translated"; text: string };

export class TranslationState {
  /** The rows currently showing their translation rather than the original. */
  shown = new Set<string>();
  /** Each row's translated text from its last success; absent means nothing cached (D13). */
  texts = new Map<string, string>();
  /** The rows with a translate request in flight. */
  pending = new Set<string>();
  /**
   * Each pending row's `AbortController`. Not observable, so aborting a request never
   * triggers a render (D13).
   */
  controllers = new Map<string, AbortController>();

  constructor() {
    makeAutoObservable(this, { controllers: false }, { autoBind: true });
  }
}

/** True when a rejection is an abort rather than a failure (the shared idiom). */
function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/**
 * Aborts the row's in-flight request, if any, and forgets it: the controller leaves the
 * non-observable map and the row leaves `pending`, so the next flick starts a fresh request
 * rather than cancelling a dead one. The cached text and the shown flag are untouched.
 */
function abortRow(state: TranslationState, messageId: string): void {
  const controller = state.controllers.get(messageId);
  if (controller === undefined) {
    return;
  }
  // Dropped before the abort, so the awaiting flick's cleanup sees a controller that is no
  // longer its own and writes nothing.
  state.controllers.delete(messageId);
  runInAction(() => {
    state.pending.delete(messageId);
  });
  controller.abort();
}

/**
 * Pure: the row's display status, carrying the translated text only when it is shown —
 * `"pending"` while its request is in flight, else `"translated"` when the row is flicked and
 * its text is cached, else `"original"`. The only derivation `005` reads.
 */
export function translationView(state: TranslationState, messageId: string): TranslationView {
  if (state.pending.has(messageId)) {
    return { status: "pending" };
  }
  const text = state.texts.get(messageId);
  if (state.shown.has(messageId) && text !== undefined) {
    return { status: "translated", text };
  }
  return { status: "original" };
}

/**
 * Effect: one flick of the row's flicker (D4, UC-040, US-045.AC-1, US-046.AC-1, US-048). Never
 * rejects. Pending cancels; shown un-shows; cached text is shown with no request; otherwise it
 * marks the row pending with a fresh controller, calls `translateMessage` with its signal,
 * caches and shows the text on success, notifies once on a failure, and writes nothing beyond
 * clearing its own pending entry on an abort. Writes happen inside `runInAction`, and pending
 * and the controller are cleared only while the row's controller is still this call's.
 */
export async function flickTranslation(state: TranslationState, messageId: string): Promise<void> {
  // Every branch decision, and every branch but the request, settles before the first await,
  // so a flick's effect on the view is visible without awaiting the returned promise.

  // 1. A request is in flight: the flicker is that request's cancel control (D4). No request
  //    goes out and nothing is notified, because a stop is not a failure.
  if (state.pending.has(messageId)) {
    cancelTranslation(state, messageId);
    return;
  }

  // 2. The translation is showing: flick back to the original, with no request (UC-040).
  if (state.shown.has(messageId)) {
    runInAction(() => {
      state.shown.delete(messageId);
    });
    return;
  }

  // 3. The text is already cached: show it again with no request (US-046.AC-1).
  if (state.texts.has(messageId)) {
    runInAction(() => {
      state.shown.add(messageId);
    });
    return;
  }

  // 4. Nothing cached: one request, under this call's own controller.
  const controller = new AbortController();
  runInAction(() => {
    state.pending.add(messageId);
  });
  state.controllers.set(messageId, controller);

  try {
    const translation = await translateMessage(messageId, controller.signal);
    if (!controller.signal.aborted) {
      runInAction(() => {
        state.texts.set(messageId, translation.text);
        state.shown.add(messageId);
      });
    }
  } catch (error) {
    // An abort writes nothing beyond the cleanup below and notifies nothing (D4,
    // US-133.AC-2). Any other failure stays on the original, caches nothing, and is
    // notified exactly once (US-048.AC-1, US-048.AC-2).
    if (!controller.signal.aborted && !isAbortRejection(error)) {
      notifyFailure(error);
    }
  } finally {
    // The controller-identity guard: only this call's own controller is cleared. After an
    // invalidate-then-reflick, the first call's cleanup must not clear the second call's
    // pending flag, and a late answer to an aborted request must write nothing at all.
    if (state.controllers.get(messageId) === controller) {
      state.controllers.delete(messageId);
      runInAction(() => {
        state.pending.delete(messageId);
      });
    }
  }
}

/**
 * Action: aborts the row's pending request, if any. The row stays on the original and nothing
 * is notified, because a stop is not a failure (D4, US-133.AC-2).
 */
export function cancelTranslation(state: TranslationState, messageId: string): void {
  abortRow(state, messageId);
}

/**
 * Action: drops the row's cached translation (D14, US-111). Aborts a pending request for the
 * row, forgets its text and un-shows it; a late answer to the aborted request writes nothing.
 */
export function invalidateTranslation(state: TranslationState, messageId: string): void {
  abortRow(state, messageId);
  runInAction(() => {
    state.texts.delete(messageId);
    state.shown.delete(messageId);
  });
}

/** Action: aborts every pending request, for use on unmount. Nothing is notified (D13). */
export function disposeTranslations(state: TranslationState): void {
  for (const messageId of [...state.controllers.keys()]) {
    abortRow(state, messageId);
  }
}
