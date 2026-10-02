// The Sessions section's state (feature 011, step 007, D1 / D5 / D15 / D18 / D19): one data
// class holding the parent character, that character's session rows, the Show-archived
// switch, the setup choices and the current choice, the start status and its failure text,
// and the row-action failure text with the row in flight — observable fields only, no methods
// and no computed getters. Every load, every mutation and the upsert rule are the free
// functions below, each taking the state as its first argument.
//
// The workspace `SessionsState` is a **parameter** of the three mutating effects, never a
// field here (`007.context.md`): a store that reaches into another store invisibly hides
// which states an action touches. The section component holds both and passes both (008).
// Navigation is reported through `onStarted`, so this module imports no router.
// The setup choices are a separate load from the session rows, so a failure of one never
// blocks the other (US-024.AC-3, D18).
// Ordering compares fixed-width `last_used_at` text only, never an id; every id is a string
// and is never parsed or coerced.
import { makeAutoObservable, runInAction } from "mobx";

import type { Session } from "./sessionsApi";
import {
  archiveSession,
  fetchCharacterSessions,
  isSessionArchived,
  restoreSession,
  startSession,
} from "./sessionsApi";
import type { SessionsState } from "./sessionsState";
import { applySession } from "./sessionsState";
import type { Setup } from "./setupsApi";
import { fetchSetups } from "./setupsApi";

/**
 * Explicit load status, used for both of the section's two independent loads: gates the
 * loading and failure renders, not "rows are empty".
 */
export type SessionsSectionLoadStatus = "idle" | "loading" | "ready" | "failed";

/** The start button's own status: there is no "failed" state — a failure is `startError`. */
export type SessionStartStatus = "idle" | "submitting";

export class SessionsSectionState {
  /** The character under which this section lists and starts sessions. Never parsed. */
  characterId: string;
  sessions: Session[] = [];
  status: SessionsSectionLoadStatus = "idle";
  /** Show-archived is section-only state, never persisted (D5). */
  showArchived = false;
  /** The character's working setups, offered as choices beside "No setup" (D1, D19). */
  setups: Setup[] = [];
  setupsStatus: SessionsSectionLoadStatus = "idle";
  /** The chosen setup, or null for "No setup" — no sentinel row exists (R2). */
  selectedSetupId: string | null = null;
  startStatus: SessionStartStatus = "idle";
  /** The start failure text the section renders as given, or null (D18). */
  startError: string | null = null;
  /** The row-action failure text the section renders as given, or null (D18). */
  error: string | null = null;
  /** The id of the row whose archive/restore is in flight, or null. */
  pendingId: string | null = null;

  constructor(characterId: string) {
    this.characterId = characterId;
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/** The three fixed 011 sentences (D18): one per action, never composed from an error. */
const START_FAILED = "Could not start the session.";
const ARCHIVE_FAILED = "Could not archive the session.";
const RESTORE_FAILED = "Could not restore the session.";

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/** Whether this row belongs in the list: working, or archived while Show-archived is on. */
function isVisible(session: Session, showArchived: boolean): boolean {
  return !isSessionArchived(session) || showArchived;
}

/**
 * Effect: load `state.characterId`'s sessions with `includeArchived` equal to
 * `state.showArchived`. Sets "loading" first, then "ready" with the server's rows in the
 * server's order, or "failed" leaving the rows as they were. Writes nothing once aborted;
 * never rejects.
 */
export async function loadSectionSessions(
  state: SessionsSectionState,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  const characterId = state.characterId;
  const includeArchived = state.showArchived;
  runInAction(() => {
    state.status = "loading";
  });

  let sessions: Session[];
  try {
    sessions = await fetchCharacterSessions(characterId, includeArchived, signal);
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
    state.sessions = sessions;
    state.status = "ready";
  });
}

/** Effect: set the Show-archived flag. Issues no request (the section reloads, 008). */
export function setShowArchived(state: SessionsSectionState, showArchived: boolean): void {
  runInAction(() => {
    state.showArchived = showArchived;
  });
}

/**
 * Effect: load the character's **working** setups as the Select's choices. Sets
 * `setupsStatus` "loading" first, then "ready" with the server's setups in the server's
 * order; a selection that is no longer among them is reset to null in the same action. A
 * failure sets "failed" and keeps both the previous choices and the selection. Writes
 * nothing once aborted; never rejects.
 */
export async function loadSetupChoices(
  state: SessionsSectionState,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  const characterId = state.characterId;
  runInAction(() => {
    state.setupsStatus = "loading";
  });

  let setups: Setup[];
  try {
    // Archived setups are never offered (D1, D19), so the flag is always false here.
    setups = await fetchSetups(characterId, false, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    // A failed reload keeps the previous choices and the selection: the server still answers
    // a stale choice (409 `setup_archived`), which lands in `startError` like any other
    // start failure.
    runInAction(() => {
      state.setupsStatus = "failed";
    });
    return;
  }

  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    state.setups = setups;
    state.setupsStatus = "ready";
    // A successful reload that no longer holds the selection resets it to "No setup" in the
    // same action, so the Select never displays a value that is not among its options.
    const selected = state.selectedSetupId;
    if (selected !== null && !setups.some((setup) => setup.id === selected)) {
      state.selectedSetupId = null;
    }
  });
}

/** Effect: choose a setup, or null for "No setup". Issues no request. */
export function selectSetup(state: SessionsSectionState, setupId: string | null): void {
  runInAction(() => {
    state.selectedSetupId = setupId;
  });
}

/**
 * Upsert one server-returned session into the section's rows: archived while Show-archived
 * is off leaves the list; otherwise removed if present and inserted at its
 * `last_used_at`-descending position, so an unchanged `last_used_at` keeps its index.
 */
export function applySectionSession(state: SessionsSectionState, session: Session): void {
  runInAction(() => {
    // Removed first, then re-inserted (004's rule): from `012` on a content write moves
    // `last_used_at` and the row must move with it.
    const next = state.sessions.filter((row) => row.id !== session.id);

    if (!isVisible(session, state.showArchived)) {
      // Archived while Show-archived is off: removed if present, never inserted.
      state.sessions = next;
      return;
    }

    // Insert at its `last_used_at`-descending position: before the first row whose
    // `last_used_at` is less than the new one's, else at the end. Equal values insert after
    // the equal rows. Fixed-width timestamps compare as text; nothing compares an id.
    const at = next.findIndex((row) => row.last_used_at < session.last_used_at);
    if (at < 0) {
      next.push(session);
    } else {
      next.splice(at, 0, session);
    }
    state.sessions = next;
  });
}

/**
 * Effect: start a session under `state.characterId` with `state.selectedSetupId` (null for
 * "No setup"). Clears `startError` and sets `startStatus` "submitting" first; on success
 * applies the returned row to the section **and** to the workspace state (D15), then reports
 * the new id exactly as received through `onStarted` — the component navigates (008). A
 * failure sets the fixed start sentence and changes neither list (never optimistic).
 * `startStatus` returns to "idle" on both settled paths. Writes nothing once aborted; never
 * rejects.
 */
export async function startSessionFromSection(
  state: SessionsSectionState,
  workspace: SessionsState,
  onStarted: (sessionId: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  const characterId = state.characterId;
  // "No setup" is null on the wire — no sentinel setup exists (R2).
  const setupId = state.selectedSetupId;
  runInAction(() => {
    state.startError = null;
    state.startStatus = "submitting";
  });

  let session: Session;
  try {
    session = await startSession(characterId, setupId, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    runInAction(() => {
      state.startError = START_FAILED;
      state.startStatus = "idle";
    });
    return;
  }

  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    applySectionSession(state, session);
    applySession(workspace, session);
    state.startStatus = "idle";
  });
  // Navigation is the section component's (008); the id goes out exactly as received.
  onStarted(session.id);
}

/**
 * The shared row-action shape: clear `error`, mark the row pending, POST the action and
 * apply the server's row to both the section and the workspace list (D15). A failure sets
 * the action's fixed sentence and leaves both lists as they were (never optimistic — no
 * refetch, no local edit). `pendingId` returns to null on both settled paths. Writes nothing
 * once aborted; never rejects.
 */
async function runRowAction(
  state: SessionsSectionState,
  workspace: SessionsState,
  sessionId: string,
  action: (sessionId: string, signal?: AbortSignal) => Promise<Session>,
  failureMessage: string,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    state.error = null;
    state.pendingId = sessionId;
  });

  let session: Session;
  try {
    session = await action(sessionId, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    runInAction(() => {
      state.error = failureMessage;
      state.pendingId = null;
    });
    return;
  }

  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    applySectionSession(state, session);
    applySession(workspace, session);
    state.pendingId = null;
  });
}

/**
 * Effect: `POST /api/sessions/<sessionId>/archive`, then apply the returned row to the
 * section and to the workspace state (D15). Clears `error` and sets `pendingId` first; a
 * failure sets the fixed archive sentence and leaves both lists unchanged. `pendingId`
 * returns to null either way. Writes nothing once aborted; never rejects.
 */
export async function archiveSectionRow(
  state: SessionsSectionState,
  workspace: SessionsState,
  sessionId: string,
  signal?: AbortSignal,
): Promise<void> {
  await runRowAction(state, workspace, sessionId, archiveSession, ARCHIVE_FAILED, signal);
}

/**
 * Effect: `POST /api/sessions/<sessionId>/restore`, then apply the returned row to the
 * section and to the workspace state (D15). Clears `error` and sets `pendingId` first; a
 * failure sets the fixed restore sentence and leaves both lists unchanged. `pendingId`
 * returns to null either way. Writes nothing once aborted; never rejects.
 */
export async function restoreSectionRow(
  state: SessionsSectionState,
  workspace: SessionsState,
  sessionId: string,
  signal?: AbortSignal,
): Promise<void> {
  await runRowAction(state, workspace, sessionId, restoreSession, RESTORE_FAILED, signal);
}
