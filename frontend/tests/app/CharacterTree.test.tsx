// Feature 009, step 008 — the tree's header and character level (DoD-1..DoD-6).
// DoD-7 lives in WorkspaceShell.test.tsx, DoD-8..DoD-10 in App.test.tsx, and DoD-11 is the
// stub amendment in AppBoot.test.tsx / entries.test.tsx. DoD-12 is [manual/live] and carries
// no test.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 008.context.md and context.md (D4 the non-persisted "Show archived" switch, D12 every
// failure is inline and nothing is notified, D13 the header's two actions, no chevron and no
// session rows).
//
// Recognition conventions (from the spec's wording, for the verifier):
// - The tree's names are the contract: the icon buttons "Search" and "New character", the
//   switch "Show archived", the list's accessible name "Characters", the badge text exactly
//   "Archived", the failure sentence "Could not load characters" and its button "Retry".
// - The list: 008.context.md sanctions either a `ul` with `aria-label` (role `list`) or the
//   equivalent landmark, so `charactersList()` accepts role `list` or role `navigation`
//   carrying that name.
// - The switch: Mantine's `Switch` exposes role `switch` (older markup exposes `checkbox`),
//   so `showArchivedSwitch()` accepts either, found by its accessible name.
// - A row: the router link whose text carries the character's name; its badge may sit in the
//   link or in the surrounding list item, so badge queries scope to `rowBlock`.
// - In-entry navigation: a location probe rendered beside the tree in the same MemoryRouter;
//   document navigation is `documentNavigation.assign` (the shared client's only seam onto
//   `window.location`).
// - A notification: `.mantine-Notification-root`.
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { CharacterTree } from "../../src/app/CharacterTree";
import type { Character } from "../../src/app/charactersApi";
import { CharactersState } from "../../src/app/charactersState";
import { documentNavigation } from "../../src/shared/api";
import { AppProviders } from "../../src/shared/AppProviders";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string };
type User = ReturnType<typeof userEvent.setup>;

// ---------------------------------------------------------------- the spec's names
const SEARCH_NAME = /^search$/i;
const NEW_CHARACTER_NAME = /^new character$/i;
const SHOW_ARCHIVED_NAME = /^show archived$/i;
const CHARACTERS_LIST_NAME = /^characters$/i;
const RETRY_NAME = /^retry$/i;
const ARCHIVED_BADGE = "Archived";
const LOAD_FAILED_TEXT = "Could not load characters";

const NOTIFICATION = ".mantine-Notification-root";

const COLLECTION_PATH = "/api/characters";
const INCLUDE_ARCHIVED_SEARCH = "?include_archived=true";
const SEARCH_PATH = "/search";
const NEW_CHARACTER_PATH = "/characters/new";

// ---------------------------------------------------------------- fixtures
// Both ids are past Number.MAX_SAFE_INTEGER (9007199254740991), so any coercion of the
// payload's id would show up in the row's href (context.md "Ids are strings"). The payload
// order below is neither alphabetical nor id-ordered, so "in the payload's order" is
// distinguishable from any sort the tree might apply.
const ID_CORVIN = "9007199254740993";
const ID_ARIA = "7250000000000000011";

const CORVIN: Character = {
  id: ID_CORVIN,
  name: "Corvin Hale",
  sheet: "A duelist who counts his scars.",
  archived_at: null,
  created_at: "2026-02-01T08:15:42.000000+00:00",
  updated_at: "2026-02-01T08:15:42.000000+00:00",
};

const ARIA: Character = {
  id: ID_ARIA,
  name: "Aria Vance",
  sheet: "A scribe who never finishes a sentence.",
  archived_at: null,
  created_at: "2026-03-14T09:26:53.000000+00:00",
  updated_at: "2026-03-14T09:26:53.000000+00:00",
};

const ARCHIVED_ARIA: Character = {
  ...ARIA,
  archived_at: "2026-04-05T10:00:00.000000+00:00",
  updated_at: "2026-04-05T10:00:00.000000+00:00",
};

/** The payload order the tree must preserve. */
const PAYLOAD = [CORVIN, ARIA];

let navigate: MockInstance<(url: string) => void>;

beforeEach(() => {
  navigate = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- fetch harness
function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function serverError(): Response {
  return jsonResponse({ error: { code: "internal_error", message: "ql-77.", detail: {} } }, 500);
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

/** Records every request in order and answers through `handler`. */
function stubBackend(handler: (request: Seen) => Response | Promise<Response>) {
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>(async (input, init) => {
    const url = requestUrl(input);
    const request: Seen = {
      method: requestMethod(input, init),
      path: url.pathname,
      search: url.search,
    };
    calls.push(request);
    return handler(request);
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

/** Answers the listing from `rows`, honouring the include-archived flag. */
function serveListing(working: Character[], archived: Character[] = []) {
  return stubBackend((request) => {
    if (request.method === "GET" && request.path === COLLECTION_PATH) {
      const includeArchived = request.search === INCLUDE_ARCHIVED_SEARCH;
      const rows = includeArchived ? [...working, ...archived] : working;
      return jsonResponse({ characters: rows }, 200);
    }
    return jsonResponse({ error: { code: "not_found", message: "", detail: {} } }, 404);
  });
}

function listRequests(calls: Seen[]): Seen[] {
  return calls.filter((call) => call.method === "GET" && call.path === COLLECTION_PATH);
}

async function flush(rounds = 6): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => setImmediate(resolve));
    });
  }
}

function newUser(): User {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

// ---------------------------------------------------------------- render
function LocationProbe() {
  const location = useLocation();
  return <output data-testid="probe-location">{location.pathname}</output>;
}

const TREE_HOST = "tree-host";

/**
 * The tree alone, at `initialPath`, with one workspace `CharactersState` (D11) and a location
 * probe beside it. The tree sits outside `<Routes>` in the shell (008.context.md), so nothing
 * declares routes here.
 */
function renderTree(initialPath = "/", characters = new CharactersState()) {
  const view = render(
    <AppProviders>
      <MemoryRouter initialEntries={[initialPath]}>
        <div data-testid={TREE_HOST}>
          <CharacterTree characters={characters} />
        </div>
        <LocationProbe />
      </MemoryRouter>
    </AppProviders>,
  );
  return { characters, view };
}

// ---------------------------------------------------------------- queries
function tree(): HTMLElement {
  return screen.getByTestId(TREE_HOST);
}

function currentPath(): string {
  return screen.getByTestId("probe-location").textContent ?? "";
}

/** The character level, by its accessible name (a list or the equivalent landmark). */
function charactersList(): HTMLElement {
  const asList = within(tree()).queryByRole("list", { name: CHARACTERS_LIST_NAME });
  if (asList !== null) {
    return asList;
  }
  return within(tree()).getByRole("navigation", { name: CHARACTERS_LIST_NAME });
}

function rowLinks(): HTMLElement[] {
  return within(charactersList()).queryAllByRole("link");
}

function rowTexts(): string[] {
  return rowLinks().map((link) => (link.textContent ?? "").trim());
}

function queryRowFor(name: string): HTMLElement | null {
  return rowLinks().find((link) => (link.textContent ?? "").includes(name)) ?? null;
}

function rowFor(name: string): HTMLElement {
  const link = queryRowFor(name);
  if (link === null) {
    throw new Error(`no tree row for "${name}"`);
  }
  return link;
}

/** A row's whole block: the link, or the list item it sits in when the badge is a sibling. */
function rowBlock(name: string): HTMLElement {
  const link = rowFor(name);
  return link.closest("li") ?? link;
}

function treeButton(name: RegExp): HTMLElement {
  return within(tree()).getByRole("button", { name });
}

function showArchivedSwitch(): HTMLElement {
  const asSwitch = within(tree()).queryByRole("switch", { name: SHOW_ARCHIVED_NAME });
  if (asSwitch !== null) {
    return asSwitch;
  }
  return within(tree()).getByRole("checkbox", { name: SHOW_ARCHIVED_NAME });
}

function switchCount(): number {
  return (
    within(tree()).queryAllByRole("switch").length +
    within(tree()).queryAllByRole("checkbox").length
  );
}

function notificationsShown(): Element[] {
  return Array.from(document.querySelectorAll(NOTIFICATION));
}

// ---------------------------------------------------------------------------
describe("the character level renders the server's rows (US-022.AC-1)", () => {
  it("requests the listing once and renders one link per character in the payload's order — DoD-1", async () => {
    const { calls } = serveListing(PAYLOAD);
    renderTree();
    await flush();

    const requests = listRequests(calls);
    expect(requests).toHaveLength(1);
    expect(requests[0]).toEqual({ method: "GET", path: COLLECTION_PATH, search: "" });
    expect(calls).toHaveLength(1);

    expect(charactersList()).toBeInTheDocument();
    expect(rowTexts()).toEqual([CORVIN.name, ARIA.name]);
  });

  it("each row links to /characters/<id> with the id string verbatim — DoD-1", async () => {
    serveListing(PAYLOAD);
    renderTree();
    await flush();

    expect(rowFor(CORVIN.name)).toHaveAttribute("href", `/characters/${ID_CORVIN}`);
    expect(rowFor(ARIA.name)).toHaveAttribute("href", `/characters/${ID_ARIA}`);
  });

  it("an empty listing renders no rows — DoD-1", async () => {
    serveListing([]);
    renderTree();
    await flush();

    expect(rowLinks()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("a row is an in-entry link that marks its own route", () => {
  it("clicking a row moves the in-entry router to /characters/<id> with no document navigation — DoD-2", async () => {
    const user = newUser();
    serveListing(PAYLOAD);
    renderTree();
    await flush();
    expect(currentPath()).toBe("/");

    await user.click(rowFor(ARIA.name));
    await flush();

    expect(currentPath()).toBe(`/characters/${ID_ARIA}`);
    expect(navigate).not.toHaveBeenCalled();
  });

  it("rendered at /characters/<id>, that row alone carries aria-current=page — DoD-2", async () => {
    serveListing(PAYLOAD);
    renderTree(`/characters/${ID_ARIA}`);
    await flush();

    expect(rowFor(ARIA.name)).toHaveAttribute("aria-current", "page");
    expect(rowFor(CORVIN.name).getAttribute("aria-current")).not.toBe("page");
  });

  it("at /characters/new no row is current — DoD-2", async () => {
    serveListing(PAYLOAD);
    renderTree(NEW_CHARACTER_PATH);
    await flush();

    for (const link of rowLinks()) {
      expect(link.getAttribute("aria-current")).not.toBe("page");
    }
  });
});

// ---------------------------------------------------------------------------
describe("the header's two actions navigate in-entry (D13)", () => {
  it("Search moves the in-entry router to /search — DoD-3", async () => {
    const user = newUser();
    serveListing(PAYLOAD);
    renderTree();
    await flush();

    await user.click(treeButton(SEARCH_NAME));
    await flush();

    expect(currentPath()).toBe(SEARCH_PATH);
    expect(navigate).not.toHaveBeenCalled();
  });

  it("New character moves the in-entry router to /characters/new — DoD-3", async () => {
    const user = newUser();
    serveListing(PAYLOAD);
    renderTree();
    await flush();

    await user.click(treeButton(NEW_CHARACTER_NAME));
    await flush();

    expect(currentPath()).toBe(NEW_CHARACTER_PATH);
    expect(navigate).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("the Show archived switch re-requests the listing (D4, R6)", () => {
  it("is off on a fresh mount and the first request carries no flag — DoD-4", async () => {
    const { calls } = serveListing([CORVIN], [ARCHIVED_ARIA]);
    renderTree();
    await flush();

    expect(showArchivedSwitch()).not.toBeChecked();
    expect(listRequests(calls)).toHaveLength(1);
    expect(listRequests(calls)[0].search).toBe("");
    expect(queryRowFor(ARIA.name)).toBeNull();
  });

  it("turning it on requests include_archived=true and badges the archived row — DoD-4", async () => {
    const user = newUser();
    const { calls } = serveListing([CORVIN], [ARCHIVED_ARIA]);
    renderTree();
    await flush();

    await user.click(showArchivedSwitch());
    await flush();

    const requests = listRequests(calls);
    expect(requests).toHaveLength(2);
    expect(requests[1]).toEqual({
      method: "GET",
      path: COLLECTION_PATH,
      search: INCLUDE_ARCHIVED_SEARCH,
    });

    expect(within(rowBlock(ARIA.name)).getByText(ARCHIVED_BADGE)).toBeInTheDocument();
    expect(within(rowBlock(CORVIN.name)).queryByText(ARCHIVED_BADGE)).toBeNull();
  });

  it("turning it off again requests the working list and drops the archived row — DoD-4", async () => {
    const user = newUser();
    const { calls } = serveListing([CORVIN], [ARCHIVED_ARIA]);
    renderTree();
    await flush();

    await user.click(showArchivedSwitch());
    await flush();
    expect(queryRowFor(ARIA.name)).not.toBeNull();

    await user.click(showArchivedSwitch());
    await flush();

    const requests = listRequests(calls);
    expect(requests).toHaveLength(3);
    expect(requests[2]).toEqual({ method: "GET", path: COLLECTION_PATH, search: "" });
    expect(showArchivedSwitch()).not.toBeChecked();
    expect(queryRowFor(ARIA.name)).toBeNull();
    expect(queryRowFor(CORVIN.name)).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("a failed load reports inside the tree (D12)", () => {
  it("renders Could not load characters and Retry, and raises no notification — DoD-5", async () => {
    stubBackend(() => serverError());
    renderTree();
    await flush();

    expect(within(tree()).getByText(LOAD_FAILED_TEXT)).toBeInTheDocument();
    expect(treeButton(RETRY_NAME)).toBeInTheDocument();
    expect(notificationsShown()).toEqual([]);
  });

  it("a transport failure reports the same way — DoD-5", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<FetchFn>(() => Promise.reject(new TypeError("Failed to fetch"))),
    );
    renderTree();
    await flush();

    expect(within(tree()).getByText(LOAD_FAILED_TEXT)).toBeInTheDocument();
    expect(treeButton(RETRY_NAME)).toBeInTheDocument();
    expect(notificationsShown()).toEqual([]);
  });

  it("Retry requests the listing again and renders the rows on success — DoD-5", async () => {
    const user = newUser();
    let failNext = true;
    const { calls } = stubBackend((request) => {
      if (request.method === "GET" && request.path === COLLECTION_PATH) {
        if (failNext) {
          failNext = false;
          return serverError();
        }
        return jsonResponse({ characters: PAYLOAD }, 200);
      }
      return serverError();
    });
    renderTree();
    await flush();
    expect(listRequests(calls)).toHaveLength(1);

    await user.click(treeButton(RETRY_NAME));
    await flush();

    expect(listRequests(calls)).toHaveLength(2);
    expect(rowTexts()).toEqual([CORVIN.name, ARIA.name]);
    expect(within(tree()).queryByText(LOAD_FAILED_TEXT)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("no chevron and no session rows in 009 (D13)", () => {
  it("the ready tree's only buttons are Search and New character — DoD-6", async () => {
    serveListing([CORVIN], [ARCHIVED_ARIA]);
    renderTree();
    await flush();
    expect(rowLinks()).toHaveLength(1);

    const names = within(tree())
      .getAllByRole("button")
      .map((button) => (button.getAttribute("aria-label") ?? button.textContent ?? "").trim());
    expect([...names].sort()).toEqual(["New character", "Search"]);
  });

  it("the switch is the tree's only other control and the rows are links — DoD-6", async () => {
    serveListing(PAYLOAD);
    renderTree();
    await flush();

    expect(switchCount()).toBe(1);
    expect(showArchivedSwitch()).toBeInTheDocument();
    expect(within(tree()).queryAllByRole("textbox")).toEqual([]);
    expect(rowLinks()).toHaveLength(PAYLOAD.length);
    expect(within(tree()).getAllByRole("link")).toHaveLength(PAYLOAD.length);
  });

  it("no row carries an expand or collapse control — DoD-6", async () => {
    serveListing(PAYLOAD);
    renderTree();
    await flush();

    for (const name of [CORVIN.name, ARIA.name]) {
      expect(within(rowBlock(name)).queryAllByRole("button")).toEqual([]);
    }
    expect(within(tree()).queryByRole("button", { name: /expand|collapse/i })).toBeNull();
  });
});
