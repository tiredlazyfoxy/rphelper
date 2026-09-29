// Feature 003, step 004 — the bootstrap entry's page and its rendered states
// (DoD-1..DoD-6, DoD-8..DoD-12, DoD-14, DoD-15). DoD-16..DoD-18 are [manual/live].
//
// `fetch` is stubbed per test. Where the retry cadence matters, only setTimeout/setInterval
// are faked; `setImmediate` stays real and is what `flush` uses to drain pending work.
// States are recognised by what the spec says each one shows, never by component structure.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BootstrapPage } from "../../src/bootstrap/BootstrapPage";
import { BootstrapState, bootstrapPhase } from "../../src/bootstrap/bootstrapState";
import { AppProviders } from "../../src/shared/AppProviders";

const { notifyFailureSpy } = vi.hoisted(() => ({ notifyFailureSpy: vi.fn() }));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const SRC_ROOT = path.join(FRONTEND_ROOT, "src");

/** The offer's heading names the instance as unconfigured. */
const OFFER_HEADING = /unconfigured|not (?:yet )?configured|not (?:yet )?set up/i;
/** The refusal states the instance is already configured (UC-003). */
const REFUSAL_TEXT = /already configured/i;
/** The not-ready state says the instance is still starting — a wait, not a fault. */
const NOT_READY_TEXT = /starting|not ready/i;
/** The visible manual retry control. */
const RETRY_NAME = /retry|try again/i;
const FAILURE_MESSAGE = "The health probe exploded zq-17.";
const NOTIFICATION_ROOT = ".mantine-Notification-root";

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
});

// ---------------------------------------------------------------- helpers

function stubFetch(impl: FetchFn) {
  const mock = vi.fn<FetchFn>(impl);
  vi.stubGlobal("fetch", mock);
  return mock;
}

/** Answers the n-th request with the n-th handler; the last handler repeats. */
function stubSequence(handlers: Array<() => Promise<Response>>) {
  let index = 0;
  return stubFetch(() => {
    const handler = handlers[Math.min(index, handlers.length - 1)];
    index += 1;
    return handler();
  });
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function healthBody(configured: boolean, status: string, schema: string) {
  return { status, configured, schema };
}

const answerHealth =
  (configured: boolean, status = configured ? "ok" : "degraded", schema = configured ? "ok" : "missing") =>
  () =>
    Promise.resolve(jsonResponse(healthBody(configured, status, schema), 200));

const transportFailure = () => Promise.reject(new TypeError("Failed to fetch"));

const htmlPage = (status: number) => () =>
  Promise.resolve(
    new Response(`<html><body><h1>${status} Bad Gateway</h1><hr>nginx</body></html>`, {
      status,
      headers: { "Content-Type": "text/html" },
    }),
  );

const failedEnvelope = () =>
  Promise.resolve(
    jsonResponse({ error: { code: "internal_error", message: FAILURE_MESSAGE, detail: {} } }, 500),
  );

const neverAnswers = () => new Promise<Response>(() => undefined);

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

function useFakeTimers(): void {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
}

async function advance(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
  await flush();
}

function renderPage(state = new BootstrapState()) {
  const view = render(
    <AppProviders>
      <MemoryRouter>
        <BootstrapPage state={state} />
      </MemoryRouter>
    </AppProviders>,
  );
  return { state, ...view };
}

function requestPath(input: RequestInfo | URL): string {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost").pathname;
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function pageText(): string {
  return document.body.textContent ?? "";
}

function offerHeadings(): HTMLElement[] {
  return screen.queryAllByRole("heading", { name: OFFER_HEADING });
}

function offerShown(): boolean {
  return offerHeadings().length > 0;
}

function refusalShown(): boolean {
  return REFUSAL_TEXT.test(pageText());
}

function loginAnchors(): HTMLAnchorElement[] {
  return Array.from(document.querySelectorAll<HTMLAnchorElement>("a")).filter(
    (a) => a.getAttribute("href") === "/login",
  );
}

function retryButton(): HTMLElement {
  return screen.getByRole("button", { name: RETRY_NAME });
}

const CONTROL_ROLES = ["button", "link", "radio", "checkbox", "tab", "menuitem", "option", "switch"] as const;

/** Any interactive element whose accessible name speaks of creating. */
function createControls(): HTMLElement[] {
  return CONTROL_ROLES.flatMap((role) => screen.queryAllByRole(role, { name: /create/i }));
}

function markers(): string[] {
  return Array.from(document.querySelectorAll("[data-entry]")).map((el) => el.getAttribute("data-entry") ?? "");
}

function notificationRoots(): Element[] {
  return Array.from(document.querySelectorAll(NOTIFICATION_ROOT));
}

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(full);
    return /\.(ts|tsx)$/.test(entry.name) ? [full] : [];
  });
}

function importSpecifiers(source: string): string[] {
  const pattern = /(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)["']([^"']+)["']/g;
  return Array.from(stripComments(source).matchAll(pattern), (m) => m[1]);
}

function relative(file: string): string {
  return path.relative(FRONTEND_ROOT, file).split(path.sep).join("/");
}

// ---------------------------------------------------------------------------
describe("the probe on mount", () => {
  it("the page issues exactly one GET /api/health and nothing else — DoD-1", async () => {
    const fetchMock = stubFetch(answerHealth(false));
    renderPage();
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [input, init] = fetchMock.mock.calls[0];
    expect(requestPath(input)).toBe("/api/health");
    expect(requestMethod(input, init)).toBe("GET");
  });

  it("mounting the bootstrap entry itself issues one GET /api/health, no /api/me, no POST — DoD-1", async () => {
    const fetchMock = stubFetch(answerHealth(false));
    vi.resetModules();
    document.body.innerHTML = '<div id="root"></div>';
    window.history.pushState({}, "", "/");
    try {
      await act(async () => {
        await import("../../src/bootstrap/main");
      });
      await flush();
      const requests = fetchMock.mock.calls.map(([input, init]) => ({
        path: requestPath(input),
        method: requestMethod(input, init),
      }));
      expect(requests).toEqual([{ path: "/api/health", method: "GET" }]);
      expect(requests.some((r) => r.path === "/api/me")).toBe(false);
      expect(requests.some((r) => r.method === "POST")).toBe(false);
    } finally {
      document.body.innerHTML = "";
    }
  });

  it("the entry marker is still rendered by the mounted entry — DoD-14", async () => {
    stubFetch(answerHealth(true));
    vi.resetModules();
    document.body.innerHTML = '<div id="root"></div>';
    window.history.pushState({}, "", "/sessions/abc123");
    try {
      await act(async () => {
        await import("../../src/bootstrap/main");
      });
      await flush();
      expect(markers()).toEqual(["bootstrap"]);
    } finally {
      document.body.innerHTML = "";
      window.history.pushState({}, "", "/");
    }
  });
});

// ---------------------------------------------------------------------------
describe("the probing state", () => {
  it("while the first probe is in flight neither the offer nor the refusal renders — DoD-2", async () => {
    const fetchMock = stubFetch(neverAnswers);
    renderPage();
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(offerShown()).toBe(false);
    expect(refusalShown()).toBe(false);
    expect(loginAnchors()).toEqual([]);
    expect(pageText()).not.toMatch(/create/i);
    expect(createControls()).toEqual([]);
    expect(markers()).toEqual(["bootstrap"]);
  });
});

// ---------------------------------------------------------------------------
describe("the offer", () => {
  it("configured:false renders the offer heading — DoD-3", async () => {
    stubFetch(answerHealth(false));
    renderPage();
    await flush();
    expect(offerShown()).toBe(true);
    expect(refusalShown()).toBe(false);
  });

  it("the offer names the create-a-new option — DoD-3", async () => {
    stubFetch(answerHealth(false));
    renderPage();
    await flush();
    expect(pageText()).toMatch(/create/i);
    expect(pageText()).toMatch(/\bnew\b/i);
  });

  it("the offer renders no sign-in hand-off link and no not-ready wording — DoD-3", async () => {
    stubFetch(answerHealth(false));
    renderPage();
    await flush();
    expect(loginAnchors()).toEqual([]);
    expect(screen.queryAllByRole("button", { name: RETRY_NAME })).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("the refusal", () => {
  it("configured:true renders the refusal — DoD-4", async () => {
    stubFetch(answerHealth(true));
    renderPage();
    await flush();
    expect(refusalShown()).toBe(true);
    expect(offerShown()).toBe(false);
  });

  it("no create control is rendered at all in the refusal — DoD-4", async () => {
    stubFetch(answerHealth(true));
    renderPage();
    await flush();
    expect(refusalShown()).toBe(true);
    expect(createControls()).toEqual([]);
    expect(document.querySelectorAll("form, input, textarea, select").length).toBe(0);
  });

  it("the refusal renders an anchor whose href is /login — DoD-5", async () => {
    stubFetch(answerHealth(true));
    renderPage();
    await flush();
    const anchors = loginAnchors();
    expect(anchors.length).toBeGreaterThan(0);
    for (const anchor of anchors) {
      expect(anchor.tagName).toBe("A");
    }
  });

  it("the /login link is a document navigation, not a router link — DoD-5", async () => {
    stubFetch(answerHealth(true));
    renderPage();
    await flush();
    const anchor = loginAnchors()[0];
    expect(anchor).toBeDefined();
    let preventedBeforeWindow: boolean | null = null;
    const observe = (event: Event) => {
      preventedBeforeWindow = event.defaultPrevented;
      event.preventDefault(); // keep jsdom from attempting the navigation
    };
    window.addEventListener("click", observe);
    try {
      const click = new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 });
      anchor.dispatchEvent(click);
    } finally {
      window.removeEventListener("click", observe);
    }
    // A router link intercepts the click (preventDefault + history push); a real anchor does not.
    expect(preventedBeforeWindow).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("the entry branches on configured alone", () => {
  it.each([
    ["degraded", "missing"],
    ["unconfigured", "ok"],
    ["ok", "ok"],
  ])("configured:false with status %s / schema %s renders the offer — DoD-6", async (status, schema) => {
    stubFetch(answerHealth(false, status, schema));
    renderPage();
    await flush();
    expect(offerShown()).toBe(true);
    expect(refusalShown()).toBe(false);
  });

  it.each([
    ["ok", "ok"],
    ["degraded", "missing"],
    ["unconfigured", "ok"],
  ])("configured:true with status %s / schema %s renders the refusal — DoD-6", async (status, schema) => {
    stubFetch(answerHealth(true, status, schema));
    renderPage();
    await flush();
    expect(refusalShown()).toBe(true);
    expect(offerShown()).toBe(false);
    expect(createControls()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("the not-ready-yet state and its fixed-interval retry", () => {
  it.each<[string, () => Promise<Response>]>([
    ["a transport failure", transportFailure],
    ["a raw 502 HTML page", htmlPage(502)],
    ["a raw 503 HTML page", htmlPage(503)],
    ["a raw 504 HTML page", htmlPage(504)],
  ])("%s renders the not-ready-yet state with a retry control — DoD-8", async (_name, handler) => {
    useFakeTimers();
    stubFetch(handler);
    renderPage();
    await flush();
    expect(pageText()).toMatch(NOT_READY_TEXT);
    expect(retryButton()).toBeInTheDocument();
    expect(offerShown()).toBe(false);
    expect(refusalShown()).toBe(false);
  });

  it("re-probes at 2000 ms and 4000 ms, then stops once a probe succeeds and renders the offer — DoD-8", async () => {
    useFakeTimers();
    const fetchMock = stubSequence([transportFailure, htmlPage(502), answerHealth(false)]);
    renderPage();
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(pageText()).toMatch(NOT_READY_TEXT);

    await advance(1999);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await advance(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(pageText()).toMatch(NOT_READY_TEXT);

    await advance(2000);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(offerShown()).toBe(true);

    await advance(20000);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(offerShown()).toBe(true);
  });

  it("every retry is a GET /api/health — DoD-8", async () => {
    useFakeTimers();
    const fetchMock = stubSequence([transportFailure, transportFailure, answerHealth(true)]);
    renderPage();
    await flush();
    await advance(4000);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    for (const [input, init] of fetchMock.mock.calls) {
      expect(requestPath(input)).toBe("/api/health");
      expect(requestMethod(input, init)).toBe("GET");
    }
    expect(refusalShown()).toBe(true);
  });
});

// ---------------------------------------------------------------------------
describe("the manual retry control", () => {
  it("in the not-ready state re-probes immediately — DoD-9", async () => {
    useFakeTimers();
    const fetchMock = stubSequence([transportFailure, answerHealth(false)]);
    renderPage();
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    act(() => {
      fireEvent.click(retryButton());
    });
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(offerShown()).toBe(true);
  });

  it("in the failed state re-probes immediately — DoD-9", async () => {
    useFakeTimers();
    const fetchMock = stubSequence([failedEnvelope, answerHealth(true)]);
    renderPage();
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    act(() => {
      fireEvent.click(retryButton());
    });
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(refusalShown()).toBe(true);
  });
});

// ---------------------------------------------------------------------------
describe("the failed state", () => {
  it("a well-formed backend error renders the failure's own message — DoD-10", async () => {
    stubFetch(failedEnvelope);
    renderPage();
    await flush();
    expect(pageText()).toContain(FAILURE_MESSAGE);
    expect(retryButton()).toBeInTheDocument();
    expect(pageText()).not.toMatch(NOT_READY_TEXT);
    expect(offerShown()).toBe(false);
    expect(refusalShown()).toBe(false);
  });

  it("the failed state does not start the interval — DoD-10", async () => {
    useFakeTimers();
    const fetchMock = stubFetch(failedEnvelope);
    renderPage();
    await flush();
    expect(pageText()).toContain(FAILURE_MESSAGE);
    await advance(20000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(pageText()).toContain(FAILURE_MESSAGE);
  });

  it("a malformed 4xx body renders the failed state, not not-ready, and starts no interval — DoD-10", async () => {
    useFakeTimers();
    const fetchMock = stubFetch(htmlPage(404));
    renderPage();
    await flush();
    expect(pageText()).not.toMatch(NOT_READY_TEXT);
    expect(retryButton()).toBeInTheDocument();
    await advance(20000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
describe("no notification in any state", () => {
  const SCENARIOS: Array<[string, () => Promise<Response>]> = [
    ["probing", neverAnswers],
    ["offer", answerHealth(false)],
    ["refusal", answerHealth(true)],
    ["not-ready", transportFailure],
    ["failed", failedEnvelope],
  ];

  it.each(SCENARIOS)("the %s state calls notifyFailure nowhere — DoD-11", async (_name, handler) => {
    useFakeTimers();
    stubFetch(handler);
    renderPage();
    await flush();
    await advance(4000);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(notificationRoots()).toEqual([]);
  });

  it("retrying from the failed state calls notifyFailure nowhere — DoD-11", async () => {
    stubSequence([failedEnvelope, failedEnvelope]);
    renderPage();
    await flush();
    act(() => {
      fireEvent.click(retryButton());
    });
    await flush();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(notificationRoots()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("unmounting cancels the timer and the in-flight request", () => {
  it("no request is issued after unmount while not-ready — DoD-12", async () => {
    useFakeTimers();
    const fetchMock = stubFetch(transportFailure);
    const { state, unmount } = renderPage();
    await flush();
    expect(bootstrapPhase(state)).toBe("not-ready");
    unmount();
    await advance(20000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(bootstrapPhase(state)).toBe("not-ready");
  });

  it("unmount aborts the in-flight request — DoD-12", async () => {
    const pending = deferred<Response>();
    const fetchMock = stubFetch(() => pending.promise);
    const { unmount } = renderPage();
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    unmount();
    expect(fetchMock.mock.calls[0][1]?.signal?.aborted).toBe(true);
    pending.resolve(jsonResponse(healthBody(false, "degraded", "missing"), 200));
    await flush();
  });

  it("a response arriving after unmount writes nothing to the store — DoD-12", async () => {
    const pending = deferred<Response>();
    const fetchMock = stubFetch(() => pending.promise);
    const { state, unmount } = renderPage();
    await flush();
    unmount();
    pending.resolve(jsonResponse(healthBody(true, "ok", "ok"), 200));
    await flush();
    expect(bootstrapPhase(state)).toBe("probing");
    expect(state.failureMessage).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
describe("the entry marker and the router", () => {
  it.each<[string, () => Promise<Response>]>([
    ["probing", neverAnswers],
    ["offer", answerHealth(false)],
    ["refusal", answerHealth(true)],
    ["not-ready", transportFailure],
    ["failed", failedEnvelope],
  ])("the %s state carries the bootstrap entry marker — DoD-14", async (_name, handler) => {
    stubFetch(handler);
    renderPage();
    await flush();
    expect(markers()).toEqual(["bootstrap"]);
  });

  it("bootstrap/main.tsx declares no router basename — DoD-14", () => {
    const source = stripComments(readFileSync(path.join(SRC_ROOT, "bootstrap", "main.tsx"), "utf8"));
    expect(source).not.toMatch(/\bbasename\b/);
  });
});

// ---------------------------------------------------------------------------
describe("stylesheet imports", () => {
  it("no module under src/bootstrap/ imports a stylesheet — DoD-15", () => {
    const offenders = sourceFiles(path.join(SRC_ROOT, "bootstrap")).flatMap((file) =>
      importSpecifiers(readFileSync(file, "utf8"))
        .filter((spec) => /\.(?:css|scss|sass|less)(?:\?.*)?$/.test(spec))
        .map((spec) => `${relative(file)} imports ${spec}`),
    );
    expect(offenders).toEqual([]);
  });

  it("src/app/main.tsx is still the only module importing shell.css — DoD-15", () => {
    const importers = sourceFiles(SRC_ROOT)
      .filter((file) =>
        importSpecifiers(readFileSync(file, "utf8")).some(
          (spec) => path.posix.basename(spec.split("?")[0]) === "shell.css",
        ),
      )
      .map(relative);
    expect(importers).toEqual(["src/app/main.tsx"]);
  });
});
