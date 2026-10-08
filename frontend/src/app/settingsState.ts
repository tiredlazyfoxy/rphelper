// The settings screen's languages form (feature 017, step 007): the `SettingsState` data
// class — observable fields only, no methods and no computed getters — and the free
// functions that load the user's settings, track the two editor texts, derive dirtiness and
// save only the changed keys with a fixed-sentence failure (D6, D19).
import { makeAutoObservable, runInAction } from "mobx";

import type { UserSettings, UserSettingsPatch } from "./configurationApi";
import { fetchUserSettings, updateUserSettings } from "./configurationApi";

/** Explicit load status of the languages form. */
export type SettingsStatus = "idle" | "loading" | "ready" | "failed";

/** Whether a save is in flight. */
export type SettingsSaveStatus = "idle" | "saving";

export class SettingsState {
  status: SettingsStatus = "idle";
  /** The server's last answer, or null before the first successful load. */
  saved: UserSettings | null = null;
  /** The RP language editor text. */
  rpLanguage: string = "";
  /** The preferred language editor text. */
  preferredLanguage: string = "";
  saveStatus: SettingsSaveStatus = "idle";
  /** The save failure sentence, or null. */
  saveFailure: string | null = null;

  constructor() {
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/** The fixed save-failure sentence (the UI strings table). */
const SAVE_FAILED = "Could not save your settings.";

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/** An editor text as the wire value: trimmed, blank as null. */
function wireValue(text: string): string | null {
  const trimmed = text.trim();
  return trimmed === "" ? null : trimmed;
}

/** Writes the server's answer into `saved` and both editor texts (null as ""). */
function applySaved(state: SettingsState, settings: UserSettings): void {
  state.saved = settings;
  state.rpLanguage = settings.rp_language ?? "";
  state.preferredLanguage = settings.preferred_language ?? "";
}

/** The changed keys only (D6): each editor text against `saved`, trimmed, blank as null. */
function patchOf(state: SettingsState): UserSettingsPatch {
  const saved = state.saved;
  const patch: UserSettingsPatch = {};
  const rpLanguage = wireValue(state.rpLanguage);
  const preferredLanguage = wireValue(state.preferredLanguage);
  if (rpLanguage !== (saved?.rp_language ?? null)) {
    patch.rp_language = rpLanguage;
  }
  if (preferredLanguage !== (saved?.preferred_language ?? null)) {
    patch.preferred_language = preferredLanguage;
  }
  return patch;
}

/** Loads the user's settings into the state; writes nothing once aborted; never rejects. */
export async function loadSettings(state: SettingsState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    state.status = "loading";
  });

  let settings: UserSettings;
  try {
    settings = await fetchUserSettings(signal);
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
    applySaved(state, settings);
    state.status = "ready";
  });
}

/** Writes the RP language editor text. */
export function setRpLanguage(state: SettingsState, text: string): void {
  runInAction(() => {
    state.rpLanguage = text;
  });
}

/** Writes the preferred language editor text. */
export function setPreferredLanguage(state: SettingsState, text: string): void {
  runInAction(() => {
    state.preferredLanguage = text;
  });
}

/** Pure: either editor text (trimmed, blank as null) differs from `saved`. */
export function isDirty(state: SettingsState): boolean {
  return Object.keys(patchOf(state)).length > 0;
}

/** Pure: ready, dirty and not saving. */
export function canSave(state: SettingsState): boolean {
  return state.status === "ready" && state.saveStatus !== "saving" && isDirty(state);
}

/** Sends only the changed keys; on failure sets the fixed sentence; never rejects. */
export async function saveSettings(state: SettingsState): Promise<void> {
  const patch = patchOf(state);
  if (Object.keys(patch).length === 0) {
    return;
  }
  runInAction(() => {
    state.saveStatus = "saving";
  });

  let settings: UserSettings;
  try {
    settings = await updateUserSettings(patch);
  } catch {
    runInAction(() => {
      state.saveFailure = SAVE_FAILED;
      state.saveStatus = "idle";
    });
    return;
  }

  runInAction(() => {
    applySaved(state, settings);
    state.saveFailure = null;
    state.saveStatus = "idle";
  });
}
