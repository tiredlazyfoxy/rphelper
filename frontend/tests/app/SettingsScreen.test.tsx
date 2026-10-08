// Feature 017, step 007 — the settings screen (DoD-4..DoD-7).
// DoD-1..DoD-3 are settingsState.test.ts's; DoD-8 and DoD-9 are App.test.tsx's (with the
// entries.test.tsx stub amendment); DoD-10 is [manual/live] and carries no test.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 007.context.md and context.md's D15 (on-page form, "Your notes" group, not reorderable), D19
// (every failure in its own place, no notification), the Wire contract and the UI strings table:
//   - a heading "Settings", then a region "Languages" (heading "Languages") with the text inputs
//     "RP language" and "Preferred language" (each described "Used by every session that does
//     not set its own.") and "Save" enabled iff there is something to save, then the region
//     "Your notes" — 015's MemoLevelGroup over the user level (`GET /api/memos?scope=user`);
//   - a failed settings load: "Could not load your settings" + "Retry" in "Languages";
//   - a failed save: "Could not save your settings." in "Languages";
//   - a new note at the user level POSTs `{ scope: "user", scope_id: null, body }`;
//   - no note carries a reorder position name ("Note <n> of <total>").
//
// Recognition conventions (for the verifier):
// - The screen renders alone inside `AppProviders` and a `MemoryRouter`. Regions and controls
//   are found by accessible name only; headings by name, never level.
// - `src/shared/MarkdownEditor` is the labelled-`<textarea>` stub (id from `useId`, several
//   "Note" editors may be on screen). A note's text is its textarea's value; focus loss is
//   `fireEvent.blur`, typing in a note is `fireEvent.change`.
// - `notifyFailure` is replaced by a spy; a notification in the DOM is `.mantine-Notification-root`.
// - `fetch` is stubbed per test; requests are recorded by exact method + pathname + query string
//   with the parsed JSON body.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ChangeEvent, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SettingsScreen } from "../../src/app/SettingsScreen";
import type { UserSettings } from "../../src/app/configurationApi";
import type { Memo } from "../../src/app/memosApi";
import { AppProviders } from "../../src/shared/AppProviders";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

vi.mock("../../src/shared/MarkdownEditor", async () => {
  const { createElement, useId } = await import("react");
  type StubProps = {
    label: string;
    value: string;
    onChange: (markdown: string) => void;
    readOnly?: boolean;
    toolbarActions?: ReactNode;
  };
  return {
    MarkdownEditor: (props: StubProps) => {
      const id = `markdown-editor-${useId()}`;
      return createElement(
        "div",
        { "data-testid": "markdown-editor-stub" },
        createElement("label", { htmlFor: id }, props.label),
        createElement("textarea", {
          id,
          value: props.value,
          readOnly: props.readOnly ?? false,
          onChange: (event: ChangeEvent<HTMLTextAreaElement>) => props.onChange(event.target.value),
        }),
        // fast 012: the toolbar-actions prop (a saved note's flags) renders inside the root.
        props.toolbarActions === undefined || props.toolbarActions === null
          ? null
          : createElement("div", { "data-testid": "stub-toolbar-actions" }, props.toolbarActions),
      );
    },
  };
});

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string; body: unknown };
type Handler = (request: Seen) => Response | Promise<Response>;

// ---------------------------------------------------------------- the spec's names
const SETTINGS_HEADING = "Settings";
const LANGUAGES = "Languages";
const RP_LANGUAGE = "RP language";
const PREFERRED_LANGUAGE = "Preferred language";
const DESCRIPTION = "Used by every session that does not set its own.";
const SAVE = "Save";
const LOAD_FAILED = "Could not load your settings";
const RETRY = "Retry";
const SAVE_FAILED = "Could not save your settings.";
const YOUR_NOTES = "Your notes";

// 015's group strings, which apply inside "Your notes".
const NOTE_LABEL = "Note";
const NEW_NOTE = "New note";
const DISABLE_NOTE = "Disable note";
const POSITION_NAME = /^Note \d+ of \d+$/;

const NOTIFICATION = ".mantine-Notification-root";

// ---------------------------------------------------------------- fixtures
const SETTINGS_PATH = "/api/me/settings";
const MEMOS_PATH = "/api/memos";
const USER_NOTES_SEARCH = "?scope=user";

const STAMP = "2026-10-02T09:26:53.000000+00:00";
const CREATED_STAMP = "2026-10-02T09:40:00.000000+00:00";
const CREATED_ID = "9007199254740999";

const BODY_1 = "Always write in past tense.";
const BODY_2 = "Keep replies under three paragraphs.";
const TYPED_NOTE = "Prefer British spelling.";

/** A user-level wire Memo with all nine keys. */
function memo(id: string, body: string, overrides: Partial<Memo> = {}): Memo {
  return {
    id,
    scope: "user",
    scope_id: null,
    body,
    is_enabled: true,
    is_forced: false,
    sort_key: 0,
    created_at: STAMP,
    updated_at: STAMP,
    ...overrides,
  };
}

const USER_NOTES: Memo[] = [
  memo("7250000000000000401", BODY_1),
  memo("7250000000000000402", BODY_2, { sort_key: 1 }),
];

const SERVED: UserSettings = { rp_language: "Japanese", preferred_language: "English" };
const EMPTY_SETTINGS: UserSettings = { rp_language: null, preferred_language: null };

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  notifyFailureSpy.mockReset();
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
  return JSON.parse(String(raw)) as unknown;
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: "ql-77 went wrong.", detail: {} } }, status);
}

function serverError(): Response {
  return envelope("internal_error", 500);
}

function stubBackend(handler: Handler) {
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

function isSettingsRead(request: Seen): boolean {
  return request.method === "GET" && request.path === SETTINGS_PATH && request.search === "";
}

function isSettingsPatch(request: Seen): boolean {
  return request.method === "PATCH" && request.path === SETTINGS_PATH && request.search === "";
}

function isUserNotesListing(request: Seen): boolean {
  return request.method === "GET" && request.path === MEMOS_PATH && request.search === USER_NOTES_SEARCH;
}

function isMemoCreate(request: Seen): boolean {
  return request.method === "POST" && request.path === MEMOS_PATH && request.search === "";
}

type BackendOptions = {
  settings?: () => Response;
  patch?: (request: Seen) => Response;
  notes?: Memo[];
};

/**
 * The settings read, the settings PATCH (answering the sent keys merged over `SERVED` by
 * default), the user notes listing and the memo create (201, the created row from what was
 * sent). Everything else 404s.
 */
function serveBackend(options: BackendOptions = {}) {
  const settings = options.settings ?? (() => jsonResponse(SERVED, 200));
  const notes = options.notes ?? USER_NOTES;
  return stubBackend((request) => {
    if (isSettingsRead(request)) return settings();
    if (isSettingsPatch(request)) {
      if (options.patch !== undefined) return options.patch(request);
      const sent = (request.body ?? {}) as Partial<UserSettings>;
      return jsonResponse({ ...SERVED, ...sent }, 200);
    }
    if (isUserNotesListing(request)) return jsonResponse({ memos: notes }, 200);
    if (isMemoCreate(request)) {
      const sent = request.body as { scope: "user"; scope_id: null; body: string };
      return jsonResponse(
        memo(CREATED_ID, sent.body, {
          scope: sent.scope,
          scope_id: sent.scope_id,
          created_at: CREATED_STAMP,
          updated_at: CREATED_STAMP,
        }),
        201,
      );
    }
    return envelope("not_found", 404);
  });
}

async function settle(): Promise<void> {
  await act(async () => {
    for (let round = 0; round < 6; round += 1) await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
    for (let round = 0; round < 6; round += 1) await Promise.resolve();
  });
}

function newUser() {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

// ---------------------------------------------------------------- render + queries
function renderScreen() {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={["/settings"]}>
        <SettingsScreen />
      </MemoryRouter>
    </AppProviders>,
  );
}

function languagesRegion(): HTMLElement {
  return screen.getByRole("region", { name: LANGUAGES });
}

function notesRegion(): HTMLElement {
  return screen.getByRole("region", { name: YOUR_NOTES });
}

function rpBox(): HTMLInputElement {
  return within(languagesRegion()).getByRole("textbox", { name: RP_LANGUAGE }) as HTMLInputElement;
}

function preferredBox(): HTMLInputElement {
  return within(languagesRegion()).getByRole("textbox", { name: PREFERRED_LANGUAGE }) as HTMLInputElement;
}

function saveButton(): HTMLElement {
  return within(languagesRegion()).getByRole("button", { name: SAVE });
}

function noteItems(): HTMLElement[] {
  return within(notesRegion()).queryAllByRole("listitem");
}

function noteBodies(): string[] {
  return within(notesRegion())
    .queryAllByRole("textbox", { name: NOTE_LABEL })
    .map((box) => (box as HTMLTextAreaElement).value);
}

/** Waits until both loads have answered: the inputs carry values and the notes are listed. */
async function waitForReady(notesCount: number = USER_NOTES.length): Promise<void> {
  await waitFor(() => {
    expect(within(languagesRegion()).queryByRole("textbox", { name: RP_LANGUAGE })).not.toBeNull();
    expect(noteBodies()).toHaveLength(notesCount);
  });
  await settle();
}

function follows(earlier: HTMLElement, later: HTMLElement): boolean {
  return (earlier.compareDocumentPosition(later) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

// ===========================================================================
describe("the settings screen with both loads answered (US-092.AC-1, D15)", () => {
  it('renders the "Settings" heading, the "Languages" region and the "Your notes" region, in that document order — DoD-4', async () => {
    serveBackend();
    renderScreen();
    await waitForReady();

    const heading = screen.getByRole("heading", { name: SETTINGS_HEADING });
    const languages = languagesRegion();
    const notes = notesRegion();
    expect(languages.contains(heading)).toBe(false);
    expect(notes.contains(heading)).toBe(false);
    expect(follows(heading, languages)).toBe(true);
    expect(follows(languages, notes)).toBe(true);
    expect(languages.contains(notes)).toBe(false);
  });

  it('the "Languages" region is headed "Languages" and holds both textboxes with the served values — DoD-4', async () => {
    serveBackend();
    renderScreen();
    await waitForReady();

    expect(within(languagesRegion()).getByRole("heading", { name: LANGUAGES })).toBeInTheDocument();
    expect(rpBox()).toHaveValue("Japanese");
    expect(preferredBox()).toHaveValue("English");
    expect(follows(rpBox(), preferredBox())).toBe(true);
  });

  it("a null served language shows as an empty textbox — DoD-4", async () => {
    serveBackend({ settings: () => jsonResponse({ rp_language: "Japanese", preferred_language: null }, 200) });
    renderScreen();
    await waitForReady();

    expect(rpBox()).toHaveValue("Japanese");
    expect(preferredBox()).toHaveValue("");
  });

  it('each textbox is described "Used by every session that does not set its own." — DoD-4', async () => {
    serveBackend();
    renderScreen();
    await waitForReady();

    expect(rpBox()).toHaveAccessibleDescription(DESCRIPTION);
    expect(preferredBox()).toHaveAccessibleDescription(DESCRIPTION);
  });

  it('"Save" sits in the "Languages" region and is disabled while nothing has changed — DoD-4', async () => {
    serveBackend();
    renderScreen();
    await waitForReady();

    expect(saveButton()).toBeDisabled();
  });

  it('the "Your notes" region, headed "Your notes", lists the user\'s notes from GET /api/memos?scope=user in order — DoD-4', async () => {
    const { calls } = serveBackend();
    renderScreen();
    await waitForReady();

    expect(within(notesRegion()).getByRole("heading", { name: YOUR_NOTES })).toBeInTheDocument();
    expect(noteBodies()).toEqual([BODY_1, BODY_2]);
    const listings = calls.filter((call) => call.method === "GET" && call.path === MEMOS_PATH);
    expect(listings).toEqual([{ method: "GET", path: MEMOS_PATH, search: USER_NOTES_SEARCH, body: undefined }]);
    expect(calls.filter(isSettingsRead)).toHaveLength(1);
  });
});

// ===========================================================================
describe("saving both languages (US-058.AC-1, US-092.AC-1)", () => {
  it('typing "Japanese" and "English" then pressing "Save" PATCHes both keys; the inputs show the served values and "Save" is disabled — DoD-5', async () => {
    const answered: UserSettings = { rp_language: "Japanese", preferred_language: "English" };
    const { calls } = serveBackend({
      settings: () => jsonResponse(EMPTY_SETTINGS, 200),
      patch: () => jsonResponse(answered, 200),
    });
    renderScreen();
    await waitForReady();
    expect(rpBox()).toHaveValue("");
    expect(preferredBox()).toHaveValue("");

    const user = newUser();
    await user.type(rpBox(), "Japanese");
    await user.type(preferredBox(), "English");
    expect(saveButton()).toBeEnabled();
    await user.click(saveButton());

    await waitFor(() => {
      expect(calls.filter(isSettingsPatch)).toHaveLength(1);
    });
    expect(calls.filter(isSettingsPatch)[0].body).toEqual({
      rp_language: "Japanese",
      preferred_language: "English",
    });

    await waitFor(() => {
      expect(saveButton()).toBeDisabled();
    });
    expect(rpBox()).toHaveValue(answered.rp_language);
    expect(preferredBox()).toHaveValue(answered.preferred_language);
    expect(within(languagesRegion()).queryByText(SAVE_FAILED)).toBeNull();
  });

  it("the inputs after a save show what the server answered, not what was typed — DoD-5", async () => {
    const { calls } = serveBackend({
      settings: () => jsonResponse(EMPTY_SETTINGS, 200),
      patch: () => jsonResponse({ rp_language: "Japanese", preferred_language: "English" }, 200),
    });
    renderScreen();
    await waitForReady();

    const user = newUser();
    await user.type(rpBox(), "  Japanese  ");
    await user.type(preferredBox(), "English");
    await user.click(saveButton());

    await waitFor(() => {
      expect(rpBox()).toHaveValue("Japanese");
    });
    expect(calls.filter(isSettingsPatch)[0].body).toEqual({
      rp_language: "Japanese",
      preferred_language: "English",
    });
    expect(saveButton()).toBeDisabled();
  });
});

// ===========================================================================
describe("failures render in the Languages region, never as a notification (D19)", () => {
  it('a failed settings load shows "Could not load your settings" and "Retry" inside "Languages", while "Your notes" still renders — DoD-6', async () => {
    serveBackend({ settings: serverError });
    renderScreen();

    await waitFor(() => {
      expect(within(languagesRegion()).queryByText(LOAD_FAILED)).not.toBeNull();
    });
    expect(within(languagesRegion()).getByRole("button", { name: RETRY })).toBeInTheDocument();
    expect(within(languagesRegion()).queryByRole("textbox", { name: RP_LANGUAGE })).toBeNull();
    await waitFor(() => {
      expect(noteBodies()).toEqual([BODY_1, BODY_2]);
    });
    expect(within(notesRegion()).getByRole("heading", { name: YOUR_NOTES })).toBeInTheDocument();
    await settle();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(document.querySelector(NOTIFICATION)).toBeNull();
  });

  it('"Retry" re-requests GET /api/me/settings and, on success, the inputs render with the served values — DoD-6', async () => {
    let failNext = true;
    const { calls } = serveBackend({
      settings: () => {
        if (failNext) {
          failNext = false;
          return serverError();
        }
        return jsonResponse(SERVED, 200);
      },
    });
    renderScreen();
    await waitFor(() => {
      expect(within(languagesRegion()).queryByText(LOAD_FAILED)).not.toBeNull();
    });
    await settle();
    expect(calls.filter(isSettingsRead)).toHaveLength(1);

    await newUser().click(within(languagesRegion()).getByRole("button", { name: RETRY }));

    await waitFor(() => {
      expect(within(languagesRegion()).queryByRole("textbox", { name: RP_LANGUAGE })).not.toBeNull();
    });
    expect(calls.filter(isSettingsRead)).toHaveLength(2);
    expect(rpBox()).toHaveValue("Japanese");
    expect(preferredBox()).toHaveValue("English");
    expect(within(languagesRegion()).queryByText(LOAD_FAILED)).toBeNull();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it('a failed save shows "Could not save your settings." in "Languages" and keeps the typed text — DoD-6', async () => {
    serveBackend({ patch: () => serverError() });
    renderScreen();
    await waitForReady();

    const user = newUser();
    await user.clear(rpBox());
    await user.type(rpBox(), "French");
    await user.click(saveButton());

    await waitFor(() => {
      expect(within(languagesRegion()).queryByText(SAVE_FAILED)).not.toBeNull();
    });
    expect(rpBox()).toHaveValue("French");
    expect(preferredBox()).toHaveValue("English");
    await settle();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(document.querySelector(NOTIFICATION)).toBeNull();
  });

  it("a failed notes load leaves the Languages form in place, with no notification — DoD-6", async () => {
    stubBackend((request) => {
      if (isSettingsRead(request)) return jsonResponse(SERVED, 200);
      return serverError();
    });
    renderScreen();

    await waitFor(() => {
      expect(within(languagesRegion()).queryByRole("textbox", { name: RP_LANGUAGE })).not.toBeNull();
    });
    expect(notesRegion()).toBeInTheDocument();
    await settle();
    expect(rpBox()).toHaveValue("Japanese");
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(document.querySelector(NOTIFICATION)).toBeNull();
  });
});

// ===========================================================================
describe('"Your notes" is the user level, not reorderable (US-092.AC-1, D15)', () => {
  it('"New note", typing and blurring POSTs /api/memos with exactly {"scope":"user","scope_id":null,"body":…} — DoD-7', async () => {
    const { calls } = serveBackend({ notes: [] });
    renderScreen();
    await waitForReady(0);

    await newUser().click(within(notesRegion()).getByRole("button", { name: NEW_NOTE }));
    await waitFor(() => {
      expect(noteItems()).toHaveLength(1);
    });
    const editor = within(noteItems()[0]).getByRole("textbox", { name: NOTE_LABEL });
    fireEvent.change(editor, { target: { value: TYPED_NOTE } });
    fireEvent.blur(editor);

    await waitFor(() => {
      expect(calls.filter(isMemoCreate)).toHaveLength(1);
    });
    expect(calls.filter(isMemoCreate)[0]).toEqual({
      method: "POST",
      path: MEMOS_PATH,
      search: "",
      body: { scope: "user", scope_id: null, body: TYPED_NOTE },
    });
    await waitFor(() => {
      expect(within(noteItems()[0]).queryByRole("button", { name: DISABLE_NOTE })).not.toBeNull();
    });
    expect(noteBodies()).toEqual([TYPED_NOTE]);
  });

  it('no note in the group exposes a reorder position name ("Note 1 of …") — DoD-7', async () => {
    serveBackend();
    renderScreen();
    await waitForReady();

    expect(noteItems()).toHaveLength(USER_NOTES.length);
    expect(within(notesRegion()).queryAllByRole("listitem", { name: POSITION_NAME })).toEqual([]);
    for (const item of noteItems()) {
      expect(item).not.toHaveAttribute("aria-roledescription");
    }
  });

  it("with a new note open, still no note exposes a position name — DoD-7", async () => {
    serveBackend();
    renderScreen();
    await waitForReady();

    await newUser().click(within(notesRegion()).getByRole("button", { name: NEW_NOTE }));
    await waitFor(() => {
      expect(noteItems()).toHaveLength(USER_NOTES.length + 1);
    });
    expect(within(notesRegion()).queryAllByRole("listitem", { name: POSITION_NAME })).toEqual([]);
  });
});

// ===========================================================================
// Fast feature 012 — "Your notes" inherits the one note behaviour (012 plan.md Interface intent
// "MemoLevelGroup"; DoD-3, DoD-5, DoD-10). The stub renders the `toolbarActions` prop inside its
// root as `[data-testid="stub-toolbar-actions"]`.
describe('fast 012 — "Your notes" header \'+\', no Save / Cancel, flags in the editor', () => {
  it('exactly one "New note" button renders, in the group header beside the "Your notes" title and before the list — fast 012 DoD-3', async () => {
    serveBackend();
    renderScreen();
    await waitForReady();

    const buttons = within(notesRegion()).getAllByRole("button", { name: NEW_NOTE });
    expect(buttons).toHaveLength(1);
    const plus = buttons[0];
    const heading = within(notesRegion()).getByRole("heading", { name: YOUR_NOTES });
    expect(heading.parentElement?.contains(plus)).toBe(true);
    const list = noteItems()[0].closest("ul");
    expect(list).not.toBeNull();
    expect(follows(heading, plus)).toBe(true);
    expect(follows(plus, list as HTMLElement)).toBe(true);
    for (const item of noteItems()) {
      expect(item.contains(plus)).toBe(false);
    }
  });

  it('no "Save new note" or "Cancel new note" renders, before or with a draft open — fast 012 DoD-5', async () => {
    serveBackend();
    renderScreen();
    await waitForReady();

    expect(screen.queryByRole("button", { name: "Save new note" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Cancel new note" })).toBeNull();
    await newUser().click(within(notesRegion()).getByRole("button", { name: NEW_NOTE }));
    await waitFor(() => {
      expect(noteItems()).toHaveLength(USER_NOTES.length + 1);
    });
    expect(within(notesRegion()).getByRole("button", { name: NEW_NOTE })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save new note" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Cancel new note" })).toBeNull();
  });

  it("each saved note's flag buttons render inside its editor root — fast 012 DoD-10", async () => {
    serveBackend();
    renderScreen();
    await waitForReady();

    for (const item of noteItems()) {
      const root = item.querySelector('[data-testid="markdown-editor-stub"]');
      expect(root).not.toBeNull();
      const disable = within(item).getByRole("button", { name: DISABLE_NOTE });
      const force = within(item).getByRole("button", { name: "Force note" });
      expect((root as HTMLElement).contains(disable)).toBe(true);
      expect((root as HTMLElement).contains(force)).toBe(true);
    }
  });
});
