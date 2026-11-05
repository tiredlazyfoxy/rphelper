// The current zone (feature 013, step 005, D5, D10): a "Zone messages" list, one item per
// zone row in served order (keyed by message id), each with its author label, an
// "Edit message" control and the painted body. The in-place editor commits on blur through
// `editZoneMessage` and stays open with the typed text when that resolves false.
//
// Fast feature 014 (P7, P8): an editable non-tool row also offers "Delete message" (hidden
// while its editor is open, disabled while busy or composing), which deletes the row after a
// `ConfirmModal`; a blank editor commit deletes with no confirm.
//
// Fast feature 016: the roleplayer's own (user) body renders in Mantine's dimmed tone.
import { useState } from "react";
import type * as React from "react";
import { observer } from "mobx-react-lite";
import { Box, Button, Group, Stack, Text, Textarea } from "@mantine/core";
import { IconEdit, IconRefresh, IconTrash } from "@tabler/icons-react";

import { ConfirmModal } from "../shared/ConfirmModal";
import { IconButton } from "../shared/IconButton";
import { AssistantBody } from "./AssistantBody";
import { LiveMessage } from "./LiveMessage";
import { MessageBody } from "./MessageBody";
import { ToolBlock } from "./ToolBlock";
import type { Message, MessageRole } from "./streamApi";
import { deleteZoneMessage, editZoneMessage, isStreaming, regenerate, showsRegenerate } from "./streamState";
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
   * Whether the row offers "Edit message" and "Delete message" (default true). Tool rows never
   * do; with false both controls are absent and the editor can never open (022 006, 021 D8,
   * fast 014 P1).
   */
  editable?: boolean;
};

const AUTHOR_LABELS: Record<MessageRole, string> = {
  user: "You",
  assistant: "Assistant",
  tool: "Tool",
};

/**
 * One zone row: author label, "Edit message" and "Delete message" controls, painted body or
 * in-place editor (D10, fast 014). The delete opens a confirm dialog whose confirm runs
 * `deleteZoneMessage`.
 */
export const ZoneMessage = observer(function ZoneMessage(
  props: ZoneMessageProps,
): React.JSX.Element {
  const { state, message, signal, editable = true } = props;
  const showsEdit = editable && message.role !== "tool";
  // The body by role (022 006): assistant rows tuck their thinking away; tool rows are a
  // collapsed tool block whose summary is the stored text. The roleplayer's own (user) body
  // sits in one theme-aware dimmed wrapper so it reads apart from the assistant's rows; the
  // colour inherits into the prose while fragment chips and OOC cards keep their own
  // (DEC-F016-2, DEC-F016-3). `data-tone="muted"` is the test hook (DEC-F016-4); the edit
  // Textarea replaces `body`, so it never sits inside the wrapper.
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
      <Box c="dimmed" data-tone="muted">
        <MessageBody text={message.text} variant="painted" />
      </Box>
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

  // Fast 014 P8: whether the delete confirm is open, and whether its delete is in flight.
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  /**
   * Fast 014 P8: runs the confirmed delete with the modal loading, then closes the modal
   * whatever the result (`deleteZoneMessage` never rejects and notifies its own failures). On
   * success the row leaves `state.zone` and this item unmounts with it.
   */
  function confirmDelete(): void {
    setDeleting(true);
    void deleteZoneMessage(state, message.id, signal).then(() => {
      setDeleting(false);
      setConfirmingDelete(false);
    });
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
            <Group gap={4} wrap="nowrap">
              <IconButton icon={IconEdit} label="Edit message" onClick={openEditor} />
              {editing ? null : (
                <IconButton
                  icon={IconTrash}
                  label="Delete message"
                  // Fast 014 P7: compose does not set `busy`, so streaming is checked too; this
                  // keeps compose's finalisation re-read from racing the delete.
                  disabled={state.busy || isStreaming(state)}
                  onClick={() => {
                    setConfirmingDelete(true);
                  }}
                />
              )}
            </Group>
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
      {showsEdit ? (
        <ConfirmModal
          opened={confirmingDelete}
          title="Delete message?"
          consequence="The message is removed for good."
          confirmLabel="Delete"
          confirmColor="red"
          loading={deleting}
          onCancel={() => {
            setConfirmingDelete(false);
          }}
          onConfirm={confirmDelete}
        />
      ) : null}
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
