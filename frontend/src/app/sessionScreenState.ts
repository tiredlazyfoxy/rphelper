// The session screen's state (feature 011, step 009): one data class holding the session
// id, the loaded session and the load status — observable fields only, no methods and no
// computed getters. The one effect is a free function below, taking the state first.
// `characterScreenState.ts` (009 step 006) is the direct template.
//
// Deliberately NOT the workspace `SessionsState` (004): that one is the tree's working list
// and an archived session reached by URL is not in it, so this screen's single source is one
// `GET /api/sessions/{id}` by id, archived or not. The load is a pure read — opening or
// reading a session never bumps `last_used_at` (D3), and there is no resume route.
import { makeAutoObservable, runInAction } from "mobx";

import { isApiError } from "../shared/apiError";
import type { Session } from "./sessionsApi";
import { fetchSession } from "./sessionsApi";

/**
 * Explicit load status for the screen: gates the loader, the 404 text and the failure
 * branch. `"idle"` is the pre-load value — the component loads on mount.
 */
export type SessionScreenStatus = "idle" | "loading" | "ready" | "not-found" | "failed";

export class SessionScreenState {
  /** The `:id` route parameter verbatim. A string, never parsed. */
  sessionId: string;
  /** The last server-returned session, or null before the first successful response. */
  session: Session | null = null;
  status: SessionScreenStatus = "idle";

  constructor(sessionId: string) {
    this.sessionId = sessionId;
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/**
 * The backend's code for "no such session of mine" (001) — the only one the screen reads.
 * Module-private on purpose: the screen's rendered text comes from the spec, not from here.
 */
const SESSION_NOT_FOUND = "session_not_found";

/** An aborted `fetch` rejects with a plain `Error` named "AbortError", never an `ApiError`. */
function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/**
 * Effect: fetch `state.sessionId` into the screen. Sets `"loading"` first (so a Retry from
 * `"failed"` shows the loader again), then on success writes the session with `"ready"`. An
 * `ApiError` whose code is `session_not_found` writes `"not-found"`; any other failure —
 * including a transport failure — writes `"failed"`. Writes nothing once aborted and never
 * rejects. Reads only: no write route is called, so `last_used_at` is untouched (D3).
 */
export async function loadSessionScreen(
  state: SessionScreenState,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted) {
    return;
  }

  const sessionId = state.sessionId;

  // "loading" first, so a Retry from the failed state shows the loader again.
  runInAction(() => {
    state.status = "loading";
  });

  let session: Session;
  try {
    session = await fetchSession(sessionId, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    // The 404 is its own terminal branch: retrying an id that is not ours cannot start
    // answering, so the screen shows "Session not found" without a Retry.
    const notFound = isApiError(error) && error.code === SESSION_NOT_FOUND;
    runInAction(() => {
      state.status = notFound ? "not-found" : "failed";
    });
    return;
  }

  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    state.session = session;
    state.status = "ready";
  });
}
