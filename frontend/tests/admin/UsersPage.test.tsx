// Feature 005, step 006 — the Users page: the list, the table, the row overflow menu, and
// disable (behind the shared confirm) / re-enable (DoD-3..DoD-17 at the page level).
// DoD-1/DoD-2 live in tests/shared/ConfirmModal.test.tsx; the store and its free functions are
// also exercised directly in usersPageState.test.ts. DoD-18..DoD-21 are [manual/live].
//
// Expected behaviour comes from the step's Interface intent, 006.context.md and context.md
// (D5 routes, D7 confirm, D16 MobX, R5, never-optimistic, no notifications). `UsersPage` takes no
// props and owns its store; `fetch` is stubbed per test with a tiny in-memory backend for the
// three routes the page may call. `notifyFailure` is mocked at file level. The store module is
// wrapped pass-through so the page's calls to its free functions (and the store instance they
// receive) are observable — behaviour is unchanged.
//
// Recognition conventions (from spec wording, for the verifier):
// - Loader: Mantine `Loader` root, `.mantine-Loader-root`. Table: the `<table>` element; rows are
//   `tbody tr`. Inline error: Mantine `Alert`, `role="alert"`. Notifications:
//   `.mantine-Notification-root`.
// - Enabled/disabled status text: /\b(active|enabled)\b/i vs /\b(disabled|inactive)\b/i, matched
//   against the row's cells read one by one (cell texts joined with a separator), never against
//   the row's raw concatenated text.
// - Menu items are looked up inside the dropdown owned by the trigger just clicked.
// - Role text: /admin/i and /role\s*-?player/i.
// - Row menu entries: Mantine `Menu.Item` (`role="menuitem"`) named /\bdisable\b/i and
//   /\bre-?\s?enable\b/i. The confirm: `role="dialog"`, confirm button /\bdisable\b/i, cancel
//   /cancel/i. The null last-login cell: a `td` whose text is exactly "—" (U+2014).
import { readFileSync } from "node:fs";
import path from "node:path";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { isObservableProp } from "mobx";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UsersPage } from "../../src/admin/UsersPage";
import { type AdminUserRow, UsersPageState } from "../../src/admin/usersPageState";
import { AppProviders } from "../../src/shared/AppProviders";

const { notifyFailureSpy, spied } = vi.hoisted(() => ({
  notifyFailureSpy: vi.fn(),
  spied: { load: [] as unknown[][], disable: [] as unknown[][], enable: [] as unknown[][] },
}));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));
vi.mock("../../src/admin/usersPageState", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../src/admin/usersPageState")>();
  return {
    ...actual,
    loadUsers: (...args: Parameters<typeof actual.loadUsers>) => {
      spied.load.push(args);
      return actual.loadUsers(...args);
    },
    disableUser: (...args: Parameters<typeof actual.disableUser>) => {
      spied.disable.push(args);
      return actual.disableUser(...args);
    },
    enableUser: (...args: Parameters<typeof actual.enableUser>) => {
      spied.enable.push(args);
      return actual.enableUser(...args);
    },
  };
});

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type User = ReturnType<typeof userEvent.setup>;

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const PAGE_MODULES = [
  path.join(FRONTEND_ROOT, "src", "admin", "UsersPage.tsx"),
  path.join(FRONTEND_ROOT, "src", "admin", "usersPageState.ts"),
  path.join(FRONTEND_ROOT, "src", "shared", "ConfirmModal.tsx"),
];

const LIST_PATH = "/api/admin/users";
const ACTION_PATH = /^\/api\/admin\/users\/([^/]+)\/(disable|enable)$/;
const FAILURE_MESSAGE = "The account ledger is on fire zq-64.";
const BIG_ID = "9007199254740993"; // 2^53 + 1
const EM_DASH = "—";

const ENABLED_STATUS = /\b(active|enabled)\b/i;
const DISABLED_STATUS = /\b(disabled|inactive)\b/i;
const ADMIN_ROLE = /admin/i;
const ROLEPLAYER_ROLE = /role\s*-?player/i;
const DISABLE_ITEM = /\bdisable\b/i;
const REENABLE_ITEM = /\bre-?\s?enable\b/i;
const CANCEL_NAME = /cancel/i;
const NOTIFICATION_ROOT = ".mantine-Notification-root";
const LOADER = ".mantine-Loader-root";
/** R5 / US-011.AC-2 — nothing about any of these may appear on the page. */
const FORBIDDEN_CONTENT = /\b(characters?|setups?|sessions?|entry|entries|memos?)\b/i;
/**
 * DoD-12 — the confirm describes the action; it may say the person is signed out (an auth
 * session), but names none of the RP-domain things a blast-radius count would be made of.
 */
const OTHER_USERS_DATA = /\b(characters?|setups?|entry|entries|memos?)\b/i;
const NUMBER_WORDS =/\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|dozens?|several|many)\b/i;

const MIREILLE: AdminUserRow = {
  id: "7340032000000101",
  username: "mireille",
  role: "roleplayer",
  is_enabled: true,
  last_login_at: "2026-03-14T09:26:53.000000+00:00",
};
const ZORA: AdminUserRow = {
  id: "7340032000000102",
  username: "zora",
  role: "roleplayer",
  is_enabled: false,
  last_login_at: null,
};
const ANSELM: AdminUserRow = {
  id: "7340032000000103",
  username: "anselm",
  role: "admin",
  is_enabled: true,
  last_login_at: null,
};
const EVERYONE = [MIREILLE, ZORA, ANSELM];

beforeEach(() => {
  notifyFailureSpy.mockClear();
  spied.load.length = 0;
  spied.disable.length = 0;
  spied.enable.length = 0;
  window.localStorage.clear();
});

afterEach(async () => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  const { notifications } = await import("@mantine/notifications");
  act(() => {
    notifications.clean();
  });
});

// ---------------------------------------------------------------- fetch

function stubFetch(impl: FetchFn) {
  const mock = vi.fn<FetchFn>(impl);
  vi.stubGlobal("fetch", mock);
  return mock;
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function failureResponse(): Response {
  return jsonResponse({ error: { code: "internal_error", message: FAILURE_MESSAGE, detail: {} } }, 500);
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

type Seen = { method: string; path: string; search: string };

function seen(mock: ReturnType<typeof stubFetch>): Seen[] {
  return mock.mock.calls.map(([input, init]) => {
    const url = requestUrl(input);
    return { method: requestMethod(input, init), path: url.pathname, search: url.search };
  });
}

function copyRows(rows: Array<Record<string, unknown>>): Array<Record<string, unknown>> {
  return rows.map((row) => ({ ...row }));
}

type Override = (method: string, path: string) => Promise<Response> | undefined;

/** A tiny in-memory backend for GET /api/admin/users and POST .../{id}/(disable|enable). */
function serveUsers(initial: Array<Record<string, unknown>>, override?: Override) {
  const rows = copyRows(initial);
  const mock = stubFetch((input, init) => {
    const method = requestMethod(input, init);
    const pathname = requestUrl(input).pathname;
    const custom = override?.(method, pathname);
    if (custom !== undefined) return custom;
    if (method === "GET" && pathname === LIST_PATH) {
      return Promise.resolve(jsonResponse({ users: copyRows(rows) }, 200));
    }
    const match = ACTION_PATH.exec(pathname);
    if (method === "POST" && match !== null) {
      const row = rows.find((candidate) => candidate.id === match[1]);
      if (row === undefined) {
        return Promise.resolve(
          jsonResponse({ error: { code: "user_not_found", message: "That account does not exist.", detail: {} } }, 404),
        );
      }
      row.is_enabled = match[2] === "enable";
      return Promise.resolve(jsonResponse({ ...row }, 200));
    }
    return Promise.resolve(jsonResponse({ error: { code: "not_found", message: "no such route", detail: {} } }, 404));
  });
  return { mock, rows };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

async function flush(rounds = 6): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => setImmediate(resolve));
    });
  }
}

// ---------------------------------------------------------------- render + queries

function renderPage() {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={["/"]}>
        <UsersPage />
      </MemoryRouter>
    </AppProviders>,
  );
}

async function renderLoaded(rows: Array<Record<string, unknown>> = EVERYONE, override?: Override) {
  const server = serveUsers(rows, override);
  const view = renderPage();
  await flush();
  return { ...server, view };
}

function newUser(): User {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

function table(): HTMLTableElement {
  const found = document.querySelector("table");
  if (found === null) throw new Error("no <table> rendered");
  return found;
}

function bodyRows(): HTMLTableRowElement[] {
  return Array.from(table().querySelectorAll<HTMLTableRowElement>("tbody tr"));
}

function rowFor(username: string): HTMLTableRowElement {
  const matches = bodyRows().filter((tr) =>
    Array.from(tr.querySelectorAll("td")).some((td) => (td.textContent ?? "").trim() === username),
  );
  expect(matches, `rows showing ${username}`).toHaveLength(1);
  return matches[0];
}

/**
 * The row's text read cell by cell: each `td`'s text, joined with a separator, so a word in one
 * cell (e.g. the status badge) is never glued to the end of the neighbouring cell's text (e.g. a
 * last-login date-time ending in a meridiem marker). Status/role recognition is per cell.
 */
function rowText(username: string): string {
  return Array.from(rowFor(username).querySelectorAll("td"))
    .map((td) => (td.textContent ?? "").trim())
    .join(" | ");
}

function renderedUsernames(known: readonly string[]): string[] {
  return bodyRows().map((tr) => {
    const cells = Array.from(tr.querySelectorAll("td")).map((td) => (td.textContent ?? "").trim());
    return cells.find((text) => known.includes(text)) ?? "";
  });
}

function iconOnlyControls(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      "button, a[href], [role='button'], input[type='button'], input[type='image'], input[type='submit']",
    ),
  ).filter((el) => (el.textContent ?? "").trim() === "");
}

function menuTrigger(username: string): HTMLElement {
  const controls = iconOnlyControls(rowFor(username));
  expect(controls, `icon-only controls in ${username}'s row`).toHaveLength(1);
  return controls[0];
}

/**
 * The element carrying the menu-target wiring for `username`'s trigger: the nearest element at or
 * above the clicked icon-only control — and still inside that row — that carries `aria-controls`,
 * `aria-haspopup` or an `id`. The wiring may sit on the control itself or on a wrapper around it.
 */
function wiredTarget(username: string): HTMLElement {
  const row = rowFor(username);
  const trigger = menuTrigger(username);
  const wired = trigger.closest<HTMLElement>("[aria-controls], [aria-haspopup]");
  if (wired !== null && row.contains(wired)) return wired;
  const withId = trigger.closest<HTMLElement>("[id]");
  if (withId !== null && row.contains(withId)) return withId;
  throw new Error(`no menu-target wiring at or above ${username}'s trigger within the row`);
}

/**
 * The dropdown belonging to `username`'s trigger, resolved strictly through its relationship to
 * that trigger: the element the wired target's `aria-controls` names, or the menu whose
 * `aria-labelledby` is the wired target's id. Never any other menu on the page — a still-mounted,
 * closing dropdown from another row is never accepted. Throws until the dropdown exists, so it is
 * meant to be polled inside `waitFor`.
 */
function dropdownFor(username: string): HTMLElement {
  const wired = wiredTarget(username);
  const controls = wired.getAttribute("aria-controls");
  if (controls) {
    const byId = document.getElementById(controls);
    if (byId !== null) return byId;
  }
  if (wired.id) {
    const labelled = Array.from(document.querySelectorAll<HTMLElement>("[aria-labelledby]")).filter(
      (menu) => (menu.getAttribute("aria-labelledby") ?? "").split(/\s+/).includes(wired.id),
    );
    if (labelled.length === 1) return labelled[0];
  }
  throw new Error(`the dropdown owned by ${username}'s trigger is not mounted yet`);
}

async function openRowMenu(user: User, username: string): Promise<HTMLElement> {
  await user.click(menuTrigger(username));
  return waitFor(() => dropdownFor(username));
}

async function chooseMenuItem(user: User, menu: HTMLElement, name: RegExp): Promise<void> {
  const item = await within(menu).findByRole("menuitem", { name });
  await user.click(item);
}

async function openDisableConfirm(user: User, username: string): Promise<HTMLElement> {
  const menu = await openRowMenu(user, username);
  await chooseMenuItem(user, menu, DISABLE_ITEM);
  return screen.findByRole("dialog");
}

function alerts(): HTMLElement[] {
  return screen.queryAllByRole("alert");
}

function alertWith(message: string): HTMLElement {
  const matching = alerts().filter((el) => (el.textContent ?? "").includes(message));
  expect(matching.length, `alerts carrying "${message}"`).toBeGreaterThan(0);
  return matching[0];
}

function isBefore(first: Node, second: Node): boolean {
  return (first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

function notificationRoots(): Element[] {
  return Array.from(document.querySelectorAll(NOTIFICATION_ROOT));
}

function loaders(): Element[] {
  return Array.from(document.querySelectorAll(LOADER));
}

/** Every piece of text a person could read or hear: text content plus naming attributes. */
function readableText(): string {
  const attributes = ["aria-label", "title", "aria-description", "placeholder", "alt", "aria-valuetext"];
  const values = Array.from(document.body.querySelectorAll("*")).flatMap((el) =>
    attributes.map((name) => el.getAttribute(name) ?? "").filter(Boolean),
  );
  return [document.body.textContent ?? "", ...values].join("\n");
}

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

function importSpecifiers(source: string): string[] {
  const pattern = /(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)["']([^"']+)["']/g;
  return Array.from(stripComments(source).matchAll(pattern), (m) => m[1]);
}

function pageStore(): UsersPageState {
  expect(spied.load.length, "loadUsers calls from the page").toBeGreaterThan(0);
  const store = spied.load[0][0];
  expect(store).toBeInstanceOf(UsersPageState);
  return store as UsersPageState;
}

// ---------------------------------------------------------------------------
describe("loading", () => {
  it("on mount issues exactly one request, for the admin users list — DoD-3", async () => {
    const { mock } = await renderLoaded();
    expect(seen(mock)).toEqual([{ method: "GET", path: LIST_PATH, search: "" }]);
  });

  it("renders a Loader, not an empty table, while the list is in flight — DoD-3", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    renderPage();
    await flush();

    expect(loaders().length).toBeGreaterThan(0);
    expect(document.querySelector("table")).toBeNull();

    pending.resolve(jsonResponse({ users: copyRows(EVERYONE) }, 200));
    await flush();
    expect(loaders()).toEqual([]);
    expect(bodyRows()).toHaveLength(3);
  });

  it("an empty list renders the table's headers with no rows and no Loader — DoD-3", async () => {
    await renderLoaded([]);
    expect(loaders()).toEqual([]);
    const headers = Array.from(table().querySelectorAll("th")).map((th) => th.textContent ?? "");
    expect(headers.some((text) => /user\s*name/i.test(text))).toBe(true);
    expect(headers.some((text) => /role/i.test(text))).toBe(true);
    expect(headers.some((text) => /last\s*login/i.test(text))).toBe(true);
    expect(headers.some((text) => /active|enabled|status/i.test(text))).toBe(true);
    expect(bodyRows()).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
describe("the loaded table", () => {
  it("renders one row per account — DoD-4 (US-011.AC-1)", async () => {
    await renderLoaded();
    expect(bodyRows()).toHaveLength(3);
    for (const account of EVERYONE) rowFor(account.username);
  });

  it("each row shows the account's username and role — DoD-4 (US-011.AC-1)", async () => {
    await renderLoaded();
    expect(rowText("anselm")).toMatch(ADMIN_ROLE);
    expect(rowText("mireille")).toMatch(ROLEPLAYER_ROLE);
    expect(rowText("mireille")).not.toMatch(ADMIN_ROLE);
    expect(rowText("zora")).toMatch(ROLEPLAYER_ROLE);
    expect(rowText("zora")).not.toMatch(ADMIN_ROLE);
  });

  it("each row shows whether the account is enabled or disabled — DoD-4 (US-011.AC-1)", async () => {
    await renderLoaded();
    for (const name of ["mireille", "anselm"]) {
      expect(rowText(name), name).toMatch(ENABLED_STATUS);
      expect(rowText(name), name).not.toMatch(DISABLED_STATUS);
    }
    expect(rowText("zora")).toMatch(DISABLED_STATUS);
    expect(rowText("zora")).not.toMatch(ENABLED_STATUS);
  });

  it("rows keep the server's order, whatever the ids — DoD-17", async () => {
    await renderLoaded([
      { ...MIREILLE, id: "20" },
      { ...ZORA, id: "3" },
      { ...ANSELM, id: "100" },
    ]);
    expect(renderedUsernames(["mireille", "zora", "anselm"])).toEqual(["mireille", "zora", "anselm"]);
  });

  it("an account with no last login renders an em dash, not an empty cell or 'null' — DoD-6", async () => {
    await renderLoaded();
    for (const name of ["zora", "anselm"]) {
      const cells = Array.from(rowFor(name).querySelectorAll("td")).map((td) => (td.textContent ?? "").trim());
      expect(cells, name).toContain(EM_DASH);
      expect(rowText(name), name).not.toMatch(/\bnull\b|\bundefined\b|Invalid Date/i);
    }
  });

  it("an account with a last login renders a date-time, not an em dash or a relative time — DoD-6", async () => {
    await renderLoaded();
    const text = rowText("mireille");
    expect(text).not.toContain(EM_DASH);
    expect(text).not.toMatch(/\bnull\b|\bundefined\b|Invalid Date|\bago\b/i);
    expect(text).toContain("2026");
  });
});

// ---------------------------------------------------------------------------
describe("R5 — the page shows accounts and nothing else", () => {
  it("renders no text, label or tooltip about a character, setup, session, entry or memo — DoD-5 (US-011.AC-2, UC-066)", async () => {
    const user = newUser();
    await renderLoaded();
    expect(readableText()).not.toMatch(FORBIDDEN_CONTENT);

    for (const account of EVERYONE) {
      await user.hover(menuTrigger(account.username));
      await flush(2);
      expect(readableText(), `hovering ${account.username}'s trigger`).not.toMatch(FORBIDDEN_CONTENT);
      await user.unhover(menuTrigger(account.username));
    }
  });

  it("the row menus carry nothing about a character, setup, session, entry or memo — DoD-5 (US-011.AC-2)", async () => {
    const user = newUser();
    await renderLoaded();
    await openRowMenu(user, "mireille");
    await screen.findByRole("menuitem", { name: DISABLE_ITEM });
    expect(readableText()).not.toMatch(FORBIDDEN_CONTENT);
  });

  it("renders no count even if the payload carried one — DoD-5 (R5)", async () => {
    await renderLoaded(
      EVERYONE.map((row) => ({
        ...row,
        last_login_at: null,
        character_count: 4817,
        session_count: 9253,
        memo_count: 6031,
        setups: 7719,
      })),
    );
    const text = readableText();
    for (const count of ["4817", "9253", "6031", "7719"]) {
      expect(text).not.toContain(count);
    }
    expect(text).not.toMatch(FORBIDDEN_CONTENT);
  });

  it("issues no request but the list and the two mutations, none with a query — DoD-5 (UC-066)", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();

    const dialog = await openDisableConfirm(user, "mireille");
    await user.click(within(dialog).getByRole("button", { name: DISABLE_ITEM }));
    await flush();
    await chooseMenuItem(user, await openRowMenu(user, "zora"), REENABLE_ITEM);
    await flush();

    const calls = seen(mock);
    expect(calls.length).toBeGreaterThan(1);
    for (const call of calls) {
      const allowed =
        (call.method === "GET" && call.path === LIST_PATH) ||
        (call.method === "POST" && ACTION_PATH.test(call.path));
      expect(allowed, `${call.method} ${call.path}`).toBe(true);
      expect(call.search, `${call.method} ${call.path}`).toBe("");
    }
  });
});

// ---------------------------------------------------------------------------
describe("failures render inline", () => {
  it("a failed load renders an inline Alert with the error's message and no notification — DoD-7", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    renderPage();
    await flush();

    const alert = alertWith(FAILURE_MESSAGE);
    const rendered = document.querySelector("table");
    if (rendered !== null) expect(isBefore(alert, rendered)).toBe(true);
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("a failed disable renders the Alert above the table and keeps the loaded rows — DoD-7", async () => {
    const user = newUser();
    await renderLoaded(EVERYONE, (method) => (method === "POST" ? Promise.resolve(failureResponse()) : undefined));

    const dialog = await openDisableConfirm(user, "mireille");
    await user.click(within(dialog).getByRole("button", { name: DISABLE_ITEM }));
    await flush();

    const alert = alertWith(FAILURE_MESSAGE);
    expect(isBefore(alert, table())).toBe(true);
    expect(bodyRows()).toHaveLength(3);
    for (const account of EVERYONE) rowFor(account.username);
    expect(rowText("mireille")).toMatch(ENABLED_STATUS);
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("a failed re-enable renders the Alert above the table and keeps the loaded rows — DoD-7", async () => {
    const user = newUser();
    await renderLoaded(EVERYONE, (method) => (method === "POST" ? Promise.resolve(failureResponse()) : undefined));

    await chooseMenuItem(user, await openRowMenu(user, "zora"), REENABLE_ITEM);
    await flush();

    const alert = alertWith(FAILURE_MESSAGE);
    expect(isBefore(alert, table())).toBe(true);
    expect(bodyRows()).toHaveLength(3);
    for (const account of EVERYONE) rowFor(account.username);
    expect(rowText("zora")).toMatch(DISABLED_STATUS);
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("the row overflow menu", () => {
  it("each row has exactly one icon-only control, named for that row's account — DoD-8", async () => {
    await renderLoaded();
    const names: string[] = [];
    for (const account of EVERYONE) {
      const controls = iconOnlyControls(rowFor(account.username));
      expect(controls, account.username).toHaveLength(1);
      expect(controls[0]).toHaveAccessibleName(new RegExp(account.username));
      names.push(controls[0].getAttribute("aria-label") ?? controls[0].textContent ?? "");
    }
    expect(new Set(names).size).toBe(EVERYONE.length);
  });

  it.each([
    ["an enabled", MIREILLE.username],
    ["a disabled", ZORA.username],
  ])("the icon-only control opens %s account's menu, whose entries are labelled text — DoD-8", async (_kind, username) => {
    const user = newUser();
    await renderLoaded();
    await openRowMenu(user, username);
    const items = await screen.findAllByRole("menuitem");
    expect(items.length).toBeGreaterThan(0);
    for (const item of items) {
      expect((item.textContent ?? "").trim().length, "menu entry text").toBeGreaterThan(0);
    }
  });

  it("an enabled account's menu offers Disable and not Re-enable — DoD-9", async () => {
    const user = newUser();
    await renderLoaded();
    await openRowMenu(user, "mireille");
    expect(await screen.findByRole("menuitem", { name: DISABLE_ITEM })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: REENABLE_ITEM })).toBeNull();
  });

  it("a disabled account's menu offers Re-enable and not Disable — DoD-9", async () => {
    const user = newUser();
    await renderLoaded();
    await openRowMenu(user, "zora");
    expect(await screen.findByRole("menuitem", { name: REENABLE_ITEM })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: DISABLE_ITEM })).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("disable goes through the shared confirm", () => {
  it("choosing Disable opens the confirm and issues no request — DoD-10 (US-009.AC-1)", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    const before = mock.mock.calls.length;

    const dialog = await openDisableConfirm(user, "mireille");
    expect(within(dialog).getByRole("button", { name: DISABLE_ITEM })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: CANCEL_NAME })).toBeInTheDocument();
    await flush();
    expect(mock.mock.calls.length).toBe(before);
  });

  it("cancelling issues no request at all, closes the confirm and leaves the row enabled — DoD-10", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    const before = seen(mock);

    const dialog = await openDisableConfirm(user, "mireille");
    await user.click(within(dialog).getByRole("button", { name: CANCEL_NAME }));
    await flush();

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(seen(mock)).toEqual(before);
    expect(rowText("mireille")).toMatch(ENABLED_STATUS);
    expect(spied.disable).toEqual([]);
  });

  it("confirming posts to that account's disable route and then re-loads the list — DoD-11 (US-009.AC-1)", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();

    const dialog = await openDisableConfirm(user, "mireille");
    await user.click(within(dialog).getByRole("button", { name: DISABLE_ITEM }));
    await flush();

    const calls = seen(mock);
    const posts = calls.filter((call) => call.method === "POST");
    expect(posts).toEqual([{ method: "POST", path: `${LIST_PATH}/${MIREILLE.id}/disable`, search: "" }]);
    const postIndex = calls.findIndex((call) => call.method === "POST");
    const laterLists = calls.slice(postIndex + 1).filter((call) => call.method === "GET" && call.path === LIST_PATH);
    expect(laterLists.length).toBeGreaterThan(0);
  });

  it("after confirming the confirm closes and the row renders as disabled — DoD-11 (US-009.AC-1)", async () => {
    const user = newUser();
    await renderLoaded();

    const dialog = await openDisableConfirm(user, "mireille");
    await user.click(within(dialog).getByRole("button", { name: DISABLE_ITEM }));
    await flush();

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(rowText("mireille")).toMatch(DISABLED_STATUS);
    expect(rowText("mireille")).not.toMatch(ENABLED_STATUS);
    expect(rowText("anselm")).toMatch(ENABLED_STATUS);
  });

  it("the rendered state comes from the re-load — a change only the server knows appears — DoD-11", async () => {
    const user = newUser();
    const { rows } = await renderLoaded();
    rows.push({ ...ANSELM, id: "7340032000000199", username: "newcomer", role: "roleplayer" });
    expect(bodyRows()).toHaveLength(3);

    const dialog = await openDisableConfirm(user, "mireille");
    await user.click(within(dialog).getByRole("button", { name: DISABLE_ITEM }));
    await flush();

    expect(bodyRows()).toHaveLength(4);
    expect(rowText("newcomer")).toMatch(ENABLED_STATUS);
    expect(rowText("mireille")).toMatch(DISABLED_STATUS);
  });

  it("nothing is written before the server answers — the row stays enabled while the post is in flight — DoD-11", async () => {
    const user = newUser();
    const pending = deferred<Response>();
    await renderLoaded(EVERYONE, (method) => (method === "POST" ? pending.promise : undefined));

    const dialog = await openDisableConfirm(user, "mireille");
    await user.click(within(dialog).getByRole("button", { name: DISABLE_ITEM }));
    await flush();
    expect(rowText("mireille")).toMatch(ENABLED_STATUS);
    expect(rowText("mireille")).not.toMatch(DISABLED_STATUS);

    pending.resolve(jsonResponse({ ...MIREILLE, is_enabled: false }, 200));
    await flush();
  });

  it("the consequence contains no number and no count of anything — DoD-12 (R5)", async () => {
    const user = newUser();
    await renderLoaded();
    for (const name of ["mireille", "anselm"]) {
      const dialog = await openDisableConfirm(user, name);
      const text = dialog.textContent ?? "";
      expect(text, name).not.toMatch(/\d/);
      expect(text, name).not.toMatch(NUMBER_WORDS);
      expect(text, name).not.toMatch(OTHER_USERS_DATA);
      await user.click(within(dialog).getByRole("button", { name: CANCEL_NAME }));
      await waitFor(() => {
        expect(screen.queryByRole("dialog")).toBeNull();
      });
    }
  });

  it("the consequence describes the action: signed out now, no sign-in until re-enabled — DoD-12", async () => {
    const user = newUser();
    await renderLoaded();
    const dialog = await openDisableConfirm(user, "mireille");
    const text = dialog.textContent ?? "";
    expect(text).toMatch(/sign(ed|s)?[\s-]*out|log(ged|s)?[\s-]*out/i);
    expect(text).toMatch(/re-?\s?enabl/i);
  });
});

// ---------------------------------------------------------------------------
describe("re-enable is not confirmed", () => {
  it("posts to that account's enable route with no confirm step, then re-loads the list — DoD-13 (UC-007)", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();

    await chooseMenuItem(user, await openRowMenu(user, "zora"), REENABLE_ITEM);
    expect(screen.queryByRole("dialog")).toBeNull();
    await flush();
    expect(screen.queryByRole("dialog")).toBeNull();

    const calls = seen(mock);
    const posts = calls.filter((call) => call.method === "POST");
    expect(posts).toEqual([{ method: "POST", path: `${LIST_PATH}/${ZORA.id}/enable`, search: "" }]);
    const postIndex = calls.findIndex((call) => call.method === "POST");
    const laterLists = calls.slice(postIndex + 1).filter((call) => call.method === "GET" && call.path === LIST_PATH);
    expect(laterLists.length).toBeGreaterThan(0);
  });

  it("after the re-load the row renders as enabled — DoD-13 (UC-007)", async () => {
    const user = newUser();
    await renderLoaded();
    await chooseMenuItem(user, await openRowMenu(user, "zora"), REENABLE_ITEM);
    await flush();
    expect(rowText("zora")).toMatch(ENABLED_STATUS);
    expect(rowText("zora")).not.toMatch(DISABLED_STATUS);
  });
});

// ---------------------------------------------------------------------------
describe("no notification from any path", () => {
  it("loading, disabling and re-enabling successfully raise no notification — DoD-14", async () => {
    const user = newUser();
    await renderLoaded();
    expect(notificationRoots()).toEqual([]);

    const dialog = await openDisableConfirm(user, "mireille");
    await user.click(within(dialog).getByRole("button", { name: DISABLE_ITEM }));
    await flush();
    expect(notificationRoots()).toEqual([]);

    await chooseMenuItem(user, await openRowMenu(user, "zora"), REENABLE_ITEM);
    await flush();
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("failing paths raise no notification either — DoD-14", async () => {
    const user = newUser();
    await renderLoaded(EVERYONE, (method) => (method === "POST" ? Promise.resolve(failureResponse()) : undefined));
    const dialog = await openDisableConfirm(user, "mireille");
    await user.click(within(dialog).getByRole("button", { name: DISABLE_ITEM }));
    await flush();
    await chooseMenuItem(user, await openRowMenu(user, "zora"), REENABLE_ITEM);
    await flush();
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("no module of this page imports notifyFailure or Mantine's notifications — DoD-14", () => {
    const offenders = PAGE_MODULES.flatMap((file) =>
      importSpecifiers(readFileSync(file, "utf8"))
        .filter((spec) => /notifyFailure|@mantine\/notifications/.test(spec))
        .map((spec) => `${path.basename(file)} imports ${spec}`),
    );
    expect(offenders).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("unmounting", () => {
  it("aborts the in-flight load — DoD-15", async () => {
    const pending = deferred<Response>();
    const mock = stubFetch(() => pending.promise);
    const view = renderPage();
    await flush();

    expect(mock).toHaveBeenCalledTimes(1);
    const signal = mock.mock.calls[0][1]?.signal;
    expect(signal).toBeTruthy();
    expect(signal?.aborted).toBe(false);

    view.unmount();
    expect(signal?.aborted).toBe(true);
    pending.resolve(jsonResponse({ users: copyRows(EVERYONE) }, 200));
    await flush();
  });

  it("no store write happens after the unmount — DoD-15", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const view = renderPage();
    await flush();
    const store = pageStore();
    const atUnmount = { rows: [...store.rows], status: store.status, errorMessage: store.errorMessage };

    view.unmount();
    pending.resolve(jsonResponse({ users: copyRows(EVERYONE) }, 200));
    await flush();

    expect({ rows: [...store.rows], status: store.status, errorMessage: store.errorMessage }).toEqual(atUnmount);
    expect(store.rows).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("the page drives a data store through free functions", () => {
  it("the load is the free function, given the page's store and an abort signal — DoD-16", async () => {
    await renderLoaded();
    expect(spied.load.length).toBeGreaterThan(0);
    const [store, signal] = spied.load[0];
    expect(store).toBeInstanceOf(UsersPageState);
    expect(signal).toBeTruthy();
    expect(typeof (signal as AbortSignal).aborted).toBe("boolean");
    expect((store as UsersPageState).rows.map((row) => row.username)).toEqual(["mireille", "zora", "anselm"]);
  });

  it("disable and re-enable are the free functions, given the same store and a string id — DoD-16, DoD-17", async () => {
    const user = newUser();
    await renderLoaded();
    const store = pageStore();

    const dialog = await openDisableConfirm(user, "mireille");
    await user.click(within(dialog).getByRole("button", { name: DISABLE_ITEM }));
    await flush();
    expect(spied.disable).toHaveLength(1);
    expect(spied.disable[0][0]).toBe(store);
    expect(spied.disable[0][1]).toBe(MIREILLE.id);

    await chooseMenuItem(user, await openRowMenu(user, "zora"), REENABLE_ITEM);
    await flush();
    expect(spied.enable).toHaveLength(1);
    expect(spied.enable[0][0]).toBe(store);
    expect(spied.enable[0][1]).toBe(ZORA.id);
  });

  it("the confirm's open flag and target row are not fields of the store — DoD-16", async () => {
    const user = newUser();
    await renderLoaded();
    const store = pageStore();
    const fieldsBefore = Object.getOwnPropertyNames(store).sort();
    const observedBefore = fieldsBefore.filter((name) => isObservableProp(store, name));
    expect(observedBefore).toEqual(["errorMessage", "rows", "status"]);
    const rowsBefore = JSON.stringify(store.rows);

    await openDisableConfirm(user, "mireille");
    expect(Object.getOwnPropertyNames(store).sort()).toEqual(fieldsBefore);
    expect(JSON.stringify(store.rows)).toBe(rowsBefore);
    expect(store.errorMessage).toBeNull();
    expect(store.status).toBe("ready");
  });
});

// ---------------------------------------------------------------------------
describe("ids are strings", () => {
  it("an id beyond MAX_SAFE_INTEGER round-trips through a disable and back into the re-loaded row — DoD-17", async () => {
    const user = newUser();
    const big = { ...MIREILLE, id: BIG_ID };
    const { mock } = await renderLoaded([big, ZORA]);

    const dialog = await openDisableConfirm(user, "mireille");
    await user.click(within(dialog).getByRole("button", { name: DISABLE_ITEM }));
    await flush();

    const posts = seen(mock).filter((call) => call.method === "POST");
    expect(posts).toEqual([{ method: "POST", path: `${LIST_PATH}/${BIG_ID}/disable`, search: "" }]);
    expect(rowText("mireille")).toMatch(DISABLED_STATUS);

    const store = pageStore();
    const row = store.rows.find((candidate) => candidate.username === "mireille");
    expect(row?.id).toBe(BIG_ID);
    expect(typeof row?.id).toBe("string");
  });

  it("the page's modules use no parseInt and type no id as a number — DoD-17", () => {
    for (const file of PAGE_MODULES) {
      const source = stripComments(readFileSync(file, "utf8"));
      expect(source, path.basename(file)).not.toMatch(/\bparseInt\b/);
      expect(source, path.basename(file)).not.toMatch(/\b\w*(?:id|Id)\s*\??\s*:\s*number\b/);
    }
  });
});
