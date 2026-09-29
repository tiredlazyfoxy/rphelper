// The admin gate's logic: pure decisions over the fetched identity and a thrown value,
// plus the impure enforce half that fetches `GET /api/me` and performs the one deny
// navigation.
import { apiGet, documentNavigation } from "../shared/api";
import { isApiError } from "../shared/apiError";
import { isNotReady } from "../shared/notReady";

/** The five outcomes of the admin gate (`context.md` D13). */
export type AdminAccessDecision =
  | "granted"
  | "denied-no-session"
  | "denied-not-admin"
  | "not-ready"
  | "failed";

/** The identity `GET /api/me` answers with. `id` is a decimal string and is never parsed. */
export type CurrentUser = {
  id: string;
  username: string;
  role: "roleplayer" | "admin";
};

/**
 * What `enforceAdminAccess` resolves to: the decision, plus — only for `"failed"` — the
 * thrown error's message, which the failure screen shows (`context.md` D13).
 */
export type AdminAccessResult =
  | { decision: Exclude<AdminAccessDecision, "failed"> }
  | { decision: "failed"; message: string };

/** The fixed, uncapped not-ready re-probe interval, in milliseconds. */
export const ADMIN_ACCESS_RETRY_INTERVAL_MS = 2000;

const ME_PATH = "/api/me";
const APP_AREA_PATH = "/";
const UNAUTHORIZED_STATUS = 401;
const GENERIC_FAILURE_MESSAGE = "Your access to the admin area could not be checked.";

/** Pure and total: `null` means nothing was fetched. Only the role decides. */
export function resolveAdminAccess(
  currentUser: CurrentUser | null,
): "granted" | "denied-no-session" | "denied-not-admin" {
  if (currentUser === null) {
    return "denied-no-session";
  }
  return currentUser.role === "admin" ? "granted" : "denied-not-admin";
}

/** Pure: classifies a value thrown by the `/api/me` request as not-ready or failed. */
export function classifyAdminAccessError(error: unknown): "not-ready" | "failed" {
  return isNotReady(error) ? "not-ready" : "failed";
}

/** The failure screen's text: an `ApiError`'s own message when it has one, else a generic one. */
function failureMessage(error: unknown): string {
  if (isApiError(error) && error.message.trim() !== "") {
    return error.message;
  }
  return GENERIC_FAILURE_MESSAGE;
}

/** Impure: one `GET /api/me`, one decision, and the only deny navigation (to `/`). */
export async function enforceAdminAccess(signal?: AbortSignal): Promise<AdminAccessResult> {
  let currentUser: CurrentUser;
  try {
    currentUser = await apiGet<CurrentUser>(ME_PATH, signal);
  } catch (error) {
    if (signal?.aborted) {
      throw error;
    }
    // The shared client has already navigated to `/login` on a 401; do not navigate again.
    if (isApiError(error) && error.status === UNAUTHORIZED_STATUS) {
      return { decision: resolveAdminAccess(null) };
    }
    const outcome = classifyAdminAccessError(error);
    if (outcome === "failed") {
      return { decision: "failed", message: failureMessage(error) };
    }
    return { decision: outcome };
  }

  const decision = resolveAdminAccess(currentUser);
  if (decision === "denied-not-admin") {
    documentNavigation.assign(APP_AREA_PATH);
  }
  return { decision };
}
