// Feature 006, step 007 — the server form modal: register and edit a connection, the hand-rolled
// MobX draft, and D9's three-state API-key rule (DoD-1..DoD-17). DoD-18 and DoD-19 are
// [manual/live].
//
// Expected behaviour comes from the step's Interface intent and Definition of done,
// 007.context.md and context.md (D1 no active flag, D5 two kinds, D9 the pointer payload table,
// D16 MobX rules, D17 routes, D18 no confirm, no success toasts, never optimistic). Bindings come
// from the frozen `### Step 007` record: `ServerFormDraft` (constructed from an optional row), the
// pure `serverFormClientErrors` / `serverFormErrors` / `canSubmitServerForm`, the effect
// `submitServerForm(draft, serverId | null, onSaved, signal?)`, and
// `<ServerFormModal draft onClose onSaved />` which the page mounts only while open. The page is
// rendered as in step 006's test: `<LlmServersPage state={new LlmServersPageState()} />` under
// `AppProviders` + `MemoryRouter`. `fetch` is stubbed per test with a tiny in-memory backend
// (GET list, POST register, PATCH edit — applying D9 the way the server does). `notifyFailure` is
// mocked at file level. The page-store module and the modal module are wrapped pass-through so
// the page's loads and the draft each open hands the modal are observable — behaviour unchanged.
//
// D9's payload table is covered case by case twice: once against `submitServerForm` directly and
// once through the rendered page.
//
// Recognition conventions (from spec wording, for the verifier):
// - The modal: `role="dialog"`. Fields by visible label: name /\bname\b/i, base URL
//   /\burl\b|address|endpoint/i, kind /\b(kind|type|backend|provider)\b/i (the `<input>` of the
//   Mantine `Select`; options are `role="option"` in its opened dropdown). The pointer field is the
//   dialog's one masked input, `input[type="password"]` (a `PasswordInput`, DoD-15).
// - The submit control: the one dialog button named /save|register|create|add|submit|update/i
//   (not cancel/close).
// - A field's error or description "renders on its field": its text is reachable through the
//   input's `aria-describedby`, or sits in that input's Mantine wrapper error/description element.
//   "Above the form": text inside the dialog preceding the first of the four fields in document
//   order.
// - The page's register button: the one button outside the dialog named
//   /\b(add|register|new|create)\b/i. The row menu's edit item: `role="menuitem"` named
//   /\bedit\b/i inside the dropdown owned by the row's trigger (step 006's menu idiom).
// - Notifications: `.mantine-Notification-root`.
import { readFileSync } from "node:fs";
import path from "node:path";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { autorun, configure, isComputedProp, isObservableProp, runInAction, toJS } from "mobx";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LlmServersPage } from "../../src/admin/LlmServersPage";
import { type LlmServerRow, LlmServersPageState } from "../../src/admin/llmServersPageState";
import * as draftModule from "../../src/admin/serverFormDraft";
import {
  canSubmitServerForm,
  ServerFormDraft,
  type ServerFormPayload,
  serverFormClientErrors,
  serverFormErrors,
  submitServerForm,
} from "../../src/admin/serverFormDraft";
import { ServerFormModal } from "../../src/admin/ServerFormModal";
import { documentNavigation } from "../../src/shared/api";
import { AppProviders } from "../../src/shared/AppProviders";

const { notifyFailureSpy, spied } = vi.hoisted(() => ({
  notifyFailureSpy: vi.fn(),
  spied: { load: [] as unknown[][], drafts: [] as unknown[] },
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
vi.mock("../../src/admin/ServerFormModal", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../src/admin/ServerFormModal")>();
  const { createElement } = await import("react");
  return {
    ...actual,
    ServerFormModal: (props: import("../../src/admin/ServerFormModal").ServerFormModalProps) => {
      spied.drafts.push(props.draft);
      return createElement(actual.ServerFormModal, props);
    },
  };
});

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type User = ReturnType<typeof userEvent.setup>;
type Seen = { method: string; path: string; search: string; body: unknown };
type DraftFields = Partial<
  Pick<ServerFormDraft, "name" | "kind" | "baseUrl" | "pointer" | "pointerTouched" | "serverErrors" | "submitStatus">
>;

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const ADMIN_SRC = path.join(FRONTEND_ROOT, "src", "admin");
const DRAFT_SOURCE = path.join(ADMIN_SRC, "serverFormDraft.ts");
const MODAL_SOURCE = path.join(ADMIN_SRC, "ServerFormModal.tsx");
const PAGE_SOURCE = path.join(ADMIN_SRC, "LlmServersPage.tsx");
const STEP_MODULES = [DRAFT_SOURCE, MODAL_SOURCE, PAGE_SOURCE];

const LIST_PATH = "/api/admin/llm-servers";
const ITEM_PATH = /^\/api\/admin\/llm-servers\/([^/]+)$/;
const BIG_ID = "9007199254740993"; // 2^53 + 1 — not representable as a JS number
const STAMP = "2026-09-30T12:00:00.000000+00:00";
const FAILURE_MESSAGE = "The registry exploded zq-707.";

const NAME_LABEL = /\bname\b/i;
const URL_LABEL = /\burl\b|address|endpoint/i;
const KIND_LABEL = /\b(kind|type|backend|provider)\b/i;
const SUBMIT_NAME = /save|register|create|add|submit|update/i;
const NOT_SUBMIT_NAME = /cancel|close/i;
const REGISTER_BUTTON = /\b(add|register|new|create)\b/i;
const EDIT_ITEM = /\bedit\b/i;
const LLAMASWAP_OPTION = /llama\s*-?\s*swap/i;
const OPENAI_OPTION = /open\s*-?\s*ai/i;
const NOTIFICATION_ROOT = ".mantine-Notification-root";

const ATTIC: LlmServerRow = {
  id: "7340032000000201",
  name: "Attic box",
  kind: "llamaswap",
  base_url: "http://attic.lan:8080",
  has_api_key: false,
  enabled_model_names: ["qwen-chat"],
  embedding_model_name: null,
  embedding_dim: null,
  last_test_at: null,
  last_test_ok: null,
  last_test_error: null,
  created_at: "2026-09-01T08:00:00.000000+00:00",
  updated_at: "2026-09-01T08:00:00.000000+00:00",
};
/** A row that records a pointer — the server reports only the boolean. */
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
const EVERYONE: LlmServerRow[] = [ATTIC, ORCHARD];

beforeEach(() => {
  notifyFailureSpy.mockClear();
  spied.load.length = 0;
  spied.drafts.length = 0;
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

function copyRows(rows: readonly LlmServerRow[]): LlmServerRow[] {
  return rows.map((row) => ({ ...row, enabled_model_names: [...row.enabled_model_names] }));
}

type Override = (method: string, path: string, body: unknown) => Promise<Response> | undefined;
type ServeOptions = { nextId?: string; override?: Override };

/**
 * A tiny in-memory backend: GET lists, POST registers (201, the new row), PATCH applies only the
 * keys present (200, the row) — `api_key_ref` omitted keeps the recorded pointer, `""` clears it,
 * any other value replaces it, which is D9 as step 005's route implements it.
 */
function serveServers(initial: readonly LlmServerRow[], options: ServeOptions = {}) {
  const rows = copyRows(initial);
  let nextId = options.nextId ?? "7340032000000401";
  const mock = stubFetch((input, init) => {
    const method = requestMethod(input, init);
    const pathname = requestUrl(input).pathname;
    const body = requestBody(init);
    const custom = options.override?.(method, pathname, body);
    if (custom !== undefined) return custom;
    if (method === "GET" && pathname === LIST_PATH) {
      return Promise.resolve(jsonResponse({ servers: copyRows(rows) }, 200));
    }
    if (method === "POST" && pathname === LIST_PATH) {
      const payload = (body ?? {}) as ServerFormPayload;
      const row: LlmServerRow = {
        id: nextId,
        name: payload.name ?? "",
        kind: payload.kind ?? "llamaswap",
        base_url: payload.base_url ?? "",
        has_api_key: typeof payload.api_key_ref === "string" && payload.api_key_ref !== "",
        enabled_model_names: [],
        embedding_model_name: null,
        embedding_dim: null,
        last_test_at: null,
        last_test_ok: null,
        last_test_error: null,
        created_at: STAMP,
        updated_at: STAMP,
      };
      nextId = `${nextId}9`;
      rows.push(row);
      return Promise.resolve(jsonResponse({ ...row }, 201));
    }
    const itemMatch = ITEM_PATH.exec(pathname);
    if (method === "PATCH" && itemMatch !== null) {
      const row = rows.find((candidate) => candidate.id === itemMatch[1]);
      if (row === undefined) {
        return Promise.resolve(envelopeResponse("llm_server_not_found", "That connection does not exist.", 404));
      }
      const patch = (body ?? {}) as ServerFormPayload;
      if (patch.name !== undefined) row.name = patch.name;
      if (patch.kind !== undefined) row.kind = patch.kind;
      if (patch.base_url !== undefined) row.base_url = patch.base_url;
      if (typeof patch.api_key_ref === "string") row.has_api_key = patch.api_key_ref !== "";
      row.updated_at = STAMP;
      return Promise.resolve(jsonResponse({ ...row, enabled_model_names: [...row.enabled_model_names] }, 200));
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

// ---------------------------------------------------------------- drafts

function registerDraft(fields: DraftFields = {}): ServerFormDraft {
  const draft = new ServerFormDraft();
  runInAction(() => {
    Object.assign(draft, fields);
  });
  return draft;
}

function editDraft(row: LlmServerRow, fields: DraftFields = {}): ServerFormDraft {
  const draft = new ServerFormDraft(row);
  runInAction(() => {
    Object.assign(draft, fields);
  });
  return draft;
}

const VALID_REGISTER: DraftFields = { name: "Loft rig", kind: "llamaswap", baseUrl: "http://loft.lan:8080" };

function draftSnapshot(draft: ServerFormDraft) {
  return {
    name: draft.name,
    kind: draft.kind,
    baseUrl: draft.baseUrl,
    pointer: draft.pointer,
    pointerTouched: draft.pointerTouched,
    serverErrors: toJS(draft.serverErrors),
    submitStatus: draft.submitStatus,
  };
}

/** The keys of an errors map that actually carry a message. */
function presentKeys(errors: Partial<Record<string, string>>): string[] {
  return Object.entries(errors)
    .filter(([, value]) => typeof value === "string" && value.length > 0)
    .map(([key]) => key)
    .sort();
}

function hasKey(body: unknown, key: string): boolean {
  return typeof body === "object" && body !== null && Object.prototype.hasOwnProperty.call(body, key);
}

// ---------------------------------------------------------------- render

function renderModal(draft: ServerFormDraft) {
  const onClose = vi.fn<() => void>();
  const onSaved = vi.fn<() => void>();
  const view = render(
    <AppProviders>
      <ServerFormModal draft={draft} onClose={onClose} onSaved={onSaved} />
    </AppProviders>,
  );
  return { onClose, onSaved, view };
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

function pointerInput(): HTMLInputElement {
  const found = Array.from(dialog().querySelectorAll<HTMLInputElement>("input[type='password']"));
  expect(found, "masked inputs in the dialog").toHaveLength(1);
  return found[0];
}

function inputsLabelled(label: RegExp): HTMLInputElement[] {
  const masked = Array.from(dialog().querySelectorAll<HTMLInputElement>("input[type='password']"));
  return within(dialog())
    .queryAllByLabelText(label)
    .filter((el): el is HTMLInputElement => el instanceof HTMLInputElement)
    .filter((el) => !masked.includes(el));
}

function nameInput(): HTMLInputElement {
  const found = inputsLabelled(NAME_LABEL);
  expect(found, "name inputs").toHaveLength(1);
  return found[0];
}

function baseUrlInput(): HTMLInputElement {
  const found = inputsLabelled(URL_LABEL);
  expect(found, "base URL inputs").toHaveLength(1);
  return found[0];
}

function kindInput(): HTMLInputElement {
  const found = inputsLabelled(KIND_LABEL);
  expect(found, "kind inputs").toHaveLength(1);
  return found[0];
}

function firstField(): HTMLInputElement {
  const fields = [nameInput(), kindInput(), baseUrlInput(), pointerInput()];
  return fields.reduce((first, candidate) =>
    (candidate.compareDocumentPosition(first) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0 ? candidate : first,
  );
}

function submitControl(): HTMLElement {
  const found = within(dialog())
    .queryAllByRole("button")
    .filter((el) => {
      const name = el.getAttribute("aria-label") ?? el.textContent ?? "";
      return SUBMIT_NAME.test(name) && !NOT_SUBMIT_NAME.test(name);
    });
  expect(found, "submit controls in the dialog").toHaveLength(1);
  return found[0];
}

function describedText(input: HTMLElement): string {
  const ids = (input.getAttribute("aria-describedby") ?? "").split(/\s+/).filter(Boolean);
  return ids.map((id) => document.getElementById(id)?.textContent ?? "").join(" ");
}

/** What renders on a field: its aria-describedby text plus its Mantine wrapper's error/description. */
function fieldNotes(input: HTMLElement): string {
  const parts = [describedText(input)];
  const wrapper = input.closest(
    ".mantine-InputWrapper-root, .mantine-PasswordInput-root, .mantine-TextInput-root, .mantine-Select-root",
  );
  if (wrapper !== null) {
    for (const el of Array.from(wrapper.querySelectorAll("[class*='-error'], [class*='-description']"))) {
      parts.push(el.textContent ?? "");
    }
  }
  return parts.join(" ").replace(/\s+/g, " ");
}

/** All text inside the dialog that precedes `target` in document order — "above the form". */
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

async function openKindOptions(user: User): Promise<HTMLElement[]> {
  await user.click(kindInput());
  return screen.findAllByRole("option");
}

async function chooseKind(user: User, which: "llamaswap" | "openai"): Promise<void> {
  const options = await openKindOptions(user);
  const wanted = which === "llamaswap" ? LLAMASWAP_OPTION : OPENAI_OPTION;
  const option = options.find((candidate) => wanted.test(candidate.textContent ?? ""));
  expect(option, `the ${which} option`).toBeDefined();
  await user.click(option as HTMLElement);
  await flush(2);
}

async function fillRegister(
  user: User,
  fields: { name: string; kind: "llamaswap" | "openai"; baseUrl: string; pointer?: string },
): Promise<void> {
  await user.type(nameInput(), fields.name);
  await chooseKind(user, fields.kind);
  await user.type(baseUrlInput(), fields.baseUrl);
  if (fields.pointer !== undefined) await user.type(pointerInput(), fields.pointer);
}

async function submit(user: User): Promise<void> {
  await user.click(submitControl());
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
    .filter((el) => NOT_SUBMIT_NAME.test(el.getAttribute("aria-label") ?? el.textContent ?? ""));
  if (named.length > 0) {
    await user.click(named[0]);
  } else {
    nameInput().focus();
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

function registerButton(): HTMLElement {
  const found = screen
    .queryAllByRole("button", { name: REGISTER_BUTTON })
    .filter((el) => el.closest("[role='dialog']") === null);
  expect(found, "register buttons outside the dialog").toHaveLength(1);
  return found[0];
}

async function openRegister(user: User): Promise<void> {
  await user.click(registerButton());
  await screen.findByRole("dialog");
}

async function openEdit(user: User, name: string): Promise<void> {
  const menu = await openRowMenu(user, name);
  const item = await within(menu).findByRole("menuitem", { name: EDIT_ITEM });
  await user.click(item);
  await screen.findByRole("dialog");
}

function storeRow(state: LlmServersPageState, id: string): LlmServerRow {
  const row = state.rows.find((candidate) => candidate.id === id);
  expect(row, `store row ${id}`).toBeDefined();
  return row as LlmServerRow;
}

function pageStoreSnapshot(state: LlmServersPageState) {
  return {
    names: Object.getOwnPropertyNames(state).sort(),
    rows: toJS(state.rows),
    status: state.status,
    errorMessage: state.errorMessage,
    testingId: state.testingId,
  };
}

function modalDrafts(): ServerFormDraft[] {
  return Array.from(new Set(spied.drafts)) as ServerFormDraft[];
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
describe("registering from the page header", () => {
  it("the header button opens the modal with empty name, base URL and pointer fields — DoD-1 (UC-010)", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    expect(screen.queryByRole("dialog")).toBeNull();
    const before = mock.mock.calls.length;

    await openRegister(user);

    expect(nameInput().value).toBe("");
    expect(baseUrlInput().value).toBe("");
    expect(pointerInput().value).toBe("");
    expect(kindInput()).toBeInTheDocument();
    await flush();
    expect(mock.mock.calls.length, "opening issues no request").toBe(before);
  });

  it("filling name, kind and base URL and submitting POSTs the registration, with no confirm step — DoD-1 (US-012.AC-1, UC-010)", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    await openRegister(user);
    await fillRegister(user, { name: "Loft rig", kind: "llamaswap", baseUrl: "http://loft.lan:8080" });
    await submit(user);

    expect(mutations(mock)).toEqual([
      {
        method: "POST",
        path: LIST_PATH,
        search: "",
        body: { name: "Loft rig", kind: "llamaswap", base_url: "http://loft.lan:8080" },
      },
    ]);
    expect(screen.queryAllByRole("dialog").length, "no second dialog appeared").toBeLessThanOrEqual(1);
  });

  it("on success the modal closes and the new row is visible after the page re-loads — DoD-1 (US-012.AC-2)", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    expect(bodyRows()).toHaveLength(2);
    await openRegister(user);
    await fillRegister(user, { name: "Loft rig", kind: "openai", baseUrl: "https://loft.example/v1" });
    await submit(user);
    await waitForNoDialog();

    const calls = seen(mock);
    const postIndex = calls.findIndex((call) => call.method === "POST");
    expect(postIndex).toBeGreaterThanOrEqual(0);
    expect(calls.slice(postIndex + 1).some((call) => call.method === "GET" && call.path === LIST_PATH)).toBe(true);
    expect(bodyRows()).toHaveLength(3);
    rowFor("Loft rig");
  });
});

// ===========================================================================
describe("the kind select", () => {
  it("offers exactly two options, llamaswap and OpenAI — DoD-2 (D5)", async () => {
    const user = newUser();
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    renderModal(new ServerFormDraft());
    const options = await openKindOptions(user);
    expect(options).toHaveLength(2);
    const texts = options.map((option) => option.textContent ?? "");
    expect(texts.filter((text) => LLAMASWAP_OPTION.test(text) && !OPENAI_OPTION.test(text))).toHaveLength(1);
    expect(texts.filter((text) => OPENAI_OPTION.test(text) && !LLAMASWAP_OPTION.test(text))).toHaveLength(1);
  });

  it.each<["llamaswap" | "openai"]>([["llamaswap"], ["openai"]])(
    "choosing %s sends the backend's literal value, never the display label — DoD-2 (US-012.AC-1)",
    async (kind) => {
      const user = newUser();
      const { mock } = serveServers([]);
      renderModal(new ServerFormDraft());
      await fillRegister(user, { name: "Loft rig", kind, baseUrl: "http://loft.lan:8080" });
      await submit(user);
      const posts = mutations(mock);
      expect(posts).toHaveLength(1);
      expect((posts[0].body as Record<string, unknown>).kind).toBe(kind);
    },
  );

  it("choosing OpenAI after llamaswap switches what is sent — DoD-2", async () => {
    const user = newUser();
    const { mock } = serveServers([]);
    renderModal(new ServerFormDraft());
    await chooseKind(user, "llamaswap");
    await fillRegister(user, { name: "Loft rig", kind: "openai", baseUrl: "http://loft.lan:8080" });
    expect(kindInput().value).toMatch(OPENAI_OPTION);
    await submit(user);
    expect((mutations(mock)[0].body as Record<string, unknown>).kind).toBe("openai");
  });

  it("an edit draft of an OpenAI row shows OpenAI selected, with the row's name and base URL — DoD-2, DoD-4", () => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    renderModal(new ServerFormDraft(ORCHARD));
    expect(kindInput().value).toMatch(OPENAI_OPTION);
    expect(nameInput().value).toBe(ORCHARD.name);
    expect(baseUrlInput().value).toBe(ORCHARD.base_url);
  });
});

// ===========================================================================
describe("D9 — the payload table, at the submit function", () => {
  it("register, pointer left empty: POSTs name, kind and base URL and omits the pointer key — DoD-3", async () => {
    const { mock } = serveServers([]);
    const onSaved = vi.fn<() => void>();
    await expect(submitServerForm(registerDraft(VALID_REGISTER), null, onSaved)).resolves.toBeUndefined();
    const calls = mutations(mock);
    expect(calls).toEqual([
      { method: "POST", path: LIST_PATH, search: "", body: { name: "Loft rig", kind: "llamaswap", base_url: "http://loft.lan:8080" } },
    ]);
    expect(hasKey(calls[0].body, "api_key_ref")).toBe(false);
    expect(onSaved).toHaveBeenCalledTimes(1);
  });

  it("register, pointer filled: the key carries the value — DoD-3", async () => {
    const { mock } = serveServers([]);
    const draft = registerDraft({ ...VALID_REGISTER, kind: "openai", pointer: "$LOFT_KEY", pointerTouched: true });
    await submitServerForm(draft, null, () => {});
    expect(mutations(mock)).toEqual([
      {
        method: "POST",
        path: LIST_PATH,
        search: "",
        body: { name: "Loft rig", kind: "openai", base_url: "http://loft.lan:8080", api_key_ref: "$LOFT_KEY" },
      },
    ]);
  });

  it("edit, pointer never touched: PATCHes with no pointer key at all — DoD-4", async () => {
    const { mock, rows } = serveServers(EVERYONE);
    const draft = editDraft(ORCHARD);
    expect(draft.pointer).toBe("");
    const onSaved = vi.fn<() => void>();
    await submitServerForm(draft, ORCHARD.id, onSaved);
    const calls = mutations(mock);
    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("PATCH");
    expect(calls[0].path).toBe(`${LIST_PATH}/${ORCHARD.id}`);
    expect(hasKey(calls[0].body, "api_key_ref")).toBe(false);
    expect(calls[0].body ?? {}).toEqual({});
    expect(rows.find((row) => row.id === ORCHARD.id)?.has_api_key).toBe(true);
    expect(onSaved).toHaveBeenCalledTimes(1);
  });

  it("edit, pointer never touched but the name changed: still no pointer key — DoD-4", async () => {
    const { mock } = serveServers(EVERYONE);
    await submitServerForm(editDraft(ORCHARD, { name: "Orchard renamed" }), ORCHARD.id, () => {});
    expect(mutations(mock).map((call) => call.body)).toEqual([{ name: "Orchard renamed" }]);
  });

  it("edit, pointer touched and left empty: the key is present as an empty string — DoD-5", async () => {
    const { mock, rows } = serveServers(EVERYONE);
    await submitServerForm(editDraft(ORCHARD, { pointer: "", pointerTouched: true }), ORCHARD.id, () => {});
    const calls = mutations(mock);
    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("PATCH");
    expect(calls[0].path).toBe(`${LIST_PATH}/${ORCHARD.id}`);
    expect(calls[0].body).toEqual({ api_key_ref: "" });
    expect(hasKey(calls[0].body, "api_key_ref")).toBe(true);
    expect(rows.find((row) => row.id === ORCHARD.id)?.has_api_key).toBe(false);
  });

  it("edit, pointer touched and filled: the key carries the new value — DoD-6", async () => {
    const { mock } = serveServers(EVERYONE);
    await submitServerForm(
      editDraft(ORCHARD, { pointer: "$ORCHARD_NEW_KEY", pointerTouched: true }),
      ORCHARD.id,
      () => {},
    );
    const calls = mutations(mock);
    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("PATCH");
    expect(calls[0].body).toEqual({ api_key_ref: "$ORCHARD_NEW_KEY" });
  });

  it("edit: only the name changed sends only the name — DoD-7 (UC-010)", async () => {
    const { mock } = serveServers(EVERYONE);
    await submitServerForm(editDraft(ORCHARD, { name: "Orchard renamed" }), ORCHARD.id, () => {});
    expect(mutations(mock)[0].body).toEqual({ name: "Orchard renamed" });
  });

  it("edit: only the kind changed sends only the kind — DoD-7", async () => {
    const { mock } = serveServers(EVERYONE);
    await submitServerForm(editDraft(ORCHARD, { kind: "llamaswap" }), ORCHARD.id, () => {});
    expect(mutations(mock)[0].body).toEqual({ kind: "llamaswap" });
  });

  it("edit: only the base URL changed sends only base_url — DoD-7", async () => {
    const { mock } = serveServers(EVERYONE);
    await submitServerForm(editDraft(ORCHARD, { baseUrl: "https://api.orchard.example/" }), ORCHARD.id, () => {});
    expect(mutations(mock)[0].body).toEqual({ base_url: "https://api.orchard.example/" });
  });

  it("edit: a field set back to the row's value is not sent — DoD-7", async () => {
    const { mock } = serveServers(EVERYONE);
    const draft = editDraft(ORCHARD, { name: "Something else" });
    runInAction(() => {
      draft.name = ORCHARD.name;
    });
    await submitServerForm(draft, ORCHARD.id, () => {});
    const body = mutations(mock)[0].body ?? {};
    expect(hasKey(body, "name")).toBe(false);
    expect(body).toEqual({});
  });

  it("edit: several changes send exactly those fields — DoD-7, DoD-6", async () => {
    const { mock } = serveServers(EVERYONE);
    await submitServerForm(
      editDraft(ATTIC, { name: "Attic renamed", pointer: "$ATTIC_KEY", pointerTouched: true }),
      ATTIC.id,
      () => {},
    );
    expect(mutations(mock)[0].body).toEqual({ name: "Attic renamed", api_key_ref: "$ATTIC_KEY" });
  });

  it("success marks the draft done and invokes the callback exactly once — DoD-14", async () => {
    serveServers(EVERYONE);
    const draft = editDraft(ORCHARD, { name: "Orchard renamed" });
    const onSaved = vi.fn<() => void>();
    await submitServerForm(draft, ORCHARD.id, onSaved);
    expect(draft.submitStatus).toBe("done");
    expect(onSaved).toHaveBeenCalledTimes(1);
  });
});

// ===========================================================================
describe("D9 — the payload table, through the page", () => {
  it("register with the pointer left empty omits the key — DoD-3", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    await openRegister(user);
    await fillRegister(user, { name: "Loft rig", kind: "llamaswap", baseUrl: "http://loft.lan:8080" });
    await submit(user);
    const posts = mutations(mock);
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({ name: "Loft rig", kind: "llamaswap", base_url: "http://loft.lan:8080" });
    expect(hasKey(posts[0].body, "api_key_ref")).toBe(false);
  });

  it("register with the pointer filled sends the value — DoD-3", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    await openRegister(user);
    await fillRegister(user, {
      name: "Loft rig",
      kind: "openai",
      baseUrl: "https://loft.example",
      pointer: "$LOFT_KEY",
    });
    await submit(user);
    await waitForNoDialog();
    const posts = mutations(mock);
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({
      name: "Loft rig",
      kind: "openai",
      base_url: "https://loft.example",
      api_key_ref: "$LOFT_KEY",
    });
    expect(state.rows.find((row) => row.name === "Loft rig")?.has_api_key).toBe(true);
  });

  it("Edit on a row that records a pointer shows the pointer field empty — DoD-4", async () => {
    const user = newUser();
    await renderLoaded();
    await openEdit(user, ORCHARD.name);
    expect(pointerInput().value).toBe("");
    expect(nameInput().value).toBe(ORCHARD.name);
    expect(baseUrlInput().value).toBe(ORCHARD.base_url);
  });

  it("submitting an edit without touching the pointer sends no pointer key, and the row still reports an API key — DoD-4", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    await openEdit(user, ORCHARD.name);
    await submit(user);
    await waitForNoDialog();

    const patches = mutations(mock);
    expect(patches).toHaveLength(1);
    expect(patches[0].method).toBe("PATCH");
    expect(patches[0].path).toBe(`${LIST_PATH}/${ORCHARD.id}`);
    expect(hasKey(patches[0].body, "api_key_ref")).toBe(false);
    expect(patches[0].body ?? {}).toEqual({});
    const calls = seen(mock);
    const patchIndex = calls.findIndex((call) => call.method === "PATCH");
    expect(calls.slice(patchIndex + 1).some((call) => call.method === "GET" && call.path === LIST_PATH)).toBe(true);
    expect(storeRow(state, ORCHARD.id).has_api_key).toBe(true);
  });

  it("typing into the pointer and clearing it sends the key as an empty string, and the row then reports no API key — DoD-5", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    await openEdit(user, ORCHARD.name);
    await user.type(pointerInput(), "$TEMPORARY_ZQ");
    await user.clear(pointerInput());
    expect(pointerInput().value).toBe("");
    await submit(user);
    await waitForNoDialog();

    const patches = mutations(mock);
    expect(patches).toHaveLength(1);
    expect(patches[0].method).toBe("PATCH");
    expect(patches[0].body).toEqual({ api_key_ref: "" });
    expect(hasKey(patches[0].body, "api_key_ref")).toBe(true);
    expect(storeRow(state, ORCHARD.id).has_api_key).toBe(false);
  });

  it("typing a new pointer sends it and the row still reports an API key — DoD-6 (UC-010)", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    await openEdit(user, ORCHARD.name);
    await user.type(pointerInput(), "$ORCHARD_NEW_KEY");
    await submit(user);
    await waitForNoDialog();

    const patches = mutations(mock);
    expect(patches).toHaveLength(1);
    expect(patches[0].body).toEqual({ api_key_ref: "$ORCHARD_NEW_KEY" });
    expect(storeRow(state, ORCHARD.id).has_api_key).toBe(true);
  });

  it("typing a pointer on a row that had none gives it an API key — DoD-6", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    await openEdit(user, ATTIC.name);
    await user.type(pointerInput(), "$ATTIC_KEY");
    await submit(user);
    await waitForNoDialog();
    expect(mutations(mock).map((call) => call.body)).toEqual([{ api_key_ref: "$ATTIC_KEY" }]);
    expect(storeRow(state, ATTIC.id).has_api_key).toBe(true);
  });

  it("an edit that changes only the name sends only the name — DoD-7 (UC-010)", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    await openEdit(user, ORCHARD.name);
    await user.clear(nameInput());
    await user.type(nameInput(), "Orchard renamed");
    await submit(user);
    await waitForNoDialog();

    const patches = mutations(mock);
    expect(patches).toHaveLength(1);
    expect(patches[0].method).toBe("PATCH");
    expect(patches[0].path).toBe(`${LIST_PATH}/${ORCHARD.id}`);
    expect(patches[0].body).toEqual({ name: "Orchard renamed" });
    for (const key of ["kind", "base_url", "api_key_ref"]) {
      expect(hasKey(patches[0].body, key), key).toBe(false);
    }
    rowFor("Orchard renamed");
    expect(storeRow(state, ORCHARD.id).has_api_key).toBe(true);
  });
});

// ===========================================================================
describe("the pointer is checked in the client", () => {
  it.each<[string, string]>([
    ["empty", ""],
    ["a dollar and one character", "$X"],
    ["a typical pointer", "$OPENAI_API_KEY"],
  ])("accepts %s — DoD-8", (_name, pointer) => {
    const draft = registerDraft({ ...VALID_REGISTER, pointer, pointerTouched: pointer !== "" });
    expect(serverFormClientErrors(draft).pointer).toBeUndefined();
    expect(canSubmitServerForm(draft)).toBe(true);
  });

  it.each<[string, string]>([
    ["a raw key", "sk-live-raw-zq"],
    ["a bare dollar", "$"],
    ["a leading space", " $OPENAI_API_KEY"],
    ["a dollar not at the start", "OPENAI$KEY"],
  ])("refuses %s, with a message on the pointer key — DoD-8", (_name, pointer) => {
    const draft = registerDraft({ ...VALID_REGISTER, pointer, pointerTouched: true });
    const message = serverFormClientErrors(draft).pointer;
    expect(typeof message).toBe("string");
    expect((message ?? "").length).toBeGreaterThan(0);
    expect(canSubmitServerForm(draft)).toBe(false);
  });

  it("the same rule applies to an edit — DoD-8", () => {
    const draft = editDraft(ORCHARD, { pointer: "sk-live-raw-zq", pointerTouched: true });
    expect(presentKeys(serverFormClientErrors(draft))).toEqual(["pointer"]);
    expect(canSubmitServerForm(draft)).toBe(false);
  });

  it("a raw key typed at register shows the message on the pointer field and issues no request — DoD-8", async () => {
    const user = newUser();
    const { mock } = serveServers([]);
    renderModal(new ServerFormDraft());
    await fillRegister(user, {
      name: "Loft rig",
      kind: "openai",
      baseUrl: "https://loft.example",
      pointer: "sk-live-raw-zq",
    });
    const expected = serverFormClientErrors(
      registerDraft({ name: "Loft rig", kind: "openai", baseUrl: "https://loft.example", pointer: "sk-live-raw-zq", pointerTouched: true }),
    ).pointer as string;
    expect(fieldNotes(pointerInput())).toContain(expected);
    expect(fieldNotes(nameInput())).not.toContain(expected);
    expect(fieldNotes(baseUrlInput())).not.toContain(expected);
    expect(submitControl()).toBeDisabled();

    await user.click(submitControl());
    await flush();
    expect(mutations(mock)).toEqual([]);
  });

  it("a raw key typed on an edit issues no PATCH — DoD-8", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    await openEdit(user, ORCHARD.name);
    await user.type(pointerInput(), "sk-live-raw-zq");
    const expected = serverFormClientErrors(editDraft(ORCHARD, { pointer: "sk-live-raw-zq", pointerTouched: true }))
      .pointer as string;
    expect(fieldNotes(pointerInput())).toContain(expected);
    await user.click(submitControl());
    await flush();
    expect(mutations(mock)).toEqual([]);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

// ===========================================================================
describe("name and base URL are checked in the client", () => {
  it("an empty register draft reports name and base URL, and cannot be submitted — DoD-9", () => {
    const draft = new ServerFormDraft();
    const errors = serverFormClientErrors(draft);
    expect(presentKeys(errors)).toEqual(["baseUrl", "name"]);
    expect(canSubmitServerForm(draft)).toBe(false);
  });

  it("a filled register draft reports nothing — DoD-9", () => {
    const draft = registerDraft(VALID_REGISTER);
    expect(presentKeys(serverFormClientErrors(draft))).toEqual([]);
    expect(canSubmitServerForm(draft)).toBe(true);
  });

  it.each<[string]>([
    ["http://host.lan:8080"],
    ["http://host.lan:8080/"],
    ["http://host.lan:8080/v1"],
    ["http://127.0.0.1:8080/v1/"],
    ["https://api.orchard.example"],
  ])("accepts the absolute base URL %s — DoD-9", (baseUrl) => {
    const draft = registerDraft({ ...VALID_REGISTER, baseUrl });
    expect(serverFormClientErrors(draft).baseUrl).toBeUndefined();
  });

  it.each<[string]>([[""], ["host.lan:8080"], ["attic.lan"], ["/v1"], ["ftp://host.lan/models"], ["localhost"]])(
    "refuses the base URL %j — DoD-9",
    (baseUrl) => {
      const draft = registerDraft({ ...VALID_REGISTER, baseUrl });
      const message = serverFormClientErrors(draft).baseUrl;
      expect(typeof message).toBe("string");
      expect((message ?? "").length).toBeGreaterThan(0);
      expect(canSubmitServerForm(draft)).toBe(false);
    },
  );

  it("an emptied name on an edit is refused — DoD-9", () => {
    const draft = editDraft(ORCHARD, { name: "" });
    expect(presentKeys(serverFormClientErrors(draft))).toEqual(["name"]);
    expect(canSubmitServerForm(draft)).toBe(false);
  });

  it("an emptied name shows its message on the name field and issues no request — DoD-9", async () => {
    const user = newUser();
    const { mock } = serveServers([]);
    renderModal(new ServerFormDraft());
    await fillRegister(user, { name: "x", kind: "llamaswap", baseUrl: "http://loft.lan:8080" });
    await user.clear(nameInput());
    const expected = serverFormClientErrors(registerDraft({ ...VALID_REGISTER, name: "" })).name as string;
    expect(fieldNotes(nameInput())).toContain(expected);
    expect(fieldNotes(baseUrlInput())).not.toContain(expected);
    expect(submitControl()).toBeDisabled();
    await user.click(submitControl());
    await flush();
    expect(mutations(mock)).toEqual([]);
  });

  it("a non-absolute base URL shows its message on the base URL field and issues no request — DoD-9", async () => {
    const user = newUser();
    const { mock } = serveServers([]);
    renderModal(new ServerFormDraft());
    await fillRegister(user, { name: "Loft rig", kind: "llamaswap", baseUrl: "loft.lan:8080" });
    const expected = serverFormClientErrors(registerDraft({ ...VALID_REGISTER, baseUrl: "loft.lan:8080" })).baseUrl as string;
    expect(fieldNotes(baseUrlInput())).toContain(expected);
    expect(fieldNotes(nameInput())).not.toContain(expected);
    expect(submitControl()).toBeDisabled();
    await user.click(submitControl());
    await flush();
    expect(mutations(mock)).toEqual([]);
  });

  it("an emptied base URL on an edit shows its message and issues no PATCH — DoD-9", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    await openEdit(user, ORCHARD.name);
    await user.clear(baseUrlInput());
    const expected = serverFormClientErrors(editDraft(ORCHARD, { baseUrl: "" })).baseUrl as string;
    expect(fieldNotes(baseUrlInput())).toContain(expected);
    await user.click(submitControl());
    await flush();
    expect(mutations(mock)).toEqual([]);
  });
});

// ===========================================================================
describe("server refusals land on the general key, above the form", () => {
  const FAILURES: Array<[string, FetchFn]> = [
    ["a 404 llm_server_not_found", () => Promise.resolve(envelopeResponse("llm_server_not_found", "That connection does not exist zq-404.", 404))],
    ["a 500 envelope", () => Promise.resolve(envelopeResponse("internal_error", FAILURE_MESSAGE, 500))],
    [
      "a 500 envelope whose prose names every field",
      () =>
        Promise.resolve(
          envelopeResponse("internal_error", "The name is wrong, the base URL is wrong and the API key pointer is wrong.", 500),
        ),
    ],
    [
      "FastAPI's own 422 naming the pointer",
      () =>
        Promise.resolve(
          jsonResponse({ detail: [{ type: "value_error", loc: ["body", "api_key_ref"], msg: "must start with $", input: "x" }] }, 422),
        ),
    ],
    [
      "FastAPI's own 422 naming the name",
      () =>
        Promise.resolve(jsonResponse({ detail: [{ type: "string_too_short", loc: ["body", "name"], msg: "too short", input: "" }] }, 422)),
    ],
    ["an unknown 409 code", () => Promise.resolve(envelopeResponse("mystery_conflict", "Name clash zq-409.", 409))],
    [
      "a 502 with a malformed body",
      () => Promise.resolve(new Response("<html>Bad Gateway</html>", { status: 502, headers: { "Content-Type": "text/html" } })),
    ],
    ["a transport failure", () => Promise.reject(new TypeError("Failed to fetch"))],
  ];

  it.each(FAILURES)("%s: an edit renders the general error above the form, on no field — DoD-10", async (_name, handler) => {
    vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(handler);
    const user = newUser();
    const draft = new ServerFormDraft(ORCHARD);
    const { onClose, onSaved } = renderModal(draft);
    await user.clear(nameInput());
    await user.type(nameInput(), "Orchard renamed");
    await submit(user);

    expect(presentKeys(draft.serverErrors)).toEqual(["general"]);
    const general = (draft.serverErrors.general as string).replace(/\s+/g, " ").trim();
    expect(general.length).toBeGreaterThan(0);
    expect(presentKeys(serverFormErrors(draft))).toContain("general");

    expect(textAbove(firstField())).toContain(general);
    for (const input of [nameInput(), baseUrlInput(), pointerInput()]) {
      expect(fieldNotes(input)).not.toContain(general);
    }
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(nameInput().value).toBe("Orchard renamed");
    expect(draft.submitStatus).not.toBe("done");
  });

  it.each(FAILURES)("%s: a register lands on the general key and never rejects — DoD-10", async (_name, handler) => {
    vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(handler);
    const draft = registerDraft({ ...VALID_REGISTER, pointer: "$LOFT_KEY", pointerTouched: true });
    const onSaved = vi.fn<() => void>();
    await expect(submitServerForm(draft, null, onSaved)).resolves.toBeUndefined();
    expect(presentKeys(draft.serverErrors)).toEqual(["general"]);
    expect(onSaved).not.toHaveBeenCalled();
    expect(draft.submitStatus).not.toBe("done");
  });

  it("a failure raises no notification — DoD-10", async () => {
    stubFetch(() => Promise.resolve(envelopeResponse("internal_error", FAILURE_MESSAGE, 500)));
    const user = newUser();
    renderModal(new ServerFormDraft());
    await fillRegister(user, { name: "Loft rig", kind: "llamaswap", baseUrl: "http://loft.lan:8080" });
    await submit(user);
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("the merged errors map carries client and server keys together — DoD-10, DoD-11", () => {
    const draft = registerDraft({ ...VALID_REGISTER, name: "", serverErrors: { general: FAILURE_MESSAGE } });
    const merged = serverFormErrors(draft);
    expect(merged.general).toBe(FAILURE_MESSAGE);
    expect(merged.name).toBe(serverFormClientErrors(draft).name);
  });
});

// ===========================================================================
describe("the draft is a data class; derivations are pure; the submit is a free function", () => {
  it("the class prototype carries no method and no getter — DoD-11 (D16)", () => {
    expect(Object.getOwnPropertyNames(ServerFormDraft.prototype)).toEqual(["constructor"]);
  });

  it("every own field is observable, none computed, none a function — DoD-11", () => {
    for (const draft of [new ServerFormDraft(), new ServerFormDraft(ORCHARD)]) {
      const names = Object.getOwnPropertyNames(draft);
      expect([...names].sort()).toEqual(
        ["baseUrl", "kind", "name", "original", "pointer", "pointerTouched", "serverErrors", "submitStatus"].sort(),
      );
      const record = draft as unknown as Record<string, unknown>;
      for (const name of names) {
        expect(isObservableProp(draft, name), name).toBe(true);
        expect(isComputedProp(draft, name), name).toBe(false);
        expect(typeof record[name], name).not.toBe("function");
      }
    }
  });

  it("a register draft starts empty, untouched, error-free and idle — DoD-11, DoD-1", () => {
    const draft = new ServerFormDraft();
    expect(draft.original).toBeNull();
    expect(draft.name).toBe("");
    expect(draft.baseUrl).toBe("");
    expect(draft.pointer).toBe("");
    expect(draft.pointerTouched).toBe(false);
    expect(toJS(draft.serverErrors)).toEqual({});
    expect(draft.submitStatus).toBe("idle");
  });

  it("an edit draft copies the row but starts the pointer empty and untouched even when the row records one — DoD-11, DoD-4", () => {
    const draft = new ServerFormDraft(ORCHARD);
    expect(draft.name).toBe(ORCHARD.name);
    expect(draft.kind).toBe(ORCHARD.kind);
    expect(draft.baseUrl).toBe(ORCHARD.base_url);
    expect(draft.pointer).toBe("");
    expect(draft.pointerTouched).toBe(false);
    expect(toJS(draft.original)).toEqual(ORCHARD);
  });

  it("the derivations need no render and no network, and are pure — DoD-11", () => {
    const mock = stubFetch(() => Promise.reject(new Error("no network expected")));
    for (const draft of [new ServerFormDraft(), registerDraft(VALID_REGISTER), editDraft(ORCHARD, { pointer: "$", pointerTouched: true })]) {
      const before = draftSnapshot(draft);
      const first = [serverFormClientErrors(draft), serverFormErrors(draft), canSubmitServerForm(draft)];
      const second = [serverFormClientErrors(draft), serverFormErrors(draft), canSubmitServerForm(draft)];
      expect(second).toEqual(first);
      expect(draftSnapshot(draft)).toEqual(before);
    }
    expect(mock).not.toHaveBeenCalled();
    expect(document.body.querySelector("[role='dialog']")).toBeNull();
  });

  it("cannot submit while submitting, even when the fields are valid — DoD-11", () => {
    expect(canSubmitServerForm(registerDraft(VALID_REGISTER))).toBe(true);
    expect(canSubmitServerForm(registerDraft({ ...VALID_REGISTER, submitStatus: "submitting" }))).toBe(false);
  });

  it("the submit writes only inside actions (strict MobX raises no warning) — DoD-11", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    configure({ enforceActions: "always" });
    try {
      const run = async (draft: ServerFormDraft, serverId: string | null) => {
        const dispose = autorun(() => {
          void draft.name;
          void draft.kind;
          void draft.baseUrl;
          void draft.pointer;
          void draft.pointerTouched;
          void draft.submitStatus;
          void JSON.stringify(toJS(draft.serverErrors));
        });
        await submitServerForm(draft, serverId, () => {});
        dispose();
      };
      serveServers(EVERYONE);
      await run(registerDraft(VALID_REGISTER), null);
      await run(editDraft(ORCHARD, { pointer: "", pointerTouched: true }), ORCHARD.id);
      vi.unstubAllGlobals();
      stubFetch(() => Promise.resolve(envelopeResponse("internal_error", FAILURE_MESSAGE, 500)));
      await run(editDraft(ORCHARD, { name: "Orchard renamed" }), ORCHARD.id);
      vi.unstubAllGlobals();
      stubFetch(() => Promise.reject(new TypeError("Failed to fetch")));
      await run(registerDraft(VALID_REGISTER), null);
    } finally {
      configure({ enforceActions: "observed" });
    }
    const mobxWarnings = warn.mock.calls.filter((args) => args.some((arg) => String(arg).includes("[MobX]")));
    expect(mobxWarnings).toEqual([]);
  });

  it.each<[string, () => ServerFormDraft, string | null]>([
    ["a register", () => registerDraft(VALID_REGISTER), null],
    ["an edit", () => editDraft(ORCHARD, { name: "Orchard renamed" }), ORCHARD.id],
  ])("%s given an already-aborted signal writes nothing and saves nothing — DoD-11", async (_name, make, serverId) => {
    serveServers(EVERYONE);
    const draft = make();
    const before = draftSnapshot(draft);
    const controller = new AbortController();
    controller.abort();
    const onSaved = vi.fn<() => void>();
    await expect(submitServerForm(draft, serverId, onSaved, controller.signal)).resolves.toBeUndefined();
    await settle();
    expect(draftSnapshot(draft)).toEqual(before);
    expect(onSaved).not.toHaveBeenCalled();
  });

  it.each<[string, () => Response]>([
    ["a success", () => jsonResponse({ ...ORCHARD, name: "Orchard renamed" }, 200)],
    ["a failure", () => envelopeResponse("internal_error", FAILURE_MESSAGE, 500)],
  ])("%s arriving after the abort is not written — DoD-11", async (_name, answer) => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const draft = editDraft(ORCHARD, { name: "Orchard renamed" });
    const controller = new AbortController();
    const onSaved = vi.fn<() => void>();
    const running = submitServerForm(draft, ORCHARD.id, onSaved, controller.signal);
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

  it("the draft module uses runInAction and makeAutoObservable, and neither module uses @mantine/form — DoD-11", () => {
    const draftSource = readSource(DRAFT_SOURCE);
    expect(draftSource).toMatch(/\brunInAction\b/);
    expect(draftSource).toMatch(/\bmakeAutoObservable\b/);
    for (const file of [DRAFT_SOURCE, MODAL_SOURCE]) {
      const specs = importSpecifiers(readFileSync(file, "utf8"));
      expect(specs.filter((spec) => spec.startsWith("@mantine/form")), path.basename(file)).toEqual([]);
    }
  });
});

// ===========================================================================
describe("a fresh draft per open", () => {
  it("opening, typing, closing without saving and reopening shows empty fields — DoD-12", async () => {
    const user = newUser();
    const { mock } = await renderLoaded();
    await openRegister(user);
    await user.type(nameInput(), "leftover-zq");
    await user.type(baseUrlInput(), "http://leftover.lan");
    await user.type(pointerInput(), "$LEFTOVER_ZQ");
    await closeModal(user);

    await openRegister(user);
    expect(nameInput().value).toBe("");
    expect(baseUrlInput().value).toBe("");
    expect(pointerInput().value).toBe("");
    expect(dialog().textContent ?? "").not.toContain("leftover-zq");
    expect(mutations(mock)).toEqual([]);
  });

  it("each open hands the modal a different draft, and the discarded one is not reset — DoD-12", async () => {
    const user = newUser();
    await renderLoaded();
    await openRegister(user);
    await user.type(nameInput(), "leftover-zq");
    await closeModal(user);
    await openRegister(user);

    const drafts = modalDrafts();
    expect(drafts).toHaveLength(2);
    expect(drafts[0]).toBeInstanceOf(ServerFormDraft);
    expect(drafts[1]).toBeInstanceOf(ServerFormDraft);
    expect(drafts[1]).not.toBe(drafts[0]);
    expect(drafts[0].name).toBe("leftover-zq");
    expect(drafts[1].name).toBe("");
  });

  it("reopening Edit after an abandoned edit shows the row's values and an empty, untouched pointer — DoD-12", async () => {
    const user = newUser();
    await renderLoaded();
    await openEdit(user, ORCHARD.name);
    await user.clear(nameInput());
    await user.type(nameInput(), "abandoned-zq");
    await user.type(pointerInput(), "$ABANDONED_ZQ");
    await closeModal(user);

    await openEdit(user, ORCHARD.name);
    expect(nameInput().value).toBe(ORCHARD.name);
    expect(pointerInput().value).toBe("");
    const drafts = modalDrafts();
    expect(drafts.length).toBeGreaterThanOrEqual(2);
    const latest = drafts[drafts.length - 1];
    expect(latest).not.toBe(drafts[0]);
    expect(latest.pointerTouched).toBe(false);
  });

  it("a server error from the previous open does not survive a close and reopen — DoD-12", async () => {
    const user = newUser();
    await renderLoaded(EVERYONE, {
      override: (method) => (method === "PATCH" ? Promise.resolve(envelopeResponse("internal_error", FAILURE_MESSAGE, 500)) : undefined),
    });
    await openEdit(user, ORCHARD.name);
    await user.clear(nameInput());
    await user.type(nameInput(), "Orchard renamed");
    await submit(user);
    const general = modalDrafts()[0].serverErrors.general as string;
    expect(typeof general).toBe("string");
    expect(dialog().textContent ?? "").toContain(general.trim());

    await closeModal(user);
    await openEdit(user, ORCHARD.name);
    expect(dialog().textContent ?? "").not.toContain(general.trim());
  });

  it("the modal is mounted only while open and the draft module offers no reset — DoD-12", async () => {
    const user = newUser();
    await renderLoaded();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(modalDrafts()).toEqual([]);
    await openRegister(user);
    await closeModal(user);
    expect(screen.queryByRole("dialog")).toBeNull();

    const exported = Object.keys(draftModule);
    expect(exported.filter((name) => /reset|clear|reuse/i.test(name))).toEqual([]);
    expect(readSource(PAGE_SOURCE)).toMatch(/new\s+ServerFormDraft\s*\(/);
  });
});

// ===========================================================================
describe("the open flag and target row are component-local", () => {
  it("opening and closing the register modal leaves the page store unchanged — DoD-13", async () => {
    const user = newUser();
    const { state } = await renderLoaded();
    const before = pageStoreSnapshot(state);
    expect(before.names.filter((name) => isObservableProp(state, name))).toEqual([
      "errorMessage",
      "rows",
      "status",
      "testingId",
    ]);

    await openRegister(user);
    expect(pageStoreSnapshot(state)).toEqual(before);
    await closeModal(user);
    expect(pageStoreSnapshot(state)).toEqual(before);
  });

  it("opening and closing Edit for a row leaves the page store unchanged — DoD-13", async () => {
    const user = newUser();
    const { state } = await renderLoaded();
    const before = pageStoreSnapshot(state);
    await openEdit(user, ORCHARD.name);
    expect(pageStoreSnapshot(state)).toEqual(before);
    await closeModal(user);
    expect(pageStoreSnapshot(state)).toEqual(before);
  });

  it("the draft carries no open flag — DoD-13", () => {
    const names = Object.getOwnPropertyNames(new ServerFormDraft(ORCHARD));
    expect(names.filter((name) => /open|visible|shown|modal/i.test(name))).toEqual([]);
  });
});

// ===========================================================================
describe("success closes the modal and re-loads; never optimistic, no toast", () => {
  it("a successful edit closes the modal and re-loads through the page's store — DoD-14", async () => {
    const user = newUser();
    const { mock, state } = await renderLoaded();
    const loadsBefore = spied.load.length;
    await openEdit(user, ORCHARD.name);
    await user.clear(nameInput());
    await user.type(nameInput(), "Orchard renamed");
    await submit(user);
    await waitForNoDialog();

    const calls = seen(mock);
    const patchIndex = calls.findIndex((call) => call.method === "PATCH");
    expect(patchIndex).toBeGreaterThanOrEqual(0);
    expect(calls.slice(patchIndex + 1).filter((call) => call.method === "GET" && call.path === LIST_PATH).length).toBeGreaterThan(0);
    expect(spied.load.length).toBeGreaterThan(loadsBefore);
    expect(spied.load[spied.load.length - 1][0]).toBe(state);
    rowFor("Orchard renamed");
  });

  it("the table reflects the re-load, not a local write — a change only the server knows appears too — DoD-14", async () => {
    const user = newUser();
    const { rows } = await renderLoaded();
    rows.push({ ...ATTIC, id: "7340032000000299", name: "Server-only zq" });
    await openRegister(user);
    await fillRegister(user, { name: "Loft rig", kind: "llamaswap", baseUrl: "http://loft.lan:8080" });
    await submit(user);
    await waitForNoDialog();
    rowFor("Server-only zq");
    rowFor("Loft rig");
  });

  it("nothing is written into the store while the request is in flight — DoD-14", async () => {
    const user = newUser();
    const pending = deferred<Response>();
    const { state } = await renderLoaded(EVERYONE, {
      override: (method) => (method === "PATCH" || method === "POST" ? pending.promise : undefined),
    });
    const before = pageStoreSnapshot(state);
    await openEdit(user, ORCHARD.name);
    await user.clear(nameInput());
    await user.type(nameInput(), "Orchard renamed");
    await submit(user);

    expect(pageStoreSnapshot(state)).toEqual(before);
    expect(bodyRows()).toHaveLength(2);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    pending.resolve(envelopeResponse("internal_error", FAILURE_MESSAGE, 500));
    await flush();
    expect(pageStoreSnapshot(state)).toEqual(before);
  });

  it("no success notification and no success message — DoD-14", async () => {
    const user = newUser();
    await renderLoaded();
    await openRegister(user);
    await fillRegister(user, { name: "Loft rig", kind: "llamaswap", baseUrl: "http://loft.lan:8080" });
    await submit(user);
    await waitForNoDialog();
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(document.body.textContent ?? "").not.toMatch(/\bsuccess(ful|fully)?\b/i);
  });

  it("the standalone modal calls onSaved exactly once on success — DoD-14", async () => {
    serveServers(EVERYONE);
    const user = newUser();
    const { onSaved } = renderModal(new ServerFormDraft(ORCHARD));
    await user.clear(nameInput());
    await user.type(nameInput(), "Orchard renamed");
    await submit(user);
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(notificationRoots()).toEqual([]);
  });

  it("no module of this step imports notifyFailure or Mantine's notifications — DoD-14", () => {
    const offenders = STEP_MODULES.flatMap((file) =>
      importSpecifiers(readFileSync(file, "utf8"))
        .filter((spec) => /notifyFailure|@mantine\/notifications/.test(spec))
        .map((spec) => `${path.basename(file)} imports ${spec}`),
    );
    expect(offenders).toEqual([]);
  });
});

// ===========================================================================
describe("the pointer control is masked and explains itself", () => {
  it("is a PasswordInput: a masked input inside Mantine's PasswordInput — DoD-15", () => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    renderModal(new ServerFormDraft());
    const input = pointerInput();
    expect(input.type).toBe("password");
    expect(input.closest(".mantine-PasswordInput-root")).not.toBeNull();
    expect(readSource(MODAL_SOURCE)).toMatch(/<PasswordInput\b/);
  });

  it("its description asks for a $-prefixed pointer and says it is not a key — DoD-15", () => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    renderModal(new ServerFormDraft());
    const notes = fieldNotes(pointerInput());
    expect(notes).toMatch(/\$[A-Z][A-Z0-9_]*/);
    expect(notes).toMatch(/\bkey\b/i);
    expect(notes).toMatch(/\b(not|never|rather than|instead of)\b/i);
  });

  it("in edit mode its description says untouched keeps the stored pointer and clearing removes it — DoD-15, DoD-4", () => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    renderModal(new ServerFormDraft(ORCHARD));
    const notes = fieldNotes(pointerInput());
    expect(notes).toMatch(/\$[A-Z][A-Z0-9_]*/);
    expect(notes).toMatch(/keep|kept|retain|preserv|unchanged/i);
    expect(notes).toMatch(/clear/i);
  });
});

// ===========================================================================
describe("no active switch and no active field", () => {
  it.each<[string, () => ServerFormDraft]>([
    ["register", () => new ServerFormDraft()],
    ["edit", () => new ServerFormDraft(ORCHARD)],
  ])("the %s modal renders no switch, no checkbox and nothing labelled active — DoD-16 (D1)", (_mode, make) => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    renderModal(make());
    const box = dialog();
    expect(within(box).queryAllByRole("switch")).toEqual([]);
    expect(within(box).queryAllByRole("checkbox")).toEqual([]);
    expect(box.querySelectorAll("input[type='checkbox'], input[type='radio']")).toHaveLength(0);
    expect(within(box).queryAllByLabelText(/\bactive\b|\benabled\b/i)).toEqual([]);
    expect(box.textContent ?? "").not.toMatch(/\bactive\b/i);
  });

  it("neither the draft nor the modal source declares an active field or a switch — DoD-16", () => {
    const names = Object.getOwnPropertyNames(new ServerFormDraft(ORCHARD));
    expect(names.filter((name) => /active/i.test(name))).toEqual([]);
    for (const file of [DRAFT_SOURCE, MODAL_SOURCE]) {
      const source = readSource(file);
      expect(source, path.basename(file)).not.toMatch(/\b(is_?)?active\b|\bisActive\b/i);
    }
    expect(readSource(MODAL_SOURCE)).not.toMatch(/<(Switch|Checkbox)\b/);
  });
});

// ===========================================================================
describe("ids are strings; no stylesheet", () => {
  it("an edit of a row with an id beyond MAX_SAFE_INTEGER PATCHes that id verbatim — DoD-17", async () => {
    const user = newUser();
    const big: LlmServerRow = { ...ORCHARD, id: BIG_ID };
    const { mock, state } = await renderLoaded([ATTIC, big]);
    await openEdit(user, big.name);
    await user.clear(nameInput());
    await user.type(nameInput(), "Orchard renamed");
    await submit(user);
    await waitForNoDialog();
    expect(mutations(mock).map((call) => `${call.method} ${call.path}`)).toEqual([`PATCH ${LIST_PATH}/${BIG_ID}`]);
    const row = storeRow(state, BIG_ID);
    expect(typeof row.id).toBe("string");
    expect(row.name).toBe("Orchard renamed");
  });

  it("the submit function uses the string id it is given and the draft keeps the row's id a string — DoD-17", async () => {
    const big: LlmServerRow = { ...ORCHARD, id: BIG_ID };
    const { mock } = serveServers([big]);
    const draft = editDraft(big, { name: "Orchard renamed" });
    expect(typeof draft.original?.id).toBe("string");
    expect(draft.original?.id).toBe(BIG_ID);
    await submitServerForm(draft, BIG_ID, () => {});
    expect(mutations(mock)[0].path).toBe(`${LIST_PATH}/${BIG_ID}`);
  });

  it("this step's modules type no id as a number and call no parseInt — DoD-17", () => {
    for (const file of STEP_MODULES) {
      const source = readSource(file);
      expect(source, path.basename(file)).not.toMatch(/\bparseInt\b|\bparseFloat\b|\bBigInt\s*\(/);
      expect(source, path.basename(file)).not.toMatch(/\b\w*(?:id|Id|ID)\s*\??\s*:\s*number\b/);
    }
  });

  it("the modal and draft import no stylesheet and the modal uses no className or style element — DoD-17", () => {
    for (const file of [DRAFT_SOURCE, MODAL_SOURCE]) {
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
