// One level's notes as a titled region (feature 015, step 007, D1 / D5 / D6 / D13 / D14):
// each note one list item with the shared `MarkdownEditor` (saved on focus loss), the two
// independent flag `IconButton`s, its reach line and its inline failure; a "New note"
// button and the unsaved new note; the empty, loading and failed states; and the flush on
// unmount. It does not create, load or own its state — the session screen (008) and the
// character page (009) both mount it with a `MemoLevelState` (006).
import type * as React from "react";
import { useEffect, useId } from "react";
import { Box, Button, Group, Loader, Stack, Text, Title } from "@mantine/core";
import type { TitleOrder } from "@mantine/core";
import { IconCircleCheck, IconCircleOff, IconPin, IconPlus } from "@tabler/icons-react";
import { observer } from "mobx-react-lite";

import { IconButton } from "../shared/IconButton";
import { MarkdownEditor } from "../shared/MarkdownEditor";
import type { Memo } from "./memosApi";
import { memoReach, reachStatement } from "./memoReach";
import {
  flushMemoLevel,
  isFlagWriteInFlight,
  noteFailure,
  noteText,
  openNewNote,
  saveNewNote,
  saveNote,
  setNewNoteText,
  setNoteText,
  toggleEnabled,
  toggleForced,
} from "./memoLevelState";
import type { MemoLevelState } from "./memoLevelState";

/** The repo's "main" icon metrics, for the "New note" button's left section. */
const ICON_SIZE = 18;
const ICON_STROKE = 1.5;

/** The forced toggle's colour while the note is forced (D14); none otherwise. */
const FORCED_COLOR = "orange";

/** The bare list: no bullets, items stacked with the theme's small spacing. */
const LIST_STYLE: React.CSSProperties = {
  listStyle: "none",
  display: "flex",
  flexDirection: "column",
  gap: "var(--mantine-spacing-sm)",
};

/**
 * Runs `save` only when focus leaves the wrapper — not when it moves between elements
 * inside it (the TipTap content and its own toolbar, DoD-17).
 */
function onFocusLeave(save: () => void): (event: React.FocusEvent<HTMLDivElement>) => void {
  return (event) => {
    const next = event.relatedTarget;
    if (next instanceof Node && event.currentTarget.contains(next)) {
      return;
    }
    save();
  };
}

export type MemoLevelGroupProps = {
  /** The level's state; created, loaded and owned by the mount. */
  state: MemoLevelState;
  /** The group's heading text, which also names its region. */
  title: string;
  /** The heading level the mount needs (Mantine `Title` `order`). */
  headingOrder: TitleOrder;
  /** Called by the failed state's "Retry" button. */
  onRetry: () => void;
};

export const MemoLevelGroup = observer(function MemoLevelGroup(
  props: MemoLevelGroupProps,
): React.JSX.Element {
  const { state, title, headingOrder, onRetry } = props;
  const headingId = useId();

  // D5: leaving keeps the edit. Flushes the state captured at mount, once, on unmount.
  useEffect(() => {
    const mounted = state;
    return () => {
      void flushMemoLevel(mounted);
    };
    // Empty dependency list by design: the state captured at mount, flushed once.
  }, []);

  const renderNote = (memo: Memo): React.JSX.Element => {
    const failure = noteFailure(state, memo.id);
    const inFlight = isFlagWriteInFlight(state, memo.id);
    const disabled = !memo.is_enabled;
    return (
      <Box component="li" key={memo.id}>
        <Stack gap={4}>
          <Box
            c={disabled ? "dimmed" : undefined}
            td={disabled ? "line-through" : undefined}
            onBlur={onFocusLeave(() => {
              void saveNote(state, memo.id);
            })}
          >
            <MarkdownEditor
              label="Note"
              value={noteText(state, memo.id)}
              onChange={(markdown) => {
                setNoteText(state, memo.id, markdown);
              }}
            />
          </Box>
          <Group gap="xs" wrap="nowrap">
            <IconButton
              icon={memo.is_enabled ? IconCircleCheck : IconCircleOff}
              label={memo.is_enabled ? "Disable note" : "Enable note"}
              sizeVariant="inline"
              disabled={inFlight}
              onClick={() => {
                void toggleEnabled(state, memo.id);
              }}
            />
            <IconButton
              icon={IconPin}
              label={memo.is_forced ? "Stop forcing note" : "Force note"}
              sizeVariant="inline"
              color={memo.is_forced ? FORCED_COLOR : undefined}
              disabled={inFlight}
              onClick={() => {
                void toggleForced(state, memo.id);
              }}
            />
            <Text c="dimmed" size="sm">
              {reachStatement(memoReach(memo))}
            </Text>
          </Group>
          {failure !== null && (
            <Text c="red" size="sm">
              {failure}
            </Text>
          )}
        </Stack>
      </Box>
    );
  };

  const renderNewNote = (): React.JSX.Element | null => {
    const newNote = state.newNote;
    if (newNote === null) {
      return null;
    }
    // D13: no flag controls and no reach line — there is no stored row yet.
    return (
      <Box component="li" key="new-note">
        <Stack gap={4}>
          <Box
            onBlur={onFocusLeave(() => {
              void saveNewNote(state);
            })}
          >
            <MarkdownEditor
              label="Note"
              value={newNote.text}
              onChange={(markdown) => {
                setNewNoteText(state, markdown);
              }}
            />
          </Box>
          {newNote.failure !== null && (
            <Text c="red" size="sm">
              {newNote.failure}
            </Text>
          )}
        </Stack>
      </Box>
    );
  };

  const renderContent = (): React.JSX.Element => {
    if (state.status === "idle" || state.status === "loading") {
      return (
        <Group justify="center" py="sm">
          <Loader size="sm" />
        </Group>
      );
    }

    if (state.status === "failed") {
      // Inline, never a notification (D5).
      return (
        <Stack gap="xs" align="flex-start">
          <Text size="sm">Could not load notes</Text>
          <Button size="xs" variant="default" onClick={onRetry}>
            Retry
          </Button>
        </Stack>
      );
    }

    const empty = state.memos.length === 0 && state.newNote === null;
    return (
      <Stack gap="xs">
        {empty ? (
          <Text c="dimmed" size="sm">
            No notes yet.
          </Text>
        ) : (
          <Box component="ul" m={0} p={0} style={LIST_STYLE}>
            {state.memos.map(renderNote)}
            {renderNewNote()}
          </Box>
        )}
        <Group>
          <Button
            leftSection={<IconPlus size={ICON_SIZE} stroke={ICON_STROKE} />}
            disabled={state.newNote !== null}
            onClick={() => {
              openNewNote(state);
            }}
          >
            New note
          </Button>
        </Group>
      </Stack>
    );
  };

  return (
    <section aria-labelledby={headingId}>
      <Stack gap="xs">
        <Title order={headingOrder} id={headingId}>
          {title}
        </Title>
        {renderContent()}
      </Stack>
    </section>
  );
});
