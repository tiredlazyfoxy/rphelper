// Fast feature 015 — translate-pending-indicator: the flicker's pending glyph, its cancel,
// and the entry's actions group revealed while that entry's translation is pending
// (DoD-1..DoD-7; DoD-8 / DoD-9 are the verifier's full-suite and typecheck gates).
//
// Expected behaviour comes from plan.md's Interface intent and Definition of done, context.md,
// and DEC-F015-2 (a loader carrying data-testid="translation-pending" replaces the language
// glyph while pending only), DEC-F015-3 (label, enabled state and no aria-pressed unchanged)
// and DEC-F015-4 (an entry's one [data-revealed] reads "true" while its translation is
// pending and "false" again once it resolves, is cancelled or fails, absent hover / focus).
// The language glyph is detected by Tabler's `tabler-icon-language` svg class (context.md).
// Never from the implementation.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { runInAction } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StreamRecord } from "../../src/app/StreamRecord";
import type { Message } from "../../src/app/streamApi";
import { StreamState } from "../../src/app/streamState";
import type { Translation } from "../../src/app/translationApi";
import { TranslationState } from "../../src/app/translationState";
import { AppProviders } from "../../src/shared/AppProviders";

// A failed translation is notified; mocked so the failure case stays silent and observable.
const notifyFailureSpy = vi.hoisted(() => vi.fn<(error: unknown) => void>());
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- the spec's names
const RECORD_NAME = "Settled record";
const SHOW_TRANSLATION = "Show translation";
const CANCEL_TRANSLATION = "Cancel translation";
const SHOW_ORIGINAL = "Show original";
const PENDING_TEST_ID = "translation-pending";
const LANGUAGE_GLYPH = "svg.tabler-icon-language";

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "7250000000000001500";
// Ids > Number.MAX_SAFE_INTEGER: a silent numeric coercion would change them.
const FIRST_ID = "7250000000000001501";
const SECOND_ID = "7250000000000001502";

const translationPath = (id: string): string => `/api/messages/${id}/translation`;

const FIRST_TEXT = "They wave.";
const SECOND_TEXT = "They smile.";
const TRANSLATED = "Они машут.";

const STAMP = "2026-11-05T09:00:00.000000+00:00";

/** A settled partner entry with all eight keys. */
function partner(id: string, text: string): Message {
  return {
    id,
    session_id: SESSION_ID,
    role: "user",
    kind: "partner",
    text,
    settled_at: STAMP,
    created_at: STAMP,
    updated_at: STAMP,
  };
}

function translation(messageId: string, text: string): Translation {
  return { message_id: messageId, target_language: "Russian", text, cached: false };
}

/** The server's failure envelope (502 translation_failed). */
function failureEnvelope(messageId: string): unknown {
  return {
    error: {
      code: "translation_failed",
      message: "The translation failed. Showing the original.",
      detail: { message_id: messageId },
    },
  };
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

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

type Call = {
  readonly key: string;
  readonly signal: AbortSignal | undefined;
  respond: (body: unknown, status?: number) => void;
};

type Backend = {
  readonly calls: Call[];
  call: (index: number) => Call;
};

/**
 * A fetch stub with one deferred promise per call: every call stays pending until the test
 * responds, which is how "while the request is unresolved" is observable. A pending call
 * rejects with an AbortError as soon as its signal aborts, as the platform does.
 */
function stubFetch(): Backend {
  const calls: Call[] = [];
  const mock = vi.fn<FetchFn>((input, init) => {
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
      key: `${requestMethod(input, init)} ${requestUrl(input).pathname}`,
      signal,
      respond: (body, status = 200) => settle(jsonResponse(body, status)),
    });
    return promise;
  });
  vi.stubGlobal("fetch", mock);
  return {
    calls,
    call: (index) => {
      const call = calls[index];
      if (call === undefined) throw new Error(`no fetch call at index ${index}`);
      return call;
    },
  };
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

function item(index: number): HTMLElement {
  const items = within(screen.getByRole("list", { name: RECORD_NAME })).getAllByRole("listitem");
  return items[index] as HTMLElement;
}

function flicker(index: number, label: string): HTMLElement {
  return within(item(index)).getByRole("button", { name: label });
}

/**
 * Presses a flicker with a bare click event: no pointer move (so no hover) and no focus move,
 * so a reveal can only come from the pending state (DoD-6 / DoD-7 "no hover, no focus").
 */
async function press(index: number, label: string): Promise<void> {
  fireEvent.click(flicker(index, label));
  await flush();
}

/** The entry's one actions group; asserts there is exactly one `[data-revealed]` (DoD-7). */
function revealedOf(index: number): string | null {
  const groups = item(index).querySelectorAll<HTMLElement>("[data-revealed]");
  expect(groups).toHaveLength(1);
  return (groups[0] as HTMLElement).getAttribute("data-revealed");
}

function expectLanguageGlyph(button: HTMLElement): void {
  expect(button.querySelector(LANGUAGE_GLYPH)).not.toBeNull();
  expect(within(button).queryByTestId(PENDING_TEST_ID)).toBeNull();
}

function expectPendingGlyph(button: HTMLElement): void {
  expect(within(button).getByTestId(PENDING_TEST_ID)).toBeInTheDocument();
  expect(button.querySelector(LANGUAGE_GLYPH)).toBeNull();
}

// ===========================================================================
// DoD-1 — at rest the flicker shows the language glyph
// ===========================================================================
describe("at rest the flicker keeps the language glyph (D15 unchanged for original)", () => {
  it('"Show translation" contains the language glyph and nothing has test id translation-pending — DoD-1', () => {
    const backend = stubFetch();
    renderRecord(seeded([partner(FIRST_ID, FIRST_TEXT)]), new TranslationState());

    expectLanguageGlyph(flicker(0, SHOW_TRANSLATION));
    expect(screen.queryByTestId(PENDING_TEST_ID)).toBeNull();
    expect(backend.calls).toHaveLength(0);
  });
});

// ===========================================================================
// DoD-2 / DoD-3 — the pending glyph and the unchanged semantics
// ===========================================================================
describe("while pending the flicker shows a loader (US-045.AC-1, DEC-F015-2, DEC-F015-3)", () => {
  it('the single "Cancel translation" button holds the pending glyph, not the language glyph, and the body keeps the original — DoD-2', async () => {
    stubFetch();
    renderRecord(seeded([partner(FIRST_ID, FIRST_TEXT)]), new TranslationState());

    await press(0, SHOW_TRANSLATION);

    const buttons = within(item(0)).getAllByRole("button", { name: CANCEL_TRANSLATION });
    expect(buttons).toHaveLength(1);
    expectPendingGlyph(buttons[0] as HTMLElement);
    expect(item(0).textContent).toContain(FIRST_TEXT);
    expect(item(0).textContent).not.toContain(TRANSLATED);
  });

  it('the pending "Cancel translation" is enabled, has no aria-pressed, and is the entry\'s only button of that name — DoD-3', async () => {
    stubFetch();
    renderRecord(seeded([partner(FIRST_ID, FIRST_TEXT)]), new TranslationState());

    await press(0, SHOW_TRANSLATION);

    const buttons = within(item(0)).getAllByRole("button", { name: CANCEL_TRANSLATION });
    expect(buttons).toHaveLength(1);
    const button = buttons[0] as HTMLElement;
    expect(button).not.toBeDisabled();
    expect(button).not.toHaveAttribute("aria-pressed");
  });
});

// ===========================================================================
// DoD-4 — cancelling while pending restores the language glyph
// ===========================================================================
describe("cancelling a pending translation (DEC-F015-2, workspace-shell 'The stop control')", () => {
  it('pressing "Cancel translation" returns to "Show translation" with the language glyph and no pending glyph — DoD-4', async () => {
    const backend = stubFetch();
    renderRecord(seeded([partner(FIRST_ID, FIRST_TEXT)]), new TranslationState());

    await press(0, SHOW_TRANSLATION);
    expectPendingGlyph(flicker(0, CANCEL_TRANSLATION));

    await press(0, CANCEL_TRANSLATION);

    expect(backend.call(0).signal?.aborted).toBe(true);
    expect(within(item(0)).queryByRole("button", { name: CANCEL_TRANSLATION })).toBeNull();
    expectLanguageGlyph(flicker(0, SHOW_TRANSLATION));
    expect(screen.queryByTestId(PENDING_TEST_ID)).toBeNull();
  });
});

// ===========================================================================
// DoD-5 — a landed translation shows the language glyph again
// ===========================================================================
describe("once the translation lands (US-045.AC-1)", () => {
  it('the button reads "Show original", holds the language glyph and no pending glyph — DoD-5', async () => {
    const backend = stubFetch();
    renderRecord(seeded([partner(FIRST_ID, FIRST_TEXT)]), new TranslationState());

    await press(0, SHOW_TRANSLATION);
    expect(backend.call(0).key).toBe(`POST ${translationPath(FIRST_ID)}`);
    backend.call(0).respond(translation(FIRST_ID, TRANSLATED));
    await flush();

    expect(item(0).textContent).toContain(TRANSLATED);
    expectLanguageGlyph(flicker(0, SHOW_ORIGINAL));
    expect(screen.queryByTestId(PENDING_TEST_ID)).toBeNull();
  });
});

// ===========================================================================
// DoD-6 / DoD-7 — reveal while pending
// ===========================================================================
describe("an entry's actions group is revealed while its translation is pending (DEC-F015-4)", () => {
  /** Two partner entries; the first is flicked without hover or focus, the second is not. */
  async function pendOnFirst(): Promise<Backend> {
    const backend = stubFetch();
    renderRecord(
      seeded([partner(FIRST_ID, FIRST_TEXT), partner(SECOND_ID, SECOND_TEXT)]),
      new TranslationState(),
    );
    expect(revealedOf(0)).toBe("false");
    expect(revealedOf(1)).toBe("false");

    await press(0, SHOW_TRANSLATION);

    // Precondition: the reveal cannot come from focus-within.
    expect(item(0).contains(document.activeElement)).toBe(false);
    await waitFor(() => {
      expect(revealedOf(0)).toBe("true");
    });
    return backend;
  }

  it('pressing "Show translation" on the first entry reveals only that entry while unresolved — DoD-6', async () => {
    await pendOnFirst();

    expect(revealedOf(0)).toBe("true");
    expect(revealedOf(1)).toBe("false");
  });

  it('after the request answers with text the entry reads "false" again, one [data-revealed] throughout — DoD-7', async () => {
    const backend = await pendOnFirst();

    backend.call(0).respond(translation(FIRST_ID, TRANSLATED));
    await flush();

    await waitFor(() => {
      expect(revealedOf(0)).toBe("false");
    });
    expect(item(0).textContent).toContain(TRANSLATED);
    expect(revealedOf(1)).toBe("false");
  });

  it('after "Cancel translation" the entry reads "false" again, one [data-revealed] throughout — DoD-7', async () => {
    await pendOnFirst();

    await press(0, CANCEL_TRANSLATION);

    await waitFor(() => {
      expect(revealedOf(0)).toBe("false");
    });
    expect(flicker(0, SHOW_TRANSLATION)).toBeInTheDocument();
    expect(revealedOf(1)).toBe("false");
  });

  it('after a 502 translation_failed the entry reads "false" again, one [data-revealed] throughout — DoD-7 (US-048.AC-1)', async () => {
    const backend = await pendOnFirst();

    backend.call(0).respond(failureEnvelope(FIRST_ID), 502);
    await flush();

    await waitFor(() => {
      expect(revealedOf(0)).toBe("false");
    });
    expect(item(0).textContent).toContain(FIRST_TEXT);
    expect(flicker(0, SHOW_TRANSLATION)).toBeInTheDocument();
    expect(revealedOf(1)).toBe("false");
  });
});
