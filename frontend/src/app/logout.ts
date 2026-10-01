// The logout effect (008 context.md D7): post, then hand off to the `/login` document; on
// any failure tell the roleplayer and stay. Invoked from a click handler, so it never
// rethrows. It names `fetch` nowhere — the shared client owns the transport, the `ApiError`
// wrapping and the 401 handling — and it navigates only through the `documentNavigation`
// seam.
import { apiPost, documentNavigation } from "../shared/api";
import { notifyFailure } from "../shared/notifyFailure";

const LOGOUT_PATH = "/api/auth/logout";
const LOGIN_PATH = "/login";

/**
 * Read through a call so the compiler does not narrow `aborted` for the rest of the body:
 * the flag can flip while the request is in flight.
 */
function isAborted(signal: AbortSignal | undefined): boolean {
  return signal?.aborted === true;
}

/**
 * Effect. One `POST /api/auth/logout` with no body through the shared client; on success a
 * document navigation to `/login`. Any thrown failure goes to `notifyFailure` and the
 * roleplayer stays where they are — nothing is rethrown. An abort neither navigates nor
 * notifies.
 */
export async function logOut(signal?: AbortSignal): Promise<void> {
  if (isAborted(signal)) {
    return;
  }

  try {
    await apiPost(LOGOUT_PATH, undefined, signal);
  } catch (error) {
    // D7: the session very probably still exists, so staying put is the honest outcome —
    // and a menu item's failure has no place of its own to render in.
    if (!isAborted(signal)) {
      notifyFailure(error);
    }
    return;
  }

  if (isAborted(signal)) {
    return;
  }
  documentNavigation.assign(LOGIN_PATH);
}
