// Feature 009, step 007 — the character screen and its two routes (DoD-1..DoD-12).
// DoD-13 lives in App.test.tsx; DoD-14 is [manual/live] and carries no test.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 007.context.md and context.md (D1 explicit Create with `replace` navigation, D2 the
// labelled Save, D4/D9 an archived character's page opens and stays editable, D11 the one
// workspace characters state arrives as a prop, D12 every failure is inline and nothing is
// notified).
//
// Recognition conventions (from the spec's wording, for the verifier):
// - The screen's own names are the contract: headings "New character" / the character's
//   name / "Sessions"; textboxes "Name" and "Persona"; buttons "Create", "Save", "Archive",
//   "Restore", "Retry"; the badge text exactly "Archived"; the sentences "Character not
//   found", "Could not load the character", "Could not create the character.", "Could not
//   save the character.". Everything is queried by role + accessible name or by text.
// - The centre column: the harness wraps the two routes in a `<main>` landmark, which is
//   what the shell gives the screen in the application (008). "In the main region" means
//   inside it.
// - A Mantine `Loader`: `.mantine-Loader-root` (the repo's existing convention).
// - A notification: `.mantine-Notification-root`.
// - The router location and in-entry navigation: a probe rendered beside the routes inside
//   the same MemoryRouter; document navigation is `documentNavigation.assign` (the shared
//   client's only seam onto `window.location`).
// - `src/shared/MarkdownEditor` is replaced by the sanctioned stub (context.md "Test
//   conventions — TipTap in jsdom"): a labelled `<textarea>` honouring `label`, `value`,
//   `onChange` and `readOnly`, so persona edits are typed reliably in jsdom.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChangeEvent } from "react";
import { CharacterRoute, CharacterScreen } from "../../src/app/CharacterScreen";
import type { Character } from "../../src/app/charactersApi";
import { CharactersState } from "../../src/app/charactersState";
import { documentNavigation } from "../../src/shared/api";
import { AppProviders } from "../../src/shared/AppProviders";

vi.mock("../../src/shared/MarkdownEditor", async () => {
  const { createElement } = await import("react");
  type StubProps = {
    label: string;
    value: string;
    onChange: (markdown: string) => void;
    readOnly?: boolean;
  };
  return {
    MarkdownEditor: (props: StubProps) => {
      const id = `markdown-editor-${props.label.toLowerCase().replace(/\s+/g, "-")}`;
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
const NEW_HEADING = /^new character$/i;
const SESSIONS_HEADING = /^sessions$/i;
const NAME_LABEL = /^name$/i;
const PERSONA_LABEL = /^persona$/i;
const CREATE_NAME = /^create$/i;
const SAVE_NAME = /^save$/i;
const ARCHIVE_NAME = /^archive$/i;
const RESTORE_NAME = /^restore$/i;
const RETRY_NAME = /^retry$/i;
const ARCHIVED_BADGE = "Archived";
const NOT_FOUND_TEXT = "Character not found";
const LOAD_FAILED_TEXT = "Could not load the character";
const CREATE_FAILED_TEXT = "Could not create the character.";
const SAVE_FAILED_TEXT = "Could not save the character.";

const LOADER = ".mantine-Loader-root";
const NOTIFICATION = ".mantine-Notification-root";

// ---------------------------------------------------------------- fixtures
// Ids are decimal strings; CREATED_ID is past Number.MAX_SAFE_INTEGER, so any coercion of
// the response's id would show up in the location (context.md "Ids are strings").
const ID_A = "7250000000000000011";
const ID_B = "7250000000000000012";
const CREATED_ID = "9007199254740993"; // 2^53 + 1

const NEW_PATH = "/characters/new";
const COLLECTION_PATH = "/api/characters";

const TYPED_NAME = "Aria Vance";
const TYPED_SHEET = "A duelist with a borrowed name.";

const CHAR_A: Character = {
  id: ID_A,
  name: "Aria Vance",
  sheet: "A scribe who never finishes a sentence.",
  archived_at: null,
  created_at: "2026-03-14T09:26:53.000000+00:00",
  updated_at: "2026-03-14T09:26:53.000000+00:00",
};

const CHAR_B: Character = {
  id: ID_B,
  name: "Corvin Hale",
  sheet: "A duelist who counts his scars.",
  archived_at: null,
  created_at: "2026-02-01T08:15:42.000000+00:00",
  updated_at: "2026-02-01T08:15:42.000000+00:00",
};

const ARCHIVED_A: Character = {
  ...CHAR_A,
  archived_at: "2026-04-05T10:00:00.000000+00:00",
  updated_at: "2026-04-05T10:00:00.000000+00:00",
};

const CREATED: Character = {
  id: CREATED_ID,
  name: TYPED_NAME,
  sheet: TYPED_SHEET,
  archived_at: null,
  created_at: "2026-04-10T12:00:00.000000+00:00",
  updated_at: "2026-04-10T12:00:00.000000+00:00",
};

/** What the server answers the PATCH with — a trimmed name the screen must re-render from. */
const SAVED_A: Character = {
  ...CHAR_A,
  name: "Bo",
  sheet: "Shorter now.",
  updated_at: "2026-03-20T18:04:11.000000+00:00",
};

const EDITED_NAME = "Bo";
const EDITED_SHEET = "Shorter now.";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- fetch harness
function itemPath(characterId: string): string {
  return `${COLLECTION_PATH}/${characterId}`;
}

/** 010 step 006: the section's listing, a different URL than the character's own. */
function setupsPath(characterId: string): string {
  return `${itemPath(characterId)}/setups`;
}

/** Every character route whose load succeeds now also answers the section's listing. */
const EMPTY_SETUPS = { setups: [] };

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
  return envelope("character_not_found", 404);
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

function parseBody(init?: RequestInit): unknown {
  const body = init?.body;
  if (body === undefined || body === null) return undefined;
  return JSON.parse(String(body)) as unknown;
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

/**
 * Answers GET of each given character and an empty setups listing for each (010 step 006),
 * and 404s everything else.
 */
function serveCharacters(...rows: Character[]) {
  return stubBackend((request) => {
    if (request.method === "GET") {
      const row = rows.find((candidate) => request.path === itemPath(candidate.id));
      if (row !== undefined) return jsonResponse(row, 200);
      const owner = rows.find((candidate) => request.path === setupsPath(candidate.id));
      if (owner !== undefined) return jsonResponse(EMPTY_SETUPS, 200);
    }
    return notFoundResponse();
  });
}

function matching(calls: Seen[], method: string, path: string): Seen[] {
  return calls.filter((call) => call.method === method && call.path === path);
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
const PROBE_NAVIGATE = /^probe navigate$/i;
const PROBE_BACK = /^probe back$/i;

function Probe(props: { to: string }) {
  const navigate = useNavigate();
  const location = useLocation();
  return (
    <div>
      <span data-testid="location">{location.pathname}</span>
      <button type="button" onClick={() => void navigate(props.to)}>
        probe navigate
      </button>
      <button type="button" onClick={() => void navigate(-1)}>
        probe back
      </button>
    </div>
  );
}

/**
 * The two routes of this step, in the `<main>` landmark the shell gives them, with one
 * workspace `CharactersState` (D11) and a location/navigation probe beside them.
 */
function renderScreen(initialPath: string, probeTo = `/characters/${ID_B}`) {
  const characters = new CharactersState();
  const view = render(
    <AppProviders>
      <MemoryRouter initialEntries={[initialPath]}>
        <main>
          <Routes>
            <Route
              path="/characters/new"
              element={<CharacterScreen characters={characters} characterId={null} />}
            />
            <Route path="/characters/:id" element={<CharacterRoute characters={characters} />} />
          </Routes>
        </main>
        <Probe to={probeTo} />
      </MemoryRouter>
    </AppProviders>,
  );
  return { characters, view };
}

// ---------------------------------------------------------------- queries
function mainRegion(): HTMLElement {
  return screen.getByRole("main");
}

function locationPath(): string {
  return screen.getByTestId("location").textContent ?? "";
}

function nameInput(): HTMLInputElement {
  const element = within(mainRegion()).getByRole("textbox", { name: NAME_LABEL });
  if (!(element instanceof HTMLInputElement)) throw new Error('the "Name" textbox is not an input');
  return element;
}

function personaInput(): HTMLTextAreaElement {
  const element = within(mainRegion()).getByRole("textbox", { name: PERSONA_LABEL });
  if (!(element instanceof HTMLTextAreaElement)) {
    throw new Error('the "Persona" textbox is not the stubbed editor');
  }
  return element;
}

function button(name: RegExp): HTMLElement {
  return within(mainRegion()).getByRole("button", { name });
}

function queryButton(name: RegExp): HTMLElement | null {
  return within(mainRegion()).queryByRole("button", { name });
}

function heading(name: RegExp | string): HTMLElement {
  return within(mainRegion()).getByRole("heading", { name });
}

function queryHeading(name: RegExp | string): HTMLElement | null {
  return within(mainRegion()).queryByRole("heading", { name });
}

function loaders(): Element[] {
  return Array.from(document.querySelectorAll(LOADER));
}

function notificationsShown(): Element[] {
  return Array.from(document.querySelectorAll(NOTIFICATION));
}

/** True when `first` comes before `second` in document order. */
function precedes(first: Element, second: Element): boolean {
  return (first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

/** Loads `character` at its own route and settles. */
async function renderLoaded(character: Character, extra: Character[] = []) {
  const server = serveCharacters(character, ...extra);
  const rendered = renderScreen(`/characters/${character.id}`);
  await flush();
  return { ...server, ...rendered };
}

async function typeInto(user: User, element: HTMLElement, text: string): Promise<void> {
  await user.clear(element);
  await user.type(element, text);
}

// ---------------------------------------------------------------------------
describe("new mode at /characters/new (D1)", () => {
  it("shows the New character form with a disabled Create and nothing of the existing screen — DoD-1", () => {
    stubBackend(() => notFoundResponse());
    renderScreen(NEW_PATH);

    expect(heading(NEW_HEADING)).toBeInTheDocument();
    expect(nameInput()).toBeInTheDocument();
    expect(personaInput()).toBeInTheDocument();
    expect(button(CREATE_NAME)).toBeDisabled();
    expect(queryButton(ARCHIVE_NAME)).toBeNull();
    expect(queryHeading(SESSIONS_HEADING)).toBeNull();
  });

  it("typing a name enables Create and sends no request — DoD-2", async () => {
    const user = newUser();
    const { mock, calls } = stubBackend(() => notFoundResponse());
    renderScreen(NEW_PATH);

    await user.type(nameInput(), TYPED_NAME);

    expect(button(CREATE_NAME)).toBeEnabled();
    expect(calls).toEqual([]);
    expect(mock).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("Create posts once and hands the route over to the new id (D1, US-020.AC-1)", () => {
  it("POSTs /api/characters once and moves the router to the returned id with no document navigation — DoD-3", async () => {
    const user = newUser();
    const assign = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    const { calls } = stubBackend((request) => {
      if (request.method === "POST" && request.path === COLLECTION_PATH) {
        return jsonResponse(CREATED, 201);
      }
      if (request.method === "GET" && request.path === itemPath(CREATED_ID)) {
        return jsonResponse(CREATED, 200);
      }
      // 010 step 006: the created character's screen mounts the Setups section.
      if (request.method === "GET" && request.path === setupsPath(CREATED_ID)) {
        return jsonResponse(EMPTY_SETUPS, 200);
      }
      return notFoundResponse();
    });
    renderScreen(NEW_PATH);

    await user.type(nameInput(), TYPED_NAME);
    await user.type(personaInput(), TYPED_SHEET);
    await user.click(button(CREATE_NAME));
    await flush();

    const posts = matching(calls, "POST", COLLECTION_PATH);
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toMatchObject({ name: TYPED_NAME, sheet: TYPED_SHEET });
    expect(locationPath()).toBe(`/characters/${CREATED_ID}`);
    expect(assign).not.toHaveBeenCalled();
  });

  it("navigates with replace, so going back does not return to the empty form — DoD-3", async () => {
    const user = newUser();
    stubBackend((request) => {
      if (request.method === "POST" && request.path === COLLECTION_PATH) {
        return jsonResponse(CREATED, 201);
      }
      if (request.method === "GET" && request.path === itemPath(CREATED_ID)) {
        return jsonResponse(CREATED, 200);
      }
      // 010 step 006: the created character's screen mounts the Setups section.
      if (request.method === "GET" && request.path === setupsPath(CREATED_ID)) {
        return jsonResponse(EMPTY_SETUPS, 200);
      }
      return notFoundResponse();
    });
    renderScreen(NEW_PATH);

    await user.type(nameInput(), TYPED_NAME);
    await user.click(button(CREATE_NAME));
    await flush();
    expect(locationPath()).toBe(`/characters/${CREATED_ID}`);

    await user.click(screen.getByRole("button", { name: PROBE_BACK }));
    await flush();

    expect(locationPath()).toBe(`/characters/${CREATED_ID}`);
  });

  it("a failed Create reports inline, stays on the form and keeps the typed name — DoD-4", async () => {
    const user = newUser();
    stubBackend(() => serverError());
    renderScreen(NEW_PATH);

    await user.type(nameInput(), TYPED_NAME);
    await user.click(button(CREATE_NAME));
    await flush();

    expect(within(mainRegion()).getByText(CREATE_FAILED_TEXT)).toBeInTheDocument();
    expect(locationPath()).toBe(NEW_PATH);
    expect(nameInput()).toHaveValue(TYPED_NAME);
    expect(notificationsShown()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("existing mode at /characters/:id", () => {
  it("shows a loader while the GET is pending, then the character — DoD-5", async () => {
    const gate = deferred<Response>();
    stubBackend((request) => {
      if (request.method === "GET" && request.path === itemPath(ID_A)) {
        return gate.promise;
      }
      // 010 step 006: once the character is ready the Setups section loads its listing.
      if (request.method === "GET" && request.path === setupsPath(ID_A)) {
        return jsonResponse(EMPTY_SETUPS, 200);
      }
      return notFoundResponse();
    });
    renderScreen(`/characters/${ID_A}`);

    expect(loaders().length).toBeGreaterThan(0);

    gate.resolve(jsonResponse(CHAR_A, 200));
    await flush();

    // 010 step 006 (DoD-13): unchanged clause — document-wide, still exactly `[]`. It now
    // waits, because the section renders its own Loader until its listing settles.
    await waitFor(() => {
      expect(loaders()).toEqual([]);
    });
    expect(heading(CHAR_A.name)).toBeInTheDocument();
    expect(nameInput()).toHaveValue(CHAR_A.name);
    expect(personaInput()).toHaveValue(CHAR_A.sheet);
    expect(button(SAVE_NAME)).toBeDisabled();
    expect(button(ARCHIVE_NAME)).toBeInTheDocument();
    expect(within(mainRegion()).queryByText(ARCHIVED_BADGE)).toBeNull();
    expect(heading(SESSIONS_HEADING)).toBeInTheDocument();
  });

  it("editing enables Save, which PATCHes name and sheet and re-renders from the response — DoD-6", async () => {
    const user = newUser();
    const { calls } = stubBackend((request) => {
      if (request.method === "GET" && request.path === itemPath(ID_A)) {
        return jsonResponse(CHAR_A, 200);
      }
      if (request.method === "PATCH" && request.path === itemPath(ID_A)) {
        return jsonResponse(SAVED_A, 200);
      }
      // 010 step 006: the ready screen mounts the Setups section.
      if (request.method === "GET" && request.path === setupsPath(ID_A)) {
        return jsonResponse(EMPTY_SETUPS, 200);
      }
      return notFoundResponse();
    });
    renderScreen(`/characters/${ID_A}`);
    await flush();

    await typeInto(user, nameInput(), EDITED_NAME);
    await typeInto(user, personaInput(), EDITED_SHEET);
    expect(button(SAVE_NAME)).toBeEnabled();

    await user.click(button(SAVE_NAME));
    await flush();

    const patches = matching(calls, "PATCH", itemPath(ID_A));
    expect(patches).toHaveLength(1);
    expect(patches[0].body).toMatchObject({ name: EDITED_NAME, sheet: EDITED_SHEET });
    expect(heading(SAVED_A.name)).toBeInTheDocument();
    expect(button(SAVE_NAME)).toBeDisabled();
  });

  it("Archive and Restore round-trip through their own routes — DoD-7", async () => {
    const user = newUser();
    const { calls } = stubBackend((request) => {
      if (request.method === "GET" && request.path === itemPath(ID_A)) {
        return jsonResponse(CHAR_A, 200);
      }
      if (request.method === "POST" && request.path === `${itemPath(ID_A)}/archive`) {
        return jsonResponse(ARCHIVED_A, 200);
      }
      if (request.method === "POST" && request.path === `${itemPath(ID_A)}/restore`) {
        return jsonResponse(CHAR_A, 200);
      }
      // 010 step 006: the ready screen mounts the Setups section.
      if (request.method === "GET" && request.path === setupsPath(ID_A)) {
        return jsonResponse(EMPTY_SETUPS, 200);
      }
      return notFoundResponse();
    });
    renderScreen(`/characters/${ID_A}`);
    await flush();

    await user.click(button(ARCHIVE_NAME));
    await flush();

    expect(matching(calls, "POST", `${itemPath(ID_A)}/archive`)).toHaveLength(1);
    expect(within(mainRegion()).getByText(ARCHIVED_BADGE)).toBeInTheDocument();
    expect(button(RESTORE_NAME)).toBeInTheDocument();
    expect(queryButton(ARCHIVE_NAME)).toBeNull();

    await user.click(button(RESTORE_NAME));
    await flush();

    expect(matching(calls, "POST", `${itemPath(ID_A)}/restore`)).toHaveLength(1);
    expect(within(mainRegion()).queryByText(ARCHIVED_BADGE)).toBeNull();
    expect(button(ARCHIVE_NAME)).toBeInTheDocument();
  });

  it("an already-archived character opens badged, offers Restore and stays editable — DoD-8", async () => {
    const user = newUser();
    await renderLoaded(ARCHIVED_A);

    expect(within(mainRegion()).getByText(ARCHIVED_BADGE)).toBeInTheDocument();
    expect(button(RESTORE_NAME)).toBeInTheDocument();
    expect(queryButton(ARCHIVE_NAME)).toBeNull();

    expect(nameInput()).toBeEnabled();
    expect(personaInput()).toBeEnabled();

    await typeInto(user, nameInput(), EDITED_NAME);
    await typeInto(user, personaInput(), EDITED_SHEET);

    expect(nameInput()).toHaveValue(EDITED_NAME);
    expect(personaInput()).toHaveValue(EDITED_SHEET);
    expect(button(SAVE_NAME)).toBeEnabled();
  });

  it("a 404 character_not_found renders Character not found in main, with no Retry and no notification — DoD-9", async () => {
    stubBackend(() => notFoundResponse());
    renderScreen(`/characters/${ID_A}`);
    await flush();

    expect(within(mainRegion()).getByText(NOT_FOUND_TEXT)).toBeInTheDocument();
    expect(queryButton(RETRY_NAME)).toBeNull();
    expect(notificationsShown()).toEqual([]);
  });

  it("a 500 on load renders Could not load the character and Retry — DoD-10", async () => {
    stubBackend(() => serverError());
    renderScreen(`/characters/${ID_A}`);
    await flush();

    expect(within(mainRegion()).getByText(LOAD_FAILED_TEXT)).toBeInTheDocument();
    expect(button(RETRY_NAME)).toBeInTheDocument();
  });

  it("a transport failure on load renders Could not load the character and Retry — DoD-10", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<FetchFn>(() => Promise.reject(new TypeError("Failed to fetch"))),
    );
    renderScreen(`/characters/${ID_A}`);
    await flush();

    expect(within(mainRegion()).getByText(LOAD_FAILED_TEXT)).toBeInTheDocument();
    expect(button(RETRY_NAME)).toBeInTheDocument();
  });

  it("Retry requests the character again and renders it on success — DoD-10", async () => {
    const user = newUser();
    let failNext = true;
    const { calls } = stubBackend((request) => {
      if (request.method === "GET" && request.path === itemPath(ID_A)) {
        if (failNext) {
          failNext = false;
          return serverError();
        }
        return jsonResponse(CHAR_A, 200);
      }
      // 010 step 006: the ready screen mounts the Setups section.
      if (request.method === "GET" && request.path === setupsPath(ID_A)) {
        return jsonResponse(EMPTY_SETUPS, 200);
      }
      return notFoundResponse();
    });
    renderScreen(`/characters/${ID_A}`);
    await flush();
    expect(matching(calls, "GET", itemPath(ID_A))).toHaveLength(1);

    await user.click(button(RETRY_NAME));
    await flush();

    expect(matching(calls, "GET", itemPath(ID_A))).toHaveLength(2);
    expect(heading(CHAR_A.name)).toBeInTheDocument();
    expect(nameInput()).toHaveValue(CHAR_A.name);
    expect(within(mainRegion()).queryByText(LOAD_FAILED_TEXT)).toBeNull();
  });

  it("a failed Save reports inline and keeps the edited values in the fields — DoD-11", async () => {
    const user = newUser();
    stubBackend((request) => {
      if (request.method === "GET" && request.path === itemPath(ID_A)) {
        return jsonResponse(CHAR_A, 200);
      }
      // 010 step 006: the section's listing must not fall through to the 500 below, or the
      // section would render its own failure text and "Retry" inside the main region.
      if (request.method === "GET" && request.path === setupsPath(ID_A)) {
        return jsonResponse(EMPTY_SETUPS, 200);
      }
      return serverError();
    });
    renderScreen(`/characters/${ID_A}`);
    await flush();

    await typeInto(user, nameInput(), EDITED_NAME);
    await typeInto(user, personaInput(), EDITED_SHEET);
    await user.click(button(SAVE_NAME));
    await flush();

    expect(within(mainRegion()).getByText(SAVE_FAILED_TEXT)).toBeInTheDocument();
    expect(nameInput()).toHaveValue(EDITED_NAME);
    expect(personaInput()).toHaveValue(EDITED_SHEET);
  });
});

// ---------------------------------------------------------------------------
describe("moving between characters builds a fresh screen (CharacterRoute is keyed by id)", () => {
  it("navigating from one character to another requests and shows the second, carrying no draft over — DoD-12", async () => {
    const user = newUser();
    const DRAFT_ONLY = "Draft only zq-55";
    const { calls } = serveCharacters(CHAR_A, CHAR_B);
    renderScreen(`/characters/${ID_A}`);
    await flush();

    await typeInto(user, nameInput(), DRAFT_ONLY);
    expect(nameInput()).toHaveValue(DRAFT_ONLY);

    await user.click(screen.getByRole("button", { name: PROBE_NAVIGATE }));
    await flush();

    expect(locationPath()).toBe(`/characters/${ID_B}`);
    expect(matching(calls, "GET", itemPath(ID_B))).toHaveLength(1);
    expect(heading(CHAR_B.name)).toBeInTheDocument();
    expect(nameInput()).toHaveValue(CHAR_B.name);
    expect(personaInput()).toHaveValue(CHAR_B.sheet);
    expect(within(mainRegion()).queryByDisplayValue(DRAFT_ONLY)).toBeNull();
  });
});
