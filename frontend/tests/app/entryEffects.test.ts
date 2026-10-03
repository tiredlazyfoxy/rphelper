// Feature 014, step 004 — the settled-entry edit effect and the copy-out effect (DoD-1..DoD-12).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done plus
// context.md's D8, D9, D10, "Never optimistic, narrowed to the row", "Copy changes nothing",
// "Notifications", "Test conventions", and 004.context.md ("Re-reads per outcome", "The
// fallback, concretely", "Test seeding"):
//   - editEntry: blank / unchanged → no request, true; otherwise PATCH with the text verbatim;
//     a settled served row replaces that one entry (no re-read); a non-settled served row
//     re-reads entries + zone; a failure notifies, re-reads the entries, resolves false;
//     never sets busy; writes / notifies nothing once aborted;
//   - copyAsPlainText: toPlainText, then navigator.clipboard.writeText, or — when the clipboard
//     API is absent — a transient textarea + document.execCommand("copy"), removed afterwards
//     with focus restored; failures notify and resolve false; no request, no success notice.
import { runInAction, toJS } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { copyAsPlainText } from "../../src/app/copyOut";
import type { Message, MessageKind } from "../../src/app/streamApi";
import { StreamState, chooseKind, editEntry, effectiveKind } from "../../src/app/streamState";
import { ApiError } from "../../src/shared/apiError";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; body: unknown };
type Route = (request: Seen) => Response | Promise<Response>;

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "s1";
const ENTRIES_PATH = `/api/sessions/${SESSION_ID}/entries`;
const ZONE_PATH = `/api/sessions/${SESSION_ID}/zone`;
const GET_ENTRIES = `GET ${ENTRIES_PATH}`;
const GET_ZONE = `GET ${ZONE_PATH}`;
const patchMessage = (id: string): string => `PATCH /api/messages/${id}`;

const STAMP = "2026-05-10T09:00:00.000000+00:00";
const LATER = "2026-05-10T09:05:00.000000+00:00";

let nextId = 500;
function freshId(): string {
  nextId += 1;
  return `7360000000000000${String(nextId).padStart(3, "0")}`;
}

/** A settled entry with all eight keys. */
function entry(kind: MessageKind, text = `entry text ${kind}`, id = freshId()): Message {
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

/** A zone row with all eight keys: `kind` and `settled_at` null. */
function zoneRow(text: string, id = freshId()): Message {
  return {
    id,
    session_id: SESSION_ID,
    role: "user",
    kind: null,
    text,
    settled_at: null,
    created_at: STAMP,
    updated_at: STAMP,
  };
}

/** The served row of a successful settled edit: same row, new text, later updated_at. */
function editedOf(original: Message, text: string): Message {
  return { ...original, text, updated_at: LATER };
}

type Seed = {
  entries?: Message[];
  zone?: Message[];
  draft?: string;
};

function seeded(seed: Seed): StreamState {
  const state = new StreamState(SESSION_ID);
  runInAction(() => {
    if (seed.entries !== undefined) state.entries = seed.entries;
    if (seed.zone !== undefined) state.zone = seed.zone;
    if (seed.draft !== undefined) state.draft = seed.draft;
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

// ---------------------------------------------------------------- fetch harness
function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: "ee-04 went wrong.", detail: {} } }, status);
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function requestBody(init?: RequestInit): unknown {
  const raw = init?.body;
  if (typeof raw !== "string") return undefined;
  return JSON.parse(raw) as unknown;
}

function stubFetch(impl: FetchFn) {
  const mock = vi.fn<FetchFn>(impl);
  vi.stubGlobal("fetch", mock);
  return mock;
}

const keyOf = (request: Seen): string => `${request.method} ${request.path}`;

/** A backend keyed on exact "METHOD pathname"; unrouted requests answer a 418 envelope. */
function serve(routes: Record<string, Route>) {
  const calls: Seen[] = [];
  const mock = stubFetch(async (input, init) => {
    const url = requestUrl(input);
    const request: Seen = {
      method: requestMethod(input, init),
      path: url.pathname,
      body: requestBody(init),
    };
    calls.push(request);
    const route = routes[keyOf(request)];
    if (route === undefined) return envelope(`unexpected_${request.method}_${request.path}`, 418);
    return route(request);
  });
  const keys = (): string[] => calls.map(keyOf);
  const bodyOf = (key: string): unknown => calls.find((c) => keyOf(c) === key)?.body;
  return { mock, calls, keys, bodyOf };
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
    await new Promise<void>((resolve) => setImmediate(resolve));
  }
}

const entriesList = (list: Message[]): Route => () => jsonResponse({ entries: list }, 200);
const zoneList = (list: Message[]): Route => () => jsonResponse({ messages: list }, 200);
const ok = (body: unknown): Route => () => jsonResponse(body, 200);
const fails = (code: string, status: number): Route => () => envelope(code, status);

function expectNotifiedOnceWith(code: string): void {
  expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
  const error = notifyFailureSpy.mock.calls[0]?.[0];
  expect(error).toBeInstanceOf(ApiError);
  expect((error as ApiError).code).toBe(code);
}

// ===========================================================================
// editEntry
// ===========================================================================
describe("editEntry — a settled served row replaces that one entry", () => {
  it("on a turn entry PATCHes exactly /api/messages/<id> with {text}, replaces only that entry, makes no GET, resolves true — DoD-1", async () => {
    const before = entry("partner", "Partner opener.");
    const target = entry("turn", "My original answer.");
    const after = entry("decision", "Skip to dusk.");
    const served = editedOf(target, "My revised answer.");
    const backend = serve({
      [patchMessage(target.id)]: ok(served),
      [GET_ENTRIES]: entriesList([entry("turn", "Should not be read.")]),
      [GET_ZONE]: zoneList([zoneRow("Should not be read.")]),
    });
    const state = seeded({ entries: [before, target, after] });

    await expect(editEntry(state, target.id, "My revised answer.")).resolves.toBe(true);

    expect(backend.keys()).toEqual([patchMessage(target.id)]);
    expect(backend.bodyOf(patchMessage(target.id))).toStrictEqual({ text: "My revised answer." });
    expect(toJS(state.entries)).toEqual([before, served, after]);
    expect(toJS(state.entries).map((e) => e.id)).toEqual([before.id, target.id, after.id]);
    expect(state.entries[1]?.kind).toBe("turn");
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  type KindCase = [kind: MessageKind, original: string, edited: string];
  const KINDS: KindCase[] = [
    ["partner", "The partner's block as filed.", "The partner's block, corrected."],
    ["decision", "Skip to dusk.", "Skip to morning."],
  ];

  it.each(KINDS)(
    "on a %s entry PATCHes with {text}, replaces only that entry with the served row of the same kind, no GET, resolves true — DoD-2",
    async (kind, original, edited) => {
      const before = entry("turn", "An earlier turn.");
      const target = entry(kind, original);
      const after = entry("turn", "A later turn.");
      const served = editedOf(target, edited);
      const backend = serve({
        [patchMessage(target.id)]: ok(served),
        [GET_ENTRIES]: entriesList([]),
        [GET_ZONE]: zoneList([]),
      });
      const state = seeded({ entries: [before, target, after] });

      await expect(editEntry(state, target.id, edited)).resolves.toBe(true);

      expect(backend.keys()).toEqual([patchMessage(target.id)]);
      expect(backend.bodyOf(patchMessage(target.id))).toStrictEqual({ text: edited });
      expect(toJS(state.entries)).toEqual([before, served, after]);
      expect(state.entries[1]?.kind).toBe(kind);
      expect(notifyFailureSpy).not.toHaveBeenCalled();
    },
  );

  it("sends the text verbatim — no trimming, no (( )) stripping — DoD-3", async () => {
    const verbatim = "  She ((really)) waits.  ";
    const target = entry("turn", "She waits.");
    const served = editedOf(target, verbatim);
    const backend = serve({ [patchMessage(target.id)]: ok(served) });
    const state = seeded({ entries: [target] });

    await expect(editEntry(state, target.id, verbatim)).resolves.toBe(true);

    expect(backend.keys()).toEqual([patchMessage(target.id)]);
    expect(backend.bodyOf(patchMessage(target.id))).toStrictEqual({ text: verbatim });
  });
});

describe("editEntry — blank or unchanged text", () => {
  it.each([
    ["empty text", ""],
    ["whitespace-only text", "  \n"],
    ["text identical to the held entry's text", "Unchanged entry text."],
  ])("with %s makes no request and resolves true — DoD-4", async (_label, text) => {
    const backend = serve({});
    const other = entry("partner", "Partner block.");
    const target = entry("turn", "Unchanged entry text.");
    const state = seeded({ entries: [other, target] });

    await expect(editEntry(state, target.id, text)).resolves.toBe(true);

    expect(backend.mock).not.toHaveBeenCalled();
    expect(toJS(state.entries)).toEqual([other, target]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

describe("editEntry and the kind override", () => {
  it("a successful edit leaves kindOverride and effectiveKind as chooseKind set them — DoD-5", async () => {
    const partner = entry("partner", "Partner block.");
    const turn = entry("turn", "My last turn.");
    const served = editedOf(turn, "My last turn, edited.");
    serve({ [patchMessage(turn.id)]: ok(served) });
    const state = seeded({ entries: [partner, turn] });
    chooseKind(state, "turn");
    expect(state.kindOverride).toBe("turn");
    expect(effectiveKind(state)).toBe("turn");

    await expect(editEntry(state, turn.id, "My last turn, edited.")).resolves.toBe(true);

    expect(toJS(state.entries)).toEqual([partner, served]);
    expect(state.kindOverride).toBe("turn");
    expect(effectiveKind(state)).toBe("turn");
  });

  it("the same holds with the override set to partner while editing a partner entry — DoD-5", async () => {
    const turn = entry("turn", "My turn.");
    const partner = entry("partner", "Last partner block.");
    const served = editedOf(partner, "Last partner block, fixed.");
    serve({ [patchMessage(partner.id)]: ok(served) });
    const state = seeded({ entries: [turn, partner] });
    chooseKind(state, "partner");
    const overrideBefore = state.kindOverride;
    const effectiveBefore = effectiveKind(state);
    expect(effectiveBefore).toBe("partner");

    await expect(editEntry(state, partner.id, "Last partner block, fixed.")).resolves.toBe(true);

    expect(state.kindOverride).toBe(overrideBefore);
    expect(effectiveKind(state)).toBe(effectiveBefore);
  });
});

describe("editEntry — failure", () => {
  it("a 409 message_not_editable notifies once with that ApiError, re-reads the entries only, resolves false — DoD-6", async () => {
    const keep = entry("partner", "Kept partner block.");
    const target = entry("turn", "Turn now buried elsewhere.");
    const reread = [keep, entry("turn", "Served after the failure.")];
    const backend = serve({
      [patchMessage(target.id)]: fails("message_not_editable", 409),
      [GET_ENTRIES]: entriesList(reread),
      [GET_ZONE]: zoneList([zoneRow("Should not be read.")]),
    });
    const state = seeded({ entries: [keep, target] });

    await expect(editEntry(state, target.id, "My edit.")).resolves.toBe(false);

    expectNotifiedOnceWith("message_not_editable");
    expect(backend.keys()).toEqual([patchMessage(target.id), GET_ENTRIES]);
    expect(backend.keys()).not.toContain(GET_ZONE);
    expect(toJS(state.entries)).toEqual(reread);
  });
});

describe("editEntry — a non-settled served row", () => {
  it("re-reads both entries and zone, does not write the served row into entries, resolves true, no notifyFailure — DoD-7", async () => {
    const keep = entry("partner", "Partner block.");
    const target = entry("turn", "Turn re-opened in another tab.");
    const served: Message = { ...target, kind: null, settled_at: null, text: "Edited text.", updated_at: LATER };
    const rereadEntries = [keep];
    const rereadZone = [served];
    const backend = serve({
      [patchMessage(target.id)]: ok(served),
      [GET_ENTRIES]: entriesList(rereadEntries),
      [GET_ZONE]: zoneList(rereadZone),
    });
    const state = seeded({ entries: [keep, target], zone: [] });

    await expect(editEntry(state, target.id, "Edited text.")).resolves.toBe(true);

    const keys = backend.keys();
    expect(keys[0]).toBe(patchMessage(target.id));
    expect(keys.slice(1).sort()).toEqual([GET_ENTRIES, GET_ZONE].sort());
    expect(toJS(state.entries)).toEqual(rereadEntries);
    expect(toJS(state.entries).some((e) => e.id === target.id)).toBe(false);
    expect(toJS(state.zone)).toEqual(rereadZone);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

describe("editEntry — abort and busy", () => {
  function written(state: StreamState) {
    return { entries: toJS(state.entries), zone: toJS(state.zone), draft: state.draft };
  }

  it("aborted while the PATCH is pending (fetch rejects) writes nothing, notifies nothing, never rejects — DoD-8", async () => {
    stubFetch(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          const signal = init?.signal;
          signal?.addEventListener("abort", () => {
            reject(signal.reason ?? new DOMException("The operation was aborted.", "AbortError"));
          });
        }),
    );
    const target = entry("turn", "Held turn.");
    const state = seeded({ entries: [entry("partner", "Partner."), target] });
    const before = written(state);
    const controller = new AbortController();

    const running = editEntry(state, target.id, "A changed text.", controller.signal);
    await flush();
    expect(state.busy).toBe(false);
    controller.abort();

    await expect(running).resolves.toBe(false);
    await flush();
    expect(written(state)).toEqual(before);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(state.busy).toBe(false);
  });

  type LateCase = [label: string, late: (target: Message) => Response];
  const LATE: LateCase[] = [
    ["a settled success", (target) => jsonResponse(editedOf(target, "A changed text."), 200)],
    [
      "a non-settled success",
      (target) => jsonResponse({ ...target, kind: null, settled_at: null, text: "A changed text." }, 200),
    ],
    ["a 409 failure", () => envelope("message_not_editable", 409)],
  ];

  it.each(LATE)(
    "whose PATCH answers with %s after the abort writes nothing and notifies nothing — DoD-8",
    async (_label, late) => {
      const answer = deferred<Response>();
      const target = entry("turn", "Held turn.");
      serve({
        [patchMessage(target.id)]: () => answer.promise,
        [GET_ENTRIES]: entriesList([entry("partner", "Late entry.")]),
        [GET_ZONE]: zoneList([zoneRow("Late zone row.")]),
      });
      const state = seeded({ entries: [entry("partner", "Partner."), target], zone: [] });
      const before = written(state);
      const controller = new AbortController();

      const running = editEntry(state, target.id, "A changed text.", controller.signal);
      await flush();
      controller.abort();
      answer.resolve(late(target));

      await expect(running).resolves.toBe(false);
      await flush();
      expect(written(state)).toEqual(before);
      expect(notifyFailureSpy).not.toHaveBeenCalled();
      expect(state.busy).toBe(false);
    },
  );

  type BusyCase = [label: string, answer: (target: Message) => Response];
  const BUSY: BusyCase[] = [
    ["a settled success", (target) => jsonResponse(editedOf(target, "Changed."), 200)],
    ["a non-settled success", (target) => jsonResponse({ ...target, kind: null, settled_at: null, text: "Changed." }, 200)],
    ["a failure", () => envelope("internal_error", 500)],
  ];

  it.each(BUSY)("busy stays false while the PATCH is pending and after %s — DoD-8", async (_label, answerOf) => {
    const answer = deferred<Response>();
    const target = entry("turn", "Held turn.");
    serve({
      [patchMessage(target.id)]: () => answer.promise,
      [GET_ENTRIES]: entriesList([target]),
      [GET_ZONE]: zoneList([]),
    });
    const state = seeded({ entries: [target] });
    expect(state.busy).toBe(false);

    const running = editEntry(state, target.id, "Changed.");
    await flush();
    expect(state.busy).toBe(false);

    answer.resolve(answerOf(target));
    await running;
    await flush();
    expect(state.busy).toBe(false);
  });

  it("busy stays false for a blank edit — DoD-8", async () => {
    serve({});
    const target = entry("turn", "Held turn.");
    const state = seeded({ entries: [target] });

    await editEntry(state, target.id, "   ");

    expect(state.busy).toBe(false);
  });
});

// ===========================================================================
// copyAsPlainText
// ===========================================================================
const COPY_SOURCE = "# Scene\n\n*She smiles* and **waits**.";
const COPY_PLAIN = "Scene\n\nShe smiles and waits.";

// navigator.clipboard and document.execCommand are installed / removed per test and restored.
let clipboardDescriptor: PropertyDescriptor | undefined;
let execCommandDescriptor: PropertyDescriptor | undefined;

beforeEach(() => {
  clipboardDescriptor = Object.getOwnPropertyDescriptor(navigator, "clipboard");
  execCommandDescriptor = Object.getOwnPropertyDescriptor(document, "execCommand");
});

afterEach(() => {
  if (clipboardDescriptor !== undefined) {
    Object.defineProperty(navigator, "clipboard", clipboardDescriptor);
  } else {
    delete (navigator as unknown as Record<string, unknown>).clipboard;
  }
  if (execCommandDescriptor !== undefined) {
    Object.defineProperty(document, "execCommand", execCommandDescriptor);
  } else {
    delete (document as unknown as Record<string, unknown>).execCommand;
  }
  for (const node of Array.from(document.body.childNodes)) node.remove();
});

function installClipboard(writeText: (text: string) => Promise<void>): void {
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
}

function removeClipboard(): void {
  delete (navigator as unknown as Record<string, unknown>).clipboard;
  if ("clipboard" in navigator && (navigator as unknown as { clipboard?: unknown }).clipboard !== undefined) {
    Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
  }
}

function stubExecCommand(impl: (command: string) => boolean) {
  const mock = vi.fn<(command: string, showUI?: boolean, value?: string) => boolean>((command) => impl(command));
  Object.defineProperty(document, "execCommand", { value: mock, configurable: true, writable: true });
  return mock;
}

function textareasInDocument(): HTMLTextAreaElement[] {
  return Array.from(document.querySelectorAll("textarea"));
}

function focusedButton(): HTMLButtonElement {
  const button = document.createElement("button");
  button.textContent = "Copy as plain text";
  document.body.appendChild(button);
  button.focus();
  expect(document.activeElement).toBe(button);
  return button;
}

describe("copyAsPlainText — the clipboard API", () => {
  it("writes exactly the plain text, resolves true, makes no fetch call, notifies nothing — DoD-9", async () => {
    const fetchMock = stubFetch(async () => envelope("unexpected_request", 418));
    const writeText = vi.fn<(text: string) => Promise<void>>(() => Promise.resolve());
    installClipboard(writeText);

    await expect(copyAsPlainText(COPY_SOURCE)).resolves.toBe(true);

    expect(writeText).toHaveBeenCalledTimes(1);
    expect(writeText).toHaveBeenCalledWith(COPY_PLAIN);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("a writeText rejection notifies once with the rejection value and resolves false (does not reject) — DoD-10", async () => {
    stubFetch(async () => envelope("unexpected_request", 418));
    const denied = new Error("Clipboard write denied.");
    const writeText = vi.fn<(text: string) => Promise<void>>(() => Promise.reject(denied));
    installClipboard(writeText);

    await expect(copyAsPlainText(COPY_SOURCE)).resolves.toBe(false);

    expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
    expect(notifyFailureSpy.mock.calls[0]?.[0]).toBe(denied);
  });
});

describe("copyAsPlainText — the insecure-origin fallback", () => {
  it("execCommand(\"copy\") sees an attached textarea holding exactly the plain text; afterwards it is gone, focus restored, true — DoD-11", async () => {
    stubFetch(async () => envelope("unexpected_request", 418));
    removeClipboard();
    const button = focusedButton();
    const seenAtCopy: { attached: boolean; value: string }[] = [];
    const execCommand = stubExecCommand((command) => {
      if (command === "copy") {
        for (const area of textareasInDocument()) {
          seenAtCopy.push({ attached: area.isConnected, value: area.value });
        }
      }
      return true;
    });
    expect(textareasInDocument()).toHaveLength(0);

    await expect(copyAsPlainText(COPY_SOURCE)).resolves.toBe(true);

    expect(execCommand).toHaveBeenCalledWith("copy");
    expect(seenAtCopy).toEqual([{ attached: true, value: COPY_PLAIN }]);
    expect(textareasInDocument()).toHaveLength(0);
    expect(document.activeElement).toBe(button);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("execCommand returning false notifies once, removes the textarea, resolves false — DoD-12", async () => {
    stubFetch(async () => envelope("unexpected_request", 418));
    removeClipboard();
    focusedButton();
    let attachedAtCopy = 0;
    stubExecCommand((command) => {
      if (command === "copy") attachedAtCopy = textareasInDocument().length;
      return false;
    });

    await expect(copyAsPlainText(COPY_SOURCE)).resolves.toBe(false);

    expect(attachedAtCopy).toBe(1);
    expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
    expect(textareasInDocument()).toHaveLength(0);
  });

  it("execCommand throwing notifies once with the thrown value, removes the textarea, resolves false — DoD-12", async () => {
    stubFetch(async () => envelope("unexpected_request", 418));
    removeClipboard();
    focusedButton();
    const thrown = new Error("Copy command unsupported.");
    let attachedAtCopy = 0;
    stubExecCommand((command) => {
      if (command === "copy") attachedAtCopy = textareasInDocument().length;
      throw thrown;
    });

    await expect(copyAsPlainText(COPY_SOURCE)).resolves.toBe(false);

    expect(attachedAtCopy).toBe(1);
    expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
    expect(notifyFailureSpy.mock.calls[0]?.[0]).toBe(thrown);
    expect(textareasInDocument()).toHaveLength(0);
  });
});
