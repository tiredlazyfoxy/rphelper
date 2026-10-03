// The composer (feature 013, step 006, D1, D2, D3, D6, D7, D9): the auto-growing "Composer"
// text area, the settle preview line, "Send" and "Settle", partner-paste filing, and the
// "Discard empty zone" control present only for an empty zone with a blank composer.
import type * as React from "react";
import { observer } from "mobx-react-lite";
import { Box, Button, Group, Stack, Text, Textarea } from "@mantine/core";
import { IconX } from "@tabler/icons-react";

import { IconButton } from "../shared/IconButton";
import { notifyWarning } from "../shared/notifyWarning";
import type { SettlePreview } from "./parens";
import { isEnormousPaste } from "./pasteCost";
import {
  canSend,
  canSettle,
  discardZone,
  effectiveKind,
  filePastedPartner,
  isBlank,
  sendComposer,
  setDraft,
  settleComposer,
  settlePreviewOf,
  showsDiscard,
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
  const blockedReason =
    sendBlockedReason !== null && effectiveKind(state) === "turn" ? sendBlockedReason : null;

  function handlePaste(event: React.ClipboardEvent<HTMLTextAreaElement>): void {
    // Read for both positions now; guarded so a paste event without clipboard data on
    // *my turn* still behaves exactly as before.
    const text = event.clipboardData?.getData("text/plain") ?? "";
    // An enormous paste warns in both positions, fire-and-forget (014 D5); never blocks.
    if (!isBlank(text) && isEnormousPaste(text)) {
      notifyWarning("paste-context-cost");
    }
    // The position is read at paste time (D7); *my turn* pastes behave normally.
    if (effectiveKind(state) !== "partner") {
      return;
    }
    event.preventDefault();
    void filePastedPartner(state, text, signal);
  }

  return (
    <Box maw={720} mx="auto" px={18} w="100%">
      <Stack gap="xs">
        <Textarea
          aria-label="Composer"
          autosize
          minRows={2}
          value={state.draft}
          onChange={(event) => {
            setDraft(state, event.currentTarget.value);
          }}
          onPaste={handlePaste}
        />
        {preview !== null ? (
          <Text size="sm" c="dimmed">
            {previewSentence(preview)}
          </Text>
        ) : null}
        <Group gap="xs" justify="flex-end">
          {blockedReason !== null ? (
            <Text size="sm" c="dimmed">
              {blockedReason}
            </Text>
          ) : null}
          {showsDiscard(state) ? (
            <IconButton
              icon={IconX}
              label="Discard empty zone"
              onClick={() => {
                discardZone(state);
              }}
            />
          ) : null}
          <Button
            variant="default"
            disabled={!canSend(state) || blockedReason !== null}
            onClick={() => {
              void sendComposer(state, signal);
            }}
          >
            Send
          </Button>
          <Button
            variant="filled"
            disabled={!canSettle(state)}
            onClick={() => {
              void settleComposer(state, signal);
            }}
          >
            Settle
          </Button>
        </Group>
      </Stack>
    </Box>
  );
});
