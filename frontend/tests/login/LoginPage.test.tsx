// Feature 004, step 005 — the `login` entry's page, its submit, the hand-off to `/`, and the
// entry wiring (docs/plans/004.authentication-session/005.login-entry.md).
// Covers DoD-3, DoD-4, DoD-5, DoD-6, DoD-7, DoD-8, DoD-9, DoD-10, DoD-11, DoD-12, DoD-13,
// DoD-14 at the rendered level. DoD-15..DoD-19 are [manual/live] and have no test.
//
// The page is rendered with its draft passed explicitly as a prop, wrapped in AppProviders.
// `fetch` is stubbed per test; `notifyFailure` is mocked at file level. Fields are found by
// their visible labels. The entry module itself is evaluated with the same recipe as
// `tests/entries.test.tsx` (vi.resetModules, a fresh #root, pushState, dynamic import).
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { runInAction } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LoginPage } from "../../src/login/LoginPage";
import { LoginDraft, submitLogin } from "../../src/login/loginDraft";
import { documentNavigation } from "../../src/shared/api";
import { AppProviders } from "../../src/shared/AppProviders";

const { notifyFailureSpy } = vi.hoisted(() => ({ notifyFailureSpy: vi.fn() }));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type HandOff = (url: string) => void;

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const LOGIN_SRC = path.join(FRONTEND_ROOT, "src", "login");

const USERNAME = "zq-roleplayer-one";
const PASSWORD = "Tq9-login-horse-zq";
const NOTIFICATION_ROOT = ".mantine-Notification-root";

const USERNAME_LABEL = /user\s*name/i;
const PASSWORD_LABEL = /password/i;
const NOT_READY_TEXT = /not\s+(yet\s+)?ready/i;

beforeEach(() => {
  notifyFailureSpy.mockClear();
  window.localStorage.clear();
});

afterEach(async () => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  const { notifications } = await import("@mantine/notifications");
  act(() => {
    notifications.clean();
  });
  document.body.innerHTML = "";
  window.history.pushState({}, "", "/");
});

// ---------------------------------------------------------------- helpers

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

function envelope(code: string, message: string, status: number, detail: Record<string, unknown> = {}) {
  return () => Promise.resolve(jsonResponse({ error: { code, message, detail } }, status));
}

const signedIn = (role: string = "roleplayer") => () =>
  Promise.resolve(jsonResponse({ id: "7340032000000009", username: USERNAME, role }, 200));

const invalidCredentials = (message = "Invalid username or password.") =>
  envelope("invalid_credentials", message, 400);

const transportFailure = () => Promise.reject(new TypeError("Failed to fetch"));

const malformed502 = () =>
  Promise.resolve(
    new Response("<html><body>502 Bad Gateway</body></html>", {
      status: 502,
      headers: { "Content-Type": "text/html" },
    }),
  );

const malformed503 = () =>
  Promise.resolve(
    new Response("<html><body>503 Service Temporarily Unavailable</body></html>", {
      status: 503,
      headers: { "Content-Type": "text/html" },
    }),
  );

const fastApi422 = () =>
  Promise.resolve(
    jsonResponse({ detail: [{ type: "string_too_short", loc: ["body", "username"], msg: "too short", input: "" }] }, 422),
  );

const backend500 = envelope("internal_error", "Login exploded zq-42.", 500);

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

async function flush(rounds = 4): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => setImmediate(resolve));
    });
  }
}

function requestPath(input: RequestInfo | URL): string {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost").pathname;
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function requestJson(init?: RequestInit): unknown {
  const raw = init?.body;
  if (typeof raw !== "string") {
    throw new Error(`request body is not a JSON string: ${String(raw)}`);
  }
  return JSON.parse(raw);
}

function loginCalls(fetchMock: ReturnType<typeof stubFetch>) {
  return fetchMock.mock.calls.filter(([input]) => requestPath(input) === "/api/auth/login");
}

function fillDraft(draft: LoginDraft, fields: { username: string; password: string }) {
  runInAction(() => {
    draft.username = fields.username;
    draft.password = fields.password;
  });
}

function validDraft(): LoginDraft {
  const draft = new LoginDraft();
  fillDraft(draft, { username: USERNAME, password: PASSWORD });
  return draft;
}

function renderPage(options: { draft?: LoginDraft; handOff?: HandOff | null } = {}) {
  const draft = options.draft ?? new LoginDraft();
  const handOff = options.handOff === undefined ? vi.fn<HandOff>() : options.handOff;
  const view = render(
    <AppProviders>
      {handOff === null ? <LoginPage draft={draft} /> : <LoginPage draft={draft} handOff={handOff} />}
    </AppProviders>,
  );
  return { draft, handOff, ...view };
}

function inputsLabelled(label: RegExp): HTMLInputElement[] {
  return screen.getAllByLabelText(label).filter((el): el is HTMLInputElement => el instanceof HTMLInputElement);
}

function usernameInput(): HTMLInputElement {
  const found = inputsLabelled(USERNAME_LABEL);
  expect(found).toHaveLength(1);
  return found[0];
}

function passwordInput(): HTMLInputElement {
  const found = inputsLabelled(PASSWORD_LABEL);
  expect(found).toHaveLength(1);
  return found[0];
}

function submitControl(): HTMLElement {
  const controls = document.querySelectorAll<HTMLElement>('button[type="submit"], input[type="submit"]');
  expect(controls).toHaveLength(1);
  return controls[0];
}

/** Activate the submit control and, if the page has a form, fire its submit event too. */
function activateSubmit(): void {
  act(() => {
    fireEvent.click(submitControl());
    const form = document.querySelector("form");
    if (form !== null) fireEvent.submit(form);
  });
}

async function clickSubmit(): Promise<void> {
  act(() => {
    fireEvent.click(submitControl());
  });
  await flush();
}

function pageText(): string {
  return document.body.textContent ?? "";
}

function alerts(): HTMLElement[] {
  return screen.queryAllByRole("alert");
}

function alertText(): string {
  return alerts()
    .map((el) => el.textContent ?? "")
    .join("\n");
}

/** The text of every element an input's aria-describedby points at (where field errors attach). */
function describedText(input: HTMLElement): string {
  const ids = (input.getAttribute("aria-describedby") ?? "").split(/\s+/).filter(Boolean);
  return ids.map((id) => document.getElementById(id)?.textContent ?? "").join(" ");
}

function notificationRoots(): Element[] {
  return Array.from(document.querySelectorAll(NOTIFICATION_ROOT));
}

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

function importSpecifiers(source: string): string[] {
  const pattern = /(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)["']([^"']+)["']/g;
  return Array.from(stripComments(source).matchAll(pattern), (m) => m[1]);
}

/** Every .ts/.tsx module under frontend/src/login/, recursively. */
function loginModules(dir: string = LOGIN_SRC): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return loginModules(full);
    return /\.(ts|tsx)$/.test(name) ? [full] : [];
  });
}

async function mountLoginEntry(pathname: string): Promise<void> {
  vi.resetModules();
  document.body.innerHTML = '<div id="root"></div>';
  window.history.pushState({}, "", pathname);
  await act(async () => {
    await import("../../src/login/main");
  });
}

/** The rendered state a person sees after a submit: what the alert says and where messages sit. */
function renderedFailureSnapshot() {
  return {
    alertText: alertText(),
    alertCount: alerts().length,
    usernameInvalid: usernameInput().getAttribute("aria-invalid"),
    passwordInvalid: passwordInput().getAttribute("aria-invalid"),
    usernameDescribed: describedText(usernameInput()),
    passwordDescribed: describedText(passwordInput()),
    usernameValue: usernameInput().value,
    submitDisabled: submitControl().hasAttribute("disabled"),
    inputCount: document.querySelectorAll("input").length,
  };
}

// ---------------------------------------------------------------------------
describe("the submit control", () => {
  it("is disabled for an empty draft — DoD-3", () => {
    stubFetch(signedIn());
    renderPage();
    expect(submitControl()).toBeDisabled();
  });

  it.each<[string, { username: string; password: string }]>([
    ["an empty username", { username: "", password: PASSWORD }],
    ["a whitespace-only username", { username: "   ", password: PASSWORD }],
    ["an empty password", { username: USERNAME, password: "" }],
  ])("is disabled for %s — DoD-3", (_name, fields) => {
    stubFetch(signedIn());
    const draft = new LoginDraft();
    fillDraft(draft, fields);
    renderPage({ draft });
    expect(submitControl()).toBeDisabled();
  });

  it("is enabled for a valid draft with no submit in flight — DoD-3", () => {
    stubFetch(signedIn());
    renderPage({ draft: validDraft() });
    expect(submitControl()).toBeEnabled();
  });

  it("is disabled while the draft marks a submit in flight — DoD-3", () => {
    stubFetch(signedIn());
    const draft = validDraft();
    runInAction(() => {
      draft.submitting = true;
    });
    renderPage({ draft });
    expect(submitControl()).toBeDisabled();
  });

  it("activating an invalid form issues no request — DoD-3", async () => {
    const fetchMock = stubFetch(signedIn());
    renderPage();
    activateSubmit();
    await flush();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("is disabled while a submit is in flight, and a second activation issues no second request — DoD-3", async () => {
    const pending = deferred<Response>();
    const fetchMock = stubFetch(() => pending.promise);
    const { handOff } = renderPage({ draft: validDraft() });
    await clickSubmit();
    expect(loginCalls(fetchMock)).toHaveLength(1);
    expect(submitControl()).toBeDisabled();

    activateSubmit();
    await flush();
    expect(loginCalls(fetchMock)).toHaveLength(1);

    pending.resolve(await signedIn()());
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(handOff).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
describe("a successful submit", () => {
  it("typing and submitting posts exactly one POST /api/auth/login with the typed values — DoD-4 (US-004.AC-1)", async () => {
    const fetchMock = stubFetch(signedIn());
    const user = userEvent.setup();
    renderPage();
    await user.type(usernameInput(), USERNAME);
    await user.type(passwordInput(), PASSWORD);
    await user.click(submitControl());
    await flush();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [input, init] = fetchMock.mock.calls[0];
    expect(requestPath(input)).toBe("/api/auth/login");
    expect(requestMethod(input, init)).toBe("POST");
    expect(requestJson(init)).toEqual({ username: USERNAME, password: PASSWORD });
  });

  it("typed whitespace and case are sent byte-for-byte, with no trimming or folding — DoD-4 (context.md D13)", async () => {
    const typedUsername = "  Mixed Case User  ";
    const typedPassword = "  PaSs WoRd  ";
    const fetchMock = stubFetch(signedIn());
    const user = userEvent.setup();
    renderPage();
    await user.type(usernameInput(), typedUsername);
    await user.type(passwordInput(), typedPassword);
    await user.click(submitControl());
    await flush();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const body = requestJson(fetchMock.mock.calls[0][1]) as Record<string, unknown>;
    expect(body.username).toBe(typedUsername);
    expect(body.password).toBe(typedPassword);
    expect(Object.keys(body).sort()).toEqual(["password", "username"]);
  });

  it("the request body carries the username and password and nothing else — DoD-4", async () => {
    const fetchMock = stubFetch(signedIn());
    renderPage({ draft: validDraft() });
    await clickSubmit();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(requestJson(fetchMock.mock.calls[0][1])).toEqual({ username: USERNAME, password: PASSWORD });
  });

  it("runs the injected hand-off once, targeting / — DoD-5 (US-004.AC-2)", async () => {
    stubFetch(signedIn());
    const { handOff } = renderPage({ draft: validDraft() });
    await clickSubmit();
    await flush();
    expect(handOff).toHaveBeenCalledTimes(1);
    expect(handOff).toHaveBeenCalledWith("/");
  });

  it("without a hand-off prop the default is the document navigation to /, once — DoD-5 (US-004.AC-2)", async () => {
    const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(signedIn());
    renderPage({ draft: validDraft(), handOff: null });
    await clickSubmit();
    await flush();
    expect(assignSpy).toHaveBeenCalledTimes(1);
    expect(assignSpy).toHaveBeenCalledWith("/");
  });

  it("an injected hand-off replaces the default: no document navigation happens — DoD-5", async () => {
    const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(signedIn());
    const { handOff } = renderPage({ draft: validDraft() });
    await clickSubmit();
    await flush();
    expect(handOff).toHaveBeenCalledTimes(1);
    expect(assignSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("no role branch", () => {
  it.each<[string, () => Promise<Response>]>([
    ["an admin identity", signedIn("admin")],
    ["a roleplayer identity", signedIn("roleplayer")],
    ["an unknown role", signedIn("some-future-role")],
    ["an empty object", () => Promise.resolve(jsonResponse({}, 200))],
    ["a JSON null", () => Promise.resolve(jsonResponse(null, 200))],
    ["an empty 200 body", () => Promise.resolve(new Response(null, { status: 200 }))],
  ])("a success reporting %s hands off to / exactly once — DoD-6 (US-004.AC-2, context.md D12)", async (_name, handler) => {
    stubFetch(handler);
    const { handOff } = renderPage({ draft: validDraft() });
    await clickSubmit();
    await flush();
    expect(handOff).toHaveBeenCalledTimes(1);
    expect(handOff).toHaveBeenCalledWith("/");
  });

  it("an admin identity does not go to /admin — DoD-6 (context.md D12)", async () => {
    stubFetch(signedIn("admin"));
    const handOff = vi.fn<HandOff>();
    renderPage({ draft: validDraft(), handOff });
    await clickSubmit();
    await flush();
    const targets = handOff.mock.calls.map(([url]) => url);
    expect(targets).toEqual(["/"]);
  });

  it("with the default hand-off, admin and roleplayer land on the same / — DoD-6", async () => {
    const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(signedIn("admin"));
    renderPage({ draft: validDraft(), handOff: null });
    await clickSubmit();
    cleanup();
    vi.unstubAllGlobals();
    stubFetch(signedIn("roleplayer"));
    renderPage({ draft: validDraft(), handOff: null });
    await clickSubmit();
    await flush();
    expect(assignSpy.mock.calls.map(([url]) => url)).toEqual(["/", "/"]);
  });
});

// ---------------------------------------------------------------------------
describe("the invalid_credentials refusal", () => {
  it("renders one fixed message in the general alert and runs no hand-off — DoD-7 (US-005.AC-2)", async () => {
    stubFetch(invalidCredentials());
    const { draft, handOff } = renderPage({ draft: validDraft() });
    await clickSubmit();

    const general = draft.serverErrors.general ?? "";
    expect(general).not.toBe("");
    expect(alerts().length).toBeGreaterThan(0);
    expect(alerts().some((el) => (el.textContent ?? "").includes(general))).toBe(true);
    expect(handOff).not.toHaveBeenCalled();
  });

  it("the rendered message is the same whatever prose the server sent — DoD-7", async () => {
    stubFetch(invalidCredentials("Server prose zq-alpha-81."));
    renderPage({ draft: validDraft() });
    await clickSubmit();
    const first = alertText();
    cleanup();
    vi.unstubAllGlobals();

    stubFetch(invalidCredentials("Different prose zq-beta-82."));
    renderPage({ draft: validDraft() });
    await clickSubmit();
    const second = alertText();

    expect(first).not.toBe("");
    expect(first).toBe(second);
    expect(pageText()).not.toContain("zq-beta-82");
  });

  it("leaves the form mounted and usable with the entered username preserved — DoD-7", async () => {
    stubFetch(invalidCredentials());
    const { draft } = renderPage({ draft: validDraft() });
    await clickSubmit();
    expect(usernameInput().value).toBe(USERNAME);
    expect(draft.username).toBe(USERNAME);
    expect(passwordInput()).toBeInTheDocument();
    expect(submitControl()).toBeEnabled();
  });

  it("places no message on the username or password field — DoD-7", async () => {
    stubFetch(invalidCredentials());
    const { draft } = renderPage({ draft: validDraft() });
    await clickSubmit();
    expect(usernameInput()).not.toHaveAttribute("aria-invalid", "true");
    expect(passwordInput()).not.toHaveAttribute("aria-invalid", "true");
    const general = draft.serverErrors.general ?? "";
    expect(general).not.toBe("");
    expect(describedText(usernameInput())).not.toContain(general);
    expect(describedText(passwordInput())).not.toContain(general);
  });

  it("the message appears once on the page — DoD-7", async () => {
    stubFetch(invalidCredentials());
    const { draft } = renderPage({ draft: validDraft() });
    await clickSubmit();
    const general = draft.serverErrors.general ?? "";
    expect(general).not.toBe("");
    expect(pageText().split(general).length - 1).toBe(1);
  });

  it("the form can be submitted again after the refusal, and a success then hands off — DoD-7", async () => {
    let calls = 0;
    const fetchMock = stubFetch(() => {
      calls += 1;
      return calls === 1 ? invalidCredentials()() : signedIn()();
    });
    const { handOff } = renderPage({ draft: validDraft() });
    await clickSubmit();
    expect(alerts().length).toBeGreaterThan(0);
    expect(handOff).not.toHaveBeenCalled();
    await clickSubmit();
    expect(loginCalls(fetchMock)).toHaveLength(2);
    expect(handOff).toHaveBeenCalledTimes(1);
    expect(handOff).toHaveBeenCalledWith("/");
  });

  it("performs no document navigation (the page does not reload) — DoD-7", async () => {
    const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(invalidCredentials());
    renderPage({ draft: validDraft(), handOff: null });
    await clickSubmit();
    await flush();
    expect(assignSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("a disabled account", () => {
  it("renders exactly as a wrong password does — same message, same place, same form — DoD-8 (US-006.AC-2, context.md D1)", async () => {
    stubFetch(invalidCredentials());
    const wrong = renderPage({ draft: validDraft() });
    await clickSubmit();
    const wrongSnapshot = renderedFailureSnapshot();
    expect(wrong.handOff).not.toHaveBeenCalled();
    cleanup();
    vi.unstubAllGlobals();

    stubFetch(envelope("invalid_credentials", "This account is disabled zq-dis-1.", 400, { reason: "account_disabled" }));
    const disabled = renderPage({ draft: validDraft() });
    await clickSubmit();
    const disabledSnapshot = renderedFailureSnapshot();
    expect(disabled.handOff).not.toHaveBeenCalled();

    expect(wrongSnapshot.alertText).not.toBe("");
    expect(disabledSnapshot).toEqual(wrongSnapshot);
    expect(alertText()).not.toMatch(/disabled/i);
    expect(pageText()).not.toContain("zq-dis-1");
  });
});

// ---------------------------------------------------------------------------
describe("any other failure renders in place", () => {
  it.each<[string, () => Promise<Response>]>([
    ["a transport failure", transportFailure],
    ["a malformed body at 502", malformed502],
    ["a malformed body at 503", malformed503],
    ["FastAPI's own 422", fastApi422],
    ["a backend error envelope at 500", backend500],
  ])("%s shows the general inline alert, keeps the form, and navigates nowhere — DoD-9 (context.md D14)", async (_name, handler) => {
    const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    const fetchMock = stubFetch(handler);
    const { draft, handOff } = renderPage({ draft: validDraft() });
    await clickSubmit();
    await flush();

    const general = draft.serverErrors.general ?? "";
    expect(general).not.toBe("");
    expect(alerts().some((el) => (el.textContent ?? "").includes(general))).toBe(true);
    expect(handOff).not.toHaveBeenCalled();
    expect(assignSpy).not.toHaveBeenCalled();
    expect(usernameInput().value).toBe(USERNAME);
    expect(passwordInput()).toBeInTheDocument();
    expect(submitControl()).toBeEnabled();
    expect(loginCalls(fetchMock)).toHaveLength(1);
  });

  it.each<[string, () => Promise<Response>]>([
    ["a transport failure", transportFailure],
    ["a malformed body at 502", malformed502],
    ["a malformed body at 503", malformed503],
    ["FastAPI's own 422", fastApi422],
  ])("%s renders no not-ready-yet screen — DoD-9 (context.md D14)", async (_name, handler) => {
    stubFetch(handler);
    renderPage({ draft: validDraft() });
    await clickSubmit();
    await flush();
    expect(pageText()).not.toMatch(NOT_READY_TEXT);
    expect(document.querySelector('[data-entry="login"]')).not.toBeNull();
    expect(usernameInput()).toBeInTheDocument();
    expect(passwordInput()).toBeInTheDocument();
  });

  it("a general server error already on the draft renders as an inline alert — DoD-9", () => {
    stubFetch(signedIn());
    const draft = validDraft();
    runInAction(() => {
      draft.serverErrors = { general: "Pre-set general zq-55." };
    });
    renderPage({ draft });
    expect(alerts().some((el) => (el.textContent ?? "").includes("Pre-set general zq-55."))).toBe(true);
  });
});

// ---------------------------------------------------------------------------
describe("the password is never readable", () => {
  it("the password input is masked and the username input is not — DoD-10", () => {
    stubFetch(signedIn());
    renderPage({ draft: validDraft() });
    expect(passwordInput()).toHaveAttribute("type", "password");
    expect(usernameInput()).not.toHaveAttribute("type", "password");
  });

  it("no rendered text shows the password, and any input holding it is masked — DoD-10", () => {
    stubFetch(signedIn());
    renderPage({ draft: validDraft() });
    expect(pageText()).not.toContain(PASSWORD);
    for (const input of Array.from(document.querySelectorAll("input"))) {
      if (input.value === PASSWORD) {
        expect(input).toHaveAttribute("type", "password");
      }
    }
  });

  it.each<[string, () => Promise<Response>]>([
    ["the refusal", invalidCredentials()],
    ["a transport failure", transportFailure],
    ["a malformed body at 502", malformed502],
    ["FastAPI's own 422", fastApi422],
    ["a backend error envelope", backend500],
    ["a server message echoing both values", envelope("internal_error", `Failed for ${USERNAME} with ${PASSWORD}.`, 500)],
    ["a refusal message echoing both values", invalidCredentials(`No ${USERNAME} with ${PASSWORD}.`)],
  ])("after %s the general alert contains neither field's value — DoD-10", async (_name, handler) => {
    stubFetch(handler);
    renderPage({ draft: validDraft() });
    await clickSubmit();
    const shown = alerts();
    expect(shown.length).toBeGreaterThan(0);
    for (const el of shown) {
      expect(el.textContent ?? "").not.toContain(USERNAME);
      expect(el.textContent ?? "").not.toContain(PASSWORD);
    }
    expect(pageText()).not.toContain(PASSWORD);
  });
});

// ---------------------------------------------------------------------------
describe("an aborted submit", () => {
  it("renders no failure and runs no hand-off — DoD-11", async () => {
    stubFetch(backend500);
    const { draft, handOff } = renderPage({ draft: validDraft() });
    const controller = new AbortController();
    controller.abort();
    await act(async () => {
      await submitLogin(draft, controller.signal);
    });
    await flush();
    expect(draft.serverErrors).toEqual({});
    expect(alerts()).toEqual([]);
    expect(pageText()).not.toContain("zq-42");
    expect(handOff).not.toHaveBeenCalled();
    expect(usernameInput().value).toBe(USERNAME);
  });
});

// ---------------------------------------------------------------------------
describe("no request on mount", () => {
  it("rendering the page issues no request — DoD-12", async () => {
    const fetchMock = stubFetch(signedIn());
    renderPage();
    await flush();
    renderPage({ draft: validDraft() });
    await flush();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(["/login", "/", "/login/deep/link"])(
    "mounting the login entry at %s issues no request at all, in particular no /api/me — DoD-12",
    async (pathname) => {
      const fetchMock = stubFetch(signedIn());
      await mountLoginEntry(pathname);
      await flush();
      expect(fetchMock).not.toHaveBeenCalled();
      expect(fetchMock.mock.calls.some(([input]) => requestPath(input) === "/api/me")).toBe(false);
    },
  );

  it("the mounted entry issues its only request in response to a submit — DoD-12", async () => {
    const fetchMock = stubFetch(invalidCredentials());
    await mountLoginEntry("/login");
    await flush();
    expect(fetchMock).not.toHaveBeenCalled();

    const user = userEvent.setup();
    await user.type(usernameInput(), USERNAME);
    await user.type(passwordInput(), PASSWORD);
    await user.click(submitControl());
    await flush();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [input, init] = fetchMock.mock.calls[0];
    expect(requestPath(input)).toBe("/api/auth/login");
    expect(requestMethod(input, init)).toBe("POST");
    expect(fetchMock.mock.calls.some(([call]) => requestPath(call) === "/api/me")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("no notification anywhere in the entry", () => {
  it.each<[string, () => Promise<Response>]>([
    ["signed in", signedIn()],
    ["refused", invalidCredentials()],
    ["a backend failure", backend500],
    ["a transport failure", transportFailure],
    ["a malformed body at 502", malformed502],
    ["FastAPI's own 422", fastApi422],
  ])("submitting (%s) calls notifyFailure nowhere and renders no notification — DoD-13", async (_name, handler) => {
    stubFetch(handler);
    renderPage({ draft: validDraft() });
    await clickSubmit();
    await flush();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(notificationRoots()).toEqual([]);
  });

  it("no module under src/login/ imports notifyFailure or Mantine's notification API — DoD-13", () => {
    const offenders = loginModules().flatMap((file) =>
      importSpecifiers(readFileSync(file, "utf8"))
        .filter((spec) => /notifyFailure|@mantine\/notifications/.test(spec))
        .map((spec) => `${path.relative(LOGIN_SRC, file)} imports ${spec}`),
    );
    expect(offenders).toEqual([]);
  });

  it("no module under src/login/ calls notifyFailure — DoD-13", () => {
    const offenders = loginModules().filter((file) => /\bnotifyFailure\b/.test(stripComments(readFileSync(file, "utf8"))));
    expect(offenders.map((file) => path.relative(LOGIN_SRC, file))).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("the entry marker, the router and stylesheets", () => {
  it("the page carries the login entry marker exactly once, around the form — DoD-14", () => {
    stubFetch(signedIn());
    renderPage();
    const markers = document.querySelectorAll('[data-entry="login"]');
    expect(markers).toHaveLength(1);
    expect(markers[0].contains(usernameInput())).toBe(true);
    expect(markers[0].contains(passwordInput())).toBe(true);
    expect(document.querySelectorAll("[data-entry]")).toHaveLength(1);
  });

  it.each(["/", "/login", "/login/", "/sessions/abc123"])(
    "the mounted entry renders its marker and the form at %s (no basename in effect) — DoD-14",
    async (pathname) => {
      stubFetch(signedIn());
      await mountLoginEntry(pathname);
      await flush();
      const root = document.getElementById("root");
      expect(root).not.toBeNull();
      expect(root?.querySelectorAll('[data-entry="login"]')).toHaveLength(1);
      expect(Array.from(document.querySelectorAll("[data-entry]"), (el) => el.getAttribute("data-entry"))).toEqual([
        "login",
      ]);
      expect(usernameInput()).toBeInTheDocument();
    },
  );

  it("login/main.tsx declares no router basename — DoD-14", () => {
    const source = stripComments(readFileSync(path.join(LOGIN_SRC, "main.tsx"), "utf8"));
    expect(source).not.toMatch(/\bbasename\b/);
  });

  it("no module under src/login/ imports a stylesheet — DoD-14", () => {
    const offenders = loginModules().flatMap((file) =>
      importSpecifiers(readFileSync(file, "utf8"))
        .filter((spec) => /\.(css|scss|sass|less|styl)(\?.*)?$/i.test(spec))
        .map((spec) => `${path.relative(LOGIN_SRC, file)} imports ${spec}`),
    );
    expect(offenders).toEqual([]);
  });
});
