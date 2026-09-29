// The create-administrator form's draft: a data class (observable fields only) plus free
// functions over it (002 D2 / D6, 003 context.md D13, D16).
import { makeAutoObservable, runInAction } from "mobx";
import { apiPost } from "../shared/api";
import { ApiError, CLIENT_TRANSPORT_FAILED } from "../shared/apiError";

/** The client-validated fields — the keys of the client-error map. */
export type CreateAdminField = "username" | "password" | "confirmation";

/** Field-keyed client errors; a key is present only when that field is invalid. */
export type CreateAdminClientErrors = Partial<Record<CreateAdminField, string>>;

/** Keys of the server-error map: the two sent fields plus the general catch-all. */
export type CreateAdminServerErrorKey = "username" | "password" | "general";

/** Field-keyed server errors; anything unmappable lands on `general`. */
export type CreateAdminServerErrors = Partial<Record<CreateAdminServerErrorKey, string>>;

/** The plain value `submitCreateAdmin` resolves to; the caller acts on it. */
export type CreateAdminOutcome = "created" | "refused" | "failed";

export class CreateAdminDraft {
  username = "";
  password = "";
  confirmation = "";
  serverErrors: CreateAdminServerErrors = {};
  submitting = false;

  constructor() {
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/** Pure: the field-keyed client errors for the draft (empty object when valid). */
export function createAdminClientErrors(draft: CreateAdminDraft): CreateAdminClientErrors {
  const errors: CreateAdminClientErrors = {};
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

/** Pure: true only when there are no client errors and no submit is in flight. */
export function canSubmitCreateAdmin(draft: CreateAdminDraft): boolean {
  if (draft.submitting) {
    return false;
  }
  return Object.keys(createAdminClientErrors(draft)).length === 0;
}

/** The backend code by which a refusal (UC-003) is recognised — never by status. */
const ALREADY_CONFIGURED = "already_configured";

const GENERIC_FAILURE = "The administrator could not be created.";
const TRANSPORT_FAILURE = "The server could not be reached. Check that it is running and try again.";

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/**
 * Maps a failure onto the server-error map by code or status, never by parsing prose.
 * The route defines no field-shaped code (003 context.md D15/D16), so every failure lands
 * on `general`. A message that would echo a submitted secret is replaced by a generic one.
 */
function serverErrorsFor(error: unknown, secrets: readonly string[]): CreateAdminServerErrors {
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
 * Posts `{ username, password }` to `POST /api/bootstrap/create` once. `runInAction`s the
 * in-flight flag around the call; early-returns on an aborted signal before writing.
 * `already_configured` → "refused" (not written onto the draft); other failures are mapped
 * onto `serverErrors` by code or status → "failed". No navigation, no `notifyFailure`.
 */
export async function submitCreateAdmin(
  draft: CreateAdminDraft,
  signal?: AbortSignal,
): Promise<CreateAdminOutcome> {
  if (signal?.aborted || draft.submitting) {
    return "failed";
  }

  const username = draft.username;
  const password = draft.password;
  const secrets = [draft.password, draft.confirmation];

  runInAction(() => {
    draft.submitting = true;
  });
  try {
    await apiPost<unknown>("/api/bootstrap/create", { username, password }, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return "failed";
    }
    if (error instanceof ApiError && error.code === ALREADY_CONFIGURED) {
      return "refused";
    }
    const serverErrors = serverErrorsFor(error, secrets);
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
  return "created";
}
