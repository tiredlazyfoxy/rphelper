// Feature 031 — import-and-id-remapping, step 007: the user menu's "Import…" item
// (DoD-1..DoD-5, DoD-8, DoD-9 for this control). The section control's clauses live in
// `SessionsSection.import.test.tsx`; the effects' own clauses live in step 006's files.
// DoD-10 is discharged by the two amended delivered files (`UserMenu.test.tsx`,
// `UserMenu.export.test.tsx`), which now supply the two new props; DoD-11 and DoD-12 are
// [manual/live] and carry no test.
//
// Expected behaviour comes from `007.app-import-entry-points.md` (Interface intent + DoD),
// `007.context.md`, `006.context.md` (the pinned coverage sentence) and the feature
// `context.md` ("Frontend shared facts", "Reload scope after a roleplayer import", "Wire
// contract", "Confirm"). Bindings come from the frozen `### Step 007` / `### Step 006` records:
// - `UserMenuProps = { user; compact; charactersState; sessionsState }`;
// - the item's accessible name is exactly `Import…` (one U+2026, not three dots);
// - the hidden `<input type="file">` lives OUTSIDE the Menu and its whole accessible name is
//   `Choose a file to import`;
// - the routes are `POST /api/import`, `GET /api/characters` (no query while `showArchived` is
//   false) and `GET /api/sessions` (never with a query).
//
// Harness conventions (harvest D.5): vitest with `globals: false`, so every helper is imported
// explicitly; `userEvent.setup({ pointerEventsCheck: 0 })` because Mantine's floating layers set
// pointer-events; menu items are portalled, so they are found on `screen` by accessible name; the
// file choice is driven with `userEvent.upload` on the hidden input, found by its label (jsdom
// 30.1.1 implements `Blob.prototype.text()`, so a real `File` works); the menu renders inside
// `AppProviders` + `MemoryRouter`, so notifications are observable through
// `.mantine-Notification-root` and navigation through a `LocationProbe`; `fetch` is stubbed per
// test, routed by method + exact pathname, and answers anything else loudly.
import type * as React from "react";
import { notifications } from "@mantine/notifications";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CharactersState } from "../../src/app/charactersState";
import { SessionsState } from "../../src/app/sessionsState";
import { UserMenu } from "../../src/app/UserMenu";
import { documentNavigation } from "../../src/shared/api";
import { AppProviders } from "../../src/shared/AppProviders";
import type { CurrentUser } from "../../src/shared/currentUser";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string; body: string | null };
type User = ReturnType<typeof userEvent.setup>;
type OwnedResult = { granularity: "user" | "character"; character_ids: string[] };

// ---------------------------------------------------------------- the spec's names
const TRIGGER_NAME = /^user menu$/i;
const LOGOUT_ITEM = /^log out$/i;
/** Exactly one U+2026 HORIZONTAL ELLIPSIS — never three full stops. */
const IMPORT_ITEM = /^Import…$/;
/** Decision 9: the input's whole accessible name. */
const FILE_INPUT_LABEL = "Choose a file to import";
const UPLOAD_ICON = ".tabler-icon-upload";

/** context.md "Wire contract" and the three reload paths recorded in `### Step 006`. */
const IMPORT_PATH = "/api/import";
const CHARACTERS_PATH = "/api/characters";
const SESSIONS_PATH = "/api/sessions";

const NOTIFICATION = ".mantine-Notification-root";

/** The sentence pinned in `006.context.md`, verbatim. */
const COVERAGE_SENTENCE =
  "Imported material won't appear in semantic search until an administrator rebuilds the search index.";

/** context.md "Frontend shared facts" — the unreadable-file message, verbatim. */
const UNREADABLE_MESSAGE = "The chosen file is not a readable export.";

/** What the server's own 400 carries; a notification must show the server's message. */
const SERVER_MESSAGE = "That file is not a readable export (zq-400 marker).";

const NEW_CHARACTER_ID = "7250000000000000501";
const OTHER_CHARACTER_ID = "7250000000000000502";

/** A route that is not "/", so "stays on the current route" is a meaningful observation. */
const START_PATH = "/characters/7250000000000000011";

const ROLES: Array<CurrentUser["role"]> = ["roleplayer", "admin"];

// ---------------------------------------------------------------- fixtures
/**
 * The client posts the file's parsed JSON object verbatim and inspects nothing in it
 * (context.md "Transport"), so the header values here are arbitrary: only the round trip
 * from file text to request body is under test.
 */
function envelopeFor(granularity: string): Record<string, unknown> {
  return {
    format: "rphelper-export",
    version: 1,
    granularity,
    created_at: "2026-05-10T09:26:53.000000+00:00",
    schema_version: 1,
    payload: {},
  };
}

/** `accept` is `.json,application/json`, so every fixture is named and typed to pass it. */
function exportFile(body: unknown): File {
  return new File([JSON.stringify(body)], "rphelper-export.json", { type: "application/json" });
}

/** A `.json` file whose text is not JSON — DoD-4's first case. */
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
 * The import route plus the two list routes, by method and exact pathname. Anything else is a
 * loud 404, so a stray request is visible in `calls` and in what the page shows.
 */
function stubBackend(
  options: { result?: OwnedResult; importFailure?: { code: string; status: number } } = {},
) {
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>((input, init) => {
    const url = requestUrl(input);
    const method = requestMethod(input, init);
    calls.push({
      method,
      path: url.pathname,
      search: url.search,
      body: typeof init?.body === "string" ? init.body : null,
    });

    if (method === "POST" && url.pathname === IMPORT_PATH) {
      if (options.importFailure !== undefined) {
        return Promise.resolve(
          errorEnvelope(options.importFailure.code, SERVER_MESSAGE, options.importFailure.status),
        );
      }
      const result: OwnedResult = options.result ?? {
        granularity: "character",
        character_ids: [NEW_CHARACTER_ID],
      };
      return Promise.resolve(jsonResponse(result, 200));
    }
    if (method === "GET" && url.pathname === CHARACTERS_PATH) {
      return Promise.resolve(jsonResponse({ characters: [] }, 200));
    }
    if (method === "GET" && url.pathname === SESSIONS_PATH) {
      return Promise.resolve(jsonResponse({ sessions: [] }, 200));
    }
    return Promise.resolve(
      errorEnvelope("not_found", `unexpected ${method} ${url.pathname}`, 404),
    );
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
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
function identity(role: CurrentUser["role"]): CurrentUser {
  return { id: "9007199254740993", username: "zmiraqua", role };
}

function LocationProbe(): React.JSX.Element {
  const location = useLocation();
  return <output data-testid="probe-location">{location.pathname}</output>;
}

function currentPath(): string {
  return screen.getByTestId("probe-location").textContent ?? "";
}

function renderMenu(role: CurrentUser["role"], initialPath = "/") {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={[initialPath]}>
        <UserMenu
          user={identity(role)}
          compact={false}
          charactersState={new CharactersState()}
          sessionsState={new SessionsState()}
        />
        <LocationProbe />
      </MemoryRouter>
    </AppProviders>,
  );
}

// ---------------------------------------------------------------- queries
function trigger(): HTMLElement {
  return screen.getByRole("button", { name: TRIGGER_NAME });
}

/** Opens the dropdown (a portal, mounted only while open) and waits for its content. */
async function openMenu(user: User): Promise<void> {
  await user.click(trigger());
  await screen.findByText(LOGOUT_ITEM);
}

async function importItem(): Promise<HTMLElement> {
  return await screen.findByRole("menuitem", { name: IMPORT_ITEM });
}

/** The hidden input lives outside the Menu, so it is present without opening the dropdown. */
function fileInput(): HTMLElement {
  return screen.getByLabelText(FILE_INPUT_LABEL);
}

async function chooseFile(user: User, file: File): Promise<void> {
  await user.upload(fileInput(), file);
  await flush();
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
describe("the user menu offers Import… to every role (US-080.AC-2)", () => {
  it.each(ROLES)("a %s sees an Import… item — DoD-1", async (role) => {
    stubBackend();
    const user = newUser();
    renderMenu(role);

    await openMenu(user);

    expect(await importItem()).toBeInTheDocument();
  });

  it.each(ROLES)("a %s can choose a file through the menu's hidden input — DoD-1", async (role) => {
    const { calls } = stubBackend();
    const user = newUser();
    renderMenu(role);

    await chooseFile(user, exportFile(envelopeFor("character")));

    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(1);
  });
});

// ===========================================================================
describe("a character export posted from the user menu (DoD-1, US-080.AC-2)", () => {
  it("is posted, parsed, to POST /api/import — DoD-1", async () => {
    const envelope = envelopeFor("character");
    const { calls } = stubBackend();
    const user = newUser();
    renderMenu("roleplayer");

    await chooseFile(user, exportFile(envelope));

    const posts = matching(calls, "POST", IMPORT_PATH);
    expect(posts).toHaveLength(1);
    expect(posts[0].search).toBe("");
    expect(JSON.parse(posts[0].body ?? "null")).toEqual(envelope);
  });

  it("then requests both the characters list and the sessions list again — DoD-1", async () => {
    const { calls } = stubBackend();
    const user = newUser();
    renderMenu("roleplayer");

    await chooseFile(user, exportFile(envelopeFor("character")));

    // The import really reached the server, so the reloads below are a successful import's.
    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(1);
    expect(matching(calls, "GET", CHARACTERS_PATH)).toEqual([
      { method: "GET", path: CHARACTERS_PATH, search: "", body: null },
    ]);
    expect(matching(calls, "GET", SESSIONS_PATH)).toEqual([
      { method: "GET", path: SESSIONS_PATH, search: "", body: null },
    ]);
  });

  it("lands on /characters/<the returned id> — DoD-1", async () => {
    stubBackend({ result: { granularity: "character", character_ids: [NEW_CHARACTER_ID] } });
    const user = newUser();
    renderMenu("roleplayer", START_PATH);
    expect(currentPath()).toBe(START_PATH);

    await chooseFile(user, exportFile(envelopeFor("character")));

    await waitFor(() => {
      expect(currentPath()).toBe(`/characters/${NEW_CHARACTER_ID}`);
    });
  });
});

// ===========================================================================
describe("a user export posted from the user menu (DoD-2, US-079.AC-2)", () => {
  const USER_RESULT: OwnedResult = {
    granularity: "user",
    character_ids: [NEW_CHARACTER_ID, OTHER_CHARACTER_ID],
  };

  it("is posted to POST /api/import and reloads both lists — DoD-2", async () => {
    const envelope = envelopeFor("user");
    const { calls } = stubBackend({ result: USER_RESULT });
    const user = newUser();
    renderMenu("roleplayer", START_PATH);

    await chooseFile(user, exportFile(envelope));

    const posts = matching(calls, "POST", IMPORT_PATH);
    expect(posts).toHaveLength(1);
    expect(JSON.parse(posts[0].body ?? "null")).toEqual(envelope);
    expect(matching(calls, "GET", CHARACTERS_PATH)).toHaveLength(1);
    expect(matching(calls, "GET", SESSIONS_PATH)).toHaveLength(1);
  });

  it("stays on the current route, even though character ids came back — DoD-2", async () => {
    const { calls } = stubBackend({ result: USER_RESULT });
    const user = newUser();
    renderMenu("roleplayer", START_PATH);

    await chooseFile(user, exportFile(envelopeFor("user")));

    // The import really happened, so the unchanged route is a successful import's.
    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(1);
    expect(currentPath()).toBe(START_PATH);
  });
});

// ===========================================================================
describe("the coverage caveat is the only thing a successful import says (DoD-3)", () => {
  it("a successful character import raises exactly one notification, carrying the coverage sentence — DoD-3", async () => {
    const { calls } = stubBackend();
    const user = newUser();
    renderMenu("roleplayer");

    await chooseFile(user, exportFile(envelopeFor("character")));

    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(1);
    await waitFor(() => {
      expect(notificationRoots()).toHaveLength(1);
    });
    expect(notificationTexts()[0]).toContain(COVERAGE_SENTENCE);
    // No second notification arrives behind it.
    await flush();
    expect(notificationRoots()).toHaveLength(1);
  });

  it("a successful user import raises exactly one notification too — DoD-3", async () => {
    const { calls } = stubBackend({
      result: { granularity: "user", character_ids: [NEW_CHARACTER_ID] },
    });
    const user = newUser();
    renderMenu("roleplayer");

    await chooseFile(user, exportFile(envelopeFor("user")));

    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(1);
    await waitFor(() => {
      expect(notificationRoots()).toHaveLength(1);
    });
    expect(notificationTexts()[0]).toContain(COVERAGE_SENTENCE);
  });
});

// ===========================================================================
describe("a failed import says one thing and reloads nothing (DoD-4)", () => {
  it("a file whose text is not JSON raises one notification and makes no POST — DoD-4", async () => {
    const { calls } = stubBackend();
    const user = newUser();
    renderMenu("roleplayer");

    await chooseFile(user, unreadableFile());

    // The notification is the positive observation that the choice was handled at all.
    await waitFor(() => {
      expect(notificationRoots()).toHaveLength(1);
    });
    expect(notificationTexts()[0]).toContain(UNREADABLE_MESSAGE);
    expect(matching(calls, "POST", IMPORT_PATH)).toEqual([]);
    expect(matching(calls, "GET", CHARACTERS_PATH)).toEqual([]);
    expect(matching(calls, "GET", SESSIONS_PATH)).toEqual([]);
  });

  it("a 400 export_invalid answer raises one notification with the server's message — DoD-4", async () => {
    const { calls } = stubBackend({ importFailure: { code: "export_invalid", status: 400 } });
    const user = newUser();
    renderMenu("roleplayer");

    await chooseFile(user, exportFile(envelopeFor("character")));

    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(1);
    await waitFor(() => {
      expect(notificationRoots()).toHaveLength(1);
    });
    expect(notificationTexts()[0]).toContain(SERVER_MESSAGE);
    expect(notificationTexts()[0]).not.toContain(COVERAGE_SENTENCE);
  });

  it("a refused import reloads neither list — DoD-4", async () => {
    const { calls } = stubBackend({ importFailure: { code: "export_invalid", status: 400 } });
    const user = newUser();
    renderMenu("roleplayer", START_PATH);

    await chooseFile(user, exportFile(envelopeFor("character")));

    // Anchored on the request having been made and refused.
    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(1);
    expect(matching(calls, "GET", CHARACTERS_PATH)).toEqual([]);
    expect(matching(calls, "GET", SESSIONS_PATH)).toEqual([]);
    expect(currentPath()).toBe(START_PATH);
  });
});

// ===========================================================================
describe("the same file may be chosen again (DoD-5, US-136.AC-2)", () => {
  it("choosing the same file twice in a row posts twice — DoD-5", async () => {
    const { calls } = stubBackend();
    const user = newUser();
    renderMenu("roleplayer");
    const file = exportFile(envelopeFor("character"));

    await chooseFile(user, file);
    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(1);

    await chooseFile(user, file);

    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(2);
  });

  it("each of the two imports reloads both lists — DoD-5", async () => {
    const { calls } = stubBackend();
    const user = newUser();
    renderMenu("roleplayer");
    const file = exportFile(envelopeFor("character"));

    await chooseFile(user, file);
    await chooseFile(user, file);

    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(2);
    expect(matching(calls, "GET", CHARACTERS_PATH)).toHaveLength(2);
    expect(matching(calls, "GET", SESSIONS_PATH)).toHaveLength(2);
  });
});

// ===========================================================================
describe("no confirm dialog stands between the choice and the request (DoD-8)", () => {
  it("choosing a file goes straight to the request — DoD-8", async () => {
    const { calls } = stubBackend();
    const user = newUser();
    renderMenu("roleplayer");
    await openMenu(user);
    await user.click(await importItem());
    // The picker's click opens no dialog, and nothing has been posted yet.
    expect(dialogs()).toEqual([]);
    expect(matching(calls, "POST", IMPORT_PATH)).toEqual([]);

    await chooseFile(user, exportFile(envelopeFor("character")));

    expect(dialogs()).toEqual([]);
    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(1);
  });
});

// ===========================================================================
describe("the control's name and icon (DoD-9)", () => {
  it("the item's accessible name is exactly Import… — DoD-9", async () => {
    stubBackend();
    const user = newUser();
    renderMenu("roleplayer");

    await openMenu(user);

    const item = await importItem();
    expect(item).toBeInTheDocument();
    expect((item.textContent ?? "").trim()).toBe("Import…");
  });

  it("the item renders the Tabler upload icon — DoD-9", async () => {
    stubBackend();
    const user = newUser();
    renderMenu("roleplayer");

    await openMenu(user);

    const item = await importItem();
    expect(item.querySelector(UPLOAD_ICON)).not.toBeNull();
  });
});
