// The session configuration state (feature 017, step 008): the `SessionConfigState` data
// class — observable fields only, no methods and no computed getters — shared by the
// session header bar and the composer's Send gate, and the free functions that load the
// session's resolved configuration and the enabled models in parallel, change the model
// through the picker (never optimistic, failures inline), and derive the model's usability
// and the Send gate's reason (D16, D17).
import { makeAutoObservable, runInAction } from "mobx";

import { isApiError } from "../shared/apiError";

import type { EnabledModel, ModelRef, SessionConfiguration } from "./configurationApi";
import {
  fetchEnabledModels,
  fetchSessionConfiguration,
  updateSessionConfiguration,
} from "./configurationApi";

/** Explicit load status of one of the two independent reads. */
export type SessionConfigStatus = "idle" | "loading" | "ready" | "failed";

/** Whether the session's captured model can be used, in D2's check order. */
export type ModelUsability = "unknown" | "no_model_enabled" | "not_chosen" | "not_enabled" | "usable";

export class SessionConfigState {
  readonly sessionId: string;
  /** The session's resolved configuration, or null before the first successful load. */
  configuration: SessionConfiguration | null = null;
  configStatus: SessionConfigStatus = "idle";
  modelsStatus: SessionConfigStatus = "idle";
  /** The enabled models, in server order. */
  models: EnabledModel[] = [];
  /** A model change is in flight. */
  modelSaving: boolean = false;
  /** The model change failure sentence, or null. */
  modelFailure: string | null = null;

  constructor(sessionId: string) {
    this.sessionId = sessionId;
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/** The fixed sentences (the UI strings table). */
const MODEL_NOT_ENABLED_FAILURE = "That model is no longer enabled.";
const MODEL_CHANGE_FAILED = "Could not change the model.";
const REASON_NO_MODEL_ENABLED = "Cannot send: no model is enabled on this instance.";
const REASON_NOT_CHOSEN = "Cannot send: choose a model for this session.";
const REASON_NOT_ENABLED = "Cannot send: this session's model is not enabled. Choose another model.";

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/** Reads the session configuration into the state under its own status; never rejects. */
async function loadConfiguration(state: SessionConfigState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    state.configStatus = "loading";
  });

  let configuration: SessionConfiguration;
  try {
    configuration = await fetchSessionConfiguration(state.sessionId, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    runInAction(() => {
      state.configStatus = "failed";
    });
    return;
  }

  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    state.configuration = configuration;
    state.configStatus = "ready";
  });
}

/** Reads the enabled models into the state under their own status; never rejects. */
async function loadModels(state: SessionConfigState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    state.modelsStatus = "loading";
  });

  let models: EnabledModel[];
  try {
    models = await fetchEnabledModels(signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    runInAction(() => {
      state.modelsStatus = "failed";
    });
    return;
  }

  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    state.models = models;
    state.modelsStatus = "ready";
  });
}

/**
 * Requests the session configuration and the enabled models in parallel; each sets its own
 * status. Writes nothing once aborted; never rejects.
 */
export async function loadSessionConfig(
  state: SessionConfigState,
  signal?: AbortSignal,
): Promise<void> {
  await Promise.all([loadConfiguration(state, signal), loadModels(state, signal)]);
}

/**
 * PATCHes `{ model }` unless the ref is the captured model or a change is in flight. Never
 * optimistic; failures set a fixed sentence; never rejects.
 */
export async function chooseModel(state: SessionConfigState, model: ModelRef): Promise<void> {
  if (state.modelSaving) {
    return;
  }
  const captured = state.configuration?.model ?? null;
  if (captured !== null && sameModel(captured, model)) {
    return;
  }
  runInAction(() => {
    state.modelSaving = true;
    state.modelFailure = null;
  });

  let configuration: SessionConfiguration;
  try {
    configuration = await updateSessionConfiguration(state.sessionId, {
      model: { server_id: model.server_id, model_name: model.model_name },
    });
  } catch (error) {
    const notEnabled = isApiError(error) && error.code === "model_not_enabled";
    runInAction(() => {
      state.modelFailure = notEnabled ? MODEL_NOT_ENABLED_FAILURE : MODEL_CHANGE_FAILED;
      state.modelSaving = false;
    });
    if (notEnabled) {
      await loadModels(state);
    }
    return;
  }

  runInAction(() => {
    state.configuration = configuration;
    state.modelSaving = false;
  });
}

/** Replaces `configuration` (the modal's save hands its response here). */
export function applySessionConfiguration(
  state: SessionConfigState,
  configuration: SessionConfiguration,
): void {
  runInAction(() => {
    state.configuration = configuration;
  });
}

/** Pure: equal when `server_id` and `model_name` are both equal as strings. */
export function sameModel(a: ModelRef, b: ModelRef): boolean {
  return String(a.server_id) === String(b.server_id) && String(a.model_name) === String(b.model_name);
}

/** Pure: the captured model's usability; `"unknown"` unless both reads are ready. */
export function modelUsability(state: SessionConfigState): ModelUsability {
  if (state.configStatus !== "ready" || state.modelsStatus !== "ready") {
    return "unknown";
  }
  if (state.models.length === 0) {
    return "no_model_enabled";
  }
  const captured = state.configuration?.model ?? null;
  if (captured === null) {
    return "not_chosen";
  }
  if (!state.models.some((listed) => sameModel(listed, captured))) {
    return "not_enabled";
  }
  return "usable";
}

/** Pure: the fixed gate sentence for a blocking usability; null for usable and unknown. */
export function sendBlockedReason(state: SessionConfigState): string | null {
  switch (modelUsability(state)) {
    case "no_model_enabled":
      return REASON_NO_MODEL_ENABLED;
    case "not_chosen":
      return REASON_NOT_CHOSEN;
    case "not_enabled":
      return REASON_NOT_ENABLED;
    case "usable":
    case "unknown":
      return null;
  }
}
