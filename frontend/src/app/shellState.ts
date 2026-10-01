// The `app` workspace shell's state (008 context.md D3, D9, D11, D12): a MobX data class
// with observable fields only. Every derivation and every effect is a free function in
// this module taking the state; the class has no methods and no computed getters.
import { makeAutoObservable, runInAction } from "mobx";

import {
  readWorkspaceLayout,
  writeWorkspaceLayout,
  type LayoutStorage,
} from "./workspaceLayout";

/**
 * The one threshold string (D12): the `@media` condition in `shell.css` verbatim, and the
 * query `useMediaQuery` receives. Range syntax, so `820px` appears literally and "narrow"
 * means strictly below it.
 */
export const NARROW_VIEWPORT_QUERY = "(width < 820px)";

/**
 * The shell's state. `navCollapsed` mirrors the persisted record; `overlayOpen` is the
 * narrow-width overlay's open flag and is never persisted.
 */
export class ShellState {
  navCollapsed: boolean;
  overlayOpen = false;

  constructor(navCollapsed: boolean) {
    this.navCollapsed = navCollapsed;
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/**
 * Builds a `ShellState` whose `navCollapsed` is the stored record's and whose overlay is
 * closed. A `null` storage yields the record's default.
 */
export function createShellState(storage: LayoutStorage | null): ShellState {
  return new ShellState(readWorkspaceLayout(storage).navCollapsed);
}

/**
 * Pure. True when the left column should render the rail: at narrow width exactly when the
 * overlay is closed; at wide width exactly when `navCollapsed`.
 */
export function showsRail(shell: ShellState, narrow: boolean): boolean {
  return narrow ? !shell.overlayOpen : shell.navCollapsed;
}

/**
 * Pure. The `.app` element's class string: always `app`, plus `nav-collapsed` when
 * `navCollapsed`, plus `nav-overlay-open` when narrow and the overlay is open.
 */
export function shellClassName(shell: ShellState, narrow: boolean): string {
  const classes = ["app"];
  if (shell.navCollapsed) {
    classes.push("nav-collapsed");
  }
  if (narrow && shell.overlayOpen) {
    classes.push("nav-overlay-open");
  }
  return classes.join(" ");
}

/**
 * Effect. Narrow: opens the overlay and writes nothing. Wide: sets `navCollapsed` false and
 * writes `{ navCollapsed: false }` to the record.
 */
export function expandTree(
  shell: ShellState,
  narrow: boolean,
  storage: LayoutStorage | null,
): void {
  if (narrow) {
    runInAction(() => {
      shell.overlayOpen = true;
    });
    return;
  }
  runInAction(() => {
    shell.navCollapsed = false;
  });
  writeWorkspaceLayout(storage, { navCollapsed: false });
}

/**
 * Effect. Narrow: closes the overlay and writes nothing. Wide: sets `navCollapsed` true and
 * writes `{ navCollapsed: true }` to the record.
 */
export function collapseTree(
  shell: ShellState,
  narrow: boolean,
  storage: LayoutStorage | null,
): void {
  if (narrow) {
    closeOverlay(shell);
    return;
  }
  runInAction(() => {
    shell.navCollapsed = true;
  });
  writeWorkspaceLayout(storage, { navCollapsed: true });
}

/** Effect. Closes the overlay; never touches `navCollapsed` and never writes the record. */
export function closeOverlay(shell: ShellState): void {
  runInAction(() => {
    shell.overlayOpen = false;
  });
}

/**
 * `window.localStorage` as a `LayoutStorage`, or `null` when merely accessing it throws.
 * The only place in this feature that names `window.localStorage`.
 */
export function browserLayoutStorage(): LayoutStorage | null {
  try {
    const storage: Storage | undefined = window.localStorage;
    return storage ?? null;
  } catch {
    // A browser with site data blocked throws from the getter itself.
    return null;
  }
}
