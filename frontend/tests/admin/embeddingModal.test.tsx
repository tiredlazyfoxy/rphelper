// Feature 006, step 009 — the embedding designation modal and the confirmed Clear Embedding
// action (DoD-1..DoD-16). DoD-17 and DoD-18 are [manual/live].
//
// Expected behaviour comes from the step's Interface intent and Definition of done,
// 009.context.md and context.md (D2 the measured dimension and the refusal it can produce, D4
// designation independent of is_enabled, D11 failed-probe resilience, D16 MobX rules, D17 routes,
// D18 the confirm, R5, no success toasts, never optimistic). Bindings come from the frozen
// `### Step 009` record: `EmbeddingDraft(designatedModelName)`, the pure `canSubmitEmbedding`, the
// effects `submitEmbeddingDesignation(draft, serverId, onSaved, signal?)` and
// `clearEmbeddingDesignation(state, serverId, signal?)`, and
// `<EmbeddingModal picker draft serverId serverName onClose onSaved />`, which starts the probe on
// mount and which the page mounts only while open; step 008's `ModelPicker` is reused unchanged.
// The page is rendered as in step 006/008's tests: `<LlmServersPage state={new
// LlmServersPageState()} />` under `AppProviders` + `MemoryRouter`. `fetch` is stubbed per test with
// a tiny in-memory backend (GET list, GET available-models, POST / DELETE embedding-model — the POST
// moves the designation table-wide and records a measured dimension, or answers 502
// `llm_unreachable` for a model that cannot embed, as step 005's route does). `notifyFailure` is
// mocked at file level. The page-store, draft and modal modules are wrapped pass-through so the
// page's loads, the clear calls and the picker/draft each open hands the modal are observable —
// behaviour unchanged.
//
// "The row shows the designation": the page's table has no designation column (step 006 / D1), so
// the re-loaded row is read from the page store's re-loaded list (its `embedding_model_name` /
// `embedding_dim`), and rendered evidence is the conditional Clear Embedding item moving with it.
//
// "Already-enabled" half of the union: the frozen props hand the modal only the designated name
// (the skeleton passes it as `enabled`), so every fixture a union assertion runs against has
// `enabled_model_names` equal to `[designated]` or `[]` — both readings then agree.
//
// Recognition conventions (from spec wording, for the verifier):
// - The modal and the confirm: `role="dialog"`. The single-select control: `role="radio"` inputs
//   (a Mantine `Radio.Group`) or `role="option"` items of an always-rendered single-choice list;
//   a choice belongs to a model when its label (aria-label, <label for>, aria-labelledby, or an
//   option's own text) contains the model name as a whole token. A choice is chosen when checked /
//   `aria-checked="true"` / `aria-selected="true"`. There are no checkboxes in the modal.
// - The save control: the one dialog button named /save|submit|apply|update|designate/i (not
//   cancel/close). The confirm's confirm button: /clear|remove|confirm|yes/i (not cancel); its
//   cancel: /cancel/i.
// - The probe-failure error: an `role="alert"` element inside the dialog. "Above the list": text in
//   the dialog preceding the first choice in document order. The page `Alert`: `role="alert"`
//   preceding the `<table>`.
// - Row-menu items: `role="menuitem"` inside the dropdown owned by the row's trigger (step 006's
//   idiom): /test\s*connection/i, /\bedit\b/i, /select\s+models/i, /set\s+embedding/i,
//   /clear\s+embedding/i, /\bdelete\b/i.
// - Notifications: `.mantine-Notification-root`.
//
// Model and server names are digit-free so the confirm's "no count" scan is meaningful.
import { readFileSync } from "node:fs";
import path from "node:path";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { autorun, configure, isComputedProp, isObservableProp, runInAction, toJS } from "mobx";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EmbeddingModal } from "../../src/admin/EmbeddingModal";
import {
  canSubmitEmbedding,
  clearEmbeddingDesignation,
  type DesignateEmbeddingPayload,
  EmbeddingDraft,
  submitEmbeddingDesignation,
} from "../../src/admin/embeddingDraft";
import { LlmServersPage } from "../../src/admin/LlmServersPage";
import { type LlmServerRow, LlmServersPageState, loadLlmServers } from "../../src/admin/llmServersPageState";
import { ModelPicker } from "../../src/admin/modelPicker";
import { documentNavigation } from "../../src/shared/api";
import { AppProviders } from "../../src/shared/AppProviders";

const { notifyFailureSpy, spied } = vi.hoisted(() => ({
  notifyFailureSpy: vi.fn(),
  spied: {
    load: [] as unknown[][],
    clear: [] as unknown[][],
    submit: [] as unknown[][],
    opens: [] as Array<{ picker: unknown; draft: unknown; serverId: string }>,
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
  };
});
vi.mock("../../src/admin/embeddingDraft", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../src/admin/embeddingDraft")>();
  return {
    ...actual,
    clearEmbeddingDesignation: (...args: Parameters<typeof actual.clearEmbeddingDesignation>) => {
      spied.clear.push(args);
      return actual.clearEmbeddingDesignation(...args);
    },
    submitEmbeddingDesignation: (...args: Parameters<typeof actual.submitEmbeddingDesignation>) => {
      spied.submit.push(args);
      return actual.submitEmbeddingDesignation(...args);
    },
  };
});
vi.mock("../../src/admin/EmbeddingModal", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../src/admin/EmbeddingModal")>();
  const { createElement } = await import("react");
  return {
    ...actual,
    EmbeddingModal: (props: import("../../src/admin/EmbeddingModal").EmbeddingModalProps) => {
      if (!spied.opens.some((open) => open.picker === props.picker && open.draft === props.draft)) {
        spied.opens.push({ picker: props.picker, draft: props.draft, serverId: props.serverId });
      }
      return createElement(actual.EmbeddingModal, props);
    },
  };
});

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type User = ReturnType<typeof userEvent.setup>;
type Seen = { method: string; path: string; search: string; body: unknown };

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const ADMIN_SRC = path.join(FRONTEND_ROOT, "src", "admin");
const DRAFT_SOURCE = path.join(ADMIN_SRC, "embeddingDraft.ts");
const MODAL_SOURCE = path.join(ADMIN_SRC, "EmbeddingModal.tsx");
const PAGE_SOURCE = path.join(ADMIN_SRC, "LlmServersPage.tsx");
const NEW_MODULES = [DRAFT_SOURCE, MODAL_SOURCE];
const STEP_MODULES = [...NEW_MODULES, PAGE_SOURCE];

const LIST_PATH = "/api/admin/llm-servers";
const PROBE_PATH = /^\/api\/admin\/llm-servers\/([^/]+)\/available-models$/;
const DESIGNATE_PATH = /^\/api\/admin\/llm-servers\/([^/]+)\/embedding-model$/;
const MODELS_PATH = /^\/api\/admin\/llm-servers\/([^/]+)\/models$/;
const BIG_ID = "9007199254740993"; // 2^53 + 1 — not representable as a JS number
const PROBE_FAILURE = "The server at attic did not answer zq-probe.";
const REFUSAL = "The model qwen-chat returned no usable embedding zq-refused.";
const CLEAR_FAILURE = "The registry could not clear the designation zq-clear.";
const SAVE_FAILURE = "The registry exploded zq-save.";

const SAVE_NAME = /save|submit|apply|update|designate/i;
const NOT_SAVE_NAME = /cancel|close/i;
const CONFIRM_CLEAR = /clear|remove|confirm|yes/i;
const CANCEL_NAME = /cancel/i;
const TEST_ITEM = /test\s*connection/i;
const EDIT_ITEM = /\bedit\b/i;
const SELECT_MODELS_ITEM = /select\s+models/i;
const SET_EMBEDDING_ITEM = /set\s+embedding/i;
const CLEAR_EMBEDDING_ITEM = /clear\s+embedding/i;
const DELETE_ITEM = /\bdelete\b/i;
const NOTIFICATION_ROOT = ".mantine-Notification-root";
/** R5 — nothing derived from another user's data. */
const OTHER_USERS_DATA = /\b(sessions?|users?|characters?|setups?|memos?|entry|entries)\b/i;
const NUMBER_WORDS = /\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|dozens?|several|many)\b/i;
/** UC-013 — changing the designation neither forces nor prompts a rebuild. */
const REBUILD_TALK =
  /\brebuild|\bre-build|\bre-?index|\bre-?embed|existing (vectors|embeddings)|not comparable|incompatible|different model|dimension (change|mismatch)/i;

/** Measured dimension per model the fake backend can embed with; `qwen-chat` cannot embed. */
const DIMS: Record<string, number> = { "nomic-embed": 768, "gte-base": 1024, "bge-small": 384, "old-embed": 512 };
const CANNOT_EMBED = new Set(["qwen-chat"]);

/** Holds the designation; enabled set == [designated]. */
const ATTIC: LlmServerRow = {
  id: "7340032000000201",
  name: "Attic box",
  kind: "llamaswap",
  base_url: "http://attic.lan:8080",
  has_api_key: false,
  enabled_model_names: ["nomic-embed"],
  embedding_model_name: "nomic-embed",
  embedding_dim: 768,
  last_test_at: null,
  last_test_ok: null,
  last_test_error: null,
  created_at: "2026-09-01T08:00:00.000000+00:00",
  updated_at: "2026-09-01T08:00:00.000000+00:00",
};
const ATTIC_OFFERED = ["bge-small", "nomic-embed", "qwen-chat"];

/** No designation, nothing enabled. */
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
const ORCHARD_OFFERED = ["gte-base", "qwen-chat"];

/** Designated model the server no longer offers (used alone — one designation per table). */
const CELLAR: LlmServerRow = {
  ...ORCHARD,
  id: "7340032000000203",
  name: "Cellar rig",
  kind: "llamaswap",
  base_url: "http://cellar.lan/llama",
  has_api_key: false,
  enabled_model_names: ["old-embed"],
  embedding_model_name: "old-embed",
  embedding_dim: 512,
};
const CELLAR_OFFERED = ["qwen-chat"];

const EVERYONE: LlmServerRow[] = [ATTIC, ORCHARD];
const DEFAULT_OFFERED: Record<string, readonly string[]> = {
  [ATTIC.id]: ATTIC_OFFERED,
  [ORCHARD.id]: ORCHARD_OFFERED,
  [CELLAR.id]: CELLAR_OFFERED,
};

beforeEach(() => {
  notifyFailureSpy.mockClear();
  spied.load.length = 0;
  spied.clear.length = 0;
  spied.submit.length = 0;
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

function laterListLoads(calls: Seen[], afterMethod: string): Seen[] {
  const index = calls.findIndex((call) => call.method === afterMethod);
  expect(index, `a ${afterMethod} request`).toBeGreaterThanOrEqual(0);
  return calls.slice(index + 1).filter((call) => call.method === "GET" && call.path === LIST_PATH);
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
 * A tiny in-memory backend: GET lists; GET `{id}/available-models` answers the offered names;
 * POST `{id}/embedding-model` designates — 502 `llm_unreachable` for a model that cannot embed
 * (nothing written), otherwise the designation is cleared on every row and set on this one with the
 * measured dimension, `is_enabled` untouched (200, the row); DELETE `{id}/embedding-model` clears
 * that server's designation (204). POST `{id}/models` exists only so an accidental enable is
 * observable as a mutation.
 */
function serveServers(initial: readonly LlmServerRow[], options: ServeOptions = {}) {
  const rows = copyRows(initial);
  const offered = options.offered ?? DEFAULT_OFFERED;
  const notFound = () => Promise.resolve(envelopeResponse("llm_server_not_found", "That connection does not exist.", 404));
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
      if (!rows.some((row) => row.id === id)) return notFound();
      return Promise.resolve(jsonResponse({ model_names: [...(offered[id] ?? [])] }, 200));
    }
    const designateMatch = DESIGNATE_PATH.exec(pathname);
    if (designateMatch !== null && (method === "POST" || method === "DELETE")) {
      const row = rows.find((candidate) => candidate.id === designateMatch[1]);
      if (row === undefined) return notFound();
      if (method === "DELETE") {
        row.embedding_model_name = null;
        row.embedding_dim = null;
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      const name = ((body ?? {}) as DesignateEmbeddingPayload).model_name;
      if (typeof name !== "string" || name.length === 0 || CANNOT_EMBED.has(name)) {
        return Promise.resolve(envelopeResponse("llm_unreachable", REFUSAL, 502));
      }
      for (const other of rows) {
        other.embedding_model_name = null;
        other.embedding_dim = null;
      }
      row.embedding_model_name = name;
      row.embedding_dim = DIMS[name] ?? 256;
      return Promise.resolve(jsonResponse({ ...row, enabled_model_names: [...row.enabled_model_names] }, 200));
    }
    const modelsMatch = MODELS_PATH.exec(pathname);
    if (method === "POST" && modelsMatch !== null) {
      const row = rows.find((candidate) => candidate.id === modelsMatch[1]);
      if (row === undefined) return notFound();
      return Promise.resolve(jsonResponse({ enabled_model_names: [...row.enabled_model_names] }, 200));
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

function draftSnapshot(draft: EmbeddingDraft) {
  return {
    selected: draft.selected,
    designated: draft.designated,
    serverErrors: toJS(draft.serverErrors),
    submitStatus: draft.submitStatus,
  };
}

function pageStoreSnapshot(state: LlmServersPageState) {
  return {
    rows: toJS(state.rows),
    status: state.status,
    errorMessage: state.errorMessage,
    testingId: state.testingId,
  };
}

function presentKeys(errors: Partial<Record<string, string>>): string[] {
  return Object.entries(errors)
    .filter(([, value]) => typeof value === "string" && value.length > 0)
    .map(([key]) => key)
    .sort();
}

function draftWith(designated: string | null, fields: Partial<Pick<EmbeddingDraft, "selected" | "submitStatus">> = {}) {
  const draft = new EmbeddingDraft(designated);
  runInAction(() => {
    Object.assign(draft, fields);
  });
  return draft;
}

function stateWith(rows: readonly LlmServerRow[]): LlmServersPageState {
  const state = new LlmServersPageState();
  runInAction(() => {
    state.rows = copyRows(rows);
    state.status = "ready";
  });
  return state;
}

function storeRow(state: LlmServersPageState, id: string): LlmServerRow {
  const row = state.rows.find((candidate) => candidate.id === id);
  expect(row, `store row ${id}`).toBeDefined();
  return row as LlmServerRow;
}

function designatedRows(state: LlmServersPageState): Array<{ id: string; model: string | null; dim: number | null }> {
  return state.rows
    .filter((row) => row.embedding_model_name !== null)
    .map((row) => ({ id: row.id, model: row.embedding_model_name, dim: row.embedding_dim }));
}

// ---------------------------------------------------------------- render

function renderModal(row: LlmServerRow, picker: ModelPicker = new ModelPicker(), draft?: EmbeddingDraft) {
  const usedDraft = draft ?? new EmbeddingDraft(row.embedding_model_name);
  const onClose = vi.fn<() => void>();
  const onSaved = vi.fn<() => void>();
  const view = render(
    <AppProviders>
      <EmbeddingModal
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

function labelOf(el: HTMLElement): string {
  const parts = [el.getAttribute("aria-label") ?? ""];
  const labels = (el as HTMLInputElement).labels;
  if (labels) for (const label of Array.from(labels)) parts.push(label.textContent ?? "");
  for (const id of (el.getAttribute("aria-labelledby") ?? "").split(/\s+/).filter(Boolean)) {
    parts.push(document.getElementById(id)?.textContent ?? "");
  }
  if (!(el instanceof HTMLInputElement)) parts.push(el.textContent ?? "");
  return parts.join(" ");
}

/** The single-select control's choices: radios, or the options of a single-choice list. */
function choices(): HTMLElement[] {
  const scope = within(dialog());
  return [...scope.queryAllByRole("radio"), ...scope.queryAllByRole("option")];
}

function isChosen(el: HTMLElement): boolean {
  if (el instanceof HTMLInputElement) return el.checked;
  return el.getAttribute("aria-checked") === "true" || el.getAttribute("aria-selected") === "true";
}

function labelledWith(el: HTMLElement, name: string): boolean {
  return new RegExp(`(^|[^\\w-])${escapeRegExp(name)}([^\\w-]|$)`).test(labelOf(el));
}

function choiceFor(name: string): HTMLElement {
  const found = choices().filter((el) => labelledWith(el, name));
  expect(found, `choices labelled ${name}`).toHaveLength(1);
  return found[0];
}

function choiceNames(candidates: readonly string[]): string[] {
  return candidates.filter((name) => choices().some((el) => labelledWith(el, name))).sort();
}

function chosenNames(candidates: readonly string[]): string[] {
  return candidates.filter((name) => choices().some((el) => labelledWith(el, name) && isChosen(el))).sort();
}

function isDisabledChoice(el: HTMLElement): boolean {
  return (
    (el as HTMLInputElement).disabled === true ||
    el.getAttribute("aria-disabled") === "true" ||
    el.hasAttribute("data-disabled")
  );
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

async function choose(user: User, name: string): Promise<void> {
  await user.click(choiceFor(name));
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
    const inside = choices()[0] ?? dialog();
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

async function menuItemNames(user: User, name: string): Promise<string[]> {
  const menu = await openRowMenu(user, name);
  await within(menu).findAllByRole("menuitem");
  const names = within(menu)
    .getAllByRole("menuitem")
    .map((item) => (item.textContent ?? "").trim());
  await user.keyboard("{Escape}");
  await flush(2);
  return names;
}

/** Row menu -> Set Embedding -> the dialog; then lets the probe settle. */
async function openSetEmbedding(user: User, name: string, settleProbe = true): Promise<void> {
  const menu = await openRowMenu(user, name);
  const item = await within(menu).findByRole("menuitem", { name: SET_EMBEDDING_ITEM });
  await user.click(item);
  await screen.findByRole("dialog");
  if (settleProbe) await flush();
}

/** Row menu -> Clear Embedding -> the shared confirm. */
async function openClearConfirm(user: User, name: string): Promise<HTMLElement> {
  const menu = await openRowMenu(user, name);
  const item = await within(menu).findByRole("menuitem", { name: CLEAR_EMBEDDING_ITEM });
  await user.click(item);
  return screen.findByRole("dialog");
}

function confirmButton(confirm: HTMLElement): HTMLElement {
  const found = within(confirm)
    .queryAllByRole("button")
    .filter((el) => {
      const name = el.getAttribute("aria-label") ?? el.textContent ?? "";
      return CONFIRM_CLEAR.test(name) && !CANCEL_NAME.test(name);
    });
  expect(found, "confirm buttons in the confirm dialog").toHaveLength(1);
  return found[0];
}

function isBefore(first: Node, second: Node): boolean {
  return (first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

function opens(): Array<{ picker: ModelPicker; draft: EmbeddingDraft; serverId: string }> {
  return spied.opens as Array<{ picker: ModelPicker; draft: EmbeddingDraft; serverId: string }>;
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
describe("opening probes once and renders a single-select control over the union", () => {
  it("Set Embedding in a row's menu opens the modal and probes that server exactly once — DoD-1 (UC-013)", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    expect(screen.queryByRole("dialog")).toBeNull();

    await openSetEmbedding(user, ORCHARD.name);
    await flush();

    expect(probeCalls(mock, ORCHARD.id)).toHaveLength(1);
    expect(probeCalls(mock, ATTIC.id)).toHaveLength(0);
    expect(probeCalls(mock, ORCHARD.id)[0].search).toBe("");
    expect(mutations(mock)).toEqual([]);
  });

  it("renders one choice per model in the union and no checkbox — DoD-1", async () => {
    const user = newUser();
    await renderLoaded();
    await openSetEmbedding(user, ATTIC.name);

    expect(within(dialog()).queryAllByRole("checkbox")).toEqual([]);
    expect(choices()).toHaveLength(ATTIC_OFFERED.length);
    expect(choiceNames(ATTIC_OFFERED)).toEqual([...ATTIC_OFFERED].sort());
  });

  it("choosing one option deselects any other; at most one is ever chosen — DoD-1", async () => {
    const user = newUser();
    await renderLoaded();
    await openSetEmbedding(user, ATTIC.name);

    await choose(user, "qwen-chat");
    expect(chosenNames(ATTIC_OFFERED)).toEqual(["qwen-chat"]);
    await choose(user, "bge-small");
    expect(chosenNames(ATTIC_OFFERED)).toEqual(["bge-small"]);
    expect(choices().filter(isChosen)).toHaveLength(1);

    const [open] = opens();
    expect(open.draft.selected).toBe("bge-small");
  });

  it("the choices are one group: radios share one name, a list is not multi-selectable — DoD-1", async () => {
    serveServers(EVERYONE);
    renderModal(ATTIC);
    await flush();
    const radios = within(dialog()).queryAllByRole("radio") as HTMLInputElement[];
    const inputRadios = radios.filter((el) => el instanceof HTMLInputElement);
    if (inputRadios.length > 0) {
      const names = new Set(inputRadios.map((el) => el.name));
      expect(names.size).toBe(1);
      expect([...names][0].length).toBeGreaterThan(0);
    }
    for (const list of within(dialog()).queryAllByRole("listbox")) {
      expect(list.getAttribute("aria-multiselectable")).not.toBe("true");
    }
    expect(choices().length).toBeGreaterThan(0);
  });

  it("a designated model the server no longer offers still renders as a choice — DoD-1 (union)", async () => {
    serveServers([CELLAR]);
    renderModal(CELLAR);
    await flush();
    expect(choiceNames(["old-embed", "qwen-chat"])).toEqual(["old-embed", "qwen-chat"]);
    expect(choices()).toHaveLength(2);
    expect(chosenNames(["old-embed", "qwen-chat"])).toEqual(["old-embed"]);
  });

  it("the standalone modal starts the probe on mount, once, at that server's available-models route — DoD-1", async () => {
    const { mock } = serveServers(EVERYONE);
    renderModal(ORCHARD);
    await flush();
    expect(seen(mock).map((call) => `${call.method} ${call.path}`)).toEqual([
      `GET ${LIST_PATH}/${ORCHARD.id}/available-models`,
    ]);
    expect(choices()).toHaveLength(ORCHARD_OFFERED.length);
  });
});

// ===========================================================================
describe("the current designation is preselected from the list payload", () => {
  it("the row's designated model is chosen on open, nothing else is — DoD-2 (UC-013)", async () => {
    const user = newUser();
    await renderLoaded();
    await openSetEmbedding(user, ATTIC.name);
    expect(chosenNames(ATTIC_OFFERED)).toEqual(["nomic-embed"]);
  });

  it("a server with no designation opens with nothing chosen — DoD-2", async () => {
    const user = newUser();
    await renderLoaded();
    await openSetEmbedding(user, ORCHARD.name);
    expect(chosenNames(ORCHARD_OFFERED)).toEqual([]);
  });

  it("the draft the page hands the modal is seeded from the row before the probe answers — DoD-2", async () => {
    const user = newUser();
    const pending = deferred<Response>();
    await renderLoaded(EVERYONE, { probe: () => pending.promise });
    await openSetEmbedding(user, ATTIC.name, false);
    await flush(2);

    const [open] = opens();
    expect(open, "the modal was opened").toBeDefined();
    expect(open.serverId).toBe(ATTIC.id);
    expect(open.draft).toBeInstanceOf(EmbeddingDraft);
    expect(open.draft.selected).toBe("nomic-embed");
    expect(open.draft.designated).toBe("nomic-embed");
    expect(open.picker.status).toBe("loading");

    pending.resolve(jsonResponse({ model_names: ["qwen-chat"] }, 200));
    await flush();
    expect(open.draft.selected).toBe("nomic-embed");
    expect(open.draft.designated).toBe("nomic-embed");
  });

  it("the draft's constructor takes the designated name as both selection and designation — DoD-2", () => {
    const seeded = new EmbeddingDraft("nomic-embed");
    expect(seeded.selected).toBe("nomic-embed");
    expect(seeded.designated).toBe("nomic-embed");
    const empty = new EmbeddingDraft(null);
    expect(empty.selected).toBeNull();
    expect(empty.designated).toBeNull();
  });
});

// ===========================================================================
describe("designating saves the chosen name and the re-loaded row carries it", () => {
  it("choosing and saving POSTs that name; the re-loaded row shows it with its measured dimension — DoD-3 (US-015.AC-1)", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    await openSetEmbedding(user, ORCHARD.name);
    await choose(user, "gte-base");
    await save(user);
    await waitForNoDialog();

    const posts = mutations(mock);
    expect(posts).toHaveLength(1);
    expect(posts[0].method).toBe("POST");
    expect(posts[0].path).toBe(`${LIST_PATH}/${ORCHARD.id}/embedding-model`);
    expect(posts[0].search).toBe("");
    expect(posts[0].body).toEqual({ model_name: "gte-base" });
    expect(laterListLoads(seen(mock), "POST").length).toBeGreaterThan(0);
    expect(storeRow(state, ORCHARD.id).embedding_model_name).toBe("gte-base");
    expect(storeRow(state, ORCHARD.id).embedding_dim).toBe(1024);
  });

  it("the submit function POSTs { model_name } to the designation route and calls onSaved once — DoD-3", async () => {
    const { mock } = serveServers(EVERYONE);
    const draft = draftWith(null, { selected: "gte-base" });
    const onSaved = vi.fn<() => void>();
    await expect(submitEmbeddingDesignation(draft, ORCHARD.id, onSaved)).resolves.toBeUndefined();
    expect(mutations(mock)).toEqual([
      { method: "POST", path: `${LIST_PATH}/${ORCHARD.id}/embedding-model`, search: "", body: { model_name: "gte-base" } },
    ]);
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(draft.submitStatus).toBe("done");
  });
});

// ===========================================================================
describe("designating on a second server moves the designation", () => {
  it("the re-loaded list shows exactly one designation, on the newly designating server — DoD-4 (UC-013)", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    expect(designatedRows(state)).toEqual([{ id: ATTIC.id, model: "nomic-embed", dim: 768 }]);

    await openSetEmbedding(user, ORCHARD.name);
    await choose(user, "gte-base");
    await save(user);
    await waitForNoDialog();

    expect(designatedRows(state)).toEqual([{ id: ORCHARD.id, model: "gte-base", dim: 1024 }]);
    expect(storeRow(state, ATTIC.id).embedding_model_name).toBeNull();
    expect(mutations(mock).map((call) => `${call.method} ${call.path}`)).toEqual([
      `POST ${LIST_PATH}/${ORCHARD.id}/embedding-model`,
    ]);
  });
});

// ===========================================================================
describe("a refusal lands on the general key and the previous designation stands", () => {
  it("the 502 a model that cannot embed produces renders on the general key above the list — DoD-5 (D2)", async () => {
    const user = newUser();
    const { state } = await renderLoaded();
    await openSetEmbedding(user, ATTIC.name);
    await choose(user, "qwen-chat");
    await save(user);

    const [open] = opens();
    expect(presentKeys(open.draft.serverErrors)).toEqual(["general"]);
    const general = (open.draft.serverErrors.general as string).replace(/\s+/g, " ").trim();
    expect(general.length).toBeGreaterThan(0);
    expect(general).toContain(REFUSAL);
    const first = choices()[0];
    expect(first, "the list still renders").toBeDefined();
    expect(textAbove(first)).toContain(general);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(open.draft.designated).toBe("nomic-embed");
    expect(storeRow(state, ATTIC.id).embedding_model_name).toBe("nomic-embed");
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("after closing the modal and re-loading, the previous designation is still shown — DoD-5", async () => {
    const user = newUser();
    const { state } = await renderLoaded();
    await openSetEmbedding(user, ATTIC.name);
    await choose(user, "qwen-chat");
    await save(user);
    await closeModal(user);

    await act(async () => {
      await loadLlmServers(state);
    });
    await flush();
    expect(designatedRows(state)).toEqual([{ id: ATTIC.id, model: "nomic-embed", dim: 768 }]);

    const names = await menuItemNames(user, ATTIC.name);
    expect(names.filter((name) => CLEAR_EMBEDDING_ITEM.test(name))).toHaveLength(1);

    await openSetEmbedding(user, ATTIC.name);
    expect(chosenNames(ATTIC_OFFERED)).toEqual(["nomic-embed"]);
  });

  const FAILURES: Array<[string, () => Promise<Response>]> = [
    ["a 502 llm_unreachable", () => Promise.resolve(envelopeResponse("llm_unreachable", REFUSAL, 502))],
    [
      "a 502 llm_unreachable whose prose reads like success and names a field",
      () => Promise.resolve(envelopeResponse("llm_unreachable", "model_name ok — designated fine zq.", 502)),
    ],
    [
      "a 502 with a malformed body",
      () => Promise.resolve(new Response("<html>Bad Gateway</html>", { status: 502, headers: { "Content-Type": "text/html" } })),
    ],
    ["a 500 envelope", () => Promise.resolve(envelopeResponse("internal_error", SAVE_FAILURE, 500))],
    ["a 404 llm_server_not_found", () => Promise.resolve(envelopeResponse("llm_server_not_found", "That connection does not exist zq.", 404))],
    [
      "FastAPI's own 422 naming the field",
      () =>
        Promise.resolve(
          jsonResponse({ detail: [{ type: "string_too_short", loc: ["body", "model_name"], msg: "String should have at least 1 character", input: "" }] }, 422),
        ),
    ],
    ["a transport failure", () => Promise.reject(new TypeError("Failed to fetch"))],
  ];

  it.each(FAILURES)("%s: only the general key, rendered above the list, modal open, nothing saved — DoD-5", async (_name, failure) => {
    vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    const user = newUser();
    serveServers(EVERYONE, { override: (method, pathname) => (method === "POST" && DESIGNATE_PATH.test(pathname) ? failure() : undefined) });
    const { draft, onSaved, onClose } = renderModal(ATTIC);
    await flush();
    await choose(user, "bge-small");
    await save(user);

    expect(presentKeys(draft.serverErrors)).toEqual(["general"]);
    const general = (draft.serverErrors.general as string).replace(/\s+/g, " ").trim();
    expect(general.length).toBeGreaterThan(0);
    expect(textAbove(choices()[0])).toContain(general);
    expect(chosenNames(ATTIC_OFFERED)).toEqual(["bge-small"]);
    expect(draft.selected).toBe("bge-small");
    expect(draft.designated).toBe("nomic-embed");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(draft.submitStatus).not.toBe("done");
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it.each(FAILURES)("%s: the submit function never rejects and writes only the general key — DoD-5", async (_name, failure) => {
    vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(() => failure());
    const draft = draftWith("nomic-embed", { selected: "qwen-chat" });
    const onSaved = vi.fn<() => void>();
    await expect(submitEmbeddingDesignation(draft, ATTIC.id, onSaved)).resolves.toBeUndefined();
    expect(presentKeys(draft.serverErrors)).toEqual(["general"]);
    expect(draft.selected).toBe("qwen-chat");
    expect(draft.designated).toBe("nomic-embed");
    expect(onSaved).not.toHaveBeenCalled();
    expect(draft.submitStatus).not.toBe("done");
  });
});

// ===========================================================================
describe("failed-probe resilience (D11)", () => {
  const PROBE_FAILURES: Array<[string, () => Promise<Response>]> = [
    ["a 502 llm_unreachable", () => Promise.resolve(envelopeResponse("llm_unreachable", PROBE_FAILURE, 502))],
    ["a transport failure", () => Promise.reject(new TypeError("Failed to fetch"))],
  ];

  it.each(PROBE_FAILURES)(
    "%s: the modal shows an error and still lists the designated model, preselected — DoD-6",
    async (_name, failure) => {
      const user = newUser();
      await renderLoaded(EVERYONE, { probe: () => failure() });
      await openSetEmbedding(user, ATTIC.name);

      const [open] = opens();
      expect(open.picker.status).toBe("failed");
      const message = (open.picker.errorMessage ?? "").trim();
      expect(message.length).toBeGreaterThan(0);
      const alerts = alertsInDialog();
      expect(alerts.length).toBeGreaterThan(0);
      expect(alerts.map((el) => el.textContent ?? "").join(" ")).toContain(message);

      expect(choices().length).toBeGreaterThan(0);
      expect(choiceNames(ATTIC.enabled_model_names)).toEqual([...ATTIC.enabled_model_names].sort());
      expect(chosenNames(ATTIC_OFFERED)).toEqual(["nomic-embed"]);
      expect(open.draft.selected).toBe("nomic-embed");
      expect(open.draft.designated).toBe("nomic-embed");
    },
  );

  it("the standalone modal after a failed probe keeps its preselection — DoD-6", async () => {
    serveServers(EVERYONE, { probe: () => Promise.resolve(envelopeResponse("llm_unreachable", PROBE_FAILURE, 502)) });
    const { picker, draft } = renderModal(ATTIC);
    await flush();
    expect(picker.status).toBe("failed");
    expect(dialog().textContent ?? "").toContain(PROBE_FAILURE);
    expect(chosenNames(["nomic-embed"])).toEqual(["nomic-embed"]);
    expect(draft.selected).toBe("nomic-embed");
  });
});

// ===========================================================================
describe("Clear Embedding is conditional", () => {
  it("offered on the row holding the designation and absent from every other row — DoD-7", async () => {
    const user = newUser();
    await renderLoaded();
    const attic = await menuItemNames(user, ATTIC.name);
    const orchard = await menuItemNames(user, ORCHARD.name);
    expect(attic.filter((name) => CLEAR_EMBEDDING_ITEM.test(name))).toHaveLength(1);
    expect(orchard.filter((name) => CLEAR_EMBEDDING_ITEM.test(name))).toEqual([]);
  });

  it("with no designation anywhere, no row offers it — DoD-7", async () => {
    const user = newUser();
    await renderLoaded([{ ...ATTIC, embedding_model_name: null, embedding_dim: null }, ORCHARD]);
    for (const server of EVERYONE) {
      const names = await menuItemNames(user, server.name);
      expect(names.filter((name) => CLEAR_EMBEDDING_ITEM.test(name)), server.name).toEqual([]);
    }
  });

  it("it follows the designation when it moves — DoD-7, DoD-4", async () => {
    const user = newUser();
    await renderLoaded();
    await openSetEmbedding(user, ORCHARD.name);
    await choose(user, "gte-base");
    await save(user);
    await waitForNoDialog();
    await flush();
    const attic = await menuItemNames(user, ATTIC.name);
    const orchard = await menuItemNames(user, ORCHARD.name);
    expect(attic.filter((name) => CLEAR_EMBEDDING_ITEM.test(name))).toEqual([]);
    expect(orchard.filter((name) => CLEAR_EMBEDDING_ITEM.test(name))).toHaveLength(1);
  });
});

// ===========================================================================
describe("Clear Embedding is confirmed", () => {
  it("choosing it opens the shared confirm and issues no request — DoD-8 (D18)", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    const before = mock.mock.calls.length;
    const confirm = await openClearConfirm(user, ATTIC.name);
    confirmButton(confirm);
    expect(within(confirm).getByRole("button", { name: CANCEL_NAME })).toBeInTheDocument();
    await flush();
    expect(mock.mock.calls.length).toBe(before);
    expect(spied.clear).toEqual([]);
  });

  it("cancelling issues no request and leaves the designation — DoD-8", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    const before = seen(mock);
    const confirm = await openClearConfirm(user, ATTIC.name);
    await user.click(within(confirm).getByRole("button", { name: CANCEL_NAME }));
    await waitForNoDialog();
    await flush();
    expect(seen(mock)).toEqual(before);
    expect(spied.clear).toEqual([]);
    expect(designatedRows(state)).toEqual([{ id: ATTIC.id, model: "nomic-embed", dim: 768 }]);
  });

  it("confirming issues the DELETE, then re-loads, after which no row shows a designation — DoD-8", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    const confirm = await openClearConfirm(user, ATTIC.name);
    await user.click(confirmButton(confirm));
    await flush();

    const calls = seen(mock);
    expect(calls.filter((call) => call.method !== "GET")).toEqual([
      { method: "DELETE", path: `${LIST_PATH}/${ATTIC.id}/embedding-model`, search: "", body: undefined },
    ]);
    expect(laterListLoads(calls, "DELETE").length).toBeGreaterThan(0);
    expect(spied.clear).toHaveLength(1);
    expect(spied.clear[0][0]).toBe(state);
    expect(spied.clear[0][1]).toBe(ATTIC.id);
    expect(designatedRows(state)).toEqual([]);
    await waitForNoDialog();
    const names = await menuItemNames(user, ATTIC.name);
    expect(names.filter((name) => CLEAR_EMBEDDING_ITEM.test(name))).toEqual([]);
  });

  it("the clear function DELETEs then re-loads; the rows come from the re-load — DoD-8", async () => {
    const { mock, rows } = serveServers(EVERYONE);
    const state = stateWith(EVERYONE);
    const newcomer: LlmServerRow = { ...ORCHARD, id: "7340032000000299", name: "Newcomer rig" };
    rows.push({ ...newcomer });
    await expect(clearEmbeddingDesignation(state, ATTIC.id)).resolves.toBeUndefined();
    const calls = seen(mock);
    expect(calls[0]).toEqual({ method: "DELETE", path: `${LIST_PATH}/${ATTIC.id}/embedding-model`, search: "", body: undefined });
    expect(calls.slice(1).map((call) => `${call.method} ${call.path}`)).toEqual([`GET ${LIST_PATH}`]);
    expect(state.rows.map((row) => row.id)).toEqual([ATTIC.id, ORCHARD.id, newcomer.id]);
    expect(designatedRows(state)).toEqual([]);
  });

  it("the page routes the confirm through the shared ConfirmModal — DoD-8", () => {
    const specs = importSpecifiers(readFileSync(PAGE_SOURCE, "utf8"));
    expect(specs.some((spec) => /(^|\/)shared\/ConfirmModal$/.test(spec))).toBe(true);
    expect(readSource(PAGE_SOURCE)).toMatch(/<ConfirmModal\b/);
  });
});

// ===========================================================================
describe("R5 — the confirm names no count and nothing about other users' data", () => {
  it("no digit (beyond the model's own dimension), no number word, nothing about sessions or users — DoD-9 (R5, UC-012)", async () => {
    const user = newUser();
    await renderLoaded();
    const confirm = await openClearConfirm(user, ATTIC.name);
    const text = (confirm.textContent ?? "").split(String(ATTIC.embedding_dim)).join(" ");
    expect(text).not.toMatch(/\d/);
    expect(text).not.toMatch(NUMBER_WORDS);
    expect(text).not.toMatch(OTHER_USERS_DATA);
    expect(text).not.toMatch(/are you sure/i);
  });

  it("it describes the action and its consequence for the instance — DoD-9 (UC-065, UC-066)", async () => {
    const user = newUser();
    await renderLoaded();
    const confirm = await openClearConfirm(user, ATTIC.name);
    const text = confirm.textContent ?? "";
    expect(text).toMatch(/embedding/i);
    expect(text).toMatch(/semantic|search|retriev|memory/i);
  });

  it("injected count fields on the payload never reach the confirm — DoD-9", async () => {
    const user = newUser();
    await renderLoaded(
      EVERYONE.map((row) => ({ ...row, session_count: 4817, user_count: 9253, sessions_using: 7719 }) as LlmServerRow),
    );
    const confirm = await openClearConfirm(user, ATTIC.name);
    const text = confirm.textContent ?? "";
    for (const count of ["4817", "9253", "7719"]) expect(text).not.toContain(count);
  });
});

// ===========================================================================
describe("no rebuild prompt when the designation changes (UC-013)", () => {
  it("neither the modal nor the page warns about or offers a rebuild, before or after a change — DoD-10", async () => {
    const user = newUser();
    await renderLoaded();
    await openSetEmbedding(user, ORCHARD.name);
    expect(dialog().textContent ?? "").not.toMatch(REBUILD_TALK);
    await choose(user, "gte-base");
    expect(dialog().textContent ?? "").not.toMatch(REBUILD_TALK);
    await save(user);
    await waitForNoDialog();
    await flush();

    expect(screen.queryAllByRole("dialog")).toEqual([]);
    expect(notificationRoots()).toEqual([]);
    expect(document.body.textContent ?? "").not.toMatch(REBUILD_TALK);
    expect(screen.queryAllByRole("button").filter((el) => REBUILD_TALK.test(el.textContent ?? ""))).toEqual([]);
  });

  it("the Clear Embedding confirm says nothing about a rebuild — DoD-10", async () => {
    const user = newUser();
    await renderLoaded();
    const confirm = await openClearConfirm(user, ATTIC.name);
    expect(confirm.textContent ?? "").not.toMatch(REBUILD_TALK);
  });

  it("no module of this step carries rebuild wording — DoD-10", () => {
    for (const file of STEP_MODULES) {
      expect(readSource(file), path.basename(file)).not.toMatch(REBUILD_TALK);
    }
  });
});

// ===========================================================================
describe("designation is independent of is_enabled (D4)", () => {
  it("a model that is not enabled can be chosen and saved, with no enable request — DoD-11", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    await openSetEmbedding(user, ATTIC.name);
    const bge = choiceFor("bge-small");
    expect(isDisabledChoice(bge)).toBe(false);
    await choose(user, "bge-small");
    expect(saveControl()).not.toBeDisabled();
    await save(user);
    await waitForNoDialog();

    expect(mutations(mock)).toEqual([
      { method: "POST", path: `${LIST_PATH}/${ATTIC.id}/embedding-model`, search: "", body: { model_name: "bge-small" } },
    ]);
    expect(seen(mock).some((call) => MODELS_PATH.test(call.path))).toBe(false);
    expect(storeRow(state, ATTIC.id).embedding_model_name).toBe("bge-small");
    expect(storeRow(state, ATTIC.id).enabled_model_names).toEqual(ATTIC.enabled_model_names);
  });

  it("on a server with nothing enabled, designation still goes through and enables nothing — DoD-11", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    await openSetEmbedding(user, ORCHARD.name);
    for (const el of choices()) expect(isDisabledChoice(el), labelOf(el)).toBe(false);
    await choose(user, "gte-base");
    await save(user);
    await waitForNoDialog();
    expect(mutations(mock).map((call) => `${call.method} ${call.path}`)).toEqual([
      `POST ${LIST_PATH}/${ORCHARD.id}/embedding-model`,
    ]);
    expect(storeRow(state, ORCHARD.id).enabled_model_names).toEqual([]);
  });

  it("can-submit needs only a selection and no submission in flight — DoD-11, DoD-14", () => {
    expect(canSubmitEmbedding(new EmbeddingDraft(null))).toBe(false);
    expect(canSubmitEmbedding(draftWith(null, { selected: "gte-base" }))).toBe(true);
    expect(canSubmitEmbedding(new EmbeddingDraft("nomic-embed"))).toBe(true);
    expect(canSubmitEmbedding(draftWith("nomic-embed", { submitStatus: "submitting" }))).toBe(false);
  });
});

// ===========================================================================
describe("a clear failure renders in the page Alert", () => {
  it("the failure's message is in an Alert above the table, no notification, designation kept — DoD-12", async () => {
    const user = newUser();
    const { state } = await renderLoaded(EVERYONE, {
      override: (method, pathname) =>
        method === "DELETE" && DESIGNATE_PATH.test(pathname)
          ? Promise.resolve(envelopeResponse("internal_error", CLEAR_FAILURE, 500))
          : undefined,
    });
    const confirm = await openClearConfirm(user, ATTIC.name);
    await user.click(confirmButton(confirm));
    await flush();

    const matching = screen.queryAllByRole("alert").filter((el) => (el.textContent ?? "").includes(CLEAR_FAILURE));
    expect(matching.length).toBeGreaterThan(0);
    expect(isBefore(matching[0], table())).toBe(true);
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(designatedRows(state)).toEqual([{ id: ATTIC.id, model: "nomic-embed", dim: 768 }]);
  });

  it.each<[string, () => Promise<Response>]>([
    ["a 500 envelope", () => Promise.resolve(envelopeResponse("internal_error", CLEAR_FAILURE, 500))],
    ["a 404 llm_server_not_found", () => Promise.resolve(envelopeResponse("llm_server_not_found", CLEAR_FAILURE, 404))],
    ["a transport failure", () => Promise.reject(new TypeError("Failed to fetch"))],
  ])("%s: the clear function writes the page error field and never rejects — DoD-12", async (_name, failure) => {
    vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(() => failure());
    const state = stateWith(EVERYONE);
    await expect(clearEmbeddingDesignation(state, ATTIC.id)).resolves.toBeUndefined();
    expect(typeof state.errorMessage).toBe("string");
    expect((state.errorMessage ?? "").length).toBeGreaterThan(0);
    expect(toJS(state.rows)).toEqual(EVERYONE);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("the clear failure's message is the server's message — DoD-12", async () => {
    stubFetch(() => Promise.resolve(envelopeResponse("internal_error", CLEAR_FAILURE, 500)));
    const state = stateWith(EVERYONE);
    await clearEmbeddingDesignation(state, ATTIC.id);
    expect(state.errorMessage).toEqual(expect.stringContaining(CLEAR_FAILURE));
  });
});

// ===========================================================================
describe("success closes and re-loads; no success notification", () => {
  it("on a successful designation the modal closes and the page re-loads through its store — DoD-13", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    const loadsBefore = spied.load.length;
    await openSetEmbedding(user, ORCHARD.name);
    await choose(user, "gte-base");
    await save(user);
    await waitForNoDialog();

    expect(laterListLoads(seen(mock), "POST").length).toBeGreaterThan(0);
    expect(spied.load.length).toBeGreaterThan(loadsBefore);
    expect(spied.load[spied.load.length - 1][0]).toBe(state);
  });

  it("the row reflects the re-load, not a local write — a change only the server knows appears too — DoD-13", async () => {
    const user = newUser();
    const { rows, state } = await renderLoaded();
    const attic = rows.find((row) => row.id === ATTIC.id) as LlmServerRow;
    attic.enabled_model_names = ["server-only"];
    await openSetEmbedding(user, ORCHARD.name);
    await choose(user, "gte-base");
    await save(user);
    await waitForNoDialog();
    expect(storeRow(state, ATTIC.id).enabled_model_names).toEqual(["server-only"]);
  });

  it("nothing is written into the page store while the designation is in flight — DoD-13", async () => {
    const user = newUser();
    const pending = deferred<Response>();
    const { state } = await renderLoaded(EVERYONE, {
      override: (method, pathname) => (method === "POST" && DESIGNATE_PATH.test(pathname) ? pending.promise : undefined),
    });
    const before = pageStoreSnapshot(state);
    await openSetEmbedding(user, ORCHARD.name);
    await choose(user, "gte-base");
    await save(user);
    expect(pageStoreSnapshot(state)).toEqual(before);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    pending.resolve(envelopeResponse("llm_unreachable", REFUSAL, 502));
    await flush();
    expect(pageStoreSnapshot(state)).toEqual(before);
  });

  it("no notification and no success message after a designation or a clear — DoD-13", async () => {
    const user = newUser();
    await renderLoaded();
    await openSetEmbedding(user, ORCHARD.name);
    await choose(user, "gte-base");
    await save(user);
    await waitForNoDialog();
    expect(notificationRoots()).toEqual([]);

    const confirm = await openClearConfirm(user, ORCHARD.name);
    await user.click(confirmButton(confirm));
    await flush();
    await waitForNoDialog();
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(screen.queryAllByRole("alert")).toEqual([]);
    expect(document.body.textContent ?? "").not.toMatch(/\bsuccess(ful|fully)?\b/i);
  });

  it("the standalone modal calls onSaved exactly once on success — DoD-13", async () => {
    const user = newUser();
    serveServers(EVERYONE);
    const { onSaved, draft } = renderModal(ORCHARD);
    await flush();
    await choose(user, "gte-base");
    await save(user);
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(draft.submitStatus).toBe("done");
    expect(notificationRoots()).toEqual([]);
  });

  it("no module of this step imports notifyFailure or Mantine's notifications — DoD-13", () => {
    const offenders = STEP_MODULES.flatMap((file) =>
      importSpecifiers(readFileSync(file, "utf8"))
        .filter((spec) => /notifyFailure|@mantine\/notifications/.test(spec))
        .map((spec) => `${path.basename(file)} imports ${spec}`),
    );
    expect(offenders).toEqual([]);
  });
});

// ===========================================================================
describe("data class; free-function effects; fresh per open (D16)", () => {
  it("the draft prototype carries no method and no getter — DoD-14", () => {
    expect(Object.getOwnPropertyNames(EmbeddingDraft.prototype)).toEqual(["constructor"]);
  });

  it("the draft's own fields are observable, none computed, none a function, and start idle — DoD-14", () => {
    const draft = new EmbeddingDraft("nomic-embed");
    const names = Object.getOwnPropertyNames(draft);
    expect([...names].sort()).toEqual(["designated", "selected", "serverErrors", "submitStatus"]);
    const record = draft as unknown as Record<string, unknown>;
    for (const name of names) {
      expect(isObservableProp(draft, name), name).toBe(true);
      expect(isComputedProp(draft, name), name).toBe(false);
      expect(typeof record[name], name).not.toBe("function");
    }
    expect(draftSnapshot(draft)).toEqual({ selected: "nomic-embed", designated: "nomic-embed", serverErrors: {}, submitStatus: "idle" });
  });

  it("the derivation is pure: no writes, no network, same answer twice — DoD-14", () => {
    const mock = stubFetch(() => Promise.reject(new Error("no network expected")));
    for (const draft of [new EmbeddingDraft(null), draftWith("nomic-embed", { selected: "bge-small" })]) {
      const before = draftSnapshot(draft);
      expect(canSubmitEmbedding(draft)).toBe(canSubmitEmbedding(draft));
      expect(draftSnapshot(draft)).toEqual(before);
    }
    expect(mock).not.toHaveBeenCalled();
  });

  it("both effects write only inside actions (strict MobX raises no warning) — DoD-14", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    configure({ enforceActions: "always" });
    try {
      const watchDraft = (draft: EmbeddingDraft) =>
        autorun(() => {
          void draft.selected;
          void draft.designated;
          void JSON.stringify(toJS(draft.serverErrors));
          void draft.submitStatus;
        });
      const watchState = (state: LlmServersPageState) =>
        autorun(() => {
          void JSON.stringify(toJS(state.rows));
          void state.status;
          void state.errorMessage;
        });

      serveServers(EVERYONE);
      const okDraft = draftWith(null, { selected: "gte-base" });
      const d1 = watchDraft(okDraft);
      await submitEmbeddingDesignation(okDraft, ORCHARD.id, () => {});
      d1();
      const okState = new LlmServersPageState();
      const d2 = watchState(okState);
      await clearEmbeddingDesignation(okState, ATTIC.id);
      d2();

      vi.unstubAllGlobals();
      stubFetch(() => Promise.resolve(envelopeResponse("llm_unreachable", REFUSAL, 502)));
      const badDraft = draftWith("nomic-embed", { selected: "qwen-chat" });
      const d3 = watchDraft(badDraft);
      await submitEmbeddingDesignation(badDraft, ATTIC.id, () => {});
      d3();
      const badState = new LlmServersPageState();
      const d4 = watchState(badState);
      await clearEmbeddingDesignation(badState, ATTIC.id);
      d4();
    } finally {
      configure({ enforceActions: "observed" });
    }
    const mobxWarnings = warn.mock.calls.filter((args) => args.some((arg) => String(arg).includes("[MobX]")));
    expect(mobxWarnings).toEqual([]);
  });

  it("the submit given an already-aborted signal writes nothing and saves nothing — DoD-14", async () => {
    serveServers(EVERYONE);
    const draft = draftWith(null, { selected: "gte-base" });
    const before = draftSnapshot(draft);
    const controller = new AbortController();
    controller.abort();
    const onSaved = vi.fn<() => void>();
    await expect(submitEmbeddingDesignation(draft, ORCHARD.id, onSaved, controller.signal)).resolves.toBeUndefined();
    await settle();
    expect(draftSnapshot(draft)).toEqual(before);
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("the clear given an already-aborted signal writes nothing into the page store — DoD-14", async () => {
    serveServers(EVERYONE);
    const state = new LlmServersPageState();
    const before = pageStoreSnapshot(state);
    const controller = new AbortController();
    controller.abort();
    await expect(clearEmbeddingDesignation(state, ATTIC.id, controller.signal)).resolves.toBeUndefined();
    await settle();
    expect(pageStoreSnapshot(state)).toEqual(before);
  });

  it.each<[string, () => Response]>([
    ["a success", () => jsonResponse({ ...ORCHARD, embedding_model_name: "gte-base", embedding_dim: 1024 }, 200)],
    ["a refusal", () => envelopeResponse("llm_unreachable", REFUSAL, 502)],
  ])("%s arriving after the submit's abort is not written — DoD-14", async (_name, answer) => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const draft = draftWith(null, { selected: "gte-base" });
    const controller = new AbortController();
    const onSaved = vi.fn<() => void>();
    const running = submitEmbeddingDesignation(draft, ORCHARD.id, onSaved, controller.signal);
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
    ["a success", () => new Response(null, { status: 204 })],
    ["a failure", () => envelopeResponse("internal_error", CLEAR_FAILURE, 500)],
  ])("%s arriving after the clear's abort is not written — DoD-14", async (_name, answer) => {
    const pending = deferred<Response>();
    stubFetch((input, init) =>
      requestMethod(input, init) === "DELETE" ? pending.promise : Promise.resolve(jsonResponse({ servers: [] }, 200)),
    );
    const state = stateWith(EVERYONE);
    const controller = new AbortController();
    const running = clearEmbeddingDesignation(state, ATTIC.id, controller.signal);
    await settle();
    const atAbort = pageStoreSnapshot(state);
    controller.abort();
    pending.resolve(answer());
    await expect(running).resolves.toBeUndefined();
    await settle();
    expect(pageStoreSnapshot(state)).toEqual(atAbort);
  });

  it("the draft module uses runInAction and makeAutoObservable — DoD-14", () => {
    const source = readSource(DRAFT_SOURCE);
    expect(source).toMatch(/\brunInAction\b/);
    expect(source).toMatch(/\bmakeAutoObservable\b/);
  });

  it("reopening after an unsaved choice shows the stored designation, not the abandoned one — DoD-14", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    await openSetEmbedding(user, ATTIC.name);
    await choose(user, "bge-small");
    await closeModal(user);
    await openSetEmbedding(user, ATTIC.name);
    expect(chosenNames(ATTIC_OFFERED)).toEqual(["nomic-embed"]);
    expect(mutations(mock)).toEqual([]);
  });

  it("each open hands the modal a new picker and a new draft, and re-probes — DoD-14", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    await openSetEmbedding(user, ATTIC.name);
    await choose(user, "bge-small");
    await closeModal(user);
    await openSetEmbedding(user, ATTIC.name);

    const all = opens();
    expect(all).toHaveLength(2);
    expect(all[1].picker).toBeInstanceOf(ModelPicker);
    expect(all[1].draft).toBeInstanceOf(EmbeddingDraft);
    expect(all[1].picker).not.toBe(all[0].picker);
    expect(all[1].draft).not.toBe(all[0].draft);
    expect(all[0].draft.selected).toBe("bge-small");
    expect(all[1].draft.selected).toBe("nomic-embed");
    expect(probeCalls(mock, ATTIC.id)).toHaveLength(2);
  });

  it("the modal is mounted only while open, and opening it leaves the page store unchanged — DoD-14", async () => {
    const user = newUser();
    const { state } = await renderLoaded();
    expect(opens()).toEqual([]);
    const before = pageStoreSnapshot(state);
    await openSetEmbedding(user, ATTIC.name);
    expect(pageStoreSnapshot(state)).toEqual(before);
    await closeModal(user);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(pageStoreSnapshot(state)).toEqual(before);
    const confirm = await openClearConfirm(user, ATTIC.name);
    expect(pageStoreSnapshot(state)).toEqual(before);
    await user.click(within(confirm).getByRole("button", { name: CANCEL_NAME }));
    await waitForNoDialog();
    const page = readSource(PAGE_SOURCE);
    expect(page).toMatch(/new\s+ModelPicker\s*\(/);
    expect(page).toMatch(/new\s+EmbeddingDraft\s*\(/);
  });
});

// ===========================================================================
describe("the complete row menu", () => {
  const FULL_SET: RegExp[] = [TEST_ITEM, EDIT_ITEM, SELECT_MODELS_ITEM, SET_EMBEDDING_ITEM, CLEAR_EMBEDDING_ITEM, DELETE_ITEM];

  it("each row still has exactly one icon-only control, in its last cell — DoD-15", async () => {
    await renderLoaded();
    for (const server of EVERYONE) {
      const row = rowFor(server.name);
      const controls = iconOnlyControls(row);
      expect(controls, server.name).toHaveLength(1);
      const cells = cellsOf(row);
      expect(cells[cells.length - 1].contains(controls[0]), `${server.name}: trigger in the trailing cell`).toBe(true);
    }
  });

  it("the designated row's menu holds exactly the full item set — DoD-15", async () => {
    const user = newUser();
    await renderLoaded();
    const names = await menuItemNames(user, ATTIC.name);
    for (const pattern of FULL_SET) {
      expect(names.filter((name) => pattern.test(name)), String(pattern)).toHaveLength(1);
    }
    expect(names).toHaveLength(FULL_SET.length);
  });

  it("any other row's menu holds the full set without Clear Embedding — DoD-15", async () => {
    const user = newUser();
    await renderLoaded();
    const names = await menuItemNames(user, ORCHARD.name);
    for (const pattern of FULL_SET.filter((p) => p !== CLEAR_EMBEDDING_ITEM)) {
      expect(names.filter((name) => pattern.test(name)), String(pattern)).toHaveLength(1);
    }
    expect(names).toHaveLength(FULL_SET.length - 1);
  });

  it("the trigger is IconDots routed through shared/IconButton, in a w={60} column — DoD-15", () => {
    const source = readSource(PAGE_SOURCE);
    const specs = importSpecifiers(readFileSync(PAGE_SOURCE, "utf8"));
    expect(specs.some((spec) => /(^|\/)shared\/IconButton$/.test(spec))).toBe(true);
    expect(source).toMatch(/<IconButton\b[\s\S]{0,400}?\bicon\s*=\s*\{\s*IconDots\s*\}/);
    expect(source).toMatch(/<Menu\b/);
    expect(source).toMatch(/\bw\s*=\s*\{\s*60\s*\}/);
    expect(source).not.toMatch(/\bActionIcon\b/);
  });
});

// ===========================================================================
describe("ids are strings; no stylesheet", () => {
  it("a row with an id beyond MAX_SAFE_INTEGER is probed, designated and cleared with that id verbatim — DoD-16", async () => {
    const user = newUser();
    const big: LlmServerRow = { ...ORCHARD, id: BIG_ID };
    const { mock, state } = await renderLoaded([big], { offered: { [BIG_ID]: ORCHARD_OFFERED } });
    await openSetEmbedding(user, big.name);
    expect(opens()[0].serverId).toBe(BIG_ID);
    expect(typeof opens()[0].serverId).toBe("string");
    await choose(user, "gte-base");
    await save(user);
    await waitForNoDialog();
    await flush();
    const confirm = await openClearConfirm(user, big.name);
    await user.click(confirmButton(confirm));
    await flush();

    expect(probeCalls(mock, BIG_ID)).toHaveLength(1);
    expect(mutations(mock).map((call) => `${call.method} ${call.path}`)).toEqual([
      `POST ${LIST_PATH}/${BIG_ID}/embedding-model`,
      `DELETE ${LIST_PATH}/${BIG_ID}/embedding-model`,
    ]);
    expect(spied.clear[0][1]).toBe(BIG_ID);
    expect(storeRow(state, BIG_ID).embedding_model_name).toBeNull();
  });

  it("the free functions use the string id they are given — DoD-16", async () => {
    const { mock } = serveServers([{ ...ORCHARD, id: BIG_ID }]);
    await submitEmbeddingDesignation(draftWith(null, { selected: "gte-base" }), BIG_ID, () => {});
    await clearEmbeddingDesignation(new LlmServersPageState(), BIG_ID);
    expect(mutations(mock).map((call) => `${call.method} ${call.path}`)).toEqual([
      `POST ${LIST_PATH}/${BIG_ID}/embedding-model`,
      `DELETE ${LIST_PATH}/${BIG_ID}/embedding-model`,
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
