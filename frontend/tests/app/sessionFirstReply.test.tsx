// Fast feature 004 — character-page-first-reply: component and router level (DoD-6..DoD-12)
// (docs/plans/fast/004.character-page-first-reply/plan.md). Store-level clauses (DoD-1..DoD-5)
// live in streamFirstReply.test.ts; DoD-13 is the verifier's suite/typecheck gate; DoD-14..16
// are [manual/live] and carry no test.
//
// Expected behaviour comes from the plan's Interface intent and Definition of done plus
// context.md D2 (a one-shot router-state marker on the page composer's push; SessionScreen reads
// it once per session id, then replaces the entry with the same pathname and search and no
// state), D3 (one textless compose — POST …/zone/compose with body {} — only when the zone's last
// non-tool row is the user's; at most once per StreamState, so StrictMode starts one request)
// and the 018 D5 push (Back returns to the character page).
//
// Recognition conventions:
// - The marker is recognised only through the frozen predicate `isFirstReplyState`, and built
//   only through `firstReplyState()` (status.md "## Skeleton").
// - The location and navigation type are observed through a probe rendered inside the router
//   (`useLocation` / `useNavigationType`), never by spying on `useNavigate`.
// - "A replace, history did not grow" is observed as: the navigation type after arrival is
//   REPLACE, and one Back from the session lands on the character-page entry beneath it.
// - The screen's backend is SessionScreen.test.tsx's stub set, by exact pathname; the compose
//   POST is a held SSE body (streamCompose's idiom). The Stop control is the composer's "Stop"
//   button (ComposerStop.test.tsx's name).
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { runInAction } from "mobx";
import { StrictMode, type ChangeEvent, type ReactNode } from "react";
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useNavigationType,
  useParams,
  type InitialEntry,
  type Location,
} from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CharacterComposer } from "../../src/app/CharacterComposer";
import { SessionRoute } from "../../src/app/SessionScreen";
import type { Character } from "../../src/app/charactersApi";
import { CharactersState } from "../../src/app/charactersState";
import type { EnabledModel, ModelRef, SessionConfiguration, Setting } from "../../src/app/configurationApi";
import { firstReplyState, isFirstReplyState } from "../../src/app/firstReply";
import type { Session, StartedSession } from "../../src/app/sessionsApi";
import { SessionsState } from "../../src/app/sessionsState";
import type { Message, MessageRole } from "../../src/app/streamApi";
import { AppProviders } from "../../src/shared/AppProviders";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

// The notes' editor, exactly as SessionScreen.test.tsx stubs it (harness setup, not a contract).
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
        null,
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
type Seen = { method: string; path: string; search: string; rawBody: unknown; signal: AbortSignal | undefined };

// ---------------------------------------------------------------- fixtures
// Every id is a decimal string past Number.MAX_SAFE_INTEGER.
const CHARACTER_ID = "7250000000000000101";
const SESSION_ID = "7270000000000000101";
const OPENING_ID = "7280000000000000101";
const ASSISTANT_ID = "7280000000000000102";
const SERVER_ID = "7250000000000000401";

const CHARACTER_PATH = `/characters/${CHARACTER_ID}`;
const SESSION_ROUTE = `/sessions/${SESSION_ID}`;
const START_PATH = `/api/characters/${CHARACTER_ID}/sessions`;
const SESSION_PATH = `/api/sessions/${SESSION_ID}`;
const ENTRIES_PATH = `${SESSION_PATH}/entries`;
const ZONE_PATH = `${SESSION_PATH}/zone`;
const COMPOSE_PATH = `${SESSION_PATH}/zone/compose`;
const MEMO_CHAIN_PATH = `${SESSION_PATH}/memo-chain`;
const CONFIGURATION_PATH = `${SESSION_PATH}/configuration`;
const MODELS_PATH = "/api/models";

const STAMP = "2026-10-07T09:00:00.000000+00:00";
const OPENING_TEXT = "The lighthouse keeper waits at the door.";
const ASSISTANT_TEXT = "The door creaks open onto the gale.";
const CHARACTER_PAGE_TEXT = "character page probe";

const CHARACTER: Character = {
  id: CHARACTER_ID,
  name: "Aria",
  sheet: "A scribe who never finishes a sentence.",
  archived_at: null,
  created_at: STAMP,
  updated_at: STAMP,
};

const SESSION: Session = {
  id: SESSION_ID,
  character_id: CHARACTER_ID,
  setup_id: null,
  setup_name: null,
  archived_at: null,
  last_used_at: STAMP,
  created_at: STAMP,
  updated_at: STAMP,
};

function zoneRow(id: string, role: MessageRole, text: string): Message {
  return { id, session_id: SESSION_ID, role, kind: null, text, settled_at: null, created_at: STAMP, updated_at: STAMP };
}

const OPENING_ROW = zoneRow(OPENING_ID, "user", OPENING_TEXT);
const ASSISTANT_ROW = zoneRow(ASSISTANT_ID, "assistant", ASSISTANT_TEXT);

function started(text: string): StartedSession {
  return { ...SESSION, opening_message: zoneRow(OPENING_ID, "user", text) };
}

const MODEL: EnabledModel = { server_id: SERVER_ID, server_name: "S1", model_name: "A" };
const MODEL_REF: ModelRef = { server_id: SERVER_ID, model_name: "A" };

function emptyTextSetting(): Setting<string> {
  return { session: null, inherited: null, inherited_level: null, value: null, level: null };
}

function defaultToolSetting(): Setting<boolean> {
  return { session: null, inherited: true, inherited_level: "default", value: true, level: "default" };
}

function sessionConfiguration(): SessionConfiguration {
  return {
    model: { ...MODEL_REF },
    system_prompt: emptyTextSetting(),
    tool_memo_search: defaultToolSetting(),
    tool_session_search: defaultToolSetting(),
    tool_web_search: defaultToolSetting(),
    rp_language: emptyTextSetting(),
    preferred_language: emptyTextSetting(),
  };
}

beforeEach(() => {
  notifyFailureSpy.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- fetch harness
const enc = new TextEncoder();

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: "ql-77 went wrong.", detail: {} } }, status);
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function abortError(): DOMException {
  return new DOMException("The operation was aborted.", "AbortError");
}

function stubBackend(handler: (request: Seen) => Response | Promise<Response>) {
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>(async (input, init) => {
    const url = requestUrl(input);
    const signal = init?.signal ?? (input instanceof Request ? input.signal : undefined) ?? undefined;
    const request: Seen = {
      method: requestMethod(input, init),
      path: url.pathname,
      search: url.search,
      rawBody: init?.body,
      signal,
    };
    calls.push(request);
    if (signal?.aborted === true) throw abortError();
    return handler(request);
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

type HeldSse = {
  response: Response;
  push: (payload: unknown) => void;
  close: () => void;
};

function heldSse(signal: AbortSignal | undefined): HeldSse {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  let ended = false;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  const fail = (): void => {
    if (ended) return;
    ended = true;
    try {
      controller.error(abortError());
    } catch {
      // already cancelled by the reader
    }
  };
  if (signal !== undefined) {
    if (signal.aborted) fail();
    else signal.addEventListener("abort", fail, { once: true });
  }
  return {
    response: new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } }),
    push(payload) {
      if (ended) return;
      try {
        controller.enqueue(enc.encode(`data: ${JSON.stringify(payload)}\n\n`));
      } catch {
        // already cancelled by the reader
      }
    },
    close() {
      if (ended) return;
      ended = true;
      try {
        controller.close();
      } catch {
        // already cancelled by the reader
      }
    },
  };
}

/**
 * The whole session screen's backend, by exact pathname: the session, an empty record, the
 * given zone (served on every read), an empty memo chain, a usable configuration and model, and
 * a held SSE body for every compose POST. Everything else 404s.
 */
function serveScreen(zone: Message[]) {
  const streams: HeldSse[] = [];
  const backend = stubBackend((request) => {
    if (request.method === "POST" && request.path === COMPOSE_PATH) {
      const held = heldSse(request.signal);
      streams.push(held);
      return held.response;
    }
    if (request.method !== "GET") return envelope("unexpected_request", 404);
    if (request.path === SESSION_PATH) return jsonResponse(SESSION, 200);
    if (request.path === ENTRIES_PATH) return jsonResponse({ entries: [] }, 200);
    if (request.path === ZONE_PATH) return jsonResponse({ messages: zone }, 200);
    if (request.path === MEMO_CHAIN_PATH) return jsonResponse({ levels: [] }, 200);
    if (request.path === CONFIGURATION_PATH) return jsonResponse(sessionConfiguration(), 200);
    if (request.path === MODELS_PATH) return jsonResponse({ models: [MODEL] }, 200);
    return envelope("session_not_found", 404);
  });
  const composeCalls = (): Seen[] =>
    backend.calls.filter((call) => call.method === "POST" && call.path === COMPOSE_PATH);
  const zoneReads = (): Seen[] => backend.calls.filter((call) => call.method === "GET" && call.path === ZONE_PATH);
  const nth = (i: number): HeldSse => {
    const held = streams[i];
    if (held === undefined) throw new Error(`no compose stream #${i}`);
    return held;
  };
  return { ...backend, streams, composeCalls, zoneReads, nth };
}

function parsedBody(raw: unknown): unknown {
  expect(typeof raw).toBe("string");
  return JSON.parse(raw as string) as unknown;
}

async function flush(rounds = 8): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => setImmediate(resolve));
    });
  }
}

// ---------------------------------------------------------------- router probe
type ProbeRecord = { location: Location | null; type: string | null };
const probe: ProbeRecord = { location: null, type: null };

beforeEach(() => {
  probe.location = null;
  probe.type = null;
});

function RouterProbe() {
  const location = useLocation();
  const type = useNavigationType();
  const navigate = useNavigate();
  probe.location = location;
  probe.type = type;
  return (
    <div>
      <span data-testid="location">{location.pathname}</span>
      <button type="button" onClick={() => void navigate(-1)}>
        probe back
      </button>
      <button type="button" onClick={() => void navigate(1)}>
        probe forward
      </button>
    </div>
  );
}

function currentLocation(): Location {
  const location = probe.location;
  if (location === null) throw new Error("the router probe has not rendered");
  return location;
}

function newUser(): ReturnType<typeof userEvent.setup> {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

function workspace(): CharactersState {
  const characters = new CharactersState();
  runInAction(() => {
    characters.characters = [{ ...CHARACTER }];
    characters.status = "ready";
  });
  return characters;
}

/** A session-route arrival entry: the given search, with or without the marker as state. */
function sessionArrival(marked: boolean, search = ""): InitialEntry {
  return marked
    ? { pathname: SESSION_ROUTE, search, state: firstReplyState() }
    : { pathname: SESSION_ROUTE, search };
}

/**
 * The session route in the `<main>` landmark, with the character page's entry beneath it in
 * history (so Back is observable) and the router probe outside `<main>`.
 */
function renderSessionArrival(arrival: InitialEntry, options: { strict?: boolean } = {}) {
  const characters = workspace();
  const tree: ReactNode = (
    <AppProviders>
      <MemoryRouter initialEntries={[CHARACTER_PATH, arrival]} initialIndex={1}>
        <main>
          <Routes>
            <Route path="/characters/:id" element={<p>{CHARACTER_PAGE_TEXT}</p>} />
            <Route path="/sessions/:id" element={<SessionRoute characters={characters} storage={null} />} />
          </Routes>
        </main>
        <RouterProbe />
      </MemoryRouter>
    </AppProviders>
  );
  const view = render(options.strict === true ? <StrictMode>{tree}</StrictMode> : tree);
  return { view, tree, characters };
}

function mainRegion(): HTMLElement {
  return screen.getByRole("main");
}

function mainText(): string {
  return mainRegion().textContent ?? "";
}

async function waitForZoneShown(text: string): Promise<void> {
  await waitFor(() => {
    expect(mainText()).toContain(text);
  });
}

function stopButton(): HTMLElement | null {
  return within(mainRegion()).queryByRole("button", { name: "Stop" });
}

// ---------------------------------------------------------------- DoD-6: the marker itself
describe("the first-reply marker (firstReply.ts, D2)", () => {
  it("the predicate recognises the constructor's value — DoD-6", () => {
    expect(isFirstReplyState(firstReplyState())).toBe(true);
  });

  it.each<[string, unknown]>([
    ["null", null],
    ["undefined", undefined],
    ["a string", "firstReply"],
    ["a number", 1],
    ["a boolean", true],
    ["an empty object", {}],
    ["an unrelated object", { from: "search" }],
    ["firstReply false", { firstReply: false }],
    ["firstReply as a string", { firstReply: "true" }],
    ["an array", [true]],
  ])("the predicate answers false for %s — DoD-6", (_label, value) => {
    expect(isFirstReplyState(value)).toBe(false);
  });
});

// ---------------------------------------------------------------- DoD-6: the page composer's push
describe("CharacterComposer — the push carries the marker (US-117.AC-3, D2, 018 D5)", () => {
  function CharacterProbeRoute(props: { sessions: SessionsState }) {
    const params = useParams();
    return <CharacterComposer characterId={params.id ?? ""} sessions={props.sessions} />;
  }

  function renderComposer() {
    const sessions = new SessionsState();
    render(
      <AppProviders>
        <MemoryRouter initialEntries={[CHARACTER_PATH]}>
          <Routes>
            <Route path="/characters/:id" element={<CharacterProbeRoute sessions={sessions} />} />
            <Route path="/sessions/:id" element={<p>session page probe</p>} />
          </Routes>
          <RouterProbe />
        </MemoryRouter>
      </AppProviders>,
    );
  }

  it("sending navigates by push to /sessions/<id> with location.state carrying the first-reply marker, and Back returns to the character page — DoD-6", async () => {
    stubBackend((request) =>
      request.method === "POST" && request.path === START_PATH && request.search === ""
        ? jsonResponse(started("Hello there"), 201)
        : envelope("unexpected_request", 599),
    );
    const user = newUser();
    renderComposer();

    // 033 DoD-13: the composer region is named "New session".
    const region = screen.getByRole("region", { name: "New session" });
    await user.type(within(region).getByRole("textbox", { name: "Composer" }), "Hello there");
    await user.click(within(region).getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(currentLocation().pathname).toBe(SESSION_ROUTE);
    });
    expect(probe.type).toBe("PUSH");
    expect(isFirstReplyState(currentLocation().state)).toBe(true);

    await user.click(screen.getByRole("button", { name: "probe back" }));
    await waitFor(() => {
      expect(currentLocation().pathname).toBe(CHARACTER_PATH);
    });
  });
});

// ---------------------------------------------------------------- DoD-7
describe("arriving with the marker starts the first reply (US-117.AC-3, UC-080 step 5, D3)", () => {
  it("on a zone ending in the user's row: exactly one compose with body {}, the streamed tokens render, and Stop shows while streaming — DoD-7", async () => {
    const backend = serveScreen([OPENING_ROW]);
    renderSessionArrival(sessionArrival(true));

    await waitForZoneShown(OPENING_TEXT);
    await waitFor(() => {
      expect(backend.composeCalls()).toHaveLength(1);
    });
    expect(parsedBody(backend.composeCalls()[0]?.rawBody)).toStrictEqual({});

    backend.nth(0).push({ event: "token", text: "Gulls wheel " });
    backend.nth(0).push({ event: "token", text: "over the harbour." });
    await waitFor(() => {
      expect(mainText()).toContain("Gulls wheel over the harbour.");
    });
    expect(stopButton()).not.toBeNull();

    await flush();
    expect(backend.composeCalls()).toHaveLength(1);

    backend.nth(0).push({ event: "done", message_id: ASSISTANT_ID });
    backend.nth(0).close();
    await flush();
  });
});

// ---------------------------------------------------------------- DoD-8
describe("arriving without the marker composes nothing (D2)", () => {
  it("on the same zone ending in the user's row, no compose request is issued — DoD-8", async () => {
    const backend = serveScreen([OPENING_ROW]);
    renderSessionArrival(sessionArrival(false));

    await waitForZoneShown(OPENING_TEXT);
    await flush(12);

    expect(backend.composeCalls()).toEqual([]);
    expect(stopButton()).toBeNull();
  });
});

// ---------------------------------------------------------------- DoD-9
describe("the marker is consumed by a replace (D2, D3)", () => {
  it("after arrival the location carries no marker, keeps its pathname and search, and was replaced (Back lands on the character page) — DoD-9", async () => {
    const backend = serveScreen([OPENING_ROW]);
    const user = newUser();
    renderSessionArrival(sessionArrival(true));

    await waitForZoneShown(OPENING_TEXT);
    await waitFor(() => {
      expect(isFirstReplyState(currentLocation().state)).toBe(false);
    });
    expect(currentLocation().state ?? null).toBeNull();
    expect(currentLocation().pathname).toBe(SESSION_ROUTE);
    expect(currentLocation().search).toBe("");
    expect(probe.type).toBe("REPLACE");

    await waitFor(() => {
      expect(backend.composeCalls()).toHaveLength(1);
    });
    backend.nth(0).push({ event: "done", message_id: ASSISTANT_ID });
    backend.nth(0).close();
    await flush();

    // One Back from the session lands on the character page: the session entry was replaced,
    // not pushed on top of the marked one.
    await user.click(screen.getByRole("button", { name: "probe back" }));
    await waitFor(() => {
      expect(currentLocation().pathname).toBe(CHARACTER_PATH);
    });
    expect(screen.getByText(CHARACTER_PAGE_TEXT)).toBeInTheDocument();
  });

  it("a subsequent re-render issues no further compose request — DoD-9", async () => {
    const backend = serveScreen([OPENING_ROW]);
    const { view, tree } = renderSessionArrival(sessionArrival(true));

    await waitForZoneShown(OPENING_TEXT);
    await waitFor(() => {
      expect(backend.composeCalls()).toHaveLength(1);
    });
    await waitFor(() => {
      expect(isFirstReplyState(currentLocation().state)).toBe(false);
    });

    view.rerender(tree);
    await flush();
    view.rerender(tree);
    await flush();
    expect(backend.composeCalls()).toHaveLength(1);

    backend.nth(0).push({ event: "done", message_id: ASSISTANT_ID });
    backend.nth(0).close();
    await flush();
    expect(backend.composeCalls()).toHaveLength(1);
  });

  it("a remount of the session route at the cleared location (Back, then Forward) issues no further compose request, even on a zone still ending in the user's row — DoD-9", async () => {
    // The zone is served as the opening row alone on every read, so only the absent marker
    // (not the last-row rule) keeps the remount from composing.
    const backend = serveScreen([OPENING_ROW]);
    const user = newUser();
    renderSessionArrival(sessionArrival(true));

    await waitForZoneShown(OPENING_TEXT);
    await waitFor(() => {
      expect(backend.composeCalls()).toHaveLength(1);
    });
    await waitFor(() => {
      expect(isFirstReplyState(currentLocation().state)).toBe(false);
    });
    backend.nth(0).push({ event: "done", message_id: ASSISTANT_ID });
    backend.nth(0).close();
    await flush();

    await user.click(screen.getByRole("button", { name: "probe back" }));
    await waitFor(() => {
      expect(currentLocation().pathname).toBe(CHARACTER_PATH);
    });
    const zoneReadsBefore = backend.zoneReads().length;

    await user.click(screen.getByRole("button", { name: "probe forward" }));
    await waitFor(() => {
      expect(currentLocation().pathname).toBe(SESSION_ROUTE);
    });
    expect(isFirstReplyState(currentLocation().state)).toBe(false);
    await waitFor(() => {
      expect(backend.zoneReads().length).toBeGreaterThan(zoneReadsBefore);
    });
    await waitForZoneShown(OPENING_TEXT);
    await flush(12);

    expect(backend.composeCalls()).toHaveLength(1);
  });
});

// ---------------------------------------------------------------- DoD-10
describe("StrictMode starts one request (D3)", () => {
  it("under <React.StrictMode>, arrival with the marker yields exactly one compose request — DoD-10", async () => {
    const backend = serveScreen([OPENING_ROW]);
    renderSessionArrival(sessionArrival(true), { strict: true });

    await waitForZoneShown(OPENING_TEXT);
    await waitFor(() => {
      expect(backend.composeCalls()).toHaveLength(1);
    });
    await flush(12);
    expect(backend.composeCalls()).toHaveLength(1);
    expect(parsedBody(backend.composeCalls()[0]?.rawBody)).toStrictEqual({});

    backend.nth(0).push({ event: "done", message_id: ASSISTANT_ID });
    backend.nth(0).close();
    await flush();
    expect(backend.composeCalls()).toHaveLength(1);
  });
});

// ---------------------------------------------------------------- DoD-11
describe("arriving with the marker on an answered zone (D3)", () => {
  it("when the zone's last non-tool row is the assistant's, no compose request is issued — DoD-11", async () => {
    const backend = serveScreen([OPENING_ROW, ASSISTANT_ROW]);
    renderSessionArrival(sessionArrival(true));

    await waitForZoneShown(ASSISTANT_TEXT);
    await flush(12);

    expect(backend.composeCalls()).toEqual([]);
    expect(stopButton()).toBeNull();
  });
});

// ---------------------------------------------------------------- DoD-12
describe("the arrival's search params survive the marker clearing (D2)", () => {
  it("arriving at /sessions/<id>?notes=open&entry=<id> with the marker keeps both params after the marker is cleared — DoD-12", async () => {
    const search = `?notes=open&entry=${OPENING_ID}`;
    const backend = serveScreen([OPENING_ROW]);
    renderSessionArrival(sessionArrival(true, search));

    await waitForZoneShown(OPENING_TEXT);
    await waitFor(() => {
      expect(isFirstReplyState(currentLocation().state)).toBe(false);
    });

    const location = currentLocation();
    expect(location.pathname).toBe(SESSION_ROUTE);
    const params = new URLSearchParams(location.search);
    expect(params.get("notes")).toBe("open");
    expect(params.get("entry")).toBe(OPENING_ID);
    expect([...params.keys()].sort()).toEqual(["entry", "notes"]);

    await waitFor(() => {
      expect(backend.composeCalls()).toHaveLength(1);
    });
    backend.nth(0).push({ event: "done", message_id: ASSISTANT_ID });
    backend.nth(0).close();
    await flush();
  });
});
