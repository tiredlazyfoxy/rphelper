// The results page's state (feature 029, step 004): observable fields only, no methods and no
// computed getters. The load effect, the two predicates and the URL/target helpers are the
// free functions below, each taking the state or a hit as its first argument.
// Ids are decimal strings and are never parsed, coerced or compared numerically. Failures are
// shown inline by the page — nothing here notifies.
import { makeAutoObservable, runInAction } from "mobx";

import { isApiError } from "../shared/apiError";
import type {
  CharacterHit,
  EntryHit,
  MemoHit,
  MySearchResults,
  SessionHit,
  SetupHit,
} from "./searchApi";
import { fetchMySearch } from "./searchApi";

/** Explicit load status: gates the loading, empty and failure renders, not "groups are empty". */
export type SearchLoadStatus = "idle" | "loading" | "ready" | "failed";

/**
 * One results page's state. Created per `SearchScreen` mount (`useState`), never a module
 * singleton, so a fresh arrival at `/search` starts idle.
 */
export class SearchState {
  status: SearchLoadStatus = "idle";
  /** The query text the current `results` or `failure` belong to; `""` while nothing is loaded. */
  query = "";
  /** The five groups as received, or null while idle, loading the first query, or failed. */
  results: MySearchResults | null = null;
  /** The failure's own message, shown inline with `Retry`, or null when there is none. */
  failure: string | null = null;

  constructor() {
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/** Whether this query text is blank — empty or whitespace only. A blank query is never sent (D1). */
export function isBlankQuery(text: string): boolean {
  return text.trim().length === 0;
}

/**
 * Effect: load `query`'s results into `state`.
 *
 * A blank query issues **no request** and leaves the state idle — `status` `"idle"`, `results`
 * null, `failure` null — even when ready results were held before (U4, D1). Otherwise `status`
 * goes `"loading"`, then `"ready"` with the results and `query` recorded, or `"failed"` with
 * `failure` set to the `ApiError`'s own message (any other rejection: a generic message) and
 * `results` null. Writes nothing once `signal` is aborted, and never rejects.
 */
export async function loadSearch(
  state: SearchState,
  query: string,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted) {
    return;
  }

  if (isBlankQuery(query)) {
    // No request at all, and the previous query's results are cleared, not kept.
    runInAction(() => {
      state.status = "idle";
      state.results = null;
      state.failure = null;
    });
    return;
  }

  runInAction(() => {
    state.status = "loading";
  });

  let results: MySearchResults;
  try {
    results = await fetchMySearch(query, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    // U1: the envelope's own message is what the page shows inline.
    const message = isApiError(error) ? error.message : "Something went wrong. Please try again.";
    runInAction(() => {
      state.status = "failed";
      state.failure = message;
      state.results = null;
      state.query = query;
    });
    return;
  }

  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    state.results = results;
    state.failure = null;
    state.query = query;
    state.status = "ready";
  });
}

/**
 * Whether a finished search found nothing: true only when `status` is `"ready"` and all five
 * groups are empty — the one condition that renders `Nothing found.`
 */
export function hasNoHits(state: SearchState): boolean {
  if (state.status !== "ready" || state.results === null) {
    return false;
  }
  const { characters, setups, sessions, entries, memos } = state.results;
  return (
    characters.length === 0 &&
    setups.length === 0 &&
    sessions.length === 0 &&
    entries.length === 0 &&
    memos.length === 0
  );
}

const SEARCH_ROUTE = "/search";

/**
 * The results page's own path for a query text: `/search` when the text is blank, otherwise
 * `/search?q=` plus the URL-encoded text (encoded as given, untrimmed). Used by both triggers —
 * the tree's input and the page's own box (U4, D8).
 */
export function searchHref(text: string): string {
  if (isBlankQuery(text)) {
    return SEARCH_ROUTE;
  }
  return `${SEARCH_ROUTE}?q=${encodeURIComponent(text)}`;
}

const SETTINGS_ROUTE = "/settings";

/** `/characters/<id>`; the id is a decimal string, only ever escaped, never parsed. */
function characterRoute(characterId: string): string {
  return `/characters/${encodeURIComponent(characterId)}`;
}

/** `/sessions/<id>`; the id is a decimal string, only ever escaped, never parsed. */
function sessionRoute(sessionId: string): string {
  return `/sessions/${encodeURIComponent(sessionId)}`;
}

/** A character hit's target: `/characters/<id>`. */
export function characterTarget(hit: CharacterHit): string {
  return characterRoute(hit.id);
}

/** A setup hit's target: `/characters/<character_id>` — setups have no route of their own. */
export function setupTarget(hit: SetupHit): string {
  return characterRoute(hit.character_id);
}

/** A session hit's target: `/sessions/<id>`. */
export function sessionTarget(hit: SessionHit): string {
  return sessionRoute(hit.id);
}

/** An entry hit's target: `/sessions/<session_id>?entry=<id>` — the landing param D8 declares. */
export function entryTarget(hit: EntryHit): string {
  return `${sessionRoute(hit.session_id)}?entry=${encodeURIComponent(hit.id)}`;
}

/**
 * A note hit's target, by level (U4, D8): `"user"` → `/settings`; `"character"` and `"setup"` →
 * `/characters/<character_id>`; `"session"` → `/sessions/<scope_id>?notes=open`. The wire
 * contract guarantees the id each branch reads is non-null; a null one is substituted with the
 * empty string, which lands on the catch-all route rather than on another user's page.
 */
export function memoTarget(hit: MemoHit): string {
  switch (hit.scope) {
    case "user":
      return SETTINGS_ROUTE;
    case "character":
    case "setup":
      return characterRoute(hit.character_id ?? "");
    case "session":
      return `${sessionRoute(hit.scope_id ?? "")}?notes=open`;
  }
}
