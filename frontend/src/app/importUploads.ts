// The `app` entry's import effects (feature 031, step 006). Two roleplayer imports — "import into
// my data" from the user menu and "import a session" from a character's Sessions section — share
// one shape: post the chosen file through `shared/importFile`, then reload what the new rows
// changed and raise the one search-coverage warning. Both live here as free functions with no
// MobX class: no control owns domain state about an import. It is the sibling of 030's
// `exportDownloads.ts`, with the one difference that these effects take a `signal`.
//
// Success is near-silent: there is no success toast (`ui-conventions.md` §"Async feedback"). The
// single `notifyWarning` these effects raise is a caveat about search coverage, not a success
// message — an import embeds nothing, so imported material stays outside the vector index until
// an administrator rebuilds it.
//
// Ids are strings end to end and are used exactly as given, so a 19-digit snowflake beyond
// `Number.MAX_SAFE_INTEGER` survives verbatim.
import { type ReadableTextFile, postExportFile } from "../shared/importFile";
import { notifyFailure } from "../shared/notifyFailure";
import { notifyWarning } from "../shared/notifyWarning";
import { type CharactersState, loadCharacters } from "./charactersState";
import { type SessionsState, loadSessions } from "./sessionsState";

/** The two granularities `POST /api/import` accepts, exactly as the route reports them back. */
export type OwnedImportGranularity = "user" | "character";

/** The whole 200 body of `POST /api/import`. */
export type OwnedImportResponse = {
  granularity: OwnedImportGranularity;
  /** The new ids of every imported character, ascending. Decimal strings, never numbers. */
  character_ids: string[];
};

/** The whole 200 body of `POST /api/characters/<characterId>/import`. */
export type SessionImportResponse = {
  /** The new id of the imported session, as a decimal string. */
  session_id: string;
};

/**
 * The navigation seam: what `useNavigate()` returns, narrowed to the one call these effects make.
 * It is passed in so each effect stays a free function testable without a router.
 */
export type NavigateTo = (path: string) => void;

/**
 * The Sessions section's own list reload, supplied by the component that owns that state.
 * `runSessionImport` awaits it; it resolves whatever the reload's outcome, like every other
 * loader in the entry.
 */
export type ReloadSection = () => Promise<void>;

const OWNED_IMPORT_PATH = "/api/import";

/** The id the one search-coverage caveat is raised under (`shared/notifyWarning.ts`). */
const COVERAGE_WARNING = "import-search-coverage" as const;

/**
 * Read through a call so the compiler does not narrow `aborted` for the rest of the body: the
 * flag can flip while the request is in flight (`logout.ts`'s idiom).
 */
function isAborted(signal: AbortSignal | undefined): boolean {
  return signal?.aborted === true;
}

/**
 * The abort predicate for the thrown value itself, matching on `name` alone whatever the
 * constructor: `fetch`/`AbortSignal` reject with a **`DOMException`**, which is not an
 * `instanceof Error`, so that narrower guard would route an abandoned import to `notifyFailure`.
 * Nothing else widens — the value must be a non-null object named exactly `AbortError`, and
 * `ApiError` sets `name = "ApiError"`, so every real failure still falls through.
 */
function isAbortRejection(error: unknown): boolean {
  return (
    typeof error === "object" && error !== null && "name" in error && error.name === "AbortError"
  );
}

/** The own-data import route (`user` and `character` granularities): the literal `/api/import`. */
export function ownedImportPath(): string {
  return OWNED_IMPORT_PATH;
}

/**
 * The one-session import route: `/api/characters/<characterId>/import`.
 *
 * @param characterId the target character's id as a decimal string, inserted verbatim.
 */
export function sessionImportPath(characterId: string): string {
  return `/api/characters/${encodeURIComponent(characterId)}/import`;
}

/**
 * Effect: posts `file` to `ownedImportPath()`. On success it reloads the characters list with
 * `loadCharacters` and then the session tree with `loadSessions` — sequentially, in that order —
 * navigates to `/characters/<the one id>` for a `character` result, and raises the search-coverage
 * warning once through `notifyWarning`.
 *
 * On any failure other than an abort it calls `notifyFailure` once. It **never rethrows** and
 * resolves either way, so every call site is a bare `void runOwnedImport(...)`. Once the signal is
 * aborted it notifies nothing, warns nothing, reloads nothing and navigates nowhere.
 */
export async function runOwnedImport(
  file: ReadableTextFile,
  charactersState: CharactersState,
  sessionsState: SessionsState,
  navigate: NavigateTo,
  signal?: AbortSignal,
): Promise<void> {
  if (isAborted(signal)) {
    return;
  }

  let result: OwnedImportResponse;
  try {
    result = await postExportFile<OwnedImportResponse>(ownedImportPath(), file, signal);
  } catch (error) {
    // An unreadable file and every refusal the route answers with arrive here the same way.
    // An abandoned import is not a failure, so it tells the roleplayer nothing.
    if (!isAborted(signal) && !isAbortRejection(error)) {
      notifyFailure(error);
    }
    return;
  }

  if (isAborted(signal)) {
    return;
  }

  // Sequentially, in this order: the characters list first, then the session level of the tree
  // (`SessionsState`), which the imported sessions also changed.
  await loadCharacters(charactersState, signal);
  await loadSessions(sessionsState, signal);

  if (result.granularity === "character" && result.character_ids.length > 0) {
    // The id is used exactly as returned: a 19-digit snowflake survives verbatim.
    navigate(`/characters/${result.character_ids[0]}`);
  }

  notifyWarning(COVERAGE_WARNING);
}

/**
 * Effect: posts `file` to `sessionImportPath(characterId)`. On success it awaits `reloadSection`
 * exactly once, then reloads the session tree with `loadSessions` — sequentially, in that order —
 * and raises the search-coverage warning once. It never navigates.
 *
 * Failures, aborts and the never-rethrow contract are as in `runOwnedImport`.
 */
export async function runSessionImport(
  characterId: string,
  file: ReadableTextFile,
  sessionsState: SessionsState,
  reloadSection: ReloadSection,
  signal?: AbortSignal,
): Promise<void> {
  if (isAborted(signal)) {
    return;
  }

  try {
    await postExportFile<SessionImportResponse>(sessionImportPath(characterId), file, signal);
  } catch (error) {
    if (!isAborted(signal) && !isAbortRejection(error)) {
      notifyFailure(error);
    }
    return;
  }

  if (isAborted(signal)) {
    return;
  }

  // The section's own list first, then the session level of the tree. The new session's id is
  // deliberately discarded: nothing here navigates.
  await reloadSection();
  await loadSessions(sessionsState, signal);

  notifyWarning(COVERAGE_WARNING);
}
