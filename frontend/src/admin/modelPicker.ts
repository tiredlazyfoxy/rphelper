// The probe-on-open picker shared by the enabled-models modal (step 008) and the embedding
// modal (step 009): a data class (observable fields only, no methods, no computed getters)
// plus free functions over it (context.md D11 / D16).
import { makeAutoObservable, runInAction } from "mobx";
import { apiGet } from "../shared/api";

/** The explicit probe lifecycle; a `Loader` is gated on `"loading"`, never on an empty list. */
export type ModelProbeStatus = "idle" | "loading" | "ready" | "failed";

/** Wire body of `GET /api/admin/llm-servers/{id}/available-models`. */
export type AvailableModelsResponse = { model_names: string[] };

/** One row of the rendered option list: a model name and whether the server offers it now. */
export type ModelOption = { name: string; offered: boolean };

export class ModelPicker {
  /** What the server offers, as last probed. Emptied on a failed probe. */
  available: string[] = [];
  status: ModelProbeStatus = "idle";
  /** The failed probe's `ApiError.message`; `null` unless `status` is `"failed"`. */
  errorMessage: string | null = null;

  constructor() {
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/**
 * `GET /api/admin/llm-servers/{serverId}/available-models`. Sets `status` to `"loading"`,
 * then on success `available` = the response's names and `status` = `"ready"`; on failure
 * `status` = `"failed"`, `errorMessage` = the error's message, `available` = `[]` — and
 * touches nothing else. `runInAction`s its writes; early-returns on an aborted signal
 * before writing. Does not reject.
 */
export async function loadAvailableModels(
  picker: ModelPicker,
  serverId: string,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    picker.status = "loading";
    picker.errorMessage = null;
  });

  let body: AvailableModelsResponse | undefined;
  try {
    body = await apiGet<AvailableModelsResponse | undefined>(
      `${SERVERS_PATH}/${encodeURIComponent(serverId)}/available-models`,
      signal,
    );
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    const message = failureMessageOf(error);
    runInAction(() => {
      picker.status = "failed";
      picker.errorMessage = message;
      picker.available = [];
    });
    return;
  }

  if (signal?.aborted) {
    return;
  }
  const names = body?.model_names ?? [];
  runInAction(() => {
    picker.available = [...names];
    picker.status = "ready";
    picker.errorMessage = null;
  });
}

const SERVERS_PATH = "/api/admin/llm-servers";
const PROBE_FAILURE = "The server's models could not be listed.";

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function failureMessageOf(error: unknown): string {
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }
  return PROBE_FAILURE;
}

/**
 * Pure: `available ∪ enabled`, deduplicated, sorted into a stable order, each entry marked
 * `offered` iff it is in `available`. No render, no store, no network.
 */
export function modelOptionsOf(
  available: readonly string[],
  enabled: readonly string[],
): ModelOption[] {
  const offered = new Set(available);
  const names = Array.from(new Set([...available, ...enabled]));
  names.sort(compareNames);
  return names.map((name) => ({ name, offered: offered.has(name) }));
}

function compareNames(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}
