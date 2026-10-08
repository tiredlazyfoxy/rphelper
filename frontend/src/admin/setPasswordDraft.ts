// The set-password modal's draft: a data class (observable fields only, no methods, no
// computed getters) plus free functions over it (002 D2, context.md D6 / D16). No current
// password field and no password policy.
import { makeAutoObservable, runInAction } from "mobx";
import { apiPost } from "../shared/api";
import { ApiError, CLIENT_TRANSPORT_FAILED } from "../shared/apiError";
import type { AdminUserRow } from "./usersPageState";

/** The client-validated fields — the keys of the client-error map. */
export type SetPasswordField = "password" | "confirmation";

/** Field-keyed client errors; a key is present only when that field is invalid. */
export type SetPasswordClientErrors = Partial<Record<SetPasswordField, string>>;

/**
 * Keys of the server-error map: the general key only. The password route produces no
 * field-attributable refusal, so every failure lands on `general`.
 */
export type SetPasswordServerErrorKey = "general";

/** Status-keyed server errors; every failure lands on `general`. */
export type SetPasswordServerErrors = Partial<Record<SetPasswordServerErrorKey, string>>;

/** The merged view the modal renders: client errors plus server errors. */
export type SetPasswordErrors = Partial<Record<SetPasswordField | SetPasswordServerErrorKey, string>>;

/** Whether a submit is in flight. */
export type SetPasswordSubmitStatus = "idle" | "submitting";

export class SetPasswordDraft {
  password = "";
  confirmation = "";
  serverErrors: SetPasswordServerErrors = {};
  submitStatus: SetPasswordSubmitStatus = "idle";

  constructor() {
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/**
 * Pure: the field-keyed client errors (empty object when valid). New password required,
 * confirmation must match. No length floor, no character classes, no strength rule.
 */
export function setPasswordClientErrors(draft: SetPasswordDraft): SetPasswordClientErrors {
  const errors: SetPasswordClientErrors = {};
  if (draft.password.trim().length === 0) {
    errors.password = "Enter a new password.";
  }
  if (draft.confirmation !== draft.password) {
    errors.confirmation = "The passwords do not match.";
  }
  return errors;
}

/** Pure: the merged view of client errors and `draft.serverErrors`. */
export function setPasswordErrors(draft: SetPasswordDraft): SetPasswordErrors {
  return { ...draft.serverErrors, ...setPasswordClientErrors(draft) };
}

/** Pure: true only when there are no client errors and no submit is in flight. */
export function canSubmitSetPassword(draft: SetPasswordDraft): boolean {
  if (draft.submitStatus === "submitting") {
    return false;
  }
  return Object.keys(setPasswordClientErrors(draft)).length === 0;
}

const GENERIC_FAILURE = "The password could not be set.";
const TRANSPORT_FAILURE = "The server could not be reached. Check that it is running and try again.";
const MALFORMED_RESPONSE = "The server returned an unreadable response.";

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/** The affected row, or null when the 200 body is not row-shaped. The id is never parsed. */
function asUpdatedRow(value: unknown): AdminUserRow | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const candidate = value as Partial<Record<keyof AdminUserRow, unknown>>;
  if (typeof candidate.id !== "string" || typeof candidate.username !== "string") {
    return null;
  }
  return value as AdminUserRow;
}

/**
 * Maps any failure onto the general key; the key never depends on a message string. A
 * message that would echo a submitted secret is replaced by a generic one.
 */
function serverErrorsFor(error: unknown, secrets: readonly string[]): SetPasswordServerErrors {
  let message = GENERIC_FAILURE;
  if (error instanceof ApiError) {
    if (error.code === CLIENT_TRANSPORT_FAILED) {
      message = TRANSPORT_FAILURE;
    } else if (error.message.length > 0) {
      message = error.message;
    }
  }
  if (secrets.some((secret) => secret.length > 0 && message.includes(secret))) {
    message = GENERIC_FAILURE;
  }
  return { general: message };
}

/**
 * Posts `{ password }` to `POST /api/admin/users/{targetId}/password` (the confirmation is
 * never sent; `targetId` is the row's string id, never parsed). On 200 invokes `onSaved`
 * once with the affected row. Every failure (any status, transport failure, malformed
 * body) lands on `serverErrors.general`; never reads a message string to decide the key.
 * `runInAction`s every write; early-returns on an aborted signal before writing. Does not
 * reject.
 */
export async function submitSetPassword(
  draft: SetPasswordDraft,
  targetId: string,
  onSaved: (updated: AdminUserRow) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted || draft.submitStatus === "submitting") {
    return;
  }

  const body = { password: draft.password };
  const secrets = [draft.password, draft.confirmation];

  runInAction(() => {
    draft.submitStatus = "submitting";
    draft.serverErrors = {};
  });

  let updated: AdminUserRow | null;
  try {
    const response = await apiPost<unknown>(
      `/api/admin/users/${encodeURIComponent(targetId)}/password`,
      body,
      signal,
    );
    if (signal?.aborted) {
      return;
    }
    updated = asUpdatedRow(response);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    const serverErrors = serverErrorsFor(error, secrets);
    runInAction(() => {
      draft.serverErrors = serverErrors;
    });
    return;
  } finally {
    if (!signal?.aborted) {
      runInAction(() => {
        draft.submitStatus = "idle";
      });
    }
  }

  if (updated === null) {
    runInAction(() => {
      draft.serverErrors = { general: MALFORMED_RESPONSE };
    });
    return;
  }
  onSaved(updated);
}
