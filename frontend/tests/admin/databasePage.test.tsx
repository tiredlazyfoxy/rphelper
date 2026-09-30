// Feature 007, step 005 — the Database page: its MobX store, the drift report table and its
// status badge (DoD-1..DoD-14). DoD-15, DoD-16 and DoD-17 are [manual/live].
//
// Expected behaviour comes from the step's Interface intent and DoD, 005.context.md and
// context.md (D1 compared set, D2 three statuses, D9 route surface, D11 badge colours, D13 MobX
// rules, R5, failures render in place, no stylesheet). Bindings come from the frozen
// `### Step 005` record (and `### Step 006`'s one added store field, `applyingTable`, which these
// tests tolerate but never require): the page takes the store as a prop, so tests construct
// `new DatabasePageState()` and render `<DatabasePage state={...} />` under `AppProviders` +
// `MemoryRouter`. `fetch` is stubbed per test. `notifyFailure` is mocked at file level. The store
// module is wrapped pass-through so the page's calls to its free functions are observable —
// behaviour unchanged.
//
// Recognition conventions (from spec wording, for the verifier):
// - Loader: `.mantine-Loader-root`. Table: the `<table>`; rows `tbody tr`; headers `thead th`.
//   Inline error: Mantine `Alert`, `role="alert"`. Notifications: `.mantine-Notification-root`.
//   Status badge: `.mantine-Badge-root` inside the row.
// - Header columns are found by their words: Table, Status, Columns, Indexes.
// - A cell "renders the helper's text" when its whitespace-stripped text contains the helper's
//   whitespace-stripped string (the component may break the text across elements).
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { act, render, screen } from "@testing-library/react";
import { autorun, configure, isComputedProp, isObservableProp, runInAction, toJS } from "mobx";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AdminApp } from "../../src/admin/AdminApp";
import { DatabasePage } from "../../src/admin/DatabasePage";
import {
  type ChangedColumn,
  differencesSummaryOf,
  DRIFT_REPORT_PATH,
  DatabasePageState,
  type DriftTableRow,
  loadDriftReport,
  statusBadgeOf,
  type TableStatus,
} from "../../src/admin/databasePageState";
import { AppProviders } from "../../src/shared/AppProviders";

const { notifyFailureSpy, spied } = vi.hoisted(() => ({
  notifyFailureSpy: vi.fn(),
  spied: {
    load: [] as unknown[][],
    badge: [] as unknown[][],
    summary: [] as unknown[][],
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
    statusBadgeOf: (...args: Parameters<typeof actual.statusBadgeOf>) => {
      spied.badge.push(args);
      return actual.statusBadgeOf(...args);
    },
    differencesSummaryOf: (...args: Parameters<typeof actual.differencesSummaryOf>) => {
      spied.summary.push(args);
      return actual.differencesSummaryOf(...args);
    },
  };
});

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type WireRow = Record<string, unknown>;

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const ADMIN_SRC = path.join(FRONTEND_ROOT, "src", "admin");
const STATE_SOURCE = path.join(ADMIN_SRC, "databasePageState.ts");
const PAGE_SOURCE = path.join(ADMIN_SRC, "DatabasePage.tsx");
const ADMIN_APP_SOURCE = path.join(ADMIN_SRC, "AdminApp.tsx");
const PAGE_MODULES = [STATE_SOURCE, PAGE_SOURCE];

/** context.md D9 — the report route. */
const REPORT_PATH = "/api/admin/database/tables";
const USERS_LIST_PATH = "/api/admin/users";
const LLM_LIST_PATH = "/api/admin/llm-servers";
const FAILURE_MESSAGE = "The drift report is on fire zq-71.";

const NOTIFICATION_ROOT = ".mantine-Notification-root";
const LOADER = ".mantine-Loader-root";
const BADGE = ".mantine-Badge-root";
const NOT_FOUND_TEXT = /not found|does not exist|doesn't exist|no such page|404/i;
const TABLE_HEADER = /^\s*tables?\s*$/i;
const STATUS_HEADER = /\bstatus\b/i;
const COLUMNS_HEADER = /\bcolumns\b/i;
const INDEXES_HEADER = /\bindex(es)?\b/i;
/** R5 — a digit-bearing claim about user-owned material. */
const COUNT_CLAIM =
  /\d[\d,.\s]*\s*(rows?|records?|sessions?|characters?|setups?|messages?|memos?|users?|entries)\b/i;
const BYTE_SIZE = /\d[\d,.\s]*\s*(bytes?|[kmgt]i?b)\b/i;
const ISO_DATE = /\d{4}-\d{2}-\d{2}/;
/** DoD-10 — whole words (with plain inflections) only, so a substring such as CSS `!important` never counts. */
const OUT_OF_SCOPE_CONTROL = /\b(export|import|rebuild|re-?index)(s|ed|ing)?\b/i;

// ---------------------------------------------------------------- fixtures (no digit anywhere)

const IN_SYNC_ROW: DriftTableRow = {
  table_name: "users",
  status: "in_sync",
  missing_columns: [],
  extra_columns: [],
  changed_columns: [],
  missing_indexes: [],
  extra_indexes: [],
};

const TYPE_CHANGE: ChangedColumn = {
  name: "base_url",
  expected: { name: "base_url", type_text: "TEXT", not_null: true },
  actual: { name: "base_url", type_text: "BLOB", not_null: true },
};

const NULLABILITY_CHANGE: ChangedColumn = {
  name: "kind",
  expected: { name: "kind", type_text: "TEXT", not_null: true },
  actual: { name: "kind", type_text: "TEXT", not_null: false },
};

const DRIFTED_ROW: DriftTableRow = {
  table_name: "llm_servers",
  status: "drifted",
  missing_columns: ["nickname"],
  extra_columns: ["legacy_flag"],
  changed_columns: [TYPE_CHANGE, NULLABILITY_CHANGE],
  missing_indexes: [{ columns: ["owner_ref", "display_name"], unique: false }],
  extra_indexes: [{ columns: ["legacy_flag"], unique: true }],
};

const MISSING_ROW: DriftTableRow = {
  table_name: "models",
  status: "missing",
  missing_columns: [],
  extra_columns: [],
  changed_columns: [],
  missing_indexes: [],
  extra_indexes: [],
};

const REPORT: DriftTableRow[] = [IN_SYNC_ROW, DRIFTED_ROW, MISSING_ROW];

const EMPTY_DIFFERENCES = {
  missing_columns: [] as string[],
  extra_columns: [] as string[],
  changed_columns: [] as ChangedColumn[],
  missing_indexes: [] as DriftTableRow["missing_indexes"],
  extra_indexes: [] as DriftTableRow["extra_indexes"],
};

beforeEach(() => {
  notifyFailureSpy.mockClear();
  spied.load.length = 0;
  spied.badge.length = 0;
  spied.summary.length = 0;
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

function copyRows(rows: readonly WireRow[]): WireRow[] {
  return JSON.parse(JSON.stringify(rows)) as WireRow[];
}

/** Answers `GET /api/admin/database/tables` with the given rows; anything else 404s. */
function serveReport(rows: readonly WireRow[] = REPORT) {
  return stubFetch((input, init) => {
    const method = requestMethod(input, init);
    const pathname = requestUrl(input).pathname;
    if (method === "GET" && pathname === REPORT_PATH) {
      return Promise.resolve(jsonResponse({ tables: copyRows(rows) }, 200));
    }
    return Promise.resolve(jsonResponse({ error: { code: "not_found", message: "no such route", detail: {} } }, 404));
  });
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

/** Every own field of the store, deep-copied — tolerant of fields later steps add. */
function snapshot(state: DatabasePageState): Record<string, unknown> {
  const record = state as unknown as Record<string, unknown>;
  return Object.fromEntries(Object.getOwnPropertyNames(state).map((name) => [name, toJS(record[name])]));
}

function readyWith(rows: readonly DriftTableRow[]): DatabasePageState {
  const state = new DatabasePageState();
  runInAction(() => {
    state.rows = copyRows(rows as unknown as WireRow[]) as unknown as DriftTableRow[];
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

async function renderLoaded(rows: readonly WireRow[] = REPORT) {
  const mock = serveReport(rows);
  const rendered = renderPage();
  await flush();
  return { mock, ...rendered };
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

function rowFor(name: string): HTMLTableRowElement {
  const matches = bodyRows().filter((tr) => cellsOf(tr).some((td) => (td.textContent ?? "").trim() === name));
  expect(matches, `rows showing ${name}`).toHaveLength(1);
  return matches[0];
}

function rowNames(): (string | undefined)[] {
  return bodyRows().map(
    (tr) => REPORT.find((row) => cellsOf(tr).some((td) => (td.textContent ?? "").trim() === row.table_name))?.table_name,
  );
}

function columnIndex(pattern: RegExp): number {
  const indexes = headerTexts()
    .map((text, index) => (pattern.test(text) ? index : -1))
    .filter((index) => index >= 0);
  expect(indexes, `header columns matching ${pattern}`).toHaveLength(1);
  return indexes[0];
}

function cellText(name: string, header: RegExp): string {
  return (cellsOf(rowFor(name))[columnIndex(header)].textContent ?? "").trim();
}

function squash(text: string): string {
  return text.replace(/\s+/g, "");
}

function badgesIn(tr: HTMLTableRowElement): HTMLElement[] {
  return Array.from(tr.querySelectorAll<HTMLElement>(BADGE));
}

function badgeOf(name: string): HTMLElement {
  const badges = badgesIn(rowFor(name));
  expect(badges, `status badges in ${name}'s row`).toHaveLength(1);
  return badges[0];
}

/** Inline style text of the badge and everything inside it (Mantine carries colour as CSS variables). */
function badgeStyle(badge: HTMLElement): string {
  return [badge, ...Array.from(badge.querySelectorAll("*"))].map((el) => el.getAttribute("style") ?? "").join(";");
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

const NAMING_ATTRIBUTES = ["aria-label", "title", "aria-description", "placeholder", "alt", "aria-valuetext"];

function attributeTexts(): string[] {
  return Array.from(document.body.querySelectorAll("*")).flatMap((el) =>
    NAMING_ATTRIBUTES.map((name) => el.getAttribute(name) ?? "").filter(Boolean),
  );
}

/** Elements whose text content is never shown to a person (e.g. the providers' injected CSS). */
const NON_RENDERED = "style, script, noscript, template";

function isRenderedTextNode(node: Node): boolean {
  const parent = node.parentElement;
  return parent === null || parent.closest(NON_RENDERED) === null;
}

/** The text nodes under `root` that a person can see — style/script contents excluded. */
function renderedTextNodesOf(root: Node): string[] {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) => (isRenderedTextNode(node) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT),
  });
  const out: string[] = [];
  for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) out.push(node.textContent ?? "");
  return out;
}

/** The visible text of an element: its textContent minus any non-rendered descendants. */
function renderedTextOf(root: Node): string {
  return renderedTextNodesOf(root).join("");
}

function textNodes(): string[] {
  return renderedTextNodesOf(document.body)
    .map((text) => text.trim())
    .filter(Boolean);
}

/** Everything a person reads, as separate pieces so neighbouring cells never glue together. */
function readablePieces(): string[] {
  const blocks = Array.from(document.body.querySelectorAll("td, th, h1, h2, h3, h4, p, [role='alert']"))
    .filter((el) => el.closest(NON_RENDERED) === null)
    .map((el) => renderedTextOf(el).trim());
  return [...blocks, ...textNodes(), ...attributeTexts()];
}

/** All visible text on the page plus the naming attributes — never the contents of style/script elements. */
function readableText(): string {
  return [renderedTextOf(document.body), ...attributeTexts()].join("\n");
}

function controls(container: ParentNode = document.body): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      "button, a[href], [role='button'], [role='menuitem'], input, select, textarea",
    ),
  );
}

function controlName(el: HTMLElement): string {
  return [renderedTextOf(el), ...NAMING_ATTRIBUTES.map((name) => el.getAttribute(name) ?? "")].join(" ");
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
describe("on mount the page loads the report and renders one row per table", () => {
  it("issues exactly one request, a GET of the report route with no query — DoD-1 (UC-014)", async () => {
    const { mock } = await renderLoaded();
    expect(seen(mock)).toEqual([{ method: "GET", path: REPORT_PATH, search: "" }]);
  });

  it("the report route constant is the D9 path — DoD-1", () => {
    expect(DRIFT_REPORT_PATH).toBe(REPORT_PATH);
  });

  it("renders one row per table, in the order the response gives — DoD-1 (US-017.AC-1)", async () => {
    await renderLoaded();
    expect(bodyRows()).toHaveLength(3);
    expect(rowNames()).toEqual(["users", "llm_servers", "models"]);
  });

  it("the order is the response's, not a sorted one — DoD-1 (US-017.AC-1)", async () => {
    await renderLoaded([MISSING_ROW, IN_SYNC_ROW, DRIFTED_ROW]);
    expect(rowNames()).toEqual(["models", "users", "llm_servers"]);
  });

  it("each row shows its table name and its status — DoD-1 (US-017.AC-1)", async () => {
    await renderLoaded();
    for (const row of REPORT) {
      expect(cellText(row.table_name, TABLE_HEADER), row.table_name).toBe(row.table_name);
      const statusCell = cellText(row.table_name, STATUS_HEADER);
      expect(squash(statusCell), row.table_name).toContain(squash(statusBadgeOf(row).label));
    }
  });

  it("the load puts the response's rows into the store verbatim and the status at ready — DoD-1", async () => {
    serveReport();
    const state = new DatabasePageState();
    await expect(loadDriftReport(state)).resolves.toBeUndefined();
    expect(toJS(state.rows)).toEqual(REPORT);
    expect(state.status).toBe("ready");
    expect(state.errorMessage).toBeNull();
  });
});

// ===========================================================================
describe("the status badge carries the status word", () => {
  it("the helper's labels are the three status words — DoD-2 (US-017.AC-1)", () => {
    expect(statusBadgeOf({ status: "in_sync" }).label).toMatch(/\bin[\s_-]*sync\b/i);
    expect(statusBadgeOf({ status: "missing" }).label).toMatch(/\bmissing\b/i);
    expect(statusBadgeOf({ status: "drifted" }).label).toMatch(/\bdrifted\b/i);
  });

  it("the three labels are distinct — DoD-2", () => {
    const statuses: TableStatus[] = ["in_sync", "missing", "drifted"];
    const labels = statuses.map((status) => statusBadgeOf({ status }).label.trim().toLowerCase());
    expect(new Set(labels).size).toBe(3);
  });

  it("each row renders one badge whose text is its status word — DoD-2 (US-017.AC-1)", async () => {
    await renderLoaded();
    expect((badgeOf("users").textContent ?? "").trim()).toMatch(/^in[\s_-]*sync$/i);
    expect((badgeOf("models").textContent ?? "").trim()).toMatch(/^missing$/i);
    expect((badgeOf("llm_servers").textContent ?? "").trim()).toMatch(/^drifted$/i);
  });

  it("the three rendered badges read differently, so the status is legible without colour — DoD-2", async () => {
    await renderLoaded();
    const texts = REPORT.map((row) => (badgeOf(row.table_name).textContent ?? "").trim().toLowerCase());
    expect(new Set(texts).size).toBe(3);
    for (const text of texts) expect(text.length).toBeGreaterThan(0);
  });
});

// ===========================================================================
describe("the badge colours come from the pure helper", () => {
  it("in sync is green, drifted is yellow, missing is red — DoD-3 (D11)", () => {
    expect(statusBadgeOf({ status: "in_sync" }).color).toBe("green");
    expect(statusBadgeOf({ status: "drifted" }).color).toBe("yellow");
    expect(statusBadgeOf({ status: "missing" }).color).toBe("red");
  });

  it("the helper is pure: same answer twice, input untouched — DoD-3", () => {
    for (const status of ["in_sync", "missing", "drifted"] as TableStatus[]) {
      const input = Object.freeze({ status });
      const first = statusBadgeOf(input);
      expect(statusBadgeOf(input)).toEqual(first);
      expect(input).toEqual({ status });
    }
  });

  it("the helper reads only the status: other row content does not change the badge — DoD-3", () => {
    expect(statusBadgeOf(DRIFTED_ROW)).toEqual(statusBadgeOf({ status: "drifted" }));
    expect(statusBadgeOf(IN_SYNC_ROW)).toEqual(statusBadgeOf({ status: "in_sync" }));
    expect(statusBadgeOf(MISSING_ROW)).toEqual(statusBadgeOf({ status: "missing" }));
  });

  it("the page asks the helper for each row's badge and renders its colour — DoD-3", async () => {
    await renderLoaded();
    expect(spied.badge.length).toBeGreaterThan(0);
    const expected: Record<string, string> = { users: "green", llm_servers: "yellow", models: "red" };
    for (const [name, colour] of Object.entries(expected)) {
      const style = badgeStyle(badgeOf(name));
      expect(style, name).toMatch(new RegExp(`\\b${colour}\\b`));
      for (const other of Object.values(expected).filter((c) => c !== colour)) {
        expect(style, `${name} carries ${other}`).not.toMatch(new RegExp(`\\b${other}\\b`));
      }
    }
  });

  it("the component maps no colour itself: it names no badge colour and calls the helper — DoD-3", () => {
    const page = readSource(PAGE_SOURCE);
    expect(page).not.toMatch(/["'`]green["'`]/);
    expect(page).not.toMatch(/["'`]yellow["'`]/);
    expect(page).toMatch(/\bstatusBadgeOf\b/);
  });
});

// ===========================================================================
describe("a drifted row renders its differences from the summary helper", () => {
  it("the Columns summary names the missing, extra and changed columns — DoD-4 (US-017.AC-1, D1)", () => {
    const { columns } = differencesSummaryOf(DRIFTED_ROW);
    for (const name of ["nickname", "legacy_flag", "base_url", "kind"]) {
      expect(columns, name).toContain(name);
    }
  });

  it("a changed column's summary carries its expected and actual type — DoD-4 (D1)", () => {
    const { columns } = differencesSummaryOf({ ...EMPTY_DIFFERENCES, changed_columns: [TYPE_CHANGE] });
    expect(columns).toContain("base_url");
    expect(columns).toContain("TEXT");
    expect(columns).toContain("BLOB");
  });

  it("expected and actual are told apart: swapping them changes the type summary — DoD-4 (D1)", () => {
    const swapped: ChangedColumn = { name: TYPE_CHANGE.name, expected: TYPE_CHANGE.actual, actual: TYPE_CHANGE.expected };
    const forward = differencesSummaryOf({ ...EMPTY_DIFFERENCES, changed_columns: [TYPE_CHANGE] }).columns;
    const backward = differencesSummaryOf({ ...EMPTY_DIFFERENCES, changed_columns: [swapped] }).columns;
    expect(forward).not.toBe(backward);
  });

  it("a nullability-only change names the column and its nullability, expected apart from actual — DoD-4 (D1)", () => {
    const swapped: ChangedColumn = {
      name: NULLABILITY_CHANGE.name,
      expected: NULLABILITY_CHANGE.actual,
      actual: NULLABILITY_CHANGE.expected,
    };
    const forward = differencesSummaryOf({ ...EMPTY_DIFFERENCES, changed_columns: [NULLABILITY_CHANGE] }).columns;
    const backward = differencesSummaryOf({ ...EMPTY_DIFFERENCES, changed_columns: [swapped] }).columns;
    expect(forward).toContain("kind");
    expect(forward).toMatch(/null/i);
    expect(forward).not.toBe(backward);
  });

  it("a missing column reads differently from the same column extra — DoD-4 (D1)", () => {
    const missing = differencesSummaryOf({ ...EMPTY_DIFFERENCES, missing_columns: ["nickname"] }).columns;
    const extra = differencesSummaryOf({ ...EMPTY_DIFFERENCES, extra_columns: ["nickname"] }).columns;
    expect(missing).toContain("nickname");
    expect(extra).toContain("nickname");
    expect(missing).not.toBe(extra);
  });

  it("the Indexes summary names the missing and extra indexes' column lists — DoD-4 (D1)", () => {
    const { indexes } = differencesSummaryOf(DRIFTED_ROW);
    for (const name of ["owner_ref", "display_name", "legacy_flag"]) {
      expect(indexes, name).toContain(name);
    }
  });

  it("a missing index reads differently from the same index extra — DoD-4 (D1)", () => {
    const shape = { columns: ["owner_ref", "display_name"], unique: false };
    const missing = differencesSummaryOf({ ...EMPTY_DIFFERENCES, missing_indexes: [shape] }).indexes;
    const extra = differencesSummaryOf({ ...EMPTY_DIFFERENCES, extra_indexes: [shape] }).indexes;
    expect(missing).toContain("owner_ref");
    expect(extra).toContain("owner_ref");
    expect(missing).not.toBe(extra);
  });

  it("the helper is pure: same answer twice, input untouched — DoD-4", () => {
    const input = JSON.parse(JSON.stringify(DRIFTED_ROW)) as DriftTableRow;
    const first = differencesSummaryOf(input);
    expect(differencesSummaryOf(input)).toEqual(first);
    expect(input).toEqual(DRIFTED_ROW);
  });

  it("the drifted row's Columns and Indexes cells render the helper's text — DoD-4 (UC-014)", async () => {
    await renderLoaded();
    expect(spied.summary.length).toBeGreaterThan(0);
    const summary = differencesSummaryOf(DRIFTED_ROW);
    expect(squash(cellText("llm_servers", COLUMNS_HEADER))).toContain(squash(summary.columns));
    expect(squash(cellText("llm_servers", INDEXES_HEADER))).toContain(squash(summary.indexes));
  });

  it("the drifted row shows every missing, extra and changed column and both index lists — DoD-4 (UC-014)", async () => {
    await renderLoaded();
    const columns = cellText("llm_servers", COLUMNS_HEADER);
    for (const text of ["nickname", "legacy_flag", "base_url", "kind", "TEXT", "BLOB"]) {
      expect(columns, text).toContain(text);
    }
    const indexes = cellText("llm_servers", INDEXES_HEADER);
    for (const text of ["owner_ref", "display_name", "legacy_flag"]) {
      expect(indexes, text).toContain(text);
    }
  });
});

// ===========================================================================
describe("R5 — no row count, no size, no timestamp", () => {
  const LOADED_WITH_EXTRAS: WireRow[] = REPORT.map((row, index) => ({
    ...row,
    row_count: [4817, 9253, 6031][index],
    size_bytes: [91234, 88123, 77011][index],
    last_checked_at: "2026-09-29T10:11:12.000000+00:00",
    updated_at: "2026-09-28T08:09:10.000000+00:00",
    sessions_using: 7719,
  }));

  it("renders no count, size or timestamp even when the payload carries them — DoD-5 (R5, UC-065, UC-066)", async () => {
    await renderLoaded(LOADED_WITH_EXTRAS);
    const text = readableText();
    for (const value of ["4817", "9253", "6031", "91234", "88123", "77011", "7719", "2026-09-29", "2026-09-28"]) {
      expect(text, value).not.toContain(value);
    }
  });

  it("no rendered string is a digit-bearing claim about rows or user material, a size or a date — DoD-5 (R5)", async () => {
    await renderLoaded(LOADED_WITH_EXTRAS);
    for (const piece of readablePieces()) {
      expect(piece).not.toMatch(COUNT_CLAIM);
      expect(piece).not.toMatch(BYTE_SIZE);
      expect(piece).not.toMatch(ISO_DATE);
    }
  });

  it("the summary helper names no count of rows — DoD-5 (R5)", () => {
    for (const row of REPORT) {
      const { columns, indexes } = differencesSummaryOf(row);
      for (const text of [columns, indexes]) {
        expect(text, row.table_name).not.toMatch(COUNT_CLAIM);
        expect(text, row.table_name).not.toMatch(BYTE_SIZE);
        expect(text, row.table_name).not.toMatch(ISO_DATE);
      }
    }
  });

  it("the store keeps no count, size or timestamp from the payload's rows — DoD-5 (R5)", async () => {
    const { state } = await renderLoaded(LOADED_WITH_EXTRAS);
    const rendered = readableText();
    expect(rendered).not.toMatch(/row_count|size_bytes|last_checked_at|sessions_using/);
    expect(state.rows.map((row) => row.table_name)).toEqual(["users", "llm_servers", "models"]);
  });
});

// ===========================================================================
describe("loading and empty states", () => {
  it("while the report is in flight a Loader renders and no table body does — DoD-6", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    renderPage();
    await flush();

    expect(loaders().length).toBeGreaterThan(0);
    expect(document.querySelector("tbody")).toBeNull();

    pending.resolve(jsonResponse({ tables: copyRows(REPORT) }, 200));
    await flush();
    expect(loaders()).toEqual([]);
    expect(bodyRows()).toHaveLength(3);
  });

  it("the status field reads loading while in flight and ready afterwards — DoD-6", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = new DatabasePageState();
    expect(state.status).toBe("idle");
    const running = loadDriftReport(state);
    await settle();
    expect(state.status).toBe("loading");
    pending.resolve(jsonResponse({ tables: copyRows(REPORT) }, 200));
    await running;
    expect(state.status).toBe("ready");
  });

  it("the Loader is gated on the status field, not on the rows: rows present but not ready still shows it — DoD-6", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = new DatabasePageState();
    runInAction(() => {
      state.rows = copyRows([IN_SYNC_ROW] as unknown as WireRow[]) as unknown as DriftTableRow[];
    });
    expect(state.status).not.toBe("ready");
    renderPage(state);
    await flush();

    expect(loaders().length).toBeGreaterThan(0);
    expect(document.querySelector("tbody")).toBeNull();
    pending.resolve(jsonResponse({ tables: [] }, 200));
    await flush();
  });

  it("an empty ready report renders the headers with no rows and no Loader — DoD-6", async () => {
    await renderLoaded([]);
    expect(loaders()).toEqual([]);
    const headers = headerTexts();
    expect(headers.some((text) => TABLE_HEADER.test(text))).toBe(true);
    expect(headers.some((text) => STATUS_HEADER.test(text))).toBe(true);
    expect(headers.some((text) => COLUMNS_HEADER.test(text))).toBe(true);
    expect(headers.some((text) => INDEXES_HEADER.test(text))).toBe(true);
    expect(bodyRows()).toHaveLength(0);
  });
});

// ===========================================================================
describe("a failed report load renders inline", () => {
  it("renders the message in an Alert above any table and raises no notification — DoD-7", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    renderPage();
    await flush();

    const alert = alertWith(FAILURE_MESSAGE);
    const rendered = document.querySelector("table");
    if (rendered !== null) expect(isBefore(alert, rendered)).toBe(true);
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("with a table on screen, the page error renders as an Alert above the table — DoD-7", async () => {
    const { state } = await renderLoaded();
    runInAction(() => {
      state.errorMessage = FAILURE_MESSAGE;
    });
    await flush();
    const alert = alertWith(FAILURE_MESSAGE);
    expect(isBefore(alert, table())).toBe(true);
    expect(notificationRoots()).toEqual([]);
  });

  it("a failed load never rejects and lands the message in the store's error field — DoD-7", async () => {
    stubFetch(() => Promise.resolve(failureResponse()));
    const state = new DatabasePageState();
    await expect(loadDriftReport(state)).resolves.toBeUndefined();
    expect(state.errorMessage).toEqual(expect.stringContaining(FAILURE_MESSAGE));
    expect(state.rows).toEqual([]);
  });

  it("a transport failure also lands in an Alert, never a notification — DoD-7", async () => {
    stubFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    const { state } = renderPage();
    await flush();
    expect(typeof state.errorMessage).toBe("string");
    expect((state.errorMessage ?? "").length).toBeGreaterThan(0);
    expect(alerts().length).toBeGreaterThan(0);
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("no module of this page imports notifyFailure or Mantine's notifications — DoD-7", () => {
    const offenders = PAGE_MODULES.flatMap((file) =>
      importSpecifiers(readFileSync(file, "utf8"))
        .filter((spec) => /notifyFailure|@mantine\/notifications/.test(spec))
        .map((spec) => `${path.basename(file)} imports ${spec}`),
    );
    expect(offenders).toEqual([]);
  });

  it("a successful load raises no notification and no Alert — DoD-7", async () => {
    await renderLoaded();
    expect(notificationRoots()).toEqual([]);
    expect(alerts()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ===========================================================================
describe("the wire carries no id", () => {
  it("the page's modules declare no id and call no parseInt — DoD-8", () => {
    for (const file of PAGE_MODULES) {
      const source = readSource(file);
      const name = path.basename(file);
      expect(source, name).not.toMatch(/\bid\b/);
      expect(source, name).not.toMatch(/\b\w+Id\b|\b\w*_id\b|\bID\b/);
      expect(source, name).not.toMatch(/\bparseInt\b/);
    }
  });

  it("the row key is the table name — DoD-8", () => {
    const page = readSource(PAGE_SOURCE);
    expect(page).toMatch(/\bkey\s*=\s*\{[^}]*\btable_name\b[^}]*\}/);
  });

  it("the store has no id-like field — DoD-8", () => {
    const names = Object.getOwnPropertyNames(new DatabasePageState());
    expect(names.filter((name) => /^id$|Id$|_id$|ID/.test(name))).toEqual([]);
  });

  it("the loaded rows are the wire rows with no id added, and the load is called with no id — DoD-8", async () => {
    const { state } = await renderLoaded();
    expect(toJS(state.rows)).toEqual(REPORT);
    for (const row of toJS(state.rows) as unknown as WireRow[]) {
      expect(Object.keys(row).filter((key) => /id/i.test(key))).toEqual([]);
    }
    expect(spied.load.length).toBeGreaterThan(0);
    for (const args of spied.load) {
      expect(args[0]).toBe(state);
      expect(args.length).toBeLessThanOrEqual(2);
      if (args.length === 2) expect(args[1] === undefined || args[1] instanceof AbortSignal).toBe(true);
    }
  });
});

// ===========================================================================
describe("no sorting, filtering or pagination", () => {
  it("the headers carry no sort control and the page no filter input or pagination — DoD-9", async () => {
    await renderLoaded();
    const head = table().querySelector("thead");
    expect(head).not.toBeNull();
    expect(head?.querySelectorAll("button, [role='button'], [aria-sort]").length).toBe(0);
    expect(screen.queryAllByRole("textbox")).toEqual([]);
    expect(screen.queryAllByRole("searchbox")).toEqual([]);
    expect(screen.queryAllByRole("combobox")).toEqual([]);
    expect(document.querySelectorAll(".mantine-Pagination-root").length).toBe(0);
  });

  it("no request the page sends carries a query parameter — DoD-9", async () => {
    const { mock } = await renderLoaded();
    const calls = seen(mock);
    expect(calls.length).toBeGreaterThan(0);
    for (const call of calls) expect(call.search, `${call.method} ${call.path}`).toBe("");
    expect(DRIFT_REPORT_PATH).not.toContain("?");
  });

  it("the page uses a plain Mantine Table and no data-table library or pagination — DoD-9", () => {
    const source = readSource(PAGE_SOURCE);
    const specs = importSpecifiers(readFileSync(PAGE_SOURCE, "utf8"));
    expect(source).toMatch(/<Table\b/);
    expect(specs.filter((spec) => /datatable|data-table|react-table|ag-grid|data-grid/i.test(spec))).toEqual([]);
    expect(source).not.toMatch(/\bPagination\b/);
    expect(source).not.toMatch(/\.sort\s*\(|\.toSorted\s*\(/);
  });
});

// ===========================================================================
describe("nothing out of scope on the page", () => {
  it("no control, enabled or disabled, is named Export, Import or Rebuild — DoD-10", async () => {
    await renderLoaded();
    const offenders = controls()
      .map(controlName)
      .filter((name) => OUT_OF_SCOPE_CONTROL.test(name));
    expect(offenders).toEqual([]);
  });

  it("nothing on the page reads Export, Import or Rebuild — DoD-10", async () => {
    await renderLoaded();
    expect(readableText()).not.toMatch(OUT_OF_SCOPE_CONTROL);
  });

  it("the page has no control outside the report table — no header action bar — DoD-10", async () => {
    await renderLoaded();
    const outside = controls().filter((el) => !table().contains(el));
    expect(outside.map(controlName)).toEqual([]);
  });

  it("an empty report and a failed load show no Export, Import or Rebuild either — DoD-10", async () => {
    await renderLoaded([]);
    expect(readableText()).not.toMatch(OUT_OF_SCOPE_CONTROL);
    expect(controls().map(controlName).filter((name) => OUT_OF_SCOPE_CONTROL.test(name))).toEqual([]);
  });

  it("the page source renders no Export, Import or Rebuild wording in any string or JSX text — DoD-10", () => {
    const page = readSource(PAGE_SOURCE);
    const literals = Array.from(page.matchAll(/"([^"\n]*)"|'([^'\n]*)'|`([^`]*)`|>([^<>{}]+)</g), (m) =>
      (m[1] ?? m[2] ?? m[3] ?? m[4] ?? "").trim(),
    ).filter((text) => text !== "" && !text.startsWith(".") && !text.startsWith("@") && !text.includes("/"));
    expect(literals.filter((text) => OUT_OF_SCOPE_CONTROL.test(text))).toEqual([]);
  });
});

// ===========================================================================
describe("the store is a data class; the load is a free function", () => {
  const ALLOWED_FIELDS = ["applyingTable", "errorMessage", "rows", "status"];
  const REQUIRED_FIELDS = ["errorMessage", "rows", "status"];

  it("the class prototype carries no method and no getter — DoD-11 (D13)", () => {
    expect(Object.getOwnPropertyNames(DatabasePageState.prototype)).toEqual(["constructor"]);
  });

  it("rows, status and errorMessage are observable fields, nothing is computed or a function — DoD-11 (D13)", () => {
    const state = new DatabasePageState();
    const own = Object.getOwnPropertyNames(state);
    const observed = own.filter((name) => isObservableProp(state, name));
    for (const name of REQUIRED_FIELDS) expect(observed, name).toContain(name);
    const record = state as unknown as Record<string, unknown>;
    for (const name of own) {
      expect(ALLOWED_FIELDS, `own property ${name}`).toContain(name);
      expect(isObservableProp(state, name), `own property ${name}`).toBe(true);
      expect(typeof record[name], `own property ${name}`).not.toBe("function");
      expect(isComputedProp(state, name), `own property ${name}`).toBe(false);
    }
  });

  it("a fresh store is idle, with no rows and no error — DoD-11", () => {
    const state = new DatabasePageState();
    expect(toJS(state.rows)).toEqual([]);
    expect(state.status).toBe("idle");
    expect(state.errorMessage).toBeNull();
  });

  it("the page calls the load with its store first and an abort signal — DoD-11 (D13)", async () => {
    const { state } = await renderLoaded();
    expect(spied.load).toHaveLength(1);
    expect(spied.load[0][0]).toBe(state);
    const signal = spied.load[0][1] as AbortSignal | undefined;
    expect(signal).toBeTruthy();
    expect(typeof signal?.aborted).toBe("boolean");
  });

  it("the load writes only inside actions (strict MobX raises no warning) — DoD-11 (D13)", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    configure({ enforceActions: "always" });
    try {
      const run = async (impl: FetchFn) => {
        stubFetch(impl);
        const state = new DatabasePageState();
        const dispose = autorun(() => {
          void state.rows.length;
          void state.status;
          void state.errorMessage;
        });
        await loadDriftReport(state);
        await loadDriftReport(state);
        dispose();
        vi.unstubAllGlobals();
      };
      await run(() => Promise.resolve(jsonResponse({ tables: copyRows(REPORT) }, 200)));
      await run(() => Promise.resolve(failureResponse()));
      await run(() => Promise.reject(new TypeError("Failed to fetch")));
    } finally {
      configure({ enforceActions: "observed" });
    }
    const mobxWarnings = warn.mock.calls.filter((args) => args.some((arg) => String(arg).includes("[MobX]")));
    expect(mobxWarnings).toEqual([]);
  });

  it("given an already-aborted signal the load writes nothing — DoD-11 (D13)", async () => {
    serveReport();
    for (const state of [new DatabasePageState(), readyWith([IN_SYNC_ROW])]) {
      const before = snapshot(state);
      const controller = new AbortController();
      controller.abort();
      await expect(loadDriftReport(state, controller.signal)).resolves.toBeUndefined();
      await settle();
      expect(snapshot(state)).toEqual(before);
    }
  });

  it("a response arriving after the abort is not written — DoD-11 (D13)", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const state = new DatabasePageState();
    const controller = new AbortController();
    const running = loadDriftReport(state, controller.signal);
    await settle();
    const atAbort = snapshot(state);
    controller.abort();
    pending.resolve(jsonResponse({ tables: copyRows(REPORT) }, 200));
    await running;
    await settle();
    expect(snapshot(state)).toEqual(atAbort);
    expect(toJS(state.rows)).toEqual([]);
  });

  it("the store is created with useState(() => new …), never useMemo, and the load uses runInAction — DoD-11 (D13)", () => {
    const page = readSource(PAGE_SOURCE);
    const app = readSource(ADMIN_APP_SOURCE);
    expect(`${page}\n${app}`).toMatch(/useState\s*\(\s*\(\s*\)\s*=>\s*new\s+DatabasePageState\s*\(/);
    expect(page).not.toMatch(/\buseMemo\b/);
    expect(app).not.toMatch(/\buseMemo\b/);
    expect(readSource(STATE_SOURCE)).toMatch(/\brunInAction\b/);
  });
});

// ===========================================================================
describe("unmounting", () => {
  it("aborts the in-flight report request — DoD-12 (D13)", async () => {
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
    pending.resolve(jsonResponse({ tables: copyRows(REPORT) }, 200));
    await flush();
  });

  it("no store write happens after the unmount — DoD-12 (D13)", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const { view, state } = renderPage();
    await flush();
    const atUnmount = snapshot(state);

    view.unmount();
    pending.resolve(jsonResponse({ tables: copyRows(REPORT) }, 200));
    await flush();

    expect(snapshot(state)).toEqual(atUnmount);
    expect(toJS(state.rows)).toEqual([]);
  });

  it("a failure arriving after the unmount is not written either — DoD-12 (D13)", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const { view, state } = renderPage();
    await flush();
    const atUnmount = snapshot(state);

    view.unmount();
    pending.resolve(failureResponse());
    await flush();

    expect(snapshot(state)).toEqual(atUnmount);
    expect(state.errorMessage).toBeNull();
  });
});

// ===========================================================================
describe("the /database route", () => {
  const answerRoutes: FetchFn = (input, init) => {
    const method = requestMethod(input, init);
    const pathname = requestUrl(input).pathname.replace(/\/+$/, "");
    if (method === "GET" && pathname === USERS_LIST_PATH) return Promise.resolve(jsonResponse({ users: [] }, 200));
    if (method === "GET" && pathname === LLM_LIST_PATH) return Promise.resolve(jsonResponse({ servers: [] }, 200));
    if (method === "GET" && pathname === REPORT_PATH) {
      return Promise.resolve(jsonResponse({ tables: copyRows(REPORT) }, 200));
    }
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

  function main(): HTMLElement {
    return screen.getByRole("main");
  }

  it("/database renders this page, not the 404 — DoD-13", async () => {
    const mock = await renderApp("/database");
    expect(renderedTextOf(main())).not.toMatch(NOT_FOUND_TEXT);
    expect(seen(mock).filter((call) => call.path === REPORT_PATH)).toEqual([
      { method: "GET", path: REPORT_PATH, search: "" },
    ]);
    const rendered = main().querySelector("table");
    expect(rendered).not.toBeNull();
    expect(rendered?.querySelectorAll("tbody tr").length).toBe(3);
    expect(renderedTextOf(main())).toContain("llm_servers");
  });

  it("/ still renders the Users page — DoD-13", async () => {
    const mock = await renderApp("/");
    expect(renderedTextOf(main())).not.toMatch(NOT_FOUND_TEXT);
    expect(seen(mock).some((call) => call.method === "GET" && call.path === USERS_LIST_PATH)).toBe(true);
    expect(seen(mock).some((call) => call.path === REPORT_PATH)).toBe(false);
  });

  it("/llm-servers still renders the LLM Servers page — DoD-13", async () => {
    const mock = await renderApp("/llm-servers");
    expect(renderedTextOf(main())).not.toMatch(NOT_FOUND_TEXT);
    expect(seen(mock).some((call) => call.method === "GET" && call.path === LLM_LIST_PATH)).toBe(true);
    expect(seen(mock).some((call) => call.path === REPORT_PATH)).toBe(false);
  });

  it("an unmatched path still renders the 404 element — DoD-13", async () => {
    const mock = await renderApp("/nope");
    expect(renderedTextOf(main())).toMatch(NOT_FOUND_TEXT);
    expect(seen(mock).some((call) => call.path === REPORT_PATH)).toBe(false);
  });

  it("the <Routes> is still flat and four elements long, and /database no longer renders the 404 — DoD-13", () => {
    const source = readSource(ADMIN_APP_SOURCE);
    expect(source.match(/<Route(?![A-Za-z])/g) ?? []).toHaveLength(4);
    const paths = Array.from(source.matchAll(/\bpath\s*=\s*\{?\s*["'`]([^"'`]+)["'`]/g), (m) => m[1]);
    expect([...paths].sort()).toEqual(["*", "/", "/database", "/llm-servers"]);
    expect(source, "every <Route> is self-closing — nothing nested").not.toMatch(/<\/Route>/);
    expect(source).not.toMatch(/\bOutlet\b/);
    const at = source.search(/\bpath\s*=\s*\{?\s*["'`]\/database["'`]/);
    expect(at).toBeGreaterThanOrEqual(0);
    const start = source.lastIndexOf("<Route", at);
    const next = source.indexOf("<Route", at);
    const segment = source.slice(start, next < 0 ? source.indexOf("</Routes>", at) : next);
    expect(segment).not.toMatch(/NotFoundPage/);
  });
});

// ===========================================================================
describe("no stylesheet in the admin area", () => {
  it("no file under src/admin is a stylesheet — DoD-14", () => {
    const offenders = walkFiles(ADMIN_SRC)
      .filter((file) => /\.(css|scss|sass|less|styl)$/i.test(file))
      .map(relative);
    expect(offenders).toEqual([]);
  });

  it("no module under src/admin imports a stylesheet — DoD-14", () => {
    const offenders = walkFiles(ADMIN_SRC)
      .filter((file) => /\.(ts|tsx)$/.test(file))
      .flatMap((file) =>
        importSpecifiers(readFileSync(file, "utf8"))
          .filter((spec) => /\.(css|scss|sass|less|styl)(\?.*)?$/i.test(spec) || /styled-components|@emotion/.test(spec))
          .map((spec) => `${relative(file)} imports ${spec}`),
      );
    expect(offenders).toEqual([]);
  });

  it("the page renders through Mantine props alone: no className and no style element — DoD-14", () => {
    const source = readSource(PAGE_SOURCE);
    expect(source).not.toMatch(/\bclassName\s*=/);
    expect(source).not.toMatch(/<style\b/);
  });
});
