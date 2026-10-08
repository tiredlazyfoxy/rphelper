// Feature 005, step 005 — the admin shell's MobX state and its free functions (DoD-5).
// DoD-1..DoD-4 live in navItems.test.ts; DoD-6..DoD-14 in AdminApp.test.tsx.
//
// Expected shape comes from 002's D2 as restated by context.md D16: a data class with
// observable fields only — here exactly one, whether the navbar is opened — and no methods
// and no computed getters; open, close and toggle are free functions taking the object.
// They are synchronous and pure-in-effect: no fetch, no navigation, no timer.
import { autorun, isComputedProp, isObservableProp } from "mobx";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AdminShellState, closeNavbar, openNavbar, toggleNavbar } from "../../src/admin/adminShellState";
import { documentNavigation } from "../../src/shared/api";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function withOpened(opened: boolean): AdminShellState {
  const shell = new AdminShellState();
  if (opened) openNavbar(shell);
  expect(shell.navbarOpened).toBe(opened);
  return shell;
}

// ---------------------------------------------------------------------------
describe("the shell state is a data class with one observable field", () => {
  it("the class prototype carries no method and no getter — DoD-5", () => {
    expect(Object.getOwnPropertyNames(AdminShellState.prototype)).toEqual(["constructor"]);
  });

  it("navbarOpened is observable and not computed — DoD-5", () => {
    const shell = new AdminShellState();
    expect(isObservableProp(shell, "navbarOpened")).toBe(true);
    expect(isComputedProp(shell, "navbarOpened")).toBe(false);
  });

  it("navbarOpened is the one and only observable field — DoD-5", () => {
    const shell = new AdminShellState();
    const observed = Object.getOwnPropertyNames(shell).filter((name) => isObservableProp(shell, name));
    expect(observed).toEqual(["navbarOpened"]);
  });

  it("no own property of an instance is a function or a computed value — DoD-5", () => {
    const shell = new AdminShellState();
    const record = shell as unknown as Record<string, unknown>;
    for (const name of Object.getOwnPropertyNames(shell)) {
      expect(typeof record[name], `own property ${name}`).not.toBe("function");
      expect(isComputedProp(shell, name), `own property ${name}`).toBe(false);
    }
  });

  it("a fresh shell starts with the navbar closed — DoD-5", () => {
    expect(new AdminShellState().navbarOpened).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("open, close and toggle are free functions over the object", () => {
  it("openNavbar opens a closed navbar and leaves an open one open — DoD-5", () => {
    const shell = withOpened(false);
    openNavbar(shell);
    expect(shell.navbarOpened).toBe(true);
    openNavbar(shell);
    expect(shell.navbarOpened).toBe(true);
  });

  it("closeNavbar closes an open navbar and leaves a closed one closed — DoD-5", () => {
    const shell = withOpened(true);
    closeNavbar(shell);
    expect(shell.navbarOpened).toBe(false);
    closeNavbar(shell);
    expect(shell.navbarOpened).toBe(false);
  });

  it("toggleNavbar flips the field each time it is called — DoD-5", () => {
    const shell = new AdminShellState();
    toggleNavbar(shell);
    expect(shell.navbarOpened).toBe(true);
    toggleNavbar(shell);
    expect(shell.navbarOpened).toBe(false);
    toggleNavbar(shell);
    expect(shell.navbarOpened).toBe(true);
  });

  it("each function changes only the object it is given — DoD-5", () => {
    const first = new AdminShellState();
    const second = new AdminShellState();
    openNavbar(first);
    expect([first.navbarOpened, second.navbarOpened]).toEqual([true, false]);
    toggleNavbar(second);
    expect([first.navbarOpened, second.navbarOpened]).toEqual([true, true]);
    closeNavbar(first);
    expect([first.navbarOpened, second.navbarOpened]).toEqual([false, true]);
  });

  it("the changes are observable to a MobX reaction — DoD-5", () => {
    const shell = new AdminShellState();
    const seen: boolean[] = [];
    const dispose = autorun(() => {
      seen.push(shell.navbarOpened);
    });
    try {
      openNavbar(shell);
      closeNavbar(shell);
      toggleNavbar(shell);
    } finally {
      dispose();
    }
    expect(seen).toEqual([false, true, false, true]);
  });

  it("the functions are synchronous and issue no fetch, no navigation and no timer — DoD-5", () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const navigate = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    const shell = new AdminShellState();

    const results = [openNavbar(shell), closeNavbar(shell), toggleNavbar(shell)];

    expect(shell.navbarOpened).toBe(true);
    for (const result of results) expect(result).toBeUndefined();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
});
