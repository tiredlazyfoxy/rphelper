// Feature 031 — import-and-id-remapping, step 007: the character page's Sessions section
// "Import session" button (DoD-6, DoD-7, and DoD-8 / DoD-9 for this control). The user menu's
// item has its own file, `UserMenu.import.test.tsx`; the effects' own clauses live in step 006's
// files. DoD-10 is discharged by the two amended delivered `UserMenu` files; DoD-11 and DoD-12
// are [manual/live] and carry no test.
//
// Expected behaviour comes from `007.app-import-entry-points.md` (Interface intent + DoD),
// `007.context.md` and the feature `context.md` ("Frontend shared facts", "Reload scope after a
// roleplayer import" — a session import refreshes the section AND reloads `SessionsState` — and
// "Confirm": a roleplayer import is deliberately not confirmed). Bindings come from the frozen
// `### Step 007` / `### Step 006` records:
// - `SessionsSectionProps` is unchanged, `{ characterId; sessions }` — the existing `sessions`
//   prop is reused and no new prop was added;
// - the button's accessible name is exactly `Import session`, inside a Mantine `FileButton`
//   whose hidden `<input type="file">` accepts `.json,application/json` and carries no name;
// - the routes are `POST /api/characters/<id>/import`,
//   `GET /api/characters/<id>/sessions` (the section list, no query while `showArchived` is
//   false) and `GET /api/sessions` (the `SessionsState` list, never with a query).
//
// Harness conventions (harvest D.5, and 011's own conventions in `SessionsSection.export.test.tsx`):
// vitest with `globals: false`; `userEvent.setup({ pointerEventsCheck: 0 })`; the file choice is
// driven with `userEvent.upload` on the `FileButton`'s hidden input, which is unnamed and so is
// located by `input[type="file"]` (it is the only file input in the tree); a session row is
// identified by its link's `href` (`/sessions/<id>`), never by its start-time label; the section
// renders inside `AppProviders` + `MemoryRouter`, so notifications are observable through
// `.mantine-Notification-root`; `fetch` is stubbed per test, routed by method + exact pathname,
// and answers anything else loudly.
//
// Amended by feature 033, step 005 (D8, D9): "Import session" is now an icon-only button in the
// section's header beside the "Show archived sessions" switch (the "Start session" button it
// used to sit beside is gone), still driven by the `FileButton`, and disabled while an import is
// in flight. Its accessible name is unchanged, so the import clauses below hold as before.
import { notifications } from "@mantine/notifications";
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
type Seen = { method: string; path: string; search: string; body: string | null };
type User = ReturnType<typeof userEvent.setup>;

// ---------------------------------------------------------------- the spec's names
const SESSIONS_REGION = /^sessions$/i;
const IMPORT_BUTTON = /^import session$/i;
/** 033 D9: the removed control, named only to assert its absence. */
const START_BUTTON = /^start session$/i;
const SESSIONS_HEADING = /^sessions$/i;
const SHOW_ARCHIVED_SESSIONS = /^show archived sessions$/i;
const UPLOAD_ICON = ".tabler-icon-upload";

const NOTIFICATION = ".mantine-Notification-root";

/** context.md "Frontend shared facts" — the unreadable-file message, verbatim. */
const UNREADABLE_MESSAGE = "The chosen file is not a readable export.";

/** The sentence pinned in `006.context.md`, verbatim — never raised on a failure. */
const COVERAGE_SENTENCE =
  "Imported material won't appear in semantic search until an administrator rebuilds the search index.";

/** What the server's own refusals carry; a notification must show the server's message. */
const SERVER_MESSAGE = "That import could not be accepted (zq-fail marker).";

// ---------------------------------------------------------------- fixtures
// Ids are decimal strings past Number.MAX_SAFE_INTEGER (context.md "Ids are strings").
const CHARACTER_ID = "7250000000000000011";
const SECTION_PATH = `/api/characters/${CHARACTER_ID}/sessions`;
const SETUPS_PATH = `/api/characters/${CHARACTER_ID}/setups`;
const IMPORT_PATH = `/api/characters/${CHARACTER_ID}/import`;
const WORKSPACE_SESSIONS_PATH = "/api/sessions";
const SCREEN_PATH = `/characters/${CHARACTER_ID}`;

const NEW_SESSION_ID = "7250000000000000404";

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

/** The row the section already lists before any import. */
const ROW_A = activeRow("7250000000000000101", "2026-05-10T09:26:53.000000+00:00");

/** The row the server only has after a successful import — started in a different minute. */
const ROW_IMPORTED = activeRow(NEW_SESSION_ID, "2026-04-02T08:15:42.000000+00:00");

/**
 * The client posts the file's parsed JSON object verbatim and inspects nothing in it
 * (context.md "Transport"), so these header values are arbitrary.
 */
function sessionEnvelope(): Record<string, unknown> {
  return {
    format: "rphelper-export",
    version: 1,
    granularity: "session",
    created_at: "2026-05-10T09:26:53.000000+00:00",
    schema_version: 1,
    payload: {},
  };
}

/** `accept` is `.json,application/json`, so every fixture is named and typed to pass it. */
function exportFile(body: unknown): File {
  return new File([JSON.stringify(body)], "rphelper-export.json", { type: "application/json" });
}

/** A `.json` file whose text is not JSON. */
function unreadableFile(): File {
  return new File(["this is not json at all"], "rphelper-export.json", {
    type: "application/json",
  });
}

// ---------------------------------------------------------------- fetch harness
function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** A domain envelope — the shape every non-2xx of ours carries. */
function errorEnvelope(code: string, message: string, status: number): Response {
  return jsonResponse({ error: { code, message, detail: {} } }, status);
}

/**
 * The section list, the setup choices, the import route and the workspace sessions list, by
 * method and exact pathname. A successful import makes the server hold one more session, so a
 * later section-list answer carries a row the first one did not. Anything else is a loud 404.
 */
type ServeOptions = {
  importFailure?: { code: string; status: number };
  /** 033 step 005: hold the import's answer until `releaseImport()` is called. */
  holdImport?: true;
};

function serveSection(options: ServeOptions = {}) {
  const calls: Seen[] = [];
  const listed: Session[] = [ROW_A];
  let releaseHeld: (() => void) | null = null;
  const held =
    options.holdImport === true
      ? new Promise<void>((resolve) => {
          releaseHeld = resolve;
        })
      : Promise.resolve();
  const releaseImport = (): void => {
    releaseHeld?.();
  };
  const mock = vi.fn<FetchFn>(async (input, init) => {
    const url = requestUrl(input);
    const method = requestMethod(input, init);
    calls.push({
      method,
      path: url.pathname,
      search: url.search,
      body: typeof init?.body === "string" ? init.body : null,
    });

    if (method === "POST" && url.pathname === IMPORT_PATH) {
      await held;
      if (options.importFailure !== undefined) {
        return Promise.resolve(
          errorEnvelope(options.importFailure.code, SERVER_MESSAGE, options.importFailure.status),
        );
      }
      listed.push(ROW_IMPORTED);
      return Promise.resolve(jsonResponse({ session_id: NEW_SESSION_ID }, 200));
    }
    if (method === "GET" && url.pathname === SECTION_PATH) {
      const includeArchived = url.search === "?include_archived=true";
      const rows = listed.filter((row) => includeArchived || row.archived_at === null);
      return Promise.resolve(jsonResponse({ sessions: rows }, 200));
    }
    if (method === "GET" && url.pathname === SETUPS_PATH) {
      return Promise.resolve(jsonResponse({ setups: [] }, 200));
    }
    if (method === "GET" && url.pathname === WORKSPACE_SESSIONS_PATH) {
      return Promise.resolve(jsonResponse({ sessions: listed }, 200));
    }
    return Promise.resolve(
      errorEnvelope("not_found", `unexpected ${method} ${url.pathname}`, 404),
    );
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls, releaseImport };
}

function matching(calls: Seen[], method: string, path: string): Seen[] {
  return calls.filter((call) => call.method === method && call.path === path);
}

async function flush(rounds = 8): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => setImmediate(resolve));
    });
  }
}

function newUser(): User {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

beforeEach(() => {
  vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
});

afterEach(() => {
  act(() => {
    notifications.clean();
  });
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

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

async function renderListed(options: ServeOptions = {}) {
  const server = serveSection(options);
  renderSection();
  await flush();
  return server;
}

// ---------------------------------------------------------------- queries
function region(): HTMLElement {
  return screen.getByRole("region", { name: SESSIONS_REGION });
}

function importButton(): HTMLElement {
  return within(region()).getByRole("button", { name: IMPORT_BUTTON });
}

/** The `FileButton`'s hidden input: unnamed by design, and the only file input in the tree. */
function fileInput(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  if (input === null) throw new Error("the Sessions section renders no file input");
  return input;
}

async function chooseFile(user: User, file: File): Promise<void> {
  await user.upload(fileInput(), file);
  await flush();
}

/** The row linking to `/sessions/<id>`, or null when the section does not list it. */
function sessionRow(id: string): HTMLElement | null {
  const link = within(region())
    .queryAllByRole("link")
    .find((candidate) => candidate.getAttribute("href") === `/sessions/${id}`);
  return link?.closest("tr") ?? null;
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

function notificationRoots(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>(NOTIFICATION));
}

function notificationTexts(): string[] {
  return notificationRoots().map((root) => root.textContent ?? "");
}

function dialogs(): HTMLElement[] {
  return [...screen.queryAllByRole("dialog"), ...screen.queryAllByRole("alertdialog")];
}

// ===========================================================================
describe("the Sessions section offers Import session (US-082.AC-1, UC-064)", () => {
  // Amended by 033 step 005 (D8, D9): the button sits in the header beside the archived switch;
  // the "Start session" button it used to sit beside is gone.
  it("the section shows an Import session button in its header beside the Show archived sessions switch, and no Start session — DoD-6 (and 033 step 005 DoD-1, DoD-2)", async () => {
    await renderListed();

    expect(importButton()).toBeInTheDocument();
    const scope = within(region());
    const title = scope.getByRole("heading", { name: SESSIONS_HEADING });
    const toggle =
      scope.queryByRole("switch", { name: SHOW_ARCHIVED_SESSIONS }) ??
      scope.getByRole("checkbox", { name: SHOW_ARCHIVED_SESSIONS });
    const header = commonAncestor([title, toggle, importButton()]);
    expect(header).not.toBe(region());
    const firstRow = sessionRow(ROW_A.id);
    expect(firstRow).not.toBeNull();
    expect(header.contains(firstRow)).toBe(false);
    expect(scope.queryByRole("button", { name: START_BUTTON, hidden: true })).toBeNull();
  });

  it("choosing a session export posts it, parsed, to that character's import path — DoD-6", async () => {
    const envelope = sessionEnvelope();
    const { calls } = await renderListed();
    const user = newUser();

    await chooseFile(user, exportFile(envelope));

    const posts = matching(calls, "POST", IMPORT_PATH);
    expect(posts).toHaveLength(1);
    expect(posts[0].search).toBe("");
    expect(JSON.parse(posts[0].body ?? "null")).toEqual(envelope);
  });

  it("after success it requests the section list again and shows the new session — DoD-6 (and 033 step 005 DoD-3)", async () => {
    const { calls } = await renderListed();
    const user = newUser();
    // Baseline: the mount's listing carried only the existing row.
    expect(matching(calls, "GET", SECTION_PATH)).toHaveLength(1);
    expect(sessionRow(NEW_SESSION_ID)).toBeNull();

    await chooseFile(user, exportFile(sessionEnvelope()));

    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(1);
    expect(matching(calls, "GET", SECTION_PATH)).toHaveLength(2);
    await waitFor(() => {
      expect(sessionRow(NEW_SESSION_ID)).not.toBeNull();
    });
    // The row that was already listed is still listed.
    expect(sessionRow(ROW_A.id)).not.toBeNull();
  });

  it("after success it also requests the workspace sessions list again — DoD-6", async () => {
    const { calls } = await renderListed();
    const user = newUser();
    // The section's mount never asks for the workspace list, so any call below is the import's.
    expect(matching(calls, "GET", WORKSPACE_SESSIONS_PATH)).toEqual([]);

    await chooseFile(user, exportFile(sessionEnvelope()));

    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(1);
    expect(matching(calls, "GET", WORKSPACE_SESSIONS_PATH)).toEqual([
      { method: "GET", path: WORKSPACE_SESSIONS_PATH, search: "", body: null },
    ]);
  });

  it("a successful section import raises the coverage caveat and nothing else — DoD-6 (and 033 step 005 DoD-3)", async () => {
    const { calls } = await renderListed();
    const user = newUser();

    await chooseFile(user, exportFile(sessionEnvelope()));

    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(1);
    await waitFor(() => {
      expect(notificationRoots()).toHaveLength(1);
    });
    expect(notificationTexts()[0]).toContain(COVERAGE_SENTENCE);
  });
});

// ===========================================================================
describe("a refused session import says one thing and reloads nothing (DoD-7)", () => {
  it("a 404 character_not_found raises one notification with the server's message — DoD-7", async () => {
    const { calls } = await renderListed({
      importFailure: { code: "character_not_found", status: 404 },
    });
    const user = newUser();

    await chooseFile(user, exportFile(sessionEnvelope()));

    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(1);
    await waitFor(() => {
      expect(notificationRoots()).toHaveLength(1);
    });
    expect(notificationTexts()[0]).toContain(SERVER_MESSAGE);
    expect(notificationTexts()[0]).not.toContain(COVERAGE_SENTENCE);
  });

  it("a 404 character_not_found reloads neither list — DoD-7", async () => {
    const { calls } = await renderListed({
      importFailure: { code: "character_not_found", status: 404 },
    });
    const user = newUser();

    await chooseFile(user, exportFile(sessionEnvelope()));

    // Anchored on the request having been made and refused.
    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(1);
    expect(matching(calls, "GET", SECTION_PATH)).toHaveLength(1);
    expect(matching(calls, "GET", WORKSPACE_SESSIONS_PATH)).toEqual([]);
  });

  it("a 400 export_invalid raises one notification with the server's message and reloads neither list — DoD-7", async () => {
    const { calls } = await renderListed({
      importFailure: { code: "export_invalid", status: 400 },
    });
    const user = newUser();

    await chooseFile(user, exportFile(sessionEnvelope()));

    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(1);
    await waitFor(() => {
      expect(notificationRoots()).toHaveLength(1);
    });
    expect(notificationTexts()[0]).toContain(SERVER_MESSAGE);
    expect(matching(calls, "GET", SECTION_PATH)).toHaveLength(1);
    expect(matching(calls, "GET", WORKSPACE_SESSIONS_PATH)).toEqual([]);
  });

  it("a file whose text is not JSON raises one notification and makes no POST — DoD-7", async () => {
    const { calls } = await renderListed();
    const user = newUser();

    await chooseFile(user, unreadableFile());

    // The notification is the positive observation that the choice was handled at all.
    await waitFor(() => {
      expect(notificationRoots()).toHaveLength(1);
    });
    expect(notificationTexts()[0]).toContain(UNREADABLE_MESSAGE);
    expect(matching(calls, "POST", IMPORT_PATH)).toEqual([]);
    expect(matching(calls, "GET", SECTION_PATH)).toHaveLength(1);
    expect(matching(calls, "GET", WORKSPACE_SESSIONS_PATH)).toEqual([]);
  });
});

// ===========================================================================
describe("no confirm dialog stands between the choice and the request (DoD-8)", () => {
  it("choosing a file for the section goes straight to the request — DoD-8", async () => {
    const { calls } = await renderListed();
    const user = newUser();
    expect(dialogs()).toEqual([]);

    await chooseFile(user, exportFile(sessionEnvelope()));

    expect(dialogs()).toEqual([]);
    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(1);
  });
});

// ===========================================================================
describe("the control's name and icon (DoD-9)", () => {
  // Amended by 033 step 005 (D8): the control is icon-only; its accessible name stays exactly
  // "Import session" and it shows no text of its own.
  it("the button's accessible name is exactly Import session, and it is icon-only — DoD-9 (and 033 step 005 DoD-2)", async () => {
    await renderListed();

    const named = within(region()).getAllByRole("button", { name: "Import session" });
    expect(named).toHaveLength(1);
    expect(named[0]).toBe(importButton());
    expect((importButton().textContent ?? "").trim()).toBe("");
  });

  it("the button renders the Tabler upload icon — DoD-9 (and 033 step 005 DoD-2)", async () => {
    await renderListed();

    expect(importButton().querySelector(UPLOAD_ICON)).not.toBeNull();
  });
});

// ===========================================================================
// Feature 033, step 005 (D8, US-082): the icon button is busy — disabled — while the import is in
// flight, and the import itself behaves as before.
describe("033 step 005: Import session is disabled while an import is in flight (D8)", () => {
  it("is enabled at rest, disabled while the import request is held, and enabled again once it answers — 033 step 005 DoD-3", async () => {
    const { calls, releaseImport } = await renderListed({ holdImport: true });
    const user = newUser();
    expect(importButton()).toBeEnabled();

    await chooseFile(user, exportFile(sessionEnvelope()));

    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(1);
    await waitFor(() => {
      expect(importButton()).toBeDisabled();
    });

    await act(async () => {
      releaseImport();
      await Promise.resolve();
    });
    await flush();

    await waitFor(() => {
      expect(importButton()).toBeEnabled();
    });
    await waitFor(() => {
      expect(sessionRow(NEW_SESSION_ID)).not.toBeNull();
    });
  });

  it("a held import that is then refused also re-enables the button — 033 step 005 DoD-3", async () => {
    const { calls, releaseImport } = await renderListed({
      holdImport: true,
      importFailure: { code: "export_invalid", status: 400 },
    });
    const user = newUser();

    await chooseFile(user, exportFile(sessionEnvelope()));

    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(1);
    await waitFor(() => {
      expect(importButton()).toBeDisabled();
    });

    await act(async () => {
      releaseImport();
      await Promise.resolve();
    });
    await flush();

    await waitFor(() => {
      expect(importButton()).toBeEnabled();
    });
  });

  it("choosing a file through the header icon button imports it under this character, lists the session and raises the coverage caveat — 033 step 005 DoD-3", async () => {
    const envelope = sessionEnvelope();
    const { calls } = await renderListed();
    const user = newUser();

    await chooseFile(user, exportFile(envelope));

    const posts = matching(calls, "POST", IMPORT_PATH);
    expect(posts).toHaveLength(1);
    expect(JSON.parse(posts[0].body ?? "null")).toEqual(envelope);
    await waitFor(() => {
      expect(sessionRow(NEW_SESSION_ID)).not.toBeNull();
    });
    await waitFor(() => {
      expect(notificationRoots()).toHaveLength(1);
    });
    expect(notificationTexts()[0]).toContain(COVERAGE_SENTENCE);
    expect(importButton()).toBeEnabled();
  });
});
