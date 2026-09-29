// Feature 005, step 004 — the not-ready / failed screen and the admin entry's gated boot
// (DoD-8, DoD-9, DoD-10, DoD-12). DoD-1..DoD-7 live in adminAccess.test.ts, DoD-11 in
// entries.test.tsx; DoD-13..DoD-16 are [manual/live].
//
// The entry is evaluated per 002/006's recipe (reset modules, a fresh <div id="root">,
// pushState, `await act(async () => import(...))`), then drained, because the entry awaits
// the gate before it creates a root. After vi.resetModules the navigation seam is spied on
// through a fresh import of shared/api, so the entry sees the same module instance.
// Where the re-probe cadence matters only setTimeout/setInterval are faked; setImmediate
// stays real and is what `flush` uses.
//
// Request counting is restricted to the gate's GET /api/me probes: once access is granted the
// mounted admin application legitimately loads its own data (step 006: GET /api/admin/users on
// the Users page), which is not part of the gate's boot and is answered with a never-settling
// promise here so it neither counts nor perturbs the probe sequence.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { AdminNotReady } from "../../src/admin/AdminNotReady";
import { AppProviders } from "../../src/shared/AppProviders";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

/** The not-ready statement is worded as a wait (the backend is starting), not a fault. */
const NOT_READY_TEXT = /starting|not ready|wait|moment/i;
const FAULT_TEXT = /error|fail|fault|broken/i;
/** The visible manual retry control. */
const RETRY_NAME = /retry|try again/i;
const FAILURE_MESSAGE = "The identity probe exploded zq-403.";

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-mantine-color-scheme");
});

afterEach(async () => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  const { notifications } = await import("@mantine/notifications");
  act(() => {
    notifications.clean();
  });
  // Unmount rendered trees (and their body portals) before wiping the body.
  cleanup();
  document.body.innerHTML = "";
  window.history.pushState({}, "", "/");
});

// ---------------------------------------------------------------- helpers

function stubFetch(impl: FetchFn) {
  const mock = vi.fn<FetchFn>(impl);
  vi.stubGlobal("fetch", mock);
  return mock;
}

const ME_PATH = "/api/me";
/** The mounted admin application's own post-grant load (step 006), outside the gate's boot. */
const ADMIN_USERS_PATH = "/api/admin/users";

/**
 * Answers the n-th GET /api/me probe with the n-th handler (the last repeats); every other
 * request (the mounted application's own loads) gets a promise that never settles.
 */
function stubSequence(handlers: FetchFn[]) {
  let index = 0;
  return stubFetch((input, init) => {
    if (requestPath(input) !== ME_PATH) return new Promise<Response>(() => {});
    const handler = handlers[Math.min(index, handlers.length - 1)];
    index += 1;
    return handler(input, init);
  });
}

/** The gate's identity probes only. */
function meProbes(mock: ReturnType<typeof stubFetch>): Array<{ path: string; method: string }> {
  return requests(mock).filter((r) => r.path === ME_PATH);
}

/** Every request except the admin application's post-grant GET /api/admin/users load. */
function bootRequests(mock: ReturnType<typeof stubFetch>): Array<{ path: string; method: string }> {
  return requests(mock).filter((r) => !(r.path === ADMIN_USERS_PATH && r.method === "GET"));
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const answerIdentity = (role: "admin" | "roleplayer") => () =>
  Promise.resolve(jsonResponse({ id: "9007199254740993", username: "mira", role }, 200));

const answerEnvelope = (status: number, code: string, message: string) => () =>
  Promise.resolve(jsonResponse({ error: { code, message, detail: {} } }, status));

const answer401 = answerEnvelope(401, "not_authenticated", "You are not signed in.");
const failedEnvelope = answerEnvelope(403, "insufficient_role", FAILURE_MESSAGE);

const transportFailure = () => Promise.reject(new TypeError("Failed to fetch"));

function requestPath(input: RequestInfo | URL): string {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost").pathname;
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function requests(mock: ReturnType<typeof stubFetch>): Array<{ path: string; method: string }> {
  return mock.mock.calls.map(([input, init]) => ({ path: requestPath(input), method: requestMethod(input, init) }));
}

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

function mountElement(): HTMLElement {
  const root = document.getElementById("root");
  if (root === null) throw new Error("test setup: #root missing");
  return root;
}

function markers(): string[] {
  return Array.from(document.querySelectorAll("[data-entry]")).map((el) => el.getAttribute("data-entry") ?? "");
}

function pageText(): string {
  return document.body.textContent ?? "";
}

/**
 * Evaluates the admin entry at `pathname` with a fresh module registry; returns the spy on
 * the navigation seam the entry itself uses. `withRoot: false` omits the mount element.
 */
async function bootAdmin(pathname = "/admin/", withRoot = true): Promise<MockInstance<(url: string) => void>> {
  vi.resetModules();
  document.body.innerHTML = withRoot ? '<div id="root"></div>' : "";
  window.history.pushState({}, "", pathname);
  const api = await import("../../src/shared/api");
  const navigate = vi.spyOn(api.documentNavigation, "assign").mockImplementation(() => {});
  await act(async () => {
    await import("../../src/admin/main");
  });
  await flush();
  return navigate;
}

function renderScreen(props: { variant: "not-ready" | "failed"; message?: string; onRetry: () => void }) {
  return render(
    <AppProviders>
      <AdminNotReady {...props} />
    </AppProviders>,
  );
}

// ---------------------------------------------------------------------------
describe("AdminNotReady", () => {
  it("the not-ready variant renders a waiting statement, not a fault — DoD-8", () => {
    renderScreen({ variant: "not-ready", onRetry: () => {} });
    expect(pageText()).toMatch(NOT_READY_TEXT);
    expect(pageText()).not.toMatch(FAULT_TEXT);
  });

  it("the failed variant renders the carried message — DoD-8", () => {
    renderScreen({ variant: "failed", message: FAILURE_MESSAGE, onRetry: () => {} });
    expect(pageText()).toContain(FAILURE_MESSAGE);
  });

  it.each(["not-ready", "failed"] as const)("the %s variant offers a visible retry control — DoD-8", (variant) => {
    renderScreen({ variant, message: variant === "failed" ? FAILURE_MESSAGE : undefined, onRetry: () => {} });
    expect(screen.getByRole("button", { name: RETRY_NAME })).toBeVisible();
  });

  it.each(["not-ready", "failed"] as const)(
    "using the %s variant's retry control invokes the callback once — DoD-8",
    (variant) => {
      const onRetry = vi.fn();
      renderScreen({ variant, message: variant === "failed" ? FAILURE_MESSAGE : undefined, onRetry });
      expect(onRetry).not.toHaveBeenCalled();
      fireEvent.click(screen.getByRole("button", { name: RETRY_NAME }));
      expect(onRetry).toHaveBeenCalledTimes(1);
    },
  );
});

// ---------------------------------------------------------------------------
describe("the admin entry mounts only when granted", () => {
  it("an administrator identity mounts the entry and renders its marker — DoD-9", async () => {
    stubFetch(answerIdentity("admin"));
    const navigate = await bootAdmin();
    expect(markers()).toEqual(["admin"]);
    expect(mountElement().querySelector('[data-entry="admin"]')).not.toBeNull();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("a 401 renders nothing at all — no marker, no frame, no spinner — DoD-9", async () => {
    stubFetch(answer401);
    const navigate = await bootAdmin();
    expect(markers()).toEqual([]);
    expect(mountElement().innerHTML).toBe("");
    expect(document.body.children.length).toBe(1);
    // only the shared client's own /login navigation
    expect(navigate.mock.calls).toEqual([["/login"]]);
  });

  it("a non-admin identity renders nothing and navigates to / — DoD-9", async () => {
    stubFetch(answerIdentity("roleplayer"));
    const navigate = await bootAdmin();
    expect(markers()).toEqual([]);
    expect(mountElement().innerHTML).toBe("");
    expect(document.body.children.length).toBe(1);
    expect(navigate.mock.calls).toEqual([["/"]]);
  });
});

// ---------------------------------------------------------------------------
describe("the not-ready and failed screens in the entry", () => {
  it("a transport failure renders the not-ready screen with a retry control and no marker — DoD-10", async () => {
    useFakeTimers();
    stubFetch(transportFailure);
    const navigate = await bootAdmin();
    expect(pageText()).toMatch(NOT_READY_TEXT);
    expect(screen.getByRole("button", { name: RETRY_NAME })).toBeInTheDocument();
    expect(markers()).toEqual([]);
    expect(navigate).not.toHaveBeenCalled();
  });

  it("re-probes at 2000 ms and 4000 ms, then stops and renders the marker in the same document — DoD-10", async () => {
    useFakeTimers();
    const fetchMock = stubSequence([transportFailure, transportFailure, answerIdentity("admin")]);
    const navigate = await bootAdmin();
    expect(meProbes(fetchMock)).toHaveLength(1);
    expect(pageText()).toMatch(NOT_READY_TEXT);

    await advance(1999);
    expect(meProbes(fetchMock)).toHaveLength(1);
    await advance(1);
    expect(meProbes(fetchMock)).toHaveLength(2);
    expect(pageText()).toMatch(NOT_READY_TEXT);
    expect(markers()).toEqual([]);

    await advance(2000);
    expect(meProbes(fetchMock)).toHaveLength(3);
    expect(markers()).toEqual(["admin"]);
    expect(mountElement().querySelector('[data-entry="admin"]')).not.toBeNull();
    expect(screen.queryByRole("button", { name: RETRY_NAME })).toBeNull();

    await advance(20000);
    expect(meProbes(fetchMock)).toHaveLength(3);
    expect(markers()).toEqual(["admin"]);
    expect(navigate).not.toHaveBeenCalled();
  });

  it("every re-probe is a GET /api/me — DoD-10", async () => {
    useFakeTimers();
    const fetchMock = stubSequence([transportFailure, transportFailure, answerIdentity("admin")]);
    await bootAdmin();
    await advance(4000);
    // the gate's probes, i.e. everything but the granted application's own GET /api/admin/users
    expect(bootRequests(fetchMock)).toEqual([
      { path: "/api/me", method: "GET" },
      { path: "/api/me", method: "GET" },
      { path: "/api/me", method: "GET" },
    ]);
  });

  it("a failed classification renders the failure screen with its message — DoD-10", async () => {
    useFakeTimers();
    stubFetch(failedEnvelope);
    const navigate = await bootAdmin();
    expect(pageText()).toContain(FAILURE_MESSAGE);
    expect(screen.getByRole("button", { name: RETRY_NAME })).toBeInTheDocument();
    expect(markers()).toEqual([]);
    expect(navigate).not.toHaveBeenCalled();
  });

  it("a failed classification starts no interval — DoD-10", async () => {
    useFakeTimers();
    const fetchMock = stubFetch(failedEnvelope);
    await bootAdmin();
    await advance(20000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(pageText()).toContain(FAILURE_MESSAGE);
  });
});

// ---------------------------------------------------------------------------
describe("the admin entry's requests during boot", () => {
  it.each<[string, FetchFn]>([
    ["an administrator", answerIdentity("admin")],
    ["a roleplayer", answerIdentity("roleplayer")],
    ["a 401", answer401],
    ["a failure envelope", failedEnvelope],
  ])("answering %s, the entry issues GET /api/me and nothing else — DoD-12", async (_name, handler) => {
    const fetchMock = stubSequence([handler]);
    await bootAdmin();
    // the boot phase only: the granted admin application's own GET /api/admin/users is excluded
    expect(bootRequests(fetchMock)).toEqual([{ path: "/api/me", method: "GET" }]);
  });

  it("no request at all is issued when the mount element is missing — DoD-12", async () => {
    const fetchMock = stubFetch(answerIdentity("admin"));
    try {
      await bootAdmin("/admin/", false);
    } catch {
      // a missing mount element may abort evaluation; only the absence of requests is asserted
    }
    await flush();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
