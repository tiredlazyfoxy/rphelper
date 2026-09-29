// The create-account modal's draft: a data class (observable fields only, no methods, no
// computed getters) plus free functions over it (002 D2, context.md D6 / D10 / D16).
import { makeAutoObservable, runInAction } from "mobx";
import { apiPost } from "../shared/api";
import { ApiError, CLIENT_TRANSPORT_FAILED } from "../shared/apiError";
import type { AdminUserRole, AdminUserRow } from "./usersPageState";

/** The client-validated fields — the keys of the client-error map. */
export type CreateUserField = "username" | "password" | "confirmation";

/** Field-keyed client errors; a key is present only when that field is invalid. */
export type CreateUserClientErrors = Partial<Record<CreateUserField, string>>;

/**
 * Keys of the server-error map: the one field a status maps onto (409 → `username`)
 * plus the general catch-all for everything else. No `password` key: no password policy
 * exists to produce one (context.md D10).
 */
export type CreateUserServerErrorKey = "username" | "general";

/** Status-keyed server errors; anything that is not a 409 lands on `general`. */
export type CreateUserServerErrors = Partial<Record<CreateUserServerErrorKey, string>>;

/** The merged view the modal renders: client errors plus server errors. */
export type CreateUserErrors = Partial<Record<CreateUserField | CreateUserServerErrorKey, string>>;

/** Whether a submit is in flight. */
export type CreateUserSubmitStatus = "idle" | "submitting";

export class CreateUserDraft {
  username = "";
  password = "";
  confirmation = "";
  role: AdminUserRole = "roleplayer";
  serverErrors: CreateUserServerErrors = {};
  submitStatus: CreateUserSubmitStatus = "idle";

  constructor() {
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/**
 * Pure: the field-keyed client errors (empty object when valid). Username required,
 * password required (trimmed view decides "filled"), confirmation must match. No length
 * floor, no character classes, no strength rule.
 */
export function createUserClientErrors(draft: CreateUserDraft): CreateUserClientErrors {
  const errors: CreateUserClientErrors = {};
  if (draft.username.trim().length === 0) {
    errors.username = "Enter a username.";
  }
  if (draft.password.trim().length === 0) {
    errors.password = "Enter a password.";
  }
  if (draft.confirmation !== draft.password) {
    errors.confirmation = "The passwords do not match.";
  }
  return errors;
}

/** Pure: the merged view of client errors and `draft.serverErrors`. */
export function createUserErrors(draft: CreateUserDraft): CreateUserErrors {
  return { ...draft.serverErrors, ...createUserClientErrors(draft) };
}

/** Pure: true only when there are no client errors and no submit is in flight. */
export function canSubmitCreateUser(draft: CreateUserDraft): boolean {
  if (draft.submitStatus === "submitting") {
    return false;
  }
  return Object.keys(createUserClientErrors(draft)).length === 0;
}

/** The one status mapped onto a field: a conflict is a taken username (context.md D10). */
const CONFLICT_STATUS = 409;

const USERNAME_TAKEN = "That username is already taken.";
const GENERIC_FAILURE = "The account could not be created.";
const TRANSPORT_FAILURE = "The server could not be reached. Check that it is running and try again.";
const MALFORMED_RESPONSE = "The server returned an unreadable response.";

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/** The created row, or null when the 201 body is not row-shaped. The id is never parsed. */
function asCreatedRow(value: unknown): AdminUserRow | null {
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
 * Maps a failure onto the server-error map by status only: 409 → `username`; anything
 * else → `general`. The key never depends on a message string. A general message that
 * would echo a submitted secret is replaced by a generic one.
 */
function serverErrorsFor(error: unknown, secrets: readonly string[]): CreateUserServerErrors {
  if (error instanceof ApiError && error.status === CONFLICT_STATUS) {
    return { username: USERNAME_TAKEN };
  }
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
 * Posts `{ username, password, role }` exactly as typed to `POST /api/admin/users` (the
 * confirmation is never sent). On 201 invokes `onSaved` once with the created row.
 * Failures are mapped by status: 409 → `serverErrors.username`; anything else (other
 * status, transport failure, malformed body) → `serverErrors.general`. Never reads a
 * message string to decide the key. `runInAction`s every write; early-returns on an
 * aborted signal before writing. Does not reject.
 */
export async function submitCreateUser(
  draft: CreateUserDraft,
  onSaved: (created: AdminUserRow) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted || draft.submitStatus === "submitting") {
    return;
  }

  const body = { username: draft.username, password: draft.password, role: draft.role };
  const secrets = [draft.password, draft.confirmation];

  runInAction(() => {
    draft.submitStatus = "submitting";
    draft.serverErrors = {};
  });

  let created: AdminUserRow | null;
  try {
    const response = await apiPost<unknown>("/api/admin/users", body, signal);
    if (signal?.aborted) {
      return;
    }
    created = asCreatedRow(response);
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

  if (created === null) {
    runInAction(() => {
      draft.serverErrors = { general: MALFORMED_RESPONSE };
    });
    return;
  }
  onSaved(created);
}
