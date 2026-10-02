// The character screen's state (feature 009, step 006): one data class holding the mode,
// the load status, the loaded character, the name/sheet draft, the submit status and the
// inline error — observable fields only, no methods and no computed getters. Every
// derivation and every effect is a free function below, each taking the state first.
// The module is React-free: navigation after a create is an `onCreated` callback (D1).
import { makeAutoObservable, runInAction } from "mobx";

import { isApiError } from "../shared/apiError";
import type { Character } from "./charactersApi";
import {
  archiveCharacter,
  createCharacter,
  fetchCharacter,
  restoreCharacter,
  updateCharacter,
} from "./charactersApi";
import type { CharactersState } from "./charactersState";
import { applyCharacter } from "./charactersState";

/** Explicit load status for the screen: gates the loading, 404 and failure renders. */
export type CharacterScreenStatus = "loading" | "ready" | "not-found" | "failed";

/** Whether a Create / Save / Archive / Restore submit is in flight. */
export type CharacterSubmitStatus = "idle" | "submitting";

export class CharacterScreenState {
  /** The character being edited, or null in new mode (`/characters/new`). Never parsed. */
  characterId: string | null;
  status: CharacterScreenStatus;
  /** The last server-returned row, or null before the first successful response. */
  character: Character | null = null;
  /** The draft the form edits; sent as typed, the server does the stripping. */
  name = "";
  sheet = "";
  submitStatus: CharacterSubmitStatus = "idle";
  /** The inline failure text the screen renders as given, or null (D12). */
  error: string | null = null;

  constructor(characterId: string | null) {
    this.characterId = characterId;
    this.status = characterId === null ? "ready" : "loading";
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/** The backend's code for "no such character of mine" — the only one the screen reads. */
const CHARACTER_NOT_FOUND = "character_not_found";

/** One fixed sentence per action: the screen never renders the backend's prose (D12). */
const CREATE_FAILED = "Could not create the character.";
const SAVE_FAILED = "Could not save the character.";
const ARCHIVE_FAILED = "Could not archive the character.";
const RESTORE_FAILED = "Could not restore the character.";

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/** Pure: true when the screen is in new mode (no character id). */
export function isNewCharacter(state: CharacterScreenState): boolean {
  return state.characterId === null;
}

/** Pure: true when a character is loaded and the draft name or sheet differs from it. */
export function isDirty(state: CharacterScreenState): boolean {
  const character = state.character;
  if (character === null) {
    return false;
  }
  return state.name !== character.name || state.sheet !== character.sheet;
}

/**
 * Pure: true when the trimmed draft name is non-empty, nothing is submitting, and the
 * mode is new or the draft is dirty. The trim decides "blank" only — the request still
 * carries the name as typed.
 */
export function canSubmit(state: CharacterScreenState): boolean {
  if (state.name.trim().length === 0) {
    return false;
  }
  if (state.submitStatus === "submitting") {
    return false;
  }
  return isNewCharacter(state) || isDirty(state);
}

/**
 * Effect: fetch `state.characterId` into the screen. Sets "loading" first, then "ready",
 * "not-found" (`character_not_found`) or "failed". Writes nothing once aborted; never rejects.
 */
export async function loadCharacter(
  state: CharacterScreenState,
  signal?: AbortSignal,
): Promise<void> {
  const characterId = state.characterId;
  if (signal?.aborted || characterId === null) {
    return;
  }

  // "loading" first, so a retry from a failed state shows loading again.
  runInAction(() => {
    state.status = "loading";
  });

  let character: Character;
  try {
    character = await fetchCharacter(characterId, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    const notFound = isApiError(error) && error.code === CHARACTER_NOT_FOUND;
    runInAction(() => {
      state.status = notFound ? "not-found" : "failed";
    });
    return;
  }

  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    state.character = character;
    state.name = character.name;
    state.sheet = character.sheet;
    state.status = "ready";
  });
}

/**
 * Effect: POST the draft, apply the created row to the workspace list and call
 * `onCreated` with its id (the caller navigates). Sets the inline error on failure,
 * returns to "idle" either way, and never rejects.
 */
export async function submitCreate(
  state: CharacterScreenState,
  characters: CharactersState,
  onCreated: (characterId: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted || state.submitStatus === "submitting") {
    return;
  }

  // The name goes as typed; the request model strips it server-side.
  const input = { name: state.name, sheet: state.sheet };

  runInAction(() => {
    state.submitStatus = "submitting";
    state.error = null;
  });

  let created: Character;
  try {
    created = await createCharacter(input, signal);
    if (signal?.aborted) {
      return;
    }
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    runInAction(() => {
      state.error = CREATE_FAILED;
    });
    return;
  } finally {
    if (!signal?.aborted) {
      runInAction(() => {
        state.submitStatus = "idle";
      });
    }
  }

  applyCharacter(characters, created);
  onCreated(created.id);
}

/**
 * Effect: PATCH `name` and `sheet` together (D2). On success the response replaces both
 * `character` and the draft and is applied to the workspace list; on failure the draft
 * and `character` are left as they were. Never optimistic, never rejects.
 */
export async function submitSave(
  state: CharacterScreenState,
  characters: CharactersState,
  signal?: AbortSignal,
): Promise<void> {
  const characterId = state.characterId;
  if (signal?.aborted || characterId === null || state.submitStatus === "submitting") {
    return;
  }

  const patch = { name: state.name, sheet: state.sheet };

  runInAction(() => {
    state.submitStatus = "submitting";
    state.error = null;
  });

  let saved: Character;
  try {
    saved = await updateCharacter(characterId, patch, signal);
    if (signal?.aborted) {
      return;
    }
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    runInAction(() => {
      state.error = SAVE_FAILED;
    });
    return;
  } finally {
    if (!signal?.aborted) {
      runInAction(() => {
        state.submitStatus = "idle";
      });
    }
  }

  // The server's stored values win: a trimmed name replaces the typed one.
  runInAction(() => {
    state.character = saved;
    state.name = saved.name;
    state.sheet = saved.sheet;
  });
  applyCharacter(characters, saved);
}

/**
 * Effect: POST the archive action. The response replaces `character` and is applied to
 * the workspace list; the draft is left untouched, so unsaved edits survive (D9).
 */
export async function submitArchive(
  state: CharacterScreenState,
  characters: CharactersState,
  signal?: AbortSignal,
): Promise<void> {
  await submitAction(state, characters, archiveCharacter, ARCHIVE_FAILED, signal);
}

/** Effect: POST the restore action. Same shape as `submitArchive`, draft untouched. */
export async function submitRestore(
  state: CharacterScreenState,
  characters: CharactersState,
  signal?: AbortSignal,
): Promise<void> {
  await submitAction(state, characters, restoreCharacter, RESTORE_FAILED, signal);
}

/**
 * The shared archive / restore body: both change only `archived_at` on the server, so the
 * response replaces `character` alone — replacing the draft would discard unsaved edits.
 */
async function submitAction(
  state: CharacterScreenState,
  characters: CharactersState,
  call: (characterId: string, signal?: AbortSignal) => Promise<Character>,
  failureText: string,
  signal?: AbortSignal,
): Promise<void> {
  const characterId = state.characterId;
  if (signal?.aborted || characterId === null || state.submitStatus === "submitting") {
    return;
  }

  runInAction(() => {
    state.submitStatus = "submitting";
    state.error = null;
  });

  let acted: Character;
  try {
    acted = await call(characterId, signal);
    if (signal?.aborted) {
      return;
    }
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    runInAction(() => {
      state.error = failureText;
    });
    return;
  } finally {
    if (!signal?.aborted) {
      runInAction(() => {
        state.submitStatus = "idle";
      });
    }
  }

  runInAction(() => {
    state.character = acted;
  });
  applyCharacter(characters, acted);
}
