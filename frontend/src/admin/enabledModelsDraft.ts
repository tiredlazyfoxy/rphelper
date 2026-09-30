// The enabled-models modal's draft (multi-select): a data class (observable fields only, no
// methods, no computed getters) plus free functions over it (context.md D11 / D16 / D17).
import { makeAutoObservable, runInAction } from "mobx";
import { apiPost } from "../shared/api";
import { ApiError, CLIENT_TRANSPORT_FAILED } from "../shared/apiError";

/** Keys of the server-error map: only the general catch-all. */
export type EnabledModelsServerErrorKey = "general";

/** Status- or code-keyed server errors; everything lands on `general`. */
export type EnabledModelsServerErrors = Partial<Record<EnabledModelsServerErrorKey, string>>;

/** Submit lifecycle. */
export type EnabledModelsSubmitStatus = "idle" | "submitting" | "done";

/** Wire body of `POST /api/admin/llm-servers/{id}/models` — the complete set, never a delta. */
export type EnabledModelsPayload = { model_names: string[] };

/** Wire response of `POST /api/admin/llm-servers/{id}/models`. */
export type EnabledModelsResponse = { enabled_model_names: string[] };

export class EnabledModelsDraft {
  /** The current selection (the complete set a save posts). */
  selected: string[];
  /** The row's enabled names as loaded from the page's list payload — the baseline. */
  loaded: string[];
  serverErrors: EnabledModelsServerErrors = {};
  submitStatus: EnabledModelsSubmitStatus = "idle";

  /** Seeded from the row's `enabled_model_names`, never from the probe. Both arrays are copies. */
  constructor(enabledModelNames: readonly string[]) {
    this.selected = [...enabledModelNames];
    this.loaded = [...enabledModelNames];
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/** Pure: whether `selected` differs (as a set) from `loaded`. */
export function enabledModelsChanged(draft: EnabledModelsDraft): boolean {
  const selected = new Set(draft.selected);
  const loaded = new Set(draft.loaded);
  if (selected.size !== loaded.size) {
    return true;
  }
  for (const name of selected) {
    if (!loaded.has(name)) {
      return true;
    }
  }
  return false;
}

/** Pure: true when no submit is in flight. An empty selection is submittable. */
export function canSubmitEnabledModels(draft: EnabledModelsDraft): boolean {
  return draft.submitStatus !== "submitting";
}

const SERVERS_PATH = "/api/admin/llm-servers";
const NOT_FOUND_STATUS = 404;

const GENERIC_FAILURE = "The enabled models could not be saved.";
const NOT_FOUND_FAILURE = "This connection no longer exists. Close the dialog to refresh the list.";
const TRANSPORT_FAILURE = "The server could not be reached. Check that it is running and try again.";

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/** Maps a failure onto the general key by status or code only; never by parsing prose. */
function serverErrorsFor(error: unknown): EnabledModelsServerErrors {
  if (error instanceof ApiError) {
    if (error.status === NOT_FOUND_STATUS) {
      return { general: NOT_FOUND_FAILURE };
    }
    if (error.code === CLIENT_TRANSPORT_FAILED) {
      return { general: TRANSPORT_FAILURE };
    }
    if (error.message.length > 0) {
      return { general: error.message };
    }
  }
  return { general: GENERIC_FAILURE };
}

/**
 * `POST /api/admin/llm-servers/{serverId}/models` with `{ model_names: draft.selected }`
 * (the complete set). Maps failures by status or code (never message text) onto
 * `draft.serverErrors.general`, leaving `selected` untouched; on success sets
 * `submitStatus` to `"done"` and invokes `onSaved` once. `runInAction`s its writes;
 * early-returns on an aborted signal before writing. Does not reject.
 */
export async function submitEnabledModels(
  draft: EnabledModelsDraft,
  serverId: string,
  onSaved: () => void,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted || draft.submitStatus === "submitting") {
    return;
  }

  const body: EnabledModelsPayload = { model_names: [...draft.selected] };

  runInAction(() => {
    draft.submitStatus = "submitting";
    draft.serverErrors = {};
  });

  try {
    await apiPost<EnabledModelsResponse | undefined>(
      `${SERVERS_PATH}/${encodeURIComponent(serverId)}/models`,
      body,
      signal,
    );
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    const serverErrors = serverErrorsFor(error);
    runInAction(() => {
      draft.serverErrors = serverErrors;
      draft.submitStatus = "idle";
    });
    return;
  }

  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    draft.submitStatus = "done";
  });
  onSaved();
}
