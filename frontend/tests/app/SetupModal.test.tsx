// Feature 010, step 005 — the create / edit setup modal (DoD-5..DoD-9).
// DoD-1..DoD-4 live in setupDraft.test.ts; DoD-10 is [manual/live] and carries no test.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 005.context.md and context.md's D2 (the modal's titles, labels and submit labels; edit
// sends both fields; the submit needs a change), D8 (the name is sent as typed and stripped
// by the server), D12 (the two fixed sentences, rendered inside the modal, and no
// notification anywhere in 010), plus the "Never optimistic" constraint (what renders and
// what reaches `onSaved` is the server's returned row).
//
// Recognition conventions (from the spec's wording, for the verifier):
// - The accessible names are the contract: the dialog's title "New setup" / "Edit setup",
//   the textboxes "Name" and "Description", the buttons "Cancel" and "Create" / "Save".
//   Everything is queried by role + accessible name or by text.
// - Mantine renders a `Modal` into a portal outside the render container, so the dialog is
//   queried through `screen` and its contents through `within(dialog())` (context.md "Test
//   conventions — Mantine portals"). 005.context.md asks for `findByRole("dialog", { name })`
//   for the first assertion, which is what DoD-5 and DoD-7 use.
// - A notification: `.mantine-Notification-root` (the repo's existing convention). 010 adds
//   no `notifyFailure` call site (D12), so the expected count is always zero.
// - `src/shared/MarkdownEditor` is replaced by the sanctioned stub (context.md "Test
//   conventions"): a labelled `<textarea>` honouring `label`, `value`, `onChange` and
//   `readOnly`, so "Description" is typed reliably in jsdom.
// - The modal does **not** close itself on success (005.context.md "`onSaved` and closing"):
//   success is asserted through `onSaved`, never through the dialog disappearing.
// - No `MemoryRouter`: a setup has no route, and the modal is rendered standalone inside
//   `AppProviders`.
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChangeEvent } from "react";
import { SetupModal } from "../../src/app/SetupModal";
import type { Setup } from "../../src/app/setupsApi";
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
const NEW_TITLE = /^new setup$/i;
const EDIT_TITLE = /^edit setup$/i;
const NAME_LABEL = /^name$/i;
const DESCRIPTION_LABEL = /^description$/i;
const CANCEL_NAME = /^cancel$/i;
const CREATE_NAME = /^create$/i;
const SAVE_NAME = /^save$/i;
const CREATE_FAILED_TEXT = "Could not create the setup.";
const SAVE_FAILED_TEXT = "Could not save the setup.";

const NOTIFICATION = ".mantine-Notification-root";

// ---------------------------------------------------------------- fixtures
// Every id is a decimal string past Number.MAX_SAFE_INTEGER, so any coercion would show up
// in the request path (context.md "Ids are strings in every frontend file").
const CHARACTER_ID = "7250000000000000001";
const SETUP_ID = "7260000000000000001";
const CREATED_ID = "9007199254740993"; // 2^53 + 1

const COLLECTION_PATH = `/api/characters/${CHARACTER_ID}/setups`;
const ITEM_PATH = `/api/setups/${SETUP_ID}`;

const TYPED_NAME = "The Gilded Tavern";
const TYPED_DESCRIPTION = "Smoke and lute strings.";

/** The row the modal edits. */
const TAVERN: Setup = {
  id: SETUP_ID,
  character_id: CHARACTER_ID,
  name: "The Gilded Tavern",
  description: "A room above the kitchen.",
  archived_at: null,
  created_at: "2026-03-14T09:26:53.000000+00:00",
  updated_at: "2026-03-14T09:26:53.000000+00:00",
};

/** What the server answers the create with (a different name: never optimistic). */
const CREATED: Setup = {
  id: CREATED_ID,
  character_id: CHARACTER_ID,
  name: "The Gilded Tavern, as filed",
  description: TYPED_DESCRIPTION,
  archived_at: null,
  created_at: "2026-04-10T12:00:00.000000+00:00",
  updated_at: "2026-04-10T12:00:00.000000+00:00",
};

const EDITED_DESCRIPTION = "Two ships, no harbourmaster.";

/** What the server answers the save with. */
const SAVED: Setup = {
  ...TAVERN,
  name: "The Gilded Tavern, as filed",
  description: EDITED_DESCRIPTION,
  updated_at: "2026-04-11T08:30:00.000000+00:00",
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
function serverError(): Response {
  return jsonResponse(
    { error: { code: "internal_error", message: "ql-77 went wrong.", detail: {} } },
    500,
  );
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

/** Records every request in order and answers with `handler`'s response. */
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
/** The modal standalone, in `AppProviders` only — a setup has no route. */
function renderModal(setup: Setup | null) {
  const onClose = vi.fn<() => void>();
  const onSaved = vi.fn<(saved: Setup) => void>();
  const view = render(
    <AppProviders>
      <SetupModal characterId={CHARACTER_ID} setup={setup} onClose={onClose} onSaved={onSaved} />
    </AppProviders>,
  );
  return { onClose, onSaved, view };
}

// ---------------------------------------------------------------- queries
function dialog(): HTMLElement {
  return screen.getByRole("dialog");
}

function nameInput(): HTMLInputElement {
  const element = within(dialog()).getByRole("textbox", { name: NAME_LABEL });
  if (!(element instanceof HTMLInputElement)) throw new Error('the "Name" textbox is not an input');
  return element;
}

function descriptionInput(): HTMLTextAreaElement {
  const element = within(dialog()).getByRole("textbox", { name: DESCRIPTION_LABEL });
  if (!(element instanceof HTMLTextAreaElement)) {
    throw new Error('the "Description" textbox is not the stubbed editor');
  }
  return element;
}

function button(name: RegExp): HTMLElement {
  return within(dialog()).getByRole("button", { name });
}

function notificationsShown(): Element[] {
  return Array.from(document.querySelectorAll(NOTIFICATION));
}

async function typeInto(user: User, element: HTMLElement, text: string): Promise<void> {
  await user.clear(element);
  await user.type(element, text);
}

// ---------------------------------------------------------------------------
describe("create mode (setup is null)", () => {
  it("renders a New setup dialog with empty fields, Cancel and a disabled Create — DoD-5", async () => {
    stubBackend(() => jsonResponse(CREATED, 201));
    renderModal(null);
    const opened = await screen.findByRole("dialog", { name: NEW_TITLE });
    expect(within(opened).getByText("New setup")).toBeInTheDocument();
    expect(nameInput()).toHaveValue("");
    expect(descriptionInput()).toHaveValue("");
    expect(button(CANCEL_NAME)).toBeEnabled();
    expect(button(CREATE_NAME)).toBeDisabled();
  });

  it("typing a name enables Create and sends no request — DoD-5", async () => {
    const { mock } = stubBackend(() => jsonResponse(CREATED, 201));
    const user = newUser();
    renderModal(null);
    await screen.findByRole("dialog", { name: NEW_TITLE });
    await user.type(nameInput(), TYPED_NAME);
    expect(nameInput()).toHaveValue(TYPED_NAME);
    expect(button(CREATE_NAME)).toBeEnabled();
    expect(mock).not.toHaveBeenCalled();
  });

  it("POSTs the typed name and description once and calls onSaved with the server's row, notifying nothing — DoD-6", async () => {
    const { calls } = stubBackend(() => jsonResponse(CREATED, 201));
    const user = newUser();
    const { onSaved } = renderModal(null);
    await screen.findByRole("dialog", { name: NEW_TITLE });
    await user.type(nameInput(), TYPED_NAME);
    await user.type(descriptionInput(), TYPED_DESCRIPTION);
    await user.click(button(CREATE_NAME));
    await flush();

    const posts = matching(calls, "POST", COLLECTION_PATH);
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({ name: TYPED_NAME, description: TYPED_DESCRIPTION });
    expect(calls).toHaveLength(1);
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onSaved).toHaveBeenCalledWith(CREATED);
    expect(notificationsShown()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("edit mode (a setup to edit)", () => {
  it("renders an Edit setup dialog holding the setup's values with Save disabled — DoD-7", async () => {
    stubBackend(() => jsonResponse(SAVED, 200));
    renderModal(TAVERN);
    const opened = await screen.findByRole("dialog", { name: EDIT_TITLE });
    expect(within(opened).getByText("Edit setup")).toBeInTheDocument();
    expect(nameInput()).toHaveValue(TAVERN.name);
    expect(descriptionInput()).toHaveValue(TAVERN.description);
    expect(button(SAVE_NAME)).toBeDisabled();
  });

  it("changing the description enables Save, which PATCHes both fields and calls onSaved with the response — DoD-7", async () => {
    const { calls } = stubBackend(() => jsonResponse(SAVED, 200));
    const user = newUser();
    const { onSaved } = renderModal(TAVERN);
    await screen.findByRole("dialog", { name: EDIT_TITLE });
    await typeInto(user, descriptionInput(), EDITED_DESCRIPTION);
    expect(descriptionInput()).toHaveValue(EDITED_DESCRIPTION);
    expect(button(SAVE_NAME)).toBeEnabled();

    await user.click(button(SAVE_NAME));
    await flush();

    const patches = matching(calls, "PATCH", ITEM_PATH);
    expect(patches).toHaveLength(1);
    expect(patches[0].body).toEqual({ name: TAVERN.name, description: EDITED_DESCRIPTION });
    expect(calls).toHaveLength(1);
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onSaved).toHaveBeenCalledWith(SAVED);
    expect(notificationsShown()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("a failed submit", () => {
  it("shows the create sentence in the dialog, keeps it open with the typed values and notifies nothing — DoD-8", async () => {
    stubBackend(() => serverError());
    const user = newUser();
    const { onSaved } = renderModal(null);
    await screen.findByRole("dialog", { name: NEW_TITLE });
    await user.type(nameInput(), TYPED_NAME);
    await user.type(descriptionInput(), TYPED_DESCRIPTION);
    await user.click(button(CREATE_NAME));
    await flush();

    expect(within(dialog()).getByText(CREATE_FAILED_TEXT)).toBeInTheDocument();
    expect(nameInput()).toHaveValue(TYPED_NAME);
    expect(descriptionInput()).toHaveValue(TYPED_DESCRIPTION);
    expect(onSaved).not.toHaveBeenCalled();
    expect(notificationsShown()).toEqual([]);
  });

  it("shows the save sentence in the dialog, keeps it open with the edited values and notifies nothing — DoD-8", async () => {
    stubBackend(() => serverError());
    const user = newUser();
    const { onSaved } = renderModal(TAVERN);
    await screen.findByRole("dialog", { name: EDIT_TITLE });
    await typeInto(user, descriptionInput(), EDITED_DESCRIPTION);
    await user.click(button(SAVE_NAME));
    await flush();

    expect(within(dialog()).getByText(SAVE_FAILED_TEXT)).toBeInTheDocument();
    expect(nameInput()).toHaveValue(TAVERN.name);
    expect(descriptionInput()).toHaveValue(EDITED_DESCRIPTION);
    expect(onSaved).not.toHaveBeenCalled();
    expect(notificationsShown()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("Cancel and the in-flight submit", () => {
  it("Cancel calls onClose and sends no request — DoD-9", async () => {
    const { mock } = stubBackend(() => jsonResponse(CREATED, 201));
    const user = newUser();
    const { onClose, onSaved } = renderModal(null);
    await screen.findByRole("dialog", { name: NEW_TITLE });
    await user.type(nameInput(), TYPED_NAME);
    await user.click(button(CANCEL_NAME));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(mock).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("disables the submit and makes the Description editor read-only while the submit is in flight — DoD-9", async () => {
    const pending = deferred<Response>();
    stubBackend(() => pending.promise);
    const user = newUser();
    const { onSaved } = renderModal(null);
    await screen.findByRole("dialog", { name: NEW_TITLE });
    await user.type(nameInput(), TYPED_NAME);
    await user.type(descriptionInput(), TYPED_DESCRIPTION);
    await user.click(button(CREATE_NAME));
    await flush();

    expect(button(CREATE_NAME)).toBeDisabled();
    expect(descriptionInput()).toHaveAttribute("readonly");
    expect(onSaved).not.toHaveBeenCalled();

    pending.resolve(jsonResponse(CREATED, 201));
    await flush();
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(descriptionInput()).not.toHaveAttribute("readonly");
  });
});
