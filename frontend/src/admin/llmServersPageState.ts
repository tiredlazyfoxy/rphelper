// The LLM Servers page's data: observable fields only, no methods, no computed getters.
// Loads, mutations and the last-test badge derivation are the free functions below.
import { makeAutoObservable, runInAction } from "mobx";
import type { MantineColor } from "@mantine/core";
import { apiDelete, apiGet, apiPost } from "../shared/api";

/** The two registration kinds the backend accepts. */
export type LlmServerKind = "llamaswap" | "openai";

/** The closed probe taxonomy — the backend's `ProbeOutcome` values, never widened to `string`. */
export type ProbeOutcome = "reachable" | "unreachable" | "auth_failed" | "model_list_empty";

/** One registration, exactly as `GET /api/admin/llm-servers` sends it. `id` is a decimal string, never parsed. */
export type LlmServerRow = {
  id: string;
  name: string;
  kind: LlmServerKind;
  base_url: string;
  has_api_key: boolean;
  enabled_model_names: string[];
  embedding_model_name: string | null;
  embedding_dim: number | null;
  last_test_at: string | null;       // UTC ISO-8601, or null when never tested
  last_test_ok: boolean | null;
  last_test_error: ProbeOutcome | null;
  created_at: string;                // UTC ISO-8601
  updated_at: string;                // UTC ISO-8601
};

/** The list route's body: `{ servers: [...] }`. */
export type LlmServerListResponse = {
  servers: LlmServerRow[];
};

/** `POST /api/admin/llm-servers/{id}/test`'s body. */
export type ConnectionTestResponse = {
  outcome: ProbeOutcome;
  ok: boolean;
  tested_at: string;                 // UTC ISO-8601
};

/** Explicit load status: gates the Loader, not "rows are empty". */
export type LlmServersLoadStatus = "idle" | "loading" | "ready";

/** The last-test badge's rendering, derived by `lastTestBadgeOf`. */
export type LastTestBadge = {
  label: string;
  color: MantineColor;
};

export class LlmServersPageState {
  rows: LlmServerRow[] = [];
  status: LlmServersLoadStatus = "idle";
  errorMessage: string | null = null;
  /** The id of the row whose connection test is in flight, or null. */
  testingId: string | null = null;

  constructor() {
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

const LIST_PATH = "/api/admin/llm-servers";

function serverPath(id: string): string {
  return `${LIST_PATH}/${encodeURIComponent(id)}`;
}

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function failureMessageOf(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }
  return fallback;
}

/**
 * `GET /api/admin/llm-servers`; writes `rows` and `status` (idle → loading → ready) in
 * `runInAction`. Returns without writing when `signal` is aborted. A failure sets
 * `errorMessage`. Does not reject.
 */
export async function loadLlmServers(state: LlmServersPageState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  if (state.status !== "ready") {
    runInAction(() => {
      state.status = "loading";
    });
  }

  let body: LlmServerListResponse | undefined;
  try {
    body = await apiGet<LlmServerListResponse | undefined>(LIST_PATH, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    const message = failureMessageOf(error, "The LLM server list could not be loaded.");
    runInAction(() => {
      state.status = "ready";
      state.errorMessage = message;
    });
    return;
  }

  if (signal?.aborted) {
    return;
  }
  const rows = body?.servers ?? [];
  runInAction(() => {
    state.rows = rows;
    state.status = "ready";
    state.errorMessage = null;
  });
}

/**
 * `DELETE /api/admin/llm-servers/{id}`, then re-loads the list (never optimistic).
 * A failure sets `errorMessage` and leaves the rows as they were. Does not reject.
 */
export async function deleteLlmServer(
  state: LlmServersPageState,
  id: string,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  try {
    await apiDelete<unknown>(serverPath(id), signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    const message = failureMessageOf(error, "The LLM server could not be deleted.");
    runInAction(() => {
      state.errorMessage = message;
    });
    return;
  }
  await loadLlmServers(state, signal);
}

/**
 * Sets `testingId`, `POST /api/admin/llm-servers/{id}/test`, then re-loads the list so the
 * badge shows what the server stored. A failure (transport or typed error, e.g.
 * `secret_ref_missing`) sets `errorMessage`. Clears `testingId` either way. Does not reject.
 */
export async function testLlmServerConnection(
  state: LlmServersPageState,
  id: string,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    state.testingId = id;
  });

  try {
    await apiPost<ConnectionTestResponse | undefined>(`${serverPath(id)}/test`, undefined, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    const message = failureMessageOf(error, "The connection test could not be run.");
    runInAction(() => {
      state.errorMessage = message;
      if (state.testingId === id) {
        state.testingId = null;
      }
    });
    return;
  }

  await loadLlmServers(state, signal);
  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    if (state.testingId === id) {
      state.testingId = null;
    }
  });
}

/**
 * Pure: the last-test badge's label and colour from the row's ok flag and typed outcome
 * (a "never tested" rendering when `last_test_at` is null). Parses no message text.
 */
export function lastTestBadgeOf(
  row: Pick<LlmServerRow, "last_test_at" | "last_test_ok" | "last_test_error">,
): LastTestBadge {
  if (row.last_test_at === null) {
    return { label: "Never tested", color: "gray" };
  }
  const outcome: ProbeOutcome | null =
    row.last_test_error ?? (row.last_test_ok === true ? "reachable" : null);
  switch (outcome) {
    case "reachable":
      return { label: "Reachable", color: "green" };
    case "unreachable":
      return { label: "Unreachable", color: "red" };
    case "auth_failed":
      return { label: "Auth failed", color: "orange" };
    case "model_list_empty":
      return { label: "No models listed", color: "yellow" };
    default:
      return { label: "Test failed", color: "red" };
  }
}
