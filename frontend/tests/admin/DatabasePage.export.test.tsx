// Feature 030 — export-granularities, step 005: the Database page's page half — the Export
// action, the size line, opacity and the inline failure (DoD-1..DoD-7). The store half lives
// in `databasePageExport.test.ts`. DoD-11 and DoD-12 are [manual/live].
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 005.context.md and the feature context.md: opacity (no viewer, preview, search, row count
// or table-name listing of any export), no success toast, no confirm dialog, the size line is
// the one permitted report, and an admin export failure renders inline and is never also
// notified. Bindings come from the frozen `### Step 005` record: the page is
// `<DatabasePage state={...} />`, the control's accessible name is exactly `Export`, and the
// store exposes `exportSizeBytes` / `exportErrorMessage` / `exportStatus`.
//
// Harness conventions (005.context.md and 004.context.md):
// - `fetch` is stubbed per file and routed by exact pathname; the page's mount also loads the
//   drift report, so the stub answers `GET /api/admin/database/tables` as well.
// - jsdom implements neither `URL.createObjectURL` nor `URL.revokeObjectURL`; both are
//   installed per test and restored afterwards, and the anchor click is swallowed by a spy on
//   `HTMLAnchorElement.prototype.click` so jsdom never navigates.
// - The page renders inside `AppProviders`, so the notifications outlet exists and "nothing
//   was notified" is observable (`.mantine-Notification-root`).
// - "Readable text" excludes the contents of style/script elements (the providers inject CSS)
//   and includes the naming attributes, so an opacity leak through a tooltip or label counts.
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DatabasePage } from "../../src/admin/DatabasePage";
import { DatabasePageState, type DriftTableRow } from "../../src/admin/databasePageState";
import { AppProviders } from "../../src/shared/AppProviders";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type User = ReturnType<typeof userEvent.setup>;

const REPORT_PATH = "/api/admin/database/tables";
const EXPORT_PATH = "/api/admin/database/export";
const NOTIFICATION_ROOT = ".mantine-Notification-root";
const NON_RENDERED = "style, script, noscript, template";
const NAMING_ATTRIBUTES = [
  "aria-label",
  "title",
  "aria-description",
  "placeholder",
  "alt",
  "aria-valuetext",
];

const EXPORT_FAILURE_MESSAGE = "The export could not be produced (qz-71 marker).";
const DRIFT_FAILURE_MESSAGE = "The drift report is on fire (zq-19 marker).";

/** A digit-bearing claim about user-owned material (R5) — a row count is one. */
const COUNT_CLAIM =
  /\d[\d,.\s]*\s*(rows?|records?|sessions?|characters?|setups?|messages?|memos?|users?|entries|tables?)\b/i;
/** Opacity — any affordance that would open, show or walk the export's contents. */
const VIEWER_CONTROL =
  /\b(view|open|preview|browse|inspect|reveal|peek|details?|contents?|display|expand|show)\b/i;
const EXPORT_NAME = /\bexport(s|ed|ing)?\b/i;

// ---------------------------------------------------------------- fixtures

function row(table_name: string, status: DriftTableRow["status"]): DriftTableRow {
  return {
    table_name,
    status,
    missing_columns: status === "drifted" ? ["nickname"] : [],
    extra_columns: [],
    changed_columns: [],
    missing_indexes: [],
    extra_indexes: [],
  };
}

/**
 * Drift tables deliberately disjoint from the export payload's table names, so that a
 * rendered "characters" or "memos" can only have come from the export (DoD-2).
 */
const IN_SYNC_REPORT: DriftTableRow[] = [
  row("llm_servers", "in_sync"),
  row("models", "in_sync"),
  row("translations", "in_sync"),
];
const DRIFTED_REPORT: DriftTableRow[] = [
  row("llm_servers", "in_sync"),
  row("models", "drifted"),
  row("translations", "in_sync"),
];
const MISSING_REPORT: DriftTableRow[] = [
  row("llm_servers", "in_sync"),
  row("models", "missing"),
  row("translations", "in_sync"),
];

const USER_ID = "7250000000000000101";
const CHARACTER_ID = "7250000000000000202";
const MEMO_ID = "7250000000000000303";
const USERNAME = "zqgrimweld";
const CHARACTER_NAME = "Quillaxon the Sentinel";
const MEMO_TEXT = "the sentinel memo body marker qz71";

/** Every string that must never reach the page: content, ids and table names. */
const SENTINELS = [
  USERNAME,
  CHARACTER_NAME,
  MEMO_TEXT,
  USER_ID,
  CHARACTER_ID,
  MEMO_ID,
  "characters",
  "memos",
  "users",
  "rphelper-export",
];

const EXPORT_ENVELOPE = {
  format: "rphelper-export",
  version: 1,
  granularity: "database",
  created_at: "2026-01-05T10:11:12Z",
  schema_version: 1,
  payload: {
    users: [{ id: USER_ID, username: USERNAME }],
    characters: [{ id: CHARACTER_ID, user_id: USER_ID, name: CHARACTER_NAME }],
    memos: [{ id: MEMO_ID, scope: "character", scope_id: CHARACTER_ID, body: MEMO_TEXT }],
  },
};

/** DoD-1/DoD-9 — padded to an exact byte count, so the expected size text is 2.0 KB. */
const EXPORT_SIZE_BYTES = 2048;
const EXPORT_SIZE_TEXT = "2.0 KB";
const EXPORT_BODY = (() => {
  const base = JSON.stringify(EXPORT_ENVELOPE);
  const used = new TextEncoder().encode(base).length;
  return base + " ".repeat(EXPORT_SIZE_BYTES - used);
})();

function envelope(code: string, message: string) {
  return { error: { code, message, detail: {} } };
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function exportResponse(): Response {
  return new Response(EXPORT_BODY, {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Content-Disposition": 'attachment; filename="rphelper-database-20260105T101112Z.json"',
    },
  });
}

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
});

afterEach(() => {
  if (!hadCreateObjectUrl) Reflect.deleteProperty(URL, "createObjectURL");
  if (!hadRevokeObjectUrl) Reflect.deleteProperty(URL, "revokeObjectURL");
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- the server

type ServerOptions = {
  report?: readonly DriftTableRow[];
  reportStatus?: number;
  exportMake?: () => Response;
};

function pathnameOf(input: RequestInfo | URL): string {
  const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(url, "http://localhost").pathname;
}

function serve(options: ServerOptions = {}) {
  const mock = vi.fn<FetchFn>((input) => {
    const pathname = pathnameOf(input);
    if (pathname === REPORT_PATH) {
      const status = options.reportStatus ?? 200;
      if (status !== 200) {
        return Promise.resolve(
          jsonResponse(envelope("drift_report_failed", DRIFT_FAILURE_MESSAGE), status),
        );
      }
      return Promise.resolve(jsonResponse({ tables: options.report ?? IN_SYNC_REPORT }, 200));
    }
    if (pathname === EXPORT_PATH) {
      return Promise.resolve((options.exportMake ?? exportResponse)());
    }
    return Promise.reject(new Error(`unexpected fetch of ${pathname}`));
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

function failingExport(): Response {
  return jsonResponse(envelope("export_failed", EXPORT_FAILURE_MESSAGE), 500);
}

// ---------------------------------------------------------------- render + queries

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

async function renderLoaded(options: ServerOptions = {}) {
  const mock = serve(options);
  const state = new DatabasePageState();
  render(
    <AppProviders>
      <MemoryRouter initialEntries={["/database"]}>
        <DatabasePage state={state} />
      </MemoryRouter>
    </AppProviders>,
  );
  await flush();
  return { mock, state };
}

function exportButton(): HTMLElement {
  return screen.getByRole("button", { name: "Export" });
}

async function clickExport(user: User): Promise<void> {
  await user.click(exportButton());
  await flush();
}

function exportCalls(mock: ReturnType<typeof serve>): RequestInit[] {
  return mock.mock.calls
    .filter(([input]) => pathnameOf(input) === EXPORT_PATH)
    .map(([, init]) => init ?? {});
}

function isRenderedTextNode(node: Node): boolean {
  const parent = node.parentElement;
  return parent === null || parent.closest(NON_RENDERED) === null;
}

function renderedTextOf(root: Node): string {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) =>
      isRenderedTextNode(node) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT,
  });
  const out: string[] = [];
  for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
    out.push(node.textContent ?? "");
  }
  return out.join("");
}

function attributeTexts(): string[] {
  return Array.from(document.body.querySelectorAll("*")).flatMap((el) =>
    NAMING_ATTRIBUTES.map((name) => el.getAttribute(name) ?? "").filter(Boolean),
  );
}

/** Everything a person can read on the page, plus the naming attributes. */
function readableText(): string {
  return [renderedTextOf(document.body), ...attributeTexts()].join("\n");
}

function controls(): HTMLElement[] {
  return Array.from(
    document.body.querySelectorAll<HTMLElement>(
      "button, a[href], [role='button'], [role='menuitem'], [aria-haspopup], input, select, textarea",
    ),
  );
}

function controlName(el: HTMLElement): string {
  return [renderedTextOf(el), ...NAMING_ATTRIBUTES.map((name) => el.getAttribute(name) ?? "")]
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
}

function controlNames(): string[] {
  return controls().map(controlName);
}

function alerts(): HTMLElement[] {
  return screen.queryAllByRole("alert");
}

function alertWith(message: string): HTMLElement {
  const matching = alerts().filter((el) => renderedTextOf(el).includes(message));
  expect(matching.length, `inline alerts carrying "${message}"`).toBe(1);
  return matching[0];
}

/**
 * Mantine carries an Alert's colour as inline CSS variables and data attributes on the root
 * and its parts, so "red" is looked for across the subtree's class/style/data attributes
 * rather than in any one of them.
 */
function colourMarkup(el: HTMLElement): string {
  return [el, ...Array.from(el.querySelectorAll<HTMLElement>("*"))]
    .flatMap((node) =>
      Array.from(node.attributes)
        .filter((attr) => attr.name === "class" || attr.name === "style" || attr.name.startsWith("data-"))
        .map((attr) => `${attr.name}=${attr.value}`),
    )
    .join(" ");
}

function notificationRoots(): Element[] {
  return Array.from(document.querySelectorAll(NOTIFICATION_ROOT));
}

function tableRowNames(): string[] {
  return Array.from(document.querySelectorAll<HTMLTableRowElement>("tbody tr")).map((tr) =>
    (tr.querySelector("td")?.textContent ?? "").trim(),
  );
}

// ===========================================================================
describe("the Export action downloads the whole-database export", () => {
  it("clicking Export fetches the export route and then shows the downloaded size — DoD-1", async () => {
    const { mock } = await renderLoaded();
    const user = newUser();

    await clickExport(user);

    const calls = exportCalls(mock);
    expect(calls).toHaveLength(1);
    expect((calls[0].method ?? "GET").toUpperCase()).toBe("GET");
    expect(readableText()).toContain(EXPORT_SIZE_TEXT);
  });

  it("shows no size line before any export has run — DoD-1", async () => {
    await renderLoaded();
    expect(readableText()).not.toContain(EXPORT_SIZE_TEXT);
  });
});

// ===========================================================================
describe("the page never shows what is inside the export", () => {
  it("the fixture really carries the sentinel content — DoD-2", () => {
    // Guards the clause below against passing vacuously.
    for (const sentinel of SENTINELS) {
      expect(EXPORT_BODY, `sentinel ${sentinel} in the served body`).toContain(sentinel);
    }
    expect(new TextEncoder().encode(EXPORT_BODY).length).toBe(EXPORT_SIZE_BYTES);
  });

  it("after a successful export no sentinel content, table name or row count appears on the page — DoD-2", async () => {
    const { mock } = await renderLoaded();
    const user = newUser();

    await clickExport(user);

    // The export really happened and the page really consumed the response.
    expect(exportCalls(mock)).toHaveLength(1);
    const text = readableText();
    expect(text).toContain(EXPORT_SIZE_TEXT);

    for (const sentinel of SENTINELS) {
      expect(text, `sentinel ${sentinel} must not be rendered`).not.toContain(sentinel);
    }
    expect(text).not.toMatch(COUNT_CLAIM);
    // Only the drift report's own tables may be named, and none of them is in the export.
    expect(tableRowNames()).toEqual(["llm_servers", "models", "translations"]);
  });
});

// ===========================================================================
describe("no viewer, no preview, no search over the export", () => {
  it("before an export the only export-related control is the Export button, and nothing opens or previews it — DoD-3", async () => {
    await renderLoaded();

    expect(controlNames().filter((name) => EXPORT_NAME.test(name))).toEqual(["Export"]);
    expect(controlNames().filter((name) => VIEWER_CONTROL.test(name))).toEqual([]);
  });

  it("after a successful export the only export-related control is still the Export button — DoD-3", async () => {
    const { mock } = await renderLoaded();
    const user = newUser();

    await clickExport(user);

    // A real export happened and the page reported it, so the absences below are post-export.
    expect(exportCalls(mock)).toHaveLength(1);
    expect(readableText()).toContain(EXPORT_SIZE_TEXT);

    expect(controlNames().filter((name) => EXPORT_NAME.test(name))).toEqual(["Export"]);
    expect(controlNames().filter((name) => VIEWER_CONTROL.test(name))).toEqual([]);
  });

  it("before an export the page offers no search or filter input — DoD-4", async () => {
    await renderLoaded();

    expect(screen.queryAllByRole("textbox")).toEqual([]);
    expect(screen.queryAllByRole("searchbox")).toEqual([]);
    expect(screen.queryAllByRole("combobox")).toEqual([]);
    expect(Array.from(document.body.querySelectorAll("input, textarea"))).toEqual([]);
  });

  it("after a successful export the page still offers no search or filter input — DoD-4", async () => {
    const { mock } = await renderLoaded();
    const user = newUser();

    await clickExport(user);

    // A real export happened and the page reported it, so the absences below are post-export.
    expect(exportCalls(mock)).toHaveLength(1);
    expect(readableText()).toContain(EXPORT_SIZE_TEXT);

    expect(screen.queryAllByRole("textbox")).toEqual([]);
    expect(screen.queryAllByRole("searchbox")).toEqual([]);
    expect(screen.queryAllByRole("combobox")).toEqual([]);
    expect(Array.from(document.body.querySelectorAll("input, textarea"))).toEqual([]);
  });
});

// ===========================================================================
describe("feedback: the size line only, inline, never a notification", () => {
  it("a successful export raises no notification and opens no alert — DoD-5", async () => {
    await renderLoaded();
    const user = newUser();

    await clickExport(user);

    expect(readableText()).toContain(EXPORT_SIZE_TEXT);
    expect(notificationRoots()).toEqual([]);
    expect(alerts()).toEqual([]);
  });

  it("a failed export renders its message in an inline red Alert, raises no notification, and leaves the drift table alone — DoD-6", async () => {
    const { state } = await renderLoaded({ exportMake: failingExport });
    const user = newUser();

    await clickExport(user);

    const alert = alertWith(EXPORT_FAILURE_MESSAGE);
    expect(colourMarkup(alert)).toMatch(/red/i);
    expect(notificationRoots()).toEqual([]);
    expect(readableText()).not.toContain(EXPORT_SIZE_TEXT);
    // The drift report is untouched: its rows still render and its own message is still null.
    expect(tableRowNames()).toEqual(["llm_servers", "models", "translations"]);
    expect(state.errorMessage).toBeNull();
    expect(state.exportErrorMessage).toBe(EXPORT_FAILURE_MESSAGE);
  });

  it("a failed export never overwrites a drift failure's own message — DoD-6", async () => {
    const { state } = await renderLoaded({ reportStatus: 500, exportMake: failingExport });
    expect(renderedTextOf(document.body)).toContain(DRIFT_FAILURE_MESSAGE);
    const user = newUser();

    await clickExport(user);

    alertWith(DRIFT_FAILURE_MESSAGE);
    alertWith(EXPORT_FAILURE_MESSAGE);
    expect(state.errorMessage).toBe(DRIFT_FAILURE_MESSAGE);
    expect(state.exportErrorMessage).toBe(EXPORT_FAILURE_MESSAGE);
    expect(notificationRoots()).toEqual([]);
  });
});

// ===========================================================================
describe("the Export button is offered in every drift state", () => {
  it.each([
    ["in sync", IN_SYNC_REPORT],
    ["drifted", DRIFTED_REPORT],
    ["missing rows", MISSING_REPORT],
  ])("the Export button is present and enabled when the report is %s — DoD-7", async (_label, report) => {
    await renderLoaded({ report });

    const button = exportButton();
    expect(button).toBeEnabled();
    expect(button).not.toHaveAttribute("disabled");
    expect(button).not.toHaveAttribute("data-disabled");
    expect(renderedTextOf(button).trim()).toBe("Export");
  });

  it("the Export button is present and enabled even when the drift report failed to load — DoD-7", async () => {
    await renderLoaded({ reportStatus: 500 });

    const button = exportButton();
    expect(button).toBeEnabled();
    expect(button).not.toHaveAttribute("disabled");
  });
});
