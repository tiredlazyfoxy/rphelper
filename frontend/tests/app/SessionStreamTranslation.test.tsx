// Feature 023, step 005 — SessionStream owns one TranslationState per mount (DoD-8).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done plus
// context.md's D13 (one state per mount, disposed on unmount) and D4 (an aborted translation
// is not a failure, so nothing is notified), and 005.context.md's "UI strings" table and
// "Test shape" (the mount's own stubs, plus a deferred POST whose signal is observed on
// unmount). Stubs key on the exact method + pathname. Never from the implementation.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SessionStream } from "../../src/app/SessionStream";
import type { Message, MessageKind } from "../../src/app/streamApi";
import type { Translation } from "../../src/app/translationApi";
import { AppProviders } from "../../src/shared/AppProviders";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- the spec's names
const RECORD_LIST = "Settled record";
const SHOW_TRANSLATION = "Show translation";
const CANCEL_TRANSLATION = "Cancel translation";
const SHOW_ORIGINAL = "Show original";
const FLICKER_LABELS = [SHOW_TRANSLATION, CANCEL_TRANSLATION, SHOW_ORIGINAL];
const COMPOSER = "Composer";
const NOTIFICATION = ".mantine-Notification-root";

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "7250000000000000077";
const BASE = `/api/sessions/${SESSION_ID}`;
const ENTRIES_PATH = `${BASE}/entries`;
const ZONE_PATH = `${BASE}/zone`;

const PARTNER_ID = "7250000000000000301";
const TURN_ID = "7250000000000000302";

const translationPath = (id: string): string => `/api/messages/${id}/translation`;
const postTranslation = (id: string): string => `POST ${translationPath(id)}`;

const ORIGINAL = "They wave.";
const TURN_TEXT = "I wave back.";
const TRANSLATED = "Они машут.";

const STAMP = "2026-05-10T09:00:00.000000+00:00";

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

/** The wire payload, with all four keys (context.md "Wire contract"). */
function translation(messageId: string, text: string, cached = false): Translation {
  return { message_id: messageId, target_language: "Russian", text, cached };
}

beforeEach(() => {
  notifyFailureSpy.mockClear();
});

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
  return jsonResponse({ error: { code, message: `refused: ${code}`, detail: {} } }, status);
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

type Call = {
  /** "METHOD pathname", keyed exactly — never a prefix. */
  readonly key: string;
  readonly signal: AbortSignal | undefined;
  respond: (body: unknown, status?: number) => void;
};

/** Named so `ReturnType` can give the mock a type without an instantiation expression. */
function fetchMock(impl: FetchFn) {
  return vi.fn<FetchFn>(impl);
}
type FetchMock = ReturnType<typeof fetchMock>;

type Backend = {
  readonly mock: FetchMock;
  readonly calls: Call[];
  keys: () => string[];
  call: (index: number) => Call;
  count: (key: string) => number;
};

/**
 * Answers the mount's two GETs at once and leaves the translate POST **deferred**, so a
 * request can still be in flight when the component unmounts (005.context.md "Test shape").
 * A pending call rejects with a `DOMException` named "AbortError" as soon as its signal
 * aborts, as the platform does. Anything unrouted answers a 500 envelope.
 */
function stubStream(entries: Message[]): Backend {
  const calls: Call[] = [];
  const mock = fetchMock((input, init) => {
    const method = requestMethod(input, init);
    const path = requestUrl(input).pathname;
    const signal = init?.signal ?? (input instanceof Request ? input.signal : undefined);
    let settle!: (response: Response) => void;
    let fail!: (reason: unknown) => void;
    const promise = new Promise<Response>((resolve, reject) => {
      settle = resolve;
      fail = reject;
    });
    const onAbort = (): void => {
      fail(new DOMException("The operation was aborted.", "AbortError"));
    };
    if (signal !== undefined) {
      if (signal.aborted) onAbort();
      else signal.addEventListener("abort", onAbort, { once: true });
    }
    calls.push({
      key: `${method} ${path}`,
      signal,
      respond: (body, status = 200) => settle(jsonResponse(body, status)),
    });
    if (method === "GET" && path === ENTRIES_PATH) settle(jsonResponse({ entries }, 200));
    else if (method === "GET" && path === ZONE_PATH) settle(jsonResponse({ messages: [] }, 200));
    else if (method === "POST" && path === translationPath(PARTNER_ID)) {
      // Deferred on purpose: the test decides whether it ever answers.
    } else settle(envelope("unexpected", 500));
    return promise;
  });
  vi.stubGlobal("fetch", mock);
  return {
    mock,
    calls,
    keys: () => calls.map((call) => call.key),
    call: (index) => {
      const call = calls[index];
      if (call === undefined) throw new Error(`no fetch call at index ${index}`);
      return call;
    },
    count: (key) => calls.filter((call) => call.key === key).length,
  };
}

async function flush(rounds = 6): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => setImmediate(resolve));
    });
  }
}

function renderStream(): { unmount: () => void } {
  const result = render(
    <AppProviders>
      <SessionStream sessionId={SESSION_ID} />
    </AppProviders>,
  );
  return { unmount: result.unmount };
}

function recordList(): HTMLElement {
  return screen.getByRole("list", { name: RECORD_LIST });
}

/** The record's listitem holding the given text. */
function recordItemWith(text: string): HTMLElement {
  const item = within(recordList())
    .getAllByRole("listitem")
    .find((candidate) => (candidate.textContent ?? "").includes(text));
  if (item === undefined) throw new Error(`no record item holds ${JSON.stringify(text)}`);
  return item;
}

function newUser(): ReturnType<typeof userEvent.setup> {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

// ===========================================================================
// DoD-8 — the stream owns the flicker state for its mount
// ===========================================================================
describe("SessionStream owns one translation state per mount (D13)", () => {
  it("a partner row served by GET …/entries shows the flicker, and a turn row does not — DoD-8", async () => {
    stubStream([entry(PARTNER_ID, "partner", ORIGINAL), entry(TURN_ID, "turn", TURN_TEXT)]);
    renderStream();
    await flush();

    expect(screen.getByRole("textbox", { name: COMPOSER })).toBeInTheDocument();

    const partner = recordItemWith(ORIGINAL);
    expect(within(partner).getAllByRole("button", { name: SHOW_TRANSLATION })).toHaveLength(1);

    const turn = recordItemWith(TURN_TEXT);
    for (const label of FLICKER_LABELS) {
      expect(within(turn).queryByRole("button", { name: label })).toBeNull();
    }
  });

  it("pressing it from the mounted stream POSTs that row's translation path, which shows once answered — DoD-8", async () => {
    const backend = stubStream([entry(PARTNER_ID, "partner", ORIGINAL)]);
    renderStream();
    await flush();

    const user = newUser();
    await user.click(within(recordItemWith(ORIGINAL)).getByRole("button", { name: SHOW_TRANSLATION }));
    await flush();

    expect(backend.count(postTranslation(PARTNER_ID))).toBe(1);
    const post = backend.calls.find((call) => call.key === postTranslation(PARTNER_ID));
    post?.respond(translation(PARTNER_ID, TRANSLATED));
    await flush();

    const item = recordItemWith(TRANSLATED);
    expect(item.textContent).not.toContain(ORIGINAL);
    expect(within(item).getAllByRole("button", { name: SHOW_ORIGINAL })).toHaveLength(1);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("unmounting while a translation POST is pending aborts that request's signal, and nothing is notified — DoD-8", async () => {
    const backend = stubStream([entry(PARTNER_ID, "partner", ORIGINAL)]);
    const { unmount } = renderStream();
    await flush();

    const user = newUser();
    await user.click(within(recordItemWith(ORIGINAL)).getByRole("button", { name: SHOW_TRANSLATION }));
    await flush();

    const post = backend.calls.find((call) => call.key === postTranslation(PARTNER_ID));
    expect(post).not.toBeUndefined();
    expect(post?.signal?.aborted).toBe(false);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: CANCEL_TRANSLATION })).toBeInTheDocument();
    });

    unmount();
    await flush();

    expect(post?.signal?.aborted).toBe(true);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(Array.from(document.querySelectorAll(NOTIFICATION))).toEqual([]);
  });
});
