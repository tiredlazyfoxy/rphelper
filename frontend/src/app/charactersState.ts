// The one workspace characters list (feature 009, step 004, D11): observable fields only,
// no methods and no computed getters. The load effect and the upsert rule are the free
// functions below, each taking the state as its first argument.
import { makeAutoObservable, runInAction } from "mobx";

import type { Character } from "./charactersApi";
import { fetchCharacters, isArchived } from "./charactersApi";

/** Explicit load status: gates the loading and failure renders, not "rows are empty". */
export type CharactersLoadStatus = "idle" | "loading" | "ready" | "failed";

export class CharactersState {
  characters: Character[] = [];
  status: CharactersLoadStatus = "idle";
  /** Show-archived is session-only state, never persisted (D4). */
  showArchived = false;

  constructor() {
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/** Whether this row belongs in the list: working, or archived while Show-archived is on. */
function isVisible(character: Character, showArchived: boolean): boolean {
  return !isArchived(character) || showArchived;
}

/**
 * Effect: load the listing with `includeArchived` equal to `state.showArchived`.
 * Never rejects; writes nothing once aborted.
 */
export async function loadCharacters(state: CharactersState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  const includeArchived = state.showArchived;
  runInAction(() => {
    state.status = "loading";
  });

  let characters: Character[];
  try {
    characters = await fetchCharacters(includeArchived, signal);
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
    state.characters = characters;
    state.status = "ready";
  });
}

/** Effect: set the Show-archived flag. Issues no request. */
export function setShowArchived(state: CharactersState, showArchived: boolean): void {
  runInAction(() => {
    state.showArchived = showArchived;
  });
}

/** Upsert one server-returned character into the list per D11's rule. */
export function applyCharacter(state: CharactersState, character: Character): void {
  runInAction(() => {
    const visible = isVisible(character, state.showArchived);
    const index = state.characters.findIndex((row) => row.id === character.id);

    if (index >= 0) {
      if (!visible) {
        // Archived while Show-archived is off: it leaves the list.
        state.characters = state.characters.filter((row) => row.id !== character.id);
        return;
      }
      // Present and still visible: replaced in place, position unchanged.
      const next = state.characters.slice();
      next[index] = character;
      state.characters = next;
      return;
    }

    if (!visible) {
      // Absent and not visible: nothing to insert.
      return;
    }

    // Absent and visible: insert at its `created_at`-descending position — before the
    // first row older than it, or at the end. Fixed-width timestamps compare as text.
    const next = state.characters.slice();
    const at = next.findIndex((row) => row.created_at < character.created_at);
    if (at < 0) {
      next.push(character);
    } else {
      next.splice(at, 0, character);
    }
    state.characters = next;
  });
}
