// Feature 011, step 008 — the "Sessions" section (DoD-1..DoD-11). DoD-12..DoD-14 render
// through 009's character screen and live in `tests/app/CharacterScreen.test.tsx`; DoD-15 is
// the `App` integration clause in `tests/app/App.test.tsx`; DoD-16 is the amendment of those
// two files; DoD-17 is [manual/live] and carries no test.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 008.context.md and the feature's context.md: D1 (the inline start — a "Setup" select whose
// first and default option is "No setup", and a "Start session" button that pushes to
// `/sessions/<id>`), D5 (the "Show archived sessions" switch, the row menu, archived rows
// badged, no confirm), D15 (the server's returned row is applied to the section and to the
// workspace `SessionsState` — nothing is optimistic and nothing refetches), D18 (the fixed
// sentences, all inline, nothing notified), D19 (the setup choices reload on each open).
//
// Recognition conventions (from the spec's wording, for the verifier):
// - The section is a region whose accessible name is "Sessions"; every assertion about what
//   the section shows goes through `within(region())` (context.md "Scoping").
// - Mantine `Select` and `Menu` render into portals, so options and menu items are queried
//   through `screen`, never `within(region())` (context.md "Mantine `Select`").
// - The contract names and texts: the heading "Sessions"; the switch "Show archived
//   sessions"; the select "Setup" with the option "No setup"; the button "Start session";
//   "No sessions yet."; "Could not load sessions" plus "Retry"; "Could not load setups to
//   choose from."; the row trigger "Actions for <start-time label>"; the menu items "Archive"
//   and "Restore"; the badge text exactly "Archived"; the sentences "Could not start the
//   session.", "Could not archive the session." and "Could not restore the session.".
// - A session row is identified by its link's `href` (`/sessions/<id>`), never by its
//   start-time label, because two sessions started in the same minute share a label and share
//   the menu trigger's name (008.context.md "Row labels and the menu trigger"). A start-time
//   label is asserted only by its fixed shape `YYYY-MM-DD HH:MM`, never by an exact local
//   value and never by calling the formatter (context.md "Start-time labels").
// - A notification: `.mantine-Notification-root` (the repo's convention). 011 raises none.
// - The router location: a probe rendered beside the section inside the same MemoryRouter.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SessionsSection } from "../../src/app/SessionsSection";
import type { Session } from "../../src/app/sessionsApi";
import { SessionsState } from "../../src/app/sessionsState";
import type { Setup } from "../../src/app/setupsApi";
import { AppProviders } from "../../src/shared/AppProviders";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string; body: unknown };
type User = ReturnType<typeof userEvent.setup>;

// ---------------------------------------------------------------- the spec's names
const SESSIONS_REGION = /^sessions$/i;
const SESSIONS_HEADING = /^sessions$/i;
const SHOW_ARCHIVED_SESSIONS = /^show archived sessions$/i;
const SETUP_LABEL = /^setup$/i;
const START_NAME = /^start session$/i;
const RETRY_NAME = /^retry$/i;
const ROW_TRIGGER_NAME = /^actions for /i;
const ARCHIVE_ITEM = /^archive$/i;
const RESTORE_ITEM = /^restore$/i;

const NO_SETUP_OPTION = "No setup";
const EMPTY_LINE = "No sessions yet.";
const LOAD_FAILED_TEXT = "Could not load sessions";
const SETUPS_FAILED_TEXT = "Could not load setups to choose from.";
const START_FAILED_TEXT = "Could not start the session.";
const ARCHIVE_FAILED_TEXT = "Could not archive the session.";
const ARCHIVED_BADGE = "Archived";

/** D4: the label's fixed shape — 24-hour, zero-padded, one space. Never an exact value. */
const LABEL_SHAPE = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/;

const NOTIFICATION = ".mantine-Notification-root";

// ---------------------------------------------------------------- fixtures
// Ids are decimal strings past Number.MAX_SAFE_INTEGER (context.md "Ids are strings"), so any
// coercion would show in an href or in the location.
const CHARACTER_ID = "7250000000000000011";
const SESSIONS_PATH = `/api/characters/${CHARACTER_ID}/sessions`;
const SETUPS_PATH = `/api/characters/${CHARACTER_ID}/setups`;
const INCLUDE_ARCHIVED_SEARCH = "?include_archived=true";
const SCREEN_PATH = `/characters/${CHARACTER_ID}`;
const CREATED_ID = "9007199254740993"; // 2^53 + 1

const TAVERN: Setup = {
  id: "7250000000000000031",
  character_id: CHARACTER_ID,
  name: "Tavern brawl",
  description: "Someone has already thrown the first stool.",
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

/** The newest row, carrying a setup label (US-088.AC-1). */
const WITH_SETUP: Session = {
  id: "7250000000000000101",
  character_id: CHARACTER_ID,
  setup_id: TAVERN.id,
  setup_name: TAVERN.name,
  archived_at: null,
  last_used_at: "2026-05-10T09:26:53.000000+00:00",
  created_at: "2026-05-10T09:26:53.000000+00:00",
  updated_at: "2026-05-10T09:26:53.000000+00:00",
};

/** The older row, with no setup at all (US-088.AC-2, R2). */
const WITHOUT_SETUP: Session = {
  id: "7250000000000000102",
  character_id: CHARACTER_ID,
  setup_id: null,
  setup_name: null,
  archived_at: null,
  last_used_at: "2026-04-02T08:15:42.000000+00:00",
  created_at: "2026-04-02T08:15:42.000000+00:00",
  updated_at: "2026-04-02T08:15:42.000000+00:00",
};

const CREATED_STAMP = "2026-06-01T12:00:00.000000+00:00";
const ACTION_STAMP = "2026-06-02T12:00:00.000000+00:00";

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

function sessionNotFound(): Response {
  return envelope("session_not_found", 404);
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

type Config = {
  /** The character's sessions, in the order the listing answers them. */
  sessions?: Session[];
  /** One payload per `GET …/setups`, the last repeating — D19's reload-on-open. */
  setupsResponses?: Setup[][];
  /** How many `GET …/sessions` fail before the listing starts answering (`true` = always). */
  failSessions?: number | true;
  failSetups?: true;
  failStart?: true;
  failArchive?: true;
  failRestore?: true;
};

/**
 * The wire contract of the sessions routes over an in-memory row set, every request recorded
 * in order and routed by the **exact** pathname plus query string (context.md "Stubs routed by
 * exact path"). Only the listing honours the include-archived flag; a mutation answers the one
 * row it changed.
 */
function serveSection(config: Config = {}) {
  const order: Session[] = [...(config.sessions ?? [])];
  const setupsResponses: Setup[][] = config.setupsResponses ?? [[]];
  const knownSetups: Setup[] = setupsResponses.flat();
  let setupsServed = 0;
  let sessionFailuresLeft =
    config.failSessions === true
      ? Number.POSITIVE_INFINITY
      : typeof config.failSessions === "number"
        ? config.failSessions
        : 0;
  const calls: Seen[] = [];

  const mock = vi.fn<FetchFn>(async (input, init) => {
    const url = requestUrl(input);
    const method = requestMethod(input, init);
    const body = parseBody(init);
    calls.push({ method, path: url.pathname, search: url.search, body });

    if (url.pathname === SESSIONS_PATH && method === "GET") {
      if (sessionFailuresLeft > 0) {
        sessionFailuresLeft -= 1;
        return serverError();
      }
      const includeArchived = url.search === INCLUDE_ARCHIVED_SEARCH;
      const listed = order.filter((row) => includeArchived || row.archived_at === null);
      return jsonResponse({ sessions: listed }, 200);
    }

    if (url.pathname === SETUPS_PATH && method === "GET") {
      if (config.failSetups === true) return serverError();
      const index = Math.min(setupsServed, setupsResponses.length - 1);
      setupsServed += 1;
      return jsonResponse({ setups: setupsResponses[index] }, 200);
    }

    if (url.pathname === SESSIONS_PATH && method === "POST") {
      if (config.failStart === true) return serverError();
      const sent = (body ?? {}) as { setup_id?: string | null };
      const setupId = sent.setup_id ?? null;
      const chosen = knownSetups.find((setup) => setup.id === setupId);
      const created: Session = {
        id: CREATED_ID,
        character_id: CHARACTER_ID,
        setup_id: setupId,
        setup_name: chosen === undefined ? null : chosen.name,
        archived_at: null,
        last_used_at: CREATED_STAMP,
        created_at: CREATED_STAMP,
        updated_at: CREATED_STAMP,
      };
      order.unshift(created);
      return jsonResponse(created, 201);
    }

    const match = /^\/api\/sessions\/([^/]+)\/(archive|restore)$/.exec(url.pathname);
    if (match !== null && method === "POST") {
      const index = order.findIndex((row) => row.id === match[1]);
      if (index < 0) return sessionNotFound();
      const row = order[index];
      if (match[2] === "archive") {
        if (config.failArchive === true) return serverError();
        const next: Session = { ...row, archived_at: ACTION_STAMP, updated_at: ACTION_STAMP };
        order[index] = next;
        return jsonResponse(next, 200);
      }
      if (config.failRestore === true) return serverError();
      const next: Session = { ...row, archived_at: null, updated_at: ACTION_STAMP };
      order[index] = next;
      return jsonResponse(next, 200);
    }

    return sessionNotFound();
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

function matching(calls: Seen[], method: string, path: string): Seen[] {
  return calls.filter((call) => call.method === method && call.path === path);
}

/** Every sessions listing request, in order — the section's own `GET …/sessions`. */
function listings(calls: Seen[]): Seen[] {
  return matching(calls, "GET", SESSIONS_PATH);
}

/** Every setup-choices request, in order — the Select's `GET …/setups`. */
function setupsRequests(calls: Seen[]): Seen[] {
  return matching(calls, "GET", SETUPS_PATH);
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
  return <output data-testid="location">{location.pathname}</output>;
}

function renderSection(workspace: SessionsState) {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={[SCREEN_PATH]}>
        <SessionsSection characterId={CHARACTER_ID} sessions={workspace} />
        <LocationProbe />
      </MemoryRouter>
    </AppProviders>,
  );
}

/** Renders the section over `config`'s rows and waits for the mount's loads to settle. */
async function renderListed(config: Config = {}) {
  const server = serveSection(config);
  const workspace = new SessionsState();
  const view = renderSection(workspace);
  await flush();
  return { ...server, workspace, view };
}

function locationPath(): string {
  return screen.getByTestId("location").textContent ?? "";
}

// ---------------------------------------------------------------- queries
function region(): HTMLElement {
  return screen.getByRole("region", { name: SESSIONS_REGION });
}

function table(): HTMLElement {
  return within(region()).getByRole("table");
}

function queryTable(): HTMLElement | null {
  return within(region()).queryByRole("table");
}

function sessionHref(session: Session): string {
  return `/sessions/${session.id}`;
}

/** Every session link in the section, in document order, by `href`. */
function listedHrefs(): string[] {
  return within(region())
    .queryAllByRole("link")
    .map((link) => link.getAttribute("href") ?? "")
    .filter((value) => value.startsWith("/sessions/"));
}

function queryRow(session: Session): HTMLElement | null {
  const link = within(region())
    .queryAllByRole("link")
    .find((candidate) => candidate.getAttribute("href") === sessionHref(session));
  if (link === undefined) return null;
  return link.closest("tr");
}

function row(session: Session): HTMLElement {
  const found = queryRow(session);
  if (found === null) throw new Error(`no session row linking to ${sessionHref(session)}`);
  return found;
}

/** A row's link text — the start-time label, asserted by shape only. */
function rowLabel(session: Session): string {
  return (within(row(session)).getByRole("link").textContent ?? "").trim();
}

function archivedSwitch(): HTMLElement {
  const scope = within(region());
  return (
    scope.queryByRole("switch", { name: SHOW_ARCHIVED_SESSIONS }) ??
    scope.getByRole("checkbox", { name: SHOW_ARCHIVED_SESSIONS })
  );
}

function setupSelect(): HTMLElement {
  const scope = within(region());
  return (
    scope.queryByRole("combobox", { name: SETUP_LABEL }) ??
    scope.queryByRole("textbox", { name: SETUP_LABEL }) ??
    scope.getByLabelText(SETUP_LABEL)
  );
}

/** What the "Setup" field currently displays. */
function setupSelectText(): string {
  const element = setupSelect();
  const shown = element instanceof HTMLInputElement ? element.value : element.textContent ?? "";
  return shown.trim();
}

function startButton(): HTMLElement {
  return within(region()).getByRole("button", { name: START_NAME });
}

function notificationsShown(): Element[] {
  return Array.from(document.querySelectorAll(NOTIFICATION));
}

/** The options live in a portal, so they are read off `screen` (context.md). */
function optionTexts(): string[] {
  return screen.queryAllByRole("option").map((option) => (option.textContent ?? "").trim());
}

async function openSelect(user: User): Promise<void> {
  await user.click(setupSelect());
  await waitFor(() => {
    expect(screen.queryAllByRole("option").length).toBeGreaterThan(0);
  });
  await flush();
}

async function closeSelect(user: User): Promise<void> {
  await user.keyboard("{Escape}");
  await waitFor(() => {
    expect(screen.queryAllByRole("option")).toEqual([]);
  });
}

async function chooseOption(user: User, name: string): Promise<void> {
  await user.click(screen.getByRole("option", { name }));
  await flush();
}

/** Opens one row's overflow menu; the items are in a portal, so they are found on `screen`. */
async function openRowMenu(user: User, session: Session): Promise<void> {
  await user.click(within(row(session)).getByRole("button", { name: ROW_TRIGGER_NAME }));
}

async function chooseMenuItem(user: User, name: RegExp): Promise<void> {
  const item = await screen.findByRole("menuitem", { name });
  await user.click(item);
  await flush();
}

async function toggleArchivedSwitch(user: User): Promise<void> {
  await user.click(archivedSwitch());
  await flush();
}

// ---------------------------------------------------------------------------
describe("the section loads the character's sessions on mount (US-028.AC-1, US-088.AC-1, US-088.AC-2)", () => {
  it("requests exactly the sessions listing and the setup choices — DoD-1", async () => {
    const { calls } = await renderListed({
      sessions: [WITH_SETUP, WITHOUT_SETUP],
      setupsResponses: [[TAVERN]],
    });

    expect(
      calls.map((call) => `${call.method} ${call.path}${call.search}`).sort((a, b) => a.localeCompare(b)),
    ).toEqual([`GET ${SESSIONS_PATH}`, `GET ${SETUPS_PATH}`].sort((a, b) => a.localeCompare(b)));
  });

  it("shows the Sessions region with its heading, an off switch, No setup and an enabled Start session — DoD-1", async () => {
    await renderListed({ sessions: [WITH_SETUP, WITHOUT_SETUP], setupsResponses: [[TAVERN]] });

    expect(region()).toBeInTheDocument();
    expect(within(region()).getByRole("heading", { name: SESSIONS_HEADING })).toBeInTheDocument();
    expect(archivedSwitch()).not.toBeChecked();
    expect(setupSelectText()).toBe(NO_SETUP_OPTION);
    expect(startButton()).toBeEnabled();
  });

  it("lists one row per session in the payload's order, each linking to /sessions/<id> — DoD-1", async () => {
    await renderListed({ sessions: [WITH_SETUP, WITHOUT_SETUP], setupsResponses: [[TAVERN]] });

    expect(table()).toBeInTheDocument();
    expect(listedHrefs()).toEqual([sessionHref(WITH_SETUP), sessionHref(WITHOUT_SETUP)]);
    expect(rowLabel(WITH_SETUP)).toMatch(LABEL_SHAPE);
    expect(rowLabel(WITHOUT_SETUP)).toMatch(LABEL_SHAPE);
  });

  it("shows the first row's setup name and no other text on the second row — DoD-1", async () => {
    await renderListed({ sessions: [WITH_SETUP, WITHOUT_SETUP], setupsResponses: [[TAVERN]] });

    expect(within(row(WITH_SETUP)).getByText(TAVERN.name)).toBeInTheDocument();

    // US-088.AC-2: nothing where the label would be — the row's only text is its start-time
    // label (the menu trigger is icon-only, named through its accessible name).
    const label = rowLabel(WITHOUT_SETUP);
    const remainder = (row(WITHOUT_SETUP).textContent ?? "").replace(label, "");
    expect(remainder.replace(/\s+/g, "")).toBe("");
  });
});

// ---------------------------------------------------------------------------
describe("an empty listing is one neutral line (D18)", () => {
  it("shows No sessions yet. and no table — DoD-2", async () => {
    await renderListed({ sessions: [] });

    expect(within(region()).getByText(EMPTY_LINE)).toBeInTheDocument();
    expect(queryTable()).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("a failed sessions load reports inline with a Retry (D18)", () => {
  it("shows Could not load sessions and Retry in the region, with no notification — DoD-3", async () => {
    await renderListed({ sessions: [WITH_SETUP], failSessions: true });

    expect(within(region()).getByText(LOAD_FAILED_TEXT)).toBeInTheDocument();
    expect(within(region()).getByRole("button", { name: RETRY_NAME })).toBeInTheDocument();
    expect(queryTable()).toBeNull();
    expect(notificationsShown()).toEqual([]);
  });

  it("Retry requests the listing again and renders the rows on success — DoD-3", async () => {
    const user = newUser();
    const { calls } = await renderListed({
      sessions: [WITH_SETUP, WITHOUT_SETUP],
      failSessions: 1,
    });
    expect(listings(calls)).toHaveLength(1);

    await user.click(within(region()).getByRole("button", { name: RETRY_NAME }));
    await flush();

    expect(listings(calls)).toHaveLength(2);
    expect(listedHrefs()).toEqual([sessionHref(WITH_SETUP), sessionHref(WITHOUT_SETUP)]);
    expect(within(region()).queryByText(LOAD_FAILED_TEXT)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("Start session with No setup starts and navigates (US-026.AC-1, US-024.AC-1, UC-023, D1, D15)", () => {
  it("POSTs setup_id null, lands on /sessions/<the response's id> and applies the row to the workspace state — DoD-4", async () => {
    const user = newUser();
    const { calls, workspace } = await renderListed({
      sessions: [WITH_SETUP],
      setupsResponses: [[TAVERN]],
    });
    expect(locationPath()).toBe(SCREEN_PATH);

    await user.click(startButton());
    await flush();

    const posts = matching(calls, "POST", SESSIONS_PATH);
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({ setup_id: null });
    expect(locationPath()).toBe(`/sessions/${CREATED_ID}`);
    expect(workspace.sessions.map((session) => session.id)).toContain(CREATED_ID);
  });
});

// ---------------------------------------------------------------------------
describe("no setup list is ever a precondition for starting (US-024.AC-3, R2, D18)", () => {
  it("with an empty setups listing Start session is enabled and starts with setup_id null — DoD-5", async () => {
    const user = newUser();
    const { calls } = await renderListed({ sessions: [], setupsResponses: [[]] });

    expect(startButton()).toBeEnabled();
    expect(setupSelectText()).toBe(NO_SETUP_OPTION);

    await user.click(startButton());
    await flush();

    const posts = matching(calls, "POST", SESSIONS_PATH);
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({ setup_id: null });
  });

  it("with a failed setups listing Start session is enabled, starts with setup_id null and the region says why — DoD-5", async () => {
    const user = newUser();
    const { calls } = await renderListed({ sessions: [], failSetups: true });

    expect(within(region()).getByText(SETUPS_FAILED_TEXT)).toBeInTheDocument();
    expect(startButton()).toBeEnabled();

    await user.click(startButton());
    await flush();

    const posts = matching(calls, "POST", SESSIONS_PATH);
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({ setup_id: null });
  });
});

// ---------------------------------------------------------------------------
describe("the Setup select offers the working setups (US-023.AC-2, US-025.AC-1, UC-021)", () => {
  it("lists No setup first, then the setups in the payload's order, and asked for them without include_archived — DoD-6", async () => {
    const user = newUser();
    const { calls } = await renderListed({
      sessions: [],
      setupsResponses: [[HARBOUR, TAVERN]],
    });

    await openSelect(user);

    expect(optionTexts()).toEqual([NO_SETUP_OPTION, HARBOUR.name, TAVERN.name]);

    const choiceRequests = setupsRequests(calls);
    expect(choiceRequests.length).toBeGreaterThan(0);
    for (const call of choiceRequests) {
      expect(call.search).toBe("");
    }
  });

  it("choosing a setup and pressing Start session POSTs that setup's id — DoD-6", async () => {
    const user = newUser();
    const { calls } = await renderListed({
      sessions: [],
      setupsResponses: [[HARBOUR, TAVERN]],
    });

    await openSelect(user);
    await chooseOption(user, TAVERN.name);
    expect(setupSelectText()).toBe(TAVERN.name);

    await user.click(startButton());
    await flush();

    const posts = matching(calls, "POST", SESSIONS_PATH);
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({ setup_id: TAVERN.id });
  });
});

// ---------------------------------------------------------------------------
describe("the choices reload each time the select opens (US-023.AC-2, D19)", () => {
  it("a setup the earlier response lacked is offered on the second opening — DoD-7", async () => {
    const user = newUser();
    // The mount load and the first opening see only TAVERN; every later request also sees
    // HARBOUR, created elsewhere on the page meanwhile.
    const { calls } = await renderListed({
      sessions: [],
      setupsResponses: [[TAVERN], [TAVERN], [TAVERN, HARBOUR]],
    });
    const afterMount = setupsRequests(calls).length;

    await openSelect(user);
    expect(optionTexts()).toEqual([NO_SETUP_OPTION, TAVERN.name]);
    const afterFirstOpen = setupsRequests(calls).length;
    expect(afterFirstOpen).toBeGreaterThan(afterMount);

    await closeSelect(user);
    await openSelect(user);

    expect(setupsRequests(calls).length).toBeGreaterThan(afterFirstOpen);
    expect(optionTexts()).toEqual([NO_SETUP_OPTION, TAVERN.name, HARBOUR.name]);
  });
});

// ---------------------------------------------------------------------------
describe("a failed start reports inline and stays where it is (D18)", () => {
  it("shows Could not start the session., keeps the location and raises no notification — DoD-8", async () => {
    const user = newUser();
    const { calls } = await renderListed({ sessions: [WITH_SETUP], failStart: true });

    await user.click(startButton());
    await flush();

    expect(matching(calls, "POST", SESSIONS_PATH)).toHaveLength(1);
    await waitFor(() => {
      expect(within(region()).getByText(START_FAILED_TEXT)).toBeInTheDocument();
    });
    expect(locationPath()).toBe(SCREEN_PATH);
    expect(notificationsShown()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("Archive from a row's menu and the Show archived sessions switch (US-027.AC-1, D5)", () => {
  it("POSTs the archive, drops the row, and the switch brings it back badged with Restore and no confirm — DoD-9", async () => {
    const user = newUser();
    const { calls } = await renderListed({ sessions: [WITH_SETUP, WITHOUT_SETUP] });

    await openRowMenu(user, WITH_SETUP);
    await chooseMenuItem(user, ARCHIVE_ITEM);

    expect(matching(calls, "POST", `/api/sessions/${WITH_SETUP.id}/archive`)).toHaveLength(1);
    expect(queryRow(WITH_SETUP)).toBeNull();
    expect(queryRow(WITHOUT_SETUP)).not.toBeNull();
    // No confirm: ui-conventions.md "Deliberately NOT confirmed".
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByRole("alertdialog")).toBeNull();

    await toggleArchivedSwitch(user);

    expect(listings(calls).map((call) => call.search)).toEqual(["", INCLUDE_ARCHIVED_SEARCH]);
    expect(archivedSwitch()).toBeChecked();
    expect(within(row(WITH_SETUP)).getByText(ARCHIVED_BADGE)).toBeInTheDocument();

    await openRowMenu(user, WITH_SETUP);
    expect(await screen.findByRole("menuitem", { name: RESTORE_ITEM })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: ARCHIVE_ITEM })).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("Restore brings an archived session back to the working list (US-027.AC-2)", () => {
  it("POSTs the restore, drops the Archived badge, and the row is still listed with the switch off — DoD-10", async () => {
    const user = newUser();
    const { calls } = await renderListed({ sessions: [WITH_SETUP, WITHOUT_SETUP] });

    await openRowMenu(user, WITH_SETUP);
    await chooseMenuItem(user, ARCHIVE_ITEM);
    await toggleArchivedSwitch(user);
    expect(within(row(WITH_SETUP)).getByText(ARCHIVED_BADGE)).toBeInTheDocument();

    await openRowMenu(user, WITH_SETUP);
    await chooseMenuItem(user, RESTORE_ITEM);

    expect(matching(calls, "POST", `/api/sessions/${WITH_SETUP.id}/restore`)).toHaveLength(1);
    expect(within(row(WITH_SETUP)).queryByText(ARCHIVED_BADGE)).toBeNull();

    await toggleArchivedSwitch(user);

    expect(listings(calls).map((call) => call.search)).toEqual([
      "",
      INCLUDE_ARCHIVED_SEARCH,
      "",
    ]);
    expect(archivedSwitch()).not.toBeChecked();
    expect(queryRow(WITH_SETUP)).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("a failed row action reports inline in the section (D18)", () => {
  it("shows Could not archive the session., keeps the row and raises no notification — DoD-11", async () => {
    const user = newUser();
    const { calls } = await renderListed({
      sessions: [WITH_SETUP, WITHOUT_SETUP],
      failArchive: true,
    });

    await openRowMenu(user, WITH_SETUP);
    await chooseMenuItem(user, ARCHIVE_ITEM);

    expect(matching(calls, "POST", `/api/sessions/${WITH_SETUP.id}/archive`)).toHaveLength(1);
    await waitFor(() => {
      expect(within(region()).getByText(ARCHIVE_FAILED_TEXT)).toBeInTheDocument();
    });
    expect(queryRow(WITH_SETUP)).not.toBeNull();
    expect(notificationsShown()).toEqual([]);
  });
});
