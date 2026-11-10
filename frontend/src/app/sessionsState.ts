// The one workspace sessions list (feature 011, step 004, D15): the caller's working
// sessions across all characters, for the tree. Observable fields only — no methods and no
// computed getters; the load effect, the upsert and the two pure derivations are the free
// functions below, each taking its state or its lists as arguments.
// The workspace list is always the working list (D5), so there is no show-archived flag here.
// Ordering is the server's list order: fixed-width `last_used_at` text descending, then id
// descending compared numerically on the decimal strings (DEC-034-12).
import { makeAutoObservable, runInAction } from "mobx";

import type { Session } from "./sessionsApi";
import { fetchSessions, isSessionArchived } from "./sessionsApi";
import { isAbortError } from "../shared/abort";

/** Explicit load status: gates the loading and failure renders, not "rows are empty". */
export type SessionsLoadStatus = "idle" | "loading" | "ready" | "failed";

export class SessionsState {
  sessions: Session[] = [];
  status: SessionsLoadStatus = "idle";

  constructor() {
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/**
 * Effect: load the caller's working sessions across all characters, written in the order
 * received. Never rejects; writes nothing once aborted.
 */
export async function loadSessions(state: SessionsState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    state.status = "loading";
  });

  let sessions: Session[];
  try {
    // The workspace list is working-only (D5): the flag is never set from here.
    sessions = await fetchSessions(false, signal);
  } catch (error) {
    if (signal?.aborted || isAbortError(error)) {
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
    state.sessions = sessions;
    state.status = "ready";
  });
}

/**
 * Pure: compares two decimal-string ids numerically (negative, zero, positive). Ids are
 * snowflakes that may exceed 2^53, so they are never converted through `Number`; without
 * leading zeros a longer string is the larger number, and equal lengths compare as text.
 */
function compareIds(left: string, right: string): number {
  if (left.length !== right.length) {
    return left.length - right.length;
  }
  return left < right ? -1 : left > right ? 1 : 0;
}

/**
 * Upsert one server-returned session into the workspace list per D15's rule: removed by id,
 * dropped when archived, else inserted by `last_used_at` descending, ties by id descending
 * (DEC-034-12). Re-applying a row whose `last_used_at` is unchanged keeps its index.
 */
export function applySession(state: SessionsState, session: Session): void {
  runInAction(() => {
    // Removed first, then re-inserted: from `012` on a content write moves `last_used_at`
    // and the row must move with it.
    const next = state.sessions.filter((row) => row.id !== session.id);

    if (isSessionArchived(session)) {
      // Archived rows never belong to the workspace list: removed if present, never inserted.
      state.sessions = next;
      return;
    }

    // Insert before the first row that sorts after it in the server's order (`last_used_at`
    // DESC, id DESC — DEC-034-12), else at the end. Fixed-width timestamps compare as text;
    // ids compare numerically, so an equal-`last_used_at` row lands back at its old index.
    const at = next.findIndex(
      (row) =>
        row.last_used_at < session.last_used_at ||
        (row.last_used_at === session.last_used_at && compareIds(row.id, session.id) < 0),
    );
    if (at < 0) {
      next.push(session);
    } else {
      next.splice(at, 0, session);
    }
    state.sessions = next;
  });
}

/** Pure: that character's sessions, in the given order. */
export function sessionsOfCharacter(
  sessions: readonly Session[],
  characterId: string,
): Session[] {
  return sessions.filter((session) => session.character_id === characterId);
}

/**
 * Pure: the same characters, ordered by D6 — those with at least one session first, by the
 * greatest `last_used_at` among their sessions (most recent first), then those with none in
 * the given order. Ties keep the given order. Generic over "anything with an `id` string", so
 * this module never imports `charactersApi.ts`; the element type is returned unchanged.
 */
export function orderCharactersByUse<T extends { id: string }>(
  characters: readonly T[],
  sessions: readonly Session[],
): T[] {
  // The greatest `last_used_at` per character, as a text max.
  const newestUse = new Map<string, string>();
  for (const session of sessions) {
    const seen = newestUse.get(session.character_id);
    if (seen === undefined || seen < session.last_used_at) {
      newestUse.set(session.character_id, session.last_used_at);
    }
  }

  // Decorate with the given position, so every tie — and every character with no session —
  // keeps the given order whatever the engine's sort does. Neither input is mutated.
  const decorated = characters.map((character, position) => ({
    character,
    position,
    newest: newestUse.get(character.id),
  }));

  decorated.sort((left, right) => {
    if (left.newest === undefined || right.newest === undefined) {
      if (left.newest === right.newest) {
        return left.position - right.position;
      }
      // A character with no session sorts after every character with one.
      return left.newest === undefined ? 1 : -1;
    }
    if (left.newest === right.newest) {
      return left.position - right.position;
    }
    return left.newest < right.newest ? 1 : -1;
  });

  return decorated.map((entry) => entry.character);
}
