// Feature 030 — export-granularities, step 006: the "Export" item in each session row's
// overflow menu (DoD-6, and DoD-7 / DoD-8 for this control). The module's own clauses live in
// `exportDownloads.test.ts`; the other two controls have their own files. DoD-9 and DoD-10 are
// [manual/live] and carry no test.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 006.context.md and the feature context.md: the item is present in both the active and the
// archived state of a row, choosing it downloads that row's export route, success is silent (no
// success toast) and a failure in the `app` entry goes through `notifyFailure`, and no export
// opens a confirm dialog. Bindings come from the frozen `### Step 006` record: the item's
// accessible name is exactly `Export`, it is reached through the row trigger `Actions for
// <label>` whose label is the formatted start (never the id), and the route is
// `GET /api/sessions/{session_id}/export` (context.md "Routes").
//
// Harness conventions (006.context.md, 004.context.md, and 011's own conventions):
// - A session row is identified by its link's `href` (`/sessions/<id>`), never by its start-time
//   label: two rows started in the same minute would share a label and a trigger name. The three
//   fixtures below start in different minutes on purpose, so each trigger name is unique.
// - The section renders inside `AppProviders` + `MemoryRouter`, so the notifications outlet
//   exists and "nothing was notified" / "one notification carrying the message" are observable
//   through `.mantine-Notification-root`. `notifyFailure` is deliberately NOT mocked: the clause
//   is about what the user is shown, so the real channel runs end to end.
// - Menu items live in a portal and only while their dropdown is open, so they are found on
//   `screen`; menus are driven with `userEvent.setup({ pointerEventsCheck: 0 })`.
// - `fetch` is stubbed per test and routed by **exact pathname**; the mount loads the listing and
//   the setup choices. `apiDownload` runs for real, so jsdom's missing `URL.createObjectURL` /
//   `URL.revokeObjectURL` are installed per test and removed afterwards, and the anchor click is
//   swallowed by a spy on `HTMLAnchorElement.prototype.click` so jsdom never navigates.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SessionsSection } from "../../src/app/SessionsSection";
import type { Session } from "../../src/app/sessionsApi";
import { SessionsState } from "../../src/app/sessionsState";
import { documentNavigation } from "../../src/shared/api";
import { AppProviders } from "../../src/shared/AppProviders";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string };
type User = ReturnType<typeof userEvent.setup>;

// ---------------------------------------------------------------- the spec's names
const SESSIONS_REGION = /^sessions$/i;
const ROW_TRIGGER_NAME = /^actions for /i;
const EXPORT_ITEM = /^export$/i;
const ARCHIVE_ITEM = /^archive$/i;
const RESTORE_ITEM = /^restore$/i;
const SHOW_ARCHIVED_SESSIONS = /^show archived sessions$/i;

const NOTIFICATION = ".mantine-Notification-root";

/** The message the error envelope carries; a notification must show it (DoD-7). */
const FAILURE_MESSAGE = "That session does not exist (zq-404 marker).";

/** Success is silent (context.md "No success toasts"): none of these may appear. */
const SUCCESS_TALK = /\b(success|succeeded|successfully|downloaded|exported|completed|finished)\b/i;

const EXPORT_FILENAME = "rphelper-session-20260105T101112Z.json";

// ---------------------------------------------------------------- fixtures
// Ids are decimal strings past Number.MAX_SAFE_INTEGER (context.md "Ids are strings").
const CHARACTER_ID = "7250000000000000011";
const SESSIONS_PATH = `/api/characters/${CHARACTER_ID}/sessions`;
const SETUPS_PATH = `/api/characters/${CHARACTER_ID}/setups`;
const INCLUDE_ARCHIVED_SEARCH = "?include_archived=true";
const SCREEN_PATH = `/characters/${CHARACTER_ID}`;

function activeRow(id: string, createdAt: string): Session {
  return {
    id,
    character_id: CHARACTER_ID,
    setup_id: null,
    setup_name: null,
    archived_at: null,
    last_used_at: createdAt,
    created_at: createdAt,
    updated_at: createdAt,
  };
}

/** Two active rows with different ids: a wrong-id export would request the other's route. */
const ROW_A = activeRow("7250000000000000101", "2026-05-10T09:26:53.000000+00:00");
const ROW_B = activeRow("7250000000000000102", "2026-04-02T08:15:42.000000+00:00");

/** An archived row — the Export item is present for it too (R6, DoD-6). */
const ROW_ARCHIVED: Session = {
  ...activeRow("7250000000000000103", "2026-03-01T07:05:11.000000+00:00"),
  archived_at: "2026-03-02T07:05:11.000000+00:00",
};

// ---------------------------------------------------------------- jsdom gaps
let hadCreateObjectUrl: boolean;
let hadRevokeObjectUrl: boolean;

beforeEach(() => {
  let issued = 0;
  hadCreateObjectUrl = typeof URL.createObjectURL === "function";
  hadRevokeObjectUrl = typeof URL.revokeObjectURL === "function";
  URL.createObjectURL = (): string => {
    issued += 1;
    return `blob:rphelper/${issued}`;
  };
  URL.revokeObjectURL = (): void => {};

  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
});

afterEach(() => {
  if (!hadCreateObjectUrl) Reflect.deleteProperty(URL, "createObjectURL");
  if (!hadRevokeObjectUrl) Reflect.deleteProperty(URL, "revokeObjectURL");
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- fetch harness
/** context.md "Routes" — one session's export. */
function exportPath(sessionId: string): string {
  return `/api/sessions/${sessionId}/export`;
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** A domain envelope — the shape every non-2xx of ours carries. */
function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: FAILURE_MESSAGE, detail: {} } }, status);
}

function exportResponse(): Response {
  return new Response('{"format":"rphelper-export","granularity":"session","payload":{}}', {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Content-Disposition": `attachment; filename="${EXPORT_FILENAME}"`,
    },
  });
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

/**
 * The listing (honouring the include-archived flag), the setup choices, and every row's export
 * route. Routed by exact pathname; anything else is a visible 404.
 */
function serveSection(rows: Session[], options: { failExport?: boolean } = {}) {
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>((input, init) => {
    const url = requestUrl(input);
    const request: Seen = {
      method: requestMethod(input, init),
      path: url.pathname,
      search: url.search,
    };
    calls.push(request);

    if (request.method === "GET") {
      if (request.path === SESSIONS_PATH) {
        const includeArchived = request.search === INCLUDE_ARCHIVED_SEARCH;
        const listed = rows.filter((row) => includeArchived || row.archived_at === null);
        return Promise.resolve(jsonResponse({ sessions: listed }, 200));
      }
      if (request.path === SETUPS_PATH) return Promise.resolve(jsonResponse({ setups: [] }, 200));
      if (rows.some((row) => request.path === exportPath(row.id))) {
        return Promise.resolve(
          options.failExport === true ? envelope("session_not_found", 404) : exportResponse(),
        );
      }
    }
    return Promise.resolve(envelope("session_not_found", 404));
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

function matching(calls: Seen[], method: string, path: string): Seen[] {
  return calls.filter((call) => call.method === method && call.path === path);
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
function renderSection() {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={[SCREEN_PATH]}>
        <SessionsSection characterId={CHARACTER_ID} sessions={new SessionsState()} />
      </MemoryRouter>
    </AppProviders>,
  );
}

async function renderListed(rows: Session[], options: { failExport?: boolean } = {}) {
  const server = serveSection(rows, options);
  renderSection();
  await flush();
  return server;
}

// ---------------------------------------------------------------- queries
function region(): HTMLElement {
  return screen.getByRole("region", { name: SESSIONS_REGION });
}

function row(session: Session): HTMLElement {
  const link = within(region())
    .queryAllByRole("link")
    .find((candidate) => candidate.getAttribute("href") === `/sessions/${session.id}`);
  if (link === undefined) throw new Error(`no session row linking to /sessions/${session.id}`);
  const tr = link.closest("tr");
  if (tr === null) throw new Error(`the row for /sessions/${session.id} is not in a table row`);
  return tr;
}

function archivedSwitch(): HTMLElement {
  const scope = within(region());
  return (
    scope.queryByRole("switch", { name: SHOW_ARCHIVED_SESSIONS }) ??
    scope.getByRole("checkbox", { name: SHOW_ARCHIVED_SESSIONS })
  );
}

/** Opens one row's overflow menu; its items are in a portal, so they are found on `screen`. */
async function openRowMenu(user: User, session: Session): Promise<void> {
  await user.click(within(row(session)).getByRole("button", { name: ROW_TRIGGER_NAME }));
  await waitFor(() => {
    expect(screen.queryAllByRole("menuitem").length).toBeGreaterThan(0);
  });
}

async function exportItem(): Promise<HTMLElement> {
  return await screen.findByRole("menuitem", { name: EXPORT_ITEM });
}

async function chooseExport(user: User, session: Session): Promise<void> {
  await openRowMenu(user, session);
  await user.click(await exportItem());
  await flush();
}

async function showArchived(user: User): Promise<void> {
  await user.click(archivedSwitch());
  await flush();
}

function notificationRoots(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>(NOTIFICATION));
}

function dialogs(): HTMLElement[] {
  return [...screen.queryAllByRole("dialog"), ...screen.queryAllByRole("alertdialog")];
}

/** Everything the user can read, excluding the providers' injected CSS. */
function readableText(): string {
  const clone = document.body.cloneNode(true) as HTMLElement;
  for (const node of Array.from(clone.querySelectorAll("style, script"))) node.remove();
  return clone.textContent ?? "";
}

// ===========================================================================
describe("every session row's menu offers Export (US-081.AC-1)", () => {
  it("an active row's Actions menu contains an Export item — DoD-6", async () => {
    await renderListed([ROW_A, ROW_B]);
    const user = newUser();

    await openRowMenu(user, ROW_A);

    expect(await exportItem()).toBeInTheDocument();
    // The row's existing item is still there: Export is an addition, not a replacement.
    expect(screen.getByRole("menuitem", { name: ARCHIVE_ITEM })).toBeInTheDocument();
  });

  it("an archived row's Actions menu contains an Export item too — DoD-6", async () => {
    await renderListed([ROW_A, ROW_ARCHIVED]);
    const user = newUser();
    await showArchived(user);

    await openRowMenu(user, ROW_ARCHIVED);

    expect(await exportItem()).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: RESTORE_ITEM })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: ARCHIVE_ITEM })).toBeNull();
  });

  it("choosing it in the first row requests that row's export route — DoD-6", async () => {
    const { calls } = await renderListed([ROW_A, ROW_B]);
    const user = newUser();

    await chooseExport(user, ROW_A);

    expect(matching(calls, "GET", exportPath(ROW_A.id))).toHaveLength(1);
    expect(matching(calls, "GET", exportPath(ROW_B.id))).toEqual([]);
  });

  it("choosing it in the second row requests that row's export route — DoD-6", async () => {
    const { calls } = await renderListed([ROW_A, ROW_B]);
    const user = newUser();

    await chooseExport(user, ROW_B);

    expect(matching(calls, "GET", exportPath(ROW_B.id))).toHaveLength(1);
    expect(matching(calls, "GET", exportPath(ROW_A.id))).toEqual([]);
  });

  it("choosing it in an archived row requests that row's export route — DoD-6", async () => {
    const { calls } = await renderListed([ROW_A, ROW_ARCHIVED]);
    const user = newUser();
    await showArchived(user);

    await chooseExport(user, ROW_ARCHIVED);

    expect(matching(calls, "GET", exportPath(ROW_ARCHIVED.id))).toHaveLength(1);
    expect(matching(calls, "GET", exportPath(ROW_A.id))).toEqual([]);
  });

  it("the export is a GET with no query parameter — DoD-6", async () => {
    const { calls } = await renderListed([ROW_A]);
    const user = newUser();

    await chooseExport(user, ROW_A);

    expect(matching(calls, "GET", exportPath(ROW_A.id))).toEqual([
      { method: "GET", path: exportPath(ROW_A.id), search: "" },
    ]);
  });
});

// ===========================================================================
describe("feedback: silent on success, one notification on failure (DoD-7)", () => {
  it("a successful export raises no notification and shows no success text — DoD-7", async () => {
    const { calls } = await renderListed([ROW_A]);
    const user = newUser();

    await chooseExport(user, ROW_A);

    // The export really reached the server, so the silence below is a successful export's.
    expect(matching(calls, "GET", exportPath(ROW_A.id))).toEqual([
      { method: "GET", path: exportPath(ROW_A.id), search: "" },
    ]);

    expect(notificationRoots()).toEqual([]);
    expect(readableText()).not.toMatch(SUCCESS_TALK);
    expect(readableText()).not.toContain(EXPORT_FILENAME);
  });

  it("a failed export raises exactly one notification carrying the error's message — DoD-7", async () => {
    await renderListed([ROW_A], { failExport: true });
    const user = newUser();

    await chooseExport(user, ROW_A);

    await waitFor(() => {
      expect(notificationRoots()).toHaveLength(1);
    });
    expect(notificationRoots()[0].textContent ?? "").toContain(FAILURE_MESSAGE);
  });
});

// ===========================================================================
describe("no confirm dialog stands between the click and the request (DoD-8)", () => {
  it("one click on the row's Export goes straight to the request — DoD-8", async () => {
    const { calls } = await renderListed([ROW_A]);
    const user = newUser();
    await openRowMenu(user, ROW_A);
    expect(dialogs()).toEqual([]);

    await user.click(await exportItem());
    await flush();

    expect(dialogs()).toEqual([]);
    expect(matching(calls, "GET", exportPath(ROW_A.id))).toHaveLength(1);
  });
});
