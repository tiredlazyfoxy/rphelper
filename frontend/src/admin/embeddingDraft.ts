// The embedding modal's draft (single-select): a data class (observable fields only, no
// methods, no computed getters) plus free functions over it (context.md D2 / D4 / D11 / D16 /
// D17 / D18). The probe, the union and failed-probe behaviour come from `./modelPicker`.
import { makeAutoObservable, runInAction } from "mobx";
import { apiDelete, apiPost } from "../shared/api";
import { ApiError, CLIENT_TRANSPORT_FAILED } from "../shared/apiError";
import { type LlmServerRow, type LlmServersPageState, loadLlmServers } from "./llmServersPageState";

/** Keys of the server-error map: only the general catch-all. */
export type EmbeddingServerErrorKey = "general";

/** Status- or code-keyed server errors; everything lands on `general`. */
export type EmbeddingServerErrors = Partial<Record<EmbeddingServerErrorKey, string>>;

/** Submit lifecycle. */
export type EmbeddingSubmitStatus = "idle" | "submitting" | "done";

/** Wire body of `POST /api/admin/llm-servers/{id}/embedding-model`. */
export type DesignateEmbeddingPayload = { model_name: string };

/** Wire response of `POST /api/admin/llm-servers/{id}/embedding-model` (the designating row). */
export type DesignateEmbeddingResponse = LlmServerRow;

export class EmbeddingDraft {
  /** The single chosen model name, or `null` when nothing is chosen. */
  selected: string | null;
  /** The server's currently designated model, from the page's list payload (survives a failed probe). */
  designated: string | null;
  serverErrors: EmbeddingServerErrors = {};
  submitStatus: EmbeddingSubmitStatus = "idle";

  /** Seeded from the row's `embedding_model_name`; `selected` starts as that name (preselection). */
  constructor(designatedModelName: string | null) {
    this.selected = designatedModelName;
    this.designated = designatedModelName;
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/** Pure: true when a model is selected and no submit is in flight. */
export function canSubmitEmbedding(draft: EmbeddingDraft): boolean {
  return draft.selected !== null && draft.selected.length > 0 && draft.submitStatus !== "submitting";
}

const SERVERS_PATH = "/api/admin/llm-servers";
const NOT_FOUND_STATUS = 404;
const BAD_GATEWAY_STATUS = 502;
const LLM_UNREACHABLE = "llm_unreachable";

const GENERIC_FAILURE = "The embedding model could not be designated.";
const NOT_FOUND_FAILURE = "This connection no longer exists. Close the dialog to refresh the list.";
const TRANSPORT_FAILURE = "The server could not be reached. Check that it is running and try again.";
const REFUSED_FAILURE =
  "The server did not return an embedding for this model, so it was not designated. " +
  "Choose a model that can produce embeddings, or check that the server is reachable.";
const CLEAR_FAILURE = "The embedding designation could not be cleared.";

function embeddingPath(serverId: string): string {
  return `${SERVERS_PATH}/${encodeURIComponent(serverId)}/embedding-model`;
}

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/** Maps a failure onto the general key by status or code only; never by parsing prose. */
function serverErrorsFor(error: unknown): EmbeddingServerErrors {
  if (error instanceof ApiError) {
    if (error.status === NOT_FOUND_STATUS) {
      return { general: NOT_FOUND_FAILURE };
    }
    if (error.code === CLIENT_TRANSPORT_FAILED) {
      return { general: TRANSPORT_FAILURE };
    }
    if (error.code === LLM_UNREACHABLE || error.status === BAD_GATEWAY_STATUS) {
      return { general: error.message.trim().length > 0 ? error.message : REFUSED_FAILURE };
    }
    if (error.message.length > 0) {
      return { general: error.message };
    }
  }
  return { general: GENERIC_FAILURE };
}

/**
 * `POST /api/admin/llm-servers/{serverId}/embedding-model` with `{ model_name: draft.selected }`.
 * Maps failures by status or code (never message text; the 502 `llm_unreachable` refusal is the
 * case that matters) onto `draft.serverErrors.general`; on success sets `submitStatus` to
 * `"done"` and invokes `onSaved` once. `runInAction`s its writes; early-returns on an aborted
 * signal before writing. Does not reject.
 */
export async function submitEmbeddingDesignation(
  draft: EmbeddingDraft,
  serverId: string,
  onSaved: () => void,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted || !canSubmitEmbedding(draft) || draft.selected === null) {
    return;
  }

  const body: DesignateEmbeddingPayload = { model_name: draft.selected };

  runInAction(() => {
    draft.submitStatus = "submitting";
    draft.serverErrors = {};
  });

  try {
    await apiPost<DesignateEmbeddingResponse | undefined>(embeddingPath(serverId), body, signal);
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

/**
 * `DELETE /api/admin/llm-servers/{serverId}/embedding-model` (204), then `loadLlmServers(state)`.
 * A failure lands in `state.errorMessage` (the page-level `Alert`), never in a draft.
 * `runInAction`s its writes; early-returns on an aborted signal before writing. Does not reject.
 */
export async function clearEmbeddingDesignation(
  state: LlmServersPageState,
  serverId: string,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  try {
    await apiDelete<unknown>(embeddingPath(serverId), signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    const message =
      error instanceof Error && error.message.trim().length > 0 ? error.message : CLEAR_FAILURE;
    runInAction(() => {
      state.errorMessage = message;
    });
    return;
  }
  await loadLlmServers(state, signal);
}
