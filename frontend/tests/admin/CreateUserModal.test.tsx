// Feature 005, step 007 — the create-account modal and its wiring into the Users page
// (DoD-3, DoD-5..DoD-12 at the component and page level). The draft's pure derivations and the
// submit's mapping are also exercised directly in createUserDraft.test.ts. DoD-13..DoD-16 are
// [manual/live].
//
// Expected behaviour comes from the step's Interface intent and Definition of done,
// 007.context.md and context.md (D6, D10, D16, no success toasts, never optimistic). Per the
// frozen interface the modal takes only `onClose`/`onSaved` and is mounted only while open, so
// standalone renders show it open. `fetch` is stubbed per test with a small in-memory backend.
// `notifyFailure` is mocked at file level. The draft module and the page-store module are wrapped
// pass-through so the draft instance the modal submits and the store the page loads into are
// observable — behaviour is unchanged.
//
// Recognition conventions (from spec wording, for the verifier):
// - The modal: `role="dialog"`. Fields by visible label: username /user\s*name/i, confirmation
//   /confirm|repeat/i, password /password/i (excluding the confirmation), role /\brole\b/i (the
//   `<input>` of the Mantine `Select`); role options are `role="option"` in the opened dropdown.
// - The submit control: the one dialog button named /create|save|submit|add/i (not cancel/close).
// - A field error "renders on its field": its text is reachable through the input's
//   `aria-describedby`. "Above the form": the text precedes the username input in document order
//   within the dialog.
// - "Username taken": /taken|already|in use|exists|unavailable/i.
// - The page's Create button: the one button outside the dialog named /create/i.
// - Enabled status in a row: /\b(active|enabled)\b/i; notifications: `.mantine-Notification-root`.
import { readFileSync } from "node:fs";
import path from "node:path";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { isObservableProp } from "mobx";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CreateUserModal } from "../../src/admin/CreateUserModal";
import { CreateUserDraft } from "../../src/admin/createUserDraft";
import { UsersPage } from "../../src/admin/UsersPage";
import { type AdminUserRow, UsersPageState } from "../../src/admin/usersPageState";
import { documentNavigation } from "../../src/shared/api";
import { AppProviders } from "../../src/shared/AppProviders";

const { notifyFailureSpy, spied } = vi.hoisted(() => ({
  notifyFailureSpy: vi.fn(),
  spied: { submit: [] as unknown[][], load: [] as unknown[][] },
}));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));
vi.mock("../../src/admin/createUserDraft", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../src/admin/createUserDraft")>();
  return {
    ...actual,
    submitCreateUser: (...args: Parameters<typeof actual.submitCreateUser>) => {
      spied.submit.push(args);
      return actual.submitCreateUser(...args);
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
  path.join(FRONTEND_ROOT, "src", "admin", "CreateUserModal.tsx"),
  path.join(FRONTEND_ROOT, "src", "admin", "createUserDraft.ts"),
  path.join(FRONTEND_ROOT, "src", "admin", "UsersPage.tsx"),
];

const LIST_PATH = "/api/admin/users";
const BIG_ID = "9007199254740993"; // 2^53 + 1
const PASSWORD = "Tq!9-correct-horse";
const FAILURE_MESSAGE = "Creation exploded zq-500.";

const USERNAME_LABEL = /user\s*name/i;
const CONFIRMATION_LABEL = /confirm|repeat/i;
const PASSWORD_LABEL = /password/i;
const ROLE_LABEL = /\brole\b/i;
const SUBMIT_NAME = /create|save|submit|add/i;
const NOT_SUBMIT_NAME = /cancel|close/i;
const CREATE_BUTTON = /create/i;
const USERNAME_TAKEN = /taken|already|in use|exists|unavailable/i;
const ENABLED_STATUS = /\b(active|enabled)\b/i;
const DISABLED_STATUS = /\b(disabled|inactive)\b/i;
const ADMIN_ROLE = /admin/i;
const ROLEPLAYER_ROLE = /role\s*-?player/i;
const NOTIFICATION_ROOT = ".mantine-Notification-root";

const MIREILLE: AdminUserRow = {
  id: "7340032000000101",
  username: "mireille",
  role: "roleplayer",
  is_enabled: true,
  last_login_at: null,
};
const ANSELM: AdminUserRow = {
  id: "7340032000000103",
  username: "anselm",
  role: "admin",
  is_enabled: true,
  last_login_at: null,
};
const EVERYONE = [MIREILLE, ANSELM];

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
 * A tiny in-memory backend: GET /api/admin/users lists, POST /api/admin/users creates an
 * enabled account (409 username_taken on an exact duplicate), as step 003's routes do.
 */
function serveUsers(initial: AdminUserRow[], options: { nextId?: string; override?: Override } = {}) {
  const rows: AdminUserRow[] = initial.map((row) => ({ ...row }));
  let nextId = options.nextId ?? "7340032000000301";
  const mock = stubFetch((input, init) => {
    const method = requestMethod(input, init);
    const pathname = requestUrl(input).pathname;
    const body = requestBody(init);
    const custom = options.override?.(method, pathname, body);
    if (custom !== undefined) return custom;
    if (method === "GET" && pathname === LIST_PATH) {
      return Promise.resolve(jsonResponse({ users: rows.map((row) => ({ ...row })) }, 200));
    }
    if (method === "POST" && pathname === LIST_PATH) {
      const { username, role } = body as { username: string; password: string; role: "roleplayer" | "admin" };
      if (rows.some((row) => row.username === username)) {
        return Promise.resolve(envelopeResponse("username_taken", "That username is already taken.", 409));
      }
      const row: AdminUserRow = { id: nextId, username, role, is_enabled: true, last_login_at: null };
      nextId = `${nextId}9`;
      rows.push(row);
      return Promise.resolve(jsonResponse({ ...row }, 201));
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

function renderModal() {
  const onClose = vi.fn<() => void>();
  const onSaved = vi.fn<(created: AdminUserRow) => void>();
  const view = render(
    <AppProviders>
      <CreateUserModal onClose={onClose} onSaved={onSaved} />
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

async function renderLoadedPage(rows: AdminUserRow[] = EVERYONE, options: { nextId?: string; override?: Override } = {}) {
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

function usernameInput(): HTMLInputElement {
  const found = inputsLabelled(USERNAME_LABEL);
  expect(found, "username inputs").toHaveLength(1);
  return found[0];
}

function confirmationInput(): HTMLInputElement {
  const found = inputsLabelled(CONFIRMATION_LABEL);
  expect(found, "confirmation inputs").toHaveLength(1);
  return found[0];
}

function passwordInput(): HTMLInputElement {
  const confirmation = confirmationInput();
  const found = inputsLabelled(PASSWORD_LABEL).filter((el) => el !== confirmation);
  expect(found, "password inputs").toHaveLength(1);
  return found[0];
}

function roleInput(): HTMLInputElement {
  const found = inputsLabelled(ROLE_LABEL);
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

/** The text of every element an input's aria-describedby points at (where field errors attach). */
function describedText(input: HTMLElement): string {
  const ids = (input.getAttribute("aria-describedby") ?? "").split(/\s+/).filter(Boolean);
  return ids.map((id) => document.getElementById(id)?.textContent ?? "").join(" ");
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

function submittedDraft(): CreateUserDraft {
  expect(spied.submit.length, "submitCreateUser calls").toBeGreaterThan(0);
  const draft = spied.submit[spied.submit.length - 1][0];
  expect(draft).toBeInstanceOf(CreateUserDraft);
  return draft as CreateUserDraft;
}

function pageStore(): UsersPageState {
  expect(spied.load.length, "loadUsers calls from the page").toBeGreaterThan(0);
  const store = spied.load[0][0];
  expect(store).toBeInstanceOf(UsersPageState);
  return store as UsersPageState;
}

function createButton(): HTMLElement {
  const found = screen
    .queryAllByRole("button", { name: CREATE_BUTTON })
    .filter((el) => el.closest("[role='dialog']") === null);
  expect(found, "Create buttons outside the dialog").toHaveLength(1);
  return found[0];
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

function isBefore(first: Node, second: Node): boolean {
  return (first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

async function fill(user: User, fields: { username: string; password: string; confirmation?: string }) {
  await user.type(usernameInput(), fields.username);
  await user.type(passwordInput(), fields.password);
  await user.type(confirmationInput(), fields.confirmation ?? fields.password);
}

async function openRoleOptions(user: User): Promise<HTMLElement[]> {
  await user.click(roleInput());
  return screen.findAllByRole("option");
}

async function openModalOnPage(user: User): Promise<void> {
  await user.click(createButton());
  await screen.findByRole("dialog");
}

/** Close the modal the way an operator would: its cancel/close control if it has a named one, else Escape. */
async function closeModal(user: User): Promise<void> {
  const named = within(dialog())
    .queryAllByRole("button")
    .filter((el) => NOT_SUBMIT_NAME.test(el.getAttribute("aria-label") ?? el.textContent ?? ""));
  if (named.length > 0) {
    await user.click(named[0]);
  } else {
    usernameInput().focus();
    await user.keyboard("{Escape}");
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

// ---------------------------------------------------------------------------
describe("the modal's fields", () => {
  it("renders as a modal dialog with username, password, confirmation and role fields — DoD-8", () => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    renderModal();
    expect(dialog()).toBeInTheDocument();
    expect(usernameInput()).toBeInTheDocument();
    expect(passwordInput()).toBeInTheDocument();
    expect(confirmationInput()).toBeInTheDocument();
    expect(roleInput()).toBeInTheDocument();
  });

  it("the fields start empty — DoD-8", () => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    renderModal();
    expect(usernameInput().value).toBe("");
    expect(passwordInput().value).toBe("");
    expect(confirmationInput().value).toBe("");
  });

  it("the role select defaults to the lower rung — DoD-8", () => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    renderModal();
    expect(roleInput().value).toMatch(ROLEPLAYER_ROLE);
    expect(roleInput().value).not.toMatch(ADMIN_ROLE);
  });

  it("the role select offers exactly the two ladder values — DoD-8", async () => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    const user = newUser();
    renderModal();
    const options = await openRoleOptions(user);
    expect(options).toHaveLength(2);
    const texts = options.map((option) => option.textContent ?? "");
    expect(texts.filter((text) => ROLEPLAYER_ROLE.test(text) && !ADMIN_ROLE.test(text))).toHaveLength(1);
    expect(texts.filter((text) => ADMIN_ROLE.test(text) && !ROLEPLAYER_ROLE.test(text))).toHaveLength(1);
  });

  it("the default role is what is sent when none is chosen — DoD-8", async () => {
    const { mock } = serveUsers([]);
    const user = newUser();
    renderModal();
    await fill(user, { username: "newcomer", password: PASSWORD });
    await user.click(submitControl());
    await flush();
    const posts = seen(mock).filter((call) => call.method === "POST");
    expect(posts).toHaveLength(1);
    expect((posts[0].body as Record<string, unknown>).role).toBe("roleplayer");
  });

  it("choosing the upper rung sends the admin role — DoD-8", async () => {
    const { mock } = serveUsers([]);
    const user = newUser();
    renderModal();
    await fill(user, { username: "newcomer", password: PASSWORD });
    const options = await openRoleOptions(user);
    const admin = options.find((option) => ADMIN_ROLE.test(option.textContent ?? "") && !ROLEPLAYER_ROLE.test(option.textContent ?? ""));
    expect(admin).toBeDefined();
    await user.click(admin as HTMLElement);
    await flush(2);
    expect(roleInput().value).toMatch(ADMIN_ROLE);
    await user.click(submitControl());
    await flush();
    const posts = seen(mock).filter((call) => call.method === "POST");
    expect(posts).toHaveLength(1);
    expect((posts[0].body as Record<string, unknown>).role).toBe("admin");
  });
});

// ---------------------------------------------------------------------------
describe("the submit control", () => {
  it("is disabled for the empty form — DoD-3", () => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    renderModal();
    expect(submitControl()).toBeDisabled();
  });

  it.each<[string, { username: string; password: string; confirmation: string }]>([
    ["a missing username", { username: "   ", password: PASSWORD, confirmation: PASSWORD }],
    ["a mismatched confirmation", { username: "newcomer", password: PASSWORD, confirmation: `${PASSWORD}!` }],
  ])("is disabled for %s — DoD-3", async (_name, fields) => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    const user = newUser();
    renderModal();
    await fill(user, fields);
    expect(submitControl()).toBeDisabled();
  });

  it("is disabled for a missing password — DoD-3", async () => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    const user = newUser();
    renderModal();
    await user.type(usernameInput(), "newcomer");
    expect(submitControl()).toBeDisabled();
  });

  it("is enabled for a filled, matching form, including a one-character password — DoD-3, DoD-2", async () => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    const user = newUser();
    renderModal();
    await fill(user, { username: "n", password: "x" });
    expect(submitControl()).toBeEnabled();
  });

  it("is disabled while a submit is in flight, and a second activation issues no second request — DoD-3", async () => {
    const pending = deferred<Response>();
    const mock = stubFetch(() => pending.promise);
    const user = newUser();
    const { onSaved } = renderModal();
    await fill(user, { username: "newcomer", password: PASSWORD });
    await user.click(submitControl());
    await flush();
    expect(mock).toHaveBeenCalledTimes(1);
    expect(submitControl()).toBeDisabled();

    await user.click(submitControl());
    await flush();
    expect(mock).toHaveBeenCalledTimes(1);

    pending.resolve(
      jsonResponse({ id: "7340032000000301", username: "newcomer", role: "roleplayer", is_enabled: true, last_login_at: null }, 201),
    );
    await flush();
    expect(onSaved).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
describe("a successful submit from the modal", () => {
  it("posts exactly what was typed — no trimming, no case folding — and nothing else — DoD-5 (US-008.AC-1)", async () => {
    const { mock } = serveUsers([]);
    const user = newUser();
    renderModal();
    const username = "  Mireille Of The Lake ";
    const password = " Pass Word ";
    await fill(user, { username, password });
    await user.click(submitControl());
    await flush();
    const posts = seen(mock).filter((call) => call.method === "POST");
    expect(posts).toEqual([
      { method: "POST", path: LIST_PATH, search: "", body: { username, password, role: "roleplayer" } },
    ]);
  });

  it("invokes the saved callback exactly once, with the created account — DoD-5 (US-008.AC-1)", async () => {
    serveUsers([], { nextId: "7340032000000555" });
    const user = newUser();
    const { onSaved } = renderModal();
    await fill(user, { username: "newcomer", password: PASSWORD });
    await user.click(submitControl());
    await flush();
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onSaved.mock.calls[0][0]).toEqual({
      id: "7340032000000555",
      username: "newcomer",
      role: "roleplayer",
      is_enabled: true,
      last_login_at: null,
    });
  });

  it("raises no notification and shows no success message — DoD-10", async () => {
    serveUsers([]);
    const user = newUser();
    renderModal();
    await fill(user, { username: "newcomer", password: PASSWORD });
    await user.click(submitControl());
    await flush();
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(document.body.textContent ?? "").not.toMatch(/\b(success|successfully|created!?)\b/i);
  });

  it("hands the created account's id to the callback as the same string — DoD-12", async () => {
    serveUsers([], { nextId: BIG_ID });
    const user = newUser();
    const { onSaved } = renderModal();
    await fill(user, { username: "newcomer", password: PASSWORD });
    await user.click(submitControl());
    await flush();
    const passed = onSaved.mock.calls[0][0];
    expect(passed.id).toBe(BIG_ID);
    expect(typeof passed.id).toBe("string");
  });
});

// ---------------------------------------------------------------------------
describe("a 409 lands on the username field", () => {
  it("renders a 'username taken' message on the username field — DoD-6", async () => {
    serveUsers([MIREILLE]);
    const user = newUser();
    renderModal();
    await fill(user, { username: "mireille", password: PASSWORD });
    await user.click(submitControl());
    await flush();
    expect(describedText(usernameInput())).toMatch(USERNAME_TAKEN);
  });

  it("puts nothing on the general key and nothing new above the form — DoD-6", async () => {
    serveUsers([MIREILLE]);
    const user = newUser();
    renderModal();
    await fill(user, { username: "mireille", password: PASSWORD });
    const aboveBefore = textAbove(usernameInput());
    await user.click(submitControl());
    await flush();
    const draft = submittedDraft();
    expect(draft.serverErrors.general).toBeUndefined();
    expect(draft.serverErrors.username).toMatch(USERNAME_TAKEN);
    expect(textAbove(usernameInput())).toBe(aboveBefore);
  });

  it("the modal stays open and every typed value survives — DoD-6", async () => {
    serveUsers([MIREILLE]);
    const user = newUser();
    const { onClose, onSaved } = renderModal();
    await fill(user, { username: "mireille", password: PASSWORD });
    await user.click(submitControl());
    await flush();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
    expect(usernameInput().value).toBe("mireille");
    expect(passwordInput().value).toBe(PASSWORD);
    expect(confirmationInput().value).toBe(PASSWORD);
    expect(roleInput().value).toMatch(ROLEPLAYER_ROLE);
  });

  it("is keyed on the status: a 409 whose prose is unrelated still lands on the username field — DoD-6, DoD-7", async () => {
    stubFetch(() => Promise.resolve(envelopeResponse("username_taken", "Kettle zq-409 overflowed.", 409)));
    const user = newUser();
    renderModal();
    await fill(user, { username: "someone", password: PASSWORD });
    await user.click(submitControl());
    await flush();
    expect(describedText(usernameInput())).toMatch(USERNAME_TAKEN);
    expect(submittedDraft().serverErrors.general).toBeUndefined();
  });

  it("raises no notification — DoD-6", async () => {
    serveUsers([MIREILLE]);
    const user = newUser();
    renderModal();
    await fill(user, { username: "mireille", password: PASSWORD });
    await user.click(submitControl());
    await flush();
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("every other failure lands on the general key, above the form", () => {
  const FAILURES: Array<[string, FetchFn]> = [
    ["a 500 envelope", () => Promise.resolve(envelopeResponse("internal_error", FAILURE_MESSAGE, 500))],
    ["a 403 envelope", () => Promise.resolve(envelopeResponse("insufficient_role", "Higher role needed zq-403.", 403))],
    [
      "a 500 envelope whose prose says the username is taken",
      () => Promise.resolve(envelopeResponse("internal_error", "That username is already taken.", 500)),
    ],
    [
      "FastAPI's own 422 body",
      () =>
        Promise.resolve(
          jsonResponse({ detail: [{ type: "string_too_short", loc: ["body", "password"], msg: "too short", input: "" }] }, 422),
        ),
    ],
    [
      "a 502 with a malformed body",
      () => Promise.resolve(new Response("<html>Bad Gateway</html>", { status: 502, headers: { "Content-Type": "text/html" } })),
    ],
    ["a transport failure", () => Promise.reject(new TypeError("Failed to fetch"))],
  ];

  it.each(FAILURES)("%s renders the general error above the form and not on the username field — DoD-7 (D10)", async (_name, handler) => {
    vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(handler);
    const user = newUser();
    const { onClose, onSaved } = renderModal();
    await fill(user, { username: "newcomer", password: PASSWORD });
    await user.click(submitControl());
    await flush();

    const draft = submittedDraft();
    const general = draft.serverErrors.general;
    expect(typeof general).toBe("string");
    expect(general).not.toBe("");
    expect(draft.serverErrors.username).toBeUndefined();

    expect(textAbove(usernameInput())).toContain((general as string).replace(/\s+/g, " ").trim());
    expect(describedText(usernameInput())).not.toMatch(USERNAME_TAKEN);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
    expect(usernameInput().value).toBe("newcomer");
  });

  it("a failure raises no notification — DoD-7", async () => {
    stubFetch(() => Promise.resolve(envelopeResponse("internal_error", FAILURE_MESSAGE, 500)));
    const user = newUser();
    renderModal();
    await fill(user, { username: "newcomer", password: PASSWORD });
    await user.click(submitControl());
    await flush();
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("the Create button on the Users page", () => {
  it("the page header carries a Create button, before the table, and no modal is open at first — DoD-9", async () => {
    await renderLoadedPage();
    const button = createButton();
    const table = document.querySelector("table");
    expect(table).not.toBeNull();
    expect(isBefore(button, table as HTMLTableElement)).toBe(true);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("clicking it opens the create modal, and opening issues no request — DoD-9", async () => {
    const user = newUser();
    const { mock } = await renderLoadedPage();
    const before = mock.mock.calls.length;
    await openModalOnPage(user);
    expect(usernameInput()).toBeInTheDocument();
    expect(roleInput()).toBeInTheDocument();
    await flush();
    expect(mock.mock.calls.length).toBe(before);
  });

  it("closing and reopening yields an empty draft, with nothing from the previous open surviving — DoD-9", async () => {
    const user = newUser();
    await renderLoadedPage();
    await openModalOnPage(user);
    await fill(user, { username: "leftover-zq", password: "leftover-pw", confirmation: "leftover-other" });
    const options = await openRoleOptions(user);
    const admin = options.find((option) => ADMIN_ROLE.test(option.textContent ?? "") && !ROLEPLAYER_ROLE.test(option.textContent ?? ""));
    await user.click(admin as HTMLElement);
    await flush(2);
    expect(roleInput().value).toMatch(ADMIN_ROLE);

    await closeModal(user);

    await openModalOnPage(user);
    expect(usernameInput().value).toBe("");
    expect(passwordInput().value).toBe("");
    expect(confirmationInput().value).toBe("");
    expect(roleInput().value).toMatch(ROLEPLAYER_ROLE);
    expect(roleInput().value).not.toMatch(ADMIN_ROLE);
    expect(dialog().textContent ?? "").not.toContain("leftover-zq");
  });

  it("a server error from the previous open does not survive a close and reopen — DoD-9", async () => {
    const user = newUser();
    await renderLoadedPage();
    await openModalOnPage(user);
    await fill(user, { username: "mireille", password: PASSWORD });
    await user.click(submitControl());
    await flush();
    expect(describedText(usernameInput())).toMatch(USERNAME_TAKEN);

    await closeModal(user);

    await openModalOnPage(user);
    expect(describedText(usernameInput())).not.toMatch(USERNAME_TAKEN);
    expect(dialog().textContent ?? "").not.toMatch(USERNAME_TAKEN);
    expect(submitControl()).toBeDisabled();
  });

  it("each open submits a different draft instance — DoD-9", async () => {
    const user = newUser();
    await renderLoadedPage();
    await openModalOnPage(user);
    await fill(user, { username: "mireille", password: PASSWORD });
    await user.click(submitControl());
    await flush();
    const first = submittedDraft();

    await closeModal(user);

    await openModalOnPage(user);
    await fill(user, { username: "anselm", password: PASSWORD });
    await user.click(submitControl());
    await flush();
    const second = submittedDraft();
    expect(second).not.toBe(first);
    expect(first.username).toBe("mireille");
  });
});

// ---------------------------------------------------------------------------
describe("a successful create on the Users page", () => {
  it("closes the modal — DoD-10 (US-008.AC-1)", async () => {
    const user = newUser();
    await renderLoadedPage();
    await openModalOnPage(user);
    await fill(user, { username: "newcomer", password: PASSWORD });
    await user.click(submitControl());
    await flush();
    await waitForNoDialog();
  });

  it("re-loads the list after the create, through the page's load function and store — DoD-10 (US-008.AC-2)", async () => {
    const user = newUser();
    const { mock } = await renderLoadedPage();
    const store = pageStore();
    const loadsBefore = spied.load.length;
    await openModalOnPage(user);
    await fill(user, { username: "newcomer", password: PASSWORD });
    await user.click(submitControl());
    await flush();

    const calls = seen(mock);
    const postIndex = calls.findIndex((call) => call.method === "POST" && call.path === LIST_PATH);
    expect(postIndex).toBeGreaterThanOrEqual(0);
    const laterLists = calls.slice(postIndex + 1).filter((call) => call.method === "GET" && call.path === LIST_PATH);
    expect(laterLists.length).toBeGreaterThan(0);
    expect(spied.load.length).toBeGreaterThan(loadsBefore);
    expect(spied.load[spied.load.length - 1][0]).toBe(store);
  });

  it("the new account appears in the table, shown as enabled — DoD-10 (US-008.AC-1, US-008.AC-2)", async () => {
    const user = newUser();
    await renderLoadedPage();
    expect(bodyRows()).toHaveLength(2);
    await openModalOnPage(user);
    await fill(user, { username: "newcomer", password: PASSWORD });
    await user.click(submitControl());
    await flush();
    await waitForNoDialog();

    expect(bodyRows()).toHaveLength(3);
    const text = rowFor("newcomer").textContent ?? "";
    expect(text).toMatch(ENABLED_STATUS);
    expect(text).not.toMatch(DISABLED_STATUS);
  });

  it("the table reflects the re-load, not a local insert — a change only the server knows appears too — DoD-10", async () => {
    const user = newUser();
    const { rows } = await renderLoadedPage();
    rows.push({ id: "7340032000000999", username: "server-only-zq", role: "roleplayer", is_enabled: true, last_login_at: null });
    await openModalOnPage(user);
    await fill(user, { username: "newcomer", password: PASSWORD });
    await user.click(submitControl());
    await flush();
    await waitForNoDialog();
    rowFor("server-only-zq");
    rowFor("newcomer");
  });

  it("nothing is written before the server answers — no new row while the create is in flight — DoD-10", async () => {
    const user = newUser();
    const pending = deferred<Response>();
    await renderLoadedPage(EVERYONE, {
      override: (method, pathname) => (method === "POST" && pathname === LIST_PATH ? pending.promise : undefined),
    });
    await openModalOnPage(user);
    await fill(user, { username: "newcomer", password: PASSWORD });
    await user.click(submitControl());
    await flush();
    expect(bodyRows()).toHaveLength(2);
    pending.resolve(envelopeResponse("internal_error", FAILURE_MESSAGE, 500));
    await flush();
  });

  it("raises no success notification and shows no success message — DoD-10", async () => {
    const user = newUser();
    await renderLoadedPage();
    await openModalOnPage(user);
    await fill(user, { username: "newcomer", password: PASSWORD });
    await user.click(submitControl());
    await flush();
    await waitForNoDialog();
    expect(notificationRoots()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(document.body.textContent ?? "").not.toMatch(/\bsuccess(fully)?\b|\bcreated\b/i);
  });

  it("a 409 on the page keeps the modal open and the table unchanged — DoD-6", async () => {
    const user = newUser();
    await renderLoadedPage();
    await openModalOnPage(user);
    await fill(user, { username: "mireille", password: PASSWORD });
    await user.click(submitControl());
    await flush();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(describedText(usernameInput())).toMatch(USERNAME_TAKEN);
    expect(bodyRows()).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
describe("the open flag is component-local", () => {
  it("opening and closing the modal adds no field to the page store and changes none — DoD-11", async () => {
    const user = newUser();
    await renderLoadedPage();
    const store = pageStore();
    const fieldsBefore = Object.getOwnPropertyNames(store).sort();
    expect(fieldsBefore.filter((name) => isObservableProp(store, name))).toEqual(["errorMessage", "rows", "status"]);
    const rowsBefore = JSON.stringify(store.rows);

    await openModalOnPage(user);
    expect(Object.getOwnPropertyNames(store).sort()).toEqual(fieldsBefore);
    expect(JSON.stringify(store.rows)).toBe(rowsBefore);
    expect(store.status).toBe("ready");
    expect(store.errorMessage).toBeNull();

    await closeModal(user);
    expect(Object.getOwnPropertyNames(store).sort()).toEqual(fieldsBefore);
  });

  it("the submitted draft carries no open flag — DoD-11", async () => {
    const user = newUser();
    await renderLoadedPage();
    await openModalOnPage(user);
    await fill(user, { username: "mireille", password: PASSWORD });
    await user.click(submitControl());
    await flush();
    const names = Object.getOwnPropertyNames(submittedDraft());
    expect(names.filter((name) => /open|visible|shown/i.test(name))).toEqual([]);
  });

  it("the modal takes no open prop — mounting it shows it — DoD-11", () => {
    stubFetch(() => Promise.resolve(jsonResponse({}, 200)));
    renderModal();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
describe("ids are strings", () => {
  it("an id beyond MAX_SAFE_INTEGER reaches the page's store unchanged after the re-load — DoD-12", async () => {
    const user = newUser();
    await renderLoadedPage(EVERYONE, { nextId: BIG_ID });
    const store = pageStore();
    await openModalOnPage(user);
    await fill(user, { username: "newcomer", password: PASSWORD });
    await user.click(submitControl());
    await flush();
    await waitForNoDialog();
    const row = store.rows.find((candidate) => candidate.username === "newcomer");
    expect(row?.id).toBe(BIG_ID);
    expect(typeof row?.id).toBe("string");
  });

  it("this step's modules use no parseInt and type no id as a number — DoD-12", () => {
    for (const file of STEP_MODULES) {
      const source = stripComments(readFileSync(file, "utf8"));
      expect(source, path.basename(file)).not.toMatch(/\bparseInt\b|\bparseFloat\b|\bBigInt\s*\(/);
      expect(source, path.basename(file)).not.toMatch(/\b\w*(?:id|Id)\s*\??\s*:\s*number\b/);
    }
  });
});
