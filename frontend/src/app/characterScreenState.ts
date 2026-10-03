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
  /** The Name field's client-side error ("A character needs a name."), or null (018 D7). */
  nameError: string | null = null;
  /** Whether a name PATCH is in flight (018 D7) — independent of `submitStatus`. */
  nameSaving = false;
  /** Whether a persona (sheet) PATCH is in flight (018 D7) — independent of `submitStatus`. */
  personaSaving = false;

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

/** Pure: true while the mode is new and no character has been created yet (018 D6). */
export function isDraft(state: CharacterScreenState): boolean {
  return isNewCharacter(state) && state.character === null;
}

/** The client-side Name error: a blank name is refused before any request (018 D7). */
const NAME_REQUIRED = "A character needs a name.";

function isBlankName(name: string): boolean {
  return name.trim().length === 0;
}

/**
 * Effect (018 D7): existing character only. A trimmed-blank name sets `nameError` and
 * sends nothing; otherwise clears it and PATCHes `{ name }` unless unchanged or a name
 * save is in flight. Takes no signal and never rejects.
 */
export async function commitName(
  state: CharacterScreenState,
  characters: CharactersState,
): Promise<void> {
  const held = state.character;
  if (isDraft(state) || held === null) {
    return;
  }
  if (isBlankName(state.name)) {
    runInAction(() => {
      state.nameError = NAME_REQUIRED;
    });
    return;
  }
  runInAction(() => {
    state.nameError = null;
  });
  if (state.name === held.name || state.nameSaving) {
    return;
  }

  const sent = state.name;
  runInAction(() => {
    state.nameSaving = true;
    state.error = null;
  });
  let saved: Character;
  try {
    saved = await updateCharacter(held.id, { name: sent });
  } catch {
    runInAction(() => {
      state.error = SAVE_FAILED;
    });
    return;
  } finally {
    runInAction(() => {
      state.nameSaving = false;
    });
  }

  applyFieldSave(state, characters, saved, () => {
    if (state.name === sent) {
      state.name = saved.name;
    }
  });
}

/**
 * Effect (018 D7): existing character only. PATCHes `{ sheet }` unless unchanged or a
 * persona save is in flight. Takes no signal and never rejects.
 */
export async function commitPersona(
  state: CharacterScreenState,
  characters: CharactersState,
): Promise<void> {
  const held = state.character;
  if (isDraft(state) || held === null) {
    return;
  }
  if (state.sheet === held.sheet || state.personaSaving) {
    return;
  }

  const sent = state.sheet;
  runInAction(() => {
    state.personaSaving = true;
    state.error = null;
  });
  let saved: Character;
  try {
    saved = await updateCharacter(held.id, { sheet: sent });
  } catch {
    runInAction(() => {
      state.error = SAVE_FAILED;
    });
    return;
  } finally {
    runInAction(() => {
      state.personaSaving = false;
    });
  }

  applyFieldSave(state, characters, saved, () => {
    if (state.sheet === sent) {
      state.sheet = saved.sheet;
    }
  });
}

/**
 * The shared success tail of the two commits: the row goes to the workspace list; it
 * replaces `character` only when its `updated_at` is not older than the held one's (a
 * fixed-width text compare, 015 D5); `adoptDraft` touches the committed field alone.
 */
function applyFieldSave(
  state: CharacterScreenState,
  characters: CharactersState,
  saved: Character,
  adoptDraft: () => void,
): void {
  runInAction(() => {
    const held = state.character;
    if (held === null || saved.updated_at >= held.updated_at) {
      state.character = saved;
    }
    adoptDraft();
  });
  applyCharacter(characters, saved);
}

/**
 * Effect (018 D7, R10): saves pending edits when the screen goes away. A draft with a
 * non-blank name runs `submitCreate` with a no-op `onCreated`; an existing character runs
 * the name commit (unless blank) and the persona commit. Never rejects.
 */
export async function flushCharacterEdits(
  state: CharacterScreenState,
  characters: CharactersState,
): Promise<void> {
  if (isDraft(state)) {
    if (!isBlankName(state.name)) {
      await submitCreate(state, characters, () => {});
    }
    return;
  }
  const commits: Promise<void>[] = [];
  if (!isBlankName(state.name)) {
    commits.push(commitName(state, characters));
  }
  commits.push(commitPersona(state, characters));
  await Promise.all(commits);
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
  // Only a draft with a non-blank name creates, and never twice (018 D6).
  if (
    signal?.aborted ||
    !isDraft(state) ||
    isBlankName(state.name) ||
    state.submitStatus === "submitting"
  ) {
    return;
  }

  // The name goes as typed (the request model strips it server-side), the persona with it.
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

  // Holding the row ends the draft, so a later commit or flush creates nothing.
  runInAction(() => {
    state.character = created;
    state.name = created.name;
    state.sheet = created.sheet;
  });
  applyCharacter(characters, created);
  onCreated(created.id);
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
