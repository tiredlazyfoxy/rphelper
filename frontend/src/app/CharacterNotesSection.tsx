// The character page's character-level "Notes" region (feature 015, step 009, D1 / D8 /
// D16): owns one `MemoLevelState` for scope "character" and the given id, loads it on mount
// (aborted on unmount), and renders the shared `MemoLevelGroup` titled "Notes" at the same
// heading order as the page's "Setups" and "Sessions" headings. Mounted by
// `CharacterScreen`'s existing-mode ready render after `SessionsSection`, keyed by the id.
//
// Feature 018, step 005 (D8): the group renders as a reorderable grid inside this section's
// own `DndContext` (the page has no chain section), with the shared sensors and
// announcements from `memoDnd` and 016's drop effect over its one level.
//
// Feature 033, step 002 (D6): the group renders as a reorderable single-column list in
// "header add" mode — a '+' beside the "Notes" heading opens an inline draft with Save and
// Cancel icon buttons and no blur-save.
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react-lite";
import { DndContext, type DragEndEvent } from "@dnd-kit/core";

import { MemoLevelState, loadMemoLevel } from "./memoLevelState";
import { MemoLevelGroup } from "./MemoLevelGroup";
import { memoAnnouncements, useMemoDndSensors } from "./memoDnd";
import { applyMemoDrop } from "./memoReorder";

export type CharacterNotesSectionProps = {
  /** The loaded character's id. A string, never parsed. */
  characterId: string;
};

export const CharacterNotesSection = observer(function CharacterNotesSection(
  props: CharacterNotesSectionProps,
): React.JSX.Element {
  // Created once; `CharacterScreen` keys this section by the character id, so a different
  // character remounts it with fresh state (D16: separate from the session screen's level).
  const [state] = useState(() => new MemoLevelState("character", props.characterId));
  const controllerRef = useRef<AbortController | null>(null);
  // D8: the shared sensor set (6px pointer distance, keyboard path) from `memoDnd`.
  const sensors = useMemoDndSensors();

  const handleDragEnd = (event: DragEndEvent): void => {
    void applyMemoDrop(
      [state],
      String(event.active.id),
      event.over ? String(event.over.id) : null,
    );
  };

  // One load on mount; whichever controller is current aborts on unmount.
  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadMemoLevel(state, controller.signal);
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
    void loadMemoLevel(state, controller.signal);
  };

  // Same `Title order={3}` as the page's "Setups" and "Sessions" headings.
  return (
    <DndContext
      sensors={sensors}
      onDragEnd={handleDragEnd}
      accessibility={{
        announcements: memoAnnouncements([
          { title: "Notes", ids: state.memos.map((memo) => memo.id) },
        ]),
      }}
    >
      <MemoLevelGroup
        state={state}
        title="Notes"
        headingOrder={3}
        onRetry={retry}
        layout="list"
        reorderable
      />
    </DndContext>
  );
});
