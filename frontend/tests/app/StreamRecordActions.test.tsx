// Feature 014, step 005 — settled-entry actions: reveal, in-place edit, copy on turns
// (DoD-1, DoD-2, DoD-4..DoD-10; DoD-3 amends tests/app/StreamRecord.test.tsx).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done plus
// context.md's D6, D7, D10, the UI strings table and "Test conventions", and 005.context.md:
//   - each entry's header holds one actions group, carrying data-revealed "true" / "false";
//     revealed while hovered or holding focus within; always rendered — hidden controls stay
//     in the document, not disabled, reachable by role and name;
//   - "Edit entry" on every kind, absent while that entry's editor is open;
//   - "Copy as plain text" on turn entries only — absent (not disabled) on partner / decision;
//     pressing it writes the stored text as plain text to the clipboard, no request, no notice;
//   - "Edit entry" swaps the body for a focused textbox "Edit entry text" holding the stored
//     text; blur commits: blank / unchanged -> no request, editor closes; otherwise exactly
//     PATCH /api/messages/<id> {"text": ...}; success -> editor closes and the served row
//     renders by its kind; 409 -> notifyFailure, GET …/entries, editor stays with the typed text.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { runInAction } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StreamRecord } from "../../src/app/StreamRecord";
import type { Message, MessageKind } from "../../src/app/streamApi";
import { StreamState } from "../../src/app/streamState";
import { ApiError } from "../../src/shared/apiError";
import { AppProviders } from "../../src/shared/AppProviders";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "7250000000000000042";
const ENTRIES_PATH = `/api/sessions/${SESSION_ID}/entries`;
const ZONE_PATH = `/api/sessions/${SESSION_ID}/zone`;

const PARTNER_ID = "7250000000000000201";
const TURN_ID = "7250000000000000202";
const DECISION_ID = "7250000000000000203";
const messagePath = (id: string): string => `/api/messages/${id}`;

const RECORD_NAME = "Settled record";
const EDIT_NAME = "Edit entry";
const EDITOR_NAME = "Edit entry text";
const COPY_NAME = "Copy as plain text";
const REOPEN_NAME = "Re-open last entry";

const STAMP = "2026-05-10T09:00:00.000000+00:00";
const LATER = "2026-05-10T09:05:00.000000+00:00";

/** A settled entry with all eight keys. */
function entry(id: string, kind: MessageKind, text: string): Message {
  return {
    id,
    session_id: SESSION_ID,
    role: kind === "partner" ? "user" : "assistant",
    kind,
    text,
    settled_at: STAMP,
    created_at: STAMP,
    updated_at: STAMP,
  };
}

/** The served row of a successful settled edit: same row, new text, later updated_at. */
function served(original: Message, text: string): Message {
  return { ...original, text, updated_at: LATER };
}

function threeEntries(): Message[] {
  return [entry(PARTNER_ID, "partner", "P1"), entry(TURN_ID, "turn", "T1"), entry(DECISION_ID, "decision", "((D1))")];
}

function seeded(entries: Message[], zone: Message[] = []): StreamState {
  const state = new StreamState(SESSION_ID);
  runInAction(() => {
    state.entries = entries;
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
 * Stubs fetch by exact method + pathname (PATCH /api/messages/<id>, GET …/entries, GET …/zone
 * as the route answers them). Every request is logged as "METHOD /path" with its raw body;
 * an unrouted request answers a 500 envelope.
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

/** PATCH /api/messages/<id> answers `row`; nothing else is routed. */
function stubPatch(row: Message): Seen[] {
  return stubFetch((method, pathname) =>
    method === "PATCH" && pathname === messagePath(row.id) ? jsonResponse(row, 200) : undefined,
  );
}

function lines(log: Seen[]): string[] {
  return log.map((seen) => seen.line);
}

function renderRecord(state: StreamState, signal?: AbortSignal): void {
  render(
    <AppProviders>
      <StreamRecord state={state} signal={signal} />
    </AppProviders>,
  );
}

function recordItems(): HTMLElement[] {
  return within(screen.getByRole("list", { name: RECORD_NAME })).getAllByRole("listitem");
}

function item(index: number): HTMLElement {
  return recordItems()[index] as HTMLElement;
}

/** The item's actions group — the only element in an item that carries data-revealed. */
function actionsGroup(listItem: HTMLElement): HTMLElement {
  const group = listItem.querySelector<HTMLElement>("[data-revealed]");
  expect(group).not.toBeNull();
  return group as HTMLElement;
}

function queryEditor(): HTMLElement | null {
  return screen.queryByRole("textbox", { name: EDITOR_NAME });
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

async function openEditor(user: ReturnType<typeof userEvent.setup>, index: number): Promise<HTMLElement> {
  await user.click(within(item(index)).getByRole("button", { name: EDIT_NAME }));
  return screen.getByRole("textbox", { name: EDITOR_NAME });
}

async function commit(textbox: HTMLElement, text: string): Promise<void> {
  fireEvent.change(textbox, { target: { value: text } });
  fireEvent.blur(textbox);
}

// ---------------------------------------------------------------- tests
describe("StreamRecord actions — which controls each kind offers", () => {
  it('each of the partner, turn and decision items holds exactly one "Edit entry" control — DoD-1', () => {
    renderRecord(seeded(threeEntries()));

    const items = recordItems();
    expect(items).toHaveLength(3);
    for (const listItem of items) {
      expect(within(listItem).getAllByRole("button", { name: EDIT_NAME })).toHaveLength(1);
    }
  });

  it('"Copy as plain text" is in the turn item and absent — not disabled — in the partner and decision items — DoD-2', () => {
    renderRecord(seeded(threeEntries()));

    const items = recordItems();
    expect(within(items[1] as HTMLElement).getAllByRole("button", { name: COPY_NAME })).toHaveLength(1);

    // queryByRole also finds disabled buttons, so null means the control is not rendered.
    for (const listItem of [items[0] as HTMLElement, items[2] as HTMLElement]) {
      expect(within(listItem).queryByRole("button", { name: COPY_NAME })).toBeNull();
      expect(within(listItem).queryByLabelText(COPY_NAME)).toBeNull();
    }
    expect(screen.getAllByRole("button", { name: COPY_NAME })).toHaveLength(1);
  });
});

describe("StreamRecord actions — in-place edit of a settled entry (D10)", () => {
  it('editing the turn to "T1 fixed" PATCHes exactly /api/messages/<id> {"text":"T1 fixed"}, closes, no GET, others unchanged — DoD-4', async () => {
    const entries = threeEntries();
    const turn = entries[1] as Message;
    const log = stubPatch(served(turn, "T1 fixed"));
    const user = newUser();
    renderRecord(seeded(entries));

    const textbox = await openEditor(user, 1);
    expect(textbox).toHaveValue("T1");
    await waitFor(() => {
      expect(textbox).toHaveFocus();
    });
    expect(within(item(1)).queryByRole("button", { name: EDIT_NAME })).toBeNull();

    await commit(textbox, "T1 fixed");

    await waitFor(() => {
      expect(queryEditor()).toBeNull();
    });
    await settle();

    expect(lines(log)).toEqual([`PATCH ${messagePath(TURN_ID)}`]);
    expect(log[0]?.body).toBe('{"text":"T1 fixed"}');
    expect(lines(log).some((line) => line.startsWith("GET "))).toBe(false);

    expect(item(1).textContent).toContain("T1 fixed");
    expect(item(0).textContent).toContain("P1");
    expect(item(0).textContent).not.toContain("fixed");
    expect(item(2).textContent).toContain("((D1))");
    expect(item(2).textContent).not.toContain("fixed");
    expect(within(item(1)).getAllByRole("button", { name: EDIT_NAME })).toHaveLength(1);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("after a successful PATCH the turn item shows the text the server served — DoD-4", async () => {
    const entries = threeEntries();
    const turn = entries[1] as Message;
    const log = stubPatch(served(turn, "Served turn text"));
    const user = newUser();
    renderRecord(seeded(entries));

    const textbox = await openEditor(user, 1);
    await commit(textbox, "T1 fixed");

    await waitFor(() => {
      expect(item(1).textContent).toContain("Served turn text");
    });
    await settle();

    expect(queryEditor()).toBeNull();
    expect(lines(log)).toEqual([`PATCH ${messagePath(TURN_ID)}`]);
  });

  it('editing the partner to "P1 fixed" PATCHes it and renders the served text inside a blockquote — DoD-5', async () => {
    const entries = threeEntries();
    const partner = entries[0] as Message;
    const log = stubPatch(served(partner, "P1 fixed"));
    const user = newUser();
    renderRecord(seeded(entries));

    const textbox = await openEditor(user, 0);
    expect(textbox).toHaveValue("P1");
    await commit(textbox, "P1 fixed");

    await waitFor(() => {
      expect(queryEditor()).toBeNull();
    });
    await settle();

    expect(lines(log)).toEqual([`PATCH ${messagePath(PARTNER_ID)}`]);
    expect(log[0]?.body).toBe('{"text":"P1 fixed"}');

    const body = within(item(0)).getByText("P1 fixed");
    expect(body.closest("blockquote")).not.toBeNull();
  });

  it('editing the decision to "plain words" renders the served decision row as the out-of-character card — DoD-5', async () => {
    const entries = threeEntries();
    const decision = entries[2] as Message;
    const log = stubPatch(served(decision, "plain words"));
    const user = newUser();
    renderRecord(seeded(entries));

    const textbox = await openEditor(user, 2);
    expect(textbox).toHaveValue("((D1))");
    await commit(textbox, "plain words");

    await waitFor(() => {
      expect(queryEditor()).toBeNull();
    });
    await settle();

    expect(lines(log)).toEqual([`PATCH ${messagePath(DECISION_ID)}`]);
    expect(log[0]?.body).toBe('{"text":"plain words"}');

    const card = item(2).querySelector('[data-paren="ooc"]');
    expect(card).not.toBeNull();
    expect(card?.textContent).toContain("plain words");
  });

  it("blurring with the text unchanged makes no request, closes the editor and shows the stored text — DoD-6", async () => {
    const log = stubFetch(() => undefined);
    const user = newUser();
    renderRecord(seeded(threeEntries()));

    const textbox = await openEditor(user, 1);
    fireEvent.blur(textbox);

    await waitFor(() => {
      expect(queryEditor()).toBeNull();
    });
    await settle();

    expect(log).toEqual([]);
    expect(item(1).textContent).toContain("T1");
  });

  it("blurring with only whitespace makes no request, closes the editor and shows the stored text — DoD-6", async () => {
    const log = stubFetch(() => undefined);
    const user = newUser();
    renderRecord(seeded(threeEntries()));

    const textbox = await openEditor(user, 1);
    await commit(textbox, "   \n\t ");

    await waitFor(() => {
      expect(queryEditor()).toBeNull();
    });
    await settle();

    expect(log).toEqual([]);
    expect(item(1).textContent).toContain("T1");
  });

  it("a 409 message_not_editable notifies with that code, re-reads the entries, and keeps the editor open with the typed text — DoD-7", async () => {
    const entries = threeEntries();
    const log = stubFetch((method, pathname) => {
      if (method === "PATCH" && pathname === messagePath(TURN_ID)) return envelope("message_not_editable", 409);
      if (method === "GET" && pathname === ENTRIES_PATH) return jsonResponse({ entries: threeEntries() }, 200);
      if (method === "GET" && pathname === ZONE_PATH) return jsonResponse({ messages: [] }, 200);
      return undefined;
    });
    const user = newUser();
    renderRecord(seeded(entries));

    const textbox = await openEditor(user, 1);
    await commit(textbox, "T1 fixed");

    await waitFor(() => {
      expect(lines(log)).toContain(`GET ${ENTRIES_PATH}`);
    });
    await settle();

    const seen = lines(log);
    expect(seen).toContain(`PATCH ${messagePath(TURN_ID)}`);
    expect(seen.indexOf(`PATCH ${messagePath(TURN_ID)}`)).toBeLessThan(seen.indexOf(`GET ${ENTRIES_PATH}`));

    expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
    const notified = notifyFailureSpy.mock.calls[0]?.[0];
    expect(notified).toBeInstanceOf(ApiError);
    expect((notified as ApiError).code).toBe("message_not_editable");

    expect(screen.getByRole("textbox", { name: EDITOR_NAME })).toHaveValue("T1 fixed");
    expect(recordItems()).toHaveLength(3);
  });
});

describe("StreamRecord actions — copy a turn as plain text (D7, D9)", () => {
  const COPY_SOURCE = "# Scene\n\n*She smiles* and **waits**.";
  const COPY_PLAIN = "Scene\n\nShe smiles and waits.";

  // navigator.clipboard is installed per test and restored afterwards (tests/setup.ts not touched).
  let clipboardDescriptor: PropertyDescriptor | undefined;

  beforeEach(() => {
    clipboardDescriptor = Object.getOwnPropertyDescriptor(navigator, "clipboard");
  });

  afterEach(() => {
    if (clipboardDescriptor !== undefined) {
      Object.defineProperty(navigator, "clipboard", clipboardDescriptor);
    } else {
      delete (navigator as unknown as Record<string, unknown>).clipboard;
    }
  });

  it("pressing Copy on a markdown turn writes exactly the plain text, makes no fetch call and notifies nothing — DoD-8", async () => {
    // No userEvent here: its setup installs its own clipboard stub over navigator.clipboard.
    const fetchMock = vi.fn<FetchFn>(async () => envelope("unexpected", 500));
    vi.stubGlobal("fetch", fetchMock);
    const writeText = vi.fn<(text: string) => Promise<void>>(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });

    renderRecord(seeded([entry(PARTNER_ID, "partner", "P1"), entry(TURN_ID, "turn", COPY_SOURCE)]));

    fireEvent.click(within(item(1)).getByRole("button", { name: COPY_NAME }));

    await waitFor(() => {
      expect(writeText).toHaveBeenCalled();
    });
    await settle();

    expect(writeText).toHaveBeenCalledTimes(1);
    expect(writeText).toHaveBeenCalledWith(COPY_PLAIN);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

describe("StreamRecord actions — reveal on hover or focus within (D6)", () => {
  it("at rest every item's actions group reports data-revealed false — DoD-9", () => {
    renderRecord(seeded(threeEntries()));

    for (const listItem of recordItems()) {
      expect(actionsGroup(listItem)).toHaveAttribute("data-revealed", "false");
    }
  });

  it("mouseEnter on the item reveals its actions group and mouseLeave hides it again — DoD-9", async () => {
    renderRecord(seeded(threeEntries()));

    const turnItem = item(1);
    expect(actionsGroup(turnItem)).toHaveAttribute("data-revealed", "false");

    fireEvent.mouseEnter(turnItem);
    await waitFor(() => {
      expect(actionsGroup(item(1))).toHaveAttribute("data-revealed", "true");
    });

    fireEvent.mouseLeave(item(1));
    await waitFor(() => {
      expect(actionsGroup(item(1))).toHaveAttribute("data-revealed", "false");
    });
  });

  it("focusing the item's Edit entry button reveals the group; blurring it out of the item hides it — DoD-9", async () => {
    renderRecord(seeded(threeEntries()));

    const editButton = within(item(1)).getByRole("button", { name: EDIT_NAME });
    act(() => {
      editButton.focus();
    });
    expect(editButton).toHaveFocus();
    await waitFor(() => {
      expect(actionsGroup(item(1))).toHaveAttribute("data-revealed", "true");
    });

    act(() => {
      editButton.blur();
    });
    expect(editButton).not.toHaveFocus();
    await waitFor(() => {
      expect(actionsGroup(item(1))).toHaveAttribute("data-revealed", "false");
    });
  });

  it("while hidden, the item's controls are in the document, not disabled, and reachable by role and name — DoD-9", () => {
    renderRecord(seeded(threeEntries()));

    const turnItem = item(1);
    expect(actionsGroup(turnItem)).toHaveAttribute("data-revealed", "false");

    const edit = within(turnItem).getByRole("button", { name: EDIT_NAME });
    const copy = within(turnItem).getByRole("button", { name: COPY_NAME });
    for (const control of [edit, copy]) {
      expect(control).toBeInTheDocument();
      expect(control).not.toBeDisabled();
      expect(actionsGroup(turnItem).contains(control)).toBe(true);
    }

    const decisionItem = item(2);
    expect(actionsGroup(decisionItem)).toHaveAttribute("data-revealed", "false");
    const decisionEdit = within(decisionItem).getByRole("button", { name: EDIT_NAME });
    expect(decisionEdit).not.toBeDisabled();
    expect(actionsGroup(decisionItem).contains(decisionEdit)).toBe(true);
    // 013's re-open control (last entry, empty zone) now sits in the same group.
    const reopen = within(decisionItem).getByRole("button", { name: REOPEN_NAME });
    expect(actionsGroup(decisionItem).contains(reopen)).toBe(true);
  });

  it("while an entry's editor is open its actions group reports data-revealed true — DoD-10", async () => {
    renderRecord(seeded(threeEntries()));

    // fireEvent.click: no pointer hover is involved in opening the editor.
    fireEvent.click(within(item(1)).getByRole("button", { name: EDIT_NAME }));
    const textbox = screen.getByRole("textbox", { name: EDITOR_NAME });
    fireEvent.mouseLeave(item(1));
    act(() => {
      textbox.focus();
    });

    expect(item(1).contains(textbox)).toBe(true);
    await waitFor(() => {
      expect(actionsGroup(item(1))).toHaveAttribute("data-revealed", "true");
    });
  });
});
