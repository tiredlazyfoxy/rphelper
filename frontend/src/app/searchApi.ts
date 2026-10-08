// The my-search wire surface (feature 029, step 004): the five hit rows and the grouped
// envelope exactly as `GET /api/search` sends them, plus the single call. No renaming layer:
// every key below is the server's key.
// Ids are decimal strings and are never parsed, coerced or compared numerically.
// Failures are the shared client's `ApiError`s, rethrown unchanged; an abort rejects as the
// raw `AbortError`, never wrapped.
import { apiGet } from "../shared/api";
import type { MemoScope } from "./memosApi";

/** One character hit: the matched name and whether the character is archived (U3). */
export type CharacterHit = {
  id: string;
  name: string;
  archived: boolean; // `archived_at` is not null
};

/** One setup hit; setups have no route, so the row lands on `character_id`'s page. */
export type SetupHit = {
  id: string;
  name: string;
  character_id: string;
  character_name: string;
  archived: boolean;
};

/** One session hit: no snippet — the row is labelled by its start and its owners. */
export type SessionHit = {
  id: string;
  character_name: string;
  setup_name: string | null; // null when the session has no setup
  created_at: string; // fixed-width UTC text, as every other response sends it
  archived: boolean;
};

/** One settled-entry hit: a plain-text snippet plus the session it belongs to (R11). */
export type EntryHit = {
  id: string;
  session_id: string;
  snippet: string;
  character_name: string;
  session_created_at: string;
};

/**
 * One note hit. `scope_id` is null exactly for the `"user"` level; `character_id` is the
 * character page the note routes to — `scope_id` for `"character"`, the setup's character for
 * `"setup"`, null for `"user"` and `"session"`. `is_enabled` is reported, never filtered on
 * (US-137.AC-1).
 */
export type MemoHit = {
  id: string;
  scope: MemoScope;
  scope_id: string | null;
  character_id: string | null;
  snippet: string;
  is_enabled: boolean;
};

/**
 * The route's 200 body: five groups in UC-059 order, each possibly empty. The server caps
 * each group and fixes each group's row order; the client re-sorts nothing.
 */
export type MySearchResults = {
  characters: CharacterHit[];
  setups: SetupHit[];
  sessions: SessionHit[];
  entries: EntryHit[];
  memos: MemoHit[];
};

const SEARCH_PATH = "/api/search";
const QUERY_PARAM = "q";

/**
 * `GET /api/search?q=<text>` — one query across everything the caller owns. The text is sent
 * URL-encoded as the `q` search parameter, untrimmed and otherwise unchanged; the caller
 * decides whether a blank query is worth a request (`loadSearch` does not issue one).
 * Resolves to the five groups as received. Rejects with the shared client's `ApiError`
 * unchanged — `no_embedding_model` 409 and `llm_unreachable` 502 fail the whole search (U1) —
 * and with the raw `AbortError` once `signal` is aborted.
 */
export async function fetchMySearch(query: string, signal?: AbortSignal): Promise<MySearchResults> {
  const search = new URLSearchParams();
  search.append(QUERY_PARAM, query);
  const body = await apiGet<MySearchResults | undefined>(
    `${SEARCH_PATH}?${search.toString()}`,
    signal,
  );
  // An empty 2xx body reads as `undefined` through the shared client; the page always has
  // five groups to render.
  return body ?? { characters: [], setups: [], sessions: [], entries: [], memos: [] };
}
