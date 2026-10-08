// The Setups section's state (feature 010, step 004, D11): one data class holding the
// parent character id, the rows, the load status, the Show-archived switch, the row-action
// error and the in-flight row — observable fields only, no methods and no computed
// getters. The load effect, the two row actions and the upsert rule are the free functions
// below, each taking the state as its first argument.
// The upsert rule is 009 D11's, copied rather than generalised (`004.context.md`):
// `charactersState.ts` is a 009 file and is not touched.
import { makeAutoObservable, runInAction } from "mobx";

import type { Setup } from "./setupsApi";
import { archiveSetup, fetchSetups, isSetupArchived, restoreSetup } from "./setupsApi";

/** Explicit load status: gates the loading and failure renders, not "rows are empty". */
export type SetupsLoadStatus = "idle" | "loading" | "ready" | "failed";

export class SetupsSectionState {
  /** The parent character whose setups this section lists. A string, never parsed. */
  characterId: string;
  setups: Setup[] = [];
  status: SetupsLoadStatus = "idle";
  /** Show-archived is session-only state, never persisted (D4). */
  showArchived = false;
  /** The row-action failure text the section renders as given, or null (D12). */
  error: string | null = null;
  /** The id of the row whose archive/restore is in flight, or null. */
  pendingId: string | null = null;

  constructor(characterId: string) {
    this.characterId = characterId;
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/** The two fixed row-action sentences (D12): one per action, never composed from an error. */
const ARCHIVE_FAILED = "Could not archive the setup.";
const RESTORE_FAILED = "Could not restore the setup.";

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/** Whether this row belongs in the list: working, or archived while Show-archived is on. */
function isVisible(setup: Setup, showArchived: boolean): boolean {
  return !isSetupArchived(setup) || showArchived;
}

/**
 * Effect: load `state.characterId`'s listing with `includeArchived` equal to
 * `state.showArchived`. Sets "loading" first, then "ready" with the server's rows in the
 * server's order, or "failed" leaving the rows as they were. Writes nothing once aborted;
 * never rejects.
 */
export async function loadSetups(
  state: SetupsSectionState,
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

  let setups: Setup[];
  try {
    setups = await fetchSetups(characterId, includeArchived, signal);
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
    state.setups = setups;
    state.status = "ready";
  });
}

/** Effect: set the Show-archived flag. Issues no request (the section reloads, 006). */
export function setShowArchived(state: SetupsSectionState, showArchived: boolean): void {
  runInAction(() => {
    state.showArchived = showArchived;
  });
}

/** Upsert one server-returned setup into the section's rows per D11's rule. */
export function applySetup(state: SetupsSectionState, setup: Setup): void {
  runInAction(() => {
    const visible = isVisible(setup, state.showArchived);
    const index = state.setups.findIndex((row) => row.id === setup.id);

    if (index >= 0) {
      if (!visible) {
        // Archived while Show-archived is off: it leaves the list.
        state.setups = state.setups.filter((row) => row.id !== setup.id);
        return;
      }
      // Present and still visible: replaced in place, position unchanged.
      const next = state.setups.slice();
      next[index] = setup;
      state.setups = next;
      return;
    }

    if (!visible) {
      // Absent and not visible: nothing to insert.
      return;
    }

    // Absent and visible: insert at its `created_at`-descending position — before the
    // first row older than it, or at the end. Fixed-width timestamps compare as text.
    const next = state.setups.slice();
    const at = next.findIndex((row) => row.created_at < setup.created_at);
    if (at < 0) {
      next.push(setup);
    } else {
      next.splice(at, 0, setup);
    }
    state.setups = next;
  });
}

/**
 * The shared row-action shape: clear `error`, mark the row pending, POST the action and
 * apply the server's row. A failure sets the action's fixed sentence and leaves the rows
 * as they were (never optimistic — no refetch, no local edit). `pendingId` returns to null
 * on both settled paths. Writes nothing once aborted; never rejects.
 */
async function runRowAction(
  state: SetupsSectionState,
  setupId: string,
  action: (setupId: string, signal?: AbortSignal) => Promise<Setup>,
  failureMessage: string,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    state.error = null;
    state.pendingId = setupId;
  });

  let setup: Setup;
  try {
    setup = await action(setupId, signal);
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
    applySetup(state, setup);
    state.pendingId = null;
  });
}

/**
 * Effect: `POST /api/setups/<setupId>/archive`, then apply the returned row. Clears
 * `error` and sets `pendingId` first; a failure sets the fixed archive sentence and leaves
 * the rows unchanged. `pendingId` returns to null either way. Writes nothing once aborted;
 * never rejects.
 */
export async function archiveRow(
  state: SetupsSectionState,
  setupId: string,
  signal?: AbortSignal,
): Promise<void> {
  await runRowAction(state, setupId, archiveSetup, ARCHIVE_FAILED, signal);
}

/**
 * Effect: `POST /api/setups/<setupId>/restore`, then apply the returned row. Clears
 * `error` and sets `pendingId` first; a failure sets the fixed restore sentence and leaves
 * the rows unchanged. `pendingId` returns to null either way. Writes nothing once aborted;
 * never rejects.
 */
export async function restoreRow(
  state: SetupsSectionState,
  setupId: string,
  signal?: AbortSignal,
): Promise<void> {
  await runRowAction(state, setupId, restoreSetup, RESTORE_FAILED, signal);
}
