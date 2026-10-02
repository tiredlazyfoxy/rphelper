// Feature 010, step 005 — the setup modal's draft (DoD-1..DoD-4).
// DoD-5..DoD-9 live in SetupModal.test.tsx; DoD-10 is [manual/live] and carries no test.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 005.context.md and context.md's D2, D8, D12 and the "No context, no methods" / "Never
// optimistic" / "Ids are strings" constraints:
// - a data class with observable fields only (characterId, original, name, description,
//   submitStatus, error), the original's values in edit mode and empty strings in create
//   mode;
// - `isEditing` is "original is non-null"; `isDirty` is "differs from the original" in edit
//   mode and always true in create mode; `canSubmit` is "trimmed name non-empty AND nothing
//   submitting AND dirty";
// - `submitSetup` clears `error`, sets "submitting", POSTs name+description to the draft's
//   character (create) or PATCHes *both* to the original's id (edit), calls `onSaved` with
//   the **server-returned** row, reports exactly "Could not create the setup." / "Could not
//   save the setup." on failure while keeping the typed values, returns to "idle", writes
//   nothing once aborted and never rejects;
// - the name is sent **as typed** (Interface intent, "The name is sent as typed").
//
// Recognition conventions (from the spec's wording, for the verifier):
// - "POSTs the collection path" is `POST /api/characters/<characterId>/setups`; "PATCHes the
//   original's id" is `PATCH /api/setups/<original id>` (context.md "Wire contract").
// - "the response's setup" is proved with a server-trimmed name that differs from the typed
//   one, so re-rendering the typed value would fail.
// - `fetch` is stubbed per test with `vi.stubGlobal`; no render happens in this file.
import { runInAction, toJS } from "mobx";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Setup } from "../../src/app/setupsApi";
import {
  canSubmit,
  isDirty,
  isEditing,
  setDraftDescription,
  setDraftName,
  SetupDraft,
  submitSetup,
} from "../../src/app/setupDraft";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string; body: unknown };

// ---------------------------------------------------------------- the spec's sentences
const CREATE_FAILED = "Could not create the setup.";
const SAVE_FAILED = "Could not save the setup.";

// ---------------------------------------------------------------- fixtures
// Every id is a decimal string past Number.MAX_SAFE_INTEGER, so any coercion would show up
// in the request path (context.md "Ids are strings in every frontend file").
const CHARACTER_ID = "7250000000000000001";
const SETUP_ID = "7260000000000000001";
const CREATED_ID = "9007199254740993"; // 2^53 + 1

const COLLECTION_PATH = `/api/characters/${CHARACTER_ID}/setups`;
const ITEM_PATH = `/api/setups/${SETUP_ID}`;

/** Typed with a trailing space: the name travels as typed, the server does the stripping. */
const TYPED_NAME = "The Gilded Tavern ";
const TYPED_DESCRIPTION = "# The Gilded Tavern\n\nSmoke and lute strings.";

/** The row an edit-mode draft is built from. */
const TAVERN: Setup = {
  id: SETUP_ID,
  character_id: CHARACTER_ID,
  name: "The Gilded Tavern",
  description: "# The Gilded Tavern\n\nSmoke and lute strings.",
  archived_at: null,
  created_at: "2026-03-14T09:26:53.000000+00:00",
  updated_at: "2026-03-14T09:26:53.000000+00:00",
};

/** What the server answers the create with — the name stripped (D8). */
const CREATED: Setup = {
  id: CREATED_ID,
  character_id: CHARACTER_ID,
  name: "The Gilded Tavern",
  description: TYPED_DESCRIPTION,
  archived_at: null,
  created_at: "2026-04-10T12:00:00.000000+00:00",
  updated_at: "2026-04-10T12:00:00.000000+00:00",
};

/** What the server answers the save with — again a stripped name, so it cannot be the typed one. */
const SAVED: Setup = {
  ...TAVERN,
  name: "Nightfall Harbour",
  description: "# Nightfall Harbour\n\nTwo ships, no harbourmaster.",
  updated_at: "2026-04-11T08:30:00.000000+00:00",
};

const EDITED_NAME = "Nightfall Harbour ";
const EDITED_DESCRIPTION = "# Nightfall Harbour\n\nTwo ships, no harbourmaster.";

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

/** A domain envelope — the shape every non-2xx of ours carries. */
function failureResponse(): Response {
  return jsonResponse(
    { error: { code: "internal_error", message: "The setup shelf collapsed zq-63.", detail: {} } },
    500,
  );
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function parseBody(init?: RequestInit): unknown {
  const body = init?.body;
  if (body === undefined || body === null) return undefined;
  return JSON.parse(String(body)) as unknown;
}

/** Records every request in order and answers with `handler`'s response. */
function stubBackend(handler: (request: Seen) => Response | Promise<Response>) {
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>(async (input, init) => {
    const url = requestUrl(input);
    const request: Seen = {
      method: requestMethod(input, init),
      path: url.pathname,
      search: url.search,
      body: parseBody(init),
    };
    calls.push(request);
    return handler(request);
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

function bodyKeys(request: Seen): string[] {
  return Object.keys(request.body as Record<string, unknown>).sort();
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

async function flush(rounds = 4): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await new Promise<void>((resolve) => setImmediate(resolve));
  }
}

// ---------------------------------------------------------------- draft helpers
function snapshot(draft: SetupDraft) {
  return {
    characterId: draft.characterId,
    original: toJS(draft.original),
    name: draft.name,
    description: draft.description,
    submitStatus: draft.submitStatus,
    error: draft.error,
  };
}

function createDraft(): SetupDraft {
  return new SetupDraft(CHARACTER_ID, null);
}

function editDraft(): SetupDraft {
  return new SetupDraft(CHARACTER_ID, TAVERN);
}

/** A create-mode draft carrying typed values, as the modal would hand it to the submit. */
function typedCreateDraft(): SetupDraft {
  const draft = createDraft();
  setDraftName(draft, TYPED_NAME);
  setDraftDescription(draft, TYPED_DESCRIPTION);
  return draft;
}

/** An edit-mode draft whose two fields were both changed. */
function typedEditDraft(): SetupDraft {
  const draft = editDraft();
  setDraftName(draft, EDITED_NAME);
  setDraftDescription(draft, EDITED_DESCRIPTION);
  return draft;
}

function savedSink() {
  const calls: Setup[] = [];
  return { calls, onSaved: (saved: Setup) => void calls.push(saved) };
}

// ---------------------------------------------------------------------------
describe("a create-mode draft (setup is null)", () => {
  it("starts empty, is not editing and cannot be submitted — DoD-1", () => {
    const draft = createDraft();
    expect(snapshot(draft)).toEqual({
      characterId: CHARACTER_ID,
      original: null,
      name: "",
      description: "",
      submitStatus: "idle",
      error: null,
    });
    expect(isEditing(draft)).toBe(false);
    expect(canSubmit(draft)).toBe(false);
  });

  it("is dirty from the start, because there is nothing to differ from — DoD-1", () => {
    expect(isDirty(createDraft())).toBe(true);
  });

  it("cannot be submitted with a whitespace-only name — DoD-1", () => {
    const draft = createDraft();
    setDraftName(draft, "   ");
    expect(canSubmit(draft)).toBe(false);
    setDraftName(draft, "\t\n ");
    expect(canSubmit(draft)).toBe(false);
  });

  it("can be submitted once the name has a non-space character — DoD-1", () => {
    const draft = createDraft();
    setDraftName(draft, " T ");
    expect(canSubmit(draft)).toBe(true);
    setDraftName(draft, TYPED_NAME);
    expect(canSubmit(draft)).toBe(true);
  });

  it("cannot be submitted while the submit status is submitting — DoD-1", () => {
    const draft = typedCreateDraft();
    expect(canSubmit(draft)).toBe(true);
    runInAction(() => {
      draft.submitStatus = "submitting";
    });
    expect(canSubmit(draft)).toBe(false);
    runInAction(() => {
      draft.submitStatus = "idle";
    });
    expect(canSubmit(draft)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
describe("an edit-mode draft built from a setup", () => {
  it("starts with that setup's values, is editing, and is neither dirty nor submittable — DoD-1", () => {
    const draft = editDraft();
    expect(snapshot(draft)).toEqual({
      characterId: CHARACTER_ID,
      original: TAVERN,
      name: TAVERN.name,
      description: TAVERN.description,
      submitStatus: "idle",
      error: null,
    });
    expect(isEditing(draft)).toBe(true);
    expect(isDirty(draft)).toBe(false);
    expect(canSubmit(draft)).toBe(false);
  });

  it("becomes dirty and submittable when the name changes — DoD-1", () => {
    const draft = editDraft();
    setDraftName(draft, EDITED_NAME);
    expect(isDirty(draft)).toBe(true);
    expect(canSubmit(draft)).toBe(true);
  });

  it("becomes dirty and submittable when the description changes — DoD-1", () => {
    const draft = editDraft();
    setDraftDescription(draft, EDITED_DESCRIPTION);
    expect(isDirty(draft)).toBe(true);
    expect(canSubmit(draft)).toBe(true);
  });

  it("is dirty but not submittable once the name is cleared — DoD-1", () => {
    const draft = editDraft();
    setDraftName(draft, "   ");
    expect(isDirty(draft)).toBe(true);
    expect(canSubmit(draft)).toBe(false);
  });

  it("is not dirty again when an edited field is put back to the original's value — DoD-1", () => {
    const draft = editDraft();
    setDraftDescription(draft, EDITED_DESCRIPTION);
    expect(isDirty(draft)).toBe(true);
    setDraftDescription(draft, TAVERN.description);
    expect(isDirty(draft)).toBe(false);
    expect(canSubmit(draft)).toBe(false);
  });

  it("cannot be submitted while the submit status is submitting, change or no change — DoD-1", () => {
    const draft = typedEditDraft();
    expect(canSubmit(draft)).toBe(true);
    runInAction(() => {
      draft.submitStatus = "submitting";
    });
    expect(canSubmit(draft)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("submitSetup in create mode", () => {
  it("POSTs the character's collection path with the draft's name and description — DoD-2", async () => {
    const { calls } = stubBackend(() => jsonResponse(CREATED, 201));
    const draft = typedCreateDraft();
    const sink = savedSink();
    await submitSetup(draft, sink.onSaved);
    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].path).toBe(COLLECTION_PATH);
    expect(bodyKeys(calls[0])).toEqual(["description", "name"]);
    // The name travels as typed — trailing space included; the server strips it.
    expect(calls[0].body).toEqual({ name: TYPED_NAME, description: TYPED_DESCRIPTION });
  });

  it("calls onSaved exactly once with the server's returned setup — DoD-2", async () => {
    stubBackend(() => jsonResponse(CREATED, 201));
    const draft = typedCreateDraft();
    const sink = savedSink();
    await submitSetup(draft, sink.onSaved);
    expect(sink.calls).toHaveLength(1);
    expect(sink.calls[0]).toEqual(CREATED);
    // The response's name, not the typed one (never optimistic).
    expect(sink.calls[0].name).not.toBe(TYPED_NAME);
  });

  it("is back to idle with no error after a successful create — DoD-2", async () => {
    stubBackend(() => jsonResponse(CREATED, 201));
    const draft = typedCreateDraft();
    const sink = savedSink();
    await expect(submitSetup(draft, sink.onSaved)).resolves.toBeUndefined();
    expect(draft.submitStatus).toBe("idle");
    expect(draft.error).toBeNull();
  });

  it("is submitting while the create request is in flight — DoD-2", async () => {
    const pending = deferred<Response>();
    stubBackend(() => pending.promise);
    const draft = typedCreateDraft();
    const sink = savedSink();
    const running = submitSetup(draft, sink.onSaved);
    await flush();
    expect(draft.submitStatus).toBe("submitting");
    expect(sink.calls).toEqual([]);
    pending.resolve(jsonResponse(CREATED, 201));
    await running;
    expect(draft.submitStatus).toBe("idle");
  });
});

// ---------------------------------------------------------------------------
describe("submitSetup in edit mode", () => {
  it("PATCHes the original's own path with both name and description — DoD-3", async () => {
    const { calls } = stubBackend(() => jsonResponse(SAVED, 200));
    const draft = typedEditDraft();
    const sink = savedSink();
    await submitSetup(draft, sink.onSaved);
    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("PATCH");
    expect(calls[0].path).toBe(ITEM_PATH);
    // D2: edit sends both fields together in one PATCH.
    expect(bodyKeys(calls[0])).toEqual(["description", "name"]);
    expect(calls[0].body).toEqual({ name: EDITED_NAME, description: EDITED_DESCRIPTION });
  });

  it("sends both fields even when only the description was changed — DoD-3", async () => {
    const { calls } = stubBackend(() => jsonResponse(SAVED, 200));
    const draft = editDraft();
    setDraftDescription(draft, EDITED_DESCRIPTION);
    const sink = savedSink();
    await submitSetup(draft, sink.onSaved);
    expect(calls).toHaveLength(1);
    expect(bodyKeys(calls[0])).toEqual(["description", "name"]);
    expect(calls[0].body).toEqual({ name: TAVERN.name, description: EDITED_DESCRIPTION });
  });

  it("calls onSaved once with the response's setup, not with the typed values — DoD-3", async () => {
    stubBackend(() => jsonResponse(SAVED, 200));
    const draft = typedEditDraft();
    const sink = savedSink();
    await submitSetup(draft, sink.onSaved);
    expect(sink.calls).toHaveLength(1);
    expect(sink.calls[0]).toEqual(SAVED);
    expect(sink.calls[0].name).toBe("Nightfall Harbour");
    expect(sink.calls[0].name).not.toBe(EDITED_NAME);
    expect(draft.submitStatus).toBe("idle");
  });
});

// ---------------------------------------------------------------------------
describe("a failed submitSetup", () => {
  it("reports exactly the create sentence, keeps the typed values and resolves — DoD-4", async () => {
    stubBackend(() => failureResponse());
    const draft = typedCreateDraft();
    const sink = savedSink();
    await expect(submitSetup(draft, sink.onSaved)).resolves.toBeUndefined();
    expect(draft.error).toBe(CREATE_FAILED);
    expect(draft.submitStatus).toBe("idle");
    expect(draft.name).toBe(TYPED_NAME);
    expect(draft.description).toBe(TYPED_DESCRIPTION);
    expect(sink.calls).toEqual([]);
  });

  it("reports exactly the save sentence, keeps the typed values and resolves — DoD-4", async () => {
    stubBackend(() => failureResponse());
    const draft = typedEditDraft();
    const sink = savedSink();
    await expect(submitSetup(draft, sink.onSaved)).resolves.toBeUndefined();
    expect(draft.error).toBe(SAVE_FAILED);
    expect(draft.submitStatus).toBe("idle");
    expect(draft.name).toBe(EDITED_NAME);
    expect(draft.description).toBe(EDITED_DESCRIPTION);
    expect(sink.calls).toEqual([]);
  });

  it("reports a transport failure the same way, without rejecting — DoD-4", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<FetchFn>(() => Promise.reject(new TypeError("Failed to fetch"))),
    );
    const draft = typedCreateDraft();
    const sink = savedSink();
    await expect(submitSetup(draft, sink.onSaved)).resolves.toBeUndefined();
    expect(draft.error).toBe(CREATE_FAILED);
    expect(draft.submitStatus).toBe("idle");
    expect(sink.calls).toEqual([]);
  });

  it("clears the previous error before the next create request — DoD-4", async () => {
    stubBackend(() => failureResponse());
    const draft = typedCreateDraft();
    const sink = savedSink();
    await submitSetup(draft, sink.onSaved);
    expect(draft.error).toBe(CREATE_FAILED);

    const errorAtRequest: Array<string | null> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn<FetchFn>(() => {
        errorAtRequest.push(draft.error);
        return Promise.resolve(jsonResponse(CREATED, 201));
      }),
    );
    await submitSetup(draft, sink.onSaved);
    expect(errorAtRequest).toEqual([null]);
    expect(draft.error).toBeNull();
  });

  it("clears the previous error before the next save request — DoD-4", async () => {
    stubBackend(() => failureResponse());
    const draft = typedEditDraft();
    const sink = savedSink();
    await submitSetup(draft, sink.onSaved);
    expect(draft.error).toBe(SAVE_FAILED);

    const errorAtRequest: Array<string | null> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn<FetchFn>(() => {
        errorAtRequest.push(draft.error);
        return Promise.resolve(jsonResponse(SAVED, 200));
      }),
    );
    await submitSetup(draft, sink.onSaved);
    expect(errorAtRequest).toEqual([null]);
    expect(draft.error).toBeNull();
  });

  it("writes nothing and does not call onSaved when its signal aborts before the response settles — DoD-4", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<FetchFn>(
        (_input, init) =>
          new Promise<Response>((_resolve, reject) => {
            const signal = init?.signal;
            signal?.addEventListener("abort", () => {
              reject(signal.reason ?? new DOMException("The operation was aborted.", "AbortError"));
            });
          }),
      ),
    );
    const draft = typedCreateDraft();
    const sink = savedSink();
    const controller = new AbortController();
    const running = submitSetup(draft, sink.onSaved, controller.signal);
    await flush();
    const atAbort = snapshot(draft);
    controller.abort();
    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(snapshot(draft)).toEqual(atAbort);
    expect(sink.calls).toEqual([]);
  });

  it("writes nothing and does not call onSaved when the response arrives after the abort — DoD-4", async () => {
    const pending = deferred<Response>();
    stubBackend(() => pending.promise);
    const draft = typedEditDraft();
    const sink = savedSink();
    const controller = new AbortController();
    const running = submitSetup(draft, sink.onSaved, controller.signal);
    await flush();
    const atAbort = snapshot(draft);
    controller.abort();
    pending.resolve(jsonResponse(SAVED, 200));
    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(snapshot(draft)).toEqual(atAbort);
    expect(sink.calls).toEqual([]);
  });
});
