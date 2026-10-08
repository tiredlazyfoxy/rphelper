// Feature 023, step 005 — the translate flicker on settled partner entries
// (DoD-1..DoD-7, DoD-9).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done plus
// context.md's D4 (while pending the flicker is the cancel control: the original stays, the
// flicker un-flicks, and nothing is notified, because a stop is not a failure), D13 (one
// state per mount, the per-mount cache, a cached flick makes no request), D14 (after an edit
// settles the row is invalidated, whatever the outcome), D15 (one IconButton whose *label*
// carries the state, no aria-pressed), the "Wire contract", and 005.context.md's "UI strings"
// table and "Test shape". The colour is deliberately never asserted (005.context.md), and the
// failure prose comes from the server and is never asserted — only the ApiError code.
// Never from the implementation.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { runInAction } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StreamRecord } from "../../src/app/StreamRecord";
import type { Message, MessageKind } from "../../src/app/streamApi";
import { StreamState } from "../../src/app/streamState";
import type { Translation } from "../../src/app/translationApi";
import { TranslationState } from "../../src/app/translationState";
import { ApiError } from "../../src/shared/apiError";
import { AppProviders } from "../../src/shared/AppProviders";

const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- the spec's names
const RECORD_NAME = "Settled record";
const SHOW_TRANSLATION = "Show translation";
const CANCEL_TRANSLATION = "Cancel translation";
const SHOW_ORIGINAL = "Show original";
/** The three labels of the one flicker control (005.context.md "UI strings"). */
const FLICKER_LABELS = [SHOW_TRANSLATION, CANCEL_TRANSLATION, SHOW_ORIGINAL];

const EDIT_NAME = "Edit entry";
const EDITOR_NAME = "Edit entry text";
const COPY_NAME = "Copy as plain text";

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "7250000000000000042";
// All three ids are > Number.MAX_SAFE_INTEGER: a silent numeric coercion would change them.
const PARTNER_ID = "7250000000000000201";
const TURN_ID = "7250000000000000202";
const DECISION_ID = "7250000000000000203";

const messagePath = (id: string): string => `/api/messages/${id}`;
const translationPath = (id: string): string => `/api/messages/${id}/translation`;
const postTranslation = (id: string): string => `POST ${translationPath(id)}`;
const patchMessage = (id: string): string => `PATCH ${messagePath(id)}`;

const ORIGINAL = "They wave.";
const TURN_TEXT = "I wave back.";
const DECISION_TEXT = "((skip))";
const TRANSLATED = "Они машут.";
const EDITED = "They bow.";
const RETRANSLATED = "Они кланяются.";

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

/** The served row of a successful settled edit: same settled partner row, new text. */
function served(original: Message, text: string): Message {
  return { ...original, text, updated_at: LATER };
}

/** The record of the DoD: a partner block, a turn and a decision, in that order. */
function threeEntries(): Message[] {
  return [
    entry(PARTNER_ID, "partner", ORIGINAL),
    entry(TURN_ID, "turn", TURN_TEXT),
    entry(DECISION_ID, "decision", DECISION_TEXT),
  ];
}

/** The wire payload, with all four keys (context.md "Wire contract"). */
function translation(messageId: string, text: string, cached = false): Translation {
  return { message_id: messageId, target_language: "Russian", text, cached };
}

function seeded(entries: Message[]): StreamState {
  const state = new StreamState(SESSION_ID);
  runInAction(() => {
    state.entries = entries;
    state.zone = [];
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

// ---------------------------------------------------------------- fetch harness
function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** The server's failure envelope; only its `code` is ever asserted. */
function envelopeBody(code: string, messageId: string): unknown {
  return {
    error: {
      code,
      message: "The translation failed. Showing the original.",
      detail: { message_id: messageId },
    },
  };
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
  readonly path: string;
  readonly body: string | null;
  readonly signal: AbortSignal | undefined;
  /** Answer this one call (only meaningful for a call the router left deferred). */
  respond: (body: unknown, status?: number) => void;
};

/** Named so `ReturnType` can give the mock a type without an instantiation expression. */
function fetchMock(impl: FetchFn) {
  return vi.fn<FetchFn>(impl);
}
type FetchMock = ReturnType<typeof fetchMock>;

type Answer = { body: unknown; status?: number };
type Router = (method: string, path: string) => Answer | undefined;

type Backend = {
  readonly mock: FetchMock;
  readonly calls: Call[];
  keys: () => string[];
  call: (index: number) => Call;
  count: (key: string) => number;
};

/**
 * A fetch stub keyed on exact method + pathname (context.md "Test conventions"), with one
 * deferred promise per call: a route the `router` answers resolves at once, anything else
 * stays pending until the test responds, which is how "while it is unresolved" is observable
 * (005.context.md "Test shape"). A pending call rejects with a `DOMException` named
 * "AbortError" as soon as its signal aborts, as the platform does.
 */
function stubFetch(router: Router = () => undefined): Backend {
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
      path,
      body: typeof init?.body === "string" ? init.body : null,
      signal,
      respond: (body, status = 200) => settle(jsonResponse(body, status)),
    });
    const answer = router(method, path);
    if (answer !== undefined) settle(jsonResponse(answer.body, answer.status ?? 200));
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

/** Answers PATCH /api/messages/<id> with the served row; leaves the translate POST deferred. */
function patchRouter(row: Message): Router {
  return (method, path) =>
    method === "PATCH" && path === messagePath(row.id) ? { body: row, status: 200 } : undefined;
}

async function flush(rounds = 6): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => setImmediate(resolve));
    });
  }
}

// ---------------------------------------------------------------- render + queries
function renderRecord(state: StreamState, translations?: TranslationState): void {
  render(
    <AppProviders>
      <StreamRecord state={state} translations={translations} />
    </AppProviders>,
  );
}

function recordItems(): HTMLElement[] {
  return within(screen.getByRole("list", { name: RECORD_NAME })).getAllByRole("listitem");
}

function item(index: number): HTMLElement {
  return recordItems()[index] as HTMLElement;
}

/** The partner entry's listitem: index 0 of the DoD's record. */
function partnerItem(): HTMLElement {
  return item(0);
}

function flicker(label: string): HTMLElement {
  return within(partnerItem()).getByRole("button", { name: label });
}

/**
 * One control in the partner entry, whose single label carries the state (D15): the given
 * label is present exactly once and neither other label is rendered at all.
 */
function expectFlickerReads(label: string): void {
  const scoped = within(partnerItem());
  expect(scoped.getAllByRole("button", { name: label })).toHaveLength(1);
  for (const other of FLICKER_LABELS.filter((candidate) => candidate !== label)) {
    // queryByRole also finds disabled buttons, so null means it is not rendered.
    expect(scoped.queryByRole("button", { name: other })).toBeNull();
  }
}

function expectNoFlickerIn(listItem: HTMLElement): void {
  for (const label of FLICKER_LABELS) {
    expect(within(listItem).queryByRole("button", { name: label })).toBeNull();
    expect(within(listItem).queryByLabelText(label)).toBeNull();
  }
}

function newUser(): ReturnType<typeof userEvent.setup> {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

async function press(label: string): Promise<void> {
  const user = newUser();
  await user.click(flicker(label));
  await flush();
}

/** Open the partner entry's in-place editor and return its textbox. */
async function openPartnerEditor(): Promise<HTMLElement> {
  const user = newUser();
  await user.click(within(partnerItem()).getByRole("button", { name: EDIT_NAME }));
  return screen.getByRole("textbox", { name: EDITOR_NAME });
}

// ===========================================================================
// DoD-1 — the flicker is a partner-entry control only
// ===========================================================================
describe("the flicker sits on partner entries only (US-131, brief Out)", () => {
  it('the partner entry offers "Show translation" and the turn and decision entries offer none — DoD-1', () => {
    stubFetch();
    renderRecord(seeded(threeEntries()), new TranslationState());

    const items = recordItems();
    expect(items).toHaveLength(3);

    expect(within(items[0] as HTMLElement).getAllByRole("button", { name: SHOW_TRANSLATION })).toHaveLength(1);
    expectNoFlickerIn(items[1] as HTMLElement);
    expectNoFlickerIn(items[2] as HTMLElement);

    expect(screen.getAllByRole("button", { name: SHOW_TRANSLATION })).toHaveLength(1);
  });

  it("a fresh partner entry starts on the original, with its stored text showing — DoD-1", () => {
    stubFetch();
    renderRecord(seeded(threeEntries()), new TranslationState());

    expectFlickerReads(SHOW_TRANSLATION);
    expect(partnerItem().textContent).toContain(ORIGINAL);
  });
});

// ===========================================================================
// DoD-2 — the first flick
// ===========================================================================
describe("the first flick translates the entry (US-045.AC-1)", () => {
  it("issues exactly one POST to that row's translation path — DoD-2", async () => {
    const backend = stubFetch();
    renderRecord(seeded(threeEntries()), new TranslationState());

    await press(SHOW_TRANSLATION);

    expect(backend.keys()).toEqual([postTranslation(PARTNER_ID)]);
  });

  it('while the request is unresolved the control reads "Cancel translation" and the body still shows the original — DoD-2', async () => {
    stubFetch();
    renderRecord(seeded(threeEntries()), new TranslationState());

    await press(SHOW_TRANSLATION);

    expectFlickerReads(CANCEL_TRANSLATION);
    expect(partnerItem().textContent).toContain(ORIGINAL);
    expect(partnerItem().textContent).not.toContain(TRANSLATED);
  });

  it('once it answers the body shows the translation, the original is gone and the control reads "Show original" — DoD-2', async () => {
    const backend = stubFetch();
    renderRecord(seeded(threeEntries()), new TranslationState());

    await press(SHOW_TRANSLATION);
    backend.call(0).respond(translation(PARTNER_ID, TRANSLATED));
    await flush();

    expect(partnerItem().textContent).toContain(TRANSLATED);
    expect(partnerItem().textContent).not.toContain(ORIGINAL);
    expectFlickerReads(SHOW_ORIGINAL);
    expect(backend.keys()).toEqual([postTranslation(PARTNER_ID)]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("the other entries are untouched by a partner translation — DoD-2", async () => {
    const backend = stubFetch();
    renderRecord(seeded(threeEntries()), new TranslationState());

    await press(SHOW_TRANSLATION);
    backend.call(0).respond(translation(PARTNER_ID, TRANSLATED));
    await flush();

    expect(item(1).textContent).toContain(TURN_TEXT);
    expect(item(1).textContent).not.toContain(TRANSLATED);
    expect(item(2).textContent).toContain(DECISION_TEXT);
    expect(item(2).textContent).not.toContain(TRANSLATED);
  });
});

// ===========================================================================
// DoD-3 — flicking back, and the second flick's cache
// ===========================================================================
describe("flicking back and forth makes no further request (UC-040, US-046.AC-1)", () => {
  it('"Show original" shows the stored text again with no request — DoD-3', async () => {
    const backend = stubFetch();
    renderRecord(seeded(threeEntries()), new TranslationState());

    await press(SHOW_TRANSLATION);
    backend.call(0).respond(translation(PARTNER_ID, TRANSLATED));
    await flush();

    await press(SHOW_ORIGINAL);

    expect(partnerItem().textContent).toContain(ORIGINAL);
    expect(partnerItem().textContent).not.toContain(TRANSLATED);
    expectFlickerReads(SHOW_TRANSLATION);
    expect(backend.keys()).toEqual([postTranslation(PARTNER_ID)]);
  });

  it("flicking again shows the cached translation, with one POST in total — DoD-3", async () => {
    const backend = stubFetch();
    renderRecord(seeded(threeEntries()), new TranslationState());

    await press(SHOW_TRANSLATION);
    backend.call(0).respond(translation(PARTNER_ID, TRANSLATED));
    await flush();
    await press(SHOW_ORIGINAL);

    await press(SHOW_TRANSLATION);

    expect(partnerItem().textContent).toContain(TRANSLATED);
    expect(partnerItem().textContent).not.toContain(ORIGINAL);
    expectFlickerReads(SHOW_ORIGINAL);
    expect(backend.count(postTranslation(PARTNER_ID))).toBe(1);
    expect(backend.keys()).toEqual([postTranslation(PARTNER_ID)]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ===========================================================================
// DoD-4 — a failed translation
// ===========================================================================
describe("a failed translation leaves the original showing (US-048.AC-1, US-048.AC-2)", () => {
  const failing: Router = (method, path) =>
    method === "POST" && path === translationPath(PARTNER_ID)
      ? { body: envelopeBody("translation_failed", PARTNER_ID), status: 502 }
      : undefined;

  it('a 502 translation_failed keeps the original and the control reads "Show translation" — DoD-4', async () => {
    stubFetch(failing);
    renderRecord(seeded(threeEntries()), new TranslationState());

    await press(SHOW_TRANSLATION);

    expect(partnerItem().textContent).toContain(ORIGINAL);
    expectFlickerReads(SHOW_TRANSLATION);
  });

  it("the failure is notified once, with an ApiError of code translation_failed — DoD-4", async () => {
    stubFetch(failing);
    renderRecord(seeded(threeEntries()), new TranslationState());

    await press(SHOW_TRANSLATION);

    expect(notifyFailureSpy).toHaveBeenCalledTimes(1);
    const notified = notifyFailureSpy.mock.calls[0]?.[0];
    expect(notified).toBeInstanceOf(ApiError);
    // The code only: the prose comes from the server and is never asserted.
    expect((notified as ApiError).code).toBe("translation_failed");
  });

  it("pressing it again after the failure issues a second POST — DoD-4", async () => {
    const backend = stubFetch(failing);
    renderRecord(seeded(threeEntries()), new TranslationState());

    await press(SHOW_TRANSLATION);
    expect(backend.count(postTranslation(PARTNER_ID))).toBe(1);

    await press(SHOW_TRANSLATION);

    expect(backend.count(postTranslation(PARTNER_ID))).toBe(2);
    expect(backend.keys()).toEqual([postTranslation(PARTNER_ID), postTranslation(PARTNER_ID)]);
  });
});

// ===========================================================================
// DoD-5 — the flicker cancels a pending translation (D4)
// ===========================================================================
describe("the flicker cancels while pending (US-133.AC-2 user-visible half, D4)", () => {
  it('"Cancel translation" aborts the request\'s signal and leaves the original showing — DoD-5', async () => {
    const backend = stubFetch();
    renderRecord(seeded(threeEntries()), new TranslationState());

    await press(SHOW_TRANSLATION);
    expect(backend.call(0).signal?.aborted).toBe(false);

    await press(CANCEL_TRANSLATION);

    expect(backend.call(0).signal?.aborted).toBe(true);
    expect(partnerItem().textContent).toContain(ORIGINAL);
    expect(partnerItem().textContent).not.toContain(TRANSLATED);
    expectFlickerReads(SHOW_TRANSLATION);
  });

  it("cancelling notifies nothing, because a stop is not a failure, and issues no second request — DoD-5", async () => {
    const backend = stubFetch();
    renderRecord(seeded(threeEntries()), new TranslationState());

    await press(SHOW_TRANSLATION);
    await press(CANCEL_TRANSLATION);

    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(backend.keys()).toEqual([postTranslation(PARTNER_ID)]);
  });
});

// ===========================================================================
// DoD-6 — editing a translated partner entry (US-111, D14)
// ===========================================================================
describe("editing a partner entry discards its translation (US-111.AC-1 client half, US-111.AC-2, D14)", () => {
  /** Flick the partner entry and let it answer, so its translation is showing. */
  async function showTranslation(backend: Backend): Promise<void> {
    await press(SHOW_TRANSLATION);
    backend.call(0).respond(translation(PARTNER_ID, TRANSLATED));
    await flush();
    expect(partnerItem().textContent).toContain(TRANSLATED);
  }

  it('with the translation showing, "Edit entry" opens the editor holding the original — DoD-6', async () => {
    const partner = threeEntries()[0] as Message;
    const backend = stubFetch(patchRouter(served(partner, EDITED)));
    renderRecord(seeded(threeEntries()), new TranslationState());

    await showTranslation(backend);
    const textbox = await openPartnerEditor();

    expect(textbox).toHaveValue(ORIGINAL);
  });

  it("typing the new text and blurring issues the PATCH for that row — DoD-6", async () => {
    const partner = threeEntries()[0] as Message;
    const backend = stubFetch(patchRouter(served(partner, EDITED)));
    renderRecord(seeded(threeEntries()), new TranslationState());

    await showTranslation(backend);
    const textbox = await openPartnerEditor();
    fireEvent.change(textbox, { target: { value: EDITED } });
    fireEvent.blur(textbox);
    await flush();

    expect(backend.count(patchMessage(PARTNER_ID))).toBe(1);
    const patch = backend.calls.find((call) => call.key === patchMessage(PARTNER_ID));
    expect(JSON.parse(patch?.body ?? "null")).toEqual({ text: EDITED });
  });

  it('after the edit the entry shows the edited text, not the translation, and the control reads "Show translation" — DoD-6', async () => {
    const partner = threeEntries()[0] as Message;
    const backend = stubFetch(patchRouter(served(partner, EDITED)));
    renderRecord(seeded(threeEntries()), new TranslationState());

    await showTranslation(backend);
    const textbox = await openPartnerEditor();
    fireEvent.change(textbox, { target: { value: EDITED } });
    fireEvent.blur(textbox);
    await waitFor(() => {
      expect(screen.queryByRole("textbox", { name: EDITOR_NAME })).toBeNull();
    });
    await flush();

    expect(partnerItem().textContent).toContain(EDITED);
    expect(partnerItem().textContent).not.toContain(TRANSLATED);
    expectFlickerReads(SHOW_TRANSLATION);
  });

  it("the next flick after the edit issues a new POST, whose answer is shown — DoD-6", async () => {
    const partner = threeEntries()[0] as Message;
    const backend = stubFetch(patchRouter(served(partner, EDITED)));
    renderRecord(seeded(threeEntries()), new TranslationState());

    await showTranslation(backend);
    const textbox = await openPartnerEditor();
    fireEvent.change(textbox, { target: { value: EDITED } });
    fireEvent.blur(textbox);
    await waitFor(() => {
      expect(screen.queryByRole("textbox", { name: EDITOR_NAME })).toBeNull();
    });
    await flush();
    expect(backend.count(postTranslation(PARTNER_ID))).toBe(1);

    await press(SHOW_TRANSLATION);

    expect(backend.count(postTranslation(PARTNER_ID))).toBe(2);
    const second = backend.calls.filter((call) => call.key === postTranslation(PARTNER_ID))[1];
    second?.respond(translation(PARTNER_ID, RETRANSLATED));
    await flush();

    expect(partnerItem().textContent).toContain(RETRANSLATED);
    expect(partnerItem().textContent).not.toContain(EDITED);
    expectFlickerReads(SHOW_ORIGINAL);
  });
});

// ===========================================================================
// DoD-7 — the prop is optional
// ===========================================================================
describe("without a translation state there is no flicker (D13, optional prop)", () => {
  it("a partner entry rendered with no translation state shows no flicker control — DoD-7", () => {
    stubFetch();
    renderRecord(seeded(threeEntries()));

    expectNoFlickerIn(partnerItem());
    for (const label of FLICKER_LABELS) {
      expect(screen.queryByRole("button", { name: label })).toBeNull();
    }
  });

  it('"Edit entry" stays available on that partner entry — DoD-7', async () => {
    const partner = threeEntries()[0] as Message;
    stubFetch(patchRouter(served(partner, EDITED)));
    renderRecord(seeded(threeEntries()));

    expect(within(partnerItem()).getAllByRole("button", { name: EDIT_NAME })).toHaveLength(1);

    const textbox = await openPartnerEditor();
    expect(textbox).toHaveValue(ORIGINAL);
  });
});

// ===========================================================================
// DoD-9 — 013 / 014 behaviour survives the new control
// ===========================================================================
describe("the delivered record behaviour is unchanged by the flicker (013 / 014 regressions)", () => {
  it("the partner entry keeps its Partner heading, its blockquote body and Edit entry, and offers no Copy — DoD-9", () => {
    stubFetch();
    renderRecord(seeded(threeEntries()), new TranslationState());

    const scoped = within(partnerItem());
    expect(scoped.getByText("Partner")).toBeInTheDocument();
    expect(scoped.getByText(ORIGINAL).closest("blockquote")).not.toBeNull();
    expect(scoped.getAllByRole("button", { name: EDIT_NAME })).toHaveLength(1);
    expect(scoped.queryByRole("button", { name: COPY_NAME })).toBeNull();
  });

  it("the turn and decision entries keep their own controls and bodies — DoD-9", () => {
    stubFetch();
    renderRecord(seeded(threeEntries()), new TranslationState());

    expect(within(item(1)).getByText("My turn")).toBeInTheDocument();
    expect(within(item(1)).getAllByRole("button", { name: EDIT_NAME })).toHaveLength(1);
    expect(within(item(1)).getAllByRole("button", { name: COPY_NAME })).toHaveLength(1);

    expect(within(item(2)).getByText("Decision")).toBeInTheDocument();
    expect(within(item(2)).getAllByRole("button", { name: EDIT_NAME })).toHaveLength(1);
    expect(item(2).querySelector('[data-paren="ooc"]')).not.toBeNull();
  });

  it("the flicker sits in the partner entry's one actions group, revealed with the others — DoD-9", async () => {
    stubFetch();
    renderRecord(seeded(threeEntries()), new TranslationState());

    const groups = partnerItem().querySelectorAll<HTMLElement>("[data-revealed]");
    expect(groups).toHaveLength(1);
    const group = groups[0] as HTMLElement;
    expect(group).toHaveAttribute("data-revealed", "false");
    expect(group.contains(flicker(SHOW_TRANSLATION))).toBe(true);
    expect(group.contains(within(partnerItem()).getByRole("button", { name: EDIT_NAME }))).toBe(true);
    expect(flicker(SHOW_TRANSLATION)).not.toBeDisabled();

    fireEvent.mouseEnter(partnerItem());
    await waitFor(() => {
      expect(partnerItem().querySelector("[data-revealed]")).toHaveAttribute("data-revealed", "true");
    });
  });

  it("no flicker state carries aria-pressed: the label alone states it (D15) — DoD-9", async () => {
    const backend = stubFetch();
    renderRecord(seeded(threeEntries()), new TranslationState());

    expect(flicker(SHOW_TRANSLATION)).not.toHaveAttribute("aria-pressed");

    await press(SHOW_TRANSLATION);
    expect(flicker(CANCEL_TRANSLATION)).not.toHaveAttribute("aria-pressed");

    backend.call(0).respond(translation(PARTNER_ID, TRANSLATED));
    await flush();
    expect(flicker(SHOW_ORIGINAL)).not.toHaveAttribute("aria-pressed");
  });
});
