// Feature 010, step 006 — the "Setups" section (DoD-1..DoD-9). DoD-10..DoD-12 render through
// 009's character screen and live in `tests/app/CharacterScreen.test.tsx`; DoD-13 is the
// amendment of 009's two test files; DoD-14 is [manual/live] and carries no test.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 006.context.md and the feature's context.md: D2 (the labelled "New setup" button, create and
// edit in a Mantine `Modal`, apply the server's row then close), D4 ("Show archived setups",
// archived rows badged, "Restore" in place of "Archive", no confirm), D11 (the section owns its
// state and applies the server's returned row — no refetch after a mutation), D12 (every
// failure is inline and nothing is notified), D13 (a table with an overflow menu per row and
// one neutral empty line).
//
// Recognition conventions (from the spec's wording, for the verifier):
// - The section is a region whose accessible name is "Setups"; every assertion about what the
//   section shows goes through `within(region())` (context.md "Scoping on the character
//   screen").
// - Mantine `Modal` and `Menu` render into portals, so dialogs and menu items are queried
//   through `screen`, never `within(region())` (context.md "Mantine portals").
// - The contract names and texts: the heading "Setups"; the button "New setup"; the switch
//   "Show archived setups"; "No setups yet."; "Could not load setups" plus "Retry"; the row
//   trigger "Actions for <name>"; the menu items "Edit", "Archive", "Restore"; the badge text
//   exactly "Archived"; the modal titles "New setup" / "Edit setup" with "Name",
//   "Description", "Create" / "Save" and "Cancel"; the sentences "Could not create the setup."
//   and "Could not archive the setup.".
// - A notification: `.mantine-Notification-root` (the repo's convention). 010 raises none.
// - `src/shared/MarkdownEditor` is replaced by the sanctioned stub (context.md "Test
//   conventions"), so "Description" is a plain labelled `<textarea>` in jsdom.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChangeEvent } from "react";
import { SetupsSection } from "../../src/app/SetupsSection";
import type { Setup } from "../../src/app/setupsApi";
import { AppProviders } from "../../src/shared/AppProviders";

vi.mock("../../src/shared/MarkdownEditor", async () => {
  const { createElement } = await import("react");
  type StubProps = {
    label: string;
    value: string;
    onChange: (markdown: string) => void;
    readOnly?: boolean;
  };
  return {
    MarkdownEditor: (props: StubProps) => {
      const id = `markdown-editor-${props.label.toLowerCase().replace(/\s+/g, "-")}`;
      return createElement(
        "div",
        null,
        createElement("label", { htmlFor: id }, props.label),
        createElement("textarea", {
          id,
          value: props.value,
          readOnly: props.readOnly ?? false,
          onChange: (event: ChangeEvent<HTMLTextAreaElement>) => props.onChange(event.target.value),
        }),
      );
    },
  };
});

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string; body: unknown };
type User = ReturnType<typeof userEvent.setup>;

// ---------------------------------------------------------------- the spec's names
const SETUPS_REGION = /^setups$/i;
const SETUPS_HEADING = /^setups$/i;
const NEW_SETUP_NAME = /^new setup$/i;
const SHOW_ARCHIVED_SETUPS = /^show archived setups$/i;
const NAME_LABEL = /^name$/i;
const DESCRIPTION_LABEL = /^description$/i;
const CREATE_NAME = /^create$/i;
const SAVE_NAME = /^save$/i;
const CANCEL_NAME = /^cancel$/i;
const RETRY_NAME = /^retry$/i;
const EDIT_ITEM = /^edit$/i;
const ARCHIVE_ITEM = /^archive$/i;
const RESTORE_ITEM = /^restore$/i;

const EMPTY_LINE = "No setups yet.";
const LOAD_FAILED_TEXT = "Could not load setups";
const CREATE_FAILED_TEXT = "Could not create the setup.";
const ARCHIVE_FAILED_TEXT = "Could not archive the setup.";
const ARCHIVED_BADGE = "Archived";
const NEW_SETUP_TITLE = "New setup";
const EDIT_SETUP_TITLE = "Edit setup";

const NOTIFICATION = ".mantine-Notification-root";

// ---------------------------------------------------------------- fixtures
// Ids are decimal strings past Number.MAX_SAFE_INTEGER (context.md "Ids are strings"); no
// fixture name is a substring of another, so a row is identified by the name it shows.
const CHARACTER_ID = "7250000000000000011";
const COLLECTION_PATH = `/api/characters/${CHARACTER_ID}/setups`;
const INCLUDE_ARCHIVED_SEARCH = "?include_archived=true";
const CREATED_ID = "9007199254740993"; // 2^53 + 1

/** `created_at` descends with the fixture order, while the ids ascend. */
const TAVERN: Setup = {
  id: "7250000000000000031",
  character_id: CHARACTER_ID,
  name: "Tavern brawl",
  description: "# The Hollow Tankard\n\nSomeone has already thrown the first stool.",
  archived_at: null,
  created_at: "2026-05-03T09:26:53.000000+00:00",
  updated_at: "2026-05-03T09:26:53.000000+00:00",
};

const HARBOUR: Setup = {
  id: "7250000000000000032",
  character_id: CHARACTER_ID,
  name: "Harbour at dusk",
  description: "Lanterns, tar, and a ship that should not be here.",
  archived_at: null,
  created_at: "2026-04-02T08:15:42.000000+00:00",
  updated_at: "2026-04-02T08:15:42.000000+00:00",
};

const CELLAR: Setup = {
  id: "7250000000000000033",
  character_id: CHARACTER_ID,
  name: "Cellar of maps",
  description: "Every map disagrees with the next.",
  archived_at: null,
  created_at: "2026-03-01T07:04:11.000000+00:00",
  updated_at: "2026-03-01T07:04:11.000000+00:00",
};

const ARCHIVED_TAVERN: Setup = {
  ...TAVERN,
  archived_at: "2026-05-10T10:00:00.000000+00:00",
  updated_at: "2026-05-10T10:00:00.000000+00:00",
};

const NEWEST_STAMP = "2026-06-01T12:00:00.000000+00:00";
const ACTION_STAMP = "2026-06-02T12:00:00.000000+00:00";

const TYPED_NAME = "Night market";
const TYPED_DESCRIPTION = "Stalls that close when you look at them.";
/** The name the server answers a PATCH with — the row must re-render from it, not the draft. */
const SAVED_NAME = "Stone quarry";
const EDITED_NAME = "Quarry road";

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

/** A domain envelope — the shape every non-2xx of ours carries. */
function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: "ql-77 went wrong.", detail: {} } }, status);
}

function serverError(): Response {
  return envelope("internal_error", 500);
}

function setupNotFound(): Response {
  return envelope("setup_not_found", 404);
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function parseBody(init?: RequestInit): unknown {
  const body = init?.body;
  if (body === undefined || body === null) return undefined;
  return JSON.parse(String(body)) as unknown;
}

type Failing = {
  listing?: boolean;
  create?: boolean;
  save?: boolean;
  archive?: boolean;
  restore?: boolean;
};

/**
 * The wire contract of the setups routes over an in-memory row set, every request recorded
 * in order. Only the listing honours the include-archived flag; a mutation answers the single
 * row it changed. `failing` turns one operation into a 500 (D12's inline failures).
 */
function serveSetups(rows: Setup[], failing: Failing = {}) {
  const order: Setup[] = [...rows];
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>(async (input, init) => {
    const url = requestUrl(input);
    const method = requestMethod(input, init);
    const body = parseBody(init);
    calls.push({ method, path: url.pathname, search: url.search, body });

    if (url.pathname === COLLECTION_PATH && method === "GET") {
      if (failing.listing === true) return serverError();
      const includeArchived = url.search === INCLUDE_ARCHIVED_SEARCH;
      const listed = order.filter((row) => includeArchived || row.archived_at === null);
      return jsonResponse({ setups: listed }, 200);
    }

    if (url.pathname === COLLECTION_PATH && method === "POST") {
      if (failing.create === true) return serverError();
      const sent = (body ?? {}) as { name?: string; description?: string };
      const created: Setup = {
        id: CREATED_ID,
        character_id: CHARACTER_ID,
        name: sent.name ?? "",
        description: sent.description ?? "",
        archived_at: null,
        created_at: NEWEST_STAMP,
        updated_at: NEWEST_STAMP,
      };
      order.unshift(created);
      return jsonResponse(created, 201);
    }

    const match = /^\/api\/setups\/([^/]+)(\/archive|\/restore)?$/.exec(url.pathname);
    if (match !== null) {
      const index = order.findIndex((row) => row.id === match[1]);
      if (index < 0) return setupNotFound();
      const row = order[index];
      const action = match[2];
      if (action === "/archive" && method === "POST") {
        if (failing.archive === true) return serverError();
        const next: Setup = { ...row, archived_at: ACTION_STAMP, updated_at: ACTION_STAMP };
        order[index] = next;
        return jsonResponse(next, 200);
      }
      if (action === "/restore" && method === "POST") {
        if (failing.restore === true) return serverError();
        const next: Setup = { ...row, archived_at: null, updated_at: ACTION_STAMP };
        order[index] = next;
        return jsonResponse(next, 200);
      }
      if (action === undefined && method === "PATCH") {
        if (failing.save === true) return serverError();
        const patch = (body ?? {}) as { name?: string; description?: string };
        // The server's stored name wins: it answers a name of its own, so a row rendered
        // from the draft instead of the response would show the typed value and fail.
        const next: Setup = {
          ...row,
          name: patch.name === undefined ? row.name : SAVED_NAME,
          description: patch.description ?? row.description,
          updated_at: ACTION_STAMP,
        };
        order[index] = next;
        return jsonResponse(next, 200);
      }
    }
    return setupNotFound();
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

function matching(calls: Seen[], method: string, path: string): Seen[] {
  return calls.filter((call) => call.method === method && call.path === path);
}

/** Every listing request, in order — the section's own `GET …/setups`. */
function listings(calls: Seen[]): Seen[] {
  return matching(calls, "GET", COLLECTION_PATH);
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
function renderSection(characterId = CHARACTER_ID) {
  return render(
    <AppProviders>
      <SetupsSection characterId={characterId} />
    </AppProviders>,
  );
}

/** Renders the section over `rows` and waits for the mount's listing to settle. */
async function renderListed(rows: Setup[], failing: Failing = {}) {
  const server = serveSetups(rows, failing);
  const view = renderSection();
  await flush();
  return { ...server, view };
}

// ---------------------------------------------------------------- queries
function region(): HTMLElement {
  return screen.getByRole("region", { name: SETUPS_REGION });
}

function table(): HTMLElement {
  return within(region()).getByRole("table");
}

function queryTable(): HTMLElement | null {
  return within(region()).queryByRole("table");
}

/** The row showing `name`, or null when the table does not list it. */
function queryRow(name: string): HTMLElement | null {
  const found = within(table())
    .getAllByRole("row")
    .find((row) => (row.textContent ?? "").includes(name));
  return found ?? null;
}

function row(name: string): HTMLElement {
  const found = queryRow(name);
  if (found === null) throw new Error(`no setup row showing "${name}"`);
  return found;
}

/** The given names in the order their rows appear in the table. */
function listedOrder(names: string[]): string[] {
  const ordered: string[] = [];
  for (const candidate of within(table()).getAllByRole("row")) {
    const text = candidate.textContent ?? "";
    for (const name of names) {
      if (text.includes(name)) ordered.push(name);
    }
  }
  return ordered;
}

function newSetupButton(): HTMLElement {
  return within(region()).getByRole("button", { name: NEW_SETUP_NAME });
}

function archivedSwitch(): HTMLElement {
  const scope = within(region());
  return (
    scope.queryByRole("switch", { name: SHOW_ARCHIVED_SETUPS }) ??
    scope.getByRole("checkbox", { name: SHOW_ARCHIVED_SETUPS })
  );
}

function regionText(): string {
  return (region().textContent ?? "").replace(/\s+/g, " ").trim();
}

/** The modal is a portal: it is reached through `screen`, never through the region. */
function dialog(): HTMLElement {
  return screen.getByRole("dialog");
}

function queryDialog(): HTMLElement | null {
  return screen.queryByRole("dialog");
}

function dialogField(label: RegExp): HTMLElement {
  return within(dialog()).getByRole("textbox", { name: label });
}

function dialogButton(name: RegExp): HTMLElement {
  return within(dialog()).getByRole("button", { name });
}

function notificationsShown(): Element[] {
  return Array.from(document.querySelectorAll(NOTIFICATION));
}

/** Opens a row's overflow menu; the items live in a portal, so they are found on `screen`. */
async function openRowMenu(user: User, name: string): Promise<void> {
  await user.click(within(region()).getByRole("button", { name: `Actions for ${name}` }));
}

async function chooseMenuItem(user: User, name: RegExp): Promise<void> {
  const item = await screen.findByRole("menuitem", { name });
  await user.click(item);
}

async function openCreateDialog(user: User): Promise<void> {
  await user.click(newSetupButton());
  await screen.findByRole("dialog");
}

// ---------------------------------------------------------------------------
describe("the section loads the character's setups on mount (US-023.AC-1, D13)", () => {
  it("shows the Setups region, its heading, New setup and an off Show archived setups switch — DoD-1", async () => {
    await renderListed([TAVERN, HARBOUR]);

    expect(region()).toBeInTheDocument();
    expect(within(region()).getByRole("heading", { name: SETUPS_HEADING })).toBeInTheDocument();
    expect(newSetupButton()).toBeInTheDocument();
    expect(archivedSwitch()).not.toBeChecked();
  });

  it("lists one row per setup in the payload's order, each showing its name — DoD-1", async () => {
    await renderListed([TAVERN, HARBOUR, CELLAR]);

    expect(table()).toBeInTheDocument();
    expect(listedOrder([TAVERN.name, HARBOUR.name, CELLAR.name])).toEqual([
      TAVERN.name,
      HARBOUR.name,
      CELLAR.name,
    ]);
  });

  it("keeps a payload order that is not the created_at order — DoD-1", async () => {
    await renderListed([CELLAR, TAVERN, HARBOUR]);

    expect(listedOrder([CELLAR.name, TAVERN.name, HARBOUR.name])).toEqual([
      CELLAR.name,
      TAVERN.name,
      HARBOUR.name,
    ]);
  });

  it("issues exactly one GET /api/characters/<id>/setups and no other request — DoD-1", async () => {
    const { calls } = await renderListed([TAVERN, HARBOUR]);

    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("GET");
    expect(calls[0].path).toBe(COLLECTION_PATH);
    expect(calls[0].search).toBe("");
  });
});

// ---------------------------------------------------------------------------
describe("an empty listing is one neutral line (R2, D13)", () => {
  it("shows No setups yet. and no table — DoD-2", async () => {
    await renderListed([]);

    expect(within(region()).getByText(EMPTY_LINE)).toBeInTheDocument();
    expect(queryTable()).toBeNull();
  });

  it("holds no other text and no other control inviting a setup to be created — DoD-2", async () => {
    await renderListed([]);

    // The header's "New setup" is the only affordance: nothing else is rendered.
    expect(
      within(region())
        .getAllByRole("button")
        .map((control) => control.textContent ?? ""),
    ).toEqual(["New setup"]);

    let remainder = regionText();
    for (const known of ["Show archived setups", EMPTY_LINE, "New setup", "Setups"]) {
      remainder = remainder.replace(known, "");
    }
    expect(remainder.replace(/\s+/g, "")).toBe("");
  });
});

// ---------------------------------------------------------------------------
describe("a failed load reports inline with a Retry (D12)", () => {
  it("shows Could not load setups and Retry in the region, with no notification — DoD-3", async () => {
    await renderListed([TAVERN], { listing: true });

    expect(within(region()).getByText(LOAD_FAILED_TEXT)).toBeInTheDocument();
    expect(within(region()).getByRole("button", { name: RETRY_NAME })).toBeInTheDocument();
    expect(queryTable()).toBeNull();
    expect(notificationsShown()).toEqual([]);
  });

  it("Retry requests the listing again and renders the rows on success — DoD-3", async () => {
    const user = newUser();
    let failNext = true;
    const calls: Seen[] = [];
    const mock = vi.fn<FetchFn>(async (input, init) => {
      const url = requestUrl(input);
      calls.push({
        method: requestMethod(input, init),
        path: url.pathname,
        search: url.search,
        body: parseBody(init),
      });
      if (failNext) {
        failNext = false;
        return serverError();
      }
      return jsonResponse({ setups: [TAVERN, HARBOUR] }, 200);
    });
    vi.stubGlobal("fetch", mock);
    renderSection();
    await flush();
    expect(listings(calls)).toHaveLength(1);

    await user.click(within(region()).getByRole("button", { name: RETRY_NAME }));
    await flush();

    expect(listings(calls)).toHaveLength(2);
    expect(listedOrder([TAVERN.name, HARBOUR.name])).toEqual([TAVERN.name, HARBOUR.name]);
    expect(within(region()).queryByText(LOAD_FAILED_TEXT)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("New setup creates through the modal and applies the returned row (US-023.AC-1, D2, D11)", () => {
  it("POSTs the collection, closes the dialog, puts the new row first and refetches nothing — DoD-4", async () => {
    const user = newUser();
    const { calls } = await renderListed([TAVERN, HARBOUR]);

    await openCreateDialog(user);
    expect(within(dialog()).getByText(NEW_SETUP_TITLE)).toBeInTheDocument();

    await user.type(dialogField(NAME_LABEL), TYPED_NAME);
    await user.type(dialogField(DESCRIPTION_LABEL), TYPED_DESCRIPTION);
    await user.click(dialogButton(CREATE_NAME));
    await flush();

    const posts = matching(calls, "POST", COLLECTION_PATH);
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toMatchObject({ name: TYPED_NAME });
    expect(queryDialog()).toBeNull();
    expect(listedOrder([TYPED_NAME, TAVERN.name, HARBOUR.name])).toEqual([
      TYPED_NAME,
      TAVERN.name,
      HARBOUR.name,
    ]);

    const postIndex = calls.findIndex(
      (call) => call.method === "POST" && call.path === COLLECTION_PATH,
    );
    expect(postIndex).toBeGreaterThanOrEqual(0);
    expect(listings(calls.slice(postIndex + 1))).toEqual([]);
    expect(listings(calls)).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
describe("a row's Edit opens the prefilled modal and saves in place (D2, D11)", () => {
  it("PATCHes /api/setups/<id> and the row shows the server's name in the same position — DoD-5", async () => {
    const user = newUser();
    const { calls } = await renderListed([TAVERN, HARBOUR, CELLAR]);

    await openRowMenu(user, HARBOUR.name);
    await chooseMenuItem(user, EDIT_ITEM);
    await screen.findByRole("dialog");

    expect(within(dialog()).getByText(EDIT_SETUP_TITLE)).toBeInTheDocument();
    expect(dialogField(NAME_LABEL)).toHaveValue(HARBOUR.name);
    expect(dialogField(DESCRIPTION_LABEL)).toHaveValue(HARBOUR.description);

    await user.clear(dialogField(NAME_LABEL));
    await user.type(dialogField(NAME_LABEL), EDITED_NAME);
    await user.click(dialogButton(SAVE_NAME));
    await flush();

    expect(matching(calls, "PATCH", `/api/setups/${HARBOUR.id}`)).toHaveLength(1);
    expect(queryDialog()).toBeNull();
    expect(within(region()).getByText(SAVED_NAME)).toBeInTheDocument();
    expect(listedOrder([TAVERN.name, SAVED_NAME, CELLAR.name])).toEqual([
      TAVERN.name,
      SAVED_NAME,
      CELLAR.name,
    ]);
    expect(within(region()).queryByText(HARBOUR.name)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("a failed create stays in the modal, and reopening starts a fresh draft (D2, D12)", () => {
  it("keeps the dialog open with Could not create the setup. inside it and the table unchanged — DoD-6", async () => {
    const user = newUser();
    await renderListed([TAVERN, HARBOUR], { create: true });

    await openCreateDialog(user);
    await user.type(dialogField(NAME_LABEL), TYPED_NAME);
    await user.click(dialogButton(CREATE_NAME));
    await flush();

    expect(queryDialog()).not.toBeNull();
    expect(within(dialog()).getByText(CREATE_FAILED_TEXT)).toBeInTheDocument();
    expect(listedOrder([TYPED_NAME, TAVERN.name, HARBOUR.name])).toEqual([
      TAVERN.name,
      HARBOUR.name,
    ]);
    expect(notificationsShown()).toEqual([]);
  });

  it("Cancel closes the dialog, and reopening New setup shows an empty Name — DoD-6", async () => {
    const user = newUser();
    await renderListed([TAVERN], { create: true });

    await openCreateDialog(user);
    await user.type(dialogField(NAME_LABEL), TYPED_NAME);
    await user.click(dialogButton(CREATE_NAME));
    await flush();
    expect(within(dialog()).getByText(CREATE_FAILED_TEXT)).toBeInTheDocument();

    await user.click(dialogButton(CANCEL_NAME));
    await flush();
    expect(queryDialog()).toBeNull();

    await openCreateDialog(user);
    expect(dialogField(NAME_LABEL)).toHaveValue("");
  });
});

// ---------------------------------------------------------------------------
describe("Archive and the Show archived setups switch (US-087.AC-1, D4)", () => {
  it("Archive POSTs, drops the row, and the switch brings it back badged with Restore in its menu and no confirm — DoD-7", async () => {
    const user = newUser();
    const { calls } = await renderListed([TAVERN, HARBOUR]);

    await openRowMenu(user, TAVERN.name);
    await chooseMenuItem(user, ARCHIVE_ITEM);
    await flush();

    expect(matching(calls, "POST", `/api/setups/${TAVERN.id}/archive`)).toHaveLength(1);
    expect(within(region()).queryByText(TAVERN.name)).toBeNull();
    expect(queryDialog()).toBeNull();

    await user.click(archivedSwitch());
    await flush();

    expect(listings(calls).map((call) => call.search)).toEqual(["", INCLUDE_ARCHIVED_SEARCH]);
    expect(archivedSwitch()).toBeChecked();
    expect(within(row(TAVERN.name)).getByText(ARCHIVED_BADGE)).toBeInTheDocument();

    await openRowMenu(user, TAVERN.name);
    expect(await screen.findByRole("menuitem", { name: RESTORE_ITEM })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: ARCHIVE_ITEM })).toBeNull();
    expect(queryDialog()).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("Restore brings an archived setup back to the working list (US-087.AC-2)", () => {
  it("POSTs the restore, drops the Archived badge, and the row is still listed with the switch off — DoD-8", async () => {
    const user = newUser();
    const { calls } = await renderListed([ARCHIVED_TAVERN, HARBOUR]);
    expect(within(region()).queryByText(TAVERN.name)).toBeNull();

    await user.click(archivedSwitch());
    await flush();
    expect(within(row(TAVERN.name)).getByText(ARCHIVED_BADGE)).toBeInTheDocument();

    await openRowMenu(user, TAVERN.name);
    await chooseMenuItem(user, RESTORE_ITEM);
    await flush();

    expect(matching(calls, "POST", `/api/setups/${TAVERN.id}/restore`)).toHaveLength(1);
    expect(within(row(TAVERN.name)).queryByText(ARCHIVED_BADGE)).toBeNull();

    await user.click(archivedSwitch());
    await flush();

    expect(listings(calls).map((call) => call.search)).toEqual([
      "",
      INCLUDE_ARCHIVED_SEARCH,
      "",
    ]);
    expect(archivedSwitch()).not.toBeChecked();
    expect(queryRow(TAVERN.name)).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("a failed row action reports inline in the section (D12)", () => {
  it("shows Could not archive the setup. in the region, keeps the row and raises no notification — DoD-9", async () => {
    const user = newUser();
    const { calls } = await renderListed([TAVERN, HARBOUR], { archive: true });

    await openRowMenu(user, TAVERN.name);
    await chooseMenuItem(user, ARCHIVE_ITEM);
    await flush();

    expect(matching(calls, "POST", `/api/setups/${TAVERN.id}/archive`)).toHaveLength(1);
    await waitFor(() => {
      expect(within(region()).getByText(ARCHIVE_FAILED_TEXT)).toBeInTheDocument();
    });
    expect(queryRow(TAVERN.name)).not.toBeNull();
    expect(notificationsShown()).toEqual([]);
  });
});
