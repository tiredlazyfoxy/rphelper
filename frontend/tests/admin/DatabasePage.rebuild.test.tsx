// Fast feature 002 — vector-index-rebuild: the admin Database page's page half — the Rebuild
// index button, its confirm, the completion line and the rebuild's own inline failure Alert
// (DoD-17..DoD-20). The store half lives in `databasePageRebuild.test.ts` (DoD-15, DoD-16).
// DoD-21 is [manual/live] and carries no test.
//
// Expected behaviour comes from `docs/plans/fast/002.vector-index-rebuild/plan.md` (Interface
// intent "Database page", DoD-17..DoD-20) and `context.md` (the button joins the page-level
// action group beside Export and Import; always available — never gated on drift state; the
// confirm's consequence names the expense: re-embeds every memo and session, real time and real
// metered calls; failures in their own inline red `Alert`, never a notification; no count of
// user content on the page). Bindings come from the frozen `## Skeleton` record: the page is
// `<DatabasePage state={...} />` (no signature change); the confirm is `shared/ConfirmModal`
// whose Cancel is named `Cancel`; its open state is page-local, so it is observed through the
// rendered dialog only, never the store.
//
// The confirm's title and confirm label are not pinned by the spec, so the confirm button is
// located as the dialog's one button that is neither Cancel nor the modal's close control.
//
// Harness conventions follow `DatabasePage.import.test.tsx`: vitest with explicit imports; `fetch`
// stubbed per test and routed by method + exact pathname (the mount also loads
// `GET /api/admin/database/tables`); the page renders inside `AppProviders`, so "nothing was
// notified" is observable through `.mantine-Notification-root`.
import { notifications } from "@mantine/notifications";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { runInAction } from "mobx";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DatabasePage } from "../../src/admin/DatabasePage";
import { DatabasePageState, type DriftTableRow } from "../../src/admin/databasePageState";
import { AppProviders } from "../../src/shared/AppProviders";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; body: string | null };
type User = ReturnType<typeof userEvent.setup>;

// ---------------------------------------------------------------- the spec's names

const REPORT_PATH = "/api/admin/database/tables";
const REBUILD_PATH = "/api/admin/database/rebuild";

/** plan.md — "a **Rebuild index** button". */
const REBUILD_NAME = /^\s*rebuild index\s*$/i;
const EXPORT_NAME = "Export";
const IMPORT_NAME = "Import";
const CANCEL_NAME = /^\s*cancel\s*$/i;

/** plan.md "Rebuild report model". */
const REPORT_BODY = { tables_rebuilt: ["memo_vec", "session_vec", "memo_fts", "message_fts"] };

/** DoD-19 — a dimmed line saying the rebuild is complete. */
const COMPLETE_LINE = /rebuild(\s+is)?\s+complete/i;

const NO_MODEL_MESSAGE = "No embedding model is designated for this instance (zq-58 marker).";
const DRIFT_ERROR = "The drift report is on fire (zq-33 marker).";

const NOTIFICATION_ROOT = ".mantine-Notification-root";
const NON_RENDERED = "style, script, noscript, template";

/** R5 — a digit-bearing claim about user-owned material; a row count is one. */
const COUNT_CLAIM =
  /\d[\d,.\s]*\s*(rows?|records?|sessions?|characters?|setups?|messages?|memos?|users?|entries|vectors?|tables?)\b/i;

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

const REPORT_CASES: [string, DriftTableRow[]][] = [
  ["all in sync", IN_SYNC_REPORT],
  ["showing a drifted row", DRIFTED_REPORT],
  ["showing a missing row", MISSING_REPORT],
];

afterEach(() => {
  act(() => {
    notifications.clean();
  });
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- the server

type ServerOptions = {
  /** The drift report's answer; a function lets a test keep it pending or fail it. */
  report?: () => Promise<Response>;
  /** The rebuild route's answer. Defaults to a 200 with the report body. */
  rebuild?: () => Promise<Response>;
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

function reportOf(rows: readonly DriftTableRow[]): () => Promise<Response> {
  return () => Promise.resolve(jsonResponse({ tables: rows }, 200));
}

function serve(options: ServerOptions = {}) {
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>((input, init) => {
    const url = requestUrl(input);
    const method = requestMethod(input, init);
    calls.push({
      method,
      path: url.pathname,
      body: typeof init?.body === "string" ? init.body : null,
    });

    if (method === "GET" && url.pathname === REPORT_PATH) {
      return (options.report ?? reportOf(IN_SYNC_REPORT))();
    }
    if (method === "POST" && url.pathname === REBUILD_PATH) {
      return options.rebuild?.() ?? Promise.resolve(jsonResponse(REPORT_BODY, 200));
    }
    return Promise.resolve(errorEnvelope("not_found", `unexpected ${method} ${url.pathname}`, 404));
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

function rebuildPosts(calls: Seen[]): Seen[] {
  return calls.filter((call) => call.method === "POST" && call.path === REBUILD_PATH);
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
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

async function renderPage(options: ServerOptions = {}) {
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

function rebuildButton(): HTMLElement {
  return screen.getByRole("button", { name: REBUILD_NAME });
}

function exportButton(): HTMLElement {
  return screen.getByRole("button", { name: EXPORT_NAME });
}

function importButton(): HTMLElement {
  return screen.getByRole("button", { name: IMPORT_NAME });
}

function dialogs(): HTMLElement[] {
  return [...screen.queryAllByRole("dialog"), ...screen.queryAllByRole("alertdialog")];
}

async function openConfirm(user: User): Promise<HTMLElement> {
  await user.click(rebuildButton());
  await flush();
  return waitFor(() => {
    const found = dialogs();
    if (found.length !== 1) throw new Error(`expected one open confirm, found ${found.length}`);
    return found[0];
  });
}

function isCloseControl(button: HTMLElement): boolean {
  const className = button.getAttribute("class") ?? "";
  const label = button.getAttribute("aria-label") ?? "";
  return /close/i.test(className) || /^\s*close\s*$/i.test(label);
}

/** The confirm's own action: the one button in the dialog that is neither Cancel nor close. */
function confirmButtonIn(dialog: HTMLElement): HTMLElement {
  const candidates = within(dialog)
    .getAllByRole("button")
    .filter((button) => !CANCEL_NAME.test(button.textContent ?? "") && !isCloseControl(button));
  expect(candidates, "the confirm's action button").toHaveLength(1);
  return candidates[0];
}

function isLoading(button: HTMLElement): boolean {
  const flag = button.getAttribute("data-loading");
  return (flag !== null && flag !== "false") || button.querySelector(".mantine-Loader-root, [class*='Loader']") !== null;
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

function alerts(): HTMLElement[] {
  return screen.queryAllByRole("alert");
}

function alertsWith(message: string): HTMLElement[] {
  return alerts().filter((el) => renderedTextOf(el).includes(message));
}

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

/** The innermost element containing both nodes. */
function commonAncestor(a: HTMLElement, b: HTMLElement): HTMLElement {
  let node: HTMLElement | null = a;
  while (node !== null && !node.contains(b)) node = node.parentElement;
  if (node === null) throw new Error("no common ancestor");
  return node;
}

// ===========================================================================
describe("the Rebuild index button lives in the page-level action group and is always available", () => {
  it("renders beside Export and Import, in a group that does not hold the drift table — DoD-17", async () => {
    await renderPage();

    const rebuild = rebuildButton();
    expect(rebuild).toBeInTheDocument();
    expect(tableRowNames()).toEqual(REPORT_TABLE_NAMES);
    const group = commonAncestor(rebuild, exportButton());
    expect(group.contains(importButton())).toBe(true);
    expect(group.querySelector("table")).toBeNull();
  });

  it.each(REPORT_CASES)("is enabled while the drift report is %s — DoD-17", async (_label, report) => {
    await renderPage({ report: reportOf(report) });

    // The report really rendered in that state, so the button's state is not vacuous.
    expect(tableRowNames()).toEqual(REPORT_TABLE_NAMES);
    expect(rebuildButton()).toBeInTheDocument();
    expect(rebuildButton()).not.toBeDisabled();
  });

  it("is enabled while the drift report is still loading — DoD-17", async () => {
    const pending = deferred<Response>();
    await renderPage({ report: () => pending.promise });

    // The report really is still in flight: no table body yet.
    expect(document.querySelector("tbody")).toBeNull();
    expect(rebuildButton()).toBeInTheDocument();
    expect(rebuildButton()).not.toBeDisabled();

    pending.resolve(jsonResponse({ tables: IN_SYNC_REPORT }, 200));
    await flush();
  });

  it("is enabled when the drift report failed to load — DoD-17", async () => {
    await renderPage({
      report: () => Promise.resolve(errorEnvelope("internal_error", DRIFT_ERROR, 500)),
    });

    expect(rebuildButton()).toBeInTheDocument();
    expect(rebuildButton()).not.toBeDisabled();
  });
});

// ===========================================================================
describe("clicking Rebuild index asks for confirmation first", () => {
  it("opens a confirm whose consequence names the expense, and sends nothing yet — DoD-18", async () => {
    const { calls } = await renderPage();
    const user = newUser();

    const dialog = await openConfirm(user);

    const text = renderedTextOf(dialog);
    // context.md / forms-and-lists.md: re-embeds every memo and session; metered provider calls.
    expect(text).toMatch(/embed/i);
    expect(text).toMatch(/memo/i);
    expect(text).toMatch(/session/i);
    expect(text).toMatch(/metered|cost|charge|billed|paid|provider/i);
    expect(within(dialog).getByRole("button", { name: CANCEL_NAME })).toBeInTheDocument();
    expect(rebuildPosts(calls)).toEqual([]);
  });

  it("Cancel closes the confirm and sends no rebuild request — DoD-18", async () => {
    const { calls } = await renderPage();
    const user = newUser();

    const dialog = await openConfirm(user);
    await user.click(within(dialog).getByRole("button", { name: CANCEL_NAME }));
    await flush();

    await waitFor(() => {
      expect(dialogs()).toEqual([]);
    });
    expect(rebuildPosts(calls)).toEqual([]);
    expect(rebuildButton()).not.toBeDisabled();
    expect(notificationRoots()).toEqual([]);
  });
});

// ===========================================================================
describe("confirming runs the rebuild and reports completion", () => {
  it("sends one POST, holds the confirm loading while pending, then closes it and shows a completion line — DoD-19", async () => {
    const pending = deferred<Response>();
    const { calls } = await renderPage({ rebuild: () => pending.promise });
    const user = newUser();

    const dialog = await openConfirm(user);
    await user.click(confirmButtonIn(dialog));
    await flush();

    expect(rebuildPosts(calls)).toHaveLength(1);

    // While pending: the confirm is still open and in its loading state.
    const stillOpen = dialogs();
    expect(stillOpen).toHaveLength(1);
    expect(isLoading(confirmButtonIn(stillOpen[0]))).toBe(true);
    // The modal may hide the page behind it from the accessibility tree, so look through that.
    expect(screen.getByRole("button", { name: REBUILD_NAME, hidden: true })).toBeDisabled();
    expect(renderedTextOf(document.body)).not.toMatch(COMPLETE_LINE);

    pending.resolve(jsonResponse(REPORT_BODY, 200));
    await flush();

    await waitFor(() => {
      expect(dialogs()).toEqual([]);
    });
    expect(renderedTextOf(document.body)).toMatch(COMPLETE_LINE);
    expect(rebuildButton()).not.toBeDisabled();
  });

  it("the completion carries no count, raises no notification and no alert — DoD-19", async () => {
    await renderPage();
    const user = newUser();

    const dialog = await openConfirm(user);
    await user.click(confirmButtonIn(dialog));
    await flush();
    await waitFor(() => {
      expect(dialogs()).toEqual([]);
    });

    const text = renderedTextOf(document.body);
    // The line really is there, so the absences below are not vacuous.
    expect(text).toMatch(COMPLETE_LINE);
    expect(text).not.toMatch(COUNT_CLAIM);
    const line = Array.from(document.body.querySelectorAll<HTMLElement>("*")).find(
      (el) => el.children.length === 0 && COMPLETE_LINE.test(el.textContent ?? ""),
    );
    expect(line, "the completion line").toBeDefined();
    expect(line?.textContent ?? "").not.toMatch(/\d/);
    expect(notificationRoots()).toEqual([]);
    expect(alerts()).toEqual([]);
  });
});

// ===========================================================================
describe("a failed rebuild shows its own inline alert", () => {
  it("closes the confirm and shows the failure in a red inline Alert, no notification — DoD-20", async () => {
    const { calls } = await renderPage({
      rebuild: () => Promise.resolve(errorEnvelope("no_embedding_model", NO_MODEL_MESSAGE, 409)),
    });
    const user = newUser();

    const dialog = await openConfirm(user);
    await user.click(confirmButtonIn(dialog));
    await flush();

    expect(rebuildPosts(calls)).toHaveLength(1);
    await waitFor(() => {
      expect(dialogs()).toEqual([]);
    });
    const matched = alertsWith(NO_MODEL_MESSAGE);
    expect(matched).toHaveLength(1);
    expect(colourMarkup(matched[0])).toMatch(/red/i);
    expect(notificationRoots()).toEqual([]);
    expect(renderedTextOf(document.body)).not.toMatch(COMPLETE_LINE);
  });

  it("the rebuild's alert is distinct from the drift report's alert — DoD-20", async () => {
    const { state } = await renderPage({
      rebuild: () => Promise.resolve(errorEnvelope("no_embedding_model", NO_MODEL_MESSAGE, 409)),
    });
    act(() => {
      runInAction(() => {
        state.errorMessage = DRIFT_ERROR;
      });
    });
    await flush();
    const user = newUser();
    // The drift report's own alert really is on the page first.
    expect(alertsWith(DRIFT_ERROR)).toHaveLength(1);

    const dialog = await openConfirm(user);
    await user.click(confirmButtonIn(dialog));
    await flush();
    await waitFor(() => {
      expect(dialogs()).toEqual([]);
    });

    const rebuildAlerts = alertsWith(NO_MODEL_MESSAGE);
    const driftAlerts = alertsWith(DRIFT_ERROR);
    expect(rebuildAlerts).toHaveLength(1);
    expect(driftAlerts).toHaveLength(1);
    expect(rebuildAlerts[0]).not.toBe(driftAlerts[0]);
    expect(renderedTextOf(rebuildAlerts[0])).not.toContain(DRIFT_ERROR);
    expect(renderedTextOf(driftAlerts[0])).not.toContain(NO_MODEL_MESSAGE);
  });
});
