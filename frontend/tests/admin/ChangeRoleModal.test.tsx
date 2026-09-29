// Feature 005, step 008 — the Change Role modal and its wiring into the Users page's row menu
// (DoD-5, DoD-6, DoD-7, DoD-8, DoD-9, DoD-11, DoD-13 at the component and page level). The
// draft's derivations and submit mapping are exercised directly in changeRoleDraft.test.ts; the
// Set Password modal and the full row-menu composition (DoD-12) are in SetPasswordModal.test.tsx.
// DoD-14..DoD-16 are [manual/live].
//
// Expected behaviour comes from the step's Interface intent and Definition of done,
// 008.context.md and context.md (D1 the self-target refusal is the server's and the UI hides
// nothing, D16 MobX, no success toasts, never optimistic). Per the frozen interface the modal
// takes `{ target, onClose, onSaved }` and is mounted only while open. `fetch` is stubbed per
// test with a small in-memory backend that refuses a role change on the "caller's own" account
// with 409 self_role_change_refused, as step 003's route does. `notifyFailure` is mocked at file
// level. The draft module and the page-store module are wrapped pass-through so the draft/target
// the modal submits and the store the page loads into are observable — behaviour is unchanged.
//
// Recognition conventions (from spec wording, for the verifier; they follow steps 006/007):
// - The modal: `role="dialog"`. The role field: the input labelled /\brole\b/i (Mantine
//   `Select`); its options are `role="option"` in the opened dropdown; its shown value names the
//   role — /role\s*-?player/i or /admin/i.
// - The submit control: the one dialog button named /save|change|submit|update|apply|set|confirm/i
//   and not /cancel|close/i.
// - "Above the form": the text precedes the role input in document order within the dialog.
// - The 409 message: matches /\bown\s+role\b/i and a refusal word
//   (/cannot|can't|can not|not allowed|may not|not permitted|unable/i).
// - Row menu entry: `role="menuitem"` named /\brole\b/i. Role badge: the row's text.
// - Close: a dialog button named /cancel|close/i if present, else Escape.
import { readFileSync } from "node:fs";
import path from "node:path";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { isObservableProp } from "mobx";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChangeRoleModal } from "../../src/admin/ChangeRoleModal";
import { ChangeRoleDraft } from "../../src/admin/changeRoleDraft";
import { UsersPage } from "../../src/admin/UsersPage";
import { type AdminUserRole, type AdminUserRow, UsersPageState } from "../../src/admin/usersPageState";
import { AppProviders } from "../../src/shared/AppProviders";

const { notifyFailureSpy, spied } = vi.hoisted(() => ({
  notifyFailureSpy: vi.fn(),
  spied: { submit: [] as unknown[][], load: [] as unknown[][] },
}));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));
vi.mock("../../src/admin/changeRoleDraft", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../src/admin/changeRoleDraft")>();
  return {
    ...actual,
    submitChangeRole: (...args: Parameters<typeof actual.submitChangeRole>) => {
      spied.submit.push(args);
      return actual.submitChangeRole(...args);
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
  path.join(FRONTEND_ROOT, "src", "admin", "ChangeRoleModal.tsx"),
  path.join(FRONTEND_ROOT, "src", "admin", "changeRoleDraft.ts"),
];

const LIST_PATH = "/api/admin/users";
const ACTION_PATH = /^\/api\/admin\/users\/([^/]+)\/(disable|enable|password|role)$/;
const BIG_ID = "9007199254740993"; // 2^53 + 1
const FAILURE_MESSAGE = "Role change exploded zq-500.";

const ROLE_LABEL = /\brole\b/i;
const SUBMIT_NAME = /save|change|submit|update|apply|set|confirm/i;
const NOT_SUBMIT_NAME = /cancel|close/i;
const CHANGE_ROLE_ITEM = /\brole\b/i;
const ADMIN_ROLE = /admin/i;
const ROLEPLAYER_ROLE = /role\s*-?player/i;
const OWN_ROLE = /\bown\s+role\b/i;
const CANNOT = /cannot|can't|can not|not allowed|may not|not permitted|unable/i;
const NOTIFICATION_ROOT = ".mantine-Notification-root";
const SUCCESS_TEXT = /\bsuccess(fully)?\b|\bhas\s+been\b|\bwas\s+(set|changed|updated)\b/i;

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
/** The administrator the in-memory backend treats as the caller: its role route answers 409. */
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
 * A tiny in-memory backend for step 003's routes. The role route writes the new role and answers
 * 200 with the row, except for `callerId`, where it refuses with 409 self_role_change_refused and
 * writes nothing; unknown ids answer 404 user_not_found.
 */
function serveUsers(initial: AdminUserRow[], options: { callerId?: string; override?: Override } = {}) {
  const rows: AdminUserRow[] = initial.map((row) => ({ ...row }));
  const callerId = options.callerId ?? ANSELM.id;
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
      if (match[2] === "role") {
        if (row.id === callerId) {
          return Promise.resolve(envelopeResponse("self_role_change_refused", "You cannot change your own role.", 409));
        }
        row.role = (body as { role: AdminUserRole }).role;
      }
      if (match[2] === "disable") row.is_enabled = false;
      if (match[2] === "enable") row.is_enabled = true;
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
      <ChangeRoleModal target={target} onClose={onClose} onSaved={onSaved} />
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

async function renderLoadedPage(rows: AdminUserRow[] = EVERYONE, options: { callerId?: string; override?: Override } = {}) {
  const server = serveUsers(rows, options);
  const view = renderPage();
  await flush();
  return { ...server, view };
}

// ---------------------------------------------------------------- queries

function dialog(): HTMLElement {
  return screen.getByRole("dialog");
}

function roleInput(): HTMLInputElement {
  const found = within(dialog())
    .queryAllByLabelText(ROLE_LABEL)
    .filter((el): el is HTMLInputElement => el instanceof HTMLInputElement);
  expect(found, "role inputs").toHaveLength(1);
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

function submittedCall(): { draft: ChangeRoleDraft; targetId: unknown } {
  expect(spied.submit.length, "submitChangeRole calls").toBeGreaterThan(0);
  const args = spied.submit[spied.submit.length - 1];
  expect(args[0]).toBeInstanceOf(ChangeRoleDraft);
  return { draft: args[0] as ChangeRoleDraft, targetId: args[1] };
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

function rowText(username: string): string {
  return rowFor(username).textContent ?? "";
}

function rowsSnapshot(): string[] {
  return bodyRows().map((tr) => (tr.textContent ?? "").replace(/\s+/g, " ").trim());
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

async function openChangeRole(user: User, username: string): Promise<HTMLElement> {
  await user.click(menuTrigger(username));
  const menu = await waitFor(() => dropdownFor(username));
  await user.click(await within(menu).findByRole("menuitem", { name: CHANGE_ROLE_ITEM }));
  return screen.findByRole("dialog");
}

async function openRoleOptions(user: User): Promise<HTMLElement[]> {
  await user.click(roleInput());
  return screen.findAllByRole("option");
}

async function chooseRole(user: User, role: AdminUserRole): Promise<void> {
  const options = await openRoleOptions(user);
  const wanted = options.find((option) => {
    const text = option.textContent ?? "";
    return role === "admin"
      ? ADMIN_ROLE.test(text) && !ROLEPLAYER_ROLE.test(text)
      : ROLEPLAYER_ROLE.test(text) && !ADMIN_ROLE.test(text);
  });
  expect(wanted, `option for ${role}`).toBeDefined();
  await user.click(wanted as HTMLElement);
  await flush(2);
}

function expectShownRole(role: AdminUserRole): void {
  const value = roleInput().value;
  if (role === "admin") {
    expect(value).toMatch(ADMIN_ROLE);
    expect(value).not.toMatch(ROLEPLAYER_ROLE);
  } else {
    expect(value).toMatch(ROLEPLAYER_ROLE);
    expect(value).not.toMatch(ADMIN_ROLE);
  }
}

async function closeModal(user: User): Promise<void> {
  const named = within(dialog())
    .queryAllByRole("button")
    .filter((el) => NOT_SUBMIT_NAME.test(el.getAttribute("aria-label") ?? el.textContent ?? ""));
  if (named.length > 0) {
    await user.click(named[0]);
  } else {
    roleInput().focus();
    await user.keyboard("{Escape}");
    if (screen.queryByRole("dialog") !== null) {
      // The first Escape may only close the Select's dropdown.
      await user.keyboard("{Escape}");
    }
  }
  await waitForNoDialog();
}

async function waitForNoDialog(): Promise<void> {
  await waitFor(() => {
    expect(screen.queryByRole("dialog")).toBeNull();
  });
}

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

function importSpecifiers(source: string): string[] {
  const pattern = /(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)["']([^"']+)["']/g;
  return Array.from(stripComments(source).matchAll(pattern), (m) => m[1]);
}

// ---------------------------------------------------------------------------
describe("the modal pre-selects the account's current role", () => {
  it.each<[AdminUserRole, AdminUserRow]>([
    ["roleplayer", MIREILLE],
    ["admin", ANSELM],
  ])("a %s account's modal shows that role selected — DoD-5", (role, target) => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    renderModal(target);
    expect(dialog()).toBeInTheDocument();
    expectShownRole(role);
  });

  it("the modal's draft is built from the target's role — DoD-5", async () => {
    stubFetch(() => Promise.resolve(jsonResponse(ANSELM, 200)));
    const user = newUser();
    renderModal(ANSELM);
    await user.click(submitControl());
    await flush();
    expect(submittedCall().draft.role).toBe("admin");
  });

  it("the submit is available straight away, because a role is already selected — DoD-5", () => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    renderModal(MIREILLE);
    expect(submitControl()).toBeEnabled();
  });

  it("the Select offers exactly the ladder's two values — DoD-5, DoD-6", async () => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    const user = newUser();
    renderModal();
    const options = await openRoleOptions(user);
    expect(options).toHaveLength(2);
    const texts = options.map((option) => option.textContent ?? "");
    expect(texts.filter((text) => ROLEPLAYER_ROLE.test(text) && !ADMIN_ROLE.test(text))).toHaveLength(1);
    expect(texts.filter((text) => ADMIN_ROLE.test(text) && !ROLEPLAYER_ROLE.test(text))).toHaveLength(1);
  });

  it("an administrator's own-looking row is submittable client-side — no self-target check in the UI — DoD-5 (D1)", async () => {
    const { mock } = serveUsers(EVERYONE);
    const user = newUser();
    renderModal(ANSELM);
    await chooseRole(user, "roleplayer");
    expect(submitControl()).toBeEnabled();
    await user.click(submitControl());
    await flush();
    const posts = seen(mock).filter((call) => call.method === "POST");
    expect(posts).toEqual([{ method: "POST", path: `${LIST_PATH}/${ANSELM.id}/role`, search: "", body: { role: "roleplayer" } }]);
  });
});

// ---------------------------------------------------------------------------
describe("a successful submit from the modal", () => {
  it("posts the selected role to that account's role route, and nothing else — DoD-6", async () => {
    const { mock } = serveUsers(EVERYONE);
    const user = newUser();
    renderModal(MIREILLE);
    await chooseRole(user, "admin");
    expectShownRole("admin");
    await user.click(submitControl());
    await flush();
    expect(seen(mock)).toEqual([
      { method: "POST", path: `${LIST_PATH}/${MIREILLE.id}/role`, search: "", body: { role: "admin" } },
    ]);
  });

  it("the target id is passed as the row's string, and reaches the path unchanged — DoD-6", async () => {
    const big = { ...MIREILLE, id: BIG_ID };
    const { mock } = serveUsers([big]);
    const user = newUser();
    renderModal(big);
    await chooseRole(user, "admin");
    await user.click(submitControl());
    await flush();
    const { targetId } = submittedCall();
    expect(targetId).toBe(BIG_ID);
    expect(typeof targetId).toBe("string");
    expect(seen(mock).map((call) => call.path)).toEqual([`${LIST_PATH}/${BIG_ID}/role`]);
  });

  it("invokes the saved callback exactly once, with the affected account — DoD-6", async () => {
    serveUsers(EVERYONE);
    const user = newUser();
    const { onSaved } = renderModal(MIREILLE);
    await chooseRole(user, "admin");
    await user.click(submitControl());
    await flush();
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onSaved.mock.calls[0][0]).toEqual({ ...MIREILLE, role: "admin" });
  });

  it("raises no notification — DoD-6, DoD-13", async () => {
    serveUsers(EVERYONE);
    const user = newUser();
    renderModal(MIREILLE);
    await chooseRole(user, "admin");
    await user.click(submitControl());
    await flush();
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("a 409 from the role route", () => {
  it("renders the 'cannot change their own role' message above the form — DoD-7", async () => {
    serveUsers(EVERYONE);
    const user = newUser();
    renderModal(ANSELM);
    await chooseRole(user, "roleplayer");
    await user.click(submitControl());
    await flush();
    const above = textAbove(roleInput());
    expect(above).toMatch(OWN_ROLE);
    expect(above).toMatch(CANNOT);
    const { draft } = submittedCall();
    expect(Object.keys(draft.serverErrors)).toEqual(["general"]);
  });

  it("keeps the modal open, calls neither callback and keeps the selection — DoD-7", async () => {
    serveUsers(EVERYONE);
    const user = newUser();
    const { onClose, onSaved } = renderModal(ANSELM);
    await chooseRole(user, "roleplayer");
    await user.click(submitControl());
    await flush();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
    expectShownRole("roleplayer");
  });

  it("is mapped by status: a 409 with unrelated prose still renders the own-role message — DoD-7, DoD-13", async () => {
    stubFetch(() => Promise.resolve(envelopeResponse("self_role_change_refused", "Kettle zq-409 overflowed.", 409)));
    const user = newUser();
    renderModal(ANSELM);
    await chooseRole(user, "roleplayer");
    await user.click(submitControl());
    await flush();
    const above = textAbove(roleInput());
    expect(above).toMatch(OWN_ROLE);
    expect(above).toMatch(CANNOT);
  });

  it("raises no notification — DoD-7, DoD-13", async () => {
    serveUsers(EVERYONE);
    const user = newUser();
    renderModal(ANSELM);
    await chooseRole(user, "roleplayer");
    await user.click(submitControl());
    await flush();
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("any other failure from the modal", () => {
  const FAILURES: Array<[string, FetchFn]> = [
    ["a 500 envelope", () => Promise.resolve(envelopeResponse("internal_error", FAILURE_MESSAGE, 500))],
    ["a 404 user_not_found", () => Promise.resolve(envelopeResponse("user_not_found", "That account does not exist.", 404))],
    ["a transport failure", () => Promise.reject(new TypeError("Failed to fetch"))],
  ];

  it.each(FAILURES)("%s renders the general message above the form and keeps the modal open — DoD-7, DoD-13", async (_name, handler) => {
    stubFetch(handler);
    const user = newUser();
    const { onClose, onSaved } = renderModal(MIREILLE);
    await chooseRole(user, "admin");
    await user.click(submitControl());
    await flush();
    const { draft } = submittedCall();
    const general = draft.serverErrors.general;
    expect(typeof general).toBe("string");
    expect(general).not.toBe("");
    expect(Object.keys(draft.serverErrors)).toEqual(["general"]);
    expect(textAbove(roleInput())).toContain((general as string).replace(/\s+/g, " ").trim());
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("Change Role on the Users page", () => {
  it("choosing Change Role opens the modal on that row's current role and issues no request — DoD-5", async () => {
    const user = newUser();
    const { mock } = await renderLoadedPage();
    const before = mock.mock.calls.length;
    await openChangeRole(user, "anselm");
    expectShownRole("admin");
    await flush();
    expect(mock.mock.calls.length).toBe(before);
  });

  it("a successful submit posts the selected role to that row's role route — DoD-6", async () => {
    const user = newUser();
    const { mock } = await renderLoadedPage();
    await openChangeRole(user, "mireille");
    await chooseRole(user, "admin");
    await user.click(submitControl());
    await flush();
    const posts = seen(mock).filter((call) => call.method === "POST");
    expect(posts).toEqual([{ method: "POST", path: `${LIST_PATH}/${MIREILLE.id}/role`, search: "", body: { role: "admin" } }]);
    expect(submittedCall().targetId).toBe(MIREILLE.id);
  });

  it("a successful submit closes the modal — DoD-6", async () => {
    const user = newUser();
    await renderLoadedPage();
    await openChangeRole(user, "mireille");
    await chooseRole(user, "admin");
    await user.click(submitControl());
    await flush();
    await waitForNoDialog();
  });

  it("a successful submit re-loads the list through the page's load function and store — DoD-6", async () => {
    const user = newUser();
    const { mock } = await renderLoadedPage();
    const store = pageStore();
    const loadsBefore = spied.load.length;
    await openChangeRole(user, "mireille");
    await chooseRole(user, "admin");
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

  it("after the re-load the row's role badge shows the new role — DoD-6", async () => {
    const user = newUser();
    await renderLoadedPage();
    expect(rowText("mireille")).toMatch(ROLEPLAYER_ROLE);
    expect(rowText("mireille")).not.toMatch(ADMIN_ROLE);

    await openChangeRole(user, "mireille");
    await chooseRole(user, "admin");
    await user.click(submitControl());
    await flush();
    await waitForNoDialog();

    expect(rowText("mireille")).toMatch(ADMIN_ROLE);
    expect(rowText("mireille")).not.toMatch(ROLEPLAYER_ROLE);
    expect(rowText("zora")).toMatch(ROLEPLAYER_ROLE);
  });

  it("the badge comes from the re-load, not a local write — nothing changes while the post is in flight — DoD-6", async () => {
    const user = newUser();
    const pending = deferred<Response>();
    await renderLoadedPage(EVERYONE, {
      override: (method, pathname) => (method === "POST" && pathname.endsWith("/role") ? pending.promise : undefined),
    });
    await openChangeRole(user, "mireille");
    await chooseRole(user, "admin");
    await user.click(submitControl());
    await flush();
    expect(rowText("mireille")).toMatch(ROLEPLAYER_ROLE);
    expect(rowText("mireille")).not.toMatch(ADMIN_ROLE);
    pending.resolve(envelopeResponse("internal_error", FAILURE_MESSAGE, 500));
    await flush();
  });

  it("a successful submit raises no success notification and shows no success message — DoD-6, DoD-13", async () => {
    const user = newUser();
    await renderLoadedPage();
    await openChangeRole(user, "mireille");
    await chooseRole(user, "admin");
    await user.click(submitControl());
    await flush();
    await waitForNoDialog();
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(document.body.textContent ?? "").not.toMatch(SUCCESS_TEXT);
  });

  it("a 409 on the caller's own row renders the own-role message, keeps the modal open and changes nothing in the list — DoD-7", async () => {
    const user = newUser();
    const { rows } = await renderLoadedPage();
    const store = pageStore();
    const rowsBefore = rowsSnapshot();
    const storeRowsBefore = JSON.stringify(store.rows);

    await openChangeRole(user, "anselm");
    await chooseRole(user, "roleplayer");
    await user.click(submitControl());
    await flush();

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    const above = textAbove(roleInput());
    expect(above).toMatch(OWN_ROLE);
    expect(above).toMatch(CANNOT);
    expect(rowsSnapshot()).toEqual(rowsBefore);
    expect(rowText("anselm")).toMatch(ADMIN_ROLE);
    expect(JSON.stringify(store.rows)).toBe(storeRowsBefore);
    expect(rows.find((row) => row.id === ANSELM.id)?.role).toBe("admin");
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("offered on every row", () => {
  it.each(EVERYONE.map((row): [string, AdminUserRole] => [row.username, row.role]))(
    "Change Role opens on %s's row, pre-selected to its role — DoD-8 (D1)",
    async (username, role) => {
      const user = newUser();
      await renderLoadedPage();
      await openChangeRole(user, username);
      expectShownRole(role);
      expect(submitControl()).toBeEnabled();
    },
  );

  it("the administrator's row — one that could be the caller's own — reaches the server, which refuses — DoD-8 (D1)", async () => {
    const user = newUser();
    const { mock } = await renderLoadedPage();
    await openChangeRole(user, "anselm");
    await chooseRole(user, "roleplayer");
    await user.click(submitControl());
    await flush();
    const posts = seen(mock).filter((call) => call.method === "POST");
    expect(posts.map((call) => call.path)).toEqual([`${LIST_PATH}/${ANSELM.id}/role`]);
  });
});

// ---------------------------------------------------------------------------
describe("the modal is conditionally mounted", () => {
  it("closing and reopening re-initialises the role from the row — DoD-9", async () => {
    const user = newUser();
    await renderLoadedPage();
    await openChangeRole(user, "mireille");
    await chooseRole(user, "admin");
    expectShownRole("admin");
    await closeModal(user);

    await openChangeRole(user, "mireille");
    expectShownRole("roleplayer");
  });

  it("opening on another row initialises from that row — DoD-9", async () => {
    const user = newUser();
    await renderLoadedPage();
    await openChangeRole(user, "mireille");
    expectShownRole("roleplayer");
    await closeModal(user);
    await openChangeRole(user, "anselm");
    expectShownRole("admin");
  });

  it("a server error from the previous open does not survive a close and reopen — DoD-9", async () => {
    const user = newUser();
    await renderLoadedPage();
    await openChangeRole(user, "anselm");
    await chooseRole(user, "roleplayer");
    await user.click(submitControl());
    await flush();
    expect(dialog().textContent ?? "").toMatch(OWN_ROLE);

    await closeModal(user);
    await openChangeRole(user, "anselm");
    expect(dialog().textContent ?? "").not.toMatch(OWN_ROLE);
    expectShownRole("admin");
  });

  it("each open submits a different draft instance — DoD-9", async () => {
    const user = newUser();
    await renderLoadedPage();
    await openChangeRole(user, "mireille");
    await chooseRole(user, "admin");
    await user.click(submitControl());
    await flush();
    await waitForNoDialog();
    const first = submittedCall().draft;

    await openChangeRole(user, "zora");
    await chooseRole(user, "admin");
    await user.click(submitControl());
    await flush();
    const second = submittedCall().draft;
    expect(second).not.toBe(first);
  });
});

// ---------------------------------------------------------------------------
describe("the open flag and target row are component-local", () => {
  it("opening and closing Change Role adds no field to the page store and changes none — DoD-11", async () => {
    const user = newUser();
    await renderLoadedPage();
    const store = pageStore();
    const fieldsBefore = Object.getOwnPropertyNames(store).sort();
    expect(fieldsBefore.filter((name) => isObservableProp(store, name))).toEqual(["errorMessage", "rows", "status"]);
    const rowsBefore = JSON.stringify(store.rows);

    await openChangeRole(user, "mireille");
    expect(Object.getOwnPropertyNames(store).sort()).toEqual(fieldsBefore);
    expect(JSON.stringify(store.rows)).toBe(rowsBefore);
    expect(store.status).toBe("ready");
    expect(store.errorMessage).toBeNull();

    await closeModal(user);
    expect(Object.getOwnPropertyNames(store).sort()).toEqual(fieldsBefore);
  });

  it("the modal takes no open prop — mounting it shows it — DoD-11", () => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    renderModal();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
describe("no prose mapping, no notification", () => {
  it("this step's change-role modules import neither notifyFailure nor Mantine's notifications — DoD-13", () => {
    const offenders = STEP_MODULES.flatMap((file) =>
      importSpecifiers(readFileSync(file, "utf8"))
        .filter((spec) => /notifyFailure|@mantine\/notifications/.test(spec))
        .map((spec) => `${path.basename(file)} imports ${spec}`),
    );
    expect(offenders).toEqual([]);
  });

  it("this step's change-role modules never inspect an error's message text — DoD-13", () => {
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

  it("this step's change-role modules use no parseInt and type no id as a number — DoD-6", () => {
    for (const file of STEP_MODULES) {
      const source = stripComments(readFileSync(file, "utf8"));
      expect(source, path.basename(file)).not.toMatch(/\bparseInt\b|\bparseFloat\b|\bBigInt\s*\(/);
      expect(source, path.basename(file)).not.toMatch(/\b\w*(?:id|Id)\s*\??\s*:\s*number\b/);
    }
  });
});
