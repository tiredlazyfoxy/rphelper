// fast/003 — bootstrap-from-export, the frontend half (DoD-13..DoD-19). DoD-20 is the verifier's
// suite gate (no new test); DoD-21 is [manual/live].
//
// Expected behaviour comes from `docs/plans/fast/003.bootstrap-from-export/plan.md` (Interface
// intent "Frontend" + Definition of done) and `context.md` (Decisions 3 and 4). Bindings come from
// the frozen `## Skeleton` record in that folder's `status.md`:
// - `src/bootstrap/restoreExport.ts` exports `RestoreExportState` (observable `file`,
//   `submitting`, `failureMessage`), `failureMessageOf(error)`, `chooseRestoreFile(state, file)`
//   and `submitRestoreExport(state, signal?, navigation?)`, where `navigation` is
//   `{ assign(url): void }` and defaults to `documentNavigation` from `src/shared/api`;
// - `src/bootstrap/RestoreExportForm.tsx` exports `RestoreExportForm({ state, navigation? })`;
// - `BootstrapPage.tsx` gains, in the offer phase, a second `List.Item` with the visible text
//   `Restore from an export` hosting the form (planned; the skeleton left the page unedited).
//
// Harness conventions (the existing bootstrap tests and the admin import tests):
// - `fetch` is stubbed per test and routed by method + pathname; health answers
//   `configured: false` so the page reaches the offer phase;
// - the file is chosen with `userEvent.upload` on the only `input[type="file"]` in the tree (the
//   create form has none), and the field's accessible label is checked separately;
// - `documentNavigation.assign` is spied, never allowed to navigate.
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { runInAction } from "mobx";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BootstrapPage } from "../../src/bootstrap/BootstrapPage";
import { BootstrapState } from "../../src/bootstrap/bootstrapState";
import { RestoreExportForm } from "../../src/bootstrap/RestoreExportForm";
import {
  chooseRestoreFile,
  failureMessageOf,
  RestoreExportState,
  submitRestoreExport,
} from "../../src/bootstrap/restoreExport";
import { documentNavigation } from "../../src/shared/api";
import { ApiError } from "../../src/shared/apiError";
import { AppProviders } from "../../src/shared/AppProviders";

const { notifyFailureSpy } = vi.hoisted(() => ({ notifyFailureSpy: vi.fn() }));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type User = ReturnType<typeof userEvent.setup>;
type Seen = { method: string; path: string; body: unknown };

// ---------------------------------------------------------------- the spec's names

const HEALTH_PATH = "/api/health";
const IMPORT_PATH = "/api/bootstrap/import";
const LOGIN_PATH = "/login";

const CREATE_CHOICE = "Create a new database";
const RESTORE_CHOICE = "Restore from an export";
const FILE_LABEL = /Export file/;
const RESTORE_BUTTON = "Restore database";

/** A 400 `export_invalid` as the backend's DomainError handler shapes it. */
const EXPORT_INVALID_MESSAGE = "That file is not a whole-database export (zq-303 marker).";

const NOTIFICATION_ROOT = ".mantine-Notification-root";

/** A whole-database envelope; the client posts the parsed object verbatim. */
const ENVELOPE = {
  format: "rphelper-export",
  version: 1,
  granularity: "database",
  created_at: "2026-10-07T10:11:12Z",
  schema_version: 1,
  payload: {
    users: [{ id: "7250000000000000101", username: "zqrestorer", role: "admin" }],
    characters: [{ id: "7250000000000000202", user_id: "7250000000000000101", name: "Quill" }],
  },
};

function exportFile(body: unknown = ENVELOPE): File {
  return new File([JSON.stringify(body)], "rphelper-database.json", { type: "application/json" });
}

function unreadableFile(): File {
  return new File(["this is not json at all {"], "rphelper-database.json", { type: "application/json" });
}

// ---------------------------------------------------------------- lifecycle

/** `documentNavigation.assign`, spied in `beforeEach` so jsdom never navigates. */
function assignSpy(): (url: string) => void {
  return documentNavigation.assign;
}

beforeEach(() => {
  notifyFailureSpy.mockClear();
  window.localStorage.clear();
  vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
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

// ---------------------------------------------------------------- the server

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

const restored = (): Promise<Response> => Promise.resolve(new Response(null, { status: 204 }));

const exportInvalid = (): Promise<Response> =>
  Promise.resolve(
    jsonResponse(
      { error: { code: "export_invalid", message: EXPORT_INVALID_MESSAGE, detail: { reason: "wrong_granularity" } } },
      400,
    ),
  );

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function serve(onImport: () => Promise<Response> = restored) {
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>((input, init) => {
    const url = requestUrl(input);
    const method = requestMethod(input, init);
    let body: unknown = null;
    if (typeof init?.body === "string") {
      try {
        body = JSON.parse(init.body);
      } catch {
        body = init.body;
      }
    }
    calls.push({ method, path: url.pathname, body });
    if (method === "GET" && url.pathname === HEALTH_PATH) {
      return Promise.resolve(jsonResponse({ status: "degraded", configured: false, schema: "missing" }, 200));
    }
    if (method === "POST" && url.pathname === IMPORT_PATH) {
      return onImport();
    }
    return Promise.resolve(
      jsonResponse({ error: { code: "not_found", message: `unexpected ${method} ${url.pathname}`, detail: {} } }, 404),
    );
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

function importCalls(calls: Seen[]): Seen[] {
  return calls.filter((call) => call.path === IMPORT_PATH);
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

async function renderOffer() {
  const state = new BootstrapState();
  render(
    <AppProviders>
      <MemoryRouter>
        <BootstrapPage state={state} />
      </MemoryRouter>
    </AppProviders>,
  );
  await flush();
  return { state };
}

function pageText(): string {
  return document.body.textContent ?? "";
}

function fileInput(): HTMLInputElement {
  const inputs = document.querySelectorAll<HTMLInputElement>('input[type="file"]');
  expect(inputs.length, "exactly one file input in the tree").toBe(1);
  return inputs[0];
}

function restoreButton(): HTMLElement {
  return screen.getByRole("button", { name: RESTORE_BUTTON });
}

async function chooseFile(user: User, file: File): Promise<void> {
  await user.upload(fileInput(), file);
  await flush();
}

async function pressRestore(user: User): Promise<void> {
  await user.click(restoreButton());
  await flush();
}

/**
 * The inline failure alerts. The environment notice may itself be a Mantine `Alert` (which
 * carries `role="alert"`), so it is told apart by its pinned copy and excluded.
 */
function alerts(): HTMLElement[] {
  return screen.queryAllByRole("alert").filter((el) => !(el.textContent ?? "").includes("API keys"));
}

function loginAnchors(): HTMLAnchorElement[] {
  return Array.from(document.querySelectorAll<HTMLAnchorElement>("a")).filter(
    (a) => a.getAttribute("href") === LOGIN_PATH,
  );
}

function notificationRoots(): Element[] {
  return Array.from(document.querySelectorAll(NOTIFICATION_ROOT));
}

// ===========================================================================================
// DoD-13 — both choices render in the offer phase.
describe("the offer phase", () => {
  it("renders both choices: create a new database and restore from an export — DoD-13", async () => {
    serve();
    await renderOffer();
    expect(pageText()).toContain(CREATE_CHOICE);
    expect(pageText()).toContain(RESTORE_CHOICE);
    expect(screen.getAllByText(RESTORE_CHOICE)[0]).toBeVisible();
  });

  it("the restore choice hosts the file input and the restore button — DoD-13", async () => {
    serve();
    await renderOffer();
    expect(fileInput()).toBeInTheDocument();
    expect(restoreButton()).toBeInTheDocument();
    // Existing offer-phase guards: no /login anchor, restore controls not named "create".
    expect(loginAnchors()).toEqual([]);
    expect(restoreButton().textContent ?? "").not.toMatch(/create/i);
  });
});

// ===========================================================================================
// DoD-14 — the environment notice.
describe("the environment notice", () => {
  it("is visible before any file is chosen and names API keys and .env — DoD-14", async () => {
    const { calls } = serve();
    await renderOffer();
    const notice = screen.getAllByText(/API keys/)[0];
    expect(notice).toBeVisible();
    expect(pageText()).toContain("API keys");
    expect(pageText()).toContain(".env");
    expect(importCalls(calls)).toHaveLength(0);
  });

  it("is static copy on the form itself, present with no file chosen — DoD-14", () => {
    serve();
    render(
      <AppProviders>
        <RestoreExportForm state={new RestoreExportState()} navigation={{ assign: vi.fn() }} />
      </AppProviders>,
    );
    const text = document.body.textContent ?? "";
    expect(text).toContain("API keys");
    expect(text).toContain(".env");
    // Offer-phase guard (status.md Notes): the notice must not read as the not-ready state.
    expect(text).not.toMatch(/starting|not ready/i);
  });
});

// ===========================================================================================
// DoD-15 — the button is disabled until a file is chosen.
describe("the Restore database button", () => {
  it("the file field carries the accessible label Export file and accepts .json — DoD-15", async () => {
    serve();
    await renderOffer();
    expect(screen.getAllByLabelText(FILE_LABEL).length).toBeGreaterThan(0);
    expect(fileInput().getAttribute("accept") ?? "").toContain(".json");
  });

  it("is disabled until a file is chosen, then enabled — DoD-15", async () => {
    serve();
    await renderOffer();
    expect(restoreButton()).toBeDisabled();
    const user = newUser();
    await chooseFile(user, exportFile());
    expect(restoreButton()).toBeEnabled();
  });

  it("chooseRestoreFile stores the file and clears a previous failure — DoD-15", () => {
    const state = new RestoreExportState();
    runInAction(() => {
      state.failureMessage = "a stale failure (zq-404 marker)";
    });
    const file = exportFile();
    act(() => {
      chooseRestoreFile(state, file);
    });
    expect(state.file).toBe(file);
    expect(state.failureMessage).toBeNull();
  });
});

// ===========================================================================================
// DoD-16 — the upload and the hand-off.
describe("a successful restore", () => {
  it("sends exactly one POST /api/bootstrap/import whose body is the file's parsed contents — DoD-16", async () => {
    const { calls } = serve();
    await renderOffer();
    const user = newUser();
    await chooseFile(user, exportFile());
    await pressRestore(user);

    const posted = importCalls(calls);
    expect(posted).toHaveLength(1);
    expect(posted[0].method).toBe("POST");
    expect(posted[0].body).toEqual(ENVELOPE);
    expect(calls.filter((call) => call.method === "POST")).toHaveLength(1);
  });

  it("on a 204 calls documentNavigation.assign('/login') once — DoD-16", async () => {
    serve();
    await renderOffer();
    const user = newUser();
    await chooseFile(user, exportFile());
    await pressRestore(user);
    expect(assignSpy()).toHaveBeenCalledTimes(1);
    expect(assignSpy()).toHaveBeenCalledWith(LOGIN_PATH);
    expect(alerts()).toEqual([]);
  });

  it("submitRestoreExport posts the parsed file and hands off to /login through the seam — DoD-16", async () => {
    const { calls } = serve();
    const state = new RestoreExportState();
    act(() => {
      chooseRestoreFile(state, exportFile());
    });
    const navigation = { assign: vi.fn<(url: string) => void>() };
    await act(async () => {
      await submitRestoreExport(state, new AbortController().signal, navigation);
    });
    expect(importCalls(calls)).toHaveLength(1);
    expect(importCalls(calls)[0].body).toEqual(ENVELOPE);
    expect(navigation.assign).toHaveBeenCalledTimes(1);
    expect(navigation.assign).toHaveBeenCalledWith(LOGIN_PATH);
    expect(state.failureMessage).toBeNull();
    expect(state.submitting).toBe(false);
  });
});

// ===========================================================================================
// DoD-17 — disabled while in flight.
describe("while the request is pending", () => {
  it("the Restore database button is disabled — DoD-17", async () => {
    const pending = deferred<Response>();
    const { calls } = serve(() => pending.promise);
    await renderOffer();
    const user = newUser();
    await chooseFile(user, exportFile());
    await pressRestore(user);

    expect(importCalls(calls)).toHaveLength(1);
    expect(restoreButton()).toBeDisabled();

    pending.resolve(new Response(null, { status: 204 }));
    await flush();
    expect(assignSpy()).toHaveBeenCalledWith(LOGIN_PATH);
  });

  it("the state's in-flight flag is set for the duration of the submit — DoD-17", async () => {
    const pending = deferred<Response>();
    serve(() => pending.promise);
    const state = new RestoreExportState();
    act(() => {
      chooseRestoreFile(state, exportFile());
    });
    const navigation = { assign: vi.fn<(url: string) => void>() };
    let running: Promise<void> = Promise.resolve();
    act(() => {
      running = submitRestoreExport(state, new AbortController().signal, navigation);
    });
    await flush();
    expect(state.submitting).toBe(true);

    pending.resolve(new Response(null, { status: 204 }));
    await act(async () => {
      await running;
    });
    expect(state.submitting).toBe(false);
  });

  it("a form whose state is in flight renders the button disabled even with a file — DoD-17", () => {
    serve();
    const state = new RestoreExportState();
    chooseRestoreFile(state, exportFile());
    runInAction(() => {
      state.submitting = true;
    });
    render(
      <AppProviders>
        <RestoreExportForm state={state} navigation={{ assign: vi.fn() }} />
      </AppProviders>,
    );
    expect(restoreButton()).toBeDisabled();
  });
});

// ===========================================================================================
// DoD-18 — a 400 export_invalid shows an inline alert and does not navigate.
describe("an export_invalid answer", () => {
  it("shows an inline alert carrying failureMessageOf's text and does not navigate — DoD-18", async () => {
    serve(exportInvalid);
    await renderOffer();
    const user = newUser();
    await chooseFile(user, exportFile());
    await pressRestore(user);

    const expected = failureMessageOf(
      new ApiError("export_invalid", EXPORT_INVALID_MESSAGE, 400, { reason: "wrong_granularity" }),
    );
    expect(expected.length).toBeGreaterThan(0);
    const shown = alerts();
    expect(shown.length).toBeGreaterThan(0);
    expect(shown.some((el) => (el.textContent ?? "").includes(expected))).toBe(true);
    expect(assignSpy()).not.toHaveBeenCalled();
  });

  it("the failure is inline, never a notification — DoD-18", async () => {
    serve(exportInvalid);
    await renderOffer();
    const user = newUser();
    await chooseFile(user, exportFile());
    await pressRestore(user);
    expect(alerts().length).toBeGreaterThan(0);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(notificationRoots()).toEqual([]);
  });

  it("submitRestoreExport stores failureMessageOf(error) and does not navigate — DoD-18", async () => {
    serve(exportInvalid);
    const state = new RestoreExportState();
    act(() => {
      chooseRestoreFile(state, exportFile());
    });
    const navigation = { assign: vi.fn<(url: string) => void>() };
    await act(async () => {
      await submitRestoreExport(state, new AbortController().signal, navigation);
    });
    const expected = failureMessageOf(
      new ApiError("export_invalid", EXPORT_INVALID_MESSAGE, 400, { reason: "wrong_granularity" }),
    );
    expect(state.failureMessage).toBe(expected);
    expect(navigation.assign).not.toHaveBeenCalled();
    expect(state.submitting).toBe(false);
  });

  it("choosing another file afterwards clears the alert — DoD-18", async () => {
    serve(exportInvalid);
    await renderOffer();
    const user = newUser();
    await chooseFile(user, exportFile());
    await pressRestore(user);
    expect(alerts().length).toBeGreaterThan(0);
    await chooseFile(user, exportFile({ ...ENVELOPE, created_at: "2026-10-07T11:00:00Z" }));
    expect(alerts()).toEqual([]);
  });
});

// ===========================================================================================
// DoD-19 — an unreadable file shows an inline alert, sends nothing, does not navigate.
describe("a file that is not valid JSON", () => {
  it("shows an inline alert, sends no request and does not navigate — DoD-19", async () => {
    const { calls } = serve();
    await renderOffer();
    const user = newUser();
    await chooseFile(user, unreadableFile());
    await pressRestore(user);

    expect(alerts().length).toBeGreaterThan(0);
    expect(importCalls(calls)).toHaveLength(0);
    expect(calls.filter((call) => call.method === "POST")).toHaveLength(0);
    expect(assignSpy()).not.toHaveBeenCalled();
    expect(notificationRoots()).toEqual([]);
  });

  it("submitRestoreExport stores a failure message and sends nothing — DoD-19", async () => {
    const { calls } = serve();
    const state = new RestoreExportState();
    act(() => {
      chooseRestoreFile(state, unreadableFile());
    });
    const navigation = { assign: vi.fn<(url: string) => void>() };
    await act(async () => {
      await submitRestoreExport(state, new AbortController().signal, navigation);
    });
    expect(typeof state.failureMessage).toBe("string");
    expect((state.failureMessage ?? "").length).toBeGreaterThan(0);
    expect(importCalls(calls)).toHaveLength(0);
    expect(navigation.assign).not.toHaveBeenCalled();
    expect(state.submitting).toBe(false);
  });
});
