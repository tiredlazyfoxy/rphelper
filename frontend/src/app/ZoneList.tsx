// The current zone (feature 013, step 005, D5, D10): a "Zone messages" list, one item per
// zone row in served order (keyed by message id), each with its author label, an
// "Edit message" control and the painted body. The in-place editor commits on blur through
// `editZoneMessage` and stays open with the typed text when that resolves false.
import { useState } from "react";
import type * as React from "react";
import { observer } from "mobx-react-lite";
import { Box, Button, Group, Stack, Text, Textarea } from "@mantine/core";
import { IconEdit, IconRefresh } from "@tabler/icons-react";

import { IconButton } from "../shared/IconButton";
import { AssistantBody } from "./AssistantBody";
import { LiveMessage } from "./LiveMessage";
import { MessageBody } from "./MessageBody";
import { ToolBlock } from "./ToolBlock";
import type { Message, MessageRole } from "./streamApi";
import { editZoneMessage, regenerate, showsRegenerate } from "./streamState";
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
  /**
   * Whether the row offers "Edit message" (default true). Tool rows never do; with false
   * the control is absent and the editor can never open (022 006, 021 D8).
   */
  editable?: boolean;
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
  const { state, message, signal, editable = true } = props;
  const showsEdit = editable && message.role !== "tool";
  // The body by role (022 006): assistant rows tuck their thinking away; tool rows are a
  // collapsed tool block whose summary is the stored text.
  const body =
    message.role === "assistant" ? (
      <AssistantBody text={message.text} live={false} />
    ) : message.role === "tool" ? (
      <ToolBlock
        name={message.tool_name}
        status={message.tool_status === "ok" ? "ok" : "failed"}
        args={message.tool_args ?? {}}
        summary={message.text}
        startsOpen={false}
      />
    ) : (
      <MessageBody text={message.text} variant="painted" />
    );
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
          {showsEdit ? (
            <IconButton icon={IconEdit} label="Edit message" onClick={openEditor} />
          ) : null}
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
          body
        )}
      </Stack>
    </Box>
  );
});

/**
 * Renders the session's current zone (the list only when non-empty, D5, D10), then the live
 * reply and, when `showsRegenerate`, the "Regenerate" button (022 006, D6, D8).
 */
export const ZoneList = observer(function ZoneList(
  props: ZoneListProps,
): React.JSX.Element | null {
  const { state, signal } = props;
  const zone = state.zone;

  return (
    <>
      {zone.length > 0 ? (
        <Box component="ul" aria-label="Zone messages" m={0} p={0} style={{ listStyle: "none" }}>
          {zone.map((message) => (
            <ZoneMessage key={message.id} state={state} message={message} signal={signal} />
          ))}
        </Box>
      ) : null}
      <LiveMessage state={state} />
      {showsRegenerate(state) ? (
        <Button
          variant="subtle"
          leftSection={<IconRefresh size={16} stroke={1.5} />}
          onClick={() => {
            void regenerate(state, signal);
          }}
        >
          Regenerate
        </Button>
      ) : null}
    </>
  );
});
