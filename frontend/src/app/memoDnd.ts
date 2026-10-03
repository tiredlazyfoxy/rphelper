// The notes' shared drag setup (feature 018, step 005, D8; 016 D8): the sensor set and the
// position-only announcements, factored out of `MemoChainSection` so the session screen's
// wall and the character page's grid use one keyboard path rather than two copies.
import {
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type Announcements,
  type SensorDescriptor,
  type SensorOptions,
  type UniqueIdentifier,
} from "@dnd-kit/core";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";

/** One group on screen, for the announcements: its title and its saved note ids in order. */
export type MemoDndGroup = {
  /** The group's title as shown (e.g. "Your notes", "Notes"). */
  title: string;
  /** The group's saved note ids, in their on-screen order. */
  ids: readonly string[];
};

/**
 * The sensor set 016 D8 fixes: a `PointerSensor` that activates after a 6px press-and-move,
 * and a `KeyboardSensor` using `sortableKeyboardCoordinates`. A React hook.
 */
export function useMemoDndSensors(): SensorDescriptor<SensorOptions>[] {
  // D8: a click edits, only a press-and-move of 6px drags; the keyboard path is required.
  return useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
}

/** A note's 1-based place among its group's saved notes, with the group's title. */
type NotePlace = { position: number; total: number; title: string };

/** Finds where a sortable id sits among the groups; `null` when it is in none. */
function findNotePlace(groups: readonly MemoDndGroup[], id: UniqueIdentifier): NotePlace | null {
  const memoId = String(id);
  for (const group of groups) {
    const index = group.ids.indexOf(memoId);
    if (index !== -1) {
      return { position: index + 1, total: group.ids.length, title: group.title };
    }
  }
  return null;
}

/**
 * dnd-kit announcements over the given groups (pure). A note is named by its 1-based
 * position in its group and the group's title, never by its id; an id in no group yields a
 * generic message that still contains no id.
 */
export function memoAnnouncements(groups: readonly MemoDndGroup[]): Announcements {
  const overMessage = (activeId: UniqueIdentifier, overId: UniqueIdentifier | null): string => {
    const active = findNotePlace(groups, activeId);
    const over = overId === null ? null : findNotePlace(groups, overId);
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
      const place = findNotePlace(groups, active.id);
      return place === null
        ? "Picked up a note."
        : `Picked up note ${place.position} of ${place.total} in ${place.title}.`;
    },
    onDragOver({ active, over }) {
      return overMessage(active.id, over ? over.id : null);
    },
    onDragEnd({ active, over }) {
      const activePlace = findNotePlace(groups, active.id);
      const overPlace = over ? findNotePlace(groups, over.id) : null;
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
