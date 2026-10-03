// Feature 017, step 007 — the settings page state (DoD-1..DoD-3).
// DoD-4..DoD-7 are SettingsScreen.test.tsx's; DoD-8 and DoD-9 are App.test.tsx's (with the
// entries.test.tsx stub amendment); DoD-10 is [manual/live] and carries no test.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 007.context.md ("The patch rule") and context.md's Wire contract (`GET` / `PATCH
// /api/me/settings`, `UserSettings`), D6 (trimmed, blank → null), D19 and the "Pure data
// contracts" / "Never optimistic" constraints:
//   - a fresh SettingsState is "idle", saved null, both texts "", not saving, no failure;
//   - loadSettings fills `saved` and both texts (null → ""), then "ready"; "failed" on any
//     failure; writes nothing once aborted; never rejects;
//   - isDirty compares each text trimmed (blank as null) against `saved`; canSave is ready,
//     dirty and not saving;
//   - saveSettings PATCHes only the changed keys (trimmed, blank → null), writes `saved` and both
//     texts from the response, clears saveFailure; any failure sets the fixed sentence and keeps
//     the typed text; never rejects. An empty patch sends nothing.
// Requests are recorded by exact method + pathname + query with the parsed JSON body, so a
// whole-object comparison catches a stray key.
import { runInAction } from "mobx";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { UserSettings } from "../../src/app/configurationApi";
import {
  SettingsState,
  canSave,
  isDirty,
  loadSettings,
  saveSettings,
  setPreferredLanguage,
  setRpLanguage,
} from "../../src/app/settingsState";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string; body: unknown };
type Handler = (request: Seen, init?: RequestInit) => Response | Promise<Response>;

// ---------------------------------------------------------------- the spec's names
const SETTINGS_PATH = "/api/me/settings";
const SAVE_FAILURE = "Could not save your settings.";

// ---------------------------------------------------------------- fixtures
const SERVED: UserSettings = { rp_language: "Japanese", preferred_language: null };
const BOTH_SET: UserSettings = { rp_language: "Japanese", preferred_language: "English" };

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- harness
function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function parseBody(init?: RequestInit): unknown {
  const raw = init?.body;
  if (raw === undefined || raw === null) return undefined;
  return JSON.parse(String(raw)) as unknown;
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: "ql-77 went wrong.", detail: {} } }, status);
}

function stubBackend(handler: Handler) {
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
    return handler(request, init);
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void };

function deferred<T>(): Deferred<T> {
  let resolve: (value: T) => void = () => {};
  const promise = new Promise<T>((settle) => {
    resolve = settle;
  });
  return { promise, resolve };
}

async function flush(): Promise<void> {
  for (let round = 0; round < 6; round += 1) await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
  for (let round = 0; round < 6; round += 1) await Promise.resolve();
}

function snapshot(state: SettingsState) {
  return {
    status: state.status,
    saved: state.saved === null ? null : { ...state.saved },
    rpLanguage: state.rpLanguage,
    preferredLanguage: state.preferredLanguage,
    saveStatus: state.saveStatus,
    saveFailure: state.saveFailure,
  };
}

/** A state as a successful load leaves it: ready, `saved` and both texts from `settings`. */
function readyState(settings: UserSettings): SettingsState {
  const state = new SettingsState();
  runInAction(() => {
    state.status = "ready";
    state.saved = { ...settings };
    state.rpLanguage = settings.rp_language ?? "";
    state.preferredLanguage = settings.preferred_language ?? "";
  });
  return state;
}

function patches(calls: Seen[]): Seen[] {
  return calls.filter((call) => call.method === "PATCH");
}

// ===========================================================================
describe("a fresh SettingsState and loadSettings (US-058.AC-1)", () => {
  it("a fresh state is idle, with saved null, both texts empty, not saving and no failure — DoD-1", () => {
    const state = new SettingsState();

    expect(snapshot(state)).toEqual({
      status: "idle",
      saved: null,
      rpLanguage: "",
      preferredLanguage: "",
      saveStatus: "idle",
      saveFailure: null,
    });
  });

  it("requests exactly GET /api/me/settings and nothing else — DoD-1", async () => {
    const { calls } = stubBackend(() => jsonResponse(SERVED, 200));
    const state = new SettingsState();

    await loadSettings(state);

    expect(calls).toEqual([{ method: "GET", path: SETTINGS_PATH, search: "", body: undefined }]);
  });

  it("is loading while the request is in flight — DoD-1", async () => {
    const pending = deferred<Response>();
    stubBackend(() => pending.promise);
    const state = new SettingsState();

    const running = loadSettings(state);
    await flush();
    expect(state.status).toBe("loading");

    pending.resolve(jsonResponse(SERVED, 200));
    await running;
  });

  it('on {rp_language: "Japanese", preferred_language: null} becomes ready with texts "Japanese" and "" — DoD-1', async () => {
    stubBackend(() => jsonResponse(SERVED, 200));
    const state = new SettingsState();

    await expect(loadSettings(state)).resolves.toBeUndefined();

    expect(state.status).toBe("ready");
    expect(state.saved).toEqual({ rp_language: "Japanese", preferred_language: null });
    expect(state.rpLanguage).toBe("Japanese");
    expect(state.preferredLanguage).toBe("");
  });

  type FailureCase = [label: string, answer: () => Response];
  const FAILURES: FailureCase[] = [
    ["a 500 envelope", () => envelope("internal_error", 500)],
    ["a 401 envelope", () => envelope("not_authenticated", 401)],
    [
      "a transport failure",
      () => {
        throw new TypeError("Failed to fetch");
      },
    ],
  ];

  it.each(FAILURES)("%s writes failed and resolves, with saved null and empty texts — DoD-1", async (_label, answer) => {
    stubBackend(() => answer());
    const state = new SettingsState();

    await expect(loadSettings(state)).resolves.toBeUndefined();

    expect(state.status).toBe("failed");
    expect(state.saved).toBeNull();
    expect(state.rpLanguage).toBe("");
    expect(state.preferredLanguage).toBe("");
  });

  it("writes nothing when its signal aborts before the response settles — DoD-1", async () => {
    stubBackend(
      (_request, init) =>
        new Promise<Response>((_resolve, reject) => {
          const signal = init?.signal;
          signal?.addEventListener("abort", () => {
            reject(signal.reason ?? new DOMException("The operation was aborted.", "AbortError"));
          });
        }),
    );
    const state = new SettingsState();
    const controller = new AbortController();

    const running = loadSettings(state, controller.signal);
    await flush();
    const atAbort = snapshot(state);
    controller.abort();

    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(snapshot(state)).toEqual(atAbort);
    expect(state.status).not.toBe("failed");
  });

  it("writes nothing when the response arrives after the abort — DoD-1", async () => {
    const pending = deferred<Response>();
    stubBackend(() => pending.promise);
    const state = new SettingsState();
    const controller = new AbortController();

    const running = loadSettings(state, controller.signal);
    await flush();
    const atAbort = snapshot(state);
    controller.abort();
    pending.resolve(jsonResponse(BOTH_SET, 200));

    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(snapshot(state)).toEqual(atAbort);
    expect(state.saved).toBeNull();
    expect(state.rpLanguage).toBe("");
    expect(state.status).not.toBe("ready");
  });
});

// ===========================================================================
describe("isDirty and canSave (D6, the patch rule)", () => {
  it("unchanged texts are not dirty and cannot be saved — DoD-2", () => {
    const state = readyState(BOTH_SET);

    expect(isDirty(state)).toBe(false);
    expect(canSave(state)).toBe(false);
  });

  it("unchanged texts with a null saved value (text \"\") are not dirty — DoD-2", () => {
    const state = readyState(SERVED);

    expect(state.preferredLanguage).toBe("");
    expect(isDirty(state)).toBe(false);
    expect(canSave(state)).toBe(false);
  });

  it('" Japanese " against saved "Japanese" is not dirty — DoD-2', () => {
    const state = readyState(SERVED);
    setRpLanguage(state, " Japanese ");

    expect(state.rpLanguage).toBe(" Japanese ");
    expect(isDirty(state)).toBe(false);
    expect(canSave(state)).toBe(false);
  });

  it('"" against saved "Japanese" is dirty and can be saved — DoD-2', () => {
    const state = readyState(SERVED);
    setRpLanguage(state, "");

    expect(isDirty(state)).toBe(true);
    expect(canSave(state)).toBe(true);
  });

  it("a whitespace-only text against a saved null is not dirty (blank is null) — DoD-2", () => {
    const state = readyState(SERVED);
    setPreferredLanguage(state, "   ");

    expect(isDirty(state)).toBe(false);
    expect(canSave(state)).toBe(false);
  });

  it("a new preferred language against a saved null is dirty — DoD-2", () => {
    const state = readyState(SERVED);
    setPreferredLanguage(state, "English");

    expect(state.preferredLanguage).toBe("English");
    expect(isDirty(state)).toBe(true);
    expect(canSave(state)).toBe(true);
  });

  it('while saveStatus is "saving" canSave is false, though dirty — DoD-2', () => {
    const state = readyState(SERVED);
    setRpLanguage(state, "French");
    runInAction(() => {
      state.saveStatus = "saving";
    });

    expect(isDirty(state)).toBe(true);
    expect(canSave(state)).toBe(false);
  });

  it.each(["idle", "loading", "failed"] as const)(
    'while status is "%s" canSave is false, though the texts differ — DoD-2',
    (status) => {
      const state = readyState(SERVED);
      setRpLanguage(state, "French");
      runInAction(() => {
        state.status = status;
      });

      expect(canSave(state)).toBe(false);
    },
  );
});

// ===========================================================================
describe("saveSettings sends only the changed keys (US-058.AC-1, D6)", () => {
  it('changing only the RP language to "French" PATCHes exactly {"rp_language":"French"} — DoD-3', async () => {
    const { calls } = stubBackend(() =>
      jsonResponse({ rp_language: "French", preferred_language: "English" }, 200),
    );
    const state = readyState(BOTH_SET);
    setRpLanguage(state, "French");

    await expect(saveSettings(state)).resolves.toBeUndefined();

    expect(calls).toEqual([
      { method: "PATCH", path: SETTINGS_PATH, search: "", body: { rp_language: "French" } },
    ]);
  });

  it('after the response the texts equal the served values, saved is the response and isDirty is false — DoD-3', async () => {
    stubBackend(() => jsonResponse({ rp_language: "French", preferred_language: "English" }, 200));
    const state = readyState(BOTH_SET);
    setRpLanguage(state, "French");

    await saveSettings(state);

    expect(state.saved).toEqual({ rp_language: "French", preferred_language: "English" });
    expect(state.rpLanguage).toBe("French");
    expect(state.preferredLanguage).toBe("English");
    expect(isDirty(state)).toBe(false);
    expect(state.saveFailure).toBeNull();
    expect(state.saveStatus).toBe("idle");
  });

  it('clearing the preferred language PATCHes exactly {"preferred_language":null} — DoD-3', async () => {
    const { calls } = stubBackend(() =>
      jsonResponse({ rp_language: "Japanese", preferred_language: null }, 200),
    );
    const state = readyState(BOTH_SET);
    setPreferredLanguage(state, "");

    await saveSettings(state);

    expect(calls).toEqual([
      { method: "PATCH", path: SETTINGS_PATH, search: "", body: { preferred_language: null } },
    ]);
    expect(state.saved).toEqual({ rp_language: "Japanese", preferred_language: null });
    expect(state.rpLanguage).toBe("Japanese");
    expect(state.preferredLanguage).toBe("");
    expect(isDirty(state)).toBe(false);
  });

  it("a text is sent trimmed, and the text afterwards is the served value — DoD-3", async () => {
    const { calls } = stubBackend(() =>
      jsonResponse({ rp_language: "French", preferred_language: "English" }, 200),
    );
    const state = readyState(BOTH_SET);
    setRpLanguage(state, "  French  ");

    await saveSettings(state);

    expect(patches(calls).map((call) => call.body)).toEqual([{ rp_language: "French" }]);
    expect(state.rpLanguage).toBe("French");
    expect(isDirty(state)).toBe(false);
  });

  it("changing both texts sends both keys — DoD-3", async () => {
    const { calls } = stubBackend(() =>
      jsonResponse({ rp_language: "French", preferred_language: "German" }, 200),
    );
    const state = readyState(BOTH_SET);
    setRpLanguage(state, "French");
    setPreferredLanguage(state, "German");

    await saveSettings(state);

    expect(patches(calls).map((call) => call.body)).toEqual([
      { rp_language: "French", preferred_language: "German" },
    ]);
  });

  it("is saving while the PATCH is in flight — DoD-3", async () => {
    const pending = deferred<Response>();
    stubBackend(() => pending.promise);
    const state = readyState(BOTH_SET);
    setRpLanguage(state, "French");

    const running = saveSettings(state);
    await flush();
    expect(state.saveStatus).toBe("saving");
    expect(canSave(state)).toBe(false);

    pending.resolve(jsonResponse({ rp_language: "French", preferred_language: "English" }, 200));
    await running;
    expect(state.saveStatus).toBe("idle");
  });

  type FailureCase = [label: string, answer: () => Response];
  const FAILURES: FailureCase[] = [
    ["a 500 envelope", () => envelope("internal_error", 500)],
    ["a 422 envelope", () => envelope("validation_error", 422)],
    [
      "a transport failure",
      () => {
        throw new TypeError("Failed to fetch");
      },
    ],
  ];

  it.each(FAILURES)(
    '%s sets "Could not save your settings." and keeps the typed text and saved — DoD-3',
    async (_label, answer) => {
      stubBackend(() => answer());
      const state = readyState(BOTH_SET);
      setRpLanguage(state, "French");

      await expect(saveSettings(state)).resolves.toBeUndefined();

      expect(state.saveFailure).toBe(SAVE_FAILURE);
      expect(state.rpLanguage).toBe("French");
      expect(state.preferredLanguage).toBe("English");
      expect(state.saved).toEqual(BOTH_SET);
      expect(state.saveStatus).toBe("idle");
      expect(isDirty(state)).toBe(true);
    },
  );

  it("a later successful save clears the failure — DoD-3", async () => {
    let fail = true;
    stubBackend(() => {
      if (fail) {
        fail = false;
        return envelope("internal_error", 500);
      }
      return jsonResponse({ rp_language: "French", preferred_language: "English" }, 200);
    });
    const state = readyState(BOTH_SET);
    setRpLanguage(state, "French");

    await saveSettings(state);
    expect(state.saveFailure).toBe(SAVE_FAILURE);

    await saveSettings(state);
    expect(state.saveFailure).toBeNull();
    expect(state.rpLanguage).toBe("French");
    expect(isDirty(state)).toBe(false);
  });

  it("with nothing changed it sends nothing and leaves the state as it is — DoD-3", async () => {
    const { calls } = stubBackend(() => jsonResponse(BOTH_SET, 200));
    const state = readyState(BOTH_SET);
    setRpLanguage(state, " Japanese ");
    const before = snapshot(state);

    await expect(saveSettings(state)).resolves.toBeUndefined();
    await flush();

    expect(calls).toEqual([]);
    expect(snapshot(state)).toEqual(before);
  });
});
