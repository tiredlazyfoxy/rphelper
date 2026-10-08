// Feature 033, step 004 — the page composer's optional setup choice (DoD-1..DoD-9; DoD-10 is
// manual/live).
//
// Expected behaviour comes from the step's Interface intent and Definition of done and from 033
// context.md D8 (the "New session" composer carries a small "Setup" select — "No setup" default,
// the character's working setups as options — and sending creates the session with the chosen
// setup and the opening message in one request) and D10 (the accepted spec conflict with
// US-117.AC-4). Bindings come from status.md's "Step 004 — frozen interface":
// `startSessionWithMessage(characterId, openingText, setupId = null, signal?)`, a Mantine
// `Select` labelled "Setup" whose first option is "No setup", a reload on dropdown open, the
// failure line "Could not load setups to choose from." and `disabled` while sending.
//
// Wire facts used (004.context.md): `POST /api/characters/<id>/sessions` takes `opening_message`
// and an optional `setup_id`; a bad setup answers `setup_archived` 409. The setups listing is
// `GET /api/characters/<id>/setups` answering `{ "setups": [...] }`.
//
// Rendered inside AppProviders and a MemoryRouter at /characters/<C> with a /sessions/:id probe
// route, so navigation is observed through the location only. Mantine Select in jsdom: the
// dropdown is opened by clicking the input and an option is picked by role "option".
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation, useParams } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CharacterComposer } from "../../src/app/CharacterComposer";
import {
  type Session,
  type StartedSession,
  startSessionWithMessage,
} from "../../src/app/sessionsApi";
import { SessionsState } from "../../src/app/sessionsState";
import type { Setup } from "../../src/app/setupsApi";
import type { Message } from "../../src/app/streamApi";
import { isApiError } from "../../src/shared/apiError";
import { AppProviders } from "../../src/shared/AppProviders";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type User = ReturnType<typeof userEvent.setup>;
type Seen = { method: string; path: string; search: string; body: unknown };

// ---------------------------------------------------------------- fixtures
// Every id is > Number.MAX_SAFE_INTEGER: a silent numeric coercion would change it.
const CHARACTER_ID = "7250000000000000401";
const SESSION_ID = "7270000000000000401";
const MESSAGE_ID = "7280000000000000401";
const TAVERN_ID = "7260000000000000401";
const HARBOUR_ID = "7260000000000000402";
const OLD_INN_ID = "7260000000000000403";

const CHARACTER_PATH = `/characters/${CHARACTER_ID}`;
const START_PATH = `/api/characters/${CHARACTER_ID}/sessions`;
const SETUPS_PATH = `/api/characters/${CHARACTER_ID}/setups`;
const STAMP = "2026-10-08T09:26:53.000000+00:00";

const COMPOSER_REGION = "New session";
const SETUP_LABEL = /^setup$/i;
const NO_SETUP = "No setup";
const SETUPS_FAILED_TEXT = "Could not load setups to choose from.";

function setupRow(id: string, name: string, archivedAt: string | null = null): Setup {
  return {
    id,
    character_id: CHARACTER_ID,
    name,
    description: "",
    archived_at: archivedAt,
    created_at: STAMP,
    updated_at: archivedAt ?? STAMP,
  };
}

const TAVERN = setupRow(TAVERN_ID, "The Gilded Tavern");
const HARBOUR = setupRow(HARBOUR_ID, "Grey Harbour");
const OLD_INN = setupRow(OLD_INN_ID, "The Old Inn", "2026-10-01T09:00:00.000000+00:00");

function servedSession(setup: Setup | null): Session {
  return {
    id: SESSION_ID,
    character_id: CHARACTER_ID,
    setup_id: setup === null ? null : setup.id,
    setup_name: setup === null ? null : setup.name,
    archived_at: null,
    last_used_at: STAMP,
    created_at: STAMP,
    updated_at: STAMP,
  };
}

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

function started(text: string, setup: Setup | null = null): StartedSession {
  return { ...servedSession(setup), opening_message: openingMessage(text) };
}

beforeEach(() => {
  notifyFailureSpy.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- fetch helpers
function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function parseBody(init?: RequestInit): unknown {
  const raw = init?.body;
  if (raw === undefined || raw === null) return undefined;
  return typeof raw === "string" ? (JSON.parse(raw) as unknown) : raw;
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, message: string): unknown {
  return { error: { code, message, detail: {} } };
}

function stubBackend(handler: (request: Seen) => Response | Promise<Response>) {
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>((input, init) => {
    const url = requestUrl(input);
    const request: Seen = {
      method: requestMethod(input, init),
      path: url.pathname,
      search: url.search,
      body: parseBody(init),
    };
    calls.push(request);
    return Promise.resolve(handler(request));
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

type Config = {
  /** One payload per setups GET, in order; the last repeats. */
  setups?: Setup[][];
  /** Every setups GET fails with a 500. */
  failSetups?: true;
  /** The answer to the sessions POST. */
  start?: () => Response | Promise<Response>;
};

function serveComposer(config: Config = {}) {
  const setupsResponses = config.setups ?? [[]];
  let setupsServed = 0;
  return stubBackend((request) => {
    if (request.method === "GET" && request.path === SETUPS_PATH) {
      if (config.failSetups === true) {
        return jsonResponse(envelope("internal_error", "The setups shelf collapsed zq-33."), 500);
      }
      const index = Math.min(setupsServed, setupsResponses.length - 1);
      setupsServed += 1;
      return jsonResponse({ setups: setupsResponses[index] }, 200);
    }
    if (request.method === "POST" && request.path === START_PATH && request.search === "") {
      if (config.start !== undefined) return config.start();
      return jsonResponse(started("unused"), 201);
    }
    return jsonResponse(
      envelope("unexpected_request", `${request.method} ${request.path}${request.search}`),
      599,
    );
  });
}

function setupsRequests(calls: Seen[]): Seen[] {
  return calls.filter((call) => call.method === "GET" && call.path === SETUPS_PATH);
}

function startPosts(calls: Seen[]): Seen[] {
  return calls.filter((call) => call.method === "POST" && call.path === START_PATH);
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
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

// ---------------------------------------------------------------- render
function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location">{location.pathname}</span>;
}

function SessionProbe() {
  const params = useParams();
  return <p>session page {params.id}</p>;
}

function CharacterProbeRoute(props: { sessions: SessionsState }) {
  const params = useParams();
  return <CharacterComposer characterId={params.id ?? ""} sessions={props.sessions} />;
}

async function renderComposer() {
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
  await flush();
  return { sessions, view };
}

function newUser(): User {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

function locationPath(): string {
  return screen.getByTestId("location").textContent ?? "";
}

function region(): HTMLElement {
  return screen.getByRole("region", { name: COMPOSER_REGION });
}

function composer(): HTMLElement {
  return within(region()).getByRole("textbox", { name: "Composer" });
}

function sendButton(): HTMLElement {
  return within(region()).getByRole("button", { name: "Send" });
}

/** The composer's "Setup" select input (Mantine renders it as a combobox or a plain textbox). */
function setupSelect(): HTMLElement {
  const scope = within(region());
  return (
    scope.queryByRole("combobox", { name: SETUP_LABEL }) ??
    scope.queryByRole("textbox", { name: SETUP_LABEL }) ??
    scope.getByLabelText(SETUP_LABEL)
  );
}

/** What the "Setup" select currently displays. */
function setupSelectText(): string {
  const element = setupSelect();
  const shown = element instanceof HTMLInputElement ? element.value : (element.textContent ?? "");
  return shown.trim();
}

function optionNames(): string[] {
  return screen.queryAllByRole("option").map((option) => (option.textContent ?? "").trim());
}

async function openSelect(user: User): Promise<void> {
  await user.click(setupSelect());
  await waitFor(() => {
    expect(screen.queryAllByRole("option").length).toBeGreaterThan(0);
  });
  await flush();
}

async function chooseOption(user: User, name: string): Promise<void> {
  await user.click(screen.getByRole("option", { name }));
  await flush();
}

async function typeAndSend(user: User, text: string): Promise<void> {
  await user.type(composer(), text);
  await user.click(sendButton());
  await flush();
}

// ---------------------------------------------------------------- DoD-1
describe("startSessionWithMessage — the optional setup id (033 step 004, D8)", () => {
  it("with a setup id, posts once to the character's sessions route with { opening_message, setup_id } (id as a string) — 033 step 004 DoD-1", async () => {
    const served = started("  Hello\n", TAVERN);
    const { calls } = stubBackend(() => jsonResponse(served, 201));

    const result = await startSessionWithMessage(CHARACTER_ID, "  Hello\n", TAVERN_ID);

    expect(calls.map(({ method, path, search }) => ({ method, path, search }))).toEqual([
      { method: "POST", path: START_PATH, search: "" },
    ]);
    expect(calls[0].body).toEqual({ opening_message: "  Hello\n", setup_id: TAVERN_ID });
    expect(Object.keys(calls[0].body as object).sort()).toEqual(["opening_message", "setup_id"]);
    expect(typeof (calls[0].body as { setup_id: unknown }).setup_id).toBe("string");
    // Return value unchanged: the served started session, as received.
    expect(result).toEqual(served);
  });

  it("without a setup id, the body is exactly { opening_message } — 033 step 004 DoD-1", async () => {
    const { calls } = stubBackend(() => jsonResponse(started("Hello there"), 201));

    await startSessionWithMessage(CHARACTER_ID, "Hello there");

    expect(startPosts(calls)).toHaveLength(1);
    expect(calls).toHaveLength(1);
    expect(calls[0].body).toEqual({ opening_message: "Hello there" });
    expect(Object.keys(calls[0].body as object)).toEqual(["opening_message"]);
  });

  it("with an explicit null setup id, the body is exactly { opening_message } — 033 step 004 DoD-1", async () => {
    const { calls } = stubBackend(() => jsonResponse(started("Hello there"), 201));

    await startSessionWithMessage(CHARACTER_ID, "Hello there", null);

    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].path).toBe(START_PATH);
    expect(calls[0].body).toEqual({ opening_message: "Hello there" });
    expect(Object.keys(calls[0].body as object)).toEqual(["opening_message"]);
  });

  it("error behaviour is unchanged: a 409 setup_archived rejects with an ApiError carrying that code — 033 step 004 DoD-1", async () => {
    stubBackend(() => jsonResponse(envelope("setup_archived", "That setup is archived."), 409));

    const error = await startSessionWithMessage(CHARACTER_ID, "Hello there", TAVERN_ID).then(
      () => {
        throw new Error("the call resolved, but the route answered an error");
      },
      (reason: unknown) => reason,
    );

    expect(isApiError(error)).toBe(true);
    expect(isApiError(error) ? error.code : null).toBe("setup_archived");
  });
});

// ---------------------------------------------------------------- DoD-2
describe("CharacterComposer — the Setup select on open (D8)", () => {
  it('the "New session" composer shows a "Setup" select reading "No setup" on open — 033 step 004 DoD-2', async () => {
    serveComposer({ setups: [[TAVERN, HARBOUR]] });
    await renderComposer();

    expect(setupSelect()).toBeInTheDocument();
    expect(region().contains(setupSelect())).toBe(true);
    expect(setupSelectText()).toBe(NO_SETUP);
  });
});

// ---------------------------------------------------------------- DoD-3
describe("CharacterComposer — the Setup choices (D8, UC-021)", () => {
  it('offers "No setup" first, then the non-archived setups by name; an archived setup is not offered — 033 step 004 DoD-3', async () => {
    const user = newUser();
    serveComposer({ setups: [[TAVERN, OLD_INN, HARBOUR]] });
    await renderComposer();

    await openSelect(user);

    const names = optionNames();
    expect(names[0]).toBe(NO_SETUP);
    expect(names.slice(1).sort()).toEqual([HARBOUR.name, TAVERN.name].sort());
    expect(names).not.toContain(OLD_INN.name);
    expect(screen.queryByRole("option", { name: OLD_INN.name })).toBeNull();
  });
});

// ---------------------------------------------------------------- DoD-4
describe('CharacterComposer — sending with "No setup" (D8, US-117.AC-1, R2)', () => {
  it("posts one body carrying no setup id and navigates to /sessions/<id> — 033 step 004 DoD-4", async () => {
    const user = newUser();
    const { calls } = serveComposer({
      setups: [[TAVERN]],
      start: () => jsonResponse(started("Hello there"), 201),
    });
    await renderComposer();
    expect(setupSelectText()).toBe(NO_SETUP);

    await typeAndSend(user, "Hello there");

    await waitFor(() => {
      expect(locationPath()).toBe(`/sessions/${SESSION_ID}`);
    });
    const posts = startPosts(calls);
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({ opening_message: "Hello there" });
    expect(Object.keys(posts[0].body as object)).toEqual(["opening_message"]);
  });

  it('choosing a setup and then "No setup" again posts a body carrying no setup id — 033 step 004 DoD-4', async () => {
    const user = newUser();
    const { calls } = serveComposer({
      setups: [[TAVERN]],
      start: () => jsonResponse(started("Hello there"), 201),
    });
    await renderComposer();

    await openSelect(user);
    await chooseOption(user, TAVERN.name);
    expect(setupSelectText()).toBe(TAVERN.name);
    await openSelect(user);
    await chooseOption(user, NO_SETUP);
    expect(setupSelectText()).toBe(NO_SETUP);

    await typeAndSend(user, "Hello there");

    await waitFor(() => {
      expect(locationPath()).toBe(`/sessions/${SESSION_ID}`);
    });
    const posts = startPosts(calls);
    expect(posts).toHaveLength(1);
    expect(Object.keys(posts[0].body as object)).toEqual(["opening_message"]);
  });
});

// ---------------------------------------------------------------- DoD-5
describe("CharacterComposer — sending with a chosen setup (D8, US-117.AC-1, US-117.AC-2)", () => {
  it("one POST carries both the opening message and the chosen setup id, then the location is /sessions/<id> — 033 step 004 DoD-5", async () => {
    const user = newUser();
    const { calls } = serveComposer({
      setups: [[HARBOUR, TAVERN]],
      start: () => jsonResponse(started("Hello there", TAVERN), 201),
    });
    await renderComposer();

    await openSelect(user);
    await chooseOption(user, TAVERN.name);
    expect(setupSelectText()).toBe(TAVERN.name);

    await typeAndSend(user, "Hello there");

    await waitFor(() => {
      expect(locationPath()).toBe(`/sessions/${SESSION_ID}`);
    });
    expect(screen.getByText(`session page ${SESSION_ID}`)).toBeInTheDocument();
    const posts = startPosts(calls);
    expect(posts).toHaveLength(1);
    expect(posts[0].search).toBe("");
    expect(posts[0].body).toEqual({ opening_message: "Hello there", setup_id: TAVERN_ID });
  });
});

// ---------------------------------------------------------------- DoD-6
describe("CharacterComposer — a failed setups load does not block sending (D8, R2)", () => {
  it('shows "Could not load setups to choose from." and sending with "No setup" still succeeds — 033 step 004 DoD-6', async () => {
    const user = newUser();
    const { calls } = serveComposer({
      failSetups: true,
      start: () => jsonResponse(started("Hello there"), 201),
    });
    await renderComposer();

    expect(await within(region()).findByText(SETUPS_FAILED_TEXT)).toBeInTheDocument();
    expect(setupSelectText()).toBe(NO_SETUP);

    await typeAndSend(user, "Hello there");

    await waitFor(() => {
      expect(locationPath()).toBe(`/sessions/${SESSION_ID}`);
    });
    const posts = startPosts(calls);
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({ opening_message: "Hello there" });
    expect(Object.keys(posts[0].body as object)).toEqual(["opening_message"]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("the failure line does not render when the setups load succeeds — 033 step 004 DoD-6", async () => {
    serveComposer({ setups: [[TAVERN]] });
    await renderComposer();

    expect(screen.queryByText(SETUPS_FAILED_TEXT)).toBeNull();
  });
});

// ---------------------------------------------------------------- DoD-7
describe("CharacterComposer — opening the dropdown reloads the choices (D8)", () => {
  it("a setup created on the server since page open is offered once the dropdown opens — 033 step 004 DoD-7", async () => {
    const user = newUser();
    const { calls } = serveComposer({ setups: [[TAVERN], [TAVERN, HARBOUR]] });
    await renderComposer();
    const afterMount = setupsRequests(calls).length;
    expect(afterMount).toBeGreaterThan(0);

    await openSelect(user);

    expect(await screen.findByRole("option", { name: HARBOUR.name })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: TAVERN.name })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: NO_SETUP })).toBeInTheDocument();
    expect(setupsRequests(calls).length).toBeGreaterThan(afterMount);
  });
});

// ---------------------------------------------------------------- DoD-8
describe("CharacterComposer — a refused send (D8)", () => {
  it("a 409 setup_archived raises the failure notification, keeps the draft and does not navigate — 033 step 004 DoD-8", async () => {
    const user = newUser();
    const { calls } = serveComposer({
      setups: [[TAVERN]],
      start: () => jsonResponse(envelope("setup_archived", "That setup is archived."), 409),
    });
    await renderComposer();

    await openSelect(user);
    await chooseOption(user, TAVERN.name);
    await typeAndSend(user, "Hello there");

    await waitFor(() => {
      expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(sendButton()).toBeEnabled();
    });
    expect(startPosts(calls)).toHaveLength(1);
    expect(locationPath()).toBe(CHARACTER_PATH);
    expect(composer()).toHaveValue("Hello there");
  });
});

// ---------------------------------------------------------------- DoD-9
describe("CharacterComposer — the Setup select while sending, and no kind switch (D8)", () => {
  it("the Setup select is disabled while the send is in flight — 033 step 004 DoD-9", async () => {
    const user = newUser();
    const gate = deferred<Response>();
    serveComposer({ setups: [[TAVERN]], start: () => gate.promise });
    await renderComposer();
    expect(setupSelect()).toBeEnabled();

    await typeAndSend(user, "Hello there");

    await waitFor(() => {
      expect(setupSelect()).toBeDisabled();
    });

    gate.resolve(jsonResponse(started("Hello there"), 201));
    await flush();
    await waitFor(() => {
      expect(locationPath()).toBe(`/sessions/${SESSION_ID}`);
    });
  });

  it("the composer offers no kind switch — 033 step 004 DoD-9", async () => {
    serveComposer({ setups: [[TAVERN]] });
    await renderComposer();

    const scope = within(region());
    expect(scope.queryByRole("radiogroup", { name: /entry kind/i })).toBeNull();
    expect(scope.queryByRole("group", { name: /entry kind/i })).toBeNull();
    expect(scope.queryByText(/entry kind/i)).toBeNull();
    expect(scope.queryByRole("radio", { name: "Partner" })).toBeNull();
    expect(scope.queryByRole("radio", { name: "My turn" })).toBeNull();
    expect(scope.queryAllByRole("radio")).toEqual([]);
  });
});
