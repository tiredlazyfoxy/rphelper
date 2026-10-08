// Feature 004, step 005 — the `login` entry's page, its submit, the hand-off to `/`, and the
// entry wiring (docs/plans/004.authentication-session/005.login-entry.md).
// Covers DoD-3, DoD-4, DoD-5, DoD-6, DoD-7, DoD-8, DoD-9, DoD-10, DoD-11, DoD-12, DoD-13,
// DoD-14 at the rendered level. DoD-15..DoD-19 are [manual/live] and have no test.
//
// The page is rendered with its draft passed explicitly as a prop, wrapped in AppProviders.
// `fetch` is stubbed per test; `notifyFailure` is mocked at file level. Fields are found by
// their visible labels. The entry module itself is evaluated with the same recipe as
// `tests/entries.test.tsx` (vi.resetModules, a fresh #root, pushState, dynamic import).
//
// fast/010.unconfigured-to-bootstrap (docs/plans/fast/010.unconfigured-to-bootstrap/plan.md):
// the page now probes GET /api/health on mount and shows the form only once the probe has
// settled on a configured instance (or failed). Its DoD-7: every pre-existing case keeps its
// assertions; the only change is that `stubFetch` now answers `/api/health` with
// `{ configured: true }` through a separate mock (so the mock it returns still records exactly
// the requests the case cares about), and `renderPage` awaits the probe before returning.
// The 004 DoD-12 "no request on mount" cases now mean "no request beyond the health probe".
// The new probe cases (fast/010 DoD-1..DoD-6) are in the "fast/010 —" describe blocks at the
// bottom; their test names carry "(010 DoD-n)".
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

const HEALTH_PATH = "/api/health";
const BOOTSTRAP_URL = "/bootstrap/";

beforeEach(() => {
  notifyFailureSpy.mockClear();
  window.localStorage.clear();
});

afterEach(async () => {
  cleanup();
  vi.useRealTimers();
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

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function requestPath(input: RequestInfo | URL): string {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost").pathname;
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

/** fast/010 — a health body: `configured` as given, `status`/`schema` shaped plausibly. */
function healthBody(configured: unknown): Record<string, unknown> {
  return configured === true
    ? { status: "ok", configured, schema: "ok" }
    : { status: "degraded", configured, schema: "missing" };
}

/** fast/010 — `/api/health` answering 200 with `configured` as given. */
const healthAnswer = (configured: unknown) => () => Promise.resolve(jsonResponse(healthBody(configured), 200));

/**
 * fast/010 — a total fetch stub. `/api/health` is answered by `health` (default: configured), every
 * other request by `impl`. `all` records every request; `rest` records only the non-health ones.
 */
function stubFetchRouted(impl: FetchFn, health: FetchFn = healthAnswer(true)) {
  const rest = vi.fn<FetchFn>(impl);
  const healthMock = vi.fn<FetchFn>(health);
  const all = vi.fn<FetchFn>((input, init) =>
    requestPath(input) === HEALTH_PATH ? healthMock(input, init) : rest(input, init),
  );
  vi.stubGlobal("fetch", all);
  return { all, rest, health: healthMock };
}

/** The pre-010 helper: the returned mock records only the non-health requests (010 DoD-7). */
function stubFetch(impl: FetchFn) {
  return stubFetchRouted(impl).rest;
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
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function flush(rounds = 4): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => setImmediate(resolve));
    });
  }
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

/** fast/010 — render without waiting for the mount probe. */
function mountPage(options: { draft?: LoginDraft; handOff?: HandOff | null } = {}) {
  const draft = options.draft ?? new LoginDraft();
  const handOff = options.handOff === undefined ? vi.fn<HandOff>() : options.handOff;
  const view = render(
    <AppProviders>
      {handOff === null ? <LoginPage draft={draft} /> : <LoginPage draft={draft} handOff={handOff} />}
    </AppProviders>,
  );
  return { draft, handOff, ...view };
}

/** Render and let the mount probe settle (fast/010: the form appears only after it). */
async function renderPage(options: { draft?: LoginDraft; handOff?: HandOff | null } = {}) {
  const rendered = mountPage(options);
  await flush();
  return rendered;
}

function inputsLabelled(label: RegExp): HTMLInputElement[] {
  return screen.queryAllByLabelText(label).filter((el): el is HTMLInputElement => el instanceof HTMLInputElement);
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

function submitControls(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>('button[type="submit"], input[type="submit"]'));
}

function submitControl(): HTMLElement {
  const controls = submitControls();
  expect(controls).toHaveLength(1);
  return controls[0];
}

/** fast/010 — "shows the form": the username and password fields and the submit control are present. */
function expectForm(): void {
  expect(inputsLabelled(USERNAME_LABEL)).toHaveLength(1);
  expect(inputsLabelled(PASSWORD_LABEL)).toHaveLength(1);
  expect(submitControls()).toHaveLength(1);
}

/** fast/010 — "shows no form": none of the username field, the password field, the submit control. */
function expectNoForm(): void {
  expect(inputsLabelled(USERNAME_LABEL)).toHaveLength(0);
  expect(inputsLabelled(PASSWORD_LABEL)).toHaveLength(0);
  expect(submitControls()).toHaveLength(0);
  expect(document.querySelectorAll("input")).toHaveLength(0);
}

function loginRoot(): Element | null {
  return document.querySelector('[data-entry="login"]');
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
  it("is disabled for an empty draft — DoD-3", async () => {
    stubFetch(signedIn());
    await renderPage();
    expect(submitControl()).toBeDisabled();
  });

  it.each<[string, { username: string; password: string }]>([
    ["an empty username", { username: "", password: PASSWORD }],
    ["a whitespace-only username", { username: "   ", password: PASSWORD }],
    ["an empty password", { username: USERNAME, password: "" }],
  ])("is disabled for %s — DoD-3", async (_name, fields) => {
    stubFetch(signedIn());
    const draft = new LoginDraft();
    fillDraft(draft, fields);
    await renderPage({ draft });
    expect(submitControl()).toBeDisabled();
  });

  it("is enabled for a valid draft with no submit in flight — DoD-3", async () => {
    stubFetch(signedIn());
    await renderPage({ draft: validDraft() });
    expect(submitControl()).toBeEnabled();
  });

  it("is disabled while the draft marks a submit in flight — DoD-3", async () => {
    stubFetch(signedIn());
    const draft = validDraft();
    runInAction(() => {
      draft.submitting = true;
    });
    await renderPage({ draft });
    expect(submitControl()).toBeDisabled();
  });

  it("activating an invalid form issues no request — DoD-3", async () => {
    const fetchMock = stubFetch(signedIn());
    await renderPage();
    activateSubmit();
    await flush();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("is disabled while a submit is in flight, and a second activation issues no second request — DoD-3", async () => {
    const pending = deferred<Response>();
    const fetchMock = stubFetch(() => pending.promise);
    const { handOff } = await renderPage({ draft: validDraft() });
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
    await renderPage();
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
    await renderPage();
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
    await renderPage({ draft: validDraft() });
    await clickSubmit();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(requestJson(fetchMock.mock.calls[0][1])).toEqual({ username: USERNAME, password: PASSWORD });
  });

  it("runs the injected hand-off once, targeting / — DoD-5 (US-004.AC-2)", async () => {
    stubFetch(signedIn());
    const { handOff } = await renderPage({ draft: validDraft() });
    await clickSubmit();
    await flush();
    expect(handOff).toHaveBeenCalledTimes(1);
    expect(handOff).toHaveBeenCalledWith("/");
  });

  it("without a hand-off prop the default is the document navigation to /, once — DoD-5 (US-004.AC-2)", async () => {
    const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(signedIn());
    await renderPage({ draft: validDraft(), handOff: null });
    await clickSubmit();
    await flush();
    expect(assignSpy).toHaveBeenCalledTimes(1);
    expect(assignSpy).toHaveBeenCalledWith("/");
  });

  it("an injected hand-off replaces the default: no document navigation happens — DoD-5", async () => {
    const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(signedIn());
    const { handOff } = await renderPage({ draft: validDraft() });
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
    const { handOff } = await renderPage({ draft: validDraft() });
    await clickSubmit();
    await flush();
    expect(handOff).toHaveBeenCalledTimes(1);
    expect(handOff).toHaveBeenCalledWith("/");
  });

  it("an admin identity does not go to /admin — DoD-6 (context.md D12)", async () => {
    stubFetch(signedIn("admin"));
    const handOff = vi.fn<HandOff>();
    await renderPage({ draft: validDraft(), handOff });
    await clickSubmit();
    await flush();
    const targets = handOff.mock.calls.map(([url]) => url);
    expect(targets).toEqual(["/"]);
  });

  it("with the default hand-off, admin and roleplayer land on the same / — DoD-6", async () => {
    const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(signedIn("admin"));
    await renderPage({ draft: validDraft(), handOff: null });
    await clickSubmit();
    cleanup();
    vi.unstubAllGlobals();
    stubFetch(signedIn("roleplayer"));
    await renderPage({ draft: validDraft(), handOff: null });
    await clickSubmit();
    await flush();
    expect(assignSpy.mock.calls.map(([url]) => url)).toEqual(["/", "/"]);
  });
});

// ---------------------------------------------------------------------------
describe("the invalid_credentials refusal", () => {
  it("renders one fixed message in the general alert and runs no hand-off — DoD-7 (US-005.AC-2)", async () => {
    stubFetch(invalidCredentials());
    const { draft, handOff } = await renderPage({ draft: validDraft() });
    await clickSubmit();

    const general = draft.serverErrors.general ?? "";
    expect(general).not.toBe("");
    expect(alerts().length).toBeGreaterThan(0);
    expect(alerts().some((el) => (el.textContent ?? "").includes(general))).toBe(true);
    expect(handOff).not.toHaveBeenCalled();
  });

  it("the rendered message is the same whatever prose the server sent — DoD-7", async () => {
    stubFetch(invalidCredentials("Server prose zq-alpha-81."));
    await renderPage({ draft: validDraft() });
    await clickSubmit();
    const first = alertText();
    cleanup();
    vi.unstubAllGlobals();

    stubFetch(invalidCredentials("Different prose zq-beta-82."));
    await renderPage({ draft: validDraft() });
    await clickSubmit();
    const second = alertText();

    expect(first).not.toBe("");
    expect(first).toBe(second);
    expect(pageText()).not.toContain("zq-beta-82");
  });

  it("leaves the form mounted and usable with the entered username preserved — DoD-7", async () => {
    stubFetch(invalidCredentials());
    const { draft } = await renderPage({ draft: validDraft() });
    await clickSubmit();
    expect(usernameInput().value).toBe(USERNAME);
    expect(draft.username).toBe(USERNAME);
    expect(passwordInput()).toBeInTheDocument();
    expect(submitControl()).toBeEnabled();
  });

  it("places no message on the username or password field — DoD-7", async () => {
    stubFetch(invalidCredentials());
    const { draft } = await renderPage({ draft: validDraft() });
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
    const { draft } = await renderPage({ draft: validDraft() });
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
    const { handOff } = await renderPage({ draft: validDraft() });
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
    await renderPage({ draft: validDraft(), handOff: null });
    await clickSubmit();
    await flush();
    expect(assignSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("a disabled account", () => {
  it("renders exactly as a wrong password does — same message, same place, same form — DoD-8 (US-006.AC-2, context.md D1)", async () => {
    stubFetch(invalidCredentials());
    const wrong = await renderPage({ draft: validDraft() });
    await clickSubmit();
    const wrongSnapshot = renderedFailureSnapshot();
    expect(wrong.handOff).not.toHaveBeenCalled();
    cleanup();
    vi.unstubAllGlobals();

    stubFetch(envelope("invalid_credentials", "This account is disabled zq-dis-1.", 400, { reason: "account_disabled" }));
    const disabled = await renderPage({ draft: validDraft() });
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
    const { draft, handOff } = await renderPage({ draft: validDraft() });
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
    await renderPage({ draft: validDraft() });
    await clickSubmit();
    await flush();
    expect(pageText()).not.toMatch(NOT_READY_TEXT);
    expect(document.querySelector('[data-entry="login"]')).not.toBeNull();
    expect(usernameInput()).toBeInTheDocument();
    expect(passwordInput()).toBeInTheDocument();
  });

  it("a general server error already on the draft renders as an inline alert — DoD-9", async () => {
    stubFetch(signedIn());
    const draft = validDraft();
    runInAction(() => {
      draft.serverErrors = { general: "Pre-set general zq-55." };
    });
    await renderPage({ draft });
    expect(alerts().some((el) => (el.textContent ?? "").includes("Pre-set general zq-55."))).toBe(true);
  });
});

// ---------------------------------------------------------------------------
describe("the password is never readable", () => {
  it("the password input is masked and the username input is not — DoD-10", async () => {
    stubFetch(signedIn());
    await renderPage({ draft: validDraft() });
    expect(passwordInput()).toHaveAttribute("type", "password");
    expect(usernameInput()).not.toHaveAttribute("type", "password");
  });

  it("no rendered text shows the password, and any input holding it is masked — DoD-10", async () => {
    stubFetch(signedIn());
    await renderPage({ draft: validDraft() });
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
    await renderPage({ draft: validDraft() });
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
    const { draft, handOff } = await renderPage({ draft: validDraft() });
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
// From fast/010 the mount issues the health probe; `fetchMock` here records only the requests
// other than `/api/health`, so these cases assert "no request beyond the probe" (010 DoD-7).
describe("no request on mount beyond the health probe", () => {
  it("rendering the page issues no request beyond the health probe — DoD-12", async () => {
    const fetchMock = stubFetch(signedIn());
    await renderPage();
    await flush();
    await renderPage({ draft: validDraft() });
    await flush();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(["/login", "/", "/login/deep/link"])(
    "mounting the login entry at %s issues no request beyond the health probe, in particular no /api/me — DoD-12",
    async (pathname) => {
      const fetchMock = stubFetch(signedIn());
      await mountLoginEntry(pathname);
      await flush();
      expect(fetchMock).not.toHaveBeenCalled();
      expect(fetchMock.mock.calls.some(([input]) => requestPath(input) === "/api/me")).toBe(false);
    },
  );

  it("the mounted entry issues its only non-probe request in response to a submit — DoD-12", async () => {
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
    await renderPage({ draft: validDraft() });
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
  it("the page carries the login entry marker exactly once, around the form — DoD-14", async () => {
    stubFetch(signedIn());
    await renderPage();
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

// ===========================================================================
// fast/010.unconfigured-to-bootstrap — the mount probe (DoD-1..DoD-6)
// ===========================================================================

describe("fast/010 — an unconfigured instance hands off to /bootstrap/", () => {
  it("the injected hand-off is called exactly once with /bootstrap/, and no form shows before or after (010 DoD-1)", async () => {
    const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    const pending = deferred<Response>();
    stubFetchRouted(signedIn(), () => pending.promise);
    const { handOff } = mountPage({ draft: validDraft() });
    await flush();

    expectNoForm();
    expect(handOff).not.toHaveBeenCalled();

    pending.resolve(jsonResponse(healthBody(false), 200));
    await flush();
    await flush();

    expect(handOff).toHaveBeenCalledTimes(1);
    expect(handOff).toHaveBeenCalledWith(BOOTSTRAP_URL);
    expect(assignSpy).not.toHaveBeenCalled();
    expectNoForm();
    expect(loginRoot()).not.toBeNull();
  });

  it("without a hand-off prop the document navigation goes to /bootstrap/, exactly once (010 DoD-1)", async () => {
    const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    const pending = deferred<Response>();
    stubFetchRouted(signedIn(), () => pending.promise);
    mountPage({ handOff: null });
    await flush();

    expectNoForm();
    expect(assignSpy).not.toHaveBeenCalled();

    pending.resolve(jsonResponse(healthBody(false), 200));
    await flush();
    await flush();

    expect(assignSpy).toHaveBeenCalledTimes(1);
    expect(assignSpy).toHaveBeenCalledWith(BOOTSTRAP_URL);
    expectNoForm();
  });

  it("a minimal { configured: false } body is enough to hand off (010 DoD-1)", async () => {
    stubFetchRouted(signedIn(), () => Promise.resolve(jsonResponse({ configured: false }, 200)));
    const { handOff } = await renderPage();
    await flush();
    expect(handOff).toHaveBeenCalledTimes(1);
    expect(handOff).toHaveBeenCalledWith(BOOTSTRAP_URL);
    expectNoForm();
  });
});

describe("fast/010 — a configured instance shows the form", () => {
  it("with configured: true the form shows after the probe and the injected hand-off never runs (010 DoD-2)", async () => {
    const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetchRouted(signedIn(), healthAnswer(true));
    const { handOff } = await renderPage();
    await flush();
    expectForm();
    expect(handOff).not.toHaveBeenCalled();
    expect(assignSpy).not.toHaveBeenCalled();
  });

  it("with configured: true and no hand-off prop, no document navigation happens (010 DoD-2)", async () => {
    const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetchRouted(signedIn(), () => Promise.resolve(jsonResponse({ configured: true }, 200)));
    await renderPage({ handOff: null });
    await flush();
    expectForm();
    expect(assignSpy).not.toHaveBeenCalled();
  });
});

describe("fast/010 — nothing in flight", () => {
  it("while /api/health is unresolved the root is present and shows no form (010 DoD-3)", async () => {
    const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetchRouted(signedIn(), () => new Promise<Response>(() => {}));
    const { handOff } = mountPage({ draft: validDraft() });
    await flush();

    const root = loginRoot();
    expect(root).not.toBeNull();
    expect(document.querySelectorAll('[data-entry="login"]')).toHaveLength(1);
    expectNoForm();
    expect((root?.textContent ?? "").trim()).toBe("");
    expect(handOff).not.toHaveBeenCalled();
    expect(assignSpy).not.toHaveBeenCalled();
  });

  it("the form is not shown even synchronously on the first render (010 DoD-3)", () => {
    stubFetchRouted(signedIn(), () => new Promise<Response>(() => {}));
    mountPage({ draft: validDraft() });
    expect(loginRoot()).not.toBeNull();
    expectNoForm();
  });
});

describe("fast/010 — a failed probe falls through to the form, once", () => {
  const FAILURES: [string, FetchFn][] = [
    ["fetch rejecting (transport failure)", () => Promise.reject(new TypeError("Failed to fetch"))],
    [
      "a 503 with a non-JSON body",
      () =>
        Promise.resolve(
          new Response("<html><body>503 Service Temporarily Unavailable</body></html>", {
            status: 503,
            headers: { "Content-Type": "text/html" },
          }),
        ),
    ],
    [
      "a 500 with a well-formed error envelope",
      () =>
        Promise.resolve(
          jsonResponse({ error: { code: "internal_error", message: "Health exploded zq-77.", detail: {} } }, 500),
        ),
    ],
    ["a 200 whose body lacks configured", () => Promise.resolve(jsonResponse({ status: "ok", schema: "ok" }, 200))],
    [
      "a 200 whose configured is the string \"false\"",
      () => Promise.resolve(jsonResponse({ status: "degraded", configured: "false", schema: "missing" }, 200)),
    ],
    [
      "a 200 whose configured is the number 0",
      () => Promise.resolve(jsonResponse({ status: "degraded", configured: 0, schema: "missing" }, 200)),
    ],
    [
      "a 200 whose configured is null",
      () => Promise.resolve(jsonResponse({ status: "degraded", configured: null, schema: "missing" }, 200)),
    ],
  ];

  it.each(FAILURES)(
    "%s leads to the form with no navigation, one probe only after 6000 ms, no not-ready text, no notification (010 DoD-4)",
    async (_name, health) => {
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
      const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
      const stub = stubFetchRouted(signedIn(), health);
      const { handOff } = mountPage({ draft: validDraft() });
      await flush();
      await flush();

      expectForm();
      expect(handOff).not.toHaveBeenCalled();
      expect(assignSpy).not.toHaveBeenCalled();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(6000);
      });
      await flush();

      expect(stub.health).toHaveBeenCalledTimes(1);
      expect(stub.all.mock.calls.filter(([input]) => requestPath(input) === HEALTH_PATH)).toHaveLength(1);
      expectForm();
      expect(handOff).not.toHaveBeenCalled();
      expect(assignSpy).not.toHaveBeenCalled();
      expect(pageText()).not.toMatch(NOT_READY_TEXT);
      expect(notifyFailureSpy).not.toHaveBeenCalled();
      expect(notificationRoots()).toEqual([]);
    },
  );

  it.each(FAILURES)("%s without a hand-off prop performs no document navigation (010 DoD-4)", async (_name, health) => {
    const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetchRouted(signedIn(), health);
    await renderPage({ handOff: null });
    await flush();
    expectForm();
    expect(assignSpy).not.toHaveBeenCalled();
  });
});

describe("fast/010 — abort on unmount", () => {
  function collectUnhandledRejections() {
    const seen: unknown[] = [];
    const onRejection = (reason: unknown) => {
      seen.push(reason);
    };
    process.on("unhandledRejection", onRejection);
    return {
      seen,
      stop: () => {
        process.off("unhandledRejection", onRejection);
      },
    };
  }

  /**
   * A probe answer the test settles by hand. The test's own promise gets a no-op catch, so a
   * rejection the page never consumes cannot surface as an unhandled rejection of the test's
   * making; any unhandled rejection seen is then the page's own chain.
   */
  function pendingProbe() {
    const pending = deferred<Response>();
    pending.promise.catch(() => {});
    return pending;
  }

  /** Before the unmount: exactly one GET /api/health has gone out and the page is still probing. */
  function expectProbeIssuedAndPending(stub: ReturnType<typeof stubFetchRouted>): void {
    expect(stub.all).toHaveBeenCalledTimes(1);
    expect(stub.health).toHaveBeenCalledTimes(1);
    const [input, init] = stub.all.mock.calls[0];
    expect(requestPath(input)).toBe(HEALTH_PATH);
    expect(requestMethod(input, init)).toBe("GET");
    // Still pending: the page has neither shown the form nor navigated.
    expect(loginRoot()).not.toBeNull();
    expectNoForm();
  }

  it.each<[string, (pending: ReturnType<typeof deferred<Response>>) => void]>([
    ["resolving with configured: false", (pending) => pending.resolve(jsonResponse(healthBody(false), 200))],
    [
      "rejecting with an abort",
      (pending) => pending.reject(new DOMException("The operation was aborted.", "AbortError")),
    ],
  ])(
    "unmounting while the probe is pending, then %s: no navigation, no rejection, no notification (010 DoD-5)",
    async (_name, settle) => {
      const rejections = collectUnhandledRejections();
      try {
        const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
        const pending = pendingProbe();
        const stub = stubFetchRouted(signedIn(), () => pending.promise);
        const { handOff, unmount } = mountPage({ draft: validDraft() });
        await flush();

        expectProbeIssuedAndPending(stub);
        expect(handOff).not.toHaveBeenCalled();

        expect(() => {
          act(() => {
            unmount();
          });
        }).not.toThrow();

        settle(pending);
        await flush();
        await flush();

        expect(handOff).not.toHaveBeenCalled();
        expect(assignSpy).not.toHaveBeenCalled();
        expect(notifyFailureSpy).not.toHaveBeenCalled();
        expect(rejections.seen).toEqual([]);
      } finally {
        rejections.stop();
      }
    },
  );

  it("unmounting while pending with the default hand-off performs no document navigation (010 DoD-5)", async () => {
    const rejections = collectUnhandledRejections();
    try {
      const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
      const pending = pendingProbe();
      const stub = stubFetchRouted(signedIn(), () => pending.promise);
      const { unmount } = mountPage({ handOff: null });
      await flush();
      expectProbeIssuedAndPending(stub);
      expect(assignSpy).not.toHaveBeenCalled();
      act(() => {
        unmount();
      });
      pending.resolve(jsonResponse(healthBody(false), 200));
      await flush();
      await flush();
      expect(assignSpy).not.toHaveBeenCalled();
      expect(notifyFailureSpy).not.toHaveBeenCalled();
      expect(rejections.seen).toEqual([]);
    } finally {
      rejections.stop();
    }
  });
});

describe("fast/010 — the probe is the only mount request", () => {
  it("on mount the page issues exactly one request, a GET to /api/health (010 DoD-6)", async () => {
    const stub = stubFetchRouted(signedIn(), healthAnswer(true));
    await renderPage({ draft: validDraft() });
    await flush();

    expect(stub.all).toHaveBeenCalledTimes(1);
    const [input, init] = stub.all.mock.calls[0];
    expect(requestPath(input)).toBe(HEALTH_PATH);
    expect(requestMethod(input, init)).toBe("GET");
    expect(stub.all.mock.calls.some(([call]) => requestPath(call) === "/api/me")).toBe(false);
    expect(stub.all.mock.calls.some(([call, callInit]) => requestMethod(call, callInit) === "POST")).toBe(false);
  });

  it("the probe is issued even while it stays pending, and nothing else is (010 DoD-6)", async () => {
    const stub = stubFetchRouted(signedIn(), () => new Promise<Response>(() => {}));
    mountPage();
    await flush();
    expect(stub.all).toHaveBeenCalledTimes(1);
    expect(requestPath(stub.all.mock.calls[0][0])).toBe(HEALTH_PATH);
    expect(requestMethod(stub.all.mock.calls[0][0], stub.all.mock.calls[0][1])).toBe("GET");
  });

  it.each(["/login", "/login/", "/"])(
    "mounting the login entry at %s issues exactly one GET /api/health and nothing else (010 DoD-6)",
    async (pathname) => {
      const stub = stubFetchRouted(signedIn(), healthAnswer(true));
      await mountLoginEntry(pathname);
      await flush();
      expect(stub.all).toHaveBeenCalledTimes(1);
      const [input, init] = stub.all.mock.calls[0];
      expect(requestPath(input)).toBe(HEALTH_PATH);
      expect(requestMethod(input, init)).toBe("GET");
    },
  );

  it("the first POST is issued only by the submit, after the probe (010 DoD-6)", async () => {
    const stub = stubFetchRouted(signedIn(), healthAnswer(true));
    await renderPage({ draft: validDraft() });
    expect(stub.all.mock.calls.some(([call, callInit]) => requestMethod(call, callInit) === "POST")).toBe(false);
    await clickSubmit();
    const methods = stub.all.mock.calls.map(([call, callInit]) => `${requestMethod(call, callInit)} ${requestPath(call)}`);
    expect(methods).toEqual([`GET ${HEALTH_PATH}`, "POST /api/auth/login"]);
  });
});
