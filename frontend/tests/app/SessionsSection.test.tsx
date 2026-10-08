// Feature 011, step 008 — the "Sessions" section (DoD-1..DoD-11). DoD-12..DoD-14 render
// through 009's character screen and live in `tests/app/CharacterScreen.test.tsx`; DoD-15 is
// the `App` integration clause in `tests/app/App.test.tsx`; DoD-16 is the amendment of those
// two files; DoD-17 is [manual/live] and carries no test.
//
// Amended by feature 033, step 005 (D8, D9): the section's inline start — the "Setup" select,
// the "Start session" button, the setup-choices load and its "Could not load setups to choose
// from." line — is removed, so 011's DoD-4..DoD-8 clauses (start with/without a setup, the
// choices and their reload on open, the failed start) are retired; a session now starts only
// through the page composer's send (`CharacterComposer` tests). The header carries "Sessions",
// the "Show archived sessions" switch and an icon-only "Import session" button. The import's own
// behaviour lives in `SessionsSection.import.test.tsx`.
//
// Expected behaviour comes from the step files' Interface intent and Definition of done and the
// features' context.md: 011 D5 (the "Show archived sessions" switch, the row menu, archived rows
// badged, no confirm), D15 (the server's returned row is applied — nothing is optimistic and
// nothing refetches), D18 (the fixed sentences, all inline, nothing notified); 033 D8 / D9.
//
// Recognition conventions (from the spec's wording, for the verifier):
// - The section is a region whose accessible name is "Sessions"; every assertion about what
//   the section shows goes through `within(region())`.
// - Mantine `Menu` renders into a portal, so menu items are queried through `screen`.
// - The contract names and texts: the heading "Sessions"; the switch "Show archived
//   sessions"; the icon button "Import session"; "No sessions yet."; "Could not load sessions"
//   plus "Retry"; the row trigger "Actions for <start-time label>"; the menu items "Archive",
//   "Restore" and "Export"; the badge text exactly "Archived"; the sentence "Could not archive
//   the session.".
// - A session row is identified by its link's `href` (`/sessions/<id>`), never by its
//   start-time label. A start-time label is asserted only by its fixed shape `YYYY-MM-DD HH:MM`.
// - A notification: `.mantine-Notification-root` (the repo's convention).
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
const IMPORT_SESSION = /^import session$/i;
const RETRY_NAME = /^retry$/i;
const ROW_TRIGGER_NAME = /^actions for /i;
const ARCHIVE_ITEM = /^archive$/i;
const RESTORE_ITEM = /^restore$/i;
const EXPORT_ITEM = /^export$/i;

/** 033 D9: the removed controls, named only to assert their absence. */
const SETUP_LABEL = /^setup$/i;
const START_NAME = /^start session$/i;
const NO_SETUP_OPTION = "No setup";
const SETUPS_FAILED_TEXT = "Could not load setups to choose from.";

const EMPTY_LINE = "No sessions yet.";
const LOAD_FAILED_TEXT = "Could not load sessions";
const ARCHIVE_FAILED_TEXT = "Could not archive the session.";
const ARCHIVED_BADGE = "Archived";

/** D4: the label's fixed shape — 24-hour, zero-padded, one space. Never an exact value. */
const LABEL_SHAPE = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/;

const NOTIFICATION = ".mantine-Notification-root";

// ---------------------------------------------------------------- fixtures
// Ids are decimal strings past Number.MAX_SAFE_INTEGER, so any coercion would show in an href.
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
  /** How many `GET …/sessions` fail before the listing starts answering (`true` = always). */
  failSessions?: number | true;
  /** Any `GET …/setups` fails — the section must not ask, and must never say it failed. */
  failSetups?: true;
  failArchive?: true;
  failRestore?: true;
};

/**
 * The wire contract of the sessions routes over an in-memory row set, every request recorded
 * in order and routed by the **exact** pathname plus query string. Only the listing honours the
 * include-archived flag; a mutation answers the one row it changed. The setups listing and the
 * session create are still answered (and recorded) so that a stray request is observable as a
 * call rather than as a loud failure.
 */
function serveSection(config: Config = {}) {
  const order: Session[] = [...(config.sessions ?? [])];
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
      return jsonResponse({ setups: [TAVERN] }, 200);
    }

    if (url.pathname === SESSIONS_PATH && method === "POST") {
      const created: Session = {
        id: CREATED_ID,
        character_id: CHARACTER_ID,
        setup_id: null,
        setup_name: null,
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

/** Every setups listing request — 033 D9: the section asks for none. */
function setupsRequests(calls: Seen[]): Seen[] {
  return matching(calls, "GET", SETUPS_PATH);
}

/** Every session create — 033 D9: the section issues none. */
function sessionCreates(calls: Seen[]): Seen[] {
  return matching(calls, "POST", SESSIONS_PATH);
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

function heading(): HTMLElement {
  return within(region()).getByRole("heading", { name: SESSIONS_HEADING });
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

function importButton(): HTMLElement {
  return within(region()).getByRole("button", { name: IMPORT_SESSION });
}

function notificationsShown(): Element[] {
  return Array.from(document.querySelectorAll(NOTIFICATION));
}

/** Whether `first` comes before `second` in document order. */
function precedes(first: Node, second: Node): boolean {
  return (first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

/** The smallest element containing every one of `nodes` — the header row they share. */
function commonAncestor(nodes: HTMLElement[]): HTMLElement {
  let candidate: HTMLElement | null = nodes[0];
  while (candidate !== null && !nodes.every((node) => candidate?.contains(node) === true)) {
    candidate = candidate.parentElement;
  }
  if (candidate === null) throw new Error("the given elements share no ancestor");
  return candidate;
}

/** 033 D9: whether the section renders anything that is the removed "Setup" select. */
function querySetupSelect(): HTMLElement | null {
  const scope = within(region());
  return (
    scope.queryByRole("combobox", { name: SETUP_LABEL, hidden: true }) ??
    scope.queryByRole("textbox", { name: SETUP_LABEL, hidden: true }) ??
    scope.queryByLabelText(SETUP_LABEL)
  );
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
  it("requests exactly the sessions listing — no setup choices, no create — DoD-1 (and 033 step 005 DoD-1, DoD-4)", async () => {
    const { calls } = await renderListed({ sessions: [WITH_SETUP, WITHOUT_SETUP] });

    expect(calls.map((call) => `${call.method} ${call.path}${call.search}`)).toEqual([
      `GET ${SESSIONS_PATH}`,
    ]);
  });

  it("shows the Sessions region with its heading, an off switch and an enabled Import session — DoD-1 (and 033 step 005 DoD-2)", async () => {
    await renderListed({ sessions: [WITH_SETUP, WITHOUT_SETUP] });

    expect(region()).toBeInTheDocument();
    expect(heading()).toBeInTheDocument();
    expect(archivedSwitch()).not.toBeChecked();
    expect(importButton()).toBeEnabled();
  });

  it("lists one row per session in the payload's order, each linking to /sessions/<id> — DoD-1 (and 033 step 005 DoD-5)", async () => {
    await renderListed({ sessions: [WITH_SETUP, WITHOUT_SETUP] });

    expect(table()).toBeInTheDocument();
    expect(listedHrefs()).toEqual([sessionHref(WITH_SETUP), sessionHref(WITHOUT_SETUP)]);
    expect(rowLabel(WITH_SETUP)).toMatch(LABEL_SHAPE);
    expect(rowLabel(WITHOUT_SETUP)).toMatch(LABEL_SHAPE);
  });

  it("shows the first row's setup name and no other text on the second row — DoD-1", async () => {
    await renderListed({ sessions: [WITH_SETUP, WITHOUT_SETUP] });

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
  it("shows No sessions yet. and no table — DoD-2 (and 033 step 005 DoD-5)", async () => {
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
describe("Archive from a row's menu and the Show archived sessions switch (US-027.AC-1, D5)", () => {
  it("POSTs the archive, drops the row, and the switch brings it back badged with Restore and no confirm — DoD-9 (and 033 step 005 DoD-5)", async () => {
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
  it("POSTs the restore, drops the Archived badge, and the row is still listed with the switch off — DoD-10 (and 033 step 005 DoD-5)", async () => {
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

// ===========================================================================
// Feature 033, step 005 — the message-less start is gone (D9) and the list header carries the
// icon-only Import session (D8).
// ===========================================================================
describe("033 step 005: no message-less start control in the section (D9)", () => {
  it("renders no Setup select, no No setup choice and no Start session button — 033 step 005 DoD-1", async () => {
    await renderListed({ sessions: [WITH_SETUP, WITHOUT_SETUP] });

    expect(querySetupSelect()).toBeNull();
    expect(within(region()).queryByText(NO_SETUP_OPTION)).toBeNull();
    expect(within(region()).queryByRole("button", { name: START_NAME, hidden: true })).toBeNull();
    expect(screen.queryByRole("button", { name: START_NAME, hidden: true })).toBeNull();
  });

  it("renders no start control for an empty listing either — 033 step 005 DoD-1", async () => {
    await renderListed({ sessions: [] });

    expect(within(region()).getByText(EMPTY_LINE)).toBeInTheDocument();
    expect(querySetupSelect()).toBeNull();
    expect(within(region()).queryByRole("button", { name: START_NAME, hidden: true })).toBeNull();
  });

  it("never shows Could not load setups to choose from., even when every setups listing would fail — 033 step 005 DoD-1", async () => {
    const { calls } = await renderListed({ sessions: [WITH_SETUP], failSetups: true });

    expect(listedHrefs()).toEqual([sessionHref(WITH_SETUP)]);
    expect(screen.queryByText(SETUPS_FAILED_TEXT)).toBeNull();
    expect(setupsRequests(calls)).toEqual([]);
  });

  it("asks for no setups even after the archived switch reloads the list — 033 step 005 DoD-1", async () => {
    const user = newUser();
    const { calls } = await renderListed({ sessions: [WITH_SETUP] });

    await toggleArchivedSwitch(user);

    expect(listings(calls).map((call) => call.search)).toEqual(["", INCLUDE_ARCHIVED_SEARCH]);
    expect(setupsRequests(calls)).toEqual([]);
    expect(screen.queryByText(SETUPS_FAILED_TEXT)).toBeNull();
  });
});

describe("033 step 005: mounting and using the section creates no session (D9)", () => {
  it("mounting issues no session create and stays on the character page — 033 step 005 DoD-4", async () => {
    const { calls, workspace } = await renderListed({ sessions: [WITH_SETUP, WITHOUT_SETUP] });
    await flush();

    expect(sessionCreates(calls)).toEqual([]);
    expect(locationPath()).toBe(SCREEN_PATH);
    expect(workspace.sessions.map((session) => session.id)).not.toContain(CREATED_ID);
  });

  it("toggling the archived switch, retrying and archiving a row issue no session create — 033 step 005 DoD-4", async () => {
    const user = newUser();
    const { calls } = await renderListed({ sessions: [WITH_SETUP, WITHOUT_SETUP], failSessions: 1 });

    await user.click(within(region()).getByRole("button", { name: RETRY_NAME }));
    await flush();
    await toggleArchivedSwitch(user);
    await openRowMenu(user, WITHOUT_SETUP);
    await chooseMenuItem(user, ARCHIVE_ITEM);

    expect(matching(calls, "POST", `/api/sessions/${WITHOUT_SETUP.id}/archive`)).toHaveLength(1);
    expect(sessionCreates(calls)).toEqual([]);
    expect(locationPath()).toBe(SCREEN_PATH);
  });
});

describe("033 step 005: the list header (D8)", () => {
  it("holds the Sessions heading, the Show archived sessions switch and the Import session button, above the list — 033 step 005 DoD-2", async () => {
    await renderListed({ sessions: [WITH_SETUP, WITHOUT_SETUP] });

    const title = heading();
    const toggle = archivedSwitch();
    const upload = importButton();
    const header = commonAncestor([title, toggle, upload]);

    expect(region().contains(header)).toBe(true);
    expect(header).not.toBe(region());
    expect(header.contains(table())).toBe(false);
    expect(precedes(title, toggle)).toBe(true);
    expect(precedes(title, upload)).toBe(true);
    expect(precedes(upload, table())).toBe(true);
    expect(precedes(toggle, table())).toBe(true);
  });

  it("the header sits above the No sessions yet. line too — 033 step 005 DoD-2", async () => {
    await renderListed({ sessions: [] });

    const line = within(region()).getByText(EMPTY_LINE);
    const header = commonAncestor([heading(), archivedSwitch(), importButton()]);

    expect(header.contains(line)).toBe(false);
    expect(precedes(importButton(), line)).toBe(true);
  });

  it("Import session is a single icon-only button: named by its accessible name, showing no text — 033 step 005 DoD-2", async () => {
    await renderListed({ sessions: [WITH_SETUP] });

    expect(within(region()).getAllByRole("button", { name: IMPORT_SESSION })).toHaveLength(1);
    expect((importButton().textContent ?? "").trim()).toBe("");
    const labelled = within(region())
      .getAllByRole("button")
      .filter((control) => (control.textContent ?? "").includes("Import session"));
    expect(labelled).toEqual([]);
  });
});

describe("033 step 005: the row menu still offers Export (D8)", () => {
  it("an active row's menu offers Archive and Export, with no confirm on opening — 033 step 005 DoD-5", async () => {
    const user = newUser();
    await renderListed({ sessions: [WITH_SETUP, WITHOUT_SETUP] });

    await openRowMenu(user, WITHOUT_SETUP);

    expect(await screen.findByRole("menuitem", { name: ARCHIVE_ITEM })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: EXPORT_ITEM })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: RESTORE_ITEM })).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
