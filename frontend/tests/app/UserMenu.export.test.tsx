// Feature 030 — export-granularities, step 006: the user menu's "Export my data" item
// (DoD-3, and DoD-7 / DoD-8 for this control). The module's own clauses live in
// `exportDownloads.test.ts`; the other two controls have their own files. DoD-9 and DoD-10 are
// [manual/live] and carry no test.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 006.context.md and the feature context.md: the item is shown to every role, choosing it
// requests the own-data export route, there is no success toast (the browser's download is the
// signal), a failure in the `app` entry goes through `notifyFailure`, and an export opens no
// confirm dialog because it is not lossy. Bindings come from the frozen `### Step 006` record:
// the item's accessible name is exactly `Export my data`, and the route is `GET /api/export`
// (context.md "Routes").
//
// Harness conventions (006.context.md, 004.context.md):
// - The menu renders inside `AppProviders` + `MemoryRouter`, so the notifications outlet exists
//   and "nothing was notified" / "one notification carrying the message" are both observable
//   through `.mantine-Notification-root`. `notifyFailure` is deliberately NOT mocked here: the
//   clause is about what the user is shown, so the real channel is exercised end to end.
// - `fetch` is stubbed per test with `vi.stubGlobal` and routed by **exact pathname**; nothing
//   else is answered, so a stray request is visible.
// - `apiDownload` runs for real, so jsdom's missing `URL.createObjectURL` / `URL.revokeObjectURL`
//   are installed per test and removed afterwards, and the anchor click is swallowed by a spy on
//   `HTMLAnchorElement.prototype.click` so jsdom never navigates.
// - Menus are driven with `userEvent.setup({ pointerEventsCheck: 0 })` and accessible names —
//   `tests/app/UserMenu.test.tsx`'s pattern.
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CharactersState } from "../../src/app/charactersState";
import { SessionsState } from "../../src/app/sessionsState";
import { UserMenu } from "../../src/app/UserMenu";
import { documentNavigation } from "../../src/shared/api";
import { AppProviders } from "../../src/shared/AppProviders";
import type { CurrentUser } from "../../src/shared/currentUser";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string };
type User = ReturnType<typeof userEvent.setup>;

// ---------------------------------------------------------------- the spec's names
const TRIGGER_NAME = /^user menu$/i;
const EXPORT_ITEM = /^export my data$/i;
const LOGOUT_ITEM = /^log out$/i;

/** context.md "Routes" — the own-data export, scoped server-side to the caller. */
const EXPORT_PATH = "/api/export";
const EXPORT_FILENAME = "rphelper-user-20260105T101112Z.json";

const NOTIFICATION = ".mantine-Notification-root";

/** The message the error envelope carries; a notification must show it (DoD-7). */
const FAILURE_MESSAGE = "The export could not be produced (zq-71 marker).";

/**
 * Words a success report would use. Success is silent (context.md "No success toasts"), so none
 * of them may appear anywhere on screen after a successful export.
 */
const SUCCESS_TALK = /\b(success|succeeded|successfully|downloaded|exported|completed|finished)\b/i;

const ROLES: Array<CurrentUser["role"]> = ["roleplayer", "admin"];

// ---------------------------------------------------------------- jsdom gaps
let hadCreateObjectUrl: boolean;
let hadRevokeObjectUrl: boolean;

beforeEach(() => {
  let issued = 0;

  hadCreateObjectUrl = typeof URL.createObjectURL === "function";
  hadRevokeObjectUrl = typeof URL.revokeObjectURL === "function";
  URL.createObjectURL = (): string => {
    issued += 1;
    return `blob:rphelper/${issued}`;
  };
  URL.revokeObjectURL = (): void => {};

  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
});

afterEach(() => {
  if (!hadCreateObjectUrl) Reflect.deleteProperty(URL, "createObjectURL");
  if (!hadRevokeObjectUrl) Reflect.deleteProperty(URL, "revokeObjectURL");
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- fetch harness
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

/** A domain envelope — the shape every non-2xx of ours carries. */
function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: FAILURE_MESSAGE, detail: {} } }, status);
}

/** What an export route answers: a JSON attachment with the feature's filename shape. */
function exportResponse(): Response {
  return new Response('{"format":"rphelper-export","granularity":"user","payload":{}}', {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Content-Disposition": `attachment; filename="${EXPORT_FILENAME}"`,
    },
  });
}

/** Routes by exact pathname: the export route only; anything else is a visible 404. */
function stubBackend(options: { failExport?: boolean } = {}) {
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>((input, init) => {
    const url = requestUrl(input);
    const method = requestMethod(input, init);
    calls.push({ method, path: url.pathname, search: url.search });
    if (method === "GET" && url.pathname === EXPORT_PATH) {
      return Promise.resolve(options.failExport === true ? envelope("internal_error", 500) : exportResponse());
    }
    return Promise.resolve(envelope("not_found", 404));
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

function exportRequests(calls: Seen[]): Seen[] {
  return calls.filter((call) => call.method === "GET" && call.path === EXPORT_PATH);
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
function identity(role: CurrentUser["role"]): CurrentUser {
  return { id: "9007199254740993", username: "zmiraqua", role };
}

function renderMenu(role: CurrentUser["role"]) {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={["/"]}>
        <UserMenu
          user={identity(role)}
          compact={false}
          charactersState={new CharactersState()}
          sessionsState={new SessionsState()}
        />
      </MemoryRouter>
    </AppProviders>,
  );
}

// ---------------------------------------------------------------- queries
function trigger(): HTMLElement {
  return screen.getByRole("button", { name: TRIGGER_NAME });
}

/** Opens the dropdown (a portal, mounted only while open) and waits for its content. */
async function openMenu(user: User): Promise<void> {
  await user.click(trigger());
  await screen.findByText(LOGOUT_ITEM);
}

async function exportItem(): Promise<HTMLElement> {
  return await screen.findByRole("menuitem", { name: EXPORT_ITEM });
}

function notificationRoots(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>(NOTIFICATION));
}

function dialogs(): HTMLElement[] {
  return [...screen.queryAllByRole("dialog"), ...screen.queryAllByRole("alertdialog")];
}

/** Everything the user can read, excluding the providers' injected CSS. */
function readableText(): string {
  const clone = document.body.cloneNode(true) as HTMLElement;
  for (const node of Array.from(clone.querySelectorAll("style, script"))) node.remove();
  return clone.textContent ?? "";
}

/** Opens the menu and chooses "Export my data", then lets the download settle. */
async function chooseExport(user: User): Promise<void> {
  await openMenu(user);
  await user.click(await exportItem());
  await flush();
}

// ===========================================================================
describe("the user menu offers the own-data export to every role (US-079.AC-1)", () => {
  it.each(ROLES)("a %s sees an Export my data item — DoD-3", async (role) => {
    stubBackend();
    const user = newUser();
    renderMenu(role);

    await openMenu(user);

    expect(await exportItem()).toBeInTheDocument();
  });

  it.each(ROLES)("choosing it as a %s requests GET /api/export, once — DoD-3", async (role) => {
    const { calls } = stubBackend();
    const user = newUser();
    renderMenu(role);

    await chooseExport(user);

    expect(exportRequests(calls)).toEqual([{ method: "GET", path: EXPORT_PATH, search: "" }]);
    expect(calls).toHaveLength(1);
  });

  it("the item is a plain menu item, not a link to another document — DoD-3", async () => {
    stubBackend();
    const user = newUser();
    renderMenu("roleplayer");

    await openMenu(user);
    const item = await exportItem();

    expect(item.getAttribute("href")).toBeNull();
  });
});

// ===========================================================================
describe("feedback: silent on success, one notification on failure (DoD-7)", () => {
  it("a successful export raises no notification and shows no success text — DoD-7", async () => {
    const { calls } = stubBackend();
    const user = newUser();
    renderMenu("roleplayer");
    // The baseline is clean, so a match after the export could only be new.
    expect(readableText()).not.toMatch(SUCCESS_TALK);

    await chooseExport(user);

    // The export really reached the server, so the silence below is a successful export's.
    expect(exportRequests(calls)).toEqual([{ method: "GET", path: EXPORT_PATH, search: "" }]);

    expect(notificationRoots()).toEqual([]);
    expect(readableText()).not.toMatch(SUCCESS_TALK);
    // Nothing about the download leaked into the page either.
    expect(readableText()).not.toContain(EXPORT_FILENAME);
  });

  it("a failed export raises exactly one notification carrying the error's message — DoD-7", async () => {
    stubBackend({ failExport: true });
    const user = newUser();
    renderMenu("roleplayer");

    await chooseExport(user);

    await waitFor(() => {
      expect(notificationRoots()).toHaveLength(1);
    });
    expect(notificationRoots()[0].textContent ?? "").toContain(FAILURE_MESSAGE);
  });
});

// ===========================================================================
describe("no confirm dialog stands between the click and the request (DoD-8)", () => {
  it("one click on Export my data goes straight to the request — DoD-8", async () => {
    const { calls } = stubBackend();
    const user = newUser();
    renderMenu("roleplayer");
    await openMenu(user);

    await user.click(await exportItem());
    await flush();

    expect(dialogs()).toEqual([]);
    expect(exportRequests(calls)).toHaveLength(1);
  });
});
