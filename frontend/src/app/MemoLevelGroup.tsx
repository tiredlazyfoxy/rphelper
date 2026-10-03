// One level's notes as a titled region (feature 015, step 007, D1 / D5 / D6 / D13 / D14):
// each note one list item with the shared `MarkdownEditor` (saved on focus loss), the two
// independent flag `IconButton`s, its reach line and its inline failure; a "New note"
// button and the unsaved new note; the empty, loading and failed states; and the flush on
// unmount. It does not create, load or own its state — the session screen (008) and the
// character page (009) both mount it with a `MemoLevelState` (006).
//
// Feature 016, step 003 (D5 / D8 / D9): the new note renders first with focus in its body,
// and behind the opt-in `reorderable` prop each saved note is a focusable sortable card in
// a per-level `SortableContext`; the level's reorder failure renders inline.
import type * as React from "react";
import { useEffect, useId, useState } from "react";
import { Box, Button, Group, Loader, Stack, Text, Title } from "@mantine/core";
import type { TitleOrder } from "@mantine/core";
import { IconCircleCheck, IconCircleOff, IconPin, IconPlus } from "@tabler/icons-react";
import { observer } from "mobx-react-lite";
import {
  SortableContext,
  rectSortingStrategy,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import { IconButton } from "../shared/IconButton";
import { MarkdownEditor } from "../shared/MarkdownEditor";
import type { Memo } from "./memosApi";
import { memoReach, reachStatement } from "./memoReach";
import {
  flushMemoLevel,
  isFlagWriteInFlight,
  isReorderInFlight,
  noteFailure,
  noteText,
  openNewNote,
  reorderFailure,
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
 * The same bare list as a responsive multi-column grid (018 D8): as many columns of at
 * least the card minimum as fit, inline style only (no stylesheet, no new selector).
 */
const GRID_STYLE: React.CSSProperties = {
  listStyle: "none",
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(18rem, 1fr))",
  gap: "var(--mantine-spacing-sm)",
  alignItems: "start",
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

type NoteCardBodyProps = {
  state: MemoLevelState;
  memo: Memo;
  /** Told when focus enters (true) and leaves (false) the editor area; sortable shell only. */
  onEditingChange?: (editing: boolean) => void;
};

/**
 * One saved note's card contents (015 `007`): the editor (saved on focus leave), the two
 * flag controls, the reach line and the inline failure. Shared by both outer shells.
 */
const NoteCardBody = observer(function NoteCardBody(
  props: NoteCardBodyProps,
): React.JSX.Element {
  const { state, memo, onEditingChange } = props;
  const failure = noteFailure(state, memo.id);
  const inFlight = isFlagWriteInFlight(state, memo.id);
  const disabled = !memo.is_enabled;
  const save = onFocusLeave(() => {
    onEditingChange?.(false);
    void saveNote(state, memo.id);
  });
  return (
    <Stack gap={4}>
      <Box
        c={disabled ? "dimmed" : undefined}
        td={disabled ? "line-through" : undefined}
        onFocus={() => {
          onEditingChange?.(true);
        }}
        onBlur={save}
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
  );
});

type SortableNoteCardProps = {
  state: MemoLevelState;
  memo: Memo;
  /** 1-based position among the level's saved notes. */
  position: number;
  /** The number of saved notes in the level. */
  total: number;
};

/**
 * The sortable outer shell (D8): the whole `listitem` is the drag surface, focusable,
 * named by its position, keyboard activation only from the card itself, and disabled
 * while its editor has focus or the level's reorder is in flight.
 */
const SortableNoteCard = observer(function SortableNoteCard(
  props: SortableNoteCardProps,
): React.JSX.Element {
  const { state, memo, position, total } = props;
  // Component-local view state: does focus sit inside this card's editor area?
  const [editing, setEditing] = useState(false);
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({
    id: memo.id,
    disabled: editing || isReorderInFlight(state),
    attributes: { role: "listitem" },
  });

  const onKeyDown = (event: React.KeyboardEvent<HTMLLIElement>): void => {
    // Keys typed in the editor or pressed on a flag button never start a drag.
    if (event.target !== event.currentTarget) {
      return;
    }
    const forward = listeners?.onKeyDown;
    if (forward !== undefined) {
      forward(event);
    }
  };

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <li
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      aria-label={`Note ${position} of ${total}`}
      onKeyDown={onKeyDown}
    >
      <NoteCardBody state={state} memo={memo} onEditingChange={setEditing} />
    </li>
  );
});

export type MemoLevelGroupProps = {
  /** The level's state; created, loaded and owned by the mount. */
  state: MemoLevelState;
  /** The group's heading text, which also names its region. */
  title: string;
  /** The heading level the mount needs (Mantine `Title` `order`). */
  headingOrder: TitleOrder;
  /** Called by the failed state's "Retry" button. */
  onRetry: () => void;
  /**
   * When true, saved notes render as focusable sortable cards inside a per-level
   * `SortableContext` (needs a `DndContext` ancestor). Defaults to false: no dnd-kit hook
   * runs and no `DndContext` is needed.
   */
  reorderable?: boolean;
  /**
   * How the list lays out its listitems (018 D8). "list" (the default) is the wall's
   * stacked list; "grid" is the same list and listitems as a responsive multi-column grid,
   * with the rect sorting strategy when `reorderable`.
   */
  layout?: MemoLevelLayout;
};

/** `MemoLevelGroup`'s list layout: the stacked list (default) or a multi-column grid. */
export type MemoLevelLayout = "list" | "grid";

export const MemoLevelGroup = observer(function MemoLevelGroup(
  props: MemoLevelGroupProps,
): React.JSX.Element {
  const { state, title, headingOrder, onRetry, reorderable = false, layout = "list" } = props;
  const headingId = useId();

  // D5: leaving keeps the edit. Flushes the state captured at mount, once, on unmount.
  useEffect(() => {
    const mounted = state;
    return () => {
      void flushMemoLevel(mounted);
    };
    // Empty dependency list by design: the state captured at mount, flushed once.
  }, []);

  const renderSavedNotes = (): React.JSX.Element | React.JSX.Element[] => {
    if (!reorderable) {
      // The plain shell: no dnd-kit hook runs, no `DndContext` needed.
      return state.memos.map((memo) => (
        <Box component="li" key={memo.id}>
          <NoteCardBody state={state} memo={memo} />
        </Box>
      ));
    }
    const total = state.memos.length;
    return (
      <SortableContext
        items={state.memos.map((memo) => memo.id)}
        strategy={layout === "grid" ? rectSortingStrategy : verticalListSortingStrategy}
      >
        {state.memos.map((memo, index) => (
          <SortableNoteCard
            key={memo.id}
            state={state}
            memo={memo}
            position={index + 1}
            total={total}
          />
        ))}
      </SortableContext>
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
              autoFocus
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
          <Box component="ul" m={0} p={0} style={layout === "grid" ? GRID_STYLE : LIST_STYLE}>
            {renderNewNote()}
            {renderSavedNotes()}
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

  const failedReorder = reorderFailure(state);
  return (
    <section aria-labelledby={headingId}>
      <Stack gap="xs">
        <Title order={headingOrder} id={headingId}>
          {title}
        </Title>
        {failedReorder !== null && (
          // The level's own failure: inside the region, outside every listitem (D7).
          <Text c="red" size="sm">
            {failedReorder}
          </Text>
        )}
        {renderContent()}
      </Stack>
    </section>
  );
});
