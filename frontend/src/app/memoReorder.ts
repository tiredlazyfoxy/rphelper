// The note wall's drop decision and drop effect (feature 016, step 004, D7 / D8).
// `decideMemoDrop` is pure and DOM-free: it is the one place a cross-level drop is refused
// (US-103.AC-2). `applyMemoDrop` is what a drag-end handler calls: it applies an accepted
// decision through `reorderMemoLevel` and does nothing at all on a refusal.
import { arrayMove } from "@dnd-kit/sortable";

import type { MemoLevelState } from "./memoLevelState";
import { reorderMemoLevel } from "./memoLevelState";

/** One level as the decision sees it: its key (the level's scope) and its saved note ids in order. */
export type MemoDropLevel = {
  key: string;
  ids: readonly string[];
};

/** An accepted drop: the one level involved and its new id order. */
export type MemoDropDecision = {
  key: string;
  ids: string[];
};

/**
 * Turns (levels, active id, over id) into one level's new order, or `null` when the drop is
 * refused: no over id, active equal to over, an id in no level, or the two ids in different
 * levels. Never mutates its inputs.
 */
export function decideMemoDrop(
  levels: readonly MemoDropLevel[],
  activeId: string,
  overId: string | null,
): MemoDropDecision | null {
  if (overId === null || activeId === overId) {
    return null;
  }
  const activeLevel = levels.find((level) => level.ids.includes(activeId));
  const overLevel = levels.find((level) => level.ids.includes(overId));
  if (activeLevel === undefined || overLevel === undefined || activeLevel !== overLevel) {
    return null;
  }
  const from = activeLevel.ids.indexOf(activeId);
  const to = activeLevel.ids.indexOf(overId);
  // `arrayMove` copies; the input is never mutated.
  return { key: activeLevel.key, ids: arrayMove([...activeLevel.ids], from, to) };
}

/**
 * Builds the decision's input from each level's `memos`, decides, and on acceptance calls
 * `reorderMemoLevel` on that level's state with the new order. A refusal does nothing.
 * Resolves once the reorder settles; never rejects.
 */
export async function applyMemoDrop(
  levels: readonly MemoLevelState[],
  activeId: string,
  overId: string | null,
): Promise<void> {
  const decision = decideMemoDrop(
    levels.map((level) => ({ key: level.scope, ids: level.memos.map((memo) => memo.id) })),
    activeId,
    overId,
  );
  if (decision === null) {
    return;
  }
  const level = levels.find((candidate) => candidate.scope === decision.key);
  if (level === undefined) {
    return;
  }
  await reorderMemoLevel(level, decision.ids);
}
