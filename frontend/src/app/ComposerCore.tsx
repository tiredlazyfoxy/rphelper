// The shared composer core (feature 018, step 003, D4): the presentational composer both
// hosts render. It owns the vertically resizable "Composer" text area, the stream-column
// geometry, the in-box icon "Send" (and Ctrl/Cmd+Enter), 014's enormous-paste warning and 017's optional send-blocked reason.
// It holds no MobX state, makes no request and knows nothing of sessions, kinds or routes.
import type * as React from "react";
import { Box, Group, Stack, Text, Textarea } from "@mantine/core";
import { IconSend } from "@tabler/icons-react";

import { IconButton } from "../shared/IconButton";
import { notifyWarning } from "../shared/notifyWarning";
import { isEnormousPaste } from "./pasteCost";

export type ComposerCoreProps = {
  /** The draft text shown in the text area. */
  draft: string;
  /** Called with the new text on every edit of the text area. */
  onDraftChange: (text: string) => void;
  /** Called once per press of "Send" (or Ctrl/Cmd+Enter while "Send" is enabled). */
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
  /** Rendered in the row under the text area, after the send-blocked reason. */
  besideSend?: React.ReactNode;
  /**
   * Fast 011: when true, the composer fills its container — no 720px max-width cap and no
   * side padding. Defaults to false: the centred 720px / 18px-padded stream column.
   */
  fullWidth?: boolean;
  /**
   * Fast 011: the text box's starting height in lines (native `rows`) and the minimum it can
   * be dragged down to. Defaults to 2.
   */
  minRows?: number;
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
    fullWidth = false,
    minRows = 2,
  } = props;

  const sendDisabled = !sendEnabled || sendBlockedReason !== null;

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key !== "Enter" || !(event.ctrlKey || event.metaKey)) return;
    // An IME composition owns Enter; the combo is ignored entirely while one is in progress.
    if (event.nativeEvent.isComposing) return;
    event.preventDefault();
    if (!sendDisabled && sendSlot === undefined) {
      onSend();
    }
  }

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
    <Box
      maw={fullWidth ? undefined : 720}
      mx={fullWidth ? undefined : "auto"}
      px={fullWidth ? undefined : 18}
      w="100%"
    >
      <Stack gap="xs">
        <Textarea
          aria-label="Composer"
          rows={minRows}
          resize="vertical"
          value={draft}
          onChange={(event) => {
            onDraftChange(event.currentTarget.value);
          }}
          onPaste={handlePaste}
          onKeyDown={handleKeyDown}
          rightSectionWidth={40}
          rightSectionPointerEvents="all"
          rightSection={
            sendSlot !== undefined ? (
              sendSlot
            ) : (
              <IconButton
                icon={IconSend}
                label="Send"
                sizeVariant="main"
                disabled={sendDisabled}
                onClick={() => {
                  onSend();
                }}
              />
            )
          }
          styles={{
            input: {
              minHeight: `calc(${minRows}lh + 2 * var(--input-padding-y, 0px) + 2px)`,
            },
            section: {
              alignItems: "flex-end",
              paddingBottom: 6,
            },
          }}
        />
        {underArea}
        <Group gap="xs" justify="flex-end">
          {sendBlockedReason !== null ? (
            <Text size="sm" c="dimmed">
              {sendBlockedReason}
            </Text>
          ) : null}
          {besideSend}
        </Group>
      </Stack>
    </Box>
  );
}
