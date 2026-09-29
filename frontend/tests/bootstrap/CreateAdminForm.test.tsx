// Feature 003, step 005 — the create-administrator form, its submit path, the hand-off to
// `/login`, and the refusal flip on the page (DoD-3..DoD-10). DoD-11..DoD-13 are [manual/live].
//
// The form is rendered with its store and draft passed explicitly as props (context.md D13),
// wrapped in AppProviders. `fetch` is stubbed per test; `notifyFailure` is mocked at file level.
// Fields are found by their visible labels; the page's states by what the spec says they show.
import { readFileSync } from "node:fs";
import path from "node:path";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { runInAction } from "mobx";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BootstrapPage } from "../../src/bootstrap/BootstrapPage";
import { BootstrapState, bootstrapPhase } from "../../src/bootstrap/bootstrapState";
import { CreateAdminForm } from "../../src/bootstrap/CreateAdminForm";
import { CreateAdminDraft, submitCreateAdmin } from "../../src/bootstrap/createAdminDraft";
import { documentNavigation } from "../../src/shared/api";
import { AppProviders } from "../../src/shared/AppProviders";

const { notifyFailureSpy } = vi.hoisted(() => ({ notifyFailureSpy: vi.fn() }));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type HandOff = (url: string) => void;

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const SRC_ROOT = path.join(FRONTEND_ROOT, "src");

const USERNAME = "operator-admin";
const PASSWORD = "Tq9-correct-horse-zq";
const FAILURE_MESSAGE = "Creation exploded zq-42.";
const NOTIFICATION_ROOT = ".mantine-Notification-root";

/** The refusal states the instance is already configured (UC-003). */
const REFUSAL_TEXT = /already configured/i;
const USERNAME_LABEL = /user\s*name/i;
const CONFIRMATION_LABEL = /confirm|repeat/i;
const PASSWORD_LABEL = /password/i;

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

const created = () =>
  Promise.resolve(jsonResponse({ id: "7340032000000001", username: USERNAME, role: "admin" }, 201));

const alreadyConfigured = () =>
  Promise.resolve(
    jsonResponse(
      { error: { code: "already_configured", message: "This instance is already configured.", detail: {} } },
      409,
    ),
  );

const backendFailure = () =>
  Promise.resolve(jsonResponse({ error: { code: "internal_error", message: FAILURE_MESSAGE, detail: {} } }, 500));

const transportFailure = () => Promise.reject(new TypeError("Failed to fetch"));

const fastApi422 = () =>
  Promise.resolve(
    jsonResponse({ detail: [{ type: "string_too_short", loc: ["body", "username"], msg: "too short", input: "" }] }, 422),
  );

const healthUnconfigured = () =>
  Promise.resolve(jsonResponse({ status: "degraded", configured: false, schema: "missing" }, 200));

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

function createCalls(fetchMock: ReturnType<typeof stubFetch>) {
  return fetchMock.mock.calls.filter(([input]) => requestPath(input) === "/api/bootstrap/create");
}

function offerState(): BootstrapState {
  const state = new BootstrapState();
  runInAction(() => {
    state.phase = "offer";
  });
  return state;
}

function fillDraft(draft: CreateAdminDraft, fields: { username: string; password: string; confirmation: string }) {
  runInAction(() => {
    draft.username = fields.username;
    draft.password = fields.password;
    draft.confirmation = fields.confirmation;
  });
}

function validDraft(): CreateAdminDraft {
  const draft = new CreateAdminDraft();
  fillDraft(draft, { username: USERNAME, password: PASSWORD, confirmation: PASSWORD });
  return draft;
}

function renderForm(options: { state?: BootstrapState; draft?: CreateAdminDraft; handOff?: HandOff | null } = {}) {
  const state = options.state ?? offerState();
  const draft = options.draft ?? new CreateAdminDraft();
  const handOff = options.handOff === undefined ? vi.fn<HandOff>() : options.handOff;
  const view = render(
    <AppProviders>
      {handOff === null ? (
        <CreateAdminForm state={state} draft={draft} />
      ) : (
        <CreateAdminForm state={state} draft={draft} handOff={handOff} />
      )}
    </AppProviders>,
  );
  return { state, draft, handOff, ...view };
}

function usernameInput(): HTMLInputElement {
  return screen.getByLabelText(USERNAME_LABEL) as HTMLInputElement;
}

function confirmationInput(): HTMLInputElement {
  return screen.getByLabelText(CONFIRMATION_LABEL) as HTMLInputElement;
}

function passwordInput(): HTMLInputElement {
  const confirmation = confirmationInput();
  const candidates = screen.getAllByLabelText(PASSWORD_LABEL).filter((el) => el !== confirmation);
  expect(candidates).toHaveLength(1);
  return candidates[0] as HTMLInputElement;
}

function formElement(): HTMLFormElement {
  const form = document.querySelector("form");
  if (form === null) throw new Error("no <form> rendered");
  return form;
}

function submitControl(): HTMLElement {
  const controls = formElement().querySelectorAll<HTMLElement>('button[type="submit"], input[type="submit"]');
  expect(controls).toHaveLength(1);
  return controls[0];
}

function pageText(): string {
  return document.body.textContent ?? "";
}

function alerts(): HTMLElement[] {
  return screen.queryAllByRole("alert");
}

function loginAnchors(): HTMLAnchorElement[] {
  return Array.from(document.querySelectorAll<HTMLAnchorElement>("a")).filter(
    (a) => a.getAttribute("href") === "/login",
  );
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

async function clickSubmit(): Promise<void> {
  act(() => {
    fireEvent.click(submitControl());
  });
  await flush();
}

// ---------------------------------------------------------------------------
describe("the submit control", () => {
  it("is disabled for an empty draft — DoD-3", () => {
    stubFetch(created);
    renderForm();
    expect(submitControl()).toBeDisabled();
  });

  it.each<[string, { username: string; password: string; confirmation: string }]>([
    ["a whitespace-only username", { username: "   ", password: PASSWORD, confirmation: PASSWORD }],
    ["an empty password", { username: USERNAME, password: "", confirmation: "" }],
    ["a mismatched confirmation", { username: USERNAME, password: PASSWORD, confirmation: `${PASSWORD}!` }],
  ])("is disabled for %s — DoD-3", (_name, fields) => {
    stubFetch(created);
    const draft = new CreateAdminDraft();
    fillDraft(draft, fields);
    renderForm({ draft });
    expect(submitControl()).toBeDisabled();
  });

  it("is enabled for a valid draft with no submit in flight — DoD-3", () => {
    stubFetch(created);
    renderForm({ draft: validDraft() });
    expect(submitControl()).toBeEnabled();
  });

  it("is disabled while the draft marks a submit in flight — DoD-3", () => {
    stubFetch(created);
    const draft = validDraft();
    runInAction(() => {
      draft.submitting = true;
    });
    renderForm({ draft });
    expect(submitControl()).toBeDisabled();
  });

  it("clicking an invalid form issues no request — DoD-3", async () => {
    const fetchMock = stubFetch(created);
    renderForm();
    act(() => {
      fireEvent.click(submitControl());
      fireEvent.submit(formElement());
    });
    await flush();
    expect(createCalls(fetchMock)).toHaveLength(0);
  });

  it("is disabled while a submit is in flight, and a second activation issues no second request — DoD-3", async () => {
    const pending = deferred<Response>();
    const fetchMock = stubFetch(() => pending.promise);
    const { handOff } = renderForm({ draft: validDraft() });
    await clickSubmit();
    expect(createCalls(fetchMock)).toHaveLength(1);
    expect(submitControl()).toBeDisabled();

    act(() => {
      fireEvent.click(submitControl());
      fireEvent.submit(formElement());
    });
    await flush();
    expect(createCalls(fetchMock)).toHaveLength(1);

    pending.resolve(await created());
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(handOff).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
describe("a successful submit", () => {
  it("typing into the form and submitting posts exactly the username and password — DoD-4 (US-001.AC-1)", async () => {
    const fetchMock = stubFetch(created);
    const user = userEvent.setup();
    renderForm();
    await user.type(usernameInput(), USERNAME);
    await user.type(passwordInput(), PASSWORD);
    await user.type(confirmationInput(), PASSWORD);
    await user.click(submitControl());
    await flush();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [input, init] = fetchMock.mock.calls[0];
    expect(requestPath(input)).toBe("/api/bootstrap/create");
    expect(requestMethod(input, init)).toBe("POST");
    expect(requestJson(init)).toEqual({ username: USERNAME, password: PASSWORD });
  });

  it("the request body carries no role, no id and no confirmation — DoD-4", async () => {
    const fetchMock = stubFetch(created);
    renderForm({ draft: validDraft() });
    await clickSubmit();
    const keys = Object.keys(requestJson(fetchMock.mock.calls[0][1]) as Record<string, unknown>);
    expect(keys.sort()).toEqual(["password", "username"]);
  });

  it("runs the hand-off once, targeting /login — DoD-5", async () => {
    stubFetch(created);
    const { handOff } = renderForm({ draft: validDraft() });
    await clickSubmit();
    await flush();
    expect(handOff).toHaveBeenCalledTimes(1);
    expect(handOff).toHaveBeenCalledWith("/login");
  });

  it("without a hand-off prop the default is the document navigation to /login, once — DoD-5", async () => {
    const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(created);
    renderForm({ draft: validDraft(), handOff: null });
    await clickSubmit();
    await flush();
    expect(assignSpy).toHaveBeenCalledTimes(1);
    expect(assignSpy).toHaveBeenCalledWith("/login");
  });

  it("success does not flip the page to the refusal — DoD-5", async () => {
    stubFetch(created);
    const { state } = renderForm({ draft: validDraft() });
    await clickSubmit();
    expect(bootstrapPhase(state)).toBe("offer");
  });
});

// ---------------------------------------------------------------------------
describe("an already_configured answer", () => {
  it("the form flips the store to the refusal phase and does not hand off — DoD-6 (US-003.AC-1)", async () => {
    stubFetch(alreadyConfigured);
    const { state, draft, handOff } = renderForm({ draft: validDraft() });
    await clickSubmit();
    expect(bootstrapPhase(state)).toBe("refusal");
    expect(handOff).not.toHaveBeenCalled();
    expect(draft.serverErrors).toEqual({});
  });

  it("on the page, the refusal and its sign-in link render and the form is gone — DoD-6 (US-003.AC-1, US-003.AC-2)", async () => {
    const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    const fetchMock = stubFetch((input) =>
      requestPath(input) === "/api/bootstrap/create" ? alreadyConfigured() : healthUnconfigured(),
    );
    const user = userEvent.setup();
    const state = new BootstrapState();
    render(
      <AppProviders>
        <MemoryRouter>
          <BootstrapPage state={state} />
        </MemoryRouter>
      </AppProviders>,
    );
    await flush();
    expect(pageText()).not.toMatch(REFUSAL_TEXT);

    await user.type(usernameInput(), USERNAME);
    await user.type(passwordInput(), PASSWORD);
    await user.type(confirmationInput(), PASSWORD);
    await user.click(submitControl());
    await flush();

    expect(createCalls(fetchMock)).toHaveLength(1);
    expect(bootstrapPhase(state)).toBe("refusal");
    expect(pageText()).toMatch(REFUSAL_TEXT);
    expect(loginAnchors().length).toBeGreaterThan(0);
    expect(document.querySelectorAll("form, input, textarea, select").length).toBe(0);
    expect(document.querySelectorAll('button[type="submit"], input[type="submit"]').length).toBe(0);
    expect(assignSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("any other failure renders in place", () => {
  it.each<[string, () => Promise<Response>]>([
    ["a backend error envelope", backendFailure],
    ["a transport failure", transportFailure],
    ["FastAPI's own 422", fastApi422],
  ])("%s shows the general inline alert and keeps the form usable — DoD-7", async (_name, handler) => {
    const fetchMock = stubFetch(handler);
    const { state, draft, handOff } = renderForm({ draft: validDraft() });
    await clickSubmit();

    expect(alerts().length).toBeGreaterThan(0);
    expect(bootstrapPhase(state)).toBe("offer");
    expect(handOff).not.toHaveBeenCalled();
    expect(formElement()).toBeInTheDocument();
    expect(usernameInput().value).toBe(USERNAME);
    expect(draft.username).toBe(USERNAME);
    expect(submitControl()).toBeEnabled();
    expect(createCalls(fetchMock)).toHaveLength(1);
  });

  it("the form can be submitted again after a failure — DoD-7", async () => {
    let calls = 0;
    const fetchMock = stubFetch(() => {
      calls += 1;
      return calls === 1 ? backendFailure() : created();
    });
    const { handOff } = renderForm({ draft: validDraft() });
    await clickSubmit();
    expect(alerts().length).toBeGreaterThan(0);
    await clickSubmit();
    expect(createCalls(fetchMock)).toHaveLength(2);
    expect(handOff).toHaveBeenCalledTimes(1);
    expect(handOff).toHaveBeenCalledWith("/login");
  });

  it("a general server error already on the draft renders as an inline alert — DoD-7", () => {
    stubFetch(created);
    const draft = validDraft();
    runInAction(() => {
      draft.serverErrors = { general: FAILURE_MESSAGE };
    });
    renderForm({ draft });
    const shown = alerts();
    expect(shown.length).toBeGreaterThan(0);
    expect(shown.some((el) => (el.textContent ?? "").includes(FAILURE_MESSAGE))).toBe(true);
  });

  it("a username server error on the draft renders on the username field, not in the general alert — DoD-7", () => {
    stubFetch(created);
    const draft = validDraft();
    const fieldMessage = "That username is refused zq-71.";
    runInAction(() => {
      draft.serverErrors = { username: fieldMessage };
    });
    renderForm({ draft });
    expect(pageText()).toContain(fieldMessage);
    expect(usernameInput()).toHaveAttribute("aria-invalid", "true");
    expect(describedText(usernameInput())).toContain(fieldMessage);
  });

  it("a password server error on the draft renders on the password field — DoD-7", () => {
    stubFetch(created);
    const draft = validDraft();
    const fieldMessage = "That password is refused zq-72.";
    runInAction(() => {
      draft.serverErrors = { password: fieldMessage };
    });
    renderForm({ draft });
    expect(pageText()).toContain(fieldMessage);
    expect(passwordInput()).toHaveAttribute("aria-invalid", "true");
    expect(describedText(passwordInput())).toContain(fieldMessage);
  });
});

// ---------------------------------------------------------------------------
describe("the password is never readable", () => {
  it("the password and confirmation inputs are masked — DoD-8", () => {
    stubFetch(created);
    renderForm({ draft: validDraft() });
    expect(passwordInput()).toHaveAttribute("type", "password");
    expect(confirmationInput()).toHaveAttribute("type", "password");
    expect(usernameInput()).not.toHaveAttribute("type", "password");
  });

  it("no unmasked input and no rendered text shows the password or a mismatched confirmation — DoD-8", () => {
    stubFetch(created);
    const draft = new CreateAdminDraft();
    const confirmation = "Tq9-mistyped-horse-zq";
    fillDraft(draft, { username: USERNAME, password: PASSWORD, confirmation });
    renderForm({ draft });
    expect(pageText()).not.toContain(PASSWORD);
    expect(pageText()).not.toContain(confirmation);
    for (const input of Array.from(document.querySelectorAll("input"))) {
      if (input.value === PASSWORD || input.value === confirmation) {
        expect(input).toHaveAttribute("type", "password");
      }
    }
  });

  it.each<[string, () => Promise<Response>]>([
    ["a backend error envelope", backendFailure],
    ["a transport failure", transportFailure],
    ["FastAPI's own 422", fastApi422],
  ])("after %s neither value appears in the general error shown — DoD-8", async (_name, handler) => {
    stubFetch(handler);
    renderForm({ draft: validDraft() });
    await clickSubmit();
    const shown = alerts();
    expect(shown.length).toBeGreaterThan(0);
    for (const el of shown) {
      expect(el.textContent ?? "").not.toContain(PASSWORD);
    }
    expect(pageText()).not.toContain(PASSWORD);
  });
});

// ---------------------------------------------------------------------------
describe("an aborted submit", () => {
  it("renders no failure — DoD-9", async () => {
    stubFetch(backendFailure);
    const { draft, state, handOff } = renderForm({ draft: validDraft() });
    const controller = new AbortController();
    controller.abort();
    await act(async () => {
      await submitCreateAdmin(draft, controller.signal);
    });
    await flush();
    expect(draft.serverErrors).toEqual({});
    expect(alerts()).toEqual([]);
    expect(pageText()).not.toContain(FAILURE_MESSAGE);
    expect(bootstrapPhase(state)).toBe("offer");
    expect(handOff).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("no notification anywhere in the form", () => {
  it.each<[string, () => Promise<Response>]>([
    ["created", created],
    ["refused", alreadyConfigured],
    ["a backend failure", backendFailure],
    ["a transport failure", transportFailure],
    ["FastAPI's own 422", fastApi422],
  ])("submitting (%s) calls notifyFailure nowhere and renders no notification — DoD-10", async (_name, handler) => {
    stubFetch(handler);
    renderForm({ draft: validDraft() });
    await clickSubmit();
    await flush();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(notificationRoots()).toEqual([]);
  });

  it("neither of this step's new modules imports notifyFailure — DoD-10", () => {
    const offenders = ["createAdminDraft.ts", "CreateAdminForm.tsx"].flatMap((name) =>
      importSpecifiers(readFileSync(path.join(SRC_ROOT, "bootstrap", name), "utf8"))
        .filter((spec) => /notifyFailure|@mantine\/notifications/.test(spec))
        .map((spec) => `${name} imports ${spec}`),
    );
    expect(offenders).toEqual([]);
  });
});
