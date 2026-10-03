// The settled record (feature 013, step 004, D4, D11; extended by 014 step 005, D6, D7, D10):
// a "Settled record" list, one item per entry with its kind label, an actions group and its
// body. The actions group — "Edit entry" on every kind, "Copy as plain text" on turns only,
// and "Re-open last entry" on the last item when `showsReopen` holds — is always rendered and
// revealed by opacity while the entry is hovered, has focus within, or the device cannot
// hover. "Edit entry" swaps the body for an in-place editor that commits on blur.
import { useState } from "react";
import type * as React from "react";
import { observer } from "mobx-react-lite";
import { Blockquote, Box, Group, Stack, Text, Textarea } from "@mantine/core";
import { useFocusWithin, useHover, useMediaQuery, useMergedRef } from "@mantine/hooks";
import { IconArrowBackUp, IconCopy, IconEdit } from "@tabler/icons-react";

import { IconButton } from "../shared/IconButton";
import { copyAsPlainText } from "./copyOut";
import { MessageBody } from "./MessageBody";
import type { Message, MessageKind } from "./streamApi";
import { editEntry, reopenLast, showsReopen } from "./streamState";
import type { StreamState } from "./streamState";

export type StreamRecordProps = {
  state: StreamState;
  /** Passed on to `reopenLast`. */
  signal?: AbortSignal;
};

const KIND_LABELS: Record<MessageKind, string> = {
  partner: "Partner",
  turn: "My turn",
  decision: "Decision",
};

/** The body by kind: partner quoted and plain, turn plain, decision the card (D5). */
function EntryBody(props: { entry: Message }): React.JSX.Element {
  const { entry } = props;
  if (entry.kind === "decision") {
    return <MessageBody text={entry.text} variant="decision" />;
  }
  if (entry.kind === "partner") {
    return (
      <Blockquote p="sm" m={0}>
        <MessageBody text={entry.text} variant="plain" />
      </Blockquote>
    );
  }
  return <MessageBody text={entry.text} variant="plain" />;
}

/** Props of one settled entry (014 `005`). */
type StreamEntryProps = {
  state: StreamState;
  entry: Message;
  /** Whether this is the record's last entry (re-open candidate under `showsReopen`). */
  isLast: boolean;
  /** Passed on to `reopenLast` and `editEntry`. */
  signal?: AbortSignal;
};

/**
 * One settled entry (014 `005`, D6, D7, D10): kind label, the always-rendered actions group
 * (revealed by opacity, reported as `data-revealed`) and the body by kind, or the
 * "Edit entry text" editor while editing.
 */
const StreamEntry = observer(function StreamEntry(
  props: StreamEntryProps,
): React.JSX.Element {
  const { state, entry, isLast, signal } = props;
  const reopenOffered = isLast && showsReopen(state);

  // Reveal (D6): hovered, focus within, or a device that cannot hover.
  const { hovered, ref: hoverRef } = useHover<HTMLLIElement>();
  const { focused, ref: focusRef } = useFocusWithin<HTMLLIElement>();
  const itemRef = useMergedRef<HTMLLIElement>(hoverRef, focusRef);
  const noHover = useMediaQuery("(hover: none)") === true;
  const revealed = hovered || focused || noHover;

  // View state (D10): whether this entry's editor is open, and its draft.
  const [editing, setEditing] = useState(false);
  const [editDraft, setEditDraft] = useState("");

  function openEditor(): void {
    if (editing) {
      return; // an open editor keeps its typed text (R10)
    }
    setEditDraft(entry.text);
    setEditing(true);
  }

  function commit(): void {
    const text = editDraft;
    void editEntry(state, entry.id, text, signal).then((mayClose) => {
      if (mayClose) {
        setEditing(false);
      }
    });
  }

  return (
    <Box component="li" ref={itemRef} mb="md">
      <Stack gap="xs">
        <Group gap="xs" justify="space-between" wrap="nowrap">
          <Text size="sm" fw={600} c="dimmed">
            {entry.kind === null ? "" : KIND_LABELS[entry.kind]}
          </Text>
          <Group
            gap={4}
            wrap="nowrap"
            data-revealed={revealed ? "true" : "false"}
            style={{ opacity: revealed ? 1 : 0 }}
          >
            {editing ? null : (
              <IconButton icon={IconEdit} label="Edit entry" onClick={openEditor} />
            )}
            {entry.kind === "turn" ? (
              <IconButton
                icon={IconCopy}
                label="Copy as plain text"
                onClick={() => {
                  void copyAsPlainText(entry.text);
                }}
              />
            ) : null}
            {reopenOffered ? (
              <IconButton
                icon={IconArrowBackUp}
                label="Re-open last entry"
                disabled={state.busy}
                onClick={() => {
                  void reopenLast(state, signal);
                }}
              />
            ) : null}
          </Group>
        </Group>
        {editing ? (
          <Textarea
            aria-label="Edit entry text"
            autosize
            autoFocus
            value={editDraft}
            onChange={(event) => {
              setEditDraft(event.currentTarget.value);
            }}
            onBlur={commit}
          />
        ) : (
          <EntryBody entry={entry} />
        )}
      </Stack>
    </Box>
  );
});

/** Renders the session's settled record (D4, D11). */
export const StreamRecord = observer(function StreamRecord(
  props: StreamRecordProps,
): React.JSX.Element {
  const { state, signal } = props;
  const entries = state.entries;
  const lastIndex = entries.length - 1;

  return (
    <Box
      component="ul"
      aria-label="Settled record"
      m={0}
      p={0}
      style={{ listStyle: "none" }}
    >
      {entries.length === 0 ? (
        <Text c="dimmed">No entries yet.</Text>
      ) : (
        entries.map((entry, index) => (
          <StreamEntry
            key={entry.id}
            state={state}
            entry={entry}
            isLast={index === lastIndex}
            signal={signal}
          />
        ))
      )}
    </Box>
  );
});
