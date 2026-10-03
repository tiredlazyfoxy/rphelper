// Feature 013, step 005 — the current zone's messages, each editable in place (DoD-1..DoD-7).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done plus
// context.md's D5, D10, "Never optimistic" and the UI strings table:
//   - a list labelled "Zone messages", one listitem per zone row in the given order, each
//     with its author label ("You" / "Assistant" / "Tool") and an "Edit message" control;
//     no list at all when the zone is empty;
//   - bodies painted: wholly-parenthesised text is the out-of-character card
//     (data-paren="ooc"), a fragment is a chip (data-paren="fragment");
//   - "Edit message" swaps the body for a textbox "Edit message text" holding the row's text;
//     blur commits: blank / unchanged -> no request, editor closes; otherwise exactly
//     PATCH /api/messages/<id> {"text": ...}, the response replaces that row, no GET;
//   - a failed PATCH notifies, re-reads GET /api/sessions/<id>/zone, and keeps the editor
//     open with the typed text while the row is still served; a row gone from the re-read
//     takes its item and editor with it.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { runInAction } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ZoneList } from "../../src/app/ZoneList";
import type { Message, MessageRole } from "../../src/app/streamApi";
import { StreamState } from "../../src/app/streamState";
import { ApiError } from "../../src/shared/apiError";
import { AppProviders } from "../../src/shared/AppProviders";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "7250000000000000042";
const ZONE_PATH = `/api/sessions/${SESSION_ID}/zone`;

const USER_ID = "7250000000000000101";
const ASSISTANT_ID = "7250000000000000102";
const TOOL_ID = "7250000000000000103";
const ASSISTANT_PATH = `/api/messages/${ASSISTANT_ID}`;

const LIST_NAME = "Zone messages";
const EDIT_NAME = "Edit message";
const EDITOR_NAME = "Edit message text";

const STAMP = "2026-05-10T09:00:00.000000+00:00";
const LATER = "2026-05-10T09:05:00.000000+00:00";

/** A zone row with all eight keys: `kind` and `settled_at` null. */
function zoneRow(id: string, role: MessageRole, text: string, updatedAt = STAMP): Message {
  return {
    id,
    session_id: SESSION_ID,
    role,
    kind: null,
    text,
    settled_at: null,
    created_at: STAMP,
    updated_at: updatedAt,
  };
}

function threeRows(): Message[] {
  return [
    zoneRow(USER_ID, "user", "Hi"),
    zoneRow(ASSISTANT_ID, "assistant", "Hello there"),
    zoneRow(TOOL_ID, "tool", "lookup"),
  ];
}

function seeded(zone: Message[]): StreamState {
  const state = new StreamState(SESSION_ID);
  runInAction(() => {
    state.zone = zone;
    state.status = "ready";
  });
  return state;
}

beforeEach(() => {
  notifyFailureSpy.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- harness
function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: `refused: ${code}`, detail: {} } }, status);
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

type Seen = { line: string; body: string | null };

/**
 * Stubs fetch by exact method + pathname. Every request is logged as "METHOD /path" with its
 * raw body. `route` answers a request or returns undefined for "unexpected" (500).
 */
function stubFetch(route: (method: string, pathname: string) => Response | undefined): Seen[] {
  const log: Seen[] = [];
  const impl: FetchFn = async (input, init) => {
    const method = requestMethod(input, init);
    const pathname = requestUrl(input).pathname;
    log.push({ line: `${method} ${pathname}`, body: typeof init?.body === "string" ? init.body : null });
    const answer = route(method, pathname);
    if (answer !== undefined) return answer;
    return envelope("unexpected", 500);
  };
  vi.stubGlobal("fetch", vi.fn(impl));
  return log;
}

function lines(log: Seen[]): string[] {
  return log.map((seen) => seen.line);
}

function renderZone(state: StreamState): void {
  render(
    <AppProviders>
      <ZoneList state={state} />
    </AppProviders>,
  );
}

function zoneList(): HTMLElement {
  return screen.getByRole("list", { name: LIST_NAME });
}

function zoneItems(): HTMLElement[] {
  return within(zoneList()).getAllByRole("listitem");
}

function item(index: number): HTMLElement {
  return zoneItems()[index] as HTMLElement;
}

function editor(): HTMLElement {
  return screen.getByRole("textbox", { name: EDITOR_NAME });
}

function newUser(): ReturnType<typeof userEvent.setup> {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

async function settle(): Promise<void> {
  await act(async () => {
    for (let round = 0; round < 6; round += 1) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  });
}

async function openAssistantEditor(user: ReturnType<typeof userEvent.setup>): Promise<HTMLElement> {
  await user.click(within(item(1)).getByRole("button", { name: EDIT_NAME }));
  return editor();
}

// ---------------------------------------------------------------- tests
describe("ZoneList — rows, labels, edit controls", () => {
  it('renders three items in order labelled "You", "Assistant", "Tool", each with "Edit message" — DoD-1', () => {
    renderZone(seeded(threeRows()));

    const items = zoneItems();
    expect(items).toHaveLength(3);

    expect(within(items[0] as HTMLElement).getByText("You")).toBeInTheDocument();
    expect(within(items[1] as HTMLElement).getByText("Assistant")).toBeInTheDocument();
    expect(within(items[2] as HTMLElement).getByText("Tool")).toBeInTheDocument();

    expect(items[0]?.textContent).toContain("Hi");
    expect(items[1]?.textContent).toContain("Hello there");
    expect(items[2]?.textContent).toContain("lookup");

    for (const listItem of items) {
      expect(within(listItem).getAllByRole("button", { name: EDIT_NAME })).toHaveLength(1);
    }
  });

  it('with an empty zone renders no "Zone messages" list — DoD-1', () => {
    renderZone(seeded([]));

    expect(screen.queryByRole("list", { name: LIST_NAME })).toBeNull();
    expect(screen.queryAllByRole("listitem")).toEqual([]);
    expect(screen.queryByRole("button", { name: EDIT_NAME })).toBeNull();
  });
});

describe("ZoneList — painted bodies (D5)", () => {
  it('a wholly-parenthesised zone row renders the out-of-character card — DoD-2', () => {
    renderZone(seeded([zoneRow(USER_ID, "user", "((just a note))")]));

    const card = item(0).querySelector('[data-paren="ooc"]');
    expect(card).not.toBeNull();
    expect(card?.textContent).toContain("((just a note))");
  });

  it('a zone row "Text ((hint)) more" renders exactly one fragment chip "((hint))" — DoD-2', () => {
    renderZone(seeded([zoneRow(USER_ID, "user", "Text ((hint)) more")]));

    const chips = item(0).querySelectorAll('[data-paren="fragment"]');
    expect(chips).toHaveLength(1);
    expect(chips[0]?.textContent).toBe("((hint))");
    expect(item(0).querySelector('[data-paren="ooc"]')).toBeNull();
  });
});

describe("ZoneList — in-place edit (D10)", () => {
  it('editing the assistant row PATCHes exactly /api/messages/<id> with {"text":"Hello, friend"}, then closes — DoD-3', async () => {
    const log = stubFetch((method, pathname) =>
      method === "PATCH" && pathname === ASSISTANT_PATH
        ? jsonResponse(zoneRow(ASSISTANT_ID, "assistant", "Hello, friend", LATER), 200)
        : undefined,
    );
    const user = newUser();
    renderZone(seeded(threeRows()));

    const textbox = await openAssistantEditor(user);
    expect(textbox).toHaveValue("Hello there");

    fireEvent.change(textbox, { target: { value: "Hello, friend" } });
    fireEvent.blur(textbox);

    await waitFor(() => {
      expect(screen.queryByRole("textbox", { name: EDITOR_NAME })).toBeNull();
    });
    await settle();

    expect(lines(log)).toEqual([`PATCH ${ASSISTANT_PATH}`]);
    expect(log[0]?.body).toBe('{"text":"Hello, friend"}');
    expect(lines(log).some((line) => line.startsWith("GET "))).toBe(false);

    expect(item(1).textContent).toContain("Hello, friend");
    expect(item(1).textContent).not.toContain("Hello there");
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("after a successful PATCH the item shows the text the server served — DoD-3", async () => {
    const log = stubFetch((method, pathname) =>
      method === "PATCH" && pathname === ASSISTANT_PATH
        ? jsonResponse(zoneRow(ASSISTANT_ID, "assistant", "Served friend text", LATER), 200)
        : undefined,
    );
    const user = newUser();
    renderZone(seeded(threeRows()));

    const textbox = await openAssistantEditor(user);
    fireEvent.change(textbox, { target: { value: "Hello, friend" } });
    fireEvent.blur(textbox);

    await waitFor(() => {
      expect(item(1).textContent).toContain("Served friend text");
    });
    await settle();

    expect(screen.queryByRole("textbox", { name: EDITOR_NAME })).toBeNull();
    expect(lines(log)).toEqual([`PATCH ${ASSISTANT_PATH}`]);
  });

  it("blurring with the text unchanged makes no request and shows the original text — DoD-4", async () => {
    const log = stubFetch(() => undefined);
    const user = newUser();
    renderZone(seeded(threeRows()));

    const textbox = await openAssistantEditor(user);
    fireEvent.blur(textbox);

    await waitFor(() => {
      expect(screen.queryByRole("textbox", { name: EDITOR_NAME })).toBeNull();
    });
    await settle();

    expect(log).toEqual([]);
    expect(item(1).textContent).toContain("Hello there");
  });

  it("blurring with only whitespace makes no request and shows the original text — DoD-4", async () => {
    const log = stubFetch(() => undefined);
    const user = newUser();
    renderZone(seeded(threeRows()));

    const textbox = await openAssistantEditor(user);
    fireEvent.change(textbox, { target: { value: "   \n\t " } });
    fireEvent.blur(textbox);

    await waitFor(() => {
      expect(screen.queryByRole("textbox", { name: EDITOR_NAME })).toBeNull();
    });
    await settle();

    expect(log).toEqual([]);
    expect(item(1).textContent).toContain("Hello there");
  });

  it("a 409 message_not_editable notifies, re-reads the zone, and keeps the editor open with the typed text — DoD-5", async () => {
    const log = stubFetch((method, pathname) => {
      if (method === "PATCH" && pathname === ASSISTANT_PATH) return envelope("message_not_editable", 409);
      if (method === "GET" && pathname === ZONE_PATH) return jsonResponse({ messages: threeRows() }, 200);
      return undefined;
    });
    const user = newUser();
    renderZone(seeded(threeRows()));

    const textbox = await openAssistantEditor(user);
    fireEvent.change(textbox, { target: { value: "Hello, friend" } });
    fireEvent.blur(textbox);

    await waitFor(() => {
      expect(lines(log)).toContain(`GET ${ZONE_PATH}`);
    });
    await settle();

    const seen = lines(log);
    expect(seen).toContain(`PATCH ${ASSISTANT_PATH}`);
    expect(seen.indexOf(`PATCH ${ASSISTANT_PATH}`)).toBeLessThan(seen.indexOf(`GET ${ZONE_PATH}`));

    expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
    const notified = notifyFailureSpy.mock.calls[0]?.[0];
    expect(notified).toBeInstanceOf(ApiError);
    expect((notified as ApiError).code).toBe("message_not_editable");

    expect(screen.getByRole("textbox", { name: EDITOR_NAME })).toHaveValue("Hello, friend");
    expect(zoneItems()).toHaveLength(3);
  });

  it("when the zone re-read after a failed PATCH no longer holds the row, its item and editor are gone — DoD-6", async () => {
    const remaining = [zoneRow(USER_ID, "user", "Hi"), zoneRow(TOOL_ID, "tool", "lookup")];
    const log = stubFetch((method, pathname) => {
      if (method === "PATCH" && pathname === ASSISTANT_PATH) return envelope("message_not_editable", 409);
      if (method === "GET" && pathname === ZONE_PATH) return jsonResponse({ messages: remaining }, 200);
      return undefined;
    });
    const user = newUser();
    renderZone(seeded(threeRows()));

    const textbox = await openAssistantEditor(user);
    fireEvent.change(textbox, { target: { value: "Hello, friend" } });
    fireEvent.blur(textbox);

    await waitFor(() => {
      expect(zoneItems()).toHaveLength(2);
    });
    await settle();

    expect(lines(log)).toContain(`GET ${ZONE_PATH}`);
    expect(screen.queryByRole("textbox", { name: EDITOR_NAME })).toBeNull();
    expect(zoneList().textContent).not.toContain("Hello there");
    expect(within(zoneList()).queryByText("Assistant")).toBeNull();
    expect(item(0).textContent).toContain("Hi");
    expect(item(1).textContent).toContain("lookup");
  });

  it("editing one row leaves every other row's text and the row order unchanged — DoD-7", async () => {
    stubFetch((method, pathname) =>
      method === "PATCH" && pathname === ASSISTANT_PATH
        ? jsonResponse(zoneRow(ASSISTANT_ID, "assistant", "Hello, friend", LATER), 200)
        : undefined,
    );
    const user = newUser();
    const state = seeded(threeRows());
    renderZone(state);

    const textbox = await openAssistantEditor(user);
    fireEvent.change(textbox, { target: { value: "Hello, friend" } });
    fireEvent.blur(textbox);

    await waitFor(() => {
      expect(item(1).textContent).toContain("Hello, friend");
    });
    await settle();

    const items = zoneItems();
    expect(items).toHaveLength(3);
    expect(within(items[0] as HTMLElement).getByText("You")).toBeInTheDocument();
    expect(within(items[1] as HTMLElement).getByText("Assistant")).toBeInTheDocument();
    expect(within(items[2] as HTMLElement).getByText("Tool")).toBeInTheDocument();
    expect(items[0]?.textContent).toContain("Hi");
    expect(items[2]?.textContent).toContain("lookup");

    expect(state.zone.map((row) => row.id)).toEqual([USER_ID, ASSISTANT_ID, TOOL_ID]);
    expect(state.zone[0]?.text).toBe("Hi");
    expect(state.zone[2]?.text).toBe("lookup");
  });
});
