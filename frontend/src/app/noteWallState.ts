// The session screen's note wall state (016 context.md D2): a MobX data class with
// observable fields only. Every derivation and every action is a free function in this
// module taking the state; the class has no methods and no computed getters. React-free
// and DOM-free; `narrow` is passed in, never read here.
import { makeAutoObservable, runInAction } from "mobx";

import {
  readWorkspaceLayout,
  writeWorkspaceLayout,
  type LayoutStorage,
} from "./workspaceLayout";

/** The wall's effective mode: a pinned column beside the stream, or a floating flyout. */
export type WallMode = "pinned" | "floating";

/**
 * The wall's state. `pinned` mirrors the persisted record's `wallPinned`; `open` is the
 * floating wall's open flag and is never persisted.
 */
export class NoteWallState {
  pinned: boolean;
  open = false;

  constructor(pinned: boolean) {
    this.pinned = pinned;
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/**
 * Builds a `NoteWallState` whose `pinned` is the stored record's `wallPinned` and whose
 * `open` is false. A `null` storage yields the record's default.
 */
export function createNoteWallState(storage: LayoutStorage | null): NoteWallState {
  return new NoteWallState(readWorkspaceLayout(storage).wallPinned);
}

/** Pure. `"pinned"` when `pinned` and not narrow; `"floating"` otherwise. */
export function wallMode(state: NoteWallState, narrow: boolean): WallMode {
  return state.pinned && !narrow ? "pinned" : "floating";
}

/** Pure. True when the mode is pinned, or when `open`. */
export function isWallVisible(state: NoteWallState, narrow: boolean): boolean {
  return wallMode(state, narrow) === "pinned" || state.open;
}

/** Pure. `"app-session"`, plus `" wall-pinned"` when the mode is pinned. */
export function sessionLayoutClassName(state: NoteWallState, narrow: boolean): string {
  return wallMode(state, narrow) === "pinned" ? "app-session wall-pinned" : "app-session";
}

/** Pure. `"app-wall"`, plus `" wall-open"` when the mode is floating and the wall visible. */
export function wallClassName(state: NoteWallState, narrow: boolean): string {
  return wallMode(state, narrow) === "floating" && isWallVisible(state, narrow)
    ? "app-wall wall-open"
    : "app-wall";
}

/** Action. Sets `open` true. Never writes the layout record. */
export function openWall(state: NoteWallState): void {
  runInAction(() => {
    state.open = true;
  });
}

/**
 * Action. Unpinned: sets `pinned` true and writes `{ wallPinned: true }`. Pinned: sets
 * `pinned` false and `open` true, and writes `{ wallPinned: false }`.
 */
export function toggleWallPin(state: NoteWallState, storage: LayoutStorage | null): void {
  if (!state.pinned) {
    runInAction(() => {
      state.pinned = true;
    });
    writeWorkspaceLayout(storage, { wallPinned: true });
    return;
  }
  runInAction(() => {
    state.pinned = false;
    state.open = true;
  });
  writeWorkspaceLayout(storage, { wallPinned: false });
}

/**
 * Action. Sets `open` false. When the mode was pinned (pinned and not narrow), also sets
 * `pinned` false and writes `{ wallPinned: false }`. Floating (a narrow pinned wall
 * included): writes nothing.
 */
export function dismissWall(
  state: NoteWallState,
  storage: LayoutStorage | null,
  narrow: boolean,
): void {
  const wasPinned = wallMode(state, narrow) === "pinned";
  runInAction(() => {
    state.open = false;
    if (wasPinned) {
      state.pinned = false;
    }
  });
  if (wasPinned) {
    writeWorkspaceLayout(storage, { wallPinned: false });
  }
}
