// Feature 011, step 009 — the session's own screen at `/sessions/:id` (DoD-2..DoD-10).
// The state module's clauses (DoD-1) live in sessionScreenState.test.ts, the route wiring
// (DoD-11) in App.test.tsx and the entry's stub widening (DoD-12) in entries.test.tsx;
// DoD-13 is [manual/live] and carries no test.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done plus
// context.md's D5 (no archive control on this screen — only the "Archived" badge), D17 (the
// five statuses, the header, the neutral "Character" fallback with no second request, and
// everything deliberately absent) and D18 ("Could not load the session" + "Retry", and no
// notification anywhere in 011).
//
// Recognition conventions (from the spec's wording, for the verifier):
// - The screen's own texts are the contract: "Session not found", "Could not load the
//   session", the button "Retry", the line "No entries yet.", the badge text exactly
//   "Archived", and the character link reading the character's name or else "Character".
// - A start-time label is asserted **only by its fixed shape** `YYYY-MM-DD HH:MM`
//   (context.md "Test conventions" — exact values belong to 005's formatter tests, and this
//   file never calls the formatter to compute an expectation).
// - The centre column: the harness wraps the route in a `<main>` landmark, which is what the
//   shell gives the screen in the application. "In the main region" means inside it, and every
//   screen assertion is scoped there (context.md "Scoping").
// - A Mantine `Loader`: `.mantine-Loader-root`; a notification: `.mantine-Notification-root`
//   (the repo's existing conventions).
// - Stubs and request counters key on the **exact** pathname (context.md "Stubs routed by
//   exact path"): `/api/sessions/<id>`, `/api/characters` and `/api/characters/<id>` share
//   prefixes.
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { runInAction } from "mobx";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SessionRoute, SessionScreen } from "../../src/app/SessionScreen";
import type { Character } from "../../src/app/charactersApi";
import { CharactersState } from "../../src/app/charactersState";
import type { Session } from "../../src/app/sessionsApi";
import { AppProviders } from "../../src/shared/AppProviders";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string };
type User = ReturnType<typeof userEvent.setup>;

// ---------------------------------------------------------------- the spec's names
const NOT_FOUND_TEXT = "Session not found";
const LOAD_FAILED_TEXT = "Could not load the session";
const NO_ENTRIES_TEXT = "No entries yet.";
const ARCHIVED_BADGE = "Archived";
const CHARACTER_FALLBACK = "Character";
const RETRY_NAME = /^retry$/i;
const ARCHIVE_NAME = /^archive$/i;
const RESTORE_NAME = /^restore$/i;
const ROW_ACTIONS_NAME = /^actions for /i;

/** D4 / "Test conventions": the start-time label is only ever asserted by this shape. */
const START_LABEL_HEADING = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/;
const START_LABEL_ANYWHERE = /\d{4}-\d{2}-\d{2} \d{2}:\d{2}/;

const LOADER = ".mantine-Loader-root";
const NOTIFICATION = ".mantine-Notification-root";

// ---------------------------------------------------------------- fixtures
// Ids are decimal strings past Number.MAX_SAFE_INTEGER, so any coercion would show in an href.
const CHAR_A_ID = "7250000000000000011";
const CHAR_B_ID = "7250000000000000012";
const SESSION_A_ID = "9007199254740993"; // 2^53 + 1
const SESSION_B_ID = "9007199254740995";
const SETUP_ID = "7250000000000000021";

const CHARACTERS_PATH = "/api/characters";

function sessionPath(sessionId: string): string {
  return `/api/sessions/${sessionId}`;
}

function characterHref(characterId: string): string {
  return `/characters/${characterId}`;
}

function sessionRoutePath(sessionId: string): string {
  return `/sessions/${sessionId}`;
}

const CHAR_A: Character = {
  id: CHAR_A_ID,
  name: "Aria",
  sheet: "A scribe who never finishes a sentence.",
  archived_at: null,
  created_at: "2026-03-14T09:26:53.000000+00:00",
  updated_at: "2026-03-14T09:26:53.000000+00:00",
};

const CHAR_B: Character = {
  id: CHAR_B_ID,
  name: "Bo Kestrel",
  sheet: "A duelist who counts his scars.",
  archived_at: null,
  created_at: "2026-02-01T08:15:42.000000+00:00",
  updated_at: "2026-02-01T08:15:42.000000+00:00",
};

const SETUP_NAME = "Tavern";
const OTHER_SETUP_NAME = "Harbour Gate";

const STAMP_A = "2026-05-10T09:00:00.000000+00:00";
const STAMP_B = "2026-06-02T17:45:00.000000+00:00";

/** A's session: a setup label, working, under CHAR_A. */
const SESSION_A: Session = {
  id: SESSION_A_ID,
  character_id: CHAR_A_ID,
  setup_id: SETUP_ID,
  setup_name: SETUP_NAME,
  archived_at: null,
  last_used_at: STAMP_A,
  created_at: STAMP_A,
  updated_at: STAMP_A,
};

/** The same session with no setup at all (R2: NULL, never a sentinel). */
const SESSION_NO_SETUP: Session = {
  ...SESSION_A,
  setup_id: null,
  setup_name: null,
};

/** Archived, reachable by URL only (D5, R6). */
const ARCHIVED_SESSION: Session = {
  ...SESSION_A,
  archived_at: "2026-05-20T10:00:00.000000+00:00",
  updated_at: "2026-05-20T10:00:00.000000+00:00",
};

/** B's session, under the other character and with its own setup label. */
const SESSION_B: Session = {
  id: SESSION_B_ID,
  character_id: CHAR_B_ID,
  setup_id: SETUP_ID,
  setup_name: OTHER_SETUP_NAME,
  archived_at: null,
  last_used_at: STAMP_B,
  created_at: STAMP_B,
  updated_at: STAMP_B,
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- fetch harness
function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** A domain envelope — the shape every non-2xx of ours carries. */
function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: "ql-77 went wrong.", detail: {} } }, status);
}

function notFoundResponse(): Response {
  return envelope("session_not_found", 404);
}

function serverError(): Response {
  return envelope("internal_error", 500);
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

/** A URL-routed in-memory backend; every request is recorded in order. */
function stubBackend(handler: (request: Seen) => Response | Promise<Response>) {
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>(async (input, init) => {
    const url = requestUrl(input);
    const request: Seen = {
      method: requestMethod(input, init),
      path: url.pathname,
      search: url.search,
    };
    calls.push(request);
    return handler(request);
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

/** Answers a GET of each given session by exact path, and 404s everything else. */
function serveSessions(...rows: Session[]) {
  return stubBackend((request) => {
    if (request.method === "GET") {
      const row = rows.find((candidate) => request.path === sessionPath(candidate.id));
      if (row !== undefined) return jsonResponse(row, 200);
    }
    return notFoundResponse();
  });
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
/** The one workspace characters state (D17: read only, and the screen never writes to it). */
function workspaceWith(...rows: Character[]): CharactersState {
  const characters = new CharactersState();
  runInAction(() => {
    characters.characters = rows.map((row) => ({ ...row }));
    characters.status = rows.length > 0 ? "ready" : "idle";
  });
  return characters;
}

function Probe(props: { to: string }) {
  const navigate = useNavigate();
  const location = useLocation();
  return (
    <div>
      <span data-testid="location">{location.pathname}</span>
      <button type="button" onClick={() => void navigate(props.to)}>
        probe navigate
      </button>
    </div>
  );
}

/**
 * The route of this step, in the `<main>` landmark the shell gives it, with one workspace
 * `CharactersState` and a location/navigation probe beside it (the probe's own controls live
 * outside the main region, so they are invisible to every scoped assertion below).
 */
function renderRoute(initialPath: string, characters: CharactersState, probeTo = initialPath) {
  const view = render(
    <AppProviders>
      <MemoryRouter initialEntries={[initialPath]}>
        <main>
          <Routes>
            <Route path="/sessions/:id" element={<SessionRoute characters={characters} />} />
          </Routes>
        </main>
        <Probe to={probeTo} />
      </MemoryRouter>
    </AppProviders>,
  );
  return { characters, view };
}

/** The component on its own, bound to its two props (no route in between). */
function renderScreen(sessionId: string, characters: CharactersState) {
  const view = render(
    <AppProviders>
      <MemoryRouter initialEntries={[sessionRoutePath(sessionId)]}>
        <main>
          <SessionScreen sessionId={sessionId} characters={characters} />
        </main>
      </MemoryRouter>
    </AppProviders>,
  );
  return { characters, view };
}

// ---------------------------------------------------------------- queries
function mainRegion(): HTMLElement {
  return screen.getByRole("main");
}

function mainText(): string {
  return (mainRegion().textContent ?? "").trim();
}

function mainLink(name: string): HTMLElement {
  return within(mainRegion()).getByRole("link", { name });
}

function queryMainLink(name: string): HTMLElement | null {
  return within(mainRegion()).queryByRole("link", { name });
}

function loaders(): Element[] {
  return Array.from(document.querySelectorAll(LOADER));
}

function notificationsShown(): Element[] {
  return Array.from(document.querySelectorAll(NOTIFICATION));
}

function sessionRequests(calls: Seen[], sessionId: string): Seen[] {
  return calls.filter((call) => call.method === "GET" && call.path === sessionPath(sessionId));
}

// ---------------------------------------------------------------------------
describe("the screen while its session is loading (D17)", () => {
  it("shows a loader while the GET is pending, then the session — DoD-2", async () => {
    const gate = deferred<Response>();
    stubBackend(() => gate.promise);
    renderRoute(sessionRoutePath(SESSION_A_ID), workspaceWith(CHAR_A));

    expect(loaders().length).toBeGreaterThan(0);

    gate.resolve(jsonResponse(SESSION_A, 200));
    await flush();

    expect(loaders()).toEqual([]);
    expect(within(mainRegion()).getByText(NO_ENTRIES_TEXT)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
describe("the ready header names the character, the start time and the empty run", () => {
  it("shows the character's name linking to its page, a start-time label and No entries yet. — DoD-3", async () => {
    const { calls } = serveSessions(SESSION_A);
    renderRoute(sessionRoutePath(SESSION_A_ID), workspaceWith(CHAR_A, CHAR_B));
    await flush();

    const link = mainLink(CHAR_A.name);
    expect(link).toHaveAttribute("href", characterHref(CHAR_A_ID));
    expect(
      within(mainRegion()).getByRole("heading", { name: START_LABEL_HEADING }),
    ).toBeInTheDocument();
    expect(within(mainRegion()).getByText(NO_ENTRIES_TEXT)).toBeInTheDocument();
    expect(sessionRequests(calls, SESSION_A_ID)).toHaveLength(1);
  });

  it("shows the session's setup name in the header — DoD-4", async () => {
    serveSessions(SESSION_A);
    renderRoute(sessionRoutePath(SESSION_A_ID), workspaceWith(CHAR_A));
    await flush();

    expect(within(mainRegion()).getByText(SETUP_NAME)).toBeInTheDocument();
  });

  it("shows nothing where the setup label would be when the session has no setup — DoD-4", async () => {
    serveSessions(SESSION_NO_SETUP);
    renderRoute(sessionRoutePath(SESSION_A_ID), workspaceWith(CHAR_A));
    await flush();

    expect(within(mainRegion()).queryByText(SETUP_NAME)).toBeNull();

    // The header's three pieces and nothing else: the character's name, a start-time label of
    // the fixed shape, and the empty-run line. Whatever is left over is the setup's place.
    const text = mainText();
    expect(text).toContain(CHAR_A.name);
    expect(text).toMatch(START_LABEL_ANYWHERE);
    expect(text).toContain(NO_ENTRIES_TEXT);
    const residue = text
      .replace(CHAR_A.name, "")
      .replace(START_LABEL_ANYWHERE, "")
      .replace(NO_ENTRIES_TEXT, "")
      .trim();
    expect(residue).toBe("");
  });

  it("falls back to Character and fetches nothing when the workspace state has no such row — DoD-5", async () => {
    const { calls } = serveSessions(SESSION_A);
    renderScreen(SESSION_A_ID, workspaceWith());
    await flush();

    const link = mainLink(CHARACTER_FALLBACK);
    expect(link).toHaveAttribute("href", characterHref(CHAR_A_ID));
    expect(queryMainLink(CHAR_A.name)).toBeNull();
    expect(calls.filter((call) => call.path.startsWith(CHARACTERS_PATH))).toEqual([]);
    expect(sessionRequests(calls, SESSION_A_ID)).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
describe("an archived session opened by URL (D5, R6)", () => {
  it("shows the Archived badge and no archive, restore or row-action control — DoD-6", async () => {
    serveSessions(ARCHIVED_SESSION);
    renderRoute(sessionRoutePath(SESSION_A_ID), workspaceWith(CHAR_A));
    await flush();

    expect(within(mainRegion()).getByText(ARCHIVED_BADGE)).toBeInTheDocument();
    expect(within(mainRegion()).getByText(NO_ENTRIES_TEXT)).toBeInTheDocument();
    // Document-wide, because a Mantine menu would render into a portal outside `<main>`.
    expect(screen.queryByRole("button", { name: ARCHIVE_NAME })).toBeNull();
    expect(screen.queryByRole("button", { name: RESTORE_NAME })).toBeNull();
    expect(screen.queryByRole("button", { name: ROW_ACTIONS_NAME })).toBeNull();
    expect(screen.queryByRole("menuitem")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("a session that is not the caller's or does not exist (D17)", () => {
  it("renders Session not found, with no Retry and no notification — DoD-7", async () => {
    stubBackend(() => notFoundResponse());
    renderRoute(sessionRoutePath(SESSION_A_ID), workspaceWith(CHAR_A));
    await flush();

    expect(within(mainRegion()).getByText(NOT_FOUND_TEXT)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: RETRY_NAME })).toBeNull();
    expect(notificationsShown()).toEqual([]);
    expect(within(mainRegion()).queryByText(LOAD_FAILED_TEXT)).toBeNull();
    expect(within(mainRegion()).queryByText(NO_ENTRIES_TEXT)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("a failed load offers one retry (D18)", () => {
  type FailureCase = [label: string, answer: () => Response];

  const FAILURES: FailureCase[] = [
    ["a 500 envelope", serverError],
    [
      "a transport failure",
      () => {
        throw new TypeError("Failed to fetch");
      },
    ],
  ];

  it.each(FAILURES)(
    "%s renders Could not load the session and a Retry, with no notification — DoD-8",
    async (_label, answer) => {
      stubBackend(() => answer());
      renderRoute(sessionRoutePath(SESSION_A_ID), workspaceWith(CHAR_A));
      await flush();

      expect(within(mainRegion()).getByText(LOAD_FAILED_TEXT)).toBeInTheDocument();
      expect(within(mainRegion()).getByRole("button", { name: RETRY_NAME })).toBeInTheDocument();
      expect(notificationsShown()).toEqual([]);
    },
  );

  it("pressing Retry requests the session again and renders it on success — DoD-8", async () => {
    const user = newUser();
    let failNext = true;
    const { calls } = stubBackend((request) => {
      if (request.method === "GET" && request.path === sessionPath(SESSION_A_ID)) {
        if (failNext) {
          failNext = false;
          return serverError();
        }
        return jsonResponse(SESSION_A, 200);
      }
      return notFoundResponse();
    });
    renderRoute(sessionRoutePath(SESSION_A_ID), workspaceWith(CHAR_A));
    await flush();
    expect(sessionRequests(calls, SESSION_A_ID)).toHaveLength(1);

    await user.click(within(mainRegion()).getByRole("button", { name: RETRY_NAME }));
    await flush();

    expect(sessionRequests(calls, SESSION_A_ID)).toHaveLength(2);
    expect(mainLink(CHAR_A.name)).toHaveAttribute("href", characterHref(CHAR_A_ID));
    expect(within(mainRegion()).getByText(NO_ENTRIES_TEXT)).toBeInTheDocument();
    expect(within(mainRegion()).queryByText(LOAD_FAILED_TEXT)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("moving in-entry from one session to another", () => {
  it("requests the second session and shows only its header — DoD-9", async () => {
    const user = newUser();
    const { calls } = serveSessions(SESSION_A, SESSION_B);
    renderRoute(
      sessionRoutePath(SESSION_A_ID),
      workspaceWith(CHAR_A, CHAR_B),
      sessionRoutePath(SESSION_B_ID),
    );
    await flush();
    expect(mainLink(CHAR_A.name)).toHaveAttribute("href", characterHref(CHAR_A_ID));

    await user.click(screen.getByRole("button", { name: /^probe navigate$/i }));
    await flush();

    expect(screen.getByTestId("location").textContent).toBe(sessionRoutePath(SESSION_B_ID));
    expect(sessionRequests(calls, SESSION_B_ID)).toHaveLength(1);
    expect(mainLink(CHAR_B.name)).toHaveAttribute("href", characterHref(CHAR_B_ID));
    expect(within(mainRegion()).getByText(OTHER_SETUP_NAME)).toBeInTheDocument();
    expect(queryMainLink(CHAR_A.name)).toBeNull();
    expect(within(mainRegion()).queryByText(SETUP_NAME)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe("nothing of 012 or 013 is on this screen yet (D17)", () => {
  it("the ready main region holds no textbox and no button — DoD-10", async () => {
    serveSessions(SESSION_A);
    renderRoute(sessionRoutePath(SESSION_A_ID), workspaceWith(CHAR_A));
    await flush();

    expect(within(mainRegion()).getByText(NO_ENTRIES_TEXT)).toBeInTheDocument();
    expect(within(mainRegion()).queryAllByRole("textbox")).toEqual([]);
    expect(within(mainRegion()).queryAllByRole("button")).toEqual([]);
    expect(notificationsShown()).toEqual([]);
  });
});
