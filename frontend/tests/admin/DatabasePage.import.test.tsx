// Feature 031 — import-and-id-remapping, step 008: the admin Database page's page half — the
// Import action, the replace confirm, the sign-out redirect, the inline failures and opacity
// (DoD-1..DoD-7, and one 030 export regression for DoD-10). The store half lives in
// `databasePageImport.test.ts`; DoD-8 and DoD-9 are store-level and live there. DoD-11 and
// DoD-12 are [manual/live] and carry no test.
//
// Expected behaviour comes from `008.admin-database-import.md` (Interface intent + Definition of
// done), `008.context.md` (the pinned confirm text, verbatim; "Why the admin page uses no
// notification") and the feature `context.md` ("Frontend shared facts" — the unreadable-file
// message and the inline-Alert-only rule for `admin`; "Wire contract" — `POST
// /api/admin/database/import` answers **204** and clears the session cookie, so the browser goes
// to `/login`; "Icon" — `IconUpload`). Bindings come from the frozen `### Step 008` and
// `### Step 006` records:
// - the page is `<DatabasePage state={...} />` and the new control's accessible name is exactly
//   `Import`, rendered by a Mantine `FileButton` whose hidden `<input type="file">` accepts
//   `.json,application/json` and deliberately carries no accessible name;
// - the confirm is `shared/ConfirmModal`, whose Cancel is named `Cancel` and whose confirm button
//   is named by `confirmLabel`;
// - an import failure renders in the page's own inline red `Alert`;
// - the navigation seam is `documentNavigation.assign` from `src/shared/api` (decision 16).
//
// Harness conventions (harvest D.5, and 030's `DatabasePage.export.test.tsx`):
// - vitest with `globals: false`, so every helper is imported explicitly;
// - `fetch` is stubbed per test and routed by method + exact pathname; the page's mount also
//   loads `GET /api/admin/database/tables`, and anything unexpected answers loudly;
// - the page renders inside `AppProviders`, so the notifications outlet exists and "nothing was
//   notified" is observable through `.mantine-Notification-root`;
// - the file choice is driven with `userEvent.upload` on the unnamed `FileButton` input, located
//   by `input[type="file"]` (the only file input on the page);
// - `documentNavigation.assign` is spied so jsdom never navigates;
// - jsdom implements neither `URL.createObjectURL` nor `URL.revokeObjectURL`; both are installed
//   and the anchor click is swallowed, so the DoD-10 export regression can run;
// - "readable text" excludes style/script contents (the providers inject CSS) and includes the
//   naming attributes, so an opacity leak through a tooltip or label counts.
import { notifications } from "@mantine/notifications";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { runInAction } from "mobx";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DatabasePage } from "../../src/admin/DatabasePage";
import { DatabasePageState, type DriftTableRow } from "../../src/admin/databasePageState";
import { documentNavigation } from "../../src/shared/api";
import { AppProviders } from "../../src/shared/AppProviders";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string; body: string | null };
type User = ReturnType<typeof userEvent.setup>;

// ---------------------------------------------------------------- the spec's names

const REPORT_PATH = "/api/admin/database/tables";
const EXPORT_PATH = "/api/admin/database/export";
const IMPORT_PATH = "/api/admin/database/import";
const LOGIN_PATH = "/login";

const IMPORT_NAME = "Import";
const EXPORT_NAME = "Export";
const UPLOAD_ICON = ".tabler-icon-upload";
const ACCEPT = ".json,application/json";
const CANCEL_NAME = /^\s*cancel\s*$/i;

/** `008.context.md` — the pinned confirm text, verbatim. */
const CONFIRM_TITLE = "Replace the whole database?";
const CONFIRM_CONSEQUENCE =
  "Everything in this instance, including your own account, is replaced by the contents of the file, and you will be signed out.";
const CONFIRM_LABEL = "Replace database";

/** context.md "Frontend shared facts" — the unreadable-file message, verbatim. */
const UNREADABLE_MESSAGE = "The chosen file is not a readable export.";

/** The server's own refusals; the page must render the server's message, not one of its own. */
const NOT_EMPTY_MESSAGE =
  "The database can only be replaced while it holds no account other than a single administrator.";
const EXPORT_INVALID_MESSAGE = "That file is not an export of this application (zq-19 marker).";

/** Already on the page before any import, so "no message overwrites another" is observable. */
const DRIFT_ERROR = "The drift report is on fire (zq-33 marker).";
const EXPORT_ERROR = "The export could not be produced (zq-44 marker).";
const SEEDED_SIZE_BYTES = 2048;
const SEEDED_SIZE_TEXT = "2.0 KB";

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

/** R5 — a digit-bearing claim about user-owned material; a row count is one. */
const COUNT_CLAIM =
  /\d[\d,.\s]*\s*(rows?|records?|sessions?|characters?|setups?|messages?|memos?|users?|entries|tables?)\b/i;

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
 * Drift tables deliberately disjoint from the chosen file's table names, so a rendered
 * "characters", "memos" or "users" could only have come from the file (DoD-7).
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
const REPORT_TABLE_NAMES = ["llm_servers", "models", "translations"];

/** DoD-1 — the three drift states the button must survive. */
const REPORT_CASES: [string, DriftTableRow[]][] = [
  ["in sync", IN_SYNC_REPORT],
  ["drifted", DRIFTED_REPORT],
  ["missing", MISSING_REPORT],
];

// Ids are decimal strings past Number.MAX_SAFE_INTEGER (context.md "Ids are strings").
const USER_ID = "7250000000000000101";
const CHARACTER_ID = "7250000000000000202";
const MEMO_ID = "7250000000000000303";
const USERNAME = "zqgrimweld";
const CHARACTER_NAME = "Quillaxon the Sentinel";
const MEMO_TEXT = "the sentinel memo body marker qz71";

/** Everything inside the chosen file that must never reach the page: content, ids, table names. */
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

/** A whole-database envelope carrying the sentinels. The client posts it verbatim. */
function importEnvelope(): Record<string, unknown> {
  return {
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
}

/** `accept` is `.json,application/json`, so every fixture is named and typed to pass it. */
function exportFile(body: unknown): File {
  return new File([JSON.stringify(body)], "transfer.json", { type: "application/json" });
}

/** A `.json` file whose text is not JSON at all. */
function unreadableFile(): File {
  return new File(["this is not json at all"], "transfer.json", { type: "application/json" });
}

/** 030's export body, padded to an exact byte count so the size line is 2.0 KB (DoD-10). */
const EXPORT_SIZE_TEXT = "2.0 KB";
const EXPORT_BODY = (() => {
  const base = JSON.stringify({ format: "rphelper-export", version: 1, payload: {} });
  const used = new TextEncoder().encode(base).length;
  return base + " ".repeat(2048 - used);
})();

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
  act(() => {
    notifications.clean();
  });
  if (!hadCreateObjectUrl) Reflect.deleteProperty(URL, "createObjectURL");
  if (!hadRevokeObjectUrl) Reflect.deleteProperty(URL, "revokeObjectURL");
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- the server

type ServerOptions = {
  report?: readonly DriftTableRow[];
  importFailure?: { code: string; message: string; status: number };
};

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

function errorEnvelope(code: string, message: string, status: number): Response {
  return jsonResponse({ error: { code, message, detail: {} } }, status);
}

function serve(options: ServerOptions = {}) {
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

    if (method === "GET" && url.pathname === REPORT_PATH) {
      return Promise.resolve(jsonResponse({ tables: options.report ?? IN_SYNC_REPORT }, 200));
    }
    if (method === "POST" && url.pathname === IMPORT_PATH) {
      const failure = options.importFailure;
      if (failure !== undefined) {
        return Promise.resolve(errorEnvelope(failure.code, failure.message, failure.status));
      }
      // context.md "Wire contract" — the admin import answers 204 with no body.
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    if (method === "GET" && url.pathname === EXPORT_PATH) {
      return Promise.resolve(
        new Response(EXPORT_BODY, {
          status: 200,
          headers: {
            "Content-Type": "application/json",
            "Content-Disposition": 'attachment; filename="rphelper-database.json"',
          },
        }),
      );
    }
    return Promise.resolve(errorEnvelope("not_found", `unexpected ${method} ${url.pathname}`, 404));
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

function matching(calls: Seen[], method: string, path: string): Seen[] {
  return calls.filter((call) => call.method === method && call.path === path);
}

// ---------------------------------------------------------------- render + queries

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

async function renderLoaded(options: ServerOptions = {}) {
  const server = serve(options);
  const state = new DatabasePageState();
  render(
    <AppProviders>
      <MemoryRouter initialEntries={["/database"]}>
        <DatabasePage state={state} />
      </MemoryRouter>
    </AppProviders>,
  );
  await flush();
  return { ...server, state };
}

function importButton(): HTMLElement {
  return screen.getByRole("button", { name: IMPORT_NAME });
}

function exportButton(): HTMLElement {
  return screen.getByRole("button", { name: EXPORT_NAME });
}

/** The `FileButton`'s hidden input: unnamed by design, and the only file input on the page. */
function fileInput(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  if (input === null) throw new Error("the Database page renders no file input");
  return input;
}

async function chooseFile(user: User, file: File): Promise<void> {
  await user.upload(fileInput(), file);
  await flush();
}

function dialogs(): HTMLElement[] {
  return [...screen.queryAllByRole("dialog"), ...screen.queryAllByRole("alertdialog")];
}

async function replaceDialog(): Promise<HTMLElement> {
  const dialog = await waitFor(() => {
    const found = dialogs().find((el) => (el.textContent ?? "").includes(CONFIRM_LABEL));
    if (found === undefined) throw new Error("the replace confirm is not open");
    return found;
  });
  return dialog;
}

async function confirmReplace(user: User): Promise<void> {
  const dialog = await replaceDialog();
  await user.click(within(dialog).getByRole("button", { name: CONFIRM_LABEL }));
  await flush();
}

async function cancelReplace(user: User): Promise<void> {
  const dialog = await replaceDialog();
  await user.click(within(dialog).getByRole("button", { name: CANCEL_NAME }));
  await flush();
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

/** Everything a person can read anywhere in the document, plus the naming attributes. */
function readableText(): string {
  return [renderedTextOf(document.body), ...attributeTexts()].join("\n");
}

function alerts(): HTMLElement[] {
  return screen.queryAllByRole("alert");
}

function alertWith(message: string): HTMLElement {
  const matched = alerts().filter((el) => renderedTextOf(el).includes(message));
  expect(matched.length, `inline alerts carrying "${message}"`).toBe(1);
  return matched[0];
}

/**
 * Mantine carries an Alert's colour as inline CSS variables and data attributes across its
 * subtree, so "red" is looked for across the subtree's class/style/data attributes.
 */
function colourMarkup(el: HTMLElement): string {
  return [el, ...Array.from(el.querySelectorAll<HTMLElement>("*"))]
    .flatMap((node) =>
      Array.from(node.attributes)
        .filter(
          (attr) => attr.name === "class" || attr.name === "style" || attr.name.startsWith("data-"),
        )
        .map((attr) => `${attr.name}=${attr.value}`),
    )
    .join(" ");
}

function notificationRoots(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>(NOTIFICATION_ROOT));
}

function tableRowNames(): string[] {
  return Array.from(document.querySelectorAll<HTMLTableRowElement>("tbody tr")).map((tr) =>
    (tr.querySelector("td")?.textContent ?? "").trim(),
  );
}

function assignCalls(): unknown[][] {
  const spy = documentNavigation.assign as unknown as { mock: { calls: unknown[][] } };
  return spy.mock.calls;
}

/** Puts a drift error, an export error and an export size line on the page (DoD-5). */
function seedOtherMessages(state: DatabasePageState): void {
  act(() => {
    runInAction(() => {
      state.errorMessage = DRIFT_ERROR;
      state.exportErrorMessage = EXPORT_ERROR;
      state.exportSizeBytes = SEEDED_SIZE_BYTES;
    });
  });
}

// ===========================================================================
describe("the page offers Import beside Export (US-077.AC-2, UC-061)", () => {
  it("an Import button with the upload icon sits beside Export — DoD-1", async () => {
    await renderLoaded();

    const button = importButton();
    expect(button).toBeInTheDocument();
    expect(button.querySelector(UPLOAD_ICON)).not.toBeNull();
    // Import is an addition, not a replacement.
    expect(exportButton()).toBeInTheDocument();
  });

  it.each(REPORT_CASES)("the Import button is present and enabled while the report is %s — DoD-1", async (_label, report) => {
    await renderLoaded({ report });

    // The report really was rendered in that state, so the button's presence is not vacuous.
    expect(tableRowNames()).toEqual(REPORT_TABLE_NAMES);
    expect(importButton()).toBeInTheDocument();
    expect(importButton()).not.toBeDisabled();
  });

  it("the file picker accepts JSON exports only — DoD-1", async () => {
    await renderLoaded();

    expect(fileInput().getAttribute("accept")).toBe(ACCEPT);
  });
});

// ===========================================================================
describe("choosing a file asks for confirmation before anything is sent", () => {
  it("choosing a file opens a dialog carrying the pinned title, consequence and confirm label — DoD-2", async () => {
    const { calls } = await renderLoaded();
    const user = newUser();

    await chooseFile(user, exportFile(importEnvelope()));

    const dialog = await replaceDialog();
    const text = renderedTextOf(dialog);
    expect(text).toContain(CONFIRM_TITLE);
    expect(text).toContain(CONFIRM_CONSEQUENCE);
    expect(within(dialog).getByRole("button", { name: CONFIRM_LABEL })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: CANCEL_NAME })).toBeInTheDocument();
    // The dialog really is open, and still nothing has been sent.
    expect(matching(calls, "POST", IMPORT_PATH)).toEqual([]);
  });

  it("the dialog raises no notification and navigates nowhere on its own — DoD-2", async () => {
    await renderLoaded();
    const user = newUser();

    await chooseFile(user, exportFile(importEnvelope()));

    await replaceDialog();
    expect(notificationRoots()).toEqual([]);
    expect(assignCalls()).toEqual([]);
  });
});

// ===========================================================================
describe("cancelling the confirm changes nothing", () => {
  it("Cancel closes the dialog, sends nothing and leaves the page as it was — DoD-3", async () => {
    const { calls } = await renderLoaded();
    const user = newUser();

    await chooseFile(user, exportFile(importEnvelope()));
    await replaceDialog();
    await cancelReplace(user);

    await waitFor(() => {
      expect(dialogs()).toEqual([]);
    });
    expect(matching(calls, "POST", IMPORT_PATH)).toEqual([]);
    expect(assignCalls()).toEqual([]);
    expect(notificationRoots()).toEqual([]);
    expect(alerts()).toEqual([]);
    // The page is as it was: the report, both actions, and no trace of the confirm.
    expect(tableRowNames()).toEqual(REPORT_TABLE_NAMES);
    expect(importButton()).not.toBeDisabled();
    expect(exportButton()).not.toBeDisabled();
    expect(readableText()).not.toContain(CONFIRM_CONSEQUENCE);
  });
});

// ===========================================================================
describe("confirming replaces the database and signs the administrator out", () => {
  it("confirming posts the file's parsed object to the admin import route — DoD-4", async () => {
    const envelope = importEnvelope();
    const { calls } = await renderLoaded();
    const user = newUser();

    await chooseFile(user, exportFile(envelope));
    await confirmReplace(user);

    const posts = matching(calls, "POST", IMPORT_PATH);
    expect(posts).toHaveLength(1);
    expect(posts[0].search).toBe("");
    expect(JSON.parse(posts[0].body ?? "null")).toEqual(envelope);
  });

  it("a 204 sends the browser to the sign-in page exactly once — DoD-4", async () => {
    const { calls } = await renderLoaded();
    const user = newUser();

    await chooseFile(user, exportFile(importEnvelope()));
    await confirmReplace(user);

    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(1);
    expect(assignCalls()).toHaveLength(1);
    expect(assignCalls()[0][0]).toBe(LOGIN_PATH);
  });
});

// ===========================================================================
describe("a refused import renders inline and nothing else", () => {
  it("a 409 closes the dialog and shows the server's message in a red Alert, with no notification and no navigation — DoD-5", async () => {
    await renderLoaded({
      importFailure: { code: "database_not_empty", message: NOT_EMPTY_MESSAGE, status: 409 },
    });
    const user = newUser();

    await chooseFile(user, exportFile(importEnvelope()));
    await confirmReplace(user);

    await waitFor(() => {
      expect(dialogs()).toEqual([]);
    });
    const alert = alertWith(NOT_EMPTY_MESSAGE);
    expect(colourMarkup(alert)).toMatch(/red/i);
    expect(notificationRoots()).toEqual([]);
    expect(assignCalls()).toEqual([]);
  });

  it("a 409 leaves the drift error, the export error and the export size line as they were — DoD-5", async () => {
    const { state } = await renderLoaded({
      importFailure: { code: "database_not_empty", message: NOT_EMPTY_MESSAGE, status: 409 },
    });
    seedOtherMessages(state);
    const user = newUser();
    // The three earlier messages really are on the page before the import runs.
    expect(readableText()).toContain(DRIFT_ERROR);
    expect(readableText()).toContain(EXPORT_ERROR);
    expect(readableText()).toContain(SEEDED_SIZE_TEXT);

    await chooseFile(user, exportFile(importEnvelope()));
    await confirmReplace(user);

    const text = readableText();
    expect(text).toContain(NOT_EMPTY_MESSAGE);
    expect(text).toContain(DRIFT_ERROR);
    expect(text).toContain(EXPORT_ERROR);
    expect(text).toContain(SEEDED_SIZE_TEXT);
  });

  it("a 400 export_invalid shows the server's message inline, with no notification and no navigation — DoD-6", async () => {
    const { calls } = await renderLoaded({
      importFailure: { code: "export_invalid", message: EXPORT_INVALID_MESSAGE, status: 400 },
    });
    const user = newUser();

    await chooseFile(user, exportFile(importEnvelope()));
    await confirmReplace(user);

    expect(matching(calls, "POST", IMPORT_PATH)).toHaveLength(1);
    const alert = alertWith(EXPORT_INVALID_MESSAGE);
    expect(colourMarkup(alert)).toMatch(/red/i);
    expect(notificationRoots()).toEqual([]);
    expect(assignCalls()).toEqual([]);
  });

  it("a file that is not JSON shows the unreadable-file sentence and sends nothing — DoD-6", async () => {
    const { calls } = await renderLoaded();
    const user = newUser();

    await chooseFile(user, unreadableFile());
    await confirmReplace(user);

    // The message really appeared, so the absences below are not a silent no-op.
    const alert = alertWith(UNREADABLE_MESSAGE);
    expect(renderedTextOf(alert)).toContain(UNREADABLE_MESSAGE);
    expect(colourMarkup(alert)).toMatch(/red/i);
    expect(matching(calls, "POST", IMPORT_PATH)).toEqual([]);
    expect(notificationRoots()).toEqual([]);
    expect(assignCalls()).toEqual([]);
  });
});

// ===========================================================================
describe("the page never shows what is inside the chosen file (US-078.AC-1, US-078.AC-3, R5)", () => {
  it("the fixture really carries the sentinel content — DoD-7", () => {
    const body = JSON.stringify(importEnvelope());
    for (const sentinel of SENTINELS) {
      expect(body, `sentinel ${sentinel} in the chosen file`).toContain(sentinel);
    }
    // None of the sentinels is a drift-report table name, so a hit could only come from the file.
    for (const name of REPORT_TABLE_NAMES) {
      expect(SENTINELS, `report table ${name}`).not.toContain(name);
    }
  });

  it("before a file is chosen none of its content appears on the page — DoD-7", async () => {
    await renderLoaded();

    // The page really rendered, with the control that would choose a file.
    expect(importButton()).toBeInTheDocument();
    const text = readableText();
    for (const sentinel of SENTINELS) {
      expect(text, `sentinel ${sentinel} must not be rendered`).not.toContain(sentinel);
    }
    expect(text).not.toMatch(COUNT_CLAIM);
  });

  it("after a file is chosen neither the page nor the dialog shows any of its content, count or tables — DoD-7", async () => {
    await renderLoaded();
    const user = newUser();

    await chooseFile(user, exportFile(importEnvelope()));

    // The file really was chosen: the replace confirm is open and names the action only.
    const dialog = await replaceDialog();
    expect(renderedTextOf(dialog)).toContain(CONFIRM_CONSEQUENCE);
    const text = readableText();
    for (const sentinel of SENTINELS) {
      expect(text, `sentinel ${sentinel} must not be rendered`).not.toContain(sentinel);
    }
    expect(renderedTextOf(dialog)).not.toMatch(COUNT_CLAIM);
    expect(text).not.toMatch(COUNT_CLAIM);
    // Only the drift report's own tables are named, and none of them is in the file.
    expect(tableRowNames()).toEqual(REPORT_TABLE_NAMES);
  });
});

// ===========================================================================
describe("030's Export is unchanged", () => {
  // DoD-10 — the rest of 030's export contract is held by `DatabasePage.export.test.tsx` and
  // `databasePageExport.test.ts`, both of which still run; this is the one regression case the
  // step asks for, taken with the Import control on the page.
  it("Export still requests the export route and still shows its size line — DoD-10", async () => {
    const { calls } = await renderLoaded();
    const user = newUser();

    await user.click(exportButton());
    await flush();

    expect(matching(calls, "GET", EXPORT_PATH)).toHaveLength(1);
    expect(readableText()).toContain(EXPORT_SIZE_TEXT);
    expect(matching(calls, "POST", IMPORT_PATH)).toEqual([]);
    expect(importButton()).toBeInTheDocument();
  });
});
