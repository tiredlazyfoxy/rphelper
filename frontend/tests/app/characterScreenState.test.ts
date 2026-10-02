// Feature 009, step 006 — the character screen's state (DoD-1..DoD-11).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 006.context.md ("Draft vs character after archive / restore", "Name sent as typed",
// "Navigation is the caller's") and context.md's D1, D2, D9, D11, D12 plus the
// "No context, no methods" and "Never optimistic" constraints:
//   - a data class with observable fields only, "ready" in new mode and "loading" otherwise;
//   - pure isNewCharacter / isDirty / canSubmit;
//   - loadCharacter writes the row and the draft, maps 404 character_not_found to
//     "not-found" and every other failure to "failed", writes nothing once aborted and
//     never rejects;
//   - the four submits clear the error first, apply the server's returned row to the
//     workspace characters state, are never optimistic, and on failure set one fixed
//     sentence per action without rejecting.
import { isComputedProp, isObservableProp, runInAction, toJS } from "mobx";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Character } from "../../src/app/charactersApi";
import { CharactersState } from "../../src/app/charactersState";
import {
  CharacterScreenState,
  canSubmit,
  isDirty,
  isNewCharacter,
  loadCharacter,
  submitArchive,
  submitCreate,
  submitRestore,
  submitSave,
} from "../../src/app/characterScreenState";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- the spec's four sentences
const CREATE_ERROR = "Could not create the character.";
const SAVE_ERROR = "Could not save the character.";
const ARCHIVE_ERROR = "Could not archive the character.";
const RESTORE_ERROR = "Could not restore the character.";

// ---------------------------------------------------------------- fixtures
// Ids are decimal strings past Number.MAX_SAFE_INTEGER (context.md "Ids are strings").
const ID = "7250000000000000001";
const NEW_ID = "7250000000000000002";

const COLLECTION_PATH = "/api/characters";
const ITEM_PATH = `/api/characters/${ID}`;
const ARCHIVE_PATH = `${ITEM_PATH}/archive`;
const RESTORE_PATH = `${ITEM_PATH}/restore`;

const LOADED: Character = {
  id: ID,
  name: "Aria Vance",
  sheet: "# Aria\n\nA scribe who never finishes a sentence.",
  archived_at: null,
  created_at: "2026-03-14T09:26:53.000000+00:00",
  updated_at: "2026-03-14T09:26:53.000000+00:00",
};

/** What the server answers a PATCH of a typed, untrimmed name with: the stored value. */
const SAVED: Character = {
  ...LOADED,
  name: "Bo",
  sheet: "# Bo\n\nShorter now.",
  updated_at: "2026-03-20T18:04:11.000000+00:00",
};

const ARCHIVED: Character = {
  ...LOADED,
  archived_at: "2026-04-05T10:00:00.000000+00:00",
  updated_at: "2026-04-05T10:00:00.000000+00:00",
};

const RESTORED: Character = {
  ...LOADED,
  archived_at: null,
  updated_at: "2026-04-09T07:30:00.000000+00:00",
};

const CREATED: Character = {
  id: NEW_ID,
  name: "Aria Vance",
  sheet: "# Aria",
  archived_at: null,
  created_at: "2026-04-10T12:00:00.000000+00:00",
  updated_at: "2026-04-10T12:00:00.000000+00:00",
};

/** Another row already in the workspace list, so "unchanged" has something to say. */
const OTHER: Character = {
  id: "7250000000000000003",
  name: "Corvin Hale",
  sheet: "# Corvin",
  archived_at: null,
  created_at: "2026-02-01T08:15:42.000000+00:00",
  updated_at: "2026-02-01T08:15:42.000000+00:00",
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- harness

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

/** A domain envelope, the shape every non-2xx of ours carries. */
function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: "ql-77 went wrong.", detail: {} } }, status);
}

function serverError(): Response {
  return envelope("internal_error", 500);
}

/** FastAPI's native 422 — no domain code; the shared client calls it malformed. */
function native422(): Response {
  return jsonResponse(
    { detail: [{ loc: ["body", "name"], msg: "String should have at least 1 character" }] },
    422,
  );
}

function notFound(): Response {
  return envelope("character_not_found", 404);
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

type Seen = { method: string; path: string; search: string; body: unknown };

/** A URL-routed in-memory backend: the handler answers, every request is recorded. */
function stubBackend(handler: (request: Seen) => Response | Promise<Response>) {
  const calls: Seen[] = [];
  const mock = stubFetch(async (input, init) => {
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
  return { mock, calls };
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

function screenSnapshot(state: CharacterScreenState) {
  return {
    characterId: state.characterId,
    status: state.status,
    character: toJS(state.character),
    name: state.name,
    sheet: state.sheet,
    submitStatus: state.submitStatus,
    error: state.error,
  };
}

function rows(characters: CharactersState): Character[] {
  return toJS(characters.characters);
}

function ids(characters: CharactersState): string[] {
  return characters.characters.map((row) => row.id);
}

/** The one workspace characters state (D11), already loaded with rows. */
function workspaceWith(initial: Character[], showArchived = false): CharactersState {
  const characters = new CharactersState();
  runInAction(() => {
    characters.characters = initial.map((row) => ({ ...row }));
    characters.status = "ready";
    characters.showArchived = showArchived;
  });
  return characters;
}

/** A screen state as it stands right after a successful load of `character`. */
function loadedScreen(character: Character): CharacterScreenState {
  const state = new CharacterScreenState(character.id);
  runInAction(() => {
    state.status = "ready";
    state.character = { ...character };
    state.name = character.name;
    state.sheet = character.sheet;
  });
  return state;
}

/** A screen state in new mode with a draft typed into it. */
function newScreen(name: string, sheet: string): CharacterScreenState {
  const state = new CharacterScreenState(null);
  runInAction(() => {
    state.name = name;
    state.sheet = sheet;
  });
  return state;
}

type FailureCase = [label: string, answer: () => Response];

const FAILURES: FailureCase[] = [
  ["a 500 envelope", serverError],
  ["a native 422", native422],
];

// ---------------------------------------------------------------------------
describe("the new-mode state and canSubmit", () => {
  it("a state constructed with null is in new mode, ready, with no character and an empty draft — DoD-1", () => {
    const state = new CharacterScreenState(null);
    expect(isNewCharacter(state)).toBe(true);
    expect(screenSnapshot(state)).toEqual({
      characterId: null,
      status: "ready",
      character: null,
      name: "",
      sheet: "",
      submitStatus: "idle",
      error: null,
    });
  });

  it("a state constructed with an id is not in new mode and starts loading — DoD-1", () => {
    const state = new CharacterScreenState(ID);
    expect(isNewCharacter(state)).toBe(false);
    expect(screenSnapshot(state)).toEqual({
      characterId: ID,
      status: "loading",
      character: null,
      name: "",
      sheet: "",
      submitStatus: "idle",
      error: null,
    });
  });

  it("canSubmit is false on an empty draft name — DoD-1", () => {
    expect(canSubmit(new CharacterScreenState(null))).toBe(false);
  });

  it.each(["   ", "\t", "\n  \n"])(
    "canSubmit is false on a whitespace-only draft name, case %# — DoD-1",
    (name) => {
      expect(canSubmit(newScreen(name, "# Anything"))).toBe(false);
    },
  );

  it("canSubmit is true once the name has a non-space character — DoD-1", () => {
    expect(canSubmit(newScreen("Aria Vance", ""))).toBe(true);
    expect(canSubmit(newScreen("  Aria  ", ""))).toBe(true);
  });

  it("the class carries no method and no computed getter — DoD-1", () => {
    expect(Object.getOwnPropertyNames(CharacterScreenState.prototype)).toEqual(["constructor"]);
    const state = new CharacterScreenState(null);
    const observed = Object.getOwnPropertyNames(state).filter((name) =>
      isObservableProp(state, name),
    );
    expect(observed.slice().sort()).toEqual([
      "character",
      "characterId",
      "error",
      "name",
      "sheet",
      "status",
      "submitStatus",
    ]);
    const record = state as unknown as Record<string, unknown>;
    for (const name of Object.getOwnPropertyNames(state)) {
      expect(typeof record[name], `own property ${name}`).not.toBe("function");
      expect(isComputedProp(state, name), `own property ${name}`).toBe(false);
    }
  });

  it("the derivations and the effects are free functions, not members — DoD-1", () => {
    for (const fn of [
      isNewCharacter,
      isDirty,
      canSubmit,
      loadCharacter,
      submitCreate,
      submitSave,
      submitArchive,
      submitRestore,
    ]) {
      expect(typeof fn).toBe("function");
    }
    expect(Object.getOwnPropertyNames(CharacterScreenState.prototype)).not.toContain("submitSave");
  });
});

// ---------------------------------------------------------------------------
describe("submitCreate", () => {
  it("posts the draft's name and sheet to /api/characters — DoD-2", async () => {
    const { calls } = stubBackend(() => jsonResponse(CREATED, 201));
    const state = newScreen("Aria Vance", "# Aria");
    const characters = workspaceWith([]);
    await submitCreate(state, characters, () => {});
    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].path).toBe(COLLECTION_PATH);
    expect(calls[0].body).toEqual({ name: "Aria Vance", sheet: "# Aria" });
    expect(Object.keys(calls[0].body as Record<string, unknown>).sort()).toEqual(["name", "sheet"]);
  });

  it("calls onCreated exactly once with the response's id string — DoD-2", async () => {
    stubBackend(() => jsonResponse(CREATED, 201));
    const onCreated = vi.fn<(characterId: string) => void>();
    await submitCreate(newScreen("Aria Vance", "# Aria"), workspaceWith([]), onCreated);
    expect(onCreated).toHaveBeenCalledTimes(1);
    expect(onCreated).toHaveBeenCalledWith(NEW_ID);
    expect(typeof onCreated.mock.calls[0][0]).toBe("string");
  });

  it("applies the created row to the workspace characters state — DoD-2", async () => {
    stubBackend(() => jsonResponse(CREATED, 201));
    const characters = workspaceWith([OTHER]);
    await submitCreate(newScreen("Aria Vance", "# Aria"), characters, () => {});
    expect(ids(characters)).toContain(NEW_ID);
    expect(rows(characters).find((row) => row.id === NEW_ID)).toEqual(CREATED);
  });

  it("is submitting while the request is in flight and idle again after it — DoD-2", async () => {
    const pending = deferred<Response>();
    stubBackend(() => pending.promise);
    const state = newScreen("Aria Vance", "# Aria");
    const running = submitCreate(state, workspaceWith([]), () => {});
    await flush();
    expect(state.submitStatus).toBe("submitting");
    pending.resolve(jsonResponse(CREATED, 201));
    await expect(running).resolves.toBeUndefined();
    expect(state.submitStatus).toBe("idle");
    expect(state.error).toBeNull();
  });

  it.each(FAILURES)(
    "a failed create (%s) sets the create sentence and resolves — DoD-3",
    async (_label, answer) => {
      stubBackend(() => answer());
      const state = newScreen("Aria Vance", "# Aria");
      const characters = workspaceWith([OTHER]);
      const before = rows(characters);
      const onCreated = vi.fn<(characterId: string) => void>();
      await expect(submitCreate(state, characters, onCreated)).resolves.toBeUndefined();
      expect(state.error).toBe(CREATE_ERROR);
      expect(onCreated).not.toHaveBeenCalled();
      expect(rows(characters)).toEqual(before);
      expect(state.submitStatus).toBe("idle");
    },
  );

  it("a transport failure on create behaves the same way — DoD-3", async () => {
    stubBackend(() => {
      throw new TypeError("Failed to fetch");
    });
    const state = newScreen("Aria Vance", "# Aria");
    const characters = workspaceWith([OTHER]);
    const onCreated = vi.fn<(characterId: string) => void>();
    await expect(submitCreate(state, characters, onCreated)).resolves.toBeUndefined();
    expect(state.error).toBe(CREATE_ERROR);
    expect(onCreated).not.toHaveBeenCalled();
    expect(rows(characters)).toEqual([OTHER]);
    expect(state.submitStatus).toBe("idle");
  });
});

// ---------------------------------------------------------------------------
describe("loadCharacter", () => {
  it("a successful load is ready, with the row and the draft from the response — DoD-4", async () => {
    const { calls } = stubBackend(() => jsonResponse(LOADED, 200));
    const state = new CharacterScreenState(ID);
    await expect(loadCharacter(state)).resolves.toBeUndefined();
    expect(calls).toEqual([{ method: "GET", path: ITEM_PATH, search: "", body: undefined }]);
    expect(state.status).toBe("ready");
    expect(toJS(state.character)).toEqual(LOADED);
    expect(state.name).toBe(LOADED.name);
    expect(state.sheet).toBe(LOADED.sheet);
  });

  it("a 404 character_not_found is not-found — DoD-4", async () => {
    stubBackend(() => notFound());
    const state = new CharacterScreenState(ID);
    await expect(loadCharacter(state)).resolves.toBeUndefined();
    expect(state.status).toBe("not-found");
    expect(state.character).toBeNull();
  });

  it("a 500 envelope is failed — DoD-4", async () => {
    stubBackend(() => serverError());
    const state = new CharacterScreenState(ID);
    await expect(loadCharacter(state)).resolves.toBeUndefined();
    expect(state.status).toBe("failed");
    expect(state.character).toBeNull();
  });

  it("a transport failure is failed — DoD-4", async () => {
    stubBackend(() => {
      throw new TypeError("Failed to fetch");
    });
    const state = new CharacterScreenState(ID);
    await expect(loadCharacter(state)).resolves.toBeUndefined();
    expect(state.status).toBe("failed");
    expect(state.character).toBeNull();
  });

  it("a retry after a failure shows loading again — DoD-4", async () => {
    const pending = deferred<Response>();
    stubBackend(() => pending.promise);
    const state = new CharacterScreenState(ID);
    runInAction(() => {
      state.status = "failed";
    });
    const running = loadCharacter(state);
    await flush();
    expect(state.status).toBe("loading");
    pending.resolve(jsonResponse(LOADED, 200));
    await expect(running).resolves.toBeUndefined();
    expect(state.status).toBe("ready");
  });

  it("writes nothing when its signal aborts before the response settles — DoD-4", async () => {
    stubFetch(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          const signal = init?.signal;
          signal?.addEventListener("abort", () => {
            reject(signal.reason ?? new DOMException("The operation was aborted.", "AbortError"));
          });
        }),
    );
    const state = new CharacterScreenState(ID);
    const controller = new AbortController();
    const running = loadCharacter(state, controller.signal);
    await flush();
    const atAbort = screenSnapshot(state);
    controller.abort();
    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(screenSnapshot(state)).toEqual(atAbort);
  });

  it("writes nothing when the response arrives after the abort — DoD-4", async () => {
    const pending = deferred<Response>();
    stubBackend(() => pending.promise);
    const state = new CharacterScreenState(ID);
    const controller = new AbortController();
    const running = loadCharacter(state, controller.signal);
    await flush();
    const atAbort = screenSnapshot(state);
    controller.abort();
    pending.resolve(jsonResponse(LOADED, 200));
    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(screenSnapshot(state)).toEqual(atAbort);
    expect(state.character).toBeNull();
    expect(state.name).toBe("");
  });
});

// ---------------------------------------------------------------------------
describe("isDirty and canSubmit around a loaded character", () => {
  async function loadedViaServer(): Promise<CharacterScreenState> {
    stubBackend(() => jsonResponse(LOADED, 200));
    const state = new CharacterScreenState(ID);
    await loadCharacter(state);
    return state;
  }

  it("right after a successful load neither isDirty nor canSubmit holds — DoD-5", async () => {
    const state = await loadedViaServer();
    expect(isDirty(state)).toBe(false);
    expect(canSubmit(state)).toBe(false);
  });

  it("changing the draft name makes both true — DoD-5", async () => {
    const state = await loadedViaServer();
    runInAction(() => {
      state.name = "Aria Vancet";
    });
    expect(isDirty(state)).toBe(true);
    expect(canSubmit(state)).toBe(true);
  });

  it("changing the draft sheet makes both true — DoD-5", async () => {
    const state = await loadedViaServer();
    runInAction(() => {
      state.sheet = `${LOADED.sheet}\n\nAnd a second paragraph.`;
    });
    expect(isDirty(state)).toBe(true);
    expect(canSubmit(state)).toBe(true);
  });

  it("a whitespace-only draft name makes canSubmit false — DoD-5", async () => {
    const state = await loadedViaServer();
    runInAction(() => {
      state.name = "   ";
    });
    expect(canSubmit(state)).toBe(false);
  });

  it("canSubmit is false while a submit is in flight — DoD-5", async () => {
    const state = await loadedViaServer();
    runInAction(() => {
      state.name = "Aria Vancet";
      state.submitStatus = "submitting";
    });
    expect(canSubmit(state)).toBe(false);
    runInAction(() => {
      state.submitStatus = "idle";
    });
    expect(canSubmit(state)).toBe(true);
  });

  it("a new-mode draft with a name cannot be submitted while a submit is in flight — DoD-5", () => {
    const state = newScreen("Aria Vance", "# Aria");
    runInAction(() => {
      state.submitStatus = "submitting";
    });
    expect(canSubmit(state)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("submitSave", () => {
  it("patches both fields, is never optimistic, and adopts the server's row — DoD-6", async () => {
    const pending = deferred<Response>();
    const { calls } = stubBackend(() => pending.promise);
    const state = loadedScreen(LOADED);
    const characters = workspaceWith([LOADED, OTHER]);
    runInAction(() => {
      state.name = "  Bo  ";
      state.sheet = "# Bo\n\nShorter now.";
    });

    const running = submitSave(state, characters);
    await flush();

    // The request: both fields, the name exactly as typed (006.context.md).
    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("PATCH");
    expect(calls[0].path).toBe(ITEM_PATH);
    expect(calls[0].body).toEqual({ name: "  Bo  ", sheet: "# Bo\n\nShorter now." });
    expect(Object.keys(calls[0].body as Record<string, unknown>).sort()).toEqual(["name", "sheet"]);

    // Never optimistic: before the response, the loaded value still stands.
    expect(toJS(state.character)).toEqual(LOADED);
    expect(rows(characters).find((row) => row.id === ID)).toEqual(LOADED);

    pending.resolve(jsonResponse(SAVED, 200));
    await expect(running).resolves.toBeUndefined();

    // After it: the server's row, in `character` and in the draft.
    expect(toJS(state.character)).toEqual(SAVED);
    expect(state.name).toBe("Bo");
    expect(state.sheet).toBe(SAVED.sheet);
    expect(isDirty(state)).toBe(false);
    expect(rows(characters).find((row) => row.id === ID)).toEqual(SAVED);
    expect(state.error).toBeNull();
  });

  it.each(FAILURES)(
    "a failed save (%s) keeps the edited draft and the loaded character — DoD-7",
    async (_label, answer) => {
      stubBackend(() => answer());
      const state = loadedScreen(LOADED);
      const characters = workspaceWith([LOADED]);
      runInAction(() => {
        state.name = "Bo the Unsaved";
        state.sheet = "# Bo\n\nUnsaved body.";
      });
      await expect(submitSave(state, characters)).resolves.toBeUndefined();
      expect(state.error).toBe(SAVE_ERROR);
      expect(state.name).toBe("Bo the Unsaved");
      expect(state.sheet).toBe("# Bo\n\nUnsaved body.");
      expect(toJS(state.character)).toEqual(LOADED);
      expect(rows(characters)).toEqual([LOADED]);
    },
  );

  it("a transport failure on save behaves the same way — DoD-7", async () => {
    stubBackend(() => {
      throw new TypeError("Failed to fetch");
    });
    const state = loadedScreen(LOADED);
    runInAction(() => {
      state.name = "Bo the Unsaved";
    });
    await expect(submitSave(state, workspaceWith([LOADED]))).resolves.toBeUndefined();
    expect(state.error).toBe(SAVE_ERROR);
    expect(state.name).toBe("Bo the Unsaved");
    expect(toJS(state.character)).toEqual(LOADED);
  });
});

// ---------------------------------------------------------------------------
describe("submitArchive and submitRestore", () => {
  it("archive posts to the archive route, adopts archived_at and keeps the draft — DoD-8", async () => {
    const { calls } = stubBackend(() => jsonResponse(ARCHIVED, 200));
    const state = loadedScreen(LOADED);
    const characters = workspaceWith([LOADED, OTHER]);
    runInAction(() => {
      state.name = "Aria the Edited";
      state.sheet = "# Aria\n\nAn unsaved paragraph.";
    });

    await expect(submitArchive(state, characters)).resolves.toBeUndefined();

    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].path).toBe(ARCHIVE_PATH);
    expect(state.character?.archived_at).toBe(ARCHIVED.archived_at);
    expect(toJS(state.character)).toEqual(ARCHIVED);
    // The unsaved edits survive the archive (D9, 006.context.md).
    expect(state.name).toBe("Aria the Edited");
    expect(state.sheet).toBe("# Aria\n\nAn unsaved paragraph.");
    // Show archived is off, so the row leaves the working list (D11).
    expect(ids(characters)).toEqual([OTHER.id]);
    expect(state.error).toBeNull();
  });

  it("restore posts to the restore route, clears archived_at and puts the row back — DoD-9", async () => {
    const { calls } = stubBackend(() => jsonResponse(RESTORED, 200));
    const state = loadedScreen(ARCHIVED);
    const characters = workspaceWith([OTHER]);

    await expect(submitRestore(state, characters)).resolves.toBeUndefined();

    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].path).toBe(RESTORE_PATH);
    expect(state.character?.archived_at).toBeNull();
    expect(toJS(state.character)).toEqual(RESTORED);
    expect(ids(characters)).toContain(ID);
    expect(rows(characters).find((row) => row.id === ID)).toEqual(RESTORED);
    expect(state.error).toBeNull();
  });

  it.each(FAILURES)(
    "a failed archive (%s) sets the archive sentence and leaves the character alone — DoD-10",
    async (_label, answer) => {
      stubBackend(() => answer());
      const state = loadedScreen(LOADED);
      const characters = workspaceWith([LOADED]);
      await expect(submitArchive(state, characters)).resolves.toBeUndefined();
      expect(state.error).toBe(ARCHIVE_ERROR);
      expect(toJS(state.character)).toEqual(LOADED);
      expect(rows(characters)).toEqual([LOADED]);
    },
  );

  it.each(FAILURES)(
    "a failed restore (%s) sets the restore sentence and leaves the character alone — DoD-10",
    async (_label, answer) => {
      stubBackend(() => answer());
      const state = loadedScreen(ARCHIVED);
      const characters = workspaceWith([OTHER]);
      await expect(submitRestore(state, characters)).resolves.toBeUndefined();
      expect(state.error).toBe(RESTORE_ERROR);
      expect(toJS(state.character)).toEqual(ARCHIVED);
      expect(rows(characters)).toEqual([OTHER]);
    },
  );

  it("a transport failure on archive and on restore sets its own sentence — DoD-10", async () => {
    stubBackend(() => {
      throw new TypeError("Failed to fetch");
    });
    const archiving = loadedScreen(LOADED);
    await expect(submitArchive(archiving, workspaceWith([LOADED]))).resolves.toBeUndefined();
    expect(archiving.error).toBe(ARCHIVE_ERROR);
    expect(toJS(archiving.character)).toEqual(LOADED);

    const restoring = loadedScreen(ARCHIVED);
    await expect(submitRestore(restoring, workspaceWith([]))).resolves.toBeUndefined();
    expect(restoring.error).toBe(RESTORE_ERROR);
    expect(toJS(restoring.character)).toEqual(ARCHIVED);
  });
});

// ---------------------------------------------------------------------------
describe("a submit after a failure", () => {
  it("submitSave clears the previous error before its own request — DoD-11", async () => {
    const pending = deferred<Response>();
    let attempt = 0;
    const { calls } = stubBackend(() => {
      attempt += 1;
      return attempt === 1 ? serverError() : pending.promise;
    });
    const state = loadedScreen(LOADED);
    const characters = workspaceWith([LOADED]);
    runInAction(() => {
      state.name = "  Bo  ";
      state.sheet = "# Bo\n\nShorter now.";
    });

    await submitSave(state, characters);
    expect(state.error).toBe(SAVE_ERROR);

    const running = submitSave(state, characters);
    await flush();
    // The second request is already out, and the stale error is already gone.
    expect(calls).toHaveLength(2);
    expect(state.error).toBeNull();

    pending.resolve(jsonResponse(SAVED, 200));
    await expect(running).resolves.toBeUndefined();
    expect(state.error).toBeNull();
  });

  it("submitCreate clears the previous error before its own request — DoD-11", async () => {
    const pending = deferred<Response>();
    let attempt = 0;
    const { calls } = stubBackend(() => {
      attempt += 1;
      return attempt === 1 ? serverError() : pending.promise;
    });
    const state = newScreen("Aria Vance", "# Aria");
    const characters = workspaceWith([]);
    const onCreated = vi.fn<(characterId: string) => void>();

    await submitCreate(state, characters, onCreated);
    expect(state.error).toBe(CREATE_ERROR);

    const running = submitCreate(state, characters, onCreated);
    await flush();
    expect(calls).toHaveLength(2);
    expect(state.error).toBeNull();

    pending.resolve(jsonResponse(CREATED, 201));
    await expect(running).resolves.toBeUndefined();
    expect(state.error).toBeNull();
    expect(onCreated).toHaveBeenCalledTimes(1);
  });

  it("an archive after a save failure clears the save sentence before its request — DoD-11", async () => {
    const pending = deferred<Response>();
    let attempt = 0;
    const { calls } = stubBackend(() => {
      attempt += 1;
      return attempt === 1 ? serverError() : pending.promise;
    });
    const state = loadedScreen(LOADED);
    const characters = workspaceWith([LOADED]);
    runInAction(() => {
      state.name = "Bo the Unsaved";
    });

    await submitSave(state, characters);
    expect(state.error).toBe(SAVE_ERROR);

    const running = submitArchive(state, characters);
    await flush();
    expect(calls).toHaveLength(2);
    expect(calls[1].path).toBe(ARCHIVE_PATH);
    expect(state.error).toBeNull();

    pending.resolve(jsonResponse(ARCHIVED, 200));
    await expect(running).resolves.toBeUndefined();
    expect(state.error).toBeNull();
  });
});
