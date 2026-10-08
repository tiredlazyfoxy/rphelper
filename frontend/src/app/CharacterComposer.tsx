// The page composer (feature 018, step 004, D1 / D5; 033 D8): `ComposerCore` in a
// "New session" region on the character page, with a small optional "Setup" select under
// the text area — no kind switch. Send creates the session with its opening message (and the
// chosen setup, if any), then router-pushes to `/sessions/<id>` unless the component has
// unmounted by then.
import type * as React from "react";
import { useEffect, useId, useRef, useState } from "react";
import { Group, Select, Stack, Text, Title } from "@mantine/core";
import { observer } from "mobx-react-lite";
import { useNavigate } from "react-router-dom";

import {
  CharacterComposerState,
  canSendCharacterComposer,
  loadComposerSetups,
  selectComposerSetup,
  sendCharacterComposer,
  setCharacterComposerDraft,
} from "./characterComposerState";
import { ComposerCore } from "./ComposerCore";
import { firstReplyState } from "./firstReply";
import type { SessionsState } from "./sessionsState";

/**
 * The "No setup" option's fixed value. Mantine's `Select` speaks strings and treats `null` as
 * "nothing selected", so the neutral choice needs a value of its own; it is mapped to `null`
 * before it reaches `selectComposerSetup` and never reaches the wire.
 */
const NO_SETUP_VALUE = "none";

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

  // D8: the setup choices load once on mount and again on each dropdown open; a new load
  // aborts the previous one, so the latest opening wins. Aborted on unmount.
  const setupsControllerRef = useRef<AbortController | null>(null);
  const reloadSetups = (): void => {
    setupsControllerRef.current?.abort();
    const controller = new AbortController();
    setupsControllerRef.current = controller;
    void loadComposerSetups(state, controller.signal);
  };
  useEffect(() => {
    reloadSetups();
    return () => {
      setupsControllerRef.current?.abort();
      setupsControllerRef.current = null;
    };
  }, [state]);

  const setupOptions = [
    { value: NO_SETUP_VALUE, label: "No setup" },
    ...state.setups.map((setup) => ({ value: setup.id, label: setup.name })),
  ];

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
          New session
        </Title>
        <ComposerCore
          draft={state.draft}
          onDraftChange={(text) => setCharacterComposerDraft(state, text)}
          sendEnabled={canSendCharacterComposer(state)}
          onSend={() => void sendCharacterComposer(state, sessions, onStarted)}
          fullWidth
          minRows={10}
          underArea={
            <Group gap="xs" align="flex-end">
              <Select
                label="Setup"
                size="xs"
                data={setupOptions}
                // The field can never be emptied: always a setup id or "No setup".
                allowDeselect={false}
                value={state.selectedSetupId ?? NO_SETUP_VALUE}
                onChange={(value) => {
                  selectComposerSetup(
                    state,
                    value === null || value === NO_SETUP_VALUE ? null : value,
                  );
                }}
                // A setup just created in the Setups tab is choosable without a remount.
                onDropdownOpen={reloadSetups}
                disabled={state.sending}
              />
              {/* Non-blocking: sending with "No setup" still works (R2). */}
              {state.setupsStatus === "failed" && (
                <Text size="xs" c="dimmed">
                  Could not load setups to choose from.
                </Text>
              )}
            </Group>
          }
        />
      </Stack>
    </section>
  );
});
