// The change-role modal's draft: a data class (observable fields only, no methods, no
// computed getters) plus free functions over it (002 D2, context.md D1 / D16). The
// self-target refusal is the server's and is never re-implemented here.
import { makeAutoObservable, runInAction } from "mobx";
import { apiPost } from "../shared/api";
import { ApiError, CLIENT_TRANSPORT_FAILED } from "../shared/apiError";
import type { AdminUserRole, AdminUserRow } from "./usersPageState";

/** The client-validated fields — the keys of the client-error map. */
export type ChangeRoleField = "role";

/** Field-keyed client errors; a key is present only when that field is invalid. */
export type ChangeRoleClientErrors = Partial<Record<ChangeRoleField, string>>;

/**
 * Keys of the server-error map: the general key only. A 409 (self-targeted role change)
 * maps to a fixed "an administrator cannot change their own role" message on `general`;
 * every other failure lands there too.
 */
export type ChangeRoleServerErrorKey = "general";

/** Status-keyed server errors; every failure lands on `general`. */
export type ChangeRoleServerErrors = Partial<Record<ChangeRoleServerErrorKey, string>>;

/** The merged view the modal renders: client errors plus server errors. */
export type ChangeRoleErrors = Partial<Record<ChangeRoleField | ChangeRoleServerErrorKey, string>>;

/** Whether a submit is in flight. */
export type ChangeRoleSubmitStatus = "idle" | "submitting";

export class ChangeRoleDraft {
  /** The selected role; `null` when the Select has been cleared. */
  role: AdminUserRole | null;
  serverErrors: ChangeRoleServerErrors = {};
  submitStatus: ChangeRoleSubmitStatus = "idle";

  /** `currentRole` is the target row's current role — the initial selection. */
  constructor(currentRole: AdminUserRole) {
    this.role = currentRole;
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/** Pure: the field-keyed client errors (empty object when valid). A role must be selected. */
export function changeRoleClientErrors(draft: ChangeRoleDraft): ChangeRoleClientErrors {
  const errors: ChangeRoleClientErrors = {};
  if (draft.role === null) {
    errors.role = "Select a role.";
  }
  return errors;
}

/** Pure: the merged view of client errors and `draft.serverErrors`. */
export function changeRoleErrors(draft: ChangeRoleDraft): ChangeRoleErrors {
  return { ...draft.serverErrors, ...changeRoleClientErrors(draft) };
}

/** Pure: true only when there are no client errors and no submit is in flight. */
export function canSubmitChangeRole(draft: ChangeRoleDraft): boolean {
  if (draft.submitStatus === "submitting") {
    return false;
  }
  return Object.keys(changeRoleClientErrors(draft)).length === 0;
}

/** The route's refusal status: the target is the caller (a self-targeted role change). */
const CONFLICT_STATUS = 409;

const SELF_ROLE_CHANGE = "An administrator cannot change their own role.";
const GENERIC_FAILURE = "The role could not be changed.";
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
 * Maps a failure onto the general key by status only: 409 → the fixed self-change
 * message; anything else → the error's own message or a generic one. The key and the
 * 409 message never depend on a message string.
 */
function serverErrorsFor(error: unknown): ChangeRoleServerErrors {
  if (error instanceof ApiError && error.status === CONFLICT_STATUS) {
    return { general: SELF_ROLE_CHANGE };
  }
  let message = GENERIC_FAILURE;
  if (error instanceof ApiError) {
    if (error.code === CLIENT_TRANSPORT_FAILED) {
      message = TRANSPORT_FAILURE;
    } else if (error.message.length > 0) {
      message = error.message;
    }
  }
  return { general: message };
}

/**
 * Posts `{ role }` to `POST /api/admin/users/{targetId}/role` (`targetId` is the row's
 * string id, never parsed). On 200 invokes `onSaved` once with the affected row. Failures
 * map by status: 409 lands on `serverErrors.general` with a fixed "an administrator cannot
 * change their own role" message; anything else lands on `serverErrors.general` too. Never
 * reads a message string to decide the key. `runInAction`s every write; early-returns on
 * an aborted signal before writing. Does not reject.
 */
export async function submitChangeRole(
  draft: ChangeRoleDraft,
  targetId: string,
  onSaved: (updated: AdminUserRow) => void,
  signal?: AbortSignal,
): Promise<void> {
  const role = draft.role;
  if (signal?.aborted || draft.submitStatus === "submitting" || role === null) {
    return;
  }

  runInAction(() => {
    draft.submitStatus = "submitting";
    draft.serverErrors = {};
  });

  let updated: AdminUserRow | null;
  try {
    const response = await apiPost<unknown>(
      `/api/admin/users/${encodeURIComponent(targetId)}/role`,
      { role },
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
    const serverErrors = serverErrorsFor(error);
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
