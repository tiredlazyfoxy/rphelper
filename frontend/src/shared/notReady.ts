// The not-ready-yet classification (003 context.md D10): a pure predicate over a thrown
// value. Navigates nothing, renders nothing, logs nothing.
import { ApiError, CLIENT_MALFORMED_ERROR, CLIENT_TRANSPORT_FAILED } from "./apiError";

/** True when `error` means "the backend is running but not yet answering". */
export function isNotReady(error: unknown): boolean {
  if (!(error instanceof ApiError)) {
    return false;
  }
  if (error.code === CLIENT_TRANSPORT_FAILED) {
    return true;
  }
  return error.code === CLIENT_MALFORMED_ERROR && error.status >= 500;
}
