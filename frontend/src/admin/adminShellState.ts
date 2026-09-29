// The admin shell's state: one observable field, no methods, no computed getters.
// Changes go through the free functions below.
import { makeAutoObservable, runInAction } from "mobx";

export class AdminShellState {
  navbarOpened = false;

  constructor() {
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/** Flips `navbarOpened`. Synchronous; no fetch, no navigation, no timer. */
export function toggleNavbar(shell: AdminShellState): void {
  runInAction(() => {
    shell.navbarOpened = !shell.navbarOpened;
  });
}

/** Sets `navbarOpened` to true. */
export function openNavbar(shell: AdminShellState): void {
  runInAction(() => {
    shell.navbarOpened = true;
  });
}

/** Sets `navbarOpened` to false. */
export function closeNavbar(shell: AdminShellState): void {
  runInAction(() => {
    shell.navbarOpened = false;
  });
}
