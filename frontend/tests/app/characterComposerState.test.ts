// Feature 018, step 004 — the page composer's state (DoD-3..DoD-6).
//
// Expected behaviour comes from the step's Interface intent and Definition of done plus 018
// context.md's Wire contract and D5:
//   - can-send: the draft is not blank and nothing is sending;
//   - the send effect posts the draft once through the start-with-message call; on success it
//     applies the response's eight session keys to the workspace SessionsState, clears the
//     draft and calls the callback with the response's id exactly as received; on failure it
//     keeps the draft, calls notifyFailure once with the thrown error, does not call the
//     callback and leaves the workspace state unchanged; either way it clears sending; it
//     never rejects; while a send is pending a second call sends nothing (no double create).
// `fetch` is stubbed by exact method and path; notifyFailure is observed by vi.mock.
import { runInAction, toJS } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  canSendCharacterComposer,
  CharacterComposerState,
  sendCharacterComposer,
  setCharacterComposerDraft,
} from "../../src/app/characterComposerState";
import type { Session, StartedSession } from "../../src/app/sessionsApi";
import { SessionsState } from "../../src/app/sessionsState";
import type { Message } from "../../src/app/streamApi";
import { isApiError } from "../../src/shared/apiError";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- fixtures
// Every id is > Number.MAX_SAFE_INTEGER: a silent numeric coercion would change it.
const CHARACTER_ID = "7250000000000000101";
const SESSION_ID = "7270000000000000101";
const MESSAGE_ID = "7280000000000000101";
const EXISTING_SESSION_ID = "7270000000000000102";
const OTHER_CHARACTER_ID = "7250000000000000102";

const START_PATH = `/api/characters/${CHARACTER_ID}/sessions`;
const STAMP = "2026-10-03T09:26:53.000000+00:00";
const OLDER = "2026-09-01T08:00:00.000000+00:00";

const SESSION_KEYS = [
  "archived_at",
  "character_id",
  "created_at",
  "id",
  "last_used_at",
  "setup_id",
  "setup_name",
  "updated_at",
];

/** The served session's eight keys. */
const SERVED_SESSION: Session = {
  id: SESSION_ID,
  character_id: CHARACTER_ID,
  setup_id: null,
  setup_name: null,
  archived_at: null,
  last_used_at: STAMP,
  created_at: STAMP,
  updated_at: STAMP,
};

/** A working row already in the workspace store (another character, older use). */
const EXISTING_SESSION: Session = {
  id: EXISTING_SESSION_ID,
  character_id: OTHER_CHARACTER_ID,
  setup_id: null,
  setup_name: null,
  archived_at: null,
  last_used_at: OLDER,
  created_at: OLDER,
  updated_at: OLDER,
};

function openingMessage(text: string): Message {
  return {
    id: MESSAGE_ID,
    session_id: SESSION_ID,
    role: "user",
    kind: null,
    text,
    settled_at: null,
    created_at: STAMP,
    updated_at: STAMP,
  };
}

/** The 201 answer: all nine keys. */
function started(text: string): StartedSession {
  return { ...SERVED_SESSION, opening_message: openingMessage(text) };
}

beforeEach(() => {
  notifyFailureSpy.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- helpers
function stubFetch(impl: FetchFn) {
  const mock = vi.fn<FetchFn>(impl);
  vi.stubGlobal("fetch", mock);
  return mock;
}

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

function isStart(input: RequestInfo | URL, init?: RequestInit): boolean {
  const url = requestUrl(input);
  return requestMethod(input, init) === "POST" && url.pathname === START_PATH && url.search === "";
}

function unexpected(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  return Promise.resolve(
    jsonResponse(
      {
        error: {
          code: "unexpected_request",
          message: `${requestMethod(input, init)} ${requestUrl(input).pathname}`,
          detail: {},
        },
      },
      599,
    ),
  );
}

function serveStart(body: unknown, status: number) {
  return stubFetch((input, init) =>
    isStart(input, init) ? Promise.resolve(jsonResponse(body, status)) : unexpected(input, init),
  );
}

function startCalls(mock: ReturnType<typeof stubFetch>): number {
  return mock.mock.calls.filter(([input, init]) => isStart(input, init)).length;
}

function sentBody(mock: ReturnType<typeof stubFetch>, index = 0): unknown {
  const raw = mock.mock.calls[index]?.[1]?.body;
  if (raw === undefined || raw === null) return undefined;
  return typeof raw === "string" ? (JSON.parse(raw) as unknown) : raw;
}

function stateWithDraft(text: string): CharacterComposerState {
  const state = new CharacterComposerState(CHARACTER_ID);
  setCharacterComposerDraft(state, text);
  return state;
}

function workspaceWith(rows: Session[]): SessionsState {
  const sessions = new SessionsState();
  runInAction(() => {
    sessions.sessions = rows.map((row) => ({ ...row }));
    sessions.status = "ready";
  });
  return sessions;
}

function snapshot(sessions: SessionsState): unknown {
  return { sessions: toJS(sessions.sessions), status: sessions.status };
}

// ---------------------------------------------------------------- DoD-3
describe("can-send (D5)", () => {
  it("a new state holds the character id, an empty draft and is not sending — DoD-3", () => {
    const state = new CharacterComposerState(CHARACTER_ID);

    expect(state.characterId).toBe(CHARACTER_ID);
    expect(state.draft).toBe("");
    expect(state.sending).toBe(false);
  });

  it("is false for an empty draft — DoD-3", () => {
    expect(canSendCharacterComposer(new CharacterComposerState(CHARACTER_ID))).toBe(false);
    expect(canSendCharacterComposer(stateWithDraft(""))).toBe(false);
  });

  it("is false for a whitespace-only draft — DoD-3", () => {
    expect(canSendCharacterComposer(stateWithDraft("   \n\t "))).toBe(false);
  });

  it('is true for "Hi" — DoD-3', () => {
    const state = stateWithDraft("Hi");

    expect(state.draft).toBe("Hi");
    expect(canSendCharacterComposer(state)).toBe(true);
  });

  it('is false for "Hi" while sending — DoD-3', () => {
    const state = stateWithDraft("Hi");
    runInAction(() => {
      state.sending = true;
    });

    expect(canSendCharacterComposer(state)).toBe(false);
  });
});

// ---------------------------------------------------------------- DoD-4
describe("the send effect on a 201 (US-117.AC-1, D5)", () => {
  it("posts the draft once as exactly { opening_message } to the character's sessions route — DoD-4", async () => {
    const mock = serveStart(started("Hello there"), 201);
    const state = stateWithDraft("Hello there");

    await sendCharacterComposer(state, new SessionsState(), vi.fn<(id: string) => void>());

    expect(mock).toHaveBeenCalledTimes(1);
    expect(startCalls(mock)).toBe(1);
    expect(sentBody(mock)).toEqual({ opening_message: "Hello there" });
  });

  it("calls the callback once with the served id string, exactly as received — DoD-4", async () => {
    serveStart(started("Hello there"), 201);
    const onStarted = vi.fn<(id: string) => void>();

    await sendCharacterComposer(stateWithDraft("Hello there"), new SessionsState(), onStarted);

    expect(onStarted).toHaveBeenCalledTimes(1);
    expect(onStarted).toHaveBeenCalledWith(SESSION_ID);
    expect(typeof onStarted.mock.calls[0]?.[0]).toBe("string");
  });

  it("leaves the draft empty and clears sending — DoD-4", async () => {
    serveStart(started("Hello there"), 201);
    const state = stateWithDraft("Hello there");

    await sendCharacterComposer(state, new SessionsState(), vi.fn<(id: string) => void>());

    expect(state.draft).toBe("");
    expect(state.sending).toBe(false);
  });

  it("the workspace SessionsState then lists the served session holding exactly its eight keys — DoD-4", async () => {
    serveStart(started("Hello there"), 201);
    const sessions = new SessionsState();

    await sendCharacterComposer(stateWithDraft("Hello there"), sessions, vi.fn<(id: string) => void>());

    const rows = toJS(sessions.sessions);
    expect(rows).toEqual([SERVED_SESSION]);
    expect(Object.keys(rows[0] ?? {}).sort()).toEqual(SESSION_KEYS);
    expect(rows[0]).not.toHaveProperty("opening_message");
  });

  it("with a row already in the workspace, the served session joins it with exactly eight keys — DoD-4", async () => {
    serveStart(started("Hello there"), 201);
    const sessions = workspaceWith([EXISTING_SESSION]);

    await sendCharacterComposer(stateWithDraft("Hello there"), sessions, vi.fn<(id: string) => void>());

    const rows = toJS(sessions.sessions);
    const served = rows.find((row) => row.id === SESSION_ID);
    expect(served).toEqual(SERVED_SESSION);
    expect(Object.keys(served ?? {}).sort()).toEqual(SESSION_KEYS);
    expect(rows.find((row) => row.id === EXISTING_SESSION_ID)).toEqual(EXISTING_SESSION);
    expect(rows).toHaveLength(2);
  });

  it("calls notifyFailure not at all — DoD-4", async () => {
    serveStart(started("Hello there"), 201);

    await sendCharacterComposer(stateWithDraft("Hello there"), new SessionsState(), vi.fn<(id: string) => void>());

    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------- DoD-5
describe("the send effect on a failure (R10, D5)", () => {
  const INTERNAL = {
    error: { code: "internal_error", message: "The session ledger is on fire zq-18.", detail: {} },
  };

  it('on a 500 envelope it keeps the draft "Hello there", clears sending and resolves without throwing — DoD-5', async () => {
    serveStart(INTERNAL, 500);
    const state = stateWithDraft("Hello there");

    await expect(
      sendCharacterComposer(state, new SessionsState(), vi.fn<(id: string) => void>()),
    ).resolves.toBeUndefined();

    expect(state.draft).toBe("Hello there");
    expect(state.sending).toBe(false);
  });

  it("on a 500 envelope it calls notifyFailure once with the thrown ApiError and never the callback — DoD-5", async () => {
    serveStart(INTERNAL, 500);
    const onStarted = vi.fn<(id: string) => void>();

    await sendCharacterComposer(stateWithDraft("Hello there"), new SessionsState(), onStarted);

    expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
    const error = notifyFailureSpy.mock.calls[0]?.[0];
    expect(isApiError(error)).toBe(true);
    expect(isApiError(error) ? error.code : null).toBe("internal_error");
    expect(isApiError(error) ? error.status : null).toBe(500);
    expect(onStarted).not.toHaveBeenCalled();
  });

  it("on a 500 envelope the workspace state is unchanged — DoD-5", async () => {
    serveStart(INTERNAL, 500);
    const sessions = workspaceWith([EXISTING_SESSION]);
    const before = snapshot(sessions);

    await sendCharacterComposer(stateWithDraft("Hello there"), sessions, vi.fn<(id: string) => void>());

    expect(snapshot(sessions)).toEqual(before);
    expect(toJS(sessions.sessions)).toEqual([EXISTING_SESSION]);
  });

  it("on a transport failure it keeps the draft, notifies once with the thrown error, skips the callback, leaves the workspace, clears sending and resolves — DoD-5", async () => {
    stubFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    const state = stateWithDraft("Hello there");
    const sessions = workspaceWith([EXISTING_SESSION]);
    const before = snapshot(sessions);
    const onStarted = vi.fn<(id: string) => void>();

    await expect(sendCharacterComposer(state, sessions, onStarted)).resolves.toBeUndefined();

    expect(state.draft).toBe("Hello there");
    expect(state.sending).toBe(false);
    expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
    const error = notifyFailureSpy.mock.calls[0]?.[0];
    expect(isApiError(error)).toBe(true);
    expect(isApiError(error) ? error.code : null).toBe("client_transport_failed");
    expect(onStarted).not.toHaveBeenCalled();
    expect(snapshot(sessions)).toEqual(before);
  });
});

// ---------------------------------------------------------------- DoD-6
describe("no double create (D5)", () => {
  it("while a send is pending, a second send effect call sends no second request — DoD-6", async () => {
    let release: (response: Response) => void = () => undefined;
    const pending = new Promise<Response>((resolve) => {
      release = resolve;
    });
    const mock = stubFetch((input, init) => (isStart(input, init) ? pending : unexpected(input, init)));
    const state = stateWithDraft("Hello there");
    const sessions = new SessionsState();
    const onStarted = vi.fn<(id: string) => void>();

    const first = sendCharacterComposer(state, sessions, onStarted);
    await vi.waitFor(() => {
      expect(mock).toHaveBeenCalledTimes(1);
    });
    expect(state.sending).toBe(true);

    const second = sendCharacterComposer(state, sessions, onStarted);
    await second;
    expect(mock).toHaveBeenCalledTimes(1);

    release(jsonResponse(started("Hello there"), 201));
    await first;

    expect(mock).toHaveBeenCalledTimes(1);
    expect(startCalls(mock)).toBe(1);
    expect(onStarted).toHaveBeenCalledTimes(1);
    expect(toJS(sessions.sessions)).toEqual([SERVED_SESSION]);
  });

  it("a send effect with a blank draft sends nothing — DoD-6", async () => {
    const mock = serveStart(started("x"), 201);
    const onStarted = vi.fn<(id: string) => void>();

    await sendCharacterComposer(stateWithDraft("   "), new SessionsState(), onStarted);

    expect(mock).not.toHaveBeenCalled();
    expect(onStarted).not.toHaveBeenCalled();
  });
});
