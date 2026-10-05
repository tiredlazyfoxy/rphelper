// Feature 030 — export-granularities, step 006: the character screen's Export button
// (DoD-4, DoD-5, and DoD-7 / DoD-8 for this control). The module's own clauses live in
// `exportDownloads.test.ts`; the other two controls have their own files. DoD-9 and DoD-10 are
// [manual/live] and carry no test.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 006.context.md and the feature context.md: the button sits next to Archive/Restore and renders
// under exactly the same condition (a persisted character), so the draft page offers no export;
// clicking it downloads that character's export route; success is silent (no success toast) and a
// failure in the `app` entry goes through `notifyFailure`; and no export opens a confirm dialog,
// because an export is not lossy. Bindings come from the frozen `### Step 006` record: the
// button's accessible name is exactly `Export`, and the route is
// `GET /api/characters/{character_id}/export` (context.md "Routes").
//
// Harness conventions (006.context.md, 004.context.md):
// - The screen renders inside `AppProviders` + `MemoryRouter` in the `<main>` landmark the shell
//   gives it, so the notifications outlet exists and "nothing was notified" / "one notification
//   carrying the message" are observable through `.mantine-Notification-root`. `notifyFailure` is
//   deliberately NOT mocked: the clause is about what the user is shown, so the real channel runs.
// - `fetch` is stubbed per test and routed by **exact pathname** (plus the exact query string for
//   the memos listing, whose pathname is shared); the screen's own mount loads the character, its
//   setups, its sessions, its configuration, the enabled models and its notes, all answered empty.
// - `apiDownload` runs for real, so jsdom's missing `URL.createObjectURL` / `URL.revokeObjectURL`
//   are installed per test and removed afterwards, and the anchor click is swallowed by a spy on
//   `HTMLAnchorElement.prototype.click` so jsdom never navigates.
// - "The same action group" is the Mantine `Group` the Archive/Restore button sits in: both
//   buttons resolve to the same `.mantine-Group-root` ancestor.
// - `src/shared/MarkdownEditor` is replaced by the repo's sanctioned stub (context.md "Test
//   conventions — TipTap in jsdom"), as in `CharacterScreen.test.tsx`.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ChangeEvent } from "react";
import { CharacterRoute, CharacterScreen } from "../../src/app/CharacterScreen";
import type { Character } from "../../src/app/charactersApi";
import type { CharacterConfiguration } from "../../src/app/configurationApi";
import { CharactersState } from "../../src/app/charactersState";
import { SessionsState } from "../../src/app/sessionsState";
import { documentNavigation } from "../../src/shared/api";
import { AppProviders } from "../../src/shared/AppProviders";

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
type Seen = { method: string; path: string; search: string };
type User = ReturnType<typeof userEvent.setup>;

// ---------------------------------------------------------------- the spec's names
const EXPORT_NAME = /^export$/i;
const ARCHIVE_NAME = /^archive$/i;
const RESTORE_NAME = /^restore$/i;

const NOTIFICATION = ".mantine-Notification-root";
const GROUP_ROOT = ".mantine-Group-root";

/** The message the error envelope carries; a notification must show it (DoD-7). */
const FAILURE_MESSAGE = "That character does not exist (zq-404 marker).";

/** Success is silent (context.md "No success toasts"): none of these may appear. */
const SUCCESS_TALK = /\b(success|succeeded|successfully|downloaded|exported|completed|finished)\b/i;

// ---------------------------------------------------------------- fixtures
// Ids are decimal strings past Number.MAX_SAFE_INTEGER (context.md "Ids are strings").
const ID_A = "7250000000000000011";
/** A second id, never rendered: a wrong-id export would hit this path instead. */
const ID_B = "7250000000000000012";

const NEW_PATH = "/characters/new";
const COLLECTION_PATH = "/api/characters";
const MODELS_PATH = "/api/models";
const MEMOS_PATH = "/api/memos";

const CHAR_A: Character = {
  id: ID_A,
  name: "Aria Vance",
  sheet: "A scribe who never finishes a sentence.",
  archived_at: null,
  created_at: "2026-03-14T09:26:53.000000+00:00",
  updated_at: "2026-03-14T09:26:53.000000+00:00",
};

const ARCHIVED_A: Character = {
  ...CHAR_A,
  archived_at: "2026-04-05T10:00:00.000000+00:00",
  updated_at: "2026-04-05T10:00:00.000000+00:00",
};

const UNSET_CONFIGURATION: CharacterConfiguration = {
  model: null,
  system_prompt: null,
  tool_memo_search: null,
  tool_session_search: null,
  tool_web_search: null,
};

const EXPORT_FILENAME = "rphelper-character-20260105T101112Z.json";

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
function itemPath(characterId: string): string {
  return `${COLLECTION_PATH}/${characterId}`;
}

/** context.md "Routes" — one character's export. */
function exportPath(characterId: string): string {
  return `${itemPath(characterId)}/export`;
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
  return new Response('{"format":"rphelper-export","granularity":"character","payload":{}}', {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Content-Disposition": `attachment; filename="${EXPORT_FILENAME}"`,
    },
  });
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

/** The six reads a loaded character's screen makes on mount, all answered empty. */
function mountRead(request: Seen, characterId: string): Response | null {
  if (request.method !== "GET") return null;
  if (request.path === `${itemPath(characterId)}/setups`) return jsonResponse({ setups: [] }, 200);
  if (request.path === `${itemPath(characterId)}/sessions`) return jsonResponse({ sessions: [] }, 200);
  if (request.path === `${itemPath(characterId)}/configuration`) {
    return jsonResponse(UNSET_CONFIGURATION, 200);
  }
  if (request.path === MODELS_PATH) return jsonResponse({ models: [] }, 200);
  if (request.path === MEMOS_PATH) return jsonResponse({ memos: [] }, 200);
  return null;
}

/** Routes by exact pathname; every unknown request is a visible 404. */
function stubBackend(row: Character, options: { failExport?: boolean } = {}) {
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>((input, init) => {
    const url = requestUrl(input);
    const request: Seen = {
      method: requestMethod(input, init),
      path: url.pathname,
      search: url.search,
    };
    calls.push(request);

    if (request.method === "GET" && request.path === exportPath(row.id)) {
      return Promise.resolve(
        options.failExport === true ? envelope("character_not_found", 404) : exportResponse(),
      );
    }
    if (request.method === "GET" && request.path === itemPath(row.id)) {
      return Promise.resolve(jsonResponse(row, 200));
    }
    const read = mountRead(request, row.id);
    if (read !== null) return Promise.resolve(read);
    return Promise.resolve(envelope("character_not_found", 404));
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

function matching(calls: Seen[], method: string, path: string): Seen[] {
  return calls.filter((call) => call.method === method && call.path === path);
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
function renderScreen(initialPath: string) {
  const characters = new CharactersState();
  const sessions = new SessionsState();
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={[initialPath]}>
        <main>
          <Routes>
            <Route
              path="/characters/new"
              element={
                <CharacterScreen characters={characters} characterId={null} sessions={sessions} />
              }
            />
            <Route
              path="/characters/:id"
              element={<CharacterRoute characters={characters} sessions={sessions} />}
            />
          </Routes>
        </main>
      </MemoryRouter>
    </AppProviders>,
  );
}

/** Loads `row` at its own route and settles the mount's reads. */
async function renderLoaded(row: Character, options: { failExport?: boolean } = {}) {
  const server = stubBackend(row, options);
  renderScreen(`/characters/${row.id}`);
  await flush();
  return server;
}

// ---------------------------------------------------------------- queries
function mainRegion(): HTMLElement {
  return screen.getByRole("main");
}

function button(name: RegExp): HTMLElement {
  return within(mainRegion()).getByRole("button", { name });
}

function queryButton(name: RegExp): HTMLElement | null {
  return within(mainRegion()).queryByRole("button", { name });
}

/** The Mantine `Group` a control sits in — "the same action group" (DoD-4). */
function groupOf(element: HTMLElement): HTMLElement | null {
  return element.closest<HTMLElement>(GROUP_ROOT);
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

async function clickExport(user: User): Promise<void> {
  await user.click(button(EXPORT_NAME));
  await flush();
}

// ===========================================================================
describe("a persisted character offers Export beside Archive/Restore (US-080.AC-1)", () => {
  it("an active character's screen shows Export in the same action group as Archive — DoD-4", async () => {
    await renderLoaded(CHAR_A);

    const exportButton = button(EXPORT_NAME);
    const archiveButton = button(ARCHIVE_NAME);

    expect(groupOf(exportButton)).not.toBeNull();
    expect(groupOf(exportButton)).toBe(groupOf(archiveButton));
  });

  it("an archived character's screen shows Export in the same action group as Restore — DoD-4", async () => {
    await renderLoaded(ARCHIVED_A);

    const exportButton = button(EXPORT_NAME);
    const restoreButton = button(RESTORE_NAME);

    expect(queryButton(ARCHIVE_NAME)).toBeNull();
    expect(groupOf(exportButton)).not.toBeNull();
    expect(groupOf(exportButton)).toBe(groupOf(restoreButton));
  });

  it("clicking it requests GET /api/characters/<that id>/export, once — DoD-4", async () => {
    const { calls } = await renderLoaded(CHAR_A);
    const user = newUser();

    await clickExport(user);

    expect(matching(calls, "GET", exportPath(ID_A))).toHaveLength(1);
    // Never another character's export: a wrong-id implementation would land here.
    expect(matching(calls, "GET", exportPath(ID_B))).toEqual([]);
  });

  it("an archived character exports through the same route — DoD-4", async () => {
    const { calls } = await renderLoaded(ARCHIVED_A);
    const user = newUser();

    await clickExport(user);

    expect(matching(calls, "GET", exportPath(ID_A))).toHaveLength(1);
  });
});

// ===========================================================================
describe("the draft page offers no export (DoD-5)", () => {
  it("renders no Export button at /characters/new — DoD-5", async () => {
    const { calls } = stubBackend(CHAR_A);
    renderScreen(NEW_PATH);
    await flush();

    expect(queryButton(EXPORT_NAME)).toBeNull();
    expect(screen.queryByRole("button", { name: EXPORT_NAME })).toBeNull();
    // And there is no Archive/Restore either: the Export button follows their condition exactly.
    expect(queryButton(ARCHIVE_NAME)).toBeNull();
    expect(queryButton(RESTORE_NAME)).toBeNull();
    expect(calls).toEqual([]);
  });
});

// ===========================================================================
describe("feedback: silent on success, one notification on failure (DoD-7)", () => {
  it("a successful export raises no notification and shows no success text — DoD-7", async () => {
    const { calls } = await renderLoaded(CHAR_A);
    const user = newUser();

    await clickExport(user);

    // The export really reached the server, so the silence below is a successful export's.
    expect(matching(calls, "GET", exportPath(ID_A))).toEqual([
      { method: "GET", path: exportPath(ID_A), search: "" },
    ]);

    expect(notificationRoots()).toEqual([]);
    expect(readableText()).not.toMatch(SUCCESS_TALK);
    expect(readableText()).not.toContain(EXPORT_FILENAME);
  });

  it("a failed export raises exactly one notification carrying the error's message — DoD-7", async () => {
    await renderLoaded(CHAR_A, { failExport: true });
    const user = newUser();

    await clickExport(user);

    await waitFor(() => {
      expect(notificationRoots()).toHaveLength(1);
    });
    expect(notificationRoots()[0].textContent ?? "").toContain(FAILURE_MESSAGE);
  });
});

// ===========================================================================
describe("no confirm dialog stands between the click and the request (DoD-8)", () => {
  it("one click on Export goes straight to the request — DoD-8", async () => {
    const { calls } = await renderLoaded(CHAR_A);
    const user = newUser();
    expect(dialogs()).toEqual([]);

    await clickExport(user);

    expect(dialogs()).toEqual([]);
    expect(matching(calls, "GET", exportPath(ID_A))).toHaveLength(1);
  });
});
