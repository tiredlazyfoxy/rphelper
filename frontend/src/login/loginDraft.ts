// The sign-in form's draft: a data class (observable fields only) plus free functions over
// it (002 D2 / D6, 003 context.md D13, 004 context.md D1, D13, D16).
import { makeAutoObservable, runInAction } from "mobx";
import { apiPost } from "../shared/api";
import { ApiError, CLIENT_TRANSPORT_FAILED } from "../shared/apiError";

/** The client-validated fields — the keys of the client-error map. */
export type LoginField = "username" | "password";

/** Field-keyed client errors; a key is present only when that field is invalid. */
export type LoginClientErrors = Partial<Record<LoginField, string>>;

/** Keys of the server-error map: the two sent fields plus the general catch-all. */
export type LoginServerErrorKey = "username" | "password" | "general";

/** Field-keyed server errors; every refusal and failure lands on `general`. */
export type LoginServerErrors = Partial<Record<LoginServerErrorKey, string>>;

/** The plain value `submitLogin` resolves to; the caller acts on it. */
export type LoginOutcome = "signedIn" | "failed";

export class LoginDraft {
  username = "";
  password = "";
  serverErrors: LoginServerErrors = {};
  submitting = false;

  constructor() {
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/**
 * Pure: the field-keyed client errors for the draft (empty object when valid). The username
 * is judged on its trimmed value; nothing that is sent is changed (context.md D13).
 */
export function loginClientErrors(draft: LoginDraft): LoginClientErrors {
  const errors: LoginClientErrors = {};
  if (draft.username.trim().length === 0) {
    errors.username = "Enter your username.";
  }
  if (draft.password.length === 0) {
    errors.password = "Enter your password.";
  }
  return errors;
}

/** Pure: true only when there are no client errors and no submit is in flight. */
export function canSubmitLogin(draft: LoginDraft): boolean {
  if (draft.submitting) {
    return false;
  }
  return Object.keys(loginClientErrors(draft)).length === 0;
}

/** The backend code by which a refusal is recognised — never by status, never by prose. */
const INVALID_CREDENTIALS = "invalid_credentials";

/** The one message for every refusal: unknown user, wrong password, disabled account (D1). */
const REFUSAL_MESSAGE = "Sign-in failed. Check the credentials you entered and try again.";
const TRANSPORT_FAILURE = "The server could not be reached. Check that it is running and try again.";
const GENERIC_FAILURE = "Signing in did not work because of a server problem. Try again.";

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/**
 * Maps a failure onto the server-error map by code or status, never by parsing prose.
 * Every failure lands on `general`; no per-field message is ever written (D1). Messages are
 * fixed texts, and one that would contain a submitted value is replaced by the generic one.
 */
function serverErrorsFor(error: unknown, values: readonly string[]): LoginServerErrors {
  let message = GENERIC_FAILURE;
  if (error instanceof ApiError) {
    if (error.code === INVALID_CREDENTIALS) {
      message = REFUSAL_MESSAGE;
    } else if (error.code === CLIENT_TRANSPORT_FAILED) {
      message = TRANSPORT_FAILURE;
    }
  }
  if (values.some((value) => value.length > 0 && message.includes(value))) {
    message = GENERIC_FAILURE;
  }
  return { general: message };
}

/**
 * Posts `{ username, password }` exactly as typed to `POST /api/auth/login` once.
 * `runInAction`s the in-flight flag around the call; early-returns on an aborted signal
 * before writing. Failures are mapped onto `serverErrors.general` by code or status →
 * "failed". No navigation, no read of the success body, no `notifyFailure`.
 */
export async function submitLogin(
  draft: LoginDraft,
  signal?: AbortSignal,
): Promise<LoginOutcome> {
  if (signal?.aborted || draft.submitting) {
    return "failed";
  }

  const username = draft.username;
  const password = draft.password;

  runInAction(() => {
    draft.submitting = true;
  });
  try {
    await apiPost<unknown>("/api/auth/login", { username, password }, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return "failed";
    }
    const serverErrors = serverErrorsFor(error, [username, password]);
    runInAction(() => {
      draft.serverErrors = serverErrors;
    });
    return "failed";
  } finally {
    runInAction(() => {
      draft.submitting = false;
    });
  }

  if (signal?.aborted) {
    return "failed";
  }
  runInAction(() => {
    draft.serverErrors = {};
  });
  return "signedIn";
}
