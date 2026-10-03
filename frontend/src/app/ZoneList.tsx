// The current zone (feature 013, step 005, D5, D10): a "Zone messages" list, one item per
// zone row in served order (keyed by message id), each with its author label, an
// "Edit message" control and the painted body. The in-place editor commits on blur through
// `editZoneMessage` and stays open with the typed text when that resolves false.
import { useState } from "react";
import type * as React from "react";
import { observer } from "mobx-react-lite";
import { Box, Group, Stack, Text, Textarea } from "@mantine/core";
import { IconEdit } from "@tabler/icons-react";

import { IconButton } from "../shared/IconButton";
import { MessageBody } from "./MessageBody";
import type { Message, MessageRole } from "./streamApi";
import { editZoneMessage } from "./streamState";
import type { StreamState } from "./streamState";

export type ZoneListProps = {
  state: StreamState;
  /** Passed on to `editZoneMessage`. */
  signal?: AbortSignal;
};

export type ZoneMessageProps = {
  state: StreamState;
  /** The zone row this item renders. */
  message: Message;
  /** Passed on to `editZoneMessage`. */
  signal?: AbortSignal;
};

const AUTHOR_LABELS: Record<MessageRole, string> = {
  user: "You",
  assistant: "Assistant",
  tool: "Tool",
};

/** One zone row: author label, "Edit message" control, painted body or in-place editor (D10). */
export const ZoneMessage = observer(function ZoneMessage(
  props: ZoneMessageProps,
): React.JSX.Element {
  const { state, message, signal } = props;
  // View state (D10): whether this row's editor is open, and its draft.
  const [editing, setEditing] = useState(false);
  const [editDraft, setEditDraft] = useState("");

  function openEditor(): void {
    if (editing) {
      return; // an open editor keeps its typed text (R10)
    }
    setEditDraft(message.text);
    setEditing(true);
  }

  function commit(): void {
    const text = editDraft;
    void editZoneMessage(state, message.id, text, signal).then((mayClose) => {
      if (mayClose) {
        setEditing(false);
      }
    });
  }

  return (
    <Box component="li" mb="md">
      <Stack gap="xs">
        <Group gap="xs" justify="space-between" wrap="nowrap">
          <Text size="sm" fw={600} c="dimmed">
            {AUTHOR_LABELS[message.role]}
          </Text>
          <IconButton icon={IconEdit} label="Edit message" onClick={openEditor} />
        </Group>
        {editing ? (
          <Textarea
            aria-label="Edit message text"
            autosize
            autoFocus
            value={editDraft}
            onChange={(event) => {
              setEditDraft(event.currentTarget.value);
            }}
            onBlur={commit}
          />
        ) : (
          <MessageBody text={message.text} variant="painted" />
        )}
      </Stack>
    </Box>
  );
});

/** Renders the session's current zone; renders nothing when the zone is empty (D5, D10). */
export const ZoneList = observer(function ZoneList(
  props: ZoneListProps,
): React.JSX.Element | null {
  const { state, signal } = props;
  const zone = state.zone;
  if (zone.length === 0) {
    return null;
  }

  return (
    <Box component="ul" aria-label="Zone messages" m={0} p={0} style={{ listStyle: "none" }}>
      {zone.map((message) => (
        <ZoneMessage key={message.id} state={state} message={message} signal={signal} />
      ))}
    </Box>
  );
});
