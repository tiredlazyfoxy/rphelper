// The Sessions section's state (feature 011, step 007, D1 / D5 / D15 / D18 / D19): one data
// class holding the parent character, that character's session rows, the Show-archived
// switch, and the row-action failure text with the row in flight — observable fields only, no methods
// and no computed getters. Every load, every mutation and the upsert rule are the free
// functions below, each taking the state as its first argument.
//
// The workspace `SessionsState` is a **parameter** of the three mutating effects, never a
// field here (`007.context.md`): a store that reaches into another store invisibly hides
// which states an action touches. The section component holds both and passes both (008).
// 033 D9: the section no longer starts sessions (the composer's send is the only create), so
// it holds no setup choices and no start status, and this module imports no router.
// Ordering compares fixed-width `last_used_at` text only, never an id; every id is a string
// and is never parsed or coerced.
import { makeAutoObservable, runInAction } from "mobx";

import type { Session } from "./sessionsApi";
import {
  archiveSession,
  fetchCharacterSessions,
  isSessionArchived,
  restoreSession,
} from "./sessionsApi";
import type { SessionsState } from "./sessionsState";
import { applySession } from "./sessionsState";

/**
 * Explicit load status of the session listing: gates the loading and failure renders, not
 * "rows are empty".
 */
export type SessionsSectionLoadStatus = "idle" | "loading" | "ready" | "failed";

export class SessionsSectionState {
  /** The character whose sessions this section lists. Never parsed. */
  characterId: string;
  sessions: Session[] = [];
  status: SessionsSectionLoadStatus = "idle";
  /** Show-archived is section-only state, never persisted (D5). */
  showArchived = false;
  /** The row-action failure text the section renders as given, or null (D18). */
  error: string | null = null;
  /** The id of the row whose archive/restore is in flight, or null. */
  pendingId: string | null = null;

  constructor(characterId: string) {
    this.characterId = characterId;
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/** The fixed 011 sentences (D18): one per action, never composed from an error. */
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
