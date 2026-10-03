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
//
// Amended by feature 013, step 007 (DoD-6..DoD-8): the ready render now mounts the session's
// stream (013 D13) in place of 011's "No entries yet." line, which is now the empty record's
// line and appears only **after** the stream loads (find, not get). Every case that reaches the
// ready render stubs `GET /api/sessions/<id>/entries` → `{ "entries": [] }` and
// `GET /api/sessions/<id>/zone` → `{ "messages": [] }` by exact path (`serveSessions` and
// `streamAnswer`). 011 DoD-10 ("no textbox and no button") is **replaced** by 013 DoD-6 (the
// composer, Send and Settle are expected; Archive / Restore / "Actions for …" stay absent).
// 011 DoD-5's request count now allows exactly the two stream GETs besides the session's own.
// 011 DoD-4's "nothing else in the header" check is scoped to the header block (the ancestor of
// the start-time heading that does not contain the stream), since the stream's own texts now
// share the main region. 011 DoD-6 and DoD-9 keep their assertions with widened stubs. The 013
// clauses are in the block at the bottom, under a describe naming 013 step 007, so their
// "— DoD-N" tags are 013 step 007's.
//
// Amended by feature 015, step 008 (DoD-10): the ready render now also mounts the session's
// "Notes" section, which reads `GET /api/sessions/<id>/memo-chain` on mount. `streamAnswer`
// answers that exact path too (`{ "levels": [] }` unless a test supplies a chain), so every
// ready-state case keeps its meaning; 011 DoD-5's exact request list gains that one GET. 011
// DoD-10's "no textbox and no button" clause no longer exists (013 step 007 replaced it with the
// Archive / Restore / "Actions for …" absence checks, which no Notes control is named like), so
// there is nothing left to scope. `Seen` now records the parsed JSON body (for 015's PATCH
// clause), and `src/shared/MarkdownEditor` is replaced by step 007's labelled-`<textarea>` stub
// (id from React's `useId`) so the notes' editors can be typed into. No other assertion changes.
// The 015 clauses are in the last block, under a describe naming 015 step 008, so their
// "— DoD-N" tags are 015 step 008's.
//
// Amended by feature 016, step 006 (DoD-1..DoD-12; D1–D4, and 016 D5's table rows for 015 008
// DoD-7/8/9): `SessionScreenProps` and `SessionRouteProps` gained a required `storage`
// (`LayoutStorage | null`), so `renderRoute` / `renderScreen` pass one — `null` unless a test
// supplies an in-memory fake. The ready render is now the note wall's layout: 011's header (with
// an "Open notes" control while the wall is not visible) and 013's stream in the stream column,
// and 015's "Notes" region **moved** into the complementary landmark "Note wall", which is closed
// (aria-hidden) by default. So the 015 step 008 clauses that read the Notes region are amended:
// absence checks query with `{ hidden: true }` (now 016 006 DoD-8), the ready placement clause
// becomes 016 006 DoD-11 (and DoD-1), and the a→b clauses open the wall before reading or typing
// (016 006 DoD-10 / DoD-11). Each amended title names its 015 item and ends with the 016 006
// "— DoD-N". The new 016 clauses are in the last block. A narrow viewport is a `window.matchMedia`
// stub matching exactly `(width < 820px)`, restored after each test (WorkspaceShell.test.tsx's
// shape). A "reload" is `unmount()` then rendering again with the same storage fake. No other 011
// / 013 / 015 assertion changes.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { runInAction } from "mobx";
import type { ChangeEvent } from "react";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SessionRoute, SessionScreen } from "../../src/app/SessionScreen";
import type { Character } from "../../src/app/charactersApi";
import { CharactersState } from "../../src/app/charactersState";
import type { Memo, MemoChainLevel, MemoScope } from "../../src/app/memosApi";
import type { Session } from "../../src/app/sessionsApi";
import type { Message, MessageKind } from "../../src/app/streamApi";
import type { LayoutStorage } from "../../src/app/workspaceLayout";
import { AppProviders } from "../../src/shared/AppProviders";

// 015 step 008: the notes' editors, as step 007's MemoLevelGroup.test.tsx stubs them.
vi.mock("../../src/shared/MarkdownEditor", async () => {
  const { createElement, useId } = await import("react");
  type StubProps = {
    label: string;
    value: string;
    onChange: (markdown: string) => void;
    readOnly?: boolean;
  };
  return {
    MarkdownEditor: (props: StubProps) => {
      const id = `markdown-editor-${useId()}`;
      return createElement(
        "div",
        null,
        createElement("label", { htmlFor: id }, props.label),
        createElement("textarea", {
          id,
          value: props.value,
          readOnly: props.readOnly ?? false,
          onChange: (event: ChangeEvent<HTMLTextAreaElement>) => props.onChange(event.target.value),
        }),
      );
    },
  };
});

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string; body: unknown };
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

// 016 step 006: tests/setup.ts's polyfill answers `matches: false` for every query (the wide
// case); a narrow test replaces it, and it is restored after each test.
const originalMatchMedia = window.matchMedia;

function installMatchMedia(value: typeof window.matchMedia): void {
  Object.defineProperty(window, "matchMedia", { writable: true, configurable: true, value });
}

afterEach(() => {
  installMatchMedia(originalMatchMedia);
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

/** 015 step 008: the parsed JSON body of a request, undefined when it has none. */
function parseBody(init?: RequestInit): unknown {
  const raw = init?.body;
  if (raw === undefined || raw === null) return undefined;
  return JSON.parse(String(raw)) as unknown;
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
      body: parseBody(init),
    };
    calls.push(request);
    return handler(request);
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

/** 013 step 007: the stream's two reads, by exact path. */
function entriesPath(sessionId: string): string {
  return `/api/sessions/${sessionId}/entries`;
}

function zonePath(sessionId: string): string {
  return `/api/sessions/${sessionId}/zone`;
}

/** 015 step 008: the Notes section's one read, by exact path. */
function memoChainPath(sessionId: string): string {
  return `/api/sessions/${sessionId}/memo-chain`;
}

/**
 * 013 step 007: answers a GET of `<id>/entries` or `<id>/zone` for any of the given session
 * ids (entries from `entriesBy`, else empty; the zone always empty), or undefined.
 * 015 step 008: also a GET of `<id>/memo-chain` (levels from `chainsBy`, else none).
 */
function streamAnswer(
  request: Seen,
  sessionIds: string[],
  entriesBy: Record<string, Message[]> = {},
  chainsBy: Record<string, MemoChainLevel[]> = {},
): Response | undefined {
  if (request.method !== "GET") return undefined;
  for (const id of sessionIds) {
    if (request.path === entriesPath(id)) return jsonResponse({ entries: entriesBy[id] ?? [] }, 200);
    if (request.path === zonePath(id)) return jsonResponse({ messages: [] }, 200);
    if (request.path === memoChainPath(id)) return jsonResponse({ levels: chainsBy[id] ?? [] }, 200);
  }
  return undefined;
}

/**
 * Answers a GET of each given session by exact path, and (013 step 007) its stream's entries
 * and zone, and 404s everything else.
 */
function serveSessionsWith(entriesBy: Record<string, Message[]>, ...rows: Session[]) {
  const ids = rows.map((row) => row.id);
  return stubBackend((request) => {
    if (request.method === "GET") {
      const row = rows.find((candidate) => request.path === sessionPath(candidate.id));
      if (row !== undefined) return jsonResponse(row, 200);
    }
    return streamAnswer(request, ids, entriesBy) ?? notFoundResponse();
  });
}

function serveSessions(...rows: Session[]) {
  return serveSessionsWith({}, ...rows);
}

const ENTRY_STAMP = "2026-05-10T09:30:00.000000+00:00";

/** A settled entry with all eight keys. */
function settledEntry(sessionId: string, id: string, kind: MessageKind, text: string): Message {
  return {
    id,
    session_id: sessionId,
    role: "user",
    kind,
    text,
    settled_at: ENTRY_STAMP,
    created_at: ENTRY_STAMP,
    updated_at: ENTRY_STAMP,
  };
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
function renderRoute(
  initialPath: string,
  characters: CharactersState,
  probeTo = initialPath,
  storage: LayoutStorage | null = null, // 016 step 006: the required layout storage
) {
  const view = render(
    <AppProviders>
      <MemoryRouter initialEntries={[initialPath]}>
        <main>
          <Routes>
            <Route
              path="/sessions/:id"
              element={<SessionRoute characters={characters} storage={storage} />}
            />
          </Routes>
        </main>
        <Probe to={probeTo} />
      </MemoryRouter>
    </AppProviders>,
  );
  return { characters, view };
}

/** The component on its own, bound to its props (no route in between). */
function renderScreen(
  sessionId: string,
  characters: CharactersState,
  storage: LayoutStorage | null = null, // 016 step 006: the required layout storage
) {
  const view = render(
    <AppProviders>
      <MemoryRouter initialEntries={[sessionRoutePath(sessionId)]}>
        <main>
          <SessionScreen sessionId={sessionId} characters={characters} storage={storage} />
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

function getRequests(calls: Seen[], path: string): Seen[] {
  return calls.filter((call) => call.method === "GET" && call.path === path);
}

/** 013 step 007: the stream's composer, which only a ready stream renders. */
function mainComposer(): HTMLElement {
  return within(mainRegion()).getByRole("textbox", { name: "Composer" });
}

/**
 * 013 step 007: the header block — the outermost ancestor of the start-time heading that does
 * not also contain the stream (its composer). 011's header stays outside the stream (007
 * Interface intent), so this is the header and nothing of the stream.
 */
function headerBlock(): HTMLElement {
  const stream = mainComposer();
  let block: HTMLElement = within(mainRegion()).getByRole("heading", { name: START_LABEL_HEADING });
  while (block.parentElement !== null && !block.parentElement.contains(stream)) {
    block = block.parentElement;
  }
  return block;
}

// ---------------------------------------------------------------------------
describe("the screen while its session is loading (D17)", () => {
  it("shows a loader while the GET is pending, then the session — DoD-2", async () => {
    const gate = deferred<Response>();
    // 013 step 007: only the session's own GET is gated; the stream's two reads answer empty.
    stubBackend(
      (request) =>
        streamAnswer(request, [SESSION_A_ID]) ??
        (request.method === "GET" && request.path === sessionPath(SESSION_A_ID)
          ? gate.promise
          : notFoundResponse()),
    );
    renderRoute(sessionRoutePath(SESSION_A_ID), workspaceWith(CHAR_A));

    expect(loaders().length).toBeGreaterThan(0);

    gate.resolve(jsonResponse(SESSION_A, 200));
    await flush();

    expect(await within(mainRegion()).findByText(NO_ENTRIES_TEXT)).toBeInTheDocument();
    expect(loaders()).toEqual([]);
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
    expect(await within(mainRegion()).findByText(NO_ENTRIES_TEXT)).toBeInTheDocument();
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

    expect(await within(mainRegion()).findByText(NO_ENTRIES_TEXT)).toBeInTheDocument();
    expect(within(mainRegion()).queryByText(SETUP_NAME)).toBeNull();
    expect(mainText()).toContain(NO_ENTRIES_TEXT);

    // The header's pieces and nothing else: the character's name and a start-time label of the
    // fixed shape. Whatever is left over is the setup's place. (013 step 007: scoped to the
    // header block, because the stream's own texts now share the main region.)
    const text = (headerBlock().textContent ?? "").trim();
    expect(text).toContain(CHAR_A.name);
    expect(text).toMatch(START_LABEL_ANYWHERE);
    const residue = text.replace(CHAR_A.name, "").replace(START_LABEL_ANYWHERE, "").trim();
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
    // 013 step 007: exactly the stream's two GETs besides the session's own.
    // 015 step 008: and the Notes section's one memo-chain GET.
    expect(calls.map((call) => `${call.method} ${call.path}`).sort()).toEqual(
      [
        `GET ${sessionPath(SESSION_A_ID)}`,
        `GET ${entriesPath(SESSION_A_ID)}`,
        `GET ${zonePath(SESSION_A_ID)}`,
        `GET ${memoChainPath(SESSION_A_ID)}`,
      ].sort(),
    );
  });
});

// ---------------------------------------------------------------------------
describe("an archived session opened by URL (D5, R6)", () => {
  it("shows the Archived badge and no archive, restore or row-action control — DoD-6", async () => {
    serveSessions(ARCHIVED_SESSION);
    renderRoute(sessionRoutePath(SESSION_A_ID), workspaceWith(CHAR_A));
    await flush();

    expect(within(mainRegion()).getByText(ARCHIVED_BADGE)).toBeInTheDocument();
    expect(await within(mainRegion()).findByText(NO_ENTRIES_TEXT)).toBeInTheDocument();
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
      // 013 step 007: the ready render's stream reads answer empty.
      return streamAnswer(request, [SESSION_A_ID]) ?? notFoundResponse();
    });
    renderRoute(sessionRoutePath(SESSION_A_ID), workspaceWith(CHAR_A));
    await flush();
    expect(sessionRequests(calls, SESSION_A_ID)).toHaveLength(1);

    await user.click(within(mainRegion()).getByRole("button", { name: RETRY_NAME }));
    await flush();

    expect(sessionRequests(calls, SESSION_A_ID)).toHaveLength(2);
    expect(mainLink(CHAR_A.name)).toHaveAttribute("href", characterHref(CHAR_A_ID));
    expect(await within(mainRegion()).findByText(NO_ENTRIES_TEXT)).toBeInTheDocument();
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
// Feature 013, step 007 — the stream on the session screen. 011 DoD-10 ("no textbox and no
// button") is replaced by DoD-6 below; every "— DoD-N" in this block is 013 step 007's.
describe("013 step 007 — the session screen mounts the stream (US-125.AC-1, R6, D13)", () => {
  it("ready with empty entries and zone: the header, No entries yet., the Composer, Send and Settle, and no archive control — DoD-6", async () => {
    const { calls } = serveSessions(SESSION_A);
    renderRoute(sessionRoutePath(SESSION_A_ID), workspaceWith(CHAR_A));
    await flush();

    const main = within(mainRegion());
    expect(mainLink(CHAR_A.name)).toHaveAttribute("href", characterHref(CHAR_A_ID));
    expect(main.getByRole("heading", { name: START_LABEL_HEADING })).toBeInTheDocument();
    expect(await main.findByText(NO_ENTRIES_TEXT)).toBeInTheDocument();
    expect(mainComposer()).toBeInTheDocument();
    expect(main.getByRole("button", { name: "Send" })).toBeInTheDocument();
    expect(main.getByRole("button", { name: "Settle" })).toBeInTheDocument();
    expect(getRequests(calls, entriesPath(SESSION_A_ID))).toHaveLength(1);
    expect(getRequests(calls, zonePath(SESSION_A_ID))).toHaveLength(1);

    // Document-wide, because a Mantine menu would render into a portal outside `<main>`.
    expect(screen.queryByRole("button", { name: ARCHIVE_NAME })).toBeNull();
    expect(screen.queryByRole("button", { name: RESTORE_NAME })).toBeNull();
    expect(screen.queryByRole("button", { name: ROW_ACTIONS_NAME })).toBeNull();
    expect(notificationsShown()).toEqual([]);
  });

  it("an archived session shows the Archived badge and a working stream whose composer enables Send and Settle — DoD-7", async () => {
    const user = newUser();
    serveSessions(ARCHIVED_SESSION);
    renderRoute(sessionRoutePath(SESSION_A_ID), workspaceWith(CHAR_A));
    await flush();

    const main = within(mainRegion());
    expect(main.getByText(ARCHIVED_BADGE)).toBeInTheDocument();
    expect(await main.findByText(NO_ENTRIES_TEXT)).toBeInTheDocument();
    expect(main.getByRole("separator", { name: "Current zone" })).toBeInTheDocument();

    const composer = mainComposer();
    expect(composer).toBeEnabled();
    await user.type(composer, "Still writing here.");

    expect(composer).toHaveValue("Still writing here.");
    expect(main.getByRole("button", { name: "Send" })).toBeEnabled();
    expect(main.getByRole("button", { name: "Settle" })).toBeEnabled();
  });

  it("navigating in-entry from a to b requests b's session, entries and zone and shows only b's record — DoD-8", async () => {
    const user = newUser();
    const A_TEXT = "A's partner waits at the well.";
    const B_TEXT = "B's duelist sheathes his blade.";
    const { calls } = serveSessionsWith(
      {
        [SESSION_A_ID]: [settledEntry(SESSION_A_ID, "7250000000000000501", "partner", A_TEXT)],
        [SESSION_B_ID]: [settledEntry(SESSION_B_ID, "7250000000000000502", "turn", B_TEXT)],
      },
      SESSION_A,
      SESSION_B,
    );
    renderRoute(
      sessionRoutePath(SESSION_A_ID),
      workspaceWith(CHAR_A, CHAR_B),
      sessionRoutePath(SESSION_B_ID),
    );
    await flush();
    expect(await within(mainRegion()).findByText(A_TEXT)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^probe navigate$/i }));
    await flush();

    expect(screen.getByTestId("location").textContent).toBe(sessionRoutePath(SESSION_B_ID));
    expect(sessionRequests(calls, SESSION_B_ID)).toHaveLength(1);
    expect(getRequests(calls, entriesPath(SESSION_B_ID)).length).toBeGreaterThanOrEqual(1);
    expect(getRequests(calls, zonePath(SESSION_B_ID)).length).toBeGreaterThanOrEqual(1);

    expect(await within(mainRegion()).findByText(B_TEXT)).toBeInTheDocument();
    const records = within(mainRegion()).getAllByRole("list", { name: "Settled record" });
    expect(records).toHaveLength(1);
    expect(records[0].textContent).toContain(B_TEXT);
    expect(records[0].textContent).not.toContain(A_TEXT);
    expect(within(mainRegion()).queryByText(A_TEXT)).toBeNull();
    expect(within(mainRegion()).getAllByRole("separator", { name: "Current zone" })).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// Feature 015, step 008 — the session's "Notes" section on the screen (D1, D5, D16). Every
// "— DoD-N" in this block is 015 step 008's. Notes are read through their "Note" editors (the
// MarkdownEditor stub's textareas); requests are matched by exact method + pathname.
const NOTES_REGION = "Notes";
const NOTE_LABEL = "Note";
const MEMO_STAMP = "2026-10-02T09:26:53.000000+00:00";

function memoRow(id: string, scope: MemoScope, scopeId: string | null, body: string): Memo {
  return {
    id,
    scope,
    scope_id: scopeId,
    body,
    is_enabled: true,
    is_forced: false,
    sort_key: 0,
    created_at: MEMO_STAMP,
    updated_at: MEMO_STAMP,
  };
}

function memoPath(memoId: string): string {
  return `/api/memos/${memoId}`;
}

const A_CHAR_NOTE_ID = "7250000000000000301";
const A_SESSION_NOTE_ID = "7250000000000000302";
const B_CHAR_NOTE_ID = "7250000000000000311";
const B_SESSION_NOTE_ID = "7250000000000000312";

const A_CHAR_NOTE = "Aria never finishes a sentence.";
const A_SESSION_NOTE = "The well is dry tonight.";
const B_CHAR_NOTE = "Bo counts his scars aloud.";
const B_SESSION_NOTE = "The duel is at dawn.";

/** A's chain: user, character, setup (A has one), session. */
const CHAIN_A: MemoChainLevel[] = [
  { scope: "user", scope_id: null, memos: [] },
  { scope: "character", scope_id: CHAR_A_ID, memos: [memoRow(A_CHAR_NOTE_ID, "character", CHAR_A_ID, A_CHAR_NOTE)] },
  { scope: "setup", scope_id: SETUP_ID, memos: [] },
  {
    scope: "session",
    scope_id: SESSION_A_ID,
    memos: [memoRow(A_SESSION_NOTE_ID, "session", SESSION_A_ID, A_SESSION_NOTE)],
  },
];

/** B's chain, with B's own notes. */
const CHAIN_B: MemoChainLevel[] = [
  { scope: "user", scope_id: null, memos: [] },
  { scope: "character", scope_id: CHAR_B_ID, memos: [memoRow(B_CHAR_NOTE_ID, "character", CHAR_B_ID, B_CHAR_NOTE)] },
  { scope: "setup", scope_id: SETUP_ID, memos: [] },
  {
    scope: "session",
    scope_id: SESSION_B_ID,
    memos: [memoRow(B_SESSION_NOTE_ID, "session", SESSION_B_ID, B_SESSION_NOTE)],
  },
];

/**
 * The given sessions, their streams and their chains by exact path, plus a PATCH of any held
 * note answered with the merged row and a later updated_at. Everything else 404s.
 */
function serveSessionsWithChains(chainsBy: Record<string, MemoChainLevel[]>, ...rows: Session[]) {
  const ids = rows.map((row) => row.id);
  const notes = new Map<string, Memo>();
  for (const levels of Object.values(chainsBy)) {
    for (const level of levels) for (const note of level.memos) notes.set(note.id, note);
  }
  return stubBackend((request) => {
    if (request.method === "GET") {
      const row = rows.find((candidate) => request.path === sessionPath(candidate.id));
      if (row !== undefined) return jsonResponse(row, 200);
    }
    if (request.method === "PATCH") {
      const note = [...notes.values()].find((candidate) => request.path === memoPath(candidate.id));
      if (note !== undefined) {
        const next: Memo = {
          ...note,
          ...(request.body as Partial<Memo>),
          updated_at: "2026-10-02T09:45:00.000000+00:00",
        };
        notes.set(next.id, next);
        return jsonResponse(next, 200);
      }
    }
    return streamAnswer(request, ids, {}, chainsBy) ?? notFoundResponse();
  });
}

/**
 * The Notes region inside the main region. 016 step 006: it now sits in the "Note wall",
 * which is aria-hidden while closed, so `hidden` must be true to find it on a closed wall.
 */
function notesRegion(hidden = false): HTMLElement {
  return within(mainRegion()).getByRole("region", { name: NOTES_REGION, hidden });
}

/** 016 step 006: presence only, so a closed wall's region counts too (`{ hidden: true }`). */
function queryNotesRegion(): HTMLElement | null {
  return screen.queryByRole("region", { name: NOTES_REGION, hidden: true });
}

function noteBodies(hidden = false): string[] {
  return within(notesRegion(hidden))
    .queryAllByRole("textbox", { name: NOTE_LABEL, hidden })
    .map((box) => (box as HTMLTextAreaElement).value);
}

function isAfter(earlier: Node, later: Node): boolean {
  return (earlier.compareDocumentPosition(later) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

// ---------------------------------------------------------------- 016 step 006: the wall
const WALL_NAME = "Note wall";
const OPEN_NOTES_NAME = "Open notes";
const PIN_NOTES_NAME = "Pin notes";
const UNPIN_NOTES_NAME = "Unpin notes";
const CLOSE_NOTES_NAME = "Close notes";
const LAYOUT_KEY = "rphelper.workspace-layout";
const NARROW_QUERY = "(width < 820px)";

type GetItem = (key: string) => string | null;
type SetItem = (key: string, value: string) => void;

/** A file-local in-memory `LayoutStorage`; both members are spies, writes land in `entries`. */
function fakeStorage(record?: { navCollapsed: boolean; wallPinned: boolean }) {
  const entries = new Map<string, string>();
  if (record !== undefined) entries.set(LAYOUT_KEY, JSON.stringify(record));
  const getItem = vi.fn<GetItem>((key) => entries.get(key) ?? null);
  const setItem = vi.fn<SetItem>((key, value) => {
    entries.set(key, value);
  });
  const storage: LayoutStorage = { getItem, setItem };
  return { storage, getItem, setItem, entries };
}

/** The stored layout record, parsed from the raw JSON under the layout key. */
function storedRecord(entries: Map<string, string>): Record<string, unknown> {
  const raw = entries.get(LAYOUT_KEY);
  expect(raw).toBeDefined();
  return JSON.parse(raw ?? "null") as Record<string, unknown>;
}

/** Replaces `window.matchMedia` with one matching exactly the narrow query. */
function stubNarrowViewport(): void {
  installMatchMedia(
    (query: string): MediaQueryList => ({
      matches: query === NARROW_QUERY,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  );
}

/**
 * Complementary landmarks labelled "Note wall" under `root`, accessible or not. The name is
 * read from `aria-label` rather than a role-query `name` filter: the installed
 * dom-accessibility-api computes an empty name for an element that itself carries
 * aria-hidden="true", so a name-filtered hidden query can never match the closed wall.
 */
function wallsUnder(root: HTMLElement): HTMLElement[] {
  return within(root)
    .queryAllByRole("complementary", { hidden: true })
    .filter((el) => el.getAttribute("aria-label") === WALL_NAME);
}

/** The wall inside the main region, accessible or not — exactly one. */
function anyWall(): HTMLElement {
  const walls = wallsUnder(mainRegion());
  expect(walls).toHaveLength(1);
  return walls[0];
}

/**
 * Anything wall-like, anywhere, accessible or not; null when none exists. Non-null when any
 * complementary landmark (hidden included) or any element labelled "Note wall" is present.
 */
function queryAnyWall(): HTMLElement | null {
  const complementary = screen.queryAllByRole("complementary", { hidden: true });
  if (complementary.length > 0) return complementary[0];
  return document.querySelector<HTMLElement>(`[aria-label="${WALL_NAME}"]`);
}

/** The wall inside the main region, found only while accessible. */
function accessibleWall(): HTMLElement {
  return within(mainRegion()).getByRole("complementary", { name: WALL_NAME });
}

function wallIsAccessible(): boolean {
  return screen.queryByRole("complementary", { name: WALL_NAME }) !== null;
}

function openNotesButton(): HTMLElement {
  return within(mainRegion()).getByRole("button", { name: OPEN_NOTES_NAME });
}

/** "Open notes" anywhere, even inside an aria-hidden subtree. */
function queryOpenNotes(): HTMLElement | null {
  return screen.queryByRole("button", { name: OPEN_NOTES_NAME, hidden: true });
}

function wallControl(name: string): HTMLElement {
  return within(accessibleWall()).getByRole("button", { name });
}

function chainRequests(calls: Seen[], sessionId: string): Seen[] {
  return getRequests(calls, memoChainPath(sessionId));
}

describe("015 step 008 — the session screen mounts the Notes section (D1, D16)", () => {
  it("ready (015 008 DoD-7, amended by 016 D4): the Notes region sits inside the Note wall in the main region, after the session header and the stream, from one memo-chain read — DoD-11", async () => {
    const { calls } = serveSessionsWithChains({ [SESSION_A_ID]: CHAIN_A }, SESSION_A);
    renderRoute(sessionRoutePath(SESSION_A_ID), workspaceWith(CHAR_A));
    await flush();

    await waitFor(() => {
      expect(wallsUnder(mainRegion())).toHaveLength(1);
    });
    const wall = anyWall();
    expect(wall.getAttribute("aria-label")).toBe(WALL_NAME);
    expect(mainRegion().contains(wall)).toBe(true);
    const notes = within(wall).getByRole("region", { name: NOTES_REGION, hidden: true });
    expect(
      within(notes).getByRole("heading", { name: NOTES_REGION, hidden: true }),
    ).toBeInTheDocument();

    const header = within(mainRegion()).getByRole("heading", { name: START_LABEL_HEADING });
    expect(header.contains(notes)).toBe(false);
    expect(isAfter(header, notes)).toBe(true);
    expect(headerBlock().contains(notes)).toBe(false);
    expect(isAfter(mainLink(CHAR_A.name), notes)).toBe(true);
    // After the screen's existing ready content: the stream (its composer) precedes the section.
    expect(isAfter(mainComposer(), notes)).toBe(true);
    expect(isAfter(headerBlock(), wall)).toBe(true);
    expect(headerBlock().contains(wall)).toBe(false);

    expect(getRequests(calls, memoChainPath(SESSION_A_ID))).toHaveLength(1);
    await waitFor(() => {
      expect(noteBodies(true)).toEqual([A_CHAR_NOTE, A_SESSION_NOTE]);
    });
  });

  it("(015 008 DoD-7, amended) while the session is loading there is no Notes region, not even hidden, and no memo-chain request — DoD-8", async () => {
    const gate = deferred<Response>();
    const { calls } = stubBackend(
      (request) =>
        streamAnswer(request, [SESSION_A_ID]) ??
        (request.method === "GET" && request.path === sessionPath(SESSION_A_ID)
          ? gate.promise
          : notFoundResponse()),
    );
    renderRoute(sessionRoutePath(SESSION_A_ID), workspaceWith(CHAR_A));
    await flush();

    expect(loaders().length).toBeGreaterThan(0);
    expect(queryNotesRegion()).toBeNull();
    expect(getRequests(calls, memoChainPath(SESSION_A_ID))).toEqual([]);

    gate.resolve(jsonResponse(SESSION_A, 200));
    await flush();
    expect(
      await within(mainRegion()).findByRole("region", { name: NOTES_REGION, hidden: true }),
    ).toBeInTheDocument();
  });

  it("(015 008 DoD-7, amended) Session not found renders no Notes region, not even hidden, and makes no memo-chain request — DoD-8", async () => {
    const { calls } = stubBackend(() => notFoundResponse());
    renderRoute(sessionRoutePath(SESSION_A_ID), workspaceWith(CHAR_A));
    await flush();

    expect(within(mainRegion()).getByText(NOT_FOUND_TEXT)).toBeInTheDocument();
    expect(queryNotesRegion()).toBeNull();
    expect(getRequests(calls, memoChainPath(SESSION_A_ID))).toEqual([]);
  });

  type FailureCase = [label: string, answer: () => Response];

  const LOAD_FAILURES: FailureCase[] = [
    ["a 500 envelope", serverError],
    [
      "a transport failure",
      () => {
        throw new TypeError("Failed to fetch");
      },
    ],
  ];

  it.each(LOAD_FAILURES)(
    "(015 008 DoD-7, amended) %s: Could not load the session renders no Notes region, not even hidden, and makes no memo-chain request — DoD-8",
    async (_label, answer) => {
      const { calls } = stubBackend(() => answer());
      renderRoute(sessionRoutePath(SESSION_A_ID), workspaceWith(CHAR_A));
      await flush();

      expect(within(mainRegion()).getByText(LOAD_FAILED_TEXT)).toBeInTheDocument();
      expect(queryNotesRegion()).toBeNull();
      expect(getRequests(calls, memoChainPath(SESSION_A_ID))).toEqual([]);
    },
  );

  it("(015 008 DoD-8, amended) navigating in-entry from a with the wall open to b shows b's wall closed again, requests b's memo chain, and opening it shows b's notes with none of a's — DoD-10", async () => {
    const user = newUser();
    const { calls } = serveSessionsWithChains(
      { [SESSION_A_ID]: CHAIN_A, [SESSION_B_ID]: CHAIN_B },
      SESSION_A,
      SESSION_B,
    );
    renderRoute(
      sessionRoutePath(SESSION_A_ID),
      workspaceWith(CHAR_A, CHAR_B),
      sessionRoutePath(SESSION_B_ID),
    );
    await flush();
    await user.click(openNotesButton());
    await flush();
    expect(wallIsAccessible()).toBe(true);
    await waitFor(() => {
      expect(noteBodies()).toEqual([A_CHAR_NOTE, A_SESSION_NOTE]);
    });
    expect(getRequests(calls, memoChainPath(SESSION_B_ID))).toEqual([]);

    await user.click(screen.getByRole("button", { name: /^probe navigate$/i }));
    await flush();

    expect(screen.getByTestId("location").textContent).toBe(sessionRoutePath(SESSION_B_ID));
    expect(mainLink(CHAR_B.name)).toHaveAttribute("href", characterHref(CHAR_B_ID));
    // Open resets per session (016 D2): b's wall is closed and offers "Open notes".
    expect(wallIsAccessible()).toBe(false);
    expect(anyWall()).toBeInTheDocument();
    expect(openNotesButton()).toBeInTheDocument();
    expect(getRequests(calls, memoChainPath(SESSION_B_ID))).toHaveLength(1);

    await user.click(openNotesButton());
    await flush();
    expect(wallIsAccessible()).toBe(true);
    await waitFor(() => {
      expect(noteBodies()).toEqual([B_CHAR_NOTE, B_SESSION_NOTE]);
    });
    expect(
      within(mainRegion()).getAllByRole("region", { name: NOTES_REGION, hidden: true }),
    ).toHaveLength(1);
    const shown = noteBodies();
    expect(shown).not.toContain(A_CHAR_NOTE);
    expect(shown).not.toContain(A_SESSION_NOTE);
  });

  it("(015 008 DoD-9, amended) with the wall opened first, typing into a note on a without blurring, then navigating to b, PATCHes that note's new body — DoD-11", async () => {
    const user = newUser();
    const { calls } = serveSessionsWithChains(
      { [SESSION_A_ID]: CHAIN_A, [SESSION_B_ID]: CHAIN_B },
      SESSION_A,
      SESSION_B,
    );
    renderRoute(
      sessionRoutePath(SESSION_A_ID),
      workspaceWith(CHAR_A, CHAR_B),
      sessionRoutePath(SESSION_B_ID),
    );
    await flush();
    await user.click(openNotesButton());
    await flush();
    await waitFor(() => {
      expect(noteBodies()).toEqual([A_CHAR_NOTE, A_SESSION_NOTE]);
    });
    const typed = "The well is full again by morning.";

    const sessionNoteBox = within(notesRegion())
      .getAllByRole("textbox", { name: NOTE_LABEL })
      .find((box) => (box as HTMLTextAreaElement).value === A_SESSION_NOTE);
    if (sessionNoteBox === undefined) throw new Error("a's session note editor is missing");
    fireEvent.change(sessionNoteBox, { target: { value: typed } });
    await flush();
    expect(calls.filter((call) => call.method === "PATCH")).toEqual([]);

    await user.click(screen.getByRole("button", { name: /^probe navigate$/i }));
    await flush();

    expect(screen.getByTestId("location").textContent).toBe(sessionRoutePath(SESSION_B_ID));
    await waitFor(() => {
      expect(calls.filter((call) => call.method === "PATCH").length).toBeGreaterThanOrEqual(1);
    });
    const patches = calls.filter((call) => call.method === "PATCH");
    expect(patches).toContainEqual({
      method: "PATCH",
      path: memoPath(A_SESSION_NOTE_ID),
      search: "",
      body: { body: typed },
    });
    expect(patches.every((call) => call.path === memoPath(A_SESSION_NOTE_ID))).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Feature 016, step 006 — the note wall on the session screen (US-094, US-095, UC-072; D1–D4).
// Every "— DoD-N" in this block is 016 step 006's. The wall is the complementary "Note wall";
// a closed wall is queried with `{ hidden: true }`, and "not accessible" means not found by role
// without it. Layout writes are read back from the raw JSON under "rphelper.workspace-layout".
const YOUR_NOTES = "Your notes";
const CHARACTER_NOTES = "Character notes";
const SETUP_NOTES = "Setup notes";
const SESSION_NOTES = "Session notes";

/** A's chain for a session with no setup: user, character, session. */
const CHAIN_A_NO_SETUP: MemoChainLevel[] = CHAIN_A.filter((level) => level.scope !== "setup");

const A_PATH = sessionRoutePath(SESSION_A_ID);

/** One group of the open wall's Notes region, by its title. */
function groupRegion(title: string): HTMLElement {
  return within(notesRegion()).getByRole("region", { name: title });
}

function groupBodies(title: string): string[] {
  return within(groupRegion(title))
    .queryAllByRole("textbox", { name: NOTE_LABEL })
    .map((box) => (box as HTMLTextAreaElement).value);
}

/** The open wall's "Note" editor currently holding `value`. */
function noteBoxHolding(value: string): HTMLTextAreaElement {
  const box = within(notesRegion())
    .getAllByRole("textbox", { name: NOTE_LABEL })
    .find((candidate) => (candidate as HTMLTextAreaElement).value === value);
  if (box === undefined) throw new Error(`no note editor holds "${value}"`);
  return box as HTMLTextAreaElement;
}

const PINNED_RECORD = { navCollapsed: true, wallPinned: true };
const UNPINNED_RECORD = { navCollapsed: true, wallPinned: false };

describe("016 step 006 — the ready session screen is the note wall's home (US-094.AC-1, D1, D3, D4)", () => {
  it("ready with an empty layout storage: the header with Open notes and the stream, no accessible complementary, the hidden Note wall in the main region holding Notes, one memo-chain read — DoD-1", async () => {
    const store = fakeStorage();
    const { calls } = serveSessionsWithChains({ [SESSION_A_ID]: CHAIN_A }, SESSION_A);
    renderRoute(A_PATH, workspaceWith(CHAR_A), A_PATH, store.storage);
    await flush();

    const main = within(mainRegion());
    expect(mainLink(CHAR_A.name)).toHaveAttribute("href", characterHref(CHAR_A_ID));
    expect(main.getByRole("heading", { name: START_LABEL_HEADING })).toBeInTheDocument();
    expect(mainComposer()).toBeInTheDocument();
    const open = openNotesButton();
    expect(headerBlock().contains(open)).toBe(true);

    expect(screen.queryByRole("complementary")).toBeNull();
    const wall = anyWall();
    expect(mainRegion().contains(wall)).toBe(true);
    expect(
      within(wall).getByRole("region", { name: NOTES_REGION, hidden: true }),
    ).toBeInTheDocument();

    expect(chainRequests(calls, SESSION_A_ID)).toHaveLength(1);
  });

  it("pressing Open notes shows the Note wall in the main region with Notes and its four groups listing the chain's notes; Open notes is gone; no second chain read; no layout write — DoD-2", async () => {
    const user = newUser();
    const store = fakeStorage();
    const { calls } = serveSessionsWithChains({ [SESSION_A_ID]: CHAIN_A }, SESSION_A);
    renderRoute(A_PATH, workspaceWith(CHAR_A), A_PATH, store.storage);
    await flush();

    await user.click(openNotesButton());
    await flush();

    const wall = accessibleWall();
    expect(mainRegion().contains(wall)).toBe(true);
    const notes = within(wall).getByRole("region", { name: NOTES_REGION });
    for (const title of [YOUR_NOTES, CHARACTER_NOTES, SETUP_NOTES, SESSION_NOTES]) {
      expect(within(notes).getByRole("region", { name: title })).toBeInTheDocument();
    }
    await waitFor(() => {
      expect(noteBodies()).toEqual([A_CHAR_NOTE, A_SESSION_NOTE]);
    });
    expect(groupBodies(YOUR_NOTES)).toEqual([]);
    expect(groupBodies(CHARACTER_NOTES)).toEqual([A_CHAR_NOTE]);
    expect(groupBodies(SETUP_NOTES)).toEqual([]);
    expect(groupBodies(SESSION_NOTES)).toEqual([A_SESSION_NOTE]);

    expect(queryOpenNotes()).toBeNull();
    expect(chainRequests(calls, SESSION_A_ID)).toHaveLength(1);
    expect(store.setItem).not.toHaveBeenCalled();
  });

  it("for a session with no setup the opened wall's Notes region has no Setup notes group — DoD-2", async () => {
    const user = newUser();
    const store = fakeStorage();
    serveSessionsWithChains({ [SESSION_A_ID]: CHAIN_A_NO_SETUP }, SESSION_NO_SETUP);
    renderRoute(A_PATH, workspaceWith(CHAR_A), A_PATH, store.storage);
    await flush();

    await user.click(openNotesButton());
    await flush();

    const notes = within(accessibleWall()).getByRole("region", { name: NOTES_REGION });
    for (const title of [YOUR_NOTES, CHARACTER_NOTES, SESSION_NOTES]) {
      expect(within(notes).getByRole("region", { name: title })).toBeInTheDocument();
    }
    expect(within(notes).queryByRole("region", { name: SETUP_NOTES })).toBeNull();
    await waitFor(() => {
      expect(groupBodies(CHARACTER_NOTES)).toEqual([A_CHAR_NOTE]);
    });
    expect(groupBodies(SESSION_NOTES)).toEqual([A_SESSION_NOTE]);
    expect(queryOpenNotes()).toBeNull();
    expect(store.setItem).not.toHaveBeenCalled();
  });
});

describe("016 step 006 — pin, reload, dismiss (US-094.AC-2, UC-072 steps 3–5, D2)", () => {
  it("Pin notes on the open wall stores wallPinned: true and reads Unpin notes; a reload with the same storage shows the wall unprompted and no Open notes — DoD-3", async () => {
    const user = newUser();
    const store = fakeStorage(UNPINNED_RECORD);
    serveSessionsWithChains({ [SESSION_A_ID]: CHAIN_A }, SESSION_A);
    const characters = workspaceWith(CHAR_A);
    const first = renderRoute(A_PATH, characters, A_PATH, store.storage);
    await flush();

    await user.click(openNotesButton());
    await flush();
    await user.click(wallControl(PIN_NOTES_NAME));
    await flush();

    expect(storedRecord(store.entries).wallPinned).toBe(true);
    expect(storedRecord(store.entries).navCollapsed).toBe(true);
    expect(wallControl(UNPIN_NOTES_NAME)).toBeInTheDocument();
    expect(within(accessibleWall()).queryByRole("button", { name: PIN_NOTES_NAME })).toBeNull();

    first.view.unmount();
    renderRoute(A_PATH, characters, A_PATH, store.storage);
    await flush();

    expect(wallIsAccessible()).toBe(true);
    expect(mainRegion().contains(accessibleWall())).toBe(true);
    expect(within(accessibleWall()).getByRole("region", { name: NOTES_REGION })).toBeInTheDocument();
    expect(queryOpenNotes()).toBeNull();
  });

  it("a wall opened but not pinned is closed again after a reload, with Open notes present — DoD-4", async () => {
    const user = newUser();
    const store = fakeStorage(UNPINNED_RECORD);
    serveSessionsWithChains({ [SESSION_A_ID]: CHAIN_A }, SESSION_A);
    const characters = workspaceWith(CHAR_A);
    const first = renderRoute(A_PATH, characters, A_PATH, store.storage);
    await flush();

    await user.click(openNotesButton());
    await flush();
    expect(wallIsAccessible()).toBe(true);

    first.view.unmount();
    renderRoute(A_PATH, characters, A_PATH, store.storage);
    await flush();

    expect(wallIsAccessible()).toBe(false);
    expect(anyWall()).toBeInTheDocument();
    expect(openNotesButton()).toBeInTheDocument();
  });

  it("on a pinned wall Close notes hides it, brings back Open notes and stores wallPinned: false — DoD-5", async () => {
    const user = newUser();
    const store = fakeStorage(PINNED_RECORD);
    serveSessionsWithChains({ [SESSION_A_ID]: CHAIN_A }, SESSION_A);
    renderRoute(A_PATH, workspaceWith(CHAR_A), A_PATH, store.storage);
    await flush();
    expect(wallIsAccessible()).toBe(true);
    expect(queryOpenNotes()).toBeNull();

    await user.click(wallControl(CLOSE_NOTES_NAME));
    await flush();

    expect(wallIsAccessible()).toBe(false);
    expect(openNotesButton()).toBeInTheDocument();
    expect(storedRecord(store.entries).wallPinned).toBe(false);
    expect(storedRecord(store.entries).navCollapsed).toBe(true);
  });

  it("on a pinned wall Unpin notes leaves the wall accessible and stores wallPinned: false — DoD-5", async () => {
    const user = newUser();
    const store = fakeStorage(PINNED_RECORD);
    serveSessionsWithChains({ [SESSION_A_ID]: CHAIN_A }, SESSION_A);
    renderRoute(A_PATH, workspaceWith(CHAR_A), A_PATH, store.storage);
    await flush();
    expect(wallIsAccessible()).toBe(true);

    await user.click(wallControl(UNPIN_NOTES_NAME));
    await flush();

    expect(wallIsAccessible()).toBe(true);
    expect(storedRecord(store.entries).wallPinned).toBe(false);
    expect(storedRecord(store.entries).navCollapsed).toBe(true);
  });

  it("below 820px a stored pin shows the wall closed with Open notes; opening and closing it never writes the record — DoD-6", async () => {
    stubNarrowViewport();
    const user = newUser();
    const store = fakeStorage(PINNED_RECORD);
    serveSessionsWithChains({ [SESSION_A_ID]: CHAIN_A }, SESSION_A);
    renderRoute(A_PATH, workspaceWith(CHAR_A), A_PATH, store.storage);
    await flush();

    expect(wallIsAccessible()).toBe(false);
    expect(anyWall()).toBeInTheDocument();
    expect(openNotesButton()).toBeInTheDocument();

    await user.click(openNotesButton());
    await flush();
    expect(wallIsAccessible()).toBe(true);

    await user.click(wallControl(CLOSE_NOTES_NAME));
    await flush();
    expect(wallIsAccessible()).toBe(false);

    expect(storedRecord(store.entries).wallPinned).toBe(true);
    expect(store.setItem).not.toHaveBeenCalled();
  });
});

describe("016 step 006 — the wall stays mounted while closed (D3)", () => {
  it("opening, pinning, unpinning and closing the wall never re-requests the memo chain — DoD-7", async () => {
    const user = newUser();
    const store = fakeStorage();
    const { calls } = serveSessionsWithChains({ [SESSION_A_ID]: CHAIN_A }, SESSION_A);
    renderRoute(A_PATH, workspaceWith(CHAR_A), A_PATH, store.storage);
    await flush();
    expect(chainRequests(calls, SESSION_A_ID)).toHaveLength(1);

    await user.click(openNotesButton());
    await flush();
    expect(chainRequests(calls, SESSION_A_ID)).toHaveLength(1);

    await user.click(wallControl(PIN_NOTES_NAME));
    await flush();
    expect(chainRequests(calls, SESSION_A_ID)).toHaveLength(1);

    await user.click(wallControl(UNPIN_NOTES_NAME));
    await flush();
    expect(chainRequests(calls, SESSION_A_ID)).toHaveLength(1);

    await user.click(wallControl(CLOSE_NOTES_NAME));
    await flush();
    expect(wallIsAccessible()).toBe(false);
    expect(chainRequests(calls, SESSION_A_ID)).toHaveLength(1);
  });

  it("text typed into a note without blurring is still in that textbox after closing and reopening the wall — DoD-7", async () => {
    const store = fakeStorage();
    const { calls } = serveSessionsWithChains({ [SESSION_A_ID]: CHAIN_A }, SESSION_A);
    renderRoute(A_PATH, workspaceWith(CHAR_A), A_PATH, store.storage);
    await flush();

    fireEvent.click(openNotesButton());
    await flush();
    await waitFor(() => {
      expect(noteBodies()).toEqual([A_CHAR_NOTE, A_SESSION_NOTE]);
    });
    const typed = "The well fills at the second bell.";
    fireEvent.change(noteBoxHolding(A_SESSION_NOTE), { target: { value: typed } });
    await flush();

    fireEvent.click(wallControl(CLOSE_NOTES_NAME));
    await flush();
    expect(wallIsAccessible()).toBe(false);

    fireEvent.click(openNotesButton());
    await flush();
    expect(wallIsAccessible()).toBe(true);
    expect(noteBoxHolding(typed)).toBeInTheDocument();
    expect(groupBodies(SESSION_NOTES)).toEqual([typed]);
    expect(chainRequests(calls, SESSION_A_ID)).toHaveLength(1);
  });
});

describe("016 step 006 — no session, no wall (US-095.AC-1, D1)", () => {
  type StorageCase = [label: string, record: { navCollapsed: boolean; wallPinned: boolean } | undefined];

  const STORAGES: StorageCase[] = [
    ["an empty layout storage", undefined],
    ["a stored wallPinned: true", PINNED_RECORD],
  ];

  it.each(STORAGES)(
    "with %s, while the session is loading there is no Note wall (not even hidden), no Open notes and no memo-chain request — DoD-8",
    async (_label, record) => {
      const store = fakeStorage(record);
      const gate = deferred<Response>();
      const { calls } = stubBackend(
        (request) =>
          streamAnswer(request, [SESSION_A_ID]) ??
          (request.method === "GET" && request.path === sessionPath(SESSION_A_ID)
            ? gate.promise
            : notFoundResponse()),
      );
      renderRoute(A_PATH, workspaceWith(CHAR_A), A_PATH, store.storage);
      await flush();

      expect(loaders().length).toBeGreaterThan(0);
      expect(queryAnyWall()).toBeNull();
      expect(queryOpenNotes()).toBeNull();
      expect(chainRequests(calls, SESSION_A_ID)).toEqual([]);

      gate.resolve(jsonResponse(SESSION_A, 200));
      await flush();
    },
  );

  it.each(STORAGES)(
    "with %s, Session not found renders no Note wall (not even hidden), no Open notes and no memo-chain request — DoD-8",
    async (_label, record) => {
      const store = fakeStorage(record);
      const { calls } = stubBackend(() => notFoundResponse());
      renderRoute(A_PATH, workspaceWith(CHAR_A), A_PATH, store.storage);
      await flush();

      expect(within(mainRegion()).getByText(NOT_FOUND_TEXT)).toBeInTheDocument();
      expect(queryAnyWall()).toBeNull();
      expect(queryOpenNotes()).toBeNull();
      expect(chainRequests(calls, SESSION_A_ID)).toEqual([]);
    },
  );

  type FailureStorageCase = [
    label: string,
    record: { navCollapsed: boolean; wallPinned: boolean } | undefined,
    answer: () => Response,
  ];

  const FAILED_LOADS: FailureStorageCase[] = [
    ["a 500 envelope and an empty layout storage", undefined, serverError],
    ["a 500 envelope and a stored wallPinned: true", PINNED_RECORD, serverError],
    [
      "a transport failure and a stored wallPinned: true",
      PINNED_RECORD,
      () => {
        throw new TypeError("Failed to fetch");
      },
    ],
  ];

  it.each(FAILED_LOADS)(
    "with %s, Could not load the session renders no Note wall (not even hidden), no Open notes and no memo-chain request — DoD-8",
    async (_label, record, answer) => {
      const store = fakeStorage(record);
      const { calls } = stubBackend(() => answer());
      renderRoute(A_PATH, workspaceWith(CHAR_A), A_PATH, store.storage);
      await flush();

      expect(within(mainRegion()).getByText(LOAD_FAILED_TEXT)).toBeInTheDocument();
      expect(queryAnyWall()).toBeNull();
      expect(queryOpenNotes()).toBeNull();
      expect(chainRequests(calls, SESSION_A_ID)).toEqual([]);
    },
  );
});

describe("016 step 006 — the wall per session (D2)", () => {
  it("with a stored pin, navigating in-entry from a to b shows b's wall pinned too, with b's notes and none of a's — DoD-10", async () => {
    const user = newUser();
    const store = fakeStorage(PINNED_RECORD);
    const { calls } = serveSessionsWithChains(
      { [SESSION_A_ID]: CHAIN_A, [SESSION_B_ID]: CHAIN_B },
      SESSION_A,
      SESSION_B,
    );
    renderRoute(A_PATH, workspaceWith(CHAR_A, CHAR_B), sessionRoutePath(SESSION_B_ID), store.storage);
    await flush();
    expect(wallIsAccessible()).toBe(true);
    await waitFor(() => {
      expect(noteBodies()).toEqual([A_CHAR_NOTE, A_SESSION_NOTE]);
    });

    await user.click(screen.getByRole("button", { name: /^probe navigate$/i }));
    await flush();

    expect(screen.getByTestId("location").textContent).toBe(sessionRoutePath(SESSION_B_ID));
    expect(chainRequests(calls, SESSION_B_ID)).toHaveLength(1);
    expect(wallIsAccessible()).toBe(true);
    expect(wallControl(UNPIN_NOTES_NAME)).toBeInTheDocument();
    expect(queryOpenNotes()).toBeNull();
    await waitFor(() => {
      expect(noteBodies()).toEqual([B_CHAR_NOTE, B_SESSION_NOTE]);
    });
    const shown = noteBodies();
    expect(shown).not.toContain(A_CHAR_NOTE);
    expect(shown).not.toContain(A_SESSION_NOTE);
  });
});

describe("016 step 006 — the screen is constructed with a storage prop (D2 re-freeze)", () => {
  it("SessionScreen given a null storage renders the ready header with Open notes and the closed wall — DoD-12", async () => {
    const { calls } = serveSessionsWithChains({ [SESSION_A_ID]: CHAIN_A }, SESSION_A);
    renderScreen(SESSION_A_ID, workspaceWith(CHAR_A), null);
    await flush();

    expect(mainLink(CHAR_A.name)).toHaveAttribute("href", characterHref(CHAR_A_ID));
    expect(openNotesButton()).toBeInTheDocument();
    expect(wallIsAccessible()).toBe(false);
    expect(anyWall()).toBeInTheDocument();
    expect(chainRequests(calls, SESSION_A_ID)).toHaveLength(1);
  });

  it("SessionScreen given a fake storage with a stored pin renders the wall accessible and no Open notes — DoD-12", async () => {
    const store = fakeStorage(PINNED_RECORD);
    serveSessionsWithChains({ [SESSION_A_ID]: CHAIN_A }, SESSION_A);
    renderScreen(SESSION_A_ID, workspaceWith(CHAR_A), store.storage);
    await flush();

    expect(wallIsAccessible()).toBe(true);
    expect(queryOpenNotes()).toBeNull();
  });
});
