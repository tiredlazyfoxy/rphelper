// Feature 006, step 008 — the shared probe-on-open picker and the enabled-models modal
// (DoD-1..DoD-16). DoD-17 and DoD-18 are [manual/live].
//
// Expected behaviour comes from the step's Interface intent and Definition of done,
// 008.context.md and context.md (D10 rows persist / the union, D11 failed-probe resilience, D16
// MobX rules, D17 routes and the complete-set payload, D18 no confirm, R5, no success toasts,
// never optimistic). Bindings come from the frozen `### Step 008` record: `ModelPicker`,
// `loadAvailableModels(picker, serverId, signal?)`, the pure `modelOptionsOf(available, enabled)`,
// `EnabledModelsDraft(enabledModelNames)`, the pure `enabledModelsChanged` /
// `canSubmitEnabledModels`, the effect `submitEnabledModels(draft, serverId, onSaved, signal?)`, and
// `<EnabledModelsModal picker draft serverId serverName onClose onSaved />`, which starts the probe
// on mount and which the page mounts only while open. The page is rendered as in step 006/007's
// tests: `<LlmServersPage state={new LlmServersPageState()} />` under `AppProviders` +
// `MemoryRouter`. `fetch` is stubbed per test with a tiny in-memory backend (GET list, GET
// available-models, POST models — replacing the enabled set the way step 005's route does).
// `notifyFailure` is mocked at file level. The page-store module and the modal module are wrapped
// pass-through so the page's loads and the picker/draft each open hands the modal are observable —
// behaviour unchanged.
//
// Recognition conventions (from spec wording, for the verifier):
// - The modal: `role="dialog"`. One checkbox per model: `role="checkbox"` inside the dialog; a
//   checkbox belongs to a model when its label (aria-label, <label for>, aria-labelledby) contains
//   that model name as a whole token (a "no longer offered" mark may sit beside it).
// - The save control: the one dialog button named /save|submit|apply|update/i (not cancel/close).
// - The probe Loader: `.mantine-Loader-root` inside the dialog. The probe-failure error: an
//   `role="alert"` element inside the dialog. "Above the list": text inside the dialog preceding
//   the first checkbox in document order.
// - The row menu's item: `role="menuitem"` named /select\s+models/i inside the dropdown owned by
//   the row's trigger (step 006's menu idiom).
// - Notifications: `.mantine-Notification-root`.
//
// Model names are deliberately digit-free so DoD-10's "no number" scan is meaningful.
import { readFileSync } from "node:fs";
import path from "node:path";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { autorun, configure, isComputedProp, isObservableProp, runInAction, toJS } from "mobx";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EnabledModelsModal } from "../../src/admin/EnabledModelsModal";
import {
  canSubmitEnabledModels,
  EnabledModelsDraft,
  type EnabledModelsPayload,
  enabledModelsChanged,
  submitEnabledModels,
} from "../../src/admin/enabledModelsDraft";
import { LlmServersPage } from "../../src/admin/LlmServersPage";
import { type LlmServerRow, LlmServersPageState } from "../../src/admin/llmServersPageState";
import { loadAvailableModels, ModelPicker, modelOptionsOf } from "../../src/admin/modelPicker";
import { documentNavigation } from "../../src/shared/api";
import { AppProviders } from "../../src/shared/AppProviders";

const { notifyFailureSpy, spied } = vi.hoisted(() => ({
  notifyFailureSpy: vi.fn(),
  spied: { load: [] as unknown[][], opens: [] as Array<{ picker: unknown; draft: unknown; serverId: string }> },
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
  };
});
vi.mock("../../src/admin/EnabledModelsModal", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../src/admin/EnabledModelsModal")>();
  const { createElement } = await import("react");
  return {
    ...actual,
    EnabledModelsModal: (props: import("../../src/admin/EnabledModelsModal").EnabledModelsModalProps) => {
      if (!spied.opens.some((open) => open.picker === props.picker && open.draft === props.draft)) {
        spied.opens.push({ picker: props.picker, draft: props.draft, serverId: props.serverId });
      }
      return createElement(actual.EnabledModelsModal, props);
    },
  };
});

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type User = ReturnType<typeof userEvent.setup>;
type Seen = { method: string; path: string; search: string; body: unknown };

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const ADMIN_SRC = path.join(FRONTEND_ROOT, "src", "admin");
const PICKER_SOURCE = path.join(ADMIN_SRC, "modelPicker.ts");
const DRAFT_SOURCE = path.join(ADMIN_SRC, "enabledModelsDraft.ts");
const MODAL_SOURCE = path.join(ADMIN_SRC, "EnabledModelsModal.tsx");
const PAGE_SOURCE = path.join(ADMIN_SRC, "LlmServersPage.tsx");
const NEW_MODULES = [PICKER_SOURCE, DRAFT_SOURCE, MODAL_SOURCE];
const STEP_MODULES = [...NEW_MODULES, PAGE_SOURCE];

const LIST_PATH = "/api/admin/llm-servers";
const PROBE_PATH = /^\/api\/admin\/llm-servers\/([^/]+)\/available-models$/;
const MODELS_PATH = /^\/api\/admin\/llm-servers\/([^/]+)\/models$/;
const BIG_ID = "9007199254740993"; // 2^53 + 1 — not representable as a JS number
const PROBE_FAILURE = "The server at attic did not answer zq-five-oh-two.";
const SAVE_FAILURE = "The registry exploded zq-save.";

const SAVE_NAME = /save|submit|apply|update/i;
const NOT_SAVE_NAME = /cancel|close/i;
const SELECT_MODELS_ITEM = /select\s+models/i;
const NOTIFICATION_ROOT = ".mantine-Notification-root";
const LOADER = ".mantine-Loader-root";

/** Enabled: one still offered, one the server no longer offers. */
const ATTIC: LlmServerRow = {
  id: "7340032000000201",
  name: "Attic box",
  kind: "llamaswap",
  base_url: "http://attic.lan:8080",
  has_api_key: false,
  enabled_model_names: ["qwen-chat", "stale-old"],
  embedding_model_name: null,
  embedding_dim: null,
  last_test_at: null,
  last_test_ok: null,
  last_test_error: null,
  created_at: "2026-09-01T08:00:00.000000+00:00",
  updated_at: "2026-09-01T08:00:00.000000+00:00",
};
const ATTIC_OFFERED = ["mistral-small", "qwen-chat"];

/** Nothing enabled yet. */
const ORCHARD: LlmServerRow = {
  id: "7340032000000202",
  name: "Orchard cloud",
  kind: "openai",
  base_url: "https://api.orchard.example/v1",
  has_api_key: true,
  enabled_model_names: [],
  embedding_model_name: null,
  embedding_dim: null,
  last_test_at: null,
  last_test_ok: null,
  last_test_error: null,
  created_at: "2026-09-02T08:00:00.000000+00:00",
  updated_at: "2026-09-02T08:00:00.000000+00:00",
};
const ORCHARD_OFFERED = ["gemma-tiny", "mistral-small", "qwen-chat"];

const EVERYONE: LlmServerRow[] = [ATTIC, ORCHARD];
const DEFAULT_OFFERED: Record<string, readonly string[]> = {
  [ATTIC.id]: ATTIC_OFFERED,
  [ORCHARD.id]: ORCHARD_OFFERED,
};

beforeEach(() => {
  notifyFailureSpy.mockClear();
  spied.load.length = 0;
  spied.opens.length = 0;
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

function envelopeResponse(code: string, message: string, status: number): Response {
  return jsonResponse({ error: { code, message, detail: {} } }, status);
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function requestBody(init?: RequestInit): unknown {
  const raw = init?.body;
  return typeof raw === "string" ? JSON.parse(raw) : undefined;
}

function seen(mock: ReturnType<typeof stubFetch>): Seen[] {
  return mock.mock.calls.map(([input, init]) => {
    const url = requestUrl(input);
    return { method: requestMethod(input, init), path: url.pathname, search: url.search, body: requestBody(init) };
  });
}

function mutations(mock: ReturnType<typeof stubFetch>): Seen[] {
  return seen(mock).filter((call) => call.method !== "GET");
}

function probeCalls(mock: ReturnType<typeof stubFetch>, id: string): Seen[] {
  return seen(mock).filter((call) => call.method === "GET" && call.path === `${LIST_PATH}/${id}/available-models`);
}

/** The names a POST body carried, sorted — the payload is a set. */
function postedNames(call: Seen): string[] {
  const body = call.body as EnabledModelsPayload | undefined;
  expect(body, "POST body").toBeDefined();
  expect(Array.isArray(body?.model_names), "model_names is an array").toBe(true);
  return [...(body?.model_names ?? [])].sort();
}

function copyRows(rows: readonly LlmServerRow[]): LlmServerRow[] {
  return rows.map((row) => ({ ...row, enabled_model_names: [...row.enabled_model_names] }));
}

type Override = (method: string, path: string, body: unknown) => Promise<Response> | undefined;
type ServeOptions = {
  offered?: Record<string, readonly string[]>;
  probe?: (id: string) => Promise<Response> | undefined;
  override?: Override;
};

/**
 * A tiny in-memory backend: GET lists, GET `{id}/available-models` answers the server's offered
 * names, POST `{id}/models` replaces that row's enabled set with the posted names (200, the stored
 * names) — which is D17's replace semantics as step 005's route implements it.
 */
function serveServers(initial: readonly LlmServerRow[], options: ServeOptions = {}) {
  const rows = copyRows(initial);
  const offered = options.offered ?? DEFAULT_OFFERED;
  const mock = stubFetch((input, init) => {
    const method = requestMethod(input, init);
    const pathname = requestUrl(input).pathname;
    const body = requestBody(init);
    const custom = options.override?.(method, pathname, body);
    if (custom !== undefined) return custom;
    if (method === "GET" && pathname === LIST_PATH) {
      return Promise.resolve(jsonResponse({ servers: copyRows(rows) }, 200));
    }
    const probeMatch = PROBE_PATH.exec(pathname);
    if (method === "GET" && probeMatch !== null) {
      const id = probeMatch[1];
      const probed = options.probe?.(id);
      if (probed !== undefined) return probed;
      if (!rows.some((row) => row.id === id)) {
        return Promise.resolve(envelopeResponse("llm_server_not_found", "That connection does not exist.", 404));
      }
      return Promise.resolve(jsonResponse({ model_names: [...(offered[id] ?? [])] }, 200));
    }
    const modelsMatch = MODELS_PATH.exec(pathname);
    if (method === "POST" && modelsMatch !== null) {
      const row = rows.find((candidate) => candidate.id === modelsMatch[1]);
      if (row === undefined) {
        return Promise.resolve(envelopeResponse("llm_server_not_found", "That connection does not exist.", 404));
      }
      const names = Array.from(new Set(((body ?? {}) as EnabledModelsPayload).model_names ?? []));
      row.enabled_model_names = names;
      return Promise.resolve(jsonResponse({ enabled_model_names: [...names] }, 200));
    }
    return Promise.resolve(envelopeResponse("not_found", "no such route", 404));
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

function newUser(): User {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

// ---------------------------------------------------------------- snapshots

function pickerSnapshot(picker: ModelPicker) {
  return { available: [...picker.available], status: picker.status, errorMessage: picker.errorMessage };
}

function draftSnapshot(draft: EnabledModelsDraft) {
  return {
    selected: [...draft.selected],
    loaded: [...draft.loaded],
    serverErrors: toJS(draft.serverErrors),
    submitStatus: draft.submitStatus,
  };
}

function presentKeys(errors: Partial<Record<string, string>>): string[] {
  return Object.entries(errors)
    .filter(([, value]) => typeof value === "string" && value.length > 0)
    .map(([key]) => key)
    .sort();
}

function draftWith(names: readonly string[], fields: Partial<Pick<EnabledModelsDraft, "selected" | "submitStatus">> = {}) {
  const draft = new EnabledModelsDraft(names);
  runInAction(() => {
    Object.assign(draft, fields);
  });
  return draft;
}

// ---------------------------------------------------------------- render

function renderModal(row: LlmServerRow, picker: ModelPicker = new ModelPicker(), draft?: EnabledModelsDraft) {
  const usedDraft = draft ?? new EnabledModelsDraft(row.enabled_model_names);
  const onClose = vi.fn<() => void>();
  const onSaved = vi.fn<() => void>();
  const view = render(
    <AppProviders>
      <EnabledModelsModal
        picker={picker}
        draft={usedDraft}
        serverId={row.id}
        serverName={row.name}
        onClose={onClose}
        onSaved={onSaved}
      />
    </AppProviders>,
  );
  return { picker, draft: usedDraft, onClose, onSaved, view };
}

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

async function renderLoaded(rows: readonly LlmServerRow[] = EVERYONE, options: ServeOptions = {}) {
  const server = serveServers(rows, options);
  const rendered = renderPage();
  await flush();
  return { ...server, ...rendered };
}

// ---------------------------------------------------------------- dialog queries

function dialog(): HTMLElement {
  return screen.getByRole("dialog");
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function labelOf(input: HTMLElement): string {
  const parts = [input.getAttribute("aria-label") ?? ""];
  const labels = (input as HTMLInputElement).labels;
  if (labels) for (const label of Array.from(labels)) parts.push(label.textContent ?? "");
  for (const id of (input.getAttribute("aria-labelledby") ?? "").split(/\s+/).filter(Boolean)) {
    parts.push(document.getElementById(id)?.textContent ?? "");
  }
  return parts.join(" ");
}

function checkboxes(): HTMLInputElement[] {
  return within(dialog()).queryAllByRole("checkbox") as HTMLInputElement[];
}

function labelledWith(input: HTMLElement, name: string): boolean {
  return new RegExp(`(^|[^\\w-])${escapeRegExp(name)}([^\\w-]|$)`).test(labelOf(input));
}

function checkboxFor(name: string): HTMLInputElement {
  const found = checkboxes().filter((input) => labelledWith(input, name));
  expect(found, `checkboxes labelled ${name}`).toHaveLength(1);
  return found[0];
}

function checkboxNames(candidates: readonly string[]): string[] {
  return candidates.filter((name) => checkboxes().some((input) => labelledWith(input, name))).sort();
}

function checkedNames(candidates: readonly string[]): string[] {
  return candidates.filter((name) => checkboxes().some((input) => labelledWith(input, name) && input.checked)).sort();
}

function saveControl(): HTMLElement {
  const found = within(dialog())
    .queryAllByRole("button")
    .filter((el) => {
      const name = el.getAttribute("aria-label") ?? el.textContent ?? "";
      return SAVE_NAME.test(name) && !NOT_SAVE_NAME.test(name);
    });
  expect(found, "save controls in the dialog").toHaveLength(1);
  return found[0];
}

function loaderInDialog(): Element | null {
  return dialog().querySelector(LOADER);
}

function alertsInDialog(): HTMLElement[] {
  return within(dialog()).queryAllByRole("alert");
}

/** All text inside the dialog that precedes `target` in document order — "above the list". */
function textAbove(target: Node): string {
  const walker = document.createTreeWalker(dialog(), NodeFilter.SHOW_TEXT);
  const parts: string[] = [];
  for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
    if ((node.compareDocumentPosition(target) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0) {
      parts.push(node.textContent ?? "");
    }
  }
  return parts.join(" ").replace(/\s+/g, " ");
}

function notificationRoots(): Element[] {
  return Array.from(document.querySelectorAll(NOTIFICATION_ROOT));
}

async function toggle(user: User, name: string): Promise<void> {
  await user.click(checkboxFor(name));
  await flush(2);
}

async function save(user: User): Promise<void> {
  await user.click(saveControl());
  await flush();
}

async function waitForNoDialog(): Promise<void> {
  await waitFor(() => {
    expect(screen.queryByRole("dialog")).toBeNull();
  });
}

/** Close the modal the way an operator would: its cancel/close control if it has a named one, else Escape. */
async function closeModal(user: User): Promise<void> {
  const named = within(dialog())
    .queryAllByRole("button")
    .filter((el) => NOT_SAVE_NAME.test(el.getAttribute("aria-label") ?? el.textContent ?? ""));
  if (named.length > 0) {
    await user.click(named[0]);
  } else {
    const inside = checkboxes()[0] ?? dialog();
    inside.focus();
    await user.keyboard("{Escape}");
  }
  await waitForNoDialog();
}

// ---------------------------------------------------------------- page queries (step 006's idiom)

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

/** Row menu -> Select Models -> the dialog; then lets the probe settle. */
async function openSelectModels(user: User, name: string, settleProbe = true): Promise<void> {
  const menu = await openRowMenu(user, name);
  const item = await within(menu).findByRole("menuitem", { name: SELECT_MODELS_ITEM });
  await user.click(item);
  await screen.findByRole("dialog");
  if (settleProbe) await flush();
}

function storeRow(state: LlmServersPageState, id: string): LlmServerRow {
  const row = state.rows.find((candidate) => candidate.id === id);
  expect(row, `store row ${id}`).toBeDefined();
  return row as LlmServerRow;
}

function pageStoreSnapshot(state: LlmServersPageState) {
  return {
    rows: toJS(state.rows),
    status: state.status,
    errorMessage: state.errorMessage,
    testingId: state.testingId,
  };
}

function opens(): Array<{ picker: ModelPicker; draft: EnabledModelsDraft; serverId: string }> {
  return spied.opens as Array<{ picker: ModelPicker; draft: EnabledModelsDraft; serverId: string }>;
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
describe("opening probes once and lists what the server offers", () => {
  it("Select Models in a row's menu opens the modal and probes that server exactly once — DoD-1 (UC-012)", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(probeCalls(mock, ORCHARD.id)).toHaveLength(0);

    await openSelectModels(user, ORCHARD.name);
    await flush();

    expect(probeCalls(mock, ORCHARD.id)).toHaveLength(1);
    expect(probeCalls(mock, ATTIC.id)).toHaveLength(0);
    expect(probeCalls(mock, ORCHARD.id)[0].search).toBe("");
    expect(mutations(mock)).toEqual([]);
  });

  it("renders one checkbox per offered model — DoD-1 (UC-012)", async () => {
    const user = newUser();
    await renderLoaded();
    await openSelectModels(user, ORCHARD.name);

    expect(checkboxes()).toHaveLength(ORCHARD_OFFERED.length);
    expect(checkboxNames(ORCHARD_OFFERED)).toEqual([...ORCHARD_OFFERED].sort());
    for (const name of ORCHARD_OFFERED) checkboxFor(name);
  });

  it("the standalone modal starts the probe on mount, once, at that server's available-models route — DoD-1", async () => {
    const { mock } = serveServers(EVERYONE);
    renderModal(ORCHARD);
    await flush();
    expect(seen(mock).map((call) => `${call.method} ${call.path}`)).toEqual([
      `GET ${LIST_PATH}/${ORCHARD.id}/available-models`,
    ]);
    expect(checkboxes()).toHaveLength(3);
  });
});

// ===========================================================================
describe("the initial selection comes from the list payload", () => {
  it("a model already enabled on the server is checked on open, an offered one not enabled is not — DoD-2 (US-014.AC-1)", async () => {
    const user = newUser();
    await renderLoaded();
    await openSelectModels(user, ATTIC.name);

    expect(checkboxFor("qwen-chat")).toBeChecked();
    expect(checkboxFor("mistral-small")).not.toBeChecked();
  });

  it("the draft the page hands the modal is seeded from the row's enabled names, before the probe answers — DoD-2 (D11)", async () => {
    const user = newUser();
    const pending = deferred<Response>();
    await renderLoaded(EVERYONE, { probe: () => pending.promise });
    await openSelectModels(user, ATTIC.name, false);
    await flush(2);

    const [open] = opens();
    expect(open, "the modal was opened").toBeDefined();
    expect(open.serverId).toBe(ATTIC.id);
    expect(open.draft).toBeInstanceOf(EnabledModelsDraft);
    expect([...open.draft.selected].sort()).toEqual([...ATTIC.enabled_model_names].sort());
    expect(open.picker.status).toBe("loading");

    pending.resolve(jsonResponse({ model_names: ATTIC_OFFERED }, 200));
    await flush();
    expect([...open.draft.selected].sort()).toEqual([...ATTIC.enabled_model_names].sort());
  });

  it("the probe's answer never adds to the selection — DoD-2 (D11)", async () => {
    serveServers(EVERYONE);
    const { draft } = renderModal(ORCHARD);
    await flush();
    expect(checkboxes()).toHaveLength(3);
    expect(checkedNames(ORCHARD_OFFERED)).toEqual([]);
    expect(toJS(draft.selected)).toEqual([]);
  });

  it("the draft copies its seed: selected and loaded equal it and are independent of the array passed in — DoD-2", () => {
    const seed = ["qwen-chat", "stale-old"];
    const draft = new EnabledModelsDraft(seed);
    expect(toJS(draft.selected)).toEqual(seed);
    expect(toJS(draft.loaded)).toEqual(seed);
    seed.push("intruder");
    expect(toJS(draft.selected)).toEqual(["qwen-chat", "stale-old"]);
    expect(toJS(draft.loaded)).toEqual(["qwen-chat", "stale-old"]);
    runInAction(() => {
      draft.selected = draft.selected.filter((name) => name !== "qwen-chat");
    });
    expect(toJS(draft.loaded)).toEqual(["qwen-chat", "stale-old"]);
  });
});

// ===========================================================================
describe("the union rule — an enabled model the server no longer offers", () => {
  it("still renders and still shows as checked, and can be unchecked — DoD-3 (D10)", async () => {
    const user = newUser();
    await renderLoaded();
    await openSelectModels(user, ATTIC.name);

    expect(checkboxNames(["mistral-small", "qwen-chat", "stale-old"])).toEqual(["mistral-small", "qwen-chat", "stale-old"]);
    expect(checkboxes()).toHaveLength(3);
    const stale = checkboxFor("stale-old");
    expect(stale).toBeChecked();
    expect(stale).not.toBeDisabled();
    await toggle(user, "stale-old");
    expect(checkboxFor("stale-old")).not.toBeChecked();
  });

  it("unchecking it and saving POSTs a set without it, and the re-loaded row no longer reports it — DoD-3", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    await openSelectModels(user, ATTIC.name);
    await toggle(user, "stale-old");
    await save(user);
    await waitForNoDialog();

    const posts = mutations(mock);
    expect(posts).toHaveLength(1);
    expect(posts[0].method).toBe("POST");
    expect(posts[0].path).toBe(`${LIST_PATH}/${ATTIC.id}/models`);
    expect(postedNames(posts[0])).toEqual(["qwen-chat"]);
    expect(storeRow(state, ATTIC.id).enabled_model_names).not.toContain("stale-old");
    expect(storeRow(state, ATTIC.id).enabled_model_names).toContain("qwen-chat");
  });

  it("the standalone modal marks the union from the picker plus the draft's enabled names — DoD-3", async () => {
    serveServers(EVERYONE);
    renderModal(ATTIC);
    await flush();
    expect(checkedNames(["mistral-small", "qwen-chat", "stale-old"])).toEqual(["qwen-chat", "stale-old"]);
    expect(modelOptionsOf(ATTIC_OFFERED, ATTIC.enabled_model_names).find((option) => option.name === "stale-old")).toEqual({
      name: "stale-old",
      offered: false,
    });
  });
});

// ===========================================================================
describe("enabling and disabling", () => {
  it("checking an offered, not-enabled model and saving POSTs a set containing it; the re-loaded row reports it — DoD-4 (US-014.AC-1)", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    await openSelectModels(user, ATTIC.name);
    expect(checkboxFor("mistral-small")).not.toBeChecked();
    await toggle(user, "mistral-small");
    expect(checkboxFor("mistral-small")).toBeChecked();
    await save(user);
    await waitForNoDialog();

    const posts = mutations(mock);
    expect(posts).toHaveLength(1);
    expect(posts[0].path).toBe(`${LIST_PATH}/${ATTIC.id}/models`);
    expect(postedNames(posts[0])).toEqual(["mistral-small", "qwen-chat", "stale-old"]);
    expect(storeRow(state, ATTIC.id).enabled_model_names).toContain("mistral-small");
  });

  it("enabling on a server with nothing enabled POSTs just that model — DoD-4", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    await openSelectModels(user, ORCHARD.name);
    await toggle(user, "gemma-tiny");
    await save(user);
    await waitForNoDialog();
    expect(postedNames(mutations(mock)[0])).toEqual(["gemma-tiny"]);
    expect(storeRow(state, ORCHARD.id).enabled_model_names).toEqual(["gemma-tiny"]);
  });

  it("unchecking an enabled model and saving POSTs a set without it; the re-loaded row no longer reports it — DoD-5 (US-014.AC-2)", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    await openSelectModels(user, ATTIC.name);
    await toggle(user, "qwen-chat");
    expect(checkboxFor("qwen-chat")).not.toBeChecked();
    await save(user);
    await waitForNoDialog();

    const posts = mutations(mock);
    expect(posts).toHaveLength(1);
    expect(postedNames(posts[0])).toEqual(["stale-old"]);
    expect(storeRow(state, ATTIC.id).enabled_model_names).not.toContain("qwen-chat");
  });
});

// ===========================================================================
describe("the payload is the complete set", () => {
  it("saving after no change sends the same set that was loaded — DoD-6 (D17)", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    await openSelectModels(user, ATTIC.name);
    await save(user);
    await waitForNoDialog();

    const posts = mutations(mock);
    expect(posts).toHaveLength(1);
    expect(posts[0].path).toBe(`${LIST_PATH}/${ATTIC.id}/models`);
    expect(postedNames(posts[0])).toEqual(["qwen-chat", "stale-old"]);
    expect([...storeRow(state, ATTIC.id).enabled_model_names].sort()).toEqual(["qwen-chat", "stale-old"]);
  });

  it("a change of one model still sends every selected model, not a delta — DoD-6", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    await openSelectModels(user, ATTIC.name);
    await toggle(user, "mistral-small");
    await save(user);
    const body = mutations(mock)[0].body as Record<string, unknown>;
    expect(Object.keys(body)).toEqual(["model_names"]);
    expect(postedNames(mutations(mock)[0])).toEqual(["mistral-small", "qwen-chat", "stale-old"]);
  });

  it("the submit function posts the draft's complete selection to the models route — DoD-6", async () => {
    const { mock } = serveServers(EVERYONE);
    const draft = new EnabledModelsDraft(ATTIC.enabled_model_names);
    const onSaved = vi.fn<() => void>();
    await expect(submitEnabledModels(draft, ATTIC.id, onSaved)).resolves.toBeUndefined();
    const posts = mutations(mock);
    expect(posts).toHaveLength(1);
    expect(posts[0].method).toBe("POST");
    expect(posts[0].path).toBe(`${LIST_PATH}/${ATTIC.id}/models`);
    expect(posts[0].search).toBe("");
    expect(postedNames(posts[0])).toEqual(["qwen-chat", "stale-old"]);
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(draft.submitStatus).toBe("done");
  });

  it("changed compares the selection with what was loaded, as sets — DoD-6", () => {
    expect(enabledModelsChanged(new EnabledModelsDraft(["qwen-chat", "stale-old"]))).toBe(false);
    expect(enabledModelsChanged(draftWith(["qwen-chat", "stale-old"], { selected: ["stale-old", "qwen-chat"] }))).toBe(false);
    expect(enabledModelsChanged(draftWith(["qwen-chat", "stale-old"], { selected: ["qwen-chat"] }))).toBe(true);
    expect(enabledModelsChanged(draftWith(["qwen-chat"], { selected: ["qwen-chat", "mistral-small"] }))).toBe(true);
    expect(enabledModelsChanged(draftWith(["qwen-chat"], { selected: ["mistral-small"] }))).toBe(true);
    expect(enabledModelsChanged(new EnabledModelsDraft([]))).toBe(false);
  });
});

// ===========================================================================
describe("the empty selection is legal", () => {
  it("unchecking everything and saving POSTs an empty set and disables every model on that server — DoD-7 (US-014.AC-2)", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    await openSelectModels(user, ATTIC.name);
    await toggle(user, "qwen-chat");
    await toggle(user, "stale-old");
    expect(checkedNames(["mistral-small", "qwen-chat", "stale-old"])).toEqual([]);
    expect(saveControl()).not.toBeDisabled();
    await save(user);
    await waitForNoDialog();

    const posts = mutations(mock);
    expect(posts).toHaveLength(1);
    expect(posts[0].path).toBe(`${LIST_PATH}/${ATTIC.id}/models`);
    expect(posts[0].body).toEqual({ model_names: [] });
    expect(storeRow(state, ATTIC.id).enabled_model_names).toEqual([]);
    expect(storeRow(state, ORCHARD.id).enabled_model_names).toEqual(ORCHARD.enabled_model_names);
  });

  it("an empty draft can be submitted and posts an empty set — DoD-7", async () => {
    const { mock } = serveServers(EVERYONE);
    const draft = draftWith(ATTIC.enabled_model_names, { selected: [] });
    expect(canSubmitEnabledModels(draft)).toBe(true);
    const onSaved = vi.fn<() => void>();
    await submitEnabledModels(draft, ATTIC.id, onSaved);
    expect(mutations(mock).map((call) => call.body)).toEqual([{ model_names: [] }]);
    expect(onSaved).toHaveBeenCalledTimes(1);
  });

  it("can-submit is true whenever not submitting, and false while submitting — DoD-7, DoD-14", () => {
    expect(canSubmitEnabledModels(new EnabledModelsDraft([]))).toBe(true);
    expect(canSubmitEnabledModels(new EnabledModelsDraft(["qwen-chat"]))).toBe(true);
    expect(canSubmitEnabledModels(draftWith(["qwen-chat"], { submitStatus: "submitting" }))).toBe(false);
    expect(canSubmitEnabledModels(draftWith([], { submitStatus: "submitting" }))).toBe(false);
  });

  it("the save button is disabled while the save is in flight — DoD-7, DoD-14", async () => {
    const user = newUser();
    const pending = deferred<Response>();
    serveServers(EVERYONE, { override: (method) => (method === "POST" ? pending.promise : undefined) });
    renderModal(ATTIC);
    await flush();
    await user.click(saveControl());
    await flush(2);
    expect(saveControl()).toBeDisabled();
    pending.resolve(jsonResponse({ enabled_model_names: ATTIC.enabled_model_names }, 200));
    await flush();
  });
});

// ===========================================================================
describe("failed-probe resilience (D11)", () => {
  const PROBE_FAILURES: Array<[string, () => Promise<Response>]> = [
    ["a 502 llm_unreachable", () => Promise.resolve(envelopeResponse("llm_unreachable", PROBE_FAILURE, 502))],
    ["a transport failure", () => Promise.reject(new TypeError("Failed to fetch"))],
  ];

  it.each(PROBE_FAILURES)(
    "%s: the modal shows an error and still lists the enabled models, checked — DoD-8",
    async (_name, failure) => {
      const user = newUser();
      await renderLoaded(EVERYONE, { probe: () => failure() });
      await openSelectModels(user, ATTIC.name);

      const [open] = opens();
      expect(open.picker.status).toBe("failed");
      expect(toJS(open.picker.available)).toEqual([]);
      const message = open.picker.errorMessage;
      expect(typeof message).toBe("string");
      expect((message ?? "").length).toBeGreaterThan(0);

      const alerts = alertsInDialog();
      expect(alerts.length).toBeGreaterThan(0);
      expect(alerts.map((el) => el.textContent ?? "").join(" ")).toContain((message ?? "").trim());

      expect(checkboxNames(["mistral-small", "qwen-chat", "stale-old"])).toEqual(["qwen-chat", "stale-old"]);
      expect(checkboxes()).toHaveLength(2);
      expect(checkboxFor("qwen-chat")).toBeChecked();
      expect(checkboxFor("stale-old")).toBeChecked();
      expect([...open.draft.selected].sort()).toEqual(["qwen-chat", "stale-old"]);
      expect(loaderInDialog()).toBeNull();
    },
  );

  it.each(PROBE_FAILURES)("%s: saving then does not submit an empty set — DoD-8", async (_name, failure) => {
    const user = newUser();
    const { mock, state } = await renderLoaded(EVERYONE, { probe: () => failure() });
    await openSelectModels(user, ATTIC.name);
    await save(user);
    await waitForNoDialog();

    const posts = mutations(mock);
    expect(posts).toHaveLength(1);
    expect(posts[0].path).toBe(`${LIST_PATH}/${ATTIC.id}/models`);
    expect(postedNames(posts[0])).toEqual(["qwen-chat", "stale-old"]);
    expect([...storeRow(state, ATTIC.id).enabled_model_names].sort()).toEqual(["qwen-chat", "stale-old"]);
  });

  it("after a failed probe the enabled models are still saveable after an edit — DoD-8", async () => {
    const user = newUser();
    const { mock } = await renderLoaded(EVERYONE, {
      probe: () => Promise.resolve(envelopeResponse("llm_unreachable", PROBE_FAILURE, 502)),
    });
    await openSelectModels(user, ATTIC.name);
    await toggle(user, "stale-old");
    await save(user);
    expect(postedNames(mutations(mock)[0])).toEqual(["qwen-chat"]);
  });

  it("the loader records the error's message, empties the available list, and touches nothing else — DoD-8 (D11)", async () => {
    stubFetch(() => Promise.resolve(envelopeResponse("llm_unreachable", PROBE_FAILURE, 502)));
    const picker = new ModelPicker();
    runInAction(() => {
      picker.available = ["qwen-chat", "mistral-small"];
    });
    const draft = draftWith(ATTIC.enabled_model_names);
    const draftBefore = draftSnapshot(draft);

    await expect(loadAvailableModels(picker, ATTIC.id)).resolves.toBeUndefined();

    expect(picker.status).toBe("failed");
    expect(picker.errorMessage).toBe(PROBE_FAILURE);
    expect(toJS(picker.available)).toEqual([]);
    expect(draftSnapshot(draft)).toEqual(draftBefore);
  });

  it("a transport failure also lands as failed with a message and never rejects — DoD-8", async () => {
    stubFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    const picker = new ModelPicker();
    await expect(loadAvailableModels(picker, ATTIC.id)).resolves.toBeUndefined();
    expect(picker.status).toBe("failed");
    expect(toJS(picker.available)).toEqual([]);
    expect(typeof picker.errorMessage).toBe("string");
    expect((picker.errorMessage ?? "").length).toBeGreaterThan(0);
  });

  it("the standalone modal after a failed probe keeps the draft's selection and saves it — DoD-8", async () => {
    const user = newUser();
    const { mock } = serveServers(EVERYONE, {
      probe: () => Promise.resolve(envelopeResponse("llm_unreachable", PROBE_FAILURE, 502)),
    });
    const { picker, draft, onSaved } = renderModal(ATTIC);
    await flush();
    expect(picker.status).toBe("failed");
    expect(dialog().textContent ?? "").toContain(PROBE_FAILURE);
    expect([...draft.selected].sort()).toEqual(["qwen-chat", "stale-old"]);
    await save(user);
    expect(postedNames(mutations(mock)[0])).toEqual(["qwen-chat", "stale-old"]);
    expect(onSaved).toHaveBeenCalledTimes(1);
  });
});

// ===========================================================================
describe("the union function is pure", () => {
  it("returns the deduplicated union, sorted, each marked offered or not — DoD-9", () => {
    expect(modelOptionsOf(["qwen-chat", "mistral-small"], ["stale-old", "qwen-chat"])).toEqual([
      { name: "mistral-small", offered: true },
      { name: "qwen-chat", offered: true },
      { name: "stale-old", offered: false },
    ]);
  });

  it("handles either side empty and both empty — DoD-9", () => {
    expect(modelOptionsOf([], [])).toEqual([]);
    expect(modelOptionsOf(["qwen-chat", "gemma-tiny"], [])).toEqual([
      { name: "gemma-tiny", offered: true },
      { name: "qwen-chat", offered: true },
    ]);
    expect(modelOptionsOf([], ["stale-old", "qwen-chat"])).toEqual([
      { name: "qwen-chat", offered: false },
      { name: "stale-old", offered: false },
    ]);
  });

  it("deduplicates within and across the two arrays — DoD-9", () => {
    expect(
      modelOptionsOf(["qwen-chat", "qwen-chat", "gemma-tiny"], ["gemma-tiny", "stale-old", "stale-old"]),
    ).toEqual([
      { name: "gemma-tiny", offered: true },
      { name: "qwen-chat", offered: true },
      { name: "stale-old", offered: false },
    ]);
  });

  it("the order is stable whatever order either input arrives in — DoD-9", () => {
    const available = ["qwen-chat", "mistral-small", "gemma-tiny"];
    const enabled = ["stale-old", "qwen-chat", "aged-out"];
    const expected = modelOptionsOf(available, enabled);
    expect(expected.map((option) => option.name)).toEqual(["aged-out", "gemma-tiny", "mistral-small", "qwen-chat", "stale-old"]);
    const permutations = [
      [[...available].reverse(), enabled],
      [available, [...enabled].reverse()],
      [[...available].sort(), [...enabled].sort()],
      [["gemma-tiny", "qwen-chat", "mistral-small"], ["qwen-chat", "aged-out", "stale-old"]],
    ];
    for (const [a, e] of permutations) {
      expect(modelOptionsOf(a, e)).toEqual(expected);
    }
  });

  it("needs no render, store or network, does not mutate its inputs, and repeats itself — DoD-9", () => {
    const mock = stubFetch(() => Promise.reject(new Error("no network expected")));
    const available = Object.freeze(["qwen-chat", "mistral-small"]);
    const enabled = Object.freeze(["stale-old", "qwen-chat"]);
    const first = modelOptionsOf(available, enabled);
    const second = modelOptionsOf(available, enabled);
    expect(second).toEqual(first);
    expect(available).toEqual(["qwen-chat", "mistral-small"]);
    expect(enabled).toEqual(["stale-old", "qwen-chat"]);
    expect(mock).not.toHaveBeenCalled();
    expect(document.body.querySelector("[role='dialog']")).toBeNull();
  });
});

// ===========================================================================
describe("disabling is never refused and nothing offers to refuse it (R5)", () => {
  it("unchecking shows no warning, count, badge or confirm, and issues no request — DoD-10 (US-016.AC-1, UC-012)", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    await openSelectModels(user, ATTIC.name);
    const callsBefore = mock.mock.calls.length;
    const badgesBefore = dialog().querySelectorAll(".mantine-Badge-root").length;
    const alertsBefore = alertsInDialog().length;

    await toggle(user, "qwen-chat");
    await toggle(user, "stale-old");

    expect(mock.mock.calls.length, "unchecking issues no request").toBe(callsBefore);
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(dialog().querySelectorAll(".mantine-Badge-root").length).toBe(badgesBefore);
    expect(alertsInDialog().length).toBe(alertsBefore);
    const text = dialog().textContent ?? "";
    expect(text).not.toMatch(/\d/);
    expect(text).not.toMatch(/\bsessions?\b|\busers?\b|\bcharacters?\b|\bin use\b|are you sure|\bwarning\b|\bdepend/i);
  });

  it("saving a disable goes straight to the POST with no confirm dialog, and is accepted — DoD-10 (D18)", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    await openSelectModels(user, ATTIC.name);
    await toggle(user, "qwen-chat");
    await user.click(saveControl());
    expect(screen.queryAllByRole("dialog").length).toBeLessThanOrEqual(1);
    await flush();
    await waitForNoDialog();
    expect(mutations(mock)).toHaveLength(1);
    expect(postedNames(mutations(mock)[0])).toEqual(["stale-old"]);
    expect(storeRow(state, ATTIC.id).enabled_model_names).not.toContain("qwen-chat");
  });

  it("nothing rendered in the modal names a session, a user or a number — DoD-10 (UC-065, UC-066)", async () => {
    serveServers(EVERYONE);
    renderModal(ATTIC);
    await flush();
    const text = dialog().textContent ?? "";
    expect(text).not.toMatch(/\d/);
    expect(text).not.toMatch(/\bsessions?\b|\busers?\b|\bcharacters?\b|are you sure/i);
  });

  it("the modal and draft source name no session or user and use no confirm dialog — DoD-10", () => {
    for (const file of [MODAL_SOURCE, DRAFT_SOURCE]) {
      const source = readSource(file);
      expect(source, path.basename(file)).not.toMatch(/\bsessions?\b|\busers?\b|are you sure/i);
      expect(importSpecifiers(readFileSync(file, "utf8")).filter((spec) => /ConfirmModal/.test(spec)), path.basename(file)).toEqual([]);
      expect(source, path.basename(file)).not.toMatch(/\bwindow\.confirm\b|\bconfirm\s*\(/);
    }
  });
});

// ===========================================================================
describe("a save failure lands on the general key above the list", () => {
  const FAILURES: Array<[string, () => Promise<Response>]> = [
    ["a 500 envelope", () => Promise.resolve(envelopeResponse("internal_error", SAVE_FAILURE, 500))],
    [
      "a 500 envelope whose prose names a model",
      () => Promise.resolve(envelopeResponse("internal_error", "qwen-chat must stay enabled for the session.", 500)),
    ],
    ["a 404 llm_server_not_found", () => Promise.resolve(envelopeResponse("llm_server_not_found", "That connection does not exist zq.", 404))],
    ["an unknown 409 code", () => Promise.resolve(envelopeResponse("mystery_conflict", "Conflict zq.", 409))],
    [
      "FastAPI's own 422",
      () =>
        Promise.resolve(
          jsonResponse({ detail: [{ type: "list_type", loc: ["body", "model_names"], msg: "Input should be a valid list", input: "x" }] }, 422),
        ),
    ],
    [
      "a 502 with a malformed body",
      () => Promise.resolve(new Response("<html>Bad Gateway</html>", { status: 502, headers: { "Content-Type": "text/html" } })),
    ],
    ["a transport failure", () => Promise.reject(new TypeError("Failed to fetch"))],
  ];

  it.each(FAILURES)("%s: renders on the general key above the list, selection as left, modal open — DoD-11", async (_name, failure) => {
    vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    const user = newUser();
    serveServers(EVERYONE, { override: (method) => (method === "POST" ? failure() : undefined) });
    const { draft, onSaved, onClose } = renderModal(ATTIC);
    await flush();
    await toggle(user, "qwen-chat");
    await toggle(user, "mistral-small");
    await save(user);

    expect(presentKeys(draft.serverErrors)).toEqual(["general"]);
    const general = (draft.serverErrors.general as string).replace(/\s+/g, " ").trim();
    expect(general.length).toBeGreaterThan(0);
    const first = checkboxes()[0];
    expect(first, "the list still renders").toBeDefined();
    expect(textAbove(first)).toContain(general);

    expect(checkedNames(["mistral-small", "qwen-chat", "stale-old"])).toEqual(["mistral-small", "stale-old"]);
    expect([...draft.selected].sort()).toEqual(["mistral-small", "stale-old"]);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(draft.submitStatus).not.toBe("done");
    expect(saveControl()).not.toBeDisabled();
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it.each(FAILURES)("%s: the submit function never rejects and leaves the selection untouched — DoD-11", async (_name, failure) => {
    vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(() => failure());
    const draft = draftWith(ATTIC.enabled_model_names, { selected: ["stale-old", "gemma-tiny"] });
    const onSaved = vi.fn<() => void>();
    await expect(submitEnabledModels(draft, ATTIC.id, onSaved)).resolves.toBeUndefined();
    expect(presentKeys(draft.serverErrors)).toEqual(["general"]);
    expect(toJS(draft.selected)).toEqual(["stale-old", "gemma-tiny"]);
    expect(toJS(draft.loaded)).toEqual(ATTIC.enabled_model_names);
    expect(onSaved).not.toHaveBeenCalled();
    expect(draft.submitStatus).not.toBe("done");
  });

  it("through the page, a failed save keeps the modal open and the store untouched — DoD-11", async () => {
    const user = newUser();
    const { state } = await renderLoaded(EVERYONE, {
      override: (method) => (method === "POST" ? Promise.resolve(envelopeResponse("internal_error", SAVE_FAILURE, 500)) : undefined),
    });
    const before = pageStoreSnapshot(state);
    await openSelectModels(user, ATTIC.name);
    await toggle(user, "qwen-chat");
    await save(user);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(checkboxFor("qwen-chat")).not.toBeChecked();
    expect(pageStoreSnapshot(state)).toEqual(before);
  });
});

// ===========================================================================
describe("success closes and re-loads; never optimistic, no toast", () => {
  it("on success the modal closes and the page re-loads its list through its store — DoD-12", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    const loadsBefore = spied.load.length;
    await openSelectModels(user, ATTIC.name);
    await toggle(user, "mistral-small");
    await save(user);
    await waitForNoDialog();

    const calls = seen(mock);
    const postIndex = calls.findIndex((call) => call.method === "POST");
    expect(postIndex).toBeGreaterThanOrEqual(0);
    expect(calls.slice(postIndex + 1).some((call) => call.method === "GET" && call.path === LIST_PATH)).toBe(true);
    expect(spied.load.length).toBeGreaterThan(loadsBefore);
    expect(spied.load[spied.load.length - 1][0]).toBe(state);
    rowFor(ATTIC.name);
    expect(storeRow(state, ATTIC.id).enabled_model_names).toContain("mistral-small");
  });

  it("the row reflects the re-load, not a local write — a change only the server knows appears too — DoD-12", async () => {
    const user = newUser();
    const { rows, state } = await renderLoaded();
    const orchard = rows.find((row) => row.id === ORCHARD.id) as LlmServerRow;
    orchard.enabled_model_names = ["server-only"];
    await openSelectModels(user, ATTIC.name);
    await save(user);
    await waitForNoDialog();
    expect(storeRow(state, ORCHARD.id).enabled_model_names).toEqual(["server-only"]);
  });

  it("nothing is written into the page store while the save is in flight — DoD-12", async () => {
    const user = newUser();
    const pending = deferred<Response>();
    const { state } = await renderLoaded(EVERYONE, {
      override: (method) => (method === "POST" ? pending.promise : undefined),
    });
    const before = pageStoreSnapshot(state);
    await openSelectModels(user, ATTIC.name);
    await toggle(user, "qwen-chat");
    await save(user);
    expect(pageStoreSnapshot(state)).toEqual(before);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    pending.resolve(envelopeResponse("internal_error", SAVE_FAILURE, 500));
    await flush();
    expect(pageStoreSnapshot(state)).toEqual(before);
  });

  it("no success notification and no success message — DoD-12", async () => {
    const user = newUser();
    await renderLoaded();
    await openSelectModels(user, ATTIC.name);
    await toggle(user, "mistral-small");
    await save(user);
    await waitForNoDialog();
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(document.body.textContent ?? "").not.toMatch(/\bsuccess(ful|fully)?\b/i);
  });

  it("the standalone modal calls onSaved exactly once on success — DoD-12", async () => {
    const user = newUser();
    serveServers(EVERYONE);
    const { onSaved, draft } = renderModal(ATTIC);
    await flush();
    await save(user);
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(draft.submitStatus).toBe("done");
    expect(notificationRoots()).toEqual([]);
  });

  it("no module of this step imports notifyFailure or Mantine's notifications — DoD-12", () => {
    const offenders = STEP_MODULES.flatMap((file) =>
      importSpecifiers(readFileSync(file, "utf8"))
        .filter((spec) => /notifyFailure|@mantine\/notifications/.test(spec))
        .map((spec) => `${path.basename(file)} imports ${spec}`),
    );
    expect(offenders).toEqual([]);
  });
});

// ===========================================================================
describe("the Loader is gated on the probe status", () => {
  it("a Loader renders while the probe is in flight, even when enabled names exist — DoD-13", async () => {
    const pending = deferred<Response>();
    serveServers(EVERYONE, { probe: () => pending.promise });
    const { picker } = renderModal(ATTIC);
    await flush(2);
    expect(picker.status).toBe("loading");
    expect(loaderInDialog()).not.toBeNull();

    pending.resolve(jsonResponse({ model_names: ATTIC_OFFERED }, 200));
    await flush();
    expect(picker.status).toBe("ready");
    expect(loaderInDialog()).toBeNull();
  });

  it("a Loader renders while loading even if an available list is already present — DoD-13", async () => {
    const pending = deferred<Response>();
    serveServers(EVERYONE, { probe: () => pending.promise });
    const picker = new ModelPicker();
    runInAction(() => {
      picker.available = ["qwen-chat"];
    });
    renderModal(ORCHARD, picker);
    await flush(2);
    expect(picker.status).toBe("loading");
    expect(loaderInDialog()).not.toBeNull();
    pending.resolve(jsonResponse({ model_names: ORCHARD_OFFERED }, 200));
    await flush();
  });

  it("an empty but ready listing shows no Loader — DoD-13", async () => {
    serveServers(EVERYONE, { offered: { [ORCHARD.id]: [] } });
    const { picker } = renderModal(ORCHARD);
    await flush();
    expect(picker.status).toBe("ready");
    expect(toJS(picker.available)).toEqual([]);
    expect(loaderInDialog()).toBeNull();
  });

  it("a failed probe shows no Loader — DoD-13", async () => {
    serveServers(EVERYONE, { probe: () => Promise.resolve(envelopeResponse("llm_unreachable", PROBE_FAILURE, 502)) });
    const { picker } = renderModal(ORCHARD);
    await flush();
    expect(picker.status).toBe("failed");
    expect(loaderInDialog()).toBeNull();
  });

  it("the loader function walks loading to ready and sets the available names — DoD-13, DoD-1", async () => {
    const pending = deferred<Response>();
    const mock = stubFetch(() => pending.promise);
    const picker = new ModelPicker();
    expect(picker.status).toBe("idle");
    const running = loadAvailableModels(picker, ATTIC.id);
    await settle();
    expect(picker.status).toBe("loading");
    pending.resolve(jsonResponse({ model_names: ATTIC_OFFERED }, 200));
    await expect(running).resolves.toBeUndefined();
    expect(picker.status).toBe("ready");
    expect([...picker.available].sort()).toEqual([...ATTIC_OFFERED].sort());
    expect(seen(mock).map((call) => `${call.method} ${call.path}`)).toEqual([`GET ${LIST_PATH}/${ATTIC.id}/available-models`]);
  });
});

// ===========================================================================
describe("data classes; free-function effects (D16)", () => {
  it("neither class prototype carries a method or a getter — DoD-14", () => {
    expect(Object.getOwnPropertyNames(ModelPicker.prototype)).toEqual(["constructor"]);
    expect(Object.getOwnPropertyNames(EnabledModelsDraft.prototype)).toEqual(["constructor"]);
  });

  it("the picker's own fields are observable, none computed, none a function, and start idle — DoD-14", () => {
    const picker = new ModelPicker();
    const names = Object.getOwnPropertyNames(picker);
    expect([...names].sort()).toEqual(["available", "errorMessage", "status"]);
    const record = picker as unknown as Record<string, unknown>;
    for (const name of names) {
      expect(isObservableProp(picker, name), name).toBe(true);
      expect(isComputedProp(picker, name), name).toBe(false);
      expect(typeof record[name], name).not.toBe("function");
    }
    expect(pickerSnapshot(picker)).toEqual({ available: [], status: "idle", errorMessage: null });
  });

  it("the draft's own fields are observable, none computed, none a function, and start idle — DoD-14", () => {
    const draft = new EnabledModelsDraft(["qwen-chat"]);
    const names = Object.getOwnPropertyNames(draft);
    expect([...names].sort()).toEqual(["loaded", "selected", "serverErrors", "submitStatus"]);
    const record = draft as unknown as Record<string, unknown>;
    for (const name of names) {
      expect(isObservableProp(draft, name), name).toBe(true);
      expect(isComputedProp(draft, name), name).toBe(false);
      expect(typeof record[name], name).not.toBe("function");
    }
    expect(draftSnapshot(draft)).toEqual({ selected: ["qwen-chat"], loaded: ["qwen-chat"], serverErrors: {}, submitStatus: "idle" });
  });

  it("the derivations are pure: no writes, no network, same answer twice — DoD-14", () => {
    const mock = stubFetch(() => Promise.reject(new Error("no network expected")));
    for (const draft of [new EnabledModelsDraft([]), draftWith(["qwen-chat"], { selected: ["stale-old"] })]) {
      const before = draftSnapshot(draft);
      const first = [enabledModelsChanged(draft), canSubmitEnabledModels(draft)];
      const second = [enabledModelsChanged(draft), canSubmitEnabledModels(draft)];
      expect(second).toEqual(first);
      expect(draftSnapshot(draft)).toEqual(before);
    }
    expect(mock).not.toHaveBeenCalled();
  });

  it("both effects write only inside actions (strict MobX raises no warning) — DoD-14", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    configure({ enforceActions: "always" });
    try {
      const watchPicker = (picker: ModelPicker) =>
        autorun(() => {
          void picker.status;
          void picker.errorMessage;
          void JSON.stringify(toJS(picker.available));
        });
      const watchDraft = (draft: EnabledModelsDraft) =>
        autorun(() => {
          void JSON.stringify(toJS(draft.selected));
          void JSON.stringify(toJS(draft.loaded));
          void JSON.stringify(toJS(draft.serverErrors));
          void draft.submitStatus;
        });

      serveServers(EVERYONE);
      const okPicker = new ModelPicker();
      const d1 = watchPicker(okPicker);
      await loadAvailableModels(okPicker, ATTIC.id);
      d1();
      const okDraft = new EnabledModelsDraft(ATTIC.enabled_model_names);
      const d2 = watchDraft(okDraft);
      await submitEnabledModels(okDraft, ATTIC.id, () => {});
      d2();

      vi.unstubAllGlobals();
      stubFetch(() => Promise.resolve(envelopeResponse("llm_unreachable", PROBE_FAILURE, 502)));
      const badPicker = new ModelPicker();
      const d3 = watchPicker(badPicker);
      await loadAvailableModels(badPicker, ATTIC.id);
      d3();
      const badDraft = new EnabledModelsDraft(ATTIC.enabled_model_names);
      const d4 = watchDraft(badDraft);
      await submitEnabledModels(badDraft, ATTIC.id, () => {});
      d4();
    } finally {
      configure({ enforceActions: "observed" });
    }
    const mobxWarnings = warn.mock.calls.filter((args) => args.some((arg) => String(arg).includes("[MobX]")));
    expect(mobxWarnings).toEqual([]);
  });

  it("the loader given an already-aborted signal writes nothing — DoD-14", async () => {
    serveServers(EVERYONE);
    const picker = new ModelPicker();
    const before = pickerSnapshot(picker);
    const controller = new AbortController();
    controller.abort();
    await expect(loadAvailableModels(picker, ATTIC.id, controller.signal)).resolves.toBeUndefined();
    await settle();
    expect(pickerSnapshot(picker)).toEqual(before);
  });

  it("the submit given an already-aborted signal writes nothing and saves nothing — DoD-14", async () => {
    serveServers(EVERYONE);
    const draft = draftWith(ATTIC.enabled_model_names, { selected: ["qwen-chat"] });
    const before = draftSnapshot(draft);
    const controller = new AbortController();
    controller.abort();
    const onSaved = vi.fn<() => void>();
    await expect(submitEnabledModels(draft, ATTIC.id, onSaved, controller.signal)).resolves.toBeUndefined();
    await settle();
    expect(draftSnapshot(draft)).toEqual(before);
    expect(onSaved).not.toHaveBeenCalled();
  });

  it.each<[string, () => Response]>([
    ["a listing", () => jsonResponse({ model_names: ATTIC_OFFERED }, 200)],
    ["a failure", () => envelopeResponse("llm_unreachable", PROBE_FAILURE, 502)],
  ])("%s arriving after the loader's abort is not written — DoD-14", async (_name, answer) => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const picker = new ModelPicker();
    const controller = new AbortController();
    const running = loadAvailableModels(picker, ATTIC.id, controller.signal);
    await settle();
    const atAbort = pickerSnapshot(picker);
    controller.abort();
    pending.resolve(answer());
    await expect(running).resolves.toBeUndefined();
    await settle();
    expect(pickerSnapshot(picker)).toEqual(atAbort);
  });

  it.each<[string, () => Response]>([
    ["a success", () => jsonResponse({ enabled_model_names: ["qwen-chat"] }, 200)],
    ["a failure", () => envelopeResponse("internal_error", SAVE_FAILURE, 500)],
  ])("%s arriving after the submit's abort is not written — DoD-14", async (_name, answer) => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const draft = draftWith(ATTIC.enabled_model_names, { selected: ["qwen-chat"] });
    const controller = new AbortController();
    const onSaved = vi.fn<() => void>();
    const running = submitEnabledModels(draft, ATTIC.id, onSaved, controller.signal);
    await settle();
    const atAbort = draftSnapshot(draft);
    controller.abort();
    pending.resolve(answer());
    await expect(running).resolves.toBeUndefined();
    await settle();
    expect(draftSnapshot(draft)).toEqual(atAbort);
    expect(onSaved).not.toHaveBeenCalled();
    expect(draft.submitStatus).not.toBe("done");
    expect(draft.serverErrors.general).toBeUndefined();
  });

  it.each<[string, () => Response]>([
    ["a listing", () => jsonResponse({ model_names: ATTIC_OFFERED }, 200)],
    ["a failure", () => envelopeResponse("llm_unreachable", PROBE_FAILURE, 502)],
  ])("unmounting the modal mid-probe means %s arriving later writes nothing — DoD-14", async (_name, answer) => {
    const pending = deferred<Response>();
    serveServers(EVERYONE, { probe: () => pending.promise });
    const { picker, view } = renderModal(ATTIC);
    await flush(2);
    expect(picker.status).toBe("loading");
    view.unmount();
    const atClose = pickerSnapshot(picker);
    pending.resolve(answer());
    await settle(8);
    expect(pickerSnapshot(picker)).toEqual(atClose);
  });

  it("closing the modal from the page mid-probe writes nothing to that open's picker afterwards — DoD-14", async () => {
    const user = newUser();
    const pending = deferred<Response>();
    await renderLoaded(EVERYONE, { probe: () => pending.promise });
    await openSelectModels(user, ATTIC.name, false);
    await flush(2);
    const [open] = opens();
    expect(open.picker.status).toBe("loading");
    await closeModal(user);
    const atClose = pickerSnapshot(open.picker);
    pending.resolve(jsonResponse({ model_names: ATTIC_OFFERED }, 200));
    await flush();
    expect(pickerSnapshot(open.picker)).toEqual(atClose);
  });

  it("the picker and draft modules use runInAction and makeAutoObservable — DoD-14", () => {
    for (const file of [PICKER_SOURCE, DRAFT_SOURCE]) {
      const source = readSource(file);
      expect(source, path.basename(file)).toMatch(/\brunInAction\b/);
      expect(source, path.basename(file)).toMatch(/\bmakeAutoObservable\b/);
    }
  });
});

// ===========================================================================
describe("a fresh picker and a fresh draft per open", () => {
  it("reopening after an unsaved change shows the stored state, not the abandoned one — DoD-15", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    await openSelectModels(user, ATTIC.name);
    await toggle(user, "qwen-chat");
    await toggle(user, "mistral-small");
    expect(checkedNames(["mistral-small", "qwen-chat", "stale-old"])).toEqual(["mistral-small", "stale-old"]);
    await closeModal(user);

    await openSelectModels(user, ATTIC.name);
    expect(checkedNames(["mistral-small", "qwen-chat", "stale-old"])).toEqual(["qwen-chat", "stale-old"]);
    expect(mutations(mock)).toEqual([]);
  });

  it("each open hands the modal a new picker and a new draft, and re-probes — DoD-15", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    await openSelectModels(user, ATTIC.name);
    await toggle(user, "qwen-chat");
    await closeModal(user);
    await openSelectModels(user, ATTIC.name);

    const all = opens();
    expect(all).toHaveLength(2);
    expect(all[1].picker).toBeInstanceOf(ModelPicker);
    expect(all[1].draft).toBeInstanceOf(EnabledModelsDraft);
    expect(all[1].picker).not.toBe(all[0].picker);
    expect(all[1].draft).not.toBe(all[0].draft);
    expect(toJS(all[0].draft.selected)).toEqual(["stale-old"]);
    expect([...all[1].draft.selected].sort()).toEqual(["qwen-chat", "stale-old"]);
    expect(probeCalls(mock, ATTIC.id)).toHaveLength(2);
  });

  it("a failed probe on one open does not survive into the next — DoD-15", async () => {
    const user = newUser();
    let fail = true;
    await renderLoaded(EVERYONE, {
      probe: () => (fail ? Promise.resolve(envelopeResponse("llm_unreachable", PROBE_FAILURE, 502)) : undefined),
    });
    await openSelectModels(user, ATTIC.name);
    expect(dialog().textContent ?? "").toContain(PROBE_FAILURE);
    await closeModal(user);
    fail = false;
    await openSelectModels(user, ATTIC.name);
    expect(dialog().textContent ?? "").not.toContain(PROBE_FAILURE);
    expect(checkboxes()).toHaveLength(3);
  });

  it("the modal is mounted only while open, and opening Select Models leaves the page store unchanged — DoD-15", async () => {
    const user = newUser();
    const { state } = await renderLoaded();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(opens()).toEqual([]);
    const before = pageStoreSnapshot(state);
    await openSelectModels(user, ATTIC.name);
    expect(pageStoreSnapshot(state)).toEqual(before);
    await closeModal(user);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(pageStoreSnapshot(state)).toEqual(before);
    const page = readSource(PAGE_SOURCE);
    expect(page).toMatch(/new\s+ModelPicker\s*\(/);
    expect(page).toMatch(/new\s+EnabledModelsDraft\s*\(/);
  });
});

// ===========================================================================
describe("ids are strings; no stylesheet", () => {
  it("a row with an id beyond MAX_SAFE_INTEGER is probed and saved with that id verbatim — DoD-16", async () => {
    const user = newUser();
    const big: LlmServerRow = { ...ATTIC, id: BIG_ID };
    const { mock, state } = await renderLoaded([big, ORCHARD], { offered: { [BIG_ID]: ATTIC_OFFERED } });
    await openSelectModels(user, big.name);
    expect(opens()[0].serverId).toBe(BIG_ID);
    expect(typeof opens()[0].serverId).toBe("string");
    await toggle(user, "mistral-small");
    await save(user);
    await waitForNoDialog();

    expect(probeCalls(mock, BIG_ID)).toHaveLength(1);
    expect(mutations(mock).map((call) => `${call.method} ${call.path}`)).toEqual([`POST ${LIST_PATH}/${BIG_ID}/models`]);
    expect(storeRow(state, BIG_ID).enabled_model_names).toContain("mistral-small");
  });

  it("the free functions use the string id they are given — DoD-16", async () => {
    const { mock } = serveServers([{ ...ATTIC, id: BIG_ID }], { offered: { [BIG_ID]: ATTIC_OFFERED } });
    await loadAvailableModels(new ModelPicker(), BIG_ID);
    await submitEnabledModels(new EnabledModelsDraft(["qwen-chat"]), BIG_ID, () => {});
    expect(seen(mock).map((call) => `${call.method} ${call.path}`)).toEqual([
      `GET ${LIST_PATH}/${BIG_ID}/available-models`,
      `POST ${LIST_PATH}/${BIG_ID}/models`,
    ]);
  });

  it("this step's modules type no id as a number and call no parseInt — DoD-16", () => {
    for (const file of STEP_MODULES) {
      const source = readSource(file);
      expect(source, path.basename(file)).not.toMatch(/\bparseInt\b|\bparseFloat\b|\bBigInt\s*\(/);
      expect(source, path.basename(file)).not.toMatch(/\b\w*(?:id|Id|ID)\s*\??\s*:\s*number\b/);
    }
  });

  it("no file added in this step imports a stylesheet, and the modal uses no className or style element — DoD-16", () => {
    for (const file of NEW_MODULES) {
      const specs = importSpecifiers(readFileSync(file, "utf8"));
      expect(
        specs.filter((spec) => /\.(css|scss|sass|less|styl)(\?.*)?$/i.test(spec) || /styled-components|@emotion/.test(spec)),
        path.basename(file),
      ).toEqual([]);
    }
    const modal = readSource(MODAL_SOURCE);
    expect(modal).not.toMatch(/\bclassName\s*=/);
    expect(modal).not.toMatch(/<style\b/);
  });
});
