// The restore-from-export choice's state: a data class (observable fields only) plus free
// functions over it, mirroring `createAdminDraft.ts` (fast/003 Decision 4).
import { makeAutoObservable, runInAction } from "mobx";
import { apiPost, documentNavigation } from "../shared/api";
import { readExportFile } from "../shared/importFile";

/** The navigation seam the submit hands off through; `documentNavigation` from `shared/api`. */
export type RestoreNavigation = {
  assign(url: string): void;
};

export class RestoreExportState {
  /** The chosen export file, or none. */
  file: File | null = null;
  /** True while the restore request is in flight. */
  submitting = false;
  /** The current failure message, or none. */
  failureMessage: string | null = null;

  constructor() {
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

const RESTORE_PATH = "/api/bootstrap/import";
const LOGIN_PATH = "/login";
const GENERIC_FAILURE = "The database could not be restored.";

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/** Pure: the message stored for a failed restore (an unreadable file or any API error). */
export function failureMessageOf(error: unknown): string {
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }
  return GENERIC_FAILURE;
}

/** Sets the chosen file and clears any previous failure. */
export function chooseRestoreFile(state: RestoreExportState, file: File | null): void {
  runInAction(() => {
    state.file = file;
    state.failureMessage = null;
  });
}

/**
 * Reads the chosen file with `readExportFile`, posts the parsed object with `apiPost` to
 * `/api/bootstrap/import`, and on success calls `navigation.assign("/login")`. On any failure
 * stores `failureMessageOf(error)` and does not navigate. Holds `submitting` for the duration;
 * ignores an abort the way `submitCreateAdmin` does. Does not reject.
 */
export async function submitRestoreExport(
  state: RestoreExportState,
  signal?: AbortSignal,
  navigation?: RestoreNavigation,
): Promise<void> {
  const file = state.file;
  if (signal?.aborted || state.submitting || file === null) {
    return;
  }
  const handOff = navigation ?? documentNavigation;

  runInAction(() => {
    state.submitting = true;
    state.failureMessage = null;
  });
  try {
    const parsed = await readExportFile(file);
    await apiPost<unknown>(RESTORE_PATH, parsed, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    const message = failureMessageOf(error);
    runInAction(() => {
      state.failureMessage = message;
    });
    return;
  } finally {
    runInAction(() => {
      state.submitting = false;
    });
  }

  if (signal?.aborted) {
    return;
  }
  handOff.assign(LOGIN_PATH);
}
