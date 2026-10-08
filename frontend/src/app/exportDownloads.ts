// The `app` entry's export downloads (feature 030, step 006). Three export controls live in
// three different components — the user menu, the character screen and each session row — and
// they share exactly one effect: ask `apiDownload` for a route, and on failure route the thrown
// value through `notifyFailure`. That one effect lives here, as free functions with no MobX
// class: none of the three controls owns domain state about the export.
//
// Everything here is route-shaping plus one effect. There is no viewer, no preview, no size
// report and no row count — opacity (US-078, R5) means the module never looks inside a body.
// Success is silent: the browser's download is the signal, so there is no success notification
// and no success text anywhere (`ui-conventions.md` §"Async feedback").
//
// Ids are strings end to end and are used **exactly as given**. Nothing here parses, widens or
// re-formats one, so a 19-digit snowflake beyond `Number.MAX_SAFE_INTEGER` survives verbatim.
import { apiDownload } from "../shared/api";
import { notifyFailure } from "../shared/notifyFailure";

const OWN_DATA_EXPORT_PATH = "/api/export";

/**
 * The abort predicate: an abandoned download, never a real failure.
 *
 * It matches on the thrown value's `name` alone, whatever its constructor, because the two abort
 * shapes reaching here have different ones. `fetch`/`AbortSignal` — and `apiDownload`'s own
 * post-body-read abort re-check — reject with a **`DOMException`**, which is *not* an
 * `instanceof Error` in jsdom or historically in browsers; test doubles and hand-rolled aborts
 * throw a plain `Error` with `name` reassigned. An `instanceof Error` guard would let the
 * `DOMException` through to `notifyFailure`, so a roleplayer who navigates away mid-download would
 * be shown an error on the way out of the page.
 *
 * Nothing else widens: the value must still be a non-null object carrying exactly the name
 * `AbortError`, so every ordinary failure (`ApiError` included) falls through to `notifyFailure`.
 */
function isAbortRejection(error: unknown): boolean {
  return (
    typeof error === "object" && error !== null && "name" in error && error.name === "AbortError"
  );
}

/**
 * The caller's own-data export route (`user` granularity): the literal `/api/export`.
 *
 * Takes no input — the route is scoped to the authenticated session on the server.
 */
export function ownDataExportPath(): string {
  return OWN_DATA_EXPORT_PATH;
}

/**
 * The one-character export route (`character` granularity):
 * `/api/characters/<characterId>/export`.
 *
 * @param characterId the character's id as a decimal string, inserted verbatim.
 */
export function characterExportPath(characterId: string): string {
  return `/api/characters/${encodeURIComponent(characterId)}/export`;
}

/**
 * The one-session export route (`session` granularity): `/api/sessions/<sessionId>/export`.
 *
 * @param sessionId the session's id as a decimal string, inserted verbatim.
 */
export function sessionExportPath(sessionId: string): string {
  return `/api/sessions/${encodeURIComponent(sessionId)}/export`;
}

/**
 * Effect: downloads the export at `path` through `apiDownload`, and on any thrown value other
 * than an abort hands that value to `notifyFailure` — once, and never on success.
 *
 * Resolves on success and on handled failure alike, and **never rethrows**, so every call site
 * is a bare `void runExport(...)` (or an `await` where a local loading flag must be cleared).
 * It raises nothing on success: the download itself is the only feedback.
 *
 * @param path one of the three routes above.
 */
export async function runExport(path: string): Promise<void> {
  try {
    // The resolved `DownloadResult` is deliberately discarded: nothing in the `app` entry
    // reports a filename or a byte count (opacity), and success is already visible as the
    // browser's download.
    await apiDownload(path);
  } catch (error) {
    if (isAbortRejection(error)) {
      return;
    }
    notifyFailure(error);
  }
}
