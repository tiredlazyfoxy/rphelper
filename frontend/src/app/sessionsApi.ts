// The sessions wire surface (feature 011, step 004): the `Session` row as the server sends
// it, one pure predicate, and the six calls over the shared client. Two path families, as the
// wire contract has them: `/api/characters/<character_id>/sessions` for the character listing
// and the start, `/api/sessions` plus `/api/sessions/<session_id>…` for the workspace listing,
// the single read and the two actions. There is no update and no delete call (R6).
// Ids are decimal strings and are never parsed, coerced or compared numerically.
// Failures are the shared client's `ApiError`s, rethrown unchanged.
import { apiGet, apiPost } from "../shared/api";

/** One session, exactly as the sessions routes send it. No renaming layer. */
export type Session = {
  id: string;
  character_id: string;
  setup_id: string | null;
  setup_name: string | null; // the setup's current name, present even when it is archived
  archived_at: string | null; // fixed-width UTC text, or null while working
  last_used_at: string;
  created_at: string;
  updated_at: string;
};

/** Either listing route's body: `{ sessions: [...] }`. */
export type SessionListResponse = {
  sessions: Session[];
};

const SESSIONS_PATH = "/api/sessions";

/** `/api/characters/<characterId>/sessions`; the id is only ever escaped, never parsed. */
function characterSessionsPath(characterId: string): string {
  return `/api/characters/${encodeURIComponent(characterId)}/sessions`;
}

/** `/api/sessions/<sessionId>` plus an optional action suffix; the id is only ever escaped. */
function sessionPath(sessionId: string, suffix = ""): string {
  return `${SESSIONS_PATH}/${encodeURIComponent(sessionId)}${suffix}`;
}

/** The archive query flag, appended to a listing path only when asked. */
function withIncludeArchived(listing: string, includeArchived: boolean): string {
  return includeArchived ? `${listing}?include_archived=true` : listing;
}

/** Pure: whether this session is archived (`archived_at` non-null). */
export function isSessionArchived(session: Session): boolean {
  return session.archived_at !== null;
}

/**
 * `GET /api/sessions`, with `?include_archived=true` only when asked: the caller's sessions
 * across all characters. Resolves to the payload's `sessions` array, in the order received.
 */
export async function fetchSessions(
  includeArchived: boolean,
  signal?: AbortSignal,
): Promise<Session[]> {
  const body = await apiGet<SessionListResponse | undefined>(
    withIncludeArchived(SESSIONS_PATH, includeArchived),
    signal,
  );
  return body?.sessions ?? [];
}

/**
 * `GET /api/characters/<characterId>/sessions`, with `?include_archived=true` only when
 * asked. Resolves to the payload's `sessions` array, in the order received.
 */
export async function fetchCharacterSessions(
  characterId: string,
  includeArchived: boolean,
  signal?: AbortSignal,
): Promise<Session[]> {
  const body = await apiGet<SessionListResponse | undefined>(
    withIncludeArchived(characterSessionsPath(characterId), includeArchived),
    signal,
  );
  return body?.sessions ?? [];
}

/** `GET /api/sessions/<sessionId>` — archived or not. */
export async function fetchSession(sessionId: string, signal?: AbortSignal): Promise<Session> {
  return apiGet<Session>(sessionPath(sessionId), signal);
}

/**
 * `POST /api/characters/<characterId>/sessions` with the JSON body `{ setup_id: <id or null> }`
 * — always sent, so the request states "no setup" rather than implying it. Resolves to the
 * created session.
 */
export async function startSession(
  characterId: string,
  setupId: string | null,
  signal?: AbortSignal,
): Promise<Session> {
  return apiPost<Session>(characterSessionsPath(characterId), { setup_id: setupId }, signal);
}

/** `POST /api/sessions/<sessionId>/archive` — resolves to the session. */
export async function archiveSession(sessionId: string, signal?: AbortSignal): Promise<Session> {
  return apiPost<Session>(sessionPath(sessionId, "/archive"), undefined, signal);
}

/** `POST /api/sessions/<sessionId>/restore` — resolves to the session. */
export async function restoreSession(sessionId: string, signal?: AbortSignal): Promise<Session> {
  return apiPost<Session>(sessionPath(sessionId, "/restore"), undefined, signal);
}
