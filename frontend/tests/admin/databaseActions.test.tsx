// Feature 007, step 006 — the per-row Create and Sync actions on the Database page, and the
// shared confirm a lossy Sync earns (DoD-1..DoD-16). DoD-17 and DoD-18 are [manual/live].
//
// Expected behaviour comes from the step's Interface intent and DoD, 006.context.md and
// context.md (D4 the two operations' postconditions, D5 what a rebuild preserves, D7 the lossy
// confirm and the deliberate non-confirm on Create, D9 the apply routes, D13 MobX rules, R5,
// never-optimistic, failures render in place, no success toast). Bindings come from the frozen
// `### Step 006` record (plus step 005's and 004's): `applyingTable`, `createDriftTable`,
// `syncDriftTable`, `isLossySync`, `syncConsequenceOf`, and the two apply routes
// `POST /api/admin/database/tables/{table_name}/create|sync` — no body, answering one TableReport.
// The page takes the store as a prop, so tests construct `new DatabasePageState()` and render
// `<DatabasePage state={...} />` under `AppProviders` + `MemoryRouter`. `fetch` is stubbed per
// test with a tiny in-memory backend that honours D4's postconditions. `notifyFailure` is mocked
// at file level. The store module is wrapped pass-through so the page's calls to its free
// functions are observable — behaviour unchanged.
//
// Recognition conventions (from spec wording, for the verifier):
// - Table: the `<table>`; rows `tbody tr`; a row is found by the cell whose text is exactly its
//   table name. Status badge: `.mantine-Badge-root` in the row; its words are the status words
//   step 005 fixed (in sync / missing / drifted).
// - The row trigger: the one icon-only control (a button with no text) in the row. Its accessible
//   name is not frozen, so nothing here depends on it.
// - Menu items are looked up inside the dropdown owned by the trigger just clicked: Create
//   /\bcreate\b/i and Sync /\bsync\b/i. The confirm: `role="dialog"`, confirm button named
//   exactly "Sync", cancel /cancel/i.
// - Inline error: Mantine `Alert`, `role="alert"`. Notifications: `.mantine-Notification-root`.
// - Every fixture name is digit-free, so any digit inside the confirm is a count (DoD-8).
import { readFileSync } from "node:fs";
import path from "node:path";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { autorun, configure, isComputedProp, isObservableProp, runInAction, toJS } from "mobx";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DatabasePage } from "../../src/admin/DatabasePage";
import {
  createDriftTable,
  DatabasePageState,
  type DriftTableRow,
  isLossySync,
  syncConsequenceOf,
  syncDriftTable,
} from "../../src/admin/databasePageState";
import { AppProviders } from "../../src/shared/AppProviders";

const { notifyFailureSpy, spied } = vi.hoisted(() => ({
  notifyFailureSpy: vi.fn(),
  spied: {
    load: [] as unknown[][],
    create: [] as unknown[][],
    sync: [] as unknown[][],
    lossy: [] as unknown[][],
    consequence: [] as unknown[][],
  },
}));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));
vi.mock("../../src/admin/databasePageState", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../src/admin/databasePageState")>();
  return {
    ...actual,
    loadDriftReport: (...args: Parameters<typeof actual.loadDriftReport>) => {
      spied.load.push(args);
      return actual.loadDriftReport(...args);
    },
    createDriftTable: (...args: Parameters<typeof actual.createDriftTable>) => {
      spied.create.push(args);
      return actual.createDriftTable(...args);
    },
    syncDriftTable: (...args: Parameters<typeof actual.syncDriftTable>) => {
      spied.sync.push(args);
      return actual.syncDriftTable(...args);
    },
    isLossySync: (...args: Parameters<typeof actual.isLossySync>) => {
      spied.lossy.push(args);
      return actual.isLossySync(...args);
    },
    syncConsequenceOf: (...args: Parameters<typeof actual.syncConsequenceOf>) => {
      spied.consequence.push(args);
      return actual.syncConsequenceOf(...args);
    },
  };
});

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type User = ReturnType<typeof userEvent.setup>;
type WireRow = Record<string, unknown>;

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const ADMIN_SRC = path.join(FRONTEND_ROOT, "src", "admin");
const STATE_SOURCE = path.join(ADMIN_SRC, "databasePageState.ts");
const PAGE_SOURCE = path.join(ADMIN_SRC, "DatabasePage.tsx");
const PAGE_MODULES = [STATE_SOURCE, PAGE_SOURCE];

/** context.md D9 / step 004's frozen routes. */
const REPORT_PATH = "/api/admin/database/tables";
const APPLY_PATH = /^\/api\/admin\/database\/tables\/([^/]+)\/(create|sync)$/;
const applyPath = (name: string, operation: "create" | "sync") => `${REPORT_PATH}/${name}/${operation}`;

const APPLY_FAILURE = "The rebuild of that table could not complete (qz marker).";

const CREATE_ITEM = /\bcreate\b/i;
const SYNC_ITEM = /\bsync\b/i;
const CONFIRM_SYNC = /^\s*sync\s*$/i;
const CANCEL_NAME = /cancel/i;
/**
 * S030_005_DoD1/DoD-7 — narrowed: feature 030 ships the page-level **Export** action, so
 * `export` is no longer out of scope for a page-wide control sweep. `rebuild` / `re-index`
 * (`fast/002`) and `import` (031) have **not** shipped and this guard still protects them —
 * never widen it to permit either.
 */
const OUT_OF_SCOPE_ITEM = /rebuild|import|re-?index/i;
/**
 * S030_005_DoD1 — the row-menu clause keeps the full regex: 030 puts Export in the page
 * header, never in a per-row dropdown, so no Export item may appear there.
 */
const OUT_OF_SCOPE_ROW_ITEM = /rebuild|export|import|re-?index/i;
const NOTIFICATION_ROOT = ".mantine-Notification-root";
const BADGE = ".mantine-Badge-root";
const IN_SYNC_WORD = /^in[\s_-]*sync$/i;
const MISSING_WORD = /^missing$/i;
const DRIFTED_WORD = /^drifted$/i;
/** R5 — a digit-bearing claim about user-owned material. */
const COUNT_CLAIM =
  /\d[\d,.\s]*\s*(rows?|records?|sessions?|characters?|setups?|messages?|memos?|users?|entries)\b/i;
const NUMBER_WORDS = /\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|dozens?|hundreds?|thousands?|several|many)\b/i;
/** D5 — the survivors' data is kept. */
const PRESERVED = /preserv|\bkept\b|\bkeep|retain|intact|unchanged|unaffected|surviv|remain/i;
const OTHER_COLUMNS = /\bother\b|\bremaining\b|\bsurviving\b|\brest\b|\bevery\b|\ball\b/i;
const DROPPED = /drop|remov|delet|\blos[te]\b|\blose\b/i;

// ---------------------------------------------------------------- fixtures (no digit anywhere)

function inSync(name: string): DriftTableRow {
  return {
    table_name: name,
    status: "in_sync",
    missing_columns: [],
    extra_columns: [],
    changed_columns: [],
    missing_indexes: [],
    extra_indexes: [],
  };
}

const IN_SYNC_ROW: DriftTableRow = inSync("users");

const MISSING_ROW: DriftTableRow = {
  table_name: "models",
  status: "missing",
  missing_columns: [],
  extra_columns: [],
  changed_columns: [],
  missing_indexes: [],
  extra_indexes: [],
};

/** Drifted, but no extra column — a Sync that loses nothing (D7). */
const SAFE_DRIFTED_ROW: DriftTableRow = {
  table_name: "llm_servers",
  status: "drifted",
  missing_columns: ["nickname"],
  extra_columns: [],
  changed_columns: [
    {
      name: "base_url",
      expected: { name: "base_url", type_text: "TEXT", not_null: true },
      actual: { name: "base_url", type_text: "BLOB", not_null: true },
    },
  ],
  missing_indexes: [{ columns: ["kind"], unique: false }],
  extra_indexes: [],
};

/** Drifted with two extra columns — a Sync that drops them (D7). */
const LOSSY_DRIFTED_ROW: DriftTableRow = {
  table_name: "auth_sessions",
  status: "drifted",
  missing_columns: ["revoked_at"],
  extra_columns: ["legacy_flag", "scratch_notes"],
  changed_columns: [],
  missing_indexes: [],
  extra_indexes: [{ columns: ["legacy_flag"], unique: false }],
};

const REPORT: DriftTableRow[] = [IN_SYNC_ROW, MISSING_ROW, SAFE_DRIFTED_ROW, LOSSY_DRIFTED_ROW];

beforeEach(() => {
  notifyFailureSpy.mockClear();
  spied.load.length = 0;
  spied.create.length = 0;
  spied.sync.length = 0;
  spied.lossy.length = 0;
  spied.consequence.length = 0;
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

function errorResponse(code: string, message: string, status: number, detail: Record<string, unknown> = {}): Response {
  return jsonResponse({ error: { code, message, detail } }, status);
}

function applyFailedResponse(name: string, operation: "create" | "sync"): Response {
  return errorResponse("schema_apply_failed", APPLY_FAILURE, 500, { table_name: name, operation });
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

type Seen = { method: string; path: string; search: string };
type FetchMock = ReturnType<typeof stubFetch>;

function seen(mock: FetchMock): Seen[] {
  return mock.mock.calls.map(([input, init]) => {
    const url = requestUrl(input);
    return { method: requestMethod(input, init), path: url.pathname, search: url.search };
  });
}

function mutations(mock: FetchMock): Seen[] {
  return seen(mock).filter((call) => call.method !== "GET");
}

function postInits(mock: FetchMock): (RequestInit | undefined)[] {
  return mock.mock.calls.filter(([input, init]) => requestMethod(input, init) === "POST").map(([, init]) => init);
}

function laterReportLoads(calls: Seen[], afterMethod: string): Seen[] {
  const index = calls.findIndex((call) => call.method === afterMethod);
  expect(index, `a ${afterMethod} request`).toBeGreaterThanOrEqual(0);
  return calls.slice(index + 1).filter((call) => call.method === "GET" && call.path === REPORT_PATH);
}

function copyRows<T>(rows: readonly T[]): T[] {
  return JSON.parse(JSON.stringify(rows)) as T[];
}

type Override = (method: string, pathname: string, rows: WireRow[]) => Promise<Response> | undefined;

/**
 * A tiny in-memory backend honouring D4: GET answers the current report; POST .../create turns a
 * missing table in sync and leaves any other state alone; POST .../sync turns any table in sync.
 * Both answer the re-derived row. An unknown table answers 404 unknown_table.
 */
function serveDatabase(initial: readonly WireRow[] = REPORT as unknown as WireRow[], override?: Override) {
  const rows = copyRows(initial);
  const mock = stubFetch((input, init) => {
    const method = requestMethod(input, init);
    const pathname = requestUrl(input).pathname;
    const custom = override?.(method, pathname, rows);
    if (custom !== undefined) return custom;
    if (method === "GET" && pathname === REPORT_PATH) {
      return Promise.resolve(jsonResponse({ tables: copyRows(rows) }, 200));
    }
    const match = APPLY_PATH.exec(pathname);
    if (method === "POST" && match !== null) {
      const name = decodeURIComponent(match[1]);
      const index = rows.findIndex((row) => row.table_name === name);
      if (index < 0) {
        return Promise.resolve(errorResponse("unknown_table", "No such table.", 404, { table_name: name }));
      }
      if (match[2] === "sync" || rows[index].status === "missing") {
        rows[index] = inSync(name) as unknown as WireRow;
      }
      return Promise.resolve(jsonResponse(copyRows([rows[index]])[0], 200));
    }
    return Promise.resolve(errorResponse("not_found", "no such route", 404));
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

async function settle(rounds = 4): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await new Promise<void>((resolve) => setImmediate(resolve));
  }
}

// ---------------------------------------------------------------- store helpers

/** Every own field of the store, deep-copied. */
function snapshot(state: DatabasePageState): Record<string, unknown> {
  const record = state as unknown as Record<string, unknown>;
  return Object.fromEntries(Object.getOwnPropertyNames(state).map((name) => [name, toJS(record[name])]));
}

function readyWith(rows: readonly DriftTableRow[]): DatabasePageState {
  const state = new DatabasePageState();
  runInAction(() => {
    state.rows = copyRows(rows);
    state.status = "ready";
  });
  return state;
}

// ---------------------------------------------------------------- render + queries

function renderPage(state: DatabasePageState = new DatabasePageState()) {
  const view = render(
    <AppProviders>
      <MemoryRouter initialEntries={["/database"]}>
        <DatabasePage state={state} />
      </MemoryRouter>
    </AppProviders>,
  );
  return { view, state };
}

async function renderLoaded(rows: readonly WireRow[] = REPORT as unknown as WireRow[], override?: Override) {
  const server = serveDatabase(rows, override);
  const rendered = renderPage();
  await flush();
  return { ...server, ...rendered };
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

function cellsOf(tr: HTMLTableRowElement): HTMLTableCellElement[] {
  return Array.from(tr.querySelectorAll<HTMLTableCellElement>("td"));
}

function rowFor(name: string): HTMLTableRowElement {
  const matches = bodyRows().filter((tr) => cellsOf(tr).some((td) => (td.textContent ?? "").trim() === name));
  expect(matches, `rows showing ${name}`).toHaveLength(1);
  return matches[0];
}

function badgeText(name: string): string {
  const badges = Array.from(rowFor(name).querySelectorAll<HTMLElement>(BADGE));
  expect(badges, `status badges in ${name}'s row`).toHaveLength(1);
  return (badges[0].textContent ?? "").trim();
}

function squash(text: string): string {
  return text.replace(/\s+/g, "");
}

function iconOnlyControls(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      "button, a[href], [role='button'], input[type='button'], input[type='image'], input[type='submit']",
    ),
  ).filter((el) => (el.textContent ?? "").trim() === "");
}

function anyControls(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      "button, a[href], [role='button'], [role='menuitem'], [aria-haspopup], input, select, textarea",
    ),
  );
}

function menuTrigger(name: string): HTMLElement {
  const controls = iconOnlyControls(rowFor(name));
  expect(controls, `icon-only controls in ${name}'s row`).toHaveLength(1);
  return controls[0];
}

function wiredTarget(name: string): HTMLElement {
  const row = rowFor(name);
  const trigger = menuTrigger(name);
  const wired = trigger.closest<HTMLElement>("[aria-controls], [aria-haspopup]");
  if (wired !== null && row.contains(wired)) return wired;
  const withId = trigger.closest<HTMLElement>("[id]");
  if (withId !== null && row.contains(withId)) return withId;
  throw new Error(`no menu-target wiring at or above ${name}'s trigger within the row`);
}

function dropdownFor(name: string): HTMLElement {
  const wired = wiredTarget(name);
  const controls = wired.getAttribute("aria-controls");
  if (controls) {
    const byId = document.getElementById(controls);
    if (byId !== null) return byId;
  }
  if (wired.id) {
    const labelled = Array.from(document.querySelectorAll<HTMLElement>("[aria-labelledby]")).filter((menu) =>
      (menu.getAttribute("aria-labelledby") ?? "").split(/\s+/).includes(wired.id),
    );
    if (labelled.length === 1) return labelled[0];
  }
  throw new Error(`the dropdown owned by ${name}'s trigger is not mounted yet`);
}

async function openRowMenu(user: User, name: string): Promise<HTMLElement> {
  await user.click(menuTrigger(name));
  return waitFor(() => dropdownFor(name));
}

async function chooseMenuItem(user: User, menu: HTMLElement, itemName: RegExp): Promise<void> {
  const item = await within(menu).findByRole("menuitem", { name: itemName });
  await user.click(item);
}

async function menuItemsOf(user: User, name: string): Promise<HTMLElement[]> {
  const menu = await openRowMenu(user, name);
  await waitFor(() => {
    expect(within(menu).queryAllByRole("menuitem").length).toBeGreaterThan(0);
  });
  return within(menu).getAllByRole("menuitem");
}

async function chooseCreate(user: User, name: string): Promise<void> {
  await chooseMenuItem(user, await openRowMenu(user, name), CREATE_ITEM);
  await flush();
}

async function chooseSync(user: User, name: string): Promise<void> {
  await chooseMenuItem(user, await openRowMenu(user, name), SYNC_ITEM);
  await flush();
}

async function openSyncConfirm(user: User, name: string): Promise<HTMLElement> {
  await chooseMenuItem(user, await openRowMenu(user, name), SYNC_ITEM);
  return screen.findByRole("dialog");
}

async function cancelDialog(user: User, dialog: HTMLElement): Promise<void> {
  await user.click(within(dialog).getByRole("button", { name: CANCEL_NAME }));
  await waitFor(() => {
    expect(screen.queryByRole("dialog")).toBeNull();
  });
}

async function confirmDialog(user: User, dialog: HTMLElement): Promise<void> {
  await user.click(within(dialog).getByRole("button", { name: CONFIRM_SYNC }));
  await flush();
}

function isDisabled(el: HTMLElement): boolean {
  return el.hasAttribute("disabled") || el.hasAttribute("data-disabled") || el.getAttribute("aria-disabled") === "true";
}

/** Includes elements an open modal may mark aria-hidden: the Alert lives on the page behind it. */
function alerts(): HTMLElement[] {
  return screen.queryAllByRole("alert", { hidden: true });
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

const NAMING_ATTRIBUTES = ["aria-label", "title", "aria-description", "placeholder", "alt", "aria-valuetext"];

function attributeTexts(): string[] {
  return Array.from(document.body.querySelectorAll("*")).flatMap((el) =>
    NAMING_ATTRIBUTES.map((name) => el.getAttribute(name) ?? "").filter(Boolean),
  );
}

function textNodes(): string[] {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const out: string[] = [];
  for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
    const text = (node.textContent ?? "").trim();
    if (text) out.push(text);
  }
  return out;
}

/** Everything a person reads, as separate pieces so neighbouring cells never glue together. */
function readablePieces(): string[] {
  const blocks = Array.from(
    document.body.querySelectorAll("td, th, h1, h2, h3, h4, p, [role='alert'], [role='dialog'], [role='menuitem']"),
  ).map((el) => (el.textContent ?? "").trim());
  return [...blocks, ...textNodes(), ...attributeTexts()];
}

function readableText(): string {
  return [document.body.textContent ?? "", ...attributeTexts()].join("\n");
}

/** Inline style text of an element and everything inside it (Mantine carries colour as CSS variables). */
function styleOf(el: HTMLElement): string {
  return [el, ...Array.from(el.querySelectorAll("*"))].map((node) => node.getAttribute("style") ?? "").join(";");
}

// ---------------------------------------------------------------- source scans

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

function readSource(file: string): string {
  return stripComments(readFileSync(file, "utf8"));
}

function importSpecifiers(source: string): string[] {
  const pattern = /(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)["']([^"']+)["']/g;
  return Array.from(stripComments(source).matchAll(pattern), (m) => m[1]);
}

// ===========================================================================
describe("the menu offers only the action the row's status allows", () => {
  it("a missing row's menu offers Create and not Sync — DoD-1 (UC-015, D4)", async () => {
    const user = newUser();
    await renderLoaded();
    const items = await menuItemsOf(user, MISSING_ROW.table_name);
    expect(items.some((item) => CREATE_ITEM.test(item.textContent ?? ""))).toBe(true);
    expect(items.filter((item) => SYNC_ITEM.test(item.textContent ?? ""))).toEqual([]);
  });

  it.each([SAFE_DRIFTED_ROW, LOSSY_DRIFTED_ROW])(
    "a drifted row ($table_name) offers Sync and not Create — DoD-1 (UC-015, D4)",
    async (row) => {
      const user = newUser();
      await renderLoaded();
      const items = await menuItemsOf(user, row.table_name);
      expect(items.some((item) => SYNC_ITEM.test(item.textContent ?? ""))).toBe(true);
      expect(items.filter((item) => CREATE_ITEM.test(item.textContent ?? ""))).toEqual([]);
    },
  );

  it("an in-sync row renders no action trigger at all — an empty cell — DoD-1 (D4)", async () => {
    await renderLoaded();
    const row = rowFor(IN_SYNC_ROW.table_name);
    expect(iconOnlyControls(row)).toEqual([]);
    expect(anyControls(row)).toEqual([]);
    const cells = cellsOf(row);
    expect((cells[cells.length - 1].textContent ?? "").trim()).toBe("");
  });

  it.each([MISSING_ROW, SAFE_DRIFTED_ROW, LOSSY_DRIFTED_ROW])(
    "the unavailable action is absent, not disabled: every item offered on $table_name is enabled — DoD-1",
    async (row) => {
      const user = newUser();
      await renderLoaded();
      const items = await menuItemsOf(user, row.table_name);
      for (const item of items) expect(isDisabled(item), item.textContent ?? "").toBe(false);
      const menu = dropdownFor(row.table_name);
      const absent = row.status === "missing" ? SYNC_ITEM : CREATE_ITEM;
      expect(menu.textContent ?? "").not.toMatch(absent);
    },
  );
});

// ===========================================================================
describe("Create is not confirmed", () => {
  it("choosing Create posts to that row's create route with no dialog, exactly one request — DoD-2 (US-018.AC-1, D7)", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();

    await chooseCreate(user, MISSING_ROW.table_name);

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(mutations(mock)).toEqual([
      { method: "POST", path: applyPath(MISSING_ROW.table_name, "create"), search: "" },
    ]);
    expect(spied.create).toHaveLength(1);
    expect(spied.create[0][0]).toBe(state);
    expect(spied.create[0][1]).toBe(MISSING_ROW.table_name);
    expect(spied.sync).toEqual([]);
  });

  it("the create request carries no body — DoD-2 (D9)", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    await chooseCreate(user, MISSING_ROW.table_name);
    const inits = postInits(mock);
    expect(inits).toHaveLength(1);
    const body = inits[0]?.body;
    expect(body === undefined || body === null || body === "").toBe(true);
  });

  it("no dialog appears at any point between choosing Create and the re-load — DoD-2 (D7)", async () => {
    const user = newUser();
    const pending = deferred<Response>();
    await renderLoaded(REPORT as unknown as WireRow[], (method) => (method === "POST" ? pending.promise : undefined));
    await chooseCreate(user, MISSING_ROW.table_name);
    expect(screen.queryByRole("dialog")).toBeNull();
    pending.resolve(jsonResponse(inSync(MISSING_ROW.table_name), 200));
    await flush();
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

// ===========================================================================
describe("a successful Create re-loads the whole report", () => {
  it("after Create the report is re-fetched and the row renders in sync — DoD-3 (US-018.AC-2)", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    expect(badgeText(MISSING_ROW.table_name)).toMatch(MISSING_WORD);

    await chooseCreate(user, MISSING_ROW.table_name);

    expect(laterReportLoads(seen(mock), "POST").length).toBeGreaterThan(0);
    expect(badgeText(MISSING_ROW.table_name)).toMatch(IN_SYNC_WORD);
  });

  it("the rows come from the re-loaded report, not from the apply's answer — DoD-3 (never optimistic)", async () => {
    const user = newUser();
    // The apply answers "in sync" but the server's report still says missing: the page shows the report.
    const { state } = await renderLoaded(REPORT as unknown as WireRow[], (method, pathname) =>
      method === "POST" && APPLY_PATH.test(pathname)
        ? Promise.resolve(jsonResponse(inSync(MISSING_ROW.table_name), 200))
        : undefined,
    );

    await chooseCreate(user, MISSING_ROW.table_name);

    expect(badgeText(MISSING_ROW.table_name)).toMatch(MISSING_WORD);
    expect(state.rows.find((row) => row.table_name === MISSING_ROW.table_name)?.status).toBe("missing");
  });

  it("the whole report is re-loaded: another table's change arriving with it is shown too — DoD-3 (US-018.AC-2)", async () => {
    const user = newUser();
    const { state } = await renderLoaded(REPORT as unknown as WireRow[], (method, pathname, rows) => {
      if (method === "POST" && APPLY_PATH.test(pathname)) {
        const users = rows.findIndex((row) => row.table_name === IN_SYNC_ROW.table_name);
        rows[users] = { ...SAFE_DRIFTED_ROW, table_name: IN_SYNC_ROW.table_name };
      }
      return undefined;
    });

    await chooseCreate(user, MISSING_ROW.table_name);

    expect(badgeText(MISSING_ROW.table_name)).toMatch(IN_SYNC_WORD);
    expect(badgeText(IN_SYNC_ROW.table_name)).toMatch(DRIFTED_WORD);
    expect(state.rows.map((row) => row.table_name)).toEqual(REPORT.map((row) => row.table_name));
  });

  it("the effect writes no row before the re-load answers — DoD-3 (never optimistic)", async () => {
    const reload = deferred<Response>();
    const { mock } = serveDatabase(REPORT as unknown as WireRow[], (method) =>
      method === "GET" ? reload.promise : undefined,
    );
    const state = readyWith(REPORT);

    const running = createDriftTable(state, MISSING_ROW.table_name);
    await settle();
    expect(mutations(mock)).toEqual([{ method: "POST", path: applyPath(MISSING_ROW.table_name, "create"), search: "" }]);
    expect(toJS(state.rows)).toEqual(REPORT);

    const after = REPORT.map((row) => (row.table_name === MISSING_ROW.table_name ? inSync(row.table_name) : row));
    reload.resolve(jsonResponse({ tables: after }, 200));
    await expect(running).resolves.toBeUndefined();
    expect(toJS(state.rows)).toEqual(after);
    expect(state.applyingTable).toBeNull();
    expect(state.errorMessage).toBeNull();
  });
});

// ===========================================================================
describe("a Sync that drops nothing is not confirmed", () => {
  it("choosing Sync on a drifted row with no extra column posts its sync route directly — DoD-4 (US-018.AC-1, D7)", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();

    await chooseSync(user, SAFE_DRIFTED_ROW.table_name);

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(mutations(mock)).toEqual([
      { method: "POST", path: applyPath(SAFE_DRIFTED_ROW.table_name, "sync"), search: "" },
    ]);
    expect(spied.sync).toHaveLength(1);
    expect(spied.sync[0][0]).toBe(state);
    expect(spied.sync[0][1]).toBe(SAFE_DRIFTED_ROW.table_name);
  });

  it("the direct Sync carries no body, re-loads the report and the row turns in sync — DoD-4 (US-018.AC-2)", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    await chooseSync(user, SAFE_DRIFTED_ROW.table_name);
    const inits = postInits(mock);
    expect(inits).toHaveLength(1);
    const body = inits[0]?.body;
    expect(body === undefined || body === null || body === "").toBe(true);
    expect(laterReportLoads(seen(mock), "POST").length).toBeGreaterThan(0);
    expect(badgeText(SAFE_DRIFTED_ROW.table_name)).toMatch(IN_SYNC_WORD);
  });

  it("the predicate calls a Sync with no extra column not lossy — whatever else differs — DoD-4 (D7)", () => {
    expect(isLossySync(SAFE_DRIFTED_ROW)).toBe(false);
    expect(isLossySync(MISSING_ROW)).toBe(false);
    expect(isLossySync(IN_SYNC_ROW)).toBe(false);
    expect(isLossySync({ extra_columns: [] })).toBe(false);
  });
});

// ===========================================================================
describe("a lossy Sync opens the shared confirm", () => {
  it("choosing Sync on a row with an extra column opens the confirm and issues no request — DoD-5 (D7)", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    const before = seen(mock);

    const dialog = await openSyncConfirm(user, LOSSY_DRIFTED_ROW.table_name);
    await flush();

    expect(dialog).toBeInTheDocument();
    expect(seen(mock)).toEqual(before);
    expect(mutations(mock)).toEqual([]);
    expect(spied.sync).toEqual([]);
  });

  it("the confirm names the table and every column that will be dropped — DoD-5 (D7)", async () => {
    const user = newUser();
    await renderLoaded();
    const dialog = await openSyncConfirm(user, LOSSY_DRIFTED_ROW.table_name);
    const text = dialog.textContent ?? "";
    expect(text).toContain(LOSSY_DRIFTED_ROW.table_name);
    for (const column of LOSSY_DRIFTED_ROW.extra_columns) expect(text, column).toContain(column);
    expect(text).toMatch(DROPPED);
  });

  it("the confirm carries the consequence helper's sentence for that row — DoD-5 (D7)", async () => {
    const user = newUser();
    await renderLoaded();
    const dialog = await openSyncConfirm(user, LOSSY_DRIFTED_ROW.table_name);
    expect(squash(dialog.textContent ?? "")).toContain(squash(syncConsequenceOf(LOSSY_DRIFTED_ROW)));
  });

  it("the predicate is true for one extra column and for several — DoD-5 (D7)", () => {
    expect(isLossySync(LOSSY_DRIFTED_ROW)).toBe(true);
    expect(isLossySync({ extra_columns: ["legacy_flag"] })).toBe(true);
    expect(isLossySync({ extra_columns: ["legacy_flag", "scratch_notes", "old_label"] })).toBe(true);
  });

  it("a row with only an extra column and nothing else different still earns the confirm — DoD-5 (D7)", async () => {
    const user = newUser();
    const onlyExtra: DriftTableRow = { ...inSync("models"), status: "drifted", extra_columns: ["old_label"] };
    const { mock } = await renderLoaded([IN_SYNC_ROW, onlyExtra] as unknown as WireRow[]);
    const dialog = await openSyncConfirm(user, onlyExtra.table_name);
    expect(dialog.textContent ?? "").toContain("old_label");
    expect(mutations(mock)).toEqual([]);
  });

  it("the consequence helper names the table and each dropped column — DoD-5 (D7)", () => {
    const sentence = syncConsequenceOf(LOSSY_DRIFTED_ROW);
    expect(sentence).toContain(LOSSY_DRIFTED_ROW.table_name);
    for (const column of LOSSY_DRIFTED_ROW.extra_columns) expect(sentence, column).toContain(column);
    const other = syncConsequenceOf({ table_name: "memos", extra_columns: ["draft_body"] });
    expect(other).toContain("memos");
    expect(other).toContain("draft_body");
    expect(other).not.toContain("legacy_flag");
  });
});

// ===========================================================================
describe("cancelling or confirming the lossy Sync", () => {
  it("cancelling issues no request and leaves the row exactly as it was — DoD-6 (D7)", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    const callsBefore = seen(mock);
    const rowBefore = rowFor(LOSSY_DRIFTED_ROW.table_name).textContent;
    const storeBefore = toJS(state.rows);

    const dialog = await openSyncConfirm(user, LOSSY_DRIFTED_ROW.table_name);
    await cancelDialog(user, dialog);
    await flush();

    expect(seen(mock)).toEqual(callsBefore);
    expect(spied.sync).toEqual([]);
    expect(badgeText(LOSSY_DRIFTED_ROW.table_name)).toMatch(DRIFTED_WORD);
    expect(rowFor(LOSSY_DRIFTED_ROW.table_name).textContent).toBe(rowBefore);
    expect(toJS(state.rows)).toEqual(storeBefore);
  });

  it("confirming issues the sync for that row and then re-loads the whole report — DoD-6 (US-018.AC-1, US-018.AC-2)", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();

    const dialog = await openSyncConfirm(user, LOSSY_DRIFTED_ROW.table_name);
    await confirmDialog(user, dialog);

    const calls = seen(mock);
    expect(mutations(mock)).toEqual([
      { method: "POST", path: applyPath(LOSSY_DRIFTED_ROW.table_name, "sync"), search: "" },
    ]);
    expect(laterReportLoads(calls, "POST").length).toBeGreaterThan(0);
    expect(spied.sync).toHaveLength(1);
    expect(spied.sync[0][0]).toBe(state);
    expect(spied.sync[0][1]).toBe(LOSSY_DRIFTED_ROW.table_name);
  });

  it("after confirming, the row renders its corrected status — DoD-6 (US-018.AC-2)", async () => {
    const user = newUser();
    await renderLoaded();
    const dialog = await openSyncConfirm(user, LOSSY_DRIFTED_ROW.table_name);
    await confirmDialog(user, dialog);
    await waitFor(() => {
      expect(badgeText(LOSSY_DRIFTED_ROW.table_name)).toMatch(IN_SYNC_WORD);
    });
  });

  it("a cancelled confirm can be re-opened and then confirmed — DoD-6", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    await cancelDialog(user, await openSyncConfirm(user, LOSSY_DRIFTED_ROW.table_name));
    expect(mutations(mock)).toEqual([]);
    await confirmDialog(user, await openSyncConfirm(user, LOSSY_DRIFTED_ROW.table_name));
    expect(mutations(mock)).toEqual([
      { method: "POST", path: applyPath(LOSSY_DRIFTED_ROW.table_name, "sync"), search: "" },
    ]);
  });
});

// ===========================================================================
describe("the confirm is the shared ConfirmModal with component-local state", () => {
  it("the page reuses shared/ConfirmModal and hand-rolls no Modal — DoD-7", () => {
    const source = readSource(PAGE_SOURCE);
    const specs = importSpecifiers(readFileSync(PAGE_SOURCE, "utf8"));
    expect(specs.some((spec) => /(^|\/)shared\/ConfirmModal$/.test(spec))).toBe(true);
    expect(source).toMatch(/<ConfirmModal\b/);
    expect(source).not.toMatch(/<Modal\b/);
    expect(source).not.toMatch(/\bimport\s*\{[^}]*\bModal\b[^}]*\}\s*from\s*["']@mantine\/core["']/);
  });

  it("the store has no open flag and no confirm target — DoD-7 (D13)", () => {
    const names = Object.getOwnPropertyNames(new DatabasePageState());
    expect(names.filter((name) => /open|modal|confirm|target|dialog|lossy|pending/i.test(name))).toEqual([]);
  });

  it("opening and cancelling the confirm changes nothing in the store — DoD-7 (D13)", async () => {
    const user = newUser();
    const { state } = await renderLoaded();
    const before = { names: Object.getOwnPropertyNames(state).sort(), snap: snapshot(state) };

    const dialog = await openSyncConfirm(user, LOSSY_DRIFTED_ROW.table_name);
    expect({ names: Object.getOwnPropertyNames(state).sort(), snap: snapshot(state) }).toEqual(before);
    await cancelDialog(user, dialog);
    expect({ names: Object.getOwnPropertyNames(state).sort(), snap: snapshot(state) }).toEqual(before);
  });

  it("the confirm's button is labelled Sync, carries red, and sits right of Cancel — DoD-7 (D7)", async () => {
    const user = newUser();
    await renderLoaded();
    const dialog = await openSyncConfirm(user, LOSSY_DRIFTED_ROW.table_name);
    const confirm = within(dialog).getByRole("button", { name: CONFIRM_SYNC });
    const cancel = within(dialog).getByRole("button", { name: CANCEL_NAME });
    expect(styleOf(confirm)).toMatch(/\bred\b/);
    expect(isBefore(cancel, confirm)).toBe(true);
  });
});

// ===========================================================================
describe("R5 — the confirm and the page name no count", () => {
  const WITH_COUNTS: WireRow[] = REPORT.map((row, index) => ({
    ...row,
    row_count: [4817, 9253, 6031, 5127][index],
    rows_to_drop: [3319, 2281, 1193, 8844][index],
    sessions_using: 7719,
  }));

  it("the rendered confirm holds no digit, no number word and no count claim — DoD-8 (R5, UC-065, UC-066)", async () => {
    const user = newUser();
    await renderLoaded(WITH_COUNTS);
    const dialog = await openSyncConfirm(user, LOSSY_DRIFTED_ROW.table_name);
    const text = dialog.textContent ?? "";
    expect(text).not.toMatch(COUNT_CLAIM);
    // Every table and column name here is digit-free, so any digit is a count.
    expect(text).not.toMatch(/\d/);
    expect(text).not.toMatch(NUMBER_WORDS);
    expect(text).not.toMatch(/rows?\s+affected/i);
  });

  it("no other string on the page, menus and confirm included, is a count claim — DoD-8 (R5)", async () => {
    const user = newUser();
    await renderLoaded(WITH_COUNTS);
    const checkAll = () => {
      for (const piece of readablePieces()) expect(piece).not.toMatch(COUNT_CLAIM);
      const text = readableText();
      for (const value of ["4817", "9253", "6031", "5127", "3319", "2281", "1193", "8844", "7719"]) {
        expect(text, value).not.toContain(value);
      }
    };
    checkAll();
    await menuItemsOf(user, MISSING_ROW.table_name);
    checkAll();
    await openSyncConfirm(user, LOSSY_DRIFTED_ROW.table_name);
    checkAll();
  });

  it("the consequence helper names no count for any row — DoD-8 (R5)", () => {
    const rows = [
      LOSSY_DRIFTED_ROW,
      { table_name: "messages", extra_columns: ["old_body"] },
      { table_name: "characters", extra_columns: ["alias", "legacy_portrait", "notes_blob"] },
    ];
    for (const row of rows) {
      const sentence = syncConsequenceOf(row);
      expect(sentence, row.table_name).not.toMatch(COUNT_CLAIM);
      expect(sentence, row.table_name).not.toMatch(/\d/);
      expect(sentence, row.table_name).not.toMatch(NUMBER_WORDS);
    }
  });

  it("the consequence helper's sentence does not depend on any count a row might carry — DoD-8 (R5)", () => {
    const plain = syncConsequenceOf(LOSSY_DRIFTED_ROW);
    const loaded = { ...LOSSY_DRIFTED_ROW, row_count: 4817, sessions_using: 7719 } as DriftTableRow;
    expect(syncConsequenceOf(loaded)).toBe(plain);
  });
});

// ===========================================================================
describe("the confirm's sentence says what survives", () => {
  it("the helper states the data in every other column is preserved — DoD-9 (D5)", () => {
    const sentence = syncConsequenceOf(LOSSY_DRIFTED_ROW);
    expect(sentence).toMatch(PRESERVED);
    expect(sentence).toMatch(OTHER_COLUMNS);
  });

  it("the rendered confirm states the survivors' data is preserved — DoD-9 (D5)", async () => {
    const user = newUser();
    await renderLoaded();
    const dialog = await openSyncConfirm(user, LOSSY_DRIFTED_ROW.table_name);
    const text = dialog.textContent ?? "";
    expect(text).toMatch(PRESERVED);
    expect(text).toMatch(OTHER_COLUMNS);
  });

  it("the helper is one sentence naming only the dropped columns — DoD-9 (D5)", () => {
    const sentence = syncConsequenceOf(LOSSY_DRIFTED_ROW).trim();
    expect(sentence.length).toBeGreaterThan(0);
    // Columns the registry still declares are never named as dropped: the helper sees only the extras.
    for (const survivor of LOSSY_DRIFTED_ROW.missing_columns) expect(sentence).not.toContain(survivor);
  });
});

// ===========================================================================
describe("a failed apply renders inline", () => {
  it("a failed Create renders its message in the Alert above the table, no notification — DoD-10", async () => {
    const user = newUser();
    const { state } = await renderLoaded(REPORT as unknown as WireRow[], (method, pathname) =>
      method === "POST" && APPLY_PATH.test(pathname)
        ? Promise.resolve(applyFailedResponse(MISSING_ROW.table_name, "create"))
        : undefined,
    );

    await chooseCreate(user, MISSING_ROW.table_name);

    const alert = alertWith(APPLY_FAILURE);
    expect(isBefore(alert, table())).toBe(true);
    expect(state.applyingTable).toBeNull();
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("after a failed Create the table stays usable: the row's menu works again — DoD-10", async () => {
    const user = newUser();
    const { mock } = await renderLoaded(REPORT as unknown as WireRow[], (method, pathname) =>
      method === "POST" && APPLY_PATH.test(pathname)
        ? Promise.resolve(applyFailedResponse(MISSING_ROW.table_name, "create"))
        : undefined,
    );
    await chooseCreate(user, MISSING_ROW.table_name);
    expect(bodyRows()).toHaveLength(REPORT.length);
    await chooseCreate(user, MISSING_ROW.table_name);
    expect(mutations(mock)).toHaveLength(2);
  });

  it("a failed direct Sync renders its message in the Alert, clears the marker, no notification — DoD-10", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded(REPORT as unknown as WireRow[], (method, pathname) =>
      method === "POST" && APPLY_PATH.test(pathname)
        ? Promise.resolve(applyFailedResponse(SAFE_DRIFTED_ROW.table_name, "sync"))
        : undefined,
    );

    await chooseSync(user, SAFE_DRIFTED_ROW.table_name);

    const alert = alertWith(APPLY_FAILURE);
    expect(isBefore(alert, table())).toBe(true);
    expect(state.applyingTable).toBeNull();
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    await chooseSync(user, SAFE_DRIFTED_ROW.table_name);
    expect(mutations(mock)).toHaveLength(2);
  });

  it("a failed confirmed Sync renders its message in the Alert, clears the marker, no notification — DoD-10", async () => {
    const user = newUser();
    const { state } = await renderLoaded(REPORT as unknown as WireRow[], (method, pathname) =>
      method === "POST" && APPLY_PATH.test(pathname)
        ? Promise.resolve(applyFailedResponse(LOSSY_DRIFTED_ROW.table_name, "sync"))
        : undefined,
    );

    await confirmDialog(user, await openSyncConfirm(user, LOSSY_DRIFTED_ROW.table_name));

    await waitFor(() => {
      alertWith(APPLY_FAILURE);
    });
    expect(state.applyingTable).toBeNull();
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("a transport failure on an apply also lands in the Alert, never a notification — DoD-10", async () => {
    const user = newUser();
    const { state } = await renderLoaded(REPORT as unknown as WireRow[], (method) =>
      method === "POST" ? Promise.reject(new TypeError("Failed to fetch")) : undefined,
    );
    await chooseCreate(user, MISSING_ROW.table_name);
    expect((state.errorMessage ?? "").length).toBeGreaterThan(0);
    expect(alerts().length).toBeGreaterThan(0);
    expect(state.applyingTable).toBeNull();
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it.each<[string, (state: DatabasePageState) => Promise<void>, string, "create" | "sync"]>([
    ["createDriftTable", (state) => createDriftTable(state, MISSING_ROW.table_name), MISSING_ROW.table_name, "create"],
    ["syncDriftTable", (state) => syncDriftTable(state, SAFE_DRIFTED_ROW.table_name), SAFE_DRIFTED_ROW.table_name, "sync"],
  ])(
    "%s marks the table in progress while in flight, then on failure writes the message and clears it — DoD-10",
    async (_label, run, name, operation) => {
      const pending = deferred<Response>();
      serveDatabase(REPORT as unknown as WireRow[], (method) => (method === "POST" ? pending.promise : undefined));
      const state = readyWith(REPORT);

      const running = run(state);
      await settle();
      expect(state.applyingTable).toBe(name);

      pending.resolve(applyFailedResponse(name, operation));
      await expect(running).resolves.toBeUndefined();
      expect(state.applyingTable).toBeNull();
      expect(state.errorMessage).toEqual(expect.stringContaining(APPLY_FAILURE));
    },
  );

  it("no module of this page imports notifyFailure or Mantine's notifications — DoD-10", () => {
    const offenders = PAGE_MODULES.flatMap((file) =>
      importSpecifiers(readFileSync(file, "utf8"))
        .filter((spec) => /notifyFailure|@mantine\/notifications/.test(spec))
        .map((spec) => `${path.basename(file)} imports ${spec}`),
    );
    expect(offenders).toEqual([]);
  });
});

// ===========================================================================
describe("a failed apply mutates nothing locally", () => {
  it.each<[string, (state: DatabasePageState) => Promise<void>, string, "create" | "sync"]>([
    ["createDriftTable", (state) => createDriftTable(state, MISSING_ROW.table_name), MISSING_ROW.table_name, "create"],
    ["syncDriftTable", (state) => syncDriftTable(state, LOSSY_DRIFTED_ROW.table_name), LOSSY_DRIFTED_ROW.table_name, "sync"],
  ])("%s leaves the rows exactly as they were on failure — DoD-11", async (_label, run, name, operation) => {
    serveDatabase(REPORT as unknown as WireRow[], (method) =>
      method === "POST" ? Promise.resolve(applyFailedResponse(name, operation)) : undefined,
    );
    const state = readyWith(REPORT);
    await expect(run(state)).resolves.toBeUndefined();
    expect(toJS(state.rows)).toEqual(REPORT);
  });

  it("after a failed Create the row still shows missing — DoD-11", async () => {
    const user = newUser();
    await renderLoaded(REPORT as unknown as WireRow[], (method, pathname) =>
      method === "POST" && APPLY_PATH.test(pathname)
        ? Promise.resolve(applyFailedResponse(MISSING_ROW.table_name, "create"))
        : undefined,
    );
    await chooseCreate(user, MISSING_ROW.table_name);
    expect(badgeText(MISSING_ROW.table_name)).toMatch(MISSING_WORD);
  });

  it("after a failed Sync the row still shows drifted, until a successful re-load replaces it — DoD-11", async () => {
    const user = newUser();
    let failNext = true;
    await renderLoaded(REPORT as unknown as WireRow[], (method, pathname) => {
      if (method === "POST" && APPLY_PATH.test(pathname) && failNext) {
        failNext = false;
        return Promise.resolve(applyFailedResponse(SAFE_DRIFTED_ROW.table_name, "sync"));
      }
      return undefined;
    });

    await chooseSync(user, SAFE_DRIFTED_ROW.table_name);
    expect(badgeText(SAFE_DRIFTED_ROW.table_name)).toMatch(DRIFTED_WORD);

    await chooseSync(user, SAFE_DRIFTED_ROW.table_name);
    expect(badgeText(SAFE_DRIFTED_ROW.table_name)).toMatch(IN_SYNC_WORD);
  });
});

// ===========================================================================
describe("no success notification", () => {
  it("a successful Create, direct Sync and confirmed Sync raise no notification and no toast — DoD-12", async () => {
    const user = newUser();
    await renderLoaded();

    await chooseCreate(user, MISSING_ROW.table_name);
    await chooseSync(user, SAFE_DRIFTED_ROW.table_name);
    await confirmDialog(user, await openSyncConfirm(user, LOSSY_DRIFTED_ROW.table_name));
    await flush();

    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(alerts()).toEqual([]);
    expect(readableText()).not.toMatch(/\bsuccess/i);
  });

  it("success is the report refreshing: each row's badge turns in sync — DoD-12", async () => {
    const user = newUser();
    await renderLoaded();
    await chooseCreate(user, MISSING_ROW.table_name);
    await chooseSync(user, SAFE_DRIFTED_ROW.table_name);
    await confirmDialog(user, await openSyncConfirm(user, LOSSY_DRIFTED_ROW.table_name));
    await waitFor(() => {
      for (const row of REPORT) expect(badgeText(row.table_name), row.table_name).toMatch(IN_SYNC_WORD);
    });
    expect(notificationRoots()).toEqual([]);
  });

  it("neither module imports a notification API — DoD-12", () => {
    for (const file of PAGE_MODULES) {
      const specs = importSpecifiers(readFileSync(file, "utf8"));
      expect(
        specs.filter((spec) => /notif|toast/i.test(spec)),
        path.basename(file),
      ).toEqual([]);
    }
  });
});

// ===========================================================================
describe("one overflow menu per row", () => {
  it.each([MISSING_ROW, SAFE_DRIFTED_ROW, LOSSY_DRIFTED_ROW])(
    "$table_name has exactly one icon-only control, in its trailing cell — DoD-13",
    async (row) => {
      await renderLoaded();
      const tr = rowFor(row.table_name);
      const controls = iconOnlyControls(tr);
      expect(controls).toHaveLength(1);
      const cells = cellsOf(tr);
      expect(cells[cells.length - 1].contains(controls[0])).toBe(true);
      expect(controls[0]).toHaveAccessibleName(/\S/);
    },
  );

  it.each([MISSING_ROW, SAFE_DRIFTED_ROW, LOSSY_DRIFTED_ROW])(
    "the menu items on $table_name are text-labelled — DoD-13",
    async (row) => {
      const user = newUser();
      await renderLoaded();
      const items = await menuItemsOf(user, row.table_name);
      expect(items.length).toBeGreaterThan(0);
      for (const item of items) expect((item.textContent ?? "").trim().length).toBeGreaterThan(0);
    },
  );

  it("the trigger is IconDots through shared/IconButton, inside a Menu, in the w={60} column — DoD-13", () => {
    const source = readSource(PAGE_SOURCE);
    const specs = importSpecifiers(readFileSync(PAGE_SOURCE, "utf8"));
    expect(specs.some((spec) => /(^|\/)shared\/IconButton$/.test(spec))).toBe(true);
    expect(source).toMatch(/\bIconDots\b/);
    expect(source).toMatch(/<IconButton\b[\s\S]{0,400}?\bicon\s*=\s*\{\s*IconDots\s*\}/);
    expect(source).toMatch(/<Menu\b/);
    expect(source).toMatch(/<Menu\.Item\b/);
    expect(source).toMatch(/\bw\s*=\s*\{\s*60\s*\}/);
    expect(source).not.toMatch(/\bActionIcon\b/);
    expect(source.match(/<IconButton\b/g) ?? []).toHaveLength(1);
  });
});

// ===========================================================================
describe("nothing out of scope in the menu", () => {
  it.each([MISSING_ROW, SAFE_DRIFTED_ROW, LOSSY_DRIFTED_ROW])(
    "$table_name's menu offers no Rebuild index, Export or Import item, enabled or disabled — DoD-14",
    async (row) => {
      const user = newUser();
      await renderLoaded();
      const items = await menuItemsOf(user, row.table_name);
      expect(
        items.map((item) => item.textContent ?? "").filter((text) => OUT_OF_SCOPE_ROW_ITEM.test(text)),
      ).toEqual([]);
      expect(dropdownFor(row.table_name).textContent ?? "").not.toMatch(OUT_OF_SCOPE_ROW_ITEM);
    },
  );

  // S030_005_DoD1 — page-wide sweep, so it narrowed to Rebuild/Import; the row-menu clause
  // above keeps the full regex and still forbids an Export item in a dropdown.
  it("no control anywhere on the page is named Rebuild or Import — DoD-14 (S030_005_DoD1)", async () => {
    const user = newUser();
    await renderLoaded();
    await openRowMenu(user, MISSING_ROW.table_name);
    const names = anyControls(document.body).map((el) =>
      [el.textContent ?? "", ...NAMING_ATTRIBUTES.map((name) => el.getAttribute(name) ?? "")].join(" "),
    );
    expect(names.filter((name) => OUT_OF_SCOPE_ITEM.test(name))).toEqual([]);
  });
});

// ===========================================================================
describe("effects are free functions; predicates are pure; the store has no methods", () => {
  // S030_005_DoD10 — 030 step 005 adds three observable fields (`exportStatus`,
  // `exportSizeBytes`, `exportErrorMessage`). This is this file's own independent copy of the
  // list; it stays alphabetical and still pins the store's whole surface.
  const ALLOWED_FIELDS = [
    "applyingTable",
    "errorMessage",
    "exportErrorMessage",
    "exportSizeBytes",
    "exportStatus",
    "rows",
    "status",
  ];

  it("the class prototype carries no method and no getter — DoD-15 (D13)", () => {
    expect(Object.getOwnPropertyNames(DatabasePageState.prototype)).toEqual(["constructor"]);
  });

  it("applyingTable is an observable field, null on a fresh store; nothing is computed or a function — DoD-15 (D13)", () => {
    const state = new DatabasePageState();
    expect(state.applyingTable).toBeNull();
    expect(isObservableProp(state, "applyingTable")).toBe(true);
    const record = state as unknown as Record<string, unknown>;
    for (const name of Object.getOwnPropertyNames(state)) {
      expect(ALLOWED_FIELDS, `own property ${name}`).toContain(name);
      expect(isObservableProp(state, name), name).toBe(true);
      expect(isComputedProp(state, name), name).toBe(false);
      expect(typeof record[name], name).not.toBe("function");
    }
  });

  it("the page calls both effects with its store first and the table name second — DoD-15 (D13)", async () => {
    const user = newUser();
    const { state } = await renderLoaded();
    await chooseCreate(user, MISSING_ROW.table_name);
    await chooseSync(user, SAFE_DRIFTED_ROW.table_name);
    expect(spied.create.map((args) => [args[0] === state, args[1]])).toEqual([[true, MISSING_ROW.table_name]]);
    expect(spied.sync.map((args) => [args[0] === state, args[1]])).toEqual([[true, SAFE_DRIFTED_ROW.table_name]]);
    for (const args of [...spied.create, ...spied.sync]) {
      expect(args.length).toBeLessThanOrEqual(3);
      if (args.length === 3) expect(args[2] === undefined || args[2] instanceof AbortSignal).toBe(true);
    }
  });

  it("both effects write only inside actions (strict MobX raises no warning) — DoD-15 (D13)", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    configure({ enforceActions: "always" });
    try {
      const run = async (override?: Override) => {
        serveDatabase(REPORT as unknown as WireRow[], override);
        const state = readyWith(REPORT);
        const dispose = autorun(() => {
          void state.rows.length;
          void state.status;
          void state.errorMessage;
          void state.applyingTable;
        });
        await createDriftTable(state, MISSING_ROW.table_name);
        await syncDriftTable(state, LOSSY_DRIFTED_ROW.table_name);
        dispose();
        vi.unstubAllGlobals();
      };
      await run();
      await run((method) => (method === "POST" ? Promise.resolve(applyFailedResponse("models", "create")) : undefined));
      await run((method) => (method === "POST" ? Promise.reject(new TypeError("Failed to fetch")) : undefined));
    } finally {
      configure({ enforceActions: "observed" });
    }
    const mobxWarnings = warn.mock.calls.filter((args) => args.some((arg) => String(arg).includes("[MobX]")));
    expect(mobxWarnings).toEqual([]);
  });

  it.each<[string, (state: DatabasePageState, signal: AbortSignal) => Promise<void>]>([
    ["createDriftTable", (state, signal) => createDriftTable(state, MISSING_ROW.table_name, signal)],
    ["syncDriftTable", (state, signal) => syncDriftTable(state, LOSSY_DRIFTED_ROW.table_name, signal)],
  ])("%s given an already-aborted signal writes nothing and does not reject — DoD-15 (D13)", async (_label, run) => {
    serveDatabase();
    for (const state of [new DatabasePageState(), readyWith(REPORT)]) {
      const before = snapshot(state);
      const controller = new AbortController();
      controller.abort();
      await expect(run(state, controller.signal)).resolves.toBeUndefined();
      await settle();
      expect(snapshot(state)).toEqual(before);
    }
  });

  it.each<[string, (state: DatabasePageState, signal: AbortSignal) => Promise<void>]>([
    ["createDriftTable", (state, signal) => createDriftTable(state, MISSING_ROW.table_name, signal)],
    ["syncDriftTable", (state, signal) => syncDriftTable(state, LOSSY_DRIFTED_ROW.table_name, signal)],
  ])("%s writes nothing once its signal aborts mid-request — DoD-15 (D13)", async (_label, run) => {
    const pending = deferred<Response>();
    serveDatabase(REPORT as unknown as WireRow[], (method) => (method === "POST" ? pending.promise : undefined));
    const state = readyWith(REPORT);
    const controller = new AbortController();
    const running = run(state, controller.signal);
    await settle();
    const atAbort = snapshot(state);
    controller.abort();
    pending.resolve(jsonResponse(inSync("models"), 200));
    await expect(running).resolves.toBeUndefined();
    await settle();
    expect(snapshot(state)).toEqual(atAbort);
  });

  it("an effect never rejects, on success or failure — DoD-15", async () => {
    serveDatabase();
    await expect(createDriftTable(readyWith(REPORT), MISSING_ROW.table_name)).resolves.toBeUndefined();
    vi.unstubAllGlobals();
    serveDatabase(REPORT as unknown as WireRow[], () => Promise.reject(new TypeError("Failed to fetch")));
    await expect(syncDriftTable(readyWith(REPORT), SAFE_DRIFTED_ROW.table_name)).resolves.toBeUndefined();
  });

  it("the lossy predicate is pure and needs no render — DoD-15 (D13)", () => {
    const lossy = Object.freeze({ extra_columns: Object.freeze(["legacy_flag"]) as unknown as string[] });
    const safe = Object.freeze({ extra_columns: Object.freeze([]) as unknown as string[] });
    expect(isLossySync(lossy)).toBe(true);
    expect(isLossySync(lossy)).toBe(true);
    expect(isLossySync(safe)).toBe(false);
    expect(isLossySync(safe)).toBe(false);
    expect(lossy).toEqual({ extra_columns: ["legacy_flag"] });
  });

  it("the consequence helper is pure and needs no render — DoD-15 (D13)", () => {
    const input = JSON.parse(JSON.stringify(LOSSY_DRIFTED_ROW)) as DriftTableRow;
    const first = syncConsequenceOf(input);
    expect(typeof first).toBe("string");
    expect(syncConsequenceOf(input)).toBe(first);
    expect(input).toEqual(LOSSY_DRIFTED_ROW);
    expect(syncConsequenceOf({ table_name: input.table_name, extra_columns: [...input.extra_columns] })).toBe(first);
  });

  it("the store module writes through runInAction and the effects are exported free functions — DoD-15 (D13)", () => {
    const source = readSource(STATE_SOURCE);
    expect(source).toMatch(/\brunInAction\b/);
    expect(source).toMatch(/export\s+async\s+function\s+createDriftTable\s*\(/);
    expect(source).toMatch(/export\s+async\s+function\s+syncDriftTable\s*\(/);
  });
});

// ===========================================================================
describe("unmounting mid-apply", () => {
  it("aborts the in-flight apply request — DoD-16 (D13)", async () => {
    const user = newUser();
    const pending = deferred<Response>();
    const { mock, view } = await renderLoaded(REPORT as unknown as WireRow[], (method) =>
      method === "POST" ? pending.promise : undefined,
    );

    await chooseCreate(user, MISSING_ROW.table_name);
    const inits = postInits(mock);
    expect(inits).toHaveLength(1);
    const signal = inits[0]?.signal;
    expect(signal).toBeTruthy();
    expect(signal?.aborted).toBe(false);

    view.unmount();
    expect(signal?.aborted).toBe(true);
    pending.resolve(jsonResponse(inSync(MISSING_ROW.table_name), 200));
    await flush();
  });

  it("writes nothing into the store after unmount — a late success — DoD-16 (D13)", async () => {
    const user = newUser();
    const pending = deferred<Response>();
    const { view, state } = await renderLoaded(REPORT as unknown as WireRow[], (method) =>
      method === "POST" ? pending.promise : undefined,
    );

    await chooseSync(user, SAFE_DRIFTED_ROW.table_name);
    const atUnmount = snapshot(state);
    view.unmount();
    pending.resolve(jsonResponse(inSync(SAFE_DRIFTED_ROW.table_name), 200));
    await flush();

    expect(snapshot(state)).toEqual(atUnmount);
  });

  it("writes nothing into the store after unmount — a late failure — DoD-16 (D13)", async () => {
    const user = newUser();
    const pending = deferred<Response>();
    const { view, state } = await renderLoaded(REPORT as unknown as WireRow[], (method) =>
      method === "POST" ? pending.promise : undefined,
    );

    await chooseCreate(user, MISSING_ROW.table_name);
    const atUnmount = snapshot(state);
    view.unmount();
    pending.resolve(applyFailedResponse(MISSING_ROW.table_name, "create"));
    await flush();

    expect(snapshot(state)).toEqual(atUnmount);
    expect(state.errorMessage).toBeNull();
  });
});
