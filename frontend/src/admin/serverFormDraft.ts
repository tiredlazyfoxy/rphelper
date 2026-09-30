// The server form modal's draft (register and edit): a data class (observable fields only,
// no methods, no computed getters) plus free functions over it (context.md D9 / D16).
import { makeAutoObservable, runInAction } from "mobx";
import { apiPatch, apiPost } from "../shared/api";
import { ApiError, CLIENT_TRANSPORT_FAILED } from "../shared/apiError";
import type { LlmServerKind, LlmServerRow } from "./llmServersPageState";

/** The client-validated fields — the keys of the client-error map. `kind` is typed, never invalid. */
export type ServerFormField = "name" | "baseUrl" | "pointer";

/** Field-keyed client errors; a key is present only when that field is invalid. */
export type ServerFormClientErrors = Partial<Record<ServerFormField, string>>;

/** Keys of the server-error map: the field keys plus the general catch-all. */
export type ServerFormServerErrorKey = ServerFormField | "general";

/** Status- or code-keyed server errors; anything unmappable lands on `general`. */
export type ServerFormServerErrors = Partial<Record<ServerFormServerErrorKey, string>>;

/** The merged view the modal renders: client errors plus server errors. */
export type ServerFormErrors = Partial<Record<ServerFormServerErrorKey, string>>;

/** Submit lifecycle. */
export type ServerFormSubmitStatus = "idle" | "submitting" | "done";

/**
 * The wire body of `POST` (register) and `PATCH` (edit). An absent key means "omitted";
 * `api_key_ref: ""` on an edit means "clear the stored pointer" (context.md D9).
 */
export type ServerFormPayload = {
  name?: string;
  kind?: LlmServerKind;
  base_url?: string;
  api_key_ref?: string;
};

export class ServerFormDraft {
  /** The row the draft was built from; `null` in register mode. Edit diffs against it. */
  original: LlmServerRow | null;
  name: string;
  kind: LlmServerKind;
  baseUrl: string;
  /** The API-key pointer text. Always starts empty — the server never returns it. */
  pointer = "";
  /** Set by the pointer field's change handler; never derived from `pointer`. */
  pointerTouched = false;
  serverErrors: ServerFormServerErrors = {};
  submitStatus: ServerFormSubmitStatus = "idle";

  /** Absent `row` = register mode; present = edit mode for that row. */
  constructor(row?: LlmServerRow) {
    this.original = row ?? null;
    this.name = row?.name ?? "";
    this.kind = row?.kind ?? "llamaswap";
    this.baseUrl = row?.base_url ?? "";
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/**
 * Pure: the field-keyed client errors (empty object when valid). Name non-empty; base URL
 * non-empty and an absolute `http`/`https` URL; pointer empty or `$` plus at least one char.
 */
export function serverFormClientErrors(draft: ServerFormDraft): ServerFormClientErrors {
  const errors: ServerFormClientErrors = {};
  if (draft.name.trim().length === 0) {
    errors.name = "Enter a name.";
  }
  if (draft.baseUrl.trim().length === 0) {
    errors.baseUrl = "Enter a base URL.";
  } else if (!isAbsoluteHttpUrl(draft.baseUrl.trim())) {
    errors.baseUrl = "Enter an absolute http:// or https:// URL.";
  }
  if (draft.pointer.length > 0 && !isPointerShaped(draft.pointer)) {
    errors.pointer = "Enter a pointer such as $OPENAI_API_KEY — a $ followed by a variable name, not a key.";
  }
  return errors;
}

/** Pure: the merged view of client errors and `draft.serverErrors`. */
export function serverFormErrors(draft: ServerFormDraft): ServerFormErrors {
  return { ...draft.serverErrors, ...serverFormClientErrors(draft) };
}

/** Pure: true only when there are no client errors and no submit is in flight. */
export function canSubmitServerForm(draft: ServerFormDraft): boolean {
  if (draft.submitStatus === "submitting") {
    return false;
  }
  return Object.keys(serverFormClientErrors(draft)).length === 0;
}

function isAbsoluteHttpUrl(value: string): boolean {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return false;
  }
  return (parsed.protocol === "http:" || parsed.protocol === "https:") && parsed.host.length > 0;
}

/** Empty is handled by the caller; otherwise `$` followed by at least one character. */
function isPointerShaped(value: string): boolean {
  return value.startsWith("$") && value.length > 1;
}

const NOT_FOUND_STATUS = 404;

const GENERIC_FAILURE = "The connection could not be saved.";
const NOT_FOUND_FAILURE = "This connection no longer exists. Close the dialog to refresh the list.";
const TRANSPORT_FAILURE = "The server could not be reached. Check that it is running and try again.";

const SERVERS_PATH = "/api/admin/llm-servers";

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/**
 * Maps a failure onto the server-error map by status or code only. This router has no
 * field-specific refusal the client does not already catch, so everything lands on
 * `general`; the key never depends on a message string.
 */
function serverErrorsFor(error: unknown): ServerFormServerErrors {
  if (error instanceof ApiError) {
    if (error.status === NOT_FOUND_STATUS) {
      return { general: NOT_FOUND_FAILURE };
    }
    if (error.code === CLIENT_TRANSPORT_FAILED) {
      return { general: TRANSPORT_FAILURE };
    }
    if (error.message.length > 0) {
      return { general: error.message };
    }
  }
  return { general: GENERIC_FAILURE };
}

/**
 * The D9 payload. Register: name, kind and base URL always; the pointer only when filled.
 * Edit: name, kind and base URL only when they differ from the original row; the pointer
 * only when its field was touched — then as typed, `""` meaning "clear".
 */
function payloadOf(draft: ServerFormDraft): ServerFormPayload {
  const original = draft.original;
  const payload: ServerFormPayload = {};
  if (original === null) {
    payload.name = draft.name;
    payload.kind = draft.kind;
    payload.base_url = draft.baseUrl;
    if (draft.pointer.length > 0) {
      payload.api_key_ref = draft.pointer;
    }
    return payload;
  }
  if (draft.name !== original.name) {
    payload.name = draft.name;
  }
  if (draft.kind !== original.kind) {
    payload.kind = draft.kind;
  }
  if (draft.baseUrl !== original.base_url) {
    payload.base_url = draft.baseUrl;
  }
  if (draft.pointerTouched) {
    payload.api_key_ref = draft.pointer;
  }
  return payload;
}

/**
 * Builds the D9 payload and sends it: `POST /api/admin/llm-servers` when `serverId` is
 * `null`, `PATCH /api/admin/llm-servers/{serverId}` otherwise. Maps failures by status or
 * code (never message text) onto `draft.serverErrors`; on success sets `submitStatus` to
 * `"done"` and invokes `onSaved` once. `runInAction`s its writes; early-returns on an
 * aborted signal before writing. Does not reject.
 */
export async function submitServerForm(
  draft: ServerFormDraft,
  serverId: string | null,
  onSaved: () => void,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted || draft.submitStatus === "submitting") {
    return;
  }
  if (Object.keys(serverFormClientErrors(draft)).length > 0) {
    return;
  }

  const body = payloadOf(draft);

  runInAction(() => {
    draft.submitStatus = "submitting";
    draft.serverErrors = {};
  });

  try {
    if (serverId === null) {
      await apiPost<unknown>(SERVERS_PATH, body, signal);
    } else {
      await apiPatch<unknown>(`${SERVERS_PATH}/${encodeURIComponent(serverId)}`, body, signal);
    }
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    const serverErrors = serverErrorsFor(error);
    runInAction(() => {
      draft.serverErrors = serverErrors;
      draft.submitStatus = "idle";
    });
    return;
  }

  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    draft.submitStatus = "done";
  });
  onSaved();
}
