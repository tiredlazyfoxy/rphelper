// Feature 016, step 005 — the session screen's two-part layout: the stream column and the
// note wall `aside` (DoD-7..DoD-11; D2, D3, D10, D11; US-094.AC-1/AC-2, UC-072).
// DoD-1..DoD-6 (the state module) live in tests/app/noteWallState.test.ts, DoD-12 in
// tests/stylesheets.test.ts; DoD-13 is [manual/live] and carries no test.
//
// Rendered inside `AppProviders`, no router. `narrow` is a prop here, so no `matchMedia`
// stub is needed (005.context.md). A closed wall is queried with `{ hidden: true }`; "not
// accessible" means not found by role without it (016 context.md, "Test conventions").
// jsdom applies no stylesheet, so the layout contract asserted here is the classes on the
// root (the stream column's parent) and on the `aside` — the CSS contract of D11.
// Controls are found by their accessible names (the strings table): "Note wall",
// "Pin notes" / "Unpin notes", "Close notes".
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { runInAction } from "mobx";
import { useEffect } from "react";
import type * as React from "react";
import { describe, expect, it, vi } from "vitest";
import { NoteWallLayout } from "../../src/app/NoteWallLayout";
import { dismissWall, NoteWallState, openWall, toggleWallPin } from "../../src/app/noteWallState";
import type { LayoutStorage } from "../../src/app/workspaceLayout";
import { AppProviders } from "../../src/shared/AppProviders";

const LAYOUT_KEY = "rphelper.workspace-layout";

const WALL_NAME = /^note wall$/i;
/** The wall's exact aria-label string (the strings table), for direct attribute checks. */
const WALL_LABEL = "Note wall";
const PIN_NAME = /^pin notes$/i;
const UNPIN_NAME = /^unpin notes$/i;
const CLOSE_NAME = /^close notes$/i;

const STREAM_NAME = "Stream probe zq-51";
const WALL_PROBE_NAME = "Wall probe zq-52";

const SESSION_CLASS = "app-session";
const PINNED_CLASS = "wall-pinned";
const STREAM_CLASS = "app-stream";
const WALL_CLASS = "app-wall";
const OPEN_CLASS = "wall-open";

type GetItem = (key: string) => string | null;
type SetItem = (key: string, value: string) => void;
type User = ReturnType<typeof userEvent.setup>;

function newUser(): User {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

// ---------------------------------------------------------------- helpers

/** An in-memory `LayoutStorage` whose two members are spies. */
function fakeStorage(record?: { navCollapsed: boolean; wallPinned: boolean }) {
  const entries = new Map<string, string>();
  if (record !== undefined) entries.set(LAYOUT_KEY, JSON.stringify(record));
  const getItem = vi.fn<GetItem>((key) => entries.get(key) ?? null);
  const setItem = vi.fn<SetItem>((key, value) => {
    entries.set(key, value);
  });
  const storage: LayoutStorage = { getItem, setItem };
  return { storage, getItem, setItem, entries };
}

function storedRecord(entries: Map<string, string>): Record<string, unknown> {
  const raw = entries.get(LAYOUT_KEY);
  expect(raw).toBeDefined();
  return JSON.parse(raw ?? "null") as Record<string, unknown>;
}

function stateOf(pinned: boolean, open: boolean): NoteWallState {
  const state = new NoteWallState(pinned);
  runInAction(() => {
    state.open = open;
  });
  return state;
}

function streamContent(): React.JSX.Element {
  return <button type="button">{STREAM_NAME}</button>;
}

function wallContent(): React.JSX.Element {
  return <button type="button">{WALL_PROBE_NAME}</button>;
}

type LayoutOptions = {
  state: NoteWallState;
  narrow?: boolean;
  storage?: LayoutStorage | null;
  wall?: React.ReactNode;
};

function layoutTree(options: LayoutOptions): React.JSX.Element {
  return (
    <AppProviders>
      <NoteWallLayout
        state={options.state}
        narrow={options.narrow ?? false}
        storage={options.storage ?? null}
        stream={streamContent()}
        wall={options.wall ?? wallContent()}
      />
    </AppProviders>
  );
}

function renderLayout(options: LayoutOptions) {
  const result = render(layoutTree(options));
  const rerenderWith = (next: LayoutOptions) => result.rerender(layoutTree(next));
  return { ...result, rerenderWith };
}

/** The stream column: the element of class app-stream that holds the stream content. */
function streamColumn(): HTMLElement {
  const probe = screen.getByRole("button", { name: STREAM_NAME, hidden: true });
  const column = probe.closest(`.${STREAM_CLASS}`);
  expect(column).not.toBeNull();
  return column as HTMLElement;
}

/** The layout's root: the stream column's parent. */
function layoutRoot(): HTMLElement {
  const root = streamColumn().parentElement;
  expect(root).not.toBeNull();
  return root as HTMLElement;
}

/**
 * The wall, found whether or not it is accessible. No `name` filter: the accessible-name
 * computation yields "" for an element that itself carries aria-hidden="true", so a closed
 * wall is matched by role with `hidden: true` and its `aria-label` is asserted directly.
 */
function anyWall(): HTMLElement {
  const walls = screen
    .getAllByRole("complementary", { hidden: true })
    .filter((el) => el.getAttribute("aria-label") === WALL_LABEL);
  expect(walls).toHaveLength(1);
  return walls[0] as HTMLElement;
}

/** The wall, found only while accessible. */
function accessibleWall(): HTMLElement {
  return screen.getByRole("complementary", { name: WALL_NAME });
}

function wallIsAccessible(): boolean {
  return screen.queryByRole("complementary", { name: WALL_NAME }) !== null;
}

// ---------------------------------------------------------------------------
describe("a closed floating wall is mounted but hidden", () => {
  it("the stream content is accessible — DoD-7", () => {
    renderLayout({ state: stateOf(false, false) });
    expect(screen.getByRole("button", { name: STREAM_NAME })).toBeInTheDocument();
  });

  it("the stream content sits in the app-stream column under the app-session root — DoD-7", () => {
    renderLayout({ state: stateOf(false, false) });
    expect(streamColumn()).toBeInTheDocument();
    expect(layoutRoot().classList.contains(SESSION_CLASS)).toBe(true);
  });

  it("no complementary landmark is found by role without hidden — DoD-7", () => {
    renderLayout({ state: stateOf(false, false) });
    expect(screen.queryByRole("complementary")).toBeNull();
  });

  it("with hidden the Note wall aside is found — DoD-7", () => {
    renderLayout({ state: stateOf(false, false) });
    const wall = anyWall();
    expect(wall.tagName.toLowerCase()).toBe("aside");
    expect(wall.getAttribute("aria-label")).toBe(WALL_LABEL);
  });

  it("the closed aside carries inert and aria-hidden true — DoD-7", () => {
    renderLayout({ state: stateOf(false, false) });
    const wall = anyWall();
    expect(wall.hasAttribute("inert")).toBe(true);
    expect(wall.getAttribute("inert")).not.toBe("false");
    expect(wall.getAttribute("aria-hidden")).toBe("true");
  });

  it("the closed aside contains the wall content — DoD-7", () => {
    renderLayout({ state: stateOf(false, false) });
    expect(
      within(anyWall()).getByRole("button", { name: WALL_PROBE_NAME, hidden: true }),
    ).toBeInTheDocument();
  });

  it("the closed aside is inside the layout root, after the stream column — DoD-7", () => {
    renderLayout({ state: stateOf(false, false) });
    const root = layoutRoot();
    const wall = anyWall();
    expect(root.contains(wall)).toBe(true);
    expect(streamColumn().contains(wall)).toBe(false);
    expect(
      streamColumn().compareDocumentPosition(wall) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("the closed aside carries app-wall and not wall-open — DoD-7", () => {
    renderLayout({ state: stateOf(false, false) });
    const wall = anyWall();
    expect(wall.classList.contains(WALL_CLASS)).toBe(true);
    expect(wall.classList.contains(OPEN_CLASS)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("an opened floating wall shows over the stream", () => {
  it("after openWall the Note wall is accessible — DoD-8", () => {
    const state = stateOf(false, false);
    renderLayout({ state });
    act(() => {
      openWall(state);
    });
    expect(accessibleWall()).toBeInTheDocument();
  });

  it("the open wall shows Pin notes and Close notes — DoD-8", () => {
    const state = stateOf(false, false);
    renderLayout({ state });
    act(() => {
      openWall(state);
    });
    const wall = accessibleWall();
    expect(within(wall).getByRole("button", { name: PIN_NAME })).toBeInTheDocument();
    expect(within(wall).getByRole("button", { name: CLOSE_NAME })).toBeInTheDocument();
  });

  it("the open wall has neither inert nor aria-hidden — DoD-8", () => {
    const state = stateOf(false, false);
    renderLayout({ state });
    act(() => {
      openWall(state);
    });
    const wall = accessibleWall();
    expect(wall.hasAttribute("inert")).toBe(false);
    expect(wall.hasAttribute("aria-hidden")).toBe(false);
  });

  it("the open wall carries wall-open — DoD-8", () => {
    const state = stateOf(false, false);
    renderLayout({ state });
    act(() => {
      openWall(state);
    });
    const wall = accessibleWall();
    expect(wall.classList.contains(WALL_CLASS)).toBe(true);
    expect(wall.classList.contains(OPEN_CLASS)).toBe(true);
  });

  it("the root lacks wall-pinned while the wall floats open — DoD-8", () => {
    const state = stateOf(false, false);
    renderLayout({ state });
    act(() => {
      openWall(state);
    });
    expect(layoutRoot().classList.contains(SESSION_CLASS)).toBe(true);
    expect(layoutRoot().classList.contains(PINNED_CLASS)).toBe(false);
  });

  it("the open wall's content is accessible — DoD-8", () => {
    const state = stateOf(false, false);
    renderLayout({ state });
    act(() => {
      openWall(state);
    });
    expect(
      within(accessibleWall()).getByRole("button", { name: WALL_PROBE_NAME }),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
describe("a pinned wall is a column at wide width and reverts to floating when narrow", () => {
  it("wide: the root carries wall-pinned — DoD-9", () => {
    renderLayout({ state: stateOf(true, false), narrow: false });
    expect(layoutRoot().classList.contains(SESSION_CLASS)).toBe(true);
    expect(layoutRoot().classList.contains(PINNED_CLASS)).toBe(true);
  });

  it("wide: the wall is accessible with Unpin notes — DoD-9", () => {
    renderLayout({ state: stateOf(true, false), narrow: false });
    const wall = accessibleWall();
    expect(within(wall).getByRole("button", { name: UNPIN_NAME })).toBeInTheDocument();
    expect(within(wall).queryByRole("button", { name: PIN_NAME })).toBeNull();
  });

  it("wide: the pinned wall has no wall-open class, inert or aria-hidden — DoD-9", () => {
    renderLayout({ state: stateOf(true, false), narrow: false });
    const wall = accessibleWall();
    expect(wall.classList.contains(WALL_CLASS)).toBe(true);
    expect(wall.classList.contains(OPEN_CLASS)).toBe(false);
    expect(wall.hasAttribute("inert")).toBe(false);
    expect(wall.hasAttribute("aria-hidden")).toBe(false);
  });

  it("narrow: the same state's root lacks wall-pinned — DoD-9", () => {
    renderLayout({ state: stateOf(true, false), narrow: true });
    expect(layoutRoot().classList.contains(SESSION_CLASS)).toBe(true);
    expect(layoutRoot().classList.contains(PINNED_CLASS)).toBe(false);
  });

  it("narrow: the wall is not accessible until openWall — DoD-9", () => {
    const state = stateOf(true, false);
    renderLayout({ state, narrow: true });
    expect(wallIsAccessible()).toBe(false);
    expect(anyWall().getAttribute("aria-hidden")).toBe("true");
    act(() => {
      openWall(state);
    });
    expect(wallIsAccessible()).toBe(true);
    expect(accessibleWall().classList.contains(OPEN_CLASS)).toBe(true);
    expect(layoutRoot().classList.contains(PINNED_CLASS)).toBe(false);
  });

  it("flipping narrow on a mounted pinned wall reverts and restores the column — DoD-9", () => {
    const state = stateOf(true, false);
    const { rerenderWith } = renderLayout({ state, narrow: false });
    expect(wallIsAccessible()).toBe(true);
    rerenderWith({ state, narrow: true });
    expect(layoutRoot().classList.contains(PINNED_CLASS)).toBe(false);
    expect(wallIsAccessible()).toBe(false);
    rerenderWith({ state, narrow: false });
    expect(layoutRoot().classList.contains(PINNED_CLASS)).toBe(true);
    expect(wallIsAccessible()).toBe(true);
  });
});

// ---------------------------------------------------------------------------
describe("the wall's header controls", () => {
  it("pressing Pin notes stores wallPinned true — DoD-10", async () => {
    const user = newUser();
    const { storage, entries } = fakeStorage({ navCollapsed: false, wallPinned: false });
    const state = stateOf(false, true);
    renderLayout({ state, storage });
    await user.click(within(accessibleWall()).getByRole("button", { name: PIN_NAME }));
    expect(storedRecord(entries).wallPinned).toBe(true);
  });

  it("pressing Pin notes relabels the control Unpin notes — DoD-10", async () => {
    const user = newUser();
    const { storage } = fakeStorage({ navCollapsed: false, wallPinned: false });
    const state = stateOf(false, true);
    renderLayout({ state, storage });
    await user.click(within(accessibleWall()).getByRole("button", { name: PIN_NAME }));
    const wall = accessibleWall();
    expect(within(wall).getByRole("button", { name: UNPIN_NAME })).toBeInTheDocument();
    expect(within(wall).queryByRole("button", { name: PIN_NAME })).toBeNull();
  });

  it("pressing Unpin notes stores wallPinned false — DoD-10", async () => {
    const user = newUser();
    const { storage, entries } = fakeStorage({ navCollapsed: false, wallPinned: true });
    const state = stateOf(true, false);
    renderLayout({ state, storage });
    await user.click(within(accessibleWall()).getByRole("button", { name: UNPIN_NAME }));
    expect(storedRecord(entries).wallPinned).toBe(false);
  });

  it("pressing Unpin notes leaves the wall accessible, floating open — DoD-10", async () => {
    const user = newUser();
    const { storage } = fakeStorage({ navCollapsed: false, wallPinned: true });
    const state = stateOf(true, false);
    renderLayout({ state, storage });
    await user.click(within(accessibleWall()).getByRole("button", { name: UNPIN_NAME }));
    const wall = accessibleWall();
    expect(within(wall).getByRole("button", { name: PIN_NAME })).toBeInTheDocument();
    expect(wall.classList.contains(OPEN_CLASS)).toBe(true);
    expect(layoutRoot().classList.contains(PINNED_CLASS)).toBe(false);
  });

  it("pressing Close notes on an open floating wall makes it not accessible — DoD-10", async () => {
    const user = newUser();
    const { storage } = fakeStorage({ navCollapsed: false, wallPinned: false });
    const state = stateOf(false, true);
    renderLayout({ state, storage });
    await user.click(within(accessibleWall()).getByRole("button", { name: CLOSE_NAME }));
    expect(wallIsAccessible()).toBe(false);
    expect(anyWall().getAttribute("aria-hidden")).toBe("true");
  });

  it("pressing Close notes on a wide pinned wall makes it not accessible — DoD-10", async () => {
    const user = newUser();
    const { storage, entries } = fakeStorage({ navCollapsed: false, wallPinned: true });
    const state = stateOf(true, false);
    renderLayout({ state, storage });
    await user.click(within(accessibleWall()).getByRole("button", { name: CLOSE_NAME }));
    expect(wallIsAccessible()).toBe(false);
    expect(layoutRoot().classList.contains(PINNED_CLASS)).toBe(false);
    expect(storedRecord(entries).wallPinned).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("the wall content is mounted once and never remounted", () => {
  it("a mount-counting wall child mounts once across open, close, pin, unpin and a narrow flip — DoD-11", () => {
    let mounts = 0;
    function MountCounter(): React.JSX.Element {
      useEffect(() => {
        mounts += 1;
      }, []);
      return <p>counted zq-53</p>;
    }
    const { storage } = fakeStorage({ navCollapsed: false, wallPinned: false });
    const state = stateOf(false, false);
    const wall = <MountCounter />;
    const { rerenderWith } = renderLayout({ state, storage, narrow: false, wall });
    expect(mounts).toBe(1);

    act(() => {
      openWall(state);
    });
    act(() => {
      dismissWall(state, storage, false);
    });
    act(() => {
      openWall(state);
    });
    act(() => {
      toggleWallPin(state, storage); // pin
    });
    rerenderWith({ state, storage, narrow: true, wall });
    rerenderWith({ state, storage, narrow: false, wall });
    act(() => {
      toggleWallPin(state, storage); // unpin
    });
    act(() => {
      dismissWall(state, storage, false);
    });

    expect(mounts).toBe(1);
  });

  it("an uncontrolled input in the wall keeps typed text across close and reopen — DoD-11", async () => {
    const user = newUser();
    const { storage } = fakeStorage({ navCollapsed: false, wallPinned: false });
    const state = stateOf(false, true);
    const wall = <input aria-label="Wall draft zq-54" defaultValue="" />;
    renderLayout({ state, storage, wall });

    await user.type(
      within(accessibleWall()).getByRole("textbox", { name: "Wall draft zq-54" }),
      "kept draft zq",
    );
    await user.click(within(accessibleWall()).getByRole("button", { name: CLOSE_NAME }));
    expect(wallIsAccessible()).toBe(false);

    act(() => {
      openWall(state);
    });
    const input = within(accessibleWall()).getByRole("textbox", {
      name: "Wall draft zq-54",
    }) as HTMLInputElement;
    expect(input.value).toBe("kept draft zq");
  });
});
