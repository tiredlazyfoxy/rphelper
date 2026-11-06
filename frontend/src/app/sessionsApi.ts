// The sessions wire surface (feature 011, step 004; feature 034, step 004): the `Session` row
// as the server sends it, one pure predicate, and the calls over the shared client. Two path
// families, as the wire contract has them: `/api/characters/<character_id>/sessions` for the
// character listing and the start, `/api/sessions` plus `/api/sessions/<session_id>…` for the
// workspace listing, the single read, the rename and the two actions. There is one update call
// (rename), no delete.
// Ids are decimal strings and are never parsed, coerced or compared numerically.
// Failures are the shared client's `ApiError`s, rethrown unchanged.
import { apiGet, apiPatch, apiPost } from "../shared/api";
import type { Message } from "./streamApi";

/** One session, exactly as the sessions routes send it. No renaming layer. */
export type Session = {
  id: string;
  character_id: string;
  setup_id: string | null;
  setup_name: string | null; // the setup's current name, present even when it is archived
  name: string | null; // the session's own stored name; null until renamed (never blank)
  archived_at: string | null; // fixed-width UTC text, or null while working
  last_used_at: string;
  created_at: string;
  updated_at: string;
};

/**
 * The start route's body (018 D5): the nine `Session` keys plus the seeded opening message,
 * or null when no opening text was sent.
 */
export type StartedSession = Session & {
  opening_message: Message | null;
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
 * created session's nine `Session` keys only: the route's `opening_message: null` never
 * reaches a store (018 D5).
 */
export async function startSession(
  characterId: string,
  setupId: string | null,
  signal?: AbortSignal,
): Promise<Session> {
  const started = await apiPost<StartedSession>(
    characterSessionsPath(characterId),
    { setup_id: setupId },
    signal,
  );
  return toSession(started);
}

/** The nine `Session` keys of a started session, named explicitly; drops `opening_message`. */
function toSession(started: Session): Session {
  return {
    id: started.id,
    character_id: started.character_id,
    setup_id: started.setup_id,
    setup_name: started.setup_name,
    name: started.name,
    archived_at: started.archived_at,
    last_used_at: started.last_used_at,
    created_at: started.created_at,
    updated_at: started.updated_at,
  };
}

/**
 * `POST /api/characters/<characterId>/sessions` (018 D5, 033 D8): create-and-seed. With no
 * setup id (null, the default) the JSON body is exactly `{ opening_message: <text verbatim> }`;
 * with one it is `{ opening_message, setup_id }`. Resolves to the served `StartedSession`
 * unchanged.
 */
export async function startSessionWithMessage(
  characterId: string,
  openingText: string,
  setupId: string | null = null,
  signal?: AbortSignal,
): Promise<StartedSession> {
  // No setup: the body stays exactly `{ opening_message }`, never `setup_id: null`.
  const body =
    setupId === null
      ? { opening_message: openingText }
      : { opening_message: openingText, setup_id: setupId };
  return apiPost<StartedSession>(characterSessionsPath(characterId), body, signal);
}

/**
 * `PATCH /api/sessions/<sessionId>` through the shared `apiPatch`, with a JSON body whose only
 * key is `name`, holding the given string or `null` exactly as passed (no client-side trim;
 * the server normalises blank to null). Resolves to the server's `Session`. Rejects with the
 * shared client's `ApiError` unchanged (e.g. `session_not_found` 404, 422).
 *
 * @param sessionId - the session id, escaped into the path and never parsed.
 * @param name - the new name, or `null` to clear it.
 * @param signal - optional abort signal.
 */
export async function renameSession(
  sessionId: string,
  name: string | null,
  signal?: AbortSignal,
): Promise<Session> {
  // The body is built from `name` alone so no other key can ever reach the narrow PATCH
  // (DEC-arch-session-names-2); `null` is sent, never omitted, because it means "clear".
  return apiPatch<Session>(sessionPath(sessionId), { name }, signal);
}

/** `POST /api/sessions/<sessionId>/archive` — resolves to the session. */
export async function archiveSession(sessionId: string, signal?: AbortSignal): Promise<Session> {
  return apiPost<Session>(sessionPath(sessionId, "/archive"), undefined, signal);
}

/** `POST /api/sessions/<sessionId>/restore` — resolves to the session. */
export async function restoreSession(sessionId: string, signal?: AbortSignal): Promise<Session> {
  return apiPost<Session>(sessionPath(sessionId, "/restore"), undefined, signal);
}
