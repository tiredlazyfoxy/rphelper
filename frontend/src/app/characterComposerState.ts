// The page composer's state (feature 018, step 004, D5): one data class holding the
// character id, the draft and the in-flight flag — observable fields only, no methods and no
// computed getters. The can-send derivation and the send effect are free functions below.
// The workspace `SessionsState` is a parameter of the send effect, never a field here, and
// navigation is reported through `onStarted`, so this module imports no router and no React.
import { makeAutoObservable, runInAction } from "mobx";

import { notifyFailure } from "../shared/notifyFailure";
import { startSessionWithMessage } from "./sessionsApi";
import type { Session } from "./sessionsApi";
import { applySession } from "./sessionsState";
import type { SessionsState } from "./sessionsState";

export class CharacterComposerState {
  /** The character the session is started under. Never parsed. */
  characterId: string;
  /** The opening text being typed. Starts empty. */
  draft = "";
  /** Whether a create-and-seed post is in flight. */
  sending = false;

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
    const started = await startSessionWithMessage(state.characterId, state.draft);
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
