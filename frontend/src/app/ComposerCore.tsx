// The shared composer core (feature 018, step 003, D4): the presentational composer both
// hosts render. It owns the auto-growing "Composer" text area, the stream-column geometry,
// the labelled "Send", 014's enormous-paste warning and 017's optional send-blocked reason.
// It holds no MobX state, makes no request and knows nothing of sessions, kinds or routes.
import type * as React from "react";
import { Box, Button, Group, Stack, Text, Textarea } from "@mantine/core";

import { notifyWarning } from "../shared/notifyWarning";
import { isEnormousPaste } from "./pasteCost";

export type ComposerCoreProps = {
  /** The draft text shown in the text area. */
  draft: string;
  /** Called with the new text on every edit of the text area. */
  onDraftChange: (text: string) => void;
  /** Called once per press of "Send". */
  onSend: () => void;
  /** Whether "Send" is enabled (before the send-blocked reason is applied). */
  sendEnabled: boolean;
  /**
   * 017 D17: when non-null, "Send" is disabled whatever `sendEnabled` says and this sentence
   * is shown. Defaults to null.
   */
  sendBlockedReason?: string | null;
  /**
   * Called with the pasted plain text and the paste event, after the core's own paste
   * handling (the enormous-paste warning). The core never prevents the default; a host that
   * wants to stop the insertion calls `event.preventDefault()` here.
   */
  onPaste?: (text: string, event: React.ClipboardEvent<HTMLTextAreaElement>) => void;
  /** Rendered under the text area. */
  underArea?: React.ReactNode;
  /**
   * 019 004: when not undefined, rendered in place of the "Send" button (which is then absent,
   * so `sendEnabled` and `onSend` are not consulted). The send-blocked reason text still
   * follows `sendBlockedReason`. Defaults to undefined: "Send" renders as before.
   */
  sendSlot?: React.ReactNode;
  /** Rendered in the button row, after "Send". */
  besideSend?: React.ReactNode;
};

/** The shared presentational composer (D4). */
export function ComposerCore(props: ComposerCoreProps): React.JSX.Element {
  const {
    draft,
    onDraftChange,
    onSend,
    sendEnabled,
    sendBlockedReason = null,
    onPaste,
    underArea,
    sendSlot,
    besideSend,
  } = props;

  function handlePaste(event: React.ClipboardEvent<HTMLTextAreaElement>): void {
    const text = event.clipboardData?.getData("text/plain") ?? "";
    // An enormous paste warns first, synchronously and fire-and-forget (014 D5); never blocks.
    if (text.trim() !== "" && isEnormousPaste(text)) {
      notifyWarning("paste-context-cost");
    }
    // The host's hook runs second; the core itself never prevents the default.
    onPaste?.(text, event);
  }

  return (
    <Box maw={720} mx="auto" px={18} w="100%">
      <Stack gap="xs">
        <Textarea
          aria-label="Composer"
          autosize
          minRows={2}
          value={draft}
          onChange={(event) => {
            onDraftChange(event.currentTarget.value);
          }}
          onPaste={handlePaste}
        />
        {underArea}
        <Group gap="xs" justify="flex-end">
          {sendBlockedReason !== null ? (
            <Text size="sm" c="dimmed">
              {sendBlockedReason}
            </Text>
          ) : null}
          {sendSlot !== undefined ? (
            sendSlot
          ) : (
            <Button
              variant="default"
              disabled={!sendEnabled || sendBlockedReason !== null}
              onClick={() => {
                onSend();
              }}
            >
              Send
            </Button>
          )}
          {besideSend}
        </Group>
      </Stack>
    </Box>
  );
}
