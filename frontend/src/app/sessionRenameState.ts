// The in-place session rename (feature 034, step 005, DEC-034-11): one data class holding
// which session is being renamed, the draft, the name it had when editing began, the pending
// flag and the inline error — observable fields only, no methods and no computed getters.
// Opening, cancelling and committing are the free functions below, each taking the state first.
//
// One instance per host: the tree and the session header each own one (DEC-034-11). The
// workspace `SessionsState` is a **parameter** of the commit, never a field here.
import { makeAutoObservable, runInAction } from "mobx";

import type { Session } from "./sessionsApi";
import { renameSession } from "./sessionsApi";
import type { SessionsState } from "./sessionsState";
import { applySession } from "./sessionsState";

/** The fixed inline failure sentence (DEC-034-11); never a notification. */
const RENAME_FAILED = "Could not rename the session.";

/**
 * The state of one host's rename editor. Invariant: the editor is open exactly when
 * `editingId` is non-null; `pending` is true only while one rename request is in flight.
 */
export class SessionRenameState {
  /** The id of the session being renamed, or null when no editor is open. Never parsed. */
  editingId: string | null = null;
  /** The text the input edits; normalised (trimmed, blank to null) only on commit. */
  draft = "";
  /** The session's `name` at the moment editing began — the "unchanged" reference. */
  originalName: string | null = null;
  /** Whether a rename request is in flight; begin, cancel and a second commit are ignored. */
  pending = false;
  /** The inline failure text ("Could not rename the session."), or null. */
  error: string | null = null;

  constructor() {
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/**
 * Opens editing for `session`: `editingId` becomes its id, the draft becomes its current
 * name (empty when the name is null), `originalName` its name, and the error is cleared.
 * Does nothing while a commit is pending. Sends no request.
 *
 * @param state - the host's rename state.
 * @param session - the session to rename.
 */
export function beginRename(state: SessionRenameState, session: Session): void {
  if (state.pending) {
    return;
  }
  runInAction(() => {
    state.editingId = session.id;
    // A never-renamed session (name null) opens with an empty draft, not its date label
    // (DEC-arch-session-names-4).
    state.draft = session.name ?? "";
    state.originalName = session.name;
    state.error = null;
  });
}

/**
 * Closes the editor and sends nothing. Does nothing while a commit is pending.
 *
 * @param state - the host's rename state.
 */
export function cancelRename(state: SessionRenameState): void {
  // Escape during the request is ignored: the answer decides whether the editor closes.
  if (state.pending) {
    return;
  }
  runInAction(() => {
    closeEditor(state);
  });
}

/** Closes the editor: no editing id, empty draft, no original name, no error. Call inside an action. */
function closeEditor(state: SessionRenameState): void {
  state.editingId = null;
  state.draft = "";
  state.originalName = null;
  state.error = null;
}

/** Trims the draft; a blank result becomes `null` (clears the name, US-150.AC-3). */
function normaliseDraft(draft: string): string | null {
  const trimmed = draft.trim();
  return trimmed.length === 0 ? null : trimmed;
}

/** Whether a rejection is the fetch's own abort, as opposed to a request failure. */
function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/**
 * Effect: commits the draft. The draft is normalised — trimmed, blank becomes `null`. When
 * the normalised value equals `originalName` the editor closes with no request. Otherwise
 * `pending` is set and exactly one `renameSession` is sent; a commit while pending sends
 * nothing. Never optimistic: nothing is written to `sessions` before the answer.
 *
 * On success, inside one `runInAction`: the returned session is applied to `sessions`
 * (`applySession`), handed to `onRenamed`, and the editor closes. On failure: `error`
 * becomes "Could not rename the session.", the editor stays open with the draft, no list
 * changes and no notification is raised. Once aborted, nothing is written to either store.
 * Never rejects.
 *
 * @param state - the host's rename state.
 * @param sessions - the workspace sessions list the returned session is applied to.
 * @param onRenamed - optional; receives the server-returned session on success.
 * @param signal - optional abort signal.
 */
export async function commitRename(
  state: SessionRenameState,
  sessions: SessionsState,
  onRenamed?: (session: Session) => void,
  signal?: AbortSignal,
): Promise<void> {
  const sessionId = state.editingId;
  // The pending guard makes Enter-then-blur send exactly one request (DoD-4); a closed
  // editor has nothing to commit.
  if (state.pending || sessionId === null || signal?.aborted) {
    return;
  }

  const name = normaliseDraft(state.draft);
  if (name === state.originalName) {
    // Unchanged — including a blank draft on a never-renamed session — sends nothing.
    runInAction(() => {
      closeEditor(state);
    });
    return;
  }

  runInAction(() => {
    state.pending = true;
    state.error = null;
  });
  let aborted = false;
  try {
    const renamed = await renameSession(sessionId, name, signal);
    if (signal?.aborted) {
      aborted = true;
      return;
    }
    // Never optimistic: the workspace list changes only here, with the server's row.
    runInAction(() => {
      applySession(sessions, renamed);
      onRenamed?.(renamed);
      closeEditor(state);
    });
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      aborted = true;
      return;
    }
    // Inline failure (DEC-034-11): the editor stays open with the typed draft.
    runInAction(() => {
      state.error = RENAME_FAILED;
    });
  } finally {
    // Once aborted the host is gone or moved on: nothing more is written to the state.
    if (!aborted) {
      runInAction(() => {
        state.pending = false;
      });
    }
  }
}
