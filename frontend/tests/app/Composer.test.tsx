// Feature 013, step 006 — the composer (DoD-3..DoD-13; DoD-14 is manual/live).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done plus
// context.md's D1, D2, D3, D6, D7, D8, D9, D15 and the UI strings table:
//   - a textbox "Composer" whose value is the draft;
//   - "Send" enabled iff the draft is non-blank and nothing is in flight; on *my turn* it POSTs
//     …/zone/messages {"text"}, on *partner* …/entries {"kind":"partner","text"};
//   - "Settle" enabled on *my turn* iff the zone holds a row or the draft is non-blank, never
//     on *partner* (disabled, not hidden); with a draft it appends then settles;
//   - on *partner* a paste is intercepted and filed at once, the draft untouched; on *my turn*
//     a paste makes no request;
//   - one fixed preview sentence under the composer on *my turn* when there is a settle target;
//   - "Discard empty zone" present only with an empty zone and a blank draft; pressing it makes
//     no request and returns the switch to its computed default.
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { runInAction } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Composer } from "../../src/app/Composer";
import { KindSwitch } from "../../src/app/KindSwitch";
import type { Message, MessageKind, MessageRole } from "../../src/app/streamApi";
import { StreamState, effectiveKind } from "../../src/app/streamState";
import { AppProviders } from "../../src/shared/AppProviders";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "7250000000000000042";
const BASE = `/api/sessions/${SESSION_ID}`;
const ENTRIES_PATH = `${BASE}/entries`;
const ZONE_PATH = `${BASE}/zone`;
const APPEND_PATH = `${BASE}/zone/messages`;
const SETTLE_PATH = `${BASE}/settle`;

const STAMP = "2026-05-10T09:00:00.000000+00:00";

const PREVIEW_DECISION = "Settles as a decision (out of character).";
const PREVIEW_STRIPPING = "Settles as a turn; the (( )) instructions will be removed.";
const PREVIEW_TURN = "Settles as a turn.";
const ALL_PREVIEWS = [PREVIEW_DECISION, PREVIEW_STRIPPING, PREVIEW_TURN];

const DISCARD_NAME = "Discard empty zone";

/** A settled entry with all eight keys. */
function entry(id: string, kind: MessageKind, text: string): Message {
  return {
    id,
    session_id: SESSION_ID,
    role: "user",
    kind,
    text,
    settled_at: STAMP,
    created_at: STAMP,
    updated_at: STAMP,
  };
}

/** A zone row with all eight keys: `kind` and `settled_at` null. */
function zoneRow(id: string, role: MessageRole, text: string): Message {
  return {
    id,
    session_id: SESSION_ID,
    role,
    kind: null,
    text,
    settled_at: null,
    created_at: STAMP,
    updated_at: STAMP,
  };
}

/** Entries whose last partner-or-turn is a turn: the computed default is *partner*. */
function partnerDefaultEntries(): Message[] {
  return [entry("7250000000000000201", "turn", "I wait by the door.")];
}

type Seed = { entries?: Message[]; zone?: Message[]; draft?: string };

function seeded(seed: Seed = {}): StreamState {
  const state = new StreamState(SESSION_ID);
  runInAction(() => {
    state.entries = seed.entries ?? [];
    state.zone = seed.zone ?? [];
    state.draft = seed.draft ?? "";
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
type Answer = Response | Promise<Response> | undefined;

/**
 * Stubs fetch by exact method + pathname. Every request is logged as "METHOD /path" with its
 * raw body. `route` answers a request or returns undefined for "unexpected" (500).
 */
function stubFetch(route: (method: string, pathname: string) => Answer): Seen[] {
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

/** A backend that answers every stream route successfully. */
function happyBackend(after: { entries?: Message[]; zone?: Message[] } = {}): Seen[] {
  return stubFetch((method, pathname) => {
    if (method === "GET" && pathname === ENTRIES_PATH) return jsonResponse({ entries: after.entries ?? [] }, 200);
    if (method === "GET" && pathname === ZONE_PATH) return jsonResponse({ messages: after.zone ?? [] }, 200);
    if (method === "POST" && pathname === ENTRIES_PATH)
      return jsonResponse(entry("7250000000000000301", "partner", "filed"), 201);
    if (method === "POST" && pathname === APPEND_PATH)
      return jsonResponse(zoneRow("7250000000000000302", "user", "appended"), 201);
    if (method === "POST" && pathname === SETTLE_PATH)
      return jsonResponse({ entry_id: "7250000000000000303", kind: "turn", buried_ids: [] }, 200);
    return undefined;
  });
}

function lines(log: Seen[]): string[] {
  return log.map((seen) => seen.line);
}

function posts(log: Seen[]): Seen[] {
  return log.filter((seen) => seen.line.startsWith("POST "));
}

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function renderComposer(state: StreamState): void {
  render(
    <AppProviders>
      <Composer state={state} />
    </AppProviders>,
  );
}

function renderSwitchAndComposer(state: StreamState): void {
  render(
    <AppProviders>
      <KindSwitch state={state} />
      <Composer state={state} />
    </AppProviders>,
  );
}

function composer(): HTMLElement {
  return screen.getByRole("textbox", { name: "Composer" });
}

function sendButton(): HTMLElement {
  return screen.getByRole("button", { name: "Send" });
}

function settleButton(): HTMLElement {
  return screen.getByRole("button", { name: "Settle" });
}

function paste(text: string): boolean {
  return fireEvent.paste(composer(), { clipboardData: { getData: () => text } });
}

function newUser(): ReturnType<typeof userEvent.setup> {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

async function flush(): Promise<void> {
  await act(async () => {
    for (let round = 0; round < 6; round += 1) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  });
}

function shownPreviews(): string[] {
  return ALL_PREVIEWS.filter((sentence) => screen.queryByText(sentence) !== null);
}

// ---------------------------------------------------------------- tests
describe("Composer — draft and button enablement (D2, D6, D9)", () => {
  it('the textbox "Composer" reflects typing into the draft; Settle and Send go from disabled to enabled after "Hello" — DoD-3', async () => {
    const log = stubFetch(() => undefined);
    const user = newUser();
    const state = seeded();
    renderComposer(state);

    expect(effectiveKind(state)).toBe("turn");
    expect(composer()).toHaveValue("");
    expect(settleButton()).toBeDisabled();
    expect(sendButton()).toBeDisabled();

    await user.type(composer(), "Hello");

    expect(state.draft).toBe("Hello");
    expect(composer()).toHaveValue("Hello");
    expect(settleButton()).toBeEnabled();
    expect(sendButton()).toBeEnabled();
    expect(log).toEqual([]);
  });

  it("the composer shows a draft set on the state — DoD-3", () => {
    const state = seeded({ draft: "Already here" });
    renderComposer(state);

    expect(composer()).toHaveValue("Already here");
  });
});

describe("Composer — Settle (D2)", () => {
  it("on my turn with one user zone row, a blank draft and no assistant row, Settle is enabled and POSTs only …/settle, then re-reads entries and zone — DoD-4", async () => {
    const log = happyBackend({ entries: [entry("7250000000000000303", "turn", "Mine")] });
    const user = newUser();
    const state = seeded({ zone: [zoneRow("7250000000000000101", "user", "Mine")] });
    renderComposer(state);

    expect(settleButton()).toBeEnabled();

    await user.click(settleButton());
    await waitFor(() => {
      expect(log.length).toBeGreaterThanOrEqual(3);
    });
    await flush();

    const seen = lines(log);
    expect(posts(log).map((s) => s.line)).toEqual([`POST ${SETTLE_PATH}`]);
    expect(log[0]?.body).toBeNull();
    expect(seen[0]).toBe(`POST ${SETTLE_PATH}`);
    expect(seen.slice(1).sort()).toEqual([`GET ${ENTRIES_PATH}`, `GET ${ZONE_PATH}`].sort());
  });

  it('on my turn with draft "My reply", Settle POSTs …/zone/messages {"text":"My reply"} then …/settle, and the composer ends empty — DoD-5', async () => {
    const log = happyBackend({ entries: [entry("7250000000000000303", "turn", "My reply")] });
    const user = newUser();
    const state = seeded();
    renderComposer(state);

    fireEvent.change(composer(), { target: { value: "My reply" } });
    expect(state.draft).toBe("My reply");

    await user.click(settleButton());
    await waitFor(() => {
      expect(lines(log)).toContain(`POST ${SETTLE_PATH}`);
    });
    await flush();

    const sent = posts(log);
    expect(sent.map((s) => s.line)).toEqual([`POST ${APPEND_PATH}`, `POST ${SETTLE_PATH}`]);
    expect(sent[0]?.body).toBe('{"text":"My reply"}');

    const seen = lines(log);
    const settleAt = seen.indexOf(`POST ${SETTLE_PATH}`);
    expect(seen.indexOf(`POST ${APPEND_PATH}`)).toBeLessThan(settleAt);
    expect(seen.lastIndexOf(`GET ${ENTRIES_PATH}`)).toBeGreaterThan(settleAt);
    expect(seen.lastIndexOf(`GET ${ZONE_PATH}`)).toBeGreaterThan(settleAt);

    expect(composer()).toHaveValue("");
    expect(state.draft).toBe("");
  });

  it("on partner, Settle is present and disabled even with zone rows and a non-blank draft — DoD-6", () => {
    const state = seeded({
      entries: partnerDefaultEntries(),
      zone: [zoneRow("7250000000000000101", "user", "A line"), zoneRow("7250000000000000102", "assistant", "Reply")],
      draft: "Some partner text",
    });
    renderComposer(state);

    expect(effectiveKind(state)).toBe("partner");
    const settle = settleButton();
    expect(settle).toBeInTheDocument();
    expect(settle).toBeDisabled();
  });
});

describe("Composer — paste (D7)", () => {
  it('on partner, pasting "Partner text ((ooc?))" POSTs exactly {"kind":"partner","text":…} to …/entries with no Settle, and leaves the draft unchanged — DoD-7', async () => {
    const log = happyBackend({
      entries: [...partnerDefaultEntries(), entry("7250000000000000301", "partner", "Partner text ((ooc?))")],
    });
    const state = seeded({ entries: partnerDefaultEntries(), draft: "Earlier draft" });
    renderComposer(state);
    expect(effectiveKind(state)).toBe("partner");

    const notPrevented = paste("Partner text ((ooc?))");

    await waitFor(() => {
      expect(lines(log)).toContain(`POST ${ENTRIES_PATH}`);
    });
    await flush();

    expect(notPrevented).toBe(false);
    const sent = posts(log);
    expect(sent.map((s) => s.line)).toEqual([`POST ${ENTRIES_PATH}`]);
    expect(sent[0]?.body).toBe('{"kind":"partner","text":"Partner text ((ooc?))"}');
    expect(lines(log)).not.toContain(`POST ${SETTLE_PATH}`);

    expect(composer()).toHaveValue("Earlier draft");
    expect(state.draft).toBe("Earlier draft");
  });

  it("on partner with zone rows present, the paste files the same way and leaves the draft unchanged — DoD-7", async () => {
    const zone = [zoneRow("7250000000000000101", "user", "Open line")];
    const log = happyBackend({
      entries: [...partnerDefaultEntries(), entry("7250000000000000301", "partner", "Partner text ((ooc?))")],
      zone,
    });
    const state = seeded({ entries: partnerDefaultEntries(), zone, draft: "Earlier draft" });
    renderComposer(state);
    expect(effectiveKind(state)).toBe("partner");

    const notPrevented = paste("Partner text ((ooc?))");

    await waitFor(() => {
      expect(lines(log)).toContain(`POST ${ENTRIES_PATH}`);
    });
    await flush();

    expect(notPrevented).toBe(false);
    const sent = posts(log);
    expect(sent.map((s) => s.line)).toEqual([`POST ${ENTRIES_PATH}`]);
    expect(sent[0]?.body).toBe('{"kind":"partner","text":"Partner text ((ooc?))"}');
    expect(lines(log)).not.toContain(`POST ${SETTLE_PATH}`);

    expect(composer()).toHaveValue("Earlier draft");
    expect(state.draft).toBe("Earlier draft");
  });

  it("on my turn, a paste makes no request — DoD-8", async () => {
    const log = happyBackend();
    const state = seeded({ draft: "Earlier draft" });
    renderComposer(state);
    expect(effectiveKind(state)).toBe("turn");

    const notPrevented = paste("Some pasted words");
    await flush();

    expect(notPrevented).toBe(true);
    expect(log).toEqual([]);
  });
});

describe("Composer — Send (D6, D7)", () => {
  it('on partner with draft "Typed partner text", Send POSTs …/entries {"kind":"partner","text":"Typed partner text"} — DoD-9', async () => {
    const log = happyBackend({ entries: partnerDefaultEntries() });
    const user = newUser();
    const state = seeded({ entries: partnerDefaultEntries(), draft: "Typed partner text" });
    renderComposer(state);
    expect(effectiveKind(state)).toBe("partner");

    await user.click(sendButton());
    await waitFor(() => {
      expect(posts(log)).toHaveLength(1);
    });
    await flush();

    const sent = posts(log);
    expect(sent.map((s) => s.line)).toEqual([`POST ${ENTRIES_PATH}`]);
    expect(sent[0]?.body).toBe('{"kind":"partner","text":"Typed partner text"}');
  });

  it('on my turn with draft "Discussion line", Send POSTs …/zone/messages {"text":"Discussion line"} — DoD-9', async () => {
    const log = happyBackend();
    const user = newUser();
    const state = seeded({ draft: "Discussion line" });
    renderComposer(state);
    expect(effectiveKind(state)).toBe("turn");

    await user.click(sendButton());
    await waitFor(() => {
      expect(posts(log)).toHaveLength(1);
    });
    await flush();

    const sent = posts(log);
    expect(sent.map((s) => s.line)).toEqual([`POST ${APPEND_PATH}`]);
    expect(sent[0]?.body).toBe('{"text":"Discussion line"}');
  });

  it("while a Send is pending, Send and Settle are disabled — DoD-13", async () => {
    const pending = deferred<Response>();
    stubFetch((method, pathname) => {
      if (method === "POST" && pathname === APPEND_PATH) return pending.promise;
      if (method === "GET" && pathname === ZONE_PATH) return jsonResponse({ messages: [] }, 200);
      if (method === "GET" && pathname === ENTRIES_PATH) return jsonResponse({ entries: [] }, 200);
      return undefined;
    });
    const user = newUser();
    const state = seeded({ draft: "Hello" });
    renderComposer(state);

    expect(sendButton()).toBeEnabled();
    expect(settleButton()).toBeEnabled();

    await user.click(sendButton());

    await waitFor(() => {
      expect(sendButton()).toBeDisabled();
    });
    expect(settleButton()).toBeDisabled();

    await act(async () => {
      pending.resolve(jsonResponse(zoneRow("7250000000000000302", "user", "Hello"), 201));
    });
    await flush();
  });
});

describe("Composer — preview line (D1)", () => {
  it('on my turn with draft "((OOC aside))" the preview reads exactly the decision sentence — DoD-10', () => {
    renderComposer(seeded({ draft: "((OOC aside))" }));

    expect(screen.getByText(PREVIEW_DECISION)).toBeInTheDocument();
    expect(shownPreviews()).toEqual([PREVIEW_DECISION]);
  });

  it('on my turn with draft "She walks. ((make it tense)) He waits." the preview reads exactly the stripping sentence — DoD-10', () => {
    renderComposer(seeded({ draft: "She walks. ((make it tense)) He waits." }));

    expect(screen.getByText(PREVIEW_STRIPPING)).toBeInTheDocument();
    expect(shownPreviews()).toEqual([PREVIEW_STRIPPING]);
  });

  it('on my turn with draft "She walks." the preview reads exactly "Settles as a turn." — DoD-10', () => {
    renderComposer(seeded({ draft: "She walks." }));

    expect(screen.getByText(PREVIEW_TURN)).toBeInTheDocument();
    expect(shownPreviews()).toEqual([PREVIEW_TURN]);
  });

  it('with a blank draft and last zone row "((note))", the preview is the decision sentence — DoD-10', () => {
    renderComposer(
      seeded({
        zone: [zoneRow("7250000000000000101", "user", "She walks."), zoneRow("7250000000000000102", "assistant", "((note))")],
        draft: "",
      }),
    );

    expect(screen.getByText(PREVIEW_DECISION)).toBeInTheDocument();
    expect(shownPreviews()).toEqual([PREVIEW_DECISION]);
  });

  it("the preview follows typing in the composer — DoD-10", () => {
    const state = seeded();
    renderComposer(state);

    expect(shownPreviews()).toEqual([]);

    fireEvent.change(composer(), { target: { value: "((OOC aside))" } });
    expect(shownPreviews()).toEqual([PREVIEW_DECISION]);

    fireEvent.change(composer(), { target: { value: "She walks." } });
    expect(shownPreviews()).toEqual([PREVIEW_TURN]);
  });

  it("on partner, no preview sentence is shown — DoD-10", () => {
    renderComposer(
      seeded({
        entries: partnerDefaultEntries(),
        zone: [zoneRow("7250000000000000101", "user", "((note))")],
        draft: "She walks. ((make it tense)) He waits.",
      }),
    );

    expect(shownPreviews()).toEqual([]);
  });

  it("with a blank draft and an empty zone, no preview sentence is shown — DoD-10", () => {
    renderComposer(seeded({ draft: "   " }));

    expect(shownPreviews()).toEqual([]);
  });
});

describe("Composer — Discard empty zone (D3)", () => {
  it('"Discard empty zone" is present with an empty zone and a blank composer — DoD-11', () => {
    renderComposer(seeded());

    expect(screen.getByRole("button", { name: DISCARD_NAME })).toBeInTheDocument();
  });

  it('"Discard empty zone" is absent once the composer holds "x" — DoD-11', () => {
    const state = seeded();
    renderComposer(state);
    expect(screen.getByRole("button", { name: DISCARD_NAME })).toBeInTheDocument();

    fireEvent.change(composer(), { target: { value: "x" } });

    expect(screen.queryByRole("button", { name: DISCARD_NAME })).toBeNull();
  });

  it('"Discard empty zone" is absent with one zone row — DoD-11', () => {
    renderComposer(seeded({ zone: [zoneRow("7250000000000000101", "user", "A line")] }));

    expect(screen.queryByRole("button", { name: DISCARD_NAME })).toBeNull();
  });

  it("with an override of partner on an empty zone, Discard makes no request and returns the switch to its computed default — DoD-12", async () => {
    const log = stubFetch(() => undefined);
    const user = newUser();
    const state = seeded();
    renderSwitchAndComposer(state);

    expect(screen.getByRole("radio", { name: "My turn" })).toBeChecked();

    await user.click(screen.getByRole("radio", { name: "Partner" }));
    expect(effectiveKind(state)).toBe("partner");
    expect(screen.getByRole("radio", { name: "Partner" })).toBeChecked();

    await user.click(screen.getByRole("button", { name: DISCARD_NAME }));
    await flush();

    expect(log).toEqual([]);
    expect(effectiveKind(state)).toBe("turn");
    expect(screen.getByRole("radio", { name: "My turn" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Partner" })).not.toBeChecked();
  });
});
