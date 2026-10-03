// The composer (feature 013, step 006, D1, D2, D3, D6, D7, D9): the auto-growing "Composer"
// text area, the settle preview line, "Send" and "Settle", partner-paste filing, and the
// "Discard empty zone" control present only for an empty zone with a blank composer.
// 018 D4: rendered on the shared `ComposerCore`, which owns the text area, "Send", the
// enormous-paste warning and the send-blocked reason; this host adds only the stream pieces.
import type * as React from "react";
import { observer } from "mobx-react-lite";
import { Button, Text } from "@mantine/core";
import { IconPlayerStop, IconX } from "@tabler/icons-react";

import { IconButton } from "../shared/IconButton";
import { ComposerCore } from "./ComposerCore";
import type { SettlePreview } from "./parens";
import {
  canSend,
  canSettle,
  discardZone,
  effectiveKind,
  filePastedPartner,
  isStreaming,
  sendComposer,
  setDraft,
  settleComposer,
  settlePreviewOf,
  showsDiscard,
  stopCompose,
} from "./streamState";
import type { StreamState } from "./streamState";

export type ComposerProps = {
  state: StreamState;
  /** Passed on to `sendComposer`, `filePastedPartner` and `settleComposer`. */
  signal?: AbortSignal;
  /**
   * 017 D17: when non-null on *my turn*, Send is disabled and this sentence is shown.
   * Ignored on *partner*. Defaults to null.
   */
  sendBlockedReason?: string | null;
};

/** The fixed preview sentence for a settle preview (D1). */
function previewSentence(preview: SettlePreview): string {
  if (preview.kind === "decision") {
    return "Settles as a decision (out of character).";
  }
  return preview.strips
    ? "Settles as a turn; the (( )) instructions will be removed."
    : "Settles as a turn.";
}

/** The composer under the zone (D1, D2, D3, D6, D7, D9). */
export const Composer = observer(function Composer(
  props: ComposerProps,
): React.JSX.Element {
  const { state, signal, sendBlockedReason = null } = props;
  const preview = settlePreviewOf(state);
  // 017 D17: on *my turn* a non-null reason disables Send and is shown; Settle is never gated.
  const streaming = isStreaming(state);
  // 019 D13: while streaming, Stop holds Send's slot; 017's reason gates Send only, never Stop.
  const blockedReason =
    !streaming && sendBlockedReason !== null && effectiveKind(state) === "turn"
      ? sendBlockedReason
      : null;
  const sendSlot = streaming ? (
    <IconButton
      icon={IconPlayerStop}
      label="Stop"
      sizeVariant="main"
      onClick={() => {
        stopCompose(state);
      }}
    />
  ) : undefined;

  function handlePaste(text: string, event: React.ClipboardEvent<HTMLTextAreaElement>): void {
    // The position is read at paste time (D7); *my turn* pastes behave normally.
    if (effectiveKind(state) !== "partner") {
      return;
    }
    event.preventDefault();
    void filePastedPartner(state, text, signal);
  }

  return (
    <ComposerCore
      draft={state.draft}
      onDraftChange={(text) => {
        setDraft(state, text);
      }}
      sendEnabled={canSend(state)}
      onSend={() => {
        void sendComposer(state, signal);
      }}
      sendBlockedReason={blockedReason}
      sendSlot={sendSlot}
      onPaste={handlePaste}
      underArea={
        preview !== null ? (
          <Text size="sm" c="dimmed">
            {previewSentence(preview)}
          </Text>
        ) : null
      }
      besideSend={
        <>
          <Button
            variant="filled"
            disabled={!canSettle(state)}
            onClick={() => {
              void settleComposer(state, signal);
            }}
          >
            Settle
          </Button>
          {showsDiscard(state) ? (
            <IconButton
              icon={IconX}
              label="Discard empty zone"
              onClick={() => {
                discardZone(state);
              }}
            />
          ) : null}
        </>
      }
    />
  );
});
