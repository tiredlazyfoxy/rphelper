// The page composer (feature 018, step 004, D1 / D5): `ComposerCore` alone in a
// "Start a session" region on the character page — no kind switch, no setup control. Send
// creates the session with its opening message, then router-pushes to `/sessions/<id>`
// unless the component has unmounted by then.
import type * as React from "react";
import { useEffect, useId, useRef, useState } from "react";
import { Stack, Title } from "@mantine/core";
import { observer } from "mobx-react-lite";
import { useNavigate } from "react-router-dom";

import {
  CharacterComposerState,
  canSendCharacterComposer,
  sendCharacterComposer,
  setCharacterComposerDraft,
} from "./characterComposerState";
import { ComposerCore } from "./ComposerCore";
import { firstReplyState } from "./firstReply";
import type { SessionsState } from "./sessionsState";

export type CharacterComposerProps = {
  /** The character the session is started under. Never parsed. */
  characterId: string;
  /** The workspace sessions store the started session is applied to. */
  sessions: SessionsState;
};

export const CharacterComposer = observer(function CharacterComposer(
  props: CharacterComposerProps,
): React.JSX.Element {
  const { characterId, sessions } = props;
  // Created once; the page keys this component by the character id.
  const [state] = useState(() => new CharacterComposerState(characterId));
  const navigate = useNavigate();
  const headingId = useId();

  // The send is a mutation and is never aborted; only the navigation is skipped once gone.
  const mountedRef = useRef(false);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // D5: a push, so Back returns to the character page. The id is used exactly as received.
  // fast/004 D2: the push carries the first-reply marker the session screen consumes.
  const onStarted = (sessionId: string): void => {
    if (!mountedRef.current) {
      return;
    }
    void navigate(`/sessions/${sessionId}`, { state: firstReplyState() });
  };

  // Same `Title order={3}` as the page's other section headings.
  return (
    <section aria-labelledby={headingId}>
      <Stack gap="xs">
        <Title order={3} id={headingId}>
          Start a session
        </Title>
        <ComposerCore
          draft={state.draft}
          onDraftChange={(text) => setCharacterComposerDraft(state, text)}
          sendEnabled={canSendCharacterComposer(state)}
          onSend={() => void sendCharacterComposer(state, sessions, onStarted)}
        />
      </Stack>
    </section>
  );
});
