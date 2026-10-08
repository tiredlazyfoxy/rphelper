// Feature 018, step 004 — the page composer component (DoD-7..DoD-10; DoD-11 is manual/live).
//
// Expected behaviour comes from the step's Interface intent and Definition of done plus 018
// context.md's UI strings ("Page composer": region "Start a session" with heading "Start a
// session"; the core's textbox "Composer" and button "Send"), D1 (no kind switch, no setup
// choice), D5 (one post, then a router push to /sessions/<id> exactly as received; on failure
// the draft is kept and notifyFailure is called) and 014's paste rule (a 128,001-character
// non-blank paste warns with "paste-context-cost" and is not prevented).
//
// Rendered inside AppProviders and a MemoryRouter at /characters/<C>, with the composer route
// and a /sessions/:id probe route, so the location after Send and after Back is observable.
// Navigation is observed through the location only, never by spying on useNavigate.
//
// Amended by feature 033, step 001 (DoD-13, D8): the composer's section heading — and so its
// region's accessible name — is now "New session" (was "Start a session"). Nothing else about
// the component changes in that step, so every other clause is untouched.
//
// Amended by feature 033, step 004 (D8, D10): the composer now carries a "Setup" select and
// lists the character's setups (`GET /api/characters/<C>/setups`) on mount. D10 supersedes 018
// D1's "no setup choice" for this composer, so the DoD-7 absence clause no longer names the
// Setup select (its presence is 033 step 004 DoD-2, asserted here and in
// CharacterComposer.setup.test.tsx). Every stub answers the setups listing with an empty list,
// and request assertions now look at the sessions POST only, never at the whole call log.
//
// Amended by fast feature 011 (composer-send-icon-and-shortcut, DoD-13): the character page's
// composer is full width and starts at 10 lines — its "Composer" textarea has rows >= 10, no
// ancestor carries the composer's 720px max-width, and the "Setup" select still follows the
// textarea. jsdom has no layout, so these are asserted on attributes and inline styles only.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CharacterComposer } from "../../src/app/CharacterComposer";
import type { Session, StartedSession } from "../../src/app/sessionsApi";
import { SessionsState } from "../../src/app/sessionsState";
import type { Message } from "../../src/app/streamApi";
import { AppProviders } from "../../src/shared/AppProviders";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

const notifyWarningSpy = vi.hoisted(() => vi.fn<(id: "paste-context-cost") => void>());
vi.mock("../../src/shared/notifyWarning", () => ({ notifyWarning: notifyWarningSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- fixtures
// Every id is > Number.MAX_SAFE_INTEGER: a silent numeric coercion would change it.
const CHARACTER_ID = "7250000000000000101";
const SESSION_ID = "7270000000000000101";
const MESSAGE_ID = "7280000000000000101";

const CHARACTER_PATH = `/characters/${CHARACTER_ID}`;
const START_PATH = `/api/characters/${CHARACTER_ID}/sessions`;
/** 033 step 004: the composer lists the character's setups on mount. */
const SETUPS_PATH = `/api/characters/${CHARACTER_ID}/setups`;
const STAMP = "2026-10-03T09:26:53.000000+00:00";
const PASTE_ID = "paste-context-cost";
const OVER_THRESHOLD = "a".repeat(128_001);

const SERVED_SESSION: Session = {
  id: SESSION_ID,
  character_id: CHARACTER_ID,
  setup_id: null,
  setup_name: null,
  archived_at: null,
  last_used_at: STAMP,
  created_at: STAMP,
  updated_at: STAMP,
};

function openingMessage(text: string): Message {
  return {
    id: MESSAGE_ID,
    session_id: SESSION_ID,
    role: "user",
    kind: null,
    text,
    settled_at: null,
    created_at: STAMP,
    updated_at: STAMP,
  };
}

function started(text: string): StartedSession {
  return { ...SERVED_SESSION, opening_message: openingMessage(text) };
}

beforeEach(() => {
  notifyFailureSpy.mockReset();
  notifyWarningSpy.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- fetch helpers
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

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function isStart(input: RequestInfo | URL, init?: RequestInit): boolean {
  const url = requestUrl(input);
  return requestMethod(input, init) === "POST" && url.pathname === START_PATH && url.search === "";
}

function unexpected(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  return Promise.resolve(
    jsonResponse(
      {
        error: {
          code: "unexpected_request",
          message: `${requestMethod(input, init)} ${requestUrl(input).pathname}`,
          detail: {},
        },
      },
      599,
    ),
  );
}

function isSetupsListing(input: RequestInfo | URL, init?: RequestInit): boolean {
  return requestMethod(input, init) === "GET" && requestUrl(input).pathname === SETUPS_PATH;
}

/** 033 step 004: answers the composer's setups listing with no setups, else delegates. */
function withSetups(impl: FetchFn): FetchFn {
  return (input, init) =>
    isSetupsListing(input, init) ? Promise.resolve(jsonResponse({ setups: [] }, 200)) : impl(input, init);
}

function serveStart(body: unknown, status: number) {
  return stubFetch(
    withSetups((input, init) =>
      isStart(input, init) ? Promise.resolve(jsonResponse(body, status)) : unexpected(input, init),
    ),
  );
}

type Seen = { method: string; path: string; search: string };

/** Every request the stub saw except the composer's setups listing (033 step 004). */
function seen(mock: ReturnType<typeof stubFetch>): Seen[] {
  return mock.mock.calls
    .filter(([input, init]) => !isSetupsListing(input, init))
    .map(([input, init]) => {
      const url = requestUrl(input);
      return { method: requestMethod(input, init), path: url.pathname, search: url.search };
    });
}

/** The JSON body of the n-th sessions POST, or undefined when none was sent. */
function sentBody(mock: ReturnType<typeof stubFetch>, index = 0): unknown {
  const raw = mock.mock.calls.filter(([input, init]) => isStart(input, init))[index]?.[1]?.body;
  if (raw === undefined || raw === null) return undefined;
  return typeof raw === "string" ? (JSON.parse(raw) as unknown) : raw;
}

// ---------------------------------------------------------------- render
function LocationProbe() {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <div>
      <span data-testid="location">{location.pathname}</span>
      <button type="button" onClick={() => void navigate(-1)}>
        probe back
      </button>
    </div>
  );
}

function SessionProbe() {
  const params = useParams();
  return <p>session page {params.id}</p>;
}

function CharacterProbeRoute(props: { sessions: SessionsState }) {
  const params = useParams();
  return <CharacterComposer characterId={params.id ?? ""} sessions={props.sessions} />;
}

function renderComposer() {
  const sessions = new SessionsState();
  const view = render(
    <AppProviders>
      <MemoryRouter initialEntries={[CHARACTER_PATH]}>
        <Routes>
          <Route path="/characters/:id" element={<CharacterProbeRoute sessions={sessions} />} />
          <Route path="/sessions/:id" element={<SessionProbe />} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </AppProviders>,
  );
  return { sessions, view };
}

function locationPath(): string {
  return screen.getByTestId("location").textContent ?? "";
}

/** 033 step 001 (DoD-13): the composer's region is named "New session". */
const COMPOSER_REGION = "New session";

function region(): HTMLElement {
  return screen.getByRole("region", { name: COMPOSER_REGION });
}

function composer(): HTMLElement {
  return within(region()).getByRole("textbox", { name: "Composer" });
}

function sendButton(): HTMLElement {
  return within(region()).getByRole("button", { name: "Send" });
}

function newUser(): ReturnType<typeof userEvent.setup> {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

// ---------------------------------------------------------------- DoD-7
describe("CharacterComposer — the core alone (US-117.AC-4, D1)", () => {
  it('(amended by 033 DoD-13) renders a "New session" region headed "New session" holding a textbox "Composer" and a "Send" button — DoD-7', () => {
    stubFetch(withSetups(unexpected));
    renderComposer();

    const startRegion = region();
    expect(within(startRegion).getByRole("heading", { name: COMPOSER_REGION })).toBeInTheDocument();
    // 033 DoD-13: the old name is gone.
    expect(screen.queryByRole("region", { name: "Start a session" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Start a session" })).toBeNull();
    expect(composer()).toBeInTheDocument();
    expect(sendButton()).toBeInTheDocument();
  });

  it('(amended by 033 step 004 DoD-2, DoD-9) renders no "Entry kind" group, no "Partner" / "My turn" radio, no "Settle" and no "Discard empty zone" — but a "Setup" select reading "No setup" — DoD-7', async () => {
    stubFetch(withSetups(unexpected));
    renderComposer();

    expect(screen.queryByRole("radiogroup", { name: "Entry kind" })).toBeNull();
    expect(screen.queryByRole("group", { name: "Entry kind" })).toBeNull();
    expect(screen.queryByText("Entry kind")).toBeNull();
    expect(screen.queryByRole("radio", { name: "Partner" })).toBeNull();
    expect(screen.queryByRole("radio", { name: "My turn" })).toBeNull();
    // 033 step 004 (D8, D10): the composer now offers a "Setup" select, "No setup" on open.
    const setupField =
      within(region()).queryByRole("combobox", { name: /^setup$/i }) ??
      within(region()).queryByRole("textbox", { name: /^setup$/i }) ??
      within(region()).getByLabelText(/^setup$/i);
    expect(setupField).toBeInTheDocument();
    await waitFor(() => {
      expect((setupField as HTMLInputElement).value).toBe("No setup");
    });
    expect(screen.queryByRole("button", { name: "Settle" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Discard empty zone" })).toBeNull();
  });

  it('"Send" is disabled while the composer is empty or blank, and enabled once non-blank text is typed — DoD-7', async () => {
    stubFetch(withSetups(unexpected));
    const user = newUser();
    renderComposer();

    expect(sendButton()).toBeDisabled();

    await user.type(composer(), "   ");
    expect(sendButton()).toBeDisabled();

    await user.type(composer(), "Hi");
    expect(sendButton()).toBeEnabled();
  });
});

// ---------------------------------------------------------------- DoD-8
describe("CharacterComposer — one post, then push into the session (US-117.AC-1, UC-080, D5)", () => {
  it('typing "Hello there" and pressing "Send" sends one POST with exactly { opening_message: "Hello there" } — DoD-8', async () => {
    const mock = serveStart(started("Hello there"), 201);
    const user = newUser();
    renderComposer();

    await user.type(composer(), "Hello there");
    await user.click(sendButton());

    await waitFor(() => {
      expect(locationPath()).toBe(`/sessions/${SESSION_ID}`);
    });
    expect(seen(mock)).toEqual([{ method: "POST", path: START_PATH, search: "" }]);
    expect(sentBody(mock)).toEqual({ opening_message: "Hello there" });
  });

  it("after the 201 the location is /sessions/<served id>, and Back returns to /characters/<C> (a push) — DoD-8", async () => {
    serveStart(started("Hello there"), 201);
    const user = newUser();
    renderComposer();

    expect(locationPath()).toBe(CHARACTER_PATH);

    await user.type(composer(), "Hello there");
    await user.click(sendButton());

    await waitFor(() => {
      expect(locationPath()).toBe(`/sessions/${SESSION_ID}`);
    });
    expect(screen.getByText(`session page ${SESSION_ID}`)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "probe back" }));

    await waitFor(() => {
      expect(locationPath()).toBe(CHARACTER_PATH);
    });
  });
});

// ---------------------------------------------------------------- DoD-9
describe("CharacterComposer — a failed send keeps everything (R10, D5)", () => {
  it('on a failed POST the location stays /characters/<C>, the composer still holds "Hello there" and "Send" is enabled again — DoD-9', async () => {
    serveStart(
      { error: { code: "internal_error", message: "The session ledger is on fire zq-18.", detail: {} } },
      500,
    );
    const user = newUser();
    renderComposer();

    await user.type(composer(), "Hello there");
    await user.click(sendButton());

    await waitFor(() => {
      expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(sendButton()).toBeEnabled();
    });
    expect(locationPath()).toBe(CHARACTER_PATH);
    expect(composer()).toHaveValue("Hello there");
  });
});

// ---------------------------------------------------------------- fast/011 DoD-13
function precedes(first: Node, second: Node): boolean {
  return (first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

const CAP_720 = /(^|[^\d.])(720px|45rem)/;

/** Whether the element carries a 720px max-width (inline style, as Mantine emits `maw`). */
function carries720MaxWidth(el: HTMLElement): boolean {
  const raw = el.getAttribute("style") ?? "";
  const declared = [...raw.matchAll(/(?:^|;)\s*max-width\s*:\s*([^;]+)/g)].map((match) => match[1] ?? "");
  const candidates = [...declared, el.style.maxWidth, el.style.getPropertyValue("--maw")];
  return candidates.some((value) => CAP_720.test(value));
}

function ancestors(node: HTMLElement): HTMLElement[] {
  const found: HTMLElement[] = [];
  for (let el = node.parentElement; el !== null && el !== document.body; el = el.parentElement) {
    found.push(el);
  }
  return found;
}

describe("fast/011 — the character page composer is full width and at least 10 lines", () => {
  it('the "Composer" textarea has rows >= 10, no 720px max-width ancestor, and the "Setup" select follows it — fast/011 DoD-13', async () => {
    stubFetch(withSetups(unexpected));
    renderComposer();

    const textbox = composer();
    expect(Number(textbox.getAttribute("rows"))).toBeGreaterThanOrEqual(10);
    expect(ancestors(textbox).filter(carries720MaxWidth)).toEqual([]);

    const setupField =
      within(region()).queryByRole("combobox", { name: /^setup$/i }) ??
      within(region()).queryByRole("textbox", { name: /^setup$/i }) ??
      within(region()).getByLabelText(/^setup$/i);
    expect(precedes(textbox, setupField)).toBe(true);
    await waitFor(() => {
      expect((setupField as HTMLInputElement).value).toBe("No setup");
    });
  });
});

// ---------------------------------------------------------------- DoD-10
describe("CharacterComposer — the core's paste warning on the second host (US-035.AC-1)", () => {
  it("pasting a 128,001-character text raises the paste warning, makes no request and does not prevent the insertion — DoD-10", () => {
    // 033 step 004: the composer's setups listing on mount is not the paste's request, so
    // `seen` (which skips it) is what must stay empty.
    const mock = stubFetch(withSetups(unexpected));
    renderComposer();

    const notPrevented = fireEvent.paste(composer(), {
      clipboardData: { getData: () => OVER_THRESHOLD },
    });

    expect(notifyWarningSpy).toHaveBeenCalledTimes(1);
    expect(notifyWarningSpy).toHaveBeenCalledWith(PASTE_ID);
    expect(notPrevented).toBe(true);
    expect(seen(mock)).toEqual([]);
  });
});
