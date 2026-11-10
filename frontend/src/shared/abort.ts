// The one abort predicate every entry shares: an aborted `fetch` (or an abandoned request the
// shared API client re-throws) rejects with an `Error` named "AbortError" — never an
// `ApiError` — and callers treat it as "the caller walked away", not as a failure to surface.

/** Whether a rejection is an abort (an `Error` named "AbortError") rather than a failure. */
export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}
