// Feature 005, step 008 — the Set Password modal and its wiring into the Users page's row menu
// (DoD-2, DoD-3, DoD-4, DoD-8, DoD-9, DoD-11, DoD-12, DoD-13 at the component and page level).
// The draft's derivations and submit mapping are exercised directly in setPasswordDraft.test.ts;
// the Change Role modal is in ChangeRoleModal.test.tsx. DoD-14..DoD-16 are [manual/live].
//
// Expected behaviour comes from the step's Interface intent and Definition of done,
// 008.context.md and context.md (D1 the UI hides nothing, D6 no current password / no policy /
// no email / no forced change, D16 MobX, no success toasts, never optimistic). Per the frozen
// interface the modal takes `{ target, onClose, onSaved }` and is mounted only while open, so a
// standalone render shows it open. `fetch` is stubbed per test with a small in-memory backend.
// `notifyFailure` is mocked at file level. The draft module and the page-store module are wrapped
// pass-through so the draft/target the modal submits and the store the page loads into are
// observable — behaviour is unchanged.
//
// Recognition conventions (from spec wording, for the verifier; they follow steps 006/007):
// - The modal: `role="dialog"`. Fields by visible label: confirmation /confirm|repeat/i; new
//   password /password/i excluding the confirmation.
// - The submit control: the one dialog button named /set|save|submit|update|reset|change|apply/i
//   and not /cancel|close/i.
// - "Above the form": the text precedes the new-password input in document order in the dialog.
// - Row menu entries: `role="menuitem"` — Set Password /password/i, Change Role /\brole\b/i,
//   Disable /\bdisable\b/i, Re-enable /\bre-?\s?enable\b/i. The row's one icon-only control is a
//   button/link with empty text content. Notifications: `.mantine-Notification-root`.
// - Close: a dialog button named /cancel|close/i if present, else Escape.
import { readFileSync } from "node:fs";
import path from "node:path";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { isObservableProp } from "mobx";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SetPasswordModal } from "../../src/admin/SetPasswordModal";
import { SetPasswordDraft } from "../../src/admin/setPasswordDraft";
import { UsersPage } from "../../src/admin/UsersPage";
import { type AdminUserRow, UsersPageState } from "../../src/admin/usersPageState";
import { AppProviders } from "../../src/shared/AppProviders";

const { notifyFailureSpy, spied } = vi.hoisted(() => ({
  notifyFailureSpy: vi.fn(),
  spied: { submit: [] as unknown[][], load: [] as unknown[][] },
}));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));
vi.mock("../../src/admin/setPasswordDraft", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../src/admin/setPasswordDraft")>();
  return {
    ...actual,
    submitSetPassword: (...args: Parameters<typeof actual.submitSetPassword>) => {
      spied.submit.push(args);
      return actual.submitSetPassword(...args);
    },
  };
});
vi.mock("../../src/admin/usersPageState", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../src/admin/usersPageState")>();
  return {
    ...actual,
    loadUsers: (...args: Parameters<typeof actual.loadUsers>) => {
      spied.load.push(args);
      return actual.loadUsers(...args);
    },
  };
});

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type User = ReturnType<typeof userEvent.setup>;
type Seen = { method: string; path: string; search: string; body: unknown };

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const STEP_MODULES = [
  path.join(FRONTEND_ROOT, "src", "admin", "SetPasswordModal.tsx"),
  path.join(FRONTEND_ROOT, "src", "admin", "setPasswordDraft.ts"),
];

const LIST_PATH = "/api/admin/users";
const ACTION_PATH = /^\/api\/admin\/users\/([^/]+)\/(disable|enable|password|role)$/;
const BIG_ID = "9007199254740993"; // 2^53 + 1
const NEW_PASSWORD = "Tq!9-new-horse";
const FAILURE_MESSAGE = "Reset exploded zq-500.";

const CONFIRMATION_LABEL = /confirm|repeat/i;
const PASSWORD_LABEL = /password/i;
const CURRENT_PASSWORD_LABEL = /current|old|existing|previous/i;
const SUBMIT_NAME = /set|save|submit|update|reset|change|apply/i;
const NOT_SUBMIT_NAME = /cancel|close/i;
const SET_PASSWORD_ITEM = /password/i;
const CHANGE_ROLE_ITEM = /\brole\b/i;
const DISABLE_ITEM = /\bdisable\b/i;
const REENABLE_ITEM = /\bre-?\s?enable\b/i;
const NOTIFICATION_ROOT = ".mantine-Notification-root";
/** DoD-2 — affordances that do not exist in this product (admin-surfaces.md, data-model.md). */
const ABSENT_AFFORDANCES =
  /current\s*password|old\s*password|e-?mail|reset\s*link|send\s*(a\s*)?link|generat|random|suggest|next\s*(sign|log)[\s-]*in|must\s*change|force/i;
const SUCCESS_TEXT = /\bsuccess(fully)?\b|\bhas\s+been\b|\bwas\s+(set|changed|updated|reset)\b/i;

const MIREILLE: AdminUserRow = {
  id: "7340032000000101",
  username: "mireille",
  role: "roleplayer",
  is_enabled: true,
  last_login_at: null,
};
const ZORA: AdminUserRow = {
  id: "7340032000000102",
  username: "zora",
  role: "roleplayer",
  is_enabled: false,
  last_login_at: null,
};
/** An administrator — the row that could be the caller's own. */
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
  spied.submit.length = 0;
  spied.load.length = 0;
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

type Override = (method: string, path: string, body: unknown) => Promise<Response> | undefined;

/**
 * A tiny in-memory backend for step 003's routes: GET the list; POST {id}/disable|enable|
 * password|role answer 200 with the affected row (404 user_not_found for an unknown id).
 */
function serveUsers(initial: AdminUserRow[], options: { override?: Override } = {}) {
  const rows: AdminUserRow[] = initial.map((row) => ({ ...row }));
  const mock = stubFetch((input, init) => {
    const method = requestMethod(input, init);
    const pathname = requestUrl(input).pathname;
    const body = requestBody(init);
    const custom = options.override?.(method, pathname, body);
    if (custom !== undefined) return custom;
    if (method === "GET" && pathname === LIST_PATH) {
      return Promise.resolve(jsonResponse({ users: rows.map((row) => ({ ...row })) }, 200));
    }
    const match = ACTION_PATH.exec(pathname);
    if (method === "POST" && match !== null) {
      const row = rows.find((candidate) => candidate.id === match[1]);
      if (row === undefined) {
        return Promise.resolve(envelopeResponse("user_not_found", "That account does not exist.", 404));
      }
      if (match[2] === "disable") row.is_enabled = false;
      if (match[2] === "enable") row.is_enabled = true;
      if (match[2] === "role") row.role = (body as { role: AdminUserRow["role"] }).role;
      return Promise.resolve(jsonResponse({ ...row }, 200));
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

function newUser(): User {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

// ---------------------------------------------------------------- render

function renderModal(target: AdminUserRow = MIREILLE) {
  const onClose = vi.fn<() => void>();
  const onSaved = vi.fn<(updated: AdminUserRow) => void>();
  const view = render(
    <AppProviders>
      <SetPasswordModal target={target} onClose={onClose} onSaved={onSaved} />
    </AppProviders>,
  );
  return { onClose, onSaved, view };
}

function renderPage() {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={["/"]}>
        <UsersPage />
      </MemoryRouter>
    </AppProviders>,
  );
}

async function renderLoadedPage(rows: AdminUserRow[] = EVERYONE, options: { override?: Override } = {}) {
  const server = serveUsers(rows, options);
  const view = renderPage();
  await flush();
  return { ...server, view };
}

// ---------------------------------------------------------------- queries

function dialog(): HTMLElement {
  return screen.getByRole("dialog");
}

function inputsLabelled(label: RegExp): HTMLInputElement[] {
  return within(dialog())
    .queryAllByLabelText(label)
    .filter((el): el is HTMLInputElement => el instanceof HTMLInputElement);
}

function confirmationInput(): HTMLInputElement {
  const found = inputsLabelled(CONFIRMATION_LABEL);
  expect(found, "confirmation inputs").toHaveLength(1);
  return found[0];
}

function newPasswordInput(): HTMLInputElement {
  const confirmation = confirmationInput();
  const found = inputsLabelled(PASSWORD_LABEL).filter((el) => el !== confirmation);
  expect(found, "new-password inputs").toHaveLength(1);
  return found[0];
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

/** Text plus naming attributes inside an element — everything a person could read or hear. */
function readableText(root: Element): string {
  const attributes = ["aria-label", "title", "aria-description", "placeholder", "alt", "aria-valuetext"];
  const values = Array.from(root.querySelectorAll("*")).flatMap((el) =>
    attributes.map((name) => el.getAttribute(name) ?? "").filter(Boolean),
  );
  return [root.textContent ?? "", ...values].join("\n");
}

function notificationRoots(): Element[] {
  return Array.from(document.querySelectorAll(NOTIFICATION_ROOT));
}

function submittedCall(): { draft: SetPasswordDraft; targetId: unknown } {
  expect(spied.submit.length, "submitSetPassword calls").toBeGreaterThan(0);
  const args = spied.submit[spied.submit.length - 1];
  expect(args[0]).toBeInstanceOf(SetPasswordDraft);
  return { draft: args[0] as SetPasswordDraft, targetId: args[1] };
}

function pageStore(): UsersPageState {
  expect(spied.load.length, "loadUsers calls from the page").toBeGreaterThan(0);
  const store = spied.load[0][0];
  expect(store).toBeInstanceOf(UsersPageState);
  return store as UsersPageState;
}

function bodyRows(): HTMLTableRowElement[] {
  const found = document.querySelector("table");
  if (found === null) throw new Error("no <table> rendered");
  return Array.from(found.querySelectorAll<HTMLTableRowElement>("tbody tr"));
}

function rowFor(username: string): HTMLTableRowElement {
  const matches = bodyRows().filter((tr) =>
    Array.from(tr.querySelectorAll("td")).some((td) => (td.textContent ?? "").trim() === username),
  );
  expect(matches, `rows showing ${username}`).toHaveLength(1);
  return matches[0];
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
 * above the clicked icon-only control — and still inside that row — that carries `aria-controls`
 * or `aria-haspopup`, else an `id`. The wiring may sit on the control itself or on a wrapper
 * around it (mirrors step 006's `wiredTarget`).
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
 * that trigger: the element the wired target's `aria-controls` names, or the element whose
 * `aria-labelledby` contains the wired target's id. Never any other menu on the page — a
 * still-mounted, closing dropdown from another row is never accepted. Throws until the right
 * dropdown exists, so it is meant to be polled inside `waitFor` (mirrors step 006's tests).
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

/** Opens `username`'s row menu and returns that dropdown (scoped, see `dropdownFor`). */
async function openRowDropdown(user: User, username: string): Promise<HTMLElement> {
  await user.click(menuTrigger(username));
  return waitFor(() => dropdownFor(username));
}

/** Opens `username`'s row menu and returns the entries of that row's dropdown only. */
async function openRowMenu(user: User, username: string): Promise<HTMLElement[]> {
  const menu = await openRowDropdown(user, username);
  return within(menu).findAllByRole("menuitem");
}

async function openSetPassword(user: User, username: string): Promise<HTMLElement> {
  const menu = await openRowDropdown(user, username);
  await user.click(await within(menu).findByRole("menuitem", { name: SET_PASSWORD_ITEM }));
  return screen.findByRole("dialog");
}

async function fill(user: User, password: string, confirmation: string = password): Promise<void> {
  await user.type(newPasswordInput(), password);
  await user.type(confirmationInput(), confirmation);
}

async function closeModal(user: User): Promise<void> {
  const named = within(dialog())
    .queryAllByRole("button")
    .filter((el) => NOT_SUBMIT_NAME.test(el.getAttribute("aria-label") ?? el.textContent ?? ""));
  if (named.length > 0) {
    await user.click(named[0]);
  } else {
    newPasswordInput().focus();
    await user.keyboard("{Escape}");
  }
  await waitForNoDialog();
}

async function waitForNoDialog(): Promise<void> {
  await waitFor(() => {
    expect(screen.queryByRole("dialog")).toBeNull();
  });
}

function rowsSnapshot(): string[] {
  return bodyRows().map((tr) => (tr.textContent ?? "").replace(/\s+/g, " ").trim());
}

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

function importSpecifiers(source: string): string[] {
  const pattern = /(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)["']([^"']+)["']/g;
  return Array.from(stripComments(source).matchAll(pattern), (m) => m[1]);
}

// ---------------------------------------------------------------------------
describe("the modal offers only what this product has", () => {
  it("renders as a dialog with a new-password field and a confirmation field — DoD-2", () => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    renderModal();
    expect(dialog()).toBeInTheDocument();
    expect(newPasswordInput()).toBeInTheDocument();
    expect(confirmationInput()).toBeInTheDocument();
  });

  it("has no current-password field: exactly two inputs, neither labelled current/old — DoD-2 (D6)", () => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    renderModal();
    expect(inputsLabelled(CURRENT_PASSWORD_LABEL)).toEqual([]);
    expect(dialog().querySelectorAll("input")).toHaveLength(2);
    expect(dialog().querySelectorAll("textarea, select")).toHaveLength(0);
  });

  it("has no force-change switch or checkbox — DoD-2", () => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    renderModal();
    expect(within(dialog()).queryAllByRole("switch")).toEqual([]);
    expect(within(dialog()).queryAllByRole("checkbox")).toEqual([]);
    expect(dialog().querySelectorAll("input[type='checkbox'], input[type='radio']")).toHaveLength(0);
  });

  it("names no current password, generated password, email, reset link or forced change — DoD-2", () => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    renderModal();
    expect(readableText(dialog())).not.toMatch(ABSENT_AFFORDANCES);
  });

  it("the fields start empty — nothing is pre-generated — DoD-2", () => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    renderModal();
    expect(newPasswordInput().value).toBe("");
    expect(confirmationInput().value).toBe("");
  });

  it("still offers none of them after a failed submit — DoD-2", async () => {
    stubFetch(() => Promise.resolve(envelopeResponse("internal_error", FAILURE_MESSAGE, 500)));
    const user = newUser();
    renderModal();
    await fill(user, NEW_PASSWORD);
    await user.click(submitControl());
    await flush();
    expect(readableText(dialog())).not.toMatch(ABSENT_AFFORDANCES);
    expect(dialog().querySelectorAll("input")).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
describe("a successful submit from the modal", () => {
  it("posts the new password to that account's password route, and nothing else — DoD-3 (US-010.AC-2)", async () => {
    const { mock } = serveUsers([MIREILLE]);
    const user = newUser();
    renderModal(MIREILLE);
    await fill(user, NEW_PASSWORD);
    await user.click(submitControl());
    await flush();
    expect(seen(mock)).toEqual([
      { method: "POST", path: `${LIST_PATH}/${MIREILLE.id}/password`, search: "", body: { password: NEW_PASSWORD } },
    ]);
  });

  it("the target id is passed as the row's string, and reaches the path unchanged — DoD-3", async () => {
    const big = { ...MIREILLE, id: BIG_ID };
    const { mock } = serveUsers([big]);
    const user = newUser();
    renderModal(big);
    await fill(user, NEW_PASSWORD);
    await user.click(submitControl());
    await flush();
    const { targetId } = submittedCall();
    expect(targetId).toBe(BIG_ID);
    expect(typeof targetId).toBe("string");
    expect(seen(mock).map((call) => call.path)).toEqual([`${LIST_PATH}/${BIG_ID}/password`]);
  });

  it("invokes the saved callback exactly once, with the affected account — DoD-3 (US-010.AC-2)", async () => {
    serveUsers([MIREILLE]);
    const user = newUser();
    const { onSaved } = renderModal(MIREILLE);
    await fill(user, NEW_PASSWORD);
    await user.click(submitControl());
    await flush();
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onSaved.mock.calls[0][0]).toEqual(MIREILLE);
  });

  it("the submit is disabled until the new password is filled and confirmed — DoD-3, DoD-1", async () => {
    stubFetch(() => Promise.resolve(jsonResponse(MIREILLE, 200)));
    const user = newUser();
    renderModal();
    expect(submitControl()).toBeDisabled();
    await user.type(newPasswordInput(), NEW_PASSWORD);
    expect(submitControl()).toBeDisabled();
    await user.type(confirmationInput(), `${NEW_PASSWORD}!`);
    expect(submitControl()).toBeDisabled();
    await user.clear(confirmationInput());
    await user.type(confirmationInput(), NEW_PASSWORD);
    expect(submitControl()).toBeEnabled();
  });

  it("raises no notification and shows no success message — DoD-3, DoD-13", async () => {
    serveUsers([MIREILLE]);
    const user = newUser();
    renderModal(MIREILLE);
    await fill(user, NEW_PASSWORD);
    await user.click(submitControl());
    await flush();
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(document.body.textContent ?? "").not.toMatch(SUCCESS_TEXT);
  });
});

// ---------------------------------------------------------------------------
describe("a failed submit from the modal", () => {
  const FAILURES: Array<[string, FetchFn]> = [
    ["a 500 envelope", () => Promise.resolve(envelopeResponse("internal_error", FAILURE_MESSAGE, 500))],
    ["a 404 user_not_found", () => Promise.resolve(envelopeResponse("user_not_found", "That account does not exist.", 404))],
    ["a 400 envelope whose prose talks about the password", () => Promise.resolve(envelopeResponse("bad_request", "Password too weak zq-400.", 400))],
    [
      "FastAPI's own 422 body",
      () =>
        Promise.resolve(
          jsonResponse({ detail: [{ type: "string_too_short", loc: ["body", "password"], msg: "too short", input: "" }] }, 422),
        ),
    ],
    ["a transport failure", () => Promise.reject(new TypeError("Failed to fetch"))],
  ];

  it.each(FAILURES)("%s renders the general message above the form and keeps the modal open — DoD-4, DoD-13", async (_name, handler) => {
    stubFetch(handler);
    const user = newUser();
    const { onClose, onSaved } = renderModal();
    await fill(user, NEW_PASSWORD);
    await user.click(submitControl());
    await flush();

    const { draft } = submittedCall();
    const general = draft.serverErrors.general;
    expect(typeof general).toBe("string");
    expect(general).not.toBe("");
    expect(Object.keys(draft.serverErrors)).toEqual(["general"]);
    expect(textAbove(newPasswordInput())).toContain((general as string).replace(/\s+/g, " ").trim());

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
    expect(newPasswordInput().value).toBe(NEW_PASSWORD);
    expect(confirmationInput().value).toBe(NEW_PASSWORD);
  });

  it("a failure raises no notification — DoD-4, DoD-13", async () => {
    stubFetch(() => Promise.resolve(envelopeResponse("internal_error", FAILURE_MESSAGE, 500)));
    const user = newUser();
    renderModal();
    await fill(user, NEW_PASSWORD);
    await user.click(submitControl());
    await flush();
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("Set Password on the Users page", () => {
  it("choosing Set Password opens the modal and issues no request — DoD-3", async () => {
    const user = newUser();
    const { mock } = await renderLoadedPage();
    const before = mock.mock.calls.length;
    await openSetPassword(user, "mireille");
    expect(newPasswordInput()).toBeInTheDocument();
    await flush();
    expect(mock.mock.calls.length).toBe(before);
  });

  it("a successful submit posts to that row's password route with its string id — DoD-3 (US-010.AC-2)", async () => {
    const user = newUser();
    const { mock } = await renderLoadedPage();
    await openSetPassword(user, "zora");
    await fill(user, NEW_PASSWORD);
    await user.click(submitControl());
    await flush();
    const posts = seen(mock).filter((call) => call.method === "POST");
    expect(posts).toEqual([
      { method: "POST", path: `${LIST_PATH}/${ZORA.id}/password`, search: "", body: { password: NEW_PASSWORD } },
    ]);
    expect(submittedCall().targetId).toBe(ZORA.id);
  });

  it("a successful submit closes the modal — DoD-3", async () => {
    const user = newUser();
    await renderLoadedPage();
    await openSetPassword(user, "mireille");
    await fill(user, NEW_PASSWORD);
    await user.click(submitControl());
    await flush();
    await waitForNoDialog();
  });

  it("a successful submit re-loads the list through the page's load function and store — DoD-3", async () => {
    const user = newUser();
    const { mock } = await renderLoadedPage();
    const store = pageStore();
    const loadsBefore = spied.load.length;
    await openSetPassword(user, "mireille");
    await fill(user, NEW_PASSWORD);
    await user.click(submitControl());
    await flush();

    const calls = seen(mock);
    const postIndex = calls.findIndex((call) => call.method === "POST");
    expect(postIndex).toBeGreaterThanOrEqual(0);
    const laterLists = calls.slice(postIndex + 1).filter((call) => call.method === "GET" && call.path === LIST_PATH);
    expect(laterLists.length).toBeGreaterThan(0);
    expect(spied.load.length).toBeGreaterThan(loadsBefore);
    expect(spied.load[spied.load.length - 1][0]).toBe(store);
  });

  it("the re-load is real — a change only the server knows appears after the save — DoD-3", async () => {
    const user = newUser();
    const { rows } = await renderLoadedPage();
    rows.push({ id: "7340032000000999", username: "server-only-zq", role: "roleplayer", is_enabled: true, last_login_at: null });
    await openSetPassword(user, "mireille");
    await fill(user, NEW_PASSWORD);
    await user.click(submitControl());
    await flush();
    await waitForNoDialog();
    rowFor("server-only-zq");
  });

  it("a successful submit raises no success notification and shows no success message — DoD-3, DoD-13", async () => {
    const user = newUser();
    await renderLoadedPage();
    await openSetPassword(user, "mireille");
    await fill(user, NEW_PASSWORD);
    await user.click(submitControl());
    await flush();
    await waitForNoDialog();
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(document.body.textContent ?? "").not.toMatch(SUCCESS_TEXT);
  });

  it("a failed submit keeps the modal open, shows the message above the form, and does not clear the list — DoD-4", async () => {
    const user = newUser();
    await renderLoadedPage(EVERYONE, {
      override: (method, pathname) =>
        method === "POST" && pathname.endsWith("/password")
          ? Promise.resolve(envelopeResponse("internal_error", FAILURE_MESSAGE, 500))
          : undefined,
    });
    const store = pageStore();
    const rowsBefore = rowsSnapshot();
    const storeRowsBefore = JSON.stringify(store.rows);

    await openSetPassword(user, "mireille");
    await fill(user, NEW_PASSWORD);
    await user.click(submitControl());
    await flush();

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    const general = submittedCall().draft.serverErrors.general;
    expect(typeof general).toBe("string");
    expect(textAbove(newPasswordInput())).toContain((general as string).replace(/\s+/g, " ").trim());
    expect(bodyRows()).toHaveLength(3);
    expect(rowsSnapshot()).toEqual(rowsBefore);
    expect(JSON.stringify(store.rows)).toBe(storeRowsBefore);
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("nothing in the list changes while the submit is in flight — DoD-4", async () => {
    const user = newUser();
    const pending = deferred<Response>();
    await renderLoadedPage(EVERYONE, {
      override: (method, pathname) => (method === "POST" && pathname.endsWith("/password") ? pending.promise : undefined),
    });
    const rowsBefore = rowsSnapshot();
    await openSetPassword(user, "mireille");
    await fill(user, NEW_PASSWORD);
    await user.click(submitControl());
    await flush();
    expect(rowsSnapshot()).toEqual(rowsBefore);
    pending.resolve(envelopeResponse("internal_error", FAILURE_MESSAGE, 500));
    await flush();
  });
});

// ---------------------------------------------------------------------------
describe("both actions on every row", () => {
  it.each(EVERYONE.map((row) => row.username))(
    "%s's menu offers Set Password and Change Role, neither disabled — DoD-8 (D1)",
    async (username) => {
      const user = newUser();
      await renderLoadedPage();
      const menu = await openRowDropdown(user, username);
      for (const name of [SET_PASSWORD_ITEM, CHANGE_ROLE_ITEM]) {
        const item = await within(menu).findByRole("menuitem", { name });
        expect(item).not.toHaveAttribute("data-disabled");
        expect(item.getAttribute("aria-disabled")).not.toBe("true");
        expect(item).not.toBeDisabled();
      }
    },
  );

  it("Set Password opens on an administrator's row — the one that could be the caller's own — DoD-8 (D1)", async () => {
    const user = newUser();
    const { mock } = await renderLoadedPage();
    await openSetPassword(user, "anselm");
    await fill(user, NEW_PASSWORD);
    await user.click(submitControl());
    await flush();
    const posts = seen(mock).filter((call) => call.method === "POST");
    expect(posts.map((call) => call.path)).toEqual([`${LIST_PATH}/${ANSELM.id}/password`]);
  });
});

// ---------------------------------------------------------------------------
describe("the row menu after this step", () => {
  it.each<[string, string, RegExp, RegExp]>([
    ["an enabled", MIREILLE.username, DISABLE_ITEM, REENABLE_ITEM],
    ["an enabled administrator", ANSELM.username, DISABLE_ITEM, REENABLE_ITEM],
    ["a disabled", ZORA.username, REENABLE_ITEM, DISABLE_ITEM],
  ])(
    "%s account's menu holds exactly Set Password, Change Role and one of Disable / Re-enable — DoD-12",
    async (_kind, username, present, absent) => {
      const user = newUser();
      await renderLoadedPage();
      const items = await openRowMenu(user, username);
      expect(items).toHaveLength(3);
      const texts = items.map((item) => (item.textContent ?? "").trim());
      for (const text of texts) expect(text.length, "menu entry text").toBeGreaterThan(0);
      expect(texts.filter((text) => SET_PASSWORD_ITEM.test(text))).toHaveLength(1);
      expect(texts.filter((text) => CHANGE_ROLE_ITEM.test(text))).toHaveLength(1);
      expect(texts.filter((text) => present.test(text))).toHaveLength(1);
      expect(texts.filter((text) => absent.test(text))).toHaveLength(0);
    },
  );

  it("each row still contains exactly one icon-only control — DoD-12", async () => {
    await renderLoadedPage();
    for (const account of EVERYONE) {
      expect(iconOnlyControls(rowFor(account.username)), account.username).toHaveLength(1);
    }
  });

  it("the icon-only control is the menu's single trigger — DoD-12", async () => {
    const user = newUser();
    await renderLoadedPage();
    const items = await openRowMenu(user, "mireille");
    expect(items.length).toBeGreaterThan(0);
    for (const account of EVERYONE) {
      expect(iconOnlyControls(rowFor(account.username)), account.username).toHaveLength(1);
    }
  });
});

// ---------------------------------------------------------------------------
describe("the modal is conditionally mounted", () => {
  it("closing and reopening shows empty fields — DoD-9", async () => {
    const user = newUser();
    await renderLoadedPage();
    await openSetPassword(user, "mireille");
    await fill(user, "leftover-zq", "leftover-other");
    await closeModal(user);

    await openSetPassword(user, "mireille");
    expect(newPasswordInput().value).toBe("");
    expect(confirmationInput().value).toBe("");
    expect(submitControl()).toBeDisabled();
  });

  it("a server error from the previous open does not survive a close and reopen — DoD-9", async () => {
    const user = newUser();
    await renderLoadedPage(EVERYONE, {
      override: (method, pathname) =>
        method === "POST" && pathname.endsWith("/password")
          ? Promise.resolve(envelopeResponse("internal_error", FAILURE_MESSAGE, 500))
          : undefined,
    });
    await openSetPassword(user, "mireille");
    await fill(user, NEW_PASSWORD);
    await user.click(submitControl());
    await flush();
    const general = submittedCall().draft.serverErrors.general as string;
    expect(dialog().textContent ?? "").toContain(general.trim());

    await closeModal(user);
    await openSetPassword(user, "mireille");
    expect(dialog().textContent ?? "").not.toContain(general.trim());
  });

  it("each open submits a different draft instance — DoD-9", async () => {
    const user = newUser();
    await renderLoadedPage();
    await openSetPassword(user, "mireille");
    await fill(user, NEW_PASSWORD);
    await user.click(submitControl());
    await flush();
    await waitForNoDialog();
    const first = submittedCall().draft;

    await openSetPassword(user, "mireille");
    await fill(user, "second-pw");
    await user.click(submitControl());
    await flush();
    const second = submittedCall().draft;
    expect(second).not.toBe(first);
  });

  it("the target is the row the menu was opened on, each time — DoD-9", async () => {
    const user = newUser();
    const { mock } = await renderLoadedPage();
    await openSetPassword(user, "mireille");
    await fill(user, NEW_PASSWORD);
    await user.click(submitControl());
    await flush();
    await waitForNoDialog();
    await openSetPassword(user, "zora");
    await fill(user, NEW_PASSWORD);
    await user.click(submitControl());
    await flush();
    const posts = seen(mock).filter((call) => call.method === "POST");
    expect(posts.map((call) => call.path)).toEqual([
      `${LIST_PATH}/${MIREILLE.id}/password`,
      `${LIST_PATH}/${ZORA.id}/password`,
    ]);
  });
});

// ---------------------------------------------------------------------------
describe("the open flag and target row are component-local", () => {
  it("opening and closing Set Password adds no field to the page store and changes none — DoD-11", async () => {
    const user = newUser();
    await renderLoadedPage();
    const store = pageStore();
    const fieldsBefore = Object.getOwnPropertyNames(store).sort();
    expect(fieldsBefore.filter((name) => isObservableProp(store, name))).toEqual(["errorMessage", "rows", "status"]);
    const rowsBefore = JSON.stringify(store.rows);

    await openSetPassword(user, "mireille");
    expect(Object.getOwnPropertyNames(store).sort()).toEqual(fieldsBefore);
    expect(JSON.stringify(store.rows)).toBe(rowsBefore);
    expect(store.status).toBe("ready");
    expect(store.errorMessage).toBeNull();

    await closeModal(user);
    expect(Object.getOwnPropertyNames(store).sort()).toEqual(fieldsBefore);
  });

  it("no store field holds the target row — DoD-11", async () => {
    const user = newUser();
    await renderLoadedPage();
    const store = pageStore();
    await openSetPassword(user, "zora");
    for (const name of Object.getOwnPropertyNames(store)) {
      const value = (store as unknown as Record<string, unknown>)[name];
      if (name === "rows") continue;
      expect(JSON.stringify(value) ?? "", name).not.toContain(ZORA.id);
    }
  });

  it("the modal takes no open prop — mounting it shows it — DoD-11", () => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    renderModal();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
describe("no prose mapping, no notification", () => {
  it("this step's set-password modules import neither notifyFailure nor Mantine's notifications — DoD-13", () => {
    const offenders = STEP_MODULES.flatMap((file) =>
      importSpecifiers(readFileSync(file, "utf8"))
        .filter((spec) => /notifyFailure|@mantine\/notifications/.test(spec))
        .map((spec) => `${path.basename(file)} imports ${spec}`),
    );
    expect(offenders).toEqual([]);
  });

  it("this step's set-password modules never inspect an error's message text — DoD-13", () => {
    const proseChecks = [
      /\.message\b\s*\??\.\s*(?:includes|match|matchAll|startsWith|endsWith|indexOf|search|toLowerCase|toUpperCase|localeCompare)\b/,
      /\.message\b\s*(?:===|!==|==|!=)/,
      /(?:===|!==|==|!=)\s*[\w.?]*\.message\b/,
      /\.(?:test|exec)\(\s*[\w.?]*\.message\b/,
    ];
    for (const file of STEP_MODULES) {
      const source = stripComments(readFileSync(file, "utf8"));
      for (const pattern of proseChecks) {
        expect(source, `${path.basename(file)} ${pattern}`).not.toMatch(pattern);
      }
    }
  });

  it("this step's set-password modules use no parseInt and type no id as a number — DoD-3", () => {
    for (const file of STEP_MODULES) {
      const source = stripComments(readFileSync(file, "utf8"));
      expect(source, path.basename(file)).not.toMatch(/\bparseInt\b|\bparseFloat\b|\bBigInt\s*\(/);
      expect(source, path.basename(file)).not.toMatch(/\b\w*(?:id|Id)\s*\??\s*:\s*number\b/);
    }
  });
});
