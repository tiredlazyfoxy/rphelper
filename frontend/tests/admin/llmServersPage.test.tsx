// Feature 006, step 006 — the LLM Servers page: its MobX store and free functions, the table,
// the row overflow menu, the confirmed delete and Test connection (DoD-1..DoD-19).
// DoD-20 and DoD-21 are [manual/live].
//
// Expected behaviour comes from the step's Interface intent and DoD, 006.context.md and
// context.md (D1 columns, D6 outcome taxonomy, D14 secret_ref_missing 500, D16 MobX rules, D17
// routes, D18 confirm, R5, never-optimistic, no notifications). Bindings come from the frozen
// `### Step 006` record: the page takes the store as a prop, so tests construct
// `new LlmServersPageState()` and render `<LlmServersPage state={...} />` under `AppProviders` +
// `MemoryRouter`. `fetch` is stubbed per test with a tiny in-memory backend for the three routes
// the page may call. `notifyFailure` is mocked at file level. The store module is wrapped
// pass-through so the page's calls to its free functions are observable — behaviour unchanged.
//
// Recognition conventions (from spec wording, for the verifier):
// - Loader: Mantine `Loader` root, `.mantine-Loader-root`. Table: the `<table>`; rows are
//   `tbody tr`; headers `thead th`. Inline error: Mantine `Alert`, `role="alert"`.
//   Notifications: `.mantine-Notification-root`. Kind badge: `.mantine-Badge-root`.
// - Menu items are looked up inside the dropdown owned by the trigger just clicked. Items:
//   /test\s*connection/i and /\bdelete\b/i. The confirm: `role="dialog"`, confirm button
//   /delete|remove/i, cancel /cancel/i.
// - The last-test badge's words are whatever `lastTestBadgeOf` answers for the row; a row "shows"
//   a label when one of its cells contains it as a whole word run (so "unreachable" never counts
//   as showing "reachable").
// - "Whether an API key is recorded": the cell under the header matching /api\s*key|\bkey\b/i;
//   its text, naming attributes and icon classes differ between a row with a key and one without.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { autorun, configure, isComputedProp, isObservableProp, runInAction, toJS } from "mobx";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AdminApp } from "../../src/admin/AdminApp";
import { LlmServersPage } from "../../src/admin/LlmServersPage";
import {
  deleteLlmServer,
  lastTestBadgeOf,
  type LlmServerRow,
  LlmServersPageState,
  loadLlmServers,
  type ProbeOutcome,
  testLlmServerConnection,
} from "../../src/admin/llmServersPageState";
import { AppProviders } from "../../src/shared/AppProviders";

const { notifyFailureSpy, spied } = vi.hoisted(() => ({
  notifyFailureSpy: vi.fn(),
  spied: {
    load: [] as unknown[][],
    del: [] as unknown[][],
    test: [] as unknown[][],
    badge: [] as unknown[][],
  },
}));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));
vi.mock("../../src/admin/llmServersPageState", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../src/admin/llmServersPageState")>();
  return {
    ...actual,
    loadLlmServers: (...args: Parameters<typeof actual.loadLlmServers>) => {
      spied.load.push(args);
      return actual.loadLlmServers(...args);
    },
    deleteLlmServer: (...args: Parameters<typeof actual.deleteLlmServer>) => {
      spied.del.push(args);
      return actual.deleteLlmServer(...args);
    },
    testLlmServerConnection: (...args: Parameters<typeof actual.testLlmServerConnection>) => {
      spied.test.push(args);
      return actual.testLlmServerConnection(...args);
    },
    lastTestBadgeOf: (...args: Parameters<typeof actual.lastTestBadgeOf>) => {
      spied.badge.push(args);
      return actual.lastTestBadgeOf(...args);
    },
  };
});

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type User = ReturnType<typeof userEvent.setup>;
type WireRow = Record<string, unknown>;

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const ADMIN_SRC = path.join(FRONTEND_ROOT, "src", "admin");
const STATE_SOURCE = path.join(ADMIN_SRC, "llmServersPageState.ts");
const PAGE_SOURCE = path.join(ADMIN_SRC, "LlmServersPage.tsx");
const ADMIN_APP_SOURCE = path.join(ADMIN_SRC, "AdminApp.tsx");
const PAGE_MODULES = [STATE_SOURCE, PAGE_SOURCE];

const LIST_PATH = "/api/admin/llm-servers";
const DELETE_PATH = /^\/api\/admin\/llm-servers\/([^/]+)$/;
const TEST_PATH = /^\/api\/admin\/llm-servers\/([^/]+)\/test$/;
const USERS_LIST_PATH = "/api/admin/users";
const FAILURE_MESSAGE = "The server registry is on fire zq-66.";
const SECRET_MESSAGE = "environment variable RPH_ORCHARD_KEY is not set zq-67";
const BIG_ID = "9007199254740993"; // 2^53 + 1 — not representable as a JS number
const TESTED_AT = "2026-09-30T12:00:00.000000+00:00";

const TEST_ITEM = /test\s*connection/i;
const DELETE_ITEM = /\bdelete\b/i;
const CONFIRM_DELETE = /delete|remove/i;
const CANCEL_NAME = /cancel/i;
const NOTIFICATION_ROOT = ".mantine-Notification-root";
const LOADER = ".mantine-Loader-root";
const NOT_FOUND_TEXT = /not found|does not exist|doesn't exist|no such page|404/i;
const API_KEY_HEADER = /api\s*key|\bkey\b/i;
/** R5 — nothing derived from another user's data. */
const OTHER_USERS_DATA = /\b(sessions?|users?|characters?|setups?|memos?|entry|entries)\b/i;
const NUMBER_WORDS = /\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|dozens?|several|many)\b/i;

/** Base URLs and names carry no digit, so any digit in the confirm is a count. */
const ATTIC: LlmServerRow = {
  id: "7340032000000201",
  name: "Attic box",
  kind: "llamaswap",
  base_url: "http://attic.lan/llama",
  has_api_key: false,
  enabled_model_names: ["qwen-chat", "mistral-small", "nomic-embed"],
  embedding_model_name: "nomic-embed",
  embedding_dim: 768,
  last_test_at: null,
  last_test_ok: null,
  last_test_error: null,
  created_at: "2026-09-01T08:00:00.000000+00:00",
  updated_at: "2026-09-01T08:00:00.000000+00:00",
};
const ORCHARD: LlmServerRow = {
  id: "7340032000000202",
  name: "Orchard cloud",
  kind: "openai",
  base_url: "https://api.orchard.example",
  has_api_key: true,
  enabled_model_names: [],
  embedding_model_name: null,
  embedding_dim: null,
  last_test_at: "2026-09-02T10:00:00.000000+00:00",
  last_test_ok: true,
  last_test_error: null,
  created_at: "2026-09-02T08:00:00.000000+00:00",
  updated_at: "2026-09-02T10:00:00.000000+00:00",
};
const CELLAR: LlmServerRow = {
  id: "7340032000000203",
  name: "Cellar gateway",
  kind: "openai",
  base_url: "https://cellar.example/gateway",
  has_api_key: true,
  enabled_model_names: ["gpt-mini"],
  embedding_model_name: null,
  embedding_dim: null,
  last_test_at: "2026-09-03T10:00:00.000000+00:00",
  last_test_ok: false,
  last_test_error: "auth_failed",
  created_at: "2026-09-03T08:00:00.000000+00:00",
  updated_at: "2026-09-03T10:00:00.000000+00:00",
};
const EVERYONE: LlmServerRow[] = [ATTIC, ORCHARD, CELLAR];

type OutcomeCase = { outcome: ProbeOutcome; ok: boolean; error: ProbeOutcome | null };
const OUTCOMES: OutcomeCase[] = [
  { outcome: "reachable", ok: true, error: null },
  { outcome: "unreachable", ok: false, error: "unreachable" },
  { outcome: "auth_failed", ok: false, error: "auth_failed" },
  { outcome: "model_list_empty", ok: false, error: "model_list_empty" },
];
const FAILING_OUTCOMES = OUTCOMES.filter((c) => !c.ok);

beforeEach(() => {
  notifyFailureSpy.mockClear();
  spied.load.length = 0;
  spied.del.length = 0;
  spied.test.length = 0;
  spied.badge.length = 0;
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

function failureResponse(): Response {
  return errorResponse("internal_error", FAILURE_MESSAGE, 500);
}

function secretMissingResponse(): Response {
  return errorResponse("secret_ref_missing", SECRET_MESSAGE, 500, { variable: "RPH_ORCHARD_KEY" });
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

function copyRows(rows: readonly WireRow[]): WireRow[] {
  return rows.map((row) => ({ ...row, enabled_model_names: [...((row.enabled_model_names as string[]) ?? [])] }));
}

type Override = (method: string, path: string) => Promise<Response> | undefined;
type ServeOptions = { outcome?: ProbeOutcome; override?: Override };

/**
 * A tiny in-memory backend for GET /api/admin/llm-servers, DELETE .../{id} (204) and
 * POST .../{id}/test (records the configured outcome on the row, as the server does, and answers
 * the typed result).
 */
function serveServers(initial: readonly WireRow[], options: ServeOptions = {}) {
  const rows = copyRows(initial);
  const outcome: ProbeOutcome = options.outcome ?? "reachable";
  const mock = stubFetch((input, init) => {
    const method = requestMethod(input, init);
    const pathname = requestUrl(input).pathname;
    const custom = options.override?.(method, pathname);
    if (custom !== undefined) return custom;
    if (method === "GET" && pathname === LIST_PATH) {
      return Promise.resolve(jsonResponse({ servers: copyRows(rows) }, 200));
    }
    const testMatch = TEST_PATH.exec(pathname);
    if (method === "POST" && testMatch !== null) {
      const row = rows.find((candidate) => candidate.id === testMatch[1]);
      if (row === undefined) {
        return Promise.resolve(errorResponse("llm_server_not_found", "That connection does not exist.", 404));
      }
      const ok = outcome === "reachable";
      row.last_test_at = TESTED_AT;
      row.last_test_ok = ok;
      row.last_test_error = ok ? null : outcome;
      return Promise.resolve(jsonResponse({ outcome, ok, tested_at: TESTED_AT }, 200));
    }
    const deleteMatch = DELETE_PATH.exec(pathname);
    if (method === "DELETE" && deleteMatch !== null) {
      const index = rows.findIndex((candidate) => candidate.id === deleteMatch[1]);
      if (index < 0) {
        return Promise.resolve(errorResponse("llm_server_not_found", "That connection does not exist.", 404));
      }
      rows.splice(index, 1);
      return Promise.resolve(new Response(null, { status: 204 }));
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

function snapshot(state: LlmServersPageState) {
  return {
    rows: toJS(state.rows),
    status: state.status,
    errorMessage: state.errorMessage,
    testingId: state.testingId,
  };
}

function withRows(rows: readonly LlmServerRow[]): LlmServersPageState {
  const state = new LlmServersPageState();
  runInAction(() => {
    state.rows = copyRows(rows) as LlmServerRow[];
    state.status = "ready";
  });
  return state;
}

function afterTest(row: LlmServerRow, c: OutcomeCase): LlmServerRow {
  return { ...row, last_test_at: TESTED_AT, last_test_ok: c.ok, last_test_error: c.error };
}

function labelOf(row: Pick<LlmServerRow, "last_test_at" | "last_test_ok" | "last_test_error">): string {
  return lastTestBadgeOf(row).label;
}

// ---------------------------------------------------------------- render + queries

function renderPage(state: LlmServersPageState = new LlmServersPageState()) {
  const view = render(
    <AppProviders>
      <MemoryRouter initialEntries={["/llm-servers"]}>
        <LlmServersPage state={state} />
      </MemoryRouter>
    </AppProviders>,
  );
  return { view, state };
}

async function renderLoaded(rows: readonly WireRow[] = EVERYONE, options: ServeOptions = {}) {
  const server = serveServers(rows, options);
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

function headerTexts(): string[] {
  return Array.from(table().querySelectorAll("thead th")).map((th) => (th.textContent ?? "").trim());
}

function cellsOf(tr: HTMLTableRowElement): HTMLTableCellElement[] {
  return Array.from(tr.querySelectorAll<HTMLTableCellElement>("td"));
}

function findRow(name: string): HTMLTableRowElement | undefined {
  return bodyRows().find((tr) => cellsOf(tr).some((td) => (td.textContent ?? "").trim() === name));
}

function rowFor(name: string): HTMLTableRowElement {
  const matches = bodyRows().filter((tr) => cellsOf(tr).some((td) => (td.textContent ?? "").trim() === name));
  expect(matches, `rows showing ${name}`).toHaveLength(1);
  return matches[0];
}

function cellTexts(name: string): string[] {
  return cellsOf(rowFor(name)).map((td) => (td.textContent ?? "").trim());
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** `label` appears in one of the row's cells as a whole run, not glued to other letters. */
function rowShows(name: string, label: string): boolean {
  const bounded = new RegExp(`(^|[^\\p{L}])${escapeRegExp(label)}($|[^\\p{L}])`, "iu");
  return cellTexts(name).some((text) => bounded.test(text));
}

function columnIndex(pattern: RegExp): number {
  const indexes = headerTexts()
    .map((text, index) => (pattern.test(text) ? index : -1))
    .filter((index) => index >= 0);
  expect(indexes, `header columns matching ${pattern}`).toHaveLength(1);
  return indexes[0];
}

/** What a person reads or hears in a cell: text, naming attributes, and icon identity. */
function cellSignature(cell: Element): string {
  const parts = [(cell.textContent ?? "").trim()];
  for (const el of [cell, ...Array.from(cell.querySelectorAll("*"))]) {
    for (const name of ["aria-label", "title", "aria-description"]) {
      const value = el.getAttribute(name);
      if (value) parts.push(`${name}=${value}`);
    }
    if (el.tagName.toLowerCase() === "svg") parts.push(`svg=${el.getAttribute("class") ?? ""}`);
  }
  return parts.join("|");
}

function iconOnlyControls(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      "button, a[href], [role='button'], input[type='button'], input[type='image'], input[type='submit']",
    ),
  ).filter((el) => (el.textContent ?? "").trim() === "");
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

async function testConnection(user: User, name: string): Promise<void> {
  await chooseMenuItem(user, await openRowMenu(user, name), TEST_ITEM);
  await flush();
}

async function openDeleteConfirm(user: User, name: string): Promise<HTMLElement> {
  await chooseMenuItem(user, await openRowMenu(user, name), DELETE_ITEM);
  return screen.findByRole("dialog");
}

async function closeDialog(user: User, dialog: HTMLElement): Promise<void> {
  await user.click(within(dialog).getByRole("button", { name: CANCEL_NAME }));
  await waitFor(() => {
    expect(screen.queryByRole("dialog")).toBeNull();
  });
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

function readableText(): string {
  const attributes = ["aria-label", "title", "aria-description", "placeholder", "alt", "aria-valuetext"];
  const values = Array.from(document.body.querySelectorAll("*")).flatMap((el) =>
    attributes.map((name) => el.getAttribute(name) ?? "").filter(Boolean),
  );
  return [document.body.textContent ?? "", ...values].join("\n");
}

function laterListLoads(calls: Seen[], afterMethod: string): Seen[] {
  const index = calls.findIndex((call) => call.method === afterMethod);
  expect(index, `a ${afterMethod} request`).toBeGreaterThanOrEqual(0);
  return calls.slice(index + 1).filter((call) => call.method === "GET" && call.path === LIST_PATH);
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

function walkFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    return entry.isDirectory() ? walkFiles(full) : [full];
  });
}

function relative(file: string): string {
  return path.relative(FRONTEND_ROOT, file).split(path.sep).join("/");
}

// ===========================================================================
describe("loading and the rendered table", () => {
  it("on mount issues exactly one request, for the registration list, with no query — DoD-1", async () => {
    const { mock } = await renderLoaded();
    expect(seen(mock)).toEqual([{ method: "GET", path: LIST_PATH, search: "" }]);
  });

  it("renders one row per registration, in the server's order — DoD-1 (US-012.AC-2, UC-010)", async () => {
    await renderLoaded();
    expect(bodyRows()).toHaveLength(3);
    for (const server of EVERYONE) rowFor(server.name);
    const order = bodyRows().map(
      (tr) => EVERYONE.find((s) => cellsOf(tr).some((td) => (td.textContent ?? "").trim() === s.name))?.name,
    );
    expect(order).toEqual([ATTIC.name, ORCHARD.name, CELLAR.name]);
  });

  it("each row shows the registration's name and base URL — DoD-1 (US-012.AC-2)", async () => {
    await renderLoaded();
    for (const server of EVERYONE) {
      expect(cellTexts(server.name), server.name).toContain(server.name);
      expect(cellTexts(server.name).some((text) => text.includes(server.base_url)), server.name).toBe(true);
    }
  });

  it("each row shows its kind as a badge — DoD-1 (US-012.AC-2)", async () => {
    await renderLoaded();
    const kindBadges = (name: string) =>
      Array.from(rowFor(name).querySelectorAll(".mantine-Badge-root")).map((el) => (el.textContent ?? "").trim());
    expect(kindBadges(ATTIC.name).some((text) => /llama\s*-?\s*swap/i.test(text))).toBe(true);
    expect(kindBadges(ATTIC.name).some((text) => /open\s*-?\s*ai/i.test(text))).toBe(false);
    for (const name of [ORCHARD.name, CELLAR.name]) {
      expect(kindBadges(name).some((text) => /open\s*-?\s*ai/i.test(text)), name).toBe(true);
      expect(kindBadges(name).some((text) => /llama\s*-?\s*swap/i.test(text)), name).toBe(false);
    }
  });

  it("each row shows whether an API key is recorded, two rows alike iff their flags agree — DoD-1", async () => {
    await renderLoaded();
    const keyColumn = columnIndex(API_KEY_HEADER);
    const signature = (name: string) => cellSignature(cellsOf(rowFor(name))[keyColumn]);
    expect(signature(ATTIC.name).replace(/\|/g, "").length).toBeGreaterThan(0);
    expect(signature(ORCHARD.name).replace(/\|/g, "").length).toBeGreaterThan(0);
    expect(signature(ORCHARD.name)).toBe(signature(CELLAR.name));
    expect(signature(ATTIC.name)).not.toBe(signature(ORCHARD.name));
  });

  it("each row shows the enabled-model count — the length of the enabled names — DoD-1", async () => {
    await renderLoaded();
    expect(cellTexts(ATTIC.name)).toContain("3");
    expect(cellTexts(ORCHARD.name)).toContain("0");
    expect(cellTexts(CELLAR.name)).toContain("1");
  });
});

// ===========================================================================
describe("rows arrive only through a load", () => {
  it("a registration created through the API appears after a load, not before — DoD-2 (US-012.AC-2)", async () => {
    const { rows, state } = await renderLoaded([ATTIC, ORCHARD]);
    const created: LlmServerRow = { ...CELLAR, id: "7340032000000299", name: "Newcomer rig" };
    rows.push({ ...created });
    expect(bodyRows()).toHaveLength(2);
    expect(findRow(created.name)).toBeUndefined();

    await act(async () => {
      await loadLlmServers(state);
    });
    await flush();

    expect(bodyRows()).toHaveLength(3);
    rowFor(created.name);
    expect(state.rows.map((row) => row.id)).toEqual([ATTIC.id, ORCHARD.id, created.id]);
  });

  it("the store and page modules have no local insertion path into the rows — DoD-2", () => {
    const state = readSource(STATE_SOURCE);
    expect(state).not.toMatch(/\brows\s*\.\s*(push|unshift|splice)\s*\(/);
    expect(state).not.toMatch(/\brows\s*=\s*\[\s*\.\.\./);
    const page = readSource(PAGE_SOURCE);
    expect(page).not.toMatch(/\.rows\s*=[^=]/);
    expect(page).not.toMatch(/\brows\s*\.\s*(push|unshift|splice)\s*\(/);
  });
});

// ===========================================================================
describe("ids are strings", () => {
  it("the page's modules type no id as a number, call no parseInt and sort nothing — DoD-3", () => {
    for (const file of [...PAGE_MODULES, ADMIN_APP_SOURCE]) {
      const source = readSource(file);
      const name = path.basename(file);
      expect(source, name).not.toMatch(/\b\w*(?:id|Id|ID)\s*\??\s*:\s*number\b/);
      expect(source, name).not.toMatch(/\bparseInt\b|\bparseFloat\b/);
      expect(source, name).not.toMatch(/\.sort\s*\(|\.toSorted\s*\(/);
    }
  });

  it("an id beyond MAX_SAFE_INTEGER is held, tested and deleted verbatim as a string — DoD-3", async () => {
    const user = newUser();
    const big: LlmServerRow = { ...ATTIC, id: BIG_ID };
    const { mock, state } = await renderLoaded([big, ORCHARD]);
    expect(state.rows[0].id).toBe(BIG_ID);
    expect(typeof state.rows[0].id).toBe("string");

    await testConnection(user, big.name);
    const dialog = await openDeleteConfirm(user, big.name);
    await user.click(within(dialog).getByRole("button", { name: CONFIRM_DELETE }));
    await flush();

    const mutations = seen(mock).filter((call) => call.method !== "GET");
    expect(mutations).toEqual([
      { method: "POST", path: `${LIST_PATH}/${BIG_ID}/test`, search: "" },
      { method: "DELETE", path: `${LIST_PATH}/${BIG_ID}`, search: "" },
    ]);
    expect(spied.test[0][1]).toBe(BIG_ID);
    expect(spied.del[0][1]).toBe(BIG_ID);
    for (const row of state.rows) expect(typeof row.id).toBe("string");
  });
});

// ===========================================================================
describe("loading and empty states", () => {
  it("while the list is in flight a Loader renders and no table body does — DoD-4", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    renderPage();
    await flush();

    expect(loaders().length).toBeGreaterThan(0);
    expect(document.querySelector("tbody")).toBeNull();

    pending.resolve(jsonResponse({ servers: copyRows(EVERYONE) }, 200));
    await flush();
    expect(loaders()).toEqual([]);
    expect(bodyRows()).toHaveLength(3);
  });

  it("the Loader is gated on the status field, not on the rows: rows present but not ready still shows it — DoD-4", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = new LlmServersPageState();
    runInAction(() => {
      state.rows = copyRows([ATTIC]) as LlmServerRow[];
    });
    expect(state.status).not.toBe("ready");
    renderPage(state);
    await flush();

    expect(loaders().length).toBeGreaterThan(0);
    expect(document.querySelector("tbody")).toBeNull();
    pending.resolve(jsonResponse({ servers: [] }, 200));
    await flush();
  });

  it("an empty ready list renders the headers with no rows and no Loader — DoD-4", async () => {
    await renderLoaded([]);
    expect(loaders()).toEqual([]);
    const headers = headerTexts();
    expect(headers.some((text) => /name/i.test(text))).toBe(true);
    expect(headers.some((text) => /url/i.test(text))).toBe(true);
    expect(headers.some((text) => API_KEY_HEADER.test(text))).toBe(true);
    expect(bodyRows()).toHaveLength(0);
  });
});

// ===========================================================================
describe("a failed list load renders inline", () => {
  it("renders the message in an Alert above the table and raises no notification — DoD-5", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    renderPage();
    await flush();

    const alert = alertWith(FAILURE_MESSAGE);
    const rendered = document.querySelector("table");
    if (rendered !== null) expect(isBefore(alert, rendered)).toBe(true);
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("a failed load never rejects and lands the message in the store's error field — DoD-5", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    const state = new LlmServersPageState();
    await expect(loadLlmServers(state)).resolves.toBeUndefined();
    expect(state.errorMessage).toEqual(expect.stringContaining(FAILURE_MESSAGE));
    expect(state.rows).toEqual([]);
  });

  it("a transport failure also lands in the Alert, never a notification — DoD-5", async () => {
    stubFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    const { state } = renderPage();
    await flush();
    expect(typeof state.errorMessage).toBe("string");
    expect((state.errorMessage ?? "").length).toBeGreaterThan(0);
    expect(alerts().length).toBeGreaterThan(0);
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("no module of this page imports notifyFailure or Mantine's notifications — DoD-5", () => {
    const offenders = PAGE_MODULES.flatMap((file) =>
      importSpecifiers(readFileSync(file, "utf8"))
        .filter((spec) => /notifyFailure|@mantine\/notifications/.test(spec))
        .map((spec) => `${path.basename(file)} imports ${spec}`),
    );
    expect(offenders).toEqual([]);
  });
});

// ===========================================================================
describe("Test connection", () => {
  it("posts to that row's test route and then re-loads the list — DoD-6 (US-013.AC-1)", async () => {
    const user = newUser();
    const { mock } = await renderLoaded(EVERYONE, { outcome: "reachable" });

    await testConnection(user, ATTIC.name);

    const calls = seen(mock);
    expect(calls.filter((call) => call.method !== "GET")).toEqual([
      { method: "POST", path: `${LIST_PATH}/${ATTIC.id}/test`, search: "" },
    ]);
    expect(laterListLoads(calls, "POST").length).toBeGreaterThan(0);
  });

  it("on a reachable result the row's badge reads as reachable after the re-load — DoD-6 (US-013.AC-1)", async () => {
    const user = newUser();
    await renderLoaded(EVERYONE, { outcome: "reachable" });
    const reachableLabel = labelOf(afterTest(ATTIC, OUTCOMES[0]));
    expect(rowShows(ATTIC.name, reachableLabel)).toBe(false);

    await testConnection(user, ATTIC.name);

    expect(rowShows(ATTIC.name, reachableLabel)).toBe(true);
    expect(reachableLabel).toMatch(/\breachable\b/i);
    expect(reachableLabel).not.toMatch(/unreachable|not\s+reachable|fail|error/i);
  });

  it("the store effect records nothing itself: the badge state comes from the re-loaded list — DoD-6", async () => {
    serveServers(EVERYONE, { outcome: "reachable" });
    const state = withRows(EVERYONE);
    await expect(testLlmServerConnection(state, ATTIC.id)).resolves.toBeUndefined();
    expect(toJS(state.rows)).toEqual([afterTest(ATTIC, OUTCOMES[0]), ORCHARD, CELLAR]);
    expect(state.testingId).toBeNull();
    expect(state.errorMessage).toBeNull();
  });

  it.each(FAILING_OUTCOMES)(
    "on a $outcome result the badge reports the failure and the row stays in the table — DoD-7 (US-013.AC-2, UC-011)",
    async (c) => {
      const user = newUser();
      await renderLoaded(EVERYONE, { outcome: c.outcome });
      const failLabel = labelOf(afterTest(ATTIC, c));
      const reachableLabel = labelOf(afterTest(ATTIC, OUTCOMES[0]));

      await testConnection(user, ATTIC.name);

      expect(bodyRows()).toHaveLength(3);
      rowFor(ATTIC.name);
      expect(rowShows(ATTIC.name, failLabel)).toBe(true);
      expect(rowShows(ATTIC.name, reachableLabel)).toBe(false);
      expect(alerts(), "a failing typed outcome is not a page error").toEqual([]);
    },
  );

  it("a failing result can be re-tested: the row keeps its menu — DoD-7 (US-013.AC-2)", async () => {
    const user = newUser();
    const { mock } = await renderLoaded(EVERYONE, { outcome: "unreachable" });
    await testConnection(user, ATTIC.name);
    await testConnection(user, ATTIC.name);
    const posts = seen(mock).filter((call) => call.method === "POST");
    expect(posts).toHaveLength(2);
  });
});

// ===========================================================================
describe("the last-test badge is derived by one pure helper", () => {
  it("the four typed outcomes map to four distinct labels — DoD-8", () => {
    const labels = OUTCOMES.map((c) => labelOf({ last_test_at: TESTED_AT, last_test_ok: c.ok, last_test_error: c.error }));
    for (const label of labels) {
      expect(typeof label).toBe("string");
      expect(label.trim().length).toBeGreaterThan(0);
    }
    expect(new Set(labels).size).toBe(4);
  });

  it("each label names its outcome in words — DoD-8", () => {
    const [reachable, unreachable, authFailed, listEmpty] = OUTCOMES.map((c) =>
      labelOf({ last_test_at: TESTED_AT, last_test_ok: c.ok, last_test_error: c.error }),
    );
    expect(reachable).toMatch(/\breachable\b/i);
    expect(reachable).not.toMatch(/unreachable|not\s+reachable/i);
    expect(unreachable).toMatch(/unreachable|not\s+reachable|can(?:no|')t\s+reach|unable\s+to\s+reach|offline|unavailable/i);
    expect(authFailed).toMatch(/auth|credential|\bkey\b|forbidden|denied|unauthori[sz]ed/i);
    expect(listEmpty).toMatch(/empty|no\s+models?/i);
  });

  it("a never-tested row gets its own rendering, distinct from all four outcomes — DoD-8", () => {
    const never = labelOf({ last_test_at: null, last_test_ok: null, last_test_error: null });
    const labels = OUTCOMES.map((c) => labelOf({ last_test_at: TESTED_AT, last_test_ok: c.ok, last_test_error: c.error }));
    expect(never.trim().length).toBeGreaterThan(0);
    expect(labels).not.toContain(never);
  });

  it("each badge carries a colour — DoD-8", () => {
    for (const c of OUTCOMES) {
      const badge = lastTestBadgeOf({ last_test_at: TESTED_AT, last_test_ok: c.ok, last_test_error: c.error });
      expect(typeof badge.color, c.outcome).toBe("string");
      expect(String(badge.color).length, c.outcome).toBeGreaterThan(0);
    }
  });

  it("the helper is pure: same answer twice, input untouched — DoD-8", () => {
    for (const c of OUTCOMES) {
      const input = Object.freeze({ last_test_at: TESTED_AT, last_test_ok: c.ok, last_test_error: c.error });
      const first = lastTestBadgeOf(input);
      const second = lastTestBadgeOf(input);
      expect(second).toEqual(first);
      expect(input).toEqual({ last_test_at: TESTED_AT, last_test_ok: c.ok, last_test_error: c.error });
    }
  });

  it("the page renders, for each row, the label the helper derives from that row — DoD-8", async () => {
    const names = ["Alder", "Birch", "Cedar", "Damson"];
    const rows: LlmServerRow[] = OUTCOMES.map((c, index) => ({
      ...ORCHARD,
      id: `734003200000030${index}`,
      name: names[index],
      last_test_at: TESTED_AT,
      last_test_ok: c.ok,
      last_test_error: c.error,
    }));
    await renderLoaded(rows);
    expect(spied.badge.length).toBeGreaterThan(0);
    const shown = rows.map((row) => labelOf(row));
    rows.forEach((row, index) => {
      expect(rowShows(row.name, shown[index]), row.name).toBe(true);
      for (const [other, label] of shown.entries()) {
        if (other !== index) expect(rowShows(row.name, label), `${row.name} shows ${label}`).toBe(false);
      }
    });
  });

  it("the page component maps no outcome value itself — DoD-8", () => {
    const page = readSource(PAGE_SOURCE);
    for (const value of ["reachable", "unreachable", "auth_failed", "model_list_empty"]) {
      expect(page, value).not.toMatch(new RegExp(`["'\`]${value}["'\`]`));
    }
    expect(page).toMatch(/\blastTestBadgeOf\b/);
  });
});

// ===========================================================================
describe("a test that fails at the transport or with a typed error", () => {
  it("secret_ref_missing (500) renders its message in the page Alert and the table stays usable — DoD-9 (D14)", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded(EVERYONE, {
      override: (method, pathname) =>
        method === "POST" && TEST_PATH.test(pathname) ? Promise.resolve(secretMissingResponse()) : undefined,
    });

    await testConnection(user, ORCHARD.name);

    const alert = alertWith(SECRET_MESSAGE);
    expect(isBefore(alert, table())).toBe(true);
    expect(state.testingId).toBeNull();
    expect(bodyRows()).toHaveLength(3);
    for (const server of EVERYONE) rowFor(server.name);
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();

    await testConnection(user, ORCHARD.name);
    expect(seen(mock).filter((call) => call.method === "POST")).toHaveLength(2);
  });

  it("a transport failure renders an Alert, clears the in-progress marker and keeps the rows — DoD-9", async () => {
    const user = newUser();
    const { state } = await renderLoaded(EVERYONE, {
      override: (method) => (method === "POST" ? Promise.reject(new TypeError("Failed to fetch")) : undefined),
    });

    await testConnection(user, ATTIC.name);

    expect(alerts().length).toBeGreaterThan(0);
    expect(state.testingId).toBeNull();
    expect((state.errorMessage ?? "").length).toBeGreaterThan(0);
    expect(bodyRows()).toHaveLength(3);
    await openRowMenu(user, ATTIC.name);
  });

  it("the effect marks the row in progress while the request is in flight, then clears it — DoD-9", async () => {
    const pending = deferred<Response>();
    serveServers(EVERYONE, {
      override: (method) => (method === "POST" ? pending.promise : undefined),
    });
    const state = withRows(EVERYONE);
    const running = testLlmServerConnection(state, CELLAR.id);
    await settle();
    expect(state.testingId).toBe(CELLAR.id);

    pending.resolve(secretMissingResponse());
    await expect(running).resolves.toBeUndefined();
    expect(state.testingId).toBeNull();
    expect(state.errorMessage).toEqual(expect.stringContaining(SECRET_MESSAGE));
    expect(toJS(state.rows)).toEqual(EVERYONE);
  });

  it("a successful test also clears the in-progress marker — DoD-9", async () => {
    serveServers(EVERYONE);
    const state = withRows(EVERYONE);
    await testLlmServerConnection(state, ATTIC.id);
    expect(state.testingId).toBeNull();
  });
});

// ===========================================================================
describe("delete is confirmed", () => {
  it("choosing Delete opens the shared confirm and issues no request — DoD-10", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    const before = mock.mock.calls.length;

    const dialog = await openDeleteConfirm(user, ATTIC.name);
    expect(within(dialog).getByRole("button", { name: CONFIRM_DELETE })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: CANCEL_NAME })).toBeInTheDocument();
    await flush();
    expect(mock.mock.calls.length).toBe(before);
    expect(spied.del).toEqual([]);
  });

  it("cancelling issues no request, closes the confirm and leaves the row — DoD-10", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    const before = seen(mock);

    const dialog = await openDeleteConfirm(user, ATTIC.name);
    await closeDialog(user, dialog);
    await flush();

    expect(seen(mock)).toEqual(before);
    expect(bodyRows()).toHaveLength(3);
    rowFor(ATTIC.name);
    expect(spied.del).toEqual([]);
  });

  it("confirming issues the DELETE for that row and then re-loads the list — DoD-10", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();

    const dialog = await openDeleteConfirm(user, ORCHARD.name);
    await user.click(within(dialog).getByRole("button", { name: CONFIRM_DELETE }));
    await flush();

    const calls = seen(mock);
    expect(calls.filter((call) => call.method !== "GET")).toEqual([
      { method: "DELETE", path: `${LIST_PATH}/${ORCHARD.id}`, search: "" },
    ]);
    expect(laterListLoads(calls, "DELETE").length).toBeGreaterThan(0);
    expect(spied.del).toHaveLength(1);
    expect(spied.del[0][0]).toBe(state);
    expect(spied.del[0][1]).toBe(ORCHARD.id);
  });

  it("after confirming the confirm closes and the row is gone — DoD-10", async () => {
    const user = newUser();
    await renderLoaded();

    const dialog = await openDeleteConfirm(user, ORCHARD.name);
    await user.click(within(dialog).getByRole("button", { name: CONFIRM_DELETE }));
    await flush();

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(bodyRows()).toHaveLength(2);
    expect(findRow(ORCHARD.name)).toBeUndefined();
    rowFor(ATTIC.name);
    rowFor(CELLAR.name);
  });

  it("the page reuses the shared ConfirmModal rather than hand-rolling one — DoD-10", () => {
    const specs = importSpecifiers(readFileSync(PAGE_SOURCE, "utf8"));
    expect(specs.some((spec) => /(^|\/)shared\/ConfirmModal$/.test(spec))).toBe(true);
    expect(readSource(PAGE_SOURCE)).toMatch(/<ConfirmModal\b/);
  });

  it("deleteLlmServer DELETEs then re-loads; the rows come from the re-load — DoD-10", async () => {
    const { mock, rows } = serveServers(EVERYONE);
    const state = withRows(EVERYONE);
    const newcomer: LlmServerRow = { ...CELLAR, id: "7340032000000299", name: "Newcomer rig" };
    rows.push({ ...newcomer });
    await expect(deleteLlmServer(state, ATTIC.id)).resolves.toBeUndefined();
    const calls = seen(mock);
    expect(calls[0]).toEqual({ method: "DELETE", path: `${LIST_PATH}/${ATTIC.id}`, search: "" });
    expect(calls.slice(1)).toEqual([{ method: "GET", path: LIST_PATH, search: "" }]);
    expect(toJS(state.rows)).toEqual([ORCHARD, CELLAR, newcomer]);
  });
});

// ===========================================================================
describe("R5 — no count and nothing about another user's data", () => {
  it("the confirm contains no digit, no number word and nothing about sessions, users or their data — DoD-11 (R5, UC-012)", async () => {
    const user = newUser();
    await renderLoaded();
    for (const server of EVERYONE) {
      const dialog = await openDeleteConfirm(user, server.name);
      const text = dialog.textContent ?? "";
      expect(text, server.name).not.toMatch(/\d/);
      expect(text, server.name).not.toMatch(NUMBER_WORDS);
      expect(text, server.name).not.toMatch(OTHER_USERS_DATA);
      await closeDialog(user, dialog);
    }
  });

  it("the confirm describes the action: the registration and its enabled models go, for good — DoD-11", async () => {
    const user = newUser();
    await renderLoaded();
    const dialog = await openDeleteConfirm(user, ATTIC.name);
    const text = dialog.textContent ?? "";
    expect(text).toMatch(/model/i);
    expect(text).toMatch(/cannot be (restored|undone)|can't be (restored|undone)|not be (restored|undone)|irreversib|permanent/i);
  });

  it("the page renders no count of user-owned things even if the payload carried one — DoD-11 (UC-065, UC-066)", async () => {
    await renderLoaded(
      EVERYONE.map((row) => ({
        ...row,
        session_count: 4817,
        user_count: 9253,
        character_count: 6031,
        sessions_using: 7719,
      })),
    );
    const text = readableText();
    for (const count of ["4817", "9253", "6031", "7719"]) {
      expect(text).not.toContain(count);
    }
    expect(text).not.toMatch(OTHER_USERS_DATA);
  });

  it("the open row menu names nothing about sessions, users or their data — DoD-11", async () => {
    const user = newUser();
    await renderLoaded();
    await openRowMenu(user, ATTIC.name);
    await screen.findByRole("menuitem", { name: DELETE_ITEM });
    expect(readableText()).not.toMatch(OTHER_USERS_DATA);
  });
});

// ===========================================================================
describe("mutations are never optimistic", () => {
  it("a delete whose request fails leaves the row rendered and puts the failure in the Alert — DoD-12", async () => {
    const user = newUser();
    await renderLoaded(EVERYONE, {
      override: (method) => (method === "DELETE" ? Promise.resolve(failureResponse()) : undefined),
    });

    const dialog = await openDeleteConfirm(user, ORCHARD.name);
    await user.click(within(dialog).getByRole("button", { name: CONFIRM_DELETE }));
    await flush();

    const alert = alertWith(FAILURE_MESSAGE);
    expect(isBefore(alert, table())).toBe(true);
    expect(bodyRows()).toHaveLength(3);
    rowFor(ORCHARD.name);
    expect(notificationRoots()).toEqual([]);
  });

  it("the row stays rendered while the DELETE is in flight — DoD-12", async () => {
    const user = newUser();
    const pending = deferred<Response>();
    await renderLoaded(EVERYONE, { override: (method) => (method === "DELETE" ? pending.promise : undefined) });

    const dialog = await openDeleteConfirm(user, ORCHARD.name);
    await user.click(within(dialog).getByRole("button", { name: CONFIRM_DELETE }));
    await flush();
    expect(bodyRows()).toHaveLength(3);
    rowFor(ORCHARD.name);

    pending.resolve(new Response(null, { status: 204 }));
    await flush();
  });

  it("the badge does not change while the test request is in flight — DoD-12", async () => {
    const user = newUser();
    const pending = deferred<Response>();
    await renderLoaded(EVERYONE, { override: (method) => (method === "POST" ? pending.promise : undefined) });
    const neverLabel = labelOf(ATTIC);
    const reachableLabel = labelOf(afterTest(ATTIC, OUTCOMES[0]));

    await testConnection(user, ATTIC.name);
    expect(rowShows(ATTIC.name, neverLabel)).toBe(true);
    expect(rowShows(ATTIC.name, reachableLabel)).toBe(false);

    pending.resolve(jsonResponse({ outcome: "reachable", ok: true, tested_at: TESTED_AT }, 200));
    await flush();
  });

  it("the store writes no row while a delete or a test is in flight, and a failed delete keeps them — DoD-12", async () => {
    const pending = deferred<Response>();
    serveServers(EVERYONE, { override: (method) => (method !== "GET" ? pending.promise : undefined) });
    const state = withRows(EVERYONE);
    const running = deleteLlmServer(state, ORCHARD.id);
    await settle();
    expect(toJS(state.rows)).toEqual(EVERYONE);
    pending.resolve(failureResponse());
    await expect(running).resolves.toBeUndefined();
    expect(toJS(state.rows)).toEqual(EVERYONE);
    expect(state.errorMessage).toEqual(expect.stringContaining(FAILURE_MESSAGE));
  });
});

// ===========================================================================
describe("no success notification anywhere", () => {
  it("loading, testing and deleting successfully raise no notification and no Alert — DoD-13", async () => {
    const user = newUser();
    await renderLoaded(EVERYONE, { outcome: "reachable" });
    expect(notificationRoots()).toEqual([]);

    await testConnection(user, ATTIC.name);
    expect(notificationRoots()).toEqual([]);
    expect(alerts()).toEqual([]);

    const dialog = await openDeleteConfirm(user, CELLAR.name);
    await user.click(within(dialog).getByRole("button", { name: CONFIRM_DELETE }));
    await flush();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(notificationRoots()).toEqual([]);
    expect(alerts()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("a failing typed outcome raises no notification either — DoD-13", async () => {
    const user = newUser();
    await renderLoaded(EVERYONE, { outcome: "auth_failed" });
    await testConnection(user, ORCHARD.name);
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ===========================================================================
describe("the row overflow menu", () => {
  it("each row has exactly one icon-only control, in its last cell, named for its registration — DoD-14", async () => {
    await renderLoaded();
    const names: string[] = [];
    for (const server of EVERYONE) {
      const row = rowFor(server.name);
      const controls = iconOnlyControls(row);
      expect(controls, server.name).toHaveLength(1);
      const cells = cellsOf(row);
      expect(cells[cells.length - 1].contains(controls[0]), `${server.name}: trigger in the trailing cell`).toBe(true);
      expect(controls[0]).toHaveAccessibleName(new RegExp(escapeRegExp(server.name)));
      names.push(controls[0].getAttribute("aria-label") ?? "");
    }
    expect(new Set(names).size).toBe(EVERYONE.length);
  });

  it("the trigger opens a menu offering Test connection and Delete, none disabled — DoD-14", async () => {
    const user = newUser();
    await renderLoaded();
    const menu = await openRowMenu(user, ATTIC.name);
    expect(await within(menu).findByRole("menuitem", { name: TEST_ITEM })).toBeInTheDocument();
    expect(within(menu).getByRole("menuitem", { name: DELETE_ITEM })).toBeInTheDocument();
    for (const item of within(menu).getAllByRole("menuitem")) {
      expect((item.textContent ?? "").trim().length).toBeGreaterThan(0);
      expect(item.hasAttribute("disabled"), item.textContent ?? "").toBe(false);
      expect(item.hasAttribute("data-disabled"), item.textContent ?? "").toBe(false);
      expect(item.getAttribute("aria-disabled"), item.textContent ?? "").not.toBe("true");
    }
  });

  it("the trigger is IconDots routed through shared/IconButton, in a w={60} column — DoD-14", () => {
    const source = readSource(PAGE_SOURCE);
    const specs = importSpecifiers(readFileSync(PAGE_SOURCE, "utf8"));
    expect(specs.some((spec) => /(^|\/)shared\/IconButton$/.test(spec))).toBe(true);
    expect(source).toMatch(/\bIconDots\b/);
    expect(source).toMatch(/<IconButton\b[\s\S]{0,400}?\bicon\s*=\s*\{\s*IconDots\s*\}/);
    expect(source).toMatch(/<Menu\b/);
    expect(source).toMatch(/\bw\s*=\s*\{\s*60\s*\}/);
    expect(source).not.toMatch(/\bActionIcon\b/);
  });
});

// ===========================================================================
describe("no sorting, filtering or pagination", () => {
  it("the headers carry no sort control and the page no filter input or pagination — DoD-15", async () => {
    await renderLoaded();
    const head = table().querySelector("thead");
    expect(head).not.toBeNull();
    expect(head?.querySelectorAll("button, [role='button'], [aria-sort]").length).toBe(0);
    expect(screen.queryAllByRole("textbox")).toEqual([]);
    expect(screen.queryAllByRole("searchbox")).toEqual([]);
    expect(screen.queryAllByRole("combobox")).toEqual([]);
    expect(document.querySelectorAll(".mantine-Pagination-root").length).toBe(0);
  });

  it("no request the page sends carries a query parameter — DoD-15", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    await testConnection(user, ATTIC.name);
    const dialog = await openDeleteConfirm(user, CELLAR.name);
    await user.click(within(dialog).getByRole("button", { name: CONFIRM_DELETE }));
    await flush();

    const calls = seen(mock);
    expect(calls.length).toBeGreaterThan(3);
    for (const call of calls) {
      const allowed =
        (call.method === "GET" && call.path === LIST_PATH) ||
        (call.method === "POST" && TEST_PATH.test(call.path)) ||
        (call.method === "DELETE" && DELETE_PATH.test(call.path));
      expect(allowed, `${call.method} ${call.path}`).toBe(true);
      expect(call.search, `${call.method} ${call.path}`).toBe("");
    }
  });

  it("the page uses a plain Mantine Table and no data-table library or pagination — DoD-15", () => {
    const source = readSource(PAGE_SOURCE);
    const specs = importSpecifiers(readFileSync(PAGE_SOURCE, "utf8"));
    expect(source).toMatch(/<Table\b/);
    expect(specs.filter((spec) => /datatable|react-table|ag-grid|data-grid/i.test(spec))).toEqual([]);
    expect(source).not.toMatch(/\bPagination\b/);
  });
});

// ===========================================================================
describe("the store is a data class; effects are free functions", () => {
  it("the class prototype carries no method and no getter — DoD-16", () => {
    expect(Object.getOwnPropertyNames(LlmServersPageState.prototype)).toEqual(["constructor"]);
  });

  it("rows, status, errorMessage and testingId are the observable fields, none computed — DoD-16", () => {
    const state = new LlmServersPageState();
    const observed = Object.getOwnPropertyNames(state).filter((name) => isObservableProp(state, name));
    expect(observed.sort()).toEqual(["errorMessage", "rows", "status", "testingId"]);
    const record = state as unknown as Record<string, unknown>;
    for (const name of Object.getOwnPropertyNames(state)) {
      expect(typeof record[name], `own property ${name}`).not.toBe("function");
      expect(isComputedProp(state, name), `own property ${name}`).toBe(false);
    }
  });

  it("a fresh store is idle, with no rows, no error and nothing in progress — DoD-16", () => {
    expect(snapshot(new LlmServersPageState())).toEqual({ rows: [], status: "idle", errorMessage: null, testingId: null });
  });

  it("holds no modal open flag and no modal target — DoD-16", () => {
    const names = Object.getOwnPropertyNames(new LlmServersPageState());
    expect(names.filter((name) => /open|modal|confirm|target|dialog|delet/i.test(name))).toEqual([]);
  });

  it("the page calls the free functions with its store first — DoD-16", async () => {
    const user = newUser();
    const { state } = await renderLoaded();
    expect(spied.load.length).toBeGreaterThan(0);
    expect(spied.load[0][0]).toBe(state);
    const signal = spied.load[0][1] as AbortSignal | undefined;
    expect(signal).toBeTruthy();
    expect(typeof signal?.aborted).toBe("boolean");

    await testConnection(user, ATTIC.name);
    expect(spied.test).toHaveLength(1);
    expect(spied.test[0][0]).toBe(state);
    expect(spied.test[0][1]).toBe(ATTIC.id);
  });

  it("the confirm's open flag and target are not store fields: opening it changes nothing in the store — DoD-16", async () => {
    const user = newUser();
    const { state } = await renderLoaded();
    const before = { names: Object.getOwnPropertyNames(state).sort(), snap: snapshot(state) };
    await openDeleteConfirm(user, ATTIC.name);
    expect({ names: Object.getOwnPropertyNames(state).sort(), snap: snapshot(state) }).toEqual(before);
  });

  it("every effect writes only inside actions (strict MobX raises no warning) — DoD-16", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    configure({ enforceActions: "always" });
    try {
      const run = async (options: ServeOptions) => {
        serveServers(EVERYONE, options);
        const state = new LlmServersPageState();
        const dispose = autorun(() => {
          void state.rows.length;
          void state.status;
          void state.errorMessage;
          void state.testingId;
        });
        await loadLlmServers(state);
        await testLlmServerConnection(state, ATTIC.id);
        await deleteLlmServer(state, ORCHARD.id);
        dispose();
        vi.unstubAllGlobals();
      };
      await run({ outcome: "reachable" });
      await run({ override: (method) => (method !== "GET" ? Promise.resolve(failureResponse()) : undefined) });
      await run({ override: () => Promise.resolve(failureResponse()) });
    } finally {
      configure({ enforceActions: "observed" });
    }
    const mobxWarnings = warn.mock.calls.filter((args) => args.some((arg) => String(arg).includes("[MobX]")));
    expect(mobxWarnings).toEqual([]);
  });

  it.each<[string, (state: LlmServersPageState, signal: AbortSignal) => Promise<void>]>([
    ["loadLlmServers", (state, signal) => loadLlmServers(state, signal)],
    ["deleteLlmServer", (state, signal) => deleteLlmServer(state, ATTIC.id, signal)],
    ["testLlmServerConnection", (state, signal) => testLlmServerConnection(state, ATTIC.id, signal)],
  ])("%s given an already-aborted signal writes nothing — DoD-16", async (_name, run) => {
    serveServers(EVERYONE);
    const fresh = new LlmServersPageState();
    const loaded = withRows(EVERYONE);
    for (const state of [fresh, loaded]) {
      const before = snapshot(state);
      const controller = new AbortController();
      controller.abort();
      await expect(run(state, controller.signal)).resolves.toBeUndefined();
      await settle();
      expect(snapshot(state)).toEqual(before);
    }
  });

  it("a response arriving after the abort is not written — DoD-16", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = new LlmServersPageState();
    const controller = new AbortController();
    const running = loadLlmServers(state, controller.signal);
    await settle();
    const atAbort = snapshot(state);
    controller.abort();
    pending.resolve(jsonResponse({ servers: copyRows(EVERYONE) }, 200));
    await running;
    await settle();
    expect(snapshot(state)).toEqual(atAbort);
    expect(state.rows).toEqual([]);
  });

  it("the store is created with useState(() => new …), never useMemo — DoD-16", () => {
    const page = readSource(PAGE_SOURCE);
    const app = readSource(ADMIN_APP_SOURCE);
    expect(`${page}\n${app}`).toMatch(/useState\s*\(\s*\(\s*\)\s*=>\s*new\s+LlmServersPageState\s*\(/);
    expect(page).not.toMatch(/\buseMemo\b/);
    expect(app).not.toMatch(/\buseMemo\b/);
    expect(readSource(STATE_SOURCE)).toMatch(/\brunInAction\b/);
  });
});

// ===========================================================================
describe("unmounting", () => {
  it("aborts the in-flight load — DoD-17", async () => {
    const pending = deferred<Response>();
    const mock = stubFetch(() => pending.promise);
    const { view } = renderPage();
    await flush();

    expect(mock).toHaveBeenCalledTimes(1);
    const signal = mock.mock.calls[0][1]?.signal;
    expect(signal).toBeTruthy();
    expect(signal?.aborted).toBe(false);

    view.unmount();
    expect(signal?.aborted).toBe(true);
    pending.resolve(jsonResponse({ servers: copyRows(EVERYONE) }, 200));
    await flush();
  });

  it("no store write happens after the unmount — DoD-17", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const { view, state } = renderPage();
    await flush();
    const atUnmount = snapshot(state);

    view.unmount();
    pending.resolve(jsonResponse({ servers: copyRows(EVERYONE) }, 200));
    await flush();

    expect(snapshot(state)).toEqual(atUnmount);
    expect(state.rows).toEqual([]);
  });
});

// ===========================================================================
describe("the /llm-servers route", () => {
  const answerRoutes: FetchFn = (input, init) => {
    const method = requestMethod(input, init);
    const pathname = requestUrl(input).pathname.replace(/\/+$/, "");
    if (method === "GET" && pathname === USERS_LIST_PATH) return Promise.resolve(jsonResponse({ users: [] }, 200));
    if (method === "GET" && pathname === LIST_PATH) return Promise.resolve(jsonResponse({ servers: [] }, 200));
    return new Promise<Response>(() => {});
  };

  async function renderApp(initialPath: string) {
    const mock = stubFetch(answerRoutes);
    render(
      <AppProviders>
        <MemoryRouter initialEntries={[initialPath]}>
          <AdminApp />
        </MemoryRouter>
      </AppProviders>,
    );
    await flush();
    return mock;
  }

  function mainText(): string {
    return screen.getByRole("main").textContent ?? "";
  }

  it("/llm-servers renders this page, not the 404 — DoD-18", async () => {
    const mock = await renderApp("/llm-servers");
    expect(mainText()).not.toMatch(NOT_FOUND_TEXT);
    expect(seen(mock).filter((call) => call.path === LIST_PATH)).toEqual([
      { method: "GET", path: LIST_PATH, search: "" },
    ]);
    expect(screen.getByRole("main").querySelector("table")).not.toBeNull();
  });

  it("/ still renders the Users page — DoD-18", async () => {
    const mock = await renderApp("/");
    expect(mainText()).not.toMatch(NOT_FOUND_TEXT);
    expect(seen(mock).some((call) => call.method === "GET" && call.path === USERS_LIST_PATH)).toBe(true);
    expect(seen(mock).some((call) => call.path === LIST_PATH)).toBe(false);
  });

  // /database was the 404 when DoD-18 was written; 007/005 DoD-13 has since built it.
  // Its own content is 007's to assert — here only "it is not the LLM Servers page".
  it.each(["/nope"])("%s still renders the 404 element — DoD-18", async (pathname) => {
    const mock = await renderApp(pathname);
    expect(mainText()).toMatch(NOT_FOUND_TEXT);
    expect(seen(mock).some((call) => call.path === LIST_PATH)).toBe(false);
  });

  it("/database is not the LLM Servers page — DoD-18 (superseded in part by 007/005 DoD-13)", async () => {
    // answerRoutes leaves any /api/admin/database/... request unsettled, so nothing errors.
    const mock = await renderApp("/database");
    expect(seen(mock).some((call) => call.path === LIST_PATH)).toBe(false);
  });

  it("the <Routes> is still flat and four elements long, with no nested layout or Outlet — DoD-18", () => {
    const source = readSource(ADMIN_APP_SOURCE);
    expect(source.match(/<Route(?![A-Za-z])/g) ?? []).toHaveLength(4);
    const paths = Array.from(source.matchAll(/\bpath\s*=\s*\{?\s*["'`]([^"'`]+)["'`]/g), (m) => m[1]);
    expect([...paths].sort()).toEqual(["*", "/", "/database", "/llm-servers"]);
    expect(source, "every <Route> is self-closing — nothing nested").not.toMatch(/<\/Route>/);
    expect(source).not.toMatch(/\bOutlet\b/);
    const at = source.search(/\bpath\s*=\s*\{?\s*["'`]\/llm-servers["'`]/);
    expect(at).toBeGreaterThanOrEqual(0);
    const start = source.lastIndexOf("<Route", at);
    const next = source.indexOf("<Route", at);
    const segment = source.slice(start, next < 0 ? source.indexOf("</Routes>", at) : next);
    expect(segment).not.toMatch(/NotFoundPage/);
  });
});

// ===========================================================================
describe("no stylesheet in the admin area", () => {
  it("no file under src/admin is a stylesheet — DoD-19", () => {
    const offenders = walkFiles(ADMIN_SRC)
      .filter((file) => /\.(css|scss|sass|less|styl)$/i.test(file))
      .map(relative);
    expect(offenders).toEqual([]);
  });

  it("no module under src/admin imports a stylesheet — DoD-19", () => {
    const offenders = walkFiles(ADMIN_SRC)
      .filter((file) => /\.(ts|tsx)$/.test(file))
      .flatMap((file) =>
        importSpecifiers(readFileSync(file, "utf8"))
          .filter((spec) => /\.(css|scss|sass|less|styl)(\?.*)?$/i.test(spec) || /styled-components|@emotion/.test(spec))
          .map((spec) => `${relative(file)} imports ${spec}`),
      );
    expect(offenders).toEqual([]);
  });

  it("the page renders through Mantine props alone: no className and no style element — DoD-19", () => {
    const source = readSource(PAGE_SOURCE);
    expect(source).not.toMatch(/\bclassName\s*=/);
    expect(source).not.toMatch(/<style\b/);
  });
});
