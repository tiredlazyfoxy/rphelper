// Feature 033, step 003 — the inline setup create form on its own (033 step 003 DoD-2..DoD-7;
// the section-level clauses, DoD-1 and DoD-8 live in SetupsSection.test.tsx; DoD-9 is
// [manual/live] and carries no test).
//
// Expected behaviour comes from 033's step file 003.setups-inline-create.md (Interface intent
// and Definition of done), 003.context.md, context.md (D7 and the inline-draft vocabulary:
// Save = IconDeviceFloppy, Cancel = IconX, Cancel sends no request, both disabled while the
// save is in flight, failures inline) and the frozen `## Skeleton` record:
// `SetupCreateForm({ characterId, onCreated, onCancel })`; a fresh draft per mount; text input
// "Name"; MarkdownEditor "Description"; icon buttons "Save setup" / "Cancel new setup"; the
// draft's single error rendered inside the form; no `role="dialog"`.
//
// Recognition conventions (for the verifier):
// - `src/shared/MarkdownEditor` is the sanctioned labelled-`<textarea>` stub (same shape as
//   SetupsSection.test.tsx), so "Description" is a plain textbox in jsdom.
// - `fetch` is stubbed per test and every request recorded, so "no request" is `calls` empty.
// - The create failure sentence "Could not create the setup." is 010's (SetupsSection DoD-6).
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ChangeEvent } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SetupCreateForm } from "../../src/app/SetupCreateForm";
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
type Handler = (request: Seen) => Response | Promise<Response>;

// ---------------------------------------------------------------- the spec's names
const NAME_LABEL = /^name$/i;
const DESCRIPTION_LABEL = /^description$/i;
const SAVE_SETUP = /^save setup$/i;
const CANCEL_NEW_SETUP = /^cancel new setup$/i;
const CREATE_FAILED_TEXT = "Could not create the setup.";
const NOTIFICATION = ".mantine-Notification-root";

// ---------------------------------------------------------------- fixtures
const CHARACTER_ID = "7250000000000000011";
const COLLECTION_PATH = `/api/characters/${CHARACTER_ID}/setups`;
const CREATED_ID = "9007199254740993"; // 2^53 + 1
const NEWEST_STAMP = "2026-06-01T12:00:00.000000+00:00";

const TYPED_NAME = "Night market";
const TYPED_DESCRIPTION = "Stalls that close when you look at them.";

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

function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: "ql-77 went wrong.", detail: {} } }, status);
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
  const raw = init?.body;
  if (raw === undefined || raw === null) return undefined;
  return JSON.parse(String(raw)) as unknown;
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

/** The created row the server answers for a create: the sent name/description, a new id. */
function createdFrom(body: unknown): Setup {
  const sent = (body ?? {}) as { name?: string; description?: string };
  return {
    id: CREATED_ID,
    character_id: CHARACTER_ID,
    name: sent.name ?? "",
    description: sent.description ?? "",
    archived_at: null,
    created_at: NEWEST_STAMP,
    updated_at: NEWEST_STAMP,
  };
}

/** POST to the character's setups collection answers 201 with the created row. */
function serveCreate() {
  return stubBackend((request) => {
    if (request.method === "POST" && request.path === COLLECTION_PATH) {
      return jsonResponse(createdFrom(request.body), 201);
    }
    return envelope("setup_not_found", 404);
  });
}

type Held = { promise: Promise<Response>; resolve: (value: Response) => void };

function held(): Held {
  let resolve: (value: Response) => void = () => undefined;
  const promise = new Promise<Response>((ok) => {
    resolve = ok;
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

// ---------------------------------------------------------------- render + queries
function newUser() {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

function renderForm() {
  const onCreated = vi.fn<(created: Setup) => void>();
  const onCancel = vi.fn<() => void>();
  const view = render(
    <AppProviders>
      <SetupCreateForm characterId={CHARACTER_ID} onCreated={onCreated} onCancel={onCancel} />
    </AppProviders>,
  );
  return { view, onCreated, onCancel };
}

function nameInput(): HTMLInputElement {
  return screen.getByRole("textbox", { name: NAME_LABEL }) as HTMLInputElement;
}

function descriptionInput(): HTMLTextAreaElement {
  return screen.getByRole("textbox", { name: DESCRIPTION_LABEL }) as HTMLTextAreaElement;
}

function saveButton(): HTMLElement {
  return screen.getByRole("button", { name: SAVE_SETUP });
}

function cancelButton(): HTMLElement {
  return screen.getByRole("button", { name: CANCEL_NEW_SETUP });
}

/** Whether a button shows the given text as its own visible content (a labelled button). */
function showsText(element: HTMLElement, text: string): boolean {
  return (element.textContent ?? "").includes(text);
}

// ===========================================================================
describe("the inline form's fields and buttons (D7)", () => {
  it("renders an empty Name, an empty Description and icon-only Save setup / Cancel new setup buttons, with no dialog — 033 step 003 DoD-2", () => {
    const { calls } = serveCreate();
    renderForm();

    expect(nameInput()).toHaveValue("");
    expect(descriptionInput()).toHaveValue("");
    expect(saveButton()).toBeInTheDocument();
    expect(cancelButton()).toBeInTheDocument();
    expect(showsText(saveButton(), "Save setup")).toBe(false);
    expect(showsText(cancelButton(), "Cancel new setup")).toBe(false);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(calls).toEqual([]);
  });

  it("focuses Name on mount — 033 step 003 DoD-2", async () => {
    serveCreate();
    renderForm();

    await waitFor(() => {
      expect(document.activeElement).toBe(nameInput());
    });
  });
});

describe("Cancel new setup (D7)", () => {
  it.each<[string, string, string]>([
    ["untouched", "", ""],
    ["typed", TYPED_NAME, TYPED_DESCRIPTION],
  ])(
    "on a %s form calls onCancel once and sends no request — 033 step 003 DoD-3",
    async (_label, name, description) => {
      const { calls } = serveCreate();
      const { onCancel, onCreated } = renderForm();
      const user = newUser();
      if (name !== "") await user.type(nameInput(), name);
      if (description !== "") await user.type(descriptionInput(), description);

      await user.click(cancelButton());
      await flush();

      expect(onCancel).toHaveBeenCalledTimes(1);
      expect(onCreated).not.toHaveBeenCalled();
      expect(calls).toEqual([]);
    },
  );
});

describe("Save setup (UC-020, US-023, D7)", () => {
  it("sends exactly one create for this character with the typed name and description and hands the server's row to onCreated — 033 step 003 DoD-4", async () => {
    const { calls } = serveCreate();
    const { onCreated, onCancel } = renderForm();
    const user = newUser();

    await user.type(nameInput(), TYPED_NAME);
    await user.type(descriptionInput(), TYPED_DESCRIPTION);
    await user.click(saveButton());
    await flush();

    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].path).toBe(COLLECTION_PATH);
    expect(calls[0].body).toMatchObject({ name: TYPED_NAME, description: TYPED_DESCRIPTION });
    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledTimes(1);
    });
    expect(onCreated).toHaveBeenCalledWith(
      createdFrom({ name: TYPED_NAME, description: TYPED_DESCRIPTION }),
    );
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("a name with no description is enough: one create carrying the name — 033 step 003 DoD-4", async () => {
    const { calls } = serveCreate();
    const { onCreated } = renderForm();
    const user = newUser();

    await user.type(nameInput(), TYPED_NAME);
    await user.click(saveButton());
    await flush();

    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].path).toBe(COLLECTION_PATH);
    expect(calls[0].body).toMatchObject({ name: TYPED_NAME });
    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledTimes(1);
    });
    expect(onCreated.mock.calls[0][0].id).toBe(CREATED_ID);
  });
});

describe("a failed save (D7)", () => {
  it("disables Save and Cancel while in flight, then shows the failure inside the form with the typed values kept and no onCreated — 033 step 003 DoD-5", async () => {
    const response = held();
    const { calls } = stubBackend(() => response.promise);
    const { view, onCreated, onCancel } = renderForm();
    const user = newUser();
    await user.type(nameInput(), TYPED_NAME);
    await user.type(descriptionInput(), TYPED_DESCRIPTION);

    await user.click(saveButton());
    await waitFor(() => {
      expect(calls).toHaveLength(1);
    });
    await waitFor(() => {
      expect(saveButton()).toBeDisabled();
    });
    expect(cancelButton()).toBeDisabled();

    await act(async () => {
      response.resolve(serverError());
    });
    await waitFor(() => {
      expect(screen.queryByText(CREATE_FAILED_TEXT)).not.toBeNull();
    });
    await flush();

    expect(view.container.contains(screen.getByText(CREATE_FAILED_TEXT))).toBe(true);
    expect(screen.getAllByText(CREATE_FAILED_TEXT)).toHaveLength(1);
    expect(nameInput()).toHaveValue(TYPED_NAME);
    expect(descriptionInput()).toHaveValue(TYPED_DESCRIPTION);
    expect(onCreated).not.toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
    expect(calls).toHaveLength(1);
    expect(document.querySelector(NOTIFICATION)).toBeNull();
    expect(saveButton()).toBeEnabled();
    expect(cancelButton()).toBeEnabled();
  });
});

describe("Save follows the draft's own submit guard (D7)", () => {
  it("is disabled on an untouched form and with a description but no name — 033 step 003 DoD-6", async () => {
    const { calls } = serveCreate();
    renderForm();
    const user = newUser();

    expect(saveButton()).toBeDisabled();
    await user.type(descriptionInput(), TYPED_DESCRIPTION);
    expect(saveButton()).toBeDisabled();

    await user.click(saveButton());
    await flush();
    expect(calls).toEqual([]);
  });

  it("is disabled for a whitespace-only name and enabled once the name has text — 033 step 003 DoD-6", async () => {
    const { calls } = serveCreate();
    renderForm();
    const user = newUser();

    await user.type(nameInput(), "   ");
    expect(saveButton()).toBeDisabled();
    await user.click(saveButton());
    await flush();
    expect(calls).toEqual([]);

    await user.clear(nameInput());
    await user.type(nameInput(), TYPED_NAME);
    expect(saveButton()).toBeEnabled();
  });
});

describe("a fresh draft per mount (forms-and-lists.md draft lifetime)", () => {
  it("a new mount after one with typed values starts from an empty Name and Description — 033 step 003 DoD-7", async () => {
    serveCreate();
    const first = renderForm();
    const user = newUser();
    await user.type(nameInput(), TYPED_NAME);
    await user.type(descriptionInput(), TYPED_DESCRIPTION);
    first.view.unmount();

    renderForm();
    expect(nameInput()).toHaveValue("");
    expect(descriptionInput()).toHaveValue("");
    expect(saveButton()).toBeDisabled();
  });
});
