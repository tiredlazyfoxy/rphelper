// The session configuration modal's draft (feature 017, step 009, D18 / D6 / D19): one data
// class seeded from a loaded `SessionConfiguration` — observable fields only, no methods and
// no computed getters — holding an Inherit / Set (or Inherit / On / Off) choice and text per
// setting. The pure derivations and the one submit effect are the free functions below, each
// taking the draft as its first argument. Shape follows `src/admin/createUserDraft.ts`
// (`serverErrors` map with a `general` key, merged with the client errors). The draft never
// carries the model: the header picker is its one control.

import { makeAutoObservable, runInAction } from "mobx";
import { updateSessionConfiguration } from "./configurationApi";
import type { SessionConfiguration, SessionConfigurationPatch, Setting } from "./configurationApi";

/** A text setting's choice: inherit the level below, or set a session override. */
export type TextSource = "inherit" | "set";

/** A tool setting's choice: inherit the level below, or override on / off. */
export type ToolChoice = "inherit" | "on" | "off";

/** The client-validated fields — the keys of the client-error map. */
export type SessionConfigField = "systemPrompt" | "rpLanguage" | "preferredLanguage";

/** Field-keyed client errors; a key is present only when that field is invalid. */
export type SessionConfigClientErrors = Partial<Record<SessionConfigField, string>>;

/** Keys of the server-error map: the three fields plus the general catch-all. */
export type SessionConfigServerErrorKey = SessionConfigField | "general";

/** Server errors; every save failure lands on `general` (D19). */
export type SessionConfigServerErrors = Partial<Record<SessionConfigServerErrorKey, string>>;

/** The merged view the modal renders: client errors plus server errors. */
export type SessionConfigErrors = Partial<Record<SessionConfigServerErrorKey, string>>;

/** Whether a submit is idle, in flight, or has succeeded. */
export type SessionConfigSubmitStatus = "idle" | "submitting" | "done";

const SYSTEM_PROMPT_REQUIRED = "Enter a system prompt, or choose Inherit.";
const LANGUAGE_REQUIRED = "Enter a language, or choose Inherit.";
const SAVE_FAILED = "Could not save the session configuration.";

function sourceOf(setting: Setting<string>): TextSource {
  return setting.session !== null ? "set" : "inherit";
}

function textOf(setting: Setting<string>): string {
  return setting.session ?? setting.inherited ?? "";
}

function toolChoiceOf(setting: Setting<boolean>): ToolChoice {
  if (setting.session === null) {
    return "inherit";
  }
  return setting.session ? "on" : "off";
}

function toolOverride(choice: ToolChoice): boolean | null {
  if (choice === "inherit") {
    return null;
  }
  return choice === "on";
}

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

export class SessionConfigDraft {
  /** The session the configuration belongs to. A string, never parsed. */
  readonly sessionId: string;
  /** The loaded configuration the draft was seeded from. Never reassigned. */
  readonly original: SessionConfiguration;
  systemPromptSource: TextSource;
  systemPrompt: string;
  rpLanguageSource: TextSource;
  rpLanguage: string;
  preferredLanguageSource: TextSource;
  preferredLanguage: string;
  toolMemoSearch: ToolChoice;
  toolSessionSearch: ToolChoice;
  toolWebSearch: ToolChoice;
  serverErrors: SessionConfigServerErrors = {};
  submitStatus: SessionConfigSubmitStatus = "idle";

  constructor(sessionId: string, configuration: SessionConfiguration) {
    this.sessionId = sessionId;
    this.original = configuration;
    this.systemPromptSource = sourceOf(configuration.system_prompt);
    this.systemPrompt = textOf(configuration.system_prompt);
    this.rpLanguageSource = sourceOf(configuration.rp_language);
    this.rpLanguage = textOf(configuration.rp_language);
    this.preferredLanguageSource = sourceOf(configuration.preferred_language);
    this.preferredLanguage = textOf(configuration.preferred_language);
    this.toolMemoSearch = toolChoiceOf(configuration.tool_memo_search);
    this.toolSessionSearch = toolChoiceOf(configuration.tool_session_search);
    this.toolWebSearch = toolChoiceOf(configuration.tool_web_search);
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/**
 * Pure: the field-keyed client errors (empty object when valid). A text setting on "set"
 * with blank text gets its fixed sentence.
 */
export function clientErrors(draft: SessionConfigDraft): SessionConfigClientErrors {
  const result: SessionConfigClientErrors = {};
  if (draft.systemPromptSource === "set" && draft.systemPrompt.trim().length === 0) {
    result.systemPrompt = SYSTEM_PROMPT_REQUIRED;
  }
  if (draft.rpLanguageSource === "set" && draft.rpLanguage.trim().length === 0) {
    result.rpLanguage = LANGUAGE_REQUIRED;
  }
  if (draft.preferredLanguageSource === "set" && draft.preferredLanguage.trim().length === 0) {
    result.preferredLanguage = LANGUAGE_REQUIRED;
  }
  return result;
}

/** Pure: the merged view of client errors and `draft.serverErrors`. */
export function errors(draft: SessionConfigDraft): SessionConfigErrors {
  return { ...draft.serverErrors, ...clientErrors(draft) };
}

/** Pure: true only when there are no client errors and no submit is in flight. */
export function canSubmit(draft: SessionConfigDraft): boolean {
  if (draft.submitStatus === "submitting") {
    return false;
  }
  return Object.keys(clientErrors(draft)).length === 0;
}

/**
 * Pure: the patch holding only the settings whose resulting session override differs from
 * `original`'s `session`. Never a `model` key.
 */
export function patchOf(draft: SessionConfigDraft): SessionConfigurationPatch {
  const original = draft.original;
  const patch: SessionConfigurationPatch = {};

  const systemPrompt = draft.systemPromptSource === "set" ? draft.systemPrompt : null;
  if (systemPrompt !== original.system_prompt.session) {
    patch.system_prompt = systemPrompt;
  }
  const rpLanguage = draft.rpLanguageSource === "set" ? draft.rpLanguage.trim() : null;
  if (rpLanguage !== original.rp_language.session) {
    patch.rp_language = rpLanguage;
  }
  const preferredLanguage =
    draft.preferredLanguageSource === "set" ? draft.preferredLanguage.trim() : null;
  if (preferredLanguage !== original.preferred_language.session) {
    patch.preferred_language = preferredLanguage;
  }

  const memoSearch = toolOverride(draft.toolMemoSearch);
  if (memoSearch !== original.tool_memo_search.session) {
    patch.tool_memo_search = memoSearch;
  }
  const sessionSearch = toolOverride(draft.toolSessionSearch);
  if (sessionSearch !== original.tool_session_search.session) {
    patch.tool_session_search = sessionSearch;
  }
  const webSearch = toolOverride(draft.toolWebSearch);
  if (webSearch !== original.tool_web_search.session) {
    patch.tool_web_search = webSearch;
  }
  return patch;
}

/**
 * Effect: does nothing unless `canSubmit`. An empty patch calls `onSaved(original)` with no
 * request; otherwise PATCHes the session configuration. On success "done" and
 * `onSaved(response)`; on any failure the general sentence and back to "idle". Never
 * rejects.
 */
export async function submitSessionConfig(
  draft: SessionConfigDraft,
  onSaved: (saved: SessionConfiguration) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted || !canSubmit(draft)) {
    return;
  }

  const patch = patchOf(draft);
  if (Object.keys(patch).length === 0) {
    onSaved(draft.original);
    return;
  }

  runInAction(() => {
    draft.submitStatus = "submitting";
    draft.serverErrors = {};
  });

  let saved: SessionConfiguration;
  try {
    saved = await updateSessionConfiguration(draft.sessionId, patch, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    runInAction(() => {
      draft.serverErrors = { general: SAVE_FAILED };
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
  onSaved(saved);
}
