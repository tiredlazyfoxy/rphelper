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
//
// Amended by feature 017, step 011 (DoD-6, DoD-7): `ComposerProps` gained an optional
// `sendBlockedReason` (017 D17). Every 013 case above renders without it and is unchanged. The
// gate cases are in the last block, under a describe naming 017 step 011, so their "— DoD-N"
// tags are 017 step 011's: on *my turn* a non-null reason disables Send whatever the draft and
// shows the sentence; Settle is never gated; on *partner* the reason is not shown and Send and
// the paste file as before; a null reason changes nothing.
//
// Amended by feature 021, step 007 (DoD-7, D12): Send on *my turn* now composes — POST
// …/zone/compose {"text"} answered with a streamed `accepted` + `done` body — instead of POST
// …/zone/messages. The two Send-on-my-turn cases (013 DoD-9, 017 step 011 DoD-7) expect the
// compose path; 013 DoD-13's pending case moves to *partner* (the branch that keeps `busy`), since
// a my-turn compose leaves Settle enabled mid-stream (019 D13). Settle still appends via
// …/zone/messages, so every Settle case is unchanged.
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
const COMPOSE_PATH = `${BASE}/zone/compose`;
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

// 021 step 007: the compose route's streamed `accepted` + `done` body, built fresh per call.
const enc = new TextEncoder();
function composedOk(): Response {
  const frames = [
    { event: "accepted", message_id: "7250000000000000304" },
    { event: "done", message_id: "7250000000000000305" },
  ];
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) controller.enqueue(enc.encode(`data: ${JSON.stringify(frame)}\n\n`));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
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
    // 021 step 007: Send on my turn composes.
    if (method === "POST" && pathname === COMPOSE_PATH) return composedOk();
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

/** 017 step 011: the composer with the gate prop (a sentence or null). */
function renderGatedComposer(state: StreamState, sendBlockedReason: string | null): void {
  render(
    <AppProviders>
      <Composer state={state} sendBlockedReason={sendBlockedReason} />
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

  // 021 step 007 (DoD-7): was POST …/zone/messages; Send on my turn now composes.
  it('[021 step 007 DoD-7] on my turn with draft "Discussion line", Send POSTs …/zone/compose {"text":"Discussion line"} — DoD-9', async () => {
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
    expect(sent.map((s) => s.line)).toEqual([`POST ${COMPOSE_PATH}`]);
    expect(sent[0]?.body).toBe('{"text":"Discussion line"}');
    expect(lines(log)).not.toContain(`POST ${APPEND_PATH}`);
  });

  // 021 step 007 (DoD-7): a my-turn Send no longer holds `busy` (019 D13: Settle stays enabled
  // mid-stream), so the pending case runs on partner, whose filing keeps 013's busy handling.
  it("[021 step 007 DoD-7] while a partner Send is pending, Send and Settle are disabled — DoD-13", async () => {
    const pending = deferred<Response>();
    stubFetch((method, pathname) => {
      if (method === "POST" && pathname === ENTRIES_PATH) return pending.promise;
      if (method === "GET" && pathname === ZONE_PATH) return jsonResponse({ messages: [] }, 200);
      if (method === "GET" && pathname === ENTRIES_PATH) return jsonResponse({ entries: partnerDefaultEntries() }, 200);
      return undefined;
    });
    const user = newUser();
    const state = seeded({ entries: partnerDefaultEntries(), draft: "Hello" });
    renderComposer(state);
    expect(effectiveKind(state)).toBe("partner");

    expect(sendButton()).toBeEnabled();

    await user.click(sendButton());

    await waitFor(() => {
      expect(sendButton()).toBeDisabled();
    });
    expect(settleButton()).toBeDisabled();

    await act(async () => {
      pending.resolve(jsonResponse(entry("7250000000000000301", "partner", "Hello"), 201));
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

// ---------------------------------------------------------------------------
// Feature 017, step 011 — the Send gate (US-107, D17). Every "— DoD-N" here is 017 step 011's.
const NO_MODEL_REASON = "Cannot send: no model is enabled on this instance.";

describe("017 step 011 — Composer's sendBlockedReason gate (US-107.AC-1, US-107.AC-2, US-135.AC-1, D17)", () => {
  it('on my turn with the reason and draft "Hello": Send is disabled, the sentence is shown and Settle is enabled — DoD-6', () => {
    stubFetch(() => undefined);
    const state = seeded({ draft: "Hello" });
    renderGatedComposer(state, NO_MODEL_REASON);

    expect(effectiveKind(state)).toBe("turn");
    expect(composer()).toHaveValue("Hello");
    expect(sendButton()).toBeDisabled();
    expect(screen.getByText(NO_MODEL_REASON)).toBeInTheDocument();
    expect(settleButton()).toBeEnabled();
  });

  it("on my turn with the reason, typing a draft never enables Send, and pressing it sends nothing — DoD-6", async () => {
    const log = happyBackend();
    const user = newUser();
    const state = seeded();
    renderGatedComposer(state, NO_MODEL_REASON);

    await user.type(composer(), "Hello");
    expect(sendButton()).toBeDisabled();

    await user.click(sendButton());
    await flush();
    expect(posts(log)).toEqual([]);
  });

  it('on my turn with the reason, pressing "Settle" with draft "Hello" still appends then settles — DoD-6', async () => {
    const log = happyBackend({ entries: [entry("7250000000000000303", "turn", "Hello")] });
    const user = newUser();
    const state = seeded({ draft: "Hello" });
    renderGatedComposer(state, NO_MODEL_REASON);

    await user.click(settleButton());
    await waitFor(() => {
      expect(lines(log)).toContain(`POST ${SETTLE_PATH}`);
    });
    await flush();

    const sent = posts(log);
    expect(sent.map((s) => s.line)).toEqual([`POST ${APPEND_PATH}`, `POST ${SETTLE_PATH}`]);
    expect(sent[0]?.body).toBe('{"text":"Hello"}');
    expect(composer()).toHaveValue("");
  });

  it("on my turn with the reason and one zone row, Settle with a blank draft settles alone — DoD-6", async () => {
    const log = happyBackend({ entries: [entry("7250000000000000303", "turn", "Mine")] });
    const user = newUser();
    const state = seeded({ zone: [zoneRow("7250000000000000101", "user", "Mine")] });
    renderGatedComposer(state, NO_MODEL_REASON);

    expect(settleButton()).toBeEnabled();
    await user.click(settleButton());
    await waitFor(() => {
      expect(lines(log)).toContain(`POST ${SETTLE_PATH}`);
    });
    await flush();

    expect(posts(log).map((s) => s.line)).toEqual([`POST ${SETTLE_PATH}`]);
  });

  it('on partner with the same reason: no reason text, and "Send" with draft "Typed partner text" files the partner block — DoD-7', async () => {
    const log = happyBackend({ entries: partnerDefaultEntries() });
    const user = newUser();
    const state = seeded({ entries: partnerDefaultEntries(), draft: "Typed partner text" });
    renderGatedComposer(state, NO_MODEL_REASON);
    expect(effectiveKind(state)).toBe("partner");

    expect(screen.queryByText(NO_MODEL_REASON)).toBeNull();
    expect(sendButton()).toBeEnabled();

    await user.click(sendButton());
    await waitFor(() => {
      expect(posts(log)).toHaveLength(1);
    });
    await flush();

    const sent = posts(log);
    expect(sent.map((s) => s.line)).toEqual([`POST ${ENTRIES_PATH}`]);
    expect(sent[0]?.body).toBe('{"kind":"partner","text":"Typed partner text"}');
  });

  it("on partner with the same reason, a paste still files immediately and leaves the draft — DoD-7", async () => {
    const log = happyBackend({
      entries: [...partnerDefaultEntries(), entry("7250000000000000301", "partner", "Partner text ((ooc?))")],
    });
    const state = seeded({ entries: partnerDefaultEntries(), draft: "Earlier draft" });
    renderGatedComposer(state, NO_MODEL_REASON);
    expect(effectiveKind(state)).toBe("partner");
    // DoD-7: while still on partner, the reason is not shown. After the paste files a
    // partner entry the default position returns to my turn (013), where D17 shows the
    // reason, so its absence is asserted only before the paste.
    expect(screen.queryByText(NO_MODEL_REASON)).toBeNull();

    const notPrevented = paste("Partner text ((ooc?))");
    await waitFor(() => {
      expect(lines(log)).toContain(`POST ${ENTRIES_PATH}`);
    });
    await flush();

    expect(notPrevented).toBe(false);
    const sent = posts(log);
    expect(sent.map((s) => s.line)).toEqual([`POST ${ENTRIES_PATH}`]);
    expect(sent[0]?.body).toBe('{"kind":"partner","text":"Partner text ((ooc?))"}');
    expect(composer()).toHaveValue("Earlier draft");
  });

  it("on partner with the same reason, Settle stays disabled exactly as without it — DoD-7", () => {
    const state = seeded({ entries: partnerDefaultEntries(), draft: "Some partner text" });
    renderGatedComposer(state, NO_MODEL_REASON);

    expect(settleButton()).toBeDisabled();
  });

  it("switching from partner to my turn with the reason shows it and disables Send — DoD-7", async () => {
    stubFetch(() => undefined);
    const user = newUser();
    const state = seeded({ entries: partnerDefaultEntries(), draft: "Typed text" });
    render(
      <AppProviders>
        <KindSwitch state={state} />
        <Composer state={state} sendBlockedReason={NO_MODEL_REASON} />
      </AppProviders>,
    );
    expect(screen.queryByText(NO_MODEL_REASON)).toBeNull();
    expect(sendButton()).toBeEnabled();

    await user.click(screen.getByRole("radio", { name: "My turn" }));

    expect(effectiveKind(state)).toBe("turn");
    expect(screen.getByText(NO_MODEL_REASON)).toBeInTheDocument();
    expect(sendButton()).toBeDisabled();
  });

  // 021 step 007 (DoD-7): was POST …/zone/messages; Send on my turn now composes.
  it("with sendBlockedReason null on my turn, Send is enabled with a draft and POSTs …/zone/compose; no reason is shown [021 step 007 DoD-7] — DoD-7", async () => {
    const log = happyBackend();
    const user = newUser();
    const state = seeded({ draft: "Discussion line" });
    renderGatedComposer(state, null);

    expect(sendButton()).toBeEnabled();
    expect(settleButton()).toBeEnabled();
    expect(screen.queryByText(NO_MODEL_REASON)).toBeNull();
    expect(screen.queryByText(/^Cannot send:/)).toBeNull();

    await user.click(sendButton());
    await waitFor(() => {
      expect(posts(log)).toHaveLength(1);
    });
    await flush();

    const sent = posts(log);
    expect(sent.map((s) => s.line)).toEqual([`POST ${COMPOSE_PATH}`]);
    expect(sent[0]?.body).toBe('{"text":"Discussion line"}');
  });

  it("with sendBlockedReason null, a blank draft keeps Send disabled and the preview line still follows the draft — DoD-7", () => {
    const state = seeded();
    renderGatedComposer(state, null);

    expect(sendButton()).toBeDisabled();
    expect(shownPreviews()).toEqual([]);
    expect(screen.getByRole("button", { name: DISCARD_NAME })).toBeInTheDocument();

    fireEvent.change(composer(), { target: { value: "She walks." } });
    expect(sendButton()).toBeEnabled();
    expect(shownPreviews()).toEqual([PREVIEW_TURN]);
    expect(screen.queryByRole("button", { name: DISCARD_NAME })).toBeNull();
  });

  it("with sendBlockedReason null on partner, a paste files immediately — DoD-7", async () => {
    const log = happyBackend({
      entries: [...partnerDefaultEntries(), entry("7250000000000000301", "partner", "Pasted")],
    });
    const state = seeded({ entries: partnerDefaultEntries() });
    renderGatedComposer(state, null);

    paste("Pasted");
    await waitFor(() => {
      expect(lines(log)).toContain(`POST ${ENTRIES_PATH}`);
    });
    await flush();

    expect(posts(log).map((s) => s.line)).toEqual([`POST ${ENTRIES_PATH}`]);
    expect(posts(log)[0]?.body).toBe('{"kind":"partner","text":"Pasted"}');
  });
});

// ---------------------------------------------------------------------------
// Feature 018, step 003 — the stream composer rebuilt on ComposerCore (D4). Every 013 / 017
// assertion above is unchanged and is DoD-5's main evidence; the cases below add the slot
// placement the step's Interface intent states (preview under the text area; Settle, then
// Discard, beside Send). Every "— DoD-N" here is 018 step 003's.
function precedes(first: Node, second: Node): boolean {
  return (first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

describe("018 step 003 — Composer rebuilt on the core keeps its public behaviour (D4)", () => {
  it('with a blank draft and an empty zone: textbox "Composer", then "Send", then "Settle", then "Discard empty zone" — DoD-5', () => {
    stubFetch(() => undefined);
    renderComposer(seeded());

    const textbox = composer();
    const send = sendButton();
    const settle = settleButton();
    const discard = screen.getByRole("button", { name: DISCARD_NAME });

    expect(precedes(textbox, send)).toBe(true);
    expect(precedes(send, settle)).toBe(true);
    expect(precedes(settle, discard)).toBe(true);
  });

  it('with draft "She walks." on my turn, the preview line sits after the text area and before "Send" — DoD-5', () => {
    stubFetch(() => undefined);
    renderComposer(seeded({ draft: "She walks." }));

    const preview = screen.getByText(PREVIEW_TURN);
    expect(precedes(composer(), preview)).toBe(true);
    expect(precedes(preview, sendButton())).toBe(true);
    expect(precedes(sendButton(), settleButton())).toBe(true);
  });

  it("the composer itself renders no kind switch (the switch stays a sibling) — DoD-5", () => {
    stubFetch(() => undefined);
    renderComposer(seeded());

    expect(screen.queryByRole("radio", { name: "My turn" })).toBeNull();
    expect(screen.queryByRole("radio", { name: "Partner" })).toBeNull();
  });
});
