// Feature 008, step 002 — the shell's MobX state and its free functions
// (DoD-7..DoD-13; UC-070, US-090.AC-1). DoD-1..DoD-6 (shell.css and the one
// threshold string) live in tests/stylesheets.test.ts; DoD-14 and DoD-15 are
// manual/live and have no test here.
//
// The state is a data class with observable fields only (context.md, "Cross-cutting
// constraints"): every derivation and effect below is a free function taking the
// state plus `narrow`, and the storage is always a passed-in fake — never a global.
// `narrow === true` is the viewport matching `(width < 820px)` (D3, D12).
import { afterEach, describe, expect, it, vi } from "vitest";
import { autorun, runInAction } from "mobx";
import {
  browserLayoutStorage,
  closeOverlay,
  collapseTree,
  createShellState,
  expandTree,
  ShellState,
  shellClassName,
  showsRail,
} from "../../src/app/shellState";
import {
  readWorkspaceLayout,
  WORKSPACE_LAYOUT_KEY,
  type LayoutStorage,
} from "../../src/app/workspaceLayout";

type GetItem = (key: string) => string | null;
type SetItem = (key: string, value: string) => void;

// ---------------------------------------------------------------- helpers

/** An in-memory `LayoutStorage` whose two members are spies. */
function fakeStorage(seed?: Record<string, string>) {
  const entries = new Map<string, string>(Object.entries(seed ?? {}));
  const getItem = vi.fn<GetItem>((key) => entries.get(key) ?? null);
  const setItem = vi.fn<SetItem>((key, value) => {
    entries.set(key, value);
  });
  const storage: LayoutStorage = { getItem, setItem };
  return { storage, getItem, setItem };
}

/** A storage holding the given record under the layout key. */
function storageHolding(navCollapsed: boolean, wallPinned = false) {
  return fakeStorage({
    [WORKSPACE_LAYOUT_KEY]: JSON.stringify({ navCollapsed, wallPinned }),
  });
}

/**
 * A state in an exact condition. `overlayOpen` is a plain observable field, so
 * the test sets it inside an action rather than through an effect under test.
 */
function stateOf(navCollapsed: boolean, overlayOpen: boolean): ShellState {
  const shell = new ShellState(navCollapsed);
  runInAction(() => {
    shell.overlayOpen = overlayOpen;
  });
  return shell;
}

function classesOf(className: string): string[] {
  return className.split(/\s+/).filter((token) => token.length > 0);
}

/** Runs `body` while merely reading `window.localStorage` throws, then restores. */
function withThrowingLocalStorage<T>(body: () => T): T {
  const own = Object.getOwnPropertyDescriptor(window, "localStorage");
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    get(): Storage {
      throw new Error("localStorage is unavailable zq-blocked");
    },
  });
  try {
    return body();
  } finally {
    delete (window as unknown as Record<string, unknown>)["localStorage"];
    if (own !== undefined) {
      Object.defineProperty(window, "localStorage", own);
    }
  }
}

// ---------------------------------------------------------------------------
describe("a shell state starts from the persisted record", () => {
  it("a stored collapsed nav starts collapsed — DoD-7", () => {
    const { storage } = storageHolding(true);
    expect(createShellState(storage).navCollapsed).toBe(true);
  });

  it("a stored expanded nav starts expanded — DoD-7", () => {
    const { storage } = storageHolding(false);
    expect(createShellState(storage).navCollapsed).toBe(false);
  });

  it("no storage at all starts expanded — DoD-7", () => {
    expect(createShellState(null).navCollapsed).toBe(false);
  });

  it("an empty storage starts expanded — DoD-7", () => {
    expect(createShellState(fakeStorage().storage).navCollapsed).toBe(false);
  });

  it("a state built over a stored record starts with the overlay closed — DoD-7", () => {
    const { storage } = storageHolding(true);
    expect(createShellState(storage).overlayOpen).toBe(false);
  });

  it("a state built over no storage starts with the overlay closed — DoD-7", () => {
    expect(createShellState(null).overlayOpen).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("showsRail decides what the left column renders", () => {
  it.each<[boolean, boolean]>([
    [false, false],
    [false, true],
  ])(
    "wide: an expanded nav shows the full column, overlay flag %s/%s notwithstanding — DoD-8",
    (navCollapsed, overlayOpen) => {
      expect(showsRail(stateOf(navCollapsed, overlayOpen), false)).toBe(false);
    },
  );

  it.each<[boolean, boolean]>([
    [true, false],
    [true, true],
  ])(
    "wide: a collapsed nav shows the rail, overlay flag %s/%s notwithstanding — DoD-8",
    (navCollapsed, overlayOpen) => {
      expect(showsRail(stateOf(navCollapsed, overlayOpen), false)).toBe(true);
    },
  );

  it.each<[boolean]>([[false], [true]])(
    "narrow: a closed overlay shows the rail whatever navCollapsed (%s) is — DoD-8",
    (navCollapsed) => {
      expect(showsRail(stateOf(navCollapsed, false), true)).toBe(true);
    },
  );

  it.each<[boolean]>([[false], [true]])(
    "narrow: an open overlay shows the full column whatever navCollapsed (%s) is — DoD-8",
    (navCollapsed) => {
      expect(showsRail(stateOf(navCollapsed, true), true)).toBe(false);
    },
  );
});

// ---------------------------------------------------------------------------
describe("shellClassName is the grid element's class", () => {
  it("an expanded wide shell is plain app — DoD-9", () => {
    expect(shellClassName(stateOf(false, false), false)).toBe("app");
  });

  it("a collapsed wide shell is app nav-collapsed — DoD-9", () => {
    expect(shellClassName(stateOf(true, false), false)).toBe("app nav-collapsed");
  });

  it("a narrow shell with the overlay open adds nav-overlay-open — DoD-9", () => {
    const classes = classesOf(shellClassName(stateOf(false, true), true));
    expect(classes.slice().sort()).toEqual(["app", "nav-overlay-open"]);
  });

  it("a narrow collapsed shell with the overlay open carries both classes — DoD-9", () => {
    const classes = classesOf(shellClassName(stateOf(true, true), true));
    expect(classes.slice().sort()).toEqual(["app", "nav-collapsed", "nav-overlay-open"]);
  });

  it("a narrow shell with the overlay closed adds nothing — DoD-9", () => {
    expect(shellClassName(stateOf(false, false), true)).toBe("app");
  });

  it.each<[boolean]>([[false], [true]])(
    "a wide shell never carries nav-overlay-open, navCollapsed %s — DoD-9",
    (navCollapsed) => {
      expect(classesOf(shellClassName(stateOf(navCollapsed, true), false))).not.toContain(
        "nav-overlay-open",
      );
    },
  );

  it("every class string begins with app — DoD-9", () => {
    expect(classesOf(shellClassName(stateOf(true, true), true))[0]).toBe("app");
  });
});

// ---------------------------------------------------------------------------
describe("wide: the toggles persist the collapse", () => {
  it("collapseTree collapses the nav — DoD-10", () => {
    const { storage } = storageHolding(false);
    const shell = createShellState(storage);
    collapseTree(shell, false, storage);
    expect(shell.navCollapsed).toBe(true);
  });

  it("collapseTree writes the collapse to the record — DoD-10", () => {
    const { storage } = storageHolding(false);
    collapseTree(createShellState(storage), false, storage);
    expect(readWorkspaceLayout(storage).navCollapsed).toBe(true);
  });

  it("expandTree expands the nav — DoD-10", () => {
    const { storage } = storageHolding(true);
    const shell = createShellState(storage);
    expandTree(shell, false, storage);
    expect(shell.navCollapsed).toBe(false);
  });

  it("expandTree writes the expansion to the record — DoD-10", () => {
    const { storage } = storageHolding(true);
    expandTree(createShellState(storage), false, storage);
    expect(readWorkspaceLayout(storage).navCollapsed).toBe(false);
  });

  it("a collapse write preserves a pinned wall — DoD-10", () => {
    const { storage } = storageHolding(false, true);
    collapseTree(createShellState(storage), false, storage);
    expect(readWorkspaceLayout(storage)).toEqual({ navCollapsed: true, wallPinned: true });
  });

  it("an expand write preserves a pinned wall — DoD-10", () => {
    const { storage } = storageHolding(true, true);
    expandTree(createShellState(storage), false, storage);
    expect(readWorkspaceLayout(storage)).toEqual({ navCollapsed: false, wallPinned: true });
  });

  it("a collapse and an expand round-trip the record — DoD-10", () => {
    const { storage } = storageHolding(false, true);
    const shell = createShellState(storage);
    collapseTree(shell, false, storage);
    expandTree(shell, false, storage);
    expect(readWorkspaceLayout(storage)).toEqual({ navCollapsed: false, wallPinned: true });
    expect(shell.navCollapsed).toBe(false);
  });

  it("a wide toggle over no storage still changes the state — DoD-10", () => {
    const shell = createShellState(null);
    collapseTree(shell, false, null);
    expect(shell.navCollapsed).toBe(true);
  });
});

// ---------------------------------------------------------------------------
describe("narrow: the toggles drive the overlay and persist nothing", () => {
  it.each<[boolean]>([[false], [true]])(
    "expandTree opens the overlay, stored collapse %s — DoD-11",
    (stored) => {
      const { storage } = storageHolding(stored);
      const shell = createShellState(storage);
      expandTree(shell, true, storage);
      expect(shell.overlayOpen).toBe(true);
    },
  );

  it.each<[boolean]>([[false], [true]])(
    "expandTree leaves navCollapsed (%s) untouched — DoD-11",
    (stored) => {
      const { storage } = storageHolding(stored);
      const shell = createShellState(storage);
      expandTree(shell, true, storage);
      expect(shell.navCollapsed).toBe(stored);
    },
  );

  it.each<[boolean]>([[false], [true]])(
    "expandTree writes nothing to storage, stored collapse %s — DoD-11",
    (stored) => {
      const { storage, setItem } = storageHolding(stored);
      expandTree(createShellState(storage), true, storage);
      expect(setItem).not.toHaveBeenCalled();
    },
  );

  it.each<[boolean]>([[false], [true]])(
    "collapseTree closes the overlay, stored collapse %s — DoD-11",
    (stored) => {
      const { storage } = storageHolding(stored);
      const shell = createShellState(storage);
      expandTree(shell, true, storage);
      collapseTree(shell, true, storage);
      expect(shell.overlayOpen).toBe(false);
    },
  );

  it.each<[boolean]>([[false], [true]])(
    "collapseTree leaves navCollapsed (%s) untouched — DoD-11",
    (stored) => {
      const { storage } = storageHolding(stored);
      const shell = createShellState(storage);
      expandTree(shell, true, storage);
      collapseTree(shell, true, storage);
      expect(shell.navCollapsed).toBe(stored);
    },
  );

  it.each<[boolean]>([[false], [true]])(
    "neither narrow toggle writes to storage, stored collapse %s — DoD-11",
    (stored) => {
      const { storage, setItem } = storageHolding(stored);
      const shell = createShellState(storage);
      expandTree(shell, true, storage);
      collapseTree(shell, true, storage);
      expect(setItem).not.toHaveBeenCalled();
    },
  );

  it.each<[boolean]>([[false], [true]])(
    "closeOverlay closes the overlay and writes nothing, stored collapse %s — DoD-11",
    (stored) => {
      const { storage, setItem } = storageHolding(stored);
      const shell = createShellState(storage);
      expandTree(shell, true, storage);
      closeOverlay(shell);
      expect(shell.overlayOpen).toBe(false);
      expect(shell.navCollapsed).toBe(stored);
      expect(setItem).not.toHaveBeenCalled();
    },
  );

  it("closeOverlay on an already closed overlay keeps it closed — DoD-11", () => {
    const shell = createShellState(null);
    closeOverlay(shell);
    expect(shell.overlayOpen).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("the toggles are observable writes", () => {
  it("an autorun reading showsRail re-runs after a wide collapseTree — DoD-12", () => {
    const { storage } = storageHolding(false);
    const shell = createShellState(storage);
    const seen: boolean[] = [];
    const dispose = autorun(() => {
      seen.push(showsRail(shell, false));
    });
    collapseTree(shell, false, storage);
    dispose();
    expect(seen).toEqual([false, true]);
  });

  it("an autorun reading showsRail re-runs after a narrow collapseTree — DoD-12", () => {
    const { storage } = storageHolding(false);
    const shell = createShellState(storage);
    expandTree(shell, true, storage);
    const seen: boolean[] = [];
    const dispose = autorun(() => {
      seen.push(showsRail(shell, true));
    });
    collapseTree(shell, true, storage);
    dispose();
    expect(seen).toEqual([false, true]);
  });

  it("an autorun reading shellClassName re-runs after a narrow expandTree — DoD-12", () => {
    const shell = createShellState(null);
    const seen: string[] = [];
    const dispose = autorun(() => {
      seen.push(shellClassName(shell, true));
    });
    expandTree(shell, true, null);
    dispose();
    expect(seen.length).toBe(2);
    expect(classesOf(seen[1] ?? "")).toContain("nav-overlay-open");
  });
});

// ---------------------------------------------------------------------------
describe("browserLayoutStorage is the one window.localStorage access", () => {
  afterEach(() => {
    window.localStorage.clear();
  });

  it("returns the document's localStorage — DoD-13", () => {
    expect(browserLayoutStorage()).toBe(window.localStorage);
  });

  it("the returned storage reads and writes the document's localStorage — DoD-13", () => {
    const storage = browserLayoutStorage();
    expect(storage).not.toBeNull();
    storage?.setItem(WORKSPACE_LAYOUT_KEY, "zq-probe");
    expect(window.localStorage.getItem(WORKSPACE_LAYOUT_KEY)).toBe("zq-probe");
    expect(storage?.getItem(WORKSPACE_LAYOUT_KEY)).toBe("zq-probe");
  });

  it("returns null when accessing window.localStorage throws — DoD-13", () => {
    expect(withThrowingLocalStorage(() => browserLayoutStorage())).toBeNull();
  });

  it("does not rethrow when accessing window.localStorage throws — DoD-13", () => {
    expect(() => withThrowingLocalStorage(() => browserLayoutStorage())).not.toThrow();
  });

  it("recovers the real localStorage once the access stops throwing — DoD-13", () => {
    withThrowingLocalStorage(() => browserLayoutStorage());
    expect(browserLayoutStorage()).toBe(window.localStorage);
  });
});
