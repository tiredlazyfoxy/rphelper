// Feature 014, step 003 — the composer's enormous-paste warning (DoD-6..DoD-9; DoD-10 is
// manual/live).
//
// Expected behaviour comes from the step's Interface intent and Definition of done plus
// context.md D3 (boundary: 128,000 chars no warning, 128,001 warning) and D5 (fires on
// composer pastes in both positions, only for non-blank enormous text; never blocks, delays
// or alters the paste or the partner filing):
//   - partner: warning (when enormous) and still the POST …/entries {"kind":"partner","text"},
//     draft untouched, default prevented;
//   - my turn: warning (when enormous), no request, default NOT prevented.
// `fireEvent.paste(...)` returns false iff the handler prevented the default.
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { runInAction } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Composer } from "../../src/app/Composer";
import type { Message, MessageKind } from "../../src/app/streamApi";
import { StreamState, chooseKind, effectiveKind } from "../../src/app/streamState";
import { AppProviders } from "../../src/shared/AppProviders";

const notifyWarningSpy = vi.hoisted(() => vi.fn<(id: "paste-context-cost") => void>());
vi.mock("../../src/shared/notifyWarning", () => ({ notifyWarning: notifyWarningSpy }));

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "7250000000000000042";
const BASE = `/api/sessions/${SESSION_ID}`;
const ENTRIES_PATH = `${BASE}/entries`;
const ZONE_PATH = `${BASE}/zone`;

const STAMP = "2026-05-10T09:00:00.000000+00:00";
const PASTE_ID = "paste-context-cost";
const EARLIER_DRAFT = "Earlier draft";

const AT_THRESHOLD = "a".repeat(128_000);
const OVER_THRESHOLD = "a".repeat(128_001);
const WHITESPACE_OVER_THRESHOLD = " ".repeat(128_001);

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

function seeded(position: "partner" | "turn"): StreamState {
  const state = new StreamState(SESSION_ID);
  runInAction(() => {
    state.entries = [];
    state.zone = [];
    state.draft = EARLIER_DRAFT;
    state.status = "ready";
  });
  if (position === "partner") chooseKind(state, "partner");
  return state;
}

beforeEach(() => {
  notifyWarningSpy.mockClear();
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

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

type Seen = { line: string; body: string | null };

/** Stubs fetch by exact method + pathname; logs "METHOD /path" with the raw body. */
function happyBackend(): Seen[] {
  const log: Seen[] = [];
  const impl: FetchFn = async (input, init) => {
    const method = requestMethod(input, init);
    const pathname = requestUrl(input).pathname;
    log.push({ line: `${method} ${pathname}`, body: typeof init?.body === "string" ? init.body : null });
    if (method === "GET" && pathname === ENTRIES_PATH) return jsonResponse({ entries: [] }, 200);
    if (method === "GET" && pathname === ZONE_PATH) return jsonResponse({ messages: [] }, 200);
    if (method === "POST" && pathname === ENTRIES_PATH)
      return jsonResponse(entry("7250000000000000301", "partner", "filed"), 201);
    return jsonResponse({ error: { code: "unexpected", message: "unexpected", detail: {} } }, 500);
  };
  vi.stubGlobal("fetch", vi.fn(impl));
  return log;
}

function posts(log: Seen[]): Seen[] {
  return log.filter((seen) => seen.line.startsWith("POST "));
}

function renderComposer(state: StreamState): void {
  render(
    <AppProviders>
      <Composer state={state} />
    </AppProviders>,
  );
}

function composer(): HTMLElement {
  return screen.getByRole("textbox", { name: "Composer" });
}

/** Returns false iff the handler prevented the default. */
function paste(text: string): boolean {
  return fireEvent.paste(composer(), { clipboardData: { getData: () => text } });
}

async function flush(): Promise<void> {
  await act(async () => {
    for (let round = 0; round < 6; round += 1) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  });
}

function expectPartnerFiling(log: Seen[], text: string): void {
  const sent = posts(log);
  expect(sent.map((s) => s.line)).toEqual([`POST ${ENTRIES_PATH}`]);
  expect(sent[0]?.body).toBe(JSON.stringify({ kind: "partner", text }));
  expect(JSON.parse(sent[0]?.body ?? "null")).toEqual({ kind: "partner", text });
}

// ---------------------------------------------------------------- tests
describe("Composer paste warning — partner (D5, US-035.AC-1, US-035.AC-2)", () => {
  it("pasting 128,001 characters warns once with the paste identifier, synchronously — DoD-6", async () => {
    happyBackend();
    const state = seeded("partner");
    renderComposer(state);
    expect(effectiveKind(state)).toBe("partner");

    paste(OVER_THRESHOLD);

    expect(notifyWarningSpy).toHaveBeenCalledTimes(1);
    expect(notifyWarningSpy).toHaveBeenCalledWith(PASTE_ID);
    await flush();
    expect(notifyWarningSpy).toHaveBeenCalledTimes(1);
  });

  it('pasting 128,001 characters still POSTs …/entries with exactly {"kind":"partner","text":<that text>}, prevents the default and leaves the composer unchanged — DoD-6', async () => {
    const log = happyBackend();
    const state = seeded("partner");
    renderComposer(state);
    expect(effectiveKind(state)).toBe("partner");

    const notPrevented = paste(OVER_THRESHOLD);

    await waitFor(() => {
      expect(posts(log)).toHaveLength(1);
    });
    await flush();

    expect(notPrevented).toBe(false);
    expectPartnerFiling(log, OVER_THRESHOLD);
    expect(composer()).toHaveValue(EARLIER_DRAFT);
    expect(state.draft).toBe(EARLIER_DRAFT);
    expect(notifyWarningSpy).toHaveBeenCalledTimes(1);
    expect(notifyWarningSpy).toHaveBeenCalledWith(PASTE_ID);
  });

  it("pasting 128,000 characters makes the same POST and does not warn — DoD-7", async () => {
    const log = happyBackend();
    const state = seeded("partner");
    renderComposer(state);
    expect(effectiveKind(state)).toBe("partner");

    const notPrevented = paste(AT_THRESHOLD);

    await waitFor(() => {
      expect(posts(log)).toHaveLength(1);
    });
    await flush();

    expect(notPrevented).toBe(false);
    expectPartnerFiling(log, AT_THRESHOLD);
    expect(notifyWarningSpy).not.toHaveBeenCalled();
  });

  it("pasting 128,001 characters of only whitespace does not warn — DoD-9", async () => {
    happyBackend();
    const state = seeded("partner");
    renderComposer(state);
    expect(effectiveKind(state)).toBe("partner");

    paste(WHITESPACE_OVER_THRESHOLD);
    await flush();

    expect(notifyWarningSpy).not.toHaveBeenCalled();
  });
});

describe("Composer paste warning — my turn (D5, US-035.AC-1, US-035.AC-2)", () => {
  it("pasting 128,001 characters warns once with the paste identifier, makes no request and is not default-prevented — DoD-8", async () => {
    const log = happyBackend();
    const state = seeded("turn");
    renderComposer(state);
    expect(effectiveKind(state)).toBe("turn");

    const notPrevented = paste(OVER_THRESHOLD);

    expect(notifyWarningSpy).toHaveBeenCalledTimes(1);
    expect(notifyWarningSpy).toHaveBeenCalledWith(PASTE_ID);
    await flush();

    expect(notPrevented).toBe(true);
    expect(log).toEqual([]);
    expect(notifyWarningSpy).toHaveBeenCalledTimes(1);
  });

  it("a short paste does not warn, makes no request and is not default-prevented — DoD-9", async () => {
    const log = happyBackend();
    const state = seeded("turn");
    renderComposer(state);
    expect(effectiveKind(state)).toBe("turn");

    const notPrevented = paste("Some pasted words");
    await flush();

    expect(notPrevented).toBe(true);
    expect(log).toEqual([]);
    expect(notifyWarningSpy).not.toHaveBeenCalled();
  });

  it("pasting 128,001 characters of only whitespace does not warn — DoD-9", async () => {
    happyBackend();
    const state = seeded("turn");
    renderComposer(state);
    expect(effectiveKind(state)).toBe("turn");

    paste(WHITESPACE_OVER_THRESHOLD);
    await flush();

    expect(notifyWarningSpy).not.toHaveBeenCalled();
  });
});
