// The session screen's "Notes" region (feature 015, step 008, D1 / D16 / R2): creates and
// loads its own `MemoChainState`, then renders one `MemoLevelGroup` per chain level in the
// server's order (the setup group absent when the session has none), with its own loading
// and failed states. Mounted by `SessionScreen`'s ready render.
import type * as React from "react";
import { useEffect, useId, useRef, useState } from "react";
import { observer } from "mobx-react-lite";
import { Button, Loader, Stack, Text, Title } from "@mantine/core";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type Announcements,
  type DragEndEvent,
  type UniqueIdentifier,
} from "@dnd-kit/core";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";

import type { MemoScope } from "./memosApi";
import { MemoChainState, loadMemoChain } from "./memoChainState";
import type { MemoLevelState } from "./memoLevelState";
import { MemoLevelGroup } from "./MemoLevelGroup";
import { applyMemoDrop } from "./memoReorder";

/** Each level's group title (private to this section). */
const LEVEL_TITLES: Record<MemoScope, string> = {
  user: "Your notes",
  character: "Character notes",
  setup: "Setup notes",
  session: "Session notes",
};

/** The chain's groups are always "ready", so their Retry is unreachable. */
const noop = (): void => {};

/** A note's 1-based place among its level's saved notes, with the level's group title. */
type NotePlace = { position: number; total: number; title: string };

/** Finds where a sortable id sits in the chain; `null` when it is in no level. */
function findNotePlace(levels: readonly MemoLevelState[], id: UniqueIdentifier): NotePlace | null {
  const memoId = String(id);
  for (const level of levels) {
    const index = level.memos.findIndex((memo) => memo.id === memoId);
    if (index !== -1) {
      return { position: index + 1, total: level.memos.length, title: LEVEL_TITLES[level.scope] };
    }
  }
  return null;
}

/** dnd-kit announcements that name a note by its position and group, never by its id (D8). */
function chainAnnouncements(levels: readonly MemoLevelState[]): Announcements {
  const overMessage = (activeId: UniqueIdentifier, overId: UniqueIdentifier | null): string => {
    const active = findNotePlace(levels, activeId);
    const over = overId === null ? null : findNotePlace(levels, overId);
    if (active === null || over === null) {
      return "The note is not over a place in its level.";
    }
    if (active.title !== over.title) {
      return `A note cannot move to ${over.title}; it stays in ${active.title}.`;
    }
    return `Note moved to position ${over.position} of ${over.total}.`;
  };
  return {
    onDragStart({ active }) {
      const place = findNotePlace(levels, active.id);
      return place === null
        ? "Picked up a note."
        : `Picked up note ${place.position} of ${place.total} in ${place.title}.`;
    },
    onDragOver({ active, over }) {
      return overMessage(active.id, over ? over.id : null);
    },
    onDragEnd({ active, over }) {
      const activePlace = findNotePlace(levels, active.id);
      const overPlace = over ? findNotePlace(levels, over.id) : null;
      if (activePlace === null || overPlace === null || activePlace.title !== overPlace.title) {
        return "Note dropped. Its place is unchanged.";
      }
      return `Note dropped in ${activePlace.title}.`;
    },
    onDragCancel() {
      return "Reorder cancelled.";
    },
  };
}

export type MemoChainSectionProps = {
  /** The loaded session's id. A string, never parsed. */
  sessionId: string;
};

export const MemoChainSection = observer(function MemoChainSection(
  props: MemoChainSectionProps,
): React.JSX.Element {
  // Created once, never with `useMemo`; `SessionRoute` keys the screen by the session id, so
  // a different session remounts this section with fresh chain state (D16).
  const [state] = useState(() => new MemoChainState(props.sessionId));
  const controllerRef = useRef<AbortController | null>(null);
  // The heading's id: `aria-labelledby` on the `<section>` names the region "Notes".
  const headingId = useId();
  // D8: a click edits, only a press-and-move of 6px drags; the keyboard path is required.
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragEnd = (event: DragEndEvent): void => {
    void applyMemoDrop(
      state.levels,
      String(event.active.id),
      event.over ? String(event.over.id) : null,
    );
  };

  // One load on mount; whichever controller is current aborts on unmount.
  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadMemoChain(state, controller.signal);
    return () => {
      controller.abort();
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, [state]);

  const retry = (): void => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadMemoChain(state, controller.signal);
  };

  const renderBody = (): React.JSX.Element => {
    if (state.status === "failed") {
      // Inline only — nothing is notified.
      return (
        <Stack gap="xs" align="flex-start">
          <Text size="sm">Could not load notes</Text>
          <Button size="xs" variant="default" onClick={retry}>
            Retry
          </Button>
        </Stack>
      );
    }

    if (state.status !== "ready") {
      return <Loader size="sm" />;
    }

    // R2: whatever levels the server returned, in its order; scope is unique per chain.
    // D8: one `DndContext` over the whole chain; each group holds its own `SortableContext`.
    return (
      <DndContext
        sensors={sensors}
        onDragEnd={handleDragEnd}
        accessibility={{ announcements: chainAnnouncements(state.levels) }}
      >
        <Stack gap="md">
          {state.levels.map((level) => (
            <MemoLevelGroup
              key={level.scope}
              state={level}
              title={LEVEL_TITLES[level.scope]}
              headingOrder={4}
              onRetry={noop}
              reorderable
            />
          ))}
        </Stack>
      </DndContext>
    );
  };

  return (
    <section aria-labelledby={headingId}>
      <Stack gap="xs">
        {/* One level below the session header's start-time heading (order 2). */}
        <Title order={3} id={headingId}>
          Notes
        </Title>
        {renderBody()}
      </Stack>
    </section>
  );
});
