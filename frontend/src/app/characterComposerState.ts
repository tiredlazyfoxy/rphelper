// The page composer's state (feature 018, step 004, D5): one data class holding the
// character id, the draft and the in-flight flag — observable fields only, no methods and no
// computed getters. The can-send derivation and the send effect are free functions below.
// The workspace `SessionsState` is a parameter of the send effect, never a field here, and
// navigation is reported through `onStarted`, so this module imports no router and no React.
import { makeAutoObservable, runInAction } from "mobx";

import { notifyFailure } from "../shared/notifyFailure";
import { startSessionWithMessage } from "./sessionsApi";
import type { Session } from "./sessionsApi";
import { fetchSetups } from "./setupsApi";
import type { Setup } from "./setupsApi";
import { applySession } from "./sessionsState";
import type { SessionsState } from "./sessionsState";

/** The composer's setup-choices load status (033 D8). */
export type CharacterComposerSetupsStatus = "idle" | "loading" | "ready" | "failed";

export class CharacterComposerState {
  /** The character the session is started under. Never parsed. */
  characterId: string;
  /** The opening text being typed. Starts empty. */
  draft = "";
  /** Whether a create-and-seed post is in flight. */
  sending = false;
  /** The character's working (non-archived) setups, offered beside "No setup" (D8). */
  setups: Setup[] = [];
  /** The setup-choices load status; "failed" shows the non-blocking failure line. */
  setupsStatus: CharacterComposerSetupsStatus = "idle";
  /** The chosen setup, or null for "No setup". */
  selectedSetupId: string | null = null;

  constructor(characterId: string) {
    this.characterId = characterId;
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/** Replaces the draft with the typed text. */
export function setCharacterComposerDraft(state: CharacterComposerState, text: string): void {
  runInAction(() => {
    state.draft = text;
  });
}

/** Chooses a setup, or null for "No setup". Issues no request. */
export function selectComposerSetup(state: CharacterComposerState, setupId: string | null): void {
  runInAction(() => {
    state.selectedSetupId = setupId;
  });
}

/**
 * Effect (D8): loads the character's setups via `fetchSetups(characterId, false, signal)` and
 * keeps only non-archived ones as `setups`. Sets `setupsStatus` "loading" then "ready"; a
 * selection no longer among the choices resets to null. A failure sets "failed" (previous
 * choices and selection kept). Writes nothing once aborted; never rejects.
 */
export async function loadComposerSetups(
  state: CharacterComposerState,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    state.setupsStatus = "loading";
  });

  let fetched: Setup[];
  try {
    fetched = await fetchSetups(state.characterId, false, signal);
  } catch (error) {
    if (signal?.aborted || (error instanceof Error && error.name === "AbortError")) {
      return;
    }
    // Previous choices and selection kept; sending with "No setup" still works (R2).
    runInAction(() => {
      state.setupsStatus = "failed";
    });
    return;
  }

  if (signal?.aborted) {
    return;
  }
  // Archived setups are never offered (UC-021), whatever the server answered.
  const working = fetched.filter((setup) => setup.archived_at === null);
  runInAction(() => {
    state.setups = working;
    state.setupsStatus = "ready";
    // A selection no longer among the choices falls back to "No setup" in the same action.
    const selected = state.selectedSetupId;
    if (selected !== null && !working.some((setup) => setup.id === selected)) {
      state.selectedSetupId = null;
    }
  });
}

/** Pure: the draft is not blank and nothing is sending. */
export function canSendCharacterComposer(state: CharacterComposerState): boolean {
  return state.draft.trim() !== "" && !state.sending;
}

/**
 * The send effect (D5): when sending is allowed, posts the draft once through
 * `startSessionWithMessage`, applies the started session's eight keys to `sessions`, clears
 * the draft and calls `onStarted` with the id exactly as received. On failure keeps the draft
 * and calls `notifyFailure`. Always clears sending; takes no signal; never rejects.
 */
export async function sendCharacterComposer(
  state: CharacterComposerState,
  sessions: SessionsState,
  onStarted: (sessionId: string) => void,
): Promise<void> {
  if (!canSendCharacterComposer(state)) {
    return;
  }
  runInAction(() => {
    state.sending = true;
  });
  let startedId: string;
  try {
    const started = await startSessionWithMessage(
      state.characterId,
      state.draft,
      state.selectedSetupId,
    );
    // Only the eight `Session` keys reach the store; `opening_message` is dropped (D5).
    const session: Session = {
      id: started.id,
      character_id: started.character_id,
      setup_id: started.setup_id,
      setup_name: started.setup_name,
      archived_at: started.archived_at,
      last_used_at: started.last_used_at,
      created_at: started.created_at,
      updated_at: started.updated_at,
    };
    applySession(sessions, session);
    runInAction(() => {
      state.draft = "";
      state.sending = false;
    });
    startedId = started.id;
  } catch (error) {
    runInAction(() => {
      state.sending = false;
    });
    notifyFailure(error);
    return;
  }
  // Outside the try: a navigation failure is not a send failure.
  onStarted(startedId);
}
