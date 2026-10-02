// Feature 008, step 005 — the AppBoot gate's five boot outcomes (DoD-4..DoD-10).
// DoD-1..DoD-3 and DoD-14 live in ./appBootState.test.ts; DoD-11 and DoD-12 in
// ../entries.test.tsx. DoD-13 is [manual/live] and has no test here.
//
// The state module is `../../src/app/appBootState` (005.context.md): `appBoot.ts` beside
// `AppBoot.tsx` was a pair of module paths differing only in letter case, which Vite and
// Vitest resolved differently from `tsc`, leaving the component binding undefined.
//
// Where the re-probe cadence matters only setTimeout/setInterval are faked; setImmediate
// stays real and is what `flush` uses. `shared/notifyFailure` is replaced by a mock module,
// so `@mantine/notifications` is never reached from here: both boot states are full-page
// states and raise no notification (context.md D2).
//
// Amended by feature 009, step 008 (DoD-11), stubs only: once the gate renders `App`, the
// shell's expanded column mounts the character tree, which issues `GET /api/characters`.
// The stubs below are routed by URL so that request is answered with an empty list instead
// of hanging or being served the `/api/me` body. No assertion about a boot outcome changes.
//
// Amended by feature 011, step 006 (DoD-12), stubs only: that same tree now also issues
// `GET /api/sessions`, so `stubSequence` answers it with an empty list, by exact pathname.
// Again no assertion about a boot outcome changes; one clause below names the widening.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { APP_BOOT_RETRY_INTERVAL_MS } from "../../src/app/appBootState";
import { AppBoot } from "../../src/app/AppBoot";
import { documentNavigation } from "../../src/shared/api";
import { AppProviders } from "../../src/shared/AppProviders";
import type { CurrentUser } from "../../src/shared/currentUser";

const notifyFailureSpy = vi.hoisted(() => vi.fn());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

const ME_PATH = "/api/me";

/** 009 step 008, DoD-11: the workspace tree's listing, answered empty everywhere here. */
const CHARACTERS_PATH = "/api/characters";

/**
 * 011 step 006, DoD-12: the tree also loads the workspace sessions once the gate renders `App`.
 * Answered empty everywhere here, by **exact** pathname — without this branch the request would
 * hang forever (`stubSequence`'s fallback) and the tree would sit in its loading state. No
 * assertion about a boot outcome changes.
 */
const SESSIONS_PATH = "/api/sessions";

const ROLES: Array<CurrentUser["role"]> = ["roleplayer", "admin"];

const SHELL_NAV_NAME = "Workspace navigation";
const USER_MENU_NAME = "User menu";
const NOT_READY_TITLE = "RPHelper is not ready yet";
const NOT_READY_LINE = "The server is not answering yet. Retrying automatically.";
const FAILED_TITLE = "Could not load your account";
const RETRY_NOW_NAME = "Retry now";
const RETRY_NAME = "Retry";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

let navigate: MockInstance<(url: string) => void>;

beforeEach(() => {
  notifyFailureSpy.mockClear();
  navigate = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  // Unmount rendered trees (and their body portals) before wiping the body.
  cleanup();
  document.body.innerHTML = "";
});

// ----------------------------------------------------------------- fetch stubs

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

function identity(role: CurrentUser["role"], id = "9007199254740993"): CurrentUser {
  return { id, username: "mira", role };
}

const answerIdentity = (role: CurrentUser["role"]): FetchFn => () =>
  Promise.resolve(jsonResponse(identity(role), 200));

const answerEnvelope = (status: number, code: string, message: string): FetchFn => () =>
  Promise.resolve(jsonResponse({ error: { code, message, detail: {} } }, status));

const answer401: FetchFn = answerEnvelope(401, "not_authenticated", "You are not signed in.");

const answer403: FetchFn = answerEnvelope(403, "forbidden", "You may not do that.");

const transportFailure: FetchFn = () => Promise.reject(new TypeError("Failed to fetch"));

const pendingForever: FetchFn = () => new Promise<Response>(() => {});

function requestPath(input: RequestInfo | URL): string {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost").pathname;
}

/**
 * Answers the n-th GET /api/me probe with the n-th handler (the last repeats). The rendered
 * shell's character listing is answered with an empty list (009 step 008, DoD-11); every
 * other request gets a promise that never settles.
 */
function stubSequence(handlers: FetchFn[]) {
  let index = 0;
  return stubFetch((input, init) => {
    const path = requestPath(input);
    if (path === CHARACTERS_PATH) {
      return Promise.resolve(jsonResponse({ characters: [] }, 200));
    }
    if (path === SESSIONS_PATH) {
      return Promise.resolve(jsonResponse({ sessions: [] }, 200));
    }
    if (path !== ME_PATH) return new Promise<Response>(() => {});
    const handler = handlers[Math.min(index, handlers.length - 1)];
    index += 1;
    return handler(input, init);
  });
}

/** The gate's identity probes only. */
function meProbes(mock: ReturnType<typeof stubFetch>): string[] {
  return mock.mock.calls.map(([input]) => requestPath(input)).filter((path) => path === ME_PATH);
}

// --------------------------------------------------------------------- timers

async function flush(rounds = 6): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => setImmediate(resolve));
    });
  }
}

function useFakeTimers(): void {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
}

async function advance(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
  await flush();
}

// --------------------------------------------------------------------- render

function renderBoot() {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={["/"]}>
        <AppBoot storage={null} />
      </MemoryRouter>
    </AppProviders>,
  );
}

function shellNav(): HTMLElement | null {
  return screen.queryByRole("navigation", { name: SHELL_NAV_NAME });
}

function expectNoBootScreen(): void {
  expect(screen.queryByText(NOT_READY_TITLE)).toBeNull();
  expect(screen.queryByText(NOT_READY_LINE)).toBeNull();
  expect(screen.queryByText(FAILED_TITLE)).toBeNull();
}

// ---------------------------------------------------------------------------
describe("nothing is rendered while GET /api/me is in flight", () => {
  it("renders no shell, no not-ready screen and no failure panel — DoD-4", async () => {
    const fetchMock = stubFetch(pendingForever);
    renderBoot();
    await flush();

    expect(meProbes(fetchMock)).toHaveLength(1);
    expect(shellNav()).toBeNull();
    expectNoBootScreen();
    expect(screen.queryAllByRole("button")).toEqual([]);
  });

  it("renders nothing of its own and navigates nowhere while pending — DoD-4", async () => {
    stubFetch(pendingForever);
    renderBoot();
    await flush();

    expect(screen.queryByRole("navigation")).toBeNull();
    expect(screen.queryByRole("main")).toBeNull();
    expect(navigate).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("a successful probe renders the shell for either role", () => {
  it.each(ROLES)(
    "a %s sees the workspace navigation and the user menu with the username — DoD-5",
    async (role) => {
      // 009 step 008, DoD-11: routed by URL, so the shell's tree listing is answered too.
      stubSequence([answerIdentity(role)]);
      renderBoot();
      await flush();

      expect(shellNav()).not.toBeNull();
      expect(screen.getByRole("button", { name: USER_MENU_NAME })).toBeInTheDocument();
      expect(screen.getByText("mira")).toBeInTheDocument();
      expectNoBootScreen();
    },
  );

  it.each(ROLES)(
    "a %s is not denied: no document navigation — DoD-5",
    async (role) => {
      // 009 step 008, DoD-11: routed by URL, so the shell's tree listing is answered too.
      stubSequence([answerIdentity(role)]);
      renderBoot();
      await flush();

      expect(shellNav()).not.toBeNull();
      expect(navigate).not.toHaveBeenCalled();
    },
  );

  // 011 step 006, DoD-12: stub widening only. The boot outcome is still 008's — the shell and
  // the user menu — and the new sessions listing is answered rather than left hanging.
  it("the booted shell's workspace sessions listing is answered — DoD-12", async () => {
    const fetchMock = stubSequence([answerIdentity("roleplayer")]);
    renderBoot();
    await flush();

    expect(shellNav()).not.toBeNull();
    expect(screen.getByRole("button", { name: USER_MENU_NAME })).toBeInTheDocument();
    expectNoBootScreen();
    expect(navigate).not.toHaveBeenCalled();
    expect(
      fetchMock.mock.calls.map(([input]) => requestPath(input)).filter((p) => p === SESSIONS_PATH),
    ).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
describe("a 401 renders nothing and is not navigated twice", () => {
  it("renders no shell and neither boot screen — DoD-6", async () => {
    const fetchMock = stubFetch(answer401);
    renderBoot();
    await flush();

    expect(meProbes(fetchMock)).toHaveLength(1);
    expect(shellNav()).toBeNull();
    expectNoBootScreen();
    expect(screen.queryAllByRole("button")).toEqual([]);
  });

  it("the shared client's /login navigation is the only one — DoD-6", async () => {
    stubFetch(answer401);
    renderBoot();
    await flush();

    expect(navigate).toHaveBeenCalledTimes(1);
    expect(navigate.mock.calls).toEqual([["/login"]]);
  });
});

// ---------------------------------------------------------------------------
describe("a not-ready failure shows the not-ready screen and recovers on its own", () => {
  it("the re-probe interval is a fixed 2000 ms — DoD-7", () => {
    expect(APP_BOOT_RETRY_INTERVAL_MS).toBe(2000);
  });

  it("shows the screen, re-probes at 2000 ms and renders the shell when that probe succeeds — DoD-7", async () => {
    useFakeTimers();
    const fetchMock = stubSequence([transportFailure, answerIdentity("roleplayer")]);
    renderBoot();
    await flush();

    expect(meProbes(fetchMock)).toHaveLength(1);
    expect(screen.getByText(NOT_READY_TITLE)).toBeInTheDocument();
    expect(screen.getByText(NOT_READY_LINE)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: RETRY_NOW_NAME })).toBeInTheDocument();
    expect(shellNav()).toBeNull();

    await advance(1999);
    expect(meProbes(fetchMock)).toHaveLength(1);
    expect(screen.getByText(NOT_READY_TITLE)).toBeInTheDocument();

    await advance(1);
    expect(meProbes(fetchMock)).toHaveLength(2);
    expect(shellNav()).not.toBeNull();
    expect(screen.queryByText(NOT_READY_TITLE)).toBeNull();
    expect(screen.queryByRole("button", { name: RETRY_NOW_NAME })).toBeNull();
  });

  it("re-probes again 2000 ms after a second not-ready outcome, then stops once ready — DoD-7", async () => {
    useFakeTimers();
    const fetchMock = stubSequence([transportFailure, transportFailure, answerIdentity("admin")]);
    renderBoot();
    await flush();
    expect(meProbes(fetchMock)).toHaveLength(1);

    await advance(2000);
    expect(meProbes(fetchMock)).toHaveLength(2);
    expect(screen.getByText(NOT_READY_TITLE)).toBeInTheDocument();

    await advance(2000);
    expect(meProbes(fetchMock)).toHaveLength(3);
    expect(shellNav()).not.toBeNull();

    await advance(20000);
    expect(meProbes(fetchMock)).toHaveLength(3);
    expect(shellNav()).not.toBeNull();
  });

  it("recovering from not-ready navigates nowhere and raises no notification — DoD-7", async () => {
    useFakeTimers();
    stubSequence([transportFailure, answerIdentity("roleplayer")]);
    renderBoot();
    await flush();
    expect(screen.getByText(NOT_READY_TITLE)).toBeInTheDocument();
    expect(navigate).not.toHaveBeenCalled();
    expect(notifyFailureSpy).not.toHaveBeenCalled();

    await advance(2000);
    expect(shellNav()).not.toBeNull();
    expect(navigate).not.toHaveBeenCalled();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("the not-ready screen's manual retry", () => {
  it("Retry now requests /api/me immediately — DoD-8", async () => {
    useFakeTimers();
    const fetchMock = stubSequence([transportFailure, answerIdentity("roleplayer")]);
    renderBoot();
    await flush();
    expect(meProbes(fetchMock)).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: RETRY_NOW_NAME }));
    await flush();

    expect(meProbes(fetchMock)).toHaveLength(2);
    expect(shellNav()).not.toBeNull();
  });

  it("Retry now, not the 2000 ms timer, issues the second probe — DoD-8", async () => {
    useFakeTimers();
    const fetchMock = stubSequence([transportFailure, transportFailure]);
    renderBoot();
    await flush();

    await advance(1000);
    expect(meProbes(fetchMock)).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: RETRY_NOW_NAME }));
    await flush();
    expect(meProbes(fetchMock)).toHaveLength(2);
    expect(screen.getByText(NOT_READY_TITLE)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
describe("a well-formed 403 shows the failure panel with a manual retry only", () => {
  it("shows the panel and never re-probes on its own — DoD-9", async () => {
    useFakeTimers();
    const fetchMock = stubSequence([answer403, answerIdentity("admin")]);
    renderBoot();
    await flush();

    expect(meProbes(fetchMock)).toHaveLength(1);
    expect(screen.getByText(FAILED_TITLE)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: RETRY_NAME })).toBeInTheDocument();
    expect(shellNav()).toBeNull();

    await advance(2000);
    expect(meProbes(fetchMock)).toHaveLength(1);
    await advance(20000);
    expect(meProbes(fetchMock)).toHaveLength(1);
    expect(screen.getByText(FAILED_TITLE)).toBeInTheDocument();
  });

  it("Retry requests /api/me again and the shell renders on success — DoD-9", async () => {
    useFakeTimers();
    const fetchMock = stubSequence([answer403, answerIdentity("admin")]);
    renderBoot();
    await flush();
    expect(meProbes(fetchMock)).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: RETRY_NAME }));
    await flush();

    expect(meProbes(fetchMock)).toHaveLength(2);
    expect(shellNav()).not.toBeNull();
    expect(screen.queryByText(FAILED_TITLE)).toBeNull();
  });

  it("the failure path navigates nowhere and raises no notification — DoD-9", async () => {
    useFakeTimers();
    stubSequence([answer403, answerIdentity("admin")]);
    renderBoot();
    await flush();
    expect(screen.getByText(FAILED_TITLE)).toBeInTheDocument();
    expect(navigate).not.toHaveBeenCalled();
    expect(notifyFailureSpy).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: RETRY_NAME }));
    await flush();
    expect(shellNav()).not.toBeNull();
    expect(navigate).not.toHaveBeenCalled();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("unmounting cancels the pending re-probe", () => {
  it("no further /api/me request is made after unmount — DoD-10", async () => {
    useFakeTimers();
    const fetchMock = stubSequence([transportFailure, answerIdentity("roleplayer")]);
    const view = renderBoot();
    await flush();
    expect(screen.getByText(NOT_READY_TITLE)).toBeInTheDocument();
    expect(meProbes(fetchMock)).toHaveLength(1);

    act(() => {
      view.unmount();
    });

    await advance(2000);
    expect(meProbes(fetchMock)).toHaveLength(1);
    await advance(20000);
    expect(meProbes(fetchMock)).toHaveLength(1);
    expect(shellNav()).toBeNull();
    expect(screen.queryByText(NOT_READY_TITLE)).toBeNull();
  });
});
