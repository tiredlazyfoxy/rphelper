// The character configuration block's state (feature 018, step 006): the
// `CharacterConfigState` data class — observable fields only, no methods and no computed
// getters — and the free functions that load the character's own configuration and the
// enabled models, save one key at a time (never optimistic, failures inline, no
// notification), commit the system prompt draft, and derive each control's choices and
// resolved-value line (D9).
import { makeAutoObservable, runInAction } from "mobx";

import { isApiError } from "../shared/apiError";

import type {
  CharacterConfiguration,
  EnabledModel,
  ModelRef,
} from "./configurationApi";
import {
  fetchCharacterConfiguration,
  fetchEnabledModels,
  updateCharacterConfiguration,
} from "./configurationApi";

/** Explicit load status of one of the two independent reads. */
export type CharacterConfigStatus = "idle" | "loading" | "ready" | "failed";

/** One of the five configuration keys. */
export type CharacterConfigKey = keyof CharacterConfiguration;

/** One of the three tool keys. */
export type CharacterToolKey = "tool_memo_search" | "tool_session_search" | "tool_web_search";

/** A one-key patch: exactly one configuration key with its value (or null to clear). */
export type CharacterConfigKeyPatch = {
  [K in CharacterConfigKey]: Pick<CharacterConfiguration, K>;
}[CharacterConfigKey];

/** A tool control's choice. */
export type ToolChoice = "Default" | "On" | "Off";

/** One option of the model control. */
export type ModelChoice = {
  /** The option's opaque value (`UNSET_MODEL_VALUE` for "First enabled model"). */
  value: string;
  /** The option's label, exactly as the UI strings table states it. */
  label: string;
  /** True only for the configured-but-not-enabled model's option. */
  disabled: boolean;
  /** The model the option stands for; null for the unset option. */
  model: ModelRef | null;
};

/** The model control's unset value ("First enabled model"). */
export const UNSET_MODEL_VALUE = "__first_enabled_model__";

export class CharacterConfigState {
  readonly characterId: string;
  /** The character's own configuration, or null before the first successful load. */
  configuration: CharacterConfiguration | null = null;
  configStatus: CharacterConfigStatus = "idle";
  /** The enabled models, in server order. */
  models: EnabledModel[] = [];
  modelsStatus: CharacterConfigStatus = "idle";
  /** The system prompt text being edited. */
  promptDraft: string = "";
  /** The key whose save is in flight, or null. */
  savingKey: CharacterConfigKey | null = null;
  /** The save failure sentence, or null. */
  failure: string | null = null;

  constructor(characterId: string) {
    this.characterId = characterId;
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/** The fixed sentences (the UI strings table). */
const MODEL_NOT_ENABLED_FAILURE = "That model is no longer enabled.";
const SAVE_FAILED = "Could not save the configuration.";
const FIRST_ENABLED_MODEL_LABEL = "First enabled model";
const MODEL_NOT_SET_LINE = "Not set: new sessions take the first enabled model.";
const PROMPT_NOT_SET_LINE = "Not set: no system prompt.";
const SET_HERE_LINE = "Set on this character.";
const TOOL_DEFAULT_LINE = "On (default)";
const TOOL_ON_LINE = "On (set on this character)";
const TOOL_OFF_LINE = "Off (set on this character)";

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/** Equal when `server_id` and `model_name` are both equal as strings. */
function sameModel(a: ModelRef, b: ModelRef): boolean {
  return String(a.server_id) === String(b.server_id) && String(a.model_name) === String(b.model_name);
}

/** A model's opaque choice value, distinct per `server_id` + `model_name`. */
function modelValue(model: ModelRef): string {
  return JSON.stringify([String(model.server_id), String(model.model_name)]);
}

/** Reads the configuration under its own status and seeds the prompt draft; never rejects. */
async function loadConfiguration(state: CharacterConfigState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    state.configStatus = "loading";
  });

  let configuration: CharacterConfiguration;
  try {
    configuration = await fetchCharacterConfiguration(state.characterId, signal);
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
    state.promptDraft = configuration.system_prompt ?? "";
    state.configStatus = "ready";
  });
}

/** Reads the enabled models under their own status; never rejects. */
async function loadModels(state: CharacterConfigState, signal?: AbortSignal): Promise<void> {
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
 * Requests the configuration and the enabled models; each sets its own status (loading
 * first). Seeds the prompt draft from the configuration. Writes nothing once aborted; never
 * rejects.
 */
export async function loadCharacterConfig(
  state: CharacterConfigState,
  signal?: AbortSignal,
): Promise<void> {
  await Promise.all([loadConfiguration(state, signal), loadModels(state, signal)]);
}

/**
 * PATCHes exactly the one key, unless a save is in flight. Never optimistic; failures set a
 * fixed sentence (a 409 `model_not_enabled` re-requests the models); never rejects.
 */
export async function saveCharacterConfig(
  state: CharacterConfigState,
  patch: CharacterConfigKeyPatch,
): Promise<void> {
  if (state.savingKey !== null) {
    return;
  }
  const key = Object.keys(patch)[0] as CharacterConfigKey | undefined;
  if (key === undefined) {
    return;
  }
  runInAction(() => {
    state.failure = null;
    state.savingKey = key;
  });

  let configuration: CharacterConfiguration;
  try {
    configuration = await updateCharacterConfiguration(state.characterId, patch);
  } catch (error) {
    const notEnabled = isApiError(error) && error.code === "model_not_enabled";
    runInAction(() => {
      state.failure = notEnabled ? MODEL_NOT_ENABLED_FAILURE : SAVE_FAILED;
      state.savingKey = null;
    });
    if (notEnabled) {
      await loadModels(state);
    }
    return;
  }

  runInAction(() => {
    state.configuration = configuration;
    state.promptDraft = configuration.system_prompt ?? "";
    state.savingKey = null;
  });
}

/** Sets the system prompt draft (the prompt control's change handler). */
export function setPromptDraft(state: CharacterConfigState, text: string): void {
  runInAction(() => {
    state.promptDraft = text;
  });
}

/**
 * Saves `system_prompt` when the draft differs from the held prompt (null read as `""`):
 * verbatim, or null when blank. Otherwise sends nothing. Never rejects.
 */
export async function commitPromptDraft(state: CharacterConfigState): Promise<void> {
  const draft = state.promptDraft;
  const held = state.configuration?.system_prompt ?? "";
  if (draft === held) {
    return;
  }
  await saveCharacterConfig(state, { system_prompt: draft.trim() === "" ? null : draft });
}

/**
 * Pure: "First enabled model", then each enabled model in served order, then — when the
 * configured model is not among them — its disabled "(not enabled)" choice.
 */
export function modelChoices(state: CharacterConfigState): ModelChoice[] {
  const choices: ModelChoice[] = [
    { value: UNSET_MODEL_VALUE, label: FIRST_ENABLED_MODEL_LABEL, disabled: false, model: null },
  ];
  for (const enabled of state.models) {
    const model: ModelRef = { server_id: enabled.server_id, model_name: enabled.model_name };
    choices.push({
      value: modelValue(model),
      label: `${enabled.model_name} (${enabled.server_name})`,
      disabled: false,
      model,
    });
  }
  const configured = state.configuration?.model ?? null;
  if (configured !== null && !state.models.some((enabled) => sameModel(enabled, configured))) {
    choices.push({
      value: modelValue(configured),
      label: `${configured.model_name} (not enabled)`,
      disabled: true,
      model: { server_id: configured.server_id, model_name: configured.model_name },
    });
  }
  return choices;
}

/** Pure: the selected choice's value — the configured model's, or `UNSET_MODEL_VALUE`. */
export function selectedModelValue(state: CharacterConfigState): string {
  const configured = state.configuration?.model ?? null;
  return configured === null ? UNSET_MODEL_VALUE : modelValue(configured);
}

/** Pure: the model's resolved-value line. */
export function modelLine(configuration: CharacterConfiguration): string {
  return configuration.model === null ? MODEL_NOT_SET_LINE : SET_HERE_LINE;
}

/** Pure: the system prompt's resolved-value line (from the held prompt, not the draft). */
export function promptLine(configuration: CharacterConfiguration): string {
  return configuration.system_prompt === null ? PROMPT_NOT_SET_LINE : SET_HERE_LINE;
}

/** Pure: a tool's resolved-value line from its held value. */
export function toolLine(value: boolean | null): string {
  if (value === null) {
    return TOOL_DEFAULT_LINE;
  }
  return value ? TOOL_ON_LINE : TOOL_OFF_LINE;
}

/** Pure: Default / On / Off from null / true / false. */
export function toolChoice(value: boolean | null): ToolChoice {
  if (value === null) {
    return "Default";
  }
  return value ? "On" : "Off";
}

/** Pure: the patch value for a choice — Default → null, On → true, Off → false. */
export function toolPatchValue(choice: ToolChoice): boolean | null {
  switch (choice) {
    case "Default":
      return null;
    case "On":
      return true;
    case "Off":
      return false;
  }
}
