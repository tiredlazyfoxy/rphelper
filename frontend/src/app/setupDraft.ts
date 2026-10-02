// The setup modal's draft (feature 010, step 005, D2 / D12): one data class holding the
// parent character id, the row being edited (or null for create), the two typed fields, the
// submit status and the one inline failure sentence — observable fields only, no methods and
// no computed getters. The three pure derivations, the one submit effect and the two field
// setters are the free functions below, each taking the draft as its first argument.
// Shape follows `src/admin/createUserDraft.ts`, with one deliberate narrowing
// (`005.context.md`): a single `error` string, not `serverErrors` / `clientErrors` maps. The
// only field that can fail validation is the name, the client already guards it, and a 422
// carries no useful prose; the modal's inline `Alert` is the general-key render.
import { makeAutoObservable, runInAction } from "mobx";

import type { Setup } from "./setupsApi";
import { createSetup, updateSetup } from "./setupsApi";

/** Whether a submit is in flight. */
export type SetupSubmitStatus = "idle" | "submitting";

export class SetupDraft {
  /** The character the setup belongs to. A string, never parsed. */
  characterId: string;
  /** The row being edited, or null in create mode. Never reassigned. */
  original: Setup | null;
  name: string;
  description: string;
  submitStatus: SetupSubmitStatus = "idle";
  /** The inline submit-failure sentence the modal renders as given, or null (D12). */
  error: string | null = null;

  constructor(characterId: string, setup: Setup | null) {
    this.characterId = characterId;
    this.original = setup;
    this.name = setup === null ? "" : setup.name;
    this.description = setup === null ? "" : setup.description;
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/** The two fixed submit sentences (D12): one per action, never composed from an error. */
const CREATE_FAILED = "Could not create the setup.";
const SAVE_FAILED = "Could not save the setup.";

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/** Pure: true when the draft edits an existing setup (`original` is non-null). */
export function isEditing(draft: SetupDraft): boolean {
  return draft.original !== null;
}

/**
 * Pure: in edit mode, true when `name` or `description` differs from the original's; in
 * create mode, always true.
 */
export function isDirty(draft: SetupDraft): boolean {
  const original = draft.original;
  if (original === null) {
    return true;
  }
  return draft.name !== original.name || draft.description !== original.description;
}

/**
 * Pure: true when the trimmed `name` is non-empty, nothing is submitting, and the draft is
 * dirty.
 */
export function canSubmit(draft: SetupDraft): boolean {
  if (draft.name.trim().length === 0) {
    return false;
  }
  if (draft.submitStatus === "submitting") {
    return false;
  }
  return isDirty(draft);
}

/**
 * Effect: clears `error`, sets "submitting", then creates (POST under the draft's character)
 * or saves (PATCH of the original's id, sending `name` and `description` together). On
 * success calls `onSaved` once with the server's returned row — it does not close the modal.
 * On failure sets `error` to the step's fixed sentence and keeps the typed values. Either
 * way returns to "idle". Writes nothing once aborted; never rejects. The name is sent as
 * typed; the server strips it (D8).
 */
export async function submitSetup(
  draft: SetupDraft,
  onSaved: (saved: Setup) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted || draft.submitStatus === "submitting") {
    return;
  }

  // Snapshotted before the first write, so no later edit can change what is sent.
  const original = draft.original;
  const characterId = draft.characterId;
  const name = draft.name;
  const description = draft.description;
  const failureMessage = original === null ? CREATE_FAILED : SAVE_FAILED;

  runInAction(() => {
    draft.submitStatus = "submitting";
    draft.error = null;
  });

  let saved: Setup;
  try {
    saved =
      original === null
        ? await createSetup(characterId, { name, description }, signal)
        : await updateSetup(original.id, { name, description }, signal);
    if (signal?.aborted) {
      return;
    }
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    runInAction(() => {
      draft.error = failureMessage;
    });
    return;
  } finally {
    if (!signal?.aborted) {
      runInAction(() => {
        draft.submitStatus = "idle";
      });
    }
  }

  onSaved(saved);
}

/** Action: write the draft's name. Exists so the modal never calls `runInAction` itself. */
export function setDraftName(draft: SetupDraft, value: string): void {
  runInAction(() => {
    draft.name = value;
  });
}

/** Action: write the draft's description. Same reason as `setDraftName`. */
export function setDraftDescription(draft: SetupDraft, value: string): void {
  runInAction(() => {
    draft.description = value;
  });
}
